# MSTA-HED 理论整合 Challenger v0.6.0

> 状态：`E0_OUTCOME_FREE_DRAFT_AWAITING_SOL_STAGE_GATE`
>
> 本文件是待审查的理论整合草案，不替换 [CORE_TRADING_THEORY_v2_1.md](./CORE_TRADING_THEORY_v2_1.md) 或 v0.5 method/registry contract。它不授权 `DATA`、`OUTCOME`、`BACKTEST`、`CALIBRATION`、`HOLDOUT`、`PAPER`、`LIVE`、`DEPLOY` 或活动 G1 mutation。

## 1. 目的与不可越界

MSTA-HED 的目的，是把点时可观测事实、多个时间角色、结构位置、有限竞争解释和受限行动建议写成一个可审计的候选方法链。它不是市场真值发现器、收益承诺、订单策略，也不是对现有 v0.5 权威的替换。

本草案只定义可被未来证据否定的对象和分层关系。任何数值阈值、固定天数、RSI/ATR/ER 参数、证据衰减半衰期、注意力投影数量、覆盖比例、正则系数或风险百分比，若未由冻结协议和相应证据阶段支持，均只能是案例或 `DRAFT_PARAMETER`，不得写成系统事实或运行默认值。

八日经验案例被保留为 `PatternInstance / ANECDOTAL_UNVERIFIED / SEEN_NARRATIVE`：它可以帮助暴露对象缺口、设计反例和提出可证伪问题，但不提供 market support、prior、opportunity universe、development/calibration/holdout role 或行动权限。被拒绝的是把它固定泛化为 `D1-D8` 序列，而不是删除或否认该案例。

## 2. 三类输入的逐项融合决策

| 输入与项目 | 决策 | 理由和本草案处理 |
|---|---|---|
| deep-research-report (1)：可观测代理 | `ADOPT_AS_E0_POLICY_BOUNDARY` | 只允许从可观测数据构造 measure；不把叙事、交易者意图或心理标签伪装成观测事实。 |
| deep-research-report (1)：不可识别边界 | `ADOPT_AS_E0_POLICY_BOUNDARY` | 机制、方向和结构均可为 `UNKNOWN`；数据缺失不能补零或被解释为“无事件”。 |
| 用户贴出的 MSTA-HED 1.0：五层分解 | `ADOPT_WITH_REWRITE` | 改写为 fact/measure、belief、position、mechanism/path、decision/permission 五个对象层；每层均保留 provenance 和不确定性。 |
| MSTA-HED 1.0：三类假说 | `ADOPT_WITH_REWRITE` | 统一为非互斥 primitive mechanism、有限 compound path 和可操作 TradeThesis；三者不得互相替代。 |
| MSTA-HED 1.0：生命周期 | `ADOPT_WITH_REWRITE` | 使用 support、soft contradiction、hard falsifier、expiry 和新 episode；旧 receipt 不可因新 episode 被复活。 |
| MSTA-HED 1.0：有限假说 | `DIRECT_ADOPT` | registry 有限、运行时不可注入新 mechanism/path；`OTHER`/`UNKNOWN` 必须常驻。 |
| MSTA-HED 1.0：证据更新 | `ADOPT_WITH_REWRITE` | 必须由 causal clock、dependency group 去重和 append-only UpdateReceipt 约束；E0 不产生校准概率。 |
| MSTA-HED 1.0：状态/区域/决策 | `ADOPT_WITH_REWRITE` | 状态是多轴 belief，区域是有不确定性的 StructuralPosition，决策还必须经过 scenario、utility 和 permission。 |
| deep-research-report (2)：工程规格 | `ADOPT_WITH_REWRITE` | 采纳其接口化、可重放、fail-closed 方向；具体 adapter、存储、任务编排须以现有 EventStore/Risk/OMS 边界为准。 |
| deep-research-report (2)：历史相似周期 | `HYPOTHESIS_REQUIRES_HISTORICAL_VALIDATION` | 仅作为 past-only comparator challenger；必须冻结特征、距离、候选池、purging/embargo，禁止视觉选图和已知 outcome 选择。 |
| deep-research-report (2)：固定数值策略参数 | `HYPOTHESIS_REQUIRES_HISTORICAL_VALIDATION` | 只能以版本化 `DRAFT_PARAMETER` 进入未来开发；不得由本 E0 文档激活。 |
| 八日固定窗口、1300/1600、RSI 阈值、ATR/ER、固定证据半衰期、3–4 条上限、90% 覆盖、lambda=20、风险百分比 | `REJECT_OR_DEFER` | 未给出可移植定义、数据口径、时间因果和验证门；可保留为案例，不得成为 BTC V1 或任何交易权限。 |
| 当前 2.1/v0.5 的 point-in-time、OTHER、partition proof、permission 分层 | `DIRECT_ADOPT` | v0.5 是当前权威约束：object kind 不可互为别名，只有完整 partition proof 的 path set 才能归一化。 |
| 当前旧 v1 episode/action/G2/paper 链 | `ADOPT_WITH_REWRITE` | 仅作为可复用的测量、研究和 paper 边界；其 episode/state/action 语义不自动等同 MSTA 对象。 |

