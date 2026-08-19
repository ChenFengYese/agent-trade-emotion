# 当前研究理论 V3.2：动态进攻与可撤销风险

版本：`3.2.6-five-trap-hardening-candidate`

版本语义：正式 authority/schema 的兼容字段仍为 `theory_version=3.2.1`；`3.2.6-five-trap-hardening-candidate` 是同一 V3.2.1 语义族内、等待新提交与资格冻结的文档/实现修订标签，不得混写成已经生效的新 authority 版本。

状态：`SEVENTH_QUALIFICATION_EXPIRED_TERMINAL / V3_2_6_FIVE_TRAP_HARDENING_CANDIDATE / NO_TARGET_AUTHORITY / NO_TARGET_RUN / NO_OUTCOME`

日期：2026-08-10（第七资格过期后修订候选）

继承：`CORE_TRADING_THEORY_v2_1.md`、`CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md` 与 V3.1.1 的 raw-first、Supervisor、十二轴、关联预注册和资格修复。

候选 V3.2 计划权限边界：`PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION / executable=false`。2026-08-08 修订取消 0–100 主观分值的风险映射，增加显式混沌状态、耐久全方向重入预算、增量依赖投影和 future-only 执行逃生舱边界；这些语义已进入本地实验合同、28 组件正式接纳、runtime closure 和 full loader。前四份失败资格继续永久封存。提交 `093b4e79d43ef523e0926aa1e8495ba13feb4145` 修正资金费四时钟后，第五资格 `v32-qualification-btcusdt-20260809t074253z` 的唯一 PUBLIC_SOURCE aggregate attempt 取得固定 `12/12` 份 OKX public HTTP 200；但真实的 `414` 根闭合 bar 与 `55` 条可引用证据使旧 Agent 市场图视图达到约 `352 KiB`，超过错误估算的 `256 KiB` 上限。材料化在 Agent view、mailbox 和 CURRENT_CODEX claim 之前停止；无 Agent delivery、monitor、target authority/genesis/cycle 或 outcome。旧 composition 又没有把该异常变成 controller 终态，因此第五 qualification/target exact pair 必须永久 tombstone，不得重试、推进、删除、改写或用修复后代码重签。有界视图与材料化失败原子性已提交为 `975e7a873e9f801594385e2feb00453586f270c3`，手工 exact post-commit V3.2 `657/657` 和全 Theory Paper `1411/1411` 通过。但它们当时没有 write-once 执行收据，不能被 authority 机器重放。因此**当时**先封闭 post-commit 收据、WorkspaceFreeze v1.1 与 qualification 每次 wake 的完整 Phase-A 物理重放；新的显式提交、受约束执行收据和 successor 资格完成前，本地 PASS 仍不等于实际 Codex 或 monitor 已资格化。

上述收据链已提交为 `e0c7d3da4e0809fd21b0d241db84e0c17155d4ff`，第六资格 `v32-qualification-btcusdt-20260809t131915z` 随后完成正式 post-commit replay、完整 Phase-A 与唯一 PUBLIC_SOURCE attempt，却在 CURRENT_CODEX 的 `CONTEXT_PACKAGE:PROPOSAL` 永久 `FAILED_CLOSED`。真实 proposal=`559,522 B`，完整 INLINE input=`562,654 B`，本来低于既有 `1 MiB` 总输入门；失败由额外 `512 KiB` proposal 子门误触发。备用 leaf-level compaction 又把原件膨胀为 `121` shards、约 `7.79 MB`，selection 约 `306,980 B`。进一步对旧实际 Presentation 只读重建发现，旧返回把同一 packet 放在 request context、canonical original 与 ordered unit 三处，最终为 `1,687,318 B`；旧门只测第一份，而且 qualification/target 会先 claim 再构造这个超限返回。

V3.2.5 因而同时修正**判定对象**与**写入顺序**：删除 stage-specific 512/768 KiB 魔法断崖；当前 pilot 固定为 `INLINE_ONLY`，正文只在 `request.agent_input_context` 出现一次。完整 `CurrentCodexPresentationEnvelope` 还绑定 checkpoint、request、可选 claim 和严格标量 control context，并在 enqueue 与 claim CAS 之前按最终对象精确测量；任何超限都保持 request、material 与 checkpoint 不变。`SHARDED` 只保留为未来尚未资格化的多段 transport 能力；它必须另行定义分段游标、逐段 ACK、完整重组与耐久消费收据并重新资格化，当前 successor 不得使用。第六现场按 `INLINE_ONLY` 规则只读重建约 `566–568 KiB`，packet 只出现一次，但这只是本地确定性可重建的 Presentation，不证明 provider/transport 已接收、完整交付或由当前 Codex 消费。第六 exact pair 和全部前驱字节永久 tombstone；修复后只能用新 commit、新 post-commit 收据和全新资格 ID 重新验证。

第六资格后的当前工作树还把这条边界收紧为单一耐久协议候选：request、claim、delivery/receipt、consumption/receipt 四个“不可变对象已发布、checkpoint CAS 尚未完成”的 exact tail 都只允许复用首次字节、首次时间和同一 predecessor 完成一次尾提交；V3.2-owned durable writer 以同目录私有临时文件完整写入并 `fsync(file)`，再用不可覆盖的原子发布和 `fsync(directory)` 固化目录项。该 writer 只归 V3.2 stores 所有；V3.1 冻结的 `domain/contracts/canonical.py` 及其使用者保持原字节不变。进程若在 CAS 成功后丢失响应，重复入口分别只可返回已经提交的 `REQUESTED`、`CLAIMED` 或 `DELIVERED` exact successor，不能再次写对象、取新时钟或调用第二次 Agent。delivery receipt 必须在 `current_codex_presentation_digest` 写入最终 `CurrentCodexPresentationEnvelope` digest，qualification full replay 从 CLAIMED 快照重建同一 envelope 后核对。Agent-facing 最终返回就是该 envelope 本身，不再套外层 runtime/alert 包装；hot path 仅接受 `INLINE_ONLY`，完整 input 或最终 envelope 超过 `1 MiB` 时立即在持久化/Agent 调用前失败，不能现场转入 `SHARDED`。

真实 fresh-process collector 已在提交 `66197c47a1281340b4226da825da0b18d8815c3e` 与第七资格中实际运行：它在任何 Phase-A authority byte 与 System UTC 资格时钟之前，以 `/opt/homebrew/bin/python3.12 -I -c` 独立进程导入冻结 roots；typed/self-digested receipt 被 write-once 保存到 qualification support，物理 binding 进入 manifest/runtime authority，并由 full loader 重开 receipt、根集合、时序、摘要和 closure。runtime manifest 保持同一个 schema family，但只接受两种严格形状：`1.0.0` 是旧六棵树的 legacy manifest，不含 fresh binding 且只允许原样重放；`2.0.0` 是 successor manifest，强制 `fresh_process_trace_binding`。新 prepare 只生成 `2.0.0`，full loader 必须物理重开 trace 并证明 `trace.completed_at <= workspace.observed_at` 后才能继续；不得给旧树补造 fresh receipt，也不得让新资格降级到 `1.0.0`。第七资格的机械闭包为 `43 roots / 194 recursively reachable local paths / 194 bindings`，fresh-process 与 fresh PUBLIC_SOURCE 子门已有实际资格证据；但 CURRENT_CODEX 在 claim 前耗尽 reservation 窗口，固定 outcome monitor 也未开始，因此完整耐久交付、monitor 与 15 分钟时延仍为 `UNKNOWN_NOT_QUALIFIED`，必须由新提交和第八 exact pair 重验。

post-commit 收据只属于**受信任本地控制器的可重放审计证据**。它没有外部签名、远端 CI 身份或硬件根，不能对抗拥有项目与运行目录写权限的恶意本地操作者，也不得称为 independent、third-party、provider 或 hardware attestation。该证据上限必须进入机器合同；若未来需要对抗恶意本地 owner，必须另行引入外部 CI/OIDC、远端日志签名或硬件根并重新授权。

明确不授权：paper/live、真实账户、订单发送、凭据、资金、真实组合写回。本文的仓位、限价、止损和执行讨论在当前阶段均为条件行为规划；只有未来独立权限和执行合同才能转为订单。

---

## 1. 核心修正

V3.2 的中心原则不是“放弃谨慎”，而是把认识论和行动论彻底分开：

> **不知道原因，不等于不能承担小额风险；不知道损失边界、数据真实性或动作权限，才等于不能承担风险。**

V2.1/V3.1 对事实、时点、因果和概率的约束继续有效；被修正的是把一般市场不确定性过多映射为 WAIT 的行为政策。

```text
认识论：事实是什么、哪些未知、推断有多脆弱
决策论：在这些未知下，什么规模的风险仍可撤销、可承受、有机会价值
执行论：当前是否有权限、成本、流动性和保护能力将计划变成动作
```

V3.2 允许在原因或方向尚未确认时先建立 `ANTICIPATORY_PROBE`，随后以新证据增加、减少、退出、反转或再入场。它不允许无失效位的赌博、亏损摊平或主观故事直接放大仓位。

---

## 2. 最终目标函数

理论的最终经济目标改为：

> 在数据和权限真实、不可接受损失被硬限制的前提下，最大化长期成本后机会捕获和资本增长，并显式惩罚过度 WAIT、迟到确认、固定止盈和退出后不重入造成的机会损失。

未来只有在存在校准分布、收益映射和账户效用时，才允许计算期望对数增长或 EV。当前非校准模式使用两级决策：

1. **硬约束**：数据完整性、权限、可定义的最坏损失、流动性/成本边界和组合风险；
2. **进攻性比较**：机会捕获、非对称收益、可撤销性、信息价值、延迟损失、换手成本和尾部脆弱性。

风险不是父目标，也不是默认否决器。它是稀缺预算：应分配给最有条件优势、最易否证且最可修正的机会。

---

## 3. UNKNOWN 分类与行为含义

所有 UNKNOWN 必须带类型，禁止统一导向 WAIT：

| UNKNOWN 类型 | 含义 | 新风险行为 |
|---|---|---|
| `UNKNOWN_FACT_INTEGRITY` | 原始数据、时间、schema、revision 或来源无法验证 | 依赖该事实的动作禁止 |
| `UNKNOWN_PERMISSION` | 账户、产品、动作或执行权限未知 | 禁止执行；研究计划可保留 |
| `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN`（compiler 判定作用域，非 dynamic-state enum） | 当前公开 PIT 中用于研究比较的合约规格或冻结压力输入不可验证 | 当前正 reference-risk 候选归零；只由 compiler 的 exact objective-input 诊断拥有，不允许 Agent 单边自报 |
| `UNKNOWN_MAX_LOSS`（legacy dynamic token，现限定为 real-execution scope） | 真实账户费用、成交滑点、venue outage 或尾部损失不可定义 | `behavior_effect=BLOCK_FUTURE_EXECUTION`；只阻断未来真实/paper 执行，当前 public/non-executable 研究不得用它删除某一方向 |
| `UNKNOWN_DIRECTION` | 多空方向不清或竞争接近 | 允许条件双路径、小额单边 probe 或继续观察 |
| `UNKNOWN_CAUSE` | 价格变化原因不清 | 不单独阻塞结构/流动性驱动的 probe |
| `UNKNOWN_ACTOR` | 无法确认主力、机构或人群身份 | 只允许行为一致性假说，不阻塞价格状态分析 |
| `UNKNOWN_NARRATIVE_ADOPTION` | 不知道多少人相信某叙事 | 保持或降低叙事支持档位，不把缺失补零 |
| `UNKNOWN_FUTURE` | 市场正常随机性和不可预见事件 | 正常风险来源，不自动 WAIT |
| `UNKNOWN_OUTCOME` | 事前 outcome 尚未到期 | 不得提前读取；不妨碍新的独立分析轮 |

若关键风险边界完整、存在明确失效位和正向机会几何，仅以“市场不确定”作为 WAIT 理由无效。

---

## 4. 市场状态的六层剥离与跨层传导

V3.2 保留用户提出的六层分析，但每层必须输出事实、推断、替代解释和传导方向：

1. **宏观与规则层**：利率、财政、监管、法币通道、制度变化；
2. **流动性与资金层**：融资成本、美元/稳定币流动性、风险承载、跨市场资金；
3. **标的基本面与管理层**：现金流、协议/产品、治理、供给、管理行为；BTC 无公司管理层时使用网络、供给、矿工/持有者与基础设施状态；
4. **跨资产与 regime 层**：股、债、美元、黄金、主流币和板块联动及其变化；
5. **微观结构与杠杆层**：主动流、盘口、成交、OI、funding、basis、清算代理、波动与韧性；
6. **注意力、叙事与情绪层**：新闻、搜索、社交、受众、恐慌/贪婪和群体行为。

合法传导示例：

```text
监管草案发布
→ 影响对象和实施概率仍未知
→ 相关受众风险预算/交易意愿变化假说
→ 价格、OI、funding、流动性是否出现一致变化
→ 当前状态与竞争路径更新
→ 条件动作计划
```

