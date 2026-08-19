# V2.1—V3—当前系统—V3.1 全面能力与设计审查

- 日期：2026-08-06
- 工作区：`/Users/wt/Documents/agent-trade-emotion`
- 分支：`codex/s0-research-foundation`
- 基线 HEAD：`e400b64b8a986ceeb3312e4dd7e6749dc4239268`
- 需求记录：`requirements/2026-07-30-theory-paper-practice.md` §三十三
- 冻结记录：`V3_1_REDESIGN_BASELINE_FREEZE_2026-08-06.md`
- V3.1 冻结理论：`CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md`，SHA-256=`ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553`
- 外部执行权限：`NONE_LOCAL_SIMULATION / PUBLIC_NON_ACCOUNT_ONLY / NON_EXECUTABLE`
- 审查结论：`V3_1_PARTIALLY_IMPLEMENTED / RUN_FAILED_CLOSED_AFTER_1_OF_8 / OUTCOME_UNRESOLVED / MARKET_VALIDITY_UNKNOWN`

## 1. 结论

V2.1 与 V3 不是相互替代的版本。V2.1 是认识论、点时性、金融边界、动态机制与证据等级的宪法；V3 是连续研究、战略仓位、重入、完整动作、两阶段 Agent 和恢复事务的运行理论。V3.1 必须把二者严格合并，再新增信息、数据、关系图、概率云、开放假说和条件路径，而不能继续在 V3 后追加孤立功能。

历史“合成连续主链”和“公开行情 pilot”确实使用两套不同 schema；它们继续只是历史/legacy 证据。新的 V3.1 冻结子集已经把公开 source qualification/admission、统一 Domain 对象、当前 Codex 两阶段 authoring、确定性 semantic compiler、六阶段 store、checkpoint 和延迟 outcome monitor 组成一个正式 prospective 主链；Cycle 1 已产生真实、不可执行的 accepted state。该事实仍不证明通用目标能力、市场增量或长期稳定性。

因此，当前可以确认：V3.1 已完成 `1/8` 个 accepted cycle，动作=`WAIT`；Cycle 1 唯一 outcome attempt 在合法窗口因 `V31_OUTCOME_PUBLIC_VALUE_INVALID` 永久失败关闭，outcome 未解析，Cycle 2 未启动。失败证明 monitor no-retry/CAS 有效，同时暴露两个 P0 缺口：adapter 成功返回后才保存 raw，失败输入不可审计；research checkpoint 仍为 `READY_FOR_CYCLE`，没有与 monitor terminal 组成统一机械 supervisor gate。不能确认预测、校准、Agent superiority、盈利或跨 regime 泛化。

## 2. 当前状态

**部分完成。**

当前冻结实验范围已完成：

- 新需求、验收和非目标已进入主需求记录；
- 旧 s3 在 1/4 周期冻结，旧 automations 保持暂停；
- V2.1、V3、历史失败、当前模块、运行调用链与能力缺口完成对照；
- V3.1 理论及四层目标设计完成并获用户冻结批准；
- 权威原始论文已映射到设计并标明不可外推边界；
- V3.1 信息、数据、累计修订登记、图、Pearson 关联基线、概率边界、假说/预期、单步路径、有限动作和金融复算合同已形成实现子集；
- inputs→Agent proposal→evaluation→selection→accepted→completion 的本地固定输入应用链已实现；
- synthetic/native snapshot 可映射到同一信息与数据 Domain 合同，旧窄 schema 已标为 legacy；
- 六阶段 write-once chronology、显式状态摘要头、CAS、物理 failure-close 与内容寻址 typed assembly bundle 已实现；全新解释器可以只凭 durable bundle 做语义重放；
- 旧十轴到 V3.1 十二轴的显式迁移、两项缺失轴固定 UNKNOWN、逐 contributor 的 PIT exact binding、prior-state change 和 inputs→completion/checkpoint 状态头已实现；
- 已复现的摘要重签、循环证据、revision 复活、伪校准、错图边、错动作支持、错 Agent 绑定和 checkpoint 越权已有回归。
- Q0–Q8 typed receipts、公开 Q6 source 和当前 Codex Q7 两阶段交付已完成物理/语义重放；
- 唯一 authority、run genesis、Cycle 1 accepted state、monitor attempt 与 failure receipt 已耐久写入；heartbeat 在终局后暂停。

通用目标能力或实验结果尚未完成：

- 十二轴原生外部来源覆盖和显式情绪 graph-state projection；
- portfolio mutation、lot/role、geometry 与 reentry 状态进入同一 reducer/store；本实验明确 `EXCLUDED_NO_CLAIM`；
- 当前只有 Pearson 基线；DCC、Granger、tail/spillover/change-point、结构因果与一般 credal set 仍未实现；
- Cycles 2–8 未启动；Cycle 1 outcome 因适配器失败保持 `UNRESOLVED`，本 run 无合法恢复路径；
- 任何真实预测、校准、Agent superiority、行为增量、收益或跨 regime 结论；其中数值校准和盈利不是本 run 的验收端点。

