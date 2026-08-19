# V3.2 用户建议审查与裁决

状态：`THIRD_REVIEW_RESOLVED / SEMANTICS_INCORPORATED_IN_V3_2_3_CANDIDATE / RUNTIME_STATUS_SEE_IMPLEMENTATION_LOG`

日期：2026-08-07

适用范围：V2.1、V3、V3.1/V3.1.1 与本次“去掉过度保守、增加动态和激进能力”的新增要求。本文只裁决理论与系统方向，不授权 paper/live、账户、订单、凭据或资金，也不把研究动作计划当成交。

## 1. 总结裁决

用户指出的核心问题成立，但需要更准确地定位：

1. 当前体系把“事实不知道”“原因不知道”“未来不知道”“风险边界不知道”混成同一种 UNKNOWN，并过多导向 WAIT。这会让 Agent 在正常市场不确定性下失去小额试探、快速修正和机会捕获能力。
2. V3/V3.1 并非完全没有历史形态、完整动作、连续仓位、reentry 或 WAIT 机会成本；这些目标已经写入理论。真正失败的是：后继实验明确排除了 portfolio/reentry，正式动作又被压缩为 `OPEN_LONG/OPEN_SHORT/WAIT`，路径 UNKNOWN 不能支持任何新风险，导致理论目标和实验动作域不一致。
3. 正确的“激进”不是降低数据真实性、取消否证或把主观故事当事实，而是把不确定性从“一票否决”改成“影响试探风险、加仓速度、保护距离和复核频率”。风险是预算，不能继续充当默认否决权；但数据完整性、损失上界和权限仍是硬边界。
4. 历史形态、注意力、主观叙事和共同信念都可能通过订单、止损、获利盘和流动性产生价格影响，不能一棍子打死；但必须把“某叙事是否真实”和“多少人相信并据此交易”拆成不同假说。
5. 用户给出的月度/年度收益区间、参与者比例、固定百分比移动止损和 RSI 固定高优先级没有当前前向证据，不能进入事实层或收益承诺。它们可作为待比较的策略候选。

## 2. 用户对当前理论的概括：哪些准确，哪些不准确

| 用户概括 | 裁决 | 说明 |
|---|---|---|
| 不知道必须明确说不知道 | 采纳 | 这是认识论底线；但只有 `INTEGRITY_UNKNOWN/RISK_BOUNDARY_UNKNOWN` 强制禁止新风险，普通方向不确定不再自动 WAIT。 |
| 信息不能直接跳到动作 | 采纳 | 继续要求信息→行为传播→数据/状态→假说→路径→动作；允许快速，但不允许跳层。 |
| 先选动作再找理由被禁止 | 采纳 | 两阶段 proposal→sealed evaluation→selection 保留。 |
| 系统只会保命、默认永远 WAIT | 部分准确 | 旧运行确实出现过度 WAIT 和过早全平；但 V3 已包含完整动作域、机会成本、连续仓位与 reentry 目标，问题是没有接到当前实验。 |
| 原理论永远固定 2% 仓位 | 不准确 | V2.1/V3 的目标是风险预算、费用、滑点、保证金、流动性和动作尺度复算；旧纸面配置曾有固定/轻仓参数，但不能代表最新理论的唯一仓位规则。 |
| 原理论鄙视历史形态 | 不准确但暴露表达失败 | V2.1 已有历史相似层、结构、pivot、区间、突破/补回和 RSI 候选；它禁止的是把形态直接当因果或订单。V3.2 会把反身性磁区提升为一等假说，以免“谨慎表述”被实现成“不使用”。 |
| 只有条件全部确定才能入场 | 需要纠正 | 市场不可能确定。新规则允许 `ANTICIPATORY_PROBE`：只要事实真实、损失边界明确、几何有利且动作可撤销，就可在机制未确认时小额试探。 |
| 最终选择后立即执行 | 当前范围拒绝 | 当前授权仅公开数据、本地、不可执行；最终选择只能成为研究动作计划。真实或纸面执行须有独立权限、账户真值和执行合同。 |

## 3. 历史形态与“磁区”

### 3.1 采纳的部分

