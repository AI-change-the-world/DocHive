import enum
import time
from datetime import datetime

from loguru import logger
from sqlalchemy import JSON, Boolean, Column
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, Text, event, inspect

from database import Base


def update_timestamp_before_update(mapper, connection, target):
    """更新时间戳的通用函数"""
    target.updated_at = int(time.time())


class ToDictMixin:
    def to_dict(self):
        """将 ORM 实例转为 JSON 可用的 dict"""
        result = {}
        for c in inspect(self).mapper.column_attrs:
            value = getattr(self, c.key)
            if isinstance(value, datetime):
                value = value.isoformat()  # 转成字符串
            elif (
                isinstance(value, int)
                and c.key.endswith(("_at", "_date"))
                and value > 1000000000
            ):
                # 将时间戳转为 ISO 格式字符串
                value = datetime.fromtimestamp(value).isoformat()
            result[c.key] = value
        return result


class UserRole(str, enum.Enum):
    """用户角色枚举"""

    ADMIN = "admin"
    USER = "user"
    REVIEWER = "reviewer"


class User(Base, ToDictMixin):
    """用户表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class ClassTemplate(Base, ToDictMixin):
    """编码模板表"""

    __tablename__ = "class_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    _levels = Column(
        "levels", Text, nullable=False
    )  # 层级定义：[{"level": 1, "name": "年份", "code": "YEAR"}, ...]
    _level_options = Column(
        "level_options", Text
    )  # 预处理的层级值域选项：{"YEAR": ["2023", "2024", "2025"], "DEPT": ["TECH", "HR"]}
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)
    creator_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))

    @property
    def levels(self):
        """自动将 JSON 字符串转为 list"""
        import json

        if isinstance(self._levels, str):
            return json.loads(self._levels)
        return self._levels

    @levels.setter
    def levels(self, value):
        """自动将 list 转为 JSON 字符串"""
        import json

        if isinstance(value, (list, dict)):
            self._levels = json.dumps(value, ensure_ascii=False)
        else:
            self._levels = value

    @property
    def level_options(self):
        """自动将 JSON 字符串转为 dict"""
        import json

        if self._level_options is not None:
            return (
                json.loads(self._level_options)
                if isinstance(self._level_options, str)
                else self._level_options
            )
        return {}

    @level_options.setter
    def level_options(self, value):
        """自动将 dict 转为 JSON 字符串"""
        import json

        if value is None:
            self._level_options = None
        elif isinstance(value, (dict, list)):
            self._level_options = json.dumps(value, ensure_ascii=False)
        else:
            self._level_options = value

    def to_dict(self):
        """重写 to_dict，确保 levels 和 level_options 返回解析后的值"""
        result = super().to_dict()
        import json

        # 将 _levels 的 key 改为 levels，并解析为 JSON
        if "_levels" in result:
            result["levels"] = (
                json.loads(result.pop("_levels"))
                if isinstance(result.get("_levels"), str)
                else result.pop("_levels")
            )

        # 将 _level_options 的 key 改为 level_options，并解析为 JSON
        if "_level_options" in result:
            result["level_options"] = (
                (
                    json.loads(result.pop("_level_options"))
                    if isinstance(result.get("_level_options"), str)
                    else result.pop("_level_options")
                )
                if result.get("_level_options")
                else {}
            )

        return result


class ClassTemplateConfigs(Base, ToDictMixin):
    """编码模板配置表"""

    __tablename__ = "class_template_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    template_id = Column(
        Integer, nullable=False, index=True
    )  # 关联 class_templates.id，无外键约束
    # 如：year, dept_code, type_
    config_name = Column(String(100), nullable=False)
    config_value = Column(Text, nullable=False)

    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))
    is_active = Column(Boolean, default=True)


class Document(Base, ToDictMixin):
    """文档记录表"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # 对象存储路径
    file_type = Column(String(50))  # pdf, docx, txt, etc.
    file_size = Column(Integer)  # 字节

    # 分类信息
    template_id = Column(Integer, index=True)  # 关联 class_templates.id，无外键约束
    doc_type_id = Column(Integer, index=True)  # 关联 document_types.id，文档类型
    # 注意：class_code 字段已移除，现在使用 template_document_mappings 表存储

    # 内容信息
    content_text = Column(Text)  # 提取的文本内容
    ai_summary = Column(Text)  # AI生成的文档摘要（100-200字）

    # 抽取信息
    _doc_metadata = Column("document_metadata", Text)  # 元信息（作者、创建时间等）

    # 审计信息
    uploader_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    upload_time = Column(Integer, default=lambda: int(time.time()), index=True)
    # 注意：status, error_message, processed_time, extracted_data 字段已移除，现在使用 template_document_mappings 表存储

    @property
    def doc_metadata(self):
        """自动将 JSON 字符串转为 dict"""
        import json

        if self._doc_metadata is not None:
            return (
                json.loads(self._doc_metadata)
                if isinstance(self._doc_metadata, str)
                else self._doc_metadata
            )
        return {}

    @doc_metadata.setter
    def doc_metadata(self, value):
        """自动将 dict 转为 JSON 字符串"""
        import json

        if value is None:
            self._doc_metadata = None
        elif isinstance(value, (dict, list)):
            self._doc_metadata = json.dumps(value, ensure_ascii=False)
        else:
            self._doc_metadata = value

    def to_dict(self):
        """重写 to_dict，确保 JSON 字段返回 dict"""
        result = super().to_dict()
        # 将私有字段改为公开字段，并解析为 JSON
        import json

        if "_doc_metadata" in result:
            result["metadata"] = (
                json.loads(result.pop("_doc_metadata"))
                if result.get("_doc_metadata")
                else {}
            )
        return result


