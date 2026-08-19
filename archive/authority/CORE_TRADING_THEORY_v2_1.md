# 自动交易系统核心理论

> 版本：2.1
> 状态：当前权威理论基线；`RSI-MTF-DRL-PM v0.2` 为 `P0-RSI-01_PASS / E0 / SYNTHETIC_PRIMITIVES_ONLY`
> 版本日期：2026-07-26
> 主要研究对象：BTCUSDT USDⓈ-M 永续；Binance 为 V1 主交易场所
> 原始研究输入：`/Users/wt/Downloads/deep-research-report (1).md`
> 证据等级：E0（理论与数据可获得性已审查；尚无本系统的合格回测、paper 或实盘证据）
> 执行治理：[PROGRAM_GOVERNANCE.md](./PROGRAM_GOVERNANCE.md)

根文件 `CORE_TRADING_THEORY.md` 是当前权威镜像；每个版本的不可变权威由对应 authority manifest 与 versioned snapshot 共同决定，历史合同继续绑定各自冻结的快照或摘要。实现文档可以引用当前权威中的 `T-*`、`DATA-*` 和 `H-*` 编号，但不得另行修改定义。原始研究报告保留为研究输入，不再作为实现规范。

本文件不是盈利承诺、投资建议或实盘授权。理论合理、接口可用、代码可运行、历史回测有效、paper trading 有效和小资金实盘有效，是六种不同的证据，不能互相替代。

2.1 新增的是通用研究方法，不是当前 V1 权限扩张。当前 BTCUSDT、Binance、吸收—修复/反转、动作和风险边界继续由既有已授权 contract 与治理闸门决定；通用方法中的机制、路径、标的、周期、方向或动作只有经过独立预注册、数据授权、样本外验证和资金所有者批准后，才可能进入未来 challenger。

---

## 1. 最终结论

### 1.1 能否获得更多可利用的数据

可以，而且这些数据能够提高模型的可观测覆盖、交叉验证和风险控制能力；它们能否改善成本后结果仍须样本外验证。当前最有价值的候选增量并不是笼统的“情绪数据”，而是：

1. **自身执行与账户遥测**：真实手续费、下单延迟、拒单、部分成交、滑点、资金费、保护单状态和持仓对账。P0-R 先完成字段、费率和账户安全契约；只有 E4 的真实小资金成交才能校准实盘 fill 与尾部成本。
2. **第二交易场所的相对独立观测**：Bybit 等场所的订单簿、成交、OI、funding 和更高覆盖的强平流，可用于区分 Binance 局部噪声与跨场事件；统计净增量尚未知。
3. **期权前瞻风险信息**：Deribit 的 DVOL、隐含波动率、偏度、期限结构、Greeks 和期权 OI，适合做尾部风险、波动状态与仓位调节，不应在未知净做市商方向时伪装成确定性的“Gamma 墙”。
4. **免费历史微观结构**：OKX 官方历史 tick、funding 和高分辨率 L2 可以低成本加快跨年份研究，但不能替代 Binance 执行市场的真实历史。
5. **交易所与结算系统压力**：ADL、保险基金、指数成分、交易所状态和 USDT/USDC 脱锚监控，适合作为风险否决与数据质量条件。
6. **预定宏观事件**：FOMC、CPI、就业等官方日历，适合做事件窗口风险控制，而不是默认作为方向预测因子。
7. **较慢的结构数据**：CME/CFTC、ETF 持仓、稳定币供给与部分链上数据可以用于日级或周级背景；它们不适合直接驱动 100ms–15m 的入场。

因此，系统应当扩充数据，但要分两条晋级路径：预测/上下文数据遵守 `T-012`，只有点时可得、生产可持续并带来锁定样本外净增量才可进入 champion；安全/运营数据遵守 `T-017`，按风险覆盖、时效、误报/漏报、演练和资金所有者风险偏好验收，不要求它提高收益。

### 1.2 核心理论定稿

> **极值不是信号。可交易信息来自主动压力是否仍能产生边际价格冲击、对手方流动性是否持续吸收并恢复，以及这种关系是否在给定市场状态下完成方向响应。**

本系统不测量人的真实贪婪或恐惧，也不声称识别逐价位的开多、平多、开空、平空人数。系统只处理可观测市场行为及其有限代理，并直接预测交易路径结果。

底层理论由五个内生因子构成：

- $D_t$：方向压力（Directional Pressure）
- $L_t$：杠杆变化（Leverage Change）
- $C_t$：拥挤状态（Crowding）
- $F_t$：已观测强制去杠杆（Observed Forced Deleveraging）
- $R_t$：流动性韧性（Liquidity Resilience）

跨交易所、期权、宏观和链上数据统一进入上下文 $K_t$，它们不再被任意相加成新的“情绪真值”。

### 1.3 V1 范围

- V1 只研究 **BTCUSDT 极值后的吸收—修复/反转**。
- Binance USDⓈ-M 永续是主决策与执行市场；Binance 现货是同场参考。
- ETH 只作为跨标的稳定性验证，在取得独立证据前不进入自动实盘候选。
- 明显趋势延续状态下，V1 的默认动作是 `ABSTAIN`，不是强行反向交易。
- 长期理论保留试探仓与确认仓两段式风险分配，不设置第三段趋势加仓；但首份 Protocol v2 只研究 `ENTER_PROBE`。`ADD_POSITION_CONFIRMED` 必须等 PROBE 获得锁定样本外证据后，用新的事前协议、动作政策、标签和风险预算独立验证，不能借用 PROBE 结果自动开放。
- P0 工程目标是研究回放和 paper trading 闭环；进入小资金 canary 必须通过独立闸门并由资金所有者批准风险上限。

### 1.4 对原始文档的提炼、保留与纠偏

| 原始核心思想 | 判断 | 最终理论处理 |
|---|---|---|
| 极值之后观察市场是否继续失衡或开始修复 | 保留 | 极值只创建 episode，不直接开仓；研究“压力—冲击—韧性—响应”链 |
| 观察当前、上方、下方的承接与抛压 | 有条件保留 | 只对有价格坐标的成交/订单簿做冻结区间；OI、funding、账户比不得伪造局部归属 |
| 用开多、平多、开空、平空人数解释行情 | 数据不可识别 | 改为 $D/L/C/F/R$ 可观测代理；不再宣称人数、身份或心理真值 |
| 用 OI 配合主动流分解进攻与撤退 | 可作为推断，不是事实 | $L=\Delta\log OI$ 保持无方向；方向由联合条件概率建模，不做确定性开平仓归因 |
| “恐慌/贪婪系数”及其增速 | 有启发但易重复计数 | 不手工合成单一情绪分数；保留压力的值、斜率和冲击变化，由正则化模型与消融决定权重 |
| 多时间框架：4H 背景、15m 定位、微观执行 | 保留并严格化 | 拆为背景状态、episode 决策和微观执行三层，每层禁止越级外推 |
| 下方先吸收、当前再确认、上方止盈 | 保留为可证伪路径 | 吸收必须同时满足持续压力、边际冲击下降和深度持续补回；随后才允许响应确认 |
| 试探、确认、趋势三段加仓 | 简化并分阶段 | 理论只保留 PROBE 与 POSITION_CONFIRMED，共享单 episode 风险预算；首份 Protocol v2 仅验证 PROBE，确认加仓延后另行预注册；趋势延续默认放弃 |
| 优先提高胜率 | 纠偏 | 优化校准后的成本后期望、尾部风险、回撤与稳定性；胜率只是一项描述指标 |
| 持续调权重和阈值 | 增加治理 | 采用预注册、锁定样本外、champion/challenger、人工晋级和可回滚发布，禁止近期盈亏驱动在线调参 |

---

## 2. 术语、证据与推理纪律

本文中的 `P0-R` 专指 **M0A–M5、最高到 E3 的研究、回放、paper/testnet 与 shadow 范围**，不含任何真实资金。`M6A/G4A` 是 Canary 准入准备；`M6B` 产生候选有限实盘证据，只有通过 G4B 审核后才可声明 E4。

### 2.1 强制标签

| 标签 | 含义 | 允许的表述 |
|---|---|---|
| `[FACT]` | 数据源直接提供、可复查的事实 | “订单簿返回了这些可见价量” |
| `[MEASURE]` | 由点时事实确定性计算的量 | “过去 10 秒多层 OFI 为正” |
| `[INFERENCE]` | 对不可直接观察状态的概率推断 | “更可能处于强制去杠杆状态” |
| `[HYPOTHESIS]` | 尚待样本外检验的统计命题 | “吸收后 TP 先发生概率提高” |
| `[FORECAST]` | 指定模型版本给出的概率 | “模型预测 TP/SL/结构退出/超时为……” |
| `[POLICY]` | 将预测、成本和风险映射到动作的规则 | “保守 EV 为正且风险闸门通过才下单” |
| `[RISK]` | 资金所有者设定、不得由收益优化的硬约束 | “单事件最大允许损失” |

### 2.2 唯一合法的推理链

```text
原始可观测事件
→ 决策时点实际可用的测量特征
→ 带不确定性的状态推断
→ 未来路径概率预测
→ 成本与硬风险约束下的行动
→ 实际执行与账户结果
```

禁止以下跳跃：

- 将代理变量直接称为真实心理、真实人数或真实开平仓身份。
- 将 OI 上升与主动买入简单拼接后，断言“新增多头开仓”。
- 将相关性写成因果性。
- 将高分状态直接等同于下单信号。
- 将缺失强平消息解释为“没有强平”。
- 将历史修复后的数据覆盖成当时可见数据。
- 将回测净值、paper 无报错或 API 连通性当作生产盈利证明。

### 2.3 点时信息集

在决策时刻 τ，模型只允许使用：

\[
\mathcal I_\tau = \{e_i:\ available\_at_i \le \tau\}
\]

每个原始 capture 必须立即记录系统接收时间和不可变 payload；解析/质量验证完成后，再追加引用原事件的 versioned availability record。该记录必须同时保存实际生成时间 `derived_at`、可用时间 `available_at` 和 `availability_kind=ACTUAL|RECONSTRUCTED`。`ACTUAL` 表示当时运行中的冻结管线实际释放该事件；后来用新解析器或新质量规则重算，只能生成 `RECONSTRUCTED`，不得倒签成历史 `ACTUAL`。失败原文可以永远没有可用记录，不得为补字段回写 raw。

研究中的 as-of join、滚动窗口和标签生成必须按其 lane clock 遵守 $a_{lane}(e)\le decision\_at$：`ACTUAL_ONLY` 使用 `available_at`，受限 reconstructed DEVELOPMENT 使用 `reconstructed_available_at`。schema 的 `availability_kind` 始终只有 `ACTUAL|RECONSTRUCTED`；若未来另获授权，历史 `DEVELOPMENT` 才可额外标记 `research_lane=RECONSTRUCTED_CAUSAL_DEVELOPMENT`。该 lane 必须在 outcome 可见前冻结 source ordering、parser、as-of release 与 eligibility，并保存 `reconstructed_available_at`、`ordering_reconstructed` 和 limitations；全管线同版本、不得跨 gap、不得伪造 receive time、不得混入 `ACTUAL`。它不能证明真实延迟、跨流顺序、queue、G1 或 E3；live/shadow 永远 `ACTUAL_ONLY`，E3 前仍须以未来 `ACTUAL` 同版本 shadow 验证。当前文档不因此授权任何历史读取，CALIBRATION/HOLDOUT 是否可使用该 lane 必须由后续 contract 与 Sol 另审。晚到、补发或事后修订的数据可以用于质量分析，但不得改写历史实际决策输入。

ETF 的持仓日期不能替代网页实际发布时间，COT 的报告日期不能替代发布日期，链上 block time 不能替代本机首次接收和确认时间。若未来研究宏观实际值，必须使用当时发布的 vintage（例如 ALFRED/FRED 的历史版本），不能使用今天看到的修订后序列。

### 2.4 数据事实等级

除上述推理标签外，每个数据字段还应永久记录来源等级：

| 等级 | 数据性质 | 示例 | 使用边界 |
|---|---|---|---|
| `O0` | 撮合引擎或协议原始记录 | 成交、订单簿更新、链上交易 | 仍需审查覆盖、排序与接收延迟 |
| `O1` | 监管机构、交易所或发行人披露 | ETF 持仓、储备报告、COT | 是披露事实，不等于实时市场真值或交易意图 |
| `M1` | 可复现的确定性变换 | basis、IV 期限斜率、OFI | 必须版本化公式与输入 |
| `I1` | 实体或标签推断 | “该地址属于某交易所” | 必须保存 point-in-time 标签和置信度 |
| `I2` | 意图或角色推断 | “鲸鱼准备卖出”“dealer gamma 墙” | 不得作为事实；V1 不进入核心决策 |

供应商给出高置信度不会自动把 `I1/I2` 升级为事实。

---

## 3. 核心 Claim 登记表

| Claim ID | 层级 | 核心内容 | 当前依据 | 可证伪或失效条件 |
|---|---|---|---|---|
| `T-001` | `[FACT]` | 公开市场流不能识别逐价位参与者人数及真实开/平仓身份 | 公开字段只提供价、量、方向代理、总 OI 等 | 交易场所未来提供可审计的逐账户开平仓真值时需重审 |
| `T-002` | `[FACT]` | 总 OI 同时对应等量未平多头与空头，变化本身无方向 | CFTC/CME 定义 | 不适用独立单边持仓真值；新字段须单独验证语义 |
| `T-003` | `[HYPOTHESIS]` | RSI、价格偏离或强平极值只负责触发观察，不单独构成反转信号 | 指标性质与趋势市场经验 | 若锁定样本外证明极值单变量已稳定优于完整模型，应简化模型 |
| `T-004` | `[HYPOTHESIS]` | 短期价格响应取决于方向流、状态条件和流动性韧性的交互 | 订单流失衡研究提供短周期依据 | 在本市场、本持有期无稳定增量或成本后失效 |
| `T-005` | `[POLICY]` | 吸收必须同时具备持续压力、边际冲击下降和对手方深度持续补回 | 防止把静态挂单墙误认为承接 | 任一条件缺失时不得标为已确认吸收 |
| `T-006` | `[POLICY]` | 事件触发后冻结锚点与价格区间，结束前不随现价重画 | 防止坐标漂移与未来解释 | 只有新 episode 创建才可重置 |
| `T-007` | `[POLICY]` | 只有带价格坐标的数据可分配到上/中/下区间 | OI、funding、账户比是全局量 | 禁止用比例分摊伪造局部信息 |
| `T-008` | `[POLICY]` | 预测目标按动作与阶段定义，并将成交后的 TP、SL、结构退出、超时与提交后的 NO_FILL 分离 | 与真实决策和执行结果对齐 | 概率失准、标签不稳定或执行结果被错误混类时失败 |
| `T-009` | `[POLICY]` | 只有保守成本后 EV 为正且数据、模型、风险、执行闸门全通过才允许新增风险 | 决策与预测分离 | 任一闸门失败即 `ABSTAIN` |
| `T-010` | `[RISK]` | 最大风险、日损、回撤、保证金和停机规则不能由历史收益自动优化 | 防止回测选择替代资金授权 | 只能由资金所有者显式修改并留痕 |
| `T-011` | `[HYPOTHESIS]` | 跨场、期权与系统压力数据可能减少局部假信号和尾部风险 | 数据含有不同市场维度 | 独立消融无净增量或运维成本过高即拒绝 |
| `T-012` | `[POLICY]` | 预测/上下文数据按“影子采集—质量—消融—锁定样本外—成本”晋级 | 防止特征堆砌和数据挖掘 | 未走完流程不得进入 champion |
| `T-013` | `[POLICY]` | 自身执行遥测是实盘成本模型和资金安全的最终真值 | 公共盘口不能替代自己的成交结果 | 无真实遥测时不得声称成本模型已获实盘校准或实盘闭环完成 |
| `T-014` | `[POLICY]` | 理论、回测、paper、canary、生产证据分级管理 | 防止准备度夸大 | 只能按闸门逐级晋升，不能越级 |
| `T-015` | `[POLICY]` | 多空方向分别标注、训练、校准和验收 | 市场结构和成本并不天然对称 | 只有证据证明可共享时才允许合并参数 |
| `T-016` | `[POLICY]` | 持续优化采用 champion/challenger、影子运行、人工晋级和可回滚发布 | 防止近期盈亏驱动在线漂移 | 禁止根据少数近期交易自动改参数或扩资 |
| `T-017` | `[RISK]` | 安全/运营数据不以提高收益为晋级条件，而按 hazard coverage、时效、误报/漏报、故障演练和资金所有者风险偏好验收 | 安全控制可能主动牺牲机会和收益 | 未覆盖目标风险、无法 fail closed 或未获资金所有者批准时不得用于真实资金 |
| `T-018` | `[HYPOTHESIS]` | RSI 多时间框架只产生待确认的观察触发；它不是方向预测、入场或加仓授权 | 指标可复算性 | 同 cohort 的静态 RSI control 已稳定更优或 RSI 无增量时，拒绝该触发层 |
| `T-019` | `[POLICY]` | RSI 只能由 UTC 已闭合 bar 按 lane clock 计算；`ACTUAL_ONLY` 使用不早于 bar close 的 `available_at`，迟到/回填无效；仅另行授权且满足冻结 causal-release 的 reconstructed DEVELOPMENT 可使用 `reconstructed_available_at`，不新增第三种 `availability_kind` | 点时信息纪律 | 任一决策跨越其 lane clock、使用未闭合 bar，或将 reconstructed 作为 ACTUAL 生产输入即整条候选无效 |
| `T-020` | `[POLICY]` | 候选只有在多源确认价格区间的非空交集 `EntryZone` 内才可提交；空交集是 `ABSTAIN` | 防止把触发误写成可执行价格 | 交集依赖未来信息、不可复算或在成本后无增量即退回更简单 control |
| `T-021` | `[RISK]` | 初始订单规模必须由冻结的风险 envelope、初始 stop、尾部缓冲和最坏成本共同反推，不能由 RSI 强度放大 | 资金风险不可由收益优化 | 任一订单在提交前不能证明风险上界即不得提交 |
| `T-022` | `[RISK]` | partial fill、保护单和总风险必须受 stop-first 与跨订单预算不变量约束；首 fill 后可立即请求保护，但只允许在 $\Delta_{unprotected}^{max}$ 内短暂 `PROTECTION_PENDING` | 执行失败可放大损失 | 保护超时、reject、unknown、未发出保护请求、风险超预算或账户不一致即 `HALTED_RECONCILE` |
| `T-023` | `[POLICY]` | target、盈利锁定和 horizon 是事前冻结的退出规则；`PRE_LOCK` target 不得外移，`PROFIT_LOCKED` 的外移必须同时满足绝对 $LCB(EV_{remain})>0$ 与相对 exit-now 超过冻结 margin，且在 $T_{cap}$ 内；horizon 永不延长 | 防止退出端的数据挖掘 | 同一 entry/fill cohort 上的退出规则不一致时不得比较结果 |
| `T-024` | `[POLICY]` | 每次管理、成交、保护、撤单和对账均写入不可变 management ledger；交易所确认前旧 barrier 仍是唯一权威 | OMS 失败模式 | 缺少身份、顺序、ack 或对账证据时不得进入 OPEN/PROFIT_LOCKED |
| `T-025` | `[POLICY]` | 理论变化必须经历 preregistration、DEVELOPMENT、误差归因、theory delta、CALIBRATION、freeze 与一次性 HOLDOUT；同一 holdout 不得用来迎合改版 | 防止同集反复优化 | 任一 holdout 已读取后，只能作为 `SEEN` 错误分析，不能重新选择理论或参数 |

