import { request } from '../utils/request';
import type {
    ApiResponse,
    QARequest,
    QAResponse,
} from '../types';

export const qaService = {
    // 非流式问答
    askQuestion: (data: QARequest) =>
        request.post<ApiResponse<QAResponse>>('/qa/ask', data),

    // 流式问答（返回URL供SSEClient使用）
    getStreamUrl: () => {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
        return `${baseUrl}/qa/ask/stream`;
    },
};
