@echo off
chcp 65001 > nul
title DocHive 一键启动 (开发模式)

echo.
echo ========================================
echo   DocHive 一键启动 (开发模式)
echo ========================================
echo.
echo 使用最简单的配置启动 DocHive:
echo - 数据库: SQLite (零配置)
echo - 搜索引擎: Database 原生FTS
echo - 内存占用: ~100MB
echo.

cd backend

REM 检查 Python 是否安装
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo ✅ Python 已安装
echo.

REM 检查依赖是否安装
echo 📦 检查依赖...
python -c "import fastapi" > nul 2>&1
if errorlevel 1 (
    echo.
    echo ⚠️  依赖未安装，开始安装依赖...
    echo.
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo ❌ 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    echo.
    echo ✅ 依赖安装完成
) else (
    echo ✅ 依赖已安装
)
echo.

REM 检查 .env 文件是否存在
if not exist .env (
    echo 📝 首次启动，创建默认配置...
    (
        echo # DocHive 开发环境配置
        echo.
        echo # 数据库配置 - SQLite
        echo DATABASE_URL=sqlite:///./dochive.db
        echo.
        echo # 搜索引擎配置 - Database 原生FTS
        echo SEARCH_ENGINE=database
        echo.
        echo # 应用配置
        echo SECRET_KEY=dev-secret-key-change-in-production
        echo JWT_SECRET_KEY=dev-jwt-secret-key-change-in-production
        echo DEBUG=True
        echo.
        echo # 对象存储配置 (OpenDAL)
        echo STORAGE_TYPE=s3
        echo STORAGE_BUCKET=dochive-documents
        echo STORAGE_ENDPOINT=http://localhost:9000
        echo STORAGE_REGION=us-east-1
        echo STORAGE_ACCESS_KEY=minioadmin
        echo STORAGE_SECRET_KEY=minioadmin
        echo STORAGE_ROOT=/
        echo.
        echo # Redis 配置
        echo REDIS_URL=redis://localhost:6379/0
        echo.
        echo # LLM 配置 (可选)
        echo LLM_PROVIDER=openai
        echo OPENAI_API_KEY=
        echo DEFAULT_MODEL=gpt-3.5-turbo
        echo.
        echo # CORS
        echo CORS_ORIGINS=http://localhost:3000,http://localhost:5173
    ) > .env
    echo ✅ 配置文件创建完成
) else (
    echo ✅ 配置文件已存在
)
echo.

REM 初始化搜索索引
echo 📦 初始化搜索索引...
python scripts\init_search_index.py
if errorlevel 1 (
    echo ⚠️  索引初始化失败，继续启动...
) else (
    echo ✅ 搜索索引初始化完成
)
echo.

REM 检查必要服务
echo 🔍 检查必要服务...
echo.

REM 检查 Redis
echo - Redis (端口 6379):
timeout /t 1 /nobreak > nul
curl -s http://localhost:6379 > nul 2>&1
if errorlevel 1 (
    echo   ⚠️  Redis 未启动
    echo   请运行: docker run -d --name redis -p 6379:6379 redis:6-alpine
) else (
    echo   ✅ Redis 已启动
)

REM 检查对象存储 (S3/MinIO)
echo - 对象存储 (端口 9000):
timeout /t 1 /nobreak > nul
curl -s http://localhost:9000 > nul 2>&1
if errorlevel 1 (
    echo   ⚠️  对象存储未启动
    echo   请运行: docker run -d --name minio -p 9000:9000 -p 9001:9001 \
    echo           -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
    echo           minio/minio server /data --console-address ":9001"
) else (
    echo   ✅ 对象存储已启动
)

echo.
echo ========================================
echo   准备就绪！正在启动后端服务...
echo ========================================
echo.
echo 访问地址:
echo - API 文档: http://localhost:8000/docs
echo - ReDoc: http://localhost:8000/redoc
echo.
echo 提示:
echo - 首次启动会自动创建数据库表
echo - 使用 Ctrl+C 停止服务
echo.
echo ========================================
echo.

REM 启动后端服务
python main.py

pause
