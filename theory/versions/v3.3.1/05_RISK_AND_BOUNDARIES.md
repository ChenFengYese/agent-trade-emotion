# Agent-first 风险管理与边界

版本：`3.3.1-agent-first-trader-candidate.1`

状态：`FROZEN_VERSION_CANDIDATE / PUBLIC_RESEARCH_BOUNDARY / NON_EXECUTABLE`

Owner：不可逆安全、数据真实性、PIT/未来隔离、原文封存、单写者与外部权限。

本文不拥有市场方向、假说、最终参考动作、entry/stop/targets/仓位或复盘的决策权。

## 1. 边界的目标

风险边界只阻止三类不可接受结果：

1. 无法确认当时真实输入或信息来自未来；
2. 无法保证决策原文的唯一身份、可读性或不可变性；
3. 尝试造成未授权外部副作用。

它不阻止观点有争议、分析不完整、Agent 表达不规范、仓位激进、缺少 stop/target、没有 lead、新词汇或 optional data UNKNOWN。这些都属于决策质量和 Agent 能力证据，不属于系统终态资格门。

## 2. 五条硬边界

### 2.1 身份、raw 与核心覆盖完整性

系统必须能够确认：

```text
run / cycle / request identity
instrument / venue / contract semantics
core price source and raw digest
decision cutoff and closed-bar semantics
minimum frozen price coverage
theory version / revision / manifest identity
```

任一身份冲突、raw 摘要损坏、标的口径不可判定或核心价格覆盖不足，不得伪造 `InputSnapshot`。

非价格数据未取得不属于核心覆盖损坏。OI、funding、order flow、L2、news、macro、on-chain 和 account 在当前必须写 UNKNOWN，不阻断 price-only cycle。

### 2.2 PIT、未来隔离与迟到

- 任何 `available_at > decision_cutoff` 的事实不得进入当时 Agent 上下文；
- outcome、事后标签、未来标的池、修订值和事后选的 zone 不得回填；
- Agent 结果在预先冻结的 decision deadline 后返回时，不能伪装成准时决策；
- 迟到原 transport bytes 可作为事故证据存储，但不写入当时 `HypothesisRecord/BehaviorPlan`。

迟到是时间真实性问题，不是因为 Agent 文本花时更长就质量较差。deadline 必须在调用前冻结，不得事后移动以选择性接受。

### 2.3 单一 owner、单写者与不可变原文

- 五工件每个只有一个语义 owner 和一个物理 writer；
- 同一 `cycle + stage + digest` 只能返回同一引用或明确冲突；
- `AgentDecisionBody` 与 `AgentReviewBody` 以收到的精确可读字节封存；
- `BehaviorPlan` 只能原样引用/复制 Agent 自选动作与仓位；
- 双写、两个不一致副本、冻结后修补或 writer 不明时停止写入。

系统不得为了“标准化”改变原文标题、空白、字段顺序、对象形状、数字、动作词汇或矛盾。

### 2.4 可读且非空

Agent 输出只需通过两个内容层接受条件：

1. 按冻结 encoding 能够解码成可读文本；
2. 解码后不是只有空白。

不检查字段完整度、序列化类型、JSON schema、固定标题、lifecycle、action enum、假说数量、stop/target 存在性或文本内部一致性。可读非空但质量较差的决策必须封存并继续 Outcome/Review。

### 2.5 权限与外部副作用

当前权限只有：

```text
public data
non-account
non-executable research
side-effect-free calculation
local immutable recording
```

以下各需独立明确授权：private account read、credential use、licensed/paid data、paper、testnet、live order、fund movement、automation/broadcast。相邻授权不能推导。

Agent 可以在原文提出任何参考动作，包括文字上的买入/卖出。可读原文仍封存为不可执行研究。只要实际外部通道被调用，安全系统就必须在未授权或真值不足时 fail-close 副作用，不伪造 ACK/fill。

## 3. 硬边界与 Agent 决策质量分开

| 情况 | 是否封存 Agent 原文 | 是否继续 Outcome/Review | 系统可以做什么 |
|---|---:|---:|---|
| 核心 raw/identity/coverage 损坏 | 无法形成当时决策工件 | 否 | 保留错误证据，不伪造 snapshot |
| 未来泄漏 | 不作合法决策封存 | 否 | 关闭身份，不重试同 cycle |
| Agent 迟到 | 不进当时 HypothesisRecord | 否 | transport raw 可作事故证据 |
| writer/digest 冲突 | 停止新写入 | 不继续直到冲突解决 | 报告精确冲突 |
| 不可读或空白 | 不伪造 body | 否 | 保留 transport 故障 |
| 未授权外部动作文本 | 是 | 是 | 封存研究，只关闭外部通道 |
| schema/字段/顺序/枚举差异 | 是 | 是 | 可作非权威索引注释 |
| 缺 lead/stop/target/position | 是 | 是 | 保留 null/ambiguous，不填充 |
| 仓位看起来过大 | 是 | 是 | 不执行；留给 Agent Review |
| 伪精确概率/证据重复 | 是 | 是 | 保留证据，不改写 |
| optional source 缺失 | 是 | 是 | UNKNOWN，不伪造为零 |
| DecisionIndex 失败 | 是 | 是 | 索引 `UNAVAILABLE`，原文继续 |

