# RSI-MTF-DRL-PM Theory Addendum v0.2.1

> 文档 ID：`rsi-mtf-drl-pm-theory-addendum-v0-2-1`
>
> 版本：`0.2.1`
>
> 状态：`REVIEW_READY / E0 / REJECT_FREEZE`
>
> 日期：2026-07-23
>
> 授权：仅允许编制新的 v0.2.1 research contract；策略实现、市场/历史数据读取、回测、CALIBRATION、HOLDOUT、paper、部署和 trading 均未授权

## 0. 规范地位、继承关系与停止条件

本文件不是对既有产物的原位修改。以下三项共同构成 `RSI-MTF-DRL-PM v0.2.1` **候选理论**：

1. `CORE_TRADING_THEORY.md` v2.0，raw SHA-256 `06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d`；
2. `config/rsi_mtf_drl_pm.research_contract.v0_2.json`，full canonical digest 为 `38d572453045016bbdc314d184f9be87a608ec8bc36aabaf92d8c0ce742201e5`；
3. 本 addendum 的完整文件字节。

CORE v2.0 与 v0.2 contract 已通过的语义不变量继续有效。本文件只关闭其未唯一化部分；若本文件与任一既有不变量冲突，解释器必须返回 `SPEC_CONFLICT`，整个 v0.2.1 候选为 `BLOCKED`，不得在代码中自行选择解释。

授权不是语义字段的普通覆盖，而取所有适用阶段门的**交集**：`ALLOW ∩ DENY = DENY`，更严格边界优先。CORE §15 对旧 `P0-RSI-02(v0.2)` 的 pure-primitives 授权仍是可复验的历史记录，但本次 Sol route decision `sol-rsi-spec-gap-stop-2026-07-23` 明确暂停实际执行；它不修改旧 artifact。当前唯一可执行工作是 `P0-RSI-01B(v0.2.1)` contract。只有 01B PASS 后，新的阶段决定才可启动 `P0-RSI-02(v0.2.1)`。builder 不得把两个版本的同名阶段合并，也不得以旧授权绕过新 contract。

后续必须创建新 schema/version、new contract ID：

`rsi-mtf-drl-pm-v0-2-1-outcome-free-contract`

禁止修改、复用或伪装成旧 ID `rsi-mtf-drl-pm-v0-2-outcome-free-contract`。新 contract 必须绑定 CORE 原始文件 SHA-256、旧 v0.2 full canonical digest 与本 addendum 原始文件 SHA-256。本文件不嵌入自己的 SHA-256；其摘要只能由新 contract 或非本文件的治理记录发布，以避免自引用。

本文件使用以下规范词：`MUST`/“必须”、`MUST NOT`/“禁止”、`SHALL`/“唯一规则”。任何未明确列出的输入、默认值、fallback、模型或状态转换均不存在；缺少必填输入时必须执行规定的 `UNKNOWN`、`ABSTAIN`、`CENSORED`、`EXIT` 或 `HALT`，不得猜测。

### 0.1 动态重算不等于在线自适应

- **允许的动态重算**：以新的、满足 lane clock 的输入，重复运行同一个已摘要的纯函数；函数、参数、窗口、阈值、tie-break 和 missing action 不变。
- **禁止的在线自适应**：依据近期盈亏、fill、市场路径、模型误差或人工判断改变参数、阈值、窗口、权重、状态转换、feature、cost、risk、label 或候选集合。
- DEVELOPMENT 中选择有限 challenger 也不是在线自适应；每次选择必须产生新 candidate/policy digest，并遵守“一次只改一层”。CALIBRATION、HOLDOUT、paper 和 trading 当前全部封闭。

### 0.2 E0 research simulator 与未来 execution system 的硬边界

v0.2.1 当前目标是判断“动态 entry/quantity/SL/TP 理论能否被唯一计算、在保守成本风险下是否值得进入历史 DEVELOPMENT 验证”，不是提前实现 production OMS。P0-RSI-02/03 唯一输入为 §2.9 `CanonicalSyntheticEventBundle`，所有 fill、ACK、pending、barrier、funding、censor 与冲突 scenario 均已在 fixture 中 typed/sealed；pure reducer只重放与验证。

三类能力明确延后且当前 FORBIDDEN：P0-RSI-04 才可另行定义被授权历史 source→canonical bundle adapter；只有 predictive validity 通过后才可设计 execution-simulator realism；只有 E3/paper 前另过安全门才可设计 async OMS、exchange connector、retry/idempotency、真实 cancel/amend race与资金账户操作。该分层不删除 risk/pending/late-fill/ACK-authority/STOP_FIRST 验收，只把不属于 E0 的 source/transport复杂度移出当前 contract。

## 1. 统一类型、单位、时钟与 canonical identity

### 1.1 原子类型

| 类型 | 唯一定义 |
|---|---|
| `UtcUs` | JSON integer，Unix epoch 起 UTC 微秒；必须 `>=0`。所有区间比较只使用该整数 |
| `DecimalString` | 十进制定点字符串；正则 `^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$`；禁止 `-0`、指数、前导零、尾随零、NaN、Infinity 和 JSON float |
| `QtyBase` | BTC base quantity，数值 `>=0` 的 `DecimalString`；signed position必须改用 DecimalString |
| `Price` | USDT/BTC，数值 `>0` 的 `DecimalString` |
| `Money` | USDT nonnegative amount，数值 `>=0` 的 `DecimalString`；可正可负的 PnL 字段必须直接声明 DecimalString |
| `Bps` | `1 bps = 0.0001`，数值 `>=0` 的 `DecimalString` |
| `Sha256` | 64 位小写十六进制字符串 |
| `StableId` | 由本节 domain-separated SHA-256 生成的 `Sha256` |

所有十进制计算使用 decimal128：34 位有效数字、`ROUND_HALF_EVEN`。`ln`、平方根和除法也使用该 context；用于比较的最终无量纲指标统一量化到 `1e-12`，金额、价格和数量随后按各自 tick/lot 规则量化。阈值比较在量化后进行。

`floor_tick(x)=floor(x/tick)*tick`、`ceil_tick(x)=ceil(x/tick)*tick`、`floor_lot(x)=floor(x/lot)*lot`。`round_out` 与 `round_toward_entry` 均为 LONG floor_tick、SHORT ceil_tick；`round_protective` 为 LONG ceil_tick、SHORT floor_tick。所有 floor/ceil 是数学意义上的有向取整，不受语言默认 rounding mode 影响。

### 1.2 Canonical JSON 与 identity

Canonical JSON 唯一定义为：UTF-8；object key 递归按 Unicode code point 升序；无无意义空白；数组顺序保留；整数使用最短十进制；禁止 float；所有 schema key 必须存在；只有 schema 明示的字段允许 `null`。

身份函数：

\[
ID(d,x)=SHA256(UTF8(d)\;||\;0x00\;||\;CanonicalJSON(x)).
\]

`d` 是本文件给出的 ASCII domain。不得用文件路径、进程时间、随机数、Python hash、数据库自增 ID 或 replay wall-clock 构造规范身份。

新 contract 必须计算而不是让本文件自嵌以下复合身份：

`composite_theory_id=ID("rsi-mtf-drl-pm-composite-theory/v0.2.1", {core_raw_sha256,v0_2_contract_canonical_sha256,addendum_raw_sha256})`。

implementation manifest 只能绑定新 v0.2.1 contract 的 full canonical digest；`composite_theory_id`、旧 v0.2 digest 或 addendum raw SHA 均不能单独替代该绑定。

全文件只有一个 candidate identity 名称与构造：

```
parameter_set_sha256 = ID("candidate-parameter-set/v0.2.1", exact baseline-or-one-layer-challenger parameter object)
policy_bundle_sha256 = ID("candidate-policy-bundle/v0.2.1", {
  entry_policy_sha256,exit_policy_sha256,cost_policy_sha256,
  risk_policy_sha256,label_policy_sha256,data_role_sha256
})
candidate_id = ID("rsi-mtf-drl-pm-candidate/v0.2.1", {
  composite_theory_id,parameter_set_sha256,policy_bundle_sha256
})
```

`candidate_id` 类型为 StableId，且所有 schema 一律使用这个 key。旧文字或外部对象中的 `candidate_theory_id`、`candidate_digest`、`candidate_sha256`、自由字符串 `candidate_id` 均不是 alias，进入 v0.2.1 时必须拒绝为 SPEC_CONFLICT；不得在 adapter 中静默改名。baseline 与每个有限 challenger 必须有不同 parameter_set_sha256/candidate_id。

### 1.3 Lane clock、事件时钟与窗口端点

沿用 CORE 的 `a_lane(e)`。ClosedMarkBar/BookSnapshot/AggTrade/OpenInterest 等研究输入对象中的时钟含义为：

- `event_time_us`：交易所事件或规范 bar close 的经济时间；
- `lane_available_at_us`：对应 lane 的 `available_at` 或 `reconstructed_available_at`；
- `source_sequence`：源序号；源无序号时为冻结 import key 的单调 rank；
- `event_id`：按 source schema 构造的 `StableId`。

一个事件在决策时刻 `tau_us` 可用，当且仅当 `lane_available_at_us <= tau_us`。默认滚动窗口 `(t-W,t]` 左开右闭；若某公式使用其他端点，本文件会显式给出。窗口成员先按 `event_time_us` 过滤，再按 lane availability 过滤，禁止用晚到事件倒签历史结果。

这些 source objects 在构造 features/path 时的通用排序键为：

`(event_time_us, event_class_rank, source_sequence, event_id)`，均升序。

`CanonicalSyntheticEvent.event_time_us` 另有且只有一种语义：它是 fixture 已冻结的 causal-effective reducer time，原经济时间只写其 `economic_event_time_us`。synthetic event 的显式 predecessor 必须先满足，再按 §2.9 ready-set 排序；book/path trigger 的 causal-effective time 是实际 evaluation grid time或 ACK evaluation time，不能倒签为所用 snapshot 的 availability。label 的 `terminal_at_us` 统一取 winner synthetic event 的 causal-effective time；需要经济时间时只能读该 event 的 nullable economic field。两种时间禁止互换。

## 2. 规范输入 schema

所有 schema 均要求“exact keys”；额外字段不得进入本规范对象。未来 P0-RSI-04 adapter 如需保留 source-specific 字段，只能放在 adapter 自身审计对象中，不能改变本 contract。

本文件所有 `availability_kind` 共用 enum `{SYNTHETIC,ACTUAL,RECONSTRUCTED}`；P0-RSI-02/03 的 bundle/artifacts 只能 SYNTHETIC，P0-RSI-04 如另获授权才可输出 ACTUAL/RECONSTRUCTED。同一 opportunity/window 禁止混 kind。

### 2.1 `ClosedMarkBar.v0.2.1`

必填字段：

`instrument_id:string`、`period_seconds:int enum{900,14400}`、`bar_open_at_us:UtcUs`、`bar_close_at_us:UtcUs`、`closed_at_us:UtcUs`、`lane_available_at_us:UtcUs`、`availability_kind:enum{SYNTHETIC,ACTUAL,RECONSTRUCTED}`、`close_price:Price`、`source_id:string`、`schema_version:string`、`source_sequence:int>=0`、`payload_sha256:Sha256`、`quality:enum{VALID,INVALID,GAP,CONFLICT}`、`stable_bar_id:StableId`。

约束：`bar_close_at_us-bar_open_at_us=period_seconds*1_000_000`；open/close 必须对 Unix epoch 的 period grid 对齐；`closed_at_us>=bar_close_at_us`；`lane_available_at_us>=bar_close_at_us`；`close_price>0`。`payload_sha256=SHA256(CanonicalJSON(object excluding stable_bar_id and payload_sha256))`；随后 `stable_bar_id=ID("closed-mark-bar/v0.2.1", entire object excluding stable_bar_id)`。

同 instrument/period/open 的完全相同对象去重；若 payload 或 close 冲突，该 grid slot 为 `CONFLICT`，不得 tie-break 成一个价格。

### 2.2 `BookSnapshot.v0.2.1`

必填字段：

`instrument_id`、`event_time_us`、`lane_available_at_us`、`availability_kind`、`source_sequence`、`event_id`、`best_bid:Price`、`best_ask:Price`、`bids:array<Level>`、`asks:array<Level>`、`book_generation_id:StableId`、`sequence_contiguous:boolean`、`quality:enum{VALID,INVALID,GAP,CONFLICT}`、`payload_sha256`。

`Level` exact keys 为 `price:Price, qty_base:QtyBase`。bids 必须严格降价，asks 必须严格升价，quantity `>0`，`best_bid<best_ask`，首层必须等于 best price。任何 crossed book、重复价、非连续 generation 或冲突均为 `INVALID/CONFLICT`。`payload_sha256=SHA256(CanonicalJSON(object excluding event_id and payload_sha256))`；随后 `event_id=ID("book-snapshot/v0.2.1", entire object excluding event_id)`。

### 2.3 `AggTrade.v0.2.1`

Exact keys：`instrument_id`、`event_time_us`、`lane_available_at_us`、`availability_kind`、`source_sequence`、`event_id`、`price:Price`、`qty_base:QtyBase`、`buyer_is_taker:boolean`、`quality:enum{VALID,INVALID,GAP,CONFLICT}`、`payload_sha256`。`price,qty_base>0`；`payload_sha256=SHA256(CanonicalJSON(object excluding event_id and payload_sha256))`；随后 `event_id=ID("agg-trade/v0.2.1", entire object excluding event_id)`。

### 2.4 `OpenInterest.v0.2.1`

Exact keys：`instrument_id`、`event_time_us`、`lane_available_at_us`、`availability_kind`、`source_sequence`、`event_id`、`oi_base:QtyBase`、`quality:enum{VALID,INVALID,GAP,CONFLICT}`、`payload_sha256`。`oi_base>0`；`payload_sha256=SHA256(CanonicalJSON(object excluding event_id and payload_sha256))`；随后 `event_id=ID("open-interest/v0.2.1", entire object excluding event_id)`。

### 2.4A `CoverageSeal.v0.2.1`

滚动计算仅看到一组事件不能证明“中间没有缺失”。每个 D、book-grid、label-path 或 reducer replay window 都必须附 exact coverage seal：

`instrument_id:string`、`source_id:string`、`source_schema_version:string`、`availability_kind:enum{SYNTHETIC,ACTUAL,RECONSTRUCTED}`、`window_start_exclusive_us:UtcUs`、`window_end_inclusive_us:UtcUs`、`lane_available_at_us:UtcUs`、`book_or_stream_generation_ids:array<StableId>`、`event_count:int>=0`、`first_source_sequence:int>=0|null`、`last_source_sequence:int>=0|null`、`observed_gap_intervals:array<Gap>`、`complete:boolean`、`seal_sha256:Sha256`。

`Gap` exact keys：`start_exclusive_us:UtcUs,end_inclusive_us:UtcUs,reason enum{SEQUENCE_GAP,CONNECTION_GAP,IMPORT_GAP,CONFLICT}`；按 `(start_exclusive_us,end_inclusive_us,reason)` 排序且不重叠。`book_or_stream_generation_ids` 去重并按 StableId 小写 hex 严格升序；必须 `window_start_exclusive_us<window_end_inclusive_us<=lane_available_at_us`。event_count=0 时 first/last sequence 必须都为 null，否则都必须非 null 且 first<=last。`seal_sha256=ID("source-coverage-seal/v0.2.1", entire object excluding seal_sha256)`。只有 `complete=true`、gap array 为空、generation 集合与输入完全一致、seal 在 decision 前 lane-available 时，窗口才可计算。不得因窗口内“看起来有足够事件”推断 complete。

### 2.5 `VenueInstrumentSnapshot.v0.2.1`

Exact keys：`venue_id`、`instrument_id`、`contract_kind:enum{LINEAR_USDT_PERPETUAL}`、`effective_at_us`、`lane_available_at_us`、`tick_size:Price`、`lot_step:QtyBase`、`min_qty:QtyBase`、`max_qty:QtyBase`、`min_notional_usdt:Money`、`max_notional_usdt:Money`、`max_leverage:DecimalString`、`initial_margin_rate:DecimalString`、`fee_bps_per_side:Bps`、`snapshot_id:StableId`、`payload_sha256`、`quality:enum{VALID,INVALID,CONFLICT}`。

`payload_sha256=SHA256(CanonicalJSON(object excluding snapshot_id and payload_sha256))`；随后 `snapshot_id=ID("venue-instrument-snapshot/v0.2.1", entire object excluding snapshot_id)`。v0.2.1 baseline 必须精确为：tick `0.1`、lot `0.001`、minimum quantity `0.001`、min notional `5`、max notional `20000`、max quantity `10`、max leverage `2`、IMR `0.5`、fee `5` bps。任何 instrument-rule 变化使活动 opportunity `EPISODE_TERMINAL/RULE_CHANGE`，不得热替换。

每个 opportunity 在 anchor 选择 `effective_at<=anchor_at` 且 lane-available 的最新 VALID venue snapshot；同 effective time 取 lex 最小 snapshot_id，并冻结其 identity。action 前若观察到不同 rule snapshot 已生效，立即 terminal，不得把新规则热换入旧 opportunity。

### 2.6 `AccountRiskSnapshot.v0.2.1`

Exact keys：`account_scope_id`、`effective_at_us`、`lane_available_at_us`、`equity_usdt:Money`、`available_balance_usdt:Money`、`existing_initial_margin_usdt:Money`、`open_order_reserve_usdt:Money`、`pending_fee_reserve_usdt:Money`、`position_qty_base:DecimalString`、`position_vwap:Price|null`、`open_order_ids:array<string>`、`snapshot_id:StableId`、`quality:enum{VALID,INVALID,CONFLICT}`。open_order_ids 去重并按 UTF-8 byte lex 严格排序；position_qty_base=0 当且仅当 position_vwap=null，非零时 vwap必须>0；必须 `effective_at_us<=lane_available_at_us`，前者是账户状态经济时刻、后者是完整 snapshot 可被因果读取的时刻；`snapshot_id=ID("account-risk-snapshot/v0.2.1", entire object excluding snapshot_id)`。

必须满足 `0<=available_balance_usdt<=equity_usdt` 且所有 reserve 非负。纯合成 E0 的所有 account snapshots 固定 `equity_usdt=available_balance_usdt=100000`、`existing_initial_margin_usdt=open_order_reserve_usdt=pending_fee_reserve_usdt=0`，这些财务字段不模拟真实账户扣款；pre-submit anchor/action snapshot 还必须 position=0、position_vwap=null、open_order_ids=[]，用于冻结预算并证明无既有仓位。post-submission snapshot只让 `position_qty_base/position_vwap/open_order_ids` 由该 scenario截至 snapshot time 的 sealed observed account state产生：正常 snapshot必须按 §9/§11 exact-match，mismatch fixture可以故意给出不同 qty/vwap/order set但必须唯一映射 ACCOUNT_MISMATCH，不能伪装正常。由此正常 nonzero reconcile、side-flip、VWAP/order mismatch、remainder/operational-flat proof均可构造，禁止把 pre-submit position/order zero默认值复制过去。市场、paper 或账户 connector 不在本 addendum 授权范围内。

`equity_usdt` 在 U anchor 冻结为 episode budget basis。quantity solver 还要求 action_at 前 age<=1s 的最新 VALID account snapshot，并令 `M_available` 使用 anchor snapshot 与 action snapshot 算得 available margin 的较小值；余额上升不得扩大本 episode budget，余额下降必须立即收紧或 ABSTAIN。缺 action snapshot 为 UNKNOWN。

### 2.7 `FrozenEVEvidence.v0.2.1`

Exact keys：`evidence_kind:enum{SUBMIT,HOLD,EXIT_NOW}`、`candidate_id:StableId`、`control_id:enum{C1,C2,C3,C4,Cmu,C5}`、`side:enum{LONG,SHORT}`、`relative_anchor_bp_bucket:int`、`extension_bp_bucket:int|null`、`role:enum{DEVELOPMENT,SYNTHETIC}`、`sample_start_exclusive_us:UtcUs`、`sample_end_inclusive_us:UtcUs`、`issued_at_us:UtcUs`、`lane_available_at_us:UtcUs`、`expires_at_us:UtcUs`、`n:int>=0`、`sum_y_r:DecimalString`、`min_y_r:DecimalString|null`、`max_y_r:DecimalString|null`、`class_counts:ClassCounts`、`observations_sha256:Sha256`、`estimator_policy_sha256:Sha256`、`cost_policy_sha256:Sha256`、`label_policy_sha256:Sha256`、`data_role_sha256:Sha256`、`evidence_sha256:Sha256`。

`ClassCounts` exact keys 为六个 terminal class，value 为非负整数且合计 n。必须满足 `sample_end<issued_at<=lane_available_at<=expires_at` 且 `expires_at-issued_at=30s`。n=0 时 min/max 必须 null；n>0 时必须有 `-1<=min_y<=max_y<=3`。evidence hash 是除自身外完整 object 的 canonical SHA-256。SUBMIT 的 extension bucket 必须 null；HOLD/EXIT_NOW 必须非 null。synthetic role 只能使用 fixture digest，不能伪装成 DEVELOPMENT evidence。

### 2.8 `CanonicalSyntheticEvent.v0.2.1`

P0-RSI-02/03 的 reducer **只**消费已经 typed、sealed、显式全序的 synthetic event，不接收 source/exchange message，也不运行 adapter、source transformation、child generator、timer service 或 venue simulator。event top-level exact keys：

`event_kind,venue_id,instrument_id,episode_id,opportunity_id,control_id,candidate_id,event_time_us,lane_available_at_us,economic_event_time_us,priority_rank,source_sequence,source_event_id,predecessor_event_ids,input_artifact_ids,shared_entry_event_id,request_id,order_id,payload_sha256,payload`。

- `event_kind` 为 §9.1 enum；identity 字段必须逐字等于 bundle scope；`event_time_us:UtcUs` 是 reducer 的 **causal-effective time**，不是市场经济时间；synthetic baseline 必须有 `lane_available_at_us=event_time_us`。economic field 的 union唯一：entry `FILL_CUMULATIVE` 逐字等于 §12.2 matching shared trace 的 fill economic time；E0 `EXIT_FILL_CUMULATIVE` 固定等于自身 `event_time_us`（exit execution latency/race 另属未来 execution-realism contract）；FUNDING_DEBIT取 funding artifact economic time；STOP_HIT/STRUCTURE_EXIT/TARGET_HIT/HORIZON取 payload.input_event_id 对应触发 BookSnapshot.event_time_us；POSITION_SNAPSHOT/RECONCILE_OK与带 non-null snapshot_id 的 ACCOUNT_MISMATCH取该 event 唯一引用的 matching account artifact.effective_at_us；其余 ACCOUNT_MISMATCH 及 decision/command/timer/lifecycle event必须 null。所有非 null值必须 `<=event_time_us`；
- `priority_rank:int` 必须按 §9.2 重算。`source_sequence` 只由 causal-ready allocator 产生：为每个 `(event_time_us,priority_rank)` 建立从0开始的 counter；每一步只看 predecessor identity 已经验证的未分配 event，重算不保存的 `pre_sequence_id=ID("canonical-synthetic-event-presequence/v0.2.1", {bundle_scope_id,event_kind,event_time_us,lane_available_at_us,economic_event_time_us,priority_rank,predecessor_event_ids,input_artifact_ids,shared_entry_event_id,request_id,order_id,payload_sha256})`，从全体当前 ready event 中取 `(event_time_us,priority_rank,pre_sequence_id)` 最小者，把对应 group counter 当前值赋给 source_sequence并将 counter 加一，随后才用下一 bullet 公式生成/验证 source_event_id并释放其 child。当前 ready set 若有相同 pre_sequence_id/不同 bytes直接拒绝。该逐项算法允许同 time/rank causal chain，且 parent ID 不依赖尚未 ready 的 child；fixture不能自行选择 tie order；
- `predecessor_event_ids` 与 `input_artifact_ids` 均去重并按 StableId 小写 hex 字典升序。predecessor 必须严格位于 array earlier position，且其 `event_time_us<=` 当前 event.event_time_us；整个 event_array 的 causal-effective time 因而不得倒退。artifact 必须在 bundle.artifacts 唯一命中。前者只证明 synthetic causal obligation，不触发 reducer 生成新事件；
- `shared_entry_event_id:StableId|null` 对任何含 non-null EntryExecutionBinding 的 submission control，其 `ENTRY_SUBMIT,ENTRY_ACK,ENTRY_REJECT,ENTRY_EXPIRE,FILL_CUMULATIVE` 以及以 shared entry order 为 target 的 `CANCEL_ACK/CANCEL_REJECT_OR_UNKNOWN` 都必须非 null，并在该 binding 唯一命中；local `CANCEL_REQUEST` 必须 null，非 entry-targeted cancel status 与其他 event 也必须 null。C4/C5 还必须按 §12.2 逐 byte复用同一 binding/shared IDs；C1/C2/C3/Cmu 只绑定各自 source binding，不承担跨 control共享约束；
- `payload_sha256=SHA256(CanonicalJSON(payload))`；payload exact schema 由 §9.1 唯一决定；
- `source_event_id=ID("canonical-synthetic-event/v0.2.1", {bundle_scope_id,event_kind,event_time_us,lane_available_at_us,economic_event_time_us,priority_rank,source_sequence,predecessor_event_ids,input_artifact_ids,shared_entry_event_id,request_id,order_id,payload_sha256})`。

request/order nullability exact：order-scoped `ENTRY_SUBMIT,ENTRY_ACK,ENTRY_REJECT,ENTRY_EXPIRE,FILL_CUMULATIVE,CANCEL_REQUEST,CANCEL_ACK,CANCEL_REJECT_OR_UNKNOWN,STOP_REQUEST,STOP_ACK,STOP_REJECT_OR_UNKNOWN,TARGET_REQUEST,TARGET_ACK,TARGET_REJECT_OR_UNKNOWN,REDUCE_ONLY_EXIT_REQUEST,EXIT_FILL_CUMULATIVE,EXIT_ACK,EXIT_REJECT_OR_UNKNOWN` 两者均非 null；ACK/REJECT/EXPIRE 必须引用 earlier matching request。另有两个 conditional order-bound trigger：`STOP_HIT.trigger_kind=ACKED_STOP_PRICE` 与 `TARGET_HIT.trigger_kind=ACKED_TARGET_PRICE` 的 request_id/order_id 也必须两者非 null，并逐字等于当时唯一 active ACK authority；`STOP_HIT/S0_VIRTUAL`、`TARGET_HIT/T0_VIRTUAL|T0_DIRECT|DYNAMIC_TARGET_DIRECT`、所有 STRUCTURE_EXIT 以及其余非 order-scoped event 两者都必须 null。不存在只允许其中一个为 null 的 event。

### 2.9 `CanonicalSyntheticEventBundle.v0.2.1`

这是 E0 reducer 的唯一 non-Genesis input。Top-level exact keys：

`schema_version,bundle_scope_id,ledger_bindings,ledger_identity,ledger_seed,action_context,entry_execution_binding,artifacts,coverage,event_array,finalized_at_us,event_set_sha256,bundle_sha256`。

