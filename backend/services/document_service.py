from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, BinaryIO
from models.database_models import Document
from schemas.api_schemas import DocumentCreate, DocumentUpdate
from utils.storage import storage_client
from utils.parser import DocumentParser
import uuid
import time
from pathlib import Path


class DocumentService:
    """文档服务层"""
    
    @staticmethod
    async def upload_document(
        db: AsyncSession,
        file_data: BinaryIO,
        filename: str,
        document_data: DocumentCreate,
        user_id: int,
    ) -> Document:
        """
        上传并解析文档
        
        Args:
            db: 数据库会话
            file_data: 文件数据流
            filename: 原始文件名
            document_data: 文档创建数据
            user_id: 上传用户ID
        
        Returns:
            创建的文档记录
        """
        # 获取文件扩展名
        file_extension = Path(filename).suffix
        
        # 生成唯一对象名
        import datetime
        object_name = f"{datetime.datetime.utcnow().strftime('%Y/%m/%d')}/{uuid.uuid4()}{file_extension}"
        
        # 读取文件数据
        file_bytes = file_data.read()
        file_data.seek(0)
        
        # 上传到对象存储
        file_path = await storage_client.upload_file(
            file_data,
            object_name,
            content_type=DocumentService._get_content_type(file_extension),
        )
        
        # 创建文档记录
        document = Document(
            title=document_data.title,
            original_filename=filename,
            file_path=file_path,
            file_type=file_extension.lstrip("."),
            file_size=len(file_bytes),
            template_id=document_data.template_id,
            doc_metadata=document_data.metadata or {},
            status="pending",
            uploader_id=user_id,
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        # 异步解析文档（实际应该使用 Celery 任务队列）
        try:
            await DocumentService.parse_document(db, document.id, file_bytes, file_extension)
        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)
            await db.commit()
        
        return document
    
    @staticmethod
    async def parse_document(
        db: AsyncSession,
        document_id: int,
        file_data: bytes,
        file_extension: str,
    ):
        """解析文档内容"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return
        
        try:
            document.status = "processing"
            await db.commit()
            
            # 解析文本内容
            content_text = await DocumentParser.parse_file(file_data, file_extension)
            
            # 提取元信息
            metadata = DocumentParser.extract_metadata(file_data, file_extension)
            
            # 生成摘要（这里简化处理，实际应该调用 LLM）
            summary = content_text[:500] if len(content_text) > 500 else content_text
            
            # 更新文档
            document.content_text = content_text
            document.summary = summary
            # 合并 doc_metadata
            current_metadata = document.doc_metadata or {}
            current_metadata.update(metadata)
            document.doc_metadata = current_metadata
            document.status = "completed"
            setattr(document, 'processed_time', int(time.time()))
            
            await db.commit()
            
        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)
            await db.commit()
            raise
    
    @staticmethod
    async def get_document(db: AsyncSession, document_id: int) -> Optional[Document]:
        """获取文档"""
        result = await db.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_documents(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        template_id: Optional[int] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> tuple[list[Document], int]:
        """获取文档列表"""
        query = select(Document)
        count_query = select(Document)
        
        if template_id:
            query = query.where(Document.template_id == template_id)
            count_query = count_query.where(Document.template_id == template_id)
        
        if status:
            query = query.where(Document.status == status)
            count_query = count_query.where(Document.status == status)
        
        if user_id:
            query = query.where(Document.uploader_id == user_id)
            count_query = count_query.where(Document.uploader_id == user_id)
        
        query = query.order_by(Document.upload_time.desc()).offset(skip).limit(limit)
        
        result = await db.execute(query)
        documents = result.scalars().all()
        
        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())
        
        return list(documents), total
    
    @staticmethod
    async def update_document(
        db: AsyncSession,
        document_id: int,
        document_data: DocumentUpdate,
    ) -> Optional[Document]:
        """更新文档"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return None
        
        update_data = document_data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(document, field, value)
        
        await db.commit()
        await db.refresh(document)
        return document
    
    @staticmethod
    async def delete_document(db: AsyncSession, document_id: int) -> bool:
        """删除文档"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return False
        
        # 从对象存储删除文件
        object_name = document.file_path.split("/", 1)[1] if "/" in document.file_path else document.file_path
        await storage_client.delete_file(object_name)
        
        # 从数据库删除
        await db.delete(document)
        await db.commit()
        return True
    
    @staticmethod
    async def get_download_url(db: AsyncSession, document_id: int) -> Optional[str]:
        """获取文档下载链接"""
        document = await DocumentService.get_document(db, document_id)
        if not document:
            return None
        
        # 提取对象名
        object_name = document.file_path.split("/", 1)[1] if "/" in document.file_path else document.file_path
        
        return storage_client.get_presigned_url(object_name)
    
    @staticmethod
    def _get_content_type(file_extension: str) -> str:
        """获取文件 MIME 类型"""
        content_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        return content_types.get(file_extension.lower(), "application/octet-stream")
