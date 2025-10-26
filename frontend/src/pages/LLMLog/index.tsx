import { useState, useEffect } from 'react';
import { Table, Card, Statistic, Row, Col, Select, DatePicker, Button, Space, Tag, Modal, Typography, Descriptions, message } from 'antd';
import { ReloadOutlined, BarChartOutlined, EyeOutlined } from '@ant-design/icons';
import type { LLMLog, LLMLogListRequest, LLMLogStatistics } from '../../types';
import { llmLogService } from '../../services/llmLog';
import dayjs from 'dayjs';

const { RangePicker } = DatePicker;
const { Title, Text, Paragraph } = Typography;

export default function LLMLogPage() {
    const [logs, setLogs] = useState<LLMLog[]>([]);
    const [loading, setLoading] = useState(false);
    const [total, setTotal] = useState(0);
    const [statistics, setStatistics] = useState<LLMLogStatistics | null>(null);
    const [selectedLog, setSelectedLog] = useState<LLMLog | null>(null);
    const [detailVisible, setDetailVisible] = useState(false);

    const [filters, setFilters] = useState<LLMLogListRequest>({
        page: 1,
        page_size: 20,
    });

    // 加载日志列表
    const loadLogs = async () => {
        setLoading(true);
        try {
            const response = await llmLogService.getLogs(filters);
            setLogs(response.data.items);
            setTotal(response.data.total);
        } catch (error: any) {
            message.error(`加载日志失败: ${error.message}`);
        } finally {
            setLoading(false);
        }
    };

    // 加载统计信息
    const loadStatistics = async () => {
        try {
            const response = await llmLogService.getStatistics();
            setStatistics(response.data);
        } catch (error: any) {
            message.error(`加载统计信息失败: ${error.message}`);
        }
    };

    useEffect(() => {
        loadLogs();
        loadStatistics();
    }, [filters]);

    // 查看详情
    const handleViewDetail = async (record: LLMLog) => {
        setSelectedLog(record);
        setDetailVisible(true);
    };

    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 80,
        },
        {
            title: '提供商',
            dataIndex: 'provider',
            key: 'provider',
            width: 100,
            render: (text: string) => (
                <Tag color={text === 'openai' ? 'blue' : 'green'}>{text}</Tag>
            ),
        },
        {
            title: '模型',
            dataIndex: 'model',
            key: 'model',
            width: 150,
        },
        {
            title: 'Token使用',
            key: 'tokens',
            width: 150,
            render: (_: any, record: LLMLog) => (
                <div className="text-sm">
                    <div>输入: {record.prompt_tokens}</div>
                    <div>输出: {record.completion_tokens}</div>
                    <div className="font-medium">总计: {record.total_tokens}</div>
                </div>
            ),
        },
        {
            title: '耗时',
            dataIndex: 'duration_ms',
            key: 'duration_ms',
            width: 100,
            render: (ms: number) => ms ? `${ms}ms` : '-',
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            width: 100,
            render: (status: string) => (
                <Tag color={status === 'success' ? 'green' : 'red'}>
                    {status === 'success' ? '成功' : '失败'}
                </Tag>
            ),
        },
        {
            title: '时间',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 180,
            render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
        },
        {
            title: '操作',
            key: 'actions',
            width: 100,
            fixed: 'right' as const,
            render: (_: any, record: LLMLog) => (
                <Button
                    type="link"
                    icon={<EyeOutlined />}
                    onClick={() => handleViewDetail(record)}
                >
                    详情
                </Button>
            ),
        },
    ];

    return (
        <div className="h-full flex flex-col space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    <BarChartOutlined className="text-3xl text-primary-600" />
                    <Title level={2} className="!mb-0">LLM调用日志</Title>
                </div>
            </div>

            {/* 统计卡片 */}
            {statistics && (
                <Row gutter={16}>
                    <Col span={6}>
                        <Card>
                            <Statistic
                                title="总调用次数"
                                value={statistics.total_calls}
                                valueStyle={{ color: '#3f8600' }}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card>
                            <Statistic
                                title="总Token消耗"
                                value={statistics.total_tokens}
                                valueStyle={{ color: '#cf1322' }}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card>
                            <Statistic
                                title="成功率"
                                value={
                                    statistics.total_calls > 0
                                        ? ((statistics.by_status?.success || 0) / statistics.total_calls * 100).toFixed(2)
                                        : 0
                                }
                                suffix="%"
                                valueStyle={{ color: '#1890ff' }}
                            />
                        </Card>
                    </Col>
                    <Col span={6}>
                        <Card>
                            <Statistic
                                title="平均Token"
                                value={
                                    statistics.total_calls > 0
                                        ? Math.round(statistics.total_tokens / statistics.total_calls)
                                        : 0
                                }
                            />
                        </Card>
                    </Col>
                </Row>
            )}

            {/* 筛选条件 */}
            <Card>
                <Space wrap>
                    <Select
                        placeholder="选择提供商"
                        style={{ width: 150 }}
                        allowClear
                        onChange={(value) => setFilters({ ...filters, provider: value, page: 1 })}
                    >
                        <Select.Option value="openai">OpenAI</Select.Option>
                        <Select.Option value="deepseek">DeepSeek</Select.Option>
                    </Select>

                    <Select
                        placeholder="选择状态"
                        style={{ width: 120 }}
                        allowClear
                        onChange={(value) => setFilters({ ...filters, status: value, page: 1 })}
                    >
                        <Select.Option value="success">成功</Select.Option>
                        <Select.Option value="error">失败</Select.Option>
                    </Select>

                    <RangePicker
                        showTime
                        onChange={(dates) => {
                            if (dates) {
                                setFilters({
                                    ...filters,
                                    start_date: dates[0]?.toISOString(),
                                    end_date: dates[1]?.toISOString(),
                                    page: 1,
                                });
                            } else {
                                setFilters({ ...filters, start_date: undefined, end_date: undefined, page: 1 });
                            }
                        }}
                    />

                    <Button
                        icon={<ReloadOutlined />}
                        onClick={() => {
                            loadLogs();
                            loadStatistics();
                        }}
                    >
                        刷新
                    </Button>
                </Space>
            </Card>

            {/* 日志表格 */}
            <Card className="flex-1">
                <Table
                    columns={columns}
                    dataSource={logs}
                    loading={loading}
                    rowKey="id"
                    pagination={{
                        current: filters.page,
                        pageSize: filters.page_size,
                        total: total,
                        showSizeChanger: true,
                        showTotal: (total) => `共 ${total} 条`,
                        onChange: (page, pageSize) => {
                            setFilters({ ...filters, page, page_size: pageSize });
                        },
                    }}
                    scroll={{ y: 'calc(100vh - 550px)' }}
                />
            </Card>

            {/* 详情模态框 */}
            <Modal
                title="调用详情"
                open={detailVisible}
                onCancel={() => setDetailVisible(false)}
                footer={null}
                width={800}
            >
                {selectedLog && (
                    <div className="space-y-4">
                        <Descriptions bordered column={2}>
                            <Descriptions.Item label="ID">{selectedLog.id}</Descriptions.Item>
                            <Descriptions.Item label="提供商">
                                <Tag color={selectedLog.provider === 'openai' ? 'blue' : 'green'}>
                                    {selectedLog.provider}
                                </Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label="模型">{selectedLog.model}</Descriptions.Item>
                            <Descriptions.Item label="状态">
                                <Tag color={selectedLog.status === 'success' ? 'green' : 'red'}>
                                    {selectedLog.status === 'success' ? '成功' : '失败'}
                                </Tag>
                            </Descriptions.Item>
                            <Descriptions.Item label="输入Token">{selectedLog.prompt_tokens}</Descriptions.Item>
                            <Descriptions.Item label="输出Token">{selectedLog.completion_tokens}</Descriptions.Item>
                            <Descriptions.Item label="总Token">{selectedLog.total_tokens}</Descriptions.Item>
                            <Descriptions.Item label="耗时">
                                {selectedLog.duration_ms ? `${selectedLog.duration_ms}ms` : '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="时间" span={2}>
                                {dayjs(selectedLog.created_at).format('YYYY-MM-DD HH:mm:ss')}
                            </Descriptions.Item>
                        </Descriptions>

                        <div>
                            <Text strong>输入消息:</Text>
                            <Card className="mt-2 bg-gray-50" size="small">
                                <pre className="whitespace-pre-wrap text-sm max-h-60 overflow-auto">
                                    {JSON.stringify(selectedLog.input_messages, null, 2)}
                                </pre>
                            </Card>
                        </div>

                        {selectedLog.output_content && (
                            <div>
                                <Text strong>输出内容:</Text>
                                <Card className="mt-2 bg-gray-50" size="small">
                                    <Paragraph className="whitespace-pre-wrap text-sm max-h-60 overflow-auto !mb-0">
                                        {selectedLog.output_content}
                                    </Paragraph>
                                </Card>
                            </div>
                        )}

                        {selectedLog.error_message && (
                            <div>
                                <Text strong className="text-red-600">错误信息:</Text>
                                <Card className="mt-2 bg-red-50" size="small">
                                    <Text type="danger">{selectedLog.error_message}</Text>
                                </Card>
                            </div>
                        )}
                    </div>
                )}
            </Modal>
        </div>
    );
}
