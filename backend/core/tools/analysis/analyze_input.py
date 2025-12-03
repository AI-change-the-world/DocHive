"""
分析用户输入工具 - 分析用户直接输入的文本内容

用于分析用户输入的举报信、案件材料等文本内容,
识别案件类型、提取关键信息、生成摘要等。
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from core.tools.base import ToolContext, tool, ValidationMode


def _compress_analyze_result(result: Dict[str, Any], state: Any) -> Dict[str, Any]:
    """
    analyze_input 工具的结果压缩函数

    分析工具需要保留核心分析结果:
    - success: 执行状态
    - case_type: 案件类型(关键信息)
    - case_summary: 案件摘要(关键信息,但可以截断)

    压缩的信息:
    - key_info: 只保留关键字段
    - analysis_result: 完全不保留(冠余信息)

    Args:
        result: 工具执行结果
        state: 执行状态

    Returns:
        压缩后的结果
    """
    compressed = {
        "success": result.get("success", False),
    }

    # 保留案件类型
    case_type = result.get("case_type", [])
    if case_type:
        compressed["case_type"] = case_type

    # 保留案件摘要(截断到300字)
    case_summary = result.get("case_summary", "")
    if case_summary:
        compressed["case_summary"] = case_summary[:300]
        if len(case_summary) > 300:
            compressed["case_summary"] += "..."

    # key_info 只保留关键字段
    key_info = result.get("key_info", {})
    if key_info:
        compressed_key_info = {}
        # 只保留关键人物和组织
        if key_info.get("persons"):
            compressed_key_info["persons"] = key_info["persons"][:5]
        if key_info.get("organizations"):
            compressed_key_info["organizations"] = key_info["organizations"][:3]
        if compressed_key_info:
            compressed["key_info"] = compressed_key_info

    # 错误信息必须保留
    if result.get("error"):
        compressed["error"] = str(result["error"])[:200]

    return compressed


def _validate_analyze_input(
    result: Dict[str, Any],
    expectations: str,
    state: Any,
    mode: ValidationMode,
    llm_client=None,
    db=None,
) -> tuple[bool, str]:
    """
    analyze_input 工具的验证函数(规则验证)

    核心检查: 是否识别出了案件类型
    """
    if mode == ValidationMode.NONE:
        if result.get("success", False):
            return True, "无需校验"
        return False, f"执行失败: {result.get('error', '未知错误')}"

    if not result.get("success", False):
        return False, f"执行失败: {result.get('error', '未知错误')}"

    case_type = result.get("case_type", [])
    case_summary = result.get("case_summary", "")

    if mode == ValidationMode.STRICT:
        # 严格模式: 需要识别出案件类型且有摘要
        if not case_type:
            return False, "未识别出案件类型"
        if not case_summary:
            return False, "未生成案件摘要"
        return True, f"识别出{len(case_type)}个案件类型"
    else:  # LOOSE
        # 宽松模式: 只要成功执行就通过
        if case_type or case_summary:
            return True, "分析完成"
        return True, "执行成功"


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
    validate_function=_validate_analyze_input,
    compress_function=_compress_analyze_result,
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
