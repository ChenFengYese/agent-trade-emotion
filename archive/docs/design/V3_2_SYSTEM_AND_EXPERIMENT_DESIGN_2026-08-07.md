# V3.2 动态进攻系统与实验设计

状态：`RUNTIME_REPAIR_DESIGN_FROZEN / IMPLEMENTATION_NOT_STARTED / NO_TARGET_AUTHORITY / NO_TARGET_RUN / NO_OUTCOME`

> 2026-08-10 当前工程裁决：正式实验继续暂停。只读生产链复核发现 source/analysis decision 时序倒置、精确 outcome horizon 与整刻格点冲突、过宽限期 schedule 无耐久终态三个 target P0，以及 strategy revision reader 静默为空的 P1。后续不再扩写本文件的理论/系统范围，统一按 [V3.2 运行时修复、简化与实验恢复计划](V3_2_RUNTIME_REPAIR_AND_SIMPLIFICATION_PLAN_2026-08-10.md) 实施一个窄旁路切片；在非整刻组合测试、单次全量回归、标准网络 smoke 与 fresh qualification 通过前，不得创建 target。

版本语义：正式 authority/schema 兼容字段仍为 `theory_version=3.2.1`；`V3_2_6_FIVE_TRAP_HARDENING_CANDIDATE` 只是该语义族内尚待提交和资格冻结的文档/实现修订状态。

日期：2026-08-10（运行时简化计划冻结）

需求入口：`requirements/2026-07-30-theory-paper-practice.md`

理论入口：`CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md`

建议裁决：`V3_2_USER_RECOMMENDATION_ADJUDICATION_2026-08-07.md`

权限：`PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION / executable=false`。设计中的动作、仓位、限价、止损、止盈均为研究计划；不得连接 paper/live、账户、订单、凭据或资金。

---

## 1. 设计结论

现有 V3.1.1 修复可以继续作为可靠性底座，但不能直接启动原目标实验。截至 2026-08-07 的基线修复改变了三个核心合同：

1. `UNKNOWN → WAIT` 改为 typed UNKNOWN；正常方向/原因不确定允许有界 probe；
2. flat 三动作实验改为完整动态行为规划，并原生记录 hypothesis→risk tranche→reentry；
3. “每个 1H outcome 完成后才能下一轮”改为 15 分钟 AnalysisClock 与独立 OutcomeClock，未到期结果不阻塞新轮。

2026-08-08 的授权修订增加治理和运行收敛合同：容量走可逆 typed compaction；客观 UNKNOWN 与有依据主观评估并存；人工公开证据只进未来 revision；环境 profile、派生审计、只读监督、same-run recovery 白名单和 exact Git commit 进入正式授权链。同时删除 0–100 主观风险映射，增加 typed 混沌 regime、全 instrument/全方向耐久 reentry 预算、依赖投影缓存和 future-only 执行逃生舱边界。前四份资格继续按各自唯一 PUBLIC_SOURCE attempt 永久封存。资金费四时钟修复提交为 `093b4e79d43ef523e0926aa1e8495ba13feb4145`；其后的第五资格 `v32-qualification-btcusdt-20260809t074253z` 首次取得真实 `12/12` OKX public HTTP 200，却在 CURRENT_CODEX 材料化时暴露旧容量估算错误：真实 `414` bars 与 `55` citable evidence 使 Agent view 约 `352 KiB > 256 KiB`。失败发生在 Agent view、mailbox、CURRENT_CODEX claim、monitor 和 target 之前；旧特殊分支又未写 controller failure terminal。第五 qualification/target exact pair 及原 `96` 文件树永久冻结。该容量与终态修复已提交为 `975e7a873e9f801594385e2feb00453586f270c3`，两套 exact post-commit 回归手工通过；随后复核发现测试结果没有形成 authority 可物理重放的执行收据。**在当时的第五资格边界**，因此必须先建立资格冷路径治理门：两个固定全量 suite 一次执行、有界日志、进程组清理、write-once receipt/aggregate、WorkspaceFreeze v1.1，以及每次 qualification wake 之前的完整 Phase-A 物理重放；它不进入 15 分钟 target analysis 热路径。该历史阶段完成提交与新 ID 收据之前不能创建第六资格；其后的第六资格事实由下一段接续。

该治理修复提交为 `e0c7d3da4e0809fd21b0d241db84e0c17155d4ff` 后，第六资格 `v32-qualification-btcusdt-20260809t131915z` 的正式收据、Phase-A 和 PUBLIC_SOURCE 均通过，但 CURRENT_CODEX 材料化在 `CONTEXT_PACKAGE:PROPOSAL` 永久失败关闭。真实 packet/input=`559,522/562,654 B`，说明 `512 KiB` proposal 子门比 `1 MiB` 完整输入门更早制造了无物理依据的断崖；旧 compaction 又生成 `121` shards、约 `7.79 MB` 累计交付并在约 `306,980 B` selection 处停止。只读重建还发现旧实际返回将同一 packet 复制三次，最终 Presentation=`1,687,318 B`，并在 qualification/target 先 claim 后才形成超限对象。V3.2.5 改为单一 owning envelope，当前 pilot 固定 `INLINE_ONLY`：packet 只在 request context 出现一次；checkpoint/request/claim/control 与唯一正文表示在 enqueue/claim CAS 前共同接受 `1 MiB` 精确总门，失败零 mailbox/material/checkpoint 写入。第六现场只读重建约 `566–568 KiB`、packet 一次。`SHARDED` 只保留为未来未资格化能力；没有分段游标、逐段 ACK、重组和耐久消费收据前不得用于当前 successor。该本地 envelope 可确定性重建，但不证明 provider/transport 已接收或当前 Codex 已消费。第六 exact pair 永久 tombstone，修复只能进入全新资格。

第六资格后的耐久边界修复已进入提交 `66197c47a1281340b4226da825da0b18d8815c3e`：request、claim、delivery/receipt、consumption/receipt 四个 mailbox 转移都允许且只允许 exact-tail 恢复，首次发布的不可变字节、时间与 predecessor 获胜，恢复只补原 checkpoint CAS。V3.2-owned durable JSON writer 先在同目录私有临时文件完成全写与 `fsync(file)`，再以不可覆盖的原子链接发布并 `fsync(parent directory)`；它只服务 V3.2-owned stores，V3.1 冻结的 `domain/contracts/canonical.py` 及其使用者保持原字节不变。CAS 成功但响应丢失时，重复 enqueue/claim/submit 只能识别并返回已提交的 `REQUESTED/CLAIMED/DELIVERED` exact successor，零第二写、零新时钟、零第二 Agent。delivery receipt 在 `current_codex_presentation_digest` 记录实际 Presentation digest；qualification full replay 从 CLAIMED 快照重建同一 Presentation 并核对 digest。最终 Agent-facing 返回就是这个 `<=1 MiB` 的 envelope，不再增加 runtime/alert 外壳；hot path 严格 `INLINE_ONLY`，超限立即在持久化/Agent 调用前失败，`SHARDED` 只保留为 future-unqualified。第七资格实际完成了 Phase-A 前 fresh-process 和唯一 fresh PUBLIC_SOURCE，机械闭包为 `43 roots / 194 reachable paths / 194 bindings`；CURRENT_CODEX 因本地逐对象唤醒耗尽 reservation 窗口而未 claim，固定 outcome monitor 未开始。当前未提交候选包括有界材料 burst、第七 `EXPIRED_TERMINAL` 历史兼容，以及 zero-eligible WAIT 的 owning-cause 二次加固；完整 Codex/monitor 资格仍为 `UNKNOWN_NOT_QUALIFIED`。

因此不能把 V3.1.1 的 `8 accepted + 8 outcome` authority 换个理论文件继续使用。V3.2 必须有新 schema、runtime closure、qualification、authority 和目标 run；旧失败 run 和 V3.1.1 未启动设计保留，不回写。

---

## 2. 已知失败与 V3.2 纠正

