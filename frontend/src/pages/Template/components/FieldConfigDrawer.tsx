import React, { useState, useEffect } from 'react';
import { Modal, Table, Button, Input, Select, message } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import type { DocumentTypeField } from '../../../types';
import { getFields, deleteField, batchUpdateFields } from '../../../services/documentType';

interface FieldConfigDrawerProps {
    visible: boolean;
    docTypeId: number;
    docTypeName?: string;
    onClose: () => void;
}

const FieldConfigDrawer: React.FC<FieldConfigDrawerProps> = ({ visible, docTypeId, docTypeName, onClose }) => {
    const [fields, setFields] = useState<DocumentTypeField[]>([]);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (visible) {
            loadFields();
        }
    }, [visible, docTypeId]);

    const loadFields = async () => {
        setLoading(true);
        try {
            const response = await getFields(docTypeId);
            // request 已经返回 response.data，所以直接访问 response.code
            if (response.code === 200) {
                setFields(response.data || []);
            }
        } catch (error) {
            console.log("error : " + error);
            message.error('加载字段失败');
        } finally {
            setLoading(false);
        }
    };

    const handleAdd = () => {
        const newField: DocumentTypeField = {
            id: Date.now(), // 临时ID
            doc_type_id: docTypeId,
            field_name: '',
            field_type: 'text',
            description: '',
        };
        setFields([...fields, newField]);
    };

    const handleChange = (index: number, field: keyof DocumentTypeField, value: any) => {
        const newFields = [...fields];
        newFields[index] = { ...newFields[index], [field]: value };
        setFields(newFields);
    };

    const handleDelete = async (index: number) => {
        const field = fields[index];
        if (field.id && field.id < 1000000000000) { // 已保存的字段
            try {
                await deleteField(field.id);
                message.success('删除成功');
            } catch (error) {
                message.error('删除失败');
                return;
            }
        }
        const newFields = fields.filter((_, i) => i !== index);
        setFields(newFields);
    };


    const handleSave = async () => {
        // 验证必填项
        for (let i = 0; i < fields.length; i++) {
            const field = fields[i];
            if (!field.field_name) {
                message.error(`第 ${i + 1} 行：字段名称为必填项`);
                return;
            }
        }

        try {
            setLoading(true);
            const fieldsData = fields.map((f, i) => ({
                field_name: f.field_name,
                description: f.description,
                field_type: f.field_type,
            }));
            await batchUpdateFields(docTypeId, fieldsData);
            message.success('保存成功');
            // loadFields();
            setFields([]);
            onClose();
        } catch (error: any) {
            message.error(error.response?.data?.detail || '保存失败');
        } finally {
            setLoading(false);
        }
    };

    const columns = [
        {
            title: '字段名称',
            dataIndex: 'field_name',
            width: 150,
            render: (text: string, record: DocumentTypeField, index: number) => (
                <Input
                    placeholder="如：编制人"
                    value={text}
                    onChange={(e) => handleChange(index, 'field_name', e.target.value)}
                />
            ),
        },
        {
            title: '字段描述',
            dataIndex: 'description',
            width: 250,
            render: (text: string, record: DocumentTypeField, index: number) => (
                <Input
                    placeholder="描述此字段的用途，如：文档的编制人员"
                    value={text}
                    onChange={(e) => handleChange(index, 'description', e.target.value)}
                />
            ),
        },
        {
            title: '类型',
            dataIndex: 'field_type',
            width: 120,
            render: (text: string, record: DocumentTypeField, index: number) => (
                <Select
                    value={text}
                    onChange={(value) => handleChange(index, 'field_type', value)}
                    style={{ width: '100%' }}
                >
                    <Select.Option value="text">文本</Select.Option>
                    <Select.Option value="number">数字</Select.Option>
                    <Select.Option value="date">日期</Select.Option>
                    <Select.Option value="array">数组</Select.Option>
                </Select>
            ),
        },
    ];

    return (
        <Modal
            title={`字段配置 - ${docTypeName || ''}`}
            width={1200}
            open={visible}
            onCancel={onClose}
            maskClosable={false}
            footer={[
                <Button key="add" icon={<PlusOutlined />} onClick={handleAdd}>
                    添加字段
                </Button>,
                <Button key="save" type="primary" onClick={handleSave} loading={loading}>
                    保存
                </Button>,
                <Button key="close" onClick={onClose}>
                    关闭
                </Button>
            ]}
            styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
        >
            <Table
                columns={columns}
                dataSource={fields}
                rowKey={(record) => record.id?.toString() || ''}
                loading={loading}
                pagination={false}
                size="small"
            />
        </Modal>
    );
};

export default FieldConfigDrawer;