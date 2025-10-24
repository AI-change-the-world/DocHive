import React, { useState, useEffect } from 'react';
import { Drawer, Table, Button, Form, Input, Select, Space, message, Popconfirm, Modal, InputNumber } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import type { DocumentTypeField } from '../../../types';
import { getFields, addField, updateField, deleteField, batchUpdateFields } from '../../../services/documentType';

const { TextArea } = Input;

interface FieldConfigDrawerProps {
    visible: boolean;
    docTypeId: number;
    onClose: () => void;
}

const FieldConfigDrawer: React.FC<FieldConfigDrawerProps> = ({ visible, docTypeId, onClose }) => {
    const [fields, setFields] = useState<DocumentTypeField[]>([]);
    const [loading, setLoading] = useState(false);
    const [modalVisible, setModalVisible] = useState(false);
    const [editingField, setEditingField] = useState<DocumentTypeField | null>(null);
    const [form] = Form.useForm();

    useEffect(() => {
        if (visible) {
            loadFields();
        }
    }, [visible, docTypeId]);

    const loadFields = async () => {
        setLoading(true);
        try {
            const response = await getFields(docTypeId);
            if (response.data.code === 200) {
                setFields(response.data.data || []);
            }
        } catch (error) {
            message.error('加载字段失败');
        } finally {
            setLoading(false);
        }
    };

    const handleAdd = () => {
        setEditingField(null);
        form.resetFields();
        form.setFieldsValue({
            field_type: 'text',
            is_required: false,
            display_order: fields.length,
        });
        setModalVisible(true);
    };

    const handleEdit = (record: DocumentTypeField) => {
        setEditingField(record);
        form.setFieldsValue(record);
        setModalVisible(true);
    };

    const handleDelete = async (id: number) => {
        try {
            await deleteField(id);
            message.success('删除成功');
            loadFields();
        } catch (error) {
            message.error('删除失败');
        }
    };

    const handleMoveUp = async (index: number) => {
        if (index === 0) return;
        const newFields = [...fields];
        [newFields[index - 1], newFields[index]] = [newFields[index], newFields[index - 1]];
        newFields.forEach((field, i) => {
            field.display_order = i;
        });
        await saveFieldsOrder(newFields);
    };

    const handleMoveDown = async (index: number) => {
        if (index === fields.length - 1) return;
        const newFields = [...fields];
        [newFields[index], newFields[index + 1]] = [newFields[index + 1], newFields[index]];
        newFields.forEach((field, i) => {
            field.display_order = i;
        });
        await saveFieldsOrder(newFields);
    };

    const saveFieldsOrder = async (newFields: DocumentTypeField[]) => {
        try {
            const fieldsData = newFields.map(f => ({
                field_name: f.field_name,
                field_code: f.field_code,
                field_type: f.field_type,
                extraction_prompt: f.extraction_prompt,
                is_required: f.is_required,
                display_order: f.display_order,
                placeholder_example: f.placeholder_example,
            }));
            await batchUpdateFields(docTypeId, fieldsData);
            setFields(newFields);
            message.success('顺序调整成功');
        } catch (error) {
            message.error('调整顺序失败');
        }
    };

    const handleSubmit = async () => {
        try {
            const values = await form.validateFields();

            if (editingField && editingField.id) {
                // 更新
                await updateField(editingField.id, values);
                message.success('更新成功');
            } else {
                // 创建
                await addField(docTypeId, values);
                message.success('添加成功');
            }

            setModalVisible(false);
            loadFields();
        } catch (error: any) {
            message.error(error.response?.data?.detail || '操作失败');
        }
    };

    const columns = [
        {
            title: '字段名称',
            dataIndex: 'field_name',
            width: 120,
        },
        {
            title: '字段编码',
            dataIndex: 'field_code',
            width: 120,
        },
        {
            title: '类型',
            dataIndex: 'field_type',
            width: 80,
            render: (type: string) => {
                const typeMap: Record<string, { text: string; color: string }> = {
                    text: { text: '文本', color: 'blue' },
                    number: { text: '数字', color: 'green' },
                    array: { text: '数组', color: 'orange' },
                    date: { text: '日期', color: 'purple' },
                    boolean: { text: '布尔', color: 'cyan' },
                };
                const info = typeMap[type] || { text: type, color: 'default' };
                return <span style={{ color: info.color }}>{info.text}</span>;
            },
        },
        // {
        //     title: 'AI提取Prompt',
        //     dataIndex: 'extraction_prompt',
        //     ellipsis: true,
        //     render: (text: string) => text || <span style={{ color: '#ccc' }}>未配置</span>,
        // },
        {
            title: '必填',
            dataIndex: 'is_required',
            width: 60,
            render: (required: boolean) => (required ? '是' : '否'),
        },
        {
            title: '操作',
            width: 200,
            render: (_: any, record: DocumentTypeField, index: number) => (
                <Space size="small">
                    <Button
                        size="small"
                        icon={<ArrowUpOutlined />}
                        onClick={() => handleMoveUp(index)}
                        disabled={index === 0}
                    />
                    <Button
                        size="small"
                        icon={<ArrowDownOutlined />}
                        onClick={() => handleMoveDown(index)}
                        disabled={index === fields.length - 1}
                    />
                    <Button
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => handleEdit(record)}
                    />
                    <Popconfirm
                        title="确定删除此字段吗？"
                        onConfirm={() => record.id && handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <>
            <Drawer
                title="字段配置"
                width={900}
                open={visible}
                onClose={onClose}
                extra={
                    <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
                        添加字段
                    </Button>
                }
            >
                <Table
                    columns={columns}
                    dataSource={fields}
                    rowKey="id"
                    loading={loading}
                    pagination={false}
                    size="small"
                />
            </Drawer>

            {/* 添加/编辑字段弹窗 */}
            <Modal
                title={editingField ? '编辑字段' : '添加字段'}
                open={modalVisible}
                onOk={handleSubmit}
                onCancel={() => setModalVisible(false)}
                width={700}
                okText="保存"
                cancelText="取消"
            >
                <Form form={form} layout="vertical">
                    <Form.Item
                        name="field_name"
                        label="字段名称"
                        rules={[{ required: true, message: '请输入字段名称' }]}
                    >
                        <Input placeholder="如：编制人、任务数量" />
                    </Form.Item>

                    <Form.Item
                        name="field_code"
                        label="字段编码"
                        rules={[
                            { required: true, message: '请输入字段编码' },
                            { pattern: /^[a-z_]+$/, message: '只能包含小写字母和下划线' }
                        ]}
                        extra="建议使用小写字母和下划线，如：author、task_count"
                    >
                        <Input placeholder="如：author" disabled={!!editingField} />
                    </Form.Item>

                    <Form.Item
                        name="field_type"
                        label="字段类型"
                        rules={[{ required: true, message: '请选择字段类型' }]}
                    >
                        <Select>
                            <Select.Option value="text">文本</Select.Option>
                            <Select.Option value="number">数字</Select.Option>
                            <Select.Option value="array">数组</Select.Option>
                            <Select.Option value="date">日期</Select.Option>
                            <Select.Option value="boolean">布尔值</Select.Option>
                        </Select>
                    </Form.Item>

                    {/* <Form.Item
                        name="extraction_prompt"
                        label="AI提取Prompt"
                        rules={[{ required: true, message: '请配置AI提取Prompt' }]}
                        extra="描述如何从文档中提取此字段的值"
                    >
                        <TextArea
                            rows={4}
                            placeholder="例：提取文档中的编制人姓名，通常在文档开头或结尾处"
                        />
                    </Form.Item> */}

                    <Form.Item
                        name="is_required"
                        label="是否必填"
                        valuePropName="checked"
                    >
                        <Select>
                            <Select.Option value={true}>是</Select.Option>
                            <Select.Option value={false}>否</Select.Option>
                        </Select>
                    </Form.Item>

                    <Form.Item
                        name="placeholder_example"
                        label="示例值"
                        extra="用于帮助用户理解此字段"
                    >
                        <Input placeholder="如：张三、2025-12-31" />
                    </Form.Item>

                    <Form.Item name="display_order" label="显示顺序" hidden>
                        <InputNumber />
                    </Form.Item>
                </Form>
            </Modal>
        </>
    );
};

export default FieldConfigDrawer;
