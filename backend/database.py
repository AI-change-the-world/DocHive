from typing import Optional

from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool

from config import DynamicConfig

# 全局数据库引擎和会话工厂(延迟初始化)
engine: Optional[AsyncEngine] = None
AsyncSessionLocal = None
_config: Optional[DynamicConfig] = None  # 存储配置引用

# 基础模型类
Base = declarative_base()


# 处理 SQLite 数据库 URL
def get_database_url(url: str) -> str:
    """URL转换:处理数据库 URL"""
    logger.debug(f"Using database URL: {url}")
    # 如果是 SQLite,使用 aiosqlite
    if url.startswith("sqlite"):
        if url.startswith("sqlite:///"):
            url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        elif url.startswith("sqlite://"):
            url = url.replace("sqlite://", "sqlite+aiosqlite:///", 1)
    # 如果是 MySQL,使用 aiomysql
    elif url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    elif url.startswith("mysql+pymysql://"):
        url = url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
    return url


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """为 SQLite 连接设置 PRAGMA 配置

    使用 DELETE 模式避免 WAL 模式的 cursor 问题
    """
    cursor = dbapi_conn.cursor()
    # 使用 DELETE 模式，避免 WAL 模式的并发问题
    cursor.execute("PRAGMA journal_mode=DELETE")
    # 设置忙等待超时（毫秒），避免立即报错
    cursor.execute("PRAGMA busy_timeout=30000")
    # 同步模式：FULL 确保数据安全
    cursor.execute("PRAGMA synchronous=FULL")
    # 启用外键约束
    cursor.execute("PRAGMA foreign_keys=ON")
    # 设置缓存大小（页数），提高性能
    cursor.execute("PRAGMA cache_size=10000")
    # 设置临时存储为内存模式
    cursor.execute("PRAGMA temp_store=MEMORY")
    # 设置锁定超时
    cursor.execute("PRAGMA lock_timeout=30000")
    cursor.close()


def _set_mysql_session(dbapi_conn, connection_record):
    """为 MySQL 连接设置会话配置"""
    cursor = dbapi_conn.cursor()
    # 设置字符集
    cursor.execute("SET NAMES utf8mb4")
    # 设置事务隔离级别
    cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
    # 设置 SQL 模式
    cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO'")
    cursor.close()


def init_engine(config: DynamicConfig):
    """初始化数据库引擎

    Args:
        config: 动态配置实例
    """
    global engine, AsyncSessionLocal, _config

    if engine is not None:
        return  # 已经初始化

    _config = config
    database_url = config.DATABASE_URL
    is_sqlite = database_url.startswith("sqlite")
    is_mysql = database_url.startswith("mysql")

    # 创建异步引擎
    engine_kwargs: dict = {
        "echo": False,
    }

    if is_sqlite:
        # SQLite 特殊配置
        # 使用 NullPool 避免连接复用导致的 cursor 问题
        from sqlalchemy.pool import NullPool
        engine_kwargs["poolclass"] = NullPool
        # 允许多线程访问（aiosqlite 需要）
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        logger.info("📦 使用 SQLite 数据库，已启用 DELETE 模式和 NullPool")
    elif is_mysql:
        # MySQL 配置
        engine_kwargs["pool_size"] = config.DATABASE_POOL_SIZE
        engine_kwargs["max_overflow"] = config.DATABASE_MAX_OVERFLOW
        engine_kwargs["pool_pre_ping"] = True  # 连接健康检查
        engine_kwargs["pool_recycle"] = 3600   # 连接回收时间（秒）
        engine_kwargs["connect_args"] = {
            "charset": "utf8mb4",
            "autocommit": False,
        }
        logger.info("📦 使用 MySQL 数据库，已启用连接池")
    else:
        # PostgreSQL 等其他数据库使用连接池
        engine_kwargs["pool_size"] = config.DATABASE_POOL_SIZE
        engine_kwargs["max_overflow"] = config.DATABASE_MAX_OVERFLOW

    engine = create_async_engine(
        get_database_url(database_url), **engine_kwargs)

    # 为 SQLite 添加 PRAGMA 配置
    if is_sqlite:
        @event.listens_for(engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            _set_sqlite_pragma(dbapi_conn, connection_record)
    
    # 为 MySQL 添加会话配置
    elif is_mysql:
        @event.listens_for(engine.sync_engine, "connect")
        def set_mysql_session(dbapi_conn, connection_record):
            _set_mysql_session(dbapi_conn, connection_record)

    # 创建异步会话工厂
    session_kwargs = {
        "class_": AsyncSession,
        "expire_on_commit": False,
        "autocommit": False,
        "autoflush": False,
    }
    
    # SQLite 需要特殊配置
    if is_sqlite:
        session_kwargs["close_resets_only"] = False
    
    AsyncSessionLocal = async_sessionmaker(engine, **session_kwargs)

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


async def init_db(config: DynamicConfig):
    """初始化数据库表

    Args:
        config: 动态配置实例
    """
    # 先初始化引擎
    init_engine(config)

    if engine is None:
        raise RuntimeError("数据库引擎初始化失败")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
