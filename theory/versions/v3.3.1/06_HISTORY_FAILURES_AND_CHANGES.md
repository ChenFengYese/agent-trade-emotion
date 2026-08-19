# 历史复盘、失败与 V3.3.1 变更

版本：`3.3.1-agent-first-trader-candidate.1`

状态：`FROZEN_VERSION_CANDIDATE_HISTORY / MAINTENANCE_ONLY / NON_AUTHORITY`

Owner：版本演进、重复失败、V3.3.0→V3.3.1 修正与保留/回滚边界。

本文不定义当前市场、假说、仓位、执行或风险规则。当前候选规则只由同目录 README 和 01–05 定义。

## 1. 当前结论

V3.3.0 正确地把市场认知、动态仓位、假说、执行、风险和历史拆成独立 owner，也保留了 price-only、UNKNOWN、PIT、条件路径、部分落袋和 runner 等有价值机制。

但 V3.3.0 在“如何运行”上仍将 Agent 降为候选生成者：系统 normalizer 检查严格 schema，deterministic selector 选择 operating lead/action，allocator 决定仓位映射。这使决策语义与用户所需的自主交易研究 Agent 不一致。

V3.3.1 不改写冻结 V3.3.0，而以新身份建立 Agent-first 候选：

- 保留 `InputSnapshot/HypothesisRecord/BehaviorPlan/Outcome/Review` 五工件；
- `HypothesisRecord.AgentDecisionBody` 成为当时决策的唯一权威原文；
- `BehaviorPlan` 只原样引用/复制 Agent 自选动作和仓位；
- `Review.AgentReviewBody` 成为复盘与学习的唯一权威原文；
- proposal schema、词表、lifecycle、字段顺序和语义缺漏不再是终态门；
- 确定性系统退回数据、PIT、计算、记忆、封存、Outcome 事实和权限安全。

本候选仍没有市场证据。预测增量、仓位 policy 效果、成本后收益、跨 regime 稳定、速度与生产可用性均为 `UNKNOWN_NOT_EVALUATED`。

## 2. 版本演进

| 版本 | 主要贡献 | 主要问题 | 当前处理 |
|---|---|---|---|
| Core V2.x | 事实分层、PIT、因果边界和安全合同 | 市场理论与治理重叠 | 历史 authority，不作当前入口 |
| V3.0/V3.1 | 更开放市场研究、raw-first、多维市场图 | 全闭包、上下文大和运行成本高 | 冻结历史 |
| V3.1.1 | 修复前瞻运行的部分可靠性 | 行为保守、资格链较重 | reliability predecessor |
| V3.2.x | probe/add/runner/reentry、动态区域和 delta 方向 | 单文件过大，运行治理吞噬市场主体 | runtime compatibility snapshot |
| V3.3.0 | 七 owner、市场主体、动态仓位、五工件 | 系统仍选择最终语义，严格 proposal 合同可拒绝可读决策 | 冻结前身，不改写 |
| V3.3.1 | Agent 唯一 decision owner、原文权威、非安全缺漏继续 Outcome/Review | runtime 与前瞻证据尚未建立 | 本自包含候选 |

上表的“贡献”不表示市场有效、盈利、可执行或生产成熟。

## 3. V3.3.0 的直接失败模式

### 3.1 隐藏/不完整 proposal 合同

Agent 可见上下文曾只列出必需字段名，而 domain normalizer 在后续要求更精确的嵌套类型、字段集和 lifecycle。可读、可反驳的 Agent 决策因这些格式差异在写入后发生终态拒绝，导致无 `HypothesisRecord/BehaviorPlan`。

这不是市场理论反证，而是系统合同夺走 Agent 决策的设计失败。

### 3.2 确定性选择器改写决策语义

V3.3.0 将 lead/runner/OTHER、动作和仓位分开给 Agent proposal、normalizer、selector 和 allocator。这产生了一个语义上的双中心：Agent 提出市场思考，系统作出真正记录的最终计划。

这类流程可以评价一个 hypothesis-only pipeline，但不能评价用户要求的自主 Agent 的市场—假说—动作—仓位整体能力。

