# Generalized Competing-Path Theory Challenger v0.5.0

> 阶段：`V5-M00 / E0 / NO_NEW_OUTCOME_ACCESS / SYNTHETIC_ONLY`
> 日期：2026-07-26
> 权威上位理论：`CORE_TRADING_THEORY.v2.1`
> 不可变权威路径：`CORE_TRADING_THEORY_v2_1.md`
> 权威原始 SHA-256：`2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d`
> 权威大小：`140126` bytes
> 当前根镜像：`CORE_TRADING_THEORY.md`（必须 byte-equal）
> 当前状态：`SYNTHETIC_TESTS_PASS_AWAITING_SOL_V5_M00_REGATE`

## 0. 权限与替代边界

本 challenger 只冻结通用多视角竞争机制与动态路径的 E0 方法。它不读取新的真实市场或 outcome，不授权 B4、source adapter、download、backtest、calibration、holdout、paper、live 或交易。随包保存的 `SEEN_NARRATIVE` 用户案例只用于诊断展示；正式规则冻结与 synthetic tests 均不得依据其已知结果调参。

v0.4 D1…D8/H10/H11 固定序列已被用户澄清明确拒绝，只保留为历史 E0 工件。本版本不迁移固定八日形态、价格事实链、H10/H11 ID 或 holdout 角色；八日经验只可作为 `PatternInstance` case。v0.4 六工件保持物理不变。

通用理论不扩大 BTC V1 权限。当前 1W/1D/4H/1H/15m 只属于 `BTC_V1_ORDERED_ROLE_PROFILE`，其他标的、周期、机制和动作必须另行申请。

## 1. 概念分层

合法链为：

```text
DataLayer
→ StateAxis
→ AnalyticalPerspective
→ competing MechanismSpec
→ variable-length PathSpec/PathBeliefSet
→ mutually-exclusive ScenarioDistribution
→ ActionCandidate
→ PermissionEnvelope
→ UpdateReceipt
```

DataLayer 是点时可见事实；StateAxis 是可以并存的状态维度；Perspective 是组织证据的观察坐标；Mechanism 是竞争解释；Path 是部分有序的可观察演化；Action 是效用、几何、权限和风险的结果。任何 anchor、event、RSI、形态、volume spike 或 wick 都不等于 signal。

### 1.1 分析视角矩阵与标准输出卡

| 分析视角 | 可观察输入 | 能支持的状态/机制 | 关键区分证据 | 禁止越权推断 |
|---|---|---|---|---|
| 价格结构 | 点时 OHLC、pivot、区间、突破/补回 | 方向/结构、range、continuation/reversal 候选 | 冻结确认窗是否保持、反向结构是否失效 | 形态等于意图或订单 |
| 成交/订单流 | 成交方向代理、量、冲击响应 | 压力/拥挤、continuation/absorption 候选 | 同等流量的边际冲击与独立源一致性 | proxy 等于真实参与者身份 |
| 流动性 | spread、深度、补单/撤离代理、滑点 | 流动性、vacuum/absorption/artifact 候选 | 深度恢复和跨 venue 复现 | 无完整簿时强拆撤单或吸收意图 |
| 衍生品/杠杆 | OI、funding、basis、强平下界代理 | 杠杆/拥挤、deleveraging 候选 | 与价格/流动性同步且点时可得 | 代理等于完整强平量或真实仓位 |
| 波动 | realized/可得 implied proxy、range、jump | 波动状态、stress/transition 候选 | 是否与结构和流动性变化同窗 | 高波动直接等于方向 |
| 事件/宏观 | 发布时间、vintage、类别、surprise proxy | 事件风险、event-repricing 候选 | 发布先后、revision 隔离、matched comparator | 标题情绪等于方向 alpha |
| 跨场 | 跨 venue/现货-衍生品价格、basis、深度、时钟 | 局部异常、传导、artifact 候选 | 同步时钟下的 lead-lag 复现 | 相关性等于因果或权限 |
| 数据质量 | freshness、gap、schema/version、clock、conflict | 数据质量轴、artifact/UNKNOWN | 独立重建、版本审计、冲突定位 | missing 补零或 silence 等于无事件 |

标准输出卡固定为：

