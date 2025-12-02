# Agent 执行器 V2 - 重构说明

## 核心改进

本次重构完全改变了Agent的定义和执行方式,从"静态步骤pipeline"变成"能力导向+动态规划"。

### 1. Agent定义改进

**旧设计(V1):**
- Markdown中写死具体步骤
- 使用符号化checkpoint (`{"left": "summary.xxx", "op": ">", "right": 0}`)
- 步骤固化在数据库中
- 每个任务都需要手写详细步骤

**新设计(V2):**
```markdown
# Agent: 智能问答助手

## 描述
根据用户提问,智能检索相关文档并生成答案

## 目标
- 快速检索相关文档
- 生成准确、完整的答案
- 支持引用来源

## 约束
- 检索文档数不超过50个
- 答案长度不超过1000字
- 必须基于检索的文档回答,不能编造

## 推荐工具(可选)
- retrieval_agent
- qa_agent
```

### 2. 执行流程改进

**旧方式:**
```
用户编写Markdown → LLM解析成固定steps → 存入DB → 执行器读取steps执行
```

**新方式:**
```
用户编写Markdown → LLM提取goals/constraints → 存入DB
                                              ↓
执行时 → LLM根据goals/constraints动态规划steps → 执行器逐步执行 + 自然语言期望判定
```

### 3. 数据结构变化

**数据库模型 (`CustomAgent`):**
```python
# 新增字段
goals: List[str]                    # Agent目标列表
constraints: List[str]              # 执行约束列表
state_schema: Dict[str, Any]        # 状态结构定义(可选)
rollback_plan: Dict[str, str]       # 回退策略表(可选)
initial_plan: List[Dict]            # 初始计划(可选,仅参考)

# 旧字段(兼容)
steps: List[Dict]                   # 已弃用,仅向后兼容
```

**执行状态 (`UnifiedExecutionState`):**
```python
state = {
    "inputs": {"query": ..., "template_id": ...},
    "outline": None,           # 大纲生成工具写入
    "document_ids": [],        # 检索工具写入
    "documents": [],           # 文档内容工具写入
    "extracted_content": None, # 摘取工具写入
    "composed_document": None, # 组合工具写入
    "reviewed_document": None, # 校对工具写入
    "quality": {               # 质量监控
        "retrieval_count": 0,
        "sections_count": 0,
        ...
    },
    "control": {               # 控制信息
        "iterations": 0,
        "max_iterations": 20,
        ...
    }
}
```

### 4. 核心类说明

**`UnifiedExecutionState`** - 统一执行状态
- 基于简化的state dict管理所有数据流
- 提供get_state/set_state方法访问状态
- 自动更新质量指标

**`DynamicPlanner`** - 动态规划器
- 执行时根据Agent定义和query,让LLM规划步骤
- 每个步骤包含:name、description、expectations(自然语言)、on_fail_strategy(自然语言)
- 不使用DB中的静态steps

**`ExpectationEvaluator`** - 期望评估器
- 使用LLM判断执行结果是否满足自然语言描述的期望
- 例如:"检索到至少5个文档"、"大纲包含3个以上章节"
- 返回简单的通过/不通过判定

**`CustomAgentExecutorV2`** - 执行器V2
- 两阶段执行:规划→执行
- 支持自然语言期望判定
- 支持失败策略解析(重试/回退/兜底)
- 基于统一state dict更新数据

## 使用方式

### 创建Agent

```python
# 1. 用户编写Markdown(只需描述目标和约束,不需要写步骤)
markdown_content = """
# Agent: 报表生成助手

## 描述
根据用户要求,自动检索数据并生成报表

## 目标
- 检索相关数据文档
- 生成结构化报表框架
- 填充关键数据
- 格式化输出

## 约束
- 数据必须真实
- 执行时间不超过10分钟
"""

# 2. 调用API创建Agent
POST /api/v1/agents/create
{
    "name": "报表生成助手",
    "description": "...",
    "template_id": 1,
    "markdown_content": "..."
}
```

### 执行Agent

```python
# 调用执行API
POST /api/v1/agents/execute/{agent_id}
{
    "query": "生成2024年销售报表",
    "template_id": 1
}

# 返回SSE事件流:
# - planning: 正在规划
# - execution_plan: 规划完成的步骤列表
# - stage_start: 步骤开始
# - stage_complete: 步骤完成
# - stage_retry: 步骤重试
# - stage_jump: 步骤跳转
# - stage_fallback: 兜底处理
# - answer: 最终答案
# - done: 执行完成
```

## 优势总结

1. **更自然**: 用自然语言描述目标和约束,而非写死步骤
2. **更灵活**: 同一个Agent可以适配不同query,动态规划步骤
3. **更智能**: LLM理解期望和失败策略,自主决策
4. **更简洁**: 去掉复杂的符号化checkpoint
5. **更通用**: 从"写文章助手"扩展到任何任务类型(问答/报表/分类等)

## 兼容性

- 旧的Agent(有steps字段)仍可继续使用
- 新Agent优先使用goals/constraints,但也保存initial_plan作为参考
- 数据库模型支持新旧两种结构
- 执行器V2优先使用动态规划,如果Agent有initial_plan也可以参考

## 下一步优化方向

1. 支持更复杂的控制流(条件分支/并行执行/子流程)
2. 增加全局replanning机制(连续失败时重新规划整体策略)
3. 支持用户自定义state schema(不同任务有不同状态字段)
4. 优化LLM调用成本(缓存规划结果、参数复用等)
5. 增加执行监控dashboard(可视化state变化和质量指标)
