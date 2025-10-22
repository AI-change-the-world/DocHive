# 📊 DocHive 后端架构总览

## 🎯 项目完成情况

✅ **所有核心模块已实现**

### 已实现的功能模块

#### 1️⃣ 分类模板管理模块 (`api/v1/templates.py`)
- ✅ 创建/更新/删除分类模板
- ✅ 支持无限层级定义
- ✅ 模板版本管理
- ✅ 模板列表查询与分页

**核心文件：**
- 服务层: `services/template_service.py`
- 数据模型: `models/database_models.py` (ClassTemplate)
- API 路由: `api/v1/templates.py`

#### 2️⃣ 文档上传与解析模块 (`api/v1/documents.py`)
- ✅ 多格式文件上传 (PDF, DOCX, TXT, MD, 图片)
- ✅ 文档内容自动解析
- ✅ OCR 图片识别支持
- ✅ 元信息自动提取
- ✅ MinIO 对象存储集成
- ✅ 文档下载链接生成

**核心文件：**
- 服务层: `services/document_service.py`
- 解析工具: `utils/parser.py`
- 存储客户端: `utils/storage.py`
- API 路由: `api/v1/documents.py`

#### 3️⃣ 智能分类引擎模块 (`api/v1/classification.py`)
- ✅ 基于 LLM 的文档智能分类
- ✅ 自动匹配分类模板
- ✅ 批量分类支持
- ✅ 强制重新分类功能
- ✅ OpenAI/DeepSeek 多模型支持

**核心文件：**
- 服务层: `services/classification_service.py`
- LLM 客户端: `utils/llm_client.py`
- API 路由: `api/v1/classification.py`

#### 4️⃣ 信息抽取引擎模块 (`api/v1/extraction.py`)
- ✅ 正则表达式抽取
- ✅ LLM 智能抽取
- ✅ 自定义抽取配置
- ✅ 多字段类型支持（文本、数字、数组、日期）
- ✅ 抽取结果结构化存储

**核心文件：**
- 服务层: `services/extraction_service.py`
- 数据模型: `models/database_models.py` (ExtractionConfig)
- API 路由: `api/v1/extraction.py`

#### 5️⃣ 编号与索引模块 (`api/v1/numbering.py`)
- ✅ 自动生成唯一文档编号
- ✅ 可配置编号格式
- ✅ 序列号自动递增
- ✅ 支持变量替换
- ✅ 编号规则管理

**核心文件：**
- 服务层: `services/numbering_service.py`
- 数据模型: `models/database_models.py` (NumberingRule)
- API 路由: `api/v1/numbering.py`

#### 6️⃣ 文档检索与管理模块 (`api/v1/search.py`)
- ✅ Elasticsearch 全文检索
- ✅ 多维度过滤（分类、时间、状态）
- ✅ 分页查询
- ✅ 统计分析
- ✅ 文档索引管理

**核心文件：**
- 服务层: `services/search_service.py`
- 搜索客户端: `utils/search_client.py`
- API 路由: `api/v1/search.py`

#### 7️⃣ 系统配置与权限模块 (`api/v1/auth.py`, `api/v1/config.py`)
- ✅ 用户注册/登录
- ✅ JWT 认证
- ✅ 基于角色的访问控制 (RBAC)
- ✅ 权限依赖注入
- ✅ 系统配置管理

**核心文件：**
- 认证服务: `services/auth_service.py`
- 配置服务: `services/config_service.py`
- 安全工具: `utils/security.py`
- 依赖注入: `api/deps.py`
- API 路由: `api/v1/auth.py`, `api/v1/config.py`

---

## 📁 完整文件清单

### 配置与入口
- ✅ `main.py` - FastAPI 应用入口
- ✅ `config.py` - 配置管理
- ✅ `database.py` - 数据库连接
- ✅ `requirements.txt` - 依赖包
- ✅ `.env.example` - 环境变量模板
- ✅ `run.py` - 启动脚本
- ✅ `alembic.ini` - 数据库迁移配置

