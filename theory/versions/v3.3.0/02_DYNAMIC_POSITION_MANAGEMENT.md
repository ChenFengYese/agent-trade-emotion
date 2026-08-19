# 动态仓位管理

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE / PUBLIC_REFERENCE_RISK_ONLY / NON_EXECUTABLE`

Owner：仓位几何、分批、止盈止损、路径调整、再入场与组合压力。

输入：`MarketState`、竞争 `HypothesisRecord`、允许动作集、公开合约规格；未来账户模式另需真实账户与执行状态。

输出：`PositionPlan`。本文不拥有假说事实、账户余额、真实成交或交易权限。

## 1. 目标与基本立场

仓位管理不是在预测之后附加一个固定百分比。它把“不确定的未来路径”转换成一组可撤销、可减小、可复核的风险安排，目标依次为：

1. 单次错误不能破坏继续研究和行动的能力；
2. 初始判断较弱时只暴露较小风险，证据和路径确认后才申请增加；
3. 亏损时不因价格更便宜、浮亏或主观不甘而扩大同一风险；
4. 盈利较大时把一部分账面收益变成已实现净值；
5. 同时保留独立 `RUNNER`，避免在首个目标位全部退出并错失长趋势；
6. 任何加减仓、保护位和目标变化都能追溯到新事实、风险释放或预先定义的路径条件；
7. 比较 `LONG / SHORT / WAIT / probe / REDUCE / CLOSE / REVERSE / REENTER / OTHER`，而不是先选方向再寻找仓位。

不存在跨市场、跨周期、跨状态都最优的 stop、take-profit、ATR 倍数、仓位比例或 runner 比例。稳定理论只定义对象、公式、不变量和裁决顺序；具体数值属于带版本、理由和 `UNVALIDATED` 状态的 `PositionPolicy`。

## 2. 两套风险语义必须分开

### 2.1 当前可用：公开数据研究参考风险

`REFERENCE` 模式用于比较路径和动作：

- 规范化一个 episode 的参考风险单位；
- 根据公开价格、合约规格和压力退出价计算参考数量；
- 比较不同 stop、harvest、runner 和 reentry 路径；
- 在 outcome 中计算参考 MFE、MAE、capture 和 giveback；
- 不读取账户，不形成订单，不声称真实最大损失或收益。

当前缺少账户权益、保证金、费率档、实际仓位、成交、滑点容量或清算价时：

```text
risk_mode = REFERENCE
reference_quantity = allowed
executable_quantity = null
execution_mapping = NOT_READY
```

### 2.2 未来另行授权：账户执行风险

`ACCOUNT` 模式只有在独立授权和执行合同成立后才能使用，至少需要：

```text
account equity and available margin
actual positions, open orders and fills
fee tier and funding accrual
leverage, liquidation price and collateral state
order mode, position mode and reduce-only semantics
lot/tick/min-notional limits
live spread, depth and size-dependent slippage
partial fill, cancel, replace and reconciliation state
```

研究 Agent 不得自行填写这些真值，也不得把 `reference_quantity` 改名为可下单数量。市场单不保证成交价，止盈止损触发也不保证最终成交；触发、订单确认、fill 和最终 position truth 是四种不同事实。[OKX 基础订单类型](https://www.okx.com/en-us/help/x-basic-order-types)、[OKX TP/SL 说明](https://www.okx.com/en-gb/help/how-to-set-up-profit-and-stop-loss-of-contract-transactions)

## 3. 核心对象与唯一所有权

```text
PositionPlan
  plan_id, episode_id, instrument, direction, as_of
  risk_mode: REFERENCE | ACCOUNT
  state: WATCH | SEED | CORE | HARVESTED | RUNNER | CLOSED
  policy_version, policy_status
  hypothesis_cluster_ids[]
  entry_trigger
  structural_invalidation
  protective_trigger
  stress_exit_price
  time_exit, event_exit
  risk_budget_class
  unit_stress_loss
  reference_quantity
  executable_quantity_or_null
  tranches[]
  profit_milestones[]
  runner_plan
  portfolio_exposure_tags[]
  unknowns[]
  evidence_refs[]

