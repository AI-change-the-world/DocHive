import asyncio
import hashlib
import json
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, TypedDict

from elasticsearch import AsyncElasticsearch
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import (
    Document,
    DocumentType,
    DocumentTypeField,
    TemplateDocumentMapping,
)
from services.intent_router import format_tool_result_as_answer, function_calling_router
from services.template_service import TemplateService
from utils.llm_client import get_llm_client

# 全局变量存储graph状态，用于支持中断和恢复
# 注意: 生产环境应使用 Redis 等分布式缓存替代内存存储
graph_state_storage: Dict[str, Dict[str, Any]] = {}


# ==================== 文档去重工具函数 ====================


def normalize_text(text: str) -> str:
    """
    文本标准化：去除HTML/Markdown标签、标点、多余空格等

    用于后续的哈希计算和相似度比对
    """
    if not text:
        return ""

    # 移除HTML标签
    text = re.sub(r"<[^>]+>", "", text)
    # 移除Markdown标题标记
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # 移除Markdown链接
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 转小写
    text = text.lower()
    # 折叠多余空白符
    text = re.sub(r"\s+", " ", text)
    # 只保留中英文、数字
    text = re.sub(r"[^\w\u4e00-\u9fa5]+", "", text)

    return text.strip()


def compute_strong_hash(text: str) -> str:
    """
    计算文本的强哈希值（SHA256）

    用于检测完全相同的文档
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_simhash(text: str, hashbits: int = 64) -> int:
    """
    计算SimHash（局部敏感哈希）

    用于检测高度相似的文档
    算法：对文本分词后，使用每个词的hash进行加权求和
    """
    if not text:
        return 0

    # 简单分词（按空格）
    tokens = text.split()
    if not tokens:
        return 0

    # 初始化特征向量
    v = [0] * hashbits

    for token in tokens:
        # 计算token的hash
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)

        # 对每一位进行加权
        for i in range(hashbits):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1

    # 生成SimHash指纹
    fingerprint = 0
    for i in range(hashbits):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def hamming_distance(hash1: int, hash2: int) -> int:
    """
    计算两个SimHash的汉明距离
    """
    x = hash1 ^ hash2
    distance = 0
    while x:
        distance += 1
        x &= x - 1  # 清除最低位的1
    return distance


def compute_shingles(text: str, k: int = 5) -> Set[str]:
    """
    生成k-shingles（滑动窗口字符串集合）

    用于Jaccard相似度计算
    """
    if len(text) < k:
        return {text}

    shingles = set()
    for i in range(len(text) - k + 1):
        shingles.add(text[i : i + k])

    return shingles


def jaccard_similarity(set1: Set[str], set2: Set[str]) -> float:
    """
    计算Jaccard相似度
    """
    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def should_remove_duplicate(
    doc_a: Dict[str, Any], doc_b: Dict[str, Any]
) -> Optional[int]:
    """
    判断两个文档是否重复，返回应该移除的文档ID

    返回值：
    - None: 不重复
    - document_id: 应该移除的文档ID（保留内容更长、时间更新的）

    Args:
        doc_a: 文档A的dict，包含 normalized, strong_hash, simhash, shingles, document_id, content
        doc_b: 文档B的dict
    """
    # 阶段1: 强哈希完全相同
    if doc_a["strong_hash"] == doc_b["strong_hash"]:
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} 强哈希相同（完全重复）"
        )
        # 保留内容更长的
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段2: SimHash汉明距离很小（高度相似）
    hamming_dist = hamming_distance(doc_a["simhash"], doc_b["simhash"])
    if hamming_dist <= 3:  # 阈值可调
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} SimHash距离={hamming_dist}（高度相似）"
        )
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段3: Jaccard相似度很高
    jac_sim = jaccard_similarity(doc_a["shingles"], doc_b["shingles"])
    if jac_sim > 0.75:  # 阈值可调
        logger.debug(
            f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} Jaccard={jac_sim:.3f}（内容重叠高）"
        )
        if len(doc_a["content"]) < len(doc_b["content"]):
            return doc_a["document_id"]
        else:
            return doc_b["document_id"]

    # 阶段4: 只对Jaccard在0.5-0.75之间的做精细difflib比对（避免O(n²)开销）
    if 0.5 < jac_sim <= 0.75:
        # difflib比对（较慢，只对候选执行）
        ratio = SequenceMatcher(None, doc_a["normalized"], doc_b["normalized"]).ratio()
        if ratio > 0.80:  # 阈值可调
            logger.debug(
                f"文档 {doc_a['document_id']} 和 {doc_b['document_id']} difflib={ratio:.3f}（精细比对重复）"
            )
            if len(doc_a["content"]) < len(doc_b["content"]):
                return doc_a["document_id"]
            else:
                return doc_b["document_id"]

    return None


class RetrievalState(TypedDict):
    """
    优化后的 RAG 智能体状态机

    工作流程:
    0. 意图路由 -> LLM 自主规划整个执行流程
    1. ES全文检索 -> 基于关键词快速召回候选文档
    2. SQL结构化检索 -> 基于模板层级提取结构化条件
    3. 结果融合 -> 合并两路检索结果
    4. 精细化筛选 -> 基于文档类型特定字段进一步筛选
    5. 生成答案 -> RAG生成最终回答

    注意: db 和 es_client 不在 state 中，通过 config 注入
    """

    # === 必需输入 ===
    query: str  # 用户查询
    template_id: int  # 模板ID
    session_id: str  # 会话ID

    # === 节点 0 (意图路由) 产出 ===
    execution_plan: List[Dict[str, Any]]  # LLM 规划的执行计划
    reasoning: str  # LLM 的推理过程
    tool_results: List[Dict[str, Any]]  # 工具执行结果列表
    need_retrieval: bool  # 是否需要文档检索

    # === 节点 1 (ES全文检索) 产出 ===
    es_fulltext_results: List[Dict[str, Any]]  # ES全文检索的初步结果
    es_document_ids: Set[int]  # ES召回的文档ID集合

    # === 节点 2 (SQL结构化检索) 产出 ===
    class_template_levels: Optional[List[Dict[str, Any]]]  # 模板层级定义
    category: str  # 识别出的文档类别
    category_field_code: Optional[str]  # 类别字段编码
    sql_extracted_conditions: List[Dict[str, Any]]  # LLM提取的结构化条件
    sql_document_ids: Set[int]  # SQL召回的文档ID集合

    # === 节点 3 (结果融合) 产出 ===
    merged_document_ids: List[int]  # 融合后的文档ID列表(按相关性排序)
    merged_documents: List[Document]  # 融合后的文档对象列表
    fusion_strategy: (
        str  # 融合策略: 'intersection'(交集), 'union'(并集), 'es_primary'(ES为主)
    )

    # === 节点 4 (精细化筛选) 产出 ===
    document_type_fields: List[DocumentTypeField]  # 文档类型特定字段
    refined_conditions: Dict[str, Any]  # 精细化查询条件
    final_es_query: Optional[Dict[str, Any]]  # 最终ES查询
    final_results: List[Dict[str, Any]]  # 精细化筛选后的最终结果

    # === 节点 5 (歧义处理) 产出 ===
    ambiguity_message: Optional[str]  # 歧义提示消息

    # === 节点 6 (生成答案) 产出 ===
    answer: Optional[str]  # 最终RAG答案


# ==================== 节点 0: 任务规划路由 ====================
async def intent_routing(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 0: 任务规划路由

    让 LLM 看到所有工具，自主规划整个任务的执行流程。

    输出:
    - execution_plan: LLM 规划的执行计划
    - reasoning: LLM 的推理过程
    - tool_results: 工具执行结果列表
    - need_retrieval: 是否需要文档检索
    """
    logger.info("========== 节点 0: 任务规划路由 ==========")

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    query = state["query"]
    template_id = state["template_id"]

    try:
        # 调用 Function Calling 路由器（现在返回执行计划）
        routing_result = await function_calling_router(query, template_id, db)

        execution_plan = routing_result.get("execution_plan", [])
        reasoning = routing_result.get("reasoning", "")
        tool_results = routing_result.get("tool_results", [])
        need_retrieval = routing_result.get("need_retrieval", False)

        logger.info(f"🧠 LLM 规划结果:")
        logger.info(f"   执行步骤: {len(execution_plan)}")
        logger.info(f"   工具调用: {len(tool_results)}")
        logger.info(f"   需要检索: {need_retrieval}")
        logger.info(f"   推理过程: {reasoning}")

        # 打印执行计划
        for step in execution_plan:
            logger.info(
                f"   步骤 {step.get('step')}: {step.get('action')} - {step.get('description')}"
            )

        # 更新状态
        state["execution_plan"] = execution_plan
        state["reasoning"] = reasoning
        state["tool_results"] = tool_results
        state["need_retrieval"] = need_retrieval

        logger.info("✅ 任务规划完成")

    except Exception as e:
        logger.error(f"❌ 任务规划失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # 默认走文档检索
        state["execution_plan"] = [
            {"step": 1, "action": "document_retrieval", "description": "文档检索"}
        ]
        state["reasoning"] = f"规划失败，降级到文档检索: {str(e)}"
        state["tool_results"] = []
        state["need_retrieval"] = True

    return state


# ==================== 节点: 工具调用答案生成 ====================
async def generate_tool_answer(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    工具调用答案生成节点

    将多步骤工具调用结果格式化为自然语言答案。

    输出:
    - answer: 格式化后的答案（单纯工具查询）
    - tool_answer_partial: 部分答案（组合查询）
    """
    logger.info("========== 工具调用答案生成 ==========")

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    tool_results = state.get("tool_results", [])
    query = state["query"]
    need_retrieval = state.get("need_retrieval", False)
    execution_plan = state.get("execution_plan", [])

    try:
        # 构建工具结果数据
        combined_results = {
            "query": query,
            "execution_plan": execution_plan,
            "tool_results": tool_results,
        }

        # 使用 LLM 将工具结果转换为自然语言
        tool_answer = await format_tool_result_as_answer(combined_results, query, db)

        # 如果是组合查询，保存工具答案，不直接设置为最终答案
        if need_retrieval:
            state["tool_answer_partial"] = tool_answer  # 保存部分答案
            logger.info(
                f"✅ 生成工具调用部分答案，等待继续检索: {tool_answer[:100]}..."
            )
        else:
            state["answer"] = tool_answer  # 直接设置为最终答案
            logger.info(f"✅ 生成工具调用最终答案: {tool_answer[:100]}...")
    except Exception as e:
        logger.error(f"❌ 格式化工具结果失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # 降级处理
        fallback_answer = (
            f"查询结果：\n{json.dumps(tool_results, ensure_ascii=False, indent=2)}"
        )
        if need_retrieval:
            state["tool_answer_partial"] = fallback_answer
        else:
            state["answer"] = fallback_answer

    return state


# ==================== 节点 1: ES 全文检索 ====================
async def es_fulltext_retrieval(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 1: ES 全文检索

    基于用户查询在 Elasticsearch 中进行全文检索,快速召回候选文档。
    这是第一阶段的粗召回,利用 ES 的全文搜索能力。

    输出:
    - es_fulltext_results: ES 检索到的文档列表
    - es_document_ids: 文档 ID 集合
    """
    logger.info("========== 节点 1: ES 全文检索 ==========")

    # 从 config 获取 es_client 和 es_index
    es_client: AsyncElasticsearch = config.get("configurable", {}).get(
        "es"
    )  # type: ignore
    es_index: str = config.get("configurable", {}).get(
        "es_index", "dochive_documents"
    )  # type: ignore

    query = state["query"]
    template_id = state["template_id"]

    # 构造 ES 全文检索查询
    es_query = {
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "content"],  # title 权重更高
                        "type": "best_fields",
                        "fuzziness": "AUTO",  # 支持模糊匹配
                    }
                },
                "filter": [{"term": {"template_id": template_id}}],  # 限定模板范围
            }
        },
        "size": 20,  # 召回 Top 20
        "_source": ["document_id", "title", "content", "metadata"],
    }

    try:
        response = await es_client.search(index=es_index, body=es_query)

        hits = response.get("hits", {}).get("hits", [])
        state["es_fulltext_results"] = [hit["_source"] for hit in hits]
        state["es_document_ids"] = set(hit["_source"]["document_id"] for hit in hits)

        logger.info(f"✅ ES 全文检索召回 {len(hits)} 篇文档")
        logger.info(f"   文档 ID: {list(state['es_document_ids'])}")

    except Exception as e:
        logger.error(f"❌ ES 全文检索失败: {e}")
        state["es_fulltext_results"] = []
        state["es_document_ids"] = set()

    return state


