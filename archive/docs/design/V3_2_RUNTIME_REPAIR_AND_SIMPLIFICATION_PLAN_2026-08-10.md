# V3.2 运行时修复、简化与实验恢复计划

状态：DESIGN_FROZEN / POSTCOMMIT_FIXTURE_DRIFT_CLOSED / EXPERIMENT_PAUSED_AWAITING_NEW_COMMIT_AND_GATE

日期：2026-08-10

需求入口：requirements/2026-07-30-theory-paper-practice.md

理论基线：CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md

当前代码基线：commit 9f5dba41fefd3759810af305b23865998110552a

权限边界：PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION / executable=false。本文不授权 paper/live、账户、订单、凭据、资金或任何真实交易动作。

---

## 1. 结论

当前最优路线不是继续扩写理论，也不是一次性重写整个系统，而是先做一个可被独立验证的“窄旁路切片”：把 source 截止、分析决策、outcome 时间与过期终态收回到 Domain/Application；复用现有 raw-first OKX collector、write-once store、mailbox 和安全边界。Presentation 只负责输入输出，Infrastructure 只负责外部访问与持久化。

正式实验暂不能启动。现有 target 主链包含三个确定会在真实时钟下失败的 P0，测试夹具使用整刻预制时间掩盖了它们。另有一个 P1 会把缺失的人工/修订输入静默变为空列表。只有这些缺陷、本地真实组合测试、一次现有正式双 suite 门和 fresh qualification 全部完成后，才可创建唯一 target run。

V3.2 理论基线在第一份正式实验结果前保持冻结，既有 opposition/配对合同不变。Agent 继续拥有开放假说和动态行动规划权；硬内核只保护事实时间、权限、耐久一致性和研究风险上限，不能因一般不确定性自动把所有路线压成 WAIT。

---

## 2. 用户目标与工程裁决

| 用户目标 | 本计划的工程裁决 |
|---|---|
| 跑得更快、更猛，但保留必要安全 | 放宽研究语义和 Agent 路线；不放宽未来数据、重复写入、越权和风险上限 |
| 避免资格阶段反复暴露本地缺陷 | 在资格前增加真实组合测试和一次非授权 transport smoke；资格不再当 debugger |
| 局部更新不再牵动全系统 | 本轮不拆巨石，只增加一个 source 边界和纯时间规则；按影响分层测试，后续再依据 Cycle 1 证据缩小 closure |
| 外部访问失败时减少无效尝试 | 相同路径只试一次；两种合法路径失败即停止，转人工、替代官方源或明确 UNKNOWN |
| 缺数据时由用户协助 | 先完成 importer 和 revision reader，再给用户明确文件、来源、时间字段和导入验收；不提前让用户收集无法接入的数据 |
| 理论先宽松验证，后按结果调整 | 冻结 V3.2；校准、成本后收益和跨 regime 泛化留给实验，不靠代码声明解决 |

### 2.1 当前明确不做

- 不建立通用事件总线、通用插件 SDK、第二套 journal/snapshot 平台。
- 不迁移全部 V3.2 文件，不原地改写旧 run 或旧资格树。
- 不再调整假说理论、支持档、reentry、portfolio 或执行策略。
- 不为当前 public/local/non-executable pilot 伪造交易所“核按钮”或市价必然清仓。
- 不把慢速人工数据替代为 BTC-USDT-SWAP 同时刻快速市场数据。
- 不用 mock PASS、资格收据或 API 可达性声称预测有效、盈利或生产就绪。

---

## 3. 已暴露问题、根因与修复

### P0-1：source 时序在生产环境必然倒置

现状：

1. opening wake 先把操作系统当前时刻冻结为 analysis_decision_at。
2. 后续 wake 才真实采集并封存 source，collector 的 decision_time 必然更晚。
3. admission 又要求 source qualification 的 decision_time 等于更早的 permit decision，并要求 completed_at 不晚于 admitted_at/decision_time。

结果：正常真实采集无法同时满足合同；Cycle 1 在 source admission 前必然失败。整刻夹具预制同一时间掩盖了问题。

修复：