### 数据层
```
models/
├── __init__.py
└── database_models.py          # 8个数据模型
    ├── User                    # 用户
    ├── ClassTemplate           # 分类模板
    ├── NumberingRule           # 编号规则
    ├── Document                # 文档
    ├── ExtractionConfig        # 抽取配置
    ├── DocumentExtractionMapping  # 文档-抽取映射
    ├── OperationLog            # 操作日志
    └── SystemConfig            # 系统配置
```

### 模式层
```
schemas/
├── __init__.py
└── api_schemas.py              # 30+ Pydantic 模型
    ├── 用户相关 (User*, Token, Login)
    ├── 模板相关 (ClassTemplate*, TemplateLevel)
    ├── 文档相关 (Document*, DocumentSearch)
    ├── 抽取相关 (ExtractionConfig*, ExtractionField)
    ├── 分类相关 (Classification*)
    ├── 编号相关 (NumberingRule*)
    └── 配置相关 (SystemConfig*)
```

### 服务层
```
services/
├── __init__.py
├── auth_service.py             # 认证服务
├── template_service.py         # 模板服务
├── document_service.py         # 文档服务
├── classification_service.py   # 分类服务
├── extraction_service.py       # 抽取服务
├── numbering_service.py        # 编号服务
├── search_service.py           # 检索服务
└── config_service.py           # 配置服务
```

### API 路由层
```
api/
├── __init__.py
├── deps.py                     # 依赖注入（认证、权限）
├── router.py                   # 路由汇总
└── v1/
    ├── __init__.py
    ├── auth.py                 # 认证接口
    ├── templates.py            # 模板接口
    ├── documents.py            # 文档接口
    ├── classification.py       # 分类接口
    ├── extraction.py           # 抽取接口
    ├── numbering.py            # 编号接口
    ├── search.py               # 检索接口
    └── config.py               # 配置接口
```

### 工具层
```
utils/
├── __init__.py
├── security.py                 # JWT、密码加密
├── storage.py                  # MinIO 客户端
├── parser.py                   # 文档解析器
├── llm_client.py              # LLM 客户端
└── search_client.py           # Elasticsearch 客户端
```

### 文档
- ✅ `README.md` - 项目说明
- ✅ `DEPLOYMENT.md` - 部署指南
- ✅ `.gitignore` - Git 忽略配置

---

## 🔌 API 端点总览

### 认证模块 (`/api/v1/auth`)
| 方法 | 端点        | 说明             |
| ---- | ----------- | ---------------- |
| POST | `/register` | 用户注册         |
| POST | `/login`    | 用户登录         |
| GET  | `/me`       | 获取当前用户信息 |
| POST | `/refresh`  | 刷新令牌         |

### 分类模板 (`/api/v1/templates`)
| 方法   | 端点             | 说明         |
| ------ | ---------------- | ------------ |
| POST   | `/`              | 创建模板     |
| GET    | `/`              | 获取模板列表 |
| GET    | `/{template_id}` | 获取模板详情 |
| PUT    | `/{template_id}` | 更新模板     |
| DELETE | `/{template_id}` | 删除模板     |

### 文档管理 (`/api/v1/documents`)
| 方法   | 端点                      | 说明         |
| ------ | ------------------------- | ------------ |
| POST   | `/upload`                 | 上传文档     |
| GET    | `/`                       | 获取文档列表 |
| GET    | `/{document_id}`          | 获取文档详情 |
| PUT    | `/{document_id}`          | 更新文档     |
| DELETE | `/{document_id}`          | 删除文档     |
| GET    | `/{document_id}/download` | 获取下载链接 |

### 智能分类 (`/api/v1/classification`)
| 方法 | 端点              | 说明         |
| ---- | ----------------- | ------------ |
| POST | `/classify`       | 分类单个文档 |
| POST | `/classify-batch` | 批量分类     |

### 信息抽取 (`/api/v1/extraction`)
| 方法 | 端点                   | 说明             |
| ---- | ---------------------- | ---------------- |
| POST | `/extract`             | 抽取文档信息     |
| GET  | `/configs`             | 获取抽取配置列表 |
| POST | `/configs`             | 创建抽取配置     |
| GET  | `/configs/{config_id}` | 获取配置详情     |

