# Agent-first 动态竞争假说体系

版本：`3.3.2-complete-market-analysis-candidate.3`

状态：`FROZEN_THEORY_REVIEW_CANDIDATE / PUBLIC_RESEARCH / POSITION_TRANSITION_LINKED / NON_EXECUTABLE`

Owner：Hypothesis Decision Agent（与 Market Cognition/Position Decision 为同一 Agent decision owner）。

输入：`InputSnapshot`、Agent 的市场认知、上一 episode/参考敞口、原始旧决策与可追溯记忆。

输出：`HypothesisRecord.AgentDecisionBody` 中的假说、路径、更新、反证、action thesis、episode 状态与仓位转换依据；`BehaviorPlan` 只原样引用/复制 Agent 自选动作、仓位和参考执行意图。

## 1. 假说的职责

假说是 Agent 连接观察、解释、未来路径和行动的可反驳思考单元：

```text
OBSERVATION
→ CURRENT-STATE INTERPRETATION
→ COMPETING MECHANISMS
→ CONDITIONAL FUTURE PATHS
→ FINAL REFERENCE ACTION AND POSITION THESIS
```

任何一层都可以 UNKNOWN、有歧义或不足以区分。上游 UNKNOWN 不会让系统自动生成 WAIT 或零风险；Agent 必须自己比较当前仍可表达的条件路径、观察动作、参考暴露和机会成本。

假说不是系统 schema 对象的同义词。Agent 可用自然语言、表格、情景树、图或自定义类别组织。可读且非空的原文必须封存；不得因假说字段、triggers 形状、lifecycle 枚举或顺序差异拒绝。

## 2. 四层思考模型，不是四种必填类型

### 2.1 当前状态假说

回答“现在是什么”：趋势、区间、转换、波动扩张/压缩、假突破、价格接受、流动性压力或另一种 Agent 觉得更准确的状态。

当轮只有价格时，Agent 只能把价格状态写成已观测/派生状态；订单流、拥挤或宏观机制仍可作为未验证假说，但不能伪装成已观测状态。

### 2.2 机制/归因假说

回答“哪些不同机制可以产生相同表象”。归因本质上不可直接观测，应当保留替代说明，例如趋势参与、获利了结、套保、套利腿、做市库存、强制去杠杆、新信息重定价或无方向噪声。

价格 Outcome 通常无法单独证实归因。Agent Review 只能说后续观察更支持/不支持，不能因上涨就倒推某个主体一定买入。

### 2.3 条件未来路径

回答“在什么条件下，未来会以什么顺序出现哪些可观测状态”。一条有信息价值的路径通常拥有：

```text
current condition
activation or trigger
expected observable sequence
acceleration / decay conditions
soft contradictions
hard falsifier
expiry or decision horizon
alternative path
next discriminating observation
action and position implications
```

上述是语义元素，不是固定 JSON。trigger 可以是完整句子、条件组、表格行或可读的结构化文本。系统不得因为它是对象而不是字符串、或不符合预设语法就拒绝。

禁止不可失败的循环故事，例如“涨了就看涨，跌了就看跌”。但如果 Agent 仍然输出了这类路径，它依然被封存，作为 Review 中的可反驳性缺陷证据，不作格式失败。

### 2.4 动作与仓位 thesis

回答“在当前信息和权限边界内，为什么这个最终不可执行参考动作与仓位比其他选项更合适”。

Agent 应将动作联系到未来路径、entry、失效、stop、targets、参考仓位和备选动作的机会成本，而不是从某个指标直接跳到 LONG/SHORT。

## 3. `HypothesisRecord` 的原文权威

`HypothesisRecord` 仍是五工件之一。它必须包含：

```text
SystemEnvelope              # 系统 owner，只有身份/时间/摘要/权限
AgentDecisionBody           # Agent owner，完整原文，唯一决策语义源
optional DecisionIndex ref  # 非权威、可丢弃
```

`AgentDecisionBody` 同时包含市场认知、假说、最终动作和仓位计划，不要求 Agent 把推理拆成两次 schema proposal。

`BehaviorPlan` 仍是正式五工件之一。它只能：

- 稳定引用完整 `AgentDecisionBody`；
- 原样引用或复制 Agent 自选的最终动作文本；
- 原样引用或复制 Agent 的 entry/stop/targets/仓位文本；
- 在无法定位时记为 null/ambiguous，同时保留完整原文引用。

