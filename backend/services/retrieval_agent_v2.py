"""
检索智能体 V2 - 基于工具调用

通过调用检索工具完成文档检索任务，而不是直接实现检索逻辑
"""

from typing import Any, Dict, List, Optional, TypedDict
from loguru import logger
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_tools import execute_tool_call, TOOLS_SCHEMA


# ==================== 检索智能体状态定义 ====================


class RetrievalAgentState(TypedDict):
    """
    检索智能体状态机

    工作流程：
    1. 分析查询 -> LLM 分析用户查询，制定检索策略
    2. 执行检索 -> 调用检索工具（ES/SQL/混合）
    3. 后处理 -> 去重、排序、筛选
    """

    # === 必需输入 ===
    query: str  # 用户查询
    template_id: int  # 模板ID
    session_id: str  # 会话ID

    # === 配置参数 ===
    top_k: int  # 返回文档数量
    enable_deduplication: bool  # 是否去重

    # === 步骤1: 分析查询 ===
    retrieval_strategy: str  # 检索策略: "es_only", "sql_only", "hybrid"
    reasoning: str  # LLM的推理过程

    # === 步骤2: 执行检索 ===
    tool_calls: List[Dict[str, Any]]  # 工具调用记录
    tool_results: List[Dict[str, Any]]  # 工具返回结果
    document_ids: List[int]  # 文档ID列表

    # === 步骤3: 后处理 ===
    final_documents: List[Dict[str, Any]]  # 最终文档结果


# ==================== 节点1: 分析查询并制定检索策略 ====================


