"""
检索智能体 V2 - 混合检索（ES + SQL）+ 质量评估

固定策略：每次都执行 ES全文检索 + SQL结构化检索
质量控制：评估SQL提取质量，UNKNOWN过多则跳过SQL
结果合并：按文档ID求交集，交集为空或SQL质量不足则使用ES结果
"""

from typing import Any, Dict, List, TypedDict
from loguru import logger
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from services.agent_tools import execute_tool_call, deduplicate_documents


# ==================== 检索智能体状态定义 ====================


class RetrievalAgentState(TypedDict):
    """
    检索智能体状态机

    工作流程：
    0. 查询优化 -> LLM提取关键词（必须/相关/排除）
    1. ES全文检索 -> 召回候选文档
    2. SQL结构化检索 -> 基于模板层级定义精确过滤
    3. SQL质量评估 -> 判断提取质量是否可靠
    4. 求交集 -> 两种检索结果求交集（质量不足或交集为空则用ES）
    5. 后处理 -> 获取内容、去重、截断
    """

    # === 必需输入 ===
    query: str  # 用户查询
    template_id: int  # 模板ID
    session_id: str  # 会话ID

    # === 配置参数 ===
    top_k: int  # 返回文档数量
    enable_deduplication: bool  # 是否去重

    # === 步靨0: 查询优化 ===
    optimized_query: Dict[str, Any]  # 优化后的查询（包含必须/相关/排除关键词）

    # === 步靨1: ES检索 ===
    es_document_ids: List[int]  # ES召回的文档ID

    # === 步骤2: SQL结构化检索 ===
    class_template_levels: List[Dict[str, Any]]  # 模板层级定义
    sql_extracted_conditions: List[Dict[str, Any]]  # LLM提取的结构化条件
    sql_document_ids: List[int]  # SQL召回的文档ID
    sql_quality_passed: bool  # SQL查询质量是否通过（是否应该使用SQL结果）
    sql_skip_reason: str  # 如果跳过SQL，记录原因

    # === 步骤3: 求交集 ===
    final_document_ids: List[int]  # 交集后的文档ID（或ES结果）

    # === 步骤4: 后处理 ===
    final_documents: List[Dict[str, Any]]  # 最终文档结果


# ==================== 节点0: 查询优化 ====================


