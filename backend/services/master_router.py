""" 
主路由器V2 - 统一的智能体调度系统（基于LangGraph）

功能：
1. 提供完整的工具和智能体清单给LLM
2. LLM基于完整信息决定最优执行方案
3. 支持多种执行模式：工具调用/智能体调用/混合调用/LLM直接回答
4. 使用LangGraph实现真正的异步流式执行
5. 统一管理执行状态和结果
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.retrieval_agent_v2 import retrieve_documents_v2
from services.qa_agent_v2 import generate_answer_v2
from services.registry import (
    get_system_capabilities,
    get_tools_description,
    get_agents_description,
    get_execution_patterns_description,
)
from utils.llm_client import get_llm_client


# ==================== 状态管理 ====================


class ExecutionState(TypedDict):
    """
    执行状态 - 记录整个执行过程（LangGraph状态）
    """
    # 输入
    query: str
    template_id: int
    session_id: str

    # 决策
    execution_pattern: str  # tool_only / agent_only / agent_chain / hybrid / llm_direct
    reasoning: str  # LLM的推理过程
    execution_plan: List[Dict[str, Any]]  # 执行计划

    # 执行结果
    tool_results: List[Dict[str, Any]]  # 工具调用结果
    agent_results: List[Dict[str, Any]]  # 智能体调用结果
    intermediate_data: Dict[str, Any]  # 中间数据（如检索到的文档）

    # 最终输出
    final_answer: Optional[str]  # 最终答案
    documents: List[Dict[str, Any]]  # 相关文档（如果有）
    success: bool  # 是否成功
    error: Optional[str]  # 错误信息


# ==================== 节点函数 ====================


async def plan_execution(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 执行计划

    调用LLM分析查询，选择执行模式和组件。
    """
    logger.info("🧠 ========== 节点: 执行计划 ===========")

    query = state["query"]
    template_id = state["template_id"]

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    llm_client = get_llm_client()

    # 构建系统能力描述
    tools_desc = get_tools_description()
    agents_desc = get_agents_description()
    patterns_desc = get_execution_patterns_description()

    system_prompt = f"""你是一个智能任务调度助手，负责分析用户查询并选择执行方案。

【当前模板ID】
{template_id}

【系统能力清单】

## 1. 可用工具
{tools_desc}

## 2. 可用智能体
{agents_desc}

## 3. 执行模式
{patterns_desc}

【决策规则】
1. **分析查询**：理解用户真正的需求
2. **选择模式**：根据查询类型选择最适合的执行模式
3. **选择组件**：
   - tool_only: 列出需要调用的工具名称
   - agent_only: 指定要调用的智能体名称
   - agent_chain: 按顺序列出要调用的智能体名称
   - hybrid: 混合工具和智能体名称
   - llm_direct: 直接使用你的知识回答

**重要**：你只需要选择调用哪些工具/智能体，不需要指定具体参数。每个工具/智能体会自行分析用户查询并生成所需参数。

【返回格式】
返回JSON格式：
{{
    "execution_pattern": "tool_only" | "agent_only" | "agent_chain" | "hybrid" | "llm_direct",
    "reasoning": "为什么选择这个模式",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool" | "agent",
            "name": "工具名或智能体名",
            "description": "描述这一步要做什么"
        }}
    ],
    "direct_answer": null | "直接答案"  // 仅当 execution_pattern="llm_direct" 时填写
}}

【示例】

示例1 - 统计查询：
问题: "有多少文档？"
返回:
{{
    "execution_pattern": "tool_only",
    "reasoning": "简单的统计查询，直接调用统计工具",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool",
            "name": "get_template_statistics",
            "description": "获取模板统计信息"
        }}
    ],
    "direct_answer": null
}}

示例2 - 仅检索：
问题: "查找关于安全的文档"
返回:
{{
    "execution_pattern": "agent_only",
    "reasoning": "需要检索文档，但不需要生成答案",
    "execution_plan": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索相关文档"
        }}
    ],
    "direct_answer": null
}}

示例3 - 完整问答：
问题: "安全规范的主要内容是什么？"
返回:
{{
    "execution_pattern": "agent_chain",
    "reasoning": "需要先检索文档，再理解内容生成答案",
    "execution_plan": [
        {{
            "step": 1,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索相关文档"
        }},
        {{
            "step": 2,
            "type": "agent",
            "name": "qa_agent",
            "description": "基于检索结果生成答案"
        }}
    ],
    "direct_answer": null
}}

示例4 - 混合调用：
问题: "统计文档数量，并总结主要内容"
返回:
{{
    "execution_pattern": "hybrid",
    "reasoning": "既需要统计工具，又需要检索和问答智能体",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool",
            "name": "get_template_statistics",
            "description": "统计文档数量"
        }},
        {{
            "step": 2,
            "type": "agent",
            "name": "retrieval_agent",
            "description": "检索代表性文档"
        }},
        {{
            "step": 3,
            "type": "agent",
            "name": "qa_agent",
            "description": "总结内容"
        }}
    ],
    "direct_answer": null
}}

示例5 - LLM直接回答：
问题: "什么是人工智能？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是通用知识问题，不需要查询文档，直接回答",
    "execution_plan": [],
    "direct_answer": "人工智能（Artificial Intelligence, AI）是计算机科学的一个分支..."
}}

现在，请为以下用户问题制定执行方案。只返回JSON，不要其他内容。
"""

    try:
        logger.info("🧠 调用LLM进行任务规划...")
        await asyncio.sleep(0.3)  # 规划延迟

        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请为这个问题制定执行方案：{query}"},
            ],
            db=db,
        )

        logger.info(f"📋 规划结果: {json.dumps(response, ensure_ascii=False)}")

        state["execution_pattern"] = response.get(
            "execution_pattern", "llm_direct")
        state["reasoning"] = response.get("reasoning", "")
        state["execution_plan"] = response.get("execution_plan", [])

        # 如果是LLM直接回答
        if state["execution_pattern"] == "llm_direct":
            direct_answer = response.get("direct_answer")
            if direct_answer:
                state["final_answer"] = direct_answer
                state["success"] = True
                logger.info("✅ LLM直接回答完成")
            else:
                # 没有直接答案，让LLM生成一个
                fallback_answer = await llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": "你是一个专业的问答助手"},
                        {"role": "user", "content": query},
                    ],
                    db=db,
                )
                state["final_answer"] = fallback_answer
                state["success"] = True
                logger.info("✅ LLM fallback回答完成")

    except Exception as e:
        logger.error(f"❌ 任务规划失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 降级：直接让LLM回答
        state["execution_pattern"] = "llm_direct"
        state["reasoning"] = f"规划失败，降级到LLM直接回答: {str(e)}"
        try:
            fallback_answer = await llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个专业的问答助手"},
                    {"role": "user", "content": query},
                ],
                db=db,
            )
            state["final_answer"] = fallback_answer
            state["success"] = True
        except Exception as e2:
            state["error"] = f"回答失败: {str(e2)}"
            state["success"] = False

    return state


