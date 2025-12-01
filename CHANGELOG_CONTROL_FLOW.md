# Agent 控制流优化 - 修改文档

## 修改概述

本次优化实现了完整的Agent控制流功能，包括：条件判断、重试、跳转、兜底等。主要采用两阶段设计：

1. **规划阶段**：LLM 根据工具能力目录进行智能选择和流程规划
2. **执行阶段**：执行器根据 checkpoint 配置实现控制流

---

## 一、核心设计理念

### 1.1 动态工具能力匹配
- **旧设计**：固定的状态键列表，需要手动维护
- **新设计**：从所有已注册工具的 `output_schema` 动态推导可用状态键
- **优势**：新增工具时自动更新能力目录，无需手动维护

### 1.2 结构化控制流（checkpoint）
- **旧设计**：自由文本 `condition` 字段，难以程序化执行
- **新设计**：结构化的 `checkpoint` 配置
  ```json
  {
    "expectations": [
      { "left": "summary.sections_count", "op": ">", "right": 0 }
    ],
    "on_fail": {
      "retry_limit": 3,
      "goto": 2,
      "set_state": { "outline": {} }
    }
  }
  ```
- **优势**：可程序化执行，支持复杂控制逻辑

### 1.3 统一状态管理
- 使用统一的 `state dict` 管理步骤间数据流
- 自动提取每步执行结果的 `summary`（关键指标）
- 支持嵌套路径访问（如 `summary.sections_count`）

---

## 二、修改的文件清单

### 2.1 工具层增强
**文件**: `backend/core/tools/base.py`

**新增函数**:
1. `get_tools_catalog()` - 生成工具能力目录
   - 包含每个工具的 name、description、capabilities、input_schema、output_schema
   - 供 LLM 在规划阶段进行能力匹配

2. `get_state_keys_catalog()` - 生成状态键目录
   - 汇总所有工具可能写入的状态键
   - 供 LLM 在规划阶段选择正确的状态键路径

**重要细节**:
- 这两个函数会自动扫描 `_TOOL_REGISTRY`，无需手动维护
- 新增工具时，只需在 `output_schema` 中声明输出字段即可
- 建议每个工具在注册时都明确指定 `output_schema`

### 2.2 数据模型更新
**文件**: `backend/schemas/agent_schemas.py`

**修改内容**:
- `AgentStepSchema` 新增 `checkpoint` 字段
- `condition` 字段标记为已弃用（保留兼容性）

**checkpoint 字段结构**:
```python
checkpoint: Optional[Dict[str, Any]] = Field(
    None, 
    description="""
    检查点配置，用于控制流程：
    {
        "expectations": [{ "left": "summary.xxx", "op": ">", "right": 0 }],
        "on_fail": { "retry_limit": 2, "goto": 1, "set_state": {...} }
    }
    """
)
```

**重要细节**:
- `expectations` 是一个数组，所有条件必须同时满足（AND 逻辑）
- 支持的操作符：`>`, `<`, `>=`, `<=`, `==`, `!=`, `in`, `not_in`
- `on_fail` 中的三个策略可以组合使用

### 2.3 解析层升级
**文件**: `backend/core/agent_editor.py`

**修改内容**:
1. `AgentMarkdownParser.parse_with_llm()`
   - 引入 `get_tools_catalog()` 和 `get_state_keys_catalog()`
   - 更新 `system_prompt`，指导 LLM 使用 checkpoint
   - 示例展示如何将自然语言转换为 checkpoint 结构

2. `AgentLLMValidator.validate_with_llm()`
   - 同步更新为使用工具能力目录
   - 验证 checkpoint 配置的合法性
   - 生成的 Mermaid 流程图支持决策节点展示

**重要细节**:
- Prompt 中明确了 checkpoint 的使用方法和最佳实践
- LLM 需要根据【工具能力目录】和【状态键目录】进行智能规划
- 状态键路径必须是从目录中选择的合法路径

### 2.4 执行器重构
**文件**: `backend/core/agents/custom_agent_executor.py`

**新增函数**:
1. `evaluate_checkpoint(checkpoint, state, step_result)`
   - 评估 checkpoint 的 expectations 是否全部满足
   - 返回 `(is_passed, on_fail_config)`
   - 支持嵌套路径和多种比较操作符