async def analyze_query_and_plan(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点1: 分析查询并制定检索策略

    让LLM分析用户查询，决定使用哪种检索策略
    """
    logger.info("========== 检索智能体 - 节点1: 分析查询 ==========")

    from utils.llm_client import get_llm_client
    import json

    db: AsyncSession = config.get("configurable", {}).get("db")

    query = state["query"]
    template_id = state["template_id"]

    llm_client = get_llm_client()

    # 构建提示词
    prompt = f"""你是一个检索策略规划专家。分析用户查询，制定最优的检索策略。

【用户查询】
{query}

【模板ID】
{template_id}

【可用的检索策略】
1. **ES全文检索** (es_only): 
   - 适用于: 基于关键词、语义匹配的查询
   - 优势: 快速、支持模糊匹配
   - 工具: es_fulltext_search
   - 特殊参数: 如需查询所有文档，将query设置为"__match_all__"

2. **SQL结构化检索** (sql_only):
   - 适用于: 需要精确匹配分类、编码的查询
   - 优势: 精确、支持复杂条件
   - 工具: sql_structured_search

3. **混合检索** (hybrid):
   - 适用于: 需要同时考虑语义和结构的查询
   - 优势: 召回更全面
   - 工具: 先ES再SQL，或先SQL再ES

【分析任务】
请分析用户查询，判断应该使用哪种检索策略，并说明原因。

**重要提示**：
- 如果用户想查询"所有文档"、"全部文档"、"列出所有"等，请将query参数设置为"__match_all__"
- 如果用户提到具体关键词或主题，请提取关键词作为query参数
- 如果用户提到分类编码，请使用SQL结构化检索

【返回格式】
返回JSON格式：
{{
    "retrieval_strategy": "es_only" | "sql_only" | "hybrid",
    "reasoning": "为什么选择这个策略",
    "tool_calls": [
        {{
            "tool_name": "工具名称",
            "arguments": {{"参数": "值"}},
            "description": "这一步要做什么"
        }}
    ]
}}

【示例1 - 关键词查询】
查询: "关于安全的文档"
返回:
{{
    "retrieval_strategy": "es_only",
    "reasoning": "用户查询是关键词匹配，适合用ES全文检索",
    "tool_calls": [
        {{
            "tool_name": "es_fulltext_search",
            "arguments": {{"query": "安全", "template_id": {template_id}, "top_k": 20}},
            "description": "使用ES检索包含'安全'的文档"
        }}
    ]
}}

【示例2 - 查询所有文档】
查询: "有几个文档，都讲了什么内容"
返回:
{{
    "retrieval_strategy": "es_only",
    "reasoning": "用户想查看所有文档并了解内容，使用match_all检索",
    "tool_calls": [
        {{
            "tool_name": "es_fulltext_search",
            "arguments": {{"query": "__match_all__", "template_id": {template_id}, "top_k": 100}},
            "description": "检索所有文档以了解文档内容"
        }}
    ]
}}

【示例3 - 结构化查询】
查询: "查找分类01的文档"
返回:
{{
    "retrieval_strategy": "sql_only",
    "reasoning": "用户指定了分类编码，使用SQL结构化检索更精确",
    "tool_calls": [
        {{
            "tool_name": "sql_structured_search",
            "arguments": {{"template_id": {template_id}, "class_code": "01", "top_k": 50}},
            "description": "使用SQL检索分类01的文档"
        }}
    ]
}}

现在请分析这个查询并制定策略。只返回JSON，不要其他内容。
"""

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": "你是一个检索策略规划专家"},
                {"role": "user", "content": prompt},
            ],
            db=db,
        )

        logger.info(f"📋 检索策略: {json.dumps(response, ensure_ascii=False)}")

        state["retrieval_strategy"] = response.get(
            "retrieval_strategy", "es_only")
        state["reasoning"] = response.get("reasoning", "")
        state["tool_calls"] = response.get("tool_calls", [])

    except Exception as e:
        logger.error(f"❌ 分析查询失败: {e}")
        # 降级策略：默认使用ES检索
        state["retrieval_strategy"] = "es_only"
        state["reasoning"] = f"分析失败，使用默认ES检索: {str(e)}"
        state["tool_calls"] = [
            {
                "tool_name": "es_fulltext_search",
                "arguments": {
                    "query": query,
                    "template_id": template_id,
                    "top_k": state.get("top_k", 20),
                },
                "description": "默认ES全文检索",
            }
        ]

    return state


# ==================== 节点2: 执行检索工具 ====================


async def execute_retrieval_tools(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点2: 执行检索工具

    根据规划的工具调用列表，依次执行检索工具
    """
    logger.info("========== 检索智能体 - 节点2: 执行检索工具 ==========")

    db: AsyncSession = config.get("configurable", {}).get("db")
    es_client = config.get("configurable", {}).get("es")
    es_index = config.get("configurable", {}).get(
        "es_index", "dochive_documents")

    tool_calls = state.get("tool_calls", [])
    tool_results = []
    all_document_ids = []

    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call.get("tool_name")
        arguments = tool_call.get("arguments", {})
        description = tool_call.get("description", "")

        logger.info(f"🔧 执行第{i+1}个工具: {tool_name} - {description}")

        try:
            # 执行工具
            result = await execute_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                db=db,
                es_client=es_client,
                es_index=es_index,
            )

            tool_results.append({
                "tool_name": tool_name,
                "arguments": arguments,
                "description": description,
                "result": result,
            })

            # 收集文档ID
            if result.get("success"):
                doc_ids = result.get("document_ids", [])
                all_document_ids.extend(doc_ids)
                logger.info(f"✅ 工具执行成功，召回 {len(doc_ids)} 篇文档")
            else:
                logger.warning(f"⚠️ 工具执行失败: {result.get('error')}")

        except Exception as e:
            logger.error(f"❌ 执行工具 {tool_name} 异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
            tool_results.append({
                "tool_name": tool_name,
                "arguments": arguments,
                "description": description,
                "result": {"success": False, "error": str(e)},
            })

    state["tool_results"] = tool_results
    state["document_ids"] = all_document_ids

    logger.info(f"📊 检索完成，共召回 {len(all_document_ids)} 篇文档（可能有重复）")

    return state


# ==================== 节点3: 后处理（去重、获取内容） ====================


async def post_process_results(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点3: 后处理

    1. 去重
    2. 获取文档完整内容
    3. 排序和截断
    """
    logger.info("========== 检索智能体 - 节点3: 后处理 ==========")

    db: AsyncSession = config.get("configurable", {}).get("db")

    document_ids = state.get("document_ids", [])
    enable_deduplication = state.get("enable_deduplication", True)
    top_k = state.get("top_k", 20)

    # 1. 去重
    if enable_deduplication:
        unique_ids = list(dict.fromkeys(document_ids))  # 保持顺序去重
        logger.info(f"🗑️ 去重: {len(document_ids)} -> {len(unique_ids)} 篇文档")
        document_ids = unique_ids

    # 2. 截断到top_k
    if len(document_ids) > top_k:
        logger.info(f"✂️ 截断: {len(document_ids)} -> {top_k} 篇文档")
        document_ids = document_ids[:top_k]

    # 3. 智能选择阅读模式：粗读 vs 精读
    if document_ids:
        try:
            # 让LLM分析查询意图，决定阅读模式
            from utils.llm_client import get_llm_client
            import json

            llm_client = get_llm_client()
            query = state["query"]

            prompt = f"""你是一个阅读策略规划助手。根据用户的查询，判断应该使用哪种阅读模式。

【用户查询】
{query}

【检索到的文档数量】
{len(document_ids)} 篇文档

【可用的阅读模式】
1. **粗读模式** (skim):
   - 只获取标题和AI摘要
   - 适用场景：统计数量、了解大致内容、概述主题
   - 示例：“有多少文档”、“都讲了什么”
   - 优势：速度快、节省Token

2. **精读模式** (read):
   - 获取完整正文内容
   - 适用场景：需要具体细节、深入理解、提取详细信息
   - 示例：“详细说明”、“具体措施是什么”、“我想知道详细信息”
   - 优势：信息完整、细节准确

【分析任务】
请分析用户查询的意图，判断应该使用哪种阅读模式。

**重要提示**：
- 如果用户明确要求“详细”、“具体”、“完整”、“详细信息”等，选择 **read**
- 如果只是统计、概述、了解大致，选择 **skim**
- 如果文档数量 > 10，建议使用 **skim** 避免超过LLM上下文限制

【返回格式】
返回JSON格式：
{{
    "reading_mode": "skim" | "read",
    "reasoning": "为什么选择这个模式"
}}

只返回JSON，不要其他内容。
"""

            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": "你是一个阅读策略规划助手"},
                    {"role": "user", "content": prompt},
                ],
                db=db,
            )

            reading_mode = response.get("reading_mode", "skim")
            reasoning = response.get("reasoning", "")

            logger.info(f"📚 阅读模式选择: {reading_mode} - {reasoning}")

            # 根据选择的模式调用不同的工具
            if reading_mode == "read":
                # 精读：获取完整正文
                result = await execute_tool_call(
                    tool_name="read_documents",
                    arguments={
                        "document_ids": document_ids,
                        "max_documents": min(len(document_ids), 10),
                    },
                    db=db,
                )
            else:
                # 粗读：只获取标题+摘要
                result = await execute_tool_call(
                    tool_name="skim_documents",
                    arguments={
                        "document_ids": document_ids,
                    },
                    db=db,
                )

            if result.get("success"):
                documents = result.get("documents", [])
                state["final_documents"] = documents
                logger.info(
                    f"✅ 获取文档内容成功 ({reading_mode} 模式): {len(documents)} 篇")
            else:
                logger.error(f"❌ 获取文档内容失败: {result.get('error')}")
                state["final_documents"] = []
        except Exception as e:
            logger.error(f"❌ 选择阅读模式失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 降级：默认使用粗读
            result = await execute_tool_call(
                tool_name="skim_documents",
                arguments={"document_ids": document_ids},
                db=db,
            )
            state["final_documents"] = result.get("documents", [])
    else:
        logger.warning("⚠️ 没有文档ID，跳过内容获取")
        state["final_documents"] = []

    return state


# ==================== 工作流构建 ====================


def build_retrieval_agent_v2() -> CompiledStateGraph:
    """
    构建检索智能体V2的工作流

    工作流程:
    1. 分析查询并制定检索策略
    2. 执行检索工具
    3. 后处理（去重、获取内容）
    """
    workflow = StateGraph(RetrievalAgentState)

    # 添加节点
    workflow.add_node("analyze_query", analyze_query_and_plan)
    workflow.add_node("execute_tools", execute_retrieval_tools)
    workflow.add_node("post_process", post_process_results)

    # 设置入口点
    workflow.set_entry_point("analyze_query")

    # 添加边
    workflow.add_edge("analyze_query", "execute_tools")
    workflow.add_edge("execute_tools", "post_process")
    workflow.add_edge("post_process", END)

    # 编译
    app = workflow.compile()

    logger.info("✅ 检索智能体V2工作流编译完成")
    logger.info("📊 工作流程: 分析查询 → 执行检索工具 → 后处理")

    return app


# 创建全局实例
retrieval_agent_v2 = build_retrieval_agent_v2()


# ==================== 便捷调用接口 ====================


async def retrieve_documents_v2(
    query: str,
    template_id: int,
    session_id: str,
    db: AsyncSession,
    es_client: Any,
    es_index: str = "dochive_documents",
    top_k: int = 20,
    enable_deduplication: bool = True,
) -> Dict[str, Any]:
    """
    检索文档V2 - 便捷调用接口

    Args:
        query: 用户查询
        template_id: 模板ID
        session_id: 会话ID
        db: 数据库会话
        es_client: Elasticsearch客户端
        es_index: ES索引名
        top_k: 返回文档数量
        enable_deduplication: 是否去重

    Returns:
        检索结果
    """
    logger.info(f"🔍 检索智能体V2: query='{query}', template_id={template_id}")

    # 初始化状态
    initial_state: RetrievalAgentState = {
        "query": query,
        "template_id": template_id,
        "session_id": session_id,
        "top_k": top_k,
        "enable_deduplication": enable_deduplication,
        # 以下字段在节点中填充
        "retrieval_strategy": "",
        "reasoning": "",
        "tool_calls": [],
        "tool_results": [],
        "document_ids": [],
        "final_documents": [],
    }

    # 执行工作流
    config = {
        "configurable": {
            "db": db,
            "es": es_client,
            "es_index": es_index,
        }
    }

    try:
        result_state = await retrieval_agent_v2.ainvoke(initial_state, config)

        final_documents = result_state.get("final_documents", [])

        logger.info(f"✅ 检索完成，共获得 {len(final_documents)} 篇文档")

        return {
            "success": True,
            "documents": final_documents,
            "total_count": len(final_documents),
            "retrieval_strategy": result_state.get("retrieval_strategy"),
            "reasoning": result_state.get("reasoning"),
            "tool_results": result_state.get("tool_results", []),
        }

    except Exception as e:
        logger.error(f"❌ 检索失败: {e}")
        import traceback
        logger.error(traceback.format_exc())

        return {
            "success": False,
            "error": str(e),
            "documents": [],
            "total_count": 0,
        }
