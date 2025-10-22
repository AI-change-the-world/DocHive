import { request } from '../utils/request';
import type { ApiResponse, NumberingRule, NumberingRuleCreate } from '../types';

export const numberingService = {
    // 生成文档编号
    generateNumber: (document_id: number) =>
        request.post<ApiResponse<{ document_id: number; class_code: string }>>(
            `/numbering/generate/${document_id}`
        ),

    // 创建编号规则
    createRule: (data: NumberingRuleCreate) =>
        request.post<ApiResponse<NumberingRule>>('/numbering/rules', data),

    // 获取模板的编号规则
    getTemplateRule: (template_id: number) =>
        request.get<ApiResponse<NumberingRule>>(`/numbering/rules/template/${template_id}`),

    // 重置序列号
    resetSequence: (rule_id: number, new_sequence: number = 0) =>
        request.post<ApiResponse<void>>(`/numbering/rules/${rule_id}/reset`, {
            new_sequence,
        }),
};
