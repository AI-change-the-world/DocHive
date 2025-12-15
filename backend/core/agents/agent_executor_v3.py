"""
Agent 执行器 V3 - 完全基于 auto_agent 框架

核心改进：
1. 使用 auto_agent.core.planner.TaskPlanner 进行动态规划
2. 使用 auto_agent.core.executor.ExecutionEngine 执行（流式）
3. DocHive 只提供工具上下文和执行记录存储
4. 不再重复实现 _build_arguments 和 _update_state，复用 ExecutionEngine
"""

from typing import Any, AsyncGenerator, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

# auto_agent 核心组件
from auto_agent import (
    TaskPlanner,
    ExecutionEngine,
    ExecutionContext,
    ExecutionPlan,
    PlanStep,
    SubTaskResult,
    get_global_registry,
    RetryConfig,
)

# DocHive 组件
from core.tools.base import ToolContext, execute_tool
from services.execution_record_service import ExecutionRecordService


class DocHiveLLMAdapter:
    """适配 DocHive 的 LLM 客户端到 auto_agent 接口"""

    def __init__(self, dochive_client, db: AsyncSession):
        self.client = dochive_client
        self.db = db

    async def chat(self, messages: List[Dict], temperature: float = 0.7, max_tokens: int = 4096) -> str:
        return await self.client.chat_completion(messages=messages, db=self.db, temperature=temperature, max_tokens=max_tokens)

    async def extract_json(self, messages: List[Dict], max_tokens: int = 4096) -> Dict:
        return await self.client.extract_json_response(messages=messages, db=self.db, max_tokens=max_tokens)


