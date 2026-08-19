# MSTA-HED 技术指导 v0.6.0

> 状态：`E0_OUTCOME_FREE_DRAFT_AWAITING_SOL_STAGE_GATE`
>
> 本文件是实施边界说明，不替换 [CORE_TRADING_THEORY_v2_1.md](./CORE_TRADING_THEORY_v2_1.md)、v0.5 method contract 或 registry。当前不授权 `DATA`、`OUTCOME`、`BACKTEST`、`CALIBRATION`、`HOLDOUT`、`PAPER`、`LIVE`、`DEPLOY` 或活动 G1 mutation。

## 1. 当前事实审计

审计锚：`as_of=2026-07-26T18:26:45+08:00`；cwd=`/Users/wt/Documents/agent-trade-emotion`；branch=`codex/s0-research-foundation`；HEAD=`7ca3fc4f99a57f98217e703f222b295653ace87e`；worktree 为 dirty/untracked。权威文件 SHA-256：CORE=`2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d`，method=`18ef5234cb018d1a89252733a6d66903a145864031a2c8d663f021abe79740b0`，registry=`fed1bcceac87582f811f57f420b83481e1621dbd8eb6627ab2fc5ee2357a33b3`，synthetic=`4159cb6bfb82022db15a95951dcc9e60e53779c900892c48196139f07140d628`。下列行号、状态与缺口仅适用于这个快照，不能外推为持续运行事实。

| 链路模块 | 状态 | 当前本地证据 |
|---|---|---|
| 数据有效性 | `PARTIAL` | 双 append-only raw/availability、seal 与 ACTUAL 防回填在 `trade_system/types.py:95-174`、`trade_system/event_store.py:38-59,131-154,179-245`；质量引擎只覆盖 critical streams/age/book health：`trade_system/quality.py:12-64`。 |
| 多周期状态 | `PARTIAL` | episode clock 与 pipeline 在 `trade_system/episode_policy.py:36-111`、`trade_system/pipeline.py:108-124,317-384`；4H-capable context 在 `trade_system/feature_context.py:169-178,323-377`，但配置仍是 unresolved template：`config/feature_context_policy.frozen.template.json:2-23`。 |
| 结构位置 | `PARTIAL` | 局部价格、深度、压力、韧性在 `trade_system/features.py:58-116`；现有 classifier 仅为 thin/deep/normal visible book：`config/state_classifier.v1.json:2-28`，没有 MSTA StructuralPosition runtime object。 |
| 有限假说竞争 | `IMPLEMENTED_CONTRACT_ONLY` | v0.5 object schemas/finite registry 位于 `config/generalized_competing_path.hypothesis_registry.v0_5_0.json:54-214,216-288`；synthetic partition/authority/ARTIFACT fail-closed 检查位于 v0.5 test module。该文件是 test helper，不是 runtime。 |
| 证据更新 | `IMPLEMENTED_CONTRACT_ONLY_AWAITING_SOL_REGATE` | 既有 exact Evidence 与 UpdateReceipt schema 未改变。canonical synthetic identity 在 tests `:233-467`，typed batch/decision context/lifecycle authority 在 `:657-1065`，effect derivation/full-ledger reducer/new-opportunity hook 在 `:1259-2305`；第三轮 P0 反例在 `:5064-5605`。当前 58 项 E0 synthetic tests 通过，但这仍不是 raw provenance、external-sealed ledger、source adapter 或 runtime implementation。 |
| 交易假说/触发 | `FORBIDDEN_AT_CURRENT_GATE` | 旧 action bundle 只生成 counterfactual、无 execution evidence 的 research action：`trade_system/action_bundle.py:92-113,145-242`；v0.5 禁止 market/outcome/backtest/paper/live/trading：`config/generalized_competing_path.method_contract.v0_5_0.json:20-41`。 |
| utility | `FORBIDDEN_AT_CURRENT_GATE` | 旧保守 EV policy 是 pure calculation：`trade_system/decision.py:98-173`；G2 明说非 execution PnL：`trade_system/g2_evaluator.py:391-424`；v0.5 只允许 synthetic counterfactual。 |
| 风险 | `PARTIAL` | 本地风险限额在 `trade_system/risk.py:114-195`，保护/对账/HALT 在 `:258-333,434-518`；生产值仍须 M6A/G4A 另行签署：`SYSTEM_DESIGN_ROADMAP.md:438-448,831-837`。 |
| 执行 | `FORBIDDEN_AT_CURRENT_GATE` | `trade_system/paper.py:1-37` 是 visible-book paper IOC simulation，不是授权 broker adapter。 |
| 反馈/校准 | `FORBIDDEN_AT_CURRENT_GATE` | G2 有 walk-forward/bootstrapping：`trade_system/g2_evaluator.py:427-540`，但无合格 development evidence；v0.5 明确禁止 calibration/holdout：`config/generalized_competing_path.hypothesis_registry.v0_5_0.json:38-52`。 |

