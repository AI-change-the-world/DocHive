# 智能体与工具系统重构指南

## 概述

本次重构采用**装饰器 + 自动注册**模式，简化工具和智能体的开发流程。

### 核心改进

| 改进点 | 旧方式 | 新方式 |
|--------|--------|--------|
| 添加新工具 | 修改 4 处代码 | 只需 1 个文件 + 1 行导入 |
| Schema 定义 | 手动维护，易不同步 | 装饰器自动生成 |
| 参数传递 | 每个工具参数格式不同 | 统一使用 `ToolContext` |
| 工具调用 | 大量 if-elif 分支 | 统一 `execute_tool()` |

---

## 文件结构

```
backend/services/
├── agents/
│   ├── __init__.py           # 智能体模块入口
│   ├── base.py               # 🆕 智能体基类 + @agent 装饰器
│   ├── master_router.py      # 主路由器
│   ├── qa_agent_v2.py        # 问答智能体
│   └── retrieval_agent_v2.py # 检索智能体
├── tools/
│   ├── __init__.py           # 工具模块入口
│   ├── base.py               # 🆕 工具基类 + @tool 装饰器
│   ├── tool_registry.py      # 兼容层（旧代码可继续使用）
│   ├── retrieval/            # 检索类工具
│   ├── document/             # 文档类工具
│   ├── statistics/           # 统计类工具
│   └── analysis/             # 分析类工具
├── context.py                # 🆕 统一执行上下文
└── registry.py               # 统一注册中心
```

---

## 如何创建新工具

### 步骤 1：创建工具文件

在对应分类目录下创建 Python 文件，使用 `@tool` 装饰器：

```python
# backend/services/tools/statistics/my_new_tool.py

from typing import Any, Dict
from loguru import logger
from services.tools.base import tool, ToolContext


@tool(
    name="my_new_tool",                    # 工具名称（唯一标识）
    description="这是我的新工具，用于...",   # 工具描述（供 LLM 理解）
    parameters={                           # 参数定义（JSON Schema 格式）
        "template_id": {
            "type": "integer",
            "description": "模板ID"
        },
        "keyword": {
            "type": "string",
            "description": "搜索关键词"
        },
        "limit": {
            "type": "integer",
            "description": "返回数量限制，默认10",
            "default": 10
        }
    },
    required=["template_id", "keyword"],   # 必需参数
    category="statistics",                 # 分类：retrieval/document/statistics/analysis
    tags=["搜索", "统计"]                   # 标签（可选）
)
async def my_new_tool(
    ctx: ToolContext,                      # 第一个参数必须是 ToolContext
    template_id: int,
    keyword: str,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    我的新工具实现

    Args:
        ctx: 工具上下文，包含 db、es_client 等依赖
        template_id: 模板ID
        keyword: 搜索关键词
        limit: 返回数量限制

    Returns:
        执行结果字典，必须包含 success 字段
    """
    # 从上下文获取依赖
    db = ctx.db
    es_client = ctx.es_client

    try:
        # 实现你的逻辑...
        results = []

        logger.info(f"✅ my_new_tool 执行成功")

        return {
            "success": True,
            "results": results,
            "count": len(results),
        }

    except Exception as e:
        logger.error(f"❌ my_new_tool 执行失败: {e}")
        return {
            "success": False,
            "error": str(e),
        }
```

### 步骤 2：注册工具

在 `backend/services/tools/__init__.py` 中添加导入：

```python
# backend/services/tools/__init__.py

# ... 其他导入 ...

# 🆕 添加新工具导入
from services.tools.statistics.my_new_tool import my_new_tool

__all__ = [
    # ... 其他导出 ...
    "my_new_tool",  # 🆕 添加到导出列表
]
```

**完成！** 工具会自动注册到系统中，LLM 可以直接使用。

---

## ToolContext 说明

`ToolContext` 是统一的依赖注入容器，包含工具执行时需要的所有资源：

```python
class ToolContext:
    db: AsyncSession          # 数据库会话
    es_client: Any            # Elasticsearch 客户端
    es_index: str             # ES 索引名（默认 "dochive_documents"）
    user_id: Optional[int]    # 用户ID
    template_id: Optional[int] # 模板ID
    session_id: Optional[str]  # 会话ID
    extra: Dict[str, Any]     # 额外数据
```

使用示例：

```python
async def my_tool(ctx: ToolContext, param1: str):
    # 获取数据库会话
    db = ctx.db

    # 获取 ES 客户端
    es = ctx.es_client
    es_index = ctx.es_index

    # 获取模板ID（如果在上下文中设置了）
    template_id = ctx.template_id

    # 获取额外数据
    custom_value = ctx.get("custom_key", default_value)
```

---

## 如何创建新智能体

### 步骤 1：创建智能体文件

