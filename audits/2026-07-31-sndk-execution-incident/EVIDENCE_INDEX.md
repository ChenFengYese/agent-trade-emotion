# SNDK 交易 Agent 执行事故审计证据索引

审计日期：2026-07-31（Asia/Shanghai）  
审计对象：`msta-paper-20260729T212716Z-87cc29bb`  
审计边界：cycle-0001 至 cycle-0024 的已提交历史；cycle-0025 仅作未提交边界证据  
分支 / HEAD：`codex/s0-research-foundation` / `7ca3fc4f99a57f98217e703f222b295653ace87e`

## 1. 不可后见与只读基线

本审计没有修改理论、提示词、运行代码、阈值、自动任务、组合状态、历史周期、账本或事务工件。只新增需求记录、审计报告和本索引。

审计开始时的受保护快照：

| 对象 | SHA-256 |
|---|---|
| `.runtime/theory-paper-v1/current` 335 个文件的排序逐文件摘要聚合 | `2e228524384f91878db76d5d18b7d08d23702550f8ea71cbcc1aea03017b0134` |
| `CORE_TRADING_THEORY_v2_1.md` | `2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d` |
| `THEORY_PAPER_AGENT_GUIDE.md`（manifest 冻结值） | `0c233562da6425900b303fd4710f85c4f5eb5248c25c5635d7f286bf3837b223` |
| `config/theory_paper_automation_prompt.v1.md` | `4866db345b071f4634855de10273df656c20f25053db2b05503a6a1d2e4dd517` |
| `trade_system/theory_paper/theory.py` | `eccf935f8cfa99c01c5d9a137ce5c1e60725333797cb20764f2e7b65454bd4c6` |
| `trade_system/theory_paper/portfolio.py` | `c9478e22b1c348453091178478833d156d68204ff95ee62004bac8b34f47fe92` |
| `trade_system/theory_paper/experiment.py` | `26c136d11cb2a559e06d63c94417b0775064d0d0dd916d2301cdfa81f1870b55` |
| `/Users/wt/.codex/automations/automation-2/automation.toml` | `2e8cd2daffe60e44181086ae3e9440b60444e799b7fbc22fa41bb3d95eaa3228` |

运行事务链在审计前只读状态检查中有效：53 条 ledger events，transaction chain valid。cycle-0025 只有冻结 `market/news/analysis/decision-template`，没有 `decision.json`，不得纳入已发生动作或收益。

## 2. 点时信息边界

- 每轮事实截止点：对应 `cycles/cycle-NNNN/analysis.json#/decision_at`。
- 市场观测：`analysis.json#/symbols/*/measurement_snapshot/observed_at`，必须不晚于 `decision_at`。
- 行情原始快照：`cycles/cycle-NNNN/market.json`。
- 决策：`cycles/cycle-NNNN/decision.json#/validated_decision`。
- 模拟执行：`cycles/cycle-NNNN/decision.json#/execution/results`。
- 组合与假说状态：`state.json#/portfolio`、`state.json#/open_hypotheses`。
- 审计对 cycle-0001 至 cycle-0025 的 market、news 和 analysis 时间字段做递归检查，发现晚于本轮 `decision_at` 的字段数为 0。
- cycle-0022 至 cycle-0024 缺独立 `agent-decision.json`，但提交事务中的规范化权威决策仍保存在 `decision.json#/validated_decision`。这是“原始作者输入留存缺口”，不是权威决策丢失。

## 3. 逐轮证据路由

审计报告的 24 行时间线每一行均由同编号工件合成：

