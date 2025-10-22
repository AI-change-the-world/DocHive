import React, { useState, useEffect } from 'react';
import {
    Table,
    Button,
    Space,
    Upload,
    Modal,
    Form,
    Input,
    Select,
    message,
    Tag,
    Card,
    Drawer,
} from 'antd';
import {
    UploadOutlined,
    EyeOutlined,
    DeleteOutlined,
    DownloadOutlined,
    FileTextOutlined,
} from '@ant-design/icons';
import { documentService, templateService, classificationService } from '../../services';
import type { Document, ClassTemplate } from '../../types';

const DocumentPage: React.FC = () => {
    const [documents, setDocuments] = useState<Document[]>([]);
    const [templates, setTemplates] = useState<ClassTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploadVisible, setUploadVisible] = useState(false);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
    const [total, setTotal] = useState(0);
    const [pagination, setPagination] = useState({ page: 1, page_size: 10 });
    const [filters, setFilters] = useState<any>({});
    const [form] = Form.useForm();

    useEffect(() => {
        fetchDocuments();
        fetchTemplates();
    }, [pagination, filters]);

    const fetchDocuments = async () => {
        setLoading(true);
        try {
            const response = await documentService.getDocuments({
                ...pagination,
                ...filters,
            });
            setDocuments(response.data.items);
            setTotal(response.data.total);
        } catch (error) {
            message.error('获取文档列表失败');
        } finally {
            setLoading(false);
        }
    };

    const fetchTemplates = async () => {
        try {
            const response = await templateService.getTemplates({ page: 1, page_size: 100 });
            setTemplates(response.data.items);
        } catch (error) {
            console.error('获取模板列表失败');
        }
    };

    const handleUpload = async (values: any) => {
        const { file, title, template_id } = values;

        const formData = new FormData();
        formData.append('file', file[0].originFileObj);
        formData.append('title', title);
        if (template_id) {
            formData.append('template_id', template_id);
        }

        try {
            await documentService.uploadDocument(formData);
            message.success('上传成功');
            setUploadVisible(false);
            form.resetFields();
            fetchDocuments();
        } catch (error) {
            message.error('上传失败');
        }
    };

    const handleClassify = async (record: Document) => {
        if (!record.template_id) {
            message.error('请先为文档关联分类模板');
            return;
        }

        try {
            await classificationService.classifyDocument({
                document_id: record.id,
                template_id: record.template_id,
            });
            message.success('分类成功');
            fetchDocuments();
        } catch (error) {
            message.error('分类失败');
        }
    };

    const handleDownload = async (record: Document) => {
        try {
            const response = await documentService.getDownloadUrl(record.id);
            window.open(response.data.download_url, '_blank');
        } catch (error) {
            message.error('获取下载链接失败');
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await documentService.deleteDocument(id);
            message.success('删除成功');
            fetchDocuments();
        } catch (error) {
            message.error('删除失败');
        }
    };

    const handleViewDetail = (record: Document) => {
        setSelectedDoc(record);
        setDetailVisible(true);
    };

    const getStatusColor = (status: string) => {
        const colorMap: Record<string, string> = {
            pending: 'default',
            processing: 'processing',
            completed: 'success',
            failed: 'error',
        };
        return colorMap[status] || 'default';
    };

    const getStatusText = (status: string) => {
        const textMap: Record<string, string> = {
            pending: '待处理',
            processing: '处理中',
            completed: '已完成',
            failed: '失败',
        };
        return textMap[status] || status;
    };

    const columns = [
        {
            title: 'ID',
            dataIndex: 'id',
            key: 'id',
            width: 80,
        },
        {
            title: '标题',
            dataIndex: 'title',
            key: 'title',
            ellipsis: true,
        },
        {
            title: '文件名',
            dataIndex: 'original_filename',
            key: 'original_filename',
            ellipsis: true,
        },
        {
            title: '类型',
            dataIndex: 'file_type',
            key: 'file_type',
            width: 80,
        },
        {
            title: '状态',
            dataIndex: 'status',
            key: 'status',
            width: 100,
            render: (status: string) => (
                <Tag color={getStatusColor(status)}>{getStatusText(status)}</Tag>
            ),
        },
        {
            title: '分类编号',
            dataIndex: 'class_code',
            key: 'class_code',
            width: 150,
        },
        {
            title: '上传时间',
            dataIndex: 'upload_time',
            key: 'upload_time',
            width: 180,
            render: (text: string) => new Date(text).toLocaleString(),
        },
        {
            title: '操作',
            key: 'action',
            width: 280,
            render: (_: any, record: Document) => (
                <Space>
                    <Button
                        type="link"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewDetail(record)}
                    >
                        详情
                    </Button>
                    {record.status === 'completed' && !record.class_code && (
                        <Button
                            type="link"
                            size="small"
                            onClick={() => handleClassify(record)}
                        >
                            分类
                        </Button>
                    )}
                    <Button
                        type="link"
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={() => handleDownload(record)}
                    >
                        下载
                    </Button>
                    <Button
                        type="link"
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(record.id)}
                    >
                        删除
                    </Button>
                </Space>
            ),
        },
    ];

    return (
        <div className="p-6">
            <Card>
                <div className="mb-4 flex justify-between items-center">
                    <h2 className="text-2xl font-bold">文档管理</h2>
                    <Space>
                        <Select
                            placeholder="选择状态"
                            style={{ width: 120 }}
                            allowClear
                            onChange={(value) => setFilters({ ...filters, status: value })}
                        >
                            <Select.Option value="pending">待处理</Select.Option>
                            <Select.Option value="processing">处理中</Select.Option>
                            <Select.Option value="completed">已完成</Select.Option>
                            <Select.Option value="failed">失败</Select.Option>
                        </Select>
                        <Button
                            type="primary"
                            icon={<UploadOutlined />}
                            onClick={() => setUploadVisible(true)}
                        >
                            上传文档
                        </Button>
                    </Space>
                </div>

                <Table
                    columns={columns}
                    dataSource={documents}
                    loading={loading}
                    rowKey="id"
                    pagination={{
                        total,
                        current: pagination.page,
                        pageSize: pagination.page_size,
                        onChange: (page, pageSize) => {
                            setPagination({ page, page_size: pageSize });
                        },
                    }}
                />

                {/* 上传文档模态框 */}
                <Modal
                    title="上传文档"
                    open={uploadVisible}
                    onCancel={() => setUploadVisible(false)}
                    footer={null}
                >
                    <Form
                        form={form}
                        layout="vertical"
                        onFinish={handleUpload}
                    >
                        <Form.Item
                            name="title"
                            label="文档标题"
                            rules={[{ required: true, message: '请输入文档标题' }]}
                        >
                            <Input placeholder="请输入文档标题" />
                        </Form.Item>

                        <Form.Item
                            name="template_id"
                            label="分类模板"
                        >
                            <Select placeholder="选择分类模板（可选）" allowClear>
                                {templates.map((template) => (
                                    <Select.Option key={template.id} value={template.id}>
                                        {template.name}
                                    </Select.Option>
                                ))}
                            </Select>
                        </Form.Item>

                        <Form.Item
                            name="file"
                            label="文档文件"
                            valuePropName="fileList"
                            getValueFromEvent={(e) => {
                                if (Array.isArray(e)) {
                                    return e;
                                }
                                return e?.fileList;
                            }}
                            rules={[{ required: true, message: '请选择文件' }]}
                        >
                            <Upload
                                beforeUpload={() => false}
                                maxCount={1}
                            >
                                <Button icon={<UploadOutlined />}>选择文件</Button>
                            </Upload>
                        </Form.Item>

                        <Form.Item>
                            <Space>
                                <Button type="primary" htmlType="submit">
                                    上传
                                </Button>
                                <Button onClick={() => setUploadVisible(false)}>
                                    取消
                                </Button>
                            </Space>
                        </Form.Item>
                    </Form>
                </Modal>

                {/* 文档详情抽屉 */}
                <Drawer
                    title="文档详情"
                    width={600}
                    open={detailVisible}
                    onClose={() => setDetailVisible(false)}
                >
                    {selectedDoc && (
                        <div className="space-y-4">
                            <div>
                                <h4 className="font-semibold mb-2">基本信息</h4>
                                <div className="space-y-2">
                                    <div><span className="text-gray-600">标题：</span>{selectedDoc.title}</div>
                                    <div><span className="text-gray-600">文件名：</span>{selectedDoc.original_filename}</div>
                                    <div><span className="text-gray-600">文件类型：</span>{selectedDoc.file_type}</div>
                                    <div>
                                        <span className="text-gray-600">文件大小：</span>
                                        {selectedDoc.file_size ? `${(selectedDoc.file_size / 1024).toFixed(2)} KB` : '-'}
                                    </div>
                                    <div>
                                        <span className="text-gray-600">状态：</span>
                                        <Tag color={getStatusColor(selectedDoc.status)}>
                                            {getStatusText(selectedDoc.status)}
                                        </Tag>
                                    </div>
                                </div>
                            </div>

                            {selectedDoc.class_path && (
                                <div>
                                    <h4 className="font-semibold mb-2">分类信息</h4>
                                    <div className="space-y-2">
                                        <div><span className="text-gray-600">分类编号：</span>{selectedDoc.class_code}</div>
                                        {Object.entries(selectedDoc.class_path).map(([key, value]) => (
                                            <div key={key}>
                                                <span className="text-gray-600">{key}：</span>{value}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {selectedDoc.extracted_data && Object.keys(selectedDoc.extracted_data).length > 0 && (
                                <div>
                                    <h4 className="font-semibold mb-2">抽取信息</h4>
                                    <div className="space-y-2">
                                        {Object.entries(selectedDoc.extracted_data).map(([key, value]) => (
                                            <div key={key}>
                                                <span className="text-gray-600">{key}：</span>
                                                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {selectedDoc.summary && (
                                <div>
                                    <h4 className="font-semibold mb-2">摘要</h4>
                                    <p className="text-gray-700">{selectedDoc.summary}</p>
                                </div>
                            )}
                        </div>
                    )}
                </Drawer>
            </Card>
        </div>
    );
};

export default DocumentPage;