`tests/test_generalized_competing_path_v0_5_0_contract.py:1-25` 明示其只读取本地 theory/contract，不读市场、outcome、G1、adapter、backtest 或 account。因此测试内 `_aggregate_evidence` 等 helper 绝不能被宣称为 production/runtime implementation。

### 1.1 2026-07-26 只读活动 G1 快照

此快照只记录本轮已提供的只读运行事实；它不改变 E0 权限、不授权访问活动目录，也不得被表述为 G1 `PASS` 或 `FAIL`。

- active plan raw SHA-256 为 `189317fdff53d9f0ca64747d48690a283a3328b04df539f53307eb1370c3cb6d`，registry SHA-256 为 `b3848092824dc65e9fea6ac524811453b8abf4783b865d8c057089cb5603453f`；本轮只读比较显示二者均与冻结值一致。
- `d4-h06` raw/availability 各有 58,165 行，mtime 为 `15:01:19+0800`；supervisor stdout 最近记录该 slot 为 `UNQUALIFIED_NOT_SEALED`。这不是对整个 G1 计划的通过或失败裁决。
- 16:12 的只读检查没有 capture worker；LaunchAgent one-shot supervisor 为 `not running`、`runs=2`、`last exit=1`。这是当时进程状态，不说明未来 slot 结果。
- 可用磁盘为 15,914,766,336 bytes，较 frozen minimum 16,106,127,360 bytes 少 191,361,024 bytes。因此它是潜在的下一 slot resource blocker；不得修改活动目录、计划、registry、package、日志或 evidence root 来尝试恢复。

## 2. 旧链与 MSTA v0.6 adapter boundary

旧 v1 链是：`EventStore → FeaturePipeline/Episode → research action/label/state → G2 → local paper risk/OMS`。MSTA v0.6 候选链是：`ObservationFrame → belief/position → mechanism/path/evidence receipt → scenario/thesis/utility/permission/action`。

两条链可在未来通过版本化 adapter 连接，但当前不得混写：

- 旧 `EpisodeState` 不是 MSTA `MultiScaleStateBelief`；
- 旧 `state_classifier` 的 liquidity bucket 不是 StructuralPosition；
- 旧 research `ActionRule`/counterfactual label 不是 TradeThesis 或 executable ActionCandidate；
- G2 market-path utility 不是 ScenarioDistribution、fill model 或 permission；
- paper `OrderStatus`/`SystemHealth` 不是 epistemic belief；
- 同名的 `state`、`action`、`risk`、`outcome` 都须带 namespace/version/digest。

任何 adapter 都必须显式输入/输出 source schema、availability semantics、version digest、unknown mapping 和 authority stage。没有该 adapter 的对象不得互相替代。

## 3. 最小目标对象与接口建议

v0.5 已定义 `ObservationFrame`、`MultiScaleStateBelief`、`MechanismSpec`、`PathSpec`、`PathEvent`、`PathBeliefSet`、`ScenarioDistribution`、`UtilityReceipt`、`PermissionEnvelope`、`UpdateReceipt` 与 `ActionCandidate` 的权威字段。实现时必须引用 v0.5 contract/registry，不复制一份漂移 schema。

