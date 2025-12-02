import { request } from "../utils/request";
import type { ApiResponse } from "../types";

export interface WritingTemplate {
    id: number;
    title: string;
    theme: string;
    content: string;
    description?: string;
    tags: string[];
    template_id: number;
    word_count?: number;
    created_at: string;
}

export interface WritingTemplateCreate {
    title: string;
    theme: string;
    content: string;
    template_id: number;
    description?: string;
    tags?: string[];
}

export const writingTemplateService = {
    // 获取写作样例列表
    getTemplates: (templateId: number) =>
        request.get<ApiResponse<WritingTemplate[]>>(
            `/writing-templates/?template_id=${templateId}`
        ),

    // 获取样例详情
    getTemplate: (id: number) =>
        request.get<ApiResponse<WritingTemplate>>(`/writing-templates/${id}`),

    // 创建写作样例
    createTemplate: (data: WritingTemplateCreate) =>
        request.post<ApiResponse<WritingTemplate>>("/writing-templates/", data),

    // 上传文件创建样例
    uploadFile: (formData: FormData) =>
        request.post<ApiResponse<WritingTemplate>>(
            "/writing-templates/upload",
            formData,
            {
                headers: {
                    "Content-Type": "multipart/form-data",
                },
            }
        ),

    // 删除样例
    deleteTemplate: (id: number) =>
        request.delete<ApiResponse<void>>(`/writing-templates/${id}`),
};
