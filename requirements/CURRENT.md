# 当前需求：V3.4 定时低频战略 Trading Agent

更新日期：2026-08-17

状态：`V4.0.0 DECISION+TRADE-PLAN BASELINE IMPLEMENTED / NON-EXECUTABLE / NO PAPER-TESTNET-LIVE AUTHORITY`

## 结论

r3/E-025 已永久只读关闭，3 个合格成交 episode 为 0 胜 3 负、3/12，保持 `MEASUREMENT_INSUFFICIENT`。V3.4 不再把 LLM 当作 continuous-goal 在线交易控制器，而是固定 4H 委员会式战略分析器：UTC `00/04/08/12/16/20` 才拥有新的市场判断权；1H/15m/更低周期只提供 4H 内部证据，不能自行唤醒 LLM 或临时改变 thesis。

用户确认 continuous-goal 的主要失败表现包括极端 token 消耗、上下文丢失、注意力漂移、指令遵循衰减、错误市场激活、短周期权重膨胀和无效重复分析。单币种 Sol Max 约 `8e8 token/day` 仅作为已观察到的失败症状，不作为未来预算预测。

## 当前 V3.4 权限

- `MIN_DECISION_HORIZON = 4H`；1H/15m/5m/tick 均无独立 LLM 交易决策权。
- 外部确定性 scheduler 决定 4H wake；Agent 无权把“30 分钟后再看”变成新 wake。
- 两个 committee 之间 LLM 不得形成新 thesis 或修改仓位；本地执行器未来只可机械执行上一 committee 已冻结的 OPEN/ADD/REDUCE/HARVEST/EXIT 条件，安全系统只可 emergency de-risk。
- 4H+ 仓位必须能承担等待到下一 committee 的压力风险；strategic invalidation、catastrophic protection、gap/impact stress、maximum-loss budget 与 quantity 由确定性 Decimal 复算。
- realized/unrealized PnL 分离；普通 15m/1H break 不得单独全平 4H CORE。
- 任何合法 Agent 原文仍可保存；增加 exposure 另需 `STRATEGIC_SEMANTICS_READY`，系统不得替 Agent 选择 LONG/SHORT 或补造观点。

## 已实现

1. V3.4 理论增量与 `strategic_control.py`：四周期权限、趋势/因果/替代、人群/事件/情绪、data quality/conflicts、future-space、WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT、tranche/runner、PnL 与风险收益复算。
2. 固定 4H `scheduled_strategy.py`：committee slot、FORECAST_ONLY 语义、intra-window authority、低 token context 和 4H/12H/24H objective outcome evaluation。
3. Durable Strategic State：`strategic_state_repository.py` write-once 按资产/4H slot 保存 forecast/outcome/evaluation；下一轮只带一个 previous-state summary + 当前 delta，不灌完整历史。
4. `forecast_qualification.py` 与 `v34-forecast`：本地、公开/合法准入 PIT 摘要的不可执行 FORECAST_ONLY context/seal/outcome/latest 路径；无账户、paper、testnet、live 或外部订单能力。
5. 上下文默认 canonical byte ceiling `64 KiB`，并绑定 current theory identity、asset、PIT reference price、slot、size/SHA，防止跨币种串线或构建后上下文漂移；forecast seal 可记录 provider 实际 input/output/cached token usage，不可得时保持 `UNKNOWN`，不使用字节数伪装 token。
6. Post-V3.4 多模型 Manager Agent 规划已单独建立：按费用/能力路由 Context Worker、Routine Analyst、Senior Strategist、Reviewer，并通过有界 artifact dialogue 对接；**当前 V3.4 不导入、不运行该设计**。

## 验证顺序

1. `FORECAST_ONLY`：当前 harness 已实现；下一项市场工作是严格 PIT replay/前瞻样本，验证 4H/12H/24H 路径，而不是交易。
2. `FROZEN_PLAN`：仅当 Stage A 达到事前验收后才实现/授权；冻结 entry/CORE invalidation/quantity/targets/harvest/runner，并与简单 4H baseline 比较。
3. `DYNAMIC_MANAGEMENT`：前两阶段通过后才开放；每个 episode 保留 frozen shadow，测 WAIT/ADD/REDUCE/HARVEST/EXIT 的真实增量价值。

## 当前边界

- 不继续 E-025，不回填 BJ/BC/U，不恢复 r3 heartbeat，不改关闭 runtime。
- 不读取私有账户、不使用凭据、不发送 paper/testnet/live/外部订单、不移动资金。
- 当前 V3.4 forecast runtime 不是交易 runtime，不能用工程 PASS 表述市场有效、盈利或 paper authority。
- Post-V3.4 多模型 Manager Agent 仅规划；任何启用必须新版本、新 cohort，不能污染 V3.4 单模型证据。

## 当前验收

当前工程阶段完成标准：固定 4H 时间权限、Durable Strategic State、FORECAST_ONLY harness、低 token/跨资产上下文边界、战略语义/算术门和未来多模型管理规划均已实现并有最小合同验证；旧 r3 保持只读。市场有效性仍为 `UNKNOWN`，只能由新的严格 PIT Stage-A 样本回答。

## V4.0 增量

V4.0 将已暴露的 Stage 4 问题正式纳入当前决策规范：风险预算/结构止损/压力损失/尾部风险闭环、事件定义、竞争假说更新、路径调整PR、成本后EV、执行不确定性、Probe/Lead/Main 状态、动态仓位质量、Canonical/Adversarial/Mutation/Repeatability 基准。

同时新增 `trade_system/v4_decision/` 非可执行交易层：将分析结论转化为明确的 LONG/SHORT/WAIT/NO_TRADE/REDUCE/EXIT/REENTER 交易计划，并提供风险仓位计算、压力风险和情景EV计算。该层不拥有账户、凭据、订单或资金权限。

## 下一步

进入分析 → 交易计划阶段：首先使用严格 PIT 公开数据验证 V4.0 分析与交易计划在 Canonical/Adversarial/Mutation/Repeatability 情景中的决策一致性；随后才评估是否有必要开启独立的 paper authority。V3.4 `FORECAST_ONLY` runtime 保持只读，不恢复 continuous-goal。
