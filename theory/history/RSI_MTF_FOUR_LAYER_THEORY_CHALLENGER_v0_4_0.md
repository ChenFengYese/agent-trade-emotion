# RSI-MTF Four-Layer Theory Challenger v0.4.0

> 状态：`E0 / OUTCOME_FREE_THEORY_DRAFT`
>
> 日期：2026-07-26
>
> 允许声明：本文件定义了可观测、可重放、可反证的四层市场分析方法候选与未来验证顺序。
>
> 禁止声明：市场有效、预测有效、成本后盈利、paper 可用、实盘可用、自动化交易授权，或对 v0.2.2/v0.3 的自动晋级。

## 0. 身份、证据等级与冻结依赖

本文件是独立的理论 challenger；它不修改、不替换、不解释为已整合下列冻结对象：

| 依赖 | 角色 | 变更权限 |
|---|---|---|
| `RSI_MTF_DRL_PM.v0.2.2` | 当前 champion 理论与权限边界；semantic `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`；authority `9b2446de9e0549579d52bc8ce2bc3bd124885203a52855f0dbf0f1324f9f1295`；route `631f8187e9eb81465718156736045c3ca5cc7ec5e33bbba7b063354cefeb792c`；strategy `26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc` | 禁止 |
| `RSI_MTF_DRL_PM_THEORY_CHALLENGER.v0.3.0` | 单层趋势、订单流、结构、几何、退出的外部研究 challenger | 禁止 |
| 活动 G1 package/plan/registry/evidence | 既有 forward 证据轨道 | 禁止 |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | 本文的机械方法合同 | 本文唯一规范来源 |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | 本文的假设、比较器、反证和状态 | 本文唯一注册来源 |

`E0` 的含义是：此处只有理论、字段、因果边界和可证伪路线，尚无本项目历史 outcome、回测、校准、holdout、paper 或 live 证据。所有功能性主张当前均为 `NOT_RUN` 或 `WAIT_DATA`。

本文件不把“宏观、情绪、K 线、相似走势或做市商叙事彼此吻合”视为市场证据。理论准入仍遵循：

```text
来源或问题
  → 可解释机制
  → decision-time 可观测量
  → 唯一机械规则
  → 可被历史或未来数据反证的预测
```

任一环节缺失，输出只能是研究笔记、`UNKNOWN` 或 `ABSTAIN`。

## 1. 四层不是加权器，而是分离的证据角色

系统应把不同来源的信息保持为可单独失效、可单独缺失、可单独比较的层，禁止先拼成不可解释的“综合评分”。

| 层 | 名称 | 可观测角色 | 初始允许作用 | 明确禁止 |
|---|---|---|---|---|
| L1 | 当前压力/数据面 | causal trades、盘口/价差、可见容量、资金费率、OI、basis、实现波动、数据新鲜度 | 确认、否决、执行风险或 `ABSTAIN` | “主力意图”“做市商必然守价” |
| L2 | 周期状态面 | 1W/1D/4H/1H/15m 的已闭合 TFState | 主结构、回撤/反弹、位置和风险上下文 | 用未来走势给当前周期贴标签 |
| L3 | 历史相似面 | past-only、embargoed AnalogEpisode | 独立的条件概率 challenger | 用 outcome 相似性、未来样本或重叠样本找类比 |
| L4 | 宏观事件面 | 时间戳、发布版本、预期、实际、修订状态 | 风险/冲突门、`ABSTAIN` 候选 | 用事后修订值解释过去，或直接把新闻叙事当方向订单 |

每层必须保留独立的：来源、`available_at`、缺失状态、规则版本、比较器、反证条件和证据等级。L1–L4 不能通过未冻结的权重相加，也不能用“多层一致”代替独立增量验证。

## 2. 五周期职责和邻接父子关系

时间周期不是依据行情任意选择。它们的职责预先固定，并只读取满足完整可见性不变量的数据：`is_closed` 必须是 exact JSON boolean `true`；`source_timestamp`、`close_time`、`available_at` 和 `decision_time` 必须均存在、合法、带时区且可比较；并且 `source_timestamp <= decision_time`、`close_time <= decision_time`、`available_at <= decision_time`。任何缺失、畸形或不可比较的时间戳，或字符串/数字/null 等伪布尔 `is_closed`，均 fail-closed 为 `DATA_INVALID → UNKNOWN/ABSTAIN`。`source_sequence` 只可在同一 `(source_id, generation_id/stream_id)` 内比较；跨源同 `available_at` 是无经济先后的 batch，任何不可交换结果为 `UNRESOLVED/STOP_FIRST`。canonical replay 可使用稳定 tie-break，但它只为序列化，绝无市场时序含义；缺少或冲突的证明首先标记 `DATA_INVALID`，再 fail-closed 为 `UNKNOWN/ABSTAIN`。

统一 record identity 必填：`source_id / generation_id_or_stream_id / source_sequence / stable_input_id / source_timestamp / available_at / record_version`。不同 generation/stream 的 sequence 不可比较；identity 缺失、重复或冲突直接 `DATA_INVALID`。`stable_input_id` 只服务 canonical replay/序列化，不具经济顺序。

| 周期 | 固定职责 | 不能做什么 |
|---|---|---|
| `1W` | 长期风险背景、异常扩展、宏观敏感度 | 精确点位、短线下单 |
| `1D` | 长期结构背景和大区间 | 替代 15m 触发 |
| `4H` | 唯一 operational `StructuralRegime` 与因果结构区间来源 | 未验证的顺势 continuation 下单 |
| `1H` | setup：局部冲量、回撤/反弹、冲量变化 | 覆盖 4H 的风险否决 |
| `15m` | RSI `OBSERVE`、决策时钟和执行时机输入 | 单独定义市场大趋势 |

合法父子链是：

```text
1W ↔ 1D ↔ 4H ↔ 1H ↔ 15m
```

规则如下：

1. 子周期只能读取相邻且合格的父周期 `TFState`；禁止跳级覆盖或全周期投票。
2. `4H` 是唯一可以设定 operational `StructuralRegime` 的周期。
3. `1W/1D` 可触发风险 veto，但不能创建 entry；`1H/15m` 不能覆盖 `4H` 结构方向。
4. 父子冲突、父周期 `UNKNOWN`、数据陈旧或缺口不能由子周期“票数更多”解决；默认 `ABSTAIN`。
5. 未来最大持有时间是冻结的状态函数，而非观察结果后改选的周期：

