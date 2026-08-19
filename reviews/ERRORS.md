# 错误复盘

更新日期：2026-08-17

本文件是项目唯一错误整理入口。只记录影响、根因、纠正、预防、状态和必要证据；不复制命令日志和过程叙述。

| ID | 问题与影响 | 根因 | 纠正与预防 | 状态 / 依据 |
|---|---|---|---|---|
| E-001 | V3.2 与全 Theory 重复执行，同次变更约耗时一小时 | 全 Theory 已包含全部 V3.2，runner、aggregate 和测试合同仍强制串行两套 | focused runner 按 exact test ID 去重；V3.4 只运行 owning targets/直接消费者，不因 run/cohort 身份重复回归 | `CLOSED`；当前 focused-runner contract 与 V3.4 owning targets 同门通过，冻结旧全套无需为 V3.4 重跑 |
| E-002 | 同一提交更换 run/qualification ID 后重新回归 | 代码能力结果同时绑定 commit/runtime 和实验身份，唯一性只在 qualification namespace | 旧 qualification/cache 不进入 V3.4 主路；V3.4 回归由代码/测试 target 决定，forecast cohort/asset/slot 变化不触发代码回归 | `ACCEPTED_LIMITATION`（冻结历史）；不再扩建旧 qualification cache，V3.4 不依赖该路径 |
| E-003 | Q0–Q8、43→196 文件闭包和全 loader 每轮重放 | 资格、发布和实验运行混成一条链 | COLD 新热路径移除 qualification/target 中心，只保留公开数据、Agent、outcome、review 和权限边界 | `CLOSED`（COLD）；依赖边界与唯一离线 E2E 已通过，旧 reader 只读保留 |
| E-004 | 四套状态头、跨层 binding 和大量小工件使恢复与修改互相阻断 | 多模块共同拥有同一运行事实 | `CycleService` 独占逻辑 RunState，Repository 独占物理写入；cycle 只暴露五类工件 | `CLOSED`（COLD）；CAS、head/history/intents 与恢复合同已验证 |
| E-005 | 四个模块合计约 13,096 行且职责混合 | transport、解析、业务、状态、资格和呈现未分层 | V3.4 新主路按 domain/application/infrastructure/presentation 分 owner；旧 V3.2/V3.1 仅作冻结历史消费者，不再承接新功能 | `ACCEPTED_LIMITATION`（冻结历史）；删除旧 13k 行对当前 V3.4 无结果增益且可能破坏历史取证，因此不继续重构 |
| E-006 | source 时间倒置、相同微秒严格顺序等问题反复阻塞 | 把不同小数精度的 ISO 文本按字符串比较，且物理时钟与领域时序混用 | 解析为真实 UTC 时刻比较；领域接收显式时间，设施负责时钟 | `CLOSED`（COLD）；相关 owning/合同验证已纳入 68/68 PASS |
| E-007 | 任意秒 decision 与 outcome 格点冲突，过期窗口永久卡死 | outcome 从交易所 K 线格点而非封存决策时刻建模 | outcome 以 sealed decision + horizon/tolerance 定义；缺失或过期形成 typed terminal 并继续 Review | `CLOSED`（COLD）；合同、public-data 与离线 E2E 已通过 |
| E-008 | Agent 后数据过旧、材料化耗尽窗口、阶段拆分等待过多 | 材料过大且 qualification/wake 反复切换 | V3.4 只在固定 4H slot 构建 `previous StrategicState + current delta` 的有界 context，单次 FORECAST 后结束；不再反复 qualification/wake | `CLOSED`（V3.4 工程根因）；真实 provider/市场端到端延迟作为 Stage-A 观测指标保持 `UNKNOWN`，不再是 continuous runtime 阻塞 |
| E-009 | 并发进程重复推进并写出相互冲突状态 | 缺少 cycle 级唯一 owner，调用端把超时 yield 当完成 | cycle lock、CAS、pending intent 与 forward-only RunState；运行中不得第二次 advance | `CLOSED`（COLD）；并发、stale state 与恢复合同已通过 |
| E-010 | 外部接口连续失败后仍批量尝试，浪费时间且没有新增证据 | 没有耐久 attempt claim、主/备路线和明确停止条件 | V3.4 FORECAST harness 本身无网络 authority，只消费已合法准入 PIT 输入；旧 collector 的 manual-intake 完整化不再属于当前 cognition runtime | `ACCEPTED_LIMITATION`（冻结旧 collector）；未来若接回网络 collector，必须在新版本按“一主一备后停止”的现有项目硬规则单独验收 |
| E-011 | 根目录 74 份 Markdown、巨型需求和 README 混合历史与当前状态 | 没有文档 owner、唯一入口、生命周期和退出规则 | 当前入口、正文、历史和冻结证据分流；旧路径用映射表和原提交解释 | `CLOSED`：根目录只剩 3 个入口；旧需求、理论、审计、日志、实验和用户副本均已分类 |
| E-012 | 市场理论和治理在正式 Baseline 前持续扩张，正式 V3.2 Cycle 仍为零 | 工程完备度代替市场实验产出 | 当前 V3.4 固定 `FORECAST_ONLY → FROZEN_PLAN → DYNAMIC_MANAGEMENT` 三阶段；Stage A 期间冻结交易理论，只允许修运行阻塞，禁止用工程扩张替代市场证据 | `CLOSED`（当前工程根因）；Stage-A 市场有效性仍 `UNKNOWN`，不得把未运行的市场验证写成工程未完成 |
| E-013 | 将 adapter 存在、API 可达或旧工件误写成当前数据能力 | “理论可接入”和“当前已获取”未分层 | V3.4 forecast 明确要求 admitted source refs、input cutoff 与 data-quality/conflict 分析；adapter/代码存在不能升级成已观测事实，缺失继续 `UNKNOWN` | `ACCEPTED_LIMITATION`（数据覆盖未知）；真实可用数据覆盖必须由未来 Stage-A 每个样本的 admitted PIT 输入证明，不用工程存在替代 |
| E-014 | V3.2 单项平均耗时显著高于其余 Theory，去重后仍会慢 | 每方法重建 Git/临时目录/大型 authority，并沿 lifecycle/acceptance 重复 canonicalize 与完整 replay | 当前 V3.4 只运行显式 owning targets 与一个本地 CLI E2E；冻结 V3.2 慢 materializer 不进入当前回归门 | `ACCEPTED_LIMITATION`（冻结历史性能）；不为退出主线的旧 suite 做高成本优化，当前 V3.4 focused gate 在秒级完成 |
| E-015 | 单点 runner 首次直接执行时 17 个 selector 全部导入失败，业务测试未启动 | 脚本从 `tools/` 启动时未把项目根目录加入 Python 导入路径 | 启动时显式加入精确项目根；合同测试固定该路径；随后同一精确入口运行成功 | `CLOSED`；runner/fixture 8 项 `0.096s` PASS，owner 9 项 `27.506s` PASS |
| E-016 | Agent 迟到或仓位计划在 outcome due 后仍可能封存，造成前瞻污染 | prospective deadline 只在部分阶段检查，seal 前没有统一失败关闭 | Agent delivery 与 BehaviorPlan 都必须在 due 前完成；迟到形成终态失败，不回写旧 cycle | `CLOSED`；受影响五 target 合计 68/68 PASS |
| E-017 | 崩溃窗口可能在公网请求已发出后丢失 attempt 身份并再次请求 | 请求认领未先于网络持久化，恢复无法区分未发与已发 | 请求前写 durable attempt binding；恢复只重放同一 raw response，indeterminate attempt 关闭旧 cycle | `CLOSED`；无二次网络、binding drift 和 crash recovery 合同已通过 |
| E-018 | 顶层工件摘要正确时，嵌套 raw ref 缺失或篡改仍可能被继续使用 | Repository 只验证直接 artifact，没有递归验证 raw bundle | 写入、读取、恢复和继续前统一复验所有嵌套 raw path/size/SHA-256 | `CLOSED`；缺失、损坏和 outcome raw 的生产 Repository 合同已通过 |
| E-019 | Agent 缺失、重复或未知的 lead/runner-up/OTHER 选择可能泄漏裸 `StopIteration` | 归一化过程先做查找，未在领域边界验证 supplied hypothesis IDs | 先验证三项存在、互异且均指向 supplied hypotheses；统一抛出合同错误并终态 `ANALYSIS_FAILED` | `CLOSED`；contracts/core E2E 已纳入最终 75/75 PASS |
| E-020 | 三个连续 Agent proposal 被逐层隐藏的格式约束拒绝，且部分 delivery 已写入后才失败；旧 run 无有效 HypothesisRecord/BehaviorPlan | Agent 可见 schema 不完整，Primary 手写重复合同，deliver 与 next 使用不同强度校验，合同没有单一事实源 | Domain `AgentProposalContractV1` 成为唯一机器 owner；packet disclosure、service-lock 写前校验和 next 复用同一 validator，旧 mailbox 活动写入口退出 | `CLOSED`（工程）；27/27 精确 selectors PASS；旧 run `SYSTEM_UNSTABLE_CLOSED`，修复后必须新 run；市场与四性质仍未评价 |
| E-021 | 替代 run 第 11 槽使用冻结集合外 lifecycle `RETAINED`，机器预检通过；Primary 写入前拒绝但系统无公开 typed-close 入口 | 唯一 `AgentProposalContractV1` 未描述/校验首槽与续槽的 `candidate_lifecycle`，Controller task 又漏列精确枚举；Application 缺少无 delivery 时的受锁失败关闭 | Proposal schema 2.0.0 强制两种 exact shape、七个 token 和续槽 ID 唯一；新增 `controller-reject-agent`，同 code 幂等且 sidecar/错 stage/异 code fail-closed | `CLOSED`（工程）；28/28 精确 selectors PASS；旧 run 10 Review 后关闭且第 11 槽无 delivery；新实现/run 身份必需，四性质与市场结果仍未评价 |
| E-022 | 严格语义 schema 与确定性 planner 取代交易 Agent，造成格式事故，并使最终动作、点位和仓位能力不可观察 | 把记录编码器与确定性 baseline 错设为市场决策 authority，而非辅助 Agent 的工具 | Agent 独占最终不可执行参考决策；原文先封存、索引非权威；格式/语义缺口进入质量证据而非系统终态；planner 只作计算或隔离对照 | `CLOSED`（工程）；Agent-first 双原文往返、PIT 记忆、外部 run 身份锚和唯一离线完整 E2E 已通过；市场能力仍未评价 |
| E-023 | 固定 00/30 唤醒错过任意秒 Outcome，且 task 写入后无 dispatch ACK 导致 Worker 未启动 | 缺少三类 Worker 共用的耐久 earliest-event/dispatch 状态、hard-stop admission 和无 task 的到期关闭 | 唯一非业务 sidecar 记录 wake ACK 与 PREPARED→SPAWN_REQUESTED→DISPATCHED→终态；迟到 Decision/Review 写前关闭，无 PREPARED 的 Decision 按 sealed request 到期；CLOSED 只读身份稳定 | `CLOSED`（工程）；Primary 复算实现 `36c3edd4…`，独立静态 P0/P1=0，changed-path 39/39 PASS；事故 run 不恢复，新 run 必需 |
| E-024 | 合法 Worker 原文已在期限内交付，但因未重复回显 task 的 `available_at` 而无法完成 cycle | Controller 把系统自有 PIT 元数据也纳入 result 全对象逐字相等硬门 | task 继续独占校验 `available_at`；result 只强绑定同序 `role/path/SHA`，主动回显的 `available_at` 仍须一致；正文、期限和 transport 原样绑定不放宽 | `CLOSED`（工程）；33/33 最小 owning/核心 E2E PASS；事故 run 已关闭，新实现/run 身份必需 |
| E-025 | 首次 HYPE run 在约 17.3 小时内形成 39 个 entry episode、42 次 entry intent 和 41 次主假说切换；10/12 已成交 episode 亏损，摩擦占已知亏损约 74.1% | 正式 deterministic calculation 实际已有 1D/4H/1H/15m；缺口是认知主线仍沉到窄 15m/微观路径，路径更新、主 thesis 切换、反向 exposure 与成本门之间缺少迟滞，而不是“没有高周期数据” | r3 L2 作为历史 cohort 保留；其暴露的问题转入 V3.4 低频战略架构，不再通过旧阈值微调或补样修正 | `ACCEPTED_LIMITATION`；r3 在用户截止时有 3 个自然成交、完整关闭并 Review 的合格 episode，0 胜 3 负、累计已知净 PnL `-4.613037835850`，fee/spread/impact 合计 `1.995637835850`、约占已知亏损 43.26%；3/12，保持 `MEASUREMENT_INSUFFICIENT`，run 已关闭且永久不补样 |
| E-026 | 旧 run 的 196 份 Decision 没有继续到基础 Outcome/Review，后轮也只见前序引用而没有最近完整原文，无法形成正式逐 episode 学习链 | `AGENT_OUTPUT_INCOMPLETE` 是非权威 projection，未阻断五工件；真实缺口是旧 cycle 未被后续自然唤醒对账，以及 `paper_context` 未有界携带最近 COMPLETE Decision/Review 精确正文 | `paper_context` 1.5.0 只携带最近一个 PIT 合格 COMPLETE 原文、大小、SHA 和引用；state 1.1.0 保存非权威 formal obligations/prior sample/evaluation 索引；每次自然唤醒先履行到期 cycle，不重复灌静态理论 | `CLOSED`；Cycle A 已 COMPLETE，Cycle B 请求 `8dd22be2…b825` 的 context `6d35afa4…14e2` 对 Decision/Review 精确文本、大小、SHA、工件引用、PIT 和单项边界全部通过；旧 run 仍只读且未补写 |
| E-027 | r3 Cycle C 将合约乘数算术算错，计划 notional 超 cap | 把精确合约/风险算术交给 LLM 自算 | V3.4 将数量、notional、PnL、战略/灾难风险、gap/impact/cost stress、maximum-loss budget 与 R:R 全部交给 Decimal checker；任何未来 exposure 必须先通过 checker，未接入该门前无 V3.4 paper authority | `CLOSED`（V3.4）；旧错误 intent 从未进入 ledger；当前 FORECAST_ONLY 无数量/订单权限，未来交易阶段不得恢复 LLM 算术 authority |
| E-028 | r3 Cycle H 因 Agent request 与 paper process 手工顺序冲突而 `ANALYSIS_FAILED` | 一个 cycle 的 request/process 由调用方跨步骤编排，状态所有权不单一 | V3.4 当前 qualification 由单一 `V340ForecastQualificationService` 负责 build-context→seal-forecast→seal-outcome，固定 slot/previous-state 顺序由服务检查；不暴露旧 paper request/process 手工组合 | `CLOSED`（V3.4 当前路径）；旧 H 保持不可变，未来 FROZEN_PLAN 必须复用单 service/state-owner 原则，否则不得获得 paper authority |
| E-029 | r3 H–O 因 CLI 默认值遗漏而把 300 秒 Outcome tolerance 变成 60 秒 | 时间策略由每次调用者重复传参，run policy 未成为时间 authority | V3.4 移除 Agent/调用者自选 cognition interval：固定 UTC 4H committee 与完整 24H forecast outcome 由 domain/service 计算并校验，无 per-cycle tolerance CLI；Agent 请求提前 wake 一律无效 | `CLOSED`（V3.4）；旧 H–O 保持原字节；若未来阶段需要执行 tolerance，必须来自冻结 plan/run identity 而非临时 CLI 默认值 |
| E-030 | r3 Cycle U 在两次 CLI 调用之间丢失公开采集授权，Outcome 变 `TYPED_MISSING` | `next` 与实际 capture 分离，授权不跨调用继承 | V3.4 FORECAST_ONLY service 不自行抓网；只接收已合法准入且带 immutable refs/input cutoff 的 PIT summary，一次 context seal 后以 asset/slot/size/SHA 绑定，Outcome 也由显式 admitted input 传入；不存在跨两步网络授权的隐式继承 | `CLOSED`（V3.4 当前路径）；旧 U 不回填；未来 collector 若重新接入必须在实际网络调用边界显式授权 |
| E-031 | r3 名义使用 4H/1H/15m，真实 exposure/退出却退化为局部阈值；WAIT/HOLD/ADD/REDUCE/HARVEST、PnL 分离、人群/事件/未来空间和多周期权限没有形成交易前强语义 | 把“原文可保存”与“足以承担 exposure”混为一体，加上 continuous-goal 的阈值锚定、注意力稀释与短周期在线控制 | V3.4 已实现 `strategic_control.py`、固定 4H `scheduled_strategy.py`、Durable Strategic State 与 FORECAST_ONLY qualification：4H 是最低 LLM decision authority，1H/15m 仅证据；语义门强制完整认知/动作比较/风险几何，普通 1H/15m 不得全平 CORE | `CLOSED`（当前 V3.4 工程根因）；市场判断能力仍 `UNKNOWN`，且 paper authority 故意保持关闭，不能把工程关闭写成盈利验证 |

