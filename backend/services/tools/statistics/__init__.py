"""统计工具模块 - 统一入口"""

from services.tools.statistics.get_template_statistics import get_template_statistics
from services.tools.statistics.search_documents_by_classification import search_documents_by_classification
from services.tools.statistics.get_document_types_info import get_document_types_info
from services.tools.statistics.list_all_templates import list_all_templates

__all__ = [
    "get_template_statistics",
    "search_documents_by_classification",
    "get_document_types_info",
    "list_all_templates",
]
