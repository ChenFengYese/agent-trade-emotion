# Agent-first 市场认知体系

版本：`3.3.1-agent-first-trader-candidate.1`

状态：`FROZEN_VERSION_CANDIDATE / PRICE_ONLY_CURRENT_SCOPE / NON_EXECUTABLE`

Owner：Market Cognition Agent。

输入：已准入的 `InputSnapshot`、可选计算工具、可追溯长期记忆与权限边界。

输出：写入 `HypothesisRecord.AgentDecisionBody` 权威原文的市场认知、时间尺度、机制、竞争路径、关键 UNKNOWN 与可行动几何；`BehaviorPlan` 只能原样引用/复制其中 Agent 自选动作和仓位。

## 1. 认知权威

市场认知是 Agent 的主体职责，不是系统 reducer、指标分数、规则树或 schema 的产物。Agent 必须自主回答：

1. 当前真正观察到了什么；
2. 哪些只是计算、解释或已知局限；
3. 市场处于什么状态，哪些状态仍无法区分；
4. 什么行为动机或传导机制可以解释观察；
5. 未来可能沿哪些条件路径发展；
6. 哪个新观察最能区分这些路径；
7. 当前认知对动作、入场和仓位的支持上限是什么。

确定性系统可以计算 returns、ATR、区间、斜率、VWAP、相关、距离和其他透明变换，但计算结果只是工具输出。哪个方法适用、当前 regime 是什么、哪个观点领先以及什么将改变结论，全部由 Agent 决定。

格式漂移不能夺走认知权。Agent 没有使用预设 regime 词汇、没有列满预期项目或给出了新的分类，系统仍须原样封存。这些差异只在 Agent Review 中被评价。

## 2. 当前数据现实

本 revision 不扩展数据源。当前只承认与每个 cycle 实际 raw 工件一致的价格类输入；订单流、连续 L2、OI、funding、basis、liquidation、options、macro、news、social、on-chain 与 account 数据继续为 `UNKNOWN_NOT_ADMITTED`，除非某个未来新身份实际取得并封存了合法 PIT raw。

| 能力状态 | 含义 | Agent 如何使用 |
|---|---|---|
| `OBSERVED_CURRENT` | 本 cycle 已取得、存储并通过身份/PIT 检查 | 可作当前事实 |
| `OBSERVED_PRIOR` | 旧 cycle 存在的点时事实 | 只作记忆，检查新鲜度 |
| `CONNECTED_NOT_OBSERVED` | 理论上有 adapter，本 cycle 没有 raw | 不能当作已知 |
| `PUBLICLY_ACQUIRABLE` | 存在合法公开来源，当前未取得 | 只能提 acquisition idea |
| `UNKNOWN_NOT_ADMITTED` | 当前没有可准入证据 | 保持 UNKNOWN，不推断为零 |
| `UNOBSERVABLE_PUBLICLY` | 公开数据无法识别，如真实账户意图 | 明确不可观测 |
| `PROHIBITED` | 需未授权凭据、付费许可或绕过限制 | 不取得、不代理 |

价格-only 不意味着 Agent 只能 WAIT。Agent 可以依据价格结构、时间、波动、区域、接受/拒绝与路径序列形成可反驳决策，但必须明言不知道订单流、拥挤、真实参与者身份和因果。

### 2.1 系统事实合同

每条准入事实至少保留：

```text
source_id, instrument_id, venue, contract_semantics
field, value, unit
provider_observed_at, observed_at, available_at
raw_ref, raw_sha256, transform_version
coverage, missingness, revision
decision_cutoff, admission_result
```

`event_time`、`available_at`、`retrieved_at`、`closed_at` 不能互换。未闭合 K 线不能伪装成确认结果；修订后数值不能回填旧决策。

系统只对这些事实和计算负责。它不得在 `admission_result`、数据标签或派生字段里嵌入看多/看空、regime、lead 或动作建议。

### 2.2 来源等级与实际取得分开