---

## 4. 可观测性与不可识别边界

### 4.1 能直接观察什么

- 公开订单簿中的可见价格层和聚合数量。
- 成交价、成交量、时间、交易所给出的 maker/taker 或 side 语义。
- 总 OI、mark/index、premium/basis、funding、账户或持仓比率。
- 交易所选择推送的强平事件。
- 自己账户的订单、成交、费用、资金费、持仓和余额变化。

### 4.2 不能直接观察什么

- 一笔公开成交属于开仓还是平仓。
- 一个价位究竟有多少独立参与者。
- 账户背后的最终控制人、套保关系或跨场净敞口。
- 可见挂单的真实意图、撤单计划和隐藏流动性全貌。
- 期权 OI 背后的净做市商方向。
- 第三方链上地址标签的绝对正确性。

### 4.3 OI 的正确用法

OI 是总未平仓合约量；市场层面的未平多头与未平空头数量相等。因而：

- $\Delta OI > 0$：有新的配对仓位进入，但不知道哪一方是信息优势方，也不知道主动成交方在整体组合中是开仓还是平仓。
- $\Delta OI < 0$：有配对仓位退出，但不能据此独立断言“多头撤退”或“空头撤退”。
- OI 只能与方向流、价格冲击、funding、强平和状态共同作为条件变量，不能被解释成方向标签。

### 4.4 强平流的正确用法

强平流是交易所定义下的已观察样本，不是完整爆仓账本。不同场所具有不同的抽样、聚合、方向和更新规则：

- Binance USDⓈ-M 在 2026-04-14 起将文档语义更新为每个 symbol 每 1000ms 推送其中最大的一笔强平订单，因此 `0` 只表示“未观察到”，不能表示真实强平为零。
- Bybit 的 `allLiquidation` 以 500ms 频率推送其定义下的全部强平，且 side 字段描述被强平仓位方向；它与 Binance side 语义不能直接拼接。
- OKX 已停止通过旧 REST 接口提供平台历史强平，实时 WebSocket 和第三方历史采集需分别审查。

统一适配层应将其归一为**价格压力方向**：$F_t>0$ 表示被迫买入流（通常与空头强平关联），$F_t<0$ 表示被迫卖出流（通常与多头强平关联），同时保留原始 side、场所语义和 coverage 标志。

### 4.5 订单簿不是全部可交易流动性

- 标准公开深度可能排除 RPI、隐藏单、条件单及尚未公开的流动性。
- Binance 标准 depth 明确排除 RPI，并提供单独的 RPI depth；两者不能在未验证可成交权限时简单相加。
- Bybit 公共订单簿也排除 RPI。
- 静态“大单墙”可能迅速撤销；只有实际承受主动流后的持久深度、补单和低边际冲击，才构成韧性证据。

---

## 5. 五因子状态条件理论

### 5.1 方向压力 $D_t$

定义 $D_t>0$ 为净主动买入压力，$D_t<0$ 为净主动卖出压力。候选测量包括：

- signed aggressive notional / taker imbalance；
- 多层 order-flow imbalance（OFI）；
- microprice 相对 mid 的偏移；
- 不同深度层的消耗速度；
- 现货与永续之间的方向一致性。

所有分量必须按实时可见深度、成交量或波动进行稳健标准化。`aggTrade` 的聚合语义会损失交易笔数信息，因此系统使用名义量和方向压力，不把聚合条数解释为人数。

### 5.2 杠杆变化 $L_t$

基础定义：

\[
L_t = \Delta \log(OI_t)
\]

它描述杠杆仓位总量扩张或收缩，不含方向真值。其价值主要来自与 $D_t$、价格响应和 $F_t$ 的交互：相同的卖压在 OI 扩张与 OI 快速收缩时可能对应完全不同的状态。

### 5.3 拥挤状态 $C_t$

$C_t$ 保持为一个向量，不预先手工压缩成“贪婪/恐慌分数”。候选分量包括：

- funding 偏离与变动；
- 永续 premium/basis；
- global long/short account ratio；
- top trader account/position ratio；
- 跨交易所 funding、basis 和 OI 分布。

这些比率通常频率较低、历史较短、全局而非价格局部，并可能共享信息。只有经过正则化、消融和稳定性检验后才允许进入预测器。

### 5.4 已观测强制去杠杆 $F_t$

$F_t$ 是按价格压力方向标准化的已观测强平名义量、强平密度与其相对正常成交量的比例，同时附带：

- `coverage`：数据源理论覆盖和实际连接覆盖；
- `censored`：是否存在交易所抽样/聚合；
- `venue`：发生场所；
- `available_at`：事件在完成接收、解析、序列/质量验证后，最早可进入决策的时刻；必须满足 `available_at >= receive_time`。

强平本身可能是趋势加速而不是反转。只有当强平、OI 收缩、边际冲击衰减和韧性提升共同出现时，才形成“去杠杆后修复”的候选路径。

### 5.5 流动性韧性 $R_t$

定义更高的 $R_t$ 表示市场在承受主动压力后更能维持或恢复流动性。必须分方向估计：

- $R_t^{sell}$：bid 对主动卖压的韧性；
- $R_t^{buy}$：ask 对主动买压的韧性。

主要测量：

1. **边际冲击**：单位标准化主动流导致的 mid/mark 变化是否下降。
2. **补单速度与持久性**：被吃掉的对手方深度是否恢复，并能持续多个更新周期。
3. **深度存活**：挂单是否在压力到来时仍留在簿中，而不是事前展示、事中撤销。
4. **价格响应不对称**：同量顺向流的推进效率是否降低，反向小流是否开始产生更大响应。
5. **spread 与恢复时间**：冲击后 spread 是否迅速恢复正常。

韧性不能由单个盘口快照或“未创新低/高”独立确认。

**严格的 $R_t$ 只允许是 post-pressure 测量**：先固定方向、强度和结束时刻的主动压力，再在其后的非重叠观测区间测量对手方深度存活/恢复和价格响应；同一压力区间内同步计算的深度变化，或压力结束前已可见的盘口变化，只能称为 `R_proxy`，不得作为严格韧性主张、H-002/H-004 的单独裁决输入或“吸收已确认”的证据。若来源时间、压力结束边界或后续观测顺序不可验证，$R_t$ 必须不可用而非以零或同步 proxy 替代。

### 5.6 市场与事件上下文 $K_t$

$K_t$ 只负责条件化，不与五因子机械相加，并拆成两类：

- **市场上下文 $K_t^{market}$**：跨交易所价格发现、价差、流量与强平一致性；期权 DVOL、ATM IV、偏度、期限结构和到期集中度；ADL、保险基金、CME/CFTC、ETF、稳定币和链上背景。
- **近似外生事件 $K_t^{event}$**：预定宏观发布、交易所维护公告、制度和合约规则变更。

跨 venue、期权和 ADL 仍是市场系统内生观测，不能因被放入上下文就被称为严格外生变量。

### 5.7 理论关系

令 $Z_t$ 表示价格结构、收益、波动、趋势和 episode 几何。数据质量 $Q_t$ 不被解释为市场状态成因，而先映射为系统可用性：

\[
A_t=q(Q_t)\in\{USABLE,DEGRADED,INVALID\}
\]

当 $A_t$ 允许推断时，市场状态概率为：

\[
P(S_t=s\mid\mathcal I_t,A_t)
=g_s\!\left(Z_t,D_t,L_t,C_t,F_t,R_t(D_t),K_t\right)
\]

方向条件韧性定义为：

\[
R_t(D_t)=
\mathbf 1_{D_t\ge 0}R_t^{buy}
+\mathbf 1_{D_t<0}R_t^{sell}
\]

即主动买压对应 ask-side 韧性，主动卖压对应 bid-side 韧性。然后在指定预测期限 $h$ 内，用下式表达待检验的价格响应关系：

\[
\frac{\Delta m_{t,h}}{\sigma_t}
\approx
\lambda_{S_t,h}D_t
+\beta_{S_t,h}(D_tL_t)
-\gamma_{S_t,h}\{D_tR_t(D_t)\}
+\theta_{S_t,h}^{\top}K_t
+\varepsilon_{t,h}
\]

直观含义：

- 主动压力通常推动短期价格；
- 杠杆状态可能放大或改变该关系；
- 对手方韧性提高时，同方向压力的价格推进效率下降；
- 跨场和期权等上下文可能改变基准风险，但是否增加方向预测力必须验证。

这不是已证明的参数方程，而是可证伪的研究结构。五因子并非五个独立真因；taker、OFI、强平、OI 和价格冲击可能共享信息，模型必须通过交互、正则化和消融避免重复计数。

---

## 6. 时间、空间与 episode

### 6.1 三层时间尺度

| 层级 | 典型尺度 | 作用 | 禁止事项 |
|---|---|---|---|
| 微观结构层 | 100ms–1m | 压力、冲击、补单、spread、执行 | 不得直接外推为数小时 alpha |
| 事件决策层 | 1m–15m | episode 演化、入场/确认/失效 | 不得使用 bar 结束后才知道的数据 |
| 背景状态层 | 1H–4H | 极值、趋势、波动与风险背景 | 不把极值直接映射成反向下单 |

窗口、bar 和最大持有期都是待验证研究参数，不是理论常数。

### 6.2 四类空间

1. **价格空间**：相对 episode 冻结锚点的下方、当前和上方区间。
2. **交易场所空间**：Binance、Bybit、OKX、Hyperliquid 等不同 venue。
3. **工具空间**：现货、永续、交割期货和期权。
4. **市场网络空间**：BTC 与 ETH、CME 和风险资产的 lead-lag。

### 6.3 episode 锚定

极值触发时记录并冻结：

- `episode_id`、方向候选、触发时刻；
- 锚点 $P_0$；
- 当时可用波动尺度 $\sigma_0$；
- 上/中/下价格边界；
- 最大观察与持有期限；
- 数据质量和模型版本。

区间宽度可采用历史分位或波动缩放，但必须在锁定训练集内选定。原报告中的固定 ±1%、0.8 ATR、3-bar slope 等只保留为候选初值，不是理论结论。

只有订单簿、成交、volume profile 等具有明确价格坐标的数据可以进入价格区间。OI、funding、多空比、宏观事件和交易所压力是全局上下文，不能按价位“分摊”。

---

## 7. 状态演化与吸收定义

### 7.1 episode 状态

```text
OBSERVE（极值观察）
→ EXPANDING（失衡扩张）
→ DECELERATING（压力减速）
→ ABSORBING（候选吸收）
→ RESPONDING（反向响应）
→ REVERSAL_CONFIRMED / FAILED / TIMED_OUT
```

状态由概率和滞回规则控制，不因单个 tick 来回跳变。数据异常进入 `UNKNOWN`，不能被当作中性状态。

V1 每个 instrument 同时最多允许一个活动 episode 和一个本策略仓位：

- 活动 episode 内出现同方向新极值，只记录为事件内观测，不重置锚点。
- 出现反方向触发时，先使原 episode 按预注册规则进入 FAILED/TIMED_OUT；不得并行创建反向可交易 episode。
- 已持仓时禁止同 episode 或新触发自动反手；必须先退出、对账并完成 COOLDOWN，才可创建反向 episode。
- 只有前一 episode 进入终态后，新 episode 才能冻结新的锚点和区间。

### 7.2 下跌后的吸收

确认 bid-side 吸收至少需要同时看到：

1. 主动卖压仍存在，排除“只是没人再卖”；
2. 单位卖压造成的下行边际冲击显著下降；
3. bid 被消耗后持续补回，且挂单在压力到来时仍存在；
4. 价格相对预期噪声不再有效扩展新低；
5. 数据序列完整、延迟在允许范围内。

强平密集、OI 收缩、跨场同步后同时满足以上条件，会提高去杠杆修复状态的概率，但不能替代上述条件。

上涨后的 ask-side 吸收为镜像过程，但参数、校准和验收必须独立，不能假设多空完全对称。

### 7.3 极值与趋势

- 极值只创建 `WATCH/OBSERVE`，不创建仓位。
- 极值后的直接反向规则只可作为 control/baseline；它既不是 `ENTER_PROBE` 候选，也不能被写成吸收—响应链已成立。
- 强趋势中持续高 $D_t$、高价格冲击且对手方 $R_t$ 低，属于延续或不可反向状态。
- V1 不交易趋势延续；在此状态主动放弃是正确输出。
- 只有完成“减速—吸收—响应”的证据链，才进入试探候选。

---

## 8. 预测目标、EV 与行动

### 8.1 动作契约

预测不是只对抽象的 LONG/SHORT 生效。每个候选动作必须锁定：

\[
a=(side,stage,entry\_policy,barriers,horizon,exit\_policy)
\]

- `side`：LONG 或 SHORT；
- `stage`：ENTER_PROBE 或 ADD_POSITION_CONFIRMED；
- `entry_policy`：IOC 价格上限、数量和有效期；
- `barriers`：成本后 TP/SL 定义；
- `horizon`：最大持有期；
- `exit_policy`：动态结构退出和超时规则。

这是完整理论中的目标动作空间，不是当前实现已经获得的权限。首份 Protocol v2 固定为 `PROBE_ONLY`：只允许在 episode 达到 `RESPONDING`、4H 上下文为 `READY/ELIGIBLE`、方向与 episode 声明一致且证据链完整时生成 `ENTER_PROBE` 反事实动作。它预测的是固定入场规则下的**市场路径**，不是交易所实际成交或执行 PnL。

极值直反/“触顶抄底”仅可作为同 cohort 的 control action；不得绕过 `RESPONDING`、严格 post-pressure $R_t$、4H context 或 episode 方向约束生成 `ENTER_PROBE`。control 的存在用于检验增量，不授予交易或动作权限。

PROBE 与确认加仓的入场价、已有持仓、障碍和条件分布不同，必须分别标注和校准。未来评估 ADD 动作时计算的是**增量动作及其对总仓位风险的影响**，不能复用 PROBE 概率；必须在 PROBE 通过 G2 后建立新的预注册协议，当前 Protocol v2 不允许生成或授权 `ADD_POSITION_CONFIRMED`。

### 8.2 成交后的 competing-risk 标签

对于每个动作和实际/仿真成交价格，锁定数据、特征、动作、标签和执行模型版本。成交后的市场路径预测为：

\[
(p_{TP},p_{SL},p_{STRUCT},p_{TO})
=P(Y\mid\mathcal I_t,a,filled)
\]

其中 `STRUCTURE_EXIT` 只表示在固定 TP/SL 之前触发了动作契约中预先冻结的市场结构退出；`TIMEOUT` 只表示成交后达到持有期限，四类条件概率之和为 1。另保存 MFE、MAE、time-to-hit、退出收益和超时收益。多、空以及两个 stage 分别训练或至少分别校准。

`RISK_KILL`、`DATA/EXECUTION_HALT`、账户异常和人工紧急退出属于运营 override，不是市场路径 competing risk。发生时另记 `operational_override` 与真实 PnL；训练样本按预注册规则在 override 时刻 censor 或排入独立故障情景，不得让市场模型学习部署故障率。

`NO_FILL` 和 `PARTIAL_FILL` 是执行结果，不得塞入 `TIMEOUT`。执行模型另行估计：

- $p_{fill}(a)$；
- 成交比例 $f\in[0,1]$；
- 条件延迟与滑点分布；
- 拒单、未知订单和重试结果。

### 8.3 决策、成交与 EV 分离

先计算成交后的净值：

\[
EV_{fill}(a)=
p_{TP}G_a-p_{SL}L_a
+p_{STRUCT}E[R_{STRUCT}\mid a]
+p_{TO}E[R_{TO}\mid a]
-C_{trade}(a)
\]

再计算提交动作的价值：

\[
EV_{submit}(a)=
p_{fill}(a)E[f\cdot EV_{fill}(a)\mid filled]
-(1-p_{fill}(a))C_{no\_fill}(a)
-C_{submit}(a)
\]

其中交易成本包含进出手续费、spread、条件滑点、funding 和尾部执行成本；`C_no_fill` 只在机会损失、重试或其他真实代价有明确口径时使用。实际准入使用保守估计或下置信界，而不是点估计。风险引擎始终按订单可能全部成交计算最大风险，成交后再按实际 fill 对账。

只有以下条件同时满足才允许新增风险：

- 数据健康；
- episode 与预测版本有效；
- 概率已在独立样本校准；
- 保守成本后 EV 超过预注册门槛；
- 流动性和容量满足；
- 硬风险闸门通过；
- 保护单和账户对账能力正常。

否则动作是 `ABSTAIN`。

### 8.4 两段式仓位

- **PROBE**：吸收概率达到准入、但当前区间尚未完成结构响应时的小风险试探。
- **POSITION_CONFIRMED**：响应与结构确认后，在同一总风险预算内增加到目标风险。

两段共享单个 episode 风险预算。第二段不是在亏损时摊低成本；若结构失效，必须退出。禁止第三段趋势仓、扩大止损、同 episode 自动反手和根据近期盈利自动扩资。

本节定义长期风险语言；首份 Protocol v2 不实现第二段。只有新的 ADD 协议通过独立数据、成本和风险门后，`POSITION_CONFIRMED` 才能从理论状态变成系统动作。

### 8.5 仓位上界

方向仓位数量必须同时满足：

\[
q \le
\min\left(
\frac{B_{episode}}{|P_{entry}-P_{stop}|+C_{tail}},
q_{liquidity},q_{margin},q_{venue}
\right)
\]

其中 $B_{episode}$ 是资金所有者设置的最大事件损失，$C_{tail}$ 是极端滑点和费用缓冲。所有具体风险数值在 live 前由资金所有者签署，不从回测最优值自动产生。

---

## 9. 数据宇宙与优先级

以下可获得性核验截至 2026-07-22。接口、权限、地区资格和历史保留会变化，实施时必须再次核验官方文档。

### 9.1 Source Registry：事实到来源的映射

Source ID 是证据定位符，不是永久可得承诺。实现时还必须保存抓取日期、endpoint/channel、schema 版本、响应样本哈希、权限和地区条件。