# ==================== 节点 2: SQL 结构化检索 ====================
async def sql_structured_retrieval(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 2: SQL 结构化检索

    基于模板层级定义,使用 LLM 提取结构化查询条件,
    在数据库中进行精确的结构化检索。

    输出:
    - class_template_levels: 模板层级定义
    - category: 文档类别
    - sql_extracted_conditions: 提取的结构化条件
    - sql_document_ids: SQL 召回的文档 ID 集合
    """
    logger.info("========== 节点 2: SQL 结构化检索 ==========")

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    # 1. 获取模板层级定义
    cls_template = await TemplateService.get_template(db, state["template_id"])

    if not cls_template:
        logger.warning("⚠️ 未找到模板,跳过 SQL 结构化检索")
        state["class_template_levels"] = []
        state["category"] = "*"
        state["sql_extracted_conditions"] = []
        state["sql_document_ids"] = set()
        return state

    # 使用 property 获取层级定义 (自动处理 JSON 转换)
    cls_template_levels = cls_template.levels
    if not isinstance(cls_template_levels, list):
        logger.error("❌ 模板层级定义格式错误")
        state["class_template_levels"] = []
        state["category"] = "*"
        state["sql_extracted_conditions"] = []
        state["sql_document_ids"] = set()
        return state

    state["class_template_levels"] = cls_template_levels

    # 2. 提取类别字段
    type_code = ""
    for field in cls_template_levels:
        if field.get("is_doc_type", False):
            type_code = field.get("code", "")
            state["category_field_code"] = type_code
            break

    # 3. 使用 LLM 提取结构化条件
    prompt = f"""
你是一个智能结构化查询助手。
用户会给出一个自然语言检索请求,请你根据以下字段定义,提取出结构化的检索条件。

字段定义:
{json.dumps(cls_template_levels, ensure_ascii=False, indent=2)}

要求:
1. 输出 JSON 对象,格式: {{"conditions": [{{"code": "字段编码", "value": "提取值", "level": 层级}}], "category": "文档类别"}}
2. 如果无法从查询中推理出某个字段,value 设为 "UNKNOWN"
3. category 字段应该是 is_doc_type=true 的字段的值
4. 只提取用户明确提到的信息,不要猜测

用户查询:
{state['query']}

请直接输出 JSON,不要解释。
    """

    try:
        llm_client = get_llm_client()
        llm_response = await llm_client.extract_json_response(prompt, db=db)
        logger.info(f"🤖 LLM 提取的结构化条件: {llm_response}")

        conditions = llm_response.get("conditions", [])
        state["category"] = llm_response.get("category", "*")
        state["sql_extracted_conditions"] = conditions

    except Exception as e:
        logger.error(f"❌ LLM 提取结构化条件失败: {e}")
        state["category"] = "*"
        state["sql_extracted_conditions"] = []

    # 4. 构造 SQL 查询条件
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

    # 5. 执行 SQL 查询
    stmt = select(TemplateDocumentMapping.document_id).where(
        TemplateDocumentMapping.template_id == state["template_id"]
    )
    if conditions_clauses:
        stmt = stmt.where(or_(*conditions_clauses))

    try:
        result = await db.execute(stmt)
        document_ids = [row[0] for row in result.all()]
        state["sql_document_ids"] = set(document_ids)

        logger.info(f"✅ SQL 结构化检索召回 {len(document_ids)} 篇文档")
        logger.info(f"   文档 ID: {list(state['sql_document_ids'])}")

    except Exception as e:
        logger.error(f"❌ SQL 查询失败: {e}")
        state["sql_document_ids"] = set()

    return state


# ==================== 节点 3: 结果融合 ====================
async def merge_retrieval_results(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 3: 结果融合

    将 ES 全文检索和 SQL 结构化检索的结果进行融合,
    采用智能策略决定如何合并两路召回结果。

    融合策略:
    1. 'intersection': 取交集 (精确匹配)
    2. 'union': 取并集 (广泛召回)
    3. 'es_primary': ES为主,SQL为辅助筛选

    输出:
    - merged_document_ids: 融合后的文档 ID 列表
    - merged_documents: 融合后的文档对象
    - fusion_strategy: 使用的融合策略
    """
    logger.info("========== 节点 3: 结果融合 ==========")

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    es_ids = state.get("es_document_ids", set())
    sql_ids = state.get("sql_document_ids", set())

    logger.info(f"📊 ES 召回: {len(es_ids)} 篇, SQL 召回: {len(sql_ids)} 篇")

    # 决定融合策略
    if not es_ids and not sql_ids:
        # 两路都没召回
        logger.warning("⚠️ ES 和 SQL 都未召回任何文档")
        state["fusion_strategy"] = "none"
        state["merged_document_ids"] = []
        state["merged_documents"] = []
        return state

    elif not sql_ids:
        # 只有 ES 召回了
        logger.info("📌 策略: ES为主 (SQL未召回)")
        state["fusion_strategy"] = "es_only"
        merged_ids = list(es_ids)

    elif not es_ids:
        # 只有 SQL 召回了
        logger.info("📌 策略: SQL为主 (ES未召回)")
        state["fusion_strategy"] = "sql_only"
        merged_ids = list(sql_ids)

    else:
        # 两路都召回了,使用智能融合策略
        intersection = es_ids & sql_ids
        union = es_ids | sql_ids

        if len(intersection) >= 3:
            # 交集足够多,使用交集 (高精度)
            logger.info(f"📌 策略: 交集 (共 {len(intersection)} 篇文档)")
            state["fusion_strategy"] = "intersection"
            merged_ids = list(intersection)

        elif len(intersection) > 0:
            # 交集较少,ES为主,SQL为辅
            logger.info(f"📌 策略: ES为主,SQL辅助 (交集 {len(intersection)} 篇)")
            state["fusion_strategy"] = "es_primary"
            # ES 结果在前,交集优先,然后是 ES 独有
            merged_ids = list(intersection) + [
                id for id in es_ids if id not in intersection
            ]

        else:
            # 没有交集,取并集
            logger.info(f"📌 策略: 并集 (ES {len(es_ids)} + SQL {len(sql_ids)})")
            state["fusion_strategy"] = "union"
            merged_ids = list(es_ids) + [id for id in sql_ids if id not in es_ids]

    # 限制结果数量 (Top 10)
    merged_ids = merged_ids[:10]
    state["merged_document_ids"] = merged_ids

    # 从数据库加载文档对象
    if merged_ids:
        try:
            docs_result = await db.execute(
                select(Document).where(Document.id.in_(merged_ids))
            )
            docs = list(docs_result.scalars().all())

            # 按 merged_ids 的顺序排序
            docs_dict = {int(doc.id): doc for doc in docs}  # type: ignore
            state["merged_documents"] = [
                docs_dict[doc_id] for doc_id in merged_ids if doc_id in docs_dict
            ]

            logger.info(f"✅ 融合完成,最终保留 {len(state['merged_documents'])} 篇文档")

        except Exception as e:
            logger.error(f"❌ 加载文档对象失败: {e}")
            state["merged_documents"] = []
    else:
        state["merged_documents"] = []

    return state


# ==================== 节点 4: 精细化筛选 ====================
async def refined_filtering(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 4: 精细化筛选

    基于文档类型的特定字段 (DocumentTypeField),
    使用 LLM 提取更精细的查询条件,在 ES 中进行二次筛选。

    输出:
    - document_type_fields: 文档类型特定字段
    - refined_conditions: 精细化条件
    - final_es_query: 最终 ES 查询
    - final_results: 最终检索结果
    """
    logger.info("========== 节点 4: 精细化筛选 ==========")

    # 从 config 获取 db 和 es_client
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore
    es_client: AsyncElasticsearch = config.get("configurable", {}).get(
        "es"
    )  # type: ignore

    # 如果没有融合结果,直接跳过
    if not state.get("merged_documents"):
        logger.warning("⚠️ 无融合结果,跳过精细化筛选")
        state["document_type_fields"] = []
        state["refined_conditions"] = {}
        state["final_es_query"] = None
        state["final_results"] = []
        return state

    # 如果类别为通配符,跳过精细化筛选
    category = state.get("category", "*")
    if category == "*":
        logger.info("📌 类别为通配符,跳过精细化筛选,直接使用融合结果")
        state["document_type_fields"] = []
        state["refined_conditions"] = {}
        state["final_es_query"] = None
        state["final_results"] = _convert_docs_to_results(state["merged_documents"])
        return state

    # 1. 获取 DocumentType 和 DocumentTypeField
    try:
        doc_types_result = await db.execute(
            select(DocumentType).where(
                DocumentType.template_id == state["template_id"],
                DocumentType.type_code == category,
            )
        )
        doc_types = doc_types_result.scalars().all()

        if not doc_types:
            logger.warning(f"⚠️ 未找到类别 '{category}' 的 DocumentType,跳过精细化筛选")
            state["document_type_fields"] = []
            state["refined_conditions"] = {}
            state["final_results"] = _convert_docs_to_results(state["merged_documents"])
            return state

        document_type_fields_result = await db.execute(
            select(DocumentTypeField).where(
                DocumentTypeField.doc_type_id.in_([dt.id for dt in doc_types])
            )
        )
        document_type_fields = list(document_type_fields_result.scalars().all())
        state["document_type_fields"] = document_type_fields

        if not document_type_fields:
            logger.info("📌 该类别无特定字段,跳过精细化筛选")
            state["refined_conditions"] = {}
            state["final_results"] = _convert_docs_to_results(state["merged_documents"])
            return state

    except Exception as e:
        logger.error(f"❌ 获取文档类型字段失败: {e}")
        state["document_type_fields"] = []
        state["refined_conditions"] = {}
        state["final_results"] = _convert_docs_to_results(state["merged_documents"])
        return state

    # 2. 使用 LLM 提取精细化条件
    field_definitions = ""
    field_map = {}  # 字段名 -> 字段类型

    for f in document_type_fields:
        field_definitions += (
            f"- {f.field_name}: {f.description} (类型: {f.field_type})\n"
        )
        field_map[f.field_name] = f.field_type

    prompt = f"""
你是一个智能精细化查询助手。
用户正在查询类别为 '{category}' 的文档,该类别有以下特定字段:

{field_definitions}

请根据用户查询提取这些字段的具体值:

要求:
1. 输出 JSON 对象: {{"conditions": {{"字段名": "值"}}, "missing_fields": ["缺失字段"]}}
2. 只提取用户明确提到的字段值
3. missing_fields 列出对精确检索有帮助但用户未提供的字段

用户查询:
{state['query']}

请直接输出 JSON,不要解释。
    """
    llm_client = get_llm_client()

    try:
        llm_response = await llm_client.extract_json_response(prompt, db=db)
        logger.info(f"🤖 LLM 提取的精细化条件: {llm_response}")

        conditions = llm_response.get("conditions", {})
        missing_fields = llm_response.get("missing_fields", [])

        state["refined_conditions"] = conditions

        # 3. 检查歧义
        if not conditions and missing_fields:
            missing_str = "、".join(missing_fields)
            state["ambiguity_message"] = (
                f"您的问题似乎有些宽泛。为了更精确地查找,能否提供: {missing_str}?"
            )
            logger.warning(f"⚠️ 检测到歧义,建议补充: {missing_str}")
            state["final_results"] = _convert_docs_to_results(state["merged_documents"])
            return state

    except Exception as e:
        logger.error(f"❌ LLM 提取精细化条件失败: {e}")
        state["refined_conditions"] = {}
        state["final_results"] = _convert_docs_to_results(state["merged_documents"])
        return state

    # 4. 构造精细化 ES 查询
    if not state["refined_conditions"]:
        logger.info("📌 无精细化条件,直接使用融合结果")
        state["final_es_query"] = None
        state["final_results"] = _convert_docs_to_results(state["merged_documents"])
        return state

    # 只在融合后的文档中筛选
    merged_doc_ids = state["merged_document_ids"]

    must_clauses = []
    for field_name, value in state["refined_conditions"].items():
        if not value or value == "UNKNOWN":
            continue

        field_type = field_map.get(field_name, "text")

        # 根据字段类型构造查询
        if field_type in ["text", "textarea"]:
            must_clauses.append({"match": {f"metadata.{field_name}": value}})
        elif field_type == "number":
            must_clauses.append({"term": {f"metadata.{field_name}": value}})
        elif field_type == "date":
            must_clauses.append({"range": {f"metadata.{field_name}": {"gte": value}}})
        else:
            must_clauses.append({"term": {f"metadata.{field_name}": value}})

    final_es_query = {
        "query": {
            "bool": {
                "must": must_clauses,
                "filter": [{"terms": {"document_id": merged_doc_ids}}],
            }
        },
        "size": 5,
        "_source": ["document_id", "title", "content", "metadata"],
    }

    state["final_es_query"] = final_es_query

    # 5. 执行精细化 ES 查询
    try:
        # 从 config 获取 es_index
        es_index: str = config.get("configurable", {}).get(
            "es_index", "dochive_documents"
        )  # type: ignore
        response = await es_client.search(index=es_index, body=final_es_query)

        hits = response.get("hits", {}).get("hits", [])
        state["final_results"] = [hit["_source"] for hit in hits]

        logger.info(f"✅ 精细化筛选完成,保留 {len(hits)} 篇文档")

    except Exception as e:
        logger.error(f"❌ 精细化 ES 查询失败: {e}")
        # 降级: 使用融合结果
        state["final_results"] = _convert_docs_to_results(state["merged_documents"])

    return state


def _convert_docs_to_results(documents: List[Document]) -> List[Dict[str, Any]]:
    """
    辅助函数: 将 Document 对象列表转换为结果字典列表
    """
    results = []
    for doc in documents:
        results.append(
            {
                "document_id": doc.id,
                "title": doc.title,
                "content": doc.content_text or "",
                "metadata": doc.doc_metadata or {},
            }
        )
    return results


# ==================== 节点 4.5: 文档去重 ====================
async def deduplicate_documents(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 4.5: 文档去重

    基于三阶段去重算法，移除重复或高度相似的文档。

    三阶段策略：
    1. 强哈希 (SHA256): 检测完全相同的文档
    2. SimHash + 汉明距离: 检测高度相似的文档
    3. Jaccard相似度 + difflib: 检测“粘贴式重复”（一个文档被粘贴到另一个文档中）

    输出:
    - final_results: 去重后的文档列表
    """
    logger.info("========== 节点 4.5: 文档去重 ===========")

    results = state.get("final_results", [])

    if not results or len(results) <= 1:
        logger.info("文档数量≤ 1，无需去重")
        return state

    logger.info(f"开始去重，原始文档数: {len(results)}")

    # 阶段 0: 预处理 - 为每个文档计算特征
    doc_features = []
    for doc in results:
        content = doc.get("content", "")
        if not content:
            continue

        # 标准化文本
        normalized = normalize_text(content)
        if not normalized:
            continue

        doc_features.append(
            {
                "document_id": doc.get("document_id"),
                "title": doc.get("title", ""),
                "content": content,
                "normalized": normalized,
                "strong_hash": compute_strong_hash(normalized),
                "simhash": compute_simhash(normalized),
                "shingles": compute_shingles(normalized, k=5),
                "original_index": results.index(doc),
            }
        )

    logger.info(f"预处理完成，有效文档数: {len(doc_features)}")

    if len(doc_features) <= 1:
        return state

    # 阶段 1-4: 进行去重比对
    removed_ids = set()

    for i in range(len(doc_features)):
        if doc_features[i]["document_id"] in removed_ids:
            continue

        for j in range(i + 1, len(doc_features)):
            if doc_features[j]["document_id"] in removed_ids:
                continue

            # 判断是否重复
            remove_id = should_remove_duplicate(doc_features[i], doc_features[j])

            if remove_id is not None:
                removed_ids.add(remove_id)
                logger.info(f"✖️  文档 {remove_id} 被标记为重复，将被移除")

    # 过滤重复文档
    deduplicated_results = [
        doc for doc in results if doc.get("document_id") not in removed_ids
    ]

    logger.info(
        f"✅ 去重完成: 原始 {len(results)} 篇 → 去重后 {len(deduplicated_results)} 篇 （移除 {len(removed_ids)} 篇）"
    )

    # 更新状态
    state["final_results"] = deduplicated_results

    return state


# ==================== 节点 5: 歧义处理 ====================
async def handle_ambiguity(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 5: 歧义处理

    如果查询有歧义,暂停流程并向用户提问。
    这是一个终端节点。
    """
    logger.info("========== 节点 5: 歧义处理 ==========")
    logger.warning(f"⚠️ 检测到歧义: {state.get('ambiguity_message')}")

    # 状态已包含 ambiguity_message,直接返回
    # 前端会展示这个消息并等待用户输入
    return state


# ==================== 节点 6: 生成最终答案 ====================
async def generate_answer(
    state: RetrievalState, config: RunnableConfig
) -> RetrievalState:
    """
    节点 6: 生成最终答案

    基于最终检索结果,使用 RAG 生成用户问题的答案。

    输出:
    - answer: 最终答案
    """
    logger.info("========== 节点 6: 生成最终答案 ==========")

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    query = state["query"]
    results = state.get("final_results", [])

    if not results:
        logger.warning("⚠️ 无最终检索结果,无法生成答案")
        state["answer"] = (
            "抱歉,我没有找到与您问题相关的文档。建议您:\n1. 尝试使用不同的关键词\n2. 简化或明确您的问题\n3. 检查文档是否已上传到系统中"
        )
        return state

    # 构造 RAG 上下文
    context_parts = []
    for i, doc in enumerate(results[:5], 1):  # 最多使用 5 篇文档
        doc_context = f"【文档 {i}】\n"
        doc_context += f"标题: {doc.get('title', '未知标题')}\n"

        # 智能截取内容片段 (优先包含查询关键词附近的内容)
        content = doc.get("content", "")
        if len(content) > 800:
            # 简单截取策略,实际可以用更智能的方法
            content = content[:800] + "..."
        doc_context += f"内容: {content}\n"

        # 添加元数据
        metadata = doc.get("metadata", {})
        if metadata:
            doc_context += f"元数据: {json.dumps(metadata, ensure_ascii=False)}\n"

        context_parts.append(doc_context)

    context_str = "\n".join(context_parts)

    # 检查是否有工具调用的部分答案（组合查询）
    tool_answer_partial = state.get("tool_answer_partial")

    # 构造 RAG prompt
    if tool_answer_partial:
        # 组合查询：需要合并工具答案和文档答案
        prompt = f"""
你是一个专业的文档问答助手。用户的问题包含多个子任务，你已经通过工具调用回答了部分问题，现在需要结合文档内容回答剩余部分。

【工具调用结果（已回答的部分）】
{tool_answer_partial}

【检索到的文档】
{context_str}

【用户问题】
{query}

【回答要求】
1. 先简要列出工具调用已经回答的部分
2. 再基于文档内容回答剩余问题
3. 如果需要引用文档，请使用 "根据文档X" 的格式
4. 回答要全面、准确、清晰
5. 如果文档内容与剩余问题无关，请如实说明

请开始回答：
    """
    else:
        # 单纯文档检索
        prompt = f"""
你是一个专业的文档问答助手。请根据以下检索到的文档内容回答用户的问题。

【检索到的文档】
{context_str}

【用户问题】
{query}

【回答要求】
1. 基于上述文档内容进行回答,如果文档中有明确答案请直接引用
2. 如果需要引用文档,请使用 "根据文档X" 的格式
3. 如果文档信息不足以完整回答问题,请明确说明哪些部分无法确定
4. 回答要简洁、准确、专业
5. 如果文档内容与问题无关,请如实说明

请开始回答:
    """
    llm_client = get_llm_client()

    try:
        answer = await llm_client.chat_completion(prompt, db=db)
        state["answer"] = answer
        logger.info(f"✅ 答案生成完成 (长度: {len(answer)} 字符)")

    except Exception as e:
        logger.error(f"❌ LLM 生成答案失败: {e}")
        state["answer"] = "抱歉,我在生成答案时遇到了技术问题,请稍后重试。"

    return state


# ==================== 决策函数 ====================
def should_use_tool(state: RetrievalState) -> str:
    """
    决策函数: 根据执行计划判断路由

    Returns:
        'tool_answer': 执行计划包含工具调用（之后可能还需要检索）
        'retrieval': 执行计划只有文档检索
    """
    execution_plan = state.get("execution_plan", [])

    # 检查执行计划中是否包含工具调用
    has_tool_call = any(step.get("action") == "tool_call" for step in execution_plan)

    if has_tool_call:
        logger.info("🔧 决策: 执行计划包含工具调用 -> tool_answer")
        return "tool_answer"
    else:
        logger.info("🔍 决策: 仅文档检索 -> retrieval")
        return "retrieval"


def should_ask_user(state: RetrievalState) -> str:
    """
    决策函数: 判断是否需要向用户提问澄清

    Returns:
        'ask_user': 有歧义,需要用户澄清
        'generate_answer': 无歧义,直接生成答案
    """
    if state.get("ambiguity_message"):
        logger.info("🔀 决策: 有歧义 -> ask_user")
        return "ask_user"
    else:
        logger.info("🔀 决策: 无歧义 -> generate_answer")
        return "generate_answer"


# ==================== 构建 LangGraph 工作流 ====================
"""
优化后的工作流程：

0. 任务规划 (intent_routing) - LLM 规划执行步骤
   ↓
   [决策] 是否包含工具调用? (should_use_tool)
   ├─ tool_answer: 包含工具调用 → 执行工具 → [决策] 是否需要检索?
   │   ├─ 需要 → 继续文档检索
   │   └─ 不需要 → END
   └─ retrieval: 只有文档检索 → ES全文检索...
       ↓
1. ES全文检索 (es_fulltext_retrieval)
   ↓
2. SQL结构化检索 (sql_structured_retrieval) 
   ↓
3. 结果融合 (merge_retrieval_results)
   ↓
4. 精细化筛选 (refined_filtering)
   ↓
4.5. 文档去重 (deduplicate_documents)
   ↓
5. [决策] 是否有歧义? (should_ask_user)
   ├─ ask_user: 歧义处理 (handle_ambiguity) → END
   └─ generate_answer: 生成答案 (generate_answer) → END
"""

# 1. 初始化 StateGraph
workflow = StateGraph(RetrievalState)

# 2. 添加所有节点
workflow.add_node("intent_routing", intent_routing)  # 节点0: 任务规划
workflow.add_node("tool_answer", generate_tool_answer)  # 工具调用答案生成
workflow.add_node("es_fulltext", es_fulltext_retrieval)  # 节点1: ES全文检索
workflow.add_node("sql_structured", sql_structured_retrieval)  # 节点2: SQL结构化检索
workflow.add_node("merge_results", merge_retrieval_results)  # 节点3: 结果融合
workflow.add_node("refined_filter", refined_filtering)  # 节点4: 精细化筛选
workflow.add_node("deduplicate", deduplicate_documents)  # 节点4.5: 文档去重
workflow.add_node("ask_user", handle_ambiguity)  # 节点5a: 歧义处理
workflow.add_node("generate_answer", generate_answer)  # 节点5b: 生成答案

# 3. 设置图的入口点（从任务规划开始）
workflow.set_entry_point("intent_routing")

# 4. 添加条件边：任务规划后决定走向
workflow.add_conditional_edges(
    "intent_routing",  # 源节点
    should_use_tool,  # 决策函数
    {
        "tool_answer": "tool_answer",  # 包含工具调用 → 工具答案生成 → [决策]
        "retrieval": "es_fulltext",  # 仅文档检索 → ES全文检索
    },
)

# 4.5 工具调用后，根据执行计划决定是否继续检索
workflow.add_conditional_edges(
    "tool_answer",  # 源节点
    lambda state: "continue_retrieval" if state.get("need_retrieval", False) else "end",
    {
        "continue_retrieval": "es_fulltext",  # 继续文档检索
        "end": END,  # 直接结束
    },
)

# 5. 添加文档检索流程的线性边
workflow.add_edge("es_fulltext", "sql_structured")  # ES全文 → SQL结构化
workflow.add_edge("sql_structured", "merge_results")  # SQL结构化 → 结果融合
workflow.add_edge("merge_results", "refined_filter")  # 结果融合 → 精细化筛选
workflow.add_edge("refined_filter", "deduplicate")  # 精细化筛选 → 文档去重

# 6. 添加条件边：在去重后，判断是否有歧义
workflow.add_conditional_edges(
    "deduplicate",  # 源节点
    should_ask_user,  # 决策函数
    {
        "ask_user": "ask_user",  # 有歧义 → 向用户提问
        "generate_answer": "generate_answer",  # 无歧义 → 生成答案
    },
)

# 7. 设置图的终点（注意：tool_answer 现在有条件边，不再直接到 END）
workflow.add_edge("ask_user", END)  # 歧义处理后结束
workflow.add_edge("generate_answer", END)  # 生成答案后结束

# 8. 编译图
app: CompiledStateGraph = workflow.compile()

logger.info("✅ LangGraph 智能体工作流编译完成")
logger.info("📊 工作流程: 意图路由 → [工具调用 | 文档检索流程] → 生成答案/歧义处理")
