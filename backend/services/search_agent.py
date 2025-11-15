import json
from typing import Any, Dict, List, Optional, TypedDict, cast
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from elasticsearch import AsyncElasticsearch
from langgraph.graph import END, StateGraph

from config import get_settings
from models.database_models import (
    Document,
    DocumentType,
    DocumentTypeField,
    TemplateDocumentMapping,
)
from services.template_service import TemplateService
from utils.llm_client import llm_client
from loguru import logger

# 全局变量存储graph状态，用于支持中断和恢复
graph_state_storage: Dict[str, Dict[str, Any]] = {}


class RetrievalState(TypedDict):
    """
    RAG 智能体状态机
    """

    # === 必需输入 ===
    query: str
    template_id: int
    db: AsyncSession  # 数据库会话
    es_client: AsyncElasticsearch  # ES 客户端
    session_id: str  # 会话ID，用于状态存储

    # === 节点 0 (SQL 检索) 产出 ===
    class_template_levels: Optional[Any]
    docs: List[Document]  # SQL 粗召回的文档列表
    category: str  # 识别出的文档类别 (来自LLM)
    category_field_code: Optional[str]  # 存储类别的字段名 (例如 'doc_type')

    # === 节点 1 (ES 条件提取) 产出 ===
    document_type_fields: List[DocumentTypeField]  # 类别相关的特定字段
    extracted_llm_json: Optional[Dict[str, Any]]  # LLM 提取的特定条件
    es_query: Optional[Dict[str, Any]]  # 构造的 ES 查询语句

    # === 节点 2 (ES 检索) 产出 ===
    es_results: List[Dict[str, Any]]  # ES 精排后的结果

    # === 节点 3 (歧义处理) 产出 ===
    ambiguity_message: Optional[str]  # 如果有歧义，向用户提问的消息

    # === 节点 4 (最终回答) 产出 ===
    answer: Optional[str]  # 最终的RAG回答


# === 节点 0：查询必要的数据 (SQL粗召回) ===
async def query_necessary_data(state: RetrievalState) -> RetrievalState:
    """根据template_id 查询必要数据，并进行 SQL 粗召回"""
    cls_template = await TemplateService.get_template(state["db"], state["template_id"])
    cls_template_levels = cls_template._levels if cls_template else None

    if isinstance(cls_template_levels, str):
        try:
            cls_template_levels = json.loads(cls_template_levels)
        except Exception:
            raise ValueError("模板字段定义不是合法的JSON")

    state["class_template_levels"] = cls_template_levels  # 保存到 state

    type_code = ""
    for field in cls_template_levels or []:
        if field.get("is_doc_type", False):
            type_code = field.get("code")
            state["category_field_code"] = type_code  # *** 增强点：保存类别字段名 ***

    prompt = f"""
    你是一个智能检索助手。
    用户会给出一个自然语言检索请求，请你根据以下字段定义，推理出最合适的检索条件。

    字段定义如下：
    {cls_template_levels}

    要求：
    1. 输出格式为 JSON 数组。
    2. 每个字段包含以下键：
       - code: 对应字段编码
       - value: 提取结果（字符串或列表）
       - level: 对应层级（数字）
    3. 如果无法从 query 中推理出该字段，请返回 "UNKNOWN"。
    4. 不要生成模板中未定义的字段。

    用户输入：
    {state['query']}

    请直接输出 JSON 数组，不要解释。
    """

    conditions = await llm_client.extract_json_response(prompt, db=state["db"])
    logger.info(f"LLM (Node 0) 输出：{str(conditions)}")

    # 提取类别
    for c in conditions:
        if isinstance(c, dict) and c.get("code") == type_code:
            state["category"] = c.get("value", "*")
            break

    normalized = []
    for f in cls_template_levels or []:
        code = f.get("code")
        level = f.get("level")
        match = next(
            (c for c in conditions if isinstance(c, dict) and c.get("code") == code),
            None,
        )
        value = match.get("value") if isinstance(match, dict) else "UNKNOWN"
        normalized.append({"code": code, "value": value or "UNKNOWN", "level": level})

    logger.info(f"归一化结果 (Node 0)：{str(normalized)}")

    conditions_clauses = []
    for cond in normalized:
        value = cond["value"]
        if value != "UNKNOWN":
            if isinstance(value, list):
                for v in value:
                    conditions_clauses.append(
                        TemplateDocumentMapping.class_code.like(f"%{v}%")
                    )
            else:
                conditions_clauses.append(
                    TemplateDocumentMapping.class_code.like(f"%{value}%")
                )

    stmt = select(TemplateDocumentMapping.document_id).where(
        TemplateDocumentMapping.template_id == state["template_id"]
    )
    if conditions_clauses:
        stmt = stmt.where(or_(*conditions_clauses))

    result = await state["db"].execute(stmt)
    document_ids = [row[0] for row in result.all()]

    if not document_ids:
        logger.warning("Node 0 SQL 粗召回未命中任何文档。")
        state["docs"] = []
        # 保存状态到全局存储
        graph_state_storage[state["session_id"]] = dict(state)
        return state

    docs_result = await state["db"].execute(
        select(Document).where(Document.id.in_(document_ids))
    )
    docs = list(docs_result.scalars().all())
    state["docs"] = docs
    logger.info(f"Node 0 SQL 粗召回 {len(docs)} 篇文档。")

    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)

    return state


