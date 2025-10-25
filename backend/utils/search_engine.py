"""
搜索引擎抽象层
支持多种搜索引擎：Elasticsearch、ClickHouse、数据库原生全文检索
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from config import get_settings

settings = get_settings()


class BaseSearchEngine(ABC):
    """搜索引擎基类"""

    @abstractmethod
    async def ensure_index(self):
        """确保索引/表存在"""
        pass

    @abstractmethod
    async def index_document(self, document_data: Dict[str, Any]) -> bool:
        """索引文档"""
        pass

    @abstractmethod
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
        """搜索文档"""
        pass

    @abstractmethod
    async def delete_document(self, document_id: int) -> bool:
        """删除文档索引"""
        pass

    async def close(self):
        """关闭连接（可选）"""
        pass


class ElasticsearchEngine(BaseSearchEngine):
    """Elasticsearch 搜索引擎"""

    def __init__(self):
        from elasticsearch import AsyncElasticsearch

        self.client = AsyncElasticsearch([settings.ELASTICSEARCH_URL])
        self.index_name = settings.ELASTICSEARCH_INDEX

    async def ensure_index(self):
        if not await self.client.indices.exists(index=self.index_name):
            await self.create_index()

    async def create_index(self):
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
                    "summary": {"type": "text", "analyzer": "ik_max_word"},
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
        try:
            await self.client.index(
                index=self.index_name,
                id=document_data["document_id"],
                document=document_data,
            )
            return True
        except Exception as e:
            print(f"ES索引失败: {e}")
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

        if class_path:
            for key, value in class_path.items():
                query["bool"]["filter"].append(
                    {"term": {f"class_path.{key}.keyword": value}}
                )

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
            print(f"ES搜索失败: {e}")
            return {"results": [], "total": 0, "page": page, "page_size": page_size}

    async def delete_document(self, document_id: int) -> bool:
        try:
            await self.client.delete(index=self.index_name, id=document_id)
            return True
        except Exception:
            return False

    async def close(self):
        await self.client.close()


class ClickHouseEngine(BaseSearchEngine):
    """ClickHouse 搜索引擎"""

    def __init__(self):
        from clickhouse_driver import Client

        self.client = Client(
            host=settings.CLICKHOUSE_HOST,
            port=settings.CLICKHOUSE_PORT,
            user=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
        self.table_name = "documents"

    async def ensure_index(self):
        """创建ClickHouse表"""
        try:
            self.client.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    document_id UInt32,
                    title String,
                    content String,
                    summary String,
                    class_path String,
                    class_code String,
                    template_id UInt32,
                    file_type String,
                    upload_time DateTime,
                    uploader_id UInt32
                ) ENGINE = MergeTree()
                ORDER BY (upload_time, document_id)
            """
            )
        except Exception as e:
            print(f"ClickHouse表创建失败: {e}")

    async def index_document(self, document_data: Dict[str, Any]) -> bool:
        try:
            import json

            self.client.execute(
                f"INSERT INTO {self.table_name} VALUES",
                [
                    (
                        document_data["document_id"],
                        document_data["title"],
                        document_data.get("content", ""),
                        document_data.get("summary", ""),
                        json.dumps(document_data.get("class_path", {})),
                        document_data.get("class_code", ""),
                        document_data.get("template_id", 0),
                        document_data.get("file_type", ""),
                        document_data.get("upload_time", datetime.now()),
                        document_data.get("uploader_id", 0),
                    )
                ],
            )
            return True
        except Exception as e:
            print(f"ClickHouse索引失败: {e}")
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
        conditions = []
        params = {}

        if keyword:
            # ClickHouse 全文检索
            conditions.append(
                "(positionCaseInsensitive(title, %(keyword)s) > 0 OR positionCaseInsensitive(content, %(keyword)s) > 0)"
            )
            params["keyword"] = keyword

        if template_id:
            conditions.append("template_id = %(template_id)s")
            params["template_id"] = template_id

        if file_type:
            conditions.append("file_type = %(file_type)s")
            params["file_type"] = file_type

        if start_date:
            conditions.append("upload_time >= %(start_date)s")
            params["start_date"] = start_date

        if end_date:
            conditions.append("upload_time <= %(end_date)s")
            params["end_date"] = end_date

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        offset = (page - 1) * page_size

        try:
            # 查询总数
            count_query = f"SELECT count(*) FROM {self.table_name} WHERE {where_clause}"
            total = self.client.execute(count_query, params)[0][0]

            # 查询结果
            query = f"""
                SELECT document_id, title, summary, class_code
                FROM {self.table_name}
                WHERE {where_clause}
                ORDER BY upload_time DESC
                LIMIT %(limit)s OFFSET %(offset)s
            """
            params["limit"] = page_size
            params["offset"] = offset

            rows = self.client.execute(query, params)
            results = [
                {
                    "document_id": row[0],
                    "title": row[1],
                    "summary": row[2],
                    "class_code": row[3],
                    "score": 1.0,
                }
                for row in rows
            ]

            return {
                "results": results,
                "total": total,
                "page": page,
                "page_size": page_size,
            }
        except Exception as e:
            print(f"ClickHouse搜索失败: {e}")
            return {"results": [], "total": 0, "page": page, "page_size": page_size}

    async def delete_document(self, document_id: int) -> bool:
        try:
            self.client.execute(
                f"ALTER TABLE {self.table_name} DELETE WHERE document_id = %(doc_id)s",
                {"doc_id": document_id},
            )
            return True
        except Exception:
            return False


