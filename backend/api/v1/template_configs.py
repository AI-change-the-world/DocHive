from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from models.database_models import User
from schemas.api_schemas import (
    ResponseBase,
    TemplateConfigResponse,
    TemplateConfigUpdate,
)
from services.template_config_service import TemplateConfigService

router = APIRouter(prefix="/template-configs", tags=["模板配置管理"])


@router.get("/template/{template_id}", response_model=ResponseBase)
async def get_template_configs(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取指定模板的所有配置项

    - **template_id**: 模板ID
    """
    try:
        configs = await TemplateConfigService.get_template_configs(db, template_id)

        return ResponseBase(
            message="配置列表获取成功",
            data=[TemplateConfigResponse.model_validate(config) for config in configs],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取配置失败: {str(e)}",
        )


@router.get("/{config_id}", response_model=ResponseBase)
async def get_config_detail(
    config_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单个配置详情"""
    config = await TemplateConfigService.get_config_by_id(db, config_id)

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="配置不存在",
        )

    return ResponseBase(data=TemplateConfigResponse.model_validate(config))


@router.put("/{config_id}", response_model=ResponseBase)
async def update_config(
    config_id: int,
    config_data: TemplateConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新配置值（仅允许修改config_value字段）

    - **config_id**: 配置ID
    - **config_value**: 新的配置值

    注意：不允许新增或删除配置项，只能修改已有配置的值
    """
    try:
        config = await TemplateConfigService.update_config_value(
            db, config_id, config_data
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="配置不存在",
            )

        return ResponseBase(
            message="配置更新成功",
            data=TemplateConfigResponse.model_validate(config),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新配置失败: {str(e)}",
        )


@router.post("/batch-update", response_model=ResponseBase)
async def batch_update_configs(
    updates: List[dict],  # [{"id": 1, "config_value": "new_value"}, ...]
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量更新配置值

    - **updates**: 更新列表，格式: [{"id": 1, "config_value": "new_value"}, ...]
    """
    try:
        configs = await TemplateConfigService.batch_update_configs(db, updates)

        return ResponseBase(
            message=f"成功更新 {len(configs)} 个配置",
            data=[TemplateConfigResponse.model_validate(config) for config in configs],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量更新配置失败: {str(e)}",
        )
