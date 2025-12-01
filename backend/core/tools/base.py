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
    output_schema: Optional[Dict[str, Any]] = None,
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
        tags=["统计", "模板"],
        output_schema={
            "success": {"type": "boolean", "description": "执行是否成功"},
            "data": {"type": "object", "description": "统计数据"}
        }
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
        output_schema: 输出结构定义（可选，用于标准化输出和参数自动装配）
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
            "output_schema": output_schema,  # 新增：输出结构定义
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


def get_tool_output_schema(name: str) -> Optional[Dict[str, Any]]:
    """
    获取指定工具的输出结构定义

    Args:
        name: 工具名称

    Returns:
        输出结构定义，如果未定义则返回 None
    """
    tool_info = _TOOL_REGISTRY.get(name)
    if not tool_info:
        return None
    return tool_info.get("output_schema")


def get_tool_metadata(name: str) -> Optional[Dict[str, Any]]:
    """
    获取指定工具的完整元数据

    包括参数schema、描述、分类等所有信息

    Args:
        name: 工具名称

    Returns:
        工具元数据字典，如果工具不存在则返回 None
    """
    tool_info = _TOOL_REGISTRY.get(name)
    if not tool_info:
        return None

    # 提取参数schema
    schema = tool_info.get("schema", {})
    function_info = schema.get("function", {})
    parameters = function_info.get("parameters", {})

    return {
        "name": name,
        "description": tool_info.get("description", ""),
        "category": tool_info.get("category", "general"),
        "tags": tool_info.get("tags", []),
        "parameters": parameters,
        "output_schema": tool_info.get("output_schema"),
    }


def get_all_tools_with_output_schema() -> Dict[str, Dict[str, Any]]:
    """
    获取所有定义了输出结构的工具

    Returns:
        包含输出结构的工具字典
    """
    return {
        name: {
            "description": info["description"],
            "output_schema": info["output_schema"],
            "category": info["category"],
        }
        for name, info in _TOOL_REGISTRY.items()
        if info.get("output_schema") is not None
    }


def get_tools_catalog() -> str:
    """
    生成工具能力目录(Tools Catalog)，供LLM规划阶段使用

    包含每个工具的:
    - name / description / capabilities(category+tags)
    - input_schema (参数摘要)
    - output_schema (输出字段与状态键)

    Returns:
        格式化的工具能力目录(Markdown格式)
    """
    catalog_lines = []

    for i, (name, info) in enumerate(_TOOL_REGISTRY.items()):
        desc = info.get("description", "").strip()
        category = info.get("category", "general")
        tags = info.get("tags", [])

        # 构建能力描述
        capabilities = f"[{category}]"
        if tags:
            capabilities += f" {', '.join(tags)}"

        # 获取参数schema
        schema = info.get("schema", {})
        function_info = schema.get("function", {})
        parameters = function_info.get("parameters", {})
        param_props = parameters.get("properties", {})
        required_params = parameters.get("required", [])

        # 简化参数列表(只显示关键参数)
        param_list = []
        for pname, pinfo in param_props.items():
            ptype = pinfo.get("type", "any")
            pdesc = pinfo.get("description", "")[:50]  # 截短描述
            req_mark = "*" if pname in required_params else ""
            param_list.append(f"{pname}{req_mark}: {ptype} - {pdesc}")

        params_text = "\n     - ".join(param_list) if param_list else "无参数"

        # 获取输出schema
        output_schema = info.get("output_schema")
        if output_schema:
            output_keys = list(output_schema.keys())
            output_text = ", ".join(output_keys)
        else:
            output_text = "success(boolean), error?(string), 其他字段未声明"

        # 拼装
        catalog_lines.append(
            f"{i+1}. **{name}** {capabilities}\n"
            f"   描述: {desc[:200]}\n"
            f"   输入参数:\n     - {params_text}\n"
            f"   输出字段: {output_text}"
        )

    return "\n\n".join(catalog_lines)


def get_state_keys_catalog() -> str:
    """
    生成状态键目录(State Keys Catalog)，汇总所有工具可能写入的状态键

    从所有工具的 output_schema 聚合状态键(去重)，说明来源工具与类型

    Returns:
        格式化的状态键目录(Markdown格式)
    """
    # 汇总所有输出键
    state_keys = {}  # key -> {type, description, sources[]}

    for tool_name, info in _TOOL_REGISTRY.items():
        output_schema = info.get("output_schema")
        if not output_schema:
            continue

        for key, schema in output_schema.items():
            if key not in state_keys:
                state_keys[key] = {
                    "type": schema.get("type", "any"),
                    "description": schema.get("description", ""),
                    "sources": []
                }
            # 添加来源工具
            if tool_name not in state_keys[key]["sources"]:
                state_keys[key]["sources"].append(tool_name)

    # 格式化输出
    catalog_lines = []
    for i, (key, details) in enumerate(sorted(state_keys.items())):
        ktype = details["type"]
        kdesc = details["description"][:80]
        ksources = ", ".join(details["sources"])

        catalog_lines.append(
            f"{i+1}. **{key}** ({ktype})\n"
            f"   说明: {kdesc}\n"
            f"   来源工具: {ksources}"
        )

    return "\n\n".join(catalog_lines)


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
        # 根据工具的 schema 过滤参数，只保留工具实际需要的参数
        schema = tool_info.get("schema", {})
        function_info = schema.get("function", {})
        param_schema = function_info.get("parameters", {})
        allowed_params = set(param_schema.get("properties", {}).keys())

        # 过滤参数，只保留工具定义的参数
        filtered_arguments = {k: v for k,
                              v in arguments.items() if k in allowed_params}

        # 记录被过滤掉的参数（用于调试）
        removed_params = set(arguments.keys()) - allowed_params
        if removed_params:
            logger.debug(f"工具 {name} 过滤掉不需要的参数: {removed_params}")

        logger.info(f"执行工具: {name}, 参数: {filtered_arguments}")

        # 调用工具函数，传入上下文和参数
        if tool_info["is_async"]:
            result = await handler(ctx, **filtered_arguments)
        else:
            result = handler(ctx, **filtered_arguments)

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
        document_compose,
        document_extraction,
        document_review,
        generate_outline,
        get_document_contents_v2,
        read_documents_v2,
        skim_documents_v2,
    )
    from core.tools.retrieval import (
        es_fulltext_search_v2,
        multi_query_search,
        sql_structured_search_v2,
    )
    from core.tools.statistics import (
        get_document_types_info_v2,
        get_template_statistics_v2,
        list_all_templates_v2,
        search_documents_by_classification_v2,
    )

    logger.info(f"工具发现完成，共注册 {len(_TOOL_REGISTRY)} 个工具")
    return _TOOL_REGISTRY
