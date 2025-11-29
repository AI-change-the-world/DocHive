""" 
主路由器V4 - 支持多轮对话和用户干预

功能：
1. 基于session_id的会话状态管理
2. 支持多轮对话
3. 支持用户干预（检索结果过多/过少时请求用户输入）
4. 三步执行流程：规划 → 执行 → 总结

特点：内存管理会话状态，支持暂停和恢复执行
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.qa_agent_v2 import generate_answer_v2

# 使用新版智能体
from core.agents.retrieval_agent_v2 import retrieve_documents_v2
from backend.core.conversation_manager import get_conversation_manager
from core.registry import (
    get_agents_description,
    get_execution_patterns_description,
    get_tools_description,
)

# 导入新版工具基础设施
from core.tools.base import ToolContext, execute_tool
from utils.llm_client import get_llm_client

# ==================== 用户意图识别 ====================


async def analyze_user_intent(
    query: str,
    conversation_history: List[Dict[str, Any]],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    分析用户意图

    Args:
        query: 当前用户输入
        conversation_history: 对话历史
        db: 数据库会话

    Returns:
        {
            "intent_type": "response_to_hint" | "new_question" | "follow_up",
            "reasoning": "判断理由"
        }
    """
    llm_client = get_llm_client()

    # 构建对话上下文（只取最后5轮）
    recent_messages = conversation_history[-10:]  # 最后5轮对话
    context_lines = []
    for msg in recent_messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            context_lines.append(f"用户: {content}")
        elif role == "assistant":
            context_lines.append(f"助手: {content[:200]}...")  # 截断过长内容

    conversation_context = "\n".join(context_lines)

    system_prompt = """你是一个用户意图分析助手。分析用户输入属于以下哪种意图：

1. **response_to_hint**: 用户回应了系统的提示（如"继续"、"使用前20篇"、"好的"、"行"等简短确认）
   - 特征：用户输入非常简短，像是对上一条消息的回应
   - 上一条assistant消息通常包含"检索到XX篇文档"、"请选择"等提示

2. **new_question**: 用户提出了全新的问题，与之前的对话无关
   - 特征：问题完整、独立，不依赖之前的上下文

3. **follow_up**: 追问或延续之前的话题
   - 特征：使用代词（它、这个、那个）、或者问题与之前的话题相关

请返回JSON格式：
{
    "intent_type": "response_to_hint" | "new_question" | "follow_up",
    "reasoning": "简要说明判断理由"
}
"""

    user_prompt = f"""【对话上下文】
{conversation_context}

【当前用户输入】
{query}

请分析用户意图。"""

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )
        logger.info(f"💡 意图识别结果: {response}")

        return response

    except Exception as e:
        logger.error(f"⚠️ 意图识别失败: {e}，默认为new_question")
        return {
            "intent_type": "new_question",
            "reasoning": "意图识别失败，默认为新问题",
        }


async def filter_relevant_context(
    query: str,
    conversation_history: List[Dict[str, Any]],
    db: AsyncSession,
) -> str:
    """
    从历史对话中过滤出与当前问题相关的上下文

    Args:
        query: 当前问题
        conversation_history: 对话历史
        db: 数据库会话

    Returns:
        过滤后的相关上下文字符串
    """
    llm_client = get_llm_client()

    # 构建历史对话（只取最后5轮）
    recent_messages = conversation_history[-10:]
    context_lines = []
    for i, msg in enumerate(recent_messages):
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            context_lines.append(f"[{i+1}] 用户: {content}")
        elif role == "assistant":
            # 截取前500字符
            context_lines.append(f"[{i+1}] 助手: {content[:500]}...")

    conversation_context = "\n".join(context_lines)

    system_prompt = """你是一个上下文过滤助手。从历史对话中提取与当前问题相关的关键信息。

要求：
1. 只保留与当前问题**直接相关**的内容
2. 删除无关的对话轮次
3. 精简提取，不要原样复制
4. 如果没有相关上下文，返回空字符串

返回格式：直接返回过滤后的上下文文本，不需要JSON。
"""

    user_prompt = f"""【历史对话】
{conversation_context}

【当前问题】
{query}

请提取与当前问题相关的上下文。"""

    try:
        response = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )

        logger.info(f"📋 过滤后的上下文: {response[:200]}...")
        return response.strip()

    except Exception as e:
        logger.error(f"⚠️ 上下文过滤失败: {e}")
        return ""


# ==================== 状态管理 ====================


