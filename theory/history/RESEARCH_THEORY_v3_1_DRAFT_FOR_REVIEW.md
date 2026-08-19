# 动态信息—数据—假说—路径—行为规划理论 v3.1（审查稿）

> 状态：`DRAFT_FOR_USER_REVIEW`
>
> 理论角色：`CANDIDATE_SUCCESSOR_TO_CORE_V2_1_AND_V3_DRAFT`
>
> 证据权限：`RESEARCH_DESIGN_AND_LOCAL_NON_EXECUTABLE_VERIFICATION_ONLY`
>
> 实验权限：`NONE_UNTIL_IMPLEMENTATION_AND_EXPLICIT_FRESH_RUN_AUTHORIZATION`
>
> 交易权限：`NONE / NO_PAPER / NO_LIVE / NO_ACCOUNT / NO_ORDER / NO_FUNDS`
>
> 日期：2026-08-06

本文件在 `CORE_TRADING_THEORY_v2_1.md` 的认识论与金融边界上，吸收 `CURRENT_RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md` 的连续状态、仓位、重入和恢复设计，并正式新增信息层、点时数据本体、动态类型图、相关性变更、概率云、开放假说发现、严格路径语言和稳健行为规划。

它是完整候选理论，不是对旧文档的静默覆盖，也不授权恢复任何旧实验。它在理论层明确禁止截至 2026-08-06 已识别的错误路径；是否已被当前本地核心实现机械关闭，必须以逐项验收证据为准。未被机械验证的项目保持 `OPEN/UNKNOWN`，不得由“设计存在”或邻近模块存在推断真实数据、Agent 增量、模型预测力、盈利性或生产可靠性已经得到验证。

### 0.1 规范目标、当前实现与证据状态

本文中的“必须”“系统维护”和数学定义首先表示 **V3.1 规范目标**，不自动表示当前代码已经实现。为避免能力等级被静默升级，本文统一使用三种状态：

- `MECHANICALLY_IMPLEMENTED`：当前代码能从冻结输入确定性复算或验证，并已有对应结构证据；
- `CONTRACT_OR_LOCAL_BASELINE_ONLY`：已有类型、容器或本地基线，但不能证明语义、外部来源或市场有效性；
- `TARGET_NOT_IMPLEMENTED`：属于本理论目标，在完成实现与验收前必须保持 UNKNOWN 或 failure-close。

截至本稿日期：PIT 数据与修订、当前注册图子集、假说/预期生命周期、四类概率对象的基本边界、云 update/repartition 收据、单步三值路径、完整有限动作网格、成本/风险复算和两阶段 proposal/selection 已具有局部机械实现。旧十轴到 V3.1 十二轴的版本化迁移、逐 contributor 的 PIT 精确绑定、prior-state change、六阶段状态接线，以及可由全新解释器仅凭 durable typed assembly bundle 重建完整 cycle，也已在固定输入下通过本地验证。高级关联估计、结构因果识别、一般 credal set 求解、概率模式 promotion、十二轴原生来源覆盖及其图投影、偏序/循环路径执行、冻结 payoff matrix 下的 EV/regret、连续组合变更/reentry 应用和新一轮前瞻实验仍未完整实现或未获得对应证据。

当前实现状态不改变 `CORE_TRADING_THEORY_v2_1.md` 的权威边界。V3.1 在用户审阅冻结前仍是候选理论；任何未列明能力不得由字段存在、本地 PASS、`accepted=true` 或摘要绑定推断出来。

---

## 1. 目标、对象与非目标

### 1.1 唯一目标

系统在每个决策时点只使用当时可得信息，持续回答五个问题：

1. 市场发生了什么，哪些只是消息、数据或代理；
2. 不同主体、受众、流动性与制度约束可能如何传导；
3. 哪些机制假说得到支持、冲突、失效或需要新增；
4. 未来可能沿哪些条件路径演化，何时应复核或否证；
5. 在真实仓位、成本、风险和权限下，当前合法行为是什么。

总链条为：

```text
信息事件与可观察行动
→ 点时事实与派生数据
→ 动态关联图与市场状态
→ 开放假说与概率云
→ 条件路径与未来趋势
→ 完整行为比较
→ 结果、误差归因与理论更新
```

### 1.2 非目标

V3.1 不承诺：

- 从公开信息还原任何人的真实内心、秘密计划或操盘身份；
- 用更多指标机械提高正确率；
- 把相关性、时间领先或文本共现解释为结构因果；
- 给未校准判断制造精确概率、期望收益或最优仓位；
- 用本地测试、单周期、`accepted=true` 或报告存在证明预测有效、盈利或生产就绪；
- 建设通用多 Agent 平台、恢复旧集群 transport，或接入真实交易权限。

---

## 2. V3.1 的十条公理

1. **事实先于解释，解释先于假说，假说先于动作。**
2. **市场是部分可观察、非平稳且反身的系统；`UNKNOWN` 是合法状态。**
3. **主体角色是时变标签，不是人格、本质身份或真实意图真值。**
4. **关联不等于机制，机制不等于已识别因果。**
5. **同一证据沿同一依赖谱系只能贡献一次。**
6. **研究候选空间开放，批准机制库、当轮工作集和动作可行域有限。**
7. **概率必须声明来源类型；未经校准的可能性不得进入 EV。**
8. **每个假说必须有来源子图、竞争解释、预期序列、反证、硬否证、期限和下一观察。**
9. **路径、动作、成交和收益评价彼此分离。**
10. **能力声明永远不得超过当前证据等级。**

---

## 3. 权威继承与冲突规则

### 3.1 必须继承 V2.1

- `FACT → MEASURE → INFERENCE → HYPOTHESIS/FORECAST → POLICY/ACTION → RISK` 的认识论层级；
- `available_at <= decision_at` 的点时约束，ACTUAL 与 RECONSTRUCTED 分离；
- D/L/C/F/R/K、严格 post-pressure 韧性、代理边界与缺失不补零；
- 多周期有序职责而非周期投票；
- 动态机制、偏序路径、OTHER、反证、hard falsifier 与 expiry；
- 证据等级、walk-forward、未见窗口、proper scoring 与分层误差归因。

### 3.2 必须继承 V3

- previous accepted state 与新增证据共同更新，禁止每轮重写世界观；
- persistent episode、belief、hypothesis、expectation、portfolio、geometry 与 reentry；
- CORE/TACTICAL 分离，target 是管理事件而非默认全平；
- `HOLD/OPEN/ADD/REDUCE/PARTIAL_EXIT/EXIT/REENTER/WAIT` 的完整动作集合；
- proposal 禁止 selected，封存完整 evaluation 后才 selection；
- WAIT 必须说明理由、机会成本、观察对象和复核时点；
- accepted 后只做确定性尾部，不重新调用 Agent 改写已接受判断；
- append-only event、preaccept、completion、checkpoint 与跨窗口恢复。

### 3.3 本文件纠正的冲突

- V3 的固定五路径只保留为可用 starter templates，不再是完整假说空间；
- 固定支持票数映射降级为实验编码，不能当通用概率函数；
- 当前 pilot 的三动作简化不再代表 V3.1 完整动作理论；
- transport 只允许作为最小边界适配器，不能成为系统中心；
- 信息层、数据本体、动态图、概率云和条件路径以本文件为候选新定义。

---

## 4. 认识论类型系统

每个对象必须声明且只能以适合自己的方式更新：

| 类型 | 定义 | 允许的例子 | 禁止的跳跃 |
|---|---|---|---|
| `SOURCE_ARTIFACT` | 原始来源或其不可变摘要 | 公告正文、讲话稿、订单簿响应、K 线响应 | 来源存在 ≠ 内容真实或影响已发生 |
| `OBSERVED_FACT` | 可点时观察并可追溯的事实 | 某时发布公告、某时成交、某值 OI | 事实 ≠ 动机或机制 |
| `DERIVED_MEASURE` | 由显式公式复算的量 | 收益、价差、事件窗异常收益 | 量 ≠ 关联或因果 |
| `ASSOCIATION` | 带模型、窗口和不确定性的关系 | DCC、条件相关、lead-lag、spillover | 关系 ≠ 结构因果 |
| `INFERENCE` | 有假设和竞争解释的推论 | 可能存在流动性收缩 | 推论 ≠ 主体真实意图 |
| `HYPOTHESIS` | 可证伪机制或路径主张 | 资金约束可能放大冲击 | 支持 ≠ 已证明 |
| `FORECAST` | 有事件、期限和评价合同的预期 | 未来 4H 波动扩张 | 预期 ≠ 决策 |
| `POLICY_CANDIDATE` | 在约束下待比较的行为 | WAIT、REDUCE_25 | 候选 ≠ 权限 |
| `AUTHORIZED_ACTION` | 确定性权限核批准的行为 | 当前研究阶段恒为不可执行 | 研究结论 ≠ 下单权限 |

所有心理、战略传播和“暗藏行为”分析至少属于 `INFERENCE`，并必须携带：观察依据、可能动机、至少一个竞争解释、可观察含义、反证和置信来源类型。

---

## 5. 信息层：主体、内容、行动、受众与传导

### 5.1 信息不是新闻标题

一个完整信息对象由六个相互独立的部分组成：

```text
谁在何种时变角色下
→ 通过什么渠道
→ 说了什么或做了什么
→ 哪些受众在什么约束下接收
→ 可能产生哪些竞争行为反应
→ 通过何种机制影响全局、行业、标的与仓位
```

转载、评论、摘要和二手报道不得冒充一手内容。讲话、法规草案、正式生效、资金行动和最终市场反应是不同事件，不能合并成一个“利多/利空”标签。

来源可信度必须把“文件内容摘要正确”“确由某次公开传输获得”“发布者身份与原始出处独立核验”“内容陈述为真”四件事分开。正式证据边界为：

