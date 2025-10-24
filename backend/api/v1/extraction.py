from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from schemas.api_schemas import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionConfigCreate,
    ExtractionConfigUpdate,
    ExtractionConfigResponse,
    ResponseBase,
    PaginatedResponse,
)
from services.extraction_service import ExtractionEngine
from api.deps import get_current_user
from models.database_models import User, ExtractionConfig
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/extraction", tags=["信息抽取"])


@router.post("/extract", response_model=ResponseBase)
async def extract_document_info(
    request: ExtractionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    从文档中抽取结构化信息
    
    - **document_id**: 文档ID
    - **config_id**: 抽取配置ID
    """
    try:
        result = await ExtractionEngine.extract_document_info(
            db, request.document_id, request.config_id
        )
        
        return ResponseBase(
            message="信息抽取成功",
            data=result,
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"抽取失败: {str(e)}",
        )


@router.get("/configs", response_model=ResponseBase)
async def list_extraction_configs(
    page: int = 1,
    page_size: int = 20,
    doc_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取抽取配置列表
    
    - **page**: 页码
    - **page_size**: 每页数量
    - **doc_type**: 文档类型过滤
    """
    skip = (page - 1) * page_size
    configs, total = await ExtractionEngine.list_extraction_configs(
        db, skip=skip, limit=page_size, doc_type=doc_type
    )
    
    return ResponseBase(
        data=PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[ExtractionConfigResponse.model_validate(c) for c in configs],
        )
    )


@router.post("/configs", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_extraction_config(
    config_data: ExtractionConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建抽取配置
    
    - **name**: 配置名称
    - **doc_type**: 文档类型
    - **extract_fields**: 抽取字段列表
    """
    config = await ExtractionEngine.create_extraction_config(
        db,
        config_data.name,
        config_data.doc_type,
        [field.model_dump() for field in config_data.extract_fields],
    )
    
    return ResponseBase(
        code=201,
        message="抽取配置创建成功",
        data=ExtractionConfigResponse.model_validate(config),
    )


@router.get("/configs/{config_id}", response_model=ResponseBase)
async def get_extraction_config(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取抽取配置详情"""
    config = await ExtractionEngine.get_extraction_config(db, config_id)
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="抽取配置不存在",
        )
    
    return ResponseBase(data=ExtractionConfigResponse.model_validate(config))
