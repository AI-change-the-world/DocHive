import { useState, useRef, useEffect } from 'react';
import {
    Input,
    Button,
    Card,
    Empty,
    Spin,
    message,
    Tag,
    Typography,
    Space,
    Divider,
    Modal,
    Select,
    Collapse,
    Badge,
    Alert,
    List,
    Radio,
} from 'antd';
import {
    SendOutlined,
    StopOutlined,
    FileTextOutlined,
    RobotOutlined,
    LoadingOutlined,
    SearchOutlined,
    DatabaseOutlined,
    FilterOutlined,
    BulbOutlined,
    CheckCircleOutlined,
    ClockCircleOutlined,
    EyeOutlined,
    MergeOutlined,
    FileSearchOutlined,
    InfoCircleOutlined,
    ThunderboltOutlined,
    ApiOutlined,
    DeleteOutlined,
} from '@ant-design/icons';
import type { QADocumentReference, QARequest, TemplateSelection } from '../../types';
import { qaService } from '../../services/qa';
import { documentService } from '../../services/document';
import ReactMarkdown from 'react-markdown';
import { v4 as uuidv4 } from 'uuid';
import html2canvas from 'html2canvas';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;

// Agent处理阶段定义
interface AgentStage {
    stage: string;
    label: string;
    icon: React.ReactNode;
    status: 'wait' | 'process' | 'finish' | 'error';
    message?: string;
    timestamp?: Date;
    result?: StageResult;
}

// 阶段结果数据结构
interface StageResult {
    // 通用字段
    document_ids?: number[];
    count?: number;
    documents?: any[];

    // 任务规划阶段
    execution_pattern?: string;
    execution_plan?: any[];
    reasoning?: string;

    // 工具/智能体执行结果
    tool_results?: any[];
    agent_results?: any[];
}

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    references?: QADocumentReference[];
    timestamp: Date;
    agentStages?: AgentStage[];
    executionPattern?: string;  // 执行模式
}

