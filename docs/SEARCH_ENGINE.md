# DocHive 搜索引擎配置指南

DocHive 支持多种搜索引擎后端,可根据环境需求灵活选择:

## 📋 支持的搜索引擎

| 搜索引擎               | 适用场景                 | 内存占用 | 性能 | 配置复杂度 |
| ---------------------- | ------------------------ | -------- | ---- | ---------- |
| **Database (原生FTS)** | 开发调试、小规模部署     | 低       | 中   | 低         |
| **Elasticsearch**      | 生产环境、大规模文档检索 | 高       | 高   | 中         |
| **ClickHouse**         | 海量数据、分析场景       | 中       | 极高 | 中         |

---

## 1️⃣ Database 原生全文检索 (推荐开发使用)

### 特点
- ✅ 无需额外服务,零依赖
- ✅ 配置简单,开箱即用
- ✅ 支持 PostgreSQL、MySQL、SQLite
- ⚠️ 大规模数据检索性能较弱

### 配置方法

#### PostgreSQL
```env
# .env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dochive
SEARCH_ENGINE=database
```

**特性**: 使用 GIN 索引 + `to_tsvector`/`plainto_tsquery`
```sql
-- 自动创建的索引
CREATE INDEX idx_documents_fulltext 
ON documents USING GIN (
    to_tsvector('simple', title || ' ' || COALESCE(content_text, ''))
);
```

#### MySQL
```env
# .env
DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/dochive
SEARCH_ENGINE=database
```

**特性**: 使用 FULLTEXT 索引 + `MATCH ... AGAINST`
```sql
-- 自动创建的索引
ALTER TABLE documents 
ADD FULLTEXT INDEX idx_documents_fulltext (title, content_text);
```

#### SQLite (最适合开发调试)
```env
# .env
DATABASE_URL=sqlite:///./dochive.db
SEARCH_ENGINE=database
```

**特性**: 使用 FTS5 虚拟表 + 触发器自动同步
```sql
-- 自动创建的虚拟表
CREATE VIRTUAL TABLE documents_fts 
USING fts5(document_id, title, content_text, content='documents');
```

### 初始化索引
```bash
cd backend
python scripts/init_search_index.py
```

---

## 2️⃣ Elasticsearch (推荐生产使用)

### 特点
- ✅ 强大的全文检索能力
- ✅ 支持中文分词 (ik_analyzer)
- ✅ 丰富的查询语法
- ⚠️ 内存占用高 (建议 2GB+)

### 安装 Elasticsearch

**使用 Docker (推荐)**:
```bash
docker run -d \
  --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
  docker.elastic.co/elasticsearch/elasticsearch:8.11.0
```

### 安装中文分词插件 (可选)
```bash
docker exec -it elasticsearch \
  elasticsearch-plugin install \
  https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v8.11.0/elasticsearch-analysis-ik-8.11.0.zip

docker restart elasticsearch
```

### 配置方法
```env
# .env
SEARCH_ENGINE=elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX=dochive_documents
```

### 索引映射
系统会自动创建以下索引:
```json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart"
      },
      "content": {
        "type": "text",
        "analyzer": "ik_max_word",
        "search_analyzer": "ik_smart"
      }
    }
  }
}
```

---

## 3️⃣ ClickHouse (适合海量数据)

### 特点
- ✅ 列式存储,压缩率高
- ✅ 适合日志分析、OLAP 场景
- ✅ 查询速度极快
- ⚠️ 全文检索能力较弱

### 安装 ClickHouse

**使用 Docker**:
```bash
docker run -d \
  --name clickhouse \
  -p 9000:9000 \
  -p 8123:8123 \
  --ulimit nofile=262144:262144 \
  clickhouse/clickhouse-server:latest
```

### 配置方法
```env
# .env
SEARCH_ENGINE=clickhouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=dochive
```

### 表结构
系统会自动创建以下表:
```sql
CREATE TABLE documents (
    document_id UInt32,
    title String,
    content String,
    upload_time DateTime
) ENGINE = MergeTree()
ORDER BY (upload_time, document_id);
```

