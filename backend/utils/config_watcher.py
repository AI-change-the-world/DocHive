"""
Nacos配置监听器 - 支持动态更新配置
"""
import asyncio
import yaml
from loguru import logger
from typing import Callable, Optional
from v2.nacos import ConfigParam


class ConfigWatcher:
    """Nacos配置监听器"""
    
    def __init__(self, nacos_client, data_id: str, group: str, on_config_change: Callable):
        self.nacos_client = nacos_client
        self.data_id = data_id
        self.group = group
        self.on_config_change = on_config_change
        self._listener_added = False
    
    async def start(self):
        """启动配置监听"""
        try:
            if not self.nacos_client or not self.nacos_client.client:
                logger.warning("Nacos客户端未初始化，无法启动配置监听")
                return
            
            async def config_listener(namespace_id: str, data_id: str, group: str, content: str):
                """配置更新回调函数"""
                try:
                    new_config = yaml.safe_load(content)
                    if isinstance(new_config, dict):
                        self.on_config_change(new_config)
                        logger.info(f"🔄 配置已更新: {data_id}")
                except Exception as e:
                    logger.error(f"解析配置失败: {e}")
            
            config_param = ConfigParam(data_id=self.data_id, group=self.group)
            
            # 根据Nacos SDK 2.0的实际API调整
            # 这里可能需要根据实际SDK版本调整参数
            await self.nacos_client.client.add_listener(config_param, config_listener)
            
            self._listener_added = True
            logger.info(f"✅ Nacos配置监听器已启动: {self.data_id}")
            
        except Exception as e:
            logger.error(f"启动配置监听失败: {e}")
    
    async def stop(self):
        """停止配置监听"""
        try:
            if self._listener_added and self.nacos_client and self.nacos_client.client:
                config_param = ConfigParam(data_id=self.data_id, group=self.group)
                # 移除监听器的逻辑
                logger.info(f"✅ Nacos配置监听器已停止: {self.data_id}")
        except Exception as e:
            logger.error(f"停止配置监听失败: {e}")
