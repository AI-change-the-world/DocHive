import json
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from utils.llm_client import get_llm_client


class CustomAgentExecutor:
    """
    自定义Agent执行器

    核心功能：根据已保存的Agent定义，按步骤执行工具和智能体
    """

    @staticmethod
    async def execute(
        agent,  # CustomAgent数据库模型实例
        query: str,
        template_id: int,
        session_id: Optional[str],
        db: AsyncSession,
        es_client,
        es_index: str = "dochive_documents",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行自定义Agent

        Args:
            agent: CustomAgent数据库模型实例
            query: 用户查询
            template_id: 模板ID
            session_id: 会话ID
            db: 数据库会话
            es_client: ES客户端
            es_index: ES索引

        Yields:
            执行过程的事件流（SSE格式）
        """
        logger.info(f"🚀 开始执行自定义Agent: {agent.name}")

        # 1. 发送执行计划事件
        steps = agent.steps if isinstance(agent.steps, list) else []

        yield {
            "event": "execution_plan",
            "data": {
                "agent_name": agent.name,
                "description": agent.description,
                "execution_pattern": agent.execution_pattern,
                "plan": [
                    {
                        "step": s.get("step"),
                        "type": s.get("type"),
                        "name": s.get("name"),
                        "description": s.get("description"),
                    }
                    for s in steps
                ],
            },
        }

        # 2. 中间数据存储
        intermediate_data = {
            "documents": [],
            "document_ids": [],
            "tool_results": [],
            "agent_results": [],
        }

        # 3. 逐步执行
        from core.tools.base import ToolContext, execute_tool
        from core.agents.retrieval_agent_v2 import retrieve_documents_v2
        from core.agents.qa_agent_v2 import generate_answer_v2

        for i, step in enumerate(steps):
            step_num = step.get("step", i + 1)
            step_type = step.get("type")
            step_name = step.get("name")
            step_desc = step.get("description", "")

            logger.info(f"🔧 执行步骤{step_num}: {step_type}/{step_name}")

            # 发送步骤开始事件
            yield {
                "event": "stage_start",
                "data": {
                    "stage": f"step_{step_num}",
                    "message": f"正在执行: {step_desc}",
                },
            }

            try:
                result = None

                if step_type == "tool":
                    # 执行工具
                    tool_ctx = ToolContext(
                        db=db,
                        es_client=es_client,
                        es_index=es_index,
                        template_id=template_id,
                        session_id=session_id,
                    )

                    # 准备工具参数
                    arguments = {"template_id": template_id}

                    # 特殊参数处理
                    if step_name in [
                        "get_document_contents",
                        "skim_documents",
                        "read_documents",
                    ]:
                        arguments["document_ids"] = intermediate_data.get(
                            "document_ids", []
                        )
                    elif step_name == "analyze_documents":
                        arguments["query"] = query
                        arguments["documents"] = intermediate_data.get(
                            "documents", [])
                    elif step_name == "search_documents_by_classification":
                        arguments["class_code"] = None

                    # 执行工具
                    result = await execute_tool(step_name, arguments, tool_ctx)
                    intermediate_data["tool_results"].append(result)

                    # 更新中间数据
                    if result.get("success"):
                        if step_name == "search_documents_by_classification":
                            intermediate_data["document_ids"] = result.get(
                                "document_ids", []
                            )
                        elif step_name in [
                            "get_document_contents",
                            "skim_documents",
                            "read_documents",
                        ]:
                            intermediate_data["documents"] = result.get(
                                "documents", [])

                elif step_type == "agent":
                    # 执行智能体
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
                        if result.get("success"):
                            intermediate_data["documents"] = result.get(
                                "documents", [])

                    elif step_name == "qa_agent":
                        documents = intermediate_data.get("documents", [])
                        result = await generate_answer_v2(
                            query=query,
                            documents=documents,
                            db=db,
                            max_context_length=10000,
                        )

                    else:
                        result = {
                            "success": False,
                            "error": f"未知的智能体: {step_name}",
                        }

                    intermediate_data["agent_results"].append(result)

                else:
                    result = {
                        "success": False,
                        "error": f"未知的步骤类型: {step_type}",
                    }

                # 发送步骤完成事件
                yield {
                    "event": "stage_complete",
                    "data": {
                        "stage": f"step_{step_num}",
                        "message": f"步骤{step_num}完成",
                        "result": result,
                    },
                }

                logger.info(f"✅ 步骤{step_num}完成: {step_name}")

            except Exception as e:
                logger.error(f"❌ 步骤{step_num}失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

                yield {
                    "event": "stage_error",
                    "data": {
                        "stage": f"step_{step_num}",
                        "error": str(e),
                    },
                }

        # 4. 生成最终答案
        logger.info("📝 生成最终答案")

        final_answer = None
        documents = intermediate_data.get("documents", [])

        # 如果有qa_agent结果，使用其答案
        for agent_result in intermediate_data.get("agent_results", []):
            if agent_result.get("success") and agent_result.get("answer"):
                final_answer = agent_result.get("answer")
                break

        # 如果没有答案但有文档，用LLM生成答案
        if not final_answer and documents:
            try:
                llm_client = get_llm_client()

                # 构建文档上下文
                doc_context = "\n\n".join([
                    f"【文档{i+1}】{doc.get('title', '未命名')}\n{doc.get('content', '')[:500]}"
                    for i, doc in enumerate(documents[:5])
                ])

                system_prompt = "你是一个专业的问答助手。请基于提供的文档内容回答用户的问题。"
                user_prompt = f"""基于以下文档回答问题。

【文档内容】
{doc_context}

【用户问题】
{query}

请给出详细的回答。
"""

                final_answer = await llm_client.chat_completion(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    db=db,
                )
            except Exception as e:
                logger.error(f"❌ 生成答案失败: {e}")
                final_answer = "抱歉，生成答案时出现错误。"

        # 5. 发送最终答案
        yield {
            "event": "answer",
            "data": {
                "answer": final_answer or "执行完成",
                "documents": documents,
            },
        }

        # 6. 发送完成事件
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
            },
        }

        logger.info(f"✅ 自定义Agent执行完成: {agent.name}")
