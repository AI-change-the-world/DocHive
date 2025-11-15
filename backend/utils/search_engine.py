"""
搜索引擎 - Elasticsearch
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.database_models import TemplateDocumentMapping
from elasticsearch import AsyncElasticsearch


class SearchEngine:
    """Elasticsearch 搜索引擎"""

    def __init__(self):
        self.client: Optional[AsyncElasticsearch] = None
        self.index_name: Optional[str] = None

    def _ensure_initialized(self):
        """确保搜索引擎已初始化"""
        if self.client is not None:
            return
        
        from config import get_settings
        
        settings = get_settings()
        self.client = AsyncElasticsearch(
            [settings.ELASTICSEARCH_URL], verify_certs=False
        )
        self.index_name = settings.ELASTICSEARCH_INDEX
        
        logger.info(f"✅ Elasticsearch 搜索引擎初始化完成")

    async def ensure_index(self):
        """确保索引存在"""
        self._ensure_initialized()
        assert self.client is not None, "Elasticsearch 客户端初始化失败"
        assert self.index_name is not None, "Elasticsearch 索引名称未配置"
        
        if not await self.client.indices.exists(index=self.index_name):
            await self.create_index()

    async def create_index(self):
        """创建索引"""
        assert self.client is not None, "Elasticsearch 客户端初始化失败"
        assert self.index_name is not None, "Elasticsearch 索引名称未配置"
        
        index_mapping = {
            "mappings": {
                "dynamic": "true",  # 支持动态字段
                "properties": {
                    "document_id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    },
                    "template_id": {"type": "keyword"},
                    "file_type": {"type": "keyword"},
                    "upload_time": {"type": "date"},
                    "metadata": {"type": "object", "dynamic": True},  # 动态元数据区域
                },
            }
        }
        await self.client.indices.create(index=self.index_name, body=index_mapping)

    async def index_document(self, document_data: Dict[str, Any]) -> bool:
        """索引文档"""
        self._ensure_initialized()
        assert self.client is not None, "Elasticsearch 客户端初始化失败"
        assert self.index_name is not None, "Elasticsearch 索引名称未配置"
        
        try:
            await self.client.index(
                index=self.index_name,
                id=str(document_data["document_id"]),
                document=document_data,
            )
            return True
        except Exception as e:
            logger.error(f"ES索引失败: {e}")
            return False

    async def search_documents(
        self,
        keyword: Optional[str] = None,
        template_id: Optional[int] = None,
        file_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """搜索文档"""
        self._ensure_initialized()
        assert self.client is not None, "Elasticsearch 客户端初始化失败"
        assert self.index_name is not None, "Elasticsearch 索引名称未配置"
        
        query = {"bool": {"must": [], "filter": []}}

        if keyword:
            query["bool"]["must"].append(
                {
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^3", "content", "summary^2"],
                        "type": "best_fields",
                    }
                }
            )
        else:
            query["bool"]["must"].append({"match_all": {}})

        if template_id:
            query["bool"]["filter"].append({"term": {"template_id": template_id}})

        if file_type:
            query["bool"]["filter"].append({"term": {"file_type": file_type}})

        if start_date or end_date:
            date_range = {}
            if start_date:
                date_range["gte"] = start_date.isoformat()
            if end_date:
                date_range["lte"] = end_date.isoformat()
            query["bool"]["filter"].append({"range": {"upload_time": date_range}})

        from_index = (page - 1) * page_size

        try:
            response = await self.client.search(
                index=self.index_name,
                query=query,
                from_=from_index,
                size=page_size,
                sort=[{"upload_time": {"order": "desc"}}],
            )

            hits = response["hits"]["hits"]
            total = response["hits"]["total"]["value"]

            results = [
                {
                    "document_id": hit["_source"]["document_id"],
                    "title": hit["_source"]["title"],
                    "summary": hit["_source"].get("summary"),
                    "class_code": hit["_source"].get("class_code"),
                    "score": hit["_score"],
                }
                for hit in hits
            ]

            return {
                "results": results,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            logger.error(f"ES搜索失败: {e}")
            return {"results": [], "total": 0, "page": page, "page_size": page_size}

    async def delete_document(self, document_id: int) -> bool:
        """删除文档索引"""
        self._ensure_initialized()
        assert self.client is not None, "Elasticsearch 客户端初始化失败"
        assert self.index_name is not None, "Elasticsearch 索引名称未配置"
        
        try:
            await self.client.delete(index=self.index_name, id=str(document_id))
            return True
        except Exception:
            return False

    async def close(self):
        """关闭连接"""
        if self.client is not None:
            await self.client.close()

    async def _get_document_mapping_info(
        self, db: AsyncSession, document_id: int
    ) -> Optional[TemplateDocumentMapping]:
        """获取文档的映射信息"""
        result = await db.execute(
            select(TemplateDocumentMapping).where(
                TemplateDocumentMapping.document_id == document_id
            )
        )
        return result.scalar_one_or_none()


# 全局实例（延迟初始化）
_search_client: Optional[SearchEngine] = None


def get_search_client() -> SearchEngine:
    """获取搜索引擎客户端（懒加载）"""
    global _search_client
    if _search_client is None:
        _search_client = SearchEngine()
    return _search_client
