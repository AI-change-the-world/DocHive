import { request } from '../utils/request';
import { SSEClient, type SSEEvent } from '../utils/sseClient';
import type {
    ApiResponse,
    Document,
    DocumentSearchRequest,
    PaginatedResponse,
} from '../types';

export const documentService = {
    // 上传文档 (SSE 流式上传)
    uploadDocumentSSE: (
        formData: FormData,
        onMessage: (event: SSEEvent) => void,
        onError?: (error: Error) => void,
        onComplete?: () => void
    ) => {
        const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/documents/upload`;
        const sseClient = new SSEClient(url, formData, onMessage, onError, onComplete);
        sseClient.start();
        return sseClient;
    },

    // 手动创建文档（SSE 流式创建）
    createDocumentManuallySSE: (
        formData: FormData,
        onMessage: (event: SSEEvent) => void,
        onError?: (error: Error) => void,
        onComplete?: () => void
    ) => {
        const url = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'}/documents/create-manually`;
        const sseClient = new SSEClient(url, formData, onMessage, onError, onComplete);
        sseClient.start();
        return sseClient;
    },

    // 传统的上传文档方法（保留以供兼容性）
    uploadDocument: (formData: FormData) =>
        request.upload<ApiResponse<Document>>('/documents/upload', formData),

    // 获取分类编码列表
    getClassCodes: (templateId: number) =>
        request.get<ApiResponse<Array<{ value: string; label: string }>>>(
            `/documents/class-codes/${templateId}`
        ),

    // 获取模板层级结构
    getTemplateLevels: (templateId: number) =>
        request.get<ApiResponse<Array<any>>>(
            `/documents/template-levels/${templateId}`
        ),

    // 获取文档列表
    getDocuments: (params: {
        page?: number;
        page_size?: number;
        template_id?: number;
        status?: string;
    }) =>
        request.get<ApiResponse<PaginatedResponse<Document>>>('/documents/', { params }),

    // 获取文档详情
    getDocument: (id: number) =>
        request.get<ApiResponse<Document>>(`/documents/${id}`),

    // 更新文档
    updateDocument: (id: number, data: Partial<Document>) =>
        request.put<ApiResponse<Document>>(`/documents/${id}`, data),

    // 删除文档
    deleteDocument: (id: number) =>
        request.delete<ApiResponse<void>>(`/documents/${id}`),

    // 获取下载链接
    getDownloadUrl: (id: number) =>
        request.get<ApiResponse<{ download_url: string; expires_in: number }>>(
            `/documents/${id}/download`
        ),

    // 搜索文档
    searchDocuments: (data: DocumentSearchRequest) =>
        request.post<ApiResponse<PaginatedResponse<Document>>>('/search/', data),
};