```text
MaximumHoldingHorizon =
  FrozenHorizonTable[StructuralRegime, LocalImpulse,
                     volatility_state, EntryType]
```

表中的窗口、阈值、确认长度和切换滞后必须在未来 DEVELOPMENT 前冻结；本文件不假装它们已经被市场验证。

## 3. 最小、正交、可观测的状态向量

不使用互相重叠的“上涨中见顶”“下跌中止跌”等大串主观标签。每个时点只生成下列正交向量：

```text
TFState(tf, t) =
  [timeframe, DataQuality, StructuralRegime,
   normalized_velocity, directional_efficiency, kinematics,
   volatility_state, trailing_location, state_age,
   close_time, available_at, measurement_version, provenance]

DecisionState(t) =
  [TFState(1W), TFState(1D), TFState(4H), TFState(1H), TFState(15m),
   parent_child_relation, MacroCondition, LocalImpulse,
   CurrentPressureContext, Confirmation, provenance]
```

| 分量 | 枚举 | 可观测含义 |
|---|---|---|
| `DataQuality` | `VALID / STALE / GAP / CONFLICT / DATA_INVALID / UNKNOWN` | 可得时间、序列连续性、字段冲突和来源证明；它绝不是方向 |
| `MacroCondition` | `QUIET / SCHEDULED_RISK / RELEASE_SHOCK / REVISION_CONFLICT / UNKNOWN` | 已知日历、已发布冲击及版本问题，不是新闻方向预测 |
| `StructuralRegime` | `UP / DOWN / RANGE / TRANSITION / UNKNOWN` | 4H 已闭合结构的唯一互斥主状态；绝不含 `DATA_INVALID` |
| `normalized_velocity` | 冻结的带符号、波动归一化速度 | 仅由因果观测计算，不是未来趋势分数 |
| `directional_efficiency` | 冻结的方向路径效率 | 区分直线推进与噪声路径，不包含未来极值 |
| `kinematics` | `ACCELERATING / STEADY / DECELERATING / UNKNOWN` | 因果速度变化，不意味着未来延续/反转 |
| `volatility_state` | `CONTRACTING / NORMAL / EXPANDING / SHOCK / UNKNOWN` | 事前波动状态，独立于方向 |
| `trailing_location` | 相对冻结结构区与 trailing range 的因果位置 | `BALANCED / EXTENDED_UP / EXTENDED_DOWN / AT_CAUSAL_ZONE / UNKNOWN` |
| `state_age` | 当前因果状态已持续的 bar 数/时长 | 不能回看结果后重写起点 |
| `parent_child_relation` | `ALIGNED / COUNTERTREND / RANGE_NESTED / RANGE_EXCURSION / TRANSITION / UNKNOWN` | 相邻父子 TFState 的关系，不是单周期方向 |
| `LocalImpulse` | `ALIGNED / COUNTER / FLAT / UNKNOWN` | DecisionState 中的局部冲量相对 4H 主状态 |
| `CurrentPressureContext` | `ORDERLY / HIGH_VOL / THIN / DISLOCATED / UNKNOWN` 等可观察压力/流动性结果 | 与 TFState 分离，不能叙事化为主力意图 |
| `Confirmation` | `NONE / REVERSAL_CANDIDATE / CONTINUATION_RISK / EXECUTION_READY / UNKNOWN` | 只描述已满足的观察条件；非预测标签 |

任何阈值、指标窗口、结构识别算法、状态转移滞后长度和确认 bar 数均属于待冻结 measurement contract；不得在看到收益后调参。状态记录为 append-only，不能用后来价格改写过去状态。只有在相邻 parent/child 的有效状态、时间证明和冻结 hysteresis 都通过时允许状态转移；否则保留此前已记录状态并将当前 DecisionState 标为 `UNKNOWN/ABSTAIN`，而不“猜测平滑”。

### 3.1 用户趋势词的机械映射

| 交易语言 | 唯一机械映射 | 不能推断的内容 |
|---|---|---|
| 上涨周期 | `UP` | 必然继续上涨 |
| 下跌周期 | `DOWN` | 必然继续下跌 |
| 震荡周期 | `RANGE` | 必然均值回归 |
| 下跌中震荡 | `DOWNTREND_RANGE_NESTED = 4H=DOWN + parent_child_relation=RANGE_NESTED + 1H directional_efficiency/state_age` | 下跌已结束 |
| 下跌中反弹 | `4H=DOWN + parent_child_relation=COUNTERTREND + 1H normalized_velocity>0` | 已确认底部 |
| 下跌中止跌 | `4H=DOWN + COUNTERTREND + 1H kinematics=DECELERATING + trailing_location=AT_CAUSAL_ZONE + REVERSAL_CANDIDATE` | 底部或 LONG 权限 |
| 下跌中加速 | `4H=DOWN + ALIGNED + 1H kinematics=ACCELERATING + volatility_state∈{NORMAL,EXPANDING}` | 可以追空 |
| 下跌中减速 | `4H=DOWN + 1H kinematics=DECELERATING`，方向效率/状态年龄仍独立记录 | 必然反转 |
| 上涨中回落 | `4H=UP + parent_child_relation=COUNTERTREND + 1H normalized_velocity<0` | 已确认顶部 |
| 上涨中震荡 | `UPTREND_RANGE_NESTED = 4H=UP + parent_child_relation=RANGE_NESTED + 1H directional_efficiency/state_age` | 上涨已结束 |
| 上涨中见顶 | `4H=UP + COUNTERTREND + 1H kinematics=DECELERATING + trailing_location=AT_CAUSAL_ZONE + REVERSAL_CANDIDATE` | 顶部或 SHORT 权限 |
| 上涨加速 | `4H=UP + ALIGNED + 1H kinematics=ACCELERATING + volatility_state∈{NORMAL,EXPANDING}` | 可以追多 |
| 上涨减速 | `4H=UP + 1H kinematics=DECELERATING`，方向效率/状态年龄仍独立记录 | 必然下跌 |
| 突破风险 | `trailing_location=AT_CAUSAL_ZONE + parent_child_relation∈{RANGE_EXCURSION,ALIGNED} + CONTINUATION_RISK` | 自动 continuation 订单 |

