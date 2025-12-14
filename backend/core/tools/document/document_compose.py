"""
文档组合工具

根据文档大纲和摘取的内容，组合生成完整的文档
"""

import json
from typing import Any, Dict, List

from loguru import logger

from auto_agent import func_tool, ValidationMode
from core.tools.base import ToolContext


def _compress_document_compose(result: Dict[str, Any], state: Any) -> Dict[str, Any]:
    """
    document_compose 工具的结果压缩函数

    生成性工具不压缩，返回 None 表示保留完整结果。
    原因:
    - 文档是LLM生成的，压缩后需要重新生成，浪费大量token
    - 文档是最终输出，必须保留完整内容
    - 可能被后续步骤（如document_review）使用

    Args:
        result: 工具执行结果
        state: 执行状态

    Returns:
        None 表示不压缩
    """
    return None  # 不压缩,保留完整结果


async def _validate_document_compose(
    result: Dict[str, Any],
    expectations: str,
    state: Any,
    mode: ValidationMode,
    llm_client=None,
    db=None,
) -> tuple[bool, str]:
    """
    document_compose 工具的验证函数(LLM验证)

    核心检查: 是否生成了文档
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
        document = result.get("document", {})
        word_count = document.get("word_count", 0) if document else 0
        if word_count > 50:
            return True, f"LLM不可用,降级为简单验证:生成{word_count}字文档"
        return False, f"LLM不可用,降级为简单验证:文档过短({word_count}字)"

    # 获取输入上下文
    input_query = state.state.get("inputs", {}).get("query", "")
    outline = state.state.get("outline", {})
    document = result.get("document", {})

    # 构造验证prompt
    strictness = "严格" if mode == ValidationMode.STRICT else "宽松"
    system_prompt = f"""你是一个文档质量评估专家。请评估生成的文档是否满足期望。

【评估模式】{strictness}模式
- 严格模式:文档必须内容完整、逻辑清晰、符合大纲要求、质量高
- 宽松模式:只要文档基本可用、有基本内容即可

【重要】如果用户输入或大纲本身不支持生成符合期望的文档(如信息不足、要求不合理),请在原因中明确指出这是输入问题,不应该重试。

请返回JSON格式:
{{
    "passed": true/false,
    "reason": "评估原因(如果不通过是因为输入问题,请明确说明)"
}}"""

    # 只传递文档的摘要信息,避免传递过长内容
    doc_summary = {
        "title": document.get("title", ""),
        "word_count": document.get("word_count", 0),
        "sections_count": len(document.get("sections", [])),
        "content_preview": document.get("content", "")[:500] + "..." if document.get("content") else "",
    }

    user_prompt = f"""【用户输入】
{input_query}

【大纲】
{json.dumps(outline, ensure_ascii=False, indent=2)}

【期望】
{expectations}

【生成的文档摘要】
{json.dumps(doc_summary, ensure_ascii=False, indent=2)}

请评估这个文档是否满足期望。"""

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
        word_count = document.get("word_count", 0) if document else 0
        if word_count > 50:
            return True, f"LLM验证异常,降级为简单验证:生成{word_count}字文档"
        return False, f"LLM验证异常,降级为简单验证:文档过短({word_count}字)"


@func_tool(
    name="document_compose",
    description="根据文档大纲和摘取的内容片段，组合生成完整的文档。",
    context_param="ctx",
    parameters=[
        {"name": "outline", "type": "object", "description": "文档大纲结构", "required": True},
        {"name": "extracted_content", "type": "object", "description": "按章节组织的摘取内容", "required": True},
        {"name": "query", "type": "string", "description": "用户原始查询", "required": True},
        {"name": "document_style", "type": "string", "description": "文档风格", "default": "auto"},
    ],
    category="document",
    tags=["文档", "组合", "生成", "compose"],
    validate_function=_validate_document_compose,
    compress_function=_compress_document_compose,
    # 参数别名：从 state 中读取对应字段
    param_aliases={"query": "inputs.query"},
    # 状态映射：将 document 写入 state["composed_document"]
    state_mapping={"document": "composed_document"},
    output_schema={
        "success": {"type": "boolean", "description": "执行是否成功"},
        "document": {
            "type": "object",
            "description": "生成的完整文档",
            "properties": {
                "title": {"type": "string", "description": "文档标题"},
                "content": {
                    "type": "string",
                    "description": "文档完整内容（Markdown格式）",
                },
                "word_count": {"type": "integer", "description": "文档字数"},
                "sections_count": {"type": "integer", "description": "章节数量"},
            },
        },
        "error": {"type": "string", "description": "错误信息（仅在失败时返回）"},
    },
)
async def document_compose(
    ctx: ToolContext,
    outline: Dict[str, Any],
    extracted_content: Dict[str, List[Dict[str, Any]]],
    query: str,
    document_style: str = "auto",
) -> Dict[str, Any]:
    """
    根据大纲和摘取内容组合生成完整文档

    Args:
        ctx: 工具上下文
        outline: 文档大纲结构
        extracted_content: 按章节组织的摘取内容
        query: 用户原始查询
        document_style: 文档风格

    Returns:
        {
            "success": bool,
            "document": {
                "title": str,
                "content": str,  # Markdown格式
                "word_count": int,
                "sections_count": int,
            }
        }
    """
    from utils.llm_client import get_llm_client

    db = ctx.db

    try:
        llm_client = get_llm_client()

        # 兼容两种outline格式
        if isinstance(outline, list):
            # 新格式: outline直接是章节列表
            sections = outline
            title = ""
        elif isinstance(outline, dict):
            # 旧格式: outline是包含title和sections的字典
            sections = outline.get(
                "sections", []) or outline.get("outline", [])
            title = outline.get("title", "")
        else:
            # 未知格式,尝试作为列表处理
            sections = []
            title = ""

        prompt = f"""
