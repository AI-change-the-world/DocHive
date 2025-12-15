import React, { useEffect, useState } from "react";
import { Card, Row, Col, Table, Tabs, Divider, Badge } from "antd";
import {
  FileTextOutlined,
  DatabaseOutlined,
  ApiOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import {
  searchService,
  documentService,
  templateService,
  llmLogService,
} from "../../services";
import type {
  DocumentStatistics,
  Document,
  ClassTemplate,
  LLMLogStatistics,
} from "../../types";

const { TabPane } = Tabs;

// 数字格式化函数
const formatNumber = (num: number): { value: number; suffix: string } => {
  if (num >= 1000000000) {
    return { value: Math.round((num / 1000000000) * 10) / 10, suffix: "B" };
  }
  if (num >= 1000000) {
    return { value: Math.round((num / 1000000) * 10) / 10, suffix: "M" };
  }
  if (num >= 1000) {
    return { value: Math.round((num / 1000) * 10) / 10, suffix: "K" };
  }
  return { value: num, suffix: "" };
};

// Token 数量格式化
const formatTokens = (tokens: number): string => {
  const formatted = formatNumber(tokens);
  return `${formatted.value}${formatted.suffix}`;
};

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<DocumentStatistics | null>(null);
  const [recentDocs, setRecentDocs] = useState<Document[]>([]);
  const [templates, setTemplates] = useState<ClassTemplate[]>([]);
  const [llmStats, setLlmStats] = useState<LLMLogStatistics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsRes, docsRes, templatesRes, llmStatsRes] = await Promise.all([
        searchService.getStatistics(),
        documentService.getDocuments({ page: 1, page_size: 5 }),
        templateService.getTemplates({ page: 1, page_size: 100 }),
        llmLogService.getStatistics(),
      ]);

      setStats(statsRes.data);
      setRecentDocs(docsRes.data.items);
      setTemplates(templatesRes.data.items);
      setLlmStats(llmStatsRes.data);
    } catch (error) {
      console.error("获取数据失败", error);
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    {
      title: <span style={{ fontWeight: "600", color: "#262626" }}>标题</span>,
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (text: string) => (
        <span style={{ color: "#1890ff", fontWeight: "500" }}>{text}</span>
      ),
    },
    {
      title: (
        <span style={{ fontWeight: "600", color: "#262626" }}>分类编号</span>
      ),
      dataIndex: "class_code",
      key: "class_code",
      render: (text: string) => (
        <span
          style={{
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            color: "#fff",
            padding: "4px 12px",
            borderRadius: "6px",
            fontSize: "13px",
            fontWeight: "500",
          }}
        >
          {text}
        </span>
      ),
    },
    {
      title: (
        <span style={{ fontWeight: "600", color: "#262626" }}>上传时间</span>
      ),
      dataIndex: "upload_time",
      key: "upload_time",
      render: (text: string) => (
        <span style={{ color: "#595959", fontSize: "13px" }}>
          {new Date(text).toLocaleString()}
        </span>
      ),
    },
    {
      title: <span style={{ fontWeight: "600", color: "#262626" }}>状态</span>,
      dataIndex: "status",
      key: "status",
      render: (status: string) => {
        const statusConfig: Record<
          string,
          { color: string; bg: string; text: string }
        > = {
          completed: { color: "#52c41a", bg: "#f6ffed", text: "已完成" },
          processing: { color: "#1890ff", bg: "#e6f7ff", text: "处理中" },
          pending: { color: "#faad14", bg: "#fffbe6", text: "待处理" },
          failed: { color: "#ff4d4f", bg: "#fff1f0", text: "失败" },
        };
        const config = statusConfig[status] || {
          color: "#8c8c8c",
          bg: "#f5f5f5",
          text: status,
        };
        return (
          <span
            style={{
              color: config.color,
              background: config.bg,
              padding: "4px 12px",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: "500",
              border: `1px solid ${config.color}30`,
            }}
          >
            {config.text}
          </span>
        );
      },
    },
  ];

  // 计算模板数量
  const templateCount = templates.length;

  // 计算LLM调用总数
  const totalLLMCalls = llmStats?.total_calls || 0;

  // 计算总消耗token数
  const totalTokens = llmStats?.total_tokens || 0;

  return (
    <div
      style={{
        padding: "24px",
        background: "linear-gradient(to bottom, #f0f5ff 0%, #ffffff 100%)",
      }}
    >
      <div style={{ marginBottom: "32px" }}>
        <h2
          style={{
            fontSize: "28px",
            fontWeight: "600",
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            marginBottom: "8px",
          }}
        >
          系统概览
        </h2>
        <p style={{ color: "#8c8c8c", fontSize: "14px" }}>
          实时监控文档管理系统运行状态
        </p>
      </div>

      {/* 核心指标卡片 */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "24px" }}>
        <div
          style={{
            flex: "1 1 200px",
            minWidth: "200px",
            maxWidth: "100%",
            height: "120px",
            borderRadius: "16px",
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            boxShadow: "0 8px 32px rgba(102, 126, 234, 0.25)",
            padding: "24px",
            cursor: "pointer",
            transition: "transform 0.3s ease, box-shadow 0.3s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-4px)";
            e.currentTarget.style.boxShadow = "0 12px 40px rgba(102, 126, 234, 0.35)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "0 8px 32px rgba(102, 126, 234, 0.25)";
          }}
        >
          <div>
            <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "14px", marginBottom: "12px" }}>
              总文档数
            </div>
            <div style={{ color: "#fff", fontSize: "32px", fontWeight: "600", lineHeight: "1" }}>
              {(stats?.total_documents || 0).toLocaleString()}
            </div>
          </div>
          <FileTextOutlined style={{ fontSize: "40px", color: "rgba(255,255,255,0.3)" }} />
        </div>

        <div
          style={{
            flex: "1 1 200px",
            minWidth: "200px",
            maxWidth: "100%",
            height: "120px",
            borderRadius: "16px",
            background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
            boxShadow: "0 8px 32px rgba(240, 147, 251, 0.25)",
            padding: "24px",
            cursor: "pointer",
            transition: "transform 0.3s ease, box-shadow 0.3s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-4px)";
            e.currentTarget.style.boxShadow = "0 12px 40px rgba(240, 147, 251, 0.35)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "0 8px 32px rgba(240, 147, 251, 0.25)";
          }}
        >
          <div>
            <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "14px", marginBottom: "12px" }}>
              模板数量
            </div>
            <div style={{ color: "#fff", fontSize: "32px", fontWeight: "600", lineHeight: "1" }}>
              {templateCount.toLocaleString()}
            </div>
          </div>
          <DatabaseOutlined style={{ fontSize: "40px", color: "rgba(255,255,255,0.3)" }} />
        </div>

        <div
          style={{
            flex: "1 1 200px",
            minWidth: "200px",
            maxWidth: "100%",
            height: "120px",
            borderRadius: "16px",
            background: "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
            boxShadow: "0 8px 32px rgba(79, 172, 254, 0.25)",
            padding: "24px",
            cursor: "pointer",
            transition: "transform 0.3s ease, box-shadow 0.3s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-4px)";
            e.currentTarget.style.boxShadow = "0 12px 40px rgba(79, 172, 254, 0.35)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "0 8px 32px rgba(79, 172, 254, 0.25)";
          }}
        >
          <div>
            <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "14px", marginBottom: "12px" }}>
              LLM调用次数
            </div>
            <div style={{ color: "#fff", fontSize: "32px", fontWeight: "600", lineHeight: "1" }}>
              {totalLLMCalls.toLocaleString()}
            </div>
          </div>
          <ApiOutlined style={{ fontSize: "40px", color: "rgba(255,255,255,0.3)" }} />
        </div>

        <div
          style={{
            flex: "1 1 200px",
            minWidth: "200px",
            maxWidth: "100%",
            height: "120px",
            borderRadius: "16px",
            background: "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
            boxShadow: "0 8px 32px rgba(250, 112, 154, 0.25)",
            padding: "24px",
            cursor: "pointer",
            transition: "transform 0.3s ease, box-shadow 0.3s ease",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.transform = "translateY(-4px)";
            e.currentTarget.style.boxShadow = "0 12px 40px rgba(250, 112, 154, 0.35)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "translateY(0)";
            e.currentTarget.style.boxShadow = "0 8px 32px rgba(250, 112, 154, 0.25)";
          }}
        >
          <div>
            <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "14px", marginBottom: "8px" }}>
              消耗Token数
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: "2px" }}>
              <span style={{ color: "#fff", fontSize: "28px", fontWeight: "600", lineHeight: "1" }}>
                {formatNumber(totalTokens).value}
              </span>
              <span style={{ color: "#fff", fontSize: "16px", fontWeight: "500" }}>
                {formatNumber(totalTokens).suffix}
              </span>
            </div>
            <div style={{ color: "rgba(255,255,255,0.7)", fontSize: "11px", marginTop: "4px" }}>
              {totalTokens.toLocaleString()} tokens
            </div>
          </div>
          <BarChartOutlined style={{ fontSize: "40px", color: "rgba(255,255,255,0.3)" }} />
        </div>
      </div>

      {/* 图表和表格区域 */}
      <div style={{ marginTop: "32px" }}>
        <Tabs
          defaultActiveKey="1"
          size="large"
          tabBarStyle={{
            borderBottom: "2px solid #f0f0f0",
            marginBottom: "24px",
          }}
        >
          <TabPane
            tab={
              <span style={{ fontSize: "15px", fontWeight: "500" }}>
                <ClockCircleOutlined style={{ marginRight: "8px" }} />
                最近上传文档
              </span>
            }
            key="1"
          >
            <Card
              style={{
                borderRadius: "16px",
                boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
                border: "none",
              }}
            >
              <Table
                columns={columns}
                dataSource={recentDocs}
                rowKey="id"
                pagination={false}
                loading={loading}
                style={{
                  background: "#fff",
                  borderRadius: "12px",
                }}
                rowClassName={() => "hover:bg-gray-50"}
              />
            </Card>
          </TabPane>
          <TabPane
            tab={
              <span style={{ fontSize: "15px", fontWeight: "500" }}>
                <ApiOutlined style={{ marginRight: "8px" }} />
                系统状态
              </span>
            }
            key="2"
          >
            <Card
              style={{
                borderRadius: "16px",
                boxShadow: "0 4px 16px rgba(0,0,0,0.06)",
                border: "none",
              }}
            >
              <h3
                style={{
                  fontSize: "18px",
                  fontWeight: "600",
                  color: "#262626",
                  marginBottom: "8px",
                }}
              >
                LLM调用统计
              </h3>
              <Divider style={{ margin: "16px 0" }} />
              <Row gutter={[24, 24]}>
                <Col span={12}>
                  <div
                    style={{
                      background:
                        "linear-gradient(135deg, #667eea15 0%, #764ba215 100%)",
                      padding: "20px",
                      borderRadius: "12px",
                      border: "1px solid #e8e8ff",
                    }}
                  >
                    <p
                      style={{
                        fontWeight: "600",
                        fontSize: "15px",
                        color: "#262626",
                        marginBottom: "16px",
                      }}
                    >
                      按提供商统计
                    </p>
                    <div style={{ paddingLeft: "8px" }}>
                      {llmStats?.by_provider &&
                        Object.entries(llmStats.by_provider).map(
                          ([provider, data]) => (
                            <div
                              key={provider}
                              style={{
                                marginBottom: "12px",
                                padding: "12px",
                                background: "#fff",
                                borderRadius: "8px",
                                border: "1px solid #f0f0f0",
                              }}
                            >
                              <Badge
                                color="#667eea"
                                text={
                                  <span style={{ fontSize: "14px" }}>
                                    <strong>{provider}</strong>: {data.calls.toLocaleString()}{" "}
                                    次调用, {formatTokens(data.tokens)} tokens
                                    <span style={{ color: "#8c8c8c", fontSize: "12px", marginLeft: "8px" }}>
                                      ({data.tokens.toLocaleString()})
                                    </span>
                                  </span>
                                }
                              />
                            </div>
                          )
                        )}
                    </div>
                  </div>
                </Col>
                <Col span={12}>
                  <div
                    style={{
                      background:
                        "linear-gradient(135deg, #4facfe15 0%, #00f2fe15 100%)",
                      padding: "20px",
                      borderRadius: "12px",
                      border: "1px solid #e0f7ff",
                    }}
                  >
                    <p
                      style={{
                        fontWeight: "600",
                        fontSize: "15px",
                        color: "#262626",
                        marginBottom: "16px",
                      }}
                    >
                      按模型统计
                    </p>
                    <div style={{ paddingLeft: "8px" }}>
                      {llmStats?.by_model &&
                        Object.entries(llmStats.by_model).map(
                          ([model, data]) => (
                            <div
                              key={model}
                              style={{
                                marginBottom: "12px",
                                padding: "12px",
                                background: "#fff",
                                borderRadius: "8px",
                                border: "1px solid #f0f0f0",
                              }}
                            >
                              <Badge
                                color="#4facfe"
                                text={
                                  <span style={{ fontSize: "14px" }}>
                                    <strong>{model}</strong>: {data.calls.toLocaleString()}{" "}
                                    次调用, {formatTokens(data.tokens)} tokens
                                    <span style={{ color: "#8c8c8c", fontSize: "12px", marginLeft: "8px" }}>
                                      ({data.tokens.toLocaleString()})
                                    </span>
                                  </span>
                                }
                              />
                            </div>
                          )
                        )}
                    </div>
                  </div>
                </Col>
              </Row>
            </Card>
          </TabPane>
        </Tabs>
      </div>
    </div>
  );
};

export default Dashboard;
