import { request } from '../utils/request';
import type {
    ApiResponse,
    QARequest,
    QAResponse,
    TemplateSelection,
} from '../types';

// 定义模板类型
interface Template {
    id: number;
    name: string;
}

export const qaService = {
    // 非流式问答
    askQuestion: (data: QARequest) =>
        request.post<ApiResponse<QAResponse>>('/qa/ask', data),

    // 流式问答（返回URL供SSEClient使用）
    getStreamUrl: () => {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
        return `${baseUrl}/qa/ask/stream`;
    },

    // 智能体流式问答（返回URL供SSEClient使用）
    getAgentStreamUrl: () => {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
        return `${baseUrl}/qa/ask/agent/stream`;
    },

    // 澄清问题后继续智能体问答
    clarifyAgentQuestion: (data: QARequest, clarification: string, sessionId: string) => {
        const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
        const url = `${baseUrl}/qa/ask/agent/clarify`;

        // 创建FormData
        const formData = new FormData();
        formData.append('question', data.question);
        if (data.template_id) {
            formData.append('template_id', data.template_id.toString());
        }
        if (data.top_k) {
            formData.append('top_k', data.top_k.toString());
        }
        formData.append('clarification', clarification);
        formData.append('session_id', sessionId);

        return fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                // 注意：不需要设置Content-Type，因为FormData会自动设置
                // 认证头部应该由request拦截器添加
            }
        });
    },

    // 获取模板列表
    getTemplates: () =>
        request.get<ApiResponse<Template[]>>('/templates'),

    getAllTemplates: () =>
        request.get<ApiResponse<TemplateSelection[]>>('/templates/all'),
};