禁止从一条信息直接跳到开仓，也禁止因为传导链不完整而忽略已经观察到的价格和流动性机会。

---

## 5. 信息主体、主观叙事与群体行为

信息主体继续按市场角色分类：规则/系统权威、流动性与价格形成者、标的管理者、政治影响者、注意力放大者、资金大户、社区/散户群体和未知主体。

每条信息生成两个分离对象：

```text
InformationTruthHypothesis
  内容真实性、正式程度、是否已执行、作用对象

AudienceBehaviorHypothesis
  哪类人看到、如何理解、可能买/卖/观望、资金和约束、影响时钟
```

错误叙事也可能产生真实订单。因此每个叙事至少记录：

- `truth_credence_tier`；
- `audience_adoption_tier`；
- `behavior_translation_tier`；
- `price_impact_tier`；
- 对立叙事、冷漠/无影响假说和失效观察。

Agent 可以分析“护盘、出货、轧空、获利了结、恐慌踩踏”等动机，但只能称行为机制候选；没有身份数据时不得声称已识别主力或机构。

---

## 6. 数据层与动态关系图

数据层继续遵守点时性，但不再用含混的 `event_time <= available_at` 表达所有时间角色。每个 datum 分离：原始 provider 时钟 `provider_observed_at`、按冻结 clock-skew policy 形成的知识安全 `observed_at`、本地实际接收并保存的 `available_at`，以及可选事件/结算生效时刻 `effective_at`。PIT 硬门是 `available_at <= decision_time`；provider 时钟超过冻结容差才失败关闭，容差内必须原样保留 `provider_observed_at`，不得用本地时钟覆盖。datum、bundle 和 axis 的 `as_of` 只能由相应市场组件的知识安全 `observed_at` 派生，不能由 SERVER_TIME、INSTRUMENT metadata、`effective_at` 或未来 schedule 推进。所有对象继续保存 revision、来源、raw digest、missingness 和 dependency group；只有来源或测量合同能确定性验证客观质量时才保存 `quality`，否则使用 `status/admission/reason/claim ceiling`，不得合成质量分数。

OKX funding 的唯一时间映射是：响应行 `ts → provider_observed_at`；在冻结 clock-skew policy 下由它形成知识安全 `observed_at`；`fundingTime → funding-rate datum.effective_at`；`nextFundingTime → 独立 next-funding-settlement-time schedule datum.effective_at`。`fundingTime` 是当前返回 funding-rate 的生效/结算时刻，可能晚于观察；`nextFundingTime` 是下一结算日程。二者都不得冒充 observation time 或推进 PIT `as_of`。

V3.2 图结构固定为：

```text
InformationEvent
→ ObservedFact / PITDatum
→ MarketState / SentimentAxis / ReflexiveLiquidityZone
→ StateHypothesis / AttributionHypothesis
→ ForecastPathHypothesis
→ ActionThesis / RiskTranchePlan
→ Outcome / LearningReceipt
```

合法边包括 `SUPPORTS / OPPOSES / MODULATES / TRANSMITS_TO / MEASURED_BY / INVALIDATES / ATTRIBUTES_RISK_TO`。信息和数据可以共同支持主观假说，但主观假说不能反向改写事实。

同一底层价格增量被描述为“突破、动量、放量叙事”时必须共享 dependency group；图上语言节点变多不能制造独立证据。

十二轴情绪继续保留，不压成单一总分。新增的历史磁区、RSI 和动作 tranche 必须作为 typed nodes 投影到图中，而不是报告层文字。

### 6.1 十二轴来源级别与覆盖声明

十二轴沿用冻结的 `DIRECT / PROXY / DERIVED / UNKNOWN` 来源矩阵，但“有轴节点”与“有原生外部证据”必须分开：

- `DIRECT`：该轴允许的公开原始观测，例如 mark/closed candle、funding 或真实 liquidation feed；
- `PROXY`：只能支持受限描述的替代观测，例如 funding 不能代表完整仓位、单次盘口不能证明流动性韧性；
- `DERIVED`：由已准入 PIT 输入按冻结变换计算，必须保留输入摘要和 dependency group；
- `UNKNOWN`：没有来源通过准入、时钟、质量、覆盖或谱系门；缺失不补零。

每轮图必须同时投影全部十二轴和 `OTHER`，包括 UNKNOWN tombstone，以保存分析空间的完整性；但覆盖声明必须分别报告 `direct_available / proxy_available / derived_available / unknown`，不得因为十三个节点都存在就写成“十二轴原生来源齐全”。来源可用也不等于已经得到方向状态，`single book snapshot → liquidity resilience`、`OI level → leverage change`、`volume level → sell pressure` 等跳跃一律禁止。

---

## 7. 历史形态升级为反身性流动性区域

### 7.1 `ReflexiveLiquidityZone`

每个区域至少包含：

```text
zone_id, instrument, side_or_role
lower_bound, upper_bound, construction_method
created_at, available_at, expires_at
touch_ledger, reaction_ledger
volume_at_price, dwell_time, round_number_relation
orderbook_and_flow_evidence, leverage_evidence, options_evidence
dependency_groups, diagnostic_quality, alternative_zones
rejection_path, absorption_break_path, false_break_path, other_path
```

区域宽度由波动、tick、价差和历史反应确定；禁止用事后结果把单点扩成刚好命中的区间。

### 7.2 强度不是简单触碰计数

反复冲击可能增加可见防守，也可能消耗流动性。分析必须同时看：

- 最近一次反应是否变弱或变强；
- 回撤深度、高低点压缩和停留时间；
- 主动买卖流、成交和盘口补充；
- OI/funding/basis 与价格是否同向扩张；
- 波动收缩后是否扩张；
- 跨交易所和跨资产是否一致；
- 触碰证据是否来自同一 dependency group。

重复触碰的证据贡献边际递减；过多触碰本身不预设看多或看空。

### 7.3 突破加速度

没有期权 dealer gamma 的点时证据时，关口突破后的快速行情建模为：

```text
stop-order cascade
forced-liquidation cascade
liquidity vacuum
attention/momentum feedback
```

只有期权执行价、OI、期限、隐波和 dealer gamma 方向均被合法建模后，才可新增 `GAMMA_HEDGING_ACCELERATION`。

### 7.4 外在路径修饰器：磁区可以是陷阱

`ReflexiveLiquidityZone` 不证明主力护盘，也不能仅凭 K 线和成交量区分“机构吸筹”与“散户抄底”。对 zone 的每条路径新增不进入方向概率云的 `ExternalPathModifier`：

```text
modifier_id, modifier_type, conditions
source_refs, dependency_groups
affected_zone_ids, affected_hypothesis_ids, affected_action_kinds
effect, trigger_effect, protection_effect
created_at, available_at, expires_at, status, invalidators
```

首批类型包括 `FALSE_BREAK_STOP_RUN / LIQUIDITY_VACUUM / FORCED_LIQUIDATION_CASCADE / CROSS_VENUE_DISLOCATION / VENUE_OR_NETWORK_DISRUPTION / EVENT_SHOCK / ATTENTION_MOMENTUM_FEEDBACK`，并保留 `OTHER/UNKNOWN`。它们表达“同一外在事件怎样改变相关路径”，不另造一个方向故事；但必须与被影响对象共享 zone 或 dependency group，禁止用“庄家可能收割”无差别降低或提高全部假说。

因此，窄 stop 被假跌破触发后又快速收回，既不是原多头 thesis 自动正确，也不是旧退出可以改写。它先终结旧 tranche；价格收回、流动性/主动流重新合格且父 thesis 未失效时，只获得创建有界 `ReentryObligation` 的资格，是否得到新风险还必须通过累计预算、次数、冷却、regime 和独立新证据门。

---

## 8. 四类假说与开放发现

每轮至少维护四类对象：

1. `StateHypothesis`：当前市场是什么状态；
2. `AttributionHypothesis`：为什么形成当前状态；
3. `ForecastPathHypothesis`：未来在何条件、何期限内如何演化；
4. `ActionThesis`：现在及未来各节点如何开、加、减、退、反转或等待。

每个对象必须包含：

```text
hypothesis_id, type, scope, horizon
source_subgraph, mechanism
supporting_evidence, opposing_evidence
dependency_groups, alternatives
hard_falsifiers, soft_contradictions
next_discriminating_observation, expiry
parent_revision, regime_scope
subjective_plausibility_tier
```

方向性假说必须存在至少一个反向竞争假说；每个集合保留 `OTHER/UNKNOWN`。反向假说可以共享部分事实，但必须提出不同机制、条件或路径，不能只是把结论中的“涨”改成“跌”。

Agent 可从残差新增方向，不受固定假说槽位限制；active working set 有界，未进入当轮的候选留在 discovery pool。

### 8.1 非方向状态不是多空残差

每轮必须单独封存 `MarketRegimeState`：

```text
TREND_UP / TREND_DOWN / NEUTRAL / RANGE / CHOPPY /
VOLATILITY_WITHOUT_DIRECTION / TRANSITION / OTHER / UNKNOWN
```