- 新增 PreparedCycleSource 作为一个独立、耐久的 SOURCE_READY 边界。
- collector 完成后产生 formal qualification；其 decision_time 是真实 source knowledge cutoff，且不早于 qualification completed_at。
- source admission 时序合同必须版本化修正：qualification 的 legacy decision_time 只解释为 source_cutoff_at；admitted_at 必须来自 admission 当下的真实系统时钟。删除 qualification decision_time 等于 admission/analysis decision，以及 admitted_at 不晚于 decision_time 的旧约束。
- PreparedCycleSource 保存 source_cutoff_at、admitted_at、prepared_at、qualification_binding、admission_binding、bundle_binding。合法顺序为 qualification.completed_at <= source_cutoff_at <= admitted_at <= prepared_at。
- 下一次边界才开启 ANALYSIS permit；permit_opened_at 必须不早于 prepared_at。Agent selection semantic compile 成功时，以已耐久验证的 selection_compile_receipt.compiled_at 定义 decision_sealed_at，且不得早于 permit_opened_at。
- outcome horizon 从 decision_sealed_at 起算，不从 source cutoff 或 permit opening 起算；否则 Agent 尚未完成时 15m 结果可能已经开始甚至到期。
- outcome schedule 在 selection compile 后、shadow/commit/acceptance 前构造；schedule、commit envelope 和 acceptance 必须逐层绑定同一 decision_sealed_at，不能在 acceptance 后补造。
- 若旧 permit 字段 analysis_decision_at 为兼容必须保留，只允许精确回显 source_cutoff_at，并明确它不是 admitted_at、permit_opened_at 或 decision_sealed_at，不能再用于 outcome schedule。
- collect→qualify→admit→replay 在一个 `SOURCE_READY` 外层边界内作为有界 append-only burst 完成；可从合法 partial prefix 续接，但不得拆成多个五分钟外部 wake。下一次外部边界才打开 ANALYSIS permit。
- freshness 分两处处理：正常路径在 SOURCE_READY 后的下一次唤醒开 permit。若进程长时间中断使已封存 prepared source 在 permit 前过旧，当前 Phase 1 零 Agent、零第二网络失败关闭；不得在固定 per-cycle write-once admission 身份下静默替换 source。selection compile 后若在 decision_sealed_at 已过旧，该 cycle 必须封存 `SOURCE_STALE_AFTER_AGENT / FAILED_CLOSED`，不得重新采源、重跑 Proposal/Selection 或复用已消费的 Agent attempt。任何分支都不得回拨、刷新或改写原对象。只有实际实验表明 pre-permit stale 高频发生时，才单独设计 source-generation successor。

单一 owner：现有 Application prospective router/cycle composition 负责流程；PreparedCycleSource 的纯 verifier 负责合法关系；现有 OKX collector 只提供真实 capture/qualification 时间。

### P0-2：精确 horizon 与 15 分钟格点互相冲突

现状：

- schedule 使用 analysis_decision_at 加 15m/1h/4h，保留秒和微秒。
- outcome attempt 却要求 planned_tick_at 必须落在 00/15/30/45 分且秒和微秒为零。
- router 把精确到期时刻直接交给 attempt builder。

结果：只要决策不恰好发生在整刻，首个 15m outcome 就必然拒绝。

修复裁决：

- 取消 calendar grid 对 planned_tick_at 的要求。
- target_at 等于 decision_sealed_at 加精确 horizon；planned_tick_at 等于 target_at。
- 合法 capture window 为 target_at 至 target_at 加 900 秒。
- scheduler_woke_at 和 capture_at 单独记录，用于测量唤醒延迟；不得修改研究 horizon。

不采用“向上取整到下一根 15m K 线”，因为它会把真实 15m horizon 延后最多 15 分钟并改变实验问题。

单一 owner：Domain.OutcomeTimePolicy；router 只执行其 FUTURE/DUE/EXPIRED 判定。

### P0-3：过宽限期 schedule 永久重选

现状：

- router 只判断 outcome 已到期，不先判断已过期。
- 过期 schedule 进入 attempt builder 后在 permit 写入前抛错。
- 没有耐久 reservation 或 terminal receipt，下一 wake 再选同一 schedule，形成永久循环。

修复：

- OutcomeTimePolicy 必须只返回 FUTURE、DUE、EXPIRED 三态。
- EXPIRED 进入零网络分支，原子写入一次 OutcomeWindowMissed、UNKNOWN_COVERAGE_LOSS 和 schedule terminal。
- 该终态不得伪造 mark、不得 backfill、不得把缺失写成 0。
- reload 后同一 wake 返回已经存在的 exact terminal；零第二写、零网络，并允许 router 处理下一 schedule。
- 只有 authority、schema、binding、chronology、CAS 和 schedule identity 已完整验证，且 now 确实晚于 expires_at，才允许生成 coverage-loss terminal。其他完整性异常继续 fail closed，可写 owning failure receipt，但绝不能伪装成市场数据缺失。

