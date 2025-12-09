"""
自定义Agent执行器 V2 - 重新设计

核心改进:
1. 执行时由LLM动态规划步骤,而非使用DB中的静态steps
2. 使用统一state dict管理数据流
3. 自然语言描述期望,而非符号化checkpoint  
4. 明确回退策略表,关键步骤失败时有清晰的回退路径
"""

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.context import ExecutionContext
from core.tools.base import get_tool_compress_function
from utils.llm_client import get_llm_client


class UnifiedExecutionState(ExecutionContext):
    """
    统一执行状态 - 基于state dict的执行状态管理

    核心理念:
    - state dict是所有工具读写数据的单一真相源
    - 简化的结构,只保留核心字段
    - 质量监控字段方便checkpoint判定
    """

    def __init__(
        self,
        db: Any = None,
        es_client: Any = None,
        es_index: str = "dochive_documents",
        template_id: Optional[int] = None,
        session_id: Optional[str] = None,
        query: str = "",
        agent_goals: Optional[List[str]] = None,
        agent_constraints: Optional[List[str]] = None,
        rollback_plan: Optional[Dict[str, str]] = None,
        **extra,
    ):
        super().__init__(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            session_id=session_id,
            query=query,
            **extra,
        )

        # 存储Agent定义的元信息
        self.agent_goals = agent_goals or []
        self.agent_constraints = agent_constraints or []
        self.rollback_plan = rollback_plan or {}

        # 初始化统一状态字典(只包含固定字段,其他字段由LLM动态生成)
        self.state = {
            # 固定字段:用户输入
            "inputs": {
                "query": query,
                "template_id": template_id,
            },
            # 控制信息(固定)
            "control": {
                "iterations": 0,  # 当前迭代次数
                "max_iterations": 20,  # 最大迭代(防止无限循环)
                "failed_steps": [],  # 失败步骤列表
            },
            # 其他字段将在规划阶段由LLM根据Agent定义动态添加
            # 例如: outline, document_ids, documents, extracted_content等
        }

        # 执行历史
        self._step_history: List[Dict[str, Any]] = []

    def _initialize_state_from_schema(self, state_schema: Dict[str, Any]):
        """根据LLM生成的state schema初始化状态字段"""
        for field_name, field_def in state_schema.items():
            if field_name in ["inputs", "control"]:
                # 跳过固定字段
                continue

            field_type = field_def.get("type", "dict")
            field_default = field_def.get("default")

            # 设置默认值
            if field_default is not None:
                self.state[field_name] = field_default
            elif field_type == "list":
                self.state[field_name] = []
            elif field_type == "dict":
                self.state[field_name] = {}
            elif field_type == "string":
                self.state[field_name] = ""
            elif field_type == "number":
                self.state[field_name] = 0
            else:
                self.state[field_name] = None

        logger.info(f"📋 根据state schema初始化了{len(state_schema)}个字段")

    def get_state(self, path: str, default: Any = None) -> Any:
        """从state dict中读取值(支持点路径)"""
        keys = path.split(".")
        value = self.state
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def set_state(self, path: str, value: Any):
        """向state dict中写入值(支持点路径)"""
        keys = path.split(".")
        cur = self.state
        for k in keys[:-1]:
            if k not in cur or not isinstance(cur[k], dict):
                cur[k] = {}
            cur = cur[k]
        cur[keys[-1]] = value

    def add_step_to_history(self, step_record: Dict[str, Any]):
        """记录步骤执行历史"""
        self._step_history.append(step_record)

    def get_step_history(self) -> List[Dict[str, Any]]:
        """获取步骤历史"""
        return self._step_history

    def summarize_state(
        self,
        target_tool_name: Optional[str] = None,
        max_steps: int = 10,
        max_context_chars: int = 51_200,
    ) -> str:
        """
        生成压缩的状态摘要供LLM使用(完全采用V1的优秀压缩策略)

        对文档内容进行智能压缩,只保留元数据,避免传递大量文本。
        支持智能过滤:只保留与目标工具相关的历史步骤。

        Args:
            target_tool_name: 目标工具名称(用于过滤相关步骤)
            max_steps: 最多保留的历史步骤数(默认10个)
            max_context_chars: 最大上下文字符数(默认51_200)

        Returns:
            压缩后的状态描述(JSON字符串)
        """
        compressed = {
            "query": self.state["inputs"]["query"],
            "template_id": self.state["inputs"]["template_id"],
            "step_history": [],
        }

        # 1. 智能过滤历史步骤
        relevant_steps = self._step_history

        # 如果指定了目标工具,优先保留相关的步骤
        if target_tool_name:
            # 定义工具依赖关系(哪些工具的结果可能被当前工具使用)
            tool_dependencies = {
                "analyze_input": [],  # 分析用户输入,不依赖其他工具
                "multi_query_search": ["generate_outline", "analyze_input"],
                "get_document_contents": [
                    "multi_query_search",
                    "es_fulltext_search",
                    "search_documents_by_classification",
                ],
                "skim_documents": ["multi_query_search", "es_fulltext_search"],
                "read_documents": ["multi_query_search", "es_fulltext_search"],
                "analyze_documents": [
                    "get_document_contents",
                    "skim_documents",
                    "read_documents",
                ],
                "document_extraction": ["multi_query_search", "generate_outline"],
                "document_compose": ["document_extraction", "generate_outline"],
                "document_review": ["document_compose"],
                "es_fulltext_search": ["analyze_input"],  # 可以基于分析结果检索
                "generate_outline": ["analyze_input"],  # 可以基于分析结果生成大纲
            }

            # 找到相关的工具名称
            related_tools = tool_dependencies.get(target_tool_name, [])

            # 优先保留相关步骤,然后保留最近的步骤
            relevant_steps = sorted(
                self._step_history,
                key=lambda s: (
                    s.get("name") in related_tools,  # 相关工具优先
                    s.get("step", 0),  # 然后按步骤号倒序(最近的在前)
                ),
                reverse=True,
            )[:max_steps]

        # 只保留最近的N个步骤
        relevant_steps = (
            relevant_steps[-max_steps:]
            if len(relevant_steps) > max_steps
            else relevant_steps
        )

        # 2. 压缩每一步的结果
        for step in relevant_steps:
            compressed_step = {
                "step": step.get("step"),
                "name": step.get("name"),
                "description": step.get("description", ""),
                "success": step.get("result", {}).get("success"),
            }

            # 获取工具的压缩函数
            tool_name = step.get("name", "")
            compress_func = get_tool_compress_function(tool_name)
            result = step.get("result", {})

            if compress_func is not None:
                # 使用工具自定义的压缩函数
                try:
                    compressed_result = compress_func(result, self)
                    if compressed_result is None:
                        # 返回 None 表示不压缩,保留完整结果
                        compressed_step["result"] = result
                    else:
                        compressed_step["result"] = compressed_result
                except Exception as e:
                    logger.warning(f"压缩函数执行失败 {tool_name}: {e}, 使用默认压缩")
                    compressed_step["result"] = self._default_compress_result(
                        result)
            else:
                # 使用默认压缩策略
                compressed_step["result"] = self._default_compress_result(
                    result)

            compressed["step_history"].append(compressed_step)

        # 3. 添加当前可用的中间数据摘要(更简洁)
        available_data = {}
        for key, value in self.state.items():
            if key in ["inputs", "control", "last_failure"]:
                continue  # 跳过内部字段

            if key == "documents" and isinstance(value, list):
                available_data["documents"] = f"{len(value)} docs available"
            elif key == "document_ids" and isinstance(value, list):
                available_data["document_ids"] = (
                    f"{len(value)} IDs: {value[:5]}..." if len(
                        value) > 5 else value
                )
            elif key == "outline":
                if isinstance(value, dict):
                    sections_count = len(value.get("sections", []))
                    available_data["outline"] = f"outline with {sections_count} sections"
                elif isinstance(value, list):
                    available_data["outline"] = f"outline with {len(value)} sections"
            elif key == "quality" and isinstance(value, dict):
                available_data["quality"] = value  # 质量指标完整保留
            elif key in ["composed_document", "reviewed_document"] and isinstance(value, dict):
                # 文档字段: 只显示元信息,完整内容通过字段引用获取
                available_data[key] = {
                    "title": value.get("title", "")[:50],
                    "word_count": value.get("word_count", 0),
                    "_ref": key,  # 标记为可引用字段
                }
            elif key == "extracted_content" and isinstance(value, dict):
                chapter_count = len(
                    [k for k in value.keys() if k not in ["summary"]])
                available_data[key] = f"{chapter_count} chapters"
            elif isinstance(value, (list, dict)):
                available_data[key] = f"{type(value).__name__}({len(str(value))} chars)"
            else:
                available_data[key] = value

        compressed["available_data"] = available_data

        # 4. 转换为JSON并检查长度
        result_json = json.dumps(compressed, ensure_ascii=False, indent=1)

        # 如果超过限制,进一步压缩
        if len(result_json) > max_context_chars:
            # 移除更多细节 - 只保留最后3个步骤
            compressed["step_history"] = compressed["step_history"][-3:]
            result_json = json.dumps(compressed, ensure_ascii=False, indent=1)

            # 如果还是太长,使用单行格式
            if len(result_json) > max_context_chars:
                result_json = json.dumps(
                    compressed, ensure_ascii=False, separators=(",", ":")
                )

        return result_json

    def _default_compress_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        默认结果压缩策略

        当工具没有定义 compress_function 时使用此策略

        Args:
            result: 工具执行结果

        Returns:
            压缩后的结果
        """
        compressed_result = {}

        for key, value in result.items():
            # 文档内容特殊处理 - 只保留元数据
            if key == "documents" and isinstance(value, list):
                compressed_result["documents"] = [
                    {
                        "id": doc.get("id") or doc.get("document_id"),
                        "title": doc.get("title", "")[:50],
                        "content_length": len(doc.get("content", "")),
                    }
                    for doc in value[:5]
                ]
                if len(value) > 5:
                    compressed_result["documents_count"] = len(value)

            # 文档ID列表 - 只保留前20个
            elif key == "document_ids" and isinstance(value, list):
                compressed_result["document_ids"] = value[:20]
                if len(value) > 20:
                    compressed_result["document_ids_count"] = len(value)

            # 大纲结构 - 压缩处理
            elif key == "outline":
                if isinstance(value, dict):
                    compressed_outline = {
                        "title": value.get("title", "")[:100],
                        "sections_count": len(value.get("sections", [])),
                    }
                    sections = value.get("sections", [])[:3]
                    compressed_outline["sections"] = [
                        {"title": s.get("title", "")[:50]}
                        for s in sections
                    ]
                    compressed_result["outline"] = compressed_outline
                elif isinstance(value, list):
                    compressed_result["outline"] = f"{len(value)} sections"
                else:
                    compressed_result["outline"] = value

            # 文档内容 - 只保留引用
            elif key == "document" and isinstance(value, dict):
                compressed_result["document"] = {
                    "title": value.get("title", "")[:50],
                    "word_count": value.get("word_count", 0),
                }

            # 错误信息
            elif key == "error":
                compressed_result["error"] = str(value)[:200]

            # 其他小型数据
            elif not isinstance(value, (list, dict)) or len(str(value)) < 300:
                compressed_result[key] = value
            # 大型数据只保留摘要
            else:
                compressed_result[f"{key}_summary"] = (
                    f"<{type(value).__name__}, {len(str(value))} chars>"
                )

        return compressed_result

    def update_quality_from_result(self, step_name: str, result: Dict[str, Any]):
        """根据工具执行结果更新质量指标"""
        if not result.get("success"):
            return

        # 如果state schema中没有quality字段,则跳过
        if "quality" not in self.state:
            return

        quality = self.state["quality"]

        # 根据工具类型更新质量指标
        if step_name == "generate_outline":
            outline = result.get("outline", {})
            if isinstance(outline, dict):
                sections = outline.get("sections", [])
                quality["sections_count"] = len(sections)
            elif isinstance(outline, list):
                quality["sections_count"] = len(outline)

        elif step_name in ["multi_query_search", "es_fulltext_search", "search_documents_by_classification"]:
            doc_ids = result.get("document_ids", [])
            quality["retrieval_count"] = len(doc_ids)

        elif step_name == "document_extraction":
            summary = result.get("summary", {})
            quality["extraction_chunks"] = summary.get(
                "total_extracted_chunks", 0)

        elif step_name == "document_compose":
            doc = result.get("document", {})
            quality["compose_word_count"] = doc.get("word_count", 0)

        elif step_name == "document_review":
            review_summary = result.get("review_summary", {})
            quality["review_errors"] = review_summary.get("errors_found", 0)


class DynamicPlanner:
    """
    动态规划器 - 根据Agent定义和当前query,动态生成执行计划 + state schema

    核心思路:
    - 不使用DB中的静态steps
    - 根据Agent的goals、constraints、可用工具,让LLM规划步骤
    - 同时生成state schema定义各个工具需要的字段
    """

    @staticmethod
    async def plan_execution(
        agent_name: str,
        agent_description: str,
        agent_goals: List[str],
        agent_constraints: List[str],
        query: str,
        template_id: int,
        db: AsyncSession,
        initial_plan: Optional[List[Dict[str, Any]]] = None,  # 新增: 初始计划(含固定步骤)
    ) -> Dict[str, Any]:
        """
        使用LLM动态规划执行步骤 + 生成state schema

        ⭐ 新增: 支持固定步骤
        - 如果 initial_plan 中有 is_pinned=True 的步骤,这些步骤必须保留
        - LLM 只能在固定步骤基础上补充必要的辅助步骤

        Returns:
            {
                "steps": [...],         # 规划的步骤列表
                "state_schema": {...},  # 状态字段定义
                "errors": [...],        # 规划过程中发现的错误
                "warnings": [...]       # 警告信息
            }
        """
        from core.tools.tool_registry import get_tool_metadata
        from core.tools.base import get_all_tools

        # 0. 提取固定步骤(is_pinned=True)
        pinned_steps = []
        if initial_plan:
            for step in initial_plan:
                if step.get("is_pinned", False):
                    pinned_steps.append(step)

        # 如果全部都是固定步骤,直接返回,不需要LLM规划
        if pinned_steps and initial_plan and len(pinned_steps) == len(initial_plan):
            logger.info(f"📌 全部为固定步骤({len(pinned_steps)}个),跳过LLM规划")
            return {
                "steps": initial_plan,
                "state_schema": {},  # 固定步骤不需要额外schema
                "errors": [],
                "warnings": [],
            }

        # 1. 获取可用工具列表(包含output_fields信息)
        all_tools_dict = get_all_tools()  # 返回字典: {tool_name: tool_info}
        tools_summary = []
        for tool_name in all_tools_dict.keys():
            meta = get_tool_metadata(tool_name)
            if meta:
                tools_summary.append({
                    "name": tool_name,
                    "description": meta.get("description", ""),
                    "category": meta.get("category", "general"),
                    "output_fields": list(meta.get("output_schema", {}).keys()) if meta.get("output_schema") else [],
                })

        # 2. 构造规划prompt(包含state schema生成要求)
        # ⭐ 如果有固定步骤,需要在prompt中告知LLM
        pinned_steps_info = ""
        if pinned_steps:
            pinned_steps_info = f"""