`CHOPPY` 表示频繁反转、方向延续性差且成本磨损占优；`VOLATILITY_WITHOUT_DIRECTION` 表示预期波动扩张但方向证据不足；`TRANSITION` 表示新方向尚未通过转换证据门。`NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 都不是“多空各给一点”的折中，也不要求伪造非零 LONG/SHORT 档位；这些状态令当前方向新增风险为零，突破路径只能保留为尚未触发的条件计划。任何该类风险候选都必须为 `CONDITIONAL/BLOCKED`、不得生成 tranche，且所有非空 `zone_refs` 必须逐项解析为已封存的 `BREAKOUT_BOUNDARY`；普通支撑/阻力或自由文本“突破”不能取得资格。`RANGE` 明确排除在该强制零集合之外：只有边界、成本、失效条件和均值回归路径完整时，才可保留条件性区间计划。当前不可执行实验只记录条件，不生成上下双向真实挂单。卖出波动率、期权组合或同时触发的双边订单不在当前权限和产品范围内。

非方向标签不能只靠一句 Agent 判断生成。`CHOPPY` 必须同时具备“方向延续性低、反转频率高、执行换手/成本压力高”的 typed feature assessment；`VOLATILITY_WITHOUT_DIRECTION` 必须同时具备“方向延续性低、实现波动高、方向失衡为平衡”的 assessment。每项都要引用当前 PIT 证据并落入冻结的可观测族；目标状态至少使用两个物理引用和两个可观测族。单一 K 线、无关新闻或一个重复引用不能制造混沌标签。状态改变时，这些 feature 引用还必须进入本次 fresh transition evidence；从非方向状态恢复方向状态仍须既有的双机制差异门，而不是反向使用一个价格点强行恢复开仓资格。

### 8.2 期限、过期和续期

每个假说实例必须有 absolute expiry。到期未被证实也未被证伪时，其状态变为 `EXPIRED`，立即失去支持新风险和维持未触发条件计划的资格；`STALE` 只作为复核原因，不是可继续行动的状态；不得只把 `expires_at` 向后移动。

续期必须创建可追溯的新 revision，绑定旧摘要、旧 expiry、新的点时证据、重新检查后的 regime/zone 和新的 falsifier。没有新信息时只能回到 discovery/review，不能把“仍有可能”当作续期证据。固定“到期降一档”仅可作为一个预注册 policy arm；TTL 和档位迁移规则必须按假说类型、时间框架和 regime 事前冻结，不能在看到结果后选择。

---

## 9. 序数主观支持 V3.2.1

0–100 的主观分数会把不可重复的语言判断包装成精确仓位输入，因此被永久移除；不保留兼容别名，也不允许界面或编译器把三档再插值成 37、70、90 等伪精确数字。Agent 的主观判断只能选择：

```text
EXTREME_UNCERTAINTY  当前方向风险上限单位 0
LOW                  当前方向风险上限单位 50
HIGH                 当前方向风险上限单位 100
```

这些单位只是冻结的离散风险上限，不是概率、收益预测或仓位百分比。Agent 对方向假说只提交上述支持档位，对 `OTHER/UNKNOWN` 只提交同一套 `residual_uncertainty_tier`；sealed plan 才能确定性地使用其补集形成 residual cap。Agent-authored risk/action submission 不再出现 `residual_uncertainty_quality`、`DEGRADED=50` 或其他会缩放风险的 quality 别名；当前 action-evaluation 仍回传连续的 `risk_reference_units` 作为 sealed plan 的冗余派生值，但 compiler 会逐项重算并要求 exact match，它不是 Agent-authoritative 分数或可调仓位旋钮。zone/source/outcome 中由 owning verifier 形成的客观或诊断性 `quality` 可以保留，但绝不进入主观风险算术。实际风险只由方向支持上限与 residual cap 约束基本包络，再受已接线的 typed regime、事实完整性、objective contract-input 与已构造 tranche geometry 验证，以及 path modifier 的非膨胀 cap 约束；真实执行 `MAX_LOSS` 只关闭未来 executor。coverage 只保留诊断，不再形成风险标量。流动性、成本或几何的 Agent 判断若没有 typed owner，只能作为 guard/比较材料，不能直接把候选标成 `BLOCKED`。`HIGH` 绝不能越过基本风险包络。档位必须由证据密度、机制一致性、反证、新鲜度和可否证性共同说明：

- 首轮必须绑定当前 PIT 证据、反向假说和 falsifier；无可解析依据只能是 `EXTREME_UNCERTAINTY`；
- 跨轮变档必须绑定新增、失效或冲突证据；档位未变时不得伪造 update refs；
- 禁止在一轮内从 `EXTREME_UNCERTAINTY` 直跳 `HIGH`，反向亦然；必须经过 `LOW`，除非 hard falsifier 直接使假说终结并归零；
- `FALSIFIED/EXPIRED` 对新风险贡献恒为零；缺失数据不是看多或看空证据；
- 稳定输入、稳定证据集和相同前序状态必须得到同一档位，实验记录档位抖动率，但小样本不称为校准。

### 9.1 依赖身份与增量风险聚类

共享主要事实、失效位或行为机制的假说仍组成 `HypothesisDependencyCluster`，以防同一走势被写成五个故事后放大五倍风险。普通 15 分钟轮的**构造路径**使用 pilot 有界 working set、已封存 cluster identity 和新 delta 增量更新，不重新生成不变的历史 revision；当前没有独立、固定的 24 小时同类证据归并能力，本文其他 `24h` 只指 reentry churn ledger。但 owning verifier 仍须在一个 acceptance/public-evidence verification scope 内，从累计图完整重建当前 evidence dependency closure **一次**，并与提交的完整 closure 精确比较；随后投影、registry 和 Agent market-view 重建只在该 owner-bound scope 内复用该成功验证结果。复用严格绑定同一线程/async task、同一递归 strict built-in JSON 快照与该 scope 生命周期；失败、caller mutation、custom Mapping、scope 退出、跨 wake/thread/task/process 均不得命中。Proposal、Selection 和 audit 可以复用已封存的 digest-bound 材料，但各自进入新的 owning verification boundary 时仍须执行该边界要求的完整重放；不得把“无跨阶段 cache”误写为“无需验证”，也不能把未触及的旧行视为天然可信。

cluster 的有效档位取仍可行动成员中的最高离散档位；成员共享 cluster 只产生一个风险单位。跨 cluster 的差异必须来自预先封存的来源、实质观测机制与失效条件，不由 Agent 在看到动作预算后临时声明。这里的 `mechanism-distinct evidence` 只是防止同一观测被重复计数的合同条件，不等于、也不声称统计独立。缓存只减少重复计算，正式原件、成员全集和物理绑定仍可全量重放；任何文件身份变化或谱系冲突都使缓存失效。

### 9.2 对立支持与混沌的含义

多空、突破/拒绝或趋势/反转可以同时为 `HIGH`，代表接近关键分岔而非“模型矛盾”。此时允许：

- 两个互斥的条件计划；
- 更小的先行 probe；
- 等待一个高区分价值观察；
- 波动型而非方向型研究假说；
- 显式 `NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN`，当前方向风险为零；结构化 `RANGE` 不自动归零。

OTHER/UNKNOWN 的增强降低总可分配风险，但不把所有未来条件计划强制删除。处于上述非方向 regime 时，任何 risk-increasing candidate 必须同时满足 `plan_state=CONDITIONAL / feasibility=BLOCKED / risk_tranche_id=null / current reference risk=0`，并且其非空 `zone_ids` 全部绑定 sealed `role=BREAKOUT_BOUNDARY`；这只表达“方向 regime 转换后重新分析”的未触发计划，不表示已经挂出上下双边订单。

对立要求只保证方向候选完整，不保证两侧都有非零档位或可行动。LONG/SHORT 模板可以是 `EXTREME_UNCERTAINTY`、被风险门阻塞或只保留为 residual candidate；非方向 regime 本身是一级状态，不需要把它摊进多空。禁止为了“任何时候都要有做多假说”伪造支持证据或强制最低仓位。

---

## 10. 严格路径与提前行动

路径语言改为允许“预期前缀尚未确认、但风险可定义”的 probe：

```text
OBSERVE current_state and zone
IF integrity/risk/permission hard guards pass
AND anticipatory trigger or reaction trigger is TRUE
THEN reserve or open PROBE tranche

IF confirmation evidence arrives
AND original thesis survives
AND refreshed geometry remains valid
THEN ADD / promote tranche

IF soft contradiction accumulates
THEN REDUCE / tighten / shorten horizon

IF hard falsifier or max-loss guard triggers
THEN CLOSE

IF old thesis survives after exit and new opportunity reappears
THEN REENTER under a new tranche/episode receipt

ELSE preserve OTHER/UNKNOWN and review at an absolute time
```

每个动作仍要绑定 trigger、guard、invalidator、absolute horizon、next observation 和 opportunity cost。`UNKNOWN_DIRECTION` 可支持 probe；依赖当前证据的真实 `UNKNOWN_FACT_INTEGRITY` 与 compiler-owning 的 `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 不可。dynamic-state legacy `UNKNOWN_MAX_LOSS` 属于 instrument-wide future-execution gate，不是当前方向比较旋钮。

---

## 11. 动作空间与机会状态机

### 11.1 完整动作域

```text
OPEN_PROBE / ADD / HOLD / REDUCE / CLOSE / REENTER / REVERSE / WAIT
```

方向作为独立字段：`OPEN_PROBE/ADD/REENTER/REVERSE` 必须为 `LONG/SHORT`；`HOLD/REDUCE/CLOSE` 引用当前 research intent；`WAIT` 为 `NONE`。`HOLD` 与 flat `WAIT` 严格分离：前者显式维持既有 exposure intent/tranche 并承担维持风险，后者表示尚不建立或不改变 exposure；不得重现旧系统把有敞口 HOLD 当作空仓 WAIT 的已知错误。报告中的 `OPEN_CORE` 是 probe 获得新证据后的 `ADD/promote`，`PARTIAL_HARVEST` 是 `REDUCE` 的管理原因，非独立顶层动作。

确定性系统根据当前状态枚举所有合法动作；Agent 不能删掉相邻动作或预先选择。

### 11.2 机会状态机

```text
DISCOVERED
→ WATCHING
→ PROBE_ELIGIBLE
→ PROBE_PLANNED
→ CONFIRM_ADD_ELIGIBLE
→ CORE_OR_RUNNER
→ DEFEND_OR_HARVEST
→ CLOSED_WITH_REENTRY_OBLIGATION | INVALIDATED | EXPIRED
```

当前 public-only 实验只保存 `ExposureIntent/ConditionalActionPlan`，不产生 fill、lot、PnL 或真实 portfolio mutation。

### 11.3 WAIT 约束

WAIT 不再是零成本默认动作。选择 WAIT 必须证明：

- 所有 probe 候选被 typed 数据完整性、损失边界、权限、已验证 objective-input 缺失或其他 owning hard gate 阻塞；未接线的费用/流动性主观判断与“明显劣势”只能支持 Selection 比较，不能自行删除候选；或
- 等待的新增信息价值高于立刻小额试探，且有明确最晚复核时点。

仅写“市场不确定”“证据不足”“等待确认”无效。报告必须计算或定性登记 `delay_cost / missed_move_risk / information_value / review_deadline`。

---

## 12. 风险预算与假说—仓位归因

### 12.1 分配风险，不直接分配名义

对 tranche `j`：

\[
UnitLoss_j = Multiplier\cdot|P_{entry}-P_{stop}|
+Fee_{stress}+Slippage_{stress}+Funding_{bound}+Tail_{gap}.
\]

\[
q_j=\operatorname{floorToLot}\left(\frac{R_j}{UnitLoss_j}\right).
\]

总风险上限：

\[
B_t=\min(B_{episode},B_{symbol},B_{portfolio},B_{daily},B_{liquidity}).
\]

当前无账户实验不再使用量纲不明的 `1`。raw envelope 被定义为精确 `1 USDT` 的**非账户研究压力比较单位**；它只用于比较不同条件计划在同一冻结压力政策下的相对损失，不是账户风险、可用余额、下单名义或最大损失。Agent 无权把它改成 `0.4`、`90` 或任何其他值。

正 reference risk 还必须绑定当前 PIT 中已观测且通过 owning verifier 的 OKX 合约规格：`Multiplier=ctVal×ctMult`，价格按 `tickSz` 对齐，研究数量按 `lotSz` 向下取整且不得低于 `minSz`。手续费、滑点、funding 与 tail-gap 项按 `ctVal×ctMult×conditional_entry_reference×frozen stress rate` 逐 tranche 推导，Agent 不能提交替代值。当前冻结 rate 只是事前研究压力假设；真实账户费率、真实滑点和尾部最大损失分别保持 `UNKNOWN_NOT_ACCESSED / UNKNOWN_NOT_OBSERVED / UNKNOWN_NOT_DEFINED`。任一合约规格缺失或无效时，正风险候选失败关闭，只允许零风险 WAIT。由此得到的 `q_j` 仍只是 research-comparison contracts，不是可执行订单数量；未来真实 portfolio 映射必须由另行授权、绑定账户与执行真值的 adapter 提供。

### 12.2 离散支持只设上限，不制造风险

连续主观分数和 `W_c/ΣW` 一并废止。唯一一个 LOW 假说不能因为分母中没有竞争者而取得全部预算；五个同向故事也不能靠相加变成超强确信。先计算有效预算：

\[
B^{eff}_t=B_t\cdot
\min(S_{abs},S_{residual}).
\]

其中 `S_abs` 只取通过全部硬门的方向 cluster 中最高主观支持档位对应的上限：`EXTREME_UNCERTAINTY=0 / LOW=0.5 / HIGH=1.0`；`S_residual` 由 OTHER/UNKNOWN 的最高档位反向派生。二者由 sealed plan 重算，不是 Agent 可填写的数字，更不是市场概率。多个 cluster 不相加；实质机制不同的 cluster 数量也只影响计划覆盖和 tranche 内的离散优先级，不能扩大总风险包络，更不表示统计独立。

- 同一 dependency cluster 内只保留最高有效档位，成员故事不叠加；
- LONG 与 SHORT 是互斥条件分支，绝不相加制造虚假确信；总风险包络取较强方向，但每个方向的 cluster 合计还必须受本方向档位与 residual cap 的较小者约束。另一方向的 `HIGH` 不能把本方向 `LOW` 抬升到半档以上；增加同侧 cluster 数量也不能提高该方向上限；
- `S_residual` 随 OTHER/UNKNOWN/混沌上升而下降；
- hypothesis evidence-chain coverage 只保留为可重放的 `COMPLETE/INCOMPLETE` 诊断，不参与风险乘法；dynamic state 若没有 source-admission coverage，必须明确记为 `UNKNOWN_NOT_IN_DYNAMIC_STATE`，不得用 hypothesis 引用数伪造；
- 已有 typed owner 的 regime、事实、objective contract inputs 与已构造 tranche geometry 是硬可行性验证：不合法即零风险或拒绝计划，合法也不额外缩放；真实执行 `MAX_LOSS` 只阻断未来 executor，不能删除当前某一研究方向；尚无 typed owner 的流动性/成本/geometry 主观判断只进入 guard、rationale 与 Selection 比较，不改变 feasibility，禁止 `DEGRADED=0.5` 一类吸引力魔法档；
- path modifier 可在已经合法的候选上使用冻结 `ZERO/HALF/NORMAL` 非膨胀 cap，不能增加支持或解除任何硬门。

初始 `HIGH` 或 `LOW→HIGH` 必须绑定至少两个 fresh refs，并保留明确、当前可用的方向性反证。真实 formal OKX 图中的 `605/605` 条 closure 都共享 `VENUE:OKX`；若机械要求完整 closure 全不相交，`HIGH` 会结构性不可达。完整 graph dependency closure 因此仍原样保存并参与重放；判定两条 refs 是否具备 `mechanism-distinct evidence` 时，只忽略共同的 `VENUE` 与 `PROJECTION` provenance，其他物质依赖仍必须不相交，同时要求不同 `REQUEST` 且不同、可用于方向判断的 `OBSERVABLE_FAMILY`。`TICKER/MARK/CANDLES` 统一属于 `PRICE_ACTION`，所以 candle+candle、ticker+candle 或 mark+candle 不能互相抬升为 `HIGH`；`PRICE_ACTION` 与 `TRADE_FLOW/POSITIONING/FUNDING_CROWDING/ORDERBOOK_LIQUIDITY` 等不同实质观测机制才可能满足该门。`PROVIDER_METADATA/CONTRACT_SPEC` 不是方向证据，不能充当支持或反证。该门只防止伪双证据，不表示统计独立或因果识别。进入非方向 regime 可由一条 fresh hard evidence 支持；从非方向恢复为方向必须满足同一双机制差异 fresh refs 门，或由系统从连续两根合格闭合 15m bar 机械重算，不能由 Agent 自报。

