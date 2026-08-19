# Post-V3.4 多模型管理 Agent 规划

状态：`POST_V3.4_DESIGN_ONLY / NOT_ACTIVE_IN_V3.4 / NO_RUNTIME_IMPORT`

用途：当 V3.4 单模型、4H 定时 FORECAST/FROZEN/DYNAMIC 路线验证稳定后，用不同成本与能力等级的模型分工，在多币种环境下降低重复上下文、重复分析和高价模型调用。本文不是当前 V3.4 的运行规则，不得被当前 scheduler、forecast harness、paper 或任何交易入口自动加载。

## 1. 设计结论

未来不采用“多个 Agent 持续互聊并共同盯盘”的模式。自由对话会把单 Agent 的 token 浪费放大为 N×M 次重复上下文，并重新引入注意力漂移、短周期目标漂移和责任不清。管理层应采用**外部定时调度 + 共享状态 + 有界消息 + 条件升级**：便宜模型处理可压缩、可复核、低风险工作；中档模型承担常规单资产 4H 分析；高价强模型只在高价值、冲突或战略重建时调用。

当前项目已观察到单币种 continuous-goal 运行可达到约 `8e8 token/day` 的极端消耗。该数字只作为架构失败样本，不作为未来成本预测。未来预算以 provider 实际 usage 计量；运行前先限制调用次数和上下文字节，再测真实 token。

## 2. 未来角色与权限

| 层级 | 默认成本 | 主要责任 | 不允许做什么 |
|---|---:|---|---|
| Deterministic Manager | 0 LLM token | 4H scheduler、预算、缓存、PIT refs、去重、任务路由、风险/订单事实 | 不解释市场、不选方向 |
| Context Worker | LOW | 把已准入的新数据压成 state delta、找数据缺口/冲突、生成引用索引 | 不输出交易方向、不覆盖 raw |
| Routine Asset Analyst | MEDIUM | 常规单币种 4H committee：状态、路径、WAIT/HOLD/计划草案 | 不越过 4H 时间权限、不直接调高价模型 |
| Senior Strategist | HIGH | regime 重建、复杂事件、跨资产联动、低置信/强冲突、重大仓位 | 不持续轮询、不重复读取完整历史 |
| Outcome Reviewer | LOW/MEDIUM | 对已封存 forecast/plan 与 outcome 做能力复盘和错误分类 | 不事后改写原 Decision |
| Manager Agent（可选） | LOW/MEDIUM | 在固定规则内选择上述模型、组织一次有界 challenge/resolution | 不拥有最终市场事实，不可自行增加调用轮数 |

模型名称、价格和具体 provider 不写死在架构里。选择只依赖四个动态能力标签：`COST_CLASS`、`REASONING_CLASS`、`CONTEXT_RELIABILITY`、`TOOL_RELIABILITY`。模型升级/降价后只改路由配置，不改交易理论。

## 3. 多 Agent 对接不是无限聊天

允许的未来对接形式是有界 artifact dialogue：

```text
TaskBrief
  → Draft
  → optional Challenge
  → Resolution
  → Seal
```

默认最多 `1 Draft + 1 Challenge + 1 Resolution`。没有实质分歧时只有 Draft。任何 Agent 不得把完整项目历史、完整理论或其他 Agent 全部原文再次复制进消息；只能引用 `shared_context_id / asset_state_id / source_ref` 并携带必要 delta。

必须保留 dissent：若低价模型和高价模型仍不同意，最终记录两个机制及分歧依据，而不是强制“讨论到一致”。管理 Agent 只负责路由和裁决流程，不得把多数票当市场真相。

## 4. Token/上下文预算

未来预算优先使用四层削减，而不是换更便宜模型后继续无限调用：

1. **调用削减**：每资产默认只有 6 个 4H committee slot/day；普通市场变化不增加额外市场 LLM slot，emergency 由确定性 safety 处理。
2. **共享削减**：宏观、BTC/ETH regime、全市场事件只形成一次 `GlobalMarketState`，所有币引用同一对象，不重复分析。
3. **增量削减**：每资产只携带 `latest StrategicState + last-4H delta + position/plan delta`，禁止完整历史灌入。
4. **模型升级削减**：Routine Analyst 先处理；只有明确 escalation condition 才调用 Senior Strategist。

