import React, { useState, useEffect } from "react";
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
} from "antd";
import {
  SaveOutlined,
  EyeOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  RobotOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  DeleteOutlined,
  EditOutlined,
} from "@ant-design/icons";
import mermaid from "mermaid";
import { agentEditorService } from "../../services/agentEditor";
import { templateService } from "../../services/template";
import { v4 as uuidv4 } from "uuid";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Search } = Input;

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
              }));
              break;
            case "stage_complete":
              setExecutionResult((prev: any) => ({
                ...prev,
                stages: [...(prev.stages || []), event.data],
              }));
              break;
            case "answer":
              setExecutionResult((prev: any) => ({
                ...prev,
                answer: event.data.answer,
                documents: event.data.documents,
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

  // 打开执行弹窗
  const handleOpenExecuteModal = (agent: any) => {
    setSelectedAgent(agent);
    setExecuteQuery("");
    setExecutionResult(null);
    setExecuteModalVisible(true);
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
      render: (text: string, record: any) => (
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
      render: (pattern: string) => (
        <Tag color="blue">{pattern}</Tag>
      ),
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
      render: (time: number) => new Date(time * 1000).toLocaleString(),
    },
    {
      title: "操作",
      key: "action",
      render: (_: any, record: any) => (
        <Space>
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
            <Paragraph>
              管理和执行自定义的智能体工作流
            </Paragraph>
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
              style={{ height: "100%", display: "flex", flexDirection: "column" }}
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
              style={{ height: "100%", display: "flex", flexDirection: "column" }}
              bodyStyle={{ flex: 1, overflow: "auto" }}
            >
              {renderRightPanel()}
            </Card>
          </Col>
        </Row>
      </Drawer>

      {/* 执行Agent弹窗 */}
      <Modal
        title={`执行Agent: ${selectedAgent?.name}`}
        open={executeModalVisible}
        onCancel={() => setExecuteModalVisible(false)}
        width={800}
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
          >
            执行
          </Button>,
        ]}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="large">
          {/* 查询输入 */}
          <div>
            <Text strong>查询内容:</Text>
            <TextArea
              value={executeQuery}
              onChange={(e) => setExecuteQuery(e.target.value)}
              placeholder="输入你的查询或任务..."
              rows={3}
              style={{ marginTop: 8 }}
            />
          </div>

          {/* 执行结果 */}
          {executionResult && (
            <div>
              <Divider>执行结果</Divider>

              {/* 执行计划 */}
              {executionResult.plan && (
                <Card title="执行计划" size="small" style={{ marginBottom: 16 }}>
                  <Text>{executionResult.plan.description}</Text>
                  <div style={{ marginTop: 8 }}>
                    {executionResult.plan.plan?.map((step: any, i: number) => (
                      <Tag key={i} color="blue" style={{ marginBottom: 4 }}>
                        步骤{step.step}: {step.description}
                      </Tag>
                    ))}
                  </div>
                </Card>
              )}

              {/* 步骤执行状态 */}
              {executionResult.stages && executionResult.stages.length > 0 && (
                <Card title="执行进度" size="small" style={{ marginBottom: 16 }}>
                  {executionResult.stages.map((stage: any, i: number) => (
                    <div key={i} style={{ marginBottom: 8 }}>
                      <CheckCircleOutlined style={{ color: "#52c41a", marginRight: 8 }} />
                      {stage.message}
                    </div>
                  ))}
                </Card>
              )}

              {/* 最终答案 */}
              {executionResult.answer && (
                <Card title="答案" size="small">
                  <Paragraph>{executionResult.answer}</Paragraph>
                </Card>
              )}

              {executing && (
                <div style={{ textAlign: "center" }}>
                  <Spin tip="执行中..." />
                </div>
              )}
            </div>
          )}
        </Space>
      </Modal>
    </div>
  );
}
