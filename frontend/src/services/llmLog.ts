import { request } from '../utils/request';
import type {
    ApiResponse,
    LLMLog,
    LLMLogListRequest,
    LLMLogStatistics,
    PaginatedResponse,
} from '../types';

export const llmLogService = {
    // 查询LLM日志列表
    getLogs: (data: LLMLogListRequest) =>
        request.post<ApiResponse<PaginatedResponse<LLMLog>>>('/llm-logs/list', data),

    // 获取统计信息
    getStatistics: (params?: {
        provider?: string;
        model?: string;
        user_id?: number;
    }) =>
        request.get<ApiResponse<LLMLogStatistics>>('/llm-logs/statistics', { params }),

    // 获取日志详情
    getLogDetail: (id: number) =>
        request.get<ApiResponse<LLMLog>>(`/llm-logs/${id}`),
};
