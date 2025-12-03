"""
多Query检索工具

支持使用多个查询词同时进行检索，并合并结果
"""

import json
from typing import Any, Dict, List

from loguru import logger

from core.tools.base import ToolContext, tool, ValidationMode


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


@tool(
    name="multi_query_search",
    description="使用多个查询词进行ES全文检索，适用于需要从多个角度或多个主题同时检索文档的场景。例如文档大纲的多个部分需要不同的数据支持。",
    parameters={
        "queries": {
            "type": "array",
            "description": "查询词列表，每个查询词是一个字符串",
            "items": {"type": "string"},
        },
        "template_id": {"type": "integer", "description": "模板ID"},
        "top_k_per_query": {
            "type": "integer",
            "description": "每个查询返回的文档数量，默认5",
            "default": 5,
        },
        "deduplication": {
            "type": "boolean",
            "description": "是否对结果去重，默认True",
            "default": True,
        },
    },
    required=["queries", "template_id"],
    category="retrieval",
    tags=["检索", "ES", "多查询", "全文搜索"],
    validate_function=_validate_search,
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "document_ids": {
            "type": "array",
            "description": "检索到的文档ID列表",
            "items": {"type": "integer"},
        },
        "documents": {
            "type": "array",
            "description": "检索到的文档摘要列表",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "integer", "description": "文档ID"},
                    "title": {"type": "string", "description": "文档标题"},
                    "snippet": {"type": "string", "description": "文档摘要"},
                    "score": {"type": "number", "description": "相关性分数"},
                    "query": {"type": "string", "description": "召回该文档的查询词"},
                },
            },
        },
        "query_results": {
            "type": "object",
            "description": "每个查询的原始结果（键为查询词，值为文档列表）",
        },
        "count": {"type": "integer", "description": "检索到的文档总数"},
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def multi_query_search(
    ctx: ToolContext,
    queries: List[str],
    template_id: int,
    top_k_per_query: int = 5,
    deduplication: bool = True,
) -> Dict[str, Any]:
    """
    多Query检索工具

    对每个查询词执行ES全文检索，然后合并结果
    支持去重和按相关性排序

    Args:
        ctx: 工具上下文
        queries: 查询词列表
        template_id: 模板ID
        top_k_per_query: 每个查询返回的文档数量
        deduplication: 是否去重

    Returns:
        {
            "success": bool,
            "document_ids": List[int],
            "documents": List[Dict],
            "query_results": Dict[str, List[Dict]],  # 每个查询的原始结果
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
            "query_results": {},
            "count": 0,
        }

    if not queries:
        return {
            "success": False,
            "error": "查询列表为空",
            "document_ids": [],
            "documents": [],
            "query_results": {},
            "count": 0,
        }

    try:
        logger.info(f"🔍 开始多Query检索: {len(queries)}个查询")

        # 存储每个查询的结果
        query_results = {}
        all_documents = {}  # document_id -> document info (带最高分数)

        # 对每个查询执行检索
        for query in queries:
            if not query or not query.strip():
                continue

            logger.info(f"   🔎 执行查询: {query}")

            # 构建ES查询
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

            # 执行检索
            response = await es_client.search(
                index=es_index,
                body={
                    "query": es_query,
                    "size": top_k_per_query,
                    "_source": ["document_id", "title", "content", "ai_summary"],
                    "highlight": {
                        "fields": {
                            "content": {"fragment_size": 150, "number_of_fragments": 2}
                        }
                    },
                },
            )

            hits = response["hits"]["hits"]
            query_docs = []

            for hit in hits:
                source = hit["_source"]
                doc_id = source.get("document_id")
                score = hit["_score"]

                highlight = hit.get("highlight", {})
                snippet = (
                    " ... ".join(highlight.get("content", []))
                    if highlight.get("content")
                    else source.get("content", "")[:200]
                )

                doc_info = {
                    "document_id": doc_id,
                    "title": source.get("title", ""),
                    "snippet": snippet,
                    "score": score,
                    "query": query,  # 记录是哪个查询召回的
                }

                query_docs.append(doc_info)

                # 去重处理：保留最高分数的结果
                if deduplication:
                    if (
                        doc_id not in all_documents
                        or score > all_documents[doc_id]["score"]
                    ):
                        all_documents[doc_id] = doc_info
                else:
                    # 不去重，添加多次
                    if doc_id not in all_documents:
                        all_documents[doc_id] = []
                    all_documents[doc_id].append(doc_info)

            query_results[query] = query_docs
            logger.info(f"      ✅ 召回 {len(query_docs)} 篇文档")

        # 整理最终结果
        if deduplication:
            # 按分数排序
            documents = sorted(
                all_documents.values(), key=lambda x: x["score"], reverse=True
            )
        else:
            # 展平列表并按分数排序
            documents = []
            for doc_list in all_documents.values():
                if isinstance(doc_list, list):
                    documents.extend(doc_list)
                else:
                    documents.append(doc_list)
            documents = sorted(
                documents, key=lambda x: x["score"], reverse=True)

        document_ids = [doc["document_id"] for doc in documents]

        logger.info(
            f"✅ 多Query检索完成: 总共召回 {len(documents)} 篇文档（去重={deduplication}）"
        )

        return {
            "success": True,
            "document_ids": document_ids,
            "documents": documents,
            "query_results": query_results,  # 返回每个查询的原始结果，方便调试
            "count": len(documents),
        }

    except Exception as e:
        logger.error(f"❌ 多Query检索失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "document_ids": [],
            "documents": [],
            "query_results": {},
            "count": 0,
        }
