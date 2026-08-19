# 工作区地图

更新日期：2026-08-17

当前状态：V3.3.2 r3/E-025 已永久只读关闭并保持 3/12、0 胜 3 负；V3.4.0 固定 4H FORECAST_ONLY harness、Durable Strategic State、64 KiB bounded context、跨资产/context integrity 与战略语义检查已实现。当前没有市场实验或 V3.4 paper authority；下一研究只做 Stage-A 严格 PIT forecast qualification，未通过不进入交易阶段。

## 60 秒启动

1. 确认 [`AGENTS.md`](./AGENTS.md) 已加载；已自动注入时不要重复打开。
2. 并发时先按 [`coordination/README.md`](./coordination/README.md) 创建自己的工作文件并检查路径占用；单 Agent 工作时跳过。
3. 读 [`requirements/CURRENT.md`](./requirements/CURRENT.md)：整合后的当前需求、状态和验收标准。
4. 按任务类型选择一个入口：[`theory/CURRENT.md`](./theory/CURRENT.md)、[`design/CURRENT_BLUEPRINT.md`](./design/CURRENT_BLUEPRINT.md) 或 [`reviews/ERRORS.md`](./reviews/ERRORS.md)。
5. 只打开入口精确指向的源码、测试或历史证据；答案充分后立即停止扩读。

禁止默认扫描全仓文档、全部测试、旧 handoff、config、artifacts 或 archive。

## 当前权威

| 主题 | 唯一入口 | 内容边界 |
|---|---|---|
| 工作规则 | `AGENTS.md` | 效率、安全、文档、测试和数据规则 |
| 当前需求 | `requirements/CURRENT.md` | 当前交付、范围、状态和最新变更 |
| 并发协作 | `coordination/README.md`、每个 Agent 的独占工作文件 | 仅保存实时范围、路径所有权和待合并结果，不作项目权威 |
| 当前理论 | `theory/CURRENT.md` | V3.4 低频战略增量入口；未修改基础继续引用冻结 V3.3.2 |
| 低频战略工作法 | `.agents/skills/v340-strategic-trader/SKILL.md` | 4H+ 战略 Agent、四层区间、PnL 分离、动作比较和分阶段验证 |
| V3.3.2 历史工作法 | `.agents/skills/v332-autonomous-trader/SKILL.md` | 仅用于审查冻结 r3/V3.3.2 行为，不作为下一 cohort 默认路线 |
| HYPE 持续 Trading Agent | `traders/hype-trader/AGENTS.md`、`traders/hype-trader/state.json` | r3 恢复胶囊、formal obligations、最近样本与 12-episode cohort 索引；历史/假说只追加，正式五工件和 paper 事实仍在独立 runtime |
| 金融交易知识 skill | `.agents/skills/route-financial-trading/SKILL.md` | 按问题路由到市场分析、执行规划、仓位、研究可信度或安全 skill；默认公开研究，不授予账户、订单或资金权限 |
| 当前方案 | `design/CURRENT_BLUEPRINT.md` | V3.4 固定 4H 架构、旧 V3.3.2 runtime 边界、qualification 与迁移；Post-V3.4 多模型规划见 `design/POST_V34_MULTI_MODEL_AGENT_MANAGEMENT.md`，当前不运行 |
| V3.4 FORECAST_ONLY 入口 | `trade_system/theory_paper_v2/presentation/v34_forecast.py` | 固定 4H context/seal/outcome/latest；本地、不可执行、无账户/订单权限 |
| V3.3.2 交易 Goal paper 入口 | `trade_system/theory_paper_v2/presentation/paper_agent.py` | 绑定当前 Goal、开户、准备/提交 intent、机械处理 admitted cycle；除 setup 的 Goal 身份外只接 cycle，不接方向、数量、价格、账户、截止或批准参数；无外部订单 |
| V3.3.2 系统计划 | `trade_system/theory_paper_v2/v3.3.2/DEVELOPMENT_PLAN.md` | 已实现阶段、数据准入、paper/capability/continuity 门、迁移、回滚与后续实验顺序 |
| V3.3.2 只读工作台 | `trade_system/theory_paper_v2/presentation/market_workbench.py` | 从 attention/paper 账本及同一主 raw store 重建六类 JSON 视图、MARK 估值与纸面成本归因；无写权限 |
| 错误复盘 | `reviews/ERRORS.md` | 已知问题、根因、纠正和状态 |
| 历史导航 | `archive/INDEX.md`、`requirements/history/INDEX.md` | 按类别查旧版本，不作当前权威 |