两份 deep-research-report 都含会话级 turn citation tokens，不是持久 source registry。报告 (1) raw SHA-256 为 `971d3166b756e8dc152d40e74360a806460d8900f408cd338f70a612b4e37f0e`；报告 (2) raw SHA-256 为 `2767fba21b8e63e258ba08f7d4245a9bc6afbca90525eb924b0a7880359bad75`。本文件仅采纳其 E0 边界逻辑；任何外部事实都仍须从可复取的一手来源获得版本/hash 验证，不能以报告 token 取代来源登记。

## 3. 统一方法链

```text
point-in-time fact
  → measure
  → MultiScaleStateBelief
  → StructuralPosition
  → nonexclusive primitive mechanisms
  → finite registered market compound paths + exact residual OTHER_PATH
  → Evidence / UpdateReceipt
  → mutually-exclusive future ScenarioDistribution
  → TradeThesis
  → UtilityReceipt
  → PermissionEnvelope
  → ActionCandidate
  → execution / result
```

前半段是 epistemic state：它描述当时可见数据、测量、解释竞争和未知性。后半段是 operational state：它描述权限、风控、订单、成交、保护、对账和结果。两者不得互相伪造：belief 不能直接下单，订单状态不能倒推机制为真，result 不能回写当时的 fact 或 receipt。

`execution / result` 仅是将来阶段的接口位置；当前 E0 一律输出 `ABSTAIN`，不产生真实或 paper execution。

## 4. 点时事实、measure 与 RoleProfile

一个 fact 至少需要 source identity、原始/派生版本、`available_at`、质量和 provenance。measure 只能使用 `available_at <= decision_time` 的 facts，并说明输入缺失、可重建性和单位。未覆盖 feed 的静默是 `UNKNOWN`，不是零也不是“不存在”。

多周期不用“一个更高周期标签压死所有低周期信息”的模型。使用 RoleProfile：

| Role | 职责 |
|---|---|
| `BACKGROUND` | 慢速背景、长期约束和可用性边界。 |
| `STRUCTURE` | 区域、anchor、主要 range/trend 语境。 |
| `REGIME` | 波动、流动性、杠杆/拥挤、事件环境。 |
| `SETUP` | 可观察的候选条件和结构接近度。 |
| `TRIGGER` | 时间敏感的 transition evidence、quality/risk veto 或 EXIT 证据。 |

BTC V1 的 `1W/1D/4H/1H/15m` 只是候选映射，尚非固定事实。低周期不得静默覆盖高周期；它可以增加 transition evidence，触发 data/risk veto，或在持仓阶段提出 `EXIT`。任何跨 role 冲突必须留在 belief 的 uncertainty/unknown reasons 中。

## 5. MultiScaleStateBelief 与 StructuralPosition

每个 MultiScaleStateBelief 至少表达下列非排他的状态轴：

- `direction`
- `phase`
- `volatility`
- `liquidity`
- `leverage_crowding`
- `event`
- `data_quality`

方向×阶段是描述性 belief，不是市场真值；一个 observation 可以同时支持多个机制，且任何轴均可 unknown。不得强制单标签、不得因为“最可能”而丢弃相冲突的证据。

