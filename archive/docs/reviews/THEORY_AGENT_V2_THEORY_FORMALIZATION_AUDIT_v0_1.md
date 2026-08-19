# Theory Agent V2 理论形式化审查

> 版本：0.1  
> 状态：`E0_REVIEW_COMPLETE_FOR_CONTRACT_DRAFT`  
> 审查对象：Core v2.1、动态路径方法、动态假说图 challenger、治理 successor v2、
> SNDK 冻结事故审计与 V2 目标。  
> 边界：只审查理论和机器合同，不修改当前权威 Core v2.1，不授权交易。

## 1. 审查结论

当前理论并非缺少市场分析对象。Core v2.1 已经定义：

- 点时事实、测量、推断、假说、预测、政策、风险的分层；
- D/L/C/F/R/K 与多时间尺度职责；
- episode、有限机制竞争、动态路径、证据去重和 receipt；
- THI、风险预算、执行成本、barrier、horizon 和评价；
- 动态假说图的事件驱动纯函数接口。

缺口位于“市场路径理论”到“持续持仓政策”的最后编译段：

1. 当前 V1 明示不交易趋势延续；
2. episode、机会、trade attempt、lot 与战略状态没有形成一条统一生命周期；
3. 两段 entry stage 没有转换为 CORE/TACTICAL/HEDGE 的持仓意图；
4. target/horizon 被绑定到整笔离散交易，无法表达 tactical target 与 core management；
5. 风险/战术退出后没有持续恢复义务；
6. 几何只表达创建，缺少 regime 迁移后的版本化注销和替换；
7. `ABSTAIN` 没有 obligation，空仓机会成本也不进入功能评价；
8. 当前治理 v2 是 shadow validator，不是新决策核心。

因此，本次不是重写 D/L/C/F/R 或为 SNDK 添加例外，而是新增一个
`Continuous Strategic Decision Policy` challenger，把已存在的市场分析理论编译为
持久战略、仓位和执行合同。

## 2. 权威与版本处理

| 对象 | 当前地位 | V2 处理 |
|---|---|---|
| `CORE_TRADING_THEORY_v2_1.md` | 当前权威、E0 | 保持不变 |
| V1 absorption/range policy | BTC V1 有限策略 | 保留为 A 组 baseline |
| 通用动态路径章节 | 上位 E0 方法 | 作为 V2 路径与证据基础 |
| 动态假说图 v1.2 | 未接受 challenger | 复用对象/receipt 纪律，不冒充已晋级 |
| governance v2 shadow | 只读历史审查和纯 validator | 降级为 legacy audit adapter 候选 |
| 新连续决策合同 | 尚无 | 新建 `E0_CANDIDATE_NOT_ACCEPTED`，不替换 Core |

V2 不能静默修改 `T-001` 至 `T-036`。任何新政策使用独立 `CDP-*` claim，
只有经过未来独立治理和证据门后才可申请合并到更高版本 Core。

## 3. 核心冲突与解决

### 3.1 V1 不交易趋势延续

**现状：** Core v2.1 明示 V1 在趋势延续状态 `ABSTAIN`。  
**V2 需求：** 反弹兑现后继续比较趋势延续、回撤、衰竭与失败。  
**解决：**

- V2 是独立 challenger，不改变 V1；
- “趋势延续”先成为可管理已有 CORE 的 path，不自动授权趋势追价或新增风险；
- continuation reentry/new risk 仍需独立 THI、几何、成本和 permission；
- 未校准前只做离线 counterfactual，不产生 paper 权限。

### 3.2 `T-023` 与动态持有

**现状：** PRE_LOCK target 和 horizon 事前冻结；horizon 永不延长。Core
`T-023` 允许在 `PROFIT_LOCKED` 后，只有绝对剩余 EV 下界为正且相对立即退出
超过冻结 margin 时，按事前规则修订 target。动态假说图 challenger 则更严格地
禁止有利方向 target 外扩；二者存在待裁决冲突。  
**错误修复：** 到 target 后由 Agent 临时决定“这次再拿一会”。  
**解决：**

