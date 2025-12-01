"""Agent编辑相关Schema"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============= Agent定义相关 =============


class AgentStepSchema(BaseModel):
    """Agent执行步骤"""

    step: int = Field(..., ge=1, description="步骤序号")
    type: str = Field(..., description="类型: tool | agent")
    name: str = Field(..., description="工具或智能体名称")
    description: str = Field(..., description="步骤描述")
    parameters: Optional[Dict[str, Any]] = Field(None, description="步骤参数")
    condition: Optional[str] = Field(
        None, description="执行条件（已弃用，建议使用checkpoint）")
    checkpoint: Optional[Dict[str, Any]] = Field(
        None,
        description="""
        检查点配置，用于控制流程：
        {
            "expectations": [{ "left": "summary.xxx", "op": ">", "right": 0 }],
            "on_fail": { "retry_limit": 2, "goto": 1, "set_state": {...} }
        }
        """
    )


class AgentDefinitionSchema(BaseModel):
    """Agent定义"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent名称")
    description: str = Field(..., description="Agent描述")
    template_id: Optional[int] = Field(None, description="关联的模板ID")
    execution_pattern: str = Field(
        ...,
        description="执行模式: tool_only | agent_only | agent_chain | hybrid | llm_direct",
    )
    steps: List[AgentStepSchema] = Field(..., min_length=1, description="执行步骤")
    version: str = Field("1.0", description="版本号")
    is_active: bool = Field(True, description="是否激活")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")


class AgentMarkdownRequest(BaseModel):
    """Agent Markdown编辑请求"""

    content: str = Field(..., description="Markdown格式的Agent定义")
    template_id: Optional[int] = Field(None, description="模板ID")


class AgentMarkdownParseResponse(BaseModel):
    """Agent Markdown解析响应"""

    success: bool = Field(..., description="是否成功解析")
    agent: Optional[AgentDefinitionSchema] = Field(
        None, description="解析后的Agent定义"
    )
    errors: List[str] = Field(default_factory=list, description="错误信息")
    warnings: List[str] = Field(default_factory=list, description="警告信息")


class AgentCreateRequest(BaseModel):
    """创建Agent请求"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(...)
    template_id: Optional[int] = Field(None)
    markdown_content: str = Field(..., description="Markdown格式定义")


class AgentUpdateRequest(BaseModel):
    """更新Agent请求"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    markdown_content: Optional[str] = None
    is_active: Optional[bool] = None


class AgentResponse(BaseModel):
    """Agent响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    template_id: Optional[int]
    execution_pattern: str
    steps: List[Dict[str, Any]]
    version: str
    is_active: bool
    metadata: Optional[Dict[str, Any]]
    markdown_content: Optional[str]
    created_at: datetime
    updated_at: datetime
    creator_id: Optional[int]


class AgentExecutionRequest(BaseModel):
    """执行Agent请求"""

    agent_id: int = Field(..., description="Agent ID")
    query: str = Field(..., description="用户查询")
    template_id: int = Field(..., description="模板ID")
    parameters: Optional[Dict[str, Any]] = Field(None, description="自定义参数")


class AgentExecutionResponse(BaseModel):
    """执行Agent响应"""

    success: bool
    answer: Optional[str] = None
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    execution_plan: List[Dict[str, Any]] = Field(default_factory=list)
    step_results: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