Tranche
  tranche_id, parent_episode_id
  role: SEED | CORE | ADD | HARVEST | RUNNER | HEDGE
  entry_mode, entry_reference
  supporting_clusters[], falsifiers[]
  risk_reserved, quantity
  structural_invalidation, protective_trigger, stress_exit_price
  target_state, expiry
  realized_net_or_unknown
  transition_history[]

PositionTransition
  transition_id, from_state, to_state
  cause_type, fresh_evidence_refs[]
  quantity_before, quantity_after
  stress_risk_before, stress_risk_after
  created_at
```

所有权固定为：

- `HypothesisRecord` 拥有假说、支持、反证和 expiry；
- `PositionPlan` 拥有仓位几何与 tranche；
- 未来 `AccountSnapshot` 拥有账户真值；
- 未来 `PositionTruth` 拥有交易所最终仓位和成交；
- Agent 可以提议转换，确定性 allocator 负责数值映射与上限截断。

同一个数据对象只能有一个 owner。仓位文档不得复制并篡改市场事实或假说证据。

## 4. 初始仓位：先失效位，后风险，再数量

### 4.1 先回答五个问题

任何 `SEED` 前先确定：

1. 哪个可观察事实说明这条路径不再成立？
2. 从该事实到可实现退出之间可能还有多少滑点、跳空和费用？
3. 计划的目标路径是否仍有足够空间覆盖压力损失和成本？
4. 这条路径与已有 exposure 是否共享价格、venue、beta、抵押品或流动性因子？
5. 若起步就错，是否仍保留足够 episode 风险用于另一条真正不同的假说？

如果失效条件无法写成事前可观察事实，则不生成方向仓位；可以继续市场认知或设计信息价值更高的观察动作。

### 4.2 三个退出概念不能混用

```text
structural_invalidation = 什么事实说明假说错了
protective_trigger      = 何时启动减仓或退出动作
stress_exit_price       = 压力条件下用于风险计算的实现价格
```

`structural_invalidation` 可以是区域失守、路径次序破坏、事件结果改变或机制反证；它不等于一个精确成交价。`protective_trigger` 是动作条件；`stress_exit_price` 必须包含触发后到实现退出的压力距离。

### 4.3 单位压力损失

对 tranche `j`：

```text
u_j = |PnLPerUnit(entry_j, stress_exit_j)|
    + fee_open_bound
    + fee_close_bound
    + slippage_stress
    + funding_bound
    + gap_or_stop_through_bound