# === 节点 1：根据类别信息，提取查询条件 (ES精排准备) ===
async def extract_query_conditions(state: RetrievalState) -> RetrievalState:
    """
    根据 Node 0 确定的类别 (state['category'])，
    1. 获取该类别下的具体字段 (DocumentTypeField)
    2. 使用 LLM 提取针对这些字段的查询条件
    3. 检查歧义（要求1）
    4. 构造 Elasticsearch 查询（要求2）
    """

    # 如果 Node 0 未召回任何文档，或未指定类别，则跳过精排
    if state["category"] == "*" or not state["docs"]:
        logger.warning(f"类别为 '*' 或 SQL 粗召回文档为0，跳过 Node 1 ES 精排。")
        # 我们可以构造一个"仅全文检索"的ES查询作为后备
        return await _build_fallback_es_query(state)

    # 1. 获取 DocumentType 和 DocumentTypeField
    doc_types_result = await state["db"].execute(
        select(DocumentType).where(
            DocumentType.template_id == state["template_id"],
            DocumentType.type_code == state["category"],
        )
    )
    doc_types = doc_types_result.scalars().all()

    if not doc_types:
        logger.warning(
            f"未在数据库中找到类别为 '{state['category']}' 的 DocumentType。转为后备查询。"
        )
        return await _build_fallback_es_query(state)

    document_type_fields_result = await state["db"].execute(
        select(DocumentTypeField).where(
            DocumentTypeField.doc_type_id.in_([doc_type.id for doc_type in doc_types])
        )
    )
    document_type_fields = list(document_type_fields_result.scalars().all())
    state["document_type_fields"] = document_type_fields

    # 2. 使用 LLM 提取特定查询条件
    field_prompt_definitions = ""
    # 字段名 -> 字段类型 (用于构造 ES 查询)
    field_map = {}
    for f in document_type_fields:
        # 示例: - contract_name: 合同名称 (类型: text)
        field_prompt_definitions += (
            f"- {f.field_name}: {f.description} (类型: {f.field_type})\n"
        )
        field_map[f.field_name] = f.field_type

    prompt = f"""
    你是一个智能查询分析助手。
    用户正在查询一个特定类别的文档 (类别: {state.get('category', '未知')})。
    
    该类别有以下可用字段，这些字段存储在 'metadata' 中：
    {field_prompt_definitions if field_prompt_definitions else "（无特定元数据字段）"}
    
    还有两个通用字段可用于全文搜索：
    - title: 标题
    - content: 内容
    
    请根据用户的查询请求，提取出用于搜索的具体键值对。
    
    要求：
    1. 输出一个 JSON 对象。
    2. 该 JSON 对象必须包含两个键：
       - "conditions": 一个字典，包含从查询中提取到的 {{字段名: 值}}。
       - "missing_fields": 一个字符串列表，包含用户未提供，但对于精确检索非常有帮助的字段名 (从上方字段定义中选择)。
    3. "conditions" 中的键必须是 "title", "content" 或上方定义的 'metadata' 字段名之一。
    4. 如果用户的查询很模糊 (例如 "帮我找找看", "随便看看")，"conditions" 应该为空，"missing_fields" 应该包含建议用户补充的字段。
    5. 只提取用户明确提到的值。不要猜测或编造。
    
    用户查询：
    {state['query']}
    
    请直接输出 JSON 对象，不要解释。
    """

    try:
        llm_response = await llm_client.extract_json_response(prompt, db=state["db"])
        state["extracted_llm_json"] = llm_response
        logger.info(f"LLM (Node 1) 提取的特定条件: {llm_response}")
    except Exception as e:
        logger.error(f"LLM (Node 1) 提取特定条件失败: {e}")
        state["extracted_llm_json"] = {"conditions": {}, "missing_fields": []}

    extracted_conditions = (
        state["extracted_llm_json"].get("conditions", {})
        if isinstance(state["extracted_llm_json"], dict)
        else {}
    )
    missing_fields = (
        state["extracted_llm_json"].get("missing_fields", [])
        if isinstance(state["extracted_llm_json"], dict)
        else []
    )

    # 3. 处理歧义 (Requirement 1)
    # 如果 LLM 没有提取到任何条件，并且它认为缺少字段，我们就触发歧义处理
    if not extracted_conditions and missing_fields:
        missing_fields_str = "、".join(missing_fields)
        state["ambiguity_message"] = (
            f"您的问题似乎有些宽泛。为了帮您更精确地查找，您能提供以下信息吗？（例如：{missing_fields_str}）"
        )

        # **重要**: 在你的智能体图 (Agent Graph) 中，这里应该有一个条件分支。
        # 如果 state['ambiguity_message'] 存在，则转到 "ask_user" 节点。
        # 如果用户 *拒绝* 提供更多信息（例如回复 "就这样搜"），
        # 那么智能体应该清空 ambiguity_message 并再次运行此节点，
        # 此时会进入下面的 `_build_fallback_es_query` 逻辑。

        # 为满足要求2 (如果用户不提供)，我们先构造一个后备查询
        logger.warning(
            f"查询有歧义，建议用户补充: {missing_fields_str}。将构造后备查询。"
        )
        # 保存状态到全局存储
        graph_state_storage[state["session_id"]] = dict(state)
        return await _build_fallback_es_query(state, "ambiguous_query")

    # 4. 构造 ES 查询 (Requirement 2)

    # 基础过滤器：只在 Node 0 返回的文档中搜索
    document_ids_from_sql = [int(str(doc.id)) for doc in state.get("docs", [])]
    filters = []
    if document_ids_from_sql:
        # 将列表转换为单个整数（这里我们只取第一个，实际应用中可能需要调整）
        filters.append({"terms": {"document_id": document_ids_from_sql}})

    # 构造查询子句
    must_clauses = []

    if not extracted_conditions:
        # 没有提取到条件，但LLM也没说缺啥（例如用户只说了类别），执行一个通用的全文搜索
        must_clauses.append(
            {"multi_match": {"query": state["query"], "fields": ["title", "content"]}}
        )
    else:
        # 如果提取到了特定条件，构造更精确的查询
        for field_name, value in extracted_conditions.items():
            if not value or value == "UNKNOWN":
                continue

            if field_name in ["title", "content"]:
                must_clauses.append({"match": {field_name: value}})
            else:
                # 这是 metadata 字段
                field_type = field_map.get(field_name, "text")  # 默认按 text 处理

                # 根据字段类型选择不同匹配方式 (ES dynamic=true 会自动处理)
                # "text" 类型使用 match (分词)
                # "keyword", "date", "number" 等类型使用 term (精确)
                if field_type in ["text", "textarea"]:
                    must_clauses.append({"match": {f"metadata.{field_name}": value}})
                else:
                    must_clauses.append({"term": {f"metadata.{field_name}": value}})

    # 组装最终查询
    es_query = {
        "query": {"bool": {"must": must_clauses, "filter": filters}},
        "size": 5,  # Requirement 2: 最多五条记录
        "_source": ["document_id", "title", "content", "metadata"],
    }

    state["es_query"] = es_query
    logger.info(
        f"Node 1 构造的 ES 查询: {json.dumps(es_query, indent=2, ensure_ascii=False)}"
    )

    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)

    return state


