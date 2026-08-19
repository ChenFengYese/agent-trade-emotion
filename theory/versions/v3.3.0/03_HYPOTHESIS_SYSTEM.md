# 竞争假说体系

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE / PUBLIC_RESEARCH / NON_EXECUTABLE`

Owner：从市场状态到可反驳路径、竞争更新和合法动作比较。

输入：`InputSnapshot` 与 `MarketState`。

输出：`HypothesisRecord`，并向仓位模块交付可行动路径和关键 UNKNOWN。

## 1. 假说的职责

假说不是对市场故事的润色，而是连接观察与未来行动的最小可反驳结构：

```text
OBSERVATION
→ STATE HYPOTHESIS
→ ATTRIBUTION HYPOTHESIS
→ FORECAST-PATH HYPOTHESIS
→ ACTION THESIS
```

任何层级都可以保持 UNKNOWN。上游 UNKNOWN 不必让下游全部归零，但下游结论必须受其 claim ceiling 限制。市场认知负责观察和状态；假说体系负责竞争解释和未来路径；仓位模块负责风险几何。三者不得相互代写。

## 2. 四类假说

### 2.1 State Hypothesis

回答“现在是什么状态”：趋势、区间、转换、波动扩张、流动性压力、拥挤或信息事件窗口。

### 2.2 Attribution Hypothesis

回答“哪些机制最可能产生当前观察”：方向性买卖、套保、基差套利、做市库存、获利了结、强制去杠杆、再平衡、信息重定价或无方向性噪声。

归因是不可直接观察的候选解释，不能升级为事实。

### 2.3 Forecast-Path Hypothesis

回答“在什么触发条件下，接下来会按什么顺序出现哪些可观察状态”。它必须包含至少一个替代路径和明确期限。

### 2.4 Action Thesis

回答“在当前可用动作全集中，为什么某个可撤销行为比其他合法行为更合适”。它必须引用 Forecast Path，不得从指标直接跳到 LONG/SHORT。

## 3. HypothesisRecord 合同

```text
HypothesisRecord
  record_id, episode_id, theory_revision
  instrument_id, decision_at, horizon
  market_state_ref
  hypotheses[]
  dependency_clusters[]
  lead_id, runner_up_id, other_id
  lawful_actions[]
  next_discriminating_observations[]
  unresolved_unknowns[]
  deterministic_selection_trace

Hypothesis
  hypothesis_id
  type: STATE | ATTRIBUTION | FORECAST_PATH | ACTION_THESIS
  proposition
  mechanism
  observable_sequence[]
  supporting_factor_refs[]
  opposing_factor_refs[]
  dependency_clusters[]
  preconditions[]
  triggers[]
  soft_contradictions[]
  hard_falsifiers[]
  expiry
  applicable_horizons[]
  claim_ceiling
  status
  parent_ids[], competing_ids[]
  action_implications[]