| 已知问题 | 根因 | V3.2 纠正 |
|---|---|---|
| 大量 WAIT | 一般不确定、事实失败和风险未知未分型；probe 不在正式动作域 | typed UNKNOWN；`OPEN_PROBE` 成为一等动作；WAIT 必须证明相邻 probe 被支配 |
| 固定止盈错失延续 | target 被实现成 episode 终局；无 runner/reentry | target 变为管理事件；partial harvest、runner 和 reentry obligation |
| 历史形态被弱化 | 只允许 observation，未形成一等状态/机制节点 | `ReflexiveLiquidityZone` + rejection/absorption/false-break/OTHER 竞争路径 |
| 主观分数伪精确 | 0–100 的语言判断被线性映射为风险 | 主观输入仅保留 `EXTREME_UNCERTAINTY/LOW/HIGH`，语义固定为 `off/probe/normal`；不允许连续主观分值、插值、求和放大或冒充概率。action-evaluation 的连续 `risk_reference_units` 只是 sealed plan 派生值的 exact 回传，不是 Agent 可调旋钮 |
| 多个故事重复放大 | dependency group 只约束证据，不约束风险分配 | `HypothesisDependencyCluster` 默认 max 聚合；多个 cluster 只切分固定总包络，不能累加放大 |
| 固定轻仓/名义分配 | 仓位比例未按失效距离和成本比较 | 先分配 worst-case risk，再反推 reference scale/未来 quantity |
| 确认后追价 | UNKNOWN 路径不能支持 OPEN/ADD | anticipatory/reaction/break/retest 四种 entry mode，分别设风险层级 |
| 15 分钟策略被 1H monitor 阻塞 | research/monitor 串行单 outstanding outcome | AnalysisClock/OutcomeClock 分离；共享观察 tick 解析多个已到期 outcome |
| 公开 adapter 失败丢 raw | parse-before-persist | transport/raw capture write-once 后解析，已有 v2 底座复用 |
| 资格 transport 强制直连而 outcome 隐式走系统代理 | bundle/outcome 物理路径不一致；首个 required timeout 又只留下异常类名；固定全局资格根无法容纳不可变失败后的合法 successor | bundle/probe/outcome 统一到冻结的无凭据系统公开 HTTPS 路由；精确 OKX public allowlist、无重定向/fallback/retry、代理 userinfo 与 bypass 在网络前拒绝；raw/body（若有）先写、typed failure receipt 后写、controller 保留稳定错误链；每个 qualification ID 使用独立 runtime root，旧失败根永久只读 |
| research READY 覆盖 monitor FAILED | 多 checkpoint 无统一所有权 | V3.2 TickSupervisor 统一检查 analysis lane、source lane、outcome lane 与 commit intent |
| current Agent 未真正收到新理论与当前市场证据 | 文档只有摘要/路径，旧 packet 又可能只含全 UNKNOWN 的历史投影 | 完整 UTF-8 theory semantic document + 由当前完整来源/图/PIT 原件确定性生成的有界市场图视图直接进入当前 root Codex，耐久消费 receipt；超限调用前失败关闭 |
| support role 可被任意 self-digest 冒充 | key→schema/digest 未冻结 | exact support role spec；错角色、错 schema、错 digest field 全部拒绝 |
| 磁区被误认成主力护盘 | zone 路径只在报告内竞争，外在假突破/流动性事件未横切绑定 | typed `ExternalPathModifier`，仅影响共享 zone/dependency 的假说、计划和 reentry |
| 弱假说分母越小风险越大 | 相对归一和连续主观分值都会制造风险 | 主观档位只降低风险上限；多个 cluster 不累加总包络，HIGH/LOW 用离散 tranche 单位切分既有预算 |
| 多空成对挤掉混沌 | 非方向状态被迫摊成 LONG/SHORT | typed `NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN`；当前方向风险为零，只保留绑定 sealed `BREAKOUT_BOUNDARY` 的 `CONDITIONAL/BLOCKED/no-tranche` 未触发计划；Domain 派生上下 research trigger pair，命中只触发重新分析；结构化 `RANGE` 可保留有边界的条件均值回归 |
| reentry 反复接飞刀 | observation obligation 被误写成自动重开，cluster/方向/动作改名可绕局部计数 | 每 instrument 单一全局 churn breaker；首次 probe 免费但立即单次锁，后续任一方向最终选中、合格、正风险的 `OPEN_PROBE/REVERSE/REENTER` 都消耗同一次数和累计风险；首次 stop 计一次失败，再失败一次即熔断；真实反转可计数纠偏但不免费，原窗口到期前禁止 RESET |
| parent 血缘被改写 | 反向假说、普通支持 ref、过期 tranche 或重复 ID 可伪造失败/继续 ADD | 风险候选必须是同方向 actionable cluster 精确闭包；sole parent 持久绑定 geometry、support、zones 与绝对 validity；只有 fresh opposing/typed invalidation 可证明失败；到期退休，ADD/REVERSE 必须生成不同 tranche ID |
| 每个子阶段重复全图验证 | 依赖闭包、材料和 acceptance prefix 被反复重算 | 普通轮的构造路径只追加新 delta；qualification bounded wake 或同一 owner-bound acceptance/public-evidence scope 内，对相同 strict snapshot 从累计图完整重建 closure 一次；append 使 snapshot key 改变并重建，成功结果不跨 wake/thread/task/process 复用 |
| Agent view 内联完整 closure ID 列表导致真实容量失败 | fixture 只估单周期 bars，且为每条 evidence 重复复制大量 association IDs | view 逐条保留全部 evidence digest、availability、status、完整 dependency groups、exact owning closure digest 和四类 counts；完整 evidence-ref/node/association IDs 只留在 verified registry，由 Application owning verifier 重建并精确比较；固定 256 KiB cap 不上调 |
| materializer 异常留下可重入 RUNNING/PENDING | CURRENT_CODEX 特殊材料化分支绕开 controller 的失败原子边界 | controller-owned write-once materialization failure receipt 绑定 authority、reservation、predecessor、stage/time、typed errors 和完整 material prefix；CAS 到 `FAILED_CLOSED`，以后只读重放；历史第五 exact pair 全 API tombstone |
| 长期 WAIT 使模型休眠 | 有机会成本字段但无连续无动作监督，单一时钟又可能被普通市场变化错误重置 | 风险计划与模型适应两只耐久时钟分别触发 `INACTIVITY_REVIEW`，持续 shadow outcome 与方法重检，不强制仓位 |
| stop 被当作退出成交价 | 保护几何未显式分离 trigger、fill、attached protection 与 venue 可用性 | 当前只研究且延迟上限为 `UNKNOWN_NOT_QUALIFIED`；未来只有 venue 原子 attached protection 模式可随入场同请求并独立确认，不支持则默认禁止新开仓；fill→保护确认间隙进入 `UNPROTECTED_EXPOSURE`，冻结新增并按预授权 reduce-only close/reconciliation；仍不保证成交 |
| 旧假说只延长期限继续工作 | 有 expires_at、无 renewal 防洗白 | 到期撤销行动权；续期必须新 revision、新证据和 regime/zone 重检 |
| 原件保留但 compact view 可删证据 | 调用者可自行传 `members/required roots`，原件重放不证明投影完整 | schema-specific extractor 从正式原件机械生成全部 typed members；冻结 StageRequiredRootPolicy；原件→member→shard→delivery 全链 round-trip |
| 客观 UNKNOWN 被主观附件洗成“有数据” | 只校验引用摘要格式，不解析当前 PIT/mechanism registry 与 chronology | ObjectiveUnknown/UnknownSubjectiveAssessment 双命名空间；引用唯一解析、available-at、相反假说、expiry、零客观/coverage/硬门贡献 |
| 人工数据事后回填 | 发布时间可被误当系统可得时间，截图可能覆盖旧 UNKNOWN/outcome | `MANUAL_PUBLIC_EVIDENCE` 使用实际接收时间，只作为未来 cycle 新 revision；旧 acceptance/outcome/failure 永不修改 |
| 中文审计反向成为事实 | 报告若参与它所描述的 typed boundary 会形成自引用，若由模型自由摘要会漏项 | 每类 narrative 都由已 sealed 的对应 typed artifacts 确定性生成；acceptance narrative 只在 acceptance 后生成；AuditCompletionReceipt 只控制下一 permit，不改已封存语义 |
| 监督 Agent 变成第二 controller/Strategy Agent | 直接读取 formal store、市场或未到期 outcome 会扩大能力并污染 run | 最小只读 projection、独立 alert store；无市场/Agent/formal-write/future-outcome capability；controller 只执行冻结恢复白名单 |
| 本地化降低标准 | 为迁就 Codex/网络/OS 调小候选、horizon、样本或 freshness | 冻结 EnvironmentCapabilityProfile；缺 REQUIRED 能力资格失败；适配仅经 port/adapter，新版本重新 qualification |
| dirty 工作树生成 authority | runtime 字节不属于 HEAD，提交/测试/授权证据不指向同一物理版本 | WorkspaceFreezeReceipt 绑定 branch/commit/tree/closure/status/敏感检查/post-commit tests；优先 clean qualification worktree |
| post-commit PASS 只留在终端/文档 | authority 能绑定测试源码，却没有受约束控制器实际运行固定全量回归的可重放本地记录 | qualification ID 预留一次尝试；固定 Python/Git/环境/argv；两份执行收据与 aggregate 全部 write-once；WorkspaceFreeze v1.1 和完整授权链每次 wake 物理重放 |

---

## 3. 只保留四层

### 3.1 Domain

拥有纯类型、不变量和状态转移：

- `V32UnknownClassification`；
- `ObjectiveUnknown / UnknownSubjectiveAssessment` 与零客观贡献不变量；
- `ContextCompactionPolicy / StageRequiredRootPolicy / reversible shard contract`；
- `DataGapEscalation / ManualPublicEvidenceAdmission`；
- `EnvironmentCapabilityProfile / EnvironmentConformanceReceipt`；
- `AutoRecoveryWhitelist / RecoveryTraceRegistry`；
- `ReflexiveLiquidityZone`；
- `DynamicHypothesisSet` 与四类假说；
- `SubjectivePlausibilityTierLedger / MarketRegimeState`；
- `HypothesisDependencyCluster`；
- `ExternalPathModifier / MarketExecutionHazard`；
- `ConditionalActionPlan`、`RiskTranchePlan`、`ReentryObligation / ReentryBudgetState`；
- `StrategicContextFrame / TacticalDeltaFrame / TriggerFrame`；
- `OutcomeObservationTick / OutcomeResolutionBatch`；
- 完整 legal action grid 与 WAIT dominance；
- 离散支持上限、cluster tranche 单位、unit loss 和归因矩阵的纯复算；
- hypothesis expiry/renewal 与 inactivity review 的纯状态转移。

禁止：文件、网络、当前时间、Agent 调用、authority 加载。

### 3.2 Application

拥有 use case 和唯一流程：

- prepare initial full-context cycle；
- prepare 15m delta cycle；
- persist full Agent context before proposal；
- proposal→compile→selection→consumption；
- seal dynamic plan/commit envelope；
- ingest one public observation tick and resolve all due outcomes；
- refresh/expire caches and hypotheses；
- recovery from controller-owned intents without second Agent/network attempt；
- 从正式 acceptance 原件确定性提取 typed members、计算强制 roots、构造 proposal/selection compaction 与全量 replay；
- 在每个 typed boundary 封存后确定性生成该边界的 audit narrative/index；acceptance narrative 在 acceptance 后生成，并在下一 analysis permit 前验证 AuditCompletionReceipt；
- 向独立监督端只发布 allowlisted read projection，消费 alert 时只匹配冻结 recovery action ID。

Application 只接收完整 loader 投影后的 V3.2 authority；不自行解释 Q0–Q8。

actual-capability 分层同样遵守该方向：Domain 拥有纯 `attempt-progress` 结构与不变量；Application 只依赖 capability/evidence-store Protocol 并拥有推进用例；Infrastructure 固定实现本地 EvidenceStore、物理 binding 重开和 owning full replay。Application 不得直接导入 Infrastructure，也不得允许公开 production API 注入 registry、adapter、路径或时钟。

### 3.3 Infrastructure

拥有外部边界：

- OKX public data/raw capture；
- write-once JSON/raw stores；
- clock；
- current Codex durable delivery；
- monitor automation adapter；
- strict UTF-8 theory reader；
- exact import/runtime closure collector；
- compaction shard、manual evidence、audit narrative、alert 与 workspace-freeze 的分权 write-once stores；
- Environment profile collector 和 exact commit/tree qualification adapter。

禁止：决定多空、假说权重、动作优劣或权限。

### 3.4 Presentation

只负责 status/report/automation 入口以及 sealed artifacts 的中文可读渲染。它不能深扫描已由 full loader 验证的业务值，不能决定 required roots、主观依据或恢复动作，也不能绕过 loader、直接写 checkpoint、读取未到期 outcome 或调用交易端点。

---

## 4. 核心文档与摘要关系

一个 V3.2 analysis cycle 的 canonical bundle 至少包括：

```text
active_authority_projection
active_authority_projection_digest
governing_authority_digest
governing_authority_binding
theory_v3_2_semantic_document
experiment_contract
environment_capability_profile_binding
workspace_freeze_receipt_binding
clock_and_tick_policy
strategic_context_frame
tactical_delta_frame
trigger_frame
public_source_admission
pit_dataset
verified_pit_evidence_availability_registry
objective_unknown_registry
unknown_subjective_assessment_registry
data_gap_escalation_registry
manual_public_evidence_admission_registry
twelve_axis_projection
reflexive_liquidity_zones
association_snapshot
dynamic_graph_projection
agent_market_graph_view
proposal_context_compaction_manifest
proposal_required_root_and_shard_plan
proposal_compaction_replay_receipt
previous_hypothesis_and_plan_heads
dynamic_hypothesis_set
subjective_plausibility_ledger
hypothesis_dependency_clusters
external_path_modifiers
legal_action_grid
risk_budget_contract
agent_input_context
proposal_transport_and_envelope
sealed_deterministic_evaluation
selection_transport_and_envelope
selection_context_compaction_manifest
selection_required_root_and_shard_plan
selection_compaction_replay_receipt
agent_context_consumption
conditional_action_plan
inactivity_review_state
successor_commit_envelope
shadow_decision_bundle
environment_conformance_receipt
recovery_trace_registry
accepted_state
outcome_schedule
```

`active_authority_projection_digest` 绑定 Application 可消费的最小权限投影；`governing_authority_digest` 与 `governing_authority_binding` 则绑定完整 V3.2 governing authority 的语义摘要和物理字节。两者必须同时成立，禁止用自摘要 projection 冒充 governing authority。旧 V3.1 loader 对 Q0–Q8 和 74 个冻结路径的只读通过只证明旧链未漂移，不生成或替代 V3.2 authority。

Agent context 内嵌完整理论正文和必要的小型支持语义文档。完整来源分析工件和累计图投影继续作为接受、重放和审计原件；它们不直接逐字复制进 Agent 上下文。确定性系统必须按固定顺序构造交付：

```text
full write-once originals
→ schema-specific member extraction with source-to-member coverage
→ canonical dictionary/deduplication
→ reversible typed series/metadata encoding
→ build or reuse digest-bound dependency identity and closure proof
→ StageRequiredRootPolicy computes mandatory roots
→ current pilot: one exact INLINE packet + durable consumption
→ full-original + compact-view + delivery replay at acceptance
```