`POTENTIAL_TOPPING`、`POTENTIAL_BOTTOMING` 只是实时可观测候选，不能成为事后确认的“顶/底”标签。首轮 `CONTINUATION_RISK` 一律默认 `ABSTAIN`，直到独立 continuation 假设、EntryZone、ExitPolicy 和验证均完成。

### 3.2 纯因果测量、有限候选族与状态转移

对任一合格 closed bar，仅允许如下因果计算（`epsilon > 0` 是冻结常数）：

```text
r_t       = log(close_t / close_{t-1})
ATR_n(t)  = causal ATR over eligible closed bars
RV_n(t)   = sqrt(sum(r_i^2)) over eligible closed bars
scale_t   = max(ATR_n(t), close_t * RV_n(t), epsilon)
v_n(t)    = (close_t - close_{t-n}) / scale_t
de_n(t)   = abs(close_t - close_{t-n})
            / max(sum(abs(close_i-close_{i-1})), epsilon)
a_n(t)    = v_n(t) - v_n(t-n)       # 两个 velocity window 不得重叠
loc_t     = (close_t-z_low)/max(z_high-z_low, epsilon)
```

`z_low/z_high` 必须来自冻结的因果 `StructuralZone`。布尔分类结构为：

```text
UP          := v_n >= theta_v and de_n >= theta_de and 本TF hysteresis完成
DOWN        := v_n <= -theta_v and de_n >= theta_de and 本TF hysteresis完成
RANGE       := -theta_v < v_n < theta_v and de_n < theta_de and 本TF hysteresis完成
TRANSITION  := DataQuality=VALID 下其余交叉区，或本TF hysteresis未完成；
               parent-child conflict 仅属于 DecisionState.parent_child_relation
UNKNOWN     := candidate tuple 未冻结，或必填时序/字段/质量无效
```

在任何 outcome 可见前，只可冻结最多八组完整 candidate tuple：

```text
(n, theta_v, theta_de, extension_band, hysteresis_length,
 volatility_window, ATR_or_RV_choice, volume_baseline_method,
 weekday_or_session_adjustment, central_range_band, epsilon)
```

每组 tuple 必须恰好包含上述全部字段，且按数值规范化后的语义全族唯一；数值相等的 `1/1.0`、`-0.0/0.0` 必须视为重复。`n/hysteresis_length/volatility_window` 为正整数，`theta_v>0`、`theta_de∈[0,1]`、`epsilon>0`，所有数值有限，band 为非负且端点有序，三个方法字段只取 method contract 冻结枚举。缺键、多键、第九组、语义重复 tuple、NaN/Inf、负 scale/band 或逆序端点均整族 fail-closed 为 `DATA_INVALID/UNKNOWN`。

最小有效参数域同样冻结：`theta_v` 有限且 `>0`；`theta_de` 有限且 `0<=theta_de<=1`；`directional_efficiency` 必须有限并位于 `[0,1]`；`n/h/volatility_window` 是正整数；`epsilon` 有限且 `>0`；所有 band/scale 必须有限、顺序合法并在适用时非负。任一非法域直接 `DATA_INVALID/UNKNOWN`，且不计算 `StructuralRegime`。

禁止无限网格、在线调参、结果条件替换、参数混合或未冻结时输出信号。若没有完整冻结 tuple，所有依赖它的状态都是 `UNKNOWN`。

状态转换必须机械执行：`TRANSITION := DataQuality=VALID AND (remaining cross-region OR this-TF hysteresis incomplete)`；新 `UP/DOWN/RANGE` 要求相同候选连续 `h` 个合格 bar；既有状态失去保留条件先进入 `TRANSITION`，不能立即跳到相反方向；`state_age` 从首个确认 bar 计数。只有本 TF 非 `VALID` 或未冻结/非法 tuple 才使 TFState `UNKNOWN`。parent-child conflict/UNKNOWN 只在 DecisionState 阻止新的 `EVALUATE_REVERSAL/EXECUTION_READY`，绝不重写 TFState，也不能压过已有仓位所需的 `HALT/EXIT/MANAGE_ONLY`。

## 4. 八个可观测对象

### 4.1 TFState

`TFState` 是某一个合格已闭合周期的对象，不是单一状态标签。其必填字段为：`timeframe`、`DataQuality`、`StructuralRegime`、`normalized_velocity`、`directional_efficiency`、`kinematics`、`volatility_state`、`trailing_location`、`state_age`、`close_time`、`available_at`、`measurement_version` 与 `provenance`。`DataQuality=DATA_INVALID` 只表示数据不可用，绝不能污染 `StructuralRegime` 的方向枚举。禁止包含未来收益、未来极值、未闭合 K 线 high/low/close 或人工画线标签。

`DecisionState`/`MarketState` 是五个相邻 TFState 的聚合对象，才承载 `MacroCondition`、`LocalImpulse`、`parent_child_relation`、`CurrentPressureContext`、`Confirmation` 和全链路 provenance。任一 required TFState 无可证明时序，或其 `DataQuality` 不是 `VALID`（`STALE / GAP / CONFLICT / DATA_INVALID / UNKNOWN`），该 DecisionState 不能产生 `EVALUATE_REVERSAL` 或 `EXECUTION_READY`。

### 4.2 CurrentPressureContext

`CurrentPressureContext` 是 L1 当前市场事实：因果交易/订单流（若有连续合格数据）、价差、可见容量、资金费率、OI、basis、实现波动和 freshness。它不包含“巨鲸意图”“吸筹”“控盘”或“情绪真值”等不可观测断言；L1 只可确认或否决 L2 已许可候选，绝不能单独创建方向。

字段族必须分别处理 missingness，不能捏合成“中性情绪”：trade/order-flow 缺失或 stale 时其分支 `UNKNOWN/ABSTAIN`；funding 缺失不能补零；OI 缺失不能由价格推断；basis 缺失或合约不匹配是 `CONFLICT/UNKNOWN`；spread 缺失阻断 `LiquidityFeasibleZone`；depth sequence gap 对 depth 分支是 `DATA_INVALID`，且可见深度不等于成交保证；realized volatility 缺失阻断风险几何；任一字段超过冻结 freshness 上限即 `STALE`。若 L2 连续订单簿不合格，依赖微观结构的分支只能 `UNKNOWN` 或 `ABSTAIN`。