## 一级目录职责

| 目录 | 唯一职责 | 文件类别与默认规则 |
|---|---|---|
| `.runtime/` | 旧本机运行状态 | 不提交；`.runtime/v32` 只读保留，未经精确备份和批准不得删除 |
| `agent-cluster/` | 冻结 Agent 集群实验 | contracts、templates、skill sources、handoff、experiments；仅按实验入口读取 |
| `archive/` | 分类历史库 | authority、旧配置说明、设计、复盘、日志、实验、报告和用户保留文件；只读 |
| `artifacts/` | 仍被引用的生成结果 | 冻结报告和实验包；不作为当前状态，解除引用后归档 |
| `audits/` | 路径绑定审计证据 | 日期化审计；保持原字节，只按精确引用读取 |
| `config/` | 配置和冻结身份 | schema、manifest、prompt 和摘要绑定；旧字符串由 archive path map 解释 |
| `coordination/` | 并发写入隔离 | `README.md` 是固定规则；每个 Agent 的工作文件单写、临时、不提交，合并后删除 |
| `design/` | 当前实施与明确批准的未来规划 | `CURRENT_BLUEPRINT.md` 是当前唯一方案；`POST_V34_MULTI_MODEL_AGENT_MANAGEMENT.md` 仅未来多模型设计，V3.4 不导入 |
| `har1/`、`har1r2/`、`har1r3/`、`har1r4/`、`har1r5/` | 历史 HAR 研究链 | 版本化旧代码/证据；严格重放使用原提交，默认不读 |
| `ops/` | 运维入口 | 本地运行辅助；不得自行扩大到外部自动化 |
| `requirements/` | 当前与历史需求 | `CURRENT.md` 唯一有效；`history/` 存历史正文和短索引 |
| `reviews/` | 当前错误复盘 | `ERRORS.md` 唯一入口，不新增分散复盘长文 |
| `tests/` | 影响验证 | `targets.json` 记录 owner、精确方法、预算和升级边界；`README.md` 给出单点用法；慢 E2E 只人工运行 |
| `theory/` | 当前与历史理论 | `CURRENT.md` 短入口、`versions/` 按版本导航、`legacy/` 压缩摘要；`current/`/`history/` 暂存仍被 runtime/冻结消费者绑定的原字节 |
| `tools/` | 小型工程工具 | 日常只用 `run_focused_tests.py` 做路径映射和精确测试；`run_theory_tests.py legacy-wide` 是隔离历史诊断，不得自动调用 |
| `trade_system/` | 当前实现 | V3.3.2 runtime 保持历史/工具边界；V3.4 `strategic_control + scheduled_strategy + forecast_qualification + strategic_state_repository` 只提供不可执行 Stage-A/语义复算，无 paper authority |
| `traders/` | 持续 Trading Agent 的局部记忆 | 每个交易员独占目录；`AGENTS.md` 定义工作法，`state.json` 负责恢复，history/hypotheses 只追加，不复制 raw 或 paper ledger |

## 当前树