- `LOCAL_SYNTHETIC`：只证明固定 fixture 可重放；
- `LOCAL_INPUT_UNATTESTED`：只有调用者提供的本地输入与自摘要；
- `SOURCE_ATTESTED`：请求身份、响应头、原始响应摘要、采集时间和 capture record 可复核；
- `EXTERNALLY_VERIFIED`：另有独立验证者与验证摘要。

`VERIFIED_PRIMARY` 不能由来源类型、官方标签或自哈希解锁，必须绑定严格 acquisition receipt；即便达到 `SOURCE_ATTESTED`，也只证明采集谱系，不证明发布内容、主体陈述或研究解释为真。全文覆盖只表示工件覆盖，不表示语义正确、事实真实或市场影响完整。

### 5.2 主体角色分类

主体可同时拥有多个角色，角色有 `valid_from/valid_to`，不得将个人或机构永久本质化。

| 角色族 | 典型主体 | 主要可观察责任/约束 | 合法分析问题 |
|---|---|---|---|
| `RULE_AND_SYSTEM_AUTHORITY` 规则与系统权威 | 央行、监管机构、财政部门、交易所规则部门、协议治理 | 制定规则、金融稳定、货币/审慎政策、准入与执法 | 政策动作、政策路径、实施概率、约束对象和传导 |
| `LIQUIDITY_AND_INTERMEDIATION` 流动性与中介 | 银行、做市商、投行、基金、交易所、稳定币赎回中介 | 融资、库存、报价、套利、保证金、佣金和风险容量 | 资金约束、价差、深度、基差、跨场套利与流动性螺旋 |
| `ISSUER_MANAGER_GOVERNANCE` 发行与管理 | 公司管理层、项目开发者、基金会、DAO、验证者、代币治理 | 披露、产品、代币经济、财库、升级、安全和治理 | 可观察承诺、可逆性、执行进度、个体标的现金流/采用/供给影响 |
| `POLITICAL_AGENDA_AND_POLICY_SIGNAL` 政治议程与政策信号 | 政界发言者、候选人、立法者、顾问 | 选举激励、议程设置、政策承诺、联盟与公众协调 | 发言的政策状态、受众、激励冲突、实施链和政策不确定性 |
| `ATTENTION_NARRATIVE_INFLUENCE` 注意力与叙事影响 | 媒体、研究员、网红、大户公开账户、社区意见领袖、多空倡议者 | 争夺注意力、声誉、订阅、流量、募资或仓位利益 | 覆盖范围、受众先验、传播速度、重复度、披露利益和注意力转化 |
| `ENDOGENOUS_MARKET_PARTICIPANT` 内生市场参与 | 套利者、趋势者、被动资金、零售、矿工、验证者、套保者、清算者 | 受资金、期限、规则、风险预算和策略约束 | 哪类可观察行为与哪条机制相容，而非猜测具体身份 |

“规格制定者”“流动性创造者”“市场管理者”“政治选票操盘手”“情绪与流量收割机”可以作为研究者提出的角色假说，但正式记录必须使用上表的中性角色、可观察激励和竞争解释。不得先验断言某主体正在操盘、收割或欺骗。

### 5.3 信息事件分类

每个事件同时使用多轴标签，不以单一文件夹分类：

- **范围**：`GLOBAL_MACRO / SECTOR / VENUE / ENTITY / INSTRUMENT / PORTFOLIO`；
- **形式**：`OBSERVED_ACTION / FORMAL_RULE / POLICY_DECISION / FORWARD_GUIDANCE / DISCLOSURE / OPINION / RUMOR / CORRECTION / SILENCE_OR_WITHHOLDING_HYPOTHESIS`；
- **制度状态**：`PROPOSED / CONSULTATION / APPROVED / EFFECTIVE / ENFORCED / REVERSED / EXPIRED / UNKNOWN`；
- **新颖度**：`NEW / CONFIRMATION / REVISION / REPETITION / CONTRADICTION`；
- **承诺度**：`NON_BINDING / PARTIALLY_BINDING / BINDING`；
- **可逆性**：`REVERSIBLE / COSTLY_TO_REVERSE / IRREVERSIBLE / UNKNOWN`；
- **传播**：`PRIMARY / SYNDICATED / COMMENTARY / DERIVED_SUMMARY`；
- **时钟**：`published_at / observed_at / available_at / effective_at / revised_at`；
- **证据质量**：来源、全文覆盖、语言/翻译、完整性、冲突、陈旧、缺失与 lineage。

### 5.4 受众与行为响应

受众不是一个“市场大众”。每条信息至少考虑可能相关的分群：

- 长期基本面投资者；
- 杠杆方向交易者；
- 期权/波动率交易者；
- 做市、套利与库存管理者；
- 被动与规则型资金；
- 零售与注意力驱动参与者；
- 发行方、矿工、验证者、开发者或治理参与者；
- 监管、合规与银行中介。

每个受众反应必须写成竞争假说：

```text
可观察信息 E
→ 受众 A 在约束 C 下可能更新信念或行为 B
→ 产生可观察中介 M（流、价差、波动、基差、搜索、链上行为等）
→ 才可能沿机制 H 影响目标 Y
```

同一信息可使不同受众采取相反行为；系统保留冲突，不以简单正负票数抵消。

### 5.5 宏观到个体的传导

全局影响与个体影响必须分边记录：

```text
制度/宏观事件
→ 政策路径、贴现率、融资条件、风险预算或共同注意力
→ 市场/行业状态
→ 标的特定现金流、采用、供给、治理、交易场或资产负债表暴露
→ 微观流动性、杠杆与价格反应
```

允许存在个体反向影响全局的反馈边，例如大型稳定币、系统性交易所或龙头资产的冲击；但必须声明阈值、网络位置和 regime 条件。

---

## 6. 数据层：点时本体、质量与可复算建模

### 6.1 核心对象

数据层至少维护：

1. `SourceArtifact`：原始正文/响应及物理摘要；
2. `InformationActor` 与 `ActorRoleAssignment`；
3. `InformationEvent` 与修订链；
4. `MarketFact`：原始市场、宏观、链上、公司/协议事实；
5. `DerivedMeasure`：公式、参数、输入 lineage 和结果；
6. `AssociationEstimate`：相关性、领先、spillover 等关系；
7. `RegimeEstimate`：明确标记为潜变量估计；
8. `QualityAssessment`：覆盖、缺失、冲突、代理和时效；
9. `GraphRevision`：节点/边的新增、变更、失效；
10. `CycleEvidenceReceipt`：当轮所有输入、推论和输出的不可变绑定。

### 6.2 统一事实合同

任何进入推论链的数据对象至少具有下列结构字段；字段存在不等于其值必然非空，可选原始绑定、缺失值和派生对象必须遵守各自合同：

```text
datum_id, epistemic_type, data_kind, category, metric
source_id, source_type, source_ref, raw_ref, raw_sha256
instrument_id, asset_class, venue_id, entity_ids
actor_ids, audience_ids, event_ids
value, unit, currency, frequency, timeframe, window
observed_at, published_at, available_at, effective_at, revised_at, as_of
vintage_id, revision, revision_of_digest, formula_version
input_refs, input_digests
quality, coverage, missingness, staleness, conflict_state, proxy_level
uncertainty, regime_ref
dependency_group, lineage, limitations
hypothesis_admissible, inference_admissible, claim_ceiling, missing_is_zero, executable, datum_digest
```

`raw_ref/raw_sha256` 是成对可选的原始绑定；未知值或没有独立原始载荷的派生对象不得伪造摘要。派生对象必须通过 `input_refs/input_digests` 绑定输入；`hypothesis_admissible`、`inference_admissible` 与 `claim_ceiling` 是确定性派生结果，不由 Agent 填写。

时钟语义：

- `observed_at`：系统观察或采样这一版本的时间；现象所属时点由 `as_of`、`effective_at` 或事件引用表达；
- `published_at`：来源公开时间；
- `available_at`：系统能够合法使用的最早时间；
- `effective_at`：规则或状态真正生效时间；
- `revised_at`：后续更正时间；
- `as_of`：此对象描述的目标时点。

`available_at` 不得被 `effective_at` 或修订后的值替代。经济数据、公告和链上标签必须保留 vintage；后见修订只能进入新的 revision，不得回写旧决策。

### 6.3 数据质量不是单一覆盖率

质量向量为：

```text
Q = (source_reliability, completeness, timeliness, semantic_fidelity,
     measurement_error, revision_risk, cross_source_consistency,
     lineage_integrity, dependency_independence, regime_applicability)
```

任一分量不足时，系统缩窄主张或保留 UNKNOWN。`14/15` 不是“完整”；缺失 liquidation 不是零；单张 REST 订单簿不能证明严格韧性；新闻 metadata 不是正文影响。

质量不做加权平均，而形成声明上限函数：

\[
Ceiling(x,t)=\begin{cases}
NO\_INFERENCE,& value=\varnothing\;\lor\;coverage=0\;\lor\;conflict\neq NONE\\
DESCRIPTIVE\_OR\_HYPOTHESIS\_ONLY,& lineage/coverage/critical\ quality\ 不完整\\
ASSOCIATION\_OR\_HYPOTHESIS\_ONLY,& PIT、谱系、覆盖与关键质量门均通过
\end{cases}
\]

`Ceiling` 是权限上限，不是置信分数。低质量对象可以作为“存在缺失或冲突”的事实被记录，但其数值方向不得进入路径触发、概率更新或动作支持。`DESCRIPTIVE_OR_HYPOTHESIS_ONLY` 只允许生成带限制的候选解释，不允许直接成为方向性路径谓词、概率质量移动或动作证据。派生量还必须满足输入有向无环图：每条输入边绑定 `(input_id,input_digest,available_at)`，且沿任一路径的可得时间不下降。

