"""
获取文档类型信息工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List

from loguru import logger
from sqlalchemy import select

from services.tools.base import ToolContext, tool


@tool(
    name="get_document_types_info",
    description="获取模板下的所有文档类型定义及其说明",
    parameters={"template_id": {"type": "integer", "description": "模板ID"}},
    required=["template_id"],
    category="statistics",
    tags=["文档类型", "模板", "元信息"],
)
async def get_document_types_info(
    ctx: ToolContext,
    template_id: int,
) -> Dict[str, Any]:
    """
    获取文档类型信息

    Args:
        ctx: 工具上下文
        template_id: 模板ID

    Returns:
        {
            "success": bool,
            "document_types": List[Dict],
            "count": int
        }
    """
    from models.database_models import DocumentType

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
            "document_types": [],
            "count": 0,
        }

    try:
        # 查询文档类型
        stmt = select(DocumentType).where(DocumentType.template_id == template_id)
        result = await db.execute(stmt)
        doc_types = result.scalars().all()

        document_types = [
            {
                "id": dt.id,
                "type_code": dt.type_code,
                "type_name": dt.type_name,
                "description": dt.description,
                "extract_fields": dt.extract_fields,
            }
            for dt in doc_types
        ]

        logger.info(f"✅ 获取文档类型完成: {len(document_types)} 个类型")

        return {
            "success": True,
            "document_types": document_types,
            "count": len(document_types),
        }

    except Exception as e:
        logger.error(f"❌ 获取文档类型失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_types": [],
            "count": 0,
        }
