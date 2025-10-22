# DocHive 功能特性总览

## 🎯 核心特性

### 1. 多搜索引擎灵活配置 ⭐⭐⭐⭐⭐

```
┌─────────────────────────────────────────────────────────┐
│  开发环境                                                  │
│  ┌──────────────┐                                        │
│  │   SQLite     │  内存: ~50MB   查询: 150ms             │
│  │      +       │  配置: 零配置                           │
│  │ Database FTS │  场景: 开发调试                         │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  生产环境                                                  │
│  ┌──────────────┐                                        │
│  │ PostgreSQL   │  内存: ~1GB    查询: 20ms              │
│  │      +       │  配置: 中等                             │
│  │Elasticsearch │  场景: 大规模生产                       │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  海量数据                                                  │
│  ┌──────────────┐                                        │
│  │ PostgreSQL   │  内存: ~200MB  查询: 15ms              │
│  │      +       │  配置: 中等                             │
│  │ ClickHouse   │  场景: 数据分析                         │
│  └──────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

### 2. 智能文档分类流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ 上传文档 │ --> │ 解析内容 │ --> │ LLM分类 │ --> │ 生成编号 │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
     │               │               │               │
     v               v               v               v
  支持格式         OCR识别        智能匹配        自动索引
PDF/DOCX        图片文字        分类模板        唯一编号
TXT/MD          表格数据        层级路径        检索优化
```

### 3. 全文检索技术对比

```
PostgreSQL GIN 索引
┌────────────────────────────────────────────┐
│ CREATE INDEX USING GIN                      │
│   (to_tsvector('simple', title || content))│
│                                             │
│ 查询: to_tsvector @@ plainto_tsquery       │
│ 性能: ★★★★☆                                │
│ 中文: 需要 pg_jieba                         │
└────────────────────────────────────────────┘

MySQL FULLTEXT 索引
┌────────────────────────────────────────────┐
│ ALTER TABLE ADD FULLTEXT INDEX             │
│   (title, content_text)                    │
│                                             │
│ 查询: MATCH AGAINST                         │
│ 性能: ★★★☆☆                                │
│ 中文: 需要 ngram parser                     │
└────────────────────────────────────────────┘

SQLite FTS5
┌────────────────────────────────────────────┐
│ CREATE VIRTUAL TABLE USING fts5            │
│   (title, content_text)                    │
│                                             │
│ 查询: WHERE fts MATCH 'keyword'            │
│ 性能: ★★★☆☆                                │
│ 中文: porter unicode61                      │
└────────────────────────────────────────────┘

Elasticsearch
┌────────────────────────────────────────────┐
│ PUT /index { mappings: { ... } }           │
│   analyzer: ik_max_word                     │
│                                             │
│ 查询: multi_match                           │
│ 性能: ★★★★★                                │
│ 中文: ik_analyzer 完美支持                  │
└────────────────────────────────────────────┘
```

---

## 📊 性能对比矩阵

### 内存占用

```
           0MB    250MB   500MB   750MB   1GB
SQLite     |███|
PostgreSQL      |██████|
MySQL           |█████|
ClickHouse            |████████|
Elasticsearch                        |████████████████|
```

### 查询速度 (10K 文档)

```
           0ms    50ms    100ms   150ms   200ms
Elasticsearch |████|
ClickHouse       |██████|
PostgreSQL             |████████████|
MySQL                         |█████████████████|
SQLite                              |████████████████████|
```

### 配置复杂度

```
           简单            中等            复杂
SQLite     |████████████|
PostgreSQL      |████████████████|
MySQL           |████████████████|
ClickHouse                 |████████████████████|
Elasticsearch              |████████████████████|
```

---

## 🔄 搜索引擎切换

### 一行配置切换

```env
# 开发环境 - 零配置
SEARCH_ENGINE=database
DATABASE_URL=sqlite:///./dochive.db

# 测试环境 - 中等配置
SEARCH_ENGINE=database
DATABASE_URL=postgresql+asyncpg://localhost:5432/dochive

# 生产环境 - 高性能
SEARCH_ENGINE=elasticsearch
DATABASE_URL=postgresql+asyncpg://prod-host:5432/dochive
ELASTICSEARCH_URL=http://es-host:9200
```

### 优雅降级

```
用户配置: Elasticsearch
          ↓
系统尝试: 初始化 ES 连接
          ↓
      ┌───┴───┐
      │成功?   │
      └───┬───┘
  成功 ↙     ↘ 失败
使用 ES      降级到 Database
          ↓
    系统正常运行 ✓
```

---

## 🛠️ 工具链

### 配置向导流程

```
启动配置向导
     ↓
┌─────────────────┐
│ 选择搜索引擎     │
│ [1] Database    │
│ [2] Elasticsearch│
│ [3] ClickHouse  │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 配置数据库连接   │
│ - SQLite        │
│ - PostgreSQL    │
│ - MySQL         │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 自动更新 .env   │
│ ✓ 写入配置      │
└────────┬────────┘
         ↓
┌─────────────────┐
│ 初始化索引      │
│ ✓ 创建索引      │
└────────┬────────┘
         ↓
      配置完成 ✓
```