closure shard builder、manifest 和 round-trip verifier 可以作为内部机械能力保留，但当前 pilot 的 transport shard set 必须为空；只有未来独立资格化的多段协议才可把它用于实际 Agent 交付。

`StageRequiredRootPolicy` 是实验合同的一部分，不接受调用者传入任意 required member IDs。初始轮、资格、缓存失效和重大 regime 变化执行全量 closure；普通 15 分钟轮只在 pilot 有界 working set 上传播新增/失效节点，并复用由原件摘要、cluster identity、策略版本和文件物理身份共同绑定的缓存。这里没有固定 `24h` 同类证据归并器；`24h` 只属于 reentry churn ledger。一个 bounded qualification wake 或 owner-bound acceptance/public-evidence verification scope 对相同 strict built-in JSON snapshot 只完整重建 closure 一次，供 projection、registry 与 Agent market-view 重建使用；内部 append 改变 snapshot key 后强制重建，失败、caller mutation、custom Mapping、scope 退出或跨 wake/thread/task/process 均不复用。Proposal 与 Selection 复用同一份封存材料，而不是共享跨阶段 verifier cache。任何文件身份变化、谱系冲突或缓存版本不符都强制全量重放。任何 lossy summary、top-k、按档位删低项、聊天记忆或“先发部分再由第二次 Agent 补看”均禁止。

Current Codex actual-capability 的 `120s` 只作为 SLO；从 seal 到 run 的总耗时超过 `660s` 必须确定性失败关闭，并在资格 receipt 中记录实际耗时。`111.067s` 是较早 lifecycle-memo 下的一次本地 deterministic cycle 证据，不包含本轮 graph-scope 修复后的 fresh Codex/target/monitor 端到端资格；它只能说明当时那一调用边界，不能外推为完整 15 分钟节拍。第七资格已另行证明 fresh process 与 fresh PUBLIC_SOURCE 子门，但没有证明 Current Codex 完整交付、固定 monitor 或 15 分钟全周期 SLO。不得据此缩短输入、跳过原件重放或声称已满足完整节拍。

本地旧性能证据显示，core 长测超过 `5m` 尚未完成：fixture 约 `216s`，receipt reconstruction 测试体约 `32s`，测试体发生 `59,018` 次 canonical serialization 与 `28,822,997` 次 normalize。根因是同一不可变完整对象沿 lifecycle/acceptance 反复验证，不是完整 closure 或 physical replay 应被删除。当前实现改为 request/receipt-scoped memo：key 与 verifier 使用同一递归精确内建对象快照；custom Mapping 不缓存；owner 同时绑定 thread 与 asyncio task；scope 退出清空；失败不缓存、不跨调用/线程/task/process、不信任 Agent digest。context shard 只对 growing candidate 做精确增量 size，最终对象仍完整 build/self-digest/actual-byte replay。严格修正后 affected core `73/73 PASS / 154.221s`、原慢测 `44.255s`，独立 TOCTOU/custom-Mapping/thread-task/shard 复核 `4/4 PASS / 42.327s`。这组局部测试自身不承担 fresh-process、网络或 Agent 交付证明；第七资格后来已单独关闭 fresh-process 与 fresh PUBLIC_SOURCE 子门。跨唤醒缓存、Current Codex 完整 delivery、固定 monitor、15 分钟全周期、市场预测和执行可靠性仍分别为 `UNKNOWN_NOT_QUALIFIED/UNKNOWN_NOT_EVALUATED`。

2026-08-07 基线曾使用 `agent_market_graph_view=256 KiB`、`proposal packet=512 KiB`、`selection packet=768 KiB`、`Agent input context=1 MiB`、单次 `UTF-8 delivery=256 KiB`，以及 `unknowns/zones/hypotheses/modifiers/clusters/action candidates=32/64/256/128/256/16` 的局部硬上限。这些数字现在只是历史实现快照；最终上限必须由 `EnvironmentCapabilityProfile`、实验合同和真实 Codex qualification 共同冻结。当前 pilot 只可执行仍形成单一 INLINE packet 的确定性去重/typed 编码；完整强制根集合或最终 envelope 仍不能交付就写 `CONTEXT_CAPACITY_UNRESOLVED`，在 Agent 调用前停止并生成 DataGap/人工处理义务，不得转入 SHARDED。

第五资格给出了第一组真实容量证据。旧 Agent view 为约 `352,324` canonical bytes，其中完整 closure association IDs 约占 `167,750` bytes；把这些 verifier-only 身份在每条 evidence 内联，不会增加 Agent 可判断的市场事实，反而造成重复传输。V3.2.4 的 `agent_market_graph_view v1.1.0` 因此采用 bounded proof index：保留全部 `55` 条 citable evidence、availability、closure status、全部 `815` 次 dependency-group occurrence、四类 closure counts、exact owning closure digest、`414` bars、UNKNOWN 与 OTHER；完整 closure rows 仍 write-once 保存在 graph registry。Application builder/acceptance 从 registry owning rebuild 后逐条比较，伪造摘要、计数、组或 registry 均失败关闭。真实 view 为 `187,892` bytes；把同一冻结形态的 cycle index/revision 改到 Cycle 16 后为 `187,895` bytes，距固定 `256 KiB` 上限仍有 `74,249` bytes。该 Cycle-16 数字不是 16 轮累计 registry 演练，不能证明真实累计容量或重放耗时；扩大 bars/evidence/group 上限或证明累计轮次能力，都必须由新版本/正式资格提供，不能把这份证据外推。

第五资格的小理论夹具形态曾给出 proposal/input=`472,441/475,433` bytes、selection/input=`589,786/592,787` bytes；第六资格使用完整理论后，真实 proposal/input=`559,522/562,654` bytes。后者证明 512/768 KiB stage packet 门没有独立物理意义：packet 本身不是 Agent 最终收到的对象，完整 input 才是。当前合同因此只在构造完整 INLINE candidate 后比较 `1 MiB` input hard cap；历史 stage 常量仅为兼容别名，不参与判定。随后必须构造精确 `CurrentCodexPresentationEnvelope`：INLINE 复用 request context 中唯一 packet，envelope 同时绑定完整 mailbox checkpoint、request、可选 claim 与严格标量 controls，自摘要后再受 `1 MiB` 总门。enqueue 以最大长度时间与 TARGET controls 预演最坏 claim，因此不会出现 pending request 合格、真正 claim 却超限的永久悬挂；qualification/target 在 CAS 前再次以真实时刻预演，CAS 后只接受逐字等同的 claim/checkpoint。第六旧返回为 `1,687,318 B`，新只读重建约 `566–568 KiB`。当前 pilot 明确 `INLINE_ONLY`；若完整 INLINE input 或最终 envelope 超过 `1 MiB`，必须 `CONTEXT_CAPACITY_UNRESOLVED`。`SHARDED` codec/package 只属于未来未资格化能力，必须先增加分段 transport 的确定性游标、逐段 ACK、完整重组、耐久 consumption receipt 和独立容量资格，不能在当前 pilot 靠提高单片上限或多次隐式 Agent 调用通过。

`prepare_v32_qualification_from_committed_workspace_v1` 已接入真实 `collect_v311_fresh_process_trace_v2`，不再把 `PRODUCTION_ROOT_PATHS` 冒充观测结果。它以固定 `/opt/homebrew/bin/python3.12 -I -c` 和随机 nonce 启动独立进程，导入完整 production roots，并校验独立 PID、nonce、空 stderr、roots 完整包含和 self-digest；该调用发生在资格 System UTC 时钟及任何 Phase-A authority byte 之前。随后 V3.2 owning composition 将 typed receipt write-once 保存到 `support/fresh-process-trace.json`，以其中 `observed_project_python_paths` 构造静态根与实际观测路径的并集 closure，并把 receipt 的语义/物理 binding 写入 runtime manifest；Q1/full loader 必须重开 receipt、时间、Python、根集合、摘要与物理 SHA-256，缺失、篡改、交换或时序倒置均失败。同一 manifest schema family 由 strict router 分为 legacy `1.0.0` 与 successor `2.0.0`：旧六棵失败资格树只按原 `1.0.0` 无 fresh binding 形状重放，不补造 receipt；新 prepare 只生成 `2.0.0`，后者缺少物理 fresh trace、binding 或 `trace.completed_at <= workspace.observed_at` chronology 即失败，未知版本也拒绝。提交 `66197c4` 与第七资格已实际证明 `43 roots / 194 reachable local paths / 194 bindings` 的 fresh-process 与 fresh PUBLIC_SOURCE 子门；当前 Codex 与 monitor 子门未完成，必须由新提交和第八资格重新关闭完整链。

`verified_pit_evidence_availability_registry` 是正式接纳对象：Cycle 1 必须有当前 registry；Cycle 2+ 必须同时重放当前与前一 registry。新增证据必须存在于当前 bounded view 的 `citable_evidence_records`，满足 `available_at <= current dynamic-state as_of`，并严格晚于前序 dynamic state/availability registry 共同固定的 cutoff。对 `ADD/REENTER/REVERSE`，只有候选假说显式 `supporting_refs` 中的这类 fresh positive digest 可以进入 `new_evidence_refs`；旧但上一轮漏引的证据、任意字符串、`opposing_refs`、zone ref、tier-update/renewal ref 均不能授权新增风险。无 fresh positive ref 时只允许 typed `NO_NEW_EVIDENCE`、固定 sentinel、`BLOCKED/no-tranche`。这里的 decision time 不能与由市场 `observed_at` 派生的 bundle `as_of` 混用；换 ID、改文案或附加无关引用不能伪造 freshness。

十二轴投影必须绑定冻结来源 registry。当前正式 axis row 保存 `status / admission / source assessments / observed_at / available_at / raw-or-input binding / reason / missingness / dependency group / claim ceiling`；只有来源合同能验真的客观质量才可另存，不合成独立 `quality/coverage` 标量。coverage 只能由 admitted/unknown 状态确定性汇总，既不是 Agent 输入，也不进入风险缩放。图中应有十二轴和 `OTHER` 的完整节点，包括 UNKNOWN；但不得以节点数量推导 `native source coverage`。验收至少拒绝三类伪装：单次 order book 冒充 `LIQUIDITY_RESILIENCE` 直接证据、OI level 冒充 `LEVERAGE_CHANGE`、UNKNOWN 轴因存在 tombstone 节点而被计入原生覆盖。

公开数据时间合同必须由数据 owner 唯一定义并被 collector、bundle verifier、axis projection 与 Agent material 共用。每个 datum 分离 `provider_observed_at / observed_at / available_at / effective_at`：provider 原始时钟不改写；`observed_at` 由冻结 clock-skew policy 形成知识安全观测；`available_at` 是本地真实接收/保存时刻；`effective_at` 是事件或结算生效时刻。OKX funding 的固定映射为 `ts → provider_observed_at`、`fundingTime → funding-rate.effective_at`、`nextFundingTime → 独立 next-funding-settlement-time schedule datum.effective_at`。只有相应市场组件的 `observed_at` 可进入 global/axis `as_of`；SERVER_TIME、INSTRUMENT metadata、`effective_at` 和未来 schedule 均不得推进。

### 4.1 新增对象的所有权与授权位置

