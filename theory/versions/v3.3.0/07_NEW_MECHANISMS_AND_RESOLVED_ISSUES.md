# 新增机制与已知问题解决矩阵

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE_CHANGE_MAP / NON_AUTHORITY`

Owner：说明 V3.3.0 新增了什么、解决哪项已知设计问题、还需什么实现或证据。

当前规则仍以 `01–05` 为准；本文件只做索引，不复制完整定义。

## 1. 状态语义

| 状态 | 含义 |
|---|---|
| `RESOLVED_IN_THEORY` | 当前文档已给出唯一合同和 owner |
| `PENDING_IMPLEMENTATION` | 设计已定，runtime 尚未接入 |
| `PENDING_FORWARD_EVIDENCE` | runtime/理论即使存在，也没有市场 outcome |
| `BLOCKED_BY_AUTHORITY` | 需要用户另行授权账户、订单或实验 |
| `RETAINED_UNKNOWN` | 理论故意保留，不能伪造答案 |

“解决”只表示设计冲突已被消除，不表示市场有效或代码已经完成。

## 2. 核心问题解决矩阵

| 已知问题 | V3.3.0 解决方案 | Owner | 当前状态 |
|---|---|---|---|
| 市场认知不是主体 | 建为最大独立市场篇，覆盖数据、十五对象、方法、来源、时间、动机、路线和模型 | 01 | `RESOLVED_IN_THEORY` |
| 市场动态识别因子少 | price/flow/book/leverage/vol/macro/cross-asset/event/narrative/on-chain/venue 等扩展对象 | 01 | `RESOLVED_IN_THEORY` |
| 指标堆叠重复计票 | `FactorCard + dependency_cluster`，同源只保留主体测量和诊断 | 01/03 | `RESOLVED_IN_THEORY` |
| 数据“已接入”冒充“已取得” | 来源等级与可获得性正交；`CURRENTLY_OBSERVED` 必须有本 cycle raw | 01 | `RESOLVED_IN_THEORY` |
| 时间尺度混用 | Context/Decision/Execution 三 frame 与六种行为目的路由 | 01 | `RESOLVED_IN_THEORY` |
| 方法适用条件不清 | `AnalysisMethodCard` 注册输入、horizon、regime、失效和 snooping risk | 01 | `RESOLVED_IN_THEORY` |
| 全数据闭包阻断 baseline | `BASELINE_PRICE / TACTICAL_FLOW / STRATEGIC_CONTEXT / FULL_RESEARCH` profiles | 01/04 | `RESOLVED_IN_THEORY`、实现待接 |
| UNKNOWN 自动变 WAIT/零风险 | 方向、regime、liquidity 分开；允许条件计划/reference probe；WAIT 写成本 | 03/05 | `RESOLVED_IN_THEORY` |
| 假说类型和维护边界混乱 | State/Attribution/Forecast Path/Action Thesis 四级合同 | 03 | `RESOLVED_IN_THEORY` |
| 假说太多或任意截断 | 按机制/路径/行动差异去重，用 payload/决策价值而非魔法数量 | 03 | `RESOLVED_IN_THEORY` |
| 主观支持映射 0/0.5/1 | 有序不可校准支持与客观仓位几何分离；数值移入 policy | 03/02 | `RESOLVED_IN_THEORY` |
| 缺少稳定 tie-break | 事实准入→机制→路径→独立支持→可撤销动作→简单性词典序 | 03 | `RESOLVED_IN_THEORY` |
| 初始仓位说明不足 | 先失效位、压力退出、单位损失，再按多重上限算 quantity | 02 | `RESOLVED_IN_THEORY` |
| 固定止盈过早全平 | `Floor / Giveback / minimum harvest / independent runner` | 02 | `RESOLVED_IN_THEORY`、效果待证 |
| 盈利时不及时落袋 | 高收益必须比较 partial harvest；继续性未增强时先实现部分净值 | 02 | `RESOLVED_IN_THEORY`、参数待证 |
| 加仓易变成摊平 | fresh mechanism evidence + released risk + independent tranche | 02 | `RESOLVED_IN_THEORY` |
| stop 放宽冲突 | 从“价格单向”升级为“总压力损失不增加”；先减仓再放宽 | 02 | `RESOLVED_IN_THEORY` |
| reentry 固定 24h/次数 | 按失败类型、新证据和剩余 episode 风险；次数只作诊断 | 02 | `RESOLVED_IN_THEORY` |
| 多假说伪装分散化 | tranche 对 dependency cluster 完整归因，共享因子不增加容量 | 02/03 | `RESOLVED_IN_THEORY` |
| 组合风险设计不足 | covariance contribution + tail scenarios + venue/collateral clusters | 02 | `RESOLVED_IN_THEORY`、账户待授权 |
| 理论、资格、事故混为一体 | 七 owner；历史与机制索引退出理论主体 | README/06/07 | `RESOLVED_IN_THEORY` |
| cycle 工件无限扩张 | 固定五业务工件，RunState 只是投影 | README/04 | `RESOLVED_IN_THEORY` |
| Agent 上下文巨大 | bounded packet、raw refs、delta dependency traversal、一次局部修正 | 04 | `PENDING_IMPLEMENTATION` |
| Q0–Q8/全闭包进入热路径 | 新路径只保留 PIT、五工件、单写者和必要摘要；旧资格只历史重放 | 04/06 | `PENDING_IMPLEMENTATION` |
| 多 Agent/多写者冲突 | 默认单 Research Agent + 单 Application writer；specialist 无写权 | 04 | `RESOLVED_IN_THEORY`、实现待接 |
| 风险模块过度否决 | 仅五条硬边界，其余 claim 降级、缩仓或关闭 execution mapping | 05 | `RESOLVED_IN_THEORY` |
| 版本只写 3.2.1 产生歧义 | version + revision + manifest digest 三元绑定 | README/04 | `PENDING_IMPLEMENTATION` |
| 单文件无法维护 | V3.3.0 七文档；旧单文件保留为 runtime snapshot | README/04 | 文档已解决、loader 待实现 |
| 旧版本入口混乱 | 版本索引 + legacy 摘要 + 引用绑定保留策略 | 06/versions INDEX | `RESOLVED_IN_THEORY` |
| 本地 PASS 冒充市场价值 | 所有版本显式 `UNKNOWN_NOT_EVALUATED`；前瞻 baseline 才能晋级 | README/06 | `PENDING_FORWARD_EVIDENCE` |

## 3. 新机制定义索引

### M01 Point-in-time Data Capability Matrix

把来源权威和当前可获得性分开。解决 adapter/page 存在就声称数据可用的问题。

输入：raw 与 source metadata。输出：source level、availability、claim ceiling、UNKNOWN。

### M02 FactorCard

统一记录原始引用、变换、delta、dependency cluster、支持/反证、替代解释和 TTL。解决指标重复、时间错配和事后解释。

### M03 AnalysisMethodCard

每个模型声明识别对象、输入、horizon、regime、失效和数据窥探风险。解决方法百科化和无条件使用。

### M04 Three-frame Routing

每轮只启用 `CONTEXT / DECISION / EXECUTION` 三个 frame。解决无限加周期寻找一致结论。

### M05 Behavior-motive Lens

按方向投机、套保、做市、套利、去杠杆、再平衡、获利了结、恐慌追涨和信息重定价生成竞争机制；始终保留替代动机。

### M06 Profile-based Market Cognition

价格 baseline 不再被十二轴闭包阻断；增强数据只升级可用模型和 claim ceiling。

### M07 Regime Reducer

方向持续、反转频率、波动和流动性共同形成可解释 regime；价格-only 与综合 regime 分开。

### M08 Four-level Hypothesis Graph

把“当前状态”“原因”“未来路径”“行动 thesis”拆开，避免从新闻或指标直接跳到仓位。

### M09 Path Contract

统一 trigger、expected sequence、acceleration/decay、soft contradiction、hard falsifier、expiry 和下一观察。解决不可失败的故事。

### M10 Ordinal Support Without Pseudo-probability

保留 `lead / runner-up / OTHER / UNRESOLVED`，不输出概率、EV 或固定分差；让选择可执行但不假装校准。

### M11 Geometry-before-size

先定义结构失效、保护触发和压力退出，再计算单位压力损失与数量。解决固定百分比脱离市场结构。

### M12 Episode and Tranche Lifecycle

`WATCH → SEED → CORE → HARVESTED → RUNNER → CLOSED`，每个 tranche 独立绑定假说、失效和预算。

### M13 Stress-risk Monotonicity

仓位调整后压力损失不得上升；需要更宽 stop 时先减 quantity。比 stop 价格机械单向更贴近真实风险。

### M14 Partial Harvest and Runner Floor

用已实现净值加剩余仓位压力清算净值形成 `Floor`，求满足目标 Floor 的最小 harvest，同时保留独立 runner。

### M15 Evidence-gated Anti-martingale

只有 fresh 机制证据、旧风险释放和多重上限通过后才能 ADD；价格有利或亏损都不自动加仓。

### M16 Failure-aware Reentry

按上次退出原因决定重入；hard falsification、新旧失败 cluster 和剩余预算比固定时钟/次数更稳定。

### M17 Five-artifact Cycle

`InputSnapshot / HypothesisRecord / BehaviorPlan / Outcome / Review` 是唯一业务工件，其他索引和图都可派生。

### M18 Bounded Agent Packet

只传任务、admitted FactorCards、必要 deterministic measures、active hypotheses、合法动作和 UNKNOWN；全理论与事故不进入 packet。

### M19 Cold/Delta/Event Routes

冷启动形成完整状态；delta 只处理变化依赖；event fast path 优先减少风险。设计目标 cold ≤15m、delta ≤2m，尚未测量。

### M20 Hard-vs-soft Boundary

硬边界只保留真实性、未来隔离、权限、可执行损失和单写者；其他不确定性进入降级而非资格扩张。

### M21 Theory Manifest Binding

每个工件绑定 `theory_version / theory_revision / theory_manifest_digest`，解决同名版本不同正文与旧兼容字段歧义。

## 4. 从文档到可运行的完整解决路线

### Phase A：工作环境、理论分类与冻结（已完成）

完成条件：

- V3.3.0 七 owner 齐全；
- 市场认知为最大单篇，市场+仓位为正文主体；
- V3.2.6 和 V3.1.1 有版本入口；
- CURRENT/WORKSPACE/INDEX 指向唯一当前候选；
- legacy 摘要解释旧版本和保留原因；
- 不破坏旧 runtime 单文件消费者；
- README 与七个 owner 由 manifest 固定；
- 五份用户批准且已吸收旧稿退出活动理论树；
- 只做文档结构验证。

### Phase B：最小 runtime 迁移

完成条件：

- 现有 composition owner 支持 manifest loader；
- 七文件按固定顺序和 digest 读取；
- 复用现有 PIT、cycle 与 domain objects；
- 五工件成为主链，不新建第二平台；
- Baseline price cold/delta 能完成；
- 旧 V3.2 snapshot 不再被新 route 读取；
- owning tests 与一个直接消费者通过。

### Phase C：冻结并获得前瞻证据

需要用户另行授权真实公开数据 baseline。完成条件：

- 冻结 theory revision、method/policy 参数和 outcome；
- 不在 run 中修改理论；
- 产生真实 PIT decision、合法 outcome 与 Review；
- 记录 cold/delta 实际耗时；
- 只基于结果决定保留/修改机制。

### Phase D：仓位 policy 比较

在有足够前瞻 episode 后比较：

```text
fixed target full exit
structure exit
trailing
partial harvest + runner
time/event exit
reentry variants
```

当前不预先宣布任何 arm 盈利更高。

### Phase E：账户/执行（非当前范围）

只有独立授权后建立 AccountSnapshot、PositionTruth、费率/保证金/成交与 reconciliation owner。reference plan 不直接升级为订单。

## 5. 可验收检查

| 检查 | 本版应满足 | 市场有效性要求 |
|---|---|---|
| 文档 owner 唯一 | 是 | 不涉及 |
| 当前入口唯一 | 是 | 不涉及 |
| 市场篇最大 | 是 | 不证明 alpha |
| 市场+仓位占正文主体 | 是 | 不证明盈利 |
| 来源与社区边界 | 是 | 实际 coverage 待 run |
| UNKNOWN 保留 | 是 | 待前瞻观察 |
| 动态仓位公式完整 | 是 | 参数效果待比较 |
| Agent/执行链完整 | 设计是 | runtime 待实现 |
| 风险边界更少 | 是 | 账户仍未授权 |
| 旧消费者不破坏 | 保留 snapshot | 新 loader 待实现 |
| 运行速度 | 只有目标 | 必须实测 |
| 市场价值 | UNKNOWN | 必须真实前瞻 outcome |

## 6. 仍需保持 UNKNOWN

- 哪些市场方法对当前目标 horizon 有稳定增量；
- 哪种 harvest/runner policy 最适合不同 regime；
- reference risk 与未来真实成本的偏差；
- cold/delta 路线是否达到时间目标；
- 数据源在运行时的实际覆盖与稳定性；
- Agent 在相同 packet 下的选择稳定性；
- portfolio stress 和 correlation model 在尾部的充分性；
- V3.3.0 能否在成本后产生正价值。

这些不是待用更多文字填满的空白，而是下一阶段必须通过实现或前瞻证据回答的问题。
