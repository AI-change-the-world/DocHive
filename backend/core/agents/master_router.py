""" 
主路由器V4 - 支持多轮对话和用户干预

功能：
1. 基于session_id的会话状态管理
2. 支持多轮对话
3. 支持用户干预（检索结果过多/过少时请求用户输入）
4. 三步执行流程：规划 → 执行 → 总结

**这个智能体后续可能只会支持检索智能体以及多轮对话，其他工具都不会支持了**

特点：内存管理会话状态，支持暂停和恢复执行
"""

import asyncio
import json
from typing import Any, Dict, List, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.agents.qa_agent_v2 import generate_answer_v2

# 使用新版智能体
from core.agents.retrieval_agent_v2 import retrieve_documents_v2
from core.conversation_manager import get_conversation_manager
from core.registry import (
    get_agents_description,
    get_execution_patterns_description,
    get_tools_description,
)

# 导入新版工具基础设施
from core.tools.base import ToolContext, execute_tool
from core.tools.tool_registry import get_tool_metadata
from utils.llm_client import get_llm_client


# ==================== 智能参数构造 ====================


async def build_tool_arguments(
    step: Dict[str, Any],
    state: "ExecutionState",
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    智能构造工具参数

    核心逻辑(用户定义优先):
    1. ⭐ 完全固定(is_pinned=True, pinned_parameters存在): 直接使用,跳过LLM
    2. ⭐ 模板化固定(is_pinned=True, parameter_template存在): LLM推断变量值并填充模板
    3. 使用step中已定义的parameters
    4. 使用LLM根据【步骤目标】构造参数

    重要: 用户定义的参数优先级最高,不会被LLM覆盖
    """
    step_name = step.get("name", "")
    step_description = step.get("description", "")
    step_type = step.get("type", "tool")

    query = state.get("query", "")
    template_id = state.get("template_id")
    intermediate_data = state.get("intermediate_data", {})
    predefined_params = step.get("parameters", {}) or {}

    is_pinned = step.get("is_pinned", False)
    pinned_parameters = step.get("pinned_parameters")
    parameter_template = step.get("parameter_template")
    template_variables = step.get("template_variables", {}) or {}

    # ⭐ 模式1: 完全固定参数 - 直接使用,跳过LLM
    if is_pinned and pinned_parameters:
        logger.info(f"📌 完全固定步骤 [{step_name}]: 直接使用用户指定参数")
        final_params = dict(pinned_parameters)
        if "template_id" not in final_params and template_id:
            final_params["template_id"] = template_id
        return _supplement_params_from_state(step_name, final_params, intermediate_data)

    # ⭐ 模式2: 模板化固定参数 - LLM推断变量值并填充模板
    if is_pinned and parameter_template:
        logger.info(f"📋 模板化固定步骤 [{step_name}]: LLM推断变量值并填充模板")

        variables_desc = "\n".join(
            f"- {k}: {v}" for k, v in template_variables.items())

        llm_client = get_llm_client()
        system_prompt = f"""你是参数推断助手。用户有一个固定的参数模板,你需要根据用户输入推断模板变量的值。

【参数模板】
```json
{json.dumps(parameter_template, ensure_ascii=False, indent=2)}
```

【模板变量说明】
{variables_desc}

【用户输入】
{query}

【任务】
分析用户输入,推断每个模板变量($开头)应该填充的值。

【返回格式】
返回JSON,包含每个变量的推断值:
```json
{{
  "$TOPIC": "推断出的值"
}}
```

【规则】
1. 仔细分析用户输入,提取与变量说明匹配的信息
2. 如果用户输入中没有明确提及,根据上下文合理推断
3. 返回的值应该可以直接替换到模板中
4. 只返回JSON,不要其他文字
"""

        try:
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请根据用户输入推断变量值"},
                ],
                db=db,
                max_tokens=1024,
            )

            logger.info(f"🔮 LLM推断变量值: {response}")

            # 将变量值填充到模板中
            template_str = json.dumps(parameter_template, ensure_ascii=False)
            for var_name, var_value in response.items():
                if var_name.startswith("$"):
                    template_str = template_str.replace(
                        var_name, str(var_value))

            final_params = json.loads(template_str)

            if "template_id" not in final_params and template_id:
                final_params["template_id"] = template_id

            logger.info(
                f"📋 填充后的参数: {json.dumps(final_params, ensure_ascii=False, default=str)[:500]}")
            return _supplement_params_from_state(step_name, final_params, intermediate_data)

        except Exception as e:
            logger.error(f"❌ 模板变量推断失败: {e}")
            return dict(parameter_template)

    # ⭐ 模式3: 用户预定义参数 - 直接使用
    if predefined_params:
        logger.info(f"📝 使用用户预定义参数: {list(predefined_params.keys())}")
        final_params = dict(predefined_params)
        if "template_id" not in final_params and template_id:
            final_params["template_id"] = template_id
        return _supplement_params_from_state(step_name, final_params, intermediate_data)

    # ⭐ 模式4: LLM智能推断参数
    # 获取工具元数据
    tool_meta = get_tool_metadata(step_name) if step_type == "tool" else None
    param_schema = tool_meta.get("parameters", {}) if tool_meta else {}

    # 构建当前状态摘要
    state_summary = _summarize_state(state)

    llm_client = get_llm_client()

    system_prompt = f"""你是参数构造助手。你需要根据【当前步骤的目标】来构造工具参数。

【重要理解】
- 当前步骤目标: 这是本步骤具体要做的事情
- 用户原始输入: 这是用户提供的原始信息，作为背景参考

⚠️ 核心原则: 工具参数（尤其是 query）应该反映【当前步骤的目标】，而不是简单复制用户原始输入!

【当前步骤信息】
- 工具/智能体名称: {step_name}
- 步骤目标: {step_description}

【用户原始输入(背景参考)】
{query}

【工具参数定义】
{json.dumps(param_schema, ensure_ascii=False, indent=2)}

【当前执行状态】
{state_summary}

【任务】
根据【当前步骤目标】和【执行状态】，生成工具参数（纯 JSON）。

【规则 - 重要！】
1. **query 参数构造**: 
   - 如果工具需要 query 参数，应该根据【步骤目标】来构造
   - 例如: 步骤目标是"检索关于安全的文档"，则 query 应该是"安全相关的文档"
   - 不要简单地把用户原始输入作为 query!
2. **template_id**: 直接使用状态中的 template_id = {template_id}
3. **document_ids/documents**: 如果状态中有，直接使用
4. 只包含参数定义中的字段
5. 返回纯 JSON，无其他文字
"""

    user_prompt = f"为工具/智能体 {step_name} 生成参数。当前步骤目标: {step_description}"

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
            max_tokens=2048,
        )

        logger.info(f"🤖 LLM 生成参数: {response}")

        # 确保 template_id 正确
        if "template_id" not in response and template_id is not None:
            response["template_id"] = template_id

        return response

    except Exception as e:
        logger.error(f"❌ LLM 生成参数失败: {e}，使用 fallback")
        # fallback: 根据步骤目标构造简单参数
        return _build_fallback_arguments(step, state)


def _summarize_state(state: "ExecutionState") -> str:
    """生成状态摘要供 LLM 使用"""
    summary = {
        "query": state.get("query", "")[:200],
        "template_id": state.get("template_id"),
    }

    # 添加中间数据
    intermediate = state.get("intermediate_data", {})

    # 文档 ID 列表
    if intermediate.get("document_ids"):
        doc_ids = intermediate["document_ids"]
        summary["document_ids"] = f"{len(doc_ids)} 个文档 ID"
        summary["document_ids_sample"] = doc_ids[:5]

    # 文档列表
    if intermediate.get("documents"):
        docs = intermediate["documents"]
        summary["documents"] = f"{len(docs)} 篇文档可用"
        summary["documents_titles"] = [
            d.get("title", "")[:50] for d in docs[:5]]

    # ⭐ 大纲
    if intermediate.get("outline"):
        outline = intermediate["outline"]
        if isinstance(outline, dict):
            sections = outline.get("sections", [])
            summary["outline"] = {
                "title": outline.get("title", "")[:100],
                "sections_count": len(sections),
                "sections": [s.get("title", "")[:50] for s in sections[:5]]
            }
        else:
            summary["outline"] = "已生成大纲"

    # ⭐ 提取的内容
    if intermediate.get("extracted_content"):
        extracted = intermediate["extracted_content"]
        if isinstance(extracted, dict):
            summary["extracted_content"] = f"{len(extracted)} 个章节的内容已提取"
        else:
            summary["extracted_content"] = "已提取内容"

    # ⭐ 生成的文档
    if intermediate.get("composed_document"):
        doc = intermediate["composed_document"]
        if isinstance(doc, dict):
            summary["composed_document"] = {
                "title": doc.get("title", "")[:100],
                "word_count": doc.get("word_count", len(doc.get("content", ""))),
                "has_content": bool(doc.get("content"))
            }
        else:
            summary["composed_document"] = "已生成文档"

    # 添加已执行步骤
    tool_results = state.get("tool_results", [])
    agent_results = state.get("agent_results", [])
    if tool_results or agent_results:
        completed_steps = []
        for r in tool_results:
            step_info = f"工具 {r.get('name')}: {'成功' if r.get('result', {}).get('success') else '失败'}"
            # 添加关键结果信息
            result = r.get('result', {})
            if r.get('name') in ['multi_query_search', 'es_fulltext_search'] and result.get('success'):
                step_info += f" - 检索到 {len(result.get('documents', []))} 篇文档"
            elif r.get('name') == 'generate_outline' and result.get('success'):
                outline = result.get('outline', {})
                if isinstance(outline, dict):
                    step_info += f" - 生成 {len(outline.get('sections', []))} 个章节"
                elif isinstance(outline, list):
                    step_info += f" - 生成 {len(outline)} 个章节"
            completed_steps.append(step_info)
        for r in agent_results:
            completed_steps.append(
                f"智能体 {r.get('name')}: {'成功' if r.get('result', {}).get('success') else '失败'}")
        summary["completed_steps"] = completed_steps

    return json.dumps(summary, ensure_ascii=False, indent=2)


def _supplement_params_from_state(
    step_name: str,
    params: Dict[str, Any],
    intermediate_data: Dict[str, Any]
) -> Dict[str, Any]:
    """
    从intermediate_data中补充工具所需但用户未指定的参数

    重要: 用户已指定的参数不会被覆盖
    """
    # document_extraction 需要 outline 和 documents
    if step_name == "document_extraction":
        if "outline" not in params:
            params["outline"] = intermediate_data.get("outline", {})
        if "documents" not in params:
            params["documents"] = intermediate_data.get("documents", [])

    # document_compose 需要 outline 和 extracted_content
    elif step_name == "document_compose":
        if "outline" not in params:
            params["outline"] = intermediate_data.get("outline", {})
        if "extracted_content" not in params:
            params["extracted_content"] = intermediate_data.get(
                "extracted_content", {})

    # document_review 需要 document
    elif step_name == "document_review":
        if "document" not in params:
            params["document"] = intermediate_data.get("composed_document", {})

    # 文档读取工具需要 document_ids
    elif step_name in ["get_document_contents", "skim_documents", "read_documents"]:
        if "document_ids" not in params:
            params["document_ids"] = intermediate_data.get("document_ids", [])

    return params


def _build_fallback_arguments(
    step: Dict[str, Any],
    state: "ExecutionState",
) -> Dict[str, Any]:
    """回退参数构造（当 LLM 失败时使用）"""
    step_name = step.get("name", "")
    step_description = step.get("description", "")

    query = state.get("query", "")
    template_id = state.get("template_id")
    intermediate = state.get("intermediate_data", {})

    # 简化用户输入
    user_input_brief = query[:50] + "..." if len(query) > 50 else query
    # 使用步骤目标构造 query
    goal_based_query = f"{step_description}：基于用户输入'{user_input_brief}'"

    fallback_params = {"template_id": template_id}

    if step_name in ["get_document_contents", "skim_documents", "read_documents"]:
        fallback_params["document_ids"] = intermediate.get("document_ids", [])
        if step_name == "read_documents":
            fallback_params["max_documents"] = 10
    elif step_name == "analyze_documents":
        fallback_params["query"] = goal_based_query
        fallback_params["documents"] = intermediate.get("documents", [])
        fallback_params["max_context_length"] = 10000
    elif step_name == "search_documents_by_classification":
        fallback_params["class_code"] = None
    elif step_name in ["multi_query_search", "es_fulltext_search"]:
        fallback_params["query"] = goal_based_query
    elif step_name == "get_template_statistics":
        pass  # 只需要 template_id
    # ⭐ 新增：内容提取工具
    elif step_name == "document_extraction":
        fallback_params["query"] = goal_based_query
        fallback_params["outline"] = intermediate.get("outline", {})
        fallback_params["documents"] = intermediate.get("documents", [])
    # ⭐ 新增：文档组合工具
    elif step_name == "document_compose":
        fallback_params["query"] = goal_based_query
        fallback_params["outline"] = intermediate.get("outline", {})
        fallback_params["extracted_content"] = intermediate.get(
            "extracted_content", {})
    # ⭐ 新增：文档审查工具
    elif step_name == "document_review":
        fallback_params["document"] = intermediate.get("composed_document", {})
    else:
        # 默认添加 query
        fallback_params["query"] = goal_based_query

    return fallback_params

# ==================== 用户意图识别 ====================


async def analyze_user_intent(
    query: str,
    conversation_history: List[Dict[str, Any]],
    db: AsyncSession,
) -> Dict[str, Any]:
    """
    分析用户意图

    Args:
        query: 当前用户输入
        conversation_history: 对话历史
        db: 数据库会话

    Returns:
        {
            "intent_type": "response_to_hint" | "new_question" | "follow_up",
            "reasoning": "判断理由"
        }
    """
    llm_client = get_llm_client()

    # 构建对话上下文（只取最后5轮）
    recent_messages = conversation_history[-10:]  # 最后5轮对话
    context_lines = []
    for msg in recent_messages:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            context_lines.append(f"用户: {content}")
        elif role == "assistant":
            context_lines.append(f"助手: {content[:200]}...")  # 截断过长内容

    conversation_context = "\n".join(context_lines)

    system_prompt = """你是一个用户意图分析助手。分析用户输入属于以下哪种意图：

1. **response_to_hint**: 用户回应了系统的提示（如"继续"、"使用前20篇"、"好的"、"行"等简短确认）
   - 特征：用户输入非常简短，像是对上一条消息的回应
   - 上一条assistant消息通常包含"检索到XX篇文档"、"请选择"等提示

2. **new_question**: 用户提出了全新的问题，与之前的对话无关
   - 特征：问题完整、独立，不依赖之前的上下文

3. **follow_up**: 追问或延续之前的话题
   - 特征：使用代词（它、这个、那个）、或者问题与之前的话题相关

请返回JSON格式：
{
    "intent_type": "response_to_hint" | "new_question" | "follow_up",
    "reasoning": "简要说明判断理由"
}
"""

    user_prompt = f"""【对话上下文】
{conversation_context}

【当前用户输入】
{query}

请分析用户意图。"""

    try:
        response = await llm_client.extract_json_response(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )
        logger.info(f"💡 意图识别结果: {response}")

        return response

    except Exception as e:
        logger.error(f"⚠️ 意图识别失败: {e}，默认为new_question")
        return {
            "intent_type": "new_question",
            "reasoning": "意图识别失败，默认为新问题",
        }


async def filter_relevant_context(
    query: str,
    conversation_history: List[Dict[str, Any]],
    db: AsyncSession,
) -> str:
    """
    从历史对话中过滤出与当前问题相关的上下文

    Args:
        query: 当前问题
        conversation_history: 对话历史
        db: 数据库会话

    Returns:
        过滤后的相关上下文字符串
    """
    llm_client = get_llm_client()

    # 构建历史对话（只取最后5轮）
    recent_messages = conversation_history[-10:]
    context_lines = []
    for i, msg in enumerate(recent_messages):
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "user":
            context_lines.append(f"[{i+1}] 用户: {content}")
        elif role == "assistant":
            # 截取前500字符
            context_lines.append(f"[{i+1}] 助手: {content[:500]}...")

    conversation_context = "\n".join(context_lines)

    system_prompt = """你是一个上下文过滤助手。从历史对话中提取与当前问题相关的关键信息。

要求：
1. 只保留与当前问题**直接相关**的内容
2. 删除无关的对话轮次
3. 精简提取，不要原样复制
4. 如果没有相关上下文，返回空字符串

返回格式：直接返回过滤后的上下文文本，不需要JSON。
"""

    user_prompt = f"""【历史对话】
{conversation_context}

【当前问题】
{query}

请提取与当前问题相关的上下文。"""

    try:
        response = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
        )

        logger.info(f"📋 过滤后的上下文: {response[:200]}...")
        return response.strip()

    except Exception as e:
        logger.error(f"⚠️ 上下文过滤失败: {e}")
        return ""


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
    session_id = state["session_id"]

    # 从 config 获取 db
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore

    llm_client = get_llm_client()

    # 获取对话历史（用于元问题识别和回答）
    conversation_manager = get_conversation_manager()
    session_data = conversation_manager.get_session(session_id)
    conversation_history = session_data.get(
        "messages", []) if session_data else []

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
2. **识别问题类型**：
   - **元问题（Meta Query）**：关于对话本身的统计问题
     * 示例："我问了几次XX？"、"这是第几个问题？"、"我们讨论了什么？"
     * 处理：直接使用 llm_direct 模式回答，不要检索文档
   - **文档查询**：关于文档内容的实际问题
     * 示例："XX文档讲了什么？"、"XX的主要内容是？"
     * 处理：使用检索+问答流程
3. **选择模式**：根据查询类型选择最适合的执行模式
4. **选择组件**：
   - tool_only: 列出需要调用的工具名称
   - agent_only: 指定要调用的智能体名称
   - agent_chain: 按顺序列出要调用的智能体名称
   - hybrid: 混合工具和智能体名称
   - llm_direct: 直接使用你的知识回答（用于元问题、通用知识问题等）

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

示例6 - LLM直接回答（通用知识）：
问题: "什么是人工智能？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是通用知识问题，不需要查询文档，直接回答",
    "execution_plan": [],
    "direct_answer": "人工智能（Artificial Intelligence, AI）是计算机科学的一个分支..."
}}

示例7 - 元问题（对话统计）：
问题: "我问了几次 国家地震应急预案？"
返回:
{{
    "execution_pattern": "llm_direct",
    "reasoning": "这是一个元问题，用户询问的是对话历史中提及某主题的次数统计，需要直接分析对话记录，不需要检索文档",
    "execution_plan": [],
    "direct_answer": "根据对话历史，您提到'国家地震应急预案'共X次..."
}}

示例8 - 元问题vs文档查询的区分：
问题A: "我之前问过什么问题？" -> llm_direct（元问题，关于对话本身）
问题B: "之前查到的文档都讲了什么？" -> llm_direct（基于对话历史回答，不需要重新检索）
问题C: "国家地震应急预案的主要内容是什么？" -> agent_chain（文档查询，需要检索+问答）

【重要提示】
- **元问题识别**：凡是询问"我问了几次"、"我们讨论了什么"、"之前的对话"等关于对话本身的问题，必须使用 llm_direct
- 如果用户要分析文档内容（"总结"、"归纳"、"都讲了什么"），使用 analyze_documents 工具（它会内部决定批量or逐份）
- 如果用户问"查找XXX相关的文档"等语义检索问题，使用 retrieval_agent 智能体
- 区分"文档分析"和"语义检索"两种场景

现在，请为以下用户问题制定执行方案。只返回JSON，不要其他内容。
"""

    try:
        logger.info("🧠 调用LLM进行任务规划...")
        await asyncio.sleep(0.3)  # 规划延迟

        # 构建规划请求消息
        planning_messages = [
            {"role": "system", "content": system_prompt},
        ]

        # 如果有对话历史，附加最近的对话（用于元问题识别）
        if conversation_history and len(conversation_history) > 1:
            # 取最近5轮对话
            recent_messages = conversation_history[-10:]
            context_summary = []
            for msg in recent_messages:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "user":
                    context_summary.append(f"用户: {content[:100]}...")
                elif role == "assistant":
                    context_summary.append(f"助手: {content[:100]}...")

            context_text = "\n".join(context_summary)
            planning_messages.append(
                {
                    "role": "user",
                    "content": f"【对话历史】\n{context_text}\n\n【当前问题】\n{query}\n\n请为这个问题制定执行方案。",
                }
            )
        else:
            planning_messages.append(
                {"role": "user", "content": f"请为这个问题制定执行方案：{query}"}
            )

        response = await llm_client.extract_json_response(
            messages=planning_messages,
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
                # 没有直接答案，让LLM生成一个（带上对话历史，用于元问题）
                logger.info("📋 LLM未返回直接答案，生成回答（带对话历史）")

                # 构建消息列表
                llm_messages = [
                    {
                        "role": "system",
                        "content": "你是一个专业的问答助手。如果用户询问对话历史相关的问题（如'我问了几次XX'、'之前讨论了什么'），请基于对话历史进行统计和分析。",
                    }
                ]

                # 添加对话历史（元问题需要）
                if conversation_history and len(conversation_history) > 1:
                    # 添加历史消息
                    for msg in conversation_history[-20:]:  # 最近10轮对话
                        role = msg.get("role")
                        content = msg.get("content", "")
                        if role in ["user", "assistant"]:
                            llm_messages.append(
                                {"role": role, "content": content})

                # 添加当前问题
                llm_messages.append({"role": "user", "content": query})

                fallback_answer = await llm_client.chat_completion(
                    messages=llm_messages,
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

    # helper: 实际调用工具/智能体实现 - 使用智能参数构造
    async def _dispatch_to_impl(step: Dict[str, Any]):
        """
        通用的工具/智能体调度器（智能版）
        - 使用 LLM 根据步骤目标智能构造参数
        - 工具调用：使用新版 execute_tool 统一处理
        - 智能体调用：直接调用智能体函数
        """
        step_type = step.get("type")
        step_name = step.get("name")
        step_desc = step.get("description", "")

        # ⭐ 使用 LLM 智能构造参数（仅作参考）
        arguments = await build_tool_arguments(step, state, db)

        if step_type == "tool":
            # 创建工具上下文
            tool_ctx = ToolContext(
                db=db,
                es_client=es_client,
                es_index=es_index,
                template_id=template_id,
                session_id=session_id,
            )

            # ⭐⭐⭐ 关键工具硬编码：必须从 intermediate_data 获取真实数据 ⭐⭐⭐
            if step_name == "document_extraction":
                arguments["outline"] = state["intermediate_data"].get(
                    "outline", {})
                arguments["documents"] = state["intermediate_data"].get(
                    "documents", [])
                if "query" not in arguments:
                    arguments["query"] = query
                logger.info(
                    f"🔧 硬编码 document_extraction: outline={type(arguments['outline'])}, docs={len(arguments['documents'])}")

            if step_name == "document_compose":
                arguments["outline"] = state["intermediate_data"].get(
                    "outline", {})
                arguments["extracted_content"] = state["intermediate_data"].get(
                    "extracted_content", {})
                if "query" not in arguments:
                    arguments["query"] = query
                logger.info(
                    f"🔧 硬编码 document_compose: outline={type(arguments['outline'])}, extracted={len(arguments.get('extracted_content', {}))} 章节")

            if step_name == "document_review":
                composed_doc = state["intermediate_data"].get(
                    "composed_document", {})
                if composed_doc:
                    arguments["document"] = composed_doc
                    logger.info(
                        f"🔧 硬编码 document_review: title={composed_doc.get('title', '')}, content_len={len(composed_doc.get('content', ''))}")
                else:
                    logger.warning("⚠️ document_review: 未找到 composed_document")

            # 其他工具的参数补充（如果 LLM 没有生成）
            if step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                if "document_ids" not in arguments:
                    arguments["document_ids"] = state["intermediate_data"].get(
                        "document_ids", [])
                if step_name == "read_documents" and "max_documents" not in arguments:
                    arguments["max_documents"] = max_read_documents

            if step_name == "analyze_documents":
                if "documents" not in arguments:
                    arguments["documents"] = state["intermediate_data"].get(
                        "documents", [])
                if "max_context_length" not in arguments:
                    arguments["max_context_length"] = rag_max_length

            # 输出最终参数（硬编码之后）
            logger.info(
                f"📦 步骤 {step_name} 最终参数: {json.dumps(arguments, ensure_ascii=False, default=str)[:500]}...")

            # 调用新版工具执行器
            return await execute_tool(step_name, arguments, tool_ctx)

        elif step_type == "agent":
            # 智能体调用：根据 LLM 生成的参数调用
            if step_name == "retrieval_agent":
                # 使用 LLM 构造的 query
                agent_query = arguments.get("query", query)
                return await retrieve_documents_v2(
                    query=agent_query,
                    template_id=template_id,
                    session_id=session_id,
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                    top_k=arguments.get("top_k", 20),
                    enable_deduplication=True,
                )
            elif step_name == "qa_agent":
                documents = state["intermediate_data"].get("documents", [])
                agent_query = arguments.get("query", query)
                return await generate_answer_v2(
                    query=agent_query,
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
                # ⭐ 使用智能参数构造执行步骤
                result = await _dispatch_to_impl(step)

                # 记录结果
                result_entry = {
                    "step": i + 1,
                    "name": step_name,
                    "description": step_desc,
                    "result": result,
                }

                if step_type == "tool":
                    state["tool_results"].append(result_entry)
                else:
                    state["agent_results"].append(result_entry)

                # 特殊处理：更新中间数据
                if result.get("success"):
                    # 检索类工具：保存文档列表
                    if step_name in ["multi_query_search", "es_fulltext_search"]:
                        documents = result.get("documents", [])
                        document_ids = result.get("document_ids", [])
                        state["intermediate_data"]["documents"] = documents
                        state["intermediate_data"]["document_ids"] = document_ids
                        state["documents"] = documents
                        logger.info(
                            f"💾 保存检索结果: {len(documents)} 篇文档, {len(document_ids)} 个 ID")

                    elif step_type == "agent" and step_name == "retrieval_agent":
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", []
                        )
                        state["documents"] = result.get("documents", [])
                    elif (
                        step_type == "tool"
                        and step_name == "search_documents_by_classification"
                    ):
                        state["intermediate_data"]["document_ids"] = result.get(
                            "document_ids", []
                        )
                    elif step_type == "tool" and step_name in [
                        "get_document_contents",
                        "skim_documents",
                        "read_documents",
                    ]:
                        state["intermediate_data"]["documents"] = result.get(
                            "documents", []
                        )

                    # ⭐ 大纲生成工具：保存大纲
                    elif step_name == "generate_outline":
                        outline = result.get("outline", {})
                        state["intermediate_data"]["outline"] = outline
                        if isinstance(outline, dict):
                            logger.info(
                                f"💾 保存大纲: {len(outline.get('sections', []))} 个章节")
                        elif isinstance(outline, list):
                            logger.info(f"💾 保存大纲: {len(outline)} 个章节")
                        else:
                            logger.info(f"💾 保存大纲")

                    # ⭐ 内容提取工具：保存提取的内容
                    elif step_name == "document_extraction":
                        extracted_content = result.get("extracted_content", {})
                        state["intermediate_data"]["extracted_content"] = extracted_content
                        logger.info(f"💾 保存提取内容: {len(extracted_content)} 个章节")

                    # ⭐ 文档组合工具：保存生成的文档
                    elif step_name == "document_compose":
                        document = result.get("document", {})
                        state["intermediate_data"]["composed_document"] = document
                        logger.info(
                            f"💾 保存生成文档: {document.get('title', '')}, 字数: {len(document.get('content', ''))}")

                    # ⭐ 文档审查工具：保存审查后的文档
                    elif step_name == "document_review":
                        reviewed_document = result.get("reviewed_document", {})
                        state["intermediate_data"]["reviewed_document"] = reviewed_document
                        logger.info(
                            f"💾 保存审查文档: {reviewed_document.get('title', '')}, 字数: {len(reviewed_document.get('content', ''))}")

                # ⭐⭐⭐ 最后一步且是生成类工具，直接写入 final_answer ⭐⭐⭐
                is_last_step = (i == len(plan) - 1)
                if is_last_step and result.get("success"):
                    if step_name == "document_review":
                        reviewed = result.get("reviewed_document", {})
                        if reviewed and reviewed.get("content"):
                            title = reviewed.get("title", "生成的文档")
                            content = reviewed.get("content", "")
                            state["final_answer"] = f"# {title}\n\n{content}"
                            logger.info(
                                f"✅ 最后一步 document_review，直接写入 final_answer")

                    elif step_name == "document_compose":
                        doc = result.get("document", {})
                        if doc and doc.get("content"):
                            title = doc.get("title", "生成的文档")
                            content = doc.get("content", "")
                            state["final_answer"] = f"# {title}\n\n{content}"
                            logger.info(
                                f"✅ 最后一步 document_compose，直接写入 final_answer")

                    elif step_name == "generate_outline":
                        outline = result.get("outline", {})
                        if outline:
                            if isinstance(outline, dict):
                                title = outline.get("title", "生成的大纲")
                                sections = outline.get("sections", [])
                                content_lines = [f"# {title}", ""]
                                for sec in sections:
                                    if isinstance(sec, dict):
                                        content_lines.append(
                                            f"## {sec.get('title', '')}")
                                        if sec.get('description'):
                                            content_lines.append(
                                                sec.get('description'))
                                        content_lines.append("")
                                    else:
                                        content_lines.append(f"## {sec}")
                                        content_lines.append("")
                                state["final_answer"] = "\n".join(
                                    content_lines)
                            elif isinstance(outline, list):
                                content_lines = ["生成的大纲", ""]
                                for sec in outline:
                                    content_lines.append(f"## {sec}")
                                    content_lines.append("")
                                state["final_answer"] = "\n".join(
                                    content_lines)
                            else:
                                state["final_answer"] = f"# 生成的大纲\n\n{str(outline)}"
                            logger.info(
                                f"✅ 最后一步 generate_outline，直接写入 final_answer")

                    elif step_name == "document_extraction":
                        extracted = result.get("extracted_content", {})
                        if extracted:
                            content_lines = ["提取的内容", ""]
                            for section_name, chunks in extracted.items():
                                content_lines.append(f"## {section_name}")
                                if isinstance(chunks, list):
                                    for chunk in chunks:
                                        if isinstance(chunk, dict):
                                            content_lines.append(
                                                chunk.get("content", str(chunk)))
                                        else:
                                            content_lines.append(str(chunk))
                                else:
                                    content_lines.append(str(chunks))
                                content_lines.append("")
                            state["final_answer"] = "\n".join(content_lines)
                            logger.info(
                                f"✅ 最后一步 document_extraction，直接写入 final_answer")

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
                    "result": {"success": False, "error": str(e)},
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

    让 LLM 根据上下文智能决定如何回答：
    - 如果有完整文档，直接使用
    - 如果需要总结，生成总结
    - 如果结果不好，自己重新回答
    """
    logger.info("📝 ========== 节点: 生成最终答案 ===========")

    query = state["query"]
    db: AsyncSession = config.get("configurable", {}).get("db")  # type: ignore
    intermediate = state.get("intermediate_data", {})

    try:
        # 如果已经有答案（qa_agent生成的），直接返回
        if state["final_answer"]:
            logger.info("✅ 已有最终答案，跳过生成")
            state["success"] = True
            return state

        # 根据执行模式处理特殊情况
        if state["execution_pattern"] == "llm_direct":
            state["success"] = True
            return state

        elif state["execution_pattern"] == "agent_only":
            if state["documents"]:
                state["final_answer"] = None
                logger.info("📚 仅检索模式，不生成答案")
            else:
                state["final_answer"] = "抱歉，没有找到相关文档。"
                logger.warning("⚠️ 未找到文档")
            state["success"] = True
            return state

        # ⭐⭐⭐ 收集所有可用的输出数据，让 LLM 智能决定如何回答 ⭐⭐⭐
        logger.info("🤖 让 LLM 智能决定如何回答")

        llm_client = get_llm_client()

        # 收集可用的输出字段
        available_outputs = {}

        # 审查后的文档（最高优先级）
        reviewed_doc = intermediate.get("reviewed_document", {})
        if reviewed_doc and reviewed_doc.get("content"):
            available_outputs["reviewed_document"] = {
                "title": reviewed_doc.get("title", ""),
                "content": reviewed_doc.get("content", ""),
                "word_count": len(reviewed_doc.get("content", "")),
                "说明": "经过校对和润色的最终文档"
            }

        # 生成的文档
        composed_doc = intermediate.get("composed_document", {})
        if composed_doc and composed_doc.get("content"):
            available_outputs["composed_document"] = {
                "title": composed_doc.get("title", ""),
                "content": composed_doc.get("content", ""),
                "word_count": len(composed_doc.get("content", "")),
                "说明": "根据大纲和提取内容生成的文档"
            }

        # 提取的内容
        extracted = intermediate.get("extracted_content", {})
        if extracted:
            available_outputs["extracted_content"] = {
                "sections": list(extracted.keys()) if isinstance(extracted, dict) else [],
                "说明": "从检索文档中提取的内容片段"
            }

        # 大纲
        outline = intermediate.get("outline", {})
        if outline:
            available_outputs["outline"] = {
                "structure": outline if isinstance(outline, (dict, list)) else str(outline)[:500],
                "说明": "生成的文档大纲"
            }

        # 检索到的文档
        documents = intermediate.get("documents", [])
        if documents:
            available_outputs["documents"] = {
                "count": len(documents),
                "titles": [d.get("title", "")[:50] for d in documents[:5]],
                "说明": "检索到的相关文档"
            }

        # 构建执行步骤摘要
        steps_summary = []
        for i, tool_result in enumerate(state["tool_results"]):
            name = tool_result.get("name", "")
            desc = tool_result.get("description", "")
            result = tool_result.get("result", {})
            success = result.get("success", False)
            error = result.get("error", "") if not success else ""
            steps_summary.append({
                "step": i + 1,
                "tool": name,
                "description": desc,
                "success": success,
                "error": error[:100] if error else ""
            })

        logger.info(f"🤖 构建执行步骤摘要 {steps_summary}")

        # 构建 LLM 决策 prompt
        system_prompt = """你是一个智能答案生成器。根据执行结果和可用输出，决定如何最佳地回答用户。

【决策逻辑】
1. 如果有 reviewed_document 且内容完整 → 直接输出该文档内容
2. 否则如果有 composed_document 且内容完整 → 直接输出该文档内容
3. 如果文档内容质量不佳（太短、不完整、不相关）→ 根据其他数据重新生成答案
4. 如果没有文档但有其他有用信息 → 综合总结回答
5. 如果执行失败或数据不足 → 说明原因并尽可能提供帮助

【输出要求】
- 使用 Markdown 格式
- 如果直接使用文档，不要添加额外的"执行过程"描述，直接输出文档内容
- 如果需要总结，请按用户问题组织答案
- 语气专业、友好

【重要】
- 绝对不要编造信息
- 如果有完整文档，优先直接使用，不要画蛇添足
"""

        # 构建用户 prompt
        user_prompt = f"""【用户问题】
{query}

【执行步骤摘要】
{json.dumps(steps_summary, ensure_ascii=False, indent=2)}

【可用输出数据】
"""

        # 添加可用输出
        for field_name, field_data in available_outputs.items():
            if field_name in ["reviewed_document", "composed_document"]:
                # 文档类：直接包含完整内容
                user_prompt += f"\n### {field_name}\n"
                user_prompt += f"标题: {field_data.get('title', '无标题')}\n"
                user_prompt += f"字数: {field_data.get('word_count', 0)}\n"
                user_prompt += f"说明: {field_data.get('说明', '')}\n"
                user_prompt += f"\n内容:\n{field_data.get('content', '')}\n"
            else:
                # 其他字段：简要信息
                user_prompt += f"\n### {field_name}\n"
                user_prompt += f"{json.dumps(field_data, ensure_ascii=False, indent=2)}\n"

        if not available_outputs:
            user_prompt += "\n无可用输出数据\n"

        user_prompt += "\n请根据以上信息，生成最佳答案。"

        # 调用 LLM
        final_answer = await llm_client.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            db=db,
            max_tokens=16000,  # 文档可能很长
        )

        state["final_answer"] = final_answer
        state["success"] = True
        logger.info(f"✅ LLM 智能生成最终答案，字数: {len(final_answer)}")

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
    session_id: Optional[str] = None,
    user_id: Optional[int] = None,
    user_input: Optional[Any] = None,
):
    """
    主路由器执行函数：支持多轮对话和用户干预

    核心改进：
    1. 每次用户输入都创建全新的state对象
    2. 会话管理器只保存历史消息
    3. 生成答案时，如果需要历史上下文，从会话中获取并用大模型过滤

    Args:
        query: 用户查询
        template_id: 模板ID
        db: 数据库会话
        es_client: ES客户端
        es_index: ES索引
        session_id: 会话ID（由前端传入，如果为None则自动生成）
        user_id: 用户ID
        user_input: 用户输入（当会话处于waiting_input状态时）

    Yields:
        dict: 每一步的执行结果
            - type: 'plan' | 'step_result' | 'user_input_request' | 'final'
            - data: 具体数据
    """
    import uuid

    # 获取会话管理器
    conversation_manager = get_conversation_manager()

    # 如果没有session_id，生成新的
    if session_id is None:
        session_id = str(uuid.uuid4())
        logger.info(f"🆕 生成新会话: {session_id}")

    # 检查会话是否存在
    session_data = conversation_manager.get_session(session_id)

    if session_data is None:
        # 创建新会话
        session_data = conversation_manager.create_session(
            session_id=session_id,
            template_id=template_id,
            initial_query=query,
            user_id=user_id,
        )
        logger.info(f"✨ 创建新会话: {session_id}")
    else:
        logger.info(f"🔄 恢复现有会话: {session_id}")

        # 添加用户消息到对话历史
        conversation_manager.add_message(
            session_id=session_id,
            role="user",
            content=query,
        )

    # ⭐ 关键：每次都创建全新的state对象，不依赖会话中的旧state
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

    # ⭐ 用户意图识别（仅在有历史对话时）
    messages = session_data.get("messages", [])
    if len(messages) > 1:  # 有历史对话（不包括当前query）
        logger.info("🔍 检测到历史对话，开始用户意图识别")

        intent_result = await analyze_user_intent(
            query=query,
            conversation_history=messages,
            db=db,
        )

        # response_to_hint / new_question / follow_up
        intent_type = intent_result.get("intent_type")
        intent_reasoning = intent_result.get("reasoning", "")

        logger.info(f"💡 用户意图: {intent_type}, 原因: {intent_reasoning}")

        if intent_type == "response_to_hint":
            # 用户回应了hint提示（如"继续"、"用前20篇"等）
            logger.info("✅ 用户选择继续使用当前结果")

            # 从会话的state中获取上次检索的文档
            previous_documents = session_data.get(
                "state", {}).get("documents", [])

            if previous_documents:
                logger.info(f"📚 使用上次检索的{len(previous_documents)}篇文档继续执行")

                # 将文档放入state，然后直接执行QA生成
                state["documents"] = previous_documents
                state["intermediate_data"]["documents"] = previous_documents
                state["execution_pattern"] = "retrieval_qa"  # 设置执行模式
                state["execution_plan"] = [
                    {
                        "type": "agent",
                        "name": "qa_agent",
                        "description": "基于检索结果生成答案",
                    }
                ]

                # 不再需要规划步骤，直接执行QA
                logger.info("🔄 跳过规划步骤，直接执行QA生成")
            else:
                # 如果没有上次的文档，则当作新问题处理
                logger.warning("⚠️ 未找到上次检索的文档，将当作新问题处理")
                intent_type = "new_question"

        elif intent_type == "follow_up":
            # 追问或延续话题，需要结合历史上下文
            logger.info("🔗 检测到追问，获取历史上下文进行归并")

            # 从历史消息中获取相关上下文
            relevant_context = await filter_relevant_context(
                query=query,
                conversation_history=messages,
                db=db,
            )

            # 将相关上下文合并到query中
            if relevant_context:
                enhanced_query = (
                    f"【历史上下文】\n{relevant_context}\n\n【当前问题】\n{query}"
                )
                state["query"] = enhanced_query
                logger.info(f"📝 增强后的查询: {enhanced_query[:100]}...")

        # intent_type == "new_question" 时，直接使用原query，继续执行

    logger.info(f"🆕 创建新的执行状态，query={state['query'][:100]}...")

    # ========== 第一步：规划 ==========
    if not state.get("execution_plan"):
        logger.info("🧠 ========== 第一步：规划 ===========")

        config = {"configurable": {
            "db": db, "es": es_client, "es_index": es_index}}
        state = await plan_execution(state, config)

        # Yield 执行计划
        yield {
            "type": "plan",
            "data": {
                "session_id": session_id,
                "execution_pattern": state["execution_pattern"],
                "execution_plan": state["execution_plan"],
                "reasoning": state["reasoning"],
            },
        }

    # ========== 第二步：执行 ==========
    if state["execution_pattern"] != "llm_direct" and not state.get("final_answer"):
        logger.info("🛠️ ========== 第二步：执行 ===========")

        # 执行步骤，支持用户干预
        async for result in execute_steps_with_intervention(
            session_id=session_id,
            state=state,
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            query=query,
        ):
            yield result

    # ========== 第三步：总结 ==========
    logger.info("📝 ========== 第三步：总结 ===========")

    config = {"configurable": {"db": db, "es": es_client, "es_index": es_index}}
    state = await finalize_answer(state, config)

    # 添加AI回复到对话历史
    if state.get("final_answer"):
        conversation_manager.add_message(
            session_id=session_id,
            role="assistant",
            content=state["final_answer"],
        )

    # 标记会话完成
    conversation_manager.complete_session(
        session_id, state.get("final_answer"))

    # Yield 最终结果
    yield {
        "type": "final",
        "data": {
            "session_id": session_id,
            "final_answer": state["final_answer"],
            "documents": state["documents"],
            "success": state["success"],
            "error": state.get("error"),
        },
    }


async def execute_steps_with_intervention(
    session_id: str,
    state: ExecutionState,
    db: AsyncSession,
    es_client,
    es_index: str,
    template_id: int,
    query: str,  # 这个参数不再需要，使用state中的query
):
    """
    执行步骤，支持用户干预

    用户干预场景：
    1. 检索结果过多（>20篇）：请求用户选择或精化查询
    2. 检索结果过少（<3篇）：提示用户重新输入问题
    3. 文档过多需要阅读：请求用户选择重点文档
    """
    from core.conversation_manager import get_conversation_manager

    conversation_manager = get_conversation_manager()

    max_read_documents = 10
    rag_max_length = 10000

    # 使用state中的query
    current_query = state["query"]

    # 逐步执行（不再使用current_step，每次都从头开始）
    for i, step in enumerate(state["execution_plan"]):
        step_type = step.get("type")
        step_name = step.get("name")
        step_desc = step.get("description", "")

        logger.info(f"🔧 执行第{i+1}步: {step_type}/{step_name}")

        try:
            result = None

            # ⭐ 使用 LLM 智能构造参数（仅作参考）
            arguments = await build_tool_arguments(step, state, db)

            # 执行工具或智能体
            if step_type == "tool":
                # 创建工具上下文
                tool_ctx = ToolContext(
                    db=db,
                    es_client=es_client,
                    es_index=es_index,
                    template_id=template_id,
                    session_id=session_id,
                )

                # ⭐⭐⭐ 关键工具硬编码：必须从 intermediate_data 获取真实数据，不能让 LLM 猜 ⭐⭐⭐
                # 使用独立的 if 语句，不使用 elif，确保每个工具都能正确处理

                if step_name == "document_extraction":
                    # 内容提取：需要大纲 + 文档，必须从 intermediate_data 获取
                    arguments["outline"] = state["intermediate_data"].get(
                        "outline", {})
                    arguments["documents"] = state["intermediate_data"].get(
                        "documents", [])
                    if "query" not in arguments:
                        arguments["query"] = current_query
                    logger.info(
                        f"🔧 硬编码 document_extraction: outline={type(arguments['outline'])}, docs={len(arguments['documents'])}")

                if step_name == "document_compose":
                    # 文档组合：需要大纲 + 提取的内容，必须从 intermediate_data 获取
                    arguments["outline"] = state["intermediate_data"].get(
                        "outline", {})
                    arguments["extracted_content"] = state["intermediate_data"].get(
                        "extracted_content", {})
                    if "query" not in arguments:
                        arguments["query"] = current_query
                    logger.info(
                        f"🔧 硬编码 document_compose: outline={type(arguments['outline'])}, extracted={len(arguments.get('extracted_content', {}))} 章节")

                if step_name == "document_review":
                    # 文档审查：需要完整的生成文档，必须从 intermediate_data 获取
                    composed_doc = state["intermediate_data"].get(
                        "composed_document", {})
                    if composed_doc:
                        arguments["document"] = composed_doc
                        logger.info(
                            f"🔧 硬编码 document_review: title={composed_doc.get('title', '')}, content_len={len(composed_doc.get('content', ''))}")
                    else:
                        logger.warning(
                            "⚠️ document_review: 未找到 composed_document，使用 LLM 生成的参数")

                # 其他工具的参数补充（如果 LLM 没有生成）
                if step_name in ["get_document_contents", "skim_documents", "read_documents"]:
                    if "document_ids" not in arguments:
                        arguments["document_ids"] = state["intermediate_data"].get(
                            "document_ids", [])
                    if step_name == "read_documents" and "max_documents" not in arguments:
                        arguments["max_documents"] = max_read_documents

                if step_name == "analyze_documents":
                    if "documents" not in arguments:
                        arguments["documents"] = state["intermediate_data"].get(
                            "documents", [])
                    if "max_context_length" not in arguments:
                        arguments["max_context_length"] = rag_max_length

                # 输出最终参数（硬编码之后）
                logger.info(
                    f"📦 步骤 {step_name} 最终参数: {json.dumps(arguments, ensure_ascii=False, default=str)[:500]}...")

                # 调用新版工具执行器
                result = await execute_tool(step_name, arguments, tool_ctx)

            elif step_type == "agent":
                if step_name == "retrieval_agent":
                    # 使用 LLM 构造的 query
                    agent_query = arguments.get("query", current_query)
                    result = await retrieve_documents_v2(
                        query=agent_query,
                        template_id=template_id,
                        session_id=session_id,
                        db=db,
                        es_client=es_client,
                        es_index=es_index,
                        top_k=arguments.get("top_k", 20),
                        enable_deduplication=True,
                    )
                elif step_name == "qa_agent":
                    documents = state["intermediate_data"].get("documents", [])
                    agent_query = arguments.get("query", current_query)
                    result = await generate_answer_v2(
                        query=agent_query,
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
                "result": result,
            }

            if step_type == "tool":
                state["tool_results"].append(result_entry)
            else:
                state["agent_results"].append(result_entry)

            # 更新中间数据
            if result.get("success"):
                # ⭐ 检索类工具：保存文档列表
                if step_name in ["multi_query_search", "es_fulltext_search"]:
                    documents = result.get("documents", [])
                    document_ids = result.get("document_ids", [])
                    state["intermediate_data"]["documents"] = documents
                    state["intermediate_data"]["document_ids"] = document_ids
                    state["documents"] = documents
                    logger.info(
                        f"💾 保存检索结果: {len(documents)} 篇文档, {len(document_ids)} 个 ID")

                elif step_type == "agent" and step_name == "retrieval_agent":
                    documents = result.get("documents", [])
                    state["intermediate_data"]["documents"] = documents
                    state["documents"] = documents

                    # ⭐ 检索结果检查：过多或过少时，在对话中提示用户
                    doc_count = len(documents)

                    if doc_count > 20:
                        # 结果过多，生成提示消息并直接返回
                        logger.info(f"⚠️ 检索到{doc_count}篇文档，过多，生成提示消息")

                        hint_message = f"检索到{doc_count}篇文档，结果过多。\n\n您可以：\n1. 输入更具体的问题来精化查询\n2. 直接让我使用前20篇文档继续回答\n\n请告诉我您的选择。"

                        # 直接设置为最终答案，不再yield hint事件
                        state["final_answer"] = hint_message
                        state["documents"] = documents[:20]
                        state["success"] = True

                        # ⭐ 保存文档到会话中state，供下次用户选择继续时使用
                        conversation_manager.update_state(
                            session_id=session_id,
                            state_updates={"documents": documents[:20]},
                        )

                        # 不继续执行后续步骤，直接break到总结
                        break

                    # 如果检索结果正常（≤20篇），直接继续执行，不需要用户确认

                # ⭐ 大纲生成工具：保存大纲
                elif step_name == "generate_outline":
                    outline = result.get("outline", {})
                    state["intermediate_data"]["outline"] = outline
                    if isinstance(outline, dict):
                        logger.info(
                            f"💾 保存大纲: {len(outline.get('sections', []))} 个章节")
                    elif isinstance(outline, list):
                        logger.info(f"💾 保存大纲: {len(outline)} 个章节")
                    else:
                        logger.info(f"💾 保存大纲")

                # ⭐ 内容提取工具：保存提取的内容
                elif step_name == "document_extraction":
                    extracted_content = result.get("extracted_content", {})
                    state["intermediate_data"]["extracted_content"] = extracted_content
                    logger.info(f"💾 保存提取内容: {len(extracted_content)} 个章节")

                # ⭐ 文档组合工具：保存生成的文档
                elif step_name == "document_compose":
                    document = result.get("document", {})
                    state["intermediate_data"]["composed_document"] = document
                    logger.info(
                        f"💾 保存生成文档: {document.get('title', '')}, 字数: {len(document.get('content', ''))}")

                # ⭐ 文档审查工具：保存审查后的文档
                elif step_name == "document_review":
                    reviewed_document = result.get("reviewed_document", {})
                    state["intermediate_data"]["reviewed_document"] = reviewed_document
                    logger.info(
                        f"💾 保存审查文档: {reviewed_document.get('title', '')}, 字数: {len(reviewed_document.get('content', ''))}")
                elif (
                    step_type == "tool"
                    and step_name == "search_documents_by_classification"
                ):
                    state["intermediate_data"]["document_ids"] = result.get(
                        "document_ids", []
                    )
                elif step_type == "tool" and step_name in [
                    "get_document_contents",
                    "skim_documents",
                    "read_documents",
                ]:
                    state["intermediate_data"]["documents"] = result.get(
                        "documents", []
                    )
                elif step_type == "agent" and step_name == "qa_agent":
                    state["final_answer"] = result.get("answer")

            # ⭐⭐⭐ 最后一步且是生成类工具，直接写入 final_answer ⭐⭐⭐
            is_last_step = (i == len(state["execution_plan"]) - 1)
            if is_last_step and result.get("success"):
                # 文档审查：直接输出审查后的文档
                if step_name == "document_review":
                    reviewed = result.get("reviewed_document", {})
                    if reviewed and reviewed.get("content"):
                        title = reviewed.get("title", "生成的文档")
                        content = reviewed.get("content", "")
                        state["final_answer"] = f"# {title}\n\n{content}"
                        logger.info(
                            f"✅ 最后一步 document_review，直接写入 final_answer，字数: {len(content)}")

                # 文档生成：直接输出生成的文档
                elif step_name == "document_compose":
                    doc = result.get("document", {})
                    if doc and doc.get("content"):
                        title = doc.get("title", "生成的文档")
                        content = doc.get("content", "")
                        state["final_answer"] = f"# {title}\n\n{content}"
                        logger.info(
                            f"✅ 最后一步 document_compose，直接写入 final_answer，字数: {len(content)}")

                # 大纲生成：直接输出大纲
                elif step_name == "generate_outline":
                    outline = result.get("outline", {})
                    if outline:
                        if isinstance(outline, dict):
                            title = outline.get("title", "生成的大纲")
                            # 将大纲转换为 Markdown 格式
                            sections = outline.get("sections", [])
                            content_lines = [f"# {title}", ""]
                            for sec in sections:
                                if isinstance(sec, dict):
                                    content_lines.append(
                                        f"## {sec.get('title', '')}")
                                    if sec.get('description'):
                                        content_lines.append(
                                            sec.get('description'))
                                    content_lines.append("")
                                else:
                                    content_lines.append(f"## {sec}")
                                    content_lines.append("")
                            state["final_answer"] = "\n".join(content_lines)
                        elif isinstance(outline, list):
                            content_lines = ["# 生成的大纲", ""]
                            for sec in outline:
                                content_lines.append(f"## {sec}")
                                content_lines.append("")
                            state["final_answer"] = "\n".join(content_lines)
                        else:
                            state["final_answer"] = f"# 生成的大纲\n\n{str(outline)}"
                        logger.info(
                            f"✅ 最后一步 generate_outline，直接写入 final_answer")

                # 内容提取：直接输出提取的内容
                elif step_name == "document_extraction":
                    extracted = result.get("extracted_content", {})
                    if extracted:
                        content_lines = ["# 提取的内容", ""]
                        for section_name, chunks in extracted.items():
                            content_lines.append(f"## {section_name}")
                            if isinstance(chunks, list):
                                for chunk in chunks:
                                    if isinstance(chunk, dict):
                                        content_lines.append(
                                            chunk.get("content", str(chunk)))
                                    else:
                                        content_lines.append(str(chunk))
                            else:
                                content_lines.append(str(chunks))
                            content_lines.append("")
                        state["final_answer"] = "\n".join(content_lines)
                        logger.info(
                            f"✅ 最后一步 document_extraction，直接写入 final_answer")

            logger.info(f"✅ 步骤{i+1}完成: {step_name}")

            # Yield 每一步的结果
            yield {
                "type": "step_result",
                "data": {
                    "session_id": session_id,
                    "step": i + 1,
                    "step_type": step_type,
                    "step_name": step_name,
                    "description": step_desc,
                    "result": result,
                    "documents": (
                        state.get("documents", []
                                  ) if step_type == "agent" else None
                    ),
                },
            }

        except Exception as e:
            import traceback

            logger.error(f"❌ 步骤{i+1}失败: {step_name}, 错误: {e}")
            logger.error(traceback.format_exc())

            result_entry = {
                "step": i + 1,
                "name": step_name,
                "description": step_desc,
                "result": {"success": False, "error": str(e)},
            }

            if step_type == "tool":
                state["tool_results"].append(result_entry)
            else:
                state["agent_results"].append(result_entry)

            yield {
                "type": "step_result",
                "data": {
                    "session_id": session_id,
                    "step": i + 1,
                    "step_type": step_type,
                    "step_name": step_name,
                    "description": step_desc,
                    "result": {"success": False, "error": str(e)},
                },
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
