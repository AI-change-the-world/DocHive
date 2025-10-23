import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from database import get_db
from schemas.api_schemas import (
    ClassTemplateCreate,
    ClassTemplateUpdate,
    ClassTemplateResponse,
    ResponseBase,
    PaginatedResponse,
)
from services.template_service import TemplateService
from api.deps import get_current_user
from models.database_models import User

router = APIRouter(prefix="/templates", tags=["分类模板管理"])


@router.post("/", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: ClassTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建分类模板
    
    - **name**: 模板名称
    - **levels**: 层级定义列表
    - **description**: 模板描述（可选）
    - **version**: 版本号（默认1.0）
    """
    try:
        template = await TemplateService.create_template(db, template_data, current_user.id)
        
        return ResponseBase(
            code=201,
            message="模板创建成功",
            data=ClassTemplateResponse.model_validate(template),
        )
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{template_id}", response_model=ResponseBase)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定模板详情"""
    template = await TemplateService.get_template(db, template_id)
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模板不存在",
        )
    
    return ResponseBase(
        data=ClassTemplateResponse.model_validate(template),
    )


@router.get("/", response_model=ResponseBase)
async def list_templates(
    page: int = 1,
    page_size: int = 20,
    is_active: bool = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取模板列表
    
    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（1-100）
    - **is_active**: 是否激活（可选）
    """
    skip = (page - 1) * page_size
    templates, total = await TemplateService.list_templates(
        db, skip=skip, limit=page_size, is_active=is_active
    )
    
    return ResponseBase(
        data=PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[ClassTemplateResponse.model_validate(t) for t in templates],
        ),
    )


@router.put("/{template_id}", response_model=ResponseBase)
async def update_template(
    template_id: int,
    template_data: ClassTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板信息"""
    template = await TemplateService.update_template(db, template_id, template_data)
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模板不存在",
        )
    
    return ResponseBase(
        message="模板更新成功",
        data=ClassTemplateResponse.model_validate(template),
    )


@router.delete("/{template_id}", response_model=ResponseBase)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板（软删除）"""
    success = await TemplateService.delete_template(db, template_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="模板不存在",
        )
    
    return ResponseBase(message="模板删除成功")
