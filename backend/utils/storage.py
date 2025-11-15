import opendal
from typing import BinaryIO, Optional
from loguru import logger


class StorageClient:
    """对象存储客户端 (OpenDAL)"""

    def __init__(self):
        self.operator: Optional[opendal.Operator] = None

    def _ensure_initialized(self):
        """确保存储客户端已初始化"""
        if self.operator is not None:
            return

        # 延迟导入配置，确保Nacos配置已加载
        from config import get_settings

        settings = get_settings()

        # 根据配置类型初始化 OpenDAL Operator
        storage_type = settings.STORAGE_TYPE

        if storage_type == "s3":
            self.operator = opendal.Operator(
                "s3",
                bucket=settings.STORAGE_BUCKET,
                endpoint=settings.STORAGE_ENDPOINT,
                region=settings.STORAGE_REGION,
                access_key_id=settings.STORAGE_ACCESS_KEY,
                secret_access_key=settings.STORAGE_SECRET_KEY,
                root=settings.STORAGE_ROOT,
            )
        elif storage_type == "fs":
            # 本地文件系统
            self.operator = opendal.Operator(
                "fs",
                root=settings.STORAGE_ROOT or "./storage",
            )
        elif storage_type == "memory":
            # 内存存储(仅用于测试)
            self.operator = opendal.Operator("memory")
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

        logger.info(f"✅ 存储客户端初始化完成: {storage_type}")

    async def upload_file(
        self,
        file_data: BinaryIO,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        上传文件

        Args:
            file_data: 文件数据流
            object_name: 对象名称（路径）
            content_type: 文件类型

        Returns:
            文件存储路径
        """
        self._ensure_initialized()
        assert self.operator is not None, "存储客户端初始化失败"

        try:
            # 读取文件内容
            content = file_data.read()
            if isinstance(content, str):
                content = content.encode("utf-8")

            # 使用 OpenDAL 写入文件
            self.operator.write(object_name, content)

            # 获取bucket名称
            from config import get_settings

            settings = get_settings()
            return f"{settings.STORAGE_BUCKET}/{object_name}"
        except Exception as e:
            raise Exception(f"文件上传失败: {str(e)}")

    async def download_file(self, object_name: str) -> bytes:
        """下载文件"""
        self._ensure_initialized()
        assert self.operator is not None, "存储客户端初始化失败"

        try:
            data = self.operator.read(object_name)
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data
        except Exception as e:
            raise Exception(f"文件下载失败: {str(e)}")

    async def delete_file(self, object_name: str) -> bool:
        """删除文件"""
        self._ensure_initialized()
        assert self.operator is not None, "存储客户端初始化失败"

        try:
            self.operator.delete(object_name)
            return True
        except Exception:
            return False

    def get_presigned_url(self, object_name: str, expires: int = 3600) -> str:
        """
        获取预签名 URL

        注意: OpenDAL 当前版本不直接支持 presigned URL,
        这里返回一个直接下载链接，实际上需要通过 API 端点提供下载
        """
        # 这里返回一个 API 路径，实际的下载需要通过后端 API
        return f"/api/v1/documents/download/{object_name}"

    def exists(self, object_name: str) -> bool:
        """检查文件是否存在"""
        self._ensure_initialized()
        assert self.operator is not None, "存储客户端初始化失败"

        try:
            stat = self.operator.stat(object_name)
            return stat is not None
        except Exception:
            return False


# 全局实例
storage_client = StorageClient()
