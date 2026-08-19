# V3.2 实施、故障修复与实验前日志

状态：`COMMIT_9F5DBA4_BASELINE / RUNTIME_REPAIR_DESIGN_FROZEN / IMPLEMENTATION_NOT_STARTED / NO_TARGET_AUTHORITY / NO_TARGET_RUN / NO_OUTCOME`

> 2026-08-10 当前续接：composition guard 候选已提交为 `9f5dba41fefd3759810af305b23865998110552a`。该提交的一次性旧门回归已完成：V3.2 `785/785 PASS / 1647.290s`，全 Theory `1552/1552 PASS / 1944.495s`，零网络；由于全量套件包含 V3.2，约 59m53s 的双执行被确认是重复成本。此收据只作为旧提交事实封存，不调用 prepare/advance/finalize，不创建 qualification authority 或 target。三个新发现的 target P0 与简化方案见 [V3.2 运行时修复、简化与实验恢复计划](V3_2_RUNTIME_REPAIR_AND_SIMPLIFICATION_PLAN_2026-08-10.md)。

版本语义：正式 authority/schema 兼容字段仍为 `theory_version=3.2.1`；commit `9f5dba4` 只关闭 qualification composition 并发问题，尚未包含当前 target P0 修复。

日期：2026-08-10（单写者提交后、target P0 修复设计冻结）

需求入口：`requirements/2026-07-30-theory-paper-practice.md`

理论入口：`CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md`

系统入口：`V3_2_SYSTEM_AND_EXPERIMENT_DESIGN_2026-08-07.md`

权限边界：`PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION / executable=false`。本文的动作、风险、仓位和退出均为不可执行研究计划，不是订单、持仓、成交或收益。

---

## 1. 结论

2026-08-07 的 27 组件基线只保留为历史快照。2026-08-08 授权修订已经把可逆上下文压缩、UNKNOWN 双轨、人工公开证据、环境能力、对应 typed boundary 后审计、只读监督、恢复白名单、工作树冻结、三档支持、typed 混沌、全局 reentry 防磨损和 actual-capability 持久化完整性接入本地四层主路径；formal acceptance 当前为 28 组件。第一版已提交为 `d5478d9463961a65d7167642c0c67e6c275f6ebf`，其 exact-commit V3.2 `502/502 PASS / 984.937s`、全 Theory Paper V2 `1187/1187 PASS / 1256.535s`。随后四份真实资格分别在各自唯一 PUBLIC_SOURCE attempt 永久失败，依次暴露系统代理路由、旧 REST host、代理协议顺序和资金费时间语义缺陷；四份失败证据均保持封存，证明本地提交和测试通过不能替代当前环境的真实资格。

第五资格之后的材料化失败原子性、write-once post-commit 执行收据、WorkspaceFreeze v1.1 和每 wake 完整 Phase-A 重放最终提交为 `e0c7d3da4e0809fd21b0d241db84e0c17155d4ff`。第六资格 `v32-qualification-btcusdt-20260809t131915z` 完成正式收据、Q0–Q8/全部 support/`42 roots / 192 paths / 192 bindings` 重放和唯一 PUBLIC_SOURCE attempt；CURRENT_CODEX 只预留一次，在 Agent request/claim 前的 `CONTEXT_PACKAGE:PROPOSAL` 写入 typed failure receipt 并把 controller CAS 到 revision `4 / FAILED_CLOSED`。`14` 个 material predecessors 完整，无 `proposal_input`、mailbox request、monitor schedule、target authority/genesis/cycle/outcome。该树及 exact target/qualification pair永久封存。

只读根因量化：完整 proposal=`559,522 B`，完整 INLINE input=`562,654 B < 1 MiB`，Agent view=`187,641 B < 256 KiB`；旧 `512 KiB` proposal 子门错误触发 compaction。compaction 将 `12,709` leaves 展开为 `12,712` members、`121` shards、约 `7.79 MB`，并因 `1,807` 个 policy roots 在 selection 中重复表达而达到约 `306,980 B > 262,144 B`。随后复核发现旧实际 Presentation 又把 packet 在 request context、canonical original 和 ordered unit 中复制三次，最终达到 `1,687,318 B`，并且 qualification/target 都是先 claim、后构造超限返回。V3.2.5 最小修复取消 512/768 KiB stage 子门，只测完整 input；再由一个 owner 构造单一 Presentation，当前 pilot 固定 `INLINE_ONLY`，正文只在 request context 内出现一次。完整 checkpoint/request/claim/control/representation 在 enqueue 与 claim CAS 前共同接受既有 `1 MiB` 总门；超限即 `CONTEXT_CAPACITY_UNRESOLVED`。`SHARDED` 仅保留为未来尚未资格化的 codec/package 能力，当前 successor 不得使用。未删理论、bars、evidence、UNKNOWN/OTHER，也未提高总容量。

第六资格后的耐久边界修复已进入提交 `66197c47a1281340b4226da825da0b18d8815c3e`：mailbox request、claim、delivery/receipt、consumption/receipt 四个对象已落盘而 checkpoint CAS 未完成时，重放只补原 exact tail；V3.2-owned durable writer 增加同目录完整临时写、`fsync(file)`、不可覆盖原子发布和 `fsync(parent directory)`，但不修改 V3.1 冻结的 `domain/contracts/canonical.py` 或其使用者。CAS 后 response-loss 的 enqueue/claim/submit 分别只返回已提交的 `REQUESTED/CLAIMED/DELIVERED` exact successor，零第二写、零新时钟、零第二 Agent。delivery receipt 写入实际 Presentation digest，qualification full replay 从 CLAIMED 快照重建并核对；qualification/target 最终 Agent-facing 对象直接返回该 `<=1 MiB` envelope。hot path 固定 `INLINE_ONLY`，超限立即失败，`SHARDED` 为 future-unqualified。真实 fresh-process collector 已在第七资格中于 Phase-A 任一 authority byte 与资格 System UTC 时钟之前运行，typed receipt 经物理 binding 进入 support、manifest/runtime closure 和 full loader；机械 closure=`43 roots / 194 reachable paths / 194 bindings`。第七资格同时完成唯一 fresh PUBLIC_SOURCE，但 CURRENT_CODEX 在 claim 前耗尽 reservation 窗口，固定 monitor 未开始。

旧 V3.1 run `v31-prospective-btcusdt-20260806t183742z` 继续永久 `FAILED_CLOSED`，不重试、不补造、不推进 Cycle 2；旧 Q0–Q8 和 74 个冻结 runtime 路径保持原字节可重放。新修订不得修改这些冻结字节。

七份 qualification runs 均为永久历史证据：前四份在 PUBLIC_SOURCE 失败；第五份 `v32-qualification-btcusdt-20260809t074253z` 在旧 Agent view 容量与非终态边界失败；第六份 `v32-qualification-btcusdt-20260809t131915z` 在正式收据、Phase-A 和 PUBLIC_SOURCE 完成后于 `CONTEXT_PACKAGE:PROPOSAL` revision `4` 永久 `FAILED_CLOSED`；第七份 `v32-qualification-btcusdt-20260809t215807z` 完成 post-commit receipts、Phase-A、fresh-process、PUBLIC_SOURCE 与 proposal request 后，在 claim 前超过 reservation 起算的 `660s`，治理状态为 `EXPIRED_TERMINAL`。第七 runtime 原件保持 controller=`RUNNING/revision 3`、proposal=`REQUESTED`、no claim，不追写为失败。六个 failed pair 与一个 expired pair 共同 tombstone；正式 target authority、target genesis、target cycle 和 outcome 均不存在。当前未提交候选用最多 `64` 个内部子阶段的 bounded burst 修复本地调度，并在 Agent、READY、no-progress、probe 高层边界、异常或上限停止；全量回归、显式提交和新 exact-pair post-commit receipts 前不得创建第八资格。没有账户、paper/live、订单、凭据、资金、fill、position 或 PnL 能力。市场预测增量、概率校准、成本后收益、真实执行可靠性及跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

## 2. 已知问题、根因与最终处理

| 问题 | 根因 | V3.2 最终处理 | 证据边界 |
|---|---|---|---|
| WAIT 过度支配 | 把一般不确定性、事实失败、研究输入缺失和未来执行风险混成同一阻断 | typed UNKNOWN 分层：事实完整性只阻断依赖动作；compiler 实际确认的研究 objective inputs 缺失才归零当前正 reference-risk；权限与真实执行 MAX_LOSS 只阻断未来执行；可行 probe 存在时 WAIT 必须证明机会成本优势 | 只证明动作合同，不证明 probe 有 alpha |
| 磁区被当作机构护盘 | K 线、成交量和公开盘口不能识别挂单所有者或隐藏流动性 | `ReflexiveLiquidityZone` 固定 rejection、break/absorption、false-break/stop-run、no-effect 四路径；机构身份保持 UNKNOWN | 历史形态是反身性候选，不是机构承接事实 |
| 外在路径变成万能故事 | “主力收割”等叙事可无差别修改全部假说 | typed `ExternalPathModifier`；必须与 zone、hypothesis 和 dependency group 双向闭包；只可降风险/失效，不可增加方向支持 | 假突破、流动性真空、跨场错位可建模，不能证明真实动机 |
| 相对权重分母陷阱 | `w/sum(w)`、连续质量分数或客观“质量档”可直接制造风险 | raw envelope 固定为 `1 USDT` 非账户研究压力比较单位；只由最高主观支持档与 residual 不确定性形成总 cap，同向/对立 cluster 均取最高档而不相加，再以 `HIGH=2/LOW=1/EXTREME=0` 切分既有预算；coverage 只诊断，regime/liquidity/cost/geometry 是 typed 硬门，path modifier 仅作非膨胀 cap | 无 Agent-authoritative 连续主观风险旋钮；action-evaluation 的 `risk_reference_units` 只是 sealed 派生值的 exact echo；该 `1 USDT` 不是账户风险或订单名义；单一 LOW 最多取得一半 envelope，候选数量不能扩大总预算 |
| 合约与成本参数仍可成为魔法数字 | Agent 可自填 multiplier、fee、slippage、funding、gap 或 lot，精确公式会放大任意输入 | 正风险逐 tranche 强绑定当前 PIT 的 `ctVal/ctMult/tickSz/lotSz/minSz`；四项压力值由合约暴露×入场价×冻结研究 rate 推导，编译器重算全文；任一规格缺失只允许零风险 WAIT | 冻结 rate 只是预注册研究压力假设；真实账户费率、真实滑点和最大损失仍为 UNKNOWN，不构成实盘规模或收益证明 |
| 同源故事重复加权 | 改写语言即可把同一证据当独立胜率 | semantic fingerprint、dependency closure、cluster max 去重及全局对象上限 | 未校准支持权重不是市场概率，不进入 Brier/ECE/EV |
| 长期无动作导致模型休眠 | 单一计数可被普通市场变化或换 ID 重置；强制交易又制造财务风险 | 两只耐久时钟：`risk-plan inactivity` 只由正风险 probe/reentry 重置；`model-adaptation inactivity` 只由新鲜 PIT 绑定的实质变化重置；8 cycles 或 7200 秒触发独立复核 | 不用真实风险购买训练样本；现金机会成本须先冻结基准 |
| 重入上限与 HIGH 升档仍可被首轮/跨轮注入 | 任意累计 envelope、任意 cooldown、cluster/方向/动作改名，或同源证据升为 HIGH 可绕过防磨损 | 当前 pilot 固定每 instrument 单一 churn breaker：per-attempt reference risk `<=1`、window=`24h`、max attempts=`2`、cumulative `<=2`；首次 probe 不计，ledger 激活后任一方向最终选中、合格、正风险的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一预算；同向恢复仍规范化为 `REENTER`，真实换向保留语义但不免费；预算耗尽 cooldown 精确等于原窗口终点，终点前禁止 RESET，终点后仍需三重 reset 门。初始 HIGH/LOW→HIGH 需双 fresh mechanism-distinct evidence 和方向性反证；watchdog 固定 `8/7200s` | 这些是不可执行 research-plan 约束，不是统计独立、fill/position/PnL 证据；未来 executor 另计真实成交 |
| 假说换名/改时间戳续命 | 生命周期按可变 ID 或文案判断 | stable semantic fingerprint、revision、predecessor、absolute expiry；到期状态为 `EXPIRED`，旧计划失去行动权；续期必须新增证据并重检 regime/zone | `STALE` 只作复核原因；固定降权 50% 仅是未来比较臂 |
| 假突破止损后永久踏空 | exit 与父 thesis 被错误合并 | exit 后若父 thesis 未失效且 false-break 条件成立，只获得创建有界 `ReentryObligation` 观察对象的资格；对象不强制开仓，仍须重算证据、成本、zone、风险和全局 churn 余额；禁止回写旧 tranche 或报复性加仓 | 当前无真实持仓或成交 |
| stop 被当作保证成交 | 触发价、委托 ACK、attached protection、排队和成交状态混同 | 明确 `stop trigger != fill`；仅支持原子 attached protection 的 venue 模式可开仓并独立确认，不支持则默认禁开；fill→保护确认间隙进入 `UNPROTECTED_EXPOSURE`，冻结新增并走预授权 reduce-only close/reconciliation | 交易所级故障不能由本地理论消除；仍不保证成交；当前 runtime 只有 future hazard |
| Agent 使用陈旧/空市场上下文 | 旧 V3.1 十二轴投影可能全 UNKNOWN，完整图又约 5.08 MB | 完整 bundle/图/PIT 原件→typed members→可逆编码→强制 roots/闭包证明→当前 pilot 单一 INLINE exact delivery→双重 replay | INLINE 本地链为候选；真实 Codex 容量仍待 qualification，SHARDED 禁用 |
| 大对象拖垮新窗口 | 没有资源预算，可能复制多 MB 图或依赖聊天摘要 | 2026-08-07 的 256 KiB/512 KiB/768 KiB/1 MiB 等上限仅为历史快照；最终由 Environment profile、实验合同和真实 Codex 资格冻结，并在拒绝前执行可逆传输压缩 | 无 top-k、无 lossy summary、无聊天补齐；完整强制 roots 仍超限才 `CONTEXT_CAPACITY_UNRESOLVED` |
| 压缩仍可任意删证据 | 原件存在不证明调用方给出的 members/required IDs 完整 | schema-specific source→member coverage、StageRequiredRootPolicy、closure/count/digest 重算；当前 pilot 核对唯一 INLINE packet，未来资格才可核对 shard receipt | 已在本地候选链失败关闭遗漏/任意 roots；真实容量待资格 |
| UNKNOWN 主观附件可伪造依据 | 摘要只验格式、未解析 PIT/mechanism registry，assessment chronology 未锁 | ObjectiveUnknown 与 SubjectiveAssessment 隔离；引用唯一解析、available-at、typed opposing hypothesis、expiry、零 coverage/事实/硬门贡献 | 伪引用与倒置时间已进入失败关闭回归 |
| 人工公开数据回填历史 | 官方发布时间、人工接收时间与旧 PIT 容易混淆 | DataGapEscalation + `MANUAL_PUBLIC_EVIDENCE` 新 revision；实际 receive time 作为 available-at，只进未来 cycle | Domain/Application/admission/store/acceptance 本地接线完成；人工数据仍未产生 |
| 审计或监督污染 sealed run | narrative 参与它所描述的 typed boundary 会循环；监督端若有 market/formal-write 能力会越权 | 各自 typed boundary 后确定性 narrative/index，acceptance narrative 仅在 acceptance 后；独立 read-only projection/alert store；controller 只匹配冻结 recovery action ID | production composition 与 capability-denial 本地合同已接线；实际监督需 target run |
| 环境与 Git 边界未冻结 | dirty/untracked runtime 与 HEAD、测试、authority 可指向不同字节 | EnvironmentCapabilityProfile + WorkspaceFreezeReceipt；exact commit/tree/clean qualification worktree/post-commit replay | 当前工作树尚未提交，authority 门关闭 |
| PIT freshness 可洗白 | 只校验引用存在，不校验首次可得性与前序 cutoff | 每周期强制 `verified_pit_evidence_availability_registry`；Cycle 2+ 同时重放当前和前一 registry；新增证据须晚于前序 state/PIT cutoff 且不晚于当前 as-of | availability 与证据语义/物理摘要绑定 |
| authority projection 自授权 | Application 最小投影可用自摘要冒充完整 governing authority | 同时绑定 `active_authority_projection_digest` 与独立 `governing_authority_digest + physical binding` | 旧 V3.1 loader PASS 不生成 V3.2 authority |
| baseline 可在 outcome 后重建 | 决策周期只封存 selected plan，没有事前封存对照 | outcome 前必须构造并接受六臂 `shadow_decision_bundle`；每臂含 frozen policy 和 derivation receipt，结果字段必须不存在 | V3.1/no-RSI 无同 PIT 可复算输入时保持 `UNKNOWN_NOT_COMPUTED` |
| terminal mark 被冒充完整路径 | 当前 adapter 只有绝对终点 mark | 当前只评价终点方向一致性与 coverage；MFE/MAE、路径、机会捕获、fill、position、PnL、概率和 EV 均 UNKNOWN/禁止 | 只有未来事前冻结并完整采集 horizon 内路径后才可增加路径指标 |
| 接纳与 Store 恢复旁路 | Store 曾允许无完整 acceptance；跨 owner locator 又被误当内容身份 | 28 个正式组件完整重放；Store 两侧 locator 各自合法并实际读回，同一对象必须 schema/semantic/physical identity 相同；缺件、漂移或不可重建全部 fail closed | 不允许 `acceptance=None` 降级接受 |
| research/monitor 多 owner | analysis 与 outcome 可并行或一轮推进两边界 | 单 `TickSupervisor`、write-once permit、CAS checkpoint；一次 wake 只允许一个 `ANALYSIS_TICK` 或 `OUTCOME_TICK` | 无第二 automation、无同轮重试 |
| 四层反向依赖 | Domain/Application 曾直接依赖外层实现 | 公开证据、source store、outcome、shadow decision/evaluation 全部经 Application port 注入 | V3.2 Domain→Application/Infrastructure/Presentation=0，Application→Infrastructure=0 |

