# MSTA-HED 研究系统变更记录 v1.0

## 2026-07-27 — RSR-P0 v1.0

### 变更类型

`PROGRAM_LEVEL_RESEARCH_RECONSTRUCTION_CANDIDATE`

### 权威与保留

- 新增 Sol 路线决定
  `config/sol_decision.research-system-reconstruction.v1.json`。
- `CORE_TRADING_THEORY_v2_1.md` 继续为只读当前核心权威。
- 旧 active-G1 终局继续不可变，未读取或修改活动 Application Support 根。
- 旧 P1A-R3.1 终局及其六个绑定工件继续不可变；没有修补、重开或声称完成。
- 已看 January/February chronology 继续保持 seen/censored 身份。

### 理论变化

- 将事实、测量、状态、结构位置、机制、路径、情景、交易命题、效用、权限、
  行动和结果拆为不同对象。
- 用依赖 DAG 代替容易误读的线性叙事。
- 引入统一 PIT 信息集、revision、gap、censoring 和 ClockProfile 方向。
- 把 RSI 限定为条件观察触发器，不能单独生成订单。
- 将用户多日案例抽象为可变长度
  `shock → compression/response → resolution/expiry`。
- 新增四个竞争分支：吸收转换、挤压失败、平衡、支撑消耗。
- 将“固定八日普遍规律”归档为需求误读反例，而不是经验模型。
- 把 `OTHER_PATH`、`UNKNOWN_PATH` 和 `ABSTAIN` 分离。
- proper score 只用于可观测、互斥 outcome；机制支持保持 ordinal。
- 动态止损/目标必须保持最坏风险单调不扩大。

### 假说治理变化

- 弱证据和无直接证据假说优先进入验证队列，不因证据不足删除。
- 每个 testable hypothesis 强制绑定 measurement contract。
- 失败后先诊断 data、measurement、label、state、mechanism、path、
  dependence、calibration、action、cost、transport、permission。
- 每个 retest 只允许一个主要理论变化。
- 旧版本、负面结果、contradiction、expiry 和 falsification 永久保留。
- 禁止看到 outcome 后修改 cohort、label、horizon、comparator、cost、
  wording 或 holdout。

### 数据权威变化

- 恢复用户定义的 A–E 证据等级：
  - A：官方原始/标准/数据库/原始实验/高质量同行评议；
  - B：权威报告、专业数据库、可复现研究；
  - C：有方法和来源的二手研究；
  - D：新闻、平台、个人经验；
  - E：不可追踪或不可验证。
- 把 authority grade 与 integrity、coverage、revision、PIT 四轴分开。
- 登记 21 个官方、专业和原始研究文档候选。
- 没有下载市场记录、没有使用认证/付费源、没有数据准入。
- strict L2 与 aggregated bookDepth 明确区分。

### 研究团队变化

- 固定角色表改为按依赖和风险动态增删的最小团队。
- 保留 Sol ultra 路线/阶段门与 Terra high 日常研究/实现分工。
- builder 不得接受自己的 candidate。
- authority、raw、chronology、holdout 强制独立对抗复核。
- 同根因两轮未关闭时升级，不无限重复调用低质量实现路径。

### 新增工件

- `RESEARCH_SYSTEM_THEORY_CHALLENGER_v1_0.md`
- `RESEARCH_TEAM_GOVERNANCE_v1_0.md`
- `DATA_AUTHORITY_STANDARD_v1_0.md`
- `RESEARCH_SYSTEM_AUDIT_v1_0.md`
- `RESEARCH_SYSTEM_ROADMAP_v1_0.md`
- `RESEARCH_SYSTEM_CHANGELOG_v1_0.md`
- `config/research_system.object_dictionary.v1.json`
- `config/research_system.hypothesis_validation_queue.v1.json`
- `config/research_system.measurement_contract.v1.json`
- `config/research_system.parameter_registry.v1.json`
- `config/research_system.dispute_registry.v1.json`
- `config/research_system.source_authority_registry.v1.json`
- `config/research_system.stage_contract.v1.json`

validator、tests、inventory 和 validation report 将在本 P0 候选闭合后登记。

### 2026-07-27 — 独立数学审查与局部修订

- 保留首轮失败报告
  `artifacts/research_system_p0_independent_math_review.v1.json`，未覆盖历史结论。
- 六份 registry/stage 及 dispute registry 均显式声明
  `SHA256(domain || 0x00 || canonical JSON)`，并重算自摘要。
- ER 与 RVOL 增加零分母、非有限、单位不兼容和历史不足的 typed `UNKNOWN`。
- 证据衰减改为 `exp(-ln(2) × age / half_life)`，使登记参数确实表示半衰期。
- E0 禁止未登记的 ordinal prior/weight；补充冻结组内聚合器、组上限和总上限。
- 仓位几何回归当前核心 v2.1 的成本/尾部风险/同单位数量约束；P0 继续
  `max_risk=0`。
- 数值 EV 强制绑定互斥、完备、含 `OTHER/UNKNOWN` 且概率和为 1 的
  `ActionOutcome` 分区；不满足时返回 `UNKNOWN`。
- 自然语言 hard falsifier/expiry 明确标为
  `NOT_YET_EXECUTABLE_BLOCKS_D3_E2`，未伪装为可自动评分。
- 复核报告
  `artifacts/research_system_p0_independent_math_recheck.v1.json`
  将四项可局部关闭问题记为 `CLOSED`，机器谓词缺口保留为
  `DEFERRED_BLOCKING`。

### 2026-07-27 — 纯验证器候选

- 新增 `trade_system/research_system_contract_v1.py`，输入只允许七路径原始文本
  bundle，不执行文件、网络、市场、adapter、回测或交易 I/O。
- 新增 `tests/test_research_system_contract_v1.py`。
- 严格拒绝 malformed/duplicate JSON、NaN/Infinity、类型混淆、未知字段、
  摘要/域/分隔符篡改、authority 自授权、阶段权限提升、交叉绑定错误、
  lifecycle/result history 破坏和多层编码别名。
- 首轮 82 项测试通过后，独立复核发现 gate prerequisites/deliverables 可被
  重签改写；局部修订将七个 gate 的完整条款和顺序固定在候选外部，并增加
  6 个反例。当前定向结果为 88/88 通过。
- 当前 bundle digest：
  `c4eb9da641ee6a8f2971d06174f9eaa2c970122fa106acc9a2e8f584833b085d`。
- 本记录仍是本地 P0 候选事实；独立最终对抗报告和 Sol P0 阶段门尚未完成。

### 已修订的关键错误

- 不再把 P1A terminal block 表述为普通 WAIT_DATA。
- 不再把数据/时钟 invalidity 作为市场机制 falsifier。
- 不再把机制 ordinal support 当作 probability。
- 不再用 OTHER 代替 UNKNOWN，也不把 ABSTAIN 当路径。
- 不再用事件响应同时作为 detection 和 outcome。
- 不再把专业付费源自动降为低可信，也不自动升为 A；按具体命题评为 B。
- 不再把原始高质量论文列为低等级来源。

### 尚未改变

- 没有修改现有核心理论权威。
- 没有改变任何活动/历史 raw 数据。
- 没有运行 adapter、dataset build、backtest、calibration、holdout、paper、
  deployment 或 trading。
- 没有形成市场有效性或盈利结论。

### 最大正面声明

本版本只建立了可审计研究体系候选和 P0 结构化工件。只有 pure validator、
独立对抗复核与 Sol P0 阶段门全部通过后，P0 才完成；即使 P0 通过，也必须
另行申请 D0，不能自动取得历史数据。
