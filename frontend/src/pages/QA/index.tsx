import { useState, useRef, useEffect } from 'react';
import { Input, Button, Card, Empty, Spin, message, Tag, Typography, Space, Divider } from 'antd';
import { SendOutlined, StopOutlined, FileTextOutlined, RobotOutlined, LoadingOutlined } from '@ant-design/icons';
import type { QADocumentReference, QARequest } from '../../types';
import { qaService } from '../../services/qa';
import ReactMarkdown from 'react-markdown';

const { TextArea } = Input;
const { Title, Text, Paragraph } = Typography;

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    references?: QADocumentReference[];
    thinking?: string;
    timestamp: Date;
}

export default function QAPage() {
    const [question, setQuestion] = useState('');
    const [messages, setMessages] = useState<Message[]>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    const [currentAnswer, setCurrentAnswer] = useState('');
    const [currentReferences, setCurrentReferences] = useState<QADocumentReference[]>([]);
    const [thinkingStatus, setThinkingStatus] = useState('');
    const abortControllerRef = useRef<AbortController | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // 自动滚动到底部
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, currentAnswer, thinkingStatus]);

    // 发送问题
    const handleAsk = async () => {
        if (!question.trim()) {
            message.warning('请输入问题');
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
        setIsStreaming(true);

        // 创建AbortController用于中断请求
        const abortController = new AbortController();
        abortControllerRef.current = abortController;

        try {
            // 构建请求数据
            const requestData: QARequest = {
                question: question.trim(),
                top_k: 5,
            };

            // 创建FormData
            const formData = new FormData();
            formData.append('question', requestData.question);
            if (requestData.template_id) {
                formData.append('template_id', requestData.template_id.toString());
            }
            formData.append('top_k', (requestData.top_k || 5).toString());

            // 使用SSE客户端
            const { SSEClient } = await import('../../utils/sseClient');
            const sseClient = new SSEClient(
                qaService.getStreamUrl(),
                formData,
                (event) => {
                    // 处理SSE事件
                    const eventData = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;

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
                    // 完成回调
                    if (currentAnswer) {
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
                    }
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
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center space-x-3">
                    <RobotOutlined className="text-3xl text-primary-600" />
                    <Title level={2} className="!mb-0">智能问答</Title>
                </div>
                {messages.length > 0 && (
                    <Button onClick={handleClear} danger>
                        清空对话
                    </Button>
                )}
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
                                            <div className="prose prose-sm max-w-none">
                                                <ReactMarkdown>{msg.content}</ReactMarkdown>
                                            </div>
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
                                                                    className="bg-gray-50"
                                                                >
                                                                    <div className="flex items-start justify-between">
                                                                        <div className="flex-1">
                                                                            <Text strong className="text-sm">
                                                                                {ref.title}
                                                                            </Text>
                                                                            <Paragraph
                                                                                className="!mb-0 mt-1 text-xs text-gray-600"
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

                {/* 当前流式回答 */}
                {isStreaming && (
                    <div className="flex justify-start">
                        <Card className="max-w-[80%] bg-white border-gray-200">
                            <div className="flex items-start space-x-2">
                                <div className="flex-shrink-0">
                                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-500 flex items-center justify-center text-white">
                                        <RobotOutlined />
                                    </div>
                                </div>
                                <div className="flex-1 min-w-0">
                                    {thinkingStatus && (
                                        <div className="flex items-center space-x-2 text-gray-500 mb-2">
                                            <Spin indicator={<LoadingOutlined spin />} size="small" />
                                            <Text type="secondary">{thinkingStatus}</Text>
                                        </div>
                                    )}

                                    {currentReferences.length > 0 && !thinkingStatus && (
                                        <>
                                            <Text strong className="text-gray-600 mb-2 block">
                                                <FileTextOutlined className="mr-1" />
                                                参考文档 ({currentReferences.length})
                                            </Text>
                                            <Space direction="vertical" className="w-full mb-3">
                                                {currentReferences.map((ref, idx) => (
                                                    <Card key={idx} size="small" className="bg-gray-50">
                                                        <div className="flex items-start justify-between">
                                                            <div className="flex-1">
                                                                <Text strong className="text-sm">
                                                                    {ref.title}
                                                                </Text>
                                                                <Paragraph
                                                                    className="!mb-0 mt-1 text-xs text-gray-600"
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

                                    {currentAnswer && (
                                        <div className="prose prose-sm max-w-none">
                                            <ReactMarkdown>{currentAnswer}</ReactMarkdown>
                                            <span className="inline-block w-2 h-4 bg-primary-500 animate-pulse ml-1"></span>
                                        </div>
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
                                >
                                    停止生成
                                </Button>
                            ) : (
                                <Button
                                    type="primary"
                                    icon={<SendOutlined />}
                                    onClick={handleAsk}
                                    disabled={!question.trim()}
                                >
                                    发送问题
                                </Button>
                            )}
                        </Space>
                    </div>
                </div>
            </Card>
        </div>
    );
}