### 2.1 2026-08-08 客观质量、HIGH 门、regime 与全局 churn 修订

- 风险算术删除 coverage、regime-liquidity、geometry 的 0/50/100 客观缩放。有效 envelope 只取最高主观支持上限与 residual 不确定性的最小值，再受 typed hard gate 和 path modifier 非膨胀 cap 约束。
- `risk_availability_assessment` 由 sealed dynamic state 确定性重建：hypothesis evidence-chain coverage 仅为诊断；source-admission coverage 不在该 state/compiler 链中时固定为 `UNKNOWN_NOT_IN_DYNAMIC_STATE`。Agent 传入同名质量对象会被 schema 拒绝，verifier 重建全文。
- 初始 `HIGH` 与 `LOW→HIGH` 先在 domain 校验双引用和显式反证，再由 continuity 使用 current-PIT first-availability 与完整 graph dependency closure 校验两条 fresh、`mechanism-distinct evidence`。真实 OKX closure 的 `605/605` 记录共同含有 `VENUE:OKX`；若要求完整 closure 全不相交，会令 `HIGH` 结构性不可达。修复没有删除 provenance closure，而是只在此配对门忽略共同 `VENUE/PROJECTION`，其余物质依赖仍须不相交，并强制不同 `REQUEST` 与不同方向性 `OBSERVABLE_FAMILY`。
- `TICKER/MARK/CANDLES` 已统一映射为 `PRICE_ACTION`：candle+candle、ticker+candle 或 mark+candle 不能伪装双机制；`PRICE_ACTION` 只有与 `TRADE_FLOW/POSITIONING/FUNDING_CROWDING/ORDERBOOK_LIQUIDITY` 等实质观测机制不同的证据配对才可能过门。`PROVIDER_METADATA/CONTRACT_SPEC` 不得充当方向支持或反证。该约束不声称统计独立、因果识别或预测有效。
- 非方向状态进入方向状态需要同样的双机制差异 fresh refs，或连续两根确认闭合且同向的 15m bar 机械证据；进入非方向状态可使用一条 fresh hard evidence。`TRANSITION` 本身仍是零方向风险状态。
- 重入预算以每 instrument 单一全局 churn breaker 管理；首次 `OPEN_PROBE` 不计，ledger 激活后任一方向最终选中、合格、正风险的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一预算；同向恢复仍规范化为 `REENTER`，真实换向保留语义但不免费，跨方向/cluster/regime/hypothesis ID 也不能另开预算。预算耗尽 cooldown 精确等于原 24h 窗口终点，窗口内禁止 RESET，到期后仍须三重 reset 门。
- 验收必须覆盖：Agent 伪造客观 quality/source coverage 被拒绝；单一/同源/同 `PRICE_ACTION` family 证据不能创建或升级 HIGH；共享 `VENUE/PROJECTION` 但 REQUEST 与方向观测 family 不同的合格证据可以通过；metadata/spec 支持或反证被拒绝；反证缺失被拒绝；非方向→方向的单证据被拒绝而双机制差异/两根闭合 bar 通过；TRANSITION 风险为零；冷却端点过短/过长均拒绝；跨 cluster/regime/ID 和动作别名不能绕过全局 churn。所有检查只证明本地不可执行合同，不证明统计独立、预测、收益或执行可靠性；未来 execution capsule 仍只是未授权设计，不能写成已实现实盘逃生。

## 3. 2026-08-07 信息、数据、图、关联与假说历史快照

本节数字来自 2026-08-07 的本地工作树和既有样本，只用于说明修订前基线；2026-08-08 新实现、最终 commit 和 fresh qualification 尚未完成，不能把这些数字当作当前授权能力。

### 3.1 十二轴来源与图投影

当前公开 OKX collector 对十二轴的诚实覆盖为：原生直接轴 `4`、代理轴 `1`、已物化派生轴 `0`、UNKNOWN 轴 `7`。框架已为全部十二轴保留 `DIRECT / PROXY / DERIVED / UNKNOWN` 来源 assessment，以及 status、admission、observed/available 时间、raw binding、reason、missingness、claim ceiling、dependency group 和图投影；当前 axis row 并没有独立的 `quality/coverage` 数值，也不得合成后进入风险缩放。系统没有把 OI level 冒充 leverage change，也没有把单次 order-book snapshot 冒充 liquidity resilience。

真实公开集成样本的本地重放曾得到：PIT availability `606/606`、证据闭包记录 `605`、图依赖成员 `139`。这些数字证明当前样本的绑定完整性，不代表十二轴原生覆盖完整或市场语义正确。

### 3.2 关联预注册

候选全集在观察结果前冻结为 `144` 条；window、lag、最低样本、缺失、效应量、不确定区间和多重检验规则均进入版本化合同。相关性只用于描述和假说发现，不能直接升级为因果、校准概率或动作信号。

### 3.3 假说与概率云

系统原生区分现状、归因、预测和行为四类假说；方向候选保持 LONG/SHORT 竞争及 OTHER/UNKNOWN，但不伪造最低正权重或强制开仓。2026-08-07 的 `subjective_plausibility_weight=0..100` 已在 2026-08-08 第二次修订中判定为伪精确风险输入并废止；这里只保留为历史快照，不得进入最终 runtime、兼容层或实验材料。

## 4. Agent、shadow 与正式周期链

下列链条由 2026-08-07 基线演进而来。2026-08-08 修订已在 source replay 后加入 proposal/selection 可逆 compaction、强制 roots、UNKNOWN/DataGap/manual/environment/recovery registries；每类 audit narrative 晚于其对应 typed boundary，acceptance 后另有 acceptance audit completion。当前本地 formal acceptance 为 28 组件；final regression、commit 和 qualification 前仍不能生成 authority。

正式 analysis path 固定为：

```text
Supervisor permit
→ raw/public source admission
→ full bundle + graph + PIT availability replay
→ bounded current-market Agent view
→ proposal delivery/consumption (single attempt)
→ deterministic compile and sealed action evaluation
→ post-seal selection delivery/consumption (single attempt)
→ dynamic state/action continuity
→ commit envelope
→ six-arm shadow_decision_bundle
→ 28-component acceptance
→ outcome schedules
→ Supervisor completion
```

六臂为：

1. `V32_SELECTED_PLAN`
2. `V31_CONSERVATIVE_WAIT_BIASED_REFERENCE`
3. `WAIT_ONLY`
4. `SIMPLE_15M_TREND`
5. `NO_RSI_REFERENCE`
6. `ALWAYS_LONG_PUBLIC_MARK_REFERENCE`

当前 terminal-only shadow outcome 使用 semantic/physical exact binding、write-once/CAS、崩溃恢复和幂等重放；coverage 缺失保持 UNKNOWN。它不生成账户、撮合、收益或执行结论。

## 5. 2026-08-07 已执行验证历史快照

以下结果使用项目 Python `/opt/homebrew/bin/python3.12`，只绑定 2026-08-07 当时的物理工作树：

- V3.2 全范围：`306/306 PASS`；
- Theory Paper V2 全范围（含 V3.1/V3.1.1/V3.2）：`991/991 PASS`；
- 旧 V3.1 active authorization chain 只读重放：authority digest=`e11ece4ce46aba8902fbe93373ed24941eab659e6177be1f07f53eac1d7a32fc`、Q0–Q8 全部验证、`74` 个 implementation binding 未漂移；
- JSON 读取检查：`317` 份通过；
- `compileall`、V3.2 零白名单四层 AST 检查及 `git diff --check`：通过；
- 自动化状态：`automation-2/3/4`、`btc-agent`、`flap-live`、`g1`、`v1-3/v1-4`、`v3-1-btc` 全部为 `PAUSED`；没有创建第二个监测任务。

这些数字早于 2026-08-08 新增合同和当前未提交改动，不能作为当前 `HEAD`、最终 commit、可逆 compaction、UNKNOWN 双轨、manual evidence、environment、audit 或 read-only supervisor 的 PASS。最终数字必须由主线程在新增 P0 修复、production composition、formal acceptance、authority/full-loader 接线完成后，从 exact commit 的 clean qualification worktree 重新运行并更新；更新前当前回归状态为 `PENDING_FINAL_REVISION_REGRESSION`。

2026-08-07 全量回归曾捕获并关闭两个当时的最后缺口：旧 semantic compiler 测试夹具引用了不同 hypothesis/cluster 谱系；Store recovery 错误要求跨 owner locator 字符串相同。前者改为同一状态下本身合法但材料不同的反例；后者仅取消 locator 文本等同，保留两侧独立物理重放和内容身份完全一致。该历史结论不表示 2026-08-08 新增 P0 已关闭。

## 6. 仍为 UNKNOWN 或不在当前权限内

- 2026-08-08 revision 的 source→member 无损覆盖、强制 roots、shard mechanics、UNKNOWN registry 解析、DataGap/manual admission、Environment profile、typed-boundary 后 audit、read-only supervision 与 WorkspaceFreezeReceipt 已形成本地 production/acceptance/authority-builder 闭环；但当前 pilot 只允许 INLINE，shard transport 尚未资格化，整个路径也尚未由 fresh qualification 证明当前环境实际可用；
- compaction/UNKNOWN 的已复现 P0 已被失败关闭：原件少投影、任意 required IDs、独立 UNKNOWN shard 遗漏、不存在 PIT 摘要及倒置 chronology 均不能通过；
- 十二轴原生来源仍是 `4 direct / 1 proxy / 0 materialized derived / 7 unknown`，不能宣称“十二轴数据完备”；
- fresh 公开来源、当前 Codex 耐久交付和 fixed outcome monitor 尚未针对最终 V3.2 摘要进行资格采集；
- 市场预测增量、校准、成本后收益、尾部表现及跨 regime 泛化均为 `UNKNOWN_NOT_EVALUATED`；
- API/网络/交易所执行可靠性只完成 hazard 建模，没有真实订单资格或证据；
- portfolio/reentry 仅为跨周期条件计划和 shadow 标签，不是账户真值、成交或资金曲线；
- 16-cycle/48-schedule 只允许称为流程与短窗判别 pilot，不能证明盈利或生产就绪。

## 7. 2026-08-07 清理历史与当前保留边界

2026-08-07 曾只清理 `trade_system/theory_paper_v2` 与 `tests` 内由当轮测试生成、可自动重建的缓存：`30` 个 `__pycache__`、`471` 个 `.pyc`，约 `12 MB`，当时复核余量为 `0`。该数字不是当前工作树保证。永久保留：旧失败 run、qualification/authority 证据、用户副本文档、旧 74 路径、全部版本化 V3.1/V3.1.1/V3.2 实现及现有未提交改动。当前修订不得执行 `git clean`、删除历史实验或改写冻结 automation/run。

## 8. 2026-08-08 历史实验启动门

用户已在 2026-08-08 批准 V3.2 唯一 `BTC-USDT-SWAP / public-data-only / local / non-executable` 实验范围，并授权当轮修订；这不等于当时尚未存在的最终 commit 已经通过资格。在该历史边界，已知 P0 的本地实现已闭合，剩余 prequalification 顺序为：

1. 完成当前字节的 V3.2 全量回归、全 Theory Paper V2、旧 Q0–Q8/74 路径、格式/编译/分层及新增对抗测试；
2. 盘点 branch/HEAD/status/untracked/sensitive/history，按明确清单 staging，禁止 `git add .`，创建 exact commit；
3. 从 exact commit 重放同一验收并生成 WorkspaceFreezeReceipt；
4. 将最终 theory/contract/commit packet 的 exact SHA 与用户批准证据绑定；若最终语义超出已批准修订范围，必须重新请求批准。

批准记录的标准陈述为：

`我批准，并授权 V3.2 唯一 BTC-USDT-SWAP 公开数据、local、non-executable 前瞻实验`

只有上述四项完成后，才允许依次创建 V3.2 qualification authority、fresh source/current-Codex/fixed-monitor 资格证据、qualification retirement、target authority/genesis 和唯一 16-cycle/48-schedule pilot。任一资格失败均保留原始证据并 fail closed，不得用旧 V3.1 结果替代。**该段当时状态**为 `LOCAL_IMPLEMENTATION_CLOSED / FINAL_REGRESSION_AND_EXACT_COMMIT_PENDING / AUTHORITY_FORBIDDEN`；当前状态以文首和第 10.25–10.26 节为准。

## 9. 2026-08-08 新增对象归属与当时接线状态

| 类别 | 新增对象 | 当前状态 |
|---|---|---|
| experiment contract + authority/runtime manifest | `ContextCompactionPolicy`、`StageRequiredRootPolicy`、`UnknownSubjectivePolicy`、`DataGapManualEvidencePolicy`、`EnvironmentCapabilityProfile`、`ReadOnlySupervisorPolicy`、`AutoRecoveryWhitelist`、`WorkspaceFreezeReceipt`、`CycleAuditGenerationPolicy` | **本地接线完成，待 exact-commit post-commit replay 与 qualification** |
| formal cycle acceptance closure | proposal/selection compaction manifest、required-root plan、replay receipt；当前 pilot 的 transport shard set 必须为空；ObjectiveUnknown/SubjectiveAssessment/DataGap/ManualAdmission registries；EnvironmentConformanceReceipt；RecoveryTraceRegistry | **28 组件本地接线完成，待最终全量回归与资格；SHARDED 未资格化** |
| sealed-boundary 派生链 | qualification/analysis/acceptance/outcome/recovery `CycleAuditNarrative`、章节 index；acceptance 专属 `AuditCompletionReceipt` | **production owner 已接线；真实边界记录待 qualification/target 生成** |
| 独立非授权观察链 | `ReadOnlySupervisorProjection / SupervisorAlert` | **只读 projection 与独立 append-only alert store 已接线；无 formal-write/market/Agent capability** |
| 人工可读派生视图 | DataGap 操作说明、Environment 说明报告 | **确定性派生合同已接线；当前无人工证据实例，不能替代 typed 原件或资格证据** |

### 9.1 same-run 自动恢复白名单

正式合同只能列入以下八类：已有 exact intent/bytes 的 write-once/CAS 尾提交；已有 raw+batch intent 且无语义失败时用同一 parser 补尾；完整 Agent delivery/consumption 后完成固定 compiler/commit tail；accepted state 后从 sealed commit 补 exact schedule；child store 提交后补 Supervisor completion；唯一 predecessor/successor 的 current pointer/index 重建；对应 typed boundary 后用固定生成器重建该边界的 audit narrative/index（acceptance narrative 只能在 acceptance 后）；Agent 前按冻结 manifest 重建摘要和字节完全相同的 compaction artifact。

