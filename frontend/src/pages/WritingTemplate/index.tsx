import React, { useEffect, useState } from "react";
import {
    Card,
    Table,
    Button,
    Modal,
    Form,
    Input,
    Select,
    Space,
    message,
    Tag,
    Drawer,
    Upload,
} from "antd";
import {
    PlusOutlined,
    DeleteOutlined,
    EyeOutlined,
    UploadOutlined,
} from "@ant-design/icons";
import type { UploadFile } from "antd";
import { writingTemplateService } from "../../services/writingTemplate";
import { templateService } from "../../services/template";

const { TextArea } = Input;

interface WritingTemplate {
    id: number;
    title: string;
    theme: string;
    content: string;
    description?: string;
    tags: string[];
    template_id: number;
    word_count?: number;
    created_at: string;
}

interface ClassTemplate {
    id: number;
    name: string;
}

const WritingTemplatePage: React.FC = () => {
    const [templates, setTemplates] = useState<WritingTemplate[]>([]);
    const [classTemplates, setClassTemplates] = useState<ClassTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploadVisible, setUploadVisible] = useState(false);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedTemplate, setSelectedTemplate] =
        useState<WritingTemplate | null>(null);
    const [form] = Form.useForm();
    const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(
        null
    );
    const [uploadMode, setUploadMode] = useState<"file" | "text">("text");

    useEffect(() => {
        fetchClassTemplates();
    }, []);

    useEffect(() => {
        if (selectedTemplateId) {
            fetchTemplates();
        } else {
            setTemplates([]);
        }
    }, [selectedTemplateId]);

    const fetchClassTemplates = async () => {
        try {
            const response = await templateService.getTemplates({
                page: 1,
                page_size: 100,
            });
            setClassTemplates(response.data.items || []);
        } catch (error) {
            message.error("获取分类模板失败");
        }
    };

    const fetchTemplates = async () => {
        if (!selectedTemplateId) return;

        setLoading(true);
        try {
            const response = await writingTemplateService.getTemplates(
                selectedTemplateId
            );
            setTemplates(response.data || []);
        } catch (error) {
            message.error("获取写作样例失败");
        } finally {
            setLoading(false);
        }
    };

    const handleUpload = async (values: any) => {
        if (!selectedTemplateId) {
            message.error("请先选择分类模板");
            return;
        }

        try {
            const tags = values.tags ? values.tags.split(/[,，\s]+/).filter((t: string) => t.trim()) : [];

            if (uploadMode === "file" && values.file && values.file[0]) {
                // 文件上传模式
                const formData = new FormData();
                formData.append("file", values.file[0].originFileObj);
                formData.append("title", values.title);
                formData.append("theme", values.theme);
                formData.append("template_id", selectedTemplateId.toString());
                formData.append("description", values.description || "");
                formData.append("tags", JSON.stringify(tags));

                await writingTemplateService.uploadFile(formData);
            } else {
                // 文本粘贴模式
                const data = {
                    title: values.title,
                    theme: values.theme,
                    content: values.content,
                    template_id: selectedTemplateId,
                    description: values.description || "",
                    tags: tags,
                };

                await writingTemplateService.createTemplate(data);
            }

            message.success("创建成功");
            setUploadVisible(false);
            form.resetFields();
            fetchTemplates();
        } catch (error) {
            message.error("创建失败");
        }
    };

    const handleDelete = async (id: number) => {
        try {
            await writingTemplateService.deleteTemplate(id);
            message.success("删除成功");
            fetchTemplates();
        } catch (error) {
            message.error("删除失败");
        }
    };

    const handleViewDetail = (record: WritingTemplate) => {
        setSelectedTemplate(record);
        setDetailVisible(true);
    };

    const columns = [
        {
            title: "ID",
            dataIndex: "id",
            key: "id",
            width: 60,
        },
        {
            title: "标题",
            dataIndex: "title",
            key: "title",
            ellipsis: true,
        },
        {
            title: "主题",
            dataIndex: "theme",
            key: "theme",
            width: 120,
            render: (theme: string) => <Tag color="blue">{theme}</Tag>,
        },
        {
            title: "标签",
            dataIndex: "tags",
            key: "tags",
            width: 200,
            render: (tags: string[]) => (
                <>
                    {tags?.map((tag) => (
                        <Tag key={tag} color="green">
                            {tag}
                        </Tag>
                    ))}
                </>
            ),
        },
        {
            title: "字数",
            dataIndex: "word_count",
            key: "word_count",
            width: 80,
            render: (count: number) => count || 0,
        },
        {
            title: "创建时间",
            dataIndex: "created_at",
            key: "created_at",
            width: 180,
            render: (text: string) => {
                if (!text) return "-";
                const timestamp = Number(text);
                return new Date(timestamp * 1000).toLocaleString();
            },
        },
        {
            title: "操作",
            key: "action",
            width: 180,
            render: (_: any, record: WritingTemplate) => (
                <Space>
                    <Button
                        type="link"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => handleViewDetail(record)}
                    >
                        查看
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
                    <h2 className="text-2xl font-bold">写作样例管理</h2>
                    <Space>
                        <Select
                            placeholder="选择分类模板"
                            style={{ width: 250 }}
                            allowClear
                            value={selectedTemplateId}
                            onChange={(value) => setSelectedTemplateId(value)}
                        >
                            {classTemplates.map((template) => (
                                <Select.Option key={template.id} value={template.id}>
                                    {template.name}
                                </Select.Option>
                            ))}
                        </Select>
                        <Button
                            type="primary"
                            icon={<PlusOutlined />}
                            onClick={() => setUploadVisible(true)}
                            disabled={!selectedTemplateId}
                        >
                            添加样例
                        </Button>
                    </Space>
                </div>

                {!selectedTemplateId ? (
                    <div
                        style={{ textAlign: "center", padding: "100px 0", color: "#999" }}
                    >
                        <p style={{ fontSize: "16px" }}>
                            请先选择分类模板以查看该模板下的写作样例
                        </p>
                    </div>
                ) : (
                    <Table
                        columns={columns}
                        dataSource={templates}
                        loading={loading}
                        rowKey="id"
                        pagination={{
                            pageSize: 10,
                            showSizeChanger: true,
                            showTotal: (total) => `共 ${total} 条`,
                        }}
                    />
                )}

                {/* 添加样例模态框 */}
                <Modal
                    title="添加写作样例"
                    open={uploadVisible}
                    onCancel={() => {
                        setUploadVisible(false);
                        form.resetFields();
                        setUploadMode("text");
                    }}
                    footer={null}
                    width={700}
                >
                    <Form form={form} layout="vertical" onFinish={handleUpload}>
                        <Form.Item
                            name="title"
                            label="标题"
                            rules={[{ required: true, message: "请输入标题" }]}
                        >
                            <Input placeholder="请输入标题" />
                        </Form.Item>

                        <Form.Item
                            name="theme"
                            label="主题"
                            rules={[{ required: true, message: "请输入主题" }]}
                        >
                            <Input placeholder="如：报告、方案、总结等" />
                        </Form.Item>

                        <Form.Item name="description" label="描述">
                            <Input placeholder="可选，描述这个样例的特点" />
                        </Form.Item>

                        <Form.Item name="tags" label="标签">
                            <Input placeholder="多个标签用逗号分隔" />
                        </Form.Item>

                        <Form.Item label="内容来源">
                            <Select
                                value={uploadMode}
                                onChange={(value) => setUploadMode(value)}
                            >
                                <Select.Option value="text">文本粘贴</Select.Option>
                                <Select.Option value="file">文件上传</Select.Option>
                            </Select>
                        </Form.Item>

                        {uploadMode === "text" ? (
                            <Form.Item
                                name="content"
                                label="内容"
                                rules={[{ required: true, message: "请输入内容" }]}
                            >
                                <TextArea
                                    rows={12}
                                    placeholder="请粘贴完整的文章内容..."
                                />
                            </Form.Item>
                        ) : (
                            <Form.Item
                                name="file"
                                label="文件"
                                valuePropName="fileList"
                                getValueFromEvent={(e) => {
                                    if (Array.isArray(e)) {
                                        return e;
                                    }
                                    return e?.fileList;
                                }}
                                rules={[{ required: true, message: "请选择文件" }]}
                            >
                                <Upload beforeUpload={() => false} maxCount={1}>
                                    <Button icon={<UploadOutlined />}>选择文件</Button>
                                </Upload>
                            </Form.Item>
                        )}

                        <Form.Item>
                            <Space>
                                <Button type="primary" htmlType="submit">
                                    提交
                                </Button>
                                <Button
                                    onClick={() => {
                                        setUploadVisible(false);
                                        form.resetFields();
                                        setUploadMode("text");
                                    }}
                                >
                                    取消
                                </Button>
                            </Space>
                        </Form.Item>
                    </Form>
                </Modal>

                {/* 详情抽屉 */}
                <Drawer
                    title="样例详情"
                    width={800}
                    open={detailVisible}
                    onClose={() => setDetailVisible(false)}
                >
                    {selectedTemplate && (
                        <div className="space-y-4">
                            <div>
                                <h4 className="font-semibold mb-2">基本信息</h4>
                                <div className="space-y-2">
                                    <div>
                                        <span className="text-gray-600">标题：</span>
                                        {selectedTemplate.title}
                                    </div>
                                    <div>
                                        <span className="text-gray-600">主题：</span>
                                        <Tag color="blue">{selectedTemplate.theme}</Tag>
                                    </div>
                                    {selectedTemplate.description && (
                                        <div>
                                            <span className="text-gray-600">描述：</span>
                                            {selectedTemplate.description}
                                        </div>
                                    )}
                                    <div>
                                        <span className="text-gray-600">标签：</span>
                                        {selectedTemplate.tags?.map((tag) => (
                                            <Tag key={tag} color="green">
                                                {tag}
                                            </Tag>
                                        ))}
                                    </div>
                                    <div>
                                        <span className="text-gray-600">字数：</span>
                                        {selectedTemplate.word_count || selectedTemplate.content?.length || 0}
                                    </div>
                                </div>
                            </div>

                            <div>
                                <h4 className="font-semibold mb-2">内容</h4>
                                <div
                                    className="p-4 bg-gray-50 rounded border border-gray-200"
                                    style={{
                                        whiteSpace: "pre-wrap",
                                        maxHeight: "500px",
                                        overflow: "auto",
                                    }}
                                >
                                    {selectedTemplate.content}
                                </div>
                            </div>
                        </div>
                    )}
                </Drawer>
            </Card>
        </div>
    );
};

export default WritingTemplatePage;
