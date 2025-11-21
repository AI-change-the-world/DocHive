from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DynamicConfig
from database import get_db
from models.database_models import User, UserRole
from utils.llm_client import LLMClient
from utils.search_engine import SearchEngine
from utils.security import decode_token
from utils.storage import StorageClient

security = HTTPBearer()


# ==================== 配置与服务依赖 ====================


def get_config(request: Request) -> DynamicConfig:
    """获取动态配置依赖

    从 app.state 中获取在 lifespan 中初始化的配置实例
    """
    return request.app.state.config


def get_search_engine(request: Request) -> SearchEngine:
    """获取搜索引擎依赖

    从 app.state 中获取在 lifespan 中初始化的搜索引擎实例
    """
    if not hasattr(request.app.state, "search_client"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="搜索引擎服务不可用"
        )
    return request.app.state.search_client


def get_storage(request: Request) -> StorageClient:
    """获取存储客户端依赖

    从 app.state 中获取在 lifespan 中初始化的存储客户端实例
    """
    if not hasattr(request.app.state, "storage_client"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="存储服务不可用"
        )
    return request.app.state.storage_client


def get_llm(request: Request) -> LLMClient:
    """获取LLM客户端依赖

    从 app.state 中获取在 lifespan 中初始化的LLM客户端实例
    """
    if not hasattr(request.app.state, "llm_client"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLM服务不可用"
        )
    return request.app.state.llm_client


# ==================== 认证依赖 ====================


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    config: DynamicConfig = Depends(get_config),
) -> User:
    """获取当前登录用户"""
    token = credentials.credentials

    payload = decode_token(token, config)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: int = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="用户未激活")
    return current_user


def require_role(required_role: UserRole):
    """角色权限依赖"""

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        role_hierarchy = {
            UserRole.ADMIN: 3,
            UserRole.REVIEWER: 2,
            UserRole.USER: 1,
        }

        user_level = role_hierarchy.get(current_user.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )

        return current_user

    return role_checker


# 管理员权限
require_admin = require_role(UserRole.ADMIN)