**修改内容**:
1. `CustomAgentExecutor.execute()` 方法
   - **从 `for` 循环改为 `while` 循环 + 指针模式**
   - 支持 `goto` 跳转到任意步骤
   - 实现重试计数器（每步独立计数）
   - 新增三种 SSE 事件：
     - `stage_retry`: 步骤重试
     - `stage_jump`: 跳转到其他步骤
     - `stage_fallback`: 应用兜底状态

**控制流实现逻辑**:
```python
while current_step_index < len(steps) and iteration_count < max_iterations:
    # 1. 执行步骤
    result = ...
    
    # 2. 评估 checkpoint
    if checkpoint:
        is_passed, on_fail = evaluate_checkpoint(checkpoint, state, result)
        
        if not is_passed and on_fail:
            # 3a. 应用 set_state（兜底状态）
            if set_state:
                for key, value in set_state.items():
                    state.set_data(key, value)
            
            # 3b. 处理 retry
            if retry_limit:
                if current_retries < retry_limit:
                    retry_counts[step_key] += 1
                    continue  # 不移动指针，重试当前步骤
            
            # 3c. 处理 goto
            if goto_step:
                current_step_index = find_step_index(goto_step)
                continue
    
    # 4. checkpoint 通过，移动到下一步
    current_step_index += 1
```

**重要细节**:
- 使用 `max_iterations = len(steps) * 10` 防止无限循环
- 每个步骤的重试次数独立计数（`retry_counts[f"step_{step_num}"]`）
- `retry` 和 `goto` 可以组合使用：先重试，重试超限后跳转
- 异常情况也会移动指针到下一步，避免卡死

---

##三、使用指南

### 3.1 为工具添加 output_schema

**示例**: `multi_query_search` 工具

```python
register_tool(
    name="multi_query_search",
    func=multi_query_search,
    description="多查询检索工具",
    category="retrieval",
    output_schema={
        "success": {"type": "boolean", "description": "是否成功"},
        "document_ids": {"type": "array", "description": "检索到的文档ID列表"},
        "document_count": {"type": "integer", "description": "检索到的文档数量"},
        "error": {"type": "string", "description": "错误信息（可选）"}
    }
)
```

**注意事项**:
- `output_schema` 必须包含工具实际返回的所有字段
- 状态键目录会自动从所有工具的 `output_schema` 汇总
- 建议字段名保持一致性（如 `document_ids`、`documents` 等）

### 3.2 编写 Agent Markdown 定义

**示例**: 智能写作助手

```markdown
# 智能写作助手

## 描述
基于用户查询，自动生成高质量文章。

## 执行模式
tool_chain

## 步骤

### 步骤1: 生成大纲
- 工具: generate_outline
- 描述: 根据用户查询生成文章大纲
- 期望: 大纲章节数大于0
- 失败处理: 最多重试3次

### 步骤2: 检索资料
- 工具: multi_query_search
- 描述: 检索相关文档资料
- 期望: 检索到的文档数大于0
- 失败处理: 最多重试2次

### 步骤3: 提取内容
- 工具: document_extraction
- 描述: 从文档中提取关键内容
- 期望: 提取的内容块数大于0
- 失败处理: 如果失败，回到步骤2重新检索

### 步骤4: 组合成文
- 工具: document_compose
- 描述: 将提取的内容组合成完整文章
```

**LLM 会自动转换为 checkpoint 结构**:

```json
{
  "steps": [
    {
      "step": 1,
      "type": "tool",
      "name": "generate_outline",
      "description": "生成大纲",
      "checkpoint": {
        "expectations": [
          { "left": "summary.sections_count", "op": ">", "right": 0 }
        ],
        "on_fail": { "retry_limit": 3 }
      }
    },
    {
      "step": 2,
      "type": "tool",
      "name": "multi_query_search",
      "description": "检索资料",
      "checkpoint": {
        "expectations": [
          { "left": "summary.document_count", "op": ">", "right": 0 }
        ],
        "on_fail": { "retry_limit": 2 }
      }
    },
    {
      "step": 3,
      "type": "tool",
      "name": "document_extraction",
      "description": "提取内容",
      "checkpoint": {
        "expectations": [
          { "left": "summary.total_chunks", "op": ">", "right": 0 }
        ],
        "on_fail": { "goto": 2 }
      }
    },
    {
      "step": 4,
      "type": "tool",
      "name": "document_compose",
      "description": "组合成文"
    }
  ]
}
```

### 3.3 状态键路径规则

