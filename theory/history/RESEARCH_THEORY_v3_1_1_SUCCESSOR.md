# 动态开放市场研究理论 v3.1.1：信息—数据—图—假说—路径—行为—结果

> 状态：`SUPERSEDED_AS_FINAL_CANDIDATE_BY_V3_2_RETAINED_AS_RELIABILITY_BASE`
>
> 前身理论：`CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md`
>
> 前身 SHA-256：`ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553`
>
> 适用范围：公开 OKX `BTC-USDT-SWAP`、本地研究、不可执行
>
> 明确排除：paper/live、账户、订单、凭据、资金、组合写回、真实仓位与再入场
>
> 日期：2026-08-07

> 2026-08-07 变更：用户在 qualification 与 target 均未启动前要求将过度保守的行为政策改为早期试探、主观支持权重、动态加减仓、历史磁区、15 分钟 delta、RSI 和 reentry。该变更已形成 `CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md`。本文继续作为 raw-first、Supervisor、十二轴、关联预注册和 two-run 资格的可靠性底座，但不得再单独冻结为目标实验理论 authority。

本文件不重写 V3.1，而是在其理论方向上纠正已经由前瞻实验暴露的 P0 运行时缺陷，并冻结十二轴原生来源、动态图投影、关联候选全集、评价边界和后继实验的合法运行路线。V3.1 与本文冲突时，仅在本文明确列出的修正范围内以本文为准；没有明确修改的认识论、信息层、数据层、开放假说、概率云、严格路径和 Agent 职责继续继承 V3.1。

本文中的“完成实现”只表示合同与本地运行时可机械重放，不表示预测有效、概率校准、成本后收益、盈利、跨市场或跨 regime 泛化已经成立。市场证据不足时必须保留 `UNKNOWN_NOT_EVALUATED`。

---

## 1. 不变目标与新增公理

系统的唯一研究目标仍然是：在每个决策时点，只使用当时可得且有谱系的证据，形成可反驳的市场状态、竞争假说、条件路径与合法行为比较，并在未来结果到期后更新，而不是用若干指标直接预测涨跌。

完整链条冻结为：

```text
公开信息与市场事实
→ 点时采集与原始字节
→ 信息/数据分类与质量
→ 十二轴证据投影与动态图
→ 开放发现、有限工作集假说竞争
→ 非校准概率云与严格 if–then 路径
→ 完整合法行为比较
→ accepted state
→ 独立到期结果
→ 误差、覆盖和理论更新
```

V3.1.1 新增七条运行公理：

1. **原始响应先于解析。** 任何已有 HTTP response 的 outcome 都必须先保存 raw bytes 与 transport capture，再进行 JSON、schema、数值或时间判断。
2. **本地评价时钟与供应商时钟分离。** `available_at` 和 `evaluation_as_of` 取本地完整接收时点；供应商时间原样保存，只参与事前冻结的质量门。
3. **accepted 与 outcome 是一条统一运行状态。** 上一周期没有合法 outcome receipt，下一周期没有进入权。
4. **一次外部尝试只有一个事实结果。** 已封存 attempt 不允许二次 GET；恢复只能消费同一份本地原始证据。
5. **资格运行与目标运行不得互相冒充。** 资格样本不进入正式 `8/8` 分母。
6. **来源轴是证据分类，不是方向结论。** 有来源不等于有轴方向；单一代理不得越级成为心理、清算或韧性事实。
7. **关联搜索空间必须先有限冻结。** 看到结果后不得删除候选、换窗口、换滞后或换校正方法。

---

## 2. P0 故障的理论纠正

### 2.1 旧失败事实

旧前瞻 run `v31-prospective-btcusdt-20260806t183742z` 在 Cycle 1 accepted 后，唯一 outcome attempt 发生 `V31_OUTCOME_PUBLIC_VALUE_INVALID`，形成 `attempt=1 / outcome=0 / resume_allowed=false`。没有 raw capture，因此精确的外部响应内容与根因保持 `UNKNOWN`。研究 checkpoint 的 `READY_FOR_CYCLE` 不得覆盖 monitor 的永久 `FAILED_CLOSED`。

该 run 及其失败证据永久只读；禁止重取、修补、改写或把其 `1/8` 计入后继实验。

### 2.2 原始证据事务

对一次到期请求，状态必须按以下偏序推进：

```text
PLAN
≺ ATTEMPT_RESERVED
≺ CAPTURE_COMMITTED | TRANSPORT_FAILURE_COMMITTED
≺ PARSE_RECEIPT
≺ OUTCOME_RECEIPT | FAILURE_RECEIPT
```

