import React, { useState } from 'react';
import { Button, Input, Space, Card, Form, Table, Tag, Tooltip, Collapse, Modal } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, InfoCircleOutlined, CodeOutlined, ThunderboltOutlined, FileTextOutlined } from '@ant-design/icons';
import type { TemplateLevel } from '../../../types';

const { TextArea } = Input;
const { Panel } = Collapse;

interface TemplateDesignerProps {
    value?: TemplateLevel[];
    onChange?: (value: TemplateLevel[]) => void;
}

const TemplateDesigner: React.FC<TemplateDesignerProps> = ({ value = [], onChange }) => {
    const [promptModalVisible, setPromptModalVisible] = useState(false);
    const [currentEditingIndex, setCurrentEditingIndex] = useState<number>(-1);

    const handleAdd = () => {
        const newLevel: TemplateLevel = {
            level: (value?.length || 0) + 1,
            name: '',
            code: '',
            description: '',
            is_doc_type: false,
        };
        onChange?.([...(value || []), newLevel]);
    };

    const handleRemove = (index: number) => {
        const newLevels = value?.filter((_, i) => i !== index) || [];
        // 重新编号
        newLevels.forEach((level, i) => {
            level.level = i + 1;
        });
        onChange?.(newLevels);
    };

    const handleChange = (index: number, field: keyof TemplateLevel, val: any) => {
        const newLevels = [...(value || [])];

        // 如果设置 is_doc_type 为 true，先取消其他所有的 is_doc_type（单选）
        if (field === 'is_doc_type' && val === true) {
            newLevels.forEach((level, i) => {
                if (i !== index) {
                    level.is_doc_type = false;
                }
            });
        }

        newLevels[index] = { ...newLevels[index], [field]: val };
        onChange?.(newLevels);
    };

    const openPromptEditor = (index: number) => {
        setCurrentEditingIndex(index);
        setPromptModalVisible(true);
    };

    const savePromptConfig = (config: Partial<TemplateLevel>) => {
        if (currentEditingIndex >= 0) {
            const newLevels = [...(value || [])];
            newLevels[currentEditingIndex] = { ...newLevels[currentEditingIndex], ...config };
            onChange?.(newLevels);
        }
        setPromptModalVisible(false);
    };

    const handleMoveUp = (index: number) => {
        if (index === 0) return;
        const newLevels = [...(value || [])];
        [newLevels[index - 1], newLevels[index]] = [newLevels[index], newLevels[index - 1]];
        newLevels.forEach((level, i) => {
            level.level = i + 1;
        });
        onChange?.(newLevels);
    };

    const handleMoveDown = (index: number) => {
        if (index === (value?.length || 0) - 1) return;
        const newLevels = [...(value || [])];
        [newLevels[index], newLevels[index + 1]] = [newLevels[index + 1], newLevels[index]];
        newLevels.forEach((level, i) => {
            level.level = i + 1;
        });
        onChange?.(newLevels);
    };

    const columns = [
        {
            title: '层级',
            dataIndex: 'level',
            width: 60,
            render: (level: number) => <Tag color="blue">L{level}</Tag>,
        },
        {
            title: '名称',
            dataIndex: 'name',
            width: 120,
            render: (text: string, record: TemplateLevel, index: number) => (
                <Input
                    placeholder="如：年份、地域层级"
                    value={text}
                    onChange={(e) => handleChange(index, 'name', e.target.value)}
                    style={{ fontWeight: 500 }}
                />
            ),
        },
        {
            title: (
                <Space>
                    层级代码
                    <Tooltip title="用于编号生成，如：YEAR、REGION">
                        <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                </Space>
            ),
            dataIndex: 'code',
            width: 150,
            render: (text: string, record: TemplateLevel, index: number) => (
                <Input
                    placeholder="如：YEAR、REG"
                    value={text}
                    onChange={(e) => handleChange(index, 'code', e.target.value)}
                    prefix={<CodeOutlined />}
                />
            ),
        },
        {
            title: (
                <Space>
                    AI配置
                    <Tooltip title="配置Prompt和编码字典">
                        <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                </Space>
            ),
            width: 140,
            render: (_: any, record: TemplateLevel, index: number) => (
                <Space size="small">
                    <Tooltip title="配置AI提取Prompt">
                        <Button
                            size="small"
                            icon={<ThunderboltOutlined />}
                            onClick={() => openPromptEditor(index)}
                            type={record.extraction_prompt ? 'primary' : 'default'}
                        >
                            {record.extraction_prompt ? 'Prompt' : '配置'}
                        </Button>
                    </Tooltip>
                    <Tooltip title={record.is_doc_type ? '文档类型字段' : '设为文档类型'}>
                        <Button
                            size="small"
                            icon={<FileTextOutlined />}
                            type={record.is_doc_type ? 'primary' : 'default'}
                            onClick={() => handleChange(index, 'is_doc_type', !record.is_doc_type)}
                        >
                            TYPE
                        </Button>
                    </Tooltip>
                </Space>
            ),
        },
        {
            title: '描述',
            dataIndex: 'description',
            width: 150,
            render: (text: string, record: TemplateLevel, index: number) => (
                <Input
                    placeholder="说明该层级的用途"
                    value={text}
                    onChange={(e) => handleChange(index, 'description', e.target.value)}
                />
            ),
        },
        {
            title: '操作',
            width: 140,
            render: (_: any, record: TemplateLevel, index: number) => (
                <Space size="small">
                    <Tooltip title="上移">
                        <Button
                            size="small"
                            icon={<ArrowUpOutlined />}
                            onClick={() => handleMoveUp(index)}
                            disabled={index === 0}
                        />
                    </Tooltip>
                    <Tooltip title="下移">
                        <Button
                            size="small"
                            icon={<ArrowDownOutlined />}
                            onClick={() => handleMoveDown(index)}
                            disabled={index === (value?.length || 0) - 1}
                        />
                    </Tooltip>
                    <Tooltip title="删除">
                        <Button
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={() => handleRemove(index)}
                        />
                    </Tooltip>
                </Space>
            ),
        },
    ];

    return (
        <div style={{ background: '#fafafa', padding: '16px', borderRadius: '8px' }}>
            <Table
                columns={columns}
                dataSource={value}
                pagination={false}
                rowKey="level"
                size="small"
                bordered
                locale={{ emptyText: '暂无层级，请点击下方按钮添加' }}
                style={{ marginBottom: 16, background: '#fff' }}
                scroll={{ x: 900 }}
            />

            <Button
                type="dashed"
                onClick={handleAdd}
                block
                icon={<PlusOutlined />}
                style={{
                    height: 40,
                    borderStyle: 'dashed',
                    borderColor: '#1890ff',
                    color: '#1890ff'
                }}
            >
                添加层级
            </Button>

            {value && value.length > 0 && (
                <Card
                    size="small"
                    title="编号预览"
                    style={{ marginTop: 16 }}
                    headStyle={{ background: '#f0f5ff' }}
                >
                    <div style={{
                        fontFamily: 'monospace',
                        fontSize: 16,
                        color: '#52c41a',
                        padding: '8px 12px',
                        background: '#f6ffed',
                        border: '1px solid #b7eb8f',
                        borderRadius: 4
                    }}>
                        {value.map(level => level.code || 'XXX').join('-')}-0001
                    </div>
                    <div style={{ marginTop: 8, color: '#999', fontSize: 12 }}>
                        示例：{value.map(level => level.name || '未命名').join(' / ')}
                    </div>
                    {value.some(l => l.is_doc_type) && (
                        <div style={{ marginTop: 8, padding: 8, background: '#e6f7ff', borderRadius: 4 }}>
                            <Tag color="cyan" icon={<FileTextOutlined />}>
                                文档类型字段：{value.find(l => l.is_doc_type)?.name}
                            </Tag>
                        </div>
                    )}
                </Card>
            )}

            {/* Prompt 配置弹窗 */}
            <PromptConfigModal
                visible={promptModalVisible}
                level={value?.[currentEditingIndex]}
                onSave={savePromptConfig}
                onCancel={() => setPromptModalVisible(false)}
            />
        </div>
    );
};

