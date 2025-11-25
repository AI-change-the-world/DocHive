"""
精读文档工具（读完整正文）
"""

from typing import Any, Dict, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


async def read_documents(
    document_ids: List[int],
    db: AsyncSession,
    max_documents: int = 10,
) -> Dict[str, Any]:
    """
    精读文档工具

    获取文档的完整正文内容，适合需要深入理解、提取详细信息的场景。
    例如:"地震预案的具体措施是什么"、"详细说明实施方案"等。

    优势：
    - 信息完整，细节准确
    - 可以找到具体细节

    限制：
    - 速度较慢，数据量大
    - 消耗更多LLM Token
    - 不适合处理大量文档

    Args:
        document_ids: 文档ID列表
        db: 数据库会话
        max_documents: 最多读取文档数，防止超过LLM上下文限制，默认10

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 文档完整内容
            "count": int,
            "reading_mode": "read",  # 标记阅读模式
            "truncated": bool  # 是否被截断
        }
    """
    try:
        from sqlalchemy import select
        from models.database_models import Document

        # 限制读取数量
        if len(document_ids) > max_documents:
            logger.warning(f"⚠️ 文档数量超过限制，截断到前{max_documents}篇")
            document_ids = document_ids[:max_documents]
            truncated = True
        else:
            truncated = False

        query = select(
            Document.id,
            Document.title,
            Document.content_text,
            Document.ai_summary,
            Document.original_filename,
        ).where(Document.id.in_(document_ids))

        result = await db.execute(query)
        documents = []

        for row in result.all():
            documents.append({
                "id": row.id,
                "title": row.title,
                "content": row.content_text or "",
                "summary": row.ai_summary or "",
                "filename": row.original_filename,
            })

        logger.info(f"✅ 精读文档完成: {len(documents)} 篇文档（包含完整正文）")

        return {
            "success": True,
            "documents": documents,
            "count": len(documents),
            "reading_mode": "read",
            "truncated": truncated,
        }

    except Exception as e:
        logger.error(f"❌ 精读文档失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "count": 0,
            "reading_mode": "read",
            "truncated": False,
        }
