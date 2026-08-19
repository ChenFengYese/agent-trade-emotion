# 多时间尺度决策治理审查 v1

## 1. 结论

当前系统已经有“多周期按角色读取、低周期不得投票覆盖父级、风险与 PnL 单独记录、原 thesis 不回写”等正确原则，但这些原则没有贯穿到最终决策校验、组合动作、跨周期假说实例和复盘评价。

因此，用户复盘中指出的漏洞在当前 v1 纸面运行时真实存在：

1. 低周期不能机械改写 `4h operational_bias`，但 Agent 可以任选注册 PHI，并用独立的 1H 几何形成与父级不一致的新风险动作；
2. 风险退出不会改写既有 immutable decision，但退出/减仓周期仍会新建假说样本，动作、当前观点与原持仓父假说可能共用同一组字段；
3. v1 schema 不仅缺少再入场合同，而且会把新增的 `action_intent`、`reentry_contract` 字段判为未知字段；
4. “八小时复盘”按八个 cycle 计数，不证明小时槽连续；所有 horizon 共用一次命中式 `SUPPORTED_ACTIVE` 逻辑；
5. PnL 不改变 theory/method score 这一条有运行时保护，但一小时价格/方向谓词仍可成为八小时假说的支持，因此仍可能产生“局部结果确认长期判断”的语义泄漏。

审查结论不是“理论完全无效”。它说明现有分析层的正确原则还没有形成分析与动作之间不可绕过的决策控制层。

## 2. 冻结范围

- cwd：`/Users/wt/Documents/agent-trade-emotion`
- branch：`codex/s0-research-foundation`
- HEAD：`7ca3fc4f99a57f98217e703f222b295653ace87e`
- 活动 run：`msta-paper-20260729T212716Z-87cc29bb`
- 审查冻结点：17 个 analysis cycle、16 个完整 decision cycle、2 个 review；cycle-0017 当时只有 analysis transaction，不能当作完整决策周期
- 当前 run 仍为 `ACTIVE`、`PAPER_ONLY`，不具备凭据、私有 API 或实盘下单能力
- 工作树原本已有大量修改和未跟踪文件；本报告绑定当前物理快照，不把结论外推为某个干净 release

本次只审查当前权威链：

`Core 理论 → research-system 静态契约 → theory-paper v1 分析/校验/组合/复盘 → v1/v2 prompt → 真实冻结周期`

旧实验、未激活 challenger 和纯合成 fixture 只用于确认边界，不被当作当前运行时能力。

## 3. 评级定义

| 评级 | 含义 |
|---|---|
| `RUNTIME_ENFORCED` | 当前实际调用链会失败关闭，调用者不能只靠改叙事绕过 |
| `CONTRACT_ONLY` | 文档或静态契约写明规则，但当前 paper runtime 不消费该契约 |
| `PARTIAL` | 部分字段或局部不变量已执行，但不足以封闭用户指出的完整路径 |
| `MISSING` | 当前权威链没有对应对象、字段或状态机 |
| `BYPASSABLE` | 有相近声明或对象，但存在已复现的合法输入路径可以绕过 |

## 4. 审查矩阵

| 治理要求 | 评级 | 已有保护 | 仍存在的漏洞 |
|---|---|---|---|
| 多时间尺度有序角色 | `PARTIAL` | Core §6.1 和 §16.7 明确三层/有序 role profile；`theory.py:444-484` 固定 1D/4H/1H/15M 角色并声明低周期不能覆盖父级 | 声明只存在于分析对象；没有最终 PHI、方向、几何与父级的不可绕过绑定 |
| 信号分为结构、确认、战术、噪音 | `MISSING` | 现有 measurement/state/PHI 分层提供了语义基础 | 决策 schema 没有信号类别、权限、持续窗口、独立确认、正常波动越界或改变的核心前提 |
| 低周期跨层升级 | `BYPASSABLE` | Core 要求 observation → state → mechanism → path → permission | `validate_decision` 只验证 PHI 在注册表；没有 `SignalUpgradeReceipt` 或 reducer |
| A/B/C/D 战略状态机 | `MISSING` | 有 episode、path、position、observation 等其他状态机 | 它们不是 `A_VALID / B_TACTICAL_DISTURBANCE / C_CHALLENGED / D_INVALIDATED`，也没有对应合法转换表 |
| 观点与风险动作隔离 | `PARTIAL` | portfolio context 不直接改 measurement；自动 stop/target 保留 lot 归因；旧 decision 不回写 | 所有 symbol decision 不论 KEEP/EXIT/风险维护都进入 `open_hypotheses`；CLOSE 的 PHI/归因可由调用者填写 |
| 固定战略审查时钟 | `MISSING` | 有 wall-clock、expiry 和每八 cycle review | 没有“4H/1D 收盘、expiry、合格重大事件”专属战略入口；review due 只计算 cycle 数 |
| 战术退出附再入场合同 | `MISSING` | 风险门会限制重新开仓规模 | 没有 prior exit、原假说实例、结构重置、冷却/时间条件、分阶段恢复、最大复审时点或取消条件 |
| 三本独立账本 | `MISSING` | 有 ledger、open_hypotheses、portfolio/fill 等分散对象 | 没有假设、信号、行为的单一语义 owner；动作结果可以进入假说生命周期 |
| 按原 horizon 评价 | `BYPASSABLE` | decision 有 expiry；review 不回写原 thesis | expiry 只要求晚于 decision；15M/1H/4H/1D 共用一次命中式 evaluator，重复父级 bar 不去重 |
| 短期 PnL 不验证理论 | `RUNTIME_ENFORCED`（窄范围） | review 明确 `PNL_DOES_NOT_CHANGE_THEORY_OR_METHOD_SCORE`，paper performance 单列 | 价格/方向支持仍可在 horizon 前产生 `SUPPORTED_ACTIVE`；所以“短期结果不验证长期判断”的完整要求仍未封闭 |
| 支持与反证冲突 | `PARTIAL` | 同一观测同时命中时 falsifier 优先，并记录 ambiguous | 同时命中仍进入混合 lifecycle；没有 `CONFLICTED` 独立状态或禁止计入支持的统一规则 |
| 当前自动提示 | `MISSING` | v1 要求 thesis/falsifier/expiry；v2 补充缺失数据竞争路径 | 两份 prompt 都没有 A/B/C/D、信号权限、再入场合同、fresh-bar horizon gate；v2 也未激活 |
| PIT、摘要、write-once | `RUNTIME_ENFORCED` | v1 transaction、ledger、digest、decision_at 和 paper-only 边界失败关闭 | 这能保护历史和来源，不等于保护决策语义 |

