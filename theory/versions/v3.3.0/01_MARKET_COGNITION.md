# 市场认知体系

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE / PUBLIC_POINT_IN_TIME_RESEARCH / NON_EXECUTABLE`

owner：Market Cognition

输入：`InputSnapshot + prior HypothesisRecord`

输出：写入 `HypothesisRecord` 的市场状态、区域、机制候选、竞争路径和下一项区分性观察

## 1. 目标与原则

市场认知不是把更多指标堆进提示词，也不是用新闻解释已经发生的价格。它要在一个明确决策时点回答：

1. 当前实际观察到了什么；
2. 市场处于什么状态，哪些状态仍无法区分；
3. 哪些参与动机和传导机制可以解释现象；
4. 接下来可能沿哪些条件路径发展；
5. 哪项新观察最能区分这些路径；
6. 当前结论能支持什么级别的行为规划，不能支持什么。

市场认知遵守六条底线：

- 事实、测量、推断、假说和行为计划分层；
- 只使用 `available_at <= decision_at` 的信息；
- 缺失保持 UNKNOWN，proxy 不升级为 direct fact；
- 先比较多个机制，再选择 lead；
- 时间尺度、标的、venue 和决策 horizon 必须一致；
- 分析方法是候选工具，不是自动有效的 alpha。

## 2. 数据能力分层

每个数据项必须标为下列一种，而不是笼统写“系统有数据”：

| 状态 | 含义 | 可否进入当前分析 |
|---|---|---|
| `OBSERVED_CURRENT` | 本 cycle 已取得、保存并通过时间/来源检查 | 可以 |
| `OBSERVED_PRIOR` | 历史 cycle 已取得，但可能过期 | 只作 prior，须检查 TTL |
| `CONNECTED_NOT_OBSERVED` | adapter 存在，本 cycle 没有实际响应 | 不可以冒充当前事实 |
| `PUBLICLY_ACQUIRABLE` | 有合法公开来源，但尚未接入/下载 | 只形成 acquisition plan |
| `MANUAL_PUBLIC_ONLY` | 需用户从官方来源导出 | 只进入保存后的未来 cycle |
| `UNOBSERVABLE` | 公开数据不能识别，如真实账户意图 | 永久保持不可观察 |
| `PROHIBITED` | 需要未授权账户、凭据或绕过限制 | 不得获取 |

### 2.1 点时事实合同

每条 datum 至少保留：

```text
source_id, instrument_id, field, value, unit
provider_observed_at, observed_at, available_at, effective_at?
raw_ref, raw_sha256, schema_version
coverage, missingness, revision, dependency_group
admission_status, claim_ceiling
```

`event_time`、`effective_at` 和 `available_at` 不是同一时间。宏观数据的统计期、发布日期、系统实际获得时间和后续修订必须分开；K 线开盘时间不能冒充确认收盘时间；funding 的观察时间、结算时间和下一结算日程不能互换。

### 2.2 来源等级与可获得性正交记录

数据“来自哪里”和“当前是否真的取得”是两个维度，不能互相代替。

| 来源等级 | 定义 | 示例 | 结论上限 |
|---|---|---|---|
| `L0_PRIMARY_RAW` | 原始主体生成、可保存的逐项事实 | 交易所逐笔/盘口、区块链节点、正式公告 | 只对该来源和字段负责 |
| `L1_PRIMARY_AGGREGATED` | 原始主体按公开规则聚合 | 官方 K 线、OI、funding、CFTC、FRED | 受聚合、修订和覆盖限制 |
| `L2_TRANSPARENT_DERIVED` | 输入、公式和时间语义可复算 | OFI、实现波动、公开指标定义 | 只证明该计算结果 |
| `L3_OPAQUE_DERIVED` | 第三方算法、标签或覆盖不完全透明 | 实体标签、黑箱情绪、部分仪表盘 | 只能作 proxy/候选 |
| `L4_COMMUNITY` | 公开个人或群体观点 | Reddit、X、TradingView Idea、视频 | 只用于发现问题和叙事 |

可获得性另记：

```text
CURRENTLY_OBSERVED
PUBLIC_DIRECT
PUBLIC_DERIVED
LICENSED_OR_PAID
UNKNOWN_OR_UNAVAILABLE
PROHIBITED
```

例如，交易所文档列出 liquidation endpoint，只能证明 `PUBLIC_DIRECT`；本 cycle 没有保存响应就不是 `CURRENTLY_OBSERVED`。第三方声称拥有全市场清算数据，若覆盖和方法不透明，只能同时标记 `L3_OPAQUE_DERIVED` 与相应可获得性。

### 2.3 FactorCard：防止同源指标重复计票

每项进入判断的观察形成 `FactorCard`：

```text
factor_id
raw_source_ref
source_level, availability_level
as_of, available_at, retrieved_at
transform, transform_version
decision_horizon
observed_state, recent_delta
dependency_cluster
supports[], contradicts[]
alternative_explanations[]
freshness, ttl
limitations[], claim_ceiling
```

`RSI / MACD / 均线 / 价格斜率 / 突破距离` 都来自价格，默认同属 `PRICE_ACTION` 依赖簇；不能把五个名字当成五份独立证据。`funding / basis / OI` 虽同属杠杆层，也可能拥有不同直接来源；只有在时间、合约和变换明确后才能决定是否独立。

一个依赖簇在同一结论中最多提供：

- 一个主体测量；
- 一个诊断或反证；
- 其余只作展示，不增加支持等级。

### 2.4 数据获取清单与更新频率

| 数据层 | 当前可合法获取的典型字段 | 合理更新时间 | 主要用途 | 典型失败 |
|---|---|---|---|---|
| 交易所价格 | instruments、ticker、closed candles、trades、index/mark | tick 至闭合 K 线 | 核心 baseline、结构、波动 | 时钟错位、未闭合 K 线 |
| 市场深度 | L1/L2 book、spread、update id | streaming/秒 | 短时流动性、冲击 | snapshot 冒充韧性 |
| 衍生品 | OI、funding、basis、期权 IV/skew/OI | 分钟至结算周期 | 杠杆、拥挤、事件风险 | 合约口径混合 |
| 宏观 | release、vintage、政策日历 | 发布/修订触发 | 结构与事件背景 | 用修订值回填历史 |
| 公司/监管 | filing、公告、生效日期 | 事件触发 | 催化剂、规则变化 | 聚合标题代替原文 |
| 新闻/注意力 | 原始报道、GDELT、Trends | 事件/小时至日 | 信息扩散、叙事 | 重复转载、抽样变化 |
| 链上/协议 | block、fees、supply、upgrade、known labels | block 至日 | 供给、网络与慢变量 | 地址当实体、内部账本不可见 |
| venue health | status、维护、指数与风控规则 | 事件触发 | 数据/执行解释 | status green 冒充全链路可用 |

只有核心价格、时间、标的身份和 outcome 价格不可缺。其他数据按 profile 增强；缺失保持 UNKNOWN，不把可选增强变成 baseline 的堵塞条件。

## 3. 市场可观察对象

市场识别对象至少覆盖十五类。表中的最后一列是强制反误读，不是可选免责声明。

| 对象 | 需要识别 | 不能直接推出 |
|---|---|---|
| 标的与合约身份 | 现货/永续/交割/期权、指数/标记、报价、venue | 同名资产的价格和风险相同 |
| 价格结构 | 趋势、区间、突破、回测、摆动、缺口 | 历史形态必然复现 |
| 参与度 | 成交量、成交数、活跃时段、价量关系 | 量增加必然看多或看空 |
| 波动状态 | 实现/隐含波动、期限、偏斜、跳跃、聚集 | 高波动等于下跌 |
| 流动性 | spread、depth、impact、恢复、薄弱区 | 挂单等于真实意愿 |
| 订单流 | aggressor、OFI、CVD、吸收、补单、撤单 | 一次不平衡会持续 |
| 杠杆与拥挤 | OI、funding、basis、清算、期权结构 | OI 增加等于新增多头 |
| 跨市场定价 | 现货—永续—期货—期权、跨 venue | 可见价差一定可套利 |
| 跨资产传导 | 美元、利率、信用、股票、商品、加密 | 相关性等于因果 |
| 宏观状态 | 增长、通胀、就业、政策、财政、美元信用 | 低频数据解释每根 K 线 |
| 事件与催化 | 预定/突发、预期、实际、修订、反应 | 新闻数量等于信息价值 |
| 叙事与注意力 | 搜索、报道广度、讨论速度、立场变化 | 注意力增加等于方向 |
| 链上行为 | 转账、费用、供应、交易所流、桥流 | 地址等于用户，转账等于买卖 |
| 协议/代币基本面 | 解锁、销毁、费用、收入、治理、升级 | 代币拥有协议现金流权利 |
| 场所/网络健康 | API、暂停、拥堵、最终性、预言机、脱锚 | 页面正常等于端到端可用 |

### 3.1 价格、收益与结构

基础对象：mark/index/last、OHLC、log return、gap、range、真实波动、趋势斜率、摆动高低点、结构突破和失败突破。

常用测量：

\[
r_t=\ln(P_t/P_{t-1}),\qquad
RV_{t,h}=\sqrt{\sum_{i=t-h+1}^{t}r_i^2}
\]

```text
TrueRange = max(high-low, |high-prev_close|, |low-prev_close|)
ATR = frozen smoother(TrueRange)
```

价格数据能证明“价格怎样变化”，不能单独证明谁买卖、为何变化或下一步必然延续。

### 3.2 成交、参与和主动流

可用对象包括 volume、trade count、成交额、主动买卖代理、成交速度、平均成交规模、VWAP 偏离和分时成交分布。

候选测量：

```text
VWAP = Σ(price_i × volume_i) / Σ(volume_i)
signed_flow = Σ(aggressor_sign_i × notional_i)
flow_acceleration = current_window_rate / comparable_prior_rate
```

限制：交易所 aggressor 标记是成交撮合角色，不等于开仓/平仓、机构/散户或真实动机；聚合成交会丢失订单身份和队列过程。

### 3.3 订单簿、价差和流动性

可观察对象：bid/ask、spread、各档深度、斜率、深度不平衡、预计冲击、撤挂变化、补单速度和跨 venue 差异。

```text
imbalance_k = (Σbid_size_1..k - Σask_size_1..k)
              / (Σbid_size_1..k + Σask_size_1..k)
