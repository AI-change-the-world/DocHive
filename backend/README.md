# DocHive 后端服务

> 基于 FastAPI 的智能文档分类分级系统后端

## 📋 项目概述

DocHive 是一个智能文档分类分级系统，支持：
- 自定义分类模板管理
- 基于大语言模型的智能文档分类
- 结构化信息抽取
- 自动编号生成
- 多维度文档检索
- 完整的权限管理

## 🏗️ 技术栈

- **Web 框架**: FastAPI 0.109.0
- **数据库**: PostgreSQL / MySQL / SQLite + SQLAlchemy (异步)
- **对象存储**: MinIO
- **搜索引擎**: 数据库原FTS / Elasticsearch / ClickHouse (可配置)
- **向量数据库**: Qdrant
- **LLM 集成**: OpenAI / DeepSeek
- **任务队列**: Celery + Redis
- **认证**: JWT

## 📁 项目结构

```
backend/
├── main.py                 # 应用入口
├── config.py               # 配置管理
├── database.py             # 数据库连接
├── requirements.txt        # 依赖列表
│
├── api/                    # API 路由层
│   ├── deps.py            # 依赖注入
│   ├── router.py          # 路由汇总
│   └── v1/                # v1 版本 API
│       ├── auth.py        # 认证接口
│       ├── templates.py   # 分类模板接口
│       ├── documents.py   # 文档管理接口
│       ├── classification.py  # 智能分类接口
│       ├── extraction.py  # 信息抽取接口
│       ├── numbering.py   # 编号管理接口
│       ├── search.py      # 检索接口
│       └── config.py      # 系统配置接口
│
├── models/                 # 数据模型层
│   └── database_models.py # SQLAlchemy 模型
│
├── schemas/                # Pydantic 模式
│   └── api_schemas.py     # API 请求/响应模式
│
├── services/               # 业务逻辑层
│   ├── auth_service.py    # 认证服务
│   ├── template_service.py        # 模板服务
│   ├── document_service.py        # 文档服务
│   ├── classification_service.py  # 分类服务
│   ├── extraction_service.py      # 抽取服务
│   ├── numbering_service.py       # 编号服务
│   ├── search_service.py          # 检索服务
│   └── config_service.py          # 配置服务
│
├── utils/                  # 工具模块
    ├── security.py        # 安全工具（JWT、密码加密）
    ├── storage.py         # MinIO 存储客户端
    ├── parser.py          # 文档解析器
    ├── llm_client.py      # LLM 客户端
    └── search_engine.py   # 多搜索引擎支持 (ES/ClickHouse/Database)
```

## 🚀 快速开始

### 1. 环境要求

#### 核心依赖
- Python 3.10+
- MinIO
- Redis 6+

#### 数据库 (任选其一)
- **SQLite** (开发调试推荐, 零配置)
- **PostgreSQL 14+** (生产环境推荐)
- **MySQL 8.0+** (也支持)

#### 搜索引擎 (可选)
- **Database 原FTS** (默认, 无需额外服务)
- **Elasticsearch 8+** (高性能, 占用内存 1GB+)
- **ClickHouse** (海量数据, 占用内存 200MB+)

#### 其他可选组件
- Tesseract OCR (图片识别)
- Qdrant (向量检索)

### 2. 安装依赖

```bash
cd backend
pip install -r requirements.txt
```

### 3. 配置环境变量

复制 `.env.example` 到 `.env` 并修改配置：

```bash
cp .env.example .env
```

关键配置项：
- `DATABASE_URL`: 数据库连接字符串 (PostgreSQL/MySQL/SQLite)
- `SEARCH_ENGINE`: 搜索引擎类型 (`database` / `elasticsearch` / `clickhouse`)
- `MINIO_*`: MinIO 配置
- `OPENAI_API_KEY` 或 `DEEPSEEK_API_KEY`: LLM API 密钥
- `JWT_SECRET_KEY`: JWT 密钥（请务必修改）

### 4. 初始化数据库

