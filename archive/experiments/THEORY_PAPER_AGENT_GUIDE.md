# 新理论 72 小时市场分析与纸面交易 Agent 指南

状态：`EXPERIMENTAL / PAPER_ONLY / NOT_LIVE_AUTHORIZATION`

本指南是当前理论的实践覆盖层，不修改、放宽或取代既有 E0 权威契约。它只允许读取公开数据、生成分析、维护本地纸面账户和写入审计记录；不得读取交易所账户、使用 API 密钥或提交真实订单。

## 1. 实验目标与边界

目标是在 72 小时内，按小时对 `SNDKUSDT`、`MUUSDT`、`BTCUSDT`、`ETHUSDT`、`SOLUSDT`、`HYPEUSDT` 做一致的事实冻结、技术与订单流测量、竞争假说、点位与风险规划、纸面决策及事后复盘。

主要检验对象是：

1. 多尺度状态、结构位置和点位寻找；
2. `D/L/C/F/R/K` 证据的联合解释；
3. 市场情绪与行为主体的可证伪推断；
4. 竞争路径、触发、否证与更新；
5. 入场、止损、止盈、仓位和组合风险；
6. 消息与价格反应的时序关联；
7. 持续决策、复盘和方法论修订。

72 小时只能提供描述性实践结果，不能证明理论有因果效力、预测效力或持续盈利能力。盈利是目标，不是验收时可以预先保证的结果。

正式实验使用 `LIVE_WALL_CLOCK`：初始化、每小时周期、决策、复盘与终结都必须贴近真实墙钟，不能用当前公开响应回填历史周期，也不能预填未来时间快速制造 72 小时结果。测试回放只能标为 `SIMULATED_CLOCK_TEST_ONLY`，即使覆盖完整也不能获得真实市场实践结论。

`SNDKUSDT` 和 `MUUSDT` 在本实验中是 Binance USDⓈ-M 股票永续衍生品，不是美股现货所有权。底层美股闭市时必须降低对现货价格发现和新闻因果解释的权重。

## 2. 每小时固定流程

每轮严格按以下次序执行：

1. 冻结决策时点，只使用该时点前已可得的数据和已闭合 K 线。
2. 抓取六标的公开行情、K 线、订单簿快照、近期主动成交、OI、资金费、多空结构和可得强平信息。
3. 抓取新闻标题元数据，并优先核对公司 IR、SEC、央行、项目方和交易所等一手来源。
4. 先列事实，再列确定性测量，再列推断。不得把推断回写成事实。
5. 形成 `15m / 1h / 4h / 1d` 多尺度状态；`1w` 只作可选背景。
6. 标出支撑、阻力、失效区、事件锚点和相对结构位置。
7. 同时保留上涨、下跌、反转、突破、区间及残余路径，不得只讲一个方向。
8. 每条主要路径必须写出支持证据、冲突证据、触发条件、否证条件、到期时间和下一观测。
9. 对“不同人群在做什么”的判断只能写为行为一致性假说，并给出替代解释。成交笔数不是人数，顶级账户不是已识别机构，OI 没有单独的方向真值。
10. 生成每标的行动与组合行动。即使 `ABSTAIN`，也必须有明确原因、解除阻塞所需观测和到期时点。
11. 新增风险必须有一个父路径、完整触发、结构失效止损、目标、成本后至少 `1.5R` 和风险预算。
12. 提交纸面决策，记录实际撮合、手续费、滑点、MFE、MAE 和归因。

公开新闻发现项必须精确绑定冻结的标题、URL、发布时间、抓取时间和内容摘要哈希；外部核验的一手来源必须另标 `OFFICIAL_PRIMARY / EXTERNAL_OFFICIAL_VERIFICATION`。新闻只能形成“时间上相关的待验证解释”，不能从同日或先后关系直接推出因果。

单次订单簿快照不能证明严格的流动性韧性 `R`；缺少连续深度序列时必须记为 `UNKNOWN`。强平接口缺失不能写成“零强平”。

## 3. 积极实践而不是无期限观望

