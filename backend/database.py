from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from config import get_settings

settings = get_settings()

# 全局数据库引擎和会话工厂（延迟初始化）
engine: Optional[AsyncEngine] = None
AsyncSessionLocal = None

# 基础模型类
Base = declarative_base()


# 处理 SQLite 数据库 URL
def get_database_url():
    url = settings.DATABASE_URL
    logger.debug(f"Using database URL: {url}")
    # 如果是 SQLite，使用 aiosqlite
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        elif url.startswith("sqlite://"):
            url = url.replace("sqlite://", "sqlite+aiosqlite:///", 1)
    return url


def init_engine():
    """初始化数据库引擎（在Nacos配置加载后调用）"""
    global engine, AsyncSessionLocal

    if engine is not None:
        return  # 已经初始化

    # 创建异步引擎
    engine_kwargs: dict = {
        "echo": settings.DEBUG,
    }

    # SQLite 不需要连接池配置
    if not settings.DATABASE_URL.startswith("sqlite"):
        engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
        engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

    engine = create_async_engine(get_database_url(), **engine_kwargs)

    # 创建异步会话工厂
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    logger.info("✅ 数据库引擎初始化完成")


def get_engine() -> Optional[AsyncEngine]:
    """获取数据库引擎实例"""
    return engine


async def get_db():
    """数据库会话依赖"""
    if AsyncSessionLocal is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    # 先初始化引擎
    init_engine()

    if engine is None:
        raise RuntimeError("数据库引擎初始化失败")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
