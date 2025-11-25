"""
问答智能体 V2 - 基于检索结果生成答案

接收检索智能体返回的文档，生成高质量答案
"""

from typing import Any, Dict, List, Optional, TypedDict
from loguru import logger
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from utils.llm_client import get_llm_client


# ==================== 问答智能体状态定义 ====================


class QAAgentState(TypedDict):
    """
    问答智能体状态机

    工作流程：
    1. 筛选文档 -> 根据摘要快速筛选相关文档
    2. 生成答案 -> 基于筛选后的文档生成答案
    """

    # === 必需输入 ===
    query: str  # 用户问题
    documents: List[Dict[str, Any]]  # 检索智能体返回的文档列表

    # === 配置参数 ===
    max_context_length: int  # 最大上下文长度

    # === 步骤1: 筛选文档 ===
    filtered_documents: List[Dict[str, Any]]  # 筛选后的文档

    # === 步骤2: 生成答案 ===
    answer: str  # 最终答案


# ==================== 节点1: 筛选文档 ====================


async def filter_relevant_documents(
    state: QAAgentState, config: RunnableConfig
) -> QAAgentState:
    """
    节点1: 筛选文档

    使用LLM快速判断文档与查询的相关性，筛选出最相关的文档
    """
    logger.info("========== 问答智能体 - 节点1: 筛选文档 ==========")

    db: AsyncSession = config.get("configurable", {}).get("db")

    query = state["query"]
    documents = state.get("documents", [])

    if not documents or len(documents) <= 3:
        # 文档数量少，直接使用全部
        logger.info("📌 文档数量≤3，跳过筛选")
        state["filtered_documents"] = documents
        return state

    logger.info(f"📋 开始筛选，原始文档数: {len(documents)}")

    llm_client = get_llm_client()

    # 构造摘要列表
    summaries = []
    for i, doc in enumerate(documents):
        doc_id = doc.get("id")
        title = doc.get("title", "未知标题")
        summary = doc.get("ai_summary") or doc.get("content", "")[:200]

        summaries.append({
            "index": i,
            "document_id": doc_id,
            "title": title,
            "summary": summary,
        })

    # 构建提示词
    summaries_text = "\n".join(
        f"{i+1}. [索引{s['index']}] {s['title']}\n   摘要: {s['summary']}"
        for i, s in enumerate(summaries)
    )

    prompt = f"""你是一个文档相关性判断助手。请根据用户的问题和文档摘要，快速判断哪些文档直接相关。

【用户问题】
{query}

【文档摘要列表】
{summaries_text}

【判断标准】
1. **直接相关**：文档内容能够直接回答用户问题，或包含用户问题所需的关键信息
2. **不相关**：文档内容与问题主题不同，或者只是边缘相关

【输出要求】
请返回JSON格式：
{{
    "relevant_indices": [相关文档的索引列表],
    "reasoning": "简要说明为什么这些文档相关"
}}

只返回JSON，不要其他内容。
"""

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": "你是一个文档相关性判断助手"},
                {"role": "user", "content": prompt},
            ],
            db=db,
        )

        relevant_indices = response.get("relevant_indices", [])
        reasoning = response.get("reasoning", "")

        logger.info(f"📊 筛选结果: {reasoning}")

        # 根据索引筛选文档
        filtered_documents = [
            documents[idx] for idx in relevant_indices
            if 0 <= idx < len(documents)
        ]

        if not filtered_documents:
            # 如果没有筛选出任何文档，保留前3个
            logger.warning("⚠️ 筛选后无文档，保留前3个")
            filtered_documents = documents[:3]

        state["filtered_documents"] = filtered_documents
        logger.info(
            f"✅ 筛选完成: {len(documents)} -> {len(filtered_documents)} 篇文档")

    except Exception as e:
        logger.error(f"❌ 筛选失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 降级：保留前5个文档
        state["filtered_documents"] = documents[:5]

    return state


# ==================== 节点2: 生成答案 ====================


async def generate_answer_from_docs(
    state: QAAgentState, config: RunnableConfig
) -> QAAgentState:
    """
    节点2: 生成答案

    基于筛选后的文档，生成自然语言答案
    """
    logger.info("========== 问答智能体 - 节点2: 生成答案 ==========")

    db: AsyncSession = config.get("configurable", {}).get("db")

    query = state["query"]
    filtered_documents = state.get("filtered_documents", [])
    max_context_length = state.get("max_context_length", 10000)

    if not filtered_documents:
        logger.warning("⚠️ 无相关文档，返回默认答案")
        state["answer"] = "抱歉，我没有找到相关的文档来回答您的问题。"
        return state

    llm_client = get_llm_client()

    # 构建上下文
    context_parts = []
    current_length = 0

    for i, doc in enumerate(filtered_documents):
        title = doc.get("title", "未知文档")
        content = doc.get("content", "")

        doc_text = f"【文档{i+1}: {title}】\n{content}\n\n"
        doc_length = len(doc_text)

        if current_length + doc_length > max_context_length:
            # 截断
            remaining = max_context_length - current_length
            if remaining > 100:
                doc_text = doc_text[:remaining] + "...\n\n"
                context_parts.append(doc_text)
            break

        context_parts.append(doc_text)
        current_length += doc_length

    context = "".join(context_parts)

    # 构建提示词
    prompt = f"""你是一个专业的问答助手。基于提供的文档内容，回答用户的问题。

【用户问题】
{query}

【相关文档】
{context}

【回答要求】
1. 直接、准确地回答问题
2. 答案必须基于文档内容，不要编造
3. 如果文档中没有相关信息，明确说明
4. 保持简洁，重点突出
5. 使用中文回答

请开始回答：
"""

    try:
        # 调用LLM生成答案
        answer = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": "你是一个专业的问答助手，基于文档内容准确回答问题"},
                {"role": "user", "content": prompt},
            ],
            db=db,
        )

        state["answer"] = answer.strip()
        logger.info(f"✅ 答案生成完成，长度: {len(answer)} 字符")

    except Exception as e:
        logger.error(f"❌ 生成答案失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["answer"] = f"抱歉，生成答案时出现错误: {str(e)}"

    return state


# ==================== 工作流构建 ====================


def build_qa_agent_v2() -> CompiledStateGraph:
    """
    构建问答智能体V2的工作流

    工作流程:
    1. 筛选文档
    2. 生成答案
    """
    workflow = StateGraph(QAAgentState)

    # 添加节点
    workflow.add_node("filter_docs", filter_relevant_documents)
    workflow.add_node("generate_answer", generate_answer_from_docs)

    # 设置入口点
    workflow.set_entry_point("filter_docs")

    # 添加边
    workflow.add_edge("filter_docs", "generate_answer")
    workflow.add_edge("generate_answer", END)

    # 编译
    app = workflow.compile()

    logger.info("✅ 问答智能体V2工作流编译完成")
    logger.info("📊 工作流程: 筛选文档 → 生成答案")

    return app


# 创建全局实例
qa_agent_v2 = build_qa_agent_v2()


# ==================== 便捷调用接口 ====================


async def generate_answer_v2(
    query: str,
    documents: List[Dict[str, Any]],
    db: AsyncSession,
    max_context_length: int = 10000,
) -> Dict[str, Any]:
    """
    生成答案V2 - 便捷调用接口

    Args:
        query: 用户问题
        documents: 文档列表
        db: 数据库会话
        max_context_length: 最大上下文长度

    Returns:
        问答结果
    """
    logger.info(f"💭 问答智能体V2: query='{query}', documents={len(documents)}")

    # 初始化状态
    initial_state: QAAgentState = {
        "query": query,
        "documents": documents,
        "max_context_length": max_context_length,
        # 以下字段在节点中填充
        "filtered_documents": [],
        "answer": "",
    }

    # 执行工作流
    config = {
        "configurable": {
            "db": db,
        }
    }

    try:
        result_state = await qa_agent_v2.ainvoke(initial_state, config)

        answer = result_state.get("answer", "抱歉，无法生成答案。")
        filtered_documents = result_state.get("filtered_documents", [])

        logger.info(f"✅ 问答完成，答案长度: {len(answer)} 字符")

        return {
            "success": True,
            "answer": answer,
            "filtered_documents": filtered_documents,
            "filtered_count": len(filtered_documents),
        }

    except Exception as e:
        logger.error(f"❌ 问答失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "answer": f"抱歉，问答过程出现错误: {str(e)}",
        }
