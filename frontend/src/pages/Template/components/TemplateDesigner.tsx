import React, { useState } from 'react';
import { Button, Input, Space, Card, Form, Table, Tag, Tooltip, Collapse, Select, Switch } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined, InfoCircleOutlined, CodeOutlined } from '@ant-design/icons';
import type { TemplateLevel } from '../../../types';

interface TemplateDesignerProps {
    value?: TemplateLevel[];
    onChange?: (value: TemplateLevel[]) => void;
}

const TemplateDesigner: React.FC<TemplateDesignerProps> = ({ value = [], onChange }) => {
    const handleAdd = () => {
        const newLevel: TemplateLevel = {
            level: (value?.length || 0) + 1,
            name: '',
            code: '',
            description: '',
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

    const handleChange = (index: number, field: keyof TemplateLevel, val: string) => {
        const newLevels = [...(value || [])];
        newLevels[index] = { ...newLevels[index], [field]: val };
        onChange?.(newLevels);
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
            width: 150,
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
            title: '描述',
            dataIndex: 'description',
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
                </Card>
            )}
        </div>
    );
};

export default TemplateDesigner;
