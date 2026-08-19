# V3.4.0 修订范围与 r3 结论

## 1. 为什么不是继续微调 V3.3.2 r3

r3 已证明缩量、不反转和执行保护能够工作，但没有证明盈利。更关键的是，三个真实成交 episode 与约 25 小时 continuous-goal 暴露同一落地缺陷：高周期语言存在，真实认知与 position authority 却持续沉到 15m/局部阈值；WAIT、阶梯 ADD/REDUCE/HARVEST、realized/unrealized、完整人群/事件/未来路径没有稳定进入真实决策。

因此本次修订不把问题简化成“stop 再放宽一点”，也不把 0 胜 3 负解释为 V3.3.2 已被市场最终证伪。V3.4 修复的是 Agent 角色、时间权限、上下文和 theory operationalization。

## 2. 继续继承的能力

继续继承 V3.3.2 的 PIT、竞争假说、event-clock path、CORE/TACTICAL/HEDGE/PROBE/RUNNER、PositionDelta、tranche、partial harvest、runner、动态 stop/target/reentry、完整合法动作集，以及“系统不能替 Agent 选择市场方向”的原则。

## 3. 当前新增硬约束

1. `MIN_DECISION_HORIZON = 4H`；固定 UTC 4H scheduler 是唯一普通 LLM market-decision wake authority。
2. 1H/15m 是 4H 内部证据；不能因一根低周期 bar 单独唤醒 LLM 或终止 CORE。
3. active/待开 CORE 必须维护 15m/1H/4H/1D 区域、趋势阶段及各层证据含义。
4. position decision 必须区分 realized / unrealized；退出、减仓、HARVEST 要明确改变了什么已实现结果和右尾机会。
5. exposure-increasing decision 必须有未来空间、strategic invalidation、catastrophic protection、等待下一 committee 的压力风险、成本和最大损失预算。
6. WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT 必须比较；有仓位/计划 exposure 时必须预注册条件化数量，计划冻结到下一 4H committee。
7. 人群、事件/消息、情绪/定位、data quality/conflicts 显式出现；无法区分时保持 UNKNOWN。
8. 长期状态使用 latest StrategicState + delta；禁止 continuous-goal 通过旧对话不断堆上下文。

## 4. 对“只能时钟唤醒”的调整

V3.4 接受“LLM 只能按 4H 时钟形成新市场判断”，但不把 intra-window 变成完全静止：上一个 4H committee 可以事前授权 bounded OPEN/ADD/REDUCE/HARVEST/EXIT 条件，本地 executor 可机械执行；这不是新 thesis。emergency safety 独立，只允许 de-risk。

这样同时解决两个矛盾：既不让 15m/1H 重新获得 Agent 决策权，又保留你要求的阶梯加减仓、利润保护和 runner。

## 5. 不允许的错误修复

- 不固定 5%/10% stop；stop 先由高周期结构决定，距离扩大时 quantity 下降。
- 不把 ATR 倍数变成 universal rule。
- 不把“15m/1H 破位=全平”或“浮盈=全平”编成系统策略。
- 不让 scheduler 读取 Agent 的“下一次什么时候醒”。
- 不让系统选择 LONG/SHORT 或把语义缺口改写成 WAIT。
- 不用第二个常驻监督 Agent 修复第一个 Agent；多模型仅作为 Post-V3.4 未来规划。

## 6. cohort 边界

E-025 r3 的 3 个合格 episode 与 V3.4 不可混样。V3.4 当前只实现 FORECAST_ONLY runtime；任何 FROZEN_PLAN、DYNAMIC_MANAGEMENT 或 paper 权限都必须 fresh cohort。
