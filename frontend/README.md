# DocHive 前端项目

> 基于 React + Ant Design + TypeScript 的智能文档分类分级系统前端

## 🎯 项目简介

DocHive 前端是一个现代化的文档管理系统界面，提供了完整的文档分类、上传、检索和管理功能。

## ✨ 主要功能模块

### 1. 用户认证
- ✅ 用户登录/注册
- ✅ JWT Token 认证
- ✅ 自动token刷新

### 2. 仪表板
- ✅ 系统概览统计
- ✅ 最近文档展示
- ✅ 数据可视化

### 3. 分类模板管理
- ✅ 创建/编辑/删除模板
- ✅ 可视化层级设计器
- ✅ 模板版本管理
- ✅ 层级拖拽排序

### 4. 文档管理
- ✅ 文档上传（支持多格式）
- ✅ 文档列表展示
- ✅ 文档详情查看
- ✅ 文档下载
- ✅ 智能分类触发

### 5. 文档检索
- ✅ 关键词搜索
- ✅ 高级过滤
- ✅ 分类路径检索
- ✅ 日期范围筛选

## 🛠️ 技术栈

- **框架**: React 18.3
- **UI 库**: Ant Design 5.27
- **路由**: React Router DOM 7.9
- **状态管理**: Zustand 4.5
- **HTTP 客户端**: Axios 1.6
- **构建工具**: Vite 7.1
- **语言**: TypeScript 5.9
- **样式**: TailwindCSS 3.4

## 📦 项目结构

```
frontend/
├── src/
│   ├── pages/              # 页面组件
│   │   ├── Login/         # 登录页
│   │   ├── Dashboard/     # 仪表板
│   │   ├── Template/      # 模板管理
│   │   ├── Document/      # 文档管理
│   │   └── Search/        # 文档检索
│   │
│   ├── components/        # 公共组件
│   │   └── Template/      # 模板相关组件
│   │       └── TemplateDesigner.tsx
│   │
│   ├── services/          # API 服务层
│   │   ├── auth.ts
│   │   ├── template.ts
│   │   ├── document.ts
│   │   ├── classification.ts
│   │   ├── extraction.ts
│   │   ├── numbering.ts
│   │   ├── search.ts
│   │   └── config.ts
│   │
│   ├── store/             # 状态管理
│   │   └── auth.ts
│   │
│   ├── types/             # TypeScript 类型定义
│   │   └── index.ts
│   │
│   ├── utils/             # 工具函数
│   │   └── request.ts     # Axios 封装
│   │
│   ├── router/            # 路由配置
│   │   └── index.tsx
│   │
│   ├── layout/            # 布局组件
│   │   └── index.tsx
│   │
│   ├── App.tsx            # 应用入口
│   └── main.tsx           # 主文件
│
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
└── .env                   # 环境变量
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd frontend
pnpm install
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

### 3. 启动开发服务器

```bash
pnpm dev
```

访问 http://localhost:5173

### 4. 构建生产版本

```bash
pnpm build
```

### 5. 预览构建结果

```bash
pnpm preview
```

## 📖 页面说明

### 登录页 (`/login`)
- 用户登录和注册
- Tab 切换界面
- 表单验证

### 仪表板 (`/dashboard`)
- 系统统计卡片
- 最近文档列表
- 快速操作入口

### 分类模板 (`/templates`)
- 模板列表查看
- 创建/编辑模板
- 可视化层级设计
- 层级拖拽排序

### 文档管理 (`/documents`)
- 文档上传
- 文档列表
- 文档详情查看
- 文档下载
- 触发智能分类

### 文档检索 (`/search`)
- 关键词搜索
- 多维度过滤
- 结果列表展示

## 🎨 UI 特性

- **响应式设计**: 适配桌面和移动端
- **现代化界面**: Glassmorphism 设计风格
- **流畅动画**: 过渡动画和交互反馈
- **深色模式**: 支持暗色主题（可选）

## 🔐 认证流程

1. 用户登录获取 JWT Token
2. Token 存储在 localStorage
3. 请求拦截器自动添加 Authorization Header
4. Token 过期自动跳转登录页

## 📡 API 对接

所有 API 请求通过 `src/services/` 下的服务文件进行：

```typescript
import { templateService } from '@/services';

// 获取模板列表
const response = await templateService.getTemplates({
  page: 1,
  page_size: 10
});
```

## 🐛 常见问题

### 1. 依赖安装失败
```bash
# 清除缓存
pnpm store prune

# 重新安装
pnpm install
```

### 2. 类型错误
确保已安装所有类型声明：
```bash
pnpm add -D @types/react @types/react-dom @types/node
```

### 3. 接口请求失败
- 检查后端服务是否启动
- 确认 `.env` 中的 API 地址正确
- 查看浏览器控制台网络请求

## 🔧 开发建议

1. **组件开发**: 遵循单一职责原则，组件尽量小而专一
2. **状态管理**: 页面级状态使用 useState，全局状态使用 Zustand
3. **类型安全**: 充分利用 TypeScript 类型检查
4. **代码规范**: 使用 ESLint 和 Prettier

## 📝 待实现功能

- [ ] 信息抽取配置页面
- [ ] 编号规则管理页面
- [ ] 系统配置页面
- [ ] 用户权限管理页面
- [ ] 批量文档操作
- [ ] 文档预览功能
- [ ] 导出功能优化

## 📄 许可证

© 2025 DocHive. All Rights Reserved.