| 来源级 | 例子 | 结论上限 |
|---|---|---|
| `L0_PRIMARY_RAW` | 交易所原始 trade/book、正式公告、节点事实 | 只对该 provider/字段负责 |
| `L1_PRIMARY_AGGREGATED` | 官方 candles、OI、funding、宏观发布 | 受聚合、修订和覆盖限制 |
| `L2_TRANSPARENT_DERIVED` | 可复算 returns、ATR、OFI、RV | 只证明公开公式输出 |
| `L3_OPAQUE_DERIVED` | 不透明标签、情绪、部分仪表盘 | proxy，不升级为事实 |
| `L4_COMMUNITY` | 社区观点、图表解读 | 发现问题/叙事候选 |

“来源存在”不等于“本轮已知”。每一个当前声称都必须回指本 cycle raw；否则 Agent 应当将它写为 UNKNOWN。

### 2.3 依赖去重

Agent 应识别事实的共同来源：

```text
price closes
  ├─ moving averages
  ├─ RSI / MACD
  ├─ slope / momentum
  └─ breakout distance
```

上述结果都属于 `PRICE_ACTION` 一个依赖族。名称增加不等于独立证据增加。系统可以提供 lineage，但是否存在重复支持、其对假说有何意义由 Agent 判断。

## 3. 市场识别对象

完整市场认知应能够识别下列对象，但本轮只能使用实际准入数据。不可用价格 proxy 填满其他层。

| 对象 | Agent 需识别 | 当前价格-only 上限 |
|---|---|---|
| 标的/合约 | 现货、永续、交割、指数/标记、乘数、venue | 身份与公开合约几何 |
| 价格结构 | 趋势、区间、突破、失败突破、缺口、摆动 | 可观测 |
| 成交参与 | volume、trade count、成交速度、主动流 | 只有 candle volume 时不识别 aggressor |
| 波动/跳跃 | realized range、RV、vol-of-vol、gap | 价格可观测，IV UNKNOWN |
| 流动性 | spread、depth、impact、补单、恢复 | UNKNOWN，不用 candle 推断 |
| 订单流 | aggressor、OFI、CVD、吸收、queue | UNKNOWN |
| 杠杆/拥挤 | OI、funding、basis、清算、options | UNKNOWN |
| 跨 venue/相对价值 | basis、价差、领先滞后 | 未准入则 UNKNOWN |
| 跨资产 | 美元、利率、股指、信用、商品、主流币 | UNKNOWN |
| 宏观/政策 | 增长、通胀、就业、流动性、发布 vintage | UNKNOWN |
| 事件/催化 | 预定/突发、预期/实际、生效与反应 | UNKNOWN，除非原文已准入 |
| 叙事/注意力 | 讨论广度、搜索、传播与立场变化 | UNKNOWN |
| 链上/网络 | block、fee、supply、已知地址流、升级 | UNKNOWN |
| 基本面/代币 | 供给、解锁、费用、治理、价值权利 | UNKNOWN |
| venue/network health | 维护、中断、指数、最终性、脱锚 | 未准入则 UNKNOWN |

对于 UNKNOWN 层，Agent 仍可生成“如果将来取得 X，哪个结果将改变判断”的区分性问题，但不能在当前决策中当作 X 已存在。

## 4. 当前 price-only 认知核心

### 4.1 价格、收益和闭合结构

可用对象：mark/index/last 中已准入的一种、closed OHLC、log return、gap、range、摆动高低点、结构突破/失败与价格接受/拒绝。

```text
r_t = ln(P_t / P_{t-1})
TrueRange = max(high-low, |high-prev_close|, |low-prev_close|)
RV_h = sqrt(sum(r_i^2 over h))
```

公式输出是测量，不是方向决定。Agent 应比较持续、回撤、反转频率、边界迁移与对突破的后续接受，而不是因一根 K 线或一个指标自动贴标签。

### 4.2 趋势、区间、混沌与转换

Agent 可以使用以下语言，也可以创建更贴合当前市场的状态描述：

