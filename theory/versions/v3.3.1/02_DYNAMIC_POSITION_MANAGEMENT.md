# Agent-first 动态仓位管理

版本：`3.3.1-agent-first-trader-candidate.1`

状态：`FROZEN_VERSION_CANDIDATE / PUBLIC_REFERENCE_POSITION_ONLY / NON_EXECUTABLE`

Owner：Position Decision Agent（与 Market Cognition Agent 为同一决策 owner）。

输入：已准入事实、Agent 自己的市场认知与竞争假说、公开合约几何、无副作用计算工具与当前权限边界。

输出：写入 `HypothesisRecord.AgentDecisionBody` 权威原文的最终不可执行参考动作、entry、stop、targets、tranche、runner、reentry、参考仓位和路径驱动的调整计划；`BehaviorPlan` 作为正式五工件之一，只能原样引用/复制这些 Agent 自选内容。

## 1. 仓位决策权

仓位管理不是系统把 Agent 的语言等级映射成一个固定数值，也不是 deterministic allocator 在 Agent 完成分析后再决定“真正最终仓位”。在 V3.3.1：

- Agent 决定是否暴露方向风险；
- Agent 决定参考方向、触发、入场区、失效和保护；
- Agent 决定初始参考仓位、分批、加减仓、止盈、runner 和再入场；
- Agent 决定哪个市场变化将使计划升级、降级、取消或反转；
- Agent 决定 Outcome 之后这个仓位政策是否合理。

系统可以按 Agent 指定的输入和公式计算距离、数量、压力损失、MAE/MFE、capture 或组合场景，但不能选择公式参数、风险档位、目标、仓位数量或最终动作。它返回计算与 provenance，Agent 对使用和结论负责。

如果 Agent 给出的仓位计划激进、没有 stop、targets 有歧义或用了未登记的表达，在当前不可执行研究中仍原样封存。这些是 Agent 质量证据，不是 schema 失败。

## 2. 目标与基本立场

动态仓位将不确定的未来路径转换为可撤销、可降低、可复核的参考风险安排：

1. 初始错误不应破坏继续判断和捕捉新机会的能力；
2. 证据较弱或路径尚未启动时，可选择更小参考暴露或条件计划；
3. 亏损、更便宜或主观不甘不是增加同类风险的理由；
4. 路径得到新的机制差异证据时，Agent 可动态增加仓位，但必须重新评估整体风险；
5. 收益显著扩大时，应认真比较部分落袋、继续全持有和全部退出；
6. 部分落袋后保留独立 runner，为右尾大行情留出空间；
7. 每个调整都应能回到新事实、假说更新、时间消耗、风险变化或预先声明的路径条件。

不存在跨市场、跨周期和跨 regime 都最优的 stop、take-profit、ATR 倍数、harvest 比例、runner 比例或 reentry 次数。稳定理论定义问题、几何、选项和失效；具体参数是 Agent 本轮决策与后续 Review 对象。

## 3. REFERENCE 与 ACCOUNT 必须分开

### 3.1 当前唯一合法模式：REFERENCE

当前可以：

- 用归一化风险单位表达仓位；
- 用公开价格和合约几何计算参考数量；
- 比较 entry/stop/target/harvest/runner/reentry 的价格路径；
- 在 Outcome 中计算参考 MAE、MFE、capture 和 giveback；
- 提交最终不可执行参考动作。

当前不得：

- 读取或推断账户权益、可用保证金、真实持仓和挂单；
- 声称知道真实 fee tier、slippage、fill、funding accrual 或 liquidation price；
- 将参考数量命名为可下单数量；
- 从 `AgentDecisionBody` 或 `BehaviorPlan` 直接调用 paper/testnet/live executor。

```text
risk_mode = REFERENCE
reference_quantity = Agent decision or explicitly UNKNOWN
executable_quantity = null
execution_mapping = NOT_AUTHORIZED
```

### 3.2 未来 ACCOUNT 模式

真实仓位需要独立授权与真值 owner，至少包括 equity、margin、positions、orders、fills、fee/funding、leverage/liquidation、position mode、reduce-only、lot/tick/min-notional、spread/depth/impact、partial fill/cancel/replace 和 reconciliation。

这些未成立时，Agent 仍可写完整参考计划；安全系统只阻断外部副作用，不改写或否决这个研究决策。

