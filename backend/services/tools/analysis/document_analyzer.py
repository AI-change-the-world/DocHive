"""
文档分析工具

功能：
1. 接收文档列表和用户查询
2. 内部智能决策如何阅读文档（批量 or 逐份）
3. 调用LLM进行分析
4. 返回分析结果
"""

import asyncio
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from utils.llm_client import get_llm_client


async def analyze_documents(
    query: str,
    documents: List[Dict[str, Any]],
    db: AsyncSession,
    max_context_length: int = 10000,
) -> Dict[str, Any]:
    """
    智能分析文档

    内部逻辑：
    1. 调用LLM判断用户意图（批量总结 or 逐份分析）
    2. 检查内容长度是否超过限制
    3. 选择合适的阅读策略
    4. 执行分析并返回结果

    Args:
        query: 用户查询
        documents: 文档列表（包含 id, title, content_text）
        db: 数据库会话

    Returns:
        {
            "success": bool,
            "analysis": str,  # 分析结果
            "reading_mode": str,  # 使用的阅读模式（batch/individual/grouped）
            "reasoning": str  # 选择该模式的原因
        }
    """
    try:
        if not documents:
            return {
                "success": False,
                "error": "没有文档需要分析",
            }

        logger.info(f"📚 开始分析 {len(documents)} 篇文档...")

        # 步骤1: 让LLM判断用户意图
        reading_mode, reasoning = await _decide_reading_mode(query, documents, db, max_context_length)
        logger.info(f"🤖 LLM决策: {reading_mode} - {reasoning}")

        # 步骤2: 根据模式执行分析
        if reading_mode == "batch":
            analysis = await _analyze_batch(query, documents, db)
        elif reading_mode == "individual":
            analysis = await _analyze_individually(query, documents, db)
        elif reading_mode == "grouped":
            analysis = await _analyze_grouped(query, documents, db, max_context_length)
        else:
            # 降级：默认批量处理
            logger.warning(f"⚠️ 未知的阅读模式: {reading_mode}，降级为批量处理")
            analysis = await _analyze_batch(query, documents, db)

        return {
            "success": True,
            "analysis": analysis,
            "reading_mode": reading_mode,
            "reasoning": reasoning,
        }

    except Exception as e:
        logger.error(f"❌ 文档分析失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
        }


async def _decide_reading_mode(
    query: str, documents: List[Dict[str, Any]], db: AsyncSession, max_context_length: int
) -> tuple[str, str]:
    """
    内部函数：让LLM判断应该使用哪种阅读模式

    Returns:
        (reading_mode, reasoning)
        - reading_mode: "batch" | "individual" | "grouped"
        - reasoning: 选择原因
    """
    llm_client = get_llm_client()

    # 计算总长度
    total_length = sum(len(doc.get("content_text", "")) for doc in documents)

    # 构造决策提示词
    prompt = f"""你是一个文档阅读策略专家。请分析用户查询，决定如何阅读文档。

【用户查询】
{query}

【文档信息】
- 文档数量: {len(documents)}
- 总内容长度: {total_length} 字符
- 系统最大上下文长度: {max_context_length} 字符

【阅读模式】
1. **batch** (批量总结): 一次性把所有文档给LLM，适合总体概览、归纳总结
2. **individual** (逐份分析): for循环处理每份文档，适合详细分析、每份都要归纳
3. **grouped** (分组处理): 内容太长时分批处理，每批不超过上下文限制

【决策规则】
1. 如果用户说"总结"、"概览"、"都讲了什么" → batch
2. 如果用户说"每一份"、"逐个"、"分别归纳" → individual
3. 如果总长度 > 最大长度 → grouped（强制）
4. 如果总长度 > 最大长度的80% → 建议 grouped

请返回JSON:
{{
    "reading_mode": "batch" | "individual" | "grouped",
    "reasoning": "选择原因"
}}

只返回JSON，不要其他内容。
"""

    try:
        response = await llm_client.extract_json_response(prompt, db=db)
        reading_mode = response.get("reading_mode", "batch")
        reasoning = response.get("reasoning", "")

        # 强制检查：如果超长，必须分组
        if total_length > max_context_length and reading_mode != "grouped":
            logger.warning(
                f"⚠️ 内容超长（{total_length} > {max_context_length}），强制使用grouped模式")
            reading_mode = "grouped"
            reasoning = f"内容超过最大长度限制，强制分组处理。{reasoning}"

        return reading_mode, reasoning

    except Exception as e:
        logger.error(f"❌ 决策失败，降级为batch模式: {e}")
        return "batch", f"决策失败，降级为批量处理: {str(e)}"


