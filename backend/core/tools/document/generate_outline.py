"""
智能生成文档大纲

使用 @tool 装饰器重构
"""

from typing import Any, Dict
import json

from loguru import logger

from core.tools.base import ToolContext, tool, ValidationMode


async def _validate_generate_outline(
    result: Dict[str, Any],
    expectations: str,
    state: Any,
    mode: ValidationMode,
    llm_client=None,
    db=None,
) -> tuple[bool, str]:
    """generate_outline工具的验证函数(LLM验证)"""
    # NONE模式:只检查success
    if mode == ValidationMode.NONE:
        if result.get("success", False):
            return True, "无需校验"
        return False, f"执行失败: {result.get('error', '未知错误')}"

    if not result.get("success", False):
        return False, f"执行失败: {result.get('error', '未知错误')}"

    # 生成性工具必须使用LLM验证
    if llm_client is None:
        # 没有LLM客户端时降级为简单规则验证
        outline = result.get("outline", [])
        if outline:
            return True, "LLM不可用,降级为简单验证:有大纲输出"
        return False, "LLM不可用,降级为简单验证:无大纲输出"

    # 获取输入上下文
    input_query = state.state.get("inputs", {}).get("query", "")
    outline = result.get("outline", [])

    # 构造验证prompt
    strictness = "严格" if mode == ValidationMode.STRICT else "宽松"
    system_prompt = f"""你是一个大纲质量评估专家。请评估生成的大纲是否满足期望。

【评估模式】{strictness}模式
- 严格模式:大纲必须结构完整、逻辑清晰、章节合理
- 宽松模式:只要大纲基本可用、有基本结构即可

【重要】如果用户输入本身不支持生成符合期望的大纲(如信息不足、目标不合理),请在原因中明确指出这是输入问题,不应该重试。

请返回JSON格式:
{{
    "passed": true/false,
    "reason": "评估原因(如果不通过是因为输入问题,请明确说明)"
}}"""

    user_prompt = f"""【用户输入】
{input_query}

【期望】
{expectations}

【生成的大纲】
{json.dumps(outline, ensure_ascii=False, indent=2)}

请评估这个大纲是否满足期望。"""

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
            max_tokens=512,
        )

        passed = response.get("passed", False)
        reason = response.get("reason", "LLM未返回原因")
        return passed, reason

    except Exception as e:
        # LLM调用失败时降级为简单规则验证
        logger.error(f"LLM验证失败: {e}")
        if outline:
            return True, f"LLM验证异常,降级为简单验证:有大纲输出"
        return False, f"LLM验证异常,降级为简单验证:无大纲输出"


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
    validate_function=_validate_generate_outline,
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
