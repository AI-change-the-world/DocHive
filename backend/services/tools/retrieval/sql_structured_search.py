"""
SQL结构化检索工具

基于分类编码和类别字段进行结构化查询
"""

from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def sql_structured_search(
    template_id: int,
    class_code: Optional[str] = None,
    category_field_code: Optional[str] = None,
    db: AsyncSession = None,
    top_k: int = 50,
) -> Dict[str, Any]:
    """
    SQL结构化检索工具

    基于分类编码和类别字段进行结构化查询

    Args:
        template_id: 模板ID
        class_code: 分类编码（如"01.02"）
        category_field_code: 类别字段编码
        db: 数据库会话
        top_k: 返回文档数量

    Returns:
        {
            "success": bool,
            "document_ids": List[int],
            "count": int,
            "class_code": str,
            "conditions": List[str]  # 查询条件描述
        }
    """
    try:
        from sqlalchemy import and_, or_, select, func
        from models.database_models import (
            Document,
            TemplateDocumentMapping,
        )

        # 构建查询条件
        conditions = []
        filters = [TemplateDocumentMapping.template_id == template_id]

        # 分类编码过滤
        if class_code and class_code != "*":
            filters.append(
                TemplateDocumentMapping.class_code.like(f"{class_code}%"))
            conditions.append(f"分类编码: {class_code}")

        # 类别字段过滤（如果有）
        if category_field_code:
            filters.append(
                TemplateDocumentMapping.class_code.like(
                    f"%{category_field_code}%")
            )
            conditions.append(f"类别字段: {category_field_code}")

        # 执行查询
        query = (
            select(Document.id)
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(and_(*filters))
            .order_by(Document.upload_time.desc())
            .limit(top_k)
        )

        result = await db.execute(query)
        document_ids = [row.id for row in result.all()]

        logger.info(f"✅ SQL结构化检索完成: 召回 {len(document_ids)} 篇文档")

        return {
            "success": True,
            "document_ids": document_ids,
            "count": len(document_ids),
            "class_code": class_code or "*",
            "conditions": conditions,
        }

    except Exception as e:
        logger.error(f"❌ SQL结构化检索失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_ids": [],
            "count": 0,
            "class_code": class_code or "*",
            "conditions": [],
        }
