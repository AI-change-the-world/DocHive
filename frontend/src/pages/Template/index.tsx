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
    Drawer,
} from 'antd';
import {
    PlusOutlined,
    EditOutlined,
    DeleteOutlined,
    EyeOutlined,
    RobotOutlined,
    CopyOutlined,
} from '@ant-design/icons';
import { templateService } from '../../services/template';
import type { ClassTemplate, TemplateLevel } from '../../types';
import type { SSEEvent } from '../../utils/sseClient';
import TemplateDesigner from './components/TemplateDesigner';
import DocumentTypeManager from './components/DocumentTypeManager';

const TemplatePage: React.FC = () => {
    const [templates, setTemplates] = useState<ClassTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState<ClassTemplate | null>(null);
    const [total, setTotal] = useState(0);
    const [pagination, setPagination] = useState({ page: 1, page_size: 10 });
    const [form] = Form.useForm();
    const [submitLoading, setSubmitLoading] = useState(false);

    // 文档类型管理抽屉
    const [docTypeDrawerVisible, setDocTypeDrawerVisible] = useState(false);
    const [selectedTemplate, setSelectedTemplate] = useState<ClassTemplate | null>(null);

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

    const handleCopy = (record: ClassTemplate) => {
        setEditingTemplate(null); // 设置为null,表示是创建新模板而不是编辑
        // 复制模板数据,但不包含id
        const { id, created_at, updated_at, ...copyData } = record;
        form.setFieldsValue({
            ...copyData,
            name: `${copyData.name} - 副本`, // 添加副本标识
        });
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
        if (editingTemplate) {
            // 编辑模式 - 使用传统接口
            try {
                setSubmitLoading(true);
                await templateService.updateTemplate(editingTemplate.id, values);
                message.success('更新成功');
                setModalVisible(false);
                fetchTemplates();
            } catch (error) {
                message.error('更新失败');
            } finally {
                setSubmitLoading(false);
            }
        } else {
            // 创建模式 - 使用流式接口
            setSubmitLoading(true);

            templateService.createTemplateStream(
                values,
                (event: SSEEvent) => {
                    const { event: eventType, data } = event;

                    // 只处理 complete 和 error 事件
                    if (eventType === 'complete') {
                        console.log('模板创建成功');
                        message.success('模板创建成功！');
                        setSubmitLoading(false);
                        setModalVisible(false);
                        fetchTemplates();
                    } else if (eventType === 'error') {
                        console.error('创建失败:', data?.message);
                        message.error(data?.message || '创建失败');
                        setSubmitLoading(false);
                    }
                },
                (error: Error) => {
                    console.error('请求失败:', error);
                    message.error('请求失败: ' + error.message);
                    setSubmitLoading(false);
                },
                () => {
                    message.success('模板创建成功！');
                    setSubmitLoading(false);
                    setModalVisible(false);
                    fetchTemplates();
                    console.log('流式创建完成');
                }
            );
        }
    };

    const handleViewDocumentTypes = (template: ClassTemplate) => {
        setSelectedTemplate(template);
        setDocTypeDrawerVisible(true);
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
                        onClick={() => handleViewDocumentTypes(record)}
                    >
                        查看类别
                    </Button>
                    <Button
                        type="link"
                        icon={<CopyOutlined />}
                        onClick={() => handleCopy(record)}
                    >
                        复制
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
                    onCancel={() => {
                        if (!submitLoading) {
                            setModalVisible(false);
                        }
                    }}
                    width={'calc(100vw - 200px)'}
                    footer={null}
                    bodyStyle={{
                        maxHeight: 'calc(100vh - 200px)',
                        overflowY: 'auto',
                        paddingRight: 8
                    }}
                    closable={!submitLoading}
                    maskClosable={!submitLoading}
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
                            <Input placeholder="请输入模板名称" disabled={submitLoading} />
                        </Form.Item>

                        <Form.Item
                            name="description"
                            label="模板描述"
                        >
                            <Input.TextArea rows={3} placeholder="请输入模板描述" disabled={submitLoading} />
                        </Form.Item>

                        <Form.Item
                            name="version"
                            label="版本号"
                            initialValue="1.0"
                        >
                            <Input placeholder="请输入版本号" disabled={submitLoading} />
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
                                <Button type="primary" htmlType="submit" loading={submitLoading}>
                                    提交
                                </Button>
                                <Button onClick={() => setModalVisible(false)} disabled={submitLoading}>
                                    取消
                                </Button>
                            </Space>
                        </Form.Item>
                    </Form>
                </Modal>

                {/* 文档类型管理抽屉 */}
                <Drawer
                    title={`文档类型管理 - ${selectedTemplate?.name || ''}`}
                    width={1000}
                    open={docTypeDrawerVisible}
                    onClose={() => setDocTypeDrawerVisible(false)}
                    destroyOnClose
                >
                    {selectedTemplate && (
                        <DocumentTypeManager
                            template={selectedTemplate}
                            onClose={() => setDocTypeDrawerVisible(false)}
                        />
                    )}
                </Drawer>
            </Card>
        </div>
    );
};

export default TemplatePage;
