"""
文档校对工具

对生成的文档进行校对（语法、用词、笔误、政治性错误等）和润色（根据文档类型调整风格）
"""

import json
from typing import Any, Dict, Optional

from loguru import logger

from core.tools.base import ToolContext, tool, ValidationMode


def _compress_document_review(result: Dict[str, Any], state: Any) -> Dict[str, Any]:
    """
    document_review 工具的结果压缩函数

    生成性工具不压缩，返回 None 表示保留完整结果。
    原因:
    - 审阅后的文档是LLM生成的，压缩后需要重新审阅，浪费大量token
    - 审阅结果是最终输出，必须保留完整内容
    - 审阅建议和修改记录都很重要

    Args:
        result: 工具执行结果
        state: 执行状态

    Returns:
        None 表示不压缩
    """
    return None  # 不压缩,保留完整结果


async def _validate_document_review(
    result: Dict[str, Any],
    expectations: str,
    state: Any,
    mode: ValidationMode,
    llm_client=None,
    db=None,
) -> tuple[bool, str]:
    """
    document_review 工具的验证函数(LLM验证)

    核心检查: 是否完成了审阅
    生成性工具必须使用LLM验证,并包含输入上下文
    """
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
        reviewed = result.get("reviewed_document", {})
        if reviewed and reviewed.get("content"):
            return True, "LLM不可用,降级为简单验证:有审阅结果"
        return False, "LLM不可用,降级为简单验证:无审阅结果"

    # 获取输入上下文
    input_query = state.state.get("inputs", {}).get("query", "")
    composed_document = state.state.get("composed_document", {})
    reviewed_document = result.get("reviewed_document", {})
    review_suggestions = result.get("review_suggestions", [])

    # 构造验证prompt
    strictness = "严格" if mode == ValidationMode.STRICT else "宽松"
    system_prompt = f"""你是一个文档审阅质量评估专家。请评估审阅结果是否满足期望。

【评估模式】{strictness}模式
- 严格模式:审阅必须全面、准确、有价值
- 宽松模式:只要完成了基本审阅即可

【重要】如果用户输入或文档本身不支持完成符合期望的审阅(如要求不合理),请在原因中明确指出这是输入问题,不应该重试。

请返回JSON格式:
{{
    "passed": true/false,
    "reason": "评估原因(如果不通过是因为输入问题,请明确说明)"
}}"""

    # 只传递文档的摘要信息
    doc_summary = {
        "title": composed_document.get("title", ""),
        "word_count": composed_document.get("word_count", 0),
    }

    review_summary = {
        "has_reviewed_document": bool(reviewed_document and reviewed_document.get("content")),
        "suggestions_count": len(review_suggestions),
        "suggestions_preview": review_suggestions[:3] if review_suggestions else [],
    }

    user_prompt = f"""【用户输入】
{input_query}

【被审阅文档摘要】
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

【期望】
{expectations}

【审阅结果摘要】
{json.dumps(review_summary, ensure_ascii=False, indent=2)}

请评估这个审阅是否满足期望。"""

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
        reviewed = result.get("reviewed_document", {})
        if reviewed and reviewed.get("content"):
            return True, "LLM验证异常,降级为简单验证:有审阅结果"
        return False, "LLM验证异常,降级为简单验证:无审阅结果"