## 4. 仓位语义对象

下列是 Agent 思考模型，不是必须按字段或枚举输出的 schema：

```text
Position Thesis
  episode and horizon
  final reference action
  direction or non-directional posture
  entry trigger / entry zone / entry mode
  structural invalidation
  protective stop or other exit response
  stress exit assumption
  initial reference size
  tranches and their purposes
  add / reduce / harvest / runner rules
  targets and path milestones
  time / event exit
  reentry conditions
  portfolio and shared-risk considerations
  critical unknowns and next review
```

Agent 可使用自然语言、表格、公式、区间或情景树组织计划。系统不能因为缺少 `state=CORE` 这类枚举就拒绝。

## 5. 初始仓位：先路径几何，后数量

### 5.1 入场前的核心问题

Agent 应在自己的结论中解决：

1. 什么可观测事实说明路径开始或已值得提前布局？
2. 什么事实说明路径不再成立？
3. 从保护条件到压力退出价可能还有多少价格距离？
4. 目标路径是否有足够空间容纳噪声、压力损失和公开成本假设？
5. 初始错误后是否仍有能力判断不同假说或等待新机会？
6. 该仓位是否与其他参考计划共享价格、venue、beta、抵押品或流动性因子？

如果 Agent 仍然决定在一个失效不清的路径上给出仓位，系统不会用格式门删掉。该决策原文将成为后续 Review 证据。

### 5.2 三个不同的退出概念

```text
structural invalidation = 什么事实说明假说/路径错了
protective response     = 什么时候开始减仓、保护或退出
stress exit price       = 用于参考损失计算的压力实现价
```

结构失效可以是区域失守、路径次序破坏、时间到期、新事实改变机制或一项反证。stop 价格不必等于结构失效点，因为触发到可实现退出之间还有距离。

### 5.3 单位压力损失工具

```text
u = |PnLPerUnit(entry, stress_exit)|
    + public_fee_bound_or_unknown
    + slippage_stress_or_unknown
    + funding_bound_or_unknown
    + gap_or_stop_through_bound
```

线性合约的简化几何：

```text
|PnLPerUnit(e, s)| = contract_multiplier × |e - s|
```

反向合约、期权或非线性产品不能用该简化。当前真实费用/滑点不可观测时，Agent 可使用明确的公开压力假设，或将数量表达为归一化 R 单位；不得宣称是真实最大损失。

### 5.4 参考数量计算

若 Agent 选择某个参考风险预算 `R_ref`：

```text
q_stop_ref = floor_to_lot(R_ref / u)
q_vol_ref  = floor_to_lot(R_vol_ref / unit_volatility_stress)
q_reference_candidate = min(q_stop_ref, q_vol_ref)
```

这些只是候选计算。Agent 可以选择更小、使用区间、改用条件触发，或因目标空间不足而选择 WAIT/OTHER。系统不能自动用 `min()` 结果覆盖 Agent 最终参考仓位。

### 5.5 噪声、结构和目标空间

```text
d_noise_candidate = k_vol × ATR_h + public_spread/slippage_stress
d_effective_candidate = max(d_structure, d_noise_candidate)
```

`k_vol` 不是理论常数。Agent 应根据 regime、horizon 和窗口敏感性决定是否使用。如果 stop 放到噪声外后已没有足够目标空间，合理选项可以是不进入，而不是把 stop 塞回噪声区。

## 6. 假说—tranche 风险对齐

每个 tranche 应有独立用途：验证路径、表达核心观点、利用新证据加仓、部分落袋、保留 runner 或在未来授权下对冲。

一个合理 tranche 通常可以说明：

```text
which hypothesis/path it expresses
why it exists now
entry or activation condition
independent invalidation/expiry
reference risk and quantity
target/harvest purpose
what evidence changes it
```

多个故事若都来自同一价格序列、同一 venue、同一 beta 或同一流动性压力，不构成分散。Agent 应将共享失败簇视为同一风险。系统可绘制依赖关系，但不能决定保留哪个 tranche。

## 7. 仓位生命周期是描述，不是枚举门

常见进程：

```text
观察/条件计划
→ 小额路径验证
→ 核心参考仓位
→ 部分落袋
→ 独立 runner
→ 关闭/重建
```

