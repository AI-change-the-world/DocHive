"""
智能体基类和装饰器

提供 @agent 装饰器和 BaseAgent 基类，实现智能体的自动注册和统一接口
"""

import inspect
from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypedDict

from loguru import logger

# ==================== 全局注册表 ====================

_AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {}


# ==================== 智能体上下文 ====================


class AgentContext:
    """
    智能体执行上下文 - 封装所有依赖

    与 ToolContext 类似，统一管理智能体执行时需要的资源
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
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.db = db
        self.es_client = es_client
        self.es_index = es_index
        self.user_id = user_id
        self.template_id = template_id
        self.session_id = session_id
        self.query = query
        self.extra = extra or {}

    def get(self, key: str, default: Any = None) -> Any:
        """从 extra 中获取值"""
        return self.extra.get(key, default)

    def set(self, key: str, value: Any):
        """设置 extra 值"""
        self.extra[key] = value

    def to_tool_context(self):
        """转换为 ToolContext（供智能体内部调用工具时使用）"""
        from core.tools.base import ToolContext

        return ToolContext(
            db=self.db,
            es_client=self.es_client,
            es_index=self.es_index,
            user_id=self.user_id,
            template_id=self.template_id,
            session_id=self.session_id,
            extra=self.extra,
        )


# ==================== 智能体执行结果 ====================


class AgentResult(TypedDict, total=False):
    """智能体执行结果的标准格式"""

    success: bool
    error: Optional[str]
    data: Dict[str, Any]  # 智能体特定的返回数据
    documents: List[Dict[str, Any]]  # 如果涉及文档
    answer: Optional[str]  # 如果生成了答案


# ==================== 智能体基类 ====================


class BaseAgent(ABC):
    """
    智能体基类

    所有智能体都应该继承此类，实现 execute 方法
    """

    # 子类需要定义的元信息
    name: str = "base_agent"
    description: str = "基础智能体"
    capabilities: List[str] = []
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}
    scenarios: List[str] = []  # 适用场景

    def __init__(self, ctx: AgentContext):
        self.ctx = ctx
        self.logger = logger.bind(agent=self.name)

    @abstractmethod
    async def execute(self, **kwargs) -> AgentResult:
        """
        执行智能体的主要逻辑

        子类必须实现此方法

        Args:
            **kwargs: 智能体特定的参数

        Returns:
            AgentResult: 标准化的执行结果
        """
        pass

    async def pre_execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行前的钩子（可选覆盖）

        用于参数验证、预处理等
        """
        return kwargs

    async def post_execute(self, result: AgentResult) -> AgentResult:
        """
        执行后的钩子（可选覆盖）

        用于结果后处理、日志记录等
        """
        return result

    async def run(self, **kwargs) -> AgentResult:
        """
        运行智能体（带钩子）

        调用顺序：pre_execute -> execute -> post_execute
        """
        try:
            # 预处理
            processed_kwargs = await self.pre_execute(**kwargs)

            # 执行
            result = await self.execute(**processed_kwargs)

            # 后处理
            result = await self.post_execute(result)

            return result

        except Exception as e:
            self.logger.error(f"智能体执行失败: {e}")
            import traceback

            self.logger.error(traceback.format_exc())
            return AgentResult(
                success=False,
                error=str(e),
                data={},
            )

    @classmethod
    def get_schema(cls) -> Dict[str, Any]:
        """获取智能体的 Schema 描述"""
        return {
            "name": cls.name,
            "description": cls.description,
            "capabilities": cls.capabilities,
            "input": cls.input_schema,
            "output": cls.output_schema,
            "scenarios": cls.scenarios,
        }


# ==================== 智能体装饰器 ====================


