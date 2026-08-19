# 市场情绪十维序数量化标准 v1.2

> 状态：冻结，供 native Codex 市场最终 successor 使用  
> 理论边界：Core v2.1；不修改理论正文  
> 用途：公开数据、本地不可执行研究；不是概率、预测分数或下单信号  
> 取代范围：只取代后续新 run 的 v1.1；所有历史工件保持不可改写

## 1. 核心定义

市场情绪是十维状态向量，不是一个可以机械相加的总分。每一维只允许：

- `-2`：该轴的强负向状态；
- `-1`：该轴的负向状态；
- `0`：该轴平衡、方向未确认或证据冲突；
- `+1`：该轴的正向状态；
- `+2`：该轴的强正向状态；
- `null`：覆盖不足，结论为 `UNKNOWN`。

各轴正负必须按轴语义解释，禁止跨轴求和、加权成总分或转换为涨跌概率。`UNKNOWN` 不是 `0`；`0` 也不表示没有风险。任一同时包含正负贡献的轴都不能产生 `-2/+2` 强标签。

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
| `TIMEFRAME_COHERENCE` | 多周期空向一致 | 周期冲突或无方向 | 多周期多向一致 | `CANDLE_15M,CANDLE_1H,CANDLE_4H,CANDLE_1D` |

上述依赖组由 config 和确定性内核共同冻结。Agent 每轮必须原样提交，不能删减、替换或按当轮可得数据重定义覆盖率。

## 3. 直接数值事实的方向绑定

以下事实的正负号由确定性内核直接读取，Agent 不能反转：

- `candle-*-return-pct`；
- `book-top5-imbalance`；
- `recent-trade-side-imbalance`；
- `funding-rate`；
- `open-interest-change-pct`。

当 contributor 非零时，其 `ordinal_contribution` 必须与绑定数值同号；数值为零时不能提交非零贡献。对 `TIMEFRAME_COHERENCE`，四个周期收益率必须全部出现，每个贡献必须精确等于数值符号 `-1/0/+1`，且 `timeframe_states` 必须精确保存 `15m/1h/4h/1d` 四个对应状态。任何缺失、重复、符号反转或周期标签错配都在接受前失败关闭。

## 4. `TIMEFRAME_COHERENCE` 关系型聚合

该轴表达“多周期是否一致”，不能使用普通加法：

1. 同时存在正向和负向周期时，轴值固定为 `0`，冲突状态为 `CONTRADICTORY`；无论多数方向为何都不能形成强标签；
2. 四个必需周期全部观测且全部为正时为 `+2`；全部为负时为 `-2`；
3. 只有正向与零值，或覆盖未达到四周期完整时，最多为 `+1`；
4. 只有负向与零值，或覆盖未达到四周期完整时，最多为 `-1`；
5. 全部为零时为 `0/MIXED`；
6. 覆盖率低于 `0.5` 或没有有效 contributor 时仍为 `null/UNKNOWN_INSUFFICIENT_COVERAGE`。

## 5. 参与与流量的语义

成交量相对中位数表示参与强度，不表示买卖方向：

1. `candle-*-volume-vs-20bar-median` 只能提交 `ordinal_contribution=0 / direction=NEUTRAL`；
2. 低成交量意味着方向缺少参与确认，不能自动记为卖方负向；高成交量也不能自动记为买方正向；
3. 当前可用方向 contributor 仅为 `recent-trade-side-imbalance`，单次 REST 成交样本最多贡献 `-1/0/+1`；
4. 量价方向是否一致写入公开解释、假说影响和动作含义，不通过篡改成交量 contributor 的正负实现。

## 6. 跨周期 OI 变化合同

1. 第 1 周期只有绝对 `open-interest-btc`，`open-interest-change-pct` 必须为 UNKNOWN；绝对 OI 不能产生非零 `LEVERAGE_CHANGE` contributor；
2. 第 2 周期起，controller 只从上一已完成周期中读取 accepted state 绑定的 market snapshot；
3. controller 将上一周期 `open-interest-btc` 复制为当前快照中的 `prior-cycle-open-interest-btc`，保留上一原始响应路径、SHA-256、observed_at 和 available_at；
4. 当前与上一 OI 均为同一 instrument、同一官方来源且非缺失时，确定性生成 `open-interest-change-pct=(current/prior-1)*100`；
5. 派生 fact 必须位于当前快照，dependency group=`OPEN_INTEREST_CHANGE`，lineage 同时指向当前与上一 OI fact，并绑定上一 market snapshot digest；
6. 任一周期 OI 缺失、上一 snapshot 未完成或绑定不一致时，变化保持 UNKNOWN，不允许 Agent 从聊天或未绑定报告补算；
7. 在没有历史基线和清算证据时，OI 变化最多贡献 `-1/0/+1`。

## 7. 其他轴的确定性聚合

1. contributor 必须包含 `fact_id / ordinal_contribution / rule / direction`；
2. 同一 dependency group 在同一轴只能贡献一次；
3. 覆盖率为有效 contributor 的 dependency group 数除以该轴冻结必需组数；
4. 覆盖率小于 `0.5` 或没有有效 contributor 时，轴值为 `null / UNKNOWN_INSUFFICIENT_COVERAGE`；
5. 覆盖充分且只有单一非零方向时，贡献求和后截断到 `[-2,+2]`；
6. 同时存在正负 contributor 时标记 `CONTRADICTORY`，其和只能截断到 `[-1,+1]`，不能形成强标签；
7. 单一非零方向标记 `ALIGNED`；全部中性标记 `MIXED`；
8. 覆盖标签：`>=0.8 HIGH`、`>=0.5 MEDIUM`、其余 `LOW`；
9. 每轴记录时间周期状态、公开解释、局限和下一项区分性观测；source anchor 不能成为方向证据。

## 8. 强标签与金融解释限制

- 单一 REST 订单簿、近期成交、单点 funding 或单次 OI 变化最多贡献 `-1/0/+1`；
- 单次订单簿不证明流动性韧性；没有冻结波动基线时，原始 range 只能中性记录；
- 周期冲突、关键来源缺失、时点谱系不清或同源重复时必须降级或 UNKNOWN；
- 强标签只描述冻结序数规则下的轴状态，不表示统计显著、预测把握或仓位许可。

## 9. 每轮记录与证据边界

每轮必须保存完整 market snapshot、十维 sentiment state、原始值与来源、raw SHA-256、时间、质量、依赖组、谱系、覆盖、冲突、公开解释、假说/预期变化、三类合法动作比较和 WAIT 机会成本。overall 只允许文字综合，`overall_numeric_score=null`。

本标准只保证记录、方向绑定、关系型聚合和跨周期事实可复核。它不证明阈值已校准、情绪向量具有预测增量、策略盈利、生产就绪或真实交易权限。
