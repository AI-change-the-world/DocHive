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


def get_agents_description():
    """获取智能体描述"""
    from core.agents import get_agents_description as _get_agents_description

    return _get_agents_description()


def get_tools_description():
    """获取工具描述"""
    from core.tools import get_tools_description as _get_tools_description

    return _get_tools_description()