记计划、尝试、capture、parse、outcome 数量为 `P,A,C,R,O`，任何时点必须满足：

\[
0 \le O \le R \le C \le A \le P \le 8,
\]

相邻未完成 gap 至多为 1。以下规则不可放宽：

- response 已返回：raw/capture 原子提交并读回后，parser 才可运行；
- 无 response：保存 typed transport-failure receipt，禁止伪造 raw；
- `A=C+1`：表示 attempt-only 中断，禁止二次网络请求并永久失败关闭；
- `C=R+1`：只允许对同一 raw、同一 parser、同一 clock policy 做本地恢复；
- `FAILED_CLOSED` 后不得追加 parse、capture 或 outcome；
- HTTP 4xx/5xx 若有完整有界 body，仍属于 response capture，不能因异常类型丢失 body。

### 2.3 时钟合同

定义：

- `T_n`：绝对 outcome not-before；
- `T_x`：绝对 expires-at；
- `T_r`：本地请求时点；
- `T_c`：响应 body 完整接收时点；
- `T_p`：OKX payload timestamp；
- `L=2000ms`：供应商最大允许领先；
- `A=5000ms`：供应商最大允许数据年龄。

本地窗口是硬条件：

\[
T_n \le T_r \le T_c \le T_x.
\]

供应商时间可接受区间为：

\[
T_c-A \le T_p \le T_c+L.
\]

- `-A <= T_p-T_c <= 0`：`OBSERVED/HIGH`；
- `0 < T_p-T_c <= L`：`OBSERVED/MEDIUM`，记录 `PROVIDER_LEAD_WITHIN_BOUND`；
- 语法有效但超界：`UNKNOWN/UNRESOLVED`，计 coverage loss；
- timestamp 非法、溢出或结构损坏：`REJECTED`，失败关闭。

禁止静默夹取 `T_p`，禁止用供应商时间替代本地 `available_at`，禁止根据 outcome 方向事后改变 `L/A`。

### 2.4 统一 Supervisor

Cycle `n` 的 permit 当且仅当：

\[
R.completed=M.plans=M.attempts=M.outcomes=n-1,
\]

且：

- research=`READY_FOR_CYCLE`，`next=n`；
- monitor=`ACTIVE`；
- 两者 `resume_allowed=true`，无 failure；
- `n>1` 时，上一 outcome、accepted state、plan 和 receipt predecessor 全部物理与语义重放通过；
- Supervisor 没有 live commit、stale digest 或失败状态。

合法 `UNKNOWN` outcome 必须同时满足：`path=UNRESOLVED`、`coverage_loss=true`、`unknown_counted_as_coverage_loss=true`。它是如实完成的观察，不是正确预测，也不是零。

### 2.5 accepted/monitor 跨 store 提交

研究 checkpoint 与 monitor checkpoint 分属两个 owner，不能假装存在单文件原子事务。每轮在任一 owner 前进前，必须先冻结完整 `commit material`：

```text
cycle permit
+ terminal Agent transport
+ durable assembly bundle
+ six semantic object digests
+ exact absolute monitor plan
+ research/monitor expected checkpoint digests
+ clock/axis/association/evaluation/qualification bindings
```

Supervisor 进入 `COMMIT_RESERVED` 后：

- 可以从同一 commit material 补完中断的本地写入；
- 不得再调用 Agent；
- 不得改变 action、阈值或支持证据；
- 不得读取 outcome；
- research 已写而 monitor 未写时，恢复 monitor；
- monitor 已写时只接受相同摘要的幂等读回。

Cycle 8 accepted 只是 `AWAITING_FINAL_OUTCOME`；只有 research=`8/8` 且 monitor=`8/8`，Supervisor 才能进入 `TERMINAL_COMPLETE`。

---

## 3. 信息层：主体、范围、行为与受众

信息事件 `I_e` 的最小结构为：

\[
I_e=(source, actor, role_t, content, action, scope, audience,
published, available, quality, lineage, alternatives).
\]

其中 `role_t` 是时变角色分配，不是人格真值。角色分类至少包括：