| 对象 | 现状 | v0.6 DRAFT 最小补充建议 |
|---|---|---|
| `ObservationFrame` | v0.5 authority | 用 versioned adapter/reference binding 将 RoleProfile、input availability summary、quality disposition 映射到权威 ObservationFrame；不得给 v0.5 exact fields 加键。 |
| `MultiScaleStateBelief` | v0.5 authority | 用 versioned adapter/reference binding 说明 `role_states` 对 BACKGROUND/STRUCTURE/REGIME/SETUP/TRIGGER 的解释；axes 保持 nonexclusive/unknown，且不得改写 exact carrier。 |
| `StructuralPosition` | `DRAFT` | `position_id`、`as_of`、`anchor_refs`、`zones`、`uncertainty`、`provenance`；zone 最小为 anchor/width/strength/consumption/relative_position。 |
| `MechanismSpec` | v0.5 authority | 只引用 registry mechanism ID、support/contradiction/falsifier/expiry，不增设 runtime injection。 |
| `PathSpec` / `PathEvent` | v0.5 authority | partial order、skip/repeat、horizon/capacity 保留在权威 schema；DRAFT adapter 仅负责映射。 |
| `Evidence` / `EvidenceLedgerReceipt` / `UpdateReceipt` | v0.5 authority | v0.5 exact Evidence 与既有 UpdateReceipt 不加键、不改义；独立 V2 E0 EvidenceLedgerReceipt 绑定 exact scope、完整 method ID/raw SHA、canonical UTC nondecreasing decision time、rejection class/idempotency key、typed batch、rederived effects、evidence/lifecycle identities、group/semantic-terminal winners、raw/clipped support、state digests 与 receipt hash chain。当前 canonical projection 没有 raw record/transform lineage或外部 tip/seal，只能做 supplied-prefix synthetic fail-closed 审计。未来 `DRAFT` `EvidenceAdmissionContext` 与 raw `AuthorityBundle` 必须引用 source artifact/digest、raw identity、transform version、target expiry、quality/provenance、admission result和外部不可变 ledger tip，并绑定 exact carrier/receipt digest。 |
| `PathBeliefSet` | v0.5 authority | qualitative E0 mode 或 `UNKNOWN`；无 partition proof 时不得填 normalized weights。 |
| `ScenarioDistribution` | v0.5 authority | 必须与 path belief 分离；E0 只能 qualitative/ synthetic counterfactual，禁止市场概率。 |
| `TradeThesis` | `DRAFT` | `thesis_id`、as_of、scenario refs、structural/trigger conditions、invalidation refs、abstain reasons、authority version；不是 OrderIntent。未来 immutable fields 还应包括 entry-zone refs、structural invalidation、stop-buffer version、target/expiry rules、allowed post-fill updates 与 no-risk-expansion invariant。 |
| `UtilityReceipt` | v0.5 authority | 引用 scenario digest、成本/tail/uncertainty assumptions 和 applicability；E0 不可计算可执行 EV。 |
| `PermissionEnvelope` | v0.5 authority | 当前状态固定为无新增风险；所有 action 必须持有其 digest。 |
| `ActionCandidate` | v0.5 authority | 只能作为 projection；E0 必为 `ABSTAIN`，不得生成 broker payload。 |

## 4. 模块边界与最小未来实现顺序

可以复用但不可改变含义的现有模块：

- `EventStore`：point-in-time raw/availability、append-only、seal；
- `FeaturePipeline`：同源 replay/live feature construction；
- `EpisodeMachine`：旧 research episode，不是 MSTA belief；
- `RiskEngine`/`OrderManager`：仅 operational veto/OMS boundary，不从 MSTA belief 获得绕过权限；
- `PaperBroker`：仅历史 paper simulation，不是未来 MSTA execution adapter。

本轮已在 tests 中完成无 I/O、纯函数 contract reducer 与攻击反例，结果仍为 `AWAITING_SOL_REGATE`，不构成 V5-M00 `PASS` 或 runtime implementation。只有 Sol 阶段 gate 明确允许后，才可把该设计实现为独立 production module：输入为已构造的 immutable object，输出为 validated object 或 exact fail-closed code。不得把 tests helper 直接搬进 production；应先重新定义 public API、错误载体、版本绑定、外部 scope/tip authority 和独立测试。

当前禁止：network/source adapter、文件写入 evidence、订单提交、账户读取、模型拟合、校准、history/outcome reader、backtest 或任何执行权限。

## 5. 通用不变量与 reason codes

建议所有未来 pure validator 使用稳定、精确 reason code，并拒绝开放文本作为机器决策。最小 `DRAFT` codes：

