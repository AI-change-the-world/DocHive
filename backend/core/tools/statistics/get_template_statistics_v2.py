"""
获取模板统计信息工具 V2

使用 @tool 装饰器重构
"""

from datetime import datetime
from typing import Any, Dict

from loguru import logger
from sqlalchemy import and_, func, select

from auto_agent import func_tool
from core.tools.base import ToolContext


def _to_iso(t):
    """将时间戳转换为ISO格式字符串"""
    if t is None:
        return None

    if isinstance(t, int):
        if t > 1e12:
            t = datetime.fromtimestamp(t / 1000)
        else:
            t = datetime.fromtimestamp(t)
        return t.isoformat()

    if hasattr(t, "isoformat"):
        return t.isoformat()

    return None


@func_tool(
    name="get_template_statistics",
    context_param="ctx",
    description="获取指定模板的统计信息，包括文档总数、分类分布、文档类型分布、最近上传的文档等",
    parameters=[
        {"name": "template_id", "type": "integer", "description": "模板ID", "required": True},
    ],
    category="statistics",
    tags=["统计", "模板", "概览"],
)
async def get_template_statistics(
    ctx: ToolContext,
    template_id: int,
) -> Dict[str, Any]:
    """
    获取模板统计信息

    Args:
        ctx: 工具上下文
        template_id: 模板ID

    Returns:
        统计信息字典
    """
    from models.database_models import (
        ClassTemplate,
        Document,
        DocumentType,
        TemplateDocumentMapping,
    )

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
        }

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

        # 2. 获取文档总数
        total_docs_result = await db.execute(
            select(func.count(TemplateDocumentMapping.document_id)).where(
                TemplateDocumentMapping.template_id == template_id
            )
        )
        total_docs = total_docs_result.scalar() or 0

        # 3. 获取分类编码分布
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

        # 4. 获取文档类型分布
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

        # 5. 获取最近上传的文档
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
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }
