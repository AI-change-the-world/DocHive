import time
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, ForeignKey, Enum as SQLEnum, inspect, event
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
    levels = Column(JSON, nullable=False)  # 层级定义：[{"level": 1, "name": "年份", "code": "YEAR"}, ...]
    version = Column(String(20), default="1.0")
    is_active = Column(Boolean, default=True)
    creator_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    created_at = Column(Integer, default=lambda: int(time.time()))
    updated_at = Column(Integer, default=lambda: int(time.time()))


class NumberingRule(Base, ToDictMixin):
    """编号规则表"""
    __tablename__ = "numbering_rules"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, nullable=False, index=True)  # 关联 class_templates.id，无外键约束
    rule_format = Column(String(200), nullable=False)  # 如：{year}-{dept_code}-{type_code}-{seq:04d}
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
    class_path = Column(JSON)  # 分类路径：{"年份": "2025", "部门": "研发部", ...}
    class_code = Column(String(100), unique=True, index=True)  # 唯一分类编号
    
    # 内容信息
    content_text = Column(Text)  # 提取的文本内容
    summary = Column(Text)  # 文档摘要
    
    # 抽取信息
    extracted_data = Column(JSON)  # 结构化抽取字段
    metadata = Column(JSON)  # 元信息（作者、创建时间等）
    
    # 状态信息
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text)
    
    # 审计信息
    uploader_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    upload_time = Column(Integer, default=lambda: int(time.time()), index=True)
    processed_time = Column(Integer)


class ExtractionConfig(Base, ToDictMixin):
    """信息抽取配置表"""
    __tablename__ = "extraction_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    doc_type = Column(String(50), nullable=False)  # 简历、报告、合同等
    extract_fields = Column(JSON, nullable=False)  # 抽取字段配置
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


class DocumentExtractionMapping(Base, ToDictMixin):
    """文档-抽取配置映射表"""
    __tablename__ = "document_extraction_mapping"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, index=True)  # 关联 documents.id，无外键约束
    extraction_config_id = Column(Integer, index=True)  # 关联 extraction_configs.id，无外键约束
    created_at = Column(Integer, default=lambda: int(time.time()))


class OperationLog(Base, ToDictMixin):
    """操作日志表"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)  # 关联 users.id，无外键约束
    action = Column(String(50), nullable=False)  # create, update, delete, classify, extract
    resource_type = Column(String(50))  # template, document, config
    resource_id = Column(Integer)
    details = Column(JSON)
    ip_address = Column(String(50))
    created_at = Column(Integer, default=lambda: int(time.time()), index=True)


class SystemConfig(Base, ToDictMixin):
    """系统配置表"""
    __tablename__ = "system_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(100), unique=True, nullable=False, index=True)
    config_value = Column(JSON, nullable=False)
    description = Column(Text)
    is_public = Column(Boolean, default=False)  # 是否对普通用户可见
    updated_at = Column(Integer, default=lambda: int(time.time()))


# 注册 before_update 事件监听器，自动更新 updated_at 时间戳
event.listen(User, 'before_update', update_timestamp_before_update)
event.listen(ClassTemplate, 'before_update', update_timestamp_before_update)
event.listen(ExtractionConfig, 'before_update', update_timestamp_before_update)
event.listen(SystemConfig, 'before_update', update_timestamp_before_update)