- `schema_version="rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.1"`；`ledger_bindings/ledger_identity/ledger_seed/action_context` 分别 byte-exact 满足 §11.1 bindings、§11.1 identity、§11.0 seed、§11.0 action context，P0-RSI-02/03 的 ledger_identity.role固定 `SYNTHETIC`。C0 必须 `action_context=null`；每个非 C0 bundle 必须非 null，且首个 context-activation event 与其 decision_kind/action_at_us 精确匹配。`bundle_scope_id=ID("canonical-synthetic-bundle-scope/v0.2.1", {ledger_identity,ledger_seed_sha256:ledger_seed.seed_sha256,policy_sha256:ledger_bindings.policy_sha256})`；
- `ledger_bindings.data_or_fixture_sha256` 只绑定 synthetic fixture schema/generator policy，不得绑定本 scenario 的未来 event/path；完整 bundle_sha256 只在 bundle validation 与最终 LabelBindings 中出现。任何 action/policy/state projection 禁止读取 bundle_sha256、coverage future suffix 或 later artifact；
- `entry_execution_binding` 为 §12.2 完整 object 或 null；C0/NO_ACTION 为 null，发生 synthetic submission 的 control 非 null且 terminal_proof.sealed_at_us<=finalized_at_us，C5 必须逐 byte 复用 C4 binding。它只供 bundle validator 与最终 label 证明 cohort；pure reducer 在每个位置只能读取当前及 earlier event，不得读取 binding 的未来字段；
- `artifacts` 元素 exact keys 为 `artifact_id:StableId,schema_id:ArtifactSchemaId,available_at_us:UtcUs|null,payload_sha256:Sha256,payload:object`，按 artifact_id 排序无重复；必须重算 `payload_sha256=SHA256(CanonicalJSON(payload))` 与 `artifact_id=ID("synthetic-artifact/v0.2.1", {schema_id,available_at_us,payload_sha256})`。`ArtifactSchemaId` 是固定 enum：`CLOSED_MARK_BAR,BOOK_SNAPSHOT,AGG_TRADE,OPEN_INTEREST,SOURCE_COVERAGE_SEAL,VENUE_INSTRUMENT_SNAPSHOT,ACCOUNT_RISK_SNAPSHOT,FROZEN_EV_EVIDENCE,PI_EXIT_POLICY,FIRST_HIT_LABEL_POLICY,SHARED_ENTRY_ACTION,EXIT_POLICY_INSTANCE,C4_C5_EXOGENOUS_PATH_MANIFEST,SYNTHETIC_FUNDING_OBSERVATION,SYNTHETIC_CONFLICT_PROOF`；其 payload 分别必须 byte-exact 满足 §2.1、§2.2、§2.3、§2.4、§2.4A、§2.5、§2.6、§2.7、§12.1、§12.5、§12.2、§12.3 及下三 bullets，未知 enum、free-form payload 或 extra/missing key 均拒绝。PI_EXIT/FIRST_HIT policy与 C4_C5 manifest必须 available_at_us=null，且 manifest禁止出现在任何 event.input_artifact_ids；SHARED_ENTRY_ACTION 必须 available_at_us=payload.action_at_us；EXIT_POLICY_INSTANCE必须等于 first nonzero fill causal time；`ACCOUNT_RISK_SNAPSHOT.available_at_us` 必须逐字等于 payload.lane_available_at_us；其余 source/evidence/snapshot/funding/conflict artifact必须非 null并等于其 schema lane/causal proof time。含 availability_kind 的 artifact 在 P0-RSI-02/03 必须为 SYNTHETIC。event 只能引用 static policy、或 `available_at_us<=event_time_us` 的 causal artifact。entry/level/candidate 与 barrier结果从 seed/action context、ledger prefix、exact source/policy artifacts重算，禁止另塞未定义的 derived-proof object；constructor 不访问 bundle 外部文件/数据库；
- funding observation 唯一使用 `schema_id=SYNTHETIC_FUNDING_OBSERVATION`，其 payload exact keys 为 `funding_event_id:StableId,venue_id:string,instrument_id:string,economic_event_time_us:UtcUs,interval_start_us:UtcUs,interval_end_us:UtcUs,funding_rate:DecimalString,price_basis:Price,availability_kind:enum{SYNTHETIC},quality:enum{VALID}`。必须 `interval_start_us<interval_end_us=economic_event_time_us<=artifact.available_at_us`、price_basis>0，且 `funding_event_id=ID("synthetic-funding/v0.2.1", {venue_id,instrument_id,interval_start_us,interval_end_us})`；
- synthetic conflict scenario 只使用一个 `schema_id=SYNTHETIC_CONFLICT_PROOF` 的 `SyntheticConflictProof.v0.2.1` artifact，其 payload exact keys 为 `claimed_source_identity:StableId,claimed_event_kind:ReducerEventKind.v0.2.1 excluding EVENT_CONFLICT,original_payload_sha256:Sha256,original_payload:object,incoming_payload_sha256:Sha256,incoming_payload:object,proof_sha256:Sha256`；original/incoming payload都必须分别满足 claimed_event_kind 的 §9.1 exact payload schema，两个 hash必须重算、互不相等，`proof_sha256=ID("synthetic-conflict-proof/v0.2.1", payload excluding proof_sha256)`，wrapper.available_at_us必须等于 EVENT_CONFLICT.event_time_us。EVENT_CONFLICT.input_artifact_ids 必须恰好只含该 proof artifact，并满足 `event.payload.original_event_id=claimed_source_identity`、`event.payload.original_payload_sha256=original_payload_sha256`、`event.payload.incoming_payload_sha256=incoming_payload_sha256`；这不等于接收两个 live source messages；
- C4/C5 filled pair还必须各含一个 byte-identical `schema_id=C4_C5_EXOGENOUS_PATH_MANIFEST` static artifact；payload exact keys 为 `schema_version,opportunity_id,candidate_id,lane_id,availability_kind,path_start_us,h0_us,book_artifact_ids,funding_artifact_ids,source_coverage_artifact_ids,manifest_sha256`。schema_version固定 `rsi-mtf-drl-pm.c4-c5-exogenous-path-manifest.v0.2.1`，availability=SYNTHETIC，三个 ID arrays各自去重/lex排序并逐项命中对应 schema artifact；正常 path 的 book IDs必须恰好等于§12.3从 shared path_start 到 H0每个可选 expected grid的 selected snapshot，缺失 grid不得伪造 ID而由 coverage gap证明；funding IDs必须恰好等于 wrapper.available_at_us（亦即其 FUNDING_DEBIT.event_time_us）落在闭区间 `[c_f_us,H0]` 的全部 SYNTHETIC_FUNDING_OBSERVATION artifact IDs，同 c_f 的 fill先按rank2、funding再按rank3，H0 funding也在rank9 horizon前纳入，且该集合不因 early terminal缩短；coverage IDs恰好 seal整个 source window及其中全部 complete/gap/conflict状态，不要求在 data-censor scenario伪称 complete。§12.3 `ZERO_GRID_OPERATIONAL_OVERRIDE` 的三个 arrays必须全空。其 control-neutral cause key 唯一为 `ID("zero-grid-shared-cause/v0.2.1", {event_kind,event_time_us,economic_event_time_us,shared_entry_event_id,input_artifact_ids,payload_sha256})`，明确排除 local bundle_scope/source_event_id；C4/C5 只有该 key与 cause time逐字相同才可形成 zero-grid pair，否则 H-013 `PAIR_REJECT/PRE_FIRST_GRID_CAUSE_NOT_SHARED`，不得比较 exit effect。`manifest_sha256=ID("c4-c5-exogenous-path-manifest/v0.2.1", payload excluding manifest_sha256)`。manifest是 final pair validator/label-only，action与逐 event reducer禁止读取 future IDs；
- artifacts 的 ID 集合必须恰好等于所有 event.input_artifact_ids、entry_execution_binding.terminal_proof 的 non-null reconcile artifact、发生 submission 时唯一 `SHARED_ENTRY_ACTION` artifact、§12.3 path/source-coverage 所引用 artifact，以及 C4/C5 manifest自身与其传递引用 IDs 的并集；禁止未被任一规范 root引用的 future/diagnostic extra。ENTRY_SUBMIT.input_artifact_ids 必须含该唯一 SharedEntryAction artifact，其 payload.entry_action_sha256 等于 action_context.shared_entry_action_sha256 与 entry_execution_binding.shared_entry_action_sha256；NO_ACTION/C0 禁止含该 artifact；
- `coverage` exact keys 为 `status enum{COMPLETE,CENSORED},window_start_exclusive_us:UtcUs,window_end_inclusive_us:UtcUs,expected_grid_times_us:array<UtcUs>,observed_grid_times_us:array<UtcUs>,missing_grid_times_us:array<UtcUs>,event_count:int>=0,artifact_count:int>=0,event_set_sha256:Sha256,artifact_set_sha256:Sha256,coverage_sha256:Sha256`。C0/NO_ACTION/NO_FILL 唯一为 `window_start_exclusive_us=window_end_inclusive_us=finalized_at_us`、三个 grid arrays均 `[]`、status=COMPLETE。正常 FILLED path 必须有 §12.3 `0<path_start_us<H0`，window start=`path_start_us-1`、window end=`evaluated_through_us`，expected逐字等于从 path_start 到该 endpoint 的 §12.3 grid prefix，observed为已有合法 book point grids，missing为 expected-observed；data censor的首个 missing就是 endpoint，至少已有一个 committed grid后的 operational censor可 missing=[]。§12.3 `ZERO_GRID_OPERATIONAL_OVERRIDE` 唯一为 window start=end=`zero_grid_cause_event.event_time_us`、三个 arrays均空、status=COMPLETE。三个非空 array严格升序无重复且每项落在 `(window_start_exclusive_us,window_end_inclusive_us]`；observed 与 missing 不相交且并集等于 expected；COMPLETE 当且仅当 missing=[]。coverage.status只表达 synthetic data-grid completeness；label 可因 operational override 为 CENSORED而 coverage仍 COMPLETE。event_count/event_set_sha分别等于 event_array length与 `ID("canonical-synthetic-event-set/v0.2.1",event_array)`；artifact_count/artifact_set_sha分别等于 artifacts length与 `ID("canonical-synthetic-artifact-set/v0.2.1",artifacts)`；`coverage_sha256=ID("canonical-synthetic-coverage/v0.2.1",coverage excluding coverage_sha256)`；
- `event_array` 是从 first non-Genesis event 到 sealed replay 尾部的全部 `CanonicalSyntheticEvent`，C0 唯一为 `[]`。每个 non-C0 bundle 的**末 event 处理后 reducer state_after 必须为 CLOSED**，且不存在未解决 clock/order remainder；ENTRY_REJECT/ENTRY_EXPIRE 等可先进入 terminal state=CLOSED但仍保留未证明 remainder，此时只允许继续消费 §9.4 明列的 first qualifying account proof、合法 late lifecycle或 conflict路径，绝不能把中间 CLOSED 当作 sealed end。这里不存在名为 CLOSED 的 event_kind。不支持 live prefix/cut。`finalized_at_us` 等于末 event.event_time_us，C0 等于 seed.anchor_at_us；
- 先按 §2.8 causal-ready allocator逐项分配/验证 source_sequence 与 source_event_id并同时验证 predecessor 已分配、时间不倒退；其产出的 event 顺序就是唯一 event_array。reducer replay时对已验证 identity 的 ready set以 `(event_time_us,priority_rank,source_sequence,source_event_id)` 升序取 event，必须得到同一 byte array。CanonicalSyntheticEvent 中不存在 `event_id`，全序最后一项唯一使用 `source_event_id`；
- `event_set_sha256=ID("canonical-synthetic-event-set/v0.2.1", event_array)`，必须同时等于 coverage.event_set_sha256；`bundle_sha256=ID("canonical-synthetic-event-bundle/v0.2.1", entire object excluding bundle_sha256)`。

bundle validator 还必须证明以下 causal obligations 已由显式事件满足，pure reducer只消费、不补造：first fill 后同 causal time依次出现 CANCEL_REQUEST、INITIAL_PROTECTION STOP_REQUEST；excess increase 后依次出现 cancel-if-needed、PROTECTION_REPAIR STOP_REQUEST、excess REDUCE_ONLY_EXIT_REQUEST；任何 market/structure/target/horizon terminal 后出现 matching reduce-only exit request；每个 active clock 在其 deadline 有且只有一个 PENDING_DEADLINE；每个 STOP/TARGET ACK 的 causal time精确等于其 request+1s；fixed/dynamic noncrossing candidate 只能有 request，crossing candidate 只能有 direct terminal；任何 STOP/TARGET request 的 replaces_order_id 非 null时，必须已有 targeting old order 的 CANCEL_REQUEST，matching new ACK 后同 causal time必须有该 cancel 的 CANCEL_ACK，顺序为 new ACK→cancel ACK；cancel reject/unknown禁止新 authority并走 failure，replacement ACK 本身绝不原子终止 old row；每个 FUNDING_DEBIT.predecessor_event_ids 必须包含全部同 event_time 的 FILL_CUMULATIVE/EXIT_FILL_CUMULATIVE，funding breach 后紧随 DATA_HEALTH_INVALID。只有 prefix从未发生 ACCOUNT_MISMATCH且当前 fill projection authority matched 时，新正常/excess/fatal exit request才可用 projection_mode=INTENDED_FILL_PROJECTION；prefix一旦发生 ACCOUNT_MISMATCH，任何已知非零 signed risk（同向 deficit/excess、VWAP mismatch、side flip均同样）只能按 `abs(reconcile.position_qty)` 发 projection_mode=OBSERVED_SIGNED_RISK 的 side-correct emergency exit。未知 signed qty禁止方向性 request并保持 HALTED_RECONCILE，已知 flat只 cancel active orders。缺失、多余、顺序或 identity 不等均拒绝整个 bundle，不由 reducer猜测。

synthetic request/order identity 也唯一：ENTRY 使用 §12.2 shared request/order IDs；其他 request 令 `request_id=ID("synthetic-management-request/v0.2.1", {bundle_scope_id,causal_trigger_source_event_id,event_kind,role,ordinal,payload_sha256})`、`order_id=ID("synthetic-management-order/v0.2.1", {request_id,role})`，ACK/reject/fill逐字复制 earlier request/order。`role` 不是 event 字段，而由 request event_kind 唯一映射：CANCEL_REQUEST→CANCEL、STOP_REQUEST→STOP、TARGET_REQUEST→TARGET、REDUCE_ONLY_EXIT_REQUEST→EXIT。causal_trigger 唯一是整条 obligation chain 的 root cause（fill、barrier evaluation/ACK、market trigger、funding breach、lifecycle failure或 fatal event），即使后续 request另有 intermediate predecessor也不改变。对同 trigger实际存在的全部 request按 `(role_rank,target_order_id null-first,payload_sha256)` 排序并从0连续赋 ordinal；`target_order_id` 只对 CANCEL 取 payload 值，其余为 null；role_rank固定 `CANCEL=0,STOP=1,TARGET=2,EXIT=3`。因此 first fill自然为 cancel0/stop1，excess为 optional cancel后 stop/exit，barrier update为 stop/target，market terminal仅 exit0，多 cancel按 target ID。初次与 fill projection不一致的 snapshot artifact只允许一个 ACCOUNT_MISMATCH event引用，禁止同时放 POSITION_SNAPSHOT/RECONCILE_OK；其 predecessor必须含全部同 event_time position-changing fills后再重算 mismatch。唯一例外是 prior mismatch 后满足 §11.3 operational-flat guard 的 later zero snapshot，只能映射一个 reconcile_mode=OPERATIONAL_FLAT_AFTER_MISMATCH 的 RECONCILE_OK；normal valid snapshot只能映射 MATCH_FILL_PROJECTION/POSITION_SNAPSHOT。

本版本故意不定义 raw message 到 bundle 的映射，也不定义真实 command transport。历史 raw→canonical adapter 只可在另行授权的 P0-RSI-04 data-admission contract 中定义；预测有效性通过后才可建立 execution-simulator-realism contract；E3/paper 前才可建立真实 async OMS/exchange race contract。此前未冻结草稿中的 RawSourceFact/Normalize/derive_children 设计均已撤回，不构成实现或数据权限。

## 3. RSI：连续 grid、freshness、方向和 rearm

### 3.1 Grid 与 release

周期 `P in {900,14400}` 秒的 slot 为 `[nP,(n+1)P)`，bar close 为 `(n+1)P`。v0.2.1 baseline release lag `lambda=60` 秒，规范 evaluation time 为：

\[
g_P(n)=barClose_P(n)+60s.
\]

在 `tau` 上的 expected bar 是满足 `bar_close+60s<=tau` 的最大 close。若该 slot 没有恰好一个 `VALID`、lane-compatible bar，则该 period 的 RSI 为 `UNKNOWN_GRID`。晚到 bar 不得倒写此前 evaluation；它只能从其实际 lane availability 之后参与，并且 expected slot 缺失期间的 event ledger 已永久记录 `UNKNOWN`。

一个 15m RSI evaluation 仅发生在 `g_900(n)`；4H RSI 在每个 15m evaluation 上选择 expected 4H slot。4H 值有效区间为其 expected release 到下一 expected 4H release 的左闭右开区间，不另设“看到最新”的模糊 freshness。K 使用的 15m-derived value另受 §4.1 的 900 秒 staleness。

### 3.2 连续性与 RSI

RSI(14) 使用 ending slot 及之前 14 个 slot，共 15 个 close；这些 slot 必须连续、同 instrument、同 period、同 lane kind 且全部 `VALID`。缺一个 slot、重复冲突、跨 gap 或混 kind 均为 `UNKNOWN_GRID`，恢复必须重新积累完整 15 个连续 close。

Wilder 公式、seed 和零分母行为沿用 CORE §15.1。量化后的 RSI 与阈值比较。long 为 `RSI<=30`，short 为 `RSI>=70`；15m×long、15m×short、4H×long、4H×short 四个 boolean 分别计算，不允许镜像缓存改变方向身份。

### 3.3 C1/C2 event identity、previous 与 rearm

`t_c^-` 唯一指同 control、同 side、同 lane、紧邻的前一个 15m expected evaluation grid；不是“前一条成功记录”。

Event ledger key：

`(candidate_id,lane_id,instrument_id,control_id enum{C1,C2},side enum{LONG,SHORT},grid_close_us)`。

状态 enum：`UNKNOWN, FALSE_ARMED, TRUE_LATCHED`。

- 初始化或任何 UNKNOWN 后：`UNKNOWN`；
- 首次有效 false：`FALSE_ARMED`；
- `UNKNOWN -> true`：不发 event，转 `TRUE_LATCHED`；只有此后再次观察到有效 false 才能 rearm；
- `FALSE_ARMED -> true`：发出一个 event 并转 `TRUE_LATCHED`；
- `TRUE_LATCHED -> true`：不重复发 event；
- `TRUE_LATCHED -> false`：`FALSE_ARMED`；
- 任意状态遇到缺失/冲突：`UNKNOWN`。

`event_id=ID("rsi-cross-event/v0.2.1", {candidate_id,lane_id,instrument_id,control_id,side,grid_close_us,previous_state,current_boolean,input_bar_ids})`，input_bar_ids 按 period、bar_close、stable_bar_id 排序。完全重复 event 去重；同 ledger key 不同 canonical payload 为 `CONFLICT`，该 branch `ABSTAIN`。

RSI period 14、阈值 30/70、release lag 60 和连续 grid 在 v0.2.1 中不可调，challenger set 为空。

## 4. K、D、严格 post-pressure R、L 与 RESPONDING

所有下述 microstructure 计算在 UTC 1 秒 grid `t_k=k*1s` 上评估；窗口均按事件 `event_time_us`，同时要求 `lane_available_at_us<=t_k`。若 window 内任一已声明 required source 出现 gap/conflict，结果为 `UNKNOWN_ABSTAIN`。

### 4.1 K：4H directional-persistence proxy

取 ending 15m slot 及之前 16 个连续 15m close，共 17 个。令：

\[
r_i=\ln(C_i/C_{i-1}),\quad
R_{4h}=\ln(C_n/C_{n-16}),\quad
RV_{4h}=\sqrt{\sum_{i=n-15}^{n}r_i^2},
\]

\[
K=|R_{4h}|/\max(RV_{4h},10^{-8}).
\]

K 只在 ending bar release 后 900 秒内有效，左闭右闭；之后为 UNKNOWN。long/short baseline gate 均为 `K>=1.5`。K 是 full/empty gate，不产生价格坐标，也不得被 C1/C2 读取。零分母只使用 `1e-8` floor。

### 4.2 D：60 秒 signed aggressive-notional imbalance

对 `(t-60s,t]` 内 `VALID AggTrade`：

\[
v_i=price_i\,qty_i,\quad \eta_i=\begin{cases}+1,&buyer\_is\_taker\\-1,&otherwise\end{cases},
\]

\[
D(t)=\frac{\sum_i\eta_i v_i}{\sum_i v_i}.
\]

该 60 秒区间必须有精确匹配的 `CoverageSeal`。`d_evidence_sha256=ID("d-grid-input/v0.2.1", {instrument_id,lane_id,window_start_exclusive_us:t-60s,window_end_inclusive_us:t,coverage_seal_sha256,agg_trade_event_ids})`，其中 event IDs 按 `(event_time_us,source_sequence,event_id)` 排序并必须与 seal event_count/generation 一致。无成交、分母零、seal 不完整、source gap/conflict 或最新 trade 距 t 超过 60 秒均为 UNKNOWN。方向 gate 为 `sD(t)>=0.1`，其中 long `s=+1`，short `s=-1`。

### 4.3 Pressure run 与严格 post-pressure R

为待入场方向 `s` 定义 adverse pressure：`P_s(t)=true` 当且仅当 `sD(t)<=-0.1`。一个 pressure run 是 1 秒 grid 上最大连续 true 段，baseline 至少连续 5 秒。`t_start` 是首个 true grid，`t_p` 是该段后首个有效 false grid；UNKNOWN 不终止也不完成 run，而是使该 run 永久无效。

counterparty depth band 固定 10 bps。对 long 使用 bid：

\[
Depth_{LONG}(u)=\sum_{p\ge bestBid_u(1-0.001)}p\,qty_p;
\]

对 short 使用 ask：

\[
Depth_{SHORT}(u)=\sum_{p\le bestAsk_u(1+0.001)}p\,qty_p.
\]

每个 UTC 秒选择 `event_time<=u` 且 lane-available 的最新 `VALID` book；age 必须 `<=1s`，先取最大 event_time，同 time 再取最小 `(lane_available_at_us,source_sequence,event_id)`。pre window 为 `[t_start-30s,t_start)` 的 30 个秒点；post window 为 `(t_p+270s,t_p+300s]` 的 30 个秒点。pressure、pre-depth、完整 recovery 和 post-depth 都必须各自被 CoverageSeal 完整覆盖；每个秒点都必须有效，且 `(t_p,t_p+300s]` 不得再次出现 `P_s=true`。

每个 run 的 identity 唯一为 `pressure_event_id=ID("pressure-run/v0.2.1", {instrument_id,lane_id,side,t_start_us,t_p_us,pressure_grid_inputs})`。`pressure_grid_inputs` 是从 t_start 到 t_p（含 false endpoint）逐秒排列的 exact array，元素 keys 为 `grid_time_us:UtcUs,d_value:DecimalString,d_evidence_sha256:Sha256,state:enum{TRUE,FALSE}`；任何 UNKNOWN 已使 run 无效，因此不得出现在 identity array。

\[
H_{pre}=median(Depth_s(u):u\in[t_{start}-30s,t_{start})),
\]

\[
H_{post}=median(Depth_s(u):u\in(t_p+270s,t_p+300s]),\quad
R_s=\min(1,H_{post}/H_{pre}).
\]

偶数样本 median 是中间两值算术平均。`H_pre<=0`、任一缺秒、gap/conflict、pressure/recovery 重叠均为 UNKNOWN。令经济 endpoint `t_R=t_p+300s`，`r_available_at=max(all input lane_available_at, all seal lane_available_at)`；R 只在 `r_available_at<=evaluation_at<=t_R+60s` 时有效。若 r_available_at 晚于右端点则永久 UNKNOWN。gate 为 `R_s>=0.6`。多个可用 pressure 候选取最大 `t_p`，再取最小 `pressure_event_id`。

该定义严格把 pressure `[t_start,t_p)` 与 recovery `(t_p,t_p+300s]` 分离；同步 depth proxy 不得替代 R。

### 4.4 L：900 秒 delta log OI

对 endpoint `e in {t-900s,t}`，选择 event_time 不晚于 e 的最新 `VALID OpenInterest`；先取最大 event_time，同 time 取最小 `(lane_available_at_us,source_sequence,event_id)`；必须 `e-event_time<=60s`、`lane_available_at_us<=t` 且 `lane_available_at_us<=e+60s`。两端 OI 均须 `>0`：

\[
L(t)=\ln(OI_{end}/OI_{start}).
\]

任一端缺失、冲突、gap、零值或迟于 release deadline 为 UNKNOWN。long/short baseline 都要求 `L<=-0.0005`；它只表示去杠杆，不解释方向。

### 4.5 RESPONDING

使用与 R 相同的 frozen pressure event。`x_s(u)` 为 long 的 best bid、short 的 best ask，按 §4.3 的 book 选择规则取得：

\[
Resp_s=10^4\,s\frac{x_s(t_p+300s)-x_s(t_p)}{x_s(t_p)}.
\]

RESPONDING 与 R 共用经济 endpoint、`r_available_at` 和 60 秒右端点；baseline gate 为 `Resp_s>=5` bps。缺任一 endpoint、spread/book 无效或同 pressure identity 不一致均为 UNKNOWN。`Confirm_s` 使用三值逻辑：任一 required gate 为 false 则 false；没有 false 但至少一项 UNKNOWN 则 UNKNOWN；仅全部 true 才为 true。UNKNOWN 在 branch deadline 前不等于 false，但 deadline 到达仍无合法 action 时必须 `ABSTAIN`。

## 5. Gate-neutral U、anchor、dedup、cooldown 与仲裁

### 5.1 固定时间分区

U 不由 RSI、K、D/R/L、RESPONDING、EntryZone、fill、exit 或 outcome 创建。对每个 lane/venue/instrument，将 Unix epoch 按 2700 秒固定 cycle 分区：

- active interval：`[cycle_start,cycle_start+1800s)`；
- cooldown：`[cycle_start+1800s,cycle_start+2700s)`。

每个 active interval 中，首个 lane-valid 15m evaluation grid 创建一个 master opportunity；第二个 grid 只生成 `DEDUP_ATTACHED` ledger event，绑定同一 opportunity。cooldown 内的 grid 生成 `COOLDOWN_SUPPRESSED`，不创建 opportunity。该分区不读取任何待测 gate，因此 candidate/control 结果不能改变 U。

`opportunity_id=ID("master-opportunity/v0.2.1", {u_policy_sha256,lane_id,role,venue_id,instrument_id,cycle_start_us})`，其中 u_policy_sha256 是新 contract 中冻结的 §5 policy digest，跨 baseline/challenger 必须相同；candidate digest 只写 U record binding，不进入 identity。一个 opportunity 同时包含 LONG、SHORT 两个独立 branch，不以 RSI 决定 side。

### 5.2 Anchor 与 envelope

`anchor_at` 是创建 opportunity 的 15m evaluation time。选择 `event_time<=anchor_at` 的最新 VALID book，age `<=1s`；tie-break 同 §4.3。若不存在，opportunity 仍写入 U，但 `anchor_status=UNKNOWN`，全部 control branch 发出 `CONTROL_ABSTAIN/ANCHOR_UNKNOWN`，防止质量缺失从 U 分母中消失。

\[
A_0=(bestBid+bestAsk)/2.
\]

LONG envelope：`[A0*(1-15bps), A0*(1+5bps)]`；SHORT envelope：`[A0*(1-5bps), A0*(1+15bps)]`。A0 和 envelope 一次冻结，禁止重锚或按 gate 重画。价格 tick domain 继续使用 v0.2 contract 的 ceil-lower/floor-upper 规则。

### 5.3 Control clocks 与 TTL

- C1 只有 anchor grid 自身产生 `E_C1` 时才启动 branch；其 gate-search interval 为 `[anchor_at,anchor_at+30s)`；没有 E_C1 则该 branch 在 anchor evaluation 直接发出 `CONTROL_ABSTAIN/NO_C1_EVENT`；
- Cmu 不读 RSI，始终从 U anchor 启动，gate-search interval 为 `[anchor_at,anchor_at+30s)`；
- C2/C3/C4：只有首个 attached `E_C2` 才启动其 branch，branch interval 为 `[E_C2_at,min(E_C2_at+1800s,cycle_start+1800s))`；
- C5 完全继承 C4；
- 任一 control 在自己的 interval 内首次 gates+common checks 全部通过时冻结 `action_at`；
- 所有可 action control 在唯一 action_at 立即生成一次 submission，`submitted_at=action_at`；entry order expiry 为 `action_at+30s`，活动区间 `[action_at,action_at+30s)`，右端点先 expiry，禁止延迟或第二次 submission；
- observation expiry、control action/abstain、episode terminal、cooldown start 的同时间优先级严格沿用 v0.2 列表；全局 `KILL/ACCOUNT_MISMATCH` 永远先于该列表。

一个 control terminal 不删除其他 control branch。instrument rule change、lane conflict 或 account kill 是 master `EPISODE_TERMINAL`；普通 gate false/UNKNOWN 只终止对应 branch。cycle cooldown 不因结果提前或延后。

## 6. EntryZone、Z_liq 与非循环 quantity solver

### 6.1 Book、spread 与 marketable IOC

每个候选 p 使用 action_at 前最新 VALID book，age `<=1s`，且与 venue snapshot 同 instrument。mid=`(bid+ask)/2`：

\[
spreadBps=10^4(ask-bid)/mid\le5.
\]

LONG IOC 必须 `p>=bestAsk`，可消费 asks `price<=p`；SHORT IOC 必须 `p<=bestBid`，可消费 bids `price>=p`。价格层分别按 long 升价、short 降价，层内只使用聚合 quantity；允许在最后一层部分消费。

对 quantity q 的 VWAP slippage：

\[
slip_{L}=10^4(VWAP(q)-bestAsk)/bestAsk,
\]

\[
slip_{S}=10^4(bestBid-VWAP(q))/bestBid.
\]

`Q_sweep(p)` 是在 limit p 内且 `slip<=5bps` 的最大可消费 base quantity；有限 book 不足时只取已见 quantity。`Q_sweep` 不依赖策略 q。

### 6.2 非循环解

先计算独立 liquidity cap：

\[
Q_{liq}(p)=Q_{sweep}(p)/3.
\]

再按 §8 计算 risk、margin、notional、venue 和 first-fill-pending caps，最后：

\[
q_0(p)=floor_{lot}(\min\{Q_{risk},Q_{liq},Q_{margin},Q_{notional},Q_{venue},Q_{firstPending}\}).
\]

用 q0 重新扫一次同一 frozen book，必须同时满足：q0>0、`Q_sweep>=3q0`、slippage<=5bps、limit、lot、min/max quantity、minimum notional、margin 和 risk。否则删除 p；禁止迭代增大 q、读取新 book 或按结果回调参数。这使 `Z_liq -> Q_liq -> q -> Z_liq` 的表面循环变成一次独立 cap 加一次验证。