## 5. 关键代码证据

### 5.1 分析层写了禁止越级

- `CORE_TRADING_THEORY_v2_1.md:343-353`：微观、事件决策、背景状态三层及禁止事项；
- `CORE_TRADING_THEORY_v2_1.md:1250-1263`：1W/1D/4H/1H/15M 有序角色，不得固定周期投票；
- `trade_system/theory_paper/theory.py:444-484`：4H 是 operational，1H 是 setup，15M 是 trigger，并输出 `NO_TIMEFRAME_VOTING_LOWER_ROLE_CANNOT_OVERRIDE_PARENT_ROLE`。

### 5.2 最终决策校验没有执行这条规则

- `theory.py:880-952`：几何只由 1H support/resistance/ATR 生成，不绑定 PHI、4H 父级或升级回执；
- `theory.py:1905-1919`：`selected_phi_id` 只需属于 finite registry；
- `theory.py:2208-2233`：低层 action 只需与 Agent 自选 PHI、方向和几何互相一致，不检查该 PHI 的方向、support ordinal 或 4H 父级；
- `experiment.py:1158-1176`：每个周期、每个标的都新建 `cycle-id:symbol` 假说实例，没有 prior instance 或 transition receipt。

只读内存反例：

- cycle-0014 HYPE 的 4H 父级为 `DOWN`；
- 将 decision 改为 `PHI_UPWARD_CONTINUATION`、`OPEN_LONG`、支持谓词 `15M_DIRECTION == UP`，同时绑定原有多头几何；
- `validate_decision` 返回 `valid=true, errors=[]`。

另一个反例把 BTC 空头 action 绑定为 `PHI_UPWARD_CONTINUATION`，校验同样返回 `valid=true`。这证明“PHI 方向—动作方向”本身也没有被绑定。

### 5.3 v1 无法表达再入场合同

`theory.py:2151-2159` 的 `CLOSE` 只允许：

`type / symbol / notional_usdt / attribution / hypothesis_id / reason`

向真实 cycle-0015 MU CLOSE 添加：

`action_intent=RISK_CONTROL` 与 `reentry_contract={...}`

会被当前 validator 拒绝为：

`UNKNOWN_FIELDS:action_intent,reentry_contract`

因此这不是“Agent 忘了填写”，而是当前 schema 根本不允许表达。

### 5.4 复盘没有 horizon 分层

- `experiment.py:1313-1387`：任一后续 hourly analysis 首次命中 support 即为 `SUPPORTED_ACTIVE`；
- evaluator 不检查 4H/1D source bar ID 是否更新，也不要求 fresh closes；
- `experiment.py:1414-1429`：review 是否到期只计算 cycle 数；
- `experiment.py:1621-1669`：不同 horizon 的 terminal 状态用统一 100/20/0 汇总，虽标明未校准且不改变 theory/method score。

## 6. 真实周期证据

### 6.1 MU：退出后无治理合同的一小时再入场

1. cycle-0014：MU 以 `PHI_DOWNWARD_CONTINUATION` 开空，止损 `784.70905219`；
2. cycle-0015：观测价 `787.15520957` 已高于止损；chaos 成交先关闭 lot-000010 的 `0.27678150046`，Agent 成交再关闭余下 `0.049820311381`；
3. 同一 cycle-0015 decision 又创建 `cycle-0015:MUUSDT`，以 `price > 784.7090521925` 为 support；
4. cycle-0016 观测价 `830.19666913` 命中该 support，随后 decision 新开 lot-000015；
5. 在 cycle-0016 decision 之后生成的 review-002 回溯将 cycle-0014 标为 `FALSIFIED`、cycle-0015 标为 `SUPPORTED_ACTIVE`，cycle-0016 标为 `UNRESOLVED_UNKNOWN`。