1. **制度与规格制定者**：央行、监管者、交易所规则制定者；分析系统安全、流动性条件、风险约束和全局/个体传导。
2. **流动性与资产负债表提供者**：做市商、投行、机构、ETF/基金；分析库存、融资、basis、报价与风险预算，不从聚合流量恢复真实身份。
3. **标的治理者**：公司管理层、协议开发者、基金会、验证者；分析现金流、供给、升级与治理承诺。
4. **政治与公共议程塑造者**：政府、候选人和高影响发声者；区分政策权限、竞选激励、口头立场与可执行行动。
5. **注意力与流量分配者**：媒体、KOL、社区、鲸鱼公开言论；分析受众分层、传播速度和行为猜想，不把热度等同买卖压力。
6. **市场参与群体**：套保者、套利者、方向交易者、被动清算者、零售群体；只从可观察行为建立竞争解释。

任何“暗藏行为”都只能作为带反例的 `IntentInference`：必须列出观察事实、推断链、替代解释、不可观察部分和失效条件。心理学直觉可以提出猜想和序数可能性，但不得伪装成统计概率或结构因果。

---

## 4. 数据层：点时本体与质量向量

每个 datum `D_i` 必须包含：

\[
D_i=(value,type,unit,instrument,timeframe,window,as\_of,
observed\_at,available\_at,vintage,source,raw,inputs,quality,missingness).
\]

硬条件：

\[
available\_at(D_i) \le decision\_at.
\]

派生 datum 必须绑定公式版本与全部 input digests；历史修订用新 vintage/新 revision 表达，禁止原地改写。质量不是单一 coverage，而是向量：

```text
source_reliability
completeness
timeliness
semantic_fidelity
measurement_error
revision_risk
cross_source_consistency
lineage_integrity
dependency_independence
regime_applicability
```

`missingness` 至少区分 `OBSERVED / NOT_PUBLISHED / SOURCE_UNAVAILABLE / OUT_OF_SCOPE / NOT_IDENTIFIABLE / INVALID`。任何缺失都不等于 0。

---

## 5. 十二轴原生来源与证据等级

十二轴只表达市场研究维度，不压缩为一个总情绪分。每条轴证据只能是 `DIRECT / PROXY / DERIVED / UNKNOWN`，并必须保存 source、raw/PIT digest、observed-at、available-at、quality、coverage、dependency group 和 limitations。

| 轴 | 可接受直接来源 | 有限代理/派生 | 必须保持 UNKNOWN 的典型情形 |
|---|---|---|---|
| 价格方向压力 | mark/index、闭合 K 线 | aggressor sample、单帧 book | 无有效价格或时钟失败 |
| 结构持续性 | 多个闭合窗口的结构事实 | 闭合 return 序列 | 仅当前 tick |
| 参与与主动流 | 成交量、aggressor trades | volume/median | 无成交或身份推断 |
| 拥挤方向 | funding、公开 position ratio | OI、basis | 仅价格上涨/下跌 |
| 杠杆变化 | 精确跨 capture OI change | funding/basis | 无上一 accepted OI binding |
| 强制去杠杆压力 | 官方 liquidation event/history | OI+price+active volume 的联合代理 | 仅价格或缺失清算流；缺失不等于零 |
| 流动性韧性 | 多时点冲击后深度/恢复 | 受控连续 book/trade 流 | 单帧 REST 盘口 |
| 波动与尾部压力 | 闭合 range/realized vol、期权 IV | return magnitude | 单点方向值 |
| 事件与叙事反应 | 有正文、时点、主体与市场反应的事件 | 经限定的事件代理 | 仅标题、无正文或冻结后补录 |
| 注意力与受众响应 | 搜索/传播/社交量及受众样本 | 有谱系流量代理 | 价格或成交量替代注意力 |
| 跨市场风险偏好/regime | 事前指定的跨资产公开数据 | 冻结 regime classifier | 单一 BTC 市场 |
| 多周期一致性 | 精确闭合 15m/1h/4h/1d 集合 | 基于该集合的派生材料 | 任一周期缺失或未闭合 |

来源可用只允许生成 evidence observation，不自动生成轴的 `-2..+2` 方向。轴状态需要另一个已绑定的规则或 Agent 推断，并保留 `UNKNOWN`。

当前单市场公开 run 对强制去杠杆、严格韧性、事件、注意力和跨市场轴允许长期 UNKNOWN；这是真实能力边界，不是实现失败。

---

## 6. 动态图与投影

时点 `t` 的图为：

\[
G_t=(V_t,E_t,\tau_V,\tau_E,L_t,Q_t),
\]

节点类型至少包括：

```text
InformationEvent, ActorRole, AudienceResponse,
RawCapture, PITDatum, AxisEvidence, AxisState,
AssociationReceipt, HypothesisRevision, ExpectationRevision,
ScenarioPath, ActionCandidate, AcceptedState, OutcomeReceipt
```

