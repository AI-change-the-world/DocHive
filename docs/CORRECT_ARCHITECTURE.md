# 文档类型管理 - 正确的系统架构

## ❌ 错误设计（已修正）

~~将文档类型管理作为独立的页面模块~~

```
错误的设计：
/templates          → 模板管理
/document-types     → 文档类型管理（独立页面）❌
```

**问题**：
- 文档类型脱离了模板上下文
- 用户需要在两个页面间跳转
- 无法直观看到"模板-类型"的从属关系

---

## ✅ 正确设计（已实现）

**文档类型作为模板的子功能，通过抽屉组件展示**

```
正确的设计：
/templates          → 模板管理
  ├── 模板列表
  └── 点击"查看类别"
      └── 打开抽屉 → 文档类型管理（属于该模板）✅
          ├── 类型列表
          └── 字段配置
```

---

## 🏗 系统层级关系

```
模板 (ClassTemplate)
  ├── 层级定义 (TemplateLevel[])
  │   └── is_doc_type: true  → 标记文档类型层级
  │
  └── 文档类型 (DocumentType[])  ← 从属于模板
      ├── type_code
      ├── type_name
      └── 字段配置 (DocumentTypeField[])
          ├── field_name
          ├── field_code
          └── extraction_prompt
```

**关系说明**：
1. 一个模板可以有多个文档类型
2. 文档类型必须从属于某个模板
3. 文档类型的值来自模板中标记为 `is_doc_type=true` 的层级

---

## 📊 用户操作流程

### 步骤 1：创建模板
```
模板管理页面 → 创建模板
  ├── 定义层级
  └── 将某个层级标记为"文档类型"（is_doc_type=true）
```

**示例**：
```json
{
  "name": "发改委文档分类模板",
  "levels": [
    {"level": 1, "name": "年份", "code": "YEAR"},
    {"level": 2, "name": "地域", "code": "REGION"},
    {"level": 3, "name": "部门", "code": "DEPT"},
    {"level": 4, "name": "文档类型", "code": "TYPE", "is_doc_type": true}  ← 标记
  ]
}
```

### 步骤 2：配置文档类型
```
模板列表 → 点击"查看类别" → 打开抽屉
  ├── 看到该模板的所有文档类型
  ├── 新建类型（如："通知"、"批复"、"报告"）
  └── 为每个类型配置字段
```

**示例**：
```
模板："发改委文档分类模板"
  └── 文档类型：
      ├── "通知" → 配置字段：[发文单位, 截止日期, 适用范围]
      ├── "批复" → 配置字段：[批复单位, 批复对象, 批复结论]
      └── "报告" → 配置字段：[报告单位, 报告主题, 建议内容]
```

### 步骤 3：文档处理
```
上传文档 → 应用模板分类
  ↓
识别文档类型（从"文档类型"层级）
  ↓
自动创建/关联 DocumentType
  ↓
根据类型配置提取字段
```

---

## 💻 前端实现

### 组件结构

```
pages/Template/
  ├── index.tsx                         # 模板管理主页面
  └── components/
      ├── TemplateDesigner.tsx          # 模板层级设计器
      ├── DocumentTypeManager.tsx       # 文档类型管理（抽屉内容）✅
      └── FieldConfigDrawer.tsx         # 字段配置抽屉
```

### 关键代码

#### 模板页面 (Template/index.tsx)
```tsx
// 打开文档类型管理抽屉
const handleViewDocumentTypes = (template: ClassTemplate) => {
    setSelectedTemplate(template);
    setDocTypeDrawerVisible(true);
};

// 抽屉组件
<Drawer
    title={`文档类型管理 - ${selectedTemplate?.name}`}
    width={1000}
    open={docTypeDrawerVisible}
    onClose={() => setDocTypeDrawerVisible(false)}
>
    {selectedTemplate && (
        <DocumentTypeManager template={selectedTemplate} />
    )}
</Drawer>
```

#### 文档类型管理器 (DocumentTypeManager.tsx)
```tsx
interface DocumentTypeManagerProps {
    template: ClassTemplate;  // 接收模板对象
}

// 只管理该模板下的文档类型
const loadDocumentTypes = async () => {
    const types = await getDocumentTypesByTemplate(template.id);
    setDocumentTypes(types);
};
```

