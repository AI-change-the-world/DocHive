"""智能体模块 - 统一入口"""

# 从当前目录导入
from services.agents.retrieval_agent import retrieve_documents_v2
from services.agents.qa_agent import generate_answer_v2
from services.agents.master_router import execute_master_router

__all__ = [
    "retrieve_documents_v2",
    "generate_answer_v2",
    "execute_master_router",
]
