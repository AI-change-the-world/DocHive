import React, { useState, useEffect } from 'react';
import {
    Table,
    Button,
    Space,
    Modal,
    Form,
    Input,
    message,
    Popconfirm,
    Tag,
    Card,
} from 'antd';
import {
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    EyeOutlined,
} from '@ant-design/icons';
import { templateService } from '../../services/template';
import type { ClassTemplate, TemplateLevel } from '../../types';
import TemplateDesigner from './components/TemplateDesigner';

const TemplatePage: React.FC = () => {
    const [templates, setTemplates] = useState<ClassTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState<ClassTemplate | null>(null);
    const [total, setTotal] = useState(0);
    const [pagination, setPagination] = useState({ page: 1, page_size: 10 });
    const [form] = Form.useForm();

    useEffect(() => {
        fetchTemplates();
    }, [pagination]);

    const fetchTemplates = async () => {
        setLoading(true);
        try {
            const response = await templateService.getTemplates(pagination);
            setTemplates(response.data.items);
            setTotal(response.data.total);
        } catch (error) {
            message.error('获取模板列表失败');
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = () => {
        setEditingTemplate(null);
        form.resetFields();
        setModalVisible(true);
    };

    const handleEdit = (record: ClassTemplate) => {
        setEditingTemplate(record);
        form.setFieldsValue(record);
        setModalVisible(true);
    };

    const handleDelete = async (id: number) => {
        try {
            await templateService.deleteTemplate(id);
            message.success('删除成功');
            fetchTemplates();
        } catch (error) {
            message.error('删除失败');
        }
    };

    const handleSubmit = async (values: any) => {
        try {
            if (editingTemplate) {
                await templateService.updateTemplate(editingTemplate.id, values);
                message.success('更新成功');
            } else {
                await templateService.createTemplate(values);
                message.success('创建成功');
            }
            setModalVisible(false);
            fetchTemplates();
        } catch (error) {
            message.error('操作失败');
        }
    };

    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 80,
        },
        {
            title: '模板名称',
            dataIndex: 'name',
            key: 'name',
        },
        {
            title: '层级数',
            dataIndex: 'levels',
            key: 'levels',
            render: (levels: TemplateLevel[]) => levels.length,
        },
        {
            title: '版本',
            dataIndex: 'version',
            key: 'version',
        },
        {
            title: '状态',
            dataIndex: 'is_active',
            key: 'is_active',
            render: (is_active: boolean) => (
                <Tag color={is_active ? 'green' : 'red'}>
                    {is_active ? '激活' : '禁用'}
                </Tag>
            ),
        },
        {
            title: '创建时间',
            dataIndex: 'created_at',
            key: 'created_at',
            render: (text: string) => new Date(text).toLocaleString(),
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: ClassTemplate) => (
                <Space>
                    <Button
                        type="link"
                        icon={<EyeOutlined />}
                        onClick={() => handleEdit(record)}
                    >
                        查看
                    </Button>
                    <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(record)}
                    >
                        编辑
                    </Button>
                    <Popconfirm
                        title="确定删除此模板吗？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Button type="link" danger icon={<DeleteOutlined />}>
                            删除
                        </Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div className="p-6">
            <Card>
                <div className="mb-4 flex justify-between items-center">
                    <h2 className="text-2xl font-bold">分类模板管理</h2>
                    <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={handleCreate}
                    >
                        创建模板
                    </Button>
                </div>

                <Table
                    columns={columns}
                    dataSource={templates}
                    loading={loading}
                    rowKey="id"
                    pagination={{
                        total,
                        current: pagination.page,
                        pageSize: pagination.page_size,
                        onChange: (page, pageSize) => {
                            setPagination({ page, page_size: pageSize });
                        },
                    }}
                />

                <Modal
                    title={editingTemplate ? '编辑模板' : '创建模板'}
                    open={modalVisible}
                    onCancel={() => setModalVisible(false)}
                    width={800}
                    footer={null}
                >
                    <Form
                        form={form}
                        layout="vertical"
                        onFinish={handleSubmit}
                    >
                        <Form.Item
                            name="name"
                            label="模板名称"
                            rules={[{ required: true, message: '请输入模板名称' }]}
                        >
                            <Input placeholder="请输入模板名称" />
                        </Form.Item>

                        <Form.Item
                            name="description"
                            label="模板描述"
                        >
                            <Input.TextArea rows={3} placeholder="请输入模板描述" />
                        </Form.Item>

                        <Form.Item
                            name="version"
                            label="版本号"
                            initialValue="1.0"
                        >
                            <Input placeholder="请输入版本号" />
                        </Form.Item>

                        <Form.Item
                            name="levels"
                            label="层级设计"
                            rules={[{ required: true, message: '请设计至少一个层级' }]}
                        >
                            <TemplateDesigner />
                        </Form.Item>

                        <Form.Item>
                            <Space>
                                <Button type="primary" htmlType="submit">
                                    提交
                                </Button>
                                <Button onClick={() => setModalVisible(false)}>
                                    取消
                                </Button>
                            </Space>
                        </Form.Item>
                    </Form>
                </Modal>
            </Card>
        </div>
    );
};

export default TemplatePage;