系统必须积极提出可证伪假说，但“积极”不等于越过数据和风险硬约束。

当连续 6 个数据有效的组合小时没有策略成交时，若至少一条路径满足完整触发、无硬失效、止损与目标完整、成本后 `RR >= 1.5`，允许一个风险不超过权益 `0.15%`、名义价值 100–250 USDT 的 `EXPLORATION_PROBE`。

到达该门槛后，文字中的“准备探针”不算执行。必须提交一个与高层 `OPEN/ADD + EXECUTE_NOW`、同一方向、同一候选路径和同一几何完全绑定的低层纸面订单；若所有标的均不可执行，则必须用枚举化的 `DATA_INVALID / RISK_VETO / NOT_ACTIONABLE` 和冻结证据满足安全否决门。

若连完整路径都没有，不得随机开仓；必须：

- 明确卡在数据、测量、状态、结构、路径、触发、成本还是风险层；
- 在理论与方法评分中扣分；
- 给出下一小时能够解除阻塞的具体观测或公式修订候选。

## 4. 初始仓位、挂单和混乱交易

初始仓位属于 `EXOGENOUS_INITIAL_POSITION`，理论只从当前时点起对管理负责，不能追溯宣称这些入场由理论产生。

初始挂单属于 `USER_INITIAL_PLAN / REVIEW_REQUIRED`。首个有效周期必须逐单保留、改价或取消；激活前不参与撮合。反向单先平掉现有方向，只有超出部分拥有新的独立路径、权限、止损和目标时才允许反手。

初始仓位没有止盈止损。首个有效周期必须为每个仓位设置结构保护，或减仓、退出。使用 ATR 兜底保护时标记 `FALLBACK_STOP` 并扣减结构评分。

自动和手工混乱交易属于 `EXOGENOUS_EMOTION_INJECTION`：

- 入场不能计入理论择时成绩；
- 后续风险管理可以计入仓位管理成绩；
- 未来自动注入时点不出现在分析包；
- 仍受绝对组合风险上限；
- 一个有效周期内未保护时必须减仓或退出并触发硬扣分。

`.sealed-chaos.json` 的未来时点只做分析包层面的隐藏。它与决策 Agent 位于同一操作系统主体下，因此文件权限不能证明真正盲化；运行结论必须保留 `BLINDING_NOT_ENFORCED_SAME_PRINCIPAL`。手工混乱单只允许 100–250 USDT，并要求调用方提供稳定幂等键，重试不得重复成交。

## 5. 风险与成交规则

- 初始权益：10,000 USDT。
- 名义价值：1 倍 USDT 名义价值，不使用真实杠杆。
- 标准单笔理论风险：权益的 `0.50%`。
- 单标的持仓加挂单风险：权益的 `1.00%`。
- 组合持仓加挂单风险：权益的 `3.00%`。
- 日内已实现亏损暂停新增风险：权益的 `2.00%`。
- 72 小时回撤达到 `5.00%` 后停止新增风险。
- 总名义价值上限：权益的 `1.50x`。
- 同一根 K 线同时触及止损和止盈时，市场路径标为 `AMBIGUOUS/CENSORED`，账户按保守的止损优先核算。
- 同一 lot 的多仓止损只能上移，空仓止损只能下移；目标和期限不能为了挽救亏损而外移。
- 风险门使用当前 mark 到止损的剩余净风险，并计入止损滑点与退出费；同时保留成本价到止损的资本结果口径，二者不得混用。
- `RR >= 1.5` 使用扣除入场费、目标退出费，以及止损退出费与止损滑点后的净口径；收支、胜率、profit factor 与交易输赢也按净 PnL 统计。
- 当前 v0.1 不模拟资金费，报告必须保留 `NOT_SIMULATED_V0_1`，不得把结果称为完整交易所成本回放。

## 6. 每小时中文解说的最低内容

每个标的至少包含：

