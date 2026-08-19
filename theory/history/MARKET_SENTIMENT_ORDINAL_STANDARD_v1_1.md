# 市场情绪十维序数量化标准 v1.1

> 状态：冻结，供 native Codex 市场第二 successor 使用  
> 理论边界：Core v2.1；不修改理论正文  
> 用途：公开数据、本地不可执行研究；不是概率、预测分数或下单信号  
> 取代范围：只取代失败 run 使用的 v1.0；历史工件不可改写

## 1. 核心定义

市场情绪是十维状态向量，不是一个可以机械相加的总分。每一维只允许：

- `-2`：该轴的强负向状态；
- `-1`：该轴的负向状态；
- `0`：该轴平衡、方向未确认或证据冲突；
- `+1`：该轴的正向状态；
- `+2`：该轴的强正向状态；
- `null`：覆盖不足，结论为 `UNKNOWN`。

各轴正负必须按轴语义解释，禁止跨轴求和、加权成总分或转换为涨跌概率。`UNKNOWN` 不是 `0`；`0` 也不表示没有风险。

## 2. 十个轴与冻结依赖组

| 轴 | 负向语义 | `0` 语义 | 正向语义 | 冻结必需 dependency groups |
|---|---|---|---|---|
| `PRICE_DIRECTIONAL_PRESSURE` | 空向推进 | 方向混合 | 多向推进 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D,BOOK_SNAPSHOT,TRADES_SNAPSHOT` |
| `STRUCTURE_PERSISTENCE` | 下行结构持续 | 无稳定结构 | 上行结构持续 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D` |
| `PARTICIPATION_AND_FLOW` | 卖方主动流主导 | 双向、低参与或方向未确认 | 买方主动流主导 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D,TRADES_SNAPSHOT` |
| `CROWDING_DIRECTION` | 空头支付/拥挤 | 均衡或不可识别 | 多头支付/拥挤 | `FUNDING_RATE,POSITIONING_SOURCE` |
| `LEVERAGE_CHANGE` | OI 收缩/去杠杆 | 稳定或不可识别 | OI 扩张/加杠杆 | `OPEN_INTEREST_CHANGE,LIQUIDATION_SOURCE` |
| `LIQUIDITY_RESILIENCE` | 流动性脆弱 | 一般或未知 | 冲击后恢复 | `BOOK_SNAPSHOT,BOOK_RESILIENCE_HISTORY,SPREAD_HISTORY` |
| `VOLATILITY_STRESS` | 压力/失序 | 无基线或混合 | 平稳可承受 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D,VOLATILITY_BASELINE,LIQUIDATION_SOURCE` |
| `CROSS_MARKET_RISK_APPETITE` | 风险规避 | 混合 | 风险寻求 | `CROSS_MARKET_SOURCE` |
| `EVENT_REACTION` | 事件后偏空/利好失败 | 无结论 | 事件后偏多/利空失败 | `NEWS_SOURCE` |
| `TIMEFRAME_COHERENCE` | 多周期空向一致 | 周期冲突 | 多周期多向一致 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D` |

上述依赖组由 config 和确定性内核共同冻结。Agent 每轮必须原样提交，不能删减、替换或按当轮可得数据重定义覆盖率。

## 3. 参与与流量的语义纠正

成交量相对中位数表示参与强度，不表示买卖方向：

1. `candle-*-volume-vs-20bar-median` 只能提交 `ordinal_contribution=0 / direction=NEUTRAL`；
2. 低成交量意味着方向缺少参与确认，不能自动记为卖方负向；高成交量也不能自动记为买方正向；
3. 当前可用方向 contributor 仅为 `recent-trade-side-imbalance`，单次 REST 成交样本最多贡献 `-1/0/+1`；
4. 量价方向是否一致写入公开解释、假说影响和动作含义，不通过篡改成交量 contributor 的正负实现；
5. 违反本节的 proposal 必须在 accept 前由确定性内核拒绝。

## 4. 跨周期 OI 变化合同

1. 第 1 周期只有绝对 `open-interest-btc`，`open-interest-change-pct` 必须为 UNKNOWN；绝对 OI 不能产生非零 `LEVERAGE_CHANGE` contributor；
2. 第 2 周期起，controller 只从上一已完成周期中读取 accepted state 绑定的 market snapshot；
3. controller 将上一周期 `open-interest-btc` 复制为当前快照中的 `prior-cycle-open-interest-btc`，保留上一原始响应路径、SHA-256、observed_at 和 available_at；
4. 当前与上一 OI 均为同一 instrument、同一官方来源且非缺失时，确定性生成：`open-interest-change-pct=(current/prior-1)*100`；
5. 派生 fact 必须位于当前 `market_information_snapshot`，dependency group=`OPEN_INTEREST_CHANGE`，lineage 同时指向当前与上一 OI fact，并绑定上一 market snapshot digest；
6. 任一周期 OI 缺失、上一 snapshot 未完成或绑定不一致时，变化保持 UNKNOWN，不允许 Agent 从聊天或未绑定报告补算；
7. 在没有历史基线和清算证据时，OI 变化最多贡献 `-1/0/+1`，不得给强标签。

## 5. 确定性聚合

1. contributor 必须包含 `fact_id / ordinal_contribution / rule / direction`；
2. 同一 dependency group 在同一轴只能贡献一次；
3. 覆盖率为有效 contributor 的 dependency group 数除以该轴冻结必需组数；
4. 覆盖率小于 `0.5` 或没有有效 contributor 时，轴值为 `null / UNKNOWN_INSUFFICIENT_COVERAGE`；
5. 覆盖充分时，contributor 序数求和后截断到 `[-2,+2]`；
6. 同时存在正负 contributor 标记 `CONTRADICTORY`；单一非零方向标记 `ALIGNED`；全部中性标记 `MIXED`；
7. 覆盖标签：`>=0.8 HIGH`、`>=0.5 MEDIUM`、其余 `LOW`；
8. 每轴记录时间周期状态、公开解释、局限和下一项区分性观测；
9. source anchor 不能成为 contributor、假说或候选动作的方向证据。

## 6. 其他强标签限制

- 单一 REST 订单簿在 `LIQUIDITY_RESILIENCE` 最多贡献 `-1/0/+1`，且不足以证明韧性；
- 单点 funding 在 `CROWDING_DIRECTION` 最多贡献 `-1/0/+1`；
- 没有冻结波动基线时，原始 range fact 只能中性记录，不能自行给压力方向；
- 周期方向冲突、关键来源缺失、时点谱系不清或同源重复时必须降级或 UNKNOWN；
- 强标签只描述冻结序数规则下的轴状态，不表示统计显著、预测把握或仓位许可。

## 7. 每轮必须保存的数据

每轮保存完整 `market_information_snapshot` 与 `multidimensional_market_sentiment_state`：

- fact 的值、单位、周期、窗口、来源、raw 路径与 SHA-256；
- observed_at、available_at、质量、覆盖、dependency group、lineage、transform、局限和 missing reason；
- 跨周期派生 fact 的上一 snapshot digest 与双亲 lineage；
- 每轴 contributor、支持/反对/中性/未知数、覆盖率、冲突、时间周期状态、解释和下一观察；
- overall 只允许公开文字综合，`overall_numeric_score=null`；
- 动态假说和预期的 CREATE/UPDATE/CLOSE，以及完整 WAIT/OPEN_LONG/OPEN_SHORT 比较。

## 8. 证据边界

本标准保证记录、覆盖和聚合可复核，并关闭已知的参与方向与跨周期 OI 谱系失败。它不证明 contributor 阈值已校准，不证明情绪向量有预测增量，也不证明收益、生产就绪或真实交易权限。
