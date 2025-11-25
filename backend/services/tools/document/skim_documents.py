"""
粗读文档工具（只读标题+摘要）
"""

from typing import Any, Dict, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def skim_documents(
    document_ids: List[int],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    粗读文档工具

    只获取文档的标题和AI摘要，适合快速浏览、统计数量、了解大致内容的场景。
    例如："有多少文档"、"都讲了什么内容"、"概述一下文档主题"等。

    优势：
    - 速度快，数据量小
    - 适合处理大量文档
    - 省LLM Token

    限制：
    - 无法获取具体细节
    - 依赖AI摘要质量

    Args:
        document_ids: 文档ID列表
        db: 数据库会话

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 文档标题+摘要
            "count": int,
            "reading_mode": "skim"  # 标记阅读模式
        }
    """
    try:
        from sqlalchemy import select
        from models.database_models import Document

        query = select(
            Document.id,
            Document.title,
            Document.ai_summary,
            Document.original_filename,
        ).where(Document.id.in_(document_ids))

        result = await db.execute(query)
        documents = []

        for row in result.all():
            documents.append({
                "id": row.id,
                "title": row.title,
                "summary": row.ai_summary or "暂无摘要",
                "filename": row.original_filename,
            })

        logger.info(f"✅ 粗读文档完成: {len(documents)} 篇文档（只包含标题+摘要）")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
            "reading_mode": "skim",
        }

    except Exception as e:
        logger.error(f"❌ 粗读文档失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
            "reading_mode": "skim",
        }
