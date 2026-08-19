# RSI-MTF-DRL-PM Theory Challenger v0.3.0

> 状态：`E0 / LITERATURE_SYNTHESIS / THEORY_CHALLENGER_ONLY`
>
> 日期：2026-07-23
>
> 允许声明：形成了可检验、可自动化、可反证的理论候选与验证路线。
>
> 禁止声明：市场有效、预测有效、成本后盈利、paper 可用、实盘可用或可自动晋级。

## 0. 文档身份与隔离边界

本文是外部权威研究与现有理论之间的独立 challenger，不是
`RSI-MTF-DRL-PM v0.2.2` 的修订版，也不改变当前任何交易权限。

以下现有权威 bytes 在本文研究期间保持不变：

| 对象 | SHA-256 |
|---|---|
| `RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md` | `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6` |
| `RSI_MTF_DRL_PM_AUTHORITY_BUNDLE_SPEC_v0_2_2.md` | `9b2446de9e0549579d52bc8ce2bc3bd124885203a52855f0dbf0f1324f9f1295` |
| `config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json` | `631f8187e9eb81465718156736045c3ca5cc7ec5e33bbba7b063354cefeb792c` |
| `config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json` | `26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc` |

活动 G1 计划与 Source Registry 同样不可修改：

| 对象 | SHA-256 |
|---|---|
| `forward_capture_plan.g1.v1.json` | `189317fdff53d9f0ca64747d48690a283a3328b04df539f53307eb1370c3cb6d` |
| `source_registry.v3.json` | `b3848092824dc65e9fea6ac524811453b8abf4783b865d8c057089cb5603453f` |

本文中的“整合”只表示：

1. 外部研究被转译成明确机制；
2. 机制被转译成 point-in-time 可观测量；
3. 可观测量被转译成有限候选规则；
4. 每条规则同时拥有反证条件和数据要求；
5. 只有后续本项目 DEVELOPMENT、CALIBRATION 和一次性 HOLDOUT 依次通过，
   才能在新的理论版本中晋级。

## 1. 理论准入纪律

### 1.1 五段证据链

任何网络观点、论文结论或交易经验必须通过以下链路：

```text
权威来源
  → 可解释的市场机制
  → 决策时可获得的观测量
  → 唯一、确定、可重放的计算规则
  → 可被历史数据否定的结果预测
```

缺失任一环节时，结论只能留在来源笔记中，不能进入策略候选。

### 1.2 来源等级

| 等级 | 来源 | 可用于什么 | 不可用于什么 |
|---|---|---|---|
| `S0` | 交易所官方 schema、监管规则、正式接口文档 | 定义字段、时序、订单和市场机制事实 | 证明 alpha 或盈利 |
| `S1` | 同行评审的原始理论或实证论文 | 提供机制与外部历史证据 | 直接外推到 BTCUSDT |
| `S2` | 有完整方法和数据说明的工作论文、预印本 | 产生 challenger | 单独支持理论晋级 |
| `S3` | 教材、机构研究、综述 | 查找来源和理解背景 | 作为唯一证据 |
| `REJECTED` | 博客、论坛、营销材料、无法复核回测 | 不进入理论 | 任何策略结论 |

### 1.3 外部证据不是本项目验证

即使一个机制在股票、外汇、商品或多个期货市场上有显著结果，也只说明：

- 该机制值得在 BTCUSDT 上提出一个有限假设；
- 不能说明该机制在 15m/4H、永续合约、Binance、当前费率和延迟下成立；
- 不能说明它对现有 RSI、EntryZone、止盈止损或风险规则有增量；
- 不能说明它在样本外、成本后或真实执行中成立。

## 2. 统一市场决策链

扩充后的系统逻辑保持简单的九段结构：

```text
数据完整性
  → 高周期市场状态
  → RSI 观察触发
  → 趋势/结构方向解释
  → 微观结构确认或否决
  → EntryZone 与执行可行性
  → 风险预算与仓位
  → 动态 TP/SL/结构退出
  → 证据化结果与版本治理
```

### 2.1 数据完整性先于信号

系统在以下任一条件出现时只能输出 `UNKNOWN` 或 `ABSTAIN`：

- K 线尚未闭合；
- 时间戳、available-at 或 source generation 不可证明；
- depth update sequence 有缺口；
- snapshot 与 diff-depth 不能构成连续本地订单簿；
- book、trade、mark、OI 或账户快照超过冻结陈旧阈值；
- 同一字段存在相互冲突的合法来源；
- 执行成本或 venue 规则不可确定。

强信号不能覆盖数据缺陷。

### 2.2 RSI 是事件触发器，不是方向真理

RSI 超买或超卖只回答“是否需要评估”，不直接回答：

- 应当反转还是顺势；
- 应当立即成交还是等待；
- 当前结构是否允许入场；
- 止损能否落在风险预算内；
- 预期收益是否覆盖成本；
- 当前流动性是否允许执行。

因此保留：

```text
RSI event → evaluate
```

并明确拒绝：

```text
RSI oversold → unconditional LONG
RSI overbought → unconditional SHORT
```

## 3. K 线与多周期分析

### 3.1 K 线的理论地位

OHLCV 是一段时间内事件流的压缩结果，不保留完整的成交、盘口和先后路径。
它适合描述：

- 区间；
- 波动；
- 收盘相对位置；
- 局部极值；
- 多周期趋势；
- 结构区间。

它不适合单独证明：

- bar 内 TP 和 SL 谁先到；
- 限价单是否真实成交；
- 某个影线必然代表做市商吸筹或出货；
- 某个命名形态具有稳定预测能力。

[Lo、Mamaysky、Wang（2000）](https://www.mit.edu/people/wangj/pap/LoMamayskyWang00.pdf)
说明技术形态应当被转译成系统化、自动化的统计对象，而不是依赖人工目测。
但
[Marshall、Young、Rose（2006）](https://doi.org/10.1016/j.jbankfin.2005.08.001)
在 DJIA 股票上没有发现其所测蜡烛策略具有价值。这两项证据共同支持：

> K 线几何可以成为有限 challenger，但命名蜡烛形态不能成为默认交易真理。

### 3.2 可接受的 K 线计算

仅允许使用已闭合 bar 的确定性几何量：

```text
range = high - low
body = abs(close - open)
upper_wick = high - max(open, close)
lower_wick = min(open, close) - low
close_location = (close - low) / max(range, epsilon)
body_fraction = body / max(range, epsilon)
```

这些值只能作为：

- 结构区间的几何描述；
- 趋势或回撤的条件变量；
- 预注册负对照；
- 对现有模型的有限增量 challenger。

禁止在看到结果后增加形态、改变影线比例或重新命名组合。

### 3.3 多周期因果边界

15m 与 4H 的任何特征都必须来自在决策时已经闭合的 bar。

若决策时间为 `t`：

```text
bar.close_time < t
bar.available_at <= t
```

当前未闭合 4H bar 的高、低、收盘、RSI 或趋势都不能进入决策。

## 4. 趋势、动量与均值回归

### 4.1 外部历史证据

[Moskowitz、Ooi、Pedersen（2012）](https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf)
在 58 个期货和远期市场中报告了 1–12 个月的时间序列动量，且更长周期存在部分反转。
[Hurst、Ooi、Pedersen（2017）](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026)
把趋势跟随历史证据扩展到更长时期。

这些研究支持“趋势可能是状态变量”，但不证明：

- 15m/4H BTCUSDT 具有相同时间尺度；
- RSI 超买超卖在趋势中一定延续或一定反转；
- 单标的、单 venue、短持有期能够复制跨资产趋势组合的结果。

[Daniel、Moskowitz（2016）](https://www.kentdaniel.net/papers/published/jfe_16.pdf)
还表明动量策略可能在高波动恐慌后的快速反弹中发生严重损失。

### 4.2 趋势条件化，而非趋势崇拜

系统不把趋势视为永久方向，而把它用于解释 RSI：

| 高周期状态 | 低周期 RSI 事件 | 候选解释 |
|---|---|---|
| 明确上行 | 超卖 | 顺势回撤 LONG 候选 |
| 明确下行 | 超买 | 顺势反弹 SHORT 候选 |
| 明确上行 | 超买 | 不直接做空；观察延续、减仓或等待 |
| 明确下行 | 超卖 | 不直接做多；观察延续、减仓或等待 |
| 无明确趋势 | 超买/超卖 | 仅允许结构区间内的均值回归候选 |
| 冲击/高波动 | 任意 | 优先降风险或 `ABSTAIN` |

这张表是待验证解释，不是已经成立的交易规则。

### 4.3 简单趋势定义优先

首轮 challenger 只比较有限、可解释的定义：

1. 已闭合 4H 过去收益符号；
2. 已闭合 4H 快慢均线差的符号；
3. 经过波动率归一化的 4H 斜率。

不得同时搜索大量周期、均线、阈值和组合后只报告最佳结果。

## 5. 点位、支撑阻力与 EntryZone

### 5.1 点位不是神秘精确价格

[Osler（2000）](https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf)
在外汇市场发现机构发布的支撑阻力水平对日内趋势中断具有一定预测信息，
但效果随货币和机构变化。

本项目据此只提出：

> 结构水平应当被建模为有宽度、可重放、能和随机水平比较的价格区间。

不接受：

- 手工画线；
- 看到反转后补画水平；
- 整数价格天然有效；
- “主力成本线”或“做市商必守价”而无可观测来源；
- 单个精确价位可以忽略 spread、tick 和滑点。

### 5.2 结构区间候选

首轮只允许从已闭合 4H bar 生成：

- 固定窗口前高/前低；
- 因果局部极值；
- 以冻结 ATR 或实现波动率扩展的区间宽度；
- venue tick-size 对齐后的上下边界。

候选区间：

```text
StructuralZone = [level - width, level + width]
```

必须与以下基线比较：

1. 相同时间、相同数量、相同宽度的随机水平；
2. 简单前高/前低；
3. 不使用结构区间的 RSI 基线。

### 5.3 EntryZone 交集

最终入场不是单一水平，而是约束交集：

```text
EntryZone =
    StructuralZone
  ∩ LiquidityFeasibleZone
  ∩ RiskGeometryZone
  ∩ VenueRuleZone
```

若交集为空，输出 `ABSTAIN`。

其中：

- `StructuralZone`：因果历史结构；
- `LiquidityFeasibleZone`：spread、深度和预估冲击允许的价格；
- `RiskGeometryZone`：止损距离和仓位预算允许的价格；
- `VenueRuleZone`：tick、最小数量、最小名义量和价格保护允许的价格。

## 6. 订单簿、订单流与做市商视角

### 6.1 订单流不平衡

[Cont、Kukanov、Stoikov（2014）](https://arxiv.org/abs/1011.6402)
发现最优买卖盘上的限价单、撤单和市价单共同形成的订单流不平衡，
与短窗价格变化近似线性，且价格冲击斜率随市场深度增加而下降。

关键限制是：论文的核心关系主要是同时窗价格解释，不能自动转译成未来收益预测。

因此本项目区分：

```text
contemporaneous impact explanation != future tradable prediction
```

任何 OFI 候选必须只使用决策时已到达的事件预测之后的价格或执行结果。

### 6.2 Queue Imbalance

[Gould、Bonart（2015）](https://arxiv.org/abs/1512.03492)
发现最优买卖队列不平衡对下一次 mid-price 变动方向具有预测信息，
但强度显著依赖 tick regime。

候选定义：

```text
QI = (best_bid_qty - best_ask_qty)
     / max(best_bid_qty + best_ask_qty, epsilon)
```

QI 只能用于：

- 在已有方向候选下确认或否决；
- 在 EntryZone 内选择更保守的成交时机；
- 估计短时 adverse-selection 风险。

QI 不能单独产生方向交易。

### 6.3 OFI 与 aggressive trade 的区别

完整 OFI 包含：

- limit order additions；
- cancellations；
- marketable executions；
- best bid/ask price 和 size 的变化。

仅有 `aggTrade` 时只能构造 signed aggressive flow，不能称为完整 OFI。
缺少连续 diff-depth 或 update-id 时，系统必须明确标记：

```text
OFI = UNKNOWN
```

不得用稀疏 depth snapshot 或成交方向伪造 OFI。

### 6.4 多档盘口

多档 OFI 可能包含增量，但相邻档位高度相关，容易过拟合。
首轮只允许：

- 预先冻结档位数量；
- 使用简单正则化；
- 与 L1 OFI 在相同滚动样本外切分上比较；
- 缺任一档连续覆盖时 fail closed。

不允许因为增加档位后样本内拟合更高就晋级。

### 6.5 做市商视角的正确含义

[Glosten、Milgrom（1985）](https://pages.stern.nyu.edu/~lpederse/courses/LAP/papers/Information%2CFundamental/GlostenMilgrom85.pdf)
说明点差的一部分用于补偿逆向选择。
[Avellaneda、Stoikov（2008）](https://math.nyu.edu/inmemoriam/avellaneda/HighFrequencyTrading.pdf)
说明做市报价应随库存、波动和成交到达风险变化。

由此可以推导：

- spread 不是免费利润；
- 被动成交可能意味着对手方拥有更强短时信息；
- 库存越偏，合理报价越应向降低库存的方向倾斜；
- 波动、逆向选择和流动性撤离上升时，应扩大安全边界或停止报价。

不能推导：

- “做市商正在猎杀止损”；
- 盘口墙一定真实；
- 大挂单一定是支撑或阻力；
- 做市模型可以预测下一段趋势；
- 模拟 maker fill 等同于真实排队成交。

当前主系统是方向交易系统。做市理论在 P0 中只用于：

1. 识别 adverse-selection 风险；
2. 判断 maker/taker 的执行可行性；
3. 约束未来库存和挂单。

完整双边做市仍是 P1/P2，不得扩大当前主路线。

### 6.6 Microprice

[Stoikov（2018）](https://doi.org/10.1080/14697688.2018.1489139)
报告 microprice 在其高频样本中比 mid-price 或简单 weighted mid 更能估计短时未来价格。

在本项目中，microprice 只允许成为 EntryZone 内的执行时机 challenger：

```text
microprice_edge = microprice - midprice
```

它不改变高周期方向，不允许脱离 spread、费用和延迟单独交易。

## 7. OI、funding、basis 与跨市场状态

OI、funding、taker ratio、mark/index basis 反映不同时间尺度的仓位和资金状态。
它们不能和毫秒级盘口事件混成同一因果精度。

首轮只允许作为状态变量：

- OI 变化率；
- funding 水平和变化；
- mark-index basis；
- spot-perpetual basis；
- aggressive buy/sell flow；
- 数据可用性和陈旧度。

禁止采用未经验证的固定叙事，例如：

```text
price up + OI up = guaranteed continuation
price down + OI up = guaranteed short build
high funding = immediate short
```

每个组合必须在相同时间切分中检验其对已有候选的增量，
而不是单独搜索最有利组合。

[Makarov、Schoar（2020）](https://doi.org/10.1016/j.jfineco.2019.07.001)
和比特币碎片化研究表明 crypto 市场存在 venue 间分割和价格形成差异。
因此单 venue 信号在 basis 或跨市场价格明显冲突时，默认降低置信度或 `ABSTAIN`，
而不是假设 Binance 永远领先。

## 8. 波动、仓位与尾部风险

### 8.1 波动率缩放的有限角色

[Moreira、Muir（2017）](https://doi.org/10.1111/jofi.12513)
报告降低高波动期风险暴露可能改善风险调整结果，
但
[Cederburg、O'Doherty、Wang、Yan（2020）](https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X)
给出了跨因子、跨市场普适性的反面证据，因此不能假定该结论在单一加密永续
合约中必然成立。

因此波动率缩放只被提出为风险 challenger：

```text
position_notional =
    min(
        hard_risk_cap,
        stop_distance_risk_budget,
        volatility_scaled_cap,
        liquidity_cap
    )
```

它不被当作 alpha 来源。

通过条件不是收益更高，而是：

- 风险违规率下降；
- 尾部损失下降；
- 最大单 episode 损失受控；
- 成本和换手没有抵消风险收益；
- 样本外净效用不显著恶化。

### 8.2 Kelly 的边界

[Kelly（1956）](https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf)
提供了在已知概率和赔率下最大化长期对数增长的理论。

当前系统的胜率、赔率、尾部和状态转移均未获得稳定校准，
因此：

- full Kelly 禁止；
- fractional Kelly 也不能在 E0/E1 使用；
- 只有一次性 HOLDOUT 后仍有可靠概率校准和稳定成本后分布时，
  才可作为独立 challenger；
- 无论 Kelly 结果如何，账户硬上限、单笔风险和累计损失门优先。

### 8.3 尾部风险

[Rockafellar、Uryasev（2000）](https://uryasev.ams.stonybrook.edu/publications/)
和 coherent risk 文献支持对尾部损失而非单一方差进行约束。

首轮不引入复杂优化器，只报告：

- 最差 episode；
- 95%/99% expected shortfall；
- 最大回撤；
- 连续亏损；
- UTC 日集中度；
- 方向和状态集中度；
- 成本压力下的尾部变化。

## 9. 止损、止盈与动态管理

### 9.1 止损不是普适 alpha

[Kaminski、Lo（2007）](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338)
表明简单止损在随机游走条件下可能降低期望收益，而在动量存在时可能增加价值。

因此止损的首要功能是：

- 限定策略失效；
- 约束单次尾部；
- 保证风险预算可计算；
- 产生可审计终态。

不能因为加入止损后历史收益提高就认为止损创造了方向优势。

### 9.2 初始 barrier

候选入场必须同时冻结：

```text
entry_zone
structural_stop
tail_buffer
target_set
maximum_holding_time
fee_and_slippage_scenario
```

仓位只能在这些值确定后计算。

### 9.3 动态 barrier

每个新事件可以重新计算 TP、SL 和结构退出，但必须遵守：

1. 止损不得向增加最大风险的方向移动；
2. 最大持有期不得延长；
3. 目标不得仅因未成交而无边界外移；
4. 数据质量恶化时只能收紧、退出或 `HALT`；
5. 重新计算使用冻结算法，不在线改变参数；
6. 同一时间戳先应用固定优先级；
7. OHLC 无法判定 barrier 顺序时采用 `STOP_FIRST`。

### 9.4 动态获利不等于追逐浮盈

允许：

- 随结构抬高 LONG 保护止损；
- 随结构降低 SHORT 保护止损；
- 流动性恶化时提前减少暴露；
- 同向订单流失效时收紧目标；
- 到达预注册 time stop 时退出。

禁止：

- 为避免亏损而扩大止损；
- 根据最近几笔盈亏改变参数；
- 在已读结果上增加新的 trailing 规则；
- 删除未盈利的终态；
- 把未成交订单按理论价格记作成交。

## 10. 执行与做市成本

[Almgren、Chriss（2000）](https://doi.org/10.21314/JOR.2001.041)
说明执行必须在市场冲击、时间风险和完成风险之间权衡。

当前主系统优先保持简单：

- marketable-limit IOC；
- 明确最大可接受 spread；
- 明确最大滑点；
- 明确超时和 `NO_FILL`；
- 明确部分成交；
- 明确 reduce-only 保护；
- 计算 implementation shortfall。

只有观察到订单规模相对深度足够大、立即 taker 成本明确吞噬有效增量时，
才研究更复杂的分片、maker 或最优执行。

做市模拟不得假设：

- touch 即 fill；
- 队列前方数量为零；
- 撤单无延迟；
- maker rebate 可以覆盖逆向选择；
- 部分成交总能按同一价格完成。

## 11. 候选假设注册表

### 11.1 P0 候选

| ID | 假设 | 最小增量 | 主要反证 |
|---|---|---|---|
| `V3-H01-TREND_VETO` | 已闭合 1H/4H 波动标准化趋势越强，RSI 极值后的反转 EV 越低；首轮趋势只作为反转 veto，不产生 continuation 订单 | v0.2.2 champion + 单一 trend-veto gate | 同一机会集合下无稳定交互增量，或错过机会的效用损失大于尾部风险改善 |
| `V3-H02-OFI_INCREMENT` | 完整 limit/add/cancel/trade OFI 在现有 aggressive-trade `D` 之外提供短周期增量 | champion + causal OFI confirmation | 相对 D-only 无增量、只在训练期成立、延迟/成本后消失或 placebo 同样有效 |
| `V3-H03-IMPACT_RESILIENCE` | adverse flow 持续时，单位 OFI 的边际冲击下降并伴随非重叠深度恢复，能够识别吸收/韧性 | H02 disposition 记录后，针对预先冻结且不随 H02 结果改变的 `V3-CMP-R-BASELINE` 的独立单层比较 | 相对该 comparator 无校准或成本后 EV 增量；恢复窗口重叠或依赖未来数据 |
| `V3-H04-LEVEL_RESPONSE` | 对冻结价格区间，持续补单且冲击下降支持趋势中断；撤单/耗尽且 OFI 持续只表示突破风险 | H03 disposition 记录后，针对预注册 `V3-CMP-LEVEL-BASELINE` 的独立单层比较 | 不优于 executable-touch G0、随机区间和简单前高/前低；初期突破分支只允许 `ABSTAIN` |
| `V3-H05-VOL_LIQ_GEOMETRY` | 事前波动、spread 和可见容量共同缩放 EntryZone、stop distance 与 horizon，比固定 bps 几何具有更稳定的归一化 MAE/MFE 和成本后效用 | 只替换交易几何，不改变账户硬风险 | 参数邻域崩溃、成本后无增量、风险违规不降或连续缩放劣于简单硬上限 |
| `V3-H06-REMAINING_EV_EXIT` | 在 exact same-submission/same-fill cohort 上，持有剩余 EV 的下置信界不再优于立即退出时离场，可改善现有动态退出且不扩大尾部 | 只改变 exit policy | entry/fill cohort 改变、尾部恶化、净效用无增量或退出收益来自后验删样本 |

### 11.2 P1 候选

| ID | 假设 | 延后原因 |
|---|---|---|
| `V3-H07-MICROPRICE_SELECTION` | QI/microprice 只用于 EntryZone 内候选排序，降低 1/5/30 秒逆向选择和提交成本 | 需要连续 L1/L2、延迟和真实 fill；不得宣称中期 alpha |
| `V3-H08-CROSS_VENUE_CONFIRM` | 独立现货或第二 venue 的领先流/价格响应可以否决 Binance 局部盘口噪声 | 需要同步多源、独立 coverage 和一致 symbol 语义 |
| `V3-H09-CROWDING_CONTEXT` | funding、basis、OI 只条件化反转/突破概率，不直接产生点位 | 与现有拥挤变量重叠，且时间尺度混合风险高 |
| `V3-H10-PASSIVE_EXECUTION` | 只有 spread capture 下置信界覆盖 fill hazard、队列和逆向选择成本时，passive 才优于 IOC | 必须有自身订单、排队、部分成交和撤单遥测 |
| `V3-H11-STATE_RISK_CAP` | 波动、spread、深度和数据质量恶化时收紧风险使用可降低 ES/预算违规 | 风险命题，不以提高收益为必要条件；不得与 H05 同轮改变 |
| `V3-H13-CONTINUATION_BRANCH` | 只有 H01/H04 先证明 continuation 状态可识别后，才设计独立 continuation 动作 | 新策略分支必须拥有独立 EntryZone、退出和标签 |

### 11.3 P2 或拒绝

| 项目 | 状态 | 原因 |
|---|---|---|
| `V3-H12-QUANTIFIED_OHLC_SHAPE` | `P2_STRONG_NEGATIVE_PRIOR` | body/range、wick/range 等在收益、range、volume、trend 后仍须证明增量；失败即永久退役 |
| 大量命名 K 线形态搜索 | `REJECTED_DEFAULT` | 多重检验、主观定义、外部证据混合 |
| “做市商猎杀止损”方向模型 | `REJECTED` | 无唯一可观测机制和反证路径 |
| 盘口墙直接开仓 | `REJECTED` | 可撤销、隐藏流动性、无成交保证 |
| full Kelly | `REJECTED_CURRENT_STAGE` | 概率与尾部分布未校准 |
| HMM/深度学习 regime | `P2` | 简单状态尚未被证明不足 |
| 双边自动做市 | `P2` | 偏离当前方向交易 P0，且无 queue/fill 证据 |
| 在线强化学习调参 | `REJECTED` | 破坏版本冻结、因果审计和风险权限 |
| 多标的、多 venue 同时扩张 | `P2` | 单一 BTCUSDT 尚未完成证据链 |

### 11.4 依赖顺序与不可合并项

- `H02 → H03 → H04` 的**disposition** 必须按顺序记录；H02 与 H03 不得在第一次比较中同时加入。
- H03 的开始条件是 H02 disposition 已记录，不是 H02 必须 `PASS`；H03 只能相对 V3-C 已冻结的 `V3-CMP-R-BASELINE` 独立比较，禁止将 H02 的入选结果累计、替换或自由切换为其 comparator。
- H04 的开始条件是 H03 disposition 已记录，不是 H03 必须 `PASS`；H04 只能相对 V3-C 已预注册的 `V3-CMP-LEVEL-BASELINE` 独立比较，禁止事后改为累计 H02/H03 图。
- H04 的反转与突破是互斥状态；首轮突破只产生 veto/`ABSTAIN`，不产生 continuation 下单。
- H05 是交易几何，H11 是安全风险上限，不能在同一轮同时改变。
- H06 必须锁定 exact same-submission/same-fill cohort，不能靠改变入场事件改善退出结果。
- H07/H10 是执行命题，不能用更高 PnL 反推方向 alpha。
- H08/H09 一次只允许增加一个外部数据族。
- H12 是强负先验的负对照，不能扩展成命名形态搜索。
- H13 是新策略分支，不能继承 reversal 路线的验证结论。

### 11.5 唯一比较图与 V3-C measurement contract

`V3-L0` 至 `V3-L6` 是 challenger 的理论比较层，**不是** v0.2.2
authority 的 B1/B2/B3/B4 阶段，也不表示把前一层获胜特征累计到下一层。
唯一 machine-readable 定义在 hypothesis registry 的 `comparison_graph`：每条 H 只有
一条预注册、独立的 comparator edge；`post_hoc_comparator_switching=FORBIDDEN` 且
`cumulative_layering=FORBIDDEN`。

```text
V3-L0 = frozen champion reference only
V3-L1 = H01 vs V3-CMP-CHAMPION
V3-L2 = H02 vs V3-CMP-D-ONLY
V3-L3 = H03 vs V3-CMP-R-BASELINE, after H02 disposition only
V3-L4 = H04 vs V3-CMP-LEVEL-BASELINE, after H03 disposition only
V3-L5 = H05 vs V3-CMP-GEOMETRY-BASELINE
V3-L6 = H06 vs V3-CMP-SAME-FILL-EXIT
```

当前没有任何 H 的 measurement function 已冻结。每项只保留
`measurement_definition_candidate`，并共同绑定
`V3-C-MEASUREMENT-CONTRACT-REQUIRED / NOT_FROZEN_REQUIRES_V3_C_SYNTHETIC`。
V3-C 必须先以合成的闭合 bar、available-at、缺失、乱序、first-hit 与 comparator
不变性测试冻结 measurement contract；在此之前，不得声称任何测量公式、阈值或层比较
已冻结。

## 12. 历史验证协议

### 12.1 先分离 AUTHORITY_B4_DATA_FEASIBILITY 与 DEVELOPMENT_GATE

`AUTHORITY_B4_DATA_FEASIBILITY` 是需要新的 Sol 授权的 outcome-free 数据可行性门：
它最多可以在明确 grant 和独立 source-adapter contract 同时存在时允许 adapter/schema/
availability/cost 可行性工作；它**不**授予历史 outcome access 或 backtest。

`INDEPENDENT_DEVELOPMENT_GATE` 是 B4 之后仍需单独 Sol 授权的第二道门。只有 B4
已授权、adapter contract 已冻结、DEVELOPMENT 日期角色与成本模型已冻结时，它才可以
单独授予 historical outcome access 和 backtest。任何 B4 授权本身都不能被解释为
DEVELOPMENT 授权。

在这两个门完成前，source adapter、历史 outcome、backtest、CALIBRATION、HOLDOUT、
paper 和 live 都保持禁止。

### 12.2 任何结果可见前冻结

每次历史实验必须先冻结：

- hypothesis ID；
- candidate 公式；
- 所有参数及有限搜索空间；
- 数据来源、symbol、contract、日期、时区；
- archive URL 和 checksum；
- 数据角色；
- feature available-at 规则；
- baseline；
- 成本、滑点和延迟；
- entry、TP、SL、time stop 和 first-hit；
- 评价指标；
- 反证门；
- 停止规则；
- 允许声明。

### 12.3 时间角色

```text
DEVELOPMENT
  → 规则实现、机制否定、有限参数选择

CALIBRATION
  → 概率校准、阈值确认、唯一 candidate 冻结

HOLDOUT
  → 一次性打开，只评价，不修复
```

任何被读取的窗口永久标记为 `SEEN`。
HOLDOUT 失败后只能退役 candidate 或建立新版本并移动到更晚未见窗口。

### 12.4 基线和增量层

同一数据、成本、标签和时间切分上依次比较：

```text
V3-L0 = frozen champion reference
V3-L1 = H01 vs frozen champion
V3-L2 = H02 vs frozen champion/D-only
V3-L3 = H03 vs its pre-frozen R comparator after H02 disposition
V3-L4 = H04 vs its pre-registered level comparator after H03 disposition
V3-L5 = H05 vs its pre-frozen geometry comparator
V3-L6 = H06 vs its pre-frozen same-fill exit comparator
```

每一层只回答“相对 registry 中唯一 comparator 是否有增量”，不能把所有特征一次加入、
不能从累计图改为独立图、也不能在看到 predecessor disposition 后替换 comparator。

### 12.5 预测指标

- Brier score；
- log loss；
- calibration slope/intercept；
- reliability by probability bin；
- next-mid or first-hit direction；
- abstain coverage；
- 每状态有效 episode 数。

AUC 或 accuracy 只能作为辅助指标，不能替代校准和成本后结果。

### 12.6 交易与执行指标

- 成本后 expectancy；
- 10/20 bps 或冻结 venue 成本压力；
- implementation shortfall；
- fill、partial fill、no-fill、reject 比例；
- TP/SL/structure/time-stop 终态；
- 最大回撤；
- expected shortfall；
- 最差 episode；
- UTC 日、方向、状态和行情阶段集中度；
- 换手与持有时间。

### 12.7 统计和 placebo

至少执行：

1. 按 UTC 日或事件簇 block bootstrap；
2. feature 时间平移；
3. 方向符号置换；
4. 随机结构区间；
5. 延迟注入；
6. 更差一档 spread/slippage；
7. White Reality Check 或 Hansen SPA，用于有限候选族；
8. Deflated Sharpe/PBO 仅作为多重试验诊断，不作为唯一通过门。

[White（2000）](https://doi.org/10.1111/1468-0262.00152)
和
[Sullivan、Timmermann、White（1999）](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=160330)
说明重复搜索同一时间序列会把偶然结果误认为有效规则。

### 12.8 结果状态

每条假设只能得到以下之一：

| 状态 | 含义 |
|---|---|
| `NOT_RUN` | 尚未获准运行 |
| `WAIT_DATA` | 所需数据、时序或执行字段不存在 |
| `STOP_DATA_INVALID` | 数据或资格链不能支持该问题 |
| `INCONCLUSIVE_COVERAGE` | 样本或状态覆盖不足 |
| `SUPPORTED_DEVELOPMENT_ONLY` | DEVELOPMENT 中存在预注册增量，仍不能称为有效 |
| `REJECTED_DEVELOPMENT` | 机制或增量被 DEVELOPMENT 否定 |
| `CALIBRATION_PASS` | 规则和阈值已冻结，可申请一次性 HOLDOUT |
| `REJECTED_CALIBRATION` | CALIBRATION 否定或方向反转 |
| `HOLDOUT_PASS_BOUNDED` | 特定窗口和假设下未被否定，不代表永久有效 |
| `REJECTED_HOLDOUT` | 一次性 HOLDOUT 否定 candidate |

## 13. 数据可行性与更多可利用数据

### 13.1 P0 免费来源

| 数据 | 主要用途 | 权威来源 | 关键限制 |
|---|---|---|---|
| 15m/4H kline、mark kline | RSI、趋势、结构 zone、first-hit 粗验证 | Binance 官方公开数据 | bar 内路径丢失 |
| aggTrade/trade | signed aggressive flow、成交强度 | Binance 官方公开数据 | aggTrade 不是完整 OFI |
| funding、premium、mark/index | basis 和拥挤状态 | Binance Futures 官方 API | 频率低于 L2 |
| OI 与 OI statistics | 仓位状态 | Binance Futures 官方 API | 不能直接解释方向 |
| diff-depth + snapshot | 连续 L2、QI、OFI、microprice | Binance WebSocket + REST snapshot | 必须重建、封存和验证 sequence |
| exchangeInfo | tick、lot、status、价格规则 | Binance 官方 API | schema 可能变化 |
| OKX 历史 L2 | 外部机制复现 | OKX 官方历史数据 | 只能形成外部 E0-X，不能替代 Binance |
| 多 venue spot/perp mid | fragmentation/basis gate | 各 venue 官方源 | 时钟与 symbol 语义必须统一 |

[Binance 官方开发文档](https://developers.binance.com/en/docs/introduction)
只证明接口和字段存在，不证明任何交易优势。

### 13.2 P1 可选来源

- CME Bitcoin futures 的公开结算、成交量、持仓与 CFTC COT；
- ETF 公开价格、NAV、成交量和申赎数据；
- options implied volatility、skew 和 term structure；
- 链上交易所净流、稳定币和结算数据；
- 新闻与宏观事件日历。

这些数据只在以下条件同时满足时接入：

1. 能明确映射到具体假设；
2. 有 point-in-time availability；
3. 不显著拖慢 P0；
4. 能在免费或低成本条件下持续获得；
5. 有独立基线和反证门。

### 13.3 暂不采购

付费 L2、新闻低延迟源、专有 sentiment 和另类数据仅在：

- 免费数据无法回答 P0 假设；
- 等待成本高于购买成本；
- 数据能改变明确决策；
- licensing、存储和生产延迟可持续；
- 已观察到非数据因素不是主要瓶颈；

时才进入采购评估。

## 14. 当前可验证事实与尚未验证部分

### 14.1 已完成

- 已搜集并交叉审阅趋势、技术形态、支撑阻力、订单流、做市、
  执行、止损、风险和回测治理的一手来源；
- 已把外部结论转译成有限候选、可观测量和反证门；
- 已明确做市理论用于库存/逆向选择和执行，不用于猜测“主力意图”；
- 已明确蜡烛形态为负对照或有限 challenger，不是默认信号；
- 已形成 `AUTHORITY_B4_DATA_FEASIBILITY` 后、且另经 `INDEPENDENT_DEVELOPMENT_GATE`
  授权才能开始的分层历史验证协议。

### 14.2 当前不能执行的验证

当前 `RSI-MTF-DRL-PM v0.2.2` 的精确阶段是
`B1_CANDIDATE awaiting independent Sol gate; B2 unauthorized`，
其 route contract 明确将 market data、historical data、source adapter 和 backtest
设为禁止能力。新的 `AUTHORITY_B4_DATA_FEASIBILITY` 即使被 Sol 授权，也只可能在
独立 contract 下放行 outcome-free 数据可行性；历史 outcome/backtest 仍禁止，直至
后续独立 `INDEPENDENT_DEVELOPMENT_GATE` 明确授权。

既有 January/February 数据已经 `SEEN`、用于其他 DEVELOPMENT 或被隔离，
不能成为本 challenger 的独立 CALIBRATION/HOLDOUT。

活动 G1 当前还因磁盘资源门处于 `RESOURCE_BLOCKED`，没有形成新的 G1 evidence。

因此本文的实际证据等级仍为：

```text
external historical evidence: PRESENT, asset-transfer-limited
local executable validation: NOT_RUN
project market evidence: E0
trading authorization: DENIED
```

## 15. 动态路线与优先级

### P0-A：完成现有 v0.2.2 authority

1. B1 refreeze report；
2. Sol B1 gate；
3. B2 kernel 对齐与测试；
4. Sol B2 gate；
5. B3 golden、双进程 replay、manifest、external receipt；
6. Sol B3 gate。

v0.3 的最小下一 P0 不是实现或数据工作，而是独立 `Sol V3-B gate`。
只有该 gate `PASS` 后才允许启动 V3-C synthetic 因果测试；B4 数据可行性申请
必须等到 V3-C 后续阶段门明确允许，不能因 v0.3 文档已完成修复而提前申请。

### P0-B：申请 AUTHORITY_B4_DATA_FEASIBILITY

B3 后、任何新数据结果可见前：

1. 从本文件 P0 候选中只选择一个增量层；
2. 冻结数据窗口角色和 checksums；
3. 冻结 baseline、成本、指标和失败门；
4. 建立独立 source-adapter contract；
5. 申请新的 Sol `AUTHORITY_B4_DATA_FEASIBILITY` 授权；该授权不等于 DEVELOPMENT。

### P0-C：独立 DEVELOPMENT gate 后的首批低成本验证

只有在 B4 已授权且新的 Sol `INDEPENDENT_DEVELOPMENT_GATE` 对冻结的日期角色、
adapter contract、成本模型和 outcome access/backtest 作出单独 grant 后，以下项目才可运行。

不需要完整 L2 的可行性/合成先行项：

1. `V3-H01-TREND_VETO`；
2. `V3-H05-VOL_LIQ_GEOMETRY` 中仅使用已冻结 kline/mark 的波动部分；
3. H06 的 same-fill 和 barrier 计算合成测试。

需要连续 L2 的第二批：

1. `V3-H02-OFI_INCREMENT`；
2. `V3-H03-IMPACT_RESILIENCE`；
3. `V3-H04-LEVEL_RESPONSE`；
4. H05 的 spread/capacity 部分；
5. `V3-H07-MICROPRICE_SELECTION`。

### P1：执行与跨市场

- basis disagreement gate；
- 多 venue price formation；
- maker/taker 路由；
- 部分成交与 queue 模型；
- options、ETF、COT 或宏观数据增量。

### P2：仅在观察到明确瓶颈后

- 深度学习；
- HMM regime；
- 双边做市；
- 多标的；
- 付费专有数据；
- 多机低延迟架构。

## 16. 晋级到新主理论的必要条件

任何 v0.3 内容进入未来主理论，必须同时满足：

1. 外部来源和机制完整；
2. point-in-time 数据可持续获得；
3. DEVELOPMENT 滚动样本外相对基线有增量；
4. CALIBRATION 不发生方向反转；
5. 一次性 HOLDOUT 未被预注册门否定；
6. 成本、延迟和 no-fill 后仍成立；
7. 尾部和集中度未恶化；
8. placebo 不能产生同等结果；
9. exact artifact、code、data 和 report 可重放；
10. 独立 Sol 阶段门审核通过。

任一条件失败时，合理结果是退役、简化或 `ABSTAIN`，不是继续增加特征。

## 17. 核心结论

外部权威研究对现有理论最有价值的扩充不是增加更多指标，而是明确了四层分工：

1. **趋势和结构**解释 RSI 事件属于回撤、反弹还是不可判断；
2. **订单流和流动性**确认短时方向是否可执行，并识别逆向选择；
3. **EntryZone、成本和风险几何**决定是否存在值得承担风险的点位；
4. **first-hit、执行和证据治理**决定历史优势是否真实、可重放、可进入下一阶段。

当前最合理的系统不是“指标越多越精密”，而是：

```text
少量可解释候选
+ 完整数据因果
+ 强制 ABSTAIN
+ 保守执行
+ 可反证历史验证
+ 分阶段人工晋级
```

本文已经完成理论候选的结构化整合，但尚未完成本项目历史验证；
在 `AUTHORITY_B4_DATA_FEASIBILITY` 与独立 `INDEPENDENT_DEVELOPMENT_GATE` 均未
完成前，任何更强结论都属于越级声明。

## 18. 主要一手来源

1. Lo, Mamaysky, Wang, “Foundations of Technical Analysis,”
   *Journal of Finance*, 2000：
   https://www.mit.edu/people/wangj/pap/LoMamayskyWang00.pdf
2. Brock, Lakonishok, LeBaron, “Simple Technical Trading Rules and the
   Stochastic Properties of Stock Returns,” *Journal of Finance*, 1992：
   https://doi.org/10.1111/j.1540-6261.1992.tb04681.x
3. Sullivan, Timmermann, White, “Data-Snooping, Technical Trading Rule
   Performance, and the Bootstrap,” *Journal of Finance*, 1999：
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=160330
4. White, “A Reality Check for Data Snooping,” *Econometrica*, 2000：
   https://doi.org/10.1111/1468-0262.00152
5. Hansen, “A Test for Superior Predictive Ability,” *JBES*, 2005：
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569
6. Moskowitz, Ooi, Pedersen, “Time Series Momentum,” *JFE*, 2012：
   https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf
7. Hurst, Ooi, Pedersen, “A Century of Evidence on Trend-Following
   Investing,” 2017：
   https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026
8. Daniel, Moskowitz, “Momentum Crashes,” *JFE*, 2016：
   https://www.kentdaniel.net/papers/published/jfe_16.pdf
9. Osler, “Support for Resistance,” Federal Reserve Bank of New York, 2000：
   https://www.newyorkfed.org/medialibrary/media/research/epr/00v06n2/0007osle.pdf
10. Marshall, Young, Rose, “Candlestick Technical Trading Strategies:
    Can They Create Value for Investors?”, *JBF*, 2006：
    https://doi.org/10.1016/j.jbankfin.2005.08.001
11. Cont, Kukanov, Stoikov, “The Price Impact of Order Book Events,”
    *Journal of Financial Econometrics*, 2014：
    https://arxiv.org/abs/1011.6402
12. Gould, Bonart, “Queue Imbalance as a One-Tick-Ahead Price Predictor,”
    2015：
    https://arxiv.org/abs/1512.03492
13. Glosten, Milgrom, “Bid, Ask and Transaction Prices in a Specialist
    Market,” *JFE*, 1985：
    https://doi.org/10.1016/0304-405X(85)90044-3
14. Kyle, “Continuous Auctions and Insider Trading,” *Econometrica*, 1985：
    https://doi.org/10.2307/1913210
15. Avellaneda, Stoikov, “High-Frequency Trading in a Limit Order Book,”
    *Quantitative Finance*, 2008：
    https://doi.org/10.1080/14697680701381228
16. Stoikov, “The Micro-Price,” *Quantitative Finance*, 2018：
    https://doi.org/10.1080/14697688.2018.1489139
17. Almgren, Chriss, “Optimal Execution of Portfolio Transactions,” 2000：
    https://doi.org/10.21314/JOR.2001.041
18. Kaminski, Lo, “When Do Stop-Loss Rules Stop Losses?”, 2007：
    https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338
19. Moreira, Muir, “Volatility-Managed Portfolios,” *Journal of Finance*,
    2017：
    https://doi.org/10.1111/jofi.12513
20. Rockafellar, Uryasev, “Optimization of Conditional Value-at-Risk,”
    2000：
    https://uryasev.ams.stonybrook.edu/publications/
21. Kelly, “A New Interpretation of Information Rate,” 1956：
    https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf
22. Makarov, Schoar, “Trading and Arbitrage in Cryptocurrency Markets,”
    *JFE*, 2020：
    https://doi.org/10.1016/j.jfineco.2019.07.001
23. Binance Developer Documentation：
    https://developers.binance.com/en/docs/introduction
24. Binance Public Data：
    https://github.com/binance/binance-public-data
25. Cederburg, O'Doherty, Wang, Yan, “On the Performance of
    Volatility-Managed Portfolios,” *JFE*, 2020：
    https://www.sciencedirect.com/science/article/abs/pii/S0304405X2030132X