## 3. 版本权威和冻结边界

| 对象 | 当前角色 | 能做什么 | 不能做什么 |
|---|---|---|---|
| `CORE_TRADING_THEORY_v2_1.md` | 冻结理论基础/前身 | 提供认识论、D/L/C/F/R/K、动态路径和证据边界 | 单独授权新实验或证明盈利 |
| `CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md` | 运行理论输入 | 提供连续状态、仓位、重入、动作和恢复设计 | 冒充已批准权威 |
| `CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md` | 本实验的 `FROZEN_APPROVED` 理论 | 约束唯一 V3.1 manifest 和不可执行研究 | 证明完整实现、预测或交易许可；文件名保留 `DRAFT_FOR_REVIEW` 仅因批准后字节不可改写 |
| s3 run | 冻结基线 | 提供 Cycle 1 的不可变过程证据 | 恢复 Cycle 2–4、改写失败或复用 chronology |
| V3.1 current authority | `ACTIVE_FROZEN_RESEARCH`，只绑定 `v31-prospective-btcusdt-20260806t183742z` | 允许该 run 在冻结边界内继续 | 允许其他 run、账户、paper/live、订单、凭据、资金或规则变更 |

本审查不再使用无边界的“已解决全部已知问题”。可以声称的只有：列明且已复现的问题是否已有对应修复和回归。尚未实现的目标、真实数据语义、未来市场、外部来源、Agent 增量和未知缺陷都不能被本地 PASS 关闭。

## 4. V2.1、V3、当前实现和 V3.1 的能力矩阵

| 能力 | V2.1 | V3 | 当前实现 | V3.1 裁决 |
|---|---|---|---|---|
| 点时事实、来源、lineage | 完整 | 继承 | 已实现，native 有 PIT/raw SHA | 保留并扩展事件修订、actor、audience、regime |
| FACT→ACTION 认识论 | 完整 | 继承 | 合成链完整，native 缩水 | 统一 typed contract，禁止跳级 |
| D/L/C/F/R/K | 完整 | 继承 | 已实现，部分数据 UNKNOWN | 作为状态/机制坐标，不作为投票器 |
| 多周期职责 | 完整 | 明确战略/战术/执行 | 有实现，历史曾误用简单加法 | 使用关系型 coherence，禁止票数相加 |
| 信息主体/受众/传播 | 仅 K 上下文 | 四维事件叙事 | V3.1 多轴本体、修订和来源证据边界已实现 | 角色时变、推测与事实分离；真实来源覆盖待实验 |
| 数据本体与修订 | 部分 | 部分 | 严格 PIT、谱系、质量、缺失、vintage、revision 已实现 | 重签语义不能绕过；真实覆盖待实验 |
| 动态假说 | 动态 primitive/path | fixed starter family + persistent belief | 开放 registry、delta、active budget、split/merge/restore 已实现 | Agent 可提新方向，reducer 独占状态 |
| 预期账本 | 有原则 | persistent expectation | append-only ledger、result evidence、expiry/terminal 门已实现 | 到期 OPEN 失败关闭 |
| 图结构 | 偏序路径/依赖 | 无完整统一图 | append-only typed multigraph 与 delta 已实现 | 只允许相邻认识论层正向可达 |
| 相关性与变化 | 只规定相关非因果 | 未新增 | 仅 Pearson/Fisher 与可比不重叠窗口变化可复算；多类 association 是合同类型而非多类估计器 | 当前不证明预注册、稳定关系、动态相关或因果 |
| 概率 | 严格限制 E0 | 序数 lead/runner-up/OTHER | 四模式容器/边界和 update/repartition 绑定已实现；校准只限常数分类本地重放 | 一般 credal、任意更新复算、mode promotion 与真实校准未实现 |
| 市场趋势/路径 | 偏序、falsifier、expiry | 路径卡 | typed predicate、三值求值、falsifier/expiry/action implication 已实现 | FALSE/UNKNOWN 不能支撑非 WAIT |
| 情绪 | 边界分散 | 四维 | 十→十二轴显式迁移、PIT exact contributor、change 和六阶段/checkpoint 头已接入；两项无数据轴固定 UNKNOWN | 必须保留冲突/UNKNOWN、无总分；原生来源与 graph projection 未实现 |
| 行为规划 | 动作/权限分离 | 八动作、尺度、WAIT | 完整合法动作生成、金融重算、WAIT/selection 合同已实现 | 无 payoff matrix 时 EV/regret 数值 UNKNOWN |
| Agent 开放性 | 候选研究 | 单 Agent 两阶段 | exact inputs/proposal/candidate bindings 已接统一链 | Agent 提议语义；不拥有事实/数值/选择前状态 |
| 恢复和失败原子性 | 原则 | completion/checkpoint | 六对象 chronology、状态头、CAS、failure document、内容寻址 bundle 与全新解释器重放已实现 | 旧 1.0 checkpoint 无 bundle 绑定时失败关闭；外部 transport 仍需另验 |
| 真实预测/盈利 | 未证明 | 未证明 | 未证明 | 只由未来预注册实验逐层检验 |

