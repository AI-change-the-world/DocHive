"""
文档校对工具

对生成的文档进行校对（语法、用词、笔误、政治性错误等）和润色（根据文档类型调整风格）
"""

import json
from typing import Any, Dict, Optional

from loguru import logger

from auto_agent import func_tool, ValidationMode
from core.tools.base import ToolContext


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


@func_tool(
    name="document_review",
    description="对生成的文档进行校对和润色，包括语法、用词、笔误、政治性错误检查等。",
    context_param="ctx",
    parameters=[
        {"name": "document", "type": "object", "description": "需要校对的文档", "required": True},
        {"name": "document_type", "type": "string", "description": "文档类型", "default": "auto"},
        {"name": "review_focus", "type": "array", "description": "校对重点"},
    ],
    category="document",
    tags=["文档", "校对", "润色", "review"],
    validate_function=_validate_document_review,
    compress_function=_compress_document_review,
    # 参数别名：state 中的 composed_document 映射到 document 参数
    param_aliases={"document": ["composed_document", "generated_document", "draft_document"]},
    # 状态映射：工具输出如何更新 state
    state_mapping={"reviewed_document": "reviewed_document"},
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
你是一名专业的中文文档校对与润色专家，长期为政府机关、事业单位、大型企业提供文字审核与规范服务。请严格按照以下要求对文档进行校对和润色，禁止出现任何英文或中英混用（除文档原文中确实有必要保留的专业名词外）。

【文档标题】
{document.get("title", "未命名文档")}

【文档内容】
{content_to_review}

【文档类型】
{document_type if document_type != "auto" else "自动推断（如方案、报告、总结、公文、汇报等）"}

【校对重点】
{', '.join(review_focus_list)}

【你的任务】
请对文档进行“全面但克制”的校对与润色，不改变原意，不进行扩写，不加入额外信息。仅限以下行为：

1. **语法校正**：修正语句不通、搭配不当、成分残缺等问题。
2. **用词规范**：替换不准确、歧义或口语化的表达，使其符合正式书面语规范。
3. **笔误修正**：修正错别字、遗漏字、重复字及标点符号错误。
4. **政治性与合规性检查**：确保表达严谨，不出现政治性错误、敏感或不当内容。
5. **风格统一与润色**：根据文档类型将文字调整为合适的语体风格，如公文、方案、汇报、总结等（仅调整风格，不改变内容结构）。
6. **格式规范化**：保持 Markdown 结构清晰，标题、列表、段落排版统一规范。

【输出要求】
必须返回完整的 JSON，格式如下：

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

【特别注意】
- 绝不能中英文混用（除原文中的外文专有名词外）。
- 不得改变原内容的意思，不得扩写或添加信息。
- 文档如有明显结构性问题，只需轻微调整，不可大规模重写。
- 如果文档内容被截断，只校对当前可见部分。
- 输出必须是合法 JSON，不得包含额外解释或多余文本。
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
