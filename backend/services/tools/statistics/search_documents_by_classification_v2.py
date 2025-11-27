"""
按分类搜索文档工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from services.tools.base import ToolContext, tool


@tool(
    name="search_documents_by_classification",
    description="根据分类编码搜索文档，可以查找特定分类下的文档列表",
    parameters={
        "template_id": {"type": "integer", "description": "模板ID"},
        "class_code": {
            "type": "string",
            "description": "分类编码，如果不提供则返回所有文档",
        },
    },
    required=["template_id"],
    category="statistics",
    tags=["搜索", "分类", "文档列表"],
)
async def search_documents_by_classification(
    ctx: ToolContext,
    template_id: int,
    class_code: Optional[str] = None,
) -> Dict[str, Any]:
    """
    按分类搜索文档

    Args:
        ctx: 工具上下文
        template_id: 模板ID
        class_code: 分类编码

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

        # 添加分类过滤
        if class_code:
            stmt = stmt.where(
                TemplateDocumentMapping.class_code.like(f"%{class_code}%")
            )

        result = await db.execute(stmt)
        document_ids = [row[0] for row in result.all()]

        logger.info(f"✅ 按分类搜索完成: {len(document_ids)} 篇文档")

        return {
            "success": True,
            "document_ids": document_ids,
            "count": len(document_ids),
        }

    except Exception as e:
        logger.error(f"❌ 按分类搜索失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_ids": [],
            "count": 0,
        }