边类型至少包括：

```text
OBSERVED_AS, AVAILABLE_AS, DERIVED_FROM, PROJECTS_TO,
SHARES_DEPENDENCY_WITH, SUPPORTS, OPPOSES, FALSIFIES,
EXPECTS, CONDITIONS, IMPLIES, SELECTED_AS, EVALUATED_BY
```

图变化只通过 append-only delta：

\[
G_t=Apply(G_{t-1},\Delta G_t).
\]

一条信息或 datum 投影到多轴时只保留一个源节点，并以多条 `PROJECTS_TO` 边共享依赖组；不得复制成多个独立证据。支持、反对和不确定贡献都必须沿 lineage 去重。

图中的边表示“已记录关系类型”，不自动表示统计显著、因果或稳定机制。时间变化相关应建模为状态和不确定性，而不是把某次窗口相关写成永久边权。

---

## 7. 关联候选全集与多重检验

### 7.1 事前冻结全集

本 successor 的描述性关联全集为：

\[
2\ families \times 12\ axes \times 2\ lags \times 2\ windows=96.
\]

两个 family：

1. 轴序数值 → future signed log return；
2. 轴绝对序数值 → future absolute log return。

固定 lag：`1H, 4H`。固定 closed-pair window：`168, 720`。最小 observed sample：`135, 576`，最大 missing fraction=`0.20`。估计量为 Kendall tau-b；区间候选为保留序列依赖的 moving-block bootstrap 95%。这些最小样本只是一道不充分门，未来仍需事前 power/precision 分析。

当前正式目标最多 8 个 outcome，因此全部 96 项均为 `UNKNOWN_NOT_EVALUATED`，不得计算后宣称发现。

### 7.2 任意依赖下的默认控制

金融轴、窗口和滞后高度相关，因此普通 Benjamini–Hochberg 不得无条件使用。每个 family 默认使用 Benjamini–Yekutieli：

\[
c(m)=\sum_{j=1}^{m}\frac1j,
\qquad
k=\max\left\{i:p_{(i)}\le\frac{i q}{m c(m)}\right\},
\quad q=0.05.
\]

并同时报告 Holm confirmatory FWER：按升序 `p_(i)`，逐步检验

\[
p_{(i)}\le\frac{\alpha}{m-i+1},\quad \alpha=0.05.
\]

普通 BH 只有在新版本、观察 outcome 前提供 independence/PRDS 证明时才能启用。任一预注册候选缺失或 UNKNOWN 时，不缩小 family 分母，不把 UNKNOWN 填成 `p=1`；整个 family 不作发现声明。

### 7.3 使用边界

关联结果只可：

- 描述关系；
- 提出或排序待验证机制假说；
- 标注关系随窗口、lag 和 regime 的变化。

它不可直接：

- 充当结构因果；
- 转成 forecast probability；
- 进入 EV；
- 自动触发 action；
- 用样本内最优结果替换预注册 family。

---

## 8. 开放假说与概率云

开放性指候选发现入口开放，不指当轮无限展开。三个集合必须分离：

```text
discovery_pool      可新增方向与机制
approved_library    通过类型和来源审查的机制模板
active_working_set  当轮有限竞争集合 + OTHER/UNKNOWN
```

Agent 可从以下残差提出新假说：

- 信息事件无法被现有角色/传导解释；
- 数据层出现稳定但未解释的关系变化；
- 图中支持/反对结构改变；
- 既有路径连续出现 `OTHER`；
- 到期结果与所有工作假说冲突。

每个假说必须有：来源子图、机制、支持与反对证据、替代解释、hard falsifier、期限、下一观察、适用 regime、修订父节点和当前序数 plausibility。

当前概率云是非互斥、非校准的序数可能性集合：

```text
lead / runner-up / OTHER / UNKNOWN
```

禁止和为 100、禁止未经校准的 `probability_pct`、margin、entropy、Brier/ECE 和 EV。证据更新只允许产生带来源的 `strengthen / weaken / repartition / retain UNKNOWN` 收据。

---

## 9. 严格 if–then 路径语言

路径必须可机器验证：

```text
IF all(trigger_i are TRUE)
AND all(guard_j are TRUE)
UNLESS any(invalidator_k is TRUE)
THEN transition(from_state -> to_state)
EXPECT observation sequence by absolute horizon
FALSIFY IF any hard_falsifier is TRUE
ELSE preserve OTHER/UNKNOWN
REVIEW AT absolute timestamp
```

