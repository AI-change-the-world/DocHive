import React, { useState } from 'react';
import { Card, Form, Input, Button, Select, DatePicker, Table, Space, Tag, message } from 'antd';
import { SearchOutlined, DownloadOutlined } from '@ant-design/icons';
import { documentService } from '../../services';
import type { Document } from '../../types';

const { RangePicker } = DatePicker;

const SearchPage: React.FC = () => {
    const [form] = Form.useForm();
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState<Document[]>([]);
    const [total, setTotal] = useState(0);
    const [pagination, setPagination] = useState({ page: 1, page_size: 20 });

    const handleSearch = async (values: any) => {
        setLoading(true);
        try {
            const searchParams = {
                ...values,
                ...pagination,
                start_date: values.dateRange?.[0]?.format('YYYY-MM-DD'),
                end_date: values.dateRange?.[1]?.format('YYYY-MM-DD'),
            };
            delete searchParams.dateRange;

            const response = await documentService.searchDocuments(searchParams);
            setResults(response.data.items);
            setTotal(response.data.total);
        } catch (error) {
            message.error('搜索失败');
        } finally {
            setLoading(false);
        }
    };

    const columns = [
        { title: 'ID', dataIndex: 'id', key: 'id', width: 80 },
        { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
        { title: '分类编号', dataIndex: 'class_code', key: 'class_code' },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            render: (status: string) => <Tag>{status}</Tag>,
        },
        {
            title: '上传时间',
            dataIndex: 'upload_time',
            key: 'upload_time',
            render: (text: string) => new Date(text).toLocaleString(),
        },
        {
            title: '操作',
            key: 'action',
            render: (_: any, record: Document) => (
                <Button
                    type="link"
                    size="small"
                    icon={<DownloadOutlined />}
                    onClick={async () => {
                        const res = await documentService.getDownloadUrl(record.id);
                        window.open(res.data.download_url, '_blank');
                    }}
                >
                    下载
                </Button>
            ),
        },
    ];

    return (
        <div className="p-6">
            <Card title="文档检索" className="mb-4">
                <Form form={form} layout="vertical" onFinish={handleSearch}>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <Form.Item name="keyword" label="关键词">
                            <Input placeholder="输入搜索关键词" />
                        </Form.Item>
                        <Form.Item name="status" label="状态">
                            <Select placeholder="选择状态" allowClear>
                                <Select.Option value="completed">已完成</Select.Option>
                                <Select.Option value="processing">处理中</Select.Option>
                            </Select>
                        </Form.Item>
                        <Form.Item name="dateRange" label="日期范围">
                            <RangePicker style={{ width: '100%' }} />
                        </Form.Item>
                    </div>
                    <Form.Item>
                        <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                            搜索
                        </Button>
                    </Form.Item>
                </Form>
            </Card>

            <Card title="搜索结果">
                <Table
                    columns={columns}
                    dataSource={results}
                    loading={loading}
                    rowKey="id"
                    pagination={{
                        total,
                        current: pagination.page,
                        pageSize: pagination.page_size,
                        onChange: (page, pageSize) => setPagination({ page, page_size: pageSize }),
                    }}
                />
            </Card>
        </div>
    );
};

export default SearchPage;
