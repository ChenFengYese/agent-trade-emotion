# V3.4.0 多周期动态仓位控制

## 1. realized 与 unrealized 必须分开

```text
RealizedPnL   = 已经通过成交关闭的结果
UnrealizedPnL = 当前剩余仓位按冻结估值规则得到的浮动结果
MarkedPnL     = RealizedPnL + UnrealizedPnL
```

浮亏不是已实现亏损；浮盈也不是必须马上兑现。EXIT/HARVEST/REDUCE 的问题是：当前高周期 thesis、剩余右尾、最大损失和机会成本下，主动把多少浮动结果转为已实现结果是否更优。

## 2. 每个 4H committee 必须比较六种动作

```text
WAIT / HOLD / ADD / REDUCE / HARVEST / EXIT
```

不适用写原因。ADD/REDUCE/HARVEST 必须给出条件和数量，而不是只写“考虑加仓/减仓”。正确的长期 WAIT/HOLD 不因动作少而扣分。

## 3. 计划在 4H committee 冻结，盘中只执行条件

committee 形成：

```text
plan_revision_policy = FROZEN_UNTIL_NEXT_4H_COMMITTEE
```

本地 executor 可在两次 committee 间执行已经声明的 bounded OPEN/ADD/REDUCE/HARVEST/EXIT 条件，但不能修改条件、数量、方向或重新解释市场。LLM 在 intra-window 没有 market-action authority。

因此 1H/15m 可以成为**预授权条件的 observation**，但不是新的决策周期。例如 4H committee 可以预先写“若 1H continuation 以 X/Y/Z 证据确认，则 ADD 0.15；若 1H damage 但 4H 尚未失效，则 REDUCE 0.20”，执行时无需重新调用 LLM。

## 4. 趋势盈利采用阶梯管理

```text
initial CORE
→ fresh high-frame confirmation
→ optional bounded ADD / HOLD
→ new 4H floor forms
→ raise structural protection
→ meaningful target / extension
→ HARVEST part + keep RUNNER
→ next 4H committee re-evaluates
→ exhaustion / strategic invalidation
→ EXIT remainder
```

小幅浮盈不是全平理由；保护上移跟随新 4H/1D 结构和剩余风险，不机械移到成本价。

## 5. 破位的权限

普通 15m/1H break 只形成 evidence，不能单独 `EXIT_CORE/EXIT_ALL`。它可以触发上次 committee 已预授权的 REDUCE/HARVEST/FREEZE_ADD。4H committee 才拥有普通 CORE thesis 的新 EXIT/REPLACE 权限。预注册 catastrophic/emergency 条件例外，但安全系统只能去风险。

## 6. ADD/REDUCE/HARVEST 的含义

ADD 需要 fresh evidence、更好几何、事件改变或已释放风险，并必须重新计算整个 episode 风险；禁止追涨和摊平式自动加仓。

REDUCE 适用于竞争路径增强、volatility/unknown tail 增加、事件前风险上升或 continuation 证据下降，但 4H thesis 尚未完全失效。

HARVEST 用于把部分浮盈转为 floor，同时保留 runner；它不是“盈利就退出”的同义词。

## 7. 风险几何必须能撑到下一 committee

对线性合约参考：

```text
StrategicRisk = |entry - strategic_invalidation| × qty × multiplier
CatastrophicRisk = |entry - catastrophic_protection| × qty × multiplier
WaitRisk = |entry - maximum_adverse_before_next_committee| × qty × multiplier

上述风险再加 round-trip cost stress 与 gap/impact stress。
```

必须满足：

```text
StrategicNetRisk <= MaximumLossBudget
CatastrophicRiskStress <= MaximumLossBudget
WaitToNextCommitteeRiskStress <= MaximumLossBudget
```

如果高周期结构需要更宽容忍，解决方式是降低 quantity，而不是把 stop 塞进普通 15m/1H noise。catastrophic protection 只是 fail-safe，不能保证实际成交恰好等于触发价。

## 8. 动态区间更新

下一 4H committee 必须对旧区域选择 `KEEP/WIDEN/NARROW/SHIFT/RETIRE/REBUILD`。单一精确价位不能因前文叙事一致性永久成为 thesis 开关。