StructuralPosition/Zone 不是一条线。最小概念包括 `anchor`、`width`、`strength`、`consumption`、`uncertainty` 和相对 `position`。区域中部是否 `ABSTAIN` 只是待检验 policy hypothesis，不能由本文件确认为一般规律。结构位置只给出解释/场景的输入，不直接创建 action。

### 5.1 标准分析卡：多视角 delta matrix

此表只定义本 challenger 相对于现有核心理论所强调的对象边界，不重复制定 CORE 的完整字段表。

| 视角 | 可接受 facts / measures | 可以支持什么 | 不能推断什么 |
|---|---|---|---|
| price structure | 已可用的价格、区间、anchor、位置、transition | StructuralPosition 和预登记路径里程碑 | 单独证明未来方向或入场价值 |
| flow / volume | 点时成交、主动方向代理、量能变化 | 压力/响应的候选 evidence | 交易者意图、吸收已成立或完整市场覆盖 |
| liquidity | 有效 order book、深度、spread、gap/恢复状态 | 流动性状态、执行约束或 data veto | 保证成交、fill 概率或止损必然有效 |
| derivatives / leverage | 已可用 OI、funding、清算/拥挤代理及覆盖语义 | regime 或机制竞争的条件 evidence | 强平因果、未来价格方向或完整清算总量 |
| volatility | 点时波动 measure、range expansion、状态转换 | volatility axis、horizon/uncertainty 条件 | 直接的 TP/SL 数值或方向 alpha |
| event / macro | 版本化、可用时间明确的事件事实 | event axis、risk veto、event-repricing 候选 | 未观测事件的方向叙事或即时交易理由 |
| cross-market | 可审计 venue/contract/clock 对齐后的 measure | 独立确认或质量冲突 evidence | 未对齐市场的 lead-lag、可交易价格或因果结论 |
| data quality | coverage、schema、sequence、freshness、availability | `UNKNOWN`、ABSTAIN、risk/data veto | 支持任一市场机制或以缺失代替零 |
| structural position | 上述 measure 的 versioned anchor/zone/uncertainty 映射 | path antecedent、invalidation、scenario 条件 | 独立生成 ActionCandidate |

## 6. 机制与路径竞争

Primitive mechanism 是非互斥、多标签、不可归一的解释单元。MSTA 候选 library 继续服从 v0.5 的有限 registry 思想，例如 continuation、absorption-reversal、range、liquidity vacuum/cascade、event repricing、`ARTIFACT`、`OTHER`；此列举不等于实证支持。`ARTIFACT` 只是一条独立的 epistemic/data-quality alternative，不是 market compound path，严禁进入 compound-path mixture、ScenarioDistribution market branch 或 utility。

Compound path 是 variable-length 的有限组合对象。它可以拥有 partial order、可 skip milestone、可 repeat milestone、明确 horizon、容量 guard、soft contradiction、hard falsifier 和 expiry。运行时不得注入新 mechanism、动态幂集或未注册 compound path。

只有具有完整、可审计的 partition proof，且各 cell 互斥、穷尽并保留 residual `OTHER` 的 compound-path competition set，才可产生归一的 path weights。primitive support 绝不能当作 mixture weights。UI/attention 可以投影 3–4 条候选，但不得裁剪底层 registry；“90% 覆盖”在没有预定义 universe、coverage measure、成本与失败策略前被拒绝为门槛。

新的 episode 必须有新的 observation frame、path instance 与 receipt chain。hard falsifier 在旧 episode 内不可逆；新的 evidence 只能追加 update，不能改写或复活旧 receipt。

## 7. Evidence、时间和更新

v0.5 exact Evidence carrier 继续按其权威 schema 使用，其中的 `available_at` 等字段不得由本 challenger 静默加键或改义。若需要 source `event_at`，它必须引用对应 source event 或 v0.5 `PathEvent`；若需要 target expiry，则必须引用对应 `MechanismSpec`/`PathSpec` 的 expiry rule。未来若确有承载这些交叉引用的需要，只能以单独、版本化的 `EvidenceAdmissionContext` wrapper 实现，不能改变 v0.5 exact object。

只有 timestamp-aware 的 source/path reference 满足 `event_at <= available_at <= decision_time`，且 target expiry reference 仍有效时，才可接受 evidence 更新 belief。相同 dependency group 对同一目标最多贡献一次；quality failure、未来数据、格式不合法或未覆盖 source 必须拒绝/unknown，而不是转为支持。