系统不得补齐 lead、选一个 action、将自然语言仓位映射成默认数值或把 `BehaviorPlan` 投影反向当作决策真值。

## 4. 竞争集合由 Agent 生成与收缩

高质量判断通常会寻找：

1. 当前最能解释观察并给出未来路径的候选；
2. 由不同机制产生相同表象的最强竞争候选；
3. 无方向影响、噪声、未被现有机制覆盖或 OTHER 的可能。

但候选数量不是魔法常数。Agent 可以提出一个、三个或更多，也可以明确说无法形成有意义的竞争集合。数量不足或重复只是后续质量证据，不是终态门。

建议收缩原则：保留会改变最终动作、仓位、关键观察或失效几何的不同机制；只有措辞差异的候选可由 Agent 自行合并。系统可展示文本相似度，不能自动删除假说。

## 5. 证据更新不是固定加分

Agent 在使用每项观察时应思考：

- 它是事实、测量还是推断；
- 它作用于当前状态、机制、路径还是动作；
- 与其他证据是否共享价格、时间、provider 或同一事件；
- 它是否在当前 horizon 上新鲜；
- 它对不同竞争假说是否产生不同预期；
- 存在什么替代解释。

Agent 可用“弱支持”、“混合”、“当前领先”、“强但未校准”、“软反证”等语言，但不必使用固定 support enum。在没有校准时，不应把自然语言确信映射成伪精确概率或 EV。

如果 Agent 使用了伪精确概率、重复证据或未准入资料，系统仍然不得因语义质量问题改写/拒绝可读原文。未准入资料若构成未来泄漏或 raw/PIT 破坏，才按硬边界 fail-close；否则作为 Agent Review 证据。

## 6. UNKNOWN 与非方向状态

| Agent 的当前认知 | 可以继续思考 | 不应由系统自动产生 |
|---|---|---|
| 方向 UNKNOWN，几何清楚 | 两侧条件路径、WAIT、参考 probe | 默认 WAIT/零仓位 |
| 可重放 RANGE | 均值回归、突破、假突破竞争 | 强制趋势标签 |
| TRANSITION | 旧状态继续、新状态建立、失败转换 | 确定性 tie-break |
| price-only | 窄 claim 的价格路径与完整参考计划 | 伪造 flow/crowding 确认 |
| 多个结论真正并列 | 保留歧义、说明哪项观察会破局 | 词典序胜者 |

UNKNOWN 不是一个特定 action。Agent 仍需对当下的不同选择负责。

## 7. 区分性观察和信息价值

不需补齐所有数据。Agent 应优先寻找会改变假说、动作或仓位的观察：

```text
what to observe
what lead/runner/other would expect differently
when it can legally become available
which source or price condition can reveal it
how the final action/position would change
what to do if it remains missing
```

这是高质量思考清单，不是必填字段。Agent 不写下一观察时，系统不得拒绝；Outcome 与 Agent Review 用这一缺失检验决策是否可学习。

## 8. 动态更新由 Agent 判断

假说可以经历以下语义变化，但不需使用枚举状态：

### 新建

新机制、新路径、新失效条件或新 horizon 可以建立新假说。只是语言改写不应伪装成新思想。

### 强化

决策 cutoff 之后的新观察可能加强假说，但同一价格移动的多个指标不自动变成多份证据。是否增加仓位由 Agent 单独判断。

### 削弱

软反证、证据过期、竞争机制增强、时间消耗或路径次序偏离可以削弱假说。Agent 可在 hard falsifier 前决定减仓、取消或重评。

### 失效

hard falsifier 命中时，理论期望 Agent 不通过延长期限、移动边界或换措辞复活旧假说。但最终失效判断仍属于 Agent；系统可将命中候选与 raw 事实显示给 Agent，不能自动改写状态或动作。

### 过期

到期未出现预期路径是市场证据，不是系统错误。Agent 决定这代表关闭、降级、换 horizon 还是新假说。

### 替换

当竞争假说获得更好的机制或路径证据时，Agent 可以让它取代旧主线。原决策不回写；新判断作为新 `AgentDecisionBody` 封存。

## 9. 没有确定性选择器

V3.3.0 使用词典序、必填 lead/runner/OTHER、固定 action set 和 deterministic tie-break 决定 operating lead。V3.3.2 取消这个决策 owner。

Agent 可以使用 lead/runner-up/OTHER，也可以：