Book freshness、spread、capacity、slippage 任一 UNKNOWN 使 p 不属于 Z_liq。不得把 UNKNOWN 当零 slippage。

## 7. Geometry：b0、G0、S0/T0/H0/Tcap

### 7.1 b0

\[
b_0(I_0)=ceil_{tickDistance}(\max(2\delta_p,2\,bps\cdot |I_0|)).
\]

`ceil_tickDistance(x)=ceil(x/delta_p)*delta_p`。该公式同时实现“至少 2 ticks”与“至少 2 bps”，不是二选一。

### 7.2 I0 与 G0

I0 使用 v0.2 的 `[anchor_at,action_at]` exit-side signed extreme，并在此唯一化输入：集合包含 interval 内全部同 instrument/lane kind、`VALID`、sequence-contiguous 且 `lane_available_at<=action_at` 的 BookSnapshot；LONG 取 best bid、SHORT 取 best ask。CoverageSeal 必须完整覆盖 interval 与 generation。令 `x_u` 为 exit-side price，按 `(s*x_u,lane_available_at_us,source_sequence,event_id)` 升序取唯一 u*，`I0=x_u*`；因此 LONG 取最低 bid、SHORT 取最高 ask，同价取最早 lane/sequence/ID。空集合、gap/conflict 或 seal 不完整删除 p。

G0 的结构窗口精确为 `[w0,action_at]`，其中 `w0=max(anchor_at,action_at-1800s)`。Baseline structure policy ID 为 `EXECUTABLE_PRICE_TOUCH_V1`：1 秒 exit-side grid 唯一为 `{ceil(w0/1s)*1s+k*1s < action_at} union {action_at}`，endpoint 去重；每点选择 event_time<=grid、lane_available<=grid、age<=1s 的最新 book，要求 CoverageSeal complete 且无 gap/conflict；每个 LONG best bid 或 SHORT best ask 经 `round_toward_entry` 后都是一个有限候选，priority 固定 0。

每个 grid point 先取最大 event_time，同 time 取最小 `(lane_available_at_us,source_sequence,event_id)`；同 rounded price 候选再按 `(lane_available_at_us,source_sequence,event_id)` 保留最早规范成员。候选 stable ID 唯一为 `ID("g0-executable-touch/v0.2.1", {policy_id:"EXECUTABLE_PRICE_TOUCH_V1",side,rounded_price,grid_time_us,source_event_time_us,source_event_id,coverage_seal_sha256})`。候选必须满足 `s(g-p)>0` 且 favorable distance 至少 4 bps。按 `(favorable_distance,priority,lane_available_at_us,stable_id)` 升序取 G0。无候选、窗口 gap 或 source UNKNOWN 删除 p。该 baseline 只主张“此前实际触达的可执行价”，不把它升格为已验证支撑/阻力。

### 7.3 Levels 与 endpoints

\[
S_0=round_{out}(I_0-sb_0),\quad d_S=s(p-S_0)>0,
\]

\[
d_T=\min(s(G_0-p),3d_S),\quad T_0=round_{towardEntry}(p+sd_T).
\]

round 后必须满足 `1.25<=s(T0-p)/dS<=3`。

\[
T_{cap}=round_{towardEntry}(p+s\,3d_S),\quad H_0=action\_at+3600s.
\]

H0 是绝对 UTC deadline，预提交即可确定；它不从 fill 重新起算且永不延长。label endpoint 包含 H0；submission expiry 使用右开区间，二者不得混淆。

## 8. 成本、EV、风险、margin 与 quantity

### 8.1 bps 到金额

线性 USDT perpetual 的 notional 为 `N(q,p)=q*p`。`Cost(q,p,b)=q*p*b/10000`。

Baseline：fee 5 bps/side；expected slippage 3 bps/side；stress slippage 10 bps/side；funding buffer 5 bps；tail 10 bps。

- expected entry/exit cost 用 `fee+3bps`；
- worst entry/exit cost 用 `fee+10bps`；
- `tail_unit(p)=Cost(1,p,5+10 bps)`，其中 funding 5 与 residual tail 10 在 ledger 分列、风险求和一次；
- 不得在 incurred、future exit 和 tail 中重复计费。

\[
r_{unit}(p)=\max(0,s(p-S_0))+Cost(1,p,15bps)+Cost(1,S_0,15bps)+Cost(1,p,15bps).
\]

### 8.2 Episode budget 与 caps

机会 anchor 时冻结 AccountRiskSnapshot：

\[
R_{episode}^{max}=equity\_usdt\cdot25/10000.
\]

Baseline equity 100000，因此为 250 USDT。盈利不得回收预算。

\[
B=R_{episode}^{max}-L_{realized}^{-}-R_{pendingExisting}.
\]

`R_pendingExisting` 在 candidate q 加入前计算，且只计一次：

\[
R_{pendingExisting}=\sum_o q_{unfilled,o}r_{unit}(p_o)+\sum_jR_{unprotected,j}.
\]

第一项精确包含所有 `ENTRY row.remainder_terminal=false` 的未成交 remainder，不以 REQUESTED/ACKED/UNKNOWN/CANCELED/REJECTED/EXPIRED lifecycle 名称提前释放。cancel/reject/expire 只先改变 lifecycle；必须再有 §11.3 规定的 post-terminal position/order reconcile 证明不可继续 fill，或该 entry 已 fully filled，remainder_terminal 才为 true、该项才释放。第二项包含 reconciled position 超出 effective protected quantity 的部分。已 fill quantity从第一项移除并进入 protected episode risk或第二项，禁止双计；exit order 不提供风险抵扣。

\[
Q_{risk}=B/r_{unit},\quad Q_{notional}=20000/p,
\]

\[
M_{available}=\max(0,availableBalance-existingIM-openOrderReserve-pendingFeeReserve),
\]

\[
Q_{margin}=M_{available}/(p\cdot0.5+Cost(1,p,15bps)),\quad Q_{venue}=10.
\]

由于 v0.2 first-fill pending cap 为 5 USDT 且 all caps must hold，未预挂 stop 的 baseline 还必须：

\[
Q_{firstPending}=5/r_{unit}.
\]

这会刻意限制 E0 研究 quantity；禁止以“可能很快 ACK”忽略 5 USDT cap。若该限制令 minimum notional 不可达，结果是 ABSTAIN，不得放宽 cap。

提交订单后，`q*r_unit` 进入 pending reserve。fill 后 entry fee 已进入实际扣款。对 §8.2 event-order inventory，`p_inv=V_inv/Q_inv` 当 Q_inv>0，否则 null；p_inv是当前 intended open inventory 的唯一平均执行 basis，后续 fill可改变它，冻结 Pe只保留 first-fill authorization/geometry身份。故唯一 post-fill unprotected risk 公式不再重复 prospective entry leg：

\[
R_{unprotected}=q_{unprotected}[\max(0,s(p_{inv}-S_0))+Cost(1,S_0,15bps)+tail\_unit(p_{inv})].
\]

INTENDED strategy cost inventory使用唯一的 event-order average-cost projection，而不是“全部历史 entry累计/累计量”。初始化 `Q_inv=V_inv=0`；每个 ENTRY positive delta `(dq,dn)` 后令 `Q_inv+=dq,V_inv+=dn`；每个 request row `quantity_projection_mode=INTENDED_FILL_PROJECTION` 的 EXIT positive delta前取 `p_inv=V_inv/Q_inv`（必须 `0<delta_qty<=Q_inv`），随后令 `V_inv-=delta_qty*p_inv,Q_inv-=delta_qty`，Q_inv归零时V_inv强制归零。即使该 order在后来的 ACCOUNT_MISMATCH 后 racing fill，inventory仍按其原 quantity mode减少，才能保持 `Q_inv=open_qty`；实际PnL basis另按下段 realized mode。每步均用 §1 decimal128。由此 later entry fill不会倒改已实现 loss，也不会把已经退出的旧成本重新混入 basis。

对每个 EXIT delta，`realized_basis_mode` 在 fill前 prefix从未发生 ACCOUNT_MISMATCH时等于 row quantity mode；一旦发生过 mismatch则固定为 OBSERVED_SIGNED_RISK。仅 realized mode=INTENDED 的 k 使用 strategy-side/p_inv并进入下式：

\[
L_{realized}^{-}=\sum_k\max(0,-s(\Delta exitQuote_k-\Delta exitQty_k\cdot p_{inv,k}^{pre})).
\]

realized mode=OBSERVED 的 EXIT（包括 mismatch前提交、mismatch后才 fill 的 legacy INTENDED row）不进入上式。只有 `pre_exit signed authority=KNOWN` 且 pre-exit vwap非 null时，才令 `risk_sign_k=sign(pre_exit reconcile.position_qty)`；严格 risk-reducing guard保证它为 +1/-1，并计算 `gross_delta_k=risk_sign_k*(delta_exit_quote_k-delta_exit_qty_k*pre_exit_position_vwap)`，realized loss加 `max(0,-gross_delta_k)`。只要 pre-exit signed authority=UNKNOWN 或 vwap为 null，旧 position_qty/vwap 即使仍作为 diagnostic byte-copy存在也不得读取为 basis：gross diagnostic固定0、record quality=UNKNOWN、realized loss保守计入完整 delta exit quote；该 fill后 authority仍为 UNKNOWN，不能据 stale projection声称已降险或已 flat。两种 realized mode 的 loss逐 delta 相加，均不得由盈利抵扣。

`C_incurredDebit` 唯一为整个 episode 截至当前已实际发生的全部正 fee、正 funding debit 与其他明确正扣款之和；每笔按 semantic event identity 只计一次，credit 一律按 0，不得抵减，也不得再塞入 `L_realized^-`。当前 p_inv 已包含全部仍开放 inventory 的 entry execution price，已退出部分又由 realized gross/loss处理，因此 entry price slippage不得作为第二笔 debit。past incurred debit 与 funding/tail/future-exit buffer分别代表已发生和未来风险，不是同一笔。任一时刻还必须满足完整 episode invariant：

\[
L_{realized}^{-}+C_{incurredDebit}+q_{protected}\max(0,s(p_{inv}-S_{ack}))+Cost(q_{protected},S_{ack},15bps)+q_{protected}tail_{unit}(p_{inv})+R_{pendingExisting}\le R_{episode}^{max},
\]

其中 `q_protected=min(reconciled_qty,effective_protected_qty)`；`reconciled_qty` 是 §11.1/§11.3 非负 QtyBase，不是 signed reconcile.position_qty。q_protected=0时所有含 p_inv/S_ack 的 protected terms不求值并固定为0；其余 reconciled quantity 必须恰好进入 R_pendingExisting 的 unprotected 项，不能遗漏或重复。

若有多个 ledger position slice，逐 slice 求和；不得用已实现盈利抵扣。任何 required risk component UNKNOWN 都是 `ABSTAIN`（提交前）或 `HALTED_RECONCILE`（持仓后）。

FIRST_FILL_PENDING 同时要求 `elapsed<=2s`、`q_unprotected<=q_auth`、`R_unprotected<=5`；EXCESS_FILL_PENDING 要求 `elapsed<=2s`、`q_excess<=0.1q_auth`、`R_unprotected<=5`。任一 cap 违反立即请求 reduce-only 全平并进入 `HALTED_RECONCILE`。

### 8.3 EV_submit、NO_FILL 与 95% LCB

P0-RSI-02/03 只实现纯函数；其 EV 输入是带摘要的 synthetic evidence。P0-RSI-04 若获授权，唯一 baseline estimator 为按 `(candidate_id,control_id,side,relative_anchor_bp_bucket)` 分组的 DEVELOPMENT-only expanding-window estimator。

`relative_anchor_bp_bucket=floor(10000*(p-A0)/A0)`，数学 floor，单位 1 bps。每个 past opportunity 对该 p 产生一个 terminal utility：

- NO_FILL：`Y=0`，同时只写 submission label；
- filled market path：`Y=net_usdt/(q*r_unit)`；
- operational override：使用实际/模拟 stress exit 的 net utility，并只写 execution override；
- `PARTIAL_FILL` 是 execution flag，不改变 terminal class。

Expanding sample 唯一规则：从获授权 DEVELOPMENT 起点开始，纳入 `terminal_at+label_tail<=current_decision_at`、bindings 完全相同、同 control/side/bucket、且不是当前 opportunity 的记录；按 `(terminal_at,opportunity_id,label_record_sha256)` 排序。sample weight 恒为 1，`n_eff=n`，禁止 decay、重采样或 outcome weight。同一 opportunity 在同 bucket 有多个 p 时，只保留 canonical tick index 最小的 replay candidate，避免重复加权；该 bucket 内所有当前 p 共用同一 evidence。`CENSORED` 且没有 operational stress utility 的记录不进入 n，但必须进入独立 coverage denominator；NO_FILL 与 OPERATIONAL_OVERRIDE 进入 n。任一 record binding、role 或 chronology 不一致即拒绝整份 evidence。

所有 Y 必须在 `[-1,3]`；越界表示 risk/cost simulator 与理论不一致，整个 candidate `INVALID_RISK_MODEL`，禁止裁剪。

为保证上界不是事后 clipping，research simulator 对 favorable price improvement 只按当时 ACK target（且不超过 Tcap）记账：LONG exit credit 为 `min(actual_fill_price,acked_target_or_tcap)`，SHORT 为 `max(actual_fill_price,acked_target_or_tcap)`；更有利的真实 improvement 只写 execution diagnostic，不进入 Y。stop gap、fee 或 operational loss 若仍使 Y<-1，不得裁剪，必须触发上述 INVALID_RISK_MODEL。

要求 `n>=30`。定义：

\[
EV_{submit}=\bar Y,\quad
LCB_{0.95}=\bar Y-4\sqrt{\ln(20)/(2n)}.
\]

这里 4 是 support width `3-(-1)`；NO_FILL 的零效用已明确进入均值。decision_at 必须落在 evidence 的 `[lane_available_at_us,expires_at_us]`。`Z_EV` 要求 `LCB>=0.05` R。n 不足、evidence stale、digest 不匹配、样本跨 lane/role、包含当前或未来 outcome、Y 越界均为 UNKNOWN，删除 p。

`n>=30` 只是单个 action bucket 可计算的最低条件，不替代 v0.2 acceptance 的总计至少 600 effective episodes、每方向至少 100、5 folds 中至少 4 folds 通过。未达到后者只能报告 coverage insufficient，不能把局部 Z_EV 计算写成候选通过。

为 log loss/Brier，terminal class enum 为 `NO_FILL,TP,SL,STRUCTURE_EXIT,TIMEOUT,OPERATIONAL_OVERRIDE`，使用 symmetric Dirichlet-1/2：`prob_k=(count_k+0.5)/(n+3)`。该概率不替代上面的 utility LCB。

`EV_hold(g)` 与 `EV_exit_now` 使用同样的 bounded expanding-window evidence，但 key 另加 `PROFIT_LOCKED` 与 extension bp bucket；n<30 时 target 不扩展。所有 evidence artifact 必须早于 decision time 冻结并有 Sha256。

## 9. Fill/protection/reconcile reducer

### 9.1 States、events 与默认规则

State enum：

`FLAT, ENTRY_PENDING, PROTECTION_PENDING, OPEN_PROTECTED_PRE_LOCK, PROFIT_LOCKED, EXIT_PENDING, CLOSED, HALTED_RECONCILE`。

Reducer context 还必须有 `resume_after_protection:enum{OPEN_PROTECTED_PRE_LOCK,PROFIT_LOCKED}|null`；仅 PROTECTION_PENDING 可非 null。first fill 固定为 OPEN_PROTECTED_PRE_LOCK；从已保护 state 因新未保护 quantity 进入 pending 时保存原 state。

`ReducerEventKind.v0.2.1` normative enum：

`CONTROL_ABSTAIN, ENTRY_SUBMIT, ENTRY_ACK, ENTRY_REJECT, ENTRY_EXPIRE, FILL_CUMULATIVE, CANCEL_REQUEST, CANCEL_ACK, CANCEL_REJECT_OR_UNKNOWN, STOP_REQUEST, STOP_ACK, STOP_REJECT_OR_UNKNOWN, TARGET_REQUEST, TARGET_ACK, TARGET_REJECT_OR_UNKNOWN, POSITION_SNAPSHOT, FUNDING_DEBIT, PENDING_DEADLINE, PROTECTION_REPAIR, ACCOUNT_MISMATCH, KILL, STOP_HIT, STRUCTURE_EXIT, TARGET_HIT, HORIZON, BARRIER_EVALUATION, REDUCE_ONLY_EXIT_REQUEST, EXIT_FILL_CUMULATIVE, EXIT_ACK, EXIT_REJECT_OR_UNKNOWN, RECONCILE_OK, DATA_HEALTH_INVALID, EVENT_CONFLICT, NO_CHANGE`。

CanonicalSyntheticEvent 的 payload exact keys：

| Event | Payload exact keys |
|---|---|
| NO_CHANGE | `reason_code:string` |
| CONTROL_ABSTAIN | `reason_code:enum{ANCHOR_UNKNOWN,NO_C1_EVENT,GATE_FALSE,GATE_UNKNOWN_AT_DEADLINE,ENTRY_ZONE_EMPTY,COMMON_CHECK_FAILED,EV_UNKNOWN,RISK_OR_MARGIN_FAIL,TTL_EXPIRED,EPISODE_TERMINAL,RULE_CHANGE}` |
| ENTRY_SUBMIT | `price:Price,qty:QtyBase,order_side:enum{BUY,SELL},expires_at_us:UtcUs,contract_sha256:Sha256,shared_entry_action_sha256:Sha256`；LONG=BUY，SHORT=SELL；price/qty/expires/shared hash逐字等于 matching SharedEntryAction 的 p_limit/submitted_qty/expires_at_us/entry_action_sha256，contract_sha256同时等于其 entry_contract_sha256 与 ledger_seed.policy_bindings.entry_contract_sha256 |
| ENTRY_ACK | `status:enum{ACKED},reason_code:string` |
| ENTRY_REJECT | `status:enum{REJECTED},reason_code:string` |
| ENTRY_EXPIRE | `status:enum{EXPIRED},reason_code:string` |
| FILL_CUMULATIVE / EXIT_FILL_CUMULATIVE | `cum_qty:QtyBase,cum_quote_notional:Money,fill_status:enum{PARTIAL,FILLED}` |
| CANCEL_REQUEST | `target_order_id:string` |
| CANCEL_ACK | `target_order_id:string,status:enum{CANCELED},reason_code:string` |
| CANCEL_REJECT_OR_UNKNOWN | `target_order_id:string,status:enum{REJECTED,UNKNOWN},reason_code:string` |
| STOP_REQUEST | `price:Price,qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,replaces_order_id:string|null,stop_role:enum{INITIAL_PROTECTION,PROTECTION_REPAIR,DYNAMIC_MANAGEMENT}`；reduce_only 必须 true |
| STOP_ACK | `price:Price,qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,status:enum{ACKED},replaces_order_id:string|null,stop_role:enum{INITIAL_PROTECTION,PROTECTION_REPAIR,DYNAMIC_MANAGEMENT}`；reduce_only 必须 true |
| STOP_REJECT_OR_UNKNOWN | `order_side:enum{BUY,SELL},status:enum{REJECTED,UNKNOWN},reason_code:string,replaces_order_id:string|null,stop_role:enum{INITIAL_PROTECTION,PROTECTION_REPAIR,DYNAMIC_MANAGEMENT}` |
| TARGET_REQUEST | `price:Price,qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,replaces_order_id:string|null,target_role:enum{FIXED_T0,DYNAMIC_MANAGEMENT}`；reduce_only 必须 true |
| TARGET_ACK | `price:Price,qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,status:enum{ACKED},replaces_order_id:string|null,target_role:enum{FIXED_T0,DYNAMIC_MANAGEMENT}`；reduce_only 必须 true |
| TARGET_REJECT_OR_UNKNOWN | `order_side:enum{BUY,SELL},status:enum{REJECTED,UNKNOWN},reason_code:string,replaces_order_id:string|null,target_role:enum{FIXED_T0,DYNAMIC_MANAGEMENT}` |
| POSITION_SNAPSHOT | `snapshot_id:StableId,account_scope_id:string,position_qty:DecimalString,position_vwap:Price|null,open_order_ids:array<string>,snapshot_sha256:Sha256`；event.input_artifact_ids 中必须恰好有一个 snapshot_id 匹配的 ACCOUNT_RISK_SNAPSHOT wrapper，六项分别等于该 artifact 的 snapshot_id/account_scope_id/position_qty_base/position_vwap/open_order_ids 与 wrapper.payload_sha256；account scope 必须等于 ledger；order IDs lex 排序；同一 bundle 可含多个不同时间的 snapshot artifact，但每个 snapshot event 只能绑定一个 |
| FUNDING_DEBIT | `funding_event_id:StableId,economic_event_time_us:UtcUs,interval_start_us:UtcUs,interval_end_us:UtcUs,funding_rate:DecimalString,position_side:enum{LONG,SHORT,FLAT,UNKNOWN},position_qty_basis:QtyBase,price_basis:Price,debit_usdt:Money`；`funding_event_id=ID("synthetic-funding/v0.2.1", {venue_id,instrument_id,interval_start_us,interval_end_us})`；input_artifact_ids必须恰好含唯一 SYNTHETIC_FUNDING_OBSERVATION artifact，event 的 funding_event_id/venue/instrument/economic time/interval/rate/price_basis 必须逐字段等于 artifact，且 `event_time_us=artifact.available_at_us`；同 causal time先应用 rank-2 fills，再从 signed risk-position重算 side/abs qty。signed authority已知时，qty=0当且仅当 side=FLAT且 debit="0"，LONG/SHORT必须 qty>0并取 signed qty符号，debit=`max(0,sign(side)*position_qty_basis*price_basis*funding_rate)`，LONG sign=+1、SHORT=-1；signed authority UNKNOWN时 side=UNKNOWN、qty=reconciled_qty（允许为0）、debit=`position_qty_basis*price_basis*abs(funding_rate)`作最坏正扣款，qty=0时 debit精确为"0"，但无论 qty是否为0都必须紧随 DATA_HEALTH_INVALID/FUNDING_BASIS_UNKNOWN |
| PENDING_DEADLINE | `deadline_kind:enum{FIRST_FILL_PENDING,EXCESS_FILL_PENDING,EXIT_PENDING},deadline_at_us:UtcUs` |
| PROTECTION_REPAIR | `required_protected_qty:QtyBase,effective_protected_qty:QtyBase,pending_deadline_us:UtcUs` |
| ACCOUNT_MISMATCH | `reason_code:string,details_sha256:Sha256,observed_position_qty:DecimalString|null,observed_position_vwap:Price|null,snapshot_id:StableId|null,account_scope_id:string|null`；只有 `quality=VALID`、wrapper.account_scope_id 与 ledger identity逐字相同的 trusted snapshot qty/VWAP/side mismatch 才允许 snapshot_id/account_scope_id/observed_position_qty 非 null，observed_position_vwap 当且仅当 qty非零时非 null，四项逐字段匹配 event.input_artifact_ids 中恰好一个 ACCOUNT_RISK_SNAPSHOT wrapper；无 snapshot artifact，或 snapshot quality 非 VALID，或 wrapper scope 不同的 non-trusting diagnostic mismatch，四项必须全 null |
| KILL / DATA_HEALTH_INVALID | `reason_code:string,details_sha256:Sha256` |
| STOP_HIT | `observed_exit_price:Price,barrier_price:Price,input_event_id:StableId,trigger_kind:enum{ACKED_STOP_PRICE,S0_VIRTUAL}` |
| STRUCTURE_EXIT | `observed_exit_price:Price,barrier_price:Price,input_event_id:StableId,trigger_kind:enum{I0,S_STRUCT_DIRECT,S_BE_DIRECT}` |
| TARGET_HIT | `observed_exit_price:Price,barrier_price:Price,input_event_id:StableId,trigger_kind:enum{ACKED_TARGET_PRICE,T0_VIRTUAL,T0_DIRECT,DYNAMIC_TARGET_DIRECT}` |
| HORIZON | `h0_us:UtcUs,input_event_id:StableId` |
| BARRIER_EVALUATION | `pivot_input_sha256:Sha256,target_input_sha256:Sha256,ev_evidence_sha256:Sha256|null`；令 `market_input_artifact_ids` 为 event.input_artifact_ids 中 BOOK_SNAPSHOT 与 SOURCE_COVERAGE_SEAL IDs 的排序数组，则 pivot hash=`ID("pivot-evaluation-inputs/v0.2.1", {event_time_us,market_input_artifact_ids,pivot_policy_id:"pivot-theta.v0.2.1"})`，target hash=`ID("target-evaluation-inputs/v0.2.1", {event_time_us,market_input_artifact_ids,target_policy_id:"target-boundary-theta.v0.2.1",ev_evidence_sha256})`；ev 非 null时必须唯一命中同 hash 的 FROZEN_EV_EVIDENCE artifact，否则必须 null |
| REDUCE_ONLY_EXIT_REQUEST | `qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,projection_mode:enum{INTENDED_FILL_PROJECTION,OBSERVED_SIGNED_RISK},reason_code:string`；reduce_only 必须 true；prefix无 ACCOUNT_MISMATCH且 fill projection matched 的正常 market/excess exit唯一用 INTENDED；任一 prior ACCOUNT_MISMATCH 后 signed authority已知非零时唯一用 OBSERVED，qty=`abs(reconcile.position_qty)`；authority未知或qty=0禁止方向性 request |
| EXIT_ACK | `status:enum{ACKED},qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,projection_mode:enum{INTENDED_FILL_PROJECTION,OBSERVED_SIGNED_RISK},reason_code:string` |
| EXIT_REJECT_OR_UNKNOWN | `status:enum{REJECTED,UNKNOWN},qty:QtyBase,order_side:enum{BUY,SELL},reduce_only:boolean,projection_mode:enum{INTENDED_FILL_PROJECTION,OBSERVED_SIGNED_RISK},reason_code:string` |
| RECONCILE_OK | `snapshot_id:StableId,account_scope_id:string,position_qty:DecimalString,position_vwap:Price|null,open_order_ids:array<string>,all_orders_terminal:boolean,reconcile_mode:enum{MATCH_FILL_PROJECTION,OPERATIONAL_FLAT_AFTER_MISMATCH},snapshot_sha256:Sha256`；snapshot六项映射同 POSITION_SNAPSHOT，all_orders_terminal由 ledger重算，order IDs lex 排序 |
| EVENT_CONFLICT | `original_event_id:StableId,original_payload_sha256:Sha256,incoming_payload_sha256:Sha256` |

trusted snapshot mismatch（即 payload.snapshot_id 非 null）令 `details_sha256=ID("account-mismatch-details/v0.2.1", {reason_code,account_snapshot_artifact_id,observed_position_qty,observed_position_vwap})`；四个 observed identity字段全 null 的 mismatch 统一令 `details_sha256=ID("account-mismatch-details/v0.2.1", {reason_code,predecessor_event_ids,input_artifact_ids})`，即使 input_artifact_ids 中含 quality/scope 不合格的 diagnostic snapshot wrapper也不例外。KILL/DATA_HEALTH_INVALID 唯一令 `details_sha256=ID("synthetic-fatal-details/v0.2.1", {event_kind,reason_code,predecessor_event_ids,input_artifact_ids})`。这些 preimage 只用 event 已有 causal IDs，不形成 payload/source hash 自引用；来料 details hash 不等即拒绝 bundle。

`SnapshotOrderSetValid(prefix,snapshot)` 是封闭谓词。snapshot.open_order_ids 中每项必须命中当前 local ledger 的 non-CANCEL order_id，CANCEL instruction row.order_id 与未知/其他 control ID 永远禁止出现。CANCELED/REJECTED/EXPIRED、fill_status=FILLED 或 remainder_terminal=true 的 row必须不出现。ACKED、未 fully filled、remainder_terminal=false 的 row必须出现，唯一例外是该 row正满足 §11.3 当前 snapshot terminal proof eligibility（自身 lifecycle UNKNOWN，或为 REJECTED/UNKNOWN failed-cancel target）；此时出现表示仍 open、不闭合，缺席才可作为 proof。REQUESTED/UNKNOWN row 的 membership按 snapshot原样作为权威 observation，但缺席只有在 §11.3 lifecycle/failed-cancel eligibility与position proof同时成立时才能令 remainder_terminal=true，不能仅凭 omission 猜 terminal。任一 unknown ID、required-active omission或forbidden ID出现使该 observation只能生成一个 ACCOUNT_MISMATCH/ORDER_SET_CONFLICT，禁止同时生成 POSITION_SNAPSHOT/RECONCILE_OK。OPERATIONAL_FLAT_AFTER_MISMATCH 先按 §11.3 base guard应用同一 proof exception，再判 full guard。