### 编号管理 (`/api/v1/numbering`)
| 方法 | 端点                            | 说明             |
| ---- | ------------------------------- | ---------------- |
| POST | `/generate/{document_id}`       | 生成文档编号     |
| POST | `/rules`                        | 创建编号规则     |
| GET  | `/rules/template/{template_id}` | 获取模板编号规则 |
| POST | `/rules/{rule_id}/reset`        | 重置序列号       |

### 文档检索 (`/api/v1/search`)
| 方法 | 端点                   | 说明         |
| ---- | ---------------------- | ------------ |
| POST | `/`                    | 多维度检索   |
| GET  | `/statistics`          | 获取统计信息 |
| POST | `/index/{document_id}` | 索引文档     |

### 系统配置 (`/api/v1/config`)
| 方法   | 端点            | 说明         |
| ------ | --------------- | ------------ |
| GET    | `/`             | 获取配置列表 |
| GET    | `/{config_key}` | 获取配置     |
| POST   | `/`             | 创建配置     |
| PUT    | `/{config_key}` | 更新配置     |
| DELETE | `/{config_key}` | 删除配置     |

---

## 🏛️ 架构设计亮点

### 1. 微服务化设计
- **分层架构**: API → Service → Model
- **模块解耦**: 每个功能模块独立
- **易于扩展**: 添加新功能只需扩展对应层

### 2. 异步架构
- 全面使用 `async/await`
- 异步数据库操作 (asyncpg)
- 异步 HTTP 请求 (httpx)
- 支持高并发

### 3. 依赖注入
- FastAPI Depends 机制
- 统一的认证和权限控制
- 数据库会话管理

### 4. 类型安全
- Pydantic 模型验证
- SQLAlchemy ORM 类型提示
- 完整的类型注解

### 5. 可扩展性
- 支持多种 LLM 提供商
- 插件化的抽取方法
- 灵活的配置系统

---

## 🔧 技术栈汇总

| 类型       | 技术                    | 用途             |
| ---------- | ----------------------- | ---------------- |
| Web 框架   | FastAPI 0.109           | API 服务         |
| 数据库     | PostgreSQL + SQLAlchemy | 数据持久化       |
| 对象存储   | MinIO                   | 文件存储         |
| 搜索引擎   | Elasticsearch           | 全文检索         |
| 向量数据库 | Qdrant                  | 向量检索（预留） |
| 缓存       | Redis                   | 会话/缓存        |
| 任务队列   | Celery                  | 异步任务         |
| LLM        | OpenAI/DeepSeek         | 智能分类/抽取    |
| 认证       | JWT                     | 用户认证         |
| 文档解析   | PyPDF2, python-docx     | 文件解析         |
| OCR        | Tesseract               | 图片识别         |

---

## 🚀 快速启动

```bash
# 1. 安装依赖
cd backend
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
# 编辑 .env 文件

# 3. 启动服务
python run.py

# 4. 访问文档
# http://localhost:8000/docs
```

---

## 📈 未来扩展方向

1. **知识图谱**: 文档关系自动提取
2. **向量检索**: 基于 Qdrant 的语义搜索
3. **自动学习**: 分类结果反馈优化
4. **工作流引擎**: 文档审批流程
5. **多语言支持**: 国际化
6. **移动端 API**: 移动应用支持

---

## ✨ 总结

完整实现了 DocHive 智能文档分类分级系统的所有后端功能模块，包括：

✅ 7 大核心功能模块  
✅ 8 个数据模型  
✅ 30+ API 端点  
✅ 完整的认证和权限系统  
✅ 智能分类和信息抽取  
✅ 全文检索和多维度过滤  
✅ 自动编号和索引管理  
✅ 完善的文档和部署指南  

代码结构清晰、模块解耦、易于维护和扩展，符合微服务化设计理念和前后端分离架构要求。