价格历史不是神秘图形，而可能是参与者协调装置：前高前低、整数位、成交密集区、期权执行价、反复测试区附近可能聚集限价、止损、止盈和清算风险。Osler 对外汇订单的研究记录了止损/止盈在整数位附近聚集，并给出“关口前反转、越过后加速”的微观结构解释；Lo、Mamaysky 与 Wang 也证明某些自动识别的技术形态在其样本内包含条件分布增量。它们支持把形态变成可检验候选，不支持任何形态跨资产、跨时期必然盈利。

V3.2 因此新增 `ReflexiveLiquidityZone`，它是带宽度、来源、形成时间和失效条件的区域，不是事后画出的单点。来源可包括：

- past-only swing high/low、range boundary、gap/imbalance；
- 成交量分布和停留时间；
- 整数位与重复触碰；
- 多交易所价格/深度一致性；
- OI、funding、清算代理和期权 strike（若点时可得）；
- 当前盘口只能作为短寿命证据，不能反推长期挂单。

### 3.2 必须同时存在的竞争解释

同一位置被连续测试，至少有四条合法路径：

1. `ZONE_REJECTION`：防守挂单、止盈和反向交易仍足以拒绝价格；
2. `ZONE_ABSORPTION_BREAK`：连续测试消耗可见/隐藏流动性，压缩后突破；
3. `FALSE_BREAK_REVERSION`：触发止损后缺少持续主动流，价格重新回区间；
4. `ZONE_NO_EFFECT_OTHER`：该位置只是叙事锚，没有稳定作用。

所以“冲击越多卖盘必然越厚”和“冲击越多卖盘必然被吃完”都不能预设。触碰次数采用边际递减；必须同时观察反应幅度、回撤深度、成交/主动流、OI/资金费、波动压缩与跨市场确认。

### 3.3 术语纠正

没有点时的期权 dealer gamma、执行价集中和净方向证据时，突破加速只能称 `STOP_OR_LIQUIDATION_CASCADE`，不能称 `Gamma Squeeze`。永续/现货的止损和清算踩踏与期权 gamma 对冲是不同机制。

## 4. 主观假说、群体信念和数值权重

### 4.1 采纳的部分

主观叙事可能即使事实错误也影响价格，但前提是它被足够多、有交易能力或受约束的参与者相信并转化为订单。媒体悲观、搜索注意力和显著新闻与交易量/投资者买入行为之间存在文献证据；这支持分析注意力和受众反应，不支持从一条帖子直接推断“主力跑路”或精确方向概率。

每个叙事必须拆成四个不同对象：

```text
truth_support_tier             叙事本身为真的序数支持档位
audience_adoption_tier         相关人群相信它的序数档位
behavior_translation_tier      相信后采取买卖/观望行为的序数档位
price_impact_tier              这些行为在当前流动性下推动价格的序数档位
```

### 4.2 序数方式的修正采纳

`0..100` 主观分值及其线性、求和、归一化风险映射永久废止，不保留兼容别名。Agent 只可提交 `EXTREME_UNCERTAINTY/LOW/HIGH`：分别表示当前方向风险为零、只允许离散 probe 上限、可使用正常的预冻结参考上限。它们不是事件概率、胜率、证据覆盖或校准输出。

- 每次档位迁移必须记录新的当前 PIT 证据、反证、依赖组、旧/新档位和 expiry；
- 非终局档位只允许相邻迁移，硬证伪直接终止行动资格；
- 多个 cluster 不扩大总包络，只以 `0/1/2` 离散 tranche 单位切分既有预算；
- 不进入 Brier/ECE、未经验证的 EV、账户百分比或连续插值；
- 确定性系统校验事实绑定、机制差异、去重和变化链，但不替 Agent 编故事或指定主观档位。

最终方案只允许 `EXTREME_UNCERTAINTY/LOW/HIGH` 三档，旧字段及兼容别名均须拒绝。每个方向性假说仍须有反向竞争解释，集合保留 `OTHER/UNKNOWN`；这项义务用于证伪，不构成必须下注。引用同一价格变化、同一新闻或同一成交增量的假说必须共享 dependency group，不能因改写故事而重复获得风险。

### 4.3 用户分仓示例的纠正

