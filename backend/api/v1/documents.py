from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
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
from models.database_models import User
from config import get_settings
import json

router = APIRouter(prefix="/documents", tags=["文档上传与管理"])
settings = get_settings()


@router.post("/upload", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(..., description="上传的文档文件"),
    title: str = Form(..., description="文档标题"),
    template_id: Optional[int] = Form(None, description="分类模板ID"),
    metadata: Optional[str] = Form(None, description="元数据（JSON格式）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    上传文档
    
    - **file**: 文档文件（PDF, DOCX, TXT, MD, PNG, JPG等）
    - **title**: 文档标题
    - **template_id**: 关联的分类模板ID（可选）
    - **metadata**: 额外的元数据信息（JSON字符串，可选）
    """
    # 验证文件类型
    file_extension = file.filename.split(".")[-1].lower() if "." in file.filename else ""
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
        title=title,
        template_id=template_id,
        metadata=metadata_dict,
    )
    
    # 上传文档
    document = await DocumentService.upload_document(
        db, file.file, file.filename, document_data, current_user.id
    )
    
    return ResponseBase(
        code=201,
        message="文档上传成功",
        data=DocumentResponse.model_validate(document),
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
    
    return ResponseBase(data=DocumentResponse.model_validate(document))


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
    
    return ResponseBase(
        data=PaginatedResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[DocumentResponse.model_validate(d) for d in documents],
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
    
    return ResponseBase(
        message="文档更新成功",
        data=DocumentResponse.model_validate(document),
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
        message="获取下载链接成功",
        data={"download_url": url, "expires_in": 3600}
    )