---

## 🔄 数据流

### 创建文档类型
```
用户操作：
  模板列表 → 点击"查看类别" → 点击"新建类型"

前端调用：
  createDocumentType({
    template_id: template.id,  ← 自动带上模板ID
    type_code: "DEV_DOC",
    type_name: "开发文档",
    ...
  })

后端存储：
  document_types 表
    ├── template_id: 1  ← 关联到模板
    ├── type_code: "DEV_DOC"
    └── type_name: "开发文档"
```

### 文档分类时自动识别类型
```
文档上传 → 应用模板ID=1分类
  ↓
分类结果：{"年份": "2025", "部门": "研发部", "文档类型": "开发文档"}
  ↓
识别到"文档类型"层级（is_doc_type=true）
  ↓
查找 template_id=1 下的 type_name="开发文档" 的记录
  ↓
找到 DocumentType.id = 5
  ↓
设置 document.doc_type_id = 5
```

---

## 🎯 设计优势

### 1. **符合业务逻辑**
- 文档类型**从属于**模板
- 一个模板对应一套分类体系
- 清晰的层级关系

### 2. **用户体验更好**
- 在同一个上下文中操作
- 无需在多个页面间跳转
- 直观理解"模板-类型"关系

### 3. **数据一致性**
- 文档类型必定关联到某个模板
- 避免孤立的类型配置
- 便于批量管理

### 4. **扩展性强**
- 可以为每个模板配置不同的类型
- 支持模板复制时同时复制类型配置
- 便于模板导入导出

---

## 📝 API 设计

### 获取模板的文档类型
```http
GET /api/v1/document-types/template/{template_id}
```

**特点**：
- 必须指定 template_id
- 只返回该模板下的类型
- 体现了从属关系

### 创建文档类型
```http
POST /api/v1/document-types/
{
    "template_id": 1,  ← 必填字段
    "type_code": "DEV_DOC",
    "type_name": "开发文档"
}
```

**特点**：
- template_id 是必填字段
- 确保类型必定关联到模板
- 避免孤立的类型配置

---

## 🔧 技术实现要点

### 1. **前端组件通信**
```tsx
// 父组件传递模板对象
<DocumentTypeManager template={selectedTemplate} />

// 子组件接收并使用
interface Props {
    template: ClassTemplate;
}
const Component: React.FC<Props> = ({ template }) => {
    // 自动带上 template.id
    loadDocumentTypes(template.id);
};
```

### 2. **抽屉vs独立页面**
- ✅ 使用抽屉：保持上下文，不离开当前页面
- ❌ 独立页面：丢失上下文，需要参数传递

### 3. **权限控制**
- 模板的创建者才能管理其文档类型
- 继承模板的权限设置

---

## ⚠️ 注意事项

### 1. **模板必须有 is_doc_type 层级**
```tsx
const hasDocTypeLevel = template.levels?.some(
    level => level.is_doc_type
);

if (!hasDocTypeLevel) {
    return <Empty description="该模板尚未配置文档类型层级" />;
}
```

### 2. **删除模板时级联处理**
- 删除模板 → 同时删除关联的文档类型
- 或者禁止删除有关联类型的模板

### 3. **模板复制**
- 复制模板时可选择是否复制文档类型配置
- 生成新的 type_code 避免冲突

---

## 🎉 总结

**正确的架构：**
- ✅ 文档类型作为模板的子功能
- ✅ 通过抽屉在模板页面中管理
- ✅ 清晰的层级关系和业务逻辑
- ✅ 更好的用户体验

**核心原则：**
> 文档类型永远从属于某个模板，它们是模板分类体系的一部分，而不是独立的业务对象。

这个设计符合实际业务场景：
- 发改委的"通知、批复、报告"属于发改委分类模板
- 研发部的"开发文档、设计文档"属于研发部分类模板
- 不同的模板有不同的文档类型配置

通过这种设计，系统的层级结构更加清晰，用户操作更加直观！🎯
