import request from '../utils/request';
import type { ApiResponse } from '../types';
import type { DocumentType, DocumentTypeCreate, DocumentTypeUpdate, DocumentTypeField } from '../types';

/**
 * 文档类型管理 API
 */

// 创建文档类型
export const createDocumentType = (data: DocumentTypeCreate) => {
    return request.post<ApiResponse<DocumentType>>('/document-types/', data);
};

// 获取模板的所有文档类型
export const getDocumentTypesByTemplate = (templateId: number, includeInactive = false) => {
    return request.get<ApiResponse<DocumentType[]>>(`/document-types/template/${templateId}`, {
        params: { include_inactive: includeInactive }
    });
};

// 获取文档类型详情
export const getDocumentType = (docTypeId: number) => {
    return request.get<ApiResponse<DocumentType>>(`/document-types/${docTypeId}`);
};

// 更新文档类型
export const updateDocumentType = (docTypeId: number, data: DocumentTypeUpdate) => {
    return request.put<ApiResponse<DocumentType>>(`/document-types/${docTypeId}`, data);
};

// 删除文档类型
export const deleteDocumentType = (docTypeId: number) => {
    return request.delete<ApiResponse>(`/document-types/${docTypeId}`);
};

// 添加字段
export const addField = (docTypeId: number, data: Omit<DocumentTypeField, 'id' | 'doc_type_id' | 'created_at' | 'updated_at'>) => {
    return request.post<ApiResponse<DocumentTypeField>>(`/document-types/${docTypeId}/fields`, {
        doc_type_id: docTypeId,
        ...data
    });
};

// 获取所有字段
export const getFields = (docTypeId: number) => {
    return request.get<ApiResponse<DocumentTypeField[]>>(`/document-types/${docTypeId}/fields`);
};

// 更新字段
export const updateField = (fieldId: number, data: Partial<DocumentTypeField>) => {
    return request.put<ApiResponse<DocumentTypeField>>(`/document-types/fields/${fieldId}`, data);
};

// 删除字段
export const deleteField = (fieldId: number) => {
    return request.delete<ApiResponse>(`/document-types/fields/${fieldId}`);
};

// 批量更新字段
export const batchUpdateFields = (
    docTypeId: number,
    fields: Omit<DocumentTypeField, 'id' | 'doc_type_id' | 'created_at' | 'updated_at'>[]
) => {
    return request.put<ApiResponse<DocumentTypeField[]>>(`/document-types/${docTypeId}/fields/batch`, fields);
};

// 获取提取配置
export const getExtractionConfig = (docTypeId: number) => {
    return request.get<ApiResponse<{
        type_code: string;
        type_name: string;
        extraction_prompt?: string;
        fields: Array<{
            field_code: string;
            field_name: string;
            field_type: string;
            extraction_prompt?: string;
            is_required: boolean;
        }>;
    }>>(`/document-types/${docTypeId}/extraction-config`);
};
