import { useState, useEffect, useRef } from "react";
import {
    Modal,
    Button,
    Tabs,
    Card,
    Tag,
    Typography,
    Statistic,
    Row,
    Col,
    Space,
    Collapse,
    message,
    Tooltip,
    Divider,
} from "antd";
import {
    CheckCircleOutlined,
    CloseCircleOutlined,
    ClockCircleOutlined,
    DownloadOutlined,
    CodeOutlined,
    FileTextOutlined,
    Html5Outlined,
    BarChartOutlined,
    RobotOutlined,
    CopyOutlined,
    EyeOutlined,
} from "@ant-design/icons";
import type { ExecutionReportData, ExecutionReportResponse } from "../../types";
import ReactMarkdown from "react-markdown";
import mermaid from "mermaid";

const { Text, Title, Paragraph } = Typography;
const { Panel } = Collapse;

interface ExecutionReportProps {
    visible: boolean;
    onClose: () => void;
    reportData: ExecutionReportResponse | null;
}

// 初始化 Mermaid
mermaid.initialize({
    startOnLoad: false,
    theme: "default",
    securityLevel: "loose",
});

export default function ExecutionReport({
    visible,
    onClose,
    reportData,
}: ExecutionReportProps) {
    const [activeTab, setActiveTab] = useState("overview");
    const mermaidRef = useRef<HTMLDivElement>(null);
    const [mermaidSvg, setMermaidSvg] = useState<string>("");

    // 渲染 Mermaid 图
    useEffect(() => {
        if (visible && reportData?.report?.mermaid_diagram && mermaidRef.current) {
            const renderMermaid = async () => {
                try {
                    const { svg } = await mermaid.render(
                        "execution-flow-" + Date.now(),
                        reportData.report.mermaid_diagram
                    );
                    setMermaidSvg(svg);
                } catch (err) {
                    console.error("Mermaid render error:", err);
                    setMermaidSvg("");
                }
            };
            renderMermaid();
        }
    }, [visible, reportData?.report?.mermaid_diagram]);

    if (!reportData) return null;

    const { report, html, markdown } = reportData;

    // 下载 HTML 报告
    const handleDownloadHtml = () => {
        const blob = new Blob([html], { type: "text/html;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `执行报告_${report.agent_name}_${new Date()
            .toISOString()
            .slice(0, 10)}.html`;
        link.click();
        URL.revokeObjectURL(url);
        message.success("HTML 报告已下载");
    };

    // 下载 Markdown 报告
    const handleDownloadMarkdown = () => {
        const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `执行报告_${report.agent_name}_${new Date()
            .toISOString()
            .slice(0, 10)}.md`;
        link.click();
        URL.revokeObjectURL(url);
        message.success("Markdown 报告已下载");
    };

    // 复制到剪贴板
    const handleCopyMarkdown = () => {
        navigator.clipboard.writeText(markdown);
        message.success("已复制到剪贴板");
    };

    // 在新窗口打开 HTML 报告
    const handlePreviewHtml = () => {
        const newWindow = window.open("", "_blank");
        if (newWindow) {
            newWindow.document.write(html);
            newWindow.document.close();
        }
    };

    // 渲染步骤状态图标
    const renderStepStatusIcon = (status: string) => {
        switch (status) {
            case "success":
                return <CheckCircleOutlined className="text-green-500 text-lg" />;
            case "failed":
                return <CloseCircleOutlined className="text-red-500 text-lg" />;
            default:
                return <ClockCircleOutlined className="text-yellow-500 text-lg" />;
        }
    };

    // 渲染步骤状态标签
    const renderStepStatusTag = (status: string) => {
        switch (status) {
            case "success":
                return <Tag color="success">成功</Tag>;
            case "failed":
                return <Tag color="error">失败</Tag>;
            default:
                return <Tag color="warning">待执行</Tag>;
        }
    };

    // 概览标签页
    const renderOverviewTab = () => (
        <div className="space-y-6">
            {/* 基本信息 */}
            <Card size="small" className="bg-gradient-to-r from-purple-50 to-blue-50">
                <div className="flex items-center gap-3 mb-4">
                    <RobotOutlined className="text-2xl text-purple-500" />
                    <div>
                        <Title level={5} className="!mb-0">
                            {report.agent_name}
                        </Title>
                        <Text type="secondary" className="text-xs">
                            生成时间: {report.generated_at}
                        </Text>
                    </div>
                </div>
                <div className="bg-white/60 p-3 rounded-lg">
                    <Text strong className="text-sm text-gray-600">
                        查询内容:
                    </Text>
                    <Paragraph className="!mb-0 mt-1 text-sm">{report.query}</Paragraph>
                </div>
            </Card>

            {/* 统计卡片 */}
            <Row gutter={[16, 16]}>
                <Col xs={12} sm={6}>
                    <Card size="small" className="text-center">
                        <Statistic
                            title="计划步骤"
                            value={report.statistics.total_steps}
                            valueStyle={{ color: "#1890ff" }}
                        />
                    </Card>
                </Col>
                <Col xs={12} sm={6}>
                    <Card size="small" className="text-center">
                        <Statistic
                            title="已执行"
                            value={report.statistics.executed_steps}
                            valueStyle={{ color: "#722ed1" }}
                        />
                    </Card>
                </Col>
                <Col xs={12} sm={6}>
                    <Card size="small" className="text-center">
                        <Statistic
                            title="成功"
                            value={report.statistics.successful_steps}
                            valueStyle={{ color: "#52c41a" }}
                            prefix={<CheckCircleOutlined />}
                        />
                    </Card>
                </Col>
                <Col xs={12} sm={6}>
                    <Card size="small" className="text-center">
                        <Statistic
                            title="成功率"
                            value={report.statistics.success_rate}
                            suffix="%"
                            precision={1}
                            valueStyle={{
                                color:
                                    report.statistics.success_rate >= 80 ? "#52c41a" : "#faad14",
                            }}
                        />
                    </Card>
                </Col>
            </Row>

            {/* 执行流程图 */}
            {report.mermaid_diagram && (
                <Card
                    size="small"
                    title={
                        <span>
                            <BarChartOutlined className="mr-2" />
                            执行流程图
                        </span>
                    }
                >
                    <div
                        ref={mermaidRef}
                        className="flex justify-center p-4 bg-gray-50 rounded-lg overflow-auto"
                        dangerouslySetInnerHTML={{ __html: mermaidSvg }}
                    />
                </Card>
            )}
        </div>
    );

    // 步骤详情标签页
    const renderStepsTab = () => (
        <div className="space-y-4">
            <Collapse
                accordion
                defaultActiveKey={
                    report.steps.find((s) => s.status === "failed")?.step.toString() ||
                    "1"
                }
            >
                {report.steps.map((step) => (
                    <Panel
                        key={step.step.toString()}
                        header={
                            <div className="flex items-center justify-between w-full pr-4">
                                <div className="flex items-center gap-3">
                                    {renderStepStatusIcon(step.status)}
                                    <span className="font-medium">
                                        步骤 {step.step}: {step.name}
                                    </span>
                                    {step.llm_calls && step.llm_calls.length > 0 && (
                                        <Tag color="blue" className="ml-2">
                                            <RobotOutlined /> {step.llm_calls.length} 次LLM调用
                                        </Tag>
                                    )}
                                </div>
                                {renderStepStatusTag(step.status)}
                            </div>
                        }
                        className={`${step.status === "success"
                            ? "border-l-4 border-l-green-400"
                            : step.status === "failed"
                                ? "border-l-4 border-l-red-400"
                                : "border-l-4 border-l-yellow-400"
                            }`}
                    >
                        <div className="space-y-4">
                            <div>
                                <Text type="secondary" className="text-sm">
                                    描述:
                                </Text>
                                <div className="mt-1">{step.description}</div>
                            </div>

                            {step.expectations && (
                                <div>
                                    <Text type="secondary" className="text-sm">
                                        期望:
                                    </Text>
                                    <div className="mt-1 text-purple-600">{step.expectations}</div>
                                </div>
                            )}

                            {/* 工具参数 */}
                            {step.arguments && Object.keys(step.arguments).length > 0 && (
                                <div>
                                    <Text type="secondary" className="text-sm">
                                        🛠️ 工具参数:
                                    </Text>
                                    <pre className="mt-2 p-3 bg-blue-50 text-blue-900 rounded-lg overflow-auto text-xs max-h-40">
                                        {JSON.stringify(step.arguments, null, 2)}
                                    </pre>
                                </div>
                            )}

                            {/* LLM调用记录 */}
                            {step.llm_calls && step.llm_calls.length > 0 && (
                                <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-4 rounded-lg">
                                    <div className="flex items-center gap-2 mb-3">
                                        <RobotOutlined className="text-purple-500" />
                                        <Text strong>大模型调用详情</Text>
                                    </div>
                                    <Collapse size="small" className="bg-white">
                                        {step.llm_calls.map((llmCall, idx) => (
                                            <Panel
                                                key={idx}
                                                header={
                                                    <span className="text-sm">
                                                        <Tag color="purple">{llmCall.purpose}</Tag>
                                                        第 {idx + 1} 次调用
                                                    </span>
                                                }
                                            >
                                                <div className="space-y-3">
                                                    <div>
                                                        <Text type="secondary" className="text-xs">
                                                            📥 输入 (System Prompt):
                                                        </Text>
                                                        <pre className="mt-1 p-2 bg-gray-100 rounded text-xs max-h-32 overflow-auto whitespace-pre-wrap">
                                                            {llmCall.input.system_prompt_brief || llmCall.input.system_prompt || "无"}
                                                        </pre>
                                                    </div>
                                                    <div>
                                                        <Text type="secondary" className="text-xs">
                                                            📥 输入 (User Prompt):
                                                        </Text>
                                                        <pre className="mt-1 p-2 bg-gray-100 rounded text-xs max-h-24 overflow-auto whitespace-pre-wrap">
                                                            {llmCall.input.user_prompt}
                                                        </pre>
                                                    </div>
                                                    <Divider className="!my-2" />
                                                    <div>
                                                        <Text type="secondary" className="text-xs">
                                                            📤 输出:
                                                        </Text>
                                                        <pre className="mt-1 p-2 bg-green-50 text-green-900 rounded text-xs max-h-40 overflow-auto">
                                                            {JSON.stringify(llmCall.output, null, 2)}
                                                        </pre>
                                                    </div>
                                                </div>
                                            </Panel>
                                        ))}
                                    </Collapse>
                                </div>
                            )}

                            {step.error && (
                                <div className="bg-red-50 p-3 rounded-lg border border-red-200">
                                    <Text type="danger" strong>
                                        错误信息:
                                    </Text>
                                    <div className="mt-1 text-red-600">{step.error}</div>
                                </div>
                            )}

                            {Object.keys(step.result).length > 0 && (
                                <div>
                                    <Text type="secondary" className="text-sm">
                                        执行结果:
                                    </Text>
                                    <pre className="mt-2 p-3 bg-gray-900 text-gray-100 rounded-lg overflow-auto text-xs max-h-64">
                                        {JSON.stringify(step.result, null, 2)}
                                    </pre>
                                </div>
                            )}
                        </div>
                    </Panel>
                ))}
            </Collapse>
        </div>
    );

    // Markdown 预览标签页
    const renderMarkdownTab = () => (
        <div className="space-y-4">
            <div className="flex justify-end gap-2">
                <Button icon={<CopyOutlined />} onClick={handleCopyMarkdown}>
                    复制
                </Button>
                <Button icon={<DownloadOutlined />} onClick={handleDownloadMarkdown}>
                    下载 .md
                </Button>
            </div>
            <Card
                size="small"
                className="max-h-[60vh] overflow-auto bg-white"
                bodyStyle={{ padding: 16 }}
            >
                <div className="prose prose-sm max-w-none">
                    <ReactMarkdown>{markdown}</ReactMarkdown>
                </div>
            </Card>
        </div>
    );

    // HTML 预览标签页
    const renderHtmlTab = () => (
        <div className="space-y-4">
            <div className="flex justify-end gap-2">
                <Button icon={<EyeOutlined />} onClick={handlePreviewHtml}>
                    新窗口预览
                </Button>
                <Button
                    type="primary"
                    icon={<DownloadOutlined />}
                    onClick={handleDownloadHtml}
                >
                    下载 .html
                </Button>
            </div>
            <Card
                size="small"
                className="bg-gray-50"
                bodyStyle={{ padding: 0 }}
            >
                <iframe
                    srcDoc={html}
                    title="HTML Preview"
                    className="w-full h-[60vh] border-0 rounded-lg"
                    sandbox="allow-scripts"
                />
            </Card>
        </div>
    );

    const tabItems = [
        {
            key: "overview",
            label: (
                <span>
                    <BarChartOutlined />
                    概览
                </span>
            ),
            children: renderOverviewTab(),
        },
        {
            key: "steps",
            label: (
                <span>
                    <CodeOutlined />
                    步骤详情
                </span>
            ),
            children: renderStepsTab(),
        },
        {
            key: "markdown",
            label: (
                <span>
                    <FileTextOutlined />
                    Markdown
                </span>
            ),
            children: renderMarkdownTab(),
        },
        {
            key: "html",
            label: (
                <span>
                    <Html5Outlined />
                    HTML
                </span>
            ),
            children: renderHtmlTab(),
        },
    ];

    return (
        <Modal
            title={
                <div className="flex items-center gap-2">
                    <BarChartOutlined className="text-purple-500" />
                    <span>执行报告</span>
                    <Tag color="purple">{report.agent_name}</Tag>
                </div>
            }
            open={visible}
            onCancel={onClose}
            width={900}
            footer={
                <div className="flex justify-between">
                    <Space>
                        <Tooltip title="下载 HTML 格式的完整报告">
                            <Button icon={<Html5Outlined />} onClick={handleDownloadHtml}>
                                导出 HTML
                            </Button>
                        </Tooltip>
                        <Tooltip title="下载 Markdown 格式的报告">
                            <Button
                                icon={<FileTextOutlined />}
                                onClick={handleDownloadMarkdown}
                            >
                                导出 Markdown
                            </Button>
                        </Tooltip>
                    </Space>
                    <Button onClick={onClose}>关闭</Button>
                </div>
            }
        >
            <Tabs
                activeKey={activeTab}
                onChange={setActiveTab}
                items={tabItems}
                className="execution-report-tabs"
            />
        </Modal>
    );
}