class OperationLog(Base, ToDictMixin):
    """操作日志表"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    action = Column(
        String(50), nullable=False
    )  # create, update, delete, classify, extract
    resource_type = Column(String(50))  # template, document, config
    request_params = Column(Text)  # 请求参数
    details = Column(Text)  # 其他详细信息
    ip_address = Column(String(50))
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)


class DocumentType(Base, ToDictMixin):
    """文档类型表（由模板中 is_doc_type=True 的层级定义）"""

    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    template_id = Column(Integer, nullable=False,
                         index=True)  # 关联 class_templates.id
    type_code = Column(
        String(50), nullable=False, index=True
    )  # 类型编码，如：DEV_DOC、DESIGN_DOC
    type_name = Column(String(100), nullable=False)  # 类型名称，如：开发文档、设计文档
    description = Column(Text)  # 类型描述
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class DocumentTypeField(Base, ToDictMixin):
    """文档类型字段配置表（定义每个文档类型需要提取的结构化字段）"""

    __tablename__ = "document_type_fields"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doc_type_id = Column(Integer, nullable=False,
                         index=True)  # 关联 document_types.id
    field_name = Column(String(100), nullable=False)  # 字段名称，如：编制人、任务数量
    description = Column(
        String(255), nullable=False
    )  # 字段编码，如：author、task_count
    field_type = Column(
        String(20), default="text"
    )  # 字段类型：text, number, array, date, boolean
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class TemplateDocumentMapping(Base, ToDictMixin):
    """模板和文档映射表"""

    __tablename__ = "template_document_mappings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    template_id = Column(Integer, nullable=False,
                         index=True)  # 关联 class_templates.id
    document_id = Column(Integer, nullable=False,
                         index=True)  # 关联 documents.id
    class_code = Column(String(100), index=True)  # 分类编号

    # 状态信息
    status = Column(
        String(20), default="pending"
    )  # pending, processing, completed, failed
    error_message = Column(Text)
    processed_time = Column(Integer)

    # 抽取信息
    _extracted_data = Column("extracted_data", Text)  # 结构化抽取字段

    created_at = Column(Integer, default=lambda: int(time.time()))

    @property
    def extracted_data(self):
        """自动将 JSON 字符串转为 dict"""
        import json

        if self._extracted_data is not None:
            return (
                json.loads(self._extracted_data)
                if isinstance(self._extracted_data, str)
                else self._extracted_data
            )
        return None

    @extracted_data.setter
    def extracted_data(self, value):
        """自动将 dict 转为 JSON 字符串"""
        import json

        if value is None:
            self._extracted_data = None
        elif isinstance(value, (dict, list)):
            self._extracted_data = json.dumps(value, ensure_ascii=False)
        else:
            self._extracted_data = value


class SystemConfig(Base, ToDictMixin):
    """系统配置表"""

    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(Text, nullable=False)
    description = Column(Text)
    is_public = Column(Boolean, default=False)  # 是否对普通用户可见
    updated_at = Column(Integer, default=lambda: int(time.time()))


class LLMLog(Base, ToDictMixin):
    """大模型调用日志表"""

    __tablename__ = "llm_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider = Column(String(50), nullable=False,
                      index=True)  # openai, deepseek等
    model = Column(String(100), nullable=False, index=True)  # 模型名称
    _input_messages = Column("input_messages", Text,
                             nullable=False)  # 输入消息（JSON）
    output_content = Column(Text)  # 输出内容
    prompt_tokens = Column(Integer, default=0)  # 提示词token数
    completion_tokens = Column(Integer, default=0)  # 完成token数
    total_tokens = Column(Integer, default=0)  # 总token数
    duration_ms = Column(Integer)  # 调用耗时（毫秒）
    status = Column(String(20), default="success")  # success, error
    error_message = Column(Text)  # 错误信息
    user_id = Column(Integer, index=True)  # 调用用户ID
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)

    @property
    def input_messages(self):
        """自动将 JSON 字符串转为 list"""
        import json

        if self._input_messages is not None:
            return (
                json.loads(self._input_messages)
                if isinstance(self._input_messages, str)
                else self._input_messages
            )
        return None

    @input_messages.setter
    def input_messages(self, value):
        """自动将 list 转为 JSON 字符串"""
        import json

        if isinstance(value, (list, dict)):
            self._input_messages = json.dumps(value, ensure_ascii=False)
        else:
            self._input_messages = value

    def to_dict(self):
        """重写 to_dict，确保 input_messages 返回 list"""
        result = super().to_dict()
        if "_input_messages" in result:
            import json

            result["input_messages"] = (
                json.loads(result.pop("_input_messages"))
                if isinstance(result.get("_input_messages"), str)
                else result.pop("_input_messages")
            )
        return result


class CustomAgent(Base, ToDictMixin):
    """自定义Agent表(新设计:能力导向)"""

    __tablename__ = "custom_agents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True, comment="Agent名称")
    description = Column(Text, comment="Agent描述")
    template_id = Column(Integer, index=True, comment="关联的模板ID")

    # Agent定义
    markdown_content = Column(Text, nullable=False,
                              comment="Markdown格式的Agent定义")
    execution_pattern = Column(
        String(50),
        nullable=False,
        comment="执行模式:tool_only/agent_only/agent_chain/hybrid/llm_direct",
    )

    # 新增:能力导向字段
    _goals = Column("goals", Text, comment="Agent目标列表的JSON数组")
    _constraints = Column("constraints", Text, comment="执行约束的JSON数组")
    _state_schema = Column("state_schema", Text, comment="状态结构定义的JSON对象")
    _rollback_plan = Column("rollback_plan", Text, comment="回退策略映射的JSON对象")
    _initial_plan = Column("initial_plan", Text, comment="初始执行计划的JSON数组(仅参考)")

    # 保留但标记为可选:旧的steps字段(向后兼容)
    _steps = Column("steps", Text, comment="[已弃用]执行步骤的JSON数组,请使用initial_plan")

    mermaid_diagram = Column(Text, comment="Mermaid流程图代码")

    # 元信息
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)

    # 审计信息
    creator_id = Column(Integer, index=True, comment="创建者ID")
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))

    # 新增:属性访问器
    @property
    def goals(self):
        """自动将JSON字符串转为list"""
        import json
        if self._goals and isinstance(self._goals, str):
            return json.loads(self._goals)
        return self._goals if self._goals else []

    @goals.setter
    def goals(self, value):
        """自动将list转为JSON字符串"""
        import json
        if value is None:
            self._goals = None
        elif isinstance(value, (list, dict)):
            self._goals = json.dumps(value, ensure_ascii=False)
        else:
            self._goals = value

    @property
    def constraints(self):
        """自动将JSON字符串转为list"""
        import json
        if self._constraints and isinstance(self._constraints, str):
            return json.loads(self._constraints)
        return self._constraints if self._constraints else []

    @constraints.setter
    def constraints(self, value):
        """自动将list转为JSON字符串"""
        import json
        if value is None:
            self._constraints = None
        elif isinstance(value, (list, dict)):
            self._constraints = json.dumps(value, ensure_ascii=False)
        else:
            self._constraints = value

    @property
    def state_schema(self):
        """自动将JSON字符串转为dict"""
        import json
        if self._state_schema and isinstance(self._state_schema, str):
            return json.loads(self._state_schema)
        return self._state_schema if self._state_schema else {}

    @state_schema.setter
    def state_schema(self, value):
        """自动将dict转为JSON字符串"""
        import json
        if value is None:
            self._state_schema = None
        elif isinstance(value, (list, dict)):
            self._state_schema = json.dumps(value, ensure_ascii=False)
        else:
            self._state_schema = value

    @property
    def rollback_plan(self):
        """自动将JSON字符串转为dict"""
        import json
        if self._rollback_plan and isinstance(self._rollback_plan, str):
            return json.loads(self._rollback_plan)
        return self._rollback_plan if self._rollback_plan else {}

    @rollback_plan.setter
    def rollback_plan(self, value):
        """自动将dict转为JSON字符串"""
        import json
        if value is None:
            self._rollback_plan = None
        elif isinstance(value, (list, dict)):
            self._rollback_plan = json.dumps(value, ensure_ascii=False)
        else:
            self._rollback_plan = value

    @property
    def initial_plan(self):
        """自动将JSON字符串转为list"""
        import json
        if self._initial_plan and isinstance(self._initial_plan, str):
            return json.loads(self._initial_plan)
        return self._initial_plan if self._initial_plan else []

    @initial_plan.setter
    def initial_plan(self, value):
        """自动将list转为JSON字符串"""
        import json
        if value is None:
            self._initial_plan = None
        elif isinstance(value, (list, dict)):
            self._initial_plan = json.dumps(value, ensure_ascii=False)
        else:
            self._initial_plan = value

    @property
    def steps(self):
        """[已弃用]自动将JSON字符串转为list,向后兼容"""
        import json
        if self._steps and isinstance(self._steps, str):
            return json.loads(self._steps)
        # 如果没有steps但有initial_plan,则返回initial_plan
        if not self._steps and self._initial_plan:
            return self.initial_plan
        return self._steps if self._steps else []

    @steps.setter
    def steps(self, value):
        """[已弃用]自动将list转为JSON字符串,向后兼容"""
        import json
        if value is None:
            self._steps = None
        elif isinstance(value, (list, dict)):
            self._steps = json.dumps(value, ensure_ascii=False)
        else:
            self._steps = value

    def to_dict(self):
        """重写to_dict,确保新字段正确解析"""
        result = super().to_dict()
        import json

        # 解析新增字段
        if "_goals" in result:
            result["goals"] = (
                json.loads(result.pop("_goals"))
                if result.get("_goals") and isinstance(result.get("_goals"), str)
                else result.pop("_goals") or []
            )

        if "_constraints" in result:
            result["constraints"] = (
                json.loads(result.pop("_constraints"))
                if result.get("_constraints") and isinstance(result.get("_constraints"), str)
                else result.pop("_constraints") or []
            )

        if "_state_schema" in result:
            result["state_schema"] = (
                json.loads(result.pop("_state_schema"))
                if result.get("_state_schema") and isinstance(result.get("_state_schema"), str)
                else result.pop("_state_schema") or {}
            )

        if "_rollback_plan" in result:
            result["rollback_plan"] = (
                json.loads(result.pop("_rollback_plan"))
                if result.get("_rollback_plan") and isinstance(result.get("_rollback_plan"), str)
                else result.pop("_rollback_plan") or {}
            )

        if "_initial_plan" in result:
            result["initial_plan"] = (
                json.loads(result.pop("_initial_plan"))
                if result.get("_initial_plan") and isinstance(result.get("_initial_plan"), str)
                else result.pop("_initial_plan") or []
            )

        # 解析旧的steps字段(向后兼容)
        if "_steps" in result:
            result["steps"] = (
                json.loads(result.pop("_steps"))
                if result.get("_steps") and isinstance(result.get("_steps"), str)
                else result.pop("_steps") or []
            )
            # 如果没有steps但有initial_plan,返回initial_plan
            if not result["steps"] and result.get("initial_plan"):
                result["steps"] = result["initial_plan"]

        return result


class WritingTemplate(Base, ToDictMixin):
    """写作模板表 - 用于存储优秀文章样本，供文档润色参考"""

    __tablename__ = "writing_templates"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(255), nullable=False, index=True, comment="模板标题")
    theme = Column(String(100), nullable=False, index=True, comment="主题分类")
    content = Column(Text, nullable=False, comment="模板内容(完整文章)")
    description = Column(Text, comment="模板描述")
    _tags = Column("tags", Text, comment="标签列表(JSON数组)")

    # 关联信息
    template_id = Column(Integer, nullable=False,
                         index=True, comment="关联的编码模板ID")
    uploader_id = Column(Integer, index=True, comment="上传者ID")

    # 元信息
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)
    updated_at = Column(Integer, default=lambda: int(time.time()))

    @property
    def tags_list(self):
        """自动将JSON字符串转为list"""
        import json

        if self._tags and isinstance(self._tags, str):
            try:
                return json.loads(self._tags)
            except:
                return []
        return self._tags if self._tags else []

    @tags_list.setter
    def tags_list(self, value):
        """自动将list转为JSON字符串"""
        import json

        if isinstance(value, (list, tuple)):
            self._tags = json.dumps(value, ensure_ascii=False)
        else:
            self._tags = value

    def to_dict(self):
        """重写to_dict，确保tags返回解析后的值"""
        result = super().to_dict()
        import json

        if "_tags" in result:
            try:
                result["tags"] = (
                    json.loads(result.pop("_tags"))
                    if isinstance(result.get("_tags"), str)
                    else result.pop("_tags")
                )
            except:
                result["tags"] = []

        return result


class AgentExecutionRecord(Base, ToDictMixin):
    """智能体执行记录表"""

    __tablename__ = "agent_execution_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_id = Column(Integer, index=True)  # 关联 custom_agents.id
    agent_name = Column(String(200), nullable=False, index=True)  # Agent名称快照
    query = Column(Text, nullable=False)  # 用户查询
    template_id = Column(Integer, index=True)  # 关联的模板ID

    # 执行信息
    # 执行模式: tool_only, agent_only, hybrid等
    execution_pattern = Column(String(50))
    session_id = Column(String(100), index=True)  # 会话 ID

    # 执行结果
    # running, completed, failed, cancelled
    status = Column(String(50), default="running", index=True)
    _execution_plan = Column("execution_plan", Text)  # 执行计划 JSON
    _step_history = Column("step_history", Text)  # 步骤历史 JSON
    _final_result = Column("final_result", Text)  # 最终结果 JSON
    _report_data = Column("report_data", Text)  # 报告数据 JSON
    html_report = Column(Text)  # HTML报告
    markdown_report = Column(Text)  # Markdown报告

    # 统计信息
    total_steps = Column(Integer, default=0)  # 总步骤数
    executed_steps = Column(Integer, default=0)  # 已执行步骤数
    successful_steps = Column(Integer, default=0)  # 成功步骤数
    failed_steps = Column(Integer, default=0)  # 失败步骤数
    success_rate = Column(Integer, default=0)  # 成功率(百分比)

    # 时间信息
    start_time = Column(Integer, index=True)  # 开始执行时间戳
    end_time = Column(Integer, index=True)  # 结束执行时间戳
    duration_seconds = Column(Integer)  # 执行时长(秒)

    # 审计信息
    user_id = Column(Integer, index=True)  # 执行用户 ID
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)
    updated_at = Column(Integer, default=lambda: int(time.time()))

    @property
    def execution_plan(self):
        """JSON字符串转 list"""
        import json
        if self._execution_plan and isinstance(self._execution_plan, str):
            try:
                return json.loads(self._execution_plan)
            except:
                return []
        return self._execution_plan if self._execution_plan else []

    @execution_plan.setter
    def execution_plan(self, value):
        """list 转 JSON字符串"""
        import json
        if isinstance(value, (list, dict)):
            self._execution_plan = json.dumps(value, ensure_ascii=False)
        else:
            self._execution_plan = value

    @property
    def step_history(self):
        """JSON字符串转 list"""
        import json
        if self._step_history and isinstance(self._step_history, str):
            try:
                return json.loads(self._step_history)
            except:
                return []
        return self._step_history if self._step_history else []

    @step_history.setter
    def step_history(self, value):
        """list 转 JSON字符串"""
        import json
        if isinstance(value, (list, dict)):
            self._step_history = json.dumps(value, ensure_ascii=False)
        else:
            self._step_history = value

    @property
    def final_result(self):
        """JSON字符串转 dict"""
        import json
        if self._final_result and isinstance(self._final_result, str):
            try:
                return json.loads(self._final_result)
            except:
                return {}
        return self._final_result if self._final_result else {}

    @final_result.setter
    def final_result(self, value):
        """dict 转 JSON字符串"""
        import json
        if isinstance(value, (list, dict)):
            self._final_result = json.dumps(value, ensure_ascii=False)
        else:
            self._final_result = value

    @property
    def report_data(self):
        """JSON字符串转 dict"""
        import json
        if self._report_data and isinstance(self._report_data, str):
            try:
                return json.loads(self._report_data)
            except:
                return {}
        return self._report_data if self._report_data else {}

    @report_data.setter
    def report_data(self, value):
        """dict 转 JSON字符串"""
        import json
        if isinstance(value, (list, dict)):
            self._report_data = json.dumps(value, ensure_ascii=False)
        else:
            self._report_data = value

    def to_dict(self):
        """重写to_dict，确保 JSON 字段返回解析后的值"""
        result = super().to_dict()
        import json

        # 解析 JSON 字段
        for field in ["execution_plan", "step_history", "final_result", "report_data"]:
            private_field = f"_{field}"
            if private_field in result:
                value = result.pop(private_field)
                try:
                    result[field] = json.loads(value) if isinstance(value, str) else (
                        value if value else ({} if field in ["final_result", "report_data"] else []))
                except:
                    result[field] = {} if field in [
                        "final_result", "report_data"] else []

        # 修复时间字段：将 ISO 字符串转回整数时间戳
        from datetime import datetime
        for time_field in ["created_at", "updated_at", "start_time", "end_time"]:
            if time_field in result and isinstance(result[time_field], str):
                try:
                    # 将 ISO 字符串转回时间戳
                    dt = datetime.fromisoformat(result[time_field])
                    result[time_field] = int(dt.timestamp())
                except:
                    pass

        return result


# 注册 before_update 事件监听器，自动更新 updated_at 时间戳
event.listen(User, "before_update", update_timestamp_before_update)
event.listen(ClassTemplate, "before_update", update_timestamp_before_update)
event.listen(ClassTemplateConfigs, "before_update",
             update_timestamp_before_update)
event.listen(DocumentType, "before_update", update_timestamp_before_update)
event.listen(DocumentTypeField, "before_update",
             update_timestamp_before_update)
event.listen(SystemConfig, "before_update", update_timestamp_before_update)
event.listen(CustomAgent, "before_update", update_timestamp_before_update)
event.listen(WritingTemplate, "before_update", update_timestamp_before_update)
event.listen(AgentExecutionRecord, "before_update",
             update_timestamp_before_update)
