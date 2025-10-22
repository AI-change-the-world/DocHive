from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from models.database_models import User, UserRole
from utils.security import verify_password, get_password_hash, create_access_token, create_refresh_token
from schemas.api_schemas import UserCreate
from loguru import logger

class AuthService:
    """认证服务"""
    
    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        username: str,
        password: str,
    ) -> Optional[User]:
        """用户认证"""
        result = await db.execute(
            select(User).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        
        if not verify_password(password, user.hashed_password):
            return None
        
        return user
    
    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_data: UserCreate,
    ) -> User:
        """创建用户"""
        # 检查用户名是否存在
        result = await db.execute(
            select(User).where(User.username == user_data.username)
        )
        if result.scalar_one_or_none():
            raise ValueError("用户名已存在")
        
        # 检查邮箱是否存在
        result = await db.execute(
            select(User).where(User.email == user_data.email)
        )
        if result.scalar_one_or_none():
            raise ValueError("邮箱已被注册")
        
        hashed_password = get_password_hash(user_data.password)
        
        # 创建用户
        user = User(
            username=user_data.username,
            email=user_data.email,
            hashed_password=hashed_password,
            role=user_data.role,
        )
        
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
        return user
    
    @staticmethod
    def generate_tokens(user: User) -> dict:
        """生成访问令牌和刷新令牌"""
        token_data = {
            "user_id": user.id,
            "username": user.username,
        }
        
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """根据ID获取用户"""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        result = await db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()
