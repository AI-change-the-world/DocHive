# 部署指南

## 环境要求

- Docker 20.10+
- Docker Compose 1.29+
- 至少 4GB 内存

## 快速部署

### 使用 Docker Compose (推荐)

1. 克隆项目代码:
```bash
git clone https://github.com/your-username/DocHive.git
cd DocHive
```

2. 进入 docker 目录:
```bash
cd docker
```

3. 启动所有服务:
```bash
docker-compose up -d
```

4. 等待服务启动完成，访问以下地址:
   - 前端界面: http://localhost:3000
   - 后端API: http://localhost:8000
   - MinIO 控制台: http://localhost:9001
   - Elasticsearch: http://localhost:9200

### 服务端口说明

| 服务          | 端口      | 说明             |
| ------------- | --------- | ---------------- |
| Frontend      | 3000      | React 前端应用   |
| Backend       | 8000      | FastAPI 后端服务 |
| MinIO         | 9000/9001 | 对象存储服务/API |
| Elasticsearch | 9200      | 搜索引擎         |
| Nacos         | 8848      | 配置中心         |

## 配置说明

### 环境变量

在 `docker/.env` 文件中配置以下环境变量:

```env
MINIO_ROOT_PASSWORD=M6tz2TdDzT0m  # MinIO 密码
ES_JAVA_OPTS=-Xms1024m -Xmx1024m  # Elasticsearch JVM 参数
MINIO_ROOT_USER=admin             # MinIO 用户名
ELASTIC_PASSWORD=admin123         # Elasticsearch 密码
```

### Nacos 配置

系统使用 Nacos 作为配置中心，配置文件位于 `backend/config/nacos-config.yaml`。

## 初始化操作

### 数据库初始化

首次启动时，系统会自动创建数据库表结构。

### 搜索引擎索引初始化

运行以下命令初始化 Elasticsearch 索引:

```bash
cd backend
python scripts/init_search_index.py
```

## 生产环境部署

### 数据库配置

生产环境建议使用 PostgreSQL 或 MySQL 替代默认的 SQLite。

在 Nacos 配置中心修改数据库连接配置:

```yaml
database:
  url: "postgresql://user:password@host:port/database"
```

### 域名配置

配置域名和 SSL 证书，确保服务安全访问。

### 监控和日志

建议配置 Prometheus 和 Grafana 进行系统监控，使用 ELK 或类似方案进行日志收集和分析。

## 故障排除

### 服务无法启动

1. 检查端口是否被占用
2. 查看容器日志: `docker-compose logs service-name`
3. 确认环境变量配置正确

### 数据库连接失败

1. 检查数据库服务是否正常运行
2. 确认数据库连接字符串配置正确
3. 验证网络连通性

### 搜索功能异常

1. 检查 Elasticsearch 服务状态
2. 确认索引已正确初始化
3. 查看后端日志中的错误信息