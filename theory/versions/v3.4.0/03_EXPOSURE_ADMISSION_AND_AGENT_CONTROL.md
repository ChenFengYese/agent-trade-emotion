# V3.4.0 Exposure Admission 与 Agent 时间控制

## 1. 原文封存与 exposure 资格分离

```text
DECISION_SEALED
  = 保存 Agent 当时真实说了什么

STRATEGIC_SEMANTICS_READY
  = 该决策解决了承担/改变 exposure 所需语义与算术
```

系统不判断多空对错、不补造 WAIT、不改写原文。

## 2. Exposure 最低语义

增加/持有 exposure 时至少需要：4H+ horizon、15m/1H/4H/1D zones、trend phase、因果/强替代、两条 IF→THEN、人群、event/news、sentiment、data quality/conflicts、realized/unrealized PnL、future-space、WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT 比较、冻结 tranche plan、management matrix、activity profile，以及由确定性工具计算的 strategic/catastrophic/wait-to-next-committee risk 与成本后 payoff。

任一缺失可继续封存 Decision，但不得增加 exposure。

## 3. 固定 4H scheduler 是唯一普通 LLM wake authority

当前固定 UTC：

```text
00 / 04 / 08 / 12 / 16 / 20
```

Agent 不能输出新的 wake 时间让系统提前调用。1H/15m bar、局部浮盈回撤、普通 volume/OI 变化、activity HIGH 都不是 LLM wake 条件。系统可 24/7 记录证据，但到下一 4H slot 才把它们作为一个窗口的内部路径交给 Agent。

## 4. Intra-window 权限

```text
LLM:
  WAIT/HOLD cognition only

LOCAL_EXECUTOR:
  execute only frozen committee conditions
  OPEN/ADD/REDUCE/HARVEST/EXIT only when preauthorized

SAFETY_SYSTEM:
  emergency HALT/CANCEL/REDUCE/EXIT only
  never increase exposure
```

这保证“低周期提供分辨率，高周期拥有行为权限”。

## 5. Durable Strategic State

每个资产的最新状态至少包含：committee slot、direction/regime/trend phase、causal/alternative thesis、participant/event/sentiment/conflicts、四周期 zones、4H/12H/24H path、next discriminating observation、以及 `INITIALIZE/KEEP/STRENGTHEN/WEAKEN/INVALIDATE/REPLACE`。

状态以 asset + slot 为单位 write-once；latest 只读取同资产最近记录。previous-state summary 必须继续携带因果/替代、IF→THEN、人群、event、sentiment、data quality/conflicts、future-space、zones、horizons 与下一辨别观察，而不是退化成几个价格点。历史不作为下一 prompt 的默认全文，防止 context dilution。

## 6. 当前 FORECAST_ONLY runtime

`scheduled_strategy.py` 提供时间与 forecast 纯合同；`forecast_qualification.py` 只接受已经 admitted 的 compact summaries 和非空 source refs。reference price 在 context 构建时即冻结并进入 context digest，seal 不允许另传新价格；context 绑定当前 V3.4 theory identity、asset、slot、size 与 SHA。24h outcome 必须绑定同一 reference price、非空 source refs 和精确的 +4H/+12H/+24H observation time，之后才产生 direction/target/MFE/MAE 评价；`strategic_state_repository.py` 只写本地研究工件。

若 provider 可给出真实 token usage，forecast record 可保存带 source ref 的 observed input/output/cached token；不可得则保持 `UNKNOWN`，不从 byte size 推测 token。

该 runtime 没有 market collector、账户、paper intent、testnet/live order、credential 或 funds authority。它解决的是 Stage-A 认知验证和长期状态，不等于 V3.4 已获得交易权限。

## 7. 计算职责

确定性工具负责时间、slot、PnL、ATR/range/volatility、距离、最大损失、cost stress、MFE/MAE、runner/floor 等算术；Agent 负责解释、结构、未来路径和动作选择。基础乘法或 next wake 不再依赖 LLM。
