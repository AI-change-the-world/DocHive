import json
import time
from typing import Callable

from fastapi import Request, Response
from loguru import logger
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware

import database
from models.database_models import OperationLog
from utils.security import decode_token


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志记录中间件"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理每个请求并记录日志"""
        start_time = time.time()

        # 获取客户端IP
        client_ip = request.client.host if request.client else None
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        # 获取请求参数
        request_params = await self._get_request_params(request)

        # 执行请求
        response = await call_next(request)

        # 计算请求耗时
        process_time = time.time() - start_time

        # 异步写入日志到数据库
        try:
            await self._log_request(
                request=request,
                response=response,
                client_ip=client_ip,
                process_time=process_time,
                request_params=request_params,
            )
        except Exception as e:
            # 日志记录失败不应影响正常请求
            logger.error(f"记录请求日志失败: {e}")

        return response

    async def _get_request_params(self, request: Request) -> dict:
        """获取请求参数"""
        params = {}

        # 获取查询参数
        if request.query_params:
            params["query"] = dict(request.query_params)

        # 获取路径参数
        if request.path_params:
            params["path"] = dict(request.path_params)

        # 获取请求体（仅对非 GET 请求）
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            try:
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    # 读取请求体并缓存，避免二次读取问题
                    body_bytes = await request.body()
                    if body_bytes:
                        try:
                            body_data = json.loads(body_bytes.decode())
                            # 过滤敏感信息（如密码）
                            if isinstance(body_data, dict):
                                filtered_body = {
                                    k: "***" if "password" in k.lower() else v
                                    for k, v in body_data.items()
                                }
                                params["body"] = filtered_body
                            else:
                                params["body"] = body_data
                        except json.JSONDecodeError:
                            params["body"] = "<invalid json>"
            except Exception as e:
                logger.debug(f"获取请求体失败: {e}")

        return params

    async def _log_request(
        self,
        request: Request,
        response: Response,
        client_ip: str,
        process_time: float,
        request_params: dict,
    ):
        """将请求日志写入数据库"""
        # 只记录 API 请求,排除静态资源和健康检查
        path = request.url.path
        if path in [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/",
        ] or path.startswith("/static"):
            return

        # 从 JWT 中获取用户信息
        user_id = None
        try:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
                # 需要从 request.app.state.config 获取配置
                if hasattr(request.app.state, "config"):
                    from utils.security import decode_token

                    payload = decode_token(token, request.app.state.config)
                    if payload:
                        user_id = payload.get("user_id")
        except Exception as e:
            logger.debug(f"解析 JWT 失败: {e}")

        # 解析 action 和 resource_type
        action, resource_type = self._parse_request_info(request)

        # 构建详细信息
        details = {
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "process_time": round(process_time, 3),
            "user_agent": request.headers.get("User-Agent", ""),
        }

        # 将请求参数和响应数据序列化为 JSON
        request_params_str = (
            json.dumps(request_params, ensure_ascii=False) if request_params else None
        )

        # 写入数据库
        # 运行时动态获取 AsyncSessionLocal，避免初始化顺序问题
        if database.AsyncSessionLocal is None:
            logger.debug("数据库尚未初始化，跳过日志记录")
            return

        async with database.AsyncSessionLocal() as session:
            try:
                log_entry = OperationLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    request_params=request_params_str,
                    details=json.dumps(details, ensure_ascii=False),
                    ip_address=client_ip,
                )
                session.add(log_entry)
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"写入操作日志失败: {e}")

    def _parse_request_info(self, request: Request) -> tuple[str, str]:
        """解析请求信息,提取 action, resource_type"""
        method = request.method
        path = request.url.path

        # 默认值
        action = method.lower()
        resource_type = "unknown"

        # 根据路径解析资源类型
        if "/templates" in path:
            resource_type = "template"
        elif "/documents" in path:
            resource_type = "document"
        elif "/config" in path:
            resource_type = "config"
        elif "/document-types" in path:
            resource_type = "document_type"
        elif "/auth" in path:
            resource_type = "auth"
        elif "/qa" in path:
            resource_type = "qa"

        # 根据 HTTP 方法映射 action
        action_mapping = {
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete",
            "GET": "read",
        }
        action = action_mapping.get(method, method.lower())

        # 特殊操作识别
        if "/classify" in path:
            action = "classify"
        elif "/extract" in path:
            action = "extract"
        elif "/search" in path:
            action = "search"
        elif "/login" in path:
            action = "login"
        elif "/logout" in path:
            action = "logout"

        return action, resource_type
