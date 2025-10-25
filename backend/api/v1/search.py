from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from schemas.api_schemas import (
    DocumentSearchRequest,
    DocumentResponse,
    ResponseBase,
    PaginatedResponse,
)
from services.search_service import SearchService
from api.deps import get_current_user
from models.database_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/search", tags=["文档检索"])


@router.post("/", response_model=ResponseBase)
async def search_documents(
    search_request: DocumentSearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    多维度文档检索

    支持以下检索方式：
    - **keyword**: 全文搜索关键词
    - **template_id**: 按模板过滤
    - **extracted_fields**: 按抽取字段过滤
    - **start_date/end_date**: 按时间范围过滤
    - **status**: 按状态过滤
    """
    try:
        result = await SearchService.search_documents(
            db,
            keyword=search_request.keyword,
            template_id=search_request.template_id,
            extracted_fields=search_request.extracted_fields,
            start_date=search_request.start_date,
            end_date=search_request.end_date,
            status=search_request.status,
            page=search_request.page,
            page_size=search_request.page_size,
        )

        return ResponseBase(
            data=PaginatedResponse(
                total=result["total"],
                page=result["page"],
                page_size=result["page_size"],
                items=[DocumentResponse.model_validate(d) for d in result["documents"]],
            )
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"检索失败: {str(e)}",
        )


@router.get("/statistics", response_model=ResponseBase)
async def get_statistics(
    template_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取文档统计信息

    - **template_id**: 按模板统计（可选）
    """
    try:
        stats = await SearchService.get_statistics(db, template_id)

        return ResponseBase(
            message="统计信息获取成功",
            data=stats,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"统计失败: {str(e)}",
        )


@router.post("/index/{document_id}", response_model=ResponseBase)
async def index_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将文档索引到搜索引擎"""
    from services.document_service import DocumentService

    document = await DocumentService.get_document(db, document_id)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    success = await SearchService.index_document_to_es(document)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="索引失败",
        )

    return ResponseBase(message="文档索引成功")
