# 当前系统状态

> **2026-08-02 读取说明：**本文保留为 2026-08-01 的机器能力和证据快照，不再承担当前研究优先级入口。当前目标、V1 事故后的研究问题、停止方向和最小后继实验，以 [`PROJECT_CORE_GOAL_RELOAD_2026-08-02.md`](./PROJECT_CORE_GOAL_RELOAD_2026-08-02.md) 为准；新窗口按 [`NEXT_WINDOW_RESEARCH_AGENT_PROMPT.md`](./NEXT_WINDOW_RESEARCH_AGENT_PROMPT.md) 恢复。此说明不修改本文绑定的历史事实或冻结工件。

状态日期：2026-08-01
机器可验证覆盖层：[`config/current_system_status.v1.json`](./config/current_system_status.v1.json)
验证器：[`trade_system/current_system_status.py`](./trade_system/current_system_status.py)

本文是 2026-08-01 机械状态快照。历史 challenger、审计、gate、终态记录和冻结 contract 保留其原始字节与当时语义；本文只依据截至该日的精确决策解释其机器状态，不回写历史证据。

## 结论

当前仓库是一个版本化的理论研究基线。2026-07-30 曾新增一条与旧治理域隔离的 paper-only 理论实践通道，但该 V1 实验已由用户终止且未达到验收标准；其 automation-2 保持暂停。当前 successor 是 `Theory Agent V2` 的 E0 离线反事实实现，不具有 paper 或 live 执行权。仓库不能把本地契约、合成测试、历史回放或纸面收益表述为市场真理、预测有效性或稳定盈利证明。

当前 Core 是 `CORE_TRADING_THEORY.v2.1`。根镜像 [`CORE_TRADING_THEORY.md`](./CORE_TRADING_THEORY.md) 与版本文件 [`CORE_TRADING_THEORY_v2_1.md`](./CORE_TRADING_THEORY_v2_1.md) 必须保持相同字节和摘要。

## Theory Agent V2 当前状态

- canonical implementation contract v1.0、142 个 schema、全部 registry、三个互斥 role skills、12 个确定性内核组件和四层 E0 runtime 已物化。
- 动态市场职责由 Proposer、Challenger、Selector 的有界一次调用承担；PIT、计算、约束、状态、撮合、风险、事件链和唯一提交仍由确定性系统独占。
- 第一轮只读回放严格使用 V1 cycle-0001 至 cycle-0024；A 组账本、动作和成交可精确复算，V1 源树摘要未变化。
- 32 个 canonical 功能场景全部通过；这只证明注册的不变量实现闭合。
- B–I 所需的事前持久战略状态、CORE/TACTICAL 角色、重入合同、动态几何和完整统一候选流在 V1 中不存在，不能用后续上涨或事后提案补造。因此第一轮终局为 `INCONCLUSIVE_NO_ADVANCE`。
- 严格 transport-attested 的等服务模型/等 token 预算证据仍不存在。但原生 Codex practical 拓扑实验已在权威 run `native-codex-e0-btcusdt-20260801T043054Z` 完成 32/32 组、192 份语义输出、32 个链式事件与确定性评估；manifest digest=`d1bb654f4a4dfa4a64eb2aeac2c903d56ca5cbcd0d4cded7a53aa9fdcd0495c2`，result digest=`b2fa08eb9dac647c6949c8c405a6ecb2eae55a7e654ed286fb8a7239c8b2d28d`，最终 verify 为 context/event 双 PASS。冻结选择状态是 `PRACTICAL_CLUSTER_PREFERRED`：集群的平均挑战覆盖率为 0.984375，单 Agent 为 0.6354167，平均综合分分别为 0.9895833 和 0.8706597，两臂硬动作错误均为 0。
- 该 practical 偏好只证明盲挑战与独立选择提高了结构化审查覆盖，没有证明动态交易行为或经济结果改善：两臂的 32 次选择完全相同（`HOLD_STATE` 31、`WAIT_FLAT` 1），一小时诊断净收益、交易成本和主路径捕获也完全相同。因此实验完成目标已达成，但“集群已改善持仓/加仓/重入/收益”的目标未被建立。
- 第二轮与 `ceil_to_tick(1.01 × genesis_mark)` 外生初始成本设置均未创建，也没有新自动任务。完整状态与冻结进入合同见 [`requirements/2026-07-30-theory-paper-practice.md`](./requirements/2026-07-30-theory-paper-practice.md)。

