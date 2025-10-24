from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from schemas.api_schemas import (
    ClassificationRequest,
    ClassificationResponse,
    ResponseBase,
)
from services.classification_service import ClassificationEngine
from api.deps import get_current_user
from models.database_models import User

router = APIRouter(prefix="/classification", tags=["智能分类"])


@router.post("/classify", response_model=ResponseBase)
async def classify_document(
    request: ClassificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    对单个文档进行智能分类
    
    - **document_id**: 文档ID
    - **template_id**: 分类模板ID
    - **force_reclassify**: 是否强制重新分类
    """
    try:
        result = await ClassificationEngine.classify_document(
            db,
            request.document_id,
            request.template_id,
            request.force_reclassify,
        )
        
        return ResponseBase(
            message="文档分类成功",
            data=result,
        )
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"分类失败: {str(e)}",
        )


@router.post("/classify-batch", response_model=ResponseBase)
async def batch_classify_documents(
    document_ids: List[int],
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量分类文档
    
    - **document_ids**: 文档ID列表
    - **template_id**: 分类模板ID
    """
    try:
        results = await ClassificationEngine.batch_classify_documents(
            db, document_ids, template_id
        )
        
        success_count = sum(1 for r in results if r.get("status") in ["success", "already_classified"])
        
        return ResponseBase(
            message=f"批量分类完成，成功: {success_count}/{len(results)}",
            data={"results": results, "success_count": success_count, "total": len(results)},
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量分类失败: {str(e)}",
        )