权重 `14,5,18,13,21` 合计为 71。第一版若直接把完整 5% 归一分完，会得到约 `0.986%,0.352%,1.268%,0.915%,1.479%`，这正是分母陷阱：即使绝对支持很弱，也会机械吃满 5%。第一版进一步把 `71/100` 乘入 reference risk，并得到下列分配；该连续算术现已作为反例废止：

```text
0.70, 0.25, 0.90, 0.65, 1.05 reference-risk units
```

但真实情形中不能这样直接分配：

- 用户后文把第三个 `18` 写成 `8`，需视为示例笔误，不能进入合同；
- 相同方向、相同证据和相同失效位的五个假说不是五笔独立优势；
- 不同止损距离下，相同名义对应完全不同的最大损失；
- 应分配的是 `worst-case risk budget`，名义和数量由失效距离、费用、滑点、跳空/尾部缓冲反推。

最终 V3.2 不把这些数解释成账户名义、概率或风险份额。当前 pilot 的 raw reference envelope 固定为 `1`，Agent 无权输入账户百分比；最高主观档位只能把总包络限制为 `0/0.5/1`，多个 cluster 不扩大包络。确定性系统先合并同依赖，再以离散 `HIGH=2/LOW=1/EXTREME_UNCERTAINTY=0` tranche 单位切分已经缩放的预算；LONG/SHORT 对立分支不相加，也不机械制造五笔重复计划。未来账户名义和数量只有在另行授权后，才能由客观账户风险、失效距离、费用、滑点及尾部压力共同反推。

## 5. 早期试探、猜底摸顶和金字塔加仓

### 5.1 方向采纳

把主要入场从“最终确认后追价”改为四种并列模式：

1. `ANTICIPATORY_PROBE`：在磁区、衰竭或非对称几何处先行小额试探；
2. `REACTION_ENTRY`：观察到预期反应后进入；
3. `BREAK_ACCELERATION`：15 分钟越过关口并出现主动流/波动扩张时抢突破；
4. `RETEST_OR_REENTRY`：突破回测、退出后重新满足条件时进入。

试探不是无依据猜测。它必须至少拥有：真实且新鲜的价格/合约/成本数据、明确失效位、压力测试后的损失上界、流动性可接受和一个有反向假说的机会对象。原因仍可 UNKNOWN。

### 5.2 金字塔加仓的约束

采纳“先试探、后加仓”，但加仓条件不是“已经盈利”这一项：

- 必须出现新的、点时可得且非重复证据；
- 原假说没有 hard falsifier；
- 新 tranche 按当前价格重新计算收益空间和失效距离；
- 加仓后组合压力损失仍在原机会风险上限内，或由已经锁定的净收益释放风险预算；
- 不允许在原 thesis 亏损时用同一 ID 摊平；新的均值回归机会必须有新 episode 和独立预算。

“用市场赚来的钱”不是正确会计概念：浮盈属于账户权益，回撤仍是损失。只有在计入费用、滑点和跳空压力后，由可执行保护位锁定的 `LockedNet` 才能释放部分风险预算；移动到成本也不能保证零亏损。

## 6. 多时间框架与速度

采纳“首轮慢、后续快”，但不采用绝对方向禁令：

- 首轮或事件变化时重建宏观、规则、日线/4H regime、跨市场和慢频信息；
- 后续 15 分钟轮只处理新闭合 bar、盘口/成交/OI/资金费变化、注意力事件、轴变化和假说 delta；
- 每个缓存对象有 `as_of/available_at/expires_at/invalidation_event`；过期不能沿用；
- 日线只形成方向先验、风险不对称和禁区候选，不规定“日线上涨绝不做空、下跌绝不做多”；
- 逆高周期方向的 15 分钟试探使用更小风险、更短期限和更快否证；顺方向则允许更高的加仓上限，但仍要重新计算几何。

限价单不是天然安全或必然抢到第二波：它存在不成交、排队、逆向选择、晚到成交和行情跳过保护的问题。未来若获得执行权限，必须有 TTL、cancel/replace、late-fill reconcile 和保护 ACK；当前实验只生成条件计划。

## 7. RSI 的位置

采纳 RSI 作为短周期重要候选，但拒绝未经前向比较就固定为最高优先级：