网络重试/换源、人工补数、改变 parser/环境/压缩算法/required roots、第二次 Agent、改变 theory/risk/evaluation/clock、修补 accepted/outcome 语义或读取未到期 outcome 均不是 recovery。监督 Agent 只能报告，不能直接执行恢复、调用市场、读取未来结果或写 formal store。

### 9.2 可逆压缩与 UNKNOWN/manual 的完成判据

- 原件到 typed members 必须由 schema-specific extractor 完整投影并可 round-trip；required roots 从合同机械生成，包含全部 UNKNOWN/冲突/反证/falsifier/hazard/对立候选及完整 closure，无任意 top-k；
- `ObjectiveUnknown` 永远保持 null/UNKNOWN；有依据主观 assessment 的引用必须在 PIT/mechanism registry 解析、时间合法、绑定相反假说和 expiry，并对客观值、coverage 和硬风险门贡献为零；
- `MANUAL_PUBLIC_EVIDENCE.available_at` 使用实际系统接收时间，只能形成未来 cycle 新 revision，永不回填旧 cycle/outcome/failure；
- `EnvironmentCapabilityProfile` 只允许 adapter/port 本地化，缺 REQUIRED 能力资格失败，不得降低理论、评价、数据时点、候选、样本或权限。

## 10. 2026-08-08 第二次问题审查与修复记录

### 10.1 判定

1. **0–100 主观权重：P0 成立且已关闭。** 精确公式不能补偿输入不可重复性；主观 schema 只允许 `EXTREME_UNCERTAINTY/LOW/HIGH`，旧连续主观字段和兼容别名均须拒绝。对 Agent 与审计界面只暴露 `off/probe/normal` 离散语义；action-evaluation 仍有连续 `risk_reference_units`，但它只能逐项回传 sealed plan 的确定性派生值，compiler 会拒绝任意漂移，因此不是主观分数、概率或可输入仓位。
2. **运行时过度计算：P0 成立并已完成局部结构修复。** 历史三组链路 `26` 项耗时 `504.151s`；后续长测超过 `5m` 仍未完成，拆分观察为 `setUpClass≈216s`、receipt reconstruction body≈`32s`，该测试体触发 `canonical_bytes=59,018`、`normalize=28,822,997`。根因定位为同一不可变对象被 lifecycle/acceptance 级联重复 canonicalize/normalize，不是完整验证、closure 或 physical replay 应被删除。现以 request/receipt-scoped full-canonical-content memo 消除同一作用域内重复工作，并保留篡改失效和最终完整重放；新计时见 10.5。15 分钟端到端正式资格仍未完成。
3. **成对假说遗漏混沌：部分成立。** 旧 Domain 已有 RANGE/VOLATILITY/NEUTRAL/OTHER/UNKNOWN，但缺少 typed `CHOPPY/VOLATILITY_WITHOUT_DIRECTION` 及“当前方向风险为零”的动作硬约束，现纳入 P0。
4. **reentry 高频磨损：P0 成立。** 旧 `ReentryObligation` 只有新 tranche/新预算要求，局部 failure-cluster ledger 仍可被 cluster/regime/动作改名绕过。该阶段提出的“只让同方向恢复共享上限”后来又被反向换向绕过，已由全方向规则 superseded：每 instrument 只有一套 `ReentryBudgetState`；ledger 激活后任一方向最终选中、合格且正风险的 `OPEN_PROBE/REVERSE/REENTER` 都共享两次/累计上限，同向恢复规范化为 `REENTER`，真实反向保留动作语义但不免费，并防方向、ID、文字、expiry、action alias 和窗口内 reset 洗白。
5. **物理失败后的老仓位逃生：未来执行 P0，当前 pilot 不接线。** 当前权限没有账户、仓位或订单，也没有经测量的延迟上限；hazard 固定 `future_latency_bound_ms=null / UNKNOWN_NOT_QUALIFIED`，`EmergencyExecutionCapsule=NOT_IMPLEMENTED_NOT_QUALIFIED`。当前 read-only recovery observer 明确不是 execution risk supervisor。未来 capsule 仅允许 venue 原子 attached protection 与入场同请求并独立确认；不支持则默认禁开，不能假设零持仓 pre-ACK reduce-only。fill→保护确认间隙进入 `UNPROTECTED_EXPOSURE`，冻结新风险并走预授权 reduce-only close/reconciliation；market fallback 仅可由另行授权开启。venue 全不可用时保留未解决暴露、告警并人工升级，不能承诺保证成交价或清仓。

### 10.2 明确拒绝的捷径

- 不删除依赖身份与语义去重，只删除每阶段重复求闭包；否则同证据多故事会再次放大风险。
- 不把“上下挂单哪边先破做哪边”变成当前真实双向订单；本轮只能保存 conditional zero-current-risk 计划。
- 不把 `ReentryObligation` 变成自动重开，也不把连续两次止损简单按日历午夜无条件重置；reset 还需独立新证据和 regime 转换。
- 不在不可执行实验中加入真实“核按钮”，不把发送请求、ACK 或 stop touched 当作平仓。

### 10.3 实验前新增验收门

- 旧 0–100 字段在 theory/domain/compiler/action/runtime/material/tests 中检索为零，历史说明文档除外；
- 稳定证据只允许相邻档位迁移，档位变化引用当前 PIT update refs；
- CHOPPY/方向无关波动下所有当前 directional candidates 为 blocked/conditional、reference risk 为零、不得生成 tranche；任一非空 zone ref 必须逐项解析为 sealed `BREAKOUT_BOUNDARY`；
- 同 instrument 第三次同方向风险恢复、以 `OPEN_PROBE/REVERSE` 伪装 reentry、跨 cluster/regime/ID 清零、原窗口内 reset、累计风险超限全部失败关闭；
- 缓存命中不跳过物理身份检查，文件变化、进程重启和版本漂移触发全量重放；
- 冻结环境端到端周期计时满足 15 分钟边界并保留 outcome 宽限，未达标则 NO-GO；
- 最终提交、clean-worktree 回归和新 qualification 完成前，不采集 fresh 正式来源、不创建 target genesis、不启动实验。

### 10.4 Current Codex 实际资格时限与缓存未知项

- current Codex 资格的 `120s` 是服务目标（SLO），不是成功判定的伪造硬上限；两条 actual-capability seal/run 路径均已加入总耗时 `>660s` 的确定性 fail-closed 门，实际资格 receipt 必须记录测得耗时。
- 进程内相同封存材料的缓存可减少同一进程重复重放，但 fresh process、跨唤醒是否仍有收益尚未验证，继续标记 `UNKNOWN_NOT_QUALIFIED`。不得把本进程缓存命中外推为下一唤醒的性能证据；fresh qualification 必须实测并记录。

### 10.5 2026-08-08 重复验证性能修复与复测

- **实现**：receipt reconstruction 的 memo 只在单个 request/receipt replay scope 内存在。key 与 verifier 使用同一份递归精确快照，只接受内建 `dict/list/str/bool/int/None`；custom `Mapping` 直接绕过缓存。owner 同时绑定当前 thread 对象和 asyncio task 对象，异步子任务、兄弟任务或其他线程不能继承可复用结果；scope 退出先清空结果再 reset，绝不跨调用、线程、task 或进程。失败不缓存，也不接受 Agent 提供的 digest 作为缓存真值。context compaction 的 growing shard candidate 改为精确增量 size 计算，但最终 shard 仍完整 build、self-digest 并按实际 UTF-8 bytes 复核。
- **对抗边界**：覆盖 key A/verify B 的 TOCTOU、custom Mapping 读值翻转、async child 继承、兄弟 owner、同 digest 内容篡改、重签 binding 篡改、失败后再次验证、scope 退出、Unicode/escaping、limit 与 limit-1；3000 个随机 shard 与完整 canonical build 精确一致。加速没有取消 schema、semantic、physical 或 actual-byte 检查。
- **聚焦结果**：affected core 五模块在严格 owner/snapshot 修正后 `73/73 PASS / 154.221s`；原慢测 `1/1 PASS / 44.255s`；独立 TOCTOU/custom-Mapping/thread-task/shard 复核 `4/4 PASS / 42.327s`。此前分模块计时 `cycle_acceptance 15/15 / 74.407s`、`agent_lifecycle 21/21 / 26.333s`、`semantic_compiler 19/19 / 51.299s`、`context_compaction 10/10 / 0.638s` 仅作定位证据；最终全量数字以本日志后续 exact-worktree/exact-commit 回归为准。
- **局限**：这些是当前本机、当前进程的 deterministic regression/benchmark，不是 fresh process、跨唤醒或 production end-to-end 资格；未覆盖真实 Codex delivery、公开网络抖动、最早 outcome 宽限、市场预测、收益或实盘执行。相关能力继续 `UNKNOWN_NOT_QUALIFIED/UNKNOWN_NOT_EVALUATED`。

### 10.6 actual-capability 分层与持久化完整性修复

- 首次全量回归发现 Application 直接依赖 Infrastructure。已拆分为 Application-owned capability/evidence-store Protocol、Domain 纯 attempt-progress verifier 与 Infrastructure 固定 store/replay 实现；公开 production composition 仍只接收 run IDs 或 Agent payload，不允许注入 registry、adapter、路径或时钟。
- 第一轮独立复核发现：adapter 返回的短缺 binding 可在 progress 之后、checkpoint 构造之前逃逸，未耐久进入失败终态。修复为 exact 五字段 binding、resume token/time 成对、`COMPLETE` 清空 resume，并把 post-progress checkpoint build/append 纳入同一永久失败关闭边界。
- 第二轮独立复核发现：字段完整但路径不存在、schema/digest field/physical identity 不成立的 binding 仍可凭匹配 semantic digest 推进 capability。最终修复要求 controller 在 `ATTEMPT_COMPLETED` 前调用固定 EvidenceStore 的 `load_binding(..., verifier=verify_evidence_root)` 物理重开，核对规范路径、schema、digest field、语义摘要、物理 SHA-256、canonical bytes、完整 durable root 与 adapter root 精确相等，并要求路径等于当前 capability 的固定 `root_ref`。
- 任一异常只追加一次永久 `FAILED_CLOSED`；后续 wake 返回 terminal，不再次调用 adapter，也不推进下一 capability。独立复核确认 application 22 个 V3.2 根、48 个递归可达本地模块没有 Infrastructure/Presentation 反向依赖；完整形状无效 binding 场景中 adapter 调用精确为 1，下一 capability 保持 `READY`。最新 controller/layer/production-closure 聚焦回归 `15/15 PASS / 6.665s`，独立复核 `5/5 PASS / 2.894s`。
- 同次全量回归还暴露一个只属于测试夹具的 chronology 错误：夹具曾以三条任意排序证据宣称 `HIGH`。修复将其降为 `LOW`，没有放宽 production 的 mechanism-distinct evidence 门；formal chronology 与 state/graph 聚焦复核 `39/39 PASS`。

### 10.17 OpenAPI 身份、Phase B 恢复与 Target Agent 入口终审

- 活动 V3.2 公开来源固定为 `https://openapi.okx.com` 与 `V32_SYSTEM_PUBLIC_HTTPS_OPENAPI_NON_CREDENTIAL_NO_REDIRECT_V2`；raw bundle/durable replay 升为 `1.3.0`，逐组件 capture/no-response/transport failure 升为 `1.1.0`，outcome adapter identity 为 `V32_OKX_PUBLIC_MARK_RAW_CAPTURE_OPENAPI_V2`。活动 builder、route、bundle transport 和 outcome adapter 均不接受 `www.okx.com`，也不存在同 attempt fallback。旧 V1/www 只可由两份永久失败资格的 exact run/target 与 sealed semantic digest 历史重放；换 ID、自签或新资格一律拒绝。Q6 gate 现显式冻结 route 间接使用的 `v32_public_evidence_port.py`，不再只依赖 Q2/全局 closure 的隐式覆盖。独立只读复核的 route/source/replay/outcome/Phase-B 联合回归为 `97/97 PASS / 261.174s`，当前差异与 V31 的 74 个冻结 implementation bindings 交集为零。
- Phase B 在 retirement 前先写 `target/finalization-intent.json`，只冻结 target/qualification identity、两份资格 binding、五个 Phase-B 时刻、retirement binding 与无网络恢复政策。顺序固定为 intent → retirement → target tail → current pointer；intent-only、retirement 后、partial tail、pointer 已写未返回和 complete 重入都复用同一时刻与摘要，不再次调用网络或 Agent。retirement 存在而 intent 缺失时，在创建新时钟前以 `FINALIZATION_INTENT_MISSING` 失败关闭。真实 write-once 中断夹具的 lifecycle `14/14`、full loader `20/20`、materializer `6/6` 与 no-new-clock composition `1/1` 通过。
- Target Agent 正式 API 只暴露 wake、claim、submit 三个固定入口，三者先完整重放 current authority/genesis，再共享同一 per-run 跨线程/跨进程 guard。Application 唯一计算 active permit deadline：`min(decision+660s, earliest outcome due-240s)`。当前候选在新 claim/submit 中各读取两次 System UTC：入口时冻结边界，紧邻 CAS 前再次拒绝到期或回拨；orphan exact-tail 恢复复用原对象时间，不取新时钟。全部 permit、anchor、owning binding 与 Presentation 容量/摘要校验都在单次 concrete-store CAS 前完成，CAS 成功后直接返回，不再取第三时钟、不再外部重读，也不伪造 `PERSISTED_POSTCHECK` quarantine。若进程丢失 CAS 成功响应，只能由下一 guarded wake 按首次不可变对象和同一 predecessor 完成或重放 exact tail，不能回滚、换 payload 或产生第二次 Agent 尝试。
- 仅匹配 run/cycle/decision time 仍可接受同周期陈旧包。最终入口还从 `LocalV32DynamicStore` 重放 OPEN cycle 的 exact predecessor supervisor checkpoint、active permit、对应 proposal/selection packet 和 input，并要求 mailbox request/context 与 owning 五字段物理 binding 逐字一致；同周期旧 decision、非 owning binding、缺 role 或材料漂移在 Agent 内容交付前拒绝。该历史三时刻实现的 deadline、回拨、stale packet、owning binding、真实 Supervisor+Outcome+Mailbox+Dynamic 联合路径 focused `16/16 PASS / 24.588s`，相邻回归 `48/48 PASS / 66.661s`；其三时钟语义已由上一条当前候选替代，测试数字只保留历史。本地不可执行边界证据仍不能替代全量、exact commit、fresh source、当前 Codex 和 fixed monitor 资格。

### 10.7 当前字节全量回归

- 项目 Python：`/opt/homebrew/bin/python3.12`；命令范围为全部 `test_theory_paper_v2_v32_*.py`。
- 初轮结果：`502/502 PASS / 982.034s`，real=`982.43s`、user=`961.49s`、sys=`17.36s`。
- 完成全 Theory Paper V2 检查并归一最终文档后，提交候选在写入本条结果前再次得到 `502/502 PASS / 975.434s`，real=`975.80s`、user=`956.52s`、sys=`16.69s`。本条只追加测试收据文字，不改变运行逻辑；exact commit 仍须 post-commit 全量重放。
- 该轮覆盖 chronology 与 layer-dependency 修复、两类无效 capability binding、三档支持、typed regime、全局 reentry、缓存对抗、qualification/controller/materializer、28 组件 acceptance、outcome/supervisor/audit/recovery 和 production-root closure。
- 全 Theory Paper V2 同一提交前工作树结果：`1187/1187 PASS / 1258.374s`，real=`1258.85s`、user=`1226.99s`、sys=`28.15s`。
- 旧 V3.1 完整 loader 的 Q0–Q8/74 路径只读重放 `1/1 PASS`；compileall、严格 JSON、Markdown 围栏、分层、生产闭包、敏感模式与变更格式检查均通过。本文最后的措辞归一后仍须重跑最终字节检查。
- 这些结果只证明提交前本地合同未在对应套件中失败。exact commit 与 post-commit replay 仍须随后完成；fresh source、当前 Codex、固定 monitor 和 15 分钟端到端能力仍未资格化。

### 10.8 最终语义复核新增修正（第二提交候选）