| 字段 | 权威位置 |
|---|---|
| 数据截止时间 | `analysis.json#/decision_at` |
| 参考价 | `analysis.json#/symbols/{SNDK}/measurement_snapshot/reference_price` |
| 1D/4H/1H/15M | `analysis.json#/symbols/{SNDK}/multi_scale_state_belief/role_states` |
| 战略/运营趋势 | `analysis.json#/symbols/{SNDK}/multi_scale_state_belief/operational_bias` |
| 市场阶段 | `analysis.json#/symbols/{SNDK}/structural_position/operational_phase` |
| 当轮假说及支持等级 | `decision.json#/validated_decision/symbol_decisions/{SNDK}/selected_phi_id` 与同轮 `analysis.json#/symbols/{SNDK}/phi_competition/hypotheses` |
| 建议动作、触发条件、证据引用 | `decision.json#/validated_decision/symbol_decisions/{SNDK}` |
| 实际动作 | `decision.json#/execution/results` |
| 总 SNDK 仓位 | 提交后的 `state.json#/portfolio/lots` 历史及各轮中文 write-once sidecar |
| 核心/战术仓位 | **未记录**；历史 schema 没有该分类，禁止事后分配 |

时间线所用文件模式：

- `.runtime/theory-paper-v1/current/cycles/cycle-0001/analysis.json` 至 `cycle-0024/analysis.json`
- `.runtime/theory-paper-v1/current/cycles/cycle-0001/decision.json` 至 `cycle-0024/decision.json`
- `.runtime/theory-paper-v1/current/reports/zh/*cycle-0001*_zh_v2.md` 至 `*cycle-0024*_zh_v2.md`

## 4. 关键事故节点

### 4.1 最早潜在根因：cycle-0001 已存在的无状态循环

- `experiment.py:970-978` 调用 `build_cycle_analysis` 时只传当轮 market、news、portfolio 和 config；不传 `state.open_hypotheses`、上一轮决策或 review update。
- `theory.py:1152-1197` 把完整 portfolio 压缩为 digest、数量和少量 ID，主动移除 lot 父假说、止损、目标、失效条件及再入场语义。
- `theory.py:1200-1246` 的分析入口没有 prior hypothesis、prior decision、invalidator 或 pending observations 参数。
- `experiment.py:1158-1176` 每轮创建新的 `cycle-NNNN:SNDKUSDT` 假说实例，而非更新同一战略实例。
- `experiment.py:1588-1611` 的八轮复盘只剪枝假说，不把结论回灌下一轮。

这证明“状态被保存但没有进入下一轮决策函数”，不是泛泛的模型谨慎。

### 4.2 首次可观察偏离：cycle-0011

- cycle-0010：`PHI_RANGE / WEAK / ADD_LONG`，提交后 SNDK 名义约 494.93496832 USDT。
- cycle-0011：切换为 `PHI_DOWNWARD_CONTINUATION / MODERATE / KEEP`。
- 证据：4H 与 1D `DOWN`（结构/战略背景），1H `RANGE`、15M `DOWN`、短窗负压力（战术/确认）；没有 typed transition receipt 说明为何上一 `PHI_RANGE` 丧失战略权。
- cycle-0011 未立即减仓，因此这是“观点与既有多头仓位语义分裂”的首次外显节点，不是首次损益动作。

### 4.3 首次策略仓位减少：cycle-0015

- `decision.json#/execution/results` 中 `fill-000016`：lot-000009 以冻结目标 1069.69 自动卖出。
- 净已实现收益 13.75498250 USDT。
- 信号类别：预注册目标/风险管理执行，不是战略假说失效，也没有“战术减仓”标签。

### 4.4 首次清空 SNDK：cycle-0016

- `analysis.json`：参考价 1215.70761844；1D/4H DOWN、1H TRANSITION、15M UP。
- `decision.json#/validated_decision/symbol_decisions/{SNDK}`：`EXIT`，原因码 `EXISTING_TARGET_EXCEEDED_FULL_PROFIT_EXIT_REQUIRED`。
- 原 lot-000007 的父假说仍是 `PHI_RANGE`；冻结目标 1124.99；实际 `fill-000021` 以 1215.46447692 全量平仓，净收益 43.55852512 USDT。
- 当轮文本明确“不重启已关闭 lot”，且没有 re-entry contract。
- 信号类别：冻结目标执行。它对冻结 v1 的 `T-023` 忠实，但在用户要求的“战略状态—战术退出—再入场”治理中缺少必要语义。

