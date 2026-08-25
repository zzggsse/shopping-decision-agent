-- 购物决策 Agent：Postgres 专用账号与库初始化脚本
--
-- 用法（以超管身份执行，不要用你的业务库账号）：
--   psql -U postgres -f docs/postgres_init.sql
--
-- 执行前请把下面的密码改成你自己的。
-- 这份脚本只建账号与库，表结构由应用首次启动时自动创建（CREATE TABLE IF NOT EXISTS）。

-- 1. 专用账号。只给这个应用用，不要用 postgres 超管跑业务。
--    把 '改成你自己的密码' 换掉，密码里避开 @ : / ? # 这几个字符，
--    否则拼 DATABASE_URL 时需要额外做 URL 编码。
CREATE USER shopping_agent WITH PASSWORD '改成你自己的密码';

-- 2. 专用数据库，归该账号所有
CREATE DATABASE shopping_agent OWNER shopping_agent ENCODING 'UTF8';

-- 3. 最小权限：能连、能建表、能读写自己的表即可
GRANT ALL PRIVILEGES ON DATABASE shopping_agent TO shopping_agent;

-- 4. 切到新库把 public schema 也交给它（PG 15+ 默认不给 public 写权限）
\connect shopping_agent
GRANT ALL ON SCHEMA public TO shopping_agent;
ALTER SCHEMA public OWNER TO shopping_agent;

-- 完成。接下来把连接串配给应用（参见 docs/CONFIG.md）：
--   DATABASE_URL=postgresql://shopping_agent:你的密码@localhost:5432/shopping_agent
--
-- 验证账号能用：
--   psql "postgresql://shopping_agent:你的密码@localhost:5432/shopping_agent" -c "SELECT current_user, current_database();"
