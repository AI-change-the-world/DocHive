import { Layout, Menu, Typography } from "antd";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import React, { useState, useEffect } from "react";
import {
  FileTextOutlined,
  FolderOpenOutlined,
  SearchOutlined,
  DashboardOutlined,
  QuestionCircleOutlined,
  BarChartOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  RobotOutlined,
  HistoryOutlined,
} from "@ant-design/icons";

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [openKeys, setOpenKeys] = useState<string[]>([]);

  // 根据当前路径确定选中的菜单项
  const getSelectedKey = () => {
    const path = location.pathname;
    if (path.includes("/dashboard")) return "dashboard";
    if (path.includes("/templates")) return "templates";
    if (path.includes("/documents")) return "documents";
    if (path.includes("/writing-templates")) return "writing-templates";
    if (path.includes("/search")) return "search";
    if (path.includes("/qa-beta")) return "qa-beta";
    if (path.includes("/qa")) return "qa";
    if (path.includes("/llm-logs")) return "llm-logs";
    if (path.includes("/template-configs")) return "template-configs";
    if (path.includes("/agent-editor")) return "agent-editor";
    if (path.includes("/execution-records")) return "execution-records";
    return "dashboard"; // 默认选中项
  };

  // 初始化和路径变化时更新展开的菜单
  useEffect(() => {
    const path = location.pathname;
    if (path.includes("/documents") || path.includes("/writing-templates")) {
      setOpenKeys(["doc-management"]);
    }
  }, [location.pathname]);

  // 处理菜单展开/收起
  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys);
  };

  return (
    <Layout className="app-shell min-h-screen">
      <Header className="app-header flex items-center px-4 md:px-6">
        <div className="flex items-center">
          <div className="hidden sm:block">
            <span className="app-title text-xl">DocHive 文档管理系统</span>
          </div>
        </div>
        <div className="flex-1" />
        <div className="flex items-center space-x-4">
          <div className="hidden md:flex items-center space-x-2 bg-primary-50 px-3 py-1 rounded-full">
            <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span className="text-primary-700 text-sm font-medium">
              分类分级与个性化智能体赋能
            </span>
          </div>
        </div>
      </Header>
      <Layout>
        <Sider
          className="app-sider z-40"
          width={240}
        >
          <style>{`
            /* 一级菜单左对齐，适度内边距 */
            .dochive-menu > .ant-menu-item,
            .dochive-menu > .ant-menu-submenu > .ant-menu-submenu-title {
              padding-inline-start: 12px !important;
              text-align: left !important;
            }
            /* 二级菜单加大缩进 */
            .dochive-menu .ant-menu-sub .ant-menu-item,
            .dochive-menu .ant-menu-sub .ant-menu-submenu-title {
              padding-inline-start: 28px !important;
              text-align: left !important;
            }
            .dochive-menu .ant-menu-title-content {
              font-weight: 500;
            }
          `}</style>

          <Menu
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            className="dochive-menu app-menu"
            items={[
              {
                key: "dashboard",
                label: <span className="font-medium">仪表盘</span>,
                onClick: () => navigate("/dashboard"),
                icon: <DashboardOutlined className="text-primary-600" />,
              },
              /* 已弃用 */
              // {
              //   key: "qa",
              //   label: (
              //     <span className="font-medium">
              //       智能问答{" "}
              //       <span className="ml-1 px-1.5 py-0.5 text-xs bg-purple-100 text-purple-600 rounded">
              //         已弃用
              //       </span>
              //     </span>
              //   ),
              //   onClick: () => navigate("/qa"),
              //   icon: <QuestionCircleOutlined className="text-primary-600" />,
              //   className:
              //     "mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200",
              // },
              {
                key: "qa-beta",
                label: (
                  <span className="font-medium">
                    知识问答
                    {/* <span className="ml-1 px-1.5 py-0.5 text-xs bg-purple-100 text-purple-600 rounded">
                      Beta
                    </span> */}
                  </span>
                ),
                onClick: () => navigate("/qa-beta"),
                icon: <ThunderboltOutlined className="text-purple-600" />,
              },
              {
                key: "agent-editor",
                label: (
                  <span className="font-medium">
                    Agent{" "}
                    {/* <span className="ml-1 px-1.5 py-0.5 text-xs bg-purple-100 text-purple-600 rounded">
                      Beta
                    </span> */}
                  </span>
                ),
                onClick: () => navigate("/agent-editor"),
                icon: <RobotOutlined className="text-blue-600" />,
              },

              {
                key: "templates",
                label: <span className="font-medium">编码模板</span>,
                onClick: () => navigate("/templates"),
                icon: <FolderOpenOutlined className="text-primary-600" />,
              },
              {
                key: "doc-management",
                label: <span className="font-medium">文档管理</span>,
                icon: <FileTextOutlined className="text-primary-600" />,
                children: [
                  {
                    key: "documents",
                    label: <span className="font-medium">文档管理</span>,
                    onClick: () => navigate("/documents"),
                    icon: <FileTextOutlined className="text-primary-600" />,
                  },
                  {
                    key: "writing-templates",
                    label: <span className="font-medium">写作样例</span>,
                    onClick: () => navigate("/writing-templates"),
                    icon: <FileTextOutlined className="text-primary-600" />,
                  },
                ],
              },
              {
                key: "logs",
                label: <span className="font-medium">日志</span>,
                icon: <BarChartOutlined className="text-primary-600" />,
                children: [
                  {
                    key: "execution-records",
                    label: <span className="font-medium">Agent日志</span>,
                    onClick: () => navigate("/execution-records"),
                    icon: <HistoryOutlined className="text-green-600" />,
                  },
                  {
                    key: "llm-logs",
                    label: <span className="font-medium">LLM日志</span>,
                    onClick: () => navigate("/llm-logs"),
                    icon: <BarChartOutlined className="text-primary-600" />,
                  },
                ],
              },


              {
                key: "template-configs",
                label: <span className="font-medium">模板配置</span>,
                onClick: () => navigate("/template-configs"),
                icon: <SettingOutlined className="text-primary-600" />,
              },
            ]}
          />
        </Sider>

        <Content
          className="app-content"
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
