import json
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database_models import Document
from utils.llm_client import LLMClient
from utils.search_engine import SearchEngine


class QAService:
    """问答服务层"""

    @staticmethod
    async def _retrieve_documents(
        db: AsyncSession,
        search_engine: SearchEngine,
        question: str,
        template_id: Optional[int] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        基于问题检索相关文档

        Args:
            db: 数据库会话
            search_engine: 搜索引擎实例
            question: 用户问题
            template_id: 限定模板ID范围
            top_k: 返回文档数量

        Returns:
            相关文档列表
        """
        # 使用搜索引擎进行检索
        search_results = await search_engine.search_documents(
            keyword=question,
            template_id=template_id,
            page=1,
            page_size=top_k,
        )

        # 获取文档详细信息
        document_ids = [r["document_id"] for r in search_results["results"]]

        if not document_ids:
            return []

        result = await db.execute(select(Document).where(Document.id.in_(document_ids)))
        documents = result.scalars().all()

        # 组装文档信息
        retrieved_docs = []
        for doc in documents:
            # 提取文档片段（这里简化处理，实际可以根据相关性提取更精准的片段）
            snippet = ""
            if doc.summary:
                snippet = doc.summary[:300]  # 取摘要的前300字符
            elif doc.content_text:
                snippet = doc.content_text[:300]  # 取内容的前300字符
            else:
                snippet = f"文档: {doc.title}"

            retrieved_docs.append(
                {
                    "document_id": doc.id,
                    "title": doc.title,
                    "snippet": snippet,
                    "content": doc.content_text or "",
                    "score": 0.8,  # 简化处理，实际应从搜索引擎获取
                }
            )

        return retrieved_docs

    @staticmethod
    def _build_qa_prompt(question: str, context_docs: List[Dict[str, Any]]) -> str:
        """
        构建问答Prompt

        Args:
            question: 用户问题
            context_docs: 上下文文档列表

        Returns:
            构建的Prompt
        """
        context_text = "\n\n".join(
            [
                # 每个文档最多1000字符
                f"【文档{i+1}: {doc['title']}】\n{doc['content'][:1000]}"
                for i, doc in enumerate(context_docs)
            ]
        )

        prompt = f"""你是一个智能文档问答助手。请基于以下文档内容回答用户的问题。

要求：
1. 仔细阅读提供的文档内容
2. 基于文档内容给出准确、详细的答案
3. 如果文档中没有相关信息，请明确告知用户
4. 回答要有条理，使用markdown格式
5. 如果引用了具体文档内容，请标注来源

===== 相关文档 =====
{context_text}

===== 用户问题 =====
{question}

请给出你的回答："""

        return prompt

    @staticmethod
    async def answer_question_stream(
        db: AsyncSession,
        llm_client: LLMClient,
        search_engine: SearchEngine,
        question: str,
        template_id: Optional[int] = None,
        top_k: int = 5,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式问答

        Args:
            db: 数据库会话
            llm_client: LLM客户端
            search_engine: 搜索引擎
            question: 用户问题
            template_id: 限定模板ID范围
            top_k: 检索文档数量

        Yields:
            SSE事件数据
        """
        try:
            # 1. 发送思考状态
            yield {
                "event": "thinking",
                "data": {"stage": "retrieving", "message": "正在检索相关文档..."},
                "done": False,
            }

            # 2. 检索相关文档
            retrieved_docs = await QAService._retrieve_documents(
                db, search_engine, question, template_id, top_k
            )

            if not retrieved_docs:
                yield {
                    "event": "error",
                    "data": {"message": "未找到相关文档，无法回答问题。"},
                    "done": True,
                }
                return

            # 3. 发送检索到的文档引用
            references = [
                {
                    "document_id": doc["document_id"],
                    "title": doc["title"],
                    "snippet": doc["snippet"],
                    "score": doc["score"],
                }
                for doc in retrieved_docs
            ]

            yield {
                "event": "references",
                "data": {"references": references},
                "done": False,
            }

            # 4. 发送思考状态
            yield {
                "event": "thinking",
                "data": {
                    "stage": "analyzing",
                    "message": "正在分析文档内容并生成答案...",
                },
                "done": False,
            }

            # 5. 构建Prompt并调用LLM
            prompt = QAService._build_qa_prompt(question, retrieved_docs)

            # 6. 流式生成答案
            stream = llm_client.client.chat.completions.create(
                model=llm_client.default_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield {
                        "event": "answer",
                        "data": {"content": chunk.choices[0].delta.content},
                        "done": False,
                    }

            # 7. 发送完成信号
            yield {"event": "complete", "data": {"message": "回答完成"}, "done": True}

        except Exception as e:
            # 发送错误信息
            yield {
                "event": "error",
                "data": {"message": f"问答过程出错: {str(e)}"},
                "done": True,
            }

    @staticmethod
    async def answer_question(
        db: AsyncSession,
        llm_client: LLMClient,
        search_engine: SearchEngine,
        question: str,
        template_id: Optional[int] = None,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        非流式问答（用于简单场景）

        Args:
            db: 数据库会话
            llm_client: LLM客户端
            search_engine: 搜索引擎
            question: 用户问题
            template_id: 限定模板ID范围
            top_k: 检索文档数量

        Returns:
            问答结果
        """
        # 检索相关文档
        retrieved_docs = await QAService._retrieve_documents(
            db, search_engine, question, template_id, top_k
        )

        if not retrieved_docs:
            return {
                "question": question,
                "answer": "未找到相关文档，无法回答问题。",
                "references": [],
                "thinking_process": None,
            }

        # 构建Prompt并调用LLM
        prompt = QAService._build_qa_prompt(question, retrieved_docs)
        answer = await llm_client.chat_completion(prompt, temperature=0.7)

        # 组装引用信息
        references = [
            {
                "document_id": doc["document_id"],
                "title": doc["title"],
                "snippet": doc["snippet"],
                "score": doc["score"],
            }
            for doc in retrieved_docs
        ]

        return {
            "question": question,
            "answer": answer,
            "references": references,
            "thinking_process": f"检索到 {len(retrieved_docs)} 个相关文档",
        }