async def _analyze_batch(
    query: str, documents: List[Dict[str, Any]], db: AsyncSession
) -> str:
    """
    批量总结：一次性把所有文档给LLM
    """
    logger.info(f"📖 批量总结模式：一次性分析 {len(documents)} 篇文档")

    llm_client = get_llm_client()

    # 构建文档内容
    doc_contents = []
    for idx, doc in enumerate(documents, 1):
        content = doc.get("content_text") or doc.get("ai_summary", "无内容")
        doc_contents.append(
            f"### 文档{idx}: {doc.get('title', '未命名')}\n"
            f"{content}\n"
        )

    prompt = f"""你是一个专业的文档分析助手。

【用户查询】
{query}

【所有文档内容】
{"".join(doc_contents)}

请基于所有文档内容，回答用户的问题。

要求：
- 准确、详细地回答
- 突出重点和关键信息
- 结构清晰，易于阅读
- 使用中文回答
"""

    analysis = await llm_client.chat_completion(prompt, db=db)
    return analysis


async def _analyze_individually(
    query: str, documents: List[Dict[str, Any]], db: AsyncSession
) -> str:
    """
    逐份分析：for循环处理每份文档
    """
    logger.info(f"📖 逐份分析模式：逐个分析 {len(documents)} 篇文档")

    llm_client = get_llm_client()

    individual_results = []

    for idx, doc in enumerate(documents, 1):
        logger.info(
            f"📄 正在分析第 {idx}/{len(documents)} 篇文档: {doc.get('title', '未命名')}")

        content = doc.get("content_text") or doc.get("ai_summary", "无内容")

        prompt = f"""你是一个专业的文档分析助手。

【用户查询】
{query}

【文档{idx}内容】
标题: {doc.get('title', '未命名')}

{content}

请详细分析这份文档，归纳其主要内容和要点。

要求：
- 详细、准确地分析
- 突出重点和关键信息
- 使用中文回答
"""

        # 添加异步延迟，避免结果混乱
        await asyncio.sleep(0.3)

        analysis = await llm_client.chat_completion(prompt, db=db)
        individual_results.append(
            f"## 文档{idx}: {doc.get('title', '未命名')}\n\n{analysis}\n"
        )

        logger.info(f"✅ 第 {idx}/{len(documents)} 篇分析完成")

    # 汇总所有结果
    final_summary = f"""共分析了 {len(documents)} 篇文档，以下是每份文档的详细分析：

{"".join(individual_results)}
"""

    return final_summary


async def _analyze_grouped(
    query: str, documents: List[Dict[str, Any]], db: AsyncSession, max_context_length: int
) -> str:
    """
    分组处理：内容太长时分批处理
    """
    logger.info(f"📖 分组处理模式：分批分析 {len(documents)} 篇文档")

    max_length = int(max_context_length * 0.8)  # 预留20%空间

    llm_client = get_llm_client()

    # 分组策略：按内容长度分组
    groups = []
    current_group = []
    current_length = 0

    for doc in documents:
        content = doc.get("content_text") or doc.get("ai_summary", "")
        doc_length = len(content)

        if current_length + doc_length > max_length and current_group:
            # 当前组已满，开始新组
            groups.append(current_group)
            current_group = [doc]
            current_length = doc_length
        else:
            current_group.append(doc)
            current_length += doc_length

    if current_group:
        groups.append(current_group)

    logger.info(f"📦 分为 {len(groups)} 组处理")

    group_results = []

    for group_idx, group in enumerate(groups, 1):
        logger.info(f"📦 正在处理第 {group_idx}/{len(groups)} 组（{len(group)} 篇文档）")

        # 构建该组的文档内容
        doc_contents = []
        for idx, doc in enumerate(group, 1):
            content = doc.get("content_text") or doc.get("ai_summary", "无内容")
            doc_contents.append(
                f"### 文档{idx}: {doc.get('title', '未命名')}\n"
                f"{content}\n"
            )

        prompt = f"""你是一个专业的文档分析助手。

【用户查询】
{query}

【本组文档内容】（第{group_idx}/{len(groups)}组）
{"".join(doc_contents)}

请分析这组文档，归纳主要内容。

要求：
- 准确、详细地分析
- 突出重点和关键信息
- 使用中文回答
"""

        # 添加异步延迟
        await asyncio.sleep(0.3)

        analysis = await llm_client.chat_completion(prompt, db=db)
        group_results.append(
            f"## 第{group_idx}组分析结果\n\n{analysis}\n"
        )

        logger.info(f"✅ 第 {group_idx}/{len(groups)} 组处理完成")

    # 最终汇总
    final_prompt = f"""你是一个专业的文档分析助手。

【用户查询】
{query}

【分组分析结果】
我已经将 {len(documents)} 篇文档分成 {len(groups)} 组进行了分析，以下是每组的分析结果：

{"".join(group_results)}

请基于这些分组分析结果，给出最终的综合回答。

要求：
- 整合所有分组的信息
- 给出完整、连贯的回答
- 突出重点和关键信息
- 使用中文回答
"""

    await asyncio.sleep(0.3)
    final_analysis = await llm_client.chat_completion(final_prompt, db=db)

    return final_analysis
