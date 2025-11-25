"""工具模块 - 统一入口"""

# 检索工具
from services.tools.retrieval.es_fulltext_search import es_fulltext_search
from services.tools.retrieval.sql_structured_search import sql_structured_search

# 文档处理工具
from services.tools.document.deduplicate_documents import deduplicate_documents
from services.tools.document.get_document_contents import get_document_contents
from services.tools.document.skim_documents import skim_documents
from services.tools.document.read_documents import read_documents

# 统计工具
from services.tools.statistics.get_template_statistics import get_template_statistics
from services.tools.statistics.search_documents_by_classification import search_documents_by_classification
from services.tools.statistics.get_document_types_info import get_document_types_info
from services.tools.statistics.list_all_templates import list_all_templates

# 分析工具
from services.tools.analysis.document_analyzer import analyze_documents

__all__ = [
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