### 4.3 MacroEvent

`MacroEvent` 至少包含：`event_time`、`source_timestamp`、`published_at`、`available_at`、`vintage_id`、实际值（若当时已发布）、预期（若可得）、修订状态。`source_timestamp` 是来源 provenance 时间，不等同于对外公开的 `published_at`；两者与 `available_at`、`decision_time` 均须存在、合法、带时区、可比较，且分别不晚于 `decision_time`。任一缺失、畸形、不可比较或未来时间均 `DATA_INVALID → UNKNOWN/ABSTAIN`。过去时点只能读取当时已知版本；未能证明发布时间或遇到修订冲突时输出 `UNKNOWN/ABSTAIN`。初期仅作为风险门，不能把“利好/利空”叙事直接转换成方向订单。

### 4.4 AnalogEpisode

`AnalogEpisode` 是 L3 的 past-only 候选：检索表示必须冻结，episode 结束时间必须早于 `t - embargo`，不得含预测目标或结果字段。它至少要与下列对照比较：时间匹配随机 episode、regime 匹配简单基线、无 analog 基线。未来样本、重叠样本、按 outcome 选邻居和事后改 query 都是硬失败。

### 4.5 两级概率：MarketScenario 与 ActionOutcome

第一层 `MarketScenario` 是 pre-trade、预注册 horizon 上对竞争市场路径的概率向量：

```text
[P(UPSIDE), P(DOWNSIDE), P(RANGE), P(UNRESOLVED)] = 1
```

`UPSIDE/DOWNSIDE/RANGE/UNRESOLVED` 是冻结 horizon `H`、barrier `B_up/B_down` 与 `central_range_band` 下严格互斥且对有效数据穷尽的市场路径标签：`UPSIDE/DOWNSIDE` 要求事件流可排序，分别为上/下 barrier first；`RANGE` 要求 H 内两 barrier 均未触及，且 terminal displacement 与 realized range 都落入冻结 central range band；`UNRESOLVED` 是数据有效但 neither-first 且不满足 RANGE，或两 barrier 同窗触及而缺少顺序证据。`UNKNOWN/DATA_INVALID` 是模型或数据无效输出，不参与归一；`ABSTAIN/NO_TRADE` 只属于 Action。

第二层 `ActionOutcome(action | submission)` 是每个候选动作在已提交条件下的联合结果向量：

```text
[P(NO_FILL), P(TP_FIRST), P(SL_FIRST),
 P(STRUCTURE_EXIT), P(TIMEOUT)] = 1
```

两层都要求归一、support count、置信区间、Brier、log loss、reliability bins；MarketScenario 另报告 calibration slope/intercept。每个概率必须是 `[0,1]` 内有限 JSON number，JSON boolean `true/false` 不能充当数值。提交时冻结 immutable 五分支 prediction，并独立记录 `observed_fill=true|false|null`、`observed_action_outcome=五分支之一|null` 与 `DataDisposition`；`observed_fill` 必须具有精确 JSON boolean/null 类型，数值伪布尔 `1/0/1.0/0.0` 必须拒绝。`P(fill)=1-P(NO_FILL)` 只在 observed_fill 非 null 的 denominator 评分；五分支 joint Brier/log-loss 只在唯一 terminal outcome 已知时评分；filled-cohort 分布只在 `observed_fill=true` 且 terminal 已知时评分。`CENSORED/DATA_INVALID/OPERATIONAL_OVERRIDE` 不得改写 prediction、伪造 `NO_FILL` 或 terminal；缺标签只排除对应 score denominator，同时按 disposition 与 pre/post-fill 报告全部 denominator/count。初始候选仅为特征冻结后的 multinomial logistic regression 与冻结校准。方向概率本身不能下单：候选动作只有在成本后 `EV` 的下置信界大于冻结的 `ABSTAIN/NO_TRADE`（或现仓 `IMMEDIATE_EXIT`）动作比较器、并同时通过数据/风险/执行门时，才可进入未来的 `EXECUTION_READY` 合同。状态/分支支持不足、概率不归一或尚未建立校准时，输出 `UNKNOWN` 或 `ABSTAIN`，不能伪造确定性方向。

概率校准是所有会输出 `MarketScenario` 或 `ActionOutcome` 的假设的横向 measurement requirement，不是独立 L1/L2 alpha 假设，也不能把 L1 当前压力和概率公式混成同一次增量检验。

### 4.6 EntryZone

点位不是单一神秘价格，而是由冻结且因果的 `StructuralZone=[z_low,z_high]`、venue tick 规则和 decision-time 流动性/风险约束生成的提交时 tick-aligned 区间：

```text
EntryZone(t) =
  StructuralZone(t)
  ∩ LiquidityFeasibleZone(t)
  ∩ RiskGeometryZone(t)
  ∩ VenueRuleZone(t)
```

`StatePermissionGate={ALLOW,DENY}` 是真正二值门且没有价格坐标。`UNKNOWN` 或无效质量在进入 gate 前已 fail-closed 为 `UNKNOWN/ABSTAIN`；任何非法 gate value 必须拒绝。只有 `ALLOW` 才允许上述四个价格区求交；`DENY` 强制空区间和 `ABSTAIN`。状态、宏观和概率只能许可/否决，不能生成或移动价格坐标。任一交集为空均为 `ABSTAIN`。可见深度不等于 guaranteed fill；其只能成为需要验证的容量代理。初始几何须在提交前以冻结公式确定：

```text
SL0_long  = tick_align_down(structural_invalidation_long - tail_buffer)
SL0_short = tick_align_up(structural_invalidation_short + tail_buffer)
TP0_long  = tick_align_up(entry + R * (entry - SL0_long))
TP0_short = tick_align_down(entry - R * (SL0_short - entry))
H0        = FrozenHorizonTable[DecisionState, EntryType]
q0        = min(risk_budget / abs(entry - SL0), venue_max_size,
                causal_liquidity_cap)
```

