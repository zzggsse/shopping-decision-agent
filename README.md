# 购物决策助手

对话式购物 Agent,解决**多平台比价**、**个性化偏好**、**长链路决策**三层问题,
并支持**配料表/营养成分精准分析**与**跨会话用户健康档案**。
定位:「只做决策 + 跳转」——不代下单、不碰支付、不存平台凭证。

目前已内置六个品类,架构按全品类设计:

| 品类 | 数据特点 |
|---|---|
| 笔记本电脑 / 智能手机 / 无线耳机 / 扫地机器人 | 标准规格参数比价 |
| 洗发水 | **配料表逐成分分析**,匹配头发问题与敏感体质 |
| 食品(零食) | **营养成分分析**,按糖尿病/高血压/过敏等条件过滤 |

## 全品类架构

新增一个品类 = 写一份配置 + 一份数据,**不需要改 agent / ranking / matching / api 代码**。

```
app/catalog/
  schema.py        CategorySchema / AttributeDef / SlotDef / DimensionDef
  definitions.py   通用品类(笔记本/手机/耳机/扫地机)
  categories_health.py  健康品类(洗发水/食品)+ 成分知识库
  __init__.py      全局注册表
```

每个品类配置三块内容,健康品类额外有两块:

| 配置项 | 作用 |
|---|---|
| `slots` | 需求槽位:必答项、追问话术、快捷选项、关键词 |
| `attributes` | 商品属性:方向(越大越好/越小越好)、枚举档位、同款判定 |
| `dimensions` | 打分维度:权重、合成属性、推荐理由模板 |
| `ingredient_attribute` + `ingredient_knowledge` | 声明配料字段 + 成分知识库(功效/风险/对症/禁忌人群) |
| `concern_rules` | 用户条件如何影响本品类:avoid(硬过滤)/ prefer(加分)/ boost(维度加权) |

## 配料表 / 营养成分精准分析

对声明了 `ingredient_attribute` 的品类,系统会把配料文本按分隔符拆分,
对照成分知识库识别每个成分,并输出:

- **功效与风险**:每个成分的 benefits / risks / helps_with
- **适配问题**:洗发水匹配"头屑/脂溢性皮炎/干枯毛躁"等头发问题
- **针对用户禁忌**:与健康档案交叉,给出"适合你/需注意/不建议"
- **硬过滤**:`avoid` 级规则直接剔除不合适商品(见下)

成分匹配支持**括号别名**,如配料里写"月桂醇硫酸酯钠(SLS)"、"聚葡萄糖(膳食纤维)",
会正确归一化到知识库中的同一成分。

## 用户健康与偏好档案(跨会话)

右上角"我的档案"可编辑,跨会话生效。勾选后推荐会自动考虑:

| 条件 | 影响 |
|---|---|
| 糖尿病 | 食品避开添加糖/反式脂肪,优先代糖、膳食纤维 |
| 高血压 | 食品标注高钠与饱和脂肪 |
| 坚果过敏 | 含坚果食品被直接排除(硬过滤) |
| 孕期/备孕 | 洗发水标注水杨酸等慎用成分 |
| 敏感头皮 | 洗发水硬过滤 SLS,优先氨基酸温和配方 |
| 硫酸盐过敏 | 含硫酸盐表活的洗发水被排除 |
| 健身/高蛋白 | 食品偏好高蛋白、高纤维 |
| 游戏重度 | 电脑/手机提升性能维度权重 |

实现位置:`app/profile/`(档案模型与存储)+ `app/ingredients/analyzer.py`(成分分析)。

## 快速开始(Windows)

双击 **`start.bat`** 即可,脚本自动检查环境、装依赖、起后端、起前端并打开浏览器。
停止服务双击 **`stop.bat`**。

前置要求:Python 3.11+、Node.js 18+,都已加入 PATH。

## 手动启动 / 访问地址

```bash
# 后端
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端(另开终端)
cd frontend && npm install && npm run dev
```

| 用途 | 地址 |
|---|---|
| 对话界面 | http://localhost:5173 |
| 接口文档(Swagger,本项目对前端的 HTTP 接口) | http://127.0.0.1:8000/docs |
| 品类元信息 | http://127.0.0.1:8000/api/categories |
| 用户档案 | http://127.0.0.1:8000/api/profile |

