# MSTA-HED 最初方向与当前系统一致性审查

> 日期：2026-08-06  
> 状态：`BASELINE_AUDIT_FROZEN / LOCAL_DYNAMIC_CONTRACT_CORRECTION_COMPLETE`  
> 证据权限：`LOCAL_DOCUMENT_CODE_AND_FROZEN_ARTIFACT_REVIEW_ONLY`  
> 实验与交易权限：`NONE`

## 1. 结论

当前系统**没有整体背离** MSTA-HED 的主方向，但只实现了“动态证据更新”的一部分，尚未实现“动态假说系统”。更准确的裁决是：

- 多周期、点时数据、事实—推断—假说—决策—执行分层、证据留痕、条件动作和风险边界仍与最初目标一致；
- v1.4 的支持等级、情绪标签和路径排序会随每轮数据变化，因此不是完全静态；
- 但路径类别、机制类别、比较路径数量和情绪维度被代码白名单预先限定，Agent 只能在固定槽位中改写内容，不能在新机制出现时真正创建、拆分、合并或替代一个新方向；
- 系统没有独立 expectation ledger，无法逐轮追加、去重、验证和关闭“接下来应观察到什么”；
- v1.4 已保存大量市场原始数据和派生特征，但这些数据还没有作为统一的 `market_information_snapshot` 与情绪量化、动态假说和 expectation 共同绑定到新连续核心的 cycle evidence receipt；
- 情绪已有具体证据引用和四维文字判断，但没有统一的多轴序数量化、覆盖率、分歧、缺失和跨周期一致性记录，不能直接做可靠的跨轮统计。

因此当前状态是：`PARTIALLY_ALIGNED / DYNAMIC_RANKING_PRESENT / OPEN_HYPOTHESIS_CREATION_MISSING / EXPECTATION_LEDGER_MISSING / SENTIMENT_QUANTIFICATION_INCOMPLETE`。

## 2. 审查输入冻结

| 输入 | SHA-256 | 用途 |
|---|---|---|
| `/Users/wt/Downloads/基于 MSTA-HED 1.0 的自动化行情分析与半自动自动交易系统技术规范报告.docx` | `ccf2a7a737ccd6c1c48ca6df29ff9262bf99c45b7bc2a1ab5dcf5fefc6d1d3eb` | 最初工程规范 |
| `/Users/wt/.codex/attachments/61ebcec0-c7e5-4fb7-8d1e-166115756fcf/pasted-text.txt` | `346633ed1e6afba4b4b618b004138293b79fcefe786364da463afe444fdebca7` | 最初方法论完整论述 |
| `CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md` | `b353274dc90ae7af1493577b872032b00a845553db6f2512d6cce709cbaa86ef` | 当前 V3 审查稿 |
| `CORE_TRADING_THEORY_v2_1.md` | `2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d` | 当前 Core 理论边界 |
| `application/single_agent_research.py` | `d4b43730aa5e6c4b1d8d212c5cba9b7b75a97c8372cf3c1cbad55d1950ad12da` | v1.4 实际 Agent 合同快照 |
| `domain/research_integrity.py` | `366d17f05cd339d9675e0fadaa3dc694f2c933d005f1bff780e968aac4660cae` | 新连续核心审查时快照 |

审查还只读核对了冻结运行：

`single-agent-prospective-24h-v14-20260805t074500z`

其 checkpoint 为 `INTERRUPTED_OUTCOMES_SEALED`，只完成 Cycle 1–4，`next_cycle_index=5`；本次没有恢复、补写、迁移或读取 Cycle 5 future outcome。

## 3. 最初目标的不可丢失内核

最初 MSTA-HED 不是“指标预测器”，而是：

```text
数据有效性
→ 多周期状态识别
→ 结构与位置
→ 有限假说竞争
→ 证据持续更新
→ 条件触发
→ 期望/风险/成本判断
→ 执行与管理
→ 结果标注与校准
```

以下约束是原始方向的核心，不应因版本演进而消失：

