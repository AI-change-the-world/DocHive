from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from schemas.api_schemas import (
    NumberingRuleCreate,
    NumberingRuleResponse,
    ResponseBase,
)
from services.numbering_service import NumberingService
from api.deps import get_current_user
from models.database_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/numbering", tags=["编号与索引"], deprecated=True)


@router.post("/generate/{document_id}", response_model=ResponseBase)
async def generate_document_number(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    为文档生成唯一编号

    - **document_id**: 文档ID
    """
    try:
        doc_number = await NumberingService.generate_document_number(db, document_id)

        return ResponseBase(
            message="编号生成成功",
            data={"document_id": document_id, "class_code": doc_number},
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"编号生成失败: {str(e)}",
        )


@router.post("/rules", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def create_numbering_rule(
    rule_data: NumberingRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建编号规则

    - **template_id**: 分类模板ID
    - **rule_format**: 编号格式（如：{year}-{dept_code}-{type_code}-{seq:04d}）
    - **separator**: 分隔符
    - **auto_increment**: 是否自动递增序列号
    """
    rule = await NumberingService.create_numbering_rule(
        db,
        rule_data.template_id,
        rule_data.rule_format,
        rule_data.separator,
        rule_data.auto_increment,
    )

    return ResponseBase(
        code=201,
        message="编号规则创建成功",
        data=NumberingRuleResponse.model_validate(rule),
    )


@router.get("/rules/template/{template_id}", response_model=ResponseBase)
async def get_template_numbering_rule(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板的编号规则"""
    rule = await NumberingService.get_numbering_rule(db, template_id)

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该模板尚未配置编号规则",
        )

    return ResponseBase(data=NumberingRuleResponse.model_validate(rule))


@router.post("/rules/{rule_id}/reset", response_model=ResponseBase)
async def reset_sequence(
    rule_id: int,
    new_sequence: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重置编号规则的序列号"""
    success = await NumberingService.reset_sequence(db, rule_id, new_sequence)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="编号规则不存在",
        )

    return ResponseBase(message=f"序列号已重置为 {new_sequence}")
