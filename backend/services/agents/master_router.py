""" 
主路由器V3 - 简单三步执行流程

功能：
1. 第一步：规划 - LLM选择合适的工具/智能体
2. 第二步：执行 - 异步顺序执行规划的步骤
3. 第三步：总结 - 格式化最终结果

特点：不使用LangGraph，直接异步执行，每步实时yield
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.agents.retrieval_agent import retrieve_documents_v2
from services.agents.qa_agent import generate_answer_v2
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

示例4 - 混合调用（概览所有文档+智能分析）：
问题: "有多少文档，每一份都详细归纳一下内容"
返回:
{{
    "execution_pattern": "tool_only",
    "reasoning": "用户想了解所有文档的详细内容，需要读取文档并分析",
    "execution_plan": [
        {{
            "step": 1,
            "type": "tool",
            "name": "get_template_statistics",
            "description": "获取文档数量统计"
        }},
        {{
            "step": 2,
            "type": "tool",
            "name": "search_documents_by_classification",
            "description": "获取所有文档ID列表"
        }},
        {{
            "step": 3,
            "type": "tool",
            "name": "get_document_contents",
            "description": "读取文档完整原文"
        }},
        {{
            "step": 4,
            "type": "tool",
            "name": "analyze_documents",
            "description": "智能分析文档（内部自动决定批量or逐份）"
        }}
    ],
    "direct_answer": null
}}

示例5 - 语义检索+问答：
问题: "查找关于地震应急的文档，并总结主要内容"
返回:
{{
    "execution_pattern": "agent_chain",
    "reasoning": "需要语义检索特定主题的文档，然后生成答案",
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
            "description": "总结内容"
        }}
    ],
    "direct_answer": null
}}

示例6 - LLM直接回答：
问题: "什么是人工智能？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是通用知识问题，不需要查询文档，直接回答",
    "execution_plan": [],
    "direct_answer": "人工智能（Artificial Intelligence, AI）是计算机科学的一个分支..."
}}

【重要提示】
- 如果用户要分析文档内容（"总结"、"归纳"、"都讲了什么"），使用 analyze_documents 工具（它会内部决定批量or逐份）
- 如果用户问"查找XXX相关的文档"等语义检索问题，使用 retrieval_agent 智能体
- 区分"文档分析"和"语义检索"两种场景

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
    节点: 执行步骤（异步顺序执行）
    """
    logger.info("🚀 ========== 节点: 执行步骤 ===========")

    query = state["query"]
    template_id = state["template_id"]
    session_id = state["session_id"]

    # 从 config 获取所需资源
    db: AsyncSession = config.get("configurable", {}).get("db")
    es_client = config.get("configurable", {}).get("es")
    es_index: str = config.get("configurable", {}).get(
        "es_index", "dochive_documents")
    max_read_documents = config.get(
        "configurable", {}).get("max_read_documents", 10)
    rag_max_length = config.get(
        "configurable", {}).get("rag_max_length", 10000)

    # helper: 实际调用工具/智能体实现 - 使用通用调用机制
    async def _dispatch_to_impl(step_type: str, step_name: str):
        """
        通用的工具/智能体调度器
        - 工具调用：使用 tool_registry.execute_tool_call 统一处理
        - 智能体调用：直接调用智能体函数
        """
        if step_type == "tool":
            # 使用通用的工具执行器
            from services.tools.tool_registry import execute_tool_call

            # 准备工具参数
            arguments = {"template_id": template_id}

            # 特殊处理：从 state 中获取中间数据
            if step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                arguments["document_ids"] = state["intermediate_data"].get(
                    "document_ids", [])
                if step_name == "read_documents":
                    arguments["max_documents"] = max_read_documents
            elif step_name == "analyze_documents":
                # analyze_documents 需要特殊处理（参数不标准）
                from services.tools.analysis.document_analyzer import analyze_documents
                documents = state["intermediate_data"].get("documents", [])
                return await analyze_documents(
                    query=query,
                    documents=documents,
                    db=db,
                    max_context_length=rag_max_length,
                )
            elif step_name == "search_documents_by_classification":
                arguments["class_code"] = None  # 默认返回所有文档

            # 调用通用执行器
            return await execute_tool_call(
                tool_name=step_name,
                arguments=arguments,
                db=db,
                es_client=es_client,
                es_index=es_index,
            )

        elif step_type == "agent":
            # 智能体调用：直接调用智能体函数
            if step_name == "retrieval_agent":
                return await retrieve_documents_v2(
                    query=query,
                    template_id=template_id,
                    session_id=session_id,
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                    top_k=20,
                    enable_deduplication=True,
                )
            elif step_name == "qa_agent":
                documents = state["intermediate_data"].get("documents", [])
                return await generate_answer_v2(
                    query=query,
                    documents=documents,
                    db=db,
                    max_context_length=rag_max_length,
                )
            else:
                raise RuntimeError(f"未知的智能体: {step_name}")
        else:
            raise RuntimeError(f"未知的 step_type: {step_type}")

    # 主执行逻辑：逐个异步执行步骤
    plan: List[Dict[str, Any]] = state.get("execution_plan", [])
    try:
        for i, step in enumerate(plan):
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name}")

            try:
                # 执行步骤
                result = await _dispatch_to_impl(step_type, step_name)

                # 记录结果
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": result
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 特殊处理：更新中间数据
                if result.get("success"):
                    if step_type == "agent" and step_name == "retrieval_agent":
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", [])
                        state["documents"] = result.get("documents", [])
                    elif step_type == "tool" and step_name == "search_documents_by_classification":
                        state["intermediate_data"]["document_ids"] = result.get(
                            "document_ids", [])
                    elif step_type == "tool" and step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", [])

                logger.info(f"✅ 步骤{i+1}完成: {step_name}")

            except Exception as e:
                import traceback
                logger.error(f"❌ 步骤{i+1}失败: {step_name}, 错误: {e}")
                logger.error(traceback.format_exc())

                # 记录错误
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": {"success": False, "error": str(e)}
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 继续执行后续步骤（可根据需要调整策略）

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
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    try:
        # 如果已经有答案（qa_agent生成的），直接返回
        if state["final_answer"]:
            logger.info("✅ 已有最终答案，跳过生成")
            state["success"] = True
            return state

        # 根据执行模式生成答案
        if state["execution_pattern"] == "llm_direct":
            # LLM直接回答的情况，已经有答案
            state["success"] = True
            return state

        elif state["execution_pattern"] == "agent_only":
            # 仅检索模式
            if state["documents"]:
                state["final_answer"] = None  # 仅检索，不生成答案
                logger.info("📚 仅检索模式，不生成答案")
            else:
                state["final_answer"] = "抱歉，没有找到相关文档。"
                logger.warning("⚠️ 未找到文档")
            state["success"] = True
            return state

        # 其他模式：根据所有步骤结果生成详细答案
        logger.info("🤖 根据执行结果生成详细答案")

        llm_client = get_llm_client()

        # 构建执行过程描述
        execution_summary = []
        execution_summary.append(f"用户问题：{query}\n")
        execution_summary.append(f"执行模式：{state['execution_pattern']}")
        execution_summary.append(f"执行推理：{state['reasoning']}\n")

        execution_summary.append("执行步骤及结果：")

        # 添加工具执行结果
        for i, tool_result in enumerate(state["tool_results"]):
            step_num = tool_result.get("step", i + 1)
            name = tool_result.get("name", "未知工具")
            desc = tool_result.get("description", "")
            result = tool_result.get("result", {})

            execution_summary.append(f"\n步骤{step_num}：{desc} (工具: {name})")

            if result.get("success"):
                # 根据不同工具类型格式化结果
                if name == "get_template_statistics":
                    # get_template_statistics 直接返回数据，不是嵌套在statistics里
                    total_docs = result.get('total_documents', 0)
                    execution_summary.append(f"  - 文档总数：{total_docs}")

                    # 显示分类分布
                    class_dist = result.get('class_code_distribution', [])
                    if class_dist:
                        execution_summary.append(
                            f"  - 分类分布：{len(class_dist)}个分类")
                        for item in class_dist[:3]:  # 只显示前3个
                            execution_summary.append(
                                f"    * {item.get('class_code', '未知')}: {item.get('count', 0)}篇")
                elif name == "search_documents_by_classification":
                    doc_ids = result.get("document_ids", [])
                    execution_summary.append(f"  - 找到{len(doc_ids)}篇文档")
                elif name in ["get_document_contents", "skim_documents", "read_documents"]:
                    docs = result.get("documents", [])
                    execution_summary.append(f"  - 读取{len(docs)}篇文档")
                    for doc in docs[:3]:  # 只显示前3篇
                        execution_summary.append(
                            f"    * {doc.get('title', '未命名')}")
                elif name == "analyze_documents":
                    analysis = result.get("analysis", "")
                    if analysis:
                        execution_summary.append(
                            f"  - 分析结果：{analysis[:200]}...")
                else:
                    # 通用处理
                    execution_summary.append(f"  - 执行成功")
            else:
                execution_summary.append(
                    f"  - 执行失败：{result.get('error', '未知错误')}")

        # 添加智能体执行结果
        for i, agent_result in enumerate(state["agent_results"]):
            step_num = agent_result.get(
                "step", len(state["tool_results"]) + i + 1)
            name = agent_result.get("name", "未知智能体")
            desc = agent_result.get("description", "")
            result = agent_result.get("result", {})

            execution_summary.append(f"\n步骤{step_num}：{desc} (智能体: {name})")

            if result.get("success"):
                if name == "retrieval_agent":
                    docs = result.get("documents", [])
                    execution_summary.append(f"  - 检索到{len(docs)}篇相关文档")
                    for doc in docs[:5]:  # 显示前5篇
                        execution_summary.append(
                            f"    * {doc.get('title', '未命名')} (相关度: {doc.get('score', 0):.2f})")
                elif name == "qa_agent":
                    answer = result.get("answer", "")
                    execution_summary.append(f"  - 生成答案：{answer[:200]}...")
                else:
                    execution_summary.append(f"  - 执行成功")
            else:
                execution_summary.append(
                    f"  - 执行失败：{result.get('error', '未知错误')}")

        execution_context = "\n".join(execution_summary)

        # 调用LLM生成最终答案
        system_prompt = """你是一个专业的智能助手，负责根据执行过程和结果生成详细的答案。

要求：
1. 按照执行步骤顺序组织答案
2. 每个步骤说明：做了什么、得到了什么结果
3. 用清晰的格式（标题、列表等）呈现
4. 最后总结回答用户的问题
5. 使用Markdown格式

注意：
- 不要编造信息，只使用执行结果中的实际内容
- 如果某步骤失败，说明原因
- 语气友好、专业
"""

        user_prompt = f"""请根据以下执行过程生成详细答案：

{execution_context}

请生成一个清晰、详细、有条理的答案。
"""

        final_answer = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )

        state["final_answer"] = final_answer
        state["success"] = True
        logger.info("✅ 最终答案生成完成")

    except Exception as e:
        logger.error(f"❌ 生成最终答案失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["error"] = str(e)
        state["success"] = False

    return state

# ==================== 简单三步执行函数（不使用LangGraph） ====================


async def execute_master_router(
    query: str,
    template_id: int,
    db: AsyncSession,
    es_client,
    es_index: str = "dochive_documents",
):
    """
    主路由器执行函数：三步流程

    第一步：规划 - LLM选择合适的工具/智能体
    第二步：执行 - 异步顺序执行每一步，yield结果
    第三步：总结 - 格式化最终结果

    Yields:
        dict: 每一步的执行结果
            - type: 'plan' | 'step_result' | 'final'
            - data: 具体数据
    """
    import uuid
    session_id = str(uuid.uuid4())

    # ========== 第一步：规划 ==========
    logger.info("🧠 ========== 第一步：规划 ===========")

    state: ExecutionState = {
        "query": query,
        "template_id": template_id,
        "session_id": session_id,
        "execution_pattern": "",
        "reasoning": "",
        "execution_plan": [],
        "tool_results": [],
        "agent_results": [],
        "intermediate_data": {},
        "final_answer": None,
        "documents": [],
        "success": False,
        "error": None,
    }

    config = {"configurable": {"db": db, "es": es_client, "es_index": es_index}}
    state = await plan_execution(state, config)

    # Yield 执行计划
    yield {
        "type": "plan",
        "data": {
            "execution_pattern": state["execution_pattern"],
            "execution_plan": state["execution_plan"],
            "reasoning": state["reasoning"],
        }
    }

    # ========== 第二步：执行 ==========
    if state["execution_pattern"] != "llm_direct":
        logger.info("🛠️ ========== 第二步：执行 ===========")

        from services.tools.tool_registry import execute_tool_call
        from services.tools.analysis.document_analyzer import analyze_documents

        max_read_documents = 10
        rag_max_length = 10000

        # 逐步执行
        for i, step in enumerate(state["execution_plan"]):
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name}")

            try:
                result = None

                # 执行工具或智能体
                if step_type == "tool":
                    arguments = {"template_id": template_id}

                    if step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                        arguments["document_ids"] = state["intermediate_data"].get(
                            "document_ids", [])
                        if step_name == "read_documents":
                            arguments["max_documents"] = max_read_documents
                    elif step_name == "analyze_documents":
                        # 特殊处理
                        documents = state["intermediate_data"].get(
                            "documents", [])
                        result = await analyze_documents(
                            query=query,
                            documents=documents,
                            db=db,
                            max_context_length=rag_max_length,
                        )
                    elif step_name == "search_documents_by_classification":
                        arguments["class_code"] = None

                    if result is None:
                        result = await execute_tool_call(
                            tool_name=step_name,
                            arguments=arguments,
                            db=db,
                            es_client=es_client,
                            es_index=es_index,
                        )

                elif step_type == "agent":
                    if step_name == "retrieval_agent":
                        result = await retrieve_documents_v2(
                            query=query,
                            template_id=template_id,
                            session_id=session_id,
                            db=db,
                            es_client=es_client,
                            es_index=es_index,
                            top_k=20,
                            enable_deduplication=True,
                        )
                    elif step_name == "qa_agent":
                        documents = state["intermediate_data"].get(
                            "documents", [])
                        result = await generate_answer_v2(
                            query=query,
                            documents=documents,
                            db=db,
                            max_context_length=rag_max_length,
                        )
                    else:
                        raise RuntimeError(f"未知的智能体: {step_name}")
                else:
                    raise RuntimeError(f"未知的 step_type: {step_type}")

                # 记录结果
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": result
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 更新中间数据
                if result.get("success"):
                    if step_type == "agent" and step_name == "retrieval_agent":
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", [])
                        state["documents"] = result.get("documents", [])
                    elif step_type == "tool" and step_name == "search_documents_by_classification":
                        state["intermediate_data"]["document_ids"] = result.get(
                            "document_ids", [])
                    elif step_type == "tool" and step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", [])
                    elif step_type == "agent" and step_name == "qa_agent":
                        state["final_answer"] = result.get("answer")

                logger.info(f"✅ 步骤{i+1}完成: {step_name}")

                # Yield 每一步的结果
                yield {
                    "type": "step_result",
                    "data": {
                        "step": i + 1,
                        "step_type": step_type,
                        "step_name": step_name,
                        "description": step_desc,
                        "result": result,
                        "documents": state.get("documents", []) if step_type == "agent" else None,
                    }
                }

            except Exception as e:
                import traceback
                logger.error(f"❌ 步骤{i+1}失败: {step_name}, 错误: {e}")
                logger.error(traceback.format_exc())

                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": {"success": False, "error": str(e)}
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                yield {
                    "type": "step_result",
                    "data": {
                        "step": i + 1,
                        "step_type": step_type,
                        "step_name": step_name,
                        "description": step_desc,
                        "result": {"success": False, "error": str(e)},
                    }
                }

    # ========== 第三步：总结 ==========
    logger.info("📝 ========== 第三步：总结 ===========")

    state = await finalize_answer(state, config)

    # Yield 最终结果
    yield {
        "type": "final",
        "data": {
            "final_answer": state["final_answer"],
            "documents": state["documents"],
            "success": state["success"],
            "error": state.get("error"),
        }
    }


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