- 独立复核发现 Agent action evaluation 虽已删除连续 0–100 主观输入，仍保留 `residual_uncertainty_quality=BLOCKED/DEGRADED/QUALIFIED`，并以 `0/50/100` 映射风险。这不是任意数字输入，但仍是会把主观判断伪装为客观质量的别名。当前候选已改为与假说同构的 `residual_uncertainty_tier=EXTREME_UNCERTAINTY/LOW/HIGH`；sealed plan 使用该档位的确定性补集形成 residual cap，semantic compiler 同时校验档位和补集，旧字段、旧常量和旧 policy 字符串在生产树检索为零。
- `CHOPPY/VOLATILITY_WITHOUT_DIRECTION` 原先只有枚举与零方向风险结果，没有机器可验证的分类输入。当前候选增加 `regime_feature_assessments`：前者要求低方向持续、高反转频率、高执行换手压力；后者要求低方向持续、高实现波动、方向失衡为平衡。每项必须引用当前 PIT 且图闭包属于允许 observable family；目标状态至少两个 refs/两个 families，转入时全部 feature refs 属于 fresh transition evidence。单一无关引用、错可观测族、缺当前 PIT 或缺组合均失败关闭。
- **本条记录的是当时累计 envelope=`1` 的历史修复，已被 10.30 的可构造 `per-attempt<=1 / max-attempts=2 / cumulative<=2` 取代。** 当时 reentry 治理已先统一为：首次 `OPEN_PROBE` 不计；ledger 激活后，任一方向最终选中、`ELIGIBLE` 且 reference risk 大于零的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一 instrument ledger。同方向恢复仍规范化为 `REENTER`，真实反向 `REVERSE/OPEN_PROBE` 可保留语义但不能免费重复。未选择、blocked 和零风险候选不被误记为一次尝试；`0.75 + 0.666667 > 1` 是旧 envelope 下发现“本轮越界不能拖到下一轮”的历史反例，不是现行累计阈值。
- 聚焦验证使用项目 Python 完成 `128/128 PASS / 2.663s`，覆盖 dynamic research/action/state continuity、action continuity、experiment contract、formal chronology、Agent lifecycle/semantic binding、authorized revision 和层依赖；`git diff --check` 通过。该结果只关闭本节语义链，不包含仍在修复的公开网络与资格 namespace，也不是全量或 exact-commit 回归。

### 10.9 方向档位预算泄漏反例与修复

- 最终构造性验收发现：旧分配器虽已给出 `LONG=100 / SHORT=50` 的离散方向上限，却先取全局最高档形成包络，再按所有 cluster 的 `HIGH=2 / LOW=1` 共同切分。`1 LONG HIGH + 5 SHORT LOW` 会得到旧分配 `LONG=0.285715 / SHORT=0.714285`，使 LOW 方向借另一方向 HIGH 和 cluster 数量越过半档；这是离散档位下仍然存在的风险放大漏洞。
- 修复后先以 raw envelope 和 LONG/SHORT 自身档位建立方向容量，再在每个方向内部作确定性量子分配；同时强制全局合计、逐方向合计、`1e-6` 量子、cluster 唯一和零候选不放大。上述反例现为 `LONG=0.5 / SHORT=0.5`，SHORT 不超过自身 LOW 上限。
- TDD 先红后绿；计划/连续性 `53/53 PASS`，Agent lifecycle/compiler/experiment contract `50/50 PASS`，另有 `288` 组组合性质检查通过。该结果仍只证明本地 reference-risk 合同，不是主观档位校准、真实仓位或收益证据。

### 10.10 公开网络 raw-first 与错误分类收口

- 最终时序复核发现，outcome adapter、outcome durable store 与 qualification probe 曾把 HTTP 已响应但 body 为零字节的情况在封存前拒绝；bundle 虽已先调用 raw sink，却把 `b""` 的 `body_present` 错记为 false。现在三条正式路径都接受 `0..MAX` 字节原始 body 先绑定 request/status/final URL/received/captured time 和空字节 SHA-256，再由严格 parser 将零字节判为结构失败。失败终态重开只重放原件，不再发网络请求。
- 共享 HTTPS classifier 曾把除 3xx 外的所有 `HTTPError` 都标成 `PUBLIC_PROVIDER_UNAVAILABLE`，wrapped/injected 404 因此可能被洗成 coverage UNKNOWN；outcome parser 也曾把 HTTP 200 的任意 provider `code != 0` 视为 coverage。当前分类精确冻结为：3xx=`PUBLIC_REDIRECT_FORBIDDEN`，429/5xx=`PUBLIC_PROVIDER_UNAVAILABLE`，400/401/403/404 及其他非白名单状态=`PUBLIC_HTTP_STATUS_STRUCTURAL_FAILURE`；HTTP 200 非零 provider code、必需 datum 缺字段、零字节/坏 JSON/envelope 均在 raw 封存后结构失败。
- 新增 bundle、adapter、target outcome、qualification probe 的零字节构造反例，以及 4xx/wrapped-404、HTTP 200 非零 provider code、必需字段缺失反例。首轮均按旧实现红灯；最新独立只读复核中四条核心 raw-first 套件 `51/51 PASS / 6.937s`、public source collector `12/12 PASS / 0.611s`，HTTPS/classifier、adapter、outcome 联合套件另有 `36/36 PASS / 3.240s`。这些结果只证明本地单次封存和分类合同，不证明公开网络长期可靠、outcome 可得率或真实执行。

### 10.11 失败资格隔离、Phase B 正式入口与兼容上限

- 失败资格 ID 与 target ID 已进入静态 tombstone；successor 只能使用全新 ID，并由 production composition 确定性派生 `.runtime/v32/qualifications/<qualification_id>`。正式五入口不接受 project/runtime root、store、clock、verifier 或 binding registry 注入；Phase B 只接收身份和已封存 Agent payload。旧 PRE_NETWORK/Q0–Q8 兼容集合只允许精确失败身份只读重放，不能被新资格继承。
- 新 write-once authority/Phase B seal 使用锚定目录描述符、`O_NOFOLLOW`、逐级非 symlink 验证和发布后 lexical readback。该轮独立复核当时确认 production roots=`36`、静态 reachable closure=`189`、frozen bindings=`189`；在 V3.2-only 增量市场图模块进入 production closure 后，当前机械结果已更新为 roots=`42`、reachable paths=`190`、frozen bindings=`190`，且路径顺序与集合一致。namespace/tombstone/symlink/父目录替换/evidence-root alias/PRE_NETWORK 精确兼容共 `7` 项聚焦通过，五入口完整 Phase B `1/1 PASS / 136.570s`；这些旧测试时长仍只作为其发生时的历史证据。
- 旧失败根仍为 `44` 文件，整树摘要前后均为 `91f575a5a393d319abe0d16e7804765ce94f8ccb15d17fdb198fb58e847401ad`；旧 V3.1 loader 仍为 Q0–Q8=`9/9`、冻结路径=`74`、历史 monitor=`FAILED_CLOSED / resume_allowed=false`。用户保留副本仍为 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，不进入提交。
- 当前可证明上限是正常本地单写者环境：拒绝预置/静态 symlink，并对 authority 与 Phase B seal 提供目录替换竞态防护。controller、material、probe、mailbox、source-admission、outcome-tick 和 supervisor 的全部子存储尚未资格化为抵抗同一系统用户恶意并发目录替换；本次 public/local/non-executable 实验因此不得宣称敌对同用户文件系统安全。

### 10.12 增量三帧接线、正式交叉绑定与 invalidation 诚实边界

- production material adapter 原先把 Cycle 2–16 的三帧全部无条件 `REFRESHED`，战略 payload 又混入每轮变化的 aggregate/raw 身份，使缓存合同名义存在、实际永远不可达。当前候选把 frame payload 投影移到纯 Domain：战略只含慢周期闭合序列、source coverage 与 axis admission 的稳定语义；TACTICAL/TRIGGER 保留当前 bundle digest 与快材料。前序战略帧只有在 TTL 未到且稳定投影逐字相同时 exact carry，保留原 created/as_of/available/expires/payload/source refs 并绑定 predecessor；快帧每轮刷新。
- 独立复核进一步证明，单独验证 market bundle 和 timeframe transition 不能阻止“旧 frame + 新 bundle”错配，且该问题同时影响 STRATEGIC/TACTICAL/TRIGGER。正式 acceptance 现在从已完整验证的当前 bundle 独立重算三帧 payload digest；任一 role 不符即失败关闭。稳定物理噪声不会使战略投影失效，慢序列、coverage 或 axis admission 语义变化会刷新；TTL 不续期。
- 最终 policy 复核又发现 payload 正确仍不足以证明 frame provenance：自洽重签后的超长 TTL、伪 source refs、依赖/invalidator 集合、frame ID 或时点曾可通过宽泛 schema。当前唯一 Domain policy 同时供 adapter 生成、acceptance 与 local resume 独立重算：每个 REFRESHED role 精确绑定 ID、`created_at=decision_time`、当前 bundle 的 `as_of/available_at`、TTL `86400/3600/900`、当前 source refs 与冻结 dependency/invalidator sets；strategic carry 只接受 predecessor 不可变字段。每 role×五类真实重签漂移共 15 组在 Domain 与正式 acceptance 双层拒绝，合法 carry 通过；相关 Domain/adapter/lifecycle/acceptance/local 聚焦回归 `63/63 PASS`。
- 当前 OKX-only 信息事件只能证明“某公开 endpoint 请求发生”，不能证明其语义是宏观、监管、跨资产断裂或异常波动。为避免用任意 PIT digest 给自由文本事件贴标签，production 不接受 non-TTL invalidation 注入；这些类别保持 `UNKNOWN_NOT_AVAILABLE` 并进入逐轮 DataGap/manual plan。当前只接线可由前序帧精确重放的 `STRATEGIC_TTL_EXPIRED` 和已验 bundle 语义变化，不能声称八类 invalidator 已完整来源资格化。

### 10.13 逐组件 response capture 与 body-read failure 收口

- 原 source bundle 虽在解析前逐组件封存 body，但 status、final URL 与 request/received/captured 三时刻只存在于稍后的 aggregate row；进程若停在两者之间，会留下无法完整解释的孤立正文。当前每个已读 response 都先写入固定 body 路径，再生成自摘要 `public_component_capture`，绑定 qualification/component、method/path/canonical query、真实 status/final URL、三时刻、body 长度与摘要、attempt=1/no-retry、route/source/non-executable 边界；body 与 capture 全部 readback 后才允许解析或发下一请求。正式 replay 从 owning store 推导路径，交叉验证 capture、body 与 aggregate/failure receipt；缺失、篡改、交换、时钟或 URL/status 不符均失败关闭。
- 三个故障旁路同时关闭：optional `429/5xx` 只有 capture 成功并取得 raw binding 才可降为 coverage UNKNOWN，sink 失败时不得继续下一请求；optional timeout/connect 在任何 response 前发生时，必须先封存并回读固定路径的逐组件无响应 receipt，aggregate UNKNOWN 与 durable replay 精确绑定它，缺失、篡改、交换或 sink failure 都不能继续；`HTTPError.read()` 或 200 response `read()` 失败不再伪造为真实零字节 body，而是保存 `PUBLIC_RESPONSE_BODY_READ_FAILED`。typed transport-failure receipt 新增 nullable `response_final_url`：有 response 时必须保存真实、无凭据 HTTPS URL并符合 redirect/canonical 关系，无 response 时必须为 null。SERVER_TIME 在 response 已 capture、后续语义解析失败时也把私有 final URL/received/captured/route 元信息带到失败凭据，发布 aggregate 前再剥离，不改变公开 aggregate schema。`ValueError` 只在 `response.read()` 的局部物理边界捕获，status/final URL/schema 的同类编程错误不再被洗成网络失败。
- TDD 覆盖成功/零字节/429/503/redirect/坏 JSON、body/capture 中途失败、sink 失败不得继续、无响应 receipt 完成后才发下一请求、receipt 缺失/篡改/交换的零网络 replay 拒绝、普通响应与 HTTPError 的 `OSError`/`ValueError`/`HTTPException`/`IncompleteRead` body-read failure、capture 缺失/篡改/交换、aggregate mismatch 和 SERVER_TIME post-capture failure；最终两套聚焦测试独立复跑 `42/42 PASS / 1.314s`。这只证明本地 raw-first 证据与失败分类，不证明公开网络长期可用或来源资格成功。

### 10.14 Durable replay schema 1.2 与跨层证据身份收口

- 逐组件无响应 receipt 落盘后，最终监督复核发现 target durable replay 仍把全部 UNKNOWN 的 failure evidence 硬编码为旧 aggregate raw binding；真实新工件会在采集成功后于下一层重放失败。当前 Application-owned public-evidence contract 冻结 raw bundle/replay schema `1.2.0` 的三态语义：OBSERVED 绑定并重放本组件 raw；UNKNOWN+HTTP `429/5xx` 绑定同一组件 raw/capture；UNKNOWN+无 response 的 timeout/connect 绑定固定 typed component-failure receipt，禁止 aggregate fallback。
- 无响应 receipt 的 owning store 读取和语义验证通过 `V32PublicEvidenceVerifierPort` 暴露，由 Infrastructure 实现；Application 只消费 port 返回的已验证身份，不直接导入 collector、路径 helper 或 Infrastructure verifier。missing/tamper/component-swap 均在零新增网络的 durable replay 中拒绝；旧“UNKNOWN 必须等于 aggregate”的测试被删除并替换为 503+raw 与 timeout+receipt 的端到端成功/失败反例。
- 独立最终联合回归覆盖 transport、collector、durable replay、qualification、timeframe policy、adapter、formal acceptance、dynamic action plan 与 continuity，共 `157/157 PASS / 224.636s`；`git diff --check`、语法编译和 Application→Infrastructure 依赖检查通过。该结果只关闭本地 schema/分层重放缺陷；公开来源是否实际可达仍须由新 commit 后的 fresh qualification 证明。

### 10.15 五项易碎性复核后的实现级 P0/P1 收口

