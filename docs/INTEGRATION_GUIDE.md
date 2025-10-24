# 文档类型功能集成指南

## 🎯 概述

本指南说明如何将新的**文档类型(TYPE)管理功能**与现有的**分类**和**提取**模块集成使用。

## 🔄 完整业务流程

```
1. 创建模板 (Template)
   ↓
2. 定义层级 (标记 is_doc_type=True)
   ↓
3. 上传文档 (Document)
   ↓
4. 智能分类 (Classification) ← 自动创建 DocumentType
   ↓
5. 识别文档类型 (TYPE识别)
   ↓
6. 结构化提取 (Extraction) ← 使用TYPE字段配置
   ↓
7. 存储结果 (extracted_data)
```

## 📊 集成点说明

### 1. 分类服务集成 (classification_service.py)

#### 新增功能
- **自动识别文档类型**：在分类过程中识别 `is_doc_type=True` 的层级
- **自动创建 DocumentType**：首次遇到新类型时自动创建
- **关联文档**：将 `doc_type_id` 写入 Document 表

#### 关键方法
```python
ClassificationEngine._identify_document_type(
    db, template_id, template_levels, class_path
)
```

**工作原理**：
1. 从模板层级中找到 `is_doc_type=True` 的层级
2. 从 `class_path` 中获取该层级的值（如："开发文档"）
3. 生成 `type_code`（如："KAI_FA_WEN_DANG"）
4. 查找或创建 DocumentType 记录
5. 返回 `doc_type_id`

#### 使用示例
```python
# 分类文档时自动识别类型
result = await ClassificationEngine.classify_document(
    db, document_id=1, template_id=1
)

# 返回结果包含
{
    "document_id": 1,
    "class_path": {"年份": "2025", "部门": "研发部", "类型": "开发文档"},
    "class_code": "2025-DEV-...",
    "doc_type_id": 5  # 自动识别并创建/关联
}
```

### 2. 提取服务集成 (extraction_service.py)

#### 新增核心方法
```python
ExtractionEngine.extract_by_document_type(db, document_id)
```

**这是与文档类型系统集成的关键方法！**

#### 工作流程
1. 获取文档的 `doc_type_id`
2. 通过 `DocumentTypeService.get_extraction_config()` 获取字段配置
3. 构建针对该文档类型的 LLM Prompt
4. **一次性提取所有字段**（比逐个提取更高效）
5. 存储到 `document.extracted_data`

#### 使用示例
```python
# 基于文档类型自动提取
result = await ExtractionEngine.extract_by_document_type(
    db, document_id=1
)

# 返回结果
{
    "document_id": 1,
    "extracted_data": {
        "author": "张三",
        "task_count": 5,
        "completion_date": "2025-12-31"
    },
    "success_fields": ["编制人", "任务数量", "完成时间"],
    "failed_fields": []
}
```

#### 核心优势
- ✅ **智能提取**：基于配置的 Prompt 自动提取
- ✅ **类型安全**：自动类型转换（text/number/array/date/boolean）
- ✅ **高效**：一次 LLM 调用提取所有字段
- ✅ **灵活**：每个文档类型独立配置

### 3. 文档处理完整流程

#### API 调用顺序

```python
# 1. 上传文档
doc = await DocumentService.upload_document(db, file)

# 2. 解析文档内容（PDF/DOCX）
await DocumentService.parse_document(db, doc.id)

# 3. 智能分类（自动识别类型）
classification_result = await ClassificationEngine.classify_document(
    db, doc.id, template_id=1
)

# 4. 基于类型提取结构化信息
extraction_result = await ExtractionEngine.extract_by_document_type(
    db, doc.id
)

# 5. 查看结果
document = await DocumentService.get_document(db, doc.id)
print(document.class_path)        # {"年份": "2025", "类型": "开发文档"}
print(document.doc_type_id)       # 5
print(document.extracted_data)    # {"author": "张三", "task_count": 5}
```

## 🎨 前端集成

### 1. 文档类型管理界面

#### 访问路径
```
/document-types?templateId=1
```

#### 主要功能
- 查看模板的所有文档类型
- 创建新的文档类型
- 编辑类型信息
- 配置提取字段

#### 组件结构
```
pages/DocumentType/
  ├── index.tsx                    # 主页面
  └── components/
      └── FieldConfigDrawer.tsx   # 字段配置抽屉
```

### 2. 在模板管理中的集成

在 `Template` 页面添加"文档类型管理"入口：

```tsx
<Button 
    onClick={() => navigate(`/document-types?templateId=${template.id}`)}
>
    管理文档类型
</Button>
```

### 3. 在文档详情中展示

```tsx
// 展示文档类型
{document.doc_type_id && (
    <Descriptions.Item label="文档类型">
        {documentType.type_name}
    </Descriptions.Item>
)}

// 展示提取的结构化数据
{document.extracted_data && (
    <Descriptions>
        {Object.entries(document.extracted_data).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
                {JSON.stringify(value)}
            </Descriptions.Item>
        ))}
    </Descriptions>
)}
```

## 📝 使用案例：发改委文档处理

### 步骤 1：创建模板
```json
{
    "name": "发改委文档分类模板",
    "levels": [
        {"level": 1, "name": "年份", "code": "YEAR"},
        {"level": 2, "name": "地域", "code": "REGION"},
        {"level": 3, "name": "部门", "code": "DEPT"},
        {"level": 4, "name": "文档类型", "code": "TYPE", "is_doc_type": true}
    ]
}
```

