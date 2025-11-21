import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.router import api_v1_router
from config import LocalSettings, close_dynamic_config, create_dynamic_config
from database import init_db
from utils.llm_client import init_llm_client
from utils.search_engine import init_search_client
from utils.storage import init_storage_client

# 加载静态配置(用于启动时读取)
local_settings = LocalSettings()

# 配置日志
logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("🚀 DocHive 后端服务启动中...")

    # 1. 初始化动态配置(从Nacos加载)
    config = await create_dynamic_config()
    app.state.config = config
    logger.info("✅ 动态配置初始化完成")

    # 2. 初始化数据库
    await init_db(config)
    logger.info("✅ 数据库初始化完成")

    # 3. 初始化搜索引擎
    try:
        search_client = init_search_client(config)
        app.state.search_client = search_client
        await search_client.ensure_index()
        logger.info("✅ 搜索引擎初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 搜索引擎初始化失败: {e}")

    # 4. 初始化存储客户端
    try:
        storage_client = init_storage_client(config)
        app.state.storage_client = storage_client
        logger.info("✅ 存储客户端初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ 存储客户端初始化失败: {e}")

    # 5. 初始化LLM客户端
    try:
        llm_client = init_llm_client(config)
        app.state.llm_client = llm_client
        logger.info("✅ LLM客户端初始化完成")
    except Exception as e:
        logger.warning(f"⚠️ LLM客户端初始化失败: {e}")

    logger.info("✨ 所有服务初始化完成，服务已就绪")

    yield

    # 关闭时
    logger.info("🛑 DocHive 后端服务关闭中...")

    # 关闭动态配置服务
    try:
        await close_dynamic_config(config)
    except Exception as e:
        logger.error(f"❌ 配置服务关闭失败: {e}")

    # 关闭搜索引擎连接
    try:
        if hasattr(app.state, "search_client"):
            await app.state.search_client.close()
    except Exception as e:
        logger.error(f"❌ 搜索引擎关闭失败: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title=local_settings.APP_NAME,
    version="1.0.0",  # 静态版本号,或后续从config读取
    description="智能文档分类分级系统 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],  # 静态配置或环境变量
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("Validation error:", exc.errors())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器"""
    traceback.print_exc()
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
async def health_check(request: Request):
    """健康检查"""
    config = request.app.state.config
    return {
        "status": "healthy",
        "service": config.APP_NAME,
        "version": config.APP_VERSION,
    }


@app.get("/")
async def root(request: Request):
    """根端点"""
    config = request.app.state.config
    return {
        "message": f"Welcome to {config.APP_NAME} API",
        "version": config.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式
        log_level="info",
    )