### P1-1：strategy revision 输入被静默丢弃

现状：生产 wake 未注入 revision reader，adapter 默认使用 Empty reader，导致 unknown tracks、人工证据和 recovery trace 被表现为空。

修复：

- StrategyRevisionReader 成为显式必需端口。
- 无输入必须写 NO_REVISION_INPUT/UNKNOWN，并说明“未提供或未接入”，不能写成“已确认不存在”。
- 人工文件只有在 schema、来源、发布时间、received_at、available_at、物理摘要和未来 cycle admission 全部通过后才能进入 Agent packet。

### P1-2：外部 orchestrator 看不到下一合法动作

修复：增加只读 read_status，不推进任何状态，返回：

- run/qualification identity 和 engine version；
- 当前 committed boundary 与 active permit；
- next_legal_action；
- Agent stage 与 request/claim/delivery 状态；
- 每个 outcome 的 target_at、expires_at、FUTURE/DUE/EXPIRED/TERMINAL；
- last terminal/failure 和 retry_allowed；
- external wait 是否只需继续 poll 同一 OS session。

这取代盲目重复 advance；write API 仍保持一次只跨一个外部状态机边界。

---

## 4. 第一阶段实际架构图

本轮不创建新 engine、事件总线、Facade、通用 Service 或 Adapter 层，只在现有主链增加一个 SOURCE_READY 状态和两个纯时间规则。

~~~mermaid
flowchart LR
    U["Codex / 本地调度器"] --> P["现有 Presentation\nrun wake / claim / submit\n新增 read-only status"]
    P --> A["现有 Application\nprospective router\ncycle coordinator"]
    A --> D1["Domain\nPreparedCycleSource contract"]
    A --> D2["Domain\nOutcome exact-time policy"]
    A --> I1["现有 Infrastructure\nraw-first collector + source stores"]
    A --> I2["现有 Infrastructure\nanalysis/outcome lane + mailbox"]
    P --> I3["显式 StrategyRevisionReader"]
    I1 --> O["OKX 公共接口"]
    D1 --> A
    D2 --> A
~~~

第一阶段边界原则：

- 复用现有 supervisor、router、stores、mailbox、PIT 和 safety verifier，不复制实现。
- Domain 纯规则不访问文件、网络或时钟。
- source 采集与 SOURCE_READY 是一个外部边界；下一 wake 才可开 ANALYSIS permit。
- Presentation 只新增只读 status 和明确的 revision reader 装配，不再增加业务规则。
- Infrastructure giant lane 不再获得新 owner；它只改为消费已封存 source，不在 ANALYSIS permit 内再次采集。
- “Application 不依赖具体 Infrastructure、Infrastructure 不反向依赖 Application”仍是 Cycle 1 后的目标，不在本轮一次性迁移。

---

## 5. 模块拆分表

| 层 | 现有模块/最小新增 | 唯一改动 | 明确不做 |
|---|---|---|---|
| Presentation | v32_target_wake_composition | 装配显式 revision reader；增加纯只读 status API | 不新建 TargetApi/Facade，不迁移 claim/submit |
| Application | v32_prospective_runtime | 在 READY_FOR_CYCLE 时先选择 SOURCE_PREPARATION；outcome 先分 FUTURE/DUE/EXPIRED | 不新建总 RunService/Reducer |
| Application | v32_cycle_composition | ANALYSIS permit 必须绑定已验证 PreparedCycleSource；EXPIRED 走现有 outcome terminal 体系 | 不复制 supervisor、CAS 或 safety |
| Domain | 一个小型 PreparedCycleSource builder/verifier + source-admission successor | 冻结四时钟、admission/replay binding 和消费身份；旧 admission schema 只读 | 不创建通用 event framework |
| Domain | v32_outcome_tick | 删除整刻限制；增加纯三态时间分类 | 不改变 horizon 或 grace |
| Infrastructure | v32_local_analysis_lane | 读取并验证 prepared source，跳过 permit 内 collector/admission/replay | 不继续下沉业务 owner |
| Infrastructure | v32_analysis_material_adapter | 必须接收显式 revision reader；缺失为 typed UNKNOWN | 不建设 importer/plugin SDK |

巨石文件本轮不拆。只有当这个切片仍无法走到 Agent request/outcome，才把相应失败 owner 迁出；不能预先迁移 20,000 多行代码。

---

## 6. 模块输入输出合同

### 6.1 PreparedCycleSource

必需字段：

