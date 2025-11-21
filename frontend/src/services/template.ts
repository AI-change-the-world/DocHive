import { request } from '../utils/request';
import { SSEClient } from '../utils/sseClient';
import type {
    ApiResponse,
    ClassTemplate,
    ClassTemplateCreate,
    ClassTemplateUpdate,
    PaginatedResponse,
} from '../types';
import type { SSEEvent } from '../utils/sseClient';

export const templateService = {
    // 获取模板列表
    getTemplates: (params: { page?: number; page_size?: number; is_active?: boolean }) =>
        request.get<ApiResponse<PaginatedResponse<ClassTemplate>>>('/templates/', { params }),

    // 获取模板详情
    getTemplate: (id: number) =>
        request.get<ApiResponse<ClassTemplate>>(`/templates/${id}`),

    // 创建模板(流式)
    createTemplateStream: (
        data: ClassTemplateCreate,
        onMessage: (event: SSEEvent) => void,
        onError?: (error: Error) => void,
        onComplete?: () => void
    ) => {
        const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        const url = `${baseURL}/templates/`;
        const client = new SSEClient(url, data, onMessage, onError, onComplete);
        client.start();
        return client;
    },

    // 更新模板
    updateTemplate: (id: number, data: ClassTemplateUpdate) =>
        request.put<ApiResponse<ClassTemplate>>(`/templates/${id}`, data),

    // 删除模板
    deleteTemplate: (id: number) =>
        request.delete<ApiResponse<void>>(`/templates/${id}`),
};