## 5. 当前真实四层模块地图

### 5.1 Presentation

- V3.1 正式 composition：`v31_authority_freeze_composition.py`、`v31_source_qualification_composition.py`、`v31_formal_cycle_composition.py`、`v31_agent_transport_worker.py`；
- 连续合成：`single_agent_research_cli.py`、`continuous_fixture_composition.py`、`continuous_cycle_report.py`；
- 当前 Agent transport：`native_cycle_experiment_cli.py`；
- 当前公开行情：`native_market_pilot_cli.py`；
- 旧实验入口：`presentation/cli.py`、`formal_cli.py`、`action_discrimination_cli.py` 等。

边界事实：旧 CLI/pilot 不代表 V3.1 主链。current authority 只允许精确 authorized run 和冻结 operations；其他 run ID、权限扩张或旧模板启动在来源访问前失败关闭。

### 5.2 Application

- V3.1 主链：`application/v31_authority_freeze.py`、`application/v31_cycle_source_admission.py`、`application/v31_agent_transport.py`、`application/v31_cycle_authoring.py`、`application/v31_formal_cycle.py`、`application/v31_research_cycle.py`、`application/v31_durable_cycle.py`、`application/v31_monitor_runtime.py`；
- V3.1 Agent 合同：exact inputs receipt、proposal、complete evaluation、post-seal selection；
- 新连续主链：`application/continuous_cycle.py`、`application/continuous_fixture.py`；
- 当前市场：`application/native_market_pilot.py`；
- transport：`application/native_agent_transport.py`；
- 权限：`application/research_authority.py`；
- ports：`application/ports.py`；
- 旧大应用：`single_agent_research.py`、`prospective_single_agent.py`。

V3.1 ports 已包含 `V31ResearchStorePort`、source、Agent transport、monitor 和 public observation 边界。同一 research store 持有六阶段正式文档、信息/数据累计修订登记册、accepted/checkpoint 状态头和内容寻址 typed assembly bundle；Application 可从 bundle 重建 dataset、graph、cloud、scenario、action evaluation 和六阶段对象。fresh source 与当前 Codex durable delivery 已在 Cycle 1 composition 中绑定；广覆盖新闻/宏观来源仍不在本次能力声明中。

### 5.3 Domain

- V3.1 信息与来源：`domain/information_model.py`；
- V3.1 数据：`domain/data_model.py`；
- V3.1 关联/估计：`domain/association_model.py`、`domain/association_estimation.py`；
- V3.1 图：`domain/market_knowledge_graph.py`；
- V3.1 概率：`domain/probability_cloud.py`；
- V3.1 路径：`domain/scenario_path.py`；
- V3.1 行为/金融：`domain/behavior_planning.py`、`domain/financial_evaluation.py`；
- V3.1 Agent 边界：`domain/agent_research_contract.py`；
- 动态研究：`domain/dynamic_research.py`；
- 公开推论：`domain/epistemic_inference.py`；
- 路径与完整性：`domain/research_integrity.py`；
- 仓位真值：`domain/portfolio_truth.py`；
- 跨窗口恢复：`domain/window_reliability.py`；
- 当前窄市场 schema：`domain/native_market_cycle.py`；
- 其他：`hypothesis/`、`deliberation/`、`evaluation/`、`policy/`、`position/`、`reentry/`、`strategic/`、`geometry/`。

### 5.4 Infrastructure

- V3.1 统一 snapshot adapter：`infrastructure/v31_market_adapter.py`；
- V3.1 chronology/store/compiler/monitor：`infrastructure/v31_research_store.py`、`v31_agent_transport_store.py`、`v31_semantic_compiler.py`、`v31_monitor_store.py`、`v31_public_outcome_adapter.py`、`authority/v31_current_research.py`；
- 数据：`infrastructure/native_market_collector.py`、`fresh_market/`；
- 写入：`research_cycle_store.py`、`native_market_pilot_store.py`、`native_agent_mailbox.py`、`event_store/`、`content_store/`；
- transport adapters：`agent_adapter/`、`generative_topology/codex_exec.py`、`codex_app_server.py`；
- legacy：`legacy_v1/`、旧实验 stores。