`TP0` 也可由预先冻结的因果结构目标定义，但不能在二者之间观察结果后切换。若 `q0` 不符合 venue、容量或账户硬风险，必须 `ABSTAIN`。

### 4.7 Action

`Action` 只能是：`UNKNOWN / OBSERVE / ABSTAIN / HALT / EVALUATE_REVERSAL / EXECUTION_READY / MANAGE_ONLY / EXIT`。RSI 只能产生 `OBSERVE`：

```text
RSI extreme → OBSERVE
RSI extreme ≠ LONG, SHORT, EXECUTION_READY
```

RSI 生命周期把 immutable `episode_id/creation_record`、可变 `active/eligible_for_upgrade`、`new_observe_emitted: bool` 与合法 `Action` 分离。新 cross 只有在 `cross_valid=true`、`DataQuality=VALID`、parent valid、candidate gates pass 且非 terminal 时才创建 episode、令 emission=true 并输出 `OBSERVE`；任一创建门失败都不得产生 episode。创建时与 same-bar 的 `eligible_for_upgrade=false`。持续极值保持 emission=false、不重复 episode。更晚 bar 的唯一升级是 `EVALUATE_REVERSAL`，并且必须同时满足 active、`eligible_for_upgrade=true`、unexpired、严格更晚的 eligible closed bar、质量/parent/candidate gates 和无 terminal。expiry、质量失败、parent invalidation 或 terminal 必须保留 identity 审计记录但令 `active=false/eligible_for_upgrade=false`；已有 inactive record 却缺少 termination proof 时输出 `UNKNOWN/LIFECYCLE_PROOF_MISSING`。same-bar 与 termination 后均不得升级；其他证明缺失时 fail-closed 为 `ABSTAIN`，但不压过既有仓位需要的 `HALT/EXIT/MANAGE_ONLY`。

### 4.8 ExitPolicy

每个精确 submission/fill cohort 必须在入场前冻结：`entry_zone`、`structural_stop`、`tail_buffer`、`target_set`、`maximum_holding_time`、成本/滑点/延迟情景。动态管理只允许 `TIGHTEN_STOP / REDUCE_EXPOSURE / EXIT / KEEP_FROZEN`，并满足单向降风险：

1. 不得扩大最坏损失或放宽保护止损；
2. 不得延长最大持有期；
3. 不得因目标未到而无边界外移；
4. 数据、宏观或流动性恶化只能收紧、减仓、退出或 `HALT`；
5. 同一 OHLC 内 TP/SL 先后不明时，必须 `STOP_FIRST`；
6. H06/H05 类退出比较必须保留相同 submission/fill cohort。

单调规则写为：

```text
SL_long(t+1)  = max(SL_long(t), frozen_causal_protective_level(t))
SL_short(t+1) = min(SL_short(t), frozen_causal_protective_level(t))
H(t+1) <= H(t)
EXIT if LCB(EV_hold_remaining | exact_fill_cohort, DecisionState_t)
        <= EV_immediate_exit_after_cost
```

`PRE_LOCK` 目标只可在 submission 前由冻结几何设定；进入仓位后的 `POST_LOCK` 目标只能保持、收紧、部分实现或退出，绝不可仅因尚未成交而外移。运行中禁止修改权重、阈值、特征版本、路径名称或任何概率类别。

## 5. 唯一决策链和动作优先级

```text
VERIFY_DATA_AND_TIME
  → BUILD_ADJACENT_TFSTATE_CHAIN
  → CLASSIFY_CURRENT_PRESSURE_AND_MACRO_CONTEXT
  → RSI_EMITS_OBSERVE_ONLY
  → CONSTRUCT_MARKETSCENARIO_AND_ACTIONOUTCOME_OR_UNKNOWN
  → CHECK_STATE_PERMISSION_AND_ENTRYZONE_INTERSECTION
  → FREEZE_INITIAL_EXIT_POLICY_AND_RISK_GEOMETRY
  → SELECT_ACTION_BY_PRIORITY
  → RECORD_PROVENANCE_AND_RESULT_STATUS
```

固定优先级为：

```text
HALT（账户、venue 或数据安全失败）
→ EXIT（已有仓位且触发保护退出）
→ MANAGE_ONLY（已有仓位且无需退出）
→ UNKNOWN（新动作所需输入或时间证明缺失）
→ OBSERVE（RSI 事件）
→ ABSTAIN（有效但冲突、支持不足、成本/风险不成立或区间为空）
→ EVALUATE_REVERSAL（候选条件齐备）
→ EXECUTION_READY（仅在未来独立执行合同及权限均通过后）
```

这意味着强信号、宏观叙事、相似周期或任何单层结论都不能绕过数据完整性、风险几何和冻结权限。

## 6. 场景路径、入场、TP/SL 的理论边界

对每个有效时点，系统不是寻找一个“唯一正确剧本”，而是维护 mutually exclusive competing market paths：`UPSIDE / DOWNSIDE / RANGE / UNRESOLVED`。`ABSTAIN/NO_TRADE` 是动作而非市场路径。若概率尚未校准、状态支持不足、宏观版本不确定、父子周期冲突或 EntryZone 为空，则正确落点是 `UNKNOWN` 或 `ABSTAIN`。

初期只允许均值回归候选的例子：

| 条件组合 | 允许输出 | 禁止输出 |
|---|---|---|
| `RANGE + AT_CAUSAL_ZONE + REVERSAL_CANDIDATE` | `EVALUATE_REVERSAL` 候选 | 自动下单 |
| `UP + COUNTER` | 顺势回撤 LONG 的评估候选 | 仅因 RSI 超卖立即 LONG |
| `DOWN + COUNTER` | 顺势反弹 SHORT 的评估候选 | 仅因 RSI 超买立即 SHORT |
| `UP/DOWN + ALIGNED + ACCELERATING` | `ABSTAIN` | 追随 continuation |
| `TRANSITION/HIGH_VOL/THIN/DISLOCATED/RELEASE_SHOCK` | 收窄风险或 `ABSTAIN` | 放大仓位或放宽止损 |

具体开仓点、止盈点、止损点和持有期只可由冻结 `EntryZone + ExitPolicy + risk budget` 生成，不能由自然语言标签直接生成。动态调整是“重算剩余风险与退出”，不是在浮亏时不断改变原始理论。