依赖候选的 `UNKNOWN_FACT_INTEGRITY`、compiler 证明的 `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN`，或 regime 为 `NEUTRAL/CHOPPY/VOLATILITY_WITHOUT_DIRECTION/TRANSITION/OTHER/UNKNOWN` 时，当前方向 reference risk 为零；`RANGE` 仅在结构化边界条件完整时保留条件路径。真实执行权限与 legacy dynamic token `UNKNOWN_MAX_LOSS` 始终关闭未来 executor，但不充当单边研究 feasibility 理由。当前不可执行实验的 `B^{eff}` 始终只是 reference risk。Agent 的档位只能降低这个上限，不能提高由客观风险条件给出的预算。路径 modifier 也只使用 `ZERO/HALF/NORMAL=0/0.5/1`：support 不放大，modulates/opposes/unknown 为半档，invalidates 为零。

### 12.3 离散 cluster 风险分配

对通过硬门且实质机制不同的 cluster，不再按主观数字比例切分。确定性分配器先在全局 `B^{eff}_t` 内按 LONG/SHORT 自身离散档位设方向容量，再在每个方向内部用冻结 tranche 单位切分：HIGH 得两个单位，LOW 得一个单位，`EXTREME_UNCERTAINTY` 得零；同档按稳定 ID 作确定性余数量子分配。必须同时满足“全局合计不超过 `B^{eff}_t`”与“任一方向合计不超过 raw envelope × min(本方向档位上限, residual cap)”；任何方向都不能借另一方向的更高档位或增加 LOW cluster 数量越过自身上限。这里仍不声称统计独立。若方向触发互斥，分配只作为 conditional reservation；若可能同时触发，压力测试必须按同时发生计算。

### 12.4 `HypothesisRiskAttributionMatrix`

每个 tranche 记录：

```text
tranche_id, direction, entry_mode, zone
risk_budget, unit_loss, derived_quantity_or_reference_scale
supporting_cluster_ids, discrete_contribution_units
shared_falsifiers, independent_falsifiers
stop/target/time/event management plan
```

假说变化时，系统根据 attribution matrix 提议减仓或取消条件 tranche；不会因为一段自然语言被重写就改仓。

---

## 13. 入场模式：从确认追价到分层抢跑

### 13.1 `ANTICIPATORY_PROBE`

适用于：结构磁区、衰竭、反身性关口、超卖/超买但尚未确认反转、事件前非对称几何。要求：

- 初始风险只占机会预算的小部分；
- 有明确失效区域而非随意百分比；
- 费用/滑点后仍有足够收益空间；
- 反向假说和取消条件完整；
- 期限短于 core thesis。

### 13.2 `REACTION_ENTRY`

预期的拒绝、补回、主动流转向或结构响应已经观察到；风险可高于 probe，但仍需避免在反应末端追价。

### 13.3 `BREAK_ACCELERATION`

15 分钟闭合或事件级突破配合主动流、波动扩张和流动性变化时进入。必须同时管理假突破、拥挤反转和晚到成本；没有 4H 确认不是阻塞，只提高失效速度和降低初始风险。

### 13.4 `RETEST_OR_REENTRY`

突破后回测、部分退出后重新获得支撑或原 thesis 仍存续时触发。使用新 opportunity/tranche receipt，不改写旧退出。

---

## 14. 金字塔、减仓、反转与再入场

### 14.1 加仓

加仓必须满足：

1. 新的非重复证据使原 cluster 的主观支持档位合法升档，或新增机制上可区分的 cluster；
2. 原 thesis 未 hard-falsified；
3. 当前价重新计算的剩余收益和失效距离仍合格；
4. 加仓后组合压力损失未超过硬上限；
5. 新 tranche 有独立 stop/management plan；
6. 不以亏损摊平为目的。

其中 `ADD/REENTER/REVERSE.new_evidence_refs` 只能引用候选假说中显式列为 `supporting_refs` 的当前 sealed PIT evidence digest；该 digest 必须存在于当前 `agent_market_graph_view.citable_evidence_records`，满足 `available_at <= current_dynamic_state.as_of`，且 Cycle 2+ 必须严格晚于前序 dynamic state/前序 availability registry 的共同 cutoff。上一轮是否引用过不是 freshness 判据；旧但漏引的 datum、任意字符串、`opposing_refs`、裸 zone ref、降档 `tier_update_refs` 或仅用于续期的 ref 均不能授权新增风险。若不存在这样的 fresh positive support，候选必须以 typed `NO_NEW_EVIDENCE` 和系统固定 sentinel 阻断，不能为了可构造 plan 伪造新引用。

允许先 `probe`、再 `confirm add`、最后 `runner add`，但层数和比例须在实验合同事前冻结。

### 14.2 减仓

软反证、支持档位下降、波动/流动性恶化、相关暴露上升、事件临近或机会成本变化都可触发 REDUCE；不必等待 hard stop。

### 14.3 反转

反转不是一个原子“翻仓”。必须先关闭/取消旧方向，再为新方向建立独立 opportunity、风险预算、失效位和 receipt。没有新方向证据时只 CLOSE，不自动 REVERSE。

### 14.4 再入场

退出只终结当前 tranche，不自动终结战略 episode。若父 thesis 仍存续，系统可以创建 `ReentryObligation`，但“观察义务”绝不等于“必须再次开仓”。每个 obligation 必须绑定耐久 `ReentryBudgetState`：

```text
failure_cluster_id, direction, rolling_window
attempt_count, cumulative_reference_risk
consecutive_failed_reentries, cooldown_until
last_exit_binding, independent_reentry_evidence_refs
regime_at_exit, reset_reason, predecessor_digest
```

当前 pilot 对单一 instrument 使用一个全局 churn breaker：精确 `24h` 绝对窗口、每次最多 `1` 个 non-account reference-risk unit、最多 `2` 次 ledger 激活后的 instrument-level 风险再参与研究尝试，因此累计硬上限由合同唯一派生为 `2 = 1 × 2`；这些值不接受 Agent 覆盖。累计值必须按 `0.000001` 量子对齐，并满足 `attempts×0.000001 <= cumulative <= attempts×1`。ledger 尚为 `INACTIVE` 时的首次 `OPEN_PROBE` 不计作重入，但下一 durable plan 必须进入 `INITIAL_PROBE_USED`，不能再伪装第二次免费 initial probe；该锁不禁止有新反向依据的纠偏 OPEN/REVERSE，而是要求它精确计入同一个 attempts/cumulative。首次 stop 已把 consecutive failure 记为 `1`，之后任一计数尝试若再失败即达到 `2` 并熔断；没有失败但已用完 attempts/cumulative 同样阻断 churn。真正反向的 `REVERSE/OPEN_PROBE` 可以保留动作语义，不能因此获得免费次数。同轮接纳前必须满足 `attempts_used < max_attempts`，单次 selected reference risk 不超过 `1`，且不超过剩余额度。达到次数、累计或连续失败上限后，cooldown 精确指向原 24h 窗口终点；原窗口到期前禁止 RESET，即使出现新 cluster、regime 转换和新 tranche 也不得清零。failure 不能只凭“与路径有关”：generic source、supporting、renewal、tier-update 或普通 zone observation 均不能证明失败，只有 exact parent 的 fresh opposing ref 或 active typed invalidation 合法。该计数只防不可执行研究计划反复，不代表真实成交、止损或账户磨损；未来 executor 须另以 fill/position truth 计数。

---

## 15. 动态保护、止盈和 LockedNet

保护候选由以下对象共同形成：

```text
STRUCTURAL_INVALIDATION_STOP
VOLATILITY_NOISE_FLOOR
LIQUIDITY_STRESS_BUFFER
TIME_STOP
EVENT_RISK_REDUCTION
LOCKED_NET_TRAIL
PARTIAL_HARVEST
RUNNER_TRAIL
```

保护位只能向降低压力损失方向移动。`+3%→成本、+8%→+5%、+15%→+10%` 只允许作为一个候选 policy arm；通用策略使用 `R`、ATR/实现波动、结构里程碑、费用和 gap stress。

对 long，新的 stop 至少满足：

```text
new_stop >= previous_stop
distance_to_market >= minimum_noise_and_execution_buffer
stress_loss <= remaining_risk_budget
```

对 short 对称。若收紧到成本会落在噪声带内，可优先部分减仓而不是制造高概率扫损。

`LockedNet` 由保护位的压力成交价扣除双边费用、滑点、funding 和 gap buffer 后计算。只有正的 LockedNet 才能释放风险预算；浮盈本身不是“市场的钱”。

目标位首先触发 `PARTIAL_HARVEST / TIGHTEN / RUNNER / REASSESS`，不默认 `CLOSE_100`。

### 15.1 stop 是触发，不是保证成交

`P_stop` 只是风险动作的触发边界，绝不是退出成交价。每个 risk tranche 必须有正的 slippage 与 tail-gap stress buffer，并完整登记 `STOP_THROUGH_OR_GAP / LIMIT_NOT_FILLED_OR_QUEUE_LOSS / RATE_LIMIT_OR_REJECTION / NETWORK_TIMEOUT_OR_PARTITION / VENUE_UNAVAILABLE / CANCEL_REPLACE_RACE / PROTECTION_ACK_UNKNOWN` 七个分支；漏掉任一分支均不合格。当前公开 PIT 中合约规格或冻结研究压力输入不可验证时，compiler-owning `RESEARCH_REFERENCE_LOSS_BOUND_UNKNOWN` 令当前正 reference-risk 归零；交易所中断、真实费用/滑点或账户尾部损失无法定义时，legacy dynamic token `UNKNOWN_MAX_LOSS` 只阻断未来 executor，不得据此删除当前某一研究方向。

当前实验没有交易 API，也没有真实持仓，只能把这些分支写入研究计划和后续公开价格 outcome；因此本轮不会伪装实现“市价核按钮”，也不得用假设值宣称网络/API 延迟上限。当前 `future_latency_bound_ms=null`、`latency_qualification_status=UNKNOWN_NOT_QUALIFIED`、证据引用为空，execution gate 始终 blocked。`EmergencyExecutionCapsule` 的机器状态固定为 `NOT_IMPLEMENTED_NOT_QUALIFIED`；当前 `RecoverySupervisor` 只是只读实验观察者，`supervisor_is_execution_risk_supervisor=false`，不是仓位风险守护进程。未来只有另行获得执行授权并完成实测资格，执行系统才可封存非空延迟界限，并必须独立于 Strategy Agent 与当前 recovery observer 建立该 capsule：

1. 只有 venue 支持原子 attached protection 时，保护才可与入场同一请求提交，并且必须独立确认保护最终状态；不支持原子附带保护的 venue/执行模式默认禁止新增暴露，不能在零持仓时假设先挂 reduce-only；
2. 若入场 fill 已发生而 attached protection 尚未确认，状态立即成为 `UNPROTECTED_EXPOSURE`：冻结新增/加仓/reentry，停止把 ACK 当作最终状态，并从独立 position truth 对账；
3. 对 `UNPROTECTED_EXPOSURE` 或已有暴露且保护状态未知，按预授权阶梯执行 `cancel/open-risk freeze → reduce-only IOC/marketable close → reconciliation`；只有另行取得明确的未来执行授权，才可进入 `market close fallback`。每步使用幂等 client ID、有限超时和 ACK/最终状态区分，仍不保证成交；
4. 两条独立传输均不可用时进入 `EXPOSURE_UNRESOLVED_VENUE_UNAVAILABLE`，触发本地告警与人工应急渠道；不得声称已经清仓或最大损失仍可定义；
5. 无论请求链显示成功或失败，终态都必须从独立仓位真值完成 reconciliation；恢复连接后先对账订单、成交和仓位，再决定是否继续；禁止在未知旧仓位上新开反向仓模拟“平仓”。

以上只是未来执行层的最低设计合同，不是已实现能力，更不是保证价格或保证成交。启用前至少还要独立验证：执行授权与账户/仓位真值、venue 原子保护、订单/成交/仓位状态机、幂等 reduce-only 与 fallback、partial fill/over-close/超时/对账、冗余传输与 degraded mode、外部告警/人工 ACK，以及延迟/分区/venue outage chaos 测试。交易所整体失效、市场停摆、断层跳空和强平先于请求仍无法由本地系统消除；任何文档不得承诺“无论价格多少一定清空”。

---

## 16. 多时间框架与增量分析

### 16.1 三种 frame

```text
StrategicContextFrame
  宏观、规则、日线/4H regime、跨市场、慢频基本面

TacticalDeltaFrame
  1H/15m 结构、磁区、成交、OI、funding、波动、情绪变化

TriggerFrame
  最新闭合 15m、事件到达、快速流动性/价格异常
```