- 每个 lot/role 在入场前拥有独立 action contract；
- TACTICAL target 是真实 barrier，触及即按预注册撮合执行；
- CORE 可以在同价位注册 `MANAGEMENT_CHECKPOINT`，但没有事后移动的旧 target；
- V2 candidate 以当前权威 `T-023` 为上限：CORE 的 target 外扩只能在
  `PROFIT_LOCKED`、冻结 EV/margin 门、`GeometryRevisionReceipt` 和 execution
  ACK 全部成立时发生；ACK 前旧 barrier 继续有效；
- 当前 E0 没有合格概率和 EV，因此 target 外扩只能做 synthetic contract
  验证，不能获得 paper action authority；
- CORE 的 trailing、structure exit 和最大 horizon 都在入场前冻结；
- 任何新 geometry/THI 使用新 ID 和 receipt，不回写旧合同。

### 3.3 target 事件与真实成交

**现状事故：** 1H barrier 延迟使 1124.99 目标最终以 1215.46 市价退出。  
**解决：**

- `TargetReachedEvent` 不是“等 Agent 决定是否成交”；
- 若 target 是已注册 order/barrier，execution engine 先成交；
- strategy policy 只管理未被该 barrier 覆盖的剩余 CORE；
- OHLC 内顺序不可识别时使用预注册 conservative/low-timeframe/censored 规则。

### 3.4 entry stage 与 position role

`PROBE / POSITION_CONFIRMED` 描述入场证据阶段；`CORE / TACTICAL / HEDGE`
描述仓位政策角色。二者是正交字段：

```text
entry_stage ∈ {PROBE, CONFIRMED}
position_role ∈ {CORE, TACTICAL, HEDGE}
```

任何默认映射都必须由 policy registry 明示；不能假定 PROBE 必然 TACTICAL，
也不能因 CONFIRMED 自动成为 CORE。

### 3.5 单一状态枚举混合两个维度

用户要求的 `ACTIVE / CHALLENGED / RISK_REDUCED / REENTRY_PENDING /
INVALIDATED / CLOSED` 同时包含假说有效性和仓位敞口。

若全部塞入一个 enum，会出现：

- 战略 ACTIVE 但风险已减少；
- 战略 CHALLENGED 且当前完全空仓；
- 风险退出并不等于假说挑战；

等不可表达组合。

V2 使用两个 owner 独立的状态轴：

```text
strategic_status = ACTIVE | CHALLENGED | INVALIDATED | CLOSED
exposure_status  = INVESTED | RISK_REDUCED | REENTRY_PENDING | FLAT_CLOSED
```

同时提供用户所需的 derived workflow projection：

```text
ACTIVE | CHALLENGED | RISK_REDUCED |
REENTRY_PENDING | INVALIDATED | CLOSED
```

状态转换 receipt 必须分别写明两个轴的 before/after，防止风险动作污染战略状态。

### 3.6 episode、opportunity、path、trade 与 lot

冻结 cardinality：

```text
StrategicEpisode 1 ── n Opportunity
Opportunity      1 ── n MHI/PHI
PHI              1 ── n THI
THI              1 ── n PositionLot
StrategicEpisode 1 ── 0..n ReentryContract
```

- episode 是持续的战略市场阶段；
- opportunity 是一次可交易评估窗口；
- PHI 是可观察路径；
- THI 是一次 entry/management 尝试；
- lot 是风险与执行对象。

一次 trade target/stop 终止 THI 或 lot，不自动终止 episode。

### 3.7 reentry 与“自动反手/自动加仓”禁止

动态假说图要求新风险具有新 opportunity、THI 和 permission；这与
ReentryContract 不冲突：

- contract 只保存恢复义务、模式和最迟复核；
- condition hit 只创建 `ReentryEligibilityEvent`；
- 新风险仍需新 THI、geometry、risk permission；
- invalidated/closed、episode expiry、账户 risk kill 可取消合同；
- time review 强制重新评估，不强制下单。

### 3.8 风险单调性与 reentry

每个 `PositionLock` 内维持：

\[
|q_{i+1}|\le |q_i|,\quad R_i^{total}\le R^{lock}
\]

reentry 是新的 trade attempt，但不得重置 episode 累计风险：

\[
R_{episode}^{used}
=L_{realized}+R_{open}+R_{pending}+Fees+Funding+TailReserve
\le B_{episode}
\]

