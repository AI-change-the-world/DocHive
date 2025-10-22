import React, { useState } from 'react';
import { Button, Input, Space, Card, Form } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
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

    return (
        <div>
            <Space direction="vertical" style={{ width: '100%' }}>
                {value?.map((level, index) => (
                    <Card
                        key={index}
                        size="small"
                        title={`第 ${level.level} 级`}
                        extra={
                            <Space>
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
                                    disabled={index === (value?.length || 0) - 1}
                                />
                                <Button
                                    size="small"
                                    danger
                                    icon={<DeleteOutlined />}
                                    onClick={() => handleRemove(index)}
                                />
                            </Space>
                        }
                    >
                        <Space direction="vertical" style={{ width: '100%' }}>
                            <Input
                                placeholder="层级名称（必填）"
                                value={level.name}
                                onChange={(e) => handleChange(index, 'name', e.target.value)}
                            />
                            <Input
                                placeholder="层级代码（可选）"
                                value={level.code}
                                onChange={(e) => handleChange(index, 'code', e.target.value)}
                            />
                            <Input.TextArea
                                placeholder="层级描述（可选）"
                                value={level.description}
                                onChange={(e) => handleChange(index, 'description', e.target.value)}
                                rows={2}
                            />
                        </Space>
                    </Card>
                ))}

                <Button
                    type="dashed"
                    onClick={handleAdd}
                    block
                    icon={<PlusOutlined />}
                >
                    添加层级
                </Button>
            </Space>
        </div>
    );
};

export default TemplateDesigner;
