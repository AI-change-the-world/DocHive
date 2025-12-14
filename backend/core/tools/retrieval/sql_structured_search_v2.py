"""
SQL结构化检索工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import or_, select

from auto_agent import func_tool
from core.tools.base import ToolContext


@func_tool(
    name="sql_structured_search",
    context_param="ctx",
    description="基于分类编码和类别字段进行结构化SQL查询。适用于需要精确匹配特定分类的场景。",
    parameters=[
        {"name": "template_id", "type": "integer", "description": "模板ID", "required": True},
        {"name": "class_code", "type": "string", "description": "分类编码，如'01.02'，不提供则查询所有", "required": False},
        {"name": "category_field_code", "type": "string", "description": "类别字段编码", "required": False},
        {"name": "top_k", "type": "integer", "description": "返回文档数量，默认50", "required": False, "default": 50},
    ],
    category="retrieval",
    tags=["检索", "SQL", "结构化查询"],
)
async def sql_structured_search(
    ctx: ToolContext,
    template_id: int,
    class_code: Optional[str] = None,
    category_field_code: Optional[str] = None,
    top_k: int = 50,
) -> Dict[str, Any]:
    """
    SQL结构化检索工具

    基于分类编码和类别字段进行结构化SQL查询

    Args:
        ctx: 工具上下文
        template_id: 模板ID
        class_code: 分类编码
        category_field_code: 类别字段编码
        top_k: 返回文档数量

    Returns:
        {
            "success": bool,
            "document_ids": List[int],
            "count": int
        }
    """
    from models.database_models import TemplateDocumentMapping

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
            "document_ids": [],
            "count": 0,
        }

    try:
        # 构建查询
        stmt = select(TemplateDocumentMapping.document_id).where(
            TemplateDocumentMapping.template_id == template_id
        )

        # 添加分类编码过滤
        conditions = []
        if class_code:
            conditions.append(
                TemplateDocumentMapping.class_code.like(f"%{class_code}%")
            )

        if category_field_code:
            conditions.append(
                TemplateDocumentMapping.class_code.like(f"%{category_field_code}%")
            )

        if conditions:
            stmt = stmt.where(or_(*conditions))

        # 限制返回数量
        stmt = stmt.limit(top_k)

        # 执行查询
        result = await db.execute(stmt)
        document_ids = [row[0] for row in result.all()]

        logger.info(f"✅ SQL结构化检索完成: 召回 {len(document_ids)} 篇文档")

        return {
            "success": True,
            "document_ids": document_ids,
            "count": len(document_ids),
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
        }