| E-032 | continuous-goal 单币种长时运行出现极端 token 消耗、上下文/注意力漂移、指令遵循衰减、错误市场激活、重复分析和短周期权重膨胀；扩到多币种会近似放大成本 | 把 LLM 当 24/7 controller，并让模型自己决定何时继续看市场；每轮重复历史/理论，缺少 durable state、context budget 和固定 wake authority | V3.4 改为外部 UTC 4H scheduler（每日每资产 6 slot）、state+delta 的 64 KiB bounded context、asset/slot/digest 绑定、intra-window no-new-LLM-thesis；未来多模型节流另以 Post-V3.4 Manager 规划，当前不启用 | `CLOSED`（V3.4 架构）；用户观察的约 `8e8 token/day` 只作为旧 continuous-goal 失败症状；新架构真实 provider token 成本必须在 Stage-A 样本中重新量测 |

## 新错误记录格式

新增错误只追加一行，并满足：

- 一个根因只建一个 ID；相同根因的后续表现更新原行。
- 状态只允许 `OPEN / MITIGATED / CLOSED / ACCEPTED_LIMITATION`。
- 只有修复已实现且相关最小验证通过，才能标记 `CLOSED`。
- 错误详情若必须保留，链接结构化证据或精确源码；不新建叙事型复盘文档。
