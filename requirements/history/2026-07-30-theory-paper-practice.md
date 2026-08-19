# 理论演化、系统修复与实验实践需求记录

> 路径绑定的历史需求正文。当前有效需求只读取 `requirements/CURRENT.md`，历史摘要见 `requirements/history/INDEX.md`。
> 本文件不再追加或改写；旧模板解除路径依赖后，正文整体移入 history。

## 2026-08-10 当前主线：先简化运行时，再恢复 V3.2 实验

### 用户最终需要的交付结果

在不修改 V3.2 理论基线、不扩大交易权限的前提下，先形成一份可执行、低耦合、低重复成本的运行时修复方案；随后只实施能让唯一 `BTC-USDT-SWAP`、公开数据、local、non-executable 前瞻实验真实走通的最小切片。任何外部数据或网络缺口必须及时停止无效尝试，明确告知人工获取方法、免费合法来源和不可替代边界。

### 验收标准

1. 正式实验前关闭三个已证实的 target P0：source/decision 时序倒置、任意秒决策与 outcome 监测格点冲突、过宽限期 schedule 无耐久终态而永久重选。
2. 生产组合测试必须使用非整刻真实时钟并分离四个时刻：source cutoff、实际 admitted_at、permit_opened_at、由 selection compile receipt 封存的 decision_sealed_at；15m outcome 从 decision_sealed_at 起保留精确 elapsed horizon，过期 outcome 零网络且只封存一次 coverage loss，进程重载后不重复写入或联网。
3. Presentation 不再拥有业务校验和跨 store 状态机；Application 只通过窄端口调用现有 collector/store/mailbox。第一阶段不新建事件总线、插件 SDK、双存储平台或全仓迁移。
4. 显式接入 strategy revision reader；无人工/修订输入时写入 typed `NO_REVISION_INPUT/UNKNOWN`，不得以静默空列表冒充“没有缺口”。
5. 增加只读 status 入口，直接返回当前边界、下一合法动作、Agent 阶段、outcome due/expiry；不得以盲目轮询或重复调用推进状态。
6. 本地开发验证分层运行，不在每个局部修改后跑全量。为避免本轮再扩大 qualification 协议，修复提交仍只执行一次现有 write-once 双 suite 正式门；测试 ID 分区去重作为 Cycle 1 后的独立严格超集迁移，不与三个 P0 同批实现。
7. 新代码提交后先做一次非授权、标准系统网络栈的真实 transport smoke；失败即停止并报告。只有本地组合链、transport smoke、fresh qualification 全部通过后才可创建 target run。
8. 理论继续允许 Agent 动态新增、削弱、替换和到期假说，选择多、空、中性、混沌、WAIT 或条件 probe；硬限制只保留事实时间、权限隔离、单写者/幂等耐久性和研究风险上限。
9. collect→qualify→admit→replay 必须在同一个 `SOURCE_READY` 外层边界内有界推进，保留 write-once 子阶段和 partial-prefix 恢复，但不得拆成多个五分钟唤醒消耗 900 秒 freshness。正常下一次唤醒再开 ANALYSIS permit。若进程长时间中断使已经封存的 prepared source 在 permit 前过旧，当前 Phase 1 必须零 Agent、零第二网络失败关闭；不得在同一 cycle 的固定 write-once admission 身份下偷偷替换 source。selection compile 后才发现过旧同样必须 `SOURCE_STALE_AFTER_AGENT / FAILED_CLOSED`，不得自动重采、重跑或消费第二次 Agent attempt。

### 当前范围与明确不做

- 当前范围：修复/简化计划、三个 P0、一个 P1（显式 revision input）、只读状态、分层本地测试、一次现有正式双 suite 门、一次 fresh qualification 和随后唯一 target Cycle 1。
- 当前不做：再次修改 V3.2 理论、概率校准结论、成本后收益结论、跨 regime 泛化结论、portfolio/reentry 实际执行、paper/live/账户/订单/凭据/资金、通用事件总线、通用插件平台、全仓一次性迁移。
- 旧 V3.1、s3、E0/E0B 和八份失败/过期 V3.2 qualification 继续永久封存，不恢复、不修补、不复用身份。

### 当前主要任务与状态

| 状态 | 任务 |
|---|---|
| 已完成 | 只读映射 target 主链、三项 P0、P1、巨石模块、冻结闭包和测试重复成本；形成最小 strangler（旁路替换）方案。 |
| 已完成 | commit `9f5dba41fefd3759810af305b23865998110552a` 的一次性旧门回归：V3.2 `785/785`、全 Theory `1552/1552` PASS、零网络；总历时约 59m53s。该收据只证明旧提交，不得进入新资格。 |
| 已完成 | 完整修复设计已冻结到 `V3_2_RUNTIME_REPAIR_AND_SIMPLIFICATION_PLAN_2026-08-10.md`，并同步系统入口和实施日志。 |
| 已完成 | 三个原始 P0、revision-input P1 与只读 status 候选实现；并关闭 active permit registry/permit 损坏、跨 grace 网络闸门、terminal reload、typed post-Agent stale 与 aggregate crash-reload 等同族缺口。 |
| 已完成 | 分层本地验证：source partial-prefix 仅一次网络；local-analysis 8/8；Supervisor/cycle 25/25；prospective runtime 28/28；read-status 4/4；非整刻四时钟经真实两阶段 Agent 后到 Supervisor READY；expiry 新实例重载零第二写/网络。 |
| 已完成 | 提交前静态边界：34 个变更 Python 文件均可解析，`git diff --check` 通过，未发现冲突标记、凭据或正向账户/订单/可执行交易开关；用户副本保持 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c` 且不进入 staging。本次提交用于冻结该 release slice。 |
| 已完成 | 提交 `f881e2ca4f11378f1ce610261aec3117c4a31270` 的正式门在第一套 V3.2 discovery 后失败关闭：`816` tests、`18` errors、`3` failures。21 个表象已归并为三项旧回归漂移并以 4 个测试文件最小修复：source admitted/cutoff 顺序、cycle-zero SOURCE_READY 夹具、closure `194→196` 及两个新增关键路径显式可达。对应聚焦 `25` 项通过；生产代码零改动，原 exact pair 永久不重试。 |
| 已完成 | 回归治理已提交为 `065d4addd9a2cf6e58cbc1efb1e0db8b9538432e`；全新 exact pair `v32-qualification-btcusdt-20260810t134909z` / `v32-prospective-btcusdt-20260810t134909z` 的 write-once 双 suite 均通过：V3.2 `816/816`、全 Theory `1583/1583`，零网络，aggregate digest=`b8a6da79da8989bfda9c4cbd3eeb9ce7adc1219349811ca55a485e0ee09b6a96`。 |
| 已完成 | 标准系统网络栈的一次性非授权 transport smoke：`GET https://openapi.okx.com/api/v5/public/time`，单请求、无重试、无凭据、HTTP 200；该结果只证明当时公开路由可达。 |
| 已完成（失败关闭） | 上述 qualification 完成 Phase-A、唯一 PUBLIC_SOURCE、Proposal 请求/领取/交付和 Selection 请求；Selection 领取时 CURRENT_CODEX 总窗口已过期，controller revision `4 / FAILED_CLOSED`，failure digest=`3e6912a49fa31cd1f92406a78223b2cbcbd33369bf1fadc92c6d2bcf285c69b2`。该 exact pair 永久不重试、不复用；未创建 target authority、genesis、cycle 或 outcome monitor。 |
| 已完成（Phase-A 失败） | 新提交 `44fab8a6978656c0b2c91e4c0e7a611808920403` 的 exact pair `v32-qualification-btcusdt-20260810t151431z` / `v32-prospective-btcusdt-20260810t151431z` 完成 write-once 双门：V3.2 `816/816`、全 Theory `1583/1583`、零网络；随后 prepare 在写入任何 qualification runtime/authority 前以 `V32_LIFECYCLE_CHRONOLOGY_INVALID` 停止。sealed Phase-A intent 中 `manifest_created_at == qualification_gate_evaluated_at == 2026-08-10T16:15:42.648507Z`，违反既有严格 `<` 合同；该 pair 永久不重试、不改 intent。 |
| 已完成 | Phase-A/Phase-B 的两处 write-once 时钟生成已改为有界重读真实 System UTC，精确保持原 `<=`/`<` 语义链；无法前进时在持久化前失败关闭。未合成 `+1µs`、未放宽 chronology、未改全局时钟或旧 intent。近期三个已永久终止 exact pair 已纳入现有静态 tombstone；已有 Q0–Q8 工件的 CURRENT_CODEX 过期 pair 同时精确登记九份原历史摘要，保留“可审计、不可重启”。时钟/恢复模块 `31/31` 与墓碑/重入/历史回放聚焦回归 `3/3` 通过。 |
| 未开始 | 新 exact pair 的 qualification、target Cycle 1 与固定 outcome monitor。 |
| 受阻 | 无人工阻塞。人工数据不是 baseline 前置条件；可选 FRED key、Google Trends/CFTC 文件只能在 importer 与 revision reader 完成后接入未来 cycle。 |

### 需求变更记录

- 2026-08-10：用户要求停止以资格运行充当调试器，先完整设计；减少层层耦合和重复验证；外部设施连续失败时停止、人工协助或换方向；理论在正式实验前保持宽松和 Agent 自主。
- 2026-08-10：正式实验继续暂停。已启动但尚未进入 qualification 的 post-commit runner 自然完成后被隔离为旧提交测试事实；没有调用 prepare/advance/finalize，没有创建 target authority、target genesis、cycle 或 outcome monitor。
- 2026-08-10：实现复核发现第一版候选又把 qualification、admission、replay 拆成三次外部 wake，五分钟 cadence 会在第四次开 permit 前耗尽 900 秒 freshness；同时 Supervisor 仍要求 successor schedule decision 等于 legacy source cutoff。修复收敛为一个 SOURCE_READY bounded burst，并对 admission v1/v2 显式分派 legacy/source-cutoff 与 successor/decision-sealed 时钟。没有采用同 cycle 自动重采：现有 admission 路径按 cycle 固定且 write-once，加入多代 source 身份会扩张整条 acceptance/continuity/runtime closure；Phase 1 对罕见的长中断 stale prefix 保持零 Agent、零第二网络失败关闭，未来只有真实实验证明高频发生时才设计 generation successor。
- 2026-08-10：Phase 1 候选完成分层验证。Outcome expiry 使用一个聚合 typed terminal，而非复制 intent/receipt/batch 第二套框架；48 个 expiry row 的共享材料投影约 126 KB，与现有 cycle-2 packet 粗合并约 458 KB，低于 1 MiB。active permit 若损坏、跨宽限期或绑定 registry 损坏，均在网络前一次失败关闭；后续 wake 在读取损坏 registry 前返回既有终态。read-status 不实例化会落锁的 stores，而是双读所有 mutable heads，变化即 `BUSY_UNSTABLE`。正式实验仍未开始。
- 2026-08-10：提交前静态边界完成；本次只冻结 Phase 1 最小修复及相邻回归，不修改理论，不纳入用户副本，不创建 qualification/target，也不访问网络、账户或订单。提交后的唯一下一门是 write-once 双 suite。
- 2026-08-10：新 exact pair `v32-qualification-btcusdt-20260810t131414z` / `v32-prospective-btcusdt-20260810t131414z` 只调用一次 post-commit runner；第一套 `V32_FULL_DISCOVERY` 在 `816` tests 后以 `18 errors / 3 failures` 写入永久失败收据，未运行第二套、未 prepare/advance、未联网、未创建 target。该 pair 不重试。修复范围限于把已变更合同同步到遗漏的旧回归夹具与精确 closure 断言；若聚焦复现显示生产错误，再单独扩大，不逐测试打补丁。
- 2026-08-10：失败收据独立复核确认 21 个表象只有三项共同根因，没有该收据直接证明的生产语义缺陷。最小同步后 source replay `14/14`、cycle-zero `4/4`、closure `5/5`、actual-capability 精确失败方法 `2/2` 通过；closure 同时显式要求 `v32_outcome_window_expiry.py` 与 `v32_read_only_status.py` 可达，避免只更新魔法计数。
- 2026-08-10：提交 `065d4ad` 的第二个 exact pair 完成两套正式回归和单请求 OKX transport smoke，但 CURRENT_CODEX qualification 在 Selection claim 前永久失败关闭。耐久时序显示 reservation→proposal request=`95.010892s`、proposal request→claim=`60.644029s`、claim→proposal delivery=`372.741112s`、proposal delivery→selection request=`85.437411s`；Selection 入队时总预算只剩 `46.166556s`。本次不修改理论、不扩大 `660s`、不后移 reservation，也不把 qualification PASS 冒充 target；下一批次先消除领取后的人工探索和重复工具往返，以原 `120/180/90/180/90` 阶段预算验证真实快速交付。
- 2026-08-11：第三个 exact pair 的双门通过后，Phase-A 真实 System UTC 在两个连续语义阶段返回同一微秒，导致 `manifest_created_at < qualification_gate_evaluated_at` 严格门失败。fresh trace 完成时间早于 workspace observation，其他时序均合法；未创建 qualification runtime、authority、source attempt、Agent 或 target。同族裸取钟还出现在 Phase-B 的 `retired_at < target_gate_evaluated_at`，因此用一个窄 helper 在两个生成点按原语义链有界重读真实时钟；不重试该 pair，不修改 chronology 合同、全局时钟或旧 intent。

完整设计入口：`V3_2_RUNTIME_REPAIR_AND_SIMPLIFICATION_PLAN_2026-08-10.md`。

2026-08-10 第八资格并发故障与新增 P0 验收：提交 `cd011ad1aee9c0e3ea995746ce2eec51ddbef3ca` 的固定 post-commit V3.2 `779/779` 与全 Theory Paper `1546/1546` 均 write-once PASS、零网络调用；第八 exact pair `v32-qualification-btcusdt-20260810t063618z` / `v32-prospective-btcusdt-20260810t063618z` 完成 Phase-A、PUBLIC_SOURCE 唯一 attempt 与 CURRENT_CODEX reservation 后，调用端把超过单次工具 yield 的仍在运行 materializer 误判为已完成并发起第二次 `advance`。两个进程缺少 qualification-wide composition owner：后发进程先封存 `V32_QUALIFICATION_MATERIAL_BURST_BOUNDARY_INVALID`，先发进程随后又写入 proposal mailbox，最终使 failure receipt 的 `material_predecessor_count=14` / 空 mailbox inventory 与实际 `proposal_input`、request/checkpoint 前缀不一致，full replay 报 `V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID`。该 pair 永久失败且不得重试、推进、修补、删除或重签；未发生 Agent claim/delivery、monitor、target authority/genesis/cycle/outcome。新增验收：所有 qualification `advance / Agent claim / Agent submit / finalize` 必须共享一个 run-scoped、跨线程且跨进程的 composition guard；并发第二调用只能在同一锁后看到首调用的完整 durable 边界，不能与 material/mailbox/controller CAS 交错，不能生成不自洽 failure evidence。修复后须以并发回归、完整双回归和新提交证明，再使用全新第九 pair；第八 pair加入永久 tombstone。

2026-08-10 第八事故修复候选收口：四个 Phase-A 后公开写入口现共享 qualification identity 级线程锁与 OS 排他锁；锁位于每个运行根之外的既有 ignored sibling namespace，锁前仅验证词法根组件，锁后才完整重放 namespace 与 authority。第八 pair 已成为第七个 `FAILED_CLOSED` identity，连同第七资格的 `EXPIRED_TERMINAL` 共八组永久 tombstone；其 Q0–Q8 原 subject 可逐项只读验证，但完整 runtime replay 必须继续以 `V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID` 拒绝。最终候选回归为 V3.2 `785/785 PASS / 1596.369s`、全 Theory Paper `1552/1552 PASS / 1886.760s`；在显式提交与全新第九 pair 产生前，仍不得声称 Current Codex、monitor 或 target 已资格化。

状态：历史 V1、seen-V1、OKX、s3、E0/E0B 均按既有裁决冻结；项目仍无预测有效、成本后 alpha、校准、盈利或生产就绪证据。唯一 V3.1 public/non-account/local/non-executable `BTC-USDT-SWAP` 前瞻实验 `v31-prospective-btcusdt-20260806t183742z` 完成 `1/8` 个 accepted cycle 后，在 Cycle 1 唯一 outcome 请求中因 `V31_OUTCOME_PUBLIC_VALUE_INVALID` 永久 `FAILED_CLOSED`；attempt=`1`、outcome=`0`、`resume_allowed=false`，不得重试或推进 Cycle 2。账户、paper/live、订单、凭据和资金权限始终为零。
V3.2 第六资格历史状态（已由第七资格事实 superseded）：post-commit 收据与完整 Phase-A 重放修复已提交为 `e0c7d3da4e0809fd21b0d241db84e0c17155d4ff`。第六资格 `v32-qualification-btcusdt-20260809t131915z` 在该 exact commit 上完成两份 write-once post-commit PASS 收据、Q0–Q8/全部 support/`42 roots / 192 paths / 192 bindings` 完整重放及唯一 PUBLIC_SOURCE attempt；CURRENT_CODEX attempt 只预留一次，材料化在 `CONTEXT_PACKAGE:PROPOSAL` 以 `CONTEXT_CAPACITY_UNRESOLVED` 永久 `FAILED_CLOSED`。终态为 controller revision `4`；已有 `14` 个精确 material predecessors，`proposal_packet` 已封存，但 `proposal_input`、mailbox request/claim/delivery、monitor schedule/probe、qualification retirement、target authority/genesis/cycle/outcome 均不存在。第六 qualification/target exact pair 不得重试、推进、改写、删除、重签或由修复后代码续跑。
第六资格当时的根因与修复目标：真实 proposal canonical packet=`559,522 B`，仅因旧 proposal 子门=`512 KiB` 被迫分片；同一完整 packet 若直接 INLINE，完整 Agent input=`562,654 B`，低于既有总输入硬门=`1 MiB`，且 Agent view=`187,641 B < 256 KiB`。旧分片把 `12,709` leaves 投影为 `12,712` members、`121` shards、合计约 `7.79 MB`，selection 又重复保存 `1,807` 个 policy roots，达到约 `306,980 B > 262,144 B`，形成第二个人工断崖。进一步只读重建确认旧实际 Presentation 将同一 packet 复制三次并达到 `1,687,318 B`，而 qualification/target 在发现这个超限前已经 claim。修复不得删理论、bars、evidence、UNKNOWN/OTHER 或无限抬高阈值；应取消没有独立物理依据的 stage packet 子门，把当前 pilot 固定为 `INLINE_ONLY` 并保证正文只出现一次，在任何 mailbox/material/checkpoint 写入及 claim CAS 前精确测量最终 checkpoint/request/claim/control/document envelope。`SHARDED` 仅为未来未资格化能力，当前 successor 不得使用。该目标后来进入提交 `66197c47a1281340b4226da825da0b18d8815c3e`，并由第七资格验证到 proposal request 边界。

第六资格后、提交 `66197c4` 前的历史候选范围又增加并完成代码接线：四个 mailbox exact-tail（request、claim、delivery/receipt、consumption/receipt）只能复用首次不可变对象、时间与 predecessor 补原 CAS；V3.2-owned durable writer 必须先完整写入同目录私有临时文件并 `fsync(file)`，再不可覆盖地原子发布并 `fsync(parent directory)`，且不得修改 V3.1 冻结的 `domain/contracts/canonical.py` 或其使用者。CAS 后 response-loss 的 enqueue/claim/submit 只能返回已提交的 `REQUESTED/CLAIMED/DELIVERED` exact successor，零第二写、零新时钟、零第二 Agent。delivery receipt 必须在 `current_codex_presentation_digest` 保存实际 `CurrentCodexPresentationEnvelope` digest，qualification full replay 从 CLAIMED 快照重建核对；最终 Agent-facing 对象直接为 `<=1 MiB` 的单一 envelope，hot path 严格 `INLINE_ONLY`，超限立即失败，`SHARDED` 只属于 future-unqualified。真实 fresh-process collector 也必须在任何 Phase-A authority byte 和资格 System UTC 时钟前运行，typed receipt 以物理 SHA-256 进入 support、manifest/runtime closure 和 full loader。同一 runtime-manifest schema family 只允许严格 `1.0.0` legacy 与 `2.0.0` successor：旧六树无 fresh binding 仍按原 `1.0.0` 重放且不得补造；新 prepare 只生成 `2.0.0` 并强制 physical fresh trace 与 `trace.completed_at <= workspace.observed_at` chronology。该候选机械闭包为 `43 roots / 194 reachable paths / 194 bindings`；第六资格冻结的 `42/192/192` 仍是历史事实。

V3.2 当前状态：提交 `66197c4` 的固定 post-commit 双回归、Phase-A、真实 fresh-process 与第七资格唯一 fresh PUBLIC_SOURCE 已通过；第七 exact pair 随后因逐对象外部唤醒在 claim 前耗尽 `660s` CURRENT_CODEX 窗口，治理状态为 `EXPIRED_TERMINAL`。其原件保持 controller=`RUNNING/revision 3`、proposal=`REQUESTED`、claim/delivery/probe/retirement/target/outcome 均不存在，不追写为伪 `FAILED_CLOSED`。六个 durable failed pair 与一个 expired pair 共同形成七组永久 tombstone。当前 bounded material burst、第七历史兼容治理和 zero-eligible WAIT owning-cause 加固为未提交候选；下一次只能由新 commit 和第八 exact pair 验证。fresh-process 与 fresh public source 已有第七实际证据；当前 Codex 耐久交付、固定 monitor 和真实 15 分钟时延仍为 `UNKNOWN_NOT_QUALIFIED`。

2026-08-09 用户新增“五个紧箍咒”复核：五项方向判断中，连续 0–100 主观权重、非方向混沌遗漏、自动 reentry 磨损和理想化物理退出均是有效风险，但当前 V3.2 已分别采用 `EXTREME_UNCERTAINTY/LOW/HIGH` 三档上限、typed `NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 零方向风险、单 instrument/全方向 `24h + max_attempts=2 + per_attempt_reference_risk<=1 + cumulative_reference_risk<=2` churn ledger，以及 future-only `EmergencyExecutionCapsule` 合同。当前 pilot 没有仓位或订单权限，故不得伪造“市价核按钮”；未来执行层只有在独立授权、真实仓位真值、venue 原子保护/降级退出、最终 position reconciliation、外部告警与 chaos 资格全部通过后才可能实现逃生舱，仍不能保证成交或无滑点清仓。完全删除 dependency identity 的建议不采纳：它会让同一价格事实被五个故事重复放大风险；当前正确优化是 pilot 有界 working set、delta 增量构造，以及一个 owning acceptance verification scope 内对同一不可变 projection 只完整重建一次当前 closure。不存在已实现的固定 `24h` 同类证据归并；本文相关 `24h` 只属于 reentry churn ledger。

2026-08-10 本轮用户要求继续审查并关闭五项易碎性风险，而不是以既有文档声明代替实现。新增验收边界为：同方向 cluster 数量不得放大方向总预算；正风险 `ADD/REENTER/REVERSE` 只能由前序状态之后新出现、当前 PIT 可引用且位于 supporting refs 的证据解锁；候选不得自报 FACT/MAX 数值制造或删除风险；无方向 regime 下的风险候选必须绑定 typed `BREAKOUT_BOUNDARY` 且保持 `CONDITIONAL/BLOCKED/zero-risk`，不冒充已经挂出的双边订单；reentry 的两次机会必须各自不超过 `1`、累计不超过 `2`，并满足量子/次数可构造性；当前研究 reference-loss 不可得只阻止当前正 reference-risk，未来真实 execution max-loss 不可得只阻止未来执行，不能单边删除当前研究方向；future escape capsule 必须明确标记 `NOT_IMPLEMENTED_NOT_QUALIFIED`，且当前 recovery observer 不得冒充 execution risk supervisor。验收热路径还必须证明同一 acceptance scope 内相同 projection 的完整 closure 只重建一次，scope 外、失败、caller mutation、custom Mapping 或不同线程/task 均不得复用。上述项目在完整回归、显式提交和新 qualification 前均为未提交候选，不得写成已资格化能力。

2026-08-09 post-commit regression receipt 新增阻断：手工终端输出和 tracked 文档中的 `657/657`、`1411/1411` 只能作为当前会话证据，不能作为机器可重放 authority evidence，因为把 post-commit 结果再写回同一 commit 会形成自引用。修复必须采用 commit 后、qualification authority 前的独立 ignored/write-once evidence namespace：固定 production runner 只允许完整 `test_theory_paper_v2_v32*.py` 与完整 `test_theory_paper*.py` 两个 suite ID，绑定 exact branch/commit/tree、Python/runtime、固定 discovery argv、started/completed、exit/status/counts、完整 bounded stdout/stderr bytes 与 SHA-256、attempt=`1/retry=false`；任一缺失、失败、超限、commit/worktree 漂移或已预留未完成都永久拒绝该 qualification ID。两份 PASS receipt 必须被聚合为 support document，并由 WorkspaceFreezeReceipt v1.1、manifest、qualification authority、target authority和 full loader 物理重开；测试源码路径、聊天说明或普通 64-hex 不能替代执行收据。旧 v1 receipt 只读兼容仅用于历史重放，不得生成新的 V3.2 qualification。

2026-08-09 post-commit 收据追加验收：固定 runner 还必须清洗 caller `PATH/GIT_DIR/GIT_WORK_TREE/PYTHON*`，使用绝对 Python/Git 入口、`-I` 与固定 `-t .`；子进程输出各有物理上限，直接进程提前关闭管道、后台进程留存、输出超限、超时、中断和读取失败必须有界终止、保留已捕获前缀并写入 typed `runner_outcome`，不得无界等待或以空输出冒充完整。两套 suite 顺序固定为 V3.2 先、全 Theory Paper 后，时间必须用 UTC datetime 比较且前者 `completed_at <=` 后者 `started_at`，不能使用 ISO 字符串词典序。更重要的是，qualification 在 prepare 后的每次 `advance / Agent claim / Agent submit / finalize` 都必须在任何网络、materializer、mailbox、probe 或写入前重放 legacy predecessor、approval/theory bytes、contract、manifest、qualification phase/authorization、Q0–Q8 gate/subject、全部 support、完整 runtime closure 与 post-commit 原件；任一删改都要求副作用计数为零。

2026-08-08 历史更新（已被后续资格事实 superseded；本段只保留当时状态）：第一版 V3.2 已提交为 `d5478d9463961a65d7167642c0c67e6c275f6ebf`；第二轮系统修复与证据日志提交为 `294bc26`、`08b6dff`，当时 HEAD 的 V3.2 `589/589` 与全 Theory Paper `1274/1274` 均通过。随后资格 `v32-qualification-btcusdt-20260808t220933z` 在 PUBLIC_SOURCE 唯一物理尝试中收到 `https://www.okx.com/api/v5/public/time` 的 Cloudflare HTTP 403 并永久 `FAILED_CLOSED`，attempt=`1`、CURRENT_CODEX/monitor/target authority/genesis=`0`；raw body、status、final URL 和 no-retry failure receipt 均已封存。该段只保留当时谱系，不表示当前仍只有一份或两份失败资格。

2026-08-09 第三资格历史更新（已被后续资格事实 superseded；本段只保留当时状态）：五项易碎性修复、OpenAPI 单主机迁移、Phase B intent 恢复、Target Agent 固定入口与 raw/capture 失败原子性已在 commit `05699eb9ce353dff4c2df09328feb5b22e1b6735` 完成，exact HEAD 的 V3.2 `616/616` 与全 Theory Paper `1301/1301` 通过。第三个全新资格 `v32-qualification-btcusdt-20260809t010844z` 只推进到 PUBLIC_SOURCE 第一次服务器时间请求，即从 `https://openapi.okx.com/api/v5/public/time` 收到 Cloudflare HTTP 403 并永久 `FAILED_CLOSED`；raw/capture/typed failure/checkpoint 已原子封存，CURRENT_CODEX、monitor、target authority、target run 和 outcome 均为零。进一步部署诊断确认 source transport 当时已经发送 `Accept: application/json` 和固定研究 User-Agent；同一 Python Request 经标准、冻结的系统 `ProxyHandler` 为 200，经 V3.2 当时“空 ProxyHandler opener 建成后再手工 `set_proxy`”路径为 403。根因是自建路由改变了标准代理协议处理顺序/请求形态，不是 OKX 域名或缺少请求头。该段只保留第三资格归因，不表示第四或第五资格已经成功。

2026-08-09 第四资格历史更新：上述路由、header durable binding、第三组 tombstone 与全链修复已在 commit `8ca2ae7bb71e6c1f63c121824f8140de9dec7339` 提交，exact HEAD 的 V3.2 `617/617` 与全 Theory Paper `1302/1302` 通过；真实非正式 OpenAPI preflight 为 HTTP 200。第四资格 `v32-qualification-btcusdt-20260809t030358z` 完成 authority 与 controller 初始化后，在唯一 PUBLIC_SOURCE aggregate attempt 中取得 12/12 份 HTTP 200 原始响应，却因 `V32_PUBLIC_SOURCE_PROVIDER_TIME_TRAVEL` 永久 `FAILED_CLOSED`，不得重试、改写或删除。只读归因确认：资金费响应的 `ts=2026-08-09T03:07:25.959Z` 是 provider observation/update time；`fundingTime=08:00Z` 是当前返回 funding-rate 的 effective/settlement time，可晚于观察；`nextFundingTime=16:00Z` 是独立下一结算 schedule。collector 与测试夹具错误地把 `fundingTime` 当作观察时钟并纳入 PIT `as_of`，造成假阳性时间穿越。四时钟合同固定为：原始 `ts → provider_observed_at`；按冻结 clock-skew policy 形成知识安全 `observed_at`；本地真实接收/保存时刻为 `available_at`；`fundingTime → funding-rate.effective_at`，`nextFundingTime → 独立 next-funding-settlement-time schedule datum 的 effective_at`。只有知识安全 `observed_at` 可推进 datum、bundle 或 axis 的 `as_of`；SERVER_TIME/INSTRUMENT metadata、`effective_at` 与 future schedule 均不得推进。provider 时钟超过冻结容差才失败关闭，容差内必须原样保留 `provider_observed_at`，不得用本地时钟覆盖原始 `ts`。历史第四资格仍保持原字节；当前修订只对新版本和未来新资格生效。

失败证据合同同时分层：`verify_durable_v32_public_source_validation_failure_v1` 只验证历史 sealed failure 事实及 attempt、aggregate raw/capture、component evidence 的物理身份；它不要求修复后的当前代码继续抛出同一旧错误。当前代码是否复现旧失败由独立诊断 `assess_current_v32_public_source_validation_failure_reproduction_v1` 报告，可能为 exact、different、unavailable 或 no-longer-reproduces；该诊断没有 authority，不改变第四资格的永久 `FAILED_CLOSED`。controller 的失败终态必须绑定已封存 evidence，不能只有字符串 `failure_code`。**在该第四资格历史边界**第五组资格仍未创建；后续第五、第六资格事实见下文，该句不得解释为当前状态。

2026-08-09 提交前最终更新（**历史快照；累计 envelope=`1` 已被 2026-08-10 的可构造 `per-attempt<=1 / max-attempts=2 / cumulative<=2` 语义取代**）：五项“易碎瑞士手表”问题当时完成同构实现与独立审查，P0/P1/P2 阻断项均为 `0`。Agent 不再提交 0–100 连续主观权重，只能选择 `EXTREME_UNCERTAINTY/LOW/HIGH`；混沌、无方向波动、过渡、OTHER 与 UNKNOWN 是一等零方向风险状态；同一 instrument 的 24h churn ledger 对所有方向和动作别名统一计数。物理逃生舱仍是未来单独授权合同，不在当前 pilot 伪造“市价必然清仓”。公开市场图采用增量构造，但 owning verifier 在每个当前投影验证作用域内完整重建累计 dependency closure，以同时避免热路径重复计算和旧记录篡改漏检；Cycle 16 完整规模为 `9,760` 条 node history、`9,680` 条 association history，直接完整验证 `79.362s`，生产闭包为 `42 roots / 190 paths / 190 bindings`。最终候选从零回归为 V3.2 `646/646 PASS / 1102.390s`，全 Theory Paper `1400/1400 PASS / 1383.323s`；测试中唯一需要修正的是严格 PIT verifier 正确拒绝了一个只改 K 线 volume、却未同步匹配 datum/member digest 的旧夹具，修正只恢复夹具内部物理一致性，没有放宽 production 合同。旧 V3.1 loader 仍为 Q0–Q8=`9`、冻结 runtime=`74`。四棵失败资格树仍分别为 `44/47/47/70` 文件，当前可复现摘要依次为 `91f575a5a393d319abe0d16e7804765ce94f8ccb15d17fdb198fb58e847401ad`、`3bcaa9b5f1824803a3f67dcd77302b131fc34b927ccb0a1038d9e193e92c4254`、`af0fcee816a25af8708696db685a0b28b41e78716719cbdd620040b3139dcb80`、`bc42b90fbcb6458dd3cf0c18fd7afb3ea94ac40f0096e27749cad8e272b8061b`；用户保留副本仍为 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，不得 staging、删除或修改。以上是提交前候选证据，不冒充 committed replay 或 fresh qualification。

2026-08-09 第五资格历史更新：上述候选已显式提交为 `093b4e79d43ef523e0926aa1e8495ba13feb4145`。exact post-commit V3.2 为 `646/646 PASS / 1096.106s`，正确全口径 `test_theory_paper*.py` 为 `1400/1400 PASS / 1382.714s`；旧 V3.1 loader=`9/74`、V3.2 production closure=`42/190/190`、四棵旧失败树及用户副本摘要均保持不变。第五资格 `v32-qualification-btcusdt-20260809t074253z` 使用一次 PUBLIC_SOURCE aggregate attempt，内部 `12` 个固定 OKX public GET 均 HTTP 200、attempt=`1`、retry=`false`；资金费四时钟与真实 raw-first bundle 通过。CURRENT_CODEX attempt 只预留一次、未实际开始，材料化在 `agent_market_graph_view` 落盘前因容量失败。真实 bundle 含 `414` 根闭合 bar（`15M=96 / 1H=168 / 4H=90 / 1D=60`）；未封存 view 约 `352,219` canonical bytes，超过旧 `256 KiB` 上限，主要由 `55` 条可引用证据记录中的完整 closure association IDs（约 `208 KiB`）与 bars（约 `75 KiB`）构成。这不是删数据许可：修复必须保留所有 citable evidence、availability、dependency groups、UNKNOWN/OTHER 和 bars，并为每条证据绑定 exact full closure digest/counts；完整 node/association/evidence-ref 列表继续 write-once 保存在 graph dependency registry，由 owning verifier 在 build/acceptance 重建后精确核对。禁止任意 top-k、静默删 closure、聊天摘要或仅无限抬高上限。

第五资格旧 composition 的伴生 P0 是材料化异常发生在 controller try/catch 之外。现场保持 revision `3 / RUNNING`，PUBLIC_SOURCE=`COMPLETE`、CURRENT_CODEX=`PENDING / ATTEMPT_RESERVED_NOT_STARTED`、OUTCOME_MONITOR=`READY`；已有 `11` 个 material roles，无 Agent view、mailbox、CURRENT_CODEX evidence root、failure receipt、monitor 或 target。第五树当前为 `96` 文件；按与旧四树相同的 `find -print0 | sort -z | per-file SHA-256 | whole-tree SHA-256` 公式，权威摘要为 `e1016aaafad02af68cc860fe909a34445b11f898eddebea8fb672b80e83d396a`，最后 mtime/ctime=`2026-08-09T07:48:11Z`。较早 Python Path 排序得到的 `9617afd...` 不是同一算法且不得作为冻结摘要。修复必须让 materializer 的 typed/validation/capacity 异常在同一单边界内生成 stage、System UTC、attempt、authority、已封存材料前驱和稳定错误链绑定，并由 owning controller 写一次 `FAILED_CLOSED`；后续 wake 只重放终态，禁止第二次 build、Agent 或 monitor。

2026-08-09 第五资格 P0 修复收口要求：异常后的 material/mailbox/probe prefix 必须分别形成 typed scan status。只有完整重扫成功才能写 `VERIFIED_EXACT` 并绑定 exact inventory；重扫本身失败必须写 `UNKNOWN_REPLAY_FAILED` 与稳定 `*_PREFIX_REPLAY_FAILED`，不得用空 inventory 冒充完整现场。即使现场未知，同一 reservation 仍必须只消费一次并永久 `FAILED_CLOSED`；第二 wake 不得再次构造 materializer、capture 或 probe。真实 Agent-view 容量证据固定为 Cycle 1 的 `187,892` bytes；把相同形态改为 Cycle 16 编号后的 `187,895` bytes 只用于字段容量压力，不得冒充 16 轮累计 registry 或累计耗时资格。完整累计能力只能由逐轮正式实验关闭。

2026-08-07 的 V3.2 `306/306`、Theory Paper V2 `991/991` 与 27 组件结果只保留为历史快照。2026-08-08 第一版正式提交扩展为 28 组件正式接纳、32 个 production roots 与 186 个本地可达路径；五项易碎复杂性修订、可逆压缩/UNKNOWN/manual/environment/audit/supervision、资格分层和 durable-binding 修复均已进入 commit `d5478d9463961a65d7167642c0c67e6c275f6ebf`。该提交 post-commit V3.2 全量为 `502/502 PASS / 984.937s`，Theory Paper V2 全量为 `1187/1187 PASS / 1256.535s`，旧 Q0–Q8/74 路径只读重放通过；这些只证明 committed runtime 可重放，不证明真实公开网络资格。实际 PUBLIC_SOURCE 资格揭示 production bundle transport 强制禁用系统代理，而当前 Codex 环境直连 OKX 超时、系统公共 CONNECT 出口可达；控制器又只保存异常类名，且在首个必需请求无响应时没有保存 typed transport-failure receipt。该资格保持永久失败，target authority/genesis 和目标实验均未开始。详细证据回指 `CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md`、`V3_2_SYSTEM_AND_EXPERIMENT_DESIGN_2026-08-07.md` 与 `V3_2_IMPLEMENTATION_AND_PREEXPERIMENT_LOG_2026-08-07.md`。

当前状态分解：

- 已完成：commit `66197c47a1281340b4226da825da0b18d8815c3e` 及其固定 post-commit 双回归；V3.2.5 单一 Presentation、完整容量门、四阶段 exact-tail、write-once file+directory fsync、Presentation digest/full replay、CLAIMED 零写重放、final-envelope direct return 与真实 fresh-process receipt；第七资格 Phase-A、fresh-process 和唯一 fresh PUBLIC_SOURCE；六个 durable failure 与第七 `EXPIRED_TERMINAL` 原件均保持只读。
- 进行中：bounded material burst、第七历史身份/subject 精确兼容、七组 tombstone 在 qualification/target/namespace 入口前的统一拒绝、zero-eligible WAIT owning-cause 加固、全量回归、精确 staging 与显式新版本提交。CURRENT_CODEX reservation 起点和 `660s` 上限不后移、不放宽。
- 未开始：第八组 successor qualification authority/current Codex/固定 monitor 资格、qualification retirement、唯一 target run 的预注册目标实验与 16-cycle/48-outcome 正式运行。
- 受阻：目标实验仍被“burst/tombstone 修复尚未形成 exact committed runtime 与第八组正式本地控制器收据”阻断；七组历史终态 pair 均不得重试、推进、改写或删除。第八资格完成前不得启动 target；当前 Codex 耐久交付、固定 outcome monitor 与真实 15 分钟时延保持 `UNKNOWN_NOT_QUALIFIED`。non-TTL 宏观/监管/跨资产 invalidation 因缺 owning public event schema 继续为 `UNKNOWN_NOT_AVAILABLE`；预测增量、校准、成本后收益和跨 regime 泛化仍为 `UNKNOWN_NOT_EVALUATED`。
- 历史启动 P0/P1（已被 `8ca2ae7...` 前的固定 Target Agent/Phase B 修复 superseded）：早期 Presentation 缺少与 qualification 同级的 target `read_and_claim` / `submit_delivery` 固定入口，且 Phase B 中断恢复未由 retirement 前 write-once intent 约束。该缺口保留为演化事实，不再作为当前未修复项；由于四次 PUBLIC_SOURCE 资格均先行失败，这些 target 路径尚未形成实际资格证据，不能写成 current Codex 或 target run 已资格化。

### 2026-08-08 V3.2 授权、上下文压缩、审计与本地化修订

#### 用户最终需要的交付结果

- 在不扩大到 paper/live、账户、订单、凭据或资金的前提下，提交当前 V3.2 相关工作树，再建立唯一 `BTC-USDT-SWAP` 公开数据、本地、不可执行前瞻实验；
- 当 Agent context、对象或输出逼近硬上限时，先进行确定性去重与结构化压缩；当前 pilot 只允许最终单一 INLINE packet，仍超限就失败关闭。分片与耐久引用仅作为未来未资格化 transport 需求保留；完整原件始终须由正式接受链全量重放；
- 每个 qualification、analysis、acceptance、outcome 和 recovery 边界都生成 append-only 的中文压缩文字记录，便于人工审查完整流程、UNKNOWN、选择、告警和修复；文字记录不是 authority，不能替代 typed 工件；
- 客观数据采集不到时保持 `UNKNOWN`，同时生成明确的人工处理方案；人工处理不得静默填值或改变正式 PIT 历史；
- UNKNOWN 可由 Agent 形成有依据的主观评估，但必须与客观 UNKNOWN 并存，引用可用事实/机制、列反向解释、证伪条件、有效期和主观序数档位，不能冒充观测值、校准概率、连续权重或因果事实；
- 在当前 macOS/Codex/公开网络能力内建立冻结的 `EnvironmentCapabilityProfile`，只通过 adapter/port 做本地化，不修改理论核心、评价终点、数据时点或权限边界来迁就环境；
- 实验期间优先自动执行已预注册的确定性恢复，并由独立只读监督 Agent 检查状态、日志、权限、未来 outcome 隔离和恢复合法性；监督 Agent 不充当第二 Strategy Agent，也不直接写正式 store。

#### 验收标准

1. **压缩不是删证据**：完整 raw、public bundle、PIT registry、图、availability、Agent input/output 和 acceptance 继续 write-once 保存。新增 compaction manifest 必须绑定原件摘要、压缩策略、保留字段、被折叠成员全集摘要、计数和可逆/不可逆边界；正式 acceptance 同时重放原件与 compact view。
2. **渐进容量处理**：当前 pilot 顺序固定为 canonical 去重与字典化 → 重复时间序列/元数据的 typed compaction → 构造单一 INLINE packet；仍超过最终物理 context 限制就记录 `CONTEXT_CAPACITY_UNRESOLVED` 并进入人工处理。按依赖闭包分片和 manifest 多段读取只作为未来未资格化 transport 设计，不得在本 pilot 启用。始终禁止任意 top-k、静默丢 UNKNOWN/冲突/反证/hazard、截断后假装成功或用聊天摘要补齐。
3. **UNKNOWN 双轨**：`objective_status=UNKNOWN` 不可被 Agent 改写；可附加 `subjective_assessment`，但至少绑定一个当前 PIT 事实或已登记机制引用，并包含 rationale、相反假说、falsifier、expires_at、dependency group 与三档 `subjective_plausibility_tier`。无依据时必须保持 `directional_view=UNKNOWN` 且档位为 `EXTREME_UNCERTAINTY`（确定性风险上限为零）。
4. **数据缺口人工方案**：每个不可获取字段生成 `DataGapEscalation`，记录请求、时间、错误、影响、claim ceiling、允许的官方人工来源、截图/导出/raw 保存步骤、时间核验、双摘要和重新准入步骤。人工数据只可作为标记为 `MANUAL_PUBLIC_EVIDENCE` 的新 revision，在验证后进入未来周期；不得回填旧周期或伪装成自动采集。
5. **逐轮文字审计**：`CycleAuditNarrative` 必须由 sealed 工件确定性生成，至少记录 run/cycle、stage chronology、source coverage、客观 UNKNOWN、主观评估、hypothesis/zone/modifier 变化、所有合法动作比较、selected/runner-up、risk envelope、shadow arms、schedule、告警、恢复、摘要和限制；单条有字节上限，超限时按章节分片并生成目录，禁止漏项。
6. **自动修复分级**：已封存字节的 deterministic tail/recovery 可在同一 run 自动执行；网络/环境适配只能在 qualification 或新 successor run 前版本化并重新资格；正式 accepted cycle 或已预留 outcome 的语义失败必须保持 fail closed，禁止同 attempt 重试、改规则、改历史或提前读取 outcome。若修复改变理论、评价、权限或数据语义，必须重新请求用户批准。
7. **监督 Agent**：只读读取 durable checkpoint、permit、acceptance、audit narrative 和已到期 outcome 状态；不得访问未到期 outcome、调用市场/Agent 第二尝试、修改正式文件、恢复旧 run 或提交交易。发现异常只能产出 append-only alert，由唯一 controller 按冻结恢复合同处理。
8. **环境本地化**：资格前冻结 Python、操作系统、Codex delivery、网络来源、存储、时间、automation 和可用工具能力；每个偏离理想设计的适配必须记录原因、claim ceiling、测试和回滚。缺失能力保持 UNKNOWN/人工处理，不得降低核心验收标准。
9. **先提交后实验**：先盘点 branch/HEAD/status/未跟踪文件/敏感信息和历史证据；只按明确清单 staging，不使用 `git add .`。提交后重放 V3.2、全 Theory Paper V2、旧 Q0–Q8/74 路径及格式检查。authority 生成前工作树必须 clean，或只剩经明确列名、与运行闭包无关的用户保留文件；提交摘要进入 qualification subject。
10. **完成定义不变**：16 个正式 analysis cycle 和 48 个事前 schedule/outcome 全部完成只证明流程与短窗判别 pilot；预测增量、校准、成本后收益、真实执行及跨 regime 泛化在足量证据前继续为 `UNKNOWN_NOT_EVALUATED`。
11. **资格不得先验自证**：qualification Phase A 的 Q2/Q3/Q6 只能证明版本化代码、契约和本地 preflight 就绪，不能作为实际能力收据；fresh source、当前 Codex 单次两阶段耐久交付与固定 public outcome monitor 必须在 qualification authority 之后各执行一次并生成 typed、write-once、可物理重放的 capability receipt。qualification retirement 与 target Phase A 必须绑定这些后置收据；full loader 必须调用 owning verifier 重放其原件、时间、attempt/network 计数和非执行边界，禁止 generic self-digest subject 或聊天 PASS 关闭 target gate。

#### 当前范围与明确不做

- 当前范围：V3.2 版本化压缩/审计/UNKNOWN/manual-gap/environment/supervision 合同、本地实现、测试、Git 提交、fresh qualification 和唯一不可执行 pilot；
- 明确不做：修改旧 V3.1 run 或 74 个冻结路径，删除历史失败，访问私人/账户数据，连接 paper/live，发送订单，触及凭据/资金，把主观 UNKNOWN 变成客观值，事后更改评价，或者让监督 Agent 成为第二决策者；
- 外部边界：官方来源不可用、物理模型 context 不足或 Codex/automation 能力缺失时，先完成所有合法压缩/本地替代与人工方案；仍不可行则如实停止在资格或当前 run 的 failure boundary，不伪造实验完成。

#### 当前主要任务与状态

- 新授权与修订需求：**已登记**；
- 上下文 compaction、逐轮审计、UNKNOWN 主观附加、人工缺口、environment、supervision、recovery、workspace freeze、正式 post-commit receipt、单一 Presentation 与容量前置门：**均已进入提交 `66197c4`；第七资格已证明 fresh-process 与 fresh PUBLIC_SOURCE**；
- read-only supervisor、same-run recovery 白名单和 workspace freeze 合同：**已提交并重放；六组 `FAILED_CLOSED` pair 与第七 `EXPIRED_TERMINAL` pair 共同保持永久 tombstone，第八组固定入口尚未创建**；
- 工作树范围审查、测试、提交和 clean 边界：**bounded burst 与历史终态兼容候选已形成；本轮全量 V3.2 与全 Theory Paper、冻结树复核、独立终审和显式提交仍在进行。继续禁止 `git add .`，用户副本保持未跟踪**；
- V3.2 qualification authority/fresh qualification：**六份为 durable 历史失败；第七份完成正式收据、Phase-A、fresh-process、PUBLIC_SOURCE 和 proposal request 后因 reservation 窗口耗尽成为治理 `EXPIRED_TERMINAL`，原 runtime 保持 `RUNNING/revision 3`。第八组尚未开始**；
- 唯一 16-cycle/48-schedule pilot：**未开始**；
- 当前门：**同一高层 qualification wake 最多连续推进冻结上限 `64` 个内部 append-only 子阶段；每步保持原 write-once/CAS、时钟与异常封存，遇 Agent、READY、no-progress、probe 高层边界、异常或上限立即停止。第七 pair 必须与六组 failed pair 分类型保存但共同在 qualification、target wake/run 与 namespace 写入前拒绝。全量回归、显式 commit 与新 exact-pair receipt 通过后，才允许第八资格。non-TTL event source 继续 UNKNOWN，不以假数据关闭。**

#### 需求变更记录

- 2026-08-10 阻断级复核新增的两个最小 P1 已修复：graph registry builder/verify 现在在一个作用域内只完整重建一次当前 closure，随后复用同一次 owning projection verification 的 projection/digest/closure；Cycle 1/2 调用计数与 self-resigned tamper 回归均通过，未删除依赖身份、完整 closure 或物理重放。原先把不存在的固定 24h 同类证据归并写成已实现的表述已统一纠正为 pilot 有界 working set + delta；未新增时间归并框架，`24h` 仅保留为 reentry ledger 的冻结窗口。
- 2026-08-10 全量回归新增的持久化 exact-replay P0 已最小修复：`V32DeterministicAuditTests.test_all_sections_are_mechanical_bounded_and_replayable` 的 directory 与 shards 原本逐字节、逐顺序相等，根因是 atomic successor loader 把 store-owned `layout/directory_binding/shard_bindings` 泄漏进既有 public `load_audit_bundle` 返回。当前 private record loader 只供 persist 幂等复用 binding，public loader 对 successor/legacy 均只返回原始 `directory + shards`；write-once 冲突、atomic publication 与 unexpected-file fail-closed 保持不变。已新增 legacy exact-layout 回归并调整 successor 回归；不扩展为新存储框架、不 stage/commit、不推进实验。
- 第六资格后、`66197c4` 提交前历史候选：用户要求解决耐久交付与真实资格链剩余缺口。新增硬验收为四阶段 exact-tail、write-once file+directory fsync、delivery receipt 绑定 Presentation digest 且由 qualification full replay 重建、CLAIMED lost-response 零写重放、最终 `<=1 MiB` envelope 直接交付、pilot `INLINE_ONLY`，以及 fresh-process collector 在任何 Phase-A authority byte 前运行并将 typed receipt 物理绑定到 support/manifest/runtime closure/full loader。当时代码接线候选为 `43 roots / 194 reachable paths / 194 bindings`；本条状态已被第七资格事实 superseded。
- 第六资格后本轮修订候选：先前 2026-08-08 日志中的 initial/pre-CAS/post-CAS 三时钟和 `PERSISTED_POSTCHECK` 是历史实现，不再描述当前候选。新 claim/submit 在新转移时只用入口与紧邻 CAS 前两次 System UTC；orphan exact-tail 复用原 `claimed_at` 而不取新时钟。全部 permit/anchor/Presentation 校验发生在单次 CAS 前，成功后直接返回；不存在第三时钟、外部重读或伪 quarantine。旧日志保留为历史，不回写旧冻结证据。
- 第六资格后最终同步候选：耐久 fsync/no-replace 实现限定为 V3.2-owned package-shared `trade_system/theory_paper_v2/v32_durable_json.py`，`infrastructure/v32_durable_json.py` 仅保留兼容 re-export，Application 不得反向依赖 Infrastructure；V3.1 冻结 `domain/contracts/canonical.py` 原字节不变。response-loss 明确覆盖 `REQUESTED/CLAIMED/DELIVERED` exact successor。runtime manifest 采用同一 schema family 的 strict `1.0.0 legacy / 2.0.0 successor` 路由：旧六树无 fresh binding 仍可原样重放，新 prepare 仅生成强制 physical trace 与 chronology 的 `2.0.0`。共享 owner 替换旧 production path 后候选 closure 仍为 `43/194/194`，历史第六 `42/192/192` 及更早数字不变。
- 2026-08-09：第六资格 `v32-qualification-btcusdt-20260809t131915z` 在 exact commit `e0c7d3d` 上完成正式 post-commit receipts、Phase-A、Q0–Q8/support/runtime replay 与唯一 PUBLIC_SOURCE attempt，随后在 `CONTEXT_PACKAGE:PROPOSAL` 永久 `FAILED_CLOSED`。真实 packet/input=`559,522/562,654 B`，旧 512 KiB 子门制造错误分片，`121` shards 约 `7.79 MB`。第六 exact qualification/target pair 和 `107` 文件树永久只读，不得续跑。
- 2026-08-09：第六失败后只读审查又发现实际 Presentation P0：旧返回将同一 packet 复制三次达到 `1,687,318 B`，且先 claim 后测量。V3.2.5 验收增加单一 owning envelope、当前 pilot `INLINE_ONLY`、完整 checkpoint/request/claim/control 总门、enqueue 最坏 claim 预演、qualification/target CAS 前真实预演，以及容量失败零持久化。`SHARDED` 仅为未来未资格化能力；新 envelope 只证明本地确定性可重建，不证明 provider/transport 已接收或当前 Codex 已消费。
- 2026-08-09：第五资格首次让修复后的真实 12 组件公开 bundle 进入 Agent 材料化，暴露测试 fixture 未覆盖的双 P0。第一，旧 256 KiB Agent view 上限错误地按“每 timeframe 96 bars”估算，真实四周期共 414 bars，加上把完整 association IDs 为每条 citable evidence 内联，形成约 352 KiB payload；修复不得删 evidence 或只抬 cap，而要把完整 closure 转为 exact digest/count/dependency-group 决策视图，并由 owning full registry 重建验证，所有原始 closure 仍耐久保留。第二，composition 的 materializer 特殊分支绕开 controller failure catch，导致 exception 后仍可误恢复；修复必须写一次 materialization failure evidence、CAS terminal checkpoint，并让后续 wake 零重试。第五 qualification/target exact pair永久 tombstone；第六组只能在新版本 commit/exact replay 后创建。
- 2026-08-09：独立复核进一步发现 failure receipt 的异常后重扫也可能再次抛错并逃过 terminal seal。最终合同将 material/mailbox/probe 三个 prefix 分别隔离：`VERIFIED_EXACT` 才表示物理清单完整，`UNKNOWN_REPLAY_FAILED` 表示重扫失败且只绑定已知前驱；两者都消费同一 CURRENT_CODEX attempt 并永久终止。三类反例首次 wake 均 seal、第二 wake 均零 materializer/capture/probe，独立终审 `P0=0/P1=0`。同轮明确 Cycle-16 容量仅为同形态编号压力，不是累计 16 轮资格。

- 2026-08-09：完成用户本轮五项问题的最终实现级审查。连续主观权重、强制二元方向、无限 reentry、理想化物理清仓承诺均已从正式合同移除；依赖闭包没有被删除，而是改为增量构造、单作用域完整 owning replay 和后续阶段复用，以保留同源去重与累计篡改检测。修复 rolling-window 新 delta 与累计 closure 不一致、旧 closure 可自签替换、dependency index 可篡改、source terminal failure 可脱离 canonical owner/attempt/capture 重放等相邻缺口。提交前 V3.2 `646/646`、全 Theory Paper `1400/1400`、五问题聚焦 `120/120` 及独立受影响链 `109/109` 均通过；独立最终 diff 审查的 P0/P1/P2 均为零。**在该历史边界**下一步仍必须先显式 commit 与 exact replay，不能凭当时工作树创建第五资格；其后第五、第六资格事实见本文开头。

- 2026-08-09：第四资格 `v32-qualification-btcusdt-20260809t030358z` 的唯一 PUBLIC_SOURCE aggregate attempt 已取得 12/12 HTTP 200，但因生产代码把 `fundingTime` 当作数据观察时间而永久失败关闭。用户授权覆盖版本化修复，但不允许修改或重试第四资格。新增验收固定为四时钟：`ts → provider_observed_at`；冻结 clock-skew policy 形成知识安全 `observed_at`；本地接收/保存为 `available_at`；`fundingTime → 当前 funding-rate.effective_at`，而 `nextFundingTime → 独立下一结算 schedule datum.effective_at`。只有 `observed_at` 进入 PIT/global/axis `as_of`；effective/schedule 可合法晚于观察且不得推进 as-of。provider 原始时钟超过冻结容差才失败，容差内仍原样保存。控制器失败终态必须绑定 raw/capture/attempt/failure evidence；历史 durable verifier 只验证 sealed 失败事实与物理输入，当前代码复现状态由独立诊断给出且不改变历史终态。**在该历史边界**修复后必须先提交并 exact replay，第五组资格当时仍未创建；其后第五、第六资格事实以本文开头和后续条目为准。
- 2026-08-09：第四资格只读复核同时登记相邻来源时钟与覆盖 P1。无 provider snapshot timestamp 的 instrument 只允许以本组件 HTTP 接收时刻作为 `available_at/observed_at` 的本地知识时钟并显式标注；有 provider 时钟时必须原样保存 `provider_observed_at`，只按冻结容差形成知识安全 `observed_at`。全局 market `as_of` 与十二轴时刻只可由各自绑定市场组件的 `observed_at` 派生，SERVER_TIME、INSTRUMENT、`effective_at` 和未来 schedule 均不得推进。实时组件超过 `120s`、funding observation 超过 `900s` 必须失败。四个 K 线序列必须网格对齐、相邻连续并止于最近应闭合桶；recent trades 必须记录实际首尾时刻、请求条数上限和截断状态，不得把固定条数描述为固定时间窗。第四组 qualification/target ID 必须成对进入 Domain 永久 tombstone。以上只对新版本和未来新资格生效，不补写第四失败树。
- 2026-08-09：第三资格 `v32-qualification-btcusdt-20260809t010844z` 在唯一 PUBLIC_SOURCE attempt 的 SERVER_TIME 请求收到 OpenAPI Cloudflare 403 并永久失败闭合。正式 source 请求已经带 JSON Accept 与固定研究 User-Agent；精确对照证明标准 urllib 代理 handler 为 200，而 active route 的“opener 构造后手工 `set_proxy`”为 403。新增硬验收：系统代理 URL 仍须先拒绝 userinfo/非法 scheme/path/query/fragment 并冻结，但代理处理必须作为 opener protocol handler 安装，不能在 `open()` 中临时改写 Request；不得因运行中 `no_proxy` 漂移静默直连或 fallback。请求头必须由版本化 route policy 生成，禁止 caller 注入；source 与 outcome 统一 `User-Agent: agent-trade-emotion-v3.2-public-research/1.0` 和 `Accept: application/json`，禁止 Authorization/Cookie/API key/自定义代理/重定向；component capture、raw bundle、transport failure、durable replay、qualification/monitor/outcome adapter 必须绑定同一 header-policy ID 或规范化头摘要。任何缺失、漂移或额外敏感头在联网前失败；旧 V1/V2 路由和三棵失败资格保持字节不变。
- 2026-08-09：独立复核追加一项 P1：第三失败资格已由 exact digest 兼容只读回放，但 active identity tombstone 仍只有前两组。新增硬验收：`v32-qualification-btcusdt-20260809t010844z` 与 `v32-prospective-btcusdt-20260809t010844z` 必须成对进入永久墓碑；任一 ID 与任意新配对都在 authority/runtime namespace 创建前拒绝，不能依赖现存目录或 write-once 冲突代替身份禁用。
- 2026-08-09：同次复核发现 active source durable evidence 仅保存 composite `route_policy_id`，但未直接保存其 owning `header_policy_id` 或规范化头摘要；运行时共享 builder 虽能保证当前调用一致，封存证据本身仍不能直接表达这一绑定。新增硬验收：active component capture、component no-response failure 与 aggregate transport failure 升版并由 builder 内生写入固定 header-policy ID 和 digest；调用方不能提供或覆盖这两个字段。旧 V1/V2 证据继续只走 exact ID+digest 兼容，raw replay 必须验证 active 字段并在 response-backed failure 中与 capture 交叉一致。

- 2026-08-08：用户在新资格前再次提出五项“瑞士手表式易碎性”质疑。裁决是不接受“删掉所有约束后糙快猛”作为无证据盈利结论，但接受其指出的运行时伪精确、方向二分、重复重入和物理故障暴露面，并把以下内容提升为新资格前的硬验收条件：
  1. **主观数字彻底退役**：Agent 的 risk-arithmetic / subjective-risk 输入、schema、编译器和文档不得保留 `residual_uncertainty_quality`、连续主观权重或任何会缩放风险且可被误读为概率的 quality 别名。Agent 的主观判断只提交 `EXTREME_UNCERTAINTY/LOW/HIGH`；action-evaluation 中连续的 `risk_reference_units` 只能 exact 回传 sealed plan 已派生的值并由 compiler 重算，不是 Agent-authoritative 风险旋钮。任何内部整数只能是 sealed policy 对档位的确定性编码或其补集，不能由 Agent 自由输入，也不得宣称校准概率、EV 或客观质量。zone/source/outcome 中同名的客观或诊断性 `quality` 必须由各自 owning verifier 验真，且不得进入风险 scalar 或主观仓位缩放；不得用同名字段静态计数冒充语义验收。
  2. **复杂性移出热路径但不删除证据完整性**：运行时不做开放式图搜索；依赖/来源在 source admission 时规范化，单 cycle 只消费冻结投影并做有界集合校验。15 分钟时限只能由 fresh-process、跨 wake、真实 Codex 与公开网络资格证明；本地 memo 优化不得再写成已证明端到端性能。
  3. **中性/混沌成为一等状态**：保留 `CHOPPY/NEUTRAL/TRANSITION/VOLATILITY_WITHOUT_DIRECTION` 的零方向风险硬门；新增 typed regime feature assessments，CHOPPY 必须由反转频率、弱方向持续性和成本/振幅关系等预先列举的当前 PIT 特征支持，波动无方向必须同时有波动扩张与方向冲突/平衡证据。任意单一无关引用不得把方向状态改为混沌或恢复为方向状态。
  4. **重入是受限机会而非义务**：ledger `INACTIVE` 时首次 `OPEN_PROBE` 不计；ledger 激活后，任一方向最终选中、合格且风险为正的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一 instrument attempts/cumulative 上限。同向恢复必须规范化为 `REENTER`，真正反向动作可以保留语义但不能免费。维持全局滚动窗口、连续止损冷却和上限；文档不得再声称每次收回都必须重入。当前不可执行 pilot 不生成真实订单。
  5. **物理逃生只作 future-only 合同**：没有账户/订单/venue 控制权限时，不得声称“核按钮必然清仓”。当前系统只能在物理异常后阻断新增风险、保存老风险暴露为 UNKNOWN 并生成未来人工/执行升级方案；未来执行版须另行授权并资格化独立 risk daemon、预置 venue-native protective order、备用出口、marketable IOC/market escalation 和最终人工接管，且任何路径都不得保证无滑点退出。
- 2026-08-08：同轮最终独立复核又关闭两项 Target Agent P1。其一，claim/submit 原先只在入口取一次时钟，邮箱写入跨过 permit deadline 仍会返回成功；现使用 initial/pre-CAS/post-CAS 三时刻并逐段拒绝回拨，pre-CAS 到期零写、post-CAS 确认跨界不返回成功，下一 guarded wake 在 mailbox 前按过期 permit 失败关闭。其二，同 run/cycle 的陈旧或移植 mailbox packet 原可被当前 permit 接受；现从 Dynamic owning store 精确重放 predecessor、permit、stage packet/input 及五字段物理 binding，并校验 decision 与 issued→created→reserved→deadline 时间链。generic post-CAS 异常明确为 `UNRESOLVED_REPLAY_REQUIRED`，不虚称已耐久隔离。独立复核 P0/P1 均为零；Q6 也显式加入 route 间接依赖的 public-evidence port。
- 2026-08-08：最终全量首轮 `615` 项中 `614 PASS / 1 ERROR`。直接错误是 formal chronology 的注入 `_Opener` 没有跟随 active OpenAPI V2 route policy，collector 因此正确拒绝其逐组件 capture；真实 `V32SystemPublicHttpsOpener` 已有正确 policy，故只给测试夹具补 exact policy，不放宽 production。只读监督同时复现独立失败原子性缺陷：组件 raw 已 write-once 成功但 capture 元数据发布失败时，transport 会把本地 sink 结构错误包装成 OSError，collector 再尝试写同一 raw 并遮蔽原始原因。现只要 typed leaf 含 `PUBLIC_RAW_SINK_STRUCTURAL_FAILURE`，collector 直接进入结构性 `QUALIFICATION_FAILED`，保留一次 raw tail，不生成普通 transport-failure receipt、不重复写、不资格化；精确反例与 source/transport/chronology 联合 `46/46 PASS`。最终两套全量必须从该字节重新开始。
- 2026-08-08：同轮独立实现复核新增以下必须在第二次提交前关闭的精确缺陷：
  1. `write_once_json` 的 containment 必须检查从既定根到叶子的每个已存在 path component 都不是 symlink，并在建父目录后重新验证；用 qualification-ID 根指向旧失败根的 symlink 必须在写前拒绝。旧失败根以全树摘要证明前后不变。
  2. pre-network/legacy Q2 路径集合只能供精确失败身份 `v32-qualification-btcusdt-20260808t150343z`、target `v32-prospective-btcusdt-20260808t150343z`、profile `QUALIFICATION_PHASE_A` 只读重放；任何新身份只能接受当前 closure。已失败的 target/qualification ID 进入静态 tombstone，不得在新 base 重用。
  3. Phase A/Phase B 正式组合入口必须从 ID 确定性派生精确 `.runtime/v32/qualifications/<qualification_id>` 根，生产 API 不得接受 caller store/root/clock/verifier/binding registry；full loader 还要验证 authority、receipt、capability receipts 与 evidence roots 全部位于该精确根，不能只做前缀匹配。
  4. 公开 source bundle 每读取一个 HTTP body，就必须在解析及下一个请求前 write-once 保存并回读绑定；transport 返回后缺任一 OBSERVED component binding 即结构失败。optional component 在收到任何 response 前发生冻结白名单内 timeout/connect 时，也必须先 write-once 保存并回读逐组件无响应 failure receipt，绑定 component/path/query/start/failure time、route、attempt=1/no-retry、response/body/status/final-URL 均不存在的事实和稳定错误码，随后才可降为 coverage UNKNOWN 并继续下一请求；aggregate 与 durable replay 必须精确绑定该 receipt，缺失、篡改、交换或 sink 失败均停止。HTTP `400/401/403/404`、redirect 与无效 JSON/envelope 属结构失败；仅冻结白名单内的 timeout/connect/`429`/`5xx` 可作为 optional coverage UNKNOWN，required component 仍失败关闭。不得合成 HTTP 599。
  5. failure receipt 必须绑定 response status/body（如存在）、实际 `failure_at` 和精确物理叶错误码；controller 终态必须耐久绑定该 receipt，verifier 必须从 owning store 重读 raw。任何 persistent receipt、checkpoint 或审计中不得出现代理值、异常自由文本、traceback 或秘密。
- 2026-08-08：五问题最终构造性验收发现离散档位仍有一个方向预算泄漏：全局包络先取 LONG/SHORT 最高档，再把它按所有 cluster 共同切分时，多个 LOW cluster 可借另一方向的 HIGH 抬高本方向合计。修复必须同时满足全局总包络和逐方向档位上限；任一方向的 cluster reference-risk 合计不得超过 `raw envelope × min(该方向档位上限, residual cap)`，增加同侧 cluster 数量不能提高该方向上限。必须加入“1 个 LONG HIGH + 多个 SHORT LOW”的构造性反例，并保持量子化、去重和零候选不放大。
- 2026-08-08：提交前最终只读审查发现 optional timeout/connect 无 response 时，transport 曾直接生成 UNKNOWN 并继续下一组件，只有稍后的 aggregate row 留下错误码；若进程在 aggregate 发布前退出，该组件失败没有 owning 物理收据。修复必须在继续前封存逐组件无响应 failure receipt 并完整回读，aggregate UNKNOWN 与 durable replay 必须绑定它；`response.read()` 的 `ValueError`/`HTTPException` 只可在局部读取边界分类，status、final URL 或 schema 产生的同类异常不得被洗成物理 body-read failure。该项完成聚焦与全量回归前，不得提交或创建 successor qualification。
- 2026-08-08：同次正式 acceptance 复核发现三帧虽然已绑定当前 bundle 的 payload digest，但 REFRESHED frame 的时间、TTL、来源引用、dependency groups、invalidation sets 与 frame ID 尚只满足宽泛 schema，未绑定 production 冻结策略；伪造超长 TTL 或伪 provenance 仍可能自摘要后通过。修复必须由纯 Domain helper 对每个 REFRESHED role 独立重算并验证：`created_at=decision_time`、`as_of/available_at=current bundle`、精确 TTL `86400/3600/900`、当前公开 source refs、固定 frame ID/dependency groups/invalidator sets；CARRIED_FORWARD strategic 继续由 predecessor immutable binding 管理，不得被强制改成当前 refs。material adapter、local resume 与正式 acceptance 均须调用 owning helper，并加入真实重签名负向验收。
- 2026-08-08：逐组件无响应 receipt 落盘后的最终跨层复核发现 `v32_durable_source_replay` 仍按旧 schema 把每个 UNKNOWN 的 failure evidence 硬编码为 aggregate raw binding；新 schema `1.2.0` 中，`429/5xx` 有 response 的 UNKNOWN 绑定本组件 raw capture，无 response timeout/connect 则绑定固定路径 typed component-failure receipt。修复必须在 target durable replay 与 receipt verifier 中保持这三类精确语义：OBSERVED 重放 component raw；UNKNOWN+raw 重放同一 component raw 且 failure binding 必须等于它；UNKNOWN+no raw 从 owning store 精确读取并验证 typed no-response receipt，禁止 aggregate fallback。必须加入 503+raw 与 timeout+receipt 的端到端成功、缺失/篡改/交换失败反例；关闭前为 P0，禁止提交或资格。
- 2026-08-08：上述 durable replay 修复不得让 Application 直接导入 Infrastructure collector 的 schema 常量或 owning verifier，破坏已冻结的依赖方向。逐组件失败合同身份和验证能力必须由既有 Application-owned `V32PublicEvidenceVerifierPort` 暴露，或由该 port 的完整 durable replay 返回已从 owning store 验证过的 typed failure mapping；Infrastructure 只实现 port。Application 可以比较经过 port 验证的身份，但不得知道 concrete store path helper 或反向依赖 Infrastructure。最终 closure 与 Application→Infrastructure 依赖检查必须重跑。
- 2026-08-08：最终全 V3.2 回归发现 outcome observation 的 `UNKNOWN_COVERAGE_LOSS` 只分别验证了“证据种类合法”和“失败码合法”，却未验证两者组合，因而原始 HTTP 响应可被重签为 `PUBLIC_TIMEOUT`。修复必须冻结原因—证据角色矩阵：`PUBLIC_CONNECTION_FAILURE/PUBLIC_DNS_UNAVAILABLE/PUBLIC_TIMEOUT/PUBLIC_TLS_FAILURE/PUBLIC_TRANSPORT_IO_FAILURE` 只能由 typed `PUBLIC_TRANSPORT_FAILURE_RECEIPT` 支撑；`PUBLIC_PROVIDER_UNAVAILABLE` 只允许由已封存的 `429/5xx` response raw 及其 normalization 支撑；`PUBLIC_DATA_EMPTY` 只允许由 HTTP 200、合法 provider envelope 且 `data=[]` 的 raw 及其 normalization 支撑。零字节、无效 JSON/envelope、非零 provider code、错 instrument/字段/时间仍为结构失败，禁止降级为 UNKNOWN。必须加入全部允许组合与 raw↔transport receipt 交换、错误 failure code 重签的交叉反例；此 P0 关闭并从零通过全量回归前禁止提交、资格或实验。
- 2026-08-08：上述 Domain 矩阵初修后，独立 PoC 又证明 owning store 可把 HTTP 200 非法 JSON 的 durable raw 与调用者自签 `PUBLIC_DATA_EMPTY` coverage receipt/observation 一并接纳；同类漏洞也可能让 parse receipt 的值脱离 raw，或让一种 transport receipt 被重签为另一种 transport 原因。最终修复不能只比较 evidence kind：store 在 `commit_normalization` 与所有 durable replay 中必须从当前 raw bytes、HTTP status 和固定解析器重新判定唯一合法 normalization；在 observation commit/replay 中必须把 raw binding、normalization semantic digest、status/value/quality/missingness/conflict 精确绑定当前 prefix。transport receipt builder 与 no-response 入口只能接受五种 transport code，且 observation conflict 必须等于 receipt 内 failure code。非法 JSON→DATA_EMPTY、HTTP 200→PROVIDER_UNAVAILABLE、非空数据→DATA_EMPTY、DNS receipt→TIMEOUT、normalization/raw/conflict 交换均须失败关闭且零网络。
- 2026-08-08：第二轮 reentry 构造审查发现现有别名门只处理与 active ledger 同方向的 `OPEN_PROBE/REVERSE`；在 LONG ledger 已消耗一次时，相反方向 SHORT `OPEN_PROBE` 可被选中为正风险而不计 attempts/cumulative，重复换向即可绕过 instrument 全局 24h 防磨损预算。修复必须保持“一 instrument 一账本”：active ledger 下任何方向的 `OPEN_PROBE/REVERSE` 都不得成为未计数正风险；它们必须被阻断、规范化为 canonical `REENTER`，或作为明确的 instrument-churn action 消耗同一 ledger，并同样服从 attempts、累计剩余额度、冷却和 expiry/reset 门。为保留真实换向能力，优先采用“允许最终选中的相反方向动作，但计入同一全局 churn budget”；ledger `INACTIVE` 时的初始 `OPEN_PROBE` 不计为 reentry。不得用换方向、换 action、换 cluster/regime/hypothesis ID 建第二本账；必须补 LONG-ledger→SHORT-open/reverse 的构造反例与 continuity 计数证明。
- 2026-08-08 原始风险算术审查（未知类型已被 2026-08-10 作用域拆分修正）：`multiplier_reference/fee/slippage/funding/gap` 曾由 Agent tranche 直接提供，`derived_reference_scale` 会对这些未绑定数值做精确运算；同一市场材料只改乘数即可得到大幅不同的影子规模。修复把客观合约乘数、数量/价格步长与冻结研究压力假设绑定 owning public bundle/experiment policy，并由 adapter/compiler 确定性核对；Agent 不得自由生成这些数值。现行语义中，研究比较所需的合约规格或冻结压力输入缺失记为 compiler-owned `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 并归零当前正 reference-risk；legacy `UNKNOWN_MAX_LOSS` 只描述未来真实执行损失不可界定并阻断未来执行，不得删除当前研究方向。任何缺失都须生成数据缺口/人工处理方案，不能用默认零或任意小数放大规模。
- 2026-08-08：第二轮 store mutation 审查证明 `LocalV32DynamicStore.persist_artifact` 可在 OPEN cycle 中接纳只有公共字段和自摘要、却未经 owning role verifier 的假 `action_plan`，使 write-once role 被永久占位并拒绝后续真实工件；正式 `accept_cycle` 最终会拒绝，因此不是假 acceptance，但可不可逆终止周期。修复必须取消生产入口对无验证 raw mutator 的可达性，或让每个 role 在首次写入前调用其 owning verifier/验证过的 stage receipt 与当前 cycle context；schema/self-digest/run/cycle/non-executable 通用检查不能代替角色语义验证。假 action_plan/proposal/selection 的自摘要占位、重复写和崩溃恢复必须失败关闭且不得污染 role path；正式 lane/controller 仍是唯一 mutation owner。
- 2026-08-08：上述 store 修复第一次仅删除公开方法名并加入 AST 直接调用检查；独立复核用私有方法仍成功写入伪 theory，证明“下划线 + 静态直调计数”不是能力边界。最终修复必须让 Store 只在初始化期发放一次 opaque writer capability，并由 formal `LocalV32AnalysisLane` 独占；领取后任何第二次领取失败，普通 Store 实例不再有直接接收任意 role/path/document 的写入口。静态门同时扫描该写方法的全部属性引用而不只 `ast.Call`，生产源只允许 capability writer 内部引用；别名/getattr 形式显式禁止。原 PoC 必须在写文件和推进 checkpoint 前失败，正式 Lane、CAS、write-once replay 和 deterministic recovery 继续通过。该能力边界只针对当前可信单进程组件隔离，不宣称抵抗能反射读取 Python 私有内存的恶意代码。
- 2026-08-08：第二版 opaque writer 仍把 `type(owner) is LocalV32AnalysisLane` 与 `owner._dynamic is store` 当作完成构造的证明；独立复核用 `object.__new__` 和单一属性赋值复现了未运行 `__init__` 仍可领取并写入，且低层 Store 测试辅助函数使用了同一方法，故聚焦 PASS 不构成关闭证据。修复必须把“正式完成构造”变成 Lane 模块在完整 authority/root/collector/factory/clock/material/public-verifier 验证后的进程内登记；Store 同时核对 exact type、exact store 与登记状态，失败后不得写文件、推进 checkpoint 或消耗唯一 writer。测试可以显式替换可信登记器来单测 Store 内核，但必须另有不替换登记器的 `object.__new__` 反向 PoC；生产 closure 要限制登记、领取、writer 和底层 gated mutator 的全部引用。该可信进程登记仍不宣称抵抗恶意 monkeypatch/私有内存反射。
- 2026-08-08：第三版候选已按上述边界实现：构造登记只包围一次 claim 并在 `finally` 删除；无效 clock 在登记前返回 typed error，随后同一 Store 的真实 Lane 可领取；未执行 `__init__` 的 exact-type owner 在零 artifact binding 时被拒绝；第二个正式 Lane 把 Store 的重复领取错误转换为 `V32LocalAnalysisLaneError`。production closure 同时限制构造登记器、checker、writer、gated mutator、locked mutator 的生产引用，并拒绝直接 `object.__new__(LocalV32AnalysisLane)` 与固定敏感字符串反射。当前证据为 Store/closure `18/18` 和构造反例 `1/1`；必须在独立复核与全量回归后才可把 P0 标记关闭。
- 2026-08-08：第三版 writer 经独立只读正确性复核未发现 P0/P1：未构造 owner 拒绝；全部依赖与 authority/root 校验先于领取；无效依赖后同一 Store 的真实 Lane 可领取；第二 Lane 返回 typed local error；成功/失败两条路径的临时登记均恢复为空；新 Store 可从原 run root 构造 Lane 并推进下一 durable substage。独立证据为 Store+Lane `19/19 PASS / 328.275s`、production closure `1/1`、registry cleanup 与 fresh-Store recovery 探针通过。能力边界仍只限可信单进程组件正确性。
- 2026-08-08：正式 local Lane 五项回归虽然全部通过，但总耗时 `243.374s`；因此用户指出的“瑞士手表式热路径超时”不能仅靠局部功能 PASS 关闭。必须记录每个 durable substage/wake 的耗时并 profile 重复验证；若重复发生在同一次 `advance_analysis`，允许在该调用内部使用既有 owner/thread/task + strict built-in snapshot 绑定的 lifecycle memo scope。scope 退出必须清空，失败不得缓存，custom Mapping 不得缓存，跨 wake/进程不得复用；不得通过少验证、聊天摘要或 lossy compaction换取速度。只有 fresh qualification 能证明真实 Codex/公开网络下的 120 秒目标或给出诚实 NO-GO。
- 2026-08-08：`advance_analysis` 现只在一次 wake 内包围既有 `v32_lifecycle_verification_scope_v1`；相同 strict built-in JSON snapshot 的成功 verifier 可复用，scope 返回/失败即清空，owner 变化、custom Mapping、线程/task/进程变化均不复用。完整本地周期从原五项累计慢测暴露的超时风险收敛为 `1/1 PASS / 112.879s`（real `113.08s`）；Local Lane 与生命周期联合 `27/27 PASS / 143.065s`。该结果达到本地 120 秒目标但不证明真实 Codex delivery 或公开网络端到端时限，fresh qualification 仍是唯一能力判定。
- 2026-08-08：轻量 profile 证明 Lane 构造/新 writer 登记仅 `0.0772s`，旧高成本集中在完成尾部的组件/市场图/依赖重放与大型 Agent 生命周期对象的递归快照；前 36 个推进边界多数为毫秒至 `1.55s`。`verify_durable_analysis_completion` 的独立完整重放现也只在本次函数调用使用相同 lifecycle scope，不能跨函数返回保留结果；完整周期最终 `1/1 PASS / 111.067s`（real `111.29s`）。缓存隔离/篡改/并发专项 `4/4 PASS / 42.650s`。不得以测试夹具构造的约 42 秒成本冒充 production 网络/Agent 时间；全量与 fresh qualification 仍待执行。
- 2026-08-08：最终 V3.2 首轮全量 `589` 项中 `588 PASS / 1 ERROR / 936.206s`。唯一错误发生在 `test_missing_qualification_audit_blocks_before_public_network`：测试把 `LocalV32AnalysisMaterialAdapter` 替换成完全空的 `_UnusedMaterial`，新 Lane 构造合同在资格审计 router 运行前正确拒绝无五个协议方法的 collaborator。生产组合未使用该空对象，网络 mock 也未被调用；这是 fixture 未跟随强化接口，而不是应放宽 production 验证的理由。修复仅为该替身增加五个“若实际调用即断言失败”的 callable 方法，继续证明审计缺失在 public network 前阻断。
- 2026-08-08：上述 fixture 修正后目标唤醒组合 `3/3 PASS`，完整 V3.2 从零复跑 `589/589 PASS / 933.646s`，real=`933.96s`、user=`911.79s`、sys=`19.21s`。该结果只证明当前工作树的 V3.2 本地回归；全 Theory Paper、exact commit、公开来源、current Codex 和 fixed monitor 资格仍未完成。
- 2026-08-08：同一最终工作树的全 Theory Paper 从零回归 `1274/1274 PASS / 1216.390s`，real=`1216.90s`、user=`1182.30s`、sys=`30.33s`。它证明当前测试覆盖内的 V1/V2/V3.1/V3.2 跨版本合同未失败，不证明预测有效、校准、成本后收益、跨 regime 泛化、公开网络长期可靠或生产就绪。
- 2026-08-08：raw-first 最终时序复核发现 response 已存在但 body 为零字节时，outcome/probe 适配器与 durable store 会在 write-once 封存前拒绝该响应。修复必须允许 `0..MAX` 字节的真实 HTTP body 先绑定 request/status/final URL/received/captured time 并耐久封存，再由严格解析将零字节、无效 JSON、无效 envelope 或必需 datum 字段缺失判为结构失败；不得把“空 body”伪装成无响应、coverage UNKNOWN，亦不得因为解析必然失败而省略原始物理证据。bundle、qualification probe 与 target outcome 必须有零字节构造性回归，且 owning replay 从已封存的 SHA-256/长度零原件复现同一失败，不发第二次网络请求。
- 2026-08-08：增量热路径的 production 接线复核发现，domain 虽允许 `STRATEGIC_CONTEXT=CARRIED_FORWARD`，正式 `LocalV32AnalysisMaterialAdapter` 却在 Cycle 2–16 无条件把三帧全部标为 `REFRESHED`，且战略 payload 混入每轮必变的 aggregate bundle digest/物理请求引用，使高周期语义即使未变也永远无法命中。修复必须只允许已验证前序战略帧在绝对 TTL 未到、无 typed invalidation、且当前公开 bundle 的稳定战略语义投影（慢周期闭合序列、source coverage/axis admission 语义）逐字等同时 exact carry；carry 必须保留前帧 payload/source refs/expiry 并绑定 predecessor digest。慢序列、coverage/axis 语义变化、TTL 到期、错 predecessor 或任何 invalidation 时必须刷新；`TACTICAL_DELTA/TRIGGER` 继续每轮刷新。不得仅凭 cache 命中跳过当前 bundle 完整 verifier、PIT/source admission 或物理证据保存，也不得在 fresh qualification 实测前宣称 1–2 分钟目标已达到。
- 2026-08-08：战略 carry 构造性回归又发现 production adapter 尚无 non-TTL typed invalidation 的 owning source/schema，不能用任意 PIT digest 或 Agent 自由文本伪装成“宏观/监管事件”来关闭此缺口。当前版本的诚实边界是：只接纳可由前序战略帧精确重放的 `STRATEGIC_TTL_EXPIRED`，以及由当前已验 market bundle 稳定投影变化形成的刷新；任何外部 typed invalidation 在没有事件类型、run/cycle/available_at 与 source semantics owning verifier 前一律 `UNKNOWN_NOT_AVAILABLE` 并在逐轮 data-gap/manual plan 中披露，formal acceptance 拒绝注入。未来若增加正式来源，必须用版本化 event schema/owning verifier 接线，重复、未来、过期、跨 run/cycle、未绑定或类型与来源语义不符均失败关闭；本轮不得声称八类 invalidator 已完整接线。
- 2026-08-08：逐组件 raw-first 复核确认正文虽在解析前 write-once，但 HTTP status、final URL、request/received/captured time 仍只存在于稍后的 aggregate row，崩溃可留下孤立正文。每个组件必须在解析及下一请求前发布并回读一个固定、可推导、write-once 的 capture bundle，至少包含原始 `0..MAX` 字节、正文 binding、method/path/canonical query、真实 status/final URL、request_started_at/response_received_at/capture_completed_at、attempt=1/no-retry、route/source/non-executable 边界及自摘要；正式 replay 必须从 owning store 推导路径，逐项交叉验证 capture 与 aggregate/failure receipt。缺失、篡改、交换、时钟倒退或 URL/status 不一致均失败关闭且不发第二次网络请求；崩溃尾可保留为失败证据，但绝不能被成功资格接纳。
- 2026-08-08 历史 reentry 构造性复核（当时累计 envelope=`1`，阈值现已 superseded）：action-plan 只验证前账 `cumulative_reference_risk <= max`，未在同轮把被选中正风险 `REENTER` 限于剩余额度，导致本轮可先越界、下一轮才失败。修复要求最终选择前验证绝对窗口、冷却、attempts 和本轮剩余额度；`0.75 + 0.666667 > 1` 是旧 envelope 下发现同轮越界的反例。现行阈值为每次 `<=1`、最多 `2` 次、累计 `<=2`，但“不得把本轮越界拖到下一轮”的不变量保持不变。

- 2026-08-08：commit `d5478d9463961a65d7167642c0c67e6c275f6ebf` 及 exact-commit 回归完成后，实际资格 `v32-qualification-btcusdt-20260808t150343z` 在 revision 2、PUBLIC_SOURCE 唯一 attempt 永久 `FAILED_CLOSED`；未读取 outcome、未生成 target authority/genesis、未启动实验。独立诊断表明生产 adapter 的 `ProxyHandler({})` 强制直连在当前环境超时，而同一官方 HTTPS URL 经系统公共 CONNECT 路由成功；这不是允许重试该资格的理由。新增修复验收如下：
  1. 旧失败 authority、attempt reservation、controller journal 和错误结果永久只读；新资格必须使用全新 target/qualification ID、全新 commit 和按 qualification ID 派生的独立 runtime root，不删除、搬移或覆盖旧根，也不接受调用者路径注入。
  2. bundle transport 与 outcome mark adapter 只允许同一冻结的 `SYSTEM_PUBLIC_HTTPS` 本地化策略；它可以读取标准系统代理配置用于公开 HTTPS 传输，但不得接受或记录含 username/password 的代理 URL，不得输出代理地址，不得改变 OKX host/path、允许重定向、添加重试或接触账户/订单/凭据环境变量。含凭据、非 HTTPS、非系统声明或无法验证的路由必须在物理请求前失败关闭。
  3. 每个物理请求先形成 request identity 与 attempt=1/no-retry；无响应也必须 write-once 保存 `transport-failure.json`，包含 qualification/run/component、request path/query、started/failure time、稳定顶层和因果错误码、response-present=false、body-present=false、route policy ID、source scope 与 non-executable 边界。禁止保存代理值、异常自由文本、堆栈、系统环境或秘密。
  4. controller checkpoint 必须保留可枚举的稳定 failure code 或绑定到 typed failure receipt，不能只记异常类名；故障链仍只推进一次 `FAILED_CLOSED` 边界，不重试、不将失败降为 optional UNKNOWN，也不因诊断成功重新开启旧资格。
  5. 当前环境 localization 必须进入新的 frozen `EnvironmentCapabilityProfile`，并明确“系统公开 HTTPS 路由可用”只代表当前公开 GET 运输能力，不代表来源资格、长期网络可靠性、Codex/automation 可靠性或交易权限。

- 2026-08-08：用户给出精确 V3.2 实验批准，并要求达到上下文/输出硬上限时先整理压缩、每轮保存压缩文字全流程、允许有依据的 UNKNOWN 主观评估、客观数据缺失附人工方案、工作树先提交、实验中优先自动修复并由监督 Agent 监控，以及按当前部署环境做不改变理论核心的本地化。该批准不授权截断证据、回填客观数据、修补已封存结果或扩大交易权限；所有新增条件必须在 authority 前实现、测试并进入提交摘要。
- 2026-08-08：实现复核新增两项必须在提交前关闭的 P0：Agent lifecycle 的超限路径没有实际无损分片消费闭环；outcome store 会用后来登记的 schedule set 污染历史 batch 重放。二者均属于用户已要求的容量可靠性与 16-cycle/48-outcome 主路径，不改变理论、评价、权限或实验范围。
- 2026-08-08：工作区复核新增一项必须在提交前关闭的 P0：固定的 `config/theory_paper_v32.current_research_authority.v1.json` 是提交后才生成的运行期授权物，若未精确 ignore，workspace-freeze 会拒绝自己刚生成的 authority。修复只能 ignore 该精确路径，不得像测试 fixture 那样忽略整个 `config/`，且必须用真实 Git 状态回归证明其他配置漂移仍会失败关闭。
- 2026-08-08：合同复核新增一项必须在 authority 前关闭的 P0：`authorized_revision_policy.cycle_audit_narrative_stage=POST_ACCEPTANCE_DERIVED` 只能表达 acceptance 审计，无法合法表达用户要求的 qualification/analysis/outcome/recovery 边界记录。修复必须冻结为“每份 narrative 晚于其对应 typed boundary”，并保留 acceptance narrative 只能晚于 acceptance、acceptance audit completion 控制下一 analysis permit 的更严格子规则。
- 2026-08-08：实际 commit-tail recovery 重放新增一项时间链 P0：恢复路径曾用较早的 `commit.sealed_at` 回填新建 acceptance 的 `accepted_at`，从而使 acceptance 早于本次恢复才完成的 authorized-revision registry。修复必须使用不早于全部被接纳证据与 recovery boundary 的真实恢复时间，禁止回填或伪造较早验收时间；正常提交与恢复提交都必须由同一 chronology verifier 重放。
- 2026-08-08：完整 Proposal→Selection 主链新增一项来源身份 P0：Selection packet 曾使用 dynamic-store 对 Agent delivery/consumption 的二次绑定，而 current-root mailbox 的 owning verifier 要求其自身 write-once receipt 的 exact binding，终态因 `V32_MAILBOX_STORE_SELECTION_PROPOSAL_CHAIN_INVALID` 正确失败关闭。修复必须从 mailbox 的完整 stage chain 取得并回传原始 delivery/consumption receipt binding，禁止用内容相同但物理身份不同的副本替代。
- 2026-08-08：analysis completion 映射新增一项 schema 漂移 P0：本地 lane 曾硬编码读取不存在的 `analysis_cycle_acceptance_digest`，而 owning acceptance 合同的实际字段为 `analysis_cycle_acceptance_receipt_digest`，使前序 Proposal/Selection/commit/acceptance/schedule 均成功后仍在最终 completion 失败。修复必须导入 owning `DIGEST_FIELD` 常量并由新根目录全链复验，禁止在跨层映射中复制字段名字符串。
- 2026-08-08：production wake 路由新增一项时限/互斥 P0：一个跨多次 wake 保持打开的 ANALYSIS permit 会阻止 OUTCOME lane 抢占；若其内部逐 artifact 推进超过首个 `15m` outcome 到期点，简单“恢复 active permit 优先”会把已到期 outcome 推迟到宽限期外。修复不得静默延期或并行打开第二 permit；必须把同一分析边界内连续、无外部副作用的确定性步骤合并为有上限且可从 write-once tail 恢复的 burst，只在 Proposal/Selection 外部 Agent 交付点暂停，并冻结 permit deadline/下一 outcome deadline 检查。若仍无法在宽限期内合法收口，则在读取 outcome 前明确失败关闭；无 active permit 时仍严格 OUTCOME 优先。
- 2026-08-08：用户在正式提交和实验前新增五项“易碎复杂性”复核要求，实验继续保持未开始，直至逐项裁决并关闭真实缺陷：
  1. 禁止把未校准的 `0..100` 主观确信权重经连续公式直接映射为风险或仓位；改为少数有序确信档位、实质观测机制差异门槛和离散风险上限，并加入跨周期滞回，主观判断只能在客观可用风险上限内降档或选择，不能凭单一分数放大风险；该门不声称统计独立。
  2. 复核 15 分钟节拍下的真实关键路径时延。保留防止重复计数所必需的依赖闭包语义，但静态闭包、候选全集和高周期材料必须首轮预计算并耐久缓存；Cycle 2–16 只增量更新新证据与受影响子图。冻结运行时预算、超时降级和 `UNKNOWN` 路径，禁止通过删除证据或跳过验收换速度。
  3. 冻结 `TREND_UP/TREND_DOWN/NEUTRAL/RANGE/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 市场状态。`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 强制当前方向新增风险为零；`TRANSITION` 通过方向转换证据门后才可进入 `TREND_UP/TREND_DOWN`。`RANGE` 必须与无序震荡分离，在结构化边界、成本和失效条件完整时可保留条件性均值回归路径。不得为了成对反假说强制形成方向仓，相反假说是可证伪性要求，不是多空下注义务；本实验不创建双边订单。
  4. reentry 的早期“仅同方向 canonical REENTER 计数”方案已被本记录后续“重入是受限机会而非义务”与“第二轮 reentry 构造审查”中的全方向 churn 规则 superseded：同一 instrument 使用绝对 24h 窗口；ledger `INACTIVE` 时首次 `OPEN_PROBE` 不计，激活后任一方向最终选中、合格且风险为正的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一 attempts/cumulative budget。同向恢复规范化为 `REENTER`；真实反向可以保留 `REVERSE/OPEN_PROBE` 语义，但不得免费。cluster、regime、hypothesis ID、方向或动作名变化均不得开第二本账；达到上限后原窗口终点前禁止 RESET，到期后仍须实质不同的新证据簇、可验证 regime 迁移和新 tranche 三门。禁止把“义务”解释为必须开仓。
  5. 区分当前不可执行研究 pilot 与未来执行层。当前 pilot 只能输出物理故障情景和非执行 shadow 动作，绝不能发送市价单；未来执行设计必须定义独立于 Strategy Agent 的预授权应急执行舱，按可验证持仓真值、交易场所状态和 kill-switch policy 执行 `CANCEL/REDUCE/CLOSE`，同时承认市价清仓也可能失败或产生无限滑点，不能把“核按钮”写成必然成交保证。
  6. 对用户提出的“删除依赖闭包”和“上下同时挂突破单”不直接照单执行：前者会重新引入相关证据重复计数，后者属于订单/撤单竞态且超出本实验权限。必须采用保留语义、移出关键路径的增量缓存，以及非执行条件路径/影子候选作为替代。
  7. 验收新增：理论、domain contract、Agent schema、runtime/material adapter 与测试必须使用同一离散确信/混沌/reentry 冷却语义；任何仍以连续主观分数直接决定风险、把 neutral 自动变成方向候选、允许同一簇无限重入、或声称异常市价单必然清仓的路径均为 P0。完成当前字节回归并重新取得与最终摘要一致的 V3.2 successor authority 后方可实验。
- 2026-08-08：进一步清除风险可用性中的主观数字入口（本条以最终修正语义取代早期“三类质量档”方案）。Agent 只能提交 hypothesis 的 `EXTREME_UNCERTAINTY/LOW/HIGH` 主观支持；coverage 只允许由 builder 形成 hypothesis evidence-chain `COMPLETE/INCOMPLETE` 诊断，不进入风险算术。dynamic state 未携带 source-admission coverage 时必须明确 `UNKNOWN_NOT_IN_DYNAMIC_STATE`，不得以 hypothesis refs 冒充。regime、流动性、成本与 geometry 只作 typed 硬可行性门，不再映射 `DEGRADED=50` 等客观吸引力标量；experiment contract、Agent evaluation/compiler binding、fixture 与回归必须同构。
- 2026-08-08：路径 modifier 同样只使用冻结的 `ZERO/HALF/NORMAL` 三态治理上限：`SUPPORTS_PATH=NORMAL` 仅表示不进一步降档，绝不放大；`MODULATES_PATH/OPPOSES_PATH/UNKNOWN=HALF`；`INVALIDATES_PATH=ZERO`。对 Agent 和审计界面不暴露连续数值，也禁止任何中间魔法数字或开放数值输入。
- 2026-08-08 原始方案（已被 2026-08-10 的作用域拆分修正）：当前不可执行 pilot 的 raw reference envelope 固定为精确 `1`，Agent 不得传入 `0.4`、`90` 或任何其他值；总风险只由最高主观支持上限与 OTHER/UNKNOWN residual cap 决定，随后受 path modifier 非膨胀 cap 约束。现行语义中，typed 非方向 regime 可归零当前方向风险；研究合约/压力输入真正缺失由 compiler 记为 `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 并归零当前正 reference-risk；legacy `UNKNOWN_MAX_LOSS` 与权限未知只阻断未来真实执行，不得删除当前研究方向。没有 typed owner 的流动性/成本/geometry 文字只作 guard/比较，不能自行归零候选。未来真实 portfolio 的账户风险映射必须来自另行授权的客观账户风险 adapter，不属于本实验。
- 2026-08-08：当前无执行资格，禁止用任意正整数伪造网络/API 延迟能力。hazard 必须保存 `future_latency_bound_ms=null`、`latency_qualification_status=UNKNOWN_NOT_QUALIFIED`、空 latency refs，并保持 execution gate blocked；只有未来另行执行授权且完成真实测量资格后，才可在新版本合同中封存非空界限。
- 2026-08-08 历史方案（已被全方向 churn 规则 superseded）：早期只计算 canonical `REENTER`，并要求恢复性 `OPEN_PROBE/REVERSE` 先改名；该规则会让真实反向动作在改名语义与免费次数之间产生冲突，现已废止。当前规则是 ledger `INACTIVE` 时首次 `OPEN_PROBE` 不计；激活后任一方向最终选中、正风险且合格的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一 instrument attempts/cumulative budget，同向恢复仍规范化为 `REENTER`，真实反向保留动作语义但不免费。初始 source tranche 止损/退出后的观察预算仍为 `AVAILABLE / attempts=0 / consecutive_failures=0 / cumulative=0`，obligation 永不强制入场；当前不可执行 pilot 不把计划计数冒充实际成交或仓位，未来 executor 必须另以 fill/position truth 计数。
- 2026-08-08：future-only physical escape 合同必须可操作且保持非承诺：未来另行取得执行授权后，仅当 venue 支持原子 attached protection 时才允许与入场同请求，并独立确认保护最终状态；不支持原子附带保护的执行模式默认禁止新开仓，不能假设零持仓时先挂 reduce-only。若发生 fill→保护确认间隙，立即标记 `UNPROTECTED_EXPOSURE`、冻结新增风险，按预授权 reduce-only close/reconciliation 处理；只有另行授权才可进入 market fallback。venue 不可用时保留 unresolved exposure、告警并人工升级，绝不保证成交价或最终清仓。当前 pilot 仍无订单能力。
- 2026-08-08：上述第 1、3、4 项已经进入最小闭合实现：旧连续主观数字字段不保留兼容别名；三档确信、严格市场 regime 与耐久 reentry 防磨损状态由各自 owning domain contract 管理，并贯穿 Agent 编译、跨周期 continuity 和聚焦测试。当前仍须完成最终全量回归、提交和 post-commit replay，不能据局部 PASS 生成 authority。
- 2026-08-08：正式 analysis lane 新增材料端口接线要求：production `V32AnalysisMaterialPort` 必须只从 full-loader 已验证的 target authority projection、冻结理论/支持文档、当前公开 bundle 和耐久前序工件构造 timeframe、完整 Proposal canonical packet、必要时的无损 context package、七类 authorized-revision material 与固定 `15m/1h/4h` 绝对 outcome schedule；不得依赖测试 fixture、伪造 Strategy Agent 的主观 UNKNOWN/Proposal/Selection 输出或联网。必须提供只读 Proposal/Selection mailbox canonical request，供当前唯一 Strategy Agent 人工生成语义输出。当前状态：材料端口、只读 mailbox、理论语义双重绑定及 outcome receipt material 接线已完成；真实形态小型公开 fixture 回放 `4/4 PASS`，authority/full-loader 聚焦回归 `22/22 PASS`。本项未生成正式 authority/run；在整个 V3.2 工作树完成验证并提交前仍不得开始实验。
- 2026-08-08：target run 新增可信 genesis 与 production composition P0：初始 timeframe 必须是 owning verifier 可重放的 typed entity，禁止任意 64hex；write-once genesis receipt 必须由 composition 内部完整 loader 返回的五份 target projection 构造并绑定各自 exact local copy 的 semantic/physical identity、`16/48` 实验范围、初始 timeframe 以及 dynamic/outcome/supervisor 三份 revision-0 immutable checkpoint。全部 copy/readback/replay 成功后才可原子发布唯一 current-run pointer；相同调用幂等，run 或 pointer 冲突失败关闭。调用者不得注入 authority 文档、authority digest 或 wall clock，composition 只能使用 System UTC 且保持 public/local/non-executable。本项只实现和离线验证生产路径，不联网、不创建真实 authority/run；当前状态：可信 genesis、唯一 pointer、内部 System UTC composition、pre-source timeframe 与 cycle-0 audit 阻断已完成，联合聚焦回归 `40/40 PASS`。未生成真实 authority/run，未联网，未提交。
- 2026-08-08：可信 genesis 还必须把 `cycle_index=0` qualification boundary audit 冻结为首个 analysis permit 的硬前置。Genesis 不得自称 audit 已完成；必须耐久暴露 full-loader 已验证的 qualification retirement、target authority local copy 与 run-genesis binding，供独立 audit owner 在 genesis 后生成 typed completion。current-run pointer 必须明确保持 `BLOCKED_PENDING_QUALIFICATION_BOUNDARY_AUDIT`，直至 Application permit gate 重放该 completion；无 audit 不得开始 cycle 1。
- 2026-08-08：初始 timeframe 时序纠正：target composition 不得接受调用者提供的 cycle-1 `FULL_CONTEXT`、market payload 或 bare digest，因为正式来源资格尚未发生。完整 loader 通过后只能由 production composition 内部构造封闭 typed `UNINITIALIZED_PENDING_FIRST_FORMAL_SOURCE` genesis entity（run/cycle 1、无市场值、无 payload/digest 占位），并由 Supervisor genesis 绑定其真实 self-digest；首个 analysis source lane 后续才可生成真实 `FULL_CONTEXT`。
- 2026-08-08：新增独立最小 cycle-0 qualification audit owner：production API 仅允许 `project_root`、`expected_run_id`，必须先完整 loader，再只读重放 sole current-run pointer/genesis，从封存 binding 精确读回 qualification retirement、target-authority local copy 与 run-genesis，使用内部 System UTC 通过 `LocalV32BoundaryAuditLane` 生成或重放 `QUALIFICATION / cycle_index=0` 中文压缩审计。缺件、错 run、摘要或物理漂移均失败关闭；重复调用幂等。不得修改 genesis/pointer、不得联网、不得创建真实 run、不得启动或打开 cycle 1 permit；只有 audit bundle 耐久存在后，router 才具备允许首个 permit 的必要条件。
- 2026-08-08：cycle-0 qualification audit owner 已完成最小生产接线，并新增非创建型 `replay_v32_target_run_from_current_authority_v1(project_root, expected_run_id)` 供 wake owner 在不调用 genesis initializer 的前提下完整重放唯一 pointer/genesis。聚焦回归 `4/4 PASS`：审计前 router 拒绝首次分析；审计后只满足 permit 必要门槛且测试 runner 未实际开 permit；三源中文 13 节 bundle 耐久存在；重复调用不再读取时钟；genesis/pointer 字节不变；missing/wrong-run/local-copy tamper 与 caller time/docs 注入均失败关闭。未创建真实 authority/run、未联网、未开始实验。
- 2026-08-08：V3.2 新冻结清单新增 production-entrypoint AST/local-import closure 要求：必须以 current-authority loader、actual-capability qualification controller、target genesis/qualification audit composition 与 target wake composition 为根，冻结所有本地可达路径；不得只枚举少数 helper，也不得修改旧 V3.1 `74` 路径清单或字节。实测发现 `presentation/__init__.py` 的 legacy report eager import 会把动态 bootstrap 错误带入 V3.2 闭包，已收敛为 side-effect-free namespace；仓内无 package-level legacy report 消费者，legacy API 仍可从 `presentation.report` / `presentation.formal_report` 直接导入。加入 Application capability ports 与 Domain attempt-progress 合同后，当前 `32` 个 production roots 的真实 AST/local-import closure 为 `186` 路径，包含两份新增分层文件；最小 fresh-trace roots 重建的 frozen binding key set 与 closure 精确相等。本项未修改旧 V3.1 `74` 路径清单/字节，未生成 authority/run，未联网，未开始实验。
- 2026-08-08：真实 clean-workspace 演练发现，用户明确要求保留的未跟踪副本 `THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md` 与 Phase A 的“status 必须全空”冲突。允许范围只能是这一条精确路径：状态必须为 `??`、普通非 symlink 文件，并把当时物理 SHA-256 写入 workspace-freeze receipt；任何其他未跟踪、tracked/index/config/code 漂移继续失败关闭。不得将该文件删除、提交或泛化为 ignore 规则。
- 2026-08-08：风险可用性最终复核确认，哪怕只保留三档，若 `coverage/regime-liquidity/geometry` 仍形成 0/50/100 风险标量，它们仍是离散“魔法旋钮”。最终设计只确定性派生 hypothesis evidence-chain 诊断并由 verifier 重算；source admission 不在 dynamic state 中则保持 UNKNOWN；regime、流动性、成本和 geometry 只作 typed hard gate。主观形态吸引力只存在于三档 hypothesis tier。其后以真实 formal OKX 图复核发现 `605/605` 条 closure 共同含 `VENUE:OKX`，旧“完整 closure 全不相交”会令 HIGH 结构性不可达。修正后，初始 `HIGH` 或 `LOW→HIGH` 至少需要两个 fresh refs、明确方向性反证与 `mechanism-distinct evidence`：完整 dependency/provenance closure 不删除，只在配对判定时忽略共同 `VENUE/PROJECTION`，同时要求其余物质依赖不相交、不同 `REQUEST` 和不同方向性 `OBSERVABLE_FAMILY`。`TICKER/MARK/CANDLES` 同属 `PRICE_ACTION`，metadata/spec 不得作为方向支持或反证；该门不等于统计独立。非方向 regime 恢复为方向 regime 同样需要该双机制差异证据，或冻结的连续两根闭合 15m bar 机械证明。
- 2026-08-08：性能 P0 的旧证据为 core 长测 `>5m` 尚未完成、fixture≈`216s`、receipt body≈`32s`，测试体累计 `59,018` 次 canonical serialization 与 `28,822,997` 次 normalize；根因是同一不可变对象在 lifecycle/acceptance 级联中重复完整规范化。最终 memo 使用同一递归精确内建对象快照完成 key 与 verifier，custom Mapping 不缓存，owner 同时绑定 thread/asyncio task，scope 退出清空，失败不缓存且不跨调用/线程/task/process；context shard 可用精确增量 size，但最终仍完整 build/self-digest/actual-byte replay。严格复测为 affected core `73/73 PASS / 154.221s`、目标慢测 `44.255s`、独立 TOCTOU/custom-Mapping/thread-task/shard `4/4 PASS / 42.327s`。这些仅关闭本地重复计算缺陷，不证明 fresh process/跨唤醒、真实 Codex/网络、15 分钟端到端资格、预测或实盘能力。
- 2026-08-08：actual-capability 端到端演练新增 production qualification P0：现有底层 controller/ports 未形成固定 production composition；CURRENT_CODEX 没有真实 Proposal materializer/交付入口；OUTCOME_MONITOR 测试用任意 digest 和普通 `16/48` schedule 伪装资格；target production loader 又未固定 owning replay registry。修复必须增加只接收 project root/expected run IDs 的固定入口，从 PUBLIC_SOURCE 的真实 durable replay 物化 `V32_QUALIFICATION_CONTEXT_PROFILE` packet，由当前 Codex 完成一次 Proposal/Selection，另用显式授权的单次 `QUALIFICATION_MONITOR_PROBE` 在绝对 15m 到期点读取一次公开 mark。该 probe 不属于、也不得计入正式 48 个 outcome，qualification authority 继续保持 `outcome_schedules=0`。
- 2026-08-08：actual-capability 最终 seal 发现失败原子性 P0：旧路径在验证循环中逐份写三张 capability receipt，任一 duration/full-replay/后续写入失败会留下部分文件并让 `READY_TO_SEAL` 再次进入同一逻辑。正式修复必须先完成全部内存验证、owning full replay 和目标路径 preflight，再单批次封存；任何异常只允许 controller 追加一次永久 `FAILED_CLOSED`，后续 wake 禁止重试。Current Codex 的 `>660s` 端到端硬门保持不放宽。
- 2026-08-08：最终分层回归先发现 actual-capability Application 直接导入 Infrastructure。已拆为 Application-owned Protocol、Domain 纯 attempt-progress verifier 与 Infrastructure 固定 EvidenceStore/replay 实现；22 个 Application V3.2 根、48 个递归可达本地模块的反向 Infrastructure/Presentation 边为零，公开 production API 未增加 registry、adapter、路径或时钟注入口。
- 2026-08-08：两次独立资格复核又发现并关闭两个 P1。其一，畸形短 binding 可在 progress 后、checkpoint 构造前逃逸而不耐久失败；其二，字段完整但路径不存在或物理身份不成立的 binding 可凭匹配 semantic digest 推进 capability。最终合同要求 exact 五字段 binding、resume token/time 成对、`COMPLETE` 清空 resume；controller 在 `ATTEMPT_COMPLETED` 前经固定 EvidenceStore 和 owning verifier 物理重开，核对规范路径、schema、digest field、语义/物理摘要、canonical bytes、完整 root 与 capability 专属 `root_ref`。任一异常只追加一次永久 `FAILED_CLOSED`，后续 wake 不再调用 adapter、也不推进下一 capability；独立复核 `5/5 PASS`。

### 2026-08-07 V3.2 P0-8/P0-9 耐久监督与单边界组合需求

- 最终交付：让研究 store 只能接受经过完整重放的实际 V3.2 cycle acceptance；新增 write-once/CAS Supervisor store；由唯一 Application coordinator 在一次 wake 中只打开并完成一个 `ANALYSIS_TICK` 或 `OUTCOME_TICK` 边界。
- 验收标准：analysis acceptance 不得缺失或使用旧 schema；必须从耐久原件重放 proposal/selection 语义输出与编译收据、compiled state、sealed evaluation、两类 continuity、Supervisor permit、commit 和 schedule。任何缺件、摘要/物理绑定漂移或重放失败均失败关闭。
- 崩溃恢复：只有已耐久的 two-stage commit 及其确定性嵌入对象可用于恢复；恢复必须构造并重放与正常路径相同的 acceptance。无法确定性重建时必须把 research store 标为 `FAILED`，不得把 `acceptance=None` 降级接受。
- Supervisor store：持久化 genesis/current checkpoint、permit、completion checkpoint 和 failure；所有状态推进使用 predecessor digest CAS，permit/failure/历史 checkpoint write-once，stale CAS 和第二 active lane 必须拒绝。
- Coordinator：依赖注入 analysis/outcome 子流程与各 store port；exact permit 必须传入子流程，子 store 成功提交后才允许 Supervisor complete。一次 wake 最多一个状态边界，不得同轮分析和 outcome、不得重试、不得并行推进。
- Outcome：正式组合入口必须验证 exact Supervisor predecessor/open checkpoint/permit，不能独立绕开 Supervisor；runtime 初始化必须绑定合法 Supervisor genesis/current outcome digest，不能凭空创建 `ACTIVE`。
- 故障注入：覆盖无 acceptance、commit-tail 崩溃、stale CAS、双 lane、同 wake 双边界、permit 篡改、子 store 已成功但 Supervisor 尚未 complete 的确定性恢复。
- 当前范围：仅本地、公开数据、不可执行；不联网、不生成 authority/run，不修改冻结实验，不接触账户、订单、凭据、资金、fill 或 PnL。
- 当前状态：已实现并通过 V3.2 `306/306` 与 Theory Paper V2 `991/991` 回归；V3.2 authority/qualification/experiment 仍未开始。
- 需求变更记录：2026-08-07 用户在 V3.2 实验前要求关闭 P0-8/P0-9，取消旧 dynamic store 的可空 acceptance 和 outcome runtime 的独立 ACTIVE 路径，并以单 Supervisor/单 wake/单 boundary 作为唯一正式组合入口。

### 2026-08-07 历史 V3.1.1 后继实验授权与验收冻结（已被 V3.2 取代）

本节保留 V3.1.1 在当时获得的授权与 `8/8` 完成标准，只作为历史谱系；它不授权 V3.2，也不是 V3.2 的现行验收。V3.2 已改变行为域、周期数、outcome 数量和 runtime 摘要，必须在最终理论与实现摘要确定后取得新的明确批准。现行候选为 `16` 个 analysis cycle、每轮 `15m/1h/4h` 三个事前 schedule（共 `48` 个），仍只构成流程与短窗判别 pilot。

- 用户授权当前 Codex 作为同一 Strategy Agent 持续完成下一步，直至目标实验完成；授权只覆盖公开市场数据、本地研究、不可执行的后继实验，不覆盖 paper/live、账户、订单、凭据或资金。
- 旧 run `v31-prospective-btcusdt-20260806t183742z` 永久保持 `FAILED_CLOSED`、`attempt=1`、`outcome=0`、`resume_allowed=false`，不重试、不修补、不改写、不作为后继实验已完成样本。
- successor 必须与旧冻结 runtime 并存：新增版本化合同、适配器、监督门、资格和 authority；旧 `74` 个 runtime 路径及其摘要保持可重放。
- 当时目标实验的完成标准冻结为：同一 V3.1.1 successor run 内 `8/8` 个正式 accepted cycle 与对应 `8/8` 个合法 outcome 全部耐久完成。该标准已被 V3.2 变更取代，不得用于生成 V3.2 authority 或完成声明。
- 任一 outcome 必须先 write-once 保存 transport/raw capture，再做 schema、数值和时间语义解析；无 HTTP 响应时也必须保存 transport-failure receipt。解析失败不得丢失原始证据，也不得对同一 sealed attempt 重试。
- provider timestamp 与本地 receive time 必须原样保存；允许范围、超界行为和质量语义须在新 authority 前冻结，禁止静默夹取或事后修改规则。
- 统一 supervisor 是进入 source qualification、formal prepare 和 Agent 阶段的机械前置门：上一 accepted cycle 无合法 outcome、monitor 为 `FAILED_CLOSED`、checkpoint 不一致或 run 已终局时，下一周期必须拒绝。
- 若 successor 暴露新的内部设计缺陷，只能保留失败证据、版本化纠正、重新资格并取得新的唯一 run；外部 403、网络长期不可用或合法数据源限制等不可控边界则如实报告，不绕过权限或伪造完成。

### 2026-08-07 全部已知缺口的新增收口范围

用户要求在 P0 设计缺陷与实验故障之外，继续收口十二轴、关联预注册、fresh 资格和评价证据，并在完成后全面检查、记录日志和清理工作区。具体边界冻结如下：

- 十二轴原生外部来源：为十二个市场情绪轴分别建立“直接公开来源、可计算代理、推断、UNKNOWN”四级来源矩阵；每个周期保存 source/available-at/missingness/quality，不得把缺失轴迁移值冒充原生来源。
- 十二轴图投影：信息事件、PIT datum、轴状态、轴变化、假说、预期、路径与动作之间必须形成 typed edge 和 projection receipt；同一证据对多个轴的贡献须保留共享来源，不得复制成独立证据。
- portfolio/reentry 决策（历史 V3.1.1 边界，已被下方 V3.2 变更取代）：当时 successor 为无账户、无持仓、不可执行的 public-data-only 研究，故标为 `EXCLUDED_NO_CLAIM`。当前 V3.2 已把 `HOLD/REDUCE/CLOSE/REENTER` 纳入条件研究计划及影子比较，但仍不创建账户持仓、成交、PnL 或组合写回接口；任何真实或 paper 执行仍须独立合同与新授权，不能借当前 run 暗接。
- 关联预注册：Phase A 前必须显式冻结候选变量全集、pair family、方向性/非方向性用途、滚动窗口、滞后、最小有效样本、缺失处理、多重检验、效应量/不确定区间与版本；观察结果后不得删候选、换窗口、换 lag 或改校正方法。相关只用于描述与假说发现，不直接充当因果、概率或动作信号。
- fresh 资格：新 run 必须重新完成公开来源的单次耐久采集、当前 Codex proposal→compile→post-seal selection 的真实交付、capture-only fixed outcome monitor 及 crash/no-retry/时钟边界资格；旧 Q6/Q7/Q8 不得代替 successor 新能力资格。
- 评价证据：新增预注册评价合同和可复算日志，但在样本不足前继续标记 `UNKNOWN_NOT_EVALUATED`。当前系统不输出未校准数值概率，因此 Brier/ECE 不得伪算；只有后续存在事前定义、互斥完备且样本足够的概率预测时，才可进入校准评价。成本后收益和跨 regime 泛化同样只能由足量数据证明。
- 全面检查：完成 focused failure-injection、完整 successor suite、旧冻结回放、authority/import closure、artifact tamper、单 active automation 和全链状态一致性检查；报告测试范围与未覆盖外部边界，不以测试数量代替实验结果。
- 日志与清理：写一份可追溯实施/资格/实验日志，记录每个已知问题、根因、版本化修复、验证和剩余证据状态。工作区只做非破坏性清理：移除本任务明确生成且可重建的临时文件，停止过期自动化，保留失败 run、资格证据、用户文件和既有未提交改动；任何既有文件删除必须先列精确路径、影响与恢复方式。

### 2026-08-07 实验前 V3.2 激进动态变更

用户要求去掉把 WAIT 当作默认正确答案的过度保守倾向，并在实验前完成以下理论与系统变更。该变更优先于既有 successor 实验启动；任何资格或正式样本都必须使用变更后冻结版本：

- 核心目标由“证据充分后才承担风险”改为“在证据不完备但风险可定义时尽早获取小额、可撤销的方向暴露，并用后续证据持续扩仓、减仓、退出或反转”。UNKNOWN 仍必须保留，但 UNKNOWN 不自动等于 WAIT；只有损失边界、数据真实性或动作合法性未知时才强制 WAIT。
- 历史形态、密集成交区、前高前低、整数关口和反复测试点位纳入反身性与流动性假说：它们可能因为参与者共同关注、挂单、止损和仓位调整而产生磁吸、阻力、支撑或突破加速度；不得预设“60% 的交易者都在看”或把相关形态直接写成因果，必须同时保留突破/假突破/失效的竞争路径。
- 假说体系固定区分现状假说、归因假说、预测假说和行为规划；每个方向性主观假说必须有至少一个方向相反的竞争假说，并始终保留 OTHER/UNKNOWN。参与者动机只能作为可检验的行为一致性推断，不能伪造主力、机构或人群身份。
- 主观确信度允许影响研究动作优先级，但不得伪装成已校准的市场发生概率。系统只使用有依据、可修订的三档 `subjective_plausibility_tier`；档位仅能作为客观可用风险的离散上限，必须先按同源证据、相关方向和共同失效条件去重/聚类，同簇或同向档位均取最大而不相加。
- 动作空间扩展为 `OPEN_PROBE / ADD / HOLD / REDUCE / CLOSE / REENTER / REVERSE / WAIT` 的研究规划。`HOLD` 必须与 flat `WAIT` 分离，避免重现历史上把有敞口维持误判为等待义务的已知故障；`OPEN_CORE` 归入有新增证据的 `ADD/promote`，`PARTIAL_HARVEST` 归入 `REDUCE` 管理事件。当前授权仍是 public-data-only、local、non-executable：只生成可审计的条件动作计划和风险预算，不连接真实账户、不发送订单、不把计划当作成交或收益；若要建立带撮合和资金曲线的 shadow/paper portfolio，须另行明确授权并冻结独立实验合同。
- 仓位不再固定为永远 2%，而由总风险预算、失效距离、波动、流动性、假说确信档位、相关暴露和已有浮盈共同决定。先行试探仓必须较小；只有新增证据到达且原假说未被否证才允许金字塔加仓；禁止亏损摊平伪装成加仓，禁止用“市场赚来的钱”否认浮盈回撤仍是账户损失。
- 退出由结构失效、波动尺度、流动性、时间止损、事件风险和成本共同驱动。`+3% 即移动到成本、+8% 移到 +5%` 等只能作为待检验候选，不是跨资产硬规则；移动保护不得因短周期噪声、价差或跳空制造必然被扫，也不得向扩大风险方向移动。
- 多时间框架采用分层缓存：慢变量和宏观/日线状态在首轮或发生事件时重算，后续 15 分钟/事件轮只更新新数据、轴变化、假说确信档位和动作计划。日线用于方向先验和风险不对称，不使用“日线上涨绝不做空/下跌绝不做多”的绝对禁令；15 分钟触发可以抢跑，但必须绑定更高周期冲突惩罚和较小初始风险。
- RSI 纳入短周期状态证据和背离/失效候选，但优先级必须由 regime、趋势强度、波动和前向实验决定；超买不直接等于做空、超卖不直接等于做多，也不得因用户偏好预先保证其排名靠前。
- 现有用户给出的月度/年度收益区间没有前向数据、费用模型和分布证据，记录为未经验证的直觉估计，不进入理论事实或验收承诺。V3.2 的六臂比较冻结为 `V32_SELECTED_PLAN / V31_CONSERVATIVE_WAIT_BIASED_REFERENCE / WAIT_ONLY / SIMPLE_15M_TREND / NO_RSI_REFERENCE / ALWAYS_LONG_PUBLIC_MARK_REFERENCE`；当前只有终点方向一致性和 coverage 可算，路径、MFE/MAE、fill、position、PnL、数值概率和 EV 均保持 UNKNOWN/禁止。样本不足时预测增量、成本后收益与跨 regime 结果仍为 `UNKNOWN_NOT_EVALUATED`。
- 当前目标实验的样本数、周期频率、outcome 定义和完成标准必须在 V3.2 行为合同完成后重新冻结。不得沿用为了 V3.1.1 设计的 `8/8+8/8` 就宣称已经评价动态加减仓、再入场或收益；如继续以八个周期做首轮，只能称为流程与短窗判别 pilot，不能证明盈利、校准或泛化。

### 2026-08-07 V3.2 第二轮风险缺口与需求变更

用户在 V3.2 实验启动前新增五项必须处理的问题：流动性幻觉/假突破、权重归一分母陷阱、长期无动作造成的机会成本与模型休眠、未来执行中的 API/网络延迟，以及假说路径依赖和过期。它们继续优先于 qualification 和正式实验；处理方式冻结如下：

- **磁区不是主力护盘事实**：历史区域只证明参与者可能聚集注意力和条件订单，不能识别挂单归属、隐藏流动性或机构意图。每个 zone 必须同时保留 rejection、absorption/break、false-break/stop-run 和 no-effect 路径，并新增 typed `ExternalPathModifier/MarketHazard` 表示假突破、止损级联、流动性真空、跨场错位和 venue disruption。modifier 只影响与其共享 zone、数据或执行依赖的假说/计划，禁止用一个模糊“庄家收割”故事无差别改变全部确信档位。
- **禁止相对归一放大全部风险，也禁止把独立证据误算成胜率相加**：cluster 内及同一方向均按三档确信取最大档，不做数值求和；`EXTREME_UNCERTAINTY / LOW / HIGH` 对 Agent 与审计界面只表达 `off / probe / normal` 的离散上限，其中 HIGH 也不能放大覆盖、regime、流动性、几何或最大损失所给出的客观上限。LONG/SHORT 对立分支不得相加；OTHER/UNKNOWN 的最高档位反向限制总风险。确定性内核可以用冻结的离散 tranche 单位切分已经获批的包络，但不暴露连续分数，候选数量或分母变小不能提高总预算。
- **方向候选完整不等于强制交易**：方向性分析应维护 LONG/SHORT 竞争候选，但允许一侧或两侧为 `EXTREME_UNCERTAINTY`、不可行动或仅为 residual template。禁止为了满足“总有做多假说”而伪造正证据、最低仓位或强制开仓；长期无动作通过分析/影子计划/基线 outcome 持续验证，而不是用本金购买样本。
- **无动作监督而非仓位下限**：每轮仍更新假说、磁区、机会成本和 shadow baselines；使用两只互不替代的耐久时钟：风险计划时钟只由合格且有正风险预算的 probe/reentry 重置，模型适应时钟只由新鲜 PIT 证据绑定的实质性状态、zone、假说或阈值变化重置。任一连续 `8` 个周期或 `7200` 秒（任一先到）触发对应 `INACTIVITY_REVIEW`，且两类计数必须从 durable previous action plan 推进，Agent 不得自行重置；普通市场变化、换 ID、改写文字和无关新引用均不能洗掉计数。复核要求重检 regime、阈值、数据覆盖、替代市场/时间框架候选和 WAIT 的机会成本。它可以生成只对未来生效的方法候选，但不得看 outcome 后改旧规则，也不得强制产生交易。现金/通胀机会成本只有在基准资产、计价单位和可比收益被冻结后才能量化。
- **止损是触发器，不是成交保证**：当前 public-only run 只建模未来执行 hazard，不连接 API。计划风险必须包含 stop-through、gap、排队、限频、网络/venue 不可用、cancel/replace 竞态和保护 ACK 未确认分支；任何止损价都不得被描述为保证成交价。未来若另行授权执行，仅允许支持原子 attached protection 的模式随入场同请求并独立确认；不支持则默认禁止新开仓。fill→保护确认间隙属于 `UNPROTECTED_EXPOSURE`，必须冻结新增并按预授权 reduce-only close/reconciliation；只有独立未来授权才可降级为 market fallback。venue 不可用时保留 unresolved exposure、告警并人工升级；交易所级故障无法由本地系统完全消除，也不得保证成交价或最终清仓。
- **期限终止旧假说的行动权**：每个假说已有 absolute expiry；到期未证实/未证伪时不得原样继续 ACTIVE，也不得靠改时间戳洗白。运行状态必须转为 `EXPIRED` 并撤销依赖它的未触发计划；`STALE` 只允许作为触发复核的原因标签。若继续研究，必须以新的 revision、新 evidence、重新检查 regime/zone 和新的 expiry 重新立项。固定“到期降权 50%”作为待比较 policy arm，而非通用真理；不同假说类型和时间框架须预注册 TTL/衰减规则。
- **假突破后的恢复**：为避免紧止损被扫后永久错过方向，退出与父 thesis 分离；若 false-break 路径成立且父 thesis 未失效，系统可以建立有界的 `ReentryObligation` 观察/复核机会，重新计算当前 zone、成本、风险和证据后才可能再入场。该对象永不强制开仓；没有合法机会时可不创建，不得回写旧 tranche 或自动报复性加仓。
- **重入防磨损参数不得由 Agent 注入**：当前 pilot 的 `ReentryBudgetState` 是每个 instrument 唯一的全局 churn breaker，固定使用每次 reference risk `<=1`、最多 `2` 次、累计 `<=2` 与精确 `24h` 滚动窗口。ledger `INACTIVE` 时首次 `OPEN_PROBE` 不计；激活后任一方向最终选中、正风险且合格的 `OPEN_PROBE/REVERSE/REENTER` research tranche 都进入同一本账并消耗 attempts/cumulative。只有同向恢复必须规范化为 `REENTER`；真实换向可保留 `REVERSE/OPEN_PROBE` 语义，但不得免费。方向、cluster、regime、hypothesis ID 或动作标签变化不得清零或建立第二 ledger。达到两次或累计上限后必须进入耐久 `EXHAUSTED`，其 cooldown 精确等于原 24h rolling window 的绝对终点；更短或更长都拒绝，且原窗口终点前禁止 RESET。窗口到期后仍须实质不同的新 cluster、可验证 regime 转换和新 tranche 三门，不能自动解锁。这里的 attempt 只是不可执行 pilot 中的 accepted research-tranche 防重复计数，不是成交、真实止损或账户磨损；未来 executor 必须另以 fill/position truth 计数。
- **客观质量不得成为主观旋钮**：不再维护 coverage、regime-liquidity 或 geometry 的可选风险档位，也不存在跨轮“相邻变档”。hypothesis evidence-chain coverage 是 builder 重算的诊断；source-admission 缺失保持 UNKNOWN；regime、流动性、成本与 geometry 由 typed validator 决定通过或阻断。初始 HIGH/LOW→HIGH 的双 fresh `mechanism-distinct evidence`、显式方向性反证，以及非方向→方向的同门证据/连续两根闭合 15m bar 是跨轮提升的硬门。完整 closure 保留；配对门只忽略共同 `VENUE/PROJECTION`，要求其余物质依赖不相交、不同 REQUEST 与不同方向性 OBSERVABLE_FAMILY。价格家族内部不能自证，metadata/spec 不能充当方向证据；“机制不同”不声称统计独立。
- **双看门狗阈值冻结**：当前 pilot 只能使用精确 `8 cycles / 7200s`，首轮和后续轮均不得由 Agent 或 fixture 覆盖；跨轮仍须重放 durable previous action plan 防漂移。

新增验收：至少加入绝对风险缩放的单假说低权重反例、zone false-break/modifier 依赖范围、inactivity review、假说 expiry/renewal 防洗白、stop-not-fill/venue-unavailable 压力分支的确定性测试；这些测试只能证明合同和恢复行为，不能证明真实交易所可用或策略盈利。

验收标准：先交付 V3.2 理论文档、用户建议逐条“采纳/修正/拒绝”表、行为规划与风险预算合同、时间框架缓存合同、历史磁区/RSI 假说合同和更新后的实验设计；完成代码实现、故障注入和全链回归后，才允许冻结新 authority 并开始 qualification。实验启动前不得产生正式市场 outcome。

## 以下为历史 V1 六市场纸面实验需求（已废止，不是 V3.2 当前范围）

以下“纸面账户、六市场、72 小时”等内容保留为需求演化证据，已被文件顶部的 V3.2 `BTC-USDT-SWAP / PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION` 当前范围取代。后续 Agent 不得据此建立账户、订单、成交、PnL 或恢复旧实验。

## 一、最终交付结果（历史）

交付一个仅使用公开数据、本地纸面账户运行的 Agent：

- 每小时分析 `SNDKUSDT`、`MUUSDT`、`BTCUSDT`、`ETHUSDT`、`SOLUSDT`、`HYPEUSDT`；
- 使用尚未成熟的新理论作为主要分析方法，旧系统仅提供数据、风险和记录支持；
- 分析行情原因、消息、情绪、参与行为、K 线、订单流、持仓量、资金费、趋势、阶段、点位和未来买卖力量；
- 主动提出可证伪假说，并持续支持、修订或否定；
- 执行本地纸面交易，设置止损、止盈和仓位风险；
- 每 8 小时复盘交易与方法论，量化评价理论和实践流程；
- 连续运行 72 小时后形成实践总结。

## 二、初始账户

- 初始资金：10,000 USDT。
- `SNDKUSDT`：多仓 500 USDT，入场 1125；初始限价买单 300@1006、300@920、500@860。
- `MUUSDT`：无初始仓位；Agent 可以主动开仓。
- `ETHUSDT`：多仓 1000 USDT，入场 1920；初始限价买单 300@1850、卖单 1000@1965。
- `SOLUSDT`：多仓 800 USDT，入场 75；初始限价买单 1200@68、卖单 1000@83。
- `BTCUSDT`：多仓 1000 USDT，入场 64000；初始限价买单 1000@60200、卖单 1000@66000。
- `HYPEUSDT`：多仓 800 USDT，入场 55；初始限价买单 800@51、卖单 1000@73。
- 初始仓位均未预设止盈止损，首轮必须保护、减仓或退出。

说明：`SNDKUSDT` 按 Binance USDⓈ-M 股票永续衍生品处理，不将其描述为美股现货所有权。

## 三、实践要求

1. 新理论优先：分析和决策尽量使用新理论的测量链、多尺度结构、竞争路径和动态假说。
2. 积极实践：不能以“不确定”为由停止分析或长期不交易；有完整触发和风险边界时应主动执行。
3. 受控冒险：允许小仓试探和受控的情绪化额外交易，但不得突破组合风险、数据有效性和止损硬约束。
4. 完整解释：区分事实、计算和推断；参与者分析只能描述行为一致性，不伪造身份。
5. 首轮责任：为全部现有仓位设置保护，并逐笔保留、修改或取消初始挂单。
6. 复盘沉淀：总结找点位、止损止盈、仓位、趋势、假说生成、方向选择和消息关联的具体方法。
7. 量化改进：低分项必须定位到具体流程、公式、数据或执行阻塞，并给出下一窗口的改进候选。

## 四、评分与结果分离

每 8 小时分别报告：

- 理论完整性评分：测量链、多尺度、结构、竞争路径、行为边界和交易几何；
- 方法实践评分：证据、竞争假说、否证、点位、风险、行动及时性和复盘学习；
- 假说结果：已支持、已否证、到期未支持和未解决；
- 纸面绩效：净收益、回撤、胜率、盈亏比、profit factor、R、手续费、滑点、MFE/MAE 和持仓时间。

盈利不能掩盖理论或方法错误，亏损也不能自动证明理论无效。

## 五、验收标准

- 六个标的均产生完整、可追溯的每小时分析；
- SNDK 初始价为 1125，MU 无初始仓但可交易，HYPE 纳入完整流程；
- 首轮现有仓位均被保护、减仓或退出，全部初始挂单均被审查；
- 新增风险均有父假说、触发、止损、止盈和成本后至少 1.5 的盈亏比；
- 每 8 小时形成四类分离结果和一项只对未来生效的方法改进；
- 所有订单、成交、仓位、假说和复盘都有本地审计记录；
- Agent1 首轮形成一份按时间、标的和动作可核验的中文执行报告，列明所用事实、计算、决策理由、替代假说、否证条件和理论来源；
- 后续每轮定时交易均自动生成对应时间的中文文档，覆盖执行记录、可审计决策轨迹和理论依据来源；记录不得以模型不可验证的隐藏思维文本代替；
- 每轮中文文档必须按 lot 完整输出：标的、方向、来源、状态、精确开仓时间与开仓价、基础资产初始/剩余数量、入场名义 USDT、标记价格、当前持仓价值 USDT、未实现和已实现盈亏、收益率、手续费、MFE/MAE、止盈止损触发价、预计成交价、受保护数量及其 USDT 名义、剩余风险与成本口径；
- 每轮中文文档必须完整输出历史交易信息：订单、成交、开平仓、部分成交、取消/拒绝、价格、数量、USDT 名义、手续费、滑点、归因、父假说、时间和当前状态；没有记录的字段必须明确为无或未知，不得省略；
- Agent1 首轮必须生成包含上述标准账户字段的新版中文完整记录，并明确列出五个初始仓位的具体开仓价格；
- 不读取私有交易账户、不使用密钥、不发送真实订单；
- 72 小时结束后报告真实结果，不预先保证盈利。

## 六、范围外事项

- 真实下单、交易所私有账户接入和资金操作；
- 为旧历史研究线继续创建协议、门控、证据系统或全局重构；
- 在首轮市场结果产生前修改理论、评分或验收标准来适应结果；
- 将纸面结果表述为实盘、因果或长期预测有效性证明。

## 七、进度

### 已完成

- 六市场公开数据采集、技术测量、竞争假说、纸面账户、风险门、审计链、每 8 小时复盘和四类评分的实现；
- 初始配置已包含 SNDK 500@1125、MU 可交易无初始仓、HYPE 完整分析；
- 本地实时墙钟、72 小时周期、受控探针和情绪扰动规则；
- 核心纸面模块测试已经通过。
- 实时运行 `msta-paper-20260729T212716Z-87cc29bb` 已于 2026-07-30 05:27（北京时间）启动，计划于 2026-08-02 05:27 结束；
- 首轮六市场分析与六个可证伪假说已冻结并提交，事务链和账本校验有效；
- 五个初始多仓均已设置止损止盈，成本后净盈亏比分别为 SNDK 2.027685、ETH 1.731171、SOL 1.931888、BTC 2.446188、HYPE 1.76538；
- 十一笔初始限价单已逐笔审查并全部取消，当前未保护仓位为 0，开放风险约 81.97 USDT；
- 现有“可持续自动交易”任务已更新为“新理论六市场纸面实践（每小时）”，处于启用状态并回指本需求记录。
- Agent1 首轮中文完整记录已回填至 `.runtime/theory-paper-v1/current/reports/zh/20260730T053830+0800_cycle-0001_agent1_zh.md`，覆盖六标的决策轨迹、五仓保护、十一单取消、组合结果、理论来源及事务/账本摘要；
- 新增确定性 write-once 中文记录导出器 `trade_system.theory_paper.zh_record`，可用 `--all` 补齐并校验全部已提交周期；
- 每小时自动任务 `automation-2` 已加入中文记录附加要求：每轮创建前补齐、提交后再次导出并校验，记录不一致或原始工件/账本缺失时失败关闭；任务保持启用且频率不变。
- 中文记录重复导出结果为 `EXISTING_IDENTICAL`；当前账本和事务链均有效，冻结交易版本未漂移；纸面交易相关 36 项单元测试通过。
- Agent1 v2 中文完整版已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T053830+0800_cycle-0001_agent1_zh_v2.md`，保留 v1 不覆盖；文档包含标准账户总览、五个 lot 的精确开仓价/数量/标记价/USDT 价值/盈亏/收益率、完整止盈止损保护、十一笔订单历史、成交历史和原始账户对象；
- Agent1 逐 lot 未实现盈亏合计 `-134.9762062 USDT`，与运行时组合值的差额为 `1e-8 USDT`，核对状态 `MATCH`；首轮成交历史为 `fills=[]`，五仓明确标为用户初始外生持仓，未伪造开仓成交；
- 每小时自动任务 `automation-2` 已升级为 v2：要求 `theory-paper-zh-audit-record.v2`、`_zh_v2.md`、完整账户/持仓/订单/成交字段及逐 lot 盈亏核对；任务保持启用且频率、目标任务不变。
- 第 2 轮已于 2026-07-30 06:40（北京时间）冻结六市场输入，并于 06:47 提交纸面决策；六标的公开数据覆盖率均为 `93.33%`，无整标的采集失败，强平字段继续保持 `UNKNOWN`，严格流动性韧性继续保持单帧代理边界；
- 第 2 轮没有研究就绪入场区被标记价触发，因此新增仓位、订单和成交均为 0；五个外生多仓止损分别上移至 SNDK `999`、ETH `1883`、SOL `72.6`、BTC `63020`、HYPE `52.5`，原止盈不外移，五项执行回执全部 `ACCEPTED`；
- 第 2 轮保护更新后组合开放风险由约 `121.024981 USDT` 降至 `59.78385202 USDT`，五仓当前成本后净盈亏比为 `1.741836 / 1.824523 / 2.127674 / 2.161861 / 2.120763`；当前权益 `9904.07951201 USDT`，未实现及总净盈亏 `-95.92048799 USDT`；
- Agent2 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T064726+0800_cycle-0002_agent2_zh_v2.md`，SHA-256 为 `2553ddeb39d2510d1eaaa0c9e824a6e32c59f5a715ce37e56a59c29f82d363bb`；逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`，重复导出为 `EXISTING_IDENTICAL`。
- 第 3 轮已于 2026-07-30 07:41（北京时间）冻结六市场输入；冻结前 SNDK 外生初始多仓按第 2 轮 `999` 保护止损成交，实际平仓价 `998.390393`、数量 `0.444444444444`、名义 `443.72906356 USDT`、退出费 `0.22186453 USDT`、净已实现盈亏 `-56.49280098 USDT`，该结果保持 `EXOGENOUS` 归因，不计为理论交易成绩；
- 第 3 轮 SNDK 冻结标记价 `997.96647285` 已进入 `991.91–1003.8701652475` 的研究就绪多头支撑回测区，完整几何、数据与风险门均通过；Agent3 于 07:49（北京时间）执行普通策略纸面做多，实际成交价 `998.16606614`、数量 `0.250509417702`、成交名义 `250.05 USDT`、入场费 `0.125025 USDT`，父假说 `PHI_RANGE`，保护为止损 `956.0295042575`、止盈 `1124.99`，当前成本后净盈亏比 `2.969406`，`probe=false`；
- 第 3 轮 HYPE 外生多仓因原保护在当前标记价下的成本后净盈亏比降至 `1.382463`，止损由 `52.5` 收紧至 `53.0`、止盈保持 `56`，执行回执 `ACCEPTED`，更新后当前成本后净盈亏比 `2.085522`；BTC、ETH、SOL 原保护复算后继续有效，全部开放 lot 均有止损止盈，未保护 lot 为 0；
- 第 3 轮提交后权益 `9902.42106376 USDT`、现金 `9943.38217403 USDT`、总净盈亏 `-97.57893624 USDT`、未实现盈亏 `-40.96111027 USDT`、已实现净盈亏 `-56.49280098 USDT`、总手续费 `0.34688953 USDT`、毛杠杆 `0.38466238x`、开放风险 `61.86835133 USDT`；当前五个开放 lot 的逐 lot 未实现盈亏合计与组合值差额为 `0 USDT`、状态 `MATCH`；
- Agent3 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T074901+0800_cycle-0003_agent3_zh_v2.md`，SHA-256 为 `e8b4d204c4d7237ffcb73170cd934056fbc020ed8a3c0e051870670e141b45a2`；三轮记录重复导出全部为 `EXISTING_IDENTICAL`，账本 `7` 个事件和事务链 `7` 笔事务均校验有效，运行继续为 `ACTIVE`。
- 第 4 轮已于 2026-07-30 08:41（北京时间）冻结六市场输入，并于 08:47 提交纸面决策；六标的公开数据覆盖率均为 `93.33%`，没有整标的采集失败，强平字段继续保持 `UNKNOWN`，严格流动性韧性继续保持单帧代理边界；
- 第 4 轮六个标记价均不在研究就绪入场区内，因此新增名义、订单和成交均为 `0`；既有 ETH、SOL、BTC、HYPE 外生多仓保护保持不变，SNDK 策略多仓止损由 `956.0295042575` 上移至 `965.7095396875`、止盈维持 `1124.99`，执行回执 `ACCEPTED`，按本轮标记价计算的成本后净盈亏比为 `2.251648`；
- 第 4 轮提交后权益 `9898.86253937 USDT`、现金 `9943.38217403 USDT`、总净盈亏 `-101.13746063 USDT`、未实现盈亏 `-44.51963466 USDT`、已实现净盈亏 `-56.49280098 USDT`、总手续费 `0.34688953 USDT`、毛杠杆 `0.38444118x`；SNDK 保护上移使组合开放风险由冻结时 `58.30982693 USDT` 降至 `55.88682648 USDT`，未保护 lot 为 `0`；
- Agent4 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T084739+0800_cycle-0004_agent4_zh_v2.md`，SHA-256 为 `7378dce6be1235d3f3f115b4a49055e16a4be9b04a9dbb8d3c8f5cd88c45b172`；四轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`，账本 `9` 个事件和事务链 `9` 笔事务均校验有效，运行继续为 `ACTIVE`。
- 中文导出器已对“保护后的持仓”小表做向前兼容的口径标签修正：第 1 至第 4 轮 write-once 文档保持逐字不变；从第 5 轮起把不随保护更新改写的 `entry_reward_risk_net` 和 `initial_net_risk_usdt` 明确标为“初始成本后净 RR / 初始净风险”，并提示当前标记价至止损的开放风险、目标收益和净 RR 以上方标准持仓表为准。
- 第 5 轮已于 2026-07-30 09:43（北京时间）冻结六市场输入，并于 09:57 提交纸面决策；六标的数据覆盖率均为 `93.33%`，没有整标的采集失败。SNDK、MU、ETH、SOL、HYPE 不在研究就绪入场区；BTC 当前只命中成本后净盈亏比 `1.0035`、低于 `1.5` 门槛的拒绝几何，而研究就绪上破区尚未触发，因此新增名义、订单和成交均为 `0`。
- 第 5 轮四项单向保护更新均获 `ACCEPTED`：ETH 止损上移至 `1900.264946295`、SOL 至 `73.298580215`、HYPE 至 `53.586271785`、SNDK 策略仓至 `1033.5141774475`，目标分别保持 `1945 / 75.5 / 56 / 1124.99`；按本轮标记价计算的成本后净盈亏比分别为 `1.807838 / 2.173879 / 2.120754 / 1.510806`，BTC 继续使用 `63020 / 66000` 保护，未保护 lot 为 `0`。
- 第 5 轮提交后权益 `9938.35654915 USDT`、现金 `9943.38217403 USDT`、总净盈亏 `-61.64345085 USDT`、未实现盈亏 `-5.02562488 USDT`、已实现净盈亏 `-56.49280098 USDT`、总手续费 `0.34688953 USDT`、毛杠杆 `0.38688734x`、开放风险 `53.45742367 USDT`；Agent5 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T095731+0800_cycle-0005_agent5_zh_v2.md`，SHA-256 为 `8fa137c74c913223ee51d00b1f7c1e7b039afd92c742e2bd0eda0c7ce0fcdcf2`，五轮记录重复导出均为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `11` 条且均有效，运行继续为 `ACTIVE`。
- 第 6 轮已于 2026-07-30 10:43（北京时间）冻结六市场输入，并于 10:51 提交纸面决策；冻结前 ETH 外生仓、SOL 外生仓和第 3 轮 SNDK 策略仓分别按保护退出，实际成交价为 `1896.780795 / 73.258016 / 1018.614324`，净实现盈亏为 `-12.58728927 / -18.97187209 / +4.86986993 USDT`，原归因和原假说均保持不变。
- 第 6 轮 SNDK 标记价 `1033.97853615` 与 HYPE 标记价 `54.041` 分别进入研究就绪的多头支撑回测区；Agent6 执行两笔各 `250 USDT` 的普通策略纸面多头，SNDK 实际开仓价 `1034.18533186`、数量 `0.24178451608`、止损/止盈 `994.26522804 / 1124.99`，HYPE 实际开仓价 `54.0518082`、数量 `4.626117207306`、止损/止盈 `53.50651548 / 55.521`，两笔均为 `PHI_RANGE`、`probe=false`；BTC 外生仓止损单向上移至 `63948.1142646375`、目标 `66000` 不变，全部开放 lot 均受保护。
- 第 6 轮提交后权益 `9906.57814169 USDT`、现金 `9916.5678576 USDT`、总净盈亏 `-93.42185831 USDT`、未实现盈亏 `-9.98971591 USDT`、已实现净盈亏 `-83.18209241 USDT`、总手续费 `1.60918852 USDT`、毛杠杆 `0.23117067x`、开放风险 `25.37187021 USDT`；Agent6 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T105131+0800_cycle-0006_agent6_zh_v2.md`，SHA-256 为 `f42a8c15ae85bb66200028f80d76ca24b35f0a374509c84e5d6abb60cfdce2d3`，六轮记录重复导出均为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `13` 条且均有效，运行继续为 `ACTIVE`。
- 第 7 轮已于 2026-07-30 11:42（北京时间）冻结六市场输入，并于 11:48 提交纸面决策；六标的覆盖率均为 `93.33%`，没有保护撮合或情绪扰动成交。24 个候选中没有研究就绪几何被当前价触发；BTC 虽命中 `64062.7146322025–64175` 阻力拒绝区，但该候选状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`、净几何约 `1.32`，低于 `1.5` 门槛，因此没有新增仓位、订单或成交。
- 第 7 轮两项保护收紧均获 `ACCEPTED`：BTC 外生多仓止损由 `63948.11426464` 上移至 `64062.7146322025`、目标 `66000` 不变，当前净 RR 为 `14.280706`；第 6 轮 HYPE 策略多仓止损由 `53.50651548` 上移至 `53.5654677675`、目标 `55.521` 不变，当前净 RR 为 `3.807331`。SNDK 策略多仓和 HYPE 外生多仓保持原保护，全部四个开放 lot 均受保护。
- 第 7 轮提交后权益 `9901.33443919 USDT`、现金 `9916.5678576 USDT`、总净盈亏 `-98.66556081 USDT`、未实现盈亏 `-15.23341841 USDT`、已实现净盈亏 `-83.18209241 USDT`、总手续费 `1.60918852 USDT`、毛杠杆 `0.2307635x`、开放风险 `18.06646714 USDT`；Agent7 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T114814+0800_cycle-0007_agent7_zh_v2.md`，SHA-256 为 `4bd7a64c2a6f5642b1e45d814d09f724963434e6eccfc071d5f5df0fde84808c`，七轮记录重复导出均为 `EXISTING_IDENTICAL`，账本和事务链各 `15` 条且均有效，运行继续为 `ACTIVE`。
- 第 8 轮已于 2026-07-30 12:43（北京时间）冻结六市场输入，并于 12:48 提交纸面决策；六标的覆盖率均为 `93.33%`。ETH 标记价 `1903.76946512` 命中多头支撑回测候选，但该几何成本后净盈亏比仅 `1.0757`、状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`，低于 `1.5` 门槛；其余研究就绪新仓几何均未触发，因此新增风险为 `0`。
- BTC 外生多仓的冻结标记价 `64052` 已低于第 7 轮止损触发价 `64062.7146322025`，但本轮离散保护撮合未自动成交；Agent8 立即执行全量 `CLOSE`，实际成交价 `64039.1896`、数量 `0.015625 BTC`、名义 `1000.6123375 USDT`、毛价格盈亏 `+0.6123375 USDT`、退出费 `0.50030617 USDT`、净盈亏 `+0.11203133 USDT`，继续保持 `EXOGENOUS` 归因，不计为理论策略成功。
- 第 8 轮提交后权益 `9892.16245695 USDT`、现金 `9916.67988893 USDT`、总净盈亏 `-107.83754305 USDT`、未实现盈亏 `-24.51743198 USDT`、已实现净盈亏 `-83.07006108 USDT`、总手续费 `2.10949469 USDT`、毛杠杆 `0.12894881x`、开放风险 `8.96173591 USDT`；当前仅余 HYPE 外生多仓、SNDK 策略多仓和 HYPE 策略多仓三个开放 lot，均有止盈止损。
- Agent8 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T124830+0800_cycle-0008_agent8_zh_v2.md`，SHA-256 为 `7cc9bbe3c60104cfdc4c920593d7394c86eddd1aa9eae519b7a912b05103bac9`；八轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`。
- 首个精确八轮复盘 `review-001` 已冻结：理论完整性 `93.0`，方法实践 `100`，假说结果诊断为 `4` 个已否证、`15` 个仍获支持、`29` 个未解决、`0` 个到期获支持，终局样本诊断分 `0.0`；纸面绩效与理论/方法评分保持分离。唯一未来生效的方法增量为 `DATA_QUALITY / MC-1ef3e83e355d7d6826b4`，自第 9 轮起检验下一窗口能否在不前视的情况下减少必需 `UNKNOWN` 字段，不回写历史工件。
- 复盘后运行继续为 `ACTIVE`，周期数 `8`、复盘数 `1`、无待决策周期；账本和事务链各 `18` 条且均有效。
- 第 9 轮已于 2026-07-30 13:45（北京时间）冻结六市场输入，并于 13:51 提交纸面决策；六标的覆盖率均为 `93.33%`。BTC 标记价 `64095.52747101` 命中空头阻力拒绝候选，但该几何成本后净盈亏比仅 `1.2705`、状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`，低于 `1.5` 门槛；其余研究就绪候选均未触发，因此本轮新增风险为 `0`。
- 第 9 轮市场保护撮合按既有止损全量退出两个 HYPE 多仓：外生 `lot-000005` 以 `53.57019591` 成交、数量 `14.545454545455 HYPE`、名义 `779.2028496 USDT`、净盈亏 `-21.18675182 USDT`；策略 `lot-000008` 以 `53.54939813` 成交、数量 `4.626117207306 HYPE`、名义 `247.72579213 USDT`、净盈亏 `-2.57309577 USDT`、`R=-0.904237`。两笔均保持原归因和父假说，外生结果不计为理论策略成功。
- 第 9 轮提交后权益 `9891.48477042 USDT`、现金 `9893.04506634 USDT`、总净盈亏 `-108.51522958 USDT`、未实现盈亏 `-1.56029592 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `2.62295901 USDT`、毛杠杆 `0.02512158x`、开放风险 `8.28404936 USDT`；当前仅余 SNDK 策略 `lot-000007`，开仓价 `1034.18533186`、剩余数量 `0.24178451608`、止损/止盈 `994.26522804 / 1124.99`，且无活动挂单、无未保护 lot。
- Agent9 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T135150+0800_cycle-0009_agent9_zh_v2.md`，SHA-256 为 `a2a3afa222e24c40d9cef8f9d0aaff43547146b96147258a83c5b8ab181fc44c`；九轮记录均返回路径和 SHA-256，前八轮为 `EXISTING_IDENTICAL`，第九轮为 `CREATED`。逐 lot 未实现盈亏核对状态为 `MATCH`；账本和事务链各 `20` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的首个未来窗口已执行：六标的 F 轴仍各有 3 个必需 `UNKNOWN`，R 轴 `strict_resilience` 仍为 `UNKNOWN`，覆盖率未低于八轮基线；本窗口没有支持“减少必需 UNKNOWN”成功，因此只收窄强平和严格韧性主张，不补零、不扩大方向性结论，后续窗口继续检验。
- 第 10 轮已于 2026-07-30 14:45（北京时间）冻结六市场输入，并于 15:46 提交纸面决策；六标的覆盖率均为 `93.33%`，无整标的采集失败。SNDK 标记价 `1013.03` 命中 `1011.52–1021.53210333` 的研究就绪多头支撑回测区，按当前入场、止损 `981.48369001`、目标 `1069.69` 计算的成本后净盈亏比为 `1.686921`，通过数据、单笔、单标的和组合风险门；BTC 命中候选的成本后净盈亏比仅 `1.1324`，明确风险否决，MU、ETH、SOL、HYPE 均未触发研究就绪入场区。
- Agent10 当轮执行 SNDK `250 USDT` 普通策略纸面加多，实际成交价 `1013.232606`、数量 `0.246784399277`、成交名义 `250.05 USDT`、入场费 `0.125025 USDT`，父假说 `PHI_RANGE`、`probe=false`；新 lot `lot-000009` 全量保护为止损 `981.48369001`、止盈 `1069.69`，既有 `lot-000007` 继续使用独立止损/止盈 `994.26522804 / 1124.99`，两笔开放 lot 均受保护且无活动挂单。
- 第 10 轮提交后权益 `9887.75500966 USDT`、现金 `9892.92004134 USDT`、总净盈亏 `-112.24499034 USDT`、未实现盈亏 `-5.16503168 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `2.74798401 USDT`、毛杠杆 `0.05005534x`、开放风险 `12.70818632 USDT`；Agent10 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T154629+0800_cycle-0010_agent10_zh_v2.md`，SHA-256 为 `aa9ca983a40471ea3ed810204d402114bd3a5c429ff9732eb3531c89c6534aaa`，十轮记录重复导出均为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `22` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第二个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，覆盖率仍为 `0.9333`，未支持“减少必需 UNKNOWN”成功；本轮继续只收窄相关主张，不补零，也未让缺失字段阻止其他有效轴上的合格几何执行。
- 第 11 轮已于 2026-07-30 16:49（北京时间）冻结六市场输入，并于 16:58 提交纸面决策；六标的覆盖率均为 `93.33%`，无整标的采集失败。SNDK 标记价 `1015.73` 已离开 `1000.03–1009.2252574725` 的研究就绪多头支撑区，MU、BTC、ETH、SOL、HYPE 也均未进入研究就绪入场区；本轮只提交 `HOLD`，回执为 `ACCEPTED / NO_CHANGE`，新增风险、订单和成交均为 `0`。
- 第 11 轮继续保护两笔 SNDK 策略多仓：`lot-000007` 开仓价 `1034.18533186`、数量 `0.24178451608`、止损/止盈 `994.26522804 / 1124.99`、本轮当前成本后净 RR `4.898240`；`lot-000009` 开仓价 `1013.232606`、数量 `0.246784399277`、止损/止盈 `981.48369001 / 1069.69`、本轮当前成本后净 RR `1.534228`。两笔均由全量剩余数量保护，无活动挂单、无未保护 lot。
- 第 11 轮提交后权益 `9889.07414574 USDT`、现金 `9892.92004134 USDT`、总净盈亏 `-110.92585426 USDT`、未实现盈亏 `-3.8458956 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `2.74798401 USDT`、毛杠杆 `0.05018206x`、开放风险 `14.02732239 USDT`；Agent11 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T165828+0800_cycle-0011_agent11_zh_v2.md`，SHA-256 为 `f0ba72fc32cac3cf942f1085a22d051f15a8d7b4a0decbd017570b78f5993e2e`。十一轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `24` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第三个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，覆盖率仍为 `0.9333`，没有支持“减少必需 UNKNOWN”成功；继续收窄强平和严格韧性主张，不补零、不回写既有冻结决策。
- 第 12 轮已于 2026-07-30 17:49（北京时间）冻结六市场输入，并于 18:00 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。BTC `64602.44717391` 和 SOL `74.08` 分别命中研究就绪空头阻力拒绝区，但按当前可成交价、2 bps 市价滑点、手续费和止损滑点复算的净 RR 只有 `1.440651 / 1.381987`；ETH 命中已拒绝阻力区的净 RR 为 `0.915127`。三者均低于 `1.5`，执行类型化风险否决；SNDK、MU、HYPE 未触发研究就绪新仓区，本轮新增订单和成交均为 `0`。
- 第 12 轮将两笔 SNDK 策略多仓的止损单向提高到当前注册下破失效边界 `1004.279523024`，目标继续为 `1124.99 / 1069.69`；两项 `UPDATE_PROTECTION` 和一项 `HOLD` 回执均为 `ACCEPTED`。`lot-000007 / lot-000009` 更新后的当前成本后净 RR 为 `4.147260 / 1.800904`，全部剩余数量继续受保护，组合开放风险由冻结时 `19.55303682 USDT` 降至 `11.51251576 USDT`。
- 第 12 轮提交后权益 `9894.59986017 USDT`、现金 `9892.92004134 USDT`、总净盈亏 `-105.40013983 USDT`、未实现盈亏 `+1.67981883 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `2.74798401 USDT`、毛杠杆 `0.05071249x`、成本价至止损损失 `10.08274693 USDT`；Agent12 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T180012+0800_cycle-0012_agent12_zh_v2.md`，SHA-256 为 `67092b7a350a0e6418cab5f41711aa8e308b43e28cc7b3649f98ec8b1e700925`。十二轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `-1e-8 USDT`、状态 `MATCH`，账本和事务链各 `26` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第四个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，覆盖率仍为 `0.9333`，未支持“减少必需 UNKNOWN”成功；继续收窄相关主张，不补零，也不让缺失字段绕过成本后风险门。
- 第 13 轮已于 2026-07-30 18:49（北京时间）冻结六市场输入，并于 18:57 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。SNDK `1047.56158949`、MU `752.63`、BTC `64573.3`、ETH `1917.58`、SOL `73.89`、HYPE `53.68454762` 均位于相邻研究就绪入场闭区间之间，本轮没有可执行的新仓几何；唯一 `HOLD` 回执为 `ACCEPTED / NO_CHANGE`，新增订单和成交均为 `0`。
- 第 13 轮继续保护两笔 SNDK 策略多仓：`lot-000007 / lot-000009` 开仓价为 `1034.18533186 / 1013.232606`、剩余数量为 `0.24178451608 / 0.246784399277`，止损均保持 `1004.27952302`，目标保持 `1124.99 / 1069.69`，全部剩余数量受保护。按冻结标记价计算的当前净 RR 为 `1.751226 / 0.497092`；后者下降源于价格接近目标，新增风险的 `1.5` 门槛不用于事后把既有止损追到没有注册结构依据的价格。
- 第 13 轮提交后权益 `9904.62607089 USDT`、现金 `9892.92004134 USDT`、总净盈亏 `-95.37392911 USDT`、未实现盈亏 `+11.70602955 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `2.74798401 USDT`、持仓名义 `511.80602955 USDT`、毛杠杆 `0.05167343x`、标记价至止损开放风险 `21.53872648 USDT`、成本价至止损损失 `10.08274693 USDT`；Agent13 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T185732+0800_cycle-0013_agent13_zh_v2.md`，SHA-256 为 `46125ccfd4d01218ce19a5d5e0b20a7e15372102d868f4db65464b8f519a15e7`。十三轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `28` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第五个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，覆盖率仍为 `0.9333`，未支持“减少必需 UNKNOWN”成功；继续收窄相关主张，不补零，也不让缺失字段绕过触发与成本后风险门。
- 第 14 轮已于 2026-07-30 19:51（北京时间）冻结六市场输入，并于 20:00 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。MU `765.45809281`、BTC `64651.8`、SOL `74.16` 和 HYPE `53.12628095` 分别命中研究就绪的阻力空、阻力空、阻力空和支撑多几何；运行时成本后净 RR 预演为 `2.270370 / 1.805099 / 1.538628 / 2.289348`，逐笔及组合风险门均通过。ETH 命中阻力空候选但注册 RR 仅 `1.3377`、状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`，明确风险否决；SNDK 未命中新仓区。
- Agent14 当轮执行四笔各 `250 USDT` 的普通策略纸面交易，全部回执为 `FILLED` 且无拒绝超量：MU 空仓 `lot-000010` 开仓价/数量 `765.30500119 / 0.326601811841`、止损/止盈 `784.70905219 / 718.43`；BTC 空仓 `lot-000011` 为 `64638.86964 / 0.003866868363`、`64949.447922 / 63881`；SOL 空仓 `lot-000012` 为 `74.145168 / 3.371089536138`、`74.5900918 / 73.26`；HYPE 多仓 `lot-000013` 为 `53.13690621 / 4.705768887442`、`52.67853861 / 54.381`。四笔均为 `probe=false`，所有新增及既有 lot 均有全量止盈止损。
- 第 14 轮提交后权益 `9918.27731062 USDT`、现金 `9892.42009134 USDT`、总净盈亏 `-81.72268938 USDT`、未实现盈亏 `+25.85721928 USDT`、已实现净盈亏 `-106.82990867 USDT`、总手续费 `3.24793401 USDT`、持仓名义 `1526.15721933 USDT`、毛杠杆 `0.15387322x`、标记价至止损开放风险 `47.69063138 USDT`、成本价至止损损失 `22.5834121 USDT`；Agent14 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T200026+0800_cycle-0014_agent14_zh_v2.md`，SHA-256 为 `88600e5cad4e21f907b7885173559b8c80347a4fc5898f1265fbaf6bee701841`。十四轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `30` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第六个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，覆盖率仍为 `0.9333`，未支持“减少必需 UNKNOWN”成功；继续收窄相关主张，不补零，也未让缺失字段阻止其他有效轴下已经触发且通过成本后风险门的普通策略交易。
- 第 15 轮已于 2026-07-30 20:51（北京时间）冻结六市场输入，并于 21:03 提交纸面决策；冻结闭合 K 线先将 SNDK `lot-000009` 按 `1069.69` 目标全量退出，实际数量 `0.246784399277 SNDK`、名义 `263.98280406 USDT`、净实现盈亏 `+13.75498250 USDT`、`R=1.686921`。随后密封 `CHAOS_AUTO` 扰动按 `787.31264061` 回补 MU 空仓 `0.27678150046 MU`，净实现盈亏 `-6.30617538 USDT`；该扰动单列归因，不计为理论策略成功或失败。
- 密封扰动后 MU `lot-000010` 剩余 `0.049820311381 MU`，冻结标记价 `787.15520957` 已高于不可放宽的 `784.70905219` 止损；Agent15 同轮执行全量 `CLOSE`，实际回补价 `787.31264061`、名义 `39.22416091 USDT`、该剩余切片净盈亏 `-1.13510340 USDT`，lot 最终累计净盈亏 `-7.44127878 USDT`。SNDK `lot-000007` 拟提高到 `1028.68601604` 的保护更新被 `UPDATED_PROTECTION_MINIMUM_NET_RR_NOT_MET` 风险门拒绝，首次事务完整回滚；最终保持原 `1004.27952302 / 1124.99` 保护，没有伪造成功回执或借用未触发突破几何。
- SOL 标记价 `74.32` 命中 `74.2252096825–74.36` 的研究就绪阻力拒绝空头区；按冻结成本口径，新增 `250 USDT` 空仓预演净 RR 约 `1.785892` 并通过风险门。Agent15 执行普通策略 `ADD_SHORT`，实际开仓价/数量 `74.305136 / 3.363832077503 SOL`、成交名义 `249.95 USDT`、入场费 `0.124975 USDT`，新 `lot-000014` 止损/止盈为 `74.7643709525 / 73.26`；既有 `lot-000012` 继续使用更紧的 `74.5900918 / 73.26`，所有开放 lot 继续全量受保护。
- 第 15 轮提交后权益 `9913.24539269 USDT`、现金 `9898.85882006 USDT`、总净盈亏 `-86.75460731 USDT`、未实现盈亏 `+14.38657263 USDT`、已实现净盈亏 `-100.51620495 USDT`、总手续费 `3.55427444 USDT`、持仓名义 `1267.37568988 USDT`、毛杠杆 `0.1278467x`、标记价至止损开放风险 `29.01582453 USDT`、成本价至止损损失 `15.25422689 USDT`；Agent15 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T210335+0800_cycle-0015_agent15_zh_v2.md`，SHA-256 为 `48173e4a9470b8a8a756739cd4f0288b16777f9dd05b0492246aecd23ba4286d`。十五轮记录重复导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `-0 USDT`、状态 `MATCH`，账本和事务链各 `32` 条且均有效，运行继续为 `ACTIVE`。
- 数据质量方法增量 `MC-1ef3e83e355d7d6826b4` 的第七个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，覆盖率仍为 `0.9333`，未支持“减少必需 UNKNOWN”成功；继续收窄相关主张、不补零，并把“保护先处理、密封扰动后执行”造成的同周期越止损剩余仓位及 SNDK 保护更新 RR 拒绝记录为具体执行阻塞。
- 第 16 轮已于 2026-07-30 21:54（北京时间）冻结六市场输入，并于 22:09 提交纸面决策；冻结闭合 K 线先将 BTC `lot-000011` 按既有止损全量回补，实际成交价 `64968.93275638`、数量 `0.003866868363 BTC`、名义 `251.22631065 USDT`、净实现盈亏 `-1.52689878 USDT`、`R=-1`。MU 标记价 `830.19666913` 命中 `827.9671814475–833.28` 研究就绪阻力拒绝空头区，运行时预演净 RR `2.821724` 且通过组合风险门；Agent16 执行普通策略纸面空仓，实际开仓价 `830.03062980`、数量 `0.301133465474 MU`、成交名义 `249.95 USDT`、止损/止盈 `849.2184556575 / 772.23`，父假说 `PHI_DOWNWARD_CONTINUATION`、`probe=false`。
- SNDK `lot-000007` 的冻结标记价 `1215.70761844` 已高于既有 `1124.99` 目标，但离散闭合 K 线撮合未生成目标成交；Agent16 没有倒填历史成交，而按当轮纸面市价全量退出，实际成交价 `1215.46447692`、数量 `0.24178451608 SNDK`、名义 `293.88049036 USDT`、净实现盈亏 `+43.55852512 USDT`、`R=4.369235`。SOL 旧空仓 `lot-000012` 的标记价已越过其独立止损，按精确剩余数量全量回补，实际成交价 `74.734944`、数量 `3.371089536138 SOL`、净实现盈亏 `-2.23913180 USDT`；较新的 `lot-000014` 继续按其独立 `74.7643709525 / 73.26` 保护。HYPE `lot-000013` 止损收紧至当前注册支撑 `53.085`、目标保持 `54.381`，所有开放 lot 均全量受保护。
- 第 16 轮提交后权益 `9939.22807955 USDT`、现金 `9938.90131460 USDT`、总净盈亏 `-60.77192045 USDT`、未实现盈亏 `+0.32676495 USDT`、已实现净盈亏 `-60.72371041 USDT`、总手续费 `4.07777194 USDT`、持仓名义 `753.16783063 USDT`、毛杠杆 `0.0757773x`、标记价至止损开放风险 `8.49957085 USDT`、成本价至止损损失 `8.54778089 USDT`；当前仅余 HYPE 多仓 `lot-000013`、SOL 空仓 `lot-000014`、MU 空仓 `lot-000015`，无活动挂单、无未保护 lot。Agent16 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T220927+0800_cycle-0016_agent16_zh_v2.md`，SHA-256 为 `eebe8aaaa802268e0cd8079bbefe19b712e498c704ef673f20677b1ece62a42e`；十六轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `-0 USDT`、状态 `MATCH`。
- 第二个精确八轮复盘 `review-002` 已冻结并严格覆盖第 9 至第 16 轮：理论完整性 `94.25`、方法实践 `100`；假说结果诊断为 `21` 个到期获支持、`32` 个已否证、`21` 个到期未支持、`11` 个仍获支持、`7` 个未知未解决，诊断分 `34.05`，不回写原 thesis。纸面绩效继续单列为权益 `9939.22807955 USDT`、12 个已平 lot、胜率 `33.3333%`、利润因子 `0.506388`、总 `R=-5.570034`，不参与理论或方法评分。
- 旧方法增量 `MC-1ef3e83e355d7d6826b4` 在第 9 至第 16 轮的必需未知项发生数仍为 `8`，与基线 `8` 相同，因此按预先冻结的否证测试判为 `REJECT`；第 17 轮起只启用一个未来生效的替代数据质量增量 `MC-8279aa5cafde5345e787`，继续检验下一未见八小时窗口能否在不前视的情况下减少必需 `UNKNOWN`，历史工件不回写。复盘后运行仍为 `ACTIVE`，周期数 `16`、复盘数 `2`、无待决策周期；账本和事务链各 `35` 条且均有效。
- 第 17 轮已于 2026-07-30 22:53（北京时间）冻结六市场输入，并于 23:13 提交纸面决策；冻结市场处理先将 SOL 空仓 `lot-000014` 按既有 `74.7643709525` 止损全量回补，实际成交价 `74.78680026`、数量 `3.363832077503 SOL`、成交名义 `251.57023769 USDT`、退出费 `0.12578512 USDT`、净实现盈亏 `-1.87099781 USDT`、`R=-1`。该成交保持 `STRATEGY / PHI_RANGE / PROTECTIVE_EXIT` 归因，不事后改写原 thesis。
- 六标的冻结覆盖率均为 `93.33%`，SNDK `1239.48`、MU `848.11`、BTC `64779.3`、ETH `1919.29`、SOL `74.70604192`、HYPE `53.89199048` 均未进入新的研究就绪入场闭区间，因此新增风险、订单和新仓成交均为 `0`。MU 空仓 `lot-000015` 保持 `849.21845566 / 772.23` 保护；HYPE 多仓 `lot-000013` 的止损由 `53.085` 收紧至冻结 15 分钟闭合 K 线支持 `53.763`、目标保持 `54.381`，执行回执 `ACCEPTED`，当前成本后前瞻净 RR 为 `2.779961`。
- 第 17 轮提交后权益 `9935.26424045 USDT`、现金 `9937.15529179 USDT`、总净盈亏 `-64.73575955 USDT`、账户累计收益率 `-0.647358%`、未实现盈亏 `-1.89105134 USDT`、已实现净盈亏 `-62.59470822 USDT`、总手续费 `4.20355706 USDT`、持仓名义 `508.99755549 USDT`、毛杠杆 `0.05123141x`、标记价至止损开放风险 `1.34777237 USDT`、成本价至止损损失 `3.48882371 USDT`；当前仅余 HYPE 多仓 `lot-000013` 与 MU 空仓 `lot-000015`，无活动挂单、无未保护 lot。
- Agent17 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260730T231335+0800_cycle-0017_agent17_zh_v2.md`，SHA-256 为 `3e35384bf68f44f2bb26917e22e5f32722a0648adf0ff7ecf0f77e3f2d354f05`；十七轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `1e-8 USDT`、状态 `MATCH`。运行继续为 `ACTIVE`，周期数 `17`、复盘数 `2`、无待决策周期；账本和事务链各 `37` 条且均有效。
- 新方法增量 `MC-8279aa5cafde5345e787` 的首个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，未支持“下一窗口减少必需 UNKNOWN”；本轮继续明确收窄强平与严格韧性主张，不补零、不使用冻结后检索结果回填决策。
- 第 18 轮已于 2026-07-30 23:56（北京时间）冻结六市场输入，并于 2026-07-31 00:06 提交纸面决策；冻结市场处理先将 MU 旧空仓 `lot-000015` 按既有止损全量回补，实际成交价 `849.47322120`、数量 `0.301133465474 MU`、成交名义 `255.80481493 USDT`、退出费 `0.12790241 USDT`、净实现盈亏 `-6.10769233 USDT`、`R=-1`。HYPE 多仓 `lot-000013` 的冻结标记价已经越过既有目标但离散闭合 K 线撮合未生成目标成交；Agent18 未倒填历史成交，而按当轮纸面市价全量退出，实际成交价 `54.38287839`、数量 `4.705768887442 HYPE`、净实现盈亏 `+5.61027549 USDT`、`R=2.261958`。
- MU `855.43` 和 BTC `64677.80007246` 分别命中当轮冻结的研究就绪阻力空头几何，运行时预演成本后净 RR 为 `2.963175 / 1.964595`，逐笔与组合风险门均通过。Agent18 各执行 `250 USDT` 普通策略纸面空仓：MU `lot-000016` 实际开仓价/数量 `855.258914 / 0.292250680944`、止损/止盈 `875.51086222 / 791.32`；BTC `lot-000017` 实际开仓价/数量 `64664.86451245 / 0.003865313906`、止损/止盈 `64956.59172332 / 63881`。两笔均为 `probe=false`，保护数量等于全部剩余基础资产数量；其他四标的的新风险几何未触发。
- 第 18 轮提交后权益 `9936.55792494 USDT`、现金 `9936.65792494 USDT`、总净盈亏 `-63.44207506 USDT`、账户累计收益率 `-0.634421%`、未实现盈亏 `-0.1 USDT`、已实现净盈亏 `-63.09212506 USDT`、总手续费 `4.70936610 USDT`、持仓名义 `500.00000003 USDT`、毛杠杆 `0.05031924x`、标记价至止损开放风险 `7.35189595 USDT`、成本价至止损损失 `7.70184595 USDT`；当前仅余 MU 与 BTC 两个全量受保护空仓，无活动挂单、无未保护 lot。
- Agent18 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T000642+0800_cycle-0018_agent18_zh_v2.md`，SHA-256 为 `5919d01b6fbc5840d0580386e054c52f66657add22bb94f368e860f3a6d96172`；十八轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`。运行继续为 `ACTIVE`，周期数 `18`、复盘数 `2`、无待决策周期；账本和事务链各 `39` 条且均有效。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第二个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，尚未观察到改进；继续收窄强平、深度韧性和参与者身份主张，不补零、不用冻结后官方核验结果回填本轮判断。
- 第 19 轮已于 2026-07-31 00:57（北京时间）冻结六市场输入，并于 01:12 提交纸面决策；六标的新仓研究就绪闭区间均未触发，新增风险为 `0 USDT`。BTC 空仓 `lot-000017` 的上一轮冻结硬否证已出现：最新闭合一小时方向为 `UP`、闭合价 `64694.2` 已进入上一轮 `64688` 以上突破路径，Agent19 因此按当前纸面市价全量回补，实际成交价 `64818.83348605`、数量 `0.003865313906 BTC`、名义 `250.54513844 USDT`、退出费 `0.12527257 USDT`、滑点成本 `0.05010903 USDT`、净实现盈亏 `-0.84538598 USDT`、`R=-0.581624`；该退出保留原始失败记录，没有移动理由等待更宽灾难止损。
- MU 空仓 `lot-000016` 的一小时与四小时仍为 `TRANSITION`，尚未满足父级向上结构否证；止损由 `875.51086222` 收紧至当前一小时注册阻力 `866.48`，目标保持 `791.32`，全量保护数量 `0.292250680944 MU`，当前成本后前瞻净 RR `9.371192`。第 19 轮提交后仅余该 MU 空仓：开仓价 `855.258914`、标记价 `859.87472656`、当前名义 `251.29897436 USDT`、未实现盈亏 `-1.34897436 USDT`、价格收益率 `-0.539698%`、当前开放风险 `2.13301714 USDT`。
- 第 19 轮提交后权益 `9934.58853960 USDT`、现金 `9935.93751396 USDT`、总净盈亏 `-65.41146040 USDT`、账户累计收益率 `-0.654115%`、已实现净盈亏 `-63.93751104 USDT`、总手续费 `4.83463867 USDT`、持仓名义 `251.29897436 USDT`、毛杠杆 `0.02529536x`、成本价至止损损失 `3.60696650 USDT`；无活动挂单、无未保护 lot。Agent19 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T011238+0800_cycle-0019_agent19_zh_v2.md`，SHA-256 为 `175dc546de05bda5d3ba2f5c8b547ddebf89e36db6f5d0ab2db4dfc51659f499`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`。运行继续为 `ACTIVE`，周期数 `19`、复盘数 `2`、无待决策周期；账本和事务链各 `41` 条且均有效。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第三个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，仍未观察到改进；继续收窄强平、严格韧性和参与者身份主张，不补零、不用冻结后检索结果回填本轮判断。
- 第 20 轮已于 2026-07-31 01:59（北京时间）冻结六市场输入，并于 02:06 提交纸面决策；六标的覆盖率均为 `93.33%`。20 个注册候选中，只有 ETH 标记价 `1920.17017829` 进入 `1918.4409758325–1921.91` 阻力拒绝区，但该候选注册净 RR 仅 `0.6651`、状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`，执行类型化风险否决；其余 14 个研究就绪候选均未触发，本轮新增风险为 `0 USDT`。
- MU 空仓 `lot-000016` 的上一轮冻结硬止损和价格否证已经触发：本轮标记价 `872.63382831` 高于不可放宽的 `866.48`。闭合 K 线市场保护撮合未生成自动成交，Agent20 因此按当前纸面市价全量回补，实际成交价 `872.80835508`、数量 `0.292250680944 MU`、名义 `255.07883611 USDT`、退出费 `0.12753942 USDT`、滑点成本 `0.05101577 USDT`、净实现盈亏 `-5.38135052 USDT`、`R=-0.861243`；没有伪造成 `866.48` 止损成交，也没有回写原 `PHI_DOWNWARD_CONTINUATION` thesis。
- 第 20 轮提交后权益与现金均为 `9930.68113843 USDT`，总净盈亏 `-69.31886157 USDT`、账户累计收益率 `-0.693189%`、未实现盈亏 `0 USDT`、已实现毛/净盈亏 `-64.35668348 / -69.31886156 USDT`、总手续费 `4.96217809 USDT`、持仓和挂单名义均为 `0 USDT`、毛杠杆和开放风险均为 `0`；17 个 lot 已全部平仓。Agent20 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T020655+0800_cycle-0020_agent20_zh_v2.md`，SHA-256 为 `6fa606fbffae9c5147dd5518ca99a78637c2030ccd39fa56c5344bee72d870fc`；20 轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏差额为 `0 USDT`、状态 `MATCH`。运行继续为 `ACTIVE`，周期数 `20`、复盘数 `2`、无待决策周期；账本和事务链各 `43` 条且均有效。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第四个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，仍未观察到改进；继续收窄强平、严格韧性和参与者身份主张，不补零。`market-execution.fills=[]` 未在价格越过保护线时自动平掉 MU，是本轮新增的具体执行缺口；本轮只以显式纸面 `CLOSE` 完成既有规则，不修改运行时或历史工件。
- 第 21 轮已于 2026-07-31 03:00（北京时间）冻结六市场输入，并于 03:07 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。BTC `64675.3` 与 ETH `1915.18379845` 虽分别进入阻力空头和支撑多头候选区，但注册净 RR 仅 `0.2642 / 0.71`、状态均为 `REJECTED_OR_UNKNOWN_GEOMETRY`，执行类型化风险否决。SOL `74.49397482` 进入 `74.3696929225–74.5` 研究就绪阻力拒绝空头区，运行时预演入场成本后净 RR `2.293054` 且通过逐笔、单标的与组合风险门；SNDK、MU 和 HYPE 的研究就绪区均未触发。
- Agent21 执行一笔 `250 USDT` 普通策略 SOL 纸面空仓，实际成交 `fill-000031`、新建 `lot-000018`：精确开仓价 `74.47907603`、数量 `3.355976112217 SOL`、成交名义 `249.95000002 USDT`、入场费 `0.124975 USDT`、市价滑点假设 `2 bps`、估计滑点成本 `0.04999 USDT`。硬止损 `74.8909212325`、预计止损成交 `74.91338851`，目标 `73.26`，保护数量等于全部剩余数量；提交时标记价 `74.49397482`，未实现盈亏 `-0.04999998 USDT`、价格收益率 `-0.020004%`、累计净盈亏 `-0.17497498 USDT`，当前开放风险 `1.53324608 USDT`、成本价至止损净损失 `1.70822107 USDT`、止损后预计净盈亏 `-1.70822107 USDT`、止盈后预计净盈亏 `+3.91704327 USDT`、当前前瞻净 RR `2.668859`；逐 lot 与组合未实现盈亏差额 `0 USDT`、状态 `MATCH`。
- 第 21 轮提交后权益 `9930.50616345 USDT`、现金 `9930.55616343 USDT`、总净盈亏 `-69.49383655 USDT`、账户累计收益率 `-0.694938%`、已实现毛/净盈亏 `-64.35668348 / -69.31886156 USDT`、总手续费 `5.08715309 USDT`、当前持仓名义 `250 USDT`、活跃挂单名义 `0 USDT`、毛杠杆 `0.02517495x`；历史累计为 18 个 lot（17 已平、1 未平）、11 个订单（均已取消）和 31 笔成交。Agent21 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T030700+0800_cycle-0021_agent21_zh_v2.md`，SHA-256 为 `26590d1fd54addd80a24eaa7a3c45d5d2908c84c9cd99f44528462b49b31b85c`；21 轮记录首次导出数量、路径与摘要均通过，账本和事务链各 `45` 条且均有效，运行继续为 `ACTIVE`、无待决策周期。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第五个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，仍未观察到改进；继续收窄强平、严格韧性与参与者身份主张，不补零。冻结新闻只有公开发现标题元数据，冻结后的一手来源核验未回填或改变本轮理论、点位、方向、仓位及风险门。
- 第 22 轮已于 2026-07-31 04:00（北京时间）冻结六市场输入，并于 04:09 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。SOL `lot-000018` 的 cycle-0021 冻结 thesis 把闭合一小时站上 `74.604245662` 列为结构否证，本轮最新闭合一小时方向为 `UP`、闭合价 `74.75`，已触发否证；Agent22 因此在原 `74.89092123` 硬止损尚未触价前全量回补，实际成交 `fill-000032`：价格 `74.7472218`、数量 `3.355976112217 SOL`、名义 `250.84989082 USDT`、退出费 `0.12542495 USDT`、滑点成本 `0.05016998 USDT`、毛价格盈亏 `-0.8998908 USDT`、净盈亏 `-1.15029074 USDT`、`R=-0.673385`；原 `PHI_RANGE` 归因和失败记录均未改写。
- HYPE 标记价 `55.4` 已进入 `55.374160505–55.521` 研究就绪阻力拒绝空头区，但按当前价、原 `55.961518485 / 54.642` 止损目标、运行时费率及滑点重算的成本后净 RR 仅 `1.098015`，低于 `1.5` 硬门，因此执行类型化风险否决且没有移动几何；SNDK、MU、BTC、ETH 和 SOL 的新风险闭区间均未触发，本轮新增仓位与新风险订单均为 `0`。
- 第 22 轮提交后权益与现金均为 `9929.53084768 USDT`，总净盈亏 `-70.46915232 USDT`、账户累计收益率 `-0.704692%`、未实现盈亏 `0 USDT`、已实现毛/净盈亏 `-65.25657428 / -70.46915230 USDT`、总手续费 `5.21257804 USDT`、持仓和挂单名义均为 `0 USDT`、毛杠杆和开放风险均为 `0`；18 个 lot 已全部平仓，11 个历史订单均已取消，历史成交增至 32 笔。
- Agent22 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T040917+0800_cycle-0022_agent22_zh_v2.md`，SHA-256 为 `69089a795093d0168a6bd832e7932539ad01208d84db1701f5b9222f00f5d20e`；22 轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `47` 条且均有效，运行继续为 `ACTIVE`、无待决策周期。
- 中文导出器已对 `strategy_fill_count` 的展示标签做仅向前生效的准确性修正：该运行时计数包含策略归因的开仓、减仓和平仓，不等于“新开风险成交数”。第 1 至第 22 轮 write-once 文档保持逐字不变；从下一轮起显示为“策略成交数（含开仓、减仓和平仓）”，原始动作、成交回执和账户对象不受影响。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第六个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，仍未观察到改进；继续收窄强平、严格韧性与参与者身份主张，不补零。
- 第 23 轮已于 2026-07-31 05:01（北京时间）冻结六市场输入，并于 05:09 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。20 个注册候选中，仅 SOL 标记价 `74.51` 进入 `74.4234214475–74.55` 阻力拒绝空头区，但该候选状态为 `REJECTED_OR_UNKNOWN_GEOMETRY`、注册中点净 RR 仅 `0.2409`；按 2 bps 入场滑点、3 bps 止损滑点和运行时费率重算，假设入场价 `74.495098`、止损成交价 `74.95221458`、目标 `74.38`，成本后净 RR 仅 `0.118409`，低于 `1.5` 硬门，执行类型化风险否决。其余研究就绪区均未触发，本轮提交一个 `HOLD`，回执为 `ACCEPTED / NO_CHANGE`，没有订单或成交。
- 第 23 轮提交后仍为空仓且无挂单：权益与现金均为 `9929.53084768 USDT`，总净盈亏 `-70.46915232 USDT`、账户累计收益率 `-0.704692%`、未实现盈亏 `0 USDT`、已实现毛/净盈亏 `-65.25657428 / -70.46915230 USDT`、总手续费 `5.21257804 USDT`、持仓价值、挂单名义、毛杠杆、开放风险和成本价至止损口径均为 `0`；历史保持 18 个 lot（全部平仓）、11 个订单（全部取消）和 32 笔成交。
- Agent23 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T050916+0800_cycle-0023_agent23_zh_v2.md`，SHA-256 为 `72e1973c0a60dfeb4a9d26e6e6cb7532212302e542b9345b7cbbba546377a9f3`；23 轮记录二次导出全部为 `EXISTING_IDENTICAL`，逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`，账本和事务链各 `49` 条且均有效，运行继续为 `ACTIVE`、无待决策周期。Agent23 已使用修正后的“策略成交数（含开仓、减仓和平仓）”标签，既有 write-once 文档未改写。
- 新方法增量 `MC-8279aa5cafde5345e787` 的第七个未来窗口仍有六标的各 3 个 F 轴必需 `UNKNOWN` 和 R 轴 `strict_resilience=UNKNOWN`，共 `24` 项，仍未观察到改进；继续收窄强平、严格韧性与参与者身份主张，不补零。冻结新闻仅含公开发现元数据，没有将未核验标题当作方向因果证据。
- 第 24 轮已于 2026-07-31 06:02（北京时间）冻结六市场输入，并于 06:11 提交纸面决策；六标的覆盖率均为 `93.33%`、无整标的采集失败。20 个注册候选中，所有 `RESEARCH_READY` 闭区间均未触发；ETH 标记价 `1919.58379845` 命中已拒绝阻力空头候选，按运行时费率与滑点重算的成本后净 RR 仅 `0.265452`；SOL 标记价 `74.47811123` 同时命中已拒绝支撑多头和阻力空头候选，成本后净 RR 分别为 `-0.078979 / 0.062696`。两者均低于 `1.5` 硬门并执行类型化风险否决，其余标的由闭区间未触发阻塞；本轮没有订单、成交或新增名义，动作前无策略成交有效小时为 `1`，六小时探针尚未到期。
- 第 24 轮提交后仍为空仓且无挂单：权益与现金均为 `9929.53084768 USDT`，总净盈亏 `-70.46915232 USDT`、账户累计收益率 `-0.704692%`、未实现盈亏 `0 USDT`、已实现毛/净盈亏 `-65.25657428 / -70.46915230 USDT`、总手续费 `5.21257804 USDT`、持仓价值、挂单名义、毛杠杆、开放风险和成本价至止损口径均为 `0`；历史保持 18 个 lot（全部平仓）、11 个订单（全部取消）和 32 笔成交，动作后无策略成交有效小时增至 `2`。
- Agent24 v2 中文完整记录已生成至 `.runtime/theory-paper-v1/current/reports/zh/20260731T061117+0800_cycle-0024_agent24_zh_v2.md`，SHA-256 为 `d8217da4ecdb840cc0c8e09c61eb8535d006436d2e9ce7cf2910076f395b7fac`；记录包含标准账户、全部 18 个 lot、11 个订单、32 笔成交、六标的“输入—规则—判断—动作—结果—来源”轨迹、理论章节与公开来源映射、原始对象和事务绑定。24 轮导出返回 `schema_version=theory-paper-zh-audit-record.v2`，前 23 轮均为 `EXISTING_IDENTICAL`、第 24 轮为 `CREATED`，逐 lot 未实现盈亏与组合值差额为 `0 USDT`、状态 `MATCH`。
- 第三次精确八轮复盘 `review-003` 已于 2026-07-31 06:11（北京时间）冻结，严格覆盖 cycle-0017 至 cycle-0024：理论完整性 `94.75`、方法实践 `100`；假说结果为 `FALSIFIED=16 / SUPPORTED_AT_EXPIRY=11 / EXPIRED_UNSUPPORTED=2 / UNRESOLVED_UNKNOWN=10 / SUPPORTED_ACTIVE=27`，终局小样本诊断分 `39.31`，明确保持未校准、描述性边界；纸面绩效继续为账户净收益 `-70.46915232 USDT`、回撤 `0.704692%`、胜率 `27.7778%`、profit factor `0.490737`、总 R `-7.424328`，与理论/方法评分分离。
- 旧方法增量 `MC-8279aa5cafde5345e787` 在 cycle-0017 至 cycle-0024 的 8 个未来窗口中，必需未知数相对基线始终为 `8` 次出现，复盘处置为 `REJECT` 且未回写历史。复盘只为 cycle-0025 起激活一个未来生效的数据质量增量 `MC-b0b92f48ea0a26292feb`，下一未见窗口继续检验能否在不前视的情况下减少必需 `UNKNOWN`；不改变第 24 轮决策、账户或既有 write-once 文档。
- 复盘后运行继续为 `ACTIVE`，周期数 `24`、复盘数 `3`、无待决策周期；账本和事务链各 `52` 条且均有效，最新事务为 `review-003`。
- 已完成当前定时 Agent 数据能力核实：每标的实际成功取得 24 小时行情、标记价/指数价、持仓量、资金费和多空比、单帧盘口、聚合成交及五周期 K 线；分析主要依赖闭合 K 线结构、1 小时候选几何和纸面风险门，D/L/C 为辅助证据。24 个既有周期均持续缺少公开强平数据，严格流动性韧性只有单帧代理；新闻自动输入仅为 Google News RSS 标题元数据，最新周期只绑定 SNDK 与 HYPE 发现标题、未绑定一手新闻正文。正规补强主路径是前向保存 Binance 公共 `forceOrder`、普通/RPI 增量深度和聚合成交流，并对官方公告保存时点与正文摘要；真实参与者身份、逐笔开平仓角色和心理状态不能由公开聚合数据恢复，必须保持未知或代理。此次仅完成说明与需求记录，不修改冻结交易逻辑或启动额外采集。
- 用户终止时已核对退出链：SNDK `lot-000007` 于 cycle-0016 因冻结标记价 `1215.70761844` 超过固定目标 `1124.99` 被全量市价退出，实际退出价 `1215.46447692`；第 25 轮冻结标记价已为 `1348.75`，一小时 `UP`、近 6 根一小时涨幅 `+7.52597%`、ADX `79.7496`、效率比 `0.98824`、四小时近 6 根涨幅 `+25.73675%`。若只做静态持有反事实，该 lot 相比实际退出少获得毛价格收益约 `32.22637570 USDT`。
- HYPE `lot-000013` 于 cycle-0018 因冻结标记价 `54.39375714` 超过固定目标 `54.381` 被全量市价退出，实际退出价 `54.38287839`；第 25 轮冻结标记价为 `55.968`，四小时近 6 根涨幅 `+4.27654%`、一小时近 6 根 `+2.06909%`、十五分钟近 6 根 `+0.95564%`，十五分钟趋势 `UP`、效率比 `0.92218`。若只做静态持有反事实，该 lot 相比实际退出少获得毛价格收益约 `7.45921596 USDT`。
- 失效结论：当前 Agent 实际读取了上涨数据，但其行为层把“原固定止盈已越过”机械解释为必须全平，并把低周期延续证据压在父级状态之下；退出后又只等待远离现价的旧支撑/突破闭区间，没有部分止盈、剩余仓位跟踪止损、突破后续持、动态再入场或机会成本门。故理论/方法流程分不能证明决策有效；本测试对用户要求的动量识别与盈利持有目标未达标。
- 第 25 轮仅于 2026-07-31 07:03（北京时间）冻结分析，未提交 Agent 决策、未创建订单或成交，也未生成 Agent25 中文文档；运行原始状态保留为 `ACTIVE` 且 `pending_decision_cycle=25`，账本与事务链各 `53` 条并校验有效。该状态只表示不可变运行时尚有待决工件，不表示实验仍被授权继续。

### 进行中

- 无。用户已明确终止，后续自动周期、交易决策和方法增量检验均停止。

### 未开始

- 原计划的 72 小时终期总结未执行；本次只保留截至 24 个已提交周期的失败结论，不能冒充完整 72 小时结果。

### 当前阻塞

- 用户已撤回继续运行授权；不得提交当前待决的第 25 轮或创建后续周期。

## 八、需求变更记录

- 2026-07-30：SNDK 初始入场由 1070 改为 1125。
- 2026-07-30：新增 MU 为可主动交易标的，无初始仓位。
- 2026-07-30：确认 HYPE 纳入完整分析。
- 2026-07-30：确认公开数据、本地纸面、每小时分析、每 8 小时复盘和 72 小时实践。
- 2026-07-30：要求新理论优先、受控冒险、方法论沉淀和量化评分。
- 2026-07-30：要求所有工作围绕本需求记录，不再扩张旧历史工程。
- 2026-07-30：明确可执行形态当轮必须执行，六小时探针仅是无普通成交时的兜底，不是等待期。
- 2026-07-30：明确每轮记录八类方法观察，每八小时按具体流程、公式、数据和执行阻塞总结低分根因。
- 2026-07-30：首轮完成五仓保护、十一单取消和六标的假说冻结；每小时自动任务正式启用。
- 2026-07-30：新增要求：汇报 Agent1 首轮具体执行记录、可审计决策轨迹及理论依据来源；后续每轮定时交易必须按对应时间自动生成同等内容的中文文档，缺失时修改定时任务。
- 2026-07-30：Agent1 首轮中文记录已生成；定时任务已改为每轮自动补齐并校验中文记录，且不修改当前 72 小时实验的冻结交易逻辑与版本绑定。
- 2026-07-30：新增要求：每轮及 Agent1 首轮完整输出标准持仓与历史交易信息，包括精确开仓价、USDT 持仓规模、标记价、方向、盈亏、收益率、止盈止损价格与数量等字段。
- 2026-07-30：Agent1 v2 完整账户记录已生成；后续每小时任务已切换为 v2 标准账户、持仓、订单和成交记录要求，旧版 write-once 文档继续保留。
- 2026-07-30：新增要求：说明当前定时 Agent 在数据分析时实际能够获取哪些数据、依据哪些数据分析、哪些数据获取不到，以及缺失数据应如何通过正规途径获得；验收以当前自动任务配置、采集代码和最新冻结周期相互核对为准，不把候选接口或理论需求误报为当前能力。
- 2026-07-30：新增要求：把不可获取数据显式转化为可审计的多路径竞争假说，使用已取得且在决策时点可用的数据分别支持或反证各路径，并在每个市场周期根据新增数据重新审视、更新或否证；先建立适合当前复杂系统的框架流程，再完善定时 Agent。为避免污染正在运行的 72 小时 v1 基线，本次默认交付并行的 successor v2 影子流程，不在本次直接切换生产任务。
- 2026-07-30：successor v2 影子框架、四层设计、版本化配置、定时 Agent v2 提示词、确定性回放入口和测试已完成；cycle-0014/0015 连续回放通过并生成独立 sidecar，现有 v1 自动任务未切换。
- 2026-07-31：用户指出 SNDK 与 HYPE 的显著上涨动量未转化为持有、部分止盈或动态再入场，认为当前测试过度保守且无用，并明确要求停止。核对确认 Agent 并非未读取动量，而是静态止盈全平、父级优先规则、滞后候选几何和缺少续持/再入场合同共同导致行为失真；当前实验标记为“已终止、未达到验收标准”，第 25 轮保持仅冻结未提交。

## 九、缺失数据多路径推论与定时 Agent successor v2

### 最终交付结果

- 一套适配当前六市场纸面系统、每轮必执行的“缺口定义 → 可用证据 → 多条竞争路径 → 支持/反证 → 下一可观测量 → 跨周期复核 → 决策边界”框架；
- 一份符合四层模块化边界的 successor v2 系统设计，明确数据对象唯一归属、模块输入输出、版本化契约、事件、插件点、迁移与激活门；
- 可运行的 v2 影子推论实现、配置和定时 Agent 提示词，可对现有冻结周期生成独立 sidecar 工件，而不改写 v1 事务工件；
- 自动验证：时间点边界、缺失不补零、至少两条可区分竞争路径并保留 `OTHER_OR_UNKNOWN`、证据支持与反证、可证伪条件、下一可观测量、到期条件、跨周期修订状态和失败关闭。

### 验收标准

1. 每个标的、每个周期先列出不可获取或证据不足的数据项，并区分“接口失败、尚未采集、历史不足、公开市场结构上不可识别”；
2. 对每个需要推论的目标建立至少两条可区分的竞争路径，并始终保留 `OTHER_OR_UNKNOWN`，不得把单一路径、代理量或缺失值写成事实；
3. 每条路径必须记录因果步骤、支持证据、反证证据、证据相关组、可证伪条件、下一可观测量、到期时点和序数支持等级；相关代理不得重复计票；
4. 所有证据必须满足 `available_at <= decision_at`，并引用当前冻结工件中的事实或派生量；违反时点边界、必要字段缺失或契约无效时失败关闭；
5. 每轮必须读取上一轮同标的 v2 sidecar，对每条路径给出 `NEW / STRENGTHENED / WEAKENED / FALSIFIED / EXPIRED / UNCHANGED` 之一及数据变化依据；
6. 输出必须继续区分事实、派生测量、推论、竞争假说、情景、风险许可与纸面动作；不得输出校准概率、参与者身份或心理状态等公开数据不能识别的结论；
7. v2 实现能够对至少两个连续的既有冻结周期完成影子回放，生成结构化工件且不改变 v1 账本、事务链、决策或纸面账户；
8. 定时 Agent v2 提示词把上述流程设为每轮强制步骤；在当前 72 小时 v1 运行结束和影子验收通过前，不自动替换现有已启用任务。

### 当前范围

- 复用当前公开市场、新闻元数据、分析工件与既有动态假说图契约；
- 新增独立的 v2 领域推论模块、版本化配置、sidecar 导出入口、系统设计文档、定时 Agent v2 提示词和针对性测试；
- 使用现有冻结周期做只读影子回放；新工件写入独立 v2 影子目录。

### 明确不做

- 不修改当前 v1 理论、评分、交易门、冻结输入、事务工件或 72 小时验收口径；
- 不把未知值补零，不伪造强平、深度恢复、新闻正文、参与者身份、开平仓角色或心理状态；
- 不声称序数支持等级是概率、因果证明、盈利证明或实盘许可；
- 不接入付费、私有或需要新授权的数据源，不切换现有定时任务，不进行真实下单。

### 当前主要任务与状态

> 历史状态说明：本节记录形成 Section 13 前的阶段快照；其中固定
> `118`、A–G、较早 gate/场景数量及“尚未放行”的文字不再是当前机器
> 验收权威。当前执行只认 Section 13 与
> `THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0.md` 的 resolved identity
> set、A–I 和完整 canonical 场景/硬门。

- 需求记录与 v1 基线冻结：**已完成**（分支 `codex/s0-research-foundation`，HEAD `7ca3fc4f99a57f98217e703f222b295653ace87e`，运行 `msta-paper-20260729T212716Z-87cc29bb`，记录时已提交 16 轮）；
- Product Design 每轮可审计流程与输出信息结构：**已完成**；
- 四层模块化架构、契约、事件、插件与迁移设计：**已完成**；
- successor v2 影子实现与定时 Agent v2 提示词：**已完成**；
- 连续冻结周期影子回放和失败关闭验证：**已完成**；
- 现有定时任务切换：**受保护，未授权且本次不执行**。

### 交付与验证记录

- 系统设计：`THEORY_PAPER_INFERENCE_SUCCESSOR_V2_DESIGN.md`，覆盖每轮信息流程、严格四层架构、模块和数据对象唯一归属、IO 契约、事件、插件、数据模型、三阶段路线、验证门及 v1 兼容策略；
- 冻结配置：`config/theory_paper_inference_framework.v2.json`，包含 5 类推论目标、10 条命名路径、`OTHER_PATH / UNKNOWN_PATH` 分离、缺口分类、证据相关组、序数支持和修订状态；
- 定时 Agent 候选提示词：`config/theory_paper_automation_prompt.v2.md`，已把每轮流程固化为强制步骤，但状态为 `SHADOW_CANDIDATE_NOT_ACTIVATED`；
- 可运行实现：`trade_system/theory_paper/inference_v2/`，分别实现 Presentation、Application、Domain 和 Infrastructure 边界；支持历史连续回放、未来 `LIVE_PENDING_ANALYSIS` 旁路模式、源摘要/时点/符号绑定验证、相关组去重、六类修订、全量内存验证和 write-once sidecar；
- cycle-0014 sidecar：`.runtime/theory-paper-successor-v2/msta-paper-20260729T212716Z-87cc29bb/cycles/cycle-0014/inference-sidecar.v2.json`，摘要 `bddf8463d31f1e8d7684fe6810c76b78f68974ebf64ce1a115686de10e3b6776`；
- cycle-0015 sidecar：`.runtime/theory-paper-successor-v2/msta-paper-20260729T212716Z-87cc29bb/cycles/cycle-0015/inference-sidecar.v2.json`，摘要 `ad82c89032725685331f81301427e1a96dd05fe19641d7d6f1d5811fc3e16ed0`，正确引用上一摘要；
- 两轮每轮均准入 185 条时点合规证据、0 条未来证据违规；六标的每个均有 5 个推论目标，每目标 2 条命名路径加 `OTHER_PATH / UNKNOWN_PATH`；
- cycle-0015 相对 cycle-0014 的 120 条路径修订为 `STRENGTHENED=12 / WEAKENED=17 / UNCHANGED=91`；当前相邻一小时窗口没有到期或已触发硬证伪的路径，`FALSIFIED / EXPIRED` 由契约和单元测试覆盖，不伪造真实发生；
- 重复回放两份 sidecar 均返回 `EXISTING_IDENTICAL`；写入前后 cycle-0014/0015 的行情、新闻、分析、Agent 决策、决策回执和四份事务提交共 14 个 v1 源文件逐项 SHA-256 相同；
- theory-paper 与 successor v2 共 43 项测试通过；既有动态假说图静态契约 122 项测试继续通过。前者验证本次运行时流程和失败关闭，后者只证明 predecessor 静态契约没有漂移，不等同于市场有效性；
- 当前 v1 自动任务、提示绑定、交易逻辑、评分、账本、组合和风险门均未修改；successor v2 `shadow_consume` 仍为 `DISABLED`。

## 十、多时间尺度决策治理漏洞审查与 successor 修复

### 最终交付结果

- 对当前 Core 理论、研究契约、定时 Agent 提示词、纸面运行时、风险/组合动作和复盘评价做逐项审查，确认用户提出的“时间尺度坍缩、噪音越级、风险动作污染观点、短期结果误证长期判断、退出后无法客观再入场”等问题在何处已被约束、仅被文档提及、仍可绕过或完全缺失；
- 若存在漏洞，交付一套位于分析与纸面动作之间、可独立验证的多时间尺度决策治理模块，强制执行信号权限、跨层升级、观点与风险隔离、四状态转换、审查时钟、再入场合同和按原定时间窗口评价；
- 生成可审计的假设、信号和行为三类账本/sidecar，使用既有冻结周期进行只读影子回放；当前 72 小时 v1 基线及其理论、评分、交易门、账本、组合和自动任务不被修改或切换。

### 验收标准

1. 形成审查矩阵，将用户提出的原则逐项标记为 `RUNTIME_ENFORCED / CONTRACT_ONLY / PARTIAL / MISSING / BYPASSABLE`，并给出文件、字段、调用链或真实周期工件依据；不得把文档声明或测试夹具误报为运行时强制；
2. 明确区分并冻结五类决策权限：`STRATEGIC_HYPOTHESIS / STRUCTURAL_EVIDENCE / RISK_CONTROL / TACTICAL_EXECUTION / REVIEW_UPDATE`；每类只能改变自己拥有的数据对象；
3. 每个新增信号必须记录来源、`available_at`、时间尺度、信号类别、作用对象、独立确认、持续窗口、正常波动越界和改变的具体核心前提；缺少必要字段时不得升级；
4. 低时间尺度信号不得直接改变战略方向或将核心假设置为失效。跨层升级必须同时满足预注册的越界、持续、独立确认、核心前提受影响和非纯流动性/随机扰动条件，并生成可审计升级回执；
5. 建立 `A_VALID / B_TACTICAL_DISTURBANCE / C_CHALLENGED / D_INVALIDATED` 四状态机，冻结合法转换、触发证据、最低来源时间尺度和审查时钟；压力、浮盈浮亏、单根小周期 K 线及单一短期结果不得成为战略转换输入；
6. 风险控制或战术动作可以改变仓位、保护和执行节奏，但不得自动改变核心假设状态；战略失效必须由独立的结构证据转换命令完成；
7. 每个战术性退出或风险性减仓必须同时具有再入场合同，包含原假设状态、默认恢复策略、最低条件、分批恢复、价格/时间条件、最迟复审时点和取消条件；缺失时失败关闭，不能自然滑入无限期观望；
8. 战略审查只允许在预注册收盘时钟、到期时点或合格重大事件后发生；小周期执行审查和实时风险审查不得重写战略假设；
9. 决策质量必须按决策声明的目标时间窗口和原始规则评价；短期价格与动作方向一致只能记录为局部路径结果，不得直接标记中长期假设或战略动作正确；
10. 输出等价于三本独立账本：假设账本拥有战略状态，信号账本拥有证据分类与升级回执，行为账本拥有动作意图、风险原因、再入场合同和评价窗口；任何账本不得反向改写其他账本的既有记录；
11. 所有治理判断继续满足 `available_at <= decision_at`、摘要绑定、write-once、失败关闭和非概率边界；至少对两个连续真实冻结周期完成影子回放，并验证相同输入确定性一致；
12. 回放前后当前 v1 源工件、账本、事务链、组合与自动任务绑定保持不变；修复只作为 successor 候选，未经 72 小时基线结束、影子门通过和用户单独授权不得被当前定时 Agent 消费。

### 当前范围

- 审查 `CORE_TRADING_THEORY_v2_1.md`、研究系统契约、`trade_system/theory_paper/`、v1/v2 自动提示、现有复盘与连续真实周期工件；
- 新增独立的 successor 决策治理领域模块、版本化配置、审查报告、候选提示词/附录、只读 legacy adapter、write-once sidecar 和针对性测试；
- 使用当前运行中已经提交的冻结周期做历史影子回放，所有新工件写入独立 successor namespace。

### 明确不做

- 不修改正在运行的 v1 理论、评分、交易规则、风险数学、冻结周期、决策/事务工件、纸面账户或自动任务；
- 不用本次个人复盘倒推或改写既有周期的原始判断，也不据后续价格为历史动作补造理由或再入场条件；
- 不把压力、恐惧、情绪或参与者心理从公开市场代理量中反向识别为事实；
- 不为信号设置未经样本验证的精确概率或连续权重，不声称影子契约证明预测有效、盈利能力或实盘许可；
- 不接入新付费/私有数据源，不进行真实下单，不扩大为通用交易平台重构。

### 当前主要任务与状态

- 需求记录、分支、HEAD、活动 run 和现有 successor v2 基线冻结：**已完成**；
- 理论、契约、提示词、运行时、动作和复盘逐项审查：**已完成**；
- 漏洞分级与最小 successor 治理设计：**已完成**；
- 独立实现、连续周期影子回放和失败关闭验证：**已完成**；
- successor 提交前门、可信 evidence/clock/repository、lot 再入场执行和
  horizon evaluator 接线：**未开始，属于激活前阻塞，不在本次冻结基线内实施**；
- 当前 v1 自动任务切换：**受保护，未授权且本次不执行**。

### 交付与验证记录

- 审查报告：`THEORY_PAPER_MULTI_TIMESCALE_GOVERNANCE_AUDIT_v1.md`，逐项给出
  `RUNTIME_ENFORCED / CONTRACT_ONLY / PARTIAL / MISSING / BYPASSABLE` 评级，
  并用 v1 调用链、只读内存反例和真实 MU cycle-0014→0016 链确认漏洞；
- successor 设计：
  `THEORY_PAPER_MULTI_TIMESCALE_GOVERNANCE_SUCCESSOR_V2_DESIGN.md`，区分五类
  业务决策权限与四层代码架构，明确唯一 owner、版本合同、事件、插件、数据模型、
  legacy adapter 和三阶段 gate；
- 冻结治理配置：`config/theory_paper_decision_governance.v2.json`，状态
  `SHADOW_CANDIDATE_NOT_ACTIVATED`，无 paper action authority；
- 候选自动提示：
  `config/theory_paper_automation_prompt.v3.md`，同时固化缺失数据竞争路径与多时间
  尺度治理流程；未绑定当前 automation-2；
- 可运行 shadow core：`trade_system/theory_paper/governance_v2/`，实现 legacy
  审查、严格治理卡纯 validator、真实 horizon 窗口规则、隔离路径和 write-once
  legacy sidecar；当前只具有 `NONE_SHADOW_ONLY / NONE_VALIDATION_ONLY`；
- cycle-0014 sidecar：
  `.runtime/theory-paper-governance-v2/msta-paper-20260729T212716Z-87cc29bb/cycles/cycle-0014/governance-sidecar.v2.json`，
  摘要 `c80d65d74d7bd2e4c3f925ce1c2733ad2ceb12d7e06f3b9dbb7305aaa223066d`，
  `45 blocking / 2 warning`；
- cycle-0015 sidecar：摘要
  `da0a91770b6da53cc55fc9fac7fc8e4063f44793c03498d3818cc1bcd7663817`，
  `44 / 4`；
- cycle-0016 sidecar：摘要
  `aa9445948a7f253e7e8a26df1868741483a06e46726a5a6fcae6bb7b57293ece`，
  `44 / 3`；
- 三周期重复回放全部返回 `EXISTING_IDENTICAL`；18/18 标的保持
  `UNDECLARED_LEGACY / UNKNOWN / null reentry`，没有从 reason 补造历史理由；
- 25 项治理测试覆盖时间尺度越级、self-signed promotion、genesis 自报 C/D、
  EXIT 冒充 HOLD、缺失/自签再入场、同 ID 静默改写、C 无证据恢复、换 ID、
  断链、一分钟战略 horizon、完整窗口不足、路径逃逸和 write-once 冲突；
- theory-paper、缺失数据 successor 与治理 successor 联合 68 项测试通过；
  research-system v1/v1.1/v1.2 静态契约 262 项测试通过。后者仍只证明静态/合成
  契约未漂移，不代表运行时治理、预测有效或盈利；
- 独立代码与架构复核确认：已知纯函数/路径负例均失败关闭；剩余阻塞仅为尚未接线的
  accepted-ledger repository、trusted signal/promotion/clock、
  `NewHypothesisReceipt`、lot/reentry executor 与 trusted horizon evaluator；
- v1 Core、`theory.py`、`portfolio.py`、`experiment.py`、prompt v1、cycle-0014
  至 0016 的 analysis/agent-decision/decision 摘要和 automation-2 TOML 与审查前
  完全一致；automation-2 仍为 `ACTIVE` 且仍绑定 v1 提示。

### 需求变更记录

- 2026-07-30：用户基于个人复盘新增“多时间尺度决策治理”要求，要求全面审查当前 Agent 理论是否仍允许短周期信息污染长期判断、风险动作污染观点、局部结果误证全局判断及退出后缺少再入场机制；确认存在漏洞时进行严谨修复，同时保持当前冻结实验不被回写。
- 2026-07-30：完成当前 v1 漏洞审查与隔离 successor shadow core；独立复核发现并
  封闭 EXIT intent、self-signed promotion、genesis C/D、假设换 ID、伪战略
  horizon 和输出路径逃逸等候选绕过。当前 v1 未切换，系统级修复等待阶段 2
  提交前门与可信 authority 接线及用户单独授权。

## 十一、SNDK 只读、不可后见修改的执行事故审计

### 最终交付结果

- 一份以当前已提交历史工件为唯一事实来源的 SNDK 执行事故审计报告；
- 一份逐项绑定文件、摘要、字段和计算口径的证据索引；
- 分开裁决理论、Agent 实施、数据、状态管理与定时系统设置责任；
- 给出最小修复方案，但本次不实施任何修复。

### 验收标准

1. 以每轮 `decision_at` 当时可用的数据为边界，重建已提交周期的逐小时五层时间线；
2. 分别定位首次假说降权、首次减仓、首次清除核心仓位、首次完全空仓及首次拒绝再入场；
3. 核验六项多时间尺度治理原则，并为每项结论提供具体工件和字段依据；
4. 检查上一轮结构化状态、失效条件和待验证事项是否被真实读取，识别状态遗失、压缩、覆盖、截断、时间戳或窗口错位；
5. 识别实际决策目标、空仓成本处理和退出/再入场门槛不对称；
6. 分开核算实际已实现盈亏、未实现盈亏、交易成本、冻结持有基准和相对机会损失；
7. 只使用各时点当时可用输入，比较原规则、严格保持战略假说和仅战术减仓三条冻结反事实路径；无法由历史规则唯一识别的结果必须标为不可识别，不补造参数；
8. 最终明确首次根因节点、直接与系统性原因、受影响规则以及理论/实现/数据/状态/定时系统责任；
9. 审计前后理论、提示词、代码、阈值、仓位记录、历史输出、账本和事务工件保持不变。

### 当前范围

- 当前运行 `msta-paper-20260729T212716Z-87cc29bb` 已提交的 cycle-0001 至 cycle-0024；
- cycle-0025 仅作为“冻结但未提交”的边界证据，不纳入已发生决策或收益；
- 当前冻结理论、v1 提示词、运行时实现、自动任务配置、逐轮行情/分析/决策/执行工件、账本、复盘和组合状态；
- 只新增本需求记录、审计报告及证据索引。

### 明确不做

- 不修改理论、提示词、代码、阈值、仓位记录、历史输出、账本、事务链或自动任务；
- 不用退出后的上涨为退出时补造失效规则、核心/战术仓位比例或再入场条件；
- 不把机会损失记作实际亏损，不用短期已实现收益证明战略退出正确；
- 不把无法从历史工件唯一识别的反事实结果伪装成精确值；
- 不实施最小修复方案，不恢复定时任务，不进行真实交易。

### 当前主要任务与状态

- 冻结分支、HEAD、运行、已提交周期和未提交第 25 轮边界：**已完成**；
- 逐轮证据盘点、时间线和首次偏离定位：**已完成**；
- 状态连续性、决策函数、定时系统责任审计：**已完成**；
- 收益账本与冻结反事实回放：**已完成**；
- 技术报告、证据索引和独立复核：**已完成**；
- 修复实施：**明确不做**。

### 交付与审计结论

- 可移植技术报告：
  `audits/2026-07-31-sndk-execution-incident/SNDK_EXECUTION_INCIDENT_AUDIT.html`；
- 证据索引：
  `audits/2026-07-31-sndk-execution-incident/EVIDENCE_INDEX.md`；
- 报告数据契约：
  `audits/2026-07-31-sndk-execution-incident/artifact.json`；
- SNDK 首次完全空仓为 cycle-0016；cycle-0022 只是全组合首次空仓；
- cycle-0016 的退出由事前冻结 1124.99 目标触发，对冻结 v1 的 `T-023`
  忠实；不能以后续上涨反向判为历史规则违规；
- 首次潜在根因从 cycle-0001 即存在：历史假说和完整仓位虽被保存，却不进入
  下一轮分析/决策函数；首次可观察偏离为 cycle-0011 的 PHI/仓位语义分裂，
  首次不可逆操作节点为 cycle-0016 的全退且无再入场合同；
- 主要责任属于 Agent 实施和状态管理；理论没有被本单例否定，但存在“不交易趋势
  延续”与趋势捕获目标的范围错配；数据缺口非根因；定时漏槽、1H barrier 与
  cycle/hour 时钟漂移是重要放大因素；
- SNDK 实际净已实现收益 5.69057657 USDT，未实现 0；lot-000007 持有至
  cycle-0024 的同风险假设平仓机会差 30.52866745 USDT，仅为反事实机会差，
  不记作实际亏损；
- “严格保持战略超跌反弹”与“仅战术减仓”没有历史唯一规则或比例，报告只给
  敏感性，不补造精确路径；
- Data Analytics artifact 通过 schema、打包和结构校验；本机 Chrome 手工加载
  已确认首屏、指标和首张图表可见。插件自动浏览器 verifier 超时，未据此扩大
  或改写报告结论；
- 审计完成后已复核受保护理论、提示、代码、自动任务和 335 个 run 文件摘要；
  run 聚合仍为
  `2e228524384f91878db76d5d18b7d08d23702550f8ea71cbcc1aea03017b0134`，
  其余逐文件摘要也与审计开始值一致；本节仅记录交付，不授权实施修复或恢复
  automation。

### 需求变更记录

- 2026-07-31：用户要求对 SNDK 已发生的逐小时运行做只读、不可后见修改的正式事故审计，先提交审计报告和证据索引，严格分开理论、Agent 实施与定时系统设置问题，不立即修复。
- 2026-07-31：完成 cycle-0001 至 cycle-0024 的点时事故审计、收益分账和冻结反事实；保留不可识别参数，不改历史运行，提交报告与证据索引后停止于修复授权边界。

## 十二、Theory Agent V2 离线重建设计与修复

### 用户最终需要的交付结果

- 先给出并冻结一份“理论如何从市场证据形成连续战略假说并治理交易”的完整流程与技术合同；
- 在理论审查完成后，给出不以粗糙 hourly Agent 为系统核心的 V2 四层架构、模块边界、schema、事件、状态转换表、插件边界和 legacy 兼容策略；
- 在 legacy v1 旁实现独立、离线、counterfactual-only、fail-closed 的 V2 core，使跨周期状态、关闭的 CORE/TACTICAL/HEDGE 角色枚举、TargetReachedEvent、ReentryContract、动态几何、调度与事件化撮合成为机器不变量；当前 E0 只准 CORE/TACTICAL，HEDGE 必须在独立合同接受前硬拒绝，本阶段不授予 paper action authority；
- 对冻结 cycle-0001 至 cycle-0024 执行 A–G 点时消融，并使用多类预注册离线场景验证功能忠实性、机会捕获与风险变化；
- 补充“路径—收益—风险—仓位”治理：把初始仓、确认仓、趋势仓等分段计划、账户风险预算、当前价增量盈亏比、剩余风险额度和无法盯盘时的离线执行约束编译为事前合同；不得把“有计划逐步加仓”继续留作自由文本；
- 建立“有边界的 Agent 自主权”：Agent 动态提出并排序多路径、几何、仓位和管理动作；确定性系统负责 PIT、状态连续性、复算、风险/权限和执行安全，不得用静态 validator 代替市场判断或把可行动作集合长期压缩为 ABSTAIN；
- 建立可移植的“Agent 集群 + 确定性内核”协作包：以项目级 `AGENTS.md` 约束全局权限和启动顺序，以职责单一的 skills 定义各 Agent 的输入、输出、工具与验收条件，使新对话或新项目不依赖旧聊天隐含记忆即可恢复同一套动态分析流程；
- 提交测试用例、消融结果、验收报告和未通过门清单；本工程不恢复 automation-2。

### 验收标准

1. 理论合同明确事实、测量、状态、竞争路径、战略假说、仓位角色、风险、动作、执行、评价的完整顺序和各时间尺度权限；
2. 每个 symbol/episode 只有一条 accepted `StrategicEpisodeState` 版本链，下一轮必须消费上一 accepted hash、决策、review、invalidators 和 pending observations；
3. 支持 `ACTIVE / CHALLENGED / RISK_REDUCED / REENTRY_PENDING / INVALIDATED / CLOSED`，每次变化必须生成可验证 `TransitionReceipt`；
4. 所有 V2 lot 必须且只能从 `CORE / TACTICAL / HEDGE` 中取一个角色，并绑定 episode、entry hypothesis、risk budget 与 exit intent；当前 E0 lot 仅允许 `CORE / TACTICAL`，`HEDGE` 在独立合同接受前不得进入候选、回放或策略收据；
5. 固定目标编译为 `TargetReachedEvent`；未失效时的全平必须原子生成 `ReentryContract`；
6. 静态几何具有 regime、有效期、失效与替换规则，能在区间到趋势迁移后重建动态几何；
7. 动作合同至少覆盖核心持有、战术加减、部分止盈、核心跟踪、战略退出、重入、几何注销/重建和有义务 abstain；
8. scheduler 只唤醒；战略时钟绑定闭合 4H/1D 或合格事件；漏槽显式记录；barrier 按预注册事件化规则成交；
9. automation/runtime/manifest/authorization 任一不一致时 fail closed；
10. 功能、行为、收益风险和机会成本四组指标分离，外生与策略归因分离，未模拟 funding 保持 UNKNOWN；
11. A–G 消融只使用各时点可用数据，不能补写 cycle-0025 或按后续价格改变规则；
12. 跨场景验证至少覆盖趋势延续、反弹失败、假突破、震荡、深回撤恢复、无回撤加速和事件跳空；
13. 所有新对象有唯一 owner、版本兼容策略、mock、独立测试面和不可绕过的提交前门；
14. 旧 24 轮、账本、事务、理论 v2.1、v1 提示和 automation-2 保持不变且 PAUSED；
15. 只有全部硬功能门和样本外纸面门通过后，才可另行申请创建新的 V2 实验；本需求不授予该激活权限。
16. 每个可交易路径具有不可变 `PathPayoffMatrix`，至少分离失败、正常反弹、趋势延续和衰竭，并记录净收益/损失、成本、跳空/滑点边界、概率是否校准及盈亏平衡阈值；
17. 每个 episode 的 `AccountRiskBudgetEnvelope`、`EpisodeRiskAllocationReceipt` 与 `StagedPositionPlan` 明确总风险、已用风险、预留风险、分段 tranche、触发/失效/到期、独立几何和剩余收益风险；原仓浮盈不得自动补贴新仓风险；
18. 每次加仓必须是事前注册 tranche 的状态转换，重新计算增量风险与组合最坏损失；不得因“趋势看起来更明确”或错失焦虑临时追入；
19. ADD 继续受 Core T-033 和 PROBE_ONLY 约束：当前只允许 schema 与 E0 反事实回放；未来必须通过独立 ADD protocol、校准和权限 envelope，当前工程不得隐式授权；
20. `SupervisionAvailabilityContract` 明确有人值守、无人值守但已保护、禁止新增风险三种模式；休息时只能执行机器可表达且同时注册保护的条件路径，否则只调整风险，不改变战略观点。
21. `AutonomyEnvelope` 明确不可自主改变、可在范围内自主选择和必须升级审查三类权限；总风险、前视、数据质量、实验冻结和真实交易授权不可由 Agent 修改；
22. Agent 可以在 envelope 内提出动态路径组合、置信/不确定性、动态几何、CORE/TACTICAL 比例、部分止盈/跟踪/重入和预注册 tranche 候选；系统只能按 typed constraint 复算和过滤，不得以自然语言“谨慎”替代决策；
23. 对每轮保留完整 `AgentProposalEnvelope → DeterministicCalculationBundle → FeasibleActionSet → AgentSelection → GovernanceAssessmentReceipt` 链；可行集合非空却长期 ABSTAIN、系统拒绝原因不对应硬约束、或 proposal 被静默改写都属于功能失败；
24. 六类动态职责（市场路径、战略状态、动态几何、敞口/仓位管理、重入、执行战术）作为四层架构内的独立 Domain 模块落地；默认运行拓扑收敛为 Proposer、Challenger、Selector 三个单职 Agent 与确定性内核，不增加第五/第六代码层，也不由一个大提示词同时拥有提案、复算、约束、选择和提交全部权威。
25. 明确划分 Agent 与确定性内核：Agent 只负责难以固定化的候选路径、解释、竞争假说、计划组合与可行集合内选择；PIT admission、数值复算、风险上限、状态 reducer、事件排序、权限和提交必须由四层系统中的确定性代码模块拥有，不得包装为运行时 Skill 或让 Skill 摘要成为内核正确性/提交权限的信任根；
26. 每个集群角色有唯一职责、版本化 typed input/output、允许工具、禁止事项和失败返回；任何角色不得同时提出市场结论、验证自身结论并提交 accepted state；
27. 集群仅通过持久化、带摘要和版本的交接对象协作；聊天摘要、上一 Agent 的自由文本结论或“大家同意”不得成为 accepted state、事实或权限来源；
28. Agent 间不得自由讨论或投票；默认会话固定为一次提案、一次质疑、确定性复算/约束、一次可行域内选择，最终 accepted chain 只有一个 `UnitOfWork` 提交者；模型共识或单个 Agent 自签不得绕过确定性复算和硬约束；
29. 新对话必须从 `AGENTS.md` 指定的需求记录、理论版本摘要、accepted state chain head、schema/skill 版本和权限 envelope 启动；新项目必须加载 accepted head 或显式 state-genesis contract。导入旧链需用户明确授权、完整摘要与 migration receipt，且不得继承凭据、runtime/automation ID 或 paper/live 权限；缺任一必需输入时 fail closed，不得凭旧会话记忆补齐；
30. 可移植 skills 必须通过结构校验和至少一轮隔离 forward test，证明角色能在无旧聊天上下文时生成合规 typed handoff，同时拒绝越权提交、未来数据、无证据状态迁移和 paper/live 动作；
31. 集群验收必须单独测量动态覆盖、独立意见保留、动作集合多样性、硬约束拒绝准确性、跨 Agent 状态一致性、相同冻结输入的重放差异和成本/延迟；Agent 数量增加本身不构成能力提升证据。
32. 每个实际调用的三类生成式角色 skill 必须生成 `SkillResolutionReceipt`，证明 manifest 中的 canonical source、解析模式、实际加载位置、完整 package bytes 与 `agents/openai.yaml` 摘要一致；每个确定性内核组件必须另行生成 `KernelComponentResolutionReceipt`，证明 code/port/schema/policy 兼容，两类回执不得互相替代；项目内 source 文件存在不等于已安装或可调用；
33. Agent 与确定性组件的非权威输出必须写入按 run/producer/artifact ID 隔离的 write-once 路径，摘要冻结后不得覆盖，不得使用 `current/latest` 可变别名；`UnitOfWork` 只消费 manifest 明列的精确 artifact ID 与 digest。
34. C1.0 前必须满足 Architecture 初始 schema 身份、SchemaRegistry entries 与 portable schema 文件集合完全相等，并能将 error/event/object-owner/constraint registries 与 run-global event chain 两次独立物化为相同字节；集合相等本身不能替代 payload、owner、幂等和无环合同。

### 当前范围

- 当前分支/物理工作区快照及已有 governance v2 shadow 资产；
- 新增候选理论合同、目标架构、V2 独立代码 namespace、版本化 schema、离线 replay/scenario 工具、测试与报告；
- 新增项目内可移植的集群设计、`AGENTS.md` 模板、cluster manifest、role-skill source 和 typed handoff 合同；是否安装到用户级 skills 或复制到其他项目，待明确目标位置后另行执行；
- 冻结 SNDK cycle-0001 至 cycle-0024 只读输入；
- synthetic/preregistered 场景仅用于合同、状态与执行语义验证，不作为盈利证明。
- 用户给出的 SNDK 风险收益估算作为理论接口需求和 seen illustration；HYPE 数字与判断视为用户提供、未在本工程中验证，不产生当下交易建议。

### 明确不做

- 不修改 `.runtime/theory-paper-v1/current`、cycle-0001 至 cycle-0025、ledger、transaction、历史收益或 sidecar；
- 不修改或恢复 automation-2，不连接凭据、私有 API、真实账户或 live order；
- 不用 SNDK 后续上涨选择固定核心比例、概率、阈值或最优动态退出参数；
- 不把 30%–40%–30% 或最多三段直接提升为通用理论常数；它们只能是可配置、待校准的个人执行 profile；
- 不把二元 3:1 简化盈亏比当作已校准胜率、真实 EV 或可成交保证；
- 不把“释放自主权”解释为允许 Agent 自签 evidence/promotion/clock/permission、修改风险上限、绕过冻结协议或直接发送 paper/live order；
- 不把多个 Agent 的投票、相互引用或语言一致性当作事实、校准、风险许可或最终提交权；
- 不覆盖当前项目根 `AGENTS.md`，不在未确认安装位置时写入用户级 skill 目录，也不假定新对话会自动继承旧对话状态；
- 不把单例消融、合成场景、测试通过或 paper 结果宣传为预测有效、稳定盈利或生产许可；
- 不把 legacy `experiment.py/theory.py/portfolio.py` 继续扩张为 V2 核心；旧实现只能作为只读数据源或兼容 adapter；
- 不在理论合同冻结前开始详细实现，不在 schema/contract 冻结前并行修改跨模块接口。

### 当前主要任务与状态

- 扩展需求记录与冻结当前权威边界：**已完成**；
- 理论完整流程与技术方案简报：**已完成**；
- 理论缺口审查与 V2 理论合同：**已完成离线实现前一致性审查；未接受为 Core addendum，且无 paper/live authority**；
- 路径盈亏矩阵、风险预算、分段仓位与离线注意力约束的新增理论审查：**进行中；该增量尚未获得 schema/reducer 实现放行**；
- 有边界自主权、可行动作集合与 Agent 选择链设计：**集群 C0 合同已完成；E0 仍只允许未来的冻结提案与反事实选择，尚未实现**；
- 可移植 Agent 集群、`AGENTS.md` 启动合同与 role skills 设计：**C0 设计已完成并通过无剩余 P0/P1 的独立复核；C1.0 schema、项目模板与三个 role skill 尚未物化、安装或接线**；
- 四层架构、模块、schema、事件和状态转换设计：**进行中；集群/确定性内核边界已闭合，其他业务 reducer 合同仍未全部完成**；
- V2 离线核心实现与 legacy adapter：**未开始**；
- A–I 消融、跨场景回放与指标：**未开始**；
- 测试、验收报告和旧工件摘要复核：**未开始**；
- automation-2 恢复或新 V2 实验激活：**明确不做，需未来单独授权**。

### 需求变更记录

- 2026-07-31：用户接受事故审计冻结结论，要求启动 V2 离线修复工程；先审查和完善理论，再进行完整系统重设计、离线实现、消融与跨场景验收，禁止把 hourly automation Agent 继续作为决策核心。
- 2026-07-31：完成市场分析—交易完整流程简报、理论形式化审查和三轮独立一致性复核；`STRATEGIC_EPISODE_POSITION_GOVERNANCE_CHALLENGER_v0_1.md` 已清零阻断 schema/reducer 的 P0，只允许进入 E0 离线实现，不构成 Core 接受或交易权限。
- 2026-07-31：用户补充个人与 Agent 的共同弱点：未把多路径盈亏、账户风险、预留加仓额度和休息/注意力约束预注册，导致首仓后最多调整一次。需求新增独立路径风险与分段建仓合同；ADD 仍保持 E0 反事实、无 paper/live 权限。
- 2026-07-31：用户进一步要求系统不得以过窄规则锁死 Agent 的动态分析能力。新增 bounded-autonomy 设计：Agent 在不可变安全 envelope 内拥有路径和动作提议/选择权，确定性内核只做状态、计算、约束和权限；可行集合被错误压成长期 ABSTAIN 作为系统缺陷验收。
- 2026-07-31：用户提出以 Agent 集群承接不可量化的动态职责、以确定性系统承接可计算职责，并通过 `AGENTS.md` 与可复用 skills 在新对话或新项目恢复能力。需求新增可移植集群包、typed handoff、单一提交权、无隐藏记忆启动及隔离 forward test；本阶段不覆盖现有项目治理文件，也不安装到用户级目录。
- 2026-07-31：完成三角色混合集群 C0 设计闭合：Proposer、Challenger、Selector 只处理开放性推理，确定性内核独占 PIT、复算、约束、状态、事件和 UnitOfWork；118 个初始 schema 与 portable tree 集合相等，四类 registry、run-global event chain 与 UoW 无环合同通过独立 P0/P1 复核。该结论只放行 C1.0 schema 物化，不表示 skills 已安装、系统可运行或获得交易权限。

## 十三、完整落地、冻结回测与第二轮进入合同

### 用户最终需要的交付结果

- 完成所有仍属必要的 V2 理论、业务 reducer、数据/权限、Agent 集群和四层系统设计，不以最小实现删减已注册理论概念；
- 物化 C1.0/C1.1 合同与可移植三角色 skills，实现独立 `theory_paper_v2` E0 离线核心、确定性计算/约束内核、状态链、风险/分段仓位、动态几何、重入、调度/撮合、唯一 UnitOfWork、只读 legacy adapter、回放/场景/报告能力；
- 使用第一轮冻结数据先做严格点时回测、A–I 消融、三条冻结反事实和预注册场景验证；
- 第一轮冻结回测通过下述门后，创建与 automation-2 完全隔离的新 V2 本地纸面实验，沿用第一轮六市场、10,000 USDT、每小时分析、每 8 小时复盘、72 小时总结和中文逐 lot/订单/成交/假说审计模板；
- 理论若未达到预注册功能或行为目标，只能生成新版本并从下一未见窗口生效；不得回写第一轮数据、规则、阈值或结果。

### 新增验收标准

1. 先完成并冻结路径盈亏、账户/episode/tranche 风险、分段仓位、监督可用性、有界自主权及所有业务 reducer 的闭合状态表、错误表和不变量，再实现跨模块业务逻辑；
2. C1.0 以冻结后的 canonical implementation contract 为唯一身份表；其完整 schema 集合及 Schema/Error/Event/ObjectOwner/Constraint/PluginPolicy registries、run-global event chain 和摘要必须两次独立物化为完全相同字节。历史草案中的 `118` 仅是修订前基线数量，不得覆盖后续已接受且必要的合同对象；
3. C1.1 必须生成项目权威 cluster manifest、write-once 布局、`AGENTS.template.md`、Proposer/Challenger/Selector 三个 role skills、各自 `agents/openai.yaml`、SkillResolutionReceipt 与 KernelComponentResolutionReceipt；
4. 四层 V2 E0 核心必须独立于 legacy `experiment.py/theory.py/portfolio.py`；旧代码和旧 24 轮只能通过只读 adapter 消费；
5. 所有 E0 输出必须绑定 `external_execution_authority=NONE_E0`、`executable=false`；paper/live adapter 在 E0 阶段必须拒绝；
6. 隔离冷启动、Domain/Application/Infrastructure/Presentation 合同测试、非法状态/缺失数据/未来数据/权限泄漏测试、write-once 幂等测试和相同输入重放必须全部通过；
7. 第一轮回测各 arm 使用完全相同的 point-in-time bundle 和同一组候选提案，不得为不同 arm 重新生成有利提案；
8. 第一轮进入第二轮的硬门为：零旧工件写入、零前视、零无 prior-state hash 的状态迁移、零无原因核心清除、零存活 thesis 全平后缺失 ReentryContract、零软警告删除硬可行候选、风险/权限门 100% 正确、确定性摘要重放 100% 一致、canonical implementation contract 当前完整的 32 个场景全部满足各自状态/风险不变量；
9. 第一轮进入第二轮的行为与绩效门为：完整 I 相对冻结 A 必须提高净收益和主要路径机会捕获；最大回撤不得超过预注册账户 5% 硬上限，且不得比 A 高出超过 `max(0.25% 账户权益, 25% × A 最大回撤)`；排除 SNDK 后不得出现由无权限 ADD、止损放宽或风险超限换来的收益；这些门只决定是否值得开展未见纸面窗口，不构成预测或盈利证明；
10. 三角色集群必须与同 token/调用预算的强单 Agent 基线比较；若不能提升动态候选覆盖、独立缺陷发现或可行动作质量，或安全/状态错误更高，则第二轮默认使用表现更优的拓扑，而不因“集群”形式强行采用三 Agent；
11. 第二轮初始外生多头沿用第一轮五标的及原名义金额，MU 仍无初始仓；每个初始 `entry_price` 固定为启动点时公共标记价的 `1.01` 倍并向上按该标的 tick 取整，因此保证 `entry_price >= 101% × genesis_mark`。该字段模拟已有持仓成本，不创建入场成交或高价限价买单；
12. 第二轮原始挂单沿用第一轮每张订单相对其原初始入场价的比例，并映射到新的初始入场价后按 side-aware tick 规则取整；所有映射值、genesis mark、来源时间、摘要和公式在 Agent1 前冻结；
13. 第二轮外生初始仓沿用首个有效周期内“保护、减仓或退出”的 SLA；新增策略风险从第一笔起必须具有父 episode、角色、tranche、独立几何、组合最坏损失和机器可表达保护；
14. 第二轮使用新的 runtime ID、manifest、权限 envelope 和独立自动任务；不得恢复、修改或复用 automation-2，也不得继承旧 runtime ID、pending cycle、账户状态、凭据或 action authority；
15. 第二轮仅允许本地 paper simulation 与公开数据/正规一手信息源，不连接私有账户、不读取密钥、不发送真实订单；“给予一切权限”解释为允许本项目文件开发、测试、联网研究、公开数据采集、项目及用户级 skills 物化和通过门后的独立纸面实验，不扩展为实盘资金权限。

### 当前范围与明确不做

- 当前先完成设计、代码、测试和第一轮冻结回测；第二轮只有在机器可核验门通过后才创建；
- 可以检索最新官方文档和一手研究，但外部理论只能作为带来源的新候选，必须与 Core v2.1 的事实/推论/权限边界兼容或显式版本化替代；
- 可以选择项目权威 skill source 加用户级派生安装的双层方案，但项目 source/digest 始终是本项目权威；
- 不以“最优理论”作无法证实的绝对声明；最优仅指在冻结目标、证据和约束下的当前最佳可辩护设计；
- 不为使第一轮回测通过而事后修改候选、阈值、初始点位、比较臂或评估门；任何未通过都保留原结果，再产生下一版本；
- 不因第一轮 seen 回测通过直接宣称预测有效、正期望、稳定盈利或 live-ready；第二轮是未见纸面证据采集，不是实盘授权。

### 当前主要任务与状态

- 需求与第二轮进入合同：**已冻结**；
- 剩余业务理论与 reducer 合同：**canonical implementation contract v1.0 已完成最终独立复核，P0=0，当前冻结 SHA-256 为 `8442abe9bf94f358314221e2f97d8e94ce63aae8b560814c8f7f174da5c894b1`；只放行 E0 实现，不构成 Core/paper/live 接受**；
- C1.0/C1.1 物化：**已完成。C1.0 冻结 manifest digest=`e296d51105f32d3bb65b429ee0a0d6e3f4d6e0da3886c039711ea7a5ccc4e760`，142 个 schema 物化为 154 个 portable files，双隔离目录逐字节一致；三个项目权威 role-skill 已生成并精确安装到用户级 skills，SkillResolutionReceipt 全部 PASS；12 个确定性内核组件与 ClusterBootstrapReceipt 全部 PASS，cluster bootstrap digest=`1aec7d5e8e4d96b90d8213fa14d3ce5eaeffaf45671480a4d31b6b97249a3a9e`**；
- V2 E0 四层核心与 legacy adapter：**已完成。包括战略连续性、PIT/时间尺度权限、竞争路径、风险预算与分段仓位、监督/离线安全、动态几何、重入、调度、撮合、路径盈亏与机会成本、Agent 三角色固定 DAG、33 项硬约束、唯一 UnitOfWork、事件兼容、只读 V1 adapter、E0 paper/live 显式拒绝、拓扑比较、场景、CLI 与中文报告；全部仍为 `NONE_E0`、不可执行**；
- 隔离测试、第一轮冻结回测与验收报告：**已完成。V2 回归 131/131、全项目回归 1115/1115；最终不可变运行 `theory-agent-v2-round1-e0-20260731T075833Z` 两次重放摘要一致，32/32 canonical 场景 PASS，A 组账本/动作/成交精确复算，V1 源树摘要前后均为 `aba02e17eca90ab4b4ae652c485940523e6c0f0ae2f78eae485c8a5019264085`，artifact index digest=`51494a58214352579b4e992f1cf2b9008756de47bcd0a87d71fe1ed894dbb325`**；
- 第二轮独立纸面实验：**未获授权、未创建。工程闸门为 `PASS_ENGINEERING`，但 B–I 缺少事前持久状态、CORE/TACTICAL、ReentryContract、动态几何与完整统一候选流，行为/经济闸门为 `INCONCLUSIVE_NOT_IDENTIFIABLE`；不得事后补造这些字段，故 101% 外生初始成本合同没有实例化**。

### 需求变更记录

- 2026-07-31：用户授权完成全部必要设计与功能、开发实现和新一轮测试；要求先使用第一轮数据回测，结果可行后再开始第二轮，并要求缺失内容与选择自动采用当前最优可辩护方案。
- 2026-07-31：将“初始仓位点位设置在当前价格 101% 以上”冻结解释为第二轮五个外生多头的模拟成本价 `ceil_to_tick(1.01 × genesis_mark)`；其余初始挂单按第一轮相对入场价比例迁移，避免把该要求误实现为会立即成交的高价买单。
- 2026-07-31：C1.0 权威 manifest 和 portable schema/registry bundle 已首次冻结并通过确定性双物化；C1.1 三个互斥 role-skill 源包已生成并完成结构及冷启动边界校验。开始四层 V2 E0 运行时实现；以上结果仅证明合同/实现边界，不证明市场预测或收益能力。
- 2026-07-31：canonical 合同扩展后，第一轮完整比较臂由 A–G 更新为 A–I；第二轮绩效比较固定为完整 I 对冻结 A。修订前 `118` 仅保留为历史 schema 基线计数，C1.0 验收改为 canonical identity set 与全部 registry/tree 的集合及字节一致性，避免为维持旧数量而删除必要理论对象。
- 2026-07-31：完成 C1.1 用户级精确安装、12 个内核 resolution、四层 E0 核心、32 场景、Agent 拓扑比较器、只读第一轮评估器与 write-once 中文报告；全项目 1115 项测试通过。
- 2026-07-31：第一轮最终裁决冻结为 `INCONCLUSIVE_NO_ADVANCE`。A 组可精确识别，总净盈亏 `-70.46915232 USDT`；SNDK 持有仅作为敏感性上界，不记作实际亏损。B–I 和三种 Agent 拓扑缺少合法事前输入，保持 UNKNOWN/回退强单 Agent；第二轮及 101% 初始成本实验未创建。

## 十四、未见 V2 完整采集、Agent 配对与正式 E0 实验

### 用户最终需要的交付结果

- 沿上一轮推荐路径持续推进，直到取得一套新的、未用于调整 V2 规则的点时数据集，并实际运行正式 E0 实验；
- 对每个决策时点保存完整 `StrategicEpisodeState`、上一 accepted head、Proposer 候选、Challenger 质疑、确定性复算、可行集合、Selector 选择、治理收据与组合结果；
- 完成至少 32 组 `SINGLE_STRONG` 与三角色集群的同输入、同模型、同推理参数、同总 token/调用预算配对会话；
- 冻结数据质量、拓扑比较、行为、收益风险和复现性结果，给出机器闸门结论；结论可以是 PASS、FAIL 或 INCONCLUSIVE，不为取得通过而修改冻结规则。

### 验收标准

1. 新实验在任何生成式角色看到输入前冻结实验合同、市场集合、时间窗口、采样规则、模型身份、参数、总调用/token 预算、评分器、成本政策、初始账户与终止条件；
2. 原始来源必须是无需私有账户的正规一手公开接口或项目内已验证不可变来源；每条记录保存 `observed_at / available_at / decision_at / source / request identity / raw digest`，并满足 `available_at <= decision_at`；
3. 数据集必须通过完整性、唯一性、时间连续性、数值合法性、跨时间尺度一致性、未来数据泄漏、来源谱系与冻结摘要检查；未知或接口缺口保留为 typed UNKNOWN，不补零、不用后续数据修补当时状态；
4. 决策样本至少 32 个，并按预注册规则从冻结窗口产生，不依据结果挑选上涨、下跌或最有利样本；同一 paired session 的两种拓扑接收逐字节相同的角色可见市场输入；
5. `SINGLE_STRONG` 与 `CLUSTER_POST_PROPOSAL` 的模型身份和推理参数相同；比较使用相同总调用/token 上限。若 API 或本地运行环境无法证明模型/预算相等，则不得把结果记为正式 paired evidence；
6. 每个生成式输出必须保存原始响应、模型/运行环境身份、输入摘要、输出摘要、耗用预算、错误与重试；自然语言不得直接成为事实、数值、权限或 accepted state；
7. 所有候选必须经确定性 schema、PIT、风险、权限、状态连续性和 E0 执行禁止门；唯一 UnitOfWork 只消费精确 artifact ID/digest；
8. 实验必须分别报告动态候选覆盖、独立缺陷发现、可行动作质量、硬约束错误、状态连续性错误、可复现差异、成本/延迟、净收益、最大回撤、机会捕获与相对冻结基准；不得用语言质量替代决策质量；
9. 32 对完成后才能作拓扑选择；缺少对、失败会话或不等预算必须显式计入，不得静默删除。默认选择规则保持 `INCONCLUSIVE_USE_SINGLE_AGENT`，只有预注册证据门通过才切换集群；
10. 正式 E0 实验必须使用全新 run ID、write-once 根目录、manifest、authority snapshot、dataset manifest 和 artifact index；两次确定性评估必须产生相同摘要；
11. 第二轮 101% 初始外生成本只有在本次实验合同明确包含第二轮账户路径且前置数据/行为闸门通过时才实例化；否则继续保持未创建，不能为了“进入实验”绕过门；
12. 本授权仅覆盖公开数据采集、生成式角色离线调用、E0 反事实组合计算和本地报告；不恢复 automation-2，不连接私有账户，不发送 paper/live/真实订单。

### 当前范围与明确不做

- 复用已冻结的 Theory Agent V2 合同、四层核心、三角色 skills、32 场景和拓扑评估器；只增加本次实验必需的数据冻结、生成式配对运行、质量门、实验编排和报告；
- 新数据窗口不得用于改写已经冻结的 V2 规则、风险阈值或评分门；若发现理论缺陷，先冻结当前实验原始结果，再另立版本；
- 不把合成响应、mock Agent、固定 fixture 或同一输出复制两份计作 32 组正式 Agent 配对证据；
- 不因用户要求“持续”而等待真实 72 小时；优先使用新冻结、逐时隐藏未来数据的离线点时窗口完成正式 E0 实验。若正规数据或同模型调用能力确实不可获得，则保留阻断证据，不伪造实验完成；
- 不把实验运行等同于策略通过、预测有效、盈利证明、模拟盘授权或实盘授权。

### 当前主要任务与状态

- 新实验需求、权限与非后见边界：**已冻结**；
- 新鲜 PIT 数据采集、冻结与数据质量门：**已完成第一份历史反事实 bundle；质量门 PASS，但其历史决策时同步输入状态保持 UNKNOWN**；
- 正式生成 transport 预检：**原 `CODEX_EXEC_CHATGPT_LOGIN` v1.0 运行保持 NO-GO，原因是 JSONL 不提供有效服务模型证明且误用 `token_budget`；不得作为正式证据。app-server adapter 已作为可选技术资产完成专用验证，但按用户最新决定，不再作为原生 Codex 集群实验的阻断前置或主线**；
- 原生 Codex 集群启动与跨窗口恢复包：**已完成。总控 skill=`run-theory-agent-e0-experiment` 、根 `AGENTS.md` 入口、manifest/checkpoint/event 链和 handoff 均已实际使用。唯一权威 practical run 为 `native-codex-e0-btcusdt-20260801T043054Z`，manifest digest=`d1bb654f4a4dfa4a64eb2aeac2c903d56ca5cbcd0d4cded7a53aa9fdcd0495c2`，transport=`CLEAN_SINGLE_TURN_FORK_V1`。旧 T110012Z/T111022Z/T112457Z 继续排除**；
- 32 组等条件 Agent 拓扑配对运行与 write-once 归档：**已完成。096..127 连续 32/32 组、192 份 schema-valid 输出和 32 个 digest-chained event 已归档；每组都在 record 后 verify，终态为 `EXPERIMENT_COMPLETE_PRACTICAL / completed=32 / next_sample=null`，context integrity 与 event chain 均 PASS**；
- 正式 practical E0 实验、确定性评估与报告：**已完成。result digest=`b2fa08eb9dac647c6949c8c405a6ecb2eae55a7e654ed286fb8a7239c8b2d28d`，冻结结论=`PRACTICAL_CLUSTER_PREFERRED`。集群/单 Agent 平均挑战覆盖率为 `0.984375 / 0.6354167`，综合分为 `0.9895833 / 0.8706597`，硬错误均为 0。但两臂动作分布与逐样本选择完全相同，一小时诊断收益/成本/路径捕获也相同；故只支持“集群提高审查覆盖”，不支持“已改善动态交易行为或收益”**；
- 第二轮 101% 外生成本实验：**未授权、未实例化；本次 practical 偏好不自动授予创建或运行权限**。

### 需求变更记录

- 2026-07-31：用户明确要求持续按照推荐路径推进直到进行实验；解释为授权新的公开数据采集、同条件生成式 Agent 配对和正式 E0 离线实验，不扩展为 automation、paper/live 或真实交易权限。
- 2026-07-31：首轮正式 transport 预检在任何生成式角色读取市场输入前失败关闭。冻结修复范围仅限 transport 权威：改用 Codex app-server 返回的 effective model/provider/reasoning、禁用 provider fallback、监控 reroute，并使用 `rollout_budget` 的 1:1 input/output 加权耗尽门；不得改样本、评分、账户、终止、理论或结果门。修订合同与重绑数据必须另建 write-once 版本并保留旧 NO-GO 证据。
- 2026-07-31：用户决定不再围绕自建 Agent 模型调用 transport 继续钻取；实际集群调用改由用户新开 Codex 窗口，让总控读取项目 `AGENTS.md`、职责 skills 与冻结状态后原生创建子 Agent。主线新增可恢复长期状态库、精确 handoff 与冷启动验收；app-server adapter 保留为可选资产，不得成为新窗口实验的强制依赖。若原生运行无法机器证明等模型/等预算，则结果必须标记为 `PRACTICAL_CODEX_CLUSTER_EXPERIMENT`，不得冒充原合同定义的严格 transport-attested paired evidence。
- 2026-07-31：原生集群实验包完成：新增总控 skill、跨窗口恢复协议、32 上下文 manifest、digest-chained checkpoint/event 工具与 handoff；合成 32 轮状态工具自测通过但不计作市场实验。实际 Agent 输出仍为 0，等待用户在新窗口以总控 skill 启动。
- 2026-07-31：首个原生 Agent 调用前发现 practical manifest 未记录统一模型和推理档位；不修改旧 manifest，新建 `...T111022Z` 并事前冻结 `gpt-5.6-sol / medium / 每臂3轮`。旧 `...T110012Z` 保留为零输出的 pre-call superseded run，不进入样本分母。
- 2026-07-31：用户明确指定新的合规运行 `native-codex-e0-btcusdt-20260731T112457Z`（manifest digest=`70144e3f597fca992c60bc6ccfcfc4afb07cb41ca24eea53a0edcc80ead874ff`）为本次唯一权威，要求从 `next_sample=96 / completed=0` 连续完成 96..127 的 32 组原生配对样本后执行 deterministic evaluate 与 verify。每样本严格使用同一 canonical context bytes；总控为唯一 writer；保持 `PRACTICAL_CODEX_CLUSTER_EXPERIMENT / E0_OFFLINE_COUNTERFACTUAL / NONE_E0`，不恢复 automation，不连接 paper/live/真实账户。
- 2026-07-31：新 run 初始 `verify` 通过（context integrity 与 event chain 均 PASS），但当前 Agent 树的唯一额外槽位被只读样本编排器占用后，其创建 fresh role worker 返回 `collab spawn failed: agent thread limit reached`；中断已完成/旧分支未从树中释放。为避免违反“worker 无继承、不得读文件、context bytes 必须由 controller 直接内嵌”的冻结规则，本轮未降级为复用旧 worker、worker 自读文件或同一 worker 模拟多角色；sample 096 保持 0/6、未 record。
- 2026-07-31：用户指定 `native-codex-e0-btcusdt-20260731T112457Z` 为唯一权威实际 run，并在新的原生总控窗口恢复。总控已在开始采样前完成 root `AGENTS.md`、项目 skill/职责合同、协议、恢复合同、manifest/checkpoint 的读取；`verify` 返回 context integrity 与 event chain 均为 PASS，严格从 096 开始，不读取或复用 T110012Z/T111022Z 的任何 worker 输出。
- 2026-08-01：用户要求从已提交的干净版本继续原生 Codex 集群 E0 实验，并持续观察、核验其是否完成 32 组配对样本、确定性评估与最终 verify。恢复不授权修改理论、样本、阈值或评分标准，也不授权 automation、paper/live 或真实账户连接。
- 2026-08-01：原生恢复连续验证了三种输入方式的边界：单条手工内嵌未完整，空启动后分段投递和首段随启动再续送都因 worker 在 `CONTEXT_END` 前结束而失败，并且 app 层向 multi-agent v2 子 Agent 直接输入返回 `direct app-server input is not allowed for multi-agent v2 sub-agents`。所有诊断 worker 均作废，无正式工件。随后的干净单轮继承诊断成功传递完整 096 上下文并返回 `PROPOSAL / SELF_REVIEW / SELECTION`，但明确不计入样本。据此授权范围内的最小工程调整是新建事前冻结的 practical run，只将 transport 改为 `CLEAN_SINGLE_TURN_FORK_V1`，不改市场输入、理论、输出 schema、评分或权限。
- 2026-08-01：新 run 从 096 至 127 严格连续完成，每一组都在六对象验证后 write-once record 并立即 verify；最终 32/32 收集、deterministic evaluate 和终态 verify 全部完成。冻结门给出 `PRACTICAL_CLUSTER_PREFERRED`，原因是 blind Challenger 显著提高挑战类别覆盖；但两臂 32 次动作与经济诊断完全相同，因此目标评价为“工程与审查目标达成，动态交易改善未证明”。
- 2026-08-01：最终验证中，与本次 transport、skill 和状态文档直接相关的 15 项测试全部通过；全项目 1164 项测试中 1162 项通过，另 2 项是冻结历史 R2 客户端将旧 HEAD `7ca3fc4...` 硬编码为 workspace identity 而产生的既存漂移错误。本次未修改该冻结历史客户端，也不把全项目测试报告为全绿。
- 2026-07-31：用户要求先清理并提交当前工作区；新的原生总控在任何 worker 启动前停止。权威 run 保持 `completed=0 / next_sample=96 / READY_FOR_NATIVE_CODEX`，无半样本、无 event、无 evaluation，后续只能按 handoff 从 096 恢复。

## 十五、动作可区分的原生 Agent 集群实验

### 用户最终需要的交付结果

- 在不修改上一轮 E0 理论、样本、输出、评分或结果的前提下，设计并运行一轮独立的动作可区分实验，判断三角色集群增加的反证覆盖能否转化为更忠实的持仓、分段加减仓、核心保留、退出和重入选择；
- 从金融学、组合风险、市场路径分析、交易执行、实验设计、软件工程和 Agent 工程视角冻结完整协议，避免把“更大胆”、更高换手或事后收益误当作能力提升；
- 将可量化的账户风险、组合最坏损失、增量风险收益、交易成本、机会成本、状态连续性和动作可行性留给确定性内核；将难以完全固定化的路径竞争、证据解释和可行集合内选择交给 Agent；
- 只有在合同、样本、指标、停止条件和 evidence label 全部事前冻结后才允许第一次正式角色调用；实验结束后提交不可覆盖结果和证据索引。

### 验收标准

1. 上一轮权威 run `native-codex-e0-btcusdt-20260801T043054Z` 保持不可变；新实验使用新的 run ID、manifest、checkpoint、事件链、输出目录和结果 schema，不复用或改写既有 worker 输出；
2. 旧 E0A 只使用上一份冻结 BTCUSDT 数据集中事前指定的 `128..159` 点时窗口；修正版 E0B 必须另用尚未被任何正式角色调用的连续 `160..191` 点时窗口。两版都必须在读取各自时点的未来 outcome 前冻结全部样本、状态 profile、分配函数、动作字典、计算公式、评分和终止规则，不按后续涨跌选择或删除时点；
3. 每个 arm 在同一 case 接收相同的 canonical market bytes、counterfactual state、风险预算、监督状态、候选动作和确定性前瞻情景算术；未来价格、未来成交结果和另一 arm 输出不得进入角色输入；
4. 样本状态必须按与 outcome 无关的确定性分配覆盖：空仓且 thesis 有效、CORE 持有、CORE+TACTICAL、战术退出后待重入、硬失效、风险预算受压、目标后延续审查和无人值守保护等必要决策状态；每种 profile 的理论目的、可行动作和禁止动作须事前登记；
5. 候选动作至少覆盖 `WAIT / HOLD_CORE / OPEN_CORE / ADD_CONFIRMATION / ADD_TREND / REDUCE_TACTICAL / PARTIAL_TAKE_PROFIT / EXIT_WITH_REENTRY / REENTER_CORE / INVALIDATE_AND_EXIT`。动作出现频次、可行集合大小和 profile 覆盖须在首次 Agent 调用前通过机器预检；
6. 确定性内核必须逐候选计算或明确 UNKNOWN：当前敞口、已用/剩余风险、所有 lot 同时失败的组合损失、增量最坏损失、成本和滑点压力、目标空间、净盈亏比、盈亏平衡概率门槛、监督可执行性以及退出后的重入义务。未校准路径不得伪装成精确胜率或 EV；
7. Agent 只能从硬约束后的 feasible set 选择，不能修改事实、风险上限、state head、失效条件、可用时间、计算结果或交易权限；确定性系统不能用“谨慎”或默认空仓替代硬约束，也不能静默删除可行的持有、加仓或重入候选；
8. 角色保持 Single-Strong 与 blind Proposer/Challenger/Selector 两臂等输入、等配置和每臂三语义轮；原生服务模型和精确 token 若仍无法机器证明相等，证据继续标为 practical，不得升级为严格 transport-attested；
9. 评价必须分离四类指标：硬安全/状态忠实性、动作可区分与状态响应、Agent 审查与干预价值、后验多 horizon 经济诊断。实际亏损、未实现损益、成本、基准持有收益和相对机会损失保持不同字段；后验收益不得反写理论忠实性评分；
10. topology 晋级不得只看语言覆盖。只有集群相对单 Agent 在零新增硬错误下产生可审计的动作差异，并且有益干预多于有害干预、理论忠实性提高且经济/回撤 guardrail 未恶化，才可给出 action-benefit 偏好；无动作差异必须裁决 `NO_ACTION_DISCRIMINATION`，差异证据不足必须裁决 `INCONCLUSIVE`；
11. 至少执行 manifest/schema/profile/输入字节/PIT/事件链/write-once/崩溃恢复/确定性复算/未来数据隔离/非法动作拒绝测试；任何正式样本必须先使六个语义对象全部通过，再写入可重复核对的 write-once 输出与单一 event，最后以原子 checkpoint 更新推进一个 index。不得把多文件落盘错误表述为单文件系统事务原子性；中途崩溃只能用完全相同的对象恢复，冲突字节必须失败关闭；
12. 最终报告必须明确区分：功能合同证明、Agent 拓扑差异、一次冻结历史诊断、预测有效性、成本后稳定盈利、paper 权限和 live 权限。前三者不得自动晋级后三者；
13. 本轮授权仅覆盖新动作可区分实验的设计、离线实现、冻结样本、原生角色调用和确定性评估；不创建 101% 外生成本账户、不恢复或新建 automation、不连接 paper/live/真实账户、不发送订单。
14. E0B 的 transport 预检必须在零正式角色输出的独立临时 run 上进行；配置须记录 sample/context/packet digest、canonical byte length、physical SHA-256、choice count、child task 和无工具状态。正式 prepare 必须从当前冻结 context 与当前角色包构造代码重新生成同一 packet 并逐项核对，任何代码、schema、common rules 或 packet 字节漂移均 fail closed，预检输出不得作为正式角色输出复用。

### 当前范围与明确不做

- 复用当前 Core v2.1、Theory Agent V2 四层架构、现有冻结数据与确定性风险/回放组件，通过新版本合同和兼容 adapter 扩展；不把 legacy v1 或上一轮原生状态脚本扩张成新的业务核心；
- 合成或 counterfactual state profile 只用于动作语义、状态治理和 Agent 选择鉴别，不作为市场预测样本；市场经济诊断只使用对应决策时点之后、角色不可见的冻结 bar；
- 不依据 SNDK/HYPE 已知结果选择核心比例、加仓比例、阈值或成功定义；固定比例若为兼容现有 E0 回放而保留，必须标为实验 profile 而非通用理论常数；
- 不用换手率、加仓次数、持仓时间或单次后验盈利单独奖励 Agent；合理的 HOLD、WAIT、REDUCE、EXIT 与 ADD 具有同等合法地位；
- 不声称能够做到“确保不会出现任何问题”；采用失败关闭、可证伪假说、guardrail 和证据等级管理残余风险。

### 当前主要任务与状态

- 新实验授权、范围和不可后见边界：**已冻结**；
- 上一轮无动作差异的结构性原因审查：**已完成。根因是单一参考状态链、缺少逐候选路径/风险/监督/重入比较对象、Selector 无冻结决策目标，以及旧确定性 selector 与有界 Agent 自主选择的职责冲突；该结论不回写旧 run**；
- 四层目标设计、状态 profile、动作合同、指标与晋级门：**已完成并在首个正式 role call 前冻结于 `THEORY_AGENT_V2_ACTION_DISCRIMINATION_EXPERIMENT_v0_1.md`；不制造概率或 EV，后验经济指标只作描述性诊断**；
- 新实验实现、角色 skill、恢复包与测试：**已完成。项目权威 skill 与用户级安装副本逐字节一致；正式 handoff 已绑定 run、manifest、config、schema、source dataset 与起始 checkpoint**；
- 正式原生角色调用、持续 verify、评估与裁决：**首个 run `native-codex-action-e0a-btcusdt-20260801T064710Z` 已作为缺包失败关闭且不得重试。inline successor `native-codex-action-e0a-inline-btcusdt-20260801T070500Z` 已合法记录 sample 128..130，状态为 `integrity=PASS / completed=3 / next=131 / outputs=18 / terminal=false`；sample 131 的 Single、Proposer、blind Challenger 已返回但未记录，唯一正式 Selector 在创建前被 native scheduler 以 `agent thread limit reached` 拒绝，因此该 run 已按协议硬停止、未重试、未 evaluate、未读取 future outcome**；
- 32-context 冻结输入内效度复核：**已完成且旧 E0A 判定合同不合格。在未读取 128..159 future outcome 的条件下确认：24 个持仓 context 中 20 个把逐 lot 注册止损损益错误呈现为统一 `FAILURE_TO_STOP.terminal_reference`；trailing 的触发/距离/同 K 线顺序未向 Agent 暴露；`PARTIAL_TAKE_PROFIT` 实际对每个 lot 减半但动作说明未声明且不保证获利；`EXIT_WITH_REENTRY` 只执行退出腿；一次性 counterfactual profile 不能证明跨轮重入履约；终局晋级只使用 1h 净值；preoutcome quality 对 cluster 的专职 Challenger 存在结构性加分。旧 3/32 run 保持不可变、不得 evaluate**；
- 修正版 E0B 合同、未见窗口与正式恢复点：**已完成调用前实现、独立 GO 复核和 write-once 正式冻结。唯一权威 run=`native-codex-action-e0b-btcusdt-20260801T102202Z`，起始状态为 `PASS / completed=0 / next=160 / outputs=0 / terminal=false`；32 个 `160..191` context 已冻结，角色输出、event 与 evaluation 均为 0，prepare 明确记录 `outcome_access_during_prepare=false`。manifest self digest=`68edb61182fc1a5763b04c9856553b194a366ead4ebca585e40298c988d273f4`，checkpoint self digest=`a382aafbcd3e663939437a3fa5d4e6bf5de83ae9b07ca1e5da58f32f8a15cd62`，source receipt self digest=`cdd4cba984d86f2a0e70bac560c5bcfa41c71df06d8290900cbe6b5a78223423`，config self digest=`6729f1c3626fe9a155625f3a5ad11e428815274128bbc92588428122f05c7425`；精确恢复协议已写入 `agent-cluster/experiments/native-codex-action-discrimination-e0b-20260801/HANDOFF.md`。逐 lot 失败端点、动作状态转换、review/reentry 义务、完整收益账本、同 K 线 trail 顺序、多 horizon 裁决、拓扑对称评分、validator 交叉字段、run-wide task 唯一性和当前代码生成 packet 与 transport 预检均已机器闭环。全新 preflight child=`/root/e0b_transport_preflight_v2` 永久保留且不得作为正式输出；该窗口仍来自同一冻结 BTCUSDT bundle，只能支持一次冻结历史的动作选择诊断，不能作为独立市场泛化样本**；
- E0B 权威正式运行：**已失败关闭且不得恢复。当前权威状态经实时 status 复核为 `integrity=PASS / completed=3 / next=163 / outputs=18 / terminal=false / event_head=47171b3e537c273ef313dc5bdddc3caa0a5d2e01acbd7829c630e392ee81ff4e`；sample 160..162 已形成事件，sample 163 无正式输出或 event，未读取 outcome、未 evaluate。原始 Codex 会话显示 sample 163 child 实际已创建并完成 schema-valid Single-Strong JSON，但总控在创建前后由 `217199/258400` tokens 上升至 `241509/258400` 并随即 compact；由于冻结恢复合同没有“child 已完成、总控未接收/未生成收据”的恢复分支，这些字节只能作为工程诊断，不能补录为正式输出**；
- E0B 失败根因与架构裁决：**已完成并保留在本需求记录、冻结 run/checkpoint 和会话证据中。P0 根因是 chat-native full-packet transport 与长生命周期总控不匹配：preflight 只验证 sample160 两动作 `20698` bytes，而 sample163 Single packet 为全窗口最大 `43325` bytes；13 次 spawn initial message 已累计 `593432` characters，原始 packet 与响应反复回灌总控。外部 258400-token 上限是已知约束，预检非最坏负载、固定每样本四 child 和恢复合同缺口使其升级为确定性故障。理论、金融内核和 Agent 推理未被本事故否定；完整集群已降为非主线历史实验，旧 E0B 保持只读**；
- 项目核心目标重载与范围纠偏：**已完成并固化于 `PROJECT_CORE_GOAL_RELOAD_2026-08-02.md`。裁决确认主线是“点时市场数据 → 多尺度竞争路径 → 路径风险收益 → 持久战略与仓位动作 → 未见连续结果”，Agent/transport 只属辅助层；当前最优下一步是新的未见连续窗口上的最小 Single-Strong 动态基线与静态 V1/确定性持续政策对照，不再继续 E0B 或扩张集群工程。本项未修改 Core、冻结实验、历史输出或交易权限**；
- 分析自由度、积极实验与最小实现原则：**已完成目标与最小设计固化，见 `PROJECT_CORE_GOAL_RELOAD_2026-08-02.md` §3.1、§3.5、§13。采用“硬边界 / 软边界 / 自由实验区”三档治理：硬边界仅覆盖前视/数据真实性、账户极端风险、杠杆/保证金、保护/停机和交易授权；Bollinger、VWAP 等辅助指标通过一个通用 `FeatureRequest / FeatureObservation` 接口按需计算，不逐项固化成信号、模块或 Agent。默认拓扑为单 Strategy Agent + 持久状态 + 通用特征计算 + 确定性风险内核；无具体 veto 的长期 ABSTAIN、静默压缩可行集合或已有观测未透传均列为功能失败。本项只完成需求和设计纠偏，尚未修改指标运行代码或启动实验**；
- 工作区清理与下一窗口研究交接：**已完成。冻结理论、E0/E0B run、事故证据与历史结果均未删除或改写；无关的 macOS 清理记录和未采纳、与核心入口重复的运行时设计草稿已移入 macOS 废纸篓，六个 `.DS_Store` 已删除。`README.md` 和 2026-08-01 状态快照已增加新的权威读取入口，新增 `NEXT_WINDOW_RESEARCH_AGENT_PROMPT.md`，并保留 `PROJECT_CORE_GOAL_RELOAD_2026-08-02.md` 作为研究优先级入口。引用存在性、24 项定向测试和 `git diff --check` 均通过；以本项定向提交和干净 Git 工作区完成交接**；
- automation、paper/live 和 101% 外生成本账户：**不在授权范围**。

### 需求变更记录

- 2026-08-01：用户确认执行上一轮报告推荐的动作可区分实验，要求从金融、工程、市场分析—交易和 Agent 工程等视角进行全面、严谨且可行的推论与设计。该授权解释为独立离线反事实实验，不改变上一轮证据，不扩展为任何执行权限。
- 2026-08-01：正式调用前预检发现并事前修正三项设计冲突：费用会使原 1.5R target 无法通过 1.5 净 RR 门、CORE+TACTICAL 的 marked gross 会机械删除 ADD_TREND、REDUCE 与 PARTIAL 在压力 profile 中经济实质重合；修订后 11 个动作均在至少一个 context 中真实可选。future reader 另改为必须验证 32-event terminal chain 才能构造，所有修订均发生在零正式 role output 状态。
- 2026-08-01：首个正式 run 的 clean Single/Proposer/Challenger 均因 fork 未传递上一工具输出中的 packet 而返回缺包错误。总控按冻结停止条件原地停机，未 record、未读 outcome，也未把失败追认为 diagnostic。随后在不写正式 run 的独立传输诊断中，`fork_turns=none` child 通过 initial message 直接内联完整 15,402-byte sample-128 proposal packet，回传 packet/context/sample/choice-count 四个锚点均精确相等且无截断。需求新增 v1.1 transport-only successor：必须把完整 canonical packet 直接内联到 clean child 首条消息；不得改变 context、数据、金融公式、评分或失败 run。
- 2026-08-01：inline successor 在 sample 128..130 形成 3 个原子事件；sample 129 首次产生 Single=`HOLD_CORE_TRAIL`、Cluster=`HOLD_CORE` 的真实动作分歧，原因是 blind Challenger 识别 trailing 与 stop 端点表达不足。sample 131 正式 Selector 创建前发生 scheduler thread-limit 拒绝，无 child/task ID、无 packet 投递、无 Selector 输出；run 依冻结停止并保持 `3/32`。该失败属于 Agent 编排/定时资源治理，不得误判为理论或市场失败。
- 2026-08-01：用户要求严谨推进且避免只修形式问题。由于多个 blind Challenger 在不知道 future outcome 的条件下重复识别金融路径矩阵与动作状态转换缺口，主线先转入全 32 context 静态内效度审计；只有证明缺口不影响判定，或另建事前冻结的修正版实验，才允许下一次正式市场角色调用。旧 run、输出、评分和后验数据保持不可变。
- 2026-08-01：全 32 context 静态审计裁决旧 E0A 不具备继续 evaluate 的内部效度。新增 E0B 修复范围严格限定为金融与评价合同，不对旧输出打补丁：使用 160..191；`FAILURE_TO_STOP` 改为逐 lot 注册止损端点；显式冻结 trail/partial/exit/reentry 转换；收益账本分离事前嵌入盈亏、决策期增量盈亏、成本和机会损失；trail 采用 `OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR`；终局使用 1/4/8/24 全向量支配与回撤 guardrail，不允许 1h 单独晋级；专职自审与 blind challenge 对称计分，challenge coverage 仅作诊断。完成合同、32-context 静态测试与新 handoff 冻结前不得调用正式角色。
- 2026-08-01：E0B 调用前独立复核确认原六类 P0 阻断已关闭，并新增两个必须先修的 P1：任何 `agent_task_id` 必须在完整 run 内全局唯一，禁止跨样本复用 clean child；硬安全错误统一为 event/result 前 fail-stop，不保留不可达的 `FAIL_HARD_SAFETY` 终局。新增 E0B 专用总控 skill 及其闭集测试，以上修复和回归完成前继续保持零正式 role output。
- 2026-08-01：同一复核以 sample160 纯 decision context 复现三项 validator 漏洞：可编造 hard-falsifier ref、可重复前三条竞争路径、Selector 可选择被自身标为 `AVOID` 的动作；WAIT 的下一小时复核义务也未进入通用 transition object。E0B 在首次正式调用前新增 hard-ref allowlist、前三路径互异、冻结 ordinal 排序一致性、显式 review obligation、预检 child task 永久保留不可复用，以及 agent/role config 全字段绑定。所有变化仍属 pre-outcome 合同修复，不得读取 future outcome。
- 2026-08-01：当前 E0B 定向、E0A 非结果兼容与 skill 闭集共 37 项通过；全项目 1192 项中 1190 项通过，另 2 项仍是冻结 R2 客户端对旧 workspace identity 的既存漂移错误，本次没有新增失败。旧 E0A inline run 仍为 `PASS / 3/32 / next=131`。E0B skill 项目源与 `/Users/wt/.codex/skills/run-theory-agent-action-discrimination-e0b-experiment` 五个文件逐字节一致。独立审查在未读 future 的条件下给出 GO，只授权正式 freeze/prepare，不等于授权 outcome、paper/live 或任何交易执行。
- 2026-08-01：按 GO 边界正式生成 E0B write-once run `native-codex-action-e0b-btcusdt-20260801T102202Z`，并在任何正式角色调用前冻结 32 个 context、manifest、config、schema、source receipt、checkpoint 与跨窗口 handoff。初始 checkpoint 为 `0/32`、下一样本 `160`、角色输出/event/evaluation 均为 0，prepare 未访问 outcome；当前窗口不启动正式角色，后续只允许新窗口通过 E0B 总控 skill 从该精确恢复点串行推进。
- 2026-08-01：用户授权在新窗口严格恢复唯一权威 E0B run `native-codex-action-e0b-btcusdt-20260801T102202Z`，要求从 checkpoint 的精确 `next_sample_index` 开始，每次只完成、记录并验证一个 paired sample；任何 packet、schema、工具使用、调度或状态异常立即停止。`32/32` 终态前不得读取 outcome，也不得创建或恢复 automation、paper/live、账户、订单、凭据或资金动作。
- 2026-08-01：sample 160 已形成首个权威事件；sample 161 在六个正式角色响应已返回、但尚未构造收据和调用 `record` 时，因为控制器临时预校验脚本误导入不存在的 `sha256_digest` 而按停止条件中断。用户随后明确授权恢复并要求持续完善、测试直到正常可用；该授权仍受 E0B 冻结与恢复合同约束：只复用 sample 161 的原始字节，不修补、不替换、不重跑正式角色，先完成六对象、packet、收据和事件链复核，再继续逐样本推进。所谓正常可用仅指离线实验达到 `32/32 / 192 outputs / terminal=true`、首次 evaluate 与最终 verify 全部通过，不扩展为预测、盈利、paper/live 或交易权限。
- 2026-08-02：用户报告 E0B 已记录 sample 160..162，sample 163 的正式 Single-Strong 创建因完整 canonical packet 触发模型上下文截断且无可验证创建确认而失败关闭，并要求停止继续围绕同一集群 transport 反复调试。需求转为先裁决持续失败的主因和复杂度收益，再选择最小可用动态架构；当前权威 run 保持只读，禁止重试、缩包续跑或提前 evaluate。
- 2026-08-02：只读核验修正了表面故障定位：parent session 留有 sample163 task start 与 task-name 创建确认，child session 也保存了完整输出；三个 Single-Strong 对象通过当前语义 validator，选择 `HOLD_CORE_TRAIL`。实际失败点是总控上下文耗尽后的结果回收/恢复，而不是 worker 无法读取 43KB packet。已决定不再新建 chat-native full-packet successor；下一实施阶段只允许复用现有 domain 内核和 Codex exec/内容存储基础，先完成最大 payload 预检与无累积 soak，再在新未见窗口运行 Single-Strong 动态基线。
- 2026-08-02：用户要求停止以当前聊天摘要延续项目理解，重新加载权威核心目标，并明确检查近期是否沉迷 Agent 工程而忽略市场分析、动态持仓和风险收益决策主线。输出必须把理论研究、决策政策、工程基础设施和验证实验重新排序；Agent/transport 只能作为辅助能力，不能继续成为项目成功标准。
- 2026-08-02：完成项目核心目标重载并新增 `PROJECT_CORE_GOAL_RELOAD_2026-08-02.md`。明确 Core v2.1 窄 V1、动态路径上位方法与持续战略政策 challenger 的边界；把本轮主问题重置为同 PIT、风险和成本条件下的连续顺序政策比较，冻结停止继续扩张 chat-native 集群 transport。该文档是项目优先级入口，不是 Core 理论改版或实验授权。
- 2026-08-02：用户进一步明确“分析自由、风险硬边界、积极实验、最小成本最高效率”原则。新增要求为：布林带、VWAP 等可复算观测指标属于 Agent 可自由调用的辅助证据，不应逐项硬编码为交易规则；分析/假说/策略空间采用开放但可审计的软约束，只有前视、伪造数据、账户极端风险、交易权限和执行安全为硬约束；默认架构收敛为单 Strategy Agent + 持久状态 + 通用特征计算 + 确定性风险内核，避免继续扩张集群、协议与指标专用模块。
- 2026-08-02：用户要求在转入新窗口前清理当前项目工作区，删除无用、错误或误放且可能干扰后续研究的文件，并提供一份能够持续遵守核心目标、优先复用现有能力、阻止低性价比工程扩张的 Agent 总控提示词。只读核明后，将 `requirements/2026-08-01-macos-storage-cleanup.md` 与 `THEORY_AGENT_V2_MINIMAL_DYNAMIC_RUNTIME_DESIGN_v0_1.md` 可恢复地移入 macOS 废纸篓，删除六个 `.DS_Store`；冻结理论、历史事故证据、实验状态和收据保持不变。新的研究入口与总控提示词完成版本化后作为下一窗口唯一主线路由。

## 十六、最小连续市场研究与原始离线结果

### 用户最终需要的交付结果

- 先完成现有市场数据、指标、战略状态、风险/账本和 Agent 输入的只读现实映射，并在一页内裁决阻塞 P0 的最小差距；
- 优先透传已有 Bollinger 与 recent-window VWAP，只在真实需要时使用一个通用 `FeatureRequest / FeatureObservation` 扩展口，不建设指标平台；
- 复用现有 V2 状态、风险和账本组件，形成一个单 Strategy Agent 的持久状态闭环，可选 Critic 默认关闭；
- 在新的连续未见窗口读取任何 outcome 前冻结输入、三条政策、风险、成本、评价和停止条件；
- 同条件比较静态 V1、确定性持续政策和单 Agent 动态政策，先完成并封存从 genesis 到 terminal 的原始离线结果，再审计和提出改版。

### 验收标准

1. 现实映射明确区分“已计算且 Agent 可见 / 已计算但未透传 / 可合法接入 / 当前不可得”，并给出真实调用链；
2. 每轮只使用 `available_at <= decision_at` 的输入并读取上一 accepted state；状态、lot 角色、风险预算、review/reentry 义务不得静默丢失；
3. 三条政策使用相同 PIT 数据、风险、成本、监督条件和连续顺序窗口；
4. 每个动作可追溯到竞争路径、证据、硬风险、成本和真实可行集合；`WAIT/ABSTAIN` 必须有具体数据缺口、风险 veto 或相对效用理由；
5. 分开记录已实现/未实现盈亏、费用、funding `UNKNOWN`、基准持有收益和机会差，并报告多 horizon、最大回撤、尾部、空仓持续、重入延迟、加仓利用和路径捕获；
6. transport、聊天上下文、报告格式或通用 Agent 工程不得再成为无法产出市场原始结果的主因；
7. 原始结果可以支持、失败或不确定，但不得用工程 PASS、字段完整率或提示词长度替代市场有效性结论。

### 当前范围与明确不做

- 范围限于 `/Users/wt/Documents/agent-trade-emotion` 内现有公开/已授权离线数据、现有代码和新的未见连续窗口；优先复用，不进行全局重构；
- 不读取 future outcome，不恢复或修改 E0/E0B，不启动或创建 automation、paper/live，不访问账户、凭据、订单或资金；
- 不新增通用 Agent 集群、transport、插件平台、角色体系、指标专用模块/schema/硬阈值；
- 不用 SNDK/HYPE 已见结果选择参数，不在基线原始结果完成前修改理论、评分或验收标准；
- 若两个合理的最小方案均失败，或合法数据不可得，则停止扩张并报告根因和最短替代路径。

### 当前主要任务与状态

- 冷启动权威文件、HEAD、分支和工作树核对：**已完成**；
- 现实调用链映射与 P0 差距裁决：**已完成**。V1 的 `run_hourly_cycle` 形成“公开数据 → 测量 → 分析 → 无持久战略状态的单轮决策 → 组合提交”；Bollinger 上下轨已进入 Agent 测量，middle/bandwidth/%B 已可由同一窗口复算但未输出，recent-window VWAP 已在市场层计算但未透传；V2 已有状态 reducer、event/content store、风险预算、lot 角色、reentry 和离线组合账本，但现有决策入口固定为 Proposer/Challenger/Selector DAG，不能直接形成单 Strategy Agent 连续闭环；
- P0 差距裁决：**已完成**。真正需要解除的工程差距只有“已有观测透传 + 单一持久状态顺序循环 + outcome 终端门”，不需要新 Agent 平台、角色体系或指标模块；
- 最小能力修复：**已完成实现**。已有 Bollinger middle/bandwidth/%B 与 recent-window VWAP 已透传；新增一个通用 `FeatureRequest / FeatureObservation` 计算口；连续切片复用 V2 风险、lot、reentry、离线账本、event/content store，并将 Critic 保持关闭；
- 新未见窗口、三政策、风险/成本/评价冻结：**合同已完成，数据冻结受阻**。冻结合同固定为 `BTCUSDT / 1h / 16` 个连续决策、1/4/8/24h 结果，比较 `STATIC_V1 / DETERMINISTIC_CONTINUOUS / SINGLE_STRATEGY_AGENT`，共享风险、费用、滑点、funding 和停止条件；未因数据阻塞修改窗口、评分或验收；
- 冻结合同身份与机械验证：**已完成**。`config/theory_paper_v2.continuous_p0.v1.json` 的 canonical digest=`d46623e3cf1f5007568afaf3988549282422688812409fff5df3f7dc09d6a65f`；37 项聚焦回归通过，其中本地无网络 fixture 完整走通 16 个 cycle、48 个三臂动作、genesis/terminal 门、event/state 连续提交和 terminal 后 evaluation/artifact 物化。该验证只证明机械路径，不是市场结果；
- 连续离线运行与原始结果封存：**受阻且未达到验收**。2026-08-02 首次只读公开数据冻结在 `/fapi/v1/time` 收到 HTTP 451，collector 返回 `EVIDENCE_SOURCE_UNAVAILABLE`，失败发生在 run 目录写入前；合法第二路径仅核验 Binance 官方公开归档可用性，所需 `2026-08-01`、`2026-08-02` BTCUSDT 1h 日归档均为 HTTP 404，`2026-08` funding 月归档亦为 404，无法覆盖冻结窗口最后 24h 结果和完整 funding 成本；
- outcome 与权限边界：**保持关闭**。未读取任何 future outcome，未恢复 E0/E0B，未启动 automation、paper/live，未接触账户、凭据、订单或资金；
- 当前阻塞：**同一官方来源的数据当前不可得；API 与官方归档两条合理合法路径均不能覆盖事前冻结窗口，按停止条件不再扩张来源或修改合同**。

### 需求变更记录

- 2026-08-02：用户将项目角色明确为市场研究总控，要求以最低必要工程成本推进“现实映射 → 最小能力修复 → 单 Agent 持久闭环 → 新未见连续三政策对照 → 原始结果封存”；明确只保留前视、数据真实性、风险、执行安全和外部授权硬边界，并继续禁止 E0/E0B、automation、paper/live、账户、凭据、订单与资金动作。
- 2026-08-02：现实映射确认已有 V2 机械组件可复用，P0 仅需一个连续垂直切片；已冻结三臂同条件实验并完成实现。首次冻结未创建 run：Binance USD-M 官方公开 REST 返回 HTTP 451；唯一合法替代的官方归档当前又缺少覆盖 16 个决策最大 24h 尾部的 2026-08-01/02 1h 文件及 2026-08 funding。依事前停止条件将本轮标记为数据不可得，禁止换源、缩短窗口、把缺失 funding 当零或读取旧 outcome 来补齐。

## 十七、V1 历史诊断回测与新纸面实验

### 用户最终需要的交付结果

- 使用 V1 纸面实验已经保存的具体市场数据、每轮分析、动作、账本和实际顺序结果，对当前理论与连续政策进行已见诊断回测；
- 逐项验证当前系统是否解决 V1 已发现的固定止盈、趋势延续捕获、退出后重入、连续战略状态、动作忠实度、机会成本和成本核算问题；
- 在不改变历史数据和评价事实的前提下，主动识别当前理论、风险内核、状态转换、Agent 输入或回测模拟中的其他问题；
- 只实现能够解除已确认问题的最小修复，并在同一 V1 数据上复核，不用已见结果宣称泛化；
- 诊断回测和问题解决完成后，自主搜索并采集满足点时、来源、质量、成本和可复算要求的公开市场数据，不再固定为单一提供方；随后开展新的连续本地纸面实验，观察理论和系统在市场顺序运行中的处理情况并继续发现问题。

### 验收标准

1. V1 输入、分析、决策、成交、仓位、账本和结果的文件谱系完整，明确哪些字段是当时可得、后验结果、缺失或不可复算；
2. 诊断协议在读取并使用具体 outcome 前冻结当前代码身份、问题清单、比较政策、风险、费用、评价指标和停止条件；由于 V1 结果已见，证据标签只能是 `SEEN_V1_DIAGNOSTIC_REPLAY`；
3. 原 V1 行为与当前连续政策使用同一可复算市场序列、起始账户、成本和可行动作边界；不能重放的差异明确标记，不作伪比较；
4. 每个已知问题给出“已解决 / 未解决 / 数据不可判 / 被新问题替代”的事实裁决，并附动作、状态、盈亏、回撤、机会差或路径捕获依据；
5. 新问题必须能够定位到具体数据、理论前提、状态转换、风险 veto、Agent 输入、成本公式或模拟顺序，不以主观观感代替；
6. 只有阻塞性问题完成最小修复并通过同数据复核后，才冻结新的未见纸面窗口；新窗口不得用 V1 结果继续调参；
7. 新纸面实验从 genesis 到 terminal 连续运行，保持 `available_at <= decision_at`、上一 accepted state、lot 角色、风险预算、退出原因与重入义务，并分开报告成本后结果和机会成本；
8. 工程通过、已见回测改善和新未见市场有效性必须分开陈述；任何一层都不自动证明预测有效、稳定盈利或真实交易就绪。

### 当前范围与明确不做

- 获准读取 `.runtime/theory-paper-v1/current` 及其已保存的公开市场输入、分析、决策、账本、中文审计记录和实际顺序结果；V1 原文件只读，派生回测写入新的独立目录；
- 获准在诊断通过后自主搜索、下载和组合合规公开市场数据源；数据仍须保留来源、抓取时间、`available_at`、质量、费用和可复算记录，缺失保持 `UNKNOWN`；
- 获准开展新的本地、不可执行纸面实验；不读取私有账户，不使用凭据，不发送真实订单，不接触资金，不把本地成交模拟称为真实成交；
- E0/E0B 保持只读且不恢复；本次不使用其 future outcome 补 V1 回测；
- `automation-2` 保持暂停。用户本轮授权的是研究数据采集与本地纸面实验，不自动解释为恢复既有定时 automation；若连续运行需要定时调度，先完成手动闭环并单独确认；
- 不建设通用数据平台、Agent 集群、插件体系或新的角色架构；一个真实阻塞最多增加一个最小抽象。

### 当前主要任务与状态

- 本轮需求变更与权限边界记录：**已完成**；
- V1 运行目录、数据谱系、时间覆盖和可复算性清点：**已完成第一阶段冻结前清点**。源 run=`msta-paper-20260729T212716Z-87cc29bb`，现存 25 个六标的市场/分析快照、24 个已提交决策和 24 份中文 v2 审计记录，实际观测约 25.60 小时而非完整 72 小时；每个市场快照包含公开的 15m/1h/4h/1d/1w K 线、depth、aggTrades、OI、funding、ratio 和 premium，liquidations 缺失保持 `UNKNOWN`；
- 已知问题与冻结诊断协议：**已完成**。`config/theory_paper_v2.seen_v1_diagnostic.v1.json` 在打开逐轮动作、成交和盈亏前绑定源文件集合、当前代码身份、三臂、八项已知问题、PIT 隔离、成本、指标与停止条件；canonical digest=`186caa897597c6a853fa5165dc2700e6a60c1c60549b1e2a8265dd5ad5c52499`，证据标签固定为 `SEEN_V1_DIAGNOSTIC_REPLAY`；
- 父诊断 v1.0 与 PIT bar successor：**v1.0 已按冻结条件停止，v1.1 已冻结**。源 raw kline 保留抓取时尚未收盘的活动 bar，六标的跨周期在 15m/1h/4h/1d/1w 分别出现 1800/1800/570/270/144 次成熟修订，因此父合同过宽的 `SHARED_MARKET_BAR_REVISION` 被触发；但以较早快照 `observed_at` 过滤后，五个 timeframe 的已收盘 bar 修订均为 0，存储的 `last_closed_bar` 与重算结果不一致也均为 0。`config/theory_paper_v2.seen_v1_diagnostic.v1_1.json`（canonical digest=`edd29908d2996b51ce537fd43e5c75659ef7d890ccc23c992ab14e96fb9c3f31`）只把不可变边界修正为“首次观察时已收盘的 bar”，不修改价格方向、问题、政策、风险、成本或评价；
- V1 顺序撮合审查与候选执行边界：**已完成审查并冻结最小 successor**。V1 `process_market_bars` 每周期只消费各标的最新一根已收盘 1h bar；cycle 10→11 与 20→21 各跨过一根中间 bar，共 12 个“标的×bar”未进入保护撮合。逐 lot 复核显示，cycle 10→11 的唯一相关 SNDK 已保护 lot 在被跳过 bar 上既未触发 stop 也未触发 target，cycle 20→21 前组合已空仓，因此该缺陷没有改变本次 V1 已记录成交；但它会在其他路径漏掉保护触发。候选臂必须按 `close_time` 逐根消费所有新收盘 1h bar，并把 V1 实际基线与修正后的候选撮合差异显式记录；
- 当前连续政策在 V1 数据上的同条件重放：**执行合同、runner 和实现绑定均已冻结，可进入 prepare；候选运行仍为 0 cycle**。runner 提交=`c120b4dc17d2e02db91e09f8473e676ff3b129e7`；执行合同 canonical digest=`6c07410d8f4c5b20382d26389217a670c3c1ef25a6411fc22dac4b8d7f5bdb78`；实现绑定 `config/theory_paper_v2.seen_v1_diagnostic.v1_3.json` canonical digest=`7eb0a385541a6108279d509f02dcfd57e96ee22b5272f884273b5a94a595ce62`，锁定 runner、CLI、测试及实际复用的计算/账本/transport 文件物理摘要，并记录 freeze 前真实 V1 候选运行数为 0。新增的单一应用切片复用现有 `FeatureRequest / FeatureObservation`、市场测量、离线 lot/成交账本和 Codex 生成适配，完成逐 bar 撮合、初始状态映射、组合风险 veto、确定性优先级、组合级单 Agent、write-once cycle/state/event、terminal outcome 门和评价输出。5 项本切片合成测试及 9 项相邻连续/legacy 回归共 14 项通过；真实 V1 仅完成 25 个 context 的只读规范化与已收盘不可变复核，没有执行候选政策；
- 首次正式 prepare：**在 run 目录创建前失败关闭，候选仍为 0 cycle；单行根路径修复、入口回归和 successor 绑定均已冻结，可重新 prepare**。失败原因是 CLI 的 `PROJECT_ROOT` 比仓库根多上移一层，默认源路径错误解析为 `/Users/wt/Documents/.runtime`；修复提交=`159fbe2`，CLI 绑定路由提交=`e37ad8e37ebed7cd1e11cf0cedc1f48e317c36d6`，15 项聚焦及相邻回归通过。successor `config/theory_paper_v2.seen_v1_diagnostic.v1_4.json` canonical digest=`f523b5a481b37f968b687212837a17daef8b8112953e9f0a57c3340ed4011487`，只重绑修正后的 CLI/测试物理摘要，runner、市场输入、政策、风险、成本、评价和停止条件均未改变；
- 正式 prepare successor：**已完成，outcome 保持关闭**。run=`seen-v1-diagnostic-20260802t000000z`，manifest digest=`fb9ec20d272d9035225e115f10ffbc610b9054b1eda6e4dc0abf7204e3b78b1a`；25 个六标的 PIT context 已 write-once 冻结，V1 源树摘要 prepare 前后均为 `aba02e17eca90ab4b4ae652c485940523e6c0f0ae2f78eae485c8a5019264085`，账本/事务链有效，checkpoint 两臂均为 `0/24` 且 `recorded_v1_decisions_opened=false / recorded_v1_outcomes_opened=false`。当前 Codex transport 已登录并具有真实生成、临时会话、只读空 workspace、工具检测、usage 和硬 token limit，但 CLI 版本为 `0.146.0-alpha.9.2`、不等于旧 adapter 常量 `0.146.0-alpha.3.1` 且无 served-model attestation；本实验因此只保留 practical 单 Agent 证据，不作严格 transport-attested 声明，该差异不改变冻结模型请求、token 上限或市场评价；
- 首次正式候选运行：**已失败关闭且不得续跑、修补或重试该 run**。同一 run 的确定性连续臂已完成 `24/24` 决策与 terminal，Agent 臂在 cycle 1 的首次调用前后均未形成 accepted 输出（`0/24`）；checkpoint=`FAILED_CLOSED`，failure receipt digest=`ea3065ecfa3207eee34de13ddeaba09b3bddb795740ee2a29ce623cc41250468`，`recorded_v1_decisions_opened=false / recorded_v1_outcomes_opened=false`。不含市场数据的同参数微型调用成功，使用原 Agent schema 的独立合成调用复现了相同 `CODEX_EXEC_NONZERO:1`，原始 provider 错误明确为 `invalid_json_schema`：`execution_order.uniqueItems` 不被当前结构化输出接口接受；cycle 1 冻结输入约 `86,930` bytes，不是本次已证实根因；
- 最小 transport-schema successor：**已实现并冻结，可创建全新 run**。只在发送给 provider 的 schema 投影中移除不受支持的 `uniqueItems`，本地 `_agent_schema`、逐字段语义校验、唯一性、精确六标的顺序、三路径顺序、可行集合、政策、风险、成本、评价和停止条件全部保持不变；Agent packet 显式声明所有需要唯一的数组不得重复。31 项聚焦及相邻回归通过；独立真实 provider 合成调用返回 `COMPLETE`，证明“仅移除 `uniqueItems`”可被当前接口接受且仍保留 `min/maxItems`、数值和字符串约束。修复提交=`b3933170a9c0b2e373efcbc8c8c82643caa0e97a`；实现绑定 `config/theory_paper_v2.seen_v1_diagnostic.v1_5.json` canonical digest=`c8d63ac56c18b378d6905ceb6f7c3b14261e23ec5cefba59ac22aeb2d02a8888`，本 successor 实现对真实 V1 的候选运行仍为 0。下一步必须创建全新 write-once run；旧失败 run 不得作为 successor 的中间状态或确定性臂缓存；
- v1.5 successor prepare：**已完成，outcome 继续关闭**。新 run=`seen-v1-diagnostic-schema-v15-20260802t062500z`，manifest digest=`d44da8bac7f126197c901bf5bf1b8a675ef4a6e120f3b79283b53e4b5c392513`，精确绑定 v1.5 digest；25 个 context 已重新 write-once 冻结，两臂均为 `0/24`，V1 源树 prepare 前后摘要仍同为 `aba02e17eca90ab4b4ae652c485940523e6c0f0ae2f78eae485c8a5019264085`，`recorded_v1_decisions_opened=false / recorded_v1_outcomes_opened=false`；
- v1.5 successor 候选终态：**已完成并封存，允许进入 evaluate**。确定性连续臂与单 Strategy Agent 臂均完成 `24/24` 决策及 cycle 25 terminal；24 次真实 Agent 调用全部形成 schema-valid、语义-valid、无工具、无重试的 accepted 输出，终端收据 digest=`55e8c56110fce4ce25274f8299090e18661f433cb5d371e6d5429c6f75bb9479`。两臂 terminal state digest 分别为 `b5a1b115c1582328ab8553caf3156d8ab9d8199a3b0909812646d06f4a5dae43` 与 `a2981cc085eb8f6f8af8f9a75248a6b619168d0fefd6bdc6f47126483d549cdc`；checkpoint=`CANDIDATES_TERMINAL_OUTCOME_ACCESS_PERMITTED`，在此边界前 `recorded_v1_decisions_opened=false / recorded_v1_outcomes_opened=false`；
- 首份完整已见离线原始结果：**已完成并保持不可变**。raw result digest=`5bc7b664699b0f848b8627d93d58160a6a9604a135b41e60395adda56a145585`，artifact manifest digest=`527875a0b0f61790dc315ca05a0d42871db3b2158d33d9057705f65ac329cd28`，两条候选 state/decision 链、文件物理摘要、自摘要和 evaluation completion 全部复核通过，V1 源树评价后摘要仍为 `aba02e17eca90ab4b4ae652c485940523e6c0f0ae2f78eae485c8a5019264085`。不含 funding 的总净盈亏：V1 实际 `-70.46915232`、单 Agent `-88.783804712151...`、确定性持续政策 `-107.972459710052...` USDT；CORE 原始持有基准为 `+126.073923611111...` USDT。Agent 比确定性臂改善约 `19.19` USDT，但仍落后 V1 约 `18.31` USDT、落后 CORE 持有约 `214.86` USDT。策略归因净值为 V1 `+44.96370591`、Agent `+25.284020849297...`、确定性 `+29.778866664426...` USDT，故当前单 Agent 的总改善主要来自较少伤害外生仓，而不是更好的新增策略风险；funding 继续 `UNKNOWN`，结论固定为 `SEEN_DIAGNOSTIC_COMPLETE_NOT_BLIND_NOT_COST_COMPLETE`；
- 原始结果后审查：**发现新的 P0 评价与战略忠实度问题，原 raw artifact 不覆盖**。第一，候选最大回撤计算把首个净值当作初始峰值，漏掉 genesis→cycle 1：raw 报告确定性/Agent 为 `0.141568% / 0.297009%`，从初始权益 `10000` 独立复算应为 `1.403768% / 1.352832%`，不仅量级错误，还反转两候选排序；V1 逐轮收据可复算最大回撤为 `1.349762%`。第二，SNDK 在 Agent cycle 1 `INVALIDATE_AND_EXIT` 后 24-step 上涨 `36.673119%`，MU 全窗口 WAIT 后上涨 `26.567283%`；Agent 的 SNDK 空仓持续约 `25.60h`，说明“删除固定全目标”只消除了结构，延续捕获和 WAIT 机会成本没有解决，raw 中 K1/K2/K5 的 `RESOLVED` 过度。第三，SNDK 的 PRIMARY/ALTERNATIVE 在 cycle 1→3 从“恢复/下破”变成“下破/恢复”，只有 state digest 与槽位顺序连续，没有稳定 hypothesis identity/lineage，raw 的 K4 不能证明战略语义连续。第四，cycle 1 理由写明未来重入需要新证据，但 `INVALIDATE_AND_EXIT` 没有创建任何 review/reengagement 义务；selected→executed 虽一致，意图→状态承诺并不忠实。第五，Agent 的 feature request 被记录但未被下一轮通用计算口消费；当前 token cap 也只能算 practical 请求值，24 轮中 18 轮 usage 的 output tokens 高于 `4000`，最大 `6016`，不得称为已机器执行的严格预算；
- 新问题审查、最小修复和同数据复核：**已完成结果审计和允许范围内的结构性 P0 修复，原始市场结果未覆盖**。独立 audit digest=`094a5e2992fecf176ebe83b8e9d9c91acba1b3288dc210309812869df378580e`，终局裁决=`SEEN_DIAGNOSTIC_AUDITED_CURRENT_POLICY_NOT_SUPPORTED`；原 raw result 物理摘要仍为 `097bc9af306f87bf0492db1e6a1285673ce2b4655246d0da88e0cfc80e3336af`。修正后最大回撤为 V1 `1.349762%`、Agent `1.352832%`、确定性 `1.403768%`，原候选排序确被反转；Agent 的 SNDK 最长空仓 `25.6041h`，两候选 WAIT/exit 后共有 8 个可得且为正的重叠 24-step 延续代理，因此 K1/K2/K5 改判未解决，K3/K7/K8 仅部分解决，K4 语义 lineage 未解决，funding 仍数据不足。连续 successor 已改为 genesis-inclusive 回撤、稳定 `hypothesis_id` 与 `UPDATE/REPLACE`、上一轮通用特征请求下一轮 OBSERVED 或 typed UNKNOWN、provider-only schema 投影，以及 terminal episode 后 `OPEN_CORE` 新建 episode 并显式替换确定性假说；未加入任何由 SNDK/MU outcome 得出的阈值或强制持有规则。15 项两条应用切片聚焦测试通过；这些 PASS 只证明修复机制，不改变已见市场失败结论；
- 新公开数据采集与连续本地纸面实验：**诊断结构门和最小 OKX 垂直适配器结构门均已通过；尚未读取拟选真实 256-bar 窗口或运行真实窗口政策**。Bybit 官方公共 time/kline 在当前地区明确返回 403；OKX 官方 `public/time` 与 `BTC-USDT-SWAP` 最新 1h history-candles 均成功，官方文档确认同一无需认证的 Public Data 范围还提供 instruments 与最长三个月 funding-rate-history。选择 OKX 只依据可达性、闭合 bar 标志、合约规则和 funding 覆盖，不依据拟实验窗口收益。唯一新增适配器已把 OKX 反序 1h bar、合约规则和 realized funding 映射进既有 `CollectedPublicResponses → PreparedFreshMarketDataset → continuous_experiment` 链；官方响应形状的合成 256-bar 输入已经完整走完 16 个连续时点、三臂、terminal gate 和评价，trade count/taker flow 在 Agent 证据中保持 typed UNKNOWN，未补零，OKX 合约手数按 `lotSz × ctVal` 转换为 BTC 数量步长。funding rate 使用官方 `realizedRate`，结算 mark 只能用结算前已收盘交易 K 线 close 代理，数据集、状态和结果必须持续标记 `NOT_COST_COMPLETE`。下一冻结配置保持原 16 个连续决策、1/4/8/24h、三臂、风险、费用、滑点和确定性政策不变；未解决的延续捕获与机会成本作为新未见实验市场假说，不在已见窗口调参数；严格 token 上限与 served-model 仍无 attestation，只保留 practical 证据标签。

### 需求变更记录

- 2026-08-02：用户明确允许以历史 V1 的具体数据记录和顺序结果进行诊断回测，其目的不是获得盲测或泛化证明，而是验证当前理论/系统能否解决既有问题并发现其他问题；问题解决和复核后，数据采集不再固定渠道，由研究总控自主搜索合规公开来源并继续新的本地纸面实验。该授权覆盖公开数据采集和不可执行纸面研究，不覆盖私有账户、凭据、真实订单、资金或 E0/E0B 恢复，也不自动恢复 `automation-2`。
- 2026-08-02：V1 顺序撮合审查发现两处跨周期中间 1h bar 未被 `process_market_bars` 消费，共 12 个标的-bar；本次实际持仓逐 lot 检查未发现因此漏掉的 barrier fill，所以保留 V1 事实账本不改。当前候选臂在运行前冻结为逐根处理全部新收盘 bar，并明确该修复是模拟顺序修复而非根据收益改策略。
- 2026-08-02：首次正式候选 run 在确定性臂 terminal 后、Agent cycle 1 因 provider 不支持 JSON Schema `uniqueItems` 而失败关闭；没有重试、没有读取 V1 决策或 outcome。允许的唯一 successor 修复是 provider-schema 兼容投影：发送端移除 `uniqueItems`，本地完整 schema 与语义 validator 继续执行所有唯一性及顺序约束；不得借此更改市场输入、动作空间、理论、风险、成本或评价。旧 run 保持不可变，新实现必须重新冻结后另建 run。
- 2026-08-02：v1.5 successor 完成两臂连续候选、terminal outcome gate 和首份完整 raw evaluation。结果不支持当前连续政策优于 V1 或持有基准，并暴露 raw evaluator 的回撤起点错误、动作次数代替路径捕获、digest 连续代替 hypothesis 语义连续、无 review 的 invalidation 后长期空仓及 FeatureRequest 未履约。下一版本只修这些可验证的忠实度/评价缺陷，不用已见涨幅制定持有、退出、重入或加仓阈值；原始结果先定向提交，再做独立 audit successor。
- 2026-08-02：独立 audit successor 在不改写 raw artifact 的前提下纠正回撤并校准 K1–K8；市场结论明确为当前 Agent 未优于 V1 或 CORE 持有，不能以 Agent 比确定性臂少亏约 `19.19` USDT 代替支持证据。允许的状态/评价修复已进入连续实验代码并通过聚焦闭环，下一步只冻结修复后的实现身份，然后从合规公开来源选择新连续窗口；已见 SNDK/MU 结果不得进入新政策阈值。
- 2026-08-02：新窗口数据源按官方文档与只读可达性预检选择 OKX：Bybit 因地区 403 排除，OKX time/kline 已成功且 instruments/funding 为公开免认证端点。本选择发生在下载完整 256-bar 输入及查看拟选窗口 outcome 之前；只允许添加一个 OKX 读取/规范化垂直适配器并复用现有连续 runner，不建设多源平台，不因来源差异把 OKX 不提供的 trade count 或 taker flow 填成零。
- 2026-08-02：最小 OKX 垂直适配器通过官方响应形状的离线合成闭环，证明来源反序、闭合标志、基准/报价成交量、合约数量步长、typed UNKNOWN 和 funding 代理限制能从采集持续到原始结果；该 PASS 只证明结构可运行，不是新的市场证据。下一步先提交并绑定实现与 v2 冻结配置，再允许一次完整 256-bar 官方公共读取；冻结后不得因窗口结果改政策、风险、成本或评价。
- 2026-08-02：OKX 垂直实现已定向提交为 `4782f78faffff40f30f45325414553f0b5963eba`，工作树复核干净。现在只创建 v2 事前合同并绑定该 commit/tree 与关键物理摘要；合同内必须记录真实 256-bar 窗口尚未获取/读取、策略和验收相对 v1 不变。v2 合同提交前继续禁止完整窗口读取，提交后只允许通过显式 `--config ...v2.json` 执行一次 prepare/freeze。
- 2026-08-02：v2 事前合同已生成，canonical digest=`5c6817e85b91c7c77293f40e8c97ef8d221a92d9427a1c6169b2e45cc89b4d36`、物理 SHA-256=`83c3bb4d5dda268aba00cf0c3a0e4069502a93bab3c18c4a4d537021060d49c9`；实现文件摘要、三臂、特征请求、确定性政策、Agent 参数、动作空间、除来源字段外的风险成本、评价指标和停止条件均与冻结前约束复核一致。真实窗口仍未获取/读取；官方响应形状的合成 v2 prepare 产生 16 个决策并通过质量门，只证明合同可执行。提交该合同后，唯一允许的下一动作是一次显式 v2 公共 prepare/freeze，先封存原始响应与 manifest，继续禁止打开 outcome 或启动 Agent 决策。
- 2026-08-02：首次真实 v2 prepare 在写入 run/manifest 前以 `FUNDING_MARK_PROXY_MISSING` 失败关闭；没有生成运行目录、没有启动三臂决策、没有打开评价，但完整响应已由进程短暂读取，后续不得以其结果选择或修改窗口。根因是 funding 解析从 256-bar warmup 起点开始，恰好纳入一个没有更早 bar 可作代理的结算点；所有臂只在首个决策 genesis，warmup 期必为空仓，因此该结算及全部首决策前结算的经济贡献确定为零。唯一允许修复是把 funding 请求/过滤起点从 raw warmup 起点收窄到首个决策时点，保持同一来源选择、窗口选择规则、政策、风险、费用、评价和 `NOT_COST_COMPLETE` 不变；原 v2 合同保持不可变，修复后另建 successor 绑定。
- 2026-08-02：上述唯一修复已提交为 `428cf1d35b9ee37414c921a819ec720111cab405`；v2.1 successor canonical digest=`826d3d8ff990c863a1e52c984d09678ef7f98364585426f59fb412121fe813f9`、物理 SHA-256=`e41d3c35e1e84be14201ee305e5c61b2aa1abc8c639f7c3796cb492551834230`。successor 明确记录前次失败、已获取但未读 outcome、无 run/manifest/决策，并逐字段证明 dataset 选择规则、三臂、风险、成本、政策、评价和停止条件与 v2 相同；关键实现摘要和官方形状合成 prepare 均复核通过。该合同提交后允许第二次真实 prepare；若同类边界再失败，则按“两种合理方案失败”停止扩张并报告，不新建第三套采集系统。
- 2026-08-02：第二次真实 prepare 成功并封存 run=`continuous-p0-btcusdt-20260731T100000Z-20260801T010000Z`，manifest digest=`52fe76ad94af30467a741149d3921be73c14205f8a4d8c05f99903f0ede845f6`、dataset digest=`ad84f7b8ecaa1b356131fcc285f75b30f0cf9d16baa7f6592bf9a0707db31b94`、config digest 与 v2.1 一致；四个官方请求及原始字节摘要已绑定，质量总状态 `PASS`、无 hard failure。16 个连续决策为 `2026-07-31T10:00:00Z` 至 `2026-08-01T01:00:00Z`；outcome 仍未向 Agent 打开，评价保持 `BLOCKED_UNTIL_TERMINAL_RECEIPT`。funding 明确保留 `OBSERVED_REALIZED_RATE_WITH_TRADE_CANDLE_CLOSE_MARK_PROXY_NOT_COST_COMPLETE`。下一动作只允许按 manifest 执行三臂 16 轮顺序决策并生成 terminal receipt；决策失败不得打开 outcome 或修改规则。
- 2026-08-02：真实顺序决策已完成并通过 terminal 复核：16 个连续 cycle、48 条三臂决策、16 个 Strategy Agent 输出，terminal receipt digest=`fe94865e87c25518653906ec18727f961e907a5fa208b5557a75a55dcffdf05a`、event chain head=`4b19ddd25571638d8d19bbc1170d3b48d5c8f1673d74a760ef0e2d9f459feefc`；aggregate heads、事件序列、manifest 绑定和 terminal 自摘要一致。所有 Agent 输出均在 outcome gate 关闭时产生，没有提前 outcome 访问。现在且仅现在允许一次 evaluation 读取已封存 outcome，生成原始结果与 artifact；评价不得修改任何决策、政策、风险、成本或指标。
- 2026-08-02：首份新未见窗口 raw artifact 已完整生成并通过全部文件摘要及自摘要复核，result digest=`be94fd7a4f1ee442ed4868f93340126872e2be294586a826d6f59b832bbe3153`、artifact manifest digest=`c73167d057ef24f0d3c46168149f8246070a62aa2fa338a71ea8bdf381d58540`，terminal verdict=`RAW_RESULT_COMPLETE_DESCRIPTIVE_ONLY`。净盈亏：STATIC_V1 `-5.39253428`、确定性 `0`、单 Agent `0`、同成本 CORE 持有 `-8.1535184676...` USDT；Agent 与确定性 16/16 动作完全相同，均为 16 次 WAIT、全程空仓，故 Agent 相对确定性增量严格为零，raw 的 `descriptive_net_leader=SINGLE_STRATEGY_AGENT` 只是并列时字符串排序，不是市场领先。两臂 WAIT 在 13/16 个时点匹配 24h hindsight-best，但 cycle 5–7 错过三个重叠的正 OPEN_CORE 反事实，合计机会损失 `7.5337825888...` USDT；STATIC_V1 在 cycle 4 由 stop 退出，少亏于持有但仍亏损。Agent 对 TAKER/OI 的请求在后续轮得到 typed UNKNOWN 而非零；16 次调用共约 `556052` input / `15922` output tokens、约 `565.9s`，served model 未 attested。该结果只支持本窗口 WAIT 相对长持有保护资本，不支持 Agent 优于确定性政策、已解决延续捕获/重入、预测有效或盈利；funding mark 代理继续阻断 cost-complete。先原样提交 raw artifact，之后只做独立 audit 与 tie-aware evaluator 修复，不改 raw 文件。
- 2026-08-02：raw artifact 已原样提交为 `9034b4f0138c2eb3b9e44ab52b1a9c79b2005957`。当前唯一在途任务改为独立 post-result audit：绑定 raw result/artifact/terminal 摘要，给出“状态与风险闭环通过、Agent 增量市场价值不获支持、add/reentry/延续捕获未被本窗口验证”的分层裁决；同时只修 successor evaluator 的并列语义，使相同净结果输出 `TIE` 与完整并列臂列表，不按 arm 字符串伪选赢家。禁止改写 raw artifact、重算既有结果文件或用本窗口 cycle 5–7 制定新入场阈值；修复验收只证明未来报告不再误报并列，不改变本窗口市场结论。
- 2026-08-02：独立 audit 已完成，audit digest=`6f3b58adfe5987d3de2c52f945b657a1fb9a1c4f4e8f0d6c72200abed6004594`、终局裁决=`UNSEEN_RESULT_AUDITED_AGENT_INCREMENTAL_VALUE_NOT_SUPPORTED`；raw result 与 artifact manifest 物理摘要仍分别为 `39331f2986c2fc74760fb2484a07f6a2ccb7d33d2a284a6cb389be4b2aae9726`、`4013ce613a8b2af75eb2885fd23eb93ebd8220a36148d1aabc86b3110c88d79e`，未改写。successor evaluator 已取消字符串 tie-break：净值相同时输出 `descriptive_net_leader=TIE` 和按冻结臂顺序列出的 `descriptive_net_leaders`；相邻连续、公开数据和已见诊断闭环均通过。该 PASS 只修报告语义。市场裁决保持：本窗口 WAIT 保护资本但 Agent 无确定性增量，反弹捕获未解决，add/reentry 未被候选臂触发，556k input-token 成本没有对应动作差异，下一轮不得直接重复同类短下跌窗口或扩大 Agent 基础设施。

## 十八、核心目标纠偏与错误决策中心退役

### 本轮最终交付结果

- 撤销 `seen_v1_diagnostic` 和 `continuous_experiment` 作为现行决策中心的资格，删除其应用入口、CLI 和只验证该错误策略形态的测试；九份冻结配置保留原始字节作为历史实验合同，但不再有可执行入口；
- 保留历史 V1、seen-V1、OKX 和 E0/E0B 原始输入、状态链、结果与审计作为不可变证据，不删除失败事实；
- 保留能直接服务下一研究的公开数据适配、点时质量检查、战略状态、lot/组合风险、成本、账本和内容存储；
- 把下一研究起点恢复为“Agent 先做市场研究并提出连续仓位方案，确定性代码只验证数据真实性、硬风险、成本和提交安全”，而不是让 Agent 在代码预先决定的市场解释和动作中选一个。

### 事实裁决

- seen-V1 与 OKX runner 都把 Agent 限制为固定 `PRIMARY / ALTERNATIVE / NULL` 三槽、固定指标摘要和预筛选动作集合的排序器；Agent 不能主动搜索或组合足以区分路径的公开数据，也不能自行构造市场情绪、参与行为和多时间尺度解释；
- 确定性规则在 Agent 之前已经定义交易几何、候选动作和大部分市场判断，风险层同时承担了策略层职责；这不符合“Agent 负责难以完全量化的解释和可行域内选择，代码负责边界与复算”的核心分工；
- 新未见窗口中 Agent 与确定性臂均为 `16/16 WAIT`、全程空仓、动作完全相同，Agent 增量为零，并错过 cycle 5–7 的正向开仓反事实；该结果不是可接受的市场策略，也不能证明长期等待合理；
- seen-V1 中 Agent 仍落后 V1 和 CORE 持有基准，退出后的重入义务、延续捕获、假说语义连续和 funding 完整性未解决；
- 两个 runner 没有完成用户要求的市场情绪研究。将 OI、taker flow、订单流、拥挤、新闻和事件长期留作 `UNKNOWN`，同时禁止 Agent 主动补取，不能被称为“诚实处理缺失后完成分析”；
- 工程闭环、schema-valid、状态摘要和 terminal receipt 只证明程序执行过，不再作为市场分析有效、策略有用或问题已解决的替代证据。

### 验收标准

- 仓库中不存在可直接启动这两个错误策略 runner 的现行 CLI 或应用导入；九份冻结配置只保留为不可变历史合同，不能在当前代码树中启动决策；
- 下一基线不得把固定指标白名单、固定三条语义路径或代码预筛动作集合当作完整市场分析；确定性代码只可拒绝违反点时、数据真实性、授权、硬风险、杠杆、保证金、保护或执行安全的动作；
- `WAIT/ABSTAIN` 必须与持有、试探建仓、加仓、减仓、退出和重入进行同条件机会成本比较，并产生明确复核条件；空仓不按零成本处理；
- Agent 可基于当时可得数据主动提出少量公开数据或指标请求，说明其区分的路径、时间尺度、前提变化和限制；缺失保持 `UNKNOWN`，但不得以预先禁止取数制造永久未知；
- 每轮必须保留上一 accepted strategic state、path/hypothesis identity、core/tactical lot、剩余风险预算、退出原因和重入义务；
- 历史原始 artifact 及审计保持字节不变；可复用数据、PIT、状态、风险、成本、账本和存储模块继续存在；
- 本轮不运行新 outcome、不启动 Agent 实验、automation、paper/live，不接触账户、凭据、订单或资金；删除和裁决完成后，定向测试与引用检查通过并形成单一提交。

### 当前范围与明确不做

- 本轮只做目标纠偏和错误决策中心退役，不立即编写第三个 runner，不建设 Agent 平台、指标平台、插件、transport、角色体系或新证据框架；
- 不修改 `CORE_TRADING_THEORY_v2_1.md` 来适应已经看过的结果；它继续保留为窄 V1 基线和待检验理论材料，动态仓位政策必须另以事前研究问题接受检验；
- 不删除历史 artifact、事故证据、冻结实验或用户原始记录；不把删除错误实现解释为删除失败证据；
- 不因本轮清理而扩大任何外部读取或写入授权。

### 当前主要任务与状态

- 冷启动权威文件、Git 身份和工作树核对：**已完成**；
- 两个错误决策中心的真实调用链、Agent 可见数据和动作约束映射：**已完成**；
- 本节需求纠偏：**已完成**；
- 当前入口纠偏：**已完成**。`README.md`、`PROJECT_CORE_GOAL_RELOAD_2026-08-02.md` 和 `NEXT_WINDOW_RESEARCH_AGENT_PROMPT.md` 已统一为“先在 V1 点时记录上完成 Agent 主导的市场/情绪/竞争路径/连续仓位研究，再由代码复算硬边界”；旧架构、E0/E0B 和固定动作 runner 均不再是当前启动方向；
- 错误入口和专用测试退役：**已完成**。删除 2 个应用决策中心、2 个 CLI 和 2 个专用测试文件，共移除 8,576 行；九份冻结配置逐字节保留为历史合同。四个旧模块均无法再由 Python 发现或导入，仓库非历史文档/非 artifact 范围内无活动代码引用；
- 删除后的引用、保留模块、历史 artifact 不变性和回归验证：**已完成**。seen-V1 raw result SHA-256 仍为 `097bc9af306f87bf0492db1e6a1285673ce2b4655246d0da88e0cfc80e3336af`；OKX raw result 与 artifact manifest SHA-256 仍为 `39331f2986c2fc74760fb2484a07f6a2ccb7d33d2a284a6cb389be4b2aae9726`、`4013ce613a8b2af75eb2885fd23eb93ebd8220a36148d1aabc86b3110c88d79e`。保留的公开数据/PIT、战略状态、风险、账本和 V1 只读适配 23 项聚焦测试通过；全仓 1,193 项中除已知的 2 项 R2 workspace identity drift 外其余通过，本轮没有新增失败；
- 新的分析优先基线：**未开始，且不属于本轮删除边界**。

### 需求变更记录

- 2026-08-02：用户否定把全程空仓、未评估市场情绪、不能主动分析和取数的固定动作排序器继续称为新系统策略，要求重新理解理论升级是为解决 V1 的静态退出、无重入、无连续状态、机会成本不对称和市场解释不足，而不是以新工程重复旧操作。本轮据此把现行 seen-V1/continuous runner 裁决为失败的研究实现并退役；原始结果保留为负面证据，下一基线必须从 Agent 的真实市场研究与连续仓位推理开始。

## 十九、单 Agent 历史诊断、修复与最新版纸面模拟

### 用户最终需要的交付结果

- 不建设或恢复 Agent 集群，由当前单个 Strategy Agent 直接完成市场证据解释、市场情绪与参与行为分析、多时间尺度竞争路径、连续战略状态和仓位选择；确定性代码只负责点时边界、复算、硬风险、成本、撮合、状态提交和执行安全；
- 先使用 V1 已保存的 24 个已提交周期和第 25 个终端边界，逐轮只消费当时可得材料与上一 accepted state，完成一份 `SEEN_V1_DIAGNOSTIC_REPLAY` 原始结果，验证是否真正解决固定目标全平、趋势延续遗漏、核心/战术语义、退出后重入、旧几何、长期空仓、机会成本和漏 bar 撮合；
- 在原始结果封存后审查暴露的问题，只修能够定位到数据、状态、风险、动作、成本或撮合语义的结构性阻塞，再在相同历史输入上复核；不得用 SNDK/HYPE 后续结果反推阈值、核心比例或最优持有规则；
- 历史诊断与问题修复完成后，自主搜索和采集可追溯的公开市场数据，按 V1 相同纸面实验内容完成最新版的本地不可执行纸面模拟：六个原市场、10,000 USDT 初始权益、同口径外生初始仓/原始挂单、逐小时决策、每 8 小时复盘、72 小时总结及逐 lot/动作/成交/假说审计；
- 分层裁决理论支持、理论失败、形式化失败、状态/政策失败、风险与执行失败、数据不足和未知；工程通过不得冒充市场有效、盈利或真实交易许可。

### 验收标准

1. 决策中心只有一个 Strategy Agent；不创建 Proposer/Challenger/Selector、Critic、角色 skill、transport 或集群恢复链，也不让确定性代码预先固定 `PRIMARY / ALTERNATIVE / NULL` 路径、指标白名单或策略动作排序；
2. 每轮 Agent 输入至少包含上一 accepted strategic state、上一动作和接受理由、仍存活与被挑战路径、hard invalidators、pending observations、CORE/TACTICAL lot、剩余风险预算、退出原因、reentry/review 义务，以及当轮所有实际可得市场材料；
3. Agent 可在当时可得和来源可追溯的范围内主动组合价格结构、Bollinger、VWAP、ATR/实现波动、EMA/ADX/效率、量价、depth、aggTrades、OI、funding、basis/拥挤、跨市场强弱、公开新闻与事件元数据；每项新增观测说明区分的路径、时间尺度、改变的前提和局限，缺失保持 `UNKNOWN`；
4. 每轮至少比较趋势延续、正常回撤、动量衰竭/失败和区间重建，并在同一可行域内比较持有、试探建仓、加仓、战术减仓、部分止盈、战略退出、重入与等待；`WAIT/ABSTAIN` 必须给出数据缺口、硬风险 veto 或相对效用理由和明确复核义务；
5. 同一 symbol/episode 使用稳定 identity 和 revision chain；战略有效性与实际敞口分离。空仓不自动结束 episode，非战略失效的全平必须留下可执行 `ReentryContract` 或明确失败关闭；
6. 每个 lot 明确 `CORE / TACTICAL`、父 episode/假说、风险预算、保护、最大 horizon 与退出意图。固定目标先成为 `TargetReachedEvent`：TACTICAL 可以真实成交，CORE 只有在硬失效、账户风险、预注册 episode 终点或显式战略退出时才允许全部清除；
7. 旧 geometry 到期或 regime 改变时必须注销并重建，不得让远离现价的旧 support zone 成为唯一重入门槛；重入资格仍须通过新证据、几何、风险与成本复算，不能自动追价；
8. 回放和纸面撮合逐根消费两个决策点之间所有新闭合 bar。已注册 barrier 按冻结 barrier 或明确的保守同 K 线顺序成交；Agent 发起的市场动作按当时价格及预注册费用/滑点成交，不得利用 1H 延迟取得更优价格；
9. 历史 V1、修复后单 Agent、原 V1 规则和 CORE 保留 25%/50%/75%/全量敏感性使用同一 PIT 序列、起始账户与成本；四种比例只用于说明收益/回撤/机会差曲线，不据已见结果选定新政策参数；
10. 原始结果分开记录策略/外生归因、已实现/未实现盈亏、费用、funding、最大回撤、尾部、多 horizon、最长空仓、重入延迟、加仓利用、路径捕获、基准持有收益和机会差；不可复算或数据不足保持 `UNKNOWN`；
11. V1 诊断先封存原始结果再审查和修复；最新版纸面实验在任何 Agent 决策前冻结数据范围、初始状态、风险、费用/滑点、评价和停止条件，决策从 genesis 到 terminal 顺序完成前不得向 Agent 暴露 future outcome；
12. 最新版纸面模拟必须复现 V1 的研究内容与账户语义，但使用全新本地 run、公开数据与不可执行权限。不能因数据源差异补零、删市场、缩窗口或修改验收来取得通过；数据确实不可得或两种合理方案均失败时停止扩张并报告；
13. 历史原文件、冻结配置、原始 artifact、E0/E0B、事故证据和旧结果保持不可变；所有派生输入、决策、状态、结果和审计写入独立路径并可复算；
14. 最终必须明确每个已知问题为“已解决 / 部分解决 / 未解决 / 数据不可判 / 被新问题替代”，并诚实给出最新版纸面实验对理论的支持、失败或不确定结论。

### 当前范围与明确不做

- 当前主线只允许一个 Strategy Agent 和解除其顺序研究闭环所需的一个最小垂直切片；优先复用现有 V1 点时材料、市场测量、V2 strategic state、lot/风险、离线账本、event/content store 与公开数据适配；
- 不新增通用 Agent 平台、集群、Critic、transport、插件、角色体系、指标专用模块/schema、通用数据平台或新的大规模文档/测试项目；
- 不修改 `CORE_TRADING_THEORY_v2_1.md` 或历史 V1 来适应已见结果；持续战略政策继续作为独立待检验 challenger；
- 不用“总是持有”“固定保留某一比例”“提高换手”代替路径判断；不把 SNDK 的 1348.75、cycle-0024 或 HYPE 后验结果写入更早决策；
- 不恢复 E0/E0B，不启动或创建 automation，不读取私有账户或凭据，不发送 paper/live/真实订单，不接触资金。这里的“纸面实验”仅指本地、不可执行、使用公开数据的顺序模拟；
- 一个真实阻塞最多增加一个最小抽象；连续两种合理方案失败即停止扩张并给出根因和最短合法替代路径。

### 当前主要任务与状态

- 冷启动权威文件、HEAD、分支和工作树核对：**已完成**。本轮从干净 HEAD=`6c73612628e9063713f6565dd35daf5209992db5` 开始，现实映射与需求冻结提交后当前 HEAD=`0465ed4ead869dbc886de668813a0fdafa7aad55`；未覆盖用户变更；
- 本节需求、权限和验收边界：**已完成记录**；
- V1 市场数据、指标、战略状态、风险/账本和 Agent 输入的真实调用链映射：**已完成**。25 个周期形成 150 个唯一“cycle×symbol”快照，六标的齐全；150/150 均为 14/15 公共请求成功，15m/1h/4h/1d 闭合技术窗口、recent 500 trades、depth、OI、funding、basis、多空比和 taker ratio 均实际保存，25 轮新闻元数据共 841 条且无查询错误。点时复核未发现 market observed time 或测量层 `last_closed_bar` 晚于 decision cutoff。强平窗口 150/150 为 `UNKNOWN`，严格订单簿韧性 150/150 不可得，funding 虽有 rate 但未进入 V1 收益账本；这些不能补零；
- 真实调用链裁决：**已完成**。V1 `run_hourly_cycle → process_market_bars → build_cycle_analysis → build_decision_template → validate/apply` 已计算 D/L/C/F/R/K 与新闻上下文，但 `_safe_portfolio_context` 主动把完整 lot、父假说、保护和退出/重入压缩为计数/ID，随后每轮新建 hypothesis instance，review 不回灌；旧分析还未透传 market 中已计算的 recent-window VWAP、完整 order-flow/depth、last closed bar，旧版本也未输出 Bollinger middle/bandwidth/%B。当前 `market.py/theory.py` 已能复算并透传这些指标，V1 raw klines 可合法派生其他少量观测；
- 可复用能力裁决：**已完成**。`LegacyV1Adapter` 可只读验证 24 个已提交周期；`OfflineLot/PortfolioState`、逐 bar matcher、strategic/reentry/risk reducer、content/event store 均存在。固定 stage/profile、action-discrimination、三角色 DAG 和已退役 runner 会再次预设路径或动作，明确不接入本轮决策中心；
- P0 差距裁决：**已完成**。唯一必要垂直切片是：从冻结 V1 原始快照生成不含旧决策/outcome 的开放研究上下文；接受单 Strategy Agent 自行形成的竞争路径与动作；只对 PIT、状态 head、硬风险、成本、保护、CORE 全退/reentry 原子性和逐 bar 撮合做确定性校验与提交。无需新理论文档、集群、transport、指标平台或通用数据层；
- 单 Agent 历史顺序诊断协议与最小提交切片：**实现与正式运行前预检已完成，尚未产生候选市场结果**。冻结合同 `config/theory_paper_v2.single_agent_market_research.v1.json` canonical digest=`027ba9cdce927a44b857f0883d9ae521a27a78e808da04c6ce298806adffde09`，绑定 V1 源树摘要与单应用文件、单 CLI、单聚焦测试文件；代码不生成路径、候选或策略，只做 PIT 规范化、上一 accepted state 透传、证据引用校验、硬风险/成本、逐根 15m 撮合和 write-once 提交。真实 V1 只读预检成功冻结 25 个 context 并打开 cycle 1，V1 决策/outcome 仍为关闭；一轮合成 Agent 提交验证 5 个初始外生仓保护、11 个旧订单处理和 17 个动作均被连续提交。Agent 包从重复证据值造成的约 394KB 降至约 169KB，只删除重复副本，未删除实际技术、市场代理、证据引用或近期闭合序列；11 项聚焦及相邻测试通过，这些只证明研究闭环可运行；
- 当前唯一在途主任务：**冻结并提交上述实现边界，然后启动单 Agent 的 24 轮 V1 历史顺序诊断；原始结果完成前不审查、不调规则**；
- 首次正式单 Agent 候选运行：**在 cycle 21 接受前失败关闭，不能继续或评价**。run=`single-agent-seen-v1-20260802-v1` 已顺序接受 cycle 1–20；cycle 21 仅打开 PIT context，单 Agent 草稿在纯结构校验阶段触发 `INACTIVITY_REQUIRES_WAIT_OBLIGATION`，没有执行 accept、没有改变 cycle 20 accepted state，也没有读取 V1 decision/outcome。failure receipt digest=`6ea18a54f40c85555630c6f20fcbaf69f210f79a2ac9fabc41323136182f3491`。根因已定位为验证器把有仓位 `HOLD` 错当成 `WAIT` 类不行动，尽管 episode 已有 `review_by/pending_observations`，仍强制附加第二条 WAIT 义务；这会扭曲 Agent 动作语义并制造无意义 HOLD+WAIT；
- 最小 successor 修复：**已实现并冻结，仍未产生 successor 候选 cycle**。只把 WAIT 专属义务校验限定到实际 `WAIT` 动作；不改变市场证据、Agent 判断空间、风险、成本、撮合、评价或 cycle 1–20 已形成的判断。失败 run 的原 cycle 21 草稿在新 validator 下纯校验通过，证明根因已被精确解除；16 项聚焦及相邻检查通过。successor `config/theory_paper_v2.single_agent_market_research.v1_1.json` canonical digest=`50c26e15f72d5999941c08aa360834280787aa8c4d36135fadf043d49b7011f1`。下一步创建全新 write-once run，从 genesis 对 cycle 1–20 的已封存 pre-outcome 决策做 run-id/digest 机械重绑定并逐轮重新验证/提交，再由同一个 Strategy Agent 从 cycle 21 继续；不得读取旧 V1 outcome，也不得把失败 run 的 checkpoint 当 successor 中间状态；
- successor 完整顺序运行与首份 V1 历史诊断原始结果：**已完成并封存，尚未进行 post-result 审查**。run=`single-agent-seen-v1-20260802-v11` 从 genesis 完成 24 个决策周期和 cycle 25 terminal，terminal receipt digest=`c93cb635e0c04571a50668b30dce159a024e830df2789c5cb3bb85c425c76ac9`、terminal state digest=`0d74ec2f6d6159b06f3b21dc055a1cfc36525aa864be7de44a6ffa942616e217`；在 terminal 前 V1 decision/outcome 始终关闭。raw evaluation digest=`fd4ec5cfaf257882c2cefcdad960560015eb2de5ef9ca6efd82cbd6992d0d84e`，物理 SHA-256=`d787557a38cab9e05056a8b760e050daef51ef952afeeab54b8a1e034b8d9a84`。不含未知 funding 的候选净损益=`-110.892682427824...` USDT，V1 实际=`-70.46915232`，初始仓静态持有基准=`+126.073923611111...`；候选比 V1 少 `40.423530107824...`，比持有少 `236.966606038935...` USDT。166 个 selected action 全部 APPLIED、0 risk veto，新增风险动作 7 次；这些只证明动作忠实度，不支持市场有效。raw 文件写入的最大回撤=`0.141625...%` 尚未审计，funding 仍 `UNKNOWN`，不得据 raw 字段直接下最终结论；
- 当前唯一在途主任务：**先原样提交 raw artifact，再独立审查评价计算、逐 symbol/归因盈亏、SNDK 路径捕获、空仓/重入、情绪证据与逐 bar 撮合；不改写 raw 文件**；
- raw 后只读审查：**已完成，原 raw 文件保持 SHA-256=`d787557a38cab9e05056a8b760e050daef51ef952afeeab54b8a1e034b8d9a84` 不变**。第一，raw 的候选最大回撤 `0.141625...%` 漏掉 genesis→cycle 1；以冻结初始权益 `10000` 加 25 个顺序净值复算应为 `1.352831803863...%`。V1 raw baseline 又把 terminal 当前回撤 `0.704692%` 误标为最大回撤；24 个 V1 receipt 加 genesis 复算为 `1.3497620622%`，因此候选并未改善决策点最大回撤。第二，候选净损益按归因为外生初始仓 `-90.211158366472...`、新增策略仓 `-20.681524061352...`；V1 对应为外生 `-109.12668283`、策略 `+44.96370591`，故候选相对外生仓少亏约 `18.92`，但新增策略判断少约 `65.65`，总体仍落后。第三，SNDK 总净损益 `-68.639595481034...`，同时初始 SNDK 静态持有为 `+99.444444...`；Agent 全窗口合计空仓约 `24.5814h`，唯一重开是短暂战术空仓而非上涨路径恢复。raw path-capture 因 `primary_direction=NEUTRAL` 把 SNDK directional opportunity 计为 0，掩盖了明确机会损失。第四，4 个 CORE 保护退出生成 reentry contract，但 0 个履约，随后全部被战略失效取消；说明“义务可保存”已解决，“实际重入”未解决。第五，7 个新风险 lot 全部经保护退出，逐账本共有 11 个 protective-stop fill、0 个 tactical-target fill；固定目标全平被消除，但动作偏向持续收紧保护，动态收益捕获不获支持。第六，V1 的 841 条公开新闻元数据均为合法 RFC 日期，而 `_news_rows` 只接受 canonical `Z` 时间并把 841/841 全部丢弃，导致 144 个 public-event sentiment 维度实际上只能报 UNKNOWN；当前结果不能证明市场情绪分析完整。第七，候选未复现 V1 `CHAOS_AUTO` 外生注入，V1 总结果包含其 `-6.30617538` USDT，三臂总 PnL 不是严格同内容对照，必须在评价中单独标明；
- post-result 最小修复边界：**已实现并事前冻结，仍未产生 successor 候选 cycle**。只兼容 RFC 公开新闻时间并保留原 `published_at <= decision_at` PIT 过滤；修正 genesis-inclusive 候选/V1 最大回撤；补充候选 strategy/exogenous 与 symbol 归因、terminal-inclusive 空仓、完整 reentry contract 历史、neutral/flat 机会和 1h/4h/8h/24h 描述性结果；显式标注 slippage 已嵌入 fill、funding 未知和 V1 chaos comparator 差异。未依据 SNDK/MU outcome 修改 stop、方向、仓位比例、入场阈值、风险、成本、撮合、路径类别或动作语义。215 项 Theory Paper V2 聚焦及相邻检查通过；旧 raw 文件 SHA-256 仍为 `d787557a38cab9e05056a8b760e050daef51ef952afeeab54b8a1e034b8d9a84`。successor `config/theory_paper_v2.single_agent_market_research.v1_2.json` canonical digest=`9c8a4b7567f6f38e61fa79bde94c13547cbd37fe25b3f161fa1d7b90b1e1b5fc`；
- 修复后同数据复核：**v12 在 cycle 1 首次纯验证时 fail-closed，0/24 accepted，不得续跑**。同一个单 Strategy Agent 从 fresh genesis 打开 cycle 1、实际读取 23 条当时可见标题元数据并完成六标的分析；草案 SHA-256=`7db5b039f247406572e18d24f83e32e796c0642f217aa157781ff538b4a48bbc`。逐 symbol 只读复核显示除 MU 外的五个决策全部通过，唯一失败是无前态的 MU 使用直观 `episode_operation=CREATE`，而隐藏在验证器中的合法字面量是 `OPEN`；Agent context 没有暴露 episode/action 输出契约，故错误码为 `EPISODE_TRANSITION_INVALID`。所有动作均未接受或执行，future/V1 decision/outcome 均未打开；
- v12 后最小 blocker 修复：**已实现并事前冻结，v13 仍为 0 candidate cycle**。每轮 Agent context 现在只额外暴露既有合法 episode operations/status、genesis/continuity transition 规则和 action type 字面量；`CREATE` 不被静默改写，Agent 仍须明确输出合法 `OPEN`。未改变任何分析、市场、风险、成本、撮合、评价或交易政策，也未建立 schema 平台、通用协议或修改 v12 草案。216 项 Theory Paper V2 聚焦及相邻检查通过；successor `config/theory_paper_v2.single_agent_market_research.v1_3.json` canonical digest=`7667c5402e6392897fac5bacb4a61f20a3efb64c975b1711f58fdc09cec7260b`；下一步从 fresh genesis 运行 `single-agent-seen-v1-20260802-v13`；
- v13 运行裁决：**在 cycle 1 决策前因 Agent 上下文污染 fail-closed，0/24 accepted，不得续跑**。Agent 已打开 v13 当前 cycle 1 context/pre-state，但在定位 CLI/normalizer 时对仓库 Markdown 做搜索，结果意外显示本需求文档中旧 v11 汇总 PnL/评价；虽然没有读取旧 runtime decision/raw/audit、没有看到逐轮 future，也没有写 v13 草案、校验、accept 或动作，但已违反 v13 冻结的“Strategy Agent 不接触旧 post-result 信息”边界。checkpoint 仍为 `AWAITING_SINGLE_AGENT_DECISION_OUTCOMES_SEALED / completed=0 / next=1`，V1 decision/outcome flags 均为 false；
- 当前唯一主任务状态：**受阻，未达到修复后完整历史复核及最新版纸面实测验收**。v12 是自包含输出契约缺失，v13 是运行者意外读取旧汇总信息；两种合理 fresh-genesis 方案连续 fail-closed 后，按停止条件不再新增 v14、第二 Agent 或基础设施。最短合法替代路径是用户确认恢复后，派生一个未接触本线程历史结果的 clean 单 Strategy Agent；只给它冻结 v13 的 CLI 命令、current agent-context/pre-state 和禁止 repo-wide search 的边界，并在新的只改运行身份的 write-once successor 中从 genesis 开始，不再改代码、理论、风险或评价；
- 最新公开数据冻结与 V1 同内容本地纸面模拟：**未开始**；
- automation、账户、凭据、订单、资金、paper/live 外部执行：**明确不做**。

### 需求变更记录

- 2026-08-02：用户明确否定继续进行 Agent 集群和复杂系统设计，要求由单个 Agent 在现有环境中真正完成市场分析、情绪与参与行为判断、连续仓位决策、历史纸面回测、问题审查与修复；历史诊断通过后，按 V1 相同内容开展最新版本地纸面实测。该要求取代第十二至第十五节中的集群/多角色实施方向，也取代第十六至第十七节中已经退役的固定路径/固定动作 runner，但不改写那些历史实验和失败证据。

## 二十、单 Strategy Agent 作战框架与按需数据搜集

### 用户最终需要的交付结果

- 将 Core v2.1、连续战略形式化审查和 V1 事故教训编译成一份短而可执行的单 Strategy Agent 作战手册与流程图，并把冻结内容真实注入每一轮 Agent 输入，而不是再增加 Agent、平台、角色或仅供人阅读的设计文档；
- 让 Agent 每轮按“数据质量与缺口 → 多时间尺度状态 → 市场情绪/参与行为代理 → 机制与竞争路径 → 路径风险收益 → CORE/TACTICAL 仓位与动作 → 复核/重入义务”的顺序完成研究，并明确为什么首选路径胜过次选路径；
- 对有实验价值的数据采用分级获取：先使用已透传观测，再从冻结原始数据按需复算，随后才检索合规公开替代源或标注代理；仍不可得时保持 `UNKNOWN` 并缩小结论，不让单项缺失自动导致全局空仓；
- 在已见 V1 诊断中允许 Agent 学习已知失败类型和完整理论流程，但仍禁止看到当前决策点之后的价格、成交、决策和结果；市场表现失败后只能在原始结果封存并完成归因后，为下一版本加强指导，不能回写当轮理由、阈值、评分或验收。

### 验收标准

1. 作战手册必须覆盖事实/测量/推论分离、多时间尺度角色、情绪与参与行为边界、有限机制库、至少四条有差异的市场路径、支持/软反证/硬失效/到期、路径收益风险以及等待的机会成本；
2. 每条路径至少包含 horizon、当前已观察前缀、支持证据、反证、下一可观察支持、hard falsifier、expiry、预期有利/不利过程和数据缺口；不得以指标极值或新闻标题直接完成路径选择；
3. 每轮必须比较与当前状态相关的 `HOLD / OPEN / ADD / REDUCE / PARTIAL_TAKE_PROFIT / EXIT / REENTER / WAIT`，说明可行集合、成本、最坏损失、剩余风险、错失代价和次优动作失败原因；不要求为了活跃而交易，也不允许无义务长期等待；
4. Agent 必须读取上一 accepted state 并以 `UPDATE / REPLACE / INVALIDATE / OPEN` 明确处理稳定 hypothesis identity；战略状态与敞口状态分离，非战略失效的全平必须留下 review/reentry 义务；
5. 新数据或指标请求只能为区分命名路径服务，必须说明时间尺度、改变的前提、来源偏好、质量/成本和局限；已有数据可复算时不建立新采集模块，不可得时不得补零或伪造；
6. 每轮输出必须绑定作战手册摘要，并由确定性校验拒绝未绑定、未来数据、伪造证据、状态断链、风险超限或保护失败；校验不得替 Agent 选择市场路径或以“谨慎”删除合法动作；
7. 使用该框架从 fresh genesis 完成 24 轮 V1 已见顺序诊断并先封存原始结果，再审查其市场分析、动作忠实度、情绪证据、重入履约、路径捕获、回撤、成本和机会差；不得因结果不好在运行中补规则；
8. 历史诊断确认阻塞问题已解决或明确未解决后，才冻结新的公开数据纸面窗口；数据源不固定，但必须保留 PIT、来源、原始摘要、质量、成本和可复算边界。

### 当前范围与明确不做

- 只增加一个冻结的作战手册/流程图及其在现有单 Agent context、输出绑定和聚焦验证中的最小接线；优先复用现有数据、特征请求、战略状态、lot、风险、账本和撮合；
- 不创建 Agent 集群、Critic、通用 prompt 平台、指标平台、插件系统、数据平台或新的角色/schema 体系；不为每个指标编写模块或硬阈值；
- 不把 V1 后验价格写入作战规则，不固定 CORE 比例、趋势阈值、重入比例或“必须交易”规则；市场失败用于定位分析/政策缺口，不自动归因于 Agent 不够激进；
- E0/E0B、automation、paper/live、账户、凭据、订单和资金边界保持关闭。

### 当前主要任务与状态

- 冷启动权威材料、Git 身份、V1 事故证据和当前需求复核：**已完成**；
- 作战框架、数据搜集阶梯和每轮分析流程冻结：**已完成**。`config/single_strategy_agent_research_playbook.v1.md` 以 Mermaid 流程和十段作战纪律覆盖数据、尺度、情绪代理、竞争机制、路径卡、路径选择、八类动作、Genesis/失效、输出自检和结果后改进；物理 SHA-256=`6314f71820a9cfd3f9fa4e21f2b3d9a4728a0bf47fbde8090b8144622f27cb65`；
- 现有单 Agent context/validator 的最小绑定：**已完成实现，尚待 fresh run 实际 context 复核**。每轮 manifest/context 冻结并内嵌手册原文，decision 必须回绑手册摘要；四条核心路径仍必需，但只在有证据时允许增加流动性、事件、artifact 和 other 路径；路径卡、primary/runner-up、数据请求生命周期和八类动作比较成为可验证输出。战略 `INVALIDATE` 必须匹配上一 accepted hard invalidator，外生初始仓未声明 thesis 不再能自证市场失效；未增加价格阈值、持仓比例、强制交易、风险、成本、撮合或结果规则。successor 合同=`config/theory_paper_v2.single_agent_market_research.v1_4.json`，canonical digest=`7cebc8afc54e87643428ad107a03a478f5a01b47d7a4af9bbf0c71342efbe810`；12 项本切片测试和相邻 Theory Paper V2 回归通过；
- fresh-genesis V1 顺序诊断：**24 个决策周期与 cycle 25 terminal 已完整顺序完成并冻结，市场原始评价尚受确定性汇总阻塞**。run=`single-agent-seen-v1-20260802-v14-guided` 在 terminal receipt 前始终保持 V1 recorded decision/outcome 与 future context 关闭；terminal receipt digest=`e8099d4d87cad63c38628e8afd747e130120999698d4529ef66fccf9c2f2e49d`，terminal state digest=`b82785fc3737c2f37db4d6c7fe3a713ba6e5bcff490adf958da5edaf9f2c0792`。运行中保留并管理五个外生 CORE，完成战术开/加/减/目标/保护、一次明确风险 veto、一次止损后基于新证据重新进入、SNDK 两次 CORE checkpoint 非自动全平和 MU 目标后带义务等待；这些仍须由冻结 raw evaluation 统一裁决，不能先称为市场有效；
- 单 Agent 决策交付阻塞：**已定位，采用一个最小运行期序列化切片解除，不改变冻结研究规则**。clean 子 Agent 对“整轮六标的 JSON”和“单标的增量 JSON”两种合理交付方式均长时间无文件产物，故不再增加 Agent/transport/平台；由当前研究总控本身承担唯一 Strategy Agent，市场解释与选择由 Agent 完成，单个运行期 serializer 只把其逐轮计划展开为既有 schema、证据引用和状态绑定，不计算或预选路径/动作；
- 原始评价阻塞与最小修复边界：**已精确解除**。冻结 terminal 的候选净损益为高精度 Decimal 聚合，按归因分别规范化后再相加只产生 `0.00000000000000000000000001` USDT 的舍入差；评价器原先使用逐位完全相等将其误判为 `CANDIDATE_ATTRIBUTION_RECONCILIATION_FAILED`。现仅增加 `1e-12 USDT` 勾稽容差，超过容差仍失败；13 项聚焦测试通过，未改 terminal state、成交、动作、价格、风险、成本、基准、市场评价或验收；
- fresh-genesis 原始结果：**已完成并封存，尚未完成 post-result 审查**。raw evaluation digest=`d8a37a55324a7dbceb052acbf369f28d41e52160024a43bf23e7cfb8890a6cd4`，物理 SHA-256=`bc0ece42cba51a3b1321f672d0c7cdf9240cfdd8a47b8c233bcca79349b7f2c1`。不含未知 funding 的候选净损益=`+28.158276796099...` USDT、V1 recorded baseline=`-70.46915232`、初始仓静态持有=`+126.073923611111...`；候选比 V1 高约 `98.63`，但比静态持有少约 `97.92` USDT。候选新增策略仓净贡献=`+39.627127924803...`，外生初始仓=`-11.468851128704...`；最大回撤=`1.3497620622%`。169 个选择动作中 168 个应用、1 个被风险内核拒绝；6 次新风险动作。上述只是已见诊断原始事实，不证明预测有效、稳定盈利或最新版纸面就绪；
- post-result 审查：**已完成，raw 文件保持 SHA-256=`bc0ece42cba51a3b1321f672d0c7cdf9240cfdd8a47b8c233bcca79349b7f2c1` 不变**。相对旧 v11，候选净结果由 `-110.89` 改善到 `+28.16` USDT；除原本无初始仓的 MU 外五个标的全程均保留 CORE，方向判断的描述性正确率由 `48.94%` 提高到 `63.57%`，正确方向中的敞口捕获由 `80.43%` 提高到 `98.78%`；保护止损成交由 11 次降至 1 次，TACTICAL 目标真实成交由 0 增至 2 次。已知问题分层为：固定目标全平、空仓吸收、CORE/TACTICAL 语义和逐 bar barrier **本样本已解决**；战术止损后下一轮重新进入 **本样本已履约**，但 CORE 全退后的 reentry contract 未被触发，仍属 **未验证**；机会成本 **部分解决**，SNDK 候选仅 `+3.94`、HYPE `-7.94`，相应静态持有为 `+99.44`、`+14.08`，候选总体仍比初始仓持有少 `97.92` USDT；最大回撤约 `1.3498%`，与 V1 基本相同；预测有效和稳定盈利仍 **未建立**；
- 审查发现的 P0 状态/分析缺口：**需要在任何新窗口前最小修复**。第一，15m 自动止损或目标把 lot 清零后，下一轮 pre-decision context 的 episode `exposure_status` 仍短暂保留 `EXPOSED_TACTICAL_ONLY`；cycle 21 与 24 的 MU 都出现“0 个 open lot / 仍称有战术仓”，虽 Agent 根据 fill event 正确处理且 accept 后恢复 `FLAT_WATCH`，但输入状态存在冲突。第二，144/144 个 public-event 情绪维度均为 `UNKNOWN`、0 条新闻证据引用，而 PIT context 实际有 111 条唯一公开标题、123/150 symbol-cycle 可见；价格/流量、拥挤和跨市场代理已实际分析，但事件情绪仅属 **部分完成**。第三，cross-market 计算虽然可见，却没有自己的 evidence ref，144 轮跨市场解释只能引用本标的价格/4h 字段，追溯不完整。第四，稳定 path identity 得到保持，但部分 terminal thesis/switch condition 仍停留在已越过的旧水平（如 MU 797/856、SNDK 1125/1167），说明动态 geometry 与 path card 内容更新 **部分失败**；
- post-result P0 修复：**已完成，未重跑或改写已见 raw**。bar replay 结束后现在按真实 open lots 与 reentry contract 重算 episode exposure；用冻结 cycle 20→21 止损和 cycle 23→24 目标场景只读复算，二者均从原来的“0 lot / `EXPOSED_TACTICAL_ONLY`”修正为“0 lot / `FLAT_WATCH`”。现有 cross-market vector 增加 `cross_market:six-symbol:relative-strength` 与 PIT `available_at`，各标的情绪决策可合法引用，未引入交易信号。14 项聚焦测试与编译检查通过；
- 下一版 Agent 作战指导：**已冻结为后续新窗口候选输入，尚未绑定或启动实验**。`config/single_strategy_agent_research_playbook.v2.md` 物理 SHA-256=`624bbdb89a4d87ff2498d52f8af34c83888645a134e22861ee53317f6fb3308c`；它新增输入真值冲突 fail-closed、新闻 metadata 必须实际审查、cross-market 必须引用独立证据、已越过 switch condition 不得原样携带、稳定 path_id 与动态 thesis/geometry 分离，以及战术成交后必须比较重入与带义务等待。未加入价格阈值、固定 CORE 比例、机械指标规则或强制交易；
- 新公开数据路线核对：**已完成，未启动 paper/automation**。当前环境对 Binance 三个公共行情路径均返回 HTTP 451 地域限制，Bybit public instrument 路径被 CloudFront country block；均未绕过。OKX 无凭据公开 API 实际返回 code `0`，六个原标的均存在 live USDT SWAP：`SNDK/MU/BTC/ETH/SOL/HYPE-USDT-SWAP`。六者逐一取得 1H candles、OI、funding、20×20 book、100 条 recent trades 和 recent liquidation groups；SNDK 额外验证 100 条 15m history candles、100 条 funding history、100 条 1h OI history、720 条 1h long/short ratio 与 taker volume。capability probe=`artifacts/public-market-data/okx-six-market-capability-20260802T172827Z.json`，SHA-256=`aa5647fec673c914541d8381e34e69004085275bd373a1a4d3e71b33e72e4a2c`；
- 数据裁决：**新窗口的数据可得性不再是总阻塞，但实验仍未获启动授权**。闭合 bar、recent flow、OI/history、funding/settlement、mark/index basis、long/short、taker volume、book snapshot 和 recent liquidation 均可从同一公开 venue 冻结；强平响应只能证明 recent rows，不证明完整历史；单次 book 仍不能证明严格补单韧性，后者保持 UNKNOWN，除非另行授权前瞻多快照/stream 采集。公开新闻继续复用现有 PIT RSS，但 v2 要求 Agent 实际引用或说明其无增量；
- 当前唯一推荐下一边界：**在用户重新授权本地最新纸面实验后，先冻结 OKX 六标的 genesis 数据、初始仓/挂单映射、72 小时窗口、费用/滑点/funding、风险、三条对照政策、评价和停止条件；首轮 Agent 决策前不再修改**。在授权前不创建 automation，不启动 paper/live，不接触账户、凭据、订单或资金；
- 最新公开数据冻结与 V1 同内容本地纸面模拟：**未开始**；

### 需求变更记录

- 2026-08-02：用户要求对暂时无法获得的数据主动寻找合规替代或暂时保留未知，优先搜集真正影响实验路径区分的数据；要求在市场表现失败后加强单 Agent 对理论、详细流程、路径分析和选择的理解，并交付可行流程图与框架，使 Agent 不再无结构地生成决策。新增要求只授权单 Agent 指导与公开研究数据搜集，不恢复集群或任何外部交易权限。

## 二十一、24 小时最新公开市场纸面实验

### 用户最终需要的交付结果

- 从全新 genesis 开始完成一次 24 小时、六市场、逐小时决策、每 4 小时复盘的连续未见纸面实验，真实检验 Core v2.1、单 Strategy Agent 作战手册 v2、连续战略状态、CORE/TACTICAL 仓位、动态退出与重入是否能够在市场顺序展开中对应运行；
- 对 V1 可比的已有初始仓位，将模拟成本统一设置为 genesis 时点 OKX mark price 的 `102%`，使开局处于约 `-1.96%` 未实现亏损；这只是外生初始 lot 的成本基准，不是在市价上方伪造成交。沿用 V1 的有仓/空仓角色与初始名义风险占比，数量按 genesis 价格反算，不直接搬用旧绝对数量；
- 每个小时周期都交付完整中文研究记录：数据采集、质量与缺口、分析流程、理论来源、事实/测量/推论分离、市场情绪与参与行为、多时间尺度结构、竞争路径及概率、上一假说的动态推进、可行动作比较、最终选择、逐 lot 仓位/成交/成本/风险和下一复核或重入义务；
- 同一数据、起点、风险和成本下并行记账 `STATIC_V1 / DETERMINISTIC_CONTINUOUS / SINGLE_STRATEGY_AGENT` 三条政策；先封存原始 terminal 结果，再审查理论支持、失败、不确定和新问题，不在运行中补规则。

### 验收标准

1. genesis 冻结六个 OKX USDT-SWAP、24 个逐小时 decision cycle、cycle 25 terminal，以及 cycle 4/8/12/16/20/24 的 4 小时复盘；每轮只使用 `available_at <= decision_at` 的观测并读取上一 accepted state；
2. 每轮数据报告逐接口列出请求时间、来源/endpoint、成功或失败、最新 observation time、rows、覆盖、陈旧性、缺口和物理摘要；闭合 15m/1h/4h/1d K 线、mark/index/basis、OI/history、funding/history、long-short、taker volume、book、trades、recent liquidation 与公开新闻按实际可得采集，失败保持 `UNKNOWN`；
3. 每轮分析必须把每个关键判断回指 `CORE_TRADING_THEORY_v2_1.md`、`config/single_strategy_agent_research_playbook.v2.md` 或本轮冻结政策中的具体章节/原则，并标明它属于观测、计算、推论、假说、预测、政策或风险；
4. 每个标的至少维护趋势延续、正常回撤、动量衰竭/失败和区间重建四条竞争路径；允许增加事件、流动性、拥挤或其他路径。每条给出概率，单标的总和为 `100%`，同时给出置信度、证据质量、支持、反证、下一可观察条件、hard falsifier、expiry、预期有利/不利过程；概率属于受证据约束的 Agent 判断，不冒充已校准频率；
5. 每轮显式说明相对上一 revision 的新增/移除证据、概率变化、主路径/次路径切换、geometry 更新、假说状态和原因；已经越过、触发或过期的条件不得原样携带；
6. 每轮在真实可行域内比较 `HOLD / OPEN / ADD / REDUCE / PARTIAL_TAKE_PROFIT / EXIT / REENTER / WAIT`，记录相对效用、最坏损失、成本、剩余风险、机会成本和次优动作未选原因；风险内核不得以“谨慎”为由静默删除合法持有、加仓或重入，`WAIT` 不得成为无义务或零成本默认答案；
7. 仓位管理允许 Agent 在冻结硬风险边界内积极使用试探、分批加仓、核心/战术分离、部分止盈、保护移动、退出和重入；不设置固定交易次数、固定 CORE 比例或强迫交易，市场判断仍由 Agent 负责；
8. 每轮逐 policy、symbol、lot 记录角色、数量、成本、mark、名义敞口、已实现/未实现盈亏、费用、funding、stop/target/trail、父 episode/path、风险预算、退出意图、成交和 reentry/review 义务；自动 barrier fill 后下一轮敞口状态必须与真实 open lots 一致；
9. 4 小时复盘分别审查预测与实际前缀、动作忠实度、路径捕获、机会差、加仓利用、退出/重入延迟、费用/funding 和回撤，但不得修改运行中的理论、阈值、评分、风险或停止条件；只能记录待 terminal 后审查的问题；
10. terminal 后报告三政策成本后结果、策略/外生归因、逐 symbol PnL、最大回撤、尾部、多 horizon、最长空仓、路径捕获和机会成本，并逐项裁决 V1 已知问题及新发现问题；工程完成不等于预测有效、稳定盈利或真实交易就绪。

### 当前范围与明确不做

- 本轮授权包括：无凭据公开市场/新闻数据读取、未来 24 小时的本地定时采集、不可执行纸面状态和报告写入，以及为本实验创建一个最小定时任务；旧 `automation-2` 继续暂停，不恢复任何历史自动任务；
- 不访问账户或私有数据，不使用凭据，不调用交易/下单接口，不发送 paper/live/真实订单，不接触资金；本地 fill 只称为模拟成交；
- 不恢复 E0/E0B，不创建 Agent 集群、Critic、transport、插件平台、指标平台、通用数据平台或新角色体系；当前研究总控本身就是唯一 Strategy Agent；
- 首轮决策前冻结数据、初始状态、三政策、硬风险、费用、滑点、funding、评价和停止条件；运行中不得用已经展开的价格结果修改这些内容；
- 数据渠道不固定，但遇到 403、地域、许可或凭据边界不绕过；使用合法公开替代源，仍不可得则保持 `UNKNOWN`。

### 当前主要任务与状态

- 用户授权、24 小时/4 小时节奏、102% 初始成本和逐轮完整报告口径：**已确认**；
- Git 分支、HEAD 和工作树复核：**已完成**。启动前 HEAD=`474668bc88be2f383a050adac78fa14a8889d0fd`，工作树干净；
- 需求记录：**已更新**；
- genesis 模板、风险/成本/三政策/评价与停止条件冻结：**已完成；正式 genesis 尝试的失败见下**。模板=`config/theory_paper_v2.prospective_24h.v1.json`，canonical digest=`75f1e4e94afc58781f1d82f50a366fc703d91251b7078f671233e7e8be6f1bcb`；固定 24 个逐小时决策、cycle 25 terminal、4/8/12/16/20/24 复盘、五个 V1 可比初始 market notional、102% 成本、V1 风险/费用/滑点、OKX realized funding、三政策和 raw-first 评价；
- 最小前瞻垂直切片：**已实现并完成无交易聚焦验证**。复用现有单 Agent state/risk/lot/账本/15m matcher；新增 OKX 六市场 PIT 采集、逐请求原始摘要、逐小时 context append、funding settlement、路径概率合计 100%、理论来源与 epistemic trace、两条冻结 comparator 复算和 terminal 评价。17 项相关检查通过；这些只证明闭环可运行，不是市场结果；
- 数据采集预检裁决：**必需数据实际可达，正式 genesis 仍须重新采集**。Python `urllib` 对 OKX TLS 握手超时，受同一 host/path 白名单约束的系统 curl 可用；MU 15m 的间歇失败定位为 HTTP/2 framing，固定 HTTP/1.1 后同 URL 返回 100 行、99 行闭合。同步等待 18 类数据曾超过 4 分钟，故冻结为每小时核心链与 4 小时慢统计补充链；可选慢端点失败保持 UNKNOWN，不拖延或伪造必需行情。三次预检目录均位于 `/tmp`，未作为正式输入；
- 首轮单 Strategy Agent 市场研究与纸面决策：**受数据入口阻塞，未进入决策阶段**；
- 首次正式 genesis 尝试：**在 manifest、初始仓和任何 Agent 决策前失败关闭，不得续用其部分数据**。run=`single-agent-prospective-24h-20260803t064523z` 的唯一 fatal=`REQUIRED_OKX_OBSERVATION_MISSING:MUUSDT:candles_1w`；其余已返回数据仍属部分 pre-freeze capture，不能拼接到 successor。该失败证明模板把 1W 错列为硬必需，而作战手册第 4 节明确规定“1W 历史不足则 UNKNOWN”；这与用户允许暂时不收集非必要数据冲突；
- genesis successor 最小修复：**已冻结，尚无市场决策结果**。后继模板=`config/theory_paper_v2.prospective_24h.v1_1.json`，canonical digest=`d10bcde934eded0361f6feefda42a036adb6c22150625819543bcca1054bad75`。只把 1W 空缺从 fatal 改为显式 `UNKNOWN`，15m/1h/4h/1d 与 mark 仍为硬必需；不改变 24 小时窗口、102% 成本、三政策、仓位、风险、费用、概率、评价或其他数据。旧失败 run 保留独立失败收据，全新 successor 必须重新采集全部 genesis 数据，不复用旧响应。新增回归直接证明空 1W 可进入 `UNKNOWN`，18 项单 Agent 聚焦检查与 5 项 fresh-market 检查通过；
- successor 正式 genesis：**再次在 manifest 前失败关闭，不得续用**。run=`single-agent-prospective-24h-20260803t065717z` 共请求 108 项 OKX 观测，成功 82 项；36 项冻结核心输入取得 33 项，缺失 SNDK 1h、SNDK 1d 与 ETH 4h。失败后同 URL 只读诊断为 SNDK 1h HTTP 200、SNDK 1d TLS `SSL_ERROR_SYSCALL`、ETH 4h empty reply，证明当前公开传输间歇不稳定；失败捕获没有持久化被 catch 的逐请求异常，因此正式请求的精确底层错误保持 UNKNOWN。failure receipt digest=`6f44821b06db972ac7e26e0c68502964693468dd7db0bbc2709a8ab5dfb014a2`；无 manifest、genesis state、102% 初始仓、Agent 分析、路径概率、动作或成交；
- 当前唯一主任务状态：**受阻，未达到 24 小时纸面实验验收**。v1 的 1W 必需性分类错误和 v1.1 的核心 OHLC 公开传输缺口构成两次合理正式方案失败，按停止条件不再创建第三个 run、automation 或新数据平台。失败后对三项缺口只读探测 OKX `market/candles`，仅 SNDK 1d 返回 HTTP 200，SNDK 1h 与 ETH 4h 仍为 TLS 失败，故单一 URL 回退也未证明稳定。最短合法替代路径需要用户再次授权一个数据可见性 successor：逐请求先落成功/失败 receipt；`history-candles`→`market/candles`；低周期完整时按固定 UTC 桶确定性聚合；instrument/mark/15m 继续硬必需，无法取得或合法聚合的高周期按标的保留 UNKNOWN 并降低置信度，不再导致六市场全局失败。仅当 1h 直接取得或可由完整 15m 复算时才评价对应 comparator。风险、成本、102% 初始仓、三政策、24 小时窗口与评价均不改变；
- 24 个顺序周期、六次 4 小时复盘和 terminal 原始结果：**受阻，0/24 accepted**。

### 2026-08-03 数据恢复续行授权

- 用户已明确授权解除“两次正式方案失败后停止”的当前阻塞，要求以完成真实市场研究为优先，规范可以在不损害事实、点时、风险和外部权限边界时灵活修正；因此允许创建全新 successor 和新 run，但不得把失败 run 的部分响应冒充同一时点完整输入，也不得改写已经 accepted 的市场决策；
- 当前唯一在途主任务改为：**先解除已知公开数据采集问题，再从新 genesis 完成首轮单 Strategy Agent 分析与纸面决策**。采集器必须先持久化每个请求的全部尝试和失败原因，降低同时请求压力，使用 OKX 两个官方 K 线端点的有界回退；完整低周期闭合 K 线可以按固定 UTC 桶确定性聚合高周期；
- instrument、mark 与足以形成当前执行前缀的闭合 15m 数据继续作为硬输入。1h/4h/1d/1w 优先直接采集，失败后可合法聚合；仍不可得时只将对应标的/尺度记为 `UNKNOWN`、降低路径置信度并留下复核义务，不再让单项高周期缺失导致六市场全局失败。若 1h ATR 无法直接取得或从完整 15m 序列复算，则只把该标的 comparator 标记不可评价，不伪造几何；
- 纯采集/序列化问题允许在没有 accepted decision 的 fresh run 之间修正并重启；一旦 cycle 1 accepted，理论、风险、成本、102% 初始成本、三政策、评价和动作语义保持冻结，只允许按原合同处理数据缺失；
- 点时边界、缺失不补零、来源可追溯、公式可复算、硬风险，以及账户/凭据/订单/资金禁区仍不可放松。数据恢复成功后直接产出首轮完整中文报告，并仅在首轮 accepted 后启动逐小时最小任务。
- 数据恢复非实验预检：**已成功形成完整六市场 context，不作为正式输入**。`/tmp/agent-trade-prospective-v12-pretest.cM9RnZ` 从 `2026-08-03T08:38:44.396Z` 至 decision cutoff `08:48:09.222Z` 运行约 565 秒；108 项 OKX 请求成功 86、失败 22，六个 instrument/mark/15m 均成功。30 个 symbol-timeframe 中 28 个直接取得，MU 1W 由 152 根直接 1D 聚合为 21 个完整 UTC 周桶，BTC 4H 由 299 根直接 1H 聚合为 74 个完整 UTC 4H 桶，0 个尺度最终 UNKNOWN；六项 K 线通过 `/market/candles` 回退成功，instrument/mark 的多次尝试也实际恢复。每个请求均有自摘要 attempt receipt，失败原因保留 curl exit、TLS/timeout/empty reply；新闻 5/6 请求成功，SNDK 超时保持 UNKNOWN。该结果证明最小数据修复可解除此前全局 fatal，但不证明下一次正式采集必然成功，也不构成市场理论结果；
- 数据恢复 successor：**已实现、冻结并启动正式 run**。模板=`config/theory_paper_v2.prospective_24h.v1_2.json`，canonical digest=`457f16bbc648c69632479f5dc40e7a598a5aecae2192e65ce49cfaf797f81614`；只改变公开数据可见性、尝试收据、并发、回退、完整 UTC 聚合和缺失尺度处理，并让 comparator 在 1h ATR/重入测量缺失时跳过不可评价动作而非伪造。理论、路径类别、风险、费用、滑点、funding、102% 初始成本、三政策、24 小时节奏和评价不变；26 项聚焦检查、编译和 binding 校验通过；
- 正式 successor genesis 与 cycle 1 输入：**已成功冻结，cycle 1 尚未 accepted**。run=`single-agent-prospective-24h-20260803t085252z`，genesis/decision cutoff=`2026-08-03T09:00:19.280Z`，terminal due=`2026-08-04T09:00:19.280Z`；acquisition digest=`016fd76be30902eb588ad7bee0f85e6bf465842a0b486273c5e4a72d3427a3db`、context digest=`3855b75e68fede68a2aa809392fc0c98747007a8fe495eab9a2b9145ce08b2c5`、manifest digest=`7165bfb4524ddda9758f8d4edc3956c9aa0a5536f454612b28a6e3fe8f2006ca`。六个 instrument/mark/15m 均可用，五个 102% 成本外生 CORE 已建立但仍待首轮保护，初始净值=`9918`、未实现损益=`-82` USDT；V1 decision/outcome 未打开；
- cycle 1 单 Agent 决策预提交：**完整六标的分析和路径概率已通过 schema/状态纯演算，但发现一个提交排序 blocker，尚未 accepted**。Agent 选择为五个外生 CORE 建立结构保护并继续持有，同时对空仓 MU 选择 800 USDT 战术超卖探针。纯演算显示 MU 动作先于 BTC/ETH/SOL/HYPE 的同一决策保护动作执行，被风险核错误报 `UNPROTECTED_EXISTING_LOT`；同时 800 USDT 的计划净损失 `15.058684...` 略高于冻结 probe 上限约 `14.877`。前者是同一原子决策按 symbol 顺序而非“先保护、后新增风险”的确定性执行缺陷，后者是正常风险复算；
- cycle 1 唯一最小修复边界：**已完成并验证**。同一 accepted decision 内的 `SET_PROTECTION / MOVE_STOP / TRAIL_CORE` 先全组合应用，再按原相对顺序应用其他动作，使新增风险读取同一决策已经建立的保护；MU Agent 探针名义从 800 调整为 775 USDT，使原 stop/target/path 不变且计划风险进入冻结 probe 上限；accepted state 在动作后重算 `risk_snapshot`。未改变市场数据、路径概率、理论、stop/target、风险上限、成本、三政策、评价或已冻结 24 小时窗口；22 项相关检查通过，完整纯演算 11/11 actions applied、0 veto；
- cycle 1 accepted 与同条件对照：**已完成**。accepted state digest=`1d9964daebfd9567cb954e9ae5f09ca68612d2c266fdf5abddf18dc2f6665f72`、decision digest=`e2fa31448dab96534addd2fecbe82daf17058b5e0fb1ff826cf8a30aa88a86c5`、receipt digest=`61659cf32e09cb9b93028cb433d06e2b59e3f391eae258bfac48f29fadd5c590`；11/11 动作 applied、0 veto，MU 775 USDT 战术 entry 成交价=`820.184004`、入场费=`0.3875`、计划净损失=`14.588100559...`、净 RR=`2.006650449...`，五个 CORE 全部受保护。首次 comparator 复算错误地用 genesis 前整个 recent 1h 窗口最高价覆盖 `high_water=genesis mark`；现已限定为从 genesis mark 开始、仅接纳持仓后新增闭合 1h high，并拒绝把不低于当前 mark 的候选保护价注册为 stop。重算五个 stop 均低于 mark，STATIC_V1/DETERMINISTIC_CONTINUOUS/INITIAL_STATIC_HOLD 在尚无后续行情时均为 `-82` USDT，result digest=`cf46c3eccee94ae7139006f2466a1c54d64f26bca6faded656bc828bc02b22bb`；
- cycle 1 lot 合同审阅：**实际风险可复算，但 accepted state 留下字段忠实度缺口；不得改写该 write-once state**。cycle 1 `risk_snapshot` 已精确记录六个标的开放风险及组合风险，但五个外生 CORE 的 `lot_contract.risk_budget_usdt` 仍为 `null`、`exit_intent` 仍为 `EXOGENOUS_RECONCILIATION_REQUIRED`，没有反映本轮已经建立保护并由 Strategy Agent 接管动态管理。后续 state 提交前必须从 entry/stop/remaining quantity/contract multiplier 复算每个开放 lot 风险预算，并仅把仍带该 genesis 占位意图的已保护 CORE 转为 `CORE_DYNAMIC_MANAGEMENT`；cycle 1 报告同时保留原字段缺口和可复算风险，不伪称历史 state 已修复；
- cycle 1 完整中文报告与续跑：**已完成并启用**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0001.md`，SHA-256=`5f9c4f6142d6be4285a3174959148be66b6bd0a53dd46e963429f1f206eaaa69`，包含采集、理论、推论、情绪、路径概率、动作比较、逐 lot、成交、风险、成本、comparator 和已知问题。heartbeat automation id=`24h-agent` 已设为 ACTIVE，在每个小时 cutoff 后推进 checkpoint 指定的一个周期；旧 automation 保持暂停，权限仍为本地不可执行。当前唯一在途主任务是按 `next_cycle_index=2` 收集并完成 cycle 2，不回改 cycle 1；
- cycle 2 到期续行：**已完成，2/24 accepted**。heartbeat 于 `2026-08-03T10:05:14.542Z` 复核 checkpoint 后只推进 next cycle 2；实际 decision_at=`2026-08-03T10:07:54.078Z`，相对 due 迟到 `454` 秒并原样保留。90/90 个 OKX 市场请求与 6/6 个新闻查询成功、0 retry；28/30 个尺度形成闭合技术状态，SNDK/MU 1W 因仅 22 根历史为 `UNKNOWN`，非 4h 慢统计周期的 F/long-short/aggregated taker 与严格 order-book resilience 也保持 UNKNOWN。acquisition digest=`248ccdcf62012183b9796aff8ca23e0a2f1c758035927bf446cd8f27be873e86`、context digest=`edd715be1d3775873be0cb86a512ee1279b339b1c272f2188f59020e81837eb8`；V1 decision/outcome 未打开；
- cycle 2 单 Agent 动态决策：**write-once accepted，8/8 动作 applied、0 veto、0 unprotected lot**。新增证据使 SNDK 的 FAILURE 从 `23%` 升至 `38%` 并成为 primary，Agent 只减 `25%` CORE，保留 `75%` 及原 `1188` 保护，不把尚未发生的 4h hard invalidator 冒充全平依据；HYPE 的回撤修复与横截面强度得到部分确认，新增 `500 USDT` TACTICAL，entry=`52.7915562`、stop=`51.86`、target=`54.4643`、计划成本后损失=`9.465833847...`、净 RR=`1.620035729...`，既有 CORE 仍使用独立 `50.99` stop。BTC/ETH/SOL CORE 与 MU 775 USDT TACTICAL 持有；accepted state digest=`71d307d0c94abbad0e14a2e3d97aac0b7198cfab33fbd7e4d0da98b938650794`、decision digest=`c08810abf3385c0855a9976e87e1e9b280d26c094b3fa7223e55981fb5d9421f`、receipt digest=`892b178c6ab5b7e2be383859625aab7168ac08e379c9eec7a4bf62098f20a422`；五个外生 CORE 的下一 accepted contract 已真实转为可复算 risk budget 与 `CORE_DYNAMIC_MANAGEMENT`，未改写 cycle 1；
- cycle 2 成本后状态与同条件对照：**已复算并如实保留不利前缀**。Agent equity=`9917.184908626040...`、净损益=`-82.815091373959...`、已实现费前=`-4.049433785107...`、未实现=`-78.066432305744...`、累计费用=`0.699225283107...`、funding=`0`、gross=`5251.433567694255...`、开放风险=`163.247976496707... / 297.515547258781...` USDT。STATIC_V1、DETERMINISTIC_CONTINUOUS 与 INITIAL_STATIC_HOLD 同点均为 `-69.325614713508...`，Agent 暂时落后约 `13.48948` USDT；2/24 不据此调参或裁定理论。对照首次复算暴露 `recent_closed_bars` 的规范字段为 `close_time_ms`、汇总器却读取 `close_time` 的确定性 KeyError；最小修复只改为读取现有 `close_time_ms`，未改变已接受决策、行情、policy、stop、成本或评价，真实 Cycle 1→2 复算 result digest=`1156e318262f88702f4c67757909fed324b71b299bddfa30ba1d2064d8808b13`，前瞻采集聚焦检查与编译通过；
- cycle 2 完整中文报告与下一状态：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0002.md`，SHA-256=`68d826aef70f521dea6276986c8d84201f788fe4740a69e0de611eb98e1f8a4c`；checkpoint 已回到 `RUNNING_OUTCOMES_SEALED`、`completed_cycles=2`、`next_cycle_index=3`、无 pending context。当前唯一在途主任务是等待 cycle 3 到期后先重放新闭合 15m barrier，再只推进 cycle 3；
- cycle 3 到期续行与公开数据：**已完成，3/24 accepted**。heartbeat=`2026-08-03T11:04:14.701Z` 复核 checkpoint 后只推进 next cycle 3；实际 decision_at=`2026-08-03T11:06:59.915Z`、迟到 `400` 秒并原样保留。90/90 个 OKX 请求与 6/6 个新闻查询成功，所有市场请求一次成功、0 retry/0 prior error；28/30 个尺度形成闭合技术状态，SNDK/MU 1W 因 22 根历史不足继续 `UNKNOWN`。F、慢统计与严格订单簿韧性不补零；acquisition digest=`ca93dd070f4f081625931735ce810507b8608fc3ad741db7a981a2d859df1e3e`、context digest=`ad2b8c230a8bd13ae30808a0194f92a2e09daf78a5ea04e546ffcc2c1e2e8c71`，V1 decision/outcome 未打开；
- cycle 3 barrier 与单 Agent 动态决策：**已 write-once 接受，6/6 动作 applied、0 veto、0 unprotected lot**。新增闭合 15m 先按冻结 `STOP_FIRST` 执行 SNDK 剩余 CORE stop=`1187.6436` 与 MU TACTICAL stop=`805.55826`，费前已实现分别为 `-18.8762655127... / -13.8200105644...` USDT。Agent 没有把保护成交一律冒充战略失效：MU 精确命中既有 `TRADE_OR_15M_STRUCTURE_ACCEPTS_BELOW_805_8`，episode 正式 `INVALIDATED` 并留下下一小时 replacement 复核；SNDK 最后闭合 4h 仍为 `1235.99`，尚未满足“4h 收在 1191 下且卖压持续”的 hard invalidator，故在 FAILURE=`48%`、PULLBACK=`30%` 下以 `400 USDT` 小 CORE 履行 reentry contract，entry=`1182.526458`、stop=`1170`、checkpoint=`1225.79`、计划成本后损失=`4.75373574398...`、净 RR=`2.99279516942...`。BTC/ETH/SOL CORE 与 HYPE CORE+TACTICAL 保持各自保护；decision digest=`0410b41247a8b81f58437ddb366f0a8ab38720e3facf691d2f9278a26f3343f7`、accepted state digest=`cb9a253cdcca0081f5fffe0706603948057fecee7582d8720eb6b528d99c48e1`、receipt digest=`cfdc38d34e27a05c0a13816a7fe03cf70510efebbce980138d6a53a9b05456dd`；
- cycle 3 成本后状态、对照与报告：**已完成并如实保留当前失败前缀**。Agent equity=`9896.807432891477...`、净损益=`-103.192567108523...`、费前已实现=`-36.745709862206...`、未实现=`-64.985230101249...`、费用=`1.461627145069...`、funding=`0`、gross=`4507.014769898751...`、开放风险=`135.126427655790... / 296.904222986744...` USDT。确定性持续、静态 V1、初始静态持有同点净损益依次为 `-83.684500329591... / -87.128675803894... / -90.946804698348...`，Agent 暂时落后 `19.508066778932... / 16.063891304629... / 12.245762410176...` USDT，不支持当前增量市场价值；3/24 不据此改规则。comparator digest=`32f9f1e34ddab211a82f227b93bc17d6e01ba48544c6c66a9c55ce32f4037667`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0003.md`、SHA-256=`5a6efc58457978dcea0795196ae6edd64ec9f046aad7bcab3eeb752eed09e91a`。checkpoint 已回到 `RUNNING_OUTCOMES_SEALED`、`completed_cycles=3`、`next_cycle_index=4`、无 pending context；唯一在途主任务是 Cycle 4 到期后先做 barrier replay，再完成冻结的首个 4 小时不改规则复盘；
- cycle 4 到期续行与 4 小时数据补充：**已完成，4/24 accepted**。heartbeat=`2026-08-03T12:05:14.985Z` 先复核 checkpoint 后只推进 next cycle 4；实际 decision_at=`2026-08-03T12:07:12.980Z`、迟到 `413` 秒并原样保留。首个 4h cadence 共完成 108/108 个 OKX 请求与 6/6 个新闻查询，全部一次成功、0 retry/0 prior error；每标的增加 hourly taker、global account long/short 与 recent liquidation 窗口。28/30 个尺度形成闭合技术状态，SNDK/MU 1W 因 22 根历史继续 `UNKNOWN`；F 只标记 `UNKNOWN_RECENT_ROWS_ONLY`、`missing_is_zero=false`，top-position ratio 与严格 R 继续 UNKNOWN。acquisition digest=`3a027370d7921f3233b30d950b9dfd078983fbf78bb9907a58035ed1f67bdc26`、context digest=`3384d8ba8dcd7ee1a8afb7b28a37d668fa442fff8a6c924e6dd997ce203d73fd`，全部 `3388` 个 available_at 不晚于 decision_at，V1 decision/outcome 未打开；
- cycle 4 barrier 与单 Agent 动态决策：**write-once accepted，6/6 动作 applied、0 veto、0 unprotected lot**。Cycle 3 的 SNDK 400 USDT 恢复 CORE 先于 `11:29:59.999Z` 以 `1169.649` 保护退出，费前损失=`-4.355913700833...`、退出费=`0.197822043149...`；新增闭合 4h 收于 `1163.6`、跌 `5.85684%`、相对量 `2.0142` 且 recent 买方 quote 仅 `24.98%`，精确满足上一 accepted `4H_CLOSE_BELOW_1191_WITH_PERSISTENT_SELL_PRESSURE`，故 episode 正式 `INVALIDATED`，新 reentry contract=`CANCELLED_BY_STRATEGIC_INVALIDATION`，不再复用旧 geometry。MU 从 `INVALIDATED` 正式 `CLOSED`；BTC/ETH/SOL 保留受保护 CORE，HYPE 保留 CORE+TACTICAL。六标的 TREND/PULLBACK/FAILURE/RANGE 概率依次为 SNDK `1/8/82/9`、MU `1/7/82/10`、BTC `7/36/34/23`、ETH `7/35/33/25`、SOL `5/27/48/20`、HYPE `34/39/11/16`；decision digest=`89ffa56b0c1a96f7e8d80cd531d006b03445cb2c38d3780a78cef57238db70ed`、accepted state digest=`88af2afaad9938d72ff73ffcc46ab00f3599205c9d85a9120b9d33284b0529a5`、receipt digest=`53baf9e6b6b38afdc60422a2910ab852c856f3b34cddc63de3ccf6185f195cfb`；
- 首个 4 小时不改规则复盘与下一状态：**已完成，市场增量不支持但连续状态机制部分支持**。Agent equity=`9888.930145252048...`、净损益=`-111.069854747952...`、费前已实现=`-41.101623563039...`、未实现=`-68.308781996695...`、费用=`1.659449188218...`、funding=`0`、gross=`4103.691218003305...`、开放风险=`130.889242799500... / 296.667904357561...` USDT。确定性持续、静态 V1、初始静态持有同点净损益依次为 `-88.148811928574... / -91.592987402877... / -107.417158100074...`，Agent 分别落后 `22.921042819378... / 19.476867345075... / 3.652696647877...` USDT，当前为四臂最差；MU 探针和 SNDK 重入的市场选择均未获支持。另一方面，跨轮状态、CORE/TACTICAL 分离、barrier、重入履约及硬失效后取消义务按合同工作，已知 V1 的固定目标全平与空仓吸收未重现。未据此修改冻结规则；comparator digest=`8c9fab538bc8fb8abe1b6665f538383c6034a470a8accd0b03a9cfcf12f77285`，完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0004.md`、SHA-256=`0ee197725fccdab60bf0f2f8aa283e925b3b297777dde31fc13e4841abc819eb`。checkpoint=`RUNNING_OUTCOMES_SEALED`、`completed_cycles=4`、`next_cycle_index=5`、无 pending context；唯一在途主任务是等待 Cycle 5 到期后只推进 Cycle 5；
- cycle 5 到期续行与公开数据：**已完成，5/24 accepted**。heartbeat=`2026-08-03T13:03:45.257Z` 先复核 checkpoint 后只推进 next cycle 5；实际 decision_at=`2026-08-03T13:05:31.474Z`、迟到 `312` 秒并原样保留。90/90 个 OKX 市场请求与 6/6 个新闻查询成功，市场请求全部一次成功、0 retry/0 prior error；28/30 个尺度形成闭合技术状态，SNDK/MU 1W 历史不足继续 `UNKNOWN`。本轮非 4h 慢统计周期，hourly aggregated taker、account long/short 与 F supplement 不前向填充而保持 UNKNOWN；acquisition digest=`00a0d58280f3a69a2cfc5b2824f05712b20292b1f13e2d2adb451002bf2e77e4`、context digest=`8463edb0595dbb08bd6b7e01f3994fb08a90664f6c0022cd43321f5077bbfaf1`，全部 `3388` 个 available_at 不晚于 decision_at，V1 decision/outcome 未打开；
- cycle 5 单 Agent 动态决策与状态：**write-once accepted，6/6 动作 applied、0 veto、0 unprotected lot、0 新成交**。SNDK/MU 的 recent 买方 quote 分别改善至 `57.88%/83.10%`，但仍低于新 episode 的恢复门槛，故保持 CLOSED 并执行带下一小时 replacement 观测义务的 WAIT；BTC/ETH/SOL 保留受保护 CORE，HYPE 以 6h `+1.12553%` 排名第一且仍在 1h VWAP 上方，但闭合 1h 未站上 `53.062`、recent 买方 quote 仅 `9.06%`，已有 TACTICAL 足以检验分歧，故 HOLD CORE+TACTICAL 而不继续 ADD。六标的 TREND/PULLBACK/FAILURE/RANGE 概率依次为 SNDK `2/13/72/13`、MU `2/13/68/17`、BTC `9/39/30/22`、ETH `9/40/28/23`、SOL `4/26/49/21`、HYPE `37/40/9/14`；decision digest=`65bc908060b37d62518d1bfeced41230364d6102d1ee108ef54e00ad9c43370d`、accepted state digest=`8c476cce081a2ecd11aaea9d929c823763ab016725ce59d455ad0a309e3e3097`、receipt digest=`2e96c9e8eb723a287835631cc7c6db8c17e88a931b414da24a2e54c1e5d2601c`；
- cycle 5 结果、动作忠实度缺口与下一状态：**完整报告已封存，市场增量仍不支持**。Agent equity=`9898.837502706573...`、净损益=`-101.162497293427...`、费前已实现=`-41.101623563039...`、未实现=`-58.401424542170...`、费用=`1.659449188218...`、funding=`0`、gross=`4113.598575457830...`、开放风险=`130.889242799500... / 296.965125081197...` USDT。确定性持续、静态 V1、初始静态持有净损益依次为 `-79.671607427184... / -83.115782901487... / -92.955303043491...`，Agent 分别落后 `21.490889866243... / 18.046714391940... / 8.207194249936...` USDT。复核发现 HYPE TACTICAL mark-to-entry 已 `+1.178633563373...`，但 accepted 八动作表沿用旧 helper 将 `PARTIAL_TAKE_PROFIT` 误标不可行；该错误未改变 HOLD、成交或账本，write-once Cycle 5 不改写，下一周期必须从实际逐 lot 成本/滑点/费用重算可行集合。comparator digest=`b97995c65b591be19c856ca0b530a2acda23b877beb0a94d4a02530eac4522a9`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0005.md`、SHA-256=`f3f67c30faaadbb706eab29e1765020165a0cb933e028bff97c932d44e7748b8`。checkpoint=`RUNNING_OUTCOMES_SEALED`、`completed_cycles=5`、`next_cycle_index=6`、无 pending context；唯一在途主任务是等待 Cycle 6 到期后只推进 Cycle 6，并在判断前纠正八动作可行性生成而不改冻结政策；
- cycle 6 到期续行与公开数据：**已完成，6/24 accepted**。heartbeat=`2026-08-03T14:04:45.504Z` 先复核 checkpoint 后只推进 next cycle 6；实际 decision_at=`2026-08-03T14:06:23.009Z`、迟到 `363` 秒并原样保留。90/90 个 OKX 市场请求与 6/6 个新闻查询成功，市场请求全部一次成功、0 retry/0 prior error；28/30 个尺度形成闭合技术状态，SNDK/MU 1W 历史不足继续 `UNKNOWN`，非4h慢统计字段不前向填充。首次采集已写入唯一context但终端完成输出晚于首次状态读取，同命令复核被write-once边界以`CYCLE_CONTEXT_ALREADY_EXISTS`拒绝，未覆盖或拼接数据。acquisition digest=`920672b1ccfbbafdee17a1d3957af3a502954a0e7b1afc273afb5060b7d94d30`、context digest=`a6132887e35bfa6ef1e54404d9a432017bc203daa13d9b53055fc60fd6ec002b`，全部`3388`个available_at不晚于decision_at，V1 decision/outcome未打开；
- cycle 6 单Agent动态决策：**write-once accepted，9/9动作applied、0 veto、0 unprotected lot、0新成交**。BTC闭合1h高量收复`63099.9/VWAP`，TREND升至`42%`并从CHALLENGED恢复ACTIVE，CORE stop由`61986.48`上移至`62227`；SOL闭合收复`73.18/VWAP`，FAILURE由`49%`降至`15%`、状态恢复ACTIVE，CORE stop由`71.62`上移至`72.27`；HYPE闭合突破`53.062`、6h排名第一，TREND升至`52%`，TACTICAL stop由`51.86`上移至`53.0`，在冻结滑点/退出费后可锁约`+1.5727 USDT`且保留`54.4643`目标，CORE `50.99`不变。SNDK虽高量收复`1191/1203`，但recent买方quote仅`6.07%`、OI`+8.61%`、basis`-19.95bps`，未满足卖压缓和，旧episode保持CLOSED并绑定下一小时REPLACE+OPEN复核；MU仍未收复`805.8`。六标的TREND/PULLBACK/FAILURE/RANGE依次为SNDK`11/36/35/18`、MU`5/20/55/20`、BTC`42/36/9/13`、ETH`20/47/15/18`、SOL`31/39/15/15`、HYPE`52/31/7/10`；decision digest=`ecb08e8018500f569ece054c8a10c589fcbb24b0abfde9a9b34d514505fbf1cb`、accepted state digest=`606b7d6b581429a3f80e91a374585069c7733a26ee3f384794ee67d4b8a4ddd0`、receipt digest=`f8966766fdab058a8ee1d22bf7ff1159cd70156cadcafbe98064a87b48d866bb`；
- cycle 6 结果、动作忠实度修复与下一状态：**报告已封存，市场增量仍不支持**。Agent equity=`9936.591549704919...`、净损益=`-63.408450295081...`、费前已实现=`-41.101623563039...`、未实现=`-20.647377543823...`、费用=`1.659449188218...`、funding=`0`、gross=`4151.352622456177...`；保护上移使开放计划风险由`130.889242799500...`降至`111.026555032828... / cap 298.097746491148...` USDT，不减仓。确定性持续、静态V1、初始静态持有净损益为`-48.597691669720... / -50.353064421697... / -44.765576072519...`，Agent仍分别落后`14.810758625361... / 13.055385873384... / 18.642874222562...` USDT。Cycle5的HYPE partial误分类已在本轮判断前按真实lot成本纠正为`feasible=true`，比较后选择MOVE_STOP+HOLD而非部分兑现，未改写Cycle5。comparator digest=`b4afc4899c95794b816c673c1b02b5fc6fa0f2b60cba99a6e416c740b829de18`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0006.md`、SHA-256=`fe262b8303fa357dc347371e99161c80beb086993d3ad7db67b9a84f234077cc`。checkpoint=`RUNNING_OUTCOMES_SEALED`、`completed_cycles=6`、`next_cycle_index=7`、无pending context；唯一在途主任务是等待Cycle7到期后只推进Cycle7，重点裁决SNDK replacement与三项新保护的后续结果；
- cycle 7 到期续行与公开数据：**已完成，7/24 accepted**。heartbeat=`2026-08-03T15:04:15.603Z` 先复核唯一 run 的 checkpoint/status 后只推进 next cycle 7；实际 decision_at=`2026-08-03T15:07:00.174Z`、迟到`400`秒并原样保留。90/90个OKX市场请求与6/6个新闻查询成功，全部市场请求一次成功、0 retry/0 prior error；28/30个尺度形成闭合技术状态，SNDK/MU 1W历史不足继续`UNKNOWN`，非4h慢统计字段不前向填充。market context中3388/3388个`available_at`不晚于decision_at，acquisition digest=`4dd896f5cbf019ed03987763e724eae211bc18819f7ba6790f064f1f9483c818`、context digest=`f2c11f99cf2afe0b6c8ab172eea650651094fd60b9f29e2946f18a498b8b3997`，V1 decision/outcome未打开；
- cycle 7 barrier、replacement与单Agent动态决策：**write-once accepted，8/8动作applied、0 veto、0 unprotected lot**。确定性重放仅记录BTC CORE在`2026-08-03T14:44:59.999Z`触及`63779.8`管理点，0 stop/0 target；Agent没有固定全平，而把BTC stop从`62227`上移至`63063.2`、下一checkpoint=`64407.5`并HOLD。SNDK闭合1h收`1261.88`、保持`1203/VWAP`上且recent买方quote由`6.07%`改善至`61.31%`，因此旧episode-001保持CLOSED、以新episode-002和全新geometry建立`700 USDT` CORE：entry=`1256.021154`、stop=`1221.95`、checkpoint=`1320.77`、计划成本后损失=`19.883087812349...`、净RR=`1.778772496945...`。MU闭合1h收`828.82`并越过`805.8/814.3/824.62`，但post-close买方quote仅`6.29%`、OI`-5.13%`，故旧episode保持CLOSED并以新CHALLENGED episode-002建立`500 USDT` TACTICAL：entry=`822.284424`、stop=`807.2`、target=`849.44`、计划成本后损失=`9.814855213651...`、净RR=`1.630591617711...`。HYPE TACTICAL stop由`53.0`上移至`53.363`且保留`54.4643`target，CORE不变；ETH/SOL HOLD。decision digest=`6b4c157804d339d0dd82436c4668c95551b89aa3199cbf31316ed336ec02897d`、accepted state digest=`ad341de41e4627f75ff99321603e18ca78f97e4dc7fd125a0eacf882e0340f82`、receipt digest=`d319ea2eafa2576327196465162a420af1a3a25d68e88d4bec0d89cfb88ca196`；
- cycle 7 结果、对照与下一状态：**完整报告已封存；连续状态问题获得动作层修复证据，市场增量仍未获支持**。Agent equity=`9971.054351150784...`、净损益=`-28.945648849216...`、费前已实现=`-41.101623563039...`、未实现=`+14.415423902041...`、费用=`2.259449188218...`、funding=`0`、gross=`5386.415423902041...`、开放名义stop风险=`125.797140334277... / cap 299.131630534524...` USDT。确定性持续、静态V1、初始静态持有净损益为`-27.854999088264... / -28.622323740447... / +4.820467367623...`，Agent仍分别落后`1.090649760953... / 0.323325108770... / 33.766116216839...` USDT；新仓刚建立，不能宣称replacement判断成功。comparator digest=`9bf64c2b4c2b2a769657e1feb4d3b3d05a826535fa8838b2329ca80282585147`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0007.md`、SHA-256=`b2c195a5051419174c162846058bc0c5def22c7dfbf1d7ecd08b6269a1cdd8ca`。checkpoint已回到`RUNNING_OUTCOMES_SEALED / completed_cycles=7 / next_cycle_index=8 / no pending context`；唯一在途主任务是等待Cycle8到期后先重放两笔replacement及BTC/HYPE新barrier，再完成第二个4小时不改规则复盘；
- cycle 8 到期续行与四小时公开数据：**已完成，8/24 accepted**。heartbeat=`2026-08-03T16:04:45.860Z` 先核对唯一 run 的 checkpoint/status 后只推进 next cycle 8；实际 decision_at=`2026-08-03T16:07:52.112Z`、迟到`452`秒并原样保留。本轮为4h补充周期，108/108个OKX市场请求、venue time及6/6个新闻查询成功，全部市场请求一次成功、0 retry/0 prior error；每标的18/18项，增加hourly taker、global account long/short与recent liquidation window。28/30个尺度形成闭合技术状态，SNDK/MU 1W因22根历史不足继续`UNKNOWN`；F仅为`OBSERVED_RECENT_API_WINDOW / history completeness UNKNOWN / missing_is_zero=false`，top-position ratio与严格R继续UNKNOWN。market context中3394/3394个`available_at`不晚于decision_at；acquisition digest=`ac9abd82233d3de0202eeeae1c2276696fb81038b6e44f28fdab8d14b9e77b7c`、context digest=`2855a474dd7832b13d1fdd01ff4b174f620afaba2124f7f934f3a5a6b2ce9087`，V1 decision/outcome未打开；
- cycle 8 barrier、funding与单Agent动态决策：**write-once accepted，9/9动作applied、0 veto、0 unprotected lot**。MU Cycle7 replacement TACTICAL在`2026-08-03T15:29:59.999Z`触发`807.2` stop，以`806.95784`成交，费前损失`-9.319514971136...`、含双边费后`-9.814855213650...` USDT；但最终闭合1h从`804.94`收回`815.36`、高于战略invalidator，当前mark=`820.46`，故episode保持CHALLENGED并以全新geometry、更小`350 USDT` TACTICAL重开：entry=`820.624092`、stop=`803.8`、target=`849.44`、成本后最坏损失=`7.624761785083...`、净RR=`1.565160242895...`。SNDK新闭合4h `+7.859% / RVOL5.441 / TRANSITION`且双尺度买流改善、OI转`-3.27%`，故保留`700 USDT` CORE并增加独立`400 USDT` TACTICAL：entry=`1264.112772`、stop=`1238.8`、target=`1320.77`、成本后最坏损失=`8.523189754150...`、净RR=`2.055443981356...`。HYPE mark进入`54.4643`目标区后只退出全部TACTICAL、成本后约`+15.9442 USDT`，CORE stop由`50.99`上移至`52.58`并HOLD至`55.536`；BTC/ETH/SOL HOLD。16:00已实现funding合计`-0.195961668090...` USDT已按开放lot写入；decision digest=`a803756d339ae0e78a7891a393478e8880329dfac1811ae915605e0bf4592004`、accepted state digest=`f74427d208723467f643a61cbe86a84f18c757970b32a5faaf97753447ef490d`、receipt digest=`e5f84e6621de3731a6e7c2937a4dcda6dcaf719445ab5208783d1c65385ccc9a`；
- cycle 8 第二次四小时不改规则复盘、对照与问题裁决：**报告已封存；连续状态和分层动作获得支持，市场增量仍不支持**。Agent equity=`9975.958748575908...`、净损益=`-24.041251424092...`、费前已实现=`-33.917222705302...`、未实现=`+13.209974337947...`、费用=`3.138041388647...`、funding=`-0.195961668090...`、gross=`5135.209974337947...`、开放stop风险=`107.572740574107... / cap299.278762457277...` USDT。确定性持续、静态V1、初始静态持有净损益依次为`-22.329345527475... / -19.857993306726... / +14.792189285404...`，Agent仍落后`1.711905896617... / 4.183258117366... / 38.833440709496...` USDT且最大回撤最高，不能宣称市场有效。8轮共63项selected/applied、0 veto，state/action fidelity failure均为空；但发现action schema缺少`REENTER_TACTICAL`，MU只能以`OPEN_TACTICAL`物理重开，正式重入指标会漏计；HYPE最后闭合15m high=`54.43`未触及target、却因decision mark=`54.545`以`54.534091`退出，较真实resting target可能约高估费前收益`0.661 USDT`，两项均不改写本轮并留待terminal审计。comparator digest=`f3e4c58fd2563d4930dabe7bd83175327ff5d6d1764e653a4101cbf422d99cb2`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0008.md`、SHA-256=`6c546a2e3206f08c49d6ed999550990484d1eed215014ee41d8f0a7b75c0ce12`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=8 / next_cycle_index=9 / no pending context`；唯一在途主任务是等待Cycle9到期后只推进Cycle9，先重放SNDK/MU新barrier与HYPE CORE管理点，不前向填充Cycle8慢数据；
- cycle 9 到期续行与公开数据：**已完成，9/24 accepted**。heartbeat=`2026-08-03T17:03:49.921Z` 先核对唯一 run 的 checkpoint/status 后只推进 next cycle 9；实际 decision_at=`2026-08-03T17:05:30.657Z`、迟到`311`秒并原样保留。OKX市场请求`89/90`成功，SNDK/BTC/ETH/SOL/HYPE各`15/15`，MU `14/15`；唯一失败为MU `funding_history`的`CURL_EXIT_35 / LibreSSL SSL_ERROR_SYSCALL`，其instrument/mark/closed15m/current funding与其余硬输入完整，历史funding保持UNKNOWN且不补零、不重试、不前向填充。6/6新闻标题元数据查询成功，原始行数`1/1/8/6/8/8`、PIT去重后可引用`1/1/5/5/5/5`；非review的hourly taker、global account ratio、F补充保持UNKNOWN，严格R继续UNKNOWN。market context中`3385/3385`个`available_at`不晚于decision_at，最晚`2026-08-03T17:05:23.352Z`；acquisition digest=`098415557be4bf4e4007aaa23fa0767de86d6ca2c9465d5874f7f7bf72966ab4`、context digest=`15bac45af3d719b2533850696ced3f2ec0550940516cab032ee50fe5f30bb4f9`，V1 decision/outcome未打开；
- cycle 9 单Agent动态分析与动作：**write-once accepted，9/9动作applied、0 veto、0 unprotected lot**。本轮无新增barrier/funding事件。SNDK 1h close=`1275.64`越过上一`1274.41`交换条件、6h=`+6.928%`排名第一，趋势概率`54→60%`；保留`700 USDT` CORE与`400 USDT` TACTICAL，只把TACTICAL stop `1238.8→1252.8`，CORE stop保持`1221.95`，不增加第三层。BTC上一轮卖流前提被recent买方quote=`98.76%`、OI=`+0.548%`与book imbalance=`+0.8373`反转，但RVOL=`0.789`且`63989.9`未突破，趋势`39→51%`并恢复ACTIVE；保留CORE并增加`300 USDT` TACTICAL probe：entry=`63746.84682`、qty=`0.0047061151`、stop=`63220`、target=`65158`、成本后计划最坏损失=`2.867373638717...`、净RR=`2.210290530002...`。MU recent买方quote仅`24.03%`、OI=`+2.744%`且1h/4h DOWN，保持CHALLENGED并只HOLD小TACTICAL；HYPE趋势`68→70%`但1h RSI=`76.15`、`%B=1.108`，CORE stop `52.58→53.08`、继续HOLD至`55.536`；ETH/SOL受保护HOLD。六标的各四条稳定path、概率均合计100%，下一小时review_by=`2026-08-03T18:05:30.657Z`、路径续期到冻结4h复盘`2026-08-03T20:00:19.280Z`；decision digest=`2f4f300a6dd3cb75a121297048f0ba94150eb2d13c77c6aefc47b02e908f861f`、accepted state digest=`dd7eb122525d143c0e14e92ed3405e0827296c3a7e335fc47a6a4482009d0893`、receipt digest=`3101d9d5ed61cc8d8b695e4b895bf982e73b9aa7bf4c64cca269d303422e65db`；
- cycle 9 账本、对照与裁决：**报告已封存；相对两个交易型基线阶段改善，市场有效仍未证明**。Agent equity=`9981.622259761176...`、净损益=`-18.377740238824...`、费前已实现=`-33.917222705302...`、未实现=`+19.023485523215...`、费用=`3.288041388647...`、funding=`-0.195961668090...`、gross=`5441.023485523215...`、开放stop风险=`98.000351864509... / cap299.448667792835...` USDT。确定性持续、静态V1、初始静态持有净损益依次为`-24.818488952214... / -20.704978232159... / +15.290183524457...`；Agent本截面领先前两者`6.440748713390... / 2.327237993335...`，但仍落后初始持有`33.667923763281...`且最大回撤最高，不能据此宣称理论有效或盈利。BTC新probe尚无future bar，结果保持UNSEEN；MU funding history失败、`REENTER_TACTICAL` schema缺口、Cycle8 HYPE约`0.661 USDT`乐观成交语义继续留待terminal审计。comparator digest=`9230b48deab97267658d58629a316881c48224babf8a88cab33fb0eba3509d8a`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0009.md`、SHA-256=`a9d0a7ca2fba8d813a7d9b2fa1303435bcbbf836da0bbb53a1c5c6dadeaecbe3`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=9 / next_cycle_index=10 / no pending context`；唯一在途主任务是等待Cycle10到期后只推进Cycle10，先重放SNDK `1252.8`、BTC TACTICAL `63220/65158`、HYPE `53.08`、MU `803.8`及其余barrier，再检查BTC probe的首个未来证据；冻结理论、风险、成本、三政策与评价不变；
- cycle 10 到期续行与公开数据：**已完成，10/24 accepted**。heartbeat=`2026-08-03T18:04:46.283Z` 先核对唯一 run 的 checkpoint/status 后只推进 next cycle 10；实际 decision_at=`2026-08-03T18:06:31.813Z`、迟到`372`秒并原样保留。本轮无新增barrier/funding事件；OKX市场请求`90/90`、每标的`15/15`、instrument/mark/closed15m硬输入及6/6新闻标题元数据查询全部成功。Cycle9 MU funding-history TLS失败本轮自然恢复100行，未回补或改写旧轮；原始新闻行数`1/1/8/8/8/8`、PIT去重后`1/1/5/5/5/5`。SNDK/MU 1W仍因22根历史不足为UNKNOWN；非review的hourly taker、global account ratio、F supplement及严格R保持UNKNOWN。market context中`3395/3395`个`available_at`不晚于decision_at，最晚`2026-08-03T18:06:24.537Z`；acquisition digest=`7a63a232de4f2a72f990fc4646674bd1690169415892edefec8c913a92c3ffa6`、context digest=`a9392854d00e3fe040cd509ca2cd29844c8fd6cbeb9624479eb45d86b252fda8`，V1 decision/outcome未打开；
- cycle 10 单Agent动态分析与动作：**write-once accepted，13/13动作applied、0 veto、0 unprotected lot**。SNDK 1h=`+2.890%`、6h=`+12.796%`排名第一、recent买方quote=`80.12%`、OI=`+6.429%`，上一轮`1288`交换条件兑现；趋势概率`60→64%`，保留CORE+TACTICAL并分别把stop `1221.95→1252.8`、`1252.8→1288`，不因接近`1320.77`固定目标全平。MU 1h close=`834.99`越过`830.5`恢复条件、6h=`+6.188%`排名第二，失败前提减弱，episode由CHALLENGED→ACTIVE、趋势`19→46%`；旧TACTICAL stop `803.8→817.25`并新增`250 USDT` TACTICAL：entry=`836.51727`、qty=`0.2988581455`、stop=`824.62`、target=`864.25`、成本后计划最坏损失=`3.877714605342...`、净RR=`2.071841019593...`。BTC盘中high=`64050`但1h close=`63879.9`未闭合越过`63989.9`，只把probe stop `63220→63612`并HOLD；SOL/HYPE CORE stop分别`72.27→72.78`、`53.08→54.04`，ETH HOLD。六标的四条稳定path概率均合计100%，next review=`2026-08-03T19:06:31.813Z`、路径续期到`2026-08-03T20:00:19.280Z`；decision digest=`92f19f24bac3a09560130702cc441a8d2a78263c9777c2194415e769de1ac369`、accepted state digest=`091b5d671562d4c1bed479b37da654c765da6f22e24f07b1bcd58af88cafa150`、receipt digest=`c6b9417bb94a6efce03c786fb341c056d5cd3de28b0813954101da8cc50a9a8f`；
- cycle 10 账本、对照与裁决：**报告已封存；旧V1空仓/固定退出问题在本轮动作上未复现，但完整市场验收未完成**。Agent equity=`10037.856586772674...`、净PnL=`+37.856586772674...`、费前已实现=`-33.917222705302...`、未实现=`+75.382812534713...`、费用=`3.413041388647...`、funding=`-0.195961668090...`、gross=`5747.382812534713...`、开放stop风险=`60.692699961558 / cap300` USDT，运行最大回撤仍`1.110698547%`。确定性持续、静态V1、初始静态持有净PnL依次为`-12.154663065666... / -18.350143206571... / +45.861652737377...`；Agent领先前两者`50.011249838340... / 56.206729979245...`，仍落后持有基准`8.005065964703...`，不能宣称稳定盈利。新MU层尚无future bar；`REENTER_TACTICAL`缺口、Cycle8 HYPE约`0.661 USDT`乐观成交及SNDK/MU静态impact反常符号继续留待审计。comparator digest=`8f670b2a2de514513de01bfc6483a41b456bd0e55bd326b6be663b7e778b379d`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0010.md`、SHA-256=`ea94cc070d540d1f0a31eccc476482c8b4113f021ab6e720c63532c83ad2d8d6`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=10 / next_cycle_index=11 / no pending context`；唯一在途主任务是等待Cycle11到期后只推进Cycle11，先重放SNDK、MU双层、BTC/SOL/HYPE新barrier并读取Cycle10 accepted state，冻结理论、风险、成本、102%初始成本、三政策和评价不变；
- cycle 11 到期续行与公开数据：**已完成，11/24 accepted**。heartbeat=`2026-08-03T19:03:16.471Z` 先核对唯一run的checkpoint/status后只推进next cycle 11；实际decision_at=`2026-08-03T19:05:00.056Z`、迟到`280`秒并原样保留。OKX市场请求`90/90`、每标的`15/15`、instrument/mark/closed15m硬输入及6/6新闻查询全部成功；原始新闻行数SNDK/MU/BTC/ETH/SOL/HYPE=`1/1/8/7/8/8`，PIT去重后`1/1/5/5/5/5`。SNDK/MU 1W仍因22根历史不足为UNKNOWN；非review的hourly taker、global account ratio、F supplement及严格R保持UNKNOWN，HYPE/MU/SNDK/SOL静态impact反常符号降级为弱代理。market context中`3389/3389`个`available_at`不晚于decision_at，最晚`2026-08-03T19:04:54.382Z`；acquisition digest=`253026beee1483e865bab40603373b904dfbf82e00d13e48d548328e8e03445d`、context digest=`c8290842d2cc3bcd4e9b6595cbd5c9652547f30045a9796a894abf81a9847394`，V1 decision/outcome未打开；
- cycle 11 barrier、动态假说与动作：**write-once accepted，8/8动作applied、0 veto、0 unprotected lot**。MU Cycle10新增`250 USDT` TACTICAL在`2026-08-03T18:44:59.999Z`按冻结`824.62` stop成交`824.372614`，费前损失`-3.629529370027...`、双边费用`0.248185235315...`、实际净loss=`3.877714605342...`，与事前planned net loss一致；Cycle8旧`350 USDT` TACTICAL仍在，episode未关闭。MU趋势`46→32%`、回撤`38→51%`成为primary并转CHALLENGED；HOLD旧层且对被止损层选择有义务WAIT，需`817.25`承接、OI稳定和`836.35/849.44`闭合重夺后重比ADD。SNDK/BTC/HYPE因回撤卖流与确认缺失分别把PULLBACK提升至`49/48/50%`，ETH回撤升至`50%`，但CORE/TACTICAL保护未失效，均HOLD而非全平；SOL 1h `+0.37% / RVOL1.359 / high74.26`但未破`74.3`且recent卖量/OI下降，CORE stop `72.78→73.19`后HOLD、不追仓。所有路径在`2026-08-03T20:00:19.280Z`四小时复盘到期；decision digest=`ed1def981d59b5133b0f4c72fe9e02cfd700b85accb55f123eb9591d1287422b`、accepted state digest=`9f90a954b10f0e58f64c0f706f7f8e641c8a25667856c35e6b9b9488574da0a3`、receipt digest=`5032ebb20f46e3479d7793246e9bf47b323ba3870ac4a9c6cc6aebc3ec41fbb3`；
- cycle 11 账本、对照与裁决：**报告已封存；主动敞口回撤成本真实暴露，仍未达到市场验收**。Agent equity=`10006.982316961711...`、净PnL=`+6.982316961711...`、费前已实现=`-37.546752075330...`、未实现=`+48.261257329092...`、费用=`3.536226623962...`、funding=`-0.195961668090...`、gross=`5470.261257329092...`、开放stop风险=`52.602959594220 / cap300` USDT；相对Cycle10峰值当前回撤`0.307578312%`，运行最大回撤仍`1.110698547%`。确定性持续、静态V1、初始静态持有净PnL依次为`-17.885348983142... / -18.926615522304... / +32.528942517068...`；Agent仍领先前两者`24.867665944853... / 25.908932484015...`，但落后持有基准扩大至`25.546625555357...`。本小时Agent损失`30.8743`而持有仅损失`13.3327 USDT`，不能用累计领先交易型基线隐藏主动路径和费用代价。comparator digest=`b5d74805b3d88ae3c36a8ebe5a20ca825c2a889dde3f9e8c1a64e72ba03362f8`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0011.md`、SHA-256=`f931c6c746af9f79f4368456210b848240dd993f0dd359f8afd980bc907f030c`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=11 / next_cycle_index=12 / no pending context`；唯一在途主任务是等待Cycle12到期后只推进第三次冻结四小时复盘，重放全部新barrier、采集direct慢D/L/F与闭合4h，续期或淘汰到期path，冻结理论、风险、成本、102%初始成本、三政策和评价不变；
- cycle 12 到期续行与四小时公开数据：**已完成，12/24 accepted**。heartbeat=`2026-08-03T20:03:46.597Z` 先核对唯一run的checkpoint/status后只推进next cycle 12；实际decision_at=`2026-08-03T20:05:24.773Z`、迟到`305`秒并原样保留。本轮108/108项OKX市场请求、六标的各18/18、instrument/mark/closed15m硬输入、venue time和6/6新闻标题元数据查询全部成功；原始新闻行数SNDK/MU/BTC/ETH/SOL/HYPE=`1/1/8/7/8/8`，PIT去重后`1/1/5/5/5/5`。direct慢字段hourly taker、global account ratio与recent liquidation window可用；F仍为近期不完整窗口、top-position ratio与严格R继续UNKNOWN，SNDK/MU 1W因22根有效闭合bar不足继续UNKNOWN，静态impact反常值未用于决策。market context中`3389/3389`个`available_at`不晚于decision_at，最晚`2026-08-03T20:05:18.430Z`；acquisition digest=`f7fe89d5b52009409a810a09eecbb24ca6ce305f2e551b1892af38219002fa24`、context digest=`9d1134e913cb235629c81661e592264dfc2d765ccb464b24d06d364e28545922`，V1 decision/outcome未打开；
- cycle 12 barrier、动态假说与动作：**write-once accepted，11/11动作applied、0 veto、0 unprotected lot**。SNDK Cycle8 `400 USDT` TACTICAL在`2026-08-03T19:14:59.999Z`按`1288` stop以`1287.6136`成交，费前`+7.436307430964...`、双边费用`0.403718153715...`、实际净盈利`+7.032589277248... USDT`；CORE与episode均未关闭。新4h `+2.75368% / RVOL1.8585`、6h强度第一，但当前卖流和1320.77确认缺失使PULLBACK/TREND=`48/45%`；保留CORE并重建`300 USDT` TACTICAL：entry=`1276.715292`、stop=`1252.8`、target=`1320.77`、成本后计划loss=`6.005027562402...`、净RR=`1.673049944487...`。HYPE测试54.04后4h/1h恢复、趋势`52%`，保留CORE并新增`300 USDT` TACTICAL：entry=`54.3648708`、stop=`54.04`、target=`55.536`、计划loss=`2.181245666089...`、净RR=`2.823787873319...`。ETH CORE stop `1816.77→1850.1`，MU旧TACTICAL stop `817.25→821.8`并对新增层有义务WAIT，BTC双层与SOL CORE受保护HOLD。六标的24条稳定path逐标的概率均合计100%，续期到`2026-08-04T00:00:19.280Z`；decision digest=`0df7fb29162f88056f418846a8d96a37704e0d31c32eb8ccd302033e383e93fe`、accepted state digest=`f0392d04a2456e73759182d86e37c74b16696cb005dbcd47b4063c029222e1fd`、receipt digest=`2b75f1512578b35cd15b3a91615191c136a068c872c513915a4c587ef1ccc3cb`；
- cycle 12 第三次四小时不改规则复盘、账本与对照：**报告已封存；V1状态/分层问题未重现，市场增量仍未通过**。Agent equity=`9992.173305524409...`、净PnL=`-7.826694475591...`、费前已实现=`-30.110444644366...`、未实现=`+26.519656614542...`、费用=`4.039944777678...`、funding=`-0.195961668090...`、gross=`5648.519656614542...`、开放stop风险=`40.449938143325 / cap299.765199165732` USDT；运行最大回撤`1.110698547%`。确定性持续、静态V1、初始静态持有净PnL为`-18.595344862258... / -18.583995183708... / +23.363764705121...`；Agent领先前两者`10.768650386666... / 10.757300708117...`，但落后持有`31.190459180712...`，Cycle11→12相对持有再恶化`5.643833625355... USDT`。SNDK战术退出没有关闭CORE且依新证据重建，固定目标全退、状态丢失、空仓吸收和CORE/TACTICAL混同在本前缀未重现；两笔Cycle12 ADD尚无future bar，市场增量、预测有效和盈利均不能宣称通过。comparator digest=`b4aa82d3a3268bfb93a657ddfcd530296c38ae4d05994643c8fe07e99068c00d`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0012.md`、SHA-256=`84ffb21d650fc171bcfc0f06bd91baeb235c0f44fbeb17c11f0927d3c9af5eb4`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=12 / next_cycle_index=13 / no pending context`；唯一在途主任务是等待Cycle13到期后只推进Cycle13，先重放两笔新TACTICAL和MU/ETH/BTC/SOL全部新barrier，不前向填充Cycle12慢字段；
- cycle 13 到期续行与公开数据：**已完成，13/24 accepted**。heartbeat=`2026-08-03T21:03:16.792Z` 先核对唯一run的checkpoint/status后只推进next cycle 13；实际decision_at=`2026-08-03T21:04:36.551Z`、迟到`257`秒并原样保留。闭合barrier重放为0 fill、0新增funding，九个lot连续。OKX市场请求`90/90`、每标的`15/15`、instrument/mark/closed15m硬输入、venue time及6/6新闻标题元数据查询全部成功；原始新闻行数SNDK/MU/BTC/ETH/SOL/HYPE=`1/1/8/8/8/8`，PIT去重后`1/1/5/5/5/5`。market context中`3389/3389`个`available_at`不晚于decision_at，最晚`2026-08-03T21:04:30.903Z`；SNDK/MU 1W仍因22根有效闭合bar不足为UNKNOWN，非review的hourly taker、global account ratio与F不前向填充，top-position与严格R保持UNKNOWN，静态impact反常值未用于决策。acquisition digest=`0196964cf6ed54ed6035000487d8f913e59c2b3f48aef5de8eeb7a2742420fda`、context digest=`3b22190dec453c97d62fd4e3e95dcad9621762a2d4d86cedcf8f5364d66be97c`，V1 decision/outcome未打开；
- cycle 13 动态假说、动作与风险：**write-once accepted，9/9动作applied、0 veto、0 unprotected lot**。SNDK新TACTICAL首个future 1h low=`1274.49`后收`1293.49`且6h仍第一，但RVOL=`0.3915`、recent买方quote=`9.17%`、OI=`-4.37%`使PULLBACK/TREND=`47/46%`；只把该TACTICAL stop `1252.8→1274.4`，CORE继续保留`1252.8`战略空间。BTC第四次缺少64050闭合接受，PULLBACK/TREND=`50/39%`，TACTICAL stop `63612→63680`而CORE仍为63063.2。MU保持旧TACTICAL并对新增层有义务WAIT；ETH、SOL CORE及HYPE CORE+TACTICAL继续在场，HYPE首future 1h回撤使TREND/PULLBACK=`46/45%`且转CHALLENGED，但54.04未失效。六标的24条稳定path逐标的概率均100%，48项八动作比较完整；五CORE、四TACTICAL全部保留，组合开放风险由`40.449938→35.054398 / cap299.937168` USDT。decision digest=`37da342737231bb045200c1e43881ac0560828152be7a2d908ce6715914174d2`、accepted state digest=`246af3700a2c6785b34873b876100670656d6cc48b0214a900ba6a98e7a1c4bc`、receipt digest=`b285b7221b2f9716f03d26cc3e5acf2316aad794b8f2f3384f044564cb355951`；
- cycle 13 账本、对照与裁决：**报告已封存；本小时相对持有改善，但完整市场验收未完成**。Agent equity=`9997.905597238442...`、净PnL=`-2.094402761558...`、费前已实现=`-30.110444644366...`、未实现=`+32.251948328575...`、费用=`4.039944777678...`、funding=`-0.195961668090...`、gross=`5654.251948328575...`、当前drawdown=`0.398003191%`，运行最大回撤仍`1.110698547%`。确定性持续、静态V1、初始静态持有净PnL依次为`-21.626015426422... / -20.530948853825... / +22.808496691516...`；Agent领先前两者`19.531612664864... / 18.436546092267...`，仍落后持有`24.902899453074... USDT`。Cycle12→13 Agent增加`5.732291714033...`、持有减少`0.555268013604...`，相对持有改善`6.287559727638... USDT`，只支持本小时分层持仓与保护结果，不能证明预测有效或稳定盈利。comparator digest=`2e8ac5bf33d430941579965ea568641aa860c6a95a990a504466307de17ef501`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0013.md`、SHA-256=`202274eda1475ac69a20bab4c2e06037ef517e5ee0e2db40f7df6c8a3dd660a8`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=13 / next_cycle_index=14 / no pending context`；唯一在途主任务是等待Cycle14到期后只推进Cycle14，先重放SNDK/BTC新trail与HYPE/MU/ETH/SOL全部barrier，再采集下一闭合1h/15m和current D/L/C/R，冻结理论、风险、成本、102%初始成本、三政策和评价不变；
- cycle 14 到期续行、barrier 与公开数据：**已完成，14/24 accepted**。heartbeat=`2026-08-03T22:03:47.096Z` 先核对唯一run的checkpoint/status后只推进next cycle 14；实际decision_at=`2026-08-03T22:05:26.296Z`、迟到`307`秒并原样保留。确定性重放产生5个事件：SNDK TACTICAL在`1320.77`精确target成交且CORE只触发management checkpoint、BTC TACTICAL以`63660.896`保护成交、HYPE TACTICAL与CORE均以`54.023788`保护成交；SNDK/BTC CORE没有随战术成交退出，HYPE episode生成`PENDING_AGENT_REVIEW`重入合同。OKX市场请求`90/90`、每标的`15/15`、instrument/mark/closed15m硬输入、venue time及6/6新闻标题元数据查询全部成功；原始新闻行数SNDK/MU/BTC/ETH/SOL/HYPE=`1/1/8/7/8/8`，PIT可引用=`1/1/5/5/5/5`。market context中`3389/3389`个`available_at`不晚于decision_at，最晚`2026-08-03T22:05:20.451Z`；SNDK/MU 1W仍因22根有效闭合bar不足为UNKNOWN，非review慢D/F不前向填充，top-position与严格R保持UNKNOWN，SNDK静态impact反常值未用于决策。acquisition digest=`048a42dd38dd3a7c1c2948b50bea6dc048b9f3df1cd5b575f7b03facef41ef05`、context digest=`700aafefb7bbc0cd627582fa3b601c4a8b9814024e9de8cea3ece112ce92ff22`，V1 decision/outcome未打开；
- cycle 14 动态假说、分层退出与重入：**write-once accepted，11/11动作applied、0 veto、0 unprotected lot；已知V1状态问题在本轮操作语义上未重现**。SNDK真实战术target净得`+10.139816596009... USDT`，6h继续第一而闭合未接受1320.77/1332.53，TREND/PULLBACK=`54/39%`；CORE保留，stop `1252.8→1274.4`、checkpoint重建到1360，战术层WAIT带闭合接受或回撤重建义务。BTC旧战术stop实际净亏`-0.704292206794...`但CORE独立连续；15m下轨外、负funding与低位买流/OI使Agent以`300 USDT`重建TACTICAL，entry=`63468.1911`、stop=`63220`、target=`64050`、成本后计划RR=`1.567512239423...`。HYPE两层保护合计净得`+4.924657133019...`且战略未硬失效；Agent在合同创建后`0.340638`小时以`400 USDT`部分CORE重入，entry=`53.840766`、stop=`53.42`、checkpoint=`54.877`、成本后计划RR=`2.002133658930...`，合同转`FULFILLED`。MU旧TACTICAL stop `821.8→825.8`并对新增层WAIT，ETH/SOL CORE受保护HOLD。六标的24条稳定path逐标的概率均100%，48项八动作比较完整；decision digest=`2cbbd30dff19fb206a0f49cf514289a1f52666ab92a602af4e47c3ef3e92e957`、accepted state digest=`33a770b0b83eff5b1e764201076c8edf6404225ba0e7ab94f8a27dfc73e60f10`、receipt digest=`97e28a7b3b71cc55991fdae21b53bc7c8b8d458c2018da4b6ae3d5cdf06d8fe0`；
- cycle 14 账本、对照与裁决：**报告已封存；连续状态/仓位语义获得直接支持，完整市场验收仍未完成**。Agent equity=`9998.514914697460...`、净PnL=`-1.485085302540...`、费前已实现=`-14.527577254528...`、未实现=`+18.401084265359...`、费用=`5.162630645281...`、funding=`-0.195961668090...`、gross=`4624.401084265359...`、开放stop风险=`34.906989740905 / cap299.955447440924` USDT；5 CORE+2 TACTICAL在场，运行最大回撤仍`1.110698547%`。确定性持续、静态V1、初始静态持有净PnL依次为`-30.430796334017... / -25.246057323073... / +11.492161592219...`；Agent领先前两者`28.945711031477... / 23.760972020533...`，仍落后持有`12.977246894759... USDT`。Cycle13→14 Agent增加`0.609317459018...`、持有减少`11.316335099297...`，相对持有改善`11.925652558315... USDT`，只支持本小时分层退出和重入结果，不能证明预测有效或稳定盈利。comparator digest=`1fa1734e4b3c87f435bd64a5a41e46d453f04607b4ddc681c7f47a65409da09e`；完整报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-20260803t085252z/reports/cycle-0014.md`、SHA-256=`f131e69d63017392dc64e1f218cb57842214e9c128c5fcf103f43ea60d8300d4`。checkpoint=`RUNNING_OUTCOMES_SEALED / completed_cycles=14 / next_cycle_index=15 / no pending context`；唯一在途主任务是等待Cycle15到期后只推进Cycle15，先重放HYPE新CORE `53.42/54.877`、BTC新TACTICAL `63220/64050`、SNDK CORE `1274.4/1360`及其余barrier，冻结理论、风险、成本、102%初始成本、三政策和评价不变；

### 需求变更记录

- 2026-08-03：用户明确授权并要求立即启动新的本地不可执行纸面实验；窗口由此前建议的 72 小时改为 24 小时，复盘由 8 小时改为 4 小时；V1 可比初始仓成本改为 genesis 现价的 102%；要求每次运行详细汇报数据采集、理论来源、推论体系、市场结论、多路径概率、动态假说、操作选择及完整仓位/交易信息，并要求在硬风险内积极检验理论而非保守空仓。本授权只打开本实验的公开数据定时采集和本地纸面写入，不打开账户、凭据、交易接口、订单或资金权限。
- 2026-08-03：用户确认继续并允许为目标适当灵活修正规范，优先解决两次 genesis 暴露的采集问题。授权范围是数据可见性 successor、fresh run 和成功后的本地逐小时任务；不可前视、不可伪造、硬风险与外部交易权限边界不变。

## 二十二、24 小时实验网络中断后的截尾复盘

### 用户最终需要的交付结果

- 因连续约 8 小时网络中断，立即停止 `single-agent-prospective-24h-20260803t085252z` 的后续采集与决策，不补写 cycle 15 以后数据，也不把中断后的市场结果拼接回原窗口；
- 以实际 write-once accepted 边界为准，对已经完成的前瞻实验前缀做全面整理，明确实际覆盖、数据质量、点时完整性、连续状态、市场/情绪分析、路径概率、动作与逐 lot 仓位、风险、成本、模拟成交和三政策阶段性结果；
- 逐项裁决 V1 已知问题在该前缀中是已解决、部分解决、未解决、未验证或被新问题替代，并识别本次新暴露的数据、理论、分析、状态、政策、执行、评价和运行连续性问题；
- 形成一份独立的中断实验复盘报告。结果只能作为 `INTERRUPTED_PROSPECTIVE_PREFIX` 的截尾诊断，不得包装为 24 小时 terminal 原始结果、预测有效性、稳定盈利或交易授权。

### 验收标准

1. 以 checkpoint、manifest、accepted state/decision/receipt、market context、collection receipt、comparator 和逐轮报告为权威，确认最后 accepted cycle、下一未完成 cycle、是否存在 pending/半提交工件及自动任务停止状态；
2. 不调用 `collect-prospective-cycle`、`finalize` 或 `evaluate-prospective` 获取中断后的行情，不修改任何 accepted decision/state、冻结理论、风险、成本、102% 初始成本、三政策和评价；
3. 复核全部 accepted 周期的摘要链、上一 state 绑定、`available_at <= decision_at`、硬输入和数据缺失；数据结论按直接证据、可复算派生、弱代理与 `UNKNOWN` 分级；
4. 量化前缀的净值、已实现/未实现盈亏、费用、funding、最大回撤、开放风险、仓位角色、成交、退出/重入、动作忠实度，以及同条件 STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 阶段性比较；
5. 审查四条稳定路径及概率更新是否真的由新增证据驱动，市场情绪、新闻、订单流、拥挤、流动性和跨市场判断是否具有足够来源与局限说明，不把主观概率称为已校准频率；
6. 明确区分网络中断造成的可用性失败、系统/执行缺陷、理论形式化问题、Agent 分析与政策问题、市场表现和当前无法判定事项；
7. 报告必须指出截尾和非随机缺失对结论的限制，并只给出一个最短、合法、不会后见拼接原窗口的推荐下一步。

### 当前范围与明确不做

- 范围只含 genesis 至最后 accepted cycle 的既有不可执行本地工件，以及为复盘生成的派生统计和报告；不读取或采集最后 accepted decision 之后的 future outcome；
- 不恢复或新建定时任务，不恢复 E0/E0B、`automation-2`，不连接 paper/live、账户、凭据、订单或资金；
- 不为解释本次结果修改作战手册、概率、仓位比例、风险、成本、执行或评价规则，不新建 Agent 集群、数据平台、指标平台或通用审计框架；
- 本轮只做停止边界确认、事实复盘和问题裁决；任何 successor 实验必须使用全新 chronology、run 和事前冻结合同，另行决策。

### 当前主要任务与状态

- 24 小时 heartbeat automation `24h-agent`：**已删除，防止旧指令在中断后继续采集或补写**；
- 权威停止边界：**已确认**。checkpoint 为 `RUNNING_OUTCOMES_SEALED / completed_cycles=14 / next_cycle_index=15`，accepted head=`33a770b0b83eff5b1e764201076c8edf6404225ba0e7ab94f8a27dfc73e60f10`，无 pending context、无 terminal receipt、无 evaluation；cycle 15 及以后不存在正式 context/decision/state/receipt；
- 截尾前缀的数据、状态、动作、风险、成本、路径和三政策全面复算：**已完成**。复算 99 个自摘要/状态绑定均通过，47,429/47,429 个 `available_at` 满足点时边界，84 个 symbol-cycle 的 252 项 instrument/mark/closed15m 硬输入全部成功；1,332 项市场请求成功 1,309、失败 23，420 个时间尺度中 392 个技术状态可用、28 个 SNDK/MU 1W 保持 UNKNOWN。14/24 accepted、3/6 四小时复盘，末态 5 CORE+2 TACTICAL、25 笔 fill、开放 stop 风险 `34.906989740905 / 299.955447440924 USDT`；Agent 成本后净 PnL=`-1.485085302540...`、MDD=`1.110698547%`，领先 STATIC_V1 `23.760972020533...`、领先确定性持续 `28.945711031477...`，但落后初始持有 `12.977246894759... USDT`。费前总边际 `+3.873507010830...` 被费用与 funding 合计 `5.358592313370...` 完全吞噬；该截尾比较不能替代 terminal；
- 已知 V1 问题裁决：**连续 state、CORE/TACTICAL 分层和战术 target 不全平在本前缀获得直接支持；退出后恢复、动态 geometry、重入、情绪与机会成本只获部分支持；调度连续性再次失败，盈利与市场有效性未验证**。Agent 共执行 13 次策略入场和 124 个 applied 动作，未复现全程空仓；SNDK target 后 CORE 保留、HYPE CORE 保护退出后 `0.340638h` 部分重入。`REENTER_TACTICAL` 缺失、cycle 5 partial 可行性误标、cycle 8 HYPE 约 `0.661 USDT` 乐观成交和 cycle 1 lot 合同字段缺口仍成立；
- 新暴露 P0：**已定位**。其一，网络中断没有 interruption/failure receipt，控制任务已删除但 checkpoint 仍为 `RUNNING_OUTCOMES_SEALED`；其二，336 张路径卡强制每标的 sum100，却无互斥完备 partition、`OTHER_PATH`、calibration 或 dependency group，与 Core v2.1 和形式化审计的 ordinal-support 边界冲突；其三，672 张八动作卡中 576 张 best/failure case 为通用模板，84/84 个标的周期给八动作使用相同 path set，至少 23 张 EXIT 卡把 TREND_CONTINUATION 写成有利过程，字段完整不等于真实反事实比较。数据层另暴露 recent 100 trades 实际覆盖 `0.013–60.002s` 的不等时间窗、严格 R 0/84、F/拥挤稀疏、headline-only 和 signed impact 语义异常；
- 独立中断复盘报告、问题分级和唯一下一步：**已完成**。报告=`audits/2026-08-04-prospective-24h-network-interruption/POSTMORTEM.md`，SHA-256=`84561dd5fd9d8420304abdf461fe67f9d8a03fac9e470a2e1a5678040d8a7202`。唯一推荐是不得恢复旧 run；先做只包含“中断失败关闭、理论合法的序数路径/依赖去重、真实八动作路径反事实”的最小 successor 合同，再由用户另行确认是否从新 genesis 启动新 24 小时窗口。

### 需求变更记录

- 2026-08-04：用户确认网络问题造成约 8 小时连续性中断，原 24 小时实验被迫提前结束，要求对已经进行的实验做全面复盘、整理并确定暴露问题。该变更终止原 run 的后续采集和 terminal 路径，只授权对已接受前缀做只读诊断与派生报告，不授权补数据、拼接窗口或重启实验。

## 二十三、理论符合性修复与深层复盘

### 用户最终需要的交付结果

- 解决中断前缀及 V1 延续暴露出的所有可定位代码、合同和作战指导问题；从市场金融、证据认识论、连续策略状态、仓位政策、风险、成本、撮合和单 Agent 设计角度形成更深层复盘；
- 使后继单 Strategy Agent 的输入、推论、竞争路径、动作比较和状态提交能够机器证明“按 Core v2.1 的边界工作”，而不是仅有字段齐全或报告写了理论引用；
- 保留 Agent 对开放市场解释和可行域内选择的自由，确定性代码只拒绝前视、伪证据、状态冲突、风险超限、执行语义冲突和理论合同违规，不预选方向或以谨慎名义删除加仓、持有、重入；
- 原中断 run 只写入一个绑定最后 accepted head 的失败关闭回执，不补写 cycle 15 以后市场、决策或 outcome，不改变任何 accepted decision/state 或冻结规则；所有研究修复进入全新 successor 合同，尚不启动新纸面窗口。

### 验收标准

1. 原 run 形成 write-once interruption receipt，绑定 manifest、最后 accepted state、`completed=14 / next=15`、中断原因、未知发生时刻和未完成周期；checkpoint 原子切换为不可继续的 `INTERRUPTED_OUTCOMES_SEALED`，重复调用幂等，`open/collect/finalize/evaluate` 不得继续；
2. 路径合同回归 Core v2.1 §16：机制允许并存，稳定 path identity 保留；每条使用 `DOMINANT / SUPPORTED / PLAUSIBLE / WEAK / INVALIDATED / UNKNOWN` 序数支持，必须包含 residual `OTHER_OR_UNKNOWN`；未经事前冻结的互斥完备 partition、OTHER、依赖去重和校准证明时禁止 `probability_pct`、sum-to-100 或伪概率 top-path；
3. 每条关键证据带 `evidence_id / available_at / perspective_id / dependency_group / target_ids / direction / ordinal_strength / quality / source_version`；同一 dependency group 对同一目标只能贡献最大绝对序数增量，稳定 evidence-id 破同值，不能把同源价格、指标和文字解释重复计票；
4. operational lead 与 runner-up 只表示当前行动排序，并明确 `UNKNOWN_NO_VALID_COMPETITION_SET` 边界；路径选择必须说明新增独立证据、交换条件、最脆弱前提和 residual/unknown，不能把排名解释为预测概率；
5. 八类动作比较必须对 operational lead、runner-up 和 residual/unknown 分别写明仓位影响、路径兑现过程、失败过程、成本风险与机会成本；拒绝八动作复制同一模板、把对已有多头有利的趋势延续机械写成 `EXIT` 有利过程，或宣称不可行但没有具体硬约束；
6. 增加 `REENTER_TACTICAL`，并让战术退出后的恢复语义、重入延迟和 lot role 可真实记录；Genesis 的每个初始 lot 在首轮 Agent 输入前已有完整 role、父 episode、风险预算、保护、checkpoint/target、退出意图与期限，不允许首轮 accepted 后才补齐；
7. 自动 barrier 与 Agent 市场动作保持互斥执行语义：已登记 tactical target 按逐 15m barrier 价格成交，不能因 Agent 下轮市价退出取得更优价；Agent 动态取消/替换目标必须在目标触发前形成 accepted state；
8. recent trades 报告真实首末时间、覆盖秒数、请求条数、固定条数而非固定窗口，以及 `cross_cycle_comparable=false`；盘口冲击以有效 bid/ask midpoint 为基准并输出非负 buy/sell adverse impact，空/交叉簿保持 UNKNOWN；严格 R、稀疏 F/C、headline-only 继续保持 UNKNOWN/弱代理；
9. funding 明确称为“公开 realized rate 加闭合 15m 成交价代理的模拟应计”，不得把代理称真实结算 mark；SNDK/MU 的股权参考衍生品与 BTC/ETH/SOL/HYPE 的连续加密衍生品使用各自冻结时间尺度职责，不声称一套通用周期角色适配所有标的；
10. 风险验证至少覆盖一条真实可行新风险动作和一条超 symbol/portfolio/gross cap 的明确 veto，证明内核既不预删合法动作也能拒绝越界；开放/挂单风险按当前 mark 到含止损滑点的 fill 加退出费计量，模拟 funding 进入有效权益但不得把 cap 抬高到初始权益以上；证据标签固定为 `PRACTICAL_SINGLE_AGENT_JUDGMENT`，不得冒充模型版本、token 或生成过程可复现证明；
11. 聚焦测试必须证明旧 accepted 工件摘要不变、旧 run 不可续写、successor 决策拒绝伪概率/重复依赖/通用动作模板/语义倒置，并接受有区别的序数路径、真实路径条件反事实、合法持有/加仓/战术重入；
12. 深层复盘逐项将问题裁决为“已解决 / 部分解决 / 结构已解决但市场未验证 / 数据不可判 / 未解决”，并明确工程理论符合性不能替代新未见 terminal 市场结果、盈利能力或真实交易许可。

### 当前范围与明确不做

- 当前只修改既有单 Agent context/validator、公开数据正规化、状态/撮合边界、CLI 中断封存、冻结作战手册与 successor 模板，以及直接相关聚焦测试和一份深层复盘；不创建 Agent 集群、Critic、transport、插件、指标平台、通用概率平台或第二决策中心；
- 不修改 `CORE_TRADING_THEORY_v2_1.md`、V1、旧 accepted decision/state、旧逐轮报告或旧冻结合同，不读取/采集 cycle 15 以后 outcome，不以已见价格选择方向、阈值、CORE 比例、stop、target、风险或评分；
- 不恢复 automation、E0/E0B、paper/live，不访问账户、凭据、订单或资金；新 24 小时窗口需要在本轮修复和冻结完成后另行确认；
- “解决全部已知问题”指解决当前证据能定位的实现、形式化和运行关闭缺陷；完整重入表现、跨 regime 预测、成本后盈利和稳定市场有效性只能由新的连续未见实验验证，不能靠代码宣称解决。

### 当前主要任务与状态

- 冷启动权威文档、HEAD、干净工作树和旧实验停止边界：**已完成核对**；本轮从 HEAD=`df416eeba0208d7e26ba7e4c18d9ecc98705b5d6` 开始，不覆盖用户变更；
- 本节需求、理论冲突和验收边界：**已完成记录**；
- 中断失败关闭、序数竞争路径/依赖账本、真实八动作反事实、战术重入、Genesis 合同、数据与执行语义修复：**已完成**；旧 run 保持 `completed=14 / next=15`，中断回执 digest=`0917660fc3f5acfed5a55c37c73a0e58248a342eb18e6238c31eac41f5415e25`；
- 聚焦验证、successor 冻结和深层市场/Agent 复盘：**已完成**；35 项本切片、243 项 Theory Paper V2 相邻回归和 25 项旧 market/theory/inference 回归通过；successor 保持 `start_authorized=false`，深层复盘见 `audits/2026-08-04-theory-conformance-successor/DEEP_REVIEW.md`，SHA-256=`7b5b63e3e6462b8d14b509291347bce67c023647f88c33364007ab3a900a77e7`；
- 新公开市场实验、automation、paper/live/账户与资金操作：**明确不做**。

### 需求变更记录

- 2026-08-04：用户要求解决全部已知问题，并从市场金融和 Agent 设计角度加深复盘，确保当前 Agent 真正遵循竞争路径与 Core 理论。该要求以 Core v2.1 的证据依赖、序数支持和无有效竞争集边界纠正上一版强制 sum-to-100 概率要求；只授权 successor 结构修复、旧 run 失败关闭、验证与复盘，不授权恢复中断窗口或启动新市场实验。
- 2026-08-04：完成旧 run 失败关闭、单 Agent 理论合同 v1.2、数据/撮合真实性、战术重入和完整 Genesis 修复；冻结 v3 作战手册与未授权启动的 v1.3 successor，并完成市场金融、Agent 设计与剩余证据缺口的逐项裁决。工程理论符合性已可验证，市场有效性仍待全新未见窗口检验。

## 二十四、授权启动 v1.3 全新 24 小时未见实验

### 用户最终需要的交付结果

- 用户已确认执行上一节唯一推荐路径：基于已冻结 v1.3 successor，从全新 genesis 和全新 chronology 启动一次完整 24 小时、逐小时决策、每 4 小时复盘的本地不可执行单 Strategy Agent 实验；
- 授权变更只允许把新副本的 `start_authorized` 从 `false` 改为 `true` 并记录本次确认，不修改 Core v2.1、v3 作战手册、实现绑定、风险、成本、102% 初始成本、三政策、评价、停止条件或旧实验；
- 每轮继续输出完整数据采集、质量、理论来源、事实到推论链、序数竞争路径、八动作比较、Agent 选择、逐 lot 仓位/风险/成本、状态推进、重入与复核义务；先封存 raw terminal，再进行结果审计。

### 验收标准

1. 先生成新的授权合同副本，保留 v1.3 未授权模板不变；授权副本精确绑定当前实现与 v3 作战手册，除授权元数据、合同 identity 和 `start_authorized=true` 外不改变研究政策；
2. 使用新的 run_id 和 runtime root；不得复用旧 run 的 genesis、context、accepted state、decision、receipt 或 outcome；
3. Genesis 使用当时公开无凭据 PIT 数据，五个 V1 可比初始 CORE 的成本为当时 mark 的 102%，首轮输入前已有完整 stop、risk budget、checkpoint、role、episode、geometry 和 24h horizon；
4. instrument、mark、闭合 15m 为硬输入；高周期按 direct、官方 fallback、完整 UTC 聚合或 UNKNOWN，不补零、不前视；
5. cycle 1 由当前 Codex 作为唯一 Strategy Agent 读取 frozen context 和 genesis state，提交符合 v1.2 决策合同的真实市场分析，不使用通用模板或伪概率；
6. 每次只推进 checkpoint 指定且已经到期的一个周期；读取上一 accepted state，先重放 barrier/funding，再分析、校验、accept 和复算三政策；
7. 只允许一个与新 run 精确绑定的本地递进任务；它不能恢复旧 automation、E0/E0B、Agent 集群、Critic、transport 或插件平台；
8. 24 个决策周期和 cycle 25 terminal 连续完成后，先封存 raw，再 evaluate 和单独审计；运行中不得根据后来价格修改理论、阈值、仓位比例或评分；
9. 任一硬输入不可得、状态/保护冲突、future outcome 暴露、授权越界或两条合理采集方案失败时失败关闭；
10. 始终保持 `LOCAL_PAPER_RESEARCH_NON_EXECUTABLE / NONE_LOCAL_SIMULATION`，不访问账户、凭据、真实订单或资金，不调用 paper/live 接口。

### 当前范围与明确不做

- 当前只创建授权合同、fresh run、逐周期完整报告与一个精确绑定的新递进任务；不修改已冻结未授权模板和旧中断 run；
- 不把“成功采集/accepted/测试通过”称为预测有效、盈利或生产就绪；
- 不创建 Agent 集群或通用基础设施，不恢复 E0/E0B，不连接账户、paper/live、订单和资金。

### 当前主要任务与状态

- 用户对全新 v1.3 24 小时窗口的单独启动授权：**已确认**；
- 授权合同副本：**已冻结并提交**；路径=`config/theory_paper_v2.prospective_24h.v1_3_authorized_20260804.json`，physical SHA-256=`9349f54fd4e7f339dd7d26a2522c96e4d88d948ae6288b24f2a3b84bb08893c6`，canonical digest=`fe6ed71f456853492aa111517190fe05edd863483ee303ffb14077b92e30510d`；已验证除 identity、授权元数据和 `start_authorized=true` 外与未授权 v1.3 的研究政策完全一致，授权冻结 commit=`55e10069335b6942a2e6c2f17687d87467a0d426`；
- fresh genesis：**已完成**。run=`single-agent-prospective-24h-v13-20260804t100154z`，genesis/decision cutoff=`2026-08-04T10:04:50.094Z`，terminal due=`2026-08-05T10:04:50.094Z`；acquisition digest=`74fd023d28f42a071efa6153f8a5b532a12696cc7d40b6c710efe6e4646217d3`、market context digest=`43e20ec488b3370fc6c3307d1059ef1efed53b882f3b13418640fa8ad91e0747`、manifest digest=`2da95cd49587cdc02da7cba94d2ac895bfd56a04aba2a60eaafdcef7dbef6f03`。六标的 18/18 请求成功、硬输入齐全；五个 102% 成本外生 CORE 在首轮前已有 role、episode、stop、risk budget、checkpoint、geometry 和 24h horizon；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，严格 R 与完整清算历史不补零；
- cycle 1 单 Agent 决策、状态提交与市场动作：**已 write-once accepted**。Agent 在 `4100 USDT` 初始毛敞口下 HOLD SNDK/BTC/SOL/HYPE CORE，MU 以明确的下一小时区间/流量复核义务 WAIT；ETH 因 1W/1D/4H/1H 弱势与小时卖压将 CORE 减半，卖出数量=`0.2694371995775224710624447654`、模拟成交=`1855.348856`、费前实现=`-10.1 USDT`、fee=`0.24995 USDT`，保留半数 CORE 与原 stop，不把风险收缩冒充战略硬失效。6/6 动作 applied、0 veto、0 unprotected lot、0 state continuity/action fidelity failure；decision digest=`8afa4cbef35729c7941a1b05b2f63c692fb14f1bd108c8ae64dba9687e79cd54`、accepted state digest=`ab6772ea2762afe410293a279deb922a49b713b8f4233c937d826ed1c93d2f2a`、receipt digest=`0ff50872d27edfd9bfc405d6f1898619994ce9f9aa292e4e8090ccc436dd54fb`；
- cycle 1 成本、风险、序数路径与同条件对照：**已复算并封存**。Agent equity=`9917.65005`、net PnL=`-82.34995`、费前已实现=`-10.1`、未实现=`-72`、fees=`0.24995`、funding=`0`、gross=`3600`、当前 mark 到 stop 风险=`61.837591713412... / cap 297.5295015 USDT`。STATIC_V1/DETERMINISTIC_CONTINUOUS/INITIAL_STATIC_HOLD 在尚无新时间推进时均为 `-82 USDT`；Agent 因 ETH 主动降险先支付 `0.34995 USDT` 摩擦，不能据此判断市场价值。SNDK/HYPE 的延续为 operational lead，BTC/SOL 的正常回撤为 lead，ETH 失败为 lead、MU 区间为 lead；所有标的保留五条稳定 path_id 与 OTHER，使用未校准序数支持且明确禁止 sum-to-100 伪概率。comparator digest=`2a3b76ed4600a1d5810bc03c689c952af4409ba81f256289a8f94c71ffeaddab`；
- cycle 1 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0001.md`，SHA-256=`e68ee2c11b0aebb7e5e21cb910f682be8cfef0191f47bb520253d5d88e0c2b07`，包含采集与质量、多周期、D/L/C/F/R、新闻、跨市场、理论来源、认识论推论链、五路径序数竞争、八动作、逐 lot、ETH 成交、风险成本、对照与下一义务；
- cycle 2 到期采集与 PIT 硬校验：**已完成**。due=`2026-08-04T11:04:50.094Z`、decision_at=`2026-08-04T11:23:27.076Z`、lateness=`1116 秒 < 90 分钟`；OKX public 市场请求 `90/90`、Google News RSS 查询 `6/6` 成功且均为单次尝试，90 个响应 SHA/request receipt、自 digest、3459 个 `available_at<=decision_at`、六标的 instrument/正 mark/299 根闭合 15M 全部验证通过。acquisition digest=`9c6a939196201c0319d47435a2eeccad78a858120a7dc4c788a3d93eecb40999`、context digest=`4957627fdb6b0d89256f6caa7cc21964f52461ee4171ba2b6acb728c6f73600d`、agent context digest=`b2f369fe0a50a5b77535e472576fd97238f7684140d852cd9c8e2ec22428f473`；SNDK/MU 1W、小时 taker、账户 L/S、完整清算和严格 R 继续 UNKNOWN，不补零、不启动不必要 fallback；
- cycle 2 单 Agent 决策、纯验证与 write-once accept：**已完成**。SNDK 的 `TREND_CONTINUATION` 保持 lead，并在原 CORE 外增加 `250 USDT` PROBE TACTICAL：entry=`1358.601666`、quantity=`0.184012728864...`、stop=`1315.8`、reward=`1436.18`、max horizon=`2026-08-04T15:23:27.076Z`、planned net loss=`8.1947142009...`、net reward/risk=`1.7106469971...`，0 risk veto；MU 虽由新增 1H/15M、买流、OI 与盘口把 trend 升为 lead，但因尚无闭合 1H 站稳 `866.27` 且小时流 UNKNOWN，继续带明确错失成本和下一小时重比义务的 WAIT；BTC/ETH 半 CORE/SOL/HYPE 均 HOLD。六动作全部 APPLIED；decision digest=`3d841c14ae23bff5a9e837c5bf779523ea7b3caab622078c06b41e32157ce369`、accepted state digest=`efee39b1c82c97fd3b1dd4b719866c23ec6c5c8b032cec4030269684a6b2e8f7`、receipt digest=`8f01c821676ae2d33ba8995f6c78db2922f5b52114bef41f620c842484e1397c`；accepted Cycle 1 工件、冻结理论/手册/风险/成本/评价均未改写，V1 decisions/outcomes 仍 sealed；
- cycle 2 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9956.903344405782...`、net PnL=`-43.096655594217...`、realized before cost=`-10.1`、unrealized=`-32.621705594217...`、fees=`0.37495`、funding=`0`、gross=`3889.378294405782...`、open risk=`109.285600320104... / 298.707100332173... USDT`、unprotected lots=`[]`。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 在尚无各自 barrier/target/reentry 触发时均为 `-39.017838929790... USDT`，Agent 暂落后 `4.078816664427... USDT` 且毛敞口更低；只完成 2/24，不据此评价理论或调参。comparator digest=`93340b47cfd1bdd6d6c4e8b22784500d32dcfee78d428f57b6383a03e0a116c1`；
- cycle 2 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0002.md`，SHA-256=`86bad10ee422263912ba1ea6c6adc746fae4fd26c7f835033a1fdd7f54a01c4d`；410 行覆盖采集来源/失败与 UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、事实到 POLICY 链、五条稳定 path_id 的序数支持/反证/expiry/switch/hard falsifier、真实 lot 下八动作三路径反事实、SNDK 新 lot、逐 lot stop/checkpoint/risk/funding/fee、三政策和下一轮义务；
- cycle 3 到期采集、来源失败与 PIT 硬校验：**已完成**。due=`2026-08-04T12:04:50.094Z`、decision_at=`2026-08-04T12:23:11.194Z`、lateness=`1101 秒 < 90 分钟`；venue-time 第一次因 LibreSSL `SSL_ERROR_SYSCALL` 失败后按冻结边界第二次成功，没有重跑整轮。OKX public 市场请求 `90/90` 成功且六标的各 `15/15`；Google News RSS `5/6` 成功，SNDK 成功但 0 行、HYPE 因 SSL EOF 为 `FAILED_UNKNOWN`。90 个 response SHA、91 个 request receipt self-digest、acquisition/attempt/context 摘要和 `3455` 个 `available_at<=decision_at` 全部通过；六 instrument 均 live、mark 为正、各 299 根闭合 15M。acquisition digest=`5d3526e0ef2cbad654b4913aa9a8df0f740e8ccc487f1f368e486b117ff12edb`、context digest=`fd84edf7b9f2ead6a6b910a6ab95f5ceb2bdff7d58b1efb29198ae30b67709da`、agent context digest=`add969fdb5ec9d8d88c66d6c66171fe21c220177869f7247e46c7f186ac8128c`；SNDK/MU 1W、小时 taker、账户 L/S、完整清算和严格 R 继续 UNKNOWN，不补零；
- cycle 3 单 Agent 决策、barrier 重放、纯验证与 write-once accept：**已完成**。确定性 pre-open 重放无 stop/target/funding 事件；SNDK TACTICAL 新增闭合 15M 区间 `1352.40–1371.10`，未触及 `1315.8/1436.18`。Agent HOLD SNDK CORE+TACTICAL、BTC/ETH 半 CORE/SOL/HYPE CORE；MU 的旧 `866.27` 价格门槛虽满足，但 fresh recent-trades 买入报价占比仅 `0.121764`，原价格+OI+主动流联合条件只部分履约，因此继续带错失成本与 `13:23:11.194Z` 重比义务的 WAIT。六动作全部 APPLIED、0 veto、0 unprotected lot；五条稳定 path_id、8 动作×lead/runner/OTHER、PIT lineage、prior consumed dependency 去重与非法概率字段纯校验通过。decision digest=`b91dad5cc2e7236f94549a3a521e1fb3a81b33793058beba3d876c5a981cb754`、accepted state digest=`0a0e04b157f3d294f47b8ef5e7e3f92c59acfac27c8a66db81f8b08ee86ab3ca`、receipt digest=`bc82f142dbb1c3d76ba18b35670f7f7edd05d4c2b919cc330e8685e52b3b3bdd`；V1 decisions/outcomes 仍 sealed；
- cycle 3 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9964.266359584012...`、net PnL=`-35.733640415987...`、realized before cost=`-10.1`、unrealized=`-25.258690415987...`、fees=`0.37495`、funding=`0`、gross=`3896.741309584012...`、open risk=`116.648615498334... / 298.927990787520... USDT`、unprotected lots=`[]`。STATIC_V1 与 INITIAL_STATIC_HOLD 均为 `-31.727456975287... USDT`；DETERMINISTIC_CONTINUOUS 按冻结规则对 SNDK/HYPE 产生两次 partial 后为 `-30.768116383815... USDT`、fees=`0.066720506086...`。Agent 暂落后 STATIC `4.006183440700... USDT`、落后 continuous `4.965524032171... USDT`；仅 3/24，不据此调参或裁定理论。comparator digest=`c24cf6620df482b9b59a9d0c06e017dcffab3f843566644a2dc4ee85e897b94e`；
- cycle 3 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0003.md`，SHA-256=`4d2676419f251061c1acce15eb67e5a437fb5c1804e2f4f924ae45a6442f9349`；430 行覆盖采集尝试/来源/失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论和认识论链、五路径序数支持/反证/expiry/switch/hard falsifier、六标的八动作三路径反事实、逐 lot parent/role/quantity/cost/stop/target/checkpoint/horizon/risk/funding/fee、三政策和 Cycle 4 复盘义务；
- cycle 4 到期采集、review 数据与 PIT 硬校验：**已完成**。due=`2026-08-04T13:04:50.094Z`、decision_at=`2026-08-04T13:23:00.725Z`、lateness=`1090 秒 < 90 分钟`；正式采集前误输入不存在的 `collect` 子命令被 argparse 在采集启动前拒绝，未写 raw/checkpoint，随后正确 collector 只运行一次。OKX public review-cycle 市场请求 `108/108` 成功、六标的各 `18/18` 且全部单次成功；Google News RSS `6/6` 成功，raw 行数 SNDK/MU/BTC/ETH/SOL/HYPE=`0/1/8/4/8/8`。第一版只读核验沿用普通轮 `90/15` 预期而产生假 count mismatch，按 manifest 的 `108/18` 复核后通过且没有重采。108 response SHA、109 request receipt self-digest、`3459` 个 `available_at<=decision_at`、六个 live instrument/正 mark/各 299 根闭合 15M 全部通过。acquisition digest=`ac2945d566e5781ac334dbe126ab8fa6f37be1e0b0dc793b7b43f6b99e39a2fe`、attempts digest=`2d648cf51854279c77ecc27d12b53b24752450cbb293527840e2f4ffff241c9b`、context digest=`eee606cd04f3736330d62705bb12d4d9f5a5b7f55c2117544622dd6f57c502f7`、agent context digest=`b9b9452e3ef4a962bfbfb422251dfd27ae7918b1664d5727cc5fa4ab45d04737`；SNDK/MU 1W、完整强平历史和严格 R 继续 UNKNOWN，不补零；本 review cycle 的小时 taker/global L-S/liquidation recent rows 只按代理解释；
- cycle 4 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。每标的先消费 Cycle 3 后新增的 4 根闭合 15M；`bar_replay_events=[] / target_events=[] / funding new event=none`，SNDK 新区间 `1351.1–1378.0` 未触及 `1315.8/1436.18`。Agent HOLD SNDK CORE+TACTICAL、BTC/ETH 半 CORE/SOL/HYPE CORE，MU 继续带 `14:23:00.725Z` 复核义务的 flat WAIT。SNDK/HYPE 保持 trend lead；BTC/MU 保持 pullback lead；ETH/SOL 因 fresh 买流与 OI 改善将 trend 升为 runner-up但未完成闭合突破，不回补/不新增。五稳定 path_id、未归一序数支持、8 动作×lead/runner/OTHER、PIT lineage、保护和 competition status 纯验证通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision digest=`575b49be2b20e700c7a60a57baf4d596f83b5dd0acbbda00fc5407e633ac9f6d`、accepted state digest=`4f273c785daf974caad93bdb759d47f906305808e400f05ea43667d21232c30d`、receipt digest=`93e4a83095c15f7e92964a7c9793baa7b69cc0d6103a4c918934083eccf1ce7e`；V1 decisions/outcomes 仍 sealed；
- cycle 4 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9971.393142423371...`、net PnL=`-28.606857576628...`、realized before cost=`-10.1`、unrealized=`-18.131907576628...`、fees=`0.37495`、funding=`0`、gross=`3903.868092423371...`、open risk=`123.775398337693... / 299.141794272701... USDT`、unprotected lots=`[]`。STATIC_V1 与 INITIAL_STATIC_HOLD 均为 `-26.859109696907... USDT`；DETERMINISTIC_CONTINUOUS 累计对 SNDK/HYPE/BTC/ETH/SOL 做五次冻结 partial 后为 `-24.583873829129... USDT`、fees=`0.208253742437...`、gross=`3116.355667727319...`。Agent 暂落后 STATIC `1.747747879721... USDT`、落后 continuous `4.022983747499... USDT`；仅 4/24，不据此调参或裁定理论。comparator digest=`f2c16bc343799452563bc5fc6b8bf25b66d24069ae29c0db787cdb7e1c01909f`；
- 首次四周期不改规则复盘：**已完成并未改任何冻结规则**。Cycle 1→4 的 mark 前缀为 SNDK `+4.1124%`、MU `+1.8819%`、BTC `+0.6432%`、ETH `+0.8282%`、SOL `+0.8339%`、HYPE `+1.6491%`；SNDK TACTICAL 当前未实现 `+2.8684519`、扣 entry fee 后净贡献约 `+2.7434519 USDT`，但 ETH Cycle 1 减半在后续恢复中产生更大少持/摩擦代价，使 Agent 仍比静态低 `1.7477479 USDT`。MU flat 的上涨只记为机会成本、不伪造 PnL；尚无完整 EXIT、stop、target、horizon、reentry 或非零 funding 事件，`reentry_delays_hours=[]`。四轮历史最大 drawdown 约 `0.8234995%`、当前 `0.2860686%`；terminal 后需审查极短 latest-N、新闻检索噪音、SNDK/MU 1W、严格 R/完整 F 与动作判别覆盖，但运行中不修改理论、阈值、风险、成本、三政策、评价、停止条件或时钟；
- cycle 4 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0004.md`，SHA-256=`db27727da4dde3463284302483c5dfbd54228d5caedd16366d6395ea7cc50e1a`；482 行覆盖采集与两项无副作用诊断、来源/成功失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、五路径支持/反证/expiry/switch/hard falsifier、六标的八动作三路径反事实、barrier、逐 lot role/quantity/cost/stop/target/checkpoint/horizon/risk/funding/fee、三政策、四周期路径/动作/ADD/机会差/费用/drawdown/reentry 复盘和下一义务；
- cycle 5 到期采集、ordinary-cycle UNKNOWN 与 PIT 硬校验：**已完成**。due=`2026-08-04T14:04:50.094Z`、decision_at=`2026-08-04T14:23:55.188Z`、lateness=`1145 秒 < 90 分钟`；OKX public 市场请求 `90/90`、Google News RSS `6/6` 成功，六标的各 `15/15` 且全部单次成功、prior error=0。90 个 response SHA、91 个 request receipt self-digest、acquisition/attempt/context 摘要、`3459` 个 `available_at<=decision_at`、六个 live instrument/正 mark/各 299 根闭合 15M 全部通过。acquisition digest=`dc92528ca8d9f1e30fe4a3d4340519e153a1320efeb2bda17016978de375ad62`、attempts digest=`96ba80c6053d1dff962210dc77ccf3c2b0410b558a89e1349a68ea0c4cec530d`、context digest=`70ca912b0d220fa2ed6cf2877eb89a6ef6bebeffb53bdb8b2f1db371c210833f`、agent context digest=`e6b3c02370a90e2c0efcb3c7bf963791d62ca5b88779389956d98837693b8f77`。本轮不是 review cycle，小时 taker/global L-S/liquidation recent rows 没有重采，均保持 UNKNOWN；Cycle 4 值没有携带、补零或当作中性；SNDK/MU 1W 与严格 R 也继续 UNKNOWN；
- cycle 5 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。每标的先消费 Cycle 4 后新增的闭合 15M；`bar_replay_events=[] / target_events=[] / funding new event=none`，SNDK TACTICAL 的 `1315.8/1436.18/15:23:27.076Z` 均未触发。Agent 将 MU 从连续 flat WAIT 切换为 `OPEN_TACTICAL`：250 USDT PROBE、entry=`875.565078`、quantity=`0.285529889532...`、stop=`856.03`、target=`931.04`、max horizon=`2026-08-04T18:23:55.188Z`、planned net loss=`5.898349721098...`、cost-after reward/risk=`2.641726790220...`；ETH 的 failure 升为 lead，`REDUCE_CORE 50%`，fill=`1860.22788`、quantity=`0.134718599788...`、fee=`0.125303647640...`，保留同量 CORE 与原 stop/checkpoint；SNDK CORE+TACTICAL、BTC/SOL/HYPE CORE 均 HOLD。五稳定 path_id、未归一序数支持、8 动作×lead/runner/OTHER、PIT lineage、保护和 competition status 纯验证通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision digest=`b67957092d707dc67481ed6436f1dd97ee4c8e398f0f45933af169843b031b2f`、accepted state digest=`3fa25e771ab3772f478341acdd803dcbf31bf7586b0d0f07b6d4896e7c409e44`、receipt digest=`693e2e0d5562142a8d8c38d50643d4ddd303757a7c782565928e388bb3a2a711`；V1 decisions/outcomes 仍 sealed；
- cycle 5 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9953.230334447270...`、net PnL=`-46.769665552729...`、realized before cost=`-14.492704718384...`、unrealized=`-31.651707186704...`、fees=`0.625253647640...`、funding=`0`、gross=`3885.348292813295...`、open risk=`107.796652492329... / 298.596910033418... USDT`、unprotected lots=`[]`。STATIC_V1 与 INITIAL_STATIC_HOLD 均为 `-47.766547345724... USDT`；DETERMINISTIC_CONTINUOUS 为 `-41.956786465075... USDT`、fees=`0.583581379206...`、gross=`2348.702809189799...`。Agent 当前高于 STATIC `0.996881792994... USDT`、低于 continuous `4.812879087653... USDT`；仅 5/24，不据此调参或裁定理论。comparator digest=`d8ce9b15a0ea29011e427f45931f025d9b16cc8f77268f165284200d70bccc0d`；
- cycle 5 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0005.md`，SHA-256=`021823016002079e7365bfb600747265fd98bfc6ba39c1feff3a5545bf6d3bac`；440 行覆盖采集来源/成功失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、五路径支持/反证/expiry/switch/hard falsifier、六标的八动作三路径反事实、MU 新 lot、ETH reduction、逐 lot role/quantity/cost/stop/target/checkpoint/horizon/risk/funding/fee、三政策和下一义务；
- cycle 6 到期采集、ordinary-cycle UNKNOWN 与 PIT 硬校验：**已完成**。due=`2026-08-04T15:04:50.094Z`、decision_at=`2026-08-04T15:23:34.011Z`、lateness=`1123 秒 < 90 分钟`；OKX public 市场请求 `90/90`、Google News RSS `6/6` 成功，六标的各 `15/15` 且全部单次成功、prior error=0。90 个 response SHA、91 个 request receipt self-digest、acquisition/attempt/context 摘要、`3460` 个 `available_at<=decision_at`、六个 live instrument/正 mark/各 299 根闭合 15M 全部通过。acquisition digest=`6741761107373fa54371ef10ffed9119122e6a60ad9d70153c81d3bef6696c83`、attempts digest=`144795586082c6804e3ba996bc84018644c13948ceb61c90dfcd0733e69d8c1d`、context digest=`94bbaee8b35536596aa19bb0fad6298131e10c1c6912c9dfb0eba9028510b8d9`、agent context digest=`9a9fb5ee709f082fef6e8d564d3fa43599be1dfb33c26b91e39f39a0391a4847`。本轮不是 review cycle，小时 taker/global L-S/liquidation recent rows 没有重采，均保持 UNKNOWN；Cycle 4 值没有携带、补零或当作中性；SNDK/MU 1W 与严格 R 也继续 UNKNOWN；
- cycle 6 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。每标的先消费 Cycle 5 后新增的闭合 15M；`bar_replay_events=[] / target_events=[] / funding new event=none`，SNDK `1315.8/1436.18` 与 MU `856.03/931.04` barrier 均未触发。SNDK TACTICAL max horizon=`15:23:27.076Z` 在 decision_at 前 6.935 秒到期，Agent 以 `1407.108522` role-exact `EXIT_TACTICAL 0.184012728864...`，费前实现=`+8.925878941178...`、fee=`0.129462939470...`，CORE 与原保护保持；该时间退出不是 target/stop 或战略失效，下一轮才可用新 geometry 重比 `REENTER_TACTICAL`。MU 价格扩张但 OI 转 `-3.66000%`，执行 `PARTIAL_TAKE_PROFIT 50%`：fill=`893.181328`、quantity=`0.142764944766...`、费前实现=`+2.514982958239...`、fee=`0.063757491479...`，剩余同量 TACTICAL 保留 `856.03/931.04/18:23:55.188Z`；BTC/ETH/SOL/HYPE CORE 均 HOLD。最终五稳定 path_id、未归一序数支持、8 动作×lead/runner/OTHER、PIT lineage、prior dependency 去重、保护和 competition status 纯验证通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision digest=`34af0c8012fac9894b2eada72f099b9ccfb0e507fc259bbec5d9bb82649cfaac`、accepted state digest=`78ae42e3d2a169c709c7e52330ed1a8624337bb6e12d519614ea0ea137af95eb`、receipt digest=`e3f453ceb23cef26c9308cdb5b6d1f57689663b9f88347bd94409d508b3d49b7`；V1 decisions/outcomes 仍 sealed；
- cycle 6 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9987.859879234446...`、net PnL=`-12.140120765553...`、realized before cost=`-3.051842818965...`、unrealized=`-8.269803867997...`、fees=`0.818474078590...`、funding=`0`、gross=`3533.730196132002...`、open risk=`120.222166749577... / 299.635796377033... USDT`、unprotected lots=`[]`。STATIC_V1 与 INITIAL_STATIC_HOLD 均为 `-20.960425332053... USDT`；DETERMINISTIC_CONTINUOUS 按冻结规则新增 ETH reentry 后为 `-25.079764250309... USDT`、fees=`0.833581379206...`、gross=`2865.829831404565...`。Agent 当前高于 STATIC `8.820304566499... USDT`、高于 continuous `12.939643484755... USDT`；仅 6/24，不据此选优、调参或裁定理论。comparator digest=`20f0c27da728706701cfdc7072ae9a39df7bd4f7226e044c5c03bae64c0dcb41`；
- cycle 6 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0006.md`，SHA-256=`1260a9a7c023ab2e53b69bedb519067e69488f239783456317839bc28777824c`；452 行覆盖采集来源/成功失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、五路径支持/反证/expiry/switch/hard falsifier、六标的八动作三路径反事实、SNDK horizon exit、MU partial take profit、逐 lot role/quantity/cost/stop/target/checkpoint/horizon/risk/funding/fee、三政策和下一义务；
- cycle 7 到期采集、ordinary-cycle UNKNOWN 与 PIT 硬校验：**已完成**。due=`2026-08-04T16:04:50.094Z`、decision_at=`2026-08-04T16:26:08.891Z`、lateness=`1278 秒 < 90 分钟`；OKX public 市场请求 `90/90`、Google News RSS `6/6` 成功，六标的各 `15/15`。90 个 response SHA、91 个 request receipt self-digest、acquisition/attempt/context 摘要、`3466` 个 `available_at<=decision_at`、六个有效 instrument/正 mark/各 299 根闭合 15M 全部通过。acquisition digest=`bbd40a42785e2a239a0a4e87530a6c3dc4f1ce3b06f818f6abd20eb056d66281`、attempts digest=`b5358e23a7aa60dd0edb2e73e771d875aff84bcdae6efe1bd2116d8d788e5d0b`、context digest=`50c169bfb6c95942aa018d97f588b1dab427d293ef88298ecf2988c56546717c`、agent context digest=`3b4d3dc1c248b2b5791e734a73978707af3cf32778ea787af69fb626e315e2e9`。本轮不是 review cycle，小时 taker/global L-S/liquidation recent rows 没有重采，均保持 UNKNOWN；SNDK/MU 1W 与严格 R 也继续 UNKNOWN；
- cycle 7 barrier/funding 重放、唯一 Agent 判断与 write-once accept：**已完成**。新增闭合 15M 没有触发 stop/target；确定性代码先重放六个 16:00 UTC funding proxy，SNDK/MU/BTC/ETH/SOL/HYPE 依次为 `+0.254077836703 / 0 / -0.086943974053 / +0.004044560091 / -0.070229501514 / +0.003569099738 USDT`，净额 `+0.104518020965 USDT`。Agent 对六标的均选择 HOLD，但逐标的理由不同：SNDK 的真实 tactical exit 让 `REENTER_TACTICAL` 状态可行，因 1H 未闭合站稳旧交换位而不自动买回；MU 的 OI 从 `-3.66000%` 反转到 `+7.10120%`，HOLD 剩余 TACTICAL 至原 stop/target/horizon；BTC 因 OI 收缩把 pullback 调为 lead，ETH/SOL/HYPE 也在各自未完成交换条件下 HOLD 受保护 CORE。五稳定 path_id、未归一序数支持、8 动作×lead/runner/OTHER、PIT lineage、prior dependency 去重、保护和 competition status 纯验证通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision digest=`6ca6e3ba89a136ccf53e551f524d973b99c28747cadf521257ff7f00ab5e106c`、accepted state digest=`dc6656434effcd752ba1b017537e6d36200fe75f66943d7aa97ae378d1eb668f`、receipt digest=`29795bb04aa307302f7a21768c8371bc9689edc84a31ee2a56a827d324edf507`；V1 decisions/outcomes 仍 sealed；
- cycle 7 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9996.718340200588...`、net PnL=`-3.281659799411...`、realized before cost=`-3.051842818965...`、unrealized=`+0.484139077179...`、fees=`0.818474078590...`、funding=`+0.104518020965...`、gross=`3542.484139077179...`、open risk=`128.976109694754... / 299.901550206017... USDT`、unprotected lots=`[]`。STATIC_V1 本轮按冻结 target 全退 SNDK 后为 `-9.464355881612... USDT`；DETERMINISTIC_CONTINUOUS 为 `-17.655018140371... USDT`；INITIAL_STATIC_HOLD 为 `-11.228316739883... USDT`。Agent 当前分别高 `6.182696082201... / 14.373358340959... / 7.946656940472... USDT`；仅 7/24，不据此选优、调参或裁定理论。comparator digest=`de6a4ad808ddeb602efcabbba5c4a0335b657e00e26740a5501a9effbfd199cd`；
- cycle 7 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0007.md`，SHA-256=`be5cfb4ce44425d78a9da0d5d3b66aab83113cbb2cc010b220ab409be780161a`；454 行覆盖采集来源/成功失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、五路径支持/反证/expiry/switch/hard falsifier、六标的八动作三路径反事实、SNDK reentry 可行性、六个 funding event、逐 lot role/quantity/cost/stop/target/checkpoint/horizon/risk/funding/fee、三政策和下一义务；
- cycle 8 到期采集、review 数据与 PIT 硬校验：**已完成**。due=`2026-08-04T17:04:50.094Z`、decision_at=`2026-08-04T17:26:56.134Z`、lateness=`1326 秒 < 90 分钟`；OKX public review-cycle 市场请求 `108/108`、Google News RSS 查询 `6/6` 成功，六标的各 `18/18` 且全部单次成功、prior error=0。108 个 response SHA、109 个 request receipt self-digest、acquisition/attempt/context 摘要、`3464` 个 `available_at<=decision_at`、六个正确 instrument/正 mark/各 299 根闭合 15M 全部通过。acquisition digest=`2b7399349108858471be3986e6350268ffb751dc4943220d1f96f159eb7b7af2`、attempts digest=`9f98127da0e0811e70e70d38c7da092ad250cbd135ceaf4fd7dfd87ee69e2561`、context digest=`d1b0bc2049e9a6174b4e60a16910ceb5998695d84d90d67bc253346cc4403a7b`、agent context digest=`861b56fbb61380914ed8394723afa0bdb88cc2628297192ef3f365df00f0d711`。SNDK/MU 1W、top-position L/S、完整强平历史和严格 R 继续 UNKNOWN；review-cycle 的小时 taker/global account L-S/liquidation recent rows 只按当前公开代理解释；
- cycle 8 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。新增闭合 15M 没有触发 stop/target/checkpoint/horizon，16:00 funding 已在 Cycle 7 消费，本轮无新 funding。唯一 Strategy Agent 对六标的均选择有差异化事实链、路径排序和下一义务的 HOLD：SNDK 的 1H 价格突破与 OI 条件履约，但小时/fresh/book 卖侧且无新闭合 4H 跟随，真实 `REENTER_TACTICAL` 可行但相对效用低于 HOLD CORE；MU HOLD 余下 TACTICAL 至原 `856.03/931.04/18:23:55.188Z`；BTC/SOL/HYPE 以 pullback 为 lead、trend 为 runner，ETH 以 pullback/failure 排序，均不在交换条件前追价或机械降险。五稳定 path_id、未归一序数支持、8 动作×lead/runner/OTHER、PIT lineage、prior dependency 去重、保护与 competition status 纯验证一次通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision digest=`9f265918201125c1b432986c2d318f4be9b98ab6a414db97f8a188d71af6703e`、accepted state digest=`e03ace1ae3b1191b73fa30c8444a4a65de0d68e6d2c789f93a8b0df144bd2786`、receipt digest=`743571944ced068c81a0bf9e04fb8746aa8ddb60fcd605a9de7b8e44100ae651`；V1 decisions/outcomes 仍 sealed；
- cycle 8 成本、风险与三政策同条件对照：**已复算**。Agent equity=`10009.996287049814...`、net PnL=`+9.996287049814...`、realized before cost=`-3.051842818965...`、unrealized=`+13.762085926404...`、fees=`0.818474078590...`、funding=`+0.104518020965...`、gross=`3555.762085926404...`、open risk=`142.254056543979... / 300 USDT`、unprotected lots=`[]`。STATIC_V1=`-1.898680270107... USDT`、DETERMINISTIC_CONTINUOUS=`-9.392594338124... USDT`、INITIAL_STATIC_HOLD=`+2.231700152466... USDT`；Agent 当前分别高 `11.894967319921... / 19.388881387938... / 7.764586897347... USDT`。仅 8/24，不据此选优、调参或裁定理论。comparator digest=`41cdfd6b402c65e0519021d19b291afff60ea6ed15eee6494d54e28ca3e0e66f`；
- 第二次四周期不改规则复盘：**已完成且没有修改任何冻结规则**。Cycle 5→8 依次记录 MU OPEN/ETH REDUCE、SNDK horizon EXIT/MU partial、两轮差异化 HOLD；路径 lead/runner 随闭合结构、OI、流量和拥挤发生可解释变化。权益由 `9953.230334...` 恢复至 `10009.996287...`，fees 累计至 `0.818474078590...`、funding=`+0.104518020965...`，八轮历史最大 drawdown 仍约 `0.8234995%`。SNDK 战术退出后至本轮 mark 的未参与静态差额约 `5.886839167176 USDT` 只记机会成本，不后见改写 horizon；MU 余仓继续受原期限约束；terminal 后再审查 latest-N、新闻噪音、1W/F/R 数据边界与动作判别，不在运行中改理论、阈值、风险、成本、三政策、评价、停止条件或时钟；
- cycle 8 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0008.md`，SHA-256=`85a59e6356d9e3bfa9fd433319edceb830777a4478485e18d4948f48d5db65b3`；516 行覆盖采集来源/成功失败/UNKNOWN、时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、五路径支持/反证/expiry/switch/hard falsifier、六标的八动作三路径真实仓位反事实、barrier/funding、全部 lot/fill/费用/风险、三政策、Cycle 5–8 不改规则复盘和下一义务；
- cycle 9 PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T18:04:50.094Z`、decision_at=`2026-08-04T18:28:44.447Z`、lateness=`1434s`；90/90 市场请求、6/6 新闻查询、91 张请求收据均成功，3465 个 `available_at` 字段全部满足 `available_at<=decision_at`，六标的、正 mark 和每标的 299 根 provider-confirmed 闭合 15M 硬输入通过。高周期均使用 direct lineage；ordinary-cycle 未请求的小时 taker/global L/S/top-position、不可得 F 与严格 R 均保持 typed UNKNOWN，未补零。acquisition/context/agent-context digest 依次为 `b22421beac4eae4e299d0a41c063dfcc2627f4a39f8d144a19f764868679cc29 / f8f4d1a4de565eb6f83f923cbf4a6f1c17020f9ab2bea4a07766b394692340a6 / 81d4767f884bdb82788e70a815dfa91ca537dee97f51ff3cb667a39a5afcc7bd`；
- cycle 9 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。确定性重放没有 stop/target/checkpoint 事件或新 funding；MU 余下 TACTICAL 的冻结 horizon 已在 decision_at 前到期，唯一 Strategy Agent 因此以 `EXIT_TACTICAL` 平掉 `0.142764944766...` MU，模拟成交价=`894.601044`、费前实现=`+2.71766863456 USDT`、手续费=`0.063858834317... USDT`，战略 episode 保持 `CHALLENGED/FLAT_WATCH` 而非伪造硬失效。SNDK、BTC、ETH、SOL、HYPE 的受保护 CORE 均 HOLD；SNDK 战术重入在状态上可行但前轮闭合接受条件未满足。五稳定 path_id、`UNKNOWN_NO_VALID_COMPETITION_SET`、未归一序数支持、六标的 8 动作×lead/runner/OTHER、保护与连续性纯验证通过；六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`abfc1a092a33483628172ac6bfa8abb976b5b0be35ad7395657453c17800e603 / b99512601d21f9799b50bcb7347b7e5be5655f7076fefda805da1cf795c9fe8a / bc89e84fe3586a751664522b2213a4f292df84ba88b11b25057b4d05bcdb35a4`；V1 decisions/outcomes 仍 sealed；
- cycle 9 成本、风险与三政策同条件对照：**已复算**。Agent equity=`10015.483668250886...`、net PnL=`+15.483668250886...`、realized before cost=`-0.334174184401...`、unrealized=`+16.595657327230...`、fees=`0.882332912907...`、funding=`+0.104518020965...`、gross=`3433.595657327230...`、open risk=`142.200953084256... / 300 USDT`；仅五个 CORE lot 在场且全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `+9.43649235057 / -3.02627246361 / +10.85835476813 USDT`，Agent 当前分别高 `6.047175900315... / 18.509940714498... / 4.625313482757... USDT`；仅 9/24，不据此选优、调参或裁定理论。comparator digest=`8226df412be394561a1fb52e7e6ab4ec2a46b1429f868fe26fe5eb3c78a7d323`；
- cycle 9 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0009.md`，SHA-256=`4b514d6238c90e5ce0fbed1a212afad42e63f497d174cf2c1cb9ab8513ea4bd3`；1898 行覆盖采集来源/成功失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、OBSERVATION→DERIVED→INFERENCE→HYPOTHESIS→POLICY、30 张路径卡的支持/反证/expiry/switch/hard falsifier、六标的 48 类动作与 144 项三路径真实仓位反事实、barrier/funding、全部 lot/fill/费用/风险、三政策和下一义务；
- cycle 10 PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T19:04:50.094Z`、decision_at=`2026-08-04T19:29:02.545Z`、lateness=`1452s`；90/90 市场请求、6/6 新闻查询和 91 张请求收据均单次成功，3459 个 `available_at` 全部满足 `available_at<=decision_at`，六标的 instrument、正 mark 与各 299 根 provider-confirmed 闭合 15M 通过。30 个高周期请求均为 direct lineage；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary-cycle 未采的慢代理、完整 F 与严格 R 也保持 typed UNKNOWN。acquisition/attempt/context/agent-context digest 依次为 `0460a6b1dcefdf92e1e896db8810c6179cbb62ed5b03f069cc036a17e10717d4 / 1f23d8285828583dbdea9f76b40300537300a255d97f2db842ed478b858d7e5b / ad39a1838a0eeb891a385872bce360c13f61b163d75af5c479cc4611ab6e8253 / e579ef34f2b6bc0a5799f47ef659136fc7e850bbb73f815b522ff4e52c3f2248`；
- cycle 10 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。确定性重放无 barrier/target/新增 funding event。SNDK、BTC、ETH、SOL HOLD 受保护 CORE；MU 在 Cycle 9 完整退出后保持 `FLAT_WATCH`，其真实 `REENTER_TACTICAL` 状态可行，但因 1H 未站稳 899/900.82 且 OI 仍收缩而选择有明确机会成本及 `20:04:50.094Z` 复核义务的 WAIT。HYPE 因 OI `-1.11588%`、latest-N 卖方流、funding=`0.0001`、1D down 与六小时截面第 6 的独立弱化证据，使 failure 成为 operational lead；在 54.10/53.982 尚未破坏时只 `REDUCE_CORE 25%`，以 `55.4509076` 减 `3.656641374897...` HYPE，保留 `10.969924124691...` CORE。首次纯验证在 accepted 工件不存在时拒绝 3 个已消费 dependency key，删除重复 ledger 并改用未消费 ETH 1D→pullback 证据后通过；决策只接受一次，六动作 APPLIED、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`84d8883cac3bd57910c9b80f5ea9d4f26fa4f7e808e4b85d2194b3ae99f0ee55 / 9ab2359d7e385386f4dc4507ed4a943d135c420fd4ad9091b71a58c6cedf5435 / 0a4de3a673ee339d05d545e64c3941c38c9cbfbb885d8d4529025dc5c2d5c517`；V1 decisions/outcomes 仍 sealed；
- cycle 10 成本、风险与三政策同条件对照：**已复算**。Agent equity=`10006.001177827731...`、net PnL=`+6.001177827731...`、realized before cost=`-1.570091178642...`、unrealized=`+8.450465939818...`、fees=`0.983714954410...`、funding=`+0.104518020965...`、gross=`3221.450465939818...`、open risk=`126.437111283026... / 300 USDT`；HYPE symbol risk 从决策前 `25.693177393457...` 降至 `19.269883045093...`。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `+2.411608692630 / -9.753754747788 / -0.337267803827 USDT`，Agent 当前分别高 `3.589569135100... / 15.754932575519... / 6.338445631558... USDT`；仅 10/24，不据此选优、调参或裁定理论。comparator digest=`be9cad05cf782485cdfcf0d09af0d6d1ab325b17df01195efaf90a9910e9aa15`；
- cycle 10 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0010.md`，SHA-256=`b186eeb67635aa8aa5aa2507d6ce88849aa2974cd2b3ade0a8d9922a661abebd`；1794 行覆盖采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、事实到政策链、30 张稳定路径卡、六标的 48 类动作与 144 项真实三路径反事实、逐 lot/fill/保护/费用/风险/funding、MU reentry/WAIT 与 HYPE 减仓后复核、三政策和下一义务；
- cycle 11 PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T20:04:50.094Z`、decision_at=`2026-08-04T20:33:45.309Z`、lateness=`1735s`；90/90 市场请求、6/6 新闻查询与 91 张请求收据均单次成功，3459 个 `available_at` 字段全部满足 `available_at<=decision_at`，六标的 instrument、正 mark 与各 299 根 provider-confirmed 闭合 15M 硬输入通过，future evidence=`0`。30 个高周期请求均为 direct lineage；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary-cycle 未采的 hourly taker/global L-S/top-position/recent liquidation、完整 F 与严格 R 也保持 typed UNKNOWN，不携带、不补零。acquisition/attempt/context/collection/agent-context digest=`6045bf0c314331cb15ac76fbf4ff04d3b828d9f99ff9771dd61114870581fe19 / 474b72ad15508e0a698f0524fa60f55f75c7ac2090b0247e2302e18dc47b1dd1 / 03feeced593bc03a3b6fdec06cc967b29bfc102f7ba22752406395568cd84247 / 75eed49f55911b1701eda5d2346d2f3820ca177a9e63bae355fe4a177f1bf3c2 / db021972b9628f01d552317c9d1560be9f5874e1bc81ebca8fd7f19b27048da0`；
- cycle 11 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。确定性 pre-state 重放无 stop/target/funding 新事件。唯一 Strategy Agent 将 SNDK 与 HYPE 的 normal pullback、BTC/ETH 的 trend、SOL 的 pullback、MU 的 failure 作为各自 operational lead；SNDK/BTC/ETH/SOL/HYPE 均 HOLD 受保护 CORE，MU 在 FLAT_WATCH 下选择带明确反弹机会成本及 `2026-08-04T21:04:50.094Z` 复核义务的 WAIT。HYPE 保留 Cycle 10 减仓后的 75% CORE，恢复份额被正确归为 ADD 而非 REENTER；MU/SNDK 的历史战术退出使 `REENTER_TACTICAL` 状态可行但相对效用低于本轮选择。六标的均保持 `UNKNOWN_NO_VALID_COMPETITION_SET`，无 probability/margin/entropy/EV；30 条稳定路径、48 张八动作卡、144 个 lead/runner/OTHER 路径条件结果和未消费 evidence lineage 纯验证一次通过。六动作均 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure；decision/state/receipt digest=`a344d679727aa19b2fe9015df0d59442ccec067d3e86b868f0cebf81f6d2eeb7 / 32174c40d0790f33624c7d32e2548f2efae7c13f309639d68e8bda7ecba9da3a / 3f58e52c13c4724f0b1c1484d7ccfbbdf29a2f12fa313ea4245a2a02d4b22088`；V1 decisions/outcomes 仍 sealed；
- cycle 11 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9994.239743442171...`、net PnL=`-5.760256557828...`、realized before cost=`-1.570091178642...`、unrealized=`-3.310968445740...`、fees=`0.983714954410...`、funding=`+0.104518020965...`、gross=`3209.689031554259...`、open risk=`114.675676897467... / cap 299.827192303265... USDT`；五个开放 CORE 均有 stop。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `+1.729165445836... / -16.999168446561... / -12.145469625070... USDT`；Agent 当前分别低 `7.489422003664...`、高 `11.238911888732...`、高 `6.385213067242... USDT`。确定性持续对照在本轮真实新增 15M 中以 trailing stop 退出剩余 SNDK，但该对照只在 Agent accepted 后复算，没有反推动作。仅 11/24，不据此选优、调参或裁定理论；comparator digest=`8adf97fe24a18114bc4d62bf9c42ecf842e94246b53eafc2c8152162f8d1fabb`；
- cycle 11 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0011.md`，SHA-256=`0ca7400158c737becdbe5312b187a5c55edf0b2d95deb792a745c51fe7827e83`；1792 行覆盖采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径的支持/反证/expiry/switch/hard falsifier、六标的 48 张动作卡与 144 项真实仓位反事实、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策和下一义务。Cycle 11 不是四周期复盘点，没有改变任何冻结规则；
- cycle 12 review-cadence PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T21:04:50.094Z`、decision_at=`2026-08-04T21:31:54.150Z`、lateness=`1624s`；108/108 OKX 市场请求、6/6 Google News RSS 查询与 109 张请求收据均成功，六标的各 18/18；3459 个 `available_at` 全部满足 `available_at<=decision_at`，六个 instrument、正 mark、每标的 299 根 provider-confirmed 闭合 15M 与 raw SHA lineage 通过，future evidence=`0`。30 个高周期请求均 direct；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，top-position L/S、完整 F 与严格 R 保持 typed UNKNOWN，不补零。acquisition/attempt/context/collection/agent-context digest=`b2e340c2c5d3412a7b7a550bab3281bc69b30a325259be62eac09289a6d1f9fb / 6bd422cc0b0f0d0f1dbe32d3053bc23ab8466c60f13bd583e3743e502b9934f1 / 76fb06bb84d072e3fd28f0f7154d67ec8e95b7610bb6c74ad85e980f1e52ffeb / 2dda43b3f1b1c57c6eda6e7dfa3da35498a3493f38f6c341eaba107c6b8add50 / 16c65f6bff2fc930e934287452987ceb8d2774ad945be5d8d69dace943768833`；
- cycle 12 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。pre-state 确定性重放无 stop/target/checkpoint/funding 新事件。SNDK/ETH/SOL/HYPE 以 normal pullback 为 operational lead，BTC 以 trend continuation 为 lead，MU 以 exhaustion/failure 为 lead；SNDK/BTC/ETH/SOL/HYPE 均 HOLD 受保护 CORE，MU 在真实 FLAT_WATCH 下以明确的全额 V 型恢复机会成本和 `2026-08-04T22:04:50.094Z` 复核义务 WAIT。SNDK/MU 的历史 TACTICAL 退出使 REENTER_TACTICAL 状态可行但条件未履约；HYPE 的已减数量只能按 ADD_CORE 恢复，不能伪称 REENTER。首次纯验证在 accepted 目标不存在时拒绝四条 Cycle 11 已消费且无新 4H close 的 evidence dependency；删除重复项并改用本轮新 1H/review-cadence F 证据后通过，accept 只执行一次。六动作全部 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure；30 条稳定路径、48 张八动作卡、144 项 lead/runner/OTHER 反事实与 `UNKNOWN_NO_VALID_COMPETITION_SET` 通过。decision/state/receipt digest=`f429a6c65a940d8086b5d8486abd78214ac532715536fe69af38a8e37fdf9d91 / 6238e1aa54ba85002be5414fbe1b263909df419ad378ce2e16b5147d3098a3f4 / e8e1b62d63a05f7242cb28063eecfbfe5fcf2ede15ce5d48b2aa85d1114cdf0d`；V1 decisions/outcomes 仍 sealed；
- cycle 12 成本、风险与三政策同条件对照：**已复算**。Agent equity=`10000.518899329444...`、net PnL=`+0.518899329444...`、realized before cost=`-1.570091178642...`、unrealized=`+2.968187441532...`、fees=`0.983714954410...`、modeled funding=`+0.104518020965...`、gross=`3215.968187441532...`、open risk=`120.954832784739... / cap 300 USDT`，五个开放 CORE 全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `-3.211594093598... / -20.681532548681... / -7.123428670531... USDT`；Agent 当前分别高 `3.730493423042... / 21.200431878126... / 7.642327999975... USDT`。本轮三对照无新增成交或 funding event；12/24 不据此选优、调参或宣称预测/盈利。comparator digest=`28d698bd4a98cb49af84427e09bdeb0dd0d09101426f6576cc06f83428d2519d`；
- 第三个四周期不改规则复盘（Cycle 9–12）：**已完成**。MU horizon 退出、HYPE role-exact 25% CORE 减仓、后续 flat-watch/reentry 分类、五 CORE stop 保护、barrier/funding 先重放均按冻结合同履约；MU 退出价 `894.601044` 与 HYPE 减仓价 `55.4509076` 当前分别高于 Cycle 12 mark `885.85 / 55.269`，只记作当前同点方向，不证明因果、最优或可重复优势。Cycle 9–12 的 Agent 相对对照排序会跨小时变化，Cycle 11 曾低于 STATIC_V1，Cycle 12 才重新高于三者；因此只支持连续状态/role/保护机制的实现忠实度和混合市场前缀，不支持终局政策胜出。没有修改 Core v2.1、v3 手册、阈值、风险、成本、102% 初始成本、三政策、评价、停止条件或时钟；下一固定复盘为 Cycle 16；
- cycle 12 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0012.md`，SHA-256=`223963cc96d41866d702186a26371fa59ba6badd3254fc0bda68f700937b971c`；1808 行覆盖 108/108 采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径支持/反证/expiry/switch/hard falsifier、48 张动作卡与 144 项真实仓位反事实、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策和 Cycle 9–12 复盘；
- cycle 13 ordinary-cadence PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T22:04:50.094Z`、decision_at=`2026-08-04T22:32:21.288Z`、lateness=`1651s`；90/90 OKX 市场请求、6/6 Google News RSS 查询与 91 张请求收据均单次成功，六标的各 15/15；3459 个 `available_at` 全部满足 `available_at<=decision_at`，六个 instrument、正 mark、每标的 299 根 provider-confirmed 闭合 15M 与 raw SHA lineage 通过，future evidence=`0`。30 个高周期请求均 direct；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary cadence 未采的 hourly taker/global L-S/top-position/recent liquidation、完整 F 与严格 R 也保持 typed UNKNOWN，不携带、不补零。acquisition/attempt/context/collection/agent-context digest=`b9f7778a26c09e2d089ca4299440051c6306aba7630506b964269c80a7cc4aab / 2812a5b0f1ee7e0096f00366c589011466184d11d777219b46980dca7ba8d14e / 74ef8a85aa057ddd75e06e5d114ef7f484b3c363cbd127533374bf210fc56ec0 / d11c7ad65f1f00dfb76b6a49e5ff115f2085a62fdaffca3778cedbfcc1e1b6a1 / 41b5b95c2b91e2eab26a95ebee65b33b18a04821eeb6b61c6a73ad25a96a7075`；
- cycle 13 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。pre-state 确定性重放无 stop/target/checkpoint/funding 新事件。唯一 Strategy Agent 将 SNDK 的 trend continuation、MU/ETH/HYPE 的 normal pullback、BTC/SOL 的 range reformation 作为各自 operational lead；SNDK/BTC/ETH/SOL/HYPE 均 HOLD 受保护 CORE，MU 在真实 FLAT_WATCH 下选择带明确全额 V 型恢复机会成本及 `2026-08-04T23:04:50.094Z` 复核义务的 WAIT。SNDK/MU 的历史 TACTICAL 退出使 REENTER_TACTICAL 状态可行但本轮成本后交换条件未合格；HYPE 的已减数量只能按 ADD_CORE 恢复，不能伪称 REENTER。首次纯验证即通过，accepted 目标不存在时已核验 30 条稳定路径、48 张八动作卡、144 项 lead/runner/OTHER 反事实、未消费 evidence lineage 与 `UNKNOWN_NO_VALID_COMPETITION_SET`；accept 只执行一次。六动作全部 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`8d1a78162a969155b1083a09a10598400ff95c37d4ebde7b94304069fc6ca452 / 3645d2b812e5bfd0b4fa167711feef0ee47d4e0be32b81cedd4ae6b699fa1614 / 0aabb69d0d17a84559eff91b81de2edaf3b89f504dae0896520c60cadc4b2e5d`；V1 decisions/outcomes 仍 sealed；
- cycle 13 成本、风险与三政策同条件对照：**已复算**。Agent equity=`10002.350884078936...`、net PnL=`+2.350884078936...`、realized before cost=`-1.570091178642...`、unrealized=`+4.800172191024...`、fees=`0.983714954410...`、modeled funding=`+0.104518020965...`、gross=`3217.800172191024...`、open risk=`122.786817534232... / cap 300 USDT`，五个开放 CORE 全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `-1.538149638528... / -19.707645901834... / -4.813577187709... USDT`；Agent 当前分别高 `3.889033717464... / 22.058529980771... / 7.164461266646... USDT`。本轮三对照无新增成交或 funding event；13/24 不据此选优、调参或宣称预测/盈利。comparator digest=`544f3ccfc735c3535044c44037b4e6fa437c12183dd4ef432b7c10e5c3cb6de4`；
- cycle 13 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0013.md`，SHA-256=`ad86f949938dd2a8f2c30a91a0b9239b9258d1e67ac5924a7da9021f41857de6`；1792 行覆盖 90/90 采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径支持/反证/expiry/switch/hard falsifier、48 张动作卡与 144 项真实仓位反事实、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策和下一义务。Cycle 13 不是四周期复盘点，没有修改冻结规则；
- cycle 14 ordinary-cadence PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-04T23:04:50.094Z`、decision_at=`2026-08-04T23:31:46.142Z`、lateness=`1616s`；90/90 OKX 市场请求、6/6 Google News RSS 查询与 91 张请求收据均单次成功，六标的各 15/15；3459 个 `available_at` 全部满足 `available_at<=decision_at`，六个 instrument、正 mark、每标的 299 根 provider-confirmed 闭合 15M、全部 raw SHA 与 receipt self-digest 通过，future evidence=`0`。30 个周期请求均 direct；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary cadence 未采的 hourly taker/global L-S/top-position/recent liquidation、完整 F 与严格 R 也保持 typed UNKNOWN，不携带、不补零。acquisition/attempt/context/collection/agent-context digest=`290b9a1f85ad2f88487a16d821649e3f8df8d215c69cd289111694fcc57d5185 / f70a220f5967ae5dd029a567300540690734432bdea7a5c769821dc300aa8850 / 60f5065cb2778ab66f098ce5699e80a9c98d601d70fbf5916b5a941f2b47d182 / 7f70ec087a07b774434c97a63feaeddf0ed54d72475057897b5ce488c314fc28 / 7da6e100124e48a4dfc7a1962628c2d279bc0908312143276703a98d7331a351`；
- cycle 14 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。pre-state 确定性重放无 stop/target/checkpoint/funding 新事件。唯一 Strategy Agent 将六标的 normal pullback 作为 operational lead；SNDK 的 trend continuation、MU/BTC/ETH/SOL 的 range reformation、HYPE 的 exhaustion/failure 分别为 runner-up。SNDK/BTC/ETH/SOL/HYPE 均 HOLD 受保护 CORE，MU 在真实 FLAT_WATCH 下选择带明确全额 V 型恢复机会成本及 `2026-08-05T00:04:50.094Z` 复核义务的 WAIT；SNDK/MU 的历史 TACTICAL 退出使 REENTER_TACTICAL 状态可行但本轮成本后交换不合格，HYPE 的已减数量只能按 ADD_CORE 恢复。纯验证在 accepted 目标不存在时先检出 BTC 一条没有新闭合 4H bar 的 dependency reuse，移除后改用本轮新 1H 增量并完整通过；accept 仅执行一次。30 条稳定路径、48 张八动作卡、144 项 lead/runner/OTHER 反事实与 `UNKNOWN_NO_VALID_COMPETITION_SET` 通过，六动作全部 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`ea6212a678b1f84f40f40212917d6a4e810f447ddf94d36a4c891d607719e898 / 840457e8caba50f94b155ff5079898e059cc9342910ba7b98150949c90ac5d12 / 02d7784f1d61f989bda24c9980c277324032ef94567578cca38c51c6d5540753`；V1 decisions/outcomes 仍 sealed；
- cycle 14 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9995.924112111515...`、net PnL=`-4.075887888484...`、realized before cost=`-1.570091178642...`、unrealized=`-1.626599776396...`、fees=`0.983714954410...`、modeled funding=`+0.104518020965...`、gross=`3211.373400223603...`、open risk=`116.360045566810... / cap 299.877723363345... USDT`，五个开放 CORE 全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `-10.659009467205... / -25.849394134695... / -13.737453888749... USDT`；Agent 当前分别高 `6.583121578720... / 21.773506246211... / 9.661566000264... USDT`。Cycle 13→14 三对照无新增成交或 funding event；14/24 不据此选优、调参或宣称预测/盈利。comparator digest=`9a0969a49e717f5184a4b538a8b94c19653fe9a3a4e77c5bce0abfb1e7cc1e62`；
- cycle 14 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0014.md`，SHA-256=`950ed54c632d3f0e11cd914c0800bb319c21fa840e7c5c209fd752cf303b2de5`；1793 行覆盖 90/90 采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径支持/反证/expiry/switch/hard falsifier、48 张动作卡与 144 项真实仓位反事实、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策和下一义务。Cycle 14 不是四周期复盘点，没有修改冻结规则；
- cycle 15 到期采集、ordinary-cycle UNKNOWN 与 PIT 硬校验：**已完成**。due=`2026-08-05T00:04:50.094Z`、decision_at=`2026-08-05T00:34:01.357Z`、lateness=`1751 秒 < 90 分钟`；OKX public 市场请求 `90/90`、Google News RSS `6/6` 成功，91 张 request receipt、raw SHA/self-digest、六个 instrument、正 mark、各 299 根 provider-confirmed closed 15M 与 `3465` 个 `available_at<=decision_at` 全部通过，future evidence=`0`。30 个尺度均 direct；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary cadence 未采的小时 taker、account L/S、完整 F 与严格 R 也保持 typed UNKNOWN，不携带、不补零。acquisition/attempt/context/collection/agent-context digest=`dc3e9e329c160ddcb8c580961206347c1a5409bea77770ab24aedf884a1f43f6 / 0286f4d5f50929bcd928e2354c65f111fa3711fc73212c2d4226dac1e9c45399 / 0cf267407def9a6204dadf85eefc985b31d40473e8478d875baac1d4365e7ed5 / 38f7dc53b01cae872af205e6ba921b524b5493940c0ca0f11015e14f19aba91d / 8dc7183757c387b2b03cde115da54c697c3160812ab22b34c70e16564b203c05`；
- cycle 15 funding 重放、唯一 Agent 判断与 write-once accept：**已完成**。确定性代码先重放六个 `2026-08-05T00:00:00Z` funding proxy：SNDK/MU/BTC/ETH/SOL/HYPE=`+0.301155390974 / 0 / -0.024941030980 / +0.011379732392 / -0.049526910736 / -0.060398208246 USDT`，没有 stop/target/checkpoint barrier。唯一 Strategy Agent 仍以六标的 normal pullback 为 operational lead；SNDK 的 trend continuation、MU/BTC/ETH/SOL 的 range reformation、HYPE 的 exhaustion/failure 为 runner-up。SNDK/BTC/ETH/SOL/HYPE HOLD 受保护 CORE，MU flat-watch 选择含全部 V 型恢复机会成本和 `2026-08-05T01:04:50.094Z` 复核义务的 WAIT；SNDK 仅部分满足阻力确认，MU 未满足 898.60/902.13+OI/flow 联合条件，HYPE 的已减份额仍只能按 ADD_CORE 恢复。30 条路径、48 张动作卡、144 项 lead/runner/OTHER 反事实与未消费 evidence lineage 纯验证一次通过；accept 只执行一次，六动作 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`b368f7b1037acea16dbfa7e3911a10cacd82ab711430ecf019701ec21c4d2429 / d4f48009c5e5200b76285520e41976488df318e8596736f01c7eb2aa86e881f8 / 754a4e0f4d32d969afa1ae5d0dad385092c79a8b16b34f87703e5ed8281754ba`；V1 decisions/outcomes 仍 sealed；
- cycle 15 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9996.319382153210...`、net PnL=`-3.680617846789...`、realized before cost=`-1.570091178642...`、unrealized=`-1.408998708105...`、fees=`0.983714954410...`、modeled funding=`+0.282186994369...`、gross=`3211.591001291894...`、open risk=`116.577646635101... / cap 299.889581464596... USDT`，五个开放 CORE 全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `-15.004737493196... / -30.942965893190... / -13.599923198539... USDT`；Agent 当前分别高 `11.324119646407... / 27.262348046401... / 9.919305351750... USDT`。15/24 只作同点描述，不据此选优、调参或宣称预测/盈利。comparator digest=`8fd616c87bb804869560fba4554e70c137a00cf6a33b493551ba73387a6214c7`；
- cycle 15 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0015.md`，SHA-256=`0078518f0d9ef58f9c53fb2ccbeb4dcf33fc820c5fafe127a3c315ede7285f9d`；1779 行覆盖采集来源/失败/UNKNOWN、PIT 时间谱系、多周期、D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径支持/反证/expiry/switch/hard falsifier、48 张动作卡与 144 项真实仓位反事实、六笔 funding、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策和下一义务。Cycle 15 不是四周期复盘点，没有修改冻结规则；
- cycle 16 到期采集、review-cadence 慢代理与 PIT 硬校验：**已完成**。due=`2026-08-05T01:04:50.094Z`、decision_at=`2026-08-05T01:30:57.713Z`、lateness=`1567 秒 < 90 分钟`；OKX public review-cycle 市场请求 `108/108`、Google News RSS `6/6` 成功，109 张 request receipt、raw SHA/self-digest、六个 instrument、正 mark、各 299 根 provider-confirmed closed 15M 与 `3465` 个 `available_at<=decision_at` 全部通过，future evidence=`0`。30 个尺度均 direct；SNDK/MU 1W 因 22 根保持 UNKNOWN。小时 taker、global account L/S 与 recent F 已按 review cadence 重采；top-position L/S 仍 UNKNOWN，F 仍为 `UNKNOWN_RECENT_ROWS_ONLY / missing_is_zero=false`，严格 R 仍为 `UNKNOWN_SNAPSHOT_ONLY`。acquisition/attempt/context/collection/agent-context digest=`0905da37369f738f250737b60b19421daede9db24d449cc6d5342774d511e1e9 / 6c8f451c2e34c33425e563a2322894168f7f7818df86e7c2f3bd2eb22f85e498 / 372973e6c3977de50aaf654294900154e785fda63271d7c8648fc3d9cb5f8a53 / 7a25e7ce38c9e53be68a17917b2dcda35ac1837a72354284c8977cf25355d72e / 0571f8b8b45e392cf0d4b851c1f63c6a2a33b945559e01fa6661979b69b59336`；
- cycle 16 barrier 重放、唯一 Agent 判断与 write-once accept：**已完成**。pre-state=`b3df46a754e4348d5a2174679feab640d9b6a488a15f25abf38446bbe540b5bc`，`bar_replay_events=[] / target_events=[]`，无新 funding、stop、target 或 checkpoint 事件。唯一 Strategy Agent 对六标的均以 normal pullback 为 operational lead；SNDK trend、MU/BTC/SOL range、ETH/HYPE failure 分别为 runner-up。SNDK/BTC/ETH/SOL/HYPE HOLD 受保护 CORE，MU flat-watch WAIT并承担至 `2026-08-05T02:04:50.094Z` 的全部突破机会成本；ETH 只部分跌破第一层支撑，联合失败门槛未触发；SNDK/MU 的已退 TACTICAL 只能按 REENTER 恢复，HYPE 已减份额只能按 ADD_CORE 恢复。首次纯验证在 accepted 目标不存在时以 `EVIDENCE_INCREMENT_REUSED` 拒绝 BTC/MU 各一条无新 4H close 的依赖；只在草案换成本轮新 15M/1H 增量后通过。30 条路径、48 张动作卡、144 项 lead/runner/OTHER 反事实完整通过；accept 只执行一次，六动作 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected lot、0 continuity/fidelity failure。decision/state/receipt digest=`f2617247d4743d7973b6324b3a9fd316217da157e1c3a7fb4c0ab51b11631b58 / 67a2ee39510a2971789b676d5160c14d6954f6a4099724d0b2c8270e59a5defd / 0749ee81315e54ccee3dec103b88e19e7062e816c01cf2e85c1e986dced44b40`；V1 decisions/outcomes 仍 sealed；
- cycle 16 成本、风险与三政策同条件对照：**已复算**。Agent equity=`9989.544392477261...`、net PnL=`-10.455607522738...`、realized before cost=`-1.570091178642...`、unrealized=`-8.183988384055...`、fees=`0.983714954410...`、modeled funding=`+0.282186994369...`、gross=`3204.816011615944...`、open risk=`109.802656959152... / cap 299.686331774317... USDT`，五个开放 CORE 全部受保护。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD 净 PnL 依次为 `-15.555236610317... / -31.619491622630... / -21.294848829588... USDT`；Agent 当前分别高 `5.099629087579... / 21.163884099892... / 10.839241306850... USDT`。16/24 只作同点描述，不据此选优、调参或宣称预测/盈利。comparator digest=`80aedf912ce0d6334d8d132e15ad4be68af9437625bc04f8329d5710e7ff191e`；
- 第四个四周期不改规则复盘（Cycle 13–16）：**已完成并未改任何冻结规则**。四轮均先确定性重放后由唯一 Agent 决策，动作均为五个受保护 CORE HOLD + MU flat-watch WAIT，无隐式仓位突变；SNDK/BTC/SOL 的 lead 在 Cycle 13→14 发生可追溯序数交换，ETH 在 Cycle 16 将 failure 升为 runner，MU/HYPE 竞争结构稳定。Agent net PnL 在四个截面为 `+2.350884078936 / -4.075887888484 / -3.680617846789 / -10.455607522738 USDT`，不构成稳定盈利证据；Cycle 16 相对三对照虽均为正差，也仅是单一路径进行中前缀。状态连续性、role-exact 动作、保护、证据增量和复核义务机制继续得到实现层支持；16/24 且 terminal 未封存，不能声称预测有效、政策胜出或生产就绪。下一固定复盘为 Cycle 20；
- cycle 16 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0016.md`，SHA-256=`d0f4d28e179c3ff34eaaedf2678d8169a6f9a138fecbfe51eae21b48317cba15`；1799 行覆盖采集来源/失败/UNKNOWN/PIT、多周期、完整 review-cadence D/L/C/F/R、新闻与跨市场、理论认识论链、30 条路径支持/反证/expiry/switch/hard falsifier、48 张动作卡与 144 项真实仓位反事实、逐 lot role/数量/成本/stop/checkpoint/risk/funding/fee、reentry/review、三政策、验证纠错和 Cycle 13–16 不改规则复盘；
- cycle 17 ordinary-cadence PIT 采集与硬输入校验：**已完成且在 90 分钟失败关闭窗口内**。due=`2026-08-05T02:04:50.094Z`、decision_at=`2026-08-05T02:31:30.804Z`、lateness=`1600s`；90/90 OKX 市场请求、6/6 Google News RSS、91 张 request receipt、raw SHA/self-digest、六个 instrument、正 mark、各 299 根 provider-confirmed closed 15M 与 `3465` 个 `available_at<=decision_at` 全部通过，future evidence=`0`。30 个尺度均 direct；SNDK/MU 1W 因仅 22 根保持 UNKNOWN，ordinary cadence 未采的小时 taker、global/top-position L/S、完整 F 与严格 R 也保持 typed UNKNOWN，不携带 Cycle 16 review 值、不补零。acquisition/attempt/context/collection/agent-context digest=`a3c9075ca060f1640043292b79d5edb9b93f824b33b27965452c1852eb39767a / 094e00daca907c91556f7a64d3089721fff903914faa1c6fab58faccbe9e9199 / c6836513c38ed259eb4239b0322c88d00c78c32b05618ac67afb6a87215f52c3 / a8dd68e51c497f4d4a622c15148c2cf1dcb5e770b7d55338ac03e84e37164f4b / 6b566e65b1fa12dd810d731189949a42f246e7cde9cb2e6291c9fa1cdb32ec0b`；
- cycle 17 barrier 重放、唯一 Agent 判断与 write-once accept：**已执行，但 accepted decision 随后被判为 fatal lot-truth conflict，不能计作完整通过**。pre-state=`759e3b86ca4c1f5f345fa5cd6973cd92460758e419c4fe03d36dee433fb7795d`，无 barrier/target/funding 新事件。唯一 Strategy Agent 选择 SNDK/ETH/SOL/HYPE normal pullback、MU normal pullback、BTC range reformation 为各自 lead；SNDK/BTC/ETH/SOL/HYPE HOLD 受保护 CORE，MU flat-watch WAIT。accept 前 schema/依赖/apply validator 返回 PASS，六动作 APPLIED/NO_POSITION_MUTATION、0 veto、0 unprotected、0 continuity/fidelity failure；accept 只执行一次，decision/state/receipt digest=`d003f566662b618d806a0ceb89ddf3c887921ce246bdda07eb99c39aa143f215 / 497702fd16741eb46067ed12eebac50cddb0f1942a8ff8cdf8ed51f6050bc0ef / c1e2cbebf949516e757dfaa5dabd16aafb87ab1ab2b5a612e1fa724a8b79486a`，V1 decisions/outcomes 仍 sealed；
- cycle 17 accept 后一致性事故与失败关闭：**已确认并 write-once 中断，不改写 accepted 工件**。只读交叉复核发现五个持仓标的的 `8 actions × 3 paths` 共 `120/144` 条 `path_realization` 文字沿用 Cycle 16 的 mark 名义/open risk，而非 Cycle 17 pre-state：SNDK `542.124084/63.071886` 应为 `536.695684/57.643486`，BTC `1009.190592/19.106950` 应为 `1013.777228/23.693586`，ETH `251.891449/5.123745` 应为 `252.282133/5.514429`，SOL `805.905673/15.939911` 应为 `810.827068/20.861306`，HYPE `602.479203/13.335154` 应为 `612.505714/23.361665`；MU 0 lot 文本正确。另有六个 `dynamic_update_summary` 的前序轮标签被错误替换为 Cycle 17，应指 Cycle 16。validator 未做该文本—pre-state 交叉绑定，属于 false negative；按授权合同 fatal `state head, lot, episode, barrier, or reentry truth conflict` 以 reason=`ACCEPTED_CYCLE_0017_ACTION_COUNTERFACTUAL_LOT_TRUTH_CONFLICT` 失败关闭。interruption digest=`13470ea3538c09d62c7c737bab83e2a6805b7c11681d585d3ba2c983833f337b`；通用中断序列化器的遗留固定 `failure_time_status=UNKNOWN_USER_REPORTED_APPROXIMATE_NETWORK_OUTAGE` 与本事故不符，权威原因只取 reason_code 与交叉字段证据，不改写该收据；
- cycle 17 成本、风险与三政策同点结果：**已在 accept 后按冻结输入复算，但因 run 中断只能作事故前缀描述**。Agent equity=`10010.816206648043...`、net PnL=`+10.816206648043...`、realized before cost=`-1.570091178642...`、unrealized=`+13.087825786727...`、fees=`0.983714954410...`、modeled funding=`+0.282186994369...`、gross=`3226.087825786727...`、open risk=`131.074471129934... / cap 300 USDT`。STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD net PnL=`+9.434709457695... / -26.726796550532... / +5.411123331111... USDT`；Agent 同点差=`+1.381497190348... / +37.543003198576... / +5.405083316931... USDT`。comparator digest=`a9e7322788e5765ba4ef04429829fa3ae5908f35634b1340e2f41ffec86e7cf7`；17/24 且 terminal 永久不再收集，不能据此选优、调参或宣称预测/盈利；
- cycle 17 完整中文事故报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v13-20260804t100154z/reports/cycle-0017.md`，SHA-256=`35e9bc3d6fbe5a245381bf1480a0c3549617fd268e46cd186a323a2bb8f3bd31`；1805 行保留采集/PIT、多周期、D/L/C/F/R、新闻、理论链、30 路径、48 动作卡、144 反事实、逐 lot、成本/风险、三对照与 write-once 工件，并显式标记 120 条反事实数值与 6 条前序轮标签冲突，不把 validator PASS 或 accepted=true 伪装成完整验收；
- 当前 durable 进度：**INTERRUPTED_OUTCOMES_SEALED / completed_cycles=17 / next_uncompleted_cycle=18 / accepted_state_digest=497702fd16741eb46067ed12eebac50cddb0f1942a8ff8cdf8ed51f6050bc0ef / no pending context / resume_allowed=false**。Cycle 18–24、terminal、evaluate、审计和 Cycle 20 复盘均取消；future context/outcome、V1 decisions/outcomes 仍 sealed。若用户未来另行授权，只能新建 `NEW_RUN / NEW_CHRONOLOGY / NEW_FROZEN_CONTRACT` successor，绝不恢复或修补本 run；
- 后续逐小时递进任务：**本 run 中断后已失去作用，但控制面删除受阻**。已对唯一 heartbeat id=`v1-3` 连续发起四次 `mode=delete`；第四次于 `2026-08-05T04:31:23.526Z` heartbeat 再次调用，仍超过 60 秒无返回并被终止。本地 `/Users/wt/.codex/automations/v1-3/automation.toml` 仍显示 `ACTIVE`，因此不得宣称已删除。没有创建第二个 automation，也没有直接改写 Codex 控制面文件；连续失败后不再扩大或绕过控制面，需在 Codex UI 手动删除。即使再次唤醒，durable checkpoint 的 `INTERRUPTED_OUTCOMES_SEALED / resume_allowed=false` 也禁止采集或打开 Cycle 18；旧 `automation-2` 与旧 `24h-agent` 不恢复；
- terminal raw、评价和审计：**因 fatal 中断永久取消**。没有收集 Cycle 18–25 或 future outcome，不对 17/24 前缀作终局评价。

### 需求变更记录

- 2026-08-04：用户回复“确认，执行”，明确批准上一节唯一推荐路径。该授权只打开全新 successor 的公开数据采集、本地不可执行纸面状态写入和完成 24 小时窗口所需的单一递进任务；不授权旧 run 恢复、账户/凭据、paper/live、真实订单或资金操作。

## 二十五、运行中的 v1.3 实验迁移至全新窗口

### 用户最终需要的交付结果

- 用户指出当前聊天上下文已经严重压缩，可能污染或截断后续单 Strategy Agent 分析，要求把正在运行的 v1.3 实验迁移到一个全新 Codex 窗口；
- 新窗口必须直接使用同一项目目录和唯一 run_root，从 durable checkpoint、accepted state、decision、receipt、冻结合同、作战手册与本需求记录恢复，不从旧聊天摘要重建市场状态；
- 现有逐小时 heartbeat 必须原子迁移到新窗口，不能让新旧两个窗口并行采集或提交同一 cycle。

### 验收标准

1. 新窗口运行在保存项目 `/Users/wt/Documents/agent-trade-emotion` 的 `local` 环境，不创建隔离 worktree，不复制或重建 `.runtime`；
2. 新窗口首条指令绑定唯一 run=`single-agent-prospective-24h-v13-20260804t100154z`，先完成冷启动权威文档读取，并以 checkpoint/status 为当前进度；
3. 迁移时权威边界保持 `completed_cycles=1 / next_cycle_index=2 / accepted_state_digest=ab6772ea... / RUNNING_OUTCOMES_SEALED`，不打开 Cycle 2、不读取 later outcome、不改写 Cycle 1；
4. heartbeat `v1-3` 只更改 `target_thread_id`，名称、周期、状态、prompt 和研究边界保持不变；新窗口 ready 并取得正式 thread id 后才能切换；
5. 当前窗口切换后不再推进实验，只负责报告新窗口与 automation 绑定结果；旧 `automation-2` 继续 PAUSED，旧 `24h-agent` 不恢复；
6. 迁移不改变 Core v2.1、v3 手册、风险、成本、102% 初始成本、三政策、评价、24h 时钟或外部执行权限。

### 当前范围与明确不做

- 本轮只更新同一需求记录、创建一个使用保存项目 local 环境的新窗口、迁移既有 heartbeat 并验证绑定；
- 不创建第二个 automation、Agent 集群、Critic、transport 或数据平台，不在迁移过程中采集 Cycle 2；
- 不访问账户、凭据、paper/live、真实订单或资金，不修改任何 runtime write-once 工件。

### 当前主要任务与状态

- 当前权威 checkpoint 与工作树：**已复核**。HEAD=`74f5de7aa02942e97b6583485e4da253fc119397`、工作树在记录本节前干净；checkpoint=`RUNNING_OUTCOMES_SEALED / completed=1 / next=2 / no pending context`；
- 全新 local 项目窗口：**已创建并 ready**。project=`agent-trade-emotion / 1f64fdfa-5700-47fb-83e8-b6a9343c122e`，thread id=`019fcc52-c1ab-7b70-b249-dfeb1892e773`；首条 handoff 要求完整冷启动读取、现场复核 checkpoint，并只从 durable 工件恢复；没有使用 worktree、聊天摘要或复制 runtime；
- heartbeat `v1-3` 的单目标迁移：**已完成并复核**。automation 保持 `ACTIVE`、同名、同周期、同 prompt，只将 `target_thread_id` 从旧窗口 `019fafdd-15d4-7531-bc5d-d34df2fc52e3` 切换为新窗口 `019fcc52-c1ab-7b70-b249-dfeb1892e773`；未创建第二个 automation；
- Cycle 2 及以后市场推进：**本窗口明确不执行**。
- 新窗口冷启动与 Cycle 2 接管：**已完成**。新窗口只从根 `AGENTS.md`、冻结理论/手册/授权合同、本需求记录、manifest/checkpoint/status、上一 accepted state/decision/receipt 恢复权威状态，没有用旧聊天摘要重建市场；随后按到期边界完成精确一个 Cycle 2，当前 durable checkpoint 已推进到 `completed=2 / next=3 / accepted_state_digest=efee39b1... / RUNNING_OUTCOMES_SEALED`。本条只记录新窗口事实，不改变旧窗口“迁移后不再执行”的历史边界。
- 新窗口 Cycle 3 续行：**已完成**。heartbeat `v1-3` 在 Cycle 3 到期后只推进 checkpoint 指定的一轮；采集、硬输入/PIT、open-cycle、唯一 Strategy Agent 判断、纯验证、write-once accept、三政策复算、完整报告和本需求记录均已闭环。当前 durable checkpoint=`completed=3 / next=4 / accepted_state_digest=0a0e04b1... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T13:04:50.094Z`，到期前不采集。
- 新窗口 Cycle 4 续行与首次四周期复盘：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定的 Cycle 4；108/108 review-cycle 公开请求与 PIT 硬输入通过，唯一 Strategy Agent 的六动作 write-once accepted，三政策复算、482 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=4 / next=5 / accepted_state_digest=4f273c78... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T14:04:50.094Z`。复盘只记录路径前缀、动作忠实度、ADD/机会差、费用、funding、drawdown、reentry 与 terminal 后审计项，没有修改运行规则。
- 新窗口 Cycle 5 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定的 Cycle 5；90/90 ordinary-cycle 公开请求、6/6 新闻查询和 PIT 硬输入通过，未把 Cycle 4 review-only 代理携带为当前事实。唯一 Strategy Agent write-once 接受 MU 250 USDT PROBE `OPEN_TACTICAL`、ETH 剩余 CORE 再减 50% 及其余四标的 HOLD；三政策复算、440 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=5 / next=6 / accepted_state_digest=3fa25e77... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T15:04:50.094Z`。本轮没有改写任何 accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 6 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定的 Cycle 6；90/90 ordinary-cycle 公开请求、6/6 新闻查询和 PIT 硬输入通过，未携带 review-only 代理。唯一 Strategy Agent 在无 barrier/funding 事件后履行 SNDK TACTICAL 最大期限，以 `EXIT_TACTICAL` 关闭该 role 并保留 CORE；MU 因上涨同时伴随 OI 收缩而 `PARTIAL_TAKE_PROFIT 50%`，其余四标的 HOLD。纯验证在 accept 前先拒绝并纠正三路径模板复用与两项历史 evidence increment 复用，accepted 工件只写一次；三政策复算、452 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=6 / next=7 / accepted_state_digest=78ae42e3... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T16:04:50.094Z`。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 7 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定的 Cycle 7；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3466 个 PIT 时间字段与六标的硬输入通过，未携带 review-only 代理。确定性代码在 Agent 前重放六个 16:00 UTC funding proxy、没有 barrier fill；唯一 Strategy Agent 对六标的均选择有差异化理由与下一义务的 HOLD，并把 SNDK 的真实 tactical reentry 标为可行但未满足闭合确认，把 MU 的 reentry 因余仓仍在标为硬不可行。纯验证一次通过，accepted 工件只写一次；三政策复算、454 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=7 / next=8 / accepted_state_digest=dc665643... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T17:04:50.094Z`，Cycle 8 到期前不采集。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 8 续行与第二次四周期复盘：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定的 Cycle 8；108/108 review-cycle 公开请求、6/6 新闻查询、3464 个 PIT 时间字段和六标的硬输入通过。唯一 Strategy Agent 对六标的完成完整市场/情绪/五路径/八动作/真实 lot 判断，六项差异化 HOLD write-once accepted；SNDK 的价格/OI 条件满足但流量/4H 跟随不完整，因此保留可行但未选择的 TACTICAL reentry，MU 继续受原 stop/target/horizon 约束。三政策复算、516 行完整报告、Cycle 5–8 不改规则复盘和同一需求记录闭环。当前 durable checkpoint=`completed=8 / next=9 / accepted_state_digest=e03ace1a... / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T18:04:50.094Z`，到期前不采集。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 9 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 9；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3465 个 PIT 时间字段和六标的硬输入通过。确定性重放无 barrier/funding 事件；MU TACTICAL 在冻结 horizon 到期后按 role 精确 `EXIT_TACTICAL`，其余五个受保护 CORE HOLD，SNDK 可行 reentry 因闭合条件未满足而未执行。五路径、八动作、真实 lot、费用/风险、三政策复算、1898 行完整报告和同一需求记录闭环；accepted state digest=`b99512601d21f9799b50bcb7347b7e5be5655f7076fefda805da1cf795c9fe8a`。当前 durable checkpoint=`completed=9 / next=10 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T19:04:50.094Z`。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 10 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 10；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3459 个 PIT 时间字段与六标的硬输入通过。确定性重放无 barrier/funding 事件；唯一 Strategy Agent 对 SNDK/BTC/ETH/SOL HOLD 受保护 CORE，MU 以显式空仓机会成本 WAIT，HYPE 在 failure lead 尚未硬失效时 `REDUCE_CORE 25%` 并保留 75% CORE。纯验证先拒绝并纠正 3 个历史 dependency reuse，accepted 工件只写一次；三政策复算、1794 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=10 / next=11 / accepted_state_digest=9ab2359d7e385386f4dc4507ed4a943d135c420fd4ad9091b71a58c6cedf5435 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T20:04:50.094Z`。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、评价或时钟。
- 新窗口 Cycle 11 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 11；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3459 个 PIT 时间字段、91 张请求收据与六标的硬输入通过，future evidence=`0`。确定性重放无 barrier/funding 新事件；唯一 Strategy Agent 对 SNDK/BTC/ETH/SOL/HYPE HOLD 受保护 CORE，MU 以显式空仓机会成本 WAIT；HYPE 的已减份额恢复被正确归类为 ADD_CORE。30 条稳定路径、48 张八动作卡和 144 项 lead/runner/OTHER 反事实纯验证一次通过，accepted 工件只写一次；三政策复算、1792 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=11 / next=12 / accepted_state_digest=32174c40d0790f33624c7d32e2548f2efae7c13f309639d68e8bda7ecba9da3a / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T21:04:50.094Z`。本轮没有改写任何 prior accepted 工件、冻结规则、成本、风险、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 12 续行与第三次四周期复盘：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 12；108/108 review-cycle 公开请求、6/6 新闻查询、3459 个 PIT 时间字段、109 张请求收据与六标的硬输入通过，future evidence=`0`。唯一 Strategy Agent 对五个受保护 CORE 选择 HOLD、MU flat-watch 选择有显式机会成本的 WAIT；纯验证先 fail-closed 排除四条已消费 4H dependency，再以新 1H/review-cadence 证据通过，accepted 工件只写一次。三政策复算、1808 行完整报告、Cycle 9–12 不改规则复盘和同一需求记录闭环。当前 durable checkpoint=`completed=12 / next=13 / accepted_state_digest=6238e1aa54ba85002be5414fbe1b263909df419ad378ce2e16b5147d3098a3f4 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T22:04:50.094Z`，到期前不采集。本轮没有改写任何 prior accepted 工件、冻结 Core/手册、阈值、风险、成本、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 13 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 13；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3459 个 PIT 时间字段、91 张请求收据与六标的硬输入通过，future evidence=`0`。确定性重放无 barrier/target/funding 新事件；唯一 Strategy Agent 对五个受保护 CORE 选择 HOLD、MU flat-watch 选择含明确机会成本和下一复核的 WAIT。30 条稳定路径、48 张八动作卡与 144 项 lead/runner/OTHER 反事实首次纯验证即通过，accepted 工件只写一次；三政策复算、1792 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=13 / next=14 / accepted_state_digest=3645d2b812e5bfd0b4fa167711feef0ee47d4e0be32b81cedd4ae6b699fa1614 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-04T23:04:50.094Z`，到期前不采集。本轮没有改写任何 prior accepted 工件、冻结 Core/手册、阈值、风险、成本、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 14 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 14；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3459 个 PIT 时间字段、91 张请求收据与六标的硬输入通过，future evidence=`0`。确定性重放无 barrier/target/funding 新事件；唯一 Strategy Agent 对五个受保护 CORE 选择 HOLD、MU flat-watch 选择含明确机会成本和 `2026-08-05T00:04:50.094Z` 复核义务的 WAIT。纯验证先排除 BTC 一条无新增 4H close 的已消费 dependency，再以本轮新 1H 增量通过；30 条稳定路径、48 张八动作卡与 144 项 lead/runner/OTHER 反事实完整验证，accepted 工件只写一次；三政策复算、1793 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=14 / next=15 / accepted_state_digest=840457e8caba50f94b155ff5079898e059cc9342910ba7b98150949c90ac5d12 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-05T00:04:50.094Z`，到期前不采集。本轮没有改写任何 prior accepted 工件、冻结 Core/手册、阈值、风险、成本、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 15 续行：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 15；90/90 ordinary-cycle 公开请求、6/6 新闻查询、3465 个 PIT 时间字段、91 张请求收据与六标的硬输入通过，future evidence=`0`。确定性代码在 Agent 前重放六笔 00:00Z funding proxy、无 barrier fill；唯一 Strategy Agent 对五个受保护 CORE 选择 HOLD，MU flat-watch 选择含明确机会成本和下一小时复核的 WAIT。30 条稳定路径、48 张八动作卡与 144 项 lead/runner/OTHER 反事实首次纯验证即通过，accepted 工件只写一次；三政策复算、1779 行完整报告和同一需求记录闭环。当前 durable checkpoint=`completed=15 / next=16 / accepted_state_digest=d4f48009c5e5200b76285520e41976488df318e8596736f01c7eb2aa86e881f8 / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-05T01:04:50.094Z`，本 heartbeat 不继续 Cycle 16。本轮没有改写任何 prior accepted 工件、冻结 Core/手册、阈值、风险、成本、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 16 续行与第四次四周期复盘：**已完成**。heartbeat `v1-3` 只推进 checkpoint 指定且已到期的 Cycle 16；108/108 review-cycle 公开请求、6/6 新闻查询、3465 个 PIT 时间字段、109 张请求收据与六标的硬输入通过，future evidence=`0`。确定性重放无 barrier/target/funding 新事件；唯一 Strategy Agent 对五个受保护 CORE 选择 HOLD，MU flat-watch 选择含全部突破机会成本和下一小时复核的 WAIT。纯验证先 fail-closed 排除 BTC/MU 两条未产生新 4H close 的历史依赖，再用当轮新 15M/1H 增量通过；accepted 工件只写一次。三政策复算、1799 行完整报告、Cycle 13–16 不改规则复盘和同一需求记录闭环。当前 durable checkpoint=`completed=16 / next=17 / accepted_state_digest=67a2ee39510a2971789b676d5160c14d6954f6a4099724d0b2c8270e59a5defd / RUNNING_OUTCOMES_SEALED / no pending context`；下一 due=`2026-08-05T02:04:50.094Z`，本 heartbeat 不继续 Cycle 17。本轮没有改写任何 prior accepted 工件、冻结 Core/手册、阈值、风险、成本、102% 初始成本、三政策、评价或时钟。
- 新窗口 Cycle 17 续行与 fatal 失败关闭：**Cycle 17 数据/状态动作已 write-once 到 durable 边界，但 run 未达到完整验收并永久中断**。heartbeat `v1-3` 只采集和接受 checkpoint 指定的 Cycle 17；90/90 ordinary-cycle 市场、6/6 新闻、91 张请求收据、3465 个 PIT 字段与六标的硬输入通过，future evidence=`0`，结构化 state/保护正确且六动作均 NO_POSITION_MUTATION。accept 后交叉复核发现五个持仓标的共 120 条动作反事实文字沿用 Cycle 16 mark 名义/open risk，另有 6 条前序轮标签错误；纯 validator 未捕获，accepted decision 不得覆盖。run 已以 `ACCEPTED_CYCLE_0017_ACTION_COUNTERFACTUAL_LOT_TRUTH_CONFLICT` write-once 中断，checkpoint=`INTERRUPTED_OUTCOMES_SEALED / completed=17 / next_uncompleted=18 / accepted_state_digest=497702fd... / no pending / resume_allowed=false`，future context/outcome 与 V1 decisions/outcomes 仍 sealed。完整事故报告=`reports/cycle-0017.md`、SHA-256=`35e9bc3d6fbe5a245381bf1480a0c3549617fd268e46cd186a323a2bb8f3bd31`；Cycle 18–24、terminal、evaluate 与原定后续复盘全部取消，不恢复本 run。
- 新窗口 heartbeat 清理：**删除控制面受阻，但不影响 durable fail-close**。对 `v1-3` 的四次正式 delete 调用均超过 60 秒无响应并终止；第四次发生在 `2026-08-05T04:31:23.526Z` heartbeat，本地记录随后复核仍为 ACTIVE。未直接改写 Codex automation 文件、未创建替代任务；连续失败后停止自动重试，需在 Codex UI 手动删除。若它再次唤醒，只能报告 run 已中断，不得采集 Cycle 18。

### 需求变更记录

- 2026-08-04：用户要求在全新窗口继续实验，因为当前窗口上下文压缩严重、可能影响实验进程。本变更只授权上下文载体迁移，不扩大市场、自动化或外部执行权限。

## 二十六、中断后自动修复与 successor 连续研究

### 用户最终需要的交付结果

- 用户明确否定“永久中断后每小时重复播报、等待人工删除”的行为；研究控制器遇到故障时必须先保全 write-once 证据，再在授权范围内自动诊断、修复并恢复研究推进；
- Cycle 17 已接受工件和旧 run 继续不可改写，不能伪装为恢复 Cycle 18；本次恢复必须停止旧 `v1-3` 心跳、修复接受前事实一致性校验，并以新的 run_id、genesis、chronology 和冻结合同启动合法 successor；
- 自动恢复只覆盖本地不可执行公开数据研究，不扩大到账户、凭据、paper/live、真实订单或资金。

### 验收标准

1. 旧 run 保持 `INTERRUPTED_OUTCOMES_SEALED / completed=17 / resume_allowed=false`，Cycle 18 不采集、不打开，任何旧 accepted decision/state/receipt 不改写；
2. 旧 `v1-3` 不再处于可唤醒的 `ACTIVE` 状态；优先使用 Codex 正式自动化接口，若正式接口连续阻塞，则只对已精确核验的本地 automation 记录执行可逆 `PAUSED` 修复并复核；
3. 在 accept 前，validator 必须把每条 action counterfactual 中的当前 lot 数量、mark 名义、mark-to-stop 风险与当轮 pre-state 机械交叉核对，并拒绝上一周期数值复用；
4. `dynamic_update_summary` 的 prior-cycle 标签必须由 `cycle_index - 1` 机械生成或验证，不允许手工沿用错误轮次；
5. 故障策略必须区分：接受前可恢复错误允许在同一 cycle 内按冻结 fallback 有界修复；接受后的 write-once 事实冲突必须封存旧 run，并自动创建全新 chronology successor，不能无限重复状态播报；
6. successor 除 identity、授权元数据、实现 digest 与自动恢复条款外，保持 Core v2.1、v3 手册、风险、成本、102% 初始成本、三政策、评价和停止条件不变；
7. successor 使用新 genesis 的公开无凭据 PIT 数据，当前 Codex 仍是唯一 Strategy Agent；准备完成后至少推进 fresh Cycle 1，并为后续周期只保留一个精确绑定的递进任务；
8. 全程保持 `LOCAL_PAPER_RESEARCH_NON_EXECUTABLE / NONE_LOCAL_SIMULATION`，不恢复 E0/E0B、旧 automation、Agent 集群、Critic、transport、插件或指标平台。

### 当前范围与明确不做

- 当前只处理造成研究停摆的最小垂直切片：旧心跳停用、两项接受前真值校验、自动恢复状态机、successor 冻结/启动、fresh Cycle 1 和唯一后续 heartbeat；
- 不修补或续跑旧 Cycle 18，不读取旧 run 的 future outcome，不根据 Cycle 17 后价格调整市场理论、仓位比例、stop、target、风险、成本或评分；
- 不把 successor 启动、validator PASS 或 Cycle 1 accepted 称为预测有效、盈利或生产就绪。

### 当前主要任务与状态

- 强制冷启动、HEAD/工作树、旧 run checkpoint/中断边界：**已复核**；本轮起点 HEAD=`27be857b3bd62f46e51bd83d2549293802b09808`，需求记录中的 Cycle 2–17 变更作为本主线历史保留；旧 run 仍为 `completed=17 / next_uncompleted=18 / resume_allowed=false`，Cycle 18 未采集或打开；
- Codex 正式 automation delete/view 再验证：**接口受阻，但失效心跳已可逆停用**；两次正式调用分别超过 60/15 秒无返回并终止，随后按本节授权只把精确文件 `/Users/wt/.codex/automations/v1-3/automation.toml` 的状态从 `ACTIVE` 改为 `PAUSED` 并现场复核，没有删除目录、修改 prompt 或创建并行任务；
- accept 前真值校验：**已完成**。决策 schema 升为 `1.3.0`；每标的由 pre-state/current mark 生成含 open lot 数量、mark 名义和 mark-to-stop open risk 的 `position_truth_digest`，144 个动作路径必须引用该 digest，四个叙事字段禁止重复数值仓位事实；`dynamic_update_from_cycle_index` 必须等于当前 cycle 减一，文字轮次冲突会失败关闭。用真实 Cycle 17 SNDK decision 重放得到 `ACTION_COUNTERFACTUAL_UNSTRUCTURED_POSITION_TRUTH`，证明旧冲突会在 accept 前被拒绝；
- 自动恢复实现：**已完成**。新增 `recover-prospective`：只接受精确绑定 `INTERRUPTED_OUTCOMES_SEALED / resume_allowed=false` predecessor 的授权合同，在临时 staging 中采集 fresh genesis，成功后原子移动为新 run；失败不留下同名半成品，且 recovery receipt 明确 `state_or_context_reused=false`。新中断回执不再硬编码“网络中断”，而区分 post-accept truth conflict 与未分类失败；
- successor 授权合同：**已冻结并用于启动 fresh successor**。路径=`config/theory_paper_v2.prospective_24h.v1_4_authorized_20260805.json`，physical SHA-256=`76a1bfee9703c8e6ca4aba56043e1979063dc9c4def236f048eea4292a21a3fb`、canonical digest=`3d5d60a78aa88cc9412af986339f60eb35e07f994d2b9b6d654f66063c522c58`；除两项 pre-accept 真值绑定和自动恢复控制外，理论、v3 手册、风险、成本、102% 初始成本、三政策、评价与 24h 时钟不变；
- 聚焦验证：**已完成**。39 项 single-agent/prospective 回归通过，CLI 可见 `recover-prospective`，7 个 implementation binding 均与实际 SHA-256 一致；
- fresh successor genesis：**已完成且与旧 run 隔离**。新 run=`single-agent-prospective-24h-v14-20260805t074500z`，decision genesis=`2026-08-05T07:46:01.409Z`、terminal due=`2026-08-06T07:46:01.409Z`；manifest/recovery digest=`a3d16c6a0a474a01dcbf7f13aca3db69436e0f90e45104fcfff9b45de15aa9ce / 22c8d9bcb49dd6e83d8df240b8c89d6d3e36b98fc038bfef623dcf5e1da6bf2d`，recovery receipt 明确未复用 predecessor state/context。旧 v1.3 run 仍为 `INTERRUPTED_OUTCOMES_SEALED / completed=17 / next_uncompleted=18 / resume_allowed=false`，Cycle 18 未采集或打开；
- fresh Cycle 1 数据采集与 PIT 硬校验：**已完成**。公开无凭据市场请求 `108/108`、新闻查询 `6/6` 成功；acquisition digest=`5477e09af5d12e70e29fd09e41d36a239f626b6cbc367055c964ef4751716f03`。六标的 instrument、mark、provider-confirmed closed 15M 与 `available_at<=decision_at` 通过；高周期使用 direct/fallback/完整 UTC 聚合/UNKNOWN 路由，严格 order-book replenishment resilience 和完整 liquidation history 继续保持 UNKNOWN，未补零、未访问账户或订单接口；
- fresh Cycle 1 唯一 Strategy Agent 判断与 write-once accept：**已完成**。Agent 对 SNDK/BTC/SOL/HYPE 持有受保护 CORE；以 `OPEN_TACTICAL` 在 MU 建立 `500 USDT` 战术仓，entry=`891.388242`、stop=`874`、target=`931.65`、成本后计划 RR=`2.12325194076253199327291112`；ETH 在高周期弱势、主动卖压与 15M 下轨吸收并存时 `REDUCE_CORE 25%`，保留 `75%` 受保护 CORE，没有把失败挑战或固定目标机械编译成全平。决策/state/receipt digest=`32eb796ea594ed852ffbec6fc1105129eceb588939c450691387b12e18610add / 973ce3fcaa89ea3ff066fe6b5e5163fa9f4e4f9c0f820ec4fb741492966952b7 / 85ce3dd83a2f5ee6d8783d3ce00980504f08fde715c7543c531b924de1b7e8e4`；当前 checkpoint=`RUNNING_OUTCOMES_SEALED / completed=1 / next=2 / no pending context`；
- fresh Cycle 1 风险、成本与同条件对照：**已复算**。Agent equity=`9917.475044996000799840031994`、net PnL=`-82.5249550039992001599680064`，其中 fees=`0.374975`、gross=`4349.900019996000799840031994`、open risk=`76.20395043026481552711394887 / 297.5242513498800239952009598 USDT`、unprotected lots=`0`。STATIC_V1 与 DETERMINISTIC_CONTINUOUS 的 Cycle 1 equity 均为 `9918`；Agent 的主动调整已产生 `0.524955... USDT` 即时交易摩擦，尚无后续 outcome，不能据此排序政策或宣称预测/盈利；comparator digest=`47700f9c12f9402e2b3e5f21b3ba7f8df7b409eb041ef19b3b0cfb14b4e9a446`；
- fresh Cycle 1 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v14-20260805t074500z/reports/cycle-0001.md`、SHA-256=`8cd3cab23b59e909aa6723dd0dacbe7739f86e2624734c107557f7fada6aaa72`；覆盖采集质量、PIT、多周期、D/L/C/F/R、新闻情绪、事实到政策推论、每标的五条稳定竞争路径、八类动作比较、逐 lot/费用/风险/保护、复核义务和三政策；
- fresh Cycle 2 数据采集与 PIT 硬校验：**已完成**。manifest due=`2026-08-05T08:46:01.409Z`，实际 decision_at=`2026-08-05T09:17:10.987Z`、lateness=`1869s`，仍在冻结 90 分钟上限内；公开无凭据市场请求 `90/90`、新闻查询 `6/6` 成功，acquisition/context/collection receipt digest=`a742882f6a51dd0a63ce10d529b75c289472ca339f3a61cd9a6189c08d8cca32 / f346bb373b39403f1b5d896789f8b838a1d9ed188def6852bcfb1f37aa701527 / 54675c8032ee9e8e696c0d94a7fa678619c32b9d029df6e885b8fb8cf36a53e3`。六标的 instrument、正 mark、各 `299` 根 provider-confirmed closed 15M 和全部 `available_at<=decision_at` 通过；SNDK/MU 周线各仅 `22` 根闭合行，技术状态保持 UNKNOWN，strict R、完整 liquidation history、固定小时 taker ratio 和缺失 crowding ratio 均未补零；
- fresh Cycle 2 确定性 replay：**已完成并先于 Agent 判断应用**。`2026-08-05T08:00:00.000Z` 的公开 realized funding proxy 合计 `-0.2014048555644632325213853132 USDT`；Cycle 1 的 MU TACTICAL lot 于 `2026-08-05T08:44:59.999Z` 在 `MUUSDT:15m:1785918600000` 按冻结 `STOP_FIRST` 规则以 `873.7378` 止损成交，费前损失=`-9.900535573813413616914188554 USDT`、止损 fee=`0.2450497322130932931915429058 USDT`。该事件是决策前 durable 事实，不是本轮主观事后退出；
- fresh Cycle 2 唯一 Strategy Agent 判断与 write-once accept：**已完成**。SNDK/BTC/ETH/SOL/HYPE 均 `HOLD` 受保护 CORE，没有新增风险；MU 原回撤吸收 hard invalidator 已满足，episode=`INVALIDATED`，本轮 `WAIT` 并保留空仓机会成本、`2026-08-05T09:46:01.409Z` 复核和未来只可先 `REPLACE` 新 episode、再比较 `REENTER_TACTICAL` 的义务。六标的均保留五条稳定 path_id、`UNKNOWN_NO_VALID_COMPETITION_SET`、lead/runner-up/OTHER、八动作三路径反事实和逐标的 position truth digest；纯验证与 accept 决策/state/receipt digest=`73cc00d4d9cb5f8990208e43c217a07b1dc32e2080a636595f3e75c1c0faa3e8 / 0952a3a50d0b909153d9affcc4466db8957260339acadaf0f87b5269f68cbb05 / acb3c7a5dc297fce4790bf754b640a0e8d55f64243b45ddb30b485983e2d8b59`；六个动作均 `APPLIED`，risk veto、action fidelity failure、state continuity failure 均为 `0`；
- fresh Cycle 2 风险、成本与同条件对照：**已复算**。Agent equity=`9918.450737393766567583822382`、net PnL=`-81.54926260623343241617761797`，realized/unrealized PnL=`-14.95053557381341361691418855 / -65.7772974446424622735505012 USDT`，fees/funding=`0.6200247322130932931915429058 / -0.2014048555644632325213853132 USDT`，gross=`3861.222702555357537726449499 USDT`，open risk=`77.38104768359504650342572261 / 297.5535221218129970275146715 USDT`，unprotected lots=`0`。同一冻结 context 下 STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD equity=`9930.045814727858080648525417 / 9930.650242219504437188386248 / 9930.045814727858080648525417`，comparator digest=`fcd3f801c05ca7f84a5f61bd33f45a7b90827d15146d3d3327992221f453a2de`；两轮过程读数不用于调参、政策定论或预测/盈利声明；
- fresh Cycle 2 完整中文报告与最小修复：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v14-20260805t074500z/reports/cycle-0002.md`、SHA-256=`bf71a95e246f1bc5351491795f54b45110fac1755023d65fe78922420bb54e26`、`1885` 行；覆盖来源/失败/UNKNOWN/时间谱系、多周期、D/L/C/F/R、新闻和跨市场、五层推论、五路径、evidence ledger、48 类动作卡的 144 条路径反事实、逐 lot 成本/stop/checkpoint/risk/funding/fee、reentry/review 和三政策。首次报告构建因 runtime 子目录启动时仓库根不在 Python import path 而在写文件前失败；accepted 工件未变，随后仅显式绑定已验证仓库根并重跑同一只读构建成功，没有修改市场事实、理论、动作或评价；
- fresh Cycle 3 数据采集与 PIT 硬校验：**已完成**。manifest due=`2026-08-05T09:46:01.409Z`，实际 decision_at=`2026-08-05T10:19:15.272Z`、lateness=`1993s`，仍在冻结 90 分钟上限内；公开无凭据市场请求 `90/90`、新闻查询 `6/6` 成功，acquisition/context/collection receipt digest=`df150edb2f8dd289b4cbd332526c4f05f797c96e4877fbc64d1a40930ca8afbf / 362c19b27dd83f466d4a1a5286050961427906c87e7f38054cce5fc5fb500c5c / 1f4e7ec65a4b25fa8a287134b580f5ab8829e2f2e724709ad059b6e2f2544646`。六标的 instrument、正 mark、各 `299` 根 provider-confirmed closed 15M 和 `3465` 个 `available_at<=decision_at` 通过，future exposure=`0`；SNDK/MU 周线技术状态、strict R、完整 liquidation history、固定小时 taker ratio 和缺失 crowding ratio 继续 UNKNOWN，未补零；
- fresh Cycle 3 确定性 replay：**已完成并先于 Agent 判断应用**。本轮 `bar_replay_events=[]`，没有新增 barrier、target 或 funding 结算；上一 accepted state 的 MU 止损与累计 funding 只作为 durable 历史进入，不作新证据重复计数；
- fresh Cycle 3 唯一 Strategy Agent 判断、纯验证与 write-once accept：**已完成**。SNDK/BTC/ETH/SOL/HYPE 均 `HOLD` 受保护 CORE，MU 维持 FLAT `WAIT`，六动作均 `APPLIED`、无 risk veto、无仓位 mutation、开放 lot 全部有 stop。路径发生真实动态更新：BTC/SOL 以 `RANGE_REFORMATION` 领先，ETH/SNDK 以 `NORMAL_PULLBACK` 领先，HYPE 以 `TREND_CONTINUATION` 领先，MU 维持 `EXHAUSTION_OR_FAILURE` 领先且旧 episode 继续 `INVALIDATED`；六标的均保留稳定五路径、`UNKNOWN_NO_VALID_COMPETITION_SET`、lead/runner-up/OTHER、八动作三路径反事实和 position truth digest。accept 前纯验证有界发现并修复两项候选契约错误：schema 不允许 `UPDATE/INVALIDATED`，改用冻结契约支持的 `INVALIDATE/INVALIDATED` 保持失效；旧 invalidated geometry 的 `valid_until` 已过期，更新为本轮冻结 path expiry。两项修复均发生在 Cycle 3 accepted 文件不存在时，没有复活旧 thesis 或修改市场事实、理论、风险、成本、评价；最终 decision/state/receipt digest=`aa34607564986c37bc58d537458e28ee2da8ccc353e47443b9997148de3a602d / b0525244633b78d401ad846a604f240a31926ad21129a48b2a99792015e1ed9e / 761d1ac51a36ff2054462a88f0fb928f0bcc48efb0663aede39c96edd239b619`；
- fresh Cycle 3 风险、成本与同条件对照：**已复算**。Agent equity=`9910.738866701548292419592696`、net PnL=`-89.26113329845170758040730447`，realized/unrealized PnL=`-14.95053557381341361691418855 / -73.4891681368607374377801877 USDT`，fees/funding=`0.6200247322130932931915429058 / -0.2014048555644632325213853132 USDT`，gross=`3853.510831863139262562219813 USDT`，open risk=`69.66917699137677133919603611 / 297.3221660010464487725877809 USDT`，unprotected lots=`0`。同一冻结 context 下 STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD equity=`9922.148839330761089306144524 / 9924.826665854585751098380757 / 9922.148839330761089306144524`，comparator digest=`c1b41f071870ecb24f26eef29b336f9c21b79507bb389400c5b6862898f20b68`；三轮过程读数不用于调参、政策定论或预测/盈利声明；
- fresh Cycle 3 完整中文报告：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v14-20260805t074500z/reports/cycle-0003.md`、SHA-256=`42dd619828607f583979bf1f88785e2b907df3c9d74a9e45a43c2dc47444438b`、`1877` 行；覆盖采集来源/成败/UNKNOWN/时间谱系、多周期、D/L/C/F/R、新闻和跨市场、五层事实到政策链、稳定五路径的序数支持/反证/expiry/switch/hard falsifier、48 类动作卡的 144 条真实仓位路径反事实、逐 lot 成本/stop/checkpoint/risk/funding/fee、reentry/review、两项 accept 前最小修复和三政策；
- fresh Cycle 4 数据采集与 PIT 硬校验：**已完成**。manifest due=`2026-08-05T10:46:01.409Z`，实际 decision_at=`2026-08-05T11:17:50.781Z`、lateness=`1909s`，仍在冻结 90 分钟上限内；公开无凭据市场请求 `108/108`、新闻查询 `6/6` 成功，acquisition/context/collection receipt digest=`48e6684ec7b4a9d7d3d52b6dbd3f0133d5c1fdbd3acfdf369275f72a4f43e723 / 5c84b60e605b5b8dbf2036d56e313d2c37003f7d2ed094338a5d3e30df508fe1 / c4721ab78d13bda917c46f0b58c5b9b70f16c24d70341582b814c035ad970c60`。六标的 instrument、正 mark、各 `299` 根 provider-confirmed closed 15M 和 agent context 中 `1469` 个 `available_at<=decision_at` 通过，future exposure=`0`；hourly taker ratio、global account long-short ratio 和 recent public liquidation rows 本轮可得，但 top-position ratio、strict R 与完整 liquidation history 继续 UNKNOWN，SNDK/MU 周线各仅 `22` 根而保持 UNKNOWN，缺失未补零；
- fresh Cycle 4 确定性 replay：**已完成并先于 Agent 判断应用**。本轮 `bar_replay_events=[]`，没有新增 barrier、target 或 funding 结算；上一 accepted state 的 MU 止损与累计 funding 只作为 durable 历史进入，不作新证据重复计数；
- fresh Cycle 4 唯一 Strategy Agent 判断、纯验证与 write-once accept：**已完成**。SNDK 新闭合 1H/15M 失速、latest-N 卖压与 OI 一小时收缩约 `7.187%` 使 `EXHAUSTION_OR_FAILURE` 升为 operational lead；旧 4H UP 和完整小时主动买盘保留 `NORMAL_PULLBACK` runner-up，因此 Agent 选择 `REDUCE_CORE 25%` 而非全退，卖出数量=`0.08687372729989505653742172678`、模拟成交=`1404.189106`、费前实现=`-5.51285852787256666689832994 USDT`、fee=`0.06099357073606371666655083505 USDT`，剩余 SNDK CORE=`0.2606211818996851696122651803` 且原 stop/checkpoint 不变。BTC/ETH/SOL/HYPE 均 `HOLD` 受保护 CORE，MU 维持 FLAT `WAIT`；六动作全部 `APPLIED`、0 risk veto、0 unprotected lot、0 action fidelity/state continuity failure。48 个动作比较、144 条绑定当前 position truth 的路径反事实、稳定五路径和 `UNKNOWN_NO_VALID_COMPETITION_SET` 首次纯 normalize 验证即通过，无 fallback 或最小修复，随后才 write-once accept；decision/state/receipt digest=`a749982b5299c31d8fa99d445b65c31b856a3f1d9706f10ec5e490d776169afa / e76f9ad7fb1a41cf578db1f4bb88bb059677cf15a53fb392696e950eb068780d / cb823afb13da327598c1cdf33285fe36babddce5b30e58dc3762748af920adb1`；
- fresh Cycle 4 风险、成本与同条件对照：**已复算**。Agent equity=`9907.947432678690587256818551`、net PnL=`-92.05256732130941274318144928`，realized/unrealized PnL=`-20.46339410168598028381251849 / -70.70675006110981221698945174 USDT`，fees/funding=`0.6810183029491570098580937408 / -0.2014048555644632325213853132 USDT`，gross=`3728.793249938890187783010549 USDT`，open risk=`64.82756294319230385598988562 / 297.2384229803607176177045565 USDT`，unprotected lots=`0`。同一冻结 context 下 STATIC_V1、DETERMINISTIC_CONTINUOUS、INITIAL_STATIC_HOLD net PnL=`-80.92070153015605718808956149 / -86.64673036896194712881554647 / -80.92070153015605718808956149 USDT`，comparator digest=`5c267e1a2ccac32ed51e6a8a14859737d8acbe9360325a147e5e43433df893a1`；四轮过程读数不用于调参、政策定论或预测/盈利声明；
- fresh Cycle 4 完整中文报告与首个四周期复盘：**已完成**。报告=`.runtime/theory-paper-v2-prospective/single-agent-prospective-24h-v14-20260805t074500z/reports/cycle-0004.md`、SHA-256=`d2ad76148a10e78f8456c332c9c868f33adc0c888c1562858633c08d037aa8dc`、`1902` 行；完整覆盖采集来源/成败/UNKNOWN/时间谱系、多周期、D/L/C/F/R、新闻与跨市场、五层事实到政策链、稳定五路径的序数支持/反证/expiry/switch/hard falsifier、48 类动作卡的 144 条真实仓位反事实、逐 lot 成本/stop/checkpoint/risk/funding/fee、SNDK 局部成交、reentry/review 和三政策。首个四周期复盘确认流程、路径、动作、保护和数据边界均按冻结合同工作，同时明确四轮过程净值不足以修改 Core v2.1、v3 手册、102% 初始成本、风险、成本、三政策、评价或停止条件；
- fresh v1.4 当前 durable 状态：**已复核**。checkpoint=`RUNNING_OUTCOMES_SEALED / completed=4 / next=5 / no pending context`，accepted_state_digest=`e76f9ad7fb1a41cf578db1f4bb88bb059677cf15a53fb392696e950eb068780d`，V1 decisions/outcomes 未打开；Cycle 5 固定 due=`2026-08-05T11:46:01.409Z`，本 heartbeat 已精确推进一轮，不得继续提前或同次推进 Cycle 5；
- 唯一 successor heartbeat：**已建立并现场复核**。Codex 正式 automation create 调用超过 120 秒无返回且没有生成目标记录，终止后按本节已授权 fallback 只新增精确记录 `/Users/wt/.codex/automations/v1-4/automation.toml`；`v1-4 / v1.4未见实验自动修复续跑 / ACTIVE / hourly / target_thread_id=019fcc52-c1ab-7b70-b249-dfeb1892e773`，其余研究 automation（包括旧 `v1-3`）现场均为 `PAUSED`，没有第二个 ACTIVE 推进者。新 heartbeat 只绑定 v1.4 run 和本线程，每次从 durable checkpoint 推进一个到期周期；接受前可恢复问题允许最多两条冻结边界内的修复路径，接受后真值冲突则封存并仅在已有授权合同时创建全新 chronology，不得退化为重复状态播报。

### 需求变更记录

- 2026-08-05：用户指出持续播报永久中断状态是严重控制失败，并明确要求 Agent 遇到问题时自动修复、使研究持续推进。本变更授权在既有本地不可执行研究范围内停止失效心跳、修复根因并启动全新 successor；不授权篡改旧 run 或扩展到真实交易。
- 2026-08-05：`v1-4` heartbeat 按 durable checkpoint 只推进已到期的 fresh Cycle 2；公开 PIT 采集、确定性 barrier/funding replay、唯一 Strategy Agent 决策、纯验证、write-once accept、三政策复算、完整中文报告和同一需求记录更新均完成。MU TACTICAL 的冻结止损被真实重放并使原 episode 失效，未重入或升级 CORE；当前 `completed=2 / next=3`，继续等待 manifest 的 Cycle 3 due。
- 2026-08-05：`v1-4` heartbeat 按 durable checkpoint 只推进已到期的 fresh Cycle 3；公开 PIT 采集、无新增事件的确定性 replay、唯一 Strategy Agent 动态决策、两项 accept 前有界最小修复、纯验证、write-once accept、三政策复算、完整中文报告和同一需求记录更新均完成。当前 `completed=3 / next=4`，只等待 manifest 的 Cycle 4 due；本次 heartbeat 不提前采集 Cycle 4。
- 2026-08-05：`v1-4` heartbeat 按 durable checkpoint 只推进已到期的 fresh Cycle 4；公开 PIT 采集、无新增事件的确定性 replay、唯一 Strategy Agent 对 SNDK 的四分之一 CORE 减持、首次纯验证通过后的 write-once accept、三政策复算、完整中文报告、首个不改规则四周期复盘和同一需求记录更新均完成。当前 `completed=4 / next=5`，只等待 manifest 的 Cycle 5 due；本次 heartbeat 不继续推进 Cycle 5。

## 二十七、Cycle 4 理论忠实度与事件留痕审查

### 用户最终需要的交付结果

- 判断 Cycle 4 的一句式 heartbeat 播报究竟只是用户可见汇报缺失，还是研究本体已经在市场分析、理论推论、状态连续、动作选择或事件记录上出现严重偏离；
- 给出基于 Cycle 1–4 已接受工件的证据分层裁决，明确哪些流程真实发生、哪些只能由长报告声称、哪些缺少机器可验证事件；
- 若存在严重问题，必须指出具体断点及其对继续实验可信度的影响，不能用报告长度、validator PASS 或三政策文件存在代替合格研究。

### 验收标准

1. 审查快照固定为 `completed=4 / next=5 / accepted_state_digest=e76f9ad7...`，不打开或采集 Cycle 5 及任何 later outcome；
2. 逐项核对 PIT 数据、上一 accepted state 消费、确定性 barrier/funding replay、唯一 Agent 输入、D/L/C/F/R 与新闻、多路径更新、八动作比较、最终动作、逐 lot 风险成本、write-once accept 和三政策对照；
3. 检查是否存在独立、不可变、按顺序可重放的事件链，而不是仅由 decision/state/receipt/report 的最终快照和自然语言描述推断流程；
4. 区分用户可见播报失败、报告可审计性缺口、理论/政策偏离、状态或仓位错误、前视和结果证据不足，不把它们混成单一结论；
5. 本轮只读审查，不改写冻结合同、Cycle 1–4 accepted 工件、市场决策、风险、成本、评价或 automation，不用 Cycle 5 后结果评判 Cycle 4。

### 当前范围与明确不做

- 当前只审查 v1.4 fresh Cycle 1–4 和直接绑定的冻结合同、checkpoint、context、decision、state、receipt、raw acquisition、报告与 comparator；
- 不读取旧 v1.3 future outcome，不恢复旧 Cycle 18，不启动或推进 Cycle 5，不访问账户、凭据、paper/live、订单或资金；
- 不在裁决前修代码、补事件、重写报告或增加新平台。

### 当前主要任务与状态

- 冷启动权威文档、HEAD、工作树和 Cycle 4 durable checkpoint：**已复核**；审查起点 HEAD=`6933b4033256858e91539e491bb3a2f4acd48d19`，工作树仅含 v1.4 heartbeat 已追加但尚未提交的 Cycle 2–4 需求记录；Cycle 5 工件不存在；
- Cycle 1–4 PIT、状态、仓位与成交链：**已完成审查，结构性通过**。Cycle 4 的 `108/108` 市场请求、`6/6` 新闻查询、`1469` 个 `available_at<=decision_at` 字段及逐请求 raw hash/时间收据存在；Cycle 1–4 的 `pre-state -> decision -> accepted state -> receipt` 摘要逐轮相互绑定，实际动作包含 MU 战术开仓/止损、ETH 与 SNDK CORE 局部减持及其他 CORE 持有，不是全程空仓，也未发现 future exposure、未保护 lot、状态摘要或成交数量冲突；
- Agent 理论推论与动作比较：**存在 P0 严重偏离，未达验收**。Cycle 4 确有逐标的多周期、D/L/C/F/R、新闻/跨市场、五层认识论链和具体 lead/runner-up；但实际 728 行 decision builder 先在每标的 `CONFIG` 中指定 `selected`，随后才把同一动作标为 `HIGHEST_CURRENT_RELATIVE_UTILITY`。`144` 条动作路径结果去掉 `symbol/action/path` 标签后，四个叙事字段各只剩 `8` 套按动作分类的通用文本；`30` 张路径卡的核心 thesis/favorable/adverse/falsifier 等只剩 `6` 套文本。现有 validator 只比较含标签的完整字符串，因此标签不同即可绕过 `ACTION_COUNTERFACTUAL_TEMPLATE_REUSE`，与上一节“拒绝通用动作模板”的验收直接冲突；
- 新证据到 belief 的连续更新：**存在 P0 严重形式化缺口**。validator 会复算 dependency-group 去重后的 `net_ordinal_delta`，但只检查 `support_level` 是否属于枚举，没有把它与上一 accepted support 和本轮 delta 绑定。Cycle 2–4 共发现 `10` 次方向上无法由当轮 ledger 解释的支持变化；例如 Cycle 4 SNDK `NORMAL_PULLBACK` 获得 `+2` delta 却从 `DOMINANT` 降为 `SUPPORTED`，`TREND_CONTINUATION` 在 `0` delta 下从 `SUPPORTED` 降为 `WEAK`。因此 evidence identity/去重有效，但“只用新增证据更新上一战略状态”尚未成为机器不变量；
- 严格事件留痕与 Agent 归属：**P0 缺失**。run 内没有独立 `PathEvent / UpdateReceipt`、`prev_hash/chain_head` 过程事件链，也没有模型 invocation/call/attempt/timing receipt；`agent_attestation` 只是 decision 内的自述。Cycle receipt 可靠绑定 context、pre-state、decision、accepted state 和已应用动作，但不绑定候选修正过程、comparator 结果、中文报告、四周期复盘或报告 SHA-256。Cycle 4 comparator digest 只存在于报告，报告摘要在主 run 内无引用；因此可证明最终接受对象，不能严格证明“Agent 如何得出它”或报告未被主链外改写；
- Cycle 4 四周期复盘与用户可见汇报：**未达验收**。1902 行报告确实存在，但复盘只给流程/路径/保护/数据的概括表，没有按冻结要求逐项审查预测与实际前缀、路径捕获、机会差、加仓利用、退出/重入延迟；“复盘已完成”属于过度结论。heartbeat 的一句式最终播报也没有向用户交付每轮完整数据、理论链、路径变化、动作权衡和仓位结果，直接违反逐轮可见汇报目标；
- 市场结果边界：**证据过早且当前不占优**。截至冻结 Cycle 4，Agent net PnL=`-92.0525673213094 USDT`，分别落后 STATIC_V1 `11.1318657911534 USDT`、落后 DETERMINISTIC_CONTINUOUS `5.40583695234747 USDT`；仅四轮且含主动调整摩擦，不能据此判定市场策略失败或修改规则。SNDK 的 `25%` 减持方向有具体 PIT 理由，但比例没有与 25/50/75、剩余风险或成本后路径效用比较；当时 SNDK mark-to-stop risk 仅约 `8.5423 USDT`、单标的 cap 约 `99.0795 USDT`，不是硬风险所迫，仓位尺度仍属未充分说明的 Agent 判断；
- 严重性裁决：**已完成——当前实验不是数据/账本全坏，也不是重新退化为全程空仓；但已出现足以阻止“严格遵循理论”结论的 P0 Agent 决策形式化、belief 更新和事件可审计性缺陷。Cycle 1–4 只能保留为有 PIT 与状态真值的诊断前缀，不能继续称为完整理论已按预期运行或四周期复盘已验收**；
- 唯一推荐下一步：**本审查不越权改 automation；应先暂停 v1.4、封存 Cycle 1–4，不在原 chronology 内补事件或改决策。仅实现一个最小 successor 垂直切片：选择动作前形成可审计的逐动作效用记录，支持等级必须由上一值与结构化新增/撤销事件转移，且单一链式 cycle receipt 同时绑定 Agent 调用/尝试、validator、accept、comparator、报告和 4 小时复盘；通过真实非模板样本后再从 fresh genesis 启动**。

### 需求变更记录

- 2026-08-05：用户认为 Cycle 4 的一句式完成播报信息严重不足，无法确认 Agent 是否遵循理论和系统，也看不到严格事件记录，要求审查项目是否已经严重偏离方向。

## 二十八、暂停实验、根因重构与完整研究理论审查稿

### 用户最终需要的交付结果

- 立即暂停唯一 ACTIVE 的 `v1-4` heartbeat，保持 Cycle 5 零采集、零打开，并把 v1.4 Cycle 1–4 原样封存为诊断前缀；
- 在全部已知问题得到根因级解决和验证前，不启动、恢复、准备或调度任何新实验、successor、paper/live 或外部执行；
- 不再通过增加自然语言门禁、字段数量或报告长度掩盖问题，而是重做决策形成顺序、连续 belief 更新、仓位尺度比较、过程事件链、报告绑定和四周期复盘主链；
- 整理一份单一、完整、可供用户逐条审查的当前研究理论，明确市场假设、证据层级、多周期职责、竞争路径、情绪解释、连续状态、动作/仓位、风险成本、事件记录、实验流程和失败裁决，并说明其与 V1 已知问题的对应关系。

### 验收标准

1. `/Users/wt/.codex/automations/v1-4/automation.toml` 精确由 `ACTIVE` 改为 `PAUSED` 并复核；checkpoint 保持 `completed=4 / next=5 / no pending`，Cycle 5 不创建任何 context/raw/decision/state/receipt/report；
2. v1.4 形成独立停止/封存收据，绑定 manifest、checkpoint、Cycle 4 accepted state、暂停原因和“不得续跑”结论；不修改 Cycle 1–4 任一 accepted 工件；
3. 删除“先指定 selected、后生成比较”的决策中心：未来候选动作及仓位尺度先形成 sealed evaluation set，最终选择只能引用已存在的候选与评价摘要，评价生成不得读取 selected action；
4. 动作比较不再依赖自然语言查重门禁。确定性代码负责逐候选真实数量、成交成本、剩余风险、最坏损失和可行性；Agent 必须对 lead、runner-up、OTHER 的不同市场过程给出具体差异，并解释次优动作和仓位尺度未选原因；
5. 路径 support 不再由 Agent 任意覆写。状态 reducer 从上一 accepted active evidence state 加本轮 `ADD / SUPERSEDE / EXPIRE / SOFT_CONTRADICTION / HARD_FALSIFIER` 事件计算独立路径支持；缺失和静默不降低支持，任一变化均可重放；
6. 每轮形成单一追加式 event chain，至少覆盖 collection、PIT admission、barrier/funding replay、Agent context、Agent proposal/attempt、deliberation、selection、risk decision、state accept、comparator、report、review 和 completion；每个事件带 sequence、prev digest、payload digest、actor、时间和 evidence boundary；
7. checkpoint 只有在 cycle completion receipt 同时绑定 decision/state/action receipt、comparator result、完整中文报告及到期 review 后才推进；accept 后报告失败只能从已封存输入确定性恢复，不能重做市场判断；
8. 四周期复盘必须由结构化工件计算预测前缀、路径捕获、动作忠实度、机会差、加仓利用、退出/重入延迟、费用/funding 和回撤，报告只是该工件的展示，不得用概括表冒充完成；
9. 完整理论审查稿必须清楚区分 Agent 自由与确定性代码边界；不得创建 Agent 集群、Critic、transport、插件/指标平台或第二决策中心；固定外部数据适配器只服务 PIT 研究；
10. 聚焦验证必须包含真实非模板多标的样本、selected 字段注入不影响 evaluation、support 转移可复算、事件链断裂失败、报告/comparator 未绑定不得推进、四周期复盘缺项失败、旧 Cycle 1–4 摘要不变；只有用户审查理论并再次明确授权，才可另建 fresh genesis 实验。

### 当前范围与明确不做

- 当前只暂停/封存 v1.4、重构现有单 Agent 研究主链、补充直接相关测试并提交一份完整理论审查稿；
- 不读取 Cycle 5 或其他 future outcome，不修改 v1.4 决策、仓位、风险、成本、比较政策或评价，不从 Cycle 4 后价格调整任何市场规则；
- 不建设通用 Agent 平台、插件系统、消息 transport、角色集群、独立指标模块或新数据平台；一个真实阻塞只允许一个最小抽象；
- 本节完成只证明理论和研究流程可审查、状态转换可复算、事件链完整；不证明预测有效、盈利、paper/live 或生产就绪。

### 当前主要任务与状态

- 冷启动权威文档、HEAD、工作树、v1.4 checkpoint 与 automation：**已复核**；起点 HEAD=`a7f07d361079d60c7a203015e7af19efa67c0a86`，工作树干净；暂停前 checkpoint=`RUNNING_OUTCOMES_SEALED / completed=4 / next=5 / no pending`；
- 暂停 heartbeat 与写入封存收据：**已完成**。`v1-4` 已精确改为 `PAUSED`；v1.4 checkpoint=`INTERRUPTED_OUTCOMES_SEALED / completed=4 / next=5 / no pending`，interruption digest=`0a7326be0fb2f750c753c80552ea64d5e065fafede1d5564c088c3cf7372c7e1`，明确 `successor_creation_authorized=false / resume_allowed=false / DISABLED_USER_REVIEW_REQUIRED`；Cycle 5 的 context/raw/decision/state/receipt/report 均不存在；
- 根因架构、决策/belief/event/completion 主链实现：**已完成本地非执行切片**。`domain/research_integrity.py` 由 active evidence lifecycle 事件确定性计算 belief，且 selection 字段不能进入 evaluation phase；逐候选复算数量、成交成本、risk/cap、最坏损失和 25/50/75/100 尺度。`infrastructure/research_cycle_store.py` 形成固定单链事件、post-accept deterministic tail 与 completion 后 checkpoint advance；`application/continuous_cycle.py` 只编排该单链；没有集群、Critic、transport、插件或指标平台；
- 四周期复盘和用户播报：**已完成本地合同**。structured review 计算 lead prefix、action fidelity、path capture、opportunity difference、add utilization、reentry delay、fees/funding 和 drawdown；`presentation/continuous_cycle_report.py` 要求每轮直接展示采集、理论来源、推论链、路径、动作尺度、仓位交易、风险成本、对照、问题与证据，不接受一句式“已完成”；
- 完整研究理论审查稿：**已完成**。路径=`CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md`，SHA-256=`b353274dc90ae7af1493577b872032b00a845553db6f2512d6cce709cbaa86ef`；明确 D/L/C/F/R/K、情绪、多时间尺度、竞争路径、belief reducer、episode/CORE/TACTICAL/reentry、两阶段单 Agent 选择、风险成本、执行语义、事件链、三政策、复盘、失败归因和用户审查项；状态仍为 `DRAFT_FOR_USER_REVIEW / NONE_UNTIL_EXPLICIT_USER_REAUTHORIZATION`；
- 聚焦验证：**已完成**。SNDK/ETH Cycle 4 已发生事实驱动的非模板多标的候选样本、selection 注入拒绝、support 静默保持/替代/反证/硬失效与 digest 重放、event chain 断裂、report/comparator/review 未绑定失败关闭、completion 幂等恢复、完整用户摘要均通过；Theory Paper V2 范围共 `257` 项回归通过；Cycle 1–4 的 context/pre-state/decision/state/receipt 摘要逐轮回绑，Cycle 5 八类候选路径仍全部不存在；
- 定向提交：**已完成**。核心交付 commit=`d4c5e77`；实验仍保持暂停，唯一外部下一步是用户审查理论稿并决定修改或接受。

### 需求变更记录

- 2026-08-05：用户明确授权暂停实验，要求所有问题未解决前不得继续实验；要求从市场金融、理论形式化和 Agent 决策形成的根因解决，而不是继续增加门禁；同时要求整理当前完整研究理论供人工审查。

## 二十九、理论与全部实验演化总审查

### 用户最终需要的交付结果

- 汇总成一份单一、完整、可独立审查的项目研究谱系文档，记录从原始理论到当前理论候选的全部关键迭代、每次变化的原因、保留与废弃内容及当前状态；
- 逐项登记当前能够找到证据的全部主要系统实验，分别说明真实正确事实、错误或过度结论、暴露问题、根因、已采取修复、剩余未验证事项和证据等级；
- 给出当前最终理论候选的完整市场逻辑、Agent 与确定性代码边界、连续状态与仓位决策流程、实验方法、失败裁决和明确非声明，供用户决定接受、修改或否决。

### 验收标准

1. 报告以当前仓库权威文件、git 历史、冻结合同、checkpoint、interruption receipt、raw/evaluation/audit 工件为证据，不以旧聊天摘要替代 durable 事实；
2. 覆盖原始研究思想、Core Theory 各关键版本、V1 形式化、V2/E0/E0A/E0B、历史固定窗口、首个 prospective、v1.3、v1.4 及当前根因重构，不把不同实验或证据等级混为一体；
3. 每个主要实验至少列出目标、状态/完成度、正确事实、错误或误判、市场/金融问题、Agent/状态/执行问题、已修复项、未解决项及能证明与不能证明的结论；
4. 清楚还原原始理论如何从“极值与情绪压力”发展为 D/L/C/F/R/K、多时间尺度竞争路径，再发展为持续 episode、CORE/TACTICAL、动态退出/重入、结构化 evidence lifecycle、先评价后选择和完整事件链；
5. 当前版本只能标记为 `DRAFT_FOR_USER_REVIEW` 的最终理论候选；本地实现和 257 项结构回归不得冒充新未见 terminal 市场结果、预测有效、盈利或生产就绪；
6. 报告给出当前封存状态：v1.4 为 `INTERRUPTED_OUTCOMES_SEALED / completed=4 / next=5 / resume_allowed=false`，Cycle 5 不存在；不读取或采集任何 future outcome；
7. 关键数值、摘要、digest、commit 和本地工件路径可复核；对无法由当前工件支持的历史细节明确标记 UNKNOWN 或不作结论；
8. 最终只交付一份主报告并更新本需求记录，不创建新平台、Agent 集群、自动化、paper/live 或外部写入。

### 当前范围与明确不做

- 当前只做本地只读证据盘点、理论/实验演化归纳、单一 Markdown 总报告、引用校验和定向提交；
- 不修改理论正文、冻结实验、评分、风险、成本、accepted decision/state、checkpoint 或 interruption receipt；不启动、恢复或准备任何实验；
- 不读取 Cycle 5 或其他未见 future outcome，不访问账户、凭据、订单、资金、paper/live，不增加 Agent、Critic、transport、插件或指标平台；
- 本轮完成表示“研究历史与当前理论已形成可审查总账”，不表示已解决市场有效性、跨 regime 泛化或盈利证明。

### 当前主要任务与状态

- 冷启动权威文档、HEAD、工作树、v1.4 封存边界及当前理论稿：**已复核**；起点 HEAD=`3a5af6a0e5e2aff84b482f7e44d03d8153d99196`，起点工作树干净；
- 理论文档、git 演化、实验目录、审计与 durable 状态盘点：**已完成**；已覆盖原始思想的现有权威提炼、Core v1.0–v2.1、21 个主要实验/验证阶段及 P1A/HAR/PITAR 上游数据权威子阶段；原始输入 `/Users/wt/Downloads/deep-research-report (1).md` 当前不存在，报告已明确限制为根据 Core §1.4 和版本记录还原，不伪造原文；
- 单一理论与实验演化总报告：**已完成**；报告=`THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05.md`，共 `833` 行，SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`；完整记录每个实验的正确事实、错误说法、根因、修复状态、证据等级、当前 v3 最终理论候选和十项用户审查选择；
- 引用/digest/事实一致性校验与需求状态回写：**已完成**；关键 raw/evaluation/audit/checkpoint/interruption JSON 均可解析，报告中本地 `.md/.json/.html` 引用除已声明缺失的原始研究输入外均存在，Core 镜像摘要一致，v1.4 Cycle 5 的 context/raw/decision/state/receipt/report 均不存在，两条旧 automation 均为 `PAUSED`，`git diff --check` 通过；本节与主报告由本轮定向 Git 提交记录；
- 实验、automation、paper/live、账户与资金操作：**明确不做**。

### 需求变更记录

- 2026-08-05：用户要求记录全部系统实验的正确与错误信息、完整理论迭代、原始理论变化过程和当前最终理论，汇总为一份完整文档供人工审查。
- 2026-08-05：完成统一审查报告并确认最终裁决：Core v2.1 仍是当前理论权威；v3 是待用户批准的最终理论候选；根因重构只有结构性证据，尚无新的完整未见 terminal 市场结果；所有旧运行继续封存，不授权续跑或新实验。

## 三十、基于 V3 候选的当前系统全面审查、目标设计与纠正

### 用户最终需要的交付结果

- 以本需求记录、`THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05.md` 和 `CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md` 为直接输入，冻结当前代码、配置、测试和耐久工件快照，对“理论 → 证据 → 状态 → 候选评价 → 选择 → 风险/执行 → 事件/收据 → 复盘”的当前系统做端到端审查；
- 找出仍然存在的不合理设计、历史失败残留、理论与实现不一致、重复或错误的决策中心、数据所有权和模块边界问题，并区分理论失败、形式化失败、Agent 失败、数据失败、执行/账本失败与评价失败；
- 形成可落地的四层模块化目标设计、公开契约、数据所有权、事件流、扩展边界、旧系统兼容/退役路径和三阶段迁移路线；
- 在不启动实验、不读取 future outcome、不接触账户/订单/资金的前提下，纠正当前范围内能够由本地事实证明的问题，并以聚焦回归和工件一致性检查验证。

### 验收标准

1. 审查前锁定工作区、分支、HEAD、未提交用户文件、理论/配置版本和所有 ACTIVE/PAUSED/封存状态；不得覆盖用户已有修改，也不得把历史摘要当作当前运行事实；
2. 三份指定输入完整阅读并交叉核对当前理论权威：Core v2.1 仍为已批准边界，V3 仅为 `DRAFT_FOR_USER_REVIEW` 候选；本轮可以纠正实现和设计缺陷，但不得静默批准理论参数或授权新实验；
3. 映射当前主入口、应用编排、领域对象、基础设施适配器、数据所有权、公开调用、事件/工件写入和测试覆盖，明确当前真实主链及仍在旁路的 legacy 路径；
4. 每项问题必须有文件/调用链/工件/测试依据、影响、根因、失败类型、优先级和处置结果；UNKNOWN 保持 UNKNOWN，不以字段存在、mock/PASS 或报告长度替代有效性；
5. 目标设计严格采用 Presentation / Application / Domain / Infrastructure 四层；模块只通过版本化 API、事件或 schema 交互，每个共享对象有唯一 owner，每个模块可独立运行或具备 mock，并给出架构图、模块表、IO 契约、事件流、数据 schema、扩展结构、三阶段路线、验证门和 legacy 兼容策略；
6. 纠正优先覆盖会改变决策结果或研究可信度的 P0/P1：理论 authority 漂移、selected-first/双决策中心、belief 非确定性写入、合法动作或仓位尺度静默缺失、WAIT 无义务、数据时间边界/UNKNOWN 漂移、执行成本/成交语义不一致、event/completion 未绑定、评价与报告反向成为权威；
7. 不因“全面”扩建通用 Agent 平台、新数据平台、插件市场、消息中间件或新权限系统；扩展点只形成当前设计和最小契约，除非现有核心纠正必须，不新增运行依赖；
8. 修改后运行与风险相称的聚焦测试及现有相关回归；必须验证 selected 字段不能污染评价、reducer 可重放、完整合法动作集/尺度比较、UNKNOWN/available_at 边界、事件链断裂失败关闭、完成收据绑定、legacy 入口只作兼容适配；
9. 交付单一主审查/设计/纠正文档和必要代码/契约/测试修改，回写本节状态；明确“已纠正的结构问题”和“仍需未来未见实验回答的市场问题”，不得声称预测有效、盈利、paper/live 或生产就绪；
10. 所有 v1.4 Cycle 1–4 accepted 工件、checkpoint、interruption receipt 和 E0/E0B 冻结权威保持不可变；不创建/恢复 automation，不进行网络采集或任何外部正式写入。

### 当前范围与明确不做

- 当前范围：本地三份权威输入、当前 `trade_system/theory_paper_v2` 主链及其直接配置/测试/工件绑定、仍能进入主流程的 legacy 适配层，以及对研究结论有直接影响的相邻模块；
- 明确不做：运行或恢复任何 E0/E0B/prospective/paper/live 实验，读取 v1.4 Cycle 5 或其他 future outcome，访问账户、凭据、订单和资金，改变既有 accepted 决策/状态/收据；
- 明确不做：为了形式完整而全仓重构、引入新框架/服务/付费依赖、建设通用插件平台或并行 Agent 集群；
- 本轮结构性纠正只证明契约、状态转换和研究流程与候选理论更一致，不证明 V3 的市场机制、参数映射、跨 regime 泛化或盈利能力。

### 当前主要任务与状态

- 需求边界、非目标与验收标准：**已登记**；
- 三份指定文档完整读取与理论权威冻结：**已完成**。Core v2.1 仍是当前理论权威但不附带新实验授权；V3 SHA-256=`b353274dc90ae7af1493577b872032b00a845553db6f2512d6cce709cbaa86ef`，继续保持 `DRAFT_FOR_USER_REVIEW`；
- 当前模块、调用链、数据所有权、事件链、legacy 路径和测试证据映射：**已完成**。真实 CLI 仍由约 `5411 + 2391` 行旧应用模块支配；`continuous_cycle / research_integrity / research_cycle_store / continuous_cycle_report` 的直接消费者仍只有测试，v1.4 冻结运行中新增 process event/completion receipt 数量为 `0`；
- 问题总账、根因裁决与四层目标设计：**已完成**。主报告=`SYSTEM_REVIEW_AND_V3_CORRECTION_DESIGN_2026-08-06.md`，`482` 行，SHA-256=`1680d3e797b627b31ce4ea575f06a2d6356bb596293f94c00b6fd322d8c55056`；登记 `R-01` 至 `R-30`，给出严格 Presentation / Application / Domain / Infrastructure 四层、对象 owner、模块 IO、事件流、最小 registry、legacy 只读兼容、动态开放边界、新窗口可靠性与三阶段迁移；
- 范围内 P0/P1 纠正：**第一批当时已完成；后续继续需求已完成其余本地项**。新增 current research authority，历史模板的 `start_authorized=true` 不再构成当前授权；prepare 只有在冻结理论、精确 operation/run/template digest 和授权收据同时匹配时才能通过。动作原型新增 registered failure trigger、25/50/75/100 数量一致、WAIT 复查义务、跨候选 process identity 与不夸大模型身份；事件原型新增真实文件 containment、物理 SHA、语义 digest、固定 actor 及 pre-state/decision/action-receipt 显式绑定；
- 原待完成核心纠正：**已由下方“解决全部已知问题”继续需求关闭**。新 coordinator 已接管合成 CLI；旧 mutation CLI 已收敛；position truth 已补全 lot/role/order/margin/leverage；四周期指标只从 receipt-bound artifact 推导。V3 理论冻结与新市场实验仍未授权；
- 聚焦验证与回归：**已完成**。旧历史授权模板在进入 collector 或创建 run root 前失败关闭；selected 注入、belief reducer 重放、动作/尺度、registered trigger、WAIT、平台收据、真实 artifact、actor、链断裂、decision/action receipt 完成绑定、post-accept deterministic tail 与 authority status 均覆盖；Theory Paper V2 全范围 `264` 项测试通过，`compileall`、`git diff --check` 通过；
- 主审查/设计/纠正文档和本需求状态回写：**已完成**；
- 实验、automation、future outcome、paper/live、账户、订单和资金操作：**明确不做**。

### 需求变更记录

- 2026-08-06：用户要求根据本需求记录、8 月 5 日理论与实验演化审计及最新 V3 理论，对当前系统做全面审查和设计，找出不合理与失败之处并进行纠正。
- 2026-08-06：完成端到端审查和四层目标设计，并实施第一批失效关闭纠正。当前裁决为 `NO_GO_NEW_RESEARCH_RUN / PARTIAL_CORRECTION_COMPLETE`：结构契约已有本地证据，真实入口迁移、lot 级状态与来源绑定 review 尚未完成；V3 未经用户冻结前不继续 Phase 2 或任何实验。
- 2026-08-06：用户继续要求“解决全部已知问题”。本变更沿用同一主线，授权完成剩余本地系统纠正，但不等于批准 V3 理论、授权新市场实验、恢复 automation 或授予 paper/live/账户/订单/资金权限。

### “解决全部已知问题”继续需求

#### 用户最终需要的交付结果

- 让新连续周期核心成为可由真实 CLI 调用、可独立运行的本地主路径；旧 v1.4 入口只保留明确的只读兼容能力，所有旧 mutation 命令失败关闭；
- 将聚合 `position_truth` 升级为 lot/role/stop/order/margin/leverage/account-equity 完整状态，动作必须指向具体 lot，CORE/TACTICAL 的减仓、退出和重入语义可验证；
- 四周期 review 只能从物理 SHA 与语义 digest 均已绑定的 accepted artifacts 推导，不再接受调用方任意填写指标；
- 消除新主路径中的层间反向依赖和双重数据 owner，形成 Presentation / Application / Domain / Infrastructure 四层的真实实现、公共 ports、mock 和独立测试；
- 用一个全新临时目录中的离线 fixture chronology，通过真实 CLI 完成一轮及四周期边界，不访问网络、不调用模型、不读取冻结 future outcome，并证明完整 event/completion/checkpoint/recovery 主链。

#### 验收标准

1. 新 CLI use case 只能通过 Application ports 调用 Domain；Presentation 不直接访问 store，Domain 不访问文件/网络，Infrastructure 不导入 Application；新增自动化依赖边界测试防止回退；
2. 新主路径按固定顺序生成真实 artifact、事件和 completion receipt；checkpoint 仅在 comparator、report、到期 review 全部绑定后推进，post-accept 恢复不重新调用 Agent；
3. action evaluation 输入包含唯一 lot、`CORE/TACTICAL` role、逐 lot quantity/stop/risk、pending orders、account equity、margin used/available、gross/net exposure、leverage cap；任何数量、role、stop、order 或风险汇总不一致均失败关闭；
4. 每个减仓/止盈/退出候选必须声明 `target_lot_ids`，确定性计算按 lot 数量验证 25/50/75/100 尺度；OPEN/ADD/REENTER 必须声明目标 role 和 post-action leverage/margin；
5. 每轮先生成不推进 checkpoint 的 `cycle evidence receipt`，绑定当轮 decision/state/action/comparator/review-source 等事实；structured review builder 读取并验证四个 evidence receipts 及其 artifact refs/SHA/digests，再计算 action fidelity、prefix、capture、opportunity difference、add utilization、reentry、fees/funding、drawdown；最终 completion receipt 再绑定当轮 evidence receipt、report 和到期 review并推进 checkpoint。不得让 review 依赖一个又反向绑定 review 的最终 receipt，也不得允许调用方直接注入最终指标；
6. legacy `prepare/collect/open/accept/finalize/interrupt/recover` mutation commands 默认拒绝并给出 `LEGACY_MUTATION_DISABLED_USE_CONTINUOUS_FIXTURE`；`status/evaluate/comparator` 只读能力保留，冻结 run 不迁移、不补事件、不改 checkpoint；
7. 新主路径使用 mock collector、mock single-Agent adapter、mock comparator 与 canonical local stores 独立运行；扩展 registry 只允许冻结 manifest 中显式注册的实现，不做动态扫描或通用插件平台；
8. 至少覆盖 CLI 四周期集成、lot/role/order/margin/leverage 不变量、review 来源篡改、artifact 物理漂移、actor/事件顺序、legacy mutation 拒绝、依赖方向和完整回归；
9. `CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md`、Core v2.1、v1.4 Cycle 1–4、E0/E0B 与所有 automation 保持原样；current authority 继续 suspended；
10. 完成只表示已知本地结构与流程问题关闭。没有 fresh unseen terminal 时，市场机制、预测力、跨 regime 泛化、收益和生产就绪继续标记 `UNKNOWN_NOT_EVALUATED`。

#### 当前主要任务与状态

- 继续需求、边界和验收标准：**已登记**；
- 起点快照：**已锁定**。分支=`codex/s0-research-foundation`，HEAD=`e400b64b8a986ceeb3312e4dd7e6749dc4239268`；保留用户未跟踪文件 `THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md`，并继续承接上一轮尚未提交的审查/纠正修改；
- 新主路径 ports、lot truth、source-bound review 与 CLI fixture use case：**已完成**。真实 `run-continuous-fixture` CLI 在全新临时目录完成四周期 chronology；checkpoint=`completed_cycles=4 / next_cycle_index=5`；
- legacy mutation 收敛、层间依赖门、四周期集成与全量回归：**已完成**。旧 mutation commands 统一返回 `LEGACY_MUTATION_DISABLED_USE_CONTINUOUS_FIXTURE`；旧 evaluation 改为只读；新 Application/Domain 依赖门、来源与嵌套 raw 数据物理漂移、actor/顺序、两阶段收据、公开推论和四周期来源绑定均覆盖；追加确认后的 Theory Paper V2 `275` 项测试、`compileall` 与 `git diff --check` 通过；
- 理论文档、冻结运行、automation、future outcome、网络、模型、paper/live、账户、订单和资金操作：**明确不做**。

### 最初 MSTA-HED 方向一致性与动态研究能力追加需求

#### 用户最终需要的交付结果

- 以用户提供的《基于 MSTA-HED 1.0 的自动化行情分析与半自动自动交易系统技术规范报告》、原始论述、当前 V3 理论文档和实际系统为同一证据链，审查当前系统是否偏离最初“多周期状态识别、有限假说竞争、证据持续更新、条件触发决策”的方向；
- 事实核验系统是否真正具备动态能力，而不是只有固定路径、固定指标、固定候选或模板化文本；
- 在确定性风险、事实和提交边界不下放给 Agent 的前提下，扩大 Agent 对市场机制发现、竞争假说生成、假说修订/失效/新增方向、预期形成与持续累积的有效判断空间；
- 建立完整、可追溯的市场信息记录与市场情绪分析标准：每轮保存原始分析数据、来源、时间、可用性、推导过程、情绪维度、量化结果、不确定性、关联假说和后续验证结果，供跨轮复盘。

#### 验收标准

1. 给出“最初目标 → 当前 V3 → 当前实现 → 偏离/缺口 → 纠正动作”的逐项事实矩阵，不能用文档存在或本地测试通过代替动态能力已实现；
2. 假说集合支持在每轮基于新证据新增、合并、拆分、降级、失效和恢复，不强制固定方向数；每个变化都必须有唯一 ID、父子/替代关系、证据与反证、发生时间、Agent 理由和确定性校验收据；
3. “预期不断增加”落实为可追加但不可静默覆盖的 expectation ledger；每条预期必须绑定假说、条件、观察窗口、可证伪结果、置信语义、失效条件和实际结果，重复内容去重，过期内容显式关闭，不能退化成无边界文本堆积；
4. Agent 负责开放式机制发现、假说竞争、解释和可行集合内选择；PIT、来源真实性、数值复算、风险/保证金/杠杆、状态 reducer、事件顺序和提交继续由确定性内核拥有，以“最大化有效认知功能”而非最大化权限；
5. 建立版本化市场信息与情绪记录 schema，至少覆盖价格/波动、趋势/结构、成交与主动买卖、订单簿/流动性、持仓量/杠杆、资金费率/基差、清算、跨市场/宏观、新闻/事件、数据质量和缺失项；每项保存 raw fact、derived feature、source、available_at、observed_at、lineage、quality 与 UNKNOWN 语义；
6. 情绪量化必须是多维、来源可追溯、区间/序数优先且带覆盖率与分歧，不输出未经校准的单一“多空概率”；至少记录方向、强度、拥挤、流动性压力、杠杆压力、风险偏好、事件冲击、跨周期一致/冲突和总体操作性状态，并绑定具体输入数据；
7. 每轮必须形成 market information snapshot、sentiment state、hypothesis registry delta、expectation ledger delta、Agent deliberation、action evaluation/selection 和 review source，全部进入周期 evidence receipt；缺数据保持 UNKNOWN，不得补零或用叙述替代；
8. 使用一个全新本地合成 fixture 证明：四周期内可新增至少一个原先不存在的假说方向、更新/关闭至少一条预期、记录市场数据和情绪维度，并让四周期复盘从绑定来源重建；该验证不证明真实市场预测或盈利；
9. 原始 DOCX、附件文本、V3/Core、冻结历史实验和 automation 保持只读；本轮不启动网络采集、模型调用、prospective/paper/live 或真实账户执行。

#### 当前主要任务与状态

- 追加需求、边界和验收标准：**已登记**；
- 原始 MSTA-HED 文档、原始论述、当前 V3 与代码一致性核对：**已完成并冻结基线与纠正结果**。审查报告=`MSTA_HED_ORIGINAL_DIRECTION_ALIGNMENT_AUDIT_2026-08-06.md`，`317` 行，SHA-256=`b2b584f38aa7fd01ab6ca85c2632b559ed021d9e78fc0be779df80a52ba2d14a`；基线裁决为部分一致，追加确认后的裁决=`ORIGINAL_DIRECTION_RESTORED / OPEN_CANDIDATE_RESEARCH_WITH_FINITE_OPERATIONAL_WINDOW / PUBLIC_INFERENCE_SOURCE_BOUND / REAL_MARKET_VALIDITY_UNKNOWN_NOT_EVALUATED`；
- 动态假说 registry、expectation ledger、市场信息/情绪 schema 与周期证据接入：**已完成**。Cycle 2 创建新方向 `hypothesis:event-liquidity-vacuum-reversal`；Cycle 1–3 创建、更新并 `FULFILLED` 关闭预期；Cycle 4 再新增预期；每轮保存 RAW/DERIVED/UNKNOWN 市场事实和十维 sentiment vector，并全部进入 evidence receipt；
- lot truth、两阶段周期收据和四层主路径修复：**已完成并按追加验收重新验证**。主报告=`SYSTEM_REVIEW_AND_V3_CORRECTION_DESIGN_2026-08-06.md`，`474` 行，SHA-256=`b88f66f93f4e79ab704456f4778a1d834c9b493f62036e88098ac06218a2b90a`；
- 网络、模型、实验、自动化、paper/live、账户、订单和资金操作：**明确不做**。

#### 需求变更记录

- 2026-08-06：用户补充最初理论建设材料，要求检查当前系统是否偏离原始方向，并明确要求真实动态能力、充分发挥 Agent 的认知功能、可新增方向的实时假说更新、持续 expectation 记录、完整市场信息留痕以及可复盘的市场情绪量化标准与逐轮数据。本追加要求扩大本地理论/系统纠正验收，但不扩大外部采集、实验或交易权限。
- 2026-08-06：完成追加需求与“解决全部已知问题”的本地范围验收。新四层真实 CLI 合成主链、动态假说、预期账本、市场/情绪记录、lot 真值、来源绑定 review、legacy 收敛和回归均完成；当前裁决=`LOCAL_KNOWN_STRUCTURE_AND_PROCESS_ISSUES_CLOSED / NO_GO_NEW_MARKET_RESEARCH_RUN`。真实市场机制、预测力、收益和生产就绪继续为 `UNKNOWN_NOT_EVALUATED`。

### 动态开放主导、完整推论与 Agent 能力边界确认

#### 用户最终需要的交付结果

- 在当前 Core v2.1 已批准理论边界和 V3 待审候选基础上，正式确认“动态性与开放性是研究主导原则”，避免系统重新退化为固定指标、固定方向、固定剧本或模板化结论；
- 最大化 Agent 的有效认知能力：Agent 可以发现新机制、提出新方向、形成和修订假说/预期、解释相互矛盾证据，并在完整可行动作集合内作比较；确定性内核只拥有事实时点、来源与数值校验、金融/仓位计算、风险边界、状态归约、事件顺序和提交权限；
- 将可审计的完整推论落实为独立结构化工件，公开记录“事实/未知 → 派生量 → 推断主张 → 支持与反证 → 金融机制 → 假说/预期影响 → 动作含义 → 失效条件 → 局限 → 下一观察”，并绑定当轮 evidence receipt；不得要求、保存或伪造模型的私有思维链；
- 形成一份可供人工确认的核心方向与四层系统边界文档，并以本地合成 fixture 证明开放新方向、结构化推论和来源绑定可以共同工作。

#### 验收标准

1. 明确区分“开放研究空间”和“有限操作窗口”：`FACT / MEASURE / INFERENCE / HYPOTHESIS / FORECAST / POLICY / RISK` 等认识论类型及 `PATH / MECHANISM / TRADE` 对象类型保持固定，但研究假说的语义、机制家族、方向、时间尺度和预期内容不设白名单，注册表总历史不设固定数量上限；每轮 ACTIVE budget 与 `lead / runner-up / OTHER` 仅用于有限注意力、可行动作比较和复查义务，不得阻止新方向以 `CANDIDATE/WATCH` 进入注册表或经证据与治理后晋升；
2. Agent 输入必须包含或不可歧义绑定当轮 PIT 市场信息、UNKNOWN/缺口、情绪状态、上一 accepted 假说/预期、portfolio truth、完整合法动作集合、金融/风险约束和可用扩展能力；不能只给摘要文本后声称 Agent 能力已最大化；
3. 结构化推论的每个推断主张必须有唯一 ID、类型、支持事实引用、反证/冲突引用、适用时间尺度、金融机制说明、假说/预期影响、动作含义、可证伪条件、局限和下一判别观察；所有引用必须指向本轮已接纳事实或显式 UNKNOWN；
4. 结构化推论只保存可公开审计的结论与证据路径，不保存自由文本私有思维链；确定性代码只校验引用、PIT、完整性、枚举/数值和状态约束，不替 Agent 编造市场解释；
5. 事实、派生量、推断、假说、预期、政策/动作和风险保持不同认识论层级；公共 OI、订单簿、清算、新闻或情绪代理不得被解释为个体身份、真实开平仓角色或人类心理事实；缺失清算不能补零，单次订单簿快照不能证明严格韧性；
6. 不输出未经校准的概率、sum-to-100、EV 或伪精确总分；允许序数、区间、覆盖率、分歧、lead/runner-up/OTHER 和明确 UNKNOWN，并要求说明何种新增证据会改变排序；
7. 每轮事件链新增独立推论工件事件，cycle evidence receipt 同时绑定 market snapshot、sentiment、hypothesis registry、expectation ledger、Agent context/proposal、结构化推论、评价/选择、状态、comparator 和 review source；任一物理或语义漂移失败关闭；
8. 本地四周期 fixture 至少证明：原不存在的新机制可进入注册表并成为操作 lead；推论可引用支持、反证及 UNKNOWN，能影响假说/预期并声明失效条件和下一观察；四周期 review 能从绑定收据重建；
9. 目标设计严格保持 Presentation / Application / Domain / Infrastructure 四层、ports、对象唯一 owner、mock 和独立测试；Agent/模型、数据源、存储和交易接口只作为 Infrastructure adapter，不新增第五层或通用 Agent 平台；
10. 本轮不批准 V3、不启动网络/模型/新市场实验、不读取 future outcome、不恢复 automation、不访问账户/凭据/订单/资金；本地合成验证不证明真实市场预测、增量价值、收益或生产就绪。

#### 当前范围与明确不做

- 当前范围：动态研究领域契约、连续周期应用主链、Agent/collector/store ports、本地 fixture、事件/收据绑定、聚焦测试，以及面向人工确认的核心方向文档；
- 明确不做：修改 Core/V3 冻结理论正文，扩大交易权限，建设多 Agent 平台或插件市场，接入真实模型/行情/账户，运行任何 E0/E0B/prospective/paper/live；
- “最大化 Agent 能力”在本轮仅指扩大并完整提供其合法认知输入、开放研究操作和可审计输出空间，不等于取消确定性金融/risk guardrail，也不等于当前合成 Agent 已具备真实市场判断力。

#### 当前主要任务与状态

- 方向确认、边界与验收标准：**已完成**。当前原则为“开放发现、有限注意、严格晋升、受控行动”；已批准 primitive mechanism library 与开放研究候选 registry 分层，V3 权威和外部权限均未扩大；
- 开放研究空间与有限操作窗口复核：**已完成**。合成 Cycle 2 创建无语义白名单的新方向，Cycle 3 将其晋升为 operational lead；ACTIVE budget 和 `lead / runner-up / OTHER` 仅限制当轮注意，不限制候选历史增长；
- 结构化公开推论契约、事件/收据绑定和 fixture 验证：**已完成**。新增 `public_epistemic_inference_trace` 与 `PUBLIC_INFERENCE_TRACE_SEALED`；支持、反证、UNKNOWN、金融机制、假说/预期影响、动作含义、falsifier、局限和下一观察均由 proposal、accepted state、evidence receipt、report、review source 绑定并可重放；明确 `private_chain_of_thought_recorded=false`；
- 完整 Agent 输入绑定：**已完成**。`AgentContext v2` 将完整 PIT snapshot、上一 registry/ledger/belief/accepted state、lot 级 portfolio、risk policy、合法动作集和研究能力边界封存在单一 digest；传给 Agent adapter 的对象不再包含 digest 外额外输入；
- 核心方向与四层边界确认文档：**已完成**。文档=`DYNAMIC_OPEN_AGENT_CORE_CONFIRMATION_2026-08-06.md`，`382` 行，SHA-256=`07b6eaa4b2ff8a1a538b34d0be5fe81aa5d7c836f21fb59f0b612a50c5532f3e`；包含理论/金融推论、四层架构、模块/IO、事件流、扩展结构、数据 schema、三阶段路线、验证门和 legacy 策略；
- 验证：**已完成**。Theory Paper V2 全范围 `275` 项测试通过；公开推论、动态领域、四周期主链与既有完整性聚焦 `23` 项通过；`compileall` 与 `git diff --check` 通过；
- 网络、真实模型、市场实验、automation、paper/live、账户、订单和资金操作：**明确不做**。

#### 需求变更记录

- 2026-08-06：用户进一步确认当前核心方向，要求以动态性和开放性为主导，分析谨慎且具有完整推论，符合理论与金融基础，并尽可能最大化 Agent 的有效能力。本变更强化研究认知契约和可审计推论，但不扩大外部数据、实验或交易授权。
- 2026-08-06：完成方向确认和本地纠正。新增完整封存 Agent context 与来源绑定的公开推论 trace；新方向从候选进入 operational lead 的四周期合成链通过。当前裁决=`DIRECTION_CONFIRMED / LOCAL_CONTRACT_CORRECTION_COMPLETE / CORE_V2_1_AUTHORITY_UNCHANGED / V3_DRAFT_NOT_APPROVED / NO_GO_NEW_MARKET_RESEARCH_RUN`。

## 三十一、新窗口 Agent 可靠性、恢复性与实验取消根因复核

### 用户最终需要的交付结果

- 从系统设计、可行性与稳定性角度复核“切换新窗口后大量 bug 导致实验取消”的完整故障链，不把它归因于单次模型输出或操作偶发失误；
- 对新窗口冷启动、跨窗口状态交接、Agent 输入体积与完整性、当轮事实绑定、接受前语义校验、write-once 提交、失败恢复和控制器停机逐项给出根因与纠正；
- 在新的四层连续研究核心中解决所有已经有本地事实依据的同类问题，使窗口迁移只依赖耐久工件，超限和当轮事实冲突在 Agent 调用或 `STATE_ACCEPTED` 前失败关闭；
- 保持已取消的 v1.3 Cycle 17 run 与 E0B sample 163 永久封存，不用修复工作追溯改写、继续或美化历史实验结果。

### 验收标准

1. 分别还原 v1.3 Cycle 17 和 E0B sample 163 的故障链，区分上下文交付失败、旧周期事实污染、验证器盲区、接收边界错误、恢复策略和控制面失效；不得读取封存 future outcome 或恢复两项实验；
2. 新窗口恢复必须使用机器生成、内容寻址且自带 digest 的 `resume capsule`，绑定 run/manifest/checkpoint、精确 next cycle、上一 accepted state、允许/禁止读取集合和当前 authority；聊天摘要、旧窗口上下文和人工抄写不得成为权威状态；
3. 每次 Agent 调用前生成确定性的 `agent input plan`，逐节记录必需性、传递模式、语义 digest、物理/规范字节数与预算；必需输入超限必须在调用前失败关闭，历史内容使用内容寻址引用或有界快照，不得把逐轮全文无限复制进新窗口；
4. Agent 输出与公开推论中的周期标签、lot ID、数量、mark、名义、mark-to-stop risk、动作尺度和候选引用必须由当前 `pre_state / evaluation_set` 机械复算；上一周期标签或数值即使结构合法也必须被拒绝；
5. `STATE_ACCEPTED` 之前必须形成 `preaccept validation receipt`，同时绑定 context、proposal、public inference、evaluation、deliberation、selection、risk、decision、当前周期 grounding 和全部接收不变量；报告或 review 不得成为首次发现关键事实冲突的环节；
6. 接收前所有工件只属于候选 staging，不得推进 accepted head；任一接收前失败都保持 checkpoint 在当前 cycle 且无 accepted partial state。只有验证收据通过后才能写入 accepted state；接收后的尾部必须完全确定性且恢复时禁止重新调用 Agent；
7. 失败状态必须类型化：输入预算失败、Agent 交付不完整、当前周期 grounding 冲突、接收前工件冲突、接收后确定性尾失败和控制器失联分别记录；不可恢复实验保持 `resume_allowed=false`，可恢复的接收前失败仅从已封存输入继续；
8. 控制器/heartbeat 设计必须有耐久 lease、kill switch、期望状态与实际状态分离、幂等 pause/delete；本轮只实现和验证本地契约/模拟适配器，不访问或修改任何真实 Codex automation；
9. 至少用本地测试复现并失败关闭：上下文超预算、缺失必需输入、输出截断/不完整、上一周期标签复用、旧 lot 数值/风险叙述复用、接收前部分写入、新窗口由 capsule 恢复、接收后恢复禁止 Agent 重入、控制器期望停止但实际仍活跃；
10. 目标设计继续严格采用 Presentation / Application / Domain / Infrastructure 四层，定义 ports、唯一 owner、事件流、数据 schema、扩展结构、三阶段路线、验证门和 frozen legacy 策略；不建立第五层、通用 Agent 平台或新消息系统；
11. Core v2.1、V3 草案、v1.3/v1.4、E0/E0B、历史 accepted 工件和用户未跟踪文件保持不变；不启动网络、模型、实验、automation、paper/live，不访问账户、凭据、订单或资金；
12. 本轮完成只证明已知跨窗口结构与流程故障在新核心中被机械阻断；真实模型长上下文表现、市场预测力、收益、跨 regime 泛化和生产稳定性仍为 `UNKNOWN_NOT_EVALUATED`。

### 当前范围与明确不做

- 当前范围：新四层连续研究主路径的窗口恢复契约、输入预算、当前周期 grounding、接收前验证、事件/收据/检查点绑定、本地控制器状态契约、故障注入测试及系统复核文档；
- 明确不做：修补、重放或恢复 v1.3 Cycle 17、E0B sample 163 或任何被冻结 run；读取其 future outcome；修改 automation；接入真实模型、网络行情、账户或交易；
- 不在旧 prospective 巨型应用中继续叠加修补；历史实现只作为只读事故证据和兼容边界，新纠正进入当前四层 successor；
- 不以 synthetic PASS 声称真实窗口、模型 transport、预测、盈利或生产稳定性已验证。

### 当前主要任务与状态

- 新需求、非目标与验收标准：**已登记**；
- 两条取消故障链和当前主路径映射：**已完成**。E0B sample 163 已还原为 full-packet/context-budget/receipt-gap/recovery-contract 共同失效；v1.3 Cycle 17 已还原为 current lot/cycle 语义未在 write-once accept 前交叉绑定；历史 run 均保持永久失败关闭；
- 四层可靠性设计、最小本地纠正和故障注入测试：**已完成**。新增 checkpoint self-digest、跨窗口 capsule、有界历史 view、精确 Agent input plan、完整 delivery receipt、adapter 返回前 durable transport record 及其语义/物理绑定校验、current-cycle/lot grounding、preaccept atomic receipt、typed pre/post-accept failure、sealed-stage resume、postaccept Agent 禁止重入、本地独占 lease 与 desired/actual controller reconciliation；
- 审查与设计报告：**已完成**。`NEW_WINDOW_AGENT_RELIABILITY_AUDIT_AND_CORRECTION_2026-08-06.md` 共 `527` 行，SHA-256=`7482138717576bdefed7c8f2e2731d581aa5fd96a348ea8a76f736051c010741`；主系统报告已追加第 20 节；
- 验证：**已完成**。新窗口故障注入 `17` 项、窗口可靠性与连续主链 `22` 项、Theory Paper V2 全范围 `292` 项通过；新增 transport binding 篡改注入在 proposal attempt 与 accept 前被拒绝，恢复不重复生成 proposal；`compileall`、四层依赖门与 `git diff --check` 通过；当前裁决=`KNOWN_NEW_WINDOW_FAILURE_MODES_CLOSED_IN_LOCAL_SUCCESSOR / REAL_MODEL_AND_MARKET_VALIDITY_UNKNOWN_NOT_EVALUATED`；
- 冻结实验、future outcome、automation、网络、模型和交易权限：**保持关闭**。

### 需求变更记录

- 2026-08-06：用户指出当前 Agent 系统在新窗口中出现大量 bug 并导致实验被迫取消，要求从系统设计角度复核可行性与稳定性并解决已知问题。本变更只授权本地 successor 的可靠性纠正，不授权恢复历史实验或扩大外部权限。
- 2026-08-06：完成本地 successor 可靠性纠正与复核。新窗口恢复不再依赖聊天；Agent adapter 在返回前先持久化 transport delivery，proposal/deliberation 直接嵌入并绑定完整 delivery receipt，Application 在任何 proposal attempt/event 前复核记录内容、语义 digest 与物理 SHA-256；controller 即使在收到输出后、写 proposal event 前崩溃，也从同一 input digest 恢复而不重复生成；已封存采集/proposal/deliberation 不重复调用；接收前旧周期、旧 lot 数值、transport 绑定漂移和部分提交失败关闭；接收后只恢复确定性尾部；同 run 并发窗口由本地 lease 拒绝。真实模型 transport 与真实 automation 控制面仍需另行授权的无市场 dry run，不能由本地合成 PASS 推定。

## 三十二、全新周期实验、持续监控与失败后重设计

### 用户最终需要的交付结果

- 在已纠正的新四层 successor 上启动一个全新周期研究实验，以实际运行检验动态假说、持续预期、完整市场/情绪记录、公开推论、动作比较、风险约束和跨窗口恢复；
- 持续监控数据、Agent transport、事件链、checkpoint、accepted state、报告、控制器和周期时钟；发现范围内软件问题时先失败关闭、保留原始证据，再修复并从合法耐久边界继续；
- 如果真实模型、公开数据源、窗口容量或控制面存在无法在当前边界内可靠解决的外部限制，停止原方案并基于已封存失败证据重新设计更简单、稳定的方案和框架，不降低理论、金融、PIT、来源或 write-once 验收标准；
- 历史失败实验继续不可变；本次只能创建新 run、新 manifest、新 chronology 和新控制收据。

### 验收标准

1. 启动前冻结并记录精确理论版本、实现摘要、模板摘要、数据/PIT 计划、周期数与 cadence、比较基准、成本/风险、终止规则、run ID 和授权收据；旧模板或聊天指令不能单独成为运行凭据；
2. 在任何新鲜市场周期前先通过 native Codex Agent transport dry run：当前 Codex 任务是唯一 Strategy Agent；固定非市场 synthetic payload、登记可观察的上下文/工件限制、完整文件邮箱交付收据、proposal/deliberation/postaccept 三处中断恢复、零重复 Agent 产出；无法机器证明服务模型与精确 token 时必须标记 `PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT`，不得伪称 provider-attested；失败则不得进入市场阶段；
3. 市场阶段默认仅使用公开数据和本地不可执行纸面状态；禁止真实账户、凭据、订单、资金与 LIVE/broadcast。用户本次指令不授予真实交易权限；
4. 每次只推进 checkpoint 指定且已到期的一个周期；先验证 lease、authority、manifest、上一 accepted state、event chain 和 resume capsule，再采集或调用 Agent；并发窗口、错周期、未到期和摘要漂移全部拒绝；
5. 每轮市场输入满足 PIT，保留原始响应、来源、available_at、覆盖率和显式 UNKNOWN；不得把失败请求、缺失清算、旧慢字段或单次订单簿快照补成已知事实；
6. Agent 可以新增、修订、降级和关闭假说与预期，必须产出来源绑定的公开推论和完整合法动作比较；不记录私有思维链，不输出未校准概率、sum-to-100、EV 或伪精确情绪总分；
7. `STATE_ACCEPTED` 前必须通过 delivery、current-cycle/lot grounding、金融复算、risk、完整动作集与 preaccept receipt；accept 后只允许确定性尾部恢复，不改写 accepted 工件；
8. 监控必须持久记录当前实际状态，而不是把期望状态当实际状态；每轮检查控制 lease、kill switch、采集/模型延迟、重试、数据覆盖、事件链、checkpoint、未完成 stage、重复调用、周期迟到与停止门；
9. 可修复的软件问题必须先保存 failure receipt、复现测试并完成相邻回归，只有原冻结理论/评价/市场输入未改变且恢复合同允许时才继续；否则原 run 永久失败关闭并另建 successor；
10. 连续外部失败、真实 provider 无耐久结果查询、数据覆盖无法满足硬门、控制状态无法确认或修复需改变冻结规则时，停止推进并产出重设计：问题证据、不可行假设、简化架构、迁移边界、新验证门和新 run 条件；
11. 周期报告逐轮记录市场信息、十维情绪、事实/测量/推论、假说与预期 delta、全部动作、选择、逐 lot 成本与风险、WAIT 机会成本、异常和下一复核；阶段性评价不反向修改冻结理论或规则；
12. “完成”必须区分 transport 通过、运行稳定、流程可信、市场增量、预测有效、收益和生产就绪；任何前一层通过不得替代后一层证据。

### 当前范围与明确不做

- 当前范围：先完成新实验的 authority/manifest/transport 启动门，再在通过后创建全新、公开数据、本地不可执行的周期研究 run，并配置附着于当前任务的持续监控；
- 在用户未明确批准 V3 正文前，Core v2.1 仍是唯一理论 authority；V3 只作为待审设计候选，不能被本次“开始实验”默认为已批准；
- 明确不做：恢复 v1.3/v1.4/E0/E0B，读取其 future outcome，修改历史 accepted 工件；连接账户、下单、转账、LIVE/broadcast；遇到外部限制时绕过授权、许可、付费或安全边界；
- 监控与周期推进必须使用同一 durable run 状态，不创建多个相互竞争的 heartbeat 或并行 advance。

### 当前主要任务与状态

- 新需求、默认安全边界和分阶段验收：**已登记**；
- 当前 authority、可运行入口、native Agent transport 能力、数据源与既有 automation 状态复核：**已完成**。旧 `automation-2/v1-3/v1-4` 均保持 PAUSED，旧 prospective mutation 继续拒绝；当前 authority 在市场 manifest 冻结前保持 suspended；新核心此前只有 synthetic Agent，因此新增独立 native Codex 文件邮箱而未恢复 legacy controller；
- Phase B 非市场 native Codex Agent transport dry run：**已完成并在 v1.2 最终冻结后重新通过**。最终 run=`native-codex-transport-phase-b-v12-20260806t094036z`，manifest digest=`b828d85836afc9b73daab31e2bfdaf2fabb37702e40ce05923711540c0bce37c`，final checkpoint=`COMPLETED / revision=4 / 55e7b6cdebd4d41f61aff5121a35a5539d5ba1b5f931d2dd5289623291a6d3dd`，accepted=`4edb08b84967048750f1cd504e9a9bbd406a68f40bd53501e58ee51ccc1269ac`，completion=`f78967b67688fec905784dc71551da4092c6e0d8465f96441f6b00b3cf09d632`；proposal/deliberation/postaccept 三处独立进程恢复均通过，Agent 重入、市场访问、模型 API 和交易均为 `0`，证据标签=`PRACTICAL_CODEX_NATIVE_AGENT_TRANSPORT`；
- 首个市场 pilot `native-codex-btc-pilot-20260806t0834z`：**完成 1 个周期后永久失败关闭，未来周期未启动**。实际暴露三项设计失败：新情绪合同丢失已有 coverage/dependency/conflict/timeframe 能力、controller 只校验冻结授权副本而未检查当前撤权、资金费生效时间被错误记录为观察时间。halt receipt digest=`1fc2330011ffdf269e3a460364827430d272c64f16a9c5953562c14b125ca770`，已接受工件未改写，`order_sent=false`；该 run 不得恢复；
- 失败纠正：**已完成**。情绪输入恢复到既有 `dynamic_research` 十轴、依赖组去重、覆盖率、冲突和多周期状态；完整 `market_information_snapshot` 保留原始字节、来源、PIT、缺失原因和十类市场信息；所有 CLI 动作重新校验当前 authority；资金费观察时间改为采集/服务器时间并保守处理时钟偏差；source anchor 禁止成为情绪或候选动作证据。冻结标准=`MARKET_SENTIMENT_ORDINAL_STANDARD_v1_0.md`，SHA-256=`ec7bf2cc4e57b3deacf5c3676e27b7d563652df5e394e01df4075858e54d56fc`；Theory Paper V2 全范围 `303` 项通过；
- 纠正版 manifest、授权和 config：**已完成**。唯一 successor run=`native-codex-btc-pilot-v2-20260806t0856z`；config semantic digest=`3d39c0c832bd1a4d116e4def968b801aea95907304fe51800f1817371656c83e`、physical SHA-256=`6e6d7a1b43c768afa975dad63a830d9dec425b3b6f4b4e7e27ccfed64b854d2f`；authorization receipt digest=`2cebba2db9509139f5550de35cf7969ea12cdcb475db9f6ba195cc6d772ad9a7`；manifest digest=`c5a17673d7586831394d9576950119a846dd0ff147b317039355e9f69943f4a6`。Core v2.1 保持 `FROZEN_APPROVED`，V3 保持 `DRAFT_NOT_AUTHORITY`；公开 OKX、4 周期、每小时、250 USDT 影子比较、fee=`0.0005`、slippage=`0.001`、风险上限=`10 USDT`、最低净 RR=`1.5`；
- successor 第 1/4 周期：**已完成并通过完整验收**。market snapshot digest=`84b26dc9694c0a6830eccaf747078ba4bfefbb644d77eae9e272953baea412c6`，完整市场信息 digest=`38773d3e2a2a43d1a7bc1aa6ca54a5ea9cebe79fdfe681c67031fb02d675911a`，proposal delivery digest=`2562714c994499e100f462f369f6c2309727cea0bdb396292fe0a2a5c2c57c93`，sentiment digest=`5f78309c62c817b556c0ed36ecb7180f8e198211acedf46ddd2126f5242f0774`，deterministic evaluation digest=`97212767102a91359add585a7d0be6c6ed47127b0e7b9f1ba581f6668f73edd0`，deliberation delivery digest=`e336c1948e179c6bdb41c55779bac104e27d03dc56e6a3ce265c6e432c260007`，accepted digest=`25ca9ed623d46f835196d5ce7c10d977dfd9762122ec1a3c7881e69e0a8f07da`，cycle completion digest=`9c6930990ca354aaaa4326def028d7ba7eb457c81f3cc6d5d0eb50716b6c8c26`，report digest=`15cb8bc490c0d115372a798d413c4ddb87244fc284019e98f788194c3d0b76b1`；proposal/deliberation consume 后 Agent 重入均为 `0`；
- 第 1 周期理论/金融结果：**已记录，非预测结论**。路径排序为 `h-mixed-consolidation` → `h-downside-reversal` → `h-upside-resolution`；选择=`WAIT`。价格压力=`-1/CONTRADICTORY`，结构=`0/CONTRADICTORY`，参与与流量=`-2`，拥挤方向=`+1/PARTIAL`，杠杆变化与流动性韧性=`UNKNOWN`，波动压力=`0/PARTIAL` 但不代表低波动，跨市场风险偏好和事件反应=`UNKNOWN`，周期一致性=`0/CONTRADICTORY`；多、空候选均通过固定费用/滑点/风险复算，净风险分别约 `2.7444/2.7559 USDT`、净 RR 分别约 `1.9078/1.9102`，但证据不足以选择方向；`order_sent=false`、`account_accessed=false`；
- successor 语义复核：**第 1 周期写入后发现新的 P0 理论一致性失败，run 已永久停止**。`PARTICIPATION_AND_FLOW` 的正负语义是卖方/买方参与主导，但第 1 周期把“成交量低于中位数”错误作为负向 contributor，产生 `-2/STRONG_NEGATIVE`，同时公开文字却判断“弱参与、方向未确认”；此外下一周期所需同源 OI 前向变化尚未物化为当前周期、来源绑定 fact。halt digest=`79896b0dc827ba8abad4c077c98b1a37c936c651c672fe63604f72d32d6dc290`，第 2 周期未启动，accepted 工件未改写，`order_sent=false`；
- v1.1 第二 successor `native-codex-btc-pilot-s2-20260806t0928z`：**在首周期 proposal 提交前永久失败关闭，accepted 周期数为 0**。冻结依赖组、参与/流量语义门和跨周期 OI fact 已通过 `305` 项回归及两次真实公开预检，但首轮新鲜输入暴露通用加法仍会把 `3` 个上向周期与 `1` 个下向周期误算为强正向 `TIMEFRAME_COHERENCE`，且非零 contributor 的符号尚未由确定性内核与数值 fact 对齐。halt digest=`94cd269d8a2cb93d913a31ef0641d092261e5867ed1ff5157cd62756744421b7`；未提交 proposal、未 accept、未启动未来周期、未下单；
- v1.2 纠正、配置与全量验证：**已完成**。累计标准=`MARKET_SENTIMENT_ORDINAL_STANDARD_v1_2.md`，SHA-256=`b67bc8fc24e5c5bef1f47a25eca31be7e994e9b7cc2354a6b1fb31dc0348a4ea`；矛盾轴强标签上限、`TIMEFRAME_COHERENCE` 关系型聚合、直接数值同号门和精确四周期状态绑定均已落地。Theory Paper V2 全范围 `307` 项通过；最新 OKX 公开预检实际命中 `15m<0 / 1h,4h,1d>0`，得到 `0/CONTRADICTORY`，强矛盾违规=`0`；
- 最终 config、授权与 successor：**已冻结并启动**。run=`native-codex-btc-pilot-s3-20260806t0942z`；config semantic digest=`8de86115c2ec6a627409ff52d13676b05ddfa0e1d69010b797f6cd950516383f`、physical SHA-256=`624e1cfa0c146739366e0d549542b954662ef54225c663d27326c09493c72ef3`；authorization receipt=`ff00f872fb3bbf20804fd181c4ef8fcbb4c0b595d1ab0def759c27419c75a2e7`；manifest=`53d6a65f1f222416040cb1bbd7fed41e6c1c9bd46c28d9c0866e6b52c346f2f8`；Core v2.1 保持唯一 authority，V3 仍为 `DRAFT_NOT_AUTHORITY`；
- 最终 successor 第 1/4 周期：**已完成、接受并通过后置语义复核**。snapshot=`9edea443b940a1b3353d91ec2c3ab53f778ba9b830f40a5c90348b52573429d6`，sentiment=`bc777140c6f3ad4b88a81322cd0453ac8db8e0a19b83cbf7834f8ab7af55eae8`，proposal payload=`75ab70ae72049b9c9f6bb0b3e744d8cf4a23ad6c814157fce44e363b1455b0b2`，evaluation=`5724576bb5c9d938d9dfd5825c4fc912320c764d56c7555a0138ac4dadf9c6bf`，accepted=`451eae1db96897a7d89e734a4df30a1774ba2414ae389a05283039b13d3d96bc`，report=`840724992070aed6c1bb97716a356c3c247044acc973f0ff51ef1d9cd9560fd8`，completion=`8c2f457f254e9f4278deccb3d23a07858dc9cd07360e1f9bd5ecd97583762827`；选择非执行 `WAIT`，3 个假说与 3 条预期进入 registry；所有直接数值同号、成交量贡献为零、矛盾轴无强标签、OI change 保持首周期 UNKNOWN、摘要链一致、Agent 重入为零，`order_sent=false/account_accessed=false`；
- 第 1 周期理论/金融结果：**已记录，非预测结论**。lead=`h-mixed-horizon-pullback`，runner-up=`h-upside-resumption`，OTHER=`h-downside-break`；价格压力=`+1/CONTRADICTORY`，结构=`+1/CONTRADICTORY`，参与/流量=`+1`，拥挤方向=`+1/PARTIAL`，杠杆变化与严格流动性韧性=`UNKNOWN`，波动压力=`0/PARTIAL`，跨市场与事件=`UNKNOWN`，周期一致性=`0/CONTRADICTORY`；多空候选净风险约 `2.7443/2.7558 USDT`、净 RR 约 `1.9079/1.9103`；
- 持续监控：**已恢复 ACTIVE**。唯一 heartbeat=`btc-agent` 仅绑定最终 successor，按每小时到期状态最多推进一个周期，任何数据、语义、摘要、authority、金融或后置复核异常会停止并自暂停；旧 `automation-2/v1-3/v1-4` 继续 PAUSED。当前 checkpoint=`READY_FOR_CYCLE 2 / fc18847d32db0bd09582c644d3643c4101eb9de675706830a076453dc51f912c`，next due=`2026-08-06T10:42:00Z`；
- 尚未完成：**周期 2–4 与 terminal 全链复核**。当前最高裁决=`CYCLE_1_PROCESS_AND_SEMANTIC_GATE_PASS / 1_OF_4 / MONITORING_ACTIVE`；预测有效性、收益和生产就绪仍为 `UNKNOWN_NOT_EVALUATED`。

### 需求变更记录

- 2026-08-06：用户授权开展新的周期实验并要求持续监控；发现问题时修复，若外部限制过多或问题无法可靠解决，则重新设计更好的方案和框架来完成理论实践。本记录将该授权解释为公开数据、本地不可执行研究，不包含真实交易权限；同时保留 V3 尚未明确批准这一理论 authority 边界。
- 2026-08-06：用户明确拒绝 OpenAI API key 路线，指定由当前 Codex 任务直接作为项目唯一 Agent。系统因此采用内容寻址的 native Codex 文件邮箱、阶段 claim/receipt 与 heartbeat 唤醒，不把聊天历史当权威，不创建子 Agent；模型身份与精确 token 若不可机器证明则如实保留 practical evidence 标签。
- 2026-08-06：native Codex transport 合同、四层模块、CLI 与 7 项故障测试落地；专项相邻验证 `29` 项通过。真实 Phase B run 完成三个显式中断边界，证明当前 Codex 可以通过耐久邮箱交接且 controller 不重复调用；该结果只解除 market pilot 的 transport 门，不构成市场或理论结果。
- 2026-08-06：首个市场 pilot 在第 1 周期后发现情绪合同降级、当前撤权未复核和资金费时点错误；立即写入 halt receipt、永久封存且未启动未来周期。未修改其 accepted 工件，也未发送订单；旧 run 不得在修补后续跑。
- 2026-08-06：在不改变 Core v2.1 authority 的前提下冻结十维序数量化情绪标准，纠正完整市场信息/PIT/current-authority/source-anchor 门，完成 `303` 项回归和最终 Phase B 重跑；随后创建唯一纠正版 successor、全新 config/授权/manifest。
- 2026-08-06：当前 Codex 作为唯一 Strategy Agent 完成 successor 第 1/4 周期 proposal、假说/预期创建、十维情绪、三动作比较和 deliberation；controller 验收后选择不可执行 `WAIT` 并形成 completion/report。唯一 `btc-agent` heartbeat 已绑定 successor 并恢复 ACTIVE，负责按到期时间一次推进一个周期；本阶段只证明首轮实践链路可信，不证明预测、收益或生产能力。
- 2026-08-06：对第 1 周期进行后置理论语义复核时发现 `PARTICIPATION_AND_FLOW` 将低成交量误计为卖方负向贡献，数值 `-2` 与“方向未确认”的公开推论冲突；同时跨周期 OI delta 缺少当前事实合同。该轮从“通过”改判为永久失败关闭，`btc-agent` 立即 PAUSED，第 2 周期未启动。修复必须建立 v1.1 标准和全新 successor，不得回写或续跑 `0856z`。
- 2026-08-06：v1.1 已冻结依赖组、参与/流量规则与跨周期 OI 谱系并通过 305 项回归；但在第二 successor 首轮提交前发现 `TIMEFRAME_COHERENCE` 不能沿用通用加法，矛盾轴也不应产生强标签，且 contributor 符号需与当前数值 fact 机器对齐。该 run 在 accepted=0 时失败关闭，当前 authority 悬停；继续修复不授权续跑该 run。
- 2026-08-06：用户再次确认由当前 Codex 本身担任项目唯一 Agent。v1.2 修正与最终 successor 继续禁止 API 模型、子 Agent、旧聊天状态补齐和人工伪造 transport 收据；验收新增“矛盾输入不得形成强方向、周期一致性必须由四个绑定收益率关系推导、直接数值 contributor 必须精确同号”三项失败关闭门，并要求首周期通过后再恢复唯一 heartbeat。
- 2026-08-06：完成 v1.2 修正、307 项回归、真实公开预检和最终 Phase B；创建且只授权最终 successor `s3`。当前 Codex 完成第 1 周期 proposal/deliberation，controller 接受 `WAIT` 并完成 report/completion；独立后置语义复核通过后恢复同一个 `btc-agent`。本阶段只证明首周期流程与已知语义门可信，剩余 3 个周期继续由耐久状态驱动。

## 三十三、V3.1 信息—数据—假说—路径—行为规划理论与系统升级（历史快照，已被 V3.2 取代）

本节的“当前范围”“实验进行中”和 V3.1 权限表述均只描述当时状态；现行状态以文件顶部 V3.2 段落为准。V3.1 run 已永久 `FAILED_CLOSED`，V3.2 尚无 authority、qualification、run 或 outcome。

### 用户最终需要的交付结果

- 在保留 Core v2.1、V3 草案、原始 MSTA-HED 方向和全部历史实验事实的前提下，先全面整理“当前系统实际能力—V2.1 理论—V3 草案—失败与纠正—尚未实现能力”，再形成一份自洽、可审查、可证伪的 `V3.1` 最新理论候选文档；
- `V3.1` 必须把动态性与开放性作为主导，同时用严格的认识论边界约束 Agent：开放发现信息、机制、假说与路径，不开放事实伪造、伪概率、风险计算、状态提交或真实交易权限；
- 新增完整的信息层：按信息主体的制度地位、经济职能、传播机制、受众、作用范围与时效分类，覆盖规则/政策制定者、中央银行与监管者、流动性与金融中介、发行人/公司/项目治理者、政治议程与舆论参与者、注意力/流量与社区影响者、专业交易者及其他内生参与者；同时区分可观察表达、可验证行动、推测动机、受众行为反应和市场传导机制，禁止把心理推测写成事实；
- 新增完备的数据层：统一建模原始信息、事件、市场微观结构、宏观与跨市场数据、主体/受众、时间点可得性、来源与谱系、单位与频率、覆盖率、质量、缺失、修订、潜在因子、市场状态、相关性及其变化；
- 建立“信息层 → 数据层 → 机制/相关性图 → 假说层 → 预期与未来路径 → 行为规划 → 结果与复盘”的动态图结构，使节点、边、证据、反证、相关性、状态和假说权重可以随新证据新增、修订、分裂、合并、降级、失效和恢复；
- 建立概率云与不确定性体系，允许心理学和机制分析形成明确标注的主观可信区间/序数可能性，但不得冒充经过校准的概率；把经验频率、市场隐含概率、模型后验和主观可能性分层记录，并保留 `OTHER`、`UNKNOWN`、模型不确定性、数据不确定性和冲突证据；
- 建立完整的市场分析、未来趋势、严格“如果…则…”路径和行为规划体系；每条路径都必须包含触发条件、守门条件、中间状态、可观察结果、时间窗口、反证条件、备选路径、风险与动作含义；
- 从权威经济学、金融学、市场微观结构、行为金融、宏观金融、网络与时变相关性、预测校准和稳健决策原始论文中提炼可用机制，明确论文结论、系统借鉴和不可外推边界，不用论文名称为未经验证的系统能力背书；
- 理论文档完成并审查后，再按 `V3.1` 契约全面更新现有四层系统、修复全部可复现已知问题，最后只在全量验证通过后启动一个全新的不可执行周期实验；旧 `s3` 只作为 1/4 原始基线保留，不续跑、不回写、不伪造终局。

### 验收标准

1. 在任何理论或代码修改前，暂停唯一 `btc-agent` heartbeat、撤销旧 `s3` 的当前研究运行权限，并以内容摘要冻结其 Cycle 1、checkpoint、manifest、授权、配置与完成收据；暂停是需求变更导致的基线冻结，不得篡改为市场失败或补造 halt receipt；
2. 形成逐项证据矩阵：`V2.1 定义 / V3 新增 / 当前代码实际实现 / 历史实验暴露 / V3.1 保留或纠正 / 验证方法`；文档存在、本地测试通过、API 可达、单周期 accepted 或 WAIT 均不得表述为动态能力、预测力、盈利或生产就绪；
3. 信息分类使用多轴而非互斥人物标签，至少包括主体身份与权限、经济职能、信息类型、可验证行动、受众分群、传播渠道、影响范围、时间尺度、可信度、利益冲突和市场传导；同一主体可同时承担多种角色，分类随事件变化；对“暗藏行为”的分析只能保存为有证据引用、替代解释和反证条件的 `INFERRED_MOTIVE` 或 `BEHAVIOR_RESPONSE_HYPOTHESIS`；
4. 数据对象至少拥有 `as_of / observed_at / available_at / effective_at / source / source_type / raw_ref / lineage / revision / unit / frequency / instrument / venue / actor / audience / quality / coverage / missingness / uncertainty / regime`；缺失保持 `UNKNOWN`，修订不得静默覆盖，点时可得性（PIT）和来源物理/语义摘要必须失败关闭；
5. 相关性模型必须区分无条件、条件、偏相关、领先—滞后、滚动/时变、跨周期、跨资产和 regime 条件相关；相关性边保存方向、符号、强度区间、样本/窗口、稳定性、滞后、数据质量和版本。相关性不是因果性，Granger 型预测关系也不得命名为结构因果；
6. 动态图至少包含 `InformationSource / Communication / ObservableAction / Audience / MarketFact / DerivedMeasure / LatentFactor / Regime / Mechanism / Hypothesis / Expectation / ScenarioPath / Action / Outcome` 节点，以及可版本化、可撤销的支持、反驳、传导、相关、领先、条件依赖、替代、继承和失效边；所有图更新必须产生 delta 与证据引用，禁止覆盖历史；
7. 概率云使用三层证据并区分四类对象：`SUBJECTIVE_PLAUSIBILITY`（未校准主观区间或序数，只供研究排序）、`EMPIRICAL_OR_MODEL_CONDITIONAL`（有明确样本/识别/模型合同）、`MARKET_IMPLIED_BELIEF`（有明确合约、流动性与风险溢价边界）、`CALIBRATED_PREDICTIVE_DISTRIBUTION`（经过样本外校准验证）。任何点概率、sum-to-100、EV、margin 或 entropy 只有在相应校准与完整互斥穷尽事件合同成立时才允许；否则使用区间/序数、`lead / runner-up / OTHER / UNKNOWN`，并进行敏感性与冲突说明；
8. 假说必须由信息、数据、机制与图路径共同引用生成，并保存来源、父子/替代关系、适用市场/周期、支持与反证、先验类型、概率云、关键相关边、可证伪预测、晋升/降级规则和生命周期；Agent 可新增方向，确定性内核只验证合同、谱系、引用、金融约束和提交顺序；
9. 每条未来路径采用严格合同：`IF triggers AND guards, THEN expected transition, BECAUSE mechanism, OBSERVE indicators BY horizon, INVALIDATE WHEN falsifier, OTHERWISE branch, ACTION implication, RISK/opportunity cost, NEXT review`。条件不满足时必须显式 WAIT/保持观察，不得把条件预测写成无条件预言；
10. 行为规划比较完整合法动作集合，包含不行动的机会成本、目标 lot/role、触发、失效、风险预算、费用/滑点/资金费、流动性、替代动作和复查时间；未经校准的主观可能性不得直接驱动仓位、EV 或风险预算；
11. `V3.1` 理论文档必须先于实现冻结，包含公理、认识论类型、信息分类、数据本体、动态图、概率云、相关性、假说生命周期、趋势/路径、行为规划、Agent/确定性边界、实验与证伪、已知错误路径禁令、论文依据及适用边界；在用户批准前其状态为候选理论，不静默覆盖 Core v2.1；
12. 系统继续严格采用 Presentation / Application / Domain / Infrastructure 四层；新契约优先在 Domain 定义，Application 编排，Infrastructure 实现数据/模型/存储 adapter，Presentation 仅组合与展示；不得扩建第五层、通用 Agent 平台或无关插件体系；
13. 更新后必须通过 schema/不变量、PIT/谱系、图 delta、概率类型、相关性退化、假说开放新增、路径 if–then、完整动作比较、恢复/幂等、依赖方向和既有回归；任何失败先修复再实验，不得修改评价标准适应结果；
14. 新实验使用全新 run、冻结理论/配置/输入/评价、公开或本地非账户数据、不可执行动作和耐久 checkpoint；先完成合成/历史不窥视验证，再开始有限 prospective 周期。不得恢复任何旧失败 run，不访问账户/凭据，不发订单，不触及资金；
15. 完成仅表示 `V3.1` 文档、当前范围实现和已知可复现问题关闭。真实市场机制、预测增量、校准质量、跨 regime 泛化、收益和生产就绪必须由新实验另行证明，未验证项保持 `UNKNOWN_NOT_EVALUATED`。

### 当前范围与明确不做

- 当前范围：保持旧实验安全冻结，继续唯一已创建的 V3.1 非执行实验，逐周期完成公开 PIT source、Agent 开放分析、确定性准入、accepted state、延迟 outcome 与阶段评价；
- 明确不做：回写或续跑 `native-codex-btc-pilot-s3-20260806t0942z`，修改旧 accepted 工件，读取冻结 future outcome，建设多 Agent 产品平台，使用心理推测伪造事实或校准概率，访问私人账户/凭据，发送订单或使用资金；
- 文档、Q0–Q8 与独立授权门已经完成；后续只允许在同一四层核心、同一 frozen manifest 和同一 run 内推进，不得重开资格、修改冻结规则或另建平行市场 run。

### 当前主要任务与状态

- 新需求理解、交付边界和验收标准：**已登记**；
- 旧 `s3` Cycle 1 原始证据与当前工作树快照：**已冻结**。冻结记录=`V3_1_REDESIGN_BASELINE_FREEZE_2026-08-06.md`；run 保持 `1/4`，checkpoint 语义摘要=`fc18847d32db0bd09582c644d3643c4101eb9de675706830a076453dc51f912c`，未补造失败收据；
- 旧 `btc-agent` 暂停与 predecessor 撤权：**继续有效**。旧 heartbeat=`PAUSED`；V2 predecessor authority=`FROZEN_V3_1_QUALIFICATION_PENDING`，旧 s3 仍无恢复权限。新的 V3.1 current authority 已独立冻结为 `ACTIVE_FROZEN_RESEARCH`，只授权唯一不可执行 run；
- V2.1/V3/当前实现/历史失败能力矩阵：**已完成**。主审查=`V3_1_THEORY_AND_SYSTEM_DESIGN_AUDIT_2026-08-06.md`；已区分 V2.1 认识论宪法、V3 连续运行理论、当前合成/公开行情双 schema 现状及 V3.1 纠正；
- 权威原始论文检索与理论映射：**已完成**。已覆盖信息经济学、市场微观结构、央行沟通、政治/披露、行为与注意力、中介流动性、动态相关、金融网络、预测校准、歧义决策及币市结构；每项均记录系统用途和不可外推边界；
- `V3.1` 理论文档与系统设计审查：**已完成并获用户冻结批准**。获批物理文件=`CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md`，获批 SHA-256=`ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553`；文件名保留历史的 `DRAFT_FOR_REVIEW` 只是为了不改写已批准字节，后续权威状态由独立 approval/authority receipt 表达。该批准不构成预测、盈利或生产能力证明；
- 系统更新与已知问题修复：**冻结实验所需边界已闭合，整体研究能力仍部分完成**。统一信息/PIT 数据、累计修订、动态图、冻结 Pearson/Fisher 关联、开放假说/预期、概率云、三值路径、完整研究动作、金融复算、十二轴情绪、两阶段 Agent、六阶段 chronology、跨周期继承、source admission 和 public outcome monitor 已组成同一正式主链。高级因果/关联、一般 credal set、连续真实组合、广覆盖新闻/宏观来源等不在本实验能力声明中；未知缺陷不能由现有回归关闭；
- 本地全量验证：**激活前最终范围已通过**。V3.1 聚焦 `245/245`、Theory Paper V2 全范围 `555/555`，并通过编译、JSON、理论摘要、实现摘要和变更格式检查；测试只证明冻结合同与本地回归一致，不证明真实来源语义、Agent 增量、预测或收益；
- V3.1 实验资格与启动（历史快照）：**当时已完成并进入实验；随后在首个 outcome 永久 FAILED_CLOSED**。当时 Q0–Q8、唯一 manifest、authorization receipt、active authority 和 run genesis 已冻结，Cycle 1 已 accepted 且 outcome 尚未读取；其后续终局以文件顶部和本节后续失败记录为准。旧 s3 继续停在 `1/4`，账户/paper/live、订单、凭据、资金权限始终为零。

### 需求变更记录

- 2026-08-06：用户要求先全面理解并更新需求记录，再整理当前系统能力、V2.1 与 V3，在 V3 基础上形成 V3.1；新增严谨信息层、完备数据建模、时变相关性、动态图与概率云、开放假说挖掘、未来路径、严格 if–then 与行为规划，并要求从权威经济学/金融学原始论文吸收可验证机制。文档完成后再全面更新、审查、修复系统并开展新一轮实验。
- 2026-08-06：本变更取代“继续推进旧 s3 周期 2–4”的执行顺序。旧 s3 在 1/4 处冻结为原始基线；暂停不构成实验失败，也不授权改写任何旧工件。新的理论、实现和实验必须使用新版本、新摘要与新 run。
- 2026-08-06：完成 V2.1/V3/现实现状/历史失败证据矩阵、原始论文映射、V3.1 候选理论和四层系统设计。概率云进一步把模型条件分布与市场隐含信念分开，避免把模型输出、期权/预测市场价格和校准预测静默混为一类。文档先行门完成，开始按统一 Domain 合同实施；旧 s3 继续冻结。
- 2026-08-06：完成 V3.1 当前实现子集与对抗复核。新增严格来源采集边界、数据质量两级准入、累计 revision registry、PIT 关联数值绑定、假说/预期无环谱系、概率云时间与成员迁移、三值路径—动作绑定、Agent exact inputs/candidates、金融复算及六文档语义重放；已复现的绕过路径均加入失败关闭回归。
- 2026-08-06：完成恢复边界的第二次收口：严格白名单 typed assembly bundle 已先于六阶段正式对象内容寻址落盘，checkpoint 1.1.0 逐周期绑定 bundle；全新 Python 解释器只接收 durable run root、run ID 与 cycle index，即可重建 dataset/graph/cloud/path/action evaluation 和六阶段对象并重新执行 semantic admission。缺失、歧义、篡改、重签替换与 schema/signature drift 均失败关闭；该结论仅是本地确定性跨进程恢复，不证明 Codex、网络或 automation 长时可靠。
- 2026-08-06：完成 V3.1 十二轴情绪本地合同收口：旧十轴必须显式映射，强制去杠杆与注意力/受众两项无直接数据时保持 UNKNOWN；每个 contributor 与同一 PIT dataset 的 exact datum digest、值、单位、窗口、来源、原始摘要、时间和 dependency group 逐项绑定，完整 state/change 进入 inputs、proposal、preselection、accepted、completion 与 checkpoint。信息层 intent/behavior 只能作为 hypothesis seed 或主观 plausibility，不能升级为 empirical/calibrated probability 或动作证据。
- 2026-08-06：Q2 情绪本地合同门与 Q4 耐久重放门已局部关闭；V3.1 仍为 `DRAFT_FOR_USER_REVIEW_PARTIALLY_IMPLEMENTED_NOT_AUTHORITY`，Core v2.1 保持当前权威，研究 authority 继续 suspended。新实验仍未创建，等待用户审阅冻结、实验范围与统计合同事前登记、fresh source/Agent 交付验证、固定评价以及独立授权。
- 2026-08-06：最终全量回归先复现 18 项同源兼容错误：legacy synthetic proposal 只有 evidence ID，没有新合同要求的 exact digest binding，因而在假说 delta schema 处失败。修复仅更新 Infrastructure fixture adapter，为 hypothesis、hypothesis delta 和 expectation result 绑定对应 snapshot fact 的 canonical digest，并在后续修订中继承旧绑定、追加新绑定；未放宽 Domain schema，也未回填旧 run。修复后 V3.1 核心/authority `120/120`、Theory Paper V2 全范围 `426/426`、编译、JSON、理论摘要绑定、Markdown 围栏和变更格式均通过。
- 2026-08-06：用户明确回复“我批准，并授权实验”。该消息批准冻结 SHA-256=`ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553` 的 V3.1 候选内容，并授权 readiness 文件所定义的唯一 fresh、公开数据、不可执行 `BTC-USDT` prospective 实验。授权不恢复任何旧 run，不授予账户、paper/live、订单、凭据或资金权限；必须先机械清零 Q0–Q8，并在唯一 run ID、manifest 与授权 receipt 摘要绑定后才可启动。

### 实验授权后的资格收口、正式首周期与监控追加状态

#### 用户最终需要的交付结果

- 在上述已批准 V3.1 内容与唯一非执行实验范围内，关闭全部当前已知且会破坏实验有效性、恢复性或金融一致性的阻塞问题；
- 由当前 Codex 任务担任唯一 Strategy Agent，使用完整公开 PIT 信息自行提出开放假说、预期、图变化、概率云、条件路径和完整动作候选，不使用测试 fixture 或预制最终提案冒充 Agent 能力；
- 完成唯一 fresh run 的冻结 manifest、Q0–Q8 typed receipts、实验授权、active authority、run genesis 和至少一个正式 accepted cycle；
- 每个 accepted cycle 生成不可提前读取的 1H outcome monitor plan，由耐久监控在到期后只读公开数据、记录 raw/UNKNOWN/outcome receipt 并推进独立 checkpoint；异常永久 failure-close，不恢复旧实验。

#### 追加验收标准

1. Q6 必须由 fresh、单次、公开非账户 OKX `BTC-USDT-SWAP` GET 采集形成完整 raw/request/response/PIT/UNKNOWN 耐久证据；历史失败资格保留，修复必须使用不同 qualification ID，不改写失败记录；
2. Q7 资格与正式运行分离：资格 packet 只能绑定批准与实验 subject，`experiment_start_authorized=false`；正式 packet 才能绑定 active authority。开放分析交付后必须停在 `READY_FOR_COMPILATION`，生产 semantic compiler 全量重放后才可进入 post-seal selection；旧 final-proposal fixture 不得关闭 RUN_READY；
3. Agent authoring packet 必须绑定并使 Agent 可读取真实 information events、PIT dataset、关联收据、上一状态头和权限；Agent 输出开放语义，确定性 compiler 只能补结构、摘要和金融复算，不得替 Agent 编造解释、假说、概率或选择；
4. 财务影子假设在 run 前一次冻结：`10000 USDT` 静态 FLAT shadow、费用/滑点/保证金/杠杆/风险与名义上限、唯一 entry scale/role、OKX `ctVal/ctMult/lotSz/minSz/tickSz`、保护位公式、取整和 minimum-size 规则。调用者不得周期中更改；funding 未形成 PIT settlement 合同时保持 UNKNOWN，不静默当零；
5. `portfolio_truth` 必须原生表达 FLAT，不得用 `intended_side=LONG` 的空对象冒充；合约数量按公开 step 向下取整，价格按 tick 保守取整，低于 minimum size 判不可行而非向上扩大；
6. source qualification 仍然不是 experiment start authority。正式周期只能在 active authority 后将新的 source completion 全量重放并 write-once 导入 run store，绑定 authority/contract/run/cycle/raw/snapshot/event/dataset；旧 `NONE_E0` 语义事件不得静默重签进入 V3.1；
7. 1H outcome 采用“决策后 elapsed 1H 的首个公开 PIT mark observation”，不得把任意秒决策错误等同于整点 closed candle；`not_before` 前只读状态，到期先耐久预留唯一尝试，再调用严格白名单 OKX public mark-price GET；
8. monitor raw、source record、observation、outcome receipt 和前序 receipt 链全部 write-once/CAS；UNKNOWN 计 coverage loss，超时、崩溃、篡改或已预留未交付均禁止重试并 failure-close；
9. manifest 和 active authority 只有在 Q0–Q8 全部为可重建 typed PASS 且外部证据物理重放成功后才能生成；任意 opaque 64-hex、generic PASS 或聊天摘要不能通过；
10. 完成首周期和监控启用只证明一次受控前瞻研究链已经开始，不证明预测增量、校准、盈利、跨 regime 稳定或生产就绪；八周期与全部 outcome 未结束前，实验总体状态不得写成完成。

#### 当前主要任务与状态

- 用户理论批准与实验边界：**已完成**。approval receipt 已冻结；旧 s3/E0/E0B 不可恢复，账户/paper/live/订单/凭据/资金权限继续为零；
- Q6 source qualification：**最终 fresh 资格已完成，历史两次记录保持不可变**。首个 ID 因等价 UTC 时间字符串精度比较失败而永久封存；第二个 ID=`v31-source-qualification-20260806t161918z` 虽 SEALED，但其信息事件仍使用旧 `NONE_E0` 内层标签，只保留为历史资格证据，不进入正式 V3.1 cycle。最终新 ID=`v31-source-qualification-20260806t172611z` 单次完成并 SEALED，12 个公开 GET 全部保存、读取回验，PIT dataset 共 44 条记录、5 条 UNKNOWN、`missing_is_zero=false`；completion semantic digest=`440a418c61f4c9e2aae4072f20a172d752c7909efe56614208f25a653d8d3f97`，physical SHA-256=`66be067ff05c74ffcb62f61064b8569b1072879ab49239b743e3c05b23a101fa`，checkpoint digest=`96c8a00f5215847d9c35d888a3a9df60cdb9a10d647d07ef35218248d02b4bfe`；新 external verifier 同时重放记录层与内层事件摘要并递归拒绝任意 `NONE_E0`；
- checkpoint/genesis 与权限 chronology：**正式冻结并启用**。唯一 run=`v31-prospective-btcusdt-20260806t183742z`；contract digest=`a3d66ed528f13089d05b12655de0065c835f23016c6511fee2da38ffdc72ae73`，manifest digest=`f75a37c7a6a910b30ca452b45b4ef086a17f1251b7affd60e0496109ba9017b8`，authorization digest=`034fead618a731aa47ba4ca9897a84bd46dc333bc3252672f14455d25b412579`，active authority digest=`e11ece4ce46aba8902fbe93373ed24941eab659e6177be1f07f53eac1d7a32fc`，run genesis digest=`766497fe894fa0ee827670eefd98986479f5773a81adea98d37d20db6b265531`；authority=`ACTIVE_FROZEN_RESEARCH`，执行权限仍为零；
- Q0–Q8 typed gates：**全部由最终 receipt 关闭**。每个 gate 都绑定冻结 subject；Q6 重放单次公开 source 物理证据，Q7 重放当前 Codex 两阶段耐久交付，完整 authority loader 同时验证 Q0–Q8 和 `74` 个冻结 runtime 路径。qualification digest 依次为 Q0=`fd1491ca...`、Q1=`e4379a68...`、Q2=`0d47e2e4...`、Q3=`8c32d39b...`、Q4=`4168d1ed...`、Q5=`61f58a11...`、Q6=`4316a3f0...`、Q7=`a27696ea...`、Q8=`6a91c675...`；
- Agent authoring/transport：**资格与正式 Cycle 1 均已完成**。Q7 前两个独立 root 分别因 stdin EOF 和 canonical PTY 行缓冲限制永久失败关闭，第三个 root 使用 non-canonical/no-echo byte transport 并为 proposal/selection 分别启动新 worker 后完成；正式 Agent envelope 由真实 PIT packet 产生，先停在 `READY_FOR_COMPILATION / SELECTION_BLOCKED`，生产 compiler 全量重放后才完成 post-seal selection，未使用 fixture 或预制 final proposal；
- outcome monitor runtime：**Cycle 1 唯一请求已失败关闭**。在合法窗口 `2026-08-06T19:57:31.967000Z` 先耐久预留 attempt digest=`64ce943d9840ba564ef7e178c56cb0e81ff84f10a6a7e28b9bfd157b8aba0132`，随后公开 OKX adapter 返回 `V31_OUTCOME_PUBLIC_VALUE_INVALID`；monitor checkpoint=`FAILED_CLOSED`、digest=`6745fea805fcabd5a36224792bbb7864e0431ff3dfdfcee51e367255607e8b60`，failure digest=`440e5714c2f10e2c8b5ba31582addc86c5c69b523cbf3356568c18b6879a5616`，outcome receipt 不存在且禁止重试；
- public contract specification 与 FLAT truth：**已完成本地实现**。新 snapshot 1.1 保存 `ctVal/ctMult/lotSz/minSz/tickSz` 并贯穿 market information/PIT；旧 snapshot 1.0 只读仍可重放。FLAT 只允许无目标 lot/order；
- frozen financial shadow、离散 quantity/tick 复算：**已完成本地实现与聚焦验证**。静态 FLAT `10000 USDT`、公开合约乘数/数量步长/最小数量/tick、向下取整、保守价格取整与 `funding=UNKNOWN_NOT_INCLUDED` 已进入生产复算；低于 minimum size 必须判不可行，不得向上扩张；
- 正式 source admission：**Cycle 1 已完成，Cycle 2–8 本地继承门已在 authority 前验证**。正式 source ID=`v31-source-qualification-formal-cycle1-20260806t185222z`，只执行一次公开网络采集，12 个 request、44 条 PIT datum、UNKNOWN 和 source completion 全量导入；非法 ID `...185157z` 在 plan/checkpoint/network 前被拒绝，仅留锁目录，不复用、不删除；后续周期必须精确回传 previous admission、prior snapshot 和 prior OI datum digest；
- 正式首周期：**accepted state 保持不可变，但实验已在 outcome 阶段失败关闭**。Cycle 1 decision mark=`64366.1`；lead=`SHORT`，runner-up=`LONG`，选择=`WAIT`，accepted digest=`118d5acceb71d8daf5759c4076fd668e190a931a60c9a9743d575fe9d7101ad7`。research checkpoint 仍显示 `READY_FOR_CYCLE / next=2 / completed=1`，而 monitor=`FAILED_CLOSED / resume_allowed=false`；当前控制器以 monitor 为终局并已暂停 heartbeat，因此 Cycle 2 不得启动。两个 store 未形成同一机械 supervisor gate 是新增设计缺陷，successor 必须在任何 prepare/source/Agent 前统一验证 monitor 非失败且上一 outcome 已合法解析；
- 已知冻结适配问题：**有界规避，未在活动 run 中修改代码**。presentation helper 会把 Q7 typed compiled AST 中合法的 `{kind: STRING, value: NONE_LOCAL_SIMULATION}` 深扫描为 legacy 权限而误报；处理顺序固定为先用完整 loader 验证全部授权、外部证据与冻结 runtime，再只向 Application 传入五份已验证授权语义文档。该方案不跳过完整验证、不改变值、不修改 frozen bytes；代码修正只能在本 run 结束后以新 authority 完成；
- 监控自动化：**唯一 heartbeat 在终局失败后停止**。automation ID=`v3-1-btc` 此前每 5 分钟附着当前任务并只推进一个边界；Cycle 1 outcome failure durable 后应切换为 `PAUSED`，防止重复唤醒。旧 `btc-agent/automation-2/automation-3/automation-4/flap-live/g1/v1-3/v1-4` 始终保持 `PAUSED`。
- outcome 失败根因边界：**已定位到适配器值/时间校验，但精确输入不可恢复**。异常只能来自 `mark` 非有限/非正或 OKX `ts > local received_at`；正常市场价格下后者更可能，但 raw response 未被保存，不能把推测升级为事实。结构缺陷一是 raw 仅在 adapter 完成语义验证并返回后才写入 store，导致失败响应不可审计；二是 research 与 monitor checkpoint 分离，formal prepare 不拥有统一 terminal gate。successor 必须先 write-once 保存 HTTP raw/capture、再解析，预注册时钟偏差处理，并让统一 supervisor 在 source/Agent 前机械拒绝 monitor failure/outcome gap；

#### 需求变更记录

- 2026-08-06：用户在 V3.1 文档冻结后明确批准并授权唯一新实验，任务从“候选理论与本地实现”进入“资格清零—唯一正式 run—首周期—耐久监控”阶段；授权边界没有扩大到交易执行。
- 2026-08-06：资格收口复核发现并登记五个新的真实阻塞：Agent 只收到摘要且 final proposal 由 fixture 预制；Q7 资格循环依赖 active authority；Q6 qualification-only 数据缺少正式周期准入；财务假设与合约最小步长未事前冻结；任意秒 1H horizon 被错误建模为 closed candle。纠正不得通过降低验收或复用旧结果完成。
- 2026-08-06：完成最终 fresh Q6。新资格 ID=`v31-source-qualification-20260806t172611z` 只执行一次，12 个 OKX 公开请求、raw bytes、source capture、信息事件、44 条 PIT 数据及 5 条 UNKNOWN 均耐久绑定；旧失败和旧 `NONE_E0` SEALED 资格保持历史不可变，不重签、不接纳。
- 2026-08-06：八周期运行前复核新增两个真实阻塞：semantic compiler 与 formal source admission 原本均只完整支持 cycle 1。由于 V3.1 的核心验收是动态、开放、跨周期更新，不能用“首周期可跑”替代八周期可持续性；正式 Phase A/ACTIVE authority 因此继续暂缓，先完成周期 2–8 状态继承、前序来源绑定和至少两周期耐久端到端验证。
- 2026-08-06：监控可运行性复核发现此前 Q8 只有耐久 monitor contract/runtime 与 fake observation adapter，没有生产 public mark-price 适配器。已新增严格白名单 OKX `GET /api/v5/public/mark-price` 实现与无网络响应测试；它只返回绝对 mark，路径的确认/反证阈值由预先冻结 monitor rules 负责，避免在缺少 decision baseline binding 时伪造“1H 涨跌幅”。
- 2026-08-06：Q0–Q8 最终 typed receipts 和 74 个 runtime 物理摘要全部通过后，冻结唯一 manifest、authorization、active authority 与 run genesis；V3.1 从资格态进入 `ACTIVE_FROZEN_RESEARCH`。旧实验及旧 automation 均未恢复。
- 2026-08-06：Q7 前两次独立 transport 尝试分别暴露 stdin EOF 和 canonical PTY 行缓冲限制，均在各自 root 永久失败关闭；第三次使用 non-canonical/no-echo byte transport 和阶段隔离 worker 完成。历史失败保留，不通过改写或重试同一状态洗白。
- 2026-08-06：正式 source admission 发现冻结 presentation helper 对 typed AST 内合法权限字符串的深扫描误报。因 74 个 runtime 文件已被 active authority 固定，未在运行中修补；采用“完整 loader 先验全链验证 + 五份已验证授权语义文档下投影”的有界方案，保持相同语义并避免跳过验证。修复代码留待 run 终止后的新 authority。
- 2026-08-06：当前 Codex 完成 Cycle 1 正式开放分析、semantic compile、post-seal selection 和六对象接受，选择 `WAIT`；1H 绝对 mark monitor 已事前冻结并在结果窗口前保持 `NOT_DUE`。唯一 `v3-1-btc` heartbeat 已启用；实验状态=`IN_PROGRESS`，不是完成、预测有效或盈利证明。
- 2026-08-07：Cycle 1 在合法 outcome 窗口预留唯一 attempt 后，公开 OKX adapter 触发 `V31_OUTCOME_PUBLIC_VALUE_INVALID`。monitor 按冻结规则永久 `FAILED_CLOSED`，attempt=`1`、outcome=`0`、`resume_allowed=false`；禁止重试、补取或推进 Cycle 2。失败同时暴露 raw-after-parse 设计缺陷：响应在语义拒绝前未耐久化，无法区分异常价格与 provider/local 时钟偏差；该缺口必须在 successor 中以 raw-before-parse 和预注册时钟合同纠正，并重新获得新 run 授权。
- 2026-08-07：用户进一步授权当前 Codex 持续推进直至目标实验完成。当时目标未下调为后继唯一 run 独立完成 `8/8 accepted + 8/8 legal outcome`；该 V3.1.1 标准随后已被 V3.2 的 `16 cycles / 48 schedules` 流程 pilot 取代，不能作为 V3.2 授权。旧失败 run 不计入。实施采用并行版本化 runtime，新增 atomic capture、clock policy、run-level Supervisor、commit intent、exact-five authority projection 和完整 import-closure freeze；授权仍不扩展到 paper/live、账户、订单、凭据或资金。
- 2026-08-07：用户要求解决全部已知问题，并明确加入十二轴原生公开来源/图投影、关联候选全集与统计预注册、successor fresh Q6/Q7/Q8、预测/校准/成本后收益/跨 regime 证据状态、全面检查/日志/工作区清理。当时 public-only successor 排除 portfolio/reentry 接线；该排除随后已被 V3.2 的“条件研究规划原生纳入、真实/paper 执行仍无权限”取代。评价类未知不得由工程 PASS 伪造结论，须由预注册数据评价逐项关闭。
- 2026-08-07：用户在 qualification 和 target 均未启动前要求修正过度保守的入场与仓位逻辑：允许结构磁区、短周期 RSI、相反主观假说、早期试探、证据加仓、动态减仓/退出/再入场和多时间框架缓存。该要求改变核心行为合同，故提升为 V3.2 并暂停既有 successor 冻结；portfolio/reentry 从“排除”改为“研究规划纳入、真实/纸面执行仍无授权”。用户示例中的精确收益区间、未经证实的参与者比例、任意主观概率直接分仓、绝对日线禁令和固定百分比移动止损不作为事实或硬规则，须以风险预算、相关性去重、结构/波动失效和前向比较替代。
- 2026-08-07：用户追加流动性幻觉、相对权重分母陷阱、长期无动作休眠、API/网络/venue 失效和假说路径依赖五项风险。V3.2 采用 dependency-scoped external path modifier、绝对支持先缩放后相对分配、风险计划/模型适应双耐久时钟、stop-not-fill hazard 与防换名/改时间戳续命；同时新增 PIT availability、Agent/对象资源硬上限、六臂事前 shadow bundle 和 authority projection/governing authority 双绑定。所有本地闭环完成后仍须取得 V3.2 新批准，不能沿用 V3.1 授权。
- 2026-08-09 原始五问题裁决（graph scope 细化已被下方 V3.2.6 当前节取代）：0–100 主观权重已经退役为三档；混沌/无方向/OTHER/UNKNOWN 为一等零方向状态；reentry 只是受固定 24h、两次和累计风险上限约束的观察机会；future execution capsule 不能在无账户/订单权限的 pilot 中伪造市价必然清仓。依赖 identity 不删除，因为删除会允许同一事实经多个故事重复放大；普通轮使用 pilot 有界 working set 与 delta 增量构造。现行 owner scope 不是仅限 registry 内部，而是一个 bounded qualification wake 或 owner-bound acceptance/public-evidence scope；相同 strict snapshot 只完整重建一次，append 后 snapshot key 改变会强制重建，绝不跨 wake/thread/task/process 缓存。不存在独立的固定 24h 同类证据归并能力；本文其他 `24h` 仅指 reentry churn ledger。

### V3.2.5 提交 `66197c4` 前历史状态（已被下一节取代）

#### 交付与验收状态

- 五项新理论问题：**已完成设计与实现收口**。连续主观分数已退役；混沌是一等零方向状态；reentry 是全 instrument/全方向共享的有界机会；物理逃生舱只保留 future-only 合同；热路径只处理有界 working set/delta，并保留一次完整 owning verification；
- 已知崩溃恢复与原子性缺陷：**已完成本地修复**。覆盖 Phase-A intent/整目录原子发布、secure stage 收养、真正 no-replace 激活、public source crash-prefix failure terminal、mailbox 五类 partial tail、dynamic present-unbound role、atomic audit bundle 与 legacy replay；
- 分层与公开合同：**已完成**。durable JSON 由包级 shared owner 持有，Application 不反向依赖 Infrastructure；audit public loader 不泄漏内部 binding/layout；preflight 路径固定字典序并可跨 canonical JSON 重载；
- 本地回归：**已完成提交前门**。V3.2 `738/738 PASS / 1705.807s`，全 Theory Paper `1505/1505 PASS / 2018.226s`，compile/diff check 通过；
- 工作区边界：**已完成核对**。只允许本任务 tracked 改动和新增 shared/compat 文件；用户副本保持 `63,676` bytes、SHA-256=`91ce66f9a17e98ec8989d16f0a4c8133644001c8d2b500cea6dc88f9eb156b3c`，不得 staging；旧六棵 qualification/runtime 不修改；
- 显式 Git 提交与 post-commit receipts：**进行中，尚未完成**；
- 当时第七 fresh qualification、target authority/genesis、正式周期与 outcome：**未开始**，必须使用全新 exact pair；
- fresh public source、当前 Codex 耐久交付、固定 outcome monitor 与真实 15 分钟时延：`UNKNOWN_NOT_QUALIFIED`；
- 市场预测增量、概率校准、成本后收益、跨 regime 泛化：`UNKNOWN_NOT_EVALUATED`。

#### 本轮需求变更记录

- 用户要求不要机械删除全部约束，而要把系统从“精密但易碎”改为模糊正确、快速且可执行的分析架构。最终实现保留 evidence identity 和 fail-closed 权限边界，同时删除 Agent 连续主观数字、方向强迫和同作用域重复 closure rebuild；没有采纳不可保证的“API 异常时必然市价清仓”。
- 全量回归先暴露 Application 反向依赖、audit loader 返回合同漂移，以及共享路径迁移后的 canonical 顺序问题。三项均在提交前修复并从零复跑，不以局部 PASS 或修改验收标准掩盖。
- 用户要求工作树优先提交；因此本状态之后唯一合法下一边界是显式 staging/commit，再以新 run ID 运行 post-commit qualification。任何新 tracked 修改都会使该资格重新失效。

### V3.2.5 提交后资格新暴露 P0：Agent 窗口被材料化开销提前耗尽

#### 用户最终需要的交付结果

- 保留已经通过的提交后回归与第七资格原始记录，不追写、不延长、不伪造已过期 CURRENT_CODEX 尝试；
- 修正本地逐对象唤醒使 `660s` Agent 总窗口在 claim 前被耗尽的问题，使同一高层分析许可内的 append-only 材料子阶段按冻结的 `MAX_ANALYSIS_SUBSTAGES_PER_WAKE=64` 有界连续推进；
- 为材料突发执行建立明确的停止条件：首次 `AWAITING_AGENT / READY / no-progress / QUALIFICATION_MONITOR_PROBE_*`、异常或达到上限即停止，任何单步异常沿用现有 write-once materialization failure，不隐藏部分前缀；
- 以新提交、新 post-commit receipts 和全新 exact qualification/target pair 验证修复，旧第七资格不得重试或接收迟到 Agent delivery。

#### 验收标准

1. `CURRENT_CODEX` attempt 仍只预留一次，时间纪律仍从冻结 reservation 起算；不得通过把窗口起点后移、篡改时钟或放宽 `660s` 来掩盖本地调度开销；
2. 一个公开 composition wake 可以包含最多 `64` 个 append-only material/mailbox 子阶段，但仍只对应一个高层 controller boundary；每个子阶段保持原 write-once/CAS、原时刻验证和 crash-tail 恢复；
3. burst 必须分别返回总 step 数/序列与真正发生写入的内部 append-only 子阶段数/序列；只读 `NO_ADVANCE_*` 和独立 probe 高层边界不得混计为内部子阶段。禁止空循环、超过上限、越过 Agent 等待点或在 Agent 已 REQUESTED/CLAIMED 时继续推进；
4. 从空 material prefix 到 `NO_ADVANCE_AWAITING_PROPOSAL` 的资格路径必须在冻结时限内完成；proposal delivery 后到 selection 等待点亦须满足同一约束；
5. 第七资格 `v32-qualification-btcusdt-20260809t215807z` 保持历史原件：controller=`RUNNING/revision 3`、PUBLIC_SOURCE 完成、proposal REQUESTED、claim 不存在；它只能标记为治理上的 `EXPIRED_TERMINAL`，不得伪称 runtime `FAILED_CLOSED`，其后不得补 claim、delivery、monitor 或 target authority；
6. 完整本地回归、显式提交和新的 post-commit 双收据通过后，才允许第八 exact pair 开始；工程修复仍不证明预测、概率校准、成本后收益或跨 regime 泛化。
7. `CHOPPY/NEUTRAL/UNKNOWN` 或客观硬门使全部方向风险候选 `BLOCKED` 时，`WAIT` 必须能完成 Proposal→sealed evaluation→Selection→final plan 全链；Selection 理由只能从已封存 blocked-risk refs、plan blocking refs 和 regime evidence 确定性派生，Agent 不得自填理由引用，且不得伪称存在方向候选 dominance；
8. 生产外层 composition 接口的确定性夹具回归必须证明：CURRENT_CODEX reservation 后一次 `advance` 从空材料前缀直达 proposal 等待，proposal delivery 后一次 `advance` 直达 selection 等待；两次均有 `burst_step_count>1`、controller revision 不变且单 wake 小于 `660s`。仅测试私有 helper 或允许 80 次循环不构成该 P0 的回归证据；该测试不得冒充 fresh public network 或真实 Current Codex 资格。
9. zero-eligible WAIT 不得由 Agent 自报软理由制造：typed 非方向 regime、事实完整性、path invalidation、极端不确定或 residual cap=`0` 等当前研究原因必须由 Domain 从封存状态重建；objective input 缺失必须由 compiler 对正式 packet 独立复算并要求 exact `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 系统诊断。legacy `UNKNOWN_MAX_LOSS` 只关闭未来执行，候选 `block_reason=MAX_LOSS` 必须被拒绝；完整输入下伪报 `COST_OR_LIQUIDITY`、任意 GEOMETRY 或泛化文字不得删除全部方向候选，仍须走 directional WAIT dominance。
10. owning-cause 门必须逐个覆盖所有 `BLOCKED` 候选，而非只在全部方向归零时启动。全 instrument churn 的 `OPEN_PROBE/REENTER/REVERSE` 只有在 ledger=`COOLDOWN/EXHAUSTED` 且 failure refs 精确一致时可被预算阻断；residual-risk 归零必须由 Domain 证明 cap=`0` 并绑定 exact hypothesis source refs；`RISK_BUDGET_BELOW_CLUSTER_QUANTUM` 不得用于 `HOLD/REDUCE/CLOSE`。完整输入下单边 COST/GEOMETRY 自报、AVAILABLE/RESET 假冷却、别名或引用扩大均须失败关闭。

#### 当前主要任务与状态

- 第七资格：**治理上 EXPIRED_TERMINAL、永久不可继续；runtime 原件不追写**。CURRENT_CODEX reservation=`2026-08-09T23:03:47.940793Z`，proposal request 入队=`2026-08-09T23:12:49.071891Z`；当前 Codex claim 前被 `V32_ACTUAL_CODEX_PORT_ATTEMPT_EXPIRED` 拒绝。controller 保持 `RUNNING/revision 3`，mailbox 保持 `REQUESTED`，没有 claim/delivery；
- 根因：**已定位并形成接线候选**。提交 `66197c4` 的 composition 每次外部调用只推进一个 material 子阶段，反复完整 authority replay 与进程启动把 `15` 个 material roles、mailbox initialize 和 proposal enqueue 共 `17` 个状态变更子阶段拉长到约九分钟，随后才到一次只读等待检查；冻结 runtime support 明确允许同一 active permit 内最多 64 个 append-only 子阶段且这些不是高层 boundary。当前未提交候选已接通 bounded burst，但仍须严格单次 outer-wake 回归、全量测试、提交和第八资格验证；
- 相邻混沌闭环 P0：**已定位并连续加固，聚焦回归通过**。WAIT row 按合同没有自身 evidence refs，而 dominance comparisons 精确只覆盖 eligible risk candidates；当该集合为空时旧 Selection 必然失败。新语义使用 `WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION`，引用只由封存对象确定性派生；随后又关闭伪 objective 缺失、AVAILABLE/RESET 假 churn 冷却、合法 residual-cap=0 被误杀、风险量子理由误封管理动作，以及单边 COST/GEOMETRY 软删除五条相邻路径。只有逐候选 owning cause 能改变 feasibility；directional WAIT 的既有 dominance 语义不变。当前聚焦通过，全量回归仍待完成；
- 修复、回归、新提交、新 qualification：**进行中**。第八资格只证明 qualification Agent transport；正式 target 仍须另过 PIT/graph closure 与跨周期 continuity，禁止把 qualification PASS 冒充首周期 acceptance；
- 权限：始终为 `PUBLIC_NON_ACCOUNT_ONLY / NONE_LOCAL_SIMULATION / non-executable`，不新增账户、订单、paper/live、凭据或资金能力。

#### 需求变更记录

- 2026-08-10：提交 `66197c4` 的双 post-commit 收据通过后，第七资格完成 fresh PUBLIC_SOURCE 和全部提案材料，但逐对象外部唤醒消耗了 CURRENT_CODEX 总预算，claim 被正确拒绝。该事实把“热路径增量化”从结构性优化提升为真实 P0；纠正采用合同已经允许的有界 substage burst，不后移时钟、不扩大 Agent 窗口、不修改第七资格原件。
- 2026-08-10：第八资格交付预演进一步发现 zero-eligible WAIT Selection 死路。旧编译器把 WAIT 理由限定为方向候选 dominance refs；混沌或全部硬阻断时 comparisons 按合同为空，导致合法 WAIT 无法 Selection。修复新增非方向专用 reason code，并从 sealed evaluation、sealed plan 和 market regime 三个已验证对象重建 exact refs；连续主观数值、自由理由引用和强行方向下注仍禁止。生产外层 composition 接口的确定性夹具回归同时升级为单次 outer wake 断言，避免 80 次循环掩盖旧调度回归；它不冒充 fresh 网络或 Current Codex 资格。
- 2026-08-10：独立复核拒绝了第一版 zero-eligible 测试的伪客观前提，并拒绝了外层测试的循环假阳性。完整 objective inputs 下自报 unavailable 现在必须失败；只有 owning hard gate 或 compiler 实际检测到缺失才可清空方向候选。外层回归先到 exact CURRENT_CODEX reservation，proposal/selection 各只允许一次 advance。两项加固的聚焦结果分别为 `4/4 PASS / 38.792s` 与 `1/1 PASS / 199.278s`；这些仍是确定性夹具证据，不是 fresh 网络、Current Codex 或 target acceptance。
- 2026-08-10：继续构造性复核发现 zero-all 之外仍可单边删除候选，并发现 residual-risk 合法归零、全 instrument churn 和非增险管理动作之间的原因所有权缺口。当前门已提升为逐候选验证：真实 ledger、Domain risk arithmetic、typed hard gate 或正式 packet objective 缺失各自只拥有自己的原因；其余主观判断不改变 feasibility。dynamic action plan 与新增 compiler 聚焦当前 `47/47 PASS / 40.157s`，尚不能替代全量、提交或 fresh qualification。
- 2026-08-10：用户再次要求审查“主观魔法数字、复杂度、混沌、重入磨损、理想物理环境”五项易碎性，并明确偏好模糊正确与快速执行。实现裁决是：三档继续保留且 Agent 不得提交连续值；依赖 identity 保留、但资格材料整次 bounded wake 复用同一 owner scope；非方向状态增加 Domain 自动派生的上下 typed research trigger pair；一根确认 15m close 只触发 fresh reanalysis，不自动开风险、下单或 OCO；执行核按钮在无账户/订单资格下仍保持 `NOT_IMPLEMENTED_NOT_QUALIFIED`，不得伪造必成交。
- 2026-08-10：独立构造性复核又发现五条相邻 P1：风险候选可夹带反向假说、支持证据可冒充路径失败、过期 parent 可继续 ADD、ADD/REVERSE 可复用 parent tranche ID、`INITIAL_PROBE_USED` 会误封合法反转。当前候选将风险假说收紧为 exact same-direction actionable cluster closure；failure 只接受 exact parent 的 fresh `opposing_refs` 或 active typed invalidation；parent 持久携带 `valid_until=min(plan expiry,candidate horizon,time stop)`，到期先退休；ADD/REVERSE 必须生成不同 ID；initial lock 下新的 OPEN/REVERSE 必须计入同一 attempts/cumulative 账本而非免费或一律禁止。当前仍只有一个 research-intent parent 槽位，不宣称完整多 tranche portfolio/pyramid 管理。

### V3.2.6 五项易碎性修复当前状态

- 正式 authority/schema 的兼容字段继续是 `theory_version=3.2.1`；`V3.2.6` 是该语义族内待新提交与资格冻结的文档/实现修订标签。
- 主观判断只允许三档；连续 `risk_reference_units` 仅是 sealed allocation 的 exact echo。同向 cluster 数量不再累加方向 cap，不能因故事数量或分母变小增加预算。
- 非方向候选必须 `CONDITIONAL/BLOCKED/no-tranche`，任一非空 zone ref 必须为 sealed `BREAKOUT_BOUNDARY`。Domain 已从 sealed candidate/zone 自动派生唯一上下 typed research trigger pair，固定 15m closed-close、严格 `GT upper / LT lower`、有效期和 first-match retirement；它只触发 fresh reanalysis，当前没有连续 trigger monitor、订单或 OCO 执行，不能宣称双边突破交易策略已经自动执行。
- 重入规则统一为 per-attempt `<=1`、max attempts=`2`、cumulative `<=2`、连续失败 max=`2`、单 instrument/全方向/24h 共用账本。首次 INACTIVE probe 免费但立即锁住；其后的 OPEN/REVERSE 可合法纠偏，但必须计入同一 attempts/cumulative，不能以“第二次初始单”免费重放。首次 stop 已计 consecutive=`1`，再一次失败即熔断；`ReentryObligation` 只是复核机会，不是自动重新开仓。
- research parent 现在机器绑定 exact tranche ID、方向、entry、stop、同方向 actionable cluster 假说闭包、zones 与绝对 `valid_until`；generic source/support/renewal/tier/zone observation 不能证明失败，只有 fresh opposing evidence 或 active typed invalidation 可以退休 parent。ADD/REVERSE 新 tranche ID 不得复用 parent。当前 pilot 刻意保持单 parent 路径，未实现完整多 tranche portfolio/pyramid ledger。
- 研究输入缺失使用 compiler-owned `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN`；legacy `UNKNOWN_MAX_LOSS` 与权限未知只阻断未来真实执行。future `EmergencyExecutionCapsule=NOT_IMPLEMENTED_NOT_QUALIFIED`，当前 recovery observer 不是 execution risk supervisor。
- 新增风险必须由本轮 cutoff 后、当前 PIT 可得且被 hypothesis `supporting_refs` 实际引用的新方向正证据支撑；否则 exact `NO_NEW_CURRENT_PIT_EVIDENCE_REF` 且无 tranche。FACT 必须有真实 UNKNOWN datum/source/request/citable closure owner。
- graph owner-scope 当前候选由整个 bounded qualification wake 持有；同一 strict snapshot 可由 projection/registry/Agent view 复用，append 后因 snapshot key 改变重建，scope 退出即清空。最新五问题与 lineage 聚焦=`114/114 PASS / 88.708s`，资格端到端修正复跑=`1/1 PASS / 279.361s`，完整 V3.2=`779/779 PASS / 1596.797s`，正确全 Theory Paper=`1546/1546 PASS / 1887.454s`，compile/diff check 通过。第一次 779 项运行的唯一错误是测试观测列表未初始化，补变量后单项与全量从零通过，不是生产逻辑失败。
- 当前状态仍为：提交前完整回归已通过；显式提交、exact post-commit receipts 和第八资格待完成。fresh Current Codex、fixed monitor、真实 15 分钟时限为 `UNKNOWN_NOT_QUALIFIED`；预测增量、概率校准、成本后收益和跨 regime 泛化为 `UNKNOWN_NOT_EVALUATED`。
