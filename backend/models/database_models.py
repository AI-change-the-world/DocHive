import time
from loguru import logger
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    Enum as SQLEnum,
    inspect,
    event,
)
from datetime import datetime
from database import Base
import enum


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

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class ClassTemplate(Base, ToDictMixin):
    """分类模板表"""

    __tablename__ = "class_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text)
    _levels = Column(
        "levels", Text, nullable=False
    )  # 层级定义：[{"level": 1, "name": "年份", "code": "YEAR"}, ...]
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

    def to_dict(self):
        """重写 to_dict，确保 levels 返回 list"""
        result = super().to_dict()
        # 将 _levels 的 key 改为 levels，并解析为 JSON
        if "_levels" in result:
            import json

            result["levels"] = (
                json.loads(result.pop("_levels"))
                if isinstance(result.get("_levels"), str)
                else result.pop("_levels")
            )
        return result


class ClassTemplateConfigs(Base, ToDictMixin):
    """分类模板配置表"""

    __tablename__ = "class_template_configs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer, nullable=False, index=True
    )  # 关联 class_templates.id，无外键约束
    config_name = Column(String(100), nullable=False)  # 如：year, dept_code, type_
    config_value = Column(Text, nullable=False)

    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))
    is_active = Column(Boolean, default=True)


class NumberingRule(Base, ToDictMixin):
    """编号规则表"""

    __tablename__ = "numbering_rules"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(
        Integer, nullable=False, index=True
    )  # 关联 class_templates.id，无外键约束
    rule_format = Column(
        String(200), nullable=False
    )  # 如：{year}-{dept_code}-{type_code}-{seq:04d}
    separator = Column(String(10), default="-")
    auto_increment = Column(Boolean, default=True)
    current_sequence = Column(Integer, default=0)
    created_at = Column(Integer, default=lambda: int(time.time()))


class Document(Base, ToDictMixin):
    """文档记录表"""

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)  # 对象存储路径
    file_type = Column(String(50))  # pdf, docx, txt, etc.
    file_size = Column(Integer)  # 字节

    # 分类信息
    template_id = Column(Integer, index=True)  # 关联 class_templates.id，无外键约束
    doc_type_id = Column(Integer, index=True)  # 关联 document_types.id，文档类型
    class_code = Column(String(100), unique=True, index=True)  # 唯一分类编号

    # 内容信息
    content_text = Column(Text)  # 提取的文本内容

    # 抽取信息
    _extracted_data = Column("extracted_data", Text)  # 结构化抽取字段
    _doc_metadata = Column("document_metadata", Text)  # 元信息（作者、创建时间等）

    # 状态信息
    status = Column(
        String(20), default="pending"
    )  # pending, processing, completed, failed
    error_message = Column(Text)

    # 审计信息
    uploader_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    upload_time = Column(Integer, default=lambda: int(time.time()), index=True)
    processed_time = Column(Integer)


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

        if "_extracted_data" in result:
            result["extracted_data"] = (
                json.loads(result.pop("_extracted_data"))
                if result.get("_extracted_data")
                else None
            )
        if "_doc_metadata" in result:
            result["metadata"] = (
                json.loads(result.pop("_doc_metadata"))
                if result.get("_doc_metadata")
                else {}
            )
        return result


class ExtractionConfig(Base, ToDictMixin):
    """信息抽取配置表"""

    __tablename__ = "extraction_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False)  # 简历、报告、合同等
    _extract_fields = Column("extract_fields", Text, nullable=False)  # 抽取字段配置
    """
    示例：[
        {"name": "姓名", "type": "text", "method": "regex", "pattern": "姓名[:：]\\s*(\\S+)"},
        {"name": "行业", "type": "text", "method": "llm", "prompt": "提取行业信息"},
        {"name": "技能", "type": "array", "method": "llm"}
    ]
    """
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))

    @property
    def extract_fields(self):
        """自动将 JSON 字符串转为 list"""
        import json

        if isinstance(self._extract_fields, str):
            return json.loads(self._extract_fields)
        return self._extract_fields

    @extract_fields.setter
    def extract_fields(self, value):
        """自动将 list 转为 JSON 字符串"""
        import json

        if isinstance(value, (list, dict)):
            self._extract_fields = json.dumps(value, ensure_ascii=False)
        else:
            self._extract_fields = value

    def to_dict(self):
        """重写 to_dict，确保 extract_fields 返回 list"""
        result = super().to_dict()
        # 将 _extract_fields 的 key 改为 extract_fields，并解析为 JSON
        if "_extract_fields" in result:
            import json

            result["extract_fields"] = (
                json.loads(result.pop("_extract_fields"))
                if isinstance(result.get("_extract_fields"), str)
                else result.pop("_extract_fields")
            )
        return result


class DocumentExtractionMapping(Base, ToDictMixin):
    """文档-抽取配置映射表"""

    __tablename__ = "document_extraction_mapping"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, index=True)  # 关联 documents.id，无外键约束
    extraction_config_id = Column(
        Integer, index=True
    )  # 关联 extraction_configs.id，无外键约束
    created_at = Column(Integer, default=lambda: int(time.time()))


class OperationLog(Base, ToDictMixin):
    """操作日志表"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    action = Column(
        String(50), nullable=False
    )  # create, update, delete, classify, extract
    resource_type = Column(String(50))  # template, document, config
    resource_id = Column(Integer)
    details = Column(Text)
    ip_address = Column(String(50))
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)


class DocumentType(Base, ToDictMixin):
    """文档类型表（由模板中 is_doc_type=True 的层级定义）"""

    __tablename__ = "document_types"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, nullable=False, index=True)  # 关联 class_templates.id
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

    id = Column(Integer, primary_key=True, index=True)
    doc_type_id = Column(Integer, nullable=False, index=True)  # 关联 document_types.id
    field_name = Column(String(100), nullable=False)  # 字段名称，如：编制人、任务数量
    description = Column(
        String(255), nullable=False
    )  # 字段编码，如：author、task_count
    field_type = Column(
        String(20), default="text"
    )  # 字段类型：text, number, array, date, boolean
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class SystemConfig(Base, ToDictMixin):
    """系统配置表"""

    __tablename__ = "system_configs"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(Text, nullable=False)
    description = Column(Text)
    is_public = Column(Boolean, default=False)  # 是否对普通用户可见
    updated_at = Column(Integer, default=lambda: int(time.time()))


# 注册 before_update 事件监听器，自动更新 updated_at 时间戳
event.listen(User, "before_update", update_timestamp_before_update)
event.listen(ClassTemplate, "before_update", update_timestamp_before_update)
event.listen(ExtractionConfig, "before_update", update_timestamp_before_update)
event.listen(DocumentType, "before_update", update_timestamp_before_update)
event.listen(DocumentTypeField, "before_update", update_timestamp_before_update)
event.listen(SystemConfig, "before_update", update_timestamp_before_update)
