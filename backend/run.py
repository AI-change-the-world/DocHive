"""
DocHive 后端服务启动脚本
"""

import uvicorn

from config import LocalSettings

local_settings = LocalSettings()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=local_settings.DOC_HIVE_PORT,
        reload=True,  # 开发模式
        log_level="info",
        access_log=True,
    )
