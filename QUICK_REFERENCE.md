# Agent 控制流优化 - 快速参考

## 修改文件清单

| 文件                                           | 修改内容                                                 | 重要性 |
| ---------------------------------------------- | -------------------------------------------------------- | ------ |
| `backend/core/tools/base.py`                   | 新增 `get_tools_catalog()` 和 `get_state_keys_catalog()` | ⭐⭐⭐    |
| `backend/schemas/agent_schemas.py`             | 新增 `checkpoint` 字段                                   | ⭐⭐⭐    |
| `backend/core/agent_editor.py`                 | 更新 prompt，支持 checkpoint                             | ⭐⭐⭐    |
| `backend/core/agents/custom_agent_executor.py` | 新增 `evaluate_checkpoint()`，重构 `execute()`           | ⭐⭐⭐    |

## 核心改进

### 1. 动态工具能力目录
```python
# 自动生成工具能力目录
tools_catalog = get_tools_catalog()
# 包含: name, description, input_schema, output_schema
```

### 2. checkpoint 结构
```json
{
  "checkpoint": {
    "expectations": [
      { "left": "summary.count", "op": ">", "right": 0 }
    ],
    "on_fail": {
      "retry_limit": 3,
      "goto": 2,
      "set_state": { "data": {} }
    }
  }
}
```

### 3. 控制流执行
- **重试**: `retry_limit` 限制重试次数
- **跳转**: `goto` 跳转到指定步骤
- **兜底**: `set_state` 应用默认状态

## 新增 SSE 事件

| 事件名           | 说明     | 数据字段                     |
| ---------------- | -------- | ---------------------------- |
| `stage_retry`    | 步骤重试 | `retry_count`, `retry_limit` |
| `stage_jump`     | 跳转步骤 | `target_step`                |
| `stage_fallback` | 应用兜底 | `fallback_state`             |

## 测试要点

### ✅ 必须测试
1. 工具的 `output_schema` 是否完整
2. checkpoint 状态键路径是否正确
3. 重试逻辑是否按预期执行
4. goto 跳转是否准确
5. Mermaid 流程图是否展示控制流

### ⚠️ 常见问题
1. **状态键不存在**: 检查 `output_schema` 是否定义该字段
2. **checkpoint 总是失败**: 检查路径和阈值是否正确
3. **无限循环**: 检查 `retry_limit` 和 `goto` 配置

## 快速示例

### 添加工具 output_schema
```python
register_tool(
    name="my_tool",
    func=my_tool,
    output_schema={
        "success": {"type": "boolean"},
        "result_count": {"type": "integer"}
    }
)
```

### 定义 Agent 步骤
```json
{
  "step": 1,
  "name": "my_tool",
  "checkpoint": {
    "expectations": [
      { "left": "summary.result_count", "op": ">", "right": 0 }
    ],
    "on_fail": { "retry_limit": 3 }
  }
}
```

### 添加摘要提取
```python
def _extract_step_summary(step_name: str, result: Dict) -> Dict:
    if step_name == "my_tool":
        summary["result_count"] = result.get("result_count", 0)
    return summary
```

## 关键注意事项

### 🔴 必须做
- 为所有工具定义 `output_schema`
- 在 `_extract_step_summary` 中处理新工具
- 测试 checkpoint 配置是否合理

### 🟡 建议做
- 使用标准字段名（`_count`、`_ids`、`success`）
- 合理设置 `retry_limit`（建议 2-3 次）
- 避免循环跳转

### ⚪ 可选做
- 优化状态压缩参数
- 自定义 SSE 事件处理
- 扩展 checkpoint 功能

## 调试命令

```bash
# 查看工具能力目录
python -c "from core.tools.base import get_tools_catalog; print(get_tools_catalog())"

# 查看状态键目录
python -c "from core.tools.base import get_state_keys_catalog; print(get_state_keys_catalog())"
```

## 文档链接

- 详细修改文档: `CHANGELOG_CONTROL_FLOW.md`
- 优化方案: `optimize.md`
- Agent 定义示例: `backend/agents/control_writer_agent.md`