### 6.1 日线冲击—压缩前缀的价格假设（V4-H10/H11）

用户描述的“巨量下跌长上影/近低收盘→缩量压缩→缩量反弹→放量上涨→消息冲高→两日新高十字/转弱→暴跌”不是可直接交易的事实链。它被保留为独立 P1 候选，且只能使用每日 close 后可得的 OHLCV 与具有 `published_at / available_at / vintage_id` 的事件记录。第 8 日的信息绝不能回写第 1–7 日状态。

日线 anatomy 的唯一候选计算是：

```text
r_d        = log(close_d / close_{d-1})
body_d     = abs(close_d-open_d)
range_d    = high_d-low_d
CLV_d      = (2*close_d-high_d-low_d)/max(range_d, epsilon)
upper_wick = high_d-max(open_d, close_d)
lower_wick = min(open_d, close_d)-low_d
range_ATR  = range_d/max(causal_ATR_n(d), epsilon)
logV_d     = log(max(volume_d, epsilon))
robustVol_d= (logV_d-rolling_median_n(logV)) / max(MAD_n(logV), epsilon)
             # 或单独冻结的 EWMA baseline；均值/标准差绝非唯一基线
gap_d      = (open_d-close_{d-1})/max(close_{d-1}, epsilon)
open≈low   := abs(open_d-low_d) <= frozen_tick_or_scale_tolerance
```

“新高/新低”只相对 trailing、eligible、此前已闭合 high/low 定义。任何 cohort 的 exact key set 必须是 `asset_class / venue / market_type / instrument_id / contract_specification / session_timezone / daily_boundary / volume_unit / price_adjustment_policy`；任一键不同即不得 pool，必须独立注册或 `DATA_INVALID`。股票须明确 split/dividend、停牌、涨跌停与 free-float turnover 的处理；加密资产须明确 24/7 日界、base/quote volume、多 venue 偏差、合约迁移/下线、指数方法与稳定币事件。数字窗口、量能阈值、weekday/session 调整、wick/CLV/ATR 边界和序列长度必须属于前述最多八组的 pre-outcome candidate family；未冻结即 `UNKNOWN`。

可记录的状态序列候选是：

```text
SHOCK_REJECTION
→ COMPRESSION
→ RESPONSIVE_BUYING
→ UPWARD_EXPANSION
→ EVENT_REPRICING
→ FAILED_CONTINUATION_OR_DISTRIBUTION_CANDIDATE
→ BREAKDOWN
```

它不是必经路径，也不是因果叙事。至少保留四个竞争解释：`CAPITULATION_ABSORPTION_MARKUP_CANDIDATE`、`DEAD_CAT_DISTRIBUTION_DOWN_CONTINUATION_CANDIDATE`、`EVENT_REPRICING_CANDIDATE` 与 `VENUE_OR_DATA_ARTIFACT_CANDIDATE`。禁止将“机构吸筹”“释放利好”“恐慌/贪婪”或“必然暴跌”写成观测事实。

H10 不把第 8 日作为唯一 anchor。对于 `D1…D8` 的每一日，`t_k = close_time(Dk)/available_at(Dk)`：在 `t_k` 只冻结前缀 `D1…Dk` 已观察到的 state、probability 与 Action；随后才揭示 next-day 和预注册 1–3 日 outcome。完整 `D1…D8` episode 仅可预测 D9 以后，绝不能倒过来筛选 D1–D7 的样本或回测早期 prefix。

H10 与 H11 是两个独立价格终点，不能用一个完整序列同时宣称成功：

| Prefix anchor | 只可在该 anchor 后揭示的目标 | 对照 |
|---|---|---|
| `D2/D3` (`H10`) | 后续 1–3 日 `UPWARD_EXPANSION` 价格终点 | prefix-matched 简单 OHLCV shock 与 time/regime controls |
| `D6/D7` (`H11`) | 次日 downside/breakdown 价格终点 | prefix-matched 简单 OHLCV shock 与 time/regime controls |

同一 episode 的嵌套 D1…D8 prefixes 是一个 cluster，必须在 train/test 切分、block bootstrap 和多重比较中整体处理。禁止全 episode outcome 筛选、overlap leakage 或在不同样本角色中复用 prefix。

H10/H11 每一步的精确 Action 集合为 `{UNKNOWN, OBSERVE, ABSTAIN, EVALUATE_REVERSAL}`；`UNKNOWN` 只用于 required input 无效、缺失或未冻结，有效且已评估状态只能输出其余三者。它们不自动下单、不追消息大阳。既有 LONG 只能按冻结单向 ExitPolicy 管理或退出；退出 LONG 与建立 SHORT 是两个不同 episode，未来 SHORT 必须有独立 EntryZone、stop、target、horizon、fill cohort 和授权。

| 序列前缀/状态 | 允许动作候选 | 点位与风险边界 |
|---|---|---|
| `SHOCK_REJECTION` | 仅 `OBSERVE`；记录结构低点候选 | 不开仓；shock-low 只是未来因果区间候选 |
| `COMPRESSION` | `ABSTAIN` | 不能将缩量本身解释为吸筹或买点 |
| `RESPONSIVE_BUYING / UPWARD_EXPANSION` | 未来、经授权后才可 `EVALUATE_REVERSAL` | 候选 EntryZone 仅为 shock-low causal zone 的有效 retest/响应交集；SL 在 shock low/结构失效外加冻结 buffer；TP 为事前供应区或冻结 R 目标 |
| `EVENT_REPRICING` 且大阳超出 EntryZone | `ABSTAIN`；只管理已有仓 | 禁止追消息价；不得外移目标或放宽 SL |
| `FAILED_CONTINUATION_OR_DISTRIBUTION_CANDIDATE` | 仅 `TIGHTEN / REDUCE / EXIT` 已有 LONG | 不把长仓退出伪装成新 SHORT |
| `BREAKDOWN` | 对既有 LONG 继续保护退出；SHORT 只能作为未来新 episode | 新 SHORT 必须独立 EntryZone、SL、TP、horizon、cohort 与授权 |

表中全部动作仍待 H10/H04/H05 的独立验证及后续权限，当前不构成交易授权。

