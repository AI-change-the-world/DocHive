"""
获取文档内容工具 V2

使用 @tool 装饰器重构
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import select

from auto_agent import func_tool
from core.tools.base import ToolContext


@func_tool(
    name="get_document_contents",
    context_param="ctx",
    description="获取指定文档的完整内容。适用于需要读取具体文档详情的场景。",
    parameters=[
        {"name": "document_ids", "type": "array", "description": "文档ID列表", "required": True},
        {"name": "include_fields", "type": "array", "description": "需要包含的字段，默认: id, title, content_text, ai_summary", "required": False},
    ],
    category="document",
    tags=["文档", "读取", "内容"],
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "documents": {
            "type": "array",
            "description": "文档内容列表",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "文档ID"},
                    "title": {"type": "string", "description": "文档标题"},
                    "content_text": {"type": "string", "description": "文档全文内容"},
                    "ai_summary": {"type": "string", "description": "AI生成的摘要"},
                },
            },
        },
        "count": {"type": "integer", "description": "返回的文档数量"},
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def get_document_contents(
    ctx: ToolContext,
    document_ids: List[int],
    include_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    获取文档内容工具

    Args:
        ctx: 工具上下文
        document_ids: 文档ID列表
        include_fields: 需要包含的字段

    Returns:
        {
            "success": bool,
            "documents": List[Dict],
            "count": int
        }
    """
    from models.database_models import Document

    db = ctx.db

    if not db:
        return {
            "success": False,
            "error": "数据库会话未配置",
            "documents": [],
            "count": 0,
        }

    if not document_ids:
        return {
            "success": True,
            "documents": [],
            "count": 0,
        }

    # 默认字段
    default_fields = ["id", "title", "content_text", "ai_summary"]
    fields = include_fields or default_fields

    try:
        # 查询文档
        stmt = select(Document).where(Document.id.in_(document_ids))
        result = await db.execute(stmt)
        docs = result.scalars().all()

        documents = []
        for doc in docs:
            doc_dict = {}
            for field in fields:
                if hasattr(doc, field):
                    doc_dict[field] = getattr(doc, field)
            documents.append(doc_dict)

        logger.info(f"✅ 获取文档内容完成: {len(documents)} 篇")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
        }

    except Exception as e:
        logger.error(f"❌ 获取文档内容失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
        }