```text
可见事实/缺失 → 多尺度状态/UNKNOWN → 候选机制/OTHER
→ 分支路径与当前前缀 → 下一支持/反证/hard falsifier/expiry
→ UNKNOWN 或选择 → Permission/EntryZone/效用/风险/动作约束
→ immutable UpdateReceipt
```

它只冻结报告语义，不扩大为 runtime 实现。

## 2. 精确对象

本版本冻结十一个核心对象、一个诊断对象与一个 E0 合成账本辅助对象：

1. `ObservationFrame`：decision time 下可见数据、质量、required/optional missing、dependency groups 和 provenance。
2. `MultiScaleStateBelief`：ordered role profile、各角色状态轴、不确定性与 unknown reason。
3. `MechanismSpec`：可共存 primitive 机制的 evidence contract、支持、软反证、hard falsifier、expiry、path family 和等价类。
4. `PathSpec`：非空去重的 `primitive_mechanism_ids`、milestone vocabulary、partial-order edges、skip/repeat、variable observation count、冻结 event-time stopping/expiry、PathEvent schema 和 predeclared merge。
5. `PathEvent`：exact `path_event_id/path_instance_id/milestone/event_at/available_at/terminal_reason/terminal_trigger_id/source_version` carrier。
6. `PathBeliefSet`：非归一 `primitive_support_by_mechanism`，以及仅在合法 competition set 内存在的 compound path weights、top path、margin、entropy/UNKNOWN、residual 与更新 receipt。
7. `ScenarioDistribution`：exact 互斥 branches、qualitative/synthetic-counterfactual/unknown mode、归一状态和 authority-compatible version。
8. `UtilityReceipt`：canonical digest 绑定完整 ScenarioDistribution、utility/cost/tail/uncertainty、`as_of` 和 authority。
9. `ActionCandidate`：验证三类 exact carrier 并绑定其 ID/digest；V5-M00 action 只能 `ABSTAIN`。
10. `PermissionEnvelope`：permission、允许动作、风险上界、veto 与 authority version。
11. `UpdateReceipt`：前后摘要、唯一证据、dependency-group aggregation、版本与 hash chain。
12. `PatternInstance`：叙事或已观察案例到多个冻结候选机制的诊断映射；必须保存非空唯一的 `candidate_mechanism_ids`、origin、instrument/time、truth status 与 outcome visibility，其 `opportunity_universe_role` 必须为 `NONE_DIAGNOSTIC_ONLY`。
13. `EvidenceLedgerReceipt`：独立于既有 exact `UpdateReceipt` schema 的 versioned E0 合成转移账本；绑定 opportunity/path/mechanism scope、完整 method authority ID/raw SHA、decision time、保留 list/tuple 等精确类型的 canonical batch、由该 batch 重算的 validated effects、group/terminal winners、raw/clipped support、前后 state digests、前序 hash 与自身 hash。它只用于当前 synthetic reducer 的可重放审计，不是 runtime raw provenance carrier。

所有 schema 都是 exact-key closed。required missing 直接 `UNKNOWN`；optional missing 只能按字段冻结的 `IGNORE_WITH_MISSING_FLAG`、`BLOCK_TARGET` 或 `UNKNOWN` 处置，禁止补零。

## 3. 有限机制竞争

机制库精确为：

```text
CONTINUATION
ABSORPTION_REVERSAL
RANGE
LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM
EVENT_REPRICING
ARTIFACT
OTHER
```

`OTHER` 永远存在。runtime、LLM、analyst note 或 PatternInstance 不得创建新 ID。primitive mechanisms 可同时成立，support 是独立多标签序数，不归一也不互相挤压，不是现实机制、参与者身份或因果真值。`EVENT_REPRICING + LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM + CONTINUATION` 是合法共存例。`ARTIFACT` 属于 epistemic/data-quality role，只能影响质量否决与 UNKNOWN；任何可进入 normalized path mixture 的 market/residual path 只要含 `ARTIFACT` 就 fail closed，防止其直接或间接进入 utility。

`volume spike + long wick` 至少与 continuation、absorption-reversal、liquidation/liquidity-vacuum、artifact 和 OTHER 竞争，不能直接选择吸收或反转。未覆盖 feed silence 是 `UNKNOWN`，不是零流量或无事件。

