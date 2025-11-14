import yaml
from typing import Dict, Any, Optional
from loguru import logger
from v2.nacos import NacosConfigService, ClientConfigBuilder, ConfigParam, GRPCConfig


class NacosClient:
    """Nacos配置客户端（支持异步）"""

    def __init__(self, host: str, port: int, namespace: str = "", group: str = "DEFAULT_GROUP"):
        self.host = host
        self.port = port
        self.namespace = namespace
        self.group = group
        self.server_addresses = f"{host}:{port}"
        self.client: Optional[NacosConfigService] = None
        self.client_config = None
        
        # 构建客户端配置
        self.client_config = (
            ClientConfigBuilder()
            .server_address(self.server_addresses)
            .namespace_id(namespace)
            .log_level("INFO")
            .grpc_config(GRPCConfig(grpc_timeout=5000))
            .build()
        )

    async def init_client(self):
        """初始化Nacos配置服务客户端"""
        if self.client is None:
            try:
                if not self.client_config:
                    raise ValueError("Nacos客户端配置未初始化")
                self.client = await NacosConfigService.create_config_service(self.client_config)
                logger.info("✅ Nacos配置服务初始化成功")
            except Exception as e:
                logger.error(f"❌ 创建Nacos配置服务失败: {e}")
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
            if not self.client:
                await self.init_client()
            
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

    async def add_listener(self, data_id: str, listener_callback):
        """添加配置监听器"""
        try:
            if not self.client:
                await self.init_client()
            
            if not self.client:
                logger.error("Nacos客户端未初始化")
                return
            
            await self.client.add_listener(
                data_id=data_id,
                group=self.group,
                listener=listener_callback
            )
            logger.info(f"✅ 配置监听器已添加: {data_id}")
        except Exception as e:
            logger.error(f"添加配置监听器失败: {e}")

    async def shutdown(self):
        """关闭Nacos配置服务"""
        if self.client:
            try:
                await self.client.shutdown()
                logger.info("✅ Nacos配置服务已关闭")
            except Exception as e:
                logger.error(f"关闭Nacos配置服务失败: {e}")


# 全局Nacos客户端实例
nacos_client: Optional[NacosClient] = None


def get_nacos_client() -> Optional[NacosClient]:
    """获取Nacos客户端实例"""
    return nacos_client


async def init_nacos_client(host: str, port: int, namespace: str = "", group: str = "DEFAULT_GROUP"):
    """初始化Nacos客户端"""
    global nacos_client
    nacos_client = NacosClient(host, port, namespace, group)
    await nacos_client.init_client()
    return nacos_client


async def close_nacos_client():
    """关闭Nacos客户端"""
    global nacos_client
    if nacos_client:
        await nacos_client.shutdown()
        nacos_client = None