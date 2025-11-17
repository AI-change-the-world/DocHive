from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from models.database_models import Document, TemplateDocumentMapping
from services.document_service import DocumentService
from utils.search_engine import get_search_client

RETERIEVAL_ROUTER_PROMPT = """
你是一个智能检索路由器，请根据用户的查询内容分析应当使用哪种检索方式。

可选的检索策略包括：
1. **fulltext**：全文检索，适合一般查询或模糊描述。
2. **vector**：向量检索，适合语义类、抽象、概念性问题。
3. **keyword**：关键字检索，适合命中具体关键词或名词（关键字表提供给你）。
4. **metadata**：元数据检索，用于涉及时间、地点、部门、作者等结构化字段。
5. **hybrid**：混合检索，适合既包含语义成分又包含明确约束的查询。

你需要综合判断用户查询的语义内容、是否包含明确字段（时间、部门、地点等），是否有模糊描述或概念性意图。

输出严格使用 JSON 格式，包含以下字段：
```json
{
  "strategy": "one of [fulltext, vector, keyword, metadata, hybrid]",
  "sub_strategies": ["可选子策略，如 ['keyword', 'metadata']"],
  "reason": "简要说明选择依据",
  "metadata": {
    "time": "可提取到的时间（可选）",
    "department": "可提取到的部门（可选）",
    "location": "可提取到的地点（可选）"
  },
  "keywords": ["命中的关键字（可选）"]
}

当无法确定时，默认输出：

{
  "strategy": "fulltext",
  "reason": "查询较为模糊，无法提取结构化信息。"
}

关键字表：
 {{keywords_dicts}}

示例 1：

用户查询：

"帮我找一下2023年销售部门的业绩报告"

输出：
{
  "strategy": "metadata",
  "reason": "用户明确提到了时间和部门信息。",
  "metadata": {
    "year": 2023,
    "department": "销售部门"
  },
  "sub_strategies": [],
  "keywords": ["业绩报告"]
}


示例 2：
用户查询：

"有哪些项目使用了深度学习算法？"

输出：
{
  "strategy": "hybrid",
  "sub_strategies": ["vector", "keyword"],
  "reason": "用户提到了具体技术关键字，同时语义上属于概念性问题。",
  "keywords": ["深度学习"],
  "metadata": {}
}

示例 3：
用户查询：

"给我看看公司最近AI方向的研究成果"

输出：
{
  "strategy": "vector",
  "reason": "用户描述较模糊且语义导向明显，适合向量检索。",
  "metadata": {},
  "keywords": ["AI"]
}

### 以下是用户输入：
{{query}}
"""


class SearchService:
    """检索服务层"""

    @staticmethod
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
