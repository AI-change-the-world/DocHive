import { request } from '../utils/request';
import type {
    ApiResponse,
    ExtractionConfig,
    ExtractionConfigCreate,
    ExtractionRequest,
    ExtractionResponse,
    PaginatedResponse,
} from '../types';

export const extractionService = {
    // 抽取文档信息
    extractDocument: (data: ExtractionRequest) =>
        request.post<ApiResponse<ExtractionResponse>>('/extraction/extract', data),

    // 获取抽取配置列表
    getConfigs: (params: { page?: number; page_size?: number; doc_type?: string }) =>
        request.get<ApiResponse<PaginatedResponse<ExtractionConfig>>>('/extraction/configs', {
            params,
        }),

    // 获取抽取配置详情
    getConfig: (id: number) =>
        request.get<ApiResponse<ExtractionConfig>>(`/extraction/configs/${id}`),

    // 创建抽取配置
    createConfig: (data: ExtractionConfigCreate) =>
        request.post<ApiResponse<ExtractionConfig>>('/extraction/configs', data),
};
