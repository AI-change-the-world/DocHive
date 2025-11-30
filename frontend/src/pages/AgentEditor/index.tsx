import { useState, useEffect } from "react";
import {
  Card,
  Button,
  message,
  Space,
  Divider,
  Empty,
  Input,
  Select,
  Spin,
  Row,
  Col,
  Alert,
  Tag,
  Typography,
  Table,
  Modal,
  Drawer,
  Collapse,
} from "antd";
import {
  SaveOutlined,
  EyeOutlined,
  CheckCircleOutlined,
  RobotOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import mermaid from "mermaid";
import ReactMarkdown from "react-markdown";
import { agentEditorService } from "../../services/agentEditor";
import { templateService } from "../../services/template";
import { v4 as uuidv4 } from "uuid";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface ParseResult {
  success: boolean;
  agent?: {
    name: string;
    description: string;
    execution_pattern: string;
    steps: Array<{
      step: number;
      type: string;
      name: string;
      description: string;
      parameters?: Record<string, any>;
      condition?: string;
    }>;
  };
  errors?: string[];
  warnings?: string[];
  mermaid_diagram?: string;
}

export default function AgentEditorPage() {
  // 列表相关
  const [agents, setAgents] = useState<any[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<any>(null);

  // 创建相关
  const [createDrawerVisible, setCreateDrawerVisible] = useState(false);
  const [markdown, setMarkdown] = useState("");
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<any[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // 执行相关
  const [executeModalVisible, setExecuteModalVisible] = useState(false);
  const [executeQuery, setExecuteQuery] = useState("");
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [expandedSteps, setExpandedSteps] = useState<Set<number>>(new Set());

  const [viewAgentDetailVisible, setViewAgentDetailVisible] = useState(false);

  // Mermaid初始化
  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: "default",
      securityLevel: "loose",
      flowchart: {
        useMaxWidth: true,
        htmlLabels: true,
      },
    });
  }, []);

  // 加载Agent列表和分类模板
  useEffect(() => {
    loadAgents();
    loadTemplates();
  }, []);

  // 加载Agent列表
  const loadAgents = async () => {
    try {
      setLoadingAgents(true);
      const response = await agentEditorService.listAgents({
        is_active: true,
      });
      if (response.data?.agents) {
        setAgents(response.data.agents);
      }
    } catch (error) {
      message.error("加载Agent列表失败");
      console.error(error);
    } finally {
      setLoadingAgents(false);
    }
  };

  const loadTemplates = async () => {
    try {
      setLoadingTemplates(true);
      const response = await templateService.getTemplates({
        page: 1,
        page_size: 100,
      });
      if (response.data?.items) {
        setTemplates(response.data.items);
      }
    } catch (error) {
      console.error("加载模板列表失败:", error);
    } finally {
      setLoadingTemplates(false);
    }
  };

  // 渲染Mermaid图
  useEffect(() => {
    if (parseResult?.mermaid_diagram) {
      const renderMermaid = async () => {
        try {
          const element = document.getElementById("mermaid-diagram");
          if (element && parseResult.mermaid_diagram) {
            element.innerHTML = parseResult.mermaid_diagram;
            await mermaid.run({
              nodes: [element],
            });
          }
        } catch (error) {
          console.error("Mermaid渲染失败:", error);
        }
      };
      renderMermaid();
    }
  }, [parseResult?.mermaid_diagram]);

  // 渲染Agent详情中的Mermaid图
  useEffect(() => {
    if (selectedAgent?.mermaid_diagram && viewAgentDetailVisible) {
      const renderMermaid = async () => {
        try {
          const element = document.getElementById("agent-detail-mermaid");
          if (element && selectedAgent.mermaid_diagram) {
            element.innerHTML = selectedAgent.mermaid_diagram;
            await mermaid.run({
              nodes: [element],
            });
          }
        } catch (error) {
          console.error("Mermaid渲染失败:", error);
        }
      };
      renderMermaid();
    }
  }, [selectedAgent?.mermaid_diagram, viewAgentDetailVisible]);

  // 解析Markdown - 使用LLM验证
  const handleParse = async () => {
    if (!markdown.trim()) {
      message.warning("请先输入Agent定义");
      return;
    }

    try {
      if (!templateId) {
        message.warning("请选择模板");
        return;
      }

      setLoading(true);
      const response = await agentEditorService.parseMarkdown({
        content: markdown,
        template_id: templateId,
      });

      setParseResult(response.data);

      if (response.data?.success) {
        message.success("解析成功，流程验证通过");
      } else {
        message.error("解析失败或流程验证未通过");
      }
    } catch (error) {
      message.error("解析失败，请检查Markdown格式");
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 创建Agent
  const handleCreateAgent = async () => {
    if (!parseResult?.success || !parseResult.agent) {
      message.warning("请先解析Agent定义并确保验证通过");
      return;
    }

    try {
      setLoading(true);
      await agentEditorService.createAgent({
        name: parseResult.agent.name,
        description: parseResult.agent.description,
        template_id: templateId,
        markdown_content: markdown,
      });
      message.success("Agent创建成功");
      setMarkdown("");
      setParseResult(null);
      setCreateDrawerVisible(false);
      loadAgents(); // 刷新列表
    } catch (error) {
      message.error("创建失败");
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  // 执行Agent
  const handleExecuteAgent = async () => {
    if (!selectedAgent || !executeQuery.trim()) {
      message.warning("请输入查询内容");
      return;
    }

    try {
      setExecuting(true);
      setExecutionResult({ stages: [], answer: null });

      await agentEditorService.executeAgent(
        selectedAgent.id,
        {
          query: executeQuery,
          template_id: selectedAgent.template_id,
          session_id: uuidv4(),
        },
        (event) => {
          console.log("收到事件:", event);

          switch (event.event) {
            case "execution_plan":
              setExecutionResult((prev: any) => ({
                ...prev,
                plan: event.data,
                steps: event.data.plan || [],
              }));
              break;
            case "stage_start":
              // 更新步骤状态为运行中
              setExecutionResult((prev: any) => {
                const steps = prev.steps || [];
                const stepIndex = steps.findIndex(
                  (s: any) => s.step === event.data.step
                );
                if (stepIndex >= 0) {
                  steps[stepIndex] = {
                    ...steps[stepIndex],
                    ...event.data,
                    status: "running",
                  };
                } else {
                  steps.push({ ...event.data, status: "running" });
                }
                return { ...prev, steps: [...steps] };
              });
              break;
            case "stage_complete":
              // 更新步骤状态为完成
              setExecutionResult((prev: any) => {
                const steps = prev.steps || [];
                const stepIndex = steps.findIndex(
                  (s: any) => s.step === event.data.step
                );
                if (stepIndex >= 0) {
                  steps[stepIndex] = {
                    ...steps[stepIndex],
                    ...event.data,
                    status: "completed",
                  };
                } else {
                  steps.push({ ...event.data, status: "completed" });
                }
                return { ...prev, steps: [...steps] };
              });
              break;
            case "stage_error":
              // 更新步骤状态为错误
              setExecutionResult((prev: any) => {
                const steps = prev.steps || [];
                const stepIndex = steps.findIndex(
                  (s: any) => s.step === event.data.step
                );
                if (stepIndex >= 0) {
                  steps[stepIndex] = {
                    ...steps[stepIndex],
                    ...event.data,
                    status: "error",
                  };
                } else {
                  steps.push({ ...event.data, status: "error" });
                }
                return { ...prev, steps: [...steps] };
              });
              break;
            case "answer":
              setExecutionResult((prev: any) => ({
                ...prev,
                answer: event.data.answer,
                documents: event.data.documents,
                document: event.data.document, // 生成的文档
              }));
              break;
            case "done":
              setExecuting(false);
              message.success("执行完成");
              break;
            case "error":
              setExecuting(false);
              message.error(event.data.error || "执行失败");
              break;
          }
        }
      );
    } catch (error: any) {
      setExecuting(false);
      message.error(`执行失败: ${error.message}`);
      console.error(error);
    }
  };

  // 打开创建抽屉
  const handleOpenCreateDrawer = () => {
    setMarkdown("");
    setParseResult(null);
    setCreateDrawerVisible(true);
  };
  const viewAgentDetail = (agent: any | null) => {
    if (viewAgentDetailVisible) {
      setViewAgentDetailVisible(false);
      setSelectedAgent(null);
    } else {
      setSelectedAgent(agent);
      setViewAgentDetailVisible(true);
    }
  };

  // 打开执行弹窗
  const handleOpenExecuteModal = (agent: any) => {
    setSelectedAgent(agent);
    setExecuteQuery("");
    setExecutionResult(null);
    setExpandedSteps(new Set());
    setExecuteModalVisible(true);
  };

  // 切换步骤展开/收起
  const toggleStep = (stepNum: number) => {
    setExpandedSteps((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(stepNum)) {
        newSet.delete(stepNum);
      } else {
        newSet.add(stepNum);
      }
      return newSet;
    });
  };

  // 获取步骤状态图标和颜色
  const getStepStatus = (step: any) => {
    if (step.status === "completed") {
      return {
        icon: <CheckCircleOutlined />,
        color: "#52c41a",
        text: "已完成",
      };
    } else if (step.status === "error") {
      return { icon: <CloseCircleOutlined />, color: "#ff4d4f", text: "失败" };
    } else if (step.status === "running") {
      return {
        icon: <ClockCircleOutlined />,
        color: "#1890ff",
        text: "执行中",
      };
    } else {
      return {
        icon: <ClockCircleOutlined />,
        color: "#d9d9d9",
        text: "等待中",
      };
    }
  };

  const renderErrors = () => {
    if (!parseResult?.errors || parseResult.errors.length === 0) {
      return null;
    }

    return (
      <Alert
        message="错误"
        description={
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {parseResult.errors.map((error, i) => (
              <li key={i}>{error}</li>
            ))}
          </ul>
        }
        type="error"
        showIcon
        style={{ marginBottom: 16 }}
      />
    );
  };

  const renderWarnings = () => {
    if (!parseResult?.warnings || parseResult.warnings.length === 0) {
      return null;
    }

    return (
      <Alert
        message="警告"
        description={
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {parseResult.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        }
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
      />
    );
  };

  const renderRightPanel = () => {
    if (loading) {
      return (
        <div style={{ textAlign: "center", padding: 100 }}>
          <Spin size="large" tip="LLM正在解析验证..." />
        </div>
      );
    }

    if (!parseResult) {
      return (
        <Empty
          description="请在左侧编辑Agent定义，然后点击【解析】查看流程图"
          style={{ marginTop: 100 }}
        />
      );
    }

    return (
      <div>
        {renderErrors()}
        {renderWarnings()}

        {parseResult.success && parseResult.agent && (
          <Card style={{ marginBottom: 16 }}>
            <Row gutter={[16, 16]}>
              <Col span={24}>
                <Title level={4}>
                  <CheckCircleOutlined
                    style={{ color: "#52c41a", marginRight: 8 }}
                  />
                  Agent信息
                </Title>
              </Col>
              <Col span={24}>
                <div>
                  <Text strong>名称:</Text> {parseResult.agent.name}
                </div>
              </Col>
              <Col span={24}>
                <div>
                  <Text strong>描述:</Text> {parseResult.agent.description}
                </div>
              </Col>
              <Col span={24}>
                <div>
                  <Text strong>执行模式:</Text>
                  <Tag color="blue" style={{ marginLeft: 8 }}>
                    {parseResult.agent.execution_pattern}
                  </Tag>
                </div>
              </Col>
              <Col span={24}>
                <div>
                  <Text strong>步骤数量:</Text> {parseResult.agent.steps.length}
                </div>
              </Col>
            </Row>
          </Card>
        )}

        {parseResult.mermaid_diagram && (
          <Card title="流程图">
            <div
              id="mermaid-diagram"
              style={{
                display: "flex",
                justifyContent: "center",
                alignItems: "center",
                minHeight: 300,
                overflow: "auto",
              }}
            >
              {parseResult.mermaid_diagram}
            </div>
          </Card>
        )}
      </div>
    );
  };

  // Agent列表列配置
  const columns = [
    {
      title: "名称",
      dataIndex: "name",
      key: "name",
      render: (text: string) => (
        <Space>
          <RobotOutlined />
          <Text strong>{text}</Text>
        </Space>
      ),
    },
    {
      title: "描述",
      dataIndex: "description",
      key: "description",
      ellipsis: true,
    },
    {
      title: "执行模式",
      dataIndex: "execution_pattern",
      key: "execution_pattern",
      render: (pattern: string) => <Tag color="blue">{pattern}</Tag>,
    },
    {
      title: "步骤数",
      dataIndex: "steps",
      key: "steps",
      render: (steps: any[]) => steps?.length || 0,
    },
    {
      title: "创建时间",
      dataIndex: "created_at",
      key: "created_at",
      render: (time: string) => time.replace("T", " "),
    },
    {
      title: "操作",
      key: "action",
      render: (_: any, record: any) => (
        <Space>
          <Button
            type="default"
            icon={<EyeOutlined />}
            onClick={() => viewAgentDetail(record)}
          >
            查看
          </Button>
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            onClick={() => handleOpenExecuteModal(record)}
          >
            执行
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24, height: "100%" }}>
      {/* 页面标题 */}
      <Card style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Col>
            <Title level={2}>
              <RobotOutlined /> 自定义Agent管理
            </Title>
            <Paragraph>管理和执行自定义的智能体工作流</Paragraph>
          </Col>
          <Col>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              size="large"
              onClick={handleOpenCreateDrawer}
            >
              创建Agent
            </Button>
          </Col>
        </Row>
      </Card>

      {/* Agent列表 */}
      <Card>
        <Table
          columns={columns}
          dataSource={agents}
          rowKey="id"
          loading={loadingAgents}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `共 ${total} 个Agent`,
          }}
        />
      </Card>

      {/* 创建Agent抽屉 */}
      <Drawer
        title="创建新Agent"
        placement="right"
        width="80%"
        onClose={() => setCreateDrawerVisible(false)}
        open={createDrawerVisible}
      >
        <Row gutter={16} style={{ height: "100%" }}>
          {/* 左侧 - Markdown编辑器 */}
          <Col span={12} style={{ height: "100%" }}>
            <Card
              title="Markdown编辑"
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
              }}
              bodyStyle={{
                flex: 1,
                overflow: "hidden",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div style={{ marginBottom: 16 }}>
                <Text strong>关联分类模板:</Text>
                <Select
                  placeholder="选择关联的分类模板"
                  style={{ width: "100%", marginTop: 8 }}
                  value={templateId}
                  onChange={setTemplateId}
                  loading={loadingTemplates}
                  options={templates.map((t) => ({
                    label: t.name,
                    value: t.id,
                  }))}
                />
              </div>

              <div
                style={{
                  flex: 1,
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <Text strong style={{ marginBottom: 8 }}>
                  Agent定义:
                </Text>
                <TextArea
                  value={markdown}
                  onChange={(e) => setMarkdown(e.target.value)}
                  placeholder="输入Agent的Markdown定义..."
                  style={{
                    flex: 1,
                    fontFamily: "monospace",
                    fontSize: 13,
                    resize: "none",
                  }}
                />
              </div>

              <Divider />

              <div>
                <Space>
                  <Button
                    type="primary"
                    icon={<EyeOutlined />}
                    onClick={handleParse}
                    loading={loading}
                  >
                    解析
                  </Button>
                  <Button
                    icon={<SaveOutlined />}
                    onClick={handleCreateAgent}
                    disabled={!parseResult?.success}
                    loading={loading}
                  >
                    创建
                  </Button>
                </Space>
              </div>
            </Card>
          </Col>

          {/* 右侧 - 流程图和验证结果 */}
          <Col span={12} style={{ height: "100%" }}>
            <Card
              title="流程预览"
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
              }}
              bodyStyle={{ flex: 1, overflow: "auto" }}
            >
              {renderRightPanel()}
            </Card>
          </Col>
        </Row>
      </Drawer>

      {/* 查看Agent详情弹窗 */}
      <Drawer
        title="Agent详情"
        placement="right"
        width="80%"
        onClose={() => viewAgentDetail(null)}
        open={viewAgentDetailVisible}
      >
        {selectedAgent && (
          <Row gutter={16} style={{ height: "100%" }}>
            {/* 左侧 - Markdown定义 */}
            <Col span={12} style={{ height: "100%" }}>
              <Card
                title="Markdown定义"
                style={{
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                }}
                bodyStyle={{ flex: 1, overflow: "auto" }}
              >
                <div
                  style={{
                    padding: 16,
                    background: "#fafafa",
                    borderRadius: 4,
                    height: "100%",
                    overflow: "auto",
                  }}
                >
                  <ReactMarkdown>{selectedAgent.markdown_content || "暂无内容"}</ReactMarkdown>
                </div>
              </Card>
            </Col>

            {/* 右侧 - Mermaid流程图 */}
            <Col span={12} style={{ height: "100%" }}>
              <Card
                title="流程图"
                style={{
                  height: "100%",
                  display: "flex",
                  flexDirection: "column",
                }}
                bodyStyle={{ flex: 1, overflow: "auto" }}
              >
                {selectedAgent.mermaid_diagram ? (
                  <div
                    id="agent-detail-mermaid"
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      alignItems: "center",
                      minHeight: 300,
                      overflow: "auto",
                    }}
                  >
                    {selectedAgent.mermaid_diagram}
                  </div>
                ) : (
                  <Empty description="暂无流程图" />
                )}
              </Card>
            </Col>
          </Row>
        )}
      </Drawer>
      {/* 执行Agent弹窗 */}
      <Modal
        title={`执行Agent: ${selectedAgent?.name}`}
        open={executeModalVisible}
        onCancel={() => setExecuteModalVisible(false)}
        width={1000}
        footer={[
          <Button key="cancel" onClick={() => setExecuteModalVisible(false)}>
            关闭
          </Button>,
          <Button
            key="execute"
            type="primary"
            icon={<PlayCircleOutlined />}
            loading={executing}
            onClick={handleExecuteAgent}
            disabled={executing}
          >
            执行
          </Button>,
        ]}
        styles={{
          body: {
            height: "70vh",
            display: "flex",
            flexDirection: "column",
            padding: "16px",
          },
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            height: "100%",
            overflow: "hidden",
          }}
        >
          {/* 查询输入 */}
          <div style={{ marginBottom: 16, flexShrink: 0 }}>
            <Text strong>查询内容:</Text>
            <TextArea
              value={executeQuery}
              onChange={(e) => setExecuteQuery(e.target.value)}
              placeholder="输入你的查询或任务..."
              rows={3}
              style={{ marginTop: 8 }}
              disabled={executing}
            />
          </div>

          {/* 执行结果 - 可滚动区域 */}
          <div
            style={{
              flex: 1,
              overflow: "auto",
              border: "1px solid #f0f0f0",
              borderRadius: 4,
              padding: 16,
            }}
          >
            {!executionResult && !executing && (
              <Empty
                description="点击执行按钮开始执行Agent"
                style={{ marginTop: 100 }}
              />
            )}

            {executing && !executionResult && (
              <div style={{ textAlign: "center", marginTop: 100 }}>
                <Spin size="large" tip="正在启动执行..." />
              </div>
            )}

            {executionResult && (
              <Space
                direction="vertical"
                style={{ width: "100%" }}
                size="large"
              >
                {/* 执行计划 */}
                {executionResult.plan && (
                  <Card title="执行计划" size="small">
                    <Text>{executionResult.plan.description}</Text>
                    <div style={{ marginTop: 12 }}>
                      {(
                        executionResult.plan.plan ||
                        executionResult.steps ||
                        []
                      ).map((step: any, i: number) => {
                        const stepData =
                          executionResult.steps?.find(
                            (s: any) => s.step === step.step
                          ) || step;
                        const status = getStepStatus(stepData);
                        return (
                          <Tag
                            key={i}
                            color={status.color}
                            style={{
                              marginBottom: 4,
                              marginRight: 8,
                              padding: "4px 8px",
                              cursor: "pointer",
                            }}
                            onClick={() => toggleStep(step.step)}
                          >
                            {status.icon} 步骤{step.step}:{" "}
                            {step.description || stepData.description}
                          </Tag>
                        );
                      })}
                    </div>
                  </Card>
                )}

                {/* 步骤执行详情 */}
                {executionResult.steps && executionResult.steps.length > 0 && (
                  <Card title="执行详情" size="small">
                    <Collapse
                      activeKey={Array.from(expandedSteps).map(String)}
                      onChange={(keys) =>
                        setExpandedSteps(
                          new Set((keys as string[]).map(Number))
                        )
                      }
                      items={executionResult.steps.map((step: any) => {
                        const status = getStepStatus(step);
                        return {
                          key: String(step.step),
                          label: (
                            <Space>
                              <span style={{ color: status.color }}>
                                {status.icon}
                              </span>
                              <Text strong>
                                步骤{step.step}: {step.description || step.name}
                              </Text>
                              <Tag
                                color={
                                  status.color === "#52c41a"
                                    ? "success"
                                    : status.color === "#ff4d4f"
                                      ? "error"
                                      : "processing"
                                }
                              >
                                {status.text}
                              </Tag>
                            </Space>
                          ),
                          children: (
                            <div>
                              {step.summary && (
                                <div style={{ marginBottom: 12 }}>
                                  <Text strong>执行摘要:</Text>
                                  <ul style={{ marginTop: 8, paddingLeft: 20 }}>
                                    {step.summary.sections_count && (
                                      <li>
                                        章节数: {step.summary.sections_count}
                                      </li>
                                    )}
                                    {step.summary.document_count && (
                                      <li>
                                        文档数: {step.summary.document_count}
                                      </li>
                                    )}
                                    {step.summary.word_count && (
                                      <li>字数: {step.summary.word_count}</li>
                                    )}
                                    {step.summary.errors_found !==
                                      undefined && (
                                        <li>
                                          发现错误: {step.summary.errors_found} 个
                                        </li>
                                      )}
                                    {step.summary.corrections_made !==
                                      undefined && (
                                        <li>
                                          修正: {step.summary.corrections_made} 处
                                        </li>
                                      )}
                                    {step.summary.improvements &&
                                      step.summary.improvements.length > 0 && (
                                        <li>
                                          改进:
                                          <ul>
                                            {step.summary.improvements.map(
                                              (imp: string, idx: number) => (
                                                <li key={idx}>{imp}</li>
                                              )
                                            )}
                                          </ul>
                                        </li>
                                      )}
                                  </ul>
                                </div>
                              )}
                              {step.error && (
                                <Alert
                                  message="执行错误"
                                  description={step.error}
                                  type="error"
                                  style={{ marginBottom: 12 }}
                                />
                              )}
                              {step.result && (
                                <div>
                                  <Text strong>执行结果:</Text>
                                  <pre
                                    style={{
                                      marginTop: 8,
                                      padding: 12,
                                      background: "#f5f5f5",
                                      borderRadius: 4,
                                      fontSize: 12,
                                      maxHeight: 300,
                                      overflow: "auto",
                                    }}
                                  >
                                    {JSON.stringify(step.result, null, 2)}
                                  </pre>
                                </div>
                              )}
                            </div>
                          ),
                        };
                      })}
                    />
                  </Card>
                )}

                {/* 最终答案/文档 */}
                {(executionResult.answer || executionResult.document) && (
                  <Card
                    title={executionResult.document ? "生成的文档" : "答案"}
                    size="small"
                  >
                    {executionResult.document ? (
                      <div>
                        <Title level={4}>
                          {executionResult.document.title || "未命名文档"}
                        </Title>
                        <div
                          style={{
                            marginTop: 16,
                            padding: 16,
                            background: "#fafafa",
                            borderRadius: 4,
                            maxHeight: 400,
                            overflow: "auto",
                          }}
                        >
                          <ReactMarkdown>
                            {executionResult.document.content || ""}
                          </ReactMarkdown>
                        </div>
                        {executionResult.document.word_count && (
                          <Text
                            type="secondary"
                            style={{ marginTop: 8, display: "block" }}
                          >
                            字数: {executionResult.document.word_count}
                          </Text>
                        )}
                      </div>
                    ) : (
                      <div
                        style={{
                          padding: 16,
                          background: "#fafafa",
                          borderRadius: 4,
                          maxHeight: 300,
                          overflow: "auto",
                        }}
                      >
                        <ReactMarkdown>{executionResult.answer}</ReactMarkdown>
                      </div>
                    )}
                  </Card>
                )}

                {executing && (
                  <div style={{ textAlign: "center", padding: 20 }}>
                    <Spin tip="执行中..." />
                  </div>
                )}
              </Space>
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
}
