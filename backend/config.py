import asyncio
import os
from typing import Any, List, Optional

import yaml
from loguru import logger
from pydantic_settings import BaseSettings, SettingsConfigDict
from v2.nacos import ClientConfigBuilder, ConfigParam, GRPCConfig, NacosConfigService


class LocalSettings(BaseSettings):
    """静态配置类 - 从.env读取,应用启动前就确定的配置"""

    # 应用基础信息
    APP_NAME: str = "DocHive"
    DOC_HIVE_PORT: int = 8000
    SECRET_KEY: str = "secret_key"

    # Nacos连接配置
    NACOS_HOST: str = "localhost"
    NACOS_PORT: int = 8848
    NACOS_NAMESPACE: str = "public"
    NACOS_GROUP: str = "DEFAULT_GROUP"
    NACOS_DATA_ID: str = "dochive-config.yaml"
    ENABLE_NACOS: bool = True  # 是否启用Nacos配置中心

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


class DynamicConfig:
    """动态配置类 - 从Nacos获取的运行时配置"""

    def __init__(self, local_settings: LocalSettings):
        self._local_settings = local_settings
        self._config_data: dict[str, Any] = {}
        self.nacos_config_service: Optional[NacosConfigService] = None
        self._on_config_change_callbacks: List[callable] = []  # 配置变更回调

    def load_from_yaml(self, yaml_content: str) -> None:
        """从YAML内容加载配置"""
        try:
            new_config = yaml.safe_load(yaml_content)
            if isinstance(new_config, dict):
                old_config = self._config_data.copy()
                self._config_data = new_config
                logger.info("✅ 动态配置已更新")

                # 触发配置变更回调
                self._notify_config_change(old_config, new_config)
        except Exception as e:
            logger.error(f"❌ 解析YAML配置失败: {e}")

    def register_on_change(self, callback: callable) -> None:
        """注册配置变更回调函数

        Args:
            callback: 回调函数,接收 (old_config, new_config) 两个参数
        """
        self._on_config_change_callbacks.append(callback)
        logger.debug(f"注册配置变更回调: {callback.__name__}")

    def _notify_config_change(self, old_config: dict, new_config: dict) -> None:
        """通知所有已注册的回调函数配置已变更"""
        for callback in self._on_config_change_callbacks:
            try:
                callback(old_config, new_config)
            except Exception as e:
                logger.error(f"配置变更回调执行失败 [{callback.__name__}]: {e}")

    def _get_config(self, key_path: str, default: Any = None) -> Any:
        """从配置中获取值，支持环境变量优先"""
        # 优先从环境变量获取
        env_key = key_path.upper().replace(".", "_")
        env_value = os.getenv(env_key)
        if env_value is not None:
            # 尝试转换类型
            if isinstance(default, bool):
                return env_value.lower() in ("true", "1", "yes")
            elif isinstance(default, int):
                try:
                    return int(env_value)
                except ValueError:
                    return default
            return env_value

        # 从Nacos配置中获取
        keys = key_path.split(".")
        value = self._config_data
        try:
            for key in keys:
                value = value[key]
            return value if value is not None else default
        except (KeyError, TypeError):
            return default

    # 静态配置访问(直接从LocalSettings获取)
    @property
    def APP_NAME(self) -> str:
        return self._local_settings.APP_NAME

    @property
    def SECRET_KEY(self) -> str:
        return self._local_settings.SECRET_KEY

    # 动态配置访问(从Nacos获取)
    @property
    def APP_VERSION(self) -> str:
        return self._get_config("app.version", "1.0.0")

    @property
    def DEBUG(self) -> bool:
        return self._get_config("app.debug", True)

    # 数据库配置
    @property
    def DATABASE_URL(self) -> str:
        return self._get_config("database.url", "")

    @property
    def DATABASE_POOL_SIZE(self) -> int:
        return self._get_config("database.pool_size", 20)

    @property
    def DATABASE_MAX_OVERFLOW(self) -> int:
        return self._get_config("database.max_overflow", 10)

    # 搜索引擎配置
    @property
    def SEARCH_ENGINE(self) -> str:
        return self._get_config("search.engine", "database")

    # 对象存储配置
    @property
    def STORAGE_TYPE(self) -> str:
        return self._get_config("storage.type", "s3")

    @property
    def STORAGE_BUCKET(self) -> str:
        return self._get_config("storage.bucket", "")

    @property
    def STORAGE_ENDPOINT(self) -> str:
        return self._get_config("storage.endpoint", "")

    @property
    def STORAGE_REGION(self) -> str:
        return self._get_config("storage.region", "us-east-1")

    @property
    def STORAGE_ACCESS_KEY(self) -> str:
        return self._get_config("storage.access_key", "")

    @property
    def STORAGE_SECRET_KEY(self) -> str:
        return self._get_config("storage.secret_key", "")

    @property
    def STORAGE_ROOT(self) -> str:
        return self._get_config("storage.root", "/")

    # Elasticsearch配置
    @property
    def ELASTICSEARCH_URL(self) -> str:
        return self._get_config("search.elastic_url", "")

    @property
    def ELASTICSEARCH_INDEX(self) -> str:
        return self._get_config("search.elastic_index", "dochive_documents")

    # ClickHouse配置
    @property
    def CLICKHOUSE_HOST(self) -> str:
        return self._get_config("clickhouse.host", "localhost")

    @property
    def CLICKHOUSE_PORT(self) -> int:
        return self._get_config("clickhouse.port", 9000)

    @property
    def CLICKHOUSE_USER(self) -> str:
        return self._get_config("clickhouse.user", "default")

    @property
    def CLICKHOUSE_PASSWORD(self) -> str:
        return self._get_config("clickhouse.password", "")

    @property
    def CLICKHOUSE_DATABASE(self) -> str:
        return self._get_config("clickhouse.database", "dochive")

    # Qdrant配置
    @property
    def QDRANT_HOST(self) -> str:
        return self._get_config("qdrant.host", "localhost")

    @property
    def QDRANT_PORT(self) -> int:
        return self._get_config("qdrant.port", 6333)

    @property
    def QDRANT_COLLECTION(self) -> str:
        return self._get_config("qdrant.collection", "dochive_vectors")

    # LLM配置
    @property
    def LLM_PROVIDER(self) -> str:
        return self._get_config("llm.provider", "openai")

    @property
    def OPENAI_API_KEY(self) -> str:
        return self._get_config("llm.openai_api_key", "")

    @property
    def OPENAI_BASE_URL(self) -> str:
        return self._get_config("llm.openai_base_url", "https://api.openai.com/v1")

    @property
    def DEEPSEEK_API_KEY(self) -> str:
        return self._get_config("llm.deepseek_api_key", "")

    @property
    def DEEPSEEK_BASE_URL(self) -> str:
        return self._get_config("llm.deepseek_base_url", "https://api.deepseek.com/v1")

    @property
    def DEFAULT_MODEL(self) -> str:
        return self._get_config("llm.default_model", "gpt-3.5-turbo")

    # Redis配置
    @property
    def REDIS_URL(self) -> str:
        return self._get_config("redis.url", "redis://localhost:6379/0")

    # JWT配置
    @property
    def JWT_SECRET_KEY(self) -> str:
        return self._get_config("jwt.secret_key", "")

    @property
    def JWT_ALGORITHM(self) -> str:
        return self._get_config("jwt.algorithm", "HS256")

    @property
    def JWT_ACCESS_TOKEN_EXPIRE_MINUTES(self) -> int:
        return self._get_config("jwt.access_minutes", 30)

    @property
    def JWT_REFRESH_TOKEN_EXPIRE_DAYS(self) -> int:
        return self._get_config("jwt.refresh_days", 7)

    # OCR配置
    @property
    def TESSERACT_PATH(self) -> str:
        return self._get_config("ocr.tesseract_path", "")

    # 文件上传配置
    @property
    def MAX_UPLOAD_SIZE(self) -> int:
        return self._get_config("upload.max_size", 52428800)

    @property
    def ALLOWED_EXTENSIONS(self) -> str:
        return self._get_config("upload.allowed", "pdf,docx,txt,md,png,jpg,jpeg")

    # CORS配置
    @property
    def CORS_ORIGINS(self) -> str:
        origins = self._get_config("cors.origins")
        if isinstance(origins, list):
            return ",".join(origins)
        return origins or "http://localhost:3000,http://localhost:5173,http://localhost:15173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    # RAG配置
    @property
    def RAG_MAX_CONTEXT_LENGTH(self) -> int:
        """单次问答最大上下文长度（字符数）。超过此长度会对每个文档单独问答再组合结果"""
        return self._get_config("rag.max_context_length", 20000)


