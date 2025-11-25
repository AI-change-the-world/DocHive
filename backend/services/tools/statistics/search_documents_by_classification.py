"""
根据分类编码搜索文档工具
"""

from datetime import datetime
from typing import Any, Dict, Optional
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import (
    Document,
    TemplateDocumentMapping,
)


def _to_iso(t):
    """
    将时间戳转换为ISO格式字符串（私有辅助函数）
    """
    if t is None:
        return None

    if isinstance(t, int):
        # 自动判断是秒还是毫秒
        if t > 1e12:  # 毫秒级
            t = datetime.fromtimestamp(t / 1000)
        else:  # 秒级
            t = datetime.fromtimestamp(t)
        return t.isoformat()

    if hasattr(t, "isoformat"):
        return t.isoformat()

    return None


async def search_documents_by_classification(
    db: AsyncSession, template_id: int, class_code: Optional[str] = None
) -> Dict[str, Any]:
    """
    根据分类编码搜索文档

    Args:
        db: 数据库会话
        template_id: 模板ID
        class_code: 分类编码（可选，不提供则返回所有）

    Returns:
        文档ID列表和基本信息（不包含内容，需要后续调用read_documents获取）
    """
    try:
        query = (
            select(
                Document.id,
                Document.title,
                Document.original_filename,
                TemplateDocumentMapping.class_code,
                Document.upload_time,
            )
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(TemplateDocumentMapping.template_id == template_id)
        )

        if class_code:
            query = query.where(
                TemplateDocumentMapping.class_code == class_code)

        query = query.order_by(Document.upload_time.desc()).limit(50)

        result = await db.execute(query)
        documents = [
            {
                "document_id": row.id,
                "title": row.title,
                "filename": row.original_filename,
                "class_code": row.class_code,
                "upload_time": _to_iso(row.upload_time),
            }
            for row in result.all()
        ]

        return {
            "success": True,
            "template_id": template_id,
            "class_code": class_code,
            "total_found": len(documents),
            "documents": documents,
            # 方便后续读取
            "document_ids": [doc["document_id"] for doc in documents],
        }

    except Exception as e:
        logger.error(f"搜索文档失败: {str(e)}")
        return {
            "success": False,
            "error": f"搜索失败: {str(e)}",
        }