- 只使用已闭合、点时可得、gap 合法的 RSI；
- 在趋势 regime 中，“超买/超卖”可能持续，不能直接反向；
- 合法角色包括：极值衰竭候选、背离、failure swing、趋势中的中轴重置、触发节奏和反证；
- RSI 可以改变假说支持和 probe 触发优先级，不能单独放大风险预算；
- 必须与无 RSI、RSI 仅 trigger、RSI 仅 filter、RSI+结构的同 cohort 基线比较。

现有 CORE v2.1 的 RSI-MTF-DRL-PM 已冻结 closed-bar、gap、availability、方向独立和对照要求，V3.2 复用这些不变量，不另造一个随意指标实现。

## 8. 动态止损、止盈和 reentry

### 8.1 采纳的部分

退出不应只靠固定目标全平。V3.2 同时维护：

- `STRUCTURAL_INVALIDATION_STOP`；
- `VOLATILITY_NOISE_FLOOR`；
- `TIME_STOP`；
- `EVENT_RISK_REDUCTION`；
- `LOCKED_NET_TRAIL`；
- `PARTIAL_HARVEST + RUNNER`；
- thesis 仍有效时的 `REENTRY_OBLIGATION`。

保护只能向减少风险方向移动，不能为挽救亏损而放宽。目标触达首先是管理事件，不默认终结整个 episode。

### 8.2 固定百分比规则的修正

`+3%→成本、+8%→+5%、+15%→+10%` 可作为一个预注册候选，但不能跨 BTC、山寨币、股票和不同周期通用。更稳妥的共同尺度是 `R`、ATR/实现波动、结构距离和压力成交成本：

- 到达某个 `R` 或结构里程碑后，比较减仓、收紧和继续持有；
- 新 stop 必须在市场噪声外且不超过剩余风险上限；
- 对强趋势允许 runner，避免固定止盈重复造成旧实验的延续损失；
- 对震荡/均值回归 regime 更早收获，但必须把换手和成本计入。

止损规则的价值本身依赖价格过程。Kaminski 与 Lo 的分析表明，在随机游走假设下止损会降低预期收益，而在动量环境中可能增加价值；这直接反对“一组固定移动止损永远更优”。

## 9. 收益估计与“理论必须赚钱”

“理论必须以成本后盈利为最终目标”采纳；“没有历史/前向证据即可估算每月和每年收益分布”拒绝。

用户给出的牛市、熊市、震荡、黑天鹅月度区间，以及年化 `+15%~+25%`，没有绑定：

- 标的、方向权限、杠杆和现金基准；
- 交易频率、成交模型、费率、funding、滑点和冲击；
- 胜率、盈亏比、序列相关、尾部和 regime 占比；
- 前向、未见数据或置信区间。

因此它们只登记为 `USER_INTUITION_UNVERIFIED`。既有旧纸面实验确实观察到固定止盈错失延续、退出后缺 reentry 和成本磨损，这支持修改机制，但不能外推新系统收益。

成本不能事后补扣。高换手常侵蚀个人投资者表现，实际交易成本和价格冲击也会显著改变策略可实现性；V3.2 必须把不成交机会成本、maker/taker、滑点、funding、晚到和冲击与毛收益同时报告。

## 10. V3.2 的最终取舍

### 采纳

- 正常市场不确定性下的小额先行试探；
- 结构磁区、突破加速度与反身性；
- 三档主观支持和方向相反假说；
- 当前/归因/预测/行为四类假说；
- 首轮慢、后续 15 分钟 delta；
- RSI 的 regime-aware 快速触发角色；
- 证据加仓、动态减仓、partial harvest、runner 和 reentry；
- WAIT 的真实机会成本和行动不足惩罚。

### 修正后采纳

- 概率分仓→非校准三档支持、相关性去重和固定总包络内的离散 tranche 分配；
- 猜底摸顶→有失效位和非对称几何的 anticipatory probe；
- 利润加仓→新增证据、重新计算几何和总压力风险后的金字塔；
- 移动到成本→考虑费用、滑点、跳空和噪声后的 LockedNet/结构保护；
- 日线定方向→高周期先验和风险不对称，不设绝对禁令；
- Gamma Squeeze→没有期权 gamma 证据时改称 stop/liquidation cascade。

### 拒绝成为硬规则