1. 事实、派生量、推断、假说、决策和执行不能混写；
2. 路径假说、机制假说和交易假说职责不同；
3. 假说必须有身份、horizon、前提、支持、反证、硬失效、过期和触发；
4. 活跃竞争集有限，但完整 registry 可以保留低活跃和历史假说；
5. 新证据更新假说，不允许每轮从零写故事；
6. 只有触发、风险与成本同时通过的交易假说才能行动；
7. 每轮数据、证据、假说、决策、执行与结果必须可复现。

## 4. 逐项一致性矩阵

| 编号 | 最初目标 | 当前 V3 | 当前实现证据 | 裁决 | 必须纠正 |
|---|---|---|---|---|---|
| A-01 | 完整推论链分层 | 明确 OBSERVATION → DERIVED → INFERENCE → HYPOTHESIS → ACTION | v1.4 有 `analysis_trace` 类型和 evidence refs | 基本一致 | 新主路径继续机器校验，不靠文本约定 |
| A-02 | 多周期职责与状态转换 | 战略/战术/执行三层；D/L/C/F/R/K | v1.4 保存 1W/1D/4H/1H/15m 特征，但确定性状态多为 `UP/DOWN/TRANSITION`，阶段仍主要由 Agent 解释 | 部分实现 | 保存方向、阶段、状态转换依据及跨周期冲突，不只存指标 |
| A-03 | 有限但可演化的假说竞争 | 五个最小路径族，三类 optional path | 代码要求五个固定 `path_class`，只允许三个 optional class；未知机制也被 `MECHANISM_IDS` 白名单限制 | 关键偏离 | 活跃集有限，registry 与语义方向必须开放；Agent 可提新假说，内核只做结构 admission |
| A-04 | 新证据持续更新，而非重写 | belief lifecycle event + reducer | v1.4 Cycle 1–4 的 support 会变化；新 reducer 可 ADD/SUPERSEDE/EXPIRE/反证/失效 | 部分实现 | reducer 同时支持 hypothesis create/split/merge/supersede/restore，不能要求 path set 永远相同 |
| A-05 | 每条假说有完整测量合同 | V3 path card 包含机制、horizon、evidence、falsifier、expiry | 固定 path card 字段较完整 | 结构基本一致 | 将完整合同用于新建假说；增加 parent/revision/novelty/directional bias/result linkage |
| A-06 | 条件预期与结果反馈 | V3 在路径卡中有 favorable/normal/adverse | 没有独立 expectation 对象；冻结运行中检索不到 expectation/forecast ledger | 未实现 | 新增 append-only expectation ledger 与每轮 delta |
| A-07 | 完整市场信息记录 | V3 要求 source、available_at、质量、公式、UNKNOWN | v1.4 每轮六标的约 1,106 条 evidence catalog 项；Cycle 4 raw 目录有 221 个文件，包含 K 线、book、trades、OI、funding、long/short、liquidations 等及请求收据 | 已有强基础但未闭环 | 统一 snapshot schema，并绑定 raw ref/SHA、派生 lineage、缺失和 cycle evidence receipt |
| A-08 | 情绪是市场机制与反应，不是新闻正负计数 | V3 有价格与流、杠杆拥挤、事件叙事、跨市场四维 | 每维只有 `RISK_SEEKING/RISK_AVERSE/MIXED/NEUTRAL/UNKNOWN`、解释和 evidence refs | 部分实现 | 增加多轴序数值、具体 contributor 值、覆盖、分歧、跨周期冲突和 UNKNOWN 原因 |
| A-09 | Agent 发挥不可固定化的认知功能 | V3 让单 Agent 解释机制、提出 evidence event、选择动作 | exact path class、mechanism、sentiment dimension 和三路径 outcome 把 Agent 限制在固定模板 | 未最大化有效功能 | 取消语义白名单；保留结构、事实、风险和提交的确定性边界 |
| A-10 | 条件动作、仓位与风险 | V3 八类动作、CORE/TACTICAL、风险成本比较 | 动作比较存在；新 lot truth 修复正在补目标 lot、挂单、margin、leverage | 部分实现 | 完成 lot 级动作与 post-action 账户不变量 |
| A-11 | 每轮可审计、可重放 | V3 event chain、completion、review | v1.4 历史收据不绑定全部报告；新两阶段 evidence/completion 仍在接入 | 部分实现 | market/sentiment/hypothesis/expectation 全部进入 evidence receipt，review 只读收据来源 |
| A-12 | 结果反馈与校准 | V3 明确 local PASS 不等于市场有效 | 只有中断的四周期冻结前缀，无 fresh unseen terminal、无校准 | 数据不可判 | 保持 UNKNOWN；本地 fixture 只证明结构，不宣称预测或盈利 |

