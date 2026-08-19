# V3.4.0 战略市场认知协议

## 1. 四周期是一套结构，不是四套独立交易系统

| 周期 | 当前职责 | 能改变什么 | 不能独立做什么 |
|---|---|---|---|
| 1D+ | regime、长期供需与尾部 | 影响下一 4H committee 的战略重建 | 精细执行 |
| 4H | 最低市场决策 authority、CORE thesis | WAIT/HOLD/OPEN/ADD/REDUCE/HARVEST/EXIT 的新计划 | 被更低周期自动覆盖 |
| 1H | 4H 内部 hypothesis evidence | 为下一 4H committee 提供 continuation/damage 证据；可触发已冻结的本地条件 | 唤醒 LLM、新建/反转 thesis、普通全平 CORE |
| 15m/5m | 内部路径、activation/执行证据 | 评价局部假突破、成交与预授权条件 | 独立 LLM 交易判断 |

每层至少维护 lower/upper、角色、当前相对位置、宽度相对本周期波动、break 的候选含义，以及怎样的 4H/1D 事实才会升级为战略变化。

## 2. 趋势阶段必须显式

至少比较：

```text
EXPANSION / ACCELERATION
PULLBACK / RESET
CONSOLIDATION / RE-ACCUMULATION
EXHAUSTION
REVERSAL_CANDIDATE
RANGE / NO_CLEAR_TREND
```

低周期破位首先被解释为 4H 内部路径证据。Agent 在下一个 committee 才决定它是否已经累计成 4H invalidation，而不是一看到 15m/1H 变化就重新发明动作。

## 3. 未来分析必须有时间与空间

FORECAST_ONLY 至少冻结 4H/12H/24H 三个 horizon：expected direction/path、target zone、invalidation condition。可交易阶段还必须回答主要 target、right-tail、正常回撤、strategic invalidation、catastrophic area、潜在 squeeze/cascade/liquidity vacuum，以及继续持有与现在退出的机会成本。

核心表达仍是：

```text
IF observable condition
THEN expected sequence
WHILE normal internal volatility may reach ...
UNLESS strategic invalidation ...
ALTERNATIVE ...
NEXT discriminating observation ...
```

## 4. 人群与约束驱动行为

至少考虑：可能成本区、realized/unrealized 状态、可观察的 leverage/stop/liquidation pressure、什么价格/时间/事件会使其 add/reduce/cover/chase/capitulate。输出使用 `SUPPORTED/PLAUSIBLE/WEAK/UNKNOWN` 一类相对证据语言，不伪造精确参与者身份。

应持续问：

- 哪个区域可能让已有多头从持有转为集中落袋？
- 哪个区域可能使空头回补或新空头入场？
- 上涨来自新需求、short covering、流动性真空还是事件重定价？
- 哪个下一观察最能区分这些机制？

“主力谋算、诱多诱空”只能是竞争机制，必须同时给出普通流动性、套保、回补、venue 差异和数据质量等替代解释。

## 5. 事件、情绪与数据冲突

每个战略判断显式记录未来已知事件、突发消息状态、source freshness/coverage/proxy 边界，以及 price/volume/OI/funding/taker-flow/long-short proxy/cross-asset/news 是否一致。

冲突不能平均投票。先检查时间错位、不同人群、套保、short covering、流动性撤退、venue 差异和 source quality；无法区分保持竞争机制与 UNKNOWN。

## 6. Activity profile 的新用途

activity profile 仍按当前标的 PIT history 统计 HIGH/MEDIUM/LOW/UNKNOWN 时段，但**它不再决定 LLM wake**。V3.4 的 LLM wake 固定在 4H scheduler。activity profile 只用于：

- 判断过去四小时哪些内部变化信息权重高；
- committee 预注册哪些 intra-window 条件值得本地 executor 关注；
- 判断哪些低活动变化应作为 noise/down-weighted evidence；
- 未来 Post-V3.4 模型路由的成本权重。

这样避免“某时段活跃 → 每 15 分钟重新分析”重新进入系统。
