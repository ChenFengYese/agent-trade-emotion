# RSI-MTF-DRL-PM Theory Challenger v0.3.0 验证报告

> 日期：2026-07-23
>
> 总体结论：`V3-A PASS / V3-B REPAIR_COMPLETE_AWAITING_SOL_GATE / LOCAL_HISTORICAL_NOT_RUN`
>
> 证据等级：`E0`
>
> 允许声明：外部证据、机制、可观测量、候选规则、控制组和反证条件已形成可审计闭环；V3-B 修复已完成，等待独立 Sol 阶段门审核。
>
> 禁止声明：BTCUSDT 市场有效、预测有效、成本后盈利、paper 可用或实盘可用。

## 1. 审计范围

本轮只完成：

1. 权威网络资料检索和相反证据检索；
2. 来源到机制、观测量、规则、控制和反证条件的逻辑审计；
3. 独立 v0.3 challenger 理论文档；
4. outcome-free P0 假设注册；
5. 文档、注册表和权限边界的机械测试。

本轮没有：

- 改动 `RSI-MTF-DRL-PM v0.2.2` champion；
- 改动活动 G1 package、plan、registry 或 evidence；
- 读取新的历史 outcome；
- 建立历史 source adapter；
- 运行回测、校准、holdout、paper 或实盘交易。

## 2. 当前权威边界

工作区：

- 路径：`/Users/wt/Documents/agent-trade-emotion`
- 分支：`codex/s0-research-foundation`
- HEAD：`7ca3fc4f99a57f98217e703f222b295653ace87e`

冻结 champion bytes 复核：

| 对象 | SHA-256 | 结果 |
|---|---|---|
| `RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md` | `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6` | 未变 |
| `RSI_MTF_DRL_PM_AUTHORITY_BUNDLE_SPEC_v0_2_2.md` | `9b2446de9e0549579d52bc8ce2bc3bd124885203a52855f0dbf0f1324f9f1295` | 未变 |
| `config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json` | `631f8187e9eb81465718156736045c3ca5cc7ec5e33bbba7b063354cefeb792c` | 未变 |
| `config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json` | `26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc` | 未变 |

活动 G1 权威 bytes 复核：

| 对象 | SHA-256 | 结果 |
|---|---|---|
| `forward_capture_plan.g1.v1.json` | `189317fdff53d9f0ca64747d48690a283a3328b04df539f53307eb1370c3cb6d` | 未变 |
| `source_registry.v3.json` | `b3848092824dc65e9fea6ac524811453b8abf4783b865d8c057089cb5603453f` | 未变 |

活动 G1 最近一次实际状态仍为：

- `action = RESOURCE_BLOCKED`
- `decided_at = 2026-07-23T12:00:02.385472+00:00`
- `missed_slots = 2`
- `pending_slots = 25`
- `reason = FREE_BYTES_BELOW_FROZEN_MINIMUM`
- `free_bytes = 6,827,732,992`
- `min_free_bytes = 16,106,127,360`
- `plan_bytes = 0`

这是采集资源约束，不是市场证据，也不是授权修改活动 G1 的理由。

## 3. 新增证据对象

| 对象 | SHA-256 | 状态 |
|---|---|---|
| `RSI_MTF_DRL_PM_THEORY_CHALLENGER_v0_3_0.md` | `572fdccfa9e9025c413df141a079d5420da2a4b73a84fa33f33ea77a4c921113` | `E0 / THEORY_CHALLENGER_ONLY` |
| `config/rsi_mtf_drl_pm.theory_challenger.v0_3_0.hypothesis_registry.json` | `0c7b8ee097aa11af95e1b02fe7d6253cad566de41f407b0c522d416123b6ab29` | `OUTCOME_FREE_REPAIR_COMPLETE_AWAITING_SOL_V3_B_GATE` |
| `tests/test_rsi_mtf_drl_pm_theory_challenger_v0_3_0.py` | `d5ca9f23ac02fde8f9344c3b3fc8265f0c1fe0501e03035d1c110bd0c64bcca6` | 机械验证 |

## 4. 外部证据审计结果

