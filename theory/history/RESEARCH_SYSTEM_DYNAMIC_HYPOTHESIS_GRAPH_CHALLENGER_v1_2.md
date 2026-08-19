# 研究系统动态假说图 Challenger v1.2

> 状态：`E0_P0_1_CANDIDATE_NOT_ACCEPTED`
>
> 权威边界：本文件是 `CORE_TRADING_THEORY.v2.1` 之上的版本化 challenger，
> 不修改、不替换也不晋升当前 Core。它只定义研究假说与运行时假说图的对象、
> 不变量和未来验证接口，不证明任何市场机制、方向、收益、概率或可交易性。
>
> 路线：`RSR-P0.1-DYNAMIC-HYPOTHESIS-GRAPH-v1`
>
> 当前禁止：数据获取、adapter、replay、dataset、backtest、calibration、
> holdout、paper、部署、交易以及活动 G1 修改。

## 1. 理论增量

当前研究系统已经区分事实、测量、状态、机制、路径、交易、效用、权限、行动和
结果，但冻结 v1/v1.1 主要表达静态研究对象与合同边界，尚不能完整表达：

1. 同一机会窗口内多个运行时机制、路径和交易实例的独立生命周期；
2. 同一方向、同一终态情景或同一交易侧的不同可证伪路径；
3. 机制与路径的多对多兼容关系，以及明确的“不传递分数”边界；
4. 路径间的区分性证据、可识别性和下一观测计划；
5. 点时状态条件下的确定性生成、修订和不可改写 receipt；
6. `OTHER_PATH`、`UNKNOWN_PATH`、`CENSORED`、`ABSTAIN` 和
   `ARTIFACT` 的不同分母与对象域。

本 challenger 只关闭上述 E0 对象和合同表达缺口。它不声称运行时数据已存在，
也不因机器谓词与合成 fixture 的结构完整而关闭 `F-005 / DSP-022`。该 finding
只有在后续外部阶段门独立处置后才能改变。

## 2. 两个平面必须分离

### 2.1 研究平面

`ResearchHypothesis` 是静态、版本化的研究命题，例如：

> 在冻结的机会全集、信息集、比较器、成本和样本外协议下，有限路径竞争是否
> 比单一路径分类提供更好的校准、覆盖—风险或决策结果？

研究平面对象评价的是方法是否增加样本外价值。它具有研究 ID、版本、比较器、
测量合同、未来 evaluation gate 和不可变结果历史。

### 2.2 运行时平面

运行时平面包含三个机会特定的实例：

- `MechanismHypothesisInstance`，简称 MHI；
- `PathHypothesisInstance`，简称 PHI；
- `TradeHypothesisInstance`，简称 THI。

MHI、PHI 和 THI 不是 ResearchHypothesis 的新版本，也不能把一次运行结果写回
静态研究命题。研究平面决定哪些模板有资格被验证；运行时平面在冻结模板和当前
点时信息集下实例化对象。两者的关系是“研究规格约束运行时候选”，不是
“运行结果自动证明研究命题”。

### 2.3 禁止的别名

以下对象不得互相替代：

```text
ResearchHypothesis != MHI != PHI != THI
Mechanism != Path != TerminalScenario != TradeSide
EvidenceSupport != Probability != Utility != Permission
Result != RevisionReceipt
```

## 3. 确定性、点时、状态条件生成

对决策时刻 \(\tau\)，令点时生成输入为：

\[
G_\tau =
(
S_\tau,\ Z_\tau,\ Q_\tau,\ C_\tau,\ T,\ R_{k-1}
)
\]

其中：

- \(S_\tau\)：多周期状态 snapshot；
- \(Z_\tau\)：结构位置 snapshot；
- \(Q_\tau\)：数据质量 snapshot；
- \(C_\tau\)：时钟与 `available_at` snapshot；
- \(T\)：冻结的有限模板 registry；
- \(R_{k-1}\)：上一合法图修订 receipt。

生成函数为：

\[
\mathcal G(G_\tau)
\rightarrow
(\text{MHI},\text{PHI},\text{THI},E,R_k)
\]

