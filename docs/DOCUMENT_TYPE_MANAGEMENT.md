# 文档类型管理功能说明

## 📋 功能概述

文档类型管理功能允许用户为不同类型的文档（如开发文档、设计文档、研发任务表等）定义专属的结构化字段配置，并通过大模型智能提取相关信息。

## 🏗 架构设计

### 数据模型

#### 1. DocumentType（文档类型表）
存储文档类型的基本信息

| 字段              | 类型        | 说明                     |
| ----------------- | ----------- | ------------------------ |
| id                | Integer     | 主键                     |
| template_id       | Integer     | 所属模板ID               |
| type_code         | String(50)  | 类型编码（如：DEV_DOC）  |
| type_name         | String(100) | 类型名称（如：开发文档） |
| description       | Text        | 类型描述                 |
| extraction_prompt | Text        | 整体提取Prompt           |
| is_active         | Boolean     | 是否启用                 |
| created_at        | Integer     | 创建时间戳               |
| updated_at        | Integer     | 更新时间戳               |

#### 2. DocumentTypeField（文档类型字段表）
存储每个文档类型的结构化字段配置

| 字段                | 类型        | 说明                                       |
| ------------------- | ----------- | ------------------------------------------ |
| id                  | Integer     | 主键                                       |
| doc_type_id         | Integer     | 所属文档类型ID                             |
| field_name          | String(100) | 字段名称（如：编制人）                     |
| field_code          | String(50)  | 字段编码（如：author）                     |
| field_type          | String(20)  | 字段类型（text/number/array/date/boolean） |
| extraction_prompt   | Text        | 字段提取Prompt（统一使用大模型）           |
| is_required         | Boolean     | 是否必填                                   |
| display_order       | Integer     | 显示顺序                                   |
| placeholder_example | String(200) | 示例值                                     |
| created_at          | Integer     | 创建时间戳                                 |
| updated_at          | Integer     | 更新时间戳                                 |

#### 3. Document 扩展
在文档表中新增字段：

| 字段        | 类型    | 说明             |
| ----------- | ------- | ---------------- |
| doc_type_id | Integer | 关联的文档类型ID |

## 🔄 业务流程

### 1. 模板创建流程
```
用户创建模板
  ↓
定义层级（包含 is_doc_type=True 的层级）
  ↓
系统识别文档类型层级
  ↓
用户可选择为该类型配置字段
```

### 2. 文档类型配置流程
```
从模板中提取文档类型
  ↓
创建 DocumentType 记录
  ↓
配置该类型需要提取的字段（DocumentTypeField）
  ↓
每个字段配置 extraction_prompt
```

### 3. 文档处理流程
```
上传文档
  ↓
应用模板进行分类
  ↓
识别文档类型（通过 is_doc_type 层级）
  ↓
获取该类型的字段配置
  ↓
调用大模型提取字段信息
  ↓
存储到 document.extracted_data
```

## 🛠 API 接口

### 文档类型管理

#### 创建文档类型
```http
POST /api/v1/document-types/
Content-Type: application/json

{
  "template_id": 1,
  "type_code": "DEV_DOC",
  "type_name": "开发文档",
  "description": "软件开发相关文档",
  "extraction_prompt": "这是一份开发文档，请提取关键信息...",
  "fields": [
    {
      "field_name": "编制人",
      "field_code": "author",
      "field_type": "text",
      "extraction_prompt": "请从文档中提取编制人信息",
      "is_required": true,
      "display_order": 0,
      "placeholder_example": "张三"
    },
    {
      "field_name": "任务数量",
      "field_code": "task_count",
      "field_type": "number",
      "extraction_prompt": "统计文档中提到的任务总数",
      "is_required": false,
      "display_order": 1,
      "placeholder_example": "5"
    }
  ]
}
```

#### 获取模板的所有文档类型
```http
GET /api/v1/document-types/template/{template_id}?include_inactive=false
```

#### 获取文档类型详情
```http
GET /api/v1/document-types/{doc_type_id}
```

响应示例：
```json
{
  "code": 200,
  "message": "获取成功",
  "data": {
    "id": 1,
    "template_id": 1,
    "type_code": "DEV_DOC",
    "type_name": "开发文档",
    "description": "软件开发相关文档",
    "extraction_prompt": "...",
    "is_active": true,
    "created_at": "2025-10-24T10:00:00",
    "updated_at": "2025-10-24T10:00:00",
    "fields": [
      {
        "id": 1,
        "doc_type_id": 1,
        "field_name": "编制人",
        "field_code": "author",
        "field_type": "text",
        "extraction_prompt": "请从文档中提取编制人信息",
        "is_required": true,
        "display_order": 0,
        "placeholder_example": "张三",
        "created_at": "2025-10-24T10:00:00",
        "updated_at": "2025-10-24T10:00:00"
      }
    ]
  }
}
```

