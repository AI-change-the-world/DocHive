"""
精读文档工具 V2 - 获取完整正文内容

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List
from loguru import logger
from sqlalchemy import select

from services.tools.base import tool, ToolContext


@tool(
    name="read_documents",
    description="精读文档：获取完整正文内容。适合需要深入理解、提取详细信息的场景。优势：信息完整、细节准确。限制：速度较慢、消耗更多Token、不适合大量文档。",
    parameters={
        "document_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "文档ID列表"
        },
        "max_documents": {
            "type": "integer",
            "description": "最多读取文档数，防止超过LLM上下文限制，默认10",
            "default": 10
        }
    },
    required=["document_ids"],
    category="document",
    tags=["文档", "精读", "全文"]
)
async def read_documents(
    ctx: ToolContext,
    document_ids: List[int],
    max_documents: int = 10,
) -> Dict[str, Any]:
    """
    精读文档工具 - 获取完整正文内容

    Args:
        ctx: 工具上下文
        document_ids: 文档ID列表
        max_documents: 最多读取文档数

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 包含 id, title, content, ai_summary
            "count": int,
            "truncated": bool  # 是否被截断
        }
    """
    from models.database_models import Document

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
            "documents": [],
            "count": 0,
            "truncated": False,
        }

    if not document_ids:
        return {
            "success": True,
            "documents": [],
            "count": 0,
            "truncated": False,
        }

    # 截断文档ID列表
    truncated = len(document_ids) > max_documents
    if truncated:
        logger.warning(f"⚠️ 文档数量 {len(document_ids)} 超过限制 {max_documents}，将截断")
        document_ids = document_ids[:max_documents]

    try:
        # 查询完整文档内容
        stmt = select(Document).where(Document.id.in_(document_ids))
        result = await db.execute(stmt)
        docs = result.scalars().all()

        documents = [
            {
                "id": doc.id,
                "title": doc.title,
                "content": doc.content_text or "",
                "ai_summary": doc.ai_summary or "",
            }
            for doc in docs
        ]

        logger.info(f"✅ 精读文档完成: {len(documents)} 篇")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
            "truncated": truncated,
        }

    except Exception as e:
        logger.error(f"❌ 精读文档失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
            "truncated": False,
        }