- 未经验证的月度/年度收益承诺；
- “60% 交易者关注某位置”等无来源比例；
- RSI 永久最高优先级；
- 相同方向的相关假说按文字数量重复加仓；
- 浮盈不是本金、移动止损必然保本；
- 固定 `3/8/15%` 跨市场移动止损；
- 当前 public-only 实验中的立即下单或真实账户封存审查。

## 11. 第二轮五项问题的裁决

### 11.1 流动性幻觉

**问题成立，但第一版 V3.2 已部分覆盖。** 原文已经要求 zone 同时存在 rejection、absorption/break、false-break 和 no-effect 四条路径，也已禁止把参与者身份当事实；缺失的是“同一个假突破/流动性事件如何同时修改相关假说、入场、保护和再入场”的 typed 横切对象。

新增 `ExternalPathModifier` 放在路径层而非方向概率云。它必须绑定 zone、source 和 dependency group，只能修改相关对象。这样既避免为每个“插针/收割”故事另造假说，又不允许一句“主力可能骗线”成为可以任意解释任何结果的万能借口。假突破退出后由新 reentry tranche 重新立项，旧止损和旧记录保持不变。

### 11.2 权重分母陷阱

**这是第一版公式中的真实 P0。** 仅用 `R_c=B_t·W_c/ΣW` 时，一个 `10/100` 假说会拿走全部 `B_t`；随后引入 `S_d=min(1,ΣW_c/100)` 仍然只是让另一组连续主观数字控制风险，并未消除伪精确。两套公式均已废止。

最终合同只有 `EXTREME_UNCERTAINTY/LOW/HIGH` 三档：先由最高档把固定 reference envelope 限制为 off/probe/normal，再用离散 tranche 单位切分该既有包络；多个 cluster 不扩大总额。覆盖只作可重放诊断，regime、流动性、成本和 geometry 只作 typed hard gate。LONG/SHORT 竞争解释必须存在并不意味着两侧必须有正风险或开仓资格；系统不得为了避免空集合而伪造方向。

### 11.3 长期无动作

**WAIT 机会成本已经存在，但缺少耐久的休眠监督。** 新增两只互不替代的时钟：风险计划时钟只由合格且有正风险预算的 probe/reentry 重置；模型适应时钟只由新鲜 PIT 证据绑定的实质性状态、区域、假说或阈值变化重置。任一达到预注册阈值即触发 `INACTIVITY_REVIEW`，强制重检 regime、数据覆盖、TTL、阈值和 shadow baselines，并产生只对未来有效的新候选。

拒绝“为了验证模型而必须用真实风险开仓”。即使不交易，前瞻假说、条件计划、终点方向覆盖和基线差异仍能生成验证样本；MFE/MAE 只有在事前冻结并取得完整 horizon 内路径后才能计算。强制仓位反而把研究需要变成财务风险。通胀或闲置现金成本只有在可投资基准和计价合同冻结后才可量化。

### 11.4 API、网络与交易所故障

**费用、滑点和 gap 已部分存在，stop-not-fill 与 venue failure 需要显式补齐。** 当前实验没有执行权限，所以不会声称修复真实 API；它只会预注册 stop-through、未成交、限频、网络中断、保护未 ACK 和交易所不可用的压力分支，且公开价格触及不等于成交。

未来执行系统即使增加幂等订单 ID、ACK 状态机、reduce-only/market fallback、对账、断线恢复和 circuit breaker，也无法保证交易所整体故障期间退出。因此真正不可定义的尾部损失必须成为 `UNKNOWN_MAX_LOSS`，而不是假装固定止损已经封顶。

### 11.5 假说过期与路径依赖

**`expires_at` 已经存在，但“到期后如何续期”未闭环。** 新规则是到期立即失去支持新风险的资格，并撤销依赖它的未触发计划；若要继续，必须创建绑定旧摘要/旧 expiry 的新 revision，提供新 evidence 并重检 regime、zone、falsifier 和 horizon。只改时间戳属于续期洗白。

用户建议的固定降权 50% 可作为前向比较 arm，但不适合作为所有宏观、15 分钟、事件和流动性假说的统一真理。更严格的通则是“过期先终止行动权，续期必须重新举证”；具体 TTL/衰减按类型预注册。

## 12. 主要学术依据与边界

