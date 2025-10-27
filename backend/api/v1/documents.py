import traceback
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from database import get_db
from schemas.api_schemas import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    ResponseBase,
    PaginatedResponse,
)
from services.document_service import DocumentService
from api.deps import get_current_user
from models.database_models import User, TemplateDocumentMapping
from config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from services.search_service import SearchService
import json
from sse_starlette import EventSourceResponse

router = APIRouter(prefix="/documents", tags=["文档上传与管理"])
settings = get_settings()



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
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"统计失败: {str(e)}",
        )


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="上传的文档文件"),
    template_id: Optional[int] = Form(None, description="分类模板ID"),
    metadata: Optional[str] = Form(None, description="元数据（JSON格式）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传文档（流式传输）

    - **file**: 文档文件（PDF, DOCX, TXT, MD, PNG, JPG等）
    - **title**: 文档标题
    - **template_id**: 关联的分类模板ID（可选）
    - **metadata**: 额外的元数据信息（JSON字符串，可选）
    """
    if not template_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请选择分类模板",
        )

    # 验证文件类型
    file_extension = (
        file.filename.split(".")[-1].lower()
        if file.filename and "." in file.filename
        else ""
    )
    if file_extension not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文件格式，允许的格式: {', '.join(settings.allowed_extensions_list)}",
        )

    # 验证文件大小
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小超过限制（最大 {settings.MAX_UPLOAD_SIZE / 1024 / 1024}MB）",
        )

    # 解析元数据
    metadata_dict = {}
    if metadata:
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="元数据格式错误，应为有效的JSON字符串",
            )

    # 创建文档数据
    document_data = DocumentCreate(
        title=file.filename or "Untitled",
        template_id=template_id,
        metadata=metadata_dict,
    )

    # 使用流式上传
    return EventSourceResponse(
        DocumentService.upload_file_stream(
            db,
            file.file,
            file.filename or "Untitled",
            document_data,
            getattr(current_user, "id"),
        )
    )


@router.get("/{document_id}", response_model=ResponseBase)
async def get_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文档详情"""
    document = await DocumentService.get_document(db, document_id)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    # 获取映射表信息
    result = await db.execute(
        select(TemplateDocumentMapping).where(
            TemplateDocumentMapping.document_id == document_id
        )
    )
    mapping = result.scalar_one_or_none()
    
    # 创建响应数据，包含映射表中的信息
    response_data = document.to_dict()
    if mapping:
        response_data["class_code"] = getattr(mapping, "class_code")
        response_data["status"] = getattr(mapping, "status")
        response_data["error_message"] = getattr(mapping, "error_message")
        response_data["processed_time"] = getattr(mapping, "processed_time")
        response_data["extracted_data"] = mapping.extracted_data

    return ResponseBase(data=DocumentResponse.model_validate(response_data))


@router.get("/", response_model=ResponseBase)
async def list_documents(
    page: int = 1,
    page_size: int = 20,
    template_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取文档列表

    - **page**: 页码
    - **page_size**: 每页数量
    - **template_id**: 过滤模板ID
    - **status**: 过滤状态（pending, processing, completed, failed）
    """
    skip = (page - 1) * page_size
    documents, total = await DocumentService.list_documents(
        db, skip=skip, limit=page_size, template_id=template_id, status=status
    )

    # 获取映射表信息
    document_ids = [doc.id for doc in documents]
    if document_ids:
        result = await db.execute(
            select(TemplateDocumentMapping).where(
                TemplateDocumentMapping.document_id.in_(document_ids)
            )
        )
        mappings = result.scalars().all()
        mapping_dict = {mapping.document_id: mapping for mapping in mappings}
    else:
        mapping_dict = {}

    # 创建响应数据，包含映射表中的信息
    response_items = []
    for doc in documents:
        doc_data = doc.to_dict()
        mapping = mapping_dict.get(doc.id)
        if mapping:
            doc_data["class_code"] = getattr(mapping, "class_code")
            doc_data["status"] = getattr(mapping, "status")
            doc_data["error_message"] = getattr(mapping, "error_message")
            doc_data["processed_time"] = getattr(mapping, "processed_time")
            doc_data["extracted_data"] = mapping.extracted_data
        response_items.append(DocumentResponse.model_validate(doc_data))

    return ResponseBase(
        data=PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=response_items,
        )
    )


@router.put("/{document_id}", response_model=ResponseBase)
async def update_document(
    document_id: int,
    document_data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新文档信息"""
    document = await DocumentService.update_document(db, document_id, document_data)

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    # 获取映射表信息
    result = await db.execute(
        select(TemplateDocumentMapping).where(
            TemplateDocumentMapping.document_id == document_id
        )
    )
    mapping = result.scalar_one_or_none()
    
    # 创建响应数据，包含映射表中的信息
    response_data = document.to_dict()
    if mapping:
        response_data["class_code"] = getattr(mapping, "class_code")
        response_data["status"] = getattr(mapping, "status")
        response_data["error_message"] = getattr(mapping, "error_message")
        response_data["processed_time"] = getattr(mapping, "processed_time")
        response_data["extracted_data"] = mapping.extracted_data

    return ResponseBase(
        message="文档更新成功",
        data=DocumentResponse.model_validate(response_data),
    )


@router.delete("/{document_id}", response_model=ResponseBase)
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除文档"""
    success = await DocumentService.delete_document(db, document_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    return ResponseBase(message="文档删除成功")


@router.get("/{document_id}/download", response_model=ResponseBase)
async def get_download_url(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文档下载链接"""
    url = await DocumentService.get_download_url(db, document_id)

    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    return ResponseBase(
        message="获取下载链接成功", data={"download_url": url, "expires_in": 3600}
    )


@router.get("/{document_id}/class-code", response_model=ResponseBase)
async def get_document_class_code(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文档的分类编码"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(TemplateDocumentMapping).where(
            TemplateDocumentMapping.document_id == document_id
        )
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档分类信息不存在",
        )
    
    return ResponseBase(
        message="获取分类编码成功",
        data={"class_code": getattr(mapping, "class_code")}
    )


@router.get("/{document_id}/status", response_model=ResponseBase)
async def get_document_status(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取文档处理状态"""
    from sqlalchemy import select
    
    result = await db.execute(
        select(TemplateDocumentMapping).where(
            TemplateDocumentMapping.document_id == document_id
        )
    )
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档状态信息不存在",
        )
    
    return ResponseBase(
        message="获取状态成功",
        data={
            "status": getattr(mapping, "status"),
            "error_message": getattr(mapping, "error_message"),
            "processed_time": getattr(mapping, "processed_time")
        }
    )