| 机制 | Antecedent | 下一步支持 | 软反证 | Hard falsifier | Expiry/terminal | 禁止意图解释 |
|---|---|---|---|---|---|---|
| `CONTINUATION` | 方向响应有效 | 同向冲击/突破保持 | 动量减弱 | 冻结反向结构失效 | horizon/target/invalidated | 主力继续推动 |
| `ABSORPTION_REVERSAL` | 压力持续、边际冲击下降 | 韧性补回与反向响应 | 仅 wick 或补回不持续 | 同向扩展重启/吸收区失效 | response expiry/structure terminal | 机构吸筹或出货 |
| `RANGE` | 双向受限、边界有效 | 边界响应与中心回归 | 单侧逐渐占优 | 有效突破保持 | range expiry/breakout | 控盘震荡 |
| `LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM` | 急移与压力/流动性代理异常 | 强平下界、深度撤离或冲击继续 | 流动性快速恢复 | 完整数据证明 artifact/条件未发生 | stress expiry/recovery | 强拆为真实强平或撤单意图 |
| `EVENT_REPRICING` | 点时事件到达 | 发布后跨层响应 | 短暂或 comparator 相同 | 时钟不可证/revision 泄漏/响应先于事件 | event expiry/new vintage | 利好利空必然方向 |
| `ARTIFACT` | gap/schema/clock/venue 冲突 | 独立源不复现或审计失败 | 多源同步有效 | 完整独立数据复现并排除 artifact | repair/isolation | 坏数据代表市场意图 |
| `OTHER` | 已注册机制全弱或库外 | 持续不可区分 | 注册机制获独立支持 | predeclared coverage 排除 | coverage expiry | LLM 临时命名新机制 |

volume+wick observation 必须同时映射上述五个相关候选，不完成任何单一路径。

## 4. 动态路径

Path 不是固定天数序列。合法 path 的 `primitive_mechanism_ids` 必须非空、唯一并只引用注册库，可含 2、8、20 或其他数量的 observation；长度由冻结的 event-time expiry/stopping rule 决定。optional milestone 可以跳过，repeatable milestone 可以重复。`PathSpec` 本身 exact-key closed，并冻结 `stopping_policy_id / frozen_horizon_seconds / path_event_schema_id`；在任何 PathEvent 验证前，必须对完整 exact PathSpec canonical JSON 重算 SHA-256，并以 `path_id + digest` 精确匹配独立加载的 method-contract 有限 allowlist。digest 覆盖所有嵌套字段与数组顺序；待验证 PathSpec 不得携带、修改或自签其 authority。附加 `fixed_day_count=8` 等未声明字段即无效。实现的 runtime capacity guard 只保护资源，不是市场路径长度或终态；超限必须状态压缩或延续 receipt chain，做不到时输出 `UNKNOWN_RESOURCE`，绝不能把 path 标为 `FALSIFIED/EXPIRED/TERMINAL`。任何未注册 milestone/primitive、违反 required edge、未声明重复、outcome 后新建 path 或非等价 merge 都 fail closed。

每个 `PathEvent` 必须 exact-key，时间戳 aware，并满足 `path_started_at <= event_at <= available_at <= decision_time`；`event_at` 严格递增。最后且唯一 terminal event 只能标注 `TERMINAL_MILESTONE`、引用冻结 allowlist 的 `HARD_FALSIFIER`，或精确等于 `path_started_at + requested_horizon_seconds` 的 `EXPIRY`。三者的最早到达立即停止路径，后续事件无效；requested horizon 不能超过 `frozen_horizon_seconds`。`NEVER_STOP`、`FIXED_8_DAY`、future/naive/missing timestamp、expiry 后继续及 horizon extension 全部 fail closed。

只允许有限、事前注册的 compound templates；禁止 primitive power set、runtime Cartesian product 或 LLM compound injection。qualifier 尽量作为 multi-hot 属性保存。canonical 去重绑定 `path_template_id + sorted primitive_mechanism_ids + scope`。当前 residual 精确为 `OTHER_PATH`、`role=RESIDUAL_PATH`、`primitive_mechanism_ids=["OTHER"]`；`OTHER` 不得出现在 market path，`ARTIFACT` 不得出现在任何 mixture-eligible market/residual path。