只有 `AccountRiskSnapshot.quality=VALID` **且** `wrapper.payload.account_scope_id=ledger_identity.account_scope_id` 才可进入 SnapshotOrderSetValid、POSITION_SNAPSHOT、RECONCILE_OK、remainder/operational-flat proof，或建立 observed signed qty/vwap authority。quality=INVALID/CONFLICT 或 account scope不等的 wrapper只能作为一个 non-trusting ACCOUNT_MISMATCH 的 input artifact：ACCOUNT_MISMATCH payload 的四个 observed identity字段必须全 null；reason_code 对应固定为 `SNAPSHOT_QUALITY_INVALID`、`SNAPSHOT_QUALITY_CONFLICT` 或 `SNAPSHOT_SCOPE_MISMATCH`，signed authority变 UNKNOWN。它不能读取该 artifact 的 qty/vwap/open orders发方向性 exit或闭合任何 remainder，且不得同 observation另放 POSITION_SNAPSHOT/RECONCILE_OK。details hash按上文“四字段全 null”公式绑定该 artifact ID。quality与scope同时不合格时 reason优先级固定 `SNAPSHOT_QUALITY_CONFLICT > SNAPSHOT_QUALITY_INVALID > SNAPSHOT_SCOPE_MISMATCH`，禁止 fixture选择。

trusted account snapshot 的“晚于”同时冻结经济轴与因果轴。定义 `AccountProofTime(e)`：positive `FILL_CUMULATIVE/EXIT_FILL_CUMULATIVE` 取其 non-null economic_event_time_us；ENTRY/STOP/TARGET/EXIT/CANCEL request、ACK/reject/expire/cancel lifecycle 取 causal event_time_us。每个 POSITION_SNAPSHOT、RECONCILE_OK 或 trusted snapshot ACCOUNT_MISMATCH 必须把它所证明结果依赖的全部 earlier positive fills，以及每个被 open_order_ids membership/absence、failed-cancel 或 terminal proof读取的最新 request/lifecycle event，直接列入 predecessor_event_ids；snapshot event在重算 total order中严格位于这些 predecessor之后。并且 wrapper.payload.effective_at_us 必须严格大于这些 required predecessors 的最大 `AccountProofTime`；相等也拒绝，因为本 contract没有独立 account sequence来证明同微秒先后。wrapper.available_at_us=payload.lane_available_at_us 且不得晚于 snapshot event.event_time_us。non-trusting diagnostic wrapper不证明 qty/order state，只受 availability 与 details binding约束。

同组 event 也必须使用表中 exact enum；event_kind 与 status 不匹配、extra/missing key 使 bundle 无效。`FILL_CUMULATIVE` 与 `EXIT_FILL_CUMULATIVE` 的 `fill_status=FILLED` 当且仅当该 order 的 `cum_qty=submitted_order_qty`，否则必须为 `PARTIAL`；position 是否为 0 只由 reconcile/position guard 决定，不能从 order FILLED 推断。`EXIT_ACK` 与 `EXIT_REJECT_OR_UNKNOWN` 的 reduce_only/order_side/qty/projection_mode/request/order identity 必须精确匹配 earlier `REDUCE_ONLY_EXIT_REQUEST`。无 mismatch 的正常 LONG STOP/TARGET/INTENDED exit order_side=SELL，正常 SHORT=BUY；任何 prior ACCOUNT_MISMATCH（包括同向 deficit/excess或仅VWAP不等）后禁止新 STOP/TARGET，只允许按最新已知 signed qty构造 OBSERVED_SIGNED_RISK reduce-only EXIT：qty>0 用 SELL、qty<0 用 BUY，request qty=abs qty；qty未知或为0禁止方向性 request并保持 HALTED_RECONCILE。payload 中不得再放第二份 request/order identity。

sealed bundle 内 source_event_id 必须唯一；重复 identity（无论 payload相同或不同）在 ledger 前拒绝。幂等性定义为完整同 bundle 重放得到同一 head，不是 live duplicate append。需测试 source conflict 时，fixture 必须显式给出 EVENT_CONFLICT 与 §2.9 的单一 SyntheticConflictProof artifact；仅 §9.4 明列的 FLAT pre-submit exception CLOSED/branch invalid，其余立即 HALTED_RECONCILE。下表未列出的 **state-changing** pair 一律 `ILLEGAL_TRANSITION -> HALTED_RECONCILE`；pure reducer不创建新 event。

### 9.2 同时间全序

event class rank：

1. `ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT`；
2. `FILL_CUMULATIVE/EXIT_FILL_CUMULATIVE/POSITION_SNAPSHOT`；
3. `FUNDING_DEBIT`；
4. `STOP_HIT`；
5. 与当前 protection request 精确匹配且 coverage sufficient 的 `STOP_ACK`；
6. `PENDING_DEADLINE/STOP_REJECT_OR_UNKNOWN/PROTECTION_REPAIR`；
7. `STRUCTURE_EXIT`；
8. `TARGET_HIT`；
9. `HORIZON`；
10. 其他 barrier/exit request/ACK/reject 与 `RECONCILE_OK`；
11. `CONTROL_ABSTAIN` 与 entry/cancel lifecycle；
12. `BARRIER_EVALUATION/NO_CHANGE`。

同 rank 再按 source_sequence、source_event_id。无法知道 OHLC 内先后时仍 `STOP_FIRST`。fill 先于同 reducer timestamp funding，funding 使用 fill 后 open qty；funding 又先于任何读取 costs/LockedNet 的 ACK、barrier evaluation 或 terminal，确保不会漏入决策。account kill 仍最优先。pending window 为 `[pending_started_at,pending_started_at+2s]` 右端包含；恰好 deadline 的 sufficient matching STOP_ACK 按 rank 5 先结束 pending，随后 deadline event成为 NO_CHANGE。非匹配、coverage 不足或晚于 deadline 的 ACK 不享受该优先级。

完整 reducer 全序只验证 §2.9 已封存 event_array：predecessor_event_ids 是显式 causal edge，所有 predecessor 处理后 event 才 ready；每步从 ready set 取 `(event_time_us,priority_rank,source_sequence,source_event_id)` 最小者。first-fill→cancel→stop、同刻 fill→funding、ACK→crossing、trigger→exit request 等 edge 可越过 rank，但必须已经存在于 bundle，reducer既不生成也不改序。missing/future predecessor、cycle、同 source identity不同 payload、或 event_array 与重算全序不等，bundle validator 直接拒绝；不能在 ledger 中临时补 EVENT_CONFLICT。

Entry order 的右开 expiry 使用 fill 的 `economic_event_time_us`：若 `economic_event_time_us>=expires_at_us`，bundle 必须含 causal time=`expires_at_us` 的 ENTRY_EXPIRE，并把该 expiry source_event_id 放入 late fill predecessor_event_ids，故先关闭 entry、再走 late-fill-after-terminal；不得凭 rank 2 抢先。经济时间<expiry但 causal-effective time晚到的 fill仍是经济上 in-window fill，只在其 causal event_time 被 reducer处理；若之前已有 explicit terminal lifecycle，则严格走 late-fill HALT，否则才进入正常 protection，均不得倒签。所有 submission descendant 的 causal-effective time必须严格晚于 action_at_us；仅当 economic_event_time_us 非 null时才还要求它严格晚于 action_at_us，command/timer 的 economic field仍为 null；缺 expiry edge或伪造先后直接拒绝 bundle。

### 9.3 Cumulative fill 与 pending clock

每个 order 维护 `last_cum_qty,last_cum_quote_notional`。新 cumulative 必须两者单调不减；delta 为新旧之差。qty 不变而 quote notional 改变、负 delta 或 cum qty 超过 submitted qty 均为冲突并 HALT。若两个 cumulative 值都与上一合法累计完全相同，则 delta=0，规范化为 NO_CHANGE：可记录这次不同 source identity 的合法重复累计，但不得改变 position、Pe/q_auth、clock、barrier、order fill status 或 reducer state；相同 source identity 仍走 §9.1 的 exact duplicate/conflict 规则。

首个 nonzero cumulative event：

`q_auth=cum_qty`，`Pe=cum_quote_notional/cum_qty`，两者永久冻结且均为正。后续 fill 不改变 Pe/q_auth。`open_qty` 只按 §11.3 entry fill与 INTENDED_FILL_PROJECTION exit delta；trusted normal snapshot 必须验证 signed qty=`s*open_qty`，不得覆写，operational-flat proof也只保留它作为诊断。异常 snapshot 由 ACCOUNT_MISMATCH 暴露独立 signed risk position与保守 reconciled_qty；risk/excess 使用 reconciled_qty，而成交损益按 §11.3 projection_mode。任何 `reconciled_qty>q_auth` 为 excess；任何 observed `s*position_qty<0` 是 side flip，不能用 abs 绕过。

`effective_protected_qty` 只统计已 ACK、reduce-only、side/stop-price/identity 有效且仍 active 的 stop quantity。`unprotected_qty=max(0,reconciled_qty-effective_protected_qty)`；`reconciled_qty` 始终为 §11.1 的非负保守 quantity，禁止改读 signed reconcile.position_qty。

pending clock 从“首个 nonzero fill 导致 unprotected_qty>0”或“fill-only open_qty 首次增加到 effective protected qty 之上”的 event_time 开始；若 fill-only quantity 增加但仍 `open_qty<=effective_protected_qty` 且无 side flip，只更新 reconcile，state/clock NO_CHANGE。后续事件不得重置或延长。若已有 pending deadline，新 deadline 取旧 deadline 与 `new_start+2s` 的较早者。FIRST_FILL_PENDING clock resolved 当且仅当可信 fill/reconcile projection 后 `open_qty=0` 或 `unprotected_qty=0`；EXCESS_FILL_PENDING clock resolved 当且仅当 `open_qty=0`，或同时满足 `unprotected_qty=0 AND excess_qty=0`。因此 fully protected 但仍 `reconciled_qty>q_auth` 的 excess 不能提前结束 EXCESS clock。若 active FIRST clock 期间出现 excess，kind 单向升级为 EXCESS_FILL_PENDING，start 保留较早 start、deadline 取较早值，并生成绑定两次 risk event 的新 EXCESS deadline identity；被取代的 FIRST timer 此后是 stale NO_CHANGE。kind 不得从 EXCESS 降回 FIRST。coverage 只可由 sufficient matching STOP_ACK 提高；open_qty 只可由已知匹配、projection_mode=INTENDED_FILL_PROJECTION 的 EXIT_FILL_CUMULATIVE 降低，OBSERVED_SIGNED_RISK fill只降低 signed risk position；POSITION_SNAPSHOT不能降低或覆写 open_qty。`open_qty=0` 只结束 clock，不推断正常 CLOSED；state transition 仍严格走 §9.4 的意外 flat/reconcile 分支。

`EXIT_PENDING` 使用独立 exit clock：在首个 REDUCE_ONLY_EXIT_REQUEST 或 market/horizon trigger 导致 reducer 发出该 request 的 event_time 启动，`deadline_at=start+2s`，kind=`EXIT_PENDING`；后续 request/ACK 不得重置。只有 reconciled position=0 使该 clock resolved，EXIT_ACK 不结束 clock。protection 与 exit clock 可同时存在，分别写 ledger 的四个独立 time fields，禁止互相覆盖。恰好 deadline 的 EXIT_FILL/POSITION_SNAPSHOT 按 rank 2 先处理；处理后仍非零才由 PENDING_DEADLINE 转 HALTED_RECONCILE。该 2 秒值在 v0.2.1 challenger set 为空。

任何 `PENDING_DEADLINE` 在轮到其 rank 时，若它精确引用的 clock 已 resolved或已被上述 kind upgrade 的新 timer 取代，必须先规范化为 stale-timer NO_CHANGE，并在当时 state 保持不变；该规则适用于 OPEN、PROFIT_LOCKED、EXIT_PENDING、HALTED_RECONCILE、CLOSED 等所有 state，不能落入 ILLEGAL_TRANSITION，也不能形成 operational override。只有尚未 resolved 且 event identity/kind/deadline 值匹配 ledger 当前 clock 的 timer 才进入 §9.4 failure branch；无法在 hash-chain 证明为已 resolved/已 superseded 的未知 identity 或值不匹配为 EVENT_CONFLICT。

### 9.4 完整转换表

本表术语 `任一持仓 state` 只展开为 `PROTECTION_PENDING,OPEN_PROTECTED_PRE_LOCK,PROFIT_LOCKED`，明确不含 ENTRY_PENDING、EXIT_PENDING、HALTED_RECONCILE 或 CLOSED。

本表裸写的 `position/remaining position` 唯一指 signed authority已知时的 `reconcile.position_qty`，`abs(position)` 是其绝对值，`position=0` 必须是 authority KNOWN 的 zero；authority UNKNOWN时这些 known-position guard全部不匹配并走 mismatch/HALT。裸写的 `reconciled position` 唯一指非负 `quantities.reconciled_qty`。fill projection正常时二者 magnitude相等；mismatch时禁止互换。

“必须动作/请求”是 bundle-validator obligation：对应 CanonicalSyntheticEvent 必须已按 §2.9 出现在 event_array并带正确 predecessor；pure reducer处理当前 event只更新投影，不发单、不插入 event。表中“直接生成/规范化为”一律解释为 fixture 必须直接提供该唯一 event kind，而非运行时转换 source message。

| Before | Event/guard | After | 必须动作 |
|---|---|---|---|
| 任意 state | FUNDING_DEBIT 且 semantic identity/basis/formula 有效 | 原 state | 只累计 debit/cost/risk；同 reducer timestamp 已先应用 rank-2 fill；不得直接成为 market terminal |
| FLAT | CONTROL_ABSTAIN 且没有 submission/fill/order reserve | CLOSED | 写唯一 abstain reason/time；不创建 order；release 零 reserve |
| FLAT | ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID 且尚无 ENTRY_SUBMIT/reserve | CLOSED | pre-submit ABSTAIN；不创建/cancel order；label=NO_ACTION、flags=[]、terminal 绑定 cause event |
| FLAT | EVENT_CONFLICT 且尚无 ENTRY_SUBMIT/reserve | CLOSED | decision=CONFLICT、branch invalid；不创建 order；label=NO_ACTION、flags=[]，只保留在 U/quality denominator |
| FLAT | POSITION_SNAPSHOT qty=0、identity/account scope 有效且尚无 ENTRY_SUBMIT/reserve | FLAT | observation NO_CHANGE；更新 snapshot hash，不产生 execution flag |
| FLAT | ACCOUNT_MISMATCH 且 observed_position_qty 非零 | CLOSED | pre-submit ABSTAIN；不接管任何既有仓位；同一 observation不得另放 POSITION_SNAPSHOT event |
| FLAT | ENTRY_SUBMIT 且 contract/qty/risk 全有效 | ENTRY_PENDING | reserve risk，写 submitted order identity |
| ENTRY_PENDING | ENTRY_ACK | ENTRY_PENDING | NO_CHANGE；保持 expiry |
| ENTRY_PENDING | ENTRY_REJECT 或 ENTRY_EXPIRE 且 cum fill=0 | CLOSED | lifecycle 先 terminal；reserve 继续保留到 §11.3 post-terminal reconcile 令 remainder_terminal=true；最终 submission label NO_FILL |
| ENTRY_PENDING | FILL_CUMULATIVE 首次 nonzero | PROTECTION_PENDING | freeze Pe/q_auth；立即 CANCEL_REQUEST，随后 STOP_REQUEST；启动 FIRST_FILL clock |
| ENTRY_PENDING | ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID | HALTED_RECONCILE | cancel、查询 position；若有仓位则 reduce-only exit |
| PROTECTION_PENDING | CANCEL_REQUEST 或 STOP_REQUEST | PROTECTION_PENDING | 记录 request；不切换 barrier、不延长 deadline |
| PROTECTION_PENDING | `(TARGET_REQUEST or matching TARGET_ACK) AND target_role=FIXED_T0`，或 BARRIER_EVALUATION | PROTECTION_PENDING | 记录 target/evaluation；fixed T0 ACK 可获 target authority但不提供 stop coverage，不结束 protection clock |
| PROTECTION_PENDING | `(TARGET_REQUEST or matching TARGET_ACK) AND target_role=DYNAMIC_MANAGEMENT` | PROTECTION_PENDING | 该 state 禁止 dynamic target authority；记录后请求 cancel；旧 target authority 不变 |
| PROTECTION_PENDING | 后续 FILL_CUMULATIVE，且 entry cancel 尚未 terminal | PROTECTION_PENDING | 不改 Pe/q_auth；检查 EXCESS caps；扩 stop request 至 reconciled qty；超 q_auth 请求 reduce-only excess |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | 后续 FILL_CUMULATIVE，且 entry cancel 尚未 terminal | PROTECTION_PENDING | 保存 resume state；检查 EXCESS caps；先扩 stop，再 reduce-only 回 q_auth |
| 任一 state（含 CLOSED） | 原 entry order 在 CANCEL_ACK/ENTRY_REJECT/ENTRY_EXPIRE 后出现新增 FILL_CUMULATIVE | HALTED_RECONCILE | 标记 LATE_FILL；立即 protect 可识别 position、reduce-only flatten、reconcile；不得返回正常 OPEN |
| EXIT_PENDING | 任一原 entry FILL_CUMULATIVE | HALTED_RECONCILE | 同 late/race fill：protect、reduce-only flatten、reconcile |
| PROTECTION_PENDING | CANCEL_ACK | PROTECTION_PENDING | lifecycle 变 CANCELED、order 不再 active；未成交 remainder risk 仍保留到 §11.3 post-cancel reconcile 令 remainder_terminal=true；不结束 protection clock |
| PROTECTION_PENDING | CANCEL_REJECT_OR_UNKNOWN | HALTED_RECONCILE | STOP 仍优先；查询并 reduce-only exit |
| PROTECTION_PENDING | matching STOP_ACK 且 stop_role=INITIAL_PROTECTION/PROTECTION_REPAIR、stop identity/price/reduce-only/qty 有效、coverage 足够、`0<abs(position)<=q_auth` 且无 side flip | resume state | 结束 pending；旧 barrier 切换为新 ACK barrier；若 resume=PROFIT_LOCKED 但复验 LockedNet<0，则降为 OPEN_PROTECTED_PRE_LOCK |
| PROTECTION_PENDING | matching STOP_ACK 且 stop_role=INITIAL_PROTECTION/PROTECTION_REPAIR、coverage 足够、`abs(position)>q_auth`、EXCESS caps 全部仍满足且无 side flip | PROTECTION_PENDING | 切换为新 ACK barrier；继续 reduce-only excess；保留较早 deadline，不得 resume |
| PROTECTION_PENDING | matching STOP_ACK 且 stop_role=INITIAL_PROTECTION/PROTECTION_REPAIR、coverage 不足 | PROTECTION_PENDING | 旧 ACK barrier 仍权威；补足请求；deadline 不延长 |
| PROTECTION_PENDING | matching STOP_ACK 且 stop_role=DYNAMIC_MANAGEMENT | PROTECTION_PENDING | 该 state 禁止动态管理 authority；记录后请求 cancel；旧 ACK barrier 与 protection clock 不变 |
| PROTECTION_PENDING | EXIT_ACK 且 reduce_only=true、qty/request/order 精确匹配已记录 excess reduce-only request | PROTECTION_PENDING | ACK 不等于 fill；继续 pending/reconcile |
| PROTECTION_PENDING | EXIT_REJECT_OR_UNKNOWN 且 reduce_only=true、qty/request/order 精确匹配已记录 excess reduce-only request | HALTED_RECONCILE | stop 仍权威；改发 emergency reduce-only flatten并 reconcile |
| PROTECTION_PENDING | matching TARGET_REJECT_OR_UNKNOWN（任一 target_role） | HALTED_RECONCILE | 归 BARRIER_ORDER_FAILURE；已有 stop barrier 仍权威，同时 reduce-only flatten并 reconcile |
| PROTECTION_PENDING | identity/source 已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 fill-only open qty 仍 `>q_auth`、单调下降、caps 仍满足且无 side flip；后续 snapshot 只可精确确认 | PROTECTION_PENDING | 更新 excess/reconcile；继续 reduce-only excess；deadline 不延长 |
| PROTECTION_PENDING | identity/source 已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 `0<open_qty<=q_auth`、unprotected_qty=0 且无 side flip；后续 snapshot 只可精确确认 | resume state | excess 清零并结束 pending；若 resume=PROFIT_LOCKED 则复验 LockedNet |
| PROTECTION_PENDING | identity/source 已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 `0<open_qty<=q_auth`、unprotected_qty>0 且无 side flip；后续 snapshot 只可精确确认 | PROTECTION_PENDING | excess 清零但 protection 未完成；补 stop，deadline 不延长 |
| PROTECTION_PENDING | identity已知且匹配的 EXIT_FILL_CUMULATIVE 造成 side flip | HALTED_RECONCILE | 标记 fill race；禁止新 stop/target，只按 observed signed qty发 side-correct reduce-only exit |
| PROTECTION_PENDING | identity已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 fill-only open_qty=0 | HALTED_RECONCILE | 标记 UNEXPECTED_FLAT_BEFORE_EXIT_PENDING；禁止静默 resume/CLOSED；完成 account/order reconcile |
| PROTECTION_PENDING | PROTECTION_REPAIR | PROTECTION_PENDING | 请求 stop coverage 到 reconciled qty；clock/deadline 不延长 |
| PROTECTION_PENDING | STOP_REJECT_OR_UNKNOWN、PENDING_DEADLINE 且 deadline_kind 为 FIRST_FILL_PENDING/EXCESS_FILL_PENDING，或任一对应 cap breach | HALTED_RECONCILE | reduce-only 全平并 reconcile |
| ENTRY_PENDING/PROTECTION_PENDING/OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | POSITION_SNAPSHOT source/identity 已知且匹配、无 side flip、与已处理 fills 一致、abs qty 未变化且未满足其他 specific guard | 原 state | 更新 reconcile hash；不得改变 Pe/q_auth |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | ACCOUNT_MISMATCH/POSITION_VS_FILL_PROJECTION | HALTED_RECONCILE | observed qty来自 snapshot artifact；禁止同步或覆写 open_qty；protect 可识别 qty并 emergency flatten；不得另放 POSITION_SNAPSHOT event |
| ENTRY_PENDING/任一持仓 state | ACCOUNT_MISMATCH/SNAPSHOT_SCOPE_MISMATCH | HALTED_RECONCILE | wrong-scope artifact仅是 diagnostic proof；四个 observed identity字段为 null、signed authority=UNKNOWN，禁止读取其 qty/vwap/orders，故不发方向性 request；不得另放 POSITION_SNAPSHOT event |
| ENTRY_PENDING/任一持仓 state | ACCOUNT_MISMATCH/SNAPSHOT_SIDE_CONFLICT，且 snapshot quality=VALID、scope逐字匹配 | HALTED_RECONCILE | 同 scope 的 side conflict建立 observed signed qty authority；禁止新 stop/target，只按 observed signed qty发 side-correct reduce-only exit；不得另放 POSITION_SNAPSHOT event |
| ENTRY_PENDING | ACCOUNT_MISMATCH/UNEXPLAINED_POSITION_BEFORE_FILL | HALTED_RECONCILE | protect 可识别 signed qty并 reduce-only flatten；不得另放 POSITION_SNAPSHOT event |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | matching STOP_ACK 且 stop_role=INITIAL_PROTECTION/PROTECTION_REPAIR、coverage sufficient | 原 state | 只更新 effective coverage；不得据此获得 dynamic barrier authority或首次 lock |
| OPEN_PROTECTED_PRE_LOCK | matching STOP_ACK 且 stop_role=DYNAMIC_MANAGEMENT、更新有效且 LockedNet<0 | OPEN_PROTECTED_PRE_LOCK | 只允许 signed stop 不下降 |
| OPEN_PROTECTED_PRE_LOCK | matching STOP_ACK 且 stop_role=DYNAMIC_MANAGEMENT、更新有效且 LockedNet>=0 | PROFIT_LOCKED | 记录首次 lock event |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | PROTECTION_REPAIR 且 unprotected_qty>0 | PROTECTION_PENDING | 保存 resume state；立即 STOP_REQUEST，启动 cap/deadline |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | PROTECTION_REPAIR 且 unprotected_qty=0 | 原 state | NO_CHANGE |
| OPEN_PROTECTED_PRE_LOCK | `(TARGET_REQUEST or matching TARGET_ACK) AND target_role=FIXED_T0` | OPEN_PROTECTED_PRE_LOCK | request 不切 authority；ACK 后记录固定 target，不得外移 |
| OPEN_PROTECTED_PRE_LOCK | `(TARGET_REQUEST or matching TARGET_ACK) AND target_role=DYNAMIC_MANAGEMENT` | OPEN_PROTECTED_PRE_LOCK | 该 state 禁止 dynamic target authority；记录后请求 cancel；固定 T0 继续权威 |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | STOP_REQUEST/BARRIER_EVALUATION | 原 state | NO_CHANGE，等待 matching STOP_ACK；旧 barrier 权威 |
| PROFIT_LOCKED | TARGET_REQUEST 且 `target_role in {FIXED_T0,DYNAMIC_MANAGEMENT}` | PROFIT_LOCKED | NO_CHANGE，等待 matching TARGET_ACK；旧 target barrier 权威 |
| OPEN_PROTECTED_PRE_LOCK | STOP_HIT/STRUCTURE_EXIT/TARGET_HIT/HORIZON | EXIT_PENDING | 按优先级发 reduce-only exit；PRE_LOCK target 不外移 |
| PROFIT_LOCKED | matching STOP_ACK 且 stop_role=DYNAMIC_MANAGEMENT，或 matching TARGET_ACK（target_role=FIXED_T0/DYNAMIC_MANAGEMENT） | PROFIT_LOCKED | 只在 ACK 后切 barrier；复验 LockedNet/geometry |
| PROFIT_LOCKED | STOP_HIT/STRUCTURE_EXIT/TARGET_HIT/HORIZON | EXIT_PENDING | reduce-only exit |
| PROTECTION_PENDING | STOP_HIT/STRUCTURE_EXIT/TARGET_HIT/HORIZON | EXIT_PENDING | 冻结 market/horizon exit reason并清空 resume_after_protection；保留/补 stop coverage并发 reduce-only exit；同时保留 protection clock、启动 exit clock |
| OPEN_PROTECTED_PRE_LOCK/PROFIT_LOCKED | REDUCE_ONLY_EXIT_REQUEST 且 projection_mode=INTENDED_FILL_PROJECTION | EXIT_PENDING | 冻结 exit reason；禁止新 barrier extension |
| OPEN_PROTECTED_PRE_LOCK 或 PROFIT_LOCKED | CANCEL/STOP/TARGET reject-or-unknown、ACCOUNT_MISMATCH、KILL、DATA_HEALTH_INVALID | HALTED_RECONCILE | 旧 barrier 仍权威，同时 reduce-only exit/reconcile |
| EXIT_PENDING | identity/source 已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 `abs(remaining position)>0`、abs qty 单调下降且无 side flip | EXIT_PENDING | 继续 reduce-only；禁止反手 |
| EXIT_PENDING | POSITION_SNAPSHOT source/identity 已知且匹配、`abs(position)>0`、与 processed fills 一致、无 side flip且不满足 exit_reconcile_mismatch_guard | EXIT_PENDING | 更新 reconcile；继续 reduce-only exit |
| EXIT_PENDING | PROTECTION_REPAIR 且 unprotected_qty>0 | EXIT_PENDING | 同时请求 stop coverage 和 reduce-only exit；启动/保持较早 pending deadline，breach 则 HALT |
| EXIT_PENDING | matching STOP_ACK 且 stop_role=INITIAL_PROTECTION/PROTECTION_REPAIR | EXIT_PENDING | 更新 effective protection；足量则 resolve protection clock，但不改变 frozen exit reason或 market-label barrier；stop 保留至 flat |
| EXIT_PENDING | matching STOP_ACK 且 stop_role=DYNAMIC_MANAGEMENT，或 matching TARGET_ACK | EXIT_PENDING | 不获得新 authority；记录后请求 cancel；继续 reduce-only exit |
| EXIT_PENDING | EXIT_ACK 且 reduce_only=true、qty/request/order 精确匹配已记录 exit request、`abs(remaining position)>0` 且无 side flip | EXIT_PENDING | ACK 不等于 flat；继续等待 fill/snapshot |
| EXIT_PENDING | RECONCILE_OK/MATCH_FILL_PROJECTION 且 `abs(remaining position)>0`、无 side flip且不满足 exit_reconcile_mismatch_guard | EXIT_PENDING | reconcile 不等于 flat；继续 reduce-only exit |
| EXIT_PENDING | identity/source 已知且匹配的 INTENDED_FILL_PROJECTION EXIT_FILL_CUMULATIVE 使 position=0 | EXIT_PENDING | 标记 `FLAT_AWAIT_RECONCILE`，cancel remaining barriers；尚不得 CLOSED |
| EXIT_PENDING | POSITION_SNAPSHOT source/identity 已知且匹配、position=0 且不满足 exit_reconcile_mismatch_guard | EXIT_PENDING | 标记 `FLAT_AWAIT_RECONCILE`，cancel remaining barriers；尚不得 CLOSED |
| EXIT_PENDING | EXIT_ACK 且 reduce_only=true、qty/request/order 精确匹配已记录 exit request、position=0 | EXIT_PENDING | 记录 exit order ACK/terminal state；保持 FLAT_AWAIT_RECONCILE |
| EXIT_PENDING | RECONCILE_OK/MATCH_FILL_PROJECTION 且 position=0、all_orders_terminal=false且不满足 exit_reconcile_mismatch_guard | EXIT_PENDING | cancel remaining orders并继续 reconcile；不得 CLOSED |
| EXIT_PENDING | RECONCILE_OK/MATCH_FILL_PROJECTION 且 position=0、所有 entry/stop/target/exit orders terminal且不满足 exit_reconcile_mismatch_guard | CLOSED | 写 final snapshot/hash 与 terminal reason |
| EXIT_PENDING | 已解决 protection clock 的 PENDING_DEADLINE 且 deadline_kind 为 FIRST_FILL_PENDING/EXCESS_FILL_PENDING | EXIT_PENDING | stale timer NO_CHANGE；不得改写 exit reason |
| EXIT_PENDING | 未解决 protection clock 的 PENDING_DEADLINE 且 deadline_kind 为 FIRST_FILL_PENDING/EXCESS_FILL_PENDING | HALTED_RECONCILE | 标记 PROTECTION_FAILURE；保留/补 stop并 emergency reduce-only flatten |
| EXIT_PENDING | PENDING_DEADLINE 且 deadline_kind=EXIT_PENDING、position=0 | EXIT_PENDING | resolved exit timer NO_CHANGE；保持 FLAT_AWAIT_RECONCILE |
| EXIT_PENDING | PENDING_DEADLINE 且 deadline_kind=EXIT_PENDING、`abs(position)>0` | HALTED_RECONCILE | exit pending 超时；重查 position，保持 reduce-only flatten |
| EXIT_PENDING | EXIT_REJECT_OR_UNKNOWN 且 reduce_only=true、qty/request/order 精确匹配已记录 exit request，或 CANCEL_REJECT_OR_UNKNOWN/STOP_REJECT_OR_UNKNOWN/TARGET_REJECT_OR_UNKNOWN/ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT | HALTED_RECONCILE | 重查 position，保持 reduce-only flatten |
| EXIT_PENDING | ACCOUNT_MISMATCH/EXIT_RECONCILE_MISMATCH | HALTED_RECONCILE | observed snapshot proof必须存在；禁止把 ACK 或 all-orders-terminal 当成 flat；不得另放 RECONCILE_OK/POSITION_SNAPSHOT event |
| HALTED_RECONCILE | FILL_CUMULATIVE/EXIT_FILL_CUMULATIVE、POSITION_SNAPSHOT、PROTECTION_REPAIR、任意 ACK/REJECT、REDUCE_ONLY_EXIT_REQUEST | HALTED_RECONCILE | signed authority=KNOWN 时 entry delta按 §11.3更新 risk、matching reduce-only exit必须严格降险；authority=UNKNOWN 时只记录 matching既有 order 的 fill与保守成本，保持 UNKNOWN且不得声称降险/flat；所有后续 outward intent只允许在最新 sign已知时保护或降低风险，禁止新 entry/barrier 扩展 |
| HALTED_RECONCILE | RECONCILE_OK/MATCH_FILL_PROJECTION 且 `open_qty=position=0`、所有订单 terminal，或 RECONCILE_OK/OPERATIONAL_FLAT_AFTER_MISMATCH 且 §11.3 guard成立 | CLOSED | episode 保留 halted/operational flag与 fill-only diagnostic，不可重开 |
| CLOSED | §11.3 precedence exception命中的 identity-known late entry/stop/target/exit/cancel lifecycle，且无 positive cumulative | CLOSED | 只追加 audit ledger NO_CHANGE；orders/authority/reconcile/terminal proof byte-copy，禁止 UNKNOWN→ACKED mutation或恢复 remainder/barrier/order |
| CLOSED | unknown/conflicting late lifecycle message | HALTED_RECONCILE | 标记 EVENT_CONFLICT，重新查询 account/orders；禁止新 entry |
| CLOSED | first qualifying POSITION_SNAPSHOT 或 RECONCILE_OK，当前仍有 remainder_terminal=false，满足 same-scope VALID 与 AccountProofTime，且应用 §11.3 snapshot proof 后 `position=0`、every(order.remainder_terminal)=true | CLOSED | 首次写 terminal confirmation 与 reconcile、释放 entry/order remainder reserve；保持原 NO_FILL/terminal reason，decision=RECONCILE、no_change=false；这不是重复 final reconcile |
| CLOSED | 已有上述 final proof 后，POSITION_SNAPSHOT 或 RECONCILE_OK 仍为 position=0、all_orders_terminal=true、source/identity 与 final reconcile exact consistent | CLOSED | ledger NO_CHANGE；byte-copy proof/reconcile并保持 terminal reason |
| CLOSED | POSITION_SNAPSHOT/RECONCILE_OK 其余任一组合 | HALTED_RECONCILE | 标记 EVENT_CONFLICT；重新查询 account/orders，禁止静默接受非零 position/active order |

