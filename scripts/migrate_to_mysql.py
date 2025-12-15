#!/usr/bin/env python3
"""
MySQL 迁移脚本
用于修复从 SQLite 迁移到 MySQL 时的 AUTO_INCREMENT 问题
"""

from sqlalchemy import create_engine, text

def fix_auto_increment():
    """修复所有表的 AUTO_INCREMENT 问题"""
    
    # 创建同步数据库引擎
    engine = create_engine("mysql+pymysql://dochive_user:dochive_pass@localhost:3307/dochive")
    
    if not engine:
        print("❌ 数据库引擎初始化失败")
        return
    
    # 需要修复的表和主键字段
    tables_to_fix = [
        "users",
        "class_templates", 
        "class_template_configs",
        "documents",
        "operation_logs",
        "document_types",
        "document_type_fields", 
        "template_document_mappings",
        "system_configs",
        "llm_logs",
        "custom_agents",
        "writing_templates",
        "agent_execution_records"
    ]
    
    with engine.begin() as conn:
        for table_name in tables_to_fix:
            try:
                # 修改主键为 AUTO_INCREMENT
                sql = f"ALTER TABLE {table_name} MODIFY COLUMN id INT AUTO_INCREMENT"
                conn.execute(text(sql))
                print(f"✅ 修复表 {table_name} 的 AUTO_INCREMENT")
            except Exception as e:
                print(f"⚠️  表 {table_name} 修复失败: {e}")
                # 可能表不存在或已经是 AUTO_INCREMENT，继续处理其他表
                continue
    
    print("🎉 AUTO_INCREMENT 修复完成")

def check_mysql_tables():
    """检查 MySQL 表结构"""
    engine = create_engine("mysql+pymysql://dochive_user:dochive_pass@localhost:3307/dochive")
    
    with engine.begin() as conn:
        # 检查所有表的主键定义
        result = conn.execute(text("""
            SELECT 
                TABLE_NAME,
                COLUMN_NAME,
                EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND COLUMN_KEY = 'PRI' 
            AND DATA_TYPE = 'int'
            ORDER BY TABLE_NAME
        """))
        
        print("📋 当前主键字段状态:")
        for row in result:
            auto_inc = "✅ AUTO_INCREMENT" if "auto_increment" in row.EXTRA.lower() else "❌ 需要修复"
            print(f"  {row.TABLE_NAME}.{row.COLUMN_NAME}: {auto_inc}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        print("🔍 检查 MySQL 表结构...")
        check_mysql_tables()
    else:
        print("🔧 开始修复 AUTO_INCREMENT...")
        fix_auto_increment()
        print("\n🔍 检查修复结果...")
        check_mysql_tables()