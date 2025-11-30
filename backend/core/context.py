"""
执行上下文管理器

提供统一的依赖注入机制，简化工具和智能体的参数传递
"""

from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from loguru import logger

from core.agents.base import AgentContext
from core.tools.base import ToolContext

# ==================== 上下文变量（线程/协程安全） ====================

_current_context: ContextVar[Optional["ExecutionContext"]] = ContextVar(
    "execution_context", default=None
)


# ==================== 统一执行上下文 ====================


class ExecutionContext:
    """
    统一执行上下文

    封装所有依赖，支持在工具和智能体之间共享状态
    """

    def __init__(
        self,
        db: Any = None,
        es_client: Any = None,
        es_index: str = "dochive_documents",
        user_id: Optional[int] = None,
        template_id: Optional[int] = None,
        session_id: Optional[str] = None,
        query: str = "",
        **extra,
    ):
        self.db = db
        self.es_client = es_client
        self.es_index = es_index
        self.user_id = user_id
        self.template_id = template_id
        self.session_id = session_id
        self.query = query
        self.extra = extra

        # 中间数据存储（用于在执行步骤之间传递数据）
        self._intermediate_data: Dict[str, Any] = {}

    # ==================== 中间数据管理 ====================

    def set_data(self, key: str, value: Any):
        """存储中间数据"""
        self._intermediate_data[key] = value

    def get_data(self, key: str, default: Any = None) -> Any:
        """获取中间数据"""
        return self._intermediate_data.get(key, default)

    def clear_data(self):
        """清空中间数据"""
        self._intermediate_data.clear()

    @property
    def intermediate_data(self) -> Dict[str, Any]:
        """获取中间数据字典（只读）"""
        return self._intermediate_data

    # ==================== 上下文转换 ====================

    def to_tool_context(self) -> ToolContext:
        """转换为工具上下文"""
        return ToolContext(
            db=self.db,
            es_client=self.es_client,
            es_index=self.es_index,
            user_id=self.user_id,
            template_id=self.template_id,
            session_id=self.session_id,
            extra={**self.extra, **self._intermediate_data},
        )

    def to_agent_context(self) -> AgentContext:
        """转换为智能体上下文"""
        return AgentContext(
            db=self.db,
            es_client=self.es_client,
            es_index=self.es_index,
            user_id=self.user_id,
            template_id=self.template_id,
            session_id=self.session_id,
            query=self.query,
            extra={**self.extra, **self._intermediate_data},
        )

    # ==================== 上下文管理器协议 ====================

    def __enter__(self):
        """进入上下文"""
        self._token = _current_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        _current_context.reset(self._token)
        return False

    async def __aenter__(self):
        """异步进入上下文"""
        self._token = _current_context.set(self)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步退出上下文"""
        _current_context.reset(self._token)
        return False


# ==================== 上下文访问函数 ====================


def get_current_context() -> Optional[ExecutionContext]:
    """获取当前执行上下文"""
    return _current_context.get()


def require_context() -> ExecutionContext:
    """获取当前上下文，如果不存在则抛出异常"""
    ctx = _current_context.get()
    if ctx is None:
        raise RuntimeError("没有活跃的执行上下文，请在 ExecutionContext 内部调用")
    return ctx


# ==================== 便捷函数 ====================


async def run_with_context(
    func,
    db: Any = None,
    es_client: Any = None,
    es_index: str = "dochive_documents",
    user_id: Optional[int] = None,
    template_id: Optional[int] = None,
    session_id: Optional[str] = None,
    query: str = "",
    **extra,
):
    """
    在上下文中运行函数

    用法:
    ```python
    result = await run_with_context(
        lambda ctx: some_async_function(ctx),
        db=db,
        es_client=es_client,
        template_id=1,
    )
    ```
    """
    async with ExecutionContext(
        db=db,
        es_client=es_client,
        es_index=es_index,
        user_id=user_id,
        template_id=template_id,
        session_id=session_id,
        query=query,
        **extra,
    ) as ctx:
        return await func(ctx)


# ==================== 工具和智能体的便捷执行函数 ====================


async def call_tool(name: str, **arguments) -> Dict[str, Any]:
    """
    在当前上下文中调用工具

    用法:
    ```python
    async with ExecutionContext(db=db, es_client=es) as ctx:
        result = await call_tool("get_template_statistics", template_id=1)
    ```
    """
    from core.tools.base import execute_tool

    ctx = require_context()
    return await execute_tool(name, arguments, ctx.to_tool_context())


async def call_agent(name: str, **kwargs) -> Dict[str, Any]:
    """
    在当前上下文中调用智能体

    用法:
    ```python
    async with ExecutionContext(db=db, es_client=es, query="xxx") as ctx:
        result = await call_agent("retrieval_agent", top_k=10)
    ```
    """
    from core.agents.base import execute_agent

    ctx = require_context()
    return await execute_agent(name, ctx.to_agent_context(), **kwargs)
