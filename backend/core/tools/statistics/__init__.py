"""统计工具模块 - 统一入口"""

from core.tools.statistics.get_document_types_info_v2 import get_document_types_info
from core.tools.statistics.get_template_statistics_v2 import get_template_statistics
from core.tools.statistics.list_all_templates_v2 import list_all_templates
from core.tools.statistics.search_documents_by_classification_v2 import (
    search_documents_by_classification,
)

__all__ = [
    "get_template_statistics",
    "search_documents_by_classification",
    "get_document_types_info",
    "list_all_templates",
]