| 对象 | Owner | 必须绑定的位置 | 权限含义 |
|---|---|---|---|
| `ContextCompactionPolicy / StageRequiredRootPolicy` | Domain | experiment contract + runtime manifest + authority Q3/Q7 | 定义可逆变换与不可裁剪根集合，不是市场事实 |
| `EnvironmentCapabilityProfile / WorkspaceFreezeReceipt` | Domain schema，Infrastructure 采集 | experiment contract + runtime manifest + authority Q1/Q8 | 冻结运行环境与 exact commit/tree，不降低理论或评价 |
| `UnknownSubjectivePolicy / DataGapManualEvidencePolicy` | Domain | experiment contract + authority Q2/Q4/Q7 | 约束主观附件和人工来源，不能授予客观事实地位 |
| `ReadOnlySupervisorPolicy / AutoRecoveryWhitelist` | Domain | experiment contract + authority Q5/Q6/Q8 | 只授予观察投影和列举的确定性尾恢复 |
| proposal/selection compaction manifest、required-root plan、shards、replay receipt | Application 组合，Infrastructure 保存 | formal cycle acceptance closure | 它们决定 Agent 实际看见什么，虽非 source authority 也必须接纳与重放 |
| ObjectiveUnknown/SubjectiveAssessment/DataGap/ManualAdmission registries | Domain 对象，Application 聚合 | formal cycle acceptance closure，零项也显式 | 保持缺失、主观性和人工渠道可审计 |
| `EnvironmentConformanceReceipt / RecoveryTraceRegistry` | Application | formal cycle acceptance closure | 证明本 cycle 未漂移、未越过恢复白名单 |
| `CycleAuditNarrative / SupervisorAlert / 人工说明渲染` | Presentation/独立观察存储 | 各自 typed boundary 封存之后；acceptance narrative 另进入 AuditCompletion gate | 只供人审，不得成为 authority、事实或 Agent 输入 |

现有 `COMPONENT_SPECS` 已扩展为 28 项，并原生包含 `authorized_revision_cycle_registry`。只有 28 项原件、binding、continuity、commit 与 owning full replay 全部一致，才可称为 2026-08-08 修订后的 acceptance；不能仅把文件放进 runtime path list，或只在 narrative 中提到它们。

### 4.2 UNKNOWN 双轨与引用解析

`ObjectiveUnknown` 保存 `objective_status=UNKNOWN / objective_value=null / zero_imputed=false`。`UnknownSubjectiveAssessment` 是独立对象，引用必须在当前 PIT 或冻结 mechanism registry 中唯一解析，满足 run/cycle/instrument 和 `available_at <= assessed_at`，且 assessment 不早于 UNKNOWN 的 detected time。有方向 assessment 必须有 rationale、typed opposing-hypothesis binding、falsifier、dependency group、expiry 和三档主观支持；无可解析依据只能是 `EXTREME_UNCERTAINTY`。跨轮档位只能相邻变化，必须绑定 PIT update refs。

Compiler 和 action evaluator 必须硬编码以下零贡献：`objective_value_contribution=0 / source_coverage_contribution=0 / fact_integrity_guard_contribution=0 / permission_guard_contribution=0 / max_loss_guard_contribution=0`。主观档位只能参与已合法 hypothesis/action 的离散排序并降低上限；不能把 UNKNOWN 升为 DIRECT/PROXY/DERIVED，不能解除硬门或增加客观预算。

### 4.3 DataGap 与人工公开来源

每轮以 `DataGapEscalationRegistry` 覆盖全部不可获取字段。人工处理必须产生 raw screenshot/export、官方公开 URL、实际系统接收时间、提取映射、semantic/physical 摘要、操作者记录和 readmission receipt。`MANUAL_PUBLIC_EVIDENCE.available_at` 使用实际接收时刻，只能进入后续 cycle；同一自动 attempt 不得重试，旧 cycle/outcome/failure 不得回填。人工与自动证据依赖同一事实时共享 dependency group。

### 4.4 Environment 与 workspace freeze

`EnvironmentCapabilityProfile` 冻结 OS/arch、Python、Codex delivery 与实测容量、UTC/monotonic clock、文件系统 atomic/CAS、公开网络/TLS/DNS/代理、automation、存储、tool inventory 和 adapter 版本，并区分 REQUIRED/OPTIONAL/UNKNOWN。每个 cycle 的 `EnvironmentConformanceReceipt` 绑定 active profile；稳定能力漂移则停止并重新 qualification，瞬时来源不可用则保存 coverage failure。

`WorkspaceFreezeReceipt` 至少绑定：branch、commit SHA、tree SHA、runtime closure digest、`git status --porcelain` 摘要、staged/unmerged/untracked 状态、symlink/realpath 边界、敏感信息检查、允许保留但在 closure 外的精确用户路径，以及 post-commit 测试收据。只按清单 staging，禁止 `git add .`。authority 与 qualification 必须从 exact commit 的 clean worktree，或可证明只剩 closure 外用户文件的等价边界生成。

post-commit 收据使用独立 ignored/write-once namespace，避免把测试结果写回同一 commit 形成自引用。正式入口不接受 caller 提供的 argv、environment、clock、output、store、pattern、timeout 或 retry；它在第一个 suite 前预留 `attempt=1/retry=false`，固定 `/opt/homebrew/bin/python3.12 -I -m unittest discover -s tests -t .`，分别执行 V3.2 与全 Theory Paper pattern。每份 receipt 绑定 exact branch/commit/tree、Python realpath/物理摘要/版本、固定环境、命令、开始/结束、结果计数、runner outcome、stdout/stderr 有界字节/摘要/完整性和测试前后 worktree 摘要。超时、输出超限、跳过、工作树漂移、中断、后台进程泄漏或任一非完整收据都永久消耗该 qualification ID，不得重试。

这条证据链的信任根是当前受信任的本地控制器和本地文件边界，不是不可伪造证明。拥有项目/运行目录写权限和本地代码执行权的操作者能够重算无密钥 self-digest；因此 aggregate 的机器合同必须把 claim ceiling 固定为 `TRUSTED_LOCAL_CONTROLLER_POSTCOMMIT_AUDIT_ONLY`，不得声称 independent/third-party/provider/hardware attestation。若未来需要对抗恶意本地 owner，必须另行引入外部 CI/OIDC、远端日志签名或硬件根并重新授权，不属于本 public/local/non-executable pilot。

WorkspaceFreeze v1.1 不只存 aggregate 摘要，而是通过 aggregate 物理重开 reservation 和两份 execution receipt，并要求 `aggregate.completed_at <= workspace.observed_at`。qualification 的 `advance/Agent claim/Agent submit/finalize` 在任何 transport、materializer、mailbox、probe 或写入前，必须重放 legacy predecessor、approval/theory bytes、contract、manifest、qualification phase/authorization、Q0–Q8 gates/subjects、所有 support、完整 runtime closure 和 post-commit 原件。任一个物理字节漂移都必须在副作用前失败。

### 4.5 sealed-boundary 派生审计与只读监督

每份 `CycleAuditNarrative` 必须从它所对应且已经封存的 typed boundary（qualification、analysis、acceptance、outcome 或 recovery）确定性生成中文章节及目录，不能参与或修改自己描述的边界。只有 acceptance narrative 在 acceptance 后生成专属 `AuditCompletionReceipt(acceptance_digest, policy_digest, section_bindings)`；下一 analysis permit 可以要求该 receipt 已存在，其他边界 narrative 不得伪造 acceptance completion。

独立监督 Agent 只读取 `ReadOnlySupervisorProjection`：durable checkpoint、permit、acceptance、audit index、failure 和 due-status；它不获得 raw future outcome 路径、market adapter、Strategy Agent、formal store writer、authority builder、交易或凭据能力。告警只进入独立 append-only alert store；controller 必须用 alert 中的预注册 recovery action ID 匹配下述白名单，不能执行自然语言建议。

### 4.6 same-run 自动恢复白名单

仅允许：

1. 已有 exact intent/bytes 的 write-once/CAS 尾提交；mailbox 仅列入 request、claim、delivery/receipt、consumption/receipt 四种 exact tail，首次不可变对象/时间/predecessor 获胜，恢复只补同一 CAS，冲突字节或第二次尝试拒绝；
2. 已有 raw + batch intent 且没有语义失败时，用同一冻结 parser 完成 parse/write tail；
3. Agent delivery 与 consumption 完整封存后完成固定 compiler/commit tail；
4. accepted state 后从 sealed commit 补 exact schedule；
5. child store 已提交后补 Supervisor completion/CAS；
6. 从唯一 predecessor/successor 历史重建 current pointer/index；
7. 对应 typed boundary 后用固定生成器重建 audit narrative/index；acceptance narrative 只能在 acceptance 后重建；
8. Agent 前依据冻结 manifest/intention 重建摘要和物理字节完全相同的 compaction artifact。

禁止项包括：网络重试或换源、人工补数、替换 parser、改变环境/压缩算法/required roots、第二 Agent、改 theory/risk/evaluation/clock、修补 accepted/outcome 语义、读取未到期 outcome。禁止项只能进入新 qualification 或 successor；已封存语义失败保持 fail closed。

---

## 5. 慢上下文与 15 分钟 delta

### 5.1 首轮

首轮重建：宏观/规则、日线/4H、跨市场、慢频基本面、完整十二轴、历史区域、关联快照、开放假说库和全部数据质量。允许较长处理，但必须在 contract 的最大时限内完成。

### 5.2 后续轮

后续只处理：

- 新闭合 15m/1H bar；
- mark、成交、盘口、OI、funding、basis、波动变化；
- 新信息/注意力事件；
- zone touch/reaction delta；
- sentiment axis delta；
- 假说序数档位迁移、新假说和失效；
- 条件计划的新增、取消、加减仓或 reentry 变化。

每个缓存对象保存 `created_at/as_of/available_at/expires_at/invalidation_events/semantic_digest`。StrategicContext 只有在前序帧已验、TTL 未到且当前已验 bundle 的稳定战略投影逐字相同时 carry，且不续期、不换 source refs；TACTICAL/TRIGGER 每轮刷新。正式 acceptance 必须从当前 bundle 独立重算三帧 payload digest，并对每个 REFRESHED frame 精确重算固定 ID、decision/current-bundle 时点、角色 TTL `86400/3600/900` 秒、当前 source refs、dependency groups 与 invalidator sets；CARRIED_FORWARD strategic 继续由前序不可变字段约束。当前 OKX-only bundle 没有能证明宏观、监管、跨资产等事件类型的 owning schema，所以 production 只接纳前序 TTL 和 market-bundle 语义变化，其他 invalidation 明确为 `UNKNOWN_NOT_AVAILABLE` 并生成 data-gap/manual plan；任意 PIT digest 或 Agent 文本注入在 formal acceptance 失败关闭，不能把“枚举存在”写成“来源已接线”。

---

## 6. Agent 两阶段生产路径

```text
TickSupervisor opens cycle permit
→ source raw capture and admission
→ cache replay/rebuild
→ graph/zone/hypothesis/action pre-context
→ extract complete typed members and build reversible proposal compaction
→ mechanically derive mandatory proposal roots and current INLINE packet
→ controller writes exact AgentInputContext + compaction bindings
→ current root Codex proposal, one attempt
→ deterministic semantic compile + full legal action/risk evaluation
→ build reversible selection compaction and current INLINE packet
→ current root Codex selection, one attempt
→ controller writes AgentContextConsumption
→ build dynamic action plan
→ build V3.2 commit envelope
→ deterministically build and seal six-arm shadow_decision_bundle
→ full-original/compact-view/delivery replay and formal acceptance
→ outcome schedule + Supervisor completion
→ deterministic acceptance Chinese audit + AuditCompletionReceipt
→ deterministic tail recovery if interrupted
```

qualification、source/analysis、outcome 与 recovery 的中文 narrative 分别紧随其对应 typed boundary 生成并绑定；上图最后一项仅表示 acceptance narrative，不代表其他记录被延迟到 acceptance 后。