```python
# backend/services/agents/my_new_agent.py

from typing import Any, Dict, List
from loguru import logger
from services.agents.base import agent, BaseAgent, AgentContext, AgentResult


@agent(
    name="my_new_agent",
    description="我的新智能体 - 负责...",
    capabilities=[
        "能力1：分析用户意图",
        "能力2：执行复杂任务",
    ],
    input_schema={
        "query": "用户查询",
        "option": "可选参数",
    },
    output_schema={
        "result": "处理结果",
        "details": "详细信息",
    },
    scenarios=[
        "场景1：当用户需要...",
        "场景2：当系统需要...",
    ]
)
class MyNewAgent(BaseAgent):
    """我的新智能体"""

    async def execute(
        self,
        query: str = None,
        option: str = None,
        **kwargs,
    ) -> AgentResult:
        """
        执行智能体逻辑

        Args:
            query: 用户查询（可从 self.ctx.query 获取）
            option: 可选参数

        Returns:
            AgentResult: 标准化执行结果
        """
        # 使用传入的 query 或上下文中的 query
        actual_query = query or self.ctx.query

        # 获取依赖
        db = self.ctx.db
        template_id = self.ctx.template_id

        # 使用日志
        self.logger.info(f"开始执行: {actual_query}")

        try:
            # 实现逻辑...
            result_data = {"key": "value"}

            return AgentResult(
                success=True,
                data=result_data,
                answer="处理完成",  # 可选：生成的答案
            )

        except Exception as e:
            self.logger.error(f"执行失败: {e}")
            return AgentResult(
                success=False,
                error=str(e),
                data={},
            )

    async def pre_execute(self, **kwargs):
        """执行前钩子（可选）"""
        self.logger.info("预处理...")
        return kwargs

    async def post_execute(self, result: AgentResult) -> AgentResult:
        """执行后钩子（可选）"""
        self.logger.info("后处理...")
        return result


# 便捷调用接口（可选）
async def run_my_new_agent(
    query: str,
    db,
    template_id: int = None,
    **kwargs,
) -> Dict[str, Any]:
    """便捷调用接口"""
    ctx = AgentContext(
        db=db,
        template_id=template_id,
        query=query,
    )

    agent_instance = MyNewAgent(ctx)
    result = await agent_instance.run(**kwargs)

    return {
        "success": result.get("success", False),
        "data": result.get("data", {}),
        "error": result.get("error"),
    }
```

### 步骤 2：注册智能体

在 `backend/services/agents/__init__.py` 中添加导入：

```python
# backend/services/agents/__init__.py

# ... 其他导入 ...

# 🆕 添加新智能体导入
from services.agents.my_new_agent import MyNewAgent, run_my_new_agent

__all__ = [
    # ... 其他导出 ...
    "MyNewAgent",
    "run_my_new_agent",
]
```

---

## 调用工具和智能体

### 方式 1：直接使用 execute_tool / execute_agent

```python
from services.tools.base import ToolContext, execute_tool
from services.agents.base import AgentContext, execute_agent

# 调用工具
tool_ctx = ToolContext(db=db, es_client=es_client, template_id=1)
result = await execute_tool("my_new_tool", {"keyword": "test"}, tool_ctx)

# 调用智能体
agent_ctx = AgentContext(db=db, template_id=1, query="用户问题")
result = await execute_agent("my_new_agent", agent_ctx, option="value")
```

### 方式 2：使用 ExecutionContext（推荐）

```python
from services.context import ExecutionContext, call_tool, call_agent

async with ExecutionContext(
    db=db,
    es_client=es_client,
    template_id=1,
    query="用户问题",
) as ctx:
    # 调用工具
    tool_result = await call_tool("my_new_tool", keyword="test")

    # 调用智能体
    agent_result = await call_agent("my_new_agent", option="value")
```

### 方式 3：在 master_router 中使用

master_router 会自动根据 LLM 的规划调用工具和智能体，只需确保工具/智能体已注册即可。

---

## @tool 装饰器参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | str | ✅ | 工具名称，全局唯一 |
| `description` | str | ✅ | 工具描述，供 LLM 理解 |
| `parameters` | dict | ❌ | 参数定义（JSON Schema） |
| `required` | list | ❌ | 必需参数列表 |
| `category` | str | ❌ | 分类：retrieval/document/statistics/analysis/general |
| `tags` | list | ❌ | 标签列表 |

---

## @agent 装饰器参数说明

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | str | ✅ | 智能体名称，全局唯一 |
| `description` | str | ✅ | 智能体描述 |
| `capabilities` | list | ❌ | 能力列表 |
| `input_schema` | dict | ❌ | 输入参数说明 |
| `output_schema` | dict | ❌ | 输出结果说明 |
| `scenarios` | list | ❌ | 适用场景列表 |

---

## 向后兼容

旧代码仍然可以正常工作：

```python
# 旧方式仍然支持
from services.tools.tool_registry import execute_tool_call

result = await execute_tool_call(
    tool_name="get_template_statistics",
    arguments={"template_id": 1},
    db=db,
    es_client=es_client,
)
```

但建议逐步迁移到新方式，以享受更好的开发体验。

---

## 常见问题

### Q: 工具没有被注册怎么办？

确保：
1. 工具文件使用了 `@tool` 装饰器
2. 在 `tools/__init__.py` 中添加了导入

### Q: 如何查看已注册的工具？

```python
from services.tools.base import get_all_tools, get_tools_description

# 获取所有工具
tools = get_all_tools()
print(tools.keys())

# 获取工具描述（文本格式）
desc = get_tools_description()
print(desc)
```

### Q: 如何在工具中访问其他工具？

```python
from services.tools.base import execute_tool

async def my_tool(ctx: ToolContext, ...):
    # 调用其他工具
    other_result = await execute_tool("other_tool", {"param": "value"}, ctx)
```
