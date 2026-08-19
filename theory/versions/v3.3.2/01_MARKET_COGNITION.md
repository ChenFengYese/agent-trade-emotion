# V3.3.2 Agent-first 完整市场分析手册

版本：`3.3.2-complete-market-analysis-candidate.3`

状态：`FROZEN_THEORY_REVIEW_CANDIDATE / COVERAGE_AWARE / DYNAMIC_HANDOFF_DEFINED / NON_EXECUTABLE`

Owner：Market Cognition Agent。

输入：已准入的 `InputSnapshot`、可选计算工具、上一 cycle 的精确决策/复盘引用、上一 episode/参考敞口投影、可追溯长期记忆与权限边界。

输出：写入 `HypothesisRecord.AgentDecisionBody` 权威原文的市场认知、时间尺度、机制、竞争路径、关键 UNKNOWN、可行动几何和给动态交易模块的交接语义；`BehaviorPlan` 只能原样引用/复制其中 Agent 自选动作和仓位。

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

V3.3.2 建立完整分析语义，但不因文档存在而宣称任何数据已经取得。每个 cycle 只承认其 `InputSnapshot` 实际封存的合法 PIT raw：价格可以是核心覆盖，trades、books、OI、funding、basis、liquidation、options、macro、news、social、on-chain 或公开申报则逐项按实际覆盖启用。未取得的数据保持 `UNKNOWN`，但相应机制仍可作为 `PLAUSIBLE_UNVERIFIED` 竞争假说和条件规划背景存在。

| 能力状态 | 含义 | Agent 如何使用 |
|---|---|---|
| `OBSERVED_CURRENT` | 本 cycle 已取得、存储并通过身份/PIT 检查 | 可作当前事实 |
| `OBSERVED_PRIOR` | 旧 cycle 存在的点时事实 | 只作记忆，检查新鲜度 |
| `CONNECTED_NOT_OBSERVED` | 理论上有 adapter，本 cycle 没有 raw | 不能当作已知 |
| `PUBLICLY_ACQUIRABLE` | 存在合法公开来源，当前未取得 | 只能提 acquisition idea |
| `UNKNOWN_NOT_ADMITTED` | 当前没有可准入证据 | 保持 UNKNOWN，不推断为零 |
| `UNOBSERVABLE_PUBLICLY` | 公开数据无法识别，如真实账户意图 | 明确不可观测 |
| `PROHIBITED` | 需未授权凭据、付费许可或绕过限制 | 不取得、不代理 |

价格-only 不意味着 Agent 只能 WAIT。Agent 可以依据价格结构、时间、波动、区域、接受/拒绝与路径序列形成可反驳决策，也可以提出机构维护、派发、套牢盘解套、错误叙事、强制去杠杆等未验证机制；但必须把它们写成假说而不是已观察事实，并说明替代解释、条件路径、反证与风险上限。

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

完整市场认知应能够识别下列对象，但每轮只能把实际准入数据写成事实。不可用价格 proxy 填满其他层，也不可因为某层没有数据就删除其假说空间。

| 对象 | Agent 需识别 | 事实与假说边界 |
|---|---|---|
| 标的/合约 | 现货、永续、交割、指数/标记、乘数、venue | 身份与公开合约几何 |
| 价格结构 | 趋势、区间、突破、失败突破、缺口、摆动 | 可观测 |
| 成交参与 | volume、trade count、成交速度、主动流 | 只有 candle volume 时不识别 aggressor |
| 波动/跳跃 | realized range、RV、vol-of-vol、gap | 价格可观测，IV UNKNOWN |
| 流动性 | spread、depth、impact、补单、恢复 | 有连续 book/trade 才能确认；无数据可保留竞争假说 |
| 订单流 | aggressor、OFI、CVD、吸收、queue | 有合法逐笔/L2才是事实；K线只能产生有限代理假说 |
| 杠杆/拥挤 | OI、funding、basis、清算、options | 按字段实际覆盖；缺失不等于不存在 |
| 跨 venue/相对价值 | basis、价差、领先滞后 | 未准入则 UNKNOWN |
| 跨资产 | 美元、利率、股指、信用、商品、主流币 | UNKNOWN |
| 宏观/政策 | 增长、通胀、就业、流动性、发布 vintage | UNKNOWN |
| 事件/催化 | 预定/突发、预期/实际、生效与反应 | UNKNOWN，除非原文已准入 |
| 叙事/注意力 | 讨论广度、搜索、传播与立场变化 | UNKNOWN |
| 链上/网络 | block、fee、supply、已知地址流、升级 | UNKNOWN |
| 基本面/代币 | 供给、解锁、费用、治理、价值权利 | UNKNOWN |
| venue/network health | 维护、中断、指数、最终性、脱锚 | 未准入则 UNKNOWN |

对于 UNKNOWN 层，Agent 仍可生成“如果将来取得 X，哪个结果将改变判断”的区分性问题，但不能在当前决策中当作 X 已存在。

## 4. 价格核心：所有覆盖状态都必须掌握

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

### 4.4 只有价格时不可声称的内容

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

### 5.6 订单流与微观结构（按实际覆盖启用）

候选问题：相同主动流是否推动更大/更小价格变化？被消耗流动性是否补回？显示深度撤走还是真实成交导致位移？

需要连续有序 trades/L2。单次 REST snapshot 不足以识别 queue、吸收、补单或韧性。取得合法 PIT raw 时可以形成当前测量；否则只保留会产生不同未来路径的微观结构假说。

### 5.7 衍生品、拥挤和强制去杠杆（按实际覆盖启用）

将 price、OI、funding、basis、liquidation 和 options 放入竞争解释；不把 OI 上升自动解释为新多头，不把高 funding 自动解释为即将下跌，不把不完整清算 feed 当全市场总账。缺少其中部分字段时，缩小结论而不是补零。

