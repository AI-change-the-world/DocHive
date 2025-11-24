"""
检索工具集合

将检索智能体中的各个步骤封装为独立工具，支持 Function Calling
"""

from typing import Any, Dict, List, Optional, Set
from loguru import logger
from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession

# ==================== 工具1: ES全文检索 ====================


async def es_fulltext_search(
    query: str,
    template_id: int,
    es_client: AsyncElasticsearch,
    es_index: str = "dochive_documents",
    top_k: int = 10,
    optimized_query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    ES全文检索工具

    使用Elasticsearch进行全文检索，基于BM25算法
    支持优化查询（必须/相关/排除关键词）

    Args:
        query: 用户查询
        template_id: 模板ID
        es_client: Elasticsearch客户端
        es_index: ES索引名
        top_k: 返回文档数量
        optimized_query: 优化后的查询（包含 must/should/must_not 关键词）

    Returns:
        {
            "success": bool,
            "document_ids": List[int],  # 文档ID列表
            "documents": List[Dict],    # 文档详情（包含title, content片段等）
            "count": int
        }
    """
    try:
        # 处理特殊查询：空查询或match_all标记
        if query == "__match_all__" or query == "":
            # 使用match_all查询返回所有文档
            es_query = {
                "bool": {
                    "must": [
                        {"match_all": {}}  # 匹配所有文档
                    ],
                    "filter": [
                        {"term": {"template_id": template_id}}
                    ],
                }
            }
            logger.info(f"🔍 使用match_all查询所有文档，template_id={template_id}")
        elif optimized_query and optimized_query.get("must_keywords"):
            # 使用优化后的查询（必须/相关/排除关键词）
            must_keywords = optimized_query.get("must_keywords", [])
            should_keywords = optimized_query.get("should_keywords", [])
            must_not_keywords = optimized_query.get("must_not_keywords", [])

            # 构建 bool 查询
            bool_clauses = {
                "must": [],
                "should": [],
                "must_not": [],
                "filter": [{"term": {"template_id": template_id}}]
            }

            # 必须关键词：每个都必须匹配
            for keyword in must_keywords:
                bool_clauses["must"].append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^3", "content", "ai_summary^2"],
                        "type": "best_fields",
                    }
                })

            # 相关关键词：匹配任意一个即可（提高分数）
            for keyword in should_keywords:
                bool_clauses["should"].append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title^2", "content", "ai_summary"],
                        "type": "best_fields",
                    }
                })

            # 排除关键词：不能包含这些词
            for keyword in must_not_keywords:
                bool_clauses["must_not"].append({
                    "multi_match": {
                        "query": keyword,
                        "fields": ["title", "content", "ai_summary"],
                    }
                })

            # 如果没有must子句，则使用原始查询作为must
            if not bool_clauses["must"]:
                bool_clauses["must"].append({
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "content", "ai_summary^2"],
                        "type": "best_fields",
                    }
                })

            # 清理空数组
            bool_clauses = {k: v for k, v in bool_clauses.items() if v}

            es_query = {"bool": bool_clauses}

            logger.info(f"🔍 使用优化查询:")
            logger.info(f"   ✅ 必须: {must_keywords}")
            logger.info(f"   🔵 相关: {should_keywords}")
            logger.info(f"   ❌ 排除: {must_not_keywords}")
        else:
            # 构建常规ES查询
            es_query = {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": ["title^3", "content", "ai_summary^2"],
                                "type": "best_fields",
                            }
                        }
                    ],
                    "filter": [
                        {"term": {"template_id": template_id}}
                    ],
                }
            }

        # 执行检索
        response = await es_client.search(
            index=es_index,
            body={
                "query": es_query,
                "size": top_k,
                "_source": ["document_id", "title", "content", "ai_summary"],
                "highlight": {
                    "fields": {
                        "content": {"fragment_size": 150, "number_of_fragments": 2}
                    }
                },
            },
        )

        hits = response["hits"]["hits"]
        document_ids = []
        documents = []

        for hit in hits:
            source = hit["_source"]
            doc_id = source.get("document_id")
            document_ids.append(doc_id)

            # 提取高亮片段
            highlight = hit.get("highlight", {})
            snippet = (
                " ... ".join(highlight.get("content", []))
                if highlight.get("content")
                else source.get("content", "")[:200]
            )

            documents.append({
                "document_id": doc_id,
                "title": source.get("title", ""),
                "snippet": snippet,
                "score": hit["_score"],
            })

        logger.info(f"✅ ES全文检索完成: 召回 {len(document_ids)} 篇文档")

        return {
            "success": True,
            "document_ids": document_ids,
            "documents": documents,
            "count": len(document_ids),
        }

    except Exception as e:
        logger.error(f"❌ ES全文检索失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_ids": [],
            "documents": [],
            "count": 0,
        }


# ==================== 工具2: SQL结构化检索 ====================


async def sql_structured_search(
    template_id: int,
    class_code: Optional[str] = None,
    category_field_code: Optional[str] = None,
    db: AsyncSession = None,
    top_k: int = 50,
) -> Dict[str, Any]:
    """
    SQL结构化检索工具

    基于分类编码和类别字段进行结构化查询

    Args:
        template_id: 模板ID
        class_code: 分类编码（如"01.02"）
        category_field_code: 类别字段编码
        db: 数据库会话
        top_k: 返回文档数量

    Returns:
        {
            "success": bool,
            "document_ids": List[int],
            "count": int,
            "class_code": str,
            "conditions": List[str]  # 查询条件描述
        }
    """
    try:
        from sqlalchemy import and_, or_, select, func
        from models.database_models import (
            Document,
            TemplateDocumentMapping,
        )

        # 构建查询条件
        conditions = []
        filters = [TemplateDocumentMapping.template_id == template_id]

        # 分类编码过滤
        if class_code and class_code != "*":
            filters.append(
                TemplateDocumentMapping.class_code.like(f"{class_code}%"))
            conditions.append(f"分类编码: {class_code}")

        # 类别字段过滤（如果有）
        if category_field_code:
            filters.append(
                TemplateDocumentMapping.class_code.like(
                    f"%{category_field_code}%")
            )
            conditions.append(f"类别字段: {category_field_code}")

        # 执行查询
        query = (
            select(Document.id)
            .join(
                TemplateDocumentMapping,
                TemplateDocumentMapping.document_id == Document.id,
            )
            .where(and_(*filters))
            .order_by(Document.upload_time.desc())
            .limit(top_k)
        )

        result = await db.execute(query)
        document_ids = [row.id for row in result.all()]

        logger.info(f"✅ SQL结构化检索完成: 召回 {len(document_ids)} 篇文档")

        return {
            "success": True,
            "document_ids": document_ids,
            "count": len(document_ids),
            "class_code": class_code or "*",
            "conditions": conditions,
        }

    except Exception as e:
        logger.error(f"❌ SQL结构化检索失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_ids": [],
            "count": 0,
            "class_code": class_code or "*",
            "conditions": [],
        }


# ==================== 工具3: 文档内容获取 ====================


async def get_document_contents(
    document_ids: List[int],
    db: AsyncSession,
    include_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    获取文档完整内容

    Args:
        document_ids: 文档ID列表
        db: 数据库会话
        include_fields: 需要包含的字段列表（默认: id, title, content, ai_summary）

    Returns:
        {
            "success": bool,
            "documents": List[Dict],  # 文档完整内容
            "count": int
        }
    """
    try:
        from sqlalchemy import select
        from models.database_models import Document

        if not include_fields:
            include_fields = ["id", "title", "content", "ai_summary"]

        # 构建查询，只选择需要的字段
        columns = [getattr(Document, field)
                   for field in include_fields if hasattr(Document, field)]

        query = select(*columns).where(Document.id.in_(document_ids))

        result = await db.execute(query)
        documents = []

        for row in result.all():
            doc_dict = {}
            for i, field in enumerate(include_fields):
                if hasattr(Document, field):
                    doc_dict[field] = row[i]
            documents.append(doc_dict)

        logger.info(f"✅ 获取文档内容完成: {len(documents)} 篇文档")

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


# ==================== 工具4: 粗读文档（只读标题+摘要） ====================


async def skim_documents(
    document_ids: List[int],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    粗读文档工具

    只获取文档的标题和AI摘要，适合快速浏览、统计数量、了解大致内容的场景。
    例如：“有多少文档”、“都讲了什么内容”、“概述一下文档主题”等。

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


# ==================== 工具5: 精读文档（读完整正文） ====================


async def read_documents(
    document_ids: List[int],
    db: AsyncSession,
    max_documents: int = 10,
) -> Dict[str, Any]:
    """
    精读文档工具

    获取文档的完整正文内容，适合需要深入理解、提取详细信息的场景。
    例如：“地震预案的具体措施是什么”、“详细说明实施方案”等。

    优势：
    - 信息完整，细节准确
    - 可以找到具体细节

    限制：
    - 速度较慢，数据量大
    - 消耗更夞LLM Token
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


# ==================== 工具Schema定义 ====================

RETRIEVAL_TOOLS_SCHEMA = [
    {
        "name": "es_fulltext_search",
        "description": "使用Elasticsearch进行全文检索，基于BM25算法召回相关文档",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "用户查询文本"
                },
                "template_id": {
                    "type": "integer",
                    "description": "模板ID"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回文档数量，默认10",
                    "default": 10
                }
            },
            "required": ["query", "template_id"]
        }
    },
    {
        "name": "sql_structured_search",
        "description": "基于分类编码和类别字段进行结构化SQL查询",
        "parameters": {
            "type": "object",
            "properties": {
                "template_id": {
                    "type": "integer",
                    "description": "模板ID"
                },
                "class_code": {
                    "type": "string",
                    "description": "分类编码，如'01.02'，不提供则查询所有"
                },
                "category_field_code": {
                    "type": "string",
                    "description": "类别字段编码"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回文档数量，默认50",
                    "default": 50
                }
            },
            "required": ["template_id"]
        }
    },
    {
        "name": "get_document_contents",
        "description": "获取指定文档的完整内容",
        "parameters": {
            "type": "object",
            "properties": {
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "文档ID列表"
                },
                "include_fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "需要包含的字段，默认: id, title, content, ai_summary"
                }
            },
            "required": ["document_ids"]
        }
    },
    {
        "name": "skim_documents",
        "description": "粗读文档：只获取标题和AI摘要。适合快速浏览、统计数量、了解大致内容的场景，例如：'有多少文档'、'都讲了什么内容'、'概述一下文档主题'。优势：速度快、节省Token、可处理大量文档。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "文档ID列表"
                }
            },
            "required": ["document_ids"]
        }
    },
    {
        "name": "read_documents",
        "description": "精读文档：获取完整正文内容。适合需要深入理解、提取详细信息的场景，例如：'地震预案的具体措施是什么'、'详细说明实施方案'。优势：信息完整、细节准确。限制：速度较慢、消耗更多Token、不适合大量文档。",
        "parameters": {
            "type": "object",
            "properties": {
                "document_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "文档ID列表"
                },
                "max_documents": {
                    "type": "integer",
                    "description": "最多读取文档数，防止超过LLM上下文限制，默认10",
                    "default": 10
                }
            },
            "required": ["document_ids"]
        }
    }
]


# ==================== 工具执行器 ====================


async def execute_retrieval_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession = None,
    es_client: AsyncElasticsearch = None,
    es_index: str = "dochive_documents",
) -> Dict[str, Any]:
    """
    执行检索工具

    Args:
        tool_name: 工具名称
        arguments: 工具参数
        db: 数据库会话
        es_client: Elasticsearch客户端
        es_index: ES索引名

    Returns:
        工具执行结果
    """
    if tool_name == "es_fulltext_search":
        return await es_fulltext_search(
            query=arguments.get("query"),
            template_id=arguments.get("template_id"),
            es_client=es_client,
            es_index=es_index,
            top_k=arguments.get("top_k", 10),
        )

    elif tool_name == "sql_structured_search":
        return await sql_structured_search(
            template_id=arguments.get("template_id"),
            class_code=arguments.get("class_code"),
            category_field_code=arguments.get("category_field_code"),
            db=db,
            top_k=arguments.get("top_k", 50),
        )

    elif tool_name == "get_document_contents":
        return await get_document_contents(
            document_ids=arguments.get("document_ids", []),
            db=db,
            include_fields=arguments.get("include_fields"),
        )

    elif tool_name == "skim_documents":
        return await skim_documents(
            document_ids=arguments.get("document_ids", []),
            db=db,
        )

    elif tool_name == "read_documents":
        return await read_documents(
            document_ids=arguments.get("document_ids", []),
            db=db,
            max_documents=arguments.get("max_documents", 10),
        )

    else:
        return {
            "success": False,
            "error": f"未知的检索工具: {tool_name}"
        }
