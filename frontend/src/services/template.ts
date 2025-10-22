import { request } from '../utils/request';
import type {
    ApiResponse,
    ClassTemplate,
    ClassTemplateCreate,
    ClassTemplateUpdate,
    PaginatedResponse,
} from '../types';

export const templateService = {
    // 获取模板列表
    getTemplates: (params: { page?: number; page_size?: number; is_active?: boolean }) =>
        request.get<ApiResponse<PaginatedResponse<ClassTemplate>>>('/templates/', { params }),

    // 获取模板详情
    getTemplate: (id: number) =>
        request.get<ApiResponse<ClassTemplate>>(`/templates/${id}`),

    // 创建模板
    createTemplate: (data: ClassTemplateCreate) =>
        request.post<ApiResponse<ClassTemplate>>('/templates/', data),

    // 更新模板
    updateTemplate: (id: number, data: ClassTemplateUpdate) =>
        request.put<ApiResponse<ClassTemplate>>(`/templates/${id}`, data),

    // 删除模板
    deleteTemplate: (id: number) =>
        request.delete<ApiResponse<void>>(`/templates/${id}`),
};