STOP_REQUEST/TARGET_REQUEST 不切换 barrier authority；STOP_ACK 只有精确匹配 `(request_id,order_id,price,qty,order_side,reduce_only=true,replaces_order_id,stop_role,status=ACKED)` 的 STOP_REQUEST，TARGET_ACK 只有精确匹配 `(request_id,order_id,price,qty,order_side,reduce_only=true,replaces_order_id,target_role,status=ACKED)` 的 TARGET_REQUEST，才可依 state/role 切换 authority。target ACK 不替代 stop coverage。除 FLAT pre-submit exception 外，`EVENT_CONFLICT` 转 `HALTED_RECONCILE`。`NO_CHANGE` 在任意 state 保持 state，但仍须写 ledger，除非它是完全重复 source event。

任何未列 state-changing pair 的 fail-closed 动作也唯一：若 reconciled position 非零，先保留/请求 sufficient reduce-only stop，再发 reduce-only flatten、cancel entry remainder、查询 account/orders，转 HALTED_RECONCILE；若 position 为零，则 cancel 所有非 terminal order、查询并 reconcile，仍转 HALTED_RECONCILE。默认规则不得只改 enum 而省略保护动作。

异步但身份已知的 late lifecycle ACK 不应被误判为新风险：ENTRY_ACK、ENTRY_REJECT、ENTRY_EXPIRE、CANCEL_ACK 若在 PROTECTION_PENDING/OPEN/PROFIT_LOCKED/EXIT_PENDING 到达，且精确匹配已记录 request、cumulative fill 未增加，则 state 不变并只更新订单终态。若 reject/expire 与此前 ACK terminal 状态冲突，则仍为 EVENT_CONFLICT。STOP_ACK/TARGET_ACK 在 HALTED_RECONCILE 到达时不得重新获得 barrier authority；记录后只保留能降低风险的 stop，否则请求 cancel。EXIT_PENDING 按表中 stop_role/target_role 分支处理，任何 ACK 都不得改写 frozen exit reason。任何未知 request identity、ACK qty/price/stop_role/target_role 不一致或 late message 携带新增 fill，分别按 EVENT_CONFLICT 或 FILL_CUMULATIVE 处理，不能走 late-ACK no-op。

## 10. PivotTheta 与 TargetBoundaryTheta 的完整序列化

### 10.1 `PivotTheta.v0.2.1`

- evaluation grid：UTC 1 秒；
- window：`(t-300s,t]`；
- input：exit-side BookSnapshot，LONG=best bid，SHORT=best ask；
- eligible：lane-compatible、VALID、sequence_contiguous，并有覆盖完整 `(t-300s,t]` 的 CoverageSeal；每个 UTC 秒必须能选择 age<=1s 的最新 snapshot；最新 source event 距 t<=2s；缺任一 expected 秒点或 seal 不完整均为 UNKNOWN；
- extreme：LONG 取 minimum bid，SHORT 取 maximum ask；
- tie-break：`(lane_available_at_us,source_sequence,event_id)` 升序；
- buffer：`ceil_tickDistance(max(2*tick,1bps*J))`；
- output：`round_out(J-s*buffer)`；
- missing：`PIVOT_UNKNOWN -> NO_CHANGE`；若同时触发冻结 health rule，则 health rule 的 EXIT/HALT 优先，禁止替代 pivot。

该函数每秒可动态重算，但参数和算法不可在线变化。

`S_BE` 不再沿用 CORE 中把 first-fill Pe 当当前成本 basis 的简写。仅在 account_match=true、`open_qty=Q_inv>0`、p_inv非 null 时，令 `r_exit=15/10000`，`C_no_exit=fee_incurred_usdt+funding_incurred_usdt+funding_buffer_usdt+tail_usdt-realized_gross_usdt`，并解析含 exit fee 的闭式方程 `x=p_inv+s(C_no_exit/open_qty+x*r_exit)`：

\[
S_{BE,raw}=\frac{p_{inv}+s\,C_{noExit}/openQty}{1-s\,r_{exit}},\qquad
S_{BE}=round_{protective}(S_{BE,raw}).
\]

denominator 对 LONG/SHORT 分别为 `1-r_exit`/`1+r_exit` 且必须>0。round 后以 `Cost(open_qty,S_BE,15bps)` 重算 exit_worst 与 LockedNet；若 LockedNet<0、crossing、quality/health/geometry不合法则 S_BE 不可用。realized gross可影响“是否已锁定”，但仍禁止抵减 episode risk budget。p_inv是动态库存 basis；Pe只保留首次授权 geometry/label identity。

### 10.2 `TargetBoundaryTheta.v0.2.1`

同一 `(t-300s,t]` 1 秒 exit-side grid。候选只有：

1. `THREE_POINT_FAVORABLE_PIVOT`：对 LONG，`x_{u-1}<x_u` 且 `x_u>=x_{u+1}`；对 SHORT，`x_{u-1}>x_u` 且 `x_u<=x_{u+1}`；priority 0；
2. `WINDOW_FAVORABLE_EXTREME`：LONG 最大 bid、SHORT 最小 ask；priority 1。

需要完整的前后秒点；窗口首尾不能生成 three-point pivot。两类 identity 分开：

- three-point：`ID("target-three-point/v0.2.1", {side,u,rounded_price,input_artifact_ids:[u-1,u,u+1],coverage_seal_sha256})`；
- window extreme：先按 favorable extreme、再 `(lane_available_at,source_sequence,event_id)` 取唯一 winner，`ID("target-window-extreme/v0.2.1", {side,window_start_exclusive,window_end_inclusive,rounded_price,winner_event_id,coverage_seal_sha256})`。

window endpoint 可以成为 extreme，但永远不会冒充 three-point。g 先 `round_toward_entry`，随后必须同时满足：

- `s(g-T_ack)>0`；
- `s(g-T_ack)<=0.5*dS`；
- `0<s(g-Pe)<=s(Tcap-Pe)`；
- absolute 与 relative EV 规则；
- current price non-crossing；
- data/ack health valid。

选择 tie-break 沿用 v0.2。没有候选或 boundary UNKNOWN 为 NO_CHANGE；越过当前 executable exit price 直接 EXIT。E0 synthetic barrier ACK latency 固定为 1 秒：request 在 t，ACK 最早在 `t+1s` 生效，旧 barrier此前权威。任何 2 秒/分布式 latency 都属于 predictive validity 通过后的 execution-realism 新 contract；零延迟与真实 venue latency均不在 v0.2.1。

本节 target inequality 中的 Pe 是故意冻结的 first-fill geometry coordinate；它不参与 §8/§11 current-open risk、tail、S_BE 或 LockedNet basis，后者只能用 p_inv。

## 11. Immutable management ledger v0.2.1

### 11.0 `FrozenLedgerSeed.v0.2.1` 与 `FrozenActionContext.v0.2.1`

为避免在 anchor 时偷看未来 action，也避免把共享 entry 事实绑死到某个 control，context 分成两层。

`FrozenLedgerSeed` 在每个 U/control branch 的 Genesis 前产生。Top-level exact keys：`schema_version,opportunity_id,control_id,candidate_id,side,anchor_at_us,anchor_status,anchor_price,cost_basis,policy_bindings,seed_sha256`。

- `schema_version="rsi-mtf-drl-pm.frozen-ledger-seed.v0.2.1"`；identity 字段必须与 ledger identity 相等；`candidate_id` 必须按 §1.2；`side enum{LONG,SHORT,NONE}`，仅 C0 为 NONE；
- `anchor_at_us` 对所有 control（含 C0/最终 ABSTAIN）都必须逐字等于 master U evaluation time且禁止 null；`anchor_status enum{VALID,UNKNOWN}` 与 master U 相等。VALID 当且仅当 `anchor_price:Price` 非 null并等于 §5.2 选出的 executable anchor；UNKNOWN 当且仅当 anchor_price=null，且所有非 C0 branch 只能形成 `CONTROL_ABSTAIN/ANCHOR_UNKNOWN`，不能产生 ENTRY；
- `cost_basis` exact keys 为 `fee_bps_per_side:Bps,worst_slippage_bps_per_side:Bps,funding_buffer_bps:Bps,tail_bps:Bps`，baseline 分别为 `"5","10","5","10"`；
- `policy_bindings` exact keys 为 `entry_contract_sha256,exit_policy_template_sha256,risk_policy_sha256,cost_policy_sha256,label_policy_sha256`，全为 Sha256 并与新 contract 相等；
- `seed_sha256=ID("frozen-ledger-seed/v0.2.1", seed object excluding seed_sha256)`。

`FrozenActionContext` 只在非 C0 branch 首次形成 terminal ABSTAIN 或 ENTRY action 时产生；Genesis 时不存在。Top-level exact keys：`schema_version,ledger_seed_sha256,decision_kind,action_at_us,entry_mode,shared_entry_action_sha256,initial_levels,risk_basis,action_context_sha256`。最终 fill/lifecycle binding 不属于 action-time context，禁止把未来 binding digest 写入本对象。

- `schema_version="rsi-mtf-drl-pm.frozen-action-context.v0.2.1"`；`decision_kind enum{ABSTAIN,ENTRY}`；`entry_mode enum{NONE,OWN_ORDER,REPLAY_C4}`；
- ABSTAIN 的 `action_at_us` 是 §5.3 control clock 与 §9 全序下首个令该 branch 在 pre-submit FLAT 终止的 event_time；该 cause 可以是 CONTROL_ABSTAIN，也可以是 §9.4 的 ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT pre-submit branch；若因 TTL/UNKNOWN 到期则精确等于 deadline。其 entry_mode=NONE、shared_entry_action_sha256=null、initial_levels 的全部八项均 null、risk_basis 四项均为 `"0"`；不存在“保留或不保留 anchor”的选择，anchor 只在 seed；
- ENTRY/OWN_ORDER 的 action_at_us 等于 SharedEntryAction.action_at_us，shared_entry_action_sha256 非 null；ENTRY/REPLAY_C4 仅允许 control_id=C5，action_at_us 同样等于共享 C4 action且 shared_entry_action_sha256 必须相同。REPLAY_C4 的最终 C4 binding 只存在于 §2.9 bundle validator-only field 与 §12.2/label binding，不能进入 action context；
- ENTRY 的 `initial_levels` exact keys `anchor,p_limit,i0,g0,s0,t0,h0_us,tcap` 全部非 null并按 §6–§8重算；C5 与 C4 的 initial_levels byte-identical。`risk_basis` exact keys `submitted_qty,r_unit_usdt,r_episode_max_usdt,pending_existing_at_action_usdt`，按 §8 重算；C5 risk_basis 必须与 C4 byte-identical，H-013 只允许 exit policy不同；
- `action_context_sha256=ID("frozen-action-context/v0.2.1", action context excluding action_context_sha256)`。

C0 永远没有 FrozenActionContext，其规范 action_at_us 只在 C0 label 中固定为 seed.anchor_at_us；C0 只保留 Genesis，不消费 CanonicalSyntheticEvent。非 C0 的 first action record 写入 local action_context_sha256，之后不可改变。C4/C5 可以有不同 local action context hash；它们只共享 §12.2 的 entry action/binding，不共享 management/exit context。

### 11.1 Exact record schema

每条记录所有 top-level key 必须存在：

`schema_version`、`ledger_id`、`sequence`、`event_id`、`source_event_id`、`source_sequence`、`parent_event_id`、`previous_hash`、`record_hash`、`bindings`、`identity`、`side`、`action_context_sha256`、`event_kind`、`state_before`、`state_after`、`times`、`inputs`、`levels`、`quantities`、`risk`、`orders`、`costs`、`reconcile`、`decision`、`operator`。

Exact nested schema：

- scalar identity：`schema_version="rsi-mtf-drl-pm.management-ledger.v0.2.1"`、`ledger_id/event_id:StableId`、`sequence:int>=0`、`source_event_id/parent_event_id:StableId|null`、`source_sequence:int>=0|null`、`previous_hash/record_hash:Sha256`、`side:enum{LONG,SHORT,NONE}`、`event_kind` 为 `GENESIS` 或 §9.1 enum、`state_before/state_after` 为 §9.1 state enum；
- `bindings` exact keys：`core_raw_sha256,v0_2_contract_canonical_sha256,addendum_raw_sha256,v0_2_1_contract_sha256,policy_sha256,code_sha256,data_or_fixture_sha256,ledger_seed_sha256`，全为 Sha256；前三项必须分别等于 §0 的 CORE raw、新 v0.2.1 contract 所绑定的旧 v0.2 full canonical 与本 addendum raw digest；ledger_seed_sha256 必须等于 §11.0 seed digest；
- `identity` exact keys：`venue_id:string,instrument_id:string,lane_id:string,account_scope_id:string,role:enum{SYNTHETIC,DEVELOPMENT,CALIBRATION,HOLDOUT,PAPER,TRADING},episode_id:StableId,opportunity_id:StableId,control_id:enum{C0,C1,C2,C3,C4,Cmu,C5},candidate_id:StableId`；account_scope_id非空，并与 anchor/action snapshot以及所有用于 POSITION_SNAPSHOT、RECONCILE_OK、trusted observed-risk ACCOUNT_MISMATCH 的 post-submit AccountRiskSnapshot逐字相等。唯一允许 scope不等的 post-submit wrapper 是 §9.1 `SNAPSHOT_SCOPE_MISMATCH` non-trusting diagnostic artifact；它不得建立 observed authority或关闭 remainder。同一 episode 的全部 controls及 C4/C5 cohort必须共享 ledger account_scope_id；candidate_id 按 §1.2，P0-RSI-02/03 role只能 SYNTHETIC；
- `action_context_sha256:Sha256|null`；Genesis 与 first action 前必须 null；非 C0 first action record 等于 local FrozenActionContext digest，之后 byte-copy；C0 永远 null；
- `times`：`event_time_us,lane_available_at_us,decision_at_us,evaluated_at_us,written_at_us`，全为 UtcUs；
- `inputs`：`input_ids:array<StableId>,input_bundle_sha256:Sha256,quality enum{VALID,UNKNOWN,INVALID,CONFLICT}`；input_ids 视为 set，去重后按 StableId 小写 hex 字典升序排列；
- `levels`：`anchor,p_limit,pe,i0,g0,s0,stop_before,stop_after,t0,target_before,target_after,h0_us,tcap,current_exit_price`；价格字段为 Price 或 null，仅 `h0_us` 为 UtcUs 或 null；
- `quantities`：`submitted_qty,q_auth,open_qty,reconciled_qty,effective_protected_qty,unprotected_qty,excess_qty`，DecimalString，未发生时使用字符串 `0`，禁止 null；
- `risk`：`r_unit_usdt,r_episode_max_usdt,realized_loss_usdt,pending_existing_usdt,pending_unprotected_usdt,locked_net_usdt,protection_pending_kind,protection_pending_started_at_us,protection_pending_deadline_us,exit_pending_started_at_us,exit_pending_deadline_us`；金额为 DecimalString；`protection_pending_kind:enum{FIRST_FILL_PENDING,EXCESS_FILL_PENDING}|null`，四个时间允许 null；kind 与 protection 两个时间必须全 null 或全非 null；两个 clock 可并存，单个 pending episode 内禁止重置或互相覆盖，唯 §9.3 FIRST→EXCESS 单向升级允许保留较早 start/deadline并更换 kind；旧 episode resolved 后，只有新的 fill/position increase 才可创建新 protection clock，并必须产生新的 deadline event identity；
- `orders`：array，元素 exact keys `role enum{ENTRY,CANCEL,STOP,TARGET,EXIT},stop_role:enum{INITIAL_PROTECTION,PROTECTION_REPAIR,DYNAMIC_MANAGEMENT}|null,target_role:enum{FIXED_T0,DYNAMIC_MANAGEMENT}|null,exit_projection_mode:enum{INTENDED_FILL_PROJECTION,OBSERVED_SIGNED_RISK}|null,order_id:string,request_id:string,order_side:enum{BUY,SELL}|null,lifecycle_status enum{REQUESTED,ACKED,CANCELED,REJECTED,EXPIRED,UNKNOWN},fill_status enum{NONE,PARTIAL,FILLED},price:Price|null,qty:QtyBase,reduce_only:boolean,cum_qty:QtyBase,cum_quote_notional:Money,remainder_terminal:boolean,terminal_confirmed_by_snapshot_id:StableId|null`；CANCEL row 的 order_side=null，其余非 null；当且仅当 role=STOP 时 stop_role 非 null，当且仅当 role=TARGET 时 target_role 非 null，当且仅当 role=EXIT 时 exit_projection_mode 非 null，其余这些 role-specific字段必须 null；按 `(role,stop_role null-first,target_role null-first,exit_projection_mode null-first,order_id,request_id)` 排序；
- `costs`：`realized_gross_usdt,fee_incurred_usdt,funding_incurred_usdt,entry_slippage_usdt,exit_worst_usdt,funding_buffer_usdt,tail_usdt`，均 DecimalString；
- `reconcile`：`snapshot_id:StableId|null,snapshot_sha256:Sha256|null,position_qty:DecimalString,position_vwap:Price|null,account_match:boolean|null,all_orders_terminal:boolean`；
- `decision`：`reason enum{GENESIS,NO_CHANGE,ACTION,ABSTAIN,EXPIRE,FILL,PROTECT,LOCK,EXIT,HALT,RECONCILE,CONFLICT},priority_rank:int>=0,barrier_authority:BarrierAuthority,resume_after_protection enum{OPEN_PROTECTED_PRE_LOCK,PROFIT_LOCKED}|null,no_change:boolean,duplicate_of_event_id:StableId|null,conflict_with_event_id:StableId|null`；`BarrierAuthority` exact keys 为 `stop,target`，两者各为 `enum{NONE,OLD_ACKED,NEW_ACKED}`，因此同时存在 stop 与 target 时无单值歧义；
- `operator`：exact object 固定为 `{kind:"SYSTEM",id:"rsi-mtf-drl-pm-reducer-v0.2.1"}`，synthetic/replay/data role 只由 immutable identity.role 与 bindings 表达，不改变规范 record bytes。

`source_event_id`、`parent_event_id`、`source_sequence` 只允许在 GENESIS 为 null；其他记录必须非 null。所有数组即使为空也写 `[]`，禁止省略。

### 11.2 Genesis、hash、sealed ordering 与 conflict proof

Genesis 不消费 CanonicalSyntheticEvent。先计算 `ledger_id=ID("management-ledger/v0.2.1", {bindings,venue_id,instrument_id,lane_id,account_scope_id,role,episode_id,opportunity_id,control_id,candidate_id})`；这些 identity 字段创建后不可变。然后 `genesis_event_id=ID("management-genesis/v0.2.1", {ledger_id,bindings,identity})`。令 `genesis_at_us` 精确等于 master U 的 anchor_at_us。GenesisRecord 的每个字段唯一如下，禁止使用实现默认值：

- scalar：`schema_version="rsi-mtf-drl-pm.management-ledger.v0.2.1"`、`ledger_id` 如上、`sequence=0`、`event_id=genesis_event_id`、`source_event_id=null`、`source_sequence=null`、`parent_event_id=null`、`previous_hash` 为 64 个字符 `0`、`action_context_sha256=null`、`event_kind="GENESIS"`、`state_before="FLAT"`、`state_after="FLAT"`；`record_hash` 最后按本节公式计算；
- `bindings` 与传入 exact bindings byte-identical；`identity` 与 ledger_id preimage 的 exact identity object byte-identical；`side="NONE"` 当且仅当 control_id=C0，否则等于该 branch 的 LONG/SHORT；
- `times={event_time_us:genesis_at_us,lane_available_at_us:genesis_at_us,decision_at_us:genesis_at_us,evaluated_at_us:genesis_at_us,written_at_us:genesis_at_us}`；
- `inputs={input_ids:[],input_bundle_sha256:ID("management-genesis-inputs/v0.2.1", {ledger_id,opportunity_id,control_id,side,genesis_at_us}),quality:"VALID"}`；
- `levels={anchor:null,p_limit:null,pe:null,i0:null,g0:null,s0:null,stop_before:null,stop_after:null,t0:null,target_before:null,target_after:null,h0_us:null,tcap:null,current_exit_price:null}`；
- `quantities={submitted_qty:"0",q_auth:"0",open_qty:"0",reconciled_qty:"0",effective_protected_qty:"0",unprotected_qty:"0",excess_qty:"0"}`；
- `risk={r_unit_usdt:"0",r_episode_max_usdt:"0",realized_loss_usdt:"0",pending_existing_usdt:"0",pending_unprotected_usdt:"0",locked_net_usdt:"0",protection_pending_kind:null,protection_pending_started_at_us:null,protection_pending_deadline_us:null,exit_pending_started_at_us:null,exit_pending_deadline_us:null}`；
- `orders=[]`；
- `costs={realized_gross_usdt:"0",fee_incurred_usdt:"0",funding_incurred_usdt:"0",entry_slippage_usdt:"0",exit_worst_usdt:"0",funding_buffer_usdt:"0",tail_usdt:"0"}`；
- `reconcile={snapshot_id:null,snapshot_sha256:null,position_qty:"0",position_vwap:null,account_match:null,all_orders_terminal:true}`；
- `decision={reason:"GENESIS",priority_rank:12,barrier_authority:{stop:"NONE",target:"NONE"},resume_after_protection:null,no_change:true,duplicate_of_event_id:null,conflict_with_event_id:null}`；
- `operator={kind:"SYSTEM",id:"rsi-mtf-drl-pm-reducer-v0.2.1"}`。

上述 constructor 也适用于 C0；因此 C0 Genesis head 不存在第二种合法 byte representation。master terminal 若与 anchor 同 timestamp，仍先创建 U/C0 Genesis，再按 §9 rank-1 关闭非 C0 branch；它不能阻止或改写已确定的 Genesis。

record hash：

\[
recordHash=SHA256("management-ledger-record/v0.2.1"||0x00||CanonicalJSON(record\ without\ record_hash)).
\]

sequence 必须从 0 连续加一；previous_hash 必须等于前一 record_hash。第一条非 Genesis record 的 parent_event_id 必须是 genesis_event_id；以后 parent_event_id 等于严格早于当前 record 的最近一条 state-changing event_id，若此前只有 NO_CHANGE 则仍指 Genesis。NO_CHANGE 不改写 parent root。重放顺序严格等于 §2.9 event_array，不使用 written_at 排序。必须满足 `event_time_us<=lane_available_at_us<=decision_at_us<=evaluated_at_us<=written_at_us`；synthetic baseline前两者相等，§11.3令后三者也相等，避免 wall-clock。incremental live append/reorder未授权；未来真实 append/write必须发布新 semantic version与constructor。

非 Genesis 的 `event_id=ID("management-event/v0.2.1", {ledger_id,event_kind,source_event_id})`。sealed event_array 内 source_event_id 必须唯一；任何 exact duplicate 或 same-ID drift 均在 ledger 构造前使 bundle 无效。对完整同 bundle 重放必须返回 byte-identical chain/head，这就是 v0.2.1 的幂等性。EVENT_CONFLICT 只能作为 bundle 已显式提供且由 §2.9 单一 conflict-proof artifact 验证的 event；其 management event_id 仍使用上述统一公式。禁止 incremental last-write-wins。

### 11.3 非 Genesis canonical constructor

本节唯一入口是已通过 §2.9 validator 的完整 `CanonicalSyntheticEventBundle.v0.2.1`。不接受 `(prev,event)` 增量调用、source messages、未终结 prefix 或 bundle 外 lookup；每次从 Genesis 重放到最终 CLOSED。`ledger_bindings/ledger_identity/ledger_seed` 必须 byte-exact 用于 §11.2 ledger_id/Genesis，action context 与 entry binding遵循 bundle scope；任何 digest、event、artifact 或 coverage 不闭合直接 `BLOCKED_SYNTHETIC_BUNDLE`，不产生部分 ledger。

constructor 先验证 bundle/coverage/event_set hash、全部 artifact、predecessor、显式全序与 §2.9 causal obligations，再从 seed 创建 Genesis并逐项处理 event_array。当前 record 的 `prev` 永远是本次重放刚生成的前一 record，`e` 是当前 CanonicalSyntheticEvent。context 用唯一两阶段映射：`ctx_prev=bundle.action_context` 当且仅当 prev.action_context_sha256 非 null且 digest相等，否则 null；`activates_now=true` 当且仅当 ctx_prev=null，且 e 是首个使 FLAT pre-submit CLOSED 的 `CONTROL_ABSTAIN/ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT`（bundle context.decision_kind=ABSTAIN），或 e 是 first ENTRY_SUBMIT（decision_kind=ENTRY）。activation还必须 `e.event_time_us=bundle.action_context.action_at_us` 并满足 §11.0 mode/control约束；其他 event绝不激活。令 `ctx_current=bundle.action_context` if activates_now else ctx_prev。当前 record 的 input hash、scalar action_context_sha256、levels/risk/reducer读取全部使用 ctx_current；pre-activation record完全看不到 bundle context，activation后的后续 record byte-copy digest。entry_execution_binding 是 validator/label-only：reducer只能读取当前和 earlier shared_entry_event_id，禁止读取 trace 中 future fill、Pe/q_auth/cost。

