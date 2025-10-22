import { request } from '../utils/request';
import type { ApiResponse, DocumentStatistics } from '../types';

export const searchService = {
    // 获取统计信息
    getStatistics: (template_id?: number) =>
        request.get<ApiResponse<DocumentStatistics>>('/search/statistics', {
            params: { template_id },
        }),

    // 索引文档
    indexDocument: (document_id: number) =>
        request.post<ApiResponse<void>>(`/search/index/${document_id}`),
};