class ExecutionState(TypedDict):
    """
    执行状态 - 记录整个执行过程（LangGraph状态）
    """

    # 输入
    query: str
    template_id: int
    session_id: str

    # 决策
    execution_pattern: str  # tool_only / agent_only / agent_chain / hybrid / llm_direct
    reasoning: str  # LLM的推理过程
    execution_plan: List[Dict[str, Any]]  # 执行计划

    # 执行结果
    tool_results: List[Dict[str, Any]]  # 工具调用结果
    agent_results: List[Dict[str, Any]]  # 智能体调用结果
    intermediate_data: Dict[str, Any]  # 中间数据（如检索到的文档）

    # 最终输出
    final_answer: Optional[str]  # 最终答案
    documents: List[Dict[str, Any]]  # 相关文档（如果有）
    success: bool  # 是否成功
    error: Optional[str]  # 错误信息


# ==================== 节点函数 ====================


async def plan_execution(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 执行计划

    调用LLM分析查询，选择执行模式和组件。
    """
    logger.info("🧠 ========== 节点: 执行计划 ===========")

    query = state["query"]
    template_id = state["template_id"]
    session_id = state["session_id"]

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    llm_client = get_llm_client()

    # 获取对话历史（用于元问题识别和回答）
    conversation_manager = get_conversation_manager()
    session_data = conversation_manager.get_session(session_id)
    conversation_history = session_data.get(
        "messages", []) if session_data else []

    # 构建系统能力描述
    tools_desc = get_tools_description()
    agents_desc = get_agents_description()
    patterns_desc = get_execution_patterns_description()

    system_prompt = f"""你是一个智能任务调度助手，负责分析用户查询并选择执行方案。

【当前模板ID】
{template_id}

【系统能力清单】

## 1. 可用工具
{tools_desc}

## 2. 可用智能体
{agents_desc}

## 3. 执行模式
{patterns_desc}

【决策规则】
1. **分析查询**：理解用户真正的需求
2. **识别问题类型**：
   - **元问题（Meta Query）**：关于对话本身的统计问题
     * 示例："我问了几次XX？"、"这是第几个问题？"、"我们讨论了什么？"
     * 处理：直接使用 llm_direct 模式回答，不要检索文档
   - **文档查询**：关于文档内容的实际问题
     * 示例："XX文档讲了什么？"、"XX的主要内容是？"
     * 处理：使用检索+问答流程
3. **选择模式**：根据查询类型选择最适合的执行模式
4. **选择组件**：
   - tool_only: 列出需要调用的工具名称
   - agent_only: 指定要调用的智能体名称
   - agent_chain: 按顺序列出要调用的智能体名称
   - hybrid: 混合工具和智能体名称
   - llm_direct: 直接使用你的知识回答（用于元问题、通用知识问题等）

**重要**：你只需要选择调用哪些工具/智能体，不需要指定具体参数。每个工具/智能体会自行分析用户查询并生成所需参数。

【返回格式】
返回JSON格式：
{{
    "execution_pattern": "tool_only" | "agent_only" | "agent_chain" | "hybrid" | "llm_direct",
    "reasoning": "为什么选择这个模式",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool" | "agent",
            "name": "工具名或智能体名",
            "description": "描述这一步要做什么"
        }}
    ],
    "direct_answer": null | "直接答案"  // 仅当 execution_pattern="llm_direct" 时填写
}}

【示例】

示例1 - 统计查询：
问题: "有多少文档？"
返回:
{{
    "execution_pattern": "tool_only",
    "reasoning": "简单的统计查询，直接调用统计工具",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool",
            "name": "get_template_statistics",
            "description": "获取模板统计信息"
        }}
    ],
    "direct_answer": null
}}

示例2 - 仅检索：
问题: "查找关于安全的文档"
返回:
{{
    "execution_pattern": "agent_only",
    "reasoning": "需要检索文档，但不需要生成答案",
    "execution_plan": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索相关文档"
        }}
    ],
    "direct_answer": null
}}

示例3 - 完整问答：
问题: "安全规范的主要内容是什么？"
返回:
{{
    "execution_pattern": "agent_chain",
    "reasoning": "需要先检索文档，再理解内容生成答案",
    "execution_plan": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索相关文档"
        }},
        {{
            "step": 2,
            "type": "agent",
            "name": "qa_agent",
            "description": "基于检索结果生成答案"
        }}
    ],
    "direct_answer": null
}}

示例4 - 混合调用（概览所有文档+智能分析）：
问题: "有多少文档，每一份都详细归纳一下内容"
返回:
{{
    "execution_pattern": "tool_only",
    "reasoning": "用户想了解所有文档的详细内容，需要读取文档并分析",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool",
            "name": "get_template_statistics",
            "description": "获取文档数量统计"
        }},
        {{
            "step": 2,
            "type": "tool",
            "name": "search_documents_by_classification",
            "description": "获取所有文档ID列表"
        }},
        {{
            "step": 3,
            "type": "tool",
            "name": "get_document_contents",
            "description": "读取文档完整原文"
        }},
        {{
            "step": 4,
            "type": "tool",
            "name": "analyze_documents",
            "description": "智能分析文档（内部自动决定批量or逐份）"
        }}
    ],
    "direct_answer": null
}}

