# DocHive 快速启动指南

## 📋 前置要求

### 后端环境
- Python 3.10+
- Redis 6+
- MinIO (可选，用于文件存储)

### 数据库 (任选其一)
- **SQLite** - 开发调试推荐 (零配置)
- **PostgreSQL 14+** - 生产环境推荐
- **MySQL 8.0+** - 也支持

### 搜索引擎 (可选)
- **Database 原FTS** - 默认,无需额外服务
- **Elasticsearch 8+** - 高性能全文检索
- **ClickHouse** - 海量数据分析

### 前端环境
- Node.js 18+
- pnpm 8+

---

## 🚀 快速启动

### 一、启动后端服务

#### 1. 进入后端目录
```bash
cd backend
```

#### 2. 创建虚拟环境（推荐）
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

#### 3. 安装依赖
```bash
pip install -r requirements.txt
```

#### 4. 配置环境变量

##### 方式一：使用配置向导 (推荐)
```bash
# Windows
configure_search.bat

# Linux/Mac
chmod +x configure_search.sh
./configure_search.sh
```

配置向导将引导您：
1. 选择搜索引擎类型 (Database/Elasticsearch/ClickHouse)
2. 配置数据库连接 (如果选择Database)
3. 自动初始化搜索索引

##### 方式二：手动配置
```bash
# 复制环境变量模板
copy .env.example .env

# 编辑 .env 文件，修改以下关键配置：
```

**开发环境配置示例 (最简单)**：
```env
# 使用 SQLite + Database 搜索引擎
DATABASE_URL=sqlite:///./dochive.db
SEARCH_ENGINE=database
SECRET_KEY=your-secret-key-change-me
JWT_SECRET_KEY=your-jwt-secret-key
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

**生产环境配置示例**：
```env
# 使用 PostgreSQL + Elasticsearch
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dochive
SEARCH_ENGINE=elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
SECRET_KEY=your-secret-key-change-me
JWT_SECRET_KEY=your-jwt-secret-key
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

> 📚 更多搜索引擎配置说明请查看: [backend/docs/SEARCH_ENGINE.md](backend/docs/SEARCH_ENGINE.md)

#### 5. 启动基础服务（Docker 方式）

##### 最简单：只需 MinIO + Redis

如果使用 **SQLite** 数据库 + **Database** 搜索引擎，只需启动：

```bash
# 启动 Redis
docker run -d \
  --name dochive-redis \
  -p 6379:6379 \
  redis:6-alpine

# 启动 MinIO
docker run -d \
  --name dochive-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

##### 完整配置：包含 PostgreSQL + Elasticsearch

如果使用 **PostgreSQL** + **Elasticsearch**：
```bash
# 启动 PostgreSQL
docker run -d \
  --name dochive-postgres \
  -e POSTGRES_DB=dochive \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:14

# 启动 Redis
docker run -d \
  --name dochive-redis \
  -p 6379:6379 \
  redis:6-alpine

# 启动 MinIO
docker run -d \
  --name dochive-minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

# (可选) 启动 Elasticsearch
docker run -d \
  --name dochive-elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
  docker.elastic.co/elasticsearch/elasticsearch:8.11.0
```

> 💡 **提示**: 开发调试推荐使用 SQLite,只需启动 Redis + MinIO,内存占用最小!

#### 6. 初始化搜索索引 (如果使用 Database 搜索引擎)
```bash
python scripts/init_search_index.py
```

#### 7. 启动后端服务
python main.py

# 方式二：使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

后端服务启动后访问：
- API 文档: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

### 二、启动前端服务

#### 1. 进入前端目录
```bash
cd frontend
```

#### 2. 安装依赖
```bash
pnpm install

# 如果没有 pnpm，先安装
npm install -g pnpm
```

#### 3. 启动开发服务器
```bash
pnpm dev
```

前端服务启动后访问：http://localhost:5173

---

## 🎯 使用流程

### 1. 注册/登录
1. 访问 http://localhost:5173
2. 点击"注册"标签
3. 填写用户名、邮箱、密码
4. 注册成功后切换到"登录"标签登录

### 2. 创建分类模板
1. 进入"分类模板"页面
2. 点击"创建模板"
3. 填写模板名称和描述
4. 设计层级结构，例如：
   - 第1级：年份
   - 第2级：部门
   - 第3级：文档类型
5. 提交保存

### 3. 上传文档
1. 进入"文档管理"页面
2. 点击"上传文档"
3. 填写文档标题
4. 选择分类模板（可选）
5. 选择文件上传

### 4. 智能分类
1. 在文档列表中找到已上传的文档
2. 等待状态变为"已完成"
3. 点击"分类"按钮触发智能分类
4. 系统将自动为文档生成分类路径和编号

### 5. 文档检索
1. 进入"文档检索"页面
2. 输入关键词
3. 选择状态、日期范围等过滤条件
4. 点击"搜索"查看结果

---

## 🔑 默认账号

首次使用需要自行注册账号。建议创建管理员账号：

```bash
curl -X POST "http://localhost:8000/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "email": "admin@example.com",
    "password": "admin123",
    "role": "admin"
  }'
```

---

## 🐛 常见问题

### 1. 后端启动失败

**问题**: `ModuleNotFoundError: No module named 'xxx'`

**解决**: 
```bash
pip install -r requirements.txt
```

**问题**: 数据库连接失败

**解决**:
- 确认 PostgreSQL 已启动
- 检查 `.env` 中的 `DATABASE_URL` 配置
- 确认数据库已创建

### 2. 前端启动失败

**问题**: 依赖安装失败

**解决**:
```bash
# 清除缓存
pnpm store prune

# 重新安装
pnpm install
```

**问题**: API 请求失败

**解决**:
- 确认后端服务已启动
- 检查 `.env` 文件中的 `VITE_API_BASE_URL`
- 查看浏览器控制台错误信息

### 3. 文件上传失败

**问题**: MinIO 连接失败

**解决**:
- 确认 MinIO 已启动
- 检查 `.env` 中的 MinIO 配置
- 访问 http://localhost:9001 查看 MinIO 控制台

### 4. 智能分类不工作

**问题**: LLM API 调用失败

**解决**:
- 确认 `.env` 中配置了有效的 API Key
- 检查网络连接
- 查看后端日志错误信息

---

## 📦 生产环境部署

### 后端部署

参考 `backend/DEPLOYMENT.md` 文档，推荐使用 Docker Compose：

```bash
cd backend
docker-compose up -d
```

### 前端部署

```bash
cd frontend

# 构建
pnpm build

# 部署 dist 目录到 Nginx/Apache 等 Web 服务器
```

Nginx 配置示例：
```nginx
server {
    listen 80;
    server_name dochive.example.com;
    
    root /path/to/frontend/dist;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📚 更多文档

- **后端架构**: `backend/ARCHITECTURE.md`
- **后端部署**: `backend/DEPLOYMENT.md`
- **前端说明**: `frontend/README.md`
- **规格说明**: `docs/specification.md`

---

## 💡 提示

1. **开发环境**: 建议使用 VS Code，安装 Python、TypeScript、ESLint 等扩展
2. **调试**: 后端使用 `DEBUG=True`，前端查看浏览器控制台
3. **日志**: 后端日志在控制台输出，可配置文件日志
4. **性能**: 生产环境建议配置多个 Worker 进程和 Redis 缓存

---

**祝您使用愉快！** 🎉

如有问题，请查看详细文档或提交 Issue。
