"""
分析用户输入工具 - 分析用户直接输入的文本内容

用于分析用户输入的举报信、案件材料等文本内容,
识别案件类型、提取关键信息、生成摘要等。
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from core.tools.base import ToolContext, tool


@tool(
    name="analyze_input",
    description="分析用户输入的文本内容。适用于分析举报信、案件材料、用户描述等直接输入的文本。可以识别案件类型、提取关键信息、生成摘要。这是处理用户输入文本的首选工具，不需要document_ids。",
    parameters={
        "input_text": {
            "type": "string",
            "description": "用户输入的文本内容（如举报信、案件材料等）",
        },
        "analysis_goals": {
            "type": "array",
            "items": {"type": "string"},
            "description": "分析目标列表，如['识别案件类型', '提取关键人物', '总结主要事实']",
        },
        "output_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "期望输出的字段名列表，如['case_type', 'key_persons', 'summary']",
        },
    },
    required=["input_text"],
    category="analysis",
    tags=["分析", "用户输入", "案件类型", "信息提取"],
    validation_mode="loose",  # 使用宽松模式评估,只要识别出案件类型就算通过
    output_schema={
        "case_summary": {"type": "string", "description": "内容摘要"},
        "case_type": {"type": "list", "description": "识别出的案件/内容类型"},
        "key_info": {"type": "dict", "description": "提取的关键信息"},
        "analysis_result": {"type": "dict", "description": "完整分析结果"},
    },
)
async def analyze_input(
    ctx: ToolContext,
    input_text: str,
    analysis_goals: Optional[List[str]] = None,
    output_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    分析用户输入的文本内容

    Args:
        ctx: 工具上下文
        input_text: 用户输入的文本内容
        analysis_goals: 分析目标列表
        output_fields: 期望输出的字段名列表

    Returns:
        {
            "success": bool,
            "case_summary": str,  # 内容摘要
            "case_type": List[str],  # 识别出的类型
            "key_info": Dict,  # 关键信息
            "analysis_result": Dict,  # 完整分析结果
        }
    """
    from utils.llm_client import get_llm_client

    db = ctx.db

    if not input_text or not input_text.strip():
        return {
            "success": False,
            "error": "输入文本为空",
            "case_summary": "",
            "case_type": [],
            "key_info": {},
            "analysis_result": {},
        }

    try:
        llm_client = get_llm_client()

        # 构建分析目标描述
        goals_text = ""
        if analysis_goals:
            goals_text = "\n".join(f"- {goal}" for goal in analysis_goals)
        else:
            # 默认分析目标
            goals_text = """- 识别内容类型/案件类型
- 提取关键人物、时间、地点
- 总结主要事实和问题
- 识别可能的法律问题或违规行为"""

        # 构建输出字段描述
        fields_text = ""
        if output_fields:
            fields_text = f"\n\n请确保输出包含以下字段: {', '.join(output_fields)}"

        system_prompt = """你是一个专业的文本分析专家，擅长分析各类文本内容，包括举报信、案件材料、工作报告等。

你的任务是对用户输入的文本进行深入分析，识别关键信息。

【输出格式】
请返回JSON格式，包含以下字段:
{
    "case_summary": "内容摘要（100-200字）",
    "case_type": ["类型1", "类型2"],  // 识别出的类型列表
    "key_info": {
        "persons": ["人物1", "人物2"],  // 涉及的关键人物
        "organizations": ["机构1"],  // 涉及的组织机构
        "time_period": "时间范围",  // 涉及的时间
        "locations": ["地点1"],  // 涉及的地点
        "amounts": ["金额1"],  // 涉及的金额
        "key_facts": ["事实1", "事实2"]  // 关键事实
    },
    "legal_issues": ["法律问题1", "法律问题2"],  // 可能涉及的法律问题
    "suggested_focus": ["重点1", "重点2"]  // 建议关注的重点
}

请确保输出是有效的JSON格式。"""

        user_prompt = f"""【分析目标】
{goals_text}
{fields_text}

【待分析文本】
{input_text}

请对上述文本进行全面分析。"""

        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
            max_tokens=4096,
        )

        # 提取结果
        case_summary = response.get("case_summary", "")
        case_type = response.get("case_type", [])
        key_info = response.get("key_info", {})

        # 确保 case_type 是列表
        if isinstance(case_type, str):
            case_type = [case_type]

        logger.info(f"✅ 用户输入分析完成: 类型={case_type}, 摘要长度={len(case_summary)}")

        return {
            "success": True,
            "case_summary": case_summary,
            "case_type": case_type,
            "key_info": key_info,
            "analysis_result": response,
        }

    except Exception as e:
        logger.error(f"❌ 用户输入分析失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "case_summary": "",
            "case_type": [],
            "key_info": {},
            "analysis_result": {},
        }
