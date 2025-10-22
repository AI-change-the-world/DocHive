#!/bin/bash

echo "========================================"
echo "  DocHive 搜索引擎配置向导"
echo "========================================"
echo ""

show_menu() {
    echo "请选择搜索引擎类型:"
    echo ""
    echo "[1] Database 原生全文检索 (推荐开发使用)"
    echo "    - 无需额外服务,零配置"
    echo "    - 支持 PostgreSQL/MySQL/SQLite"
    echo "    - 内存占用: 低"
    echo ""
    echo "[2] Elasticsearch (推荐生产使用)"
    echo "    - 强大的全文检索能力"
    echo "    - 支持中文分词"
    echo "    - 内存占用: 高 (1GB+)"
    echo ""
    echo "[3] ClickHouse (适合海量数据)"
    echo "    - 列式存储,压缩率高"
    echo "    - 查询速度极快"
    echo "    - 内存占用: 中 (200MB+)"
    echo ""
    echo "[0] 退出"
    echo ""
}

configure_database() {
    echo ""
    echo "========================================"
    echo "  配置 Database 原生全文检索"
    echo "========================================"
    echo ""
    echo "请选择数据库类型:"
    echo "[1] SQLite (开发调试推荐)"
    echo "[2] PostgreSQL (生产环境推荐)"
    echo "[3] MySQL"
    echo ""
    read -p "请输入选项 (1-3): " db_choice
    
    case $db_choice in
        1)
            DB_URL="sqlite:///./dochive.db"
            echo ""
            echo "✅ 已配置 SQLite 数据库"
            ;;
        2)
            read -p "PostgreSQL 主机 [localhost]: " pg_host
            pg_host=${pg_host:-localhost}
            read -p "PostgreSQL 端口 [5432]: " pg_port
            pg_port=${pg_port:-5432}
            read -p "PostgreSQL 用户 [postgres]: " pg_user
            pg_user=${pg_user:-postgres}
            read -sp "PostgreSQL 密码: " pg_pass
            echo ""
            read -p "数据库名 [dochive]: " pg_db
            pg_db=${pg_db:-dochive}
            DB_URL="postgresql+asyncpg://$pg_user:$pg_pass@$pg_host:$pg_port/$pg_db"
            echo ""
            echo "✅ 已配置 PostgreSQL 数据库"
            ;;
        3)
            read -p "MySQL 主机 [localhost]: " my_host
            my_host=${my_host:-localhost}
            read -p "MySQL 端口 [3306]: " my_port
            my_port=${my_port:-3306}
            read -p "MySQL 用户 [root]: " my_user
            my_user=${my_user:-root}
            read -sp "MySQL 密码: " my_pass
            echo ""
            read -p "数据库名 [dochive]: " my_db
            my_db=${my_db:-dochive}
            DB_URL="mysql+aiomysql://$my_user:$my_pass@$my_host:$my_port/$my_db"
            echo ""
            echo "✅ 已配置 MySQL 数据库"
            ;;
        *)
            echo "无效选项!"
            return 1
            ;;
    esac
    
    # 更新 .env 文件
    sed -i.bak '/^SEARCH_ENGINE=/d' .env
    sed -i.bak '/^DATABASE_URL=/d' .env
    echo "SEARCH_ENGINE=database" >> .env
    echo "DATABASE_URL=$DB_URL" >> .env
    rm -f .env.bak
    
    echo ""
    echo "📦 正在初始化全文检索索引..."
    python scripts/init_search_index.py
    
    echo ""
    echo "✅ Database 搜索引擎配置完成!"
    return 0
}

