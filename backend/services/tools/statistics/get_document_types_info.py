"""
获取文档类型信息工具
"""

from typing import Any, Dict
from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import DocumentType


async def get_document_types_info(db: AsyncSession, template_id: int) -> Dict[str, Any]:
    """
    获取模板下的所有文档类型定义

    Args:
        db: 数据库会话
        template_id: 模板ID

    Returns:
        文档类型列表及其字段配置
    """
    try:
        result = await db.execute(
            select(DocumentType).where(
                and_(
                    DocumentType.template_id == template_id,
                    DocumentType.is_active == True,
                )
            )
        )
        doc_types = result.scalars().all()

        types_info = []
        for doc_type in doc_types:
            types_info.append(
                {
                    "type_code": doc_type.type_code,
                    "type_name": doc_type.type_name,
                    "description": doc_type.description,
                }
            )

        return {
            "success": True,
            "template_id": template_id,
            "total_types": len(types_info),
            "document_types": types_info,
        }

    except Exception as e:
        logger.error(f"获取文档类型信息失败: {str(e)}")
        return {
            "success": False,
            "error": f"查询失败: {str(e)}",
        }
