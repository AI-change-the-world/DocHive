from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from schemas.api_schemas import (
    SystemConfigCreate,
    SystemConfigUpdate,
    SystemConfigResponse,
    ResponseBase,
)
from services.config_service import ConfigService
from api.deps import get_current_user, require_admin
from models.database_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/config", tags=["系统配置"])


@router.get("/", response_model=ResponseBase)
async def list_configs(
    is_public: bool = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取系统配置列表

    - **is_public**: 是否只显示公开配置
    """
    # 非管理员只能看公开配置
    if current_user.role != "admin" and (is_public is None or not is_public):
        is_public = True

    configs = await ConfigService.list_configs(db, is_public)

    return ResponseBase(
        data=[SystemConfigResponse.model_validate(c) for c in configs],
    )


@router.get("/{config_key}", response_model=ResponseBase)
async def get_config(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定配置"""
    config = await ConfigService.get_config(db, config_key)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配置不存在",
        )

    # 非管理员不能访问私有配置
    if not config.is_public and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问此配置",
        )

    return ResponseBase(data=SystemConfigResponse.model_validate(config))


@router.post("/", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_config(
    config_data: SystemConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """创建系统配置（需要管理员权限）"""
    config = await ConfigService.set_config(
        db,
        config_data.config_key,
        config_data.config_value,
        config_data.description,
        config_data.is_public,
    )

    return ResponseBase(
        code=201,
        message="配置创建成功",
        data=SystemConfigResponse.model_validate(config),
    )


@router.put("/{config_key}", response_model=ResponseBase)
async def update_config(
    config_key: str,
    config_data: SystemConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """更新系统配置（需要管理员权限）"""
    config = await ConfigService.get_config(db, config_key)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配置不存在",
        )

    update_data = config_data.model_dump(exclude_unset=True)

    config = await ConfigService.set_config(
        db,
        config_key,
        update_data.get("config_value", config.config_value),
        update_data.get("description", config.description),
        update_data.get("is_public", config.is_public),
    )

    return ResponseBase(
        message="配置更新成功",
        data=SystemConfigResponse.model_validate(config),
    )


@router.delete("/{config_key}", response_model=ResponseBase)
async def delete_config(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """删除系统配置（需要管理员权限）"""
    success = await ConfigService.delete_config(db, config_key)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配置不存在",
        )

    return ResponseBase(message="配置删除成功")
