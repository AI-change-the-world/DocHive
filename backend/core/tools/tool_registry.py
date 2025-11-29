"""
工具注册表和Schema定义（兼容层）

此文件保持向后兼容，实际功能已迁移到 services.tools.base 模块
新代码请使用 services.tools.base 中的 @tool 装饰器和 execute_tool 函数
"""

from typing import Any, Dict

from elasticsearch import AsyncElasticsearch
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

# 从新版基础设施导入
from core.tools.base import ToolContext
from core.tools.base import execute_tool as _execute_tool_new
from core.tools.base import get_tools_schema_list

# ==================== 向后兼容：TOOLS_SCHEMA ====================


# 延迟加载，避免循环导入
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


# ==================== 向后兼容：TOOLS_MAP ====================

# 注意：新版工具使用装饰器自动注册，不再需要手动维护 TOOLS_MAP
# 此处保留空字典，旧代码如果直接访问 TOOLS_MAP 会得到空结果
# 应该使用 execute_tool_call 函数来执行工具
TOOLS_MAP = {}


# ==================== 向后兼容：execute_tool_call ====================


async def execute_tool_call(
    tool_name: str,
    arguments: Dict[str, Any],
    db: AsyncSession,
    es_client: AsyncElasticsearch = None,
    es_index: str = "dochive_documents",
) -> Dict[str, Any]:
    """
    执行工具调用（向后兼容接口）

    此函数保持与旧版相同的接口，内部使用新版工具系统

    Args:
        tool_name: 工具名称
        arguments: 工具参数
        db: 数据库会话
        es_client: Elasticsearch客户端（检索工具需要）
        es_index: ES索引名

    Returns:
        工具执行结果
    """
    # 创建工具上下文
    ctx = ToolContext(
        db=db,
        es_client=es_client,
        es_index=es_index,
        template_id=arguments.get("template_id"),
    )

    try:
        logger.info(f"执行工具: {tool_name}, 参数: {arguments}")

        # 调用新版执行器
        result = await _execute_tool_new(tool_name, arguments, ctx)

        logger.info(f"工具执行成功: {tool_name}")
        return result

    except Exception as e:
        logger.error(f"执行工具 {tool_name} 失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"工具执行失败: {str(e)}",
        }