每个 frame 有 `as_of/available_at/expires_at/invalidation_events/digest`。StrategicContext 只在前序帧已验证、绝对 TTL 未到且当前已验 bundle 的稳定战略投影（慢周期序列、source coverage、axis admission）逐字相同时 carry；carry 不续期、不换 source refs，并绑定前序 frame digest。三类 frame 的 payload digest 都必须在正式 acceptance 中由当前 bundle 独立重算；每个 REFRESHED frame 还必须精确绑定固定 frame ID、`created_at=decision_time`、当前 bundle 的 `as_of/available_at`、角色 TTL `86400/3600/900` 秒、当前公开 source refs 及冻结 dependency/invalidator sets，不能用一个自洽摘要把超长 TTL 或伪来源带入 acceptance。TACTICAL/TRIGGER 每轮刷新；CARRIED_FORWARD strategic 则只接受前序不可变字段，不换成当前来源。当前公开来源没有能证明“宏观/监管/跨资产事件类型”的 owning event schema，因此 non-TTL invalidation 保持 `UNKNOWN_NOT_AVAILABLE`、进入 DataGap/manual plan，并在 formal acceptance 拒绝自由文本或任意 PIT digest 注入；当前只接纳可重放的 TTL 与稳定投影变化，不能宣称八类 invalidator 已完整接线。

### 16.2 高低周期关系

日线和 4H 是先验及风险不对称，不是绝对禁令：

- 顺高周期方向：允许较高的总机会预算和较长 horizon；
- 逆高周期方向：只允许较小 probe、更快否证和更严格加仓条件；
- regime 转换候选：允许双向条件计划；
- 高周期信息过期或冲突时显式 UNKNOWN，不沿用旧方向。

### 16.3 速度预算

目标运行预算：

- 初始/全量轮：允许约 15 分钟；
- 15 分钟 delta 轮：目标 1–2 分钟；
- 若 Agent 超时，保留上一已封存计划并按其保护/过期条件处理，不用半成品改状态。

运行预算是资格门而不是愿望。正式 runtime 必须预计算已封存的 dependency identity、cluster membership 与当前 delta，只对新增/失效节点传播变化；Proposal 和 Selection 共用同一份封存材料。当前并不存在固定时间窗的同类证据自动归并器。每次完整全量重放只用于进程启动、资格、缓存失效、重大 regime 变化和审计抽查，不进入每个 append-only 子阶段。正式实验前必须证明：单个 15 分钟周期在冻结环境中留有 outcome 宽限余量；若未达标则保持 NO-GO，不能靠删验证或缩短 Agent 输入伪造速度。

2026-08-08 的本地性能复核先观察到：旧长测超过 `5m` 尚未完成，其中 `setUpClass` fixture 约 `216s`、receipt reconstruction 测试体约 `32s`，测试体累计触发 `59,018` 次 `canonical_bytes` 与 `28,822,997` 次 normalize。根因不是完整验证本身，而是同一不可变对象在 lifecycle/acceptance 级联中反复 canonicalize/normalize。修复采用 request/receipt-scoped memo，并把安全边界收紧为：key 与 verifier 使用同一份递归精确内建对象快照；custom Mapping 不缓存；owner 同时绑定 thread 与 asyncio task；scope 退出清空；失败不缓存；不跨调用、线程、task 或进程，也不信任 Agent 自报 digest。context shard 的 growing candidate 使用精确增量 size，最终仍执行完整 build、自摘要与 actual-byte 复核。严格快照/owner 修正后受影响五模块 `73/73 PASS / 154.221s`，原慢测 `44.255s`，独立 TOCTOU/custom-Mapping/thread-task/shard 复核 `4/4 PASS / 42.327s`。这些结果本身只证明本地确定性重放加速；后续第七资格另行证明了 fresh-process 与 fresh PUBLIC_SOURCE 子门。跨唤醒 Current Codex、固定 outcome monitor、完整 15 分钟周期与 outcome 宽限仍为 `UNKNOWN_NOT_QUALIFIED`，绝不外推为市场预测或实盘执行能力。

### 16.4 长期无动作监督

无仓位不等于无研究。每个 15 分钟轮继续更新假说、区域、主观支持档位、机会成本和同 cohort shadow baselines。休眠监督使用两只互不替代的耐久时钟：

1. `testable_risk_plan_clock`：只有新的、合格且获得正风险预算的 probe/reentry 计划才能重置；市场状态变化、换 ID 或改写文字不能重置；
2. `model_adaptation_clock`：只有由新鲜 PIT 证据绑定的 material state/zone/hypothesis/threshold 变化才能重置；普通 heartbeat、重复分析或无关新引用不能重置。

本 16-cycle pilot 对任一时钟连续 `8` 个周期或 `7200` 秒（任一先到）触发对应 `INACTIVITY_REVIEW`。两只计数都必须从 durable 前一 action plan 推进，Agent 不得自行重置：

- 重检 regime 是否错分、TTL 是否过长、阈值是否失配、数据是否退化；
- 搜索新的相反假说、时间框架或标的候选，但只对未来生效；
- 比较 WAIT、简单趋势、常持有/现金基线的机会损失；
- 判断系统是在合理等待，还是已经成为不产生可检验决策的黑箱。

该监督不设置最低仓位，也不为“获取样本”强制交易。现金、通胀或替代资产机会成本只有在计价资产、可投资基准、费用和同一时点被冻结后才能量化，否则只作定性登记。

---

## 17. RSI 的 V3.2 角色

RSI 使用 CORE v2.1 已冻结的 closed-bar、availability、gap、方向独立和同 cohort 约束。

合法假说角色：

1. 极值后衰竭/反转候选；
2. 价格与 RSI 背离；
3. failure swing；
4. 强趋势中的中轴重置与再加速；
5. 与磁区、主动流和多周期结构共同触发 probe；
6. 作为反证：极值持续且结构继续扩张，拒绝过早逆势。

RSI 可提高分析与触发优先级，但不能单独提高 risk budget。必须预注册以下对照：

```text
NO_RSI
RSI_TRIGGER_ONLY
RSI_FILTER_ONLY
RSI_PLUS_STRUCTURE
RSI_PLUS_STRUCTURE_AND_FLOW
```

在前向结果完成前，RSI 的净增量仍为 `UNKNOWN_NOT_EVALUATED`。

---

## 18. Agent 最大化与确定性系统边界

### 18.1 Agent 拥有的判断

- 信息角色、受众、动机和行为传播的竞争解释；
- 当前/归因/预测/行为四类假说的新增、拆分、修订和否证；
- 非校准 `subjective_plausibility_tier` 及其依据；
- 历史磁区的机制解释和竞争路径；
- 各合法动作的语义、机会成本、进攻理由和风险理由；
- 哪个新观察最有区分价值；
- sealed evaluation 后的一次最终研究选择。

### 18.2 确定性系统拥有的事实

- raw、时间、PIT、revision、来源、schema 和 digest；
- 数据质量、依赖去重和图类型；
- 合法动作全集、风险/成本/数量/保护位复算；
- authority、Supervisor、单次尝试、commit、outcome 和恢复；
- 不允许 Agent 修改的历史、账户/权限和结果。

### 18.3 两阶段协议

Proposal 阶段必须为所有合法动作给出理由，禁止 selected。中间层封存：事实、序数支持档位、预计算 dependency cluster 身份、动作风险和机会成本。Selection 阶段只能从已封存候选选择。

V3.2 新增强制项：如果至少一个 probe 通过硬门，Agent 选择 WAIT 时必须逐项解释为什么该 probe 被机会价值、成本或风险支配；“不确定”本身不是理由。但当 typed regime 为 `CHOPPY/VOLATILITY_WITHOUT_DIRECTION` 时，方向风险为零是合法结论，不能被 WAIT 机会成本条款反向强迫开仓。完整来源工件和累计图继续耐久保存；Agent 接收由这些原件确定性构造的有界市场图视图，正常 delta 轮复用已验证 cluster/closure 缓存，只传播依赖变化。视图必须逐条保留全部可引用 evidence digest、可得时间、closure status、完整 dependency-group IDs、exact owning-closure digest 和四类计数；只把供确定性重放、但不构成 Agent 市场判断语义的完整 evidence-ref/node/association ID 列表留在 verified graph registry。Application owning verifier 必须从该 registry 重建每一条视图记录并精确比较，调用者不得自报摘要或计数。任何必需对象数或 UTF-8/canonical 字节超限都在调用前失败关闭，禁止 top-k、漏 evidence、静默截断、摘要补写或依赖聊天记忆。

具体对象上限、authority 双重绑定和跨周期 PIT availability 规则以 `V3_2_SYSTEM_AND_EXPERIMENT_DESIGN_2026-08-07.md` 为规范：市场图视图、完整 Agent input、完整 Current Codex Presentation 和单次 UTF-8 output 各有硬上限；proposal/selection packet 不再拥有低于完整 input 的第二个 stage-specific 魔法门。Cycle 1 必须重放当前 availability registry，Cycle 2+ 还必须重放前一 registry。真实第六资格的 Agent view 为 `187,641` canonical bytes，保留 `414` 根 bars、全部 `55` 条可引用 evidence、UNKNOWN 与 OTHER；完整 proposal/input 为 `559,522/562,654` bytes，合法位于 `1 MiB` complete-input gate 内，故当前 pilot 应使用单个 INLINE `CANONICAL_PACKET`。旧 512 KiB proposal gate 和 768 KiB selection gate 只保留为历史实现事实，不再参与判定。当前 pilot 的生产策略是 `INLINE_ONLY`：checkpoint、request、claim、control 与唯一 packet 表示共同接受 `1 MiB` 精确总门；完整 INLINE input 或最终 Presentation 任一超限都直接 `CONTEXT_CAPACITY_UNRESOLVED`。第六现场的旧 `121` shards 合计约 `7.79 MB`，因此 `SHARDED` 只能作为未来未资格化机制，不能在当前 pilot 中靠抬高单片门、多次隐式调用或无逐段 ACK 的 package 绕过总门。普通 delta 轮只在构造路径传播变化；owning verification 仍对当前完整 closure 重建一次，并且只在同一 owner-bound call scope 内对相同 strict snapshot 复用。scope 退出后 Proposal/Selection/audit 只能复用已经封存的 digest-bound 材料，不能继续使用 verifier cache。旧 V3.1 Q0–Q8/74 路径的只读通过只证明旧冻结链未漂移，不能代替 V3.2 authority。

### 18.4 可逆传输压缩：容量不是删证据的许可证

完整 raw、public bundle、PIT registry、图、availability、Agent 输入输出和 acceptance 始终以 write-once 原件保存。压缩只能改变传输表示，不能改变证据、状态、冲突、反证或风险对象的语义全集。**当前 pilot 只允许最终仍能形成一个 `INLINE` packet 的确定性去重/typed 编码；下列 closure 分片与多段交付是未来 `SHARDED` 能力的规范草案，不是当前可用路径：**

```text
canonical 去重与字典化
→ 可逐值还原的 typed time-series / metadata 编码
→ 按已封存依赖身份生成或复用确定性 closure 分片
→ 按冻结强制根集合交付完整闭包
→ 对原件与交付视图双重重放
```

合法压缩必须满足：

- 每个变换均有固定 schema、算法版本和 round-trip receipt；解码后 canonical typed value 与压缩前逐值相等；
- 不可逆摘要、自然语言概括和 top-k 只能作为人类派生视图，不能作为 Agent 证据或 acceptance 的原件替代；
- `required_member_ids` 不能由 Agent、Presentation 或任意调用者挑选，必须由冻结的 `StageRequiredRootPolicy` 从正式对象角色机械生成；
- 强制根至少包含当前状态、全部合法动作、ACTIVE/WEAKENED/UNKNOWN 假说及其相反候选、OTHER、客观 UNKNOWN、冲突、反证、falsifier、hazard、continuity 和它们的完整传递依赖闭包；
- `CompactionManifest` 必须绑定每份原件、原件到 typed member 的完整投影、保留字段、全部成员与计数、closure、shard、实际交付顺序、canonical/UTF-8 bytes 和可逆性证明；
- 正式 acceptance 必须从完整原件重建成员全集，重算强制根与 closure；当前 pilot 核对 Agent 实际消费的唯一 INLINE packet，未来 SHARDED 资格才核对 exact shard set。仅验证“原件文件仍存在”不构成无损证明。

若单个不可分依赖闭包、完整强制根集合或最终 delivery 仍超过已资格化的物理上限，必须在 Agent 调用前写入 `CONTEXT_CAPACITY_UNRESOLVED` 和人工处理义务；不得删对象、缩短证据、改用聊天摘要或发起一个“先看部分、以后再补”的第二 Agent 尝试。

### 18.5 客观 UNKNOWN 与主观评估双轨

客观缺失以 `ObjectiveUnknown` 保存，始终满足：

```text
objective_status = UNKNOWN
objective_value = null
zero_imputed = false
agent_may_change_objective_status = false
```

Agent 可创建独立 `UnknownSubjectiveAssessment`，但不得把它写回 datum、来源角色、coverage 或 claim ceiling。每个非零或有方向的主观评估必须：