端到端演示:

```bash
cd backend && python demo.py        # 六品类比价
cd backend && python demo_health.py # 配料分析与健康档案
```

## Agent 架构:决策层 + 工具层

系统是一个真正的 **tool-calling agent**,不是包了壳的规则流水线。

```
用户输入
  ↓
graph.py  只做三件事:建 Context、驱动循环、把工具结果转成 SSE 事件
  ↓
决策层(llm.py)  每一步读任务观测,决定下一个调哪个工具
  ↓
工具层(toolkit.py)  17 个工具,全部业务能力都在这一个文件里
  ↓
结果回填进消息历史 → 再决策 …… 直到 compose_answer 收尾
```

**关键点:`graph.py` 里没有任何购物决策。** "要不要追问、追问什么、
是否换品类、候选太少怎么办、结论怎么说"全部由决策层调工具决定。

### 工具清单(`app/agent/toolkit.py`)

| 类别 | 工具 |
|---|---|
| 品类 | `list_categories`、`get_category_schema`、`detect_category`、`set_category`、`ask_category_choice` |
| 需求 | `understand_requirement`、`ask_clarifying_question`、`relax_constraints` |
| 比价 | `search_candidates`、`refresh_prices_now`、`verify_price_before_redirect` |
| 个性化 | `get_user_profile`、`update_user_profile`、`analyze_ingredients`、`rerank_with_weights`、`drop_candidates` |
| 收尾 | `compose_answer` |

改业务逻辑只需动这一个文件,`graph.py` 不用碰。

### 决策层可切换

两种决策者走**完全相同**的工具接口与循环,区别只是"怎么选下一步":

| Provider | 说明 |
|---|---|
| `mock`(默认) | 离线策略决策器。读观测按条件选工具,不需要 key、可离线跑完整流程 |
| `ark` | 火山方舟(OpenAI 兼容),由模型自己选工具 |
| `openai` | OpenAI 兼容接口 |

```powershell
# 默认离线,无需任何配置
python demo.py

# 换成真实模型决策(凭据只走环境变量,禁止写入文件)
$env:LLM_PROVIDER="ark"
$env:ARK_API_KEY="<你的key>"
$env:ARK_MODEL="<接入点/模型名>"
python demo.py
```

| 变量 | 说明 |
|---|---|
| `LLM_PROVIDER` | `mock`(默认)/ `ark` / `openai` |
| `ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL` | 方舟凭据,`ARK_MODEL` 必填 |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | OpenAI 兼容同理 |

### 决策层具备的自主行为

这些都不是写死的分支,而是按观测触发的:

- **品类不明先问**,绝不拿默认品类瞎追问
- **槽位缺失才追问**,最多 3 轮,之后停止纠缠直接给结果
- **候选不足自我修复**:逐级放宽最低规格 → 预算(1.35/1.6/2.0 倍)→ 品牌黑名单,每次重新检索
- **放宽后如实告知**:说明原预算是多少、超出多少,不悄悄换掉用户的条件
- **有配料表的品类**先读健康档案再分析成分,然后才下结论
- **决策前复核价格**,拿不到实时价就标注需要核对
- **工具报错降级继续**,单点失败不中断整轮
- **步数上限兜底**(14 步),决策层失控也不会挂死前端

## API 说明:三种别搞混

项目里有三处叫"API"的东西,用途完全不同:

| # | 是什么 | 在哪看 / 在哪改 | 要不要 key |
|---|---|---|---|
| 1 | **本项目对前端暴露的 HTTP 接口** | 运行后访问 http://127.0.0.1:8000/docs (FastAPI 自动生成的 Swagger 文档);代码在 `backend/app/api/routes.py` | 不需要 |
| 2 | **电商平台数据接口**(京东/淘宝联盟等,用来拿真实商品和价格) | `backend/app/adapters/base.py` 的 `LiveAdapter` | 需要各平台联盟凭据 |
| 3 | **大模型接口**(给 agent 做决策) | `backend/app/agent/llm.py` | 需要模型厂商 key |