- 保留真正并列的两个路径；
- 将一个路径设为条件主线而不声称唯一领先；
- 明确当前无法选出足够好的市场解释；
- 提出理论词库之外的机制和动作；
- 在歧义中仍然作出最终参考动作和仓位。

系统可以在 `DecisionIndex` 中标记“未找到明确 lead”或“多个候选”，但不能自行排序、选择、重命名或将一个候选当最终行动。

## 10. 从假说到最终动作

Agent 应在原文中比较会改变决策的行为，例如方向参考、条件触发、WAIT、参考 probe、HOLD、REDUCE、CLOSE、部分落袋、runner、反向新 episode、reentry 或信息动作。

这些例子不是受控 action enum。Agent 可以选择新的不可执行参考动作。系统只在真的外部副作用请求到达安全边界时检查权限；不因文本超出词表拒绝研究决策。

高质量动作 thesis 通常说明：

| 问题 | Agent 需做的判断 |
|---|---|
| 哪条路径支持该动作 | 主机制、条件与时钟 |
| 哪条路径使动作受损 | 竞争机制和机会成本 |
| 什么时候错 | 失效、stop/exit、expiry |
| 如何缩小错误代价 | 条件入场、小额参考、减仓或 WAIT |
| 仓位如何随路径改变 | tranche、加减仓、targets、runner、reentry |
| 什么新观察会改变决策 | 下一 review 的具体条件 |

这是质量准则，不是封存门。

## 11. Agent Review 与学习

Outcome 封存后，Agent 读取原 `AgentDecisionBody`、`BehaviorPlan`、`Outcome` 与有界记忆，在 `Review.AgentReviewBody` 中自主判断：

```text
当前状态理解是否有用？
竞争机制是否真正不同？
路径是否给出了可观测序列和有意义反证？
领先/并列判断是否合理？
最终动作和仓位是否充分利用了当时认知？
WAIT/其他备选的机会成本是什么？
缺失、歧义、不可反驳或伪精确如何影响结果？
应保留、修改、删除还是新增什么候选？
```

系统可以计算路径 touch sequence、endpoint、MAE/MFE 和原文存在性，但不能自动判定假说“成功/失败”、产生教训或更新理论。

## 12. 质量期望与封存边界

理论期望 Agent：

- 不使用未准入或未来事实；
- 不把归因写成可观测真值；
- 不把同一价格依赖族当多份独立支持；
- 不用事后结果移动 zone、falsifier 或 expiry；
- 不用未校准概率、sum-to-100、margin、entropy 或 EV 制造精确性；
- 不把 UNKNOWN 当零，不把 WAIT 当系统默认；
- 将最终动作和仓位明确归于自己的当时判断。

但这些是 Agent 能力/理论遵循的评价标准，不是非安全格式或语义终态门。只要身份、raw、PIT、未来隔离、迟到、核心覆盖、单写者、可读非空与外部授权硬边界未被破坏，决策不得被拒绝。

## 13. 数据不足不删除假说

V3.3.2 明确采用：

```text
absence of evidence != evidence of absence
```

缺少机构、账户、完整盘口或叙事数据，只说明主体机制当前不能确认，不说明它不可能存在。一个未验证机制若能提供不同的未来路径、提前动作、保护条件或信息需求，就可以留在竞争集合中。

建议的认识等级：

| 等级 | 含义 | 可否用于规划 |
|---|---|---|
| `OBSERVED_FACT` | 有合法PIT raw直接支持 | 可以 |
| `TRANSPARENT_MEASUREMENT` | 由事实可复算 | 可以 |
| `SUPPORTED_LATENT_STATE` | 多项签名支持的潜在市场状态 | 可以，保留替代 |
| `PLAUSIBLE_UNVERIFIED` | 机制合理但数据不足 | 可以，用条件触发和更小风险 |
| `ACTOR_HYPOTHESIS_UNOBSERVABLE` | 特定主体/意图公开不可验证 | 可以作情景背景，不写成身份事实 |
| `CONTRADICTED` | 预注册观察与假说相冲突 | 应削弱、关闭或新建episode |
| `EXPIRED/CENSORED` | 时间到期或样本尚未进入验证域 | 分开记录，不能伪装命中/失败 |

系统不能因为后两种未验证等级而删掉Agent原文。Agent应比较保留它的规划价值与注意力成本。

## 14. 观察、潜在状态、主体和意图四级分层

