import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.context import ExecutionContext
from utils.llm_client import get_llm_client


class CustomExecutionState(ExecutionContext):
    """
    自定义Agent执行状态 - 继承自 ExecutionContext

    专门用于自定义Agent的执行，复用 ExecutionContext 的所有功能，
    同时提供执行历史管理功能。
    """

    def __init__(
        self,
        db: Any = None,
        es_client: Any = None,
        es_index: str = "dochive_documents",
        template_id: Optional[int] = None,
        session_id: Optional[str] = None,
        query: str = "",
        **extra,
    ):
        """
        初始化自定义执行状态

        Args:
            db: 数据库会话
            es_client: ES客户端
            es_index: ES索引
            template_id: 模板ID
            session_id: 会话ID
            query: 用户查询
            **extra: 其他额外参数
        """
        super().__init__(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            session_id=session_id,
            query=query,
            **extra,
        )

        # 初始化中间数据（方便快速访问）
        self.set_data("documents", [])
        self.set_data("document_ids", [])
        self.set_data("outline", {})

        # 执行历史（用于记录Agent执行过程中的所有步骤结果）
        self._step_results: List[Dict[str, Any]] = []  # 所有步骤的结果列表
        self._tool_results: List[Dict[str, Any]] = []  # 所有工具调用结果
        self._agent_results: List[Dict[str, Any]] = []  # 所有智能体调用结果

    # ==================== 执行历史管理 ====================

    def add_step_result(self, step_record: Dict[str, Any]):
        """添加步骤执行结果"""
        self._step_results.append(step_record)
        result = step_record.get("result", {})
        if step_record.get("type") == "tool":
            self._tool_results.append(result)
        elif step_record.get("type") == "agent":
            self._agent_results.append(result)

    def get_step_results(self) -> List[Dict[str, Any]]:
        """获取所有步骤结果"""
        return self._step_results

    def get_tool_results(self) -> List[Dict[str, Any]]:
        """获取所有工具调用结果"""
        return self._tool_results

    def get_agent_results(self) -> List[Dict[str, Any]]:
        """获取所有智能体调用结果"""
        return self._agent_results

    def clear_history(self):
        """清空执行历史"""
        self._step_results.clear()
        self._tool_results.clear()
        self._agent_results.clear()


