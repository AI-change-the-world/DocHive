import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, TypedDict

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from utils.llm_client import get_llm_client


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


class CustomExecutionState(TypedDict):
    """
    自定义Agent执行状态 - 累积所有步骤的执行结果
    """
    # 基础信息
    query: str
    template_id: int
    session_id: Optional[str]

    # 执行历史（累积所有步骤的结果）
    step_results: List[Dict[str, Any]]  # 所有步骤的结果列表
    tool_results: List[Dict[str, Any]]  # 所有工具调用结果
    agent_results: List[Dict[str, Any]]  # 所有智能体调用结果

    # 中间数据（方便快速访问）
    # 如: {"documents": [], "document_ids": [], "outline": {}}
    intermediate_data: Dict[str, Any]


def compress_state_for_llm(state: CustomExecutionState) -> str:
    """
    压缩执行状态以供LLM使用

    对文档内容进行智能压缩，只保留元数据，避免传递大量文本

    Args:
        state: 执行状态

    Returns:
        压缩后的状态描述（JSON字符串）
    """
    compressed = {
        "query": state["query"],
        "template_id": state["template_id"],
        "step_history": [],
    }

    # 压缩每一步的结果
    for step in state["step_results"]:
        compressed_step = {
            "step": step.get("step"),
            "type": step.get("type"),
            "name": step.get("name"),
            "description": step.get("description"),
            "success": step.get("result", {}).get("success"),
        }

        # 压缩结果数据
        result = step.get("result", {})
        compressed_result = {}

        for key, value in result.items():
            # 文档内容特殊处理
            if key == "documents" and isinstance(value, list):
                compressed_result["documents"] = [
                    {
                        "id": doc.get("id"),
                        "title": doc.get("title"),
                        "doc_number": doc.get("doc_number"),
                        "content_length": len(doc.get("content", "")),
                        "class_code": doc.get("class_code"),
                    }
                    for doc in value[:10]  # 最多显示10个文档
                ]
            # 文档ID列表
            elif key == "document_ids" and isinstance(value, list):
                compressed_result["document_ids"] = value[:50]  # 最多显示50个ID
            # 大纲结构
            elif key == "outline":
                compressed_result["outline"] = value
            # 错误信息
            elif key == "error":
                compressed_result["error"] = value
            # 其他小型数据
            elif not isinstance(value, (list, dict)) or len(str(value)) < 500:
                compressed_result[key] = value
            # 大型数据只保留摘要
            else:
                compressed_result[f"{key}_summary"] = f"<数据类型: {type(value).__name__}, 大小: {len(str(value))} 字符>"

        compressed_step["result"] = compressed_result
        compressed["step_history"].append(compressed_step)

    # 添加当前可用的中间数据摘要
    intermediate_summary = {}
    for key, value in state["intermediate_data"].items():
        if key == "documents" and isinstance(value, list):
            intermediate_summary["documents"] = f"<{len(value)}个文档可用>"
        elif key == "document_ids" and isinstance(value, list):
            intermediate_summary["document_ids"] = f"<{len(value)}个文档ID: {value[:10]}...>"
        elif isinstance(value, (list, dict)):
            intermediate_summary[key] = f"<{type(value).__name__}, 大小: {len(str(value))[:100]}>"
        else:
            intermediate_summary[key] = value

    compressed["available_data"] = intermediate_summary

    return json.dumps(compressed, ensure_ascii=False, indent=2)


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
        使用LLM自主构造工具参数

        基于完整的执行状态（所有历史步骤结果），让LLM自主决定下一步的参数。
        这样可以避免硬编码参数映射，让Agent更加智能和灵活。

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

        # 1. 压缩状态（避免传递大量文档内容）
        compressed_state = compress_state_for_llm(state)

        # 2. 获取工具参数schema（从工具定义中）
        from core.tools.tool_registry import get_tool_metadata

        tool_metadata = get_tool_metadata(step_name)
        if not tool_metadata:
            logger.warning(f"⚠️ 未找到工具元数据: {step_name}，使用默认参数")
            return {"template_id": state["template_id"]}

        tool_params_schema = tool_metadata.get("parameters", {})

        # 3. 构造LLM prompt
        system_prompt = f"""你是一个参数构造助手。根据当前执行状态和工具定义，为下一步工具调用生成合适的参数。

【重要规则】
1. 仔细分析历史执行结果，从中提取有用的数据
2. 如果历史结果中有 documents（文档列表），你看到的是压缩后的元数据，实际使用时需要引用完整文档
3. 如果历史结果中有 document_ids，可以直接使用这些ID
4. 参数必须符合工具的schema定义
5. 返回JSON格式的参数字典

【当前工具】
名称: {step_name}
类型: {step_type}
描述: {step_desc}

【工具参数Schema】
{json.dumps(tool_params_schema, ensure_ascii=False, indent=2)}

【执行状态】
{compressed_state}

【输出格式】
返回JSON格式的参数字典，例如：
{{
    "query": "用户的问题",
    "template_id": 1,
    "document_ids": [1, 2, 3],
    ...
}}

注意：
- 如果需要使用文档内容，参数名应为 "documents"，值应设置为 "<use_available_documents>"（表示使用状态中的完整文档）
- 如果需要使用文档ID列表，参数名应为 "document_ids"，直接从历史结果中提取
- template_id 始终从状态中获取
"""

        user_prompt = f"请为工具 '{step_name}' 构造参数。"

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
            )

            # 5. 解析LLM响应
            arguments = json.loads(response)
            logger.info(f"   🤖 LLM生成的参数: {arguments}")

            # 6. 后处理：替换特殊占位符
            if arguments.get("documents") == "<use_available_documents>":
                arguments["documents"] = state["intermediate_data"].get(
                    "documents", [])
                logger.info(f"   📄 使用可用文档: {len(arguments['documents'])} 个")

            # 确保 template_id 存在
            if "template_id" not in arguments:
                arguments["template_id"] = state["template_id"]

            return arguments

        except Exception as e:
            logger.error(f"❌ LLM构造参数失败: {e}，使用fallback逻辑")
            import traceback
            logger.error(traceback.format_exc())

            # Fallback: 使用简单规则
            return CustomAgentExecutor._build_tool_arguments_fallback(
                step, state
            )

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
        query = state["query"]
        template_id = state["template_id"]
        intermediate_data = state["intermediate_data"]

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
            arguments["document_ids"] = intermediate_data.get(
                "document_ids", [])

        elif step_name == "analyze_documents":
            arguments["query"] = query
            arguments["documents"] = intermediate_data.get("documents", [])

        elif step_name == "search_documents_by_classification":
            arguments["class_code"] = None

        elif step_name == "es_fulltext_search":
            arguments["query"] = query
            arguments["top_k"] = 10

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

        # 2. 初始化执行状态（累积所有步骤结果）
        execution_state: CustomExecutionState = {
            "query": query,
            "template_id": template_id,
            "session_id": session_id,
            "step_results": [],  # 累积所有步骤的结果
            "tool_results": [],
            "agent_results": [],
            "intermediate_data": {
                "documents": [],
                "document_ids": [],
                "outline": {},
            },
        }

        # 3. 逐步执行
        from core.tools.base import ToolContext, execute_tool
        from core.agents.retrieval_agent_v2 import retrieve_documents_v2
        from core.agents.qa_agent_v2 import generate_answer_v2

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
                    "message": f"正在执行: {step_desc}",
                },
            }

            try:
                result = None

                if step_type == "tool":
                    # 执行工具
                    tool_ctx = ToolContext(
                        db=db,
                        es_client=es_client,
                        es_index=es_index,
                        template_id=template_id,
                        session_id=session_id,
                    )

                    # 🚀 使用LLM自主构造参数（基于完整执行状态）
                    arguments = await CustomAgentExecutor.build_tool_arguments_with_llm(
                        step=step,
                        state=execution_state,
                        db=db,
                    )

                    # 执行工具
                    result = await execute_tool(step_name, arguments, tool_ctx)

                    # 📝 记录到执行状态
                    step_record = {
                        "step": step_num,
                        "type": step_type,
                        "name": step_name,
                        "description": step_desc,
                        "arguments": arguments,
                        "result": result,
                    }
                    execution_state["step_results"].append(step_record)
                    execution_state["tool_results"].append(result)

                    # 更新中间数据（方便快速访问）
                    if result.get("success"):
                        # 大纲生成工具
                        if step_name == "generate_outline":
                            execution_state["intermediate_data"]["outline"] = result.get(
                                "outline", {})

                        # 检索工具 - 更新 document_ids
                        elif step_name in [
                            "search_documents_by_classification",
                            "es_fulltext_search",
                            "multi_query_search",
                        ]:
                            execution_state["intermediate_data"]["document_ids"] = result.get(
                                "document_ids", []
                            )

                        # 文档内容获取工具 - 更新 documents
                        elif step_name in [
                            "get_document_contents",
                            "skim_documents",
                            "read_documents",
                        ]:
                            execution_state["intermediate_data"]["documents"] = result.get(
                                "documents", [])

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
                            execution_state["intermediate_data"]["documents"] = result.get(
                                "documents", [])

                    elif step_name == "qa_agent":
                        documents = execution_state["intermediate_data"].get(
                            "documents", [])
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
                    execution_state["step_results"].append(step_record)
                    execution_state["agent_results"].append(result)

                else:
                    result = {
                        "success": False,
                        "error": f"未知的步骤类型: {step_type}",
                    }

                # 发送步骤完成事件
                yield {
                    "event": "stage_complete",
                    "data": {
                        "stage": f"step_{step_num}",
                        "message": f"步骤{step_num}完成",
                        "result": result,
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
                        "error": str(e),
                    },
                }

        # 4. 生成最终答案
        logger.info("📝 生成最终答案")

        final_answer = None
        documents = execution_state["intermediate_data"].get("documents", [])

        # 如果有qa_agent结果，使用其答案
        for agent_result in execution_state.get("agent_results", []):
            if agent_result.get("success") and agent_result.get("answer"):
                final_answer = agent_result.get("answer")
                break

        # 如果没有答案但有文档，用LLM生成答案
        if not final_answer and documents:
            try:
                llm_client = get_llm_client()

                # 构建文档上下文
                doc_context = "\n\n".join([
                    f"【文档{i+1}】{doc.get('title', '未命名')}\n{doc.get('content', '')[:500]}"
                    for i, doc in enumerate(documents[:5])
                ])

                system_prompt = "你是一个专业的问答助手。请基于提供的文档内容回答用户的问题。"
                user_prompt = f"""基于以下文档回答问题。

【文档内容】
{doc_context}

【用户问题】
{query}

请给出详细的回答。
"""

                final_answer = await llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    db=db,
                )
            except Exception as e:
                logger.error(f"❌ 生成答案失败: {e}")
                final_answer = "抱歉，生成答案时出现错误。"

        # 5. 发送最终答案
        yield {
            "event": "answer",
            "data": {
                "answer": final_answer or "执行完成",
                "documents": documents,
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