async def _build_fallback_es_query(
    state: RetrievalState, reason: str = "no_category"
) -> RetrievalState:
    """
    (私有) 构造一个后备的 ES 查询，仅基于全文和 SQL 召回列表。
    """
    logger.info(f"执行后备 ES 查询，原因: {reason}")
    document_ids_from_sql = [int(str(doc.id)) for doc in state.get("docs", [])]

    # TODO 结合大模型，对需要提取的内容，和query进行结合，构造更加准确的查询条件

    # 如果 SQL 列表为空，则进行全库全文检索
    filters = [{"term": {"template_id": state["template_id"]}}]
    if document_ids_from_sql:
        filters.append({"terms": {"document_id": document_ids_from_sql}})

    state["es_query"] = {
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": state["query"],
                        "fields": ["title", "content"],
                    }
                },
                "filter": filters,
            }
        },
        "size": 5,  # Requirement 2
    }
    logger.info(
        f"Node 1 构造的 Fallback ES 查询: {json.dumps(state['es_query'], indent=2, ensure_ascii=False)}"
    )

    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)

    return state


# === 节点 2：执行 ES 查询 ===
async def run_es_query(state: RetrievalState) -> RetrievalState:
    """
    执行 state['es_query'] 并将结果存入 state['es_results']
    """
    settings = get_settings()
    es_query = state.get("es_query")
    if not es_query:
        logger.warning("Node 2: ES query 为空，跳过检索。")
        state["es_results"] = []
        # 保存状态到全局存储
        graph_state_storage[state["session_id"]] = dict(state)
        return state

    try:
        response = await state["es_client"].search(
            index=settings.ELASTICSEARCH_INDEX, body=es_query  # 替换为你的 ES 索引名
        )

        hits = response.get("hits", {}).get("hits", [])
        state["es_results"] = [hit["_source"] for hit in hits]  # 存储 _source
        logger.info(f"Node 2: ES 检索到 {len(hits)} 条结果。")

    except Exception as e:
        logger.error(f"Node 2: ES 查询失败: {e}")
        state["es_results"] = []

    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)

    return state


