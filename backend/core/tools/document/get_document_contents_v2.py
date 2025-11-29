"""
获取文档内容工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from core.tools.base import ToolContext, tool


@tool(
    name="get_document_contents",
    description="获取指定文档的完整内容。适用于需要读取具体文档详情的场景。",
    parameters={
        "document_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "文档ID列表",
        },
        "include_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "需要包含的字段，默认: id, title, content, ai_summary",
        },
    },
    required=["document_ids"],
    category="document",
    tags=["文档", "读取", "内容"],
)
async def get_document_contents(
    ctx: ToolContext,
    document_ids: List[int],
    include_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    获取文档内容工具

    Args:
        ctx: 工具上下文
        document_ids: 文档ID列表
        include_fields: 需要包含的字段

    Returns:
        {
            "success": bool,
            "documents": List[Dict],
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

    # 默认字段
    default_fields = ["id", "title", "content", "ai_summary"]
    fields = include_fields or default_fields

    try:
        # 查询文档
        stmt = select(Document).where(Document.id.in_(document_ids))
        result = await db.execute(stmt)
        docs = result.scalars().all()

        documents = []
        for doc in docs:
            doc_dict = {}
            for field in fields:
                if hasattr(doc, field):
                    doc_dict[field] = getattr(doc, field)
            documents.append(doc_dict)

        logger.info(f"✅ 获取文档内容完成: {len(documents)} 篇")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
        }

    except Exception as e:
        logger.error(f"❌ 获取文档内容失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
        }