- `MSTA_E_TIME_NAIVE`
- `MSTA_E_CAUSAL_FUTURE_EVIDENCE`
- `MSTA_E_REQUIRED_INPUT_UNKNOWN`
- `MSTA_E_DEPENDENCY_GROUP_DUPLICATE`
- `MSTA_E_TARGET_SCOPE_UNDETERMINED`
- `MSTA_E_EVIDENCE_ID_REPLAY`
- `MSTA_E_EVIDENCE_ID_CONTENT_DRIFT`
- `MSTA_E_UNDERLYING_INCREMENT_ALIAS`
- `MSTA_E_LEDGER_GENESIS_INVALID`
- `MSTA_E_TRANSITION_NOT_DERIVABLE`
- `MSTA_E_EFFECT_ABSENT_FROM_BATCH`
- `MSTA_E_RECEIPT_SCOPE_OR_HASH_INVALID`
- `MSTA_E_TERMINAL_REACTIVATION`
- `MSTA_E_LIFECYCLE_PATH_AUTHORITY_INVALID`
- `MSTA_E_EXPECTED_TIP_MISMATCH`
- `MSTA_E_RECEIPT_PREFIX_REWRITE`
- `MSTA_E_PATH_UNREGISTERED`
- `MSTA_E_PARTITION_PROOF_MISSING`
- `MSTA_E_PRIMITIVE_WEIGHT_NORMALIZATION`
- `MSTA_E_PERMISSION_NO_NEW_RISK`
- `MSTA_E_AUTHORITY_STAGE_DENIED`

因果时钟必须是 timezone-aware 且 `event_at <= available_at <= decision_time`。证据必须先验证 exact schema/type/target/clock/quality，再按 target 过滤；ledger target 只能是 exact singleton path instance，无法确定或附带 alias 时不得对任何剩余行做局部更新。时间参与 identity 前统一渲染 UTC。

receipt 必须从 strict `ACTIVE/0/empty-chain` genesis 重放。`decision_time` 只保存 canonical UTC `Z` 且 chain 非递减；相同/等价时区允许，倒退在入口与 reducer 均拒绝。receipt 绑定 scope、完整 method raw SHA、rejection class、由 scope/kind/batch/time/class 生成的 idempotency key、typed batch、validated effects、evidence/lifecycle identities、before/after state、previous/self hash；reducer重新计算而不相信自报 transition。future Evidence/lifecycle 是 `RETRYABLE_AT_LATER_DECISION_TIME`，同 context no-op、较晚 decision 重推；永久或 resource rejection 不重试。空输入是 byte-identical no-op，rejection-only 不改 support。

terminal class 在同一 opportunity 内不可重新激活，但 later-arriving earlier terminal 可以修正 reason/status：lifecycle 用最后一个有效 PathEvent `event_at`，EXPIRY 必须等于 start+horizon；Evidence HARD 因 schema 无 event_at，保守用 canonical `available_at`。同一时刻先按冻结语义优先级 `HARD_FALSIFIER < EXPIRY < TERMINAL_MILESTONE`，再按稳定 method authority 决胜。current winner 使用排除任意 PathEvent ID/source digest 的 semantic terminal identity；provenance 可进 receipt 和内部 lifecycle identity set，但不能改变 current state digest。同 exact lifecycle + 同 decision context 为 byte no-op；同 ID drift 永久拒绝，不同更早 terminal 可竞争。event-time B 允许 terminal 后接纳 `effective_at < cutoff` 的 ordinary evidence，只修正 derived support且保持 terminal；`>= cutoff` 拒绝。SUPPORT/SOFT/HARD 单批、分批及 receipt 排列必须收敛。`COMPACT_REQUIRED_RECEIPT_CONTINUATION` 只能路由 `RESOURCE_CAPACITY_REQUIRED/UNKNOWN_RESOURCE`，不能生成 terminal effect。旧 receipt bytes 不回写，receipt 只是当时 decision-time view。完整 caller-provided lifecycle 仍只证明 synthetic structural derivability；没有独立 path-instance event-log tip 或外部事实权威。当前 helper 只验证 supplied prefix，V5-M00 也没有 external seal。

PermissionEnvelope 永远不能绕过现有 RiskEngine。即使未来 MSTA 产生 action projection，RiskEngine、health、risk gate、OMS protection 和 reconciliation 仍拥有最终 operational 否决权。

