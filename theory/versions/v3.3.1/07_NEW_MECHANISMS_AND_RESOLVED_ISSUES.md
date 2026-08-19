# V3.3.1 新机制与已知问题解决矩阵

版本：`3.3.1-agent-first-trader-candidate.1`

状态：`FROZEN_VERSION_CANDIDATE_CHANGE_MAP / MAINTENANCE_ONLY / NON_AUTHORITY`

Owner：V3.3.1 新机制、已知冲突的理论处理、实现边界与前瞻证据边界。

本文只是索引。当前候选规则以 README 和 01–05 为准；当前共享路由仍由 `theory/CURRENT.md` 决定。

## 1. 状态语义

| 状态 | 含义 |
|---|---|
| `RESOLVED_IN_CANDIDATE_THEORY` | V3.3.1 候选已给出唯一 owner 和无冲突语义 |
| `PENDING_INTEGRATOR_ROUTING` | 候选未成为共享当前入口 |
| `PENDING_RUNTIME_MIGRATION` | 理论已定义，新 Agent-first 主链尚未实现 |
| `PENDING_FORWARD_EVIDENCE` | 运行即使完成，也没有新身份前瞻 Outcome/Review |
| `BLOCKED_BY_AUTHORITY` | 需要用户独立授权的外部数据、账户或执行 |
| `RETAINED_UNKNOWN` | 证据尚不足，不得伪造已知 |

“候选理论已解决”只表示文档中的设计冲突已被消除，不表示 runtime 已完成、Agent 已高质量、预测有效或仓位能够盈利。

## 2. 核心问题解决矩阵

| 已知问题 | V3.3.1 处理 | Owner | 状态 |
|---|---|---|---|
| Agent 只是候选生成者 | Agent 独占市场、假说、最终动作、仓位和复盘 | README/01–04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| deterministic selector 选 lead/action | 删除系统语义选择权；并列/无解仍由 Agent 表达 | 03/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| allocator 决定仓位 | 系统只计算；Agent 选参考数量、tranche、stop/targets | 02/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| proposal schema 拒绝可读决策 | 内容层只检查可读非空；其他缺漏封存并继续 | 04/05 | `RESOLVED_IN_CANDIDATE_THEORY` |
| trigger 对象/字符串形状冲突 | trigger 只是可读可观测语义，序列化不作终态门 | 03/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| lifecycle/action 词表成为资格门 | 词汇是思考参考，Agent 可创建新语言 | 02–04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 缺漏导致无 Outcome/Review | 封存缺漏/歧义作为能力证据，按冻结时钟继续 | 04/05 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 五工件与新原文对象冲突 | AgentDecisionBody 内嵌 HypothesisRecord，AgentReviewBody 内嵌 Review，BehaviorPlan 原样引用 | README/03/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| BehaviorPlan 被系统 planner 改写 | 保留正式五工件身份，只允许 Agent 原文引用/复制 | README/02–04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 索引反向成为决策真值 | DecisionIndex 可丢弃、可缺失、只指 source spans | README/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| SystemEnvelope 混入市场结论 | 外层只有身份、时间、摘要、权限、writer | README/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 风险模块过度否决 | 五硬边界外的问题都转为质量证据 | 05 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 非价格数据能力夸大 | 当前只承认实际 price raw，其他继续 UNKNOWN，不扩源 | 01/05 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 市场方法被系统 reducer 选择 | 系统提供测量，Agent 选方法、regime 和解释 | 01 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 初始/动态仓位仍是固定档位 | Agent 用失效几何、路径、压力和机会成本自己选数量/分批 | 02 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 高收益缺少落袋与 runner 权衡 | 必须作为 Agent 质量问题比较全持有/部分+runner/全平 | 02 | 理论完成，`PENDING_FORWARD_EVIDENCE` |
| 复盘由系统指标替代 | Outcome 只记事实，AgentReviewBody 独占判断/学习 | 03/04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| 学习与冻结检查混合 | Agent 提 learning candidate，integrator 选是否改版，系统只验字节 | 04 | `RESOLVED_IN_CANDIDATE_THEORY` |
| base+overlay 可能产生两套规则 | V3.3.1 是自包含 manifest 包，运行时不叠加 V3.3.0 | README | `RESOLVED_IN_CANDIDATE_THEORY` |
| 旧 run 与新语义混用 | 理论/决策语义变化必须全新 run，旧 run 只读 | README/04/06 | `RESOLVED_IN_CANDIDATE_THEORY` |

## 3. 新机制定义索引

### M22 Agent-exclusive Decision Ownership

Market cognition、hypotheses、final reference action、entry/stop/targets/position 和 review judgement 只有一个 Agent owner。系统不再是隐式 co-decider。

### M23 Authoritative AgentDecisionBody

`HypothesisRecord.AgentDecisionBody` 以收到的可读原文字节封存，包括市场—假说—动作—仓位全部决策语义。

### M24 Verbatim BehaviorPlan

`BehaviorPlan` 保留为正式工件，但只原样引用/复制 Agent 自选动作与仓位。系统不生成第二个计划。

