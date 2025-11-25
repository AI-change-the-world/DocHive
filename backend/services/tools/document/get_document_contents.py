"""
获取文档完整内容工具
"""

from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def get_document_contents(
    document_ids: List[int],
    db: AsyncSession,
    include_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    获取文档完整内容

    Args:
        document_ids: 文档ID列表
        db: 数据库会话
        include_fields: 需要包含的字段列表（默认: id, title, content_text, ai_summary）

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 文档完整内容
            "count": int
        }
    """
    try:
        from sqlalchemy import select
        from models.database_models import Document

        if not include_fields:
            include_fields = ["id", "title", "content_text", "ai_summary"]

        # 构建查询，只选择需要的字段
        columns = [getattr(Document, field)
                   for field in include_fields if hasattr(Document, field)]

        query = select(*columns).where(Document.id.in_(document_ids))

        result = await db.execute(query)
        documents = []

        for row in result.all():
            doc_dict = {}
            for i, field in enumerate(include_fields):
                if hasattr(Document, field):
                    doc_dict[field] = row[i]
            documents.append(doc_dict)

        logger.info(f"✅ 获取文档内容完成: {len(documents)} 篇文档")

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