async def execute_steps(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 执行步骤

    根据执行计划，顺序执行工具和智能体。
    """
    logger.info("🚀 ========== 节点: 执行步骤 ===========")

    query = state["query"]
    template_id = state["template_id"]
    session_id = state["session_id"]

    # 从 config 获取所需资源
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore
    es_client = config.get("configurable", {}).get("es")  # type: ignore
    es_index: str = config.get("configurable", {}).get(
        "es_index", "dochive_documents")  # type: ignore

    try:
        for i, step in enumerate(state["execution_plan"]):
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name} - {step_desc}")

            await asyncio.sleep(0.3)  # 步骤间延迟

            if step_type == "tool":
                # 执行工具
                if step_name == "get_template_statistics":
                    from services.agent_tools import get_template_statistics
                    tool_result = await get_template_statistics(db, template_id)
                elif step_name == "get_document_summary":
                    from services.agent_tools import get_document_summary
                    tool_result = await get_document_summary(db, template_id)
                elif step_name == "get_classification_info":
                    from services.agent_tools import get_classification_info
                    tool_result = await get_classification_info(db, template_id)
                elif step_name == "list_all_templates":
                    from services.agent_tools import list_all_templates
                    tool_result = await list_all_templates(db)
                else:
                    logger.warning(f"⚠️ 未知的工具: {step_name}")
                    continue

                state["tool_results"].append({
                    "step": i + 1,
                    "tool_name": step_name,
                    "description": step_desc,
                    "result": tool_result,
                })

                logger.info(f"✅ 工具执行完成: {step_name}")

            elif step_type == "agent":
                # 执行智能体
                if step_name == "retrieval_agent":
                    # 检索智能体
                    retrieval_result = await retrieve_documents_v2(
                        query=query,
                        template_id=template_id,
                        session_id=session_id,
                        db=db,
                        es_client=es_client,
                        es_index=es_index,
                        top_k=20,
                        enable_deduplication=True,
                    )

                    state["agent_results"].append({
                        "step": i + 1,
                        "agent_name": step_name,
                        "description": step_desc,
                        "result": retrieval_result,
                    })

                    # 保存检索到的文档
                    if retrieval_result.get("success"):
                        state["intermediate_data"]["documents"] = retrieval_result.get(
                            "documents", [])
                        state["documents"] = retrieval_result.get(
                            "documents", [])
                        logger.info(
                            f"✅ 检索智能体执行完成: {len(state['documents'])} 篇文档")
                    else:
                        logger.warning(
                            f"⚠️ 检索智能体执行失败: {retrieval_result.get('error')}")

                elif step_name == "qa_agent":
                    # 问答智能体
                    documents = state["intermediate_data"].get("documents", [])

                    qa_result = await generate_answer_v2(
                        query=query,
                        documents=documents,
                        db=db,
                        max_context_length=10000,
                    )

                    state["agent_results"].append({
                        "step": i + 1,
                        "agent_name": step_name,
                        "description": step_desc,
                        "result": qa_result,
                    })

                    # 保存答案
                    if qa_result.get("success"):
                        state["final_answer"] = qa_result.get("answer")
                        logger.info(f"✅ 问答智能体执行完成")
                    else:
                        logger.warning(
                            f"⚠️ 问答智能体执行失败: {qa_result.get('error')}")
                else:
                    logger.warning(f"⚠️ 未知的智能体: {step_name}")

        state["success"] = True
        logger.info("✅ 所有步骤执行完成")

    except Exception as e:
        logger.error(f"❌ 执行步骤失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["error"] = str(e)
        state["success"] = False

    return state


async def finalize_answer(
    state: ExecutionState, config: RunnableConfig
) -> ExecutionState:
    """
    节点: 生成最终答案

    整合执行结果，生成最终答案。
    """
    logger.info("📝 ========== 节点: 生成最终答案 ===========")

    query = state["query"]

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    try:
        # 如果已经有答案，直接返回
        if state["final_answer"]:
            logger.info("✅ 已有最终答案，跳过生成")
            return state

        # 根据执行模式生成答案
        if state["execution_pattern"] == "tool_only" and state["tool_results"]:
            # 格式化工具结果
            from services.intent_router import format_tool_result_as_answer

            combined_results = {
                "query": query,
                "execution_plan": state["execution_plan"],
                "tool_results": state["tool_results"],
            }

            state["final_answer"] = await format_tool_result_as_answer(
                combined_results, query, db
            )
            logger.info("✅ 工具结果格式化完成")

        elif state["execution_pattern"] == "agent_only":
            # 仅智能体，看是否有答案
            if state["documents"]:
                # 有文档但没答案，返回文档列表
                state["final_answer"] = None  # 仅检索，不生成答案
                logger.info("📚 仅检索模式，不生成答案")
            else:
                state["final_answer"] = "抱歉，没有找到相关文档。"
                logger.warning("⚠️ 未找到文档")

        state["success"] = True

    except Exception as e:
        logger.error(f"❌ 生成最终答案失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["error"] = str(e)
        state["success"] = False

    return state


# ==================== 决策函数 ====================


def should_execute_steps(state: ExecutionState) -> str:
    """
    决策函数：是否需要执行步骤

    Returns:
        'execute': 需要执行步骤
        'finalize': LLM直接回答，直接到终点
    """
    if state["execution_pattern"] == "llm_direct":
        logger.info("🔀 决策: LLM直接回答 -> 跳过执行")
        return "finalize"
    else:
        logger.info("🔀 决策: 需要执行步骤 -> execute")
        return "execute"


# ==================== 构建LangGraph工作流 ====================

# 1. 初始化 StateGraph
workflow = StateGraph(ExecutionState)

# 2. 添加所有节点
workflow.add_node("plan", plan_execution)  # 节点: 执行计划
workflow.add_node("execute", execute_steps)  # 节点: 执行步骤
workflow.add_node("finalize", finalize_answer)  # 节点: 生成最终答案

# 3. 设置图的入口点
workflow.set_entry_point("plan")

# 4. 添加条件边：规划后决定走向
workflow.add_conditional_edges(
    "plan",
    should_execute_steps,
    {
        "execute": "execute",  # 需要执行步骤
        "finalize": "finalize",  # LLM直接回答
    },
)

# 5. 添加线性边
workflow.add_edge("execute", "finalize")  # 执行完成 -> 生成答案
workflow.add_edge("finalize", END)  # 生成答案 -> 结束

# 6. 编译图
master_router_app: CompiledStateGraph = workflow.compile()

logger.info("✅ LangGraph 主路由器工作流编译完成")
logger.info("📊 工作流程: 执行计划 -> [执行步骤 | 跳过] -> 生成答案")
