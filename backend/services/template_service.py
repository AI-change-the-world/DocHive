import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import List, Optional
from models.database_models import ClassTemplate, NumberingRule
from schemas.api_schemas import ClassTemplateCreate, ClassTemplateUpdate
import time


class TemplateService:
    """分类模板服务层"""
    
    @staticmethod
    async def create_template(
        db: AsyncSession,
        template_data: ClassTemplateCreate,
        creator_id: int
    ) -> ClassTemplate:
        """创建分类模板"""
        template = ClassTemplate(
            name=template_data.name,
            description=template_data.description,
            levels=[level.model_dump() for level in template_data.levels],  # 直接传入 list，setter 会自动转为 JSON 字符串
            version=template_data.version,
            creator_id=creator_id,
        )
        
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template
    
    @staticmethod
    async def get_template(db: AsyncSession, template_id: int) -> Optional[ClassTemplate]:
        """获取单个模板"""
        result = await db.execute(
            select(ClassTemplate).where(ClassTemplate.id == template_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_templates(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        is_active: Optional[bool] = None
    ) -> tuple[List[ClassTemplate], int]:
        """获取模板列表"""
        query = select(ClassTemplate)
        count_query = select(ClassTemplate)
        
        if is_active is not None:
            query = query.where(ClassTemplate.is_active == is_active)
            count_query = count_query.where(ClassTemplate.is_active == is_active)
        
        query = query.order_by(ClassTemplate.created_at.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        templates = result.scalars().all()
        
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        return list(templates), total
    
    @staticmethod
    async def update_template(
        db: AsyncSession,
        template_id: int,
        template_data: ClassTemplateUpdate
    ) -> Optional[ClassTemplate]:
        """更新模板"""
        template = await TemplateService.get_template(db, template_id)
        if not template:
            return None
        
        update_data = template_data.model_dump(exclude_unset=True)
        
        # 处理 levels 字段：直接传入 list，setter 会自动转为 JSON 字符串
        if "levels" in update_data and template_data.levels:
            update_data["levels"] = [level.model_dump() for level in template_data.levels]
        
        for field, value in update_data.items():
            setattr(template, field, value)
        
        # 使用 setattr 避免类型检查错误
        setattr(template, 'updated_at', int(time.time()))
        
        await db.commit()
        await db.refresh(template)
        return template
    
    @staticmethod
    async def delete_template(db: AsyncSession, template_id: int) -> bool:
        """删除模板（软删除）"""
        template = await TemplateService.get_template(db, template_id)
        if not template:
            return False
        
        # 使用 setattr 避免类型检查错误
        setattr(template, 'is_active', False)
        await db.commit()
        return True
