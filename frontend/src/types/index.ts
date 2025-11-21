// 通用响应类型
export interface ApiResponse<T = any> {
    code: number;
    message: string;
    data: T;
}

// 分页参数
export interface PaginationParams {
    page: number;
    page_size: number;
}

// 分页响应
export interface PaginatedResponse<T> {
    total: number;
    page: number;
    page_size: number;
    items: T[];
}

// 用户相关类型
export type UserRole = 'admin' | 'user' | 'reviewer';

export const UserRole = {
    ADMIN: 'admin',
    USER: 'user',
    REVIEWER: 'reviewer',
} as const;

export interface User {
    id: number;
    username: string;
    email: string;
    role: UserRole;
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface LoginRequest {
    username: string;
    password: string;
}

export interface RegisterRequest {
    username: string;
    email: string;
    password: string;
    role?: UserRole;
}

export interface Token {
    access_token: string;
    refresh_token: string;
    token_type: string;
    user?: User;
}

// 分类模板相关类型
export interface TemplateLevel {
    level: number;
    name: string;
    code?: string;
    description?: string;
    // AI智能提取配置（统一使用大模型）
    extraction_prompt?: string;  // AI提取的Prompt（包含编码规则说明）
    placeholder_example?: string;  // 示例值
    // 业务属性配置
    business_keywords_prompt?: string;  // 业务关键词识别Prompt，用于智能检索匹配
    is_doc_type?: boolean;  // 是否为文档类型字段（用于最终分类）
}

export interface ClassTemplate {
    id: number;
    name: string;
    description?: string;
    levels: TemplateLevel[];
    version: string;
    is_active: boolean;
    creator_id: number;
    created_at: string;
    updated_at: string;
}

export interface ClassTemplateCreate {
    name: string;
    description?: string;
    levels: TemplateLevel[];
    version?: string;
}

export interface ClassTemplateUpdate {
    name?: string;
    description?: string;
    levels?: TemplateLevel[];
    version?: string;
    is_active?: boolean;
}

// 文档相关类型
export interface Document {
    id: number;
    title: string;
    original_filename: string;
    file_path: string;
    file_type?: string;
    file_size?: number;
    template_id?: number;
    class_code?: string;
    summary?: string;
    extracted_data?: Record<string, any>;
    metadata?: Record<string, any>;
    status: string;
    uploader_id: number;
    upload_time: string;
    processed_time?: string;
}

export interface DocumentCreate {
    title: string;
    template_id?: number;
    metadata?: Record<string, any>;
}

export interface DocumentSearchRequest extends PaginationParams {
    keyword?: string;
    template_id?: number;
    extracted_fields?: Record<string, any>;
    start_date?: string;
    end_date?: string;
    status?: string;
}

// 系统配置相关类型
export interface SystemConfig {
    id: number;
    config_key: string;
    config_value: Record<string, any>;
    description?: string;
    is_public: boolean;
    updated_at: string;
}

export interface TemplateSelection {
    template_id: number;
    template_name: string;
}

export interface SystemConfigCreate {
    config_key: string;
    config_value: Record<string, any>;
    description?: string;
    is_public?: boolean;
}

// 文档类型相关类型
export interface DocumentTypeField {
    id?: number;
    doc_type_id?: number;
    field_name: string;
    field_type: 'text' | 'number' | 'array' | 'date' | 'boolean';
    description?: string;
}

export interface DocumentType {
    id: number;
    template_id: number;
    type_code: string;
    type_name: string;
    description?: string;
    extraction_prompt?: string;
    is_active: boolean;
    created_at: string;
    updated_at: string;
    fields?: DocumentTypeField[];
}

export interface DocumentTypeCreate {
    template_id: number;
    type_code: string;
    type_name: string;
    description?: string;
    extraction_prompt?: string;
    fields?: Omit<DocumentTypeField, 'id' | 'doc_type_id' | 'created_at' | 'updated_at'>[];
}

export interface DocumentTypeUpdate {
    type_name?: string;
    description?: string;
    extraction_prompt?: string;
    is_active?: boolean;
}

// 统计信息类型
export interface DocumentStatistics {
    total_documents: number;
    by_status: Record<string, number>;
    by_template?: Record<number, number>;
}

// 问答相关类型
export interface QARequest {
    question: string;
    template_id?: number;
    top_k?: number;
}

export interface QADocumentReference {
    document_id: number;
    title: string;
    snippet: string;
    score?: number;
}

export interface QAResponse {
    question: string;
    answer: string;
    references: QADocumentReference[];
    thinking_process?: string;
}

export interface QAStreamEvent {
    event: 'thinking' | 'references' | 'answer' | 'complete' | 'error';
    data: any;
    done: boolean;
}

// LLM日志相关类型
export interface LLMLog {
    id: number;
    provider: string;
    model: string;
    input_messages: Array<{ role: string; content: string }>;
    output_content?: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    duration_ms?: number;
    status: string;
    error_message?: string;
    user_id?: number;
    created_at: string;
}

export interface LLMLogListRequest extends PaginationParams {
    provider?: string;
    model?: string;
    status?: string;
    user_id?: number;
    start_date?: string;
    end_date?: string;
}

export interface LLMLogStatistics {
    total_calls: number;
    total_tokens: number;
    by_status: Record<string, number>;
    by_provider: Record<string, { calls: number; tokens: number }>;
    by_model: Record<string, { calls: number; tokens: number }>;
}

// 模板配置相关类型
export interface TemplateConfig {
    id: number;
    template_id: number;
    config_name: string;
    config_value: string;
    created_at: string;
    updated_at: string;
    is_active: boolean;
}

export interface TemplateConfigUpdate {
    config_value: string;
}