| 领域 | 一手来源给出的有限支持 | 不能外推的内容 | 在 v0.3 中的处理 |
|---|---|---|---|
| 技术/K 线 | Lo、Mamaysky、Wang 给出可统计定义形态的方法 | 不能证明命名形态在 BTCUSDT 可盈利 | 只保留确定计算特征；命名蜡烛形态降为 negative control |
| 趋势 | Time Series Momentum 提供跨资产历史趋势证据 | 不能把月度、多资产结果直接搬到 15m/4H BTC | H01 只做逆势 RSI 交易 veto，不自动开顺势单 |
| 动量尾部 | Momentum Crashes 表明趋势/动量存在状态依赖和崩溃风险 | 不能假定趋势永久延续 | 加入反向、时移控制和尾部指标 |
| 点位 | Osler 的机构外汇水平研究支持“水平可能影响盘中行为” | 不能证明主观点位、整数位或精确单价必然反转 | H04 使用确定区间，并与随机区间、时间匹配和简单区间比较 |
| 订单流 | Cont、Kukanov、Stoikov 支持订单簿事件与短时价格变化关系 | 主要证据偏同期解释；不能把 aggTrade 当完整 OFI | H02 必须用连续 diff-depth、本地簿和未来窗口测增量 |
| 队列不平衡 | Gould、Bonart 支持特定市场的一跳预测 | 效果依赖 tick regime，不能直接迁移 | 只作为确认/否决特征，禁止独立入场 |
| 做市商视角 | Glosten-Milgrom、Avellaneda-Stoikov 支持逆向选择、库存和报价权衡 | 不支持推断“做市商真实意图”或把做市模型当方向 alpha | 仅用于执行质量、库存风险和 adverse selection |
| 执行 | Almgren-Chriss 提供冲击与时机风险的优化框架 | 小额加密永续执行仍需本地估计 | 所有候选共用冻结成本、延迟和 fill 模型 |
| 波动管理 | Moreira-Muir 支持部分组合的波动率管理 | 后续研究存在跨策略反例，不能视为普适 alpha | H05 只作为风险几何 challenger |
| 止损 | Kaminski-Lo 表明止损价值取决于收益过程 | 止损不是普适盈利来源 | H06 比较同一入场/成交 cohort 的剩余 EV |
| 多重检验 | White Reality Check、Hansen SPA 和技术规则 data-snooping 研究表明搜索会制造虚假优胜者 | 单一最好回测不能证明有效 | 预注册、共享基线、block bootstrap、SPA/Reality Check |
| 加密数据 | Binance 官方文档和公共归档定义可取得的市场数据 | 字段存在不等于字段有 alpha | schema 事实与市场有效性严格分离 |

关键审计判断：

1. 外部历史研究只构成 prior 和 challenger 来源，不构成本项目 E1 证据。
2. 做市商理论是库存、逆向选择和执行理论，不是“庄家方向预测器”。
3. named candlestick、完整 market-making engine、full Kelly 和复杂深度模型当前均不进入 P0。
4. 任何未来历史实验必须保持 point-in-time 可得性，并把缺失、冲突或时序不可证的数据变成 `UNKNOWN/ABSTAIN`。

## 5. P0 逻辑链与顺序

每条注册假设都具备：

```text
一手来源
  → 有限机制
  → 决策时可观测字段
  → V3-C 待冻结 measurement contract/候选规则
  → 同机会集 champion control
  → 主要结果与指标
  → negative control/placebo
  → 明确反证条件
```

唯一允许的首轮顺序：

1. `V3-H01-TREND_VETO`
2. `V3-H02-OFI_INCREMENT`
3. `V3-H03-IMPACT_RESILIENCE`
4. `V3-H04-LEVEL_RESPONSE`
5. `V3-H05-VOL_LIQ_GEOMETRY`
6. `V3-H06-REMAINING_EV_EXIT`

约束：

- H01 只能 veto 逆势反转，不能创建顺势订单；
- H02、H03、H04 的 disposition 必须逐层记录，不能首次实验一起加入；H03/H04 的 predecessor 不要求 PASS，且各自只能对 V3-C 预注册、独立、不可切换的 comparator 比较；
- H05 只改变止盈止损与风险几何，不和仓位上限混测；
- H06 必须使用相同下单/成交 cohort，防止退出效果被入场变化伪造；
- registry `comparison_graph` 是唯一比较图：V3-L0–V3-L6 为理论层，不与 authority B1–B4 重名；禁止累计图和事后 comparator 切换。

## 6. 实际验证

### 6.1 机械测试

