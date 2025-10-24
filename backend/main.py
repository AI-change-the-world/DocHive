from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from config import get_settings
from database import init_db
from api.router import api_v1_router
from utils.search_engine import search_client
import logging
from loguru import logger

settings = get_settings()

# 配置日志
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 DocHive 后端服务启动中...")
    
    # 初始化数据库
    await init_db()
    logger.info("✅ 数据库初始化完成")
    
    # 初始化搜索引擎索引
    try:
        await search_client.ensure_index()
        logger.info("✅ 搜索引擎索引初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 搜索引擎初始化失败: {e}")
    
    yield
    
    # 关闭时
    logger.info("🛑 DocHive 后端服务关闭中...")
    
    # 关闭搜索引擎连接
    try:
        await search_client.close()
        logger.info("✅ 搜索引擎连接已关闭")
    except Exception as e:
        logger.error(f"❌ 搜索引擎关闭失败: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="智能文档分类分级系统 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    logger.error(f"全局异常: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
        },
    )


# 注册路由
app.include_router(api_v1_router)


# 健康检查端点
@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/")
async def root():
    """根端点"""
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
