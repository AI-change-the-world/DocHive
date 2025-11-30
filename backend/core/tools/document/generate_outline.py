"""
智能生成文档大纲

使用 @tool 装饰器重构
"""

from typing import Any, Dict

from loguru import logger

from core.tools.base import ToolContext, tool


@tool(
    name="generate_outline",
    description="""
    根据用户输入智能推断用户想生成的文档类型（如方案、报告、总结、规划、PPT 等），
    自动生成结构化文档大纲，包括章节标题、每章内容说明，并给出后续写作所需的检索 query。
    适用于自动生成方案、报告、规划、设计文档等大纲。
    """,
    parameters={
        "query": {
            "type": "string",
            "description": '用户的生成大纲请求，如"帮我写一个xxx方案的大纲"',
        },
    },
    required=["query"],
    category="document",
    tags=["文档", "大纲", "outline"],
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "title": {"type": "string", "description": "文档标题"},
        "outline": {
            "type": "array",
            "description": "大纲章节列表",
            "items": {
                "type": "object",
                "properties": {
                    "section_title": {"type": "string", "description": "章节标题"},
                    "description": {"type": "string", "description": "章节说明"},
                    "subsections": {
                        "type": "array",
                        "description": "子章节列表（可选）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "search_query": {
            "type": "array",
            "description": "后续写作所需的检索关键词列表",
            "items": {"type": "string"},
        },
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def generate_outline(
    ctx: ToolContext,
    query: str,
) -> Dict[str, Any]:
    """
    自动生成文档大纲，包括章节标题、内容说明、推荐搜索 Query。

    Args:
        ctx: 工具上下文
        query: 用户的生成大纲描述

    Returns:
        {
            "success": bool,
            "title": str,
            "outline": List[Dict[str, Any]],
            "search_query": List[str]
        }
    """

    from utils.llm_client import get_llm_client

    db = ctx.db

    try:
        llm_client = get_llm_client()

        prompt = f"""
你是一名专业的技术文档与方案编写专家，请根据用户的输入生成一个完整的大纲结构。

【用户输入】
{query}

【你的任务】
1. 推断用户想生成什么类型的文档（如：实施方案、技术方案、分析报告、规划文档、PPT、大模型方案等）
2. 自动生成文档标题（如果用户没有指定标题）
3. 生成结构化大纲：包含章节标题、每章内容说明，如有需要可包含二级或三级小节
4. 给出后续完成文档需要检索的资料（以 query 列表形式输出）
5. 输出格式必须是 JSON，结构如下：

{{
    "title": "文档标题",
    "outline": [
        {{
            "section_title": "章节标题",
            "description": "该章节的说明",
            "subsections": [
                {{
                    "title": "小节标题",
                    "description": "说明"
                }}
            ]
        }}
    ],
    "search_query": ["应检索的关键内容1", "应检索的关键内容2"]
}}

【注意】
- outline 要结构清晰、专业，必须可直接用于写方案
- search_query 要尽量覆盖写文档所需的资料范围
- 所有内容必须专业、简洁、可执行
"""

        response = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": "你是一个专业的文档结构设计助手。"},
                {"role": "user", "content": prompt},
            ],
            db=db,
        )

        # 解析模型返回的 JSON
        import json

        try:
            data = json.loads(response)
        except Exception:
            # 如果模型没有严格返回 JSON，则作为错误返回
            return {
                "success": False,
                "error": "模型返回格式不是有效 JSON，请检查 prompt。",
                "raw_response": response,
            }

        return {
            "success": True,
            "title": data.get("title", ""),
            "outline": data.get("outline", []),
            "search_query": data.get("search_query", []),
        }

    except Exception as e:
        import traceback

        logger.error("❌ 大纲生成失败: %s", e)
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "title": "",
            "outline": [],
            "search_query": [],
        }
