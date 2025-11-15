from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas.api_schemas import (
    QARequest,
    QAResponse,
    ResponseBase,
)
from services.qa_service import QAService
from api.deps import get_current_user
from models.database_models import User
from sse_starlette import EventSourceResponse
import json
import uuid
from typing import Dict, Any, Optional

# 导入search_agent相关模块
from services.search_agent import (
    app as search_agent_app,
    RetrievalState,
    graph_state_storage,
)
from elasticsearch import AsyncElasticsearch
from config import get_settings

router = APIRouter(prefix="/qa", tags=["智能问答"])


@router.post("/ask/stream")
async def ask_question_stream(
    qa_request: QARequest,
    db: AsyncSession = Depends(get_db),
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
                "event": "error",
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
        try:
            # 生成会话ID
            session_id = str(uuid.uuid4())

            # 获取配置
            settings = get_settings()

            # 初始化Elasticsearch客户端
            es_client = AsyncElasticsearch(
                [settings.ELASTICSEARCH_URL], verify_certs=False
            )

            try:
                # 构造初始状态
                initial_state: RetrievalState = {
                    "query": qa_request.question,
                    "template_id": qa_request.template_id or 0,  # 确保是int类型
                    "db": db,
                    "es_client": es_client,
                    "session_id": session_id,
                    "class_template_levels": None,
                    "docs": [],
                    "category": "*",
                    "category_field_code": None,
                    "document_type_fields": [],
                    "extracted_llm_json": None,
                    "es_query": None,
                    "es_results": [],
                    "ambiguity_message": None,
                    "answer": None,
                }

                # 发送开始处理消息
                yield {
                    "event": "thinking",
                    "data": json.dumps(
                        {
                            "event": "thinking",
                            "data": {
                                "stage": "start",
                                "message": "开始处理您的问题...",
                            },
                            "done": False,
                        },
                        ensure_ascii=False,
                    ),
                }

                # 运行智能体图
                final_state = await search_agent_app.ainvoke(dict(initial_state))

                # 检查是否有歧义消息需要用户澄清
                if final_state.get("ambiguity_message"):
                    yield {
                        "event": "ambiguity",
                        "data": json.dumps(
                            {
                                "event": "ambiguity",
                                "data": {"message": final_state["ambiguity_message"]},
                                "done": True,
                            },
                            ensure_ascii=False,
                        ),
                    }
                    return

                # 发送检索到的文档引用
                es_results = final_state.get("es_results", [])
                if es_results:
                    references = []
                    for i, doc in enumerate(es_results):
                        references.append(
                            {
                                "document_id": doc.get("document_id", i),
                                "title": doc.get("title", "未知文档"),
                                "snippet": (
                                    doc.get("content", "")[:200] + "..."
                                    if doc.get("content")
                                    else ""
                                ),
                                "score": 1.0,  # 简化处理
                            }
                        )

                    yield {
                        "event": "references",
                        "data": json.dumps(
                            {
                                "event": "references",
                                "data": {"references": references},
                                "done": False,
                            },
                            ensure_ascii=False,
                        ),
                    }

                # 发送最终答案
                answer = final_state.get("answer", "抱歉，我没有找到相关答案。")
                yield {
                    "event": "answer",
                    "data": json.dumps(
                        {
                            "event": "answer",
                            "data": {"content": answer},
                            "done": False,
                        },
                        ensure_ascii=False,
                    ),
                }

                # 发送完成信号
                yield {
                    "event": "complete",
                    "data": json.dumps(
                        {
                            "event": "complete",
                            "data": {"message": "回答完成"},
                            "done": True,
                        },
                        ensure_ascii=False,
                    ),
                }

            finally:
                # 关闭Elasticsearch客户端
                await es_client.close()

        except Exception as e:
            # 发送错误事件
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "event": "error",
                        "data": {"message": f"智能体问答失败: {str(e)}"},
                        "done": True,
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())


@router.post("/ask/agent/clarify")
async def clarify_question_agent(
    request: Request,
    qa_request: QARequest,
    clarification: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
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

            # 获取配置
            settings = get_settings()

            # 初始化Elasticsearch客户端
            es_client = AsyncElasticsearch(
                [settings.ELASTICSEARCH_URL], verify_certs=False
            )
            stored_state["es_client"] = es_client

            try:
                # 发送开始处理消息
                yield {
                    "event": "thinking",
                    "data": json.dumps(
                        {
                            "event": "thinking",
                            "data": {
                                "stage": "start",
                                "message": "正在处理您的澄清...",
                            },
                            "done": False,
                        },
                        ensure_ascii=False,
                    ),
                }

                # 继续运行智能体图
                final_state = await search_agent_app.ainvoke(dict(stored_state))

                # 发送检索到的文档引用
                es_results = final_state.get("es_results", [])
                if es_results:
                    references = []
                    for i, doc in enumerate(es_results):
                        references.append(
                            {
                                "document_id": doc.get("document_id", i),
                                "title": doc.get("title", "未知文档"),
                                "snippet": (
                                    doc.get("content", "")[:200] + "..."
                                    if doc.get("content")
                                    else ""
                                ),
                                "score": 1.0,  # 简化处理
                            }
                        )

                    yield {
                        "event": "references",
                        "data": json.dumps(
                            {
                                "event": "references",
                                "data": {"references": references},
                                "done": False,
                            },
                            ensure_ascii=False,
                        ),
                    }

                # 发送最终答案
                answer = final_state.get("answer", "抱歉，我没有找到相关答案。")
                yield {
                    "event": "answer",
                    "data": json.dumps(
                        {
                            "event": "answer",
                            "data": {"content": answer},
                            "done": False,
                        },
                        ensure_ascii=False,
                    ),
                }

                # 发送完成信号
                yield {
                    "event": "complete",
                    "data": json.dumps(
                        {
                            "event": "complete",
                            "data": {"message": "回答完成"},
                            "done": True,
                        },
                        ensure_ascii=False,
                    ),
                }

                # 清除存储的状态
                if session_id in graph_state_storage:
                    del graph_state_storage[session_id]

            finally:
                # 关闭Elasticsearch客户端
                await es_client.close()

        except Exception as e:
            # 发送错误事件
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "event": "error",
                        "data": {"message": f"智能体问答失败: {str(e)}"},
                        "done": True,
                    },
                    ensure_ascii=False,
                ),
            }

    return EventSourceResponse(event_generator())
