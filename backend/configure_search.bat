@echo off
chcp 65001 > nul
echo ========================================
echo   DocHive 搜索引擎配置向导
echo ========================================
echo.

:menu
echo 请选择搜索引擎类型:
echo.
echo [1] Database 原生全文检索 (推荐开发使用)
echo     - 无需额外服务,零配置
echo     - 支持 PostgreSQL/MySQL/SQLite
echo     - 内存占用: 低
echo.
echo [2] Elasticsearch (推荐生产使用)
echo     - 强大的全文检索能力
echo     - 支持中文分词
echo     - 内存占用: 高 (1GB+)
echo.
echo [3] ClickHouse (适合海量数据)
echo     - 列式存储,压缩率高
echo     - 查询速度极快
echo     - 内存占用: 中 (200MB+)
echo.
echo [0] 退出
echo.

set /p choice=请输入选项 (0-3): 

if "%choice%"=="1" goto database
if "%choice%"=="2" goto elasticsearch
if "%choice%"=="3" goto clickhouse
if "%choice%"=="0" goto end
echo 无效选项,请重新选择!
echo.
goto menu

:database
echo.
echo ========================================
echo   配置 Database 原生全文检索
echo ========================================
echo.
echo 请选择数据库类型:
echo [1] SQLite (开发调试推荐)
echo [2] PostgreSQL (生产环境推荐)
echo [3] MySQL
echo.
set /p db_choice=请输入选项 (1-3): 

if "%db_choice%"=="1" (
    set DB_URL=sqlite:///./dochive.db
    echo.
    echo ✅ 已配置 SQLite 数据库
) else if "%db_choice%"=="2" (
    set /p pg_host=PostgreSQL 主机 [localhost]: 
    if "%pg_host%"=="" set pg_host=localhost
    set /p pg_port=PostgreSQL 端口 [5432]: 
    if "%pg_port%"=="" set pg_port=5432
    set /p pg_user=PostgreSQL 用户 [postgres]: 
    if "%pg_user%"=="" set pg_user=postgres
    set /p pg_pass=PostgreSQL 密码: 
    set /p pg_db=数据库名 [dochive]: 
    if "%pg_db%"=="" set pg_db=dochive
    set DB_URL=postgresql+asyncpg://%pg_user%:%pg_pass%@%pg_host%:%pg_port%/%pg_db%
    echo.
    echo ✅ 已配置 PostgreSQL 数据库
) else if "%db_choice%"=="3" (
    set /p my_host=MySQL 主机 [localhost]: 
    if "%my_host%"=="" set my_host=localhost
    set /p my_port=MySQL 端口 [3306]: 
    if "%my_port%"=="" set my_port=3306
    set /p my_user=MySQL 用户 [root]: 
    if "%my_user%"=="" set my_user=root
    set /p my_pass=MySQL 密码: 
    set /p my_db=数据库名 [dochive]: 
    if "%my_db%"=="" set my_db=dochive
    set DB_URL=mysql+aiomysql://%my_user%:%my_pass%@%my_host%:%my_port%/%my_db%
    echo.
    echo ✅ 已配置 MySQL 数据库
) else (
    echo 无效选项!
    goto database
)

findstr /v "^SEARCH_ENGINE=" .env > .env.tmp
findstr /v "^DATABASE_URL=" .env.tmp > .env.tmp2
echo SEARCH_ENGINE=database >> .env.tmp2
echo DATABASE_URL=%DB_URL% >> .env.tmp2
move /y .env.tmp2 .env > nul
del .env.tmp

echo.
echo 📦 正在初始化全文检索索引...
python scripts\init_search_index.py

echo.
echo ✅ Database 搜索引擎配置完成!
goto success

:elasticsearch
echo.
echo ========================================
echo   配置 Elasticsearch
echo ========================================
echo.
set /p es_url=Elasticsearch URL [http://localhost:9200]: 
if "%es_url%"=="" set es_url=http://localhost:9200
set /p es_index=索引名称 [dochive_documents]: 
if "%es_index%"=="" set es_index=dochive_documents

findstr /v "^SEARCH_ENGINE=" .env > .env.tmp
findstr /v "^ELASTICSEARCH_URL=" .env.tmp > .env.tmp2
findstr /v "^ELASTICSEARCH_INDEX=" .env.tmp2 > .env.tmp
echo SEARCH_ENGINE=elasticsearch >> .env.tmp
echo ELASTICSEARCH_URL=%es_url% >> .env.tmp
echo ELASTICSEARCH_INDEX=%es_index% >> .env.tmp
move /y .env.tmp .env > nul
del .env.tmp2

echo.
echo ✅ Elasticsearch 配置完成!
echo.
echo 提示: 请确保 Elasticsearch 服务已启动
echo 可使用 Docker 快速启动:
echo docker run -d --name elasticsearch -p 9200:9200 \
echo   -e "discovery.type=single-node" \
echo   docker.elastic.co/elasticsearch/elasticsearch:8.11.0
goto success

:clickhouse
echo.
echo ========================================
echo   配置 ClickHouse
echo ========================================
echo.
set /p ch_host=ClickHouse 主机 [localhost]: 
if "%ch_host%"=="" set ch_host=localhost
set /p ch_port=ClickHouse 端口 [9000]: 
if "%ch_port%"=="" set ch_port=9000
set /p ch_user=ClickHouse 用户 [default]: 
if "%ch_user%"=="" set ch_user=default
set /p ch_pass=ClickHouse 密码 (可选): 
set /p ch_db=数据库名 [dochive]: 
if "%ch_db%"=="" set ch_db=dochive

findstr /v "^SEARCH_ENGINE=" .env > .env.tmp
findstr /v "^CLICKHOUSE_HOST=" .env.tmp > .env.tmp2
findstr /v "^CLICKHOUSE_PORT=" .env.tmp2 > .env.tmp
findstr /v "^CLICKHOUSE_USER=" .env.tmp > .env.tmp2
findstr /v "^CLICKHOUSE_PASSWORD=" .env.tmp2 > .env.tmp
findstr /v "^CLICKHOUSE_DATABASE=" .env.tmp > .env.tmp2
echo SEARCH_ENGINE=clickhouse >> .env.tmp2
echo CLICKHOUSE_HOST=%ch_host% >> .env.tmp2
echo CLICKHOUSE_PORT=%ch_port% >> .env.tmp2
echo CLICKHOUSE_USER=%ch_user% >> .env.tmp2
echo CLICKHOUSE_PASSWORD=%ch_pass% >> .env.tmp2
echo CLICKHOUSE_DATABASE=%ch_db% >> .env.tmp2
move /y .env.tmp2 .env > nul
del .env.tmp

echo.
echo ✅ ClickHouse 配置完成!
echo.
echo 提示: 请确保 ClickHouse 服务已启动
echo 可使用 Docker 快速启动:
echo docker run -d --name clickhouse -p 9000:9000 -p 8123:8123 \
echo   clickhouse/clickhouse-server:latest
goto success

:success
echo.
echo ========================================
echo   配置成功!
echo ========================================
echo.
echo 当前配置已保存到 .env 文件
echo.
echo 下一步操作:
echo 1. 重启后端服务
echo 2. 访问 http://localhost:8000/docs 查看 API 文档
echo.
pause
goto end

:end
exit /b 0
