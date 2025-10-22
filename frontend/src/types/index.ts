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
export enum UserRole {
    ADMIN = 'admin',
    USER = 'user',
    REVIEWER = 'reviewer',
}

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
    class_path?: Record<string, string>;
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
    class_path?: Record<string, string>;
    extracted_fields?: Record<string, any>;
    start_date?: string;
    end_date?: string;
    status?: string;
}

// 编号规则相关类型
export interface NumberingRule {
    id: number;
    template_id: number;
    rule_format: string;
    separator: string;
    auto_increment: boolean;
    current_sequence: number;
    created_at: string;
}

export interface NumberingRuleCreate {
    template_id: number;
    rule_format: string;
    separator?: string;
    auto_increment?: boolean;
}

// 信息抽取相关类型
export interface ExtractionField {
    name: string;
    type: 'text' | 'number' | 'array' | 'date' | 'boolean';
    method: 'regex' | 'llm' | 'rule';
    pattern?: string;
    prompt?: string;
    required?: boolean;
}

export interface ExtractionConfig {
    id: number;
    name: string;
    doc_type: string;
    extract_fields: ExtractionField[];
    is_active: boolean;
    created_at: string;
    updated_at: string;
}

export interface ExtractionConfigCreate {
    name: string;
    doc_type: string;
    extract_fields: ExtractionField[];
}

export interface ExtractionRequest {
    document_id: number;
    config_id: number;
}

export interface ExtractionResponse {
    document_id: number;
    extracted_data: Record<string, any>;
    success_fields: string[];
    failed_fields: string[];
}

// 分类相关类型
export interface ClassificationRequest {
    document_id: number;
    template_id: number;
    force_reclassify?: boolean;
}

export interface ClassificationResponse {
    document_id: number;
    class_path: Record<string, string>;
    class_code: string;
    confidence?: number;
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

export interface SystemConfigCreate {
    config_key: string;
    config_value: Record<string, any>;
    description?: string;
    is_public?: boolean;
}

// 统计信息类型
export interface DocumentStatistics {
    total_documents: number;
    by_status: Record<string, number>;
    by_template?: Record<number, number>;
}
