#!/bin/bash

echo ""
echo "========================================"
echo "  DocHive 一键启动 (开发模式)"
echo "========================================"
echo ""
echo "使用最简单的配置启动 DocHive:"
echo "- 数据库: SQLite (零配置)"
echo "- 搜索引擎: Database 原生FTS"
echo "- 内存占用: ~100MB"
echo ""

cd "$(dirname "$0")"

# 检查 Python 是否安装
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 未安装，请先安装 Python 3.10+"
    exit 1
fi

echo "✅ Python 已安装"
echo ""

# 检查依赖是否安装
echo "📦 检查依赖..."
if ! python3 -c "import fastapi" &> /dev/null; then
    echo ""
    echo "⚠️  依赖未安装，开始安装依赖..."
    echo ""
    pip3 install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ 依赖安装失败，请检查网络连接"
        exit 1
    fi
    echo ""
    echo "✅ 依赖安装完成"
else
    echo "✅ 依赖已安装"
fi
echo ""

# 检查 .env 文件是否存在
if [ ! -f .env ]; then
    echo "📝 首次启动，创建默认配置..."
    cat > .env << 'EOF'
# DocHive 开发环境配置

# 数据库配置 - SQLite
DATABASE_URL=sqlite:///./dochive.db

# 搜索引擎配置 - Database 原生FTS
SEARCH_ENGINE=database

# 应用配置
SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET_KEY=dev-jwt-secret-key-change-in-production
DEBUG=True

# 对象存储配置 (OpenDAL)
STORAGE_TYPE=s3
STORAGE_BUCKET=dochive-documents
STORAGE_ENDPOINT=http://localhost:9000
STORAGE_REGION=us-east-1
STORAGE_ACCESS_KEY=minioadmin
STORAGE_SECRET_KEY=minioadmin
STORAGE_ROOT=/

# Redis 配置
REDIS_URL=redis://localhost:6379/0

# LLM 配置 (可选)
LLM_PROVIDER=openai
OPENAI_API_KEY=
DEFAULT_MODEL=gpt-3.5-turbo

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
EOF
    echo "✅ 配置文件创建完成"
else
    echo "✅ 配置文件已存在"
fi
echo ""

# 初始化搜索索引
echo "📦 初始化搜索索引..."
python3 scripts/init_search_index.py
if [ $? -ne 0 ]; then
    echo "⚠️  索引初始化失败，继续启动..."
else
    echo "✅ 搜索索引初始化完成"
fi
echo ""

# 检查必要服务
echo "🔍 检查必要服务..."
echo ""

# 检查 Redis
echo -n "- Redis (端口 6379): "
if nc -z localhost 6379 2>/dev/null || (command -v redis-cli &> /dev/null && redis-cli ping &> /dev/null); then
    echo "✅ Redis 已启动"
else
    echo "⚠️  Redis 未启动"
    echo "  请运行: docker run -d --name redis -p 6379:6379 redis:6-alpine"
fi

# 检查对象存储 (S3/MinIO)
echo -n "- 对象存储 (端口 9000): "
if nc -z localhost 9000 2>/dev/null || curl -s http://localhost:9000 &> /dev/null; then
    echo "✅ 对象存储已启动"
else
    echo "⚠️  对象存储未启动"
    echo "  请运行: docker run -d --name minio -p 9000:9000 -p 9001:9001 \\"
    echo "          -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \\"
    echo "          minio/minio server /data --console-address \":9001\""
fi

echo ""
echo "========================================"
echo "  准备就绪！正在启动后端服务..."
echo "========================================"
echo ""
echo "访问地址:"
echo "- API 文档: http://localhost:8000/docs"
echo "- ReDoc: http://localhost:8000/redoc"
echo ""
echo "提示:"
echo "- 首次启动会自动创建数据库表"
echo "- 使用 Ctrl+C 停止服务"
echo ""
echo "========================================"
echo ""

# 启动后端服务
python3 main.py