# === 节点 3：生成最终回答 ===
async def generate_answer(state: RetrievalState) -> RetrievalState:
    """
    根据 ES 检索结果，综合生成最终回答。
    """
    query = state["query"]
    results = state["es_results"]

    if not results:
        logger.info("Node 3: 没有可用的检索结果，无法生成答案。")
        # 检查是否有歧义消息
        if state.get("ambiguity_message"):
            # 如果有歧义消息，说明是用户拒绝提供信息后的回退查询，但依然没查到
            state["answer"] = "抱歉，根据您提供的信息，我没有找到相关的文档。"
        else:
            state["answer"] = "抱歉，我没有找到与您问题相关的文档。"
        # 保存状态到全局存储
        graph_state_storage[state["session_id"]] = dict(state)
        return state

    # 构造 RAG prompt
    context_str = ""
    for i, doc in enumerate(results):
        context_str += f"--- 文档 {i+1} (ID: {doc.get('document_id')}) ---\n"
        context_str += f"标题: {doc.get('title')}\n"
        content_snippet = doc.get("content", "")[:500]  # 截取片段
        context_str += f"内容片段: {content_snippet}...\n"
        if doc.get("metadata"):
            context_str += (
                f"元数据: {json.dumps(doc.get('metadata'), ensure_ascii=False)}\n"
            )
        context_str += "---------------------------------\n\n"

    prompt = f"""
    你是一个问答助手。请根据以下上下文信息，简洁地回答用户的问题。
    
    上下文信息：
    {context_str}
    
    用户问题：
    {query}
    
    请根据上下文回答问题。如果上下文信息不足以回答，请告知用户 "根据已有信息，我无法回答..."。
    """

    try:
        answer = await llm_client.chat_completion(
            prompt, db=state["db"]
        )  # 假设 llm_client 有一个 generate_response 方法
        state["answer"] = answer
    except Exception as e:
        logger.error(f"Node 3: LLM 生成答案失败: {e}")
        state["answer"] = "抱歉，我在处理您的请求时遇到了一个内部错误。"

    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)

    return state


