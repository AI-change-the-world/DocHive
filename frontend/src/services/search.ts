import { request } from '../utils/request';
import type { ApiResponse, DocumentStatistics } from '../types';

export const searchService = {
    // 获取统计信息
    getStatistics: (template_id?: number) =>
        request.get<ApiResponse<DocumentStatistics>>('/documents/statistics', {
            params: { template_id },
        }),
};
