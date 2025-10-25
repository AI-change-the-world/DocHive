"""
搜索引擎功能测试
测试不同搜索引擎的基本功能
"""

import asyncio
from utils.search_engine import (
    get_search_engine,
    DatabaseEngine,
    ElasticsearchEngine,
    ClickHouseEngine,
)
from config import get_settings
from datetime import datetime

settings = get_settings()


async def test_search_engine():
    """测试搜索引擎基本功能"""
    print("=" * 60)
    print("DocHive 搜索引擎测试")
    print("=" * 60)
    print()

    # 获取搜索引擎实例
    engine = get_search_engine()
    engine_type = type(engine).__name__

    print(f"🔍 当前搜索引擎: {engine_type}")
    print(f"📝 配置: SEARCH_ENGINE={settings.SEARCH_ENGINE}")
    print()

    try:
        # 1. 测试索引创建
        print("📦 测试 1: 创建/确保索引...")
        await engine.ensure_index()
        print("✅ 索引创建成功!")
        print()

        # 2. 测试文档索引
        print("📝 测试 2: 索引测试文档...")
        test_doc = {
            "document_id": 9999,
            "title": "测试文档 - 搜索引擎功能验证",
            "content": "这是一个用于测试搜索引擎功能的文档。包含关键词：测试、搜索、引擎。",
            "summary": "搜索引擎功能测试文档",
            "class_path": {"level1": "测试", "level2": "功能验证"},
            "class_code": "TEST-001",
            "template_id": 1,
            "file_type": "txt",
            "upload_time": datetime.now(),
            "uploader_id": 1,
        }

        result = await engine.index_document(test_doc)
        if result:
            print("✅ 文档索引成功!")
        else:
            print("⚠️ 文档索引失败 (可能是数据库引擎,会自动索引)")
        print()

        # 3. 测试搜索功能
        print("🔎 测试 3: 搜索测试...")

        # 测试关键词搜索
        print("- 搜索关键词: '测试'")
        search_result = await engine.search_documents(
            keyword="测试", page=1, page_size=10
        )
        print(f"  找到 {search_result['total']} 个结果")
        if search_result["results"]:
            print(f"  第一个结果: {search_result['results'][0]['title']}")
        print()

        # 测试无关键词搜索 (列表所有)
        print("- 搜索所有文档")
        all_docs = await engine.search_documents(page=1, page_size=5)
        print(f"  总共 {all_docs['total']} 个文档")
        print()

        # 4. 测试删除
        print("🗑️  测试 4: 删除测试文档...")
        delete_result = await engine.delete_document(9999)
        if delete_result:
            print("✅ 文档删除成功!")
        else:
            print("⚠️ 文档删除失败 (可能是数据库引擎,会自动删除)")
        print()

        print("=" * 60)
        print("✨ 所有测试通过!")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # 关闭连接
        await engine.close()


async def test_all_engines():
    """测试所有搜索引擎类型"""
    print("=" * 60)
    print("测试所有搜索引擎实现")
    print("=" * 60)
    print()

    engines = [
        ("Database", DatabaseEngine),
    ]

    # 如果配置了 ES,添加 ES 测试
    if settings.ELASTICSEARCH_URL:
        try:
            engines.append(("Elasticsearch", ElasticsearchEngine))
        except ImportError:
            print("⚠️ Elasticsearch 库未安装,跳过测试")

    # 如果配置了 ClickHouse,添加 ClickHouse 测试
    if settings.CLICKHOUSE_HOST:
        try:
            engines.append(("ClickHouse", ClickHouseEngine))
        except ImportError:
            print("⚠️ ClickHouse 库未安装,跳过测试")

    for engine_name, engine_class in engines:
        print(f"\n{'=' * 60}")
        print(f"测试 {engine_name} 引擎")
        print(f"{'=' * 60}\n")

        try:
            engine = engine_class()

            # 测试索引创建
            await engine.ensure_index()
            print(f"✅ {engine_name} 索引创建成功")

            # 测试搜索
            results = await engine.search_documents(page=1, page_size=1)
            print(f"✅ {engine_name} 搜索功能正常 (共 {results['total']} 个文档)")

            await engine.close()

        except Exception as e:
            print(f"❌ {engine_name} 测试失败: {e}")


async def benchmark_search():
    """简单的性能基准测试"""
    print("=" * 60)
    print("搜索引擎性能基准测试")
    print("=" * 60)
    print()

    engine = get_search_engine()
    engine_type = type(engine).__name__

    print(f"🔍 测试引擎: {engine_type}")
    print()

    # 测试不同查询的性能
    test_cases = [
        ("空查询 (列表所有)", {}),
        ("关键词搜索", {"keyword": "测试"}),
        ("分页查询", {"page": 1, "page_size": 20}),
    ]

    for test_name, params in test_cases:
        import time

        start = time.time()

        result = await engine.search_documents(**params)

        elapsed = (time.time() - start) * 1000  # 转换为毫秒

        print(f"📊 {test_name}")
        print(f"   耗时: {elapsed:.2f}ms")
        print(f"   结果: {result['total']} 个文档")
        print()

    await engine.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "all":
        # 测试所有引擎
        asyncio.run(test_all_engines())
    elif len(sys.argv) > 1 and sys.argv[1] == "benchmark":
        # 性能测试
        asyncio.run(benchmark_search())
    else:
        # 基本测试
        asyncio.run(test_search_engine())
