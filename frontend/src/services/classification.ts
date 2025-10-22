import { request } from '../utils/request';
import type { ApiResponse, ClassificationRequest, ClassificationResponse } from '../types';

export const classificationService = {
    // 分类单个文档
    classifyDocument: (data: ClassificationRequest) =>
        request.post<ApiResponse<ClassificationResponse>>('/classification/classify', data),

    // 批量分类
    batchClassify: (document_ids: number[], template_id: number) =>
        request.post<ApiResponse<{
            results: ClassificationResponse[];
            success_count: number;
            total: number;
        }>>('/classification/classify-batch', { document_ids, template_id }),
};
