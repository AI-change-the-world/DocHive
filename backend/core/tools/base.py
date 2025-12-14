"""
工具模块 - 直接使用 auto_agent 框架

DocHive 只扩展：
- ToolContext: 封装数据库、ES 等依赖
- 便捷函数: 简化工具访问
"""

from typing import Any, Callable, Dict, List, Optional

# 直接从 auto_agent 导入，不做封装
from auto_agent.models import ToolDefinition, ToolParameter, ValidationMode
from auto_agent.tools.base import BaseTool
from auto_agent.tools.registry import (
    ToolRegistry,
    func_tool,
    get_global_registry,
)

__all__ = [
    # auto_agent 核心（直接导出）
    "BaseTool",
    "ToolRegistry",
    "ToolDefinition",
    "ToolParameter",
    "ValidationMode",
    "func_tool",
    "get_global_registry",
    # DocHive 扩展
    "ToolContext",
    # 便捷函数
    "get_tool",
    "get_all_tools",
    "get_tools_by_category",
    "get_tools_schema_list",
    "get_tools_description",
    "get_tools_catalog",
    "get_state_keys_catalog",
    "get_tool_compress_function",
    "get_tool_validate_function",
    "get_tool_output_schema",
    "get_tool_metadata",
    "execute_tool",
]


# ==================== DocHive 扩展 ====================


class ToolContext:
    """
    工具执行上下文 - DocHive 特有

    封装数据库会话、ES 客户端等依赖
    """

    def __init__(
        self,
        db: Any = None,
        es_client: Any = None,
        es_index: str = "dochive_documents",
        user_id: Optional[int] = None,
        template_id: Optional[int] = None,
        session_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.es_client = es_client
        self.es_index = es_index
        self.user_id = user_id
        self.template_id = template_id
        self.session_id = session_id
        self.extra = extra or {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key, default)

    def set(self, key: str, value: Any):
        self.extra[key] = value


# ==================== 便捷函数 ====================


def get_tool(name: str):
    """获取工具"""
    return get_global_registry().get_tool(name)


def get_all_tools():
    """获取所有工具（返回字典 {name: tool}）"""
    tools = get_global_registry().get_all_tools()
    return {t.definition.name: t for t in tools}


def get_tools_by_category(category: str):
    """按分类获取工具"""
    return get_global_registry().get_tools_by_category(category)


def get_tools_schema_list():
    """获取工具 Schema 列表"""
    return get_global_registry().get_tools_schema_list()


def get_tools_description():
    """获取工具描述"""
    return get_global_registry().get_tool_descriptions()


def get_tools_catalog():
    """获取工具目录"""
    return get_global_registry().get_tools_catalog()


def get_state_keys_catalog():
    """获取状态键目录"""
    return get_global_registry().get_state_keys_catalog()


def get_tool_compress_function(name: str):
    """获取压缩函数"""
    return get_global_registry().get_compress_function(name)


def get_tool_validate_function(name: str):
    """获取验证函数"""
    return get_global_registry().get_validate_function(name)


def get_tool_output_schema(name: str):
    """获取输出 Schema"""
    t = get_global_registry().get_tool(name)
    if t:
        return t.definition.output_schema
    return None


def get_tool_metadata(name: str):
    """获取工具元数据"""
    t = get_global_registry().get_tool(name)
    if not t:
        return None

    defn = t.definition
    properties = {}
    required = []

    for p in defn.parameters:
        properties[p.name] = {
            "type": p.type,
            "description": p.description,
        }
        if p.enum:
            properties[p.name]["enum"] = p.enum
        if p.default is not None:
            properties[p.name]["default"] = p.default
        if p.required:
            required.append(p.name)

    return {
        "name": defn.name,
        "description": defn.description,
        "category": defn.category,
        "tags": defn.tags,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
        "output_schema": defn.output_schema,
    }


async def execute_tool(name: str, arguments: dict, ctx: ToolContext) -> dict:
    """执行工具"""
    from loguru import logger

    t = get_global_registry().get_tool(name)
    if not t:
        return {"success": False, "error": f"未知工具: {name}"}

    try:
        # 过滤参数
        allowed = {p.name for p in t.definition.parameters}
        filtered = {k: v for k, v in arguments.items() if k in allowed}

        logger.info(f"执行工具: {name}")
        return await t.execute(ctx=ctx, **filtered)

    except Exception as e:
        logger.error(f"工具执行失败: {name}, {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}