每条 evidence 只允许 `SUPPORT / SOFT_CONTRADICTION / HARD_FALSIFIER`。hard falsifier 立即把当前 `path instance / opportunity episode` 置于 terminal class；后到的普通 Evidence 不得救回、触发行动或改写旧 receipt，但 event-time 早于 terminal cutoff 的 late ordinary evidence 可以修正 current derived support，等于或晚于 cutoff 的普通 Evidence 必须拒绝。hard falsifier 不永久删除机制库中的机制。新的独立 opportunity 可在新的 `ObservationFrame` 下以新 episode/path-instance/receipt chain 重新实例化同一机制，但 V5-M00 只在调用方显式提供 predecessor 时执行 pairwise reinstantiation validator；没有全局 ObservationFrame/scope registry，不能据此证明跨进程唯一性。soft contradiction 只降低支持；expiry 到时不延长。

终态单调指 **terminal class 不得返回 `ACTIVE/UNKNOWN`**，不表示第一个被处理的 terminal reason 永远冻结。完整 PathSpec-bound lifecycle carrier 使用最后一个已验证 `PathEvent.event_at`；`EXPIRY` 还必须精确等于 `path_started_at + requested_horizon_seconds`。既有 exact Evidence 没有 `event_at`，所以 V5-M00 对 HARD_FALSIFIER Evidence 保守使用 canonical UTC `available_at` 作为有效时间。同一时刻不使用可由调用方磨选的 source digest，而使用冻结语义优先级 `HARD_FALSIFIER < EXPIRY < TERMINAL_MILESTONE`，再用 method-bound `terminal_authority_id` 决胜。后来到达但排序更早的终态证据可以把 `EXPIRED/TERMINAL` 修正为 `FALSIFIED` 或反向修正 reason/status，但仍留在 terminal class。

冻结采用 event-time 语义 B：current derived state 始终保留所有 `effective_at < terminal cutoff` 的 ordinary candidates，包括 terminal 后才到达的 late evidence；`effective_at >= cutoff` 的 ordinary candidates 必须拒绝或在 winner 变早时由补偿重算撤销。随后统一重算 underlying groups、group winners、raw/clipped support。旧 receipt prefix 是当时 decision-time view，字节保持不变；补偿只体现在新 receipt 的 current state projection。`SUPPORT/SOFT_CONTRADICTION/HARD_FALSIFIER` 同批或分 receipt、以及所有合法处理排列，必须收敛到相同 cutoff-eligible identities、terminal winner、support 与 state digest。`EXPIRED_OR_UNKNOWN` 保留为 schema 终态，但 V5-M00 没有可生成它的 synthetic lifecycle source，调用方不得直接创建。

## 5. Evidence ledger、更新和依赖去重

E0 synthetic-only、no-new-outcome ledger 使用 ordinal strength `WEAK/MODERATE/STRONG`，禁止概率。Evidence 必须 exact-key，identity/target 非空唯一，direction/strength/quality 使用冻结 enum，且 aware `available_at <= decision_time`。当前 decision time 之前尚不可用的 exact Evidence 标为 `RETRYABLE_AT_LATER_DECISION_TIME`：相同 canonical decision context 重试是 byte-identical no-op，较晚且不倒退的 decision time 必须重新推导；schema、authority、identity drift 等永久 rejection 不得借换时间重试。所有输入行必须先完成 exact schema、类型、enum、时钟、quality 与 `target_ids` 验证，再做 target filter；`target_ids` 为字符串、tuple、混合类型或其他无法确定 scope 的 malformed 值时，整个 target-scoped aggregation 返回 `UNKNOWN`、support 不变并记录 rejection，禁止静默滤掉坏行后对其余行局部更新。

`evidence_id` 在每个 target-scoped batch 内必须唯一；任何重复（同内容、跨 dependency group、字段冲突，或 SUPPORT 与 HARD_FALSIFIER 冲突）均拒绝整个相关 batch，support 不变且状态为 `UNKNOWN`，不得通过调用方的 `dependency_group` 规避。missing、malformed、naive、未来（包括直接 `2099-...`）、schema 漂移和非 `VALID` quality 必须记录 rejection 并返回 `UNKNOWN`，不能改变 support。相同底层增量的派生视角共享 `dependency_group`；组内按冻结的最大绝对增量和 `evidence_id` tie-break 聚合，只能贡献一次。

