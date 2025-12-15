import { useState, useEffect } from "react";
import {
    Table,
    Card,
    Space,
    Button,
    Tag,
    message,
    Popconfirm,
    Typography,
    DatePicker,
    Select,
    Tooltip,
} from "antd";
import {
    ReloadOutlined,
    DeleteOutlined,
    EyeOutlined,
    DownloadOutlined,
    CheckCircleOutlined,
    CloseCircleOutlined,
    ClockCircleOutlined,
    SyncOutlined,
    FileTextOutlined,
    HistoryOutlined,
} from "@ant-design/icons";
import type {
    ExecutionRecord,
    ExecutionRecordListRequest,
    ExecutionRecordStatistics,
    ExecutionReportResponse,
} from "../../types";
import { executionRecordService } from "../../services/executionRecord";
import ExecutionReport from "../QABeta/ExecutionReport";
import dayjs from "dayjs";

const { RangePicker } = DatePicker;
const { Option } = Select;
const { Text } = Typography;

export default function ExecutionRecordsPage() {
    const [records, setRecords] = useState<ExecutionRecord[]>([]);
    const [loading, setLoading] = useState(false);
    const [pagination, setPagination] = useState({
        current: 1,
        pageSize: 10,
        total: 0,
    });

    // 筛选条件
    const [filters, setFilters] = useState<{
        status?: string;
        dateRange?: [string, string];
    }>({});

    // 统计信息（保留以备将来使用）
    const [_statistics, setStatistics] = useState<ExecutionRecordStatistics | null>(null);

    // 报告查看
    const [showReportModal, setShowReportModal] = useState(false);
    const [currentReport, setCurrentReport] = useState<ExecutionReportResponse | null>(null);

    // 加载执行记录列表
    const loadRecords = async (page = 1, pageSize = 10) => {
        setLoading(true);
        try {
            const params: ExecutionRecordListRequest = {
                page,
                page_size: pageSize,
                ...filters,
                ...(filters.dateRange && {
                    start_date: filters.dateRange[0],
                    end_date: filters.dateRange[1],
                }),
            };

            const response = await executionRecordService.getExecutionRecords(params);
            // response 已经是解析后的数据（拦截器返回 response.data）
            if (response) {
                setRecords(response.items || []);
                setPagination({
                    current: response.page,
                    pageSize: response.page_size,
                    total: response.total,
                });
            }
        } catch (error) {
            message.error("加载执行记录失败");
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    // 加载统计信息
    const loadStatistics = async () => {
        try {
            const response = await executionRecordService.getExecutionStatistics() as any;
            if (response) {
                // 后端返回的字段名和前端类型可能不一致，做个转换
                setStatistics({
                    total_records: response.total_executions || 0,
                    total_duration_seconds: 0,
                    avg_duration_seconds: response.avg_duration_seconds || 0,
                    by_status: response.by_status || {},
                    by_agent: {},
                    avg_success_rate: response.avg_success_rate || 0,
                });
            }
        } catch (error) {
            console.error("加载统计信息失败:", error);
        }
    };

    useEffect(() => {
        loadRecords();
        loadStatistics();
    }, [filters]);

    // 删除记录
    const handleDelete = async (recordId: number) => {
        try {
            await executionRecordService.deleteExecutionRecord(recordId);
            message.success("删除成功");
            loadRecords(pagination.current, pagination.pageSize);
            loadStatistics();
        } catch (error) {
            message.error("删除失败");
            console.error(error);
        }
    };

    // 查看报告
    const handleViewReport = async (record: ExecutionRecord) => {
        if (!record.report_data) {
            message.warning("该记录没有生成报告");
            return;
        }

        const reportResponse: ExecutionReportResponse = {
            report: record.report_data,
            html: record.html_report || "",
            markdown: record.markdown_report || "",
        };
        setCurrentReport(reportResponse);
        setShowReportModal(true);
    };

    // 下载报告
    const handleDownloadReport = async (record: ExecutionRecord, type: "html" | "markdown") => {
        try {
            let content = "";
            let filename = "";

            if (type === "html") {
                content = record.html_report || "";
                filename = `execution_report_${record.id}.html`;
            } else {
                content = record.markdown_report || "";
                filename = `execution_report_${record.id}.md`;
            }

            if (!content) {
                message.warning(`该记录没有${type.toUpperCase()}报告`);
                return;
            }

            const blob = new Blob([content], { type: "text/plain" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
            message.success("下载成功");
        } catch (error) {
            message.error("下载失败");
            console.error(error);
        }
    };

    // 状态标签渲染
    const renderStatusTag = (status: string) => {
        const statusConfig: Record<string, { color: string; icon: any; text: string }> = {
            running: { color: "processing", icon: <SyncOutlined spin />, text: "运行中" },
            completed: { color: "success", icon: <CheckCircleOutlined />, text: "已完成" },
            failed: { color: "error", icon: <CloseCircleOutlined />, text: "失败" },
            cancelled: { color: "default", icon: <ClockCircleOutlined />, text: "已取消" },
        };

        const config = statusConfig[status] || statusConfig.completed;
        return (
            <Tag color={config.color} icon={config.icon}>
                {config.text}
            </Tag>
        );
    };

    // 格式化时间
    const formatTime = (timestamp: number) => {
        return dayjs(timestamp * 1000).format("YYYY-MM-DD HH:mm:ss");
    };

    // 格式化时长
    const formatDuration = (seconds?: number) => {
        if (!seconds) return "-";
        if (seconds < 60) return `${seconds}秒`;
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        return `${minutes}分${remainingSeconds}秒`;
    };

    const columns = [
        {
            title: "ID",
            dataIndex: "id",
            key: "id",
            width: 80,
        },
        {
            title: "智能体",
            dataIndex: "agent_name",
            key: "agent_name",
            width: 150,
            render: (text: string) => <Text strong>{text}</Text>,
        },
        {
            title: "查询内容",
            dataIndex: "query",
            key: "query",
            ellipsis: true,
            render: (text: string) => (
                <Tooltip title={text}>
                    <Text>{text}</Text>
                </Tooltip>
            ),
        },
        {
            title: "执行模式",
            dataIndex: "execution_pattern",
            key: "execution_pattern",
            width: 100,
            render: (pattern?: string) => pattern || "-",
        },
        {
            title: "状态",
            dataIndex: "status",
            key: "status",
            width: 100,
            render: (status: string) => renderStatusTag(status),
        },
        {
            title: "成功率",
            key: "success_rate",
            width: 100,
            render: (_: any, record: ExecutionRecord) => (
                <Text type={record.success_rate >= 80 ? "success" : "danger"}>
                    {record.success_rate}%
                </Text>
            ),
        },
        {
            title: "步骤",
            key: "steps",
            width: 120,
            render: (_: any, record: ExecutionRecord) => (
                <Text>
                    {record.executed_steps}/{record.total_steps}
                </Text>
            ),
        },
        {
            title: "执行时长",
            dataIndex: "duration_seconds",
            key: "duration_seconds",
            width: 100,
            render: (duration?: number) => formatDuration(duration),
        },
        {
            title: "开始时间",
            dataIndex: "start_time",
            key: "start_time",
            width: 170,
            render: (timestamp: number) => formatTime(timestamp),
        },
        {
            title: "操作",
            key: "action",
            width: 180,
            fixed: "right" as const,
            render: (_: any, record: ExecutionRecord) => (
                <Space size="small">
                    <Tooltip title="查看报告">
                        <Button
                            type="link"
                            size="small"
                            icon={<EyeOutlined />}
                            onClick={() => handleViewReport(record)}
                            disabled={!record.report_data}
                        />
                    </Tooltip>
                    <Tooltip title="下载HTML">
                        <Button
                            type="link"
                            size="small"
                            icon={<DownloadOutlined />}
                            onClick={() => handleDownloadReport(record, "html")}
                            disabled={!record.html_report}
                        />
                    </Tooltip>
                    <Tooltip title="下载Markdown">
                        <Button
                            type="link"
                            size="small"
                            icon={<FileTextOutlined />}
                            onClick={() => handleDownloadReport(record, "markdown")}
                            disabled={!record.markdown_report}
                        />
                    </Tooltip>
                    <Popconfirm
                        title="确定删除此记录？"
                        onConfirm={() => handleDelete(record.id)}
                        okText="确定"
                        cancelText="取消"
                    >
                        <Tooltip title="删除">
                            <Button
                                type="link"
                                size="small"
                                danger
                                icon={<DeleteOutlined />}
                            />
                        </Tooltip>
                    </Popconfirm>
                </Space>
            ),
        },
    ];

    return (
        <div className="p-6">
            <Card>
                <div className="mb-4 flex justify-between items-center">
                    <h2 className="text-2xl font-bold flex items-center">
                        {/* <HistoryOutlined className="mr-3 text-primary-600" /> */}
                        执行记录管理
                    </h2>
                </div>

                {/* 筛选条件 */}
                <div className="mb-4">
                    <Space size="middle" wrap>
                        <Select
                            placeholder="选择状态"
                            style={{ width: 150 }}
                            allowClear
                            onChange={(value) => setFilters({ ...filters, status: value })}
                        >
                            <Option value="running">运行中</Option>
                            <Option value="completed">已完成</Option>
                            <Option value="failed">失败</Option>
                            <Option value="cancelled">已取消</Option>
                        </Select>

                        <RangePicker
                            showTime
                            onChange={(dates) => {
                                if (dates && dates[0] && dates[1]) {
                                    setFilters({
                                        ...filters,
                                        dateRange: [
                                            dates[0].toISOString(),
                                            dates[1].toISOString(),
                                        ],
                                    });
                                } else {
                                    const { dateRange, ...rest } = filters;
                                    setFilters(rest);
                                }
                            }}
                        />

                        <Button
                            icon={<ReloadOutlined />}
                            onClick={() => {
                                setFilters({});
                                loadRecords();
                                loadStatistics();
                            }}
                        >
                            重置
                        </Button>
                    </Space>
                </div>

                {/* 执行记录表格 */}
                <Table
                    columns={columns}
                    dataSource={records}
                    rowKey="id"
                    loading={loading}
                    scroll={{ x: 1500 }}
                    pagination={{
                        ...pagination,
                        showSizeChanger: true,
                        showQuickJumper: true,
                        showTotal: (total) => `共 ${total} 条记录`,
                        onChange: (page, pageSize) => {
                            loadRecords(page, pageSize);
                        },
                    }}
                />
            </Card>

            {/* 报告查看弹窗 */}
            <ExecutionReport
                visible={showReportModal}
                onClose={() => {
                    setShowReportModal(false);
                    setCurrentReport(null);
                }}
                reportData={currentReport}
            />
        </div>
    );
}