- 当前价格、24 小时变化、波动和数据质量；
- 15m、1h、4h、1d 趋势与阶段；
- 最近支撑、阻力、结构失效点及当前所处位置；
- 主动买卖、订单簿、OI、资金费、拥挤和强平代理；
- 消息与宏观背景，以及信息发布时间和价格反应先后；
- 至少两条相互竞争的路径；
- 行为主体与情绪推断、替代解释及非身份识别声明；
- 未来买卖力量可能如何变化、验证它需要看到什么；
- 当前行动、仓位、入场、止损、止盈、风险和不行动的机会成本。

不得使用伪精确概率。场景只使用有序支持度 `LOW / MEDIUM / HIGH`，并明确它未经校准。

## 7. 每 8 小时复盘

复盘必须同时输出四个互不替代的结果：

1. `Theory Integrity Score`：数据、测量、多尺度、结构、机制、路径、证据链、权限与重放。
2. `Method Practice Score`：覆盖、引用、竞争假说、否证、点位、风险、及时行动、错误分层和解说。
3. `Paper Performance`：净 PnL、回撤、profit factor、胜率、平均盈亏、盈亏比、R、MFE/MAE、手续费、滑点、交易数和持仓时间。
4. `Hypothesis Outcome Diagnostics`：仅对已经到期或被硬否证的原始假说统计 `SUPPORTED_AT_EXPIRY / FALSIFIED / EXPIRED_UNSUPPORTED`；未解决样本不计分，并明确小样本、未校准。

盈利不能提高前两个分数，亏损也不能自动证明理论错误。复盘要将错误定位到：

`DATA → MEASUREMENT → STATE → STRUCTURE → MECHANISM → PATH → TRIGGER → COST → RISK → EXECUTION → REVIEW`

每次复盘必须恰好覆盖连续的 8 个周期，最终完整结果要求 `[1,8]...[65,72]` 九个窗口。每次最多选择一个主要理论或方法变化，生成 `MethodCandidate`，只对未来周期生效，不回写历史。下一窗口必须把该增量、执行步骤、验收标准和否证观察冻结进分析与决策；随后给出 `RETAIN / REVISE / REJECT`，并保留版本链。候选必须有适用环境、输入、步骤、预期收益、失败方式和验收方法。

`Method Practice Score` 衡量过程纪律，不因假说被支持或否证而自动升降；判断质量由独立的 `Hypothesis Outcome Diagnostics` 暴露。纸面 PnL 仍不能改变前两项分数。

## 8. 审计、事务与版本绑定

每个初始化、分析、决策、复盘、混乱注入与终结动作都使用 prepare/commit 事务，绑定前态摘要、后态摘要、产物摘要和哈希链账本。初始化本身是第一笔事务，防止首次周期前的账户状态被静默修改。

运行 manifest 冻结：

- `common / market / theory / portfolio / experiment` 实现；
- 新理论、竞争路径、动态假说图、数据权威标准；
- 本指南和自动化 prompt；
- 公开数据与纸面权限边界。

任一绑定文件漂移后，既有运行必须失败关闭并另起新 run；不能把不同版本的分析混在一个 72 小时结论中。运行目录、JSON、账本与锁文件均限制为当前用户访问。任何预先占位但没有对应事务提交的 decision/final 文件都视为篡改，不得当作幂等成功。

## 9. 本地命令

```bash
/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-init \
  --config config/theory_paper_experiment.v1.json \
  --run-dir .runtime/theory-paper-v1/current

/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-cycle \
  --run-dir .runtime/theory-paper-v1/current

/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-submit \
  --run-dir .runtime/theory-paper-v1/current \
  --decision /absolute/path/to/agent-decision.json

/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-review \
  --run-dir .runtime/theory-paper-v1/current

/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-status \
  --run-dir .runtime/theory-paper-v1/current

/opt/homebrew/bin/python3.12 -m trade_system.cli theory-paper-manual-chaos \
  --run-dir .runtime/theory-paper-v1/current \
  --idempotency-key user-event-001 \
  --symbol MUUSDT --side BUY --notional-usdt 100 \
  --reason "显式记录的情绪化纸面扰动"
```

第 72 小时执行 `theory-paper-finalize`，停止新增风险并封存报告。所有命令只写入被 Git 忽略的 `.runtime/`。
