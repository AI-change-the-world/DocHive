from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from database import get_db
from schemas.api_schemas import (
    LLMLogResponse,
    LLMLogListRequest,
    ResponseBase,
    PaginatedResponse,
)
from models.database_models import LLMLog, User
from api.deps import get_current_user
from typing import Optional


router = APIRouter(prefix="/llm-logs", tags=["LLM调用日志"])


@router.post("/list", response_model=ResponseBase)
async def list_llm_logs(
    request: LLMLogListRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    查询LLM调用日志列表

    - **page**: 页码
    - **page_size**: 每页数量
    - **provider**: 提供商过滤（openai, deepseek等）
    - **model**: 模型名称过滤
    - **status**: 状态过滤（success, error）
    - **user_id**: 用户ID过滤
    - **start_date**: 开始时间
    - **end_date**: 结束时间
    """
    try:
        # 构建查询条件
        conditions = []
        
        if request.provider:
            conditions.append(LLMLog.provider == request.provider)
        if request.model:
            conditions.append(LLMLog.model == request.model)
        if request.status:
            conditions.append(LLMLog.status == request.status)
        if request.user_id:
            conditions.append(LLMLog.user_id == request.user_id)
        if request.start_date:
            start_timestamp = int(request.start_date.timestamp())
            conditions.append(LLMLog.created_at >= start_timestamp)
        if request.end_date:
            end_timestamp = int(request.end_date.timestamp())
            conditions.append(LLMLog.created_at <= end_timestamp)

        # 查询总数
        count_query = select(func.count(LLMLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # 查询日志列表
        skip = (request.page - 1) * request.page_size
        query = select(LLMLog).offset(skip).limit(request.page_size).order_by(LLMLog.created_at.desc())
        
        if conditions:
            query = query.where(and_(*conditions))
        
        result = await db.execute(query)
        logs = result.scalars().all()

        return ResponseBase(
            data=PaginatedResponse(
                total=total,
                page=request.page,
                page_size=request.page_size,
                items=[LLMLogResponse.model_validate(log) for log in logs],
            )
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询LLM日志失败: {str(e)}",
        )


@router.get("/statistics", response_model=ResponseBase)
async def get_llm_statistics(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取LLM调用统计信息

    - **provider**: 提供商过滤
    - **model**: 模型过滤
    - **user_id**: 用户ID过滤
    """
    try:
        conditions = []
        
        if provider:
            conditions.append(LLMLog.provider == provider)
        if model:
            conditions.append(LLMLog.model == model)
        if user_id:
            conditions.append(LLMLog.user_id == user_id)

        # 统计总调用次数
        count_query = select(func.count(LLMLog.id))
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await db.execute(count_query)
        total_calls = total_result.scalar()

        # 统计总token数
        token_query = select(func.sum(LLMLog.total_tokens))
        if conditions:
            token_query = token_query.where(and_(*conditions))
        
        token_result = await db.execute(token_query)
        total_tokens = token_result.scalar() or 0

        # 按状态统计
        status_query = select(
            LLMLog.status, 
            func.count(LLMLog.id).label("count")
        ).group_by(LLMLog.status)
        
        if conditions:
            status_query = status_query.where(and_(*conditions))
        
        status_result = await db.execute(status_query)
        by_status = {row.status: row.count for row in status_result.all()}

        # 按提供商统计
        provider_query = select(
            LLMLog.provider,
            func.count(LLMLog.id).label("count"),
            func.sum(LLMLog.total_tokens).label("tokens")
        ).group_by(LLMLog.provider)
        
        if conditions:
            provider_query = provider_query.where(and_(*conditions))
        
        provider_result = await db.execute(provider_query)
        by_provider = {
            row.provider: {"calls": row.count, "tokens": row.tokens or 0}
            for row in provider_result.all()
        }

        # 按模型统计
        model_query = select(
            LLMLog.model,
            func.count(LLMLog.id).label("count"),
            func.sum(LLMLog.total_tokens).label("tokens")
        ).group_by(LLMLog.model)
        
        if conditions:
            model_query = model_query.where(and_(*conditions))
        
        model_result = await db.execute(model_query)
        by_model = {
            row.model: {"calls": row.count, "tokens": row.tokens or 0}
            for row in model_result.all()
        }

        return ResponseBase(
            message="统计信息获取成功",
            data={
                "total_calls": total_calls,
                "total_tokens": total_tokens,
                "by_status": by_status,
                "by_provider": by_provider,
                "by_model": by_model,
            }
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"统计失败: {str(e)}",
        )


@router.get("/{log_id}", response_model=ResponseBase)
async def get_llm_log_detail(
    log_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取LLM调用日志详情"""
    result = await db.execute(select(LLMLog).where(LLMLog.id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="日志不存在",
        )

    return ResponseBase(data=LLMLogResponse.model_validate(log))
