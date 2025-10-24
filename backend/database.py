from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from config import get_settings

settings = get_settings()

# 处理 SQLite 数据库 URL
def get_database_url():
    url = settings.DATABASE_URL
    # SQLite 使用标准格式
    return url

# 创建同步引擎
engine_kwargs = {
    "echo": settings.DEBUG,
}

# SQLite 不需要连接池配置
if not settings.DATABASE_URL.startswith('sqlite'):
    engine_kwargs.update({
        "pool_size": settings.DATABASE_POOL_SIZE,
        "max_overflow": settings.DATABASE_MAX_OVERFLOW,
    })

engine = create_engine(
    get_database_url(),
    **engine_kwargs
)

# 创建会话工厂
SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 基础模型类
Base = declarative_base()


def get_db():
    """数据库会话依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表"""
    Base.metadata.create_all(bind=engine)