当前 method contract 的独立 `V5-M00-SYNTHETIC-EVIDENCE-LINEAGE-V1` authority 只允许冻结的 synthetic source/perspective，并从 canonical admitted projection 重算 `evidence_id` 与 `dependency_group`；外部 ledger identity 另记录 `underlying_increment_id`。`available_at` 在参与 identity/content digest 前必须解析为 timezone-aware 并渲染为 UTC `Z`；`target_ids` 只用于精确 ledger routing，不充当 raw underlying identity。待验证 Evidence 不得自签 authority，helper 每次调用必须重新读取并校验 exact method artifact 的路径、原始 SHA-256、contract/stage/status，禁止模块内可变 allowlist 或内存替换成为权威。

该 authority 有明确能力上限：既有 exact Evidence carrier 没有 raw source record identity 或 transform lineage，因此当前 canonical projection 可能保守地把投影相同但原始记录不同的增量视为同一项；反之，微调 `available_at` 也可能把同一个现实来源投影成新 underlying/group。它只关闭 E0 synthetic identity contract，不证明真实数据 provenance。任何未来 runtime admission 必须另行冻结 raw `AuthorityBundle`，至少绑定 contract/stage、source artifact path/digest、raw record identity、transform identity/version，以及 deterministic evidence/dependency/underlying identities；在此之前不得把测试 helper 称为数据 adapter 或 runtime ledger。

每个 opportunity/path-instance 的 `EvidenceLedgerReceipt` chain 必须以 `observation_frame_id + episode_id + path_instance_id + mechanism_id` 的 canonical scope digest 隔离，并从 strict genesis（注册机制、`ACTIVE`、support/raw support 均为 0、空 chain）开始。receipt 的 `decision_time` 必须解析 aware time 并只以 canonical UTC `Z` 保存，整条 chain 非递减；相同时刻和等价时区允许，倒退在入口与 reducer 均 fail closed。receipt 绑定完整 method ID/raw SHA、canonical decision time、`rejection_class`、由 scope/kind/batch/time/class 生成的 `idempotency_key`、精确 type-tagged canonical batch、batch/effect digests、validated effects、admitted evidence/lifecycle identities、全账本 group winner、semantic terminal winner、未裁剪 raw support、裁剪 support、前后 state digests、连续 receipt ID、前序 receipt hash 和完整自身 hash。reducer 必须从 genesis/前一重放状态重新推导，不相信 receipt 自报的 before/after/hash 自洽性。

跨 receipt 重放相同 `evidence_id` 或同 ID 内容漂移必须拒绝。同一 `underlying_increment_id + dependency_group` 的不同 authority-valid evidence 不是新增独立贡献，只能竞争同一个全账本 group winner；按绝对 signed ordinal delta 最大、再按 `evidence_id` 字典序最小选择。更强候选只用 `new_delta-old_delta` 替换，更弱候选不得降低 winner；`raw_support` 始终保存未裁剪总和，外显 support 才裁剪到 `[-9,9]`。同一 underlying 被改入不同 group 必须 fail closed。由此，ordinary-only 以及 ordinary 与 HARD_FALSIFIER 混合的单批、分批和 receipt 排列都必须在非递减 decision clock 下收敛。

第一次 evidence replay 违规追加一条可审计永久 rejection receipt；相同 idempotency context 再试必须返回 byte-identical episode/chain。只有 `RETRYABLE_AT_LATER_DECISION_TIME` 可在较晚 decision time 重推；`COMPACT_REQUIRED_RECEIPT_CONTINUATION` 必须成为 `RESOURCE_CAPACITY_REQUIRED/UNKNOWN_RESOURCE` rejection，绝不能生成 terminal effect。target 必须是 exact singleton path instance，附加 alias 即拒绝；等价时区先 canonical UTC，不能借时间表示法重复计数。完整 lifecycle 终态 carrier 必须携带 exact PathSpec、ordered PathEvents、path start、requested horizon 与 terminal time，重新通过有限 PathSpec allowlist、episode mechanism 必须属于 PathSpec primitives、scope、因果时钟、earliest stopping、预声明 hard trigger和 exact expiry 验证；仅复制 `path_id/path_spec_digest/status` 的旧短 carrier 无效。

