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
} from "antd";
import {
  SaveOutlined,
  EyeOutlined,
  FileTextOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import mermaid from "mermaid";
import { agentEditorService } from "../../services/agentEditor";
import { templateService } from "../../services/template";

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
  const [markdown, setMarkdown] = useState("");
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [templateId, setTemplateId] = useState<number | undefined>();
  const [templates, setTemplates] = useState<any[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

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

  // 加载分类模板列表
  useEffect(() => {
    loadTemplates();
  }, []);

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
    } catch (error) {
      message.error("创建失败");
      console.error(error);
    } finally {
      setLoading(false);
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

  return (
    <div style={{ padding: 24, height: "100%" }}>
      <Card style={{ marginBottom: 16 }}>
        <Title level={2}>
          <RobotOutlined /> Agent编辑器
        </Title>
        <Paragraph>
          使用Markdown格式定义Agent流程，大模型自动验证并生成流程图
        </Paragraph>
      </Card>

      <Row gutter={16} style={{ height: "calc(100% - 140px)" }}>
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
              <Text strong>关联分类模板（可选）:</Text>
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
    </div>
  );
}