示例5 - 语义检索+问答：
问题: "查找关于地震应急的文档，并总结主要内容"
返回:
{{
    "execution_pattern": "agent_chain",
    "reasoning": "需要语义检索特定主题的文档，然后生成答案",
    "execution_plan": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索相关文档"
        }},
        {{
            "step": 2,
            "type": "agent",
            "name": "qa_agent",
            "description": "总结内容"
        }}
    ],
    "direct_answer": null
}}

示例6 - LLM直接回答（通用知识）：
问题: "什么是人工智能？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是通用知识问题，不需要查询文档，直接回答",
    "execution_plan": [],
    "direct_answer": "人工智能（Artificial Intelligence, AI）是计算机科学的一个分支..."
}}

示例7 - 元问题（对话统计）：
问题: "我问了几次 国家地震应急预案？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是一个元问题，用户询问的是对话历史中提及某主题的次数统计，需要直接分析对话记录，不需要检索文档",
    "execution_plan": [],
    "direct_answer": "根据对话历史，您提到'国家地震应急预案'共X次..."
}}

示例8 - 元问题vs文档查询的区分：
问题A: "我之前问过什么问题？" -> llm_direct（元问题，关于对话本身）
问题B: "之前查到的文档都讲了什么？" -> llm_direct（基于对话历史回答，不需要重新检索）
问题C: "国家地震应急预案的主要内容是什么？" -> agent_chain（文档查询，需要检索+问答）

【重要提示】
- **元问题识别**：凡是询问"我问了几次"、"我们讨论了什么"、"之前的对话"等关于对话本身的问题，必须使用 llm_direct
- 如果用户要分析文档内容（"总结"、"归纳"、"都讲了什么"），使用 analyze_documents 工具（它会内部决定批量or逐份）
- 如果用户问"查找XXX相关的文档"等语义检索问题，使用 retrieval_agent 智能体
- 区分"文档分析"和"语义检索"两种场景

