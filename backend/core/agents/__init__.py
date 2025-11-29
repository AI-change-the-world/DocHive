"""
智能体模块 - 统一入口

使用装饰器模式，支持自动注册和依赖注入
"""

# 基础设施
from core.agents.base import (
    AgentContext,
    AgentResult,
    BaseAgent,
    agent,
    execute_agent,
    get_agent,
    get_agent_class,
    get_agents_description,
    get_agents_schema_list,
    get_all_agents,
)

# 主路由器
from core.agents.master_router import execute_master_router
from core.agents.qa_agent_v2 import QAAgentV2, generate_answer_v2

# 智能体实现（使用新版本）
from core.agents.retrieval_agent_v2 import RetrievalAgentV2, retrieve_documents_v2

__all__ = [
    # 基础设施
    "agent",
    "BaseAgent",
    "AgentContext",
    "AgentResult",
    "get_agent",
    "get_agent_class",
    "get_all_agents",
    "get_agents_schema_list",
    "get_agents_description",
    "execute_agent",
    # 智能体
    "RetrievalAgentV2",
    "retrieve_documents_v2",
    "QAAgentV2",
    "generate_answer_v2",
    # 主路由器
    "execute_master_router",
]