### 4.5 首次 SNDK 空仓后不重入：cycle-0017；首次方向/动作断裂：cycle-0019 与 cycle-0021

- cycle-0017 首次在 SNDK 为 0 仓位时 `ABSTAIN`。
- cycle-0019 已选择 `PHI_UPWARD_CONTINUATION / WEAK`，仍因多头几何被拒而 `ABSTAIN`。
- cycle-0021 已达到 `PHI_UPWARD_CONTINUATION / MODERATE`，1H 与 15M 均为 UP，仍 `ABSTAIN`。
- cycle-0017 至 0024 的多头 support-retest 几何均远低于现价且 target 为 `UNKNOWN`；validator 要求当轮 `RESEARCH_READY` 几何、现价位于 entry zone、精确 stop/target 和净盈亏比至少 1.5，故上涨事实不能编译为合法多头动作。
- cycle-0022 是全组合最后一项 SOL 仓位退出后“整个组合空仓”的节点，不是 SNDK 首次空仓节点。

“首次在原超跌反弹假说仍满足时拒绝重入”无法按历史工件唯一识别：正式对象叫 `PHI_RANGE`，不是开放式“超跌反弹”；cycle-0006 的冻结路径在 2026-07-30T10:43:23Z 到期，目标 1124.99，review-002 将其评为 `SUPPORTED_AT_EXPIRY`。它不是 cycle-0017 后仍开放的持久战略假说。最近似、可证的节点是 cycle-0019/0021 的上涨方向与动作断裂。

## 5. 理论与实现证据

### 冻结理论

- `CORE_TRADING_THEORY_v2_1.md:150-170`：极值只触发观察；动作必须冻结目标、止损和 horizon；`T-023` 禁止事后移动 target/horizon。
- `:345-353`：时间尺度有分工，小尺度不得直接外推数小时 alpha。
- `:381-399`：episode 应有连续状态和滞回。
- `:415-421`：V1 不交易趋势延续；主动放弃趋势延续是允许输出。
- `:427-442`：完整动作契约包含 barriers、horizon 和 exit policy，但文档明确这不是当前实现已获得的全部权限。
- `:491-501`：新增风险必须全部闸门通过，否则 `ABSTAIN`。

因此，冻结理论事前产生了可获利的 support-retest/range-reversion 候选，但没有定义用户现在要求的“长期核心仓位 + 战术仓位 + 强制再入场合同”。cycle-0016 目标退出不能被后见上涨改判为违反冻结 v1。

### 决策编译与校验

- `theory.py:1261-1407`：每轮模板从空状态生成，没有 prior instance、revision、战略状态或 re-entry 字段。
- `theory.py:1959-2036`：新增风险只接受当轮研究就绪几何、精确 entry/stop/target/notional 和成本后 RR。
- `theory.py:2040-2067`：规范化决策字段没有跨轮状态。
- `theory.py:2151-2168`：`CLOSE` schema 不接受 action intent 或 re-entry contract。
- `theory.py:2208-2323`：validator 只验证新增风险与同轮假说/几何自洽。
- `theory.py:2342-2406`：全组合 inactivity gate 可由 typed `NOT_ACTIONABLE` 满足。

### 执行与调度