- Lo, Mamaysky & Wang (2000), *Foundations of Technical Analysis*: <https://doi.org/10.1111/0022-1082.00265>
- Osler (2003), *Currency Orders and Exchange Rate Dynamics*: <https://doi.org/10.1111/1540-6261.00588>
- Moskowitz, Ooi & Pedersen (2012), *Time Series Momentum*: <https://doi.org/10.1016/j.jfineco.2011.11.003>
- Daniel & Moskowitz (2016), *Momentum Crashes*: <https://doi.org/10.1016/j.jfineco.2015.12.002>
- Kaminski & Lo (2014), *When Do Stop-Loss Rules Stop Losses?*: <https://doi.org/10.1016/j.finmar.2013.07.001>
- Moreira & Muir (2017), *Volatility-Managed Portfolios*: <https://doi.org/10.1111/jofi.12513>
- Tetlock (2007), *Giving Content to Investor Sentiment*: <https://doi.org/10.1111/j.1540-6261.2007.01232.x>
- Barber & Odean (2008), *All That Glitters*: <https://doi.org/10.1093/rfs/hhm079>
- Da, Engelberg & Gao (2011), *In Search of Attention*: <https://doi.org/10.1111/j.1540-6261.2011.01679.x>
- Sullivan, Timmermann & White (1999), *Data-Snooping, Technical Trading Rule Performance, and the Bootstrap*: <https://doi.org/10.1111/0022-1082.00163>
- Barber & Odean (2000), *Trading Is Hazardous to Your Wealth*: <https://doi.org/10.1111/0022-1082.00226>
- OKX, *API Guide*（订单接受不等于最终状态、订单状态/限频/WebSocket 断线语义）：<https://www.okx.com/docs-v5/>

上述工作提供可检验机制与实验设计灵感，不证明 BTC、15 分钟、RSI、磁区、金字塔或任一 Agent 规则在当前样本中有效。所有市场有效性仍须通过点时、前向、成本一致的比较获得。

## 13. 第三轮“易碎复杂性”五项复核（2026-08-08）

本轮发生在 V3.2 authority、qualification 与目标实验创建之前，因此可以修订尚未冻结的候选理论；正式实验继续为 `NO-GO`，直至本节 P0 进入理论、typed contract、Agent schema、runtime 与测试的同一闭包。此前第 4、10、11 节关于连续 `0..100` 主观权重直接缩放风险的裁决由本节取代。

### 13.1 连续主观权重：问题成立，旧修复仍有伪精确

把未校准主观值声明成“不是概率”，并不能消除它被线性乘入风险预算时的伪精确。当前实现仍会把 Agent 的任意整数差异变成仓位差异，也会在簇内按这些整数继续分配风险。这是新的 P0。

最终修正采用少数有序档位，而不是任意整数：

- `HIGH`：只表示证据条件允许使用正常的预冻结参考风险上限；它不能把客观上限放大；
- `LOW`：只允许较低的离散 probe 上限；
- `EXTREME_UNCERTAINTY`：方向风险为零，但仍保留观察、反证和条件路径；
- 升降档必须绑定新的当前 PIT 证据；跨周期采用滞回，禁止从极不确定一步跳到高确信；硬证伪直接终止行动资格，不用缓慢降档掩盖；
- coverage、流动性、几何、成本和最大损失仍分别形成客观上限，最终风险取这些上限与主观档位上限的最小值。主观判断只能降档或在合法候选间选择，不能创造风险容量。

档位到风险 cap 的固定表只是治理规则，不是市场概率、胜率或校准输出。正式审计记录档位、依据、反向解释和变化原因，不输出看似精确的主观百分比。

### 13.2 复杂性与 15 分钟时限：问题成立，但不能删除相关证据语义

当前完整本地分析链的聚焦回归虽然通过，但一次组合运行耗时约 `504` 秒；代码还会在每次 checkpoint 读取时重复读取全部工件并重放历史 acceptance。它证明“正确但关键路径过慢”是真问题。直接删除依赖闭包会重新制造同一价格、同一新闻或同一公共原因被多个假说重复计入风险的旧漏洞，因此不采纳。

修正采用控制面/数据面分离：

