from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from typing_extensions import deprecated

from models.database_models import Document, TemplateDocumentMapping
from services.document_service import DocumentService
from utils.search_engine import get_search_client


class SearchService:
    """检索服务层"""

    @staticmethod
    @deprecated("Deprecated")
    async def search_documents(
        db: AsyncSession,
        keyword: Optional[str] = None,
        template_id: Optional[int] = None,
        extracted_fields: Optional[Dict[str, Any]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        多维度文档检索

        支持：
        1. 全文检索（ES/ClickHouse/数据库原生）
        2. 分类路径过滤
        3. 抽取字段过滤
        4. 时间范围过滤
        """
        search_client = get_search_client()
        # 使用搜索引擎
        search_results = await search_client.search_documents(
            keyword=keyword,
            template_id=template_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

        # 获取详细文档信息
        document_ids = [r["document_id"] for r in search_results["results"]]

        if document_ids:
            result = await db.execute(
                select(Document).where(Document.id.in_(document_ids))
            )
            documents = {doc.id: doc for doc in result.scalars().all()}

            # 按搜索结果排序
            ordered_docs = [
                documents.get(doc_id) for doc_id in document_ids if doc_id in documents
            ]
        else:
            ordered_docs = []

        return {
            "documents": ordered_docs,
            "total": search_results["total"],
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    async def get_statistics(
        db: AsyncSession,
        template_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取文档统计信息

        包括：
        - 总文档数
        - 按模板分组统计
        - 按状态分组统计
        - 按日期分组统计
        """
        stats = {}

        # 总文档数
        total_query = select(func.count(Document.id))
        if template_id:
            total_query = total_query.where(Document.template_id == template_id)

        total_result = await db.execute(total_query)
        stats["total_documents"] = total_result.scalar()

        # 按状态统计（从TemplateDocumentMapping表获取）
        status_query = select(
            TemplateDocumentMapping.status,
            func.count(TemplateDocumentMapping.id).label("count"),
        ).group_by(TemplateDocumentMapping.status)

        if template_id:
            status_query = status_query.where(
                TemplateDocumentMapping.template_id == template_id
            )

        status_result = await db.execute(status_query)
        stats["by_status"] = {row.status: row.count for row in status_result.all()}

        # 按模板统计
        if not template_id:
            template_query = select(
                TemplateDocumentMapping.template_id,
                func.count(TemplateDocumentMapping.id).label("count"),
            ).group_by(TemplateDocumentMapping.template_id)

            template_result = await db.execute(template_query)
            stats["by_template"] = {
                row.template_id: row.count for row in template_result.all()
            }

        return stats

    @staticmethod
    @deprecated("Deprecated")
    async def index_document_to_es(
        document: Document, mapping: Optional[TemplateDocumentMapping] = None
    ) -> bool:
        """将文档索引到 Elasticsearch"""
        search_client = get_search_client()
        # 如果没有提供mapping，从数据库获取
        if mapping is None:
            # 这里应该从数据库获取mapping，但在当前上下文中我们可能没有db session
            # 在实际使用中，应该传递mapping或者db session
            pass

        # 检查文档状态（从mapping获取）
        document_status = (
            getattr(mapping, "status", getattr(document, "status", ""))
            if mapping
            else getattr(document, "status", "")
        )
        if document_status != "completed":
            return False

        # 获取upload_time的值
        upload_time = getattr(document, "upload_time", None)

        document_data = {
            "document_id": document.id,
            "title": document.title,
            "content": document.content_text or "",
            "summary": document.summary or "",
            "class_path": getattr(document, "class_path", {}) or {},
            "class_code": (
                getattr(mapping, "class_code", getattr(document, "class_code", ""))
                if mapping
                else getattr(document, "class_code", "")
            ),
            "template_id": document.template_id,
            "extracted_data": (
                mapping.extracted_data
                if mapping
                else getattr(document, "extracted_data", {}) or {}
            ),
            "file_type": document.file_type,
            "upload_time": (upload_time.isoformat() if upload_time else None),
            "uploader_id": document.uploader_id,
        }

        return await search_client.index_document(document_data)