`UpdateReceipt` 追加记录 previous belief digest、observation frame、accepted/rejected evidence、dependency aggregation、updated path IDs、新 digest 和 previous receipt hash。late evidence 只能新建 receipt，不能重写前缀。

需要严格分开两种时间语义：

1. 可用性、schema failure、hard falsifier 和 expiry 是可审计的硬状态；
2. 经验权重的衰减是统计/建模选择。

固定指数衰减或“证据半衰期”不能由直觉进入 runtime，须在至少 E2 的预注册验证中证明校准、稳定性和成本收益；E0 仅可保留该问题为 hypothesis。

### 7.1 动态竞争路径算法（future contract）

1. 冻结 ObservationFrame、RoleProfile、StructuralPosition anchor 和 event-time horizon；不以固定天数或 `D1-D8` 取代 horizon。
2. 仅从有限 registry 激活候选 primitive/compound paths，并始终保留 residual market path `OTHER_PATH`；`ARTIFACT` 仅作为独立 epistemic/data-quality alternative，不能进入 compound-path mixture 或 utility。不能因注意力投影而删除底层候选。
3. 对每条 active path 预登记 antecedent、milestones、support rules、soft contradictions、hard falsifiers 和 expiry。
4. 每个新 evidence 先经 causal clock、quality 和 dependency-group admission；随后对每条被指向 path 独立追加 UpdateReceipt。
5. active path 只可因已定义 terminal/success、hard falsifier 或 expiry 退出 active lifecycle。soft contradiction 只能按预登记规则降级，不能静默删除 path；terminal 后拒绝后续该 path 的 PathEvent。证据不足、未覆盖或冲突未消解时返回 `UNKNOWN`，而不是强迫选择。
6. sequence 可为 2、8、20 或任何其他长度；它由已注册的 variable-length partial order、skip/repeat 和 event-time stopping rule 决定，不由日历天数决定。
7. 新 evidence、expiry 或 terminal event 会触发再次更新；late evidence 只追加新 receipt，且不能使 terminal path 接收新的 path event。

该流程在 E0 最多产生 `LEADING_QUALITATIVE`。它不是 probability、交易信号或执行许可。

### 7.2 pathway selection 边界

E0 不能强行输出 top-1。若多个候选之间没有可审计的支配关系，结果必须为 `UNKNOWN` 或 `TIED`；`LEADING_QUALITATIVE` 仅表示在限定证据下的描述性投影。即便某 path leading，它仍可能没有 TradeThesis、没有 utility，或被 data/risk/permission veto。

只有未来 E2，且仅在合法的、完整 partition proof 的 competition set 上，才可讨论 calibrated path weights、margin 与 entropy。primitive support 永远不得被归一化为 path probability。

## 8. 概率、交易成功、fill、utility 与权限

下列概念不得合并：

- path belief：解释竞争的认识状态；
- ScenarioDistribution：未来情景的互斥、穷尽分布；
- trade success：行动特定的未来市场结果定义；
- fill：执行/流动性事件；
- EV/utility：结合情景、成本、尾部和约束后的决策量。

E0 只允许 qualitative state 或 synthetic counterfactual。它不产生市场校准概率、真实交易成功率、fill 估计或可执行 EV；PermissionEnvelope 必须为无新增风险，ActionCandidate 必须投影为 `ABSTAIN`。

未来校准应以 proper score、reliability、成本压力、尾部风险和权限一致性共同评价；calibration 后的 path weight、scenario、fill 和 utility 仍须保持不同 artifact 与不同适用范围。

## 9. 历史相似周期 challenger

历史相似周期不是证据捷径。它只能是 `past_only_comparator_challenger`：先在 outcome 不可见时冻结特征版本、距离函数、候选池、时间排序、purging、embargo、相似窗口重叠规则和报告指标；随后才在授权的 DEVELOPMENT/CALIBRATION/HOLDOUT chronology 内评价。禁止凭图形视觉选取、将已知 outcome 引入候选池，或把相似对象直接变成 active-path posterior。

## 10. TradeThesis 与动态 entry / SL / TP 边界（future contract）

