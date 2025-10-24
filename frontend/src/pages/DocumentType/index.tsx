import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Space, message, Popconfirm, Tag, Drawer } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DocumentType, DocumentTypeField } from '../../types';
import { getDocumentTypesByTemplate, createDocumentType, updateDocumentType, deleteDocumentType } from '../../services/documentType';
import FieldConfigDrawer from './components/FieldConfigDrawer';

const { TextArea } = Input;

interface DocumentTypeManagerProps {
    templateId: number;
    templateName?: string;
}

const DocumentTypeManager: React.FC<DocumentTypeManagerProps> = ({ templateId, templateName }) => {
    const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingType, setEditingType] = useState<DocumentType | null>(null);
    const [fieldDrawerVisible, setFieldDrawerVisible] = useState(false);
    const [currentTypeId, setCurrentTypeId] = useState<number | null>(null);
    const [form] = Form.useForm();

    useEffect(() => {
        loadDocumentTypes();
    }, [templateId]);

    const loadDocumentTypes = async () => {
        setLoading(true);
        try {
            const response = await getDocumentTypesByTemplate(templateId);
            if (response.data.code === 200) {
                setDocumentTypes(response.data.data || []);
            }
        } catch (error) {
            message.error('加载文档类型失败');
        } finally {
            setLoading(false);
        }
    };

    const handleCreate = () => {
        setEditingType(null);
        form.resetFields();
        setModalVisible(true);
    };

    const handleEdit = (record: DocumentType) => {
        setEditingType(record);
        form.setFieldsValue({
            type_code: record.type_code,
            type_name: record.type_name,
            description: record.description,
            extraction_prompt: record.extraction_prompt,
        });
        setModalVisible(true);
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteDocumentType(id);
            message.success('删除成功');
            loadDocumentTypes();
        } catch (error) {
            message.error('删除失败');
        }
    };

    const handleConfigFields = (typeId: number) => {
        setCurrentTypeId(typeId);
        setFieldDrawerVisible(true);
    };

    const handleSubmit = async () => {
        try {
            const values = await form.validateFields();

            if (editingType) {
                // 更新
                await updateDocumentType(editingType.id, values);
                message.success('更新成功');
            } else {
                // 创建
                await createDocumentType({
                    template_id: templateId,
                    ...values,
                });
                message.success('创建成功');
            }

            setModalVisible(false);
            loadDocumentTypes();
        } catch (error: any) {
            message.error(error.response?.data?.detail || '操作失败');
        }
    };

    const columns = [
        {
            title: '类型编码',
            dataIndex: 'type_code',
            width: 150,
            render: (text: string) => <Tag color="blue">{text}</Tag>,
        },
        {
            title: '类型名称',
            dataIndex: 'type_name',
            width: 150,
        },
        {
            title: '描述',
            dataIndex: 'description',
            ellipsis: true,
        },
        {
            title: '字段数量',
            dataIndex: 'fields',
            width: 100,
            render: (fields?: DocumentTypeField[]) => (
                <Tag color={fields && fields.length > 0 ? 'green' : 'default'}>
                    {fields?.length || 0} 个字段
                </Tag>
            ),
        },
        {
            title: '状态',
            dataIndex: 'is_active',
            width: 80,
            render: (active: boolean) => (
                <Tag color={active ? 'success' : 'default'}>
                    {active ? '启用' : '停用'}
                </Tag>
            ),
        },
        {
            title: '操作',
            width: 240,
            render: (_: any, record: DocumentType) => (
                <Space size="small">
                    <Button
                        size="small"
                        icon={<SettingOutlined />}
                        onClick={() => handleConfigFields(record.id)}
                    >
                        配置字段
                    </Button>
                    <Button
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(record)}
                    >
                        编辑
                    </Button>
                    <Popconfirm
                        title="确定删除此文档类型吗？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Button size="small" danger icon={<DeleteOutlined />}>
                            删除
                        </Button>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div style={{ padding: '24px' }}>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h2 style={{ margin: 0 }}>文档类型管理</h2>
                    {templateName && <span style={{ color: '#999', fontSize: 14 }}>模板：{templateName}</span>}
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                    新建文档类型
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={documentTypes}
                rowKey="id"
                loading={loading}
                pagination={{ pageSize: 10 }}
            />

            {/* 创建/编辑弹窗 */}
            <Modal
                title={editingType ? '编辑文档类型' : '新建文档类型'}
                open={modalVisible}
                onOk={handleSubmit}
                onCancel={() => setModalVisible(false)}
                width={700}
                okText="保存"
                cancelText="取消"
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="type_code"
                        label="类型编码"
                        rules={[
                            { required: true, message: '请输入类型编码' },
                            { pattern: /^[A-Z_]+$/, message: '只能包含大写字母和下划线' }
                        ]}
                        extra="建议使用大写字母和下划线，如：DEV_DOC"
                    >
                        <Input placeholder="如：DEV_DOC" disabled={!!editingType} />
                    </Form.Item>

                    <Form.Item
                        name="type_name"
                        label="类型名称"
                        rules={[{ required: true, message: '请输入类型名称' }]}
                    >
                        <Input placeholder="如：开发文档" />
                    </Form.Item>

                    <Form.Item name="description" label="描述">
                        <TextArea rows={3} placeholder="描述此文档类型的用途" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* 字段配置抽屉 */}
            {currentTypeId && (
                <FieldConfigDrawer
                    visible={fieldDrawerVisible}
                    docTypeId={currentTypeId}
                    onClose={() => {
                        setFieldDrawerVisible(false);
                        loadDocumentTypes(); // 刷新数据以更新字段数量
                    }}
                />
            )}
        </div>
    );
};

export default DocumentTypeManager;