```

状态只允许：

```text
PROPOSED
ACTIVE
LEAD
RUNNER_UP
WEAKENED
FALSIFIED
EXPIRED
REPLACED
UNRESOLVED
```

不得删除失败假说后假装它从未存在；使用 `REPLACED` 或 `FALSIFIED` 保留谱系。

## 4. 竞争集合的生成

每轮至少包含三类解释：

1. lead candidate：当前最能解释观察且能给出区分路径；
2. competing candidate：由不同机制产生相似表象；
3. `OTHER/NO_DIRECTIONAL_EFFECT`：现有机制库之外、噪声或对方向无确定影响。

只有一个故事时，系统必须主动生成最强反例；不是为了对称而编造一个相反方向，而是寻找在相同事实下成立的不同机制。

候选生成顺序：

```text
market state
→ relevant mechanism families
→ path templates valid for horizon
→ instantiate with point-in-time facts
→ add alternatives and no-effect
→ bind falsifiers and expiry
→ prune duplicates by dependency/mechanism
```

数量不设永久魔法常数。边界由 payload 和决策价值控制：保留所有会改变合法动作或关键观察的非重复候选；仅措辞不同、路径相同或不改变行动的候选合并。

## 5. 证据不是简单加分

V3.3.0 不使用固定 `0 / 0.5 / 1` 作为普适证据真值，也不把多个指标直接相加。

每个 factor 先回答：

- 它是事实、测量还是推断；
- 对哪个 hypothesis 的哪条边有作用；
- 与其他 factor 是否同源；
- 时间是否匹配；
- 它支持的是状态、机制还是路径；
- 存在哪些替代解释。

更新使用有序状态而非伪精确概率：

```text
NO_ADMISSIBLE_EVIDENCE
WEAK_SUPPORT
MIXED
OPERATING_SUPPORT
STRONG_BUT_UNCALIBRATED
SOFT_CONTRADICTION
HARD_FALSIFIED
```

`STRONG_BUT_UNCALIBRATED` 仍然不是概率。它只表示在当前合法证据与竞争集合内拥有更清楚的机制、路径和反证。

### 5.1 独立性规则

同一 `dependency_cluster` 的多个 factor 不能累积成多份支持。跨簇证据也不自动独立；若它们共同依赖同一价格、同一事件或同一 provider，须在图上保留共同父节点。

### 5.2 客观几何与主观支持分开

方向支持仍未校准时，仓位几何可以客观计算：entry、structural invalidation、stress loss、expiry 和公开成本压力。行为强度由以下最小值约束：

```text
action_ceiling = min(
  evidence_claim_ceiling,
  geometry_ceiling,
  data_profile_ceiling,
  position_policy_ceiling,
  permission_ceiling
)
```

这样不会把 Agent 的语言确信直接转换成更大仓位。

## 6. UNKNOWN 与非方向状态

`direction=UNKNOWN`、`regime=TRANSITION`、`liquidity=STRESSED` 可以同时成立；它们不是同一个结论。

| 市场认知结果 | 假说系统可做 | 不应自动做 |
|---|---|---|
| 方向 UNKNOWN、几何清楚 | 比较 WAIT、条件 probe、两侧触发 | 伪造方向确信 |
| RANGE/无方向但边界可重放 | 建均值回归或突破条件路径 | 把无方向等于无机会 |
| TRANSITION | 建旧状态延续、新状态建立、假突破 | 强行选趋势/区间 |
| 数据覆盖较低但核心价可信 | 输出 price-only 假说与窄 claim | 阻断整个 cycle |
| 关键事实冲突 | 保留 competing lead/runner-up | 用平均分掩盖冲突 |
| 合约身份或时间不可信 | 不准入假说 | 继续做方向推断 |
| 流动性/成本不可定义 | 市场假说可继续，执行映射关闭 | 抹掉市场分析 |

可撤销 probe 需要清楚的几何、信息价值和退出条件；不是 UNKNOWN 时默认下注。

## 7. Path Contract

每条 Forecast Path 使用同一结构：

```text
Path
  path_id
  parent_hypothesis_id
  initial_state
  trigger
  expected_observation_sequence[]
  decision_horizon
  acceleration_conditions[]
  decay_conditions[]
  soft_contradictions[]
  hard_falsifiers[]
  expiry
  next_discriminating_observation
  feasible_actions_by_stage[]
