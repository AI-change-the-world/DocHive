from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from models.database_models import ClassTemplateConfigs
from schemas.api_schemas import TemplateConfigUpdate


class TemplateConfigService:
    """模板配置服务层"""

    @staticmethod
    async def get_template_configs(
        db: AsyncSession,
        template_id: int,
    ) -> List[ClassTemplateConfigs]:
        """
        获取模板的所有配置项

        Args:
            db: 数据库会话
            template_id: 模板ID

        Returns:
            配置列表
        """
        result = await db.execute(
            select(ClassTemplateConfigs)
            .where(ClassTemplateConfigs.template_id == template_id)
            .where(ClassTemplateConfigs.is_active == True)
            .order_by(ClassTemplateConfigs.config_name)
        )
        return result.scalars().all()

    @staticmethod
    async def get_config_by_id(
        db: AsyncSession,
        config_id: int,
    ) -> Optional[ClassTemplateConfigs]:
        """
        根据ID获取单个配置

        Args:
            db: 数据库会话
            config_id: 配置ID

        Returns:
            配置对象或None
        """
        result = await db.execute(
            select(ClassTemplateConfigs).where(ClassTemplateConfigs.id == config_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_config_value(
        db: AsyncSession,
        config_id: int,
        config_data: TemplateConfigUpdate,
    ) -> Optional[ClassTemplateConfigs]:
        """
        更新配置值（仅允许修改config_value字段）

        Args:
            db: 数据库会话
            config_id: 配置ID
            config_data: 更新数据

        Returns:
            更新后的配置对象或None
        """
        config = await TemplateConfigService.get_config_by_id(db, config_id)

        if not config:
            return None

        # 仅允许修改config_value
        config.config_value = config_data.config_value

        await db.commit()
        await db.refresh(config)

        return config

    @staticmethod
    async def batch_update_configs(
        db: AsyncSession,
        updates: List[dict],  # [{"id": 1, "config_value": "new_value"}, ...]
    ) -> List[ClassTemplateConfigs]:
        """
        批量更新配置值

        Args:
            db: 数据库会话
            updates: 更新列表

        Returns:
            更新后的配置列表
        """
        updated_configs = []

        for update_item in updates:
            config_id = update_item.get("id")
            config_value = update_item.get("config_value")

            if not config_id or config_value is None:
                continue

            config = await TemplateConfigService.get_config_by_id(db, config_id)
            if config:
                config.config_value = config_value
                updated_configs.append(config)

        await db.commit()

        for config in updated_configs:
            await db.refresh(config)

        return updated_configs
