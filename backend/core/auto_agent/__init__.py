"""
Auto Agent 集成模块

将 auto_agent 框架的核心能力集成到 DocHive 中：
- Memory 系统 (L1/L2/L3)
- TaskPlanner (LLM 驱动规划)
- ExecutionEngine (统一执行引擎)
- ExecutionContext (执行上下文)
- 工具系统 (已通过 core.tools 集成)
"""

# 从 auto_agent 导入核心组件
from auto_agent import (
    # 执行模型
    ExecutionPlan,
    PlanStep,
    SubTaskResult,
    AgentResponse,
    ValidationMode,
    # 规划和执行
    TaskPlanner,
    ExecutionEngine,
    ExecutionContext,
    # Memory 系统
    WorkingMemory,
    SemanticMemory,
    NarrativeMemoryManager,
    MemorySystem,
    MemoryRouter,
)

# DocHive 适配器（简化版）
from core.auto_agent.adapter import (
    DocHiveToolExecutor,
    DocHiveLLMClientAdapter,
)

__all__ = [
    # 执行模型
    "ExecutionPlan",
    "PlanStep",
    "SubTaskResult",
    "AgentResponse",
    "ValidationMode",
    # 规划和执行
    "TaskPlanner",
    "ExecutionEngine",
    "ExecutionContext",
    # Memory 系统
    "WorkingMemory",
    "SemanticMemory",
    "NarrativeMemoryManager",
    "MemorySystem",
    "MemoryRouter",
    # DocHive 适配器
    "DocHiveToolExecutor",
    "DocHiveLLMClientAdapter",
]