对当前 e，artifact descriptor exact keys 为 `input_id,payload_sha256,lane_available_at_us,quality`：每个 e.input_artifact_id 从 bundle.artifacts 取 hash；causal artifact lane time取 available_at_us，static artifact唯一取 seed.anchor_at_us，且都不得晚于 e.event_time_us。ArtifactSchemaId 到 descriptor quality 的映射封闭如下：`CLOSED_MARK_BAR/BOOK_SNAPSHOT/AGG_TRADE/OPEN_INTEREST/VENUE_INSTRUMENT_SNAPSHOT/ACCOUNT_RISK_SNAPSHOT/SYNTHETIC_FUNDING_OBSERVATION` 取 payload.quality 并按 VALID/GAP/INVALID/CONFLICT 同名映射（GAP→UNKNOWN）；`SOURCE_COVERAGE_SEAL` 在 complete=true且 gap=[] 时 VALID，任一 gap.reason=CONFLICT 时 CONFLICT，其余 incomplete/ordinary gap 为 UNKNOWN；`FROZEN_EV_EVIDENCE/PI_EXIT_POLICY/FIRST_HIT_LABEL_POLICY/SHARED_ENTRY_ACTION/EXIT_POLICY_INSTANCE/C4_C5_EXOGENOUS_PATH_MANIFEST` 在 exact schema/hash/binding 验证通过后为 VALID；`SYNTHETIC_CONFLICT_PROOF` 固定为 CONFLICT。枚举外无 fallback，malformed artifact 在 bundle validation 已拒绝，不能映射成 UNKNOWN。每个 predecessor读取 earlier event payload hash与 record quality。全部 descriptor按 input_id排序。然后计算：

```
source_envelope_sha256 = ID("canonical-synthetic-event-envelope/v0.2.1", e)
source_quality = CONFLICT  if e.event_kind=EVENT_CONFLICT
                 INVALID   if e.event_kind in {DATA_HEALTH_INVALID,ACCOUNT_MISMATCH}
                 UNKNOWN   if e payload status=UNKNOWN
                 VALID     otherwise
all_descriptors = sort_by_input_id(
  [{input_id:e.source_event_id,payload_sha256:e.payload_sha256,
    lane_available_at_us:e.lane_available_at_us,quality:source_quality}] + referenced_descriptors)
inputs.input_ids = [d.input_id for d in all_descriptors]
inputs.input_bundle_sha256 = ID("management-record-inputs/v0.2.1", {
  bundle_scope_id:bundle.bundle_scope_id,
  ledger_seed_sha256:bundle.ledger_seed.seed_sha256,
  action_context_sha256:(ctx_current==null ? null : ctx_current.action_context_sha256),
  previous_hash:prev.record_hash,
  source_event_sha256:source_envelope_sha256,
  descriptors:all_descriptors
})
inputs.quality = max_severity(all_descriptors.quality,
                              CONFLICT>INVALID>UNKNOWN>VALID)
```

descriptor IDs 必须恰好等于 `e.predecessor_event_ids ∪ e.input_artifact_ids ∪ {e.source_event_id}`。未列 state-changing pair 不改写 event_kind，而以 attempted `(state,event_kind)` 唯一执行 §9.4 fail-closed action，decision.reason=HALT，并在 label cause 中记 ILLEGAL_TRANSITION；其后所需 emergency intent也必须已在 bundle中显式存在。

scalar 与 time 字段唯一映射：schema/ledger/bindings/identity/side 从 prev byte-copy；action_context_sha256 等于 ctx_current digest或null；sequence=prev.sequence+1；previous_hash=prev.record_hash；source_event_id/source_sequence/event_kind 从 e；event_id 按 §11.2；state_before=prev.state_after，state_after=§9.4 reducer 结果；parent_event_id 按 §11.2 最近 state-changing event；`times={event_time_us:e.event_time_us,lane_available_at_us:e.lane_available_at_us,decision_at_us:e.lane_available_at_us,evaluated_at_us:e.lane_available_at_us,written_at_us:e.lane_available_at_us}`；operator 固定为 §11.1 exact object。该映射也适用于 synthetic/replay，禁止 wall clock。

以下 projection 全部从“截至当前 event 的已排序 ledger prefix”重算，而不是相信调用方提供的 post-state。先把 prev 的 end authority 定义为 prev.levels.stop_after/target_after 与 prev.orders 的 active status，再按当前 event 应用 §9.4。record 的 nested fields唯一如下。

**levels**

- 在 ENTRY_SUBMIT 前，除已存在的 event-relative barrier 字段外，`anchor,p_limit,i0,g0,s0,t0,h0_us,tcap` 均为 null；first ENTRY_SUBMIT（OWN_ORDER 或 REPLAY_C4）时一次性从 ctx_current.initial_levels 复制，之后 byte-copy，禁止清空或修改；
- pe 在首个 nonzero FILL_CUMULATIVE 按 §9.3 设置，此后 byte-copy；
- `stop_before/target_before` 等于处理 e 前的 active ACK authority price；无 active ACK authority 为 null。`stop_after/target_after` 等于处理 e 后的 active ACK authority price；request、reject、direct/virtual hit 均不自行建立 authority；
- active ACK order 当且仅当 lifecycle_status=ACKED、fill_status!=FILLED 且 remainder_terminal=false。stop authority 是允许的 active ACK stop 中 `s*price` 最大者，tie 依次取较早 ACK total-order position、较小 order_id；target authority 是 frozen T0 ACK 或 TargetUpdateRule 最近一次获准替换后的 active ACK target；任何 dynamic TARGET_REQUEST 必须以 replaces_order_id 指向当时 authority，若 ACK 后产生两个不在同一 replacement chain 的 active target，立即 EVENT_CONFLICT；
- `current_exit_price` 对 STOP_HIT/STRUCTURE_EXIT/TARGET_HIT 等于 payload.observed_exit_price；对 HORIZON 等于 payload.input_event_id 所指 H0 BookSnapshot 的 side-specific executable exit price；其余 event 必须 null。fixed S0/T0 virtual level 只在 s0/t0 字段，不伪装成 ACK authority。

**orders 与 quantities**

- 从 prefix 的 request/lifecycle/cumulative events重放 orders。ENTRY/STOP/TARGET/EXIT request 各创建 matching role row：lifecycle_status=REQUESTED、fill_status=NONE、remainder_terminal=false、terminal_confirmed_by_snapshot_id=null，order_side/price/qty/reduce_only逐字取 request；EXIT 还复制 projection_mode 到 exit_projection_mode，其他 role该字段null。CANCEL_REQUEST 创建 CANCEL row，order_side=null、price=null、qty="0"、reduce_only=false且三个 role-specific字段全null，其余初值相同；
- lifecycle 合法矩阵唯一为：REQUESTED/UNKNOWN + matching ACK→ACKED；REQUESTED/UNKNOWN + matching REJECT→REJECTED；REQUESTED/ACKED/UNKNOWN + matching CANCEL_ACK→CANCELED；ENTRY 的 REQUESTED/ACKED/UNKNOWN + ENTRY_EXPIRE→EXPIRED；REQUESTED/ACKED + matching UNKNOWN→UNKNOWN；同一 status 的重复 message为 NO_CHANGE。唯一 precedence exception：state=CLOSED 且 matching row.remainder_terminal=true 时（无论 terminal_confirmed_by_snapshot_id 是 non-null snapshot proof，还是因 fill_status=FILLED/terminal CANCEL 而为 null），identity精确匹配、若忽略 CLOSED exception本可命中上述合法 lifecycle matrix、且不伴随 positive cumulative 的 late ENTRY/STOP/TARGET/EXIT ACK/reject/expire 或 CANCEL ACK/reject/unknown只写 audit ledger record，orders、barrier authority、reconcile与 terminal proof全部 byte-copy，decision=NO_CHANGE；它不得把 REQUESTED/UNKNOWN 改 ACKED或重新打开 remainder。identity不匹配或原矩阵本就非法的 status conflict仍 EVENT_CONFLICT；任何 later positive cumulative 先清旧 proof并按 late fill HALT。除此以外，已在 CANCELED/REJECTED/EXPIRED 后任何不同 lifecycle status、或 ACKED 后 REJECTED，均 EVENT_CONFLICT。CANCEL_ACK 把 CANCEL row设 CANCELED，并只把 target row lifecycle设 CANCELED，不触碰 fill_status。STOP/TARGET replacement ACK只 ACK新 row并切换 barrier authority，绝不隐式改 old row；old row只能由同 causal time随后显式 CANCEL_ACK终止。old row fill_status=FILLED 或缺该 cancel proof均为 ORDER_REPLACE_CONFLICT/HALT；
- cumulative event 只按 delta 更新 cum fields 与 fill_status NONE→PARTIAL/FILLED 或 PARTIAL→FILLED，永不倒退；terminal lifecycle 后 positive delta 保留原 lifecycle、更新 fill_status并走 LATE_FILL HALT。**任何** positive delta 都先清除旧 `terminal_confirmed_by_snapshot_id`，因为旧 snapshot 已早于新增 fill；若更新后 fill_status=FILLED，则由下述 (a) 立即令 remainder_terminal=true且 confirmation保持 null，若仍未 fully filled则 remainder_terminal=false直到新 proof。每个 row 的 `proof_order_id`：role!=CANCEL 时等于 row.order_id；role=CANCEL 时等于创建该 row 的 CANCEL_REQUEST.payload.target_order_id。`remainder_terminal=true` 当且仅当：(a) fill_status=FILLED；或 (b) role=CANCEL且 lifecycle 属于 CANCELED/REJECTED；或 (c) **（row.lifecycle 属于 CANCELED/REJECTED/EXPIRED/UNKNOWN，或该 row 是 lifecycle 属于 REJECTED/UNKNOWN 的 failed CANCEL row 之 proof_order_id 所指 target row）并且**最早一条满足 §9.1 AccountProofTime 双轴规则的 valid POSITION_SNAPSHOT/RECONCILE_OK 把最近 lifecycle、关联 failed-cancel 与最后 positive cumulative 全部列为 required predecessor，其 open_order_ids 不含 proof_order_id，且要么是隐式 MATCH_FILL_PROJECTION 的 POSITION_SNAPSHOT/显式同 mode的 RECONCILE_OK并且 signed position等于 fill-only projection，要么是 OPERATIONAL_FLAT_AFTER_MISMATCH RECONCILE_OK且本节 operational-flat **base guard**成立；随后绑定 terminal_confirmed_by_snapshot_id。UNKNOWN 仍是 lifecycle 的不确定状态，绝不伪装成 ACKED/REJECTED，但权威 snapshot 可证明其 order remainder 已不存在。对 REJECTED/UNKNOWN CANCEL，此 proof闭合其仍未 terminal 的 target row；对 UNKNOWN CANCEL还同时闭合 CANCEL row。snapshot 始终检查 target proof_order_id，不检查 synthetic cancel instruction自身的 row.order_id。不满足双轴时序或其他条件的较早 snapshot只作普通 reconcile，不会永久阻止后续 proof。否则 false；`all_orders_terminal=every(order.remainder_terminal)`；empty order array 的 every=true。最后按 §11.1 key 排序；
- 若 state_before=CLOSED 但仍有任一 remainder_terminal=false，只有 §9.4 的 first qualifying POSITION_SNAPSHOT/RECONCILE_OK 可以应用上一 bullet 的 snapshot projection；必须在同一 record把所有可证明 row 的 terminal_confirmed_by_snapshot_id/remainder_terminal、reconcile snapshot/position/account_match 与 all_orders_terminal 一并重算。仅当 projection 后 position=0且 every(order.remainder_terminal)=true 才保持 CLOSED，并固定 `decision.reason=RECONCILE,no_change=false`、原 terminal/label reason byte-copy、pending remainder reserve从该 record起释放。不得先做 CLOSED NO_CHANGE 再在 ledger外补 proof；已有 final proof后的 exact-consistent observation才 byte-copy并 NO_CHANGE；
- `submitted_qty` 为 ENTRY row qty（无 submission 为 0）；q_auth/pe 由首个 nonzero entry cumulative 永久冻结。每个 EXIT fill有两个不可混用的 derived mode：`quantity_projection_mode` 永远逐字等于 request row.exit_projection_mode；`realized_basis_mode` 在该 fill前从未有 ACCOUNT_MISMATCH时等于 quantity mode（且正常只能 INTENDED），prefix一旦有 ACCOUNT_MISMATCH则固定为 OBSERVED_SIGNED_RISK。legacy INTENDED order在 mismatch 后 racing fill因此仍按 INTENDED减少 diagnostic inventory，但以 observed basis记实际PnL并标 operational fill-race。`open_qty=sum(entry fill deltas)-sum(quantity mode=INTENDED 的 EXIT fill deltas)`；quantity OBSERVED exit绝不改它。INTENDED quantity projection必须为正常反向 order_side，结果若<0即 OVER_EXIT conflict/HALT；禁止 abs或clamp掩盖；
- `reconcile.position_qty` 同时承载独立的 signed risk-position projection。无 mismatch 时每个 positive ENTRY delta先增加 open_qty并令 position_qty=`s*open_qty`，每个 quantity INTENDED exit再按上一 bullet减少 open_qty并令 position_qty=`s*open_qty`。ACCOUNT_MISMATCH 有 observed_position_qty时，从该 event起把 position_qty设为该 signed observed值、account_match=false且 signed authority=KNOWN；未知时保留最后数值仅作 diagnostic、signed authority=UNKNOWN，禁止方向性 request。进入 mismatch branch 后，每个 positive ENTRY/EXIT delta 都可按实际 order_side更新这个数值诊断（BUY 为 `+delta_qty`、SELL 为 `-delta_qty`）；ENTRY 仍增加 diagnostic open_qty，EXIT仅当 legacy quantity mode=INTENDED时同时减少 diagnostic open_qty，新 OBSERVED request不改它。若 pre-event authority=KNOWN，late/continuing ENTRY fill可使 signed risk减小、增大或穿越0但始终 HALTED并按新 sign确定 flatten 方向，reduce-only EXIT 必须严格减小 absolute signed risk且不得穿越0，否则 EVENT_CONFLICT。若 pre-event authority=UNKNOWN，只允许消费 identity精确匹配的既有 reduce-only order fill；不得用 stale数值执行 risk-reduction/crossing guard，处理后 authority仍 UNKNOWN，即使数值诊断变成0也不得推断 flat或发新方向性 request。POSITION_SNAPSHOT 不得覆写 open_qty；
- MATCH_FILL_PROJECTION snapshot/reconcile必须同时满足 SnapshotOrderSetValid、signed position=`s*open_qty`，且 open_qty>0时 `position_vwap=p_inv`、open_qty=0时 position_vwap=null；此时 `reconciled_qty=open_qty,account_match=true`。同 qty但 vwap不等也必须是单一 ACCOUNT_MISMATCH/VWAP_MISMATCH，并从此使用 observed risk/basis。mismatch 未最终 flat时 `reconciled_qty=max(open_qty,abs(signed risk projection))`；unknown authority使用 max(open_qty,abs(last known))且 quality UNKNOWN。只有 OPERATIONAL_FLAT_AFTER_MISMATCH guard通过后，才允许 snapshot position=0、`reconciled_qty=0,account_match=false` 而保留非零 open_qty作为不可改写诊断；这不是恢复正常交易，只允许 HALTED_RECONCILE→CLOSED；
- `effective_protected_qty` 为 active ACK、reduce-only、identity/side/price 有效 STOP rows 的 remaining qty 之和；account_match=false、signed authority UNKNOWN 或 observed position与 intended side不一致时固定为0，旧 stop不得伪装 coverage。`unprotected_qty=max(0,reconciled_qty-effective_protected_qty)`；`excess_qty=max(0,reconciled_qty-q_auth)`。全部在 decimal128 后按 lot 量化。

lifecycle/fill 两个正交字段是唯一 representation；禁止再合并为单个 status。任何变化必须由上述唯一 event 引起。

**costs 与 risk**

- `entry_cum_qty/notional` 与 `exit_cum_qty/notional` 均先取每个 matching order 的最新合法 cumulative，再跨 order 求和，禁止把同一 order 的中间 cumulative 重复相加。另从完整 ledger event order按 §8.2重放 transient `Q_inv/V_inv` average-cost inventory：ENTRY positive delta增加 qty/quote；每个 quantity_projection_mode=INTENDED 的 EXIT positive delta按 p_inv同比减少 inventory（即使它在 mismatch后成为 legacy race），每个 record末必须 `Q_inv=open_qty`，否则 EVENT_CONFLICT。realized_basis_mode=INTENDED 时令 `gross_delta_k=s*(delta_exit_quote_k-delta_exit_qty_k*pre_exit_p_inv)`；realized_basis_mode=OBSERVED 且 pre-exit signed authority=KNOWN、position_vwap非 null时，令 `risk_sign_k=sign(pre_exit reconcile.position_qty)`（strict risk-reducing guard保证为±1）并计算 `gross_delta_k=risk_sign_k*(delta_exit_quote_k-delta_exit_qty_k*pre_exit_position_vwap)`；authority=UNKNOWN或 vwap为 null时，禁止读取 stale position/vwap，gross diagnostic固定0、record quality=UNKNOWN且 realized_loss保守计完整 `delta_exit_quote_k`。`realized_gross_usdt` 为所有可知 gross_delta之和；`realized_loss_usdt` 为所有可知 `max(0,-gross_delta_k)` 加上述 unknown-basis conservative debit，二者无 exit fill时均为0。后来的盈利不得降低 realized_loss，后来的 entry fill只更新当时剩余 inventory，绝不倒改既往 basis；
- `fee_incurred_usdt=(entry_cum_quote_notional+exit_cum_quote_notional)*ledger_seed.cost_basis.fee_bps_per_side/10000`；
- `funding_incurred_usdt` 为完整 prefix 中 unique FUNDING_DEBIT payload.debit_usdt 之和；`funding_event_id` 由 venue/instrument/interval 语义键唯一生成，同 ID 只能出现一次。position/price basis 必须按同 causal time rank-2 fill 后状态重算；credit 永远不抵扣；
- `entry_slippage_usdt=max(0,s*(entry_cum_quote_notional-entry_cum_qty*p_limit))`；它使用截至当前 prefix 的全 entry cumulative，而不是冻结的首 fill q_auth/pe；缺 fill 为 0；
- 每个 prefix按 §8.2 transient inventory得到 `p_inv=V_inv/Q_inv`（Q_inv=0时 null）；冻结 levels.pe仍是首 fill identity，禁止用于当前 open-risk basis。令 `p_risk` 为 stop_after 非 null 时的 stop_after，否则为 s0，再否则为 p_inv；`exit_worst_usdt=Cost(reconciled_qty,p_risk,15bps)`，`funding_buffer_usdt=Cost(reconciled_qty,p_inv,ledger_seed.cost_basis.funding_buffer_bps)`，`tail_usdt=Cost(reconciled_qty,p_inv,ledger_seed.cost_basis.tail_bps)`；任一 qty为0或对应 price为 null 时该项不求值并固定为0；
- account_match非 false时，`pending_unprotected_usdt` 按 §8.2 对当前 unprotected_qty重算；account_match=false或 signed authority UNKNOWN时固定为 `max(r_episode_max_usdt, 可计算的正常公式)`，以耗尽而非虚构释放预算，并保持 HALTED；唯一释放点是 OPERATIONAL_FLAT_AFTER_MISMATCH full guard成立的 record，此时精确为0。当前 ENTRY unfilled remainder risk 只在该 ENTRY row.remainder_terminal=false 时计 `(submitted_qty-cum_qty)*ctx_current.risk_basis.r_unit_usdt`，terminal confirmation 后精确为 0；`pending_existing_usdt=ctx_current.risk_basis.pending_existing_at_action_usdt + 上述 remainder risk + pending_unprotected_usdt`。filled quantity不得仍在 remainder；ctx_current为 null时这三项均为 0；
- `r_unit_usdt/r_episode_max_usdt` 在 first ENTRY_SUBMIT 从 ctx_current.risk_basis 设置并保留；此前为 0。E0 baseline 的 `C_incurredDebit=fee_incurred_usdt+funding_incurred_usdt`（other debit固定为0），与上述纯毛损 `realized_loss_usdt` 分列且各 semantic debit只出现一次。令 q_protected=min(reconciled_qty,effective_protected_qty)，`locked_net_usdt=realized_gross_usdt+q_protected*s*(p_risk-p_inv)-fee_incurred_usdt-exit_worst_usdt-funding_incurred_usdt-funding_buffer_usdt-tail_usdt`；p_inv/p_risk 不存在、q_protected=0、account_match不严格等于true或 observed side flip时 locked_net=0且禁止 LOCK。realized_gross只用于判断 episode净锁定，不得降低 §8 risk invariant或回收预算。所有金额按 §1 decimal128 量化；每个 record按 §8 invariant以 `realized_loss_usdt+C_incurredDebit+future protected risk+pending_existing_usdt` 重算，禁止用 realized_gross盈利抵扣。invariant 失败时，bundle 必须在引发 breach 的 event 后显式包含 DATA_HEALTH_INVALID/RISK_ACCOUNTING_BREACH，再由该 event 唯一 HALT；reducer不得自行追加事件。

每个 bundle funding artifact 必须在其 causal-effective time有且只有一个 FUNDING_DEBIT，input_artifact_ids 必须引用该 artifact；漏 event、重复 semantic interval、basis/debit 不等或把它放到同刻更低优先级 cost reader之后，使整个 bundle无效。由此 STOP/TARGET ACK、BARRIER_EVALUATION、terminal 等读取 costs/LockedNet 的 event 都看到此前全部 funding debit。

**clock 与 reconcile**

- protection/exit start 时按 §9.3写 kind/start/deadline；未 start 为 null。active clock 在后续 record byte-copy，不得重置；FIRST→EXCESS upgrade 只改 kind并保留较早 start/deadline。一旦其 resolved 条件成立，该 record 起把 protection 的 kind/start/deadline 三项或 exit 的 start/deadline 两项**同时清为 null**。历史 timestamp 由先前 hash-chain record 保留；新 risk increase 可在以后建立全新 clock；
- stale deadline 通过 prefix 中最近一次同 kind start/deadline identity 证明已 resolved，NO_CHANGE 不恢复已清空字段。position=0 同时 clear protection 与 exit 两对字段；未 flat 时一对 resolved 不得清另一对；
- reconcile 字段逐 event 唯一映射：只有 quality=VALID 且 wrapper.account_scope_id 与 ledger逐字相同、ACCOUNT_MISMATCH payload 的 `snapshot_id/account_scope_id/observed_position_qty` 非 null，并且 `observed_position_vwap` 当且仅当 observed qty非零时非 null（qty为零时必须 null）的 trusted snapshot mismatch，才把 `snapshot_id/snapshot_sha256/position_qty/position_vwap` 逐字段设为 artifact.snapshot_id/wrapper.payload_sha256/position_qty_base/position_vwap，令 `account_match=false` 并建立 observed signed authority。无 snapshot artifact，或 quality非 VALID，或 scope不等的 non-trusting ACCOUNT_MISMATCH，其四个 observed identity字段必须按 §9.1 全为 null；record byte-copy先前 snapshot_id/hash/vwap与 signed position，令 account_match=false并把 signed authority标为 UNKNOWN，输入 artifact只作为 details-bound diagnostic proof。每个 POSITION_SNAPSHOT/RECONCILE_OK 都要求 event.input_artifact_ids 中恰好一个 snapshot_id 匹配、quality=VALID且 account_scope_id 等于 ledger 的 ACCOUNT_RISK_SNAPSHOT wrapper，payload.snapshot_id/account_scope_id/hash 与其重算匹配，并完整满足 §9.1 AccountProofTime 双轴 predecessor/effective/availability 规则；其他非 snapshot input 仍按 event schema允许，第二个 ACCOUNT_RISK_SNAPSHOT input 一律拒绝。POSITION_SNAPSHOT 与 reconcile_mode=MATCH_FILL_PROJECTION 的 RECONCILE_OK 还必须通过 SnapshotOrderSetValid、signed position_qty=`s*open_qty`及 nonzero-vwap=`p_inv`/zero-vwap=null；此时四个 snapshot/position字段逐字取 payload，account_match=true；
- 任何 positive ENTRY/EXIT fill 后 snapshot_id/hash继续指最近一次真实 observation（从未观察则仍 null），但该 observation 不再 fresh：无 prior mismatch 时 account_match=null，prior mismatch 后保持 false。position_qty按上一 orders bullet更新；ENTRY fill 后 position_vwap固定为 null，因为旧 observed basis已被新增/穿越的 entry改变；side-correct且未 crossing 的 EXIT fill 在计算当前 realized gross 时先读取 pre-event position_vwap，处理后若 signed position非零则 byte-copy该 vwap、若归零则设 null。无新 snapshot 时其他 event byte-copy这四个字段与 account_match；不得把任一 snapshot写回 open_qty，也不得在 fill 后继续声称 account_match=true；
- `OPERATIONAL_FLAT_AFTER_MISMATCH` 必须按无循环的三步求值。第一步独立验证当前 matching snapshot wrapper/payload/time 与 §9.1 AccountProofTime 双轴规则，不读取 all_orders_terminal，并令 `candidate_signed_risk=payload.position_qty="0"`、candidate signed authority=`KNOWN`；因此 prior authority 即使 UNKNOWN，也只能由这次 same-scope VALID、经济时刻严格晚于全部被证明 state change 且 causal predecessor齐全的 zero observation恢复为已知，不能要求 pre-event projection 已先归零。第二步定义 base guard 当且仅当：当前 state=HALTED_RECONCILE；prefix已有 ACCOUNT_MISMATCH；candidate signed risk=0且 authority KNOWN；payload.position_vwap=null、open_order_ids=[]；required predecessors包含最后 positive fill及每个被 absence proof读取的 lifecycle/failed-cancel event。第三步先以 base guard按 orders bullet对每个 lifecycle-terminal/failed-cancel target row投影当前 snapshot带来的 remainder_terminal，再定义 full guard 为 base guard 且投影后的 every(row.remainder_terminal)=true、payload.all_orders_terminal=true。full guard令 reconcile.position_qty="0"、reconciled_qty=0、account_match=false并允许 CLOSED，但保留原 open_qty与 halted/operational flag；它不是 fill projection恢复一致。`all_orders_terminal` 每条 record 都从 order rows重算；任一 mode/payload/open-order/terminal 不符时，bundle必须显式给出 ACCOUNT_MISMATCH/EXIT_RECONCILE_MISMATCH并走 HALT，不能让 reducer改写来料 event。

**decision**

- barrier_authority.stop/target 各自为：本 event 安装对应新 matching ACK authority 时 NEW_ACKED；本 event 后已有该 ACK authority但不是本 event 安装时 OLD_ACKED；否则 NONE；
- priority_rank 等于 §9.2 当前 event class rank；resume_after_protection 等于 reducer 处理后的 context；duplicate_of_event_id 永远 null，因为 exact duplicate 不追加；EVENT_CONFLICT 时 conflict_with_event_id=payload.original_event_id，illegal pair 时等于 e.source_event_id，其余 null；
- reason 使用以下首个匹配项：EVENT_CONFLICT=`CONFLICT`；illegal pair 或 state_after=HALTED_RECONCILE=`HALT`；ENTRY_REJECT/ENTRY_EXPIRE 且零 fill 后首次进入 CLOSED=`EXPIRE`；无 submission/risk 的 FLAT pre-submit branch 进入 CLOSED=`ABSTAIN`；进入 EXIT_PENDING=`EXIT`；RECONCILE_OK 使 EXIT_PENDING/HALTED_RECONCILE 进入 CLOSED，或 CLOSED 内 first qualifying POSITION_SNAPSHOT/RECONCILE_OK 首次写 terminal proof并释放 remainder=`RECONCILE`；进入 PROFIT_LOCKED=`LOCK`；进入 PROTECTION_PENDING=`PROTECT`；positive fill delta=`FILL`；FUNDING_DEBIT 或 request/ACK/reject/cancel/order projection 改变=`ACTION`；其他可信 snapshot/reconcile projection 改变=`RECONCILE`；其余=`NO_CHANGE`；
- no_change=true 当且仅当 state、end authorities、quantities、risk、orders、costs、reconcile 与 clock 对比 prev end context全部不变；否则 false。event-relative before/after、times、inputs 和 hash 自身不参与此布尔判断。

最后按 §11.1 exact key 集合构造 object，先放 `record_hash` 的 64 位零占位只用于 schema validation，再移除该 key 按 §11.2 公式计算真实 record_hash 并替换；禁止 serializer 对 null、0、空 array 或 key order做第二种处理。以上任一重算值与来料声称值不等时，不得“以 ledger 为准”或“以 exchange 为准”静默选择，只能按 §9 生成 conflict/override。