**当前实现边界：** 当前代码已把两种准入机械分离：`DESCRIPTIVE_OR_HYPOTHESIS_ONLY` 可作为受限候选假说的来源，即 `hypothesis_admissible=true / inference_admissible=false`；它不能进入概率云更新、关联估计、路径求值或动作证据。`NO_INFERENCE` 两种准入均为 false。该门只证明本地合同能阻断越权引用，不证明质量标签、来源内容或市场语义在现实中必然正确。

### 6.4 多时间尺度的关系

周期承担不同职责，不能多数投票：

- 战略：1W/1D/4H，负责 episode、宏观制度、主机制与硬失效；
- 战术：1H，负责路径转移、吸收/衰竭、风险调整；
- 执行：15M 或更细，负责成交、保护、成本和局部异常。

跨周期一致性必须是关系型主张，例如“1H 回撤未破坏 4H 结构且 15M 出现吸收”，而不是“三个正向减一个负向”。

---

## 7. 动态类型图：信息、数据、假说与动作的共同骨架

### 7.1 图定义

在决策时点 \(t\)，维护版本化有向多重图：

\[
G_t=(V_t,E_t,\tau_V,\tau_E,\mathcal{A}_t)
\]

其中 `τV` 是节点类型，`τE` 是边类型，`A` 保存时钟、质量、窗口、regime、证据和不确定性。图不是“真相图”，而是点时知识状态。

以下节点与边是 V3.1 的 **目标词汇表**。当前运行图只接纳代码中已注册的类型子集；未注册类型不得写入运行图，也不得声称已经实现。当前实现中的 `ASSOCIATION` 主要是带类型、窗口与不确定性的边，而不是独立节点；目标本体允许在需要保存估计历史时将其投影为 `ASSOCIATION_ESTIMATE` 节点。

节点类型：

- `ACTOR / ACTOR_ROLE / AUDIENCE_SEGMENT`；
- `SOURCE_ARTIFACT / INFORMATION_EVENT / OBSERVED_ACTION`；
- `MARKET_FACT / DERIVED_MEASURE / LATENT_FACTOR / REGIME`；
- `ASSOCIATION_ESTIMATE / MECHANISM_HYPOTHESIS / PATH_HYPOTHESIS`；
- `EXPECTATION / SCENARIO_STATE / ACTION_CANDIDATE / OUTCOME`；
- `RISK_CONSTRAINT / PORTFOLIO_LOT / ERROR_ATTRIBUTION`。

边类型必须显式分开：

- 事实/来源：`EMITS / REPORTS / REVISES / DERIVED_FROM / OBSERVED_BY / TARGETS`；
- 传播：`TRANSMITS_TO / AMPLIFIES / DAMPENS / CONDITIONS`；
- 统计：`ASSOCIATED_WITH / PARTIALLY_ASSOCIATED_WITH / LEADS / PREDICTS / SPILLOVER_TO`；
- 假说：`SUPPORTS / OPPOSES / SOFT_CONTRADICTS / HARD_FALSIFIES / EXPLAINS / ALTERNATIVE_TO`；
- 生命周期：`PARENT_OF / SPLIT_FROM / MERGED_FROM / SUPERSEDES / EXPIRES`；
- 决策：`FAVORS_ACTION / OPPOSES_ACTION / BLOCKED_BY_RISK / EVALUATED_BY_OUTCOME`；
- 因果：只有受信估计收据、独立识别验证和人工冻结均通过时才可用 `IDENTIFIED_CAUSAL_EFFECT`；只有结构合法的 identification contract 不证明识别成立，否则只能用 `MECHANISM_CAUSAL_HYPOTHESIS`。

### 7.2 图变化

每轮只提交增量：

\[
\Delta G_t=(V_t^+,V_t^-,E_t^+,E_t^-,A_t^{revision})
\]

每个增量保存 `reason/evidence_refs/previous_version/new_version/available_at/actor/model/review_status`。`V^-` 与 `E^-` 只表示追加一个失效、retire 或 supersede revision，不表示物理删除；历史对象不得抹去。

图变化本身是可分析事件：相关性断裂、主体角色改变、信息传播速度改变、机制边冲突增加，都可触发新的假说，但不能自动触发动作。

任一可进入行动比较的节点必须存在完整的相邻层证明路径：

\[
SOURCE/INFO \rightsquigarrow FACT \rightsquigarrow MEASURE
\rightsquigarrow ASSOCIATION/STATE \rightsquigarrow HYPOTHESIS
\rightsquigarrow EXPECTATION/PATH \rightsquigarrow ACTION
\]

这里的 `\rightsquigarrow` 只能由类型允许、PIT 合法、摘要绑定且未失效的边组成；`ASSOCIATION` 可以是跨相邻状态的有类型边。信息到动作、图后层对象反向作为同轮概率证据、或 action/evaluation 再证明自身，均构成循环证据并失败关闭。

### 7.3 去重与冲突

- 共享 `dependency_group` 的证据不得被多条边重复计权；
- 同源转载默认属于同一 lineage；
- 冲突来源同时保留，不用平均值掩盖；
- 图的密度、中心性或聚类只是派生量，除非有冻结合同，不能自动解释为系统重要性或因果地位。

当前 dependency index 证明哪些对象共享谱系，但不会自动完成贝叶斯或统计权重去重。“只能贡献一次”因此是概率更新器和估计器必须执行的规范，不得仅凭 dependency 字段存在宣称已完成定量去重。

---

## 8. 相关性与关联变化建模

### 8.1 关联类型

系统必须区分：

1. 无条件相关；
2. 条件相关；
3. 偏相关；
4. lead-lag / Granger predictive relation；
5. time-varying conditional correlation；
6. cross-timeframe 与 cross-asset 关联；
7. tail dependence、co-jump 与 volatility spillover；
8. regime-conditioned association；
9. event-window reaction；
10. structural causal effect（仅在识别成立时）。

下列是目标统计对象应覆盖的语义字段。当前 `AssociationRevision` 使用 `association_type/method/estimate_interval/window/lag/regime/coverage/stability/dependency_group_ids/provenance/validity/identification_contract/status` 等注册字段；两者必须由显式适配器映射，不得把自由文本字段当作已经计算的统计结果。

每个目标 `AssociationEstimate` 必须覆盖：

```text
relation_type, source_node, target_node, direction
estimator, model_version, transform, lag, horizon, window
sample_start, sample_end, point_in_time_cutoff
estimate, uncertainty_interval, sign, strength_bucket
coverage, effective_sample_size, missingness
regime_ref, stability, break_evidence, multiple_testing_control
dependency_group, confounder_set, limitations
created_at, available_at, expires_at, supersedes
```

### 8.2 动态相关

DCC、rolling/expanding estimates、state-space 或 change-point 方法都只是候选估计器。系统比较：

\[
\rho_{ij,t|r}=Corr(X_{i,t},X_{j,t}\mid Z_t,Regime_t=r)
\]

并记录变化：

