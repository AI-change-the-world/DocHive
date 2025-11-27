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
   * 预览Agent执行计划
   */
  previewExecution(data: AgentMarkdownRequest) {
    return request.post("/agents/preview", data);
  },

  /**
   * 获取Markdown模板
   */
  getMarkdownTemplate() {
    return request.get("/agents/markdown-template");
  },

  /**
   * 执行Agent
   */
  executeAgent(data: any) {
    return request.post("/agents/execute", data);
  },
};