### M25 Safety-only SystemEnvelope

外层绑定身份、PIT、deadline、摘要、权限和 writer，不包含市场决策真值。

### M26 Readable Decision Admission

内容层只检查约定 encoding 可读且非空。格式、词汇、字段、对象形状、顺序、歧义和缺漏不作终态门。

### M27 Missingness-as-Capability-Evidence

缺失 stop、target、lead、机会成本或仓位不由系统补齐；原样封存，用 Outcome 和 Agent Review 评价它是否损害决策。

### M28 Disposable Source-span Index

DecisionIndex/ReviewIndex 只存原文 spans、not-found 或 ambiguous。索引失败不影响五工件，不可反向重建决策。

### M29 Outcome Continues Through Semantic Gaps

基本 Outcome 时钟在 request/InputSnapshot 冻结，不依赖完美 proposal 或索引。可读决策使语义缺口变成可评价证据。

### M30 Agent-authored Review

`Review.AgentReviewBody` 由 Agent 自主判断市场、假说、动作、仓位、机会成本、缺漏和学习。Outcome metric 不自动成为复盘结论。

### M31 Learning/Freeze Separation

AgentReviewBody 产生 learning candidates；用户/integrator 决定是否新建 revision；manifest 只验字节身份。学习不自动改当前理论。

### M32 Five Hard Boundaries Only

五类硬边界：身份/raw/核心覆盖；PIT/未来/迟到；单 writer/原文不可变；可读非空；外部权限/副作用。其余全部是质量证据。

### M33 Agent-owned Calculation Adoption

系统可计算，Agent 选问题、参数、是否采用与如何解释。工具输出不能自动成为 regime/action/position。

### M34 Self-contained V3.3.1 Package

README 与 01–07 由单一 manifest 绑定，运行时不叠加前身。维护篇 06/07 验证身份但不默认注入 Agent 热路径。

## 4. 从候选到新前瞻身份

### Phase A：候选文档与 manifest

完成条件：

- V3.3.0 字节未改；
- V3.3.1 README 和七 owner 完整、语义一致；
- 五工件、AgentDecisionBody、BehaviorPlan、AgentReviewBody 没有新工件歧义；
- manifest 固定顺序、路径、大小和 SHA-256；
- 只进行无网络结构验证，不运行市场实验。

### Phase B：新 Agent-first runtime

完成条件：

- 唯一 loader 验证 V3.3.1 manifest，不读 V3.3.0 规则补丁；
- `HypothesisRecord.AgentDecisionBody` 是唯一决策原文；
- `BehaviorPlan` 只原样引用/复制，不 planner/allocator；
- `Review.AgentReviewBody` 是唯一复盘判断；
- proposal schema/normalizer/tie-break 不再以非安全问题拒绝决策；
- 五硬边界没有被放松；
- 旧 V3.3.0 route 只读且不双写。

### Phase C：新身份前瞻评价

需要用户/integrator 另行决定。完成前：

- 冻结 theory/implementation/Agent context/Outcome/run 身份；
- 旧 run 不续跑、不回填、不混入样本；
- 使用真实合法 PIT 公开数据；
- 每个可读决策都继续 Outcome/Review，缺漏不被清除；
- 从完整终态工件评价动态性、自主性、全面性、效率、预测增量和仓位效果。

## 5. 候选理论验收

| 检查 | V3.3.1 候选应满足 | 不能证明 |
|---|---|---|
| 自包含包 | 不依赖 base overlay | runtime 已迁移 |
| 五工件 | 不新增 AgentDecision/AgentReview 工件 | 工程已稳定 |
| Agent 唯一 owner | 01–04 权责一致 | Agent 实际质量 |
| 格式非终态门 | 04/05 无例外冲突 | 前瞻链已运行 |
| 五硬边界 | 身份/PIT/写入/可读/权限完整 | 外部执行已授权 |
| 非价格 UNKNOWN | 不扩源、不伪造 | 价格-only 有预测增量 |
| 原文与索引分开 | 索引可丢弃、不反向授权 | 自动抽取准确 |
| 学习/冻结分开 | 新版需独立 integrator 决定 | 学习结论有效 |
| manifest 摘要 | 字节大小/顺序/SHA 精确 | 市场有效/盈利 |

## 6. 仍保持 UNKNOWN

- Agent-first runtime 是否能按当前五工件完整运行；
- Agent 原文在无严格 schema 时的完整性、动态性与稳定性；
- 价格-only 市场认知相对简单 baselines 是否有增量；
- 哪些假说/路径方法真正改善决策；
- 哪种初始仓位、stop/target、partial+runner 和 reentry 管理有更好前瞻效果；
- cold/delta 是否足够快，长期记忆是否提高而不污染判断；
- 公开参考价格效果与未来真实执行成本的差异；
- 任何预测或仓位组合能否产生成本后正价值。

这些问题不再由理论文字或格式资格门解决，只能由未来独立冻结的实现与前瞻 Outcome/Agent Review 变成有界已知。