| 字段 | 含义 |
|---|---|
| run_id / cycle_id / instrument_id | 唯一研究身份 |
| source_cutoff_at | formal qualification 允许 Agent 知道的最后时刻 |
| admitted_at | source admission 实际发生的系统时刻 |
| prepared_at | raw、qualification、admission、replay 全部封存完成的真实时刻 |
| qualification_binding | formal source qualification 的物理/语义 binding |
| admission_binding | source admission receipt |
| bundle_binding | raw-first normalized bundle |
| pit_registry_binding | 首次可得性登记 |
| revision_input_state | PRESENT 或 NO_REVISION_INPUT/UNKNOWN |
| prepared_source_digest | 全对象 canonical digest |

不变量：

- qualification.completed_at <= source_cutoff_at <= admitted_at <= prepared_at <= permit_opened_at <= decision_sealed_at。
- legacy analysis_decision_at 若保留，只精确回显 source_cutoff_at，不能用于 outcome schedule。
- 所有 datum 的 available_at 不晚于 source_cutoff_at 才可用于该 cycle。
- PreparedCycleSource 只可消费一次；过期后 terminal，不可刷新原对象。

### 6.2 OutcomeSchedule

| 字段 | 规则 |
|---|---|
| decision_sealed_at | 已耐久验证的 selection_compile_receipt.compiled_at |
| horizon_seconds | 900 / 3600 / 14400 |
| target_at | decision_sealed_at + horizon_seconds |
| expires_at | target_at + 900 秒 |
| state | FUTURE / DUE / EXPIRED / TERMINAL |
| scheduler_woke_at | 调度器真实唤醒时间 |
| capture_at | 若 DUE 成功捕获，记录 provider/local 时间 |

不变量：

- 不做 15 分钟格点对齐。
- DUE 才允许一次 public capture。
- EXPIRED 零网络，只能形成 UNKNOWN_COVERAGE_LOSS。
- 一个 schedule 最终只能有成功 outcome 或 window-missed terminal，不能同时存在。

### 6.3 ReadStatus

输入：run_id；now 只能来自 production System UTC；测试使用现有显式可控 clock，调用者不得在生产入口注入。

输出：纯只读 projection，不写文件、不联网、不 claim、不改变时钟：

- current_boundary；
- next_legal_action；
- active_permit；
- agent_stage；
- outcome_states；
- terminal_state；
- same_process_poll_required。

### 6.4 StrategyRevision

人工或外部慢数据字段：

- source_name、official_url、license/use note；
- event_time、publisher_release_at、received_at、available_at；
- raw physical digest；
- parsed typed observations；
- limitations、UNKNOWN 和 applicable_future_cycle。

任何字段缺失都不能用当前时间或 0 补齐。

---

## 7. 事件与状态流

### 7.1 正常 Cycle 1

~~~mermaid
sequenceDiagram
    participant API as 现有 target wake
    participant APP as 现有 router/coordinator
    participant SRC as 现有 collector/source stores
    participant LANE as 现有 analysis lane/mailbox
    participant OUT as 现有 outcome lane

    API->>APP: wake
    APP->>SRC: bounded collect qualify admit replay burst
    SRC-->>APP: PreparedCycleSource
    APP->>SRC: commit SOURCE_READY
    Note over APP,SRC: 外部边界 1 结束
    API->>APP: wake
    APP->>LANE: open ANALYSIS bound to prepared source
    LANE->>LANE: proposal request
    Note over APP,LANE: 外部边界 2 到 Agent
    API->>LANE: claim / submit once
    API->>APP: wake to compile proposal
    LANE->>LANE: selection request
    API->>LANE: claim / submit once
    API->>APP: wake to compile selection
    APP->>APP: verify selection receipt and seal decision_sealed_at
    APP->>OUT: build schedules from decision_sealed_at
    APP->>APP: bind schedules into shadow / commit / acceptance
    loop each scheduled wake
        API->>APP: read status then wake at most once
        APP->>OUT: success capture or verified EXPIRED terminal
    end
~~~

### 7.2 过期 outcome

验证 authority/schema/binding/chronology/CAS/schedule identity -> 若 EXPIRED -> no network -> build OutcomeWindowMissed -> atomically commit schedule TERMINAL -> next status can advance。验证失败走 owning FAILED_CLOSED，不得写 UNKNOWN_COVERAGE_LOSS。

### 7.3 外部进程仍在运行