未来 Manager 需要维护：

```text
system_daily_token_budget
asset_daily_token_budget
committee_token_budget
premium_call_budget
max_context_bytes
max_dialogue_rounds
actual_input_tokens / actual_output_tokens
cache_hit / escalation_reason
```

超预算默认是 `DEFER / USE_LOWER_COST / KEEP_PRIOR_STATE`，不是自动缩短 horizon 或增加低周期检查。风险紧急情况仍由确定性 fail-safe 处理，而不是用 token 预算逼模型做草率交易判断。

## 5. 多币种扩展

每个 4H slot 先构建一次：

```text
GlobalMarketState
  macro / BTC / ETH / broad risk / known events / shared data-quality
```

然后每个币只构建：

```text
AssetDelta
  own 4H/1H/15m internal path
  own OI/funding/volume/event delta
  own StrategicState
  own position/plan state
```

若 20 个币共享同一宏观/大盘背景，不允许把宏观正文复制 20 次。Context Worker 只返回引用和必要差异。相关性很高的一组资产可先做 cluster-level summary，但任何单资产最终 forecast 仍必须绑定自己的 PIT 数据，不能用 BTC 判断直接代替其自身分析。

## 6. 升级到高价模型的条件

高价模型只能在既定 4H committee 内由明确条件升级触发，不能因此新增盘中 wake。例如：

- 1D/4H regime 需要 `REPLACE/INVALIDATE`；
- Routine Analyst 的主/替代路径仍高度冲突且下一步会改变较大 exposure；
- 重大已知事件影响多个资产；
- 数据之间存在无法由普通解释消除的强冲突；
- 资产达到事前定义的高风险/高机会级别；
- 低价模型连续出现合同、算术或上下文一致性问题；
- Outcome Reviewer 发现某类重复错误需要战略重建。

“价格动了”“15m 破位”“Agent 想再确认一次”“本轮没事做”都不是升级理由。

## 7. 管理 Agent 的未来最小协议

Manager 每次只接收任务元数据，不接完整市场 raw：

```text
committee_slot
asset / cluster
current_state_ref
asset_delta_ref
position_risk_class
forecast_conflict_class
data_quality_class
remaining_token_budget
available_model_classes
```

输出只有：

```text
ROUTE_TO_MODEL_CLASS
OPTIONAL_CHALLENGER_CLASS
MAX_ROUNDS
CONTEXT_REFS
ESCALATION_REASON
```

最终方向仍由被路由的战略 Agent 负责。Manager 不允许生成 LONG/SHORT、stop、target 或仓位数量；这样可以避免“管理模型”在无完整市场上下文时偷偷成为第二个交易 Agent。

## 8. 禁止模式

未来即使启用多模型也禁止：continuous goal、无限 Agent-to-Agent chat、每币复制完整理论、每币重复获取共享数据、高价模型默认常驻、Agent 自己决定下一次 wake、低周期触发高价重分析、为了省 token 删掉关键 PIT/风险事实、通过多数投票代替证据。

## 9. 激活门

该设计只有同时满足以下条件才允许进入下一版本实现：

1. V3.4 `FORECAST_ONLY` 已产生足够合法 PIT 样本，并确认 scheduled context 的真实 token 成本；
2. Durable Strategic State 与 4H scheduler 在单模型下稳定，不依赖 continuous-goal；
3. 至少两个币种的离线 replay 证明共享 `GlobalMarketState + AssetDelta` 不会串状态；
4. 先定义 provider/model-independent routing config，再选择具体模型；
5. 多模型实验必须开新版本、新 cohort，不与 V3.4 单模型样本混算。

在上述门通过前，V3.4 始终只运行一个战略模型/一次 4H committee，不存在 Manager Agent、模型投票或 Agent 间对话。
