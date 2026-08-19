# 风险管理与边界处理

版本：`3.3.0-modular-cognition-position-candidate.1`

状态：`FROZEN_CURRENT_CANDIDATE / PUBLIC_RESEARCH_BOUNDARY / NON_EXECUTABLE`

Owner：不可逆安全、真实性、未来隔离、权限与软降级。

本文不是市场判断主体。它只阻止无法恢复、无法定义或未经授权的动作，不用“更安全”为理由替 Agent 选择市场方向。

## 1. 设计原则

V3.3.0 将限制压缩为少量硬边界，把其余不确定性转换为：

```text
claim ceiling
UNKNOWN
smaller reference risk
conditional plan
probe/reference observation
WAIT with review condition
execution_mapping=NOT_READY
```

风险模块回答“这个动作是否越过不可接受边界”；市场认知回答“市场是什么”；假说体系回答“哪些路径竞争”；仓位模块回答“暴露多少”。风险模块不得拥有后面三者。

## 2. 五条硬边界

### 2.1 数据与身份完整性

以下任一项不可确认时，不准入方向 cycle：

- instrument/contract/venue 身份；
- 核心价格字段和单位；
- 决策时间与 closed-bar 语义；
- raw 来源和摘要；
- outcome 与决策使用同一口径的能力。

可选 OI、flow、news、macro 或 on-chain 缺失不属于硬失败。

### 2.2 未来隔离

任何 `available_at > decision_at` 的事实不得进入决策。修订后的宏观值、事后标签、outcome、未来标的池和事后选择的 zone 都不能回填旧 cycle。

### 2.3 权限边界

当前默认只有公开、合法、不可执行研究。以下分别需要独立明确授权：

```text
private account read
credential use
licensed/paid data
paper trading
testnet
live order
fund movement
automation/broadcast
```

相邻授权不能推导。账户有资金、API 可达、paper ACK 或 value=0 canary 都不等于订单/资金权限。

### 2.4 可执行损失必须可定义

未来 executor 只有在真实数量、费用、滑点、保证金、清算、reduce-only、partial fill 和最终 position truth 可校验时才能增加风险。缺失时 market/hypothesis/reference plan 可继续，但 `executable_quantity=null`。

### 2.5 单一事实 owner 与单写者

raw、InputSnapshot、HypothesisRecord、BehaviorPlan、Outcome、Review 和未来账户真值各有唯一 owner。出现两个写者、双写或无法判定最新状态时停止写入，不能“择一看起来正确”的副本继续。

## 3. 软边界：降级而非封死

| 情况 | 默认处理 | 不应处理成 |
|---|---|---|
| 可选 source 缺失 | UNKNOWN；关闭对应模型 | 全 cycle 失败 |
| 方向冲突 | 保留 lead/runner-up/OTHER | 强行平均或归零 |
| 归因不确定 | 缩窄 claim，寻找区分观察 | 禁止任何条件计划 |
| regime TRANSITION | 条件路径、较小 reference risk | 永久 WAIT |
| 成本只有公开压力估计 | 允许 reference plan | 冒充 executable plan |
| 流动性只有 snapshot | 不输出韧性；缩小 claim | 把 depth 当 fill 保证 |
| 新闻只到聚合层 | 作为发现线索 | 确认事实 |
| Agent 输出并列 | `UNRESOLVED` | 用伪概率破局 |
| 数据 profile 较低 | price-only baseline | 要求十二轴全闭包 |

软边界不得不断升级为新的资格门、registry 或 receipt。

## 4. Agent 的自由空间

在五条硬边界内，Agent 可以：

- 新建、削弱、替换竞争假说；
- 使用注册方法或提出新的候选方法；
- 比较方向、WAIT、probe、减仓、退出、再入场和信息动作；
- 提出反直觉机制和 `OTHER`；
- 在可选数据缺失时完成 price-only 判断；
- 对风险等级提出更低建议；
- 请求一项会改变决策的公开信息；
- 明确指出现有理论不够解释市场。

Agent 不可以：

- 改写准入事实、时间或 raw；
- 自行创建账户值、费用、fill 或权限；
- 用语言信心扩大 risk budget；
- 删除合法动作来让旧框架看似正确；
- 修改已封存决策或 outcome；
- 绕过许可、403、付费或地区限制；
- 发送订单或移动资金。

这不是限制推理，而是把推理自由与外部副作用分开。

## 5. 风险动作的最小原则

风险动作按副作用从低到高：

