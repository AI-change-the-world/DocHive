"""
写作模板API路由
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_user
from database import get_db
from models.database_models import User, WritingTemplate
from schemas.api_schemas import ResponseBase

router = APIRouter(prefix="/writing-templates", tags=["写作模板管理"])


class WritingTemplateCreate(BaseModel):
    title: str
    theme: str
    content: str
    template_id: int
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class WritingTemplateResponse(BaseModel):
    id: int
    title: str
    theme: str
    content: str
    description: Optional[str] = None
    tags: List[str]
    template_id: int
    word_count: int
    created_at: int

    class Config:
        from_attributes = True


@router.get("/")
async def get_writing_templates(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取写作模板列表"""
    try:
        stmt = select(WritingTemplate).where(
            WritingTemplate.template_id == template_id,
            WritingTemplate.is_active == True,
        ).order_by(WritingTemplate.created_at.desc())

        result = await db.execute(stmt)
        templates = result.scalars().all()

        # 转换为响应格式
        data = []
        for tpl in templates:
            data.append({
                "id": tpl.id,
                "title": tpl.title,
                "theme": tpl.theme,
                "content": tpl.content,
                "description": tpl.description,
                "tags": tpl.tags_list,
                "template_id": tpl.template_id,
                "word_count": len(tpl.content) if tpl.content else 0,
                "created_at": tpl.created_at,
            })

        return ResponseBase(code=200, message="success", data=data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}")
async def get_writing_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取写作模板详情"""
    try:
        stmt = select(WritingTemplate).where(WritingTemplate.id == template_id)
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        data = {
            "id": template.id,
            "title": template.title,
            "theme": template.theme,
            "content": template.content,
            "description": template.description,
            "tags": template.tags_list,
            "template_id": template.template_id,
            "word_count": len(template.content) if template.content else 0,
            "created_at": template.created_at,
        }

        return ResponseBase(code=200, message="success", data=data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/")
async def create_writing_template(
    data: WritingTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建写作模板"""
    try:
        import time

        template = WritingTemplate(
            title=data.title,
            theme=data.theme,
            content=data.content,
            description=data.description,
            template_id=data.template_id,
            uploader_id=current_user.id,
            is_active=True,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )

        # 设置标签
        if data.tags:
            template.tags_list = data.tags

        db.add(template)
        await db.commit()
        await db.refresh(template)

        response_data = {
            "id": template.id,
            "title": template.title,
            "theme": template.theme,
            "content": template.content,
            "description": template.description,
            "tags": template.tags_list,
            "template_id": template.template_id,
            "word_count": len(template.content) if template.content else 0,
            "created_at": template.created_at,
        }

        return ResponseBase(code=200, message="创建成功", data=response_data)

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_writing_template(
    file: UploadFile = File(...),
    title: str = Form(...),
    theme: str = Form(...),
    template_id: int = Form(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传文件创建写作模板"""
    try:
        import json
        import time

        from services.document_service import DocumentParser

        # 解析文件内容
        file_bytes = await file.read()
        file_extension = file.filename.split(".")[-1].lower()

        # 解析文档
        doc = await DocumentParser.parse_file(file_bytes, file_extension)
        content = doc.get("content", "")

        if not content:
            raise HTTPException(status_code=400, detail="无法解析文件内容")

        # 解析标签
        tags_list = []
        if tags:
            try:
                tags_list = json.loads(tags)
            except:
                tags_list = [t.strip() for t in tags.split(",") if t.strip()]

        # 创建模板
        template = WritingTemplate(
            title=title,
            theme=theme,
            content=content,
            description=description,
            template_id=template_id,
            uploader_id=current_user.id,
            is_active=True,
            created_at=int(time.time()),
            updated_at=int(time.time()),
        )

        if tags_list:
            template.tags_list = tags_list

        db.add(template)
        await db.commit()
        await db.refresh(template)

        response_data = {
            "id": template.id,
            "title": template.title,
            "theme": template.theme,
            "content": template.content,
            "description": template.description,
            "tags": template.tags_list,
            "template_id": template.template_id,
            "word_count": len(template.content) if template.content else 0,
            "created_at": template.created_at,
        }

        return ResponseBase(code=200, message="上传成功", data=response_data)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{template_id}")
async def delete_writing_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除写作模板"""
    try:
        stmt = select(WritingTemplate).where(WritingTemplate.id == template_id)
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")

        # 软删除
        template.is_active = False
        await db.commit()

        return ResponseBase(code=200, message="删除成功")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