// Prompt 配置弹窗组件
interface PromptConfigModalProps {
    visible: boolean;
    level?: TemplateLevel;
    onSave: (config: Partial<TemplateLevel>) => void;
    onCancel: () => void;
}

const PromptConfigModal: React.FC<PromptConfigModalProps> = ({ visible, level, onSave, onCancel }) => {
    const [form] = Form.useForm();

    React.useEffect(() => {
        if (visible && level) {
            form.setFieldsValue({
                extraction_prompt: level.extraction_prompt,
                placeholder_example: level.placeholder_example,
                business_keywords_prompt: level.business_keywords_prompt,
            });
        }
    }, [visible, level, form]);

    const handleSubmit = () => {
        form.validateFields().then(values => {
            const config: Partial<TemplateLevel> = {
                extraction_prompt: values.extraction_prompt,
                placeholder_example: values.placeholder_example,
                business_keywords_prompt: values.business_keywords_prompt,
            };
            onSave(config);
            form.resetFields();
        });
    };

    return (
        <Modal
            title={`配置层级提取规则 - ${level?.name || '未命名'}`}
            open={visible}
            onOk={handleSubmit}
            onCancel={onCancel}
            width={700}
            okText="保存"
            cancelText="取消"
        >
            <Form form={form} layout="vertical">
                <Form.Item
                    name="extraction_prompt"
                    label="AI提取Prompt"
                    extra="描述如何从文档中提取该字段，例：'提取文档的创建年份'、'识别文档所属地区'"
                    rules={[{ required: true, message: '请配置AI提取Prompt' }]}
                >
                    <TextArea
                        rows={6}
                        placeholder="例：请从文档中提取年份信息，如果文档中没有明确的年份，请根据上下文推断。返回4位数字的年份。"
                    />
                </Form.Item>



                <div style={{ marginBottom: 16, padding: '12px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 4 }}>
                    <InfoCircleOutlined style={{ color: '#faad14', marginRight: 8 }} />
                    <span style={{ fontSize: 12, color: '#666' }}>
                        <strong>提示：</strong>如果需要特定的编码规则，请在Prompt中明确说明。<br />
                        例："请提取部门信息，并转换为编码：开发部=DEV，市场部=MAR，产品部=PROD"
                    </span>
                </div>

                <Form.Item
                    name="placeholder_example"
                    label="示例值"
                    extra="用于帮助用户理解该字段的格式"
                >
                    <Input placeholder="例：2025、北京市、技术部" />
                </Form.Item>

                <Collapse ghost>
                    <Panel header="高级配置 - 业务属性检索" key="1">
                        <Form.Item
                            name="business_keywords_prompt"
                            label="业务关键词识别Prompt"
                            extra="描述如何通过业务语义识别该字段，用于智能检索匹配"
                        >
                            <TextArea
                                rows={4}
                                placeholder="例：当用户搜索'开发相关'、'技术文档'、'代码设计'等关键词时，应该匹配到'开发部'编码"
                            />
                        </Form.Item>
                        <div style={{ padding: '12px', background: '#f0f5ff', borderRadius: 4, fontSize: 12, color: '#666' }}>
                            <InfoCircleOutlined /> 提示：配置业务关键词识别Prompt后，用户搜索时系统能通过AI语义理解匹配到对应的编码
                        </div>
                    </Panel>
                </Collapse>
            </Form>
        </Modal >
    );
};

export default TemplateDesigner;
