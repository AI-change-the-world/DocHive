# DocHive 后端部署指南

## 生产环境部署

### 方式一：使用 Docker（推荐）

#### 1. 创建 Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 2. 创建 docker-compose.yml

```yaml
version: '3.8'

services:
  # PostgreSQL 数据库
  postgres:
    image: postgres:14
    environment:
      POSTGRES_DB: dochive
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # Redis
  redis:
    image: redis:6-alpine
    ports:
      - "6379:6379"

  # MinIO 对象存储
  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  # Elasticsearch (可选)
  elasticsearch:
    image: elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - es_data:/usr/share/elasticsearch/data
    ports:
      - "9200:9200"

  # DocHive 后端
  backend:
    build: .
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:password@postgres:5432/dochive
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      ELASTICSEARCH_URL: http://elasticsearch:9200
      # 其他环境变量从 .env 文件加载
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
      - minio
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs

volumes:
  postgres_data:
  minio_data:
  es_data:
```

#### 3. 启动服务

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 停止服务
docker-compose down
```

### 方式二：直接部署

#### 1. 准备环境

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

#### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填写生产环境配置
```

#### 3. 初始化数据库

```bash
alembic upgrade head
```

#### 4. 使用 Supervisor 管理进程

创建 `/etc/supervisor/conf.d/dochive.conf`：

```ini
[program:dochive]
directory=/path/to/DocHive/backend
command=/path/to/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
user=www-data
autostart=true
autorestart=true
stdout_logfile=/var/log/dochive/access.log
stderr_logfile=/var/log/dochive/error.log
```

启动服务：

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start dochive
```

#### 5. 配置 Nginx 反向代理

创建 `/etc/nginx/sites-available/dochive`：

```nginx
server {
    listen 80;
    server_name api.dochive.example.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

启用站点：

```bash
sudo ln -s /etc/nginx/sites-available/dochive /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 方式三：使用 Gunicorn + Uvicorn Workers

```bash
# 安装 Gunicorn
pip install gunicorn

# 启动（推荐生产环境）
gunicorn main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile /var/log/dochive/access.log \
  --error-logfile /var/log/dochive/error.log
```

## 性能优化

### 1. 数据库连接池

在 `config.py` 中调整：

```python
DATABASE_POOL_SIZE = 50
DATABASE_MAX_OVERFLOW = 20
```

### 2. Redis 缓存

可以添加 Redis 缓存层来缓存热点数据。

### 3. Celery 异步任务

对于耗时操作（文档解析、分类、抽取），建议使用 Celery：

```bash
# 启动 Celery Worker
celery -A tasks worker --loglevel=info

# 启动 Celery Beat（定时任务）
celery -A tasks beat --loglevel=info
```

### 4. CDN 加速

静态资源和文件下载建议使用 CDN。

## 监控与日志

### 1. 日志收集

使用 Loguru 或集成 ELK Stack。

### 2. 性能监控

- 使用 Prometheus + Grafana
- 集成 Sentry 错误追踪

### 3. 健康检查

```bash
curl http://localhost:8000/health
```

## 备份策略

### 1. 数据库备份

```bash
# 备份
pg_dump -U postgres dochive > backup_$(date +%Y%m%d).sql

# 恢复
psql -U postgres dochive < backup_20251021.sql
```

### 2. MinIO 数据备份

```bash
mc mirror minio/dochive-documents /backup/minio/
```

## 安全加固

1. **启用 HTTPS**
2. **配置防火墙规则**
3. **定期更新依赖**
4. **限制 API 访问速率**
5. **启用日志审计**

## 扩展性

### 水平扩展

- 多个后端实例 + 负载均衡
- 使用 Redis 共享会话
- 分离读写数据库

### 垂直扩展

- 增加服务器配置
- 优化数据库查询
- 使用缓存

---

部署完成后，访问 API 文档：http://your-domain/docs