且必须满足：

1. 相同规范输入产生字节可重建的相同模板选择和实例 identity；
2. 只评估 registry 中已注册模板；
3. 不允许 runtime、LLM 或人工临时创建 template；
4. 不允许对 primitive 取幂集或笛卡尔积生成路径；
5. 不允许看到 outcome 后选择或补写路径；
6. 只有预注册 refresh trigger 可创建新修订；
7. 每个新修订引用上一修订 digest；历史修订与 receipt 不回写；
8. backdated state、future evidence、clock unknown 或 registry drift 必须
   fail closed；
9. 生成失败、容量冲突或必要输入未知时输出 `UNKNOWN_PATH + ABSTAIN`，而不是
   选择性删除反向路径。

当前 P0.1 只验证上述纯函数合同，不提供生产 generator 或 runtime source。

## 4. 三层对象

### 4.1 MechanismHypothesisInstance

MHI 是非互斥的观察性解释候选。它至少绑定：

- 机会、实例和模板 identity；
- 生成修订；
- 激活、支持、软反证、硬失效与过期谓词；
- ordinal support；
- 可识别性 class；
- terminal 状态和 receipt tip。

同一观测可以同时支持多个 MHI。MHI 不能被解释为真实参与者身份、计划、意图或
因果真值。没有权威 truth label 或 identification design 时，允许的最强陈述是：

> 在当前冻结信息集中，该机制与观测相容，或暂时不可区分。

### 4.2 PathHypothesisInstance

PHI 描述一条可观察、有限、带期限的部分顺序演化。它至少绑定：

- 路径模板和实例 identity；
- 机会、修订和点时时钟；
- 激活和当前 milestone；
- 部分顺序、可跳过和可重复 milestone；
- terminal matcher 与 terminal cell；
- hard invalidation、expiry、status 和独立 ordinal support；
- evidence receipt tip。

### 4.3 TradeHypothesisInstance

THI 把一条 PHI 与位置、trigger、invalidation、expiry 和交易侧绑定。v1.2 的
最小 cardinality 是：

```text
THI --exactly one parent--> PHI
PHI --zero or more--> THI
```

多路径 composite trade 被明确延后。THI 中的 mechanism refs 只能是 context，
其 effect 固定为 `NONE`；机制分数不能进入交易支持、仓位、utility 或 permission。
P0.1 没有可用 Permission，所有行动均为 `ABSTAIN`，最大风险为零。

## 5. 路径 identity 与不可合并原则

路径 identity 由以下观察性合同决定：

1. 激活条件；
2. 必需和可选 partial-order edges；
3. repeat/skip 规则；
4. terminal matcher 和独立 terminal cell；
5. horizon；
6. hard invalidation；
7. expiry；
8. clock profile。

路径 identity **不由**以下内容决定：

- mechanism identity；
- mechanism 数量；
- LONG、SHORT 或 NONE side；
- 粗粒度终态方向；
- 自然语言名称。

令 \(I(P)\) 为上述 identity projection 的规范摘要。若两个注册路径
\(P_i,P_j\)：

\[
I(P_i)=I(P_j),\ i\ne j
\]

则它们是重复规格，必须在实例化前拒绝，不能以两个 ID 重复计数。

若：

\[
I(P_i)\ne I(P_j)
\]

则即使二者：

- 都映射 `DOWNSIDE`；
- 都生成 `SHORT`；
- 都兼容同一 mechanism；

仍必须保留为不同 PHI。其 support、hard invalidation、expiry、result history、
calibration 和 trade template 不得合并。

## 6. 终态路径 cell 与情景聚合

PHI 的 `terminal_cell_id` 是精确、可观测且事前注册的结果 cell。参与同一
competition scope 的 named terminal cells 必须无重叠；未命中任何 named cell 的
可观察市场结果进入 `OTHER_PATH`。

仅有不同的 cell ID 或不同的 resolution predicate ID，不能证明逻辑互斥。v1.2
采用同一个分区观测量 `OBS-FIRST-UNIQUE-TERMINAL-CELL-ID`：