```

线性合约的方向无关近似为：

```text
|PnLPerUnit(e, s)| = contract_multiplier × |e - s|
```

反向合约、期权和非线性产品必须使用交易所精确 PnL 函数；不能沿用线性近似。

### 4.4 数量计算

给定 tranche 风险预算 `R_j`：

```text
q_stop_j = floor_to_lot(R_j / u_j)
```

波动压力上限：

```text
u_vol_j = contract_exposure_per_unit × forecast_or_realized_vol_h
q_vol_j = floor_to_lot(R_vol_j / u_vol_j)
```

当前研究模式：

```text
q_reference_j = min(q_stop_ref_j, q_vol_ref_j)
```

未来真实执行模式：

```text
q_exec_j = min(
  q_stop_j,
  q_vol_j,
  q_liquidity_j,
  q_margin_j,
  q_portfolio_j,
  q_venue_limit_j
)
```

缺少任何执行必需真值时 `q_exec=null`，但市场分析、假说和 reference plan 可以继续。

CME 的仓位教育材料同样把 stop 位置和可承受风险置于数量之前；其中示例比例只是教学参数，不是市场定律。[CME：Proper Position Size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size)

### 4.5 噪声、结构与收益空间

对 long 的示意：

```text
d_noise = k_vol × ATR_h + spread_stress + slippage_stress
d_effective = max(d_structure, d_noise)
```

`k_vol` 不是理论常数。若把 stop 放到正常噪声之外后，目标空间已不足以覆盖压力损失和成本，应拒绝 setup，而不是把 stop 塞回噪声区。ATR 衡量包含 gap 的波动，不提供方向。[Fidelity：ATR](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr)

## 5. 风险预算的层级

```text
B_t = min(
  B_episode_remaining,
  B_symbol_remaining,
  B_dependency_cluster_remaining,
  B_portfolio_remaining,
  B_daily_remaining,
  B_drawdown_remaining
)
```

`REFERENCE` 模式只允许使用规范化 episode、symbol、dependency cluster 和公开场景压力预算。`daily/account drawdown` 没有真实账户时保持 `NOT_APPLICABLE`，不能用模拟盈亏冒充。

仓位上限依次经过：

1. 风险预算：最多愿意暴露多少压力损失；
2. stop-distance sizing：把预算映射为数量；
3. volatility scaling：避免同名义仓位在高波动时暴露更大；
4. liquidity/margin/venue：未来执行真值向下截断；
5. portfolio/drawdown：共享因子与账户状态再次向下截断。

波动管理只作为风险稳定器，不作为 alpha 或盈利保证。研究既有正面结果，也有实时、样本外并不稳定的反证。[Moreira 与 Muir](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12513)、[Cederburg 等](https://experts.arizona.edu/en/publications/on-the-performance-of-volatility-managed-portfolios/)

### 5.1 当前不使用 Kelly

Kelly 需要可信的胜率和赔率分布：

```text
f* = (b × p - q) / b
```

V3.3.0 未完成概率校准，禁止伪精确概率、EV 和胜率驱动仓位，因此 Kelly、fractional Kelly 和风险约束 Kelly 都不能进入当前仓位生成。它们只保留为未来拥有可信分布时的研究候选。[Kelly 原论文](https://www.princeton.edu/~wbialek/rome/refs/kelly_56.pdf)、[风险约束 Kelly](https://web.stanford.edu/~boyd/papers/kelly.html)

## 6. 假说—tranche 风险归因

每个 tranche 必须列出支持它的机制 cluster。对 tranche `j` 和 cluster `h`：

```text
A[j,h] ∈ {0,1}
sum_j A[j,h] × R_j <= Cap_h
```

一个 tranche 同时依赖多个 cluster 时，其风险在每个相关 cluster 下都完整计入，不能拆成多个小份后声称分散。多个故事若都来自同一价格序列、同一 venue、同一底层 beta 或同一拥挤因子，也不增加风险容量。

| 假说变化 | 仓位反应 |
|---|---|
| 仅自然语言改写 | 不变 |
| 支持证据过期 | 降级、减仓或取消未触发 tranche |
| 新的机制差异证据 | 可提出 ADD，但不自动获得预算 |
| 软反证增强 | `REDUCE / TIGHTEN / CANCEL_PENDING` |
| hard falsifier 命中 | `CLOSE` 对应 tranche |
| competing hypothesis 增强 | 比较 `REDUCE / CLOSE / REVERSE`，不能直接翻仓 |
| `OTHER / UNKNOWN` 扩大 | 降低风险等级，不抹掉分析 |
| 可选数据缺失 | 标记 UNKNOWN；只有执行必需真值缺失才阻断 executor |

`SEED / CORE / ADD / RUNNER` 是风险预算等级，不是固定数字。Agent 提议等级，确定性 allocator 按 `policy_version` 映射数值；Agent只能降低上限，不能自行扩大。

## 7. 仓位生命周期

```text
WATCH
  → SEED
  → CORE
  → HARVESTED
  → RUNNER
  → CLOSED