class DatabaseEngine(BaseSearchEngine):
    """数据库原生全文检索引擎（PostgreSQL/MySQL/SQLite）"""

    def __init__(self):
        self.db_type = self._detect_db_type()

    def _detect_db_type(self) -> str:
        """检测数据库类型"""
        url = settings.DATABASE_URL.lower()
        if "postgresql" in url or "postgres" in url:
            return "postgresql"
        elif "mysql" in url:
            return "mysql"
        elif "sqlite" in url:
            return "sqlite"
        return "unknown"

    async def ensure_index(self):
        """创建全文索引"""
        from database import engine
        from sqlalchemy import text

        async with engine.begin() as conn:
            try:
                if self.db_type == "postgresql":
                    # PostgreSQL 使用 GIN 索引 + to_tsvector
                    await conn.execute(
                        text(
                            """
                        CREATE INDEX IF NOT EXISTS idx_documents_fulltext 
                        ON documents USING GIN (
                            to_tsvector('simple', title || ' ' || COALESCE(content_text, ''))
                        )
                    """
                        )
                    )
                elif self.db_type == "mysql":
                    # MySQL 使用 FULLTEXT 索引
                    await conn.execute(
                        text(
                            """
                        ALTER TABLE documents 
                        ADD FULLTEXT INDEX idx_documents_fulltext (title, content_text)
                    """
                        )
                    )
                elif self.db_type == "sqlite":
                    # SQLite 使用 FTS5 虚拟表
                    await conn.execute(
                        text(
                            """
                        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts 
                        USING fts5(document_id, title, content_text, content='documents', content_rowid='id')
                    """
                        )
                    )
                    # 创建触发器保持同步
                    await conn.execute(
                        text(
                            """
                        CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                            INSERT INTO documents_fts(rowid, document_id, title, content_text)
                            VALUES (new.id, new.id, new.title, new.content_text);
                        END
                    """
                        )
                    )
                    await conn.execute(
                        text(
                            """
                        CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                            DELETE FROM documents_fts WHERE rowid = old.id;
                        END
                    """
                        )
                    )
                    await conn.execute(
                        text(
                            """
                        CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                            DELETE FROM documents_fts WHERE rowid = old.id;
                            INSERT INTO documents_fts(rowid, document_id, title, content_text)
                            VALUES (new.id, new.id, new.title, new.content_text);
                        END
                    """
                        )
                    )
            except Exception as e:
                print(f"创建全文索引失败: {e}")

    async def index_document(self, document_data: Dict[str, Any]) -> bool:
        """数据库自动索引，无需额外操作"""
        return True

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
        """使用数据库原生全文检索"""
        from database import AsyncSessionLocal
        from sqlalchemy import select, func, or_, and_, text
        from models.database_models import Document

        async with AsyncSessionLocal() as session:
            # 构建基础查询
            query = select(Document)
            count_query = select(func.count(Document.id))

            conditions = []

            # 全文检索条件
            if keyword:
                if self.db_type == "postgresql":
                    # PostgreSQL to_tsvector
                    search_condition = text(
                        "to_tsvector('simple', title || ' ' || COALESCE(content_text, '')) @@ plainto_tsquery('simple', :keyword)"
                    )
                    conditions.append(search_condition.bindparams(keyword=keyword))
                elif self.db_type == "mysql":
                    # MySQL MATCH AGAINST
                    search_condition = text(
                        "MATCH(title, content_text) AGAINST(:keyword IN NATURAL LANGUAGE MODE)"
                    )
                    conditions.append(search_condition.bindparams(keyword=keyword))
                elif self.db_type == "sqlite":
                    # SQLite FTS5
                    # 需要通过子查询关联
                    fts_query = text(
                        """
                        id IN (
                            SELECT rowid FROM documents_fts 
                            WHERE documents_fts MATCH :keyword
                        )
                    """
                    )
                    conditions.append(fts_query.bindparams(keyword=keyword))
                else:
                    # 降级到 LIKE 查询
                    conditions.append(
                        or_(
                            Document.title.like(f"%{keyword}%"),
                            Document.content_text.like(f"%{keyword}%"),
                        )
                    )

            # 其他过滤条件
            if template_id:
                conditions.append(Document.template_id == template_id)

            if file_type:
                conditions.append(Document.file_type == file_type)

            if start_date:
                conditions.append(Document.upload_time >= start_date)

            if end_date:
                conditions.append(Document.upload_time <= end_date)

            # 应用条件
            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

            # 查询总数
            total_result = await session.execute(count_query)
            total = total_result.scalar()

            # 分页查询
            offset = (page - 1) * page_size
            query = (
                query.order_by(Document.upload_time.desc())
                .offset(offset)
                .limit(page_size)
            )

            result = await session.execute(query)
            documents = result.scalars().all()

            results = [
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "summary": doc.summary,
                    "class_code": doc.class_code,
                    "score": 1.0,
                }
                for doc in documents
            ]

            return {
                "results": results,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    async def delete_document(self, document_id: int) -> bool:
        """数据库自动删除索引"""
        return True


def get_search_engine() -> BaseSearchEngine:
    """工厂方法：根据配置返回搜索引擎实例"""
    engine_type = settings.SEARCH_ENGINE.lower()

    if engine_type == "elasticsearch":
        if not settings.ELASTICSEARCH_URL:
            print("⚠️ Elasticsearch URL 未配置，降级使用数据库搜索")
            return DatabaseEngine()
        try:
            return ElasticsearchEngine()
        except Exception as e:
            print(f"⚠️ Elasticsearch 初始化失败: {e}，降级使用数据库搜索")
            return DatabaseEngine()

    elif engine_type == "clickhouse":
        try:
            return ClickHouseEngine()
        except Exception as e:
            print(f"⚠️ ClickHouse 初始化失败: {e}，降级使用数据库搜索")
            return DatabaseEngine()

    else:  # database
        return DatabaseEngine()


# 全局实例
search_client = get_search_engine()
