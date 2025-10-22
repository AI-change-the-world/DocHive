import { request } from '../utils/request';
import type { ApiResponse, SystemConfig, SystemConfigCreate } from '../types';

export const configService = {
    // 获取配置列表
    getConfigs: (is_public?: boolean) =>
        request.get<ApiResponse<SystemConfig[]>>('/config/', {
            params: { is_public },
        }),

    // 获取配置
    getConfig: (config_key: string) =>
        request.get<ApiResponse<SystemConfig>>(`/config/${config_key}`),

    // 创建配置
    createConfig: (data: SystemConfigCreate) =>
        request.post<ApiResponse<SystemConfig>>('/config/', data),

    // 更新配置
    updateConfig: (config_key: string, data: Partial<SystemConfigCreate>) =>
        request.put<ApiResponse<SystemConfig>>(`/config/${config_key}`, data),

    // 删除配置
    deleteConfig: (config_key: string) =>
        request.delete<ApiResponse<void>>(`/config/${config_key}`),
};