def _extract_step_summary(step_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """
    提取步骤执行的关键信息摘要，用于前端显示

    Args:
        step_name: 工具名称
        result: 执行结果

    Returns:
        摘要信息字典
    """
    summary = {
        "success": result.get("success", False),
    }

    if not result.get("success"):
        summary["error"] = result.get("error", "执行失败")
        return summary

    # 根据工具类型提取关键信息
    if step_name == "generate_outline":
        outline = result.get("outline", {})
        if isinstance(outline, list):
            summary["sections_count"] = len(outline)
        elif isinstance(outline, dict):
            summary["sections_count"] = len(outline.get("sections", []))
        summary["title"] = result.get("title", "")

    elif step_name == "multi_query_search":
        summary["document_count"] = result.get("count", 0)
        summary["document_ids"] = result.get("document_ids", [])[:10]  # 只显示前10个

    elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
        docs = result.get("documents", [])
        summary["document_count"] = len(docs)
        if docs:
            summary["sample_titles"] = [doc.get("title", "")[:30] for doc in docs[:3]]

    elif step_name == "document_extraction":
        extracted = result.get("extracted_content", {})
        summary_data = result.get("summary", {})
        summary["sections_with_content"] = summary_data.get("sections_with_content", 0)
        summary["total_chunks"] = summary_data.get("total_extracted_chunks", 0)

    elif step_name == "document_compose":
        doc = result.get("document", {})
        summary["word_count"] = doc.get("word_count", 0)
        summary["sections_count"] = doc.get("sections_count", 0)
        summary["title"] = doc.get("title", "")
        summary["has_content"] = bool(doc.get("content"))

    elif step_name == "document_review":
        reviewed = result.get("reviewed_document", {})
        review_summary = result.get("review_summary", {})
        summary["word_count"] = reviewed.get("word_count", 0)
        summary["errors_found"] = review_summary.get("errors_found", 0)
        summary["corrections_made"] = review_summary.get("corrections_made", 0)
        summary["improvements"] = review_summary.get("improvements", [])

    elif step_name == "analyze_documents":
        summary["analysis_complete"] = True
        if result.get("analysis"):
            summary["key_points"] = result.get("analysis", {}).get("key_points", [])[:3]

    return summary


def get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    从嵌套字典中获取值

    支持点号路径，例如: "outline.sections" 或 "result.data.items"

    Args:
        data: 数据字典
        path: 路径字符串
        default: 默认值

    Returns:
        提取的值
    """
    keys = path.split(".")
    value = data

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
            if value is None:
                return default
        else:
            return default

    return value


def compress_state_for_llm(
    state: CustomExecutionState,
    target_tool_name: Optional[str] = None,
    max_steps: int = 5,
    max_context_chars: int = 8000,
) -> str:
    """
    压缩执行状态以供LLM使用（优化版）

    对文档内容进行智能压缩，只保留元数据，避免传递大量文本。
    支持智能过滤：只保留与目标工具相关的历史步骤。

    Args:
        state: 执行状态
        target_tool_name: 目标工具名称（用于过滤相关步骤）
        max_steps: 最多保留的历史步骤数（默认5个）
        max_context_chars: 最大上下文字符数（默认8000）

    Returns:
        压缩后的状态描述（JSON字符串）
    """
    compressed = {
        "query": state.query,
        "template_id": state.template_id,
        "step_history": [],
    }

    # 1. 智能过滤历史步骤
    relevant_steps = state.get_step_results()

    # 如果指定了目标工具，优先保留相关的步骤
    if target_tool_name:
        # 定义工具依赖关系（哪些工具的结果可能被当前工具使用）
        tool_dependencies = {
            "multi_query_search": ["generate_outline"],
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
        }

        # 找到相关的工具名称
        related_tools = tool_dependencies.get(target_tool_name, [])

        # 优先保留相关步骤，然后保留最近的步骤
        relevant_steps = sorted(
            state.get_step_results(),
            key=lambda s: (
                s.get("name") in related_tools,  # 相关工具优先
                s.get("step", 0),  # 然后按步骤号倒序（最近的在前）
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
            "type": step.get("type"),
            "name": step.get("name"),
            "success": step.get("result", {}).get("success"),
        }

        # 压缩结果数据
        result = step.get("result", {})
        compressed_result = {}

        for key, value in result.items():
            # 文档内容特殊处理 - 只保留元数据
            if key == "documents" and isinstance(value, list):
                compressed_result["documents"] = [
                    {
                        "id": doc.get("id"),
                        "title": doc.get("title", "")[:50],  # 限制标题长度
                        "doc_number": doc.get("doc_number"),
                        "content_length": len(doc.get("content", "")),
                    }
                    for doc in value[:5]  # 最多显示5个文档（减少）
                ]
                if len(value) > 5:
                    compressed_result["documents_count"] = len(value)

            # 文档ID列表 - 只保留前20个
            elif key == "document_ids" and isinstance(value, list):
                compressed_result["document_ids"] = value[:20]  # 减少到20个
                if len(value) > 20:
                    compressed_result["document_ids_count"] = len(value)

            # 大纲结构 - 压缩处理
            elif key == "outline":
                if isinstance(value, dict):
                    # 只保留大纲的关键信息
                    compressed_outline = {
                        "title": value.get("title", "")[:100],
                        "sections_count": len(value.get("sections", [])),
                    }
                    # 只保留前3个章节的标题
                    sections = value.get("sections", [])[:3]
                    compressed_outline["sections"] = [
                        {
                            "title": s.get("title", "")[:50],
                            "data_requirements": (
                                s.get("data_requirements", "")[:100]
                                if s.get("data_requirements")
                                else None
                            ),
                        }
                        for s in sections
                    ]
                    compressed_result["outline"] = compressed_outline
                else:
                    compressed_result["outline"] = value

            # 错误信息
            elif key == "error":
                compressed_result["error"] = str(value)[:200]  # 限制错误信息长度

            # 其他小型数据
            elif not isinstance(value, (list, dict)) or len(str(value)) < 300:
                compressed_result[key] = value
            # 大型数据只保留摘要
            else:
                compressed_result[f"{key}_summary"] = (
                    f"<{type(value).__name__}, {len(str(value))} chars>"
                )

        compressed_step["result"] = compressed_result
        compressed["step_history"].append(compressed_step)

    # 3. 添加当前可用的中间数据摘要（更简洁）
    intermediate_summary = {}
    for key, value in state.intermediate_data.items():
        if key == "documents" and isinstance(value, list):
            intermediate_summary["documents"] = f"{len(value)} docs available"
        elif key == "document_ids" and isinstance(value, list):
            intermediate_summary["document_ids"] = (
                f"{len(value)} IDs: {value[:5]}..." if len(value) > 5 else value
            )
        elif key == "outline" and isinstance(value, dict):
            sections_count = len(value.get("sections", []))
            intermediate_summary["outline"] = f"outline with {sections_count} sections"
        elif isinstance(value, (list, dict)):
            intermediate_summary[key] = (
                f"{type(value).__name__}({len(str(value))} chars)"
            )
        else:
            intermediate_summary[key] = value

    compressed["available_data"] = intermediate_summary

    # 4. 转换为JSON并检查长度
    result_json = json.dumps(compressed, ensure_ascii=False, indent=1)  # 使用更小的缩进

    # 如果超过限制，进一步压缩
    if len(result_json) > max_context_chars:
        # 移除更多细节
        compressed["step_history"] = compressed["step_history"][
            -3:
        ]  # 只保留最后3个步骤
        result_json = json.dumps(compressed, ensure_ascii=False, indent=1)

        # 如果还是太长，使用单行格式
        if len(result_json) > max_context_chars:
            result_json = json.dumps(
                compressed, ensure_ascii=False, separators=(",", ":")
            )

    return result_json


class CustomAgentExecutor:
    """
    自定义Agent执行器

    核心功能：根据已保存的Agent定义，按步骤执行工具和智能体
    """

    @staticmethod
    async def build_tool_arguments_with_llm(
        step: Dict[str, Any],
        state: CustomExecutionState,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        使用LLM自主构造工具参数（优化版）

        基于完整的执行状态（所有历史步骤结果），让LLM自主决定下一步的参数。
        优化了上下文长度，只传递相关的历史信息。

        Args:
            step: 当前步骤配置
            state: 完整的执行状态（包含所有历史结果）
            db: 数据库会话

        Returns:
            工具参数字典
        """
        step_name = step.get("name")
        step_type = step.get("type")
        step_desc = step.get("description", "")

        logger.info(f"🤖 使用LLM构造参数: {step_name}")

        # 1. 智能压缩状态（只保留相关步骤，避免上下文过长）
        compressed_state = compress_state_for_llm(
            state,
            target_tool_name=step_name,
            max_steps=5,  # 最多保留5个历史步骤
            max_context_chars=8000,  # 最大8000字符
        )

        logger.debug(f"   压缩后状态长度: {len(compressed_state)} 字符")

        # 2. 获取工具参数schema（从工具定义中）
        from core.tools.tool_registry import get_tool_metadata

        tool_metadata = get_tool_metadata(step_name)
        if not tool_metadata:
            logger.warning(f"⚠️ 未找到工具元数据: {step_name}，使用默认参数")
            return {"template_id": state.template_id}

        tool_params_schema = tool_metadata.get("parameters", {})
        allowed_params = set(tool_params_schema.get("properties", {}).keys())

        # 压缩schema（只保留关键信息）
        schema_summary = {
            "properties": {
                k: {
                    "type": v.get("type"),
                    "description": v.get("description", "")[:100],  # 限制描述长度
                }
                for k, v in tool_params_schema.get("properties", {}).items()
            },
            "required": tool_params_schema.get("required", []),
        }

        # 检查工具是否需要 template_id
        needs_template_id = "template_id" in allowed_params
        template_id_rule = (
            f"3. 必须包含template_id: {state.template_id}"
            if needs_template_id
            else "3. 如果工具需要template_id，则包含它；否则不要包含"
        )

        # 3. 构造更简洁的LLM prompt
        system_prompt = f"""你是参数构造助手。根据执行历史和工具定义，生成工具参数（JSON格式）。

工具: {step_name}
描述: {step_desc[:200]}

参数Schema:
{json.dumps(schema_summary, ensure_ascii=False, indent=1)}

执行历史:
{compressed_state}

规则:
1. 从历史结果中提取数据（如document_ids、outline等）
2. 如需文档内容，设置documents为"<use_available_documents>"
{template_id_rule}
4. 只包含参数Schema中定义的参数，不要添加额外参数
5. 返回纯JSON，无其他文字"""

        user_prompt = f"为工具 {step_name} 生成参数。"

        try:
            # 4. 调用LLM
            llm_client = get_llm_client()
            response = await llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                db=db,
                response_format={"type": "json_object"},
                max_tokens=1024,  # 参数通常不会很长，限制输出长度
            )

            # 5. 解析LLM响应
            arguments = json.loads(response)
            logger.info(f"   🤖 LLM生成的参数: {arguments}")

            # 6. 后处理：替换特殊占位符
            if arguments.get("documents") == "<use_available_documents>":
                arguments["documents"] = state.get_data("documents", [])
                logger.info(f"   📄 使用可用文档: {len(arguments['documents'])} 个")

            # 确保 template_id 存在（仅在工具需要时）
            if needs_template_id and "template_id" not in arguments:
                arguments["template_id"] = state.template_id

            # 过滤掉不在 schema 中的参数（双重保险）
            filtered_arguments = {
                k: v for k, v in arguments.items() if k in allowed_params
            }

            removed_params = set(arguments.keys()) - allowed_params
            if removed_params:
                logger.debug(
                    f"   过滤掉工具 {step_name} 不需要的参数: {removed_params}"
                )

            return filtered_arguments

        except Exception as e:
            logger.error(f"❌ LLM构造参数失败: {e}，使用fallback逻辑")
            import traceback

            logger.error(traceback.format_exc())

            # Fallback: 使用简单规则
            return CustomAgentExecutor._build_tool_arguments_fallback(step, state)

    @staticmethod
    def _build_tool_arguments_fallback(
        step: Dict[str, Any],
        state: CustomExecutionState,
    ) -> Dict[str, Any]:
        """
        参数构造的fallback逻辑（当LLM失败时）

        使用简单规则从状态中提取参数
        """
        step_name = step.get("name")
        query = state.query
        template_id = state.template_id
        intermediate_data = state.intermediate_data

        arguments = {"template_id": template_id}

        # 基于步骤名称的简单规则
        if step_name == "generate_outline":
            arguments["query"] = query
            arguments["user_requirements"] = query

        elif step_name == "multi_query_search":
            outline = intermediate_data.get("outline", {})
            sections = outline.get("sections", [])
            if sections:
                queries = [
                    section.get("data_requirements") or section.get("title")
                    for section in sections
                    if section.get("data_requirements") or section.get("title")
                ]
                arguments["queries"] = queries
                arguments["top_k_per_query"] = 5
                arguments["deduplication"] = True
            else:
                arguments["queries"] = [query]

        elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
            arguments["document_ids"] = intermediate_data.get("document_ids", [])

        elif step_name == "analyze_documents":
            arguments["query"] = query
            arguments["documents"] = intermediate_data.get("documents", [])

        elif step_name == "search_documents_by_classification":
            arguments["class_code"] = None

        elif step_name == "es_fulltext_search":
            arguments["query"] = query
            arguments["top_k"] = 10

        elif step_name == "document_extraction":
            arguments["outline"] = intermediate_data.get("outline", {})
            arguments["documents"] = intermediate_data.get("documents", [])
            arguments["query"] = query

        elif step_name == "document_compose":
            arguments["outline"] = intermediate_data.get("outline", {})
            arguments["extracted_content"] = intermediate_data.get(
                "extracted_content", {}
            )
            arguments["query"] = query

        elif step_name == "document_review":
            # 优先使用组合后的文档，如果没有则使用其他文档
            composed_doc = intermediate_data.get("composed_document", {})
            if composed_doc:
                arguments["document"] = composed_doc
            else:
                # 如果没有组合文档，尝试从其他来源获取
                arguments["document"] = {
                    "title": intermediate_data.get("outline", {}).get(
                        "title", "未命名文档"
                    ),
                    "content": "",
                }

        logger.info(f"   🔧 Fallback参数: {arguments}")
        return arguments

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

        Args:
            agent: CustomAgent数据库模型实例
            query: 用户查询
            template_id: 模板ID
            session_id: 会话ID
            db: 数据库会话
            es_client: ES客户端
            es_index: ES索引

        Yields:
            执行过程的事件流（SSE格式）
        """
        logger.info(f"🚀 开始执行自定义Agent: {agent.name}")

        # 1. 发送执行计划事件
        steps = agent.steps if isinstance(agent.steps, list) else []

        yield {
            "event": "execution_plan",
            "data": {
                "agent_name": agent.name,
                "description": agent.description,
                "execution_pattern": agent.execution_pattern,
                "plan": [
                    {
                        "step": s.get("step"),
                        "type": s.get("type"),
                        "name": s.get("name"),
                        "description": s.get("description"),
                    }
                    for s in steps
                ],
            },
        }

        # 2. 初始化执行状态（使用 CustomExecutionState，自动初始化中间数据）
        execution_state = CustomExecutionState(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            session_id=session_id,
            query=query,
        )

        # 3. 逐步执行
        from core.agents.qa_agent_v2 import generate_answer_v2
        from core.agents.retrieval_agent_v2 import retrieve_documents_v2
        from core.tools.base import execute_tool

        for i, step in enumerate(steps):
            step_num = step.get("step", i + 1)
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行步骤{step_num}: {step_type}/{step_name}")

            # 发送步骤开始事件
            yield {
                "event": "stage_start",
                "data": {
                    "stage": f"step_{step_num}",
                    "step": step_num,
                    "type": step_type,
                    "name": step_name,
                    "description": step_desc,
                    "message": f"正在执行: {step_desc}",
                    "status": "running",
                },
            }

            try:
                result = None

                if step_type == "tool":
                    # 🚀 使用LLM自主构造参数（基于完整执行状态）
                    arguments = await CustomAgentExecutor.build_tool_arguments_with_llm(
                        step=step,
                        state=execution_state,
                        db=db,
                    )

                    # 执行工具（使用 execution_state 的 to_tool_context 方法）
                    result = await execute_tool(
                        step_name, arguments, execution_state.to_tool_context()
                    )

                    # 📝 记录到执行状态
                    step_record = {
                        "step": step_num,
                        "type": step_type,
                        "name": step_name,
                        "description": step_desc,
                        "arguments": arguments,
                        "result": result,
                    }
                    execution_state.add_step_result(step_record)

                    # 更新中间数据（方便快速访问）
                    if result.get("success"):
                        # 大纲生成工具
                        if step_name == "generate_outline":
                            outline_data = result.get("outline", {})
                            # 如果outline是列表，转换为字典格式
                            if isinstance(outline_data, list):
                                outline_data = {
                                    "sections": outline_data,
                                    "title": result.get("title", ""),
                                }
                            execution_state.set_data("outline", outline_data)

                        # 检索工具 - 更新 document_ids
                        elif step_name in [
                            "search_documents_by_classification",
                            "es_fulltext_search",
                            "multi_query_search",
                        ]:
                            execution_state.set_data(
                                "document_ids", result.get("document_ids", [])
                            )
                            # 如果有documents摘要，也保存
                            if result.get("documents"):
                                execution_state.set_data(
                                    "documents", result.get("documents", [])
                                )

                        # 文档内容获取工具 - 更新 documents
                        elif step_name in [
                            "get_document_contents",
                            "skim_documents",
                            "read_documents",
                        ]:
                            execution_state.set_data(
                                "documents", result.get("documents", [])
                            )

                        # 文档摘取工具 - 保存摘取的内容
                        elif step_name == "document_extraction":
                            execution_state.set_data(
                                "extracted_content", result.get("extracted_content", {})
                            )

                        # 文档组合工具 - 保存生成的文档
                        elif step_name == "document_compose":
                            execution_state.set_data(
                                "composed_document", result.get("document", {})
                            )

                        # 文档校对工具 - 保存校对后的文档
                        elif step_name == "document_review":
                            execution_state.set_data(
                                "reviewed_document", result.get("reviewed_document", {})
                            )

                elif step_type == "agent":
                    # 执行智能体
                    if step_name == "retrieval_agent":
                        result = await retrieve_documents_v2(
                            query=query,
                            template_id=template_id,
                            session_id=session_id,
                            db=db,
                            es_client=es_client,
                            es_index=es_index,
                            top_k=20,
                            enable_deduplication=True,
                        )
                        if result.get("success"):
                            execution_state.set_data(
                                "documents", result.get("documents", [])
                            )

                    elif step_name == "qa_agent":
                        documents = execution_state.get_data("documents", [])
                        result = await generate_answer_v2(
                            query=query,
                            documents=documents,
                            db=db,
                            max_context_length=10000,
                        )

                    else:
                        result = {
                            "success": False,
                            "error": f"未知的智能体: {step_name}",
                        }

                    # 📝 记录到执行状态
                    step_record = {
                        "step": step_num,
                        "type": step_type,
                        "name": step_name,
                        "description": step_desc,
                        "result": result,
                    }
                    execution_state.add_step_result(step_record)

                else:
                    result = {
                        "success": False,
                        "error": f"未知的步骤类型: {step_type}",
                    }

                # 发送步骤完成事件（包含详细信息）
                yield {
                    "event": "stage_complete",
                    "data": {
                        "stage": f"step_{step_num}",
                        "step": step_num,
                        "type": step_type,
                        "name": step_name,
                        "description": step_desc,
                        "message": f"步骤{step_num}完成: {step_desc}",
                        "status": "completed",
                        "success": result.get("success", False),
                        "result": result,
                        # 提取关键信息用于前端显示
                        "summary": _extract_step_summary(step_name, result),
                    },
                }

                logger.info(f"✅ 步骤{step_num}完成: {step_name}")

            except Exception as e:
                logger.error(f"❌ 步骤{step_num}失败: {e}")
                import traceback

                logger.error(traceback.format_exc())

                yield {
                    "event": "stage_error",
                    "data": {
                        "stage": f"step_{step_num}",
                        "step": step_num,
                        "type": step_type,
                        "name": step_name,
                        "description": step_desc,
                        "message": f"步骤{step_num}失败: {step_desc}",
                        "status": "error",
                        "success": False,
                        "error": str(e),
                    },
                }

        # 4. 生成最终答案
        logger.info("📝 生成最终答案")

        final_answer = None
        documents = execution_state.get_data("documents", [])

        # 如果有qa_agent结果，使用其答案
        for agent_result in execution_state.get_agent_results():
            if agent_result.get("success") and agent_result.get("answer"):
                final_answer = agent_result.get("answer")
                break

        # 如果没有答案但有文档，用LLM生成答案
        if not final_answer and documents:
            try:
                llm_client = get_llm_client()

                # 构建文档上下文
                doc_context = "\n\n".join(
                    [
                        f"【文档{i+1}】{doc.get('title', '未命名')}\n{doc.get('content', '')[:500]}"
                        for i, doc in enumerate(documents[:5])
                    ]
                )

                system_prompt = (
                    "你是一个专业的问答助手。请基于提供的文档内容回答用户的问题。"
                )
                user_prompt = f"""基于以下文档回答问题。

【文档内容】
{doc_context}

【用户问题】
{query}

请给出详细的回答。
"""

                # 使用流式接口避免超时
                final_answer = await llm_client.chat_completion_but_in_stream(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    db=db,
                    max_tokens=2000,
                )
            except Exception as e:
                logger.error(f"❌ 生成答案失败: {e}")
                final_answer = "抱歉，生成答案时出现错误。"

        # 5. 发送最终答案（如果是文档生成类Agent，返回Markdown格式）
        final_document = execution_state.get_data(
            "reviewed_document"
        ) or execution_state.get_data("composed_document")

        yield {
            "event": "answer",
            "data": {
                "answer": final_answer or "执行完成",
                "documents": documents,
                "document": final_document,  # 如果有生成的文档，也返回
            },
        }

        # 6. 发送完成事件
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
            },
        }

        logger.info(f"✅ 自定义Agent执行完成: {agent.name}")