```

允许跳过某些状态，但不得逆向伪造历史。

### 7.1 WATCH

已有可反驳假说，但触发、成本空间或失效条件尚不完整。输出条件计划，不暴露方向风险。

### 7.2 SEED

用最小风险验证路径是否按预期启动。SEED 不是“先买一点再说”，必须已有 entry trigger、失效位、expiry 和参考压力损失。

### 7.3 CORE

只有在出现时间晚于前次决策 cutoff 的新机制证据，且既有路径没有反证时，才能从 SEED 升级。价格上涨本身不构成独立证据。

### 7.4 HARVESTED

到达预注册里程碑、波动扩大、拥挤增强或继续性下降时，卖出足够数量，使 episode 的压力保底净值达到 policy 要求。

### 7.5 RUNNER

剩余仓位拥有独立 thesis、stop、expiry 和 giveback policy。它不是无人管理的余仓，也不能因“已经免费”而忽略风险。

### 7.6 CLOSED

方向风险归零并记录原因。反向仓位必须建立新 episode：`CLOSE old → reconcile → OPEN new`；不能假设一个“翻仓”动作原子完成。

## 8. 分批、加仓与减仓

### 8.1 合法的反马丁格尔

允许顺着已验证路径增加，不允许仅因盈利机械增加：

- SEED 只验证路径；
- 新的机制差异证据支持升为 CORE；
- 趋势持续、旧风险已被实际减仓或可靠保护释放后，才可建立 ADD/RUNNER；
- 每个新增 tranche 有独立失效位、风险预算和 expiry；
- 新增后的总压力损失不得超过剩余预算。

```text
StressLoss(current + new) <= B_episode_remaining
FreshEvidenceTime > PreviousDecisionCutoff
```

浮盈、有利移动或 Agent 信心不能创造新风险预算。新增风险只能来自：

1. 新的独立证据；
2. 已经真实释放的旧风险；
3. 更高层预算 owner 的新分配。

趋势持续和 Turtle 的波动单位可作为成熟工程先例，但月度跨资产研究或 Turtle 的固定 `N`/单位数不能直接外推到 BTC 15 分钟。[Time Series Momentum](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf)、[Original Turtle Rules](https://www.turtletrader.com/rules/)

### 8.2 禁止亏损摊平

以下都不是加仓理由：

- 价格更便宜；
- 已经亏了很多；
- 距离成本价更远；
- 相信“总会回来”；
- 同一假说换一种说法；
- 为改善平均成本而增加同一 failure cluster。

均值回归的第二次进入只能作为拥有新证据、新失效位和新预算的独立 episode，不能伪装成补仓。

### 8.3 主动减仓条件

优先减小风险而不是等待硬 stop：

- 支持证据过期或变弱；
- 波动上升使单位压力损失扩大；
- spread/depth 恶化或 venue 状态异常；
- 与其他计划的相关暴露增加；
- 重大未建模事件临近；
- 时间价值耗尽而预期路径未出现；
- 已有高收益但继续性下降；
- competing hypothesis 获得机制差异证据。

## 9. 止损体系

| 类型 | 触发依据 | 主要动作 |
|---|---|---|
| 结构失效 | 关键区域、路径次序或机制被破坏 | `CLOSE` |
| 假说失效 | hard falsifier | 关闭对应 tranche |
| 波动失配 | stop 落入正常噪声或单位风险上升 | `REDUCE`，不凭空扩风险 |
| 时间止损 | 到期仍未出现预期路径 | `REDUCE / CLOSE / REASSESS` |
| 事件止损 | 未建模二元事件临近 | `REDUCE / CLOSE` |
| 流动性止损 | depth、spread、恢复能力恶化 | 减仓并冻结新增 |
| 组合止损 | 共享场景损失或集中度超限 | 减边际风险最大者 |
| 盈利保护 | 已走出较大利润，需控制 giveback | `HARVEST / TRAIL` |

简单 stop 并不普遍提高期望收益；其价值取决于动量、均值回归和成本状态。因此 stop 必须绑定机制和 regime，不能用统一百分比。[Kaminski 与 Lo](https://www.sciencedirect.com/science/article/abs/pii/S138641811300030X)

### 9.1 风险单调性替代“价格永不后退”

稳定不变量是：

```text
StressLoss_new <= StressLoss_old
```

不是机械要求 stop 价格永远只向盈利方向移动。如果新的结构需要更宽 stop，只允许：

```text
REDUCE quantity
→ recompute stress loss
→ verify new stress loss <= old stress loss
→ replace protection
```

如果未来 executor 无法原子、可靠地完成，则先关闭旧 tranche，再用新 receipt 建立新 tranche。绝不能先放宽 stop，再期待随后减仓。

### 9.2 不机械推到成本价

成本价与市场结构无关。若 breakeven stop 落在正常噪声内，优先实际 harvest 或减仓；不要用容易被扫出的保护位伪造“零风险”。

## 10. 动态止盈、部分落袋与 runner

定义 episode 的压力保底净值：

```text
Floor_t = RealizedNet_t
        + StressLiquidationNet(Q_remaining_t, stress_exit_t)