1. 从 opportunity start 起，按 `available_at` 升序只扫描当时已可得的 closed
   observations；
2. 一个 path 只有在仍 active、完整满足 required partial order、resolution
   predicates 为真、且尚未 hard-invalidated 或 expired 时，才成为该时点的
   candidate match；
3. 最早只有一个 candidate match 的时点，将观测量赋值为该 path 的
   `terminal_cell_id`，并生成不可改写的 assignment receipt；
4. 若最早时点同时有两个或更多 candidate matches，结果进入
   `OTHER_PATH`，reason 固定为
   `AMBIGUOUS_SIMULTANEOUS_TERMINAL_MATCH`，禁止按 ID、分数或交易侧任选；
5. named assignment 后的更晚匹配可作为证据保留，但不得重写终态 label；
6. 到 master horizon 没有 named match 的可观察结果进入 `OTHER_PATH`；若必要
   观测本身不可得，则按 typed reason 进入 `UNKNOWN_PATH` 或 `CENSORED`，不得
   伪装成市场 residual。

每个 named terminal matcher 必须是同一分区观测量上的 `EQ` singleton，且
singleton value 精确等于本 path 的 `terminal_cell_id`。因为单值观测量在同一
assignment receipt 中不能同时等于两个不同 singleton，这才构成可机检的
pairwise-disjoint proof。

粗粒度 `TerminalScenario` 只用于下游聚合：

```text
多个独立 PHI terminal cells
  → UPSIDE / DOWNSIDE / RANGE / UNRESOLVED
```

多个 PHI 可以映射同一 `DOWNSIDE`，但聚合 receipt 必须保留：

- 每个 source path instance ID；
- path template ID；
- terminal cell ID；
- path receipt tip；
- aggregation rule version。

情景聚合不能删除、替代或反写 PHI，也不能成为 path identity。

## 7. 机制—路径—交易拓扑

### 7.1 MHI ↔ PHI

机制和路径是多对多关系：

```text
one MHI → zero or many PHI
one PHI → one or many compatible MHI
```

每一条 `MECHANISM_TO_PATH` edge 必须显式记录：

- source 和 target template；
- edge role；
- `transfer_mode=NO_SCORE_TRANSFER`。

机制支持不会自动提升路径。路径支持只来自直接 target PHI 的有效 evidence effect。

### 7.2 PHI → THI

每个 THI 只有一个 parent PHI。一个 PHI 可没有交易模板，也可有多个不同的
path-specific THI，例如不同 trigger 或 order geometry 的候选。当前 v1.2 不支持
多个 parent PHI 合成一个 THI。

### 7.3 不允许的穿透

以下传播均禁止：

```text
MHI score → PHI score
MHI score → THI score / side / size / utility / permission
PHI top rank → auto-create order
THI update → rewrite PHI
Scenario aggregation → rewrite PHI
```

跨层变化只能通过独立、typed edge 和新 revision receipt 被记录。

## 8. 当前 shock 四路径 crosswalk

用户经验不是固定八日规则，而是用于提取“候选路径—区分证据—后续更新”的
方法论。当前 queue 的四条路径被显式映射为：

| Research queue hypothesis | Runtime path template | terminal scenario | trade side |
|---|---|---|---|
| `H-SHOCK-ABSORPTION-01` | shock 后低下行效率、收回、更高低点、向上转换 | `UPSIDE` | `LONG` |
| `H-SHOCK-SQUEEZE-FAIL-01` | 反弹后不接受、形成更低高点或丢失 event VWAP、恢复下跌 | `DOWNSIDE` | `SHORT` |
| `H-SHOCK-BALANCE-01` | shock 后压缩、重叠旋转、区间维持或到期 | `RANGE` | `NONE` |
| `H-SHOCK-SUPPORT-CONSUME-01` | 多次测试、反应衰减、有效破位、回收失败、下行扩张 | `DOWNSIDE` | `SHORT` |

其中两个 `DOWNSIDE/SHORT` 路径不能合并：

