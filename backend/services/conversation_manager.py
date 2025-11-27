"""
对话会话管理器 - 基于内存的会话状态管理
支持多轮对话和用户干预
"""

import time
from typing import Any, Dict, List, Optional
from loguru import logger
import asyncio


class ConversationManager:
    """
    内存中的对话会话管理器

    特性：
    1. 基于session_id管理会话状态
    2. 支持多轮对话
    3. 支持用户干预（等待用户输入）
    4. 自动过期清理（默认30分钟无交互）
    """

    def __init__(self, default_ttl: int = 1800):  # 默认30分钟
        """
        初始化会话管理器

        Args:
            default_ttl: 会话默认过期时间（秒）
        """
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl
        self._cleanup_task = None

    def start_cleanup_task(self):
        """启动后台清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_expired_sessions())
            logger.info("🧹 启动会话清理任务")

    async def _cleanup_expired_sessions(self):
        """定期清理过期会话"""
        while True:
            try:
                await asyncio.sleep(300)  # 每5分钟清理一次
                current_time = int(time.time())
                expired_sessions = []

                for session_id, session_data in self._sessions.items():
                    if current_time > session_data.get("expires_at", 0):
                        expired_sessions.append(session_id)

                for session_id in expired_sessions:
                    self._sessions.pop(session_id, None)
                    logger.info(f"🗑️ 清理过期会话: {session_id}")

                if expired_sessions:
                    logger.info(f"🧹 清理了 {len(expired_sessions)} 个过期会话")

            except Exception as e:
                logger.error(f"❌ 清理会话失败: {e}")

    def create_session(
        self,
        session_id: str,
        template_id: int,
        initial_query: str,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        创建新会话

        Args:
            session_id: 会话ID（由前端生成的UUID）
            template_id: 模板ID
            initial_query: 初始查询
            user_id: 用户ID（可选）

        Returns:
            会话数据
        """
        current_time = int(time.time())

        session_data = {
            "session_id": session_id,
            "template_id": template_id,
            "user_id": user_id,
            "created_at": current_time,
            "updated_at": current_time,
            "expires_at": current_time + self._default_ttl,
            "last_interaction_at": current_time,

            # 会话状态
            "status": "active",  # active / waiting_input / completed / error
            "current_step": 0,

            # 执行状态
            "state": {
                "query": initial_query,
                "template_id": template_id,
                "session_id": session_id,
                "execution_pattern": "",
                "reasoning": "",
                "execution_plan": [],
                "tool_results": [],
                "agent_results": [],
                "intermediate_data": {},
                "final_answer": None,
                "documents": [],
                "success": False,
                "error": None,
            },

            # 对话历史
            "messages": [
                {
                    "role": "user",
                    "content": initial_query,
                    "timestamp": current_time,
                }
            ],

            # 用户干预
            "needs_user_input": False,
            "user_input_prompt": None,
            "user_input_type": None,  # refine_query / select_documents / confirm
            "user_input_options": None,
        }

        self._sessions[session_id] = session_data
        logger.info(f"✅ 创建会话: {session_id}, template_id={template_id}")

        return session_data

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话数据

        Args:
            session_id: 会话ID

        Returns:
            会话数据，如果不存在或已过期返回None
        """
        session_data = self._sessions.get(session_id)

        if session_data is None:
            return None

        # 检查是否过期
        current_time = int(time.time())
        if current_time > session_data.get("expires_at", 0):
            self._sessions.pop(session_id, None)
            logger.info(f"🗑️ 会话已过期: {session_id}")
            return None

        return session_data

    def update_session(
        self,
        session_id: str,
        **updates
    ) -> Optional[Dict[str, Any]]:
        """
        更新会话数据

        Args:
            session_id: 会话ID
            **updates: 要更新的字段

        Returns:
            更新后的会话数据，如果会话不存在返回None
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            logger.warning(f"⚠️ 会话不存在: {session_id}")
            return None

        current_time = int(time.time())

        # 更新字段
        session_data.update(updates)

        # 更新时间戳
        session_data["updated_at"] = current_time
        session_data["last_interaction_at"] = current_time
        session_data["expires_at"] = current_time + self._default_ttl

        logger.info(f"🔄 更新会话: {session_id}")
        return session_data

    def update_state(
        self,
        session_id: str,
        state_updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        更新执行状态

        Args:
            session_id: 会话ID
            state_updates: 状态更新

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        # 更新state字段
        session_data["state"].update(state_updates)

        # 更新时间戳
        current_time = int(time.time())
        session_data["updated_at"] = current_time
        session_data["last_interaction_at"] = current_time
        session_data["expires_at"] = current_time + self._default_ttl

        return session_data

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        添加对话消息

        Args:
            session_id: 会话ID
            role: 角色（user / assistant / system）
            content: 消息内容
            metadata: 额外元数据

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        current_time = int(time.time())

        message = {
            "role": role,
            "content": content,
            "timestamp": current_time,
        }

        if metadata:
            message["metadata"] = metadata

        session_data["messages"].append(message)

        # 更新时间戳
        session_data["updated_at"] = current_time
        session_data["last_interaction_at"] = current_time
        session_data["expires_at"] = current_time + self._default_ttl

        logger.info(f"💬 添加消息: {session_id}, role={role}")
        return session_data

    def request_user_input(
        self,
        session_id: str,
        prompt: str,
        input_type: str,
        options: Optional[List[Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        请求用户输入

        Args:
            session_id: 会话ID
            prompt: 提示用户的问题
            input_type: 输入类型（refine_query / select_documents / confirm）
            options: 可选项列表

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        session_data["status"] = "waiting_input"
        session_data["needs_user_input"] = True
        session_data["user_input_prompt"] = prompt
        session_data["user_input_type"] = input_type
        session_data["user_input_options"] = options

        # 更新时间戳
        current_time = int(time.time())
        session_data["updated_at"] = current_time
        session_data["last_interaction_at"] = current_time
        session_data["expires_at"] = current_time + self._default_ttl

        logger.info(f"⏸️ 请求用户输入: {session_id}, type={input_type}")
        return session_data

    def submit_user_input(
        self,
        session_id: str,
        user_input: Any,
    ) -> Optional[Dict[str, Any]]:
        """
        提交用户输入

        Args:
            session_id: 会话ID
            user_input: 用户输入的内容

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        # 记录用户输入
        self.add_message(
            session_id=session_id,
            role="user",
            content=str(user_input),
            metadata={"type": "user_input"}
        )

        # 清除等待状态
        session_data["status"] = "active"
        session_data["needs_user_input"] = False
        session_data["user_input_prompt"] = None
        session_data["user_input_type"] = None
        session_data["user_input_options"] = None

        # 将用户输入存储到state中，供后续步骤使用
        session_data["state"]["user_input"] = user_input

        logger.info(f"▶️ 用户提交输入: {session_id}")
        return session_data

    def complete_session(
        self,
        session_id: str,
        final_answer: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        完成会话

        Args:
            session_id: 会话ID
            final_answer: 最终答案

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        session_data["status"] = "completed"

        if final_answer:
            session_data["state"]["final_answer"] = final_answer
            self.add_message(
                session_id=session_id,
                role="assistant",
                content=final_answer,
            )

        logger.info(f"✅ 会话完成: {session_id}")
        return session_data

    def error_session(
        self,
        session_id: str,
        error: str,
    ) -> Optional[Dict[str, Any]]:
        """
        标记会话错误

        Args:
            session_id: 会话ID
            error: 错误信息

        Returns:
            更新后的会话数据
        """
        session_data = self.get_session(session_id)

        if session_data is None:
            return None

        session_data["status"] = "error"
        session_data["state"]["error"] = error
        session_data["state"]["success"] = False

        logger.error(f"❌ 会话错误: {session_id}, error={error}")
        return session_data

    def delete_session(self, session_id: str) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        if session_id in self._sessions:
            self._sessions.pop(session_id)
            logger.info(f"🗑️ 删除会话: {session_id}")
            return True
        return False

    def list_sessions(
        self,
        user_id: Optional[int] = None,
        template_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        列出会话

        Args:
            user_id: 按用户ID筛选
            template_id: 按模板ID筛选

        Returns:
            会话列表
        """
        sessions = []
        current_time = int(time.time())

        for session_id, session_data in self._sessions.items():
            # 过滤过期会话
            if current_time > session_data.get("expires_at", 0):
                continue

            # 按条件筛选
            if user_id is not None and session_data.get("user_id") != user_id:
                continue

            if template_id is not None and session_data.get("template_id") != template_id:
                continue

            sessions.append(session_data)

        return sessions

    def get_session_count(self) -> int:
        """获取活跃会话数量"""
        current_time = int(time.time())
        count = sum(
            1 for session_data in self._sessions.values()
            if current_time <= session_data.get("expires_at", 0)
        )
        return count


# 全局单例
_conversation_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    """获取全局会话管理器"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
        _conversation_manager.start_cleanup_task()
    return _conversation_manager
