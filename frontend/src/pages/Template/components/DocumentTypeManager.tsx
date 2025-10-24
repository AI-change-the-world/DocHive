import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, Space, message, Popconfirm, Tag, Empty, Spin } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, SettingOutlined } from '@ant-design/icons';
import type { DocumentType, DocumentTypeField, ClassTemplate } from '../../../types';
import { getDocumentTypesByTemplate, createDocumentType, updateDocumentType, deleteDocumentType } from '../../../services/documentType';
import FieldConfigDrawer from './FieldConfigDrawer';

const { TextArea } = Input;

interface DocumentTypeManagerProps {
    template: ClassTemplate;
    onClose?: () => void;
}

/**
 * 文档类型管理组件
 * 作为模板的子功能，管理该模板下的所有文档类型配置
 */
const DocumentTypeManager: React.FC<DocumentTypeManagerProps> = ({ template, onClose }) => {
    const [documentTypes, setDocumentTypes] = useState<DocumentType[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingType, setEditingType] = useState<DocumentType | null>(null);
    const [fieldDrawerVisible, setFieldDrawerVisible] = useState(false);
    const [currentTypeId, setCurrentTypeId] = useState<number | null>(null);
    const [currentTypeName, setCurrentTypeName] = useState<string>('');
    const [form] = Form.useForm();

    useEffect(() => {
        loadDocumentTypes();
    }, [template.id]);

    const loadDocumentTypes = async () => {
        setLoading(true);
        try {
            const response = await getDocumentTypesByTemplate(template.id);
            console.log('API Response:', response);
            console.log('Response data:', response.data);

            // 处理响应数据：response.data 可能直接是数组，也可能是 {code, data} 结构
            let types: DocumentType[] = [];
            if (Array.isArray(response.data)) {
                // 直接是数组
                types = response.data;
            } else if (response.data.code === 200 && response.data.data) {
                // 标准响应结构
                types = response.data.data;
            } else if (response.data.data) {
                // 只有 data 字段
                types = response.data.data;
            }

            console.log('Setting document types:', types);
            setDocumentTypes(types);
        } catch (error) {
            console.error('Load error:', error);
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

    const handleConfigFields = (record: DocumentType) => {
        setCurrentTypeId(record.id);
        setCurrentTypeName(record.type_name);
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
                    template_id: template.id,
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

    // 检查模板是否有 is_doc_type 层级
    const hasDocTypeLevel = template.levels?.some(level => level.is_doc_type);

    console.log('Template:', template);
    console.log('Template levels:', template.levels);
    console.log('Has doc type level:', hasDocTypeLevel);
    console.log('Document types state:', documentTypes);

    if (!hasDocTypeLevel) {
        return (
            <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                    <div>
                        <p>该模板尚未配置文档类型层级</p>
                        <p style={{ fontSize: 12, color: '#999' }}>
                            请先在模板编辑中，将某个层级标记为"文档类型"（is_doc_type）
                        </p>
                    </div>
                }
            />
        );
    }

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
                    {fields?.length || 0} 个
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
                        onClick={() => handleConfigFields(record)}
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
        <Spin spinning={loading}>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h3 style={{ margin: 0 }}>文档类型配置</h3>
                    <p style={{ margin: '4px 0 0 0', color: '#999', fontSize: 12 }}>
                        为模板「{template.name}」配置不同类型文档的字段提取规则
                    </p>
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                    新建类型
                </Button>
            </div>

            <Table
                columns={columns}
                dataSource={documentTypes}
                rowKey="id"
                pagination={false}
                size="small"
                locale={{ emptyText: '暂无文档类型，请点击"新建类型"添加' }}
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

            {/* 字段配置弹窗 */}
            {currentTypeId && (
                <FieldConfigDrawer
                    visible={fieldDrawerVisible}
                    docTypeId={currentTypeId}
                    docTypeName={currentTypeName}
                    onClose={() => {
                        setFieldDrawerVisible(false);
                        loadDocumentTypes(); // 刷新数据以更新字段数量
                    }}
                />
            )}
        </Spin>
    );
};

export default DocumentTypeManager;