## 6. 报告投影与内部状态机

`WAIT`、`WATCH`、`PREPARE`、`EXECUTE`、`EXIT` 等可以作为人类报告视图，但只是 projection。它们不能替代或重命名内部 episode、order、protection、system-health、risk-gate 或 receipt 状态机；每个 view 必须能反查 versioned object/digest 与其 reason codes。

当前 E0 报告投影只能为 `WAIT / ABSTAIN / AWAITING_SOL_STAGE_GATE`。`EXECUTE` 不是当前可用状态，也不是文档中出现该词就获得的权限。

## 7. 优先级、阶段门与验收

| 优先级 | 工作 | 当前授权 |
|---|---|---|
| P0 | V5-M00 ledger transition derivability：strict genesis、canonical decision clock、retry classes/idempotency、lifecycle identity、event-time B mixed-batch convergence、semantic terminal merge、capacity resource routing 与攻击测试。 | E0 tests 已实现；`AWAITING_SOL_REGATE`，不得自判 PASS。 |
| P0 下一门 | Sol 复核本轮 theory/method/registry/synthetic/test/report/technical 一致性与 P0 反例。 | `AWAITING_SOL_REGATE`。 |
| P1 | 如获单独允许，将 pure reducer 迁为独立 module，并先冻结 raw AuthorityBundle、ObservationFrame/scope registry 与 external tip/seal contract。 | 未授权。 |
| P1 | 冻结 B4/development contract，才讨论历史 data/outcome、similarity challenger、backtest。 | 未授权。 |
| P2 | calibration、holdout、paper/live/deploy、broker/account adapter、反馈训练。 | 未授权且更后阶段。 |

本轮验收清单：

- 两份文件均声明 E0/无 outcome/awaiting gate；
- 不替换 2.1/v0.5 authority；
- 不把案例参数写为事实或默认；
- 区分 epistemic 与 operational state；
- variable-length path 不得退化成固定 `D1-D8` 序列；
- `LEADING_QUALITATIVE` 不等于 trade，且 E0 仍为 ABSTAIN；
- 动态风险管理不得放宽 stop、延长 horizon 或因 path 切换自动反手；
- 明示 test helpers 非 runtime；
- 明示 exact Evidence carrier 不足以证明 raw lineage，未来 runtime 必须另获 raw AuthorityBundle；
- 跨 receipt identity、decision clock/retry、转移可推导、full-ledger mixed winner、lifecycle semantic merge、capacity routing 与 terminal-class 单调均有 E0 反例；
- 明示 supplied-prefix/expected-tip、raw provenance和全局 opportunity scope authority仍未关闭；
- 文档包含 v1/MSTA adapter boundary、P0/P1/P2 与未授权事项；
- 不产生市场、回测、校准、paper/live/G1 mutation 或部署输出。

## 8. 已知风险

1. 当前 worktree 为脏树，且 v0.5/v6 相关文件可能尚未纳入同一提交；任何后续 authority claim 必须锁定 commit、file digest 和 worktree。
2. 本文记录了 2026-07-26 的活动 G1 只读快照，但该快照不更新治理权威、可能已经过时，也不能替代正式 G1 裁决或授权任何活动目录修改。
3. MSTA 的对象分层降低语义混写风险，但不证明可预测性、盈利性、fill quality、执行可靠性或风险许可。
4. 如果未先经 Sol gate 就把本草案写成 adapter/runtime、回测或市场采集，将违反 v0.5 的 E0 authority boundary。
5. 当前 ledger 没有 raw record/transform identity、外部不可变 tip/seal 或全局 ObservationFrame/opportunity scope registry；微调 `available_at`、替换整条合法 chain 或省略 predecessor 的初始 scope 不能被纯函数独立证明为同一现实来源、回滚或重复 opportunity。
6. HARD Evidence 只能用 `available_at` 与 PathEvent `event_at` 混合排序，这是 exact Evidence 缺少 event-time 的保守 E0 规则，不是生产市场时钟设计；runtime 前必须以新的 authority carrier 统一事件时间语义。
7. capacity overflow 当前只证明 fail-closed resource routing；没有 runtime compactor、receipt continuation storage 或资源恢复实现。