# ==================== 配置初始化函数 ====================


async def create_dynamic_config() -> DynamicConfig:
    """创建并初始化动态配置

    在应用启动时调用,从Nacos加载配置
    """
    # 1. 加载静态配置
    local_settings = LocalSettings()

    # 2. 创建动态配置实例
    config = DynamicConfig(local_settings)

    # 3. 如果启用Nacos,则从Nacos加载配置
    if local_settings.ENABLE_NACOS:
        try:
            await _init_nacos_config(config, local_settings)
        except Exception as e:
            logger.warning(f"⚠️ Nacos配置初始化失败,将使用默认配置: {e}")
    else:
        logger.info("ℹ️ Nacos配置中心已禁用,使用默认配置")

    return config


async def _init_nacos_config(
    config: DynamicConfig, local_settings: LocalSettings
) -> None:
    """初始化Nacos配置(内部函数)"""
    logger.debug(
        f"[Nacos] 连接配置: {local_settings.NACOS_HOST}:{local_settings.NACOS_PORT}, "
        f"namespace={local_settings.NACOS_NAMESPACE}, group={local_settings.NACOS_GROUP}"
    )

    # 构建客户端配置
    client_config = (
        ClientConfigBuilder()
        .server_address(f"{local_settings.NACOS_HOST}:{local_settings.NACOS_PORT}")
        .log_level("INFO")
        .grpc_config(GRPCConfig(grpc_timeout=5000))
        .build()
    )

    # 创建Nacos配置服务
    config.nacos_config_service = await NacosConfigService.create_config_service(
        client_config
    )
    logger.info("✅ Nacos配置服务初始化成功")

    # 加载初始配置
    config_param = ConfigParam(
        data_id=local_settings.NACOS_DATA_ID, group=local_settings.NACOS_GROUP
    )
    yaml_str = await config.nacos_config_service.get_config(config_param)

    if yaml_str:
        config.load_from_yaml(yaml_str)
        logger.info(f"[Nacos] ✅ 配置加载成功: dataId={local_settings.NACOS_DATA_ID}")

    # 启动监听协程(热更新)
    asyncio.create_task(_watch_nacos_config(config, local_settings))


async def _watch_nacos_config(
    config: DynamicConfig, local_settings: LocalSettings
) -> None:
    """持续监听Nacos配置变化"""

    async def on_change(tenant, data_id, group, content):
        logger.info("🔥 [Nacos] 配置变更,重新加载...")
        config.load_from_yaml(content)

    if config.nacos_config_service:
        await config.nacos_config_service.add_listener(
            data_id=local_settings.NACOS_DATA_ID,
            group=local_settings.NACOS_GROUP,
            listener=on_change,
        )


async def close_dynamic_config(config: DynamicConfig) -> None:
    """关闭动态配置,释放资源"""
    if config.nacos_config_service:
        await config.nacos_config_service.shutdown()
        logger.info("✅ Nacos配置服务已关闭")