接受的 lifecycle ID/digest 必须进入内部 ledger identity set；同一 exact lifecycle 与同一 canonical decision context 重放立即 byte-identical no-op，同 ID 内容漂移永久拒绝，不同且更早的 valid terminal 仍可竞争。current terminal winner 使用不含任意 PathEvent ID/source digest 的 `semantic_terminal_id`；完全同 rank、同义但 provenance 不同的 carrier 可在 receipt 留痕，却不能改变 winner 或 current state digest。完整 carrier 仍由调用方作为 synthetic input；当前无独立 path-instance event-log tip、原始 PathEvent 记录或外部事实权威，所以这里只证明 **合成结构可推导性**，不证明现实 terminal 事实。

当前纯 reducer 只能证明 **调用方提供的 canonical prefix 内部可推导**。调用方如果提供先前可信的 `expected_tip_hash`，截尾或替换会因 tip mismatch 被拒绝；但 V5-M00 没有外部不可变 tip/seal，无法发现调用方同时替换完整 canonical batch、receipt chain 和所声称 expected tip 的跨进程 fork。该边界不得被表述成 runtime append-only、防回滚或 raw provenance 已完成。

\[
q_m'=\operatorname{clip}\left(q_m+\sum_g A_g(\Delta_{g,m}),-Q,Q\right).
\]

primitive support 永远不做以下 softmax，也不要求总和为 1。未来只有在另获 CALIBRATION 授权且 compound `PathHypothesis` competition set 合法时，才允许：

\[
\alpha_h'=\frac{\alpha_h\exp(\Delta_h)}
{\sum_{j\in H_C}\alpha_j\exp(\Delta_j)}.
\]

合法 set 不接受任意非空 `exclusivity_basis`，而必须引用冻结有限的 `partition_proof_id`。proof 与 set 必须精确绑定 `competition_set_id`、对有序 path registry 完整定义重算的 canonical `path_registry_digest`、canonical full `partition_proof_digest`、`partition_version`、有序 `path_hypothesis_ids`、有限 domain values 及同序逐 path 非空 partition cells、`mutually_exclusive=true`、`exhaustive=true`、`residual_path_id=OTHER_PATH`、精确 `residual_domain_values=["OTHER_OR_UNRESOLVED_TERMINAL"]` 和非空 `calibration_version`。full digest 对 proof 除 `partition_proof_digest` 自身外的完整 canonical JSON 取 SHA-256；method authority 的 finite allowlist 另精确绑定 proof digest、path registry digest、eligible paths、partition domain ID/values 和 residual scope，且 scope 必须同时含 market path 与 residual，禁止 residual-only authority。path registry digest 覆盖每行精确 `path_hypothesis_id + primitive_mechanism_ids + role` 及数组顺序，不能只凭未变 ID 复用旧 proof。合成 helper 只查验 cells 对预注册 domain 无重叠且无遗漏，不把它夸大为现实市场的数学证明。`NOT_A_PROOF`、authority 未登记、residual-only shrink、domain/cell rename、market cell swap、domain ID 或同 identity 内容漂移、path 定义、set/path/cell/版本漂移、缺 residual、非穷尽、market path 含 `OTHER` 或任一路径含 `ARTIFACT` 都禁止 path normalization。primitive support 不得直接充当 $\alpha_h$，同一 primitive 可出现在多个 compound path 中。

只有合法 competition set 才输出 top path、top-two margin 和 entropy；否则输出并存 primitive 与 `UNKNOWN_NO_VALID_COMPETITION_SET`。required missing、tie、全弱、uncovered feed 或库外解释产生 `OTHER/UNKNOWN`。

## 6. Scenario 与动作

纯价格 Scenario branches 精确互斥：

```text
UPSIDE
DOWNSIDE
RANGE
UNRESOLVED
```

event/liquidity 只作 mechanism/path qualifier，不能冒充价格终态。提交后的 `ActionOutcome={NO_FILL,TP_FIRST,SL_FIRST,STRUCTURE_EXIT,TIMEOUT}` 独立建模。`QUALITATIVE_E0` 只允许冻结序数值且不能含数值；V5-M00 数值只允许 exact `SYNTHETIC_COUNTERFACTUAL_ONLY` carrier 做纯合成算术，每 branch 必须有限非布尔、位于 `[0,1]` 且和为 1。raw probability map、伪 `calibrated` bool、future/missing `as_of` 和 `CALIBRATED_PROBABILITY` 均未获授权。

V5-M00 只可由 exact synthetic counterfactual ScenarioDistribution 计算：

\[
LCB_U(a)=\sum_s\pi_sU(a,s)-Cost_{stress}-Tail-Penalty_{uncertainty},
\]

