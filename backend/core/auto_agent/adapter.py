"""
DocHive 与 auto_agent 框架的适配器

简化版 - 大部分逻辑已移至 auto_agent.ExecutionEngine
DocHive 只需要提供：
- ToolContext: 封装数据库、ES 等依赖
- LLM 客户端适配器
"""

from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from core.tools.base import ToolContext, execute_tool


class DocHiveToolExecutor:
    """
    DocHive 工具执行器 - 适配 auto_agent 的工具调用接口
    """

    def __init__(
        self,
        db: AsyncSession,
        es_client: Any = None,
        es_index: str = "dochive_documents",
        template_id: Optional[int] = None,
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ):
        self.ctx = ToolContext(
            db=db,
            es_client=es_client,
            es_index=es_index,
            template_id=template_id,
            user_id=user_id,
            session_id=session_id,
        )

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        return await execute_tool(tool_name, arguments, self.ctx)


class DocHiveLLMClientAdapter:
    """
    LLM 客户端适配器 - 将 DocHive 的 LLM 客户端适配为 auto_agent 接口
    """

    def __init__(self, dochive_llm_client, db: AsyncSession):
        self.client = dochive_llm_client
        self.db = db

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """调用 LLM"""
        return await self.client.chat_completion(
            messages=messages,
            db=self.db,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def extract_json(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """调用 LLM 并提取 JSON"""
        return await self.client.extract_json_response(
            messages=messages,
            db=self.db,
            max_tokens=max_tokens,
        )
