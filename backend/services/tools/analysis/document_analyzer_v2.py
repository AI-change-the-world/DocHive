"""
文档分析工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List

from loguru import logger

from services.tools.base import ToolContext, tool


@tool(
    name="analyze_documents",
    description="智能分析文档内容，根据文档数量自动选择批量分析或逐篇分析策略。适用于需要总结、归纳、对比文档内容的场景。",
    parameters={
        "query": {"type": "string", "description": "用户的分析请求"},
        "documents": {
            "type": "array",
            "items": {"type": "object"},
            "description": "待分析的文档列表",
        },
        "max_context_length": {
            "type": "integer",
            "description": "最大上下文长度，默认10000",
            "default": 10000,
        },
    },
    required=["query", "documents"],
    category="analysis",
    tags=["分析", "总结", "归纳"],
)
async def analyze_documents(
    ctx: ToolContext,
    query: str,
    documents: List[Dict[str, Any]],
    max_context_length: int = 10000,
) -> Dict[str, Any]:
    """
    智能分析文档

    Args:
        ctx: 工具上下文
        query: 用户的分析请求
        documents: 待分析的文档列表
        max_context_length: 最大上下文长度

    Returns:
        {
            "success": bool,
            "analysis": str,
            "strategy": str  # "batch" 或 "individual"
        }
    """
    from utils.llm_client import get_llm_client

    db = ctx.db

    if not documents:
        return {
            "success": True,
            "analysis": "没有文档需要分析。",
            "strategy": "none",
        }

    try:
        llm_client = get_llm_client()

        # 根据文档数量选择策略
        if len(documents) <= 3:
            # 逐篇详细分析
            strategy = "individual"
            analyses = []

            for i, doc in enumerate(documents):
                title = doc.get("title", f"文档{i+1}")
                content = doc.get("content", doc.get("ai_summary", ""))

                # 截断内容
                if len(content) > max_context_length // len(documents):
                    content = content[: max_context_length // len(documents)] + "..."

                prompt = f"""请分析以下文档内容：

【文档标题】{title}

【文档内容】
{content}

【分析要求】
{query}

请给出详细分析："""

                response = await llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": "你是一个专业的文档分析助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    db=db,
                )

                analyses.append(f"### {title}\n\n{response}")

            analysis = "\n\n---\n\n".join(analyses)

        else:
            # 批量概览分析
            strategy = "batch"

            # 构建文档摘要
            summaries = []
            current_length = 0

            for i, doc in enumerate(documents):
                title = doc.get("title", f"文档{i+1}")
                summary = doc.get("ai_summary", doc.get("content", "")[:200])

                doc_text = f"{i+1}. **{title}**\n   {summary}\n"

                if current_length + len(doc_text) > max_context_length:
                    break

                summaries.append(doc_text)
                current_length += len(doc_text)

            summaries_text = "\n".join(summaries)

            prompt = f"""请分析以下 {len(documents)} 篇文档：

【文档列表】
{summaries_text}

【分析要求】
{query}

请给出综合分析："""

            analysis = await llm_client.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的文档分析助手，擅长总结和归纳多篇文档。",
                    },
                    {"role": "user", "content": prompt},
                ],
                db=db,
            )

        logger.info(f"✅ 文档分析完成，策略: {strategy}")

        return {
            "success": True,
            "analysis": analysis,
            "strategy": strategy,
        }

    except Exception as e:
        logger.error(f"❌ 文档分析失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "analysis": "",
            "strategy": "error",
        }
