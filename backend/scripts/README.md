# DocHive 后端脚本说明

本目录包含 DocHive 后端的工具脚本。

## 📋 脚本列表

### 1. `init_search_index.py` - 搜索索引初始化

**用途**: 初始化数据库全文检索索引 (PostgreSQL GIN / MySQL FULLTEXT / SQLite FTS5)

**使用场景**:
- 首次使用 `database` 搜索引擎时
- 数据库迁移后
- 索引损坏需要重建时

**用法**:
```bash
cd backend
python scripts/init_search_index.py
```

**输出示例**:
```
🔍 检测到数据库类型: SQLITE
🔍 搜索引擎配置: DATABASE

📦 初始化 SQLite FTS5 全文检索虚拟表...
✅ SQLite FTS5 虚拟表和触发器创建成功!

✨ 搜索索引初始化完成!
```

**支持的数据库**:
- ✅ PostgreSQL (创建 GIN 索引)
- ✅ MySQL (创建 FULLTEXT 索引)
- ✅ SQLite (创建 FTS5 虚拟表 + 触发器)

---

### 2. `test_search_engine.py` - 搜索引擎功能测试

**用途**: 测试搜索引擎的基本功能和性能

**用法**:

```bash
# 基本功能测试
python scripts/test_search_engine.py

# 测试所有已配置的搜索引擎
python scripts/test_search_engine.py all

# 性能基准测试
python scripts/test_search_engine.py benchmark
```

**测试内容**:
1. 索引创建/确保
2. 文档索引
3. 关键词搜索
4. 分页查询
5. 文档删除

**输出示例**:
```
============================================================
DocHive 搜索引擎测试
============================================================

🔍 当前搜索引擎: DatabaseEngine
📝 配置: SEARCH_ENGINE=database

📦 测试 1: 创建/确保索引...
✅ 索引创建成功!

📝 测试 2: 索引测试文档...
✅ 文档索引成功!

🔎 测试 3: 搜索测试...
- 搜索关键词: '测试'
  找到 1 个结果
  第一个结果: 测试文档 - 搜索引擎功能验证

🗑️  测试 4: 删除测试文档...
✅ 文档删除成功!

✨ 所有测试通过!
```

---

## 🔧 其他工具脚本 (待添加)

### 计划中的脚本:

1. **`rebuild_search_index.py`** - 重建所有文档的搜索索引
   ```bash
   python scripts/rebuild_search_index.py
   ```

2. **`migrate_search_engine.py`** - 搜索引擎迁移工具
   ```bash
   # 从 Elasticsearch 迁移到 Database
   python scripts/migrate_search_engine.py --from=elasticsearch --to=database
   ```

3. **`backup_database.py`** - 数据库备份脚本
   ```bash
   python scripts/backup_database.py --output=backup.sql
   ```

4. **`import_documents.py`** - 批量导入文档
   ```bash
   python scripts/import_documents.py --dir=/path/to/documents --template=1
   ```

5. **`cleanup_orphaned_files.py`** - 清理孤立文件
   ```bash
   python scripts/cleanup_orphaned_files.py
   ```

---

## 💡 开发新脚本指南

### 脚本模板

```python
"""
脚本名称 - 简短描述

详细说明...
"""
import asyncio
from database import engine, AsyncSessionLocal
from config import get_settings

settings = get_settings()


async def main():
    """主函数"""
    print("脚本开始执行...")
    
    async with AsyncSessionLocal() as session:
        # 在这里编写你的逻辑
        pass
    
    await engine.dispose()
    print("脚本执行完成!")


if __name__ == "__main__":
    asyncio.run(main())
```

### 最佳实践

1. **使用异步**: 所有数据库操作应使用 `async/await`
2. **错误处理**: 添加 try/except 捕获异常
3. **日志输出**: 使用清晰的 emoji 和格式化输出
4. **资源清理**: 确保数据库连接正确关闭
5. **参数解析**: 使用 `argparse` 处理命令行参数
6. **文档字符串**: 添加详细的 docstring

---

## 📚 相关文档

- [搜索引擎配置指南](../docs/SEARCH_ENGINE.md)
- [后端架构说明](../ARCHITECTURE.md)
- [部署指南](../DEPLOYMENT.md)

---

**如有问题或建议,欢迎提交 Issue!** 🎉