async def optimize_query(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点0: 查询优化

    使用LLM分析用户查询，提取关键词：
    1. must_keywords: 必须出现的关键词
    2. should_keywords: 可能出现的相关关键词
    3. must_not_keywords: 不应该出现的关键词
    """
    logger.info("========== 检索智能体 - 节点0: 查询优化 ===========")

    from utils.llm_client import get_llm_client
    import json

    db: AsyncSession = config.get("configurable", {}).get("db")
    query = state["query"]

    # 构造提示词
    prompt = f"""你是一个智能查询优化助手。请分析用户的自然语言查询，提取出关键词。

【用户查询】
{query}

【提取任务】
请分析查询，提取三类关键词：

1. **must_keywords** (必须出现): 文档中必须包含的核心关键词
   - 示例：查询“火山的处置措施” → [“火山”, “措施”]
   
2. **should_keywords** (可能出现): 相关的近义词、扩展词
   - 示例：查询“火山的处置措施” → [“应急预案”, “处置”, “防范”, “应对”]
   
3. **must_not_keywords** (不应出现): 需要排除的干扰词
   - 示例：查询“火山的处置措施” → [“地震”, “洪水”, “台风”] (排除其他灾害类型)

【提取原则】
- must_keywords: 提取用户查询中的核心名词和动词，通常是2-5个
- should_keywords: 扩展相关词，包括近义词、上下位词、常见搭配词
- must_not_keywords: 分析查询意图，推断需要排除的干扰词（例如其他类型、相反含义等）
- 如果某一类没有合适的词，返回空数组

【返回格式】
返回JSON格式：
{{
    "must_keywords": ["keyword1", "keyword2"],
    "should_keywords": ["keyword3", "keyword4"],
    "must_not_keywords": ["keyword5", "keyword6"]
}}

请分析并返回JSON，不要其他内容。
    """

    try:
        llm_client = get_llm_client()
        response = await llm_client.extract_json_response(prompt, db=db)

        optimized_query = {
            "original_query": query,
            "must_keywords": response.get("must_keywords", []),
            "should_keywords": response.get("should_keywords", []),
            "must_not_keywords": response.get("must_not_keywords", []),
        }

        state["optimized_query"] = optimized_query

        logger.info(f"🔍 查询优化结果:")
        logger.info(f"   ✅ 必须关键词: {optimized_query['must_keywords']}")
        logger.info(f"   🔵 相关关键词: {optimized_query['should_keywords']}")
        logger.info(f"   ❌ 排除关键词: {optimized_query['must_not_keywords']}")

    except Exception as e:
        logger.error(f"❌ 查询优化失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # 降级：直接使用原始查询
        state["optimized_query"] = {
            "original_query": query,
            "must_keywords": [],
            "should_keywords": [],
            "must_not_keywords": [],
        }

    return state


# ==================== 节点1: ES全文检索 ====================


async def es_fulltext_retrieval(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点1: ES全文检索

    使用Elasticsearch进行全文检索，召回候选文档
    """
    logger.info("========== 检索智能体 - 节点1: ES全文检索 ===========")

    es_client = config.get("configurable", {}).get("es")
    es_index = config.get("configurable", {}).get(
        "es_index", "dochive_documents")

    query = state["query"]
    template_id = state["template_id"]
    top_k = state.get("top_k", 20)
    optimized_query = state.get("optimized_query", {})

    try:
        result = await execute_tool_call(
            tool_name="es_fulltext_search",
            arguments={
                "query": query,
                "template_id": template_id,
                "top_k": top_k * 2,  # 多检索一些，留给后面交集
                "optimized_query": optimized_query,  # 传入优化后的查询
            },
            es_client=es_client,
            es_index=es_index,
            db=config.get("configurable", {}).get("db"),
        )

        if result.get("success"):
            document_ids = result.get("document_ids", [])
            state["es_document_ids"] = document_ids
            logger.info(f"✅ ES检索完成，召回 {len(document_ids)} 篇文档")
        else:
            logger.error(f"❌ ES检索失败: {result.get('error')}")
            state["es_document_ids"] = []

    except Exception as e:
        logger.error(f"❌ ES检索异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
        state["es_document_ids"] = []

    return state


# ==================== 节点2: SQL结构化检索 ====================


async def sql_structured_retrieval(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点2: SQL结构化检索

    基于模板层级定义，使用LLM提取结构化查询条件，
    在数据库中进行精确的结构化检索。
    """
    logger.info("========== 检索智能体 - 节点2: SQL结构化检索 ===========")

    from utils.llm_client import get_llm_client
    from services.template_service import TemplateService
    from models.database_models import TemplateDocumentMapping
    from sqlalchemy import select, or_
    import json

    db: AsyncSession = config.get("configurable", {}).get("db")

    query = state["query"]
    template_id = state["template_id"]

    # 1. 获取模板层级定义
    cls_template = await TemplateService.get_template(db, template_id)

    if not cls_template:
        logger.warning("⚠️ 未找到模板，跳过SQL结构化检索")
        state["class_template_levels"] = []
        state["sql_extracted_conditions"] = []
        state["sql_document_ids"] = []
        return state

    # 使用property获取层级定义
    cls_template_levels = cls_template.levels
    if not isinstance(cls_template_levels, list):
        logger.error("❌ 模板层级定义格式错误")
        state["class_template_levels"] = []
        state["sql_extracted_conditions"] = []
        state["sql_document_ids"] = []
        return state

    state["class_template_levels"] = cls_template_levels
    logger.info(f"📋 模板层级定义: {len(cls_template_levels)} 个层级")

    # 2. 使用LLM提取结构化条件
    prompt = f"""
你是一个智能结构化查询助手。
用户会给出一个自然语言检索请求，请你根据以下字段定义，提取出结构化的检索条件。

字段定义:
{json.dumps(cls_template_levels, ensure_ascii=False, indent=2)}

要求:
1. 输出JSON对象，格式: {{"conditions": [{{"code": "字段编码", "value": "提取值", "level": 层级}}]}}
2. 如果无法从查询中推理出某个字段，value设为"UNKNOWN"
3. 只提取用户明确提到的信息，不要猜测

用户查询:
{query}

请直接输出JSON，不要解释。
    """

    try:
        llm_client = get_llm_client()
        llm_response = await llm_client.extract_json_response(prompt, db=db)
        logger.info(f"🤖 LLM提取的结构化条件: {llm_response}")

        conditions = llm_response.get("conditions", [])
        state["sql_extracted_conditions"] = conditions

    except Exception as e:
        logger.error(f"❌ LLM提取结构化条件失败: {e}")
        state["sql_extracted_conditions"] = []

    # 3. 构造SQL查询条件
    conditions_clauses = []
    for cond in state["sql_extracted_conditions"]:
        value = cond.get("value")
        if value and value != "UNKNOWN":
            if isinstance(value, list):
                for v in value:
                    conditions_clauses.append(
                        TemplateDocumentMapping.class_code.like(f"%{v}%")
                    )
            else:
                conditions_clauses.append(
                    TemplateDocumentMapping.class_code.like(f"%{value}%")
                )

    # 4. 执行SQL查询
    stmt = select(TemplateDocumentMapping.document_id).where(
        TemplateDocumentMapping.template_id == template_id
    )
    if conditions_clauses:
        stmt = stmt.where(or_(*conditions_clauses))

    try:
        result = await db.execute(stmt)
        document_ids = [row[0] for row in result.all()]
        state["sql_document_ids"] = document_ids

        logger.info(f"✅ SQL结构化检索召回 {len(document_ids)} 篇文档")

    except Exception as e:
        logger.error(f"❌ SQL查询失败: {e}")
        state["sql_document_ids"] = []

    return state


# ==================== 节点2.5: SQL质量评估 ====================


async def evaluate_sql_quality(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点2.5: SQL质量评估

    分析提取的结构化条件，判断是否有足够的有效信息来执行SQL查询。
    如果UNKNOWN值过多（>2），则跳过SQL结果。
    """
    logger.info("========== 检索智能体 - 节点2.5: SQL质量评估 ===========")

    from utils.llm_client import get_llm_client
    import json

    db: AsyncSession = config.get("configurable", {}).get("db")

    conditions = state.get("sql_extracted_conditions", [])
    template_levels = state.get("class_template_levels", [])

    # 如果没有模板层级定义或没有提取到条件，直接跳过SQL
    if not template_levels or not conditions:
        state["sql_quality_passed"] = False
        state["sql_skip_reason"] = "模板层级定义或提取条件为空"
        logger.warning(f"⚠️ SQL质量评估: 跳过 - {state['sql_skip_reason']}")
        return state

    # 1. 统计UNKNOWN数量
    unknown_count = sum(
        1 for cond in conditions if cond.get("value") == "UNKNOWN")
    total_count = len(conditions)

    logger.info(f"📊 提取结果: 总计{total_count}个编码，其中{unknown_count}个UNKNOWN")

    # 2. 让LLM分析哪些字段是必需的
    prompt = f"""
你是一个结构化查询质量评估专家。

【模板层级定义】
{json.dumps(template_levels, ensure_ascii=False, indent=2)}

【提取到的结构化条件】
{json.dumps(conditions, ensure_ascii=False, indent=2)}

【分析任务】
1. 分析模板层级定义，识别出哪些字段是业务上必须准确识别的（例如：标记为is_required=true的字段，或者低层级的关键字段）
2. 检查提取结果中，必需字段是否被准确识别（value不为"UNKNOWN"）
3. 判断SQL查询的质量是否可靠

【判断规则】
- 如果UNKNOWN数量 > 2，则认为信息不足，质量不可靠
- 如果必需字段有UNKNOWN，也认为质量不可靠
- 否则认为质量可靠

【返回格式】
返回JSON格式：
{{
    "passed": true | false,
    "reasoning": "判断理由",
    "required_fields": ["必需字段列表"],
    "missing_required": ["缺失的必需字段"]
}}

请分析并返回JSON：
    """

    try:
        llm_client = get_llm_client()
        evaluation = await llm_client.extract_json_response(prompt, db=db)
        logger.info(f"🤖 LLM评估结果: {evaluation}")

        passed = evaluation.get("passed", False)
        reasoning = evaluation.get("reasoning", "")

        state["sql_quality_passed"] = passed

        if not passed:
            state["sql_skip_reason"] = reasoning
            logger.warning(f"⚠️ SQL质量不足，将跳过SQL结果: {reasoning}")
        else:
            state["sql_skip_reason"] = ""
            logger.info(f"✅ SQL质量通过: {reasoning}")

    except Exception as e:
        logger.error(f"❌ SQL质量评估失败: {e}")
        # 默认通过，避免评估失败影响检索
        state["sql_quality_passed"] = True
        state["sql_skip_reason"] = ""

    return state


# ==================== 节点3: 求交集 ====================


async def merge_results(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点3: 求交集

    将ES和SQL的检索结果求交集，如果SQL质量不足或交集为空则使用ES结果
    """
    logger.info("========== 检索智能体 - 节点3: 求交集 ===========")

    es_ids = set(state.get("es_document_ids", []))
    sql_ids = set(state.get("sql_document_ids", []))
    sql_quality_passed = state.get("sql_quality_passed", False)
    sql_skip_reason = state.get("sql_skip_reason", "")

    logger.info(f"🔵 ES结果: {len(es_ids)} 篇文档")
    logger.info(f"🟢 SQL结果: {len(sql_ids)} 篇文档")
    logger.info(f"📊 SQL质量: {'✅ 通过' if sql_quality_passed else '❌ 不通过'}")

    # 判断是否使用SQL结果
    if not sql_quality_passed:
        # SQL质量不足，直接使用ES结果
        state["final_document_ids"] = list(es_ids)
        logger.warning(
            f"⚠️ SQL质量不足，跳过SQL结果，直接使用ES结果: {len(es_ids)} 篇文档\n"
            f"   原因: {sql_skip_reason}"
        )
        return state

    # SQL质量通过，求交集
    intersection = list(es_ids & sql_ids)

    if intersection:
        # 交集不为空，使用交集结果
        state["final_document_ids"] = intersection
        logger.info(f"✅ 交集结果: {len(intersection)} 篇文档")
    else:
        # 交集为空，使用ES结果
        state["final_document_ids"] = list(es_ids)
        logger.warning(f"⚠️ 交集为空，使用ES结果: {len(es_ids)} 篇文档")

    return state


# ==================== 节点4: 后处理（获取内容、去重、截断） ====================


async def post_process_results(
    state: RetrievalAgentState, config: RunnableConfig
) -> RetrievalAgentState:
    """
    节点4: 后处理

    1. 获取文档完整内容
    2. 内容去重
    3. 截断到top_k
    """
    logger.info("========== 检索智能体 - 节点4: 后处理 ===========")

    db: AsyncSession = config.get("configurable", {}).get("db")

    document_ids = state.get("final_document_ids", [])
    enable_deduplication = state.get("enable_deduplication", True)
    top_k = state.get("top_k", 20)

    # 1. 获取文档内容（直接查询数据库，获取完整内容）
    if document_ids:
        try:
            result = await execute_tool_call(
                tool_name="read_documents",
                arguments={
                    "document_ids": document_ids,
                    "max_documents": 100,  # 先获取所有文档，后面再去重和截断
                },
                db=db,
            )

            if result.get("success"):
                documents = result.get("documents", [])
                logger.info(f"📄 获取到文档: {len(documents)} 篇")

                # 2. 基于内容的高级去重（如果开启了去重）
                if enable_deduplication and len(documents) > 1:
                    before_count = len(documents)
                    documents = deduplicate_documents(documents)
                    logger.info(
                        f"🗑️ 内容去重: {before_count} -> {len(documents)} 篇文档")

                # 3. 截断到top_k
                if len(documents) > top_k:
                    logger.info(f"✂️ 截断: {len(documents)} -> {top_k} 篇文档")
                    documents = documents[:top_k]

                state["final_documents"] = documents
                logger.info(f"✅ 文档处理完成: {len(documents)} 篇")
            else:
                logger.error(f"❌ 获取文档内容失败: {result.get('error')}")
                state["final_documents"] = []
        except Exception as e:
            logger.error(f"❌ 后处理失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            state["final_documents"] = []
    else:
        logger.warning("⚠️ 没有文档ID，跳过内容获取")
        state["final_documents"] = []

    return state


# ==================== 工作流构建 ====================


def build_retrieval_agent_v2() -> CompiledStateGraph:
    """
    构建检索智能体V2的工作流

    工作流程:
    1. ES全文检索
    2. SQL结构化检索
    3. SQL质量评估
    4. 求交集
    5. 后处理（去重、获取内容）
    """
    workflow = StateGraph(RetrievalAgentState)

    # 添加节点
    workflow.add_node("optimize_query", optimize_query)
    workflow.add_node("es_retrieval", es_fulltext_retrieval)
    workflow.add_node("sql_retrieval", sql_structured_retrieval)
    workflow.add_node("sql_quality_eval", evaluate_sql_quality)
    workflow.add_node("merge", merge_results)
    workflow.add_node("post_process", post_process_results)

    # 设置入口点
    workflow.set_entry_point("optimize_query")

    # 添加边
    workflow.add_edge("optimize_query", "es_retrieval")
    workflow.add_edge("es_retrieval", "sql_retrieval")
    workflow.add_edge("sql_retrieval", "sql_quality_eval")
    workflow.add_edge("sql_quality_eval", "merge")
    workflow.add_edge("merge", "post_process")
    workflow.add_edge("post_process", END)

    # 编译
    app = workflow.compile()

    logger.info("✅ 检索智能体V2工作流编译完成")
    logger.info("📋 工作流程: 查询优化 → ES检索 → SQL检索 → SQL质量评估 → 求交集 → 后处理")

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
        "optimized_query": {},
        "es_document_ids": [],
        "class_template_levels": [],
        "sql_extracted_conditions": [],
        "sql_document_ids": [],
        "sql_quality_passed": False,
        "sql_skip_reason": "",
        "final_document_ids": [],
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
