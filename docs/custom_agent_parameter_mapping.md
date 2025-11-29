# CustomAgentExecutor 动态参数构造功能说明

## 概述

`CustomAgentExecutor` 现在支持灵活的动态参数构造机制，可以在每个步骤执行时，根据配置或内置规则自动从中间数据中提取参数，实现步骤之间的数据传递。

## 新增功能

### 1. 嵌套值获取工具函数

`get_nested_value(data, path, default=None)` - 从嵌套字典中提取值

```python
data = {
    "outline": {
        "title": "测试文档",
        "sections": [...]
    }
}

# 使用点号路径提取值
title = get_nested_value(data, "outline.title")  # "测试文档"
sections = get_nested_value(data, "outline.sections")  # [...]
```

### 2. 参数构造方法

`CustomAgentExecutor.build_tool_arguments(step, query, template_id, intermediate_data)` - 自动构造工具参数

支持两种模式：

#### 模式1: 配置化参数映射（推荐）

在步骤配置中添加 `parameter_mappings` 字段：

```json
{
  "step": 2,
  "type": "tool",
  "name": "multi_query_search",
  "description": "根据大纲检索文档",
  "parameter_mappings": {
    "queries": {
      "source": "intermediate",
      "path": "outline.sections"
    },
    "template_id": {
      "source": "context"
    },
    "top_k_per_query": {
      "source": "value",
      "value": 5
    }
  }
}
```

**source 选项说明：**

- `"query"` - 直接使用用户查询文本
- `"context"` - 从执行上下文获取（支持 `template_id`, `query`）
- `"intermediate"` - 从 `intermediate_data` 中获取，可使用 `path` 指定嵌套路径
- `"previous"` - 从上一步结果（`last_result`）中获取
- `"value"` - 使用固定值，通过 `value` 字段指定

**path 说明：**

使用点号分隔的路径字符串，如：
- `"outline.sections"` - 获取大纲的章节列表
- `"result.data.items"` - 获取结果的数据项
- `"documents"` - 直接获取顶层字段

#### 模式2: 内置规则自动映射（兼容模式）

如果不配置 `parameter_mappings`，系统会根据工具名称使用内置规则：

- `generate_outline` - 自动传入 `query` 和 `user_requirements`
- `multi_query_search` - 自动从 `outline.sections` 提取 `queries`
- `get_document_contents` / `skim_documents` / `read_documents` - 自动传入 `document_ids`
- `es_fulltext_search` - 自动传入 `query` 和 `top_k`
- `analyze_documents` - 自动传入 `query` 和 `documents`

### 3. 中间数据管理增强

`intermediate_data` 结构：

```python
{
    "documents": [],         # 文档列表
    "document_ids": [],      # 文档ID列表
    "tool_results": [],      # 所有工具执行结果历史
    "agent_results": [],     # 所有智能体执行结果历史
    "last_result": {},       # 上一步的执行结果（新增）
    "outline": {},           # 文档大纲（新增）
}
```

**自动更新规则：**

- `generate_outline` 工具 → 更新 `intermediate_data["outline"]`
- 检索工具（`es_fulltext_search`, `multi_query_search` 等）→ 更新 `intermediate_data["document_ids"]`
- 文档获取工具 → 更新 `intermediate_data["documents"]`
- 所有工具 → 更新 `intermediate_data["last_result"]`

## 新增工具

### multi_query_search

支持使用多个查询词同时检索，适用于文档大纲有多个部分需要不同数据的场景。

**参数：**
- `queries: List[str]` - 查询词列表
- `template_id: int` - 模板ID
- `top_k_per_query: int` - 每个查询返回的文档数量（默认5）
- `deduplication: bool` - 是否去重（默认True）

**返回：**
```python
{
    "success": True,
    "document_ids": [1, 2, 3, ...],
    "documents": [...],
    "query_results": {  # 每个查询的原始结果
        "查询1": [...],
        "查询2": [...]
    },
    "count": 10
}
```

## 使用示例

### 示例1: 写作智能体完整配置

参见 `test_agent_md/writer_agent_config_example.json`

流程：
1. `generate_outline` - 生成大纲
2. `multi_query_search` - 根据大纲的多个部分进行检索
3. `get_document_contents` - 获取完整文档内容
4. 后续步骤可使用 `outline` 和 `documents` 进行文档生成

### 示例2: 简单配置（使用内置规则）

```json
{
  "steps": [
    {
      "step": 1,
      "type": "tool",
      "name": "generate_outline",
      "description": "生成大纲"
    },
    {
      "step": 2,
      "type": "tool",
      "name": "multi_query_search",
      "description": "检索文档"
    },
    {
      "step": 3,
      "type": "tool",
      "name": "get_document_contents",
      "description": "获取文档内容"
    }
  ]
}
```

系统会自动：
- 步骤1：传入 `query` 和 `user_requirements`
- 步骤2：从步骤1的 `outline.sections` 提取 `queries`
- 步骤3：使用步骤2的 `document_ids`

### 示例3: 复杂配置（使用参数映射）

```json
{
  "step": 4,
  "type": "tool",
  "name": "custom_analysis",
  "description": "自定义分析",
  "parameter_mappings": {
    "outline_data": {
      "source": "intermediate",
      "path": "outline"
    },
    "retrieved_docs": {
      "source": "intermediate",
      "path": "documents"
    },
    "user_query": {
      "source": "query"
    },
    "previous_analysis": {
      "source": "previous",
      "path": "analysis_result"
    },
    "max_items": {
      "source": "value",
      "value": 100
    }
  }
}
```

## 测试

运行测试脚本验证功能：

```bash
cd test_agent_md
python test_parameter_builder.py
```

测试覆盖：
- ✅ 嵌套值提取
- ✅ 内置规则参数构造
- ✅ 配置化参数映射
- ✅ 多种数据源（query, context, intermediate, previous, value）
- ✅ 路径解析

## 文件变更

### 新增文件

1. `backend/core/tools/retrieval/multi_query_search.py` - 多查询检索工具
2. `test_agent_md/writer_agent_config_example.json` - 写作智能体配置示例
3. `test_agent_md/test_parameter_builder.py` - 参数构造测试脚本
4. `docs/custom_agent_parameter_mapping.md` - 本说明文档

### 修改文件

1. `backend/core/agents/custom_agent_executor.py`
   - 新增 `get_nested_value()` 函数
   - 新增 `build_tool_arguments()` 方法
   - 更新工具执行逻辑
   - 增强中间数据管理

2. `backend/core/tools/retrieval/__init__.py`
   - 注册 `multi_query_search` 工具

3. `backend/core/tools/base.py`
   - 添加 `multi_query_search` 到工具发现列表

## 核心优势

1. **灵活性** - 支持配置化和内置规则两种模式
2. **可扩展性** - 轻松添加新的参数映射规则
3. **易用性** - 简单场景无需配置，复杂场景配置清晰
4. **可维护性** - 参数构造逻辑集中管理
5. **向后兼容** - 保留内置规则支持旧配置

## 后续优化方向

1. 支持更复杂的路径表达式（如数组过滤、条件选择）
2. 添加参数验证和类型转换
3. 支持参数转换函数（如列表合并、字符串拼接）
4. 提供可视化配置工具
