import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios';
import { message } from 'antd';

// 创建 axios 实例
const instance: AxiosInstance = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
    timeout: 60000,
    headers: {
        'Content-Type': 'application/json',
    },
});

// 请求拦截器
instance.interceptors.request.use(
    (config) => {
        // 从 localStorage 获取 token
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// 响应拦截器
instance.interceptors.response.use(
    (response: AxiosResponse) => {
        return response.data;
    },
    (error) => {
        if (error.response) {
            const { status, data } = error.response;

            switch (status) {
                case 401:
                    message.error('未授权，请重新登录');
                    localStorage.removeItem('access_token');
                    localStorage.removeItem('refresh_token');
                    window.location.href = '/login';
                    break;
                case 403:
                    message.error('权限不足');
                    break;
                case 404:
                    message.error('请求的资源不存在');
                    break;
                case 500:
                    message.error('服务器错误');
                    break;
                default:
                    message.error(data?.detail || data?.message || '请求失败');
            }
        } else if (error.request) {
            message.error('网络错误，请检查网络连接');
        } else {
            message.error('请求配置错误');
        }

        return Promise.reject(error);
    }
);

export default instance;

// 导出常用方法
export const request = {
    get: <T = any>(url: string, config?: AxiosRequestConfig) =>
        instance.get<any, T>(url, config),

    post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) =>
        instance.post<any, T>(url, data, config),

    put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) =>
        instance.put<any, T>(url, data, config),

    delete: <T = any>(url: string, config?: AxiosRequestConfig) =>
        instance.delete<any, T>(url, config),

    upload: <T = any>(url: string, formData: FormData) =>
        instance.post<any, T>(url, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        }),
};