## 5. 当前系统究竟有多少“动态能力”

### 5.1 已真实存在

冻结 v1.4 的以下内容确实随周期变化：

- 每轮重新采集并保存 point-in-time 市场信息；
- evidence catalog 的具体值、数据质量和来源版本变化；
- 假说的支持等级与 lead/runner 排序变化；
- 四个情绪维度的状态与解释变化；
- observation request 可从一条增长到两条并被带入下一轮；
- accepted episode、lot、动作和风险状态持续存在。

例如 SNDK 的 `NORMAL_PULLBACK` 从 Cycle 1 的 `DOMINANT` 变为 Cycle 4 的 `SUPPORTED`，`EXHAUSTION_OR_FAILURE` 从 `PLAUSIBLE` 变为 `DOMINANT`；这证明更新不是完全静态。

### 5.2 尚未真实存在

六个标的在四轮中始终恰好保留同五类路径：

`TREND_CONTINUATION / NORMAL_PULLBACK / EXHAUSTION_OR_FAILURE / RANGE_REFORMATION / OTHER_OR_UNKNOWN`

原因不是市场四轮恰好没有新方向，而是代码要求：

- `REQUIRED_PATH_CLASSES` 必须全部出现；
- path class 只能来自固定集合；
- mechanism 只能来自固定 `MECHANISM_IDS`；
- 旧 path class 的 `path_id` 必须延续，旧 class 不允许消失；
- 新连续 reducer 要求本轮 `path_ids` 与上一轮完全相同；
- action evaluation 永远只接收 lead、runner-up、residual 三条路径。

所以当前能力应叫“**固定槽位内动态更新**”，不能叫“开放式动态假说发现”。

## 6. Agent 的正确最大化方式

“最大化 Agent”不等于把数字、风险、状态提交或订单权限交给 Agent。正确边界是最大化其**认知自由度**，同时保持事实与执行确定性。

### Agent 应拥有

- 发现当前 registry 未覆盖的新路径或机制；
- 创建新假说并说明与旧假说的差异；
- 提出 split、merge、supersede、restore 和失效建议；
- 为每条假说提出可证伪 expectation；
- 解释多周期、流、杠杆、流动性、事件和跨市场之间的机制联系；
- 请求真正有区分力的新观测；
- 在 sealed 可行行动集合中选择，并解释机会成本。

### 确定性内核必须拥有

- point-in-time、source、raw SHA、数据质量与 UNKNOWN；
- 数值和派生量复算；
- hypothesis/expectation 的 ID、revision、父子关系、状态转换和去重；
- evidence dependency 去相关与 lifecycle replay；
- lot、订单、保证金、杠杆、风险、成本与 hard veto；
- event order、write-once artifacts、receipt、checkpoint 和权限。

这使 Agent 能提出新知识，但不能伪造事实、静默覆盖历史或绕过风险。

## 7. 动态假说 registry 纠正合同

### 7.1 假说对象

每个假说至少包含：

- `hypothesis_id`、`revision`、`hypothesis_type=PATH|MECHANISM|TRADE`；
- `directional_bias=LONG|SHORT|BIDIRECTIONAL|NEUTRAL|UNKNOWN`；
- `family_label`，允许 Agent 新建，不做语义白名单；
- `parent_hypothesis_ids`、`supersedes_ids`、`derived_from_expectation_ids`；
- `created_at`、`updated_at`、`horizon`、`timeframe_scope`；
- `premises`、`expected_sequence`、`support_rules`、`oppose_rules`；
- `hard_falsifiers`、`expiry`、`trade_triggers`、`forbidden_conditions`；
- `active_evidence_ids`、`support_level`、`state`、`limitations`；
- `novelty_reason` 与 `agent_rationale`。