- `portfolio.py:1897-1948`：保护障碍只在新闭合 1H bar 上解析。
- cycle-0016 决策时标记价已高于目标，但最新闭合 1H high 尚未命中；15M 已命中。Agent 约 15 分钟后用当前标记显式 `CLOSE`，说明 1H 屏障时钟与 15M/实时执行时钟不一致。
- automation：`RRULE:FREQ=HOURLY;INTERVAL=1`，当前 `PAUSED`。
- `state.json#/completed_hour_slots` 缺 2026-07-30T07:00Z 和 18:00Z。
- `experiment.py:858-869` 只校验当前小时属于 expected slots，不要求前一槽已完成或补跑。
- `experiment.py:1414-1429` 按 cycle 数触发“八小时复盘”；假说却按八个真实小时到期，漏槽后两种时钟漂移。
- cycle-0010 到 0011 间隔 2.069 小时；它与首次假说切换同窗，但工件不能证明因果，只能列为放大因素。
- 当前控制面存在双重状态源：automation TOML 为 `PAUSED`，但
  `state.json#/status` 仍为 `ACTIVE`、`pending_decision_cycle=25`。手工提交入口只
  检查 runtime state；这不是既往 SNDK 空仓的原因，却意味着“暂停/终止”尚未形成
  单一机器授权状态。
- manifest 绑定的基础 v1 prompt 摘要为
  `4866db345b071f4634855de10273df656c20f25053db2b05503a6a1d2e4dd517`
  （3655 bytes），实际 automation prompt 还拼接了中文记录附加要求，完整 prompt
  为 8726 bytes、SHA-256
  `3651f7d5c0623cd4b96d1dd4a67b42d70765569060ee7bbf4eae83d7d748853f`。
  附加要求明确不改变交易决策，故没有证据认定它造成 SNDK 事故；但完整运行提示
  没有被 manifest 精确绑定，是可追溯性缺口。

## 6. 收益账本

### 6.1 实际 SNDK

| lot | 归因 | 入场 → 出场 | 毛已实现 PnL | 费用 | 净已实现 PnL |
|---|---|---:|---:|---:|---:|
| lot-000001 | EXOGENOUS | 1125.00000000 → 998.39039300 | -56.27093644 | 0.22186453 | -56.49280098 |
| lot-000006 | STRATEGY | 998.16606614 → 1018.61432400 | 5.12248117 | 0.25261124 | 4.86986993 |
| lot-000007 | STRATEGY | 1034.18533186 → 1215.46447692 | 43.83049036 | 0.27196525 | 43.55852512 |
| lot-000009 | STRATEGY | 1013.23260600 → 1069.69000000 | 13.93280406 | 0.17782156 | 13.75498250 |
| **合计** |  |  | **6.61483915** | **0.92426258** | **5.69057657** |

- 策略归因净收益：62.18337755 USDT。
- 外生初始仓位净收益：-56.49280098 USDT。
- cycle-0024 时 SNDK 已全部平仓，未实现 PnL 为 0。
- 已估滑点 0.41847656 USDT 已体现在成交价中，不得再次扣除。
- funding：`NOT_SIMULATED_V0_1`，不可伪造为 0。

### 6.2 持有基准与机会差

以 lot-000007 的真实数量、真实入场和 cycle-0024 已提交参考价 1342.06 做同风险口径：

- 持有至 cycle-0024 的 mark-to-market 净值：74.31430265 USDT（只扣已发生入场费）。
- 假设在 cycle-0024 按冻结 2 bps 滑点和 0.05% 退出费平仓：74.08719257 USDT。
- 相对实际 cycle-0016 退出的机会差：mark 口径 30.75577753 USDT；假设平仓口径 30.52866745 USDT。

上述是反事实机会差，**不是实际亏损**。

初始外生 500 USDT 买入并持有至 cycle-0024 的假设退出净收益为 96.05364098 USDT，但其入场时点、风险和策略归因不同，只能作非风险匹配参考。

## 7. 冻结反事实识别边界

