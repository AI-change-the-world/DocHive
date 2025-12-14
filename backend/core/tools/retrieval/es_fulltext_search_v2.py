"""
ES全文检索工具 V2

使用 @tool 装饰器重构
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from auto_agent import func_tool, ValidationMode
from core.tools.base import ToolContext


def _compress_search_result(result: Dict[str, Any], state: Any) -> Dict[str, Any]:
    """
    检索工具的结果压缩函数

    检索工具只需保留核心信息:
    - success: 执行状态
    - document_ids: 文档ID列表(关键信息,后续步骤需要)
    - count: 文档数量

    不保留的信息:
    - documents: 文档详细信息(可以通过ID重新获取)
    - snippet: 文档摘要(不是必要信息)

    Args:
        result: 工具执行结果
        state: 执行状态

    Returns:
        压缩后的结果
    """
    compressed = {
        "success": result.get("success", False),
        "count": result.get("count", 0),
    }

    # 保留文档ID列表(只保留前20个)
    doc_ids = result.get("document_ids", [])
    if doc_ids:
        compressed["document_ids"] = doc_ids[:20]
        if len(doc_ids) > 20:
            compressed["document_ids_total"] = len(doc_ids)

    # 错误信息必须保留
    if result.get("error"):
        compressed["error"] = str(result["error"])[:200]

    return compressed


def _validate_search(
    result: Dict[str, Any],
    expectations: str,
    state: Any,
    mode,
    llm_client=None,
    db=None,
) -> tuple[bool, str]:
    """
    检索工具(规则验证)

    核心检查: 是否检索到了文档
    """
    if mode == ValidationMode.NONE:
        if result.get("success", False):
            return True, "无需校验"
        return False, f"执行失败: {result.get('error', '未知错误')}"

    if not result.get("success", False):
        return False, f"执行失败: {result.get('error', '未知错误')}"

    doc_ids = result.get("document_ids", [])
    count = result.get("count", len(doc_ids))

    if mode == ValidationMode.STRICT:
        # 严格模式: 需要检索到至少一定数量的文档
        if count >= 3:
            return True, f"检索到{count}个文档"
        elif count > 0:
            return True, f"检索到{count}个文档(数量较少)"
        return False, "未检索到任何文档"
    else:  # LOOSE
        # 宽松模式: 只要执行成功就通过,有无结果都可以
        if count > 0:
            return True, f"检索到{count}个文档"
        return True, "检索完成,暂无匹配文档"


@func_tool(
    name="es_fulltext_search",
    description="使用Elasticsearch进行全文检索，基于BM25算法召回相关文档。适用于需要基于关键词匹配的检索场景。",
    parameters=[
        {"name": "query", "type": "string", "description": "用户查询文本", "required": True},
        {"name": "template_id", "type": "integer", "description": "模板ID", "required": True},
        {"name": "top_k", "type": "integer", "description": "返回文档数量，默认10", "default": 10},
        {"name": "optimized_query", "type": "object", "description": "优化后的查询"},
    ],
    category="retrieval",
    tags=["检索", "ES", "全文搜索"],
    validate_function=_validate_search,
    compress_function=_compress_search_result,
    context_param="ctx",
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "document_ids": {"type": "array", "description": "检索到的文档ID列表"},
        "documents": {"type": "array", "description": "检索到的文档摘要列表"},
        "count": {"type": "integer", "description": "检索到的文档数量"},
        "error": {"type": "string", "description": "错误信息"},
    },
)
async def es_fulltext_search(
    ctx: ToolContext,
    query: str,
    template_id: int,
    top_k: int = 10,
    optimized_query: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    ES全文检索工具

    使用Elasticsearch进行全文检索，基于BM25算法
    支持优化查询（必须/相关/排除关键词）

    Args:
        ctx: 工具上下文
        query: 用户查询
        template_id: 模板ID
        top_k: 返回文档数量
        optimized_query: 优化后的查询

    Returns:
        {
            "success": bool,
            "document_ids": List[int],
            "documents": List[Dict],
            "count": int
        }
    """
    es_client = ctx.es_client
    es_index = ctx.es_index

    if not es_client:
        return {
            "success": False,
            "error": "ES客户端未配置",
            "document_ids": [],
            "documents": [],
            "count": 0,
        }

    try:
        # 处理特殊查询：空查询或match_all标记
        if query == "__match_all__" or query == "":
            es_query = {
                "bool": {
                    "must": [{"match_all": {}}],
                    "filter": [{"term": {"template_id": template_id}}],
                }
            }
            logger.info(f"🔍 使用match_all查询所有文档，template_id={template_id}")

        elif optimized_query and optimized_query.get("primary_keywords"):
            # 使用优化后的查询
            primary_keywords = optimized_query.get("primary_keywords", [])
            context_keywords = optimized_query.get("context_keywords", [])
            related_keywords = optimized_query.get("related_keywords", [])

            if len(primary_keywords) > 2:
                context_keywords.extend(primary_keywords[1:])
                primary_keywords = primary_keywords[:1]

            bool_clauses = {
                "must": [],
                "should": [],
                "filter": [{"term": {"template_id": template_id}}],
            }

            # 主查询条件
            for keyword in primary_keywords:
                bool_clauses["must"].append(
                    {
                        "multi_match": {
                            "query": keyword,
                            "fields": ["title^3", "content", "ai_summary^2"],
                            "type": "best_fields",
                        }
                    }
                )

            # 上下文扩展
            for keyword in context_keywords:
                bool_clauses["should"].append(
                    {
                        "multi_match": {
                            "query": keyword,
                            "fields": ["title^1.5", "content", "ai_summary"],
                            "type": "best_fields",
                        }
                    }
                )

            # 相关词
            for keyword in related_keywords:
                bool_clauses["should"].append(
                    {
                        "multi_match": {
                            "query": keyword,
                            "fields": ["title^2", "content", "ai_summary"],
                            "type": "best_fields",
                        }
                    }
                )

            if not bool_clauses["must"]:
                bool_clauses["must"].append(
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^3", "content", "ai_summary^2"],
                            "type": "best_fields",
                        }
                    }
                )

            bool_clauses = {k: v for k, v in bool_clauses.items() if v}
            es_query = {"bool": bool_clauses}

            logger.info(f"🔍 使用优化查询:")
            logger.info(f"   ⭐ 主查询: {primary_keywords}")
            logger.info(f"   🌐 上下文扩展: {context_keywords}")
            logger.info(f"   💡 相关词: {related_keywords}")

        else:
            # 常规ES查询
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
                    "filter": [{"term": {"template_id": template_id}}],
                }
            }

        logger.info(f"🔍 使用query={json.dumps(es_query, ensure_ascii=False)}")

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

            highlight = hit.get("highlight", {})
            snippet = (
                " ... ".join(highlight.get("content", []))
                if highlight.get("content")
                else source.get("content", "")[:200]
            )

            documents.append(
                {
                    "document_id": doc_id,
                    "title": source.get("title", ""),
                    "snippet": snippet,
                    "score": hit["_score"],
                }
            )

        logger.info(f"✅ ES全文检索完成: 召回 {len(document_ids)} 篇文档，为 {document_ids}")

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
