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
    Steps,
    Badge,
    Alert,
    Table,
    Tooltip,
    List,
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
} from '@ant-design/icons';
import type { QADocumentReference, QARequest, TemplateSelection } from '../../types';
import { qaService } from '../../services/qa';
import { documentService } from '../../services/document';
import ReactMarkdown from 'react-markdown';

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
    result?: StageResult;  // 新增：阶段结果
}

// 阶段结果数据结构
interface StageResult {
    // 通用字段
    document_ids?: number[];
    count?: number;
    documents?: any[];
    category?: string;
    conditions?: any[];
    strategy?: string;

    // 任务规划阶段 (intent_routing)
    execution_plan?: any[];
    reasoning?: string;
    tool_count?: number;
    has_retrieval?: boolean;

    // 工具执行阶段 (tool_answer)
    tools_count?: number;
    results?: any[];
}

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    references?: QADocumentReference[];
    thinking?: string;
    timestamp: Date;
    agentStages?: AgentStage[];
    showDetails?: boolean;
}

export default function QAPage() {
    const [question, setQuestion] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [currentAnswer, setCurrentAnswer] = useState('');
    const [currentReferences, setCurrentReferences] = useState<QADocumentReference[]>([]);
    const [agentStages, setAgentStages] = useState<AgentStage[]>([]);
    const [executionMode, setExecutionMode] = useState<'tool_calling' | 'document_retrieval' | null>(null);
    const [currentStageIndex, setCurrentStageIndex] = useState(0);

    // 使用ref保存最新值
    const currentAnswerRef = useRef('');
    const currentReferencesRef = useRef<QADocumentReference[]>([]);
    const agentStagesRef = useRef<AgentStage[]>([]);

    const [templateId, setTemplateId] = useState<number | undefined>(undefined);
    const [templates, setTemplates] = useState<TemplateSelection[]>([]);
    const [loadingTemplates, setLoadingTemplates] = useState(false);
    const [sessionId, setSessionId] = useState<string>('');
    const [ambiguityMessage, setAmbiguityMessage] = useState<string>('');
    const [clarification, setClarification] = useState('');
    const [showClarificationModal, setShowClarificationModal] = useState(false);

    // 文档预览相关
    const [previewDocId, setPreviewDocId] = useState<number | null>(null);
    const [showPreviewModal, setShowPreviewModal] = useState(false);
    const [previewDocument, setPreviewDocument] = useState<any>(null);
    const [loadingPreview, setLoadingPreview] = useState(false);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortControllerRef = useRef<AbortController | null>(null);

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
    const initializeStagesFromPlan = (plan: Array<{ stage: string, name: string, icon: string }>): AgentStage[] => {
        return plan.map((item, index) => ({
            stage: item.stage,
            label: item.name,
            icon: <span style={{ fontSize: '18px' }}>{item.icon}</span>,
            status: index === 0 ? 'process' : 'wait',
            message: index === 0 ? `正在${item.name}...` : undefined,
            timestamp: index === 0 ? new Date() : undefined,
        }));
    };

    // 旧的静态初始化（保留作为默认）
    const initializeStages = (): AgentStage[] => [
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
            icon: <MergeOutlined />,
            status: 'wait',
        },
        {
            stage: 'refined_filter',
            label: '精细化筛选',
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
                // 当前阶段完成，开始下一阶段
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
        setAmbiguityMessage('');
        setIsStreaming(true);
        setExecutionMode(null);

        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];

        // 暂时不初始化阶段，等待后端返回 execution_plan
        setAgentStages([]);
        setCurrentStageIndex(0);

        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        try {
            const requestData: QARequest = {
                question: question.trim(),
                template_id: templateId,
                top_k: 5,
            };

            // 参考fh_agent实现，直接使用fetch+ReadableStream，不用SSEClient
            const streamUrl = qaService.getAgentStreamUrl();
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
                buffer = lines.pop() || ''; // 保留最后不完整的行

                for (const line of lines) {
                    if (!line.trim() || !line.startsWith('data:')) continue;

                    try {
                        const jsonStr = line.substring(5).trim(); // 移除 "data: " 前缀
                        const eventData = JSON.parse(jsonStr);
                        console.log('[收到SSE事件]', eventData.event, eventData);

                        switch (eventData.event) {
                            case 'execution_plan':
                                // 根据后端返回的计划初始化阶段
                                const plan = eventData.data?.plan || [];
                                const mode = eventData.data?.mode;
                                console.log('[execution_plan]', { plan, mode });

                                setExecutionMode(mode);
                                const initialStages = initializeStagesFromPlan(plan);
                                setAgentStages(initialStages);
                                agentStagesRef.current = initialStages;
                                setCurrentStageIndex(0);
                                break;

                            case 'thinking':
                            case 'stage_start':
                                const stage = eventData.data?.stage || 'start';
                                const msg = eventData.data?.message || '处理中...';

                                setAgentStages(prev => {
                                    if (prev.length === 0) return prev; // 还没有计划
                                    return updateStageStatus(prev, stage, 'process', msg);
                                });
                                break;

                            case 'stage_complete':
                                const completedStage = eventData.data?.stage;
                                const resultData = eventData.data?.result;
                                const completeMsg = eventData.data?.message;
                                console.log(`[阶段${completedStage}完成]`, { resultData, message: completeMsg });

                                setAgentStages(prev => {
                                    if (prev.length === 0) return prev; // 还没有计划
                                    const updated = updateStageStatus(prev, completedStage, 'finish', completeMsg, resultData);
                                    agentStagesRef.current = updated;
                                    return updated;
                                });
                                break;

                            case 'references':
                                const refs = eventData.data?.references || [];
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

                            case 'ambiguity':
                                setAmbiguityMessage(eventData.data?.message || '');
                                setShowClarificationModal(true);
                                setIsStreaming(false);
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

                                // 从 ref 中获取最新的阶段数据，并标记为完成
                                const completedStages = agentStagesRef.current.map(s => ({
                                    ...s,
                                    status: (s.status === 'error' ? 'error' : 'finish') as 'wait' | 'process' | 'finish' | 'error',
                                }));

                                // 获取最终数据
                                const finalAnswer = currentAnswerRef.current;
                                const finalReferences = [...currentReferencesRef.current];

                                console.log('[准备添加消息]', {
                                    hasAnswer: !!finalAnswer,
                                    answerLength: finalAnswer.length,
                                    answer: finalAnswer,
                                    referencesCount: finalReferences.length,
                                    stagesCount: completedStages.length,
                                });

                                // 总是添加消息，即使没有答案也要显示
                                const newMessage: Message = {
                                    id: Date.now().toString(),
                                    type: 'assistant',
                                    content: finalAnswer || '抱歉，没有找到相关答案。',
                                    references: finalReferences,
                                    timestamp: new Date(),
                                    agentStages: completedStages,
                                    showDetails: false,
                                };

                                console.log('[添加消息到列表]', newMessage);
                                setMessages(prev => {
                                    const updated = [...prev, newMessage];
                                    console.log('[消息列表更新]', { count: updated.length });
                                    return updated;
                                });

                                // 延迟清理流式状态，确保消息先渲染
                                setTimeout(() => {
                                    setIsStreaming(false);
                                    setCurrentAnswer('');
                                    setCurrentReferences([]);
                                    setAgentStages([]);
                                    currentAnswerRef.current = '';
                                    currentReferencesRef.current = [];
                                    agentStagesRef.current = [];
                                    console.log('[流式状态已清理]');
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

            // 清空输入框
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
        setAmbiguityMessage('');
        setClarification('');
        setAgentStages([]);
        setCurrentStageIndex(0);
        currentAnswerRef.current = '';
        currentReferencesRef.current = [];
        agentStagesRef.current = [];
    };

    // 渲染阶段结果详情
    const renderStageResult = (stage: AgentStage) => {
        if (!stage.result) return null;

        const { document_ids, count, documents, category, conditions, strategy, execution_plan, reasoning, tool_count, has_retrieval, tools_count, results } = stage.result;

        // === 1. 任务规划阶段 (intent_routing) ===
        if (stage.stage === 'intent_routing' && execution_plan) {
            return (
                <div className="mt-2 space-y-2">
                    {/* LLM 推理过程 */}
                    {reasoning && (
                        <div className="p-3 bg-amber-50 rounded-lg border border-amber-200">
                            <div className="flex items-start space-x-2">
                                <BulbOutlined className="text-amber-600 mt-0.5" />
                                <div className="flex-1">
                                    <Text strong className="text-xs text-amber-700">💭 LLM 推理过程</Text>
                                    <div className="text-xs text-gray-700 mt-1 whitespace-pre-wrap">
                                        {reasoning}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* 执行计划 */}
                    <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                        <div className="flex items-start space-x-2">
                            <InfoCircleOutlined className="text-blue-600 mt-0.5" />
                            <div className="flex-1">
                                <Text strong className="text-xs text-blue-700">📋 执行计划</Text>
                                <div className="mt-2 space-y-2">
                                    {execution_plan.map((step: any, idx: number) => (
                                        <div key={idx} className="flex items-start space-x-2 text-xs">
                                            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-500 text-white flex items-center justify-center text-[10px] font-bold">
                                                {step.step}
                                            </span>
                                            <div className="flex-1">
                                                <div className="font-medium text-gray-800">
                                                    {step.action === 'tool_call' ? '🔧 调用工具' : '📚 文档检索'}: {step.description}
                                                </div>
                                                {step.tool_name && (
                                                    <div className="mt-1 text-gray-600">
                                                        <Tag color="purple" className="text-xs">
                                                            {step.tool_name}
                                                        </Tag>
                                                        {step.arguments && Object.keys(step.arguments).length > 0 && (
                                                            <span className="ml-2 text-gray-500">
                                                                参数: {JSON.stringify(step.arguments)}
                                                            </span>
                                                        )}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* 执行摘要 */}
                    <div className="flex items-center space-x-2 text-xs text-gray-600">
                        <Tag color="green">{tool_count || 0} 个工具调用</Tag>
                        {has_retrieval && <Tag color="blue">需要文档检索</Tag>}
                    </div>
                </div>
            );
        }

        // === 2. 工具执行阶段 (tool_answer) ===
        if (stage.stage === 'tool_answer' && results) {
            return (
                <div className="mt-2 space-y-2">
                    <div className="p-3 bg-purple-50 rounded-lg border border-purple-200">
                        <div className="flex items-start space-x-2">
                            <CheckCircleOutlined className="text-purple-600 mt-0.5" />
                            <div className="flex-1">
                                <Text strong className="text-xs text-purple-700">
                                    ✅ 工具执行结果 ({tools_count || results.length} 个)
                                </Text>
                                <div className="mt-2 space-y-3">
                                    {results.map((toolResult: any, idx: number) => (
                                        <div key={idx} className="p-2 bg-white rounded border border-purple-100">
                                            {/* 工具信息头部 */}
                                            <div className="flex items-center space-x-2 mb-2">
                                                <Badge count={idx + 1} style={{ backgroundColor: '#722ed1' }} />
                                                <Text strong className="text-xs text-gray-800">
                                                    {toolResult.tool_name}
                                                </Text>
                                                {toolResult.step && (
                                                    <Tag color="purple" className="text-xs">步骤 {toolResult.step}</Tag>
                                                )}
                                            </div>

                                            {/* 工具参数 */}
                                            {toolResult.arguments && Object.keys(toolResult.arguments).length > 0 && (
                                                <div className="mb-2 p-2 bg-gray-50 rounded">
                                                    <Text className="text-xs text-gray-600">📝 调用参数:</Text>
                                                    <div className="mt-1 flex flex-wrap gap-1">
                                                        {Object.entries(toolResult.arguments).map(([key, value]) => (
                                                            <Tag key={key} color="blue" className="text-xs">
                                                                {key}: {String(value)}
                                                            </Tag>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            {/* 工具描述 */}
                                            {toolResult.description && (
                                                <div className="mb-2 text-xs text-gray-600 italic">
                                                    💡 {toolResult.description}
                                                </div>
                                            )}

                                            {/* 执行结果 */}
                                            <div className="p-2 bg-green-50 rounded border border-green-100">
                                                <Text className="text-xs text-green-700 font-medium">📊 执行结果:</Text>
                                                <div className="mt-1 max-h-40 overflow-y-auto">
                                                    {toolResult.result?.success === false ? (
                                                        <Alert
                                                            type="error"
                                                            message={toolResult.result.error || '执行失败'}
                                                            className="text-xs"
                                                        />
                                                    ) : (
                                                        <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono bg-white p-2 rounded">
                                                            {JSON.stringify(toolResult.result, null, 2)}
                                                        </pre>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            );
        }

        // === 3. 其他阶段（原有逻辑）===
        return (
            <div className="mt-2 p-3 bg-gray-50 rounded border border-gray-200">
                <Space direction="vertical" className="w-full" size="small">
                    {/* 文档ID列表 */}
                    {document_ids && document_ids.length > 0 && (
                        <div>
                            <Text strong className="text-xs text-gray-600">
                                <FileSearchOutlined className="mr-1" />
                                召回文档 ({count || document_ids.length} 篇):
                            </Text>
                            <div className="mt-1 flex flex-wrap gap-1">
                                {document_ids.map((id, idx) => (
                                    <Tag
                                        key={idx}
                                        color="blue"
                                        className="cursor-pointer"
                                        onClick={() => handlePreviewDocument(id)}
                                    >
                                        <EyeOutlined className="mr-1" />
                                        文档 #{id}
                                    </Tag>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 分类信息 */}
                    {category && category !== '*' && (
                        <div>
                            <Text strong className="text-xs text-gray-600">分类: </Text>
                            <Tag color="green">{category}</Tag>
                        </div>
                    )}

                    {/* 提取条件 */}
                    {conditions && conditions.length > 0 && (
                        <div>
                            <Text strong className="text-xs text-gray-600">提取条件:</Text>
                            <div className="mt-1">
                                {conditions.map((cond, idx) => (
                                    <Tag key={idx} color="purple" className="mb-1">
                                        {cond.code}: {cond.value}
                                    </Tag>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* 融合策略 */}
                    {strategy && (
                        <div>
                            <Text strong className="text-xs text-gray-600">融合策略: </Text>
                            <Tag color="orange">{strategy}</Tag>
                        </div>
                    )}

                    {/* 文档详情 */}
                    {documents && documents.length > 0 && (
                        <Collapse
                            ghost
                            size="small"
                            items={[{
                                key: 'docs',
                                label: <Text className="text-xs">查看文档详情 ({documents.length})</Text>,
                                children: (
                                    <List
                                        size="small"
                                        dataSource={documents}
                                        renderItem={(doc: any, idx: number) => (
                                            <List.Item
                                                key={idx}
                                                className="cursor-pointer hover:bg-blue-50"
                                                onClick={() => handlePreviewDocument(doc.document_id)}
                                            >
                                                <List.Item.Meta
                                                    avatar={<FileTextOutlined className="text-blue-500" />}
                                                    title={
                                                        <Text className="text-xs">
                                                            #{doc.document_id} {doc.title}
                                                        </Text>
                                                    }
                                                    description={
                                                        <Text className="text-xs text-gray-500" ellipsis>
                                                            {doc.content?.substring(0, 100)}...
                                                        </Text>
                                                    }
                                                />
                                            </List.Item>
                                        )}
                                    />
                                ),
                            }]}
                        />
                    )}
                </Space>
            </div>
        );
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
                                            {/* Agent处理阶段 */}
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
                                                            <Space direction="vertical" className="w-full">
                                                                {msg.agentStages.map((stage, idx) => (
                                                                    <Card
                                                                        key={idx}
                                                                        size="small"
                                                                        className={`${stage.status === 'finish' ? 'bg-green-50 border-green-200' :
                                                                            stage.status === 'process' ? 'bg-blue-50 border-blue-200' :
                                                                                'bg-gray-50 border-gray-200'
                                                                            }`}
                                                                    >
                                                                        <div className="flex items-start justify-between">
                                                                            <div className="flex items-center space-x-2">
                                                                                {stage.icon}
                                                                                <div>
                                                                                    <Text strong className="text-sm">{stage.label}</Text>
                                                                                    {stage.message && (
                                                                                        <div className="text-xs text-gray-500 mt-1">
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
                                                                    <div className="flex items-start justify-between">
                                                                        <div className="flex-1">
                                                                            <div className="flex items-center space-x-2">
                                                                                <Badge count={idx + 1} style={{ backgroundColor: '#1890ff' }} />
                                                                                <Text strong className="text-sm">{ref.title}</Text>
                                                                                <EyeOutlined className="text-blue-500" />
                                                                            </div>
                                                                            <Paragraph className="!mb-0 mt-2 text-xs text-gray-600" ellipsis={{ rows: 2 }}>
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
                                            <Space direction="vertical" className="w-full">
                                                {agentStages.map((stage, idx) => (
                                                    <Card
                                                        key={idx}
                                                        size="small"
                                                        className={`${stage.status === 'finish' ? 'bg-green-50 border-green-200' :
                                                            stage.status === 'process' ? 'bg-white border-blue-300' :
                                                                'bg-gray-50 border-gray-200'
                                                            }`}
                                                    >
                                                        <div className="flex items-start justify-between">
                                                            <div className="flex items-center space-x-2 flex-1">
                                                                {stage.icon}
                                                                <div className="flex-1">
                                                                    <Text strong className="text-sm">{stage.label}</Text>
                                                                    {stage.message && (
                                                                        <div className="text-xs text-gray-500 mt-1">
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
                                                        className="bg-gradient-to-r from-gray-50 to-blue-50 border-blue-200 hover:shadow-md transition-shadow cursor-pointer"
                                                        onClick={() => handlePreviewDocument(ref.document_id)}
                                                    >
                                                        <div className="flex items-start justify-between">
                                                            <div className="flex-1">
                                                                <div className="flex items-center space-x-2">
                                                                    <Badge count={idx + 1} style={{ backgroundColor: '#52c41a' }} />
                                                                    <Text strong className="text-sm">{ref.title}</Text>
                                                                    <EyeOutlined className="text-blue-500" />
                                                                </div>
                                                                <Paragraph className="!mb-0 mt-2 text-xs text-gray-600" ellipsis={{ rows: 2 }}>
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
                            if (e.shiftKey) return;
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
                                <Button type="primary" danger icon={<StopOutlined />} onClick={handleStop} size="small">
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

            {/* 澄清问题模态框 */}
            <Modal
                title="需要更多信息"
                open={showClarificationModal}
                onCancel={() => setShowClarificationModal(false)}
                onOk={() => {/* TODO: 实现澄清逻辑 */ }}
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
