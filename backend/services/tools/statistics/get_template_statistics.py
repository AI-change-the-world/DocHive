"""
获取模板统计信息工具
"""

from datetime import datetime
from typing import Any, Dict
from loguru import logger
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import (
    ClassTemplate,
    Document,
    DocumentType,
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


async def get_template_statistics(db: AsyncSession, template_id: int) -> Dict[str, Any]:
    """
    获取指定模板的统计信息

    包括：文档总数、各分类文档数量、文档类型分布等

    Args:
        db: 数据库会话
        template_id: 模板ID

    Returns:
        统计信息字典
    """
    try:
        # 1. 获取模板信息
        template_result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.id == template_id)
        )
        template = template_result.scalar_one_or_none()

        if not template:
            return {
                "success": False,
                "error": f"模板ID {template_id} 不存在",
            }

        # 2. 获取该模板下的文档总数
        total_docs_result = await db.execute(
            select(func.count(TemplateDocumentMapping.document_id)).where(
                TemplateDocumentMapping.template_id == template_id
            )
        )
        total_docs = total_docs_result.scalar() or 0

        # 3. 获取各分类编码的文档数量分布
        class_code_stats_result = await db.execute(
            select(
                TemplateDocumentMapping.class_code,
                func.count(TemplateDocumentMapping.document_id).label("count"),
            )
            .where(TemplateDocumentMapping.template_id == template_id)
            .group_by(TemplateDocumentMapping.class_code)
        )
        class_code_stats = [
            {"class_code": row.class_code, "count": row.count}
            for row in class_code_stats_result.all()
        ]

        # 4. 获取文档类型分布（如果有）
        doc_type_stats_result = await db.execute(
            select(
                DocumentType.type_name,
                DocumentType.type_code,
                func.count(TemplateDocumentMapping.document_id).label("count"),
            )
            .join(
                TemplateDocumentMapping,
                and_(
                    TemplateDocumentMapping.template_id == template_id,
                    TemplateDocumentMapping.class_code.like(
                        func.concat("%", DocumentType.type_code, "%")
                    ),
                ),
            )
            .where(DocumentType.template_id == template_id)
            .group_by(DocumentType.type_name, DocumentType.type_code)
        )
        doc_type_stats = [
            {
                "type_name": row.type_name,
                "type_code": row.type_code,
                "count": row.count,
            }
            for row in doc_type_stats_result.all()
        ]

        # 5. 获取最近上传的文档（前5个）
        recent_docs_result = await db.execute(
            select(Document.id, Document.title, Document.upload_time)
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(TemplateDocumentMapping.template_id == template_id)
            .order_by(Document.upload_time.desc())
            .limit(5)
        )
        recent_docs = [
            {
                "document_id": row.id,
                "title": row.title,
                "upload_time": _to_iso(row.upload_time),
            }
            for row in recent_docs_result.all()
        ]

        return {
            "success": True,
            "template_name": template.name,
            "template_id": template_id,
            "total_documents": total_docs,
            "class_code_distribution": class_code_stats,
            "document_type_distribution": doc_type_stats,
            "recent_documents": recent_docs,
        }

    except Exception as e:
        logger.error(f"获取模板统计信息失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }
