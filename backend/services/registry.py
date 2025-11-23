"""
工具和智能体注册中心

统一管理所有可用的工具和智能体，提供完整的清单给LLM
"""

from typing import Any, Dict, List
from services.agent_tools import TOOLS_SCHEMA


# ==================== 智能体注册表 ====================

AGENTS_SCHEMA = [
    {
        "name": "retrieval_agent",
        "description": "检索智能体 - 负责从文档库中检索相关文档",
        "capabilities": [
            "分析用户查询意图",
            "自动选择最优检索策略（ES全文检索/SQL结构化检索/混合检索）",
            "执行检索工具组合",
            "对检索结果进行去重和后处理",
        ],
        "input": {
            "query": "用户查询文本",
            "template_id": "模板ID",
            "top_k": "返回文档数量（默认20）",
        },
        "output": {
            "documents": "文档列表，包含id、title、content、ai_summary",
            "total_count": "文档数量",
            "retrieval_strategy": "使用的检索策略",
        },
        "适用场景": [
            "需要获取文档列表",
            "需要基于语义或结构化条件查找文档",
            "作为问答的前置步骤",
        ],
    },
    {
        "name": "qa_agent",
        "description": "问答智能体 - 基于给定文档生成答案",
        "capabilities": [
            "筛选与查询最相关的文档",
            "理解文档内容",
            "生成准确、简洁的自然语言答案",
        ],
        "input": {
            "query": "用户问题",
            "documents": "文档列表（通常来自检索智能体）",
            "max_context_length": "最大上下文长度（默认10000）",
        },
        "output": {
            "answer": "生成的答案",
            "filtered_documents": "使用的文档列表",
        },
        "适用场景": [
            "需要理解文档内容并生成答案",
            "已有文档列表，需要基于文档回答问题",
            "需要总结、分析、解释文档内容",
        ],
    },
]


# ==================== 组合方案定义 ====================

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
        "tools": TOOLS_SCHEMA,
        "agents": AGENTS_SCHEMA,
        "execution_patterns": EXECUTION_PATTERNS,
    }


def get_tools_description() -> str:
    """获取工具的文本描述"""
    tools_list = []
    for i, tool in enumerate(TOOLS_SCHEMA):
        func = tool.get("function", {})
        name = func.get("name", "")
        desc = func.get("description", "")
        tools_list.append(f"{i+1}. **{name}**: {desc}")

    return "\n".join(tools_list)


def get_agents_description() -> str:
    """获取智能体的文本描述"""
    agents_list = []
    for i, agent in enumerate(AGENTS_SCHEMA):
        name = agent.get("name", "")
        desc = agent.get("description", "")
        capabilities = agent.get("capabilities", [])
        scenarios = agent.get("适用场景", [])

        cap_text = "\n     - ".join(capabilities)
        scenario_text = "\n     - ".join(scenarios)

        agents_list.append(
            f"{i+1}. **{name}**: {desc}\n"
            f"   能力:\n     - {cap_text}\n"
            f"   适用场景:\n     - {scenario_text}"
        )

    return "\n\n".join(agents_list)


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