## 12. C5 Pi_exit、exact C4 fill 与 first-hit label

### 12.1 `PiExitPolicy.v0.2.1`

`Pi_exit.v0.2.1` 是 §9 reducer、§10 Pivot/Target、barrier authority、H0 和本节 first-hit arbitration 的单一 canonical policy object。它必须在 C4 submission 前生成并摘要；submission 后禁止改变任一 nested value。

Top-level exact keys 与值域：

- `schema_version="rsi-mtf-drl-pm.pi-exit.v0.2.1"`；
- `policy_id="pi-exit.v0.2.1"`；
- `reducer_policy_id="fill-protect-reconcile.v0.2.1"`；
- `pivot_policy_id="pivot-theta.v0.2.1"`；
- `target_boundary_policy_id="target-boundary-theta.v0.2.1"`；
- `priority` 必须逐字为 `["KILL_ACCOUNT_MISMATCH","STOP_HIT","PROTECTION_REPAIR","STRUCTURE_EXIT","TARGET_HIT","TIMEOUT","BARRIER_UPDATE","NO_CHANGE"]`；
- `same_timestamp_rule="STOP_FIRST"`；
- `stop_update_rule:StopUpdateRule`；
- `target_update_rule:TargetUpdateRule`；
- `horizon_rule="ABSOLUTE_H0_NO_EXTENSION"`；
- `ack_latency_seconds:int` 且唯一等于 1；其他 latency 必须发布 execution-realism 新 schema/version；
- `data_health_rule:DataHealthRule`；
- `operational_override_rule:OperationalOverrideRule`；
- `ev_evidence_policy_id:string`、`cost_policy_id:string`、`risk_policy_id:string`、`label_policy_id:string`，均为新 v0.2.1 contract 中非空、不可变的 policy ID；
- `policy_sha256:Sha256`。

`StopUpdateRule` exact keys/value：

- `candidate_order=["S_ACK","S_STRUCT","S_BE"]`；
- `selection="MAX_SIGNED_PRICE"`；
- `s_struct_formula_id="ROUND_OUT_PIVOT_MINUS_SIGNED_BUFFER"`；
- `s_be_formula_id="ROUND_PROTECTIVE_PINV_SIGNED_EXCLUSIVE_COST_CLOSED_FORM"`；
- `s_be_eligibility="QUALITY_DATA_ACK_HEALTHY_AND_NONCROSSING"`；
- `struct_rounding="ROUND_OUT"`、`be_rounding="ROUND_PROTECTIVE"`；
- `monotonic_rule="SIGNED_STOP_NONDECREASING_AFTER_ACK"`；
- `crossing_map` exact object 为 `{S_STRUCT:"STRUCTURE_EXIT",S_BE:"STRUCTURE_EXIT"}`；
- `ack_required=true`；
- `ack_identity="PRICE_QTY_REQUEST_ID_ORDER_ID_REDUCE_ONLY_STOP_ROLE_ACK"`；
- `old_barrier_authority="OLD_ACKED_BARRIER_UNTIL_NEW_ACK"`；
- `post_ack_checks=["GEOMETRY_VALID","LOCKED_NET_RECOMPUTED","PROTECTED_QTY_SUFFICIENT"]`。

`TargetUpdateRule` exact keys/value：

- `state_required="PROFIT_LOCKED_FOR_DYNAMIC_TARGET_UPDATE"`；fixed T0 的 request、virtual first-hit 与 ACK authority 由 §9.4/§12.4 管理，不受本字段禁止；
- `pre_lock_rule="KEEP_T0_OR_EARLY_EXIT"`；
- `candidate_sources=["THREE_POINT_FAVORABLE_PIVOT","WINDOW_FAVORABLE_EXTREME"]`；
- `max_extension_r_multiple="0.5"`、`tcap_r_multiple="3"`；
- `absolute_ev_rule="LCB_EV_HOLD_GT_ZERO"`；
- `relative_ev_rule="LCB_EV_HOLD_MINUS_EV_EXIT_NOW_GTE_0_05R"`；
- `tie_break=["MAX_LCB_RELATIVE_EV","MIN_EXTENSION","MIN_PRIORITY_RANK","LEX_STABLE_ID"]`；
- `rounding="ROUND_TOWARD_ENTRY"`；
- `crossing_map` exact object 为 `{T0:"TARGET_HIT",DYNAMIC_TARGET:"TARGET_HIT"}`；
- `ack_required=true`；
- `ack_identity="PRICE_QTY_REQUEST_ID_ORDER_ID_REDUCE_ONLY_TARGET_ROLE_ACK"`；
- `old_barrier_authority="OLD_ACKED_BARRIER_UNTIL_NEW_ACK"`；
- `post_ack_checks=["GEOMETRY_VALID","LOCKED_NET_RECOMPUTED","TCAP_NOT_EXCEEDED"]`。

`DataHealthRule` exact keys/value：

- `pivot_window_unknown="NO_CHANGE"`；
- `target_window_unknown="NO_CHANGE"`；
- `path_grid_missing="CENSOR_PATH_AND_REDUCE_ONLY_EXIT_HALT"`；
- `path_sequence_conflict="CENSOR_PATH_AND_REDUCE_ONLY_EXIT_HALT"`；
- `path_lane_mix="CENSOR_PATH_AND_REDUCE_ONLY_EXIT_HALT"`；
- `current_exit_price_invalid="REDUCE_ONLY_EXIT_AND_HALT"`；
- `management_coverage_invalid="REDUCE_ONLY_EXIT_AND_HALT"`；
- `account_or_order_conflict="REDUCE_ONLY_EXIT_AND_HALT"`；
- `missing_action_pre_submit="ABSTAIN"`；
- `missing_action_post_fill="REDUCE_ONLY_EXIT_AND_HALT"`。

`OperationalOverrideRule` exact keys/value：

- `flag="OPERATIONAL_OVERRIDE"`；
- `winner_rule="CAUSE_EVENT_POSITION_IN_SECTION_9_TOTAL_ORDER"`；
- `pre_submit_rule="NO_ACTION_ABSTAIN_NO_EXECUTION_FLAG"`；
- `flag_requires_submission_or_open_risk=true`；
- `cause_category_priority=["FATAL_EVENT","ENTRY_LATE_OR_FILL_RACE","EXIT_ORDER_FAILURE","PROTECTION_FAILURE","BARRIER_ORDER_FAILURE"]`；同一 cause 只归入首个匹配 category；所有 category 加 OPERATIONAL_OVERRIDE，ENTRY_LATE 另加 LATE_FILL，PROTECTION_FAILURE 另加 PROTECTION_FAILURE；
- `before_market_terminal="CENSOR_AND_NULL_MARKET_PATH"`；
- `same_time_rule="COMPARE_SECTION_9_CLASS_RANK_THEN_SOURCE_SEQUENCE_THEN_EVENT_ID"`；
- `after_market_terminal="KEEP_MARKET_PATH_AND_APPEND_FLAG"`；
- `fatal_events=["ACCOUNT_MISMATCH","KILL","DATA_HEALTH_INVALID","EVENT_CONFLICT","ILLEGAL_TRANSITION"]`；
- `fill_race_events=["LATE_FILL_AFTER_ENTRY_TERMINAL","ENTRY_FILL_DURING_EXIT_PENDING","UNKNOWN_POSITION_INCREASE_OR_SIDE_FLIP_BEFORE_EXIT_PENDING"]`；
- `exit_failure_events=["EXIT_PENDING/EXIT_REJECT_OR_UNKNOWN","PROTECTION_PENDING/EXCESS_EXIT_REJECT_OR_UNKNOWN","UNRESOLVED_PENDING_DEADLINE/EXIT_PENDING_WITH_NONZERO_POSITION","EXIT_RECONCILE_MISMATCH"]`；
- `protection_failure_events=["STOP_REJECT_OR_UNKNOWN_WITH_LIVE_PROTECTION_RISK","UNRESOLVED_PENDING_DEADLINE/FIRST_FILL_PENDING","UNRESOLVED_PENDING_DEADLINE/EXCESS_FILL_PENDING","PENDING_CAP_BREACH_WITH_LIVE_POSITION","CANCEL_REJECT_OR_UNKNOWN_WITH_OPEN_RISK","INSUFFICIENT_PROTECTION_AT_DEADLINE"]`；
- `barrier_failure_events=["TARGET_REJECT_OR_UNKNOWN_WITH_LIVE_TARGET_RISK"]`；
- `exit_reconcile_mismatch_guard="EXIT_PENDING_AND_POSITION_SOURCE_UNKNOWN_OR_SIDE_FLIP_OR_IDENTITY_MISMATCH_OR_POSITION_CONTRADICTS_PROCESSED_FILLS_OR_ALL_ORDERS_TERMINAL_WITH_NONZERO_POSITION"`。

上式 guard 当且仅当 state=EXIT_PENDING 且以下至少一项成立：POSITION_SNAPSHOT/RECONCILE_OK 的 source 或 account/order identity 未知/不匹配；`s*position_qty<0`；position/cumulative quantity 与已处理 fill ledger 矛盾；或 `all_orders_terminal=true` 但 `abs(position_qty)>0`。除此之外 guard=false。cause-category priority 必须先运行，因此 EXIT_PENDING 的上述 mismatch 只归 EXIT_ORDER_FAILURE，不再归 generic fill-race。`PROTECTION_PENDING/EXCESS_EXIT_REJECT_OR_UNKNOWN` 仅指与已记录 excess reduce-only request 精确匹配的 reject/unknown；其他 exit reject 由 state table 或 EVENT_CONFLICT 处理。`UNRESOLVED_PENDING_DEADLINE/EXIT_PENDING_WITH_NONZERO_POSITION` 只在对应 exit clock 未 resolved 且 rank-2 fill/snapshot 后 position 仍非零时成立；resolved stale timer 不属于 override。

`STOP_REJECT_OR_UNKNOWN_WITH_LIVE_PROTECTION_RISK` 当且仅当 state 属于 `{PROTECTION_PENDING,OPEN_PROTECTED_PRE_LOCK,PROFIT_LOCKED,EXIT_PENDING}`、stop request/order identity 精确匹配、该 stop order 在 reject/unknown 前仍非 terminal，且 position 非零或 protection clock 未 resolved。两个 `UNRESOLVED_PENDING_DEADLINE/*` 当且仅当对应 protection clock 在同时间更高 rank event 处理后仍未 resolved；resolved stale timer 不属于 override。`PENDING_CAP_BREACH_WITH_LIVE_POSITION` 只在 PROTECTION_PENDING/EXIT_PENDING 且 position 非零时成立。`TARGET_REJECT_OR_UNKNOWN_WITH_LIVE_TARGET_RISK` 当且仅当 state 属于 `{PROTECTION_PENDING,OPEN_PROTECTED_PRE_LOCK,PROFIT_LOCKED,EXIT_PENDING}`、target request/order identity 精确匹配且该 target order 在该 reject/unknown 前仍非 terminal；它只归 BARRIER_ORDER_FAILURE。FLAT、ENTRY_PENDING、HALTED_RECONCILE、CLOSED 的 consistent late stop/target lifecycle 不命中上述 category，分别只走其 state table、late lifecycle 或 EVENT_CONFLICT 规则。以上 state-qualified sets 两两不重叠。

`policy_sha256=ID("pi-exit-policy/v0.2.1", policy object excluding policy_sha256)`。上述四个 nested object 也必须 exact keys；任何 extra/missing key、array 重排、policy ID 未绑定或摘要不等均为 `SPEC_CONFLICT`。

### 12.2 `EntryExecutionBinding.v0.2.1` 与 exact C4/C5 cohort

每个发生 synthetic submission 的 source control 先生成 control-neutral `SharedEntryAction.v0.2.1`。Top-level exact keys：`schema_version,source_control_id,opportunity_id,candidate_id,side,anchor_at_us,anchor_price,action_at_us,p_limit,submitted_qty,expires_at_us,initial_levels,risk_basis,entry_contract_sha256,entry_action_sha256`。`schema_version="rsi-mtf-drl-pm.shared-entry-action.v0.2.1"`；source_control_id 只能为 C1/C2/C3/C4/Cmu，C5 禁止成为 source；identity/anchor/action/price/qty 字段必须等于 source ledger seed与 FrozenActionContext，`entry_contract_sha256` 必须等于每个复用 bundle 的 ledger_seed.policy_bindings.entry_contract_sha256；`expires_at_us=action_at_us+30s`；initial_levels/risk_basis exact schema与 §11.0 相同且包含 p_limit/submitted_qty 的同值；`entry_action_sha256=ID("shared-entry-action/v0.2.1", entire object excluding entry_action_sha256)`。发生 submission 的 bundle 必须按 §2.9 含唯一 SHARED_ENTRY_ACTION artifact，其 payload就是本完整 object；source control 与任何 C5 replay context 都逐 byte复制 initial_levels/risk_basis并使用同一 artifact/hash。

E0 `EntryExecutionBinding.v0.2.1` 是 sealed control-neutral synthetic entry trace，不是 raw feed或 local OMS log。NO_ACTION 不创建 binding。Top-level exact keys：

`schema_version,source_control_id,opportunity_id,candidate_id,side,anchor_at_us,anchor_price,action_at_us,shared_entry_action_sha256,entry_request_id,entry_order_id,trace_events,ordered_shared_entry_event_ids,first_nonzero_fill_event_id,pe,q_auth,terminal_proof,entry_cost_binding,fill_sequence_sha256`。

- `schema_version="rsi-mtf-drl-pm.entry-execution-binding.v0.2.1"`；identity/action 字段必须与唯一 SharedEntryAction artifact相等；`entry_request_id=ID("shared-synthetic-entry-request/v0.2.1", {entry_action_sha256})`、`entry_order_id=ID("shared-synthetic-entry-order/v0.2.1", {entry_request_id})`；source_control_id 不允许 C5；每个 local ENTRY_* / FILL_CUMULATIVE event 的 request/order必须逐字使用这对 identity；
- `trace_events` 元素 exact keys 为 `trace_sequence:int>=0,event_kind:enum{ENTRY_SUBMIT,ENTRY_ACK,ENTRY_REJECT,ENTRY_EXPIRE,FILL_CUMULATIVE,ENTRY_CANCEL_CONFIRMED,ENTRY_CANCEL_REJECTED,ENTRY_CANCEL_UNKNOWN},shared_entry_event_id:StableId,economic_event_time_us:UtcUs|null,causal_event_time_us:UtcUs,entry_order_id:string,status:enum{SUBMITTED,ACKED,REJECTED,EXPIRED,PARTIAL,FILLED,CANCELED,UNKNOWN},cum_qty:QtyBase,cum_quote_notional:Money,payload_sha256:Sha256`；按 `(causal_event_time_us,trace_sequence,shared_entry_event_id)` 严格排序，trace_sequence 从0连续；
- `payload_sha256=SHA256(CanonicalJSON({event_kind,economic_event_time_us,causal_event_time_us,entry_order_id,status,cum_qty,cum_quote_notional}))`；`shared_entry_event_id=ID("shared-synthetic-entry-event/v0.2.1", {entry_action_sha256,trace_sequence,payload_sha256})`。event_kind↔status唯一映射为 SUBMIT→SUBMITTED、ACK→ACKED、ENTRY_REJECT→REJECTED、ENTRY_EXPIRE→EXPIRED、FILL→PARTIAL/FILLED、CANCEL_CONFIRMED→CANCELED、CANCEL_REJECTED→REJECTED、CANCEL_UNKNOWN→UNKNOWN。SUBMIT 为首项且 causal=action、economic=null、cum均0；fill 的 economic非 null且 causal>=economic，cum/quote单调并按 submitted_qty重算 PARTIAL/FILLED；所有非 fill trace 的 economic=null且必须逐字复制前一 trace的 cum_qty/cum_quote_notional；
- ENTRY_CANCEL_* 只是 control-neutral entry-order状态，不包含 local cancel request/order ID。C4/C5 bundle 各自把它映射到一个 local CANCEL_ACK/CANCEL_REJECT_OR_UNKNOWN，并引用 earlier local CANCEL_REQUEST；两边 local IDs 可不同，但 shared_entry_event_id、target entry_order_id、time/status 必须相同。CANCEL_REQUEST 本身不进入 shared trace；
- `ordered_shared_entry_event_ids` 必须恰好等于 trace_events IDs顺序；`first_nonzero_fill_event_id` 指首个 cum_qty>0 的 shared ID或 null；只要存在任一 nonzero fill（包括 partial 后 CANCELED/UNKNOWN_HALTED），Pe/q_auth都按 §9.3从首个 nonzero event重算并非 null；全程 cum_qty=0 时两者必须 null；
- `terminal_proof` exact keys 为 `terminal_kind enum{FILLED,REJECTED,EXPIRED,CANCELED,UNKNOWN_HALTED},terminal_shared_entry_event_id:StableId,terminal_reconcile_artifact_id:StableId|null,terminal_reconcile_proof_event_time_us:UtcUs|null,sealed_at_us:UtcUs`。terminal kind与其 ID所指 trace kind唯一映射：FILLED→最后一个 status=FILLED 的 FILL_CUMULATIVE、REJECTED→ENTRY_REJECT、EXPIRED→ENTRY_EXPIRE、CANCELED→ENTRY_CANCEL_CONFIRMED、UNKNOWN_HALTED→ENTRY_CANCEL_REJECTED或ENTRY_CANCEL_UNKNOWN；不得指其他 trace。选中的 terminal event之后只允许出现逐字映射 §11.3 CLOSED audit-only exception、且 cumulative完全不变的 entry lifecycle trace；它不改变 terminal_kind/ID。FILLED 当且仅当 cum_qty=submitted_qty；artifact 与 proof-event-time 必须同时 null。其余 kind 的 artifact 与 proof-event-time 必须同时非 null：在每个消费该 binding 的 local bundle中，按 event_array total order选择**第一条**引用 terminal_reconcile_artifact_id、证明 entry order不在 open_order_ids、且完整满足本 bullet 与 §9.1 AccountProofTime 的 POSITION_SNAPSHOT/RECONCILE_OK，作为唯一 qualifying local proof event；不存在则 binding无效，后续同样合格 event不能替代第一条。该 event 的 source_event_id 在 local bundle中就是唯一 proof management event identity，但因 C4/C5 的 bundle_scope/control不同而不写入 control-neutral shared binding；validator必须唯一解析并绑定它，且其 `event_time_us=terminal_reconcile_proof_event_time_us`，所有复用该 binding 的 bundles 必须同值。它把 terminal trace对应 local lifecycle event与最后 positive fill event列为 required predecessors；snapshot.effective_at_us 严格大于 terminal lifecycle causal time，也严格大于最后 positive fill economic time（无 fill时只取前者），并证明它要么匹配 fill projection，要么是 prior ACCOUNT_MISMATCH 后满足 §11.3 guard 的 OPERATIONAL_FLAT_AFTER_MISMATCH proof。对 REJECTED/EXPIRED/CANCELED 的 zero-fill NO_FILL，local event允许且必须命中 §9.4 CLOSED first-proof分支，在该 record写 confirmation/reconcile、释放 remainder，不能走 NO_CHANGE。`sealed_at_us=max(trace_events[-1].causal_event_time_us,last positive fill causal time,reconcile artifact.available_at_us,terminal_reconcile_proof_event_time_us)`（null项不参与 max），因此 snapshot availability、真正 proof event与 late audit trace都被 seal覆盖；
- `entry_cost_binding` exact keys 为 `cost_policy_sha256,fee_bps_per_side,entry_fee_usdt,entry_price_slippage_usdt,slippage_accounting_rule`，最后字段固定 `CURRENT_AVERAGE_INVENTORY_BASIS_INCLUDES_ENTRY_PRICE_DO_NOT_DEDUCT_AGAIN`。令 `q_term`、`n_term` 为 `trace_events[-1]` 的 cum_qty/cum_quote_notional（非 fill与 late audit trace按本节复制累计，因此总有唯一值），则 `cost_policy_sha256` 必须等于每个复用该 binding 的 local bundle之 `ledger_seed.policy_bindings.cost_policy_sha256`，`fee_bps_per_side` 必须等于各 local ledger_seed.cost_basis.fee_bps_per_side；普通 source control只验证自身，C4/C5 pair必须两边都相等。唯一金额公式为 `entry_fee_usdt=n_term*fee_bps_per_side/10000`、`entry_price_slippage_usdt=max(0,s*(n_term-q_term*p_limit))`；全程零 fill 时 q_term=n_term=0且两金额都为 `"0"`。这是全 trace 实际 entry cost binding；q_auth/Pe 仍只冻结首个 nonzero fill的授权 geometry，current-open risk必须按 §8.2 p_inv，不得拿 Pe替代 terminal/current inventory cumulative。两金额使用 §1 decimal128量化，并必须等于各 local ledger terminal record 的 entry fee component与 entry_slippage_usdt；
- `fill_sequence_sha256=ID("entry-execution-binding/v0.2.1", entire binding excluding fill_sequence_sha256)`。

每个 local bundle 中所有 entry-scoped CanonicalSyntheticEvent 必须与 trace一一映射：event.shared_entry_event_id 命中一次；ENTRY/FILL 的 trace.entry_order_id等于 event.order_id，ENTRY_CANCEL_* 的 trace.entry_order_id等于 local CANCEL_ACK/CANCEL_REJECT_OR_UNKNOWN.payload.target_order_id而非 local cancel order_id；semantic kind/status/causal/economic time相等，trace cumulative对 fill取 event payload、对非 fill取该 local event处理前 entry row最新 cumulative。local source_event_id 与 cancel request/order IDs不要求相等。ENTRY_EXPIRE 和 local CANCEL_REQUEST虽在 bundle中是显式 reducer event，但前者映射 shared expiry、后者绝不进入 trace。binding 是 validator/label-only；pure reducer在 trace event实际到达前不得读取其未来项。

`C4ExactFillBinding.v0.2.1` 就是 source_control_id=C4 的完整 binding。C5 的 FrozenActionContext只绑定同一 SharedEntryAction；C5 bundle逐 byte复用 C4 binding、initial_levels、risk_basis、fill_sequence、entry_order/times/Pe/q_auth/cost。C5 从自己的 seed/Genesis消费自己的完整 event_array；first nonzero fill 实际处理后才允许后续 DYNAMIC_PI_EXIT events。C4/C5 local ledger hashes与 management order IDs允许不同，但 shared entry trace必须 byte-identical；这是唯一 cohort/fork 规则。

若 C4 为 NO_FILL，C5 必须使用同一 empty/nonzero-free fill sequence并同为 NO_FILL，H-013 不产生 market-path pair。若 C4 filled 而上述任一 byte/binding 不同，H-013 必须 `PAIR_REJECT/NOT_EXACT_C4_FILL`，不能把差异作为 exit effect。

### 12.3 Observation start、path grid 与 input hash

令首个 nonzero fill 的经济时间为 `f_us`、causal-effective time 为 `c_f_us`，两者来自 exact binding/local event，且 `c_f_us>=f_us`。首个 path grid time唯一为：

\[
t_{path0}=\left\lceil\frac{\max(f_{us},c_{f,us})}{1{,}000{,}000}\right\rceil 1{,}000{,}000.
\]

为使“同 grid 的 operational event 与 market trigger”有唯一边界，path assembler 在每个有合法 selected book 的 expected grid 定义一个不写入 event_array/ledger 的确定性 `PATH_GRID_COMMIT`：它位于该 `grid_time_us` 的 §9 rank 9 HORIZON 之后、rank 10 management event 之前。先按 §9/§12.4 处理 ranks 1–9；若已有 market winner则该 grid 的 selected book point 随 winner 提交，随后较晚 operational flag不能抹除它；若没有 winner则在此 marker 提交该 book point，再处理 ranks 10–12。若 grid 本身因 gap/sequence/lane/endpoint 缺失而无法产生合法 selected book，则唯一使用另一个 path-assembler-only `PATH_DATA_CENSOR_COMMIT`：在验证 SOURCE_COVERAGE_SEAL/gap proof后，先提交 missing endpoint，再紧接处理由该 proof导出的 DATA_HEALTH_INVALID；这是 rank-1 fatal 之前的唯一 commit exception。两个 marker都没有 ID、payload 或独立 hash，只由 grid proof与固定边界导出，不能由 fixture选择，也不改变 reducer event rank。

`ZERO_GRID_OPERATIONAL_OVERRIDE` 是以下互斥 union：(a) `f_us>=H0`、`c_f_us>=H0` 或 `t_path0<=0/t_path0>=H0`，其 zero_grid_cause_event 为 first nonzero FILL_CUMULATIVE；或 (b) 正常时间条件虽满足，但 §12.4 的首个 **非 path-data-censor** operational cause 按完整 total order 在任何 PATH_GRID_COMMIT 前获胜，且此前没有 market winner，其 zero_grid_cause_event 为该 operational event。`path-data-censor` 唯一指由当前 expected grid 的 gap/sequence/lane/endpoint proof导出的 DATA_HEALTH_INVALID，并映射 censor_reason `{DATA_GAP,SEQUENCE_CONFLICT,LANE_MIX,ENDPOINT_MISSING}`；它先把该 grid作为 missing endpoint与 SOURCE_COVERAGE_SEAL 提交，再处理 fatal event，永不属于 zero-grid。ZERO branch覆盖 economic late fill 已先 ENTRY_EXPIRE、fill 后 protection/external-fatal cause 落在 `(c_f,t_path0)`，以及非 data-censor cause 在 t_path0 同刻但排序早于 commit。该 branch 唯一输出 FILLED + OPERATIONAL_OVERRIDE/CENSORED、market path null、`evaluated_through_us=zero_grid_cause_event.event_time_us`、book/missing grids `[]`、source coverage null；不得回放 cause 之前尚未 commit 的 quote。

若 operational cause 获胜前已存在至少一个 PATH_GRID_COMMIT，则不是 zero-grid：market path仍为 CENSORED/OPERATIONAL_OVERRIDE且 market label null，但 `evaluated_through_us` 唯一等于 cause 前最近一个 committed grid，book prefix只到该 grid、missing=[]、source seal也只到该 grid；cause本身另由 PathInput.censor_cause_event_id/reducer_events绑定，不能把未 commit 的同刻 grid伪装成 observed。其余 filled branch 才是正常 path，并必须同时满足 `f_us<H0`、`c_f_us<H0`、`0<t_path0<H0`。正常分支完整 expected grid 为

\[
\{t_{path0}+k\cdot1s:\ t_{path0}+k\cdot1s<H_0\}\cup\{H_0\},
\]

H0 只出现一次，因此即使它不在整秒也有唯一 endpoint。对 grid time t，候选 snapshot artifact 必须同 instrument/lane kind、VALID、sequence contiguous、`event_time_us<=t`、`lane_available_at_us<=t` 且 `0<=t-event_time_us<=1s`；先取最大 event_time，再取最小 `(lane_available_at_us,source_sequence,event_id)`。首个 grid point 另要求 snapshot 在 fill 后可用：`event_time_us>f_us`，或 `event_time_us=f_us` 且 `lane_available_at_us>c_f_us`；否则禁止使用 pre-fill quote。相同 fill/book timestamp且无法证明顺序时 CENSORED/SEQUENCE_CONFLICT，不用 stable ID 人造因果。所有由 fill 派生的 trigger.event_time_us 必须 `>=c_f_us`。

first-hit 只要求从 `t_path0` 到首个 terminal/censor 的连续 committed prefix；若没有更早 terminal，则必须一直到 H0 endpoint。任何 prefix 内 expected point 缺失立即在首个缺失 t 终止为 CENSORED；terminal 后的市场数据不用于改变 winner。除 ZERO_GRID_OPERATIONAL_OVERRIDE 外，独立的 §2.4A SOURCE_COVERAGE_SEAL artifact 必须覆盖 `(max(0,t_path0-1_000_001),evaluated_through_us]`、所有被选择 source generation 与 gap；early terminal 的 seal 覆盖到 terminal，TIMEOUT 的 seal 必须覆盖到 H0。它不等于 §2.9 bundle coverage，seal 不完整不能由相邻价格插值。

每个 filled control 先生成 `ExitPolicyInstance.v0.2.1`。其 top-level exact keys 为 `schema_version,opportunity_id,control_id,side,template_id,initial_levels,dynamic_policy_sha256,priority,same_timestamp_rule,horizon_rule,policy_instance_sha256`：

- `schema_version="rsi-mtf-drl-pm.exit-policy-instance.v0.2.1"`；
- `template_id enum{FIXED_S0_I0_T0_H0,DYNAMIC_PI_EXIT}`；C5 只能 DYNAMIC，其余 filled controls 只能 FIXED；
- `initial_levels` exact keys 为 `p_limit:Price,pe:Price,i0:Price,g0:Price,s0:Price,t0:Price,tcap:Price,h0_us:UtcUs`，必须与 entry binding/ledger exact 相等；C5 与 C4 的 object 必须 byte-identical；
- `dynamic_policy_sha256:Sha256|null`；C5 等于 §12.1 policy_sha256，其余为 null；
- `priority` 与 `same_timestamp_rule` 等于 §12.1 的 fixed array/`STOP_FIRST`；`horizon_rule="ABSOLUTE_H0_NO_EXTENSION"`；
- `policy_instance_sha256=ID("exit-policy-instance/v0.2.1", entire instance excluding policy_instance_sha256)`。

