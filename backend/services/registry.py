"""
工具和智能体注册中心

统一管理所有可用的工具和智能体，提供完整的清单给LLM
使用新的装饰器模式，自动从注册表获取工具和智能体信息
"""

from typing import Any, Dict, List

from loguru import logger

from services.agents.base import get_agents_description as _get_agents_description
from services.agents.base import get_agents_schema_list, get_all_agents

# 导入新的基础设施
from services.tools.base import get_all_tools
from services.tools.base import get_tools_description as _get_tools_description
from services.tools.base import get_tools_schema_list

# ==================== 执行模式定义 ====================

EXECUTION_PATTERNS = {
    "tool_only": {
        "description": "仅工具调用 - 直接使用工具获取结果",
        "适用场景": "简单的统计查询、信息查询、不需要语义理解的任务",
        "示例": ["有多少文档", "列出所有模板", "查询分类01的文档"],
    },
    "agent_only": {
        "description": "仅智能体调用 - 调用单个智能体",
        "适用场景": "需要智能体的能力，但不需要组合",
        "示例": ["查找关于安全的文档（仅检索智能体）"],
    },
    "agent_chain": {
        "description": "智能体链式调用 - 多个智能体按顺序执行",
        "适用场景": "需要多个智能体协作完成任务",
        "示例": ["安全规范是什么（检索智能体→问答智能体）"],
    },
    "hybrid": {
        "description": "混合调用 - 工具和智能体组合",
        "适用场景": "既需要工具获取信息，又需要智能体处理",
        "示例": ["统计文档数量，并总结主要内容"],
    },
    "llm_direct": {
        "description": "LLM直接回答 - 使用LLM自身知识",
        "适用场景": "所有工具和智能体都无法处理的问题",
        "示例": ["什么是人工智能", "今天天气怎么样"],
    },
}


# ==================== 获取完整的系统能力描述 ====================


def get_system_capabilities() -> Dict[str, Any]:
    """
    获取系统的完整能力描述，供LLM决策使用

    Returns:
        包含所有工具、智能体、执行模式的完整描述
    """
    return {
        "tools": get_tools_schema_list(),
        "agents": get_agents_schema_list(),
        "execution_patterns": EXECUTION_PATTERNS,
    }


def get_tools_description() -> str:
    """获取工具的文本描述"""
    return _get_tools_description()


def get_agents_description() -> str:
    """获取智能体的文本描述"""
    return _get_agents_description()


def get_execution_patterns_description() -> str:
    """获取执行模式的文本描述"""
    patterns_list = []
    for pattern_name, pattern_info in EXECUTION_PATTERNS.items():
        desc = pattern_info.get("description", "")
        scenarios = pattern_info.get("适用场景", "")
        examples = pattern_info.get("示例", [])

        example_text = ", ".join([f'"{ex}"' for ex in examples])

        patterns_list.append(
            f"- **{pattern_name}**: {desc}\n"
            f"  适用: {scenarios}\n"
            f"  示例: {example_text}"
        )

    return "\n\n".join(patterns_list)


# ==================== 向后兼容：保留旧的 TOOLS_SCHEMA 和 AGENTS_SCHEMA ====================


# 这些变量现在动态生成，保持向后兼容
def _get_tools_schema_compat():
    """兼容旧代码的 TOOLS_SCHEMA"""
    return get_tools_schema_list()


def _get_agents_schema_compat():
    """兼容旧代码的 AGENTS_SCHEMA"""
    return get_agents_schema_list()


# 延迟加载，避免循环导入
class _LazySchema:
    def __init__(self, getter):
        self._getter = getter
        self._cache = None

    def __iter__(self):
        if self._cache is None:
            self._cache = self._getter()
        return iter(self._cache)

    def __len__(self):
        if self._cache is None:
            self._cache = self._getter()
        return len(self._cache)

    def __getitem__(self, index):
        if self._cache is None:
            self._cache = self._getter()
        return self._cache[index]


# 保持向后兼容
TOOLS_SCHEMA = _LazySchema(_get_tools_schema_compat)
AGENTS_SCHEMA = _LazySchema(_get_agents_schema_compat)