1. Cycle 1 计算并封存静态候选全集、高周期状态和完整依赖闭包；
2. Cycle 2–16 只处理新到证据、变化节点及其受影响子图；
3. 已接受的不可变前缀使用摘要绑定的验证缓存；首次进程读取、当前新 acceptance、显式审查和终态仍执行 owning full replay；任何物理 stat/摘要变化立即失效缓存；
4. Agent 接收完整语义所需的确定性 compact/delta view，原件继续 write-once 保存；
5. 冻结每阶段和总时限。超时只能进入 `DEGRADED/UNKNOWN/FAIL_CLOSED` 的预注册路径，不能删证据、绕过验收或后移 outcome。

因此要删除的是重复计算与重复传输，不是依赖关系、反证、UNKNOWN 或验收语义。

### 13.3 中性、混沌与无方向波动：问题部分成立

当前 Domain 已存在 `RANGE/VOLATILITY/NEUTRAL/OTHER/UNKNOWN`，所以“系统只有多空一对”不符合现状；反向假说的义务是可证伪性，不是下注义务。但 `regime_scope` 仍可用任意字符串，动作层没有机器保证混沌状态的当前方向风险为零，这部分是 P0。

修正增加严格 `MarketRegimeState`：至少覆盖 `TREND_UP/TREND_DOWN/NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN`。在无方向状态下：

- LONG/SHORT 仅能作为被阻断的条件观察路径；
- 当前方向风险预算为零；
- 可以记录上下突破触发、假突破和恢复条件，但本次不可执行实验不创建双边挂单；
- 若未来允许交易，双边突破单还必须有 OCO/cancel-race/late-fill/保护 ACK 的独立执行合同，不能由研究标签直接下单。

不采用“多空权重都低于 30 就判混沌”，因为最终系统已经没有连续 0–100 分值。`CHOPPY` 必须由频繁反转、方向延续性、成本磨损、结构边界和波动状态的 typed 证据判定；缺少这些证据时保持 `NEUTRAL/OTHER/UNKNOWN`，不能用一个阈值替代市场状态分析。

### 13.4 Reentry 磨损：问题成立

“新 tranche、新证据、新预算、不改写旧退出”只能防止历史洗白，不能限制同一失效簇在震荡中反复消耗风险。`ReentryObligation` 也容易被误读为必须再次入场。

修正增加耐久 `ReentryBudgetState`：每个 instrument 只有一套全局防磨损账本，绑定滚动 UTC 窗口、尝试数、连续失败数、累计参考风险、硬上限和 `cooldown_until`。当前 pilot 固定绝对 `24h` 窗口、最多两次 ledger 激活后的正风险再参与、累计 reference risk 不超过 `1`。ledger `INACTIVE` 时首次 `OPEN_PROBE` 不计；一旦激活，任一方向最终选中、合格且风险为正的 `REENTER/OPEN_PROBE/REVERSE` 都消耗同一本账。同向恢复规范化为 `REENTER`；真实反向可以保留 `REVERSE/OPEN_PROBE` 语义，但不得免费。方向、cluster、regime、hypothesis ID 或动作名变化都不能重开预算。耗尽后在原窗口终点前禁止 RESET；到期后也仍须实质不同的新证据簇、可验证 regime transition 和新 tranche 三门。`Obligation` 只表示必须继续观察并给出未来处置，不表示必须开仓。

当前 pilot 没有订单或真实止损成交，因此只检验该状态机和 shadow 条件，不伪造真实磨损、费用或 PnL。

### 13.5 物理逃生舱：当前 pilot 不增加真实核按钮，未来责任需补全

用户指出“只禁止新增风险无法处理既有仓位”在未来执行系统中成立；但“API/交易所异常时立即市价清仓”本身也不是可靠终局：相同故障可能令市价单无法提交、状态未知或以极端滑点成交。

正确的未来执行边界是独立于 Strategy Agent 的预授权应急执行舱：

