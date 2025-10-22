import React, { useState } from 'react';
import { Form, Input, Button, Card, message, Tabs } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { authService } from '../../services/auth';
import { useAuthStore } from '../../store/auth';
import type { LoginRequest, RegisterRequest } from '../../types';

const Login: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('login');
    const navigate = useNavigate();
    const { setUser, setToken } = useAuthStore();

    const handleLogin = async (values: LoginRequest) => {
        setLoading(true);
        try {
            const response = await authService.login(values);
            const { access_token, refresh_token, user } = response.data;

            setToken(access_token);
            if (user) {
                setUser(user);
            }
            localStorage.setItem('refresh_token', refresh_token);

            message.success('登录成功！');
            navigate('/dashboard');
        } catch (error) {
            message.error('登录失败，请检查用户名和密码');
        } finally {
            setLoading(false);
        }
    };

    const handleRegister = async (values: RegisterRequest) => {
        setLoading(true);
        try {
            await authService.register(values);
            message.success('注册成功，请登录！');
            setActiveTab('login');
        } catch (error) {
            message.error('注册失败');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
            <Card className="w-full max-w-md shadow-lg">
                <div className="text-center mb-6">
                    <h1 className="text-3xl font-bold text-gray-800">DocHive</h1>
                    <p className="text-gray-600 mt-2">智能文档分类分级系统</p>
                </div>

                <Tabs
                    activeKey={activeTab}
                    onChange={setActiveTab}
                    centered
                    items={[
                        {
                            key: 'login',
                            label: '登录',
                            children: (
                                <Form
                                    name="login"
                                    onFinish={handleLogin}
                                    autoComplete="off"
                                    size="large"
                                >
                                    <Form.Item
                                        name="username"
                                        rules={[{ required: true, message: '请输入用户名' }]}
                                    >
                                        <Input
                                            prefix={<UserOutlined />}
                                            placeholder="用户名"
                                        />
                                    </Form.Item>

                                    <Form.Item
                                        name="password"
                                        rules={[{ required: true, message: '请输入密码' }]}
                                    >
                                        <Input.Password
                                            prefix={<LockOutlined />}
                                            placeholder="密码"
                                        />
                                    </Form.Item>

                                    <Form.Item>
                                        <Button
                                            type="primary"
                                            htmlType="submit"
                                            loading={loading}
                                            block
                                        >
                                            登录
                                        </Button>
                                    </Form.Item>
                                </Form>
                            ),
                        },
                        {
                            key: 'register',
                            label: '注册',
                            children: (
                                <Form
                                    name="register"
                                    onFinish={handleRegister}
                                    autoComplete="off"
                                    size="large"
                                >
                                    <Form.Item
                                        name="username"
                                        rules={[
                                            { required: true, message: '请输入用户名' },
                                            { min: 3, message: '用户名至少3个字符' },
                                        ]}
                                    >
                                        <Input
                                            prefix={<UserOutlined />}
                                            placeholder="用户名"
                                        />
                                    </Form.Item>

                                    <Form.Item
                                        name="email"
                                        rules={[
                                            { required: true, message: '请输入邮箱' },
                                            { type: 'email', message: '请输入有效的邮箱地址' },
                                        ]}
                                    >
                                        <Input
                                            prefix={<MailOutlined />}
                                            placeholder="邮箱"
                                        />
                                    </Form.Item>

                                    <Form.Item
                                        name="password"
                                        rules={[
                                            { required: true, message: '请输入密码' },
                                            { min: 6, message: '密码至少6个字符' },
                                        ]}
                                    >
                                        <Input.Password
                                            prefix={<LockOutlined />}
                                            placeholder="密码"
                                        />
                                    </Form.Item>

                                    <Form.Item
                                        name="confirm"
                                        dependencies={['password']}
                                        rules={[
                                            { required: true, message: '请确认密码' },
                                            ({ getFieldValue }) => ({
                                                validator(_, value) {
                                                    if (!value || getFieldValue('password') === value) {
                                                        return Promise.resolve();
                                                    }
                                                    return Promise.reject(new Error('两次输入的密码不一致'));
                                                },
                                            }),
                                        ]}
                                    >
                                        <Input.Password
                                            prefix={<LockOutlined />}
                                            placeholder="确认密码"
                                        />
                                    </Form.Item>

                                    <Form.Item>
                                        <Button
                                            type="primary"
                                            htmlType="submit"
                                            loading={loading}
                                            block
                                        >
                                            注册
                                        </Button>
                                    </Form.Item>
                                </Form>
                            ),
                        },
                    ]}
                />
            </Card>
        </div>
    );
};

export default Login;