截至本次核验，Binance USDⓈ-M WebSocket 已按流量类型拆分为 `/public`（高频公开）、`/market`（常规市场）与 `/private`（用户数据）路由；活动 G1 只使用已实测的公开 `/public/stream` 与 `/market/stream`，不含私有连接。来源契约必须保存精确路由，不能把旧 `/ws` 探针、计划配置或单次连通误写成持续可用性。[Binance 官方迁移说明](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice)

当前实现将 BTCUSDT 的最小公开来源契约冻结在 `config/source_registry.v3.json`；每个 `collect-public` collection 在开始前校验配置流，并不可覆盖地记录 registry ID、canonical SHA-256、来源 schema 版本和每个已观测来源的首个 raw payload hash。对未来需要按计划积累的窗口，可另行冻结 `FROZEN_FORWARD_CAPTURE_PLAN`：它要求 plan 在每个 UTC slot 开始前冻结，并在连接前绑定 instrument、registry ID/SHA-256、互不重叠的 slot 和最小时长，只有当前启动与请求时长落入指定 slot 才能采集，且 manifest 会保留 plan/slot/冻结时间摘要。受监督调度器可调用 `collect-planned-public`，它原子创建 `<plan-id>/<slot-id>` 独立 Evidence Store，成功 collection 才自动封存；失败窗口明确保留为 `UNQUALIFIED_NOT_SEALED`，不允许自动重跑覆盖或作为 G1 输入。`capture-plan-status` 是不创建目录的只读审计：只有绑定 plan/slot/registry 摘要相符、collection 为 `QUALIFIED_SMOKE`、所有所属 raw 分段已封存且 audit 有效时才报告完成；目录存在、收集曾启动或 stdout 一次成功都不构成完成。该计划只证明窗口是事前排程，`coverage_intent` 只能描述日历/会话意图，绝不能当作市场状态或结果声明；它不追溯既有 collection，也不替代质量验收。v3 按 collection 记录的 cadence 轮询 `exchangeInfo` 合约状态/filter 快照；任一次 BTCUSDT 观测为非 `TRADING` 即拒绝 collection。冻结 G1 必须预先声明 metadata 最少观测数、最大实际间隔及全程状态要求、最少不同 UTC 日期与小时桶，并为 depth、成交、mark 与 OI 分别声明最少观测数和从窗口首尾计入的最大观察间隔；因此“该流曾出现一次”或在同一短时段重复采集均不能替代连续、分散覆盖。日历桶只防止时间集中，不声称覆盖了不同市场状态。snapshot 只要求最少观测数，因为它是重建锚点而非周期流。`forceOrder` 只要求已配置且留痕：空窗口代表未观测，不能填为零，也不能反过来把无强平事件判为数据中断。已用于先前 collection 的 `source_registry.v1.json` 与 `source_registry.v2.json` 保持原样。这个绑定只证明当次采集使用了哪个来源契约，不替代接口可用性、覆盖完整性或研究有效性的验证；任一来源语义变动必须创建新 registry 版本，并在 G1/M0B 中重新冻结。

本理论的第一份可执行证据契约已经冻结为 `forward_capture_plan.g1.v1.json` 与 `g1_data_acceptance.v1.json`。计划在 2026-07-23 至 07-29 轮转 28 个 UTC 窗口，每窗最少 3,660 秒，并在创建目录前同时校验 Source Registry、整个 `trade_system` package 源码摘要、15 GiB 最低可用空间和 12 GiB 本计划最大占用；`supervise-capture-once` 由本机 LaunchAgent 在每个冻结 slot 对应的本地日历时刻唤醒，`RunAtLoad` 只用于重启恢复，且只有完整时长仍能装入窗口时才运行。G1 要求至少 24 个合格 collection、86,400 秒非重叠观测、7 个 UTC 日期和 12 个小时桶；每窗另有 depth、aggTrade、mark、OI、snapshot、exchangeInfo cadence、零解析/簿 gap、零重连、ACTUAL-only 与封存门。28 个 slot 的冗余只容忍运行失败，不允许移动或补采原 slot。当前 14 个既有 `SEALED_CURRENT` 短窗口因未绑定 exact 新计划或不满足每窗阈值而全部排除；因此当前结论是 `COLLECTING/WAIT_DATA`，量化缺口仍为 24 个/86,400 秒/7 日/12 小时桶。历史 archive overlap 保留为 P1 交叉审计；某日文件尚未发布或 URL 404 不阻塞这条前瞻 P0 主链，也不能被写成审计通过。

后续 DEVELOPMENT/HOLDOUT 研究窗口必须另外事前冻结角色、决策区间、4 小时 warmup 与 300 秒标签尾部，不能把 G1 qualification collection 直接改名为研究样本。上下文管线只接受 collection-local `ACTUAL`，以每个闭合 UTC 秒的最后实际观测形成 1 秒测量，在下一条真实事件到达时发布；原事件时间不向下取整或倒签。它计算 60/900/3600/14400 秒收益与实现波动、1 小时趋势/区间/episode anchor、`price_impact_1s`、压力侧 `R_directional` 及同侧连续秒的 `R_directional_improvement`。任一缺秒、非 ACTUAL、订单簿无效、方向切换、warmup 不足或趋势延续否决都必须 `ABSTAIN`；不能插值、填零或跨 collection 延续。

未来角色 bundle 还必须逐 collection 绑定 acceptance/admission、role-window、context artifact/manifest 和已验证冷归档 receipt。压缩冷段只有在 gzip、记录数、raw/availability 摘要、terminal、audit/replay、plan、registry 与软件绑定全部一致时才可重放。当前 workspace 只提供冷重放和不可执行的热源退役计划；实际删除永久 fail-closed。同一磁盘上的压缩副本只改善容量，不是灾备；只有另行授权的异机/对象存储目标、恢复演练与保留政策成立后，才可设计真实热源退役。

在冻结任何 episode/action 阈值之前，允许对 `SEALED_CURRENT` collection 作一次**只读、无 outcome 的特征描述**：先重验 terminal manifest、原始段封存和当前 audit/replay 摘要，再以每个 collection 独立的簿/状态机回放 feature，记录每个数值特征的观测数、极值、1/5/50/95/99 分位数以及 quality flag 计数。这一步的用途仅是识别量纲、异常长尾、数据缺失和删失比例，从而制定候选的预注册网格与数据质量约束；不得以这些分位数直接挑出“最佳”触发阈值。它不去重重叠窗口、不读取 label/outcome、不拟合模型，也不能替代 G1、状态覆盖、M0B、G2/G3 或任何交易授权。最终阈值仍必须在 outcome/holdout 打开前以独立 `FROZEN_EPISODE_POLICY`、action policy 和 research protocol 固定。

对需要 paper 可行性检查的 intent，可从指定封存 `exchangeInfo` event 派生 PRICE_FILTER、LOT_SIZE 和 MIN_NOTIONAL 规则，先验证价格 tick、数量 step、上下界、最小名义量和 `TRADING` 状态，再进入本地风险审批；规则失败必须记录具体原因。这个校验仅避免显而易见的离线不可行订单，不能证明交易所接受、账户权限、动态限额、实际成交或执行成本。