下面分别说 2 和 3 怎么接。

### 本项目自己的 HTTP 接口一览

起服务后在 http://127.0.0.1:8000/docs 可交互调试。代码全在 `backend/app/api/routes.py`。

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | 健康检查,返回当前数据源模式与已注册品类 |
| GET | `/api/categories` | 品类元信息,前端选择器与动态渲染的数据来源 |
| POST | `/api/chat/stream` | **主接口**,SSE 流式返回 agent 的决策过程与结论 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{task_id}` | 任务详情:候选、报告、权重、决策日志 |
| POST | `/api/tasks/{task_id}/weights` | 调整打分权重并重排 |
| POST | `/api/tasks/{task_id}/drop` | 排除指定候选 |
| POST | `/api/tasks/{task_id}/refresh` | 实时复核候选价格 |
| POST | `/api/tasks/{task_id}/redirect/{offer_id}` | 跳转前价格二次校验,返回带参链接 |
| GET / PUT | `/api/profile` | 读取 / 更新用户健康与偏好档案 |

---

## 接入电商平台 API(换掉本地样本,拿真实价格)

### 改哪里

只改 **`backend/app/adapters/base.py`** 里的 `LiveAdapter` 一个类。
agent、比价、打分、前端都只依赖 `PlatformAdapter` 抽象协议,不关心数据来自
API、爬虫还是本地样本,所以**其他文件一行都不用动**。

当前 `LiveAdapter` 是骨架,三个方法都会抛 `NotImplementedError`:

```python
class LiveAdapter(PlatformAdapter):
    realtime = True

    def supported_categories(self) -> list[str]:
        # 【改这里】返回该平台能供货的品类,如 ["laptop", "phone"]
        return list(self._categories)

    async def search(self, query: SearchQuery) -> list[RawOffer]:
        # 【改这里】调平台搜索接口,把返回结果转成 list[RawOffer]
        raise NotImplementedError(...)

    async def refresh_offer(self, offer: Offer) -> Offer:
        # 【改这里】查单个商品的实时价,用于决策前和跳转前校验
        raise NotImplementedError(...)
```

### 要返回什么

`search` 的返回类型是 `list[RawOffer]`,每个 `RawOffer` 由两部分组成:

- `offer`:报价信息(`Offer`,见 `app/domain/models.py`)——标价、券、到手价、
  平台、商品链接、库存、抓取时间
- `spec`:商品规格(`ProductSpec`)——品牌、型号、品类,以及 `attributes` 字典
  (键必须用 `app/catalog/` 里该品类声明的 attribute key,比如笔记本的 `ram`、`weight`)

照抄 `app/adapters/fixtures/jd/laptop.json` 的结构最直观,那就是这两个对象序列化后的样子。

### 凭据放哪

**不要写进代码或配置文件**,一律走环境变量,和大模型 key 同样处理:

```powershell
$env:DATA_SOURCE_MODE="live"
$env:JD_APP_KEY="..."
$env:JD_APP_SECRET="..."
```

然后在 `LiveAdapter.__init__` 里用 `os.getenv` 读取。

### 切换开关

```bash
DATA_SOURCE_MODE=mock   # 默认,读本地 fixture,开发/CI 用,不发外部请求
DATA_SOURCE_MODE=live   # 走 LiveAdapter,真实 API + 爬虫补齐
```

切换逻辑在 `base.py` 末尾的 `create_adapters()`,要加平台就改 `PLATFORMS` 常量。

### 实时价格的三道保障

Mock 仅用于开发。接入真实数据后,用户侧实时性由三道机制保证:

1. 决策前对 Top-5 候选强制实时复核(`refresh_prices_now` 工具)
2. 拿不到实时价就标记 `stale` 置灰,绝不用旧价冒充
3. 跳转前二次校验,价格变动超 2% 提示用户核对

---

## 接入大模型 API(换掉离线策略决策器)

### 改哪里

**通常不用改代码**,配好环境变量就能切换。实现在
**`backend/app/agent/llm.py`**,是有意收敛到单文件的:

| 位置 | 作用 |
|---|---|
| `build_llm()` | 按 `LLM_PROVIDER` 选择决策者,新增厂商在这里加分支 |
| `OpenAICompatibleClient` | OpenAI 兼容协议的实现(方舟、OpenAI、多数国内厂商都兼容) |
| `MockClient` | 离线策略决策器,不需要 key |
| `SYSTEM_PROMPT` | 给模型的系统指令,想调决策风格改这里 |

### 怎么配

```powershell
# 默认:离线策略决策器,不需要任何 key
python demo.py

