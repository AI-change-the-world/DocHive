"""文档处理工具子模块"""

from core.tools.document.deduplicate_documents import deduplicate_documents
from core.tools.document.get_document_contents_v2 import get_document_contents
from core.tools.document.read_documents_v2 import read_documents
from core.tools.document.skim_documents_v2 import skim_documents

__all__ = [
    "deduplicate_documents",
    "get_document_contents",
    "skim_documents",
    "read_documents",
]