- squeeze-fail 的核心判别是“反弹未形成高周期接受，lower-high 或 event-VWAP
  loss”；其失效是“向上转换和 higher-low 被接受并维持”；
- support-consume 的核心判别是“反复测试后反应质量下降，effective break 后
  failed reclaim”；其失效是“快速 accepted reclaim 与 higher-low”。

它们拥有不同 partial order、terminal matcher、hard invalidation、expiry 和
trade trigger，因此 identity 不同，未来必须分别评价，不能用 pooled SHORT 结果
掩盖其中一条失败。

## 9. Evidence 原子 effect 与冲突

每个 evidence item 必须绑定：

- source 或 measurement identity；
- `available_at`；
- quality；
- lineage root；
- dependency group；
- expiry；
- 原子 per-target effect vector。

每个 target effect 只影响一个 exact MHI、PHI 或 THI instance，direction 为：

```text
SUPPORT
SOFT_CONTRADICTION
HARD_INVALIDATION
NO_EFFECT
```

约束如下：

1. 一条 underlying lineage 在同一 target 和 update 中最多贡献一次；
2. copied alias 或换 dependency group 不能形成独立证据；
3. malformed、future、stale、gap、conflicting-quality evidence 不更新 support；
4. hard invalidation 优先于任何 ordinal score；
5. invalidated 或 expired instance 不复活、不延长；
6. 同一 target、同一 dependency group 中等强反向证据必须产生
   `MATERIAL_CONFLICT` 或 `UNKNOWN_CONFLICT`；
7. 不能使用 evidence ID 的词典序消除语义冲突；
8. receipt 必须记录 accepted、rejected、conflicts、before/after digest 和上一
   receipt digest。

## 10. 区分性证据与可识别性

对尚未解决的两个路径 \(P_i,P_j\)，证据 \(e\) 只有在预注册 implication 不同
时才是区分性证据：

\[
\Delta(e,P_i)\ne\Delta(e,P_j)
\]

若二者 effect 相同，\(e\) 可以同时支持两个路径，但不提供 path discrimination。

每个 named path pair 必须满足：

- `terminal_identifiable=true`：在期限内存在互斥 terminal matcher；
- 若某 THI 在 resolution 之前偏好其中一条路径，还必须
  `decision_identifiable=true`；
- 若 deadline 前不存在合格区分证据，则 disposition 为
  `UNKNOWN_NOT_DECISION_IDENTIFIABLE`，不能强制 Top-1 或下单。

多个机制若在允许信息集中观察等价，必须进入预注册 mechanism
identifiability class。系统可以保留多机制相容，不能伪造唯一因果选择。

## 11. 下一观测计划

P0.1 的 next-observation plan 只输出确定性 ordinal 排名：

1. 是否在路径或交易 deadline 前可获得；
2. 是否通过 quality/PIT；
3. 能否对至少一对 unresolved path 产生不同 effect；
4. 观测成本等级；
5. 是否与已有 evidence 同 lineage/dependency。

输出示例：

```text
rank=1: accepted higher-low
rank=2: failed reclaim after effective break
rank=3: event-VWAP acceptance
```

该排名不是 Shannon information gain。只有在未来同时具备：

- 合法校准的 path probability；
- 合法校准的 \(P(E\mid P)\)；
- 支持域和 calibration receipt；

时才可能计算数值 information gain。P0.1 中 numeric IG、entropy reduction 或
pseudo-IG 全部禁止。

## 12. OTHER、UNKNOWN、CENSORED、ABSTAIN、ARTIFACT

五者必须分离：

| 名称 | 对象域 | 含义 | 可进入未来市场概率分母 |
|---|---|---|---|
| `OTHER_PATH` | market outcome residual | 可观察结果未命中任一 named terminal cell | 是，未来且仅在合法 calibration 后 |
| `UNKNOWN_PATH` | epistemic meta-node | 无有效信息集、竞争集或可识别性 | 否 |
| `CENSORED` | result labeling | gap、barrier ordering 或观察窗口使结果不可判 | 否，单独报告 denominator |
| `ABSTAIN` | action | 当前不采取新增风险行动 | 否 |
| `ARTIFACT` | data-quality | 数据、时钟、schema 或 venue 映射异常 | 否 |