- 用户提出的五项问题不以“删掉约束”处理：连续主观数字已退役为三档上限；开放式依赖搜索移出热路径；`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 是一等零方向风险状态；reentry 改为全 instrument churn ledger 下的受限机会；物理故障在当前无账户权限中只冻结新增风险并保留暴露 UNKNOWN，未来逃生舱另行授权且不保证成交。
- 全量候选回归随后暴露 outcome 原因—证据角色 P0：无响应 transport receipt 与 response-backed raw capture 曾可互相替代。Domain、qualification monitor、Application classifier 与 owning store 现按五类无响应物理错误和 response-backed provider/empty-data 错误严格分离，并从 durable raw/status 唯一重建 normalization/observation；聚焦回归 `69/69 PASS`。
- 反向换向曾可绕同向 reentry 计数。当前 ledger 激活后，任一方向最终选中、合格、正 reference risk 的 `OPEN_PROBE/REENTER/REVERSE` 都消耗同一 attempts/cumulative 额度；同向恢复仍规范化为 `REENTER`，首次 INACTIVE probe 不计。计划、continuity、compile/acceptance 相邻回归 `93/93 PASS`。
- 合约 multiplier 与成本输入曾仍由 Agent 提供。现固定 `1 USDT` 非账户研究压力单位，从已验 `ctVal×ctMult` 得到每 contract 暴露，以 `tickSz/lotSz/minSz` 约束价格和研究数量，四项压力值按逐 tranche 入场价和冻结 rate 重算；缺任一规格时正风险拒绝、零风险 WAIT 保留。contract/compiler/lifecycle/acceptance 聚焦回归 `74/74 PASS`。这些 rate 不是账户费率或成交校准，真实 fee/slippage/tail max loss 继续 UNKNOWN。
- Dynamic Store 的第一版“私有名+AST”可被直接私有调用写入；第二版“一次 writer”又可由 `object.__new__(LocalV32AnalysisLane)` 跳过构造器领取，且异常转换缺少导入。当前仅在 Lane 完成 authority、root、collector、qualification factory、clock、material 与 public verifier 检查后，临时登记 exact owner→Store；Store 在该登记窗口内才发放唯一 opaque writer，登记在 `finally` 清除。伪 owner 在文件/checkpoint 变化前拒绝，无效 collaborator 不消耗 writer，第二 Lane 返回 typed local error。Store/production closure `18/18 PASS / 89.259s`，构造反例 `1/1 PASS / 41.483s`；独立复核的 Store+Lane `19/19 PASS / 328.275s`、closure `1/1`、registry cleanup 与 fresh-Store recovery 探针亦通过，未发现剩余 P0/P1。
- 该 writer 边界只防可信单进程生产组件的意外旁路；它明确不抵抗恶意 monkeypatch、主动导入私有登记器或 Python 私有内存反射。最终全 V3.2、全 Theory Paper、exact commit 与 fresh qualification 尚未完成，因此本节不能写成实验就绪。
- 完整 local Lane 五项初次虽为 `5/5 PASS`，累计耗时 `243.374s`，证明功能 PASS 不能替代热路径验收。轻量 profile 显示 Lane 构造/新 writer 仅 `0.0772s`，前 36 个推进边界多数为毫秒至 `1.55s`，热点集中在完成尾部重放和大型 Agent lifecycle 递归快照。`advance_analysis` 与 `verify_durable_analysis_completion` 现各自在单次函数调用内使用既有 owner/thread/task 与 strict built-in snapshot 绑定的 lifecycle memo scope；成功返回或失败后清空，custom Mapping 与跨调用/wake/thread/task/process 均不复用。相同完整周期最终 `1/1 PASS / 111.067s`（real `111.29s`），Local Lane+lifecycle 联合 `27/27 PASS / 143.065s`，缓存隔离/篡改/并发 `4/4 PASS / 42.650s`。这达到本机 deterministic 120 秒目标，但公开网络、fresh process、当前 Codex 与跨 wake 性能仍待 qualification。
- 首轮最终 V3.2 全量在 `589` 项中得到 `588 PASS / 1 ERROR / 936.206s`。唯一错误是 target-wake 的 `_UnusedMaterial` 空测试替身未实现 Lane 新要求的五个 callable；production 使用真实 adapter，网络 mock 未被调用。只补齐“若实际调用即失败”的测试接口、不移动审计门也不放宽 Lane 后，目标组合 `3/3 PASS`，从零全量复跑 `589/589 PASS / 933.646s`（real `933.96s`、user `911.79s`、sys `19.21s`）。全 Theory Paper 与 exact-commit replay 仍待后续收据。
- 同一最终工作树的全 Theory Paper 从零回归 `1274/1274 PASS / 1216.390s`（real `1216.90s`、user `1182.30s`、sys `30.33s`）。这关闭当前本地跨版本回归门；旧 Q0–Q8/74、静态/敏感检查、精确 commit 与 post-commit replay 仍须单独完成。
- 提交前最终只读检查已完成：旧 V3.1 完整 loader 重放 `1/1 PASS`，Q0–Q8=`9/9`、冻结实现路径=`74`、历史 monitor 继续 `FAILED_CLOSED / resume_allowed=false`；旧失败 V3.2 qualification 根仍为 `44` 文件，按项目相对路径与逐文件 SHA-256 形成的 manifest 摘要仍为 `91f575a5a393d319abe0d16e7804765ce94f8ccb15d17fdb198fb58e847401ad`。用户保留副本仍为 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，明确不进入提交。
- `git diff --check`、`compileall`、四份变更 Markdown 围栏、Application/Domain 分层 `2/2` 与 production closure `4/4` 均通过；候选没有变更 JSON。敏感模式只命中 public-HTTPS 负向测试中的虚构 proxy userinfo，测试同时证明该输入在任何网络调用前被拒绝且异常不泄漏；未发现真实凭据、账户、订单或可执行交易权限。精确候选为 `68` 个文件（`63` 个 tracked 修改与 `5` 个新增实现/测试文件），下一边界只允许显式 staging 与 commit，禁止 `git add .`。
- 上述 `68` 文件提交为 `294bc26` 后立即从零重放：V3.2 `589/589 PASS / 957.157s`（real `957.57s`、user `933.92s`、sys `20.52s`），全 Theory Paper `1274/1274 PASS / 1242.253s`（real `1242.73s`、user `1206.60s`、sys `31.69s`）。两套并行执行造成的资源争用耗时不作为热路径性能证据；它们只证明 `294bc26` 的回归终态。
- 本日志补入上述收据后将形成最终 qualification HEAD，并再次从零重放两套测试、旧 Q0–Q8/74、失败资格树和静态门。最终重放结果只在外部任务/资格前置收据中报告，不再写回 tracked 文件；否则每次写回都会产生一个尚未被测的新 commit，形成不可终止的自引用。fresh source、当前 Codex 与固定 outcome monitor 在此之前仍为 `UNKNOWN_NOT_QUALIFIED`。

### 10.16 新资格揭示的 OKX Global REST 域名漂移

- 最终 HEAD `08b6dff` 的 exact replay 为 V3.2 `589/589 PASS / 954.307s`、全 Theory Paper `1274/1274 PASS / 1238.500s`；旧 Q0–Q8/74、失败资格树、静态门和用户副本摘要均通过。随后新 authority `v32-qualification-btcusdt-20260808t220933z` 成功封存，但 PUBLIC_SOURCE 唯一 attempt 在首个 `SERVER_TIME` 请求收到 Cloudflare HTTP `403`，资格于 controller revision `2` 永久 `FAILED_CLOSED`。response body=`151` bytes、SHA-256=`eed0b81a2fbdd1c5a9f80705885fc5bbf346ba428a79ff7a13ec8491c6a8e96c`；status、final URL、raw body、component capture 与 no-retry transport-failure receipt 均已耐久保存。CURRENT_CODEX、monitor、target authority/genesis 均未开始，禁止再次 advance 或重试该 ID。
- 这不是 parser、raw-first 或代理凭据问题，而是 source identity 漂移：OKX 官方变更日志在 2026-05-20 将 Global REST 推荐基址从 `www.okx.com` 更新为 `openapi.okx.com`，旧域名虽声称继续兼容，但当前本地公共出口对旧域名返回 Cloudflare 403；同环境对 `https://openapi.okx.com/api/v5/public/time` 的独立非资格化诊断得到 HTTP `200`、provider code=`0`。因此只迁移 V3.2 的公开 REST host 和 route policy identity，路径、查询、公开 GET 白名单、无凭据、无重定向、单 attempt/no retry、raw-first 和 evaluation 语义全部不变；旧 V31 的 74 个冻结路径及当时已有的两份失败资格保持原字节。后续第三、第四资格另见 10.19–10.20，本段只是当时历史边界。

### 10.18 OpenAPI 集成夹具与 raw/capture 失败原子性

- 最终全量首轮在 `615` 项中得到 `614 PASS / 1 ERROR / 969.118s`。唯一错误来自 formal chronology 的注入 `_Opener` 未声明新的 V2 route policy；严格逐组件 capture 因而拒绝 `INJECTED_PUBLIC_OPENER_NO_ROUTE_CLAIM`。真实 `V32SystemPublicHttpsOpener` 已携带 exact V2 policy，直接故障属于测试夹具迁移遗漏；修复只给该集成入口绑定 production policy，没有允许未知 route、fallback 或重定向。
- 同一失败暴露出独立生产健壮性问题：组件正文已 write-once 成功、capture 元数据随后失败时，transport 会把 `V32PublicComponentRawSinkError` 包装成 OSError；collector 若把它当普通物理网络失败，会再次写同一路径并把原始结构错误遮蔽成 `TRANSPORT_FAILURE_WRITE_FAILED`。当前 collector 在 durable failure 分支前检查 typed leaf；`PUBLIC_RAW_SINK_STRUCTURAL_FAILURE` 直接形成结构性 `QUALIFICATION_FAILED`，保留单份 raw tail，禁止 transport-failure receipt、重复 raw 写入、资格推进和重试。
- 新构造性回归使用真实 bundle transport、真实 write-once store 与 capture 发布故障，验证网络只调用一次、raw 路径只写一次、transport-failure/qualification 均不存在。精确失败与 formal chronology `2/2 PASS`，source collector + bundle transport + chronology 联合 `46/46 PASS / 2.511s`。最终 V3.2、全 Theory Paper、旧冻结链、exact commit 与 post-commit replay 仍须从这些最终字节重新执行；本节不把局部 PASS 外推为公开网络或实验资格。

### 10.19 第三资格、代理协议顺序与永久身份收口

- 上述最终字节已提交为 `05699eb9ce353dff4c2df09328feb5b22e1b6735`。exact HEAD 回归为 V3.2 `616/616 PASS / 970.690s`、全 Theory Paper `1301/1301 PASS / 1253.966s`；旧 V31 Q0–Q8=`9`、冻结路径=`74`，两棵既有失败资格树及用户副本摘要保持不变。第三组全新身份为 qualification `v32-qualification-btcusdt-20260809t010844z`、target `v32-prospective-btcusdt-20260809t010844z`；authority preparation、controller initialization 与 PUBLIC_SOURCE reservation 分别形成单一耐久边界，随后唯一 SERVER_TIME 请求收到 Cloudflare HTTP `403`，controller revision `2` 永久 `FAILED_CLOSED`。只产生一份 `151` bytes raw、一份 component capture、一份 typed transport failure；CURRENT_CODEX、monitor、qualification receipt、target authority/run 和 outcome 均为零，禁止重试或推进该 ID。
- 失败不是缺少固定头或 OpenAPI host 不可达：当时 source transport 已发送 JSON Accept 与固定研究 User-Agent。同一 Python Request 经标准 urllib system proxy handler 返回 `200`，经 V3.2 V2 route 的“空 ProxyHandler opener 构造完成后，再由 `open()` 手工 `set_proxy`”路径稳定返回 Cloudflare `403`；命令行同头对照也为 `200`。根因是自建路由改变了标准代理协议处理顺序/请求形态。当前候选把已验证无 userinfo 的 system HTTPS proxy 固定为 opener 内 `_FrozenHttpsProxyHandler`，在 protocol chain 中建立 CONNECT；bypass 只在冻结前检查一次，之后不重读全局 `no_proxy`，也不轮换、不回退、不暴露代理地址。
- source 与 outcome 现在共用唯一 request builder：只允许 `Accept: application/json` 与 `User-Agent: agent-trade-emotion-v3.2-public-research/1.0`。缺失、额外、Cookie、Authorization、OKX key、UA 漂移均在联网前失败；route policy 升为 `...FIXED_HEADERS...V3`，outcome adapter contract 升为 OpenAPI V3并绑定 header-policy ID、规范化头摘要、禁止 caller header 注入和 proxy identity rotation。旧 www/V1 与第三资格 OpenAPI/V2 证据只允许 exact run/qualification/digest 只读回放，active builder 不接受旧 policy。
- 独立复核发现第三失败 ID 尚未进入 Domain tombstone；目录存在虽会阻止覆盖，但路径被移动后理论上可复用，构成 P1。当前 qualification/target exact pair 已加入永久墓碑；任一 ID 与任何新配对均在 authority/runtime namespace 创建前拒绝。第三资格九份 preflight subject、outcome adapter、component capture 与 transport failure 以原摘要精确重放；兼容分支不接受其他 ID、自签或字段漂移。
- 同次复核还发现 source durable evidence 只保存 composite route policy，未直接表达 owning header policy。为避免把“当前代码用了同一 builder”误写成耐久证明，active component capture、component no-response failure 与 aggregate transport failure 升为 `1.2.0`，由 builder 内生写入固定 `request_header_policy_id` 与规范化头摘要，调用方无参数可覆盖；response-backed durable replay 同时交叉核对 failure 与 capture 的两项绑定。三棵旧树分别按原 1.0/1.1 exact identity+digest 只读回放，不接受重新签名的近似旧工件。
- 当前受影响链 `81/81 PASS / 5.429s`，真实但非资格化的唯一 OpenAPI SERVER_TIME 预检为 HTTP `200`、provider code=`0`、route mode=`SYSTEM_HTTPS_PROXY_NON_CREDENTIAL`。这些只证明修复了本机公共路由故障，不构成 fresh qualification：最终 V3.2、全 Theory Paper、旧冻结树、静态门、显式 commit 与 exact post-commit replay 全部通过后，才允许用第四组全新 ID 执行一次不可重试资格。
- 最终提交前字节回归：V3.2 `617/617 PASS / 976.708s`（real `977.56s`），全 Theory Paper `1302/1302 PASS / 1257.477s`（real `1258.72s`）；分层、production-root closure 与 workspace freeze `10/10 PASS / 5.058s`，旧 V31 Q0–Q8/74/永久 monitor failure 精确重放 `1/1 PASS / 0.907s`，11 个变更 Python 文件语法、Markdown 围栏与 `git diff --check` 通过。三棵失败资格仍为 `44/47/47` 文件，整树摘要依次为 `91f575a5a393d319abe0d16e7804765ce94f8ccb15d17fdb198fb58e847401ad`、`3bcaa9b5f1824803a3f67dcd77302b131fc34b927ccb0a1038d9e193e92c4254`、`af0fcee816a25af8708696db685a0b28b41e78716719cbdd620040b3139dcb80`；用户副本仍为 `63,676` bytes / `91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`。测试产生的约 `1.3 MB` Python cache 已清除，未删除研究或运行证据。下一边界只允许显式 staging/commit 与 exact post-commit replay，不把本行结果冒充 fresh qualification。

### 10.20 第四资格的资金费时间语义与失败证据重放修复

- commit `8ca2ae7bb71e6c1f63c121824f8140de9dec7339` 的 exact post-commit replay 为 V3.2 `617/617 PASS`、全 Theory Paper `1302/1302 PASS`。第四资格 `v32-qualification-btcusdt-20260809t030358z` 在唯一 PUBLIC_SOURCE attempt 中取得 `12/12` 份 HTTP 200 响应，却以 `V32_PUBLIC_SOURCE_PROVIDER_TIME_TRAVEL` 永久失败。只读原件证明 OKX funding-history 的 `ts` 是该记录的 provider observation/update time，`fundingTime` 与 `nextFundingTime` 是本次/下次资金费结算日程；旧 collector 把未来 `fundingTime` 错当观察时间并纳入 PIT `as_of`，属于实现假阳性，不是未来数据真的进入决策。该失败树保持 `70` 文件且全部文件的 mtime/ctime 不晚于原失败终态；按与前三棵失败树相同的“项目相对路径 + 逐文件 SHA-256 + 末尾换行”算法，当前可复现整树摘要为 `bc42b90fbcb6458dd3cf0c18fd7afb3ea94ac40f0096e27749cad8e272b8061b`。此前监督摘要记录的 `29115ccce11296f980f72bd1d72dae1f35edc2234d83a93e49a78ec21250780c` 缺少可重放 manifest 且无法从原树复现，现保留为历史错误说法，不作为字节漂移证据。禁止重试、修补或改写该失败树。
- active datum/bundle schema 已版本化并分离四类时间角色：每个 datum 保存原始 `provider_observed_at`、知识安全 `observed_at`、本地 `available_at` 与可选 `effective_at`；当前 schema 不存在通用 `next_scheduled_at` 字段。OKX funding 行固定映射为 `ts → provider_observed_at`，再按冻结 clock-skew policy 形成 `observed_at`；`fundingTime → funding-rate datum.effective_at`；`nextFundingTime` 则成为独立 `next-funding-settlement-time-ms` schedule datum 的 `effective_at`，并强制 `ts <= fundingTime < nextFundingTime`。只有相应市场 datum 的知识安全 `observed_at` 可进入 observation/PIT `as_of`；bundle `as_of` 排除 SERVER_TIME/INSTRUMENT metadata、`effective_at` 与未来 schedule，并取实际市场 datum 的最晚观察时刻；逐 axis 的观察时刻只取该 axis 绑定组件，不再使用全局最大值。
- 时间完整性同时补齐四个相邻缺口：provider 领先本地最多允许冻结的 `5s` 时钟不确定性并保留原始时刻；realtime/funding 分别使用 `120s/900s` staleness 上限，且相对整个 bundle 最终可得时刻而不是逐请求响应时刻；K 线必须连续、截至最近一个已闭合 bucket，并由 verifier 重算 OHLCV、区间收益与 RSI；trades 明确保存查询窗口、上限和截断状态。公开来源时钟容差由唯一 Domain 常量提供，collector 不再复制第二份数值。
- PUBLIC_SOURCE 在 raw/capture 成功后发生 derivation、analysis build 或 owning verifier 失败时，必须生成 write-once validation-failure receipt。receipt 绑定完整 attempt、aggregate raw、12 个 component raw/capture 或 no-response 原件、实际物理 SHA-256、稳定失败码和真实失败时刻。`verify_durable_v32_public_source_validation_failure_v1` 从 owning store 零网络重读这些原件，只证明历史 sealed failure 事实和全部物理输入仍完整；它不要求修复后的当前 collector/parser 继续抛出相同旧错误。partial prior attempt 只能恢复同一 failure receipt，禁止第二次 transport 或第二次取时钟。
- 当前代码是否仍复现历史实现失败由独立诊断 `assess_current_v32_public_source_validation_failure_reproduction_v1` 给出，可报告 `REPRODUCED_EXACT_FAILURE / DIFFERENT_FAILURE_UNDER_CURRENT_CODE / CURRENT_CODE_REPLAY_UNAVAILABLE / NO_LONGER_REPRODUCES_AFTER_CODE_CHANGE`。该结果不是 authority：即使当前代码不再复现，历史 receipt、attempt、raw/capture 和永久 `FAILED_CLOSED` 仍不改变。actual-capability controller 只有在固定 EvidenceStore 完整重放历史 failure binding 后才可提交终态 checkpoint；以后每次 terminal wake 都再次物理重放该 binding，并把当前复现状态只作为诊断。篡改任一 binding 会失败且 checkpoint 保持原字节，不会把只有 `failure_code` 的孤儿终态误当可信证据。CURRENT_CODEX/outcome 不支持此 source-specific binding 时显式拒绝，不做通用伪兼容。
- 第四 qualification/target exact pair 已进入 Domain 和 preflight subject 永久 tombstone。聚焦复测为 collector `31/31 PASS / 2.808s`、controller `13/13 PASS / 4.202s`、Agent semantic compiler `24/24 PASS / 60.896s`、qualification materializer `6/6 PASS / 251.629s`。**在该第四资格历史边界**，这些只证明当时工作树的局部合同；完整回归、explicit commit、exact post-commit replay 和第五份 fresh qualification 尚未完成，因此实验当时仍未开始。
- 五项“易碎瑞士手表”问题的当前边界：连续主观分数已被三档有依据确信替代，连续 `risk_reference_units` 仅可 exact 回传 sealed 派生值；依赖身份仍保留以防同源故事重复，普通轮只在**构造路径**追加变更 delta。同一 owner-bound acceptance/public-evidence scope 内，相同 strict snapshot 的 owning closure 只完整重建一次；scope 退出、失败、custom Mapping 或跨 thread/task/process 均不复用，后续阶段复用封存材料而非 verifier cache。混沌/无方向波动是一等零方向风险状态，风险候选必须绑定 typed `BREAKOUT_BOUNDARY` 且保持 blocked/conditional/no-tranche；reentry 是每次≤1、最多两次、累计≤2 的研究机会，不是自动重开；未来 capsule=`NOT_IMPLEMENTED_NOT_QUALIFIED`，当前 recovery observer 不是执行风险 supervisor。当前 non-executable pilot 不实现或伪造“市价核按钮”，也不把研究 ledger 冒充真实连续止损计数。