#### 更新文档类型
```http
PUT /api/v1/document-types/{doc_type_id}
Content-Type: application/json

{
  "type_name": "软件开发文档",
  "description": "更新后的描述"
}
```

#### 删除文档类型（软删除）
```http
DELETE /api/v1/document-types/{doc_type_id}
```

### 字段管理

#### 添加字段
```http
POST /api/v1/document-types/{doc_type_id}/fields
Content-Type: application/json

{
  "field_name": "完成时间",
  "field_code": "completion_date",
  "field_type": "date",
  "extraction_prompt": "提取文档中提到的完成日期",
  "is_required": true,
  "display_order": 2,
  "placeholder_example": "2025-12-31"
}
```

#### 获取所有字段
```http
GET /api/v1/document-types/{doc_type_id}/fields
```

#### 更新字段
```http
PUT /api/v1/document-types/fields/{field_id}
Content-Type: application/json

{
  "field_name": "项目完成时间",
  "extraction_prompt": "更新后的提取规则"
}
```

#### 删除字段
```http
DELETE /api/v1/document-types/fields/{field_id}
```

#### 批量更新字段
```http
PUT /api/v1/document-types/{doc_type_id}/fields/batch
Content-Type: application/json

[
  {
    "field_name": "编制人",
    "field_code": "author",
    "field_type": "text",
    "extraction_prompt": "...",
    "is_required": true,
    "display_order": 0
  },
  {
    "field_name": "任务数量",
    "field_code": "task_count",
    "field_type": "number",
    "extraction_prompt": "...",
    "is_required": false,
    "display_order": 1
  }
]
```

#### 获取提取配置
```http
GET /api/v1/document-types/{doc_type_id}/extraction-config
```

用于大模型提取时获取完整配置信息。

## 💡 使用示例

### 场景：配置"开发文档"类型

1. **创建文档类型**
```python
# 从模板中识别出文档类型层级后，创建 DocumentType
doc_type = {
    "template_id": 1,
    "type_code": "DEV_DOC",
    "type_name": "开发文档",
    "extraction_prompt": "这是软件开发文档，请提取关键开发信息"
}
```

2. **配置提取字段**
```python
fields = [
    {
        "field_name": "编制人",
        "field_code": "author",
        "field_type": "text",
        "extraction_prompt": "提取文档的编制人姓名",
        "is_required": True
    },
    {
        "field_name": "开发任务列表",
        "field_code": "tasks",
        "field_type": "array",
        "extraction_prompt": "提取所有开发任务，返回数组格式",
        "is_required": False
    },
    {
        "field_name": "预计完成时间",
        "field_code": "deadline",
        "field_type": "date",
        "extraction_prompt": "提取项目预计完成时间",
        "is_required": True
    }
]
```

3. **文档上传时自动提取**
```python
# 识别到文档类型为 "开发文档" 后
config = get_extraction_config(doc_type_id=1)

# 调用大模型提取
extracted_data = llm_extract(
    document_content=doc_content,
    config=config
)

# 结果示例
{
    "author": "张三",
    "tasks": ["需求分析", "系统设计", "编码实现", "测试"],
    "deadline": "2025-12-31"
}
```

## 🎯 核心特性

1. **统一使用大模型提取**
   - 所有字段提取均通过 LLM 完成
   - 无需配置正则表达式或固定值
   - 配置简单，灵活性高

2. **类型化字段支持**
   - text: 文本类型
   - number: 数值类型
   - array: 数组类型
   - date: 日期类型
   - boolean: 布尔类型

3. **灵活的配置管理**
   - 支持单个字段增删改
   - 支持批量更新字段配置
   - 字段顺序可调整

4. **与模板系统集成**
   - 从模板的 is_doc_type 层级识别文档类型
   - 自动关联到文档分类体系
   - 编号规则自动生成

## 📝 注意事项

1. **文档类型唯一性**
   - 同一模板下，type_code 必须唯一
   - 同一文档类型下，field_code 必须唯一

2. **Prompt 设计建议**
   - 提取 Prompt 应清晰描述提取目标
   - 包含字段类型说明（如"返回数组格式"）
   - 提供必要的上下文信息

3. **性能考虑**
   - 字段数量不宜过多（建议 < 20）
   - 大模型调用会增加处理时间
   - 可配置字段缓存策略

## 🔧 后续扩展

1. **字段验证规则**
   - 添加字段值验证逻辑
   - 支持自定义验证函数

2. **提取结果评分**
   - 记录提取置信度
   - 支持人工校正

3. **模板复用**
   - 跨模板复用字段配置
   - 字段配置导入导出

4. **统计分析**
   - 字段提取成功率统计
   - 常见提取错误分析