Agent 可使用 `WATCH/SEED/CORE/HARVESTED/RUNNER/CLOSED` 等语言，也可以用更自然的描述。这些词不是必填 lifecycle 枚举，不得因为词汇不同拒绝决策。

关键语义：

- 路径未启动时，条件计划可以比立即暴露更合理；
- 小额路径验证必须有失效、expiry 和明确目的；
- 升级为核心应有新的决策信息，而不只是浮盈或语言信心；
- 部分落袋把一部分有利路径转为参考已实现结果；
- runner 必须有自己的 thesis、stop/exit、expiry 和 giveback 处理；
- 反向计划是新 episode，不用“翻仓”语言掩盖旧风险的关闭。

## 8. 加仓、减仓与反马丁格尔

### 8.1 加仓的合理证据

加仓可以基于：

- 新的可观测路径确认；
- 来自不同依赖簇的新机制证据（如果当前真的有这类数据）；
- 旧 tranche 风险已通过实际减仓或可靠保护释放；
- 新 tranche 拥有自己的入场、失效、目标和风险理由；
- 加仓后总体压力损失仍符合 Agent 本轮选择的参考风险计划。

价格上涨本身可以是路径观察，但不必然是独立新证据。Agent 必须判断它是否真的改变了路径与风险。

### 8.2 亏损时的风险收缩

下列不是增仓理由：更便宜、已经亏了很多、距离成本价更远、想改善平均成本、相同假说换一种说法或相信总会回来。

亏损面前，Agent 应比较：

```text
hold under unchanged thesis
reduce because unit stress increased
close because path/invalidation failed
wait for a genuinely new episode after close
reverse only through a separate opposite thesis
```

最终选择仍属于 Agent。系统不能把“亏损=自动 close”或“距离更远=自动加仓”写成语义规则。

### 8.3 主动减仓条件

Agent 可在 hard falsifier 之前减少参考风险：

- 支持证据过期、路径迟迟不出现；
- 竞争假说获得更好的解释力；
- 波动上升使单位压力损失扩大；
- 已准入的流动性或 venue 事实恶化（当前未观测则不伪造）；
- 相关暴露增加；
- 已有高收益，但继续性没有同步增强；
- 时间价值接近耗尽。

## 9. 动态止损

Agent 可组合多种 stop/exit 逻辑：

| 类型 | 主要问题 | 候选处理 |
|---|---|---|
| 结构失效 | 区域、次序、路径被破坏 | 减仓/关闭/重建 |
| 假说失效 | hard falsifier 或机制被反证 | 关闭对应 thesis |
| 波动失配 | stop 落在正常噪声或单位风险升高 | 减小数量或放弃 setup |
| 时间止损 | expiry 前预期路径未出现 | 减仓/关闭/重评 |
| 事件止损 | 已准入的新事件改变风险 | 保护/关闭/新决策 |
| 组合止损 | 共享场景损失或集中度上升 | 减少边际风险大的计划 |
| 盈利保护 | 已有高收益且 giveback 风险上升 | 部分落袋/跟踪/关闭 |

一个有用的风险参考是：

```text
StressLoss_after_change <= StressLoss_before_change
```

它不要求 stop 价格永远只向盈利方向移动。如果新结构需要更宽的 stop，Agent 可以决定先减小参考数量后重算。这是管理思路，不是系统强制改写 Agent 计划的 allocator rule。

不机械把 stop 推到成本价。成本价不是市场结构；若 breakeven stop 位于正常噪声中，部分落袋或减小仓位可能更真实。

## 10. 动态止盈、落袋与 runner

在参考 episode 中：

```text
Floor_t = ReferenceRealizedNet_t
        + StressLiquidationNet(Q_remaining_t, stress_exit_t)

Giveback_t = PeakMarkedNet_t - Floor_t
```

若 Agent 选择一个希望锁定的参考保底 `RequiredFloor_t`，可以请求计算工具求最小落袋数量 `h`：

```text
Floor_t(h, stress_exit_t) >= RequiredFloor_t
Q_remaining_t >= Q_runner_min chosen by Agent
```

`RequiredFloor`、里程碑、harvest 比例和 `Q_runner_min` 全部是 Agent 决策/候选 policy，不是系统常数。

### 10.1 高收益时的主动处理

收益较大时，Agent 应认真比较：

