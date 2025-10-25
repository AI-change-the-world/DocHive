from typing import Dict, Any, Optional
from config import get_settings
import openai
import httpx
import json

settings = get_settings()


class LLMClient:
    """大语言模型客户端"""

    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self.default_model = settings.DEFAULT_MODEL

        if self.provider == "openai":
            self.api_key = settings.OPENAI_API_KEY
            self.base_url = settings.OPENAI_BASE_URL
        elif self.provider == "deepseek":
            self.api_key = settings.DEEPSEEK_API_KEY
            self.base_url = settings.DEEPSEEK_BASE_URL

    async def chat_completion(
        self,
        messages: list[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict] = None,
    ) -> str:
        """
        调用 LLM 完成对话

        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            response_format: 响应格式（如 {"type": "json_object"}）

        Returns:
            模型响应内容
        """
        model = model or self.default_model

        try:
            if self.provider in ["openai", "deepseek"]:
                return await self._openai_compatible_chat(
                    messages, model, temperature, max_tokens, response_format
                )
            else:
                raise ValueError(f"不支持的 LLM 提供商: {self.provider}")

        except Exception as e:
            raise Exception(f"LLM 调用失败: {str(e)}")

    async def _openai_compatible_chat(
        self,
        messages: list[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        response_format: Optional[Dict],
    ) -> str:
        """OpenAI 兼容接口调用"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            response.raise_for_status()
            result = response.json()

            return result["choices"][0]["message"]["content"]

    async def extract_json_response(
        self,
        messages: list[Dict[str, str]],
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        调用 LLM 并解析 JSON 响应

        Args:
            messages: 消息列表
            model: 模型名称

        Returns:
            解析后的 JSON 对象
        """
        # 尝试使用 JSON 模式
        try:
            response = await self.chat_completion(
                messages,
                model=model,
                temperature=0.3,  # 降低温度以获得更稳定的输出
                response_format={"type": "json_object"},
            )
        except:
            # 如果不支持 JSON 模式，使用普通模式
            response = await self.chat_completion(
                messages,
                model=model,
                temperature=0.3,
            )

        # 解析 JSON
        try:
            # 尝试提取 JSON 块
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