| 路径 | 可识别性 | 结果 |
|---|---|---|
| 原 Agent 实际路径 | 精确 | cycle-0016 退出；cycle-0017 至 0024 空仓；lot-000007 净 43.55852512 |
| 严格机械执行冻结 v1 动作契约 | 精确控制 | 不做 cycle-0016 的显式市价平仓时，下一轮 1H barrier 会按 1124.99 target 平仓；净 21.77573671。冻结 v1 也不会继续持有趋势 |
| 严格保持“战略超跌反弹” | **历史规则不可识别；只可做敏感性** | 历史没有持久战略对象、核心仓位比例或重入规则。若额外假设 lot-000007 全量作为核心持有至 cycle-0024，则 mark 净 74.31430265；该值不能冒充原理论结果 |
| 仅战术减仓 | **参数不可唯一识别** | 历史没有 tactical fraction。若 cycle-0016 减仓比例为 α，则 cycle-0024 mark 净值为 `74.31430265 - 30.75577753 × α`；假设平仓净值为 `74.08719257 - 30.52866745 × α` |

三条路径均只在每个时点使用当时已冻结的输入；cycle-0024 终值只用于统一事后评价，不作为更早动作的输入。lot-000007 从入场到 cycle-0016 的局部 mark-to-market 最大回撤约 5.24005668 USDT；全量持有敏感性在 cycle-0016 后价格单调上升，因此同一局部口径不增加最大回撤。严格 v1 barrier 控制因 1H 执行滞后，从 cycle-0016 标记峰值到下一轮冻结 target 成交产生约 21.98851651 USDT 的标记到已实现回撤；这反映执行时钟，不是市场先验。

## 8. 数据质量与未知项

- 所有轮次的点时边界检查通过。
- SNDK 典型覆盖率 93.33%。
- 强平窗口 F 为 UNKNOWN；严格补单韧性序列 R 为 UNKNOWN；1W 历史不足。
- 这些缺口限制参与者机制判断，但 cycle-0016 的退出由冻结目标触发，cycle-0017 后的 abstention 由几何与 validator 触发，故数据缺口不是主因。
- 没有保存每轮模型实际读取文件清单、token 数或截断位置，因此不能声称发生了语言模型上下文截断。可证的是结构化接口本身已经压缩并丢弃跨轮语义。

## 9. 责任结论的证据等级

| 裁决 | 证据等级 | 说明 |
|---|---|---|
| 理论被本例否定 | 不支持 | `PHI_RANGE` 在冻结期限内获支持并达到目标；单例也不能证明稳定预测能力 |
| 理论/产品目标存在范围缺口 | 直接 | V1 明示不交易趋势延续，且无核心/战术/重入状态 |
| Agent 实施失败 | 直接 | 每轮重算、当前自洽校验、无再入场编译 |
| 状态管理失败 | 直接 | 历史保存但不输入下一轮；每轮新实例；review 不回灌 |
| 数据失败是根因 | 否 | 点时数据完整到足以解释动作；缺失项是放大不确定性的次因 |
| 定时系统是根因 | 部分 | 漏槽、1H barrier、cycle/hour 漂移会放大，但不能单独解释永久空仓 |

## 10. 不实施的最小修复边界

最小修复不是改阈值或延长提示词，而是把一个不可绕过的持久对象接入现有提交门：

1. `StrategicHypothesisState`：同一 episode 只有一个版本链，保存 horizon、硬失效、待验证项及当前状态；
2. lot 绑定 `CORE/TACTICAL` 与动作意图，目标/风险退出不自动等于战略失效；
3. 非战略失效退出必须同时生成 `ReentryContract` 和最迟复核时钟；
4. 下一轮强制消费上一 accepted state，只允许输出 delta/transition receipt；
5. inactivity 与机会差按 symbol 计量，其他标的成交和退出成交不得重置 SNDK 时钟；
6. hourly scheduler 只负责唤醒；战略审查绑定闭合 4H/1D bar 或合格事件，并补报漏槽；
7. breakout 需条件入场或事件驱动执行能力，否则明确承认小时采样无法覆盖越过静态 zone 的路径。

本次只提交方案，不实施。