因此反复退出/重入不能通过换 THI 或 lot 重获完整预算。

### 3.9 动态几何与坐标漂移

动态几何不是修改旧 zone：

```text
Geometry.v1 --InvalidatedReceipt--> terminal
RegimeTransition + new structure
--GeometryBuildReceipt--> Geometry.v2
```

每个 geometry 必须绑定 created regime、anchor、validity clock、maximum
displacement、invalidators、replacement rule 和 source state digest。
价格远离旧 zone 只能使旧 geometry 到期/失效；新 geometry 是否可交易仍由
新 THI 与 permission 决定。

### 3.10 多路径竞争与数值概率

V2 初期继续使用 ordinal support，不因 SNDK 样本输出概率：

```text
LEADING / SUPPORTED / PLAUSIBLE / WEAK / INVALIDATED / UNKNOWN
```

primitive 支持不归一。只有未来拥有合法 partition proof、calibration 与
out-of-sample receipt 的 compound set 才允许概率和 EV。

### 3.11 空仓与 ABSTAIN

`ABSTAIN` 仍是无新增风险动作，但必须区分：

- `ABSTAIN_NO_OPPORTUNITY`：没有战略 opportunity；
- `ABSTAIN_RISK_OR_DATA_VETO`：风险/数据失败关闭；
- `ABSTAIN_WITH_OBLIGATION`：episode 仍有效，必须带 `review_by`、待观察条件和
  条件命中后的 use case。

它不会强制交易，但不能无限期无状态等待。

## 4. 新理论必须新增的机器不变量

| ID | 不变量 |
|---|---|
| `CDP-001` | 每个 symbol/episode 只有一条 accepted state revision chain |
| `CDP-002` | 下一事件必须引用 accepted prior state hash |
| `CDP-003` | strategic status 与 exposure status 分属不同 owner |
| `CDP-004` | 低时间尺度无 promotion/review receipt 不得改 strategic status |
| `CDP-005` | 每个 lot 必须有 role、episode、THI、risk budget 和 exit intent |
| `CDP-006` | tactical barrier 触发不能自动关闭 core 或 episode |
| `CDP-007` | 非 INVALIDATED/CLOSED 的全平必须原子生成 ReentryContract |
| `CDP-008` | reentry eligibility 不等于 permission |
| `CDP-009` | geometry 只能版本化替换，不能原地随现价重画 |
| `CDP-010` | stop/horizon/trailing 与 target-revision meta-policy 事前冻结；horizon 永不延长，target 外扩只允许通过 T-023 与 ACK |
| `CDP-011` | scheduler 不拥有战略时间；漏槽必须显式事件化 |
| `CDP-012` | registered barrier 由 execution engine 而非 Agent 心跳触发 |
| `CDP-013` | pause/authorization/prompt/policy hash 不一致时 fail closed |
| `CDP-014` | episode 累计风险不能由换 THI、lot 或 reentry 重置 |
| `CDP-015` | LLM 输出只有 PROPOSAL 权限，不能拥有状态或签发 receipt |
| `CDP-016` | 功能、预测、执行、收益和机会成本评价相互分离 |

## 5. 需要保持未知的参数

以下参数不能由 SNDK 已见样本决定：

- CORE/TACTICAL 分配比例；
- continuation、pullback、exhaustion 的升级阈值；
- trailing distance、minimum hold、maximum horizon；
- reentry 最小验证仓及分阶段规模；
- normal range、独立窗口数和确认组数；
- opportunity-cost penalty；
- scenario probability、EV threshold 和趋势捕获目标。

它们必须保留为 registry 参数、`UNSET_BLOCKS_ACTIVATION` 或跨场景离线
comparison 维度。

## 6. 理论审查后的允许结论

- 可以开始编写 V2 候选理论合同和详细架构；
- 可以实现 deterministic offline/shadow core 与 synthetic fixtures；
- 可以在 SNDK 24 轮上验证“状态是否连续、事件是否正确、合同是否生成”；
- 不能用该样本选择收益最优参数；
- 不能声明趋势延续或 reentry 提高真实市场收益；
- 不能恢复 automation 或接入 paper action authority。