Giveback_t = PeakMarkedNet_t - Floor_t
```

到达路径里程碑后，求最小 harvest 数量 `h`：

```text
Floor_t(h, stress_exit_t) >= RequiredFloor_t
Q_remaining_t >= Q_runner_min
```

`RequiredFloor`、`Q_runner_min` 和 milestone 比例属于 policy arm，不是稳定理论常数。

### 10.1 路径条件表

| 市场路径 | 动态管理重点 |
|---|---|
| 趋势稳定、假说完整、波动正常 | 少量或暂不 harvest；给 runner 合理空间 |
| 顺势波动扩张 | 先部分落袋，再保留较宽 runner |
| 到达结构目标、继续性一般 | harvest 至正的压力保底净值 |
| 衰竭、反向主动流或拥挤反转 | 加大 harvest、收紧或关闭 |
| RANGE / 均值回归 | 结构目标优先，runner 较小 |
| 未建模重大事件临近 | 大幅降低或关闭 |
| hard falsifier | 全部关闭，不因已有浮盈继续持有 |

### 10.2 高收益时的处理原则

- 高收益必须至少比较“继续全持有”“部分兑现 + runner”“全部退出”三条路径；
- 在收益已显著扩大而继续性没有同步增强时，优先把一部分利润变成已实现净值；
- harvest 后无新证据不得立刻加回；
- 费用、滑点和 funding 后仍为正，才称为“锁定”；
- runner 的目标是保留右尾，不是把全部已得收益重新暴露；
- 首个目标位全平与完全不止盈都只是 policy arm，需要未来前瞻比较，不能先验宣布胜出。

经纪商教育资料提供 partial harvest、core、trailing stop 和 time exit 的成熟实践示例，但不构成盈利证明。[Fidelity：Managing Positions](https://www.fidelity.com/learning-center/trading-investing/trading/managing-positions)、[Fidelity：Exit Strategies](https://www.fidelity.com/learning-center/trading-investing/trading/exit-strategies)

## 11. 路径驱动的实时重规划

每次增量更新只检查发生变化的维度：

```text
price path
hypothesis support/falsifier
volatility and liquidity
time and scheduled event
leverage/crowding
portfolio dependency
actual fills and position truth (future ACCOUNT only)
```

| 变化 | reference plan | 未来账户动作 |
|---|---|---|
| 结构明确、证据尚弱 | `SEED` | 仅在账户门通过后最小风险 |
| fresh 独立支持 | `CORE / ADD` 候选 | 重算所有上限后才增加 |
| 只有浮盈 | `HOLD / HARVEST` | 不自动加仓 |
| 软反证 | `REDUCE / TIGHTEN` | reduce-only |
| hard falsifier | `CLOSE` | 紧急关闭并对账 |
| 波动上升 | 减少 reference quantity | 减仓，不维持固定名义 |
| 波动下降 | 不自动放大 | 新决策和新预算后才增加 |
| 高收益且趋势仍在 | `PARTIAL_HARVEST + RUNNER` | 先兑现部分，再留 runner |
| runner giveback 超 policy | `REDUCE / CLOSE` | 保护触发并对账 |
| 事件未建模 | 降级或关闭 | 不新增暴露 |
| 相关风险上升 | 减边际风险最高计划 | 组合减仓 |
| 可选数据缺失 | UNKNOWN，分析继续 | 缺执行真值则 no-execute |

同一时点 `CLOSE` 支配 `REDUCE`，风险减少支配新增风险。Agent 偏好不能覆盖 hard falsifier、组合超限或账户真值。

## 12. 再入场与同类失败

固定“24 小时、两次”不是稳定理论。再入场取决于失败类型、新证据和剩余风险：

```text
B_reentry_remaining = max(
  0,
  B_episode_cap
  - Loss_closed_reference_or_actual
  - Risk_reserved_open
)
```

| 上次退出原因 | 再入场条件 |
|---|---|
| 正常噪声 stop，父 thesis 仍存续 | 退出后出现 fresh confirmation，只允许 SEED |
| 假突破后重新夺回结构 | 需要价格以外的机制差异证据 |
| 时间到期 | 新信息改变原路径期限，不能只重启时钟 |
| hard falsification | 禁止同方向，直至建立新 thesis/episode |
| 流动性或执行故障 | 研究可继续；executor 保持关闭 |
| 同一 failure cluster 重复 | 无新机制证据则禁止 |
| 新反向假说成立 | 先关旧方向，再独立建新 episode |

attempt count 只作诊断，不自动决定是否再入场。稳定停止线是风险耗尽、同类失败无新证据、hard falsification。cooldown 应绑定新闭合 bar、事件结束或结构重新成立，不绑定任意固定时钟。

## 13. Drawdown、相关性与组合风险

### 13.1 未来账户 drawdown

```text
H_t  = max_{u<=t}(Equity_u)
DD_t = 1 - Equity_t / H_t
```

未来账户层可按权益距离高水位保护线的剩余空间收缩暴露；参数属于账户 policy，不能由 Agent临时填写。[Grossman 与 Zhou](https://onlinelibrary.wiley.com/doi/10.1111/j.1467-9965.1993.tb00044.x)

当前 research 不使用模拟 PnL 触发账户 drawdown。它只记录 reference episode 的连续错误和压力损失，用于比较 policy，而非冒充账户安全。

### 13.2 协方差贡献与压力场景并用

```text
portfolio_vol = sqrt(w' Σ w)
MRC_i = (Σw)_i / portfolio_vol
RC_i  = w_i × MRC_i

PortfolioStressLoss = max_{scenario in Ω} sum_i Loss_i(scenario)
```

风险贡献用于识别正常状态集中度；压力场景用于覆盖相关性、流动性和 venue 在尾部共同恶化。至少包括：

- BTC/市场 beta 同向冲击；
- 相关性向 1 收敛；
- 波动跳升与 spread 扩张；
- 同 venue/API/托管故障；
- funding、拥挤和清算同时恶化；
- gap 或 stop-through；
- stablecoin、抵押品或预言机冲击；
- 多个“不同假说”共享同一价格和流动性因子。

正常期 rolling correlation 不能独自证明分散化；尾部相关性可能上升。[Longin 与 Solnik](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00340)、[风险贡献方法](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1271972)

### 13.3 组合冲突裁决

当多个计划争夺同一预算时，优先保留：

1. 数据和合约身份更可靠；
2. 失效位更清楚且压力损失可定义；
3. 与既有 exposure 依赖更少；
4. 路径已获得新机制证据；
5. 流动性和退出能力更好；
6. opportunity cost 更低。

不使用未经校准的概率或 EV 排序。

## 14. 完整仓位规划路线

```text
1. 读取 MarketState、竞争假说、动作全集和已有 exposure
2. 明确 episode、方向、decision horizon 与 policy_version
3. 写 structural invalidation、protective trigger、stress exit
4. 计算单位压力损失；成本或缺失项用有界压力值/UNKNOWN
5. 按 episode、symbol、cluster、portfolio 上限得到可用预算
6. 先生成 SEED；再预注册 CORE/ADD 的 fresh-evidence 条件
7. 为每个 tranche 写独立风险、expiry、目标和 falsifier
8. 预注册至少一个 harvest milestone 和一个 runner policy
9. 比较全持、部分兑现、全平、WAIT/OTHER 的机会成本
10. 通过风险单调性和依赖集中度检查
11. 封存 PositionPlan；未授权时 executable_quantity=null
12. 增量轮只在新事实到达时做 PositionTransition
13. 到期后用统一 outcome 口径计算路径指标并进入 Review
```

## 15. 评价接口

一个 position policy 是否更好，必须在未来前瞻、同口径样本中比较，不能从少数成功案例判断。Review 至少接收：

```text
MAE                         最大不利变动
MFE                         最大有利变动
realized_or_reference_net   净结果
capture_ratio               已实现净值 / 可定义的 MFE 价值
giveback                    peak marked net - final floor/net
time_in_risk                暴露时间
stress_budget_used          使用的压力预算
stop_through                触发与实现价差
harvest_contribution        部分兑现贡献
runner_contribution         runner 贡献
reentry_contribution        再入场的独立贡献
opportunity_cost            相对当时合法备选动作
```

`MFE` 是事后诊断，不得在决策时反向选择最优 exit。固定目标、trailing、partial+runner、时间退出和结构退出应作为不同 policy arms；只有前瞻结果足够后才能保留或淘汰。

## 16. 冲突裁决顺序

```text
真实账户与执行安全（未来）
> hard falsifier
> 组合、流动性与场所超限
> 事件/时间到期
> 软证据变化
> 盈利优化
> Agent 偏好
```

风险模块只能否决不可定义或未经授权的执行损失，不能以“分析不完整”为由抹掉市场认知。可选数据缺失通常使对应结论降级、仓位缩小或执行映射为 `NOT_READY`，而不是让整个系统停止。

## 17. Policy 参数治理

任何固定参数必须位于：

```text
PositionPolicy
  policy_version
  parameter_name
  value_or_range
  applicable_regime
  applicable_horizon
  rationale
  evidence_level
  status: UNVALIDATED | CANDIDATE | RETAINED | REJECTED
  effective_from
```

以下不能写回稳定理论常量：

- 固定 `LOW=0.5 / HIGH=1.0`；
- 统一账户百分比；
- 固定 ATR 倍数；
- 固定 harvest/runner 比例；
- 固定 cooldown 小时数或 reentry 次数；
- 统一 trailing 距离；
- 统一 drawdown 分档。

社区参数或单次回测的最优点只产生候选 policy。参数选择应偏向跨状态稳定平台，而非热图最高单元；仍需未来前瞻验证。

## 18. 已知失效边界

- 不存在所有 regime 通用的 stop、take-profit、ATR 倍数或 harvest 比例。
- CME 教学比例、Turtle 单位和社区模板都不能复制为市场定律。
- 无校准概率时不得用 Kelly、EV 或胜率驱动仓位。
- 波动缩放控制风险，不证明预测增量。
- partial harvest 与 runner 是候选政策，不保证优于全平。
- 价格上涨不是独立证据；亏损更不是加仓理由。
- 多个共享价格、venue、beta 的假说不能制造分散化。
- rolling covariance 在尾部可能失效，必须配压力场景。
- stop trigger、order ACK、fill 和 position truth 不相等。
- 当前无账户、fill 和真实费用时，只能输出 reference plan。
- 可选市场数据缺失不终止认知，但会降低相关结论和执行就绪度。

## 19. 研究与社区参考的采用方式

成熟文献和机构教育只提供机制、公式与工程先例；社区只提供容易忽略的问题，不提供有效性结论：

- [Moreira & Muir：Volatility-Managed Portfolios](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12513)
- [Moskowitz, Ooi & Pedersen：Time Series Momentum](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf)
- [Kaminski & Lo：When Do Stop-Loss Rules Stop Losses?](https://www.sciencedirect.com/science/article/abs/pii/S138641811300030X)
- [CME：Proper Position Size](https://www.cmegroup.com/education/courses/trade-and-risk-management/proper-position-size)
- [Fidelity：Managing Positions](https://www.fidelity.com/learning-center/trading-investing/trading/managing-positions)
- [社区 ATR/退出参数讨论](https://www.reddit.com/r/Daytrading/comments/1rzvsam/i_simulated_every_stoploss_level_from_05_to_4_atr/)：采用“警惕小样本、单点最优和 regime 过拟合”这一问题，不采用其数值。
- [社区 fixed TP 与 runner 讨论](https://www.reddit.com/r/Daytrading/comments/1rfomiy/i_stopped_using_a_take_profit_my_average_winning/)：采用“按 regime 比较 policy arms”，不宣布任一方案普适。

社区票数会变化，热度不等于重复性、预测增量或收益。
