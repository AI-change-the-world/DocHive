"""
智能体执行报告生成器

用于生成可视化的执行过程报告，支持 Markdown 和 HTML 格式导出
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class ExecutionReportGenerator:
    """智能体执行报告生成器"""

    @staticmethod
    def generate_report_data(
        agent_name: str,
        query: str,
        steps: List[Dict[str, Any]],
        step_history: List[Dict[str, Any]],
        final_result: Dict[str, Any],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        生成结构化的执行报告数据

        Args:
            agent_name: 智能体名称
            query: 用户查询
            steps: 规划的执行步骤
            step_history: 实际执行历史
            final_result: 最终执行结果
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            结构化的报告数据
        """
        # 构建步骤执行状态映射
        step_status_map = {}
        for record in step_history:
            step_num = record.get("step")
            success = record.get("result", {}).get("success", False)
            step_status_map[step_num] = {
                "success": success,
                "result": record.get("result", {}),
                "description": record.get("description", ""),
                "arguments": record.get("arguments", {}),  # 新增: 工具参数
                "llm_calls": record.get("llm_calls", []),  # 新增: LLM调用记录
            }

        # 构建步骤详情
        steps_detail = []
        for step in steps:
            step_num = step.get("step")
            tool_name = step.get("name", "unknown")
            description = step.get("description", "")
            expectations = step.get("expectations", "")

            status_info = step_status_map.get(step_num, {})
            success = status_info.get("success", None)  # None 表示未执行
            result = status_info.get("result", {})

            # 状态判断
            if success is None:
                status = "pending"
            elif success:
                status = "success"
            else:
                status = "failed"

            steps_detail.append({
                "step": step_num,
                "name": tool_name,
                "description": description,
                "expectations": expectations,
                "status": status,
                "arguments": status_info.get("arguments", {}),  # 新增: 工具参数
                "result": ExecutionReportGenerator._compress_result(result),
                "llm_calls": status_info.get("llm_calls", []),  # 新增: LLM调用记录
                "error": result.get("error") if not success else None,
            })

        # 统计信息
        total_steps = len(steps)
        executed_steps = len(step_history)
        successful_steps = sum(1 for r in step_history if r.get(
            "result", {}).get("success", False))
        failed_steps = executed_steps - successful_steps

        # 计算执行时间
        duration = None
        if start_time and end_time:
            duration = (end_time - start_time).total_seconds()

        return {
            "agent_name": agent_name,
            "query": query[:500] + "..." if len(query) > 500 else query,
            "generated_at": datetime.now().isoformat(),
            "start_time": start_time.isoformat() if start_time else None,
            "end_time": end_time.isoformat() if end_time else None,
            "duration_seconds": duration,
            "statistics": {
                "total_steps": total_steps,
                "executed_steps": executed_steps,
                "successful_steps": successful_steps,
                "failed_steps": failed_steps,
                "success_rate": round(successful_steps / executed_steps * 100, 1) if executed_steps > 0 else 0,
            },
            "steps": steps_detail,
            "final_result": ExecutionReportGenerator._compress_result(final_result),
            "mermaid_diagram": ExecutionReportGenerator._generate_mermaid(steps, step_history),
        }

    @staticmethod
    def generate_markdown_report(
        agent_name: str,
        query: str,
        steps: List[Dict[str, Any]],
        step_history: List[Dict[str, Any]],
        final_result: Dict[str, Any],
    ) -> str:
        """生成Markdown格式的执行报告"""

        lines = [
            f"# 智能体执行报告",
            f"",
            f"**Agent**: {agent_name}",
            f"**执行时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**用户输入**: {query[:200]}{'...' if len(query) > 200 else ''}",
            f"",
            f"---",
            f"",
            f"## 执行计划",
            f"",
        ]

        # 执行计划表格
        lines.append("| 步骤 | 工具 | 描述 | 期望 |")
        lines.append("|------|------|------|------|")
        for step in steps:
            desc = step.get("description", "")[:50]
            expectations = step.get("expectations", "-")
            if expectations and len(expectations) > 30:
                expectations = expectations[:30] + "..."
            lines.append(
                f"| {step.get('step')} | `{step.get('name')}` | "
                f"{desc} | {expectations if expectations else '-'} |"
            )

        lines.extend([
            f"",
            f"## 执行流程图",
            f"",
            f"```mermaid",
            ExecutionReportGenerator._generate_mermaid(steps, step_history),
            f"```",
            f"",
            f"## 执行详情",
            f"",
        ])

        # 构建步骤执行状态映射
        step_status_map = {}
        for record in step_history:
            step_num = record.get("step")
            step_status_map[step_num] = record

        # 每个步骤的详细执行结果
        for step in steps:
            step_num = step.get("step", 0)
            tool_name = step.get("name", "unknown")
            record = step_status_map.get(step_num, {})
            result = record.get("result", {})
            success = result.get("success", False) if record else None

            if success is None:
                status_icon = "⏳"
                status_text = "未执行"
            elif success:
                status_icon = "✅"
                status_text = "成功"
            else:
                status_icon = "❌"
                status_text = "失败"

            lines.extend([
                f"### 步骤 {step_num}: {tool_name} {status_icon}",
                f"",
                f"**描述**: {step.get('description', '')}",
                f"",
                f"**状态**: {status_text}",
                f"",
            ])

            if record:
                lines.extend([
                    f"**执行结果**:",
                    f"```json",
                    ExecutionReportGenerator._format_result(result),
                    f"```",
                    f"",
                ])

                # 如果失败，显示错误信息
                if not success:
                    error = result.get("error", "未知错误")
                    lines.extend([
                        f"> ⚠️ **错误**: {error}",
                        f"",
                    ])

        # 最终结果
        lines.extend([
            f"---",
            f"",
            f"## 最终结果",
            f"",
            f"```json",
            ExecutionReportGenerator._format_result(final_result),
            f"```",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_html_report(
        agent_name: str,
        query: str,
        steps: List[Dict[str, Any]],
        step_history: List[Dict[str, Any]],
        final_result: Dict[str, Any],
    ) -> str:
        """生成HTML格式的执行报告（含交互式可视化）"""

        # 构建步骤执行状态映射
        step_status_map = {}
        for record in step_history:
            step_num = record.get("step")
            step_status_map[step_num] = record

        # 统计信息
        total = len(steps)
        executed = len(step_history)
        successful = sum(1 for r in step_history if r.get(
            "result", {}).get("success", False))
        failed = executed - successful

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智能体执行报告 - {agent_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
            max-width: 1200px; 
            margin: 0 auto; 
            padding: 20px; 
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
        }}
        .card {{ 
            background: white; 
            border-radius: 12px; 
            padding: 24px; 
            margin: 16px 0; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.1);
        }}
        h1 {{ 
            color: #1a1a2e; 
            margin: 0 0 8px 0;
            font-size: 28px;
        }}
        h2 {{ 
            color: #16213e; 
            border-bottom: 2px solid #e8e8e8; 
            padding-bottom: 12px; 
            margin-top: 0;
            font-size: 20px;
        }}
        .header {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 32px;
            border-radius: 12px;
            margin-bottom: 20px;
        }}
        .header h1 {{ color: white; }}
        .header p {{ margin: 8px 0; opacity: 0.9; }}
        .stats-grid {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); 
            gap: 16px; 
            margin: 20px 0;
        }}
        .stat-item {{ 
            background: #f8f9fa; 
            padding: 20px; 
            border-radius: 8px; 
            text-align: center;
            border: 1px solid #e9ecef;
        }}
        .stat-value {{ 
            font-size: 32px; 
            font-weight: bold; 
            color: #667eea;
        }}
        .stat-value.success {{ color: #22c55e; }}
        .stat-value.failed {{ color: #ef4444; }}
        .stat-label {{ 
            color: #6c757d; 
            font-size: 14px; 
            margin-top: 4px;
        }}
        .step {{ 
            border-left: 4px solid #e9ecef; 
            padding: 16px 16px 16px 20px; 
            margin: 16px 0; 
            background: #fafafa;
            border-radius: 0 8px 8px 0;
            transition: all 0.3s ease;
        }}
        .step:hover {{ 
            background: #f0f0f0;
            transform: translateX(4px);
        }}
        .step.success {{ border-left-color: #22c55e; background: #f0fdf4; }}
        .step.failed {{ border-left-color: #ef4444; background: #fef2f2; }}
        .step.pending {{ border-left-color: #f59e0b; background: #fffbeb; }}
        .step-header {{ 
            display: flex; 
            align-items: center; 
            gap: 12px; 
            cursor: pointer;
            user-select: none;
        }}
        .step-icon {{ 
            font-size: 24px; 
            width: 32px;
            text-align: center;
        }}
        .step-info {{ flex: 1; }}
        .step-name {{ 
            font-weight: 600; 
            color: #1a1a2e; 
            font-size: 16px;
        }}
        .step-desc {{ 
            color: #6c757d; 
            font-size: 14px; 
            margin-top: 4px;
        }}
        .step-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
        }}
        .step-badge.success {{ background: #dcfce7; color: #166534; }}
        .step-badge.failed {{ background: #fee2e2; color: #991b1b; }}
        .step-badge.pending {{ background: #fef3c7; color: #92400e; }}
        .result-box {{ 
            background: #1e1e1e; 
            border-radius: 8px; 
            padding: 16px; 
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace; 
            font-size: 13px; 
            overflow-x: auto;
            color: #d4d4d4;
            margin-top: 12px;
            display: none;
        }}
        .result-box.show {{ display: block; }}
        .collapsible {{ cursor: pointer; }}
        .mermaid {{ 
            text-align: center; 
            background: white;
            padding: 20px;
            border-radius: 8px;
        }}
        .query-box {{
            background: #f8f9fa;
            padding: 16px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
            margin: 12px 0;
            font-size: 14px;
            color: #495057;
        }}
        .timestamp {{
            color: #6c757d;
            font-size: 13px;
        }}
        .toggle-btn {{
            background: #667eea;
            color: white;
            border: none;
            padding: 4px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}
        .toggle-btn:hover {{ background: #5a67d8; }}
        .error-msg {{
            background: #fee2e2;
            color: #991b1b;
            padding: 12px;
            border-radius: 8px;
            margin-top: 12px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 智能体执行报告</h1>
        <p><strong>Agent:</strong> {agent_name}</p>
        <p class="timestamp">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="card">
        <h2>📋 查询内容</h2>
        <div class="query-box">
            {query[:500]}{'...' if len(query) > 500 else ''}
        </div>
    </div>
    
    <div class="card">
        <h2>📊 执行统计</h2>
        <div class="stats-grid">
            <div class="stat-item">
                <div class="stat-value">{total}</div>
                <div class="stat-label">计划步骤</div>
            </div>
            <div class="stat-item">
                <div class="stat-value">{executed}</div>
                <div class="stat-label">已执行</div>
            </div>
            <div class="stat-item">
                <div class="stat-value success">{successful}</div>
                <div class="stat-label">成功</div>
            </div>
            <div class="stat-item">
                <div class="stat-value failed">{failed}</div>
                <div class="stat-label">失败</div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>🗺️ 执行流程图</h2>
        <div class="mermaid">
{ExecutionReportGenerator._generate_mermaid(steps, step_history)}
        </div>
    </div>
    
    <div class="card">
        <h2>📝 执行详情</h2>
{ExecutionReportGenerator._generate_steps_html(steps, step_status_map)}
    </div>
    
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default' }});
        
        document.querySelectorAll('.step-header').forEach(header => {{
            header.addEventListener('click', () => {{
                const resultBox = header.parentElement.querySelector('.result-box');
                if (resultBox) {{
                    resultBox.classList.toggle('show');
                }}
            }});
        }});
    </script>
</body>
</html>"""
        return html

    @staticmethod
    def _generate_mermaid(steps: List[Dict], history: List[Dict]) -> str:
        """生成执行流程的Mermaid图（包含实际执行状态）"""
        lines = ["graph TD"]
        lines.append("    Start([🚀 开始])")

        # 构建成功/失败状态映射
        status_map = {}
        for record in history:
            step_num = record.get("step")
            success = record.get("result", {}).get("success", False)
            status_map[step_num] = "success" if success else "failed"

        prev_node = "Start"
        for step in steps:
            step_num = step.get("step")
            tool_name = step.get("name", "unknown")
            desc = step.get("description", "")[:20]
            status = status_map.get(step_num, "pending")

            if status == "success":
                icon = "✅"
            elif status == "failed":
                icon = "❌"
            else:
                icon = "⏳"

            node_id = f"Step{step_num}"
            # 避免特殊字符导致 mermaid 解析错误
            safe_desc = desc.replace('"', "'").replace('\n', ' ')
            lines.append(
                f'    {prev_node} --> {node_id}["{icon} {step_num}. {tool_name}"]')
            prev_node = node_id

        lines.append(f"    {prev_node} --> End([🏁 结束])")
        return "\n".join(lines)

    @staticmethod
    def _generate_steps_html(steps: List[Dict], status_map: Dict) -> str:
        """生成步骤详情HTML"""
        html_parts = []

        for step in steps:
            step_num = step.get("step", 0)
            tool_name = step.get("name", "unknown")
            desc = step.get("description", "")
            expectations = step.get("expectations", "")

            record = status_map.get(step_num, {})
            result = record.get("result", {}) if record else {}
            success = result.get("success", None) if record else None

            if success is None:
                status_class = "pending"
                icon = "⏳"
                badge_text = "待执行"
            elif success:
                status_class = "success"
                icon = "✅"
                badge_text = "成功"
            else:
                status_class = "failed"
                icon = "❌"
                badge_text = "失败"

            result_json = json.dumps(
                result, ensure_ascii=False, indent=2, default=str)
            if len(result_json) > 3000:
                result_json = result_json[:3000] + "\n... (已截断)"

            error_html = ""
            if not success and result.get("error"):
                error_html = f'<div class="error-msg">⚠️ {result.get("error")}</div>'

            html_parts.append(f"""
        <div class="step {status_class}">
            <div class="step-header collapsible">
                <span class="step-icon">{icon}</span>
                <div class="step-info">
                    <div class="step-name">步骤 {step_num}: {tool_name}</div>
                    <div class="step-desc">{desc}</div>
                </div>
                <span class="step-badge {status_class}">{badge_text}</span>
            </div>
            <div class="result-box"><pre>{result_json}</pre></div>
            {error_html}
        </div>
            """)

        return "\n".join(html_parts)

    @staticmethod
    def _compress_result(result: Dict[str, Any], max_len: int = 1000) -> Dict[str, Any]:
        """压缩结果，移除过大的字段"""
        if not result:
            return {}

        compressed = {}
        for key, value in result.items():
            if key in ["documents", "extracted_content", "composed_document", "reviewed_document"]:
                # 大型字段只保留摘要
                if isinstance(value, list):
                    compressed[key] = f"[{len(value)} items]"
                elif isinstance(value, dict):
                    if "content" in value:
                        word_count = len(value.get("content", ""))
                        compressed[key] = {
                            "title": value.get("title", "")[:100],
                            "word_count": word_count,
                            "_note": "内容已省略"
                        }
                    else:
                        compressed[key] = f"{{...}} ({len(str(value))} chars)"
                else:
                    compressed[key] = value
            elif isinstance(value, str) and len(value) > max_len:
                compressed[key] = value[:max_len] + "..."
            else:
                compressed[key] = value

        return compressed

    @staticmethod
    def _format_result(result: Dict, max_len: int = 2000) -> str:
        """格式化结果JSON"""
        try:
            text = json.dumps(result, ensure_ascii=False,
                              indent=2, default=str)
            if len(text) > max_len:
                return text[:max_len] + "\n... (已截断)"
            return text
        except Exception:
            return str(result)[:max_len]
