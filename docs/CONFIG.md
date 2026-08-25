# 配置说明

本项目只有两处需要你自己配，且**两处都不配也能完整跑**：

| 要配的东西 | 改哪里 | 不配的后果 |
|---|---|---|
| **LLM API Key** | `local.env` 的 `LLM_PROVIDER` / `ARK_*` / `OPENAI_*` | 走离线策略决策器，功能完整、不联网 |
| **Postgres** | `local.env` 的 `DATABASE_URL` | 记忆只存内存，重启就丢 |

> **安全约定：凭据只写 `local.env`，该文件已在 `.gitignore` 里，永不入库。**
> 不要把 key 或数据库密码写进 `config.py`、`start.bat` 或任何会被提交的文件。

---

## 一、创建本地配置文件

把模板复制一份（在项目根目录）：

```powershell
copy local.env.example local.env
```

编辑 `local.env`，只填你要用的行，其余保持注释。
`start.bat` 启动时会自动加载它；手动跑的话用下面的 `$env:` 方式也一样。

---

## 二、LLM API 配置

### 改哪个文件

| 内容 | 位置 |
|---|---|
| 填凭据 | 根目录 `local.env` |
| 客户端实现（要改请求格式/新增厂商） | `backend/app/agent/llm.py` |
| 工具定义（模型能调的 17 个工具） | `backend/app/agent/toolkit.py` |

### 方舟（火山引擎，OpenAI 兼容）

```ini
LLM_PROVIDER=ark
ARK_API_KEY=你的key
ARK_MODEL=你的接入点ID或模型名
```

`ARK_MODEL` **必填**，在方舟控制台「在线推理」里取。缺失会直接报错提醒，
不会静默降级到离线模式——避免你以为在用真模型、其实跑的是策略代码。

### OpenAI 或第三方中转

```ini
LLM_PROVIDER=openai
OPENAI_API_KEY=你的key
OPENAI_MODEL=gpt-4o-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

### 不接（默认）

```ini
LLM_PROVIDER=mock
```

走 `MockClient`：一个「读任务观测 → 选下一个工具」的策略决策器。
它与真模型**走完全相同的工具接口与核心循环**，区别只是「怎么选」由代码而非模型给出。

### 测评判官（可选，单独指定）

```ini
JUDGE_PROVIDER=ark      # 不写则跟随 LLM_PROVIDER
JUDGE_MODEL=你的模型   # 不写则跟随 ARK_MODEL / OPENAI_MODEL
```

不配时测评自动回退到「行为断言 + 轨迹对比」，完全离线。

---

## 三、Postgres 配置

### 1. 建专用账号与库

**不要用 `postgres` 超管跑业务。** 用现成脚本建一个专用账号：

```powershell
# 先编辑 docs/postgres_init.sql，把里面的密码改成你自己的
psql -U postgres -f docs/postgres_init.sql
```

脚本做四件事：建账号 `shopping_agent`、建同名数据库、授权、把 `public` schema
交给它（PG 15+ 默认不给 public 写权限，不做这一步建表会失败）。

**表结构不需要你管**，应用首次启动会自动 `CREATE TABLE IF NOT EXISTS` 建三张表：

| 表 | 存什么 |
|---|---|
| `user_memory` | 长期偏好（健康条件、品牌黑名单、价格态度） |
| `shopping_task` | 购物任务快照（JSONB） |
| `conversation_turn` | 逐轮对话记录 |

### 2. 填连接串

`local.env`：

```ini
DATABASE_URL=postgresql://shopping_agent:你的密码@localhost:5432/shopping_agent
```

格式：`postgresql://用户名:密码@主机:端口/库名`

密码里如果含 `@ : / ? #`，需要 URL 编码（比如 `@` 写成 `%40`）。
简单做法是建账号时就避开这几个字符。

### 3. 验证配对了

启动后看健康检查的 `memory_backend` 字段：

```powershell
curl http://127.0.0.1:8000/api/health
```

| `memory_backend` 的值 | 含义 |
|---|---|
| `postgres` | 配对了，记忆真的存进了数据库 |
| `memory` | 没配 `DATABASE_URL`，只存内存（重启丢） |
| `memory (postgres unavailable)` | **配了但连不上**，已降级内存，去看后端控制台警告 |

这个字段是故意如实暴露的——避免你以为记忆存住了，其实一重启全没了。

### 4. 设计上的两个取舍

- **读走进程内缓存，写异步回写**：记忆读取在决策循环的热路径上，
  每步都要用，同步查库会把每一轮对话拘死。
- **持久化失败只记警告**：数据库挂了不应该让用户买不了东西。

---

## 四、完整变量清单

| 变量 | 默认 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` / `ark` / `openai` |
| `ARK_API_KEY` | — | 方舟 Key |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 换区域改这里 |
| `ARK_MODEL` | — | 用 ark 时**必填** |
| `OPENAI_API_KEY` | — | OpenAI Key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | 第三方中转改这里 |
| `OPENAI_MODEL` | — | 用 openai 时**必填** |
| `JUDGE_PROVIDER` | 跟随 `LLM_PROVIDER` | 测评判官厂商 |
| `JUDGE_MODEL` | 跟随上面的 model | 测评判官模型 |
| `DATABASE_URL` | — | 不配则记忆只存内存 |
| `DATA_SOURCE_MODE` | `mock` | `mock` 跑本地样本；`live` 走真实适配器 |

---

## 五、手动设环境变量（不用 local.env）

PowerShell，仅当前终端有效：

```powershell
$env:LLM_PROVIDER="ark"
$env:ARK_API_KEY="你的key"
$env:ARK_MODEL="你的接入点"
$env:DATABASE_URL="postgresql://shopping_agent:你的密码@localhost:5432/shopping_agent"

cd backend
uvicorn app.main:app --reload --port 8000
```