# === 节点 4：(终端) 向用户提问 ===
async def ask_user_for_info(state: RetrievalState) -> RetrievalState:
    """
    这是一个终端节点，它不执行操作，
    只是为了让智能体图 (Agent Graph) 在此停止，
    并将 state['ambiguity_message'] 返回给前端。
    """
    logger.info("进入歧义处理节点 (ask_user_for_info)。等待用户输入。")
    # 状态中已包含 ambiguity_message，智能体图应将其返回
    # 保存状态到全局存储
    graph_state_storage[state["session_id"]] = dict(state)
    return state


def check_ambiguity(state: RetrievalState) -> str:
    """
    检查 Node 1 是否产生了歧义消息。
    这是图的"决策者"。
    """
    logger.info("--- 检查条件: check_ambiguity ---")
    if state.get("ambiguity_message"):
        logger.info("决策：查询有歧义 (is_ambiguous)")
        return "is_ambiguous"
    else:
        logger.info("决策：查询清晰 (is_clear)")
        return "is_clear"


# 1. 初始化 StateGraph
workflow = StateGraph(RetrievalState)

# 2. 添加所有节点
workflow.add_node("sql_retrieval", query_necessary_data)
workflow.add_node("es_condition_extractor", extract_query_conditions)
workflow.add_node("run_es_query", run_es_query)
workflow.add_node("generate_answer", generate_answer)
workflow.add_node("ask_user", ask_user_for_info)  # 歧义处理节点

# 3. 设置图的入口
workflow.set_entry_point("sql_retrieval")

# 4. 添加常规边 (Edges)
workflow.add_edge("sql_retrieval", "es_condition_extractor")
workflow.add_edge("run_es_query", "generate_answer")

# 5. 添加条件边 (Conditional Edges)
#    在 "es_condition_extractor" 节点之后，调用 "check_ambiguity" 函数
workflow.add_conditional_edges(
    "es_condition_extractor",  # 源节点
    check_ambiguity,  # 决策函数
    {
        # 决策函数返回 "is_ambiguous" 时，转到 "ask_user" 节点
        "is_ambiguous": "ask_user",
        # 决策函数返回 "is_clear" 时，转到 "run_es_query" 节点
        "is_clear": "run_es_query",
    },
)

# 6. 设置图的终点
#    当 "generate_answer" 或 "ask_user" 运行完毕时，流程结束
workflow.add_edge("generate_answer", END)
workflow.add_edge("ask_user", END)

# 7. 编译图
app = workflow.compile()