export default function QABetaPage() {
    const [question, setQuestion] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [currentAnswer, setCurrentAnswer] = useState('');
    const [currentReferences, setCurrentReferences] = useState<QADocumentReference[]>([]);
    const [agentStages, setAgentStages] = useState<AgentStage[]>([]);
    const [executionPattern, setExecutionPattern] = useState<string>('');

    // 会话管理
    const [sessionId, setSessionId] = useState<string>(uuidv4());

    // 用户干预
    const [showUserInputModal, setShowUserInputModal] = useState(false);
    const [userInputPrompt, setUserInputPrompt] = useState('');
    const [userInputType, setUserInputType] = useState('');
    const [userInputOptions, setUserInputOptions] = useState<any[]>([]);
    const [userInputDocuments, setUserInputDocuments] = useState<any[]>([]);
    const [selectedUserInput, setSelectedUserInput] = useState<any>(null);

    // 使用ref保存最新值
    const currentAnswerRef = useRef('');
    const currentReferencesRef = useRef<QADocumentReference[]>([]);
    const agentStagesRef = useRef<AgentStage[]>([]);
    const executionPatternRef = useRef('');

    const [templateId, setTemplateId] = useState<number | undefined>(undefined);
    const [templates, setTemplates] = useState<TemplateSelection[]>([]);
    const [loadingTemplates, setLoadingTemplates] = useState(false);

    // 文档预览相关
    const [previewDocId, setPreviewDocId] = useState<number | null>(null);
    const [showPreviewModal, setShowPreviewModal] = useState(false);
    const [previewDocument, setPreviewDocument] = useState<any>(null);
    const [loadingPreview, setLoadingPreview] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);
    const messagesContainerRef = useRef<HTMLDivElement>(null);

    // 自动滚动
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, currentAnswer]);

    // 获取模板列表
    const fetchTemplates = async () => {
        setLoadingTemplates(true);
        try {
            const response = await qaService.getAllTemplates();
            if (response.data) {
                setTemplates(response.data);
                if (!templateId && response.data.length > 0) {
                    setTemplateId(response.data[0].template_id);
                }
            }
        } catch (error) {
            message.error('获取模板列表失败');
        } finally {
            setLoadingTemplates(false);
        }
    };

    useEffect(() => {
        fetchTemplates();
    }, []);

    // 根据执行计划初始化阶段
    const initializeStagesFromPlan = (plan: Array<{ step: number, type: string, name: string, description: string }>): AgentStage[] => {
        return plan.map((item, index) => ({
            stage: `step_${item.step}`,
            label: item.description,
            icon: item.type === 'tool' ? <ApiOutlined /> : <SearchOutlined />,
            status: index === 0 ? 'process' : 'wait',
            message: index === 0 ? `正在${item.description}...` : undefined,
            timestamp: index === 0 ? new Date() : undefined,
        }));
    };

    // 更新阶段状态
    const updateStageStatus = (
        stages: AgentStage[],
        targetStage: string,
        status: 'process' | 'finish' | 'error',
        message?: string,
        result?: any
    ): AgentStage[] => {
        const stageIndex = stages.findIndex(s => s.stage === targetStage);
        if (stageIndex === -1) return stages;

        return stages.map((stage, idx) => {
            if (idx === stageIndex) {
                return {
                    ...stage,
                    status,
                    message,
                    result,
                    timestamp: new Date(),
                };
            } else if (idx === stageIndex + 1 && status === 'finish') {
                return {
                    ...stage,
                    status: 'process',
                    message: `正在${stage.label}...`,
                    timestamp: new Date(),
                };
            }
            return stage;
        });
    };

    // 预览文档
    const handlePreviewDocument = async (docId: number) => {
        setPreviewDocId(docId);
        setShowPreviewModal(true);
        setLoadingPreview(true);

        try {
            const response = await documentService.getDocument(docId);
            if (response.data) {
                setPreviewDocument(response.data);
            }
        } catch (error) {
            message.error('获取文档详情失败');
        } finally {
            setLoadingPreview(false);
        }
    };

    // 发送问题
    const handleAsk = async (userInput?: any) => {
        if (!userInput && !question.trim()) {
            message.warning('请输入问题');
            return;
        }

        if (!templateId) {
            message.warning('请选择模板');
            return;
        }

        // 如果不是用户干预，添加用户消息
        if (!userInput) {
            const userMessage: Message = {
                id: Date.now().toString(),
                type: 'user',
                content: question,
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, userMessage]);
        }

        // 重置状态
        setCurrentAnswer('');
        setCurrentReferences([]);
        setIsStreaming(true);
        setExecutionPattern('');

        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];
        executionPatternRef.current = '';

        setAgentStages([]);

        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        try {
            const requestData: QARequest = {
                question: userInput ? '' : question.trim(),
                template_id: templateId,
                top_k: 5,
                session_id: sessionId,  // 传入session_id
                user_input: userInput,   // 传入用户输入
            };

            // 使用新的beta接口
            const streamUrl = qaService.getBetaStreamUrl();
            const response = await fetch(streamUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                },
                body: JSON.stringify(requestData),
                signal: abortController.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            if (!response.body) {
                throw new Error('响应体为空');
            }

            // 逐行读取SSE流
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim() || !line.startsWith('data:')) continue;

                    try {
                        const jsonStr = line.substring(5).trim();
                        const eventData = JSON.parse(jsonStr);
                        console.log('[收到SSE事件-Beta]', eventData.event, eventData);

                        switch (eventData.event) {
                            case 'plan':
                                // 收到执行计划
                                const plan = eventData.data?.execution_plan || [];
                                const pattern = eventData.data?.execution_pattern || '';
                                const reasoning = eventData.data?.reasoning || '';

                                console.log('[执行计划]', { pattern, plan, reasoning });

                                setExecutionPattern(pattern);
                                executionPatternRef.current = pattern;

                                const initialStages = initializeStagesFromPlan(plan);
                                setAgentStages(initialStages);
                                agentStagesRef.current = initialStages;
                                break;

                            case 'stage_start':
                                const stage = eventData.data?.stage || '';
                                const msg = eventData.data?.message || '处理中...';

                                setAgentStages(prev => {
                                    if (prev.length === 0) return prev;
                                    return updateStageStatus(prev, stage, 'process', msg);
                                });
                                break;

                            case 'stage_complete':
                                const completedStage = eventData.data?.stage;
                                const resultData = eventData.data?.result;
                                const completeMsg = eventData.data?.message;

                                setAgentStages(prev => {
                                    if (prev.length === 0) return prev;
                                    const updated = updateStageStatus(prev, completedStage, 'finish', completeMsg, resultData);
                                    agentStagesRef.current = updated;
                                    return updated;
                                });
                                break;

                            case 'hint':
                                // 收到提示信息（检索结果过多/过少）
                                console.log('[收到提示]', eventData.data);

                                const hintMessage = eventData.data?.message || '';
                                const hintDocs = eventData.data?.documents || [];

                                // 将提示消息显示为助手回复
                                setCurrentAnswer(hintMessage);
                                currentAnswerRef.current = hintMessage;

                                // 显示相关文档
                                if (hintDocs.length > 0) {
                                    setCurrentReferences(hintDocs);
                                    currentReferencesRef.current = hintDocs;
                                }
                                break;

                            case 'user_input_request':
                                // 旧的用户输入请求（已废弃）
                                console.log('[请求用户输入-已废弃]', eventData.data);
                                break;

                            case 'documents':
                                const refs = eventData.data?.documents || [];
                                setCurrentReferences(refs);
                                currentReferencesRef.current = refs;
                                break;

                            case 'answer':
                                const newContent = (eventData.data?.content || '');
                                setCurrentAnswer(prev => {
                                    const updated = prev + newContent;
                                    currentAnswerRef.current = updated;
                                    return updated;
                                });
                                break;

                            case 'complete':
                                console.log('[收到complete事件]', {
                                    currentAnswer: currentAnswerRef.current,
                                    referencesCount: currentReferencesRef.current.length,
                                    stagesCount: agentStagesRef.current.length,
                                    pattern: executionPatternRef.current,
                                });

                                const completedStages = agentStagesRef.current.map(s => ({
                                    ...s,
                                    status: (s.status === 'error' ? 'error' : 'finish') as 'wait' | 'process' | 'finish' | 'error',
                                }));

                                const finalAnswer = currentAnswerRef.current;
                                const finalReferences = [...currentReferencesRef.current];
                                const finalPattern = executionPatternRef.current;

                                const newMessage: Message = {
                                    id: Date.now().toString(),
                                    type: 'assistant',
                                    content: finalAnswer || '抱歉，没有找到相关答案。',
                                    references: finalReferences,
                                    timestamp: new Date(),
                                    agentStages: completedStages,
                                    executionPattern: finalPattern,
                                };

                                setMessages(prev => [...prev, newMessage]);

                                setTimeout(() => {
                                    setIsStreaming(false);
                                    setCurrentAnswer('');
                                    setCurrentReferences([]);
                                    setAgentStages([]);
                                    setExecutionPattern('');
                                    currentAnswerRef.current = '';
                                    currentReferencesRef.current = [];
                                    agentStagesRef.current = [];
                                    executionPatternRef.current = '';
                                }, 200);
                                break;

                            case 'error':
                                message.error(eventData.data?.message || '问答失败');
                                setIsStreaming(false);
                                break;
                        }
                    } catch (parseError) {
                        console.error('[解析SSE数据失败]', parseError, line);
                    }
                }
            }

            setQuestion('');

        } catch (error: any) {
            if (!abortController.signal.aborted) {
                message.error(`问答失败: ${error.message}`);
            }
            setIsStreaming(false);
        }
    };

    // 中断请求
    const handleStop = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsStreaming(false);
        message.info('已中断问答');
    };

    // 清空对话
    const handleClear = () => {
        setMessages([]);
        setCurrentAnswer('');
        setCurrentReferences([]);
        setAgentStages([]);
        setExecutionPattern('');
        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];
        executionPatternRef.current = '';

        // 生成新的session_id
        setSessionId(uuidv4());
    };

    // 导出对话历史为图片
    const handleExportChat = async () => {
        if (!messagesContainerRef.current) {
            message.error('无法导出：未找到对话容器');
            return;
        }

        if (messages.length === 0) {
            message.warning('暂无对话历史可导出');
            return;
        }

        try {
            message.loading({ content: '正在生成图片...', key: 'export', duration: 0 });

            // 使用html2canvas截取对话区域
            const canvas = await html2canvas(messagesContainerRef.current, {
                backgroundColor: '#f5f5f5',
                scale: 2, // 提高清晰度
                logging: false,
                useCORS: true,
                allowTaint: true,
                windowWidth: messagesContainerRef.current.scrollWidth,
                windowHeight: messagesContainerRef.current.scrollHeight,
            });

            // 转换为图片并下载
            canvas.toBlob((blob) => {
                if (blob) {
                    const url = URL.createObjectURL(blob);
                    const link = document.createElement('a');
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
                    link.download = `对话历史_${timestamp}.png`;
                    link.href = url;
                    link.click();
                    URL.revokeObjectURL(url);
                    message.success({ content: '导出成功！', key: 'export' });
                } else {
                    message.error({ content: '导出失败', key: 'export' });
                }
            }, 'image/png');
        } catch (error) {
            console.error('导出失败:', error);
            message.error({ content: '导出失败，请重试', key: 'export' });
        }
    };

    // 提交用户输入
    const handleSubmitUserInput = () => {
        if (!selectedUserInput) {
            message.warning('请选择或输入内容');
            return;
        }

        setShowUserInputModal(false);

        // 添加用户选择的消息
        const userMessage: Message = {
            id: Date.now().toString(),
            type: 'user',
            content: typeof selectedUserInput === 'string' ? selectedUserInput : JSON.stringify(selectedUserInput),
            timestamp: new Date(),
        };
        setMessages(prev => [...prev, userMessage]);

        // 使用同一个session_id继续执行
        handleAsk(selectedUserInput);
    };

    // 渲染执行模式标签
    const renderExecutionPattern = (pattern: string) => {
        const patternConfig: Record<string, { color: string; label: string; icon: React.ReactNode }> = {
            'tool_only': { color: 'purple', label: '仅工具调用', icon: <ApiOutlined /> },
            'agent_only': { color: 'blue', label: '仅智能体', icon: <RobotOutlined /> },
            'agent_chain': { color: 'green', label: '智能体链', icon: <MergeOutlined /> },
            'hybrid': { color: 'orange', label: '混合模式', icon: <ThunderboltOutlined /> },
            'llm_direct': { color: 'cyan', label: 'LLM直答', icon: <BulbOutlined /> },
        };

        const config = patternConfig[pattern] || { color: 'default', label: pattern, icon: <InfoCircleOutlined /> };

        return (
            <Tag color={config.color} icon={config.icon}>
                {config.label}
            </Tag>
        );
    };

    // 渲染阶段结果详情
    const renderStageResult = (stage: AgentStage) => {
        if (!stage.result) return null;

        const { execution_pattern, execution_plan, reasoning, tool_results, agent_results, documents, document_ids } = stage.result;

        return (
            <div className="mt-2 space-y-2">
                {/* 执行计划 */}
                {execution_plan && (
                    <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                        <Text strong className="text-xs text-blue-700">📋 执行计划</Text>
                        {reasoning && (
                            <div className="text-xs text-gray-600 mt-1 mb-2 italic">
                                💭 {reasoning}
                            </div>
                        )}
                        <div className="mt-2 space-y-1">
                            {execution_plan.map((step: any, idx: number) => (
                                <div key={idx} className="text-xs flex items-start space-x-2">
                                    <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px]">
                                        {step.step}
                                    </span>
                                    <div className="flex-1">
                                        <span className="font-medium">
                                            {step.type === 'tool' ? '🔧' : '🤖'} {step.name}
                                        </span>
                                        <span className="text-gray-600 ml-2">{step.description}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* 工具执行结果 */}
                {tool_results && tool_results.length > 0 && (
                    <div className="p-3 bg-purple-50 rounded-lg border border-purple-200">
                        <Text strong className="text-xs text-purple-700">✅ 工具执行结果 ({tool_results.length})</Text>
                        <div className="mt-2 space-y-2">
                            {tool_results.map((tr: any, idx: number) => (
                                <div key={idx} className="p-2 bg-white rounded border">
                                    <div className="text-xs">
                                        <Text strong>{tr.tool_name}</Text>
                                        {tr.description && <Text className="ml-2 text-gray-500">- {tr.description}</Text>}
                                    </div>
                                    <pre className="text-xs mt-1 text-gray-600 max-h-32 overflow-auto">
                                        {JSON.stringify(tr.result, null, 2)}
                                    </pre>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* 文档列表 */}
                {documents && documents.length > 0 && (
                    <div className="p-3 bg-green-50 rounded-lg border border-green-200">
                        <Text strong className="text-xs text-green-700">📚 检索到 {documents.length} 篇文档</Text>
                        <div className="mt-2 flex flex-wrap gap-1">
                            {documents.slice(0, 10).map((doc: any, idx: number) => (
                                <Tag
                                    key={idx}
                                    color="green"
                                    className="cursor-pointer"
                                    onClick={() => handlePreviewDocument(doc.document_id)}
                                >
                                    #{doc.document_id}
                                </Tag>
                            ))}
                        </div>
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <div className="flex flex-wrap items-center gap-2">
                    <ThunderboltOutlined className="text-2xl text-purple-600" />
                    <Title level={3} className="!mb-0 !text-lg">智能体问答 - Beta</Title>
                    <Tag color="purple">V2架构</Tag>
                </div>
                <div className="flex items-center space-x-2">
                    {messages.length > 0 && (
                        <>
                            <Button
                                size="small"
                                icon={<FileTextOutlined />}
                                onClick={handleExportChat}
                            >
                                导出对话
                            </Button>
                            <Button size="small" onClick={handleClear} danger icon={<DeleteOutlined />}>
                                清空对话
                            </Button>
                        </>
                    )}
                </div>
            </div>

            {/* 消息列表 */}
            <div ref={messagesContainerRef} className="flex-1 overflow-y-auto mb-4 space-y-4">
                {messages.length === 0 && !isStreaming && (
                    <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                            <div className="text-center">
                                <Text type="secondary">使用全新的V2架构，支持智能路由和混合调用</Text>
                            </div>
                        }
                    />
                )}

                {messages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <Card
                            className={`w-full md:max-w-[85%] lg:max-w-[80%] ${msg.type === 'user'
                                ? 'bg-primary-50 border-primary-200'
                                : 'bg-white border-gray-200'
                                }`}
                        >
                            <div className="flex items-start space-x-2">
                                <div className="flex-shrink-0">
                                    {msg.type === 'user' ? (
                                        <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center text-white font-medium">
                                            我
                                        </div>
                                    ) : (
                                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white">
                                            <ThunderboltOutlined />
                                        </div>
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    {msg.type === 'user' ? (
                                        <Paragraph className="!mb-0">{msg.content}</Paragraph>
                                    ) : (
                                        <>
                                            {/* 执行模式 */}
                                            {msg.executionPattern && (
                                                <div className="mb-3">
                                                    {renderExecutionPattern(msg.executionPattern)}
                                                </div>
                                            )}

                                            {/* Agent处理阶段 */}
                                            {msg.agentStages && msg.agentStages.length > 0 && (
                                                <Collapse
                                                    ghost
                                                    size="small"
                                                    className="mb-3"
                                                    items={[{
                                                        key: 'agent-stages',
                                                        label: (
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <BulbOutlined className="text-purple-500" />
                                                                <Text strong className="text-sm">执行过程</Text>
                                                                <Badge
                                                                    count={msg.agentStages.filter(s => s.status === 'finish').length}
                                                                    showZero
                                                                    style={{ backgroundColor: '#52c41a' }}
                                                                />
                                                            </div>
                                                        ),
                                                        children: (
                                                            <Space direction="vertical" className="w-full" size="small">
                                                                {msg.agentStages.map((stage, idx) => (
                                                                    <Card
                                                                        key={idx}
                                                                        size="small"
                                                                        className={`${stage.status === 'finish' ? 'bg-green-50 border-green-200' :
                                                                            stage.status === 'process' ? 'bg-blue-50 border-blue-200' :
                                                                                'bg-gray-50 border-gray-200'
                                                                            }`}
                                                                    >
                                                                        <div className="flex flex-wrap items-start justify-between gap-2">
                                                                            <div className="flex items-start space-x-2 flex-1 min-w-0">
                                                                                <div className="flex-shrink-0">{stage.icon}</div>
                                                                                <div className="flex-1 min-w-0">
                                                                                    <Text strong className="text-sm break-words">{stage.label}</Text>
                                                                                    {stage.message && (
                                                                                        <div className="text-xs text-gray-500 mt-1 break-words">
                                                                                            {stage.message}
                                                                                        </div>
                                                                                    )}
                                                                                    {renderStageResult(stage)}
                                                                                </div>
                                                                            </div>
                                                                            {stage.status === 'finish' && (
                                                                                <CheckCircleOutlined className="text-green-500" />
                                                                            )}
                                                                            {stage.status === 'process' && (
                                                                                <LoadingOutlined className="text-blue-500" />
                                                                            )}
                                                                        </div>
                                                                    </Card>
                                                                ))}
                                                            </Space>
                                                        ),
                                                    }]}
                                                />
                                            )}

                                            {/* 答案内容 */}
                                            <div className="prose prose-sm max-w-none">
                                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                                            </div>

                                            {/* 参考文档 */}
                                            {msg.references && msg.references.length > 0 && (
                                                <>
                                                    <Divider className="my-3" />
                                                    <div>
                                                        <Text strong className="text-gray-600 mb-2 block">
                                                            <FileTextOutlined className="mr-1" />
                                                            参考文档 ({msg.references.length})
                                                        </Text>
                                                        <Space direction="vertical" className="w-full">
                                                            {msg.references.map((ref, idx) => (
                                                                <Card
                                                                    key={idx}
                                                                    size="small"
                                                                    className="bg-gray-50 hover:bg-gray-100 transition-colors cursor-pointer"
                                                                    onClick={() => handlePreviewDocument(ref.document_id)}
                                                                >
                                                                    <div className="flex flex-col sm:flex-row items-start gap-2">
                                                                        <div className="flex-1 min-w-0">
                                                                            <div className="flex flex-wrap items-center gap-2">
                                                                                <Badge count={idx + 1} style={{ backgroundColor: '#1890ff' }} />
                                                                                <Text strong className="text-sm break-words">{ref.title}</Text>
                                                                                <EyeOutlined className="text-blue-500" />
                                                                            </div>
                                                                            <Paragraph className="!mb-0 mt-2 text-xs text-gray-600 break-words" ellipsis={{ rows: 2 }}>
                                                                                {ref.snippet}
                                                                            </Paragraph>
                                                                        </div>
                                                                        {ref.score !== undefined && (
                                                                            <Tag color="blue" className="flex-shrink-0">
                                                                                {(ref.score * 100).toFixed(0)}%
                                                                            </Tag>
                                                                        )}
                                                                    </div>
                                                                </Card>
                                                            ))}
                                                        </Space>
                                                    </div>
                                                </>
                                            )}
                                        </>
                                    )}
                                    <Text type="secondary" className="text-xs block mt-2">
                                        {msg.timestamp.toLocaleTimeString()}
                                    </Text>
                                </div>
                            </div>
                        </Card>
                    </div>
                ))}

                {/* 流式回答 */}
                {isStreaming && (
                    <div className="flex justify-start">
                        <Card className="w-full md:max-w-[85%] lg:max-w-[80%] bg-white border-purple-200 shadow-md">
                            <div className="flex items-start space-x-2">
                                <div className="flex-shrink-0">
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center text-white">
                                        <Spin indicator={<LoadingOutlined spin />} size="small" />
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    {/* 执行模式 */}
                                    {executionPattern && (
                                        <div className="mb-3">
                                            {renderExecutionPattern(executionPattern)}
                                        </div>
                                    )}

                                    {/* Agent处理阶段进度 */}
                                    {agentStages.length > 0 && (
                                        <div className="mb-3 p-3 bg-purple-50 rounded-lg border border-purple-200">
                                            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                                                <Text strong className="text-sm text-purple-700">
                                                    <ThunderboltOutlined className="mr-1" />
                                                    智能体正在执行...
                                                </Text>
                                                <Badge
                                                    count={`${agentStages.filter(s => s.status === 'finish').length}/${agentStages.length}`}
                                                    style={{ backgroundColor: '#722ed1' }}
                                                />
                                            </div>
                                            <Space direction="vertical" className="w-full" size="small">
                                                {agentStages.map((stage, idx) => (
                                                    <Card
                                                        key={idx}
                                                        size="small"
                                                        className={`${stage.status === 'finish' ? 'bg-green-50 border-green-200' :
                                                            stage.status === 'process' ? 'bg-white border-purple-300' :
                                                                'bg-gray-50 border-gray-200'
                                                            }`}
                                                    >
                                                        <div className="flex flex-wrap items-start justify-between gap-2">
                                                            <div className="flex items-start space-x-2 flex-1 min-w-0">
                                                                <div className="flex-shrink-0">{stage.icon}</div>
                                                                <div className="flex-1 min-w-0">
                                                                    <Text strong className="text-sm break-words">{stage.label}</Text>
                                                                    {stage.message && (
                                                                        <div className="text-xs text-gray-500 mt-1 break-words">
                                                                            {stage.message}
                                                                        </div>
                                                                    )}
                                                                    {renderStageResult(stage)}
                                                                </div>
                                                            </div>
                                                            {stage.status === 'finish' && (
                                                                <CheckCircleOutlined className="text-green-500" />
                                                            )}
                                                            {stage.status === 'process' && (
                                                                <LoadingOutlined className="text-purple-500" />
                                                            )}
                                                        </div>
                                                    </Card>
                                                ))}
                                            </Space>
                                        </div>
                                    )}

                                    {/* 参考文档 */}
                                    {currentReferences.length > 0 && (
                                        <>
                                            <Divider className="my-3" orientation="left">
                                                <Text strong className="text-gray-600 text-sm">
                                                    <FileTextOutlined className="mr-1" />
                                                    检索到 {currentReferences.length} 篇相关文档
                                                </Text>
                                            </Divider>
                                            <Space direction="vertical" className="w-full mb-3">
                                                {currentReferences.map((ref, idx) => (
                                                    <Card
                                                        key={idx}
                                                        size="small"
                                                        className="bg-gradient-to-r from-gray-50 to-purple-50 border-purple-200 hover:shadow-md transition-shadow cursor-pointer"
                                                        onClick={() => handlePreviewDocument(ref.document_id)}
                                                    >
                                                        <div className="flex flex-col sm:flex-row items-start gap-2">
                                                            <div className="flex-1 min-w-0">
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    <Badge count={idx + 1} style={{ backgroundColor: '#722ed1' }} />
                                                                    <Text strong className="text-sm break-words">{ref.title}</Text>
                                                                    <EyeOutlined className="text-purple-500" />
                                                                </div>
                                                                <Paragraph className="!mb-0 mt-2 text-xs text-gray-600 break-words" ellipsis={{ rows: 2 }}>
                                                                    {ref.snippet}
                                                                </Paragraph>
                                                            </div>
                                                            {ref.score !== undefined && (
                                                                <Tag color="purple" className="flex-shrink-0">
                                                                    {(ref.score * 100).toFixed(0)}%
                                                                </Tag>
                                                            )}
                                                        </div>
                                                    </Card>
                                                ))}
                                            </Space>
                                        </>
                                    )}

                                    {/* 流式答案 */}
                                    {currentAnswer && (
                                        <>
                                            <Divider className="my-3" orientation="left">
                                                <Text strong className="text-gray-600 text-sm">
                                                    <CheckCircleOutlined className="mr-1 text-green-500" />
                                                    AI回答
                                                </Text>
                                            </Divider>
                                            <div className="prose prose-sm max-w-none">
                                                <ReactMarkdown>{currentAnswer}</ReactMarkdown>
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>
                        </Card>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* 输入区域 */}
            <Card className="shadow-md">
                <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm text-gray-600 whitespace-nowrap">模板:</span>
                        <Select
                            size="small"
                            // className="flex-1 min-w-[150px]"
                            placeholder="选择模板"
                            value={templateId}
                            onChange={setTemplateId}
                            loading={loadingTemplates}
                            showSearch
                            optionFilterProp="children"
                        >
                            {templates.map(template => (
                                <Option key={template.template_id} value={template.template_id}>
                                    {template.template_name}
                                </Option>
                            ))}
                        </Select>
                    </div>
                    <TextArea
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder="请输入您的问题..."
                        autoSize={{ minRows: 2, maxRows: 6 }}
                        disabled={isStreaming}
                        onPressEnter={(e) => {
                            if (e.shiftKey) return;
                            e.preventDefault();
                            handleAsk();
                        }}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <Text type="secondary" className="text-xs hidden sm:inline">
                            按 Enter 发送，Shift + Enter 换行
                        </Text>
                        <Space className="ml-auto">
                            {isStreaming ? (
                                <Button type="primary" danger icon={<StopOutlined />} onClick={handleStop} size="small">
                                    停止生成
                                </Button>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<SendOutlined />}
                                    onClick={() => handleAsk()}
                                    disabled={!question.trim() || !templateId}
                                    size="small"
                                    style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}
                                >
                                    发送问题
                                </Button>
                            )}
                        </Space>
                    </div>
                </div>
            </Card>

            {/* 文档预览模态框 */}
            <Modal
                title={
                    <div className="flex items-center space-x-2">
                        <FileTextOutlined className="text-blue-500" />
                        <span>文档预览</span>
                    </div>
                }
                open={showPreviewModal}
                onCancel={() => {
                    setShowPreviewModal(false);
                    setPreviewDocument(null);
                }}
                footer={null}
                width={800}
            >
                {loadingPreview ? (
                    <div className="text-center py-8">
                        <Spin />
                    </div>
                ) : previewDocument ? (
                    <div className="space-y-4">
                        <div>
                            <Text strong>文档ID:</Text> <Tag color="blue">#{previewDocument.id}</Tag>
                        </div>
                        <div>
                            <Text strong>标题:</Text>
                            <div className="mt-1">
                                <Text>{previewDocument.title}</Text>
                            </div>
                        </div>
                        <div>
                            <Text strong>文件名:</Text>
                            <div className="mt-1">
                                <Text type="secondary">{previewDocument.file_name}</Text>
                            </div>
                        </div>
                        <Divider />
                        <div>
                            <Text strong>内容:</Text>
                            <div className="mt-2 p-3 bg-gray-50 rounded max-h-96 overflow-y-auto">
                                <pre className="whitespace-pre-wrap text-sm">{previewDocument.content}</pre>
                            </div>
                        </div>
                        {previewDocument.metadata && Object.keys(previewDocument.metadata).length > 0 && (
                            <>
                                <Divider />
                                <div>
                                    <Text strong>元数据:</Text>
                                    <div className="mt-2">
                                        <pre className="text-xs bg-gray-50 p-2 rounded">
                                            {JSON.stringify(previewDocument.metadata, null, 2)}
                                        </pre>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                ) : (
                    <Empty description="无法加载文档" />
                )}
            </Modal>

            {/* 用户输入模态框（用户干预） */}
            <Modal
                title={
                    <div className="flex items-center space-x-2">
                        <InfoCircleOutlined className="text-orange-500" />
                        <span>需要您的帮助</span>
                    </div>
                }
                open={showUserInputModal}
                onOk={handleSubmitUserInput}
                onCancel={() => setShowUserInputModal(false)}
                okText="提交"
                cancelText="取消"
                width={700}
            >
                <div className="space-y-4 py-4">
                    <Alert
                        message={userInputPrompt}
                        type="info"
                        showIcon
                    />

                    {/* 选项列表 */}
                    {userInputOptions.length > 0 && (
                        <div>
                            <Text strong className="block mb-2">请选择：</Text>
                            <Radio.Group
                                value={selectedUserInput}
                                onChange={(e) => setSelectedUserInput(e.target.value)}
                                className="w-full"
                            >
                                <Space direction="vertical" className="w-full">
                                    {userInputOptions.map((option, idx) => (
                                        <Radio key={idx} value={option.value}>
                                            {option.label}
                                        </Radio>
                                    ))}
                                </Space>
                            </Radio.Group>
                        </div>
                    )}

                    {/* 如果是精化查询，显示文本输入 */}
                    {userInputType === 'refine_query' && selectedUserInput === 'refine' && (
                        <div>
                            <Text strong className="block mb-2">请输入更具体的问题：</Text>
                            <TextArea
                                placeholder="输入更具体的查询问题..."
                                rows={3}
                                onChange={(e) => {
                                    const newQuery = e.target.value;
                                    setSelectedUserInput({ action: 'refine', query: newQuery });
                                }}
                            />
                        </div>
                    )}

                    {/* 显示文档列表（如果有） */}
                    {userInputDocuments.length > 0 && selectedUserInput === 'select' && (
                        <div>
                            <Text strong className="block mb-2">请选择相关文档：</Text>
                            <div className="max-h-60 overflow-y-auto border rounded p-2">
                                <List
                                    dataSource={userInputDocuments}
                                    renderItem={(doc: any, idx) => (
                                        <List.Item
                                            className="cursor-pointer hover:bg-gray-50 p-2 rounded"
                                            onClick={() => {
                                                const currentSelection = (selectedUserInput as any)?.document_ids || [];
                                                const docId = doc.id || doc.document_id;
                                                const newSelection = currentSelection.includes(docId)
                                                    ? currentSelection.filter((id: number) => id !== docId)
                                                    : [...currentSelection, docId];
                                                setSelectedUserInput({ action: 'select', document_ids: newSelection });
                                            }}
                                        >
                                            <div className="flex items-center space-x-2 w-full">
                                                <input
                                                    type="checkbox"
                                                    checked={(selectedUserInput as any)?.document_ids?.includes(doc.id || doc.document_id)}
                                                    readOnly
                                                />
                                                <div className="flex-1">
                                                    <Text strong>{doc.title}</Text>
                                                    {doc.score && (
                                                        <Tag color="blue" className="ml-2">
                                                            {(doc.score * 100).toFixed(0)}%
                                                        </Tag>
                                                    )}
                                                </div>
                                            </div>
                                        </List.Item>
                                    )}
                                />
                            </div>
                        </div>
                    )}
                </div>
            </Modal>
        </div>
    );
}
