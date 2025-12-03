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
    <Layout className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
      <Header className="flex items-center px-4 md:px-6 bg-white/80 backdrop-blur-md border-b border-gray-200/50 h-16 fixed top-0 left-0 right-0 z-50 shadow-soft">
        <div className="flex items-center">
          {/* <img
                        src={defaultThumbnail}
                        alt="Logo"
                        className="h-8 w-8 mr-3 animate-bounce-gentle"
                    /> */}
          <div className="hidden sm:block">
            <span className="font-bold text-xl bg-gradient-to-r from-primary-600 to-primary-900 bg-clip-text text-transparent">
              DocHive 文档管理系统
            </span>
          </div>
        </div>
        <div className="flex-1"></div>
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
          className="bg-white/90 backdrop-blur-md border-r border-gray-200/50 overflow-y-auto fixed left-0 h-screen z-40 shadow-soft"
          style={{
            top: "64px",
            height: "calc(100vh - 64px)",
            width: "240px",
          }}
          width={240}
        >
          {/* 精简并修复过的样式：关键在于覆盖 AntD 给父级 submenu 加的 selected/active/open 状态样式 */}
          <style>{`
            /* ---- 强制父级 submenu 标题在子项被选中或展开时保持透明/不变色 ---- */
            .ant-menu-submenu.ant-menu-submenu-selected > .ant-menu-submenu-title,
            .ant-menu-submenu.ant-menu-submenu-open > .ant-menu-submenu-title,
            .ant-menu-submenu.ant-menu-submenu-active > .ant-menu-submenu-title {
              background-color: transparent !important;
              color: inherit !important;
              box-shadow: none !important;
            }

            /* 一级菜单项和 submenu 标题的 hover 效果 */
            .ant-menu-item:hover,
            .ant-menu-submenu > .ant-menu-submenu-title:hover {
              background-color: rgba(24, 144, 255, 0.06) !important;
            }

            /* 选中状态 */
            .ant-menu-item-selected {
              background-color: rgba(24, 144, 255, 0.1) !important;
            }

            /* 保证图标/文字颜色在父级状态变化时不受影响 */
            .ant-menu-submenu-title .ant-menu-title-content,
            .ant-menu-submenu-title .anticon {
              color: inherit !important;
            }

            /* 细微：防止 submenu-title 在被焦点或 active 时出现内边框样式 */
            .ant-menu-submenu-title:focus {
              outline: none;
            }
          `}</style>

          <Menu
            mode="inline"
            selectedKeys={[getSelectedKey()]}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            className="bg-transparent border-none pt-4"
            theme="light"
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
                  },
                  {
                    key: "writing-templates",
                    label: <span className="font-medium">写作样例</span>,
                    onClick: () => navigate("/writing-templates"),
                  },
                ],
              },
              // {
              //     key: 'search',
              //     label: <span className="font-medium">文档检索</span>,
              //     onClick: () => navigate('/search'),
              //     icon: <SearchOutlined className="text-primary-600" />,
              //     className: 'mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200'
              // },

              {
                key: "llm-logs",
                label: <span className="font-medium">LLM日志</span>,
                onClick: () => navigate("/llm-logs"),
                icon: <BarChartOutlined className="text-primary-600" />,
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
          className="bg-transparent transition-all duration-300"
          style={{
            padding: "24px",
            marginLeft: "240px",
            marginTop: "64px",
            height: "calc(100vh - 64px)",
            overflow: "hidden",
          }}
        >
          <div className="bg-white/70 backdrop-blur-sm rounded-2xl shadow-soft border border-white/50 p-6 h-full overflow-auto transition-all duration-300 hover:shadow-medium">
            <Outlet />
          </div>
        </Content>
      </Layout>
    </Layout>
  );
}
