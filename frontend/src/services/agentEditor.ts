/**
 * Agent编辑器服务
 */

import request from "../utils/request";

export interface AgentMarkdownRequest {
  content: string;
  template_id?: number;
}

export interface AgentCreateRequest {
  name: string;
  description: string;
  template_id?: number;
  markdown_content: string;
  // V2: 直接传递已解析好的字段,避免后端重复LLM解析
  execution_pattern?: string;
  goals?: string[];
  constraints?: string[];
  initial_plan?: any[];
  mermaid_diagram?: string;
}

export const agentEditorService = {
  /**
   * 解析Agent Markdown
   */
  parseMarkdown(data: AgentMarkdownRequest) {
    return request.post("/agents/parse-markdown", data);
  },

  /**
   * 创建Agent
   */
  createAgent(data: AgentCreateRequest) {
    return request.post("/agents/create", data);
  },

  /**
   * 获取Agent列表
   */
  listAgents(params?: { template_id?: number; is_active?: boolean }) {
    return request.get("/agents/list", { params });
  },

  /**
   * 获取单个Agent
   */
  getAgent(agentId: number) {
    return request.get(`/agents/${agentId}`);
  },

  /**
   * 获取Markdown模板
   */
  getMarkdownTemplate() {
    return request.get("/agents/markdown-template");
  },

  /**
   * 执行自定义Agent (SSE流式)
   * 这是主要入口：执行已保存的Agent
   */
  async executeAgent(
    agentId: number,
    data: {
      query: string;
      template_id?: number;
      session_id?: string;
    },
    onEvent: (event: any) => void
  ) {
    const baseURL = request.defaults.baseURL || "";
    const response = await fetch(`${baseURL}/agents/execute/${agentId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("access_token")}`
      },
      body: JSON.stringify(data),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("响应体为空");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();

      if (value) {
        buffer += decoder.decode(value, { stream: true });
      }

      // 处理 buffer 中的完整行
      const lines = buffer.split("\n");

      // 如果流结束，处理所有行；否则保留最后一行（可能不完整）
      if (done) {
        buffer = "";
      } else {
        buffer = lines.pop() || "";
      }

      for (const line of lines) {
        if (!line.trim() || !line.startsWith("data:")) continue;

        try {
          const jsonStr = line.substring(5).trim();
          if (jsonStr) {
            const eventData = JSON.parse(jsonStr);
            onEvent(eventData);
          }
        } catch (e) {
          console.error("解析SSE事件失败:", e, line);
        }
      }

      if (done) break;
    }
  },
};