### 3.3 格式错误掩盖 Agent 质量证据

当缺字段、额外字段、trigger 形状或 lifecycle 差异导致终态时，Outcome 与 Review 不再发生。结果既无法知道 Agent 的市场判断如何，也无法知道缺漏是否真的损害了决策。

V3.3.1 将缺漏/歧义本身作为样本中的能力证据：不修补、不重试到符合 schema，原样封存并继续 Outcome/Review。

## 4. 仍需保留的 V3.3.0 理论核心

V3.3.1 保留并重定 owner：

- 价格-only baseline 可完成，optional data 继续 UNKNOWN；
- 事实、测量、推断、假说和动作分层；
- 多时间尺度、依赖去重、行为动机与多模型路由；
- 竞争机制、条件路径、soft contradiction、hard falsifier、expiry 和区分观察；
- 初始仓位几何、tranche、加减仓、动态 stop/target、partial harvest、runner 和 reentry；
- 账户/执行真值与公开 reference plan 分开；
- 五条硬边界、五工件、单写者和前瞻 Outcome/Review。

改变的是决策 owner，不是市场理论主体。

## 5. V3.3.1 精确变更

| V3.3.0 设计 | V3.3.1 修正 | 当前 owner |
|---|---|---|
| Agent 返回 structured hypothesis/action proposal | Agent 返回可读完整 `AgentDecisionBody` | Agent |
| normalizer 校验语义 schema | 只检查可读非空；其他缺漏封存 | 系统安全外层 |
| 词典序选 lead/tie-break | Agent 自己选、并列或保留无解 | Agent |
| fixed action enum | Agent 可表达任何不可执行参考动作 | Agent |
| deterministic position allocator | Agent 选参考数量、tranche、stop/targets | Agent |
| BehaviorPlan 由 planner 生成 | 只原样引用/复制 Agent 动作和仓位 | Agent 语义，系统封存 |
| schema 缺失可 ANALYSIS_FAILED | 只有五硬边界可 fail-close | 系统安全 owner |
| Review 可由系统指标解释 | `Review.AgentReviewBody` 是唯一复盘判断 | Agent |
| learning 和版本验证易混合 | 学习候选→用户/integrator 选择→新版→字节验证 | Agent + integrator + system 分开 |

## 6. 不应重复的历史路线

- 不通过再加一层 schema 解决 schema 拒绝；
- 不使用“宽容 parser 后再强 normalizer”悄悄恢复系统选择权；
- 不同时保留 Agent 原文和一个系统“等价决策”；
- 不因格式缺漏重试 Agent 到出现系统喜欢的文本；
- 不把可丢弃 DecisionIndex 反向当作决策真值；
- 不让风险模块以非安全理由否决市场决策；
- 不在运行中修改理论或用新版重解释旧 run；
- 不用测试/manifest PASS 声称 Agent 决策有效。

## 7. 保留、回滚与身份

- V3.3.0 目录和 manifest 继续冻结，不修改。
- V3.3.1 是完整自包含包，不在运行时叠加 V3.3.0 规则。
- `theory/CURRENT.md` 在 integrator 合并前仍指向 V3.3.0；候选存在不等于已路由。
- 理论、Agent context、工件语义或 Outcome 口径改变都必须建立新 run identity。
- 旧 V3.3.0 run 只读保留，不继续、不补样、不回填、不算入 V3.3.1 证据。
- 回滚只能把共享入口重新指向已冻结版本，不能修改已有工件语义。

## 8. 仍未解决

- V3.3.1 manifest loader 与 Agent-first runtime 尚未实现；
- 五工件原文映射、可丢弃索引和新 run 尚未冻结；
- 非价格数据继续 UNKNOWN，本版不扩源；
- Agent 的动态性、自主性、全面性和高效性未有新身份前瞻证据；
- 市场预测增量、仓位管理效果、成本后收益和跨 regime 稳定均未评价；
- 当前没有账户、执行、paper/testnet/live 或资金权限。

这些 UNKNOWN 不能用更多理论文字解除。它们需要 integrator 先完成新身份实现与冻结，再由用户单独决定是否运行前瞻评价。
