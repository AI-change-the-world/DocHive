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
    Radio,
} from 'antd';
import {
    UploadOutlined,
    EyeOutlined,
    DeleteOutlined,
    DownloadOutlined,
} from '@ant-design/icons';
import { documentService, templateService, classificationService } from '../../services';
import { getDocumentTypesByTemplate } from '../../services/documentType';
import type { Document, ClassTemplate, DocumentType } from '../../types';
import type { SSEEvent } from '../../utils/sseClient';

const DocumentPage: React.FC = () => {
    const [documents, setDocuments] = useState<any[]>([]);
    const [templates, setTemplates] = useState<ClassTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploadVisible, setUploadVisible] = useState(false);
    const [detailVisible, setDetailVisible] = useState(false);
    const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
    const [total, setTotal] = useState(0);
    const [filters, setFilters] = useState<any>({});
    const [form] = Form.useForm();
    const [uploadStatus, setUploadStatus] = useState<string>('');
    const [isUploading, setIsUploading] = useState(false);
    const [uploadMode, setUploadMode] = useState<'auto' | 'manual'>('auto'); // 'auto' | 'manual'
    const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null); // 用于上传的模板
    const [viewTemplateId, setViewTemplateId] = useState<number | null>(null); // 用于查看文档列表的模板
    const [templateLevels, setTemplateLevels] = useState<Array<any>>([]);
    const [levelOptions, setLevelOptions] = useState<Record<string, string[]>>({});
    const [levelValues, setLevelValues] = useState<Record<number, string>>({});
    const [docTypeId, setDocTypeId] = useState<number | null>(null); // 存储选中的文档类型ID
    const [editCodeVisible, setEditCodeVisible] = useState(false); // 编辑编码弹窗
    const [editingDoc, setEditingDoc] = useState<any | null>(null); // 正在编辑的文档
    const [newClassCode, setNewClassCode] = useState<string>(''); // 新的分类编码
    const [editLevelValues, setEditLevelValues] = useState<Record<number, string>>({}); // 编辑时的层级值
    const [editTemplateLevels, setEditTemplateLevels] = useState<Array<any>>([]); // 编辑时的模板层级
    const [editLevelOptions, setEditLevelOptions] = useState<Record<string, any[]>>({}); // 编辑时的层级选项
    const [editDocTypeId, setEditDocTypeId] = useState<number | null>(null); // 编辑时的文档类型ID
    const [editNumericId, setEditNumericId] = useState<string>(''); // 编辑时的数字序号（不可修改）

    useEffect(() => {
        fetchTemplates();
    }, []);

    useEffect(() => {
        if (viewTemplateId) {
            fetchDocumentsByTemplate();
        } else {
            setDocuments([]);
            setTotal(0);
        }
    }, [viewTemplateId, filters]);

    // 根据选择的模板查询文档列表
    const fetchDocumentsByTemplate = async () => {
        if (!viewTemplateId) return;

        setLoading(true);
        try {
            const response = await documentService.getClassCodes(viewTemplateId);
            setDocuments(response.data || []);
            setTotal(response.data?.length || 0);
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
        if (uploadMode === 'auto') {
            // AI自动解析模式
            setIsUploading(true);
            const { file, template_id } = values;

            const formData = new FormData();
            formData.append('file', file[0].originFileObj);
            if (template_id) {
                formData.append('template_id', template_id);
            }

            setUploadStatus('上传中...');

            try {
                documentService.uploadDocumentSSE(
                    formData,
                    (event: SSEEvent) => {
                        if (event.data) {
                            setUploadStatus(event.data);
                            message.info(event.data);
                        }
                    },
                    (error: Error) => {
                        message.error('上传失败: ' + error.message);
                        setUploadStatus('上传失败');
                        setIsUploading(false);
                    },
                    () => {
                        message.success('文档上传并处理完成');
                        setUploadVisible(false);
                        setUploadStatus('');
                        form.resetFields();
                        if (viewTemplateId) {
                            fetchDocumentsByTemplate();
                        }
                        setIsUploading(false);
                    }
                );
            } catch (error) {
                message.error('上传失败');
                setUploadStatus('上传失败');
                setIsUploading(false);
            }
        } else {
            // 手动创建模式（流式处理）
            setIsUploading(true);
            const { file, title, template_id, doc_type_id, class_code } = values;

            const formData = new FormData();
            formData.append('file', file[0].originFileObj);
            formData.append('title', title);
            formData.append('template_id', template_id);
            formData.append('doc_type_id', doc_type_id);
            formData.append('class_code', class_code);

            setUploadStatus('创建中...');

            try {
                documentService.createDocumentManuallySSE(
                    formData,
                    (event: SSEEvent) => {
                        if (event.data) {
                            setUploadStatus(event.data);
                            message.info(event.data);
                        }
                    },
                    (error: Error) => {
                        message.error('创建失败: ' + error.message);
                        setUploadStatus('创建失败');
                        setIsUploading(false);
                    },
                    () => {
                        message.success('文档创建完成');
                        setUploadVisible(false);
                        setUploadStatus('');
                        form.resetFields();
                        if (viewTemplateId) {
                            fetchDocumentsByTemplate();
                        }
                        setIsUploading(false);
                    }
                );
            } catch (error) {
                message.error('创建失败');
                setUploadStatus('创建失败');
                setIsUploading(false);
            }
        }
    };

    // 处理模板选择变化
    const handleTemplateChange = async (templateId: number) => {
        setSelectedTemplateId(templateId);
        form.setFieldsValue({ doc_type_id: undefined, class_code: undefined });
        setLevelValues({});
        setDocTypeId(null);

        if (uploadMode === 'manual' && templateId) {
            // 加载模板层级结构和值域选项（包括文档类型）
            try {
                const response = await documentService.getTemplateLevels(templateId);
                if (response.data) {
                    const data = response.data as any;
                    // 按 level 排序
                    const sortedLevels = (data.levels || []).sort((a: any, b: any) => a.level - b.level);
                    setTemplateLevels(sortedLevels);
                    setLevelOptions(data.level_options || {});
                }
            } catch (error) {
                message.error('获取模板层级失败');
            }
        }
    };

    // 处理层级值变化，动态构建分类编码
    const handleLevelChange = (level: number, value: string, isDocType: boolean = false, docTypeId?: number) => {
        const newLevelValues = { ...levelValues, [level]: value };
        setLevelValues(newLevelValues);

        // 如果是文档类型层，记录 doc_type_id
        if (isDocType && docTypeId) {
            setDocTypeId(docTypeId);
            form.setFieldValue('doc_type_id', docTypeId);
        }

        // 构建分类编码（按 level 顺序）
        const sortedLevels = [...templateLevels].sort((a, b) => a.level - b.level);
        const classCode = sortedLevels
            .map(lvl => newLevelValues[lvl.level] || '')
            .filter(v => v)
            .join('-');

        form.setFieldValue('class_code', classCode);
    };

    // 处理上传模式切换
    const handleUploadModeChange = (e: any) => {
        const mode = e.target.value;
        setUploadMode(mode);
        form.resetFields(['doc_type_id', 'class_code', 'title']);
        setTemplateLevels([]);
        setLevelOptions({});
        setLevelValues({});
        setDocTypeId(null);

        // 如果切换到手动模式且已选择模板，则加载相关数据
        if (mode === 'manual' && selectedTemplateId) {
            handleTemplateChange(selectedTemplateId);
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
            if (viewTemplateId) {
                fetchDocumentsByTemplate();
            }
        } catch (error) {
            message.error('分类失败');
        }
    };

    const handlePreview = async (record: Document) => {

    };

    const handleDelete = async (id: number) => {
        try {
            await documentService.deleteDocument(id);
            message.success('删除成功');
            if (viewTemplateId) {
                fetchDocumentsByTemplate();
            }
        } catch (error) {
            message.error('删除失败');
        }
    };

    // 处理编辑编码
    const handleEditCode = async (record: any) => {
        setEditingDoc(record);
        setNewClassCode(record.class_code || '');

        // 如果有模板ID，加载模板层级和解析现有编码
        if (viewTemplateId) {
            try {
                // 1. 加载模板层级结构
                const response = await documentService.getTemplateLevels(viewTemplateId);
                if (response.data) {
                    const data = response.data as any;
                    const sortedLevels = (data.levels || []).sort((a: any, b: any) => a.level - b.level);
                    setEditTemplateLevels(sortedLevels);
                    setEditLevelOptions(data.level_options || {});

                    // 2. 解析当前编码
                    const currentCode = record.class_code || '';
                    const codeParts = currentCode.split('-');

                    // 最后一部分是数字序号，不可修改
                    const numericId = codeParts[codeParts.length - 1] || '';
                    setEditNumericId(numericId);

                    // 前面的部分对应各个层级
                    const levelParts = codeParts.slice(0, -1);
                    const parsedLevelValues: Record<number, string> = {};

                    sortedLevels.forEach((level: any, index: number) => {
                        if (index < levelParts.length) {
                            parsedLevelValues[level.level] = levelParts[index];

                            // 如果是文档类型层，找到对应的 doc_type_id
                            if (level.is_doc_type) {
                                const levelCode = level.code;
                                const options = data.level_options[levelCode];
                                if (Array.isArray(options)) {
                                    const found = options.find((opt: any) => opt.name === levelParts[index]);
                                    if (found && found.doc_type_id) {
                                        setEditDocTypeId(found.doc_type_id);
                                    }
                                }
                            }
                        }
                    });

                    setEditLevelValues(parsedLevelValues);
                }
            } catch (error) {
                message.error('加载模板层级失败');
            }
        }

        setEditCodeVisible(true);
    };

    // 处理编辑时的层级变化
    const handleEditLevelChange = (level: number, value: string, isDocType: boolean = false, docTypeId?: number) => {
        const newLevelValues = { ...editLevelValues, [level]: value };
        setEditLevelValues(newLevelValues);

        // 如果是文档类型层，记录 doc_type_id
        if (isDocType && docTypeId) {
            setEditDocTypeId(docTypeId);
        }

        // 构建新的分类编码前缀（不包含数字序号）
        const sortedLevels = [...editTemplateLevels].sort((a, b) => a.level - b.level);
        const codeParts = sortedLevels
            .map(lvl => newLevelValues[lvl.level] || '')
            .filter(v => v);

        // 只保存前缀部分，不包含序号
        const codePrefix = codeParts.join('-');

        // 显示时拼接序号（仅用于预览）
        const finalCode = editNumericId ? `${codePrefix}-${editNumericId}` : codePrefix;
        setNewClassCode(finalCode);
    };

    // 保存编辑的编码
    const handleSaveClassCode = async () => {
        if (!editingDoc || !newClassCode) {
            message.error('请输入分类编码');
            return;
        }

        // 提取原编码的前缀部分（去掉最后一位序号）
        const originalCode = editingDoc.class_code || '';
        const originalParts = originalCode.split('-');
        const originalPrefix = originalParts.slice(0, -1).join('-');

        // 提取新编码的前缀部分
        const newParts = newClassCode.split('-');
        const newPrefix = newParts.slice(0, -1).join('-');

        // 检查前缀是否有变化
        if (originalPrefix === newPrefix) {
            message.info('编码未发生变化，无需更新');
            setEditCodeVisible(false);
            return;
        }

        try {
            // 只传前缀部分，后端会自动拼接原有序号
            await documentService.updateClassCode(editingDoc.id, newPrefix);
            message.success('分类编码更新成功');
            setEditCodeVisible(false);
            setEditingDoc(null);
            setNewClassCode('');
            setEditLevelValues({});
            setEditTemplateLevels([]);
            setEditLevelOptions({});
            setEditDocTypeId(null);
            setEditNumericId('');
            if (viewTemplateId) {
                fetchDocumentsByTemplate();
            }
        } catch (error) {
            message.error('更新失败');
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
            title: '文档ID',
            dataIndex: 'document_id',
            key: 'document_id',
            width: 80,
        },
        {
            title: '文档标题',
            dataIndex: 'title',
            key: 'title',
            ellipsis: true,
        },
        {
            title: '文件名',
            dataIndex: 'filename',
            key: 'filename',
            ellipsis: true,
        },
        {
            title: '分类编码',
            dataIndex: 'class_code',
            key: 'class_code',
            width: 200,
        },
        {
            title: '创建时间',
            dataIndex: 'created_at',
            key: 'created_at',
            width: 180,
            render: (text: string) => {
                if (!text) return '-';
                // 假设 text 是字符串格式的秒级时间戳（如 "1732000000"）
                const timestamp = Number(text);
                return new Date(timestamp * 1000).toLocaleString();
            },
        },
        {
            title: '操作',
            key: 'action',
            width: 250,
            render: (_: any, record: any) => (
                <Space>
                    <Button
                        type="link"
                        size="small"
                        icon={<EyeOutlined />}
                        onClick={() => {
                            const doc = {
                                id: record.document_id,
                                title: record.title,
                                original_filename: record.filename,
                                class_code: record.class_code,
                            };
                            handleViewDetail(doc as any);
                        }}
                    >
                        详情
                    </Button>
                    {record.class_code && (
                        <Button
                            type="link"
                            size="small"
                            onClick={() => {
                                const doc = {
                                    id: record.document_id,
                                    title: record.title,
                                    original_filename: record.filename,
                                    class_code: record.class_code,
                                };
                                handleEditCode(doc as any);
                            }}
                        >
                            编辑编码
                        </Button>
                    )}
                    <Button
                        type="link"
                        danger
                        size="small"
                        icon={<DeleteOutlined />}
                        onClick={() => handleDelete(record.document_id)}
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
                            placeholder="选择模板查看文档"
                            style={{ width: 250 }}
                            allowClear
                            value={viewTemplateId}
                            onChange={(value) => setViewTemplateId(value)}
                        >
                            {templates.map((template) => (
                                <Select.Option key={template.id} value={template.id}>
                                    {template.name}
                                </Select.Option>
                            ))}
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

                {!viewTemplateId ? (
                    <div style={{ textAlign: 'center', padding: '100px 0', color: '#999' }}>
                        <p style={{ fontSize: '16px' }}>请先选择模板以查看该模板下的文档</p>
                    </div>
                ) : (
                    <Table
                        columns={columns}
                        dataSource={documents}
                        loading={loading}
                        rowKey="document_id"
                        pagination={false}
                    />
                )}

                {/* 上传文档模态框 */}
                <Modal
                    title="上传文档"
                    open={uploadVisible}
                    onCancel={() => {
                        setUploadVisible(false);
                        setUploadStatus('');
                        form.resetFields();
                        setUploadMode('auto');
                    }}
                    footer={null}
                    width={600}
                >
                    <Form
                        form={form}
                        layout="vertical"
                        onFinish={handleUpload}
                    >
                        {/* 上传模式选择 */}
                        <Form.Item label="上传模式">
                            <Radio.Group value={uploadMode} onChange={handleUploadModeChange}>
                                <Radio value="auto">AI自动解析</Radio>
                                <Radio value="manual">手动创建</Radio>
                            </Radio.Group>
                        </Form.Item>

                        {/* 分类模板 */}
                        <Form.Item
                            required={true}
                            name="template_id"
                            label="分类模板"
                            rules={[{ required: true, message: '请选择分类模板' }]}
                        >
                            <Select
                                placeholder="选择分类模板"
                                onChange={handleTemplateChange}
                            >
                                {templates.map((template) => (
                                    <Select.Option key={template.id} value={template.id}>
                                        {template.name}
                                    </Select.Option>
                                ))}
                            </Select>
                        </Form.Item>

                        {/* 手动模式下的额外字段 */}
                        {uploadMode === 'manual' && (
                            <>
                                {/* 文档标题 - 可选 */}
                                <Form.Item
                                    name="title"
                                    label="文档标题"
                                >
                                    <Input placeholder="可选，不填则自动提取" />
                                </Form.Item>

                                {/* 隐藏的 doc_type_id 字段 */}
                                <Form.Item name="doc_type_id" hidden>
                                    <Input type="hidden" />
                                </Form.Item>

                                {/* 根据模板层级动态生成分类编码选择器 - 水平布局，不换行 */}
                                {templateLevels.length > 0 && (
                                    <Form.Item label="分类编码构建">
                                        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', flexWrap: 'nowrap', overflowX: 'auto' }}>
                                            {templateLevels.map((level, index) => {
                                                const levelCode = level.code;
                                                const options = levelOptions[levelCode];
                                                const isInputType = !options || options === null;
                                                const showSeparator = index < templateLevels.length - 1;
                                                const isDocType = level.is_doc_type;

                                                return (
                                                    <React.Fragment key={level.level}>
                                                        <div style={{ flex: '1 1 auto', minWidth: '150px', maxWidth: '250px' }}>
                                                            <div style={{ marginBottom: '4px', fontSize: '12px', color: '#666', whiteSpace: 'nowrap' }}>
                                                                {level.name}
                                                            </div>
                                                            {isInputType ? (
                                                                <Input
                                                                    placeholder={level.placeholder_example || `请输入${level.name}`}
                                                                    value={levelValues[level.level] || ''}
                                                                    onChange={(e) => handleLevelChange(level.level, e.target.value, isDocType)}
                                                                    style={{ width: '100%' }}
                                                                />
                                                            ) : (
                                                                <Select
                                                                    placeholder={`选择${level.name}`}
                                                                    value={levelValues[level.level] || undefined}
                                                                    onChange={(value) => {
                                                                        // 如果是文档类型层,需要查找对应的 doc_type_id
                                                                        let docTypeId: number | undefined;
                                                                        if (isDocType && Array.isArray(options)) {
                                                                            const selectedOption: any = options.find((opt: any) => opt.name === value);
                                                                            docTypeId = selectedOption?.doc_type_id;
                                                                        }
                                                                        handleLevelChange(level.level, value, isDocType, docTypeId);
                                                                    }}
                                                                    showSearch
                                                                    allowClear
                                                                    optionFilterProp="children"
                                                                    style={{ width: '100%' }}
                                                                >
                                                                    {Array.isArray(options) && options.map((option: any) => (
                                                                        <Select.Option key={option.name} value={option.name}>
                                                                            {option.description ? `${option.name} - ${option.description}` : option.name}
                                                                        </Select.Option>
                                                                    ))}
                                                                </Select>
                                                            )}
                                                        </div>
                                                        {showSeparator && (
                                                            <div style={{
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                paddingBottom: '2px',
                                                                fontSize: '16px',
                                                                color: '#999',
                                                                fontWeight: 'bold',
                                                                flexShrink: 0
                                                            }}>
                                                                -
                                                            </div>
                                                        )}
                                                    </React.Fragment>
                                                );
                                            })}
                                        </div>
                                    </Form.Item>
                                )}

                                {/* 分类编码（自动生成） */}
                                <Form.Item
                                    name="class_code"
                                    label="最终编码"
                                >
                                    <Input
                                        placeholder="根据上面层级自动生成"
                                        disabled
                                        style={{
                                            fontWeight: 'bold',
                                            fontSize: '14px',
                                            color: '#1890ff'
                                        }}
                                    />
                                </Form.Item>
                            </>
                        )}

                        {/* 文件上传 */}
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

                        {uploadStatus && (
                            <div className="mb-4">
                                <div className="text-sm text-gray-600 mb-1">{uploadStatus}</div>
                            </div>
                        )}

                        <Form.Item>
                            <Space>
                                <Button type="primary" htmlType="submit" loading={isUploading}>
                                    {uploadMode === 'auto' ? '上传' : '创建'}
                                </Button>
                                <Button onClick={() => {
                                    setUploadVisible(false);
                                    setUploadStatus('');
                                    form.resetFields();
                                    setUploadMode('auto');
                                }}>
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

                {/* 编辑分类编码弹窗 */}
                <Modal
                    title="编辑分类编码"
                    open={editCodeVisible}
                    onOk={handleSaveClassCode}
                    onCancel={() => {
                        setEditCodeVisible(false);
                        setEditingDoc(null);
                        setNewClassCode('');
                        setEditLevelValues({});
                        setEditTemplateLevels([]);
                        setEditLevelOptions({});
                        setEditDocTypeId(null);
                        setEditNumericId('');
                    }}
                    okText="保存"
                    cancelText="取消"
                    width={800}
                >
                    {editingDoc && (
                        <div className="space-y-4">
                            <div>
                                <div className="text-sm text-gray-600 mb-1">文档名称：</div>
                                <div className="font-medium">{editingDoc.title || editingDoc.original_filename || editingDoc.filename}</div>
                            </div>
                            <div>
                                <div className="text-sm text-gray-600 mb-1">原始编码：</div>
                                <div className="font-medium text-gray-800">{editingDoc.class_code}</div>
                            </div>

                            {/* 水平布局的编码构建器 */}
                            {editTemplateLevels.length > 0 && (
                                <div>
                                    <div className="text-sm text-gray-600 mb-2">编辑编码：</div>
                                    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '8px', flexWrap: 'nowrap', overflowX: 'auto' }}>
                                        {editTemplateLevels.map((level, index) => {
                                            const levelCode = level.code;
                                            const options = editLevelOptions[levelCode];
                                            const isInputType = !options || options === null;
                                            const showSeparator = index < editTemplateLevels.length;
                                            const isDocType = level.is_doc_type;

                                            return (
                                                <React.Fragment key={level.level}>
                                                    <div style={{ flex: '1 1 auto', minWidth: '150px', maxWidth: '250px' }}>
                                                        <div style={{ marginBottom: '4px', fontSize: '12px', color: '#666', whiteSpace: 'nowrap' }}>
                                                            {level.name}
                                                        </div>
                                                        {isInputType ? (
                                                            <Input
                                                                placeholder={level.placeholder_example || `请输入${level.name}`}
                                                                value={editLevelValues[level.level] || ''}
                                                                onChange={(e) => handleEditLevelChange(level.level, e.target.value, isDocType)}
                                                                style={{ width: '100%' }}
                                                            />
                                                        ) : (
                                                            <Select
                                                                placeholder={`选择${level.name}`}
                                                                value={editLevelValues[level.level] || undefined}
                                                                onChange={(value) => {
                                                                    // 如果是文档类型层,需要查找对应的 doc_type_id
                                                                    let docTypeId: number | undefined;
                                                                    if (isDocType && Array.isArray(options)) {
                                                                        const selectedOption: any = options.find((opt: any) => opt.name === value);
                                                                        docTypeId = selectedOption?.doc_type_id;
                                                                    }
                                                                    handleEditLevelChange(level.level, value, isDocType, docTypeId);
                                                                }}
                                                                showSearch
                                                                allowClear
                                                                optionFilterProp="children"
                                                                style={{ width: '100%' }}
                                                            >
                                                                {Array.isArray(options) && options.map((option: any) => (
                                                                    <Select.Option key={option.name} value={option.name}>
                                                                        {option.description ? `${option.name} - ${option.description}` : option.name}
                                                                    </Select.Option>
                                                                ))}
                                                            </Select>
                                                        )}
                                                    </div>
                                                    {showSeparator && (
                                                        <div style={{
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            paddingBottom: '2px',
                                                            fontSize: '16px',
                                                            color: '#999',
                                                            fontWeight: 'bold',
                                                            flexShrink: 0
                                                        }}>
                                                            -
                                                        </div>
                                                    )}
                                                </React.Fragment>
                                            );
                                        })}
                                        {/* 数字序号（不可修改） */}
                                        <div style={{ flex: '0 0 auto', minWidth: '100px', maxWidth: '150px' }}>
                                            <div style={{ marginBottom: '4px', fontSize: '12px', color: '#666', whiteSpace: 'nowrap' }}>
                                                序号（系统生成）
                                            </div>
                                            <Input
                                                value={editNumericId}
                                                disabled
                                                style={{ width: '100%', backgroundColor: '#f5f5f5', color: '#999' }}
                                            />
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* 最终编码预览 */}
                            <div>
                                <div className="text-sm text-gray-600 mb-1">新编码：</div>
                                <div className="font-medium text-blue-600" style={{ fontSize: '16px' }}>{newClassCode}</div>
                            </div>
                        </div>
                    )}
                </Modal>
            </Card>
        </div>
    );
};

export default DocumentPage;