```

单次 snapshot 只能描述当时显示深度。它不能证明韧性、吸收或可成交性；这些结论至少需要时间序列中的冲击、消耗和补充。CME 对流动性的说明也显示，在高波动阶段 book depth 可以大幅下降而成交量上升，因此 depth 不能单独代表流动性质量：[CME liquidity discussion](https://www.cmegroup.com/education/articles-and-reports/assessing-liquidity)。

### 3.4 杠杆、拥挤与衍生品

对象：open interest、funding、basis、期限结构、强平观测、期权 IV/skew/term structure、put/call、期权 OI 和交易所风险状态。

OI 与价格的四象限只是候选描述：

| 价格 | OI | 候选解释 | 必留替代解释 |
|---|---|---|---|
| 上升 | 上升 | 新风险参与、趋势扩张 | 套保、跨 venue/basis 仓位 |
| 上升 | 下降 | 空头回补或去杠杆上涨 | 多头止盈、数据覆盖变化 |
| 下降 | 上升 | 新空头或对冲增加 | 基差/套利腿变化 |
| 下降 | 下降 | 多头退出或强制去杠杆 | 组合迁移、到期换月 |

funding 反映特定永续合约机制，不等于全市场多空人数；公开 liquidation feed 通常不是交易所完整强平账本；期权 OI 与 strike 聚集不能在 dealer gamma 方向未知时直接写成“Gamma wall”。

### 3.5 波动、尾部和跳跃

观察 realized volatility、ATR、range expansion、vol-of-vol、gap、极端分位、期权隐含波动和期限/偏度变化。

用途：识别趋势可交易性、均值回归噪声带、stop 距离、仓位缩放、事件风险和路径分岔。限制：高波动不是方向信号；低波动可能继续压缩，也可能处于扩张前夜。

### 3.6 宏观、政策和流动性背景

候选对象：政策利率与路径、通胀、就业、增长、美元、实际利率、信用利差、财政/监管事件、稳定币和法币通道。

官方来源优先：

- [Federal Reserve](https://www.federalreserve.gov/)：声明、会议日程、资产负债表；
- [FRED/ALFRED API](https://fred.stlouisfed.org/docs/api/fred/)：宏观序列、release 与 vintage；
- [BLS Public Data API](https://www.bls.gov/developers/)：CPI、就业等；
- [BEA API](https://apps.bea.gov/api/)：GDP、收入和国家账户；
- [U.S. Treasury Fiscal Data](https://fiscaldata.treasury.gov/api-documentation/)；
- [CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)：周度期货持仓分类及历史数据。

慢频数据必须用当时可得 vintage；最新修订值不能回填旧决策。宏观背景用于 regime 和事件路径，不得把一次公布直接映射成 BTC 15m 方向。

### 3.7 跨资产与相对价值

对象：美元、利率、股指、信用、黄金、能源、主流币、stablecoin、现货/永续/期货基差和跨 venue 价差。

方法包括 rolling beta、相关变化、领先/滞后候选、共同因子、相对强弱和 spread/z-score。相关性只描述共同变化，不证明传导方向；危机时相关结构可能快速改变。

### 3.8 事件、信息、叙事与注意力

信息对象拆为：

```text
InformationTruthHypothesis
  来源、正式程度、内容是否生效、作用对象、时间