生产代码必须实际调用 context/consumption/commit builders 并由一个 controller owner write-once；纯 builder/test 不算接线。

Agent proposal 必须覆盖所有 legal actions，并为 WAIT 和每个 probe 提供机会成本比较。`CHOPPY/VOLATILITY_WITHOUT_DIRECTION` 下，方向候选只能是绑定 sealed `BREAKOUT_BOUNDARY` 的 blocked/conditional zero-current-risk/no-tranche 计划，不得被机会成本条款强迫开仓。Domain 从这些 sealed 对象确定性派生一个上下 research trigger pair：15m confirmed close、严格 `GT upper / LT lower`、最早 expiry、first-match retirement；Agent 不能修改阈值或 comparator。命中只触发 fresh reanalysis，当前没有连续 monitor、OCO 或真实订单；Selection 也不能看到未来 outcome 或更改支持档位与动作算术。

---

## 7. 动态规划对象

### 7.1 `ConditionalActionPlan`

包含：

```text
plan_id, cycle, as_of, expires_at
current_state_hypotheses
attribution_hypotheses
forecast_path_hypotheses
action_theses
legal_actions_considered
selected_research_action
alternative_action_rank
wait_opportunity_cost
next_review_or_event
```

### 7.2 `RiskTranchePlan`

包含 entry mode、方向、条件 zone、固定 raw envelope=`1 USDT non-account research stress`、ordinal-support/residual cap、hypothesis evidence-chain 诊断、typed regime/事实/objective-input 门、已构造 tranche geometry 验证、effective reference risk、unit loss、支持 clusters、共同/独立失效、结构/波动/时间保护、partial/runner/reentry 计划。该 `1 USDT` 只是不可执行研究比较单位，不是账户风险、订单名义或最大损失。正风险 tranche 的 `ctVal/ctMult/tickSz/lotSz/minSz` 必须来自当前市场图中 owning-verifier 已验的 PIT 合约规格；`multiplier=ctVal×ctMult`，价格对齐 tick，研究数量按 lot 向下取整且不低于 min。四项压力成本由合约暴露、该 tranche 入场价与预注册非账户 stress rate 确定性推导；真实账户费率、成交滑点和尾部最大损失继续为 dynamic-state legacy `UNKNOWN_MAX_LOSS / BLOCK_FUTURE_EXECUTION`。任一研究规格缺失时，compiler 的 objective-input 诊断使正 reference-risk 归零而零风险 WAIT 仍可成立；未来真实 max-loss 未知不得删除当前单一方向。Agent 不得覆盖 envelope、合约参数或压力值，也不得提交会缩放风险的主观质量档。Agent 主观 schema 只允许方向 `subjective_plausibility_tier` 与 `OTHER/UNKNOWN` 的 `residual_uncertainty_tier`；action-evaluation 的连续 `risk_reference_units` 仅是 sealed allocation 的 exact 派生回传，compiler 对任何漂移失败关闭。sealed builder 以方向档位上限和 residual 档位补集确定性缩放 envelope，不再暴露 `residual_uncertainty_quality` 或 `DEGRADED=50` 别名。zone/source/outcome 中由 owning verifier 产生的客观或诊断性 `quality` 不在此删除范围，且不得进入风险算术。hypothesis evidence-chain coverage 仅为可重放诊断，dynamic state 不含 source-admission coverage 时必须写 `UNKNOWN_NOT_IN_DYNAMIC_STATE`。已有 typed owner 的门不合法即零风险或拒绝计划，合法也不产生 HALF/NORMAL 吸引力标量；没有 typed owner 的流动性/成本/geometry 主观判断只进入 guard/rationale/Selection comparison，不改变 feasibility。分配器先同时约束全局包络与 LONG/SHORT 各自档位容量，再在方向内部以 HIGH=2、LOW=1、EXTREME=0 的离散 tranche 单位切分；多个 LOW cluster 或另一方向的 HIGH 均不能抬高本方向上限。path modifier 只允许 `ZERO/HALF/NORMAL` 非膨胀 cap。

### 7.3 状态而非成交

当前 Proposal 的 action plan 与每个 candidate 固定为 `CONDITIONAL`；Agent 不能在同一提交中把 `CANCELLED/EXPIRED/SUPERSEDED` 终态对象继续标为 eligible 或 selected。reentry obligation 仍可持久化 `PLANNED/CONDITIONAL/CANCELLED/EXPIRED/SUPERSEDED`，但其终态由对应生命周期规则重建；未来若要给 action plan 增加终态，必须使用独立 transition owner 和历史对象，不能复用当前 Proposal builder。禁止 `FILLED/OPEN_POSITION/REALIZED_PNL` 等账户事实。市场后续触及计划价只属于 outcome 评价，不改变成真实持仓。

### 7.4 期限与休眠监督

假说到期会确定性取消依赖其支持的未触发 plan；续期只能写新 revision，不能覆盖旧 expiry。系统维护两只 durable 时钟：`testable_risk_plan_clock` 只有合格且具有正风险预算的 probe/reentry 才重置，`model_adaptation_clock` 只有由新鲜 PIT 证据绑定的实质性状态/zone/hypothesis/threshold 变化才重置。任一达到 `8` cycles 或 `7200` 秒（任一先到）就写相应 `INACTIVITY_REVIEW_DUE`；普通市场变化、换 ID、改写文字、无关新引用和 Agent 自述均不能洗掉计数。下一轮必须重建相关假说/阈值诊断和 shadow baselines；该状态不能自动生成仓位。

### 7.5 外在路径与 stop-not-fill

`ExternalPathModifier` 记录 false break、liquidity vacuum、forced liquidation、cross-venue dislocation、event shock 和 venue/network disruption。每个 modifier 必须与受影响 zone/hypothesis/plan 共享 dependency。`stop_touched/limit_touched` 只是 observation；outcome contract 永不产生 fill/PnL，且保存 `EXECUTION_NOT_OBSERVED` 或压力 hazard 分支。

### 7.6 混沌、重入与未来执行隔离

`MarketRegimeState` 原生覆盖 `TREND_UP/TREND_DOWN/NEUTRAL/RANGE/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN`。`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 令当前 directional new risk 为零；risk-increasing candidate 必须保持 `CONDITIONAL/BLOCKED/no-tranche`，且全部 zone refs 必须是 sealed `BREAKOUT_BOUNDARY`。Domain 已为再分析边界派生 typed close comparator、阈值与有效期，但 candidate trigger/guard 仍有分析文字，且没有连续监测、可执行订单或 OCO。`TRANSITION` 只有通过方向转换门后才能成为 `TREND_UP/TREND_DOWN`。`RANGE` 不在强制零集合中，只有结构化边界、成本与失效条件完整时才保留条件性均值回归。当前实验不发送上下双向挂单，也不研究卖出期权。

`CHOPPY` 不是 Agent 的自由标签：必须同时封存 `DIRECTIONAL_PERSISTENCE=LOW / REVERSAL_FREQUENCY=HIGH / EXECUTION_CHURN_PRESSURE=HIGH`；`VOLATILITY_WITHOUT_DIRECTION` 必须同时封存 `DIRECTIONAL_PERSISTENCE=LOW / REALIZED_VOLATILITY=HIGH / DIRECTIONAL_IMBALANCE=BALANCED`。每项 assessment 都要引用当前 PIT，并由图闭包证明属于允许的 `PRICE_ACTION/TRADE_FLOW/ORDERBOOK_LIQUIDITY/POSITIONING/FUNDING_CROWDING` 可观测族；目标 regime 至少两个引用、两个族。转入该状态时全部 feature refs 必须属于 fresh transition refs，单一无关引用不能改变 regime。

每个 instrument 只有一个耐久 `ReentryBudgetState` 全局 churn breaker。source tranche 首次退出只创建 `AVAILABLE` ledger，计数必须为 `attempts=0 / consecutive_failures=0 / cumulative=0`。当前 pilot 冻结 `rolling_window=24h`、`per_attempt_reference_risk<=1`、`max_attempts=2`、`max_cumulative_reference_risk=2`，调用者不得覆盖；累计值按 `0.000001` 量子对齐并满足 `attempts×0.000001 <= cumulative <= attempts×1`。ledger `INACTIVE` 时的首次 `OPEN_PROBE` 不计作 reentry；一旦 ledger 激活，任一方向最终选中、合格且 reference risk 大于零的 `OPEN_PROBE/REVERSE/REENTER` 都使共享 attempts/cumulative 精确累计。同方向恢复仍必须规范化为 `REENTER`，但真正换向可以保留 `REVERSE/OPEN_PROBE` 语义，同时消耗相同预算。未选择、零风险或 blocked 候选不增加。当前选择还必须满足 `attempts_used < max_attempts`、单次 risk 不超过 `1`，且 selected risk 不超过 `max_cumulative_reference_risk - cumulative_reference_risk`，同一轮不能先越界、下一轮才失败。`COOLDOWN` 至少已有一次正风险尝试与一次失败；未耗尽时剩余额度必定至少为 `1`，不需要会制造最小量死锁的临时截断。方向、cluster、regime、hypothesis ID 或 action label 改变不能建立第二预算。达到次数或累计上限后 `EXHAUSTED` 持久锁定，cooldown 精确等于原 rolling window 的绝对终点且到期不自动解锁；原窗口终点前禁止 RESET，终点后仍须实质不同的新 cluster、可验证 regime 转换和新 tranche 三门。该 ledger 是不可执行 research-plan 防重复机制，不声称 fill、position 或实盘磨损；未来执行层必须另绑定真实成交/仓位真值。

初始 `HIGH` 或 `LOW→HIGH` 至少需要两个 fresh refs、显式且当前可用的方向性反证，以及 `mechanism-distinct evidence` 门。真实 formal OKX 图的 `605/605` 条 closure 共享 `VENUE:OKX`，证明“完整 closure 必须全不相交”的旧门会令 HIGH 结构性不可达。系统不删除或缩短完整 provenance/dependency closure；仅在该门的配对判定中忽略共同 `VENUE/PROJECTION` lineage，其他物质依赖仍须不相交，并要求不同 `REQUEST` 与不同的方向性 `OBSERVABLE_FAMILY`。`TICKER/MARK/CANDLES` 统一归入 `PRICE_ACTION`，因此两个价格/K 线请求不构成双机制；`PRICE_ACTION` 与 `TRADE_FLOW/POSITIONING/FUNDING_CROWDING/ORDERBOOK_LIQUIDITY` 等实质观测机制不同的证据才可能成对，`PROVIDER_METADATA/CONTRACT_SPEC` 禁止充当方向支持或反证。这是反重复计数门，不是统计独立、因果识别或胜率证明。从非方向 regime 恢复到方向 regime 同样要求该双机制差异 fresh refs，或由系统从连续两根合格闭合 15m bar 机械判定；进入非方向 regime 可由一条 fresh hard evidence 支持。双 inactivity watchdog 在当前 pilot 精确冻结为 `8 cycles / 7200s`，genesis 与后续调用均不能覆盖。

未来真实执行若另行授权，只能由独立 `EmergencyExecutionCapsule` 而非 Strategy Agent 负责；它当前机器状态为 `NOT_IMPLEMENTED_NOT_QUALIFIED`，当前 read-only recovery observer 也明确 `supervisor_is_execution_risk_supervisor=false`。只有 venue 支持原子 attached protection 时，保护才可与入场同请求并独立确认；不支持该能力的执行模式默认禁止新增暴露，不能假设零持仓时先挂 reduce-only。若出现 fill→保护确认间隙，进入 `UNPROTECTED_EXPOSURE`、冻结新增风险，并按预授权幂等 reduce-only IOC/marketable close 与独立 position-truth reconciliation 处理；只有另行授权才允许 market fallback。venue 全不可用时记录 `EXPOSURE_UNRESOLVED_VENUE_UNAVAILABLE`、告警并转人工渠道。除独立授权外，还必须先资格化账户/仓位真值、原子保护、订单状态机、幂等退出/partial-fill/over-close/超时对账、冗余传输、外部告警与 chaos tests；该未来合同不进入本次不可执行 authority，也不承诺保证价格、成交或最终清仓。

---

## 8. AnalysisClock 与 OutcomeClock

### 8.1 对齐 tick

建议 pilot 固定 UTC 15 分钟边界：`00/15/30/45`。每个 analysis cycle 使用边界后首次合格公开 PIT capture，记录计划边界、实际 capture、provider time 和 receive time。

### 8.2 outcome horizon

每个正式 decision 事前安排：

```text
T+15m  触发/抢跑质量
T+1h   战术路径
T+4h   结构延续/反转
```

三者共享未来 `OutcomeObservationTick`；同一未来 mark capture 可解析多个到期 decision/horizon，不为每个 outcome 重复请求。共享不改变各自的 baseline、规则、horizon 和 receipt。

### 8.3 到期顺序

一个 observation tick 的事务顺序：

```text
reserve unique tick attempt
→ transport/raw write-once
→ parse point-in-time mark/quality
→ identify all due schedule IDs
→ build one batch intent
→ write one outcome receipt per schedule
→ seal batch completion
```

崩溃后只从已有 raw/batch intent 恢复确定性尾部，禁止第二次网络请求。一个 schedule 最多一个 attempt。

### 8.4 与新分析轮的关系

同一 tick 如需新 Agent cycle，先封存已成熟 outcome，再构建新 Agent input；这样 Agent 可以合法学习 `available_at <= decision_time` 的结果。未到期结果不可见且不阻塞。

---

## 9. Supervisor 与失败分级

### 9.1 lane

```text
AUTHORITY_LANE
SOURCE_LANE
ANALYSIS_LANE
AGENT_LANE
COMMIT_LANE
OUTCOME_LANE
AUTOMATION_LANE
```

### 9.2 可继续的覆盖损失

仅冻结白名单内的 timeout/connect、HTTP `429` 或 `5xx`，并且只针对 optional component，在 raw/transport-failure receipt 已保存时才可记为 `UNKNOWN_COVERAGE_LOSS`；同一 attempt 不重试。required component 的上述故障仍使当前资格或 lane 失败关闭。收到 HTTP response 后，每个组件的 `0..MAX` 字节 body 与 method/path/canonical query、status、final URL、request/received/captured time、attempt=1/no-retry 必须先组成固定可推导的 self-digested capture bundle，write-once 发布并完整回读后才允许解析或下一请求；若 timeout/connect 发生在任何 response 前，optional component 同样先发布并回读逐组件无响应 receipt，绑定固定请求身份、started/failure time、route、attempt=1/no-retry、稳定错误码以及 `response/body/status/final_url` 全部不存在，再允许生成 UNKNOWN 或下一个请求。aggregate 与 durable replay 必须绑定 owning receipt；缺失、篡改、交换、时钟错误或 sink failure 均失败关闭。HTTP `400/401/403/404`、redirect、HTTP 200 但 provider `code != 0`、零字节/无效 JSON、无效 provider envelope 或必需 datum 字段缺失属于封存后的结构失败，不能降级为无响应或 coverage UNKNOWN。

### 9.3 必须失败关闭

摘要漂移、wrong run/cycle、未来数据、authority 不一致、同一 attempt 二次调用、raw 与解析不匹配、commit 状态冲突、Agent 超过一次、错 support role 或无可定义损失边界时，相应 lane 永久 fail closed。若影响状态完整性，整个 run 停止并保留证据。

### 9.4 恢复边界

恢复必须匹配 §4.6 的八项 action ID；未列入即禁止。permit 已开但后续没有任何冻结 intent/bytes 时不能重新采集或重新调用 Agent；Agent request 已发未完整交付时失败关闭；raw 只有在 batch intent 已封存且同一 parser 无语义失败时才能补尾；任一写入内容、摘要、物理字节或唯一 predecessor 不一致均永久 fail closed。监督 Agent 只能报警，不能直接执行或扩大这份白名单。

---

## 10. V3.2 版本化实现范围

保留并复用：

- V3.1.1 raw-first capture、outcome evidence、clock policy；
- unified Supervisor 的状态校验思想；
- twelve-axis source registry/projection；
- 144 条 association 候选全集预注册与 UNKNOWN 评价边界；
- fresh source/Codex/monitor qualification 的机制与代码；V3.2 必须在新 authority 前重新生成 fresh 资格证据，禁止复用旧资格结果；
- direct full-theory Agent lifecycle、write-once commit、authority full loader；
- 旧 v2 Q0–Q8 与 74 frozen paths 的只读重放。

当前版本化实现按四层落在下列真实模块组中；禁止改旧 frozen bytes：

```text
Domain:
  v32_dynamic_research.py
  v32_dynamic_action_plan.py
  v32_context_compaction.py
  v32_unknown_assessment.py
  v32_data_gap_escalation.py
  v32_environment_capability.py
  v32_cycle_audit_narrative.py
  v32_recovery_supervision.py
  v32_actual_capability_attempt_progress.py
  governance/v32_experiment_contract.py

