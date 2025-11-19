"""
Function Calling 路由器 - 基于 LLM 的任务规划与执行

让 LLM 自主规划整个任务的执行流程，包括：
1. 分析用户问题
2. 决定需要调用哪些工具
3. 确定工具调用的顺序
4. 决定是否需要文档检索
5. 智能组合所有结果
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
    Function Calling 路由器 - LLM 自主任务规划

    让 LLM 看到所有可用工具，自主规划最优的执行方案：
    - 分析问题，决定需要哪些步骤
    - 规划工具调用顺序
    - 决定是否需要文档检索
    - 系统按计划执行并组合结果

    Args:
        query: 用户查询
        template_id: 模板ID
        db: 数据库会话

    Returns:
        {
            "execution_plan": [
                {
                    "step": 1,
                    "action": "tool_call",
                    "tool_name": "get_template_statistics",
                    "arguments": {...},
                    "description": "获取模板统计信息"
                },
                ...
            ],
            "reasoning": "LLM的推理过程",
            "tool_results": [...],
            "need_retrieval": bool
        }
    """
    try:
        # 1. 构造工具描述（给 LLM 看的）
        tools_description = json.dumps(
            TOOLS_SCHEMA, ensure_ascii=False, indent=2)

        # 2. 构造系统提示词 - 让 LLM 规划整个执行流程
        system_prompt = f"""你是一个智能任务规划助手，能够分析用户问题并规划最优的执行方案。

用户当前的模板ID: {template_id}

【可用的工具列表】
{tools_description}

【你的任务】
分析用户的问题，规划最优的执行方案。你可以：
1. 调用一个或多个工具来获取信息
2. 决定工具调用的顺序
3. 决定是否还需要文档检索

【执行计划格式】
请返回 JSON 格式的执行计划：
{{
    "execution_plan": [
        {{
            "step": 1,
            "action": "tool_call",
            "tool_name": "工具名称",
            "arguments": {{"参数名": "参数值"}},
            "description": "这一步要做什么"
        }},
        {{
            "step": 2,
            "action": "document_retrieval",
            "description": "检索相关文档内容"
        }}
    ],
    "reasoning": "为什么这样规划"
}}

【规划原则】
1. **识别问题类型**：
   - 统计/信息查询 → 调用相应工具
   - 内容理解问题 → document_retrieval
   - 组合问题 → 先工具调用，再文档检索

2. **工具调用顺序**：
   - 如果需要多个工具，考虑依赖关系
   - 基础信息优先（如先获取模板列表，再查询具体模板）

3. **参数处理**：
   - template_id 会自动填充为 {template_id}（除非你明确指定其他值）
   - 可选参数可以不提供

4. **action 类型**：
   - "tool_call": 调用工具
   - "document_retrieval": 文档检索（语义理解）

【示例】
问题: "有多少文档，都讲了什么内容"
计划:
{{
    "execution_plan": [
        {{
            "step": 1,
            "action": "tool_call",
            "tool_name": "get_template_statistics",
            "arguments": {{"template_id": {template_id}}},
            "description": "获取文档数量统计"
        }},
        {{
            "step": 2,
            "action": "document_retrieval",
            "description": "检索文档内容进行总结"
        }}
    ],
    "reasoning": "问题包含两部分：1)统计信息用工具查询 2)内容理解需要文档检索"
}}

现在，请为以下用户问题规划执行方案：
{query}

只返回 JSON，不要其他内容。
"""

        # 3. 调用 LLM 获取执行计划
        logger.info("🧠 调用 LLM 规划任务执行流程...")

        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请为这个问题规划执行方案：{query}"},
            ],
            db=db,
        )

        logger.info(
            f"📋 LLM 规划结果:\n{json.dumps(response, ensure_ascii=False, indent=2)}")

        execution_plan = response.get("execution_plan", [])
        reasoning = response.get("reasoning", "")

        if not execution_plan:
            # 没有计划，默认走文档检索
            logger.info("⚠️ LLM 未返回执行计划，默认走文档检索")
            return {
                "execution_plan": [
                    {
                        "step": 1,
                        "action": "document_retrieval",
                        "description": "文档检索"
                    }
                ],
                "reasoning": "默认流程",
                "tool_results": [],
                "need_retrieval": True,
            }

        # 4. 执行计划中的工具调用
        tool_results = []
        for step in execution_plan:
            if step.get("action") == "tool_call":
                tool_name = step.get("tool_name")
                arguments = step.get("arguments", {})

                # 自动填充 template_id
                if "template_id" not in arguments and tool_name != "list_all_templates":
                    arguments["template_id"] = template_id

                # 执行工具
                logger.info(
                    f"🔧 执行步骤 {step.get('step')}: {step.get('description')}")
                result = await execute_tool_call(tool_name, arguments, db)

                tool_results.append({
                    "step": step.get("step"),
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "description": step.get("description"),
                })

        # 5. 检查是否需要文档检索
        need_retrieval = any(step.get("action") ==
                             "document_retrieval" for step in execution_plan)

        logger.info(
            f"✅ 执行计划完成: {len(tool_results)} 个工具调用, 需要检索: {need_retrieval}")

        return {
            "execution_plan": execution_plan,
            "reasoning": reasoning,
            "tool_results": tool_results,
            "need_retrieval": need_retrieval,
        }

    except Exception as e:
        logger.error(f"❌ Function Calling 路由失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        # 错误时默认走文档检索
        return {
            "execution_plan": [
                {
                    "step": 1,
                    "action": "document_retrieval",
                    "description": "文档检索"
                }
            ],
            "reasoning": f"规划失败，降级到文档检索: {str(e)}",
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