```bash
# 自动创建表（首次运行时）
python main.py

# 初始化搜索索引 (如果使用 database 搜索引擎)
python scripts/init_search_index.py
```

或使用 Alembic 进行迁移：

```bash
alembic init migrations
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

### 5. 启动服务

```bash
# 开发模式
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 6. 访问 API 文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📖 API 使用示例

### 用户注册

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "password123",
    "role": "admin"
  }'
```

### 用户登录

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "password123"
  }'
```

### 创建分类模板

```bash
curl -X POST "http://localhost:8000/api/v1/templates/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "年度部门分类模板",
    "description": "按年份、地点、部门、类型分类",
    "levels": [
      {"level": 1, "name": "年份"},
      {"level": 2, "name": "地点"},
      {"level": 3, "name": "部门"},
      {"level": 4, "name": "类型"}
    ]
  }'
```

### 上传文档

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "title=技术报告" \
  -F "template_id=1"
```

### 智能分类

```bash
curl -X POST "http://localhost:8000/api/v1/classification/classify" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": 1,
    "template_id": 1
  }'
```

## 🔧 核心功能模块

### 1. 分类模板管理
- 创建/更新/删除分类模板
- 支持无限层级
- 版本管理

### 2. 文档上传与解析
- 支持 PDF, DOCX, TXT, Markdown
- OCR 图片识别
- 自动提取元信息

### 3. 智能分类引擎
- 基于 LLM 的文档分类
- 自动匹配分类模板
- 支持强制重新分类

### 4. 信息抽取引擎
- 正则表达式抽取
- LLM 智能抽取
- 自定义抽取规则

### 5. 编号与索引
- 自动生成唯一编号
- 可配置编号格式
- 序列号自动递增

### 6. 文档检索
- 多搜索引擎支持 (Database FTS / Elasticsearch / ClickHouse)
- 多维度过滤
- 统计分析

> 📚 详细配置请查看: [docs/SEARCH_ENGINE.md](docs/SEARCH_ENGINE.md)

### 7. 权限管理
- 基于角色的访问控制（RBAC）
- JWT 认证
- 细粒度权限

## 🔐 安全说明

1. **请务必修改默认密钥**：
   - `SECRET_KEY`
   - `JWT_SECRET_KEY`

2. **生产环境建议**：
   - 启用 HTTPS
   - 配置防火墙
   - 限制 CORS 来源
   - 定期更新依赖

## 📝 开发指南

### 添加新功能模块

1. 在 `models/` 中定义数据模型
2. 在 `schemas/` 中定义 API 模式
3. 在 `services/` 中实现业务逻辑
4. 在 `api/v1/` 中创建路由
5. 在 `api/router.py` 中注册路由

### 数据库迁移

```bash
# 创建迁移文件
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

## 🐛 常见问题

### 1. 选择哪个数据库?
- **开发调试**: 推荐 SQLite (零配置)
- **生产环境**: 推荐 PostgreSQL (功能强大)
- **单机部署**: MySQL 也是不错的选择

### 2. 选择哪个搜索引擎?
- **开发调试**: 推荐 `database` (占用内存最少)
- **中小规模**: `database` 就够用 (< 10万篇文档)
- **大规模检索**: 推荐 `elasticsearch` (性能最佳)
- **海量数据**: 推荐 `clickhouse` (压缩比高)

> 🔍 详细比较请查看: [docs/SEARCH_ENGINE.md](docs/SEARCH_ENGINE.md)

### 3. MinIO 连接失败
- 检查 MinIO 服务是否启动
- 验证端点和凭据配置

### 4. LLM 调用失败
- 检查 API 密钥是否正确
- 验证网络连接
- 查看 API 配额限制

### 5. 搜索引擎初始化失败
- 系统会自动降级到数据库检索
- 检查 `.env` 中的搜索引擎配置
- 如使用 `database`,请运行 `python scripts/init_search_index.py`

## 📄 许可证

© 2025 DocHive. All Rights Reserved.
