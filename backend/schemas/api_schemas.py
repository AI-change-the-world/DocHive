from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

#  ============= SSE统一格式 =============
class SSEEvent(BaseModel):
    """SSE事件"""
    event: str = Field(..., description="事件名称")
    data: Optional[Any]  = Field(None, description="事件数据")
    id: Optional[str] = Field(None, description="事件ID")
    done: Optional[bool] = Field(False, description="是否完成")


# ============= 通用模式 =============
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    REVIEWER = "reviewer"


class ResponseBase(BaseModel):
    """API 响应基础模式"""
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class PaginatedResponse(BaseModel):
    """分页响应"""
    total: int
    page: int
    page_size: int
    items: List[Any]


# ============= 用户相关 =============
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    role: UserRole = UserRole.USER


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserInDB(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserResponse(UserInDB):
    """用户响应模式（不包含密码）"""
    pass


# ============= 认证相关 =============
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None
    username: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


# ============= 分类模板相关 =============
class TemplateLevelSchema(BaseModel):
    """模板层级定义"""
    level: int = Field(..., ge=1, description="层级序号")
    name: str = Field(..., min_length=1, max_length=50, description="层级名称")
    code: Optional[str] = Field(None, max_length=20, description="层级代码")
    description: Optional[str] = None
    
    # AI智能提取配置（统一使用大模型）
    extraction_prompt: Optional[str] = Field(None, description="AI提取的Prompt（包含编码规则说明）")
    placeholder_example: Optional[str] = Field(None, description="示例值")
    
    # 业务属性配置
    business_keywords_prompt: Optional[str] = Field(None, description="业务关键词识别Prompt，用于智能检索匹配")
    is_doc_type: Optional[bool] = Field(False, description="是否为文档类型字段")


class ClassTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    levels: List[TemplateLevelSchema] = Field(..., min_length=1)
    version: str = Field("1.0", max_length=20)


class ClassTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    levels: Optional[List[TemplateLevelSchema]] = None
    version: Optional[str] = None
    is_active: Optional[bool] = None


class ClassTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    description: Optional[str]
    levels: List[Dict[str, Any]]
    version: str
    is_active: bool
    creator_id: int
    created_at: datetime
    updated_at: datetime


# ============= 编号规则相关 =============
class NumberingRuleCreate(BaseModel):
    template_id: int
    rule_format: str = Field(..., description="编号格式，如：{year}-{dept_code}-{type_code}-{seq:04d}")
    separator: str = Field("-", max_length=10)
    auto_increment: bool = True


class NumberingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    template_id: int
    rule_format: str
    separator: str
    auto_increment: bool
    current_sequence: int
    created_at: datetime


# ============= 文档相关 =============
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    template_id: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class DocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    class_path: Optional[Dict[str, str]] = None
    extracted_data: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    title: str
    original_filename: str
    file_path: str
    file_type: Optional[str]
    file_size: Optional[int]
    template_id: Optional[int]
    class_path: Optional[Dict[str, str]]
    class_code: Optional[str]
    summary: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    status: str
    uploader_id: int
    upload_time: datetime
    processed_time: Optional[datetime]


class DocumentSearchRequest(BaseModel):
    """文档检索请求"""
    keyword: Optional[str] = Field(None, description="全文搜索关键词")
    template_id: Optional[int] = None
    class_path: Optional[Dict[str, str]] = Field(None, description="分类路径过滤")
    extracted_fields: Optional[Dict[str, Any]] = Field(None, description="抽取字段过滤")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


# ============= 信息抽取相关 =============
class ExtractionFieldSchema(BaseModel):
    """抽取字段定义"""
    name: str = Field(..., description="字段名称")
    type: str = Field(..., description="字段类型：text, number, array, date")
    method: str = Field(..., description="抽取方法：regex, llm, rule")
    pattern: Optional[str] = Field(None, description="正则表达式（method=regex时）")
    prompt: Optional[str] = Field(None, description="LLM提示词（method=llm时）")
    required: bool = Field(False, description="是否必需")


class ExtractionConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    doc_type: str = Field(..., min_length=1, max_length=50)
    extract_fields: List[ExtractionFieldSchema] = Field(..., min_length=1)


class ExtractionConfigUpdate(BaseModel):
    name: Optional[str] = None
    extract_fields: Optional[List[ExtractionFieldSchema]] = None
    is_active: Optional[bool] = None


class ExtractionConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    name: str
    doc_type: str
    extract_fields: List[Dict[str, Any]]
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ============= 分类相关 =============
class ClassificationRequest(BaseModel):
    """文档分类请求"""
    document_id: int
    template_id: int
    force_reclassify: bool = Field(False, description="强制重新分类")


class ClassificationResponse(BaseModel):
    """分类结果"""
    document_id: int
    class_path: Dict[str, str]
    class_code: str
    confidence: Optional[float] = Field(None, description="分类置信度")


# ============= 抽取相关 =============
class ExtractionRequest(BaseModel):
    """信息抽取请求"""
    document_id: int
    config_id: int


class ExtractionResponse(BaseModel):
    """抽取结果"""
    document_id: int
    extracted_data: Dict[str, Any]
    success_fields: List[str]
    failed_fields: List[str]


# ============= 文档类型相关 =============
class DocumentTypeFieldSchema(BaseModel):
    """文档类型字段定义"""
    field_name: str = Field(..., min_length=1, max_length=100, description="字段名称")
    description: str = Field(..., description="字段描述")
    field_type: str = Field("text", description="字段类型:text, number, array, date, boolean")


class DocumentTypeCreate(BaseModel):
    """创建文档类型"""
    template_id: int = Field(..., description="所属模板ID")
    type_code: str = Field(..., min_length=1, max_length=50, description="类型编码")
    type_name: str = Field(..., min_length=1, max_length=100, description="类型名称")
    description: Optional[str] = None
    extraction_prompt: Optional[str] = Field(None, description="AI提取Prompt")
    fields: Optional[List[DocumentTypeFieldSchema]] = Field(default=[], description="字段配置列表")


class DocumentTypeUpdate(BaseModel):
    """更新文档类型"""
    type_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    extraction_prompt: Optional[str] = None
    is_active: Optional[bool] = None


class DocumentTypeFieldResponse(BaseModel):
    """文档类型字段响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    doc_type_id: int
    field_name: str
    field_code: str
    field_type: str
    extraction_prompt: Optional[str]
    is_required: bool
    display_order: int
    placeholder_example: Optional[str]
    created_at: datetime
    updated_at: datetime


class DocumentTypeResponse(BaseModel):
    """文档类型响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    template_id: int
    type_code: str
    type_name: str
    description: Optional[str]
    extraction_prompt: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    fields: Optional[List[DocumentTypeFieldResponse]] = None


class DocumentTypeFieldCreate(BaseModel):
    """创建文档类型字段"""
    doc_type_id: int = Field(..., description="文档类型ID")
    field_name: str = Field(..., min_length=1, max_length=100)
    field_code: str = Field(..., min_length=1, max_length=50)
    field_type: str = Field("text")
    extraction_prompt: Optional[str] = None
    is_required: bool = False
    display_order: int = 0
    placeholder_example: Optional[str] = None


class DocumentTypeFieldUpdate(BaseModel):
    """更新文档类型字段"""
    field_name: Optional[str] = None
    field_type: Optional[str] = None
    extraction_prompt: Optional[str] = None
    is_required: Optional[bool] = None
    display_order: Optional[int] = None
    placeholder_example: Optional[str] = None


# ============= 系统配置相关 =============
class SystemConfigCreate(BaseModel):
    config_key: str = Field(..., max_length=100)
    config_value: Dict[str, Any]
    description: Optional[str] = None
    is_public: bool = False


class SystemConfigUpdate(BaseModel):
    config_value: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class SystemConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    config_key: str
    config_value: Dict[str, Any]
    description: Optional[str]
    is_public: bool
    updated_at: datetime
