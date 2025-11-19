"""
Function Calling 路由器

让 LLM 自主决策是否调用工具以及调用哪个工具
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_tools import TOOLS_SCHEMA, execute_tool_call
from utils.llm_client import llm_client


# ==================== Function Calling 路由 ====================


async def function_calling_router(
    query: str, template_id: int, db: AsyncSession
) -> Dict[str, Any]:
    """
    Function Calling 路由器

    让 LLM 自主决策是否需要调用工具，以及调用哪个工具。

    Args:
        query: 用户查询
        template_id: 模板ID
        db: 数据库会话

    Returns:
        {
            "need_tool": bool,
            "tool_calls": [...],  # LLM 返回的工具调用列表
            "tool_results": [...],  # 工具执行结果列表
            "need_retrieval": bool,
        }
    """
    try:
        # 1. 构造工具描述（给 LLM 看的）
        tools_description = json.dumps(TOOLS_SCHEMA, ensure_ascii=False, indent=2)

        # 2. 构造系统提示词
        system_prompt = f"""你是一个智能助手，能够通过调用工具来回答用户的问题。

用户当前的模板ID: {template_id}

可用的工具列表：
{tools_description}

请判断用户的问题是否需要调用工具：

1. **需要调用工具的情况**：
   - 统计查询（文档数量、分类分布等）
   - 信息查询（模板列表、文档类型列表等）
   - 分类筛选（按分类编码查找文档）

2. **不需要调用工具的情况**：
   - 需要语义理解的文档内容查询
   - 需要基于文档内容生成答案的问题

如果需要调用工具，请返回 JSON 格式：
{{
    "need_tool": true,
    "tool_calls": [
        {{
            "name": "工具名称",
            "arguments": {{"参数名": "参数值"}}
        }}
    ]
}}

如果不需要调用工具，请返回：
{{
    "need_tool": false
}}

注意：
- 你可以一次调用多个工具
- 如果工具需要 template_id 但你没有提供，系统会自动填充为 {template_id}
- 只返回 JSON，不要有其他内容
"""

        # 3. 调用 LLM
        logger.info("🧠 调用 LLM 进行 Function Calling...")

        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            db=db,
        )

        logger.info(f"LLM 响应: {response}")

        # 4. 检查 LLM 是否选择调用工具
        if not response.get("need_tool", False):
            # 不需要调用工具，走文档检索
            logger.info("✅ LLM 决定不调用工具，走文档检索流程")
            return {
                "need_tool": False,
                "tool_calls": [],
                "tool_results": [],
                "need_retrieval": True,
            }

        # 5. 执行工具调用
        tool_calls = response.get("tool_calls", [])
        logger.info(f"🔧 LLM 要求调用 {len(tool_calls)} 个工具")

        tool_results = []
        for tool_call in tool_calls:
            tool_name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})

            # 自动填充 template_id（如果工具需要且 LLM 未提供）
            if "template_id" not in arguments and tool_name != "list_all_templates":
                arguments["template_id"] = template_id

            # 执行工具
            result = await execute_tool_call(tool_name, arguments, db)
            tool_results.append(
                {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                }
            )

        return {
            "need_tool": True,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "need_retrieval": False,
        }

    except Exception as e:
        logger.error(f"❌ Function Calling 路由失败: {str(e)}")
        # 错误时默认走文档检索
        return {
            "need_tool": False,
            "tool_calls": [],
            "tool_results": [],
            "need_retrieval": True,
        }


async def format_tool_result_as_answer(
    tool_result: Dict[str, Any], query: str, db: AsyncSession
) -> str:
    """
    将工具调用结果格式化为自然语言回答

    Args:
        tool_result: 工具执行结果
        query: 用户原始查询
        db: 数据库会话

    Returns:
        格式化后的自然语言答案
    """
    try:
        # 使用LLM将结构化数据转换为自然语言
        prompt = f"""请将以下工具查询结果转换为自然、友好的回答。

用户问题: {query}

查询结果:
{json.dumps(tool_result, ensure_ascii=False, indent=2)}

要求：
1. 用自然语言描述结果
2. 突出关键数据和重点信息
3. 如果有列表数据，适当归纳总结
4. 语气友好、专业

请直接返回回答内容，不要加额外说明。"""

        answer = await llm_client.chat_completion(prompt, db=db)
        return answer

    except Exception as e:
        logger.error(f"格式化工具结果失败: {str(e)}")
        # 降级处理：直接返回JSON
        return f"查询结果：\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}"
