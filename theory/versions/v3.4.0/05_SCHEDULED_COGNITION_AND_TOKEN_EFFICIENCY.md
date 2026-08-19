# V3.4.0 定时认知、上下文与 Token 效率

## 1. 时间权限是系统 invariant

V3.4.0 当前采用固定 UTC 四小时委员会：

```text
00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00 UTC
```

`4H` 是最小市场决策周期，不是“主要参考周期”。`1H/15m/5m/tick` 可以提高对过去四小时内部路径的分辨率，但不能在两个 committee slot 之间唤醒 LLM 形成新 LONG/SHORT、反转或临时退出 thesis。下一次 LLM 市场决策时间由确定性 scheduler 计算，Agent 的“30 分钟后再看”等建议没有调度权限。

信息分辨率与动作权限必须分开：

```text
Information: tick → 5m → 15m → 1H → 4H → 1D → higher
Decision:                         4H → 1D → higher
```

## 2. 两个 slot 之间发生什么

LLM 在完成一个 4H committee 后停止。确定性系统可继续采集、封存、估值和执行已经冻结的计划，但不重新解释市场。

允许的 intra-window 行为分三类：

1. `LLM`：只能保持 `WAIT/HOLD` 认知状态；无权修改仓位或生成新 thesis。
2. `LOCAL_EXECUTOR`：只能执行上一个 4H committee 已明确预授权的 OPEN/ADD/REDUCE/HARVEST/EXIT 条件；它不能修改条件或发明新方向。
3. `SAFETY_SYSTEM`：只有预注册 emergency 才可 `HALT/CANCEL/REDUCE/EXIT`，永远不能增加 exposure。

因此，“动态管理”仍存在，但动态的是**冻结计划的条件执行**，不是让 LLM 每 15 分钟重新决定一次。这同时保留阶梯加减仓、HARVEST/runner 和灾难性保护，又消除 continuous-goal 的短周期漂移。

## 3. 4H thesis 必须能承担等到下一次 committee 的风险

如果一个仓位必须依赖“30 分钟后让 Agent 再判断”才能保持安全，那么该仓位不符合 V3.4。建立/增加 exposure 前除战略 invalidation 外，还必须计算：

```text
StrategicRisk
CatastrophicProtectionRisk
LossIfWaitToNext4HCommittee
MaximumLossBudget
```

止损距离扩大时必须通过 quantity 缩小保持账户风险预算，不允许把 4H thesis 的保护塞回普通 15m/1H noise。灾难性保护是 fail-safe，不保证实际 fill 一定等于触发价，因此还要包含 gap/impact stress。

## 4. Durable Strategic State 取代长对话记忆

每个资产只携带一个最新战略状态和当前四小时 delta，不重复灌入几十轮旧 Decision。最新状态至少保留：

```text
previous state identity
4H committee time
regime / trend phase / directional bias
causal thesis / strong alternative
participant / catalyst / sentiment / data conflicts
15m/1H/4H/1D zones
4H/12H/24H forecast paths
next discriminating observation
state change: KEEP/STRENGTHEN/WEAKEN/INVALIDATE/REPLACE
```

历史 forecast/outcome 保持 write-once，可用于 replay/evaluation；它们不是每次 prompt 的默认上下文。

## 5. 当前低 Token 上下文协议

当前 context packet 只包含：

```text
shared_context_summary
asset_delta_summary
portfolio_summary
latest StrategicState summary (最多一个)
immutable source refs
time authority / theory identity
```

默认最大 canonical context 为 `64 KiB`。packet 在 seal 前复验 asset、4H slot、canonical size 与 SHA，防止多币种串线和构建后 context drift。这是字节预算，不冒充固定 token 数，因为不同模型/tokenizer 的 tokenization 不同。超过预算必须先删重复内容、引用 raw 或进一步压缩 delta，不能自动扩大 prompt。

reference price 与当前 theory identity 在 context 构建时一起冻结，seal 不能重新提供另一套价格/版本。若调用侧能取得 provider 实际 usage，forecast record 记录带 provider receipt/source ref 的 `input_tokens / output_tokens / cached_input_tokens`；取不到则明确为 `UNKNOWN`，不得由字节数反推一个伪精确 token 账单。

理论全文也不应每次重复发送。运行上下文只需要冻结 theory identity、当前关键规则与必要引用；若 Agent 需要查证某一理论细节，再按引用读取对应 owner，而不是把整个理论包复制六次/日/资产。

## 6. FORECAST_ONLY 当前实现

当前 V3.4 只实现不可执行的 scheduled forecast harness：

```text
build bounded context
→ fixed 4H Agent forecast
→ durable StrategicState
→ 4H/12H/24H future outcome
→ objective direction/target/MFE/MAE evaluation
```

它不读取账户、不创建 paper intent、不调用 testnet/live、不拥有外部订单能力。`FROZEN_PLAN` 与 `DYNAMIC_MANAGEMENT` 仍必须在 Stage-A forecast 能力通过后另行开启 fresh cohort。

## 7. 多币种与多模型边界

V3.4 当前仍是单战略模型，不启用管理 Agent 或 Agent-to-Agent 对话。未来多币种/多模型节流设计由 `design/POST_V34_MULTI_MODEL_AGENT_MANAGEMENT.md` 单独拥有；其任何规则都不得反向改变 V3.4 样本。