```text
Observed Evidence
→ Latent Market State
→ Actor Hypothesis
→ Actor Intent Hypothesis
```

示例：

1. 关键区放量、下影、重复成交：`OBSERVED_FACT/MEASUREMENT`；
2. 该区域存在响应性买盘或吸收：`SUPPORTED_LATENT_STATE`；
3. 大型参与者可能吸筹或护盘：`PLAUSIBLE_UNVERIFIED`；
4. 其目的可能是配合利好拉高后派发：`ACTOR_HYPOTHESIS_UNOBSERVABLE`。

四层都允许存在，但不能互相冒充。后续价格按路径演化可以支持第2层并证明提前路径规划有用；若没有申报、身份或行为链证据，不能仅凭价格命中宣称第3或第4层已被证实。

## 15. 假说真实性与交易规划价值分开

一个主体故事可能没有被证明，但其条件路径仍可能帮助提前交易：

```text
若关键区出现承接并收回
→ 允许反弹probe
若事件后放量上冲但无法接受高位
→ 保护利润/考虑反向新episode
若关键区被放量接受性跌破
→ 关闭护盘路径并转入下行扩张路径
```

这里真正被交易的是可观察状态转换，不是对主体心理下注。Review分别评价：

- 机制真实性得到多少支持；
- 路径是否按顺序发生；
- 提前动作是否有用；
- 主体叙事是否增加、减少或没有改变决策质量；
- 若删去主体叙事，是否仍能得到同样路径。

只有会改变路径、动作、仓位或下一观察的假说值得长期保留。永远不能失败、没有差异预测或只在Outcome后解释一切的故事，应在Review中削弱或退休，而不是由系统事前删除。

## 16. 假说、episode 与仓位转换

市场假说生命周期和仓位 episode 生命周期必须分开：

```text
Hypothesis: NEW → ACTIVE → STRENGTHENED/WEAKENED → CONTRADICTED/EXPIRED/REPLACED
Episode: WATCHING → ACTIVE/SUSPENDED → CLOSED/INVALIDATED/EXPIRED
Exposure: FLAT → PROBE/CORE/TACTICAL/HEDGE → REDUCED/FLAT
```

一个假说被削弱不必然要求立即平仓；如果风险几何仍合格，Agent 可 REDUCE 或等待区分性观察。反之，假说仍可能存在，但价格、成本、数据或组合预算使当前最佳敞口为零。系统不得用假说状态机械决定仓位。

### 16.1 `Action Thesis` 最低语义

高质量 action thesis 应说明：

1. 哪条路径和哪些观察支持该动作；
2. 当时的 `ReferenceExposureState`；
3. Agent 选择的 `TargetExposureState` 与 `PositionDelta`；
4. 涉及哪个 episode、角色和 tranche；
5. 为什么不是其他合法动作；
6. 哪个新观察会取消、增加、降低、止盈或退出；
7. 决策到期、关键 UNKNOWN、成本和风险预算；
8. 参考执行与未成交 fallback。

这是学习语义，不是严格字段门。缺失时仍封存，但 actionability 降级，不允许系统自行补完。

### 16.2 ADD、REENTER 与故事重命名

- `ADD` 必须指向新证据、预注册路径升级、改善后的几何或新增独立 tranche；
- “价格更便宜”“浮亏变大”“仍相信原故事”不能单独构成 ADD；
- `REENTER` 必须有平仓后的新观察、重新计算的失效/风险和新的激活身份；
- 不得把未止损的旧仓事后重命名为新 episode，也不得把失败 PROBE 改名 CORE；
- 反转必须关闭旧 episode 后新建反向 episode，分别保留证据链。

### 16.3 路径支持不直接决定数量

即使主路径领先，也不能从 `SUPPORTED_LATENT_STATE` 机械映射为“50%仓位”。目标敞口还取决于：

```text
invalidation distance
gap/liquidity/product risk
reference execution cost
correlated and pending risk
data freshness and fallback
right-tail opportunity and opportunity reserve
```

Agent 是最终 owner；透明计算器只给几何，不给方向或数量。

### 16.4 保留反事实但不改写历史

在 cutoff 时可预注册合理替代动作与参考尺度，供 Outcome 比较。若 Review 才提出替代方案，必须标记为事后反事实，不能说它是原计划的一部分。MFE、最终价格或后来新闻不得用于重写当时假说、zone、expiry 或仓位依据。
