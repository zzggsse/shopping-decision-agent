# 购物决策助手

对话式购物 Agent，解决**多平台比价**、**个性化偏好**、**长链路决策**三层问题，
并支持**配料表/营养成分精准分析**与**跨会话记忆**。

定位：**只做决策 + 跳转** —— 不代下单、不碰支付、不存平台凭证。

---

## 目录

1. [需要的配置](#1-需要的配置) —— 两处，都不配也能跑
2. [快速开始](#2-快速开始)
3. [为什么做这个](#3-为什么做这个) —— 要解决的三层真实痛点
4. [技术点](#4-技术点) —— 技术栈与关键设计
5. [Agent 相关概念的落地情况](#5-agent-相关概念在本项目的落地情况) —— 用了什么、没用什么、为什么
6. [Harness 层](#6-harness-层编排--上下文--记忆--测评) —— 编排 / 上下文 / 记忆 / 测评
7. [接入真实数据与真实模型](#7-接入真实数据与真实模型)
8. [代码地图与扩展](#8-代码地图与扩展)
9. [测试与合规](#9-测试与合规)

---

# 1. 需要的配置

只有两处需要你自己配，**两处都不配也能双击 `start.bat` 直接跑起来**：

| 要配的东西 | 改哪个文件 | 改哪一行 | 不配的后果 |
|---|---|---|---|
| **LLM API Key** | 根目录 `local.env` | `LLM_PROVIDER` + `ARK_API_KEY`/`ARK_MODEL`（或 `OPENAI_*`） | 走离线策略决策器，功能完整、不联网 |
| **Postgres** | 根目录 `local.env` | `DATABASE_URL` | 记忆只存内存，重启就丢 |

上手三步：

```powershell
copy local.env.example local.env              # 1. 生成本地配置
notepad local.env                             # 2. 填你的 key / 数据库连接串
psql -U postgres -f docs/postgres_init.sql    # 3. 要用 Postgres 才需要，先改脚本里的密码
```

- **完整配置说明：[`docs/CONFIG.md`](docs/CONFIG.md)**（含全部环境变量清单）
- **Postgres 建账号脚本：[`docs/postgres_init.sql`](docs/postgres_init.sql)**

### 配没配对，一眼就能看出来

```powershell
curl http://127.0.0.1:8000/api/health
```

`memory_backend` 字段会**如实告知**当前状态：

| 值 | 含义 |
|---|---|
| `postgres` | 配对了，记忆真的写进数据库 |
| `memory` | 没配 `DATABASE_URL`，只存内存（重启丢） |
| `memory (postgres unavailable)` | **配了但连不上**，已降级，去看后端控制台警告 |

> **凭据只写 `local.env`**（已 gitignore，永不入库）。不要写进 `config.py`、
> `start.bat` 或任何会被提交的文件。缺 key 时程序会直接抛错而非静默降级 ——
> 避免你以为在用真模型、其实跑的是离线策略。

---

# 2. 快速开始

**Windows 一键**：双击 `start.bat`，脚本自动检查环境、装依赖、起前后端并打开浏览器。
停止双击 `stop.bat`。前置要求：Python 3.11+、Node.js 18+，都已加入 PATH。

**手动启动**：

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（另开终端）
cd frontend && npm install && npm run dev
```

| 用途 | 地址 |
|---|---|
| 对话界面 | http://localhost:5173 |
| 接口文档（Swagger 自动生成） | http://127.0.0.1:8000/docs |

**端到端演示**（需先起后端）：

```bash
cd backend && python demo.py        # 六品类比价
cd backend && python demo_health.py # 配料分析与健康档案
```

---

# 3. 为什么做这个

购物决策里有三件事是搜索框和商品详情页解决不了的，这个项目就是冲着这三件事做的。

### 痛点一：多平台比价，比的不是标价而是到手价

同一台笔记本在四个平台标价可能差 200，但叠加优惠券、满减、运费、会员折扣之后
排序完全反过来。手动比价的麻烦在于：

- 各平台的**同款判定**很难 —— 标题噪音多（"2024款""旗舰""国行"），
  而 16G/512G 和 32G/1T 根本不是同一件商品，混着比价毫无意义
- 到手价要**拆开算**才可信，不能只看一个数字

做法：`matching.py` 用「品牌 + 归一化型号 + 品类声明的 identity 属性 + 成色」
做同款键，配置差异不合并；`pricing.py` 输出到手价的**每一项构成与依据**，
不是给个结果让你猜。

### 痛点二：个性化偏好，尤其是有硬禁忌的时候

"帮我推荐个洗发水"对不同的人是完全不同的问题。糖尿病患者不该被推荐高糖零食，
敏感头皮不该被推荐含 SLS 的洗发水 —— 这类需求**不是排序靠后的问题，是必须排除**。

做法：用户档案里的条件（糖尿病 / 高血压 / 坚果过敏 / 孕期 / 敏感头皮 / 硫酸盐过敏
/ 健身 / 游戏重度）通过品类配置里的 `concern_rules` 生效，分三档：

| 级别 | 效果 |
|---|---|
| `avoid` | **硬过滤**，含该成分的商品直接不出现在候选池 |
| `prefer` | 加分 |
| `boost` | 提升相关打分维度的权重（如游戏重度 → 性能维度加权） |

对声明了配料字段的品类（洗发水、食品），会把配料表**逐成分**拆开，对照知识库
给出功效、风险、对症人群，并与用户档案交叉得出「适合你 / 需注意 / 不建议」。
成分匹配支持括号内外双向归一，"月桂醇硫酸酯钠(SLS)"、"浓缩乳清蛋白(蛋白质)"都能命中。

除了「不能用什么」，还要回答「这瓶到底治不治我的问题」。品类配置里的
`need_tags` 把槽位取值翻译成成分诉求标签（`hair_issue=dandruff` → 头屑 / 头皮瘙痒 /
脂溢性皮炎），再与知识库的 `helps_with` 求交集：

- 命中 → 记入 `matched_needs`，加分并给出「含吡硫鎓锌，针对头屑有效」这类具体理由
- 没命中 → 记入 `unmet_needs`，**如实写进注意事项**而不是假装匹配

这条链路是「选了头屑头痒和选了干枯毛躁，结果必须不一样」的保证。

### 痛点三：长链路决策，需求是聊出来的

真实购物很少一句话说清。用户说"想买个笔记本"，缺预算、缺用途、缺便携性要求；
说"预算 1000 买游戏本"，则是预算根本不够 —— 这时候**装作找到了**才是最坏的结果。

做法：做成真正的 tool-calling agent，让决策层按观测自主决定下一步：

- **品类不明先问**，绝不拿默认品类瞎追问
- **槽位缺失才追问**，最多 3 轮，之后停止纠缠直接给结果
- **候选不足自我修复**：逐级放宽最低规格 → 预算（1.35/1.6/2.0 倍）→ 品牌黑名单，每次重新检索
- **放宽后如实告知**：说明原预算多少、超出多少，不悄悄换掉用户的条件
- **决策前复核价格**，拿不到实时价就标注需要核对，绝不用旧价冒充
- **工具报错降级继续**，单点失败不中断整轮

### 边界：为什么只做决策 + 跳转

不代下单、不碰支付、不存平台登录凭证。决策做完给带参链接，用户在平台自己完成交易。
这样既不触碰支付合规红线，也不需要拿用户的平台账号。

---

# 4. 技术点

## 4.1 技术栈

| 层 | 选型 | 为什么选它 |
|---|---|---|
| 后端框架 | **FastAPI** + Uvicorn | 原生 async（多平台并发拉价必需）、自带 OpenAPI 文档 |
| 流式推送 | **SSE**（`StreamingResponse`） | agent 逐步产出需要流式；单向推送用 SSE 比 WebSocket 轻 |
| 数据校验 | **Pydantic v2** | 领域模型与接口契约共用一套定义 |
| 持久化 | **PostgreSQL** + asyncpg | JSONB 存任务快照；未配置时自动降级内存 |
| 前端 | **React 18** + TypeScript + Vite | 类型安全；品类元信息由后端下发，TS 接口守住形状 |
| 前端状态 | **Zustand** | 一个 store 就够，不为这个体量引 Redux |
| LLM 接入 | **OpenAI 兼容协议**（方舟 / OpenAI / 中转） | 一套 tool-calling 接口跨厂商复用 |
| 测试 | **pytest** + pytest-asyncio | 200 项，含 8 个行为测评用例 |
| 用例集 | **YAML** | 测评用例与基线轨迹声明式管理 |

三个刻意的取舍：

- **零前端硬编码品类**。维度、属性、追问话术、快捷选项全由 `/api/categories`
  下发，前端据此动态渲染。新增品类不需要动前端一行代码。
- **不引 LangChain / LlamaIndex**。核心循环就一个 while，自己写反而能把预算、
  轨迹、降级控得更紧，也不用为了改一行行为去读框架源码。
  LangGraph、MCP、多智能体、few-shot 这四项都提供了**可切换的对照实现**，
  默认全部关闭——判断依据与实测代价见 [§5](#5-agent-相关概念在本项目的落地情况)。
- **离线可跑是硬约束**。`MockClient` 不是演示桩，而是与真模型走**同一套工具接口
  和同一个核心循环**的策略决策器，区别只在「怎么选下一步」。这让测试确定、
  不花钱、不依赖网络。

## 4.2 全品类配置驱动

新增一个品类 = 写一份配置 + 一份数据，**不需要改 agent / ranking / matching / api 代码**。

```
app/catalog/
  schema.py             CategorySchema / AttributeDef / SlotDef / DimensionDef
  definitions.py        通用品类（笔记本 / 手机 / 耳机 / 扫地机）
  categories_health.py  健康品类（洗发水 / 食品）+ 成分知识库
  __init__.py           全局注册表
```

| 配置项 | 作用 |
|---|---|
| `slots` | 需求槽位：必答项、追问话术、快捷选项、关键词 |
| `attributes` | 商品属性：方向（越大越好/越小越好）、枚举档位、同款判定 |
| `dimensions` | 打分维度：权重、合成属性、推荐理由模板 |
| `ingredient_attribute` + `ingredient_knowledge` | 声明配料字段 + 成分知识库（功效/风险/对症/禁忌人群） |
| `need_tags` | 槽位取值 → 成分诉求标签，让"用户说的问题"参与打分 |
| `concern_rules` | 用户条件如何影响本品类：avoid / prefer / boost |

目前已内置六个品类：笔记本、手机、无线耳机、扫地机器人（标准规格比价），
洗发水、食品（额外做配料表分析）。离线样本共 410 条报价，覆盖四个平台，
每个品类都跨满各预算档位（含低价档），避免筛完只剩两三款、不同诉求给出同一批结果。

## 4.3 Agent 架构：决策层 + 工具层

系统是一个真正的 tool-calling agent，不是包了壳的规则流水线。

```
用户输入
  ↓
graph.py     只做三件事：建 Context、驱动循环、把工具结果转成 SSE 事件
  ↓
决策层        每一步读任务观测，决定下一个调哪个工具（llm.py）
  ↓
工具层        17 个工具，全部业务能力都在这一个文件里（toolkit.py）
  ↓
结果回填进消息历史 → 再决策 …… 直到 compose_answer 收尾
```

**关键点：`graph.py` 里没有任何购物决策。**「要不要追问、追问什么、是否换品类、
候选太少怎么办、结论怎么说」全部由决策层调工具决定。

| 类别 | 工具 |
|---|---|
| 品类 | `list_categories`、`get_category_schema`、`detect_category`、`set_category`、`ask_category_choice` |
| 需求 | `understand_requirement`、`ask_clarifying_question`、`relax_constraints` |
| 比价 | `search_candidates`、`refresh_prices_now`、`verify_price_before_redirect` |
| 个性化 | `get_user_profile`、`update_user_profile`、`analyze_ingredients`、`rerank_with_weights`、`drop_candidates` |
| 收尾 | `compose_answer` |

改业务逻辑只需动 `toolkit.py` 这一个文件。

## 4.4 实时价格的三道保障

Mock 数据仅用于开发。接入真实数据后，用户侧实时性由三道机制保证：

1. 决策前对 Top-5 候选强制实时复核（`refresh_prices_now`）
2. 拿不到实时价就标记 `stale` 置灰，**绝不用旧价冒充**
3. 跳转前二次校验，价格变动超 2% 提示用户核对

---

# 5. Agent 相关概念在本项目的落地情况

这一节集中回答「这些技术你到底用了没、用在哪、为什么不用」。
先给总表，再逐个展开只讲代码里真实存在的部分。

| 概念 | 用了没 | 落在哪 / 为什么不用 |
|---|---|---|
| **Agent（自主决策）** | 用了，系统主干 | 决策层每步按观测自选工具，`graph.py` 不含任何购物决策 |
| **Function Calling** | 用了，系统主干 | `toolkit.py:tool_schemas()`，17 个工具的 OpenAI tools schema |
| **ReAct 范式** | 用了，但不输出思考文本 | 观测→决策→行动→新观测的闭环，见 [§5.2](#52-react-范式的闭环) |
| **CoT（思维链）** | 用了，落成结构化轨迹 | 推理过程走 `TraceStep` 和 pros/cons 依据，不是自然语言独白 |
| **SSE 流式** | 用了 | `routes.py` 的 `StreamingResponse` + 前端手动读 `ReadableStream` |
| **RAG（检索增强）** | 用了，非向量 | 成分知识库精确检索，见 [§5.4](#54-rag-流程与为什么不用向量) |
| **记忆管理** | 用了，三层 | 详见 [§6.3](#63-记忆memorypy--repositorypy) |
| **工作流编排** | 用了，但不是静态图 | 单一核心循环 + 三重预算，见 [§6.1](#61-编排orchestratorpy) |
| **幻觉治理** | 重点做了 | 五道机制，见 [§5.5](#55-幻觉治理五道机制) |
| **智能体框架（LangChain 等）** | **主动不用** | 核心循环自己写，理由见 [§4.1](#41-技术栈) |
| **LangGraph** | 有可切换对照实现，**默认关闭** | `harness/langgraph_loop.py`，代价见 [§5.3](#53-langgraph-与多智能体对照实现默认关闭) |
| **多智能体协作** | 有可切换对照实现，**默认关闭** | `harness/multi_agent.py`，仅跨品类对比时有正收益，见 [§5.3](#53-langgraph-与多智能体对照实现默认关闭) |
| **MCP** | 有可切换对照实现，**默认关闭** | `app/mcp/`，17 个工具零改动即可暴露，见 [§5.6](#56-mcp-对照实现默认关闭) |
| **Few-shot** | 有可切换对照实现，**默认关闭** | `agent/few_shot.py`，实测 +119% token，见 [§5.7](#57-prompt-策略与-few-shot-对照实现) |

> **关于「默认关闭的对照实现」。** 上表里 LangGraph、多智能体、MCP、few-shot 四项，
> 在本项目当前规模下实测是**净负收益**（各自的代价数据见下文）。
> 但「我判断不该用」和「我不会用」是两件事，所以每一项都提供了一份**能跑通的对照实现**，
> 由环境变量开关控制（见 `local.env.example`）：
>
> | 开关 | 打开后 | 实测代价 |
> |---|---|---|
> | `USE_LANGGRAPH=1` | 主循环换成 LangGraph `StateGraph` | 流式退化成批式 |
> | `USE_MCP=1` | 工具走 MCP 协议暴露/调用 | 多一层序列化，无功能增益 |
> | `USE_MULTI_AGENT=1` | 跨品类对比时每品类起一个子 agent | token ≈ 品类数倍数 |
> | `USE_FEW_SHOT=1` | 系统提示词追加 4 条示例 | 325 → 712 tokens（**+119%**） |
>
> 两条硬约束（写在 `harness/flags.py` 里）：
> 1. **默认全关时，行为与引入这些代码之前完全一致**——由等价性测试守住：
>    四种开关组合下候选数与 Top3 必须逐字相同（`tests/test_alt_implementations.py`）
> 2. 打开后若依赖缺失，**明确报错而不是静默退回**，否则你会以为在用 LangGraph、其实跑的是原路径
>
> 当前打开了哪些，`/api/health` 的 `alt_implementations` 字段会如实上报。

## 5.1 Agent 的判定标准：自主性在哪

「能对话 + 会调函数」不等于 agent。这个项目里决策权真的交了出去：

- **下一步做什么由决策层定**，不是写死的 if-else。`graph.py` 只做三件事：
  建 Context、驱动循环、把工具结果转成 SSE 事件
- **同一句输入可以走出不同路径**：品类不明→先问；槽位缺→追问；候选为 0→
  自我修复放宽；工具报错→换路。这些分支不在代码里预设顺序
- **失败可自愈**：`relax_constraints` 逐级放宽最低规格→预算（1.35/1.6/2.0 倍）
  →品牌黑名单，每次重新检索，且放宽后如实告知超出原预算多少

判断依据很简单：把 `toolkit.py` 里某个工具改掉，agent 的行为会跟着变，
而不需要动流程代码。

## 5.2 ReAct 范式的闭环

核心循环就是 ReAct 的形状，只是**不让模型把思考写成自然语言**：

```
观测(Observation)  _observation() 汇总任务真实状态:
                   候选数、缺失槽位、已做过什么、已拉黑哪些工具
      ↓
决策(Reasoning)    决策层读观测,输出 tool_calls 或 final
      ↓
行动(Action)       execute_tool() 执行,结果回填进消息历史
      ↓
新观测             回到第一步,直到 compose_answer 收尾
```

**刻意不做「让模型先输出一段 Thought 再行动」**。原因是那段文本既要花 token、
又会被用户看到却无法验证真假，反而增加幻觉暴露面。这里的「思考」以
`TraceStep`（工具名、参数、成败、耗时、token）形式落盘，可回放、可断言、可测评。

## 5.3 LangGraph 与多智能体（对照实现，默认关闭）

### LangGraph：`USE_LANGGRAPH=1`

对照实现在 `backend/app/harness/langgraph_loop.py`，用 `StateGraph` 把主循环
拆成三个节点，与自写循环**共用**同一套决策层、工具、`BudgetGuard`、`ContextAssembler`：

```
assemble ──> decide ──> act ──┐
   ^                          │  未结束
   └──────────────────────────┘
                              └──> END（BudgetGuard 判定或决策层收尾）
```

`recursion_limit` 设为 `max_steps * 3 + 10`，但真正的终止条件仍然是 `BudgetGuard`
——框架的递归限制只是最后一道兜底，不参与业务判断。

**默认不用它的直接原因**：LangGraph 的节点函数不能 `yield`。本项目的 SSE 是
逐工具推事件的，走图之后事件只能先攒进 `state["events"]`、等整张图跑完再一次性吐出，
**流式退化成批式**——用户从「看到 agent 一步步在做什么」变成「转圈等一个结果」。
这是产品体验上的实质倒退，换来的只是控制流的图形化表达，而这个控制流本来就只有三个节点。

其余代价与 [§4.1](#41-技术栈) 一致：预算、轨迹、工具拉黑、降级都要绕框架抽象走。

### 多智能体：`USE_MULTI_AGENT=1`

对照实现在 `backend/app/harness/multi_agent.py`，采用 **Supervisor + 并行 Worker**：

```
Supervisor：识别涉及哪些品类，派发子任务
   ├── Worker(laptop)  ─┐
   ├── Worker(phone)   ─┼─ asyncio.gather 并行，各自独立 ShoppingTask
   └── Worker(earbuds) ─┘
              ↓
   Supervisor：汇总为一份可对比的结论
```

**刻意不用辩论式**，选了可归因的派发式。因为结论必须能追溯到自己的完整决策路径，
辩论出的折中结论无法回答「为什么这瓶排第一」——而这正是本项目的核心交付物。

**只在跨品类横向对比时启用**（`detect_multi_categories()` 识别出 ≥ 2 个品类），
否则自动退回单 agent。这是多智能体在本场景**唯一有正收益**的情形：
「预算 5000，买笔记本还是手机」这类问题里，各品类的检索与排序确实互不相干。
单品类下拆分则纯属开销——比价、成分分析、排序是**严格顺序依赖**的流水线。

汇总时**刻意不给唯一冠军**：跨品类没有公共量纲（笔记本的性能分和洗发水的成分分
不是同一个刻度），所以只给各自最优 + 依据，把权重留给用户。

**代价**：每个 worker 各跑一遍完整循环，token 约等于品类数的倍数；
失败点从 1 个变成 N 个（用 `return_exceptions` 兜住，单品类失败不影响其他品类）。

实现时踩到的两个真实 bug，都由测试守住了：

1. **无限递归**——worker 内部又触发多智能体分支自我派发。
   修法：`ShoppingAgent(allow_multi_agent=False)`
2. **所有 worker 返回同一件商品**——用户原文含多个品类触发词，
   worker 里的 `detect_category` / `set_category` 会把品类改回同一个。
   修法：`ctx.flow["lock_category"]`，锁定后品类识别与切换不再覆盖外部指定的品类

**结论没变**：默认仍是单 agent。真需要横向扩展时，正确的做法是加工具，而不是加 agent。

## 5.4 RAG 流程与为什么不用向量

对声明了配料字段的品类（洗发水、食品），检索增强的完整流程：

```
1. 取配料表原文        group.spec[schema.ingredient_attribute]
2. 切分               split_ingredients() 按品类声明的分隔符拆成单条成分
3. 检索               在 ingredient_knowledge 里逐条精确匹配
4. 归一               _match() 括号内外双向匹配 + 别名表 + 子串包含
5. 交叉               与用户档案(禁忌)和 need_tags(诉求)求交集
6. 注入               作为工具返回值进上下文,供决策层引用
```

**为什么不用 embedding + 向量库。** 这个场景的要求是硬过滤——
「含 SLS 就必须排除」。而「月桂醇硫酸酯钠（SLS）」和
「月桂醇聚醚硫酸酯钠（SLES）」在向量空间里极度接近，但一个要排除、一个不用。
语义近似在这里是风险而不是优势。

**做的优化都在归一化而非召回上：**

| 优化 | 解决的问题 |
|---|---|
| 括号内外双向匹配 | `月桂醇硫酸酯钠(SLS)` 与 `浓缩乳清蛋白(蛋白质)` 两种写法都命中 |
| 别名表 | `白砂糖`/`果葡糖浆`/`蔗糖` 都归一到「添加糖」 |
| 子串包含（≥2 字） | 配料写`浓缩乳清蛋白`能命中别名`乳清蛋白` |
| 括号内再按 `/、,` 切分 | `代糖/糖醇` 这类复合标注不漏 |
| 未识别成分单独留存 | 进 `unrecognized`，不假装看懂 |

知识库规模有限是已知边界：洗发水 12 条、食品 8 条成分。扩充方式是往
`categories_health.py` 的 `ingredient_knowledge` 加条目，不需要改代码。
成分数量上千后再考虑「向量粗筛 + 精确规则复核」的两段式。

## 5.5 幻觉治理：五道机制

不接 key 时不存在幻觉问题；接了真模型后靠这五道防线：

| 机制 | 做法 | 挡住的幻觉类型 |
|---|---|---|
| **数据不由模型产生** | 价格、规格、配料全部来自适配器，模型只能引用工具返回值 | 编造不存在的型号和价格 |
| **结论必须有依据** | pros/cons 由 `ranking.py` 按维度得分和模板生成，不是模型自由写 | 编造推荐理由 |
| **价格新鲜度硬标注** | 拿不到实时价就标 `stale` 置灰，跳转前二次校验，变动超 2% 提示 | 拿旧价当现价 |
| **未覆盖如实说** | 诉求没有对应有效成分就记 `unmet_needs` 并写进注意事项 | 假装对症 |
| **超预算如实告知** | 放宽约束后必须说明原预算多少、超出多少（有专门测试守） | 悄悄换掉用户条件 |

系统指令里也明确写了「拿不到实时价就如实说明，不许用旧价冒充」。
最后一道是测评：LLM-as-judge 的三项打分里 `honesty` 和 `grounding` 各占一项。

## 5.6 MCP（对照实现，默认关闭）

MCP（Model Context Protocol）是 Anthropic 提出的**工具调用标准协议**，
让工具能跨进程、跨宿主复用：同一个工具服务可以同时被不同的 agent 客户端接入。

对照实现在 `backend/app/mcp/`，`USE_MCP=1` 打开：

| 文件 | 职责 |
|---|---|
| `server.py` | schema 双向转换 + 进程内桥接 + 标准 MCP server（stdio） |
| `__main__.py` | `python -m app.mcp` 把本项目工具作为 MCP 服务暴露出去 |

**改动面之所以极小**，是因为工具层本来就收敛成「schema + handler」两部分：

- `build_mcp_tools()`：`tool_schemas()` 的 `function.parameters` 直接对应 MCP 的 `inputSchema`
- `to_openai_schema()`：反向转换，让远端 MCP 工具能和本地工具混在同一张工具表里喂给模型
- `InProcessMCPBridge`：走完整的 MCP 数据结构（`CallToolResult` / `TextContent`）
  但不起子进程，用于在不引入部署复杂度的前提下验证协议契约

**17 个工具零改动全部暴露**，schema 往返无损——有测试逐字比对
`description` 与 `parameters`（`tests/test_alt_implementations.py`）。

**默认关闭的原因**：当前是单体应用，工具与决策层同进程。走 MCP 只是多一层
序列化 / 反序列化，**没有任何功能增益**。协议的价值要到「工具被第三方复用」
或「引入外部 MCP 工具」时才兑现——而那一天到了，打开开关就行，这也正是
把它做成对照实现而不是删掉的理由。

## 5.7 Prompt 策略与 few-shot 对照实现

Few-shot 是**在提示词里放几个完整示例**，让模型照着模仿，
不改一行权重就能对齐输出格式与风格（区别于 zero-shot 的纯指令描述）。

默认只有一个 `SYSTEM_PROMPT`（在 `llm.py`），内容是**决策纪律而非话术**：
工具调用的建议顺序、追问上限、拿不到实时价要如实说。

### 对照实现：`USE_FEW_SHOT=1`

`backend/app/agent/few_shot.py` 提供 4 条示例，覆盖四种典型决策路径：
品类未知先问、信息够了直接检索、成分类品类追加分析、预算不足如实告知。

示例**只演示决策路径，不含任何品类商品知识**——品类知识属于 `app/catalog/`
的职责，写进提示词会造成两处真相，新增品类就得改 prompt。有测试守住这条边界：
`酮康唑`、`MagicBook`、`RTX` 这类词不允许出现在示例里。

`llm.py` 的 `active_system_prompt()` 是唯一入口，自写循环与 LangGraph 循环
都走它，避免两条路径的提示词分叉。

### 默认关闭的原因：实测代价

| | tokens |
|---|---|
| 基础系统提示词 | 325 |
| few-shot 追加 | +387 |
| 合计 | 712（**+119%**） |

**每一轮请求都要多付这 387 token**，换来的收益在本项目却很有限：

- 工具的 `description` 和 `parameters` 已经是最精确的格式约束，
  比举例更省 token 且不会被示例带偏
- 购物场景输入分布太广（六品类 × 各种表达），4 条示例覆盖不了，
  反而容易让模型往示例出现过的品类上靠
- 品类专属话术全在 `app/catalog/` 配置里，由工具返回值携带

真正值得打开的场景：换了个指令跟随能力较弱的小模型，
它不按 schema 输出、或者不肯先追问就直接推荐。这时 387 token 换稳定性是划算的。

### 动态部分

由 `context.py` 装配：系统指令 → 长期记忆摘要 → 历史对话 →
当前观测 → 本轮输入 → 工具结果，超预算时按优先级裁剪（[§6.2](#62-上下文contextpy)）。

# 6. Harness 层：编排 / 上下文 / 记忆 / 测评

光有「模型 + 工具」不算 agent，还得有一层把它养活的基础设施。
这四块全在 `backend/app/harness/`，**不含任何购物逻辑** —— 它不知道什么是预算、
什么是洗发水，只知道「决策者、工具、预算、追踪」。

## 关键设计点（也是跟「调一下模型」的区别）

| 点 | 具体做法 | 不这么做会怎样 |
|---|---|---|
| **预算硬上限** | 步数/token/耗时三重，触顶即收敛并告知原因 | 模型打环就无限循环，前端永远 loading |
| **工具可放弃** | 同一工具连续失败 2 次就拉黑，并在观测里告知决策层「这个已不可用」 | 模型反复撞同一面墙直到耗尽预算 |
| **上下文有优先级地裁** | 先丢早期工具结果，再摘要旧对话；系统指令/当前输入/最近工具结果永不丢 | 简单截断会把"你是谁"和"用户刚说什么"剔掉 |
| **观测而非口令** | 每步把任务真实状态（候选数、缺失槽位、已做过什么、已拉黑工具）喂回去 | 模型靠猜，重复调已完成的工具 |
| **记忆可撤销** | 每条记忆带原话依据与置信度，前端一键「忘掉它」 | 黑盒子，用户不知道系统背着它记了什么 |
| **降级如实暴露** | 连不上 Postgres 就在 `/api/health` 写 `memory (postgres unavailable)` | 以为存住了，其实一重启全没 |
| **行为可回归** | 轨迹录基线，改动后自动报「缺少/新增了哪些工具」 | 改一行 prompt 默默弄坏三个场景，没人发现 |
| **离线可测评** | 无 key 时走行为断言 + 轨迹对比，确定且不花钱 | 测评只能手测，或者每次 CI 都烧钱 |

一句话概括：**模型负责「下一步做什么」，harness 负责「别失控、别失忆、别让你不知道出了什么事」。**

## 6.1 编排（`orchestrator.py`）

三重预算上限，任一触顶即收敛，**永远保证产出结果**，不让前端卡在 loading：

| 预算项 | 默认 | 作用 |
|---|---|---|
| `max_steps` | 14 | 防死循环 |
| `max_tokens` | 60000 | 防上下文失控花钱 |
| `max_seconds` | 90 | 防卡死 |
| `max_tool_retries` | 2 | 同一工具连续失败则放弃它，告知决策层换路 |

每一步（决策 / 工具 / 结论 / 报错）都落成 `TraceStep`：名字、参数、成败、耗时、token。
这份轨迹同时服务三个场景：前端调试面板、日志、测评的轨迹对比。

## 6.2 上下文（`context.py`）

装配顺序：系统指令 → 长期记忆摘要 → 历史对话 → 当前观测 → 本轮输入 → 工具结果。

超出预算时的裁剪**有优先级**，永不丢系统指令 / 当前输入 / 最近的工具结果：

1. 先丢早期工具结果（只留最近 3 条）
2. 再把较早的对话压成摘要（保留最近 6 轮原文）
3. 候选列表只留 5 条、每条只留关键字段

> 顺手修了一个严重 bug：旧的循环每轮从零重建消息列表，只放当前一句输入，
> 历史存了却从没读过 —— 多轮对话完全失忆。现已由 `test_evals.py` 的
> `multi_turn_context_retained` 用例守住。

## 6.3 记忆（`memory.py` + `repository.py`）

三层记忆，生命周期不同：

| 层 | 范围 | 内容 |
|---|---|---|
| `SessionMemory` | 单会话 | 逐轮对话原文 |
| `TaskMemory` | 单任务 | 看过哪些候选、拒了哪些、放宽过几轮 |
| `LongTermMemory` | 跨会话永久 | 健康条件、品牌黑白名单、价格态度 |

长期记忆从对话里**自动沉淀**：你说「我有糖尿病，平时打游戏，不要小米」，
系统会抽出 3 条记忆并弹出「已记住…」提示。健康类条件会同步进档案，
让 `concern_rules` 硬过滤直接生效。

**记忆必须可感知、可撤销** —— 右上角「记忆」面板列出每条记忆、为什么记住的
（原话依据），并给一个「忘掉它」按钮。否则就是黑盒子。
对应接口：`GET /api/memory`、`DELETE /api/memory?kind=&value=`。

**持久化**：配了 `DATABASE_URL` 就存 Postgres，三张表
`user_memory` / `shopping_task` / `conversation_turn`（应用首次启动自动建表）。
读走进程内缓存、写异步回写，请求路径不阻塞；持久化失败只记警告，不影响用户当前请求。
没配或连不上会降级内存，并在 `/api/health` 如实标注（见 [§1](#1-需要的配置)）。

## 6.4 测评（`backend/evals/`）

```bash
cd backend
python -m evals.runner                    # 控制台报告
python -m evals.runner --no-judge         # 强制走离线双轨
python -m evals.runner --json report.json # 写 JSON 报告
python -m evals.runner --case laptop_basic_gaming
python -m evals.runner --update-baseline  # 行为变更合理后重录基线
```

双轨评判：

- **接入了 LLM 凭据** → LLM-as-judge 为主，按 relevance / honesty / grounding
  三项打分（各 0-2），行为断言作为硬底线
- **未接入** → 行为断言 + 轨迹对比，完全离线、确定、不花钱

判官宁可不跑也不用 `MockClient` 凑数：用离线策略当自己的判官只会自己给自己发奖状。
判官凭据可用 `JUDGE_PROVIDER` / `JUDGE_MODEL` 单独指定，默认跟随 `LLM_PROVIDER`。

用例写在 `evals/cases.yaml`，断言五类：

| 断言 | 含义 |
|---|---|
| `tool_used` / `tool_not_used` | 必须（不）调用某工具 |
| `event_type` | 必须产出某类事件（`report` / `clarify` / `memory_updated`…） |
| `text_contains` | 结论必须提到关键信息（如超预算要如实告知） |
| `text_excludes` | 结论不得出现某内容（如被拉黑的品牌） |
| `max_steps` | 工具调用次数上限 |

**轨迹对比**用序列相似度而非集合比较，因为调用顺序本身就是行为的一部分：
先检索再刷价与先刷价再检索是两种策略。基线变了会指出「缺少/新增了哪些工具」。

测评集已接入 pytest（`tests/test_evals.py`），行为回归跟单测一起守，这部分永远离线跑。

---

# 7. 接入真实数据与真实模型

> 项目里有三处叫 "API" 的东西，先分清：

| # | 是什么 | 在哪看 / 在哪改 | 要不要 key |
|---|---|---|---|
| 1 | **本项目对前端暴露的 HTTP 接口** | http://127.0.0.1:8000/docs ；代码在 `app/api/routes.py` | 不需要 |
| 2 | **电商平台数据接口**（拿真实商品和价格） | `app/adapters/base.py` 的 `LiveAdapter` | 需要平台联盟凭据 |
| 3 | **大模型接口**（给 agent 做决策） | `app/agent/llm.py` | 需要模型厂商 key |

## 7.1 本项目的 HTTP 接口一览

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查：数据源模式、已注册品类、记忆后端 |
| GET | `/api/categories` | 品类元信息，前端动态渲染的数据来源 |
| POST | `/api/chat/stream` | **主接口**，SSE 流式返回决策过程与结论 |
| GET | `/api/tasks` · `/api/tasks/{id}` | 任务列表 / 详情（候选、报告、权重、决策日志） |
| POST | `/api/tasks/{id}/weights` | 调整打分权重并重排 |
| POST | `/api/tasks/{id}/drop` | 排除指定候选 |
| POST | `/api/tasks/{id}/refresh` | 实时复核候选价格 |
| POST | `/api/tasks/{id}/redirect/{offer_id}` | 跳转前价格二次校验，返回带参链接 |
| GET / PUT | `/api/profile` | 读取 / 更新用户健康与偏好档案 |
| GET / DELETE | `/api/memory` | 查看 / 删除长期记忆 |
| GET | `/api/trace` | 最近一次运行轨迹（调试用） |

## 7.2 接入电商平台（换掉本地样本）

只改 `app/adapters/base.py` 里的 `LiveAdapter` 一个类。agent、比价、打分、前端
都只依赖 `PlatformAdapter` 抽象协议，不关心数据来自 API、爬虫还是本地样本，
所以**其他文件一行都不用动**。当前三个方法都是抛 `NotImplementedError` 的骨架：

```python
class LiveAdapter(PlatformAdapter):
    realtime = True

    def supported_categories(self) -> list[str]: ...   # 该平台供货的品类
    async def search(self, query) -> list[RawOffer]: ...  # 平台搜索 → RawOffer
    async def refresh_offer(self, offer) -> Offer: ...    # 查单品实时价
```

`RawOffer` 由两部分组成：`offer`（标价、券、到手价、链接、库存、抓取时间）与
`spec`（品牌、型号、品类、`attributes` 字典 —— 键必须用 `app/catalog/` 里该品类
声明的 attribute key）。照抄 `app/adapters/fixtures/jd/laptop.json` 的结构最直观，
那就是这两个对象序列化后的样子。

切换开关在 `create_adapters()`：`DATA_SOURCE_MODE=mock`（默认，读本地 fixture，
不发外部请求）/ `live`（走 `LiveAdapter`）。平台凭据同样只走环境变量。

## 7.3 接入大模型

**通常不用改代码**，配好 `local.env` 就能切换（见 [§1](#1-需要的配置)）。
实现有意收敛到 `app/agent/llm.py` 单文件：

| 位置 | 作用 |
|---|---|
| `build_llm()` | 按 `LLM_PROVIDER` 选择决策者，新增厂商在这里加分支 |
| `OpenAICompatibleClient` | OpenAI 兼容协议实现（方舟、OpenAI、多数国内厂商都兼容） |
| `MockClient` | 离线策略决策器，不需要 key |
| `SYSTEM_PROMPT` | 给模型的系统指令，想调决策风格改这里 |

如果对方不兼容 OpenAI 协议，继承 `LLMClient` 实现一个 `decide` 即可，
再在 `build_llm()` 加分支，`graph.py` 和 `toolkit.py` 都不用改：

```python
class YourClient(LLMClient):
    async def decide(self, messages, tools, state) -> Decision:
        # 要求调工具：Decision(tool_calls=[{"name": ..., "arguments": {...}}])
        # 给出最终答复：Decision(final="...")
        ...
```

---

# 8. 代码地图与扩展

| 能力 | 位置 |
|---|---|
| 品类注册表 | `app/catalog/` |
| 平台适配 / 本地样本 | `app/adapters/base.py`、`app/adapters/fixtures/` |
| SKU 同款对齐 | `app/services/matching.py` |
| 到手价引擎 | `app/services/pricing.py` |
| 配置驱动打分 | `app/services/ranking.py` |
| 新鲜度与实时校验 | `app/services/freshness.py` |
| 成分分析 | `app/ingredients/analyzer.py` |
| 健康档案 | `app/profile/` |
| Agent 核心循环 | `app/agent/graph.py` |
| 决策层（mock / ark / openai） | `app/agent/llm.py` |
| 工具层（17 个工具，单文件） | `app/agent/toolkit.py` |
| 需求抽取与追问 | `app/agent/extract.py` |
| 序列化 / 报告辅助 | `app/agent/serialize.py` |
| 编排：预算 / 轨迹 / 重试 / 收敛 | `app/harness/orchestrator.py` |
| 上下文装配与裁剪 | `app/harness/context.py` |
| 三层记忆与自动沉淀 | `app/harness/memory.py` |
| 持久化（Postgres，可降级） | `app/harness/repository.py` |
| 测评（断言 / 轨迹 / judge） | `backend/evals/` |
| 本地配置加载 | `app/env.py` |

**新增一个品类**：以"机械键盘"为例，在 `app/catalog/definitions.py`
（健康类放 `categories_health.py`）注册 `CategorySchema` —— triggers / slots /
attributes / dimensions / budget_options，再放一份 fixture。注册后 Agent、比价、
打分、追问、前端全部自动可用。若要做配料分析，额外声明 `ingredient_attribute`、
填充 `ingredient_knowledge` 和 `concern_rules`。

---

# 9. 测试与合规

```bash
cd backend && pytest -q                    # 166 项
cd backend && python -m evals.runner --no-judge   # 8 个行为测评用例
```

覆盖六品类决策链路、工具编排顺序、候选不足自我修复、超预算如实告知、SKU 对齐、
权重重排、品类切换、实时价格校验、配料分析、健康档案硬过滤/加权、上下文多轮不失忆、
`local.env` 加载优先级。新品类只需把 key 加入 `ALL_CATEGORIES` 即自动纳入全量参数化验证。

**合规边界**：混合数据层，优先联盟/开放 API（自带带参跳转）。爬虫只做低频补齐，
遵守 robots.txt、低并发、短 TTL、不绕过登录/风控、不搬运隐私数据。
不代下单、不碰支付、不存平台凭证。