工具返回 session_id 代表同一 OS 进程尚未结束，不是业务 PENDING。唯一合法动作是 poll 同一 session 到终态；不得启动第二个入口。read_status 只报告 same_process_poll_required，不接管该进程。

---

## 8. 扩展点设计：只定义替代边界，本轮不实现插件层

第一阶段继续使用现有具体实现，只把下列未来替代边界写清楚；不为它们新建协议或 adapter：

| 未来边界 | 当前实现 | 未来替代条件 |
|---|---|---|
| Public source | 现有 OKX BTC-USDT-SWAP collector | 仅同一 instrument、同等时间语义和合法公开源可替代 |
| Strategy revision | 显式 Empty/Local reader | importer 通过 schema、时间和物理 binding 后才能接人工文件 |
| Agent exchange | Current Codex durable mailbox | 必须保持同一单次交付、exact-tail recovery 和 receipt 语义 |
| Clock | production System UTC；测试现有可控 clock | 生产禁止 caller 注入；测试必须显式标识 |
| Durability | 现有 local write-once stores | 未来替代须先通过 write-once/CAS/reload conformance |

禁止：

- runtime 动态发现任意 Python plugin；
- provider 自动轮询和无限 fallback；
- 不同交易所数据静默拼成同一 OKX instrument；
- reader/collector 吞掉 UNKNOWN 或把缺失改成默认值。

---

## 9. 数据模型、现有覆盖与人工入口

### 9.1 当前已经真实取得过的数据

最近一次已封存但属于失败资格、不可复用的 source 证据显示：

- 12/12 OKX 公共组件曾取得 HTTP 200；
- 414 根 closed bars：15m 96、1h 168、4h 90、1d 60；
- 2,923 个 datum 没有 datum-level UNKNOWN；
- 可得字段包括 server time、instrument spec、ticker、mark、OHLCV/return/range/RSI14、OI level、funding、单次 order book/top-5 imbalance、recent-100 trade imbalance。

这只证明来源和解析曾经成功，不证明未来网络、Cycle 1、预测或收益。

### 9.2 当前仍为 UNKNOWN 的数据

| 数据缺口 | 当前处理 | 免费/合法路径 | 是否需要用户现在处理 |
|---|---|---|---|
| OI 变化而非单点 level | 跨 cycle 保存同一规格 OI datum 并计算 delta | OKX 官方 public OI | 否，AI 可实现 |
| 流动性韧性 | 定时重复 book snapshot，记录恢复时间；不能用单快照代替 | OKX 官方 market data | 否，AI 可实现 |
| 强平/forced deleveraging 历史 | 当前保持 UNKNOWN；OKX 当前 liquidation-orders WebSocket 不能补完整历史 | OKX 官方 WebSocket，仅前瞻 | 否，baseline 非前置 |
| 跨市场风险偏好 | 当前保持 UNKNOWN；以后接 BTC/CME/宏观同 PIT 数据 | CFTC、FRED、Treasury、Fed | 否 |
| 关注度/受众 | 当前保持 UNKNOWN 或有依据主观 assessment | Google Trends CSV；公开官方 RSS | 否 |
| 期权 IV/skew | 当前保持 UNKNOWN | Deribit public methods（交易所特定） | 否 |
| 完整机构流、社交全量、跨所强平历史 | 保持 UNKNOWN，不反复抓取或假造 | 通常付费或不可完整公开 | 否 |

### 9.3 免费官方来源

- OKX public API：https://www.okx.com/docs-v5/en/
- CFTC Commitments of Traders：https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- Deribit public API：https://docs.deribit.com/
- Coin Metrics Community API：https://docs.coinmetrics.io/api
- FRED API key：https://fred.stlouisfed.org/docs/api/fred/v2/api_key.html
- Google Trends CSV：https://support.google.com/trends/answer/4365538?hl=en
- Google Trends BigQuery：https://support.google.com/trends/answer/12764470?hl=en
- Federal Reserve H.4.1：https://www.federalreserve.gov/datadownload/Download.aspx?rel=H41
- U.S. Treasury XML：https://home.treasury.gov/treasury-daily-interest-rate-xml-feed
- SEC developer resources：https://www.sec.gov/about/developer-resources
- BLS API：https://www.bls.gov/developers/api_FAQs.htm
- FOMC calendar/RSS：https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

### 9.4 未来需要用户时的精确任务

baseline 不需要用户获取任何数据。只有 importer 与 StrategyRevisionPort 完成后，才可能请求：

