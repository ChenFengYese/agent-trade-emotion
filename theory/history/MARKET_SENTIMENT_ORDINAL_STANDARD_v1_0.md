# 市场情绪十维序数量化标准 v1.0

> 状态：冻结候选，供 native Codex 市场 successor 使用  
> 理论边界：Core v2.1；不修改理论正文  
> 用途：公开数据、本地不可执行研究；不是概率、预测分数或下单信号

## 1. 核心定义

市场情绪是十维状态向量，不是一个可以机械相加的“总分”。每一维只允许：

- `-2`：该轴的强负向状态；
- `-1`：该轴的负向状态；
- `0`：该轴平衡或证据冲突；
- `+1`：该轴的正向状态；
- `+2`：该轴的强正向状态；
- `null`：覆盖不足，结论为 `UNKNOWN`。

负向和正向必须按各轴语义解释。例如 `VOLATILITY_STRESS` 的正值表示波动环境较健康，不等于价格看多；因此禁止跨轴求和、加权成总分或转换为涨跌概率。

## 2. 十个轴

| 轴 | `-2` 语义 | `0` 语义 | `+2` 语义 | 当前可用输入 |
|---|---|---|---|---|
| `PRICE_DIRECTIONAL_PRESSURE` | 强空向推进 | 方向混合 | 强多向推进 | mark、15m/1h/4h/1d 闭合收益 |
| `STRUCTURE_PERSISTENCE` | 下行结构持续 | 无稳定结构 | 上行结构持续 | 多周期方向与延续 |
| `PARTICIPATION_AND_FLOW` | 卖方参与占优 | 双向或不确认 | 买方参与占优 | 成交量比、近期成交侧失衡 |
| `CROWDING_DIRECTION` | 空头拥挤 | 均衡或不可识别 | 多头拥挤 | funding、定位数据；缺定位数据时降覆盖 |
| `LEVERAGE_CHANGE` | 快速去杠杆 | 稳定或不可识别 | 风险敞口健康扩张 | OI 前向变化、清算；首轮仅绝对 OI 不得定向 |
| `LIQUIDITY_RESILIENCE` | 流动性脆弱 | 一般或未知 | 冲击后快速恢复 | spread、depth、impact 的时间序列；单次簿只能弱贡献 |
| `VOLATILITY_STRESS` | 极端压力/失序 | 常态或无基线 | 平稳可承受 | 多周期 range；无历史分位时不得给强标签 |
| `CROSS_MARKET_RISK_APPETITE` | 风险规避 | 混合 | 风险寻求 | 跨资产/宏观；未授权时 UNKNOWN |
| `EVENT_REACTION` | 事件后偏空/利好失败 | 无结论 | 事件后偏多/利空失败 | 新闻与事件反应；未授权时 UNKNOWN |
| `TIMEFRAME_COHERENCE` | 多周期空向一致 | 周期冲突 | 多周期多向一致 | 15m/1h/4h/1d 状态 |

## 3. 确定性聚合

每个轴由 Agent 提交 contributor，确定性内核只接受当前周期、来源绑定且非 UNKNOWN 的 fact：

1. 每个 contributor 必须包含 `fact_id / ordinal_contribution / rule / direction`；
2. 同一 dependency group 在同一轴只能贡献一次，避免同源数据重复计票；
3. 轴先冻结 `required_dependency_groups`，覆盖率为 `observed_group_count / required_group_count`；
4. 覆盖率小于 `0.5` 或没有有效 contributor 时，轴值必须为 `null / UNKNOWN_INSUFFICIENT_COVERAGE`；
5. 覆盖充分时，contributor 序数求和后截断到 `[-2, +2]`；
6. 同时存在正负 contributor 时标记 `CONTRADICTORY`；只有单一非零方向时为 `ALIGNED`；全部中性为 `MIXED`；
7. 覆盖标签：`>=0.8 HIGH`、`>=0.5 MEDIUM`、其余 `LOW`；
8. 每轴必须记录时间周期状态、Agent 解释、局限和下一项区分性观测。

## 4. 强标签限制

`+2/-2` 只表示某一轴在已冻结 contributor 规则下达到强序数状态，不代表统计显著、预测把握或仓位许可。存在以下任一情况时，Agent 应降低 contributor 或减少 required group 覆盖，不能用文字绕过：

- 只有单一 REST 订单簿或近期成交样本；
- 只有绝对 OI，没有同源前向变化；
- 没有历史分位却判断波动极端；
- 周期方向冲突；
- 关键来源缺失、陈旧或时间谱系不清；
- contributor 来自同一 dependency group。

## 5. 每轮必须保存的数据

每轮保存完整 `market_information_snapshot` 与 `multidimensional_market_sentiment_state`，包括：

- 每个 fact 的值、单位、周期、窗口、来源、raw 路径和 SHA-256；
- observed_at、available_at、质量、覆盖、dependency group、lineage、transform、局限与 missing reason；
- 每轴 contributor、支持/反对/中性/未知数、覆盖率、冲突状态、时间周期状态、解释和下一观察；
- overall 只允许公开文字综合；`overall_numeric_score=null`；
- `UNKNOWN` 不得当作中性或零，不得事后补造。

## 6. 证据边界

本标准保证记录和聚合可复核，不证明各 contributor 规则已校准，也不证明情绪向量具有预测增量。其市场有效性必须由冻结的前瞻周期数据另行评估；流程通过不等于盈利、生产就绪或真实交易权限。
