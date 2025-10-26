import { useState, useEffect } from 'react';
import { Table, Card, Button, Select, Input, message, Modal, Form, Typography, Space } from 'antd';
import { SettingOutlined, EditOutlined, SaveOutlined } from '@ant-design/icons';
import type { TemplateConfig, ClassTemplate } from '../../types';
import { templateConfigService } from '../../services/templateConfig';
import { templateService } from '../../services';

const { Title, Text } = Typography;
const { TextArea } = Input;

export default function TemplateConfigPage() {
    const [configs, setConfigs] = useState<TemplateConfig[]>([]);
    const [templates, setTemplates] = useState<ClassTemplate[]>([]);
    const [selectedTemplateId, setSelectedTemplateId] = useState<number>();
    const [loading, setLoading] = useState(false);
    const [editVisible, setEditVisible] = useState(false);
    const [editingConfig, setEditingConfig] = useState<TemplateConfig | null>(null);
    const [form] = Form.useForm();

    // 加载模板列表
    const loadTemplates = async () => {
        try {
            const response = await templateService.getTemplates({ page: 1, page_size: 100 });
            setTemplates(response.data.items);
        } catch (error: any) {
            message.error(`加载模板列表失败: ${error.message}`);
        }
    };

    // 加载配置列表
    const loadConfigs = async (templateId: number) => {
        setLoading(true);
        try {
            const response = await templateConfigService.getTemplateConfigs(templateId);
            setConfigs(response.data);
        } catch (error: any) {
            message.error(`加载配置失败: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadTemplates();
    }, []);

    useEffect(() => {
        if (selectedTemplateId) {
            loadConfigs(selectedTemplateId);
        } else {
            setConfigs([]);
        }
    }, [selectedTemplateId]);

    // 打开编辑对话框
    const handleEdit = (record: TemplateConfig) => {
        setEditingConfig(record);
        form.setFieldsValue({
            config_value: record.config_value,
        });
        setEditVisible(true);
    };

    // 保存配置
    const handleSave = async () => {
        if (!editingConfig) return;

        try {
            const values = await form.validateFields();
            await templateConfigService.updateConfig(editingConfig.id, values);
            message.success('配置更新成功');
            setEditVisible(false);
            if (selectedTemplateId) {
                loadConfigs(selectedTemplateId);
            }
        } catch (error: any) {
            message.error(`更新失败: ${error.message || '请检查表单'}`);
        }
    };

    const columns = [
        {
            title: '配置名称',
            dataIndex: 'config_name',
            key: 'config_name',
            width: 200,
        },
        {
            title: '配置值',
            dataIndex: 'config_value',
            key: 'config_value',
            ellipsis: true,
            render: (text: string) => (
                <div className="max-w-md">
                    <Text ellipsis={{ tooltip: text }}>{text}</Text>
                </div>
            ),
        },
        {
            title: '更新时间',
            dataIndex: 'updated_at',
            key: 'updated_at',
            width: 180,
            render: (time: string) => new Date(time).toLocaleString(),
        },
        {
            title: '操作',
            key: 'actions',
            width: 120,
            fixed: 'right' as const,
            render: (_: any, record: TemplateConfig) => (
                <Button
                    type="link"
                    icon={<EditOutlined />}
                    onClick={() => handleEdit(record)}
                >
                    编辑
                </Button>
            ),
        },
    ];

    return (
        <div className="h-full flex flex-col space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    <SettingOutlined className="text-3xl text-primary-600" />
                    <Title level={2} className="!mb-0">模板配置管理</Title>
                </div>
            </div>

            {/* 模板选择 */}
            <Card>
                <Space>
                    <Text strong>选择模板:</Text>
                    <Select
                        placeholder="请选择模板"
                        style={{ width: 300 }}
                        value={selectedTemplateId}
                        onChange={setSelectedTemplateId}
                        options={templates.map(t => ({
                            label: t.name,
                            value: t.id,
                        }))}
                    />
                    {selectedTemplateId && (
                        <Text type="secondary">
                            共 {configs.length} 个配置项
                        </Text>
                    )}
                </Space>
            </Card>

            {/* 配置列表 */}
            <Card className="flex-1">
                {selectedTemplateId ? (
                    <Table
                        columns={columns}
                        dataSource={configs}
                        loading={loading}
                        rowKey="id"
                        pagination={false}
                        scroll={{ y: 'calc(100vh - 350px)' }}
                    />
                ) : (
                    <div className="flex items-center justify-center h-64 text-gray-400">
                        <div className="text-center">
                            <SettingOutlined className="text-6xl mb-4" />
                            <Text type="secondary">请先选择一个模板查看配置</Text>
                        </div>
                    </div>
                )}
            </Card>

            {/* 编辑对话框 */}
            <Modal
                title={`编辑配置: ${editingConfig?.config_name}`}
                open={editVisible}
                onCancel={() => setEditVisible(false)}
                onOk={handleSave}
                okText="保存"
                cancelText="取消"
                width={600}
                okButtonProps={{
                    icon: <SaveOutlined />,
                }}
            >
                <Form
                    form={form}
                    layout="vertical"
                >
                    <Form.Item
                        label="配置名称"
                    >
                        <Input value={editingConfig?.config_name} disabled />
                    </Form.Item>

                    <Form.Item
                        label="配置值"
                        name="config_value"
                        rules={[
                            { required: true, message: '请输入配置值' },
                        ]}
                    >
                        <TextArea
                            rows={6}
                            placeholder="请输入配置值（支持文本、Prompt等）"
                        />
                    </Form.Item>

                    <div className="bg-blue-50 p-3 rounded">
                        <Text type="secondary" className="text-xs">
                            提示：配置名称不可修改，只能编辑配置值。配置值可以是Prompt、系统参数等内容。
                        </Text>
                    </div>
                </Form>
            </Modal>
        </div>
    );
}