1. Google Trends：把比较词放在同一次查询中导出一个 CSV，保留下载时间和查询地区/时间范围；不同导出批次的归一化指数不能直接拼接。
2. CFTC：下载 Bitcoin/Micro Bitcoin 的同一期 CSV，保留 report date、官方 release time 和本地 received_at；它反映 CME 仓位，不等于币圈交易所资金流。
3. FRED：如需自动拉取，用户自行注册免费 key 并放入项目忽略的本地配置文件；不得把 key 发到聊天或提交 Git。

当这些入口尚未实现时，用户提前下载文件没有验收价值，本计划不会要求。

---

## 10. 外部设施故障停止规则

### 10.1 网络与 provider

1. 正式 attempt 只允许一次；失败后封存，不重试同一 identity。
2. 开发诊断最多使用两种合理且合法的路线。例如官方主 host 加官方备选 host，或系统标准代理加直连网络诊断。
3. 出现 403、付费墙、许可、凭据或地域边界时立即停止；不改 User-Agent 欺骗、不绕过、不手工重排代理协议。
4. 若系统标准网络栈失败，用户检查 VPN/代理、DNS、系统时间、防火墙，并允许官方 hostname；仍失败则换官方公开源、采用慢速人工 revision 或把该轴保持 UNKNOWN。
5. 对快速 outcome mark，人工慢数据和另一交易所不能替代 OKX BTC-USDT-SWAP 同时刻 mark；只有合法窗口内唯一 attempt 的 typed 物理失败或已验证 window miss 才写 UNKNOWN_COVERAGE_LOSS，其他完整性错误继续 fail closed。

### 10.2 代码和架构

- 同一根因连续两次代码修复仍失败，停止第三个热补丁，回到 owner/contract 边界重构。
- 相同失败不得靠新 qualification identity 重复试探。
- 不 backfill sealed cycle，不删除失败证据，不把 missing 写 0。
- 不在每个局部修改后跑 30–60 分钟全量测试。

### 10.3 需要用户排障时提供的信息

AI 必须一次性提供：失败 URL/官方来源、HTTP/系统错误、发生时间、是否经过代理、已尝试的两条合法路径、为何不能自动替代、用户需检查的系统项、人工文件格式和恢复验收。不得只说“网络有问题”。

---

## 11. Agent 自主权与硬内核

### Agent 可自主决定

- 在 V3.2 既有 opposition 合同内成对提出、削弱、替换、合并、到期假说，并保留中性/混沌/OTHER 状态；
- 表达多、空、中性、混沌、过渡、方向未知和 OTHER；
- 对历史形态、RSI、反身性磁区、叙事传播、人群行为和外在路径提出有依据的主观 assessment；
- 选择 WAIT、条件 probe、开放研究计划或零方向计划；
- 在研究风险包络内提出动态管理路径；
- 对 UNKNOWN 给出有依据的主观等级，但不得冒充统计概率或客观事实。

### 硬内核只负责

- 时间和事实真值：未来不可见，缺失不等于已知，相关不等于因果；
- 权限隔离：当前只能公开数据、本地、不可执行；
- durable correctness：单写者、write-once、CAS、幂等、reload 可重放；
- 研究风险上限和 churn 上限；
- 证据绑定和反向假说可见性。

一般方向、因果、叙事或参与者动机不确定，不得自动触发全局 WAIT。只有依赖事实缺失、权限不允许、风险上限不可定义或当前动作确实被替代方案支配时，才阻断相应动作。

---

## 12. 测试与验证效率设计

### 12.1 已证实的重复成本

commit 9f5dba4 的一次性旧门结果：

- V3.2 discovery：785 tests，1,647.290 秒；
- full Theory discovery：1,552 tests，1,944.495 秒；
- 总墙钟约 3,592.8 秒，即 59 分 53 秒；
- full Theory 已包含 V3.2，因此先跑子集再跑全量是重复验证。

该 receipt 只证明旧 commit，不能授权修复后的代码。

### 12.2 新测试梯级

| 级别 | 内容 | 目标 |
|---|---|---|
| T0 | Domain contract/纯函数 | 常态 30s 内，硬上限 60s |
| T1 | 单模块 + fake port | 常态 120s 内，硬上限 180s |
| T2 | 现有 router/coordinator/state-machine/reload | 常态 300s 内，硬上限 420s |
| T3 | 真实 Presentation/Application/Store/Router，仅替换 Clock 与 HTTP transport | 常态 120s 内，硬上限 180s |
| Local impact | 静态路径影响表选择 T0–T3 | P95 8m，硬上限 10m |
| Post-commit | 本轮仍使用现有固定双 suite write-once runner，且只启动一次 | 预计约 60m；本轮不修改资格协议 |

