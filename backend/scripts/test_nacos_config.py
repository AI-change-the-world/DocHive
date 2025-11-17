#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Nacos配置获取功能
"""

import os
import sys

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings
from utils.nacos_client import get_nacos_client


def test_config_loading():
    """测试配置加载"""
    print("=== 测试配置加载 ===")

    # 获取配置
    settings = get_settings()

    print(f"应用名称: {settings.APP_NAME}")
    print(f"应用版本: {settings.APP_VERSION}")
    print(f"调试模式: {settings.DEBUG}")

    print(f"数据库URL: {settings.DATABASE_URL}")
    print(f"搜索引擎: {settings.SEARCH_ENGINE}")
    print(f"存储类型: {settings.STORAGE_TYPE}")

    print(f"Nacos主机: {settings.NACOS_HOST}")
    print(f"Nacos端口: {settings.NACOS_PORT}")
    print(f"Nacos命名空间: {settings.NACOS_NAMESPACE}")
    print(f"Nacos组: {settings.NACOS_GROUP}")
    print(f"Nacos数据ID: {settings.NACOS_DATA_ID}")

    # 测试Nacos客户端
    print("\n=== 测试Nacos客户端 ===")
    nacos_client = get_nacos_client()
    if nacos_client:
        print("Nacos客户端初始化成功")
        # 尝试获取配置
        config = nacos_client.get_config(settings.NACOS_DATA_ID)
        if config is not None:
            print("从Nacos获取配置成功:")
            print(f"  应用名称: {config.get('app', {}).get('name', 'N/A')}")
            print(f"  数据库URL: {config.get('database', {}).get('url', 'N/A')}")
        else:
            print("从Nacos获取配置失败或无配置")
    else:
        print("Nacos客户端未初始化")


if __name__ == "__main__":
    test_config_loading()
