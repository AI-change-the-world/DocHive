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
    ) -> Dict[str, Any]:
        """
        使用LLM动态规划执行步骤 + 生成state schema

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
4. state schema设计:
   - 根据规划的步骤,汇总所有write_fields
   - 每个字段指定type(list/dict/string/number)和default默认值
   - 可包含quality子字段用于质量监控
5. 步骤要简洁但完整,避免冗余
6. 如果缺少关键工具,返回errors说明

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
            "on_fail_strategy": "失败处理策略"
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
                # 执行工具
                arguments = await CustomAgentExecutorV2._build_tool_arguments(
                    step=step,
                    state=state,
                    db=db,
                )

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

                # 记录历史
                state.add_step_to_history({
                    "step": step_num,
                    "name": step_name,
                    "description": step_desc,
                    "result": result,
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

        # 5. 完成
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
                "iterations": state.state["control"]["iterations"],
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
        构造工具参数(使用LLM智能推断)

        优先使用step中已定义的parameters,
        如果没有则使用LLM从state中推断
        """
        step_name = step.get("name")
        predefined_params = step.get("parameters", {})

        if predefined_params:
            # 步骤中已定义参数,优先使用
            logger.debug(f"使用预定义参数: {predefined_params}")
            return predefined_params

        # 使用LLM推断参数
        from core.tools.tool_registry import get_tool_metadata

        tool_meta = get_tool_metadata(step_name)
        if not tool_meta:
            return {"template_id": state.template_id}

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

        system_prompt = f"""你是参数构造助手。

【工具】{step_name}
【参数定义】
{json.dumps(param_schema, ensure_ascii=False, indent=2)}

【当前状态】
{state.summarize_state(target_tool_name=step_name)}  # 传递target_tool_name实现智能过滤
{failure_context}
【任务】
根据当前状态,生成工具参数(纯JSON)。

【规则 - 重要！】
1. **必须使用状态中的template_id**: 直接从当前状态中提取template_id,不要自己编造！
2. 从状态中提取其他数据(如document_ids、outline等)
3. **文档字段特殊处理**: 如果状态中有composed_document或reviewed_document的摘要信息(如{{"title": "...", "word_count": 1000, "has_content": true}}),
   表示完整文档内容存在于state中但未显示,你应该:
   - 引用该字段名(如"composed_document")
   - 完整文档会自动从state中获取
4. 只包含参数定义中的字段
5. 返回纯JSON,无其他文字
6. 如果有上次失败记录,请特别注意调整参数以满足期望

示例:
如果状态中 template_id=1, query="某某问题",那么生成:
{{
  "query": "某某问题",
  "template_id": 1
}}

如果状态中有 composed_document: {{"title": "报告", "word_count": 5000, "has_content": true}}, 需要document参数时生成:
{{
  "document": "composed_document"  // 引用字段名,完整内容会自动获取
}}
"""

        user_prompt = f"为工具 {step_name} 生成参数。"

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

            return resolved_response

        except Exception as e:
            logger.error(f"❌ LLM生成参数失败: {e},使用fallback")
            # fallback: 根据工具类型提供合理的默认参数
            fallback_params = {"template_id": state.template_id}

            # 根据工具类型添加必需参数(直接从state原始数据中获取,不使用压缩后的摘要)
            if step_name == "analyze_input":
                # 分析用户输入: 将query作为待分析的文本
                fallback_params.update({
                    "input_text": state.state["inputs"]["query"],
                })
            elif step_name == "document_compose":
                fallback_params.update({
                    "query": state.state["inputs"]["query"],
                    "outline": state.state.get("outline", {}),
                    "extracted_content": state.state.get("extracted_content", {}),
                })
            elif step_name == "document_extraction":
                fallback_params.update({
                    "query": state.state["inputs"]["query"],
                    "outline": state.state.get("outline", {}),
                    "document_ids": state.state.get("document_ids", []),
                })
            elif step_name == "document_review":
                # 关键修复: 直接从state中获取完整的composed_document
                fallback_params.update({
                    "query": state.state["inputs"]["query"],
                    "document": state.state.get("composed_document", {}),
                })
            elif step_name == "generate_outline":
                fallback_params.update({
                    "query": state.state["inputs"]["query"],
                })
            elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                fallback_params.update({
                    "document_ids": state.state.get("document_ids", []),
                })
            elif step_name in ["multi_query_search", "es_fulltext_search"]:
                fallback_params.update({
                    "query": state.state["inputs"]["query"],
                })

            logger.info(
                f"🔧 Fallback参数: {json.dumps(fallback_params, ensure_ascii=False, default=str)[:200]}...")
            return fallback_params

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
