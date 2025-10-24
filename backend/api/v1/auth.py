import traceback
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from schemas.api_schemas import (
    LoginRequest,
    Token,
    UserCreate,
    UserResponse,
    ResponseBase,
)
from services.auth_service import AuthService
from api.deps import get_current_user
from models.database_models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["认证与授权"])


@router.post("/register", response_model=ResponseBase, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db),
):
    """
    用户注册
    
    - **username**: 用户名（3-50字符）
    - **email**: 邮箱
    - **password**: 密码（至少6字符）
    - **role**: 角色（默认为普通用户）
    """
    try:
        user = await AuthService.create_user(db, user_data)
        
        return ResponseBase(
            code=201,
            message="注册成功",
            data=UserResponse.model_validate(user),
        )
    
    except ValueError as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=ResponseBase)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    """
    user = await AuthService.authenticate_user(
        db, login_data.username, login_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    tokens = AuthService.generate_tokens(user)
    
    return ResponseBase(
        message="登录成功",
        data={
            **tokens,
            "user": UserResponse.model_validate(user),
        },
    )


@router.get("/me", response_model=ResponseBase)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """获取当前用户信息"""
    return ResponseBase(
        data=UserResponse.model_validate(current_user),
    )


@router.post("/refresh", response_model=ResponseBase)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db),
):
    """
    刷新访问令牌
    
    - **refresh_token**: 刷新令牌
    """
    from utils.security import decode_token
    
    payload = decode_token(refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )
    
    user_id = payload.get("user_id")
    user = await AuthService.get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    
    tokens = AuthService.generate_tokens(user)
    
    return ResponseBase(
        message="令牌刷新成功",
        data=tokens,
    )