```text
observe
→ condition
→ reference probe
→ reduce planned risk
→ close reference plan
→ future account reduce-only
→ future account close/reconcile
→ future account new risk
```

在研究模式中只能到 `close reference plan`。未来账户模式中，减少既有风险与新增风险分别授权；紧急减少风险也必须读取真实 position truth 并在动作后对账。

## 6. Hard Falsifier 与风险否决

hard falsifier 是理论上的路径失效事实；风险否决是外部动作不合法或损失不可定义。二者分开：

| 情况 | Hypothesis | Position | Risk |
|---|---|---|---|
| 路径 hard falsified | 标记 FALSIFIED | CLOSE 对应 tranche | 允许/要求减风险 |
| 可选数据缺失 | 保留/降级 | 缩小或条件化 | 不否决研究 |
| 执行真值缺失 | 可继续 | reference only | 否决真实新增风险 |
| 权限缺失 | 可继续 | 行为映射停在研究 | 否决外部动作 |
| 数据身份不可信 | 不准入 | 无计划 | 终止 cycle |

风险模块不能因为观点看起来激进而否决；它只能依据明确合同和状态。

## 7. 不可逆动作与恢复

涉及外部状态、冻结工件或删除时：

1. 解析精确目标；
2. 读取当前真值；
3. 验证权限和幂等键；
4. 先选择可恢复方式；
5. 写入只由 owner 执行；
6. 重新读取最终状态；
7. 不把 ACK 当最终真值。

文档/历史清理优先用 Git 可恢复性并先修复活动引用。冻结实验、accepted/outcome、原始市场数据和用户副本不得因理论整理被改写。

## 8. Venue、流动性与执行风险

当前只记录公开风险候选：

- spread 与 size-dependent impact；
- market/limit/trigger 语义；
- stop-through、gap 和 partial fill；
- API/status/sequence 异常；
- index/mark/last 的差异；
- funding、margin、liquidation、ADL；
- collateral/stablecoin/venue concentration。

公开规则不等于当前账户真值；网页正常不等于端到端可用。未来 executor 需拥有独立 adapter、reconciliation 和 emergency reduce-only 合同，不能由理论文档直接激活。

## 9. 组合与尾部边界

组合风险由仓位模块计算，风险模块只检查上限是否违反 policy。正常相关性之外至少考虑：

```text
common beta shock
correlation-to-one
liquidity withdrawal
venue outage
funding and liquidation spiral
gap/stop-through
collateral or oracle shock
shared data/source failure
```

多个故事共享同一因子时按集中暴露处理。未知尾部风险不要求所有仓位归零，但要求不使用“模型未显示风险”作为扩大暴露理由。

## 10. WAIT、Probe 与 Reduce

### WAIT

合法 WAIT 必须有原因、机会成本、下一 review 和改变决策的观察。没有这些字段的 WAIT 是推迟决策，不是风险管理。

### Probe

当前 probe 只是规范化 reference action，用来比较信息价值和路径；不产生真实订单。它需要：

- 清楚的可观察问题；
- 最大 reference stress loss；
- expiry；
- 何种结果会更新竞争假说；
- 为什么观察价格/等待不更便宜。

### Reduce

软反证、波动/流动性恶化、相关性上升或高收益 giveback 增加时可先减仓，不必等待 hard falsifier。风险减少优先于新增风险。

## 11. 停止线

仅在以下情况停止当前链路：

- 核心数据身份、时间或完整性无法成立；
- 发现未来泄漏；
- 用户请求需要未授予的账户/订单/资金权限；
- 可执行损失无法定义但请求要求真实执行；
- 单一 owner/单写者冲突；
- 两条合法外部数据路线均被明确阻塞，继续需要绕过限制；
- 继续将产生不可恢复的错误状态。

“观点有争议”“缺少所有增强数据”“Agent 未给唯一方向”“市场波动很大”本身不是停止线。

## 12. 当前边界与未来边界

| 能力 | 当前 V3.3.0 文档 | 未来需另行完成 |
|---|---|---|
| 公开市场认知 | 已定义 | 接入与前瞻评价 |
| reference PositionPlan | 已定义 | runtime 映射 |
| 账户读取 | 无 | 明确授权、adapter、truth owner |
| paper/testnet | 无 | 独立授权与资格 |
| live | 无 | 更高独立授权、对账与紧急关闭 |
| 盈利/有效性 | UNKNOWN | 冻结理论后的真实前瞻证据 |

减少理论限制不等于放松真实性、未来隔离、资金和权限边界。V3.3.0 放开的是研究动作、假说竞争和软降级空间，不是未经授权的外部执行。