## 6. 当前真实调用链

### 6.1 完整但合成的连续研究链

```text
single_agent_research_cli
→ continuous_fixture_composition
→ run_four_cycle_synthetic_fixture
→ snapshot / sentiment / hypothesis / expectation / public inference
→ path belief reducer
→ complete legal-action evaluation
→ Agent proposal + sealed evaluation + selection
→ deterministic risk / preaccept / accepted state
→ evidence receipt / report / review / checkpoint
```

此链验证了较完整的本地契约，但 snapshot 和 Agent 都是 synthetic；不能证明真实数据或真实 Agent 增量。

### 6.2 当前公开行情 pilot

```text
native_market_pilot_cli
→ OKX public collector
→ raw artifacts + PIT snapshot
→ proposal request / Codex claim / durable delivery
→ current-cycle grounding
→ deterministic sentiment + three-action shadow finance
→ deliberation request / selection
→ preaccept / accepted / report / checkpoint
```

实际接入：OKX time、instrument、ticker、mark、闭合 15m/1h/4h/1d K 线，可选 OI、funding、book、recent trades。

仍为 UNKNOWN：positioning、liquidation、news/event、cross-market/macro。无账户、订单、凭据或执行。

### 6.3 Native transport

当前 transport 是异步文件邮箱：request→claim→delivery→seal→consume；checkpoint 使用 compare-and-swap。它能防止聊天成为状态权威，但不机器证明服务模型与精确 token 预算，也不是自动 Agent API。

### 6.4 V3.1 统一本地主链

```text
source-bound InformationEvent + strict PIT dataset + prior state heads
→ exact inputs receipt
→ current Codex/Strategy-Agent proposal (no selection)
→ graph delta + registry/ledger replay + probability transition
→ three-valued scenario evaluation + complete financial action evaluation
→ preselection seal
→ independent selection
→ accepted state + completion receipt
→ six write-once events + checkpoint state heads
```

该链除 synthetic 固定输入验证外，已经在唯一正式 run 的 Cycle 1 组成 prospective 端到端证据：active authority → fresh public source qualification/admission → open Agent authoring → deterministic semantic compile → sealed evaluation → post-seal selection → accepted/completion → absolute public mark monitor。typed assembly bundle 在正式文档前内容寻址落盘；恢复仍只能依赖绑定 bundle/checkpoint，不能依赖聊天或六份摘要文档。

## 7. 已发现结构失配、修复与剩余边界

### 局部关闭 P0-1：合成与公开 snapshot 的语义分叉

V3.1 adapter 将 synthetic/native snapshot 映射为同一 `InformationEvent` 与 `PointInTimeDatum`；独立 snapshot 使用内容寻址 genesis ID，不再用固定 revision 1 暗示跨周期修订。旧 `native_market_cycle` 仍是历史 pilot 的真实依赖，current authority 阻止其创建新 run；正式 Cycle 1 已证明冻结 V3.1 composition 的单一路径，不追溯改写旧 pilot。

### 已关闭 P0-2：认识论与图链分叉

统一链强制 `INFORMATION→FACT→MEASURE→STATE/ASSOCIATION→HYPOTHESIS→EXPECTATION→PATH→ACTION` 相邻层级；循环、跨层跳跃、反向边和 `OPPOSES` 正向可达均失败关闭。假说、预期和概率只能引用当前准入证据；superseded revision 仅供审计。

### 已关闭 P0-3：动作与金融语义分叉

V3.1 从实际 portfolio truth 生成完整合法动作域，并从原子价格、数量、费用、滑点、保证金、保护位和风险 policy 重算每个候选。未校准模式禁止 EV；没有冻结 payoff matrix 时数值 regret 也保持 UNKNOWN。

### 局部关闭 P0-4：信息、数据、图、概率和路径核心缺失

对应 Domain 合同、application coordinator、adapter 和 durable store 的实现子集已落地。通用未来设计中，任何 calibrated forecast 都必须由冻结且不重叠的开发/校准/OOS 事件、评分重算、漂移与 deployment vector 解锁；当前 frozen experiment 明确排除 `CALIBRATED_PROBABILITY` 与 `BRIER_LOG_ECE`，只使用 `SUBJECTIVE_PLAUSIBILITY` 的序数 lead/runner-up/OTHER/UNKNOWN。一般线性约束 credal set、高级估计、十二轴广覆盖原生来源/图投影和偏序/循环路径执行器尚未落地。

### 已关闭 P1-1：来源自认证

官方类型、自哈希或 `VERIFIED_PRIMARY` 标签不再解锁可信度。本地输入降为 `UNVERIFIED/PARTIAL`；公开 transport capture 逐项通过请求、响应、raw、时间和事实绑定后，也只达到 `SOURCE_ATTESTED/VERIFIED_SECONDARY`，不声称内容为真或独立外部验证。