外部研究只提供机械化与对照方法边界：[Lo、Mamaysky、Wang](https://www.mit.edu/people/wangj/pap/LoMamayskyWang00.pdf) 支持把主观图形转成可检验对象；[Llorente 等](https://www.nber.org/papers/w8312) 表明量价关系取决于交易动机；[Boudoukh 等](https://www.nber.org/papers/w18725) 支持区分新闻与纯价格冲击；[MacKinlay](https://www.bu.edu/econ/files/2011/01/MacKinlay-1996-Event-Studies-in-Economics-and-Finance.pdf) 支持独立事件窗与对照。它们均不构成本项目有效性。

H10 仅与“简单 OHLCV shock baseline + time/regime-matched controls”这一预注册 comparator family 比较其 D2/D3 价格终点；H11 使用同一类但独立样本/终点比较 D6/D7 次日 downside/breakdown。任何 future new-high/new-low、post-outcome 选择、状态回写或无独立增量均构成反证。它们均与 `V4-H03-CURRENT_PRESSURE_CONFIRMATION` 分轮检验，不能把日线序列与 L1 当前压力混成一次胜利。

### 6.2 事件到达关联诊断（V4-H12）

`H12-EVENT_ARRIVAL_ASSOCIATION` 只在 `source_timestamp / published_at / available_at` 均已达到且不晚于 decision time 后，按其 `source_timestamp / published_at / available_at / vintage_id / revision_status` 做独立、time/regime-matched 的关联诊断。未来来源时间、未来修订、缺失或畸形时间戳均 fail-closed。它不能改变 H10/H11 的价格 primary outcome，不能把事件叙事变成价格 alpha，也不能作为入场或路径通过条件；其正确证据等级始终独立于价格假设。

## 7. Source contract：可行性来源不是市场验证

以下来源只用于未来、经授权后的字段、版本、发布时点与 archive 可行性设计；它们既不证明 alpha，也不构成读取真实历史 outcome、回测、paper 或 live 的权限。

| 等级 | 官方一手来源 | 未来可检查的内容 | 当前边界 |
|---|---|---|---|
| P0 | [Binance developer documentation](https://developers.binance.com/en/docs/introduction)；[Binance public data archive](https://github.com/binance/binance-public-data) | venue 字段、事件顺序、交易规则、公开 archive 的 schema 可行性 | 仅 source/schema 可行性证据 |
| P0 风险门 | [ALFRED](https://alfred.stlouisfed.org/)；[Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)；[BLS release schedule](https://www.bls.gov/schedule/)；[BEA schedule](https://www.bea.gov/news/schedule) | vintage、官方发布时间、日历和修订语义 | point-in-time 宏观风险门的数据可行性；不是宏观方向 alpha |
| P1 | 上述宏观字段进入方向或概率模型 | 仅在独立假设、比较器和回测授权下检验宏观方向增量 | 当前 `WAIT_DATA`，不构成方向权重 |
| P2 | [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | 报告可得时间与低频限制 | 不是 15m/1H 的即时情绪代理 |

任何实际 source adapter 都需要 V4-M00 通过后的 Sol 阶段门、显式 B4 数据可行性授权与独立 adapter contract。数据必须持久化完整 record identity：`source_id / generation_id_or_stream_id / source_sequence / stable_input_id / source_timestamp / available_at / record_version`，以及 schema/version、checksum（若适用）和 provenance。发生缺口、乱序、复写、未知 vintage、版本冲突或不可证明的 available time 时，路径是 `DATA_INVALID → UNKNOWN/ABSTAIN`，而不是插值成可交易信号。

## 8. 假设、优先级与逐层验证

完整 machine-readable 定义见 `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json`。本表只提供阅读索引：

| ID | 优先级 | 目的 | 当前状态 |
|---|---|---|---|
| `V4-M00-OUTCOME_FREE_CONTRACT` | P0 | 冻结因果、枚举、失败行为与 synthetic 用例 | `NOT_RUN`；`TESTS_PASS_AWAITING_SOL_STAGE_GATE` |
| `V4-H01-MTF_PARENT_VETO` | P0 | L2 的 4H 父周期 veto 相对冻结 champion 的独立增量 | `WAIT_DATA` |
| `V4-H02-PARENT_CHILD_RELATION` | P0 | 相邻父子关系相对 parent-only 的独立增量 | `WAIT_DATA` |
| `V4-H03-CURRENT_PRESSURE_CONFIRMATION` | P0 | L1 当前压力只确认/否决 L2 已许可候选 | `WAIT_DATA` |
| `V4-H04-CAUSAL_LEVEL_RESPONSE` | P0 | 因果区间/响应相对简单因果前高前低 | `WAIT_DATA` |
| `V4-H05-VOL_LIQ_GEOMETRY` | P0 | 波动/流动性几何相对固定 bps 几何 | `WAIT_DATA` |
| `V4-H06-REMAINING_EV_EXIT` | P0 | 同 cohort 的单向降风险 remaining-EV 退出 | `WAIT_DATA` |
| `V4-H07-PAST_ONLY_ANALOG` | P1 | past-only 类比相对 no-analog 的独立增量 | `WAIT_DATA` |
| `V4-H08-MACRO_RISK_CONDITION` | P1 | point-in-time 宏观风险门相对 no-macro gate | `WAIT_DATA` |
| `V4-H09-FOUR_LAYER_INTEGRATION` | P2 | 仅由已独立支持组件在全新 chronology 上整合 | `WAIT_DATA` |
| `V4-H10-D2_D3_UPWARD_EXPANSION_PRICE_SEQUENCE` | P1 | D2/D3 日线前缀相对简单 shock/control 的 1–3 日上涨价格终点 | `WAIT_DATA` |
| `V4-H11-D6_D7_DOWNSIDE_BREAKDOWN_PRICE_SEQUENCE` | P1 | D6/D7 前缀相对简单 shock/control 的次日下跌价格终点 | `WAIT_DATA` |
| `V4-H12-EVENT_ARRIVAL_ASSOCIATION` | P2 | available-at 后的独立事件到达关联诊断，不是价格 alpha | `WAIT_DATA` |

每一个假设都必须在同一机会宇宙、相同日期角色、成本、延迟、fill 假设、first-hit 与 comparator 上比较。若覆盖不足，结果是 `INCONCLUSIVE_COVERAGE`；若反证条件触发，结果是退役或简化，不是增加指标。

## 9. V4-M00 synthetic 测试设计

在任何真实历史 outcome 之前，必须完成以下纯合成测试。它们只验证逻辑合同，不验证市场盈利。

| 类别 | 合成情形 | 必须结果 |
|---|---|---|
| 时间可得性 | 未闭合 15m/1H/4H/1D/1W，或 `available_at > t` | `UNKNOWN` 或 `ABSTAIN`，不得准备执行 |
| 事件顺序 | 同一 source+generation 内 `source_sequence` 缺失/冲突；或跨源同 `available_at` 的非交换结果 | 前者 `DATA_INVALID → UNKNOWN/ABSTAIN`；后者为无经济顺序 batch，输出 `UNRESOLVED/STOP_FIRST` |
| 父子对齐 | 15m 已闭合，当前 4H 未闭合 | 不读取当前 4H OHLC/RSI/趋势 |
| 状态互斥 | 造出 UP、DOWN、RANGE、边界扰动 | 仅一个 `StructuralRegime`；不稳定时 `TRANSITION` |
| 状态映射 | 回撤、反弹、加速、减速、顶部/底部候选 | 映射唯一，候选不变成确认顶底 |
| 概率层分离 | MarketScenario 与每个 action 的 ActionOutcome | 两个向量各自归一；支持/区间/校准独立报告，方向概率不可直接下单 |
| RSI 边界 | RSI 极值与任意高周期组合 | 只产生 `OBSERVE`，不能绕过 veto |
| EntryZone | 缺少任一可行区间或交集为空 | `ABSTAIN` |
| barrier | 同 bar 触及 TP 与 SL | `STOP_FIRST` |
| 动态风险 | 浮亏、流动性恶化、数据陈旧 | 不放宽 SL、不延长 horizon，优先收紧/退出/HALT |
| analog | future、overlap、outcome-selected 候选 | 检索器拒绝该候选 |
| macro | 发布前、发布后、延迟、修订 | 只读当时 vintage；冲突进入 `UNKNOWN/ABSTAIN` |
| comparator | predecessor 失败或层级变更 | 不更换比较器、不扩大样本宇宙 |

`V4-M00` 任一失败均阻止 B4 申请；即使 V4-M00 测试通过，也只允许提交 Sol 阶段门审，不能自动读取数据、下载 archive、建立 adapter 或回测。

## 10. 未来 B4、DEVELOPMENT 与 walk-forward 路线

路线必须严格顺序推进：

```text
V4-M00 synthetic measurement contract
  → Sol V4-M00 stage gate
  → explicit AUTHORITY_B4_DATA_FEASIBILITY
  → independent DEVELOPMENT authorization
  → chronological walk-forward DEVELOPMENT
  → CALIBRATION freeze
  → one-shot HOLDOUT
  → separate promotion decision or retire
```

### 10.1 B4 前

E0 当前允许执行 synthetic method-contract tests，不以 V4-M00 PASS 作为其前置条件，避免循环依赖。允许：理论、合同、假设注册、synthetic 因果与 schema 设计。禁止：真实历史 outcome、source adapter、backtest、参数搜索、CALIBRATION、HOLDOUT、paper、live。B4 仍必须同时满足 V4-M00 Sol PASS 与显式 B4 authorization。

### 10.2 B4

B4 只可在明确授权后进行 outcome-free 数据可行性：字段、availability、档案、成本、source adapter 合同。它不等于 historical outcome 或回测权限。B4 之后、任何 archive 下载或历史 outcome 可见之前，仍必须冻结完整 candidate family、日期角色、成本/延迟/fill 模型、embargo 和停止规则。

### 10.3 独立 DEVELOPMENT

在新的独立授权前必须冻结：数据 manifest、venue/symbol/contract、档案 checksum、时区、版本、费用、滑点、延迟、fill 模型、样本日期角色、embargo、指标、有限搜索空间、EntryZone、TP/SL/time-stop/first-hit 和停止规则。任何读到的窗口永久记为 `SEEN`。

### 10.4 Walk-forward

按时间顺序使用 DEVELOPMENT → CALIBRATION → 一次性 HOLDOUT。DEVELOPMENT 只可在已冻结的有限 candidate family 内选择，并报告同一多重比较族控制；CALIBRATION 只能冻结唯一 candidate 与概率校准；HOLDOUT 一次性打开、只评价不修复。每个阶段间加入至少覆盖最大 lookback 与最大 holding horizon 的 embargo。报告必须按：

```text
StructuralRegime × LocalImpulse × volatility_state × direction × UTC day
```

分层展示 coverage、Brier、log loss、calibration、成本后 utility、expected shortfall、最大回撤、终态、fill/no-fill/reject、`ABSTAIN` 覆盖率与最差 episode。

至少实施时间平移、方向符号置换、随机/平移 zone、延迟注入、恶化成本、UTC 日或事件簇 block bootstrap，以及有限候选族的 White/Hansen 多重比较控制。任何外部文献、历史类比或宏观解释均不能替代此验证。

## 11. 明确未验证项与禁止项

当前以下结论均不存在：

- 任何周期状态是否能稳定识别真实趋势；
- RSI 在本标的、本周期和成本后是否有优势；
- 任何支撑阻力、相似周期、资金费率、OI、basis、订单流或宏观事件是否有增量；
- EntryZone 是否可成交，TP/SL 是否能按理论价格触及；
- 动态管理是否改善收益或尾部；
- 多层组合是否优于更简单的基线；
- 系统是否适用于 paper 或实盘。

以下行为继续禁止：读取真实历史 outcome 或回测、读取未来或未闭合数据、把 revised macro value 放入过去、用相似 outcome 选择 analog、把可见盘口视为成交保证、扩大止损、延长持有期、替换比较器、自动升级 champion、paper 和 live 交易。

因此目前正确的全局运行状态是：

```text
E0 / OUTCOME_FREE_THEORY_DRAFT / WAIT_DATA
```

未来任一实际结果若不支持假设，合理处理是 `REJECTED_DEVELOPMENT`、`REJECTED_CALIBRATION`、`REJECTED_HOLDOUT` 或退役；不得以新增叙事和参数来掩盖失败。
