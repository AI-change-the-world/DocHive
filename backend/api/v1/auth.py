import traceback

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from api.deps import get_config, get_current_user
from config import DynamicConfig
from database import get_db
from models.database_models import User
from schemas.api_schemas import (
    LoginRequest,
    ResponseBase,
    Token,
    UserCreate,
    UserResponse,
)
from services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证与授权"])


@router.post(
    "/register", response_model=ResponseBase, status_code=status.HTTP_201_CREATED
)
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
    config: DynamicConfig = Depends(get_config),
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

    tokens = AuthService.generate_tokens(user, config)

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
    config: DynamicConfig = Depends(get_config),
):
    """
    刷新访问令牌

    - **refresh_token**: 刷新令牌
    """
    from utils.security import decode_token

    payload = decode_token(refresh_token, config)

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

    tokens = AuthService.generate_tokens(user, config)

    return ResponseBase(
        message="令牌刷新成功",
        data=tokens,
    )