### 已关闭 P1-2：本地耐久状态与语义恢复含糊

preselection、accepted、completion 与 checkpoint 明确绑定数据、情绪、图、假说、预期、概率云及概率迁移状态摘要头。严格白名单 typed assembly bundle 在六个正式对象之前内容寻址落盘；当前 formal checkpoint schema=`1.2.0` 另绑定 approval、manifest、authorization、active authority、genesis 与 accepted/completion heads。全新解释器可只从 run store 读取 bundle、重建 typed input 和六对象并重新注册 semantic admission。缺失、多个候选、内容改后重签、schema/signature drift 或 executable 输入均失败关闭。

### 已关闭 P0-5：六文档互相重签可伪造终局

旧实现只验证六份文档的摘要和跨阶段引用，攻击者可把 `candidate:WAIT` 的 `selected_action` 改为 `OPEN_LONG`，同步重签 accepted/completion 后推进 TERMINAL。当前 coordinator 会从 durable typed bundle 的原始 action evaluation 完整重建 preselection、selection、accepted 与 completion；store 在没有应用层语义准入时拒绝 checkpoint advance，并额外核对 selected action 与候选动作。该修复证明本地信任边界，不证明外部语义或市场有效性。

### 已关闭 P1-3：跨周期 ID 消失后重生

信息事件和数据对象现在各有累计修订登记册，保留所有已知 ID 的 latest revision。对象即使不在某一轮当前推论快照中，也不能随后以 `revision=1 / predecessor=None` 重新出现。当前 schema 已把登记册摘要绑定到 inputs、preselection、accepted/completion 与 checkpoint，并有跨周期消失—复活拒绝回归。

### 冻结排除边界 R0：情绪图投影与连续组合未进入同一 reducer

V3.1 新 cycle 已把显式十二轴情绪 state/change 接入 accepted/completion/checkpoint，并禁止情绪绕过 PIT 数据门；但还没有十二轴广覆盖原生信息或显式 sentiment graph-state node。portfolio mutation、geometry 与 reentry 也尚未进入同一 accepted reducer。当前 manifest 已将这些能力标为 `EXCLUDED_NO_CLAIM`，因此不是启动阻塞，也不能由本 run 形成相应结论。

### 已关闭 R0B：本地可移植语义恢复

formal checkpoint 1.2.0 累计保存每周期 assembly bundle、authority/genesis 和 accepted/completion heads。独立新解释器仅接收 durable run root、run ID 与 cycle index，即可重建 dataset、graph、cloud、scenario、action evaluation 和六正式对象；物理篡改、重签替换、缺失或目录歧义均失败关闭。该结论不等于 Codex、网络或 automation 长时可靠。

### 已关闭的窄资格边界 R1：正式公开 source/Agent transport

Q6 已以一次 fresh 公开 OKX 采集完成 raw/PIT/UNKNOWN 耐久重放，Q7 已以第三个独立 qualification root 完成当前 Codex 的 open-analysis→deterministic compile→post-seal selection。前两个 Q7 roots 分别因 stdin EOF 和 canonical PTY 行缓冲限制永久失败关闭并保留。该门只证明一次可重放窄链；官方全文/新闻/宏观覆盖和长期 Agent/网络可用性仍未证明。

### 剩余证据边界 R2：市场有效性

Cycle 1 monitor=`ACTIVE`，`outcome_not_before=2026-08-06T19:52:52.950875Z`、`expires_at=2026-08-06T20:07:52.950875Z`；截至本快照尚无 V3.1 future outcome，禁止提前读取。真实假说区分力和路径解析仍是 `UNKNOWN_NOT_EVALUATED`；数值概率校准、Agent superiority、盈利、组合绩效与跨 regime 泛化是当前 frozen contract 的排除项，不得伪装成待通过的本轮端点。

## 8. 历史失败与 V3.1 防线

