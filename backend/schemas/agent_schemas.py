"""Agent编辑相关Schema"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ============= Agent定义相关 =============


class AgentStepSchema(BaseModel):
    """Agent执行步骤(仅用于初始计划或规划参考)"""

    step: int = Field(..., ge=1, description="步骤序号")
    type: str = Field(..., description="类型: tool | agent")
    name: str = Field(..., description="工具或智能体名称")
    description: str = Field(..., description="步骤描述")
    parameters: Optional[Dict[str, Any]] = Field(None, description="步骤参数(可选)")
    read_fields: Optional[List[str]] = Field(None, description="需要读取的状态字段列表")
    write_fields: Optional[List[str]] = Field(None, description="将写入的状态字段列表")
    expectations: Optional[str] = Field(
        None, description="自然语言描述的期望结果,如'检索到至少5个文档'、'大纲包含3个以上章节'")
    on_fail_strategy: Optional[str] = Field(
        None, description="失败处理策略的自然语言描述,如'重试最多3次'、'回退到步骤2重新检索'")

    # 新增: 固定步骤相关字段
    is_pinned: bool = Field(False, description="是否为固定步骤,固定步骤的参数结构不会被LLM修改")
    pinned_parameters: Optional[Dict[str, Any]] = Field(
        None, description="完全固定的参数,直接使用不经过LLM推断")
    parameter_template: Optional[Dict[str, Any]] = Field(
        None, description="参数模板,包含占位符(如$TOPIC),由LLM根据用户输入推断填充")
    template_variables: Optional[Dict[str, str]] = Field(
        None, description="模板变量说明,如{'$TOPIC': '从用户输入中提取的主题关键词'}")


class AgentDefinitionSchema(BaseModel):
    """Agent定义(新设计:能力导向而非步骤导向)"""

    name: str = Field(..., min_length=1, max_length=100, description="Agent名称")
    description: str = Field(..., description="Agent描述")
    template_id: Optional[int] = Field(None, description="关联的模板ID")

    # 新增:目标与约束
    goals: Optional[List[str]] = Field(None, description="Agent要达成的目标列表")
    constraints: Optional[List[str]] = Field(
        None, description="执行约束,如'文档数量不超过50'、'执行时间不超过5分钟'")

    # 新增:状态结构定义
    state_schema: Optional[Dict[str, Any]] = Field(
        None, description="统一状态字典的结构定义,定义了各个工具将读写的字段")

    # 新增:回退策略表
    rollback_plan: Optional[Dict[str, str]] = Field(
        None,
        description="关键步骤的回退策略映射,如{'document_extraction': 'multi_query_search', 'document_compose': 'document_extraction'}",
    )

    # 保留但调整:初始执行计划(仅作为参考,非强制)
    execution_pattern: str = Field(
        "hybrid",
        description="执行模式: tool_only | agent_only | agent_chain | hybrid | llm_direct",
    )
    initial_plan: Optional[List[AgentStepSchema]] = Field(
        None,
        description="初始执行计划(可选),实际执行时会由LLM动态规划,这里仅作为参考",
    )

    version: str = Field("1.0", description="版本号")
    is_active: bool = Field(True, description="是否激活")
    metadata: Optional[Dict[str, Any]] = Field(None, description="元数据")

    # 兼容性:保留steps字段但标记为已弃用
    steps: Optional[List[AgentStepSchema]] = Field(
        None, description="[已弃用]执行步骤,请使用initial_plan")


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
    """创建Agent请求(V2:直接接收解析好的Agent定义)"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(...)
    template_id: Optional[int] = Field(None)
    markdown_content: str = Field(..., description="Markdown格式定义")

    # V2: 直接接收已解析好的字段,避免重复LLM解析
    execution_pattern: Optional[str] = Field("hybrid", description="执行模式")
    goals: Optional[List[str]] = Field(None, description="Agent目标")
    constraints: Optional[List[str]] = Field(None, description="执行约束")
    initial_plan: Optional[List[AgentStepSchema]
                           ] = Field(None, description="初始计划")
    mermaid_diagram: Optional[str] = Field(None, description="Mermaid流程图")


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


# ============= 执行报告相关 =============


class ExecutionStepDetail(BaseModel):
    """执行步骤详情"""
    step: int = Field(..., description="步骤序号")
    name: str = Field(..., description="工具名称")
    description: str = Field("", description="步骤描述")
    expectations: Optional[str] = Field(None, description="期望结果")
    status: str = Field(..., description="状态: success | failed | pending")
    result: Dict[str, Any] = Field(default_factory=dict, description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")


class ExecutionStatistics(BaseModel):
    """执行统计信息"""
    total_steps: int = Field(..., description="总步骤数")
    executed_steps: int = Field(..., description="已执行步骤数")
    successful_steps: int = Field(..., description="成功步骤数")
    failed_steps: int = Field(..., description="失败步骤数")
    success_rate: float = Field(..., description="成功率(百分比)")


class ExecutionReportData(BaseModel):
    """执行报告数据结构"""
    agent_name: str = Field(..., description="智能体名称")
    query: str = Field(..., description="用户查询")
    generated_at: str = Field(..., description="报告生成时间")
    start_time: Optional[str] = Field(None, description="开始执行时间")
    end_time: Optional[str] = Field(None, description="结束执行时间")
    duration_seconds: Optional[float] = Field(None, description="执行时长(秒)")
    statistics: ExecutionStatistics = Field(..., description="执行统计")
    steps: List[ExecutionStepDetail] = Field(
        default_factory=list, description="步骤详情")
    final_result: Dict[str, Any] = Field(
        default_factory=dict, description="最终结果")
    mermaid_diagram: str = Field("", description="Mermaid流程图")


class ExecutionReportResponse(BaseModel):
    """执行报告响应"""
    report: ExecutionReportData = Field(..., description="结构化报告数据")
    html: str = Field("", description="HTML格式报告")
    markdown: str = Field("", description="Markdown格式报告")