每个 predicate 必须绑定 `fact_ref, operator, expected, timing, available_at, minimum_quality, minimum_coverage, conflict policy`。`UNKNOWN` 不能当 FALSE，未到期不能当未实现，future predicate 不能进入当前 decision truth。

未来趋势不是单一方向标签，而是：

\[
Trend_t=(regime,structure,momentum,participation,liquidity,
leverage,event,coherence,alternatives,falsifiers).
\]

路径可生成多个互斥或部分重叠场景，但当前未校准模式不输出数值概率。

---

## 10. 行为规划、portfolio 与 reentry 边界

理论动作域继续保留：

```text
HOLD, OPEN, ADD, REDUCE, PARTIAL_EXIT, EXIT, REENTER, WAIT
```

但本 successor 正式 run 没有账户、持仓、订单或资金真值，因此：

- portfolio=`EXCLUDED_NO_CLAIM`；
- reentry=`EXCLUDED_NO_CLAIM`；
- portfolio mutation=`false`；
- 仅允许 `STATIC_COUNTERFACTUAL_FLAT_SHADOW`，用于证明无持仓上下文下动作不可执行；
- Agent 选择是研究标签，不是交易指令。

WAIT 必须记录原因、机会成本、待观察事实和绝对复核时点。未来要评价持仓管理或再入场，必须使用不同实验合同、新权限、点时成本账本和真实 episode state，不能暗接到当前 run。

---

## 11. Agent 最大化与确定性边界

当前 Codex Strategy Agent 负责：

- 从完整 canonical packet 解释信息、数据、轴证据和图变化；
- 提出、修订、否证或新增方向假说；
- 保留竞争解释与 OTHER/UNKNOWN；
- 构造严格路径、未来预期、falsifier 和复核计划；
- 在完整合法候选中进行一次 proposal 和后置 selection；
- 解释 WAIT 的机会成本。

确定性系统负责：

- 权限、时点、schema、digest、raw、PIT 与谱系验证；
- semantic compile、候选全集和完整动作比较；
- Supervisor gate、一次尝试、commit、monitor 与 outcome；
- 禁止未校准概率、EV 和执行能力。

Agent 每阶段单次尝试，完整 canonical packet 必须直接进入当前 Codex；聊天摘要不能补齐 packet，子 Agent/fixture 不能替代当前 Codex 资格，Agent 也不能修改已封存数据、规则和 outcome。

---

## 12. 两阶段资格与唯一目标实验

同一 run 不能用自身已接受结果证明自己在启动前已合格。因此冻结两阶段：

### 12.1 Qualification run

先由标准、范围受限的 qualification authority 授权一个独立 run，只用于形成：

1. authority-postdating 的 12 请求公开 OKX source qualification；
2. 当前 root Codex 的 proposal → compile → post-seal selection → accepted 耐久交付；
3. raw-first monitor、clock、no-retry、并发与 Supervisor failure probes。

资格 run 的 accepted cycle 永不计入目标 `8/8`。完成资格后必须以不可恢复的 retirement receipt 封存，不连接 automation。

### 12.2 Target run

最终 target authority 同时绑定：

- 旧 v2 active chain 的 Q0–Q8 与 74 个冻结路径重放；
- 旧失败 run 的 monitor failure lineage；
- qualification authority/run/retirement 与三份资格；
- V3.1.1 文档；
- clock policy、Supervisor、完整 runtime closure；
- 十二轴 registry/projection；
- 96 候选预注册与评价合同。

必须满足：

```text
target_run_id != qualification_run_id != predecessor_run_id
```

Application 只能接收 full loader 完成后投影出的 target 五份语义授权文档；这既避免 Q7 typed AST 同名字段误报，也不绕过完整 loader。

目标 run 的完成标准固定为同一 run `8/8 accepted + 8/8 legal outcome`。任何新 P0 内部缺陷导致失败，只能保留证据并重新版本化；不得改变分母或把资格/旧 run 样本拼接进来。

---

## 13. 评价合同

当前 8 周期只评价运行忠实性和前瞻证据链，不足以回答市场有效性。