- 绑定能够在当前正式 PIT registry 或冻结 mechanism registry 中唯一解析的摘要；伪造格式正确但不存在的摘要不算依据；
- 满足引用 `available_at <= assessed_at` 且 `assessed_at >= objective_unknown.detected_at`，run/cycle/instrument 一致；
- 记录 rationale、typed 相反假说绑定、可观察 falsifier、dependency group、绝对 expiry 和 `subjective_plausibility_tier`；
- 明示其为未校准主观支持，不进入 source coverage、事实完整性、权限、最大损失、Brier/ECE、EV 或 Kelly；
- 仅有登记机制而无当前观测时可保留机制性主观候选，但必须标记 `MECHANISM_ONLY`，不得冒充当前 PIT 事实或解除硬风险门；无可解析依据时方向为 UNKNOWN、档位为 `EXTREME_UNCERTAINTY`。

主观评估可以影响已经合法的假说排序和条件规划，这保留理论的开放性；它不能制造客观观测或把不可定义损失变成可承担风险。

### 18.6 数据缺口与人工公开证据

每个未取得的正式字段必须生成 typed `DataGapEscalation`，至少记录请求、实际请求/失败时间、错误、影响、claim ceiling、允许的官方公开来源、人工截图/导出和 raw 保存步骤、时间核验、semantic/physical 双摘要及重新准入步骤。

人工取得的数据只能形成 `MANUAL_PUBLIC_EVIDENCE` 新 revision：

- 官方内容所述事件/生效时刻写入 `event_time/effective_at`；只有来源合同明确它是观测时钟时才可写入 `provider_observed_at/observed_at`。`available_at` 必须是系统实际收到并保存该人工证据的时间，禁止借发布日期倒填可得时间，也禁止用未来生效/日程时刻推进 PIT `as_of`；
- 只允许公开官方页面或官方公开导出，不允许账户页面、凭据、私有群、付费私有数据或无法保存原件的转述；
- 经来源、时间、raw 字节、提取映射和 dependency group 验证后，只能进入 `available_at` 之后的未来 cycle；
- 不得修改已 accepted cycle、已预留/已失败 outcome、旧 UNKNOWN 或旧 failure receipt，也不得伪装为自动采集；
- 自动与人工渠道若依赖同一官方事实，必须进入同一 dependency group，不能重复增加 coverage 或支持。

### 18.7 环境本地化不改变理论和评价

qualification 前冻结 `EnvironmentCapabilityProfile`：操作系统/架构、Python 可执行文件与版本、Codex delivery 方式和实测容量、UTC/单调时钟、文件系统原子写/CAS 能力、公开网络端点与 TLS/DNS/代理边界、automation、存储、可用工具和 adapter 版本。能力分为 `REQUIRED / OPTIONAL / UNKNOWN`：

- 缺少 REQUIRED 能力则资格失败，不能通过缩短 horizon、删候选、降低样本、放宽 freshness、改变 outcome、换非官方来源或扩权来适配；
- adapter 或 profile 变化必须形成新 runtime revision 并重新 qualification，不能在已封存 run 中热修；
- 时间语义始终使用 canonical UTC，时区只允许影响展示；
- V3.2 bundle、qualification probe 与 outcome 只能复用同一无凭据公开 HTTPS 路由政策：精确允许 OKX Global 官方推荐 REST 基址 `https://openapi.okx.com` 的冻结公开 GET 路径，禁止认证/账户/订单头，禁止重定向、fallback 和 retry；若本地环境要求系统 HTTPS proxy，只读取无 userinfo 的系统声明并在首次请求前冻结为单一路由，不保存代理地址，也不因运行时 `no_proxy` 漂移改走直连。旧 V31 的 `www.okx.com` 绑定继续冻结，只允许历史重放，不得被 V3.2 修改；
- 明文或百分号编码 userinfo、代理绕过、非法 host/path/header、路由配置异常都在网络前结构性失败关闭，不能降级为普通 coverage UNKNOWN；timeout/DNS/TLS/connection/provider 等真实物理失败则封存稳定枚举码，无自由异常文本、环境值或秘密；
- qualification 的每次物理失败先保存已有 response body（若有），再保存绑定 attempt/component/path/query/time、response/body presence、route policy、attempt=`1`、retry=`false` 的 write-once failure receipt，最后才推进 terminal checkpoint；outcome/probe 同样保留精确物理叶节点；
- 每个 qualification 使用 `.runtime/v32/qualifications/<qualification_run_id>` 独立命名空间。旧 `.runtime/v32/qualification` 失败根保持原字节，不能通过清理、迁移或复用来制造 successor；
- 瞬时网络失败属于 coverage/failure evidence，不应被环境说明洗成成功；一次系统公开 HTTPS 可达也不证明来源资格、持续网络可靠性、Codex/automation 可靠性或交易能力。

### 18.8 逐边界中文审计是 sealed-boundary 派生物

`CycleAuditNarrative` 由 sealed typed artifacts 确定性生成，记录 stage chronology、source coverage、客观 UNKNOWN、主观评估、hypothesis/zone/modifier 变化、所有合法动作、selected/runner-up、risk envelope、shadow arms、schedule、告警、恢复、摘要和限制。它不是 authority、事实、Agent 输入或 acceptance 的替代品。

为避免循环，每份 qualification、analysis、acceptance、outcome 或 recovery narrative 都必须晚于其对应 typed boundary 的封存；它不能参与或改变该边界。cycle acceptance 先只接受 typed 原件，随后生成分章节 narrative 和 index，再写 `AuditCompletionReceipt` 绑定 acceptance digest、生成政策和全部章节摘要。下一 analysis permit 可以要求前一 acceptance 已有合法 audit completion，但不能因审计渲染失败回写或改变已封存 acceptance。超限时按冻结章节分片，不得漏项或用模型自由摘要。

### 18.9 只读监督与同一 run 恢复白名单

独立监督 Agent 只能通过最小 `ReadOnlySupervisorProjection` 读取 durable checkpoint、permit、acceptance、audit index、failure 和“哪些 schedule 已到期”的状态。它没有市场 adapter、Strategy Agent、formal store、authority builder、订单或未到期 outcome 的 capability；`SupervisorAlert` 只能写到独立 append-only alert store，不能成为决策证据、正式状态或恢复授权。

同一 run 自动恢复只允许以下事前冻结、逐字节确定的尾部：

1. 已有 exact intent/bytes 的 write-once 或 CAS 尾提交；Agent mailbox 只承认 request、claim、delivery/receipt、consumption/receipt 四个已冻结转移的 exact tail，均复用首次不可变字节、首次时间和同一 predecessor，禁止换 payload、补第二次尝试或覆盖已有对象；
2. 已保存 raw 与 batch intent、且没有语义校验失败时，用同一冻结 parser 完成未写的 parse/write tail；
3. 完整 Agent delivery 和 consumption 已封存后，继续同一 compiler/commit tail，绝不二次调用 Agent；
4. accepted state 后从 sealed commit 补 exact outcome schedule；
5. child store 已成功提交后补 Supervisor completion/CAS；
6. 从唯一 predecessor/successor 历史重建 current pointer 或 index；
7. 对应 typed boundary 封存后用固定生成器重建缺失的 audit narrative/index；其中 acceptance narrative 只能在 acceptance 后重建；
8. Agent 调用前，依据已冻结 manifest/intention 重建摘要和字节完全相同的 compaction artifact。

网络重试、换源、人工补数、改变 parser/环境/压缩算法/强制根、第二次 Agent、改变理论/风险/评价/时钟、修补 accepted 语义或读取未到期 outcome 均不属于恢复；需要新 qualification 或 successor，语义失败保持 fail closed。

### 18.10 工作树与新增对象的授权归属

authority 只能在明确提交边界后生成。资格工作树必须绑定 branch、commit SHA、tree SHA、runtime closure、status、staged/unmerged/untracked 检查、敏感信息检查、允许保留但位于 closure 外的精确路径及 post-commit test receipts。禁止 `git add .`，禁止用 dirty working tree 的物理字节冒充 HEAD；优先在 exact commit 的 clean qualification worktree 中重放。

新增对象分为三类：

1. `ContextCompactionPolicy / UnknownSubjectivePolicy / DataGapManualEvidencePolicy / EnvironmentCapabilityProfile / ReadOnlySupervisorPolicy / AutoRecoveryWhitelist / WorkspaceFreezeReceipt / CycleAuditGenerationPolicy` 必须进入 experiment contract 与 authority/runtime manifest 的 support bindings；
2. proposal/selection compaction manifest、required-root plan、replay receipt，以及 ObjectiveUnknown/SubjectiveAssessment/DataGap/ManualAdmission registries、EnvironmentConformanceReceipt 与 RecoveryTraceRegistry 必须进入正式 cycle acceptance closure，零项也显式登记；当前 pilot 的 transport shard set 必须显式为空，未来 SHARDED 资格才允许非空；
3. `CycleAuditNarrative`、人工操作说明渲染、环境说明报告和 `SupervisorAlert` 只能是派生非授权视图。

截至当前工作树，这些对象已经进入本地 production composition、28 组件 acceptance、实验合同、authority builder/runtime closure 与 full loader；actual-capability 路径也已按 Domain 纯合同、Application Protocol、Infrastructure 固定实现完成分层，并在 `COMPLETE` 前物理重开 evidence binding。六份资格保持各自 durable `FAILED_CLOSED` 历史边界；第七份在提交 `66197c4` 的正式 post-commit receipts、完整 Phase-A、fresh-process 与唯一 PUBLIC_SOURCE 成功后，因逐对象外部唤醒在 claim 前耗尽 CURRENT_CODEX reservation 窗口而成为治理 `EXPIRED_TERMINAL`。其 runtime 原件仍是 controller `RUNNING/revision 3`、proposal `REQUESTED`、no claim，不得追写成失败。六个 failed pair 与一个 expired pair 共同形成七组 tombstone；没有 target authority、target run 或 outcome。当前未提交候选同时修复材料子阶段调度与 zero-eligible WAIT 的 owning-cause 边界：同一高层许可内最多推进 `64` 个 append-only 子阶段，并在 Agent、READY、no-progress、probe 高层边界、异常或上限停止；零方向候选只能来自 Domain 可重建硬门或 compiler 实际确认的 objective-input 缺失，Agent 软理由不得删除全部方向候选。reservation 起点、`660s` 上限和逐步 write-once/CAS 均不变。每个全量 suite 仍必须在新 qualification ID 下只允许一次预留与执行，绑定固定 Python/Git/环境/命令、exact commit/tree、时间、计数、有界完整输出及工作树前后状态，再由 aggregate→WorkspaceFreeze v1.1→manifest→qualification/target authority 物理绑定。资格期间每一次 public source、Agent、monitor 或 finalization 边界之前，都必须重放 approval、theory bytes、contract、manifest、Q0–Q8、support、runtime closure、fresh-process receipt/binding 与 post-commit 原件。当前候选尚须完整回归、独立复核、显式提交和第八 exact pair 的真实收据生成；不能用聊天记录、本轮手工 PASS 或第七资格的迟到交付启动 successor。

零候选不等于只有“全部被删”时才需要审查。每一个被标为 `BLOCKED` 的合法动作都必须有 owning cause：Domain 从当前状态重建的事实完整性/path invalidation/极端不确定/typed 非方向门；Domain 确定性算出的 residual-risk cap=`0`，并绑定候选假说的 exact source refs；全 instrument churn ledger 对 `OPEN_PROBE/REENTER/REVERSE` 给出的真实 `COOLDOWN/EXHAUSTED + exact failure refs`；或 compiler 从正式 packet 独立确认的 objective-input 缺失。未来真实执行 `MAX_LOSS` 不属于当前候选 owning cause。`AVAILABLE/RESET` 不得伪装冷却，`GEOMETRY`、自由 cost 文本、别名和引用扩大只能保留为诊断或 guard，不能单边删除候选。`RISK_BUDGET_BELOW_CLUSTER_QUANTUM` 仅属于新增风险动作，禁止封掉 `HOLD/REDUCE/CLOSE`。在未来有新的 typed owner 之前，非增险管理动作保持可比较，Selector 必须显式选择，而不能先删选项再解释。

### 18.11 Agent 前材料化失败必须是单尝试终态

PUBLIC_SOURCE 已完成且 CURRENT_CODEX reservation 已创建后，任何 authority/material replay、市场图视图、timeframe、proposal/input、mailbox 或编译材料边界的异常，都属于这一次 CURRENT_CODEX 资格尝试，不能掉出 controller 形成可再次进入的 `RUNNING/PENDING` 悬空状态。新版本必须在同一状态变更边界写入一次 `qualification-materialization-failure`：绑定 exact qualification/target identity、authority、CURRENT_CODEX reservation、controller predecessor、稳定 typed error chain、失败阶段、时间状态以及当时完整 material role 的语义与物理 binding；随后 controller 只能追加 `FAILED_CLOSED`。若进程在 receipt 与 checkpoint 之间中断，下一次 wake 只允许完成同一 receipt 的 terminal CAS；终态后只读重放 receipt、authority、reservation、material prefix 与 checkpoint，禁止再次 materialize、调用 Agent、建立 monitor 或创建 target。旧第五树没有该新 receipt，因此只能由 exact-ID tombstone 封禁，绝不能事后补写来伪造当时已经 failure-atomic。

