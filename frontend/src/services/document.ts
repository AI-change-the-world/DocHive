import { request } from '../utils/request';
import type {
    ApiResponse,
    Document,
    DocumentSearchRequest,
    PaginatedResponse,
} from '../types';

export const documentService = {
    // 上传文档
    uploadDocument: (formData: FormData) =>
        request.upload<ApiResponse<Document>>('/documents/upload', formData),

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