禁止：

- 把 UNKNOWN 的质量缺失计入 OTHER 市场概率；
- 把 CENSORED 当作失败或市场路径；
- 把 ABSTAIN 当作路径或结果；
- 把 ARTIFACT 当作市场机制、路径支持或 utility weight；
- 从总 denominator 删除 UNKNOWN、CENSORED 或 ABSTAIN 机会来改善指标。

## 13. 未校准边界

当前 path 和 trade support 只允许 ordinal：

\[
q_h \in \{\text{LEADING, SUPPORTED, WEAK, UNSUPPORTED, UNKNOWN}\}
\]

P0.1 禁止：

- 将 ordinal softmax；
- 除以总分归一；
- 把 candidate assertion 写成 probability；
- 输出数字 EV、胜率、entropy 或 information gain；
- 将 mechanism support 放入任何 probability simplex；
- 将 `UNKNOWN_PATH` 放入市场 probability simplex。

未来合法 probability 只允许：

```text
named observable path terminal cells + OTHER_PATH
```

并须绑定完整 partition proof、calibration version、样本外 reliability receipt 和
支持域。Trade-success probability 还必须以 exact trigger 和一个 parent path 为
条件，不能与 path probability 混写。

## 14. 局部失败诊断和版本化

失败必须先归因到最小层：

```text
DATA_AVAILABILITY
→ MEASUREMENT
→ STATE
→ STRUCTURAL_POSITION
→ TEMPLATE_GENERATION
→ MECHANISM
→ PATH
→ DISCRIMINATION
→ TRADE_TRIGGER
→ COST_EXECUTION
→ CALIBRATION_SELECTION
→ PERMISSION_RISK
```

一条路径失败不能自动否定所有同方向路径；一个机制不可识别不能自动否定可观测
路径；一个 THI 失败不能反写 parent PHI。每次研究修订只改变一个 primary layer，
声明未改变的不变量，并使用新的 version、receipt 和未见 chronology。历史失败、
弱证据、矛盾、过期和 superseded 版本永久保留。

## 15. 事件驱动动态策略接口

本版本冻结的是 E0 接口和禁止条件，不是 replay 实现、参数或市场结论。
`PolicyEvent` 的唯一合法顺序是：

```text
(available_at ASC, source_sequence ASC, event_id ASC)
```

全量 bar 事后回填、未闭合高周期 bar、未来 high/low/close、未来 MFE/MAE 以及
favorable-first 同 bar 假设均不得进入当时的信息集。迟到修订只能成为新 event，
不能覆盖旧 event、旧 graph revision 或旧 receipt。重复 event 必须幂等，不能
产生第二次状态变化、effect 或 receipt。

每个 event 的状态向量固定为：

\[
\Sigma_i=(I_i,G_i,S_i,L_i,P_i,R_i,A_i,C_i)
\]

其中依次为 point-in-time information set、graph revision、policy state、
PositionLock、position、risk envelope、permission 和 receipt chain。状态转移为：

\[
F(\Sigma_i, e_i, \Pi)
\rightarrow
(\Sigma_{i+1},DecisionReceipt_i,Emissions_i)
\]

\(\Pi\) 是冻结 policy package。\(F\) 必须纯、确定且幂等；同一 state、event 和
package 产生同一规范输出。每个 admitted event 的固定链路为：

```text
PolicyEvent
→ PIT information set
→ state snapshot
→ graph revision 或 no-change receipt
→ THI revision 或 no-change receipt
→ policy action
→ DecisionReceipt
→ 必要时的 OrderIntent / PositionStateTransition
```

E0 只允许反事实 lane：

```text
FLAT → WATCH → PREPARE → CF_ENTRY_ELIGIBLE
→ CF_OPEN_LOCKED → CF_MANAGE → CF_EXITED
```