AudienceBehaviorHypothesis
  谁可能看到、如何理解、可能采取什么行为、反应时钟
```

来源优先级：官方公告/监管文件/公司或协议发布 > 可靠新闻原文 > 聚合发现 > 社交讨论。GDELT、RSS、搜索和社交平台适合发现线索与注意力变化，不是事实确认器。

每个事件形成可去重的 `EventObject`：

```text
event_id, event_type, actor, asset_scope
scheduled_at, first_published_at, effective_at, retrieved_at
source_original, source_level
expected_value, actual_value, revision
novelty, credibility, duplicate_cluster
market_reaction_windows[]
unresolved_questions[]
```

反应窗口按机制拆开：

- 事件前：预期、拥挤、IV、流动性和提前定价；
- `T0–15m`：跳跃、spread、主动流和场所异常；
- `15m–4h`：接受新价格还是回吐；
- `4h–72h`：跨资产、资金与二次传播；
- 更长：是否改变结构状态、供给或政策反应函数。

同一事件的转载、摘要和评论共享 `duplicate_cluster`，不能累加为多份证据。正式事实和受众行为假说分别更新。

可用入口：

- [SEC EDGAR](https://www.sec.gov/edgar/search-and-access)：公司披露；
- 各央行、监管机构、交易所 status/公告页；
- [GDELT data](https://www.gdeltproject.org/data.html)：公开新闻发现和元数据；
- [Google Trends](https://trends.google.com/trends/)：人工公开导出的相对搜索兴趣；
- Reddit/X/论坛公开内容：叙事与受众候选，绝不代表真实持仓或群体全貌。

### 3.9 链上与网络状态

对象：区块、费用、mempool、活跃地址代理、交易所已知地址流、稳定币发行、矿工/验证者、协议升级和网络异常。

优先级：自有完整节点/官方链数据 > 可保存的公共 API/数据集 > 区块浏览器展示。地址标签是提供方推断，不是实体身份真值；链上转移不自动等于买卖；交易所内部账本不可见。

### 3.10 venue 与系统状态

交易所维护、指数成分、价格保护、保险基金、ADL、限频、延迟和数据间断既影响风险，也影响市场解释。venue 局部异常必须与全市场价格发现分开。

当前公开 venue 的主参考为 [OKX API](https://www.okx.com/docs-v5/en/)；公开接口覆盖 instruments、tickers、candles、trades、order book、funding 和 OI。接口存在只表示理论可接入，只有本 cycle 保存的 raw response 才是当前已获取。

## 4. 成熟分析方法库

每种方法以 `AnalysisMethodCard` 登记：`method_id / question / inputs / transform / output / regime / horizon / alternatives / invalidators / data_snooping_risk`。方法只产生测量或假说，不直接产生订单。

### 4.1 趋势与时间序列动量

方法：高低点结构、moving-average slope/cross、Donchian/channel breakout、不同 horizon return、趋势强度和回撤深度。

适合：方向持续、价格发现、流动性追随。重点不是某条均线，而是方向、持续性、波动调整后强度、参与确认和失败条件。

失效：区间/震荡、事件反转、拥挤和高换手。时间序列动量有成熟研究基础，但不同资产和周期的参数、成本与崩溃风险必须重新验证：[Moskowitz, Ooi & Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003)、[Daniel & Moskowitz](https://doi.org/10.1016/j.jfineco.2015.12.002)。

### 4.2 均值回归与超调

方法：rolling mean/median、z-score、VWAP/价值区偏离、布林带类标准化偏离、短期反转、极端后衰竭。

```text
z_t = (x_t - rolling_center) / rolling_scale
```

适合：稳定区间、临时流动性冲击、无结构变化的超调。失效：新信息永久重定价、强趋势、波动 regime 变化、中心本身移动。进入前必须区分“偏离旧均值”和“均值已失效”。

### 4.3 波动与 regime 识别

方法：realized-vol 分位、ATR/range、趋势持续性、反转频率、change-point、状态转换、相关结构变化。

V3.3.0 使用可解释 reducer，不让 Agent 用一句话决定 regime：

| 状态 | 必需观察 | 典型反证 |
|---|---|---|
| `TREND_UP/DOWN` | 方向结构、持续性、回撤可控 | 连续结构失败、反向扩张 |
| `RANGE` | 可重放边界、边界反应、中心回归 | 接受区外持续、边界迁移 |
| `CHOPPY` | 低延续、高反转、成本压力 | 持续性显著恢复 |
| `VOL_EXPANSION` | range/RV 扩张 | 扩张快速衰减 |
| `VOL_COMPRESSION` | range/RV 收缩 | 突发扩张 |
| `TRANSITION` | 旧状态失效、新状态未确认 | 新状态获得持续证据 |
| `UNKNOWN` | 输入不足或冲突 | 新数据形成可区分状态 |

状态转换模型有成熟统计基础，但实际离散状态和阈值仍是待检验建模选择：[Hamilton regime switching](https://doi.org/10.2307/1912559)。

### 4.4 支撑、阻力与反身性流动区

区域由摆动点、成交密集、VWAP/价值区、round number、历史反应、波动宽度和流动性证据构造。禁止用事后结果把单点扩成刚好命中的区间。

每个 zone 至少给出：边界、构造方法、创建/可得/过期时间、触碰与反应、替代区域、拒绝/吸收突破/假突破路径。反复触碰可能强化可见性，也可能消耗流动性；不得固定解释。

关口附近 stop 聚集与突破加速有实证研究，但不是每个整数位都有效：[Osler 2003](https://doi.org/10.1111/1540-6261.00588)。

### 4.5 Auction Market、Market Profile、Volume Profile 与 VWAP

这些方法把价格看作寻找接受区的拍卖过程：关注价值区、成交密集/稀疏区、POC、开盘相对价值区位置、接受与拒绝。Market Profile 的通用定义可参考 [CME glossary](https://www.cmegroup.com/education/glossary)。

用途：定位市场接受区、潜在快速穿越区、均值回归或突破后的接受。限制：profile 参数、session 切分和数据源会改变结果；它描述分布，不自动证明未来方向。

### 4.6 订单流与微观结构

方法：主动成交不平衡、order-flow imbalance、spread/depth/impact、queue/replenishment、成交速度、价格对流的响应、跨 venue lead-lag。

核心问题不是“买单多不多”，而是：

```text
相同主动流是否推动了更大/更小的价格变化？
被消耗的流动性是否补回？
价格移动来自真实交易还是显示深度撤走？
venue 局部变化是否跨市场确认？
```

只有 snapshot 时只能生成 `OBSERVED_SNAPSHOT_PROXY`；严格韧性需要序列。当前 Baseline 不因缺少微观结构停止，但不得输出吸收、韧性或 queue 结论。

### 4.7 衍生品与拥挤分析

联合观察 price、OI、funding、basis、liquidation 和 options。分析顺序：先确认时间/合约口径，再描述变化，再提出拥挤/套保/套利等竞争解释，最后寻找能区分的下一观察。

典型失败：把高 funding 直接等同于即将下跌；把 OI 上升直接等同于新增多头；把清算金额当成完整市场损失；把期权 strike OI 当成 dealer 净 gamma。

### 4.8 宏观与跨资产 regime

方法：事件日历、surprise 相对预期、release vintage、rolling beta、相关变化、美元/实际利率/信用/股指风险偏好组合、流动性传导。

适合 4H–周级战略背景和事件风险。对 15m 决策，宏观通常是路径修饰器或风险条件；只有时间、影响对象和价格/流动性反应都匹配时，才升级为当前机制证据。

### 4.9 事件研究与叙事反应

事件卡必须包含：来源、正式程度、首次可得时间、预期差、受影响对象、传播对象、预期时钟、已观察反应、替代解释和失效条件。

事件前、事件瞬间和事件后分别分析：

- 事件前：定位预期、拥挤和可承受风险；
- 事件瞬间：观察价格、流、价差、跳跃和 venue 状态；
- 事件后：区分一次性冲击、接受新价格、反转和二次传播。

新闻/注意力与市场反应有研究依据，但只能形成候选机制：[Tetlock](https://doi.org/10.1111/j.1540-6261.2007.01232.x)、[Da, Engelberg & Gao](https://doi.org/10.1111/j.1540-6261.2011.01679.x)。

### 4.10 经典技术指标

RSI、MACD、moving averages、stochastic、Bollinger/ATR 等只做测量压缩：

- RSI：衰竭、背离、failure swing、趋势中轴重置；
- MACD/均线：方向与加速度候选；
- ATR/带宽：噪声、波动和 stop 参考；
- volume/OBV 类：参与候选。

任何单一指标不得直接决定方向或仓位。技术形态可被算法化，但存在数据窥探和样本依赖：[Lo, Mamaysky & Wang](https://doi.org/10.1111/0022-1082.00265)、[Sullivan, Timmermann & White](https://doi.org/10.1111/0022-1082.00163)。

### 4.11 横截面、相对强弱和市场广度

在多标的 profile 中比较收益、波动调整动量、相关 cluster、资金轮动和 breadth。它适合标的选择和机会成本，但当前单标的 Baseline 不具备横截面结论；不能用未来幸存标的池回测旧决策。

### 4.12 On-chain 与供需结构

方法候选：费用/mempool、活跃与转移、已知实体流、供应分布、稳定币、矿工/验证者。必须保留地址标签不确定性、链上与交易所内部账本差异、批处理和自转账替代解释。慢频链上状态不直接触发微观入场。

### 4.13 宏观四轴与反应函数

宏观不是“数据高于预期就上涨/下跌”的字典。按四轴组织：

```text
growth       扩张 / 放缓 / 收缩 / UNKNOWN
inflation    上行 / 下行 / 粘性 / UNKNOWN
policy       收紧 / 中性 / 放松 / 反应函数变化
liquidity    改善 / 恶化 / 分化 / UNKNOWN
```

分析顺序：

1. 比较实际值、此前值、修订值和当时可获得的预期；
2. 区分数据 surprise 与价格实际反应；
3. 判断市场是否已提前定价；
4. 判断政策反应函数是否变化；
5. 画出利率、美元、信用、风险偏好、杠杆到目标资产的传导；
6. 给出传导中断或反向的条件。

宏观公告可造成跳跃，但反应依赖公告类型、经济周期和当时持仓，不能冻结固定利好/利空映射。[宏观公告与资产价格](https://www.aeaweb.org/articles?id=10.1257/000282803321455151)、[美联储跨市场价格发现研究](https://www.federalreserve.gov/econres/ifdp/real-time-price-discovery-in-global-stock-bond-and-foreign-exchange-markets.htm)

### 4.14 相对价值、配对与协整

相对价值不等于“两个资产相关性高”。候选流程：

```text
economic/contract link
→ synchronized point-in-time sample
→ stable transform and spread
→ stationarity/cointegration diagnostics
→ half-life and transaction-cost bound
→ structural-break monitor
→ venue/borrow/funding/transfer constraints
```

适用条件是存在可解释共同锚且 spread 仍稳定。协议规则、代币经济、交割合约、流动性或市场制度改变时，旧关系可以永久破裂。[Gatev、Goetzmann、Rouwenhorst：Pairs Trading](https://academic.oup.com/rfs/article-abstract/19/3/797/1646694)

### 4.15 订单簿序列与 OFI

严格本地订单簿必须按照交易所序列号连接 snapshot 与增量；丢序时重新初始化。不能把不连续 book 用于 queue、撤单或恢复结论。[Binance 本地订单簿规则](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly)

OFI 同时考虑最优报价变化、挂单、撤单和成交引起的队列变化；其候选价值在于短时价格冲击与深度的关系，不是一个永久方向分数。[Cont、Kukanov、Stoikov](https://arxiv.org/abs/1011.6402)

微观分析至少比较：

```text
displayed pressure
executed pressure
price response per unit flow
depth consumed
depth replenished
cross-venue confirmation
recovery time
```

只有 REST snapshot 时这些字段多数必须为 UNKNOWN。

### 4.16 方法路由与失效条件

| 当前状态 | 主方法 | 辅助诊断 | 不适合的直接外推 |
|---|---|---|---|
| 方向持续、波动正常/扩张 | 趋势、突破、回撤 | 参与、OFI、OI/basis | 单根突破等于长期趋势 |
| 平衡、波动收缩 | profile、均值回归 | spread、价值区、半衰期 | 旧中心永久有效 |
| 结构转换 | change-point、regime reducer | 跨周期扩散、事件 | 模型标签具有因果意义 |
| 事件窗口 | surprise/response | IV、流动性、跨资产 | 新闻文字直接决定方向 |
| 去杠杆压力 | leverage/liquidity spiral | 清算、depth、basis | 不完整清算 feed 是全量 |
| 超短执行观察 | OFI、microprice | spread、impact、恢复 | 秒级失衡延续数周 |
| 跨市场偏离 | relative value/cointegration | basis、转移成本、健康 | 价差必然可执行 |

每个启用模型注册：

```text
model_id, recognized_object
required_inputs[], optional_inputs[]
valid_horizons[], preconditions[]
output_schema, update_cadence
known_failure_modes[], invalidation_rule
dependency_cluster
```

输入不满足时模型标为 `UNAVAILABLE`，不是用 proxy 默默补齐。

## 5. 时间尺度分类

| Frame | 典型 horizon | 主要问题 | 方法重点 | 更新条件 |
|---|---|---|---|---|
| `STRUCTURAL` | 月至年 | 制度、采用、供给、长期流动性 | 基本面、政策、链上结构 | 重大正式事件或定期复核 |
| `STRATEGIC` | 日至周 | 主 regime、主要方向、尾部 | 1D/4H、跨资产、宏观、波动 | closed bar、release、regime break |
| `TACTICAL` | 小时至日 | 当前路径、区域、拥挤与机会 | 4H/1H/15m、flow、OI/funding | 新 closed bar 或重要事件 |
| `TRIGGER` | 分钟至小时 | 何时行动、失效和保护 | 15m/5m、结构、成交、价差 | 预注册触发 |
| `MICRO` | 毫秒至分钟 | queue、冲击、执行质量 | tick/L2/latency | 仅有 streaming 与资格时 |

高周期提供背景和风险不对称，不是低周期动作的绝对禁令。低周期触发不能单独推翻高周期战略，但可以创建短 horizon 的反向 tactical 假说。不同 frame 的数据、假说、expiry 和 owner 必须分开。

每次决策默认只启用三个 frame：

```text
CONTEXT_FRAME    定义背景和主要风险
DECISION_FRAME   形成当前市场判断与假说
EXECUTION_FRAME  观察短时接受、拒绝与流动性
```

禁止为了寻找一致结论无限增加周期。短期反转、中期动量和长期过度反应可以同时存在，因此多周期不是把同一图形机械放大，而是识别不同参与者、信息到达速度和信号半衰期。[短期反转](https://www.nber.org/papers/w2533)、[中期动量](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1993.tb04702.x)、[长期过度反应](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1985.tb05004.x)

| 行为目的 | 默认观察尺度 | 主体方法 | 禁止替代 |
|---|---|---|---|
| 结构配置 | 月至年；1M/1W | 宏观周期、政策、供应、基本面 | 分钟订单流决定长期价值 |
| 战略方向 | 数周至数月；1W/1D | 趋势、相对动量、跨资产、机构头寸 | 单次新闻跳跃替代结构状态 |
| 波段判断 | 1 日至数周；1D/4H/1H | regime、趋势/回归、事件、OI/funding | 月度数据决定精确入场 |
| 战术判断 | 数小时至 2 日；4H/1H/15m | profile、结构、事件反应、杠杆 | 无视高周期风险背景 |
| 执行观察 | 秒至 2 小时；tick/1m/5m | spread、depth、OFI、microprice | 微观失衡外推数周 |
| 防守与保护 | 事件驱动 | 跳跃、流动性、清算、venue/network | 等固定 K 线结束才识别故障 |

### 5.1 不同时间尺度的方法差异

- 结构/战略：强调 release vintage、制度传导、跨资产、趋势和状态转换；少看单笔噪声。
- 战术：强调区域、路径、OI/funding/flow 的变化和事件反应；比较趋势延续、正常回撤、衰竭和失败。
- 触发：只处理入场/加减仓所需的最新证据、结构失效和流动性；不得重新生成整套宏观故事。
- 微观：强调 queue、spread、impact 和 fill 风险；不具备相应数据时保持不可用。

## 6. 按行为动机组织分析

系统分析可观察行为，不宣称识别真实主体。每个动机至少保留一个替代动机。

| 动机候选 | 分析重点 | 可观察签名候选 | 常见误判 |
|---|---|---|---|
| 方向投机 | 趋势、加速、持仓扩张 | price+OI+flow 同向 | 套保或套利腿 |
| 套保 | 相关资产、basis、事件 | 现货/衍生品反向变化 | 当成单向看空/看多 |
| 做市库存管理 | spread、补单、短期反转 | 冲击后补充、库存偏斜 | 当成“主力护盘” |
| 基差/跨 venue 套利 | basis、funding、价差 | 多腿同步、价差收敛 | 把单腿 OI 当方向 |
| 强制去杠杆 | liquidation、OI、gap、流动性 | 快速价格/OI 下降、冲击 | 把不完整 feed 当全量 |
| 再平衡/被动流 | 时间、权重、收盘窗口 | 规律性成交、跨资产同步 | 事后故事化 |
| 获利了结 | 盈利路径、flow、结构 | 上涨中 OI/动量/承接变化 | 自动等同趋势反转 |
| 恐慌/追涨 | 注意力、速度、价差、波动 | flow 加速与流动性恶化 | 声称知道群体心理 |
| 信息重定价 | 正式事件与 surprise | 多 venue 快速新价格接受 | 把谣言当事实 |

## 7. 分析流程与路线规划

### 7.1 完整冷启动路线

1. **冻结任务**：instrument、venue、decision time、horizons、profile、权限。
2. **准入数据**：保存 raw；核对时间、单位、closed bar、revision 和 missingness。
3. **声明覆盖**：列出 `OBSERVED_CURRENT / UNKNOWN / UNOBSERVABLE`，禁止“有节点=有数据”。
4. **结构背景**：Structural/Strategic frame，确认大级别趋势、波动和事件。
5. **战术状态**：Tactical/Trigger frame，构造 regime、zones、price/flow/leverage state。
6. **行为机制**：至少生成主机制、竞争机制和“不产生方向影响”机制。
7. **方法三角验证**：价格结构、参与/流、杠杆/流动性、事件/跨资产中选择可用且依赖不同的视角；缺失不伪造。
8. **生成假说**：状态、归因、预测路径、行为 thesis；绑定反证和 expiry。
9. **找区分性观察**：说明下一数据为何能在竞争假说间产生不同更新。
10. **移交仓位模块**：只传递可行动假说、几何、关键 UNKNOWN 和机会成本，不传重复全图。
11. **封存与排程**：写五工件引用、下一 review 和 outcome horizon。

### 7.2 1–2 分钟 delta 路线目标

Delta 不重写全市场：

```text
load prior frames and hypotheses
→ admit only new/expired/invalidated data
→ recompute affected measures and zones
→ update affected hypotheses and paths
→ compare prior plan with new feasible actions
→ seal delta and next observation
```

必须重新检查：当前时间、数据 freshness、hard falsifier、stop/target/expiry、venue 状态和新风险候选。不得重复：未变化的历史叙事、全部 raw 列表、旧资格、全仓代码闭包和事故日志。

### 7.3 Event fast path

事件触发只读取：正式事件卡、最新价格/流动性、受影响假说、当前计划和风险边界。它可以触发 `REDUCE/CLOSE/PROTECT/REANALYZE`，但新增风险仍须生成当前 PIT `InputSnapshot` 和新 `BehaviorPlan`。

### 7.4 分析目的与路线选择

| 任务 | 必须先读 | 重点更新 | 交付 | 何时停止扩读 |
|---|---|---|---|---|
| 新标的建档 | 合约/venue 身份、可用历史、供给和主要事件 | 结构 frame、数据能力矩阵 | identity card、可用模型、关键 UNKNOWN | 能支持首个 price baseline |
| 每日战略复核 | 前次 Strategic state、日历、1D/4H、跨资产 | regime、波动、主要传导 | 结构变化与当天风险背景 | 未变化慢层已确认 |
| 日内战术判断 | 已封存战略背景、1H/15m、事件与杠杆 | zones、flow、路径和 falsifier | lead/runner-up/OTHER | 能区分合法动作 |
| 触发复核 | 当前 plan、最新 closed bar、spread/venue | 触发、接受/拒绝、保护条件 | PositionTransition 候选 | 不重建宏观故事 |
| 突发事件 | 原始事件、受影响对象、最新价格/流动性 | surprise、传播和反应窗口 | 保护/重分析路径 | 已确认事实与受众假说分开 |
| 异常诊断 | raw、时钟、venue、跨场所价格 | 数据故障 vs 市场跳跃 | typed anomaly 与 claim ceiling | 已能决定数据是否准入 |

选择路线先问“这个判断会改变什么”，再选择数据和方法；不得从手边恰好有的指标反推任务。

### 7.5 观察 horizon 与历史 lookback 分开

`decision_horizon` 是未来要判断的时间，`lookback` 是估计结构或波动所用的历史；两者不能用一个周期标签代替。

| Frame | lookback 设计原则 | 需要保留的变化检查 |
|---|---|---|
| STRUCTURAL | 尽量覆盖多个制度/供给/流动性阶段；数据不足则缩窄主张 | 定义、市场制度和幸存样本变化 |
| STRATEGIC | 覆盖当前趋势与至少一个可比较状态；release 使用 vintage | 状态转换、相关结构和参数漂移 |
| TACTICAL | 足以稳定计算当前 zone/vol，又不能把旧 regime 混入 | 窗口敏感性、事件前后分段 |
| TRIGGER | 只覆盖当前结构和可执行时钟 | closed bar、延迟和短时噪声 |
| MICRO | 必须是连续、有序的事件序列 | 丢序、采样、venue 延迟和恢复 |

具体 bar 数、日数和半衰期属于 `AnalysisMethodCard` 参数，必须随 horizon、venue、交易时段和数据密度版本化。不得为得到想要的结论临时延长或缩短窗口；至少报告相邻合理窗口下结论是否改变。

### 7.6 冲突分析路线

当不同层给出冲突结果时，不做多数表决：

1. 先检查时间、标的、venue 和 dependency 是否一致；
2. 区分“不同 horizon 同时成立”和“同 horizon 真正矛盾”；
3. 找出哪个模型的前置条件已失效；
4. 将冲突写入 competing hypotheses；
5. 选择一项能区分的下一观察；
6. 如果冲突仍在，缩窄 claim 或输出 `UNRESOLVED`，不使用伪精确平均分。

## 8. 核心市场模型

### 8.1 六层传导模型

```text
规则与宏观
→ 融资、流动性与中介约束
→ 标的供给/治理/基本面
→ 跨资产和 venue 网络
→ 微观结构、杠杆和波动
→ 注意力、叙事和群体行为
→ 价格路径与反馈
```

传导链可以中断、反向或被价格提前反映。每层输出：事实、推断、替代解释、作用时钟、传导方向、下一验证。

### 8.2 Regime reducer

Regime 由四组 feature 共同形成：方向持续、反转/均值回归、波动状态、流动性/成本。Baseline 只有价格族时允许输出 `PRICE_ONLY_TREND/RANGE/TRANSITION/UNKNOWN`，并标记 `SINGLE_FAMILY`；不再因缺少第二 observable family 而让 cycle 无法完成。只有 Tactical profile 才升级为含 flow/leverage/liquidity 的综合 regime。

### 8.3 证据依赖图

图用于去重与追踪，不用于制造节点数量：

```text
Information/Raw Datum → Measure → MarketState/Zone
→ Hypothesis → Path → BehaviorPlan → Outcome/Review
```

同一价格序列产生的突破、均线、动量和 RSI 必须共享 `PRICE_ACTION` dependency group；语言描述变多不增加独立支持。

### 8.4 反身性路径模型

价格变化会改变注意力、止损、杠杆、做市库存和流动性，进而反馈价格。每条路径说明：初始状态、触发、行为机制、可观察序列、加速/衰减条件、替代路径、失效和期限。

### 8.5 动态多模型组合

系统不选一个永久冠军模型。每轮按 regime 和数据 profile 选择方法组合：

| Regime | 主方法 | 辅助方法 | 主要风险 |
|---|---|---|---|
| 趋势 | 结构/动量/回撤 | flow、OI、跨资产 | 拥挤反转、晚入 |
| 区间 | auction/VWAP/均值回归 | 边界 flow、波动 | 假突破、区间迁移 |
| 波动扩张 | break/path、流动性 | event、options | 滑点、双向扫损 |
| 混沌 | 反转频率/成本 | 观望或条件触发 | 过度交易 |
| 事件 | surprise/反应/接受 | flow、跨 venue | 先验错误、延迟 |
| UNKNOWN | 信息价值与小额可撤销 probe | 简单 price baseline | 伪造确信 |

## 9. 工具与网站使用规则

| 工具/来源 | 用途 | 权威上限 |
|---|---|---|
| 交易所官方 REST/WS/历史下载 | 原始市场数据 | 对该 venue 的公开字段负责 |
| FRED/ALFRED、BLS、BEA、CFTC、央行/监管 | 宏观与制度事实 | 注意 release/vintage/revision |
| TradingView/专业图表 | 可视化、手工复核、候选发现 | 图表展示不是 raw authority |
| Jupyter/Python/SQL/Spreadsheet | 复算、对齐、可视化、敏感性 | 代码输出必须回指输入与版本 |
| GDELT/RSS/搜索 | 信息发现 | 不直接确认事实或影响 |
| Google Trends | 相对注意力 | 非绝对人数、会修订/抽样 |
| Reddit/X/社区 | 叙事、操作痛点和候选方法 | 热度不是有效性或代表性 |
| 区块浏览器/第三方链上平台 | 网络与标签 proxy | 不等于实体身份或交易意图 |

### 9.1 官方与原始来源导航

| 领域 | 推荐入口 | 可用内容 | 注意事项 |
|---|---|---|---|
| 美国宏观 vintage | [FRED/ALFRED](https://fred.stlouisfed.org/docs/api/fred/overview.html) | 序列、release、vintage | 保存当时可见版本 |
| 就业与通胀 | [BLS releases](https://www.bls.gov/bls/newsrels.htm) | CPI、就业、工资 | 统计期与发布日期分开 |
| GDP/收入/支出 | [BEA schedule](https://www.bea.gov/news/schedule) | 发布日历和国家账户 | 后续修订不可回填 |
| 货币政策 | [FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) | 声明、纪要、日程 | 区分公布与生效 |
| 全球美元信用 | [BIS Global Liquidity](https://www.bis.org/statistics/dataportal/gli.htm) | 跨境信贷与流动性 | 低频背景，不作分钟触发 |
| 机构期货头寸 | [CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | 周度分类头寸 | 分类不等于实际动机 |
| 期货/期权 OI | [CME Daily Bulletin](https://www.cmegroup.com/market-data/daily-bulletin.html) | 成交、OI、合约信息 | 初值与最终值可不同 |
| 公司披露 | [SEC EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | submissions、XBRL | filing 原文优先 |
| 加密现货/衍生品 | [OKX API](https://www.okx.com/docs-v5/en/)、[Binance Market Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api) | 价格、book、funding、OI | venue 与合约口径 |
| 公开实时盘口 | [Coinbase WebSocket](https://docs.cdp.coinbase.com/exchange/websocket-feed/overview) | level2、trades | 按序维护本地状态 |
| 加密期权 | [Deribit public API](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency) | IV、OI、book summary | 期权结构不等于 dealer 方向 |
| 网络/协议 | [Bitcoin Core RPC](https://developer.bitcoin.org/reference/rpc/)、[Ethereum EIPs](https://github.com/ethereum/EIPs) | 原始链事实、升级提案 | 提案与生效分开 |

### 9.2 透明派生与人工工具

- [Coin Metrics](https://docs.coinmetrics.io/)：指标定义、时间语义和透明派生；
- [Glassnode Docs](https://docs.glassnode.com/)：实体调整指标，但专有实体聚类必须标为启发式；
- [GDELT](https://www.gdeltproject.org/data.html)：新闻发现和多语言覆盖，不是事件真值；
- [Google Trends 数据说明](https://newsinitiative.withgoogle.com/resources/trainings/google-trends-understanding-the-data/)：抽样且归一化到 0–100，不是绝对搜索量；
- [TradingView Volume Profile 说明](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/)：图表与 profile 复核；其 up/down volume 语义不能冒充真实主动买卖；
- Python `pandas/polars/numpy/statsmodels/arch/scipy`、SQL、Jupyter、Spreadsheet：复算、对齐、敏感性和图形；输出必须回指输入、公式与版本。

### 9.3 社区方案的采用门

高互动方案只进入 `COMMUNITY_HEURISTIC_NOT_EVIDENCE`：

1. 提取它指出的实际问题；
2. 查找可复算定义或原始研究；
3. 写适用状态、失效条件和数据要求；
4. 去掉作者的固定参数与收益承诺；
5. 只作为 method/policy candidate；
6. 未有前瞻证据前不升级为默认。

例如，[订单簿失衡讨论](https://www.reddit.com/r/algotrading/comments/1pgsphr/algo_only_based_on_orderbook_imbalance_could_it/)提示需要把 OBI、OFI 与 regime 结合；[regime 讨论](https://www.reddit.com/r/algotrading/comments/11fyy87/what_market_regime_detection_methods_have_you/)提示复杂分类器容易过拟合。可采纳的是问题与反例，不是帖内数值、票数或盈利结论。

社区常见且值得保留为候选的经验包括：stop-distance sizing、portfolio heat、相关暴露、波动缩放、不要用单一指标、先定义失效再决定仓位。它们必须进入 future-only policy arm 或 sensitivity comparison；不得因高赞直接冻结参数。一个高互动 r/algotrading 讨论也强调风险、价格行为和趋势过程的重要性，但这只代表社区经验：[community discussion](https://www.reddit.com/r/algotrading/comments/y4mt3l/)。

## 10. 标准输出

每轮市场认知输出：

```text
decision_scope
data_profile_and_coverage
structural/strategic/tactical/trigger frames
market_regime + feature refs + alternatives
zones + construction + alternatives
observed changes
lead mechanism / competing mechanism / no-effect mechanism
state / attribution / forecast-path hypotheses
supporting and opposing dependency groups
hard falsifiers / soft contradictions / expiry
next discriminating observations
action-relevant geometry and critical UNKNOWN
claim ceilings and non-claims
```

如果只有核心四项价格数据，输出仍须完成，但必须清楚写出：没有观察到 order flow、OI/funding、严格流动性韧性、宏观 surprise、身份或叙事采用。

## 11. 失效与自检

以下现象说明市场认知需要修正，而不是继续加治理：

- 多数结果持续落入 OTHER，现有机制库解释力不足；
- 同一输入产生大幅不稳定的 regime/zone；
- lead 经常由单一依赖组的多个指标重复制造；
- 分析完成时数据已过期；
- 15m 触发用月度数据解释，或周级判断被一次 tick 推翻；
- Agent 能讲故事但不能给出反证、期限和下一观察；
- 可选数据缺失导致 cycle 无法形成最小判断；
- 方法数量增加但对基线没有可测增量。

遇到这些问题时，优先修改 method card、profile、阈值或数据 owner；不得在没有前瞻结果时新增不可证伪的故事类型。

## 12. 主要依据与使用边界

- [Lo, Mamaysky & Wang (2000), technical pattern recognition](https://doi.org/10.1111/0022-1082.00265)
- [Hamilton (1989), regime switching](https://doi.org/10.2307/1912559)
- [Moskowitz, Ooi & Pedersen (2012), time-series momentum](https://doi.org/10.1016/j.jfineco.2011.11.003)
- [Daniel & Moskowitz (2016), momentum crashes](https://doi.org/10.1016/j.jfineco.2015.12.002)
- [Osler (2003), stop-order clustering](https://doi.org/10.1111/1540-6261.00588)
- [Tetlock (2007), media and investor behavior](https://doi.org/10.1111/j.1540-6261.2007.01232.x)
- [Da, Engelberg & Gao (2011), search attention](https://doi.org/10.1111/j.1540-6261.2011.01679.x)
- [Sullivan, Timmermann & White (1999), data snooping](https://doi.org/10.1111/0022-1082.00163)
- [White (2000), reality check for data snooping](https://doi.org/10.1111/1468-0262.00152)

这些资料支持方法候选、边界和验证需求，不证明任何具体组合能预测 BTC、提高收益或适合当前 15m runtime。