### 5.8 宏观、跨资产与事件（按实际覆盖启用）

候选方法：release surprise/vintage、rolling beta、相关变化、实际利率/美元/信用/股指组合、正式事件的预期—实际—反应链。慢频数据用当时 vintage，不回填修订值；一次发布不直接决定分钟级方向。

### 5.9 相对价值、横截面与协整（按实际覆盖启用）

候选方法：spread、z-score、rolling beta、cointegration/error correction、波动调整相对强弱和 breadth。价差存在不代表可执行套利；要考虑转移、资金、费用、venue 和结构断点。单标的 price-only 不产生横截面声称。

### 5.10 叙事、注意力与链上（按实际覆盖启用）

信息真值假说与受众行为假说必须分开。搜索、转载、评论和链上地址都是有限 proxy；热度不是仓位，地址不是用户，转账不是买卖。取得数据时只能在其覆盖范围内使用，缺失时仍可保留叙事传播的条件假说。

### 5.11 数据窥探与参数敏感性

方法越多，事后找到“刚好解释”的概率越高。Agent 应说明相邻合理窗口下结论是否改变，并把不稳定性进入决策。参考：[Sullivan, Timmermann & White](https://doi.org/10.1111/0022-1082.00163)、[White reality check](https://doi.org/10.1111/1468-0262.00152)。

## 6. 时间尺度路由

| Frame | 典型 horizon | Agent 要回答 | 无增强数据时的价格方法 |
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

当轮只有价格时，不足以确认上述任一行的真实动机。Agent 仍可把它们作为产生相同价格表象的竞争解释，并写出哪个未来观察能区分。

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
→ admit only new legally available closed/released facts
→ compare what materially changed
→ update affected market interpretation and hypotheses
→ reconsider entry/stop/targets/position and final action
→ seal a new exact decision body
```

Delta 是 Agent 的增量思考，不是系统依赖图自动更新决策。系统可提供差分和旧原文；Agent 决定什么变化有意义以及是否需要改变决策。

### 8.3 触发/事件复核

当轮没有准入非价格事件源时，只能对已封存的价格条件、expiry 或预注册 review 时间复核。若正式事件原文已准入，Agent 必须将事实真值、受众反应假说和价格接受分开。

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

本节给出 V3.3.2 方法来源导航，不表示文档本身新增了数据能力。每个当前事实仍必须有本 cycle raw。

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

## 13. 四层完整市场分析协议

V3.3.2 将市场分析固定为四层认知结构。四层是语义 owner，不是四个必须独立部署的软件服务：

```text
L1 市场身份与点时事实
→ L2 透明派生测量与依赖关系
→ L3 参与者、心理、信息和博弈竞争假说
→ L4 条件路径、动作、仓位与复盘
```

| 层 | 只回答什么 | 输入 | 输出 | 唯一 owner |
|---|---|---|---|---|
| L1 身份/事实 | 当时实际观察到什么 | 合法 raw、合约资料、正式事件 | 有时间和覆盖边界的事实 | 系统事实 owner |
| L2 测量/关系 | 事实经过什么透明变换 | L1 + 可复算公式 | returns、RV、OFI、basis、相对量等 | 系统计算；Agent解释 |
| L3 假说/博弈 | 哪些机制、人群和心理可解释表象 | L1/L2、记忆、理论 | 主假说、强替代、OTHER、区分观察 | Agent |
| L4 路径/动作 | 未来如何演化，如何提前规划 | L3、风险几何、权限 | 条件路径、触发、反证、动作、仓位、review | Agent；系统封存 |

跨层纪律：

1. L2 不能把指标计算结果命名为“机构派发”或“恐慌”；
2. L3 可以提出没有直接数据的机制，但必须标明证据等级；
3. L4 可以针对未验证机制设计条件交易，但风险必须以可观察触发和失效约束；
4. Outcome 可以验证路径、动作和仓位是否有用，不能自动证明未观测主体身份；
5. 学习候选不能自动修改冻结理论。

## 14. 标的、合约、venue 与代币化资产识别

方向分析之前必须先确认“分析的到底是什么”。同名标的可能同时存在底层股票、代币化包装、现货、永续、交割合约、指数和标记价格。

### 14.1 标的身份卡

```text
display_name
instrument_id / underlying_id
asset_type
venue / jurisdiction
quote_currency / settlement_currency
contract_multiplier / tick / lot
price_semantics: last | mark | index | underlying
trading_hours / maintenance / auction
issuer_or_wrapper / custodian / redemption
corporate_action_mapping
fx_or_stablecoin_dependency
decision_cutoff / source refs / unresolved semantics
```

若任一字段未知，Agent 必须说明它是否会改变趋势、关键位、风险或交易时间判断。

### 14.2 代币化股票的双层价格模型

```text
底层股票价格
→ 官方/供应商指数与汇率
→ 包装、托管、赎回和公司行动权利
→ 代币 venue 的订单簿与时段流动性
→ 代币成交价
```

应分别分析：

- 底层股票处于开市、闭市、盘前还是盘后；
- 代币是否 24/7 交易，闭市期间价格由什么形成；
- 指数或oracle的更新时间、来源和异常处理；
- USD、USDT或其他报价之间的FX/稳定币风险；
- 分红、拆股、停牌、退市等公司行动如何传递；
- 是否存在可执行赎回/套利，谁能使用以及时延；
- 代币自身spread、depth和成交量是否足以承载底层价格映射；
- `token_price - mapped_underlying_price` 的tracking basis是否持续。

不能把底层市场的支撑直接当作代币venue的可成交支撑；也不能把代币薄盘口的跳价当作底层公司价值重定价。

## 15. 数据字典、推导关系与解释上限

### 15.1 价格、K线与波动族 `PRICE_ACTION`

原始字段：`open/high/low/close`、last、mark、index、bid、ask、timestamp。

常用透明测量：

```text
return_t = ln(close_t / close_{t-1})
bar_range = high - low
body = |close - open|
upper_wick = high - max(open, close)
lower_wick = min(open, close) - low
body_ratio = body / bar_range
close_location = (2*close - high - low) / bar_range
TrueRange = max(high-low, |high-prev_close|, |low-prev_close|)
RV_h = sqrt(sum(return_i^2 over h))
```

解释上限：价格能够确认路径、结构和接受/拒绝，不能单独确认交易者身份、开平仓、真实情绪、内幕信息或机构意图。

RSI、MACD、均线、斜率、布林带、突破距离都从价格族派生；五个指标方向一致仍主要是一份价格证据。

### 15.2 成交活跃度族 `TRADE_ACTIVITY`

原始字段：base volume、quote volume/turnover、trade count、逐笔价量、aggressor side（若provider定义可靠）。

```text
turnover = sum(price_i * size_i)
VWAP = turnover / sum(size_i)
trade_arrival_rate = trade_count / elapsed_time
average_trade_size = total_volume / trade_count
relative_volume = current_volume / comparable_window_baseline
```

必须分开：

| 概念 | 含义 | 不等于 |
|---|---|---|
| 成交量 | 成交资产或合约数量 | 资金规模、人数 |
| 成交额 | 价乘量的总和 | 净流入；每笔交易同时有买卖两方 |
| 成交笔数 | matching events 数量 | 唯一成交人数 |
| 主动买/卖量 | provider规则下的aggressor流 | 新开多/新开空 |
| 大单占比 | 某阈值以上成交占比 | 机构身份 |

唯一成交人数只有在来源明确提供去重账户且口径合法时才能使用。trade count、地址数、账户多空比都不能替代真实人数。

### 15.3 盘口与订单流族 `MICROSTRUCTURE`

原始字段：有序bid/ask价量、逐笔成交、订单新增/修改/撤销、sequence id。

```text
mid = (best_bid + best_ask) / 2
spread = best_ask - best_bid
spread_bps = spread / mid * 10000
depth_bid(x) = sum(bid size within x bps)
depth_ask(x) = sum(ask size within x bps)
book_imbalance = (depth_bid-depth_ask)/(depth_bid+depth_ask)
CVD_h = sum(signed_trade_volume over h)
impact = price_change / signed_flow
resiliency = time/depth needed to recover after shock
```

OFI应按provider序列和价格层级变化计算，不能用一张REST快照伪造。单次盘口只能描述当时显示流动性；连续数据才可研究撤单、补单、吸收和恢复。

### 15.4 衍生品、杠杆与拥挤族 `POSITIONING_LEVERAGE`

| 数据 | 真正含义 | 常见误读 |
|---|---|---|
| OI | 尚未平仓合约总量 | OI上涨=新多头；每张合约同时有多空两端 |
| funding | 永续多空之间的周期性支付及偏离机制 | funding高=马上跌 |
| basis | 衍生品相对现货/指数的价差 | 正basis=必然看涨 |
| account long/short ratio | 做多账户数/做空账户数 | 资金或持仓规模比 |
| position long/short ratio | provider口径下的持仓规模比 | 全市场净多空 |
| taker buy/sell ratio | 主动成交方向比 | 开仓方向比 |
| liquidation feed | feed覆盖内的强制平仓 | 全市场完整清算账本 |
| option IV/skew | 期权价格隐含的波动和尾部相对定价 | 单一dealer gamma方向 |

任何“多空比”必须携带 `population / numerator / denominator / instrument_scope / venue / window`，否则不进入组合分析。

### 15.5 参与者、成本与公开头寸族 `PARTICIPANT_PROXY`

可能来源：CFTC COT、SEC/公司正式申报、公开持仓集中度、volume profile、链上已知标签、账户级公开聚合。

可以研究：报告分类、滞后头寸、成本密集区、集中度、已知地址流和公开持仓变化。

不能直接研究：匿名账户真实身份、每笔开平仓理由、所有机构当前意图、未报告交易者人数、跨venue完整组合。

### 15.6 信息、基本面、宏观与注意力族

| 依赖族 | 事实候选 | 派生候选 | 结论上限 |
|---|---|---|---|
| `EVENT_FACT` | 正式公告、发布日期、原文、生效时间 | novelty、预期差、事件阶段 | 不能仅凭标题确认价格因果 |
| `FUNDAMENTAL` | 财报、供给、解锁、现金流、权利 | 增长、利润、估值、稀释 | 估值不自动给短周期方向 |
| `MACRO_CROSS_ASSET` | 利率、美元、指数、信用、行业 | rolling beta、相关变化、surprise | 历史相关不保证当前传导 |
| `ATTENTION_NARRATIVE` | 搜索、新闻、公开帖子、传播时间 | 广度、速度、立场、情绪proxy | 热度不等于持仓或全体心理 |
| `ON_CHAIN_NETWORK` | 区块、费用、供应、已知标签流 | 活跃度、净流、集中度 | 地址不等于人，转账不等于买卖 |

### 15.7 每项数据的最小语义卡

新数据进入手册或cycle前至少回答：

```text
definition / provider semantics
instrument and population coverage
unit / scale / sign
event_time / available_at / captured_at
sampling / aggregation / revision
raw ref / transform / dependency family
missingness / known bias
what it can support
what it cannot identify
which hypothesis/action it could change
```

缺少最后三项的数据即使技术上可获取，也不自动拥有分析价值。

## 16. K线、位置、量能与后续确认

### 16.1 单根K线的六维读法

每根K线至少放在六个维度中：

1. **方向结果**：收涨、收跌或近似平衡；
2. **形态**：实体、上下影线、收盘位置；
3. **相对量**：与相同session、星期和状态的基准比较；
4. **所在位置**：趋势中段、关键区、突破外、价值区内；
5. **形成路径**：只有更小周期或逐笔数据才能确认先后顺序；
6. **后续确认**：下一至若干根K线是否接受、拒绝或反转。

### 16.2 常见形态的竞争解释

| 形态 | 可以描述 | 至少保留的替代解释 |
|---|---|---|
| 长上影、收盘靠低 | 高位未被当期接受 | 获利了结、套保、薄流动、事件回撤、派发假说 |
| 长下影、收盘靠高 | 低位被拒绝 | 抄底、空头回补、强平后恢复、做市补单、护盘假说 |
| 宽幅十字星 | 高波动但净方向有限 | 双边止损、事件等待、换手、吸收、派发或吸筹 |
| 窄幅十字星 | 暂时平衡/波动压缩 | 无人交易、等待信息、流动性下降 |
| 大实体收于极端 | 当期方向结果一致 | 趋势参与、强平、流动性真空或消息重定价 |
| 突破后收回区间 | 当期缺少接受 | 假突破、止损清扫、流动性不足或事件快速反转 |

“十字星=机构派发”“长下影=主力吸筹”都不能作为事实；它们可以作为假说，只要给出区分观察。

### 16.3 量价状态序列

| 序列 | 首要问题 | 候选含义 | 不能自动声称 |
|---|---|---|---|
| 缩量下跌 | 卖压衰减还是需求缺失 | 跌速放缓、耐心消耗 | 立即见底 |
| 缩量下跌→放量下跌 | 新信息还是强平 | 再定价/流动性破坏 | 必然继续暴跌 |
| 缩量下跌→放量上涨 | 谁推动、能否接受 | 回补、抄底、事件反弹 | 下降趋势已反转 |
| 缩量上涨→放量下跌 | 获利了结还是趋势破坏 | 供应重新占优 | 上涨周期必然结束 |
| 缩量上涨→放量上涨 | 参与扩张是否健康 | 趋势强化/追涨 | 高量永远可持续 |
| 高量横盘 | 大量交换为何不位移 | 吸收、换手、对敲风险 | 自动吸筹或派发 |

量能必须比较同一市场时段和制度背景。开盘、收盘、事件窗口与普通时段的成交基准不能混用。

## 17. 订单流、流动性和短周期价格形成

### 17.1 五种需要区分的微观状态

| 状态候选 | 可观察签名 | 强替代 |
|---|---|---|
| 主动流推动 | signed flow与价格同向，impact稳定或增强 | 薄盘口放大少量成交 |
| 吸收 | 单边主动流很大但价格位移有限，反向深度持续补充 | 数据延迟、隐藏跨venue对冲 |
| 流动性撤退 | spread扩大、近端depth减少、少量流造成大位移 | 交易所维护、报价源异常 |
| 冲击后恢复 | spread/depth在冲击后快速复原，价格回到旧区 | 新信息尚未传播完全 |
| 流衰竭 | 原方向主动流、成交速度和impact同时减弱 | 仅短时休息，稍后再扩张 |

### 17.2 吸收不是方向结论

买方主动流被卖方吸收，可能代表：

- 大额卖方派发；
- 做市商库存管理；
- 套保或套利腿；
- 旧套牢盘解套；
- 一个暂时存在但会撤走的limit wall。

只有后续价格选择、补单持续性、跨venue同步和OI/basis变化才能继续区分。相同逻辑适用于卖方主动流被买方吸收。

### 17.3 价格冲击效率

Agent 应比较“相同流量造成的位移是否变化”：

```text
directional_efficiency = directional_price_change / |signed_flow|
```

- 买流增加但上涨效率下降：供应/吸收增强或追涨衰竭候选；
- 卖流增加但下跌效率下降：承接/空头衰竭候选；
- 少量流造成巨大位移：流动性真空，不自动等于强基本面共识；
- 冲击后很快回归：临时库存/流动性影响候选；
- 冲击后在新区域持续：信息重定价或结构迁移候选。

## 18. OI、资金费率、多空比、basis与清算联合分析

### 18.1 价格 × OI 基础四象限

| 价格 | OI | 首要候选 | 关键区分数据 |
|---|---|---|---|
| 上涨 | 上升 | 新风险进入、趋势仓位扩张 | spot flow、funding、basis、账户/持仓比 |
| 上涨 | 下降 | 空头回补、去杠杆上涨 | short liquidation、spot承接、回补后延续 |
| 下跌 | 上升 | 新空头、对冲增加或多空共同加仓 | funding、basis、spot/derivative分化 |
| 下跌 | 下降 | 多头平仓/强平、整体去风险 | liquidation、spread、卖流衰竭和恢复 |

OI相等的多空两端不表示双方力量相等：持仓成本、杠杆、止损位置、资金约束和主动成交权决定短期脆弱性。

### 18.2 funding与basis的解释

funding分析至少区分：

```text
current rate
predicted/next rate
historical percentile
duration at extreme
price path during extreme
OI and basis change
cross-venue dispersion
```

高正funding可能表示持续多头需求，也可能表示晚期拥挤；负funding可能表示空头拥挤，也可能因现货/永续套利产生。极端程度本身不提供反转时点。

basis需要检查到期、资金成本、借贷、稳定币和venue风险。正basis可以来自融资需求和套利结构，不等于所有参与者看多。

### 18.3 多空比的三种人口

```text
account ratio  = long accounts / short accounts
position ratio = long notional / short notional under provider scope
taker ratio    = aggressive buy volume / aggressive sell volume
```

少数大户与大量小账户可以让账户比和仓位比方向相反。taker ratio描述成交发起，不描述交易后总持仓。三者冲突时不是“数据错误”，而是人群规模、资金规模和当前流动行为不同。

### 18.4 清算链

```text
价格冲击
→ 保证金恶化
→ 强平/减仓
→ 主动成交增加
→ depth消耗、spread扩大
→ 进一步价格冲击
```

这是正反馈候选。判断强平接近尾声时，应寻找清算强度、OI下降速度、卖出impact和spread是否同步衰减；不能仅因出现大额清算就自动抄底。

## 19. 人群分布、成本、约束、心理与博弈

### 19.1 人群不是“机构/散户”二分法

市场分析至少考虑以下行为群体；同一主体可以同时属于多个群体：

| 群体 | 主要约束 | 常见行为候选 | 需要的区分观察 |
|---|---|---|---|
| 前期套牢多头 | 成本位、时间和回撤 | 反弹解套、降低风险 | 成本密集区的卖流和价格接受 |
| 低位抄底者 | 快速利润、紧止损 | 反弹兑现、低点破坏时退出 | 低位成交分布和回撤承接 |
| 趋势多头/空头 | 延续和波动预算 | 突破参与、移动保护 | 趋势效率和回撤结构 |
| 高杠杆多空 | 保证金、funding、清算 | 被迫减仓、挤压 | OI、funding、liquidation |
| 做市/流动性提供者 | 库存、spread、逆向选择 | 补单、扩大spread、短时反转 | order lifecycle与恢复性 |
| 套保者 | 现货/业务风险 | 单腿方向与真实观点不一致 | 相关腿和正式业务分类 |
| 基差/跨venue套利者 | 价差、资金、转移 | 多腿同步、价差收敛 | spot/perp/futures与venue网络 |
| 被动/再平衡资金 | 时间窗、权重规则 | 开收盘集中流 | 指数和再平衡日历 |
| 事件驱动资金 | 预期差和催化时钟 | 事件前布局、发布后退出 | 事件时间线和价格接受 |
| 发行方/内部人/操纵者假说 | 融资、声誉、持仓、监管 | 护盘、派发、叙事引导候选 | 申报、公告、链路和异常行为证据 |

最后一行可以存在，而且可能对提前规划有价值；但在没有公开证据时必须标为主体不可验证假说，不能因为价格路径命中就升级为身份事实。

### 19.2 人群状态卡

每个会改变动作的人群假说至少考虑：

```text
cohort label
estimated cost zone and construction
horizon / leverage / liquidity constraint
current unrealized PnL state
likely trigger and action
observable signature
strong alternative cohort
falsifier / expiry
confidence language and data gap
```

人群分布默认用序数语言：`主导候选 / 有意义 / 次要 / 不可区分 / UNKNOWN`。没有校准和覆盖完整的账户数据时，不输出伪精确百分比。

### 19.3 心理推导链

心理词只能放在下列链条末端：

```text
可观察事实
→ 成本/期限/杠杆约束假说
→ 约束下的可能动作
→ 情绪或动机proxy
→ 下一项区分观察
```

示例：

```text
上方历史成交密集
+ 多次反弹到该区主动卖流增加
+ 价格未能接受该区域
→ 前期持仓者存在减仓约束的假说
→ 逢高解套/降低风险
→ “饥渴解套”心理proxy
→ 若放量站稳且卖出impact衰减，则假说削弱
```

### 19.4 恐慌、贪婪、犹豫和共识代理

| 心理proxy | 需要的联合签名候选 | 重要替代 |
|---|---|---|
| 恐慌/被迫退出 | 卖出加速、spread扩大、depth撤退、OI下降、清算增加 | 新信息理性重定价 |
| FOMO/贪婪 | 注意力扩散、主动买入、杠杆扩张、高位接受 | 套保、套利或薄盘口 |
| 犹豫 | 双边高换手、位移有限、方向频繁反转 | 做市库存平衡 |
| 解套需求 | 成本区附近重复供应和上冲失败 | 基本面卖方或被动流 |
| 过度共识 | 仓位、funding、叙事同向极端且冲击效率下降 | 强趋势仍在价格发现 |

心理proxy不是对个人内心的测量，而是对可观察约束和行为的压缩描述。

### 19.5 机构护盘、吸筹和派发假说的标准写法

允许写：

> 机构/公司相关方可能在关键区域维护价格、吸收供应或借事件创造对手盘；若该假说成立，预期将观察到区域内反复承接、下破迅速收回、事件窗口放量上冲后高位供给增加。

同时必须写：

- 当前是否存在申报、公告、已知地址、连续盘口或跨venue证据；
- 做市库存、自然套牢盘、套利、被动再平衡等强替代；
- 哪些路径只支持“区域有人承接”，哪些证据才能进一步支持“特定主体”；
- 基于该假说的交易如何在主体判断错误时仍有有限损失；
- 到期或反证是什么。

## 20. 信息真值、受众行为、情绪传播与反身性

### 20.1 信息的七层拆解

```text
1. truth        内容是否真实、正式、已生效
2. novelty      相对市场已知信息是否新增
3. expectation  相对事前共识是否超预期/低预期
4. reach        谁在何时接收到
5. interpretation 不同群体如何理解
6. positioning  信息发布前市场如何持仓
7. reaction/acceptance 价格、量、流和持仓是否接受新状态
```

“利好”只描述内容方向，不自动给出订单方向。利好已定价、持仓过度拥挤或用于兑现时，价格可以下跌；利空同理。

### 20.2 事件生命周期

| 阶段 | 核心问题 | 数据 |
|---|---|---|
| 预期形成 | 市场原本期待什么 | 预期调查、价格、期权、叙事 |
| 事前布局 | 谁可能提前承担风险 | 价格、量、OI、basis、IV |
| 正式发布 | 原文、时间、修订和生效 | 官方源、available_at |
| 初始反应 | 第一批订单如何响应 | trades、book、短周期价格 |
| 传播扩散 | 更多受众如何解释 | 新闻、搜索、公开社交proxy |
| 价格接受 | 是否建立新价值区 | 结构、volume、flow、OI |
| 衰减/反转 | 信息影响是否耗尽 | 动量、冲击效率、回到旧区 |

### 20.3 好消息不涨、坏消息不跌

好消息不涨的竞争解释：已经定价、获利了结、套牢盘供应、利好质量不足、其他利空占优、流动性撤退、派发假说。

坏消息不跌的竞争解释：已定价、空头拥挤、卖压被吸收、信息可信度不足、其他利好占优、护盘假说。

价格反应是信息链的一部分，不是对真值的终极裁决。

### 20.4 错误叙事与自我实现

错误信息也可能产生真实订单。Agent可以建立：

```text
叙事出现
→ 信者追随 / 怀疑者反向 / 知假者顺势 / 做局者派发
→ 流动性和价格改变
→ 更多注意力与止损触发
→ 叙事暂时自我实现或反转
```

该机制只用于识别、风险规划和合法研究。不得把制造、传播虚假信息或操纵对手盘写成可执行策略。

### 20.5 关键位的反身性

整数位、前高低、成本密集区和公开技术位可能因为大量参与者共同关注而产生真实订单。反复测试既可能增强可见性和自我实现，也可能消耗原有流动性。Agent必须同时保留“支撑强化”和“支撑耗尽”两条路径，并用反弹效率、成交、深度恢复与价格接受区分。

## 21. 基本面、宏观、跨资产与多venue传导

### 21.1 传导链而不是关键词映射

宏观或基本面信息进入目标价格前，至少经过：

```text
正式事实/预期差
→ 现金流、贴现率、融资或供给含义
→ 受影响资产和期限
→ 相关市场的已有持仓
→ venue、时段和流动性
→ 目标标的订单与价格接受
```

“降息利好风险资产”“非农利好公司股价”等只能是第一层候选映射。Agent必须说明中间环节、适用期限和替代传导。

### 21.2 基本面支持、技术支持和流动性支持

| 支持类型 | 来源 | 失效方式 |
|---|---|---|
| 技术/可见性支持 | 前低、整数位、公开形态 | 共识改变或反复测试耗尽 |
| 成本支持 | 大量历史成交/持仓成本 | 持仓者认亏或结构迁移 |
| 流动性支持 | 显示/隐藏买盘与补单 | 报价撤退或资金耗尽 |
| 基本面/估值支持 | 现金流、资产权利、供给 | 基本面、贴现率或权利改变 |
| 政策/发行方支持假说 | 回购、承诺、干预或维护动机 | 无执行、资金不足、监管约束 |

一个区域可以同时拥有多种支持，也可能只有自我实现的技术可见性。不能把“没有基本面支持”直接等于“马上跌破”，只能表示该支持对信息冲击可能更脆弱。

### 21.3 跨资产与venue确认

跨资产分析至少检查：

- 同一风险因子的理论传导是否清楚；
- rolling beta/相关是否在当前窗口稳定；
- 相关变化是共同信息还是一方领先；
- 不同市场是否同时开市；
- 数据是否同币种、同时间和同收益口径；
- 代币、现货、永续、期货和底层股票的basis是否可交易；
- 某venue异常是否被其他venue接受。

相关同步可以支持共同因子，不能单独证明具体因果。

## 22. 数据相互影响、可推导关系与组合语义

### 22.1 依赖图

```text
PRICE_ACTION
├─ return / trend / RSI / MACD / ATR / K线形态
├─ 与 volume → VWAP / profile / relative volume
├─ 与 trades/book → CVD / OFI / impact / resiliency
├─ 与 OI/funding/basis → leverage/crowding hypotheses
├─ 与 event facts → surprise/reaction/acceptance
├─ 与 cross asset → beta/correlation/relative strength
└─ 与 participant proxies → cost/constraint/cohort hypotheses
```

可推导关系必须满足：输入实际存在、公式透明、时间对齐、单位一致。行为与主体只能从这些关系生成假说，不能作为确定性派生字段。

### 22.2 联合状态矩阵

下表是候选语义库，不是固定信号表：

| 联合观察 | 主候选 | 强替代/区分观察 |
|---|---|---|
| 价涨、量增、OI增、主动买增强、funding温和 | 新风险进入并推动趋势 | 套保/套利腿；看spot同步、basis和高位接受 |
| 价涨、OI降、空头清算增 | 空头回补/去杠杆上涨 | 新现货需求是否在清算后继续 |
| 价涨、OI增、funding极端、上涨效率下降 | 晚期多头拥挤和脆弱性候选 | 强趋势仍可能延续；看回撤承接和清算敏感性 |
| 价跌、量增、OI增、funding转负 | 新空头或对冲扩张 | 看spot卖流、basis、跨venue同步 |
| 价跌、OI降、多头清算、spread扩大 | 多头强制退出/恐慌proxy | 强平尾声还是结构继续破坏 |
| 价平、高量、单边主动流、位移小 | 吸收/大规模换手 | 吸筹、派发、做市或对冲；等待突破与恢复 |
| 价平、OI快速增、funding走极端 | 杠杆在窄区间积累 | 只提示未来扩张风险，不给方向 |
| 突破、量弱、OI平、快速收回 | 缺少接受/假突破 | 低流动时段或数据缺口 |
| 突破、量增、OI增、回测守住、flow恢复 | 新区域接受候选 | 事件短暂冲击；看多周期持续 |
| 利好、放量上冲、收盘弱、卖flow增强 | 已定价/获利了结/sell-the-news | 派发假说需主体或持续供应证据 |
| 利空、卖流放大但价不跌、深度补回 | 坏消息吸收 | 临时护盘/做市；看后续接受 |
| 支撑反复测试、反弹递减、恢复变慢 | 支撑流动性耗尽 | 卖方枯竭；看下破是否被接受 |
| RSI超卖、卖流/OI/清算仍扩张 | 下跌动能仍在，反转未确认 | 关注冲击效率何时下降 |
| RSI背离、卖流衰减、下破收回、OI清洗 | 反转/均值回归候选增强 | 高周期下降趋势仍可恢复 |
| 注意力暴增、成交/OI扩张、价不再前进 | 叙事拥挤/派发风险候选 | 新信息可能仍在消化 |

### 22.3 冲突不投票

当价格、量、flow、OI、funding和消息冲突时：

1. 检查它们是否回答不同horizon；
2. 检查时间、venue和合约是否对齐；
3. 识别账户数、资金规模和主动成交是否属于不同人口；
4. 检查重复依赖，避免RSI、MACD、均线三票压过一份OI事实；
5. 将冲突改写成两条会产生不同下一观察的路径；
6. 若仍不可区分，保留歧义并调整行动几何。

## 23. RSI、多周期技术指标与经验参数

### 23.1 RSI的含义

```text
RS = average_gain_n / average_loss_n
RSI = 100 - 100/(1+RS)
```

RSI压缩的是最近收益方向与幅度。它不测量真实买卖人数、订单簿、持仓或基本面。

### 23.2 状态化使用

| regime | RSI超买候选含义 | RSI超卖候选含义 |
|---|---|---|
| 强上涨 | 趋势强度、继续高位运行 | 回撤重置候选 |
| 强下跌 | 反弹重置候选 | 跌势强度、可持续低位运行 |
| 可重放区间 | 上边界衰竭候选 | 下边界衰竭候选 |
| 转换/事件 | 参数意义不稳定 | 参数意义不稳定 |

超买不自动做空，超卖不自动做多。Agent至少联合结构位置、量能、flow、波动、OI/funding（若有）和后续收复/失守。

### 23.3 多周期路由

```text
1D/4H RSI  → 背景动能和状态
1H        → 决策周期的衰竭/重置
15m/5m    → 触发与失效，不改写高周期事实
```

高周期下降、低周期超卖可以支持短反弹路径，同时保留高周期继续下跌。不同周期冲突并非错误，而是持有期限不同。

### 23.4 拐点、斜率、背离和failure swing

- RSI斜率变缓：近期动能衰减候选，不等于方向反转；
- 价格创新低而RSI未创新低：卖压效率下降候选；
- 背离只有在结构位置、窗口固定和后续触发明确时才可使用；
- failure swing等形态必须给出客观构造和相邻参数敏感性；
- 未闭合周期的RSI不得伪装成确认信号。

### 23.5 用户经验参数的地位

下列规则保留为 `USER_VALIDATED_HEURISTIC_CANDIDATE`，不删除：

- 震荡目标可参考区间约80%位置；
- 反向RSI关键点附近可构造保护区；
- 趋势行情中止损区可考虑压缩至波动区间约3%–5%；
- 单笔压力风险可参考总仓位2%以内；
- 非震荡状态需要重估超买/超卖阈值。

使用条件：

1. 明确“80%、10%、3%–5%、2%”分别以什么分母计算；
2. 参数是仓位policy还是预测信号；
3. 在什么市场、周期、波动状态和费用下形成；
4. 相邻参数是否改变结论；
5. 若结构失效与固定百分比冲突，Agent如何裁决；
6. 作为用户验证经验进入案例和前瞻比较，不冒充跨市场常数。

## 24. 标准市场分析流程

### 24.1 Cold完整分析

```text
1. 识别标的、合约、venue、时段、cutoff和horizon
2. 列实际数据覆盖、质量、时效与UNKNOWN
3. 建立结构/决策/触发三个功能周期
4. 判断趋势、区间、转换、波动和关键区域
5. 读取K线位置、相对量与后续接受
6. 若有微观数据，分析flow、depth、impact和恢复
7. 若有衍生品数据，分析OI、funding、basis、ratio和清算
8. 若有事件，拆分真值、预期、受众、持仓、反应和接受
9. 建立成本/期限/杠杆人群和心理proxy
10. 生成主机制、强替代、OTHER和不可观测主体假说
11. 形成带顺序、触发、加速/衰减、反证和期限的路径树
12. 读取上一StrategicEpisodeState与ReferenceExposureState，区分战略观点和当前风险
13. 比较WATCH/WAIT/PROBE/OPEN/HOLD/ADD/REDUCE/HARVEST/CLOSE/REENTER/HEDGE/OTHER
14. 形成TargetExposureState、PositionDelta与角色/tranche计划
15. 设计entry、stop、targets、runner、风险预算和参考执行意图
16. 检查决策相关delta、无交易区、数据降级和产品特有风险
17. 指定最有信息价值的下一观察、re-arm条件与review时间
18. 封存完整原文，不为结果修改
```

### 24.2 Delta增量分析

Delta不重新朗读全部手册，只回答：

- 哪些新事实已闭合并合法可用；
- 哪些测量、状态、人群约束或事件阶段真正变化；
- 哪条假说强化、削弱、过期或被替代；
- strategic episode是否改变，原/目标敞口与PositionDelta是什么；
- 是否越过无交易区，还是只需观察或review；
- 原动作、仓位、风险预算和机会成本是否改变；
- 新的下一观察是什么。

### 24.3 Event分析

事件分析必须读取事前原决策和当时预期，随后依次比较正式原文、初始反应、传播、持仓变化与价格接受。不能用事后价格重新定义“市场原本预期”。

### 24.4 建议的可读决策结构

这不是封存schema，但可用于训练：

```text
市场身份与数据覆盖
事实与透明测量
多周期结构和关键区域
量价/微观/杠杆/事件联合状态
参与者与心理竞争假说
主路径、替代路径、OTHER
触发、里程碑、软反证、硬反证、expiry
StrategicEpisodeState与当前ReferenceExposureState
目标敞口、PositionDelta、角色/tranche和风险预算
最终参考动作、entry/stop/targets/runner/reentry
ExecutionIntent、actionability、机会成本和下一review
```

## 25. 经验规律、教学、技能与持续学习

### 25.1 经验规律登记卡

```text
rule_id / natural-language rule
origin: user case | literature | forward review | community
market / venue / instrument / horizon / regime
required observations and dependency families
mechanism and strong alternatives
activation / expected path / falsifier / expiry
action implication and risk geometry
parameter sensitivity and costs
supporting cases / counterexamples
status: CANDIDATE | USER_VALIDATED | MIXED | WEAKENED | RETIRED | NOT_EVALUATED
```

`USER_VALIDATED`表示用户报告该规则或方向在其案例中经市场结果验证，不等于独立复现或普适有效。

### 25.2 Review分解

Outcome后分别评价：

1. **状态**：趋势、区间或转换判断是否有用；
2. **机制**：哪些观察支持/反对机制，主体身份是否仍不可验证；
3. **路径**：顺序、里程碑、反证和时间是否合理；
4. **动作**：提前规划是否利用了路径；
5. **仓位**：风险、加减仓、止盈、runner是否匹配；
6. **时机**：触发是否过早、过晚或未出现；
7. **机会成本**：WAIT和未选动作后来怎样；
8. **学习**：保留、弱化、扩充或退休什么候选。

路径命中可以证明路径规划有用；动作获得更好结果可以证明当时规划有决策价值；二者都不能在缺少主体证据时单独证明“某机构确实按所述意图操作”。

### 25.3 技能梯度

| 等级 | 能力 |
|---|---|
| S1 事实识别 | 不混淆标的、时钟、OHLC、成交量、成交额和人数 |
| S2 结构测量 | 能稳定识别周期、区域、波动、量价和参数敏感性 |
| S3 联合分析 | 能连接flow、liquidity、OI、funding、event和cross-asset |
| S4 人群博弈 | 能从成本和约束建立多群体竞争假说，不把读心当事实 |
| S5 路径与动作 | 能生成可反驳路径、提前计划动作和独立tranche风险 |
| S6 动态仓位 | 能区分episode、当前/目标敞口、delta、角色、风险预算和执行意图 |
| S7 动态转换 | 能在新事实、无交易区、数据降级和冲突中管理加减仓/退出/再入场 |
| S8 点时学习 | 能在无后见之明下区分市场、动作、仓位、转换、执行与风险错误 |

### 25.4 教学案例的用途

教学案例必须保留原始判断、当时数据边界和后来Outcome三者分离。案例用于学习“如何推导”，不是让Agent复制点位、参数或主体故事。V3.3.2 的首个案例见 [`08_SANDISK_USDT_TEACHING_CASE.md`](./08_SANDISK_USDT_TEACHING_CASE.md)。

### 25.5 市场手册完成但市场仍未评价

手册完整只证明分析对象、推导边界和技能路径更完整。是否比price-only提高预测、是否降低错误、是否改善动作和仓位，仍需使用同一cutoff、同一horizon和未来隔离的前瞻对照。文档完整、本地PASS、案例方向准确都不单独证明跨regime市场有效或成本后盈利。

## 26. 市场认知到动态交易的交接合同

市场分析不能直接跳到一个仓位数字。Agent 必须先把认知压缩为能约束动作、又不会伪装精确性的交接语义：

```text
Market-to-Position Handoff
  instrument/product/venue identity
  structural, decision and trigger horizons
  strategic state and local tactical state
  operational lead / runner-up / OTHER
  event-clock path and calendar expiry
  key zones and acceptance/rejection criteria
  activation / soft contradiction / hard invalidation
  next discriminating observation
  action-support ceiling
  critical data dependencies and degradation fallback
```

`action-support ceiling` 回答“当前证据最多支持到什么程度”，例如只支持观察、条件 probe、正常 CORE，或因数据/成本只支持减险。它是 Agent 的序数判断，不是系统根据 epistemic label 自动映射仓位。

### 26.1 多周期冲突的处理

多周期不是多数投票。Agent 需分开：

- **战略周期**：定义 episode 的主要命题、关键失效和最大持有窗口；
- **决策周期**：决定当前是否值得承担、维持或降低风险；
- **触发周期**：定位 activation、执行价带和局部保护；
- **执行观察周期**：只辅助参考执行，不得偷偷改变战略 thesis。

例如日线看空而15分钟出现超跌反弹，可以形成“战略 bearish CORE 暂不增加 + 条件 TACTICAL 多头 probe”，不能写成“短周期转多所以战略观点自动翻多”。若要反转，必须关闭旧 episode 并建立新 episode。

### 26.2 从分析证据到仓位的非机械关系

下列链条必须保留人工判断：

```text
evidence
→ market state
→ competing path
→ action geometry
→ risk budget
→ target exposure
```

更多指标共振不自动等于更大仓位；同源数据不能重复计票；故事更具体不等于证据更强。只有路径、失效、成本、预算和可撤销性共同成立，才构成增加参考风险的理由。

### 26.3 交接失败如何处理

如果分析能描述市场但不能给出 activation、invalidation、horizon 或关键数据依赖，它仍可作为 `RESEARCH_ACCEPTED/OBSERVATIONAL_ONLY` 封存并学习；系统不得补齐默认动作。只有 Agent 原文提供足够明确的 episode、目标敞口、风险和参考执行语义，才可标为 `REFERENCE_ACTIONABLE`。完整动态合同见 [`02_DYNAMIC_POSITION_MANAGEMENT.md`](./02_DYNAMIC_POSITION_MANAGEMENT.md)。