### 步骤 2：上传并分类文档
```
文档：《常州市发改委关于2025年智能制造项目申报通知》
↓
分类结果：
{
    "年份": "2025",
    "地域": "常州市",
    "部门": "发改委",
    "文档类型": "通知"  ← 自动创建 DocumentType("通知")
}
```

### 步骤 3：配置"通知"类型的字段
```javascript
// 前端操作：进入文档类型管理 → 点击"通知" → 配置字段
{
    type_name: "通知",
    fields: [
        {
            field_name: "发文单位",
            field_code: "issuer",
            field_type: "text",
            extraction_prompt: "提取发文单位名称"
        },
        {
            field_name: "截止日期",
            field_code: "deadline",
            field_type: "date",
            extraction_prompt: "提取申报截止日期"
        },
        {
            field_name: "适用范围",
            field_code: "scope",
            field_type: "array",
            extraction_prompt: "提取适用企业类型列表"
        }
    ]
}
```

### 步骤 4：自动提取
```python
# 后端自动调用
result = await ExtractionEngine.extract_by_document_type(db, document_id)

# 提取结果
{
    "issuer": "常州市发展和改革委员会",
    "deadline": "2025-06-30",
    "scope": ["制造业企业", "高新技术企业", "专精特新企业"]
}
```

## 🔧 API 端点总结

### 文档类型管理
| 方法   | 路径                                            | 说明               |
| ------ | ----------------------------------------------- | ------------------ |
| GET    | `/api/v1/document-types/template/{template_id}` | 获取模板的所有类型 |
| POST   | `/api/v1/document-types/`                       | 创建文档类型       |
| GET    | `/api/v1/document-types/{id}`                   | 获取类型详情       |
| PUT    | `/api/v1/document-types/{id}`                   | 更新类型           |
| DELETE | `/api/v1/document-types/{id}`                   | 删除类型           |

### 字段配置
| 方法   | 路径                                       | 说明         |
| ------ | ------------------------------------------ | ------------ |
| POST   | `/api/v1/document-types/{id}/fields`       | 添加字段     |
| GET    | `/api/v1/document-types/{id}/fields`       | 获取所有字段 |
| PUT    | `/api/v1/document-types/fields/{field_id}` | 更新字段     |
| DELETE | `/api/v1/document-types/fields/{field_id}` | 删除字段     |
| PUT    | `/api/v1/document-types/{id}/fields/batch` | 批量更新字段 |

### 提取配置
| 方法 | 路径                                            | 说明         |
| ---- | ----------------------------------------------- | ------------ |
| GET  | `/api/v1/document-types/{id}/extraction-config` | 获取提取配置 |

## ⚠️ 注意事项

### 1. 文档类型自动创建
- 首次分类时，如果遇到新的文档类型值，会**自动创建** DocumentType
- 自动创建的类型没有字段配置，需要后续手动添加
- 建议：先手动创建常见类型并配置字段

### 2. Prompt 配置建议
- **类型级别 Prompt**：描述该类型文档的整体特征
- **字段级别 Prompt**：描述如何提取该字段
- **编码规则**：直接在 Prompt 中说明值到编码的映射

### 3. 性能优化
- 使用 `extract_by_document_type` 一次性提取所有字段
- 避免逐个字段调用 LLM
- 考虑异步批量处理大量文档

### 4. 错误处理
- 文档未分类 → 无法提取（需先分类）
- 文档类型未配置字段 → 返回空结果
- 字段提取失败 → 记录在 `failed_fields` 中

## 🚀 快速开始

### 后端
```bash
# 1. 运行数据库迁移
cd backend
python -m alembic upgrade head
# 或手动执行
sqlite3 dochive.db < migrations/add_document_types.sql

# 2. 启动服务
python run.py
```

### 前端
```bash
# 1. 安装依赖
cd frontend
pnpm install

# 2. 启动开发服务器
pnpm dev
```

### 测试流程
1. 访问 http://localhost:5173/templates
2. 创建一个模板，定义层级（包含 is_doc_type=true）
3. 访问 http://localhost:5173/document-types?templateId=1
4. 添加文档类型并配置字段
5. 上传文档并分类
6. 查看提取结果

## 📚 相关文档

- [文档类型管理功能说明](./DOCUMENT_TYPE_MANAGEMENT.md)
- [TYPE功能实现总结](./TYPE_FEATURE_SUMMARY.md)
- [搜索引擎说明](./SEARCH_ENGINE.md)
- [系统架构](../ARCHITECTURE.md)

## 💡 最佳实践

1. **先定义类型，再上传文档**
   - 提前配置好常见文档类型的字段
   - 避免大量自动创建的空类型

2. **Prompt 工程**
   - 清晰描述提取目标
   - 提供必要的上下文
   - 说明返回格式

3. **批量处理**
   - 使用异步任务处理大批量文档
   - 设置合理的并发限制
   - 监控 LLM API 调用次数

4. **用户培训**
   - 教会用户如何配置字段
   - 提供 Prompt 模板
   - 建立类型库和最佳实践

---

通过以上集成，DocHive 现在具备了完整的**文档类型管理 + 智能提取**能力！🎉