异常后的物理现场重扫必须逐 prefix 标注认识边界。只有成功列举并物理重开全部对象时，prefix status 才能是 `VERIFIED_EXACT`，并绑定 exact inventory；若 material、mailbox 或 probe 的重扫本身失败，则对应 status 必须是 `UNKNOWN_REPLAY_FAILED`，记录稳定的 `*_PREFIX_REPLAY_FAILED` 代码，且不得用空清单冒充“现场为空”或“已完整核验”。这类 UNKNOWN receipt 仍绑定原始异常、authority、reservation 与 controller predecessor，并消费同一尝试进入永久 `FAILED_CLOSED`；它证明的是禁止重试和已知控制前驱，不证明故障时刻的物理 prefix 完整性。若连 failure receipt/terminal CAS 的存储都不可写，只能报告 storage failure，任何软件合同都不能伪称已耐久封存。

---

## 19. 当前不可执行实验中的组合与 reentry 边界

V3.2 将 portfolio/reentry 从“完全排除”改为“研究规划原生接线”：

```text
ConditionalActionPlan
ExposureIntent
RiskTranchePlan
HypothesisRiskAttributionMatrix
ReentryObligation
```

这些对象可以跨分析轮更新，但不得声称：

- 限价单已成交；
- stop/target 已真实存在；
- 账户拥有某仓位；
- 产生 PnL、保证金、funding 或资金变化；
- 可直接执行。

如果未来要评价实际持仓路径，必须另行冻结 `counterfactual fill model` 或 paper execution authority；否则只能评价计划的前瞻一致性、触发覆盖和事后价格路径，不能报告账户收益。

---

## 20. 动态运行时：分析时钟与 outcome 时钟分离

V3.1.1 的“上一 1H outcome 未完成就不能开始下一轮”会让 15 分钟系统天然失速。V3.2 改为双时钟：

```text
AnalysisClock
  每 15 分钟或事件触发一个新 PIT 分析轮

OutcomeClock
  对每个已封存 decision 独立安排 15m/1H/4H 等预注册 outcome
```

Supervisor 只允许使用 `available_at <= current decision_time` 的已成熟 outcome；未到期结果留在队列，不阻塞新的分析。每个 outcome 仍是 raw-first、单次尝试、write-once。

失败分类：

- optional 数据源发生冻结白名单内的 timeout/connect、HTTP `429` 或 `5xx` 且已有 raw/transport-failure receipt：该 datum/outcome=`UNKNOWN_COVERAGE_LOSS`，不自动杀死整条研究；required component 仍失败关闭。凡 HTTP response 已存在，每个组件的 `0..MAX` 字节 body、status、final URL、request/received/captured 三时刻、attempt=1/no-retry 与请求身份必须先组成固定可推导的 write-once capture bundle，完整回读后才解析或发下一请求；若 timeout/connect 发生在任何 response 前，optional component 也必须先封存并回读固定路径的逐组件无响应 receipt，明确 `response/body/status/final_url` 均不存在，再允许继续。aggregate UNKNOWN 必须绑定该 receipt，durable replay 必须从 owning store 精确重放；缺失、篡改、交换或 sink failure 均停止。HTTP `400/401/403/404`、redirect、HTTP 200 但 provider `code != 0`、零字节/无效 JSON/envelope 或必需字段缺失一律在封存后判为结构失败，不能伪装成“无响应”或 coverage UNKNOWN；
- schema、时钟、摘要、并发或状态完整性失败：对应 lane=`FAILED_CLOSED`，不得继续写同一 lane；
- 一个 horizon 失败不允许用另一个 horizon 或二次请求补造。

计划中的 `stop/limit/target touched` 只表示公开市场价格触及，不表示限价成交、止损成交或真实 PnL；执行延迟和 venue failure 作为独立 hazard outcome 保存。

这一区分既保持前瞻性，又不让一个公开接口缺失永久终止全部动态研究。

---

## 21. 评价体系

### 21.1 工程资格不等于市场能力

第一阶段只评价：

- 首轮全量与后续 delta 是否按时完成；
- 新假说、主观支持档位和相反假说是否可重放；
- probe/add/reduce/reentry/WAIT 候选是否完整；
- outcome queue、raw-first、no-retry 和 crash recovery 是否可靠。

### 21.2 市场增量

未来市场评价必须在同一 PIT 输入、同一成本、同一 outcome 和同一机会集合比较：

```text
V3.2_DYNAMIC_AGGRESSIVE
V3.1_CONSERVATIVE
WAIT_ONLY
BUY_AND_HOLD_OR_ALWAYS_EXPOSED_REFERENCE
SIMPLE_TREND
NO_RSI / RSI arms
```

本轮本地 shadow 合同固定六臂：`V32_SELECTED_PLAN / V31_CONSERVATIVE_WAIT_BIASED_REFERENCE / WAIT_ONLY / SIMPLE_15M_TREND / NO_RSI_REFERENCE / ALWAYS_LONG_PUBLIC_MARK_REFERENCE`。其中 WAIT、简单趋势和 always-long 可由同一 PIT 事实确定性生成；没有同 PIT、同规则的 V3.1 与 no-RSI 重放时必须保留 `UNKNOWN_NOT_COMPUTED`，不得由调用者编造标签。

指标分离：

- 当前 terminal-only shadow 只评价终点方向一致性和 coverage；
- MFE/MAE、区间路径、机会捕获、迟到成本和提前试探损失，只有未来事前冻结并耐久采集完整 horizon 内价格路径后才评价；
- turnover、fee/slippage/funding 敏感性；
- probe→add、reduce、runner、reentry 的条件结果；
- 最大连续损失、尾部和 regime 分解；
- 若未来有合法 fill model，才报告成本后 PnL。

用户给出的月度与年度收益区间继续为 `USER_INTUITION_UNVERIFIED`，不得作为验收阈值。

### 21.3 样本边界

少量周期只能证明流程。市场预测增量、序数档位稳定性、成本后收益和跨 regime 泛化仍需更大前向样本；在达到预注册样本前保持 `UNKNOWN_NOT_EVALUATED`。三档支持不声称可被 Brier/ECE 校准；只有未来另行建立真实频率概率模型时才评价概率校准。

---

## 22. 永久禁止的错误路径

1. UNKNOWN 不分类，统一导向 WAIT；
2. 只因信息不完备拒绝一切 probe；
3. 用主观支持档位冒充事件概率、EV，或将其插值成 0–100 魔法数字；
4. 同一证据写成多个故事后重复加仓；
5. 用名义百分比代替最大损失预算；
6. 把浮盈称为免费资金；
7. 亏损时以同一 thesis 摊平；
8. 固定止盈默认全平并终结 episode；
9. 退出后主 thesis 仍有效却既不生成有界观察义务、也不明确终结理由；
10. 固定 `3/8/15%` stop 跨市场硬编码；
11. RSI 超买直接做空、超卖直接做多；
12. 日线上涨绝不做空或下跌绝不做多；
13. 反复触碰必然强化阻力或必然消耗阻力；
14. 没有期权 gamma 证据就声称 Gamma Squeeze；
15. 限价单必然成交或必然更安全；
16. Agent 直接给出数量、费用、风险和账户真值；
17. 当前不可执行选择被写成真实订单或收益；
18. 未到期 outcome 阻塞所有 15 分钟分析；
19. outcome 缺失用第二次请求补造；
20. 以工程 PASS、八个周期或单一 regime 宣称盈利和泛化。
21. 唯一弱假说因相对归一分母变小取得全部风险预算；
22. 为防止休眠而强制最低仓位或伪造正风险方向；
23. 把 stop trigger、限价触及或保护请求当作保证成交；
24. 假说到期后只延长时间戳、没有新证据仍继续支持旧计划；
25. 用一个无依赖绑定的“庄家收割”修饰器广播到全部假说。
26. 把累计多兆字节图全文复制进每个 Agent 窗口，或在超限后任意截断、丢对象、改用聊天摘要补齐。
27. 原件虽然保存，却允许调用者任意决定哪些成员进入 compact view 或 required roots。
28. 只验证内部 closure/shard mechanics，不证明原件到 typed member 的完整投影和 Agent 实际 INLINE 交付覆盖；未来 SHARDED 亦不得只验单片。
29. 用格式正确但 registry 中不存在的摘要给客观 UNKNOWN 附加 HIGH 方向评估。
30. 用人工截图回填旧 cycle、旧 outcome，或把人工渠道伪装为自动采集。
31. 把 `CycleAuditNarrative` 当作 authority、事实原件或 acceptance 自身的一部分形成循环。
32. 让监督 Agent 访问市场、未到期 outcome、第二 Strategy Agent 或 formal store 写接口。
33. 把网络重试、换源、规则修改、人工补数或第二次 Agent 包装成 same-run recovery。
34. 为适配本地环境降低理论、数据时点、候选全集、评价终点、样本规模或权限边界。
35. 在未提交或含 runtime closure 内 dirty/untracked 字节的工作树上生成 qualification authority。
36. 把 0–100 主观分数、整数 delta 或主观 cluster 求和重新接回风险预算。
37. 在 `CHOPPY/VOLATILITY_WITHOUT_DIRECTION` 中为满足成对假说或避免 WAIT 而建立当前方向风险。
38. 把 `ReentryObligation` 解释为自动重开；绕过两次上限、累计风险、冷却或 regime reset 条件。
39. 在每个 runtime 子阶段重复全图闭包计算，或为了满足速度预算删除语义去重与全量可重放性。
40. 把 API 请求已发送、保护单已 ACK 或本地 fallback 已触发写成真实清仓；venue 不可用时隐瞒未解决暴露。

---

## 23. 理论依据与适用限度

- 技术形态的可算法化与条件信息：Lo, Mamaysky & Wang (2000), <https://doi.org/10.1111/0022-1082.00265>
- 关口附近订单聚集与突破加速：Osler (2003), <https://doi.org/10.1111/1540-6261.00588>
- 时间序列动量：Moskowitz, Ooi & Pedersen (2012), <https://doi.org/10.1016/j.jfineco.2011.11.003>
- 动量在恐慌/反弹中的崩溃风险：Daniel & Moskowitz (2016), <https://doi.org/10.1016/j.jfineco.2015.12.002>
- stop policy 的 regime 依赖：Kaminski & Lo (2014), <https://doi.org/10.1016/j.finmar.2013.07.001>
- 波动状态与动态风险：Moreira & Muir (2017), <https://doi.org/10.1111/jofi.12513>
- 媒体、注意力与投资者行为：Tetlock (2007), <https://doi.org/10.1111/j.1540-6261.2007.01232.x>；Barber & Odean (2008), <https://doi.org/10.1093/rfs/hhm079>；Da, Engelberg & Gao (2011), <https://doi.org/10.1111/j.1540-6261.2011.01679.x>
- 技术规则的数据窥探风险：Sullivan, Timmermann & White (1999), <https://doi.org/10.1111/0022-1082.00163>
- 反复试验与模型选择的数据窥探风险：White (2000), <https://doi.org/10.1111/1468-0262.00152>
- 非平稳时间序列的离散 regime 转换：Hamilton (1989), <https://doi.org/10.2307/1912559>
- 高频换手和成本边界：Barber & Odean (2000), <https://doi.org/10.1111/0022-1082.00226>
- 未来执行边界的官方语义：OKX API 文档明确区分请求被系统接受与最终订单状态，订单可为 `live/partially_filled/filled/canceled`，REST/WS 共享部分交易限频且 WebSocket 需心跳/重连；<https://www.okx.com/docs-v5/>

这些论文只支持“值得形成候选并严格验证”，不支持把任一规则直接移植为 BTC 15 分钟 alpha。

---

## 24. V3.2 冻结判据

V3.2 只有在以下全部完成后才能成为新实验 authority 的理论输入：

