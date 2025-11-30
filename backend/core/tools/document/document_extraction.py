"""
文档摘取工具

从检索到的文档中，根据文档大纲和需求，摘取需要的部分内容
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from core.tools.base import ToolContext, tool


@tool(
    name="document_extraction",
    description="""
    根据文档大纲和检索到的文档，智能摘取每个章节所需的内容片段。
    分析文档内容与大纲章节的匹配度，提取最相关的段落和关键信息。
    适用于从大量检索结果中筛选和提取与文档大纲各章节相关的具体内容。
    """,
    parameters={
        "outline": {
            "type": "object",
            "description": "文档大纲结构，包含章节标题和说明",
        },
        "documents": {
            "type": "array",
            "description": "检索到的文档列表，每个文档包含id、title、content等字段",
            "items": {"type": "object"},
        },
        "query": {
            "type": "string",
            "description": "用户原始查询，用于理解文档需求",
        },
    },
    required=["outline", "documents", "query"],
    category="document",
    tags=["文档", "摘取", "提取", "extraction"],
    output_schema={
        "success": {
            "type": "boolean",
            "description": "执行是否成功"
        },
        "extracted_content": {
            "type": "object",
            "description": "按章节组织的摘取内容",
            "additionalProperties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_title": {"type": "string", "description": "章节标题"},
                        "content": {"type": "string", "description": "摘取的内容片段"},
                        "source_document_id": {"type": "integer", "description": "来源文档ID"},
                        "source_document_title": {"type": "string", "description": "来源文档标题"},
                        "relevance_score": {"type": "number", "description": "相关性分数"},
                    }
                }
            }
        },
        "summary": {
            "type": "object",
            "description": "摘取摘要统计",
            "properties": {
                "total_sections": {"type": "integer", "description": "章节总数"},
                "sections_with_content": {"type": "integer", "description": "有内容的章节数"},
                "total_extracted_chunks": {"type": "integer", "description": "摘取的片段总数"},
            }
        },
        "error": {
            "type": "string",
            "description": "错误信息（仅在失败时返回）"
        }
    }
)
async def document_extraction(
    ctx: ToolContext,
    outline: Dict[str, Any],
    documents: List[Dict[str, Any]],
    query: str,
) -> Dict[str, Any]:
    """
    从文档中摘取与大纲各章节相关的内容

    Args:
        ctx: 工具上下文
        outline: 文档大纲结构
        documents: 检索到的文档列表
        query: 用户原始查询

    Returns:
        {
            "success": bool,
            "extracted_content": Dict[str, List[Dict]],  # 按章节组织的摘取内容
            "summary": Dict[str, int],  # 摘取摘要统计
        }
    """
    from utils.llm_client import get_llm_client

    db = ctx.db

    try:
        if not documents:
            return {
                "success": False,
                "error": "没有可用的文档进行摘取",
                "extracted_content": {},
                "summary": {
                    "total_sections": 0,
                    "sections_with_content": 0,
                    "total_extracted_chunks": 0,
                }
            }

        llm_client = get_llm_client()

        # 构建文档内容摘要（避免传递过多内容）
        doc_summaries = []
        for doc in documents[:20]:  # 最多处理20个文档
            content = doc.get("content", "")
            # 如果内容太长，只取前2000字符
            if len(content) > 2000:
                content = content[:2000] + "..."
            doc_summaries.append({
                "id": doc.get("id") or doc.get("document_id"),
                "title": doc.get("title", "未命名文档"),
                "content": content,
            })

        # 构建大纲结构
        sections = outline.get("sections", []) or outline.get("outline", [])
        
        prompt = f"""
你是一个专业的文档内容摘取助手。根据文档大纲和检索到的文档，为每个章节摘取最相关的内容片段。

【用户需求】
{query}

【文档大纲】
{json.dumps(outline, ensure_ascii=False, indent=2)}

【可用文档】
{json.dumps(doc_summaries, ensure_ascii=False, indent=2)}

【你的任务】
1. 分析每个章节的需求（根据章节标题和说明）
2. 从可用文档中找到与每个章节最相关的内容片段
3. 为每个章节摘取多个内容片段（每个片段200-500字）
4. 记录每个片段的来源文档和相关性分数（0-1之间）

【输出格式】
返回JSON格式，结构如下：
{{
    "extracted_content": {{
        "章节1标题": [
            {{
                "section_title": "章节1标题",
                "content": "摘取的内容片段...",
                "source_document_id": 123,
                "source_document_title": "来源文档标题",
                "relevance_score": 0.85
            }}
        ],
        "章节2标题": [...]
    }},
    "summary": {{
        "total_sections": 5,
        "sections_with_content": 4,
        "total_extracted_chunks": 12
    }}
}}

【注意】
- 每个章节至少摘取1-3个相关片段
- 内容要准确、相关，避免冗余
- 如果某个章节没有相关内容，该章节可以为空数组
- 相关性分数要合理评估
"""

        response = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": "你是一个专业的文档内容摘取助手，擅长从大量文档中提取与特定主题相关的内容。"},
                {"role": "user", "content": prompt},
            ],
            db=db,
            response_format={"type": "json_object"},
        )

        # 解析响应
        try:
            data = json.loads(response)
            extracted_content = data.get("extracted_content", {})
            summary = data.get("summary", {
                "total_sections": len(sections),
                "sections_with_content": len([k for k, v in extracted_content.items() if v]),
                "total_extracted_chunks": sum(len(v) for v in extracted_content.values()),
            })

            return {
                "success": True,
                "extracted_content": extracted_content,
                "summary": summary,
            }
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON解析失败: {e}, 响应: {response[:500]}")
            return {
                "success": False,
                "error": f"LLM返回格式错误: {str(e)}",
                "extracted_content": {},
                "summary": {
                    "total_sections": len(sections),
                    "sections_with_content": 0,
                    "total_extracted_chunks": 0,
                }
            }

    except Exception as e:
        import traceback
        logger.error(f"❌ 文档摘取失败: {e}")
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "extracted_content": {},
            "summary": {
                "total_sections": 0,
                "sections_with_content": 0,
                "total_extracted_chunks": 0,
            }
        }