真实 `Permission=DENIED_P0_1`、真实 `Action=ABSTAIN`、`max_risk=0`。
`CF_` 对象只是将来可 replay 的决策载体，不是订单、paper fill 或执行证明。

### 15.1 NEW_RISK 与 POSITION_MANAGEMENT

策略动作严格分为：

- `NEW_RISK`：abstain、创建 entry intent、取消未成交 entry、以不增加声明风险的
  方式替换未成交 entry；
- `POSITION_MANAGEMENT`：仅 `KEEP / TIGHTEN / REDUCE / EXIT`。

创建 `CF_OPEN_LOCKED` 时生成不可变 `PositionLock`，锁定 opportunity、THI、
parent PHI、side、初始 quantity/stop/targets、horizon、总风险预算和 permission。
后续 graph/path 切换、迟到 event 或新叙事均不能改写它。

### 15.2 风险单调性

持仓后的可控计划风险只能不变或下降：

\[
|q_{i+1}|\le |q_i|
\]

在退出前 position sign 不变；LONG stop 只能不下降，SHORT stop 只能不上升；
horizon 不得延长；LONG target 不得外移上调，SHORT target 不得外移下调。

总风险使用或预留量定义为：

\[
R^{total}_i =
L^{realized}_i+
L^{open,worst}_i+
L^{pending,worst}_i+
Fees_i+Funding_i+TailReserve_i
\]

并要求：

\[
R^{total}_i \le R^{lock}
\]

不得遗漏 pending order、fee、funding 或 tail reserve；不能用最终盈利掩盖轨迹中
已经发生的 risk breach。gap 或 slippage 可能使实际损失超出计划上限，此时必须
记录显式 gap transition/breach，不能把它伪装为正常 `ENTER`、`KEEP` 或新的风险
许可。

### 15.3 路径切换不等于自动反手

leading path 改变最多触发原 THI 约束下的 KEEP、TIGHTEN、REDUCE 或 EXIT，不能
自动反向、加仓、救仓或退出后自动重入。相反方向的新风险必须同时具备：

1. 新 opportunity；
2. 新 THI，且仍只有一个 parent PHI；
3. 新的独立 Permission。

P0.1 中第三项永远不可用，因此只记录反事实状态，不产生行动。

## 16. 未来 trajectory evaluation 接口

未来 D2/D3/E2 必须在完全相同的 `PolicyEvent`、PIT 信息、opportunity denominator、
risk budget、fee/funding/slippage/fill model 和同 bar ambiguity rule 下比较：

1. `DYNAMIC_HYPOTHESIS_POLICY`；
2. `FROZEN_ENTRY_STATIC_EXIT`；
3. `SINGLE_PATH`；
4. `NO_TRADE`。

必须报告整条 trajectory，而非只报告 endpoint PnL。最少包括 path/graph revision、
leader switch、decision latency、entry/cancel/replace/fill、stop/target/horizon
revision、MFE、MAE、fee、slippage、funding、tail loss、轨迹内 risk breach、
abstain、coverage、UNKNOWN 和 CENSORED。

基线的精确参数、sample unit、独立 episode、总体和分层最小支持、
effect/non-inferiority margin、coverage/abstain/unknown/censored 限制、
calibration error、multiplicity、stability、chronology 和 one-time holdout receipt
当前全部为：

```text
UNSET_BLOCKS_E2
```

这意味着接口已定义，但 replay engine、baseline implementation、阈值和 evaluation
均未实现、未授权。任何 synthetic/E2 proxy 都不得称为执行、市场或盈利证明。

## 17. 理论来源与吸收边界