---

## 🔧 切换搜索引擎

只需修改 `.env` 文件中的 `SEARCH_ENGINE` 配置:

```env
# 使用数据库原生检索
SEARCH_ENGINE=database

# 使用 Elasticsearch
SEARCH_ENGINE=elasticsearch

# 使用 ClickHouse
SEARCH_ENGINE=clickhouse
```

重启后端服务即可生效:
```bash
cd backend
uvicorn main:app --reload
```

---

## 📊 性能对比

### 测试环境
- 文档数量: 10,000 篇
- 平均文档大小: 2KB
- 查询关键词: "合同协议"

| 搜索引擎       | 索引时间 | 查询响应时间 | 内存占用 |
| -------------- | -------- | ------------ | -------- |
| SQLite FTS5    | 5s       | 150ms        | 50MB     |
| PostgreSQL GIN | 3s       | 80ms         | 100MB    |
| MySQL FULLTEXT | 4s       | 120ms        | 80MB     |
| Elasticsearch  | 10s      | 20ms         | 1GB      |
| ClickHouse     | 2s       | 15ms         | 200MB    |

---

## 💡 推荐配置

### 开发环境
```env
DATABASE_URL=sqlite:///./dochive.db
SEARCH_ENGINE=database
```
- 优点: 零配置,一键启动
- 缺点: 性能较弱

### 测试环境
```env
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/dochive
SEARCH_ENGINE=database
```
- 优点: 接近生产环境,性能适中
- 缺点: 需要安装 PostgreSQL

### 生产环境
```env
DATABASE_URL=postgresql+asyncpg://postgres:password@db-host:5432/dochive
SEARCH_ENGINE=elasticsearch
ELASTICSEARCH_URL=http://es-host:9200
```
- 优点: 性能最佳,功能强大
- 缺点: 需要维护额外服务

---

## 🔍 优雅降级机制

DocHive 实现了自动降级策略:

```python
# 如果 Elasticsearch 初始化失败,自动降级到数据库检索
if settings.SEARCH_ENGINE == 'elasticsearch':
    try:
        engine = ElasticsearchEngine()
    except:
        print("⚠️ ES 初始化失败,降级到数据库检索")
        engine = DatabaseEngine()
```

即使配置了外部搜索引擎,系统也能保证基本功能可用。

---

## ❓ 常见问题

### 1. SQLite 全文检索不支持中文?
SQLite FTS5 默认使用 `unicode61` tokenizer,支持基础中文分词。如需更好的中文支持,建议使用 PostgreSQL 或 Elasticsearch。

### 2. MySQL FULLTEXT 索引创建失败?
确保表引擎为 `InnoDB`,且字段为 `TEXT` 或 `VARCHAR` 类型:
```sql
ALTER TABLE documents ENGINE=InnoDB;
```

### 3. Elasticsearch 启动报错 `max virtual memory areas`?
```bash
# Linux 系统需要调整内核参数
sudo sysctl -w vm.max_map_count=262144
```

### 4. 如何验证搜索引擎是否正常工作?
```bash
# 查看启动日志
cd backend
uvicorn main:app --log-level debug

# 应该看到:
# ✅ 搜索引擎: DATABASE (PostgreSQL/MySQL/SQLite)
# 或
# ✅ 搜索引擎: ELASTICSEARCH
```

---

## 📚 相关文档
- [PostgreSQL 全文检索官方文档](https://www.postgresql.org/docs/current/textsearch.html)
- [MySQL FULLTEXT 索引](https://dev.mysql.com/doc/refman/8.0/en/fulltext-search.html)
- [SQLite FTS5 文档](https://www.sqlite.org/fts5.html)
- [Elasticsearch 中文分词](https://github.com/medcl/elasticsearch-analysis-ik)
- [ClickHouse 全文检索](https://clickhouse.com/docs/en/sql-reference/functions/string-search-functions)
