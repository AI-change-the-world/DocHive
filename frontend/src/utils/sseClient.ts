import { message } from 'antd';

export interface SSEEvent {
    event?: string;
    data: string;
    done?: boolean;
}

export class SSEClient {
    private url: string;
    private formData: FormData;
    private onMessage: (event: SSEEvent) => void;
    private onError: (error: Error) => void;
    private onComplete: () => void;

    constructor(
        url: string,
        formData: FormData,
        onMessage: (event: SSEEvent) => void,
        onError?: (error: Error) => void,
        onComplete?: () => void
    ) {
        this.url = url;
        this.formData = formData;
        this.onMessage = onMessage;
        this.onError = onError || (() => { });
        this.onComplete = onComplete || (() => { });
    }

    async start() {
        try {
            const response = await fetch(this.url, {
                method: 'POST',
                body: this.formData,
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
                },
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const reader = response.body?.getReader();
            const decoder = new TextDecoder('utf-8');

            if (reader) {
                let result = '';
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    result += decoder.decode(value, { stream: true });

                    // 处理 SSE 数据
                    const lines = result.split('\n\n');
                    result = lines.pop() || ''; // 保留不完整的行

                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.slice(6);
                            try {
                                const event: SSEEvent = JSON.parse(data);
                                this.onMessage(event);

                                // 如果是完成事件
                                if (event.done) {
                                    this.onComplete();
                                    break;
                                }
                            } catch (e) {
                                console.log('解析事件数据失败:', e);
                            }
                        }
                    }
                }
            }
        } catch (error) {
            this.onError(error as Error);
        }
    }
}