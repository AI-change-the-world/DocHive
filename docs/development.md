# 开发指南

## 开发环境搭建

### 后端开发环境

1. 安装 Python 3.10+
2. 创建虚拟环境:
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. 安装依赖:
```bash
pip install -r requirements.txt
```

4. 配置环境变量:
复制 [.env.example](../backend/.env.example) 到 [.env](../backend/.env) 并根据需要修改配置

5. 启动开发服务器:
```bash
python run.py
```

### 前端开发环境

1. 安装 Node.js 18+
2. 安装 pnpm:
```bash
npm install -g pnpm
```

3. 安装依赖:
```bash
cd frontend
pnpm install
```

4. 启动开发服务器:
```bash
pnpm dev
```

## 项目结构说明

### 后端结构

```
backend/
├── api/               # API 路由层
├── models/            # 数据模型
├── services/          # 业务逻辑
├── utils/             # 工具模块
├── scripts/           # 工具脚本
├── config.py          # 配置管理
├── database.py        # 数据库连接
├── main.py            # 应用入口
└── run.py             # 启动脚本
```

### 前端结构

```
frontend/
├── src/
│   ├── pages/         # 页面组件
│   ├── components/    # 通用组件
│   ├── services/      # API 服务
│   ├── store/         # 状态管理
│   ├── router/        # 路由配置
│   ├── types/         # TypeScript 类型
│   └── utils/         # 工具函数
└── ...
```

## 代码规范

### 后端规范

- 遵循 PEP8 代码风格
- 使用类型注解
- 编写单元测试

### 前端规范

- 遵循 Airbnb TypeScript 规范
- 使用 TypeScript 严格模式
- 组件化开发

## 数据库设计

### 主要实体

1. **用户(User)**: 系统用户
2. **文档(Document)**: 上传的文档
3. **分类(Category)**: 文档分类
4. **模板(Template)**: 分类模板
5. **标签(Tag)**: 文档标签

### 关系说明

- 用户可以上传多个文档
- 文档属于某个分类
- 分类基于模板创建
- 文档可以有多个标签

## API 设计

### 认证接口

- POST /auth/login - 用户登录
- POST /auth/register - 用户注册
- POST /auth/refresh - 刷新令牌

### 文档管理接口

- GET /documents - 获取文档列表
- POST /documents - 上传文档
- GET /documents/{id} - 获取文档详情
- PUT /documents/{id} - 更新文档信息
- DELETE /documents/{id} - 删除文档

### 分类管理接口

- GET /categories - 获取分类列表
- POST /categories - 创建分类
- PUT /categories/{id} - 更新分类
- DELETE /categories/{id} - 删除分类

## 测试

### 后端测试

运行后端测试:
```bash
cd backend
pytest
```

### 前端测试

运行前端测试:
```bash
cd frontend
pnpm test
```

## 贡献指南

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 发起 Pull Request

### 提交信息规范

遵循语义化提交规范:
- feat: 新功能
- fix: 修复 bug
- docs: 文档更新
- style: 代码格式调整
- refactor: 代码重构
- test: 测试相关
- chore: 构建过程或辅助工具的变动