"""
文档组合工具

根据文档大纲和摘取的内容，组合生成完整的文档
"""

import json
from typing import Any, Dict, List

from loguru import logger

from core.tools.base import ToolContext, tool


@tool(
    name="document_compose",
    description="""
    根据文档大纲和摘取的内容片段，组合生成完整的文档。
    将各个章节的摘取内容进行整合、润色、结构化，生成符合大纲要求的完整文档。
    适用于将分散的内容片段组合成结构化的正式文档。
    """,
    parameters={
        "outline": {
            "type": "object",
            "description": "文档大纲结构，包含标题和章节信息",
        },
        "extracted_content": {
            "type": "object",
            "description": "按章节组织的摘取内容，来自document_extraction工具的输出",
        },
        "query": {
            "type": "string",
            "description": "用户原始查询，用于理解文档需求",
        },
        "document_style": {
            "type": "string",
            "description": "文档风格（可选），如：方案、报告、总结、规划等，默认自动推断",
            "default": "auto",
        },
    },
    required=["outline", "extracted_content", "query"],
    category="document",
    tags=["文档", "组合", "生成", "compose"],
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