【⭐⭐⭐ 固定步骤(必须保留,不可修改) ⭐⭐⭐】
以下步骤是用户明确指定的固定步骤,你必须完整保留,不能修改、删除或重新排序:
{json.dumps(pinned_steps, ensure_ascii=False, indent=2)}

你的任务是:
1. 保留所有固定步骤(is_pinned=True)
2. 在固定步骤之间或之后,根据需要补充必要的辅助步骤
3. 确保最终计划完整可执行
4. 固定步骤的参数(pinned_parameters/parameter_template)不要修改
"""

        system_prompt = f"""你是一个专业的任务规划器。

【任务背景】
Agent名称: {agent_name}
Agent描述: {agent_description}

【Agent目标】
{chr(10).join(f"- {g}" for g in agent_goals) if agent_goals else "- 完成用户查询"}

【执行约束】
{chr(10).join(f"- {c}" for c in agent_constraints) if agent_constraints else "- 无特殊约束"}

【可用工具列表】
{json.dumps(tools_summary, ensure_ascii=False, indent=2)}
{pinned_steps_info}
【核心要求】
1. 根据用户查询和Agent目标,规划执行步骤
2. 同时设计state schema(状态字段结构)
3. 每个步骤必须指定:
   - step: 步骤序号(从1开始)
   - name: 工具名称(必须从可用工具列表中选择)
   - description: 这一步做什么
   - read_fields: 需要读取的state字段列表(如["documents", "outline"])
   - write_fields: 将写入的state字段列表(如["document_ids", "quality.retrieval_count"])
   - expectations: 自然语言描述的期望,如"检索到至少5个文档"
   - on_fail_strategy: 失败策略,如"重试最多3次"、"回退到步骤2"
   - is_pinned: 是否为固定步骤(固定步骤必须为true)
   - pinned_parameters: 固定参数(固定步骤需保留原值)
   - parameter_template: 参数模板(固定步骤需保留原值)
   - template_variables: 模板变量说明(固定步骤需保留原值)