TradeThesis 不是 path 的别名。未来一个可审查 thesis 至少需要：RoleProfile premise、StructuralPosition、trigger、情景/utility/cost/risk/permission 引用和明确的 invalidation。所有条件的 EntryZone 必须相交；交集为空、未知或未经 permission 时为 `ABSTAIN`。

- stop 必须锚定 structure hard invalidation 加上版本化、待验证的 buffer；buffer 不是本 E0 文档能确定的数值。
- target 必须来自预登记 scenario 或 zone transition rule；不能在结果可见后改变目标定义。
- 持仓后的动态管理只可按预先规则 `TIGHTEN`、`REDUCE` 或 `EXIT`；stop 不得向扩大风险方向移动，horizon 不得延长。
- target 的动态调整必须有预注册条件、cost/tail/permission 约束和 receipt；不能以“看起来更强”临场延展。
- path top 改变不得自动反手；反向方向必须建立新的 thesis、opportunity 和 permission，并通过独立 risk approval。

这些是未来 contract 边界，不是当前交易授权。E0 不创建 entry、stop、target 或 position。

## 11. 待证假说

| ID | E0 可陈述的候选命题 | 成功条件 | 失败条件 | 最早证据阶段 |
|---|---|---|---|---|
| `V6-H01` | RoleProfile 分层比单一时间标签更少产生未解释冲突。 | 预注册 OOS reliability/coverage 改善且无成本恶化。 | 无改善、冲突隐藏或复杂度收益不成立。 | E2 |
| `V6-H02` | StructuralPosition 的 uncertainty/consumption 字段改善 scenario calibration 或 abstain safety。 | 相对同信息 baseline 的 proper score/尾部风险改善。 | 无校准或风险改善。 | E2 |
| `V6-H03` | dependency-group 去重降低过度自信。 | reliability/entropy 改善，且覆盖不恶化。 | 无改善或机会成本过高。 | E2 |
| `V6-H04` | finite variable-length partial-order paths 优于固定顺序模板。 | OOS 稳定性或 proper score 的净提升超过复杂度成本。 | 无增益或路径注册失效。 | E2 |
| `V6-H05` | `OTHER/UNKNOWN/ABSTAIN` 在未覆盖状态降低尾部错误。 | 尾部改善超过预注册机会成本。 | forced-choice 更优或 abstain 成本过高。 | E2 |
| `V6-H06` | 低周期 transition evidence 在不覆盖高周期 belief 的前提下改善 risk/exit conditioning。 | 预注册的风险/退出指标改善，无方向泄漏。 | 无改善或造成覆盖漂移。 | E2 |
| `V6-H07` | past-only comparator challenger 提供独立增量，而不是视觉模式挖掘。 | 严格 purged OOS 优于同信息 frozen baseline。 | 无增量、泄漏或选择偏差。 | E2 |
| `V6-H08` | 经验衰减在冻结版本中改善校准而不损害稳定性。 | 预注册 proper score/reliability 与压力成本门通过。 | 无改善或参数敏感。 | E2 |

## 12. 参考资料与证据边界

这些资料是概念与方法背景，不是对 MSTA-HED 有效性的证据：

- [Hamilton, 1989, regime switching](https://doi.org/10.2307/1912559)
- [Kaelbling, Littman and Cassandra, 1998, POMDP planning](https://doi.org/10.1016/S0004-3702(98)00023-X)
- [Cont, Kukanov and Stoikov, order book events](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822)
- [Gneiting and Raftery, proper scoring rules](https://doi.org/10.1198/016214506000001437)
- [White, reality check](https://doi.org/10.1111/1468-0262.00152)
- [Adams and MacKay, Bayesian online change point detection](https://arxiv.org/abs/0710.3742)
- [Niculescu-Mizil and Caruana, calibrated probabilities](https://doi.org/10.1145/1102351.1102430)
- [Binance developer documentation](https://developers.binance.com/docs)
- [OKX API v5 documentation](https://www.okx.com/docs-v5/en/)
- [Bybit v5 order book documentation](https://bybit-exchange.github.io/docs/v5/market/orderbook)

## 13. 当前结论

本草案的唯一当前输出是：`ABSTAIN / AWAITING_SOL_STAGE_GATE`。通过文档审查、synthetic fixture 或静态 contract test 均不构成数据有效、理论成立、校准完成、执行就绪或交易授权。
