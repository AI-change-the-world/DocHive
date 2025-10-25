from config import get_settings
import json
from typing import Dict, Any, Optional, List
from openai import OpenAI

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

    def chat_completion(
        self,
        messages: List[Dict[str, str]] | str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        response_format: Optional[Dict] = None,
    ) -> str:
        """
        调用 LLM 完成对话

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成token数
            response_format: 响应格式（如 {"type": "json_object"}）
        """
        model = model or self.default_model
        if isinstance(messages, str)  :
            messages = [{"role": "user", "content": messages}]

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            return response.choices[0].message.content

        except Exception as e:
            raise Exception(f"LLM 调用失败: {str(e)}")

    def extract_json_response(
        self,
        messages: List[Dict[str, str]] | str,
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
        if isinstance(messages, str)  :
            messages = [{"role": "user", "content": messages}]


        try:
            response = self.chat_completion(
                messages,
                model=model,
                temperature=0.3,
                response_format={"type": "json_object"},
            )
        except Exception:
            # 不支持 json_object 时回退到普通模式
            response = self.chat_completion(
                messages,
                model=model,
                temperature=0.3,
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
