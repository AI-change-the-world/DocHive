"""
问答智能体 V2 - 使用 @agent 装饰器和 BaseAgent 基类

基于检索结果生成答案
"""

from typing import Any, Dict, List
from loguru import logger

from services.agents.base import agent, BaseAgent, AgentContext, AgentResult


@agent(
    name="qa_agent",
    description="问答智能体 - 基于给定文档生成答案",
    capabilities=[
        "筛选与查询最相关的文档",
        "理解文档内容",
        "生成准确、简洁的自然语言答案",
    ],
    input_schema={
        "query": "用户问题（可选，默认使用上下文中的query）",
        "documents": "文档列表（通常来自检索智能体）",
        "max_context_length": "最大上下文长度（默认10000）",
    },
    output_schema={
        "answer": "生成的答案",
        "filtered_documents": "使用的文档列表",
    },
    scenarios=[
        "需要理解文档内容并生成答案",
        "已有文档列表，需要基于文档回答问题",
        "需要总结、分析、解释文档内容",
    ]
)
class QAAgentV2(BaseAgent):
    """问答智能体 V2"""

    async def execute(
        self,
        query: str = None,
        documents: List[Dict[str, Any]] = None,
        max_context_length: int = 10000,
        **kwargs,
    ) -> AgentResult:
        """
        执行问答

        Args:
            query: 用户问题（默认使用上下文中的query）
            documents: 文档列表
            max_context_length: 最大上下文长度

        Returns:
            AgentResult
        """
        # 使用传入的query或上下文中的query
        question = query or self.ctx.query

        if not question:
            return AgentResult(
                success=False,
                error="缺少问题参数",
                data={},
            )

        if not documents:
            return AgentResult(
                success=True,
                data={"filtered_count": 0},
                answer="抱歉，没有找到相关文档来回答您的问题。",
            )

        self.logger.info(f"💭 开始问答: query='{question}', documents={len(documents)}")

        # Step 1: 筛选相关文档
        filtered_documents = await self._filter_documents(question, documents)

        self.logger.info(f"✅ 文档筛选完成: {len(documents)} -> {len(filtered_documents)}")

        # Step 2: 生成答案
        answer = await self._generate_answer(question, filtered_documents, max_context_length)

        self.logger.info(f"✅ 答案生成完成，长度: {len(answer)} 字符")

        return AgentResult(
            success=True,
            data={
                "filtered_count": len(filtered_documents),
            },
            documents=filtered_documents,
            answer=answer,
        )

    async def _filter_documents(
        self,
        query: str,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """筛选相关文档"""
        from utils.llm_client import get_llm_client

        if len(documents) <= 3:
            return documents

        # 构造摘要列表
        summaries = []
        for i, doc in enumerate(documents):
            title = doc.get("title", "未知标题")
            summary = doc.get("ai_summary") or doc.get("content", "")[:200]
            summaries.append(f"{i}. {title}: {summary}")

        summaries_text = "\n".join(summaries)

        prompt = f"""判断以下文档与问题的相关性：

【用户问题】
{query}

【文档列表】
{summaries_text}

【输出格式】
返回JSON：
{{
    "relevant_indices": [相关文档的索引列表]
}}
"""

        try:
            llm_client = get_llm_client()
            response = await llm_client.extract_json_response(
                messages=[
                    {"role": "system", "content": "你是一个文档相关性判断助手"},
                    {"role": "user", "content": prompt},
                ],
                db=self.ctx.db,
            )

            relevant_indices = response.get("relevant_indices", [])

            filtered = [
                documents[idx] for idx in relevant_indices
                if 0 <= idx < len(documents)
            ]

            return filtered if filtered else documents[:3]

        except Exception as e:
            self.logger.warning(f"文档筛选失败: {e}")
            return documents[:5]

    async def _generate_answer(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        max_context_length: int,
    ) -> str:
        """生成答案"""
        from utils.llm_client import get_llm_client

        if not documents:
            return "抱歉，我没有找到相关的文档来回答您的问题。"

        # 构建上下文
        context_parts = []
        current_length = 0

        for i, doc in enumerate(documents):
            title = doc.get("title", "未知文档")
            content = doc.get("content", "")

            doc_text = f"【文档{i+1}: {title}】\n{content}\n\n"
            doc_length = len(doc_text)

            if current_length + doc_length > max_context_length:
                remaining = max_context_length - current_length
                if remaining > 100:
                    doc_text = doc_text[:remaining] + "...\n\n"
                    context_parts.append(doc_text)
                break

            context_parts.append(doc_text)
            current_length += doc_length

        context = "".join(context_parts)

        prompt = f"""基于以下文档回答问题：

【用户问题】
{query}

【相关文档】
{context}

【要求】
1. 直接、准确地回答问题
2. 答案必须基于文档内容
3. 如果文档中没有相关信息，明确说明
4. 使用中文回答
"""

        try:
            llm_client = get_llm_client()
            answer = await llm_client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是一个专业的问答助手"},
                    {"role": "user", "content": prompt},
                ],
                db=self.ctx.db,
            )

            return answer.strip()

        except Exception as e:
            self.logger.error(f"答案生成失败: {e}")
            return f"抱歉，生成答案时出现错误: {str(e)}"


# ==================== 便捷调用接口 ====================


async def generate_answer_v2(
    query: str,
    documents: List[Dict[str, Any]],
    db,
    max_context_length: int = 10000,
) -> Dict[str, Any]:
    """
    生成答案 V2 - 便捷调用接口

    保持与旧版本兼容的接口
    """
    ctx = AgentContext(
        db=db,
        query=query,
    )

    agent_instance = QAAgentV2(ctx)
    result = await agent_instance.run(
        query=query,
        documents=documents,
        max_context_length=max_context_length,
    )

    # 转换为旧版格式
    return {
        "success": result.get("success", False),
        "answer": result.get("answer", ""),
        "filtered_documents": result.get("documents", []),
        "filtered_count": result.get("data", {}).get("filtered_count", 0),
        "error": result.get("error"),
    }
