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
        try {
            const headers: Record<string, string> = {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
            };

            // 根据body类型设置相应的headers和body
            let body: FormData | string | undefined;
            if (this.options.body instanceof FormData) {
                // FormData情况，不需要额外设置Content-Type，浏览器会自动设置
                body = this.options.body;
            } else if (typeof this.options.body === 'object' && this.options.body !== null) {
                // JSON对象情况
                headers['Content-Type'] = 'application/json';
                body = JSON.stringify(this.options.body);
            } else if (typeof this.options.body === 'string') {
                // 字符串情况
                headers['Content-Type'] = 'application/json';
                body = this.options.body;
            }

            const response = await fetch(this.url, {
                method: this.options.method,
                body: body,
                headers,
                signal: this.options.signal,
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            if (!response.body) {
                throw new Error('SSE response has no body.');
            }

            await this.parseStream(response.body, this.options.signal);
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

        try {
            while (true) {
                if (signal?.aborted) break;

                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // 按 \n\n 分割消息
                const messages = buffer.split('\n\n');
                buffer = messages.pop() || ''; // 留下可能不完整的消息

                for (const message of messages) {
                    const lines = message.split('\n');

                    for (const line of lines) {
                        const trimmed = line.trim();
                        if (!trimmed || !trimmed.startsWith('data:')) continue;

                        const dataStr = trimmed.slice(5).trim();

                        try {
                            const event: SSEEvent = JSON.parse(dataStr);
                            this.onMessage(event);

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