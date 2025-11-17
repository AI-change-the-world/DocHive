"""
文档类型管理 API
提供文档类型的 CRUD、字段配置等功能
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user, get_db
from models.database_models import DocumentType, DocumentTypeField, User
from schemas.api_schemas import (
    DocumentTypeCreate,
    DocumentTypeFieldCreate,
    DocumentTypeFieldResponse,
    DocumentTypeFieldSchema,
    DocumentTypeFieldUpdate,
    DocumentTypeResponse,
    DocumentTypeUpdate,
    ResponseBase,
)
from services.document_type_service import DocumentTypeService

router = APIRouter()


@router.post("/", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_document_type(
    doc_type_data: DocumentTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建文档类型

    - **template_id**: 所属模板ID
    - **type_code**: 类型编码（如：DEV_DOC）
    - **type_name**: 类型名称（如：开发文档）
    - **fields**: 字段配置列表（可选）
    """
    try:
        doc_type = await DocumentTypeService.create_document_type(db, doc_type_data)
        return ResponseBase(
            code=201, message="文档类型创建成功", data=doc_type.to_dict()
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/template/{template_id}", response_model=ResponseBase)
async def get_document_types_by_template(
    template_id: int,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取指定模板的所有文档类型

    - **template_id**: 模板ID
    - **include_inactive**: 是否包含已停用的类型
    """
    doc_types = await DocumentTypeService.get_document_types_by_template(
        db, template_id, include_inactive
    )

    # 转换为字典并附加字段信息
    result = []
    for dt in doc_types:
        dt_dict = dt.to_dict()
        fields = await DocumentTypeService.get_fields(db, int(dt.id))  # type: ignore
        dt_dict["fields"] = [f.to_dict() for f in fields]
        result.append(dt_dict)

    return ResponseBase(message="获取成功", data=result)


@router.get("/{doc_type_id}", response_model=ResponseBase)
async def get_document_type(
    doc_type_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取文档类型详情（含字段配置）
    """
    doc_type = await DocumentTypeService.get_document_type(db, doc_type_id)

    if not doc_type:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    # 获取字段配置
    fields = await DocumentTypeService.get_fields(db, doc_type_id)

    result = doc_type.to_dict()
    result["fields"] = [f.to_dict() for f in fields]

    return ResponseBase(message="获取成功", data=result)


@router.put("/{doc_type_id}", response_model=ResponseBase)
async def update_document_type(
    doc_type_id: int,
    update_data: DocumentTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新文档类型基本信息
    """
    doc_type = await DocumentTypeService.update_document_type(
        db, doc_type_id, update_data
    )

    if not doc_type:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    return ResponseBase(message="更新成功", data=doc_type.to_dict())


@router.delete("/{doc_type_id}", response_model=ResponseBase)
async def delete_document_type(
    doc_type_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除文档类型（软删除）
    """
    success = await DocumentTypeService.delete_document_type(db, doc_type_id)

    if not success:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    return ResponseBase(message="删除成功")


# ==================== 字段管理接口 ====================


@router.post(
    "/{doc_type_id}/fields",
    response_model=ResponseBase,
    status_code=status.HTTP_201_CREATED,
)
async def add_field(
    doc_type_id: int,
    field_data: DocumentTypeFieldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    为文档类型添加字段
    """
    # 确保 doc_type_id 匹配
    field_data.doc_type_id = doc_type_id

    try:
        field = await DocumentTypeService.add_field(db, field_data)
        return ResponseBase(code=201, message="字段添加成功", data=field.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加失败: {str(e)}")


@router.get("/{doc_type_id}/fields", response_model=ResponseBase)
async def get_fields(
    doc_type_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取文档类型的所有字段
    """
    fields = await DocumentTypeService.get_fields(db, doc_type_id)
    return ResponseBase(message="获取成功", data=[f.to_dict() for f in fields])


@router.put("/fields/{field_id}", response_model=ResponseBase)
async def update_field(
    field_id: int,
    update_data: DocumentTypeFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新字段配置
    """
    field = await DocumentTypeService.update_field(db, field_id, update_data)

    if not field:
        raise HTTPException(status_code=404, detail="字段不存在")

    return ResponseBase(message="更新成功", data=field.to_dict())


@router.delete("/fields/{field_id}", response_model=ResponseBase)
async def delete_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除字段
    """
    success = await DocumentTypeService.delete_field(db, field_id)

    if not success:
        raise HTTPException(status_code=404, detail="字段不存在")

    return ResponseBase(message="删除成功")


@router.put("/{doc_type_id}/fields/batch", response_model=ResponseBase)
async def batch_update_fields(
    doc_type_id: int,
    fields: List[DocumentTypeFieldSchema],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量更新文档类型的字段配置
    会删除现有所有字段并重新创建
    """
    try:
        updated_fields = await DocumentTypeService.batch_update_fields(
            db, doc_type_id, fields
        )
        return ResponseBase(
            message="批量更新成功", data=[f.to_dict() for f in updated_fields]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新失败: {str(e)}")


@router.get("/{doc_type_id}/extraction-config", response_model=ResponseBase)
async def get_extraction_config(
    doc_type_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取文档类型的完整提取配置
    用于大模型提取时的配置引用
    """
    config = await DocumentTypeService.get_extraction_config(db, doc_type_id)

    if not config:
        raise HTTPException(status_code=404, detail="文档类型不存在")

    return ResponseBase(message="获取成功", data=config)
