import React, { useEffect, useState } from 'react';
import { Card, Row, Col, Statistic, Table } from 'antd';
import { FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined, FolderOutlined } from '@ant-design/icons';
import { searchService, documentService } from '../../services';
import type { DocumentStatistics, Document } from '../../types';

const Dashboard: React.FC = () => {
    const [stats, setStats] = useState<DocumentStatistics | null>(null);
    const [recentDocs, setRecentDocs] = useState<Document[]>([]);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const [statsRes, docsRes] = await Promise.all([
                searchService.getStatistics(),
                documentService.getDocuments({ page: 1, page_size: 5 }),
            ]);
            setStats(statsRes.data);
            setRecentDocs(docsRes.data.items);
        } catch (error) {
            console.error('获取数据失败', error);
        }
    };

    const columns = [
        { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
        { title: '分类编号', dataIndex: 'class_code', key: 'class_code' },
        {
            title: '上传时间',
            dataIndex: 'upload_time',
            key: 'upload_time',
            render: (text: string) => new Date(text).toLocaleString(),
        },
    ];

    return (
        <div className="p-6 space-y-6">
            <h2 className="text-2xl font-bold">系统概览</h2>

            <Row gutter={[16, 16]}>
                <Col xs={24} sm={12} lg={6}>
                    <Card>
                        <Statistic
                            title="总文档数"
                            value={stats?.total_documents || 0}
                            prefix={<FileTextOutlined />}
                            valueStyle={{ color: '#3f8600' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card>
                        <Statistic
                            title="已完成"
                            value={stats?.by_status?.completed || 0}
                            prefix={<CheckCircleOutlined />}
                            valueStyle={{ color: '#52c41a' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card>
                        <Statistic
                            title="处理中"
                            value={stats?.by_status?.processing || 0}
                            prefix={<ClockCircleOutlined />}
                            valueStyle={{ color: '#1890ff' }}
                        />
                    </Card>
                </Col>
                <Col xs={24} sm={12} lg={6}>
                    <Card>
                        <Statistic
                            title="待处理"
                            value={stats?.by_status?.pending || 0}
                            prefix={<FolderOutlined />}
                            valueStyle={{ color: '#faad14' }}
                        />
                    </Card>
                </Col>
            </Row>

            <Card title="最近上传文档">
                <Table
                    columns={columns}
                    dataSource={recentDocs}
                    rowKey="id"
                    pagination={false}
                    size="small"
                />
            </Card>
        </div>
    );
};

export default Dashboard;