现在，请为以下用户问题制定执行方案。只返回JSON，不要其他内容。
"""

    try:
        logger.info("🧠 调用LLM进行任务规划...")
        await asyncio.sleep(0.3)  # 规划延迟

        # 构建规划请求消息
        planning_messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 如果有对话历史，附加最近的对话（用于元问题识别）
        if conversation_history and len(conversation_history) > 1:
            # 取最近5轮对话
            recent_messages = conversation_history[-10:]
            context_summary = []
            for msg in recent_messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    context_summary.append(f"用户: {content[:100]}...")
                elif role == "assistant":
                    context_summary.append(f"助手: {content[:100]}...")

            context_text = "\n".join(context_summary)
            planning_messages.append(
                {
                    "role": "user",
                    "content": f"【对话历史】\n{context_text}\n\n【当前问题】\n{query}\n\n请为这个问题制定执行方案。",
                }
            )
        else:
            planning_messages.append(
                {"role": "user", "content": f"请为这个问题制定执行方案：{query}"}
            )

        response = await llm_client.extract_json_response(
            messages=planning_messages,
            db=db,
        )

        logger.info(f"📋 规划结果: {json.dumps(response, ensure_ascii=False)}")

        state["execution_pattern"] = response.get(
            "execution_pattern", "llm_direct")
        state["reasoning"] = response.get("reasoning", "")
        state["execution_plan"] = response.get("execution_plan", [])

        # 如果是LLM直接回答
        if state["execution_pattern"] == "llm_direct":
            direct_answer = response.get("direct_answer")
            if direct_answer:
                state["final_answer"] = direct_answer
                state["success"] = True
                logger.info("✅ LLM直接回答完成")
            else:
                # 没有直接答案，让LLM生成一个（带上对话历史，用于元问题）
                logger.info("📋 LLM未返回直接答案，生成回答（带对话历史）")

                # 构建消息列表
                llm_messages = [
                    {
                        "role": "system",
                        "content": "你是一个专业的问答助手。如果用户询问对话历史相关的问题（如'我问了几次XX'、'之前讨论了什么'），请基于对话历史进行统计和分析。",
                    }
                ]

                # 添加对话历史（元问题需要）
                if conversation_history and len(conversation_history) > 1:
                    # 添加历史消息
                    for msg in conversation_history[-20:]:  # 最近10轮对话
                        role = msg.get("role")
                        content = msg.get("content", "")
                        if role in ["user", "assistant"]:
                            llm_messages.append(
                                {"role": role, "content": content})

                # 添加当前问题
                llm_messages.append({"role": "user", "content": query})

                fallback_answer = await llm_client.chat_completion(
                    messages=llm_messages,
                    db=db,
                )
                state["final_answer"] = fallback_answer
                state["success"] = True
                logger.info("✅ LLM fallback回答完成")

    except Exception as e:
        logger.error(f"❌ 任务规划失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # 降级：直接让LLM回答
        state["execution_pattern"] = "llm_direct"
        state["reasoning"] = f"规划失败，降级到LLM直接回答: {str(e)}"
        try:
            fallback_answer = await llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个专业的问答助手"},
                    {"role": "user", "content": query},
                ],
                db=db,
            )
            state["final_answer"] = fallback_answer
            state["success"] = True
        except Exception as e2:
            state["error"] = f"回答失败: {str(e2)}"
            state["success"] = False

    return state


async def execute_steps(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 执行步骤（异步顺序执行）
    """
    logger.info("🚀 ========== 节点: 执行步骤 ===========")

    query = state["query"]
    template_id = state["template_id"]
    session_id = state["session_id"]

    # 从 config 获取所需资源
    db: AsyncSession = config.get("configurable", {}).get("db")
    es_client = config.get("configurable", {}).get("es")
    es_index: str = config.get("configurable", {}).get(
        "es_index", "dochive_documents")
    max_read_documents = config.get(
        "configurable", {}).get("max_read_documents", 10)
    rag_max_length = config.get(
        "configurable", {}).get("rag_max_length", 10000)

    # helper: 实际调用工具/智能体实现 - 使用新版工具系统
    async def _dispatch_to_impl(step_type: str, step_name: str):
        """
        通用的工具/智能体调度器
        - 工具调用：使用新版 execute_tool 统一处理
        - 智能体调用：直接调用智能体函数
        """
        if step_type == "tool":
            # 创建工具上下文
            tool_ctx = ToolContext(
                db=db,
                es_client=es_client,
                es_index=es_index,
                template_id=template_id,
                session_id=session_id,
            )

            # 准备工具参数
            arguments = {"template_id": template_id}

            # 特殊处理：从 state 中获取中间数据
            if step_name in [
                "get_document_contents",
                "skim_documents",
                "read_documents",
            ]:
                arguments["document_ids"] = state["intermediate_data"].get(
                    "document_ids", []
                )
                if step_name == "read_documents":
                    arguments["max_documents"] = max_read_documents
            elif step_name == "analyze_documents":
                # analyze_documents 参数
                arguments["query"] = query
                arguments["documents"] = state["intermediate_data"].get(
                    "documents", [])
                arguments["max_context_length"] = rag_max_length
            elif step_name == "search_documents_by_classification":
                arguments["class_code"] = None  # 默认返回所有文档

            # 调用新版工具执行器
            return await execute_tool(step_name, arguments, tool_ctx)

        elif step_type == "agent":
            # 智能体调用：直接调用智能体函数
            if step_name == "retrieval_agent":
                return await retrieve_documents_v2(
                    query=query,
                    template_id=template_id,
                    session_id=session_id,
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                    top_k=20,
                    enable_deduplication=True,
                )
            elif step_name == "qa_agent":
                documents = state["intermediate_data"].get("documents", [])
                return await generate_answer_v2(
                    query=query,
                    documents=documents,
                    db=db,
                    max_context_length=rag_max_length,
                )
            else:
                raise RuntimeError(f"未知的智能体: {step_name}")
        else:
            raise RuntimeError(f"未知的 step_type: {step_type}")

    # 主执行逻辑：逐个异步执行步骤
    plan: List[Dict[str, Any]] = state.get("execution_plan", [])
    try:
        for i, step in enumerate(plan):
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name}")

            try:
                # 执行步骤
                result = await _dispatch_to_impl(step_type, step_name)

                # 记录结果
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": result,
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 特殊处理：更新中间数据
                if result.get("success"):
                    if step_type == "agent" and step_name == "retrieval_agent":
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", []
                        )
                        state["documents"] = result.get("documents", [])
                    elif (
                        step_type == "tool"
                        and step_name == "search_documents_by_classification"
                    ):
                        state["intermediate_data"]["document_ids"] = result.get(
                            "document_ids", []
                        )
                    elif step_type == "tool" and step_name in [
                        "get_document_contents",
                        "skim_documents",
                        "read_documents",
                    ]:
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", []
                        )

                logger.info(f"✅ 步骤{i+1}完成: {step_name}")

            except Exception as e:
                import traceback

                logger.error(f"❌ 步骤{i+1}失败: {step_name}, 错误: {e}")
                logger.error(traceback.format_exc())

                # 记录错误
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": {"success": False, "error": str(e)},
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 继续执行后续步骤（可根据需要调整策略）

        state["success"] = True
        logger.info("✅ 所有步骤执行完成")

    except Exception as e:
        logger.error(f"❌ 执行步骤失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        state["error"] = str(e)
        state["success"] = False

    return state


async def finalize_answer(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 生成最终答案

    整合执行结果，生成最终答案。
    """
    logger.info("📝 ========== 节点: 生成最终答案 ===========")

    query = state["query"]
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    try:
        # 如果已经有答案（qa_agent生成的），直接返回
        if state["final_answer"]:
            logger.info("✅ 已有最终答案，跳过生成")
            state["success"] = True
            return state

        # 根据执行模式生成答案
        if state["execution_pattern"] == "llm_direct":
            # LLM直接回答的情况，已经有答案
            state["success"] = True
            return state

        elif state["execution_pattern"] == "agent_only":
            # 仅检索模式
            if state["documents"]:
                state["final_answer"] = None  # 仅检索，不生成答案
                logger.info("📚 仅检索模式，不生成答案")
            else:
                state["final_answer"] = "抱歉，没有找到相关文档。"
                logger.warning("⚠️ 未找到文档")
            state["success"] = True
            return state

        # 其他模式：根据所有步骤结果生成详细答案
        logger.info("🤖 根据执行结果生成详细答案")

        llm_client = get_llm_client()

        # 构建执行过程描述
        execution_summary = []
        execution_summary.append(f"用户问题：{query}\n")
        execution_summary.append(f"执行模式：{state['execution_pattern']}")
        execution_summary.append(f"执行推理：{state['reasoning']}\n")

        execution_summary.append("执行步骤及结果：")

        # 添加工具执行结果
        for i, tool_result in enumerate(state["tool_results"]):
            step_num = tool_result.get("step", i + 1)
            name = tool_result.get("name", "未知工具")
            desc = tool_result.get("description", "")
            result = tool_result.get("result", {})

            execution_summary.append(f"\n步骤{step_num}：{desc} (工具: {name})")

            if result.get("success"):
                # 根据不同工具类型格式化结果
                if name == "get_template_statistics":
                    # get_template_statistics 直接返回数据，不是嵌套在statistics里
                    total_docs = result.get("total_documents", 0)
                    execution_summary.append(f"  - 文档总数：{total_docs}")

                    # 显示分类分布
                    class_dist = result.get("class_code_distribution", [])
                    if class_dist:
                        execution_summary.append(
                            f"  - 分类分布：{len(class_dist)}个分类"
                        )
                        for item in class_dist[:3]:  # 只显示前3个
                            execution_summary.append(
                                f"    * {item.get('class_code', '未知')}: {item.get('count', 0)}篇"
                            )
                elif name == "search_documents_by_classification":
                    doc_ids = result.get("document_ids", [])
                    execution_summary.append(f"  - 找到{len(doc_ids)}篇文档")
                elif name in [
                    "get_document_contents",
                    "skim_documents",
                    "read_documents",
                ]:
                    docs = result.get("documents", [])
                    execution_summary.append(f"  - 读取{len(docs)}篇文档")
                    for doc in docs[:3]:  # 只显示前3篇
                        execution_summary.append(
                            f"    * {doc.get('title', '未命名')}")
                elif name == "analyze_documents":
                    analysis = result.get("analysis", "")
                    if analysis:
                        execution_summary.append(
                            f"  - 分析结果：{analysis[:200]}...")
                else:
                    # 通用处理
                    execution_summary.append(f"  - 执行成功")
            else:
                execution_summary.append(
                    f"  - 执行失败：{result.get('error', '未知错误')}"
                )

        # 添加智能体执行结果
        for i, agent_result in enumerate(state["agent_results"]):
            step_num = agent_result.get(
                "step", len(state["tool_results"]) + i + 1)
            name = agent_result.get("name", "未知智能体")
            desc = agent_result.get("description", "")
            result = agent_result.get("result", {})

            execution_summary.append(f"\n步骤{step_num}：{desc} (智能体: {name})")

            if result.get("success"):
                if name == "retrieval_agent":
                    docs = result.get("documents", [])
                    execution_summary.append(f"  - 检索到{len(docs)}篇相关文档")
                    for doc in docs[:5]:  # 显示前5篇
                        execution_summary.append(
                            f"    * {doc.get('title', '未命名')} (相关度: {doc.get('score', 0):.2f})"
                        )
                elif name == "qa_agent":
                    answer = result.get("answer", "")
                    execution_summary.append(f"  - 生成答案：{answer[:200]}...")
                else:
                    execution_summary.append(f"  - 执行成功")
            else:
                execution_summary.append(
                    f"  - 执行失败：{result.get('error', '未知错误')}"
                )

        execution_context = "\n".join(execution_summary)

        # 调用LLM生成最终答案
        system_prompt = """你是一个专业的智能助手，负责根据执行过程和结果生成详细的答案。

要求：
1. 按照执行步骤顺序组织答案
2. 每个步骤说明：做了什么、得到了什么结果
3. 用清晰的格式（标题、列表等）呈现
4. 最后总结回答用户的问题
5. 使用Markdown格式

注意：
- 不要编造信息，只使用执行结果中的实际内容
- 如果某步骤失败，说明原因
- 语气友好、专业
"""

        user_prompt = f"""请根据以下执行过程生成详细答案：

{execution_context}

请生成一个清晰、详细、有条理的答案。
"""

        final_answer = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )

        state["final_answer"] = final_answer
        state["success"] = True
        logger.info("✅ 最终答案生成完成")

    except Exception as e:
        logger.error(f"❌ 生成最终答案失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        state["error"] = str(e)
        state["success"] = False

    return state


# ==================== 简单三步执行函数（不使用LangGraph） ====================


async def execute_master_router(
    query: str,
    template_id: int,
    db: AsyncSession,
    es_client,
    es_index: str = "dochive_documents",
    session_id: Optional[str] = None,
    user_id: Optional[int] = None,
    user_input: Optional[Any] = None,
):
    """
    主路由器执行函数：支持多轮对话和用户干预

    核心改进：
    1. 每次用户输入都创建全新的state对象
    2. 会话管理器只保存历史消息
    3. 生成答案时，如果需要历史上下文，从会话中获取并用大模型过滤

    Args:
        query: 用户查询
        template_id: 模板ID
        db: 数据库会话
        es_client: ES客户端
        es_index: ES索引
        session_id: 会话ID（由前端传入，如果为None则自动生成）
        user_id: 用户ID
        user_input: 用户输入（当会话处于waiting_input状态时）

    Yields:
        dict: 每一步的执行结果
            - type: 'plan' | 'step_result' | 'user_input_request' | 'final'
            - data: 具体数据
    """
    import uuid

    # 获取会话管理器
    conversation_manager = get_conversation_manager()

    # 如果没有session_id，生成新的
    if session_id is None:
        session_id = str(uuid.uuid4())
        logger.info(f"🆕 生成新会话: {session_id}")

    # 检查会话是否存在
    session_data = conversation_manager.get_session(session_id)

    if session_data is None:
        # 创建新会话
        session_data = conversation_manager.create_session(
            session_id=session_id,
            template_id=template_id,
            initial_query=query,
            user_id=user_id,
        )
        logger.info(f"✨ 创建新会话: {session_id}")
    else:
        logger.info(f"🔄 恢复现有会话: {session_id}")

        # 添加用户消息到对话历史
        conversation_manager.add_message(
            session_id=session_id,
            role="user",
            content=query,
        )

    # ⭐ 关键：每次都创建全新的state对象，不依赖会话中的旧state
    state: ExecutionState = {
        "query": query,
        "template_id": template_id,
        "session_id": session_id,
        "execution_pattern": "",
        "reasoning": "",
        "execution_plan": [],
        "tool_results": [],
        "agent_results": [],
        "intermediate_data": {},
        "final_answer": None,
        "documents": [],
        "success": False,
        "error": None,
    }

    # ⭐ 用户意图识别（仅在有历史对话时）
    messages = session_data.get("messages", [])
    if len(messages) > 1:  # 有历史对话（不包括当前query）
        logger.info("🔍 检测到历史对话，开始用户意图识别")

        intent_result = await analyze_user_intent(
            query=query,
            conversation_history=messages,
            db=db,
        )

        # response_to_hint / new_question / follow_up
        intent_type = intent_result.get("intent_type")
        intent_reasoning = intent_result.get("reasoning", "")

        logger.info(f"💡 用户意图: {intent_type}, 原因: {intent_reasoning}")

        if intent_type == "response_to_hint":
            # 用户回应了hint提示（如"继续"、"用前20篇"等）
            logger.info("✅ 用户选择继续使用当前结果")

            # 从会话的state中获取上次检索的文档
            previous_documents = session_data.get(
                "state", {}).get("documents", [])

            if previous_documents:
                logger.info(f"📚 使用上次检索的{len(previous_documents)}篇文档继续执行")

                # 将文档放入state，然后直接执行QA生成
                state["documents"] = previous_documents
                state["intermediate_data"]["documents"] = previous_documents
                state["execution_pattern"] = "retrieval_qa"  # 设置执行模式
                state["execution_plan"] = [
                    {
                        "type": "agent",
                        "name": "qa_agent",
                        "description": "基于检索结果生成答案",
                    }
                ]

                # 不再需要规划步骤，直接执行QA
                logger.info("🔄 跳过规划步骤，直接执行QA生成")
            else:
                # 如果没有上次的文档，则当作新问题处理
                logger.warning("⚠️ 未找到上次检索的文档，将当作新问题处理")
                intent_type = "new_question"

        elif intent_type == "follow_up":
            # 追问或延续话题，需要结合历史上下文
            logger.info("🔗 检测到追问，获取历史上下文进行归并")

            # 从历史消息中获取相关上下文
            relevant_context = await filter_relevant_context(
                query=query,
                conversation_history=messages,
                db=db,
            )

            # 将相关上下文合并到query中
            if relevant_context:
                enhanced_query = (
                    f"【历史上下文】\n{relevant_context}\n\n【当前问题】\n{query}"
                )
                state["query"] = enhanced_query
                logger.info(f"📝 增强后的查询: {enhanced_query[:100]}...")

        # intent_type == "new_question" 时，直接使用原query，继续执行

    logger.info(f"🆕 创建新的执行状态，query={state['query'][:100]}...")

    # ========== 第一步：规划 ==========
    if not state.get("execution_plan"):
        logger.info("🧠 ========== 第一步：规划 ===========")

        config = {"configurable": {
            "db": db, "es": es_client, "es_index": es_index}}
        state = await plan_execution(state, config)

        # Yield 执行计划
        yield {
            "type": "plan",
            "data": {
                "session_id": session_id,
                "execution_pattern": state["execution_pattern"],
                "execution_plan": state["execution_plan"],
                "reasoning": state["reasoning"],
            },
        }

    # ========== 第二步：执行 ==========
    if state["execution_pattern"] != "llm_direct" and not state.get("final_answer"):
        logger.info("🛠️ ========== 第二步：执行 ===========")

        # 执行步骤，支持用户干预
        async for result in execute_steps_with_intervention(
            session_id=session_id,
            state=state,
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            query=query,
        ):
            yield result

    # ========== 第三步：总结 ==========
    logger.info("📝 ========== 第三步：总结 ===========")

    config = {"configurable": {"db": db, "es": es_client, "es_index": es_index}}
    state = await finalize_answer(state, config)

    # 添加AI回复到对话历史
    if state.get("final_answer"):
        conversation_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=state["final_answer"],
        )

    # 标记会话完成
    conversation_manager.complete_session(
        session_id, state.get("final_answer"))

    # Yield 最终结果
    yield {
        "type": "final",
        "data": {
            "session_id": session_id,
            "final_answer": state["final_answer"],
            "documents": state["documents"],
            "success": state["success"],
            "error": state.get("error"),
        },
    }


async def execute_steps_with_intervention(
    session_id: str,
    state: ExecutionState,
    db: AsyncSession,
    es_client,
    es_index: str,
    template_id: int,
    query: str,  # 这个参数不再需要，使用state中的query
):
    """
    执行步骤，支持用户干预

    用户干预场景：
    1. 检索结果过多（>20篇）：请求用户选择或精化查询
    2. 检索结果过少（<3篇）：提示用户重新输入问题
    3. 文档过多需要阅读：请求用户选择重点文档
    """
    from backend.core.conversation_manager import get_conversation_manager

    conversation_manager = get_conversation_manager()

    max_read_documents = 10
    rag_max_length = 10000

    # 使用state中的query
    current_query = state["query"]

    # 逐步执行（不再使用current_step，每次都从头开始）
    for i, step in enumerate(state["execution_plan"]):
        step_type = step.get("type")
        step_name = step.get("name")
        step_desc = step.get("description", "")

        logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name}")

        try:
            result = None

            # 执行工具或智能体
            if step_type == "tool":
                # 创建工具上下文
                tool_ctx = ToolContext(
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                    template_id=template_id,
                    session_id=session_id,
                )

                arguments = {"template_id": template_id}

                if step_name in [
                    "get_document_contents",
                    "skim_documents",
                    "read_documents",
                ]:
                    arguments["document_ids"] = state["intermediate_data"].get(
                        "document_ids", []
                    )
                    if step_name == "read_documents":
                        arguments["max_documents"] = max_read_documents
                elif step_name == "analyze_documents":
                    arguments["query"] = current_query
                    arguments["documents"] = state["intermediate_data"].get(
                        "documents", []
                    )
                    arguments["max_context_length"] = rag_max_length
                elif step_name == "search_documents_by_classification":
                    arguments["class_code"] = None

                # 调用新版工具执行器
                result = await execute_tool(step_name, arguments, tool_ctx)

            elif step_type == "agent":
                if step_name == "retrieval_agent":
                    result = await retrieve_documents_v2(
                        query=current_query,  # 使用current_query
                        template_id=template_id,
                        session_id=session_id,
                        db=db,
                        es_client=es_client,
                        es_index=es_index,
                        top_k=20,
                        enable_deduplication=True,
                    )
                elif step_name == "qa_agent":
                    documents = state["intermediate_data"].get("documents", [])
                    result = await generate_answer_v2(
                        query=current_query,  # 使用current_query
                        documents=documents,
                        db=db,
                        max_context_length=rag_max_length,
                    )
                else:
                    raise RuntimeError(f"未知的智能体: {step_name}")
            else:
                raise RuntimeError(f"未知的 step_type: {step_type}")

            # 记录结果
            result_entry = {
                "step": i + 1,
                "name": step_name,
                "description": step_desc,
                "result": result,
            }

            if step_type == "tool":
                state["tool_results"].append(result_entry)
            else:
                state["agent_results"].append(result_entry)

            # 更新中间数据
            if result.get("success"):
                if step_type == "agent" and step_name == "retrieval_agent":
                    documents = result.get("documents", [])
                    state["intermediate_data"]["documents"] = documents
                    state["documents"] = documents

                    # ⭐ 检索结果检查：过多或过少时，在对话中提示用户
                    doc_count = len(documents)

                    if doc_count > 20:
                        # 结果过多，生成提示消息并直接返回
                        logger.info(f"⚠️ 检索到{doc_count}篇文档，过多，生成提示消息")

                        hint_message = f"检索到{doc_count}篇文档，结果过多。\n\n您可以：\n1. 输入更具体的问题来精化查询\n2. 直接让我使用前20篇文档继续回答\n\n请告诉我您的选择。"

                        # 直接设置为最终答案，不再yield hint事件
                        state["final_answer"] = hint_message
                        state["documents"] = documents[:20]
                        state["success"] = True

                        # ⭐ 保存文档到会话中state，供下次用户选择继续时使用
                        conversation_manager.update_state(
                            session_id=session_id,
                            state_updates={"documents": documents[:20]},
                        )

                        # 不继续执行后续步骤，直接break到总结
                        break

                    # 如果检索结果正常（≤20篇），直接继续执行，不需要用户确认

                elif (
                    step_type == "tool"
                    and step_name == "search_documents_by_classification"
                ):
                    state["intermediate_data"]["document_ids"] = result.get(
                        "document_ids", []
                    )
                elif step_type == "tool" and step_name in [
                    "get_document_contents",
                    "skim_documents",
                    "read_documents",
                ]:
                    state["intermediate_data"]["documents"] = result.get(
                        "documents", []
                    )
                elif step_type == "agent" and step_name == "qa_agent":
                    state["final_answer"] = result.get("answer")

            logger.info(f"✅ 步骤{i+1}完成: {step_name}")

            # Yield 每一步的结果
            yield {
                "type": "step_result",
                "data": {
                    "session_id": session_id,
                    "step": i + 1,
                    "step_type": step_type,
                    "step_name": step_name,
                    "description": step_desc,
                    "result": result,
                    "documents": (
                        state.get("documents", []
                                  ) if step_type == "agent" else None
                    ),
                },
            }

        except Exception as e:
            import traceback

            logger.error(f"❌ 步骤{i+1}失败: {step_name}, 错误: {e}")
            logger.error(traceback.format_exc())

            result_entry = {
                "step": i + 1,
                "name": step_name,
                "description": step_desc,
                "result": {"success": False, "error": str(e)},
            }

            if step_type == "tool":
                state["tool_results"].append(result_entry)
            else:
                state["agent_results"].append(result_entry)

            yield {
                "type": "step_result",
                "data": {
                    "session_id": session_id,
                    "step": i + 1,
                    "step_type": step_type,
                    "step_name": step_name,
                    "description": step_desc,
                    "result": {"success": False, "error": str(e)},
                },
            }


# ==================== 决策函数 ====================


def should_execute_steps(state: ExecutionState) -> str:
    """
    决策函数：是否需要执行步骤

    Returns:
        'execute': 需要执行步骤
        'finalize': LLM直接回答，直接到终点
    """
    if state["execution_pattern"] == "llm_direct":
        logger.info("🔀 决策: LLM直接回答 -> 跳过执行")
        return "finalize"
    else:
        logger.info("🔀 决策: 需要执行步骤 -> execute")
        return "execute"
