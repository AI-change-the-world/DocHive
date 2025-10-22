import { request } from '../utils/request';
import type { ApiResponse, LoginRequest, RegisterRequest, Token, User } from '../types';

export const authService = {
    // 用户登录
    login: (data: LoginRequest) =>
        request.post<ApiResponse<Token>>('/auth/login', data),

    // 用户注册
    register: (data: RegisterRequest) =>
        request.post<ApiResponse<User>>('/auth/register', data),

    // 获取当前用户信息
    getCurrentUser: () =>
        request.get<ApiResponse<User>>('/auth/me'),

    // 刷新令牌
    refreshToken: (refresh_token: string) =>
        request.post<ApiResponse<Token>>('/auth/refresh', { refresh_token }),

    // 登出（前端清除本地存储）
    logout: () => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    },
};
