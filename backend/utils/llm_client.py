from config import get_settings
import json
from typing import Dict, Any, Optional, List
from openai import OpenAI
import time
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()


class LLMClient:
    """大语言模型客户端（同步版）"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.default_model = settings.DEFAULT_MODEL

        # 自动根据 provider 初始化兼容 openai 的客户端
        if self.provider == "openai":
            self.client = OpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL.rstrip("/"),
            )
        elif self.provider == "deepseek":
            self.client = OpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL.rstrip("/"),
            )
        else:
            raise ValueError(f"不支持的 LLM 提供商: {self.provider}")

    async def _log_llm_call(
        self,
        db: Optional[AsyncSession],
        messages: List[Dict[str, str]],
        model: str,
        output_content: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: int,
        status: str = "success",
        error_message: Optional[str] = None,
        user_id: Optional[int] = None,
    ):
        """记录LLM调用日志"""
        if db is None:
            return

        try:
            from models.database_models import LLMLog

            log = LLMLog(
                provider=self.provider,
                model=model,
                input_messages=messages,
                output_content=output_content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                status=status,
                error_message=error_message,
                user_id=user_id,
            )
            db.add(log)
            await db.commit()
        except Exception as e:
            print(f"Failed to log LLM call: {e}")
            # 不影响主流程
            pass

    async def chat_completion(
        self,
        messages: List[Dict[str, str]] | str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[int] = None,
    ) -> str:
        """
        调用 LLM 完成对话

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            response_format: 响应格式（如 {"type": "json_object"}）
            db: 数据库会话（用于记录日志）
            user_id: 调用用户ID
        """
        model = model or self.default_model
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        start_time = time.time()
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            output_content = response.choices[0].message.content

            # 记录日志
            if db is not None:
                await self._log_llm_call(
                    db=db,
                    messages=messages,
                    model=model,
                    output_content=output_content,
                    prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                    completion_tokens=response.usage.completion_tokens if response.usage else 0,
                    total_tokens=response.usage.total_tokens if response.usage else 0,
                    duration_ms=duration_ms,
                    status="success",
                    user_id=user_id,
                )

            return output_content

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 记录错误日志
            if db is not None:
                await self._log_llm_call(
                    db=db,
                    messages=messages,
                    model=model,
                    output_content="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    duration_ms=duration_ms,
                    status="error",
                    error_message=str(e),
                    user_id=user_id,
                )
            
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def extract_json_response(
        self,
        messages: List[Dict[str, str]] | str,
        model: Optional[str] = None,
        db: Optional[AsyncSession] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        调用 LLM 并解析 JSON 响应

        Args:
            messages: 消息列表
            model: 模型名称
            db: 数据库会话
            user_id: 调用用户ID
        Returns:
            解析后的 JSON 对象
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        try:
            response = await self.chat_completion(
                messages,
                model=model,
                temperature=0.3,
                response_format={"type": "json_object"},
                db=db,
                user_id=user_id,
            )
        except Exception:
            # 不支持 json_object 时回退到普通模式
            response = await self.chat_completion(
                messages,
                model=model,
                temperature=0.3,
                db=db,
                user_id=user_id,
            )

        # 解析 JSON 内容
        try:
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()

            return json.loads(response)
        except json.JSONDecodeError as e:
            raise Exception(f"JSON 解析失败: {str(e)}, 响应内容: {response}")



# 全局实例
llm_client = LLMClient()