```text
A. 继续全持有
B. 部分落袋 + 独立 runner
C. 全部退出
D. 更换 stop/target 与数量的组合
```

当已有收益扩大，而继续性、新证据或路径空间没有同步增强时，理论倾向让 Agent 优先考虑部分落袋，将一部分有利路径变成参考已实现结果。但最终比例和动作仍由 Agent 决定，并在 Review 中受检验。

落袋后无新证据不应立即加回；runner 的目标是保留右尾，不是把全部已得收益重新暴露。

### 10.2 路径—管理对照

| Agent 判断的路径 | 值得比较的管理 |
|---|---|
| 趋势稳定、路径完整、波动可控 | 保留更多 runner 空间，避免过早全平 |
| 顺势波动扩张 | 部分落袋 + 更宽但数量更小的 runner |
| 到达结构目标、继续性一般 | 提高参考 Floor，减小剩余暴露 |
| 衰竭/假突破/竞争路径增强 | 更大 harvest、收紧或退出 |
| RANGE/均值回归 | 结构目标更重要，runner 可更小 |
| hard falsifier | 关闭对应计划，不因浮盈忽略 |
| 关键 UNKNOWN 增加 | 条件化、减小或等待，由 Agent 比较机会成本 |

## 11. 路径驱动的实时重规划

每次新决策只需重新审视真正变化的内容：

```text
price path and zones
hypothesis support / contradiction / falsifier
volatility and unit stress
time / expiry / scheduled review
admitted liquidity or event facts, if any
shared portfolio exposures
original position thesis and prior decision text
```

| 新观察 | Agent 可考虑的参考转换 |
|---|---|
| 路径开始但证据尚弱 | 小额验证/条件触发 |
| fresh 路径确认 | 升级核心或增加独立 tranche |
| 只有浮盈 | 持有/落袋/收紧的比较，不自动加仓 |
| 软反证 | 减小/保护/取消未触发部分 |
| hard falsifier | 关闭相关 thesis，保留事后 Review |
| 波动上升 | 重算单位压力，通常需比较减小数量 |
| 波动下降 | 不自动放大；需新决策 |
| 高收益且趋势仍在 | 部分落袋 + runner |
| runner giveback 超过 Agent 本轮容忍 | 减小/关闭/改变保护 |
| 竞争假说转为主线 | 先处理旧计划，再建独立新 episode |

系统可将原决策和新事实放在一个有界上下文中，但不能自动生成 PositionTransition 并把它当成 Agent 选择。

## 12. 再入场

固定“24 小时”、“最多两次”不是稳定理论。Agent 应根据上一次失败类型、新证据、新路径和剩余参考风险判断：

| 上次退出原因 | 再入场时需回答 |
|---|---|
| 正常噪声触发保护，父 thesis 仍在 | 退出后是否出现 fresh confirmation？ |
| 假突破后重新夺回区域 | 是否有新机制/路径，而不只是价格回来？ |
| 时间到期 | 什么新信息改变了时钟？ |
| hard falsification | 是否真的建立了新 thesis/episode？ |
| 流动性/执行故障 | 研究可继续，外部执行仍保持关闭 |
| 同一失败簇重复 | 是否真的有不同证据，还是再次表述旧信念？ |
| 新反向假说 | 旧计划如何先关闭，新计划如何独立失效？ |

attempt count 只是 Review 信息，不是系统终态门。Agent 可在原文中解释为什么当前次数仍值得/不值得。

## 13. 组合、共享风险与尾部

当前没有账户真值，因此只能做参考场景。Agent 可请求工具计算：

```text
portfolio_vol = sqrt(w' Σ w)
MRC_i = (Σw)_i / portfolio_vol
RC_i = w_i × MRC_i
PortfolioStressLoss = max_scenario sum_i Loss_i(scenario)
```

但是否使用 covariance、哪些场景有意义、如何调整某个计划由 Agent 决定。最少考虑的尾部候选：

- common beta shock 和相关性向 1 收敛；
- 波动跃升、价差扩大与流动性撤退；
- venue/API/托管/指数或预言机故障；
- funding、拥挤和清算链式恶化；
- gap/stop-through；
- stablecoin、抵押品或网络状态冲击；
- 多个不同故事共享价格/流动性/数据源失败。

非价格数据当前 UNKNOWN，因此 Agent 应将这些作为未观测压力场景，不声称已测得真实组合风险。