### 7.2 允许的 delta

`CREATE / REVISE / PROMOTE / DEMOTE / SPLIT / MERGE / SUPERSEDE / INVALIDATE / EXPIRE / ARCHIVE / RESTORE`

每次 delta 都绑定 prior registry digest。确定性 reducer 检查：

- CREATE 的 ID 不存在且合同完整；
- REVISE 不改变 identity，只增加 revision；
- SPLIT/MERGE 保留父子 lineage，旧对象进入 SUPERSEDED；
- INVALIDATE 必须命中事前登记的 hard falsifier；
- EXPIRE 必须到期；
- RESTORE 只能用于可解释的新 evidence lineage，不能抹掉历史失效；
- 任何删除都变成显式状态，不物理删除对象。

### 7.3 有限竞争与允许新增并不冲突

- registry 可以持续增长；
- 每轮参与 action ranking 的 active path 保持有限；
- operational comparison 至少包含 lead、runner-up 和 OTHER；
- 新假说可以进入 active set 并替代旧成员；
- 超出 active budget 的假说进入 DORMANT/WATCH，而不是丢失；
- 若新增内容与现有合同在语义和证据 lineage 上重复，确定性 admission 拒绝为 `DUPLICATE_HYPOTHESIS`。

## 8. expectation ledger 纠正合同

“预期不断增加”不能实现成无限文本堆积。应实现为 append-only、可关闭的条件预期账本。

每条 expectation 至少包含：

- `expectation_id`、`revision`、`hypothesis_id`；
- `created_at`、`observation_start`、`observation_deadline`；
- `if_conditions`；
- `expected_observations`，每项含 metric、direction/range、timeframe、source requirement；
- `falsifying_observations`；
- `evidence_sufficiency=LOW|MEDIUM|HIGH|UNKNOWN`，不是概率；
- `status=OPEN|FULFILLED|PARTIAL|FALSIFIED|EXPIRED|CANCELLED`；
- `result_evidence_refs`、`closed_at`、`result_note`；
- `deduplication_key` 与 parent expectation。

每轮先用当前 admitted market facts 评估旧 expectation，再允许 Agent 新建或修订未来 expectation。关闭不会删除历史；同义重复不能靠换措辞无限增加。

## 9. 市场信息记录合同

每轮每标的生成一个 `market_information_snapshot`，至少覆盖：

1. 价格、收益、区间位置和结构；
2. 趋势效率、波动和状态阶段；
3. 成交量、主动买卖和成交推进效率；
4. 订单簿、spread、depth、impact 与连续性；
5. OI、funding、basis、long/short proxy；
6. liquidation（缺失必须 UNKNOWN）；
7. 跨市场、行业和宏观；
8. 公开新闻、事件和事件后反应；
9. 资产/合约规则、交易时段和映射；
10. 数据质量、缺失、陈旧和冲突。

每个 fact/measure 行必须含：

`fact_id / kind / category / metric / value / unit / symbol / timeframe / window / source_ref / raw_ref / raw_sha256 / observed_at / available_at / quality / coverage / lineage / transform / limitations / missing_reason`

原始观测与派生量必须分行；原始 body、请求收据和派生 snapshot 分别保留物理 SHA 与语义 digest。

## 10. 市场情绪量化标准

### 10.1 量化原则

情绪是多维状态向量，不是一个未经校准的“70 分”或多空概率。每个维度使用序数 `-2/-1/0/+1/+2`，但必须同时保存该维度的轴语义；不同轴不允许直接相加成伪精确总分。

每个维度记录：

