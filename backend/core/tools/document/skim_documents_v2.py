"""
粗读文档工具 V2 - 只获取标题和摘要

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import select

from core.tools.base import ToolContext, tool


@tool(
    name="skim_documents",
    description="粗读文档：只获取标题和AI摘要。适合快速浏览、统计数量、了解大致内容的场景。优势：速度快、节省Token、可处理大量文档。",
    parameters={
        "document_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "文档ID列表",
        }
    },
    required=["document_ids"],
    category="document",
    tags=["文档", "粗读", "摘要"],
)
async def skim_documents(
    ctx: ToolContext,
    document_ids: List[int],
) -> Dict[str, Any]:
    """
    粗读文档工具 - 只获取标题和摘要

    Args:
        ctx: 工具上下文
        document_ids: 文档ID列表

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 只包含 id, title, ai_summary
            "count": int
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
        }

    if not document_ids:
        return {
            "success": True,
            "documents": [],
            "count": 0,
        }

    try:
        # 只查询 id, title, ai_summary
        stmt = select(Document.id, Document.title, Document.ai_summary).where(
            Document.id.in_(document_ids)
        )

        result = await db.execute(stmt)
        rows = result.all()

        documents = [
            {
                "id": row.id,
                "title": row.title,
                "ai_summary": row.ai_summary or "",
            }
            for row in rows
        ]

        logger.info(f"✅ 粗读文档完成: {len(documents)} 篇")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
        }

    except Exception as e:
        logger.error(f"❌ 粗读文档失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
        }