## 4. 风险模块不得拥有的权力

风险/安全模块不得：

- 因观点太激进、不符合旧 policy 或系统偏好而否决参考决策；
- 在 Agent 没写仓位时生成默认零仓位；
- 在 Agent 写多个动作时选择“最安全”动作；
- 将 hard falsifier 命中自动转为系统选的 CLOSE；
- 用风险档位、波动阈值、allocator 或账户假值改写 Agent 参考仓位；
- 把非价格 UNKNOWN 当作“不允许判断”；
- 把不可执行参考计划伪装成订单。

它可以在 Agent 上下文中清楚告知当前不可执行、账户真值未知、外部通道关闭，并在 `SystemEnvelope` 中记录这些事实。

## 5. 假说失效与安全失败分开

| 情况 | 语义 owner | 理论处理 |
|---|---|---|
| 路径 hard falsifier 命中 | Agent | Agent 判断假说、动作和仓位如何改变 |
| 软反证/时间消耗 | Agent | Agent 比较 hold/reduce/close/reassess |
| 价格路径没按预期 | Agent Review | 封存 Outcome 后判断，不当系统错误 |
| 可选数据缺失 | 系统事实 + Agent 解释 | UNKNOWN，cycle 继续 |
| 核心 raw/PIT 不可信 | 系统 | 硬边界 fail-close |
| 外部权限缺失 | 系统 | 阻断副作用，保留研究原文 |

这防止了系统把市场理论质量问题当作安全合同问题。

## 6. WAIT、probe、reduce 与新动作

WAIT、probe、reduce、close、部分落袋、runner、reentry 和 OTHER 都只是 Agent 可用的语义，不是风险系统的 action enum。

理论期望 Agent 对 WAIT 说明机会成本和 review，对 probe 说明它能回答什么问题，对 reduce 说明哪个路径/风险发生了变化。但缺失这些内容仍封存并复盘，不由系统补齐。

Agent 可以提出未出现在理论词表中的新的不可执行参考动作。只要它没有真的外部副作用，系统必须记录，不因超出词典拒绝。

## 7. 外部执行的未来边界

本版不定义或激活 executor。未来如需进入真实账户行为，至少需要独立权威的：

```text
AccountSnapshot
PositionTruth
OrderIntent and idempotency
venue rules and instrument limits
fee/funding/margin/liquidation truth
spread/depth/slippage/fill state
cancel/replace/reduce-only semantics
post-action reconciliation
emergency reduce/close authority
```

这些未成立时，`BehaviorPlan.non_executable=true`。网页存在、API 可达、paper ACK、value=0 canary 或账户有资金都不等于订单/资金权限。

## 8. 恢复与不可逆操作

恢复只从已封存五工件和摘要继续，不从压缩聊天、可丢弃索引或系统对原文的重述恢复。

涉及外部状态、冻结工件或删除时：

1. 解析精确目标；
2. 读取当前真值；
3. 验证授权和幂等身份；
4. 优先可恢复方式；
5. 只由唯一 owner 写入；
6. 重读最终状态；
7. 不把 ACK 当最终真值。

这些规则保护不可逆结果，不得扩张成每一轮市场决策的资格闭包。

## 9. 停止线

只在下列情况停止对应链路：

- 标的/任务/核心 raw/覆盖不可信；
- PIT 或未来隔离被破坏；
- Agent 决策迟到，不能作为当时决策；
- 单写者/摘要/幂等身份冲突；
- Agent 原文不可读或只有空白；
- 未授权外部副作用到达安全通道（只停止副作用）。

“观点有争议”、“格式不符预期”、“假说不完整”、“没有 stop”、“仓位太大”、“Agent 没有选唯一方向”、“可选数据缺失”和“索引失败”都不是停止线。

## 10. 当前边界

| 能力 | V3.3.1 理论 | 当前实际边界 |
|---|---|---|
| Agent 市场/假说/动作/仓位/复盘唯一 owner | 已定义 | runtime 待迁移 |
| 五工件与原文权威 | 已定义 | 新实现/新 run 待冻结 |
| 价格-only 公开研究 | 允许 | 非价格数据 UNKNOWN |
| 账户读取 | 不授权 | 不可用 |
| paper/testnet/live | 不授权 | 不可用 |
| 预测/仓位效果 | 未声称 | `UNKNOWN_NOT_EVALUATED` |

减少系统语义门不是放松数据真实性、PIT、未来隔离、原文不可变性和外部权限。它放开的是 Agent 在安全研究范围内的思考、表达和决策权。