你是一个专业的文档编写助手。根据文档大纲和摘取的内容片段，组合生成一份完整、专业、结构化的文档。

【用户需求】
{query}

【文档大纲】
{f'标题: {title}' if title else ''}
章节结构:
{json.dumps(sections, ensure_ascii=False, indent=2)}

【摘取的内容片段】
{json.dumps(extracted_content, ensure_ascii=False, indent=2)}

【文档风格】
{document_style if document_style != "auto" else "根据文档类型自动推断（方案、报告、总结等）"}

【你的任务】
1. 根据大纲结构组织文档，**严格按照大纲的层级关系**：
   - 如果大纲中某章节有subsections字段，则该章节为主章节(用##)，subsections为子章节(用###)
   - 子章节下如果还有细分内容(如"案件概况"、"案件处理")，使用####
2. 将摘取的内容片段整合到对应章节
3. 对内容进行润色、优化，确保：
   - 逻辑连贯、条理清晰
   - 语言专业、准确
   - 符合文档风格要求
   - 章节之间过渡自然
4. 生成完整的Markdown格式文档

【输出格式】
返回JSON格式，结构如下：
{{
    "document": {{
        "title": "文档标题",
        "content": "# 文档标题\\n\\n## 第一章 引言\\n\\n内容...\\n\\n## 第二章 典型案例分析\\n\\n### 案例一：XXX案\\n\\n#### 案件概况\\n\\n内容...\\n\\n#### 案件处理\\n\\n内容...\\n\\n### 案例二：YYY案\\n\\n内容...",
        "word_count": 5000,
        "sections_count": 5
    }}
}}

【Markdown层级规范 - 非常重要！】
- 文档标题: # (一级标题，仅用于文档最顶层标题)
- 主章节: ## (二级标题，如"第一章"、"第二章"，对应大纲中的section_title)
- 子章节: ### (三级标题，对应大纲中的subsections[].title)
- 小节: #### (四级标题，用于子章节下的细分内容，如"案件概况"、"案件处理"、"案例启示")
- **关键**：必须根据大纲的subsections字段判断层级，不要把所有章节都用##

【注意】
- content必须是完整的Markdown格式文档
- 包含所有章节，即使某些章节内容较少
- 内容要专业、准确、连贯
- 字数要合理（根据大纲复杂度，通常3000-10000字）
- 对于研究报告、学习报告等，需要严格按照摘取的内容片段中的内容，不能胡乱生成数据，篡改数据
- 对于小说、散文等文学作品，可以适当美化语言，增加可读性
"""

        # 使用流式接口避免超时
        response = await llm_client.chat_completion_but_in_stream(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的文档编写助手，擅长将分散的内容片段组合成结构化的完整文档。",
                },
                {"role": "user", "content": prompt},
            ],
            db=db,
            response_format={"type": "json_object"},
            max_tokens=8000,  # 文档可能较长，增加token限制
        )

        # 解析响应
        try:
            data = json.loads(response)
            document = data.get("document", {})

            # 计算字数（如果LLM没有提供）
            if "word_count" not in document and "content" in document:
                content = document.get("content", "")
                # 简单估算：中文字符数
                word_count = len(content)
                document["word_count"] = word_count

            # 计算章节数
            if "sections_count" not in document:
                document["sections_count"] = len(sections)

            return {
                "success": True,
                "document": document,
            }
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}, 响应: {response[:500]}")
            return {
                "success": False,
                "error": f"LLM返回格式错误: {str(e)}",
                "document": {
                    "title": title or "未命名文档",
                    "content": "",
                    "word_count": 0,
                    "sections_count": 0,
                },
            }

    except Exception as e:
        import traceback

        logger.error(f"❌ 文档组合失败: {e}")
        logger.error(traceback.format_exc())

        # 安全地提取title
        fallback_title = "未命名文档"
        if isinstance(outline, dict):
            fallback_title = outline.get("title", "未命名文档")

        return {
            "success": False,
            "error": str(e),
            "document": {
                "title": fallback_title,
                "content": "",
                "word_count": 0,
                "sections_count": 0,
            },
        }