## 14. 完整动作比较

Agent 不应只在 LONG/SHORT 中二选一。当前参考研究可比较：

```text
directional entry
conditional entry
small reference probe
WAIT with opportunity cost
HOLD / REDUCE / CLOSE
partial harvest + runner
full exit
reverse through two episodes
reentry as a new episode
information-seeking or OTHER action
```

上述不是必须使用的受控词汇。Agent 可表达新的参考行为。系统不得因动作不在 enum 中拒绝；只有实际调用外部副作用时，权限系统才能按授权阻断执行。

WAIT 也应是 Agent 的真实决策，而不是系统因 UNKNOWN 或规则不闭合产生的默认值。高质量 WAIT 通常说明原因、机会成本、下一复核和改变决策的观察。缺失这些内容仍封存，留给 Review。

## 15. 可读仓位决策的语义责任

一个能支持实战研究的 `AgentDecisionBody` 应尽可能让读者理解：

- 最终不可执行参考动作是什么；
- 立即、条件、分批或不进入的入场逻辑；
- 结构失效、保护响应、stop 和压力退出假设；
- 初始参考仓位或归一化风险单位及其理由；
- 不同假说/路径对应的 tranche；
- 加仓、减仓、取消、落袋和 runner 的条件；
- 目标区、分批目标、时间/事件退出与 giveback 处理；
- 亏损情景、高收益情景与超预期延续情景的不同计划；
- reentry 需要的新证据与剩余风险；
- 关键 UNKNOWN、下一 review 与什么会改变计划。

这是语义职责，不是必填 schema、标题顺序或封存门。Agent 缺失某项时，系统不得用默认 policy 填充；原文封存，Outcome 依预注册市场时钟继续，Agent Review 判断缺失的实际后果。

## 16. Outcome 与 Agent Review

系统可在预注册 horizon 采集同口径价格并计算：

```text
MAE
MFE
endpoint reference return
time in reference risk
path milestones observed or typed missing
reference capture
reference giveback
stop/target touch sequence where observable
```

当前没有 fill、fee、slippage、latency 和 position truth，不能计算真实 net R 或盈利。

Agent Review 需自主判断：

- 初始仓位是否与当时认知和失效几何一致；
- stop 太紧、太宽、与结构无关，还是合理；
- targets 是否太早截断右尾，或过度暴露已得收益；
- partial harvest 与 runner 如何分别贡献；
- 加仓是基于新证据，还是追价/不甘；
- 减仓和退出是否对路径变化反应过慢/过快；
- reentry 是新 episode，还是老失败的重复；
- 当时的 WAIT/替代动作机会成本如何。

固定全平、trailing、partial+runner、时间退出、结构退出和 reentry 变体都是候选 policy arms，未来只能从同一 PIT/同一机会集的前瞻 Outcome 比较中学习。系统不能从 MFE 事后反向挑选“最优退出”并写回旧决策。

## 17. 参数、成熟方法与已知边界

可供 Agent 判断的成熟方法：stop-distance sizing、volatility scaling、risk unit/tranche、portfolio heat、stress scenarios、partial harvest、trailing/time/structure exit、runner 与 drawdown 思路。这些提供问题和计算框架，不提供当前最优参数。

参考：

- [CME: Proper Position Size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size)；
- [Fidelity: Managing Positions](https://www.fidelity.com/learning-center/trading-investing/trading/managing-positions)；
- [Fidelity: Exit Strategies](https://www.fidelity.com/learning-center/trading-investing/trading/exit-strategies)；
- [Kaminski & Lo: When Do Stop-Loss Rules Stop Losses?](https://www.sciencedirect.com/science/article/abs/pii/S138641811300030X)；
- [Moreira & Muir: Volatility-Managed Portfolios](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12513)；
- [Moskowitz, Ooi & Pedersen: Time Series Momentum](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf)。

未校准时不把概率、EV、Kelly 或胜率当作仓位根据。如果 Agent 仍然在原文使用了伪精确概率，该原文依然被封存，并由 Review 评价这种做法对决策的影响；系统不用格式门修改或拒绝。

当前仍为 UNKNOWN：哪种 stop/target/harvest/runner/reentry 组合有稳定优势，参考风险与真实执行风险的偏差，以及任何仓位政策能否在成本后提供正价值。