| 问题 | 当前状态 | 将来最小设计门（非充分条件） |
|---|---|---|
| 市场预测增量 | `UNKNOWN_NOT_EVALUATED` | ≥240 同样本前瞻 outcome、冻结 ablation/baseline、序列依赖区间 |
| 概率校准 | `NOT_APPLICABLE_ORDINAL_ONLY` | 新概率版本、互斥完备事件、≥500 预测、proper score/校准区间 |
| 成本后收益 | `UNKNOWN_NOT_EVALUATED` | 新 authority、≥100 completed episode、费率/funding/slippage/终止规则 |
| 跨 regime 泛化 | `UNKNOWN_NOT_EVALUATED` | ≥480 outcome、≥3 事前 regime、每 regime ≥96 且分块 |
| 关联发现 | `UNKNOWN_NOT_EVALUATED` | 满足 96 候选预注册的窗口/缺失/多重检验与区间 |

预测增量的将来比较应使用同一 PIT outcome、同一 coverage 与同一 horizon 的 paired loss。Diebold–Mariano 类损失差异检验、Hansen 数据窥探/多模型控制、Engle 动态相关等只提供设计灵感；它们需要足够样本与正确假设，不能被 8 周期或本地 PASS 冒充。

---

## 14. 已知错误路径的永久禁令

以下路径在本版本永久禁止：

1. parse 后才保存 raw；
2. `HTTPError` 丢弃已有 response body；
3. attempt-only 中断后再次请求；
4. 把 in-flight attempt 误判成 crash；
5. failed checkpoint 后追加证据；
6. transport failure receipt 未绑定 checkpoint；
7. provider clock 静默夹取或政策未入 authority；
8. research READY 覆盖 monitor FAILED；
9. accepted state 已写而 monitor 未写且无法恢复；
10. Cycle 8 accepted 冒充实验终局；
11. 把 74 个显式路径称为完整 import closure；
12. 只扫描五文档而绕过 Q0–Q8 full loader；
13. 价格替代清算、注意力或跨市场；
14. 单帧盘口宣称严格韧性；
15. 缺失轴补零或迁移旧值冒充新来源；
16. 看到结果后改变关联 family/window/lag/多重检验；
17. 相关性、p-value 或文本直觉转成预测概率；
18. 序数云计算 Brier/ECE/EV；
19. 暗接 portfolio/reentry、账户或订单能力；
20. 资格 run、旧 run 或 fixture 样本计入正式 `8/8`。

---

## 15. 学术来源与使用限度

本设计从以下权威工作取得有限灵感，而非声称已经复现其全部统计条件：

- Diebold & Mariano (1995), predictive accuracy comparison：<https://doi.org/10.1080/07350015.1995.10524599>
- Engle (2002), Dynamic Conditional Correlation：<https://doi.org/10.1198/073500102288618487>
- Hansen (2005), Superior Predictive Ability / data snooping：<https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569>
- Benjamini & Yekutieli (2001), FDR under dependency：<https://doi.org/10.1214/aos/1013699998>
- Holm (1979), sequentially rejective multiple testing：<https://doi.org/10.2307/4615733>
- Pesaran & Timmermann (1992), directional accuracy：<https://doi.org/10.1080/07350015.1992.10509922>
- OKX 官方公开数据接口：<https://www.okx.com/docs-v5/en/>

这些文献不能把相关变成因果，也不能替代 point-in-time、数据质量、serial dependence、multiple testing、样本量、交易成本和 regime 覆盖。当前系统继续不作预测有效、校准、盈利或生产就绪声明。

---

## 16. 版本完成判据

V3.1.1 只有在以下全部满足时才可从 `PENDING_FINAL_AUTHORITY_FREEZE` 转为后继实验正式权威输入：

- 旧 authority/Q0–Q8/74 路径与旧失败 lineage 完整重放；
- raw-first、clock、Supervisor、commit recovery 故障注入通过；
- 十二轴 registry、run-local projection 与 UNKNOWN 边界可重放；
- 96 候选、BY/Holm、评价合同已在 outcome 前冻结；
- fresh public source、当前 Codex、fixed monitor 三资格来自独立 qualification run；
- qualification run 已退休且不计入 target；
- target runtime 静态闭包与 fresh-process trace union 全部摘要绑定；
- target 五文档由最终 full loader 投影；
- 仅保留一个 target automation，所有旧 automation 保持暂停；
- 全链仍为 `PUBLIC_NON_ACCOUNT_ONLY / NONE_LOCAL_SIMULATION / executable=false`。

即使正式目标 `8/8 + 8/8` 完成，本理论仍只获得一次受控前瞻运行证据；市场预测增量、概率校准、成本后收益与跨 regime 泛化继续按评价合同决定，不因实验顺利运行自动晋级。
