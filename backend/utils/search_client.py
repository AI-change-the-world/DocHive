from elasticsearch import AsyncElasticsearch
from typing import List, Dict, Any, Optional
from config import get_settings
from datetime import datetime

settings = get_settings()


class SearchClient:
    """Elasticsearch 检索客户端"""
    
    def __init__(self):
        self.client = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
        self.index_name = settings.ELASTICSEARCH_INDEX
    
    async def ensure_index(self):
        """确保索引存在"""
        if not await self.client.indices.exists(index=self.index_name):
            await self.create_index()
    
    async def create_index(self):
        """创建索引"""
        index_mapping = {
            "mappings": {
                "properties": {
                    "document_id": {"type": "integer"},
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
                    "summary": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                    },
                    "class_path": {"type": "object"},
                    "class_code": {"type": "keyword"},
                    "template_id": {"type": "integer"},
                    "extracted_data": {"type": "object"},
                    "file_type": {"type": "keyword"},
                    "upload_time": {"type": "date"},
                    "uploader_id": {"type": "integer"},
                }
            }
        }
        
        await self.client.indices.create(index=self.index_name, body=index_mapping)
    
    async def index_document(self, document_data: Dict[str, Any]) -> bool:
        """索引文档"""
        try:
            await self.client.index(
                index=self.index_name,
                id=document_data["document_id"],
                document=document_data,
            )
            return True
        except Exception as e:
            print(f"索引文档失败: {e}")
            return False
    
    async def search_documents(
        self,
        keyword: Optional[str] = None,
        class_path: Optional[Dict[str, str]] = None,
        template_id: Optional[int] = None,
        file_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        搜索文档
        
        Args:
            keyword: 全文检索关键词
            class_path: 分类路径过滤
            template_id: 模板ID过滤
            file_type: 文件类型过滤
            start_date: 开始日期
            end_date: 结束日期
            page: 页码
            page_size: 每页数量
        
        Returns:
            搜索结果
        """
        query = {"bool": {"must": [], "filter": []}}
        
        # 全文检索
        if keyword:
            query["bool"]["must"].append({
                "multi_match": {
                    "query": keyword,
                    "fields": ["title^3", "content", "summary^2"],
                    "type": "best_fields",
                }
            })
        else:
            query["bool"]["must"].append({"match_all": {}})
        
        # 分类路径过滤
        if class_path:
            for key, value in class_path.items():
                query["bool"]["filter"].append({
                    "term": {f"class_path.{key}.keyword": value}
                })
        
        # 模板ID过滤
        if template_id:
            query["bool"]["filter"].append({"term": {"template_id": template_id}})
        
        # 文件类型过滤
        if file_type:
            query["bool"]["filter"].append({"term": {"file_type": file_type}})
        
        # 日期范围过滤
        if start_date or end_date:
            date_range = {}
            if start_date:
                date_range["gte"] = start_date.isoformat()
            if end_date:
                date_range["lte"] = end_date.isoformat()
            query["bool"]["filter"].append({"range": {"upload_time": date_range}})
        
        # 执行搜索
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
            print(f"搜索失败: {e}")
            return {
                "results": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
            }
    
    async def delete_document(self, document_id: int) -> bool:
        """删除索引文档"""
        try:
            await self.client.delete(index=self.index_name, id=document_id)
            return True
        except Exception:
            return False
    
    async def close(self):
        """关闭客户端"""
        await self.client.close()


# 全局实例
search_client = SearchClient()