\[
EntryZone=\bigcap_k Z_k,\qquad
q=\min\left(\frac{R_{budget}}
{|P_{entry}-SL|+Cost_{worst/unit}+Tail_{unit}},Q_{liq},Q_{venue},Q_{margin}\right).
\]

第一式必须生成 canonical `UtilityReceipt`，完整绑定 ScenarioDistribution ID/digest、逐情景 utility、stress cost、tail、uncertainty penalty、`as_of`、authority 与自身 digest；raw scalar 或任一字段/摘要漂移无效。第二式只是独立 research geometry candidate：LONG 为 `SL < zone.low <= zone.high < TP`，SHORT 方向相反，horizon 不延长；几何或正 utility 均不产生权限。

V5-M00 的 exact PermissionEnvelope 仅接受 `DENY/UNKNOWN`、`allowed_actions=["ABSTAIN"]`、`max_risk=0` 与 `authority_version=V5-M00-E0-NO-NEW-RISK`。ActionCandidate 必须验证并绑定 ScenarioDistribution、UtilityReceipt、PermissionEnvelope 的 ID/digest；完整有效时也只能返回 `ABSTAIN / V5_M00_NEW_RISK_FORBIDDEN`。无效 carrier 分别返回 `SCENARIO_DISTRIBUTION_INVALID / UTILITY_RECEIPT_INVALID / PERMISSION_ENVELOPE_INVALID` 并清空对应绑定。numeric/calibrated market action mode 只有未来另获授权后才可评估。

只有未来合法 compound competition set 才可另行使用 path-conditioned utility。primitive support、ARTIFACT support、任何含 ARTIFACT 的 market/residual path，以及未通过已登记 partition proof 的 path scores，均不得直接或间接进入 mixture。

持仓后只允许 `KEEP/TIGHTEN/REDUCE/EXIT`。path switch 不自动 reverse；stop 单向收紧，size 只能不变或减少。反向交易必须是独立 opportunity、几何、风险和权限。

## 7. 评估时钟、多尺度与四层

评估触发为 `SCHEDULED / STATE_CHANGE / EVENT_ARRIVAL / DATA_QUALITY_CHANGE / POSITION_RISK`。RSI 是 optional trigger；即使 RSI 为 `None`，上述五类评估仍全部运行，尤其 `EVENT_ARRIVAL` 不得因 RSI 缺失而静默。

`BTC_V1_ORDERED_ROLE_PROFILE` 的顺序职责为：

- 1W：risk background；
- 1D：structural background；
- 4H：operational regime；
- 1H：setup；
- 15m：evaluation/optional trigger。

四层独立：L1 current pressure/data、L2 multi-scale state、L3 past-only analog、L4 point-in-time event。任一层缺失不会被另一层补零或伪造成中性；required missing 导致相应 target `UNKNOWN`。

## 8. PatternInstance 与八日案例

`CASE-USER-EXPERIENCE-SHOCK-COMPRESSION-001` 只保存一个用户经验案例：

- `origin=USER_EXPERIENCE`，instrument/time=`UNSPECIFIED`；
- `truth_status=ANECDOTAL_UNVERIFIED`；
- `outcome_visibility=SEEN_NARRATIVE`，因此不能称 outcome-free；
- observation_count 可以改变，不以 8 为规则；
- milestone 可以 skip/repeat；
- 同时映射多条 path；
- 不定义 opportunity universe；
- `not_for_holdout_selection=true`；
- 不提供 prior、market support、DEVELOPMENT/CALIBRATION/HOLDOUT 或 action permission。

该案例只映射非空、唯一、已注册的 `candidate_mechanism_ids`；空数组、重复 ID 或 runtime/LLM 新 ID 都无效。机制随后是否产生哪一条 `PathSpec` 必须由独立 ObservationFrame 和冻结规则决定。其已知叙事结果不参与本版本规则冻结或 synthetic assertion 选择。

## 9. 未来验证与 falsification

未来只有在独立授权后，才允许 walk-forward DEVELOPMENT/CALIBRATION/HOLDOUT。概率使用事前冻结的 Brier、log score 或其他 strictly proper scoring rule；同时报告 calibration、sharpness/分辨率、coverage、abstention、tail 和成本后 utility。