# 切换到火山方舟
$env:LLM_PROVIDER="ark"
$env:ARK_API_KEY="<你的key>"
$env:ARK_MODEL="<接入点ID或模型名>"      # 必填,方舟控制台"在线推理"里获取

# 切换到 OpenAI 或其他兼容接口
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="<你的key>"
$env:OPENAI_MODEL="gpt-4o-mini"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"   # 第三方中转改这里
```

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` / `ark` / `openai` |
| `ARK_API_KEY` | — | 方舟 Key |
| `ARK_BASE_URL` | `https://ark.cn-beijing.volces.com/api/v3` | 换区域改这里 |
| `ARK_MODEL` | — | **必填**,缺失会直接报错提醒 |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | — | 同理 |

### 新增一个厂商

如果对方不兼容 OpenAI 协议,在 `llm.py` 里继承 `LLMClient` 实现一个 `decide` 即可:

```python
class YourClient(LLMClient):
    async def decide(self, messages, tools, state) -> Decision:
        # 调你的接口,把结果包成 Decision
        # 模型要求调工具:Decision(tool_calls=[{"name": ..., "arguments": {...}}])
        # 模型给出最终答复:Decision(final="...")
        ...
```

再在 `build_llm()` 里加一个分支。`graph.py` 和 `toolkit.py` 都不用改。

### 安全约定

**API key 一律只走环境变量,禁止写入任何文件**(含 `.env`、`config.py`、`start.bat`)。
`OpenAICompatibleClient` 在缺 key 时会直接抛错,不会静默降级到 mock——避免你以为
在用真模型、其实跑的是离线策略。

## 三层能力实现位置

| 能力 | 位置 |
|---|---|
| 品类注册表 | `app/catalog/` |
| 平台适配 / 本地样本 | `app/adapters/base.py`、`app/adapters/fixtures/` |
| SKU 同款对齐 | `app/services/matching.py` |
| 到手价引擎 | `app/services/pricing.py` |
| 配置驱动打分 | `app/services/ranking.py` |
| 成分分析 | `app/ingredients/analyzer.py` |
| 健康档案 | `app/profile/` |
| 新鲜度与实时校验 | `app/services/freshness.py` |
| Agent 核心循环(决策→工具→反馈) | `app/agent/graph.py` |
| 决策层(mock 策略 / ark / openai) | `app/agent/llm.py` |
| 工具层(17 个工具,单文件) | `app/agent/toolkit.py` |
| 序列化/报告辅助 | `app/agent/serialize.py` |
| 需求抽取与追问 | `app/agent/extract.py` |

## 新增一个品类

以"机械键盘"为例,在 `app/catalog/definitions.py`(健康类放 `categories_health.py`)注册 `CategorySchema`:
triggers / slots / attributes / dimensions / budget_options,再放一份 fixture。
注册后 Agent、比价、打分、追问、前端全部自动可用。若要做配料分析,
额外声明 `ingredient_attribute`、填充 `ingredient_knowledge` 和 `concern_rules`。

## 合规边界

混合数据层,优先联盟/开放 API(自带带参跳转)。爬虫只做低频补齐遵守 robots.txt、
低并发、短 TTL、不绕过登录/风控、不搬运隐私数据。

## 测试

```bash
cd backend && pytest -q
```

123 项测试覆盖六品类决策链路、工具编排顺序、候选不足自我修复、超预算如实告知、SKU 对齐、权重重排、品类切换、实时价格校验、
以及配料分析、健康档案硬过滤/加权。新品类只需把 key 加入 `ALL_CATEGORIES`
即自动纳入全量参数化验证。