正式门去重不与三个 P0 同批实现。Phase 1 在开发期只跑 T0–T3 和影响集；代码冻结并提交后才运行一次现有双 suite runner，之后不得再改该 commit 或重复启动同一 pair。

Cycle 1 后可另立 receipt v2 迁移。它必须是 v1 的严格超集，完整保留 exact commit/tree、branch、Python 物理身份、固定环境和 argv、worktree allowlist、started/completed、timeout、exit、count、bounded stdout/stderr bytes 与摘要、attempt=1/no-retry、aggregate/physical replay，并新增 full test-ID set 及 V3.2/non-V3.2 精确分区。loader、manifest、authority 和历史 v1 兼容必须同批设计和验证；在此之前不得用“单次 full”签发资格。

### 12.3 必须新增的真实组合测试

使用 12:07:31.123456Z 等非整刻时间：

1. source capture/qualification 完成晚于 opening request，仍能先封存 SOURCE_READY；
2. source_cutoff_at <= admitted_at <= prepared_at <= permit_opened_at <= selection_compile_receipt.compiled_at，且至少物理顺序/receipt predecessor 严格推进；legacy analysis_decision_at 只回显 source cutoff；
3. 15m target 精确为 decision_sealed_at+900s，不要求 00/15/30/45；
4. target_at 前为 FUTURE，合法窗口内只 capture 一次；
5. expires_at 后零网络封存 UNKNOWN_COVERAGE_LOSS；
6. 进程重建和重复 wake 不产生第二写或第二网络；
7. revision reader 缺失表现为 typed UNKNOWN，而非空事实；
8. read_status 多次读取无文件变化、无时钟变化、无网络。
9. qualification/admission/replay 在单次 SOURCE_READY 外层 wake 内完成且仅一次网络；合法 partial prefix 可续接。长中断导致 permit 前 stale 时只写一次 owning failure，零 Agent、零第二网络；selection 后 stale 只写一次 `SOURCE_STALE_AFTER_AGENT`，零第二 Agent、零自动重采。

### 12.4 qualification 前停止门

按顺序：

1. T0–T3 全部通过；
2. 本地 exact production composition rehearsal 通过；
3. 提交代码；
4. 现有 post-commit 双 suite runner 只启动一次并生成 write-once receipts；
5. 使用标准系统网络栈进行一次非授权 transport smoke；失败则停止，不创建 qualification；
6. 全新 exact pair 执行 fresh qualification；
7. Current Codex proposal/selection、固定 monitor 和 finalize 都成功后，才创建 target；
8. target 先完成 Cycle 1 和至少一个正式 outcome，再讨论理论/策略调整。

---

## 13. 三阶段路线图

### Phase 1：恢复最小正式主链

范围：

- PreparedCycleSource / SOURCE_READY；
- source-admission 四时钟 successor（旧 schema 只读）；
- OutcomeTimePolicy 去格点；
- EXPIRED 零网络终态；
- 显式 StrategyRevisionReader；
- read_status；
- 非整刻组合测试；
- 分层开发验证；提交后一次现有固定双 suite 正式门。

完成定义：新 commit 的本地门、transport smoke 和 fresh qualification 全部通过；唯一 target Cycle 1 可进入 Agent proposal/selection 并封存 acceptance/schedules。

### Phase 2：用正式结果检验理论

只在 Phase 1 成功后：

- 解析 15m/1h/4h outcomes；
- 记录每轮完整但压缩的 source、假说、反向假说、主观 UNKNOWN 依据、行为规划和 revision；
- 增加 OI delta、重复盘口韧性、已有 bars 的 timeframe coherence；
- 评价覆盖、延迟、行动多样性、WAIT/probe 结构和失败归因；
- 不在看到结果后回写旧 cycle 的理论或评分规则。

### Phase 3：证据驱动优化

只有实验暴露真实瓶颈后才选择：

- 拆 public source collector；
- 进一步迁出 analysis lane；
- 设计严格超集 receipt v2 并去除正式双 suite 重复；
- 加人工宏观/关注度 revision；
- 冻结关联候选全集、窗口、滞后和多重检验；
- 设计概率校准、成本后收益、跨 regime 泛化；
- 另行授权 paper/testnet，再讨论 execution capsule。

---

## 14. Legacy 兼容与迁移

