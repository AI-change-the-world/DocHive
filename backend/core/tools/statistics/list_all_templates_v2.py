"""
列出所有模板工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import func, select

from auto_agent import func_tool
from core.tools.base import ToolContext


@func_tool(
    name="list_all_templates",
    context_param="ctx",
    description="列出系统中所有可用的模板及其基本信息，包括模板名称、描述、版本、文档数量等",
    parameters=[],
    category="statistics",
    tags=["模板", "列表", "系统信息"],
)
async def list_all_templates(
    ctx: ToolContext,
) -> Dict[str, Any]:
    """
    列出所有模板

    Args:
        ctx: 工具上下文

    Returns:
        {
            "success": bool,
            "templates": List[Dict],
            "count": int
        }
    """
    from models.database_models import ClassTemplate, TemplateDocumentMapping

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
            "templates": [],
            "count": 0,
        }

    try:
        # 查询所有模板及其文档数量
        stmt = (
            select(
                ClassTemplate,
                func.count(TemplateDocumentMapping.document_id).label("doc_count"),
            )
            .outerjoin(
                TemplateDocumentMapping,
                TemplateDocumentMapping.template_id == ClassTemplate.id,
            )
            .group_by(ClassTemplate.id)
        )

        result = await db.execute(stmt)
        rows = result.all()

        templates = [
            {
                "id": row.ClassTemplate.id,
                "name": row.ClassTemplate.name,
                "description": row.ClassTemplate.description,
                "version": row.ClassTemplate.version,
                "document_count": row.doc_count,
            }
            for row in rows
        ]

        logger.info(f"✅ 列出所有模板完成: {len(templates)} 个模板")

        return {
            "success": True,
            "templates": templates,
            "count": len(templates),
        }

    except Exception as e:
        logger.error(f"❌ 列出模板失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "templates": [],
            "count": 0,
        }