configure_elasticsearch() {
    echo ""
    echo "========================================"
    echo "  配置 Elasticsearch"
    echo "========================================"
    echo ""
    read -p "Elasticsearch URL [http://localhost:9200]: " es_url
    es_url=${es_url:-http://localhost:9200}
    read -p "索引名称 [dochive_documents]: " es_index
    es_index=${es_index:-dochive_documents}
    
    # 更新 .env 文件
    sed -i.bak '/^SEARCH_ENGINE=/d' .env
    sed -i.bak '/^ELASTICSEARCH_URL=/d' .env
    sed -i.bak '/^ELASTICSEARCH_INDEX=/d' .env
    echo "SEARCH_ENGINE=elasticsearch" >> .env
    echo "ELASTICSEARCH_URL=$es_url" >> .env
    echo "ELASTICSEARCH_INDEX=$es_index" >> .env
    rm -f .env.bak
    
    echo ""
    echo "✅ Elasticsearch 配置完成!"
    echo ""
    echo "提示: 请确保 Elasticsearch 服务已启动"
    echo "可使用 Docker 快速启动:"
    echo "docker run -d --name elasticsearch -p 9200:9200 \\"
    echo "  -e \"discovery.type=single-node\" \\"
    echo "  docker.elastic.co/elasticsearch/elasticsearch:8.11.0"
    return 0
}

configure_clickhouse() {
    echo ""
    echo "========================================"
    echo "  配置 ClickHouse"
    echo "========================================"
    echo ""
    read -p "ClickHouse 主机 [localhost]: " ch_host
    ch_host=${ch_host:-localhost}
    read -p "ClickHouse 端口 [9000]: " ch_port
    ch_port=${ch_port:-9000}
    read -p "ClickHouse 用户 [default]: " ch_user
    ch_user=${ch_user:-default}
    read -sp "ClickHouse 密码 (可选): " ch_pass
    echo ""
    read -p "数据库名 [dochive]: " ch_db
    ch_db=${ch_db:-dochive}
    
    # 更新 .env 文件
    sed -i.bak '/^SEARCH_ENGINE=/d' .env
    sed -i.bak '/^CLICKHOUSE_HOST=/d' .env
    sed -i.bak '/^CLICKHOUSE_PORT=/d' .env
    sed -i.bak '/^CLICKHOUSE_USER=/d' .env
    sed -i.bak '/^CLICKHOUSE_PASSWORD=/d' .env
    sed -i.bak '/^CLICKHOUSE_DATABASE=/d' .env
    echo "SEARCH_ENGINE=clickhouse" >> .env
    echo "CLICKHOUSE_HOST=$ch_host" >> .env
    echo "CLICKHOUSE_PORT=$ch_port" >> .env
    echo "CLICKHOUSE_USER=$ch_user" >> .env
    echo "CLICKHOUSE_PASSWORD=$ch_pass" >> .env
    echo "CLICKHOUSE_DATABASE=$ch_db" >> .env
    rm -f .env.bak
    
    echo ""
    echo "✅ ClickHouse 配置完成!"
    echo ""
    echo "提示: 请确保 ClickHouse 服务已启动"
    echo "可使用 Docker 快速启动:"
    echo "docker run -d --name clickhouse -p 9000:9000 -p 8123:8123 \\"
    echo "  clickhouse/clickhouse-server:latest"
    return 0
}

show_success() {
    echo ""
    echo "========================================"
    echo "  配置成功!"
    echo "========================================"
    echo ""
    echo "当前配置已保存到 .env 文件"
    echo ""
    echo "下一步操作:"
    echo "1. 重启后端服务"
    echo "2. 访问 http://localhost:8000/docs 查看 API 文档"
    echo ""
}

# 主循环
while true; do
    show_menu
    read -p "请输入选项 (0-3): " choice
    
    case $choice in
        1)
            configure_database
            if [ $? -eq 0 ]; then
                show_success
                break
            fi
            ;;
        2)
            configure_elasticsearch
            if [ $? -eq 0 ]; then
                show_success
                break
            fi
            ;;
        3)
            configure_clickhouse
            if [ $? -eq 0 ]; then
                show_success
                break
            fi
            ;;
        0)
            echo "退出配置"
            exit 0
            ;;
        *)
            echo "无效选项,请重新选择!"
            echo ""
            ;;
    esac
done
