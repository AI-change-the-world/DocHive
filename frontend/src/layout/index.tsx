import { Layout, Menu, Typography } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { FileTextOutlined, FolderOpenOutlined, SearchOutlined, DashboardOutlined, SettingOutlined } from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

export default function AppLayout() {


    const navigate = useNavigate();
    const location = useLocation();

    // 根据当前路径确定选中的菜单项
    const getSelectedKey = () => {
        const path = location.pathname;
        if (path.includes('/dashboard')) return 'dashboard';
        if (path.includes('/templates')) return 'templates';
        if (path.includes('/documents')) return 'documents';
        if (path.includes('/search')) return 'search';
        return 'dashboard'; // 默认选中项
    };



    return (
        <Layout className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50">
            <Header
                className="flex items-center px-4 md:px-6 bg-white/80 backdrop-blur-md border-b border-gray-200/50 h-16 fixed top-0 left-0 right-0 z-50 shadow-soft"
            >
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
                        <span className="text-primary-700 text-sm font-medium">智能文档分类分级系统</span>
                    </div>
                </div>
            </Header>
            <Layout>
                <Sider
                    className="bg-white/90 backdrop-blur-md border-r border-gray-200/50 overflow-y-auto fixed left-0 h-screen z-40 shadow-soft"
                    style={{
                        top: '64px',
                        height: 'calc(100vh - 64px)',
                        width: '240px',
                    }}
                    width={240}
                >
                    <Menu
                        mode="inline"
                        selectedKeys={[getSelectedKey()]}
                        className="bg-transparent border-none pt-4"
                        items={[
                            {
                                key: 'dashboard',
                                label: <span className="font-medium">仪表盘</span>,
                                onClick: () => navigate('/dashboard'),
                                icon: <DashboardOutlined className="text-primary-600" />,
                                className: 'mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200'
                            },
                            {
                                key: 'templates',
                                label: <span className="font-medium">分类模板</span>,
                                onClick: () => navigate('/templates'),
                                icon: <FolderOpenOutlined className="text-primary-600" />,
                                className: 'mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200'
                            },
                            {
                                key: 'documents',
                                label: <span className="font-medium">文档管理</span>,
                                onClick: () => navigate('/documents'),
                                icon: <FileTextOutlined className="text-primary-600" />,
                                className: 'mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200'
                            },
                            {
                                key: 'search',
                                label: <span className="font-medium">文档检索</span>,
                                onClick: () => navigate('/search'),
                                icon: <SearchOutlined className="text-primary-600" />,
                                className: 'mx-2 mb-1 rounded-lg hover:bg-primary-50 transition-all duration-200'
                            },
                        ]}
                    />
                </Sider>

                <Content
                    className="bg-transparent transition-all duration-300"
                    style={{
                        padding: '24px',
                        marginLeft: '240px',
                        marginTop: '64px',
                        height: 'calc(100vh - 64px)',
                        overflow: 'hidden',
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