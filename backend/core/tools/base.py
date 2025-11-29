"""
工具基类和装饰器

提供 @tool 装饰器实现工具的自动注册和 Schema 生成
"""

import inspect
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints

from loguru import logger

# ==================== 全局注册表 ====================

_TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ==================== 类型映射 ====================

PYTHON_TYPE_TO_JSON_SCHEMA = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
    List: "array",
    Dict: "object",
}


def python_type_to_json_type(py_type: Type) -> str:
    """将 Python 类型转换为 JSON Schema 类型"""
    # 处理 Optional 类型
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        # List[int] -> array
        if origin is list:
            return "array"
        # Dict[str, Any] -> object
        if origin is dict:
            return "object"

    return PYTHON_TYPE_TO_JSON_SCHEMA.get(py_type, "string")


# ==================== 工具装饰器 ====================


def tool(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]] = None,
    required: Optional[List[str]] = None,
    category: str = "general",
    tags: Optional[List[str]] = None,
):
    """
    工具装饰器 - 将函数注册为可调用的工具

    使用方式:
    ```python
    @tool(
        name="get_template_statistics",
        description="获取指定模板的统计信息",
        parameters={
            "template_id": {
                "type": "integer",
                "description": "模板ID"
            }
        },
        required=["template_id"],
        category="statistics",
        tags=["统计", "模板"]
    )
    async def get_template_statistics(ctx: ToolContext, template_id: int):
        ...
    ```

    Args:
        name: 工具名称（唯一标识）
        description: 工具描述（供 LLM 理解）
        parameters: 参数定义（JSON Schema 格式）
        required: 必需参数列表
        category: 工具分类（retrieval/document/statistics/analysis）
        tags: 标签列表（用于筛选和分组）
    """

    def decorator(func: Callable):
        # 构建完整的 JSON Schema
        param_schema = {
            "type": "object",
            "properties": parameters or {},
            "required": required or [],
        }

        # 构建工具 Schema（OpenAI function calling 格式）
        tool_schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": param_schema,
            },
        }

        # 注册到全局注册表
        _TOOL_REGISTRY[name] = {
            "name": name,
            "description": description,
            "schema": tool_schema,
            "handler": func,
            "category": category,
            "tags": tags or [],
            "is_async": inspect.iscoroutinefunction(func),
        }

        logger.debug(f"注册工具: {name} (category={category})")

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        # 保留原函数的元信息
        wrapper._tool_name = name
        wrapper._tool_schema = tool_schema

        return wrapper

    return decorator


# ==================== 工具上下文 ====================


class ToolContext:
    """
    工具执行上下文 - 封装所有依赖

    统一管理工具执行时需要的各种资源，避免参数传递混乱
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
        """从 extra 中获取值"""
        return self.extra.get(key, default)

    def set(self, key: str, value: Any):
        """设置 extra 值"""
        self.extra[key] = value


# ==================== 注册表访问函数 ====================


def get_tool(name: str) -> Optional[Dict[str, Any]]:
    """获取指定工具的注册信息"""
    return _TOOL_REGISTRY.get(name)


def get_all_tools() -> Dict[str, Dict[str, Any]]:
    """获取所有已注册的工具"""
    return _TOOL_REGISTRY.copy()


def get_tools_by_category(category: str) -> Dict[str, Dict[str, Any]]:
    """按分类获取工具"""
    return {
        name: info
        for name, info in _TOOL_REGISTRY.items()
        if info.get("category") == category
    }


def get_tools_schema_list() -> List[Dict[str, Any]]:
    """获取所有工具的 Schema 列表（供 LLM 使用）"""
    return [info["schema"] for info in _TOOL_REGISTRY.values()]


def get_tools_description() -> str:
    """获取工具的文本描述（供 Prompt 使用）"""
    tools_list = []
    for i, (name, info) in enumerate(_TOOL_REGISTRY.items()):
        desc = info.get("description", "")
        category = info.get("category", "general")
        tools_list.append(f"{i+1}. **{name}** [{category}]: {desc}")

    return "\n".join(tools_list)


# ==================== 工具执行器 ====================


async def execute_tool(
    name: str,
    arguments: Dict[str, Any],
    ctx: ToolContext,
) -> Dict[str, Any]:
    """
    执行工具

    Args:
        name: 工具名称
        arguments: 工具参数
        ctx: 工具上下文

    Returns:
        工具执行结果
    """
    tool_info = _TOOL_REGISTRY.get(name)

    if not tool_info:
        return {
            "success": False,
            "error": f"未知的工具: {name}",
        }

    handler = tool_info["handler"]

    try:
        logger.info(f"执行工具: {name}, 参数: {arguments}")

        # 调用工具函数，传入上下文和参数
        if tool_info["is_async"]:
            result = await handler(ctx, **arguments)
        else:
            result = handler(ctx, **arguments)

        logger.info(f"工具执行成功: {name}")
        return result

    except Exception as e:
        logger.error(f"执行工具 {name} 失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"工具执行失败: {str(e)}",
        }


# ==================== 工具发现（显式导入模式） ====================


def discover_tools():
    """
    发现并注册所有工具

    通过导入各模块触发 @tool 装饰器执行
    """
    # 导入所有工具模块（装饰器会自动注册）
    from core.tools.analysis import document_analyzer_v2
    from core.tools.document import (
        get_document_contents_v2,
        read_documents_v2,
        skim_documents_v2,
    )
    from core.tools.retrieval import es_fulltext_search_v2, sql_structured_search_v2
    from core.tools.statistics import (
        get_document_types_info_v2,
        get_template_statistics_v2,
        list_all_templates_v2,
        search_documents_by_classification_v2,
    )

    logger.info(f"工具发现完成，共注册 {len(_TOOL_REGISTRY)} 个工具")
    return _TOOL_REGISTRY
