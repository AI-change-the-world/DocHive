# API 参考文档

## 认证接口

### 用户登录

**POST** `/api/v1/auth/login`

请求参数:
```json
{
  "username": "string",
  "password": "string"
}
```

响应:
```json
{
  "access_token": "string",
  "token_type": "string"
}
```

### 用户注册

**POST** `/api/v1/auth/register`

请求参数:
```json
{
  "username": "string",
  "email": "string",
  "password": "string"
}
```

响应:
```json
{
  "id": "integer",
  "username": "string",
  "email": "string",
  "created_at": "string"
}
```

### 刷新令牌

**POST** `/api/v1/auth/refresh`

请求头:
```
Authorization: Bearer <refresh_token>
```

响应:
```json
{
  "access_token": "string",
  "token_type": "string"
}
```

## 文档管理接口

### 获取文档列表

**GET** `/api/v1/documents`

查询参数:
- `skip`: integer (默认: 0)
- `limit`: integer (默认: 100)
- `category_id`: integer (可选)
- `search`: string (可选)

响应:
```json
[
  {
    "id": "integer",
    "title": "string",
    "filename": "string",
    "category_id": "integer",
    "created_at": "string",
    "updated_at": "string"
  }
]
```

### 上传文档

**POST** `/api/v1/documents`

请求体 (multipart/form-data):
- `file`: 文件
- `category_id`: integer (可选)

响应:
```json
{
  "id": "integer",
  "title": "string",
  "filename": "string",
  "category_id": "integer",
  "created_at": "string",
  "updated_at": "string"
}
```

### 获取文档详情

**GET** `/api/v1/documents/{id}`

响应:
```json
{
  "id": "integer",
  "title": "string",
  "filename": "string",
  "content": "string",
  "category_id": "integer",
  "tags": ["string"],
  "created_at": "string",
  "updated_at": "string"
}
```

### 更新文档

**PUT** `/api/v1/documents/{id}`

请求参数:
```json
{
  "title": "string",
  "category_id": "integer"
}
```

响应:
```json
{
  "id": "integer",
  "title": "string",
  "filename": "string",
  "category_id": "integer",
  "created_at": "string",
  "updated_at": "string"
}
```

### 删除文档

**DELETE** `/api/v1/documents/{id}`

响应:
```
204 No Content
```

## 分类管理接口

### 获取分类列表

**GET** `/api/v1/categories`

查询参数:
- `skip`: integer (默认: 0)
- `limit`: integer (默认: 100)

响应:
```json
[
  {
    "id": "integer",
    "name": "string",
    "description": "string",
    "parent_id": "integer",
    "created_at": "string"
  }
]
```

### 创建分类

**POST** `/api/v1/categories`

请求参数:
```json
{
  "name": "string",
  "description": "string",
  "parent_id": "integer"
}
```

响应:
```json
{
  "id": "integer",
  "name": "string",
  "description": "string",
  "parent_id": "integer",
  "created_at": "string"
}
```

### 更新分类

**PUT** `/api/v1/categories/{id}`

请求参数:
```json
{
  "name": "string",
  "description": "string",
  "parent_id": "integer"
}
```

响应:
```json
{
  "id": "integer",
  "name": "string",
  "description": "string",
  "parent_id": "integer",
  "created_at": "string"
}
```

### 删除分类

**DELETE** `/api/v1/categories/{id}`

响应:
```
204 No Content
```

## 模板管理接口

### 获取模板列表

**GET** `/api/v1/templates`

查询参数:
- `skip`: integer (默认: 0)
- `limit`: integer (默认: 100)

响应:
```json
[
  {
    "id": "integer",
    "name": "string",
    "structure": "object",
    "created_at": "string"
  }
]
```

### 创建模板

**POST** `/api/v1/templates`

请求参数:
```json
{
  "name": "string",
  "structure": "object"
}
```

响应:
```json
{
  "id": "integer",
  "name": "string",
  "structure": "object",
  "created_at": "string"
}
```

### 更新模板

**PUT** `/api/v1/templates/{id}`

请求参数:
```json
{
  "name": "string",
  "structure": "object"
}
```

响应:
```json
{
  "id": "integer",
  "name": "string",
  "structure": "object",
  "created_at": "string"
}
```

### 删除模板

**DELETE** `/api/v1/templates/{id}`

响应:
```
204 No Content
```

## 搜索接口

### 全文搜索

**GET** `/api/v1/search`

查询参数:
- `q`: string (搜索关键词)
- `category_id`: integer (可选)
- `skip`: integer (默认: 0)
- `limit`: integer (默认: 100)

响应:
```json
[
  {
    "document_id": "integer",
    "title": "string",
    "snippet": "string",
    "score": "number"
  }
]
```

## 错误响应格式

所有错误响应遵循以下格式:

```json
{
  "detail": "错误描述信息"
}
```

常见HTTP状态码:
- 200: 请求成功
- 201: 创建成功
- 204: 删除成功
- 400: 请求参数错误
- 401: 未认证
- 403: 权限不足
- 404: 资源不存在
- 500: 服务器内部错误