### 一键启动流程

```
运行 quick_start.bat/sh
         ↓
┌──────────────────┐
│ 检查 Python 环境  │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ 安装/检查依赖     │
│ pip install ...  │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ 创建默认配置      │
│ SQLite + DB FTS  │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ 初始化搜索索引    │
│ init_search_...  │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ 检查必要服务      │
│ Redis / MinIO    │
└────────┬─────────┘
         ↓
┌──────────────────┐
│ 启动后端服务      │
│ python main.py   │
└────────┬─────────┘
         ↓
   服务就绪 ✓
 http://localhost:8000
```

---

## 📦 部署架构

### 开发环境 (最小化)

```
┌─────────────────────────────────────┐
│          开发机器                    │
│  ┌──────────────────────────────┐  │
│  │      DocHive Backend         │  │
│  │   (SQLite + Database FTS)    │  │
│  └──────────────────────────────┘  │
│                                      │
│  ┌─────────┐    ┌─────────┐        │
│  │  Redis  │    │  MinIO  │        │
│  └─────────┘    └─────────┘        │
│                                      │
│  内存占用: ~100MB                    │
└─────────────────────────────────────┘
```

### 生产环境 (高性能)

```
┌─────────────────────────────────────────────┐
│              生产服务器集群                   │
│                                              │
│  ┌────────────────┐    ┌────────────────┐  │
│  │   Backend x3   │    │  PostgreSQL    │  │
│  │   (FastAPI)    │----│   (主从复制)    │  │
│  └────────────────┘    └────────────────┘  │
│          │                                   │
│          │             ┌────────────────┐  │
│          └────────────│ Elasticsearch  │  │
│                        │   (集群模式)    │  │
│                        └────────────────┘  │
│                                              │
│  ┌─────────┐    ┌─────────┐    ┌────────┐ │
│  │  Redis  │    │  MinIO  │    │ Nginx  │ │
│  │ (哨兵)   │    │ (分布式) │    │ (LB)   │ │
│  └─────────┘    └─────────┘    └────────┘ │
│                                              │
│  内存占用: ~4GB                              │
└─────────────────────────────────────────────┘
```

---

## 🎓 技术实现

### 数据库原生全文检索实现

```python
# PostgreSQL
async def search_postgresql(keyword):
    query = text("""
        SELECT * FROM documents 
        WHERE to_tsvector('simple', title || ' ' || content_text)
              @@ plainto_tsquery('simple', :keyword)
    """)
    return await session.execute(query, {"keyword": keyword})

# MySQL
async def search_mysql(keyword):
    query = text("""
        SELECT * FROM documents 
        WHERE MATCH(title, content_text) 
              AGAINST(:keyword IN NATURAL LANGUAGE MODE)
    """)
    return await session.execute(query, {"keyword": keyword})

# SQLite
async def search_sqlite(keyword):
    query = text("""
        SELECT * FROM documents 
        WHERE id IN (
            SELECT rowid FROM documents_fts 
            WHERE documents_fts MATCH :keyword
        )
    """)
    return await session.execute(query, {"keyword": keyword})
```

### 搜索引擎工厂模式

```python
class BaseSearchEngine(ABC):
    @abstractmethod
    async def search_documents(...): pass

class DatabaseEngine(BaseSearchEngine):
    # PostgreSQL/MySQL/SQLite FTS

class ElasticsearchEngine(BaseSearchEngine):
    # ES with ik_analyzer

class ClickHouseEngine(BaseSearchEngine):
    # ClickHouse MergeTree

def get_search_engine() -> BaseSearchEngine:
    if settings.SEARCH_ENGINE == 'elasticsearch':
        return ElasticsearchEngine()
    elif settings.SEARCH_ENGINE == 'clickhouse':
        return ClickHouseEngine()
    else:
        return DatabaseEngine()
```

---

## 🎯 使用场景

### 场景 1: 个人开发者

**需求**: 快速搭建,零配置  
**配置**: SQLite + Database FTS  
**启动**: `quick_start.bat`  
**内存**: ~50MB

### 场景 2: 小型团队

**需求**: 中小规模,稳定可靠  
**配置**: PostgreSQL + Database FTS  
**部署**: Docker Compose  
**内存**: ~100MB

### 场景 3: 企业生产

**需求**: 大规模,高性能  
**配置**: PostgreSQL + Elasticsearch  
**部署**: Kubernetes  
**内存**: ~1GB

### 场景 4: 数据分析

**需求**: 海量数据,快速查询  
**配置**: PostgreSQL + ClickHouse  
**部署**: 分布式集群  
**内存**: ~200MB

---

## 📈 性能优化建议

### 开发阶段
```
✓ 使用 SQLite
✓ Database FTS
✓ 单机部署
✓ 内存 < 100MB
```

### 测试阶段
```
✓ 使用 PostgreSQL
✓ Database FTS
✓ Docker 部署
✓ 内存 ~100MB
```

### 生产阶段
```
✓ 使用 PostgreSQL
✓ Elasticsearch
✓ 集群部署
✓ 内存 ~1GB
✓ 启用缓存
```

---

**更新时间**: 2025-10-22  
**文档版本**: v1.1.0