def agent(
    name: str,
    description: str,
    capabilities: Optional[List[str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    scenarios: Optional[List[str]] = None,
):
    """
    智能体类装饰器 - 自动注册智能体

    使用方式:
    ```python
    @agent(
        name="retrieval_agent",
        description="检索智能体 - 负责从文档库中检索相关文档",
        capabilities=["分析用户查询意图", "执行混合检索"],
        input_schema={"query": "用户查询", "template_id": "模板ID"},
        output_schema={"documents": "文档列表", "total_count": "数量"},
        scenarios=["需要获取文档列表", "作为问答的前置步骤"]
    )
    class RetrievalAgent(BaseAgent):
        async def execute(self, **kwargs):
            ...
    ```

    Args:
        name: 智能体名称（唯一标识）
        description: 智能体描述
        capabilities: 能力列表
        input_schema: 输入参数说明
        output_schema: 输出结果说明
        scenarios: 适用场景
    """

    def decorator(cls: type):
        # 设置类属性
        cls.name = name
        cls.description = description
        cls.capabilities = capabilities or []
        cls.input_schema = input_schema or {}
        cls.output_schema = output_schema or {}
        cls.scenarios = scenarios or []

        # 注册到全局注册表
        _AGENT_REGISTRY[name] = {
            "name": name,
            "description": description,
            "capabilities": capabilities or [],
            "input_schema": input_schema or {},
            "output_schema": output_schema or {},
            "scenarios": scenarios or [],
            "class": cls,
        }

        logger.debug(f"注册智能体: {name}")

        return cls

    return decorator


# ==================== 注册表访问函数 ====================


def get_agent(name: str) -> Optional[Dict[str, Any]]:
    """获取指定智能体的注册信息"""
    return _AGENT_REGISTRY.get(name)


def get_agent_class(name: str) -> Optional[type]:
    """获取指定智能体的类"""
    info = _AGENT_REGISTRY.get(name)
    return info["class"] if info else None


def get_all_agents() -> Dict[str, Dict[str, Any]]:
    """获取所有已注册的智能体"""
    return _AGENT_REGISTRY.copy()


def get_agents_schema_list() -> List[Dict[str, Any]]:
    """获取所有智能体的 Schema 列表"""
    return [
        {
            "name": info["name"],
            "description": info["description"],
            "capabilities": info["capabilities"],
            "input": info["input_schema"],
            "output": info["output_schema"],
            "scenarios": info["scenarios"],
        }
        for info in _AGENT_REGISTRY.values()
    ]


def get_agents_description() -> str:
    """获取智能体的文本描述（供 Prompt 使用）"""
    agents_list = []
    for i, (name, info) in enumerate(_AGENT_REGISTRY.items()):
        desc = info.get("description", "")
        capabilities = info.get("capabilities", [])
        scenarios = info.get("scenarios", [])

        cap_text = "\n     - ".join(capabilities) if capabilities else "无"
        scenario_text = "\n     - ".join(scenarios) if scenarios else "无"

        agents_list.append(
            f"{i+1}. **{name}**: {desc}\n"
            f"   能力:\n     - {cap_text}\n"
            f"   适用场景:\n     - {scenario_text}"
        )

    return "\n\n".join(agents_list)


# ==================== 智能体执行器 ====================


async def execute_agent(
    name: str,
    ctx: AgentContext,
    **kwargs,
) -> AgentResult:
    """
    执行智能体

    Args:
        name: 智能体名称
        ctx: 智能体上下文
        **kwargs: 智能体参数

    Returns:
        AgentResult: 执行结果
    """
    agent_info = _AGENT_REGISTRY.get(name)

    if not agent_info:
        return AgentResult(
            success=False,
            error=f"未知的智能体: {name}",
            data={},
        )

    agent_class = agent_info["class"]

    try:
        logger.info(f"执行智能体: {name}")

        # 创建智能体实例并执行
        agent_instance = agent_class(ctx)
        result = await agent_instance.run(**kwargs)

        logger.info(f"智能体执行完成: {name}, success={result.get('success')}")
        return result

    except Exception as e:
        logger.error(f"执行智能体 {name} 失败: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        return AgentResult(
            success=False,
            error=f"智能体执行失败: {str(e)}",
            data={},
        )


# ==================== 智能体发现 ====================


def discover_agents():
    """
    发现并注册所有智能体

    通过导入各模块触发 @agent 装饰器执行
    """
    from core.agents import qa_agent_v2, retrieval_agent_v2

    logger.info(f"智能体发现完成，共注册 {len(_AGENT_REGISTRY)} 个智能体")
    return _AGENT_REGISTRY
