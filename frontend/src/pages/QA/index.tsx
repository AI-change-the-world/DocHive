import { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Empty, Spin, message, Tag, Typography, Space, Divider, Modal, Select, Collapse, Steps, Badge, Alert } from 'antd';
import { SendOutlined, StopOutlined, FileTextOutlined, RobotOutlined, LoadingOutlined, SearchOutlined, DatabaseOutlined, FilterOutlined, BulbOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import type { QADocumentReference, QARequest, TemplateSelection } from '../../types';
import { qaService } from '../../services/qa';
import ReactMarkdown from 'react-markdown';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;
const { Option } = Select;
const { Panel } = Collapse;
const { Step } = Steps;

// Agent处理阶段定义
interface AgentStage {
    stage: string;
    label: string;
    icon: React.ReactNode;
    status: 'wait' | 'process' | 'finish' | 'error';
    message?: string;
    timestamp?: Date;
}

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    references?: QADocumentReference[];
    thinking?: string;
    timestamp: Date;
    agentStages?: AgentStage[];  // Agent处理阶段
    showDetails?: boolean;  // 是否展开详情
}

export default function QAPage() {
    const [question, setQuestion] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [currentAnswer, setCurrentAnswer] = useState('');
    const [currentReferences, setCurrentReferences] = useState<QADocumentReference[]>([]);
    const [thinkingStatus, setThinkingStatus] = useState('');
    const [agentStages, setAgentStages] = useState<AgentStage[]>([]);  // Agent当前处理阶段
    const [currentStageIndex, setCurrentStageIndex] = useState(0);  // 当前阶段索引

    // 使用ref保存最新的答案和引用，解决闭包问题
    const currentAnswerRef = useRef('');
    const currentReferencesRef = useRef<QADocumentReference[]>([]);
    const agentStagesRef = useRef<AgentStage[]>([]);
    const [templateId, setTemplateId] = useState<number | undefined>(undefined); // 模板ID
    const [templates, setTemplates] = useState<TemplateSelection[]>([]); // 模板列表
    const [loadingTemplates, setLoadingTemplates] = useState(false); // 模板加载状态
    const [sessionId, setSessionId] = useState<string>(''); // 会话ID，用于处理歧义
    const [ambiguityMessage, setAmbiguityMessage] = useState<string>(''); // 歧义消息
    const [clarification, setClarification] = useState(''); // 澄清内容
    const [showClarificationModal, setShowClarificationModal] = useState(false); // 显示澄清模态框

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null); // 用于中断请求

    // 调试：监控messages变化
    useEffect(() => {
        console.log('[消息列表变化]', {
            count: messages.length,
            latest: messages[messages.length - 1] ? {
                type: messages[messages.length - 1].type,
                hasContent: !!messages[messages.length - 1].content,
                contentLength: messages[messages.length - 1].content?.length || 0,
            } : null,
        });
    }, [messages]);

    // 调试：监控isStreaming变化
    useEffect(() => {
        console.log('[isStreaming变化]', isStreaming);
    }, [isStreaming]);

    // 调试：监控agentStages变化
    useEffect(() => {
        if (agentStages.length > 0) {
            console.log('[agentStages变化]', {
                count: agentStages.length,
                stages: agentStages.map(s => ({ label: s.label, status: s.status })),
            });
        }
    }, [agentStages]);

    // 获取模板列表
    const fetchTemplates = async () => {
        setLoadingTemplates(true);
        try {
            const response = await qaService.getAllTemplates();
            if (response.data) {
                setTemplates(response.data);
                // 如果还没有选择模板，默认选择第一个
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

    // 自动滚动到底部
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, currentAnswer, thinkingStatus]);

    // 组件挂载时获取模板列表
    useEffect(() => {
        fetchTemplates();
    }, []);

    // 发送问题
    const handleAsk = async () => {
        if (!question.trim()) {
            message.warning('请输入问题');
            return;
        }

        if (!templateId) {
            message.warning('请选择模板');
            return;
        }

        // 添加用户消息
        const userMessage: Message = {
            id: Date.now().toString(),
            type: 'user',
            content: question,
            timestamp: new Date(),
        };
        setMessages(prev => [...prev, userMessage]);

        // 重置状态
        setCurrentAnswer('');
        setCurrentReferences([]);
        setThinkingStatus('');
        setAmbiguityMessage('');
        setIsStreaming(true);

        // 清理ref
        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];

        // 初始化Agent处理阶段
        const initialStages: AgentStage[] = [
            {
                stage: 'start',
                label: '开始处理',
                icon: <ClockCircleOutlined />,
                status: 'process',
                message: '正在分析您的问题...',
                timestamp: new Date(),
            },
            {
                stage: 'es_fulltext',
                label: 'ES全文检索',
                icon: <SearchOutlined />,
                status: 'wait',
            },
            {
                stage: 'sql_structured',
                label: 'SQL结构化检索',
                icon: <DatabaseOutlined />,
                status: 'wait',
            },
            {
                stage: 'merge_results',
                label: '结果融合',
                icon: <FilterOutlined />,
                status: 'wait',
            },
            {
                stage: 'generate',
                label: '生成答案',
                icon: <BulbOutlined />,
                status: 'wait',
            },
        ];
        setAgentStages(initialStages);
        setCurrentStageIndex(0);

        // 创建AbortController用于中断请求
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        try {
            // 构建请求数据
            const requestData: QARequest = {
                question: question.trim(),
                template_id: templateId,
                top_k: 5,
            };

            // 选择使用哪个API端点
            const streamUrl = qaService.getAgentStreamUrl();

            // 使用SSE客户端，现在可以发送JSON对象
            const { SSEClient } = await import('../../utils/sseClient');
            const sseClient = new SSEClient(
                streamUrl,
                requestData, // 直接发送JSON对象
                (event) => {
                    // 处理SSE事件
                    const eventData = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

                    switch (eventData.event) {
                        case 'thinking':
                            const thinkingMsg = eventData.data?.message || '思考中...';
                            const stage = eventData.data?.stage || 'start';
                            console.log('[收到thinking事件]', { stage, message: thinkingMsg });

                            setThinkingStatus(thinkingMsg);

                            // 更新Agent处理阶段
                            setAgentStages(prev => {
                                const updated = [...prev];
                                const stageMap: Record<string, number> = {
                                    'start': 0,
                                    'es_fulltext': 1,
                                    'sql_structured': 2,
                                    'merge_results': 3,
                                    'generate': 4,
                                };

                                const currentIdx = stageMap[stage] ?? 0;
                                console.log('[更新阶段]', { stage, index: currentIdx, totalStages: updated.length });
                                setCurrentStageIndex(currentIdx);

                                // 标记之前的阶段为完成
                                for (let i = 0; i < currentIdx; i++) {
                                    if (updated[i]) {
                                        updated[i].status = 'finish';
                                    }
                                }

                                // 标记当前阶段为进行中
                                if (updated[currentIdx]) {
                                    updated[currentIdx].status = 'process';
                                    updated[currentIdx].message = thinkingMsg;
                                    updated[currentIdx].timestamp = new Date();
                                }

                                // 后续阶段保持wait状态
                                for (let i = currentIdx + 1; i < updated.length; i++) {
                                    if (updated[i]) {
                                        updated[i].status = 'wait';
                                    }
                                }

                                agentStagesRef.current = updated;
                                console.log('[阶段状态更新]', updated.map(s => ({ label: s.label, status: s.status })));

                                return updated;
                            });
                            break;

                        case 'references':
                            const refs = eventData.data?.references || [];
                            console.log('[收到references事件]', { count: refs.length });

                            setCurrentReferences(refs);
                            currentReferencesRef.current = refs;  // 同步到ref
                            setThinkingStatus('');

                            // 标记检索阶段完成
                            setAgentStages(prev => {
                                const updated = [...prev];
                                for (let i = 0; i <= 3; i++) {
                                    if (updated[i]) {
                                        updated[i].status = 'finish';
                                    }
                                }
                                agentStagesRef.current = updated;  // 同步到ref
                                return updated;
                            });
                            break;

                        case 'answer':
                            const newContent = (eventData.data?.content || '');
                            console.log('[收到answer事件]', { contentLength: newContent.length });

                            setCurrentAnswer(prev => {
                                const updated = prev + newContent;
                                currentAnswerRef.current = updated;  // 同步到ref
                                console.log('[答案累积]', { totalLength: updated.length });
                                return updated;
                            });
                            break;

                        case 'ambiguity':
                            // 处理歧义消息
                            setAmbiguityMessage(eventData.data?.message || '');
                            setShowClarificationModal(true);
                            setIsStreaming(false);
                            // 从响应中获取会话ID
                            if (eventData.data?.session_id) {
                                setSessionId(eventData.data.session_id);
                            }
                            break;

                        case 'complete':
                            console.log('[收到complete事件]', {
                                currentAnswer: currentAnswerRef.current,
                                referencesCount: currentReferencesRef.current.length,
                                stagesCount: agentStagesRef.current.length,
                            });

                            // 标记所有阶段完成
                            setAgentStages(prev => {
                                const updated = [...prev];
                                updated.forEach(stage => {
                                    if (stage.status !== 'error') {
                                        stage.status = 'finish';
                                    }
                                });
                                agentStagesRef.current = updated;
                                return updated;
                            });

                            // 使用ref中的最新值添加助手消息
                            const finalAnswer = currentAnswerRef.current;
                            const finalReferences = [...currentReferencesRef.current];  // 克隆数组
                            const finalStages = [...agentStagesRef.current];  // 克隆一份

                            console.log('[准备添加消息]', {
                                hasAnswer: !!finalAnswer,
                                answerLength: finalAnswer.length,
                                referencesCount: finalReferences.length,
                                stagesCount: finalStages.length,
                            });

                            if (finalAnswer || finalReferences.length > 0) {
                                const newMessage: Message = {
                                    id: Date.now().toString(),
                                    type: 'assistant',
                                    content: finalAnswer,
                                    references: finalReferences,
                                    timestamp: new Date(),
                                    agentStages: finalStages,
                                    showDetails: false,
                                };

                                console.log('[添加消息]', newMessage);
                                setMessages(prev => {
                                    const updated = [...prev, newMessage];
                                    console.log('[消息列表更新]', { count: updated.length });
                                    return updated;
                                });
                            } else {
                                console.warn('[跳过添加消息] 没有答案和引用');
                            }

                            // 延迟清理状态，确保消息先渲染
                            setTimeout(() => {
                                console.log('[开始清理状态]');
                                setIsStreaming(false);
                                setCurrentAnswer('');
                                setCurrentReferences([]);
                                setThinkingStatus('');
                                setAgentStages([]);
                                currentAnswerRef.current = '';
                                currentReferencesRef.current = [];
                                agentStagesRef.current = [];
                                console.log('[状态清理完成]');
                            }, 100);  // 延迟100ms，确保消息先添加到DOM
                            break;

                        case 'error':
                            message.error(eventData.data?.message || '问答失败');
                            setIsStreaming(false);
                            setThinkingStatus('');
                            break;
                    }
                },
                (error) => {
                    if (!abortController.signal.aborted) {
                        message.error(`问答失败: ${error.message}`);
                    }
                    setIsStreaming(false);
                    setThinkingStatus('');
                },
                () => {
                    // 完成回调 - 不再在这里添加消息，由complete事件处理
                    setIsStreaming(false);
                    setThinkingStatus('');
                }
            );

            // 添加signal到SSEClient
            (sseClient as any).options.signal = abortController.signal;

            // 启动SSE流
            await sseClient.start();
            setQuestion('');

        } catch (error: any) {
            if (!abortController.signal.aborted) {
                message.error(`问答失败: ${error.message}`);
            }
            setIsStreaming(false);
            setThinkingStatus('');
        }
    };

    // 处理澄清问题
    const handleClarify = async () => {
        if (!clarification.trim()) {
            message.warning('请输入澄清内容');
            return;
        }

        setShowClarificationModal(false);
        setIsStreaming(true);
        setCurrentAnswer('');
        setCurrentReferences([]);
        setThinkingStatus('正在处理您的澄清...');

        try {
            // 构建请求数据
            const requestData: QARequest = {
                question: question.trim(),
                template_id: templateId,
                top_k: 5,
            };

            // 调用澄清API
            const response = await qaService.clarifyAgentQuestion(requestData, clarification, sessionId);

            // 处理SSE流
            const reader = response.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                throw new Error('无法读取响应流');
            }

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                // 解析SSE事件
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const eventData = JSON.parse(line.slice(6));
                            switch (eventData.event) {
                                case 'thinking':
                                    setThinkingStatus(eventData.data?.message || '思考中...');
                                    break;

                                case 'references':
                                    setCurrentReferences(eventData.data?.references || []);
                                    setThinkingStatus('');
                                    break;

                                case 'answer':
                                    setCurrentAnswer(prev => prev + (eventData.data?.content || ''));
                                    break;

                                case 'complete':
                                    // 添加助手消息
                                    const assistantMessage: Message = {
                                        id: Date.now().toString(),
                                        type: 'assistant',
                                        content: currentAnswer,
                                        references: currentReferences,
                                        timestamp: new Date(),
                                    };
                                    setMessages(prev => [...prev, assistantMessage]);
                                    setCurrentAnswer('');
                                    setCurrentReferences([]);
                                    setThinkingStatus('');
                                    setIsStreaming(false);
                                    setClarification('');
                                    break;

                                case 'error':
                                    message.error(eventData.data?.message || '问答失败');
                                    setIsStreaming(false);
                                    setThinkingStatus('');
                                    break;
                            }
                        } catch (e) {
                            console.error('解析SSE事件失败:', e);
                        }
                    }
                }
            }

        } catch (error: any) {
            message.error(`问答失败: ${error.message}`);
            setIsStreaming(false);
            setThinkingStatus('');
        }
    };

    // 中断请求
    const handleStop = () => {
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
            abortControllerRef.current = null;
        }
        setIsStreaming(false);
        setThinkingStatus('');
        message.info('已中断问答');
    };

    // 清空对话
    const handleClear = () => {
        setMessages([]);
        setCurrentAnswer('');
        setCurrentReferences([]);
        setThinkingStatus('');
        setAmbiguityMessage('');
        setClarification('');
        setAgentStages([]);
        setCurrentStageIndex(0);

        // 清理ref
        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];
    };

    // 切换消息详情展示
    const toggleMessageDetails = (messageId: string) => {
        setMessages(prev => prev.map(msg =>
            msg.id === messageId ? { ...msg, showDetails: !msg.showDetails } : msg
        ));
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-2">
                    <RobotOutlined className="text-2xl text-primary-600" />
                    <Title level={3} className="!mb-0 !text-lg">智能问答</Title>
                </div>
                <div className="flex items-center space-x-2">
                    {messages.length > 0 && (
                        <Button size="small" onClick={handleClear} danger>
                            清空对话
                        </Button>
                    )}
                </div>
            </div>

            {/* 消息列表 */}
            <div className="flex-1 overflow-y-auto mb-4 space-y-4">
                {messages.length === 0 && !isStreaming && (
                    <Empty
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                        description={
                            <div className="text-center">
                                <Text type="secondary">请输入您的问题，我会基于文档库为您解答</Text>
                                <div className="mt-4 text-left max-w-2xl mx-auto">
                                    <Text type="secondary" className="block mb-2">示例问题：</Text>
                                    <ul className="text-gray-500 space-y-1">
                                        <li>• 文档库中有哪些关于项目管理的内容？</li>
                                        <li>• 总结一下技术规范文档的要点</li>
                                        <li>• 最近上传的文档主要讲了什么？</li>
                                    </ul>
                                </div>
                            </div>
                        }
                    />
                )}

                {messages.map((msg) => (
                    <div key={msg.id} className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}>
                        <Card
                            className={`max-w-[80%] ${msg.type === 'user'
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
                                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white">
                                            <RobotOutlined />
                                        </div>
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    {msg.type === 'user' ? (
                                        <Paragraph className="!mb-0">{msg.content}</Paragraph>
                                    ) : (
                                        <>
                                            {/* Agent处理阶段展示 */}
                                            {msg.agentStages && msg.agentStages.length > 0 && (
                                                <Collapse
                                                    ghost
                                                    size="small"
                                                    className="mb-3"
                                                    items={[{
                                                        key: 'agent-stages',
                                                        label: (
                                                            <div className="flex items-center space-x-2">
                                                                <BulbOutlined className="text-blue-500" />
                                                                <Text strong className="text-sm">
                                                                    Agent处理过程
                                                                </Text>
                                                                <Badge
                                                                    count={msg.agentStages.filter(s => s.status === 'finish').length}
                                                                    showZero
                                                                    style={{ backgroundColor: '#52c41a' }}
                                                                />
                                                            </div>
                                                        ),
                                                        children: (
                                                            <Steps
                                                                size="small"
                                                                direction="vertical"
                                                                current={msg.agentStages.findIndex(s => s.status === 'process')}
                                                                items={msg.agentStages.map(stage => ({
                                                                    title: stage.label,
                                                                    status: stage.status,
                                                                    icon: stage.icon,
                                                                    description: stage.message && (
                                                                        <Text type="secondary" className="text-xs">
                                                                            {stage.message}
                                                                            {stage.timestamp && (
                                                                                <span className="ml-2">
                                                                                    {stage.timestamp.toLocaleTimeString()}
                                                                                </span>
                                                                            )}
                                                                        </Text>
                                                                    ),
                                                                }))}
                                                            />
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
                                                                    className="bg-gray-50 hover:bg-gray-100 transition-colors"
                                                                >
                                                                    <div className="flex items-start justify-between">
                                                                        <div className="flex-1">
                                                                            <div className="flex items-center space-x-2">
                                                                                <Badge
                                                                                    count={idx + 1}
                                                                                    style={{ backgroundColor: '#1890ff' }}
                                                                                />
                                                                                <Text strong className="text-sm">
                                                                                    {ref.title}
                                                                                </Text>
                                                                            </div>
                                                                            <Paragraph
                                                                                className="!mb-0 mt-2 text-xs text-gray-600"
                                                                                ellipsis={{ rows: 2 }}
                                                                            >
                                                                                {ref.snippet}
                                                                            </Paragraph>
                                                                        </div>
                                                                        {ref.score !== undefined && (
                                                                            <Tag color="blue" className="ml-2">
                                                                                相关度 {(ref.score * 100).toFixed(0)}%
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

                {/* 当前流式回答 - 在streaming期间显示 */}
                {isStreaming && (
                    <div className="flex justify-start">
                        <Card className="max-w-[80%] bg-white border-gray-200 shadow-md">
                            <div className="flex items-start space-x-2">
                                <div className="flex-shrink-0">
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white">
                                        <Spin indicator={<LoadingOutlined spin />} size="small" />
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    {/* Agent处理阶段进度 */}
                                    {agentStages.length > 0 && (
                                        <div className="mb-3 p-3 bg-blue-50 rounded-lg border border-blue-200">
                                            <div className="flex items-center justify-between mb-2">
                                                <Text strong className="text-sm text-blue-700">
                                                    <BulbOutlined className="mr-1" />
                                                    Agent正在思考...
                                                </Text>
                                                <Badge
                                                    count={`${agentStages.filter(s => s.status === 'finish').length}/${agentStages.length}`}
                                                    style={{ backgroundColor: '#1890ff' }}
                                                />
                                            </div>
                                            <Steps
                                                size="small"
                                                current={currentStageIndex}
                                                items={agentStages.map(stage => ({
                                                    title: stage.label,
                                                    status: stage.status,
                                                    icon: stage.icon,
                                                }))}
                                            />
                                            {thinkingStatus && (
                                                <Alert
                                                    message={thinkingStatus}
                                                    type="info"
                                                    showIcon
                                                    icon={<LoadingOutlined />}
                                                    className="mt-2"
                                                    banner
                                                />
                                            )}
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
                                                        className="bg-gradient-to-r from-gray-50 to-blue-50 border-blue-200 hover:shadow-md transition-shadow"
                                                    >
                                                        <div className="flex items-start justify-between">
                                                            <div className="flex-1">
                                                                <div className="flex items-center space-x-2">
                                                                    <Badge
                                                                        count={idx + 1}
                                                                        style={{ backgroundColor: '#52c41a' }}
                                                                    />
                                                                    <Text strong className="text-sm">
                                                                        {ref.title}
                                                                    </Text>
                                                                </div>
                                                                <Paragraph
                                                                    className="!mb-0 mt-2 text-xs text-gray-600"
                                                                    ellipsis={{ rows: 2 }}
                                                                >
                                                                    {ref.snippet}
                                                                </Paragraph>
                                                            </div>
                                                            {ref.score !== undefined && (
                                                                <Tag color="blue" className="ml-2">
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
                                                <span className="inline-block w-2 h-4 bg-primary-500 animate-pulse ml-1"></span>
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
                    {/* 模板选择放在输入区域内部 */}
                    <div className="flex items-center space-x-2">
                        <span className="text-sm text-gray-600">模板:</span>
                        <Select
                            size="small"
                            style={{ width: 150 }}
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
                            if (e.shiftKey) {
                                return; // Shift+Enter 换行
                            }
                            e.preventDefault();
                            handleAsk();
                        }}
                    />
                    <div className="flex items-center justify-between">
                        <Text type="secondary" className="text-xs">
                            按 Enter 发送，Shift + Enter 换行
                        </Text>
                        <Space>
                            {isStreaming ? (
                                <Button
                                    type="primary"
                                    danger
                                    icon={<StopOutlined />}
                                    onClick={handleStop}
                                    size="small"
                                >
                                    停止生成
                                </Button>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<SendOutlined />}
                                    onClick={handleAsk}
                                    disabled={!question.trim() || !templateId}
                                    size="small"
                                >
                                    发送问题
                                </Button>
                            )}
                        </Space>
                    </div>
                </div>
            </Card>

            {/* 澄清问题模态框 */}
            <Modal
                title="需要更多信息"
                open={showClarificationModal}
                onCancel={() => setShowClarificationModal(false)}
                onOk={handleClarify}
                okText="提交"
                cancelText="取消"
            >
                <div className="space-y-3">
                    <p>{ambiguityMessage}</p>
                    <TextArea
                        value={clarification}
                        onChange={(e) => setClarification(e.target.value)}
                        placeholder="请提供更多信息..."
                        autoSize={{ minRows: 3, maxRows: 6 }}
                    />
                </div>
            </Modal>
        </div>
    );
}