### 10.21 历史快照：五项易碎性终审、动态图隔离与当时提交前全量收据

- **本节只描述当时 commit `093b4e7` 前后的历史候选，已被 10.30 的 V3.2.6 修订取代。** 当时连续 0–100 主观输入已经不存在，Agent 主观判断只能提交 `EXTREME_UNCERTAINTY/LOW/HIGH`；内部 `0/50/100` 只作为封闭 policy 的 off/probe/normal 编码。`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 均为一等状态且方向风险为零；相反假说只用于可证伪，不强制下注。当时全 instrument 24h churn ledger 的累计上限为 `1`；这一历史上限后来发现与“最多两次、每次可到 1”不可构造，当前已改为 per-attempt≤1、attempts≤2、cumulative≤2。
- 没有删除 dependency closure。构造路径新增 V3.2 专用 `v32_incremental_market_graph.py`，只在 pilot 有界 working set 上追加本轮 node/association delta；不存在固定 `24h` 同类证据归并器，`24h` 只属于 reentry churn ledger。V3.1 的 `74` 个冻结 runtime 路径已恢复并保持原字节。当时 registry 单次 build/verify 内部的 projection/closure 复用、`42 roots / 190 local paths / 190 bindings` 与 `20/20 PASS / 118.929s` 均只属于该历史 commit/scope，不能证明后续完整 acceptance、outer wake 或当前未提交 closure。后续实测发现完整 acceptance 仍会经 projection、registry 与 market-view 重建累计 closure 四次，当前修复与证据见 10.30。
- 当时 Cycle 16 性能构造包含 `9,760` 条 node history 与 `9,680` 条 association history；`79.362s` 包含 projection 构造、registry build/verify 的历史测试范围，并不是完整 acceptance/outer-wake 单独计时。公开图投影当时为 `18/18 PASS / 106.148s`；这些结果不能外推为当前 fresh network、Codex delivery、monitor 或 15 分钟端到端资格。
- public source datum、bar、book、trade 均升级为 strict raw-first 语义合同；funding 保存 provider `ts`、知识安全 observed、HTTP local available、funding/next-funding effective schedule 四类时钟。validation failure receipt 精确绑定 stage、System UTC failure time、attempt、aggregate raw、每个 component raw/capture 与物理摘要。终态 replay 从 canonical owning `transport-failure.json` 和 exact attempt reservation 重建；空 store、自签 failure、未封存证据和 attempt swap 全部失败关闭。历史 sealed failure verifier 与当前代码 reproduction diagnostic 保持分离。
- 最终全量前曾发现一项测试夹具不一致：`test_production_delta_carries_only_unchanged_strategic_semantics` 只修改 4H bar 的 `volume_contracts`，却未同步匹配 PIT datum、自摘要与 bundle member digest；严格 verifier 正确返回 `BAR_RECONSTRUCTION_MISMATCH`。夹具现同步更新对应 datum 与 member digest，production verifier 未放宽；该测试模块随后 `6/6 PASS`。
- 当前最终候选从零串行回归为 V3.2 `646/646 PASS / 1102.390s`（real `1102.73s`、user `1062.77s`、sys `32.12s`），全 Theory Paper `1400/1400 PASS / 1383.323s`（real `1383.89s`、user `1332.56s`、sys `42.96s`）。五项聚焦 `120/120 PASS`；最终受影响链的独立复核 `109/109 PASS / 469.262s`。独立 diff 终审没有 P0、P1 或 P2 阻断项。
- 旧 V3.1 full loader 只读重放仍返回 Q0–Q8=`9`、冻结 runtime binding=`74`、唯一旧 run 正确且 monitor 永久 `FAILED_CLOSED`。四棵失败 V3.2 qualification 保持 `44/47/47/70` 文件，当前可重放 whole-tree 摘要依次为 `91f575a5a393d319abe0d16e7804765ce94f8ccb15d17fdb198fb58e847401ad`、`3bcaa9b5f1824803a3f67dcd77302b131fc34b927ccb0a1038d9e193e92c4254`、`af0fcee816a25af8708696db685a0b28b41e78716719cbdd620040b3139dcb80`、`bc42b90fbcb6458dd3cf0c18fd7afb3ea94ac40f0096e27749cad8e272b8061b`。第四树此前的 `29115cc...` 没有 durable manifest、不能用同一算法复现，只保留为历史错误摘要；所有第四树文件 mtime/ctime 均停留在原失败创建窗口，没有后续字节修改。
- 用户保留副本 `THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md` 当时仍为 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，不 staging、不删除、不修改。该历史边界仍是 precommit 候选；其后的提交与第五资格结果见 10.22。预测增量、校准、成本后收益、跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

### 10.22 commit 093b4e7、第五资格真实容量失败与新 P0

- 上述 20 个文件已显式提交为 `093b4e79d43ef523e0926aa1e8495ba13feb4145`，用户副本未进入 index。exact post-commit V3.2=`646/646 PASS / 1096.106s`（real `1096.93s`），正确全口径 `test_theory_paper*.py`=`1400/1400 PASS / 1382.714s`（real `1383.09s`）。一次较窄的 `test_theory_paper_v2*.py` 也得到 `1331/1331 PASS`，但它少 69 个早期基线测试，不作为全 Theory Paper 收据。旧 V3.1 loader=`9 gates / 74 runtime bindings`；V3.2 closure=`42 roots / 190 paths / 190 bindings`；四棵旧失败树及用户副本摘要不变。
- 第五 qualification=`v32-qualification-btcusdt-20260809t074253z`、target=`v32-prospective-btcusdt-20260809t074253z`。authority、controller revision `0`、PUBLIC_SOURCE reservation 和唯一 aggregate attempt 各自单边界推进；aggregate 内 `12` 个固定 `openapi.okx.com` public GET 均 HTTP 200、attempt=`1`、retry=`false`，PUBLIC_SOURCE 在 revision `2` COMPLETE。CURRENT_CODEX reservation 在 revision `3` 创建，attempt=`1`、retry=`false`，尚未执行 Agent。
- 材料化逐边界保存 `11` 个 role 后，在构造 `agent_market_graph_view` 时抛出 `V32_AGENT_MARKET_GRAPH_VIEW_PAYLOAD_TOO_LARGE`；Agent view、mailbox、CURRENT_CODEX evidence root、monitor probe、qualification receipt、target authority/run/outcome 均不存在。无第二 network/Agent attempt。真实输入有 `414` 根闭合 bars：`15M=96 / 1H=168 / 4H=90 / 1D=60`。只读重建的未封存 view 约 `352,219` canonical bytes；`citable_evidence_records≈208,156`、bars≈`75,301`、non-bar≈`34,036`、axes≈`15,536` bytes。旧注释把 256 KiB 错称为足以容纳 96-bar request ceiling，却未计四周期合计和真实 closure，是 fixture/容量模型失败。
- 修复采用 bounded proof projection，不是删除证据或无限抬 cap：所有 citable evidence 逐条保留 digest、availability、closure status、完整 dependency group IDs、exact closure digest 及 node/association/evidence-ref/group counts；完整 closure row 继续 write-once 保存在 graph dependency registry。builder 与 acceptance owning verifier 从完整 registry 重建每个摘要/计数/组并与 view 精确比较，任一 registry/view 篡改失败关闭。Association IDs 不是 Agent 必须逐字阅读的市场事实；Agent 以 evidence digest 和 dependency groups 分析，确定性 compiler/acceptance 用完整 registry 执行同源去重与可追溯重放。禁止 top-k、漏 evidence、静默截断、聊天摘要或把 closure digest 当因果/独立性证明。
- 旧 composition 还暴露 materializer 位于 controller try/catch 之外的 P0。异常后 controller 仍停在 revision `3 / RUNNING / CURRENT_CODEX=PENDING / ATTEMPT_RESERVED_NOT_STARTED`，物理上可被下一次 advance 再次进入；这不是合法 terminal。第五 pair 必须永久 tombstone，任何 API 从新版本加载时拒绝。未来 materializer exception 必须写入 single-attempt `materialization-failure` receipt，绑定 qualification/target、authority、CURRENT_CODEX reservation、精确失败 stage、System UTC、已封存 role bindings/physical bytes 和稳定错误链；controller 以 predecessor CAS 追加一次 `FAILED_CLOSED`，后续 wake 只重放 receipt 和终态，不再次 materialize/Agent/monitor。
- 第五树保持原字节：`96` files，按与旧四树相同的 shell bytewise path sort + per-file SHA-256 + whole-manifest SHA-256 公式，当前可复现摘要=`e1016aaafad02af68cc860fe909a34445b11f898eddebea8fb672b80e83d396a`，最后 mtime/ctime=`2026-08-09T07:48:11Z`。较早 Python `Path` 排序得到的 `9617afd...` 使用不同排序口径，不能作为冻结摘要。当前只读监督确认 public/local/non-executable、无账户/订单/凭据/资金、旧四树不变且没有第二 run。3.2.4 修复、新提交、exact replay 和全新第六资格之前实验继续 NO-GO。

### 10.23 V3.2.4 有界 Agent 视图、材料化终态与独立复核

- 真实第五资格的只读重建在新 `agent_market_graph_view v1.1.0` 下为 `187,892` canonical bytes，逐条保留 `55` 条 citable evidence、`815` 次 dependency-group occurrence、`414` 根 bars、UNKNOWN 与 OTHER；完整 closure identities 仍在 verified graph registry，由 Application owning verifier完整重建并核对 digest/count/group。真实 proposal/input=`472,441/475,433` bytes，selection/input=`589,786/592,787` bytes，分别位于独立 packet/input hard cap 内。完整 414-bar proposal→selection→READY 两阶段端到端独立复核 `1/1 PASS / 252.087s`。
- Cycle-16 `187,895` bytes 只把同一冻结形态的 cycle index/revision 改到 16，用于检查字段增长；没有构造 16 轮累计 registry，因此真实 Cycle 16 的累计容量与上游重放耗时仍未资格化，不能用这个数字声称 16 轮节拍已经证明。
- 材料化异常现在由 controller 消费同一 CURRENT_CODEX reservation，并形成 write-once failure receipt 与 terminal CAS。material、mailbox、probe 三类异常现场分别重扫：成功为 `VERIFIED_EXACT` 并绑定 exact inventory；重扫本身失败为 `UNKNOWN_REPLAY_FAILED` 与稳定 `*_PREFIX_REPLAY_FAILED`，空 inventory 明确表示未知而非“现场为空”。三类 recovery-scan 注入均验证首次 wake 永久 `FAILED_CLOSED`、seal exactly once，第二 wake 不再构造 materializer/capture/probe；UNKNOWN receipt 只证明单尝试终止及 authority/reservation/controller predecessor，不伪称物理现场完整。
- 聚焦证据：controller `18/18 PASS / 3.451s`，Agent lifecycle `24/24 PASS / 27.155s`，qualification materializer `12/12 PASS / 422.808s`。独立终审为 `P0=0 / P1=0`；剩余 P2 是累计 16 轮真实节拍尚未资格验证，以及失败原子实现的维护复杂度。后者不扩大交易能力，后续仅在不改变 receipt/schema/replay 语义的前提下考虑抽取通用 exact-prefix helper；本次不以重构换取表面简短。
- 提交前从零串行全量回归已完成：V3.2=`657/657 PASS / 1244.759s`（real `1245.23s`），正确全口径 `test_theory_paper*.py`=`1411/1411 PASS / 1541.822s`（real `1542.66s`）。这只关闭当前工作树的本地回归门；显式 3.2.4 提交与 exact post-commit replay 在本节写入时仍未完成，不得写成 successor qualification 或实验已经开始。第五树继续保持 `96` files、摘要=`e1016aaafad02af68cc860fe909a34445b11f898eddebea8fb672b80e83d396a`、最后 mtime/ctime=`2026-08-09T07:48:11Z`；用户副本继续排除在 staging 外。

### 10.24 commit 975e7a8 与 post-commit authority-evidence P1

- 上节 3.2.4 容量与材料化修复已显式提交为 `975e7a873e9f801594385e2feb00453586f270c3`，用户副本未 staging。该 exact commit 之后手工重放 V3.2 `657/657 PASS / 1242.357s` 与全 Theory Paper `1411/1411 PASS / 1530.794s`；旧 V3.1 loader 仍为 `9 gates / 74 paths`，V3.2 production closure 为 `42 roots / 190 paths / 190 bindings`，五棵冻结资格树及用户副本摘要未变。
- 上述回归结果真实发生，但它们只存于终端/文字记录。当时 `WorkspaceFreezeReceipt 1.0.0` 只绑定 branch/commit/tree/tracked bytes/允许用户文件，没有绑定 suite、argv、Python、计数、状态或原始输出。因此 qualification authority 可以在不能机器证明这两次执行的情况下生成；独立复核将其重新打开为 blocking P1，**第六资格在该历史边界尚未创建**，其后真实失败见 10.25。
- 候选修复新增 qualification-ID 专属 ignored/write-once namespace。第一个字节是 `attempt=1/retry=false` reservation；两个固定 suite 分别为 `test_theory_paper_v2_v32*.py` 与 `test_theory_paper*.py`，统一使用 `/opt/homebrew/bin/python3.12 -I -m unittest discover -s tests -t .`。调用者不能注入 argv、pattern、environment、clock、output、store、timeout 或 retry；关键 Git 读取固定 `/usr/bin/git` 和清洗环境，不继承 caller `PATH/GIT_DIR/GIT_WORK_TREE`。
- 每份 execution receipt 绑定 exact branch/commit/tree、Python executable/realpath/物理 SHA-256/version、固定命令/环境、开始/结束、exit/status/counts/skips、typed `runner_outcome`、stdout/stderr 有界字节/摘要/完整性与每 suite 前后 worktree 摘要。runner 对 stdout/stderr 各保留最多 `4 MiB + 1` 的物理检测边界，用新 process group 运行；超时、输出超限、直接子进程关闭两管道后卡住、后代进程泄漏、中断和读取异常都有有界终止/排空，保留已捕获前缀并且不能 PASS。跳过数必须为零。
- 两份 PASS receipt 按固定先后顺序形成 aggregate；WorkspaceFreeze `1.1.0` 绑定该 aggregate，并在 live verifier 中物理重开 aggregate→reservation→两份 receipt，验 target/qualification exact pair、exact Git/Python 与 `aggregate.completed_at <= workspace.observed_at`。旧 `1.0.0` 只保留历史语义验证，不能创建新资格。
- 信任边界终审确认：这些对象是无密钥 self-digest 和本地 write-once 路径，能够给受信任本地控制器提供可重放、失败关闭的运行记录，但不能对抗拥有项目/运行目录写权限与代码执行权的恶意本地 owner。测试夹具可以在隔离临时仓库合成 schema-valid PASS receipt，且只被 tests 导入、未进入 `trade_system` production closure；这同时证明不能把本地 receipt 写成 independent/third-party/provider/hardware attestation。aggregate 的固定 claim ceiling 已收紧为 `TRUSTED_LOCAL_CONTROLLER_POSTCOMMIT_AUDIT_ONLY`；外部 CI/OIDC、远端签名或硬件根超出当前 local pilot。
- 独立复核进一步发现，仅在 prepare 和最终 target full loader 重放收据仍不足：prepare 后若 approval、theory bytes、qualification phase/authorization、Q0–Q8 subject、其他 support 或 implementation byte 被删改，旧 `_load_authority` 仍可先发公开网络请求或进入 Agent mailbox。候选因此复用现有 full-loader helper，要求每一次 qualification `advance/claim/submit/finalize` 在构造 transport/materializer/mailbox/probe 或写任何 target byte 之前，完整重放 legacy predecessor、approval/theory semantic+source bytes、contract、manifest、qualification phase/authorization、Q0–Q8 gate/subject、所有 support、runtime closure 和 post-commit 原件。
- 最终提交前候选已完成：postcommit `16/16`、workspace `4/4`、qualification Phase-A/full loader `26/26`、lifecycle `16/16`、production closure `4/4`、qualification materializer `12/12`；独立终审为 `P0=0 / P1=0`。从零串行全量回归为 V3.2 `681/681 PASS / 1303.271s`（real `1303.60s`）、全 Theory Paper `1435/1435 PASS / 1591.557s`（real `1592.08s`）。**在该历史提交前边界** production closure=`42 roots / 192 paths / 192 bindings`；旧 V3.1 loader `11/11` 通过并保持 `9 gates / 74 paths / monitor FAILED_CLOSED`。五棵历史资格树继续为 `44/47/47/70/96` 个文件且摘要逐一不变，用户副本仍为 `63,676` bytes / `91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`。这些仍是当时未提交工作树证据；随后提交及第六资格事实见 10.25，不得把本行冒充当前 `43/194/194` 候选或 fresh qualification。

### 10.25 commit e0c7d3d、第六资格失败与 V3.2.5 Presentation P0

- 10.24 的治理候选已提交为 `e0c7d3da4e0809fd21b0d241db84e0c17155d4ff`。第六 exact pair=`v32-qualification-btcusdt-20260809t131915z / v32-prospective-btcusdt-20260809t131915z`；两份正式 post-commit receipt、aggregate、Phase-A、Q0–Q8/全部 support/`42 roots / 192 paths / 192 bindings` 和唯一 PUBLIC_SOURCE attempt 均通过。CURRENT_CODEX attempt 只预留一次，materializer 在 `CONTEXT_PACKAGE:PROPOSAL` 写入 typed failure 后将 controller 推进至 revision `4 / FAILED_CLOSED`。树内有 `14` 个 material roles 和 proposal packet，但无 proposal input、mailbox request/claim/delivery、monitor schedule/probe、qualification completion、target authority/run/outcome；该 pair 永久 tombstone。
- 第六真实 packet/input=`559,522/562,654 B`，低于 `1 MiB`；旧 512 KiB 子门迫使它进入 `121` shards、约 `7.79 MB` 的膨胀路径。对同一 sealed request 进一步只读重建，旧 `read_and_claim` 返回=`1,687,318 B`：packet 在 `request.agent_input_context.canonical_packet`、`input_materials.canonical_packet_original`、`ordered_delivery_units[0].document` 三处重复，而 gate 只测第一处。qualification/target 又在构造返回前先提交 claim，存在“超限后永久 CLAIMED”的第二个 P0。
- 当前 V3.2.5 候选建立共享 `CurrentCodexPresentationEnvelope`，并把本 pilot 的可用表示固定为 `INLINE_ONLY`：packet 只出现一次；checkpoint、request、可选 claim、严格标量 controls 和唯一正文表示共同 self-digest，并按最终 canonical bytes 接受 `1 MiB` 门。mailbox enqueue 在任何 material/request/checkpoint 写入前，以最大时间长度和 TARGET controls 精确预演最坏 claim；qualification/target 再以实际边界时刻于 CAS 前预演，CAS 后必须与预演 claim/checkpoint 完全一致。容量失败不留下请求、材料或 checkpoint 变化。`SHARDED` package 仅是未来未资格化能力，须另行取得分段 cursor、逐段 ACK、重组、耐久 consumption receipt 与整段容量证据，当前 successor 禁止使用。
- 第六 sealed proposal 的新 envelope 只读测量约 `566–568 KiB`，完整 packet 字节只出现一次；旧 `1,687,318 B` 路径不再返回。该对象由耐久 mailbox chain 可确定性重建且自带 digest，但“本地能重建”不证明 provider/transport 已接收、未截断交付或当前 Codex 已消费，不能称为 transport attestation。聚焦回归当前为 mailbox `7/7`、prospective runtime `14/14`、Agent lifecycle/compiler `49/49`、analysis adapter `6/6`、target wake `16/16`、lossless delivery `5/5`；全量 suite 和提交后正式收据仍待完成。
- mailbox 的 crash 边界已从泛化“write-once/CAS tail”具体化为四个独立状态转移：`REQUEST→checkpoint`、`CLAIM→checkpoint`、`DELIVERY+receipt→checkpoint`、`CONSUMPTION+receipt→checkpoint`。每条路径都以首次不可变字节、首次时间与唯一 predecessor 为准；重入只允许补同一 CAS，冲突对象和第二 attempt 拒绝。若 CAS 已成功而调用方只丢失返回，重复 enqueue/claim/submit 分别精确识别已提交的 `REQUESTED/CLAIMED/DELIVERED` successor 并直接返回。V3.2-owned package-shared `trade_system/theory_paper_v2/v32_durable_json.py` 先写同目录私有临时文件，验证完整字节后 `flush+fsync(file)`，以不可覆盖的原子发布再 `fsync(parent directory)`，最后清理临时项；`infrastructure/v32_durable_json.py` 仅为旧导入保留薄兼容导出，正式 Application/Infrastructure 路径均直接依赖 package-shared owner。已存在逐字相同对象保持幂等，冲突/race 失败关闭。该变更只迁移 V3.2-owned stores；V3.1 冻结的 `domain/contracts/canonical.py` 保持原字节。
- atomic audit bundle 全量回归曾出现 public exact-replay 假失败：持久化后的 directory 与 shard bytes/order 均未改变，实际差异只是新 loader 把内部 `layout/directory_binding/shard_bindings` 添加到旧 public mapping。修复把内部 `_load_audit_bundle_record` 与 public `load_audit_bundle` 分离：前者继续为二次 persist 提供 write-once binding，后者对 successor atomic 与 legacy exact layout 都只返回原始 `directory + shards`。unexpected file、partial legacy tail、symlink 和 write-once 冲突仍失败关闭。聚焦复测为 deterministic audit `4/4`、authorized revision layers `11/11`、local audit + prospective runtime `24/24`；另行扩展运行的 cycle-zero qualification audit 因当前共享工作树既有 `V32_PREFLIGHT_SUBJECT_IMPLEMENTATION_INVALID` 在 setUp 失败，与 audit replay 字节无关，未在本修复中扩大范围。
- delivery receipt schema 现强制 `current_codex_presentation_digest`。submit 在写入前重建 exact checkpoint/request/claim/package envelope 并与 caller 期望 digest 核对；qualification full replay 从 sealed CLAIMED snapshot 重建相同 envelope，再要求 digest 等于 delivery receipt。若 qualification mailbox checkpoint 已经是同一 CLAIMED 状态，composition 直接重建并返回相同 Presentation，不写任何文件、不推进 checkpoint、不取新时钟。prospective runtime 与 target wake 识别该 envelope 后直接返回，故 `1 MiB` 门测量的就是 Agent 最终收到的顶层对象，而不是内部子对象。
- 第六冻结树为 `107` 文件；按 `v32-terminal-tree-v1` 算法得到 whole-tree SHA-256=`419b9fb401d0f6be5e38c7dae6b5cb9f084ab7f656099c45ad4aad1962662830`，其中 104 个非锁文件摘要=`9ffabcc79a5ae4c77ac3c52b815c411d679497b1512026158bcce14ae2f4b321`，最后 mtime=`2026-08-09T14:24:24.062819Z`。该摘要不能与前五棵树曾使用的其他 project-relative/shell 排序口径混用。其余五棵树与用户副本继续只读；**在 10.25 当时**，第七资格只能在 V3.2.5 全量回归、显式提交及新 exact-pair 正式 post-commit receipts 后创建。

### 10.26 V3.2 fresh-process trace 接线候选

- `prepare_v32_qualification_from_committed_workspace_v1` 现以固定项目根、`/opt/homebrew/bin/python3.12`、完整 `PRODUCTION_ROOT_PATHS` 和新随机 nonce 调用 `collect_v311_fresh_process_trace_v2`；collector 使用 `-I -c` 独立子进程，校验 nonce、不同 parent/worker PID、空 stderr、roots 全包含，并返回 typed/self-digested `theory_paper_v311_fresh_process_import_trace_v2`。该调用发生在 composition 请求资格 System UTC 时钟和写任何 Phase-A authority byte 之前。
- `prepare_v32_qualification_authority` 不再接受未证明的路径列表冒充 fresh trace；它验证 typed receipt、exact roots、`completed_at <= workspace observed_at`，把 receipt write-once 发布到固定 `support/fresh-process-trace.json`，并以 `observed_project_python_paths` 参与 closure。runtime manifest 新增必需 `fresh_process_trace_binding`，closure policy 固定为 `EXACT_STATIC_AND_OBSERVED_FRESH_PROCESS_UNION_WITH_TRACE_RECEIPT_AND_PHYSICAL_SHA256`。
- runtime manifest 沿用同一个 schema family ID，但 strict router 只接受两种互不强转的形状：`1.0.0` legacy 或 `2.0.0` successor。旧六棵冻结资格树没有 `fresh_process_trace_binding`，只能按原 `1.0.0` 完整形状重放，不回填或合成 fresh receipt；新 `prepare_v32_qualification_authority` 只构造 `2.0.0`，并强制 physical fresh trace binding。未知版本、`2.0.0` 缺 binding，或 fresh trace chronology 不满足 `completed_at <= workspace.observed_at` 均失败关闭。
- full loader/actual-capability replay 必须从 owning qualification root 物理重开 trace receipt，核对 schema/self-digest、Python/nonce/PID/时序、根集合、observed paths、manifest binding 与文件 SHA-256；删改、交换、路径漂移或只提供静态 roots 均失败。当前 production closure 机械候选为 `43 roots / 194 recursively reachable local paths / 194 bindings`。
- **在 10.26 候选历史边界**，该状态应准确写为“代码接线候选已完成、正式资格仍 `UNKNOWN_NOT_QUALIFIED`”。它当时尚未经过该轮全量回归、显式 commit、post-commit receipts 和第七资格真实运行；不得把 collector 可调用、closure=`43/194/194` 或本地 replay 冒充 fresh-process 资格。第六资格在冻结 `e0c7d3d` 上的 `42/192/192` 及其失败树保持历史原样。

### 10.27 历史快照：`66197c4` 前耐久收口、五问题复核与全量结果

- 在该历史提交边界，五项理论质疑收敛为：Agent 主观判断三档 `off/probe/normal`，无连续 0–100 主观输入；typed 混沌/无方向状态零当前方向风险；每 instrument 全方向共享 24h reentry churn ledger；未来执行逃生舱不接入当前 pilot；依赖 identity 保留。该版本只证明 registry 自身 build/verify 的 closure 复用，后来发现 acceptance 外层仍重复四次，已由 10.30 的 owner-bound graph scope 修复；`24h` 始终仅指 reentry ledger，不代表固定同类证据归并。
- `v32_durable_json` 收敛为包级 shared owner，Application 与正式 Infrastructure/Authority 直接依赖 shared；旧 Infrastructure 文件只保留显式兼容导出。preflight gate 路径按 canonical 字典序冻结，production closure 保持 `43/194/194`，layer dependency、cycle-zero gate 重载与旧 V3.1 路径均通过。
- common/secure write-once 增加线程内串行、OS lock、清理异常聚合、主对象保护和 exact directory bundle。目录激活采用 anchored `renameatx_np(RENAME_EXCL)`；并发空 final/冲突 final 不被覆盖，不支持平台失败关闭。唯一完整 stage 可按 inode 与完整字节全集收养；不完整/不同的唯一安全 stage 清理重建；多个、非法、symlink、特殊对象或身份漂移一律失败关闭。
- Phase-A 新增外部 write-once intent：fresh process trace 先发生，随后一次取得并封存时间；runtime root 以整目录 atomic publish。响应丢失或 pre-rename 崩溃复用同一 trace/时间，完整 root 则先 full-loader replay，均不重复 fresh trace、时钟或 authority 字节。
- public source 的 attempt-only、raw-only 与 capture-present 崩溃前缀均封存 `V32_PUBLIC_SOURCE_LOCAL_CRASH_PREFIX_FAILED_CLOSED`，资格永久终止且不重试外部请求。mailbox 的 claim-only、delivery-only、delivery-receipt-pre-CAS、consumption-only、consumption-receipt-pre-CAS，以及 dynamic proposal/acceptance present-unbound tail 均只附着已验证首次字节并补原 CAS，零新网络、Agent 或时钟。
- audit narrative successor 改为单目录原子 bundle；完整 legacy layout 原 binding 路径保持重放，partial legacy 拒绝。内部 loader 保留 layout/bindings 给 persist 幂等，公开 loader 继续精确返回 `directory + shards`，避免实现 metadata 破坏应用合同。
- 首次从零 V3.2 全量得到 `735/737`，暴露两个组合缺陷：Application 反向导入 Infrastructure，以及 audit loader 泄漏内部 metadata。两项修复后又由 cycle-zero 聚焦发现 gate path 非字典序会在 canonical JSON 重载后误判，已排序并验证。最终从零 V3.2=`738/738 PASS / 1705.807s`（real `1706.23s`、user `1596.23s`、sys `90.28s`）；全 Theory Paper=`1505/1505 PASS / 2018.226s`（real `2018.83s`、user `1889.06s`、sys `105.65s`）。`compileall`、`git diff --check` 与用户副本摘要复核通过。
- 在 10.27 的提交前历史边界，用户保留副本仍为 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，不 staging、不删除、不修改。六棵历史 qualification 与旧 runtime 没有进入 diff；当时第七资格、target、正式 cycle/outcome 尚未创建。
- **在 10.27 当时**只可标记为“提交前本地工程门通过”。当时下一边界必须是显式提交，随后由新 exact qualification/target pair 运行固定 post-commit runner 并生成真实 receipts；fresh public source、当前 Codex、固定 outcome monitor 与 15 分钟实际时延仍为 `UNKNOWN_NOT_QUALIFIED`。预测增量、概率校准、成本后收益及跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

### 10.28 commit 66197c4、第七资格 EXPIRED_TERMINAL 与调度 burst P0

- 10.27 候选已提交为 `66197c47a1281340b4226da825da0b18d8815c3e`。第七 exact pair=`v32-qualification-btcusdt-20260809t215807z / v32-prospective-btcusdt-20260809t215807z` 的固定 post-commit runner 只执行一次：V3.2=`738/738 PASS`、全 Theory Paper=`1505/1505 PASS`、aggregate digest=`1eaa1571488194a60d68cce0c23b6d928e693b20deb1949a219ab687e775ebee`、network calls=`0`。Phase-A 与 fresh PUBLIC_SOURCE 随后成功。
- 第七资格完成 `15` 个 material roles、mailbox initialize 与 proposal enqueue；proposal packet=`568,876` bytes，只能确认本地 enqueue 前容量门与单一-envelope 构造路径未再次触发旧 1 MiB 错误。CURRENT_CODEX reservation=`2026-08-09T23:03:47.940793Z`，proposal request 时间=`2026-08-09T23:12:49.071891Z`，claim 被 `V32_ACTUAL_CODEX_PORT_ATTEMPT_EXPIRED` 拒绝；因此不能据此声称真实 delivery 已关闭。claim/delivery/probe/qualification completion/target authority 均不存在。
- 根因是 qualification composition 每次进程唤醒只调用一次 `materializer.advance_once()`。每一步本身保持 write-once，但反复进程启动和完整 authority replay 把内部 append-only 工作错误放大成约九分钟；这与 runtime support 已允许一个高层 wake 内最多 `64` 个 append-only 子阶段不一致。
- successor 修复只在 composition 增加有界 burst，不改变 materializer 单子阶段、不后移 reservation、不延长 `660s`。burst 在 `AWAITING_AGENT / READY / no-progress / QUALIFICATION_MONITOR_PROBE_* / exception / 64` 停止，并分别返回总 burst step 与真实内部 append-only 写入的计数/序列。只读终止检查和独立 probe 高层边界不混计为内部子阶段；probe schedule 后不再同 wake 推进 controller。
- 第七 controller 的真实状态是 `RUNNING/revision 3`，因此不追写、不伪称 `FAILED_CLOSED`。identity governance 新增独立 `EXPIRED_TERMINAL` pair，与六个 durable failed pair 共同 tombstone；第七 Q0–Q8 精确 digest 已加入 historical verifier，保证旧原件仍可离线重放。全部 qualification public APIs 与 target APIs 在 runtime/network/clock 前拒绝该 pair。
- 本节写入时 burst/tombstone/历史摘要兼容与测试仍是未提交候选；必须完成聚焦及全量回归、确认七棵历史树与用户副本不变、重新显式提交并运行第八 exact-pair post-commit receipts，才可再次尝试资格。市场预测增量、概率校准、成本后收益与跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

### 10.29 zero-eligible WAIT 与生产外层确定性夹具回归

- 第八资格交付预演发现相邻 P0：`WAIT` 行按合同没有自己的 evidence refs，而旧 Selection 理由只从 eligible risk candidate 的 dominance comparisons 取 refs。当混沌、无方向或客观硬门使 eligible risk 集合为空时，comparisons 依法也为空，合法 `WAIT` 会被 `V32_AGENT_SELECTION_REASON_REFS_EMPTY` 拒绝，形成“理论允许中性、实现却无法封存中性”的死路。
- 修复保留有方向候选时的既有 `WAIT_DOMINANCE_PROVEN_BY_SEALED_VARIANT`；只有 eligible risk 集合为空时才使用 `WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION`。理由引用不由 Agent 自填，而是从已封存 evaluation 中 blocked risk rows、已封存 plan 中 blocking refs，以及 market regime 的 evidence/counter/transition refs 取确定性并集。该路径不生成连续主观分数、不把 UNKNOWN 当零，也不强迫系统下注方向；reason code、comparisons 或 refs 被改写时，重建验证必须拒绝。
- 第一版聚焦证据曾得到 zero-eligible Proposal→evaluation→Selection→final plan `1/1 PASS / 31.723s`，以及方向 WAIT、篡改与 burst 停止边界 `8/8 PASS / 14.173s`。生产外层 composition 的确定性夹具测试也曾为 `1/1 PASS / 200.247s`，但独立复核发现它仍允许最多 80 次 outer advance，因此不能证明“reservation 后单次 wake”这一主张；该结果不是 fresh public network 或 Current Codex 资格证据。测试现改为先精确到 `ATTEMPT_RESERVED:CURRENT_CODEX`，随后 proposal 与 selection 各只调用一次 outer API，必须立即到对应等待点并满足 `burst_step_count>1`、controller revision 不越界和 `<660s`。修正后的生产外层组合接口确定性夹具测试为 `1/1 PASS / 199.278s`。
- 相邻复核还发现第一版 objective-zero-risk 正例在完整合约规格仍存在时，接受了 Agent 自报的 `COST_OR_LIQUIDITY + objective-reference-risk-inputs-unavailable`，会重新制造“永远 WAIT”的绕过路径。新硬门要求 zero-eligible 的每个原因要么由 Domain 从封存状态重建（事实完整性、path invalidation、极端不确定或 typed 非方向 regime），要么由 compiler 独立确认 frozen objective inputs 确实缺失且 refs 精确等于系统缺失诊断；churn 冷却必须由全 instrument ledger 证明。legacy dynamic `UNKNOWN_MAX_LOSS` 只关闭未来执行，候选 `block_reason=MAX_LOSS` 不得删除当前研究方向。完整输入下的伪阻断、GEOMETRY/泛化文字等软理由不得抹掉全部可比较方向候选，必须保留候选并走 WAIT dominance。缺失规格、zero-eligible 两类闭环、完整输入伪阻断拒绝及正常 directional WAIT 回归合计 `4/4 PASS / 38.792s`。
- 第三次构造发现 Agent 仍可在 ledger=`AVAILABLE` 时给一个 churn candidate 写入 `REENTRY_COOLDOWN_OR_BUDGET`，再用另一个真实硬门清空方向候选。Domain/compiler 现要求全 instrument churn 动作 `OPEN_PROBE/REENTER/REVERSE` 只能由真实 `COOLDOWN/EXHAUSTED`、非空 failure refs 且 candidate refs 与 ledger refs 完全相等来阻断；`AVAILABLE/RESET`、别名和 superset refs 均拒绝。最小 Domain/compiler 回归 `2/2 PASS / 7.966s`，真正 EXHAUSTED exact-ref 正例保留。
- 第四次复核发现合法路径被误杀：OTHER/UNKNOWN 残余假说达到 `HIGH` 时，Domain 会把 residual risk cap 确定性降为 `0` 并生成 `RISK_BUDGET_BELOW_CLUSTER_QUANTUM`，旧 compiler 却不承认这一 owning cause。现在首次构建与重建都要求 cap=`0`、risk-increasing candidate=`BLOCKED/CONDITIONAL`、无 blocking unknown、无 tranche，且 refs 精确等于候选 hypothesis source refs；compiler 只在完整 Domain plan verification 后承认。合法完整 Proposal、cap 非零伪造、错 refs 及将该原因用于 HOLD/REDUCE 的反例均通过。
- 第五次复核把问题从 zero-all 推广到每个候选：完整输入下，Agent 曾可只用自由 COST/GEOMETRY 文字屏蔽一个方向、保留另一方向 eligible，从而偏置选择和风险分配。当前 Domain 拒绝无 typed owner 的 feasibility block，compiler 对每个 blocked risk row 复核正式 packet，不再因仍有一个 eligible 方向而提前返回；没有 owner 的软判断只能进入 guard/rationale，不能删除候选。dynamic action plan 全模块与新增 compiler 聚焦合计 `47/47 PASS / 40.157s`；完整受影响模块与全量回归仍待完成。
- 上述仍是提交前候选证据。全量 V3.2、全 Theory Paper、七棵历史树与用户副本复核、显式 staging/commit 及 exact post-commit runner 尚待本轮完成；任何失败都会继续阻断第八资格。即使资格通过，也只证明当前 Codex 的本地耐久交付，正式 target 仍须独立验证 PIT、完整图依赖闭包与跨周期 continuity，不能把 qualification PASS 写成 Cycle 1 acceptance、预测增量或盈利证明。

### 10.30 V3.2.6 五项易碎性终审与当前候选边界

- **主观权重**：Agent-authoritative 连续主观风险数字已经退出主路径，只允许 `EXTREME_UNCERTAINTY/LOW/HIGH`。action-evaluation 中的连续 `risk_reference_units` 只是 sealed plan 已派生 allocation 的 exact echo，compiler 逐项重算；同一方向多个 cluster 只按该方向最高档确定总 cap，再在方向内部切分，新增同侧故事不能抬高方向预算。它仍是未校准研究确信档，不是概率、EV 或真实仓位比例。
- **复杂性与图重建**：dependency identity 不删除，因为它承担同源证据去重和旧行篡改检测；构造路径只处理 pilot 有界 working set/delta。公开图 verifier 使用 owner=(thread, async task) 的严格快照作用域。qualification materializer 的整个 bounded wake 持有外层 scope，内部 `advance_once` 只嵌套使用；相同 snapshot 可由 projection/registry/market-view 复用，append 改变 snapshot key 后自动重建。失败、caller mutation、custom Mapping、scope 退出或跨 wake/thread/task/process 均不复用，不存在跨周期全局图缓存。
- **混沌可表达性**：`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 保持零当前方向风险。任何非方向风险候选必须 `CONDITIONAL/BLOCKED`、无 tranche，所有非空 zone refs 必须逐项解析为已封存 `BREAKOUT_BOUNDARY`；合法 zero-eligible 状态可用 `WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION` 完成 Selection，而不是伪造多空下注。Domain 已自动派生唯一上下 research trigger pair：15m confirmed close、LONG strict `GT upper`、SHORT strict `LT lower`、最早 expiry 与 first-match retirement。一次命中只要求 fresh reanalysis；连续 monitor、订单和 OCO 均未实现，因此仍不能称为自动双边突破交易策略。
- **重入磨损**：现行可构造预算精确为 per-attempt `<=1`、max attempts=`2`、cumulative `<=2`、consecutive failures=`2`、window=`24h`。首次 INACTIVE probe 免费但立刻进入 `INITIAL_PROBE_USED`；之后的 OPEN/REVERSE 可以纠偏，但必须在下一 durable transition 精确增加 attempts 与 selected reference risk，不得免费重放。首次 stop 直接计 failure=`1`，再一次失败即熔断；同 instrument、全方向和 `OPEN_PROBE/REENTER/REVERSE` 共用账本。`ReentryObligation` 仍只是复核机会，不强制开仓。
- **仓位研究血缘**：风险候选假说必须精确等于同方向 actionable cluster closure，不能夹带反向故事。sole reference parent 持久绑定 ID、方向、entry、stop、support closure、zones 和 `valid_until=min(plan expiry,candidate horizon,time stop)`；到期先退休，ADD/REVERSE 新 ID 不得复用 parent。generic source/support/renewal/tier/zone observation 不能被重新解释为失败，只有 exact parent 的 fresh opposing ref 或 active typed invalidation 可触发 failure transition。该对象仍只是单 parent research intent，不是 fill/position，也不宣称完整多 tranche portfolio/pyramid ledger。
- **物理逃生边界**：current research 的合约/压力输入缺失由 compiler-owned `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 处理；legacy `UNKNOWN_MAX_LOSS` 和权限未知只关闭未来真实执行，候选自报 `MAX_LOSS` 删除当前研究方向会被拒绝。未来 `EmergencyExecutionCapsule` 明确为 `NOT_IMPLEMENTED_NOT_QUALIFIED`，当前 read-only recovery observer 不是 execution risk supervisor。必须另行取得执行授权，并完成真实 position truth、venue-native protection、reduce-only reconciliation、fill/latency/chaos 资格与 unresolved-exposure 告警后，才可讨论实现；仍不得承诺成交或无滑点清仓。
- **新风险证据所有权**：`ADD/REENTER/REVERSE` 和其他 eligible 新风险必须由本轮 cutoff 之后当前 PIT 可得、方向支持为正且被该 hypothesis `supporting_refs` 实际引用的新证据支撑；仅有新反证、无关新 datum、旧 evidence 或 Agent 自报引用均不得解锁。没有 fresh positive support 时走 exact `NO_NEW_CURRENT_PIT_EVIDENCE_REF`，不能生成 tranche。FACT 也必须由真实 UNKNOWN PIT datum/source UNKNOWN/具体 request/citable closure 拥有，不能用自签文本制造。
- **当前验证边界**：五问题、typed trigger 与 lineage 聚焦=`114/114 PASS / 88.708s`；414-bar/双 Agent-stage 资格端到端修正复跑=`1/1 PASS / 279.361s`；从零完整 V3.2=`779/779 PASS / 1596.797s`；正确全口径 `test_theory_paper*.py`=`1546/1546 PASS / 1887.454s`；compileall 与 `git diff --check` 通过。第一次完整 V3.2 运行在 779 项中的唯一错误是测试本地 `boundaries` 列表未初始化，生产路径未失败；补变量后单项与全量均从零通过。exact commit/post-commit runner、fresh Current Codex、fixed monitor 与真实 15 分钟端到端仍待后续边界；预测增量、概率校准、成本后收益和跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

### 10.31 commit cd011ad、第八资格并发失败与 composition owner P0

- 10.30 候选已提交为 `cd011ad1aee9c0e3ea995746ce2eec51ddbef3ca`，tree=`937d5a2de67aad38d268ac1c4025ce6df80e6b42`。该提交的固定 post-commit runner 仅运行一次：V3.2 `779/779 PASS / 1586.769s`，全 Theory Paper `1546/1546 PASS / 1865.004s`，aggregate digest=`c7fb9dfb7ff6d10c6925865f694b55fde621aff940316dc100f3281fb71e4eaa`，网络调用为零。
- 第八 exact pair=`v32-qualification-btcusdt-20260810t063618z / v32-prospective-btcusdt-20260810t063618z` 完成 Phase-A、PUBLIC_SOURCE 唯一 attempt 与 CURRENT_CODEX reservation。第一次 materialization 调用超过外部工具的初始 yield 后仍在运行，但调用端没有继续轮询原 session，而是启动第二个 `advance`。这是编排错误，同时揭示 production P0：material、mailbox、controller 的局部锁之间没有 qualification-wide composition owner。
- 后发进程先以 `V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID` 写入 materialization failure 和 controller revision `4 / FAILED_CLOSED`；先发进程随后继续写入 `proposal_input`、mailbox checkpoint 与 proposal request。failure receipt 固定 `material_predecessor_count=14`、`mailbox_prefix_status=VERIFIED_EXACT`，已不能描述后续交错形成的真实磁盘前缀，full replay 因 `V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID` 拒绝。该历史不能修补；Agent claim/delivery、monitor、target authority/genesis/cycle/outcome 均为零。
- 第八 qualification/target 已加入第七个 durable failed identity pair；连同第七资格的一个 expired pair，历史终态总数为八。其原 Q0–Q8 typed subject digests 已逐项冻结到 historical verifier，确保 tombstone 后仍能按原字节只读验证，而 arbitrary self-digested replacement 继续被拒绝。
- 修复新增一个 qualification 外部、每 identity 唯一的 composition lock：路径为 `.runtime/v32/qualifications/.composition-locks/<qualification-id>.lock`，与 qualification roots 为 sibling 并位于既有 qualifications 忽略边界内。锁前只验证 Phase-A 已创建的 lexical root components，避免深扫首进程正在发布/删除的临时对象；锁后完整重放 namespace 和 authority。`advance / claim / submit / finalize` 四入口使用同一线程锁与 OS `flock`，等待者只能从前一调用完整 successor 继续。
- sibling-lock 版本的聚焦回归=`13/13 PASS / 20.162s`，资格材料化模块=`28/28 PASS / 504.763s`，授权全回放模块=`29/29 PASS / 26.593s`。它们实际证明 advance 与 submit 不重叠、等待方只观察 revision `1` successor、四个公开入口共享同一 guard、独立 Python 进程之间互斥、业务 ValueError 不被改写为锁错误、第八 tombstone 在 live API 前生效、真实第八 controller/failure 字节保持只读，以及第八 Q0–Q8 历史 subject 可完整验证。追加事故物理前缀断言与锁路径常量派生后，最小复核=`6/6 PASS / 0.716s`，最终完整 V3.2=`785/785 PASS / 1596.369s`，正确全口径 `test_theory_paper*.py`=`1552/1552 PASS / 1886.760s`。显式提交和全新第九 pair 仍须在后续边界完成；当前修复仍是提交前候选，绝不能用于续跑、修补或重放第八 pair。
