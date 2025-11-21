from typing import BinaryIO, Optional

import opendal
from loguru import logger

from config import DynamicConfig


class StorageClient:
    """对象存储客户端 (OpenDAL)"""

    def __init__(self, config: DynamicConfig):
        """
        初始化存储客户端

        Args:
            config: 动态配置实例
        """
        self.config = config
        storage_type = config.STORAGE_TYPE

        if storage_type == "s3":
            self.operator = opendal.Operator(
                "s3",
                bucket=config.STORAGE_BUCKET,
                endpoint=config.STORAGE_ENDPOINT,
                region=config.STORAGE_REGION,
                access_key_id=config.STORAGE_ACCESS_KEY,
                secret_access_key=config.STORAGE_SECRET_KEY,
                root=config.STORAGE_ROOT,
            )
        elif storage_type == "fs":
            # 本地文件系统
            self.operator = opendal.Operator(
                "fs",
                root=config.STORAGE_ROOT or "./storage",
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

        try:
            # 读取文件内容
            content = file_data.read()
            if isinstance(content, str):
                content = content.encode("utf-8")

            # 使用 OpenDAL 写入文件
            self.operator.write(object_name, content)

            # 返回存储路径
            return f"{self.config.STORAGE_BUCKET}/{object_name}"
        except Exception as e:
            raise Exception(f"文件上传失败: {str(e)}")

    async def download_file(self, object_name: str) -> bytes:
        """下载文件"""

        try:
            data = self.operator.read(object_name)
            if isinstance(data, str):
                data = data.encode("utf-8")
            return data
        except Exception as e:
            raise Exception(f"文件下载失败: {str(e)}")

    async def delete_file(self, object_name: str) -> bool:
        """删除文件"""

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

        try:
            stat = self.operator.stat(object_name)
            return stat is not None
        except Exception:
            return False


# 全局实例（在 app.state 中存储）
_storage_client: Optional[StorageClient] = None


def init_storage_client(config: DynamicConfig) -> StorageClient:
    """初始化存储客户端

    Args:
        config: 动态配置实例

    Returns:
        StorageClient 实例
    """
    global _storage_client
    _storage_client = StorageClient(config)
    return _storage_client


def get_storage_client() -> StorageClient:
    """获取存储客户端

    注意：应该在 lifespan 中调用 init_storage_client 初始化
    """
    if _storage_client is None:
        raise RuntimeError("存储客户端未初始化，请先调用 init_storage_client()")
    return _storage_client
