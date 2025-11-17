import asyncio
import json
import traceback
import uuid
from typing import Any, Dict, Optional

from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette import EventSourceResponse

from api.deps import get_current_user
from config import get_settings
from database import get_db
from models.database_models import User
from schemas.api_schemas import QARequest, QAResponse, ResponseBase
from services.qa_service import QAService

# 导入search_agent相关模块
from services.search_agent import RetrievalState
from services.search_agent import app as search_agent_app
from services.search_agent import graph_state_storage

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
            # 构造初始状态 (优化后的状态机)
            initial_state: RetrievalState = {
                # 必需输入
                "query": qa_request.question,
                "template_id": qa_request.template_id or 0,
                "session_id": session_id,
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

            # 使用astream_events流式处理LangGraph,通过config注入db和es_client
            final_state = None
            async for event in search_agent_app.astream_events(
                initial_state,
                config={"configurable": {"db": db, "es": es_client}},
                version="v1",
            ):
                # 处理不同类型的事件
                event_type = event.get("event")
                event_name = event.get("name", "")

                # 调试日志
                print(f"[LangGraph Event] type={event_type}, name={event_name}")

                # 节点开始执行
                if event_type == "on_chain_start":
                    node_name = event_name

                    # 根据节点名称发送相应的thinking事件
                    if node_name == "es_fulltext":
                        yield {
                            "event": "thinking",
                            "data": json.dumps(
                                {
                                    "event": "thinking",
                                    "data": {
                                        "stage": "es_fulltext",
                                        "message": "正在进行ES全文检索...",
                                    },
                                    "done": False,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    elif node_name == "sql_structured":
                        yield {
                            "event": "thinking",
                            "data": json.dumps(
                                {
                                    "event": "thinking",
                                    "data": {
                                        "stage": "sql_structured",
                                        "message": "正在进行SQL结构化检索...",
                                    },
                                    "done": False,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    elif node_name == "merge_results":
                        yield {
                            "event": "thinking",
                            "data": json.dumps(
                                {
                                    "event": "thinking",
                                    "data": {
                                        "stage": "merge_results",
                                        "message": "正在融合检索结果...",
                                    },
                                    "done": False,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    elif node_name == "refined_filter":
                        yield {
                            "event": "thinking",
                            "data": json.dumps(
                                {
                                    "event": "thinking",
                                    "data": {
                                        "stage": "refined_filter",
                                        "message": "正在进行精细化筛选...",
                                    },
                                    "done": False,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    elif node_name == "generate_answer":
                        yield {
                            "event": "thinking",
                            "data": json.dumps(
                                {
                                    "event": "thinking",
                                    "data": {
                                        "stage": "generate",
                                        "message": "正在生成答案...",
                                    },
                                    "done": False,
                                },
                                ensure_ascii=False,
                            ),
                        }

                # 节点执行完成，获取最终状态
                elif event_type == "on_chain_end":
                    # 保存最终状态
                    if event_name == "LangGraph":
                        final_state = event.get("data", {}).get("output", {})
                        print(
                            f"[LangGraph] 获取到最终状态: {list(final_state.keys()) if final_state else 'None'}"
                        )

            # 如果没有获取到final_state，使用默认值
            if final_state is None:
                print("[LangGraph] 警告: 没有获取到final_state")
                final_state = {}

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
        finally:
            # 关闭Elasticsearch客户端
            await es_client.close()

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
                final_state = await search_agent_app.ainvoke(dict(stored_state))  # type: ignore

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