## 尚未完成或未获授权

- 原生 Agent practical 拓扑实验已完成；结果与不可重跑的本地状态入口见 [`HANDOFF.md`](./agent-cluster/experiments/native-codex-e0-20260731/HANDOFF.md)。尚未完成的是能够识别动作与经济差异的后续冻结实验，不得用本次挑战覆盖提升代替。
- 严格服务模型身份与精确 token 预算的 transport-attested 实验证据仍不存在；本次本机原生协作结果不能提升为该证据等级。
- Theory Agent V2 第二轮本地 paper 实验、101% 外生成本实例、自动任务和任何账户连接均未创建或授权。
- HAR1R5 仍只有静态 gate；真实数据许可、D0、合格数据集、样本外预测增量、成本后正期望和生产/实盘许可均未建立。
- `.runtime/` 只保存本机可恢复状态且不进入 Git；当前提交用于版本化代码、合同、设计和恢复说明，不把本地运行记录转化为发布证据。

完整工作区交付边界见 [`WORKSPACE_CHECKPOINT_2026-07-31.md`](./WORKSPACE_CHECKPOINT_2026-07-31.md)。

## 决策时间线的当前解释

- Dynamic Hypothesis Graph P0.1：后续 gate 已接受精确绑定的 E0 包。challenger 或 inventory 文件头中的“候选、待 gate”是 gate 发生前的历史状态，不能覆盖后续 `ACCEPT_P0_1`；该接受没有把 challenger 提升为 Core，也没有证明市场有效性。
- PIT Authority Replay：精确 E0 contract 包已接受；真实 source、D0、adapter/replay、数据集与市场有效性仍未由该 E0 gate 建立。
- SD0 R8：曾授权一个有期限、同进程 capability 约束的七请求元数据路径；该 capability 已于 `2026-07-29T17:21:36Z` 到期。后续证据文件可能已经存在，所以测试只应证明生产入口没有改变工作区字节，不能继续假设“证据永远不存在”。
- HAR1R4：四个请求的封存清单为 `FAILURE`；repository 是 `WAIT_DATA_SOURCE_CONTRACT_MISMATCH`，terms 是 `WAIT_DATA_TERMS_D0_DENIED`，`legal_conclusion=false`。这批结果没有建立 source、terms 或法律权限。
- HAR1R5：当前只获准创建静态 gate 文件，状态是 `AUTHORIZE_HAR1R5_STATIC_GATE_ONLY_NO_NETWORK`；网络、activation、data、backtest 与 trading 均为 `false`，且尚无 R5 evidence manifest。
- Active G1：冻结计划已进入 `TERMINAL_WAIT_DATA_PLAN_UNREACHABLE`，不得回填、降低门槛或把工作区包覆盖到活动包。
- 2025-02 历史诊断：版本化 A2F1 决策是 `FEB2025_TERMINAL_WAIT_DATA_NOT_SCORED`，执行门是 `HOLD_BEFORE_ANY_NEW_ACQUISITION_OR_SCORING`；版本化 terminal-SEEN 守卫保持 `ACTIVE_FAIL_CLOSED`。旧下载器的 fake-transport 测试只能在显式 test-only 隔离夹具中检查终态前机械行为，不能放松生产守卫。

这些状态由 [`config/current_system_status.v1.json`](./config/current_system_status.v1.json) 对精确决策文件做物理摘要绑定并交叉验证。

## RSI v0.2.2 哈希漂移处理

