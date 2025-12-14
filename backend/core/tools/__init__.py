"""
工具模块 - 完全基于 auto_agent 框架

所有工具直接使用 auto_agent.func_tool 装饰器
DocHive 只提供 ToolContext 和便捷函数
"""

# 从 auto_agent 直接导入
from auto_agent.models import ValidationMode
from auto_agent.tools.base import BaseTool
from auto_agent.tools.registry import ToolRegistry, func_tool, get_global_registry

# DocHive 扩展和便捷函数
from core.tools.base import (
    ToolContext,
    get_tool,
    get_all_tools,
    get_tools_by_category,
    get_tools_schema_list,
    get_tools_description,
    get_tools_catalog,
    get_state_keys_catalog,
    get_tool_compress_function,
    get_tool_validate_function,
    get_tool_output_schema,
    get_tool_metadata,
    execute_tool,
)

# 工具导入（触发注册）
from core.tools.analysis.analyze_input import analyze_input
from core.tools.analysis.document_analyzer_v2 import analyze_documents
from core.tools.document.deduplicate_documents import deduplicate_documents
from core.tools.document.document_compose import document_compose
from core.tools.document.document_extraction import document_extraction
from core.tools.document.document_review import document_review
from core.tools.document.generate_outline import generate_outline
from core.tools.document.get_document_contents_v2 import get_document_contents
from core.tools.document.read_documents_v2 import read_documents
from core.tools.document.skim_documents_v2 import skim_documents
from core.tools.retrieval.es_fulltext_search_v2 import es_fulltext_search
from core.tools.retrieval.multi_query_search import multi_query_search
from core.tools.retrieval.search_writing_templates import search_writing_templates
from core.tools.retrieval.sql_structured_search_v2 import sql_structured_search
from core.tools.statistics.get_document_types_info_v2 import get_document_types_info
from core.tools.statistics.get_template_statistics_v2 import get_template_statistics
from core.tools.statistics.list_all_templates_v2 import list_all_templates
from core.tools.statistics.search_documents_by_classification_v2 import (
    search_documents_by_classification,
)

__all__ = [
    # auto_agent 核心（直接导出）
    "BaseTool",
    "ToolRegistry",
    "ValidationMode",
    "func_tool",
    "get_global_registry",
    # DocHive 扩展
    "ToolContext",
    # 便捷函数
    "get_tool",
    "get_all_tools",
    "get_tools_by_category",
    "get_tools_schema_list",
    "get_tools_description",
    "get_tools_catalog",
    "get_state_keys_catalog",
    "get_tool_compress_function",
    "get_tool_validate_function",
    "get_tool_output_schema",
    "get_tool_metadata",
    "execute_tool",
    # 工具
    "es_fulltext_search",
    "sql_structured_search",
    "multi_query_search",
    "search_writing_templates",
    "deduplicate_documents",
    "get_document_contents",
    "skim_documents",
    "read_documents",
    "generate_outline",
    "document_extraction",
    "document_compose",
    "document_review",
    "get_template_statistics",
    "search_documents_by_classification",
    "get_document_types_info",
    "list_all_templates",
    "analyze_documents",
    "analyze_input",
]
