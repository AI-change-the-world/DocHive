from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from config import DynamicConfig, LocalSettings

# 静态配置(加密密钥不应动态变更)
local_settings = LocalSettings()
key = local_settings.SECRET_KEY
f = Fernet(key)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return plain_password == f.decrypt(hashed_password.encode()).decode()


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return f.encrypt(password.encode()).decode()


def create_access_token(
    data: dict, config: DynamicConfig, expires_delta: Optional[timedelta] = None
) -> str:
    """创建访问令牌

    Args:
        data: 要编码的数据
        config: 动态配置实例
        expires_delta: 过期时间
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({"exp": expire, "type": "access"})

    encoded_jwt = jwt.encode(
        to_encode,
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )

    return encoded_jwt


def create_refresh_token(data: dict, config: DynamicConfig) -> str:
    """创建刷新令牌

    Args:
        data: 要编码的数据
        config: 动态配置实例
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})

    encoded_jwt = jwt.encode(
        to_encode,
        config.JWT_SECRET_KEY,
        algorithm=config.JWT_ALGORITHM,
    )

    return encoded_jwt


def decode_token(token: str, config: DynamicConfig) -> Optional[dict]:
    """解码令牌

    Args:
        token: JWT令牌
        config: 动态配置实例
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        return None