4. state schema设计:
   - 根据规划的步骤,汇总所有write_fields
   - 每个字段指定type(list/dict/string/number)和default默认值
   - 可包含quality子字段用于质量监控
5. 步骤要简洁但完整,避免冗余
6. 如果缺少关键工具,返回errors说明
7. ⭐ 固定步骤必须完整保留,包括其is_pinned/pinned_parameters/parameter_template/template_variables字段

【返回格式】
请返回JSON:
{{
    "steps": [
        {{
            "step": 1,
            "name": "tool_name",
            "description": "步骤描述",
            "read_fields": [],
            "write_fields": ["field1", "quality.metric1"],
            "expectations": "期望结果描述",
            "on_fail_strategy": "失败处理策略",
            "is_pinned": false,
            "pinned_parameters": null,
            "parameter_template": null,
            "template_variables": null
        }}
    ],
    "state_schema": {{
        "field1": {{ "type": "list", "default": [] }},
        "quality": {{
            "type": "dict",
            "default": {{
                "metric1": 0
            }}
        }}
    }},
    "errors": [],
    "warnings": []
}}
"""

        user_prompt = f"""用户查询: {query}
模板ID: {template_id}

请规划执行步骤并设计state schema。"""

        try:
            llm_client = get_llm_client()
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
                max_tokens=4096,
            )

            steps = response.get("steps", [])
            state_schema = response.get("state_schema", {})
            errors = response.get("errors", [])
            warnings = response.get("warnings", [])

            logger.info(
                f"🤖 LLM规划完成: {len(steps)}个步骤, {len(state_schema)}个状态字段, {len(errors)}个错误")

            return {
                "steps": steps,
                "state_schema": state_schema,
                "errors": errors,
                "warnings": warnings,
            }

        except Exception as e:
            logger.error(f"❌ LLM规划失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "steps": [],
                "state_schema": {},
                "errors": [f"规划失败: {str(e)}"],
                "warnings": [],
            }


class ExpectationEvaluator:
    """
    期望评估器 - 使用LLM判断执行结果是否满足自然语言描述的期望

    核心思路:
    - 不使用符号化的checkpoint
    - 用LLM理解"检索到至少5个文档"这类自然语言期望
    - 返回简单的通过/不通过判定
    """

    @staticmethod
    async def evaluate(
        expectations: str,
        step_result: Dict[str, Any],
        state: UnifiedExecutionState,
        db: AsyncSession,
        step_name: Optional[str] = None,
        mode: Optional[str] = None,  # 外部传入的模式: none/loose/strict
    ) -> tuple[bool, str]:
        """
                评估步骤执行结果是否满足期望

        验证逻辑:
        1. 如果工具没有定义 validate_function,直接通过(只检查success)
        2. 如果有 validate_function,调用它并传入 ValidationMode 枚举、llm_client、db

        Args:
            expectations: 自然语言描述的期望
            step_result: 步骤执行结果
            state: 当前执行状态
            db: 数据库会话
            step_name: 工具名称
            mode: 验证模式(none/loose/strict),默认none

        Returns:
            (passed, reason): 是否通过和原因
        """
        from core.tools.base import ValidationMode, get_tool

        # 获取工具信息
        validate_function = None
        if step_name:
            tool_info = get_tool(step_name)
            if tool_info:
                validate_function = tool_info.get("validate_function")

        # 解析模式
        validation_mode = ValidationMode.NONE
        if mode:
            mode_lower = mode.lower()
            if mode_lower == "strict":
                validation_mode = ValidationMode.STRICT
            elif mode_lower == "loose":
                validation_mode = ValidationMode.LOOSE

        # 如果没有定义 validate_function,直接通过(只检查success)
        if validate_function is None:
            success = step_result.get("success", False)
            if success:
                logger.info(f"👎🏻 跳过验证[{step_name}]: 未定义validate_function")
                return True, "无需验证,执行成功即通过"
            else:
                error = step_result.get("error", "执行失败")
                return False, f"执行失败: {error}"

        # 调用自定义验证函数,传入 ValidationMode 枚举、llm_client、db
        try:
            # 获取 llm_client
            llm_client = get_llm_client()

            # 检查函数是否是异步的
            if asyncio.iscoroutinefunction(validate_function):
                result = await validate_function(
                    step_result, expectations, state, validation_mode, llm_client, db
                )
            else:
                result = validate_function(
                    step_result, expectations, state, validation_mode, llm_client, db
                )

            if isinstance(result, tuple) and len(result) == 2:
                passed, reason = result
                mode_name = validation_mode.value
                icon = "👍🏻" if passed else "👎🏻"
                logger.info(f"{icon} 验证[{step_name}][{mode_name}]: {reason}")
                return passed, reason
            else:
                logger.warning(
                    f"validate_function返回格式错误,期望(bool, str),实际: {result}")
                return step_result.get("success", False), "验证函数返回格式错误"
        except Exception as e:
            logger.error(f"👎🏻 validate_function执行失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 失败时回退到只检查success
            return step_result.get("success", False), f"验证异常: {str(e)}"


class CustomAgentExecutorV2:
    """
    自定义Agent执行器 V2

    核心改进:
    1. 执行时动态规划步骤(而非使用DB中的静态steps)
    2. 基于统一state dict管理数据
    3. 自然语言期望判定(而非符号化checkpoint)
    4. 明确回退策略表
    """

    @staticmethod
    async def execute(
        agent,  # CustomAgent数据库模型实例
        query: str,
        template_id: int,
        session_id: Optional[str],
        db: AsyncSession,
        es_client,
        es_index: str = "dochive_documents",
        user_id: Optional[int] = None,  # 新增: 用户ID
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行自定义Agent

        核心流程:
        1. 动态规划: 使用LLM根据Agent定义和query规划步骤
        2. 逐步执行: 执行每个步骤,更新state dict
        3. 期望判定: 使用LLM判断结果是否满足自然语言期望
        4. 智能回退: 失败时根据回退策略表决定下一步
        """
        logger.info(f"🚀 开始执行Agent V2: {agent.name}")

        # 创建执行记录
        from services.execution_record_service import ExecutionRecordService

        execution_record = await ExecutionRecordService.create_record(
            db=db,
            agent_id=agent.id,
            agent_name=agent.name,
            query=query,
            template_id=template_id,
            execution_pattern=agent.execution_pattern or "hybrid",
            session_id=session_id or "",
            user_id=user_id,
        )
        record_id = execution_record.id
        logger.info(f"📝 创建执行记录 ID={record_id}")

        # ⭐ 检查是否有固定步骤
        initial_plan = agent.initial_plan or []
        pinned_count = sum(
            1 for s in initial_plan if s.get("is_pinned", False))
        if pinned_count > 0:
            logger.info(f"📌 发现 {pinned_count} 个固定步骤,将优先使用")

        # 1. 动态规划阶段
        yield {
            "event": "planning",
            "data": {
                "message": "正在规划执行步骤...",
            },
        }

        plan_result = await DynamicPlanner.plan_execution(
            agent_name=agent.name,
            agent_description=agent.description,
            agent_goals=agent.goals or [],
            agent_constraints=agent.constraints or [],
            query=query,
            template_id=template_id,
            db=db,
            initial_plan=initial_plan,  # ⭐ 传入固定步骤
        )

        if plan_result["errors"]:
            yield {
                "event": "error",
                "data": {
                    "message": "规划失败",
                    "errors": plan_result["errors"],
                },
            }
            return

        steps = plan_result["steps"]
        state_schema = plan_result.get("state_schema", {})

        # 发送执行计划
        yield {
            "event": "execution_plan",
            "data": {
                "agent_name": agent.name,
                "description": agent.description,
                "steps": steps,
                "state_schema": state_schema,
                "warnings": plan_result.get("warnings", []),
            },
        }

        # 2. 初始化执行状态(使用动态生成的state schema)
        state = UnifiedExecutionState(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            session_id=session_id,
            query=query,
            agent_goals=agent.goals,
            agent_constraints=agent.constraints,
            rollback_plan=agent.rollback_plan or {},
        )

        # 根据state_schema初始化动态字段
        if state_schema:
            state._initialize_state_from_schema(state_schema)

        # 3. 执行步骤(支持跳转和回退)
        from core.tools.base import execute_tool

        current_step_index = 0
        max_iterations = state.state["control"]["max_iterations"]

        while current_step_index < len(steps) and state.state["control"]["iterations"] < max_iterations:
            state.state["control"]["iterations"] += 1
            step = steps[current_step_index]
            step_num = step.get("step", current_step_index + 1)
            step_name = step.get("name")
            step_desc = step.get("description", "")
            expectations = step.get("expectations")
            on_fail_strategy = step.get("on_fail_strategy")

            logger.info(f"🔧 执行步骤{step_num}: {step_name}")

            # 发送步骤开始事件
            yield {
                "event": "stage_start",
                "data": {
                    "stage": f"step_{step_num}",
                    "step": step_num,
                    "name": step_name,
                    "description": step_desc,
                    "message": f"正在执行: {step_desc}",
                    "status": "running",
                },
            }

            try:
                # 执行工具 - 返回参数和LLM调用信息
                build_result = await CustomAgentExecutorV2._build_tool_arguments(
                    step=step,
                    state=state,
                    db=db,
                )

                # 解构返回值
                if isinstance(build_result, dict) and "arguments" in build_result:
                    arguments = build_result["arguments"]
                    llm_calls = build_result.get("llm_calls", [])
                else:
                    # 兼容旧版返回格式
                    arguments = build_result
                    llm_calls = []

                result = await execute_tool(
                    step_name,
                    arguments,
                    state.to_tool_context(),
                )

                # 更新state dict
                CustomAgentExecutorV2._update_state_from_result(
                    step_name=step_name,
                    result=result,
                    state=state,
                )

                # 更新质量指标
                state.update_quality_from_result(step_name, result)

                # 记录历史 - 包含LLM调用信息
                state.add_step_to_history({
                    "step": step_num,
                    "name": step_name,
                    "description": step_desc,
                    "arguments": arguments,  # 记录参数
                    "result": result,
                    "llm_calls": llm_calls,  # 记录LLM调用
                })

                # 评估期望
                evaluation_reason = None  # 记录评估结果
                if expectations and result.get("success"):
                    passed, evaluation_reason = await ExpectationEvaluator.evaluate(
                        expectations=expectations,
                        step_result=result,
                        state=state,
                        db=db,
                        step_name=step_name,  # 传递工具名称
                    )

                    if not passed:
                        # 期望未满足,触发失败处理
                        logger.warning(f"⚠️ 步骤{step_num}期望未满足: {expectations}")
                        logger.warning(f"原因: {evaluation_reason}")
                        result["success"] = False
                        result["expectation_failed"] = True
                        result["evaluation_reason"] = evaluation_reason  # 保存失败原因

                        # 将失败原因记录到state中,供重试时参考
                        if "last_failure" not in state.state:
                            state.state["last_failure"] = {}
                        state.state["last_failure"][step_name] = {
                            "reason": evaluation_reason,
                            "expectations": expectations,
                            "step": step_num,
                        }

                # 发送步骤完成事件
                yield {
                    "event": "stage_complete",
                    "data": {
                        "stage": f"step_{step_num}",
                        "step": step_num,
                        "name": step_name,
                        "description": step_desc,
                        "success": result.get("success", False),
                        "result": result,
                        "status": "completed" if result.get("success") else "failed",
                    },
                }

                # 如果成功,移动到下一步
                if result.get("success"):
                    current_step_index += 1
                else:
                    # 失败处理
                    state.state["control"]["failed_steps"].append({
                        "step": step_num,
                        "name": step_name,
                        "error": result.get("error", "执行失败"),
                    })

                    # 解析失败策略
                    if on_fail_strategy:
                        action = await CustomAgentExecutorV2._parse_fail_strategy(
                            strategy=on_fail_strategy,
                            step_name=step_name,
                            state=state,
                            db=db,
                        )

                        if action.get("type") == "retry":
                            # 重试:不移动指针
                            logger.info(f"↻ 重试步骤{step_num}")
                            yield {
                                "event": "stage_retry",
                                "data": {
                                    "step": step_num,
                                    "message": f"重试步骤{step_num}",
                                },
                            }
                            continue

                        elif action.get("type") == "goto":
                            # 跳转回退
                            target_step = action.get("target_step")
                            logger.info(f"↩️ 回退到步骤{target_step}")
                            # 找到目标步骤的索引
                            for i, s in enumerate(steps):
                                if s.get("step") == target_step:
                                    current_step_index = i
                                    break
                            yield {
                                "event": "stage_jump",
                                "data": {
                                    "from_step": step_num,
                                    "to_step": target_step,
                                    "message": f"从步骤{step_num}回退到步骤{target_step}",
                                },
                            }
                            continue

                        elif action.get("type") == "fallback":
                            # 使用默认值继续
                            logger.info(f"🔄 使用默认值继续")
                            yield {
                                "event": "stage_fallback",
                                "data": {
                                    "step": step_num,
                                    "message": "使用默认值继续执行",
                                },
                            }
                            current_step_index += 1
                            continue

                    # 没有明确策略,或策略解析失败,直接跳过
                    logger.warning(f"⚠️ 步骤{step_num}失败,跳过")
                    current_step_index += 1

            except Exception as e:
                logger.error(f"❌ 步骤{step_num}执行失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

                yield {
                    "event": "stage_error",
                    "data": {
                        "step": step_num,
                        "name": step_name,
                        "error": str(e),
                        "message": f"步骤{step_num}出错: {str(e)}",
                    },
                }

                # 异常情况,跳过该步骤
                current_step_index += 1

        # 4. 生成最终答案
        logger.info("📝 生成最终答案")

        final_document = state.state.get(
            "reviewed_document") or state.state.get("composed_document")
        documents = state.state.get("documents", [])

        yield {
            "event": "answer",
            "data": {
                "answer": "执行完成" if final_document or documents else "执行完成,但未生成结果",
                "document": final_document,
                "documents": documents,
            },
        }

        # 5. 生成执行报告
        from core.agents.execution_report import ExecutionReportGenerator

        final_result = {
            "composed_document": state.state.get("composed_document"),
            "reviewed_document": state.state.get("reviewed_document"),
            "documents": state.state.get("documents"),
        }

        # 生成结构化报告数据
        report_data = ExecutionReportGenerator.generate_report_data(
            agent_name=agent.name,
            query=query,
            steps=steps,
            step_history=state.get_step_history(),
            final_result=final_result,
        )

        # 生成 HTML 报告
        html_report = ExecutionReportGenerator.generate_html_report(
            agent_name=agent.name,
            query=query,
            steps=steps,
            step_history=state.get_step_history(),
            final_result=final_result,
        )

        # 生成 Markdown 报告
        markdown_report = ExecutionReportGenerator.generate_markdown_report(
            agent_name=agent.name,
            query=query,
            steps=steps,
            step_history=state.get_step_history(),
            final_result=final_result,
        )

        yield {
            "event": "execution_report",
            "data": {
                "report": report_data,
                "html": html_report,
                "markdown": markdown_report,
            },
        }

        # 6. 保存执行记录
        try:
            await ExecutionRecordService.complete_record(
                db=db,
                record_id=record_id,
                execution_plan=steps,
                step_history=state.get_step_history(),
                final_result=final_result,
                report_data=report_data,
                html_report=html_report,
                markdown_report=markdown_report,
                status="completed",
            )
            logger.info(f"✅ 执行记录已保存 ID={record_id}")
        except Exception as e:
            logger.error(f"⚠️ 保存执行记录失败: {e}")

        # 7. 完成
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
                "iterations": state.state["control"]["iterations"],
                "record_id": record_id,  # 新增: 返回记录ID
            },
        }

        logger.info(f"✅ Agent V2执行完成: {agent.name}")

    @staticmethod
    async def _build_tool_arguments(
        step: Dict[str, Any],
        state: UnifiedExecutionState,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        构造工具参数

        返回格式:
        {
            "arguments": {...},  # 工具参数
            "llm_calls": [...]  # LLM调用记录
        }

        核心逻辑(用户定义优先):
        1. ⭐ 完全固定(is_pinned=True, pinned_parameters存在): 直接使用,跳过LLM
        2. ⭐ 模板化固定(is_pinned=True, parameter_template存在): LLM推断变量值并填充模板
        3. 使用step中已定义的parameters
        4. 使用LLM根据【步骤目标】构造参数

        重要: 用户定义的参数优先级最高,不会被LLM覆盖
        """
        step_name = step.get("name")
        step_description = step.get("description", "")  # 步骤的具体目标
        step_expectations = step.get("expectations", "")  # 期望结果
        predefined_params = step.get("parameters", {}) or {}

        is_pinned = step.get("is_pinned", False)
        pinned_parameters = step.get("pinned_parameters")
        parameter_template = step.get("parameter_template")
        template_variables = step.get("template_variables", {}) or {}

        # LLM调用记录列表
        llm_calls = []

        # ⭐ 模式1: 完全固定参数 - 直接使用,跳过LLM
        if is_pinned and pinned_parameters:
            logger.info(f"📌 完全固定步骤 [{step_name}]: 直接使用用户指定参数")
            final_params = dict(pinned_parameters)
            # 补充必需但未指定的参数(template_id)
            if "template_id" not in final_params and state.template_id:
                final_params["template_id"] = state.template_id
            # 从 state 补充工具所需的中间数据
            final_args = CustomAgentExecutorV2._supplement_params_from_state(
                step_name, final_params, state)
            return {"arguments": final_args, "llm_calls": llm_calls}

        # ⭐ 模式2: 模板化固定参数 - LLM推断变量值并填充模板
        if is_pinned and parameter_template:
            logger.info(f"📋 模板化固定步骤 [{step_name}]: LLM推断变量值并填充模板")

            variables_desc = "\n".join(
                f"- {k}: {v}" for k, v in template_variables.items())

            llm_client = get_llm_client()
            system_prompt = f"""你是参数推断助手。用户有一个固定的参数模板,你需要根据用户输入推断模板变量的值。

【参数模板】
```json
{json.dumps(parameter_template, ensure_ascii=False, indent=2)}
```

【模板变量说明】
{variables_desc}

【用户输入】
{state.state["inputs"]["query"]}

【任务】
分析用户输入,推断每个模板变量($开头)应该填充的值。

【返回格式】
返回JSON,包含每个变量的推断值:
```json
{{
  "$TOPIC": "推断出的值"
}}
```

【规则】
1. 仔细分析用户输入,提取与变量说明匹配的信息
2. 如果用户输入中没有明确提及,根据上下文合理推断
3. 返回的值应该可以直接替换到模板中
4. 只返回JSON,不要其他文字
"""

            try:
                user_prompt_template = f"请根据用户输入推断变量值"
                response = await llm_client.extract_json_response(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt_template},
                    ],
                    db=db,
                    max_tokens=1024,
                )

                # 记录LLM调用
                llm_calls.append({
                    "purpose": "模板变量推断",
                    "input": {
                        "system_prompt": system_prompt[:500] + "..." if len(system_prompt) > 500 else system_prompt,
                        "user_prompt": user_prompt_template,
                    },
                    "output": response,
                })

                logger.info(f"🔮 LLM推断变量值: {response}")

                # 将变量值填充到模板中
                template_str = json.dumps(
                    parameter_template, ensure_ascii=False)
                for var_name, var_value in response.items():
                    if var_name.startswith("$"):
                        template_str = template_str.replace(
                            var_name, str(var_value))

                final_params = json.loads(template_str)

                # 补充必需参数
                if "template_id" not in final_params and state.template_id:
                    final_params["template_id"] = state.template_id

                logger.info(
                    f"📋 填充后的参数: {json.dumps(final_params, ensure_ascii=False, default=str)[:500]}")
                final_args = CustomAgentExecutorV2._supplement_params_from_state(
                    step_name, final_params, state)
                return {"arguments": final_args, "llm_calls": llm_calls}

            except Exception as e:
                logger.error(f"❌ 模板变量推断失败: {e}")
                # Fallback: 直接使用模板(变量未替换)
                return {"arguments": dict(parameter_template), "llm_calls": llm_calls}

        # ⭐ 模式3: 用户预定义参数 - 直接使用
        if predefined_params:
            logger.info(f"📝 使用用户预定义参数: {list(predefined_params.keys())}")
            final_params = dict(predefined_params)
            if "template_id" not in final_params and state.template_id:
                final_params["template_id"] = state.template_id
            final_args = CustomAgentExecutorV2._supplement_params_from_state(
                step_name, final_params, state)
            return {"arguments": final_args, "llm_calls": llm_calls}

        # ⭐ 模式4: LLM智能推断参数
        from core.tools.tool_registry import get_tool_metadata

        tool_meta = get_tool_metadata(step_name)
        if not tool_meta:
            return {"arguments": {"template_id": state.template_id}, "llm_calls": llm_calls}

        param_schema = tool_meta.get("parameters", {})

        # 检查是否有上次失败记录
        last_failure = state.state.get("last_failure", {}).get(step_name)
        failure_context = ""
        if last_failure:
            failure_context = f"""

【上次失败原因】
期望: {last_failure.get('expectations', '')}
失败原因: {last_failure.get('reason', '')}

⚠️ 请根据上次失败原因调整参数,确保满足期望！
"""

        # 获取Agent的总体目标
        agent_goals = state.agent_goals or []
        agent_goals_text = "\n".join(
            f"- {g}" for g in agent_goals) if agent_goals else "完成用户请求"

        system_prompt = f"""你是参数构造助手。你需要根据【当前步骤的目标】来构造工具参数。

【重要理解】
- Agent总体目标: 这是整个智能体要完成的任务
- 当前步骤目标: 这是本步骤具体要做的事情
- 用户原始输入: 这是用户提供的原始信息,作为背景参考

⚠️ 核心原则: 工具参数(尤其是query)应该反映【当前步骤的目标】,而不是简单复制用户原始输入!

【Agent总体目标】
{agent_goals_text}

【当前步骤信息】
- 工具名称: {step_name}
- 步骤目标: {step_description}
- 期望结果: {step_expectations}

【用户原始输入(背景参考)】
{state.state["inputs"]["query"]}

【工具参数定义】
{json.dumps(param_schema, ensure_ascii=False, indent=2)}

【当前执行状态】
{state.summarize_state(target_tool_name=step_name)}
{failure_context}
【任务】
根据【当前步骤目标】和【执行状态】,生成工具参数(纯JSON)。

【规则 - 重要！】
1. **query参数构造**: 
   - 如果工具需要query参数,应该根据【步骤目标】来构造
   - 例如: 步骤目标是"生成案件备忘录大纲",则query应该是"生成一份关于XXX的案件备忘录大纲"
   - 不要简单地把用户原始输入作为query!
2. **必须使用状态中的template_id**: 直接从当前状态中提取template_id,不要自己编造！
3. 从状态中提取其他数据(如document_ids、outline等)
4. **文档字段特殊处理**: 如果状态中有composed_document或reviewed_document的摘要信息,引用该字段名
5. 只包含参数定义中的字段
6. 返回纯JSON,无其他文字
7. 如果有上次失败记录,请特别注意调整参数以满足期望

【示例】
场景: 用户输入是一段举报内容,Agent目标是生成案件备忘录,当前步骤是生成大纲
- 用户原始输入: "张三于2024年1月被某平台骗取资金..."
- 步骤目标: "根据举报内容生成案件备忘录大纲"
- 正确的query: "请根据张三被某平台骗取资金的举报内容,生成一份案件备忘录大纲"
- 错误的query: "张三于2024年1月被某平台骗取资金..." (这是错误的!不应直接复制原始输入)
"""

        # 这个参数用来固定一些工具的输出，尤其是es全文检索，如果不固定很容易出事情
        # 切记！！！
        _extra_ = """     
【特定规则】
- 如果当前工具名为 es_fulltext_search,或者multi_query_search，那么在构建参数的时候，需要遵循以下规则：
```markdown
【提取规则】
1. primary_keywords（核心关键词）
   - 必须是实体、事件、主题、专有名词、可被检索的对象
     例如：公车私用、住房公积金、商业贿赂、供应链金融、心脏支架、ChatGPT
   - 不能是提问结构词，如：
     如何、为什么、是否、会不会、可以吗、怎么办
   - 不能是泛化词，如：
     法律法规、政策、规定、办法、问题、影响、处理方式、后果
   - 不能是动作辅助词：
     触犯、涉及、属于、构成、导致、存在
   - **数量控制**
     1. 如果查询是简单句或单个问题：限制 1-2 个核心关键词
     2. 如果查询是复杂句或多问题：可以适当增加，但一般不超过 5 个

2. context_keywords（上下文扩展词）
   - 描述核心词的领域、属性、范围、场景
     例如：法律责任、财务审计、交通安全、职务行为、医疗器械
   - 可以包含抽象词，但不能替代核心词

3. related_keywords（相关词）
   - 与核心词可能相关的补充检索词或同义词
   - 可包括：常见别名、对应领域、技术名词、常见问题
```"""

        logger.info(f"🚀 为工具 {step_name} 生成参数。")

        user_prompt = f"为工具 {step_name} 生成参数。当前步骤目标: {step_description}\n {_extra_}"

        try:
            llm_client = get_llm_client()
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
                max_tokens=4096,
            )

            # 记录LLM调用
            llm_calls.append({
                "purpose": "参数构造",
                "input": {
                    "system_prompt_brief": system_prompt[:800] + "..." if len(system_prompt) > 800 else system_prompt,
                    "user_prompt": user_prompt[:500] + "..." if len(user_prompt) > 500 else user_prompt,
                },
                "output": response,
            })

            logger.info(f"🤖 LLM生成参数: {response}")

            # 处理字段引用: 如果参数值是字段名,从state中获取实际值
            resolved_response = {}
            for key, value in response.items():
                if isinstance(value, str) and value in state.state:
                    # 这是一个字段引用,替换为实际值
                    resolved_response[key] = state.state[value]
                    logger.info(f"🔗 解析字段引用: {key}={value} -> 从state获取实际值")
                else:
                    resolved_response[key] = value

            return {"arguments": resolved_response, "llm_calls": llm_calls}

        except Exception as e:
            logger.error(f"❌ LLM生成参数失败: {e},使用fallback")
            # fallback: 根据工具类型提供合理的默认参数
            fallback_params = {"template_id": state.template_id}

            # 根据步骤目标构造query，而不是简单使用用户原始输入
            user_input = state.state["inputs"]["query"]
            # 简化用户输入，取前50个字符作为概要
            user_input_brief = user_input[:50] + \
                "..." if len(user_input) > 50 else user_input
            # 使用步骤目标构造query
            goal_based_query = f"{step_description}：基于用户输入'{user_input_brief}'"

            # 根据工具类型添加必需参数
            if step_name == "analyze_input":
                # 分析用户输入: 将原始输入作为待分析的文本（这是合理的，因为分析的就是原始输入）
                fallback_params.update({
                    "input_text": user_input,
                })
            elif step_name == "document_compose":
                fallback_params.update({
                    "query": goal_based_query,
                    "outline": state.state.get("outline", {}),
                    "extracted_content": state.state.get("extracted_content", {}),
                })
            elif step_name == "document_extraction":
                fallback_params.update({
                    "query": goal_based_query,
                    "outline": state.state.get("outline", {}),
                    "document_ids": state.state.get("document_ids", []),
                })
            elif step_name == "document_review":
                fallback_params.update({
                    "query": goal_based_query,
                    "document": state.state.get("composed_document", {}),
                })
            elif step_name == "generate_outline":
                # 生成大纲：使用步骤目标构造query
                fallback_params.update({
                    "query": goal_based_query,
                })
            elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                fallback_params.update({
                    "document_ids": state.state.get("document_ids", []),
                })
            elif step_name in ["multi_query_search", "es_fulltext_search"]:
                # 检索工具：使用步骤目标构造检索query
                fallback_params.update({
                    "query": goal_based_query,
                })

            logger.info(
                f"🔧 Fallback参数: {json.dumps(fallback_params, ensure_ascii=False, default=str)[:200]}...")
            return {"arguments": fallback_params, "llm_calls": llm_calls}

    @staticmethod
    def _supplement_params_from_state(
        step_name: str,
        params: Dict[str, Any],
        state: "UnifiedExecutionState"
    ) -> Dict[str, Any]:
        """
        从state中补充工具所需但用户未指定的参数

        重要: 用户已指定的参数不会被覆盖
        """
        # document_extraction 需要 outline 和 documents
        if step_name == "document_extraction":
            if "outline" not in params:
                params["outline"] = state.state.get("outline", {})
            if "documents" not in params:
                params["documents"] = state.state.get("documents", [])

        # document_compose 需要 outline 和 extracted_content
        elif step_name == "document_compose":
            if "outline" not in params:
                params["outline"] = state.state.get("outline", {})
            if "extracted_content" not in params:
                params["extracted_content"] = state.state.get(
                    "extracted_content", {})

        # document_review 需要 document
        elif step_name == "document_review":
            if "document" not in params:
                params["document"] = state.state.get("composed_document", {})

        # 文档读取工具需要 document_ids
        elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
            if "document_ids" not in params:
                params["document_ids"] = state.state.get("document_ids", [])

        return params

    @staticmethod
    def _update_state_from_result(
        step_name: str,
        result: Dict[str, Any],
        state: UnifiedExecutionState,
    ):
        """根据工具执行结果更新state dict"""
        if not result.get("success"):
            return

        # 根据工具类型更新对应字段
        if step_name == "analyze_input":
            # 分析用户输入的结果
            case_summary = result.get("case_summary", "")
            case_type = result.get("case_type", [])
            key_info = result.get("key_info", {})
            analysis_result = result.get("analysis_result", {})

            state.set_state("case_summary", case_summary)
            state.set_state("case_type", case_type)
            state.set_state("key_info", key_info)
            state.set_state("analysis_result", analysis_result)

        elif step_name == "generate_outline":
            outline = result.get("outline", {})
            state.set_state("outline", outline)

        elif step_name in ["multi_query_search", "es_fulltext_search", "search_documents_by_classification"]:
            doc_ids = result.get("document_ids", [])
            state.set_state("document_ids", doc_ids)
            if result.get("documents"):
                state.set_state("documents", result.get("documents", []))

        elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
            docs = result.get("documents", [])
            state.set_state("documents", docs)

        elif step_name == "document_extraction":
            content = result.get("extracted_content", {})
            state.set_state("extracted_content", content)

        elif step_name == "document_compose":
            doc = result.get("document", {})
            state.set_state("composed_document", doc)

        elif step_name == "document_review":
            doc = result.get("reviewed_document", {})
            state.set_state("reviewed_document", doc)

        elif step_name == "analyze_documents":
            analysis = result.get("analysis", {})
            state.set_state("analysis_result", analysis)

    @staticmethod
    async def _parse_fail_strategy(
        strategy: str,
        step_name: str,
        state: UnifiedExecutionState,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        解析失败策略(自然语言 -> 结构化动作)

        Returns:
            {
                "type": "retry" | "goto" | "fallback" | "abort",
                "target_step": int,  # 仅当type=goto时
            }
        """
        system_prompt = """你是失败策略解析专家。

【任务】
将自然语言描述的失败处理策略转换为结构化指令。

【策略类型】
1. retry: 重试当前步骤(如"重试最多3次"、"再试一次")
2. goto: 跳转到指定步骤(如"回退到步骤2"、"返回步骤1重新检索")
3. fallback: 使用默认值继续(如"使用空大纲继续"、"跳过该步骤")
4. abort: 终止执行(如"停止执行"、"中止流程")

【返回格式】
JSON:
{
    "type": "retry" | "goto" | "fallback" | "abort",
    "target_step": 步骤号(仅当type=goto时)
}
"""

        user_prompt = f"""策略描述: {strategy}
当前步骤: {step_name}

请解析策略。"""

        try:
            llm_client = get_llm_client()
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
                max_tokens=4096,
            )

            return response

        except Exception as e:
            logger.error(f"❌ 策略解析失败: {e}")
            # fallback: 继续执行
            return {"type": "fallback"}
