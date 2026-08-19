# 历史复盘、失败与变更总结

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE_HISTORY / NON_AUTHORITY`

Owner：版本演进、已知失败、吸取的设计教训和本版变更。

本文件不定义当前市场或仓位规则；当前规则只由同目录前五篇定义。历史 PASS、qualification、accepted、paper 或事故不能自动继承为 V3.3.0 有效性或权限。

## 1. 当前结论

项目已经积累了较强的点时数据、未来隔离、可反驳路径和故障恢复思想，但市场认知、仓位管理与运行治理长期写在同一正文，治理和资格逐渐吞噬核心链路。V3.3.0 的主要修正不是再加一套治理，而是把市场认知和动态仓位重新放回主体，将执行合同、风险边界与历史分别归档。

截至本版：

- 没有正式 V3.3.0 前瞻 baseline；
- 市场预测增量、成本后收益和跨 regime 泛化均为 `UNKNOWN_NOT_EVALUATED`；
- V3.3.0 多文件 runtime 尚未实现；
- 旧 V3.2 qualification/故障记录只作不可变历史，不授权新运行；
- 当前只完成理论与工作区重构。

## 2. 版本演进

| 版本 | 当前角色 | 主要贡献 | 主要不足 | 当前处理 |
|---|---|---|---|---|
| Core V2.0/V2.1 | 历史成熟工程 authority | 事实分层、PIT、因果边界、运行与安全合同 | 市场/治理混合，当前大量代码与冻结材料绑定 | 保留原字节，不作默认理论入口 |
| V3.0 Draft | 历史研究草案 | 更开放的市场研究与 Agent 假说 | 合同和实际落地仍不稳定 | 历史摘要；原件因引用保留 |
| V3.1 Draft | 冻结实验前身 | raw-first、十二轴、动态图、严格路径 | 全闭包、上下文与运行成本过大 | 冻结引用保留，不删除 |
| V3.1.1 | 前一 reliability base | 修复旧前瞻运行 P0、序数假说与资格边界 | 行为仍偏保守、资格链仍重 | 保留为前一可靠性基线 |
| V3.2.0–V3.2.6 | advanced pending-evaluation candidate | probe/add/runner/reentry、动态区域、delta、软 UNKNOWN | 单文件约 10 万字节；运行治理和事故占比高；正式 target/outcome 为零 | 保留 runtime compatibility snapshot |
| V3.3.0 | 冻结当前模块化候选 | 市场认知主体、动态仓位、七 owner、五工件、快慢路径 | 尚未实现和前瞻评价 | manifest 固定；当前理论入口 |

“成熟”在上表只指工程/可靠性角色，不表示市场有效、盈利或生产可用。

## 3. 历史失败分类

### 3.1 市场核心被治理挤出

V3.2 后半段包含大量 qualification、authority、receipt、Q0–Q8、runtime closure、恢复和事故处置；这些设计曾用于保护冻结实验，但进入理论主体和每轮热路径后，造成：

- 研究 Agent 需要读取与市场无关的大量上下文；
- cycle 完成依赖资格链，而非五个业务工件；
- 市场方法和仓位细节篇幅不足；
- 每次修复产生更多 receipt/registry 而不是 baseline；
- 用户难以定位当前理论规则。

V3.3.0 将治理退出前五篇正文；执行篇只保留单写者、五工件和恢复所需的最小合同。

### 3.2 正式 baseline 长期为零

历史多轮本地回归和 qualification 只能证明局部工程合同。正式 V3.2 target authority、cycle 和 outcome 没有形成，因此：

- 不能说理论已经预测有效；
- 不能由本地 PASS 推断市场价值；
- 继续加规则不能弥补无前瞻结果；
- 速度、稳定性和成本后收益仍未知。

此前“Baseline 前冻结理论”是为阻止无结果扩张。本次用户明确要求先重构理论和工作环境，因此仅对本任务解除；V3.3.0 文档完成后重新冻结，下一步应先实现最小 loader/route，再由用户单独授权前瞻 baseline。

### 3.3 上下文与材料化失控

历史 qualification 暴露过多种上下文失败：真实 market graph view、proposal 和最终 presentation 重复包装后达到数百 KiB 乃至更大；分片反而膨胀；调用未持续轮询又产生跨进程 owner 冲突。

设计教训：

- Agent packet 必须只含 admitted facts、必要 deterministic measures、active hypotheses 和 refs；
- raw、全图、旧理论、事故、测试闭包不重复内联；
- packet 在最终对象上度量，不能只测中间片段；
- 一个 cycle 只有一个 composition owner；
- delta 只遍历变化节点的直接消费者；
- transport 分片不能在未定义游标、ACK 与重组合同前临时启用。

V3.3.0 不复制旧 transport 事故细节到主链，只在执行篇保留 bounded packet 与单写者。

### 3.4 资格和测试重复

当前错误 owner 已记录：V3.2 与全 Theory suite 重叠、换 run ID 重跑相同提交、Q0–Q8 与 43→196 文件闭包每轮重放、V3.2 单项不断重建 Git/临时目录/authority。历史数据表明重复套件能占据接近一半时间。

修正方向：

- 代码能力绑定 commit/runtime，不绑定 qualification ID；
- 同一 test ID 在同一门只运行一次；
- suite 有包含关系时只执行全集；
- 资格、发布和实验运行拆开；
- 纯合同使用最小内存对象；
- 真实 Git、进程和外部 transport 只留给相应 integration 边界；
- 文档变更只做结构、链接、引用和 diff 检查。

本次按用户要求没有运行实验或业务测试。

### 3.5 UNKNOWN 被过度解释为零风险/WAIT

旧理论曾在数据不全、非方向 regime 或执行最大损失未知时把方向 reference risk 归零，造成合法研究动作被删除。V3.2 已开始区分 real-execution `UNKNOWN_MAX_LOSS` 与公开研究，但仍保留固定档位和部分零风险映射。

V3.3.0 明确：

- 核心事实有效时可完成 price-only baseline；
- 可选数据缺失只关闭对应模型；
- `direction=UNKNOWN` 与 `regime=RANGE/TRANSITION` 分开；
- 研究 reference plan 与真实 executable quantity 分开；
- WAIT 必须给机会成本和下一 review；
- 条件计划和 reference probe 是合法动作；
- 只有事实/时间、未来、权限、执行损失和 owner 冲突是硬边界。

### 3.6 主观支持被固定数值化

V3.2 使用过 `EXTREME_UNCERTAINTY / LOW / HIGH` 到 `0 / 0.5 / 1` 的固定 risk mapping。即使它声明不是概率，也会把尚未校准的主观支持与仓位数值绑定，且难以适应不同市场状态。

V3.3.0 将其移入版本化 `PositionPolicy`：

- 假说只给有序、不可校准支持和 claim ceiling；
- 仓位几何由失效位、压力损失与预算计算；
- Agent 只能建议 risk class 或降低上限；
- 固定比例必须标 `UNVALIDATED`；
- 不使用概率、EV 或 Kelly。

### 3.7 固定 reentry 与保护规则

旧 V3.2 固定 24h ledger、次数/累计上限和单向保护位，能防 churn，却把 policy 参数写成稳定理论。

V3.3.0 改为：

- reentry 取决于失败类型、新机制证据和剩余 episode 风险；
- attempt count 只作诊断；
- hard falsification、风险耗尽和同类失败无新证据才是稳定停止线；
- 保护遵守“压力损失不增加”，不是机械“stop 价格只向前”；
- 如结构需要放宽 stop，先减仓并重算，否则关闭后重建。

### 3.8 固定止盈与过早全平

历史理论已经识别“固定止盈默认全平并终结 episode”会损失长趋势，但动态落袋、runner 和 giveback 的合同仍不足。

V3.3.0 新增：

- episode `Floor_t` 与 `Giveback_t`；
- 最小 harvest 数量求解；
- `SEED → CORE → HARVESTED → RUNNER`；
- 高收益时部分实现净值；
- runner 拥有独立 thesis/stop/expiry；
- harvest 后无新证据不得加回；
- fixed TP、trailing、partial+runner 仅是未来 policy arms。

## 4. 历史 qualification 的正确使用

旧失败、expired 或 tombstone pair 的唯一用途是：

- 证明某种工程失败真实发生；
- 防止同 identity 重试或改写；
- 为新版本提供失败模式；
- 保护冻结 evidence lineage。

它们不能：

- 证明 V3.3.0 runtime 可用；
- 证明当前 Codex transport/monitor 可靠；
- 计入新 baseline；
- 授权任何 external run；
- 被清理为“过时文件”后重签；
- 替代真实市场 outcome。

因此旧绑定文件继续留在 history/archive，不进入默认理论阅读路线。

## 5. V3.3.0 逐项变更

| 旧问题 | V3.3.0 变更 | Owner |
|---|---|---|
| 单文件混合理论/治理 | 七个稳定 owner + 短入口 | README/WORKSPACE |
| 市场方法细节不足 | 十五类对象、方法库、来源、模型路由、时间/动机路线 | 01 |
| 仓位仍是固定档位 | 压力损失 sizing、tranche、harvest/runner、portfolio | 02 |
| 假说维护困难 | 四类假说、竞争集、Path Contract、生命周期 | 03 |
| 完整链路分散 | 五工件、四层、cold/delta/event 路径、Agent packet | 04 |
| 限制过多 | 五条硬边界，其余软降级 | 05 |
| 历史污染当前规则 | 本文件单独承载 | 06 |
| 新机制与问题映射散落 | 独立问题矩阵 | 07 |
| 版本字段歧义 | `version + revision + manifest digest` | README/04 |
| runtime 仅单文件 | 先保留旧快照，后续实现 manifest loader | 04 |

## 6. 保留、压缩与删除原则

### 默认可导航版本

- V3.3.0：当前模块化候选；
- V3.2.6：先进、待实验的 runtime compatibility predecessor；
- V3.1.1：前一 reliability base。

### 只在 legacy 索引可见

- V3.1/V3.0 drafts；
- Core V2.x；
- 市场情绪、RSI、四层、动态图、路径风险、自主性等 challenger。

### 当前不能删除

Core、V3.1、V3.0 和多数 challenger 仍被代码、配置、测试或冻结工件按路径/摘要引用。删除会破坏重放和活动消费者，不能只因版本旧而移除。

### 用户批准删除的五份原文

目前只识别出五份没有现行代码/配置/测试引用或仅有历史叙述引用的候选，合计 `127,366` 字节：

```text
theory/history/BOUNDED_AGENT_AUTONOMY_CHALLENGER_v0_1.md
theory/history/PATH_RISK_AND_STAGED_POSITION_GOVERNANCE_CHALLENGER_v0_1.md
theory/history/STRATEGIC_EPISODE_POSITION_GOVERNANCE_CHALLENGER_v0_1.md
theory/history/THEORY_AGENT_V2_THEORY_BASIS_v1_0.md
theory/history/THEORY_AGENT_V2_THEORY_TECHNICAL_BRIEF_v0_1.md
```

本版已吸收其有效原则。用户于 `2026-08-11` 明确批准删除上述五个精确目标；删除后只保留本摘要、原 SHA-256 和 Git 恢复点，不把不存在的路径继续作为活动入口。恢复来源为基准提交 `0de6bf87ae3d065205d337ad8996881b159f91f6` 中的旧根路径。

## 7. 仍未解决

- V3.3.0 manifest loader 尚未实现；
- 现有 V3.2 runtime 仍依赖单文件完整 Markdown；
- cold `≤15m`、delta `≤2m` 只是设计目标；
- 市场识别和仓位 policy 未有前瞻 outcome；
- 公开数据实际覆盖需在获准 baseline 时逐项确认；
- portfolio/account/execution 仍是未来合同，不是当前能力；
- 五份用户批准旧稿已退出活动理论树；仅可从上述 Git 恢复点恢复。

这些 UNKNOWN 不阻止当前文档成为新的理论候选，但阻止“成熟、盈利、可执行、可快速上线”的声明。
