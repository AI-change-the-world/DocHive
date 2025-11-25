"""
列出所有模板工具
"""

from typing import Any, Dict
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import (
    ClassTemplate,
    TemplateDocumentMapping,
)


async def list_all_templates(db: AsyncSession) -> Dict[str, Any]:
    """
    列出所有可用的模板

    Args:
        db: 数据库会话

    Returns:
        模板列表
    """
    try:
        result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.is_active == True)
        )
        templates = result.scalars().all()

        templates_info = []
        for template in templates:
            # 获取该模板下的文档数量
            count_result = await db.execute(
                select(func.count(TemplateDocumentMapping.document_id)).where(
                    TemplateDocumentMapping.template_id == template.id
                )
            )
            doc_count = count_result.scalar() or 0

            templates_info.append(
                {
                    "template_id": template.id,
                    "template_name": template.name,
                    "description": template.description,
                    "version": template.version,
                    "document_count": doc_count,
                }
            )

        return {
            "success": True,
            "total_templates": len(templates_info),
            "templates": templates_info,
        }

    except Exception as e:
        logger.error(f"列出模板失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }
