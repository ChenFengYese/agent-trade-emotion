# V3.3.2 市场状态转换、双时钟与多维评价

版本：`3.3.2-complete-market-analysis-candidate.3`

状态：`FROZEN_THEORY_REVIEW_CANDIDATE / MARKET_AND_POSITION_EVALUATION_DEFINED / FORWARD_EVALUATION_NOT_RUN`

Owner：Agent拥有状态、路径与复盘语义；系统只拥有点时事实和透明Outcome测量。

## 1. 核心定义

V3.3.2 的主要预测对象不是单个未来价格，而是市场状态及其转换：

```text
结构识别
→ 参与者约束
→ 行为/主体竞争假说
→ 关键区域和事件
→ 条件触发
→ 状态转换
→ 动态证伪与重规划
```

RSI、K线、成交量、订单流、OI、funding、新闻和情绪proxy都是观察状态的传感器，不是自动投票者。

## 2. 状态向量

概念状态可以写为：

```text
S_t = {
  structural_trend,
  volatility_state,
  auction_and_key_zones,
  participation_and_volume,
  liquidity_and_order_flow,
  positioning_and_leverage,
  information_event_state,
  sentiment_and_attention_proxy,
  cross_asset_and_venue_state
}
```

每个分量可以 `OBSERVED / DERIVED / HYPOTHESIZED / UNKNOWN`。状态向量不要求每一维有数据，也不把UNKNOWN补成中性。

参与者与意图另写为竞争假说 `H_t`，不能混入状态事实：

```text
H_t = {
  trapped_long_exit,
  bottom_fisher_profit_taking,
  short_covering,
  leverage_liquidation,
  market_maker_inventory,
  institutional_support,
  distribution_after_news,
  OTHER
}
```

## 3. 状态转换不是已校准概率

概念上可以研究：

```text
Pr(S_{t+h}=j | S_t=i, X_t, H_t)
```

但在状态集合尚未互斥完备、样本不足或未完成校准时，V3.3.2只输出：

```text
operational lead
runner-up
OTHER / unresolved
conditions that switch the lead
```

只有在以下条件全部成立后，才允许输出数值转移概率：

1. 状态定义事前冻结、互斥且覆盖OTHER；
2. horizon、sampling和状态标注规则冻结；
3. 训练、校准和评价严格未来隔离；
4. 样本量、缺失、class imbalance和regime覆盖可报告；
5. calibration curve/Brier或适用评分已预注册；
6. 数值不由语言确信度伪造。

市场通常不满足“下一状态只由当前单一标签决定”的简单Markov假设。持续时间、路径历史、关键区测试次数、未完成事件和外部信息都可能影响转换。未来模型至少比较：规则化事件状态机、semi-Markov/显式duration模型、change-point/regime模型和无状态的直接基线；复杂模型必须证明有前瞻增量。

## 4. 市场事件时钟与日历时钟

```text
Calendar Clock != Market Event Clock
```

### 4.1 Event clock

路径先写事件顺序：

```text
E1 测试关键区域
E2 出现吸收/拒绝或接受性跌破
E3 进入反弹或下行扩张状态
E4 触达下一价值区/压力区
E5 出现衰竭、再接受或反转
```

每个事件包含：

```text
activation condition
observable completion rule
allowed tolerance band
dependency on prior event
soft contradiction
hard falsifier
expiry/censor rule
action implication
```

### 4.2 Calendar clock

日历时间另写：

- 最早合理窗口；
- 中心窗口或序数时效判断；
- 最晚到期；
- 开闭市、事件和流动性依赖；
- 若未校准，只写 `immediate / near / delayed / unresolved` 或时间区间，不输出伪精确概率。

方向和事件顺序正确、calendar timing偏差较大时，只惩罚timing，不把方向和路径一起判错。

## 5. 路径状态与验证域

每个预注册事件在Outcome时只能处于：

| 状态 | 含义 |
|---|---|
| `NOT_ACTIVATED` | 前置事件未发生，尚未进入验证域 |
| `ACTIVE` | 前置条件满足，正在演化 |
| `HIT` | 在容差和期限内满足 |
| `PARTIAL` | 方向/区域部分满足但目标或确认不完整 |
| `SOFT_MISS` | 偏离预期但未命中hard falsifier |
| `HARD_FAIL` | 预注册反证命中 |
| `EXPIRED` | 到期未发生 |
| `CENSORED` | 数据/观察窗口结束，无法判断 |

后续事件不能在前置事件未激活时被提前判错。例如 `E3→E4→E5` 中E3尚未完成，E4/E5应为 `NOT_ACTIVATED`，不是失败。

## 6. 十四个相互独立的评价维度

### 6.1 状态识别 `State Accuracy`

评价当时对趋势、区间、转换、波动和关键区域的识别是否解释了后续市场行为。若状态标签未冻结，只做Agent定性review，不事后强行量化。

### 6.2 方向 `Directional Accuracy`

在预先冻结horizon内，评价主路径的方向或状态迁移方向。必须说明是endpoint、最大位移、第一事件还是全过程方向，不能事后挑有利口径。

### 6.3 路径顺序 `Path Accuracy`

比较预注册事件序列和实际触达序列：

```text
predicted: down → support test → break → acceleration → rebound
observed : down → support test → break → acceleration → rebound
```

可计算有序里程碑的命中、遗漏、倒序和额外事件；不能用事后新增里程碑提高命中。

### 6.4 关键区域 `Level Accuracy`

同时报告原始百分比误差和波动标准化误差：

```text
E_pct = |realized_level - predicted_center| / |predicted_center|
E_scaled = distance_to_predicted_zone / predecision_scale
predecision_scale = frozen ATR or zone width
```

若价格进入事前区域，按zone hit评价；不能只拿中心点制造失败。

### 6.5 时间 `Timing Error`

只有事前声明calendar窗口时才评价：

```text
early_error = predicted_start - realized_time, if realized earlier
late_error  = realized_time - predicted_end, if realized later
```

未声明时间则为 `NOT_SCORED`；事件未激活则为 `NOT_ACTIVATED`；观察终止则为 `CENSORED`。

### 6.5.1 未来独立 timing 模型

在样本和校准门满足后，可将每个事件视为time-to-event问题：

```text
T_k = time from activation of E_{k-1} to completion of E_k
```

候选方法包括离散时间survival/hazard、competing risks和带duration的状态模型。输入只能使用激活时合法可得的状态、流动性、订单到达、事件日历和波动；未发生事件必须作为right-censored，不得删除。timing模型输出只是Agent的一个工具，不覆盖事件路径和最终动作。

### 6.6 机制与主体 `Mechanism/Actor Support`

分别评价：

```text
price/path evidence
latent-state evidence
actor identity evidence
actor intent evidence
```

路径命中不自动证明机构身份。主体假说可以保留规划价值，但证据等级不因此越级。

### 6.7 动作 `Action Utility`

比较当时所有合法动作：LONG、SHORT、WAIT、probe、HOLD、ADD、REDUCE、CLOSE、runner、reentry等。评价动作是否利用正确路径、是否错过机会、是否在反证后及时改变。

在不可执行研究中，只评价reference action和公开压力几何，不宣称真实fill或收益。

### 6.8 仓位与风险 `Position Policy`

评价初始风险、tranche、止损、落袋、runner、reentry和共享风险是否与路径一致。不能用事后MFE选择一个从未在当时提出的“最优仓位”。

### 6.9 仓位转换 `Position Transition Quality`

逐次评价 `ReferenceExposureState → TargetExposureState → PositionDelta`：

- 是否由决策相关新证据、几何、成本、预算或到期驱动；
- ADD 是否是新证据而不是摊平；
- REDUCE/HARVEST/CLOSE 是否区分风险恶化、兑现和 thesis 失效；
- REENTER 是否有新证据和新风险身份；
- 多周期角色是否被静默混合或重命名；
- 同一阈值附近是否发生不必要的反复交易。

### 6.10 参考执行 `Reference Execution Robustness`

评价事前冻结的 `TOUCH_ONLY_UPPER_BOUND/NEXT_OBSERVABLE_PRICE/STRESS_BAND/LIQUIDITY_AWARE_PROXY` 口径、价带、延迟、spread、impact、funding、borrow 和未成交处理。只有 touch 时不能给 fill 评价；路径粒度不足时标 `UNRESOLVED_REFERENCE_EXECUTION`。

### 6.11 真实执行 `Actual Execution Quality`

只有未来存在授权、OrderTruth、FillTruth、费用和账户对账时才评价：fill rate、implementation shortfall、slippage、latency、rejection、partial fill、cancel/replace 和 target-versus-actual。当前一律为 `NOT_APPLICABLE_NOT_AUTHORIZED`，不能用公开K线代替。

### 6.12 风险治理 `Risk Governance`

评价 Agent 是否遵守自己事前声明的 invalidation、tranche/episode/组合预算、pending risk、数据降级和产品特有风险；未来另评价系统硬风险门是否正确 permit/block、有没有静默改仓或漏拦未授权副作用。

### 6.13 机会成本与换手 `Opportunity Cost / Churn`

评价 WAIT 是否有明确原因和复核价值、限价未成交是否错失路径、无交易区是否避免噪声、迟滞是否过强或过弱，以及不必要转换造成的参考成本。未校准时做条件与序数比较，不伪造精确反事实利润。

### 6.14 注意力调度 `Attention Scheduling Quality`

评价 Agent 是否在真正临界阶段选择连续观察，是否为等待声明了有价值的复核窗，以及是否因过早、过晚或过度频繁进入而损害决策：

- `CONTINUE_NOW` 是否绑定新数据和明确退出条件；
- `WAKE_AFTER/RELEASE` 的时间是否在信号成熟、失效、止损或事件发布前留下行动空间；
- 实际进入延迟来自 Agent 时间判断、监控批准、系统派发还是外部不可用；
- 提前进入造成多少无效分析，迟到进入错过哪些前兆、入场、减仓或保护机会；
- 突发信息早于预期到达时，原注意力决策是否仍符合当时信息，而不是用后见之明改写；
- 同等路径质量下使用了多少观察时间和重新进入次数。

该维度评价“何时值得重新看”，不把唤醒次数少或模型调用少自动当作高效，也不让系统按得分接管下一次市场判断。

## 7. 不使用单一总分覆盖细节

V3.3.2 默认给出多维结果：

```text
state      = strong / mixed / weak / not_evaluated
direction  = hit / miss / unresolved
path       = ordered hit / partial / fail / censored
level      = zone hit + errors
timing     = early / on-window / late / not_scored
mechanism  = supported / unverified / contradicted
action     = useful / mixed / opportunity missed
position   = appropriate / aggressive / conservative / unresolved
transition = timely / premature / late / noisy / unresolved
ref_exec   = robust / optimistic / missed / touch_only / unresolved
actual_exec= not_applicable / reconciled_quality_state
risk       = followed / breached / ambiguous / not_evaluated
churn      = restrained / excessive / opportunity_missed / unresolved
attention  = timely / early / late / overactive / missed / runtime_delayed / unresolved
```

系统可以计算客观测量，但不能用加权总分替Agent选择市场方向或自动修改理论。

## 8. 闪迪案例的初步多维结果

依据用户原始记录与随后公开SNDK路径，教学用初评为：

| 维度 | 初评 |
|---|---|
| 趋势/状态 | 强命中：识别下降、支撑争夺、破位扩张和低位反弹 |
| 主方向 | 强命中 |
| 路径顺序 | 中高命中 |
| 关键区域 | 中高命中：1300失守、约1000低位和反弹区域有意义 |
| 精确目标 | 部分：800和1600未完成 |
| calendar timing | 较弱或记录不足 |
| 成交量 | 明确失败：部分窗口实际放量而非递减 |
| 主体/意图 | 可保留为假说，公开证据不足 |
| 动作选择 | 原记录有部分参考动作，但不同时间记录未形成统一冻结policy，`PARTIAL/NOT_FORWARD_EVALUATED` |
| 仓位/转换 | 有风险、止损和路径想法；无连续参考敞口与逐次转换证据，`NOT_EVALUATED` |
| 参考执行 | 只有点位和公开价格触达，不能证明fill，`TOUCH_ONLY` |
| 真实执行 | 无授权账户/订单/成交证据，`NOT_APPLICABLE` |
| 教学价值 | 高：展示状态转换预测强于单点和时间预测 |

该初评的完整事实、限制与教学重写见 [`08_SANDISK_USDT_TEACHING_CASE.md`](./08_SANDISK_USDT_TEACHING_CASE.md)。

## 9. 正式前瞻评价最低门

1. 冻结原始决策时间、版本、数据和事件路径；
2. 冻结state、direction、path、level、timing、action、position、transition、execution和attention口径；
3. Outcome前不读取未来；
4. 未激活、部分、失败、到期和截尾分开；
5. price-only与增强数据在同一cutoff/horizon比较；
6. 主体机制和状态路径分别评分；
7. 不用一个案例证明普适性；
8. reference touch、fill和actual account outcome分开；
9. 预注册或明确标记事后反事实动作与仓位尺度；
10. 新理论学习只进入新版本，不回填原决策。

## 10. 三阶段扩展路线

### Phase A：人工可读状态转换

Agent用自然语言和事件序列形成状态路径；系统只提取非权威触达索引。目标是验证概念是否稳定，不训练概率。

### Phase B：冻结状态本体与事件标注

在足够前瞻样本上检查状态标签一致性、OTHER覆盖、事件顺序和censoring；不因标签难做就删除合法动作或主体假说。

### Phase C：独立timing/transition模型

仅在满足第3节校准门后，训练和评价数值状态转移或time-to-event模型。模型是Agent的一个传感器/工具，不拥有最终动作和仓位。

## 11. 仓位转换的验证域

市场事件状态和仓位转换状态相互关联但不相同。每个预注册 `PositionTransitionPlan` 在 Outcome 时使用：

| 状态 | 含义 |
|---|---|
| `PLANNED` | 计划已封存，尚未到观察窗口 |
| `NOT_ACTIVATED` | activation 未发生，没有参考风险变化 |
| `ACTIVATED_REFERENCE` | 市场条件发生；仅表示参考计划被激活，不表示真实fill |
| `PARTIAL_REFERENCE` | 事前定义的部分路径/分批条件发生 |
| `COMPLETED_REFERENCE` | 按冻结参考口径完成目标转换 |
| `CANCELED` | 预注册取消/冲突条件先发生 |
| `HARD_FAIL` | 失效条件命中，原转换 thesis 失败 |
| `EXPIRED` | 条件到期未发生 |
| `UNRESOLVED_PATH` | 数据粒度无法确定先后或激活状态 |
| `CENSORED` | 观察窗口结束或数据中断，无法继续评价 |

例如同一根K线同时穿过 entry 与 stop，且没有更细路径，不能写成“先入场后止损”或“未入场”。它属于 `UNRESOLVED_PATH`，除非事前冻结了适用的保守路径规则。

## 12. 动态决策按 decision point 评价

一个 episode 可有多个决策点：

```text
D0 WATCH/OPEN
D1 HOLD/ADD/REDUCE
D2 HARVEST/RUNNER/CLOSE
D3 REENTRY_PENDING/REENTER/EXPIRE
```

每个 `D_k` 只使用当时 cutoff 的事实评价：

```text
prior state
new decision-relevant delta
legal action set
chosen target exposure and transition
reference execution assumption
subsequent bounded Outcome
```

最终方向命中不能替中间错误加仓免责；最终亏损也不能把合规减险和稳健执行一起判错。若 Agent 在硬反证后依据新证据改变观点，这是动态更新能力，不是“原预测必须永远坚持”。

## 13. 合法替代动作与反事实比较

理想情况下，cutoff 时冻结：

- chosen action；
- runner-up/OTHER；
- WAIT 的机会成本；
- 若有意义，离散参考尺度（例如 flat/probe/small/medium/full-plan）；
- 各 arm 共用的参考执行、成本和风险口径。

Outcome 后可比较“哪个当时合法 arm 更好地利用路径”，但必须保留：

```text
PRE_REGISTERED_ALTERNATIVE
REVIEW_ONLY_COUNTERFACTUAL
NOT_COMPARABLE_DUE_TO_FILL_OR_DATA
```

只有事后看到 MFE 才发明的满仓、最低点入场或最高点退出不能算预测能力。反事实比较用于学习动作和仓位政策，不用于把旧记录改写成命中。

## 14. 失败归因矩阵

| 观察结果 | 首要归因候选 | 不能自动推出 |
|---|---|---|
| 方向/状态错，stop按计划 | market analysis failure | risk governance failure |
| 路径判断对，选择WAIT错失 | action/opportunity failure | market analysis failure |
| 动作方向对，仓位超出事前预算 | sizing/risk failure | 方向错误 |
| 分析与仓位对，限价未成交 | reference/actual execution failure | 策略方向错误 |
| touch目标但无fill证据 | touch-only outcome | 已实现收益 |
| ADD后亏损且没有新证据 | transition/policy failure | 假说必然为假 |
| 数据已变旧仍当当前事实 | data/PIT or degradation failure | 正常市场误差 |
| 订单已ACK但账户不符 | execution/reconciliation failure | 目标仓位已完成 |
| 路径判断正确但 Agent 过晚请求复核而错过动作窗 | attention scheduling failure | 市场状态判断错误 |
| Agent 按时请求但系统超过最晚有效时间才恢复 | runtime dispatch failure | Agent timing failure |

Review 可判断多重原因，但必须说明证据链，不能用盈亏作为单一总解释。

## 15. Candidate.3 评价能力结论

评价体系现已覆盖“看对没有”之外的完整问题：是否选对动作、承担多少风险、何时改变、何时重新观察、如何参考执行、是否遵守风险、真实成交是否实现意图，以及频繁调整或唤醒是否值得。当前这些只是冻结评价合同；闪迪案例只能教学重构，尚不能证明动态仓位、注意力调度或执行能力。正式能力证据必须来自新身份、未来隔离、逐 decision point 的前瞻记录。
