"""
数据库全文检索索引初始化脚本
支持 PostgreSQL GIN 索引、MySQL FULLTEXT 索引、SQLite FTS5
"""

import asyncio

from sqlalchemy import text

from config import get_settings
from database import engine

settings = get_settings()


def detect_db_type() -> str:
    """检测数据库类型"""
    url = settings.DATABASE_URL.lower()
    if "postgresql" in url or "postgres" in url:
        return "postgresql"
    elif "mysql" in url:
        return "mysql"
    elif "sqlite" in url:
        return "sqlite"
    return "unknown"


async def init_postgresql_fts():
    """初始化 PostgreSQL 全文检索索引"""
    print("📦 初始化 PostgreSQL GIN 全文检索索引...")

    async with engine.begin() as conn:
        # 创建 GIN 索引
        await conn.execute(
            text(
                """
            CREATE INDEX IF NOT EXISTS idx_documents_fulltext 
            ON documents USING GIN (
                to_tsvector('simple', title || ' ' || COALESCE(content_text, ''))
            )
        """
            )
        )

        # 可选: 创建中文分词索引 (需要安装 pg_jieba 扩展)
        # await conn.execute(text("""
        #     CREATE INDEX IF NOT EXISTS idx_documents_fulltext_zh
        #     ON documents USING GIN (
        #         to_tsvector('jiebacfg', title || ' ' || COALESCE(content_text, ''))
        #     )
        # """))

        print("✅ PostgreSQL 全文检索索引创建成功!")


async def init_mysql_fts():
    """初始化 MySQL 全文检索索引"""
    print("📦 初始化 MySQL FULLTEXT 全文检索索引...")

    async with engine.begin() as conn:
        # 检查索引是否存在
        result = await conn.execute(
            text(
                """
            SELECT COUNT(*) 
            FROM information_schema.statistics 
            WHERE table_schema = DATABASE() 
            AND table_name = 'documents' 
            AND index_name = 'idx_documents_fulltext'
        """
            )
        )
        exists = result.scalar() > 0

        if not exists:
            # MySQL 需要先检查字段类型是否支持 FULLTEXT
            await conn.execute(
                text(
                    """
                ALTER TABLE documents 
                ADD FULLTEXT INDEX idx_documents_fulltext (title, content_text)
            """
                )
            )
            print("✅ MySQL FULLTEXT 索引创建成功!")
        else:
            print("✅ MySQL FULLTEXT 索引已存在!")


async def init_sqlite_fts():
    """初始化 SQLite FTS5 虚拟表"""
    print("📦 初始化 SQLite FTS5 全文检索虚拟表...")

    async with engine.begin() as conn:
        # 创建 FTS5 虚拟表
        await conn.execute(
            text(
                """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts 
            USING fts5(
                document_id UNINDEXED, 
                title, 
                content_text, 
                content='documents', 
                content_rowid='id',
                tokenize='porter unicode61'
            )
        """
            )
        )

        # 创建插入触发器
        await conn.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS documents_ai 
            AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, document_id, title, content_text)
                VALUES (new.id, new.id, new.title, COALESCE(new.content_text, ''));
            END
        """
            )
        )

        # 创建删除触发器
        await conn.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS documents_ad 
            AFTER DELETE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
            END
        """
            )
        )

        # 创建更新触发器
        await conn.execute(
            text(
                """
            CREATE TRIGGER IF NOT EXISTS documents_au 
            AFTER UPDATE ON documents BEGIN
                DELETE FROM documents_fts WHERE rowid = old.id;
                INSERT INTO documents_fts(rowid, document_id, title, content_text)
                VALUES (new.id, new.id, new.title, COALESCE(new.content_text, ''));
            END
        """
            )
        )

        # 如果已有数据,重建索引
        await conn.execute(
            text(
                """
            INSERT INTO documents_fts(rowid, document_id, title, content_text)
            SELECT id, id, title, COALESCE(content_text, '') 
            FROM documents 
            WHERE id NOT IN (SELECT rowid FROM documents_fts)
        """
            )
        )

        print("✅ SQLite FTS5 虚拟表和触发器创建成功!")


async def main():
    """主函数"""
    db_type = detect_db_type()

    print(f"🔍 检测到数据库类型: {db_type.upper()}")
    print(f"🔍 搜索引擎配置: {settings.SEARCH_ENGINE.upper()}")
    print()

    if settings.SEARCH_ENGINE.lower() == "database":
        if db_type == "postgresql":
            await init_postgresql_fts()
        elif db_type == "mysql":
            await init_mysql_fts()
        elif db_type == "sqlite":
            await init_sqlite_fts()
        else:
            print(f"❌ 不支持的数据库类型: {db_type}")
            return
    else:
        print(
            f"ℹ️  当前使用 {settings.SEARCH_ENGINE.upper()} 搜索引擎,无需初始化数据库索引"
        )
        print(f"ℹ️  如需使用数据库原生全文检索,请在 .env 中设置: SEARCH_ENGINE=database")

    await engine.dispose()
    print("\n✨ 搜索索引初始化完成!")


if __name__ == "__main__":
    asyncio.run(main())
