import asyncio
import json
import traceback
import uuid
from typing import Any, Dict, Optional

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from api.deps import get_config, get_current_user, get_llm, get_search_engine
from config import DynamicConfig
from database import get_db
from models.database_models import User
from schemas.api_schemas import QARequest, QAResponse, ResponseBase, SSEEvent
from services.qa_service import QAService

# 导入search_agent相关模块
from services.search_agent import RetrievalState
from services.search_agent import app as search_agent_app
from services.search_agent import graph_state_storage
from utils.llm_client import LLMClient
from utils.search_engine import SearchEngine

router = APIRouter(prefix="/qa", tags=["智能问答"])


@router.post("/ask/stream")
async def ask_question_stream(
    qa_request: QARequest,
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
    search_engine: SearchEngine = Depends(get_search_engine),
    current_user: User = Depends(get_current_user),
):
    """
    流式问答接口（SSE）

    - **question**: 用户问题
    - **template_id**: 限定模板ID范围（可选）
    - **top_k**: 检索文档数量（默认5，范围1-20）

    返回流式事件：
    - **thinking**: 思考过程状态更新
    - **references**: 检索到的相关文档引用
    - **answer**: 流式生成的答案片段
    - **complete**: 回答完成标记
    - **error**: 错误信息
    """

    async def event_generator():
        """SSE事件生成器"""
        try:
            async for event in QAService.answer_question_stream(
                db,
                llm,
                search_engine,
                question=qa_request.question,
                template_id=qa_request.template_id,
                top_k=qa_request.top_k,
            ):
                # 将事件转换为SSE格式
                yield {
                    "event": event.get("event", "message"),
                    "data": json.dumps(event, ensure_ascii=False),
                }

        except Exception as e:
            # 发送错误事件
            yield {
                "data": json.dumps(
                    {
                        "event": "error",
                        "data": {"message": f"问答失败: {str(e)}"},
                        "done": True,
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/ask", response_model=ResponseBase)
async def ask_question(
    qa_request: QARequest,
    db: AsyncSession = Depends(get_db),
    llm: LLMClient = Depends(get_llm),
    search_engine: SearchEngine = Depends(get_search_engine),
    current_user: User = Depends(get_current_user),
):
    """
    非流式问答接口

    - **question**: 用户问题
    - **template_id**: 限定模板ID范围（可选）
    - **top_k**: 检索文档数量（默认5，范围1-20）

    返回完整的问答结果，包括答案和相关文档引用
    """
    try:
        result = await QAService.answer_question(
            db,
            llm,
            search_engine,
            question=qa_request.question,
            template_id=qa_request.template_id,
            top_k=qa_request.top_k,
        )

        return ResponseBase(
            message="问答成功",
            data=result,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"问答失败: {str(e)}",
        )


@router.post("/ask/agent/stream")
async def ask_question_agent_stream(
    request: Request,
    qa_request: QARequest,
    db: AsyncSession = Depends(get_db),
    config: DynamicConfig = Depends(get_config),
    current_user: User = Depends(get_current_user),
):
    """
    基于LangGraph智能体的流式问答接口（SSE）

    - **question**: 用户问题
    - **template_id**: 限定模板ID范围（必需）
    - **top_k**: 检索文档数量（默认5，范围1-20）

    返回流式事件：
    - **thinking**: 思考过程状态更新
    - **references**: 检索到的相关文档引用
    - **answer**: 流式生成的答案片段
    - **complete**: 回答完成标记
    - **error**: 错误信息
    - **ambiguity**: 需要用户澄清的问题
    """

    # 检查template_id是否提供
    if not qa_request.template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用智能体问答必须提供template_id",
        )

    async def event_generator():
        """SSE事件生成器"""
        es_client = None  # 初始化
        # 生成会话/任务ID（整个流程使用同一个UUID）
        task_id = str(uuid.uuid4())
        try:
            # 生成会话ID
            session_id = str(uuid.uuid4())

            # 初始化Elasticsearch客户端
            es_client = AsyncElasticsearch(
                [config.ELASTICSEARCH_URL], verify_certs=False
            )
            # 构造初始状态 (优化后的状态机)
            initial_state: RetrievalState = {
                # 必需输入
                "query": qa_request.question,
                "template_id": qa_request.template_id or 0,
                "session_id": session_id,
                # 节点 0 (任务规划) 产出
                "execution_plan": [],
                "reasoning": "",
                "tool_results": [],
                "need_retrieval": True,
                # 节点 1 (ES全文检索) 产出
                "es_fulltext_results": [],
                "es_document_ids": set(),
                # 节点 2 (SQL结构化检索) 产出
                "class_template_levels": None,
                "category": "*",
                "category_field_code": None,
                "sql_extracted_conditions": [],
                "sql_document_ids": set(),
                # 节点 3 (结果融合) 产出
                "merged_document_ids": [],
                "merged_documents": [],
                "fusion_strategy": "none",
                # 节点 4 (精细化筛选) 产出
                "document_type_fields": [],
                "refined_conditions": {},
                "final_es_query": None,
                "final_results": [],
                # 节点 5 (歧义处理) 产出
                "ambiguity_message": None,
                # 节点 6 (生成答案) 产出
                "answer": None,
            }

            logger.info(f"[LangGraph initial_state] {initial_state}")

            # 发送开始处理消息
            yield SSEEvent(
                event="thinking",
                data={
                    "stage": "start",
                    "message": "开始处理您的问题...",
                },
                id=task_id,
                done=False,
            ).model_dump_json()

            # 先执行意图识别，获取执行计划
            first_step = True
            execution_plan = []

            # 使用astream方式异步流式处理LangGraph（修复：异步节点必须用异步stream）
            state_data = None  # 初始化，用于保存最终状态
            async for step_result in search_agent_app.astream(
                initial_state,
                config={
                    "configurable": {
                        "db": db,
                        "es": es_client,
                        "es_index": config.ELASTICSEARCH_INDEX,
                        "rag_max_length": config.RAG_MAX_CONTEXT_LENGTH,
                    }
                },
            ):
                logger.info(
                    f"[LangGraph step_result.keys()] {step_result.keys()}")
                # 获取节点名称和状态数据
                node_name = list(step_result.keys())[0]
                state_data = step_result[node_name]

                print(f"[LangGraph Node] {node_name}")

                # 第一个节点是 intent_routing，根据执行计划生成前端渲染步骤
                if first_step and node_name == "intent_routing":
                    first_step = False

                    # 获取 LLM 规划的执行计划
                    llm_execution_plan = state_data.get("execution_plan", [])
                    reasoning = state_data.get("reasoning", "")

                    logger.info(f"📋 LLM执行计划: {llm_execution_plan}")
                    logger.info(f"💭 推理过程: {reasoning}")

                    # 根据执行计划动态生成前端渲染步骤
                    frontend_plan = []

                    # 总是先添加任务规划步骤
                    frontend_plan.append(
                        {"stage": "intent_routing", "name": "任务规划", "icon": "🧠"}
                    )

                    # 遍历 LLM 的执行计划，转换为前端步骤
                    for step in llm_execution_plan:
                        action = step.get("action")
                        description = step.get("description", "")

                        if action == "tool_call":
                            # 工具调用步骤（合并所有工具调用为一个步骤）
                            if not any(
                                s["stage"] == "tool_answer" for s in frontend_plan
                            ):
                                frontend_plan.append(
                                    {
                                        "stage": "tool_answer",
                                        "name": "工具执行",
                                        "icon": "🔧",
                                    }
                                )
                        elif action == "document_retrieval":
                            # 文档检索步骤（包含完整的检索流程）
                            frontend_plan.extend(
                                [
                                    {
                                        "stage": "es_fulltext",
                                        "name": "ES全文检索",
                                        "icon": "🔍",
                                    },
                                    {
                                        "stage": "sql_structured",
                                        "name": "SQL结构化检索",
                                        "icon": "📊",
                                    },
                                    {
                                        "stage": "merge_results",
                                        "name": "结果融合",
                                        "icon": "🔀",
                                    },
                                    {
                                        "stage": "refined_filter",
                                        "name": "精细化筛选",
                                        "icon": "✨",
                                    },
                                ]
                            )

                    # 总是最后添加答案生成步骤
                    frontend_plan.append(
                        {"stage": "generate_answer", "name": "生成答案", "icon": "📝"}
                    )

                    # 判断模式
                    has_tool = any(
                        step.get("action") == "tool_call" for step in llm_execution_plan
                    )
                    has_retrieval = any(
                        step.get("action") == "document_retrieval"
                        for step in llm_execution_plan
                    )

                    if has_tool and has_retrieval:
                        mode = "combined_query"
                    elif has_tool:
                        mode = "tool_calling"
                    else:
                        mode = "document_retrieval"

                    logger.info(f"🎯 前端渲染计划: {len(frontend_plan)} 个步骤")
                    logger.info(f"📌 执行模式: {mode}")

                    # 发送执行计划事件
                    yield SSEEvent(
                        event="execution_plan",
                        data={
                            "plan": frontend_plan,
                            "mode": mode,
                            "reasoning": reasoning,  # 传递 LLM 的推理过程
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                # 根据节点发送相应事件
                if node_name == "intent_routing":
                    # 任务规划节点
                    execution_plan = state_data.get("execution_plan", [])
                    reasoning = state_data.get("reasoning", "")
                    tool_count = len(
                        [s for s in execution_plan if s.get(
                            "action") == "tool_call"]
                    )
                    has_retrieval = any(
                        s.get("action") == "document_retrieval" for s in execution_plan
                    )

                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "intent_routing",
                            "message": f"任务规划完成: {tool_count}个工具调用 + {'文档检索' if has_retrieval else '无需检索'}",
                            "result": {
                                "execution_plan": execution_plan,
                                "reasoning": reasoning,
                                "tool_count": tool_count,
                                "has_retrieval": has_retrieval,
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "tool_answer":
                    # 工具调用答案生成节点
                    tool_results = state_data.get("tool_results", [])
                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "tool_answer",
                            "message": "工具调用完成",
                            "result": {
                                "tools_count": len(tool_results),
                                "results": tool_results,
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "enhance_query":
                    # 检索增强节点
                    parsed_fields = state_data.get("parsed_fields", {})
                    rewritten_query = state_data.get("rewritten_query", "")

                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "enhance_query",
                            "message": f"检索增强完成: 提取 {len(parsed_fields)} 个字段",
                            "result": {
                                "parsed_fields": parsed_fields,
                                "rewritten_query": rewritten_query,
                                "fields_count": len(parsed_fields),
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "es_fulltext":
                    # 先发送stage_start事件
                    yield SSEEvent(
                        event="stage_start",
                        data={
                            "stage": "es_fulltext",
                            "message": "正在进行ES全文检索...",
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    # 再发送stage_complete事件
                    es_doc_ids = list(state_data.get("es_document_ids", set()))
                    es_results = state_data.get("es_fulltext_results", [])[:10]
                    doc_summaries = [
                        {
                            "document_id": doc.get("document_id"),
                            "title": doc.get("title", ""),
                            "snippet": (
                                doc.get("content", "")[:100] + "..."
                                if doc.get("content")
                                else ""
                            ),
                        }
                        for doc in es_results
                    ]
                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "es_fulltext",
                            "message": f"ES检索完成，召回 {len(es_doc_ids)} 篇文档",
                            "result": {
                                "document_ids": es_doc_ids,
                                "count": len(es_doc_ids),
                                "documents": doc_summaries,
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "sql_structured":
                    # 先发送stage_start事件
                    yield SSEEvent(
                        event="stage_start",
                        data={
                            "stage": "sql_structured",
                            "message": "正在进行SQL结构化检索...",
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    # 再发送stage_complete事件
                    sql_doc_ids = list(state_data.get(
                        "sql_document_ids", set()))
                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "sql_structured",
                            "message": f"SQL检索完成，召回 {len(sql_doc_ids)} 篇文档",
                            "result": {
                                "document_ids": sql_doc_ids,
                                "count": len(sql_doc_ids),
                                "category": state_data.get("category", "*"),
                                "conditions": state_data.get(
                                    "sql_extracted_conditions", []
                                ),
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "merge_results":
                    # 先发送stage_start事件
                    yield SSEEvent(
                        event="stage_start",
                        data={
                            "stage": "merge_results",
                            "message": "正在融合检索结果...",
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    # 再发送stage_complete事件
                    merged_ids = state_data.get("merged_document_ids", [])
                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "merge_results",
                            "message": f"结果融合完成，融合后 {len(merged_ids)} 篇文档",
                            "result": {
                                "document_ids": merged_ids,
                                "count": len(merged_ids),
                                "strategy": state_data.get("fusion_strategy", "none"),
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "refined_filter":
                    # 先发送stage_start事件
                    yield SSEEvent(
                        event="stage_start",
                        data={
                            "stage": "refined_filter",
                            "message": "正在进行精细化筛选...",
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    # 再发送stage_complete事件
                    final_results = state_data.get("final_results", [])
                    result_summaries = [
                        {
                            "document_id": doc.get("document_id"),
                            "title": doc.get("title", ""),
                            "snippet": (
                                doc.get("content", "")[:100] + "..."
                                if doc.get("content")
                                else ""
                            ),
                        }
                        for doc in final_results
                    ]
                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "stage": "refined_filter",
                            "message": f"精细化筛选完成,最终 {len(final_results)} 篇文档",
                            "result": {
                                "document_ids": [
                                    doc.get("document_id") for doc in final_results
                                ],
                                "count": len(final_results),
                                "documents": result_summaries,
                            },
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                elif node_name == "generate_answer":
                    # 发送生成答案的开始事件
                    yield SSEEvent(
                        event="stage_start",
                        data={
                            "stage": "generate",
                            "message": "正在生成答案...",
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

            # 获取最终状态
            final_state = state_data if state_data is not None else {}

            # 检查是否有歧义消息需要用户澄清
            if final_state.get("ambiguity_message"):
                yield SSEEvent(
                    event="ambiguity",
                    data={"message": final_state["ambiguity_message"]},
                    id=task_id,
                    done=True,
                ).model_dump_json()
                return

            # 发送检索到的文档引用
            final_results = final_state.get("final_results", [])
            if final_results:
                references = []
                for i, doc in enumerate(final_results):
                    references.append(
                        {
                            "document_id": doc.get("document_id", i),
                            "title": doc.get("title", "未知文档"),
                            "snippet": (
                                doc.get("content", "")[:200] + "..."
                                if doc.get("content")
                                else ""
                            ),
                            "score": 1.0,
                        }
                    )

                yield SSEEvent(
                    event="references",
                    data={"references": references},
                    id=task_id,
                    done=False,
                ).model_dump_json()

            # 发送最终答案
            answer = final_state.get("answer", "抱歉，我没有找到相关答案。")
            yield SSEEvent(
                event="answer",
                data={"content": answer},
                id=task_id,
                done=False,
            ).model_dump_json()

            await asyncio.sleep(0.5)

            # 发送完成信号
            yield SSEEvent(
                event="complete",
                data={"message": "回答完成"},
                id=task_id,
                done=True,
            ).model_dump_json()

        except Exception as e:
            traceback.print_exc()
            yield SSEEvent(
                event="error",
                data={"message": f"智能体问答失败: {str(e)}"},
                id=task_id,
                done=True,
            ).model_dump_json()
        finally:
            # 关闭Elasticsearch客户端
            if es_client:
                await es_client.close()

    return EventSourceResponse(event_generator())


@router.post("/ask/beta/stream")
async def ask_question_beta_stream(
    request: Request,
    qa_request: QARequest,
    db: AsyncSession = Depends(get_db),
    config: DynamicConfig = Depends(get_config),
    current_user: User = Depends(get_current_user),
):
    """
    基于Master Router V4的流式问答接口（SSE）- 支持多轮对话和用户干预

    新架构特性：
    - 统一的工具和智能体注册中心
    - LLM基于完整信息进行智能决策
    - 支持5种执行模式：tool_only, agent_only, agent_chain, hybrid, llm_direct
    - 完整的状态管理和中间结果追踪
    - 支持多轮对话和用户干预

    参数：
    - **question**: 用户问题
    - **template_id**: 限定模板ID范围（必需）
    - **top_k**: 检索文档数量（默认5，范围1-20）
    - **session_id**: 会话ID（可选，用于多轮对话）
    - **user_input**: 用户输入（可选，当会话等待用户输入时）

    返回流式事件：
    - **plan**: 执行计划（包含execution_pattern和execution_plan）
    - **stage_start**: 阶段开始
    - **stage_complete**: 阶段完成（包含result数据）
    - **documents**: 检索到的文档
    - **user_input_request**: 请求用户输入（用户干预）
    - **answer**: 流式生成的答案片段
    - **complete**: 回答完成标记
    - **error**: 错误信息
    """

    # 检查template_id是否提供
    if not qa_request.template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用Beta问答必须提供template_id",
        )

    async def event_generator():
        """SSE事件生成器"""
        es_client = None
        task_id = str(uuid.uuid4())

        try:
            # 使用请求中的session_id，如果没有则生成新的
            session_id = qa_request.session_id
            if not session_id:
                session_id = str(uuid.uuid4())
                logger.info(f"🆕 [Beta] 生成新会话: {session_id}")
            else:
                logger.info(f"🔄 [Beta] 使用现有会话: {session_id}")

            # 初始化Elasticsearch客户端
            es_client = AsyncElasticsearch(
                [config.ELASTICSEARCH_URL], verify_certs=False
            )

            logger.info(f"🚀 [Beta] 开始处理问题: {qa_request.question}")

            # 使用新的三步执行函数，支持多轮对话和用户干预
            from services.agents.master_router import execute_master_router

            async for step_data in execute_master_router(
                query=qa_request.question,
                template_id=qa_request.template_id,
                db=db,
                es_client=es_client,
                es_index=config.ELASTICSEARCH_INDEX,
                session_id=session_id,
                user_id=current_user.id if current_user else None,
                user_input=qa_request.user_input,
            ):
                step_type = step_data["type"]
                data = step_data["data"]

                if step_type == "plan":
                    # 发送执行计划
                    await asyncio.sleep(0.3)
                    yield SSEEvent(
                        event="plan",
                        data={
                            "session_id": data.get("session_id"),
                            "execution_pattern": data["execution_pattern"],
                            "execution_plan": data["execution_plan"],
                            "reasoning": data["reasoning"],
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()
                    logger.info(
                        f"📊 [Beta] 已发送执行计划，共{len(data['execution_plan'])}步")

                elif step_type == "step_result":
                    # 发送步骤结果
                    await asyncio.sleep(0.3)

                    result_data = {data["step_type"] +
                                   "_result": {"result": data["result"]}}
                    if data.get("documents"):
                        result_data["documents"] = data["documents"]

                    yield SSEEvent(
                        event="stage_complete",
                        data={
                            "session_id": data.get("session_id"),
                            "stage": f"step_{data['step']}",
                            "step_index": data["step"],
                            "message": f"{data['description']}完成",
                            "result": result_data,
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()
                    logger.info(f"📊 [Beta] 已发送步骤{data['step']}结果")

                elif step_type == "hint":
                    # 发送提示信息（检索结果过多/过少）
                    await asyncio.sleep(0.3)

                    # 先发送文档（如果有）
                    hint_documents = data.get("documents", [])
                    if hint_documents:
                        references = []
                        for doc in hint_documents:
                            references.append({
                                "document_id": doc.get("id") or doc.get("document_id"),
                                "title": doc.get("title", "未命名文档"),
                                "snippet": doc.get("ai_summary") or doc.get("content", "")[:200],
                                "score": doc.get("score", 1.0),
                            })

                        yield SSEEvent(
                            event="documents",
                            data={
                                "session_id": data.get("session_id"),
                                "documents": references
                            },
                            id=task_id,
                            done=False,
                        ).model_dump_json()

                    # 发送hint消息
                    hint_message = data.get("message", "")
                    yield SSEEvent(
                        event="answer",
                        data={
                            "session_id": data.get("session_id"),
                            "content": hint_message
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    logger.info(f"💡 [Beta] 已发送hint提示: {data.get('hint_type')}")

                elif step_type == "user_input_request":
                    # 发送用户输入请求（用户干预）
                    await asyncio.sleep(0.3)
                    yield SSEEvent(
                        event="user_input_request",
                        data={
                            "session_id": data.get("session_id"),
                            "prompt": data.get("prompt"),
                            "input_type": data.get("input_type"),
                            "options": data.get("options"),
                            "documents": data.get("documents", []),
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()
                    logger.info(f"⏸️ [Beta] 请求用户输入: {data.get('input_type')}")

                elif step_type == "final":
                    # 发送文档引用（如果有）
                    references = []
                    if data["documents"]:
                        await asyncio.sleep(0.5)
                        for doc in data["documents"]:
                            references.append({
                                "document_id": doc.get("id") or doc.get("document_id"),
                                "title": doc.get("title", "未命名文档"),
                                "snippet": doc.get("ai_summary") or doc.get("content", "")[:200],
                                "score": doc.get("score", 1.0),
                            })

                        yield SSEEvent(
                            event="documents",
                            data={
                                "session_id": data.get("session_id"),
                                "documents": references
                            },
                            id=task_id,
                            done=False,
                        ).model_dump_json()

                    # 发送答案
                    answer = data["final_answer"] or "抱歉，无法生成答案。"
                    await asyncio.sleep(0.5)

                    yield SSEEvent(
                        event="answer",
                        data={
                            "session_id": data.get("session_id"),
                            "content": answer
                        },
                        id=task_id,
                        done=False,
                    ).model_dump_json()

                    # 发送完成信号（带上答案）
                    yield SSEEvent(
                        event="complete",
                        data={
                            "session_id": data.get("session_id"),
                            "message": "回答完成",
                            "answer": answer,  # 关键：带上答案
                            "documents": references,
                        },
                        id=task_id,
                        done=True,
                    ).model_dump_json()

        except Exception as e:
            logger.error(f"❌ [Beta] 问答失败: {e}")
            logger.error(traceback.format_exc())
            # 发送错误事件
            yield SSEEvent(
                event="error",
                data={"message": f"Beta问答失败: {str(e)}"},
                id=task_id,
                done=True,
            ).model_dump_json()
        finally:
            # 关闭Elasticsearch客户端
            if es_client:
                await es_client.close()

    return EventSourceResponse(event_generator())


@router.post("/ask/agent/clarify")
async def clarify_question_agent(
    request: Request,
    qa_request: QARequest,
    clarification: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    config: DynamicConfig = Depends(get_config),
    current_user: User = Depends(get_current_user),
):
    """
    澄清问题后继续智能体问答流程

    - **question**: 用户问题
    - **template_id**: 限定模板ID范围（必需）
    - **clarification**: 用户对歧义问题的澄清
    - **session_id**: 会话ID

    返回流式事件：
    - **thinking**: 思考过程状态更新
    - **references**: 检索到的相关文档引用
    - **answer**: 流式生成的答案片段
    - **complete**: 回答完成标记
    - **error**: 错误信息
    """

    # 检查template_id是否提供
    if not qa_request.template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用智能体问答必须提供template_id",
        )

    async def event_generator():
        """SSE事件生成器"""
        es_client = None  # 初始化
        # 生成会话/任务ID（整个流程使用同一个UUID）
        task_id = str(uuid.uuid4())
        try:
            # 检查会话ID是否存在
            if session_id not in graph_state_storage:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的会话ID或会话已过期",
                )

            # 获取存储的状态
            stored_state = graph_state_storage[session_id]

            # 更新问题为澄清后的问题
            stored_state["query"] = f"{stored_state['query']} {clarification}"
            # 清除歧义消息
            stored_state["ambiguity_message"] = None

            # 初始化Elasticsearch客户端
            es_client = AsyncElasticsearch(
                [config.ELASTICSEARCH_URL], verify_certs=False
            )
            stored_state["es_client"] = es_client

            # 发送开始处理消息
            yield SSEEvent(
                event="thinking",
                data={
                    "stage": "start",
                    "message": "正在处理您的澄清...",
                },
                id=task_id,
                done=False,
            ).model_dump_json()

            # 继续运行LangGraph智能体图
            # type: ignore
            final_state = await search_agent_app.ainvoke(
                dict(stored_state),
                config={
                    "configurable": {
                        "db": db,
                        "es": es_client,
                        "es_index": config.ELASTICSEARCH_INDEX,
                        "rag_max_length": config.RAG_MAX_CONTEXT_LENGTH,
                    }
                },
            )

            # 发送检索到的文档引用
            final_results = final_state.get("final_results", [])
            if final_results:
                references = []
                for i, doc in enumerate(final_results):
                    references.append(
                        {
                            "document_id": doc.get("document_id", i),
                            "title": doc.get("title", "未知文档"),
                            "snippet": (
                                doc.get("content", "")[:200] + "..."
                                if doc.get("content")
                                else ""
                            ),
                            "score": 1.0,
                        }
                    )

                yield SSEEvent(
                    event="references",
                    data={"references": references},
                    id=task_id,
                    done=False,
                ).model_dump_json()

            # 发送最终答案
            answer = final_state.get("answer", "抱歉，我没有找到相关答案。")
            yield SSEEvent(
                event="answer",
                data={"content": answer},
                id=task_id,
                done=False,
            ).model_dump_json()

            # 发送完成信号
            yield SSEEvent(
                event="complete",
                data={"message": "回答完成"},
                id=task_id,
                done=True,
            ).model_dump_json()

            # 清除存储的状态
            if session_id in graph_state_storage:
                del graph_state_storage[session_id]

        except Exception as e:
            # 发送错误事件
            yield SSEEvent(
                event="error",
                data={"message": f"智能体问答失败: {str(e)}"},
                id=task_id,
                done=True,
            ).model_dump_json()
        finally:
            # 关闭Elasticsearch客户端
            if es_client:
                await es_client.close()

    return EventSourceResponse(event_generator())
