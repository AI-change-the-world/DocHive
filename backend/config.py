import os
import asyncio
from typing import List, Any
from functools import lru_cache
from loguru import logger
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class __LocalSettings(BaseSettings):
    """本地配置类 - 从.env读取配置"""

    APP_NAME: str = "DocHive"
    APP_VERSION: str = "1.0.0"
    NACOS_HOST: str = "localhost"
    NACOS_PORT: int = 8848
    NACOS_NAMESPACE: str = ""
    NACOS_GROUP: str = "DEFAULT_GROUP"
    NACOS_DATA_ID: str = "dochive-config.yaml"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


class Settings:
    """应用配置类 - 从Nacos动态获取配置"""

    def __init__(self):

        __local_settings = __LocalSettings()

        self.NACOS_HOST = os.getenv("NACOS_HOST", __local_settings.NACOS_HOST)
        self.NACOS_PORT = int(os.getenv("NACOS_PORT", __local_settings.NACOS_PORT))
        self.NACOS_NAMESPACE = os.getenv(
            "NACOS_NAMESPACE", __local_settings.NACOS_NAMESPACE
        )
        self.NACOS_GROUP = os.getenv("NACOS_GROUP", __local_settings.NACOS_GROUP)
        self.NACOS_DATA_ID = os.getenv("NACOS_DATA_ID", __local_settings.NACOS_DATA_ID)

        # 配置数据缓存
        self._config_data: dict[str, Any] = {}
        self._nacos_client = None

    def load_from_yaml(self, yaml_content: str):
        """从YAML内容加载配置"""
        try:
            new_config = yaml.safe_load(yaml_content)
            if isinstance(new_config, dict):
                self._config_data = new_config
                logger.info("✅ 配置已更新")
        except Exception as e:
            logger.error(f"❌ 解析YAML配置失败: {e}")

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

    # 应用基础配置
    @property
    def APP_NAME(self) -> str:
        return self._get_config("app.name", "DocHive")

    @property
    def APP_VERSION(self) -> str:
        return self._get_config("app.version", "1.0.0")

    @property
    def DEBUG(self) -> bool:
        return self._get_config("app.debug", True)

    @property
    def SECRET_KEY(self) -> str:
        return self._get_config("app.secret_key", "")

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
        return origins or "http://localhost:3000,http://localhost:5173"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def allowed_extensions_list(self) -> List[str]:
        return [ext.strip() for ext in self.ALLOWED_EXTENSIONS.split(",")]


# 全局配置实例
_settings: Settings | None = None


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Nacos配置初始化和监听
async def init_nacos_config():
    """初始化Nacos配置（v2异步版）"""
    from utils.nacos_client import init_nacos_client

    settings = get_settings()

    # 初始化Nacos客户端
    nacos_client = await init_nacos_client(
        host=settings.NACOS_HOST,
        port=settings.NACOS_PORT,
        namespace=settings.NACOS_NAMESPACE,
        group=settings.NACOS_GROUP,
    )

    # 加载初始配置
    yaml_data = await nacos_client.get_config(settings.NACOS_DATA_ID)
    if yaml_data:
        import yaml

        yaml_str = (
            yaml.dump(yaml_data) if isinstance(yaml_data, dict) else str(yaml_data)
        )
        settings.load_from_yaml(yaml_str)
        logger.info(
            f"[Nacos] ✅ Loaded config: dataId={settings.NACOS_DATA_ID}, group={settings.NACOS_GROUP}"
        )

    # 启动监听协程（热更新）
    asyncio.create_task(start_watch_config(nacos_client, settings))


async def start_watch_config(nacos_client, settings: Settings):
    """持续监听配置变化"""

    async def on_change(tenant, data_id, group, content):
        logger.info("🔥 [Nacos] Config changed, reloading...")
        settings.load_from_yaml(content)

    await nacos_client.add_listener(
        data_id=settings.NACOS_DATA_ID, listener_callback=on_change
    )


async def close_nacos_config():
    """关闭Nacos配置服务"""
    from utils.nacos_client import close_nacos_client as shutdown

    await shutdown()