| 失败 | 根因 | V3.1 强制防线 |
|---|---|---|
| V1 target 后永久离场 | 无状态、全平、无重入 | episode/exposure 分离，target 仅管理事件，reentry obligation |
| E0/E0B 集群失败 | transport/context 成为主问题，动作无增量 | 单 Strategy Agent；transport 仅适配器；不恢复集群 |
| 全 WAIT | 未比较完整动作和机会成本 | 完整合法动作域；WAIT 有 cost/observation/review |
| active 仍落后 hold | 成本、重入延迟、path capture 不足 | hold/flat 基准与成本/回撤/reentry 并列评价 |
| 伪概率 | 非互斥路径归一、无 OTHER/校准、重复证据 | typed probability cloud；默认不归一；dependency de-dup |
| 时间/代理误用 | 窗口不一、funding 时钟错、新闻只有标题 | 统一时钟/vintage/proxy/coverage/正文合同 |
| Cycle 17 旧 lot | accept 后才检查语义 | current-cycle grounding 与 preaccept semantic receipt |
| selected-first | 先选后解释 | proposal 禁 selected，evaluation sealed 后 selection |
| belief 任意覆写 | Agent 拥有 reducer 状态 | Agent 只提议，deterministic reducer 独占状态 |
| 新窗口丢状态 | 聊天/全量上下文/无 durable delivery | capsule、input plan、mailbox、CAS、分阶段恢复 |
| automation 删除失联 | desired 冒充 actual | desired/actual/lease/kill switch/reconciliation 分离 |
| 情绪 pilot 连续失败 | 低量=卖压、OI 无 lineage、周期加法、sign 无事实 | 关系型 coherence、contributor→fact、UNKNOWN 和失败关闭 |

### 8.1 本轮实现审查暴露并关闭的问题

| 问题情况 | 失败方式 | 当前解决方案 |
|---|---|---|
| 数据文档只验摘要 | 修改 enum/revision/准入计数后重签 | 从严格字段重建 typed datum/dataset，并重算推论准入与 quarantine |
| 数据质量越权 | 描述/候选假说级数据进入概率、关联、路径或动作 | `hypothesis_admissible` 与 `inference_admissible` 分离；后四者只接收强准入数据 |
| 集合摘要洗白 | dataset/event digest 掩盖低质量 datum、心理假说或上下文 | 聚合摘要只绑定输入边界；语义目录只接收 typed member 的 exact ref→digest |
| 信息认识论混层 | actor/role/audience/intent/behavior 与 observed fact 共用概率白名单 | observed evidence、hypothesis seed、context 分目录；intent/behavior 只允许候选假说或 subjective mode |
| 来源质量自认证 | `VERIFIED_PRIMARY`+自哈希伪装来源 | acquisition receipt、四级 evidence boundary、native 默认降权 |
| 假说证据可漂移 | 未准入或旧 revision 仍可引用 | current admitted catalog + latest revision only + inherited prior refs 显式分离 |
| 概率云循环 | 云/假说/动作引用自身作为前置证据 | 只接受当前信息/事实/度量和低层关联；后层、自身与循环 ref 拒绝 |
| 校准 receipt 自报 | 占位摘要或调用者填写 score 解锁 EV | 冻结原始 forecast/outcome、分割、评分、ECE、基准、漂移和部署向量全部重算 |
| cloud 状态跳变 | 跨周期静默替换成员/概率 | update/repartition replay receipt + previous/current cloud head |
| 路径—动作错绑 | FALSE/UNKNOWN 路径仍有 SUPPORTS，或 OPPOSES 被当正向 | 三值实际求值、exact action implication、正向边兼容矩阵与 selectable gate |
| Agent 摘要自授权 | 任意 proposal digest 或错候选绑定进入 selection | exact inputs receipt、proposal schema、candidate-only digest、selection after seal |
| 金融字段可伪造 | 调用者提交 cost/risk/EV | 原子输入重算费用、保证金、风险和可行性；无 payoff matrix 不算 EV/regret |
| store 接受语义伪造链或新窗口丢失构造状态 | 六对象可互相重签，WAIT 可被改写成 OPEN_LONG；内存 input 不可恢复 | 六事件固定 schema + durable typed bundle 全链重放 + action exact match；无语义准入不得 advance |
| checkpoint 内部漂移 | 只绑定 accepted 总摘要 | 显式状态头逐项匹配前一 accepted；非 advance 禁止改头；新增信息/数据累计修订头 |
| 失败后伪恢复 | `resume_allowed` 与状态不一致 | 物理 failure document、严格 transition matrix、FAILED_CLOSED 永久终止 |
| 到期预期仍开放 | deadline 已过但继续支撑路径 | 到期 OPEN 强制拒绝，必须提交 CLOSE/EXPIRE delta |
| validity/PIT 混淆 | 晚到记录描述过去被误判未来 | `valid_from` 描述适用期，`available_at` 独占知识时钟 |
| 信息/数据 ID 复活 | ID 消失一轮后以 revision 1 重生 | 累计 revision registry 保留全部已知 ID 的 latest head，inputs/accepted/checkpoint 跨轮绑定 |
| inherited evidence 漂移 | 旧假说只继承 evidence ID，忽略同 ID 新 revision 降级 | active/result evidence 使用 exact ref→digest，每轮对 latest registry head 与准入重核 |
| legacy fixture 未同步 exact binding | 新 Domain 合同要求假说、delta、预期结果逐条绑定证据摘要，但旧 adapter 仍只提交 ID，导致全量回归 18 项同源中断 | Infrastructure 以当轮 `canonical_digest(snapshot_fact)` 补齐绑定，revision 合并旧/新绑定；未放宽 Domain、未填伪摘要、未回填旧 run；修复后相关 24 项及全范围 426 项通过 |
| 情绪形成第二数据通道 | 独立 snapshot/contributor 未绑定 V3.1 PIT dataset 也能进入 Agent | 先验证 PIT、后重放情绪；每个 contributor 精确绑定当前 inference-admissible datum 并逐字段复核；跨轴可共享、轴内 dependency 去重 |
| 假说/预期循环谱系 | self-parent 或 A↔B 形成伪 lineage | parent 必须在 delta 前存在；self-parent 与任意拓扑环失败关闭 |
| cloud repartition 时间回退 | 换成员时 `available_at` 可早于 prior | repartition 与普通 update 同样禁止可得时间回退 |
| 关联数字自报 | Pearson receipt 内嵌任意数字与任意 64 位摘要 | 每个 paired observation 必须绑定当前准入 PIT numeric datum、值、as_of 与可得时间 |
| Q7 stdin/PTY 交付失败 | EOF 或 canonical 行缓冲使 payload 未完整交付 | 两个原 root 永久失败关闭；第三个独立 root 使用 non-canonical/no-echo byte transport 与阶段隔离 worker，不改写失败历史 |
| 冻结 helper 权限字符串误报 | presentation 深扫描把 typed AST 内合法 `NONE_LOCAL_SIMULATION` 当 legacy authority | 完整 loader 仍先验证 Q0–Q8、外部物理证据和 74 个 frozen runtime；Application 只接收其中五份已验证语义文档。活动 run 不改冻结字节，代码修复留待 successor authority |