**可用的顶级键**:
- `summary.*`: 当前步骤执行结果的摘要（由 `_extract_step_summary` 自动生成）
- 工具的 `output_schema` 中定义的任何字段

**常用状态键示例**:
- `summary.sections_count`: 章节数量（generate_outline）
- `summary.document_count`: 文档数量（multi_query_search）
- `summary.total_chunks`: 内容块数量（document_extraction）
- `summary.word_count`: 字数（document_compose）
- `documents`: 文档列表
- `document_ids`: 文档ID列表
- `outline`: 大纲结构

**路径访问示例**:
```json
{
  "left": "summary.sections_count",  // 访问 summary 下的 sections_count
  "op": ">",
  "right": 0
}
```

---

## 四、测试建议

### 4.1 单元测试要点

1. **测试 `evaluate_checkpoint` 函数**
   ```python
   # 测试各种操作符
   assert evaluate_checkpoint(
       {"expectations": [{"left": "summary.count", "op": ">", "right": 0}]},
       state_with_count_5,
       step_result
   ) == (True, None)
   
   # 测试嵌套路径
   assert evaluate_checkpoint(
       {"expectations": [{"left": "outline.sections.0.title", "op": "==", "right": "引言"}]},
       state_with_outline,
       step_result
   ) == (True, None)
   ```

2. **测试控制流逻辑**
   - 测试重试计数器是否正确递增
   - 测试重试超限后是否继续执行
   - 测试 goto 跳转是否准确
   - 测试 set_state 是否正确应用

### 4.2 集成测试要点

1. **测试重试流程**
   - 构造一个总是失败的工具
   - 设置 `retry_limit: 3`
   - 验证是否重试3次后继续执行

2. **测试回退流程**
   - 步骤3设置 `on_fail: { goto: 2 }`
   - 让步骤3的 checkpoint 失败
   - 验证是否跳转回步骤2

3. **测试组合流程**
   - 设置 `on_fail: { retry_limit: 2, goto: 1 }`
   - 验证：先重试2次，超限后跳转到步骤1

### 4.3 前端测试要点

1. **验证新增的 SSE 事件**
   - `stage_retry`: 显示重试提示
   - `stage_jump`: 显示跳转提示
   - `stage_fallback`: 显示兜底状态应用提示

2. **验证 Mermaid 流程图**
   - 是否正确显示决策节点（菱形）
   - 是否正确显示重试箭头（回到自身）
   - 是否正确显示跳转箭头（跳到其他步骤）

---

## 五、注意事项与最佳实践

### 5.1 避免无限循环

**问题**: 如果 checkpoint 配置不当，可能导致无限循环

**解决方案**:
1. 执行器设置了 `max_iterations = len(steps) * 10` 作为安全阈值
2. 建议在 `on_fail` 中合理设置 `retry_limit`
3. 避免循环跳转（如步骤2跳到步骤3，步骤3又跳回步骤2）

**最佳实践**:
```json
{
  "on_fail": {
    "retry_limit": 3,  // 先尝试重试
    "goto": 1          // 重试超限后才跳转
  }
}
```

### 5.2 状态键命名规范

**建议**:
- 使用蛇形命名法（`document_ids`、`sections_count`）
- 保持一致性（如都用 `_count` 后缀表示数量）
- 使用有意义的名称（避免 `data1`、`result2` 这样的名称）

**标准字段**:
- `success`: 布尔值，表示是否成功
- `error`: 字符串，错误信息（可选）
- `{entity}_count`: 整数，实体数量
- `{entity}_ids`: 数组，实体ID列表
- `{entity}s`: 数组，实体对象列表

### 5.3 checkpoint 期望设计原则

**原则1: 明确且可验证**
```json
// ✅ 好的设计
{"left": "summary.document_count", "op": ">", "right": 0}

// ❌ 不好的设计（依赖不存在的字段）
{"left": "documents.length", "op": ">", "right": 0}
```

**原则2: 关注关键指标**
```json
// ✅ 好的设计（检查实质性结果）
{"left": "summary.sections_count", "op": ">", "right": 0}

// ❌ 不好的设计（只检查成功标志）
{"left": "success", "op": "==", "right": true}
```

**原则3: 合理的阈值**
```json
// ✅ 好的设计
{"left": "summary.word_count", "op": ">=", "right": 500}

// ❌ 不好的设计（阈值过高，很难满足）
{"left": "summary.word_count", "op": ">=", "right": 10000}
```

### 5.4 工具开发建议