Application:
  v32_cycle_composition.py
  v32_cycle_acceptance.py
  v32_authorized_revision_orchestration.py
  v32_actual_capability_ports.py
  v32_actual_capability_qualification.py
  v32_actual_capability_qualification_controller.py
  v32_outcome_tick_composition.py
  v32_prospective_runtime.py

Infrastructure:
  v32_dynamic_store.py
  v32_local_analysis_lane.py
  v32_local_outcome_lane.py
  v32_local_audit_lane.py
  v32_authorized_revision_store.py
  v32_public_source_collector.py
  v32_public_market_graph_projection.py
  v32_public_https_route.py
  v32_okx_public_bundle_transport.py
  v32_okx_public_outcome_adapter.py
  authority/v32_actual_capability_attempt_ports.py
  authority/v32_actual_capability_replay.py
  authority/v32_authority_lifecycle.py
  authority/v32_current_research.py

Presentation:
  v32_qualification_composition.py
  v32_target_run_composition.py
  v32_target_wake_composition.py
  v32_cycle_audit_presenter.py
```

以上是职责映射，不替代冻结清单。最终 authority 必须以 production entrypoint 的机械 AST/local-import closure 和物理摘要为准；任何手写文件表都不能单独证明 production composition、formal acceptance 或 full loader 已接线。

提交 `66197c4` 与第七资格已把当时的 `43` 个 production roots、`194` 个递归可达本地路径和 `194` 个 frozen bindings 固定为历史 exact closure；新增 fresh-process receipt 的 authority/manifest/full-loader owner 与 post-commit、增量市场图、共享公开 HTTPS route、Application capability ports、Domain attempt-progress verifier 均在其中。第一版 commit `d5478d...` 的 `32/186`、提交 `975e7a8` 的 `42/190` 和第六资格 exact commit `e0c7d3d` 的 `42/192/192` 也只属于各自历史快照。当前 burst/WAIT 候选虽未新增 production path，但改变了受绑定字节，仍必须由新 exact commit、WorkspaceFreezeReceipt、post-commit replay 和第八资格重新冻结；不能否定或改写第七资格的历史 `43/194/194` 证据。旧 V3.1 的 `74` 个冻结路径与字节不作修改。

---

## 11. 资格实验

资格 run 与目标 run 分离且永不计入目标。至少验证：

1. 新 authority 后 fresh 单次公开 source；
2. 完整 V3.2 正文、canonical packet 和 exact support roles 进入当前 root Codex；
3. proposal→compile→selection→consumption→commit 生产 writer 真正接线；
4. 首轮 full context 与一轮 15m delta；
5. 至少两个 overlapping outcome schedule 共享一个 raw tick；
6. raw-after-reserve crash、parse fail、batch partial write、重复 wake、clock skew、wrong role、wrong theory hash、Agent interruption、commit tail recovery；
7. 单一 LOW、多个重复 HIGH、旧 0–100 字段、modifier 无依赖广播、expiry/reentry reset 洗白、inactivity 强制交易和 stop-touch→fill 冒充全部被拒绝；
8. 原件含 UNKNOWN/反证/hazard 但 member inventory 或 required roots 故意遗漏时拒绝；closure digest/count、source→member coverage、当前 exact INLINE delivery 和 round-trip 全部重算；未来 SHARDED 另行资格时才加入 exact shard delivery；
9. 不存在的 PIT/mechanism 摘要、assessment 早于 UNKNOWN、人工证据倒填 available-at、人工回填旧 cycle/outcome 全部拒绝；
10. EnvironmentCapabilityProfile 漂移、低容量、clock/TLS/storage 能力缺失只能资格失败或 UNKNOWN，不能降低理论/评价；
11. Supervisor 无法访问未到期 outcome、market/Agent/formal writer；自然语言 alert 不能直接触发动作，非白名单恢复拒绝；
12. 各 typed boundary 后 narrative 分片/index 可确定性重建；acceptance narrative 不存在 acceptance 自引用；
13. WorkspaceFreezeReceipt v1.1 绑定 exact commit/tree/clean closure 与两份 write-once post-commit 全回归收据；每次 qualification wake 在副作用前完整重放 Phase-A/Q0–Q8/support/runtime closure/post-commit 原件；该绑定仅证明受信任本地控制器审计链的一致性，不冒充独立或抗恶意本地写入 attestation；
14. qualification retirement 同时绑定 research/outcome/audit checkpoints 并禁止 automation/进一步 cycle。
15. capability adapter 返回 `COMPLETE` 后，controller 必须经固定 EvidenceStore 与 owning verifier 物理重开 binding，重验 schema、digest field、语义摘要、物理 SHA-256、规范字节、完整 root 内容及 capability 专属规范路径；畸形、缺失或字段完整但物理身份不成立的 binding 必须在一次 attempt 后永久 `FAILED_CLOSED`，不得推进下一 capability或再次调用 adapter。
16. bundle、qualification probe 与 target outcome 必须由同一冻结的无凭据公开 HTTPS route policy 构造；含 proxy userinfo、运行时 bypass、redirect、非法 host/path/header 或 route drift 时在请求前结构性失败。真实 timeout/DNS/TLS/connection/provider 失败必须保留精确物理叶节点；qualification source 依次封存 attempt、已有 body（若有）、typed failure receipt、terminal controller，不得 fallback/retry。失败 qualification 第二次 wake 为零 network，successor 使用新 commit、新 ID 和独立 root，旧根字节不变。
17. 真实 `96/168/90/60` 四周期 bars 形态下，Agent view 必须保留全部 citable evidence/dependency groups/UNKNOWN/OTHER 并在固定 256 KiB cap 内；完整 closure registry owning replay、摘要/计数/组篡改反例、proposal/selection packet 和 complete input 的独立容量门全部通过。
18. CURRENT_CODEX reservation 后任一 materializer/validation/capacity exception 必须写一次物理绑定 failure receipt 并由 controller 原子进入 `FAILED_CLOSED`；crash-between-receipt-and-checkpoint 只能完成同一 terminal CAS，后续 wake 不得再次 materialize、调用 Agent 或建立 monitor。material/mailbox/probe prefix 重扫成功时标记 `VERIFIED_EXACT` 并绑定 exact inventory；重扫异常时标记 `UNKNOWN_REPLAY_FAILED` 与稳定 `*_PREFIX_REPLAY_FAILED` 代码，不得以空 inventory 冒充完整，但同一 attempt 仍须永久终止。第五 qualification/target exact identity 必须在所有固定公开 API 的 runtime/authority 访问之前拒绝。
19. request、claim、delivery/receipt、consumption/receipt 四阶段分别注入“对象已发布、checkpoint CAS 未完成”故障；重放只补 exact tail，保留首次字节与时间，冲突 payload、第二次 Agent 或第二次 delivery 均拒绝。write-once 文件须证明完整写、file fsync、不可覆盖原子发布和 parent-directory fsync。
20. delivery receipt 必须绑定 exact `CurrentCodexPresentationEnvelope` digest；qualification full replay 从 CLAIMED 快照重建并逐字核对。CLAIMED lost-response 重放必须零写、零新时钟；target/qualification 最终 Agent-facing 返回均直接为该 envelope，canonical bytes `<= 1 MiB` 且 pilot 只允许 `INLINE_ONLY`。
21. 真实 fresh-process collector 必须在 Phase-A 任一 authority byte 和资格 System UTC 时钟前运行；typed receipt 被 write-once 保存并以物理 SHA-256 进入 support、manifest、runtime closure 与 Q1/full loader。第七资格已关闭 `43/194/194` fresh-process 与 PUBLIC_SOURCE 子门；当前调度修复和完整 Codex/monitor 链只能由新 exact commit 与正式第八资格关闭，不能以静态 roots、本地测试或第七迟到交付替代。

任何使用 fixture 预制 Agent 最终语义的结果只能作为本地测试，不是当前 Codex 资格。

---

## 12. 推荐目标 pilot

### 12.1 名称与规模

推荐冻结为：`V32_DYNAMIC_AGGRESSIVE_BTCUSDT_15M_PROCESS_PILOT`

- 标的：`BTC-USDT-SWAP`；
- 公开数据、本地、不可执行；
- `16` 个正式 analysis cycles；
- Cycle 1 为 full context，Cycle 2–16 为 15m delta；
- 每 cycle 安排 `15m/1h/4h` 三个 outcome；
- 最后一个 Agent cycle 后继续 outcome-only ticks，直至 `48/48` schedules 终局；
- qualification/旧失败/V3.1.1 样本均不计入。

### 12.2 完成标准

```text
analysis_cycles = 16/16 accepted
scheduled_outcomes = 48/48 terminal
agent_attempts = exactly one proposal + one selection per cycle
all raw/tick/batch/commit/checkpoint receipts replayable
no future outcome leakage
no paper/live/account/order/credential/funds interaction
```

`terminal` 可以是合法观察或预注册 `UNKNOWN_COVERAGE_LOSS`；内部完整性失败仍终止 run 且不得改称完成。

### 12.3 该 pilot 能回答什么

- Agent 是否能维护相反假说、非方向 regime 和三档主观支持；
- 是否真的产生 probe/add/reduce/reentry/WAIT 的完整比较；
- 15 分钟 delta、缓存、共享 outcome tick 和恢复是否可靠；
- 历史磁区/RSI 是否在预先声明的短窗有描述性区分。

### 12.4 不能回答什么

- 稳定盈利、月收益或年收益；
- 概率校准；
- 真实成交、滑点、funding 或 PnL；
- 跨 regime 泛化；
- Agent 优于系统基线的统计显著性。

这些继续为 `UNKNOWN_NOT_EVALUATED`。至少需要后续 `>=240` 点时 decision observations 和独立 episode/cost contract 才进入市场增量评价。

---

## 13. pilot 的事前比较

同一 source/PIT/outcome 上确定性生成以下 shadow labels，不调用额外 Agent：

```text
V32_SELECTED_PLAN
V31_CONSERVATIVE_WAIT_BIASED_REFERENCE
WAIT_ONLY
SIMPLE_15M_TREND
NO_RSI_REFERENCE
ALWAYS_LONG_PUBLIC_MARK_REFERENCE
```

本地 deterministic adapter 只允许由冻结规则生成各 arm：WAIT 和 always-long 是常量策略，简单趋势使用最后两根合格闭合 15m bar，selected 复制 sealed plan；没有同 PIT、同规则的 V3.1/no-RSI 计算时，两臂必须是 `UNKNOWN_NOT_COMPUTED`。当前 outcome 仅有 terminal mark，因此只比较终点方向一致性与 coverage；path alignment、MFE/MAE、机会错失、fill、position、PnL、数值概率和 EV 全部保持 UNKNOWN/禁止。只有未来冻结 horizon 内完整路径合同后，才可新增路径指标。

历史 zone 候选、RSI arms、窗口和阈值必须在第一个 outcome 前冻结；不得看到结果后移动关口或更换 RSI 规则。

---

## 14. authority chronology

```text
final code + docs + revision contracts
→ branch/HEAD/status/untracked/sensitive/history inventory
→ explicit staging list and exact Git commit; never git add .
→ clean qualification worktree + WorkspaceFreezeReceipt
→ post-commit full regression/import closure/format/old Q0-Q8 and 74-path replay
→ final user approval receipt bound to exact theory/contract/commit packet SHA
→ freeze EnvironmentCapabilityProfile and all new support policies
→ qualification Phase A + Q0-Q8
→ qualification authority
→ qualification genesis
→ fresh source/current Codex/outcome-tick qualification
→ qualification retirement
→ target Phase A + Q0-Q8
→ target authority and genesis
→ target cycle 1
→ reuse one existing paused automation with updated prompt/run
→ 16 analysis cycles
→ outcome-only tail until 48 terminal
→ final loader/replay/report
```

任一 code/doc 修改都使后续 closure/authority 失效，必须在冻结前完成。旧 automation 不恢复为旧 run，也不创建第二个监控任务。

---

## 15. 测试与验收

### 15.1 Domain

- UNKNOWN 分类逐类行为；
- 三档 support、相邻变档、PIT update refs 和非概率边界；拒绝所有旧 0–100 字段与兼容别名；
- dependency cluster 重复证据不增风险；
- opposing hypothesis/OTHER/UNKNOWN 完整；CHOPPY/方向未知不被强迫分配 directional risk；
- zone 事后移动、错时点、错依赖拒绝；
- risk-first allocation、不同 stop 距离、lot rounding；
- ordinal support/residual 缩放先于离散 tranche 分配；coverage 只作可重放诊断且缺失 source-admission 保持 UNKNOWN；单一 LOW 和多个重复 HIGH 都不获满预算；
- WAIT 不得用一般不确定性绕过 probe；
- inactivity review 不得强制开仓；
- add/average-down/reverse/reentry 状态不变量；instrument 全局 churn breaker、同方向动作别名、累计风险、原绝对窗口与非法 reset 对抗；
- modifier 只能影响共享依赖对象，expiry/renewal 不能只改时间戳；
- stop/limit touched 不得变成 fill、position 或 PnL；
- RSI 不能直接改变 risk budget。
- source→member 完整投影、可逆 round-trip、closure 重算和强制 roots 无遗漏；
- 调用者伪造 member inventory、遗漏 UNKNOWN/hazard 或任意 required IDs 必须拒绝；
- ObjectiveUnknown 不可被 subjective assessment 改写；引用解析、chronology、opposing binding、expiry 和零客观贡献；
- manual evidence 实际 available-at、future-only revision 和 dependency 去重；
- Environment profile required capability 与不降低理论/评价不变量。

### 15.2 Application/Infrastructure

- full→delta cache、TTL、event invalidation；
- closure/artifact/accepted-prefix 缓存只在精确物理身份未变时命中；篡改、重启和版本变化触发全量重放；
- exact theory/support context writer；
- Agent single attempt；
- consumption/commit full replay；
- one raw tick resolves multiple schedules；
- reserve/crash/partial batch/replay/no second GET；
- due/overdue/clock skew/transport failure；
- bundle/probe/outcome 的零字节 body 先封存后结构失败、HTTP 200 provider error code 与 4xx 不得降级 coverage、失败后零二次网络；
- accepted/schedule deterministic tail；
- full loader、tamper、import closure、wrong run/cycle；
- actual-capability progress 的短缺 binding、字段完整但路径/物理摘要不成立的 binding、durable root 缺失、resume token/time 不成对和 post-progress checkpoint 构造失败；任一情况只允许一次 adapter 调用，永久 `FAILED_CLOSED`，后续 wake 不推进下一 capability。
- proposal/selection full-original + compact-view + 当前 exact INLINE delivery replay；未来 SHARDED 机制保持禁用；
- DataGap/ManualAdmission/EnvironmentConformance/RecoveryTrace registries 进入 formal acceptance；
- typed-boundary 后 audit 无自引用、章节分片完整；acceptance narrative 与下一 analysis permit audit gate；
- read-only supervisor capability denial、future-outcome 隔离和 recovery whitelist 全拒绝测试。
- 冻结机器端到端计时：初始轮不超过 15 分钟、普通 delta 轮目标 1–2 分钟，并至少为最早 outcome 宽限保留冻结余量；不达标保持 NO-GO。

### 15.3 最终检查

- project Python `/opt/homebrew/bin/python3.12`；
- 旧 active authority、Q0–Q8、物理证据和 74 paths 只读重放；
- V3.1/V3.1.1 focused/full suite；
- V3.2 full suite；
- JSON/Markdown/compile/diff check；
- exact branch/commit/tree、clean qualification worktree、explicit staging 与敏感信息检查；
- 新 support bindings、扩展后的 formal acceptance 和 authority Q1/Q2/Q3/Q5/Q6/Q7/Q8 全链重放；
- 单一 automation、旧任务 PAUSED；
- 无 paper/live/account/order/credential/funds 调用路径；
- 非破坏性清理仅删除本任务可重建缓存。

---

## 16. 当前状态

- 理论方向与五问题裁决：V3.2.1 语义底座已完成；当前文档版本为 `3.2.6-five-trap-hardening-candidate`，正在收口第七资格暴露的材料调度，以及五项易碎性复核发现的图重复验证、风险所有权与构造性问题；
- 三档主观支持（连续 risk 字段仅允许 deterministic derived echo）、typed 混沌与 `BREAKOUT_BOUNDARY` 零风险条件候选、每 instrument 全局 24h/两次/累计 2 的 reentry ledger、owner-bound 图验证 scope，以及 `EmergencyExecutionCapsule=NOT_IMPLEMENTED_NOT_QUALIFIED`：已进入 Domain/Application/Infrastructure/Agent compiler 与聚焦回归；
- 可逆 context delivery、UNKNOWN/DataGap/manual evidence、environment profile、typed-boundary 后 audit、read-only supervision、revision stores、workspace freeze：已进入 production composition、28 组件 acceptance、authority builder/runtime closure 与 full loader；
- actual-capability 分层和 durable-binding 两次独立 P1：已修复并独立复核；Application 的 22 个 V3.2 根、48 个递归可达本地模块没有 Infrastructure/Presentation 反向依赖；
- production closure：提交 `66197c4` 与第七资格实际使用 43 roots / 194 recursively reachable local paths / 194 frozen bindings；第一版提交的 32/186、`975e7a8` 的 42/190 和第六资格 `e0c7d3d` 的 42/192/192 保留为历史，旧 V3.1 74 路径保持不变；
- 第一版 exact commit=`d5478d9463961a65d7167642c0c67e6c275f6ebf`；post-commit V3.2=`502/502 PASS / 984.937s`，Theory Paper V2=`1187/1187 PASS / 1256.535s`；
- 七份资格均为历史只读树：前四份在 PUBLIC_SOURCE 永久失败；第五份在旧 Agent view 容量/非终态边界失败；第六份在 `CONTEXT_PACKAGE:PROPOSAL` revision `4` 永久 `FAILED_CLOSED`；第七份在 fresh-process、PUBLIC_SOURCE 与 proposal request 后因 reservation 窗口耗尽成为治理 `EXPIRED_TERMINAL`，原 runtime 保持 `RUNNING/revision 3 + REQUESTED + no claim`。六个 failed pair 与一个 expired pair 共同 tombstone，不能重试、推进、改写、删除或混配；target authority/genesis=0，正式 outcome 未读取；
- 单一 Presentation、完整输入总门、claim 前失败原子性、四阶段 exact-tail、file+directory fsync、Presentation-digest/full-replay、CLAIMED 零写重放、final-envelope direct return 与真实 fresh-process receipt 已提交到 `66197c4`；当前未提交候选增加 bounded material burst、第七历史 subject 精确重放、七组入口 tombstone，以及 zero-eligible WAIT 的 owning-cause 二次加固；
- 当前聚焦回归已覆盖 burst、probe/controller 停止边界、历史身份与 target 入口；全量 V3.2/全 Theory Paper、冻结树复核、显式 staging/commit 和新 exact-pair 正式收据仍须完成。当前不能生成第八资格 authority；
- V3.2 target authority/target run：未开始；
- 正式 outcome：未读取；
- 交易权限：零。

因此，早期“一份失败资格、等待第二次 commit”的状态已经被六次 durable failure 与第七次 expired-terminal 事实 superseded。第七资格证明正式本地收据、fresh-process 与公开来源成功，仍不能替代 Current Codex 完整耐久交付或 monitor 资格；当前 bounded-burst 候选只有在全量回归、显式提交以及第八 exact pair 固定 runner 产生真实本地控制器收据后才能启动。当前 Codex 耐久交付与固定 outcome monitor 继续为 `UNKNOWN_NOT_QUALIFIED`。任何“文档已完成”、提交前测试 PASS、12/12 HTTP 200、本地可重建 envelope 或第七 proposal 已入队都不得改写为实验或预测已经完成；后续若发现新故障，必须重新阻断。

---

## 17. 本轮提交前最终设计状态

五项新质疑已形成唯一实现语义：三档支持取代连续主观输入，连续 risk 只可作为 sealed plan 的 exact 派生回传；混沌/无方向状态为零当前方向风险，且风险候选必须绑定 typed `BREAKOUT_BOUNDARY`、保持未触发/无 tranche；reentry 使用每 instrument 全方向共享的 24h、单次≤1、最多两次、累计≤2；未来物理逃生舱状态为 `NOT_IMPLEMENTED_NOT_QUALIFIED`，当前 recovery observer 不是 execution risk supervisor；依赖身份不删除，但热路径只处理有界 working set 和 delta，同一 owner-bound acceptance scope 的相同 strict snapshot 仅完整重建一次 closure。固定 24h 同类证据归并从能力声明中删除，避免把未实现窗口写成已实现事实。

提交前耐久设计同时关闭以下阻断路径：

1. fresh trace 已产生但 Phase-A authority 只写入一部分：外部意图保存原 trace/时间，整套 runtime 目录一次原子发布；
2. stage 已完整、final 尚未激活：唯一且字节全集相同的 stage 可收养；不完整或不同的唯一安全 stage 清理后重建；多项、非法名、symlink、特殊对象或 inode 漂移失败关闭；
3. final 在检查与 rename 之间并发出现：Darwin 使用 anchored `renameatx_np(RENAME_EXCL)`，不支持平台直接失败关闭，不回退普通 rename；
4. public source 在 attempt/raw/capture 后本地崩溃：依据现有耐久前缀封存稳定 failure terminal，绝不再次调用外部 transport；
5. mailbox request/claim/delivery/consumption 或 dynamic role 已落盘而 CAS 未完成：只核验并附着首次原字节/首次时间，零新网络、Agent 和时钟；
6. audit narrative 多文件半发布：successor 使用单目录 atomic bundle；完整 legacy layout 原路径可重放，partial legacy 失败关闭；公开 loader 仍保持 `directory + shards` 合同，内部 binding 不泄漏。

当前包级 `trade_system/theory_paper_v2/v32_durable_json.py` 是唯一 shared owner；旧 Infrastructure 路径只作兼容导出。Application 不再反向导入 Infrastructure。production closure 仍为 `43 roots / 194 reachable paths / 194 bindings`，旧 V3.1 的 `74` 个冻结路径不变。

提交前从零结果：V3.2 `738/738 PASS / 1705.807s`（real `1706.23s`）；全 Theory Paper `1505/1505 PASS / 2018.226s`（real `2018.83s`）。该耗时属于包含大量故障注入的资格冷路径，不能冒充普通 15 分钟分析延迟。显式提交、post-commit 固定 runner receipts、新 qualification exact pair、真实 Current Codex/monitor 资格和实际周期时延仍未完成，因此 target authority、target genesis、正式 cycle 和 outcome 继续为未开始。

---

## 18. 提交后第七资格：窗口耗尽与有界子阶段 burst

提交 `66197c47a1281340b4226da825da0b18d8815c3e` 的固定 post-commit runner 已真实得到 V3.2 `738/738` 与全 Theory Paper `1505/1505`，网络调用为零；随后第七资格 `v32-qualification-btcusdt-20260809t215807z` 完成 Phase-A、PUBLIC_SOURCE 与提案材料。它没有重现 1 MiB 容量错误，但暴露新的调度 P0：CURRENT_CODEX 于 `23:03:47.940793Z` 预留，提案到 `23:12:49.071891Z` 才入队，claim 时已超过 reservation 起算的 `660s` 硬窗口。

根因不是 Agent 分析或网络，而是 composition 把 materializer 的每个 append-only 子阶段拆成独立外部 wake；每次都重新启动进程并完整重放 authority。修复保留 materializer 的单子阶段合同，在 composition 内复用 runtime support 已冻结的 `MAX_ANALYSIS_SUBSTAGES_PER_WAKE=64`：

```text
one qualification high-level wake
  -> up to 64 write-once/CAS material substages
  -> stop on AWAITING_AGENT | READY | no-progress
             | QUALIFICATION_MONITOR_PROBE_* | exception | hard cap