class AgentExecutorV3:
    """
    Agent 执行器 V3 - 完全基于 auto_agent 框架

    核心改进：
    - 规划逻辑使用 auto_agent.core.planner.TaskPlanner
    - 执行逻辑使用 auto_agent.core.executor.ExecutionEngine.execute_plan_stream
    - DocHive 只负责：工具上下文、执行记录存储
    - 不再重复实现参数构造和状态更新，复用 ExecutionEngine
    """

    @staticmethod
    async def execute(
        agent,  # CustomAgent 数据库模型
        query: str,
        template_id: int,
        session_id: Optional[str],
        db: AsyncSession,
        es_client,
        es_index: str = "dochive_documents",
        user_id: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行 Agent（流式返回事件）"""
        logger.info(f"🚀 开始执行 Agent V3: {agent.name}")

        # 1. 创建执行记录
        record = await ExecutionRecordService.create_record(
            db=db,
            agent_id=agent.id,
            agent_name=agent.name,
            query=query,
            template_id=template_id,
            execution_pattern=agent.execution_pattern or "hybrid",
            session_id=session_id or "",
            user_id=user_id,
        )
        record_id = record.id
        logger.info(f"📝 创建执行记录 ID={record_id}")

        # 2. 初始化组件
        from utils.llm_client import get_llm_client
        dochive_llm = get_llm_client()
        llm_adapter = DocHiveLLMAdapter(dochive_llm, db)

        registry = get_global_registry()
        tool_ctx = ToolContext(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            user_id=user_id,
            session_id=session_id,
        )

        # 3. 规划阶段
        yield {"event": "planning", "data": {"message": "正在规划执行步骤..."}}

        planner = TaskPlanner(
            llm_client=llm_adapter,
            tool_registry=registry,
            agent_goals=agent.goals or [],
            agent_constraints=agent.constraints or [],
        )

        initial_plan = agent.initial_plan or []
        plan = await planner.plan(
            query=query,
            user_context="",
            conversation_context="",
            initial_plan=initial_plan,
        )

        if plan.errors:
            yield {"event": "error", "data": {"message": "规划失败", "errors": plan.errors}}
            return

        # 发送执行计划
        steps_dict = [
            {
                "step": i + 1,
                "step_id": s.id,
                "name": s.tool,
                "description": s.description,
                "expectations": s.expectations,
                "on_fail_strategy": s.on_fail_strategy,
                "is_pinned": s.is_pinned,
            }
            for i, s in enumerate(plan.subtasks)
        ]

        yield {
            "event": "execution_plan",
            "data": {
                "agent_name": agent.name,
                "description": agent.description,
                "steps": steps_dict,
                "state_schema": plan.state_schema,
                "warnings": plan.warnings,
            },
        }

        # 4. 初始化状态（包含 Agent 上下文）
        state = {
            "inputs": {"query": query, "template_id": template_id},
            "control": {"iterations": 0, "max_iterations": 20, "failed_steps": []},
            "agent_context": {
                "name": agent.name,
                "description": agent.description,
                "goals": agent.goals or [],
                "constraints": agent.constraints or [],
            },
        }
        for field, defn in plan.state_schema.items():
            if field not in ["inputs", "control", "agent_context"]:
                if isinstance(defn, dict):
                    ftype = defn.get("type", "dict")
                    state[field] = [] if ftype == "list" else ({} if ftype == "dict" else defn.get("default"))
                elif isinstance(defn, str):
                    state[field] = [] if defn == "list" else ({} if defn == "dict" else None)
                else:
                    state[field] = {}

        # 5. 创建 ExecutionEngine 并执行
        # Memory 系统由 auto_agent 框架内部管理，只需传 user_id
        retry_config = RetryConfig(max_retries=3, base_delay=1.0)
        engine = ExecutionEngine(
            tool_registry=registry,
            retry_config=retry_config,
            llm_client=llm_adapter,
            memory_storage_path="./dochive_memory",  # 可选：自定义存储路径
        )

        # 自定义工具执行器（传递 DocHive 的 ToolContext）
        async def tool_executor(tool_name: str, args: Dict) -> Dict:
            if not tool_name:
                return {"success": True}
            return await execute_tool(tool_name, args, tool_ctx)

        # 6. 流式执行并转发事件
        step_history = []
        agent_info = {
            "name": agent.name,
            "description": agent.description,
            "goals": agent.goals or [],
            "constraints": agent.constraints or [],
            "user_id": str(user_id) if user_id else "default",
        }
        async for event in engine.execute_plan_stream(
            plan=plan,
            state=state,
            conversation_id=session_id or "",
            tool_executor=tool_executor,
            agent_info=agent_info,
        ):
            # 记录步骤历史
            if event["event"] == "stage_complete":
                step_history.append({
                    "step": event["data"]["step"],
                    "name": event["data"]["name"],
                    "description": event["data"]["description"],
                    "result": event["data"]["result"],
                })

            # 转发事件给前端
            if event["event"] != "execution_complete":
                yield event

        # 7. 生成答案
        final_doc = state.get("reviewed_document") or state.get("composed_document")
        documents = state.get("documents", [])

        yield {
            "event": "answer",
            "data": {
                "answer": "执行完成" if final_doc or documents else "执行完成，但未生成结果",
                "document": final_doc,
                "documents": documents,
            },
        }

        # 8. 生成报告
        from core.agents.execution_report import ExecutionReportGenerator

        final_result = {
            "composed_document": state.get("composed_document"),
            "reviewed_document": state.get("reviewed_document"),
            "documents": state.get("documents"),
        }

        report_data = ExecutionReportGenerator.generate_report_data(
            agent_name=agent.name, query=query, steps=steps_dict, step_history=step_history, final_result=final_result
        )
        html_report = ExecutionReportGenerator.generate_html_report(
            agent_name=agent.name, query=query, steps=steps_dict, step_history=step_history, final_result=final_result
        )
        markdown_report = ExecutionReportGenerator.generate_markdown_report(
            agent_name=agent.name, query=query, steps=steps_dict, step_history=step_history, final_result=final_result
        )

        yield {"event": "execution_report", "data": {"report": report_data, "html": html_report, "markdown": markdown_report}}

        # 9. 保存执行记录
        try:
            await ExecutionRecordService.complete_record(
                db=db,
                record_id=record_id,
                execution_plan=steps_dict,
                step_history=step_history,
                final_result=final_result,
                report_data=report_data,
                html_report=html_report,
                markdown_report=markdown_report,
                status="completed",
            )
            logger.info(f"✅ 执行记录已保存 ID={record_id}")
        except Exception as e:
            logger.error(f"⚠️ 保存执行记录失败: {e}")

        # 10. 完成
        yield {
            "event": "done",
            "data": {
                "success": True,
                "message": "Agent执行完成",
                "iterations": state["control"]["iterations"],
                "record_id": record_id,
            },
        }

        logger.info(f"✅ Agent V3 执行完成: {agent.name}")



