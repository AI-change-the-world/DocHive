"""
工具注册表 - 直接使用 auto_agent

所有工具逻辑已移至 auto_agent 框架，这里只保留兼容层
"""

from typing import Any, Dict

from elasticsearch import AsyncElasticsearch
from sqlalchemy.ext.asyncio import AsyncSession

from core.tools.base import (
    ToolContext,
    execute_tool,
    get_tools_schema_list,
    get_tool_metadata,
    get_all_tools,
    get_tool,
    get_tools_catalog,
    get_tools_description,
)

__all__ = [
    "TOOLS_SCHEMA",
    "execute_tool_call",
    "get_tool_metadata",
    "get_all_tools",
    "get_tool",
    "get_tools_catalog",
    "get_tools_description",
]


# 兼容旧接口：延迟加载工具 Schema
class _LazyToolsSchema:
    def __init__(self):
        self._cache = None

    def _load(self):
        if self._cache is None:
            self._cache = get_tools_schema_list()
        return self._cache

    def __iter__(self):
        return iter(self._load())

    def __len__(self):
        return len(self._load())

    def __getitem__(self, index):
        return self._load()[index]


TOOLS_SCHEMA = _LazyToolsSchema()


async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession,
    es_client: AsyncElasticsearch = None,
    es_index: str = "dochive_documents",
) -> Dict[str, Any]:
    """兼容旧接口：执行工具调用"""
    ctx = ToolContext(
        db=db,
        es_client=es_client,
        es_index=es_index,
        template_id=arguments.get("template_id"),
    )
    return await execute_tool(tool_name, arguments, ctx)