| 候选状态 | 常用观察 | 关键反证 |
|---|---|---|
| 趋势持续 | 高低点序列、回撤可控、突破后接受 | 连续结构失败、反向扩张 |
| 可重放区间 | 边界反应、中心回归、突破无接受 | 边界迁移、区间外持续 |
| 混沌/成本主导 | 延续低、反转高、可用空间小 | 持续性和位移恢复 |
| 波动压缩 | range/RV 收缩、区域收敛 | 新的持续扩张 |
| 波动扩张 | range/RV 跃升、价格重定价 | 扩张衰减且回到旧价值 |
| 转换/未解 | 旧状态失效、新状态未稳定 | 新状态出现重复可观测序列 |

系统不得用固定阈值自动产生最终 regime。它可以返回多窗口测量与敏感性，Agent 对窗口适用性与语义负责。

### 4.3 区域、拍卖与反身性

区域可来自摆动、历史接受/拒绝、VWAP/成交分布（如果有合法 volume）、round number、缺口、波动宽度或多时间尺度共振。

每个会改变决策的 zone 应由 Agent 说明：

```text
construction and source window
boundary or uncertainty band
why it matters now
acceptance / rejection / false-break alternatives
expiry or migration condition
```

区域不得根据事后 outcome 移动到刚好命中的位置。反复触碰可能增强可见性，也可能消耗原有流动性；哪个解释当前更合理由 Agent 比较。

### 4.4 价格-only 不可声称的内容

- 真实买卖者、机构/散户或开平仓身份；
- 订单簿吸收、恢复性、实际可成交容量；
- OI/funding/清算与价格变化的当前联合解释；
- 宏观、新闻、叙事、链上流的当前因果；
- 真实 spread、slippage、fill、fee、margin 与账户风险；
- 价格路径外的“全面市场确认”。

## 5. Agent 可用的成熟方法库

方法是工具，不是自动 alpha。Agent 可选择、组合、拒绝或提出新方法。建议为每个实际启用的方法考虑 `question / inputs / horizon / regime / output / alternatives / invalidation / snooping risk`，但这不是字段资格门。

### 5.1 趋势与时间序列动量

工具：高低点、通道/突破、移动中心斜率、不同 horizon return、波动调整持续与回撤。

