export interface SSEEvent {
    event?: string;
    data?: any;
    done?: boolean;
}

export interface SSERequestOptions {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
    body?: FormData | string | object; // 支持FormData、字符串和对象
    headers?: Record<string, string>;
    signal?: AbortSignal;
}

export class SSEClient {
    private url: string;
    private options: SSERequestOptions;
    private onMessage: (event: SSEEvent) => void;
    private onError: (error: Error) => void;
    private onComplete: () => void;

    constructor(
        url: string,
        data: FormData | object, // 支持FormData和普通对象
        onMessage: (event: SSEEvent) => void,
        onError?: (error: Error) => void,
        onComplete?: () => void
    ) {
        this.url = url;
        this.options = {
            method: 'POST',
            body: data,
        };
        this.onMessage = onMessage;
        this.onError = onError || (() => { });
        this.onComplete = onComplete || (() => { });
    }

    async start() {
        console.log('[SSEClient] 开始连接', this.url);
        try {
            const headers: Record<string, string> = {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            };

            // 根据body类型设置相应的headers和body
            let body: FormData | string | undefined;
            if (this.options.body instanceof FormData) {
                body = this.options.body;
            } else if (typeof this.options.body === 'object' && this.options.body !== null) {
                headers['Content-Type'] = 'application/json';
                body = JSON.stringify(this.options.body);
            } else if (typeof this.options.body === 'string') {
                headers['Content-Type'] = 'application/json';
                body = this.options.body;
            }

            console.log('[SSEClient] 发送请求...');
            const response = await fetch(this.url, {
                method: this.options.method,
                body: body,
                headers,
                signal: this.options.signal,
            });

            console.log('[SSEClient] 收到响应', response.status, response.ok);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error('SSE response has no body.');
            }

            console.log('[SSEClient] 开始解析流...');
            await this.parseStream(response.body, this.options.signal);
            console.log('[SSEClient] 流解析完成');
        } catch (error) {
            if (this.options.signal?.aborted) return;
            this.onError(error as Error);
        }
    }

    /**
     * 解析 SSE 数据流
     */
    private async parseStream(
        stream: ReadableStream<Uint8Array>,
        signal?: AbortSignal
    ) {
        const decoder = new TextDecoder('utf-8');
        const reader = stream.getReader();
        let buffer = '';
        let chunkCount = 0;

        console.log('[SSEClient] parseStream 开始');
        try {
            while (true) {
                if (signal?.aborted) {
                    console.log('[SSEClient] Signal aborted');
                    break;
                }

                console.log('[SSEClient] 准备读取chunk...');
                const { value, done } = await reader.read();
                chunkCount++;
                console.log(`[SSEClient] Chunk ${chunkCount}: done=${done}, bytes=${value?.length || 0}`);

                if (done) {
                    console.log('[SSEClient] Stream done, 退出循环');
                    break;
                }

                buffer += decoder.decode(value, { stream: true });
                console.log('[SSEClient] Buffer:', buffer.substring(0, 200));

                // 按 \n\n 分割消息
                const messages = buffer.split('\n\n');
                buffer = messages.pop() || '';
                console.log(`[SSEClient] 分割到 ${messages.length} 个消息`);

                for (const message of messages) {
                    console.log('[SSEClient] 处理消息:', message.substring(0, 100));
                    const lines = message.split('\n');

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith('data:')) continue;

                        const dataStr = trimmed.slice(5).trim();
                        console.log('[SSEClient] 提取data:', dataStr.substring(0, 100));

                        try {
                            const event: SSEEvent = JSON.parse(dataStr);
                            console.log('[SSEClient] 解析到事件，准备调用onMessage', event);
                            this.onMessage(event);
                            console.log('[SSEClient] onMessage调用完成');

                            // 检测到完成标记，立即结束
                            if (event.done === true) {
                                this.onComplete();
                                return; // 直接返回，结束整个解析
                            }
                        } catch (e) {
                            console.warn('SSE parse error:', e, dataStr);
                        }
                    }
                }
            }

            // 流正常结束（无 done 标记）
            this.onComplete();
        } catch (err) {
            if (!signal?.aborted) {
                console.error('SSE stream error:', err);
                throw err;
            }
        } finally {
            reader.releaseLock();
        }
    }
}