```

示例结构而非市场结论：

```text
IF price accepts above predeclared zone
AND participation expands from a different dependency cluster
THEN trend-continuation path becomes operating lead
ELSE IF price returns into value and flow response weakens
THEN failed-break path becomes runner-up/lead
EXPIRE at decision horizon
FALSIFY continuation on specified structural break
```

禁止使用“如果涨就看涨、跌就看跌”这种不可失败的循环路径。触发与 falsifier 必须事前指向不同可观察状态。

## 8. 区分性观察与信息价值

系统不要求补齐所有数据，只寻找最能改变竞争排序或合法动作的下一观察。

选择顺序：

1. 哪项观察在 lead 与 runner-up 下预期不同；
2. 能否在 decision horizon 内合法获得；
3. 是否来自新的 dependency cluster；
4. 获取成本和延迟是否低于决策价值；
5. 若缺失，是否仍能完成最小判断。

输出：

```text
observation
expected_under_lead
expected_under_runner_up
availability_time
source
decision_change_if_seen
fallback_if_missing
```

不得为了“完整”漫无目的读取所有网站。

## 9. 生命周期与更新

### 9.1 新建

只有新机制、不同路径或不同失效条件才新建 hypothesis。语言改写更新原记录。

### 9.2 强化

必须出现决策 cutoff 之后的新证据，且不只是原价格移动的重复指标。强化可以提高有序支持，但不能自动增加仓位预算。

### 9.3 削弱

soft contradiction、证据过期、替代机制增强、路径超时都可削弱。削弱通常触发比较 `HOLD / REDUCE / WAIT`，不必等 hard falsifier。

### 9.4 失效

hard falsifier 命中后，该 hypothesis 在本 episode 中为 `FALSIFIED`。不得靠延长期限、移动边界或更换文字复活；若真正出现新机制，建立新 hypothesis/episode。

### 9.5 过期

到期但未出现预期序列标为 `EXPIRED`，这是可评估结果，不是系统故障。

### 9.6 替换

runner-up 获得更强机制差异证据时可取代 lead；保留 `replaced_by`、原因和 cutoff，禁止回写旧决策。

## 10. 从分析到动作

动作全集由当前权限和任务给出，假说体系不得静默删除合法动作。公开研究默认可比较：

```text
LONG_REFERENCE
SHORT_REFERENCE
WAIT
CONDITIONAL_TRIGGER
PROBE_REFERENCE
HOLD_REFERENCE
REDUCE_REFERENCE
CLOSE_REFERENCE
REVERSE_AS_TWO_EPISODES
REENTER_AS_NEW_EPISODE
OTHER_INFORMATION_ACTION
```

对每个可行动 hypothesis，建立：

| 字段 | 内容 |
|---|---|
| 受支持动作 | 哪些动作利用该路径 |
| 受损动作 | 哪些动作在该路径下机会成本高 |
| 失效几何 | 何处说明 action thesis 错误 |
| 时间成本 | WAIT 到下一 review 的损失与价值 |
| 信息动作 | 哪个观察比暴露方向风险更有价值 |
| 可逆性 | 是否能用 SEED/条件计划缩小错误成本 |
| 关键 UNKNOWN | 哪个未知限制 claim 或执行映射 |

WAIT 不是默认安全答案。它必须写出：

```text
reason
opportunity_cost
next_review_at/event
what_would_change_the_decision
```

## 11. Lead、Runner-up 与 OTHER 的确定性选择

在不使用概率和 EV 的前提下，按以下词典序选择：

1. 是否通过事实与时间准入；
2. 是否有清楚机制而非纯描述；
3. 是否给出可区分路径；
4. 是否有跨依赖簇支持；
5. hard falsifier 是否未命中；
6. 关键证据是否新鲜且匹配 horizon；
7. 替代解释是否更少、但未被人为删除；
8. 是否能映射到可撤销、损失可定义的动作；
9. 若仍相同，选择更简单、假设更少者；
10. 仍相同则保持并列 `UNRESOLVED`，不伪造胜者。

`lead` 是当前操作领先者，不是“真实概率最高”。`runner-up` 必须足够具体，能说明什么新证据会取代 lead。`OTHER` 永远保留，但不能借此逃避提出可检验主张。

## 12. Agent 与确定性系统的分工

Agent 适合：

- 生成机制差异候选；
- 找替代解释和反例；
- 连接跨层传导；
- 提出下一项区分性观察；
- 用自然语言解释机会成本。

确定性系统负责：

- 时间、schema 和 source 准入；
- dependency 去重；
- hard falsifier/expiry 触发；
- 合法动作全集；
- 词典序选择与稳定 tie-break；
- 版本、摘要和五工件封存。

Agent 不得改写 raw fact、账户真值、权限、政策参数或已封存决策。

## 13. Review 接口

到期后按 hypothesis/path 分开评价：

```text
state_classification_result
attribution_support_after_outcome
path_sequence_hit/miss/typed_missing
lead_vs_runner_up_resolution
falsifier_behavior
expiry_quality
action_opportunity_cost
OTHER_rate_and_new_mechanism_candidate
instability_across_identical_input
```

归因通常无法由单个价格 outcome 直接证实；Review 只能写“后续观察更支持/不支持”，不能把上涨倒推成某个主体一定买入。

持续出现以下情况时才建议修改理论：

- OTHER 高且出现重复的新机制；
- 相同输入的 lead 不稳定；
- 多数 hypothesis 无法给出不同路径；
- falsifier 总被事后移动；
- WAIT 没有复核条件；
- 证据数量主要来自同一依赖簇；
- action thesis 不能映射到可定义风险。

Review 只能提出下一版本变更，不自动修改当前理论。

## 14. 禁止项与已知边界

- 不输出未经校准的 `probability_pct`、sum-to-100、margin、entropy 或 EV。
- 不用 Agent 信心作为风险预算。
- 不把指标数量当证据数量。
- 不因缺少可选增强而取消 price-only baseline。
- 不让 hard falsifier 被更长时间、移动 zone 或新措辞规避。
- 不把事后价格方向当作归因真值。
- 不把 `OTHER` 解释成“什么都不知道”，也不把 UNKNOWN 解释成零。
- 不规定永久候选数量、固定证据分数或固定 lead 差值。
- 不从旧版本自动继承权限、动作删减或资格状态。
