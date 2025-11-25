"""
工具注册表和Schema定义

统一管理所有工具的Schema和执行器
"""

from typing import Any, Dict
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from elasticsearch import AsyncElasticsearch

# 导入所有工具
from services.tools.retrieval.es_fulltext_search import es_fulltext_search
from services.tools.retrieval.sql_structured_search import sql_structured_search
from services.tools.document.get_document_contents import get_document_contents
from services.tools.document.skim_documents import skim_documents
from services.tools.document.read_documents import read_documents
from services.tools.statistics.get_template_statistics import get_template_statistics
from services.tools.statistics.search_documents_by_classification import search_documents_by_classification
from services.tools.statistics.get_document_types_info import get_document_types_info
from services.tools.statistics.list_all_templates import list_all_templates


# ==================== 工具Schema定义 ====================

TOOLS_SCHEMA = [
    # 统计查询工具
    {
        "type": "function",
        "function": {
            "name": "get_template_statistics",
            "description": "获取指定模板的统计信息，包括文档总数、分类分布、文档类型分布、最近上传的文档等",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    }
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_documents_by_classification",
            "description": "根据分类编码搜索文档，可以查找特定分类下的文档列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    },
                    "class_code": {
                        "type": "string",
                        "description": "分类编码，如果不提供则返回所有文档",
                    },
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_types_info",
            "description": "获取模板下的所有文档类型定义及其说明",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "integer",
                        "description": "模板ID",
                    }
                },
                "required": ["template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_all_templates",
            "description": "列出系统中所有可用的模板及其基本信息，包括模板名称、描述、版本、文档数量等",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    # 检索工具
    {
        "type": "function",
        "function": {
            "name": "es_fulltext_search",
            "description": "使用Elasticsearch进行全文检索，基于BM25算法召回相关文档。适用于需要基于关键词匹配的检索场景。",
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sql_structured_search",
            "description": "基于分类编码和类别字段进行结构化SQL查询。适用于需要精确匹配特定分类的场景。",
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
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_contents",
            "description": "获取指定文档的完整内容。适用于需要读取具体文档详情的场景。",
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
        }
    },
    {
        "type": "function",
        "function": {
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
        }
    },
    {
        "type": "function",
        "function": {
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
    }
]

# 工具函数映射表
TOOLS_MAP = {
    # 统计工具
    "get_template_statistics": get_template_statistics,
    "search_documents_by_classification": search_documents_by_classification,
    "get_document_types_info": get_document_types_info,
    "list_all_templates": list_all_templates,
    # 检索工具
    "es_fulltext_search": es_fulltext_search,
    "sql_structured_search": sql_structured_search,
    "get_document_contents": get_document_contents,
    # 阅读工具
    "skim_documents": skim_documents,
    "read_documents": read_documents,
}


# ==================== 工具调用执行器 ====================

async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession,
    es_client: AsyncElasticsearch = None,
    es_index: str = "dochive_documents",
) -> Dict[str, Any]:
    """
    执行工具调用

    Args:
        tool_name: 工具名称
        arguments: 工具参数
        db: 数据库会话
        es_client: Elasticsearch客户端（检索工具需要）
        es_index: ES索引名

    Returns:
        工具执行结果
    """
    if tool_name not in TOOLS_MAP:
        return {
            "success": False,
            "error": f"未知的工具: {tool_name}",
        }

    tool_function = TOOLS_MAP[tool_name]

    try:
        logger.info(f"执行工具: {tool_name}, 参数: {arguments}")

        # 检索工具需要传入 es_client
        if tool_name in ["es_fulltext_search", "sql_structured_search", "get_document_contents", "skim_documents", "read_documents"]:
            if tool_name == "es_fulltext_search":
                if not es_client:
                    return {
                        "success": False,
                        "error": "ES全文检索需要es_client参数",
                    }
                result = await tool_function(
                    query=arguments.get("query"),
                    template_id=arguments.get("template_id"),
                    es_client=es_client,
                    es_index=es_index,
                    top_k=arguments.get("top_k", 10),
                )
            elif tool_name == "sql_structured_search":
                result = await tool_function(
                    template_id=arguments.get("template_id"),
                    class_code=arguments.get("class_code"),
                    category_field_code=arguments.get("category_field_code"),
                    db=db,
                    top_k=arguments.get("top_k", 50),
                )
            elif tool_name == "get_document_contents":
                result = await tool_function(
                    document_ids=arguments.get("document_ids", []),
                    db=db,
                    include_fields=arguments.get("include_fields"),
                )
            elif tool_name == "skim_documents":
                result = await tool_function(
                    document_ids=arguments.get("document_ids", []),
                    db=db,
                )
            elif tool_name == "read_documents":
                result = await tool_function(
                    document_ids=arguments.get("document_ids", []),
                    db=db,
                    max_documents=arguments.get("max_documents", 10),
                )
        else:
            # 统计查询工具，只需要 db
            result = await tool_function(db, **arguments)

        logger.info(f"工具执行成功: {tool_name}")
        return result
    except Exception as e:
        logger.error(f"执行工具 {tool_name} 失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"工具执行失败: {str(e)}",
        }