| Source ID | 对应 Data ID | 官方来源或 channel | 能支持的事实边界 |
|---|---|---|---|
| `SRC-BIN-FUT-MKT` | 001、004–006、008、103 | [USDⓈ-M Market Data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data) | 当前 REST 字段、保留期和部分系统压力数据；不能证明历史 schema 相同 |
| `SRC-BIN-FUT-WS` | 001、002、007 | [aggTrade](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Aggregate-Trade-Streams)、[diff depth](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Diff-Book-Depth-Streams)、[forceOrder](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Liquidation-Order-Streams) | 实时消息语义；不等同于无缺口历史档案 |
| `SRC-BIN-SPOT-WS` | 003 | [Binance Spot WebSocket Streams](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams) | 现货成交、depth、book ticker 的实时协议 |
| `SRC-BIN-USER` | 009 | [USDⓈ-M User Data Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/user-data-streams/Connect) | 账户/订单事件接口；自己的端到端延迟仍须本地测量 |
| `SRC-BIN-PRIVATE-REST` | 009 | [USDⓈ-M Account REST](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)、[Trade REST](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade) | Account V3、position、open orders、user trades、income、commission 与持仓模式等权威快照；与 User Stream 共同完成恢复/对账 |
| `SRC-BIN-OPS` | 008、013 | [USDⓈ-M Market Data / exchangeInfo](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)、[API Change Log](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log)、[官方公告入口](https://www.binance.com/en/support/announcement) | 合约当前状态、规则/API 变更和已公告维护；不存在完整、保证提前的机器可读停服日历，仍须实时健康探针和签名人工维护输入 |
| `SRC-OPS-MANUAL` | 013 | 系统内部签名维护输入契约 | 经授权操作者录入的维护/异常窗口、来源链接、录入人、签名、创建时间和到期时间；未知来源、过期或撤销后不得继续作为有效安全输入 |
| `SRC-BIN-CHANGE` | 007、008 | [USDⓈ-M Change Log](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log) | 语义和接口变更断点 |
| `SRC-BIN-ARCHIVE` | 010 | [Binance Public Data](https://github.com/binance/binance-public-data) | 官方公开归档种类和历史文件 schema；不包含完整历史 L2/OI/比率 |
| `SRC-OKX-HIST` | 011 | [Historical Data](https://www.okx.com/historical-data)、[Historical Market Data API](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data) | OKX 历史数据起点、模块和深度覆盖；不能替代 Binance 执行真值 |
| `SRC-OKX-LIQ` | 109 | [OKX API Guide](https://www.okx.com/docs-v5/en/)、[Change Log](https://www.okx.com/docs-v5/log_en/) | 旧平台历史 liquidation REST 下线及实时 channel 的覆盖边界；recent liquidation 不应解释为平台全量 |
| `SRC-BYB-PUBLIC` | 101 | [orderbook](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook)、[trade](https://bybit-exchange.github.io/docs/v5/websocket/public/trade)、[OI](https://bybit-exchange.github.io/docs/v5/market/open-interest)、[funding](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)、[long/short](https://bybit-exchange.github.io/docs/v5/market/long-short-ratio) | Bybit 市场字段、单位和实时/REST 频率 |
| `SRC-BYB-RISK` | 101 | [allLiquidation](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)、[ADL](https://bybit-exchange.github.io/docs/v5/websocket/public/adl-alert)、[insurance](https://bybit-exchange.github.io/docs/v5/websocket/public/insurance-pool)、[历史下载](https://www.bybit.com/en/derivative-activity/history-data) | 风险流和官方可下载目录；本地仍须审计断线、品种、日期和深度覆盖 |
| `SRC-DER-MKT` | 102 | [DVOL](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data)、[instruments](https://docs.deribit.com/api-reference/market-data/public-get_instruments)、[book summary](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency)、[order book](https://docs.deribit.com/api-reference/market-data/public-get_order_book)、[trades](https://docs.deribit.com/api-reference/market-data/public-get_last_trades_by_currency) | 期权合约、报价、成交、OI/Greeks 和波动率指数；不提供净 dealer side |
| `SRC-ETF-IBIT` | 104 | [iShares IBIT Holdings](https://www.ishares.com/us/products/333011/ishares-bitcoin-trust-etf) | 单一发行人的官方持仓/份额/NAV 披露；不是全市场净流入真值，发布时间须另存 |
| `SRC-TARDIS` | 105 | [历史数据说明](https://docs.tardis.dev/faq/data)、[CSV 规范](https://docs.tardis.dev/downloadable-csv-files) | 供应商覆盖与标准化 schema；供应商 capture 仍不等于交易所真值 |
| `SRC-CME-CRYPTO` | 107 | [Crypto Data/FAQ](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-cryptocurrency-futures.html)、[24/7 变更](https://www.cmegroup.com/media-room/press-releases/2026/6/01/cme_group_announceslaunchof247cryptocurrencyfuturesandoptionstra.html) | CME 数据许可、产品范围、2026-05-29 结构断点和 weekend/holiday trade-date 语义 |
| `SRC-CB-WS` | 108 | [Coinbase Exchange Channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels) | 实时 L2/L3/成交协议；不证明存在官方批量历史文件 |
| `SRC-PEG` | 012 | [Tether Transparency](https://tether.to/transparency/?tab=reports)、[Circle Transparency](https://www.circle.com/transparency) | 发行人披露和慢频状态；实时脱锚必须另取多场可交易价格 |
| `SRC-PEG-MKT-CAND` | 012 | [Coinbase products](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-all-known-trading-pairs)、[ticker](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker)、[Kraken asset pairs](https://docs.kraken.com/api-reference/market-data/get-tradable-asset-pairs)、[ticker](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/ticker) | 用于 M6A 发现并复核可交易稳定币/法币市场的候选；产品、地区和在线状态须当时确认，不能预先算作 quorum |
| `SRC-EVENT` | 013 | [FOMC](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)、[BLS](https://www.bls.gov/schedule/)、[BEA](https://www.bea.gov/news/schedule/) | 官方宏观预定发布时间；交易所维护使用 `SRC-BIN-OPS` 与签名人工输入，不能假定存在完整日历 |

### 9.2 P0-R：形成可信研究和 paper 闭环

| Data ID | 数据 | 主要用途 | 当前可获得性与限制 | 采集/使用结论 |
|---|---|---|---|---|
| `DATA-001` | Binance 永续成交/aggTrade | $D_t$、成交密度、冲击 | 实时可得；aggTrade 有聚合语义，不能解释为人数。当前 REST aggTrades 有总量 `q` 与普通量 `nq`，但不能还原每笔 RPI；官方历史归档也不含 `nq/isRPITrade` | P0-R 核心依赖；实时与历史 schema 分开版本化 |
| `DATA-002` | Binance 永续 diff depth + REST snapshot | OFI、microprice、$R_t$、执行价格 | 必须按 sequence 重建；标准 depth 排除 RPI；缺口后需失效并重同步 | P0-R 核心依赖 |
| `DATA-003` | Binance 现货成交、depth、book ticker | 现货—永续确认、basis、价格发现 | 与永续时间和 symbol 规范不同；同样需要序列和延迟治理 | 低成本前瞻 shadow；不是首个 Binance 永续 G1 的阻塞项 |
| `DATA-004` | mark/index、premium/basis、funding | 拥挤、定价偏离、成本 | funding 是慢变量；basis 历史接口保留有限 | P0-R 核心依赖 |
| `DATA-005` | OI 当前值与自建历史 | $L_t$、去杠杆状态 | 官方 OI history 仅约最近 1 个月；必须持续自存，且不得方向化解释 | P0-R 核心依赖 |
| `DATA-006` | global/top long-short、taker 指标 | $C_t$ 候选 | 多数仅最近 30 天；top 部分端点需 API key。单一 account-ratio 内每账户只计一次，但 global/top 样本可能重叠且各指标高度相关 | 低成本前瞻留存；未经消融不得当作独立证据重复加权 |
| `DATA-007` | Binance forceOrder | $F_t$ 下界、踩踏事件 | 官方文档自 2026-04-14 起将选择语义由“latest”改述为每 symbol、每 1000ms 最大一笔；是否同日改变底层生成逻辑尚未核实。它始终是 censored observation | P0-R 核心依赖；断点前后按未知语义边界分开，归档对照前不得直接拼接或当强平真值 |
| `DATA-008` | exchangeInfo、合约过滤器、限价、状态、指数成分 | 合约规则、容量、数据/执行健康 | schema 和规则会更新；必须版本化 | P0-R 核心依赖 |
| `DATA-009` | 自身订单、成交、费用、资金费、余额、持仓、延迟、错误 | 成本真值、回测校准、对账、风控 | 需要私有只读/交易权限；禁止提款权限。P0-R 先冻结 schema、费率和账户契约；M6B 只收集当前固定版本的真实遥测，不得在同一轮自适应更新 | 账户安全契约为 P0-R；经 G4B 审核的 M6B 数据只可校准下一 challenger，并重新经过 shadow、批准和新一轮 canary |
| `DATA-010` | Binance 历史成交/K 线与历史 L2 方案 | 训练与主执行场所回放 | Binance 公共归档含 trades/aggTrades/klines，但不是完整 L2/OI/比率历史；Binance L2 需前瞻采集或合格供应商 | 立即自采；供应商样本合格且能改变决策后才申请购买 |
| `DATA-011` | OKX 官方历史 tick、funding 与 L2 | 免费的跨年份微观结构研究、replay 工程和外部机理检查 | 官方页给出 2021-09 起 tick、2022-03 起 funding、2023-03 起高分辨率 L2；50 档在逐步弃用，5000 档仅自 2025-11-01 起，400/5000 的实际品种和日期覆盖仍须审计 | 先抽取 BTC 小样本审计，再按特征所需价带选择最小深度；不得用 OKX 通过 Binance G2 |

P0-R 的阻塞性依赖是 `DATA-001/002/004/005/007/008/010` 和 `DATA-009` 的安全/账户契约。`DATA-003/006` 可低成本留存但不应扩大首轮研究；`DATA-011` 加速 replay 与外部机理检查，却不能证明 Binance 条件分布、执行或盈利。

当前 `config/account_telemetry_contract.v1.json` 已将 `DATA-009` 的字段和安全边界冻结为可验证配置：订单状态、逐笔成交、独立资金费结算、账户更新和 REST 恢复快照均要求保留 local/source 时间、稳定身份、费用/资金费、余额/持仓和原始 payload hash；任何未解释持仓差异必须阻止新增风险。该配置仅适用于未来 paper/Testnet 的只读遥测准备，明确禁止交易/提款，尚未连接账户，也不是费用、滑点或实盘成本的观察证据。

为使该契约可以被实际离线检查而不引入账户连接，`binance-usdm-private.v1` 仅定义一层本地 source-to-artifact 映射：已脱敏的订单/账户用户流、funding income 和恢复快照各自保留原始 payload 摘要、来源/本地时间及稳定身份，然后立即按冻结契约审计。它不把 API key、签名或原始 payload 写入目标 artifact，也不把 source schema 名称误当成交易所永久承诺；任何 wire 语义或字段变化必须停机并产生新的映射/契约版本。此机制防止静默 schema 漂移进入 paper 对账，但不能证明私有连接完整、导出无遗漏、账户真值、费用正确或执行质量。

`DATA-011` 现有本地只读 `audit-okx-historical` 工具与计划模板：每个声明日期都必须以实际下载文件单独审计缺失、格式、checksum、抽样时间覆盖和最大 bid/ask 档数；不识别的 schema 或日期不匹配必须显式失败，不得填零。该审计只能支持 OKX replay/外部机理工程，报告固定为 `eligible_for_binance_g2=false`；截至当前尚无已审计的官方 BTC 文件，因此没有任何 OKX 覆盖或深度结论。

为满足 M1 的“自采与官方归档至少一个重叠日对照”工程条件，`DATA-010` 还提供独立的 `audit-binance-aggtrade-overlap`。它只接受一个已冻结的计划：计划同时固定官方 USD-M `aggTrades` 日文件和 `.CHECKSUM` 的 URL/本地路径、SHA-256、官方 CSV 列序、日期、当前 `SEALED_CURRENT` forward collection 和 Source Registry ID/SHA-256。审计器先要求本地 archive 与官方伴随 checksum、计划摘要三者相同，再重验 collection 的 terminal manifest、raw segment、audit/replay 摘要与 registry binding；随后以 aggregate trade ID 将 archive 与 collection 中 `ACTUAL` trade 对照，要求 price、quantity、buyer-maker 语义和 exchange timestamp 全部相同。至少一个精确匹配仅证明两个固定表示在交集上无该类差异；它不提供全日完整性分母、不会修复 collector gap，不验证 L2/OI/funding，也不成为 G1/G2/G3、成本或交易许可的证据。截至当前尚未对真实官方日文件运行该审计，因此没有 archive-overlap 成功结论。

### 9.3 G4A-Live Safety：真实资金前的硬依赖

| Data ID | 数据 | 主要用途 | 当前可获得性与限制 | 结论 |
|---|---|---|---|---|
| `DATA-012` | USDT/USDC 可交易价格与主执行抵押品状态 | 脱锚、结算和保证金风险闸门 | BTCUSDT 以 USDT 暴露为主；发行人披露不能替代实时成交价。quorum 的每票必须来自独立运营 venue/故障域，单 venue 或同一 vendor 的多个 pair/feed 只计一票；必须使用满足最小可执行名义量的 bid/ask 口径 | G4A 前从候选产品目录选定并复核合格市场，冻结 product whitelist、最小名义量、票数、陈旧度、持续阈值、恢复迟滞和抵押品处置；USDC 异常不得自动归因为 USDT |
| `DATA-013` | 官方 FOMC、BLS、BEA 日历与交易所公告/status | 预定消息和停服窗口的禁入/降风险 | 发布时间是事实，实际值和市场共识另属数据；宏观日历会调整；`SRC-BIN-OPS` 不保证完整或提前，因此还要结合实时公共/私有健康探针和带签名、有效期的人工维护窗口 | 交易所服务/账户风险属于 G4A 安全依赖；每类输入须有 Source ID、SLA、陈旧动作和 fail-closed 规则。宏观 blackout 需资金所有者明确启用或由 `H-009` 支持 |

### 9.4 P1：核心模型通过 G2/E2 后，逐个评估扩充

| Data ID | 数据 | 独立信息 | 关键限制 | 晋级条件 |
|---|---|---|---|---|
| `DATA-101` | Bybit L2、成交、ticker/OI/funding、allLiquidation、ADL/保险池 | 第二 venue 的相对独立压力、跨场同步、更高覆盖强平和系统压力 | 公共 book 排除 RPI；OI REST 可分页至合约上线，官方历史下载现含部分 book/trade 文件，但品种、日期、深度与完整性需逐文件审计；实时强平/ADL 仍需自存和连接监控 | M1 起低成本 shadow 留存不可回补的 liquidation/ADL/保险流；是否影响决策仍为 P1，须证明减少局部假信号或尾部损失 |
| `DATA-102` | Deribit DVOL、期权链、IV、Greeks、OI、期限结构 | 前瞻波动、偏度、到期集中与尾部风险 | OI 不透露净 dealer side；不可无假设计算确定性 GEX | 优先用于风险/仓位，方向 alpha 单独验证 |
| `DATA-103` | Binance ADL 风险、保险基金、指数成分 | 交易所系统压力、指数源变化 | ADL 风险更新较慢，适合作为 veto/context；历史不可完整回补 | M1 起低成本 shadow 留存；P1 消融证明能减少尾部损失或错误开仓后才使用 |
| `DATA-104` | ETF 官方每日持仓/份额/NAV 快照 | 慢速法币需求与美国时段背景 | `as-of` 日期不等于实际发布时间，“净流入”通常是派生值 | M1 仅低成本影子留存；P1 完成 point-in-time 消融后才可使用 |
| `DATA-105` | 合格历史 tick/L2 供应商（候选 Tardis） | 补齐 Binance 历史 L2、强平和衍生品 tick | 付费、供应商 capture 与交易所真值仍有差异；已有 OKX 免费研究集后购买门槛应更高 | 免费样本与实时自采 schema/重建结果对齐，且 Binance 专属历史确有净价值后再购买 |
| `DATA-106` | ETH 同构数据 | 外部稳定性和参数脆弱性检验 | ETH 不是 BTC 的独立时期样本，也不自动获得交易资格 | 仅验证；单独通过全部闸门才交易 |
| `DATA-107` | CME BTC futures/期权市场数据 | 受监管 venue 的价格发现、basis 与 OI | 实时/历史深度通常有许可和费用；多数加密期货/期权自 2026-05-29 起 24/7（保留维护窗），Spot-Quoted futures 不在该范围；周末/假日成交使用下一营业日 trade date | 使用产品白名单，同时保存 event time 与 CME trade date；断点前后分开验证，旧“周末 CME 缺口”假设不得沿用 |
| `DATA-108` | Coinbase BTC-USD L2/L3 与逐笔成交 | 独立美元现货价格发现、lead-lag 与异常检测 | 实时公开；截至本次核验未发现官方批量历史 L2/L3，不能把“未发现”写成永久不可得；成交 side 语义需按官方定义处理 | Bybit 之后的第二个跨场增量候选 |
| `DATA-109` | OKX 实时 liquidation channel | OKX 场所的强制去杠杆上下文 | 旧平台历史 REST 已下线；官方明确 recent liquidation data 不代表平台全部强平，且实时断线后不可完整补回 | 只作 censored shadow；M1 sidecar 可选留存，P1 独立验证后才使用 |

这里的生命周期统一为：M1 只允许在严格时间预算内做**可取消、非阻塞的 archival sidecar**，失败不能拖延 Binance P0-R；G2/E2 后才扩接和评估；通过该数据族独立晋级后，才允许成为 champion 或风险政策依赖。

### 9.5 P2：可获得但当前不值得阻塞 P0/P1

| Data ID | 数据 | 潜在用途 | 为什么暂缓 |
|---|---|---|---|
| `DATA-201` | Hyperliquid、Coinbase International 等更多衍生品 venue | 更广的价格发现和 OI/funding 网络 | 在 Bybit/OKX/Coinbase 现货尚未证明增量前会显著增加 schema、时钟和运维复杂度 |
| `DATA-202` | 原始链上转账、mempool、矿工/验证者数据 | 慢频供给与大额活动 | 链到交易意图的映射弱，时间尺度与 V1 不匹配 |
| `DATA-203` | 第三方交易所流入/流出、地址标签、储备 | 交易所压力背景 | 标签会误分和修订，许可成本高；必须保留 point-in-time 标签版本 |
| `DATA-204` | 稳定币周度供给/铸销与发行人储备 | 法币通道与慢频需求背景 | 低频、发行人披露有时滞；mint/burn 也可能是库存或跨链迁移，不适合作微观入场 |
| `DATA-205` | CFTC COT | CME 参与者周度拥挤 | 周频且报告日与发布日期不同，只适合背景 |
| `DATA-206` | 新闻与社交文本/情绪 | 突发事件、风险分类 | 噪声、机器人、许可、修订和时效问题大；默认仅用于风险提示 |
| `DATA-207` | 深度学习、强化学习所需的大规模替代特征 | 非线性交互 | 数据量、漂移、解释与验证成本远高于当前明确价值 |

`POLICY-EXT-001`：慢频链上、ETF 和社交数据默认不进入 V1 微观入场。这是控制范围的可逆政策，不是关于其“必然无效”的正向科学命题；只有预注册实验显示稳定净增量时才晋级。

### 9.6 两类数据的晋级流程

数据不是越多越好。预测/上下文候选数据 $j$ 的净价值按以下概念评估：

\[
V_j = \Delta OOS\ Utility_j
\times Reliability_j
\times ProductionAvailability_j
- AcquisitionCost_j
- OperationalCost_j
- OverfitRisk_j
\]

预测/上下文数据强制流程：

```text
明确独立信息假设
→ 影子采集且不影响 champion
→ 数据质量/时效/许可报告
→ 单独消融和泄漏审计
→ 锁定样本外与成本后评估
→ 复杂度和故障域评估
→ 人工批准生产晋级
→ 可回滚监控
```

如果提升只存在于单一月份、单一方向、少数极端交易或调参样本中，则视为失败。若提升小于数据购买与运维成本，也视为失败。

安全/运营数据使用不同闸门：

```text
定义 hazard 与不可逆后果
→ 冻结来源独立性、freshness、quorum 与 fail-closed 契约
→ 测量覆盖率、误报、漏报和故障域
→ fixture + shadow + 生产配置故障演练
→ 资金所有者批准风险偏好与处置动作
→ 人工准入、监控和回滚
```

这类数据可以降低交易次数或收益，不能因为“没有提高 PnL”而自动删除。相反，若它无法可靠覆盖目标 hazard、误报导致不可接受的处置，或恢复/人工接管不可实施，则不得进入真实资金路径。宏观 blackout 属于待检验/待批准的风险政策；账户对账、交易所可用性和实际抵押品风险属于资金安全硬约束。

---

## 10. 可证伪研究命题

| Hypothesis ID | 命题 | 最小对照 | 失败判据 |
|---|---|---|---|
| `H-001` | 极值后的吸收—响应链比极值单变量更能预测成本后 TP-first | 价格/波动/成交量 + 极值基线 | 锁定样本外无稳定增量 |
| `H-002` | $R_t$ 在 $D_t$ 之外提供独立信息 | 仅 $D_t$ 模型 | 加入 R 后校准/效用无改善或只在训练期改善 |
| `H-003` | $D_t\times L_t$ 的作用依赖状态而非固定线性 | 无交互的正则化基线 | 交互不稳定、符号反复或成本后无增量 |
| `H-004` | 强平 + OI 收缩只在韧性提升时支持修复 | 仅强平/OI 模型 | 不加 R 已同等稳定，或加 R 无增量 |
| `H-005` | 第二 venue 能识别 Binance 局部假吸收 | Binance-only champion | 跨场特征无独立增量或延迟使其不可用 |
| `H-006` | 期权风险状态改善波动预测、仓位和尾部控制 | 无期权风险上下文 | 净效用不升或数据成本超过收益 |
| `H-007` | 多空参数和概率校准存在稳定不对称 | 共享参数模型 | 独立模型长期不优于共享模型则简化 |
| `H-008` | 自身执行遥测显著修正公共盘口推算成本 | 公共盘口成本模型 | 两者长期误差可忽略时可简化，但仍保留对账 |
| `H-009` | 宏观事件 blackout 可能降低尾部损失 | 无 blackout 同期模拟 | 风险无改善且机会成本显著时不启用或缩小窗口；资金所有者仍可基于风险偏好显式要求 |
| `H-010` | closed 4H RSI 在 fixed 15m RSI 上有增量 | `C2-C1` | 同一 outcome-free $U$、相同成本/模拟器下无预注册增量即拒绝 |
| `H-011` | 冻结 regime 在 C2 上有增量 | `C3-C2` | 无成本后、校准或稳定性增量即拒绝 |
| `H-012` | 既有 $D/R/L$ 组合在 C3 上有增量 | `C4-C3` | 无同 $U$ 增量或质量约束失效即拒绝 |
| `H-013` | frozen dynamic exit 在 C4 的 exact entry submission 与 actual fill cohort 上有增量且不扩大 tail | `C5-C4` | 改变 exact entry/fill cohort、扩大 tail 或无增量即拒绝 |
| `H-014` | fixed RSI 路径相对完全无 RSI 的 $Cmu$ 在同一 $U$ 上有增量 | `C4-Cmu` | 以不同 $U$、成本或模拟器比较，或无增量即拒绝 |

外部来源（第二 venue、期权、ETF、链上或宏观）若只有代理变量、时间对齐不完整、版本/vintage 缺失或无法证明当时可用，只能登记为诊断性 context/proxy。它们不得单独支持或否定任一 H，也不得填补 Binance 主 cohort 的 G2 证据缺口。

---

## 11. 验证体系

### 11.1 验证顺序

1. 价格、波动、成交量和时间特征基线。
2. 加入 $D_t$。
3. 加入 $L_t,C_t$。
4. 加入 $F_t$。
5. 加入 $R_t$。
6. 加入交互和 episode 状态。
7. 逐个加入跨场、期权和事件数据。

每一步只能声明相对上一步的增量，不能用最终复杂模型掩盖底层因子无效。

候选与 control 必须在同一预先冻结 cohort 上使用同一 episode 边界、可用性规则、标签尾部、行动政策和成本增量；不得让候选使用更有利的入场/退出、不同样本或较低成本。H-001 需要相对极值 control 的预声明增量及成本后效用/稳定性证据；log loss 单独改善只说明概率评分变化，不能单独裁决 H-001。

### 11.2 数据与切分

- 以 episode 为基本样本单位，避免一个事件被切到训练和验证两侧。
- 使用 purged walk-forward；embargo 至少覆盖最大标签/持有期和数据修订窗口。
- 保留一次性锁定样本外集；所有阈值在查看该结果前预注册。最终窗口的开放必须留下绑定 protocol、完整 labels artifact 与受控账本的一次性 receipt；开发研究只可使用窗口开始前已经结束的标签，不能把 holdout、跨界或之后的标签混入训练/校准。最终评分只从 pre-holdout 拟合，并把报告摘要写入同一账本的唯一 consumption entry；即使覆盖不足，已打开的 holdout 也不得在调参后重跑。一经读取任一 holdout 结果，该窗口对后续协议永久标记为 `SEEN`；同一冻结配置的再次运行只可作为可复现性检查，不能重新选择候选、阈值、控制组、成本或理论结论。
- 任何修订数据必须保存当时版本，不允许 hindsight correction 泄漏。
- 长、短、年份、波动状态、趋势状态、交易时段分别报告。

对按月或更长窗口演进的历史研究，必须使用**事前 chronology 分工**：在读取任何 outcome 前，把互不重叠的日期版本化为 `DEVELOPMENT`、`CALIBRATION`、`HOLDOUT`。模型、特征和 action policy 只在 DEVELOPMENT 构建；概率校准只在 CALIBRATION 完成；随后冻结唯一 candidate，再用一次性 receipt 打开更晚 HOLDOUT。任一数据窗口一经读取，便永久转为 `SEEN`；无论结果是覆盖不足、预测失败、经济失败、运行失败还是通过，都不得在调参、换候选、改成本或放宽门后再次充当独立验证集。失败版本应退役或在新的 chronology 上建立新版本，而不是救回已消费的 holdout。

### 11.3 指标

预测层：

- log loss / Brier score；
- calibration curve、ECE 或等价校准误差；
- TP/SL/STRUCTURE_EXIT/timeout 分类别召回与混淆；
- 不确定性覆盖与 abstain 后的 coverage。

交易层：

- 成本后期望值与置信区间；
- profit factor、盈亏比，不单看胜率；
- 最大回撤、expected shortfall、最差 episode；
- turnover、容量、持仓时长、方向/时期贡献集中度；
- 延迟、部分成交、拒单和滑点敏感性。

稳定性层：

- 参数邻域、窗口和成本扰动；
- 逐因子/逐数据源消融；
- 多重尝试校正（大量试验时使用 Deflated Sharpe Ratio、PBO 或等价方法）；
- offline/live 特征与状态一致性。

H-001 的 candidate 与极值直反 control 必须在同一冻结 cohort 使用同一 action policy、entry/exit 定义、标签尾部和成本增量；log loss 单独改善不构成 H-001 裁决，只有预声明的相对成本后效用、校准和稳定性增量才可进入后续判定。

### 11.4 理论失败条件

只有达到 M0B 预注册的总有效 episode 数、状态覆盖或置信区间精度后，才允许把下列结果判为失败。状态覆盖不是事后按收益挑选“好/坏市况”：必须在最终标签和结果打开前冻结状态分类器 artifact 的 ID/SHA-256、互斥状态 ID 及每状态最低有效 episode 数。分类器只读取 feature vector，不读取 outcome；它把原 label 派生成新的 state-bound label artifact，研究运行时重新计算每行状态并校验同一摘要。总样本下限、walk-forward folds 与 embargo 也是协议的一部分，运行时不得用命令行临时改变。冻结运行不论形成评估结果还是 `WAIT_DATA`，都要写入新的不可覆盖报告，绑定输入 labels、协议、G1 与分类器摘要。任何摘要/重算不符、未分类/未知状态、预声明状态样本不足或总有效 episode 不足，研究流程都必须停止在 `INCONCLUSIVE/WAIT_DATA`，返回采集而不是训练或宣称支持/否定。

历史 `research_protocol.preregistered.v1.json` 因理论 H-ID 漂移、holdout 资格不可到达和动作/标签不一致，已由摘要绑定的 `research_protocol_supersession.v2.json` 在 G1 PASS、标签结果和 holdout 打开前废止；finalizer 无论是否省略 guard 都必须拒绝 v1。当前唯一前进路线是 `research_protocol.v2.draft.json`，但它仍是不可 finalise 的 S0 草案：真实 DEVELOPMENT/HOLDOUT capture plan、acceptance、G1 PASS report、冻结 context/action 阈值和组件软件摘要仍为 `REQUIRED`，所以它既不是预注册完成，也不授权研究评分或交易。

Protocol v2 的可执行基础已把理论假设与验收门分开：H-001 比较“D + 1 秒价格冲击 + 方向韧性响应链”与“D + 1 秒价格冲击”；H-002 检验 R 相对 D 的独立增量；H-003 检验 `D × L × liquidity-state` 相对主效应；H-004 检验强平与 OI 条件中 R improvement 的增量。G2 必须 BUY/SELL 分模、每侧覆盖充足、5 个 purged walk-forward folds 中至少 4 个达到预声明增量，并同时执行 fold 内校准、10/20 bps 反事实全成本代理、UTC 日 block bootstrap、日期/状态/方向集中度和 `SUPPORT/FAIL/INCONCLUSIVE` 裁决。这里的 utility 是未成交的市场路径反事实，不是已观察手续费、滑点、funding 或执行 PnL；真实 G2 数据尚不存在。

上述比较的 candidate/control 必须同 cohort、同动作政策、同成本增量和同 holdout 可见性；任一不一致只可报告为诊断，不能用于 H-001–H-004 的 `SUPPORT/FAIL`。严格 post-pressure $R_t$ 不可得时，涉及 R 的命题应为 `INCONCLUSIVE`，而不是用同步 proxy 代替后宣称失败或支持。

满足证据充足条件后，任一核心条件成立，应停止晋级并简化或否定当前模型：

- 在合理成本假设下，锁定样本外无正增量。
- 结果由极少数交易、单一牛熊阶段或单一方向贡献。
- 概率严重失准，EV 点估计无法转化为真实结果。
- 参数、窗口或微小成本变化导致结果崩溃。
- 数据在生产无法以训练时的时效、许可和质量获得。
- offline 与 live 无法重现同一特征、状态和决策。
- 执行失败、滑点或资金费吞噬研究增量。
- 运维和数据成本高于可验证收益。

---

## 12. 风险与证据等级

### 12.1 不可优化的硬风险

以下值必须由资金所有者在 canary 前明确批准：

- 单 episode 最大损失；
- 单日损失和最大回撤；
- 总名义敞口、杠杆和保证金占用；
- 单 venue 暴露；
- 单轮 canary 的累计允许损失、累计成交名义量、最大订单/episode 数和最长日历时间；
- 最大滑点和订单重试；
- 数据陈旧、时钟漂移、持仓不一致时的停机行为；
- API 权限、提款禁用和密钥轮换规则。

历史上“最赚钱”的风险值不能成为默认生产值。

### 12.2 证据阶梯

| 等级 | 含义 | 能声明什么 |
|---|---|---|
| E0 | 理论与来源审查 | 数据可能可得、命题可检验 |
| E0-X | 受限外部/历史诊断 | 仅检查语义、时间对齐、覆盖与 proxy 局限；不裁决 H、不构成 G1/G2 或市场验证 |
| E1 | 数据质量与确定性重放 | 数据链可用、特征可复现 |
| E2 | 合格锁定样本外回测 | 在特定数据/成本假设下有历史证据 |
| E3 | shadow / paper | live 数据与系统运行闭环成立，不代表真实成交盈利 |
| E4 | 小资金 canary 经 G4B 审核 | 在严格限额下得到达到预注册要求的有限实盘执行证据 |
| E5 | 生产观察 | 多状态、足够样本和持续监控下的有限生产证据 |

当前项目仅处于 E0。后续任何报告必须明确自身等级。

---

## 13. 持续优化与变更治理

### 13.1 版本链

每次实验和决策必须能追溯：

```text
raw schema version
→ normalization version
→ feature version
→ episode/label version
→ model + calibration version
→ policy version
→ risk-policy version
→ execution version
```

### 13.2 champion/challenger

- champion 只运行已批准版本。
- challenger 使用相同 live 数据影子计算，不影响下单。
- challenger 必须在预注册窗口内完成质量、校准、效用、稳定性和故障测试。
- 晋级需要人工审批、发布记录和一键回滚路径。
- 所有失败实验同样登记，防止重复数据挖掘和选择性汇报。
- 每一轮 M6B 固定模型、校准、政策、风险和执行版本；本轮真实遥测只能进入下一 challenger，重新经过 shadow、人工批准和新一轮 canary，不能更新正在产生 G4B 证据的 active 版本。
- Canary 证据不足不产生无限续期权；每次继续必须在上一轮总风险预算和到期点触发前重新获得资金所有者的显式授权。

### 13.3 禁止的“持续优化”

- 根据最近几笔盈亏自动调阈值或扩仓。
- 在线训练后未经锁定样本和 shadow 直接替换模型。
- 使用本轮 canary 成交即时调整同一轮模型、成本参数、门槛或风险预算。
- 同时改变数据、标签、模型和执行，再把结果归功于某一个因素。
- 为提高历史收益不断增加特征、状态和例外规则。
- 在数据质量下降时用模型填补并继续正常交易。

### 13.4 优化顺序

1. 数据完整性和点时正确性。
2. 成本、执行和账户真值。
3. 简单基线与可证伪性。
4. 风险和故障恢复。
5. 入场概率与校准。
6. 新数据的独立增量。
7. 最后才是模型复杂度和更多标的。

---

## 14. 当前已知未知与非主张

- 尚不知道五因子在 BTCUSDT 的目标持有期内是否有成本后 alpha。
- 尚不知道吸收定义在不同波动阶段是否稳定。
- 尚没有足够历史 L2、OI、ratio 和自身成交数据完成 E1/E2。
- 尚未确定最优 episode 触发、障碍和持有期；这些是研究参数。
- 尚未验证跨 venue 数据的时间同步与增量。
- 尚未验证 Deribit 期权数据对方向、波动或仓位的净价值。
- 尚未设置任何实盘风险数值或获得实盘授权。
- 2025-01 的 v1 历史材料只保留为诊断事实：其协议语义、动作/标签与当前 H-ID/资格链不一致，且不具备当前 future-role/holdout 约束；不得追溯标记为 H 失败、G2 结果或当前候选的训练/选择依据。
- 若在有上限的 external diagnostic 中复查该材料，结论只能是数据/语义/代理限制或 `INCONCLUSIVE`；任何 fresh 前瞻数据、G1、DEVELOPMENT/HOLDOUT 或 holdout 路线仍保持封闭，直到独立的事前契约和真实证据满足。
- January v4 development 的最新 A3 只读事实为：官方 archive/checksum 完整性通过，但 bookDepth 有 3 个 canonical 内部 gap（2025-01-06 一个；2025-01-16 两个）；2,242 行 v4 rows 中恰有 1 个 `FIT` row 的 pressure window 与该 gap 相交。该污染只说明旧 v4 产物不能原样复用；它不是策略有效性、H 支持/失败、G2 或市场结论。
- February 的唯一事实终态为 [Sol A2F1](./config/sol_decision.s0-009-r1-acquisition-gap-censoring.a2f1.json) 所绑定的 `FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED`：该月已 `SEEN`、未生成 input receipt、未评分，独立角色永久消费；禁止 builder replay、重取、验证或评分。March 仍未读、未授权；RSI/A3 只可作为 future-only 理论 DRAFT，不能改变上述终态、G1 或交易权限。当前证据等级仍为 E0。
- 本理论不主张识别真实心理、操纵者、鲸鱼意图或净 dealer gamma。
- 本理论不主张自动交易一定盈利；`ABSTAIN` 和否定假设都是合格结果。

---

## 15. RSI-MTF-DRL-PM v0.2：future-only 可审计理论草案

`RSI-MTF-DLR-PM v0.1` 已被本节**明确 supersede**，不得实现、回测、引用为候选或用于解释历史结果。Sol 阶段审查与 P0-RSI-01 静态契约验收均已 PASS：`RSI-MTF-DRL-PM v0.2` 当前为 `P0-RSI-01_PASS / E0 / SYNTHETIC_PRIMITIVES_ONLY`。契约 [rsi_mtf_drl_pm.research_contract.v0_2.json](./config/rsi_mtf_drl_pm.research_contract.v0_2.json) 仍是 `REVIEW_READY / E0 / REJECT_FREEZE`，strategy binding 为 `ABSENT_BY_DESIGN`。为避免 CORE 文件 SHA 与其自身绑定的 contract full digest 形成自引用，CORE 永不嵌入该 full digest；canonical digest 仅由 contract artifact 与非 CORE 的治理记录发布。唯一新增授权是 P0-RSI-02 的纯合成 strategy primitives、implementation manifest 与 synthetic tests；禁止市场/历史数据、任何 reader/network/exchange adapter、backtest、calibration、holdout、paper 或 trading。A3、January、February、March、活动 G1 与其 package 保持隔离且不可写。`DRL` 是既有 $D/R/L$ tuple，`PM=Position Management`。

### 15.1 UTC closed-bar RSI、组合事件与可用性

对每个 UTC 15m/4H 已闭合 mark-close 序列 $C_j$，令 $\Delta_j=C_j-C_{j-1}$、$g_j=\max(\Delta_j,0)$、$\ell_j=\max(-\Delta_j,0)$；这里 $\ell$ 仅表示 RSI loss，绝不等同于既有 $L_t$。Wilder RSI(14) 以 14 个闭合变化的均值初始化，后续为：

\[
\bar g_j=(13\bar g_{j-1}+g_j)/14,\quad
\bar\ell_j=(13\bar\ell_{j-1}+\ell_j)/14,\quad
RSI_j=100-100/(1+\bar g_j/\bar\ell_j).
\]

lane clock 定义为：

\[
a_{lane}(e)=\begin{cases}available\_at(e),&lane=ACTUAL\_ONLY\\reconstructed\_available\_at(e),&lane=RECONSTRUCTED\_CAUSAL\_DEVELOPMENT\end{cases},\qquad
\mathcal I^{lane}_{\le\tau}=\{e:a_{lane}(e)\le decision\_at=\tau\}.
\]

`ACTUAL_ONLY` 的 $a_{lane}$ 必须不早于 bar close；`RECONSTRUCTED_CAUSAL_DEVELOPMENT` 仅在另行授权且满足 §2.3 冻结 causal-release 时存在。其 `reconstructed_available_at` 必须逐 event 落盘，并是 contract 冻结纯函数 $f(raw\_exchange\_time,source\_sequence\_or\_frozen\_import\_key,schema\_version,fixed\_release\_lag)$；bar feature 不得早于 `bar_close_at`。禁止使用 replay wall-clock、mtime 或后来的 capture time；该值是该 lane 唯一的 as-of join 时钟，不得伪装为 `ACTUAL`。它不新增第三种 `availability_kind`。本节所有 RSI、$\kappa$、$t^-$、Confirm/action gates、EntryZone、$I_0/G_0/Pivot/target$ boundaries 与 management evaluation 的输入，统一必须属于 $\mathcal I^{lane}_{\le\tau}$。seed 为 $\bar g_{14}=\frac1{14}\sum_{j=1}^{14}g_j$、$\bar\ell_{14}=\frac1{14}\sum_{j=1}^{14}\ell_j$。若 $\bar g=\bar\ell=0$，RSI=50；若 $\bar\ell=0<\bar g$，RSI=100；若 $\bar g=0<\bar\ell$，RSI=0。RSI(14) 需要 15 个同一 lane 的连续 eligible close：15m 至少 3.75h，4H 至少 60h；不得拼接离散 G1 collection、跨 gap 或混合 kind。每个 input 必须有 `bar_open_at/bar_close_at/closed_at/available_at/source+schema+payload_hash/quality`，且 `available_at >= bar_close_at`，并满足：

\[
\max_e a_{lane}(e)\le decision\_at.
\]

令 $eligible\_kind(b,lane)$ 为 role-aware admissibility：`ACTUAL_ONLY` 只接受 `kind=ACTUAL`；`RECONSTRUCTED_CAUSAL_DEVELOPMENT` 只接受满足 §2.3 已冻结 ordering/parser/as-of release/eligibility 的 `kind=RECONSTRUCTED`。同一 RSI、boolean 与 join 只能使用一个 lane，不能混 kind。给定 evaluation time $t$ 与决策时刻 $\tau$，最近可用 4H bar 不是“最新看到的 bar”，而是：

\[
\mathcal K_{4h}(t,\tau,lane)=\{b:\ period(b)=4h,\ bar\_close\_at(b)\le t,\ a_{lane}(b)\le\tau,\ quality(b)=valid,\ eligible\_kind(b,lane)\},
\quad
\kappa(t,\tau,lane)=\arg\min_{b\in\{b'\in\mathcal K_{4h}(t,\tau,lane):bar\_close\_at(b')=\max_{c\in\mathcal K_{4h}(t,\tau,lane)}bar\_close\_at(c)\}}stable\_bar\_id(b).
\]

`C1` 的冻结静态基线为 $Q^{L,15m}=1[RSI_{15m}\le30]$、$Q^{S,15m}=1[RSI_{15m}\ge70]$，前提是其 15m bar `eligible_kind(\cdot,lane)`；`C2` 只是在同一 lane、同一方向上要求 15m 和 $\kappa(t,\tau,lane)$ 的闭合 4H RSI 都分别满足 $\le30$（long）或 $\ge70$（short）。它们是独立 event process：

\[
B_{C1,t}^s=Q_t^{s,15m},\qquad B_{C2,t}^s=Q_t^{s,15m}\land Q_{\kappa(t,\tau,lane)}^{s,4h},\qquad
E_{c,t}^s=(B_{c,t_c^-}^s=false)\land(B_{c,t}^s=true),\ c\in\{C1,C2\}.
\]

30/70 是唯一 baseline；任何 adaptive threshold 必须是另一个 policy version，不能替换或重述 C1/C2。每个 $c$ 独立维护其 lane-aware 15m grid、$t_c^-$、`UNKNOWN`/rearm 与 event ledger；bar 缺失、过期或质量失败使对应 $B_c$ 为 `UNKNOWN`。`RECONSTRUCTED` 导致 `UNKNOWN` 仅适用于 live/`ACTUAL_ONLY`，历史 lane 可按自身 predicate 计算但不能作生产、延迟或 queue 结论。gap/UNKNOWN 后，每个 $c$ 都必须先观察到自身合格 false 才能 rearm；false→true 仅创建其 control 的 `WATCH`。同 episode 的重复极值不得重置 anchor、zone 或 cooldown。

mark close 仅是指标输入；entry、TP、SL、PnL 与成本必须由实际可执行 bid/ask、延迟、深度、fee、funding 与 tail 计算。long/short 的 RSI 阈值、window、staleness、regime、DRL、barrier、calibration 均为独立必填参数，不假定镜像或共享。

观察链独立于执行状态：`IDLE → WATCH → CONFIRMING → ENTRY_CONTRACT_FROZEN | ABSTAIN | EXPIRED`；只有 `ENTRY_CONTRACT_FROZEN` 才可进入下节的 execution state。`WATCH`、`CONFIRMING` 不是持仓、成交或保护状态。

### 15.2 Confirm、可管理 EntryZone 与初始风险

方向 $s\in\{+1,-1\}$。v0.2 只能使用既有 $D/R/L$ 定义：`DRL \equiv (D_t^s,R_t^{post-pressure,s},L_t)` 只是三项的组合 ID，不产生新因子、score 或权重。每个方向的确认必须完整写成：

\[
Confirm_s=RESPONDING_s\land K_s\land D_s\land R^{post-pressure}_s\land L_s\land quality_s.
\]

每一项的 window、staleness、availability、missing/UNKNOWN 动作和方向参数都是 research contract 必填项。下列通用 entry 规则对每个 control $c$ 按 §15.4 的 `anchor_at(c)` 与 `action_at(c)` 应用。令冻结 anchor envelope 为 $[A_\ell,A_u]$、tick 为 $\delta_p$，则 action 前可提交的有限 tick domain 为 $P_\tau=\{k\delta_p\mid \lceil A_\ell/\delta_p\rceil\le k\le\lfloor A_u/\delta_p\rfloor,\ k\in\mathbb Z\}$；以下每个输入都必须属于 $\mathcal I^{lane}_{\le\tau}$：

\[
\begin{aligned}
Z_{anchor}^{(c)}&=P_\tau;\\
Z_{regime}^{(c)}&=\begin{cases}P_\tau,&c\in\{C1,C2\}\\P_\tau,&c\in\{C3,C4,Cmu\}\land K_s\text{ gate pass}\\\varnothing,&c\in\{C3,C4,Cmu\}\land K_s\text{ gate fail}\\Z_{regime}^{(C4)},&c=C5\\\varnothing,&c=C0\end{cases};\\
Z_{liq}^{(c)}&=\{p\in P_\tau:\text{fresh marketable-limit IOC、spread/slippage/capacity/TTL 均通过}\};\\
Z_{geom}^{(c)}&=\{p\in P_\tau:S_0(p),T_0(p),q(p),R_{min},R_{cap}\text{ 均为有效冻结值}\};\\
Z_{EV}^{(c)}&=\{p\in P_\tau:LCB(EV_{submit}(p,q(p)))\ge\epsilon_{EV}>0\};\\
Z_{entry}^{(c)}&=Z_{anchor}^{(c)}\cap Z_{regime}^{(c)}\cap Z_{liq}^{(c)}\cap Z_{geom}^{(c)}\cap Z_{EV}^{(c)}.
\end{aligned}
\]

`Z_regime^{(c)}` 是 full/empty control gate toggle，绝不为 regime 伪造价格坐标。C1/C2 构造 EntryZone 时不得读取 $K$；该 toggle 不改变其余四个集合、风险或执行语义。C5 完全继承 C4 的 entry/fill cohort，C0 不产生 action。`action_at(c)` 前，control 只可在冻结 $P_\tau$ 内按预注册格更新由 as-of quote/cost 决定的 $Z_{liq}^{(c)}$ 与 $Z_{EV}^{(c)}$；anchor 和 geometry parameters 不得重画。action gate 通过且 $Z_{entry}^{(c)}$ 非空后，上述集合与输入全部冻结。若 gate false、$Z_{entry}^{(c)}=\varnothing$ 或 TTL 过期，则该 control `ABSTAIN`，不得追价或重画。候选 $p$ 只可来自该 control 的集合，令 $\iota(p)$ 为冻结 canonical tick index，并定义 $WorstRisk^{(c)}(p)=q(p)r_{unit}(p)+R_{pending}$：

\[
p_c^*=\arg\min_{p\in Z_{entry}^{(c)}}^{lex}\big(-LCB(EV_{submit}(p,q(p))),\ WorstRisk^{(c)}(p),\ s\cdot p,\ \iota(p)\big).
\]

该顺序使 long 选更低价、short 选更高价；后续 $p^*$ 均指当前 control 的 $p_c^*$。不得用事后 fill、价格路径或未冻结盘口解释候选。

固定符号为：$p$ 是候选 IOC limit，$P_e$ 是实际授权 fill VWAP，$I_0$ 是结构失效点，$G_0$ 是结构目标。令 $x_u^s$ 为 exit-side executable price（long 用 bid，short 用 ask），在 control $c$ 的 $[anchor\_at(c),action\_at(c)]\cap\mathcal I^{lane}_{\le\tau}$ 路径中：

\[
u^*=\arg\min_u^{lex}\big(sx_u^s,\ a_{lane}(u),\ capture\_seq_u,\ event\_id_u\big),\qquad
I_0=x_{u^*}^s,\qquad S_0=round_{out}(I_0-sb_0),
\]

其中同价取最早 $a_{lane}$、再最小 `(capture_seq,event_id)`。rounding 固定为：`round_out` long floor/short ceil；`round_toward_entry` long floor/short ceil；`round_protective` long ceil/short floor。$G_0=G_0(p)$ 必须从 entry 前已可用的有限结构价集中选取，且 $s(G_0(p)-p)>0$，按最小 favorable distance、再 priority、$a_{lane}$、stable ID 决定；无结构或结构失效均删除该 $p$。令 $d_S=s(p-S_0)>0$：

\[
d_T=\min\{s(G_0-p),R_{cap}d_S\},\qquad
T_0=round_{toward\ entry}(p+s d_T),\qquad
R_{min}\le\frac{s(T_0-p)}{d_S}\le R_{cap}.
\]

每次 round 后都必须重新验证 geometry；不满足 bounds 则删除该 $p$。令

\[
r_{unit}(p)=\max\{0,s(p-S_0)\}+c_{entry}^{worst}(p)+c_{exit}^{worst}(S_0)+tail_{unit},\quad
B_\tau=R_{episode}^{max}-L_{realized}^{-}-R_{pending},
\]

\[
q(p)=floor_{lot}\!\left(\min\left\{\frac{B_\tau}{r_{unit}(p)},Q_{liq}(p),\frac{M_{available}}{p\cdot IMR+c_{entry}^{worst}(p)},Q_{venue}(p)\right\}\right).
\]

`Q_liq` 必须由冻结 freshness/depth/slippage/capacity 得到，`M_available/IMR`、`Q_venue`、lot、最小/最大 quantity 与 minimum notional 均须取自冻结 venue/instrument snapshot。$B_\tau\le0$、$r_{unit}\le0$、$q\le0$、不满足 lot/venue/notional/margin 任一项，均删除 $p$。RSI 不得进入 sizing。$S_0/T_0/H_0$ 在提交前由 $p^*$ contract 固定；首 fill 后成为权威，不因 $P_e$ 放宽。若 $P_e$ 在 zone 外或 $s(P_e-p)>0$ 超过授权 limit，必须先保护后退出。`EV_submit` 必须显式拆分 `NO_FILL`，未确认、拒绝、超时或取消不产生持仓路径。

既有 `Protocol v2`（与本节 `RSI-MTF-DRL-PM v0.2` 不同）仍固定为 `PROBE_ONLY`、20 bps target、12 bps stop、300 秒 horizon；不得被本节重跑或改写。本节只为新的 v0.2 research contract 设计动态 entry/exit、label 与 simulator。

### 15.3 Fill、保护、管理优先级与不可变账本

状态机为：

```text
FLAT → ENTRY_PENDING → PARTIALLY_FILLED_PROTECTION_PENDING
→ OPEN_PROTECTED/PRE_LOCK → PROFIT_LOCKED → EXIT_PENDING → CLOSED
                         ↘ HALTED_RECONCILE
```

`q_auth` 是首个 authoritative nonzero fill event 中的 cumulative quantity；$S_0/T_0/H_0$ 在提交前已由 $p^*$ contract 算好，并在该 fill 后生效，$P_e$ 则冻结为实际授权 fill VWAP。随后立即请求 cancel remainder；cancel ACK 前 remainder 仍计入 $R_{pending}$。其后 quantity 只能减少，禁止 ADD 和平均成本；late fill 必须先保护、以 reduce-only 回到不超过 $q_auth$，再 reconcile。`PARTIALLY_FILLED_PROTECTION_PENDING`（或全量 fill 的 `PROTECTION_PENDING`）只允许至多 $\Delta_{unprotected}^{max}$ 且 `NO_NEW_RISK`，此短暂状态允许 protection invariant 尚未成立。序列必须为 first fill → cancel remainder → stop-protect request → 有效 stop price/qty/order ID/reduce-only ACK → `OPEN_PROTECTED/PRE_LOCK`；target ACK 不是 stop coverage 的前置条件。只有该 stop ACK 后才必须满足 $effectiveProtectedQty\ge|reconciledExchangePositionQty|$。保护 timeout/reject/unknown/不足或对账不一致必须 emergency reduce-only exit 并 `HALTED_RECONCILE`；新 barrier ACK 前旧 barrier 始终权威。

令 $J_t=Pivot_\Theta(\mathcal I^{lane}_{\le\tau})$。每个 contract 必须将 `Pivot_\Theta` 序列化为唯一函数，固定 window endpoints、exit-side field、eligible predicate、极值方向、tie-break、buffer/rounding、staleness 与 missing action；不得写“baseline 可定义”。缺任一项时 `Pivot=UNKNOWN`，本次管理只能 `NO_CHANGE`，或按已冻结健康规则 `EXIT/HALT`，禁止改用另一 pivot。$b_t$、pivot window、eligibility、buffer 与 rounding 都是冻结函数，不能在线调参。令：

\[
S_{struct,t}=round_{out}(J_t-sb_t),\qquad
S_{BE,t}=round_{protective}\!\left(P_e+s\frac{C_{incurred}+C_{exit}^{worst}+Tail}{q_t}\right),
\]

令有限候选集 $S_{cand,t}=\{S_{ack,t-1},S_{struct,t}\}\cup\{S_{BE,t}:quality\ valid\land data/ack\ healthy\land S_{BE,t}\text{ 在冻结 buffer 后不穿越当前 executable exit price}\}$。若 $S_{struct,t}$ 或合格 $S_{BE,t}$ 已穿越当前 executable exit price，必须直接 reduce-only `EXIT`，不得提交越价 stop；$S_{BE,t}$ 不得无条件进入候选集。否则以 signed $Y=sP$ 取 $Y_{stop,t}=\max\{sS:S\in S_{cand,t}\}$。只有新的 stop price/qty/orderID/reduce-only ACK 后才切换 $S_{ack,t}$，故 $s(S_{ack,t}-S_{ack,t-1})\ge0$。每次 stop round/ACK 后必须重新验证 geometry 与 $LockedNet$。定义：

\[
LockedNet_t=PnL_{realized,episode}^{gross}+q_t\,s(S_{ack,t}-P_e)-C_{incurred,episode}-C_{exit}^{worst}(q_t)-Tail(q_t).
\]

其中 realized gross、已发生成本、未来 exit worst cost 与 tail 分量互斥且不得重复扣除。只有 stop 已 ACK 且 $LockedNet_t\ge0$ 才进入 `PROFIT_LOCKED`。episode 风险不得用盈利回收预算：

\[
R_{episode}=L_{realized}^{-}+\sum_j q_j\max\{0,s(P_{e,j}-S_{ack,j})\}+\sum_j(C_{exit\ stress,j}+Tail_j)+R_{pending}\le R_{episode}^{max},
\]

其中 $L_{realized}^{-}=\sum_j\max(0,-PnL_{realized,j}^{net})$。`PRE_LOCK` 只保持 $T_0$ 或提前退出，target 不得外移。令 $B_t^{target}=TargetBoundary_\Theta(\mathcal I^{lane}_{\le\tau})$，其中每个候选 $g$ 都有 `stable_id/quality/a_lane<=decision_at`；令已 ACK target 为 $T_{ack}$；`PROFIT_LOCKED` 的有限候选集为

\[
\mathcal G_t=\{g\in B_t^{target}:s(g-T_{ack})>0,\ 0<s(g-P_e)\le s(T_{cap}-P_e),\ LCB(EV_{hold}(g))>0,\ LCB(EV_{hold}(g)-EV_{exit-now})\ge\epsilon_{hold}>0,\ quality/data/ack\ healthy\}.
\]

若 $\mathcal G_t\ne\varnothing$，唯一 target 为 $g^*=\arg\min_{g\in\mathcal G_t}^{lex}(-LCB(EV_{hold}(g)-EV_{exit-now}),s(g-T_{ack}),priority\_rank(g),stable\_id(g))$；即最高 LCB、最小 extension、最小 priority rank、lex 最小 ID。若 $g^*$ 或 $T_0$ 在当前 executable exit price 上穿越，则直接 reduce-only `EXIT`；target 只有在 price/qty/orderID 有效 ACK 后才切换为 $T_{ack}$，此前旧 target 权威。每次 target round/ACK 后都重新验证 geometry 与 $LockedNet$；无候选为 `NO_CHANGE`。$H_t=H_0$ 直到提前退出，不能重设或延长。

管理评估只能由事件即时、UTC 对齐 1s 的首个 lane-eligible snapshot、barrier/structure/horizon/deadline 触发；live 仍是 `ACTUAL_ONLY`。优先级唯一为 `KILL/ACCOUNT_MISMATCH → STOP_HIT → PROTECTION_REPAIR → STRUCTURE_EXIT → TARGET_HIT → TIMEOUT → BARRIER_UPDATE → NO_CHANGE`；同 timestamp/OHLC 不可判定时 `STOP_FIRST`。动态 label 是 entry 前冻结 $\Pi_{exit}$ 对 as-of 路径的 `firstHit`；`operational_override`、`NO_FILL`、`PARTIAL_FILL` 与市场路径 label 必须分离。

immutable `management_ledger` 必填：event/parent/episode/opportunity ID、theory+contract+policy+code digest、side、state before/after、decision/available/evaluated time、全部输入摘要、anchor/zone、$p/P_e/I_0/G_0/S/T/H$ 旧新值、$q_auth$/position/protection/pending risk、request/ack/fill/cancel/reduce-only order IDs、fee/funding、barrier authority、reconcile snapshot/hash、reason/priority、`NO_CHANGE`、操作者身份、链前哈希和写入时间。所有公式的 input fields、window、rounding、missing action 与 tie-break 都是 contract fields。

### 15.4 Master opportunity ledger、controls 与命题

master opportunity ledger $U$ 是 gate-neutral 的 outcome-free universe：在 RSI、4H、regime、$D/R/L$、exit 与任何 outcome 之前，由所有质量合格、lane-aware closed 15m evaluation grids（$a_{lane}\le decision\_at$）按冻结 candidate-neutral cooldown/de-dup 生成 `opportunity_id` 与 anchor。任何待测 gate 都不得筛选、创建或删除 $U$。$U$ 共享 availability/quality、common execution/geometry/EV/risk、成本与 simulator；每个 control 必须独立 action 或 `ABSTAIN`，不得把 actual fills 强行共享。

对每个 `E_C2` evaluation time，active C2 opportunity 从该时刻开始，并对每个 control $c$ 独立持续至 $opportunity\_expire\_at=E\_C2\_time+observation\_ttl$、该 control 的首个 action/`ABSTAIN`、episode terminal、cooldown start 四者的最早者。重叠的 `E_C2` 不创建第二机会，而是按 candidate-neutral de-dup 归入同一 `opportunity_id`；`observation_ttl` 和 terminal priority 都是 contract fields。control-specific lifecycle 意味着一个 control 的 action/`ABSTAIN` 或终止不得误杀其他 control 的生命周期。

`anchor_at(c)` 是 control $c$ 所关联 $U$ opportunity 的冻结 anchor time；`action_at(c)` 是下表的首次 lane-aware gate 与 common gates 同时通过时刻。若不存在该时刻则该 control `ABSTAIN`。所有 control 的 $I_0/G_0/P_\tau$ 路径均是 $[anchor_at(c),action_at(c)]$，而不是把 `WATCH→Confirm` 固定为唯一研究路径。

| Control | 唯一 research action gate | `anchor_at(c)` / `action_at(c)` 与限制 |
|---|---|---|
| `C0` | no-trade-only 风险参考 | 不产生 alpha action |
| `C1` | $E_{C1}$ + common quality/execution/geometry/EV/risk | $U$ anchor；首次满足时为 `CONTROL_ACTION`；不得使用 4H/regime/`RESPONDING`/$D/R/L$ |
| `C2` | $E_{C2}$ + common gates | $U$ anchor；首次满足时为 `CONTROL_ACTION`；不得使用 regime/`RESPONDING`/$D/R/L$ |
| `C3` | active C2 opportunity 内首次 $K$ gate pass + common gates | C2 的 $U$ anchor；不得使用 `RESPONDING`/$D/R/L$；为 `CONTROL_ACTION` |
| `C4` | active C2 opportunity 内首次 $K+RESPONDING+D/R/L$ Confirm + common gates | C2 的 $U$ anchor；独立 action/`ABSTAIN` |
| `Cmu` | $U$ opportunity 内首次 $K+RESPONDING+D/R/L$ + common gates | $U$ anchor；完全不读任何 RSI；独立 action/`ABSTAIN` |
| `C5` | exact C4 submission/fill，只换 frozen dynamic exit | 继承 C4 的 `anchor_at/action_at` 与 exact cohort |

`C1/C2/C3` 的 action 只能称为 `CONTROL_ACTION`，不构成 `ENTER_PROBE`、订单或交易权限。`C1/C2/C3/C4/Cmu` 使用同一 EntryZone construction/geometry、cost 与 fill simulator；只有被 H 命名的 gate 启用/禁用不同。仅 `C4/C5` 必须共享 actual entry submission 与 actual fill cohort。唯一映射为：`H-010=C2-C1`、`H-011=C3-C2`、`H-012=C4-C3`、`H-013=C5-C4`、`H-014=C4-Cmu`。H-008 已覆盖执行遥测，不得在本组重复。

### 15.5 Error attribution、chronology 与 research-contract 必填清单

闭环为 `theory version → preregister → DEVELOPMENT → error attribution → theory delta → CALIBRATION → freeze → one-time HOLDOUT`。一次只允许改一层：

| 失败类型 | 允许新版本唯一修改 | 同版本或 `SEEN` 窗口禁止 |
|---|---|---|
| data / availability | source、schema、quality、availability | 改策略层、补写/跨 gap 或重用已读窗口 |
| RSI | closed-bar、warmup、阈值/事件 | 同时改 regime/DRL/entry/风险 |
| regime | 4H regime 参数 | 与其他层联调或伪造价格坐标 |
| DRL | 既有 $D/R/L$ 确认及其 window/staleness | 新 factor/score/权重或改 RSI |
| entry | anchor/zone/submit/fill policy | 同时改 exit/cost/risk |
| exit | $\Pi_{exit}$、barrier、label/horizon | 用回测结果改风险/成本 |
| cost | fee/slippage/funding/worst-cost 模型 | 同时改 entry/exit 或降低 tail |
| tail | risk envelope、$b_0$、$\Delta_{unprotected}^{max}$、保护 | 用结果收紧/放松以救回同一版本 |
| coverage | cohort、数据质量、样本/状态门 | 放宽门槛、合并 delta 或重用 `SEEN` |

DEVELOPMENT/CALIBRATION/HOLDOUT 任何 outcome 一经读取即为 `SEEN`。校准发现结构问题也使该窗口 `SEEN`；独立 holdout fail 必须退役版本并建立新 chronology，绝不能跨层联调、合并 delta、以回测改风险/成本或重用任何 `SEEN` 窗口。理论 Sol `PASS` 后才允许冻结 contract/chronology；之后才可 Terra 实现 synthetic primitives；之后才可 DEVELOPMENT backtest；然后 error attribution→delta→calibration→freeze→one-shot holdout。当前不授权其中任何一步。

任何 v0.2 research contract 必须显式列出：理论/协议/代码摘要；lane clock $a_{lane}$、role-aware admissibility、方向独立的 RSI/4H/DRL/regime windows、thresholds、staleness、UNKNOWN/rearm、C1/C2 独立 event ledger 与 $\kappa(t,\tau,lane)/t_c^-$ 算法；ACTUAL warmup/availability/gap 规则及可能的 `RECONSTRUCTED_CAUSAL_DEVELOPMENT` lane（逐 event 的冻结纯函数、ordering/parser/as-of release/eligibility/reconstructed fields/limitations）；gate-neutral $U$-before-gates 生成规则、C2 opportunity 的 TTL/de-dup/terminal priority、control-specific lifecycle 与 gate/anchor/action table、各 control action/ABSTAIN、H-ID 与 C4/C5 exact fill cohort；control-indexed $Z_{regime}^{(c)}$ 与 C1/C2 不读 $K$ 的无泄漏约束、$P_\tau$、tick、其余 EntryZone 集合、TTL、$p_c^*$ key；$x_u^s/I_0/G_0/b_0/R_{min}/R_{cap}/S_0/T_0/H_0/T_{cap}$ 的 source/window/rounding/missing/tie-break；唯一序列化 `Pivot_\Theta` 的 window/field/predicate/extreme/tie-break/buffer/rounding/staleness/missing action；$r_unit/B_\tau/Q_{liq}/IMR/Q_{venue}$、budget/cost/tail/lot/notional；fill/cancel/late-fill/$\Delta_{unprotected}^{max}$/protection ACK/reconcile/deadline；$J_t/S_{struct}/S_{BE}$ eligibility/current-price crossing action、exclusive cost accounting、LockedNet/$\Pi_{exit}$、$B_t^{target}$/target rounding/price-qty-orderID ACK、priority、label 与 `STOP_FIRST`；ledger schema；DEVELOPMENT/CALIBRATION/HOLDOUT chronology、one-shot receipt、失败动作和 acceptance metrics。任何 `TBD`、隐含代码默认、未版本化来源或无法摘要的字段都禁止实现。

A3 只是一条数据完整性/censor 上游门，不是 RSI/DRL 策略理论，也不支持 H、E1–E5 或任何证据升级；历史实验必须另获 role/protocol 授权。January 的 3 gaps/1 FIT row、February A2F1 `SEEN/NOT_SCORED`、March 未读未授权和活动 G1 均保持隔离。当前仍为 E0。

---

## 16. 通用多视角竞争机制—动态路径方法论

本章是高于单一 RSI、固定 K 线形态和单一市场叙事的“未读取新 outcome”上位方法。它只冻结如何组织观测、竞争解释、动态路径、预测与动作，不声称任何机制在现实中为真，也不授权读取新数据、回测或交易。随包保存的已见用户叙事仅用于诊断展示；正式规则不得依据该叙事的已知结果调参。

### 16.1 六类概念必须严格分离

1. **数据层（Data Layer）**：带点时可得性、质量、来源和版本的原始或确定性派生事实，例如 OHLCV、成交、深度、OI、funding、强平下界、事件发布与账户遥测。
2. **状态轴（State Axis）**：对不同维度的有界描述，例如方向、波动、流动性、杠杆、拥挤、强制去杠杆、事件风险和数据质量。状态轴可以同时成立，不是相互排他的机制。
3. **分析视角（Analytical Perspective）**：价格行为、订单流、流动性、杠杆、事件、跨场和执行等观察坐标。视角只组织证据，不能自称独立事实或重复贡献同一底层增量。
4. **机制假设（Mechanism Hypothesis）**：对“为什么出现该观测”的有限竞争解释。它是可被支持、软反证、硬反证和到期的研究对象，不是参与者意图真值。
5. **路径（Path）**：机制在可变长度、部分有序 milestone 上的可观察演化候选。路径可跳过或重复预声明 milestone，不等于固定天数模板。
6. **动作（Action）**：预测、保守效用、权限、成本、风险和执行约束共同映射的结果。anchor、事件、状态、机制、路径、形态或 RSI 均不直接等于信号或订单。

因此合法链条扩展为：

```text
ObservationFrame
→ MultiScaleStateBelief
→ finite MechanismSpec competition
→ exact PathEvent lifecycle
→ variable-length PathBeliefSet
→ ScenarioDistribution
→ canonical UtilityReceipt
→ ActionCandidate
→ PermissionEnvelope
→ immutable UpdateReceipt
```

任何 anchor 或 event 只创建评估上下文；它不自动创建 opportunity、方向、EntryZone 或交易许可。

### 16.2 十一个核心对象与 PatternInstance

| 对象 | 唯一职责 | 硬边界 |
|---|---|---|
| `ObservationFrame` | 冻结 decision time 下可见的数据层、质量、缺失、dependency group 与 provenance | 不含未来字段，不把缺失补零 |
| `MultiScaleStateBelief` | 按有序 role profile 保存各状态轴及不确定性 | 周期不是投票；低周期不得覆盖高周期职责 |
| `MechanismSpec` | 冻结机制 ID、必要/可选证据、支持、软反证、hard falsifier、expiry 与路径族 | runtime/LLM 不得新增机制 |
| `PathSpec` | 冻结一个有限 compound path template 的非空去重 `primitive_mechanism_ids`、milestone vocabulary、partial order、skip/repeat、variable horizon、expiry 与 merge 等价类 | 不允许 outcome 后创造路径、runtime power set 或 Cartesian product |
| `PathEvent` | 以 exact-key carrier 保存 path event ID、path instance、milestone、`event_at`、`available_at`、terminal reason/trigger 与 source version | 只接受 aware timestamp；未来可得、schema 漂移、终止后事件或未注册 hard falsifier 一律拒绝 |
| `PathBeliefSet` | 分开保存非归一 primitive support，以及仅在合法 competition set 内存在的 compound path weights、top path、margin、entropy/UNKNOWN 与 residual path | primitive support 不是 mixture weight；无互斥/完备证明不得归一 |
| `ScenarioDistribution` | exact-key 相互排他的未来情景 carrier | V5-M00 数值只允许 synthetic counterfactual；E0 qualitative 不含数值；raw map/伪 calibrated bool 无效 |
| `UtilityReceipt` | 以 canonical digest 绑定完整 scenario、逐情景 utility、stress cost、tail、uncertainty penalty、`as_of` 与 authority | raw scalar 或任一内容/摘要漂移无效；不得授权动作 |
| `ActionCandidate` | 验证并绑定 ScenarioDistribution、UtilityReceipt、PermissionEnvelope 的 ID/digest，再保存研究几何与理由 | V5-M00 新风险动作恒为 `ABSTAIN`；几何可行性不等于权限 |
| `PermissionEnvelope` | 冻结允许动作、风险上界、否决与 authority version | `DENY/UNKNOWN` 阻止新增风险 |
| `UpdateReceipt` | 记录前后 belief、唯一证据增量、dependency group、版本和链式摘要 | 禁止静默重算或前缀回写 |
| `PatternInstance` | 保存某段叙事或已观察序列如何映射到候选机制，供案例解构与错误归因 | 必须显式标注来源、事实状态和 outcome visibility；不定义 opportunity universe |

`PatternInstance` 是诊断对象，不是新的 truth label。其 `candidate_mechanism_ids` 必须非空、唯一并只能引用冻结机制库；相同观测可以同时支持多个机制，相同机制也可在独立 `PathSpec` 下产生多条路径。

### 16.2.1 分析视角矩阵与标准输出卡

| 分析视角 | 可观察输入 | 能支持的状态/机制 | 关键区分证据 | 禁止越权推断 |
|---|---|---|---|---|
| 价格结构 | 点时 OHLC、pivot、区间、突破/补回 | 方向、结构、range、continuation/reversal 候选 | 冻结确认窗内是否保持、是否出现反向结构失效 | 仅凭形态断言参与者意图或直接下单 |
| 成交/订单流 | 成交方向代理、成交量、冲击响应 | 压力、拥挤、continuation/absorption 候选 | 同等流量下边际价格冲击、跨来源一致性 | 把 volume spike、wick 或 aggressor proxy 当作真实身份 |
| 流动性 | spread、深度、补单/撤离代理、滑点 | 流动性状态、vacuum/absorption/artifact 候选 | 深度恢复、独立 venue 复现、压力与韧性是否同窗 | 无完整订单簿时强拆撤单意图或真实吸收 |
| 衍生品/杠杆 | OI、funding、basis、强平下界代理 | 杠杆、拥挤、去杠杆压力 | OI/funding/basis 与价格、流动性同步及点时可得性 | 将代理值当真实仓位、账户身份或完整强平量 |
| 波动 | realized/可得 implied proxy、range、jump | 波动状态、stress/transition 候选 | 波动变化是否先于/伴随结构和流动性变化 | 由高波动直接推出方向或交易许可 |
| 事件/宏观 | 发布时间、vintage、事件类别、surprise proxy | 事件风险、event-repricing 候选 | 发布先后、revision 隔离、matched comparator 与跨层响应 | 用标题情绪直接推出方向 alpha |
| 跨场 | 跨 venue/现货-衍生品价格、basis、深度、时钟 | 局部异常、传导、artifact 候选 | lead-lag 是否在同步时钟与独立源上复现 | 将相关性写成确定因果或跨市场权限 |
| 数据质量 | freshness、gap、schema/version、时钟、conflict | 数据质量轴、artifact/UNKNOWN | 独立重建、版本审计、冲突定位与恢复 | 把 missing 补零、把 feed silence 当无事件 |

一次评估必须按同一 decision-time 输出：

```text
可见事实与缺失
→ 多尺度状态及 UNKNOWN
→ 有限候选机制与 OTHER
→ 各候选分支路径和当前前缀
→ 下一可观测支持 / soft contradiction / hard falsifier / expiry
→ UNKNOWN 或定性/校准选择
→ PermissionEnvelope、EntryZone、效用、风险和动作约束
→ immutable UpdateReceipt
```

输出卡不得跳过中间层，也不得把“下一证据”写成已经发生的事实。

### 16.3 有限机制库、OTHER 与最小竞争族

每个 contract 必须事前冻结有限机制库，并始终包含 `OTHER`。最小族为：

- `CONTINUATION`：原方向信息或压力继续主导；
- `ABSORPTION_REVERSAL`：压力被持续吸收，边际冲击下降并出现反向响应；
- `RANGE`：双向供需在区间内均未形成持续响应；
- `LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM`：强制去杠杆、流动性撤离或两者不可识别的联合候选；
- `EVENT_REPRICING`：点时可得事件改变条件分布；
- `ARTIFACT`：数据缺口、venue 局部异常、schema/时钟错误或测量伪影；
- `OTHER`：有限库未覆盖、证据全弱或解释仍未知。

这些机制是可共存的 primitive、多标签解释，不是互斥终态。例如 `EVENT_REPRICING → LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM → CONTINUATION` 可以在同一 episode 同时获得支持；新增一项支持不得机械压低另外两项。primitive support 不归一、不求和为 1，也不是现实机制、参与者身份或因果真值。`ARTIFACT` 是 epistemic/data-quality alternative，只参与质量否决与 UNKNOWN 路由；任何可进入 normalized path mixture 的路径（包括 residual path）只要含 `ARTIFACT` 就必须 fail closed，防止它直接或间接带权进入动作效用。没有独立识别设计时，`LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM` 不得强拆成确定性强平或撤单叙事。

每个机制必须事前分配至少一个 path signature：

| 机制 | Antecedent | 下一步可观测支持 | 软反证 | Hard falsifier | Expiry/terminal | 禁止解释 |
|---|---|---|---|---|---|---|
| `CONTINUATION` | 有方向的价格/流量响应仍有效 | 同向冲击与结构突破保持、反向吸收不足 | 动量减弱或局部回补 | 冻结反向结构失效成立 | horizon 到期或目标/失效 terminal | “主力继续拉/砸” |
| `ABSORPTION_REVERSAL` | 压力持续但边际冲击下降 | 可见韧性补回、反向响应并通过结构确认 | 仅出现 wick、补回不持续 | 压力重新产生同向扩展或吸收区失效 | response window 到期/结构终态 | “机构吸筹/出货” |
| `RANGE` | 双向响应受限且区间边界有效 | 多次边界响应、中心回归 | 单侧压力逐渐占优 | 有效突破并在冻结确认窗保持 | range expiry/突破 terminal | “控盘震荡” |
| `LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM` | 急剧价格位移与流动性/强平代理异常 | 强平下界、深度撤离、spread/冲击异常继续 | 流动性快速恢复且无去杠杆代理 | 完整数据证明异常来自 artifact 或未发生声明条件 | stress window 到期/流动性恢复 | 将联合候选强拆为真实强平或撤单意图 |
| `EVENT_REPRICING` | 点时可见事件与市场状态变更同窗 | 发布后跨数据层响应持续 | 反应短暂或与 event comparator 相同 | event 时间不可证明、revision 泄漏或响应先于发布 | event window 到期/新 vintage | “利好/利空必然导致方向” |
| `ARTIFACT` | gap、schema/clock/venue 冲突或异常集中于单 feed | 独立源不复现、重建/版本审计失败 | 多源同步且质量持续有效 | 独立完整数据一致复现并排除声明 artifact | 数据修复/隔离 terminal | 将坏数据解释成市场意图 |
| `OTHER` | 已注册机制均不足或库外解释 | 持续无法由已注册 signature 区分 | 某一注册机制获得独立强支持 | 只在 predeclared coverage rule 下被已注册机制排除 | coverage/expiry terminal | 临时由 LLM 命名新故事 |

`volume spike + wick` 必须同时映射 `CONTINUATION / ABSORPTION_REVERSAL / LIQUIDATION_CASCADE_OR_LIQUIDITY_VACUUM / ARTIFACT / OTHER`，等待下一步可观测支持；它本身不完成任何 signature。

### 16.4 动态路径：可变 horizon、partial order、跳过与重复

`PathSpec` 不以 D1…D8 或任何固定长度定义。每条路径冻结非空、去重、只引用注册库的 `primitive_mechanism_ids`，以及 milestone vocabulary、必要边、可选边、可重复节点、可跳过节点、`stopping_policy_id`、`frozen_horizon_seconds`、exact `PathEvent` schema、hard falsifier 和 expiry。观察序列可以是 2、8、20 或其他长度；只要满足 partial order，milestone 可以跳过，预声明的压力、吸收或测试节点可以重复。实现可设置独立的内存/计算 capacity guard，但该 guard 不是市场路径长度、终态或理论 horizon。

`PathEvent` 必须 exact-key 保存 `path_event_id / path_instance_id / milestone / event_at / available_at / terminal_reason / terminal_trigger_id / source_version`。所有时间戳必须 aware，并满足 `path_started_at <= event_at <= available_at <= decision_time`；同一路径的 `event_at` 严格递增。最后且唯一的 terminal event 只能取 `TERMINAL_MILESTONE`、引用 `PathSpec.hard_falsifiers` 的 `HARD_FALSIFIER`，或精确发生于 `path_started_at + requested_horizon_seconds` 的 `EXPIRY`。三者中最早发生者立即停止路径，之后任何事件都无效。`requested_horizon_seconds` 不得超过冻结 horizon；`NEVER_STOP`、`FIXED_8_DAY`、expiry 后继续或 horizon extension 全部 fail closed。

compound path 只允许有限、事前注册的 template；禁止枚举 primitive power set、runtime Cartesian product 或由 LLM 注入新组合。event、liquidity 和 data-quality 多数应保存为 path qualifier/multi-hot 属性，而不是为每个组合复制路径。canonical 去重键至少绑定 `path_template_id + sorted primitive_mechanism_ids + scope`。当前对象模型的 residual 精确为 `OTHER_PATH` 且 `primitive_mechanism_ids=["OTHER"]`；`OTHER` 不得出现在 market path，`ARTIFACT` 不得混入任何 mixture-eligible market/residual path，也不得以 residual 名义绕过 utility 边界。

路径只在已观察前缀上更新。后到事件产生新的 `UpdateReceipt`，不能回写旧前缀。两条路径只有在 outcome 前冻结的 `merge_equivalence_class` 相同且 merge rule 成立时才可合并；相似自然语言名称不是等价证明。

每条路径的证据处置只有：

- `SUPPORT`：增加相对支持；
- `SOFT_CONTRADICTION`：降低支持但不立即淘汰；
- `HARD_FALSIFIER`：立即把当前 `path instance / opportunity episode` 标为 `FALSIFIED`，不得用该 episode 的后续弱证据救回或复写旧 receipt；
- `EXPIRY`：到时未达到冻结条件即 `EXPIRED/UNKNOWN`，不得延长 horizon。

路径切换只改变 belief。已有仓位不得因为 top path 改变而自动反手；只能由冻结的持仓管理规则 `KEEP/TIGHTEN/REDUCE/EXIT` 处理。

hard falsifier 不会永久删除有限机制库中的机制。新的、独立 opportunity 只有在新的 `ObservationFrame` 下才可重新实例化同一机制；它必须使用新 path instance、episode ID 和 receipt chain，旧 episode 仍永久保持 `FALSIFIED`。

### 16.5 E0 定性 ledger、未来校准模式与去重更新

E0 只允许定性、未读取新 outcome 的 evidence ledger。每条证据必须 exact-key 记录 `evidence_id / available_at / perspective_id / dependency_group / target_ids / direction / ordinal_strength / quality / source_version`；identity 必须非空，target 必须非空唯一，direction、strength 与 quality 只能取冻结 enum。`available_at` 和 `decision_time` 必须为 aware timestamp，且只有 `available_at <= decision_time` 的证据可增加或降低支持。missing、malformed、naive、未来时间、schema 漂移或非 `VALID` quality 一律记入 rejection/UNKNOWN，支持值保持不变；`UNAVAILABLE`、`STALE`、`GAP`、`CONFLICT` 或 `DATA_INVALID` 不能伪装成零。

对机制或路径 $m$，E0 更新为冻结的有界序数：

\[
q_m^{(t)}=\operatorname{clip}\left(q_m^{(t-1)}+\sum_g A_g\{s_{i,m}:dependency\_group_i=g\},-Q,Q\right),
\]

其中 $A_g$ 是事前冻结的组内聚合器；默认只保留绝对强度最大的一个增量并用 `evidence_id` 稳定 tie-break。来自同一底层增量的价格、成交、图形和语言解释必须共享 `dependency_group`，不得重复加权。每个 $q_m$ 独立更新；禁止对 primitive mechanism 做 softmax 或 simplex normalization。

只有未来另获授权、在独立 CALIBRATION 上冻结合法的 compound `PathHypothesis` competition set 后，才可使用：

\[
\alpha_h^{(t)}=
\frac{\alpha_h^{(t-1)}\exp(\Delta_h)}
{\sum_{j\in H_C}\alpha_j^{(t-1)}\exp(\Delta_j)}.
\]

这里 $H_C$ 不能接受任意自然语言 `exclusivity_basis`。每个 competition set 必须引用有限、冻结的 `partition_proof_id`，并与该 proof 的 `competition_set_id`、对有序 path registry 完整定义重算的 canonical `path_registry_digest`、canonical **full proof** `partition_proof_digest`、`partition_version`、精确有序 `path_hypothesis_ids`、同序且非空的 partition cells、`mutually_exclusive=true`、`exhaustive=true`、`residual_path_id=OTHER_PATH`、精确 `residual_domain_values=["OTHER_OR_UNRESOLVED_TERMINAL"]` 和非空 `calibration_version` 完全一致。full proof digest 对 proof 除自身 digest 字段外的全部 canonical JSON 内容取 SHA-256；另由 method authority 的有限 allowlist 精确绑定 `partition_proof_id + digest + path_registry_digest + eligible_path_hypothesis_ids + partition_domain_id + partition_domain_values + residual_path_id + residual_domain_values`。authority scope 必须至少含一条 market path 和 residual path，禁止 residual-only authority。path registry digest 覆盖每行精确 `path_hypothesis_id + primitive_mechanism_ids + role` 及数组顺序，不能只凭未变的 ID 复用旧 proof。合成验证只能证明“预注册的有限 domain values 被 cells 无重叠且无遗漏地分区”，不得声称已给出现实市场的数学证明。proof authority 未登记、proof 内容/域/cell/market assignment 漂移、path 定义、set/path/cell 顺序或版本漂移、cell 重叠/缺口、缺 residual、非穷尽、market path 含 `OTHER` 或任一路径含 `ARTIFACT`，都禁止 path normalization。primitive 可以在不同 compound hypothesis 中重复出现，其原始 support 不得直接用作 $\alpha_h$。

只有合法 competition set 才报告单一 `top_path_hypothesis_id`、top-two `margin` 与 entropy；否则报告并存的 `active_primitive_mechanism_ids` 和 `UNKNOWN_NO_VALID_COMPETITION_SET`。必要输入缺失、top tie、证据全弱、未覆盖 feed silence 或机制库解释不足时，输出 `OTHER/UNKNOWN`，而不是强行选择最像的故事。

### 16.6 情景、保守效用与动作几何

`ScenarioDistribution` 的纯价格终态 branches 精确为 `{UPSIDE,DOWNSIDE,RANGE,UNRESOLVED}`，相互排他且完备。`EVENT_REPRICING`、流动性异常等只可作为 mechanism/path qualifier，不能冒充价格终态。提交后的 `ActionOutcome` 另以 `{NO_FILL,TP_FIRST,SL_FIRST,STRUCTURE_EXIT,TIMEOUT}` 建模，不能与价格情景混合。V5-M00 只接受 exact-key `SYNTHETIC_COUNTERFACTUAL_ONLY` 数值载荷用于纯合成算术；数值必须有限、非布尔、位于 $[0,1]$ 且总和为 1。E0 `QUALITATIVE_E0` 只允许冻结序数标签且绝不包含数值；raw probability map、`calibrated=true` 伪字段、missing/future `as_of` 或未授权 `CALIBRATED_PROBABILITY` mode 都无效。

当前 P0 的纯合成算术只允许互斥完备的四分支 `ScenarioDistribution` 进入候选动作 $a$ 的保守效用：

\[
LCB_U(a)=
\sum_s \pi_sU(a,s)
-Cost_{stress}(a)-Tail(a)-Penalty_{uncertainty}(a).
\]

该结果必须写入 canonical `UtilityReceipt`，其 digest 绑定完整 ScenarioDistribution ID/digest、逐情景 utility、stress cost、tail、uncertainty penalty、`as_of`、authority version 和 conservative utility。raw scalar、内容篡改、摘要漂移或 authority 不匹配一律无效。未来只有合法 compound path competition set 存在时，才可另行授权 path-conditioned $\sum_h\alpha_h\sum_s\pi(s\mid h)U(a,s)$；primitive mechanism support、`ARTIFACT` support、任何含 `ARTIFACT` 的 market/residual path 或未通过预注册 partition proof 的 path 分数，都不得直接或间接充当 mixture weight。

`ActionCandidate` 必须 exact-key 验证并绑定 `ScenarioDistribution`、`UtilityReceipt`、`PermissionEnvelope` 的 ID/digest 及共同因果时钟。V5-M00 的 PermissionEnvelope authority 精确为 `V5-M00-E0-NO-NEW-RISK`，只允许 `DENY/UNKNOWN`、`allowed_actions=["ABSTAIN"]` 和 `max_risk=0`；因此即使三个 carrier 完整且研究几何成立，新风险动作仍恒为 `ABSTAIN`。invalid carrier 还必须返回精确的 `SCENARIO_DISTRIBUTION_INVALID / UTILITY_RECEIPT_INVALID / PERMISSION_ENVELOPE_INVALID`，不得保留对应 ID/digest。价格与风险几何仅作为独立 research candidate 计算：

\[
EntryZone=\bigcap_k Z_k,\quad
q=\min\left(
\frac{R_{budget}}
{|P_{entry}-SL|+Cost_{worst/unit}+Tail_{unit}},
Q_{liq},Q_{venue},Q_{margin}
\right).
\]

LONG 必须满足 $SL<EntryZone_{low}\le EntryZone_{high}<TP$；SHORT 方向相反。`horizon` 取被支持路径的冻结允许范围并不得延长。`size` 不可由机制确信度、RSI 强度、形态完整度或事件标题放大。

入场后动作集合严格为 `{KEEP,TIGHTEN,REDUCE,EXIT}`。stop 只能单向收紧，target/horizon 不得为挽救亏损而放宽；新方向需要新的 opportunity、EntryZone、风险预算和权限。

### 16.7 多周期 role profile、四层职责与 RSI

多周期必须使用 ordered role profile，而不是固定周期投票。每个 profile 冻结从高到低的角色、允许状态轴、最大 freshness 和信息流方向。当前 `1W/1D/4H/1H/15m` 只属于 BTC V1 profile：1W 风险背景、1D 结构背景、4H operational regime、1H setup、15m evaluation/trigger。它不是其他标的、其他市场或通用理论的默认周期。

RSI 是可选 trigger。RSI 缺失时，预定评估、状态变化、事件到达、质量变化和持仓风险评估仍须运行；缺失 RSI 只能影响声明依赖它的路径，不得让整个系统静默。

四层职责保持分离：

1. L1 当前压力与数据面：确认、否决、流动性和执行风险；
2. L2 多尺度状态面：结构、位置、波动与父子职责；
3. L3 历史相似面：past-only comparator/conditional challenger；
4. L4 事件面：点时风险、冲突与独立 timing hypothesis。

放量长影、RSI 极值或消息大阳只能是 observation。它们不能强制选择 continuation、absorption-reversal 或任何单路径；未覆盖 feed 静默必须为 `UNKNOWN`。

### 16.8 八日经验的正确位置

既有 v0.4 的 D1…D8/H10/H11 固定序列已被用户澄清明确拒绝，只保留为历史 E0 challenger。本章不迁移其固定天数、价格事实链、假设 ID 或 holdout 角色。用户经验只可登记为 `CASE-USER-EXPERIENCE-SHOCK-COMPRESSION-001`：`origin=USER_EXPERIENCE`、instrument/time=`UNSPECIFIED`、`truth_status=ANECDOTAL_UNVERIFIED`、`outcome_visibility=SEEN_NARRATIVE`、`not_for_holdout_selection=true`。它可以保存叙事中已知的后续结果以便解构，因此不能称 outcome-free；但不得提供 market support、prior、opportunity 筛选或 DEVELOPMENT/CALIBRATION/HOLDOUT 角色。它只可同时映射多个冻结候选机制；任何具体路径仍须由新的 ObservationFrame 与独立规则实例化。

### 16.9 历史验证、proper scoring 与 theory delta

未来若获得独立授权，验证必须使用按时间推进的 walk-forward split；每个预测时点只读此前可用、版本正确的数据。概率模型用 log score、Brier score 或其他事前冻结的 strictly proper scoring rule，并分别报告校准、分辨率、coverage、abstention 与成本后 utility；只比较命中率无效。

错误归因至少分为 `DATA/AVAILABILITY`、`STATE`、`MECHANISM_LIBRARY`、`PATH_SPEC`、`DEPENDENCE`、`CALIBRATION`、`ACTION_GEOMETRY`、`COST/EXECUTION` 和 `PERMISSION/RISK`。一次 theory delta 只修改一类，并生成新版本、新 chronology 和未见窗口。被打开的窗口永久 `SEEN`；不能用 error attribution 重新优化同一 holdout。

### 16.10 新增上位 Claims 与待证伪 Hypotheses

| ID | 类型 | 命题 | 当前状态/反证 |
|---|---|---|---|
| `T-026` | `[POLICY]` | 数据层、状态轴、视角、机制、路径和动作严格分离 | 任一实现把其中两层等同即失败 |
| `T-027` | `[POLICY]` | primitive 机制库有限、可共存且始终含 `OTHER`；support 不归一，runtime/LLM 不得扩库 | 未注册 ID、primitive simplex 或新增支持压低另一 primitive 即失败 |
| `T-028` | `[POLICY]` | 路径为 variable-length partial order，可跳过/重复预声明 milestone | 固定天数或 outcome 后改 milestone 即失败 |
| `T-029` | `[POLICY]` | 同一 dependency group 的增量不得重复计数 | 重复观测改变组聚合结果即失败 |
| `T-030` | `[POLICY]` | E0 qualitative 无数值；V5-M00 数值 Scenario 仅可为 exact synthetic counterfactual carrier，并与未来 market calibration 分离 | raw map、伪 calibrated bool、未来/缺失 `as_of` 或未授权 numeric market mode 即无效 |
| `T-031` | `[POLICY]` | top path、margin、entropy 只属于引用已登记 partition proof、精确绑定 path/cell/version、互斥完备、含纯 `OTHER_PATH` residual 且所有路径排除 `ARTIFACT` 的 compound competition set | 任意字符串 proof、集合漂移、ARTIFACT residual、无合法 set 却归一或强行单路径即失败 |
| `T-032` | `[RISK]` | V5-M00 仅允许四分支 synthetic counterfactual 生成 canonical UtilityReceipt；研究几何与权限分离，PermissionEnvelope 固定 deny/unknown、零风险，ActionCandidate 只能 `ABSTAIN` | 任一 carrier/schema/digest/时钟漂移须精确拒绝并解绑；任何新增风险或 primitive support 进入 utility 即失败 |
| `T-033` | `[RISK]` | 持仓后只可 `KEEP/TIGHTEN/REDUCE/EXIT`，path switch 不自动反手 | 自动 reverse/add 即失败 |
| `T-034` | `[POLICY]` | ordered role profile 是标的/市场专属；BTC 1W/1D/4H/1H/15m 不自动泛化 | 跨 profile 沿用即失败 |
| `T-035` | `[POLICY]` | RSI 与形态均为可选 observation/trigger，不是机制或动作 | RSI 缺失导致 scheduled/state-change/event-arrival/data-quality/position-risk 任一评估静默即失败 |
| `T-036` | `[POLICY]` | PatternInstance 不定义 opportunity universe 或 holdout | 案例筛选机会或样本即失败 |

| ID | 待证伪假设 | 必要 comparator | 失败条件 |
|---|---|---|---|
| `H-015` | 有限竞争机制相对单叙事可改善 calibrated scenario score | 相同信息集的 frozen single-path baseline | proper score 无增量或 coverage 明显恶化 |
| `H-016` | dependency-group 去重可减少过度确信 | 不去重但其余相同的 baseline | calibration/entropy 无改善 |
| `H-017` | variable-length partial-order path 比通用固定长度严格顺序模板更稳健 | `FIXED_LENGTH_STRICT_ORDER_TEMPLATE` | walk-forward 无增量或复杂度成本更高 |
| `H-018` | `OTHER/UNKNOWN` 可降低未覆盖状态的尾部错误 | forced-choice mechanism baseline | abstention opportunity cost 超过尾部改善 |
| `H-019` | absorption-reversal 与 continuation 的竞争证据优于 volume+wick 单路径 | 简单 volume+wick rule | 样本外 score/utility 无增量 |
| `H-020` | 通用事件 timing 可改善风险条件但不直接提供方向 alpha | 无事件 timing gate | 无风险改善、机会成本过大或产生方向泄漏 |
| `H-021` | RSI-absent 的 scheduled/state-change/event-arrival/data-quality/position-risk evaluation 减少静默盲区 | RSI-trigger-only evaluation | 无 coverage/风险增量 |
| `H-022` | 合法 compound competition set 的路径条件保守效用优于 top-path forced action | 相同互斥完备 set 的 top-path-only action policy | set 不合法、成本后 utility 或尾部风险不改善 |
| `H-023` | 机制/path/action 的分层 error attribution 能产生更小、更稳定的 theory delta | 跨层联合调参 baseline | 改版频率、过拟合或 holdout 失败未下降 |

---

## 17. 参考资料

以下资料优先采用交易所官方文档、监管机构、原始研究和数据供应商自身规范；访问与语义核验日期为 2026-07-22。

### 17.1 交易所与市场数据

- [Binance USDⓈ-M Futures Market Data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Binance Aggregate Trade Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Aggregate-Trade-Streams)
- [Binance Diff Book Depth Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Diff-Book-Depth-Streams)
- [Binance Liquidation Order Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Liquidation-Order-Streams)
- [Binance USDⓈ-M User Data Streams](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/user-data-streams/Connect)
- [Binance USDⓈ-M Account REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)
- [Binance USDⓈ-M Trade REST API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade)
- [Binance Official Announcements](https://www.binance.com/en/support/announcement)
- [Binance Spot WebSocket Streams](https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams)
- [Binance USDⓈ-M Futures Change Log](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/change-log)
- [Binance Public Data Archive](https://github.com/binance/binance-public-data)
- [Bybit Orderbook WebSocket](https://bybit-exchange.github.io/docs/v5/websocket/public/orderbook)
- [Bybit Public Trade WebSocket](https://bybit-exchange.github.io/docs/v5/websocket/public/trade)
- [Bybit All Liquidation WebSocket](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)
- [Bybit ADL Alert](https://bybit-exchange.github.io/docs/v5/websocket/public/adl-alert)
- [Bybit Insurance Pool](https://bybit-exchange.github.io/docs/v5/websocket/public/insurance-pool)
- [Bybit Ticker WebSocket](https://bybit-exchange.github.io/docs/v5/websocket/public/ticker)
- [Bybit Funding Rate History](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate)
- [Bybit Open Interest](https://bybit-exchange.github.io/docs/v5/market/open-interest)
- [Bybit Long Short Ratio](https://bybit-exchange.github.io/docs/v5/market/long-short-ratio)
- [Bybit Historical Market Data Downloads](https://www.bybit.com/en/derivative-activity/history-data)
- [Deribit Volatility Index Data](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data)
- [Deribit Instruments](https://docs.deribit.com/api-reference/market-data/public-get_instruments)
- [Deribit Book Summary by Currency](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency)
- [Deribit Order Book](https://docs.deribit.com/api-reference/market-data/public-get_order_book)
- [Deribit Last Trades by Currency](https://docs.deribit.com/api-reference/market-data/public-get_last_trades_by_currency)
- [Deribit Market Data Collection Best Practices](https://docs.deribit.com/articles/market-data-collection-best-practices)
- [OKX API Guide](https://www.okx.com/docs-v5/en/)
- [OKX API Change Log](https://www.okx.com/docs-v5/log_en/)
- [OKX Historical Market Data](https://www.okx.com/historical-data)
- [OKX Historical Market Data API](https://www.okx.com/docs-v5/en/#public-data-rest-api-get-historical-market-data)
- [Coinbase Exchange WebSocket Channels](https://docs.cdp.coinbase.com/exchange/websocket-feed/channels)
- [Coinbase Exchange Products](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-all-known-trading-pairs)
- [Kraken Tradable Asset Pairs](https://docs.kraken.com/api-reference/market-data/get-tradable-asset-pairs)
- [Kraken Spot WebSocket Ticker](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/ticker)
- [Hyperliquid Perpetuals Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [Hyperliquid WebSocket Subscriptions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)

### 17.2 历史与机构数据

- [Tardis Historical Data Documentation](https://docs.tardis.dev/faq/data)
- [Tardis Downloadable CSV Specification](https://docs.tardis.dev/downloadable-csv-files)
- [CME Cryptocurrency Futures FAQ / DataMine](https://www.cmegroup.com/articles/faqs/frequently-asked-questions-cryptocurrency-futures.html)
- [CME — Launch of 24/7 Cryptocurrency Futures and Options Trading](https://www.cmegroup.com/media-room/press-releases/2026/6/01/cme_group_announceslaunchof247cryptocurrencyfuturesandoptionstra.html)
- [CFTC COT Historical Compressed Data](https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm)
- [CFTC COT Explanatory Notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm)

### 17.3 宏观与慢频上下文

- [Federal Reserve FOMC Calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [BLS Release Calendar](https://www.bls.gov/schedule/)
- [BLS CPI Release Schedule](https://www.bls.gov/schedule/news_release/cpi.htm)
- [BEA Release Schedule](https://www.bea.gov/news/schedule/)
- [FRED/ALFRED API — Series Observations and Vintages](https://fred.stlouisfed.org/docs/api/fred/series_observations.html)
- [Circle USDC Transparency](https://www.circle.com/transparency)
- [Tether Transparency](https://tether.to/transparency/?tab=reports)
- [iShares IBIT Holdings](https://www.ishares.com/us/products/333011/ishares-bitcoin-trust-etf)

### 17.4 理论与验证

- [Cont, Kukanov & Stoikov — The Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402)
- [CME — Open Interest](https://www.cmegroup.com/education/lessons/open-interest.html)
- [Oxford — Bitcoin Price Formation and Fragmentation](https://ora.ox.ac.uk/objects/uuid%3Ac124591c-2dc9-4bbb-90a8-ebc4d7f2caf8)
- [Bailey & López de Prado — The Deflated Sharpe Ratio](https://www.pm-research.com/content/iijpormgmt/40/5/94)
- [Bailey et al. — The Probability of Backtest Overfitting](https://escholarship.org/uc/item/4hn4t174)
- [Lo, Mamaysky & Wang — Foundations of Technical Analysis](https://doi.org/10.1111/0022-1082.00265)
- [Llorente, Michaely, Saar & Wang — Dynamic Volume-Return Relation of Individual Stocks](https://doi.org/10.1093/rfs/15.4.1005)
- [Hamilton — A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle](https://doi.org/10.2307/1912559)
- [Adams & MacKay — Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
- [Gneiting & Raftery — Strictly Proper Scoring Rules, Prediction, and Estimation](https://doi.org/10.1198/016214506000001437)

---

## 18. 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 2.1 | 2026-07-26 | 新增“未读取新 outcome / 纯合成验证”的通用多视角竞争机制—动态路径方法论：严格分离数据/状态/视角/机制/路径/动作；冻结 full-proof method authority、causal exact EvidenceEvent/PathEvent lifecycle、可共存非归一 primitive 机制库与 OTHER、有限 compound path competition set、variable-length partial order、四分支 synthetic UtilityReceipt、V5-M00 全局 `ABSTAIN`、非空唯一 PatternInstance candidates 与 T-026–T-036/H-015–H-023；已见叙事仅作诊断且不参与规则调参；不扩大 BTC V1 或任何交易权限 |
| 2.0-P0-RSI-02 | 2026-07-23 | P0-RSI-01 静态契约与 Sol 阶段审查 PASS：v0.2 状态统一为 `P0-RSI-01_PASS / E0 / SYNTHETIC_PRIMITIVES_ONLY`；contract 仍为 `REVIEW_READY / E0 / REJECT_FREEZE`、strategy binding `ABSENT_BY_DESIGN`，仅授权纯合成 primitives/manifest/tests，活动 G1 package 不可写 |
| 2.0-P0-RSI-01 | 2026-07-23 | Sol 理论阶段门 PASS：状态转为 `THEORY_PASS / E0 / CONTRACT_DRAFTING`；唯一授权 outcome-free contract/chronology freeze candidate、canonical serialization/SHA-256、static validator 与纯合成无 outcome fixtures，未授权策略原语、数据读取、回测、校准、holdout、paper 或交易 |
| 2.0-A4c | 2026-07-23 | 固化 reconstructed causal lane 的逐 event 纯函数时钟、C2 opportunity/control lifecycle、唯一序列化 Pivot，以及 `Protocol v2` 与本节 v0.2 的命名消歧；状态保持 `DRAFT / E0 / REWORK` |
| 2.0-A4b | 2026-07-23 | 将 EntryZone 改为 control-indexed；明确 C1/C2 不读 $K$、C5 继承 C4 cohort、C0 无 action，防止 regime gate 泄漏；状态保持 `DRAFT / E0 / REWORK` |
| 2.0-A4 | 2026-07-23 | Sol A4 语义闭包：v0.2 退回 `DRAFT / E0 / REWORK`；加入 lane clock、C1/C2 独立事件、gate-neutral $U$、control action 表、target ACK/rounding 边界与 T-022/T-023 修订；仍未授权实现、历史读取或交易 |
| 2.0 | 2026-07-23 | 明确 supersede `RSI-MTF-DLR-PM v0.1`，以 `RSI-MTF-DRL-PM v0.2` 的 `DRAFT / E0 / REVIEW_READY` future-only research contract 替代；补足 closed-bar RSI、方向独立 Confirm/EntryZone、风险/保护/管理账本、同 cohort controls、逐层错误归因与 chronology，未授权实现、数据读取或交易 |
| 1.6 | 2026-07-23 | 新增 future-only `RSI-MTF-DLR-PM v0.1` 理论 DRAFT：closed-bar RSI、EntryZone、风险/保护状态机、ledger、同 cohort 对照与一次性 holdout 闭环；更新 A3/January/February/March/G1 的 E0 隔离事实，不授权实现或交易 |
| 1.5 | 2026-07-23 | 加入 DEVELOPMENT/CALIBRATION/HOLDOUT 的可持续 chronology；登记 January v4 负面 E0-X 事实；引用 S0-009 条件式 February falsification 与当前 HOLD、G2/交易拒绝边界 |
| 1.4 | 2026-07-23 | 明确严格 post-pressure R 与同步 proxy 边界；极值直反仅为 control；强化 holdout `SEEN`、同 cohort candidate/control、E0-X 与 Jan v1 历史诊断限制 |
| 1.3 | 2026-07-22 | 废止不一致的 Protocol v1；将首份 v2 限定为 PROBE-only；对齐 H-001–H-004 与机器 G2；加入 closed-UTC-second 4H 上下文、角色窗口、归档证据链和冷存储边界 |
| 1.2 | 2026-07-22 | 修复 episode terminal/cooldown 生命周期并升级为 1 秒决策时钟；建立 DEVELOPMENT/HOLDOUT 分离、反事实动作和四类路径标签契约 |
| 1.1 | 2026-07-22 | 冻结 7 天前瞻采集/G1、采集代码与磁盘预算；固定 outcome-free episode/状态/研究协议并建立 PASS-G1-only finalizer；历史 archive 改为非阻塞 P1 |
| 1.0 | 2026-07-22 | 将原始“人数/贪婪恐慌系数”重构为五因子流量—冲击—韧性理论；补充数据宇宙、证据边界、可证伪假设、风险与持续优化治理 |