## 9. V3.1 当前四层实现

### Domain

当前模块：

- `information_model.py`：Actor/Role/Audience/Event/Transmission；
- `market_knowledge_graph.py`：typed nodes/edges/deltas/revisions；
- `association_model.py`：association types、estimate contracts、regime/time windows；
- `probability_cloud.py`：模式、包络、识别区间、market implied 与 calibrated objects；当前 frozen run 只使用序数 subjective cloud，calibrated objects 未启用；
- `scenario_path.py`：predicate/guard/transition/falsifier/expiry；
- 复用并扩展 `dynamic_research.py`、`epistemic_inference.py` 和 portfolio/risk 模块。

Domain 不读文件、不联网、不调用模型。

### Application

当前 V3.1 cycle coordinator 编排：

```text
active authority → fresh source qualification/admission → input plan
→ open Agent proposal → deterministic semantic compilation/evaluation
→ post-seal Agent selection → reducers/risk
→ six receipts → accepted/completion → checkpoint
→ delayed absolute OKX public-mark monitor
```

Application 只依赖 ports 与 Domain，不导入具体 OKX、文件系统或 Codex adapter。

### Infrastructure

- OKX/public data adapter；
- information/artifact adapters；
- append-only graph/cycle store；
- Codex mailbox adapter；
- deterministic estimator adapters（若使用外部统计库）。

合成 fixture 和公开行情只在适配器上不同，不能拥有两套 hypothesis、inference、path 或 action schema。

### Presentation

- `status`：证据等级、authority、checkpoint、真实缺失；
- `init/advance`：仅在当前授权和 manifest 下；
- `claim/submit`：durable delivery；
- `report`：只渲染 receipt 绑定事实；
- 不直接修改 Domain 状态。

## 10. 目标核心合同

### 10.1 信息事件

```text
InformationEvent(
  actor_roles, authority_scope, observable_message_or_action,
  channel, audiences, novelty, commitment, reversibility,
  published_at, available_at, effective_at, revised_at,
  source_artifact, quality, competing_intent_hypotheses
)
```

`inferred_intent` 只能是 hypothesis ref，不能成为 observed field。

### 10.2 图边

```text
GraphEdge(
  edge_type, source, target, valid_from, valid_until,
  evidence_refs, dependency_group, regime,
  strength_or_band, uncertainty, stability,
  epistemic_status, limitations, revision_reason
)
```

`ASSOCIATED_WITH / PREDICTIVE_LEAD / MECHANISM_HYPOTHESIS / IDENTIFIED_CAUSAL_EFFECT` 永不互相冒充。

### 10.3 概率云

三层证据、四种对象：

1. `SUBJECTIVE_PLAUSIBILITY`：序数/宽包络，不归一、不进 EV；
2. `EMPIRICAL_OR_MODEL_CONDITIONAL`：有样本/模型/识别区间，保存敏感性；
3. `MARKET_IMPLIED_BELIEF`：保存流动性、风险溢价和合约假设；
4. `CALIBRATED_PREDICTIVE_DISTRIBUTION`：互斥完备标签、OTHER、独立校准、proper scoring 后才允许。

