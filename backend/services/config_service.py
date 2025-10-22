from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from models.database_models import SystemConfig


class ConfigService:
    """系统配置服务"""
    
    @staticmethod
    async def get_config(
        db: AsyncSession,
        config_key: str,
    ) -> Optional[SystemConfig]:
        """获取配置"""
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.config_key == config_key)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_configs(
        db: AsyncSession,
        is_public: Optional[bool] = None,
    ) -> List[SystemConfig]:
        """获取配置列表"""
        query = select(SystemConfig)
        
        if is_public is not None:
            query = query.where(SystemConfig.is_public == is_public)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def set_config(
        db: AsyncSession,
        config_key: str,
        config_value: dict,
        description: Optional[str] = None,
        is_public: bool = False,
    ) -> SystemConfig:
        """设置配置"""
        config = await ConfigService.get_config(db, config_key)
        
        if config:
            # 更新现有配置
            config.config_value = config_value
            if description is not None:
                config.description = description
            config.is_public = is_public
        else:
            # 创建新配置
            config = SystemConfig(
                config_key=config_key,
                config_value=config_value,
                description=description,
                is_public=is_public,
            )
            db.add(config)
        
        await db.commit()
        await db.refresh(config)
        
        return config
    
    @staticmethod
    async def delete_config(
        db: AsyncSession,
        config_key: str,
    ) -> bool:
        """删除配置"""
        config = await ConfigService.get_config(db, config_key)
        
        if not config:
            return False
        
        await db.delete(config)
        await db.commit()
        
        return True
