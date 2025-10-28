# DocHive - 智能文档分类分级系统

> 基于大语言模型的智能文档管理平台

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/react-18.3-blue.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.109-green.svg)](https://fastapi.tiangolo.com/)

---

## 📋 项目简介

DocHive 是一个智能文档分类分级系统,通过大语言模型实现文档的自动分类、信息抽取、智能编号和全文检索。

### 核心思路

传统的 **RAG（Retrieval-Augmented Generation）** 实际上是一个相对粗糙的概念。
在实践中，绝大多数文档类型（例如简历、报告、合同等）并不适合直接采用传统 RAG 进行处理。
即便后续出现的 **GraphRAG** 等变体引入了“实体–关系”图的概念，也仅仅是在知识组织层面进行了扩展。
对于缺乏显性实体的文档类型（如政策法规、技术规范、制度文件等），这些方法仍然难以解决检索性能差、上下文关联弱的问题。

在 2025 年 4 月，我提出过一个设想：
**将所有非结构化文档转化为结构化数据进行处理。**
理由是：几乎所有类型的文档都围绕某种“关注对象”展开。
只要能够准确抽取并索引这些关注信息，就可以在检索阶段快速锁定相关内容，从而显著提升 RAG 的准确性与响应效率。

接下来，我计划将这一“文档结构化”思路与 **分类分级体系** 相结合，
以“结构化（或半结构化）文档”为核心，使文档具备更强的 **可比性** 与 **可检索性**。
这不仅能优化 RAG 的信息召回效果，也为构建可解释、可控的知识语义体系奠定基础。

### 核心功能

- 🏷️ **自定义分类模板** - 支持多级分类层级设计
- 📄 **文档上传解析** - 支持 PDF、DOCX、TXT、Markdown 等多种格式
- 🤖 **智能分类引擎** - 基于 LLM 的文档自动分类
- 🔍 **信息抽取引擎** - 智能提取关键字段和结构化数据
- 🔢 **自动编号管理** - 规则化编号生成与索引
- 🔎 **多维度检索** - 支持全文检索、分类筛选、时间范围等
- 👥 **权限管理** - 基于角色的访问控制


## 🏗️ 技术栈

### 后端
- **框架**: FastAPI 0.109
- **数据库**: PostgreSQL / MySQL / **SQLite** (新增)
- **搜索引擎**: Database FTS / Elasticsearch（推荐，支持复杂的查询逻辑） / ClickHouse (可配置)
- **对象存储**: MinIO
- **LLM**: OpenAI / DeepSeek
- **任务队列**: Celery + Redis

### 前端
- **框架**: React 18.3 + TypeScript 5.9
- **UI 库**: Ant Design 5.27
- **路由**: React Router DOM 7.9
- **状态管理**: Zustand 4.5
- **构建工具**: Vite 7.1

---

## 🚀 快速开始

### 最简单的启动方式 (推荐开发使用)

**Windows**:
```bash
cd backend
quick_start.bat
```

**Linux/Mac**:
```bash
cd backend
chmod +x quick_start.sh
./quick_start.sh
```

一键完成:
- ✅ 检查环境
- ✅ 安装依赖
- ✅ 创建配置 (SQLite + Database FTS)
- ✅ 初始化索引
- ✅ 启动服务

### 详细启动步骤

参考 [快速启动指南](QUICK_START.md)

---

## 📁 项目结构

```
DocHive/
├── backend/                # 后端服务
│   ├── api/               # API 路由层
│   ├── models/            # 数据模型
│   ├── services/          # 业务逻辑
│   ├── utils/             # 工具模块
│   │   └── search_engine.py  # 多搜索引擎支持 (新增)
│   ├── scripts/           # 工具脚本
│   │   ├── init_search_index.py   # 索引初始化 (新增)
│   │   └── test_search_engine.py  # 功能测试 (新增)
│   ├── configure_search.bat/sh   # 配置向导 (新增)
│   ├── quick_start.bat/sh        # 一键启动 (新增)
│   └── docs/              # 文档
│       └── SEARCH_ENGINE.md      # 搜索引擎配置指南 (新增)
│
├── frontend/              # 前端应用
│   ├── src/
│   │   ├── pages/        # 页面组件
│   │   ├── components/   # 通用组件
│   │   ├── services/     # API 服务
│   │   └── types/        # TypeScript 类型
│   └── ...
│
├── docs/                  # 项目文档
├── QUICK_START.md         # 快速启动指南
├── README_SEARCH_ENGINE.md  # 搜索引擎更新说明 (新增)
└── UPDATE_SUMMARY.md      # 完整更新清单 (新增)
```

---

## 🎯 配置选项

### 数据库选择

| 数据库     | 适用场景 | 配置                                    |
| ---------- | -------- | --------------------------------------- |
| **SQLite** | 开发调试 | `DATABASE_URL=sqlite:///./dochive.db`   |
| PostgreSQL | 生产环境 | `DATABASE_URL=postgresql+asyncpg://...` |
| MySQL      | 单机部署 | `DATABASE_URL=mysql+aiomysql://...`     |

### 搜索引擎选择

| 搜索引擎         | 适用场景      | 内存占用 | 配置                          |
| ---------------- | ------------- | -------- | ----------------------------- |
| **Database FTS** | 开发/中小规模 | ~50MB    | `SEARCH_ENGINE=database`      |
| Elasticsearch    | 生产/大规模   | ~1GB     | `SEARCH_ENGINE=elasticsearch` |
| ClickHouse       | 海量数据      | ~200MB   | `SEARCH_ENGINE=clickhouse`    |

### 推荐配置

**开发环境** (零配置):
```env
DATABASE_URL=sqlite:///./dochive.db
SEARCH_ENGINE=database
```

**生产环境** (高性能):
```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/dochive
SEARCH_ENGINE=elasticsearch
ELASTICSEARCH_URL=http://es-host:9200
```

📚 详细配置指南: [backend/docs/SEARCH_ENGINE.md](backend/docs/SEARCH_ENGINE.md)

---

## 🔧 配置向导

使用交互式配置向导快速配置搜索引擎:

```bash
cd backend

# Windows
configure_search.bat

# Linux/Mac
chmod +x configure_search.sh
./configure_search.sh
```

向导功能:
1. ✅ 选择搜索引擎类型
2. ✅ 配置数据库连接
3. ✅ 自动更新 `.env`
4. ✅ 初始化搜索索引

---

## 📖 文档

| 文档                                                           | 描述             |
| -------------------------------------------------------------- | ---------------- |
| [QUICK_START.md](./docs/QUICK_START.md)                        | 快速启动指南     |
| [README_SEARCH_ENGINE.md](./docs/README_SEARCH_ENGINE.md)      | 搜索引擎更新说明 |
| [UPDATE_SUMMARY.md](./docs/UPDATE_SUMMARY.md)                  | 完整更新清单     |
| [backend/README.md](backend/README.md)                         | 后端项目说明     |
| [backend/docs/SEARCH_ENGINE.md](backend/docs/SEARCH_ENGINE.md) | 搜索引擎配置指南 |
| [frontend/README.md](frontend/README.md)                       | 前端项目说明     |
| [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md)             | 后端架构说明     |
| [backend/DEPLOYMENT.md](backend/DEPLOYMENT.md)                 | 部署指南         |

---

## 🎨 功能预览

### 1. 分类模板管理
- 创建多级分类模板
- 可视化层级设计
- 模板版本管理

### 2. 文档管理
- 批量上传文档
- 多格式解析 (PDF/DOCX/TXT/MD)
- 文档预览与下载

### 3. 智能分类
- 自动分类文档
- 人工校正分类
- 分类结果可视化

### 4. 信息抽取
- 关键字段自动提取
- 结构化数据展示
- 自定义抽取规则

### 5. 文档检索
- 全文关键词搜索
- 多维度筛选
- 检索结果导出

---

## 🧪 测试

### 后端测试

```bash
cd backend

# 搜索引擎功能测试
python scripts/test_search_engine.py

# 测试所有引擎
python scripts/test_search_engine.py all

# 性能基准测试
python scripts/test_search_engine.py benchmark
```

### 前端测试

```bash
cd frontend
pnpm test
```

---

## 📊 性能数据

### 搜索性能 (10,000 篇文档)

| 搜索引擎       | 索引时间 | 查询响应 | 内存占用 |
| -------------- | -------- | -------- | -------- |
| SQLite FTS5    | 5s       | 150ms    | 50MB     |
| PostgreSQL GIN | 3s       | 80ms     | 100MB    |
| MySQL FULLTEXT | 4s       | 120ms    | 80MB     |
| Elasticsearch  | 10s      | 20ms     | 1GB      |
| ClickHouse     | 2s       | 15ms     | 200MB    |

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

### 开发规范

1. 代码风格: 遵循 PEP8 (Python) 和 Airbnb (TypeScript)
2. 提交信息: 使用语义化提交 (Semantic Commit)
3. 测试覆盖: 新功能需包含单元测试

---

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 📞 支持

- 📧 Email: support@dochive.example.com
- 💬 Issue: [GitHub Issues](https://github.com/your-repo/DocHive/issues)
- 📚 文档: [在线文档](https://docs.dochive.example.com)

---

## 🙏 致谢

感谢以下开源项目:
- [FastAPI](https://fastapi.tiangolo.com/)
- [React](https://reactjs.org/)
- [Ant Design](https://ant.design/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [Elasticsearch](https://www.elastic.co/)

---

**⭐ 如果这个项目对您有帮助,请给一个 Star!** ⭐

---

**最后更新**: 2025-10-22  
**版本**: v1.1.0