- [Hamilton (1989), DOI 10.2307/1912559](https://doi.org/10.2307/1912559)
  支持把不可直接观察的 regime 作为条件状态推断问题；不证明本系统的状态标签或
  交易价值。
- [Fearnhead & Liu (2007), DOI 10.1111/j.1467-9868.2007.00601.x](https://doi.org/10.1111/j.1467-9868.2007.00601.x)
  支持在线变点/分段更新的研究方向；不证明本系统变点可预测市场。
- [Blom & Bar-Shalom (1988), DOI 10.1109/9.1299](https://doi.org/10.1109/9.1299)
  支持多模型并行更新的工程类比；其模型 mixing/merging 不能作为本系统
  same-side path non-merge 的依据。
- [Gneiting & Raftery (2007), DOI 10.1198/016214506000001437](https://doi.org/10.1198/016214506000001437)
  支持未来概率预测采用 proper scoring 与 calibration；当前没有概率资格。
- [Naghshvar & Javidi (2013), DOI 10.1214/13-AOS1144](https://doi.org/10.1214/13-AOS1144)
  支持主动序贯区分观测的理论方向；当前 next observation 仍只是 ordinal plan。
- [Pearl (2009), DOI 10.1214/09-SS057](https://doi.org/10.1214/09-SS057)
  支持把观察相容性与因果识别严格分开；不能把 mechanism support 升格为主体意图
  或因果真值。

以上来源只支撑方法接口和认识论边界，不支撑市场有效性、正 EV、盈利或自动执行。

## 18. 组合验证连续性

v1.2 public validator 不是只验证三份新合同的孤立入口。它的 raw input 必须精确
包含冻结 v1.1 public validator 所需的 8 份文档，以及 3 份 v1.2 合同，共 11 份；
缺少或增加任一文件均先失败。

固定顺序是：

```text
exact 11-file raw set
→ public v1.1 validator over exact predecessor 8
→ require ACCEPTED / OK
→ require frozen v1.1 bundle digest
→ require exact predecessor raw bytes
→ validate three v1.2 contract canonical identities and semantics
→ compose one successor bundle identity
```

successor bundle identity 必须同时承诺：

1. 冻结 v1.1 bundle digest；
2. graph contract canonical identity；
3. template registry canonical identity；
4. evidence/evaluation contract canonical identity。

因此，任一 predecessor raw byte drift、v1.1 合同失败、v1.1 bundle identity
不一致、三份新合同任一失败、缺文件或多文件，都不能得到 v1.2
`ACCEPTED / OK`。v1.1 failure 通过明确的 wrapped reason 返回，不能被三份新合同
的成功掩盖；predecessor 验证也必须先于新合同解析。该组合验证只证明版本化合同
连续性，不把 v1/v1.1 的 E0 接受解释为市场证据或 later-stage 权限。

## 19. P0.1 合成验证能证明什么

合成和对抗测试可以证明：

- exact schema、identity、cross-reference 和摘要一致；
- 同侧不同路径不合并；
- 反向路径和 residual 不被静默裁剪；
- M↔P 多对多、M→P `NO_SCORE_TRANSFER`；
- THI exactly one parent；
- evidence atomic、lineage 去重、冲突保留；
- hard invalidation、expiry 和 revision monotonicity；
- OTHER/UNKNOWN/CENSORED/ABSTAIN/ARTIFACT 域分离；
- 未校准概率、EV 和 numeric IG 被拒绝；
- PolicyEvent 顺序、PIT、幂等和不可回写合同；
- PositionLock、路径切换与持仓风险单调合同；
- 同信息同成本 trajectory baseline 接口和未设阈值边界；
- 所有 later-stage permission 保持拒绝。

它不能证明：

- predicate 对现实市场的测量有效性；
- 四条路径有预测能力；
- 任一机制是真实原因；
- probability、EV、盈利或执行可行；
- F-005/DSP-022 已关闭；
- P0.1 已被外部阶段门接受。

## 20. 当前最大正面结论

若本 challenger、三份 JSON 合同、纯 validator、合成/对抗测试、独立 evidence
report 和 inventory 全部通过，当前最大结论仍只能是：

> 已形成一个可审计、有限、确定性、点时、同侧路径不合并、区分
> OTHER/UNKNOWN/CENSORED/ABSTAIN/ARTIFACT 且不会自我授权的 E0 动态假说图
> candidate，等待外部 Sol P0.1 完整阶段门。

不得表述为市场有效、预测成立、概率已校准、回测通过、paper ready、可部署或
可交易。
