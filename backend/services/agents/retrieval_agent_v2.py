"""
检索智能体 V2 - 使用 @agent 装饰器和 BaseAgent 基类

混合检索（ES + SQL）+ 质量评估
"""

from typing import Any, Dict, List
from loguru import logger

from services.agents.base import agent, BaseAgent, AgentContext, AgentResult
from services.tools.base import execute_tool


@agent(
    name="retrieval_agent",
    description="检索智能体 - 负责从文档库中检索相关文档",
    capabilities=[
        "分析用户查询意图",
        "自动选择最优检索策略（ES全文检索/SQL结构化检索/混合检索）",
        "执行检索工具组合",
        "对检索结果进行去重和后处理",
    ],
    input_schema={
        "query": "用户查询文本（可选，默认使用上下文中的query）",
        "top_k": "返回文档数量（默认20）",
        "enable_deduplication": "是否去重（默认True）",
    },
    output_schema={
        "documents": "文档列表，包含id、title、content、ai_summary、score",
        "total_count": "文档数量",
    },
    scenarios=[
        "需要获取文档列表",
        "需要基于语义或结构化条件查找文档",
        "作为问答的前置步骤",
    ]
)
class RetrievalAgentV2(BaseAgent):
    """检索智能体 V2"""

    async def execute(
        self,
        query: str = None,
        top_k: int = 20,
        enable_deduplication: bool = True,
        **kwargs,
    ) -> AgentResult:
        """
        执行检索

        Args:
            query: 用户查询（默认使用上下文中的query）
            top_k: 返回文档数量
            enable_deduplication: 是否去重

        Returns:
            AgentResult
        """
        # 使用传入的query或上下文中的query
        search_query = query or self.ctx.query

        if not search_query:
            return AgentResult(
                success=False,
                error="缺少查询参数",
                data={},
                documents=[],
            )

        template_id = self.ctx.template_id
        tool_ctx = self.ctx.to_tool_context()

        self.logger.info(f"🔍 开始检索: query='{search_query}', template_id={template_id}")

        # Step 1: 查询优化
        optimized_query = await self._optimize_query(search_query)

        # Step 2: ES全文检索
        es_result = await execute_tool(
            "es_fulltext_search",
            {
                "query": search_query,
                "template_id": template_id,
                "top_k": top_k * 2,
                "optimized_query": optimized_query,
            },
            tool_ctx,
        )

        es_doc_ids = es_result.get("document_ids", []) if es_result.get("success") else []
        es_documents = es_result.get("documents", []) if es_result.get("success") else []

        self.logger.info(f"✅ ES检索完成: {len(es_doc_ids)} 篇文档")

        # Step 3: SQL结构化检索
        sql_result = await execute_tool(
            "sql_structured_search",
            {
                "template_id": template_id,
                "top_k": top_k * 2,
            },
            tool_ctx,
        )

        sql_doc_ids = sql_result.get("document_ids", []) if sql_result.get("success") else []

        self.logger.info(f"✅ SQL检索完成: {len(sql_doc_ids)} 篇文档")

        # Step 4: 合并结果
        final_doc_ids = self._merge_results(es_doc_ids, sql_doc_ids)

        self.logger.info(f"✅ 合并结果: {len(final_doc_ids)} 篇文档")

        # Step 5: 获取文档内容
        if final_doc_ids:
            read_result = await execute_tool(
                "read_documents",
                {
                    "document_ids": final_doc_ids[:top_k],
                    "max_documents": top_k,
                },
                tool_ctx,
            )

            documents = read_result.get("documents", []) if read_result.get("success") else []

            # 合并 score 信息
            score_map = {d["document_id"]: d.get("score", 0) for d in es_documents}
            for doc in documents:
                doc_id = doc.get("id")
                if doc_id in score_map:
                    doc["score"] = score_map[doc_id]
                else:
                    doc["score"] = 0.0

            # 按 score 排序
            documents.sort(key=lambda x: x.get("score", 0), reverse=True)

            # 去重
            if enable_deduplication:
                documents = self._deduplicate(documents)

        else:
            documents = []

        self.logger.info(f"✅ 检索完成: 返回 {len(documents)} 篇文档")

        return AgentResult(
            success=True,
            data={
                "total_count": len(documents),
                "optimized_query": optimized_query,
            },
            documents=documents,
        )

    async def _optimize_query(self, query: str) -> Dict[str, Any]:
        """查询优化 - 提取关键词"""
        from utils.llm_client import get_llm_client

        prompt = f"""分析以下查询，提取关键词：

【用户查询】
{query}

【输出格式】
返回JSON：
{{
    "primary_keywords": ["核心关键词"],
    "context_keywords": ["上下文扩展词"],
    "related_keywords": ["相关词"]
}}
"""

        try:
            llm_client = get_llm_client()
            response = await llm_client.extract_json_response(prompt, db=self.ctx.db)

            return {
                "original_query": query,
                "primary_keywords": response.get("primary_keywords", []),
                "context_keywords": response.get("context_keywords", []),
                "related_keywords": response.get("related_keywords", []),
            }

        except Exception as e:
            self.logger.warning(f"查询优化失败: {e}")
            return {"original_query": query}

    def _merge_results(
        self,
        es_ids: List[int],
        sql_ids: List[int],
    ) -> List[int]:
        """合并ES和SQL结果"""
        es_set = set(es_ids)
        sql_set = set(sql_ids)

        # 尝试求交集
        intersection = es_set & sql_set

        if intersection:
            # 保持ES的顺序
            return [doc_id for doc_id in es_ids if doc_id in intersection]
        else:
            # 交集为空，使用ES结果
            return es_ids

    def _deduplicate(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """去重"""
        seen_ids = set()
        result = []

        for doc in documents:
            doc_id = doc.get("id")
            if doc_id not in seen_ids:
                seen_ids.add(doc_id)
                result.append(doc)

        return result


# ==================== 便捷调用接口 ====================


async def retrieve_documents_v2(
    query: str,
    template_id: int,
    session_id: str,
    db,
    es_client,
    es_index: str = "dochive_documents",
    top_k: int = 20,
    enable_deduplication: bool = True,
) -> Dict[str, Any]:
    """
    检索文档 V2 - 便捷调用接口

    保持与旧版本兼容的接口
    """
    ctx = AgentContext(
        db=db,
        es_client=es_client,
        es_index=es_index,
        template_id=template_id,
        session_id=session_id,
        query=query,
    )

    agent_instance = RetrievalAgentV2(ctx)
    result = await agent_instance.run(
        query=query,
        top_k=top_k,
        enable_deduplication=enable_deduplication,
    )

    # 转换为旧版格式
    return {
        "success": result.get("success", False),
        "documents": result.get("documents", []),
        "total_count": result.get("data", {}).get("total_count", 0),
        "error": result.get("error"),
    }