适用候选：价格发现和方向持续。主要反证：区间、假突破、拥挤反转、事件重定价与成本过高。参考：[Moskowitz, Ooi & Pedersen](https://doi.org/10.1016/j.jfineco.2011.11.003)、[Daniel & Moskowitz](https://doi.org/10.1016/j.jfineco.2015.12.002)。

### 5.2 均值回归、超调与价值区

```text
z_t = (x_t - rolling_center) / rolling_scale
```

工具：rolling median/mean、z-score、VWAP/价值区偏离、布林带类标准化、极值后衰竭。关键问题是“偏离了仍有效的中心”还是“中心已经迁移”。

### 5.3 波动和状态转换

工具：RV/ATR/range 分位、反转频率、趋势持续、change-point、状态转换与窗口敏感性。Hamilton regime switching 支持这类建模候选，不会为当前标签提供真值：[Hamilton 1989](https://doi.org/10.2307/1912559)。

### 5.4 拍卖、Market/Volume Profile 与 VWAP

用于识别接受区、成交密集/稀疏区、相对价值和回归/突破后接受。session 切分、数据源和 profile 参数会改变结果；分布不自动提供方向。参考：[CME glossary](https://www.cmegroup.com/education/glossary)。

### 5.5 经典技术指标

RSI、MACD、均线、通道、布林带、ATR 可用于压缩信息、找背离/衰竭/重置或对齐不同窗口。它们应回到价格结构和依赖族，不作多票表决。[Lo, Mamaysky & Wang](https://doi.org/10.1111/0022-1082.00265) 支持对技术形态进行统计审视，不支持任意参数的普适性。

### 5.6 订单流与微观结构（当前 UNKNOWN）

候选问题：相同主动流是否推动更大/更小价格变化？被消耗流动性是否补回？显示深度撤走还是真实成交导致位移？

需要连续有序 trades/L2。单次 REST snapshot 不足以识别 queue、吸收、补单或韧性。本版不扩源，因此不启用这些当前结论。

### 5.7 衍生品、拥挤和强制去杠杆（当前 UNKNOWN）

将 price、OI、funding、basis、liquidation 和 options 放入竞争解释；不把 OI 上升自动解释为新多头，不把高 funding 自动解释为即将下跌，不把不完整清算 feed 当全市场总账。当前没有准入该类 raw，不产生当前拥挤结论。

### 5.8 宏观、跨资产与事件（当前 UNKNOWN）

候选方法：release surprise/vintage、rolling beta、相关变化、实际利率/美元/信用/股指组合、正式事件的预期—实际—反应链。慢频数据用当时 vintage，不回填修订值；一次发布不直接决定分钟级方向。

### 5.9 相对价值、横截面与协整（当前 UNKNOWN）

候选方法：spread、z-score、rolling beta、cointegration/error correction、波动调整相对强弱和 breadth。价差存在不代表可执行套利；要考虑转移、资金、费用、venue 和结构断点。当前单标的 price-only 不产生横截面声称。

### 5.10 叙事、注意力与链上（当前 UNKNOWN）

信息真值假说与受众行为假说必须分开。搜索、转载、评论和链上地址都是有限 proxy；热度不是仓位，地址不是用户，转账不是买卖。本版不扩源，所以它们只保留为未来可评价方法库。

### 5.11 数据窥探与参数敏感性

方法越多，事后找到“刚好解释”的概率越高。Agent 应说明相邻合理窗口下结论是否改变，并把不稳定性进入决策。参考：[Sullivan, Timmermann & White](https://doi.org/10.1111/0022-1082.00163)、[White reality check](https://doi.org/10.1111/1468-0262.00152)。

## 6. 时间尺度路由

| Frame | 典型 horizon | Agent 要回答 | 当前 price-only 方法 |
|---|---|---|---|
| `STRUCTURAL` | 月至年 | 制度、供给、长期流动性是否改变 | 只有长历史价格时限于结构描述 |
| `STRATEGIC` | 日至周 | 主状态、主要方向和尾部不对称 | 1D/4H 结构、波动、回撤 |
| `TACTICAL` | 小时至数日 | 当前路径、区域、转换和机会 | 4H/1H/15m 结构与接受/拒绝 |
| `TRIGGER` | 分钟至小时 | 何时入场、失效、保护或重评 | closed 15m/5m 与预声明条件 |
| `MICRO` | 毫秒至分钟 | queue、impact、fill 质量 | 当前不可用 |

每次决策默认只需三个功能 frame：

```text
CONTEXT_FRAME   背景和主风险
DECISION_FRAME  当前判断和假说
TRIGGER_FRAME   entry/stop/target 的短时条件
```

高周期不是低周期动作的自动否决器；低周期也不能因一个触发改写高周期事实。Agent 可同时持有高周期看法和短 horizon 反向或防守假说，但需说清时钟。

`decision_horizon` 是要判断的未来，`lookback` 是用于估计的历史。Agent 可根据市场状态选择窗口，但不应为了得到喜欢的方向事后改变窗口。

## 7. 按行为动机分析

Agent 可用行为动机组织竞争解释，但不宣称识别了真实主体。每个动机至少考虑一个替代动机。

| 动机候选 | 可观察签名候选 | 常见误判 |
|---|---|---|
| 方向投机 | 持续、加速、风险参与扩张 | 套保/套利腿当方向 |
| 套保 | 相关资产和衍生品反向变化 | 当作单向情绪 |
| 做市库存 | 冲击后补充、短时反转、spread 变化 | 当作“主力护盘” |
| 基差/跨 venue 套利 | 多腿同步、价差收敛 | 单腿变化当方向 |
| 强制去杠杆 | 快速价格/OI 变化、流动性冲击 | 部分 liquidation feed 当全量 |
| 再平衡/被动流 | 时间窗口和跨资产同步 | 事后故事化 |
| 获利了结 | 有利路径中的动量/承接变化 | 自动等于趋势反转 |
| 恐慌/追涨 | 注意力和流动性共同加速 | 声称知道群体心理 |
| 信息重定价 | 正式事件后多 venue 接受新价格 | 谣言或标题当事实 |

当前 price-only 不足以确认上述任一行的真实动机。Agent 只能把它们作为产生相同价格表象的竞争解释，并写出哪个未来观察能区分。

## 8. Agent 市场分析路线

### 8.1 Cold / 深度认知

```text
1. 核对 instrument、venue、cutoff、horizon 和价格口径
2. 声明本轮实际数据覆盖与 UNKNOWN
3. 比较 context / decision / trigger 三个 frame
4. 识别结构、区域、波动与最近变化
5. 选择适用方法，说明方法失效可能
6. 生成至少一个主机制和有力替代机制，数量由 Agent 决定
7. 建立未来路径、反证、期限与下一项区分观察
8. 说明什么几何支持 entry / stop / targets / WAIT / OTHER
9. 作出最终不可执行参考动作和仓位决策
10. 以可读正文封存，不为 schema 重写
```

这是语义责任路线，不是必须按顺序输出的十个字段。Agent 可以用自己的组织方式交付。

### 8.2 Delta / 增量复核

```text
load original prior decision and bounded memory
→ admit only new closed price facts
→ compare what materially changed
→ update affected market interpretation and hypotheses
→ reconsider entry/stop/targets/position and final action
→ seal a new exact decision body
```

Delta 是 Agent 的增量思考，不是系统依赖图自动更新决策。系统可提供差分和旧原文；Agent 决定什么变化有意义以及是否需要改变决策。

### 8.3 触发/事件复核

当前没有准入非价格事件源时，只能对已封存的价格条件、expiry 或预注册 review 时间复核。未来若正式事件原文已准入，Agent 可将事实真值、受众反应假说和价格接受分开。

### 8.4 冲突处理

当方法或时间尺度冲突时，Agent 不做多数投票：

1. 检查是否在回答不同 horizon；
2. 检查数据和窗口是否匹配；
3. 识别哪个方法的前置条件可能失效；
4. 将冲突改写为竞争路径或时钟差异；
5. 选择能产生不同预期的下一观察；
6. 如果仍无法区分，直接保留歧义，不让系统用 tie-break 制造唯一结论。

## 9. 核心市场模型

### 9.1 多层传导

```text
制度/宏观
→ 融资/流动性/中介约束
→ 标的供给/基本面
→ 跨资产与 venue 网络
→ 微观结构/杠杆/波动
→ 注意力/叙事/行为
→ 价格路径与反馈
```

这是生成候选机制的思考图，不是要求每层有数据的资格门。当前只有价格时，Agent 不得倒推上游层为已知因果。

### 9.2 反身性路径

价格变化可能改变注意力、止损、杠杆、做市库存和流动性，再反馈价格。Agent 应分开可观测的价格路径与未观测的行为机制，并为后者保留替代解释。

### 9.3 动态多方法组合

Agent 不需选一个永久冠军模型。常见组合候选：

| 市场状态 | 候选主方法 | 必须关注的失效 |
|---|---|---|
| 趋势 | 结构/动量/回撤 | 假突破、晚入、反向扩张 |
| 区间 | auction/VWAP/均值回归 | 边界迁移、新信息重定价 |
| 波动扩张 | break/path/区域接受 | 双向扫损、快速衰减 |
| 波动压缩 | range/突破双路径 | 预测方向过早 |
| 混沌 | 反转频率/成本/条件触发 | 过度交易、伪精确级别 |
| UNKNOWN | 简单 price baseline + 信息价值 | 用未取得数据伪造全面确认 |

组合由 Agent 基于当前任务决定，不由系统按状态标签自动路由。

## 10. 工具与信息源导航

本节只保留 V3.3.0 已有方法来源导航，不表示本版新增了数据能力。每个当前事实仍必须有本 cycle raw。

| 领域 | 公开入口 | 合理用途 | 不能声称 |
|---|---|---|---|
| 当前公开 venue | [OKX API](https://www.okx.com/docs-v5/en/) | instrument、server time、public price/candles | endpoint 存在等于已取得 |
| 其他交易所参考 | [Binance Market Data](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api)、[Coinbase WS](https://docs.cdp.coinbase.com/exchange/websocket-feed/overview) | 公开 market-data 定义 | 本版已接入 |
| 期权参考 | [Deribit public API](https://docs.deribit.com/api-reference/market-data/public-get_book_summary_by_currency) | IV/OI/book 字段定义 | dealer gamma 方向 |
| 美国宏观 vintage | [FRED/ALFRED](https://fred.stlouisfed.org/docs/api/fred/overview.html)、[BLS](https://www.bls.gov/developers/)、[BEA](https://apps.bea.gov/api/) | release/vintage 语义 | 已取得当前宏观数据 |
| 政策/头寸 | [Federal Reserve](https://www.federalreserve.gov/)、[CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) | 正式文件与周度分类 | 分类等于真实动机 |
| 公司/监管 | [SEC EDGAR](https://www.sec.gov/edgar/search-and-access) | 原始 filing | 聚合标题已确认影响 |
| 新闻发现 | [GDELT](https://www.gdeltproject.org/data.html) | 发现线索与去重 | 事件真值或影响 |
| 注意力 | [Google Trends](https://trends.google.com/trends/) | 相对搜索兴趣 | 绝对人数或方向 |
| 链上参考 | [Bitcoin Core RPC](https://developer.bitcoin.org/reference/rpc/)、[Ethereum EIPs](https://github.com/ethereum/EIPs) | 链事实和升级原文 | 地址身份或当前买卖 |

可用工具：Python/SQL/Jupyter/Spreadsheet/图表用于计算、对齐、敏感性和可视化。系统返回输入引用、公式/版本和输出；Agent 判断其意义。

社区高互动方案只能作为 `COMMUNITY_HEURISTIC_NOT_EVIDENCE`：提取问题，查找可复算定义，写适用状态与失效，移除收益承诺和固定参数，保留为未验证 method/policy candidate。热度、点赞和单个案例不是市场证据。

## 11. 可读市场认知的语义责任

高质量 `AgentDecisionBody` 应让人能够从原文理解：

- 标的、cutoff、决策 horizon 与当前数据覆盖；
- 事实、测量、解释和 UNKNOWN 的区别；
- 多时间尺度结构及其最近变化；
- 当前市场状态、备选状态与区分条件；
- 使用了什么方法、为什么适用以及何时失效；
- 竞争机制、未来路径、关键区域、反证和 expiry；
- 哪个下一观察会改变决策；
- 市场认知如何支持最终动作和仓位几何。

这是 Agent 的语义责任清单，不是 JSON 字段清单、固定标题或封存资格门。如果决策原文缺失某项，系统可在非权威索引中标记“未找到/有歧义”，但必须封存并继续 Outcome/Review。

## 12. Review 中的认知评价

Outcome 之后由 Agent 评价，不由系统给市场认知打分或自动改规则：

```text
当时对市场状态的判断是否能解释后续路径？
竞争机制是否真的给出了不同预期？
哪些数据缺失真正改变了判断，哪些没有？
方法失效、窗口错配、依赖重复或迟到信息是否发生？
关键区域、反证与 expiry 是否事前有意义？
哪个新方法/数据真的值得作为后续候选？
```

下列结果仍保持 UNKNOWN：哪种方法对当前 horizon 有预测增量、价格-only Agent 是否稳定、非价格数据是否能提高决策质量、任何组合是否能产生成本后正价值。
