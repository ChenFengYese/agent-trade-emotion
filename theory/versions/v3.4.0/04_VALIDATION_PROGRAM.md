# V3.4.0 分阶段验证计划

## 1. Stage A：FORECAST_ONLY

当前已实现 harness，未进行市场有效性裁决。每个固定 4H PIT cutoff 冻结：

- 4H / 12H / 24H expected direction 与 path；
- target zone / invalidation；
- 15m/1H/4H/1D zones；
- trend phase、主/替代因果、人群、event、sentiment、data conflicts；
- next discriminating observation 与 state change。

reference price 必须在原 4H context 内冻结。未来推进后，Outcome 必须引用 admitted source、保持同一 reference，并在精确 +4H/+12H/+24H 时点记录 close/high/low，确定性评价 direction match、target touch、MFE/MAE。它只回答“Agent 是否会看市场”，不引入 fill、fee、stop 或动态仓位噪声。

Stage A 主样本优先严格 PIT historical replay；实时 scheduled run 只验证在线迁移。不能因 outcome 已知回写 forecast。

## 2. Stage B：FROZEN_PLAN

只有 Stage A 达到事前定义的跨 regime/baseline 门后才开放。Agent 在 4H committee 一次性制定 entry、CORE invalidation、catastrophic protection、quantity、targets、HARVEST/RUNNER 和预授权 intra-window 条件；下一 committee 前 LLM 不修改计划。

对照至少包含：`ALWAYS_FLAT`、简单 4H trend/breakout、Agent forecast-only、Agent entry + frozen management。

这一阶段回答“原始方向与冻结计划是否有 edge”。

## 3. Stage C：DYNAMIC_MANAGEMENT

只有 A/B 合格后才测试新的 committee 是否能通过 HOLD/ADD/REDUCE/HARVEST/EXIT/REENTER 提高相对 frozen shadow 的结果。每个 episode 保留不可写回的 frozen shadow，评价：避免损失、HARVEST floor、runner right-tail、ADD 增量、过早实现亏损、低周期预授权动作的收益/损害。

动作次数不是 KPI。条件没发生时长期 WAIT/HOLD 是合法最优结果。

## 4. 样本与结论边界

12 episode 可发现明显 churn/风控/执行错误，不足以证明长期盈利。最终结论需要更多跨 regime PIT 样本、简单 baseline、成本敏感性和未触碰窗口。

## 5. 当前停止线

- r3/E-025 永久只读，不补样、不回填、不与 V3.4 混算；
- FORECAST_ONLY 已具本地 runtime identity，但尚无市场能力结论；
- paper/testnet/live 均未授权；
- Stage B/C 未完成前，不能把 strategic semantics checker 描述为已验证交易系统；
- 未来多模型 Manager 必须开 Post-V3.4 新版本与新 cohort。