- 用户建议逐条裁决已记录；
- UNKNOWN 分类、三档序数主观支持、typed regime、dependency cluster 和四类假说有 typed contract；
- ReflexiveLiquidityZone 与 RSI 角色进入图和 Agent context；
- 完整动作域、probe/add/reduce/close/reentry/reverse/WAIT 有确定性合法候选；
- 风险按最坏损失分配，非校准支持档位不进入 EV；
- StrategicContext/TacticalDelta/TriggerFrame 有缓存、过期和恢复合同；
- AnalysisClock 与 OutcomeClock 分离，队列单次 raw-first monitor 通过故障注入；
- 离散支持上限与残差在 typed hard gate 后缩放总风险；coverage 仅诊断且 source-admission 缺失保持 UNKNOWN；单一 LOW、多个重复 HIGH 和 mixed-direction 反例通过；
- external path modifier 只能影响共享依赖对象；false-break 后的新 tranche 仍进入 instrument 全局 churn breaker，不能借 cluster/regime/ID/动作名绕过原 24h 窗口、累计风险和次数上限；
- hypothesis expiry/renewal 防时间戳洗白和 inactivity review 有确定性合同；
- stop-not-fill、API/venue unavailable 只作为压力分支且不冒充真实成交；未来 `EmergencyExecutionCapsule=NOT_IMPLEMENTED_NOT_QUALIFIED`，与当前不可执行 runtime 物理隔离，当前 recovery observer 也不是 execution risk supervisor；
- 当前 Codex 直接收到完整 V3.2 正文、有界 canonical packet、当前市场图视图和 exact support bindings；完整来源/图原件由接受链全量重放，不在窗口中重复复制；
- Agent 市场图视图保留全部可引用 evidence、availability、dependency groups、UNKNOWN/OTHER 与 exact closure proof index；完整 verifier-only closure lists 留在 write-once registry 并由 owning verifier 重建，真实 414-bar 资格形态在固定 view cap 内；
- 可逆 compaction 从正式原件确定性生成全部 typed members，强制 roots 与完整 closure 不可由调用者裁剪；当前 pilot 对原件、compact view、唯一 INLINE packet 和实际 Agent delivery 双重重放，未来 SHARDED 资格才增加 shard selection；
- ObjectiveUnknown 与 UnknownSubjectiveAssessment 双轨、引用解析、PIT chronology、相反假说、expiry 和零客观贡献通过对抗验证；
- DataGapEscalation 与 MANUAL_PUBLIC_EVIDENCE 只进入未来周期，旧 accepted/outcome/failure 不可回填；
- EnvironmentCapabilityProfile、EnvironmentConformanceReceipt、只读 Supervisor projection、独立 alert store 和精确 recovery whitelist 已进入合同与 full loader；
- bundle/probe/outcome 复用冻结的无凭据、无重定向、无 fallback/retry 公开 HTTPS 路由；物理失败 raw-first 封存稳定原因，旧失败资格保持不可变且 successor 使用独立 runtime root；
- CURRENT_CODEX reservation 后的任一材料化异常形成 write-once failure receipt 与 controller `FAILED_CLOSED`，重复 wake 零材料化、零 Agent、零 monitor；历史第五 exact identity 在所有公开入口访问 runtime 前永久拒绝；
- request、claim、delivery/receipt、consumption/receipt 四个 mailbox 转移均通过 exact-tail 故障注入；首次不可变对象与时间获胜，重放只完成原 CAS，冲突 payload 和第二次尝试均失败关闭；write-once 发布同时证明 file fsync 与 parent-directory fsync；
- qualification delivery receipt 绑定实际 `CurrentCodexPresentationEnvelope` digest，full replay 从 CLAIMED 状态重建并逐字核对；已 CLAIMED 的资格重放零写、零新时钟，最终 Agent-facing envelope 直接返回且 canonical bytes `<= 1 MiB`，当前 pilot 仅 `INLINE_ONLY`；
- fresh-process collector 在任一 Phase-A authority byte 前真实运行，typed receipt 的物理 SHA-256 进入 support、manifest、runtime closure 与 full loader；提交 `66197c4` 已完成该门，但第七资格因 Agent 窗口提前耗尽终止，successor 必须由新 exact commit 和第八资格重新关闭；
- CycleAuditNarrative 在各自对应 typed boundary 封存后确定性生成；acceptance narrative 与 AuditCompletionReceipt 均不形成 acceptance 自引用；
- exact commit/tree、clean qualification worktree、runtime closure、敏感信息检查与 post-commit test receipts 由 WorkspaceFreezeReceipt 绑定；
- 所有 V3.1.1 已知 P0 修复、全链回归和非破坏性清理完成；
- 新 qualification 和 target authority 在理论与 runtime 最终摘要之后冻结；
- 旧失败 run、旧 74 路径和历史记录保持不可变；
- 冻结环境的全周期计时证明满足 15 分钟边界并保留 outcome 宽限；缓存失效与物理篡改反例通过；
- paper/live、账户、订单、凭据和资金权限继续为零。

在上述条件满足前，任何新的 successor qualification、target cycle 或 outcome 都不得启动；历史七组资格只允许只读重放。

---

## 25. 本轮最终冻结补充：模糊正确、热路径最小化与物理边界

本轮对“主观魔法数字、过度工程、混沌遗漏、reentry 磨损和物理逃生”五项质疑的最终裁决不再保留两套解释：

- Agent 只能给出 `EXTREME_UNCERTAINTY / LOW / HIGH`，对应 `off / probe / normal` 三档固定策略；不得提交连续主观分数、概率百分比或任意仓位系数。action-evaluation 中连续 `risk_reference_units` 仅是 sealed plan 的 exact 派生回传，任何漂移都会被 compiler 拒绝；内部离散编码只是 policy 常量，不是可调主观权重；
- `NEUTRAL / CHOPPY / VOLATILITY_WITHOUT_DIRECTION / TRANSITION / OTHER / UNKNOWN` 是一等市场状态，当前方向新增风险严格为零。风险候选只能是绑定 typed `BREAKOUT_BOUNDARY` 的 `CONDITIONAL/BLOCKED` 未触发计划，不生成 tranche 或订单；Domain 自动派生一个上下 research trigger pair，固定 15m confirmed close、严格 `GT upper / LT lower`、最早 expiry 和 first-match retirement。命中只触发 fresh reanalysis，连续 monitor、订单与 OCO 均未实现；
- 普通周期使用 pilot 有界 working set 和 delta 增量构造。完整 dependency identity 继续保留以防同源故事重复放大，但一个 bounded qualification wake 或 owner-bound acceptance/public-evidence scope 对相同 strict snapshot 只完整重建一次 closure；append 改变 snapshot key 后重建，失败、custom Mapping、scope 退出或跨 wake/thread/task/process 均不复用。Proposal/Selection/audit 复用封存材料而不是跨阶段 verifier cache；不存在“已实现固定 24h 同类证据归并”的能力，本文 `24h` 仅指 reentry churn ledger；
- `ReentryObligation` 只是观察资格。每 instrument、全方向共享一个耐久 24h ledger；首次 probe 免费但单次锁，随后 OPEN/REVERSE 可计数纠偏而不能免费；每次 reference risk 不超过 `1`、最多两次、连续失败最多两次，因此累计上限精确为 `2`，方向、动作名、cluster、regime、hypothesis ID 和日历切换均不能重置；
- 风险候选只能携带其同方向 actionable cluster 的精确假说闭包。sole research parent 绑定 ID、方向、entry、stop、support、zones 与 `valid_until=min(plan expiry,candidate horizon,time stop)`；到期先退休，ADD/REVERSE 必须生成不同 ID。该单槽位不等于完整多 tranche portfolio/pyramid ledger；
- 当前 pilot 没有账户、持仓或订单，不能伪造“异常时必然市价清仓”。未来 `EmergencyExecutionCapsule` 当前状态为 `NOT_IMPLEMENTED_NOT_QUALIFIED`，必须另行授权并以 venue 原子保护、reduce-only reconciliation、真实 fill/latency 资格和 unresolved exposure 告警为前提；当前 read-only recovery observer 明确不拥有执行风险监督职责，交易所完全不可用时不得承诺成交或零损失。

工程层进一步把上述理论约束落到可恢复边界：Phase-A fresh trace 先于时钟和 authority byte，意图与整套 runtime 原子发布；目录激活使用真正 no-replace 的 anchored 原语，不能用普通 rename 覆盖并发 final；public source 的崩溃前缀只允许封存一次失败、禁止外部重试；mailbox 四个 partial tail、dynamic present-unbound artifact 和 atomic audit bundle 均只附着已验证原字节，不重新调用网络、Agent 或时钟。

提交 `66197c4` 前从零回归达到 V3.2 `738/738 PASS / 1705.807s`（real `1706.23s`）和全 Theory Paper `1505/1505 PASS / 2018.226s`（real `2018.83s`）；其 post-commit 固定 runner 亦通过。第七资格已实际关闭 fresh-process 与 fresh PUBLIC_SOURCE 子门，但没有关闭当前 Codex 耐久交付、固定 outcome monitor 或 15 分钟实际周期时延；完整 successor 链必须由当前候选的新提交和第八资格重新验证。市场预测增量、概率校准、成本后收益和跨 regime 泛化继续为 `UNKNOWN_NOT_EVALUATED`。

提交后的第七资格进一步证明，“单对象 append-only”如果被错误提升为一次外部唤醒，就会把 `660s` 分析预算消耗在重复进程启动和 authority replay 上。正确边界不是后移 reservation、延长时钟或删除验证，而是在同一高层许可内按已冻结上限连续推进最多 `64` 个内部子阶段：每个子阶段仍独立 write-once/CAS 并重新核对当前时刻；遇 Agent、READY、no-progress、probe 高层边界、异常或上限立即停止。第七资格保持 `RUNNING/revision 3 + proposal REQUESTED + no claim` 原件，并以治理 `EXPIRED_TERMINAL` 永久 tombstone；不得追写成伪造的 `FAILED_CLOSED`。该修复必须由第八资格证明，而不是用第七资格迟到交付自证。

混沌/无方向状态还必须能在**没有任何 eligible risk candidate** 时完成最终 Selection。此时不得虚构多空比较，也不得因为 `WAIT` 行没有自身证据引用而让流程死锁；唯一合法理由为 `WAIT_NO_ELIGIBLE_RISK_BY_SEALED_EVALUATION`，其引用由已封存的 blocked-risk evidence、plan blocking evidence 与 regime evidence 确定性合并。若存在 eligible risk candidate，则继续使用原有的 sealed-variant dominance 论证，不能借新路径绕开动作比较。这样，“不下注方向”成为可完整封存、可重放、可被篡改测试拒绝的积极判断，而不是默认空值。

第八资格只能验证上述语义能被当前 Codex 在固定窗口内耐久交付；它不等同于正式 target 的 PIT 数据准入、图依赖闭包、跨周期连续性、outcome monitor 或任何收益证据。市场预测增量、概率校准、成本后收益和跨 regime 泛化仍为 `UNKNOWN_NOT_EVALUATED`。

---

## 26. 第八资格事故补充：资格运行必须只有一个组合写入者

提交 `cd011ad1aee9c0e3ea995746ce2eec51ddbef3ca` 已把第 25 节的五项修复落到 committed bytes；其固定 post-commit runner 得到 V3.2 `779/779`、全 Theory Paper `1546/1546` 两份 write-once PASS 收据且网络调用为零。第八资格 `v32-qualification-btcusdt-20260810t063618z` 随后完成 Phase-A、唯一 PUBLIC_SOURCE attempt 与 CURRENT_CODEX reservation，但暴露了一个独立的 P0：一个仍在运行的长 materialization 调用因外部工具提前 yield 而未被调用端继续轮询，随后第二进程又调用同一 `advance`。material、mailbox 与 controller 各自的 CAS 锁只能保护本 store，不能阻止两个 composition 跨 store 交错；最终一边封存失败，另一边又发布 proposal request，形成不可自洽的历史前缀。

因此 V3.2 新增以下不可降级不变量：

- 同一 qualification identity 在 Phase-A 后只能有一个 run-scoped composition owner；`advance / Agent claim / Agent submit / finalize` 必须共享同一个线程内和跨进程排他锁，不得各自只依赖子 store 锁；
- 锁必须位于 exact qualification evidence tree 之外的 qualifications sibling lock namespace，由已经语法验证且已存在的 exact qualification root 派生。等待前只核对 lexical root components，不扫描正在变化的子树；取得锁后才完整重放 namespace、authority、Q0–Q8、support 与当前 durable successor；
- 首调用完成前，后续调用只能等待。取得锁后必须从首调用已经完整发布的 successor 重新开始，不得沿用等待前的 checkpoint、material inventory、mailbox view 或时钟；
- 外部工具返回 running session/yield 只表示调用仍在执行，不是无结果完成。调用端必须持续轮询原 session；不得用第二次 `advance` 作为超时、解卡或恢复手段；
- body 的业务失败必须保留原错误身份；锁取得或正常释放失败才可归一化为 composition-guard failure。primary body failure 与 release failure 同时出现时保留 primary，并附加 release 诊断；
- 该锁只负责 Phase-A 后的 live mutation 串行化，不把 prepare/post-commit regression 变成可重试步骤，也不改变每项 external attempt=`1/retry=false`、Agent 单次尝试或失败关闭规则。

第八 qualification/target exact pair 现为第七个 durable failure pair，并与一组 `EXPIRED_TERMINAL` 共同形成八组永久 tombstone。其原 Q0–Q8 subject 可按固定 digest 逐项只读验证，但完整 runtime replay 必须继续以 `V32_ACTUAL_MATERIAL_FAILURE_PREDECESSORS_INVALID` 拒绝这棵不自洽历史；不得重试、推进、修补、删除、重签或用于 target。事故前后均未发生 Agent claim/delivery、monitor、target authority/genesis/cycle/outcome，故当前 Codex 耐久交付、固定 outcome monitor 与真实 15 分钟端到端仍为 `UNKNOWN_NOT_QUALIFIED`。只有新提交、全量回归与全新第九 pair 才能继续资格实验。
