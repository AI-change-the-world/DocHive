from fastapi import APIRouter, Depends, HTTPException, status
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
                    "data": json.dumps(event, ensure_ascii=False)
                }

        except Exception as e:
            # 发送错误事件
            yield {
                "event": "error",
                "data": json.dumps({
                    "event": "error",
                    "data": {"message": f"问答失败: {str(e)}"},
                    "done": True
                }, ensure_ascii=False)
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