@tool(
    name="document_review",
    description="""
    对生成的文档进行校对和润色。
    包括：语法错误检查、用词准确性、笔误修正、政治性错误检查、格式规范等。
    根据文档类型（公文、汇报、方案等）进行风格润色，确保文档专业、准确、规范。
    """,
    parameters={
        "document": {
            "type": "object",
            "description": "需要校对的文档，包含title和content字段",
        },
        "document_type": {
            "type": "string",
            "description": "文档类型（可选），如：方案、报告、总结、公文、汇报等，用于确定润色风格",
            "default": "auto",
        },
        "review_focus": {
            "type": "array",
            "description": "校对重点（可选），如：['grammar', 'spelling', 'political', 'style']",
            "items": {"type": "string"},
            "default": ["grammar", "spelling", "political", "style"],
        },
    },
    required=["document"],
    category="document",
    tags=["文档", "校对", "润色", "review"],
    validate_function=_validate_document_review,
    compress_function=_compress_document_review,
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "reviewed_document": {
            "type": "object",
            "description": "校对后的文档",
            "properties": {
                "title": {"type": "string", "description": "文档标题"},
                "content": {
                    "type": "string",
                    "description": "校对后的文档内容（Markdown格式）",
                },
                "word_count": {"type": "integer", "description": "文档字数"},
            },
        },
        "review_summary": {
            "type": "object",
            "description": "校对摘要",
            "properties": {
                "errors_found": {"type": "integer", "description": "发现的错误数量"},
                "corrections_made": {"type": "integer", "description": "修正的数量"},
                "improvements": {
                    "type": "array",
                    "description": "改进说明列表",
                    "items": {"type": "string"},
                },
            },
        },
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def document_review(
    ctx: ToolContext,
    document: Dict[str, Any],
    document_type: str = "auto",
    review_focus: Optional[list] = None,
) -> Dict[str, Any]:
    """
    对文档进行校对和润色

    Args:
        ctx: 工具上下文
        document: 需要校对的文档
        document_type: 文档类型
        review_focus: 校对重点

    Returns:
        {
            "success": bool,
            "reviewed_document": {
                "title": str,
                "content": str,  # Markdown格式
                "word_count": int,
            },
            "review_summary": {
                "errors_found": int,
                "corrections_made": int,
                "improvements": List[str],
            }
        }
    """
    from utils.llm_client import get_llm_client

    db = ctx.db

    try:
        if not document or not document.get("content"):
            return {
                "success": False,
                "error": "文档内容为空，无法进行校对",
                "reviewed_document": document,
                "review_summary": {
                    "errors_found": 0,
                    "corrections_made": 0,
                    "improvements": [],
                },
            }

        llm_client = get_llm_client()

        # 如果文档太长，截取前8000字符进行校对（避免token限制）
        content = document.get("content", "")
        original_length = len(content)
        is_truncated = original_length > 8000

        if is_truncated:
            content_to_review = (
                content[:8000] + "\n\n[文档后续内容已省略，仅校对前8000字符]"
            )
            logger.warning(f"⚠️ 文档过长({original_length}字符)，仅校对前8000字符")
        else:
            content_to_review = content

        review_focus_list = review_focus or [
            "grammar",
            "spelling",
            "political",
            "style",
        ]

        prompt = f"""
你是一个专业的文档校对和润色助手。请对以下文档进行全面校对和润色。

【文档标题】
{document.get("title", "未命名文档")}

【文档内容】
{content_to_review}

【文档类型】
{document_type if document_type != "auto" else "自动推断（方案、报告、总结、公文、汇报等）"}

【校对重点】
{', '.join(review_focus_list)}

【你的任务】
1. 语法检查：修正语法错误、句式不当等问题
2. 用词检查：修正用词不准确、不当表达等问题
3. 笔误修正：修正错别字、标点符号错误等
4. 政治性检查：确保没有政治性错误、敏感内容等
5. 风格润色：根据文档类型调整语言风格，确保专业、规范
6. 格式规范：确保Markdown格式正确、层次清晰

【输出格式】
返回JSON格式，结构如下：
{{
    "reviewed_document": {{
        "title": "校对后的标题（如有修改）",
        "content": "校对后的完整文档内容（Markdown格式）",
        "word_count": 5000
    }},
    "review_summary": {{
        "errors_found": 10,
        "corrections_made": 10,
        "improvements": [
            "修正了3处语法错误",
            "优化了5处用词表达",
            "调整了文档风格，使其更符合公文规范"
        ]
    }}
}}

【注意】
- 如果文档被截断，只校对提供的内容部分
- 保持文档的Markdown格式
- 改进说明要具体、清晰
- 确保校对后的文档质量显著提升
"""

        # 使用流式接口避免超时
        response = await llm_client.chat_completion_but_in_stream(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的文档校对和润色专家，擅长发现和修正文档中的各种错误，并根据文档类型进行风格优化。",
                },
                {"role": "user", "content": prompt},
            ],
            db=db,
            response_format={"type": "json_object"},
            max_tokens=10000,  # 校对后的文档可能更长
        )

        # 解析响应
        try:
            data = json.loads(response)
            reviewed_document = data.get("reviewed_document", {})
            review_summary = data.get(
                "review_summary",
                {
                    "errors_found": 0,
                    "corrections_made": 0,
                    "improvements": [],
                },
            )

            # 如果文档被截断，需要合并
            if is_truncated and reviewed_document.get("content"):
                # 保留校对后的前8000字符，然后拼接原文档的后续内容
                reviewed_content = reviewed_document.get("content", "")
                if len(reviewed_content) > 8000:
                    reviewed_content = reviewed_content[:8000]
                # 拼接后续内容
                remaining_content = content[8000:]
                reviewed_document["content"] = reviewed_content + \
                    remaining_content
                logger.info("✅ 已合并文档的后续内容")

            # 计算字数
            if "word_count" not in reviewed_document:
                reviewed_document["word_count"] = len(
                    reviewed_document.get("content", "")
                )

            return {
                "success": True,
                "reviewed_document": reviewed_document,
                "review_summary": review_summary,
            }
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}, 响应: {response[:500]}")
            return {
                "success": False,
                "error": f"LLM返回格式错误: {str(e)}",
                "reviewed_document": document,
                "review_summary": {
                    "errors_found": 0,
                    "corrections_made": 0,
                    "improvements": [],
                },
            }

    except Exception as e:
        import traceback

        logger.error(f"❌ 文档校对失败: {e}")
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "reviewed_document": document,
            "review_summary": {
                "errors_found": 0,
                "corrections_made": 0,
                "improvements": [],
            },
        }