RSI v0.2.2 是不可变历史包，它声明的 Core v2.0 摘要为：

```text
06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d
```

当前根 Core 已升级为 v2.1，因此不能再直接把当前根目录当作 v0.2.2 的原始 workspace。修复方式是：

1. 不修改 v0.2.2 strategy contract、route decision 或其 expected raw bytes。
2. 将原 Core v2.0 精确字节保存在 [`archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md`](./archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md)。
3. 将被 route decision 绑定的旧 validator test 精确字节保存在 [`archive/authority/tests/test_rsi_research_contract.v0_2.py`](./archive/authority/tests/test_rsi_research_contract.v0_2.py)。
4. 测试把全部 14 个冻结输入复制到临时 workspace，在原路径恢复历史 Core 和旧测试；基线验证通过后才进行单项篡改并确认 fail-closed。

这证明的是“旧包精确字节可复现”，不是把旧 Core 重新设为当前 Core，也不是证明 RSI 方法有市场收益。

还需区分“物理历史字段”和“后续路线状态”：冻结的 v0.2 research contract 文件本身仍写 `REVIEW_READY / REJECT_FREEZE`；后续 v0.2.2 Route B 当前状态是 `SOL_ROUTE_B_ADOPTED / AUTHORITY_BUNDLE_CONTRACT_DRAFTING`，原 Direct AST 被标为 `HISTORICAL_REWORK_NON_AUTHORITY`。因此不能用历史文件中的 `REVIEW_READY` 覆盖后续路线结论，也不能把 Route B adoption 解释为 contract freeze、市场验证或交易授权。

## 当前可做与不可做

旧 hash-bound 研究域当前可做：

- 读取和复验精确 E0 contract、合成 fixture、决策链和已有操作证据。
- 在隔离 workspace 中复现 RSI v0.2.2 历史包。
- 维护状态覆盖层、测试夹具和发布验证。

旧 hash-bound 研究域仍不可据此做：

- 将 E0、合成 PASS 或一次受限 SD0 请求解释为市场、预测或盈利有效。
- 回填 active G1，绕过 February terminal guard，或自动继承 D0/adapter/replay/backtest/paper/live 权限。
- 发起真实交易。

已终止的新理论 V1 paper 实践通道在运行时的历史边界是：

- 只使用公开数据和本地纸面账户，不读取交易凭据，不提交真实订单。
- 当时可在本地纸面账户提出、执行、否定和复盘新理论假说；该授权不延续到 V2 或新的自动任务。
- 可以使用旧系统的数据、回放、风险和审计能力作为支持，但不能把旧 gate 的限制或旧策略语义冒充为新理论结论。
- 所有既有结果仍只是实验性 paper evidence；当前不得继续提交 pending cycle、启动第二轮或恢复 automation-2。

## 运行与发布要求

项目支持的 Python 范围统一为 `>=3.11,<3.14`，主验证运行时为 Python 3.12。Python 3.9 不再属于声明支持范围。

发布结论必须绑定一个版本化 commit，并满足机器状态覆盖层验证、完整测试套件和目标 paper 核心路径验证。实时脏工作区、单个 README、历史审计快照或仅有局部测试通过都不能单独称为可发布版本。

`.runtime/` 中的本地运行记录继续用于机器内操作审计，但被 Git 忽略，不是可发布版本的权威链接目标。February 当前发布态由版本化 [`A2F1 决策`](./config/sol_decision.s0-009-r1-acquisition-gap-censoring.a2f1.json) 与 [`A3E1 terminal guard`](./config/s0_009_february_terminal_seen_guard.a3e1.json) 共同证明；运行态文件只能作为二者绑定的本地补充。

状态覆盖层定向验证：

```bash
python3.12 -m unittest tests.test_current_system_status -v
python3.12 -m unittest \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_research_contract \
  tests.test_historical_diagnostic_guarded_download \
  tests.test_pit_authority_replay_sd0_metered_fetch_v1 -v
```