```text
/
├── AGENTS.md
├── README.md
├── WORKSPACE.md
├── coordination/{README.md, <work-id>--<agent-id>.md}
├── requirements/
│   ├── CURRENT.md
│   └── history/{INDEX.md, historical requirements}
├── theory/
│   ├── CURRENT.md
│   ├── versions/
│   │   ├── INDEX.md
│   │   ├── v3.4.0/{MANIFEST.json, README.md, 00..05 modules}
│   │   ├── v3.3.2/{MANIFEST.json, README.md, 00..05, 08..09 modules}
│   │   ├── v3.3.1/{MANIFEST.json, README.md, 01..07 modules}
│   │   ├── v3.3.0/{MANIFEST.json, README.md, 01..07 modules}
│   │   ├── v3.2.6/README.md
│   │   ├── v3.1.1/README.md
│   │   └── v2.1/README.md
│   ├── legacy/SUMMARY_BEFORE_V3_1_1.md
│   ├── current/V3_2_DYNAMIC_AGGRESSIVE.md
│   └── history/{referenced legacy bytes}
├── design/CURRENT_BLUEPRINT.md
├── reviews/ERRORS.md
├── archive/
│   ├── INDEX.md
│   ├── legacy-path-map.tsv
│   ├── authority/
│   ├── config-history/
│   ├── docs/{design,reviews,logs,status}/
│   ├── experiments/
│   ├── reports/
│   └── user-preserved/
├── trade_system/
├── traders/hype-trader/{AGENTS.md, state.json, history.jsonl, hypotheses.jsonl, policy.json, attention.json}
├── tests/
├── config/
├── artifacts/
├── audits/
└── agent-cluster/
```

根目录 Markdown 只剩 `AGENTS.md`、`README.md` 和 `WORKSPACE.md`；工程元数据为 `.gitignore`、`pyproject.toml`、`setup.py`。不存在长期兼容正文或历史大文件。

## Market-cycle 现有实现与 V3.3.2 系统边界

共享 `market_cycle` 仅保留为 V3.3.2 PIT/paper 历史取证与工具边界，不再是 V3.4 的 cognition runtime。旧 HYPE continuous-goal/r3 run 已权威只读关闭且不补写；其既有 paper 授权不延伸到 V3.4。V3.4 当前只使用独立的本地 FORECAST_ONLY service/repository，不接账户或订单。

目标主链保持五工件，但决策 owner 正在切换为 Agent：

```text
capture PIT InputSnapshot
→ Agent 可读原文决策
→ HypothesisRecord + BehaviorPlan 原样封存
→ 到期 Outcome
→ Agent Review 封存
```

- 默认新运行根为 `~/.local/state/agent-trade-emotion/market-cycle`；每个 cycle 的 `request.json`、state head/history/intents、五工件、raw attempts/bundles 和 Agent sidecar 共同构成恢复边界。
- `CycleService` 拥有逻辑 `RunState` 与合法转换；`Repository` 是唯一物理 writer。旧 store 不双写、不迁移进新 run。
- V3.3.2 HYPE 路由为同一 `FileRawCaptureStore` → 强语义 profile → `MarketDataPort/InputSnapshot`；默认只 replay sealed raw，只有显式 CLI/runtime flag 才调用公共 HTTP collector。输入与 Outcome 共用这条授权门；外置 `v3.3.2/external_data_interface` 只作来源合同迁移/诊断，不是第二主路。
- Attention repository 只保存顶层 Goal 自述的下一检查点；正式写入从当前 Goal registry 与可信时钟派生 provenance，并受 run 生命周期锁保护，不判断条件、不派发、不唤醒。每次自然唤醒先对账到期五工件，未到期只保留最早 due，不因此重做市场分析。paper ledger 拥有模拟账户事实；Goal 经 cycle-only paper port 准备/提交 intent 并机械处理 admitted cycle。GTC impact 越限保持有效，IOC 同条件到期，任何 fill 不得越 Agent 限价。`paper_context` 1.5.0 只投影最近一个 PIT 合格 COMPLETE Decision/Review 精确原文；formal state 索引不是新事实 owner。
- outcome 前评价分成市场/假说/交易/仓位/Goal 自管节奏五类语义能力；DATA/SYSTEM/recovery/E0 只使用可重放运行事实。continuity 只记录 Goal checkpoint、后续真实 decision 与 owner heads，不驱动 Agent，也不能权威关闭 run。
- `infrastructure/market_cycle/operational_evaluation.py` 是 E0 唯一评价计算入口；`operational_evaluation_store.py` 只以可信时钟 create-once 封存其可重建 package。它们验证 runtime/run-binding、读取 COMPLETE 五工件并离线重放 InputSnapshot 与已观察 Outcome 的 raw；`application/domain market_cycle/evaluation.py` 只承载纯 facts 投影，不解析 Agent 原文、不接收 paper/attention 效果，也不成为新事实 owner。
- `infrastructure/market_cycle/capability_assessor_mailbox.py` 只承载独立 assessor task 的精确 request/findings 边界；general/paper capability stores 必须由事实回执重建 assessor 身份与 findings，不接受调用方代填。
- 旧 `COLD` 实现可读但暂停写入；其严格 proposal schema 和确定性 planner 不再是目标合同。`DELTA`、`EVENT_FAST`、`manual_intake.py` 与 checkout 外理论发现仍未实现。
- 新路由只允许系统处理身份/PIT/未来隔离、迟到、不可读/空白、覆盖损坏和未授权副作用；格式或市场语义缺口封存为质量证据，不终止 cycle。
- 精确测试入口除既有 market-cycle targets 外，覆盖 `v332-data-contracts`、`v332-hype-data`、`v332-sndk-identity`、`v332-attention`、`v332-paper-ledger`、`v332-paper-valuation`、`v332-capability-evaluation`、`v332-funding-scheduler`、`v332-continuity`、`v332-operational-evaluation` 与唯一离线 E2E；不得因此运行全量 Theory。