错误归因精确分为 `DATA_AVAILABILITY / STATE / MECHANISM_LIBRARY / PATH_SPEC / DEPENDENCE / CALIBRATION / ACTION_GEOMETRY / COST_EXECUTION / PERMISSION_RISK`。每次 theory delta 只能修改一类，并使用新版本和未见 chronology；任何已读窗口永久 SEEN。

## 10. V5-M00 闸门

V5-M00 只在纯 synthetic contract 证明以下反例全部 fail closed 后，才可提交 Sol 复核：

- 2/8/20 observation path、skip/repeat 与 partial order；
- required/optional missing；
- dependency duplicate；
- malformed `target_ids` 在 target filter 前被拒绝，且不得产生局部 support update；
- 跨 receipt evidence-ID replay、同 ID 语义漂移、同 underlying 改组，或同 underlying/same-group candidate 被错误累计成第二份贡献；
- receipt decision time 非 canonical UTC、chain 倒退，或等价时区被当成不同 idempotency context；
- future Evidence/lifecycle rejection 被永久锁死而无法在较晚 decision time 重推，或永久 rejection 被错误重试；
- lifecycle identity 未进入 ledger、同 exact/context 重放追加 receipt、同 ID drift 未拒绝，或不同更早 terminal 无法竞争；
- terminal class 被 late pre-cutoff ordinary evidence 重新激活，late before/equal/after cutoff 未按 event-time B 处理，或 SUPPORT/SOFT/HARD 同批与分批不收敛；
- 同刻 terminal reason 由可磨选 source digest 而非冻结语义优先级决定，或同义 carrier 的任意 PathEvent ID/source digest 改变 current state digest；
- PathSpec capacity guard 返回 `COMPACT_REQUIRED_RECEIPT_CONTINUATION` 却被 lifecycle admission 生成 terminal effect；
- receipt scope/order/previous-hash/self-hash/method-authority 篡改、空 effects 自报 0→9、替换 batch 外 effect、整链字段重写并重哈希，或同一 batch 排列产生不同语义；
- 非零/终态空链伪造 genesis，或 empty/rejection-only transition 改变 support；
- 同组 weak/strong 在单批、weak→strong、strong→weak 下产生不同最终 winner/raw/clipped support/status/state digest；
- target routing 附加 alias 或等价时区表示被用来重复计数；
- 把 caller-supplied expected tip 误称为外部不可变 tip/seal，或宣称纯函数能发现跨进程全链替换；
- method authority 内存替换、调用间不重新读取，或 exact Evidence carrier 被误称为 runtime raw lineage；
- runtime mechanism injection；
- evidence future/missing/malformed/naive `available_at` 改变 support；
- uncalibrated pseudo-probability；
- raw Scenario map、伪 calibrated bool 或 future/missing `as_of`；
- raw/tampered UtilityReceipt、raw/future/pseudo-allow PermissionEnvelope；
- scenario non-normalization；
- volume+wick forced path；
- uncovered feed silence；
- late event prefix rewrite；
- all weak forced choice；
- RSI `None` 时 `EVENT_ARRIVAL` 或其他通用评估静默；
- empty EntryZone/permission deny，或研究几何绕过全局 `ABSTAIN`；
- path switch auto reverse；
- invalid point/risk geometry；
- PatternInstance 创建 opportunity universe，或候选为空/重复/未注册；
- primitive support 被归一或新增一项 support 压低另一项；
- compound PathSpec 的 primitives 为空、重复或未注册；
- PathSpec 附加固定天数字段、`NEVER_STOP`、`FIXED_8_DAY`、horizon extension、终止后事件、非因果 PathEvent 或错误 expiry；
- path normalization 引用 `NOT_A_PROOF`、未登记 full-proof authority、residual-only shrink、proof/domain/cell/market assignment 漂移、集合/版本漂移、cell 重叠/缺口、缺 residual、非穷尽或 calibration version 不一致；
- primitive weights/ARTIFACT 直接进入 action utility，或 ARTIFACT 经 market/residual path 间接进入 utility；
- runtime power-set 或未注册 compound injection。

即使 synthetic 全部通过，证据仍为 E0，`B4/DATA/BACKTEST/CALIBRATION/HOLDOUT/PAPER/LIVE=FORBIDDEN`，下一状态只能是 `AWAITING_SOL_V5_M00_REGATE`。