```

proposal/selection mailbox 等待点绝不跨越；probe schedule 是独立高层边界，写入后立即返回，下一 wake 才允许 controller 完成 CURRENT_CODEX。每个内部步骤仍从原 reservation 校验 `660s`，没有把时钟起点后移到 request，也没有扩大预算。进程中断时已写前缀仍由现有 exact-tail/failure receipt 恢复。

审计输出分开记录 `burst_step_*` 与 `internal_append_only_substage_*`：前者包含终止用的只读检查，后者只包含真实内部写入且排除独立 probe 高层边界，避免以计数名称把两种边界混为一谈。

第七资格不是 durable `FAILED_CLOSED`：真实控制器仍为 `RUNNING/revision 3`，mailbox 为 `REQUESTED`，claim/delivery 不存在。设计将其独立分类为治理 `EXPIRED_TERMINAL`，与六棵 durable failure 分开；两类共同进入不可复用 tombstone，且第七 Q0–Q8 原始 subject digest 仍可精确离线验证。所有 qualification 公开入口和 target 入口必须先拒绝该 exact pair，禁止迟到 claim、补 delivery、补 monitor 或 target authority。

预演同时发现并关闭 zero-eligible WAIT 的相邻 P0。若 sealed evaluation 中仍有方向风险候选，Selection 继续以完整 candidate comparisons 证明 `WAIT` 的相对优势；若 `CHOPPY/NEUTRAL/UNKNOWN` 或客观硬门使方向风险候选为零，comparisons 必须为空，reason 固定为 `WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION`，refs 只能由 sealed evaluation 的 blocked rows、sealed plan 的 blocking refs 和 market-regime refs 确定性重建。Agent 不得自由填写 refs，编译器也不得虚构一个多空候选来满足 schema；reason、refs 或 comparison 集合不一致均失败关闭。

候选可行性本身也属于 owning system，而不是 Agent 的自由叙事字段。当前实现对每个 `BLOCKED` 候选逐一复核，不再只在“多空全部归零”时检查：Domain hard gate、residual cap=`0 + exact hypothesis-source refs`、全 instrument churn 对 `OPEN_PROBE/REENTER/REVERSE` 的 `COOLDOWN/EXHAUSTED + exact failure refs`，以及 compiler 从正式 packet 独立证明的 objective-input 缺失是当前仅有合法来源。`AVAILABLE/RESET` 假冷却、自由 COST/GEOMETRY、别名、superset refs 或把新增风险量子理由用于 `HOLD/REDUCE/CLOSE` 均失败关闭。没有 typed owner 的 geometry/cost 判断仍可写入 trigger、guard、rationale 和 WAIT comparison，但不能静默删除一侧方向后放大另一侧仓位。

生产外层 composition 接口的确定性夹具回归现要求两个 outer-wake 断言，而非私有 helper 或最多 80 次循环：reservation 后一次 wake 必须直达 proposal waiting，proposal delivery 后一次 wake 必须直达 selection waiting；两次均须 `burst_step_count>1`、controller revision 不越界且耗时小于 `660s`。该回归没有调用 fresh public network 或真实 Current Codex，只验证本地资格热路径；正式 qualification 和 target 仍须分别通过真实交付，以及 PIT、完整 graph dependency closure、跨周期 continuity 和 monitor 门。

---

## 19. 第八资格并发事故与单写者设计

第八资格没有证明 Current Codex delivery。它在同一 CURRENT_CODEX reservation 下被两个 `advance` 进程交错推进：后发进程先写入材料化失败，先发进程随后完成 proposal material 与 mailbox request，导致 controller failure receipt 描述的前缀不再等于实际磁盘前缀。该 pair 永久失败；不允许以修复后的代码重放或补齐。

修复后的运行拓扑为：

```text
validated exact identity
        │
        ├─ root-components-only precheck
        ▼