整个链路没有：

`prior_exit_event_id / reentry_contract→closed_lot_ids / prior_hypothesis_instance_id / exit_kind / reset predicates / staged restoration / reentry count / risk adjustment / review_by`

执行成交回执本身保留了 `closed_lots`，缺少的是它与后续再入场合同之间的机器可读链接。同一价格谓词方向在旧实例中作为 falsifier、在下一新实例中作为 support，中间没有 typed state transition 或 reentry link，风险动作状态因而被泄漏进路径评价。

这条链由原始 chaos、decision、fill 和 review 工件及完整 ledger 校验共同支持；当前 governance sidecar 的 source hash 尚未单独列入 chaos-execution 与 review-002 摘要，因此 sidecar 本身不能独立充当这两类工件的加密证据包。

### 6.2 动作、观点和原持仓假说混用

- cycle-0016 SNDK 的 symbol decision 是 `EXIT + PHI_DOWNWARD_CONTINUATION`，实际 CLOSE action 却携带原 lot 的 `PHI_RANGE`；
- cycle-0016 SOL 是 `REDUCE + PHI_RANGE`，support 阈值正是旧 lot 的 stop；精确 lot 只在成交回执中事后绑定；
- HYPE long lot 的父假说仍是 cycle-0014 `PHI_ABSORPTION_REVERSAL`，后续 symbol decision 已改为 DOWN；schema 没有独立的 current market view 和 position parent thesis。

这不是历史工件被篡改，而是多个语义被装进同一 decision 对象。

## 7. 已有研究契约的边界

research-system v1/v1.1/v1.2 中有不少可复用原则：

- PIT、摘要、append-only；
- finite path、hard invalidation、expiry；
- research plane 与 permission/action plane 分离；
- position risk 单调收紧；
- path switch 不能自动反手。

但 v1.2 明示为 `E0_STATIC_AND_SYNTHETIC_CONTRACT_ONLY`，其 Python validator 不做 market-data、replay、paper 或 execution I/O。测试通过只能证明静态契约未漂移，不能证明当前定时 Agent 正在执行这些治理规则。

## 8. 修复判定

不能在现有 v1 `theory.py / portfolio.py / experiment.py / prompt v1` 中直接加字段：

1. 当前活动 run 的 manifest 已绑定这些权威摘要；
2. v1 transaction 和 decision schema 已冻结；
3. 中途修改会污染 72 小时基线，且无法让历史周期获得当时不存在的 intent/reentry 数据。

严谨修复必须在 v1 旁边新增 successor governance core：

- 读取 v1 committed decision、commit 和 ledger；
- 不根据 reason 文本补造历史 intent；
- 对旧周期输出阻塞型 audit sidecar；
- 对未来 governance card 强制五层权限、A/B/C/D、升级回执、再入场合同和 horizon 评价；
- 当前 run 结束、shadow gate 通过并获得用户单独授权后，才接入提交前门。

这一路径保留原始实验，同时把漏洞变成可执行、可测试、可失败关闭的系统约束。

## 9. Successor 修复状态

已在独立 `trade_system/theory_paper/governance_v2/` 中实现 shadow core，并把
独立代码复核发现的候选绕过继续封闭：

- 实际 `EXIT/REDUCE` 与允许 intent 强绑定，不能再冒充 `HOLD` 逃避再入场合同；
- 自签 lower-timeframe promotion 一律拒绝，等待可信 evidence adapter；
- genesis 只能建立为 `A_VALID + NO_CHANGE`，不能用自报时钟和自签 4H 信号直接进入 C/D；
- 同一 hypothesis 的 PHI、方向、前提、失效条件和 horizon 不可静默重写；
  没有 creation receipt 时更换 hypothesis ID 也拒绝；
- 再入场字段即使形状完整，在 lot/谓词/调度执行 authority 未接入时仍拒绝，
  不把 `MADE-UP` condition ID 当作可执行合同；
- card 强制同 run、相邻 cycle 和 `previous_card_digest`；
- strategic horizon 强制匹配评价周期、最低 closed windows 和相应最短时长；
- `evaluate_horizon_status` 在时间或完整窗口不足时只返回 interim；
- sidecar cycle ID 只允许 `cycle-NNNN`，最终 resolved target 必须位于独立
  output root 且不得位于 v1 run 内。

这些修复使已知反例在 successor 纯领域门中失败关闭，但仍不代表当前 v1 已修复。
可信信号提取、真实收盘/事件时钟、已接受 card repository、合法新假设铸造、
lot 级再入场执行和冻结谓词 horizon evaluator 尚未接线；相应路径当前保持
`NONE_SHADOW_ONLY / NONE_VALIDATION_ONLY`，而不是降级放行。
