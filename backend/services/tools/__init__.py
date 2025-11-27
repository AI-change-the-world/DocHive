"""
工具模块 - 统一入口

使用装饰器模式，支持自动注册和依赖注入
"""

# 分析工具
from services.tools.analysis.document_analyzer_v2 import analyze_documents

# 基础设施
from services.tools.base import (
    ToolContext,
    execute_tool,
    get_all_tools,
    get_tool,
    get_tools_by_category,
    get_tools_description,
    get_tools_schema_list,
    tool,
)

# 文档处理工具
from services.tools.document.deduplicate_documents import deduplicate_documents
from services.tools.document.get_document_contents_v2 import get_document_contents
from services.tools.document.read_documents_v2 import read_documents
from services.tools.document.skim_documents_v2 import skim_documents

# 检索工具
from services.tools.retrieval.es_fulltext_search_v2 import es_fulltext_search
from services.tools.retrieval.sql_structured_search_v2 import sql_structured_search
from services.tools.statistics.get_document_types_info_v2 import get_document_types_info

# 统计工具
from services.tools.statistics.get_template_statistics_v2 import get_template_statistics
from services.tools.statistics.list_all_templates_v2 import list_all_templates
from services.tools.statistics.search_documents_by_classification_v2 import (
    search_documents_by_classification,
)

__all__ = [
    # 基础设施
    "tool",
    "ToolContext",
    "get_tool",
    "get_all_tools",
    "get_tools_by_category",
    "get_tools_schema_list",
    "get_tools_description",
    "execute_tool",
    # 检索工具
    "es_fulltext_search",
    "sql_structured_search",
    # 文档工具
    "deduplicate_documents",
    "get_document_contents",
    "skim_documents",
    "read_documents",
    # 统计工具
    "get_template_statistics",
    "search_documents_by_classification",
    "get_document_types_info",
    "list_all_templates",
    # 分析工具
    "analyze_documents",
]
