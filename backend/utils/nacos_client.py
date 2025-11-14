import yaml
from typing import Dict, Any, Optional
from loguru import logger
import asyncio
from v2.nacos import NacosConfigService, ClientConfigBuilder, ConfigParam


class NacosClient:
    """Nacos配置客户端（支持异步）"""

    def __init__(self, host: str, port: int, namespace: str = "", group: str = "DEFAULT_GROUP"):
        self.host = host
        self.port = port
        self.namespace = namespace
        self.group = group
        self.server_addresses = f"{host}:{port}"
        self.client = None
        self.client_config = None
        
        try:
            # 构建客户端配置
            self.client_config = (ClientConfigBuilder()
                           .server_address(self.server_addresses)
                           .namespace_id(namespace)
                           .build())
        except Exception as e:
            logger.error(f"初始化Nacos客户端配置失败: {e}")
            raise

    async def _ensure_client(self):
        """确保客户端已初始化"""
        if self.client is None and self.client_config:
            try:
                self.client = await NacosConfigService.create_config_service(self.client_config)
            except Exception as e:
                logger.error(f"创建Nacos配置服务失败: {e}")
                raise

    async def get_config(self, data_id: str) -> Optional[Dict[str, Any]]:
        """
        异步从Nacos获取配置
        
        Args:
            data_id: 配置的dataId
            
        Returns:
            配置字典或None（如果获取失败）
        """
        try:
            await self._ensure_client()
            
            if not self.client:
                logger.error("Nacos客户端未初始化")
                return None
            
            # 使用官方异步SDK获取配置
            config_param = ConfigParam(data_id=data_id, group=self.group)
            config_str = await self.client.get_config(config_param)
            
            # 解析YAML配置
            if config_str:
                config_data = yaml.safe_load(config_str)
                return config_data if isinstance(config_data, dict) else {}
            return {}
            
        except Exception as e:
            logger.error(f"从Nacos获取配置失败: {e}")
            return None

    async def get_config_value(self, data_id: str, key_path: str, default=None):
        """
        异步获取配置中的特定值
        
        Args:
            data_id: 配置的dataId
            key_path: 键路径，例如 "app.name" 或 "database.url"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        config = await self.get_config(data_id)
        if not config:
            return default
            
        keys = key_path.split(".")
        value = config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default


# 全局Nacos客户端实例
nacos_client: Optional[NacosClient] = None


def init_nacos_client(host: str, port: int, namespace: str = "", group: str = "DEFAULT_GROUP"):
    """初始化Nacos客户端"""
    global nacos_client
    nacos_client = NacosClient(host, port, namespace, group)


def get_nacos_client() -> Optional[NacosClient]:
    """获取Nacos客户端实例"""
    return nacos_client