## 历史与冻结材料

- 分类历史按主题目录保存，版本或日期保留在文件名中。
- 旧路径到新位置的映射见 `archive/legacy-path-map.tsv`。
- 冻结 config、artifact、handoff 和 receipt 不为整理目录而改字节；严格历史重放使用清理前提交 `0de6bf87ae3d065205d337ad8996881b159f91f6`。
- `CORE_TRADING_THEORY.md` 与 v2.1 字节完全相同；无版本重复件已删除，唯一正文位于 `archive/authority/CORE_TRADING_THEORY_v2_1.md`，Git 可恢复旧路径。
- 用户副本已原字节移入 `archive/user-preserved/`，移动前后 SHA-256 不变。
- 旧 V3.2/V3.1 代码和 `.runtime/v32` 仍未删除；其退出只以 `requirements/CURRENT.md` 的精确恢复、外部调用方确认和用户批准边界为准。

## 后续写入规则

- 并发 Agent 的实时任务、进度、路径所有权和共享修改建议只写各自 `coordination/` 工作文件；integrator 在同步点重新读取并一次合入对应唯一 owner。
- 新需求只更新 `requirements/CURRENT.md`；被替代内容进入 `requirements/history/` 并在索引留一行。
- 理论入口只更新 `theory/CURRENT.md`；新版本写入唯一 `theory/versions/vX.Y.Z/`，旧版本通过索引和 legacy 摘要导航。被 runtime、代码、测试或冻结工件绑定的原字节保持旧路径，消费者迁移完成前不得为整洁而移动。
- 架构、数据、测试和迁移只更新 `design/CURRENT_BLUEPRINT.md`。
- 错误只更新 `reviews/ERRORS.md`，相同根因复用同一 ID。
- 运行结果写结构化 cycle 工件；一次测试、一次失败、一次讨论或一个日期不得单独新建 Markdown。
- 历史正文不追加“最新状态”；当前文件不复制历史过程。

下一步按 `requirements/CURRENT.md` 保持 r3 永久只读；V3.4 Stage-A harness 已实现，只运行严格 PIT `FORECAST_ONLY` qualification 来测 4H/12H/24H 能力；未通过前不实现/授权 FROZEN_PLAN、DYNAMIC_MANAGEMENT 或 fresh paper cohort。

## V4.0 分析 → 交易计划入口

- `theory/CURRENT.md`：当前 V4.0 决策理论唯一入口。
- `theory/versions/v4.0.0/`：风险、假说/结构、PR/EV、执行/管理和 Stage 4 benchmark 的正式规范。
- `trade_system/v4_decision/`：纯计算/校验的非可执行交易决策层；不接账户、凭据或订单。
- `tests/v4/`：V4 决策层最小 owning tests。

V4.0 的“交易”在当前阶段指分析结果到交易计划/仓位风险表达，不等同于 paper/testnet/live 执行权限。任何外部副作用必须另行授权并经过交易安全边界。
