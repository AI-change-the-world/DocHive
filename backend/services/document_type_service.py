"""
文档类型管理服务
负责文档类型的 CRUD 操作和字段配置管理
"""
import traceback
from typing import List, Optional, Dict, Any
from sqlalchemy import select, and_
from models.database_models import DocumentType, DocumentTypeField
from schemas.api_schemas import (
    DocumentTypeCreate,
    DocumentTypeUpdate,
    DocumentTypeFieldCreate,
    DocumentTypeFieldUpdate,
    DocumentTypeFieldSchema
)
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentTypeService:
    """文档类型服务类"""
    
    @staticmethod
    async def create_document_type(db: AsyncSession, doc_type_data: DocumentTypeCreate) -> DocumentType:
        """
        创建文档类型
        
        Args:
            db: 数据库会话
            doc_type_data: 文档类型创建数据
            
        Returns:
            创建的文档类型对象
        """
        # 检查同一模板下是否已存在相同编码
        result = await db.execute(
            select(DocumentType).where(
                and_(
                    DocumentType.template_id == doc_type_data.template_id,
                    DocumentType.type_code == doc_type_data.type_code
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"文档类型编码 '{doc_type_data.type_code}' 在该模板下已存在")
        
        # 创建文档类型
        db_doc_type = DocumentType(
            template_id=doc_type_data.template_id,
            type_code=doc_type_data.type_code,
            type_name=doc_type_data.type_name,
            description=doc_type_data.description,
            extraction_prompt=doc_type_data.extraction_prompt,
        )
        db.add(db_doc_type)
        await db.flush()  # 获取 ID
        
        # 创建关联字段
        if doc_type_data.fields:
            for idx, field_schema in enumerate(doc_type_data.fields):
                db_field = DocumentTypeField(
                    doc_type_id=db_doc_type.id,
                    field_name=field_schema.field_name,
                    field_code=field_schema.field_code,
                    field_type=field_schema.field_type,
                    extraction_prompt=field_schema.extraction_prompt,
                    is_required=field_schema.is_required,
                    display_order=field_schema.display_order or idx,
                    placeholder_example=field_schema.placeholder_example,
                )
                db.add(db_field)
        
        await db.commit()
        await db.refresh(db_doc_type)
        return db_doc_type
    
    @staticmethod
    async def get_document_type(db: AsyncSession, doc_type_id: int) -> Optional[DocumentType]:
        """获取文档类型详情"""
        result = await db.execute(
            select(DocumentType).where(DocumentType.id == doc_type_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_document_types_by_template(
        db: AsyncSession, 
        template_id: int,
        include_inactive: bool = False
    ) -> List[DocumentType]:
        """
        获取指定模板的所有文档类型
        
        Args:
            db: 数据库会话
            template_id: 模板ID
            include_inactive: 是否包含已停用的类型
            
        Returns:
            文档类型列表
        """
        query = select(DocumentType).where(DocumentType.template_id == template_id)
        
        if not include_inactive:
            query = query.where(DocumentType.is_active == True)
        
        query = query.order_by(DocumentType.created_at.desc())
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_document_type_by_code(
        db: AsyncSession,
        template_id: int,
        type_code: str
    ) -> Optional[DocumentType]:
        """根据编码获取文档类型"""
        result = await db.execute(
            select(DocumentType).where(
                and_(
                    DocumentType.template_id == template_id,
                    DocumentType.type_code == type_code,
                    DocumentType.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def update_document_type(
        db: AsyncSession,
        doc_type_id: int,
        update_data: DocumentTypeUpdate
    ) -> Optional[DocumentType]:
        """
        更新文档类型
        
        Args:
            db: 数据库会话
            doc_type_id: 文档类型ID
            update_data: 更新数据
            
        Returns:
            更新后的文档类型对象
        """
        result = await db.execute(
            select(DocumentType).where(DocumentType.id == doc_type_id)
        )
        db_doc_type = result.scalar_one_or_none()
        
        if not db_doc_type:
            return None
        
        # 更新字段
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(db_doc_type, field, value)
        
        await db.commit()
        await db.refresh(db_doc_type)
        return db_doc_type
    
    @staticmethod
    async def delete_document_type(db: AsyncSession, doc_type_id: int) -> bool:
        """
        删除文档类型（软删除）
        
        Args:
            db: 数据库会话
            doc_type_id: 文档类型ID
            
        Returns:
            是否删除成功
        """
        result = await db.execute(
            select(DocumentType).where(DocumentType.id == doc_type_id)
        )
        db_doc_type = result.scalar_one_or_none()
        
        if not db_doc_type:
            return False
        
        # 使用 setattr 避免类型检查错误
        setattr(db_doc_type, 'is_active', False)
        await db.commit()
        return True
    
    # ==================== 字段管理 ====================
    
    @staticmethod
    async def add_field(db: AsyncSession, field_data: DocumentTypeFieldCreate) -> DocumentTypeField:
        """
        为文档类型添加字段
        
        Args:
            db: 数据库会话
            field_data: 字段创建数据
            
        Returns:
            创建的字段对象
        """
        # 检查字段编码是否已存在
        result = await db.execute(
            select(DocumentTypeField).where(
                and_(
                    DocumentTypeField.doc_type_id == field_data.doc_type_id,
                    DocumentTypeField.field_code == field_data.field_code
                )
            )
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"字段编码 '{field_data.field_code}' 已存在")
        
        db_field = DocumentTypeField(
            doc_type_id=field_data.doc_type_id,
            field_name=field_data.field_name,
            field_code=field_data.field_code,
            field_type=field_data.field_type,
            extraction_prompt=field_data.extraction_prompt,
            is_required=field_data.is_required,
            display_order=field_data.display_order,
            placeholder_example=field_data.placeholder_example,
        )
        
        db.add(db_field)
        await db.commit()
        await db.refresh(db_field)
        return db_field
    
    @staticmethod
    async def get_fields(db: AsyncSession, doc_type_id: int) -> List[DocumentTypeField]:
        """获取文档类型的所有字段"""
        result = await db.execute(
            select(DocumentTypeField)
            .where(DocumentTypeField.doc_type_id == doc_type_id)
            .order_by(DocumentTypeField.id)
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def update_field(
        db: AsyncSession,
        field_id: int,
        update_data: DocumentTypeFieldUpdate
    ) -> Optional[DocumentTypeField]:
        """更新字段配置"""
        result = await db.execute(
            select(DocumentTypeField).where(DocumentTypeField.id == field_id)
        )
        db_field = result.scalar_one_or_none()
        
        if not db_field:
            return None
        
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(db_field, field, value)
        
        await db.commit()
        await db.refresh(db_field)
        return db_field
    
    @staticmethod
    async def delete_field(db: AsyncSession, field_id: int) -> bool:
        """删除字段"""
        result = await db.execute(
            select(DocumentTypeField).where(DocumentTypeField.id == field_id)
        )
        db_field = result.scalar_one_or_none()
        
        if not db_field:
            return False
        
        await db.delete(db_field)
        await db.commit()
        return True
    
    @staticmethod
    async def batch_update_fields(
        db: AsyncSession,
        doc_type_id: int,
        fields: List[DocumentTypeFieldSchema]
    ) -> List[DocumentTypeField]:
        """
        批量更新文档类型的字段配置
        
        Args:
            db: 数据库会话
            doc_type_id: 文档类型ID
            fields: 字段配置列表
            
        Returns:
            更新后的字段列表
        """
        try:
            # 删除现有字段
            result = await db.execute(
                select(DocumentTypeField).where(DocumentTypeField.doc_type_id == doc_type_id)
            )
            existing_fields = result.scalars().all()
            for field in existing_fields:
                await db.delete(field)
            
            # 重新创建字段
            new_fields = []
            for idx, field_schema in enumerate(fields):
                db_field = DocumentTypeField(
                    doc_type_id=doc_type_id,
                    field_name=field_schema.field_name,
                    description=field_schema.description,
                    field_type=field_schema.field_type,
                )
                db.add(db_field)
                new_fields.append(db_field)
            
            await db.commit()
            
            # 刷新对象
            for field in new_fields:
                await db.refresh(field)
            
            return new_fields
        except Exception as e:
            traceback.print_exc()
            raise e
    
    @staticmethod
    async def get_extraction_config(db: AsyncSession, doc_type_id: int) -> Dict[str, Any]:
        """
        获取文档类型的完整提取配置
        用于大模型提取时的配置引用
        
        Returns:
            {
                "type_name": "开发文档",
                "extraction_prompt": "...",
                "fields": [
                    {"field_code": "author", "field_name": "编制人", ...}
                ]
            }
        """
        result = await db.execute(
            select(DocumentType).where(DocumentType.id == doc_type_id)
        )
        doc_type = result.scalar_one_or_none()
        if not doc_type:
            return {}
        
        fields = await DocumentTypeService.get_fields(db, doc_type_id)
        
        return {
            "type_code": doc_type.type_code,
            "type_name": doc_type.type_name,
            "extraction_prompt": doc_type.extraction_prompt,
            "fields": [
                {
                    "field_code": f.field_code,
                    "field_name": f.field_name,
                    "field_type": f.field_type,
                    "extraction_prompt": f.extraction_prompt,
                    "is_required": f.is_required,
                }
                for f in fields
            ]
        }
