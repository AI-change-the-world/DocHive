import { request } from '../utils/request';
import type {
    ApiResponse,
    TemplateConfig,
    TemplateConfigUpdate,
} from '../types';

export const templateConfigService = {
    // 获取模板的所有配置项
    getTemplateConfigs: (templateId: number) =>
        request.get<ApiResponse<TemplateConfig[]>>(`/template-configs/template/${templateId}`),

    // 获取单个配置详情
    getConfigDetail: (id: number) =>
        request.get<ApiResponse<TemplateConfig>>(`/template-configs/${id}`),

    // 更新配置值
    updateConfig: (id: number, data: TemplateConfigUpdate) =>
        request.put<ApiResponse<TemplateConfig>>(`/template-configs/${id}`, data),

    // 批量更新配置
    batchUpdateConfigs: (updates: Array<{ id: number; config_value: string }>) =>
        request.post<ApiResponse<TemplateConfig[]>>('/template-configs/batch-update', updates),
};