每个 filled control 再生成 `PathInputBundle.v0.2.1`，top-level exact keys：

`schema_version,opportunity_id,control_id,side,lane_id,availability_kind,first_fill_shared_event_id,first_fill_economic_time_us,first_fill_causal_time_us,path_start_us,h0_us,evaluated_through_us,status,censor_reason,censor_cause_event_id,synthetic_coverage_sha256,source_coverage_artifact_id,source_coverage_seal_sha256,book_points,missing_grid_times_us,reducer_events,funding_events,funding_events_sha256,exit_policy_sha256,path_input_sha256`。

约束：

- `schema_version="rsi-mtf-drl-pm.path-input-bundle.v0.2.1"`；
- identity/time 字段必须与 entry binding、local ledger event 和 H0 完全一致；`availability_kind` 在 P0-RSI-02/03 唯一为 `SYNTHETIC`；first_fill_shared_event_id命中 binding，economic/causal time分别等于 trace与 local event；path_start按本节 `ceil(max(f,c_f))` 计算。market winner/data missing/H0 的 evaluated_through分别等于 winner grid/missing grid/H0；已有 committed prefix后的 operational censor等于 cause前最近 committed grid；ZERO_GRID_OPERATIONAL_OVERRIDE唯一等于 zero_grid_cause_event.event_time_us；
- `status enum{COMPLETE,CENSORED}`；`censor_reason enum{DATA_GAP,SEQUENCE_CONFLICT,LANE_MIX,ENDPOINT_MISSING,OPERATIONAL_OVERRIDE}|null`、`censor_cause_event_id:StableId|null`。COMPLETE 时两者都必须 null；CENSORED 时两者都非 null，cause ID必须唯一命中 reducer_events 中触发该 censor 的 management_event_id：path data censor命中显式 DATA_HEALTH_INVALID，operational override命中 §12.1 cause-category event；
- `synthetic_coverage_sha256:Sha256` 必须等于 CanonicalSyntheticEventBundle.coverage.coverage_sha256，即使 CENSORED 也禁止 null；`source_coverage_artifact_id:StableId|null` 与 `source_coverage_seal_sha256:Sha256|null` 必须同时非 null或同时 null，非 null时前者唯一命中 SOURCE_COVERAGE_SEAL wrapper、后者等于其 payload.seal_sha256；正常 path 必须非 null，只有上述 ZERO_GRID_OPERATIONAL_OVERRIDE 才必须均 null；synthetic/source两个 hash domain禁止互换；
- `book_points` 元素 exact keys 为 `grid_time_us:UtcUs,book_artifact_id:StableId,book_event_id:StableId,book_event_time_us:UtcUs,lane_available_at_us:UtcUs,source_sequence:int>=0,exit_side_price:Price,payload_sha256:Sha256`，book_artifact_id必须唯一命中 BOOK_SNAPSHOT wrapper，其余 source字段与 wrapper.payload逐字匹配；按 grid_time 严格递增，每个成功 observed/committed grid恰好一个，missing endpoint只能进 missing_grid_times_us且禁止伪造 book point；
- `missing_grid_times_us:array<UtcUs>` 升序去重；只有 data/sequence/lane/endpoint censor 才非空，第一个元素必须等于 `evaluated_through_us`；operational override censor 时必须为空；
- `reducer_events` 元素 exact keys 为 `management_event_id:StableId,source_event_id:StableId,event_kind:ReducerEventKind.v0.2.1,event_time_us:UtcUs,economic_event_time_us:UtcUs|null,priority_rank:int,source_sequence:int>=0,predecessor_event_ids:array<StableId>,input_artifact_ids:array<StableId>,payload_sha256:Sha256`。membership不做“是否影响”的语义筛选：COMPLETE 时恰好投影 event_array total-order 中从 first nonzero FILL_CUMULATIVE 到 market winner/HORIZON（两端含）的**每一个** CanonicalSyntheticEvent；CENSORED 时恰好投影从 first fill 到 censor_cause_event（两端含）的每一个 event，即使 operational cause晚于 evaluated_through的最后 committed grid也必须纳入。字段逐项 byte-copy/映射 management event ID，顺序与原 slice完全相同，无重复、无遗漏；
- `funding_events` 元素 exact keys 为 `funding_event_id:StableId,source_event_id:StableId,input_artifact_id:StableId,economic_event_time_us:UtcUs,event_time_us:UtcUs,source_sequence:int>=0,interval_start_us:UtcUs,interval_end_us:UtcUs,funding_rate:DecimalString,payload_sha256:Sha256`；semantic funding ID按 §9.1，interval合法，按 `(event_time_us,source_sequence,source_event_id)` 排序无重复；每项必须在 reducer_events 中有且只有一个同 source_event_id/input_artifact_id/funding_event_id 的 FUNDING_DEBIT，且排在所有同刻 cost reader前；这里 payload_sha256 唯一等于该 FUNDING_DEBIT CanonicalSyntheticEvent.payload_sha256，不是 observation artifact payload hash；
- `funding_events_sha256=ID("path-funding-events/v0.2.1", funding_events)`；空 array 也必须写 `[]` 并摘要；
- `exit_policy_sha256` 必须等于该 control 的 `ExitPolicyInstance.policy_instance_sha256`；
- `path_input_sha256=ID("path-input-bundle/v0.2.1", entire bundle excluding path_input_sha256)`。

缺失/冲突 synthetic coverage 仍可形成一个结构合法的 CENSORED bundle/label，但 gap time必须显式列出，不得伪装成无命中。bundle event_array必须已经含 data-health reduce-only exit/HALT与最终 reconcile/CLOSED；pure reducer不追加。primary censor_reason保留 data原因并加 OPERATIONAL_OVERRIDE flag。C4/C5 的 C4_C5_EXOGENOUS_PATH_MANIFEST、其传递引用的 book/funding/coverage artifacts与 shared entry trace必须 byte-identical；policy-specific policy artifact、barrier/management event及 terminal prefix允许不同，不得更换 exogenous manifest或 lane。

### 12.4 Barrier triggers、direct crossing 与同时间仲裁

固定 controls C1/C2/C3/C4/Cmu 的 book-derived trigger：

- STOP_HIT：LONG `bid<=S0`；SHORT `ask>=S0`，未 ACK 的 fixed S0 使用 S0_VIRTUAL、已 ACK stop 使用 ACKED_STOP_PRICE，均映射 `SL`；
- STRUCTURE_EXIT：LONG `bid<=I0`；SHORT `ask>=I0`，使用 I0，映射 `STRUCTURE_EXIT`；
- TARGET_HIT：LONG `bid>=T0`；SHORT `ask<=T0`。首次 target request 之前已经 crossing 使用 T0_DIRECT；fixed T0 request 已发但尚无有效 ACK 时的后续 crossing 使用 T0_VIRTUAL；已 ACK target 使用 ACKED_TARGET_PRICE，三者均映射 `TP`；
- TIMEOUT：此前无 winner 且处理 H0 endpoint 后仍未命中，映射 `TIMEOUT`。

C5 仍与 C4 共用 frozen I0 和 H0。PivotTheta 只产生 stop-update candidate；它不替代 I0 structure trigger。C5 的当时权威 stop/target 才参与 ordinary price hit：request 不生效，新 ACK 必须先按 §9.2 入序，旧 ACK barrier 在 ACK event 前权威。禁止“先应用同 timestamp 新 ACK、再回看此前 quote”。candidate crossing 与 ACK 后 crossing 必须严格分开：

- 在发送 request **之前**，若 S_STRUCT candidate 已被当前 executable exit price 穿越，生成 `STRUCTURE_EXIT/S_STRUCT_DIRECT`；S_BE 同理生成 `STRUCTURE_EXIT/S_BE_DIRECT`。两者 request/order IDs 为 null，映射 STRUCTURE_EXIT；不得发送该 crossing stop request；
- 在发送首次 fixed T0 request **之前**，若 T0 已 crossing，生成 `TARGET_HIT/T0_DIRECT`，不得发送该 crossing target request；若 request 已发送且尚无有效 ACK，T0 此后 crossing 生成 `TARGET_HIT/T0_VIRTUAL`，立即发 reduce-only exit 并 cancel pending target request，不能等待 ACK。两者 request/order IDs 均为 null并映射 TP；
- dynamic target candidate 仅在发送 request **之前** 已 crossing 时生成 `TARGET_HIT/DYNAMIC_TARGET_DIRECT`，request/order IDs 为 null并映射 TP，且不得发送该 crossing target request；dynamic request 已发而 ACK 未到期间 candidate 不具 authority，旧 ACK target 继续权威，不能生成 DYNAMIC_TARGET_DIRECT；
- candidate 在 request 时 non-crossing，后来获得有效 ACK 后，若 ACK 时当前 quote 已穿越新的 stop/target，分别生成 `STOP_HIT/ACKED_STOP_PRICE` 或 `TARGET_HIT/ACKED_TARGET_PRICE`，并绑定该 ACK 的 request/order IDs；不得再标成 *_DIRECT；
- 未 ACK fixed S0 的 virtual first-hit 使用 `STOP_HIT/S0_VIRTUAL`；已 ACK stop 的普通 market crossing 使用 `STOP_HIT/ACKED_STOP_PRICE`。未 ACK fixed T0 的等待期 first-hit 唯一使用 `TARGET_HIT/T0_VIRTUAL`，不得与 T0_DIRECT 或 ACKED_TARGET_PRICE 重叠。

这些 trigger 必须已是 §2.8 synthetic event：*_DIRECT、S0_VIRTUAL、T0_VIRTUAL 的 input_artifact_ids 含 candidate/fixed-level与触发 quote，predecessor_event_ids 含需要的 prior request；ACKED_*_PRICE 同时以有效 ACK为 predecessor并引用触发 quote。trigger.event_time_us 唯一等于 path grid evaluation time，ACK-immediate crossing则等于 ACK evaluation time，不能倒签为 snapshot availability。禁止把 reduce-only exit request本身当 market label。

唯一仲裁算法直接消费 bundle显式 ready-set，全序 key 为 `(event_time_us,priority_rank,source_sequence,source_event_id)`；每处理一个 event立即更新 reducer再判断 terminal。rank 展开不变：1 kill/account/data/conflict，2 fill/snapshot，3 funding，4 stop，5 matching protection ACK，6 protection failure/repair，7 structure，8 target，9 timeout，随后 barrier/exit/entry/no-change。`STOP_FIRST` 只解决同一 synthetic aggregate 内无法恢复的市场触发顺序，不越过 operational cause；funding不是 market winner但先进入 costs。

operational override 只在已经发生 submission/reserve 或存在 open position/order risk 时成立；FLAT pre-submit 的 account/kill/data/conflict 按 §9.4 形成 NO_ACTION/ABSTAIN 且 flags=[]。其余 operational override 的 terminal 位置等于 cause event 在上述全序的位置，而不是一律抢占全部 market events：

- cause 在首个 market terminal 前，或同时间但排序更早：设置 OPERATIONAL_OVERRIDE flag、CENSORED、market null；
- cause 在同时间但排序更晚，或在既有 market terminal 后：保留既有 market label，只追加 flags；
- 同 source identity 漂移或无法形成全序：EVENT_CONFLICT，按 rank 1 override；
- PROTECTION_REPAIR 只有在 reject/unknown/deadline/cap breach 导致 EXIT/HALT 时才是 PROTECTION_FAILURE；成功 repair 不是 terminal。

因此 stop 与 pending deadline 同时发生时，rank-4 STOP_HIT 先胜出，随后 protection flag 可以追加但不能擦除 SL；late fill 与 stop 同时发生时，rank-2 fill race 先产生 override；同 timestamp funding 在 stop/ACK/target 前先记 debit；stop 与 target 同一无法判序 quote 上同时命中时，STOP_FIRST 产生 SL。

### 12.5 Label envelope、bindings 与 record hash

每个 control 输出 exact label keys：

`control_id,side,action_at_us,submission_label,execution_flags,observation_status,censor_reason,market_path_label,terminal_event_id,terminal_at_us,fill_sequence_sha256,path_input_sha256,pi_exit_sha256,label_record_sha256`。

字段类型和联合约束：

- `control_id enum{C0,C1,C2,C3,C4,Cmu,C5}`；`side enum{LONG,SHORT,NONE}`，NONE 只允许 C0；
- `action_at_us:UtcUs`；C0 唯一等于 FrozenLedgerSeed.anchor_at_us，非 C0 唯一等于其 FrozenActionContext.action_at_us；
- `submission_label enum{NO_ACTION,FILLED,NO_FILL}`；
- `execution_flags` 只含 enum `{PARTIAL_FILL,OPERATIONAL_OVERRIDE,LATE_FILL,PROTECTION_FAILURE}`，去重并严格按该列举顺序排列；
- `observation_status enum{NOT_APPLICABLE,COMPLETE,CENSORED}`；
- `censor_reason enum{DATA_GAP,SEQUENCE_CONFLICT,LANE_MIX,ENDPOINT_MISSING,OPERATIONAL_OVERRIDE}|null`；仅 CENSORED 可非 null且此时必须非 null；
- `market_path_label enum{TP,SL,STRUCTURE_EXIT,TIMEOUT}|null`；
- `terminal_event_id:StableId|null`、`terminal_at_us:UtcUs|null`；只有 C0 两者为 null；非 C0 NO_ACTION 对 CONTROL_ABSTAIN 绑定 `ID("control-abstain-terminal/v0.2.1", {opportunity_id,control_id,terminal_at_us,reason_code})`，对 pre-submit account/kill/data/conflict 直接绑定 cause management event_id；NO_FILL 绑定 reject/expire/cancel terminal 或 pre-fill operational cause 的 management event_id；data censor 绑定 `ID("label-censor-terminal/v0.2.1", {opportunity_id,control_id,censor_reason,terminal_at_us,path_input_sha256})`；其他结果绑定实际 winner management event_id；
- `fill_sequence_sha256:Sha256|null`；NO_ACTION 为 null，NO_FILL/FILLED 必须为 EntryExecutionBinding 摘要；C5 发生 submission 时必须等于 C4 摘要；
- `path_input_sha256:Sha256|null`；仅 FILLED 非 null，并必须等于 §12.3 bundle；
- `pi_exit_sha256:Sha256|null`；仅 C5 必须为 §12.1 policy_sha256，其余 controls 必须 null；
- `label_record_sha256:Sha256`。

状态组合唯一为：

- C0：NO_ACTION、flags `[]`、NOT_APPLICABLE、censor/market/terminal/fill/path/pi 均 null；
- 非 C0 NO_ACTION：flags `[]`、NOT_APPLICABLE、censor/market/fill/path 均 null；若由 CONTROL_ABSTAIN/TTL 终止，terminal ID/time 绑定首次 CONTROL_ABSTAIN/TTL terminal；若由 §9.4 pre-submit account/kill/data/conflict 终止，terminal ID/time 直接绑定该 cause management event。两支互斥，C5 的 pi 均必须按下述规则非 null；
- NO_FILL：NO_FILL、NOT_APPLICABLE、censor/market/path 均 null；非 C0 fill_sequence 与 reject/expire terminal 必须非 null；
- FILLED 且 path complete：COMPLETE、censor null、market 与 terminal 必须非 null；
- FILLED 且 path/data/override censor：CENSORED、censor 与 terminal 必须非 null、market null；override censor 还必须有 OPERATIONAL_OVERRIDE flag；
- PARTIAL_FILL 当且仅当曾有 PARTIAL cumulative 或 `q_auth<submitted_qty`；LATE_FILL/PROTECTION_FAILURE 按 §9 与 §12.4 cause 设置；partial flag 可与 complete market label共存。

除 C0 外，Label 只能在 reducer 到达 CLOSED、所有 order remainder/reconcile terminal且 CanonicalSyntheticEventBundle 已 final seal 后 finalize；NO_ACTION/NO_FILL 没有 path prefix，但 binding/terminal proof仍须闭合。C0 在 Genesis 后即可 finalize。`terminal_at_us` 唯一等于 first winner/reject/censor CanonicalSyntheticEvent.event_time_us，即 causal-effective time，不是原经济时间或 final write time。sealed bundle 之后不存在 live append；未来 data adapter若发现 late source，只能作废旧 bundle/label并生成新 immutable digest，全量重算，不能覆写旧 record或择取“最新一行”。

`FirstHitLabelPolicy.v0.2.1` 是 label hash 所绑定的 canonical policy object，exact keys/value 为：

- `schema_version="rsi-mtf-drl-pm.first-hit-label-policy.v0.2.1"`；
- `control_dispatch` exact object `{C0:"NO_MARKET_PATH",C1:"FIXED_S0_I0_T0_H0",C2:"FIXED_S0_I0_T0_H0",C3:"FIXED_S0_I0_T0_H0",C4:"FIXED_S0_I0_T0_H0",Cmu:"FIXED_S0_I0_T0_H0",C5:"DYNAMIC_PI_EXIT_EXACT_C4_FILL"}`；
- `observation_grid_rule="SECTION_12_3_EXACT_PREFIX_GRID"`；
- `snapshot_selection_rule="LATEST_EVENT_TIME_THEN_MIN_LANE_SEQUENCE_ID_WITH_POST_FILL_PROOF"`；
- `trigger_rule="SECTION_12_4_DIRECT_AND_ACKED_BARRIER_TRIGGERS"`；
- `arbitration_rule="SECTION_9_TOTAL_ORDER_AND_STOP_FIRST"`；
- `operational_override_rule="CAUSE_EVENT_POSITION_NOT_GLOBAL_PREEMPTION"`；
- `no_fill_rule="SEPARATE_SUBMISSION_LABEL_NO_MARKET_PATH"`；
- `partial_fill_rule="EXECUTION_FLAG_NOT_MARKET_CLASS"`；
- `horizon_rule="ABSOLUTE_H0_ENDPOINT_INCLUDED_NO_EXTENSION"`；
- `label_tail_rule="ROLE_CHRONOLOGY_LABEL_TAIL_BEFORE_FINALIZE"`；
- `pi_exit_sha256:Sha256`，必须等于 §12.1 policy_sha256；
- `policy_sha256:Sha256`，其值为 `ID("first-hit-label-policy/v0.2.1", object excluding policy_sha256)`。

extra/missing key 或 symbolic rule string 不完全相等均拒绝；`LabelBindings.label_policy_sha256` 必须等于此 object 的 policy_sha256。

`LabelBindings.v0.2.1` exact keys：

`core_raw_sha256,v0_2_contract_canonical_sha256,addendum_raw_sha256,v0_2_1_contract_sha256,candidate_id,code_sha256,data_or_fixture_sha256,synthetic_bundle_sha256,entry_execution_binding_sha256,management_ledger_head_sha256,label_policy_sha256`。

全部值均为 Sha256/StableId（candidate_id 按 §1.2）；`synthetic_bundle_sha256` 必须等于 §2.9 full bundle digest，只能在全部 event完成后的 label/final receipt中绑定。任一 NO_ACTION 的 `entry_execution_binding_sha256` 必须为 `ID("no-entry-execution/v0.2.1", {opportunity_id,control_id})`，NO_FILL/FILLED controls 必须等于 label 的 fill_sequence_sha256。C4/C5 pair 发生 submission 时 entry binding digest 必须相等。`management_ledger_head_sha256` 对非 C0 必须等于 finalize 时 CLOSED record_hash；C0 等于 Genesis hash。label 内重复出现的 fill/path/pi hash 必须一致。

最终 hash 唯一为：

`label_record_sha256=ID("label-record/v0.2.1", {bindings:LabelBindings exact object,label:label envelope excluding label_record_sha256})`。

任何 nullable 组合、binding、digest、event winner 或 path prefix 不符合本节即拒绝整条 label；禁止用文件名、行序或数据库主键补 identity。

## 13. 冻结 baseline、有限 challengers 与开发纪律

下表中 baseline 是 v0.2.1 初始唯一候选。challenger 只允许在 P0-RSI-04 的 DEVELOPMENT 中按“一次一层、一个新版本”选择；不得同时搜索多行、连续优化或用 CALIBRATION/HOLDOUT 结果回选。

| 层 | Baseline | 有限 challenger set |
|---|---:|---|
| adverse pressure 最短连续秒数 | 5 | `{1,10}` |
| K threshold | 1.5 | `{1,2}` |
| `abs(D)` directional threshold | 0.1 | `{0.05,0.2}` |
| R threshold | 0.6 | `{0.5,0.7}` |
| L upper threshold | -0.0005 | `{-0.001,0}` |
| RESPONDING bps | 5 | `{3,8}` |
| U active/cooldown seconds | 1800/900 | `none — frozen universe` |
| EV minimum n | 30 | `{60,100}` |
| synthetic barrier ACK latency seconds | 1 | `none in E0 — future execution-realism contract` |

RSI 14/30/70、release lag、DRL/K windows、U active/cooldown、EntryZone bps、spread/slippage/capacity、Rmin/Rcap、risk/cost/tail、pending caps、H0/Tcap、priority、label arbitration 当前 challenger set 为空。U 尤其不得作为 challenger，因为改变 U 会破坏同 universe 对照。若要改变这些字段，必须先出新的 theory delta 和 contract ID，不能在 DEVELOPMENT 代码配置中暗改。

任何 challenger 比较必须使用相同 U、相同 source/availability、相同 fill/cost/risk simulator 和只到 decision time 的 expanding evidence。选择结果只能形成新 DEVELOPMENT candidate；它不能回写 baseline，也不能解释已见结果。

## 14. 重规划路线与阶段门

此前的 P0-RSI-02 编码授权因规范不完整暂停。唯一合法顺序如下。

### P0-RSI-01B — v0.2.1 contract

产物：新 ID contract、新 validator、新 negative tests；绑定 CORE、旧 v0.2 contract、本 addendum，并把 CanonicalSyntheticEvent/Bundle、纯 reducer、ledger、label exact schema完整序列化。

PASS：本文件全部 normative schema/union/identity 成为 exact fields；canonical digest 稳定；同 ID 任一 semantic/tooling drift 被拒绝；无未决占位；所有 data/execution auth 仍 FORBIDDEN；`E0/REJECT_FREEZE`；旧 v0.2 artifact 可原样复验。

REJECT：修改旧 ID、遗漏 addendum binding、摘要自引用、任一公式/schema/state/label 可有两种解释、授权数据或执行、或把测试通过写成市场有效。

### P0-RSI-02 — pure implementation

产物：只实现新 contract 允许的 pure calculators、U reducer、entry/risk solver、CanonicalSyntheticEventBundle validator、只消费 event_array 的 management reducer、ledger encoder 和 labeler；独立 implementation manifest 绑定 v0.2.1 full contract digest。

PASS：无 IO/network/reader/source adapter/event generator/timer service/exchange simulator/backtest；相同 sealed bundle 得到 byte-identical output；reducer不补造 event；所有 UNKNOWN/ABSTAIN/CENSOR/HALT 路径存在；旧或错误 digest fail closed。

REJECT：隐含默认、float、wall-clock/randomness、参数热更新、读取 outcome 选择 action、未绑定实现或任何 scope expansion。

### P0-RSI-03 — synthetic stage gate

产物：完整 sealed CanonicalSyntheticEventBundle fixtures、golden/property/metamorphic/state×event/hash-chain/mutation tests，以及独立 Sol 审查。

PASS 至少证明：四路 RSI grid/freshness/rearm；严格 R 非重叠；U gate neutrality；Z_liq 非循环；EV no-fill/LCB；risk/pending caps；bundle causal obligations与非法 mutation拒绝；所有 reducer转换与非法 pair；late fill/expiry edge；barrier ACK authority；funding-before-cost-reader；ledger deterministic full replay；C4/C5 exact trace；first-hit/gap/censor/override arbitration。全部测试 PASS 且独立审查无 P0 漂移。

REJECT：只测 happy path、跳过非法转换、测试依赖实现内部顺序、使用市场数据、或用 coverage 数量代替语义验收。

### P0-RSI-04 — DEVELOPMENT-only data admission/backtest

该阶段不是自动开放。必须另有 Sol 授权 artifact与独立的 historical source→CanonicalSyntheticEventBundle adapter contract，精确绑定：v0.2.1 contract、implementation、adapter code、DEVELOPMENT chronology、release policy、typed source schema、data manifest、gap/censor policy、pre-access seen registry、固定 E0 fill/cost/risk assumptions 和 candidate digest。adapter 输出必须先被 §2.9 validator接受，reducer接口不变。

PASS：只读被授权 DEVELOPMENT；as-of/reconstructed clock 可复验；任何 gap fail closed/censor；expanding evidence 不看未来；baseline 与一次一层 challenger 同 U/成本/模拟器；报告明确 E0，不产生市场或交易结论。

REJECT：访问 CALIBRATION/HOLDOUT、读取未授权月份、重用 SEEN、改 chronology/cohort/action/cost/risk/label、让 adapter生成未声明语义、在结果后加 challenger、写活动 G1 package，或声称 execution realism/G2/paper/trading readiness。

P0-RSI-04 后先回答 predictive validity，不能自动开发 OMS。只有 DEVELOPMENT→CALIBRATION→one-shot HOLDOUT 的预测与成本后结果均通过未来阶段门，才可另建 execution-simulator-realism contract；只有其通过且进入 E3/paper 前，才可另建 async OMS/exchange connector安全 contract。paper、部署和 trading 始终各自另过阶段门。

### 14.1 失败后的唯一回路

| 首次发现位置 | 唯一允许路线 | 禁止的跨层救援 |
|---|---|---|
| 01B 出现两种解释或无法序列化 | `BLOCKED_CONTRACT_SERIALIZATION`，修订理论 addendum 并使用新版本/digest 后重做 01B | 让实现选择默认值 |
| 02 与 contract 不一致 | 只修实现，生成新 code/manifest digest，再重做 02 | 改理论、放宽 validator |
| 03 发现 code bug | 回 02；全部 synthetic gate 重跑 | 只改单个测试 expected output |
| 03 发现规范本身矛盾 | 回 01B，发布新的 semantic version | 在代码注释中解释 |
| 04 data/gap/availability fail | 只做 data-layer delta；使用未来未见 DEVELOPMENT role 重新授权 | 改 gate、cohort、cost、risk 或把 gap 填成零 |
| 04 predictive/EV fail | 在 DEVELOPMENT 内只选所属层一个有限 challenger，形成新 candidate digest | 同时调多层、读取 CALIBRATION/HOLDOUT 后回选 |
| 04 risk/cost support 越界 | candidate STOP，回 theory delta/new contract；不得裁剪 Y 或降低 tail | 用回测盈亏改风险上限 |

路线可以依据事实进入上述回路，但不能自动扩大权限。每次状态变化都必须记录当前 stage、失败层、已见数据角色、旧/新 digest 和下一项唯一 P0。

## 15. 内部一致性审计与剩余 BLOCKED 项

### 15.1 本 addendum 已关闭的实现歧义

- RSI 四路 freshness、连续 grid、duplicate/conflict 和 rearm；
- K/D/R/L/RESPONDING exact calculators；
- U identity、time-based gate-neutral dedup/cooldown、anchor 和 TTL；
- spread/slippage/capacity 与 q 的非循环解；
- EV_submit、NO_FILL、LCB 和 bounded evidence；
- b0/G0/Tcap 与 risk/cost/margin/notional mapping；
- E0 CanonicalSyntheticEventBundle、显式 predecessor/全序、artifact/coverage seal 与 source/OMS 分层；
- cumulative fill、pending clock、保护、reconcile reducer；
- Pivot/TargetBoundary；
- ledger canonical bytes/hash、sealed full-bundle replay幂等与 explicit conflict proof；
- C5 Pi_exit 与 label gap/censor/override arbitration。

### 15.2 仍然 BLOCKED，但不阻止 P0-RSI-01B/02/03

1. `BLOCKED_HISTORICAL_ADAPTER`：source→CanonicalSyntheticEventBundle mapping 在本版本有意不存在；只能在 P0-RSI-04 单独 contract/审计，不能塞进 pure reducer。
2. `BLOCKED_EMPIRICAL_DATA_FITNESS`：真实或历史源能否满足严格 1 秒 book grid、post-pressure recovery、OI endpoint 和 gap 规则尚无证据。只能在 P0-RSI-04 授权前审查，不能放宽公式救数据。
3. `BLOCKED_PREDICTIVE_VALIDITY`：baseline/任一 challenger 是否有 log-loss、Brier 或成本后 EV 增量完全未知；当前 E0。
4. `BLOCKED_EXECUTION_REALISM`：1 秒 synthetic ACK、公开深度 capacity、stress slippage 和 pending cap 尚未由真实订单遥测验证；必须等预测有效性通过后另建 contract，不得用于 paper/trading sizing。
5. `BLOCKED_VENUE_ACCOUNT_SEMANTICS`：真实 position mode、margin tier、liquidation、rate limit、order amend/cancel race 和 exchange error taxonomy 未形成 production contract。
6. `BLOCKED_CALIBRATION_HOLDOUT`：没有获授权的 CALIBRATION/HOLDOUT data role、receipt 或 frozen candidate。

若新 v0.2.1 contract 无法逐字段表达本文件，P0-RSI-01B 必须标 `BLOCKED_CONTRACT_SERIALIZATION`；禁止用代码注释或测试 fixture 替代规范字段。
