# Agent Trade Emotion

本项目用公开市场数据让 Agent 形成可检验的前瞻判断、封存结果并复盘迭代。当前默认边界是**研究且不可执行**：不连接账户、不发送订单、不使用凭据或资金，也不把本地测试等同于市场有效性。

## 开始位置

1. [`AGENTS.md`](./AGENTS.md)：效率、安全和工作规则。
2. 并发工作时先读 [`coordination/README.md`](./coordination/README.md) 并创建自己的独占工作文件；单 Agent 跳过。
3. [`requirements/CURRENT.md`](./requirements/CURRENT.md)：整合后的当前需求、状态和验收标准。
4. [`WORKSPACE.md`](./WORKSPACE.md)：文件路由、历史边界和写入规则。
5. [`theory/CURRENT.md`](./theory/CURRENT.md)：当前理论短入口。
6. [`design/CURRENT_BLUEPRINT.md`](./design/CURRENT_BLUEPRINT.md)：仅在任务需要时读取对应章节，不默认通读。

默认不要批量读取历史理论、审计、配置、测试、工件或实验目录。只有当前入口给出精确路径时才读取对应文件。

## 一级目录

| 目录 | 作用 | 文件类别与默认规则 |
|---|---|---|
| `.runtime/` | 本机运行状态 | 临时状态、收据和缓存；不是发布依据，不批量读取或提交 |
| `agent-cluster/` | 冻结的 Agent 集群实验 | 合同、模板、skill source、handoff 和实验工件；只在用户明确恢复对应实验时读取 |
| `archive/` | 只读历史库 | 旧设计、审计、日志、报告、配置说明、权威快照和用户保留文件；从 `archive/INDEX.md` 按类别进入 |
| `artifacts/` | 仍被引用的生成结果 | 冻结报告和实验包；不把它们当作当前状态，不重写历史结果 |
| `audits/` | 路径绑定的正式审计证据 | 日期化事故或一致性审计；保持原位，只按精确引用读取 |
| `config/` | 配置与冻结身份 | 当前/候选配置、schema、manifest 和摘要绑定；不能为整理目录改写冻结内容 |
| `coordination/` | 并发工作隔离 | 固定规则加每个 Agent 的独占临时工作文件；共享结果由 integrator 合并后删除 |
| `design/` | 当前设计 | 只把 `CURRENT_BLUEPRINT.md` 作为现行方案；旧设计进入 archive |
| `har1/`、`har1r2/`、`har1r3/`、`har1r4/`、`har1r5/` | 历史 HAR 研究链 | 版本化旧实验与证据；路径绑定，默认不读，不用于当前能力声明 |
| `ops/` | 运维入口 | 本地服务和运行辅助；未经当前需求授权不得启动外部或自动化操作 |
| `requirements/` | 需求 | `CURRENT.md` 是唯一当前需求；旧正文和摘要均在 `history/` |
| `reviews/` | 当前复盘 | `ERRORS.md` 是唯一错误入口；不再新增按日期分散的复盘长文 |
| `tests/` | 验证代码 | 日常只跑受影响模块；跨模块变更才跑合同/直接消费者，新实验或明确阶段门才跑唯一去重 E2E |
| `theory/` | 当前与历史理论 | `CURRENT.md` 为短入口，`versions/` 按版本分类，`legacy/` 为压缩摘要；旧 `current/`/`history/` 原字节仅为兼容与冻结引用保留 |
| `tools/` | 开发工具 | 小型、可复用的维护或验证脚本；不得演变为第二套编排平台 |
| `trade_system/` | 生产与研究实现 | 当前业务代码；按 Presentation/Application/Domain/Infrastructure 原地收缩 |

## 根目录文件

- `AGENTS.md`、`README.md`、`WORKSPACE.md`：当前入口。
- `pyproject.toml`、`setup.py`、`.gitignore`：工程元数据。
- 根目录不再保留其他 Markdown 正文；历史路径由 `archive/legacy-path-map.tsv` 定位。
- 用户未跟踪副本已原字节移入 `archive/user-preserved/`，未删除或改写。

## 信息生命周期

- 当前信息只更新 `AGENTS.md` 分类树指定的唯一 owner；需求、蓝图和理论分别只保留一个当前入口。
- 并发实时目标、进度和文件所有权只写各自 `coordination/` 工作文件，不直接争抢共享入口。
- 内容被替代时，正文按主题进入 history/archive；索引只记“改了什么、实现了什么、为什么、暴露了什么问题”。
- 新增文档必须有唯一类别、owner 和退出条件；一次测试、一次失败或一次讨论不得单独建长文。
- 冻结实验、accepted/outcome、原始市场数据和路径/摘要绑定材料保持原字节，不能为表面整洁改写。

## V4.0 analysis → trading stage

The current methodology is V4.0.0. It adds an auditable risk/structure/hypothesis/PR/EV/execution/position-management layer and a non-executable trade-plan package under `trade_system/v4_decision/`. This stage is designed to test whether an Agent can turn PIT market analysis into a bounded, cost-aware trade plan without silently acquiring account or order authority.