**新增工具时，务必做到**:
1. 明确定义 `output_schema`（包含所有返回字段）
2. 在 `_extract_step_summary` 中添加对应的摘要提取逻辑
3. 确保工具返回的数据结构与 `output_schema` 一致

**示例**:
```python
# 1. 注册工具时定义 output_schema
register_tool(
    name="my_new_tool",
    func=my_new_tool,
    output_schema={
        "success": {"type": "boolean"},
        "result_count": {"type": "integer"},
        "items": {"type": "array"}
    }
)

# 2. 在 _extract_step_summary 中添加提取逻辑
def _extract_step_summary(step_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
    # ... 其他工具的处理 ...
    
    elif step_name == "my_new_tool":
        summary["result_count"] = result.get("result_count", 0)
        summary["items_preview"] = result.get("items", [])[:5]
    
    return summary
```

### 5.5 调试技巧

**查看执行状态**:
- 在执行器中添加日志：`logger.debug(f"当前状态: {state.intermediate_data}")`
- 检查 checkpoint 评估结果：观察 `✅ checkpoint通过` 或 `❌ checkpoint未通过` 日志

**排查控制流问题**:
1. 检查状态键路径是否正确（大小写、拼写）
2. 检查操作符是否正确（`>` vs `>=`）
3. 检查阈值是否合理
4. 检查 `_extract_step_summary` 是否正确提取了该工具的摘要

**前端调试**:
- 使用浏览器开发者工具查看 SSE 事件流
- 检查是否收到 `stage_retry`、`stage_jump`、`stage_fallback` 事件
- 验证 Mermaid 流程图语法是否正确

---

## 六、性能优化建议

### 6.1 状态压缩

执行器中已实现 `compress_state_for_llm` 函数，用于压缩状态以供 LLM 使用：
- 文档内容只保留元数据（标题、长度）
- 大纲只保留前3个章节
- 历史步骤只保留最近5个

**如果需要进一步优化**:
- 减少 `max_steps` 参数（默认5）
- 减少 `max_context_chars` 参数（默认8000）

### 6.2 减少 LLM 调用

**当前设计**: 每个步骤都调用 LLM 构造参数

**优化方向**:
- 对于参数固定的步骤，可以在 Agent 定义中直接指定 `parameters`
- LLM 构造参数时会优先使用已指定的参数

**示例**:
```json
{
  "step": 2,
  "name": "multi_query_search",
  "parameters": {
    "top_k": 20,
    "enable_deduplication": true
  },
  "checkpoint": {...}
}
```

---

## 七、未来扩展方向

### 7.1 条件分支（if/else）

当前设计支持 `on_fail` 处理失败情况，可以扩展为：

```json
{
  "checkpoint": {
    "expectations": [...],
    "on_pass": { "goto": 5 },  // 通过时跳到步骤5
    "on_fail": { "goto": 3 }   // 失败时跳到步骤3
  }
}
```

### 7.2 并行执行

对于无依赖的步骤，可以并行执行：

```json
{
  "step": 2,
  "parallel_steps": [
    {"name": "tool_a"},
    {"name": "tool_b"}
  ]
}
```

### 7.3 子流程

支持调用其他 Agent 作为子流程：

```json
{
  "step": 3,
  "type": "agent",
  "name": "sub_agent_name",
  "inherit_state": true  // 继承父流程的状态
}
```

---

## 八、总结

本次优化实现了完整的Agent控制流功能，核心改进包括：

1. ✅ **动态能力目录**: 工具能力和状态键自动生成，无需手动维护
2. ✅ **结构化控制流**: checkpoint 配置可程序化执行
3. ✅ **执行器重构**: 支持重试、跳转、兜底等控制逻辑
4. ✅ **状态管理优化**: 统一的 state dict + 自动摘要提取
5. ✅ **前端事件增强**: 新增 stage_retry、stage_jump、stage_fallback 事件

**测试时重点关注**:
- 工具的 `output_schema` 是否完整
- checkpoint 的状态键路径是否正确
- 控制流逻辑是否按预期执行
- Mermaid 流程图是否正确展示控制流

**如有问题，请检查**:
1. 工具是否正确注册了 `output_schema`
2. `_extract_step_summary` 是否处理了该工具
3. checkpoint 的状态键路径是否存在于 state dict 中
4. 控制流逻辑是否合理（避免无限循环）

---

**修改完成日期**: 2025-12-01  
**修改人**: AI Assistant  
**版本**: v2.0