\[
\Delta\rho_{ij,t}=\rho_{ij,t|r}-\rho_{ij,t-k|r'}
\]

只有当窗口、样本、估计器、regime 和不确定性均可比时，才允许解释变化。若两个估计共享样本，必须由联合重采样、状态空间模型或明确协方差得到变化区间 `I(Δρ)`，不得把两个独立区间简单相减；`0∈I(Δρ)` 时默认结论是“变化未被当前设计区分”，而不是“相关性已上升/下降”。多 lag、多资产和多窗口搜索必须保存候选全集与 multiplicity control，不能只记录最显著结果。相关性上升既可能来自共同冲击，也可能来自流动性收缩、杠杆联动或样本缩短；这些是竞争机制，不是自动结论。

### 8.3 领先不等于结构因果

`X LEADS Y` 只表示在给定模型和信息集下，X 的过去增量改善 Y 的预测。它必须标记 `GRANGER_PREDICTIVE_NOT_STRUCTURAL_CAUSAL`，并保留共同原因、同步发布、数据时钟错位和交易时段等替代解释。

### 8.4 当前实现边界

当前唯一可本地复算的关联估计器是配对 Pearson 基线、Fisher 95% 区间及不重叠窗口比较。它能验证输入数值与 PIT datum 的逐对绑定，但尚未机器绑定 prospective manifest、候选 pair 全集、window/lag 搜索空间或 multiplicity plan，因此不能仅凭 receipt 自称“已预注册”。DCC、Granger、tail dependence、co-jump、spillover、event-window 与结构因果均为目标合同，尚非当前能力。Pearson 基线中的 `multiple_testing_control` 当前只是必须声明的字段，并不会由该函数执行多重检验校正。

没有受信估计收据的 `AssociationRevision` 只是声明容器，不能单凭 `method`、区间和摘要进入概率云或动作证据。结构合法的 identification contract 只证明字段和假设被声明，不证明识别假设成立；在独立识别验证器完成前，`IDENTIFIED_CAUSAL_EFFECT` 必须从新实验的概率与动作证据白名单中排除。

---

## 9. 概率云：在不确定性下表达可能性而不制造伪概率

### 9.1 为什么是云而不是一个数字

假说通常不互斥，数据有缺失，模型和 regime 不确定。因此 V3.1 的默认输出不是合计 100% 的路径表，而是带来源、区间、冲突和敏感性的对象集合。

### 9.2 三层证据、四种互不冒充的对象

#### A. `SUBJECTIVE_PLAUSIBILITY`

适用于 Agent 基于机制、信息经济学、行为心理与有限证据提出的可能性。表示为序数等级或宽包络：

\[
C_t(h)=[\underline c_t(h),\overline c_t(h)],\quad h\in\mathcal H_t
\]

不同假说可共存，区间不归一，不称 calibrated probability，不计算 EV。每个对象必须有竞争解释和敏感性。

#### B. `EMPIRICAL_OR_MODEL_CONDITIONAL`

适用于有明确事件、样本、识别方法或模型的频率、识别区间或条件分布：

\[
P_t(Y\in A)\in[\underline p_t(A),\overline p_t(A)]
\]

必须保存事件定义、样本选择、模型集、先验、识别区间、误差、遗漏模型风险与适用 regime。模型条件分布只在其假设下成立；未经独立校准不得升级为可靠预测分布。

#### C. `MARKET_IMPLIED_BELIEF`

适用于期权、预测市场或其他价格所隐含的信念对象。必须记录合约事件、期限、流动性、风险溢价、财富/风险偏好、市场分割与可套利性。它不称客观概率，也不能与经验频率静默合并。

#### D. `CALIBRATED_PREDICTIVE_DISTRIBUTION`

只在下列条件同时满足时允许：

- 标签集合有限、互斥、完备并包含 `OTHER`；
- 预测事件、期限和评价时钟冻结；
- 有独立 calibration 窗口和 proper scoring；
- 模型、样本、漂移和失效合同明确；
- 样本外表现未显示系统性失准。

此时才可维护：

\[
\sum_{h\in\mathcal H_t\cup\{OTHER\}}P_t(h)=1
\]

目标模型集合仍应保存 posterior range、ensemble dispersion 和 regime sensitivity，不以单一平均数掩盖模型不确定性；这些字段目前不是一般模型集合求解能力的证明。

只有对有限、显式互斥且完备的经验/模型结果分区，才允许把约束表示为可行分布集合（credal set）：

\[
\mathcal K_t=\{p\in\Delta(\Omega_t): A_tp\le b_t,\;C_tp=d_t\}
\]

其上下概率为 `lower P(A)=inf_{p∈K}p(A)`、`upper P(A)=sup_{p∈K}p(A)`。只有 `K_t` 非空、事件分区 `Ω_t` 互斥完备、评价期限一致且校准收据绑定同一事件合同时，才具备概率侧的归一分布资格。非互斥假说的边际区间不是一般 `K_t`；`SUBJECTIVE_PLAUSIBILITY` 也不是 `K_t`，其数值包络不满足可加性，不得通过归一化“升级”为概率。

**当前实现边界：** 当前代码只验证分量区间、分区标志和有限分区的基本可行性，不求解一般 `A_t,b_t,C_t,d_t`，也不计算 credal lower/upper probability。当前本地可重放的 calibrated receipt 仅支持有限分类的 `CONSTANT_CATEGORICAL_DISTRIBUTION_V1`、Brier 或 log score、固定分箱 classwise ECE 与有限漂移阈值；它证明本地冻结样本上的计算一致性，不证明外部样本来源真实性、模型增量、sharpness 或长期校准。

### 9.3 更新合同

任何目标云更新均写为：

\[
Cloud_{t+1}=U(Cloud_t,E_t,Q_t,D_t,R_t,M_t)
\]

其中 `E` 是新增证据，`Q` 是质量，`D` 是依赖/重复关系，`R` 是 regime，`M` 是模型。当前通用 update receipt 只绑定声明的 prior、updated cloud 与证据，不会复算任意更新函数 `U`；只有 estimator-specific verifier 能从输入重建结果时，才可称该数值变化由模型计算得到。收据必须保存：

- prior object 与模式；
- 新证据和可用时点；
- 支持、反证、冲突与缺失；
- dependency adjustment；
- update method/version；
- posterior/envelope 变化；
- 对模型、窗口、质量和竞争解释的敏感性；
- 无更新时的理由。

未经校准的心理猜测只能改变 `SUBJECTIVE_PLAUSIBILITY`，不能改变风险预算、EV 或仓位比例。

普通更新必须保持 `cloud_id / event_contract / horizon / mode / component_set` 不变。新增、拆分、合并或退出假说会改变事件空间，必须创建显式 `REPARTITION` 收据与新 cloud id，并保存旧新成员映射；模式升级必须创建独立 promotion/validation receipt，不能借一次 update 改名。当前实现已验证 update/repartition，但尚无通用 mode-promotion 状态机；在其完成前，模式改变必须 failure-close。

---

## 10. 假说层：开放发现、有限工作集与生命周期

### 10.1 三层假说空间

1. `APPROVED_PRIMITIVE_LIBRARY`：有限、冻结、经治理的机制原语；
2. `OPEN_RESEARCH_CANDIDATE_REGISTRY`：Agent 可新增语义方向；
3. `ACTIVE_WORKING_SET`：当轮有限注意预算中的 lead、runner-up 与 OTHER。

开放性不意味着 Agent 可以修改历史、计算结果、权限或已批准原语。新候选只有经过独立前瞻窗口、反事实比较、稳定性和人工冻结，才能晋升原语。

### 10.2 假说来源

Agent 从信息与数据图的局部子图提出候选，而不是从一个指标生成结论：

```text
actor/event/audience subgraph
+ market facts and measures
+ association/regime changes
+ known mechanism primitives
+ unresolved residuals / OTHER
→ candidate hypothesis
```

新增假说必须解释它比现有候选多区分什么；纯同义改写、模板变体和无新 falsifier 的叙事被拒绝。

候选 `h` 的规范性准入条件不是“分数够高”，而是以下布尔合取：

\[
Admit(h)=PIT(h)\land Lineage(h)\land MechanismPath(h)
\land ObservableDifference(h)\land Falsifier(h)\land NonDuplicate(h)
\]

`ObservableDifference` 要求至少存在一个未来观察，在同一时间窗内对新候选与现有候选产生不同的确认/反证结果。候选命名空间开放且不预枚举，但每次请求、每轮新增、registry 总量与当轮 active set 都必须有明确有限上限；超出预算的候选进入 WATCH/ARCHIVE，不得通过删除 OTHER 或旧反证历史腾出“概率”。

当前确定性 reducer 机械验证结构、PIT、生命周期、ID/语义指纹去重、显式 evidence 引用和 falsifier 字段；它不能仅凭非空文本或摘要证明 `MechanismPath` 真实、`ObservableDifference` 有语义区分力或新候选不是更隐蔽的同义改写。这些条件仍需独立语义审查，并在前瞻结果中接受证伪。

### 10.3 假说合同

```text
hypothesis_id, title, type, status, horizon, applicability
origin_subgraph_refs, parent_ids, alternative_ids
mechanism_chain, assumptions, audience_response_hypotheses
support_refs, opposition_refs, dependency_groups
probability_cloud_ref, expected_observation_sequence
soft_contradictions, hard_falsifiers, expiry
next_observation, next_review_at
created_at, revised_at, superseded_by, owner
```

生命周期操作：`CREATE / REVISE / PROMOTE / DEMOTE / SPLIT / MERGE / SUPERSEDE / INVALIDATE / EXPIRE / ARCHIVE / RESTORE`。Agent 提议，确定性 reducer 验证前提、所有权和事件顺序后执行。

### 10.4 残差驱动发现

当 lead 与 runner-up 都不能解释新增事实，或结果连续落入预测区间外，Agent 提案策略必须优先更新 `OTHER/UNKNOWN` 和 error attribution，而不是强行增强最接近的旧假说。确定性层只验证显式 delta，不自动发现“无法解释的残差”。只有能提出可观察机制和反证的新方向才进入 candidate registry。

---

## 11. 完整市场分析体系

每轮市场分析遵循由上至下再反馈的六层结构：

1. **规则与宏观**：政策状态、政策路径、贴现率、财政、监管、地缘和制度存续；
2. **融资与中介**：资金成本、保证金、做市库存、基差、套利容量、稳定币/银行/交易所约束；
3. **发行与治理**：公司/协议披露、财库、供给、采用、产品、升级、安全和治理；
4. **跨市场网络**：共同因子、风险偏好、关联变化、spillover、系统节点与市场分割；
5. **微观结构与仓位**：D/L/C/F/R、订单流代理、深度、价差、冲击、杠杆与拥挤；
6. **信息、注意力与行为**：事件新颖度、传播、受众反应、叙事冲突和注意力转化。

分析最终形成：

- 当前可观察状态；
- 主机制与竞争机制；
- 关键未知；
- 图变化；
- 概率云变化；
- 未来路径；
- 能区分路径的下一信息请求；
- 当前合法动作及机会成本。

六层结构是每轮的目标分析清单，不是数据已完整覆盖的声明。任何缺失层必须显示为 UNKNOWN/NOT_AVAILABLE，并记录对假说、路径和动作声明上限的影响；第一轮形成 genesis cloud，只有存在绑定的 prior cloud 与 transition receipt 时才可称“概率云变化”。

---

## 12. 未来趋势与严格 if–then 路径体系

### 12.1 趋势不是方向标签

趋势是条件化状态迁移：在某些前提、约束和 regime 下，哪些状态更可能先后出现。目标路径模型允许分支、合流、可选业务状态跳过、重复和到期，使用有向无环场景片段或显式循环状态机，不使用固定剧本；认识论证明链本身不得跳层。

### 12.2 机器可验规则

每条路径规则必须包含：

```text
IF      point-in-time observations with fact refs
AND     quality, coverage, regime and portfolio guards
UNLESS  explicit counter-evidence, risk veto or permission veto
THEN    one typed state / graph / hypothesis / expectation update
BECAUSE an explicit mechanism chain
EXPECT  observable sequence and horizon
ELSE IF competing branch ...
ELSE    preserve OTHER/UNKNOWN and define information request
FALSIFIED WHEN hard observable condition occurs
EXPIRES AT / WHEN ...
ACTION IMPLICATION favors/opposes/conditional only
NEXT REVIEW AT / WHEN ...
```

`THEN` 一次只能跨一个认识论层级。信息偏正面不能直接 `THEN OPEN_LONG`；必须先形成推论、假说、路径，再进入完整动作比较。

条件求值使用三值逻辑 `TRUE / FALSE / UNKNOWN`。事实缺失、在评价时点尚不可得、质量低于门槛、覆盖不足或冲突状态不允许时为 `UNKNOWN`，绝不折算为 `FALSE`。未提供绑定可以产生 `UNKNOWN`；但已提供事实的 `fact_digest` 与谓词绑定不一致属于完整性错误，必须 failure-close，不能降级为 UNKNOWN。对规则 `r`：

\[
Truth_t(r)=\begin{cases}
FALSE,& t\ge expiry\;\lor\;\exists positive=FALSE\;\lor\;\exists blocker/falsifier=TRUE\\
UNKNOWN,& otherwise\;\land\;\exists relevant\ predicate=UNKNOWN\\
TRUE,& otherwise
\end{cases}
\]

若任一正条件为 `FALSE`、任一 `UNLESS`/到期 hard falsifier 为 `TRUE`，路径为 `FALSE`；若尚未得到 `FALSE`、但任一必要正条件、反条件或到期 falsifier 为 `UNKNOWN`，路径为 `UNKNOWN`，只能保留条件观察并导向 WAIT/HOLD，不能支撑 OPEN/ADD。到期或已命中 hard falsifier 的路径不得因重新签名文档而恢复，恢复必须走新的假说/路径 revision。未来 falsifier 只有在后续 monitor/outcome 对旧路径进行摘要绑定的重放并产生 receipt 后，才可声称已命中；创建路径时仅封存 future monitor 不等于已经执行反证。

### 12.3 场景路径对象

```text
path_id, start_state, regime_guards
ordered_or_partial_order_steps
branch_conditions, merge_conditions
required_observations, quality_guards
mechanism_hypotheses, probability_cloud_refs
soft_contradictions, hard_falsifiers, expiry
action_implications, risk_implications
opportunity_cost, next_review
```

默认 starter paths 可以包括延续、回撤后延续、拥挤反转、流动性冲击、区间/不确定与事件重定价，但它们不限制新增方向。

**当前实现边界：** 当前 `ScenarioPathRule` 只实现一组 trigger/guard/unless、一个相邻认识论 transition、future falsifier 与 action implication；`ScenarioPathSet` 是单步规则集合，不是 ordered/partial-order DAG 或循环状态机执行器。分支合流、偏序步骤、循环和跨周期旧路径监控在完成专用执行器与 receipt 验收前均为 `TARGET_NOT_IMPLEMENTED`。

---

## 13. 情绪体系：不压成单一总分

V3.1 目标情绪本体使用十二个可解释轴；它们是并列视角，不合成为总情绪分：

1. `PRICE_DIRECTIONAL_PRESSURE`：价格与方向压力；
2. `STRUCTURE_PERSISTENCE`：趋势、区间、关键结构与其持续性；
3. `PARTICIPATION_AND_ACTIVE_FLOW`：参与、主动流与承接；
4. `CROWDING_DIRECTION`：拥挤方向；
5. `LEVERAGE_CHANGE`：杠杆变化；
6. `FORCED_DELEVERAGING_PRESSURE`：强制去杠杆压力；
7. `LIQUIDITY_RESILIENCE`：流动性与韧性；
8. `VOLATILITY_AND_TAIL_STRESS`：波动与尾部风险；
9. `EVENT_AND_NARRATIVE_REACTION`：信息事件与叙事反应；
10. `ATTENTION_AND_AUDIENCE_RESPONSE`：注意力与受众行为；
11. `CROSS_MARKET_RISK_APPETITE_AND_REGIME`：跨市场风险偏好与 regime；
12. `TIMEFRAME_COHERENCE`：战略、战术与执行周期之间的关系型一致性。

每轴目标输出为 `state/evidence_refs/inference/alternatives/quality/timeframe/change/next_observation`。`change` 必须绑定前一 sentiment state digest；没有前序状态时为 UNKNOWN。轴内 ordinal 只是可审计压缩摘要，不是概率、证据强度或净支持票数；即使 ordinal 为 0，也必须单独保留 conflict、coverage、supporting/opposing contributors 和 dependency groups，不得自动解释为市场中性。

禁止：低成交量=卖压、周期票数相加、无 fact_ref 的符号、标题数量当影响、总分 70 或“极度看多”直接映射动作。

**当前实现边界：** legacy `build_sentiment_state` 仍使用十轴：`PRICE_DIRECTIONAL_PRESSURE / STRUCTURE_PERSISTENCE / PARTICIPATION_AND_FLOW / CROWDING_DIRECTION / LEVERAGE_CHANGE / LIQUIDITY_RESILIENCE / VOLATILITY_STRESS / CROSS_MARKET_RISK_APPETITE / EVENT_REACTION / TIMEFRAME_COHERENCE`。当前 V3.1 cycle 已用版本化对象显式迁移为上述十二轴：可映射轴记录 mapping；`FORCED_DELEVERAGING_PRESSURE` 与 `ATTENTION_AND_AUDIENCE_RESPONSE` 在没有直接数据时固定为 UNKNOWN。每个实际 contributor 必须绑定同一已验证 PIT dataset 中的 exact datum digest，并逐字段核对数值、单位、窗口、来源、原始摘要、时间和 dependency group；PATH/ACTION 范围只接受 `INFERENCE_ADMISSIBLE` 数据。十二轴 state/change 已进入 inputs、proposal、preselection、accepted、completion 与 checkpoint 头，但这只证明本地合同：原生十二轴外部来源覆盖、语义正确性、图内显式情绪状态节点和任何市场有效性仍未验证。

---

## 14. 行为规划与仓位决策

### 14.1 完整动作域

根据当前 portfolio truth 生成全部合法候选：

- `HOLD`；
- `OPEN_LONG / OPEN_SHORT`；
- `ADD_25 / ADD_50 / ADD_75 / ADD_100`；
- `REDUCE_25 / REDUCE_50 / REDUCE_75`；
- `PARTIAL_EXIT`；
- `EXIT_100`；
- `REENTER_LONG / REENTER_SHORT`；
- `WAIT`。

无仓位时不生成 HOLD/REDUCE；有仓位时不得静默删除 EXIT 或风险保护；相邻尺度必须在同一费用、滑点、风险和信息条件下比较。

### 14.2 概率模式决定决策方法

- `SUBJECTIVE_PLAUSIBILITY`：只允许非数值的风险支配、稳健性、可逆性、机会成本、风险预算上限和信息价值比较；禁止 EV；
- `EMPIRICAL_OR_MODEL_CONDITIONAL`：在明确误差、识别区间和模型集下做敏感性，不把模型输出当无条件真值；
- `MARKET_IMPLIED_BELIEF`：必须扣除流动性、风险溢价、合约和市场分割影响，不把价格当物理概率；
- `CALIBRATED_PREDICTIVE_DISTRIBUTION`：只通过概率侧资格门；还必须存在同一事件合同下的冻结 payoff matrix、效用函数、情景成本和模型不确定性处理，才允许计算期望效用。

若不同可信模型给出不同动作，系统优先选择对模型误差更稳健、可逆且不触犯风险约束的动作，或 WAIT 并明确获取哪项信息最能降低决策不确定性。

令 `A(s_t)` 为由真实 portfolio truth、lot/role 与有限尺度网格生成的完整合法动作集；确定性金融内核从价格、数量、合约乘数、费用、滑点、保证金、保护位与风险 policy 复算可行集 `F_t⊆A(s_t)`。Agent 不得提交这些数值作为真值。

只有对冻结互斥结果集和已校准 `p`，才计算：

\[
EU(a)=\sum_{\omega\in\Omega}p(\omega)U(W_t+GrossPayoff(a,\omega)-Cost(a,\omega))
\]

若仅有可行概率集合 `K_t`，采用显式稳健准则，例如最大 regret：

\[
a^*\in\arg\min_{a\in F_t}\sup_{p\in\mathcal K_t}
\left[\max_{b\in F_t}E_pU(b)-E_pU(a)\right]
\]

若只有主观序数 plausibility，则不把等级代入上式；只比较硬风险支配、情景稳健性、可逆性、机会成本和下一信息价值。没有冻结 payoff matrix 时，regret 数值也保持 UNKNOWN，不能因 `expected_value_allowed=true` 字段存在而升级。

**当前实现边界：** 当前 V3.1 金融内核从原子 portfolio/market/risk inputs 复算 action cost、风险、保证金、名义敞口和可行性，但尚未把冻结 path payoff matrix 接入 `financial_evaluation`。因此无论概率云模式为何，当前 V3.1 cycle 的 EV 与 numeric regret 均必须保持 `None/UNKNOWN`。

### 14.3 WAIT 合同

WAIT 必须同时包含：

- 当前阻止行动的具体条件；
- 与相邻合法动作相比的机会成本；
- 正在等待的观察对象；
- 最晚复核时间或触发事件；
- 若信息未到达时的默认处理；
- 当前仓位的保护责任。

### 14.4 连续仓位

- strategic episode 与当前 exposure 分离；
- CORE 与 TACTICAL lot 独立；
- target 只触发管理事件，不默认终结 episode；
- EXIT 后若主假说未失效，必须生成 reentry obligation；
- geometry 变化必须显式 `VALID / REBUILT / INVALIDATED`；
- lot、费用、滑点、保证金、开放风险与成交全部由确定性内核复算；
- 研究 Agent 无法授予 paper/live 权限。

本节是从 V3 继承的连续组合目标合同。当前 V3.1 研究 cycle 不执行 portfolio mutation，也不会仅因研究选择了 EXIT 就自动生成和持久化 reentry obligation；只有 portfolio reducer、event store、reentry 状态机和跨周期恢复均接线并通过验收后，才可声称该能力已经实现。

---

## 15. Agent 与确定性系统的边界

### 15.1 Agent 负责

- 解释信息主体、受众和可能行为，但保留竞争解释；
- 请求具有区分价值的新数据；
- 提出、拆分、合并、修订或淘汰假说；
- 解释图与概率云变化；
- 构造严格条件路径；
- 比较合法动作、机会成本和下一观察；
- 发现既有原语无法解释的残差方向。

完整动作集合的身份与尺度不由 Agent 创造：确定性系统先从 portfolio truth、lot/role 和冻结有限网格枚举全部 legal action keys；Agent 只为每个 key 提供 thesis、path、evidence、风险、机会成本和下一观察语义，并在封存 evaluation 后比较。Agent 不得删减合法候选全集、增添未注册动作或自行决定计算型尺度。

### 15.2 Agent 不负责

- 伪造、修改或补齐原始事实；
- 计算 lot、PnL、费用、风险、相关统计或物理摘要；
- 任意覆写 hypothesis support；
- 在 proposal 阶段选择动作；
- 把未校准判断转换为概率、EV 或仓位；
- 修改 checkpoint、事件链、权限或历史；
- 下单或访问账户、凭据和资金。

### 15.3 单 Strategy Agent 两阶段协议

```text
阶段 A：PROPOSAL
  信息解释 + 图变化提议 + 假说/路径 + 为确定性 legal keys 填充完整候选语义
  禁止 selected

确定性中间层
  验证点时、来源、图类型、概率模式、事实绑定、动作数量、成本和风险
  封存 evaluation

阶段 B：SELECTION
  只读取已封存 proposal 与 evaluation
  输出选择、理由、机会成本、失败条件与下一观察
```

任何 selected-first、模板补理由或 accept 后首次语义检查均为失败关闭。

---

## 16. 四层系统设计与职责

V3.1 只采用四层，不新增平行平台：

| 层 | 唯一职责 | 主要所有权 | 禁止 |
|---|---|---|---|
| Domain | 类型、不变量、状态转移与纯计算 | 信息本体、动态图、概率云、假说、路径、仓位/风险规则 | 文件、网络、CLI、模型调用 |
| Application | 编排一个完整 cycle/use case | proposal→evaluation→selection→completion，ports | 重新实现领域规则 |
| Infrastructure | 外部适配器 | 数据源、正文存储、事件存储、Agent mailbox/transport | 决策与授权逻辑 |
| Presentation | 人机入口与报告 | CLI/status/report、明确权限和证据等级 | 直接写领域状态 |

显式 ports：`MarketDataPort / InformationSourcePort / AgentDeliberationPort / ResearchStorePort / ClockPort / DigestPort`。transport 只是 `AgentDeliberationPort` 的适配器，可替换、可失败关闭，不拥有业务状态。

### 16.1 目标事件流

```text
Presentation request
→ Application checks current authority and creates cycle input plan
→ Infrastructure collects point-in-time artifacts
→ Domain validates facts, builds graph delta and admissible proposal space
→ Agent proposal delivered durably
→ Domain/Application preaccept validation and sealed evaluation
→ Agent selection delivered durably
→ Domain applies reducers and deterministic portfolio/risk computation
→ Infrastructure appends receipts/artifacts
→ Application verifies completion and advances checkpoint
→ Presentation renders evidence-bound report
```

每个写入只有一个 owner；失败发生在 accept 前则不推进，accepted 后只恢复确定性尾部。

---

## 17. 实验、校准与证伪

### 17.1 分层验证

必须分别验证：

1. 信息分类是否完整、点时、可追溯；
2. 数据与修订是否可复算；
3. 相关性/图变化是否稳定且不越权因果；
4. 假说是否新增区分力而非改写；
5. 概率模式是否合规、校准是否真实；
6. 路径是否在未来窗口产生可观察区分；
7. Agent 动作是否优于 deterministic shadow 或基准；
8. 收益、成本、回撤、重入和 path capture 是否改善；
9. 长窗口、换 regime 和换资产是否保持或失效。

### 17.2 必须使用的对照

- frozen policy baseline；
- deterministic shadow；
- no-information-layer ablation；
- no-dynamic-graph ablation；
- no-probability-cloud ablation；
- hold/flat/简单规则基准；
- 相同 PIT、成本、风险、窗口和可行动作集合。

### 17.3 评价

下列是新实验的预注册评价目标。未生成对应前瞻 outcome 与可复算 receipt 的指标一律为 UNKNOWN，不得用本地结构测试代替：

- 未校准 plausibility：评价区分义务、反证命中、路径分辨率和信息价值，不使用 Brier/log score；
- calibrated forecast：目标上使用 proper scoring、calibration curve、sharpness、coverage 和 conditional predictive ability；当前本地实现仅覆盖 Brier/log score、固定 classwise ECE 和有限漂移检查，不具备 sharpness 或 conditional predictive ability 结论；
- 行为：机会成本、regret、成本后收益、最大回撤、尾部风险、reentry delay 与 path capture 分开；
- failure attribution：`DATA / INFORMATION / ASSOCIATION / GRAPH / HYPOTHESIS / PROBABILITY / PATH / AGENT / RISK / EXECUTION / ORCHESTRATION / EXTERNAL`。

任何一次失败不得通过回写理论、缩短窗口、读取未来结果或更换评分规则修复。

截至本文日期，尚无新的 V3.1 前瞻周期实验结果。当前本地测试、合成 fixture、Pearson receipt、calibration receipt、accepted state 和恢复验证只能证明合同与重放一致性，不能证明信息层增量、关联稳定性、预测有效性、Agent 动作优越性、成本后收益改善或跨 regime 稳定性。

---

## 18. 截至本版本永久禁止的已知错误路径

1. 固定 target 全平并永久离场；
2. 每轮重写 persistent state；
3. 无 CORE/TACTICAL、无 reentry；
4. WAIT 无机会成本和复核；
5. 固定乐观成交与事后价格；
6. 非互斥路径强制合计 100%；
7. 重复依赖证据多次计权；
8. selected-first 或事后补理由；
9. 模板文本冒充路径区分；
10. Agent 任意改 support、lot、风险或权限；
11. OI 单独解释多空开平，低成交量解释卖压；
12. 单帧订单簿解释严格韧性；
13. 缺失 liquidation/funding/新闻正文补零或补方向；
14. 周期正负票数相加制造一致性；
15. contributor sign 无 numeric fact_ref；
16. 标题或转载数量冒充事件影响；
17. 公开发言冒充真实意图或操盘事实；
18. 相关性、Granger 或文本共现冒充结构因果；
19. 序数支持或心理猜测计算 EV；
20. accept 后首次做语义真实性检查；
21. accepted 后重新调用 Agent 改判断；
22. 用聊天摘要代替 durable state；
23. desired control state 冒充 actual state；
24. one-line heartbeat 冒充完整 cycle；
25. 恢复旧 v1.3/v1.4/E0/E0B chronology；
26. 让 transport、多 Agent 或新平台取代理论实践；
27. 用 PASS、1/4 周期或本地 receipt 宣称市场有效、盈利或就绪。
28. 调用者修改数据枚举、revision、质量、推论准入或统计计数后只重签摘要；
29. 用旧信息修订中的事实、来源或推论绕过最新修订；
30. 用来源类型、官方标签、自哈希或占位 receipt 解锁 `VERIFIED_PRIMARY`；
31. 概率云把自身、假说、预期、路径、动作或 evaluation 当作同轮前置证据；
32. 用占位十六进制摘要、调用者自报评分或重叠样本解锁 calibration/EV；
33. 概率云换成员、换事件空间或换模式时伪装成普通 update；
34. 假说或预期引用未准入、已 supersede、未来可得或不可推论的证据；
35. 到期预期仍保持 OPEN，或 terminal 假说继续拥有开放预期；
36. 路径为 `FALSE/UNKNOWN` 时仍用正向图边支持非 WAIT 动作；
37. 用 `OPPOSES`、不相容或缺失的图边制造正向可达性；
38. proposal 用任意 Agent 摘要、错 input boundary 或错 candidate binding 自我授权；
39. 金融 evaluator 接受调用者提交的费用、风险、保证金、可行性或 EV 作为真值；
40. 没有冻结 payoff matrix 时计算数值 regret，或把 ordinal plausibility 代入效用；
41. 任意自签 JSON 冒充 inputs/proposal/evaluation/selection/accepted/completion 正式对象；
42. checkpoint 只记录一个总摘要，不记录数据、图、假说、预期、概率云和迁移状态头；
43. `resume_allowed=false` 后继续推进，或失败文档未物理绑定仍宣称 failure-close；
44. 把历史有效期早于采集时间误判为未来信息；知识时钟由 `available_at` 控制，validity 只描述对象适用期；
45. 内容寻址的独立 snapshot 固定写 `revision=1`，却暗示它是同一对象的跨周期修订。
46. 信息或数据对象暂时不在当前推论快照后，以 `revision=1 / predecessor=None` 复活并绕过既有修订头；
47. 假说或预期把自身作为父对象，或用 `A→B→A` 环制造伪谱系；
48. 概率云 repartition 更换成员、事件空间或模式时，让 `available_at` 早于 prior cloud；
49. 六份正式文档互相重签后，把原始 `WAIT` 选择改成 `OPEN/ADD` 并伪造 terminal；
50. 关联收据使用调用者自报数值或任意 datum 摘要，而没有逐对绑定当轮准入的 PIT 数值、`as_of` 和 `available_at`；
51. checkpoint 摘要可核对但缺少可重建的 typed assembly bundle 时，声称已具备完整跨进程或跨窗口语义恢复；
52. 用整个 dataset/event 的聚合摘要作为语义证据，洗白其中不可推论的数据、心理猜想或上下文；
53. 跨周期只继承 evidence ID，不绑定 cumulative registry 的最新 revision digest，使已降级、已 supersede 或不可推论的新版本仍被旧假说使用；
54. 把 actor、role、audience 等上下文 ID 或 intent/behavior hypothesis 与 observed fact 合并为同一证据等级，并直接进入 empirical/calibrated probability；
55. 新合同要求 exact evidence ref→digest 后，让 legacy adapter 继续只提交 evidence ID，或为通过回归而放宽 Domain schema、填固定伪摘要、静默回填旧 run。

可机械检测的违规必须立即使 cycle failure-close，并写入类型化原因。主体真实意图、因果越权、同义叙事、错误心理解释等语义性违规无法由当前确定性代码保证自动发现；一旦在独立审查或结果评价中发现，对应 artifact 和依赖它的 cycle 必须失效并保留事件记录。不得把本清单存在解释为上述项目都已被代码机械关闭。

### 18.1 已复现问题、纠正与剩余边界

下表把第 1–55 项合并为根因级记录；“局部关闭”只表示冻结本地输入下已有拒绝回归，不表示真实市场语义、未知缺陷或目标能力已经完成。完整模块、调用链和逐项证据见 `V3_1_THEORY_AND_SYSTEM_DESIGN_AUDIT_2026-08-06.md`。

| 问题情况 | 失败原因 | V3.1 纠正 | 当前证据边界 |
|---|---|---|---|
| 固定止盈全平后错失延续 | target 被当成永久退出，仓位无角色与重入义务 | CORE/TACTICAL、geometry、reentry 和完整动作域分离 | 理论已纠正；V3.1 action comparison 已实现，portfolio mutation/reentry 应用仍未接线 |
| 合成链与公开 pilot 语义分叉 | 两套 snapshot、情绪、假说和动作 schema | 统一 InformationEvent、PIT Datum、图、概率、路径和动作 Domain 合同；旧链 legacy 隔离 | snapshot 映射与本地 coordinator 已验证；fresh prospective composition 未完成 |
| 情绪把低量解释为卖压、周期票数相加、OI 无前序，或情绪快照绕过 PIT 数据门 | 代理越权、方向符号与事实不绑定、缺失被强解释、第二数据通道 | 十二轴并列状态、显式十→十二轴迁移、dependency/coverage/conflict、UNKNOWN、prior change，以及 contributor→PIT datum 的 exact ref→digest/语义绑定 | state/change 已进入六阶段与 checkpoint；两项无直接数据轴固定 UNKNOWN；原生十二轴真实来源与图投影仍待资格验证 |
| 撤权后历史配置仍可启动 | controller 只看冻结副本，不核对 current authority | 所有 start 在来源访问与 run 创建前核对当前 authority、operation、run、template 与 receipt | 当前 suspended authority 的旧入口拒绝回归已通过 |
| 资金费、公告或修订发生后倒填决策时点 | observed/effective/available/as_of 混用 | 五时钟、vintage、append-only revision 与 `available_at` 独占知识时钟 | 本地 PIT/修订回归已通过；真实来源时钟质量待 dry run |
| 官方标签、自哈希或占位 receipt 自认证来源 | 文件一致性被误当成外部来源真实性 | LOCAL/SOURCE_ATTESTED/EXTERNALLY_VERIFIED 分级和 acquisition receipt；native 无 capture 默认降权 | 本地适配器失败关闭已验证；内容真实性仍不可由系统自动证明 |
| 低质量数据越权进入方向判断 | 单一 coverage 或字段存在被当推论资格 | `hypothesis_admissible` 与 `inference_admissible` 分离；后者才可进入关联、概率、路径和动作 | 本地全链引用门已验证；质量标签现实正确性未知 |
| dataset/event 聚合摘要洗白成员 | composite hash 隐藏了成员的认识论类型和准入差异 | 聚合摘要只作 input boundary；语义证据必须是带精确 digest 的 typed member | 本地绕过回归必须逐层覆盖；集合完整性不等于成员可推论 |
| 信息事实、上下文与心理猜想同级 | actor/role/audience/intent/behavior 共用一个 ref 白名单 | 拆分 observed evidence、hypothesis seed 与 context；心理猜想最多进入候选假说或 subjective mode | empirical/calibrated 模式不得引用 intent/behavior；现实心理解释仍未知 |
| 信息/数据 ID 消失后以 revision 1 复活 | 只保存当轮 active 快照，未保存累计身份头 | 永久累计 revision registry，inputs/accepted/completion/checkpoint 跨轮绑定 | 消失—复活和错 predecessor 拒绝回归已通过 |
| 证据 ID 跨周期继承后忽略新 revision | active evidence 只有 ref，没有 exact digest/latest-head 重核 | active/result evidence 保存 ref→digest，并与 cumulative latest head 和准入状态逐轮比较 | 旧版本仅供审计；任何降级或 supersede 必须撤证、修订或关闭依赖状态 |
| legacy synthetic fixture 在 exact evidence schema 下全量中断 | adapter 仍只发送 evidence ID，未发送 hypothesis/delta/expectation 的 fact digest binding | Infrastructure 从当轮 snapshot fact 计算 canonical digest；修订时继承旧绑定并追加新绑定；Domain 严格 schema 不变，旧 run 不回填 | 首轮全量回归复现 18 项同源中断；最小 adapter 修复后相关 24 项及全范围 426 项通过 |
| 旧 revision、任意 enum 或准入计数重签后通过 | 只验摘要，不从严格字段重建 | 从文档重建 typed 对象、重算质量/准入/registry，并与声明精确比较 | 本地篡改回归已通过 |
| 假说/预期自父或环状谱系 | parent 只验存在，不验时序和有向无环 | parent 必须先存在，非递归拓扑检查 self-parent 与任意 cycle | 局部 reducer 回归已通过；语义同义改写仍需审查 |
| 概率云自循环、静默换成员或时间回退 | 同轮后层对象可当证据，repartition 冒充 update | 低层证据白名单、update/repartition 两类 receipt、previous/current head 与单调 `available_at` | 基本模式和迁移回归已通过；通用 promotion/credal solver 未实现 |
| 伪造校准摘要或自报 score 解锁 EV | 未冻结 forecast/outcome/split，未复算评分 | 三组不重叠样本、事件合同、Brier/log/ECE、baseline/drift/deployment 全部重放 | 仅常数分类本地基线；无真实校准或模型增量结论 |
| 关联收据内嵌任意数字 | 估计器结果未绑定原始 PIT observation | Pearson/Fisher receipt 逐对绑定准入 datum digest、值、as_of、available_at | 单一基线局部关闭；prospective 预注册、高级时变/尾部/因果与 multiplicity 未实现 |
| FALSE/UNKNOWN 路径或 OPPOSES 边仍支撑行动 | 路径文本、图可达与候选动作没有精确语义绑定 | 三值谓词实际求值、相邻层兼容矩阵、exact action implication 与 selectable gate | 单步路径局部关闭；偏序/循环执行与旧路径 monitor 未实现 |
| Agent 先选后解释或用任意摘要自授权 | inputs、candidate 全集和 selection 顺序不封存 | exact inputs→proposal(no selection)→完整 evaluation→post-seal selection；计算状态由 reducer 独占 | 本地两阶段合同通过；fresh 当前 Codex durable delivery 待资格验证 |
| 调用者伪造费用、风险、保证金、EV/regret | 金融字段被当输入真值 | 从原子 portfolio/market/risk 输入复算；无冻结 payoff matrix 时 EV/regret 为 UNKNOWN | 成本/风险/可行性局部关闭；行为收益尚未评价 |
| 六文档互相重签，把 WAIT 改成 OPEN_LONG，或新窗口只能依赖聊天/内存恢复 | 摘要链内部自洽却没有外部语义根；原始构造输入未耐久化 | 严格白名单 typed assembly bundle、内容寻址、六文档全链重建、store semantic admission 与逐周期 checkpoint bundle 绑定 | 全新解释器仅凭 durable bundle 的恢复与 tamper/歧义失败关闭已通过；这不证明真实外部 transport 长时可靠 |
| 失败后继续推进或聊天补状态 | checkpoint/failure/resume 语义松散 | 固定 transition matrix、CAS、物理 failure document、`resume_allowed=false` 永久关闭 | 本地 chronology 已验证；外部长时 transport 可靠性未知 |

不存在一种有限测试能够证明“未知问题为零”。V3.1 的完成标准因此是：所有已登记且可复现的问题有根因、修复与回归；所有未实现目标有显式资格门；所有真实市场和外部语义主张保持 `UNKNOWN_NOT_EVALUATED`。

---

## 19. 学术基础与使用边界

下列原始研究只提供机制与建模灵感，不构成某次市场方向的证据：

| 研究 | V3.1 吸收内容 | 不允许外推 |
|---|---|---|
| [Grossman & Stiglitz (1980), Informationally Efficient Markets](https://www.aeaweb.org/aer/top20/70.3.393-408.pdf) | 信息有成本，价格不会无条件包含全部信息 | 不能由“市场有效/无效”直接预测方向 |
| [Kyle (1985), Continuous Auctions and Insider Trading](https://doi.org/10.2307/1913210) | 信息交易、噪声、深度与价格冲击的机制分层 | 不能从公开流识别具体知情者 |
| [Glosten & Milgrom (1985), Bid, Ask and Transaction Prices](https://business.columbia.edu/faculty/research/bid-ask-and-transaction-prices-specialist-market-heterogeneously-informed-traders) | 逆向选择与价差、成交价格之间的关系 | specialist 模型不是所有市场的事实 |
| [Brunnermeier & Pedersen (2009), Market Liquidity and Funding Liquidity](https://academic.oup.com/rfs/article-abstract/22/6/2201/1592184) | 融资约束与市场流动性的反馈/螺旋 | 不能把一次价差扩大自动称为流动性螺旋 |
| [Morris & Shin (2002), Social Value of Public Information](https://www.aeaweb.org/articles?id=10.1257/000282802762024610) | 公共信号可能协调受众并压过私人信息 | 不能假设所有受众同质或福利结论普适 |
| [Kamenica & Gentzkow (2011), Bayesian Persuasion](https://www.aeaweb.org/articles?id=10.1257/aer.101.6.2590) | 发送者、信号设计、受众行动与激励分离 | 不能把策略性表达等同撒谎或真实动机 |
| [Gentzkow & Shapiro (2006), Media Bias and Reputation](https://www.nber.org/papers/w11664) | 来源声誉、受众先验和竞争来源影响信息解释 | 不能给任何媒体预置方向性偏差 |
| [Gürkaynak, Sack & Swanson (2005), Do Actions Speak Louder Than Words?](http://www.ijcb.org/journal/ijcb05q2a2.pdf) | 当前政策动作与未来政策路径分开 | 美国货币政策事件窗不能直接泛化至所有发言 |
| [Jarociński & Karadi (2020), Monetary Policy vs Information Shocks](https://www.aeaweb.org/articles?id=10.1257/mac.20180090) | 公告同时携带政策冲击与基本面信息，需竞争分解 | 识别符号和高频窗不是通用实时分类器 |
| [Nakamura & Steinsson (2018), The Information Effect](https://www.nber.org/papers/w19260) | 央行公告会改变对政策与基本面的共同信念 | 不能忽略其事件窗和识别假设 |
| [Pástor & Veronesi (2012), Government Policy Uncertainty](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2012.01746.x) | 政策状态、不确定性、经济环境与价格反应分开 | 政治发言不等于政策已实施 |
| [Barberis, Shleifer & Vishny (1998), Investor Sentiment](https://scholar.harvard.edu/files/shleifer/files/model_invest_sent.pdf) | 保守更新与代表性启发可形成欠反应/过度反应候选 | 模型心理机制不能读出个体真实心理 |
| [Hong & Stein (1999), Underreaction, Momentum and Overreaction](https://onlinelibrary.wiley.com/doi/10.1111/0022-1082.00184) | 异质群体、渐进扩散与反馈交易路径 | 模型代理人类型不等于可观察身份 |
| [Tetlock (2007), Media and Investor Sentiment](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2007.01232.x) | 文本悲观、成交与短期价格压力可作待检验关系 | 历史报刊结果不能直接移植到币市或单条消息 |
| [Da, Engelberg & Gao (2011), In Search of Attention](https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2011.01679.x) | 搜索数据可作为零售注意力代理，并与新闻区分 | 搜索量不是购买意图或统一情绪真值 |
| [Engle (2002), Dynamic Conditional Correlation](https://doi.org/10.1198/073500102288618487) | 时变条件相关及其版本化估计 | DCC 仍是模型依赖相关，不是因果 |
| [Hamilton (1989), Regime Switching](https://doi.org/10.2307/1912559) | 潜在 regime 与转移概率 | 离散状态设定和后验不是可观察事实 |
| [Diebold & Yilmaz (2012), Directional Spillovers](https://doi.org/10.1016/j.ijforecast.2011.02.006) | 方向性预测连接与网络变化 | 方差分解不是结构因果网络 |
| [Acemoglu, Ozdaglar & Tahbaz-Salehi (2015), Financial Networks](https://www.aeaweb.org/articles?id=10.1257/aer.20130456) | 网络在小/大冲击下可能有不同稳定性 | 银行网络模型不能直接生成币价信号 |
| [Granger (1969), Predictive Causal Relations](https://doi.org/10.2307/1912791) | 时间领先与预测增量的正式检验 | 名称中的 causality 不等于结构因果 |
| [Hoeting et al. (1999), Bayesian Model Averaging](https://doi.org/10.1214/ss/1009212519) | 显式保留模型不确定性和 ensemble dispersion | 未校准模型不能通过平均变成可靠概率 |
| [Gneiting & Raftery (2007), Proper Scoring Rules](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf) | 概率评价必须用适当评分规则 | proper score 不能修复标签或 PIT 错误 |
| [Giacomini & White (2006), Conditional Predictive Ability](https://doi.org/10.1111/j.1468-0262.2006.00718.x) | 在可能错设下做条件样本外比较 | 单窗口显著不证明长期稳定 |
| [Dawid (1982), The Well-Calibrated Bayesian](https://www.tandfonline.com/doi/abs/10.1080/01621459.1982.10477856) | 概率主张必须接受长期校准检查 | 主观一致性不等于经验校准 |
| [Manski (2008), Decisions With Partial Knowledge](https://www.nber.org/papers/w14396) | 部分识别和歧义下采用稳健/支配/部分处方 | 无分布时不能伪造唯一 EV 最优动作 |
| [Makarov & Schoar (2020), Crypto Arbitrage](https://www.fmg.ac.uk/publications/academic-journals/trading-and-arbitrage-cryptocurrency-markets) | 币市跨场分割、套利资本与共同/特异流 | 单一交易所价格不能代表无摩擦全球价格 |
| [Liu & Tsyvinski (2021), Risks and Returns of Cryptocurrency](https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024) | 币市特有网络、动量和注意力候选因子 | 历史因子关系不能当永久参数或因果 |

---

## 20. 从审查稿到新实验的唯一合法路线

1. 用户审阅并冻结 V3.1，或明确指出需修改内容；
2. 先冻结实现前基线，不改旧实验和评分；（当前基线已冻结）
3. 只在现有四层核心内实现信息、数据、图、概率云、路径和动作合同；（已完成实现子集，目标合同仍有本文件明确列出的缺口）
4. 通过结构、领域、恢复、PIT、权限和失败原子性验证；（已完成局部验证，新实验阻塞项尚未清零）
5. 用本地合成/固定 fixture 验证已实现合同，不作市场能力主张；（已覆盖当前实现子集，不等于全部目标合同完成）
6. 为唯一全新、不可执行、未见未来 outcome 的周期实验生成 manifest、input plan、checkpoint 和停止条件；
7. 用户明确授权后才启动；旧 s3、v1.3、v1.4、E0/E0B 永不恢复；
8. 每个 cycle 完成完整六对象/receipt/状态验证后，才进入下一个 cycle；
9. 任何数据、Agent、transport、上下文、权限或原子性异常立即 failure-close；
10. 只有足够未来窗口完成后，才讨论校准、预测增量或下一阶段。

截至 2026-08-06，步骤 2 已完成，步骤 3–5 仅对当前实现子集成立；数据质量两级准入、PIT 数值绑定的 Pearson 关联基线、十二轴显式情绪迁移/六阶段接线，以及可跨进程重建的 typed assembly bundle 已局部机械关闭。但十二轴原生来源与图投影、路径跨周期 monitor、一般概率/模式升级、实际 multiplicity control、独立因果识别、payoff/EV 和 portfolio/reentry 应用等阻塞项仍未完成。步骤 1 也仍等待用户审阅/冻结。因此本文件的正确状态是：`THEORY_CANDIDATE / PARTIALLY_IMPLEMENTED / ACCEPTANCE_BLOCKERS_OPEN / NO_NEW_EXPERIMENT / NON_EXECUTABLE`。

---

## 21. 当前实现对应、阻塞项与未验证边界

### 21.1 `MECHANICALLY_IMPLEMENTED` 的局部能力

当前四层核心已对冻结输入实现并局部验证：PIT 数据对象与 append-only revision、信息/数据累计修订登记册、质量两级准入、当前注册图类型子集与相邻层可达性、PIT 数值绑定的 Pearson 关联收据、假说/预期 reducer、概率云基本模式边界与 update/repartition 收据、单步三值路径、完整有限 legal action keys、成本/风险/保证金/可行性复算、两阶段 Agent 合同、十二轴显式情绪迁移与 exact PIT contributor 绑定、耐久事件链、跨周期状态头、内容寻址 typed assembly bundle、全新解释器语义重放、幂等恢复和可机械异常的物理 failure-close。六文档或聊天本身仍不是恢复权威；恢复必须同时拥有 checkpoint 所绑定的完整 bundle。

### 21.2 `CONTRACT_OR_LOCAL_BASELINE_ONLY`

信息角色与事件对象、通用 association revision、Pearson/Fisher 基线与不重叠窗口变化、常数分类模型的本地 calibration replay、主观/模型条件/市场隐含概率容器和 Agent 语义提案都属于合同或本地基线。它们证明结构、摘要和重放一致性，不证明来源真实性、统计识别、语义正确、市场预测能力或 Agent 增量。

### 21.3 `TARGET_NOT_IMPLEMENTED` 或新实验阻塞项

- 实际 multiplicity control 和独立因果识别验证；
- DCC、Granger、tail dependence、spillover、event-window 等高级估计器；
- 一般 credal set 求解、模型 ensemble/posterior 与 mode-promotion 状态机；
- 十二轴原生信息/数据来源覆盖及其显式 graph state projection；
- 偏序/循环路径执行器和对旧路径 future falsifier 的跨周期 monitor receipt；
- 冻结 path payoff matrix、效用、情景成本、numeric EV/regret；
- 研究选择后的 portfolio mutation、geometry/reentry reducer 应用与跨周期证明。

### 21.4 `UNKNOWN_NOT_EVALUATED`

真实公开信息采集的覆盖与语义质量、真实 Agent 是否提供新增区分力、关联与假说是否具有未来预测增量、概率是否在真实分布变化下保持校准、动作是否改善成本后收益与风险、外部数据/transport 长时可靠性、跨资产与跨 regime 泛化均未评价。

当前没有运行中的 V3.1 experiment、paper/live 连接、账户读取、订单或资金权限。旧 s3 保持冻结的 `1/4` 原始基线，不能续跑或改写；任何新实验必须使用全新 run、冻结的 V3.1 SHA、独立授权收据和未见未来窗口。