- `axis` 与 `ordinal_value`；
- `state_label`；
- `contributors`：fact ID、具体值、规则、方向和 dependency group；
- `supporting_count / opposing_count / unknown_count`；
- `required_group_count / observed_group_count / coverage_ratio / coverage_label`；
- `conflict_state=ALIGNED|MIXED|CONTRADICTORY|UNKNOWN`；
- `timeframe_states` 与跨周期冲突；
- Agent 机制解释、局限和下一项区分性观测。

### 10.2 最小十维向量

| 维度 | `-2` 方向 | `0` | `+2` 方向 | 典型输入 |
|---|---|---|---|---|
| `PRICE_DIRECTIONAL_PRESSURE` | 强空向推进 | 混合/平衡 | 强多向推进 | 结构、CLV、VWAP、效率、相对收益 |
| `STRUCTURE_PERSISTENCE` | 下行结构高度持续 | 无清晰持续 | 上行结构高度持续 | 多周期高低点、突破/回踩、状态阶段 |
| `PARTICIPATION_AND_FLOW` | 主动卖压占优 | 双向/无优势 | 主动买盘占优 | taker flow、CVD proxy、RVOL、推进效率 |
| `CROWDING_DIRECTION` | 空头拥挤 | 不可识别/均衡 | 多头拥挤 | funding、basis、账户/仓位比及局限 |
| `LEVERAGE_CHANGE` | 强制/快速去杠杆 | 稳定或不可识别 | 风险敞口健康扩张 | OI、liquidation、funding、basis |
| `LIQUIDITY_RESILIENCE` | 脆弱/冲击后不恢复 | 一般/未知 | 深度与价差快速恢复 | spread、depth、impact、gap recovery |
| `VOLATILITY_STRESS` | 极端压力与失序 | 常态 | 平稳且可承受 | ATR/RV 分位、跳空、尾部冲击；本轴正值代表健康而非看多 |
| `CROSS_MARKET_RISK_APPETITE` | 风险规避 | 混合 | 风险寻求 | BTC/行业/宏观相对强弱与同步性 |
| `EVENT_REACTION` | 事件后反应偏空/利好失败 | 无结论 | 事件后反应偏多/利空失败 | 异常收益、event VWAP、持续性、来源质量 |
| `TIMEFRAME_COHERENCE` | 多周期空向一致 | 周期冲突 | 多周期多向一致 | 1W/1D/4H/1H/15m 状态与晋级条件 |

### 10.3 聚合边界

- 同一 dependency group 只能贡献一次；
- `UNKNOWN` 不得当 `0`；
- coverage 低时不能输出强标签；
- 正负 contributor 同时存在时必须保留分歧；
- `LIQUIDITY_RESILIENCE` 和 `VOLATILITY_STRESS` 等健康轴不能与 long/short 轴机械求和；
- Agent 可给出 overall operational synthesis，但必须引用完整向量，确定性代码不把它转换为概率或下单信号。

## 11. 纠正后的每轮最小工件

```text
market_information_snapshot
→ sentiment_state
→ hypothesis_registry_delta + accepted_hypothesis_registry
→ expectation_ledger_delta + accepted_expectation_ledger
→ belief_event_delta + accepted_belief_state
→ action_evaluation_set
→ action_selection / risk / decision / accepted state / action receipt
→ comparator / review_source
→ cycle_evidence_receipt
→ report / due review
→ completion_receipt / checkpoint advance
```

这些工件均必须有真实文件、物理 SHA、语义 digest、actor、point-in-time boundary 和 write-once event。

## 12. 当前禁止结论

本审查只证明当前系统的结构事实：

- 不能据此宣称新动态理论已实现；
- 不能据此宣称情绪量化有效；
- 不能据此宣称 Agent 能发现真实市场机制；
- 不能据此宣称预测有效、成本后盈利或跨 regime 稳健；
- 不能恢复 v1.4、automation、paper/live、账户、订单或资金操作。

下一步只能在全新本地合成 fixture 中证明合同、状态与收据闭环，然后继续保持 market evidence 为 `UNKNOWN_NOT_EVALUATED`。

## 13. 纠正结果

基线审查完成后，以下缺口已在新四层主路径中关闭：