- 交易所原生、reduce-only 的保护尽量在断线前已 ACK；
- 异常时先冻结新增风险和取消未触发入口，再用独立持仓真值对账；
- 场所可用时按预授权 `CANCEL/REDUCE/CLOSE` 优先级执行 reduce-only 或 market fallback；
- ACK 未知时禁止盲目重复下单，必须用幂等 ID 和订单/持仓查询收敛；
- 场所整体不可用时状态为 `EMERGENCY_EXIT_UNCONFIRMED / EXPOSURE_UNKNOWN`，触发人工与替代场所方案，不宣称必然退出；
- 该执行舱需要新的账户、订单、凭据、资金和 paper/live authority。本次 `PUBLIC_NON_ACCOUNT_ONLY / NONE_LOCAL_SIMULATION` pilot 只保留非执行 hazard 和 shadow emergency plan。

### 13.6 当前裁决

| 建议 | 裁决 | 落地方式 |
|---|---|---|
| 删除依赖闭包 | 拒绝直接删除 | 静态预计算、增量受影响子图、不可变前缀缓存，最终全量重放 |
| 0–100 改三档 | 采纳并加强 | 三档 enum、证据门槛、跨周期滞回、仅能限制风险 |
| 增加混沌标签 | 采纳 | typed regime；无方向状态当前风险为零，突破仅为条件 shadow |
| 连续止损两次停止 reentry | 采纳并加强 | 每 instrument 全局 24h 账本；ledger 激活后全方向 `OPEN_PROBE/REVERSE/REENTER` 共享次数/累计风险；冷却与三门 reset |
| API 异常立即市价全平 | 修正后仅用于未来 | 独立应急执行舱、预置保护、对账、幂等 fallback；永不保证成交 |

本节不证明这些修订能够盈利。它们修复的是风险分配的伪精确、混沌误分类、重复磨损、关键路径超时和执行责任空洞；市场预测增量、成本后收益、概率校准及跨 regime 泛化仍为 `UNKNOWN_NOT_EVALUATED`。

## 14. 第五资格对“删复杂度”建议的实践复核（2026-08-09）

第五资格首次让修正后的固定 `12` 组件公开 OKX bundle 进入正式 Agent 材料化。它确认用户对“精密系统会在真实容量和异常处碎裂”的担忧成立，但根因不是三档、混沌或 churn 规则本身，而是两个更具体的实现错误：把完整 graph association ID 列表重复内联到每条 Agent evidence，以及让 materializer 特殊分支处于 controller 失败边界之外。

裁决如下：

- 不删除 dependency closure。删除会恢复同一新闻、同一价格变化和同一公共来源被多个故事重复计风险的漏洞；但 Agent 不需要逐字阅读所有 verifier-only node/association IDs。
- Agent view 改为 bounded proof index：全部 evidence、availability、status、dependency groups、exact closure digest/counts、bars、UNKNOWN 与 OTHER 保留；完整 closure rows 只在 write-once graph registry 保存，由 owning verifier重建。真实 view 从约 `352 KiB` 降至 `187,892` bytes，固定 `256 KiB` cap 不上调。
- proposal/selection 的完整 canonical packet 仍直接进入同一 current Codex。真实 input 分别约 `475/593 KiB`，低于独立 `1 MiB` input hard cap；只有触及各自硬门才走可逆分片，不为了形式上的“压缩”增加无用阶段。
- materializer exception 必须消费已经预留的唯一 CURRENT_CODEX 资格尝试：先封存 exact authority/reservation/controller predecessor/material prefix/stage/time/typed error，再由 controller 进入 `FAILED_CLOSED`。重复 wake 只能重放，不得偷偷再构造一次。
- 异常后若物理 prefix 可以完整重扫，receipt 才写 `VERIFIED_EXACT`；重扫本身失败则写 `UNKNOWN_REPLAY_FAILED`，保留稳定失败码并永久终止同一尝试，但明确承认现场清单未知，不能拿空列表包装成“审计完整”。
- `187,895` bytes 的 Cycle-16 结果只是同一真实形态的编号/修订压力测试，并非 16 轮累计图演练；真实累计节拍仍由后续前瞻实验逐轮验证。
- 历史第五树没有新 failure receipt，不能事后补写洗成“当时已正确失败”。其 qualification/target exact pair 只能永久 tombstone；successor 必须来自新提交和新 ID。

这项修正体现的原则是：删掉重复传输和无决策价值的表示，不删去 provenance、UNKNOWN、反证和同源去重；简化热路径，同时让异常只有一个明确终态。它仍不证明预测增量、成本后收益、概率校准、跨 regime 泛化或盈利。