- 所有旧 V3.1、s3、E0/E0B、失败或过期 V3.2 run 保持原字节、原 verifier 和只读 replay。
- 本轮沿用现有 V3.2 engine、公开 API、stores、mailbox、verifier 和 manifest family；只给 fresh run 生成新 authority，不引入 engine selector。
- 旧 API 响应保持兼容；新增 read_status 是只读旁路，不迁写 checkpoint、permit、artifact 或 receipt。
- PreparedCycleSource 是新 run 的前置对象；旧 run 不补造、不迁移、不由新 router 续跑。
- 新 run 使用版本化 source-admission successor，明确 source_cutoff_at、admitted_at、permit_opened_at，并以 selection_compile_receipt.compiled_at 定义 decision_sealed_at；旧 admission schema 和旧 decision_time 等同关系仅由历史 verifier 重放。
- safety/authority closure 继续冻结所有实际生产改动；缩小 closure 属 Cycle 1 后的独立治理设计，不在本轮偷改。
- 旧 verifier 永不以新 schema 解释历史失败；新 schema 也不为旧树补造字段。

---

## 15. 风险、回滚与决策点

| 风险 | 控制 |
|---|---|
| 窄切片仍被现有 giant lane 私有接口绑死 | 只允许复用现有公开 store/collector API；若必须新增第二个私有 writer 调用，停止并迁出对应 store contract |
| SOURCE_READY 增加一个 wake | 这是必要的真实时间边界；read_status 消除盲轮询，bounded internal material steps 保留 |
| 当前正式双 suite 仍耗时约 60m | 本轮只在最终 commit 后运行一次；receipt v2 去重延期，避免把 P0 修复扩大成资格协议重写 |
| 网络 smoke 成功但 qualification 失败 | qualification 仍 fail closed；按新错误分类一次处理，不重用 identity |
| Agent 输出超容量 | 保留当前 single inline envelope 和总门；不恢复旧 shard 膨胀路径 |
| Phase 1 扩展成重写 | 一旦超出本节列出的模块/合同，必须暂停并回到用户决策 |

回滚：Phase 1 只服务新 identity；失败时封存新 qualification/target pair并停止。旧 run、旧 API 和旧 verifier 始终只读，不回写；不能用 Git 回滚去继续已封存 identity。

---

## 16. 当前状态与下一步

已完成：

- 完整只读主链、owner、三项 P0、P1、测试重复与数据缺口分析；
- 本修复设计和需求边界冻结；
- 独立设计复核已关闭 source 四时钟、coverage-loss 限域、opposition 冻结、receipt 范围、最小切片和 post-Agent stale 的全部 P0/P1 阻断；
- 旧 commit 9f5dba4 的一次性回归自然完成并隔离，未进入 qualification。
- Phase 1 候选已实现：SOURCE_READY 单边界、source-admission v2、selection-sealed outcome 时钟、任意秒 horizon、零网络 expiry terminal、显式 revision input、严格只读 status。
- 已关闭随后暴露的同族缺口：active permit 的 registry/permit 损坏耐久失败关闭、跨 grace 后网络前阻断、FAILED_CLOSED 在损坏 registry 前幂等短路、`SOURCE_STALE_AFTER_AGENT` typed owner，以及 aggregate-commit 后进程重启恢复。
- 分层本地验证已覆盖真实两阶段 Agent、四时钟严格顺序、非整刻 selection sealed time、Supervisor READY、48-row 容量投影、零第二网络/写入和 mutable-head 双读。慢速 local-analysis 最近一次完整为 8/8 PASS；正式全量门尚未运行。
- 提交前静态边界已完成：34 个变更 Python 文件可解析，diff 格式与敏感正向能力扫描通过，用户副本字节和 SHA-256 不变且明确排除在提交之外。
- 第一次 post-commit pair 已永久失败关闭且未进入 qualification。`18 errors / 3 failures` 归并为三项遗漏旧夹具/闭包断言；仅修改 4 个测试文件后对应聚焦 25 项通过，生产代码没有再次变更。

尚未完成：

- 回归治理小提交及新的 write-once 正式双 suite；
- 标准系统网络栈的一次 transport smoke；
- fresh qualification；
- target authority、target genesis、Cycle 1 或 outcome monitor；
- 市场预测增量、概率校准、成本后收益和跨 regime 泛化评价。

推荐唯一下一步：提交已通过聚焦验证的 4 文件回归治理，再用全新 exact pair 运行一次 write-once 双 suite。通过后才做标准系统 transport smoke 和 fresh qualification；在此之前不修改理论，也不要求用户获取数据。