执行：

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_drl_pm_theory_challenger_v0_3_0
```

结果：`11/11 PASS`

已验证：

- 四个 champion SHA 与注册表一致；
- 六个 P0 ID 和次序唯一；
- source、mechanism、observables、control、outcome、metric 和 falsifier 完整；
- source ID 可解析；
- `AUTHORITY_B4_DATA_FEASIBILITY` 与其后的 `INDEPENDENT_DEVELOPMENT_GATE` 被严格分离：B4 不授予 outcome access/backtest，后者仍需独立 Sol 授权；
- paper/live 被禁止；
- 所有结果仍为 `NOT_RUN` 或 `WAIT_DATA`；
- 理论文档包含 E0 和 no-trade 边界。

### 6.2 现有权威回归

执行：

```text
/opt/homebrew/bin/python3.12 -B -m unittest -q \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_research_contract
```

结果：`33/33 PASS`

执行 `git diff --check`，结果：通过。

### 6.3 独立事实审查

Terra microstructure 审查结论：`PASS`

- 未发现 P0/P1 事实性错误；
- 文档正确区分同期 OFI 解释与未来预测；
- 文档正确声明 aggTrade 不等于完整 OFI；
- 文档把做市理论限制在逆向选择、库存和执行；
- 文档未把 Binance 官方字段存在误写成 alpha。

## 7. 历史验证为何未运行

当前 v0.2.2 authority 的精确阶段是
`B1_CANDIDATE awaiting independent Sol gate; B2 unauthorized`，且其 contract 明确禁止
market-data/historical-data
source adapter、读取新 outcome 或运行 backtest。绕过该门槛会造成：

1. 先看结果再修改假设；
2. DEVELOPMENT、CALIBRATION、HOLDOUT 角色污染；
3. 已见的一月、二月数据被错误称为独立验证；
4. 无法区分理论增量和重复搜索产生的偶然结果。

因此 `LOCAL_HISTORICAL_NOT_RUN` 是本轮唯一合规事实结论，不是缺少理论路线。

B4 前、且在 V3-B gate `PASS` 前，未授权任何新的 V3-C P0 实现。只有以下非执行性
事实准备可以保留：

- 官方文档的字段/schema 阅读与来源引用核对；
- 不接触真实市场 payload 的 synthetic schema 设计与文档化；
- 既有文档、配置和报告的 lineage 规范。

真实字段连续性审计、真实 adapter、真实 archive 或实际 data feasibility 必须等到 B3 后、
并经明确 `AUTHORITY_B4_DATA_FEASIBILITY` Sol 授权；它们不能被称为 pre-B4 schema 工作。

## 8. 阶段判定与下一路线

| 阶段 | 当前判定 | 下一门 |
|---|---|---|
| V3-A 权威资料与相反证据 | `PASS` | 保持来源和迁移风险可追溯 |
| V3-B outcome-free 理论/注册 | `REPAIR_COMPLETE_AWAITING_SOL_GATE` | 独立 Sol 复核权限、比较图、状态和 measurement-contract 边界 |
| V3-C synthetic 因果测试 | `FORBIDDEN_UNTIL_SOL_V3_B_GATE_PASS` | 仅在 V3-B gate PASS 后，才能进行不接触真实市场 payload 的时序/缺失测试 |
| V3-D pre-B4 synthetic/schema-design | `NOT_RUN` | 仅官方文档与合成 schema 设计；不做真实字段连续性或 adapter 审计 |
| V3-D real data feasibility | `FORBIDDEN_UNTIL_POST_B3_AUTHORITY_B4_DATA_FEASIBILITY_GRANT` | 真实字段连续性、真实 adapter/archive/availability/cost feasibility 需 B3 后独立 B4 Sol 授权 |
| AUTHORITY_B4_DATA_FEASIBILITY | `REQUIRES_NEW_SOL_AUTHORIZATION` | 最多允许独立 adapter/schema/availability/cost feasibility，不能读取 outcome 或回测 |
| INDEPENDENT_DEVELOPMENT_GATE | `FORBIDDEN_UNTIL_SEPARATE_POST_B4_SOL_AUTHORIZATION` | 在 B4、adapter contract、日期角色和成本冻结后，才可能单独授予 outcome/backtest |
| V3-F CALIBRATION/HOLDOUT | `FORBIDDEN` | DEVELOPMENT 通过后逐门推进 |
| paper/live | `FORBIDDEN` | 不在当前路线内 |

最小下一 P0：

1. 独立 `Sol V3-B gate`；此 gate 未 PASS 前，不启动 V3-C、真实 schema/字段连续性、adapter 或 B4 申请。
2. 只有 `Sol V3-B gate = PASS` 后，V3-C 才成为下一 P0；B4 仍不是自动可申请的状态。

## 9. 最终结论

本轮已完成 V3-B 权限、比较图、状态、反面证据和 measurement-contract 边界的修复；
当前判定只能是 `V3-A PASS / V3-B REPAIR_COMPLETE_AWAITING_SOL_GATE`。它把
“RSI 触发后如何解释趋势、选择点位、确认订单流、设置动态 TP/SL 和处理执行风险”
转化为六条可反证候选。

当前仍没有本项目历史市场证据，因此 v0.3 不能替换 v0.2.2，不能进入 paper
或实盘。当前唯一下一 P0 是 `Sol V3-B gate`；只有 PASS 后才能启动 V3-C synthetic
因果验证，绝不能提前读取历史结果、实施真实 adapter 或申请 B4。