external per-qualification process lock
        │
        ├─ full namespace + authority replay
        ├─ material / mailbox / controller / probe mutation
        └─ publish one complete durable successor
        ▼
next contender replays that successor under the same lock
```

锁文件固定在 `.runtime/v32/qualifications/.composition-locks/<qualification-id>.lock`，是 qualification roots 的 sibling，不属于任一 qualification 的 material、mailbox、controller、probe 或 evidence inventory；该父目录沿用已经冻结的 qualifications 忽略边界，不会制造 workspace-freeze 的 untracked drift。锁前禁止深扫运行树，以免与首调用的 write-once 临时发布发生竞态；锁后必须完整深扫和 authority replay。四个 Phase-A 后公开写入口——`advance`、Agent request claim、Agent delivery submit、target authority finalize——都只能通过同一个 guard 到达内部实现。线程、独立进程、不同入口同时竞争时只能串行；等待者进入后必须看到首调用发布完毕的 revision，不能使用等待前快照。

外部编排也增加一条同等重要的约束：命令返回 running session 时，唯一合法动作是轮询该 session；未取得原进程终态前不得再次调用相同写入口。排他锁是最后一道一致性保护，不是允许重复调用、自动重试或并发加速的许可。

第八 pair 的 exact Q0–Q8 digest 加入历史只读白名单，identity 在任何 runtime、authority、网络、Agent 或 target 访问之前即 tombstone。后续新第九 pair 仍须按 commit-first → fixed post-commit receipts → Phase-A → single PUBLIC_SOURCE → single CURRENT_CODEX → fixed monitor → target authority 的原顺序运行，且每次只跨一个可审计状态边界。