| 基线缺口 | 纠正结果 | 本地证据 | 仍未知 |
|---|---|---|---|
| 固定五类路径、不能新增方向 | 开放语义动态 registry；支持 create/revise/promote/demote/split/merge/supersede/invalidate/expire/archive/restore；活跃集合有限但 registry 可增长 | 四周期 fixture 在 Cycle 2 创建 `event-liquidity-vacuum-reversal`，Cycle 3 晋级 | 新方向是否对应真实市场机制 |
| 无 expectation ledger | 条件、窗口、证伪、结果、revision history、显式关闭和确定性语义去重 | Cycle 1 创建、Cycle 2 部分更新、Cycle 3 `FULFILLED` 关闭，Cycle 4 新增第二条 | 预期是否有预测力或校准价值 |
| 市场信息未统一绑定 | 十类 `market_information_snapshot`，同时保存 RAW/DERIVED、source/time/lineage/quality/UNKNOWN | 每轮进入 evidence receipt；合成 liquidation 缺失保持 UNKNOWN | 真实数据源覆盖率与可靠性 |
| 情绪只有文字标签 | 十维 `-2..2` 序数向量，保存 contributor、dependency group、coverage、conflict、timeframe 和限制；不生成总分或概率 | 四轮 sentiment state 均与 market snapshot digest 绑定 | 维度与规则的真实市场效度 |
| Agent 功能受固定槽位压缩 | Agent port 负责开放机制、假说/预期 delta、解释、候选和封存后选择；内核负责 PIT、去重、reducer、lot/risk/event/commit | proposal 无 selection；完整 evaluation 封存后才调用 deliberation | 真实 Agent 是否能稳定发现有用机制 |
| review 指标可由调用方注入 | 四份 evidence receipt 的全部来源物理 SHA 与语义 digest 通过后，repository 才加载绑定 review row | 物理篡改测试失败关闭 | 指标本身是否足以评价真实策略 |

真实 CLI 的全新四周期合成 chronology 已完成，且未访问网络、模型、automation、账户、订单或资金。这个结果把审查裁决更新为：

`ORIGINAL_DIRECTION_RESTORED_IN_LOCAL_CONTRACTS / OPEN_DYNAMIC_HYPOTHESIS_PROVEN_SYNTHETICALLY / REAL_MARKET_VALIDITY_UNKNOWN_NOT_EVALUATED`

因此，原审查第 12 节的禁止结论继续有效；已经关闭的是本地结构和流程缺口，不是市场证据缺口。

## 14. 动态开放与完整推论追加确认

后续用户确认“动态性与开放性是主导”后，系统进一步完成两项收口：

1. Agent 的完整 PIT snapshot、上一 registry/ledger/belief/accepted state、portfolio truth、risk policy、合法动作和能力边界现在封存在单一 `AgentContext v2`；实际传入 adapter 的对象与 `agent_context_digest` 完全一致，不再存在 digest 外附加输入；
2. 每轮新增 `public_epistemic_inference_trace`，逐条绑定支持、反证、UNKNOWN、金融机制、假说/预期影响、动作含义、失效条件、局限和下一观察；该工件明确不保存私有 chain-of-thought，并由 evidence receipt、accepted state、report、review source 和四周期重放共同验证。

开放性与 Core v2.1 的有限机制边界按层分离：已批准 primitive mechanism library 继续有限且不可由运行时 Agent 改写；研究候选 registry 的语义开放、历史可增长；ACTIVE budget 与 lead/runner-up/OTHER 只限制当轮注意和动作比较。完整裁决见 `DYNAMIC_OPEN_AGENT_CORE_CONFIRMATION_2026-08-06.md`。

更新后的本地结论为：

`ORIGINAL_DIRECTION_RESTORED / OPEN_CANDIDATE_RESEARCH_WITH_FINITE_OPERATIONAL_WINDOW / PUBLIC_INFERENCE_SOURCE_BOUND / REAL_MARKET_VALIDITY_UNKNOWN_NOT_EVALUATED`