### 10.4 条件路径

```text
IF observations
AND quality/regime/portfolio guards
UNLESS counter-evidence or veto
THEN one typed epistemic transition
BECAUSE mechanism
EXPECT observables by horizon
ELSE preserve competitors/OTHER
FALSIFY when ...
EXPIRE when ...
ACTION implication only
NEXT REVIEW ...
```

## 11. 学术基础的设计用途

- 信息成本与部分价格发现：Grossman–Stiglitz、Kyle、Glosten–Milgrom；
- 政策动作/路径/信息冲击分解：Gürkaynak–Sack–Swanson、Nakamura–Steinsson、Jarociński–Karadi；
- 受众协调、说服与来源激励：Morris–Shin、Kamenica–Gentzkow、Gentzkow–Shapiro；
- 中介资本和流动性反馈：Brunnermeier–Pedersen、He–Krishnamurthy；
- 注意力、叙事与异质受众：Tetlock、Da–Engelberg–Gao、Hong–Stein；
- 动态网络与关系：Engle DCC、Hamilton regime、Diebold–Yilmaz、Acemoglu 等；
- 模型不确定性和稳健决策：Hoeting 等、Gneiting–Raftery、Giacomini–White、Manski；
- 币市特有分割和网络/注意力：Makarov–Schoar、Liu–Tsyvinski。

完整链接、吸收内容和不可外推边界见 V3.1 理论文档 §19。文献支持可检验机制，不支持把人物身份、发言、相关性或文本直接变成精确交易概率。

## 12. 三阶段实施路线与门

### Phase A：统一 Domain 合同

状态：**部分完成。** 当前注册类型、严格数据、十二轴情绪迁移/PIT 绑定、图、概率边界、生命周期、单步路径、有限动作与金融复算已有实现；十二轴原生来源/图投影、高级关联/因果、一般 credal set、偏序/循环路径和连续组合状态仍属于目标而非当前能力。

交付：信息本体、关系/图、概率云、场景路径；复用假说/推论/reducer。

门：

- 所有对象类型和时钟可验证；
- 读心、因果升级、伪概率、重复证据失败关闭；
- 不改旧实验 artifact。

### Phase B：统一 Application 与 adapters

状态：**冻结实验子集已接通，通用目标仍部分完成。** V3.1 snapshot 映射、十二轴情绪 accepted state、完整研究动作 evaluation、fresh source/Agent composition、durable chronology、跨进程 bundle 重建和 public outcome monitor 已接通；情绪 graph projection 及 portfolio/reentry accepted reducer 未接通且在当前 manifest 中排除。旧链仅标记 legacy，并未物理删除。

交付：单 V3.1 coordinator；synthetic 与 public market 共用同一 Domain schema；完整动作域；durable receipts。

门：

- Application 不导入 Infrastructure；
- proposal→evaluation→selection 顺序固定；
- accepted 后只恢复 deterministic tail；
- authority 仅允许 exact authorized run；其他 start 或权限扩张统一拒绝。

### Phase C：新实验资格

状态：**`QUALIFIED_AND_STARTED / 1_OF_8 / MONITOR_FAILED_CLOSED / NO_RETRY`。** 理论、Q0–Q8、manifest、authorization、fresh source/Agent 和 Cycle 1 accepted state 保持有效；唯一 outcome attempt 失败且未产生 outcome，Cycle 2–8 不得启动。

交付：固定 fixture、恢复测试、PIT/权限/失败原子性测试；唯一 fresh run manifest。

门：

- 本地合同测试通过；
- 新鲜 transport dry run 成功；
- 输入、期限、动作、评分、停止条件预注册；
- 用户明确授权新 run；
- 无账户、订单、paper/live 和 future outcome 权限。

## 13. 验收判断

V3.1 文档阶段的完成标准：

- 理论不再依赖固定假说槽位、单一情绪分、伪概率或直接信息→动作；
- 信息、数据、关系、概率、假说、路径和行为均有正式类型与越界禁令；
- V2.1 与 V3 的有效部分均可追溯；
- 当前实现能力与缺失不混写；
- 所有历史已知失败均映射到明确防线；
- 目标系统只有一条四层主链和一组统一 Domain 语义。

系统通用目标仍只达到一个冻结子集，且首个正式 run 已终止。当前唯一合法路径是保留原始失败，离线重构 outcome 为“HTTP capture/raw 先耐久化，解析后置”，并预注册 provider/local 时钟偏差、UNKNOWN 与无响应收据；完成测试和新 authority 后，再由用户决定是否授权唯一 successor。不得重试本 run、补造 outcome、推进 Cycle 2，或把 `1/8 + WAIT` 写成预测有效、盈利或生产就绪。
