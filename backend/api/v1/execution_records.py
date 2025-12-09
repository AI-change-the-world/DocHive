"""
执行记录API接口
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from models.database_models import AgentExecutionRecord, User
from services.execution_record_service import ExecutionRecordService

router = APIRouter(prefix="/execution-records", tags=["execution-records"])


# ============= Schema定义 =============


class ExecutionRecordListRequest(BaseModel):
    """执行记录列表请求"""

    agent_id: Optional[int] = Field(None, description="Agent ID筛选")
    status: Optional[str] = Field(
        None, description="状态筛选: running/completed/failed/cancelled")
    template_id: Optional[int] = Field(None, description="模板ID筛选")
    start_date: Optional[int] = Field(None, description="开始时间戳")
    end_date: Optional[int] = Field(None, description="结束时间戳")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class ExecutionRecordResponse(BaseModel):
    """执行记录响应"""

    id: int
    agent_id: Optional[int]
    agent_name: str
    query: str
    template_id: int
    execution_pattern: Optional[str]
    session_id: Optional[str]
    status: str
    total_steps: int
    executed_steps: int
    successful_steps: int
    failed_steps: int
    success_rate: int
    start_time: Optional[int]
    end_time: Optional[int]
    duration_seconds: Optional[int]
    user_id: Optional[int]
    created_at: int
    updated_at: int
    # 报告相关字段
    report_data: Optional[dict] = None
    html_report: Optional[str] = None
    markdown_report: Optional[str] = None

    class Config:
        from_attributes = True


class ExecutionRecordDetailResponse(ExecutionRecordResponse):
    """执行记录详情响应"""

    execution_plan: list
    step_history: list
    final_result: dict
    report_data: dict
    html_report: Optional[str]
    markdown_report: Optional[str]


class ExecutionRecordListResponse(BaseModel):
    """执行记录列表响应"""

    total: int
    page: int
    page_size: int
    items: list[ExecutionRecordResponse]


class ExecutionStatisticsResponse(BaseModel):
    """执行统计响应"""

    total_executions: int
    by_status: dict
    avg_success_rate: float
    avg_duration_seconds: float


# ============= API接口 =============


@router.get("/list", response_model=ExecutionRecordListResponse)
async def list_execution_records(
    agent_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    template_id: Optional[int] = Query(None),
    start_date: Optional[int] = Query(None),
    end_date: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取执行记录列表
    """
    try:
        logger.info(f"📊 查询执行记录: user_id={current_user.id}, page={page}")
        # 暂时不按user_id筛选，调试用
        records, total = await ExecutionRecordService.list_records(
            db=db,
            user_id=None,  # current_user.id,  # TODO: 恢复用户筛选
            agent_id=agent_id,
            status=status,
            template_id=template_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [record.to_dict() for record in records],
        }
    except Exception as e:
        logger.error(f"获取执行记录列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记录失败: {str(e)}")


@router.get("/{record_id}", response_model=ExecutionRecordDetailResponse)
async def get_execution_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取执行记录详情
    """
    try:
        record = await ExecutionRecordService.get_record(db, record_id)

        if not record:
            raise HTTPException(status_code=404, detail="执行记录不存在")

        # 权限检查：只能查看自己的记录
        if record.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权访问此记录")

        return record.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取执行记录详情失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记录失败: {str(e)}")


@router.delete("/{record_id}")
async def delete_execution_record(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    删除执行记录
    """
    try:
        record = await ExecutionRecordService.get_record(db, record_id)

        if not record:
            raise HTTPException(status_code=404, detail="执行记录不存在")

        # 权限检查：只能删除自己的记录
        if record.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权删除此记录")

        success = await ExecutionRecordService.delete_record(db, record_id)

        if not success:
            raise HTTPException(status_code=500, detail="删除失败")

        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除执行记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/statistics/summary", response_model=ExecutionStatisticsResponse)
async def get_execution_statistics(
    start_date: Optional[int] = Query(None),
    end_date: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取执行统计信息
    """
    try:
        stats = await ExecutionRecordService.get_statistics(
            db=db,
            user_id=current_user.id,
            start_date=start_date,
            end_date=end_date,
        )

        return stats
    except Exception as e:
        logger.error(f"获取执行统计失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.get("/{record_id}/html")
async def get_execution_html_report(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取HTML格式的执行报告
    """
    try:
        record = await ExecutionRecordService.get_record(db, record_id)

        if not record:
            raise HTTPException(status_code=404, detail="执行记录不存在")

        # 权限检查
        if record.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权访问此记录")

        if not record.html_report:
            raise HTTPException(status_code=404, detail="HTML报告不存在")

        from fastapi.responses import HTMLResponse

        return HTMLResponse(content=record.html_report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取HTML报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取报告失败: {str(e)}")


@router.get("/{record_id}/markdown")
async def get_execution_markdown_report(
    record_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    获取Markdown格式的执行报告
    """
    try:
        record = await ExecutionRecordService.get_record(db, record_id)

        if not record:
            raise HTTPException(status_code=404, detail="执行记录不存在")

        # 权限检查
        if record.user_id != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="无权访问此记录")

        if not record.markdown_report:
            raise HTTPException(status_code=404, detail="Markdown报告不存在")

        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(content=record.markdown_report)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Markdown报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取报告失败: {str(e)}")
