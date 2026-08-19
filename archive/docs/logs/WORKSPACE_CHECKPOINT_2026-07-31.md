# 工作区版本化检查点（2026-07-31）

## 本次提交目标

把自 `7ca3fc4f99a57f98217e703f222b295653ace87e` 以来已经完成的理论、治理、合同、Agent skills、V1/V2 离线实现、测试、审计与合法证据纳入版本控制；同时把未完成实验和权限边界写清楚。此检查点不删除 `.runtime/`，不恢复自动化，不产生 paper/live/真实订单。

## 已完成并纳入版本化的能力

- Core Trading Theory v2.1、竞争路径、多时间尺度、战略 episode、路径盈亏与分段仓位、有界 Agent 自主权等理论与 challenger 文档；
- 当前状态覆盖层、数据权限与历史诊断治理、PIT/研究系统/RSI/HAR1 系列合同和封存证据；
- 已终止 V1 paper 实验的只读代码、审计接口与历史说明；本地逐小时运行记录仍在被忽略的 `.runtime/`；
- Theory Agent V2 canonical contract、142 个 schema 与 registries、三个互斥角色 skills、确定性内核 resolution 与 cluster bootstrap；
- Theory Agent V2 四层 E0 离线运行时：战略连续性、竞争路径、动态几何、风险预算、CORE/TACTICAL、重入、调度、撮合、机会成本、唯一提交与事件兼容；
- 冻结第一轮只读评估、canonical 场景、正式 E0 数据/实验编排、原生 Codex 跨窗口 checkpoint/record/evaluate 工具；
- 对应 CLI、报告、配置、测试、审计和恢复说明。

这些完成项证明的是代码、合同、状态机、确定性回放和本地测试边界，不证明预测有效、因果解释、成本后盈利、paper readiness 或 live readiness。

## 未完成模块与恢复状态

| 模块 | 当前状态 | 恢复条件 |
| --- | --- | --- |
| 原生 Codex 32 对拓扑实验 | `PAUSED_INCOMPLETE`；权威 run `native-codex-e0-btcusdt-20260731T112457Z` 为 `0/32`、next `96`，尚无 evaluation | 使用项目 skill 和 `agent-cluster/experiments/native-codex-e0-20260731/HANDOFF.md`，从干净 Agent 树恢复 |
| 严格 transport-attested 拓扑证据 | `NOT_ESTABLISHED` | 需要可机器证明的服务模型身份与等 token 预算；不能由 practical 原生协作结果冒充 |
| Theory Agent V2 第二轮 paper | `NOT_CREATED / NOT_AUTHORIZED` | 先完成预注册实验与行为/风险门，再独立授权和创建新 run/automation |
| 101% 外生初始成本实例 | `NOT_INSTANTIATED` | 仅在第二轮前置门通过后按冻结公式创建 |
| V1 paper 自动任务 | `TERMINATED / PAUSED` | 当前不得恢复；历史结果未达到原验收标准 |
| HAR1R5 与真实数据许可 | `STATIC_GATE_ONLY / NO_NETWORK_AUTHORITY` | 需独立合法许可、失败原子持久化和新的明确授权 |
| 真实 PIT 数据、D0、样本外预测与收益证明 | `NOT_ESTABLISHED` | 需要正规来源、冻结未见数据、合格评估与独立风险闸门 |
| paper/live/账户连接 | `DENIED` | 本提交不提供任何执行许可 |

## 本地运行时与 Git 边界

- `.runtime/`、`.env*`、虚拟环境、缓存、coverage 和构建目录保持忽略；它们不会被本次提交吸收或删除。
- 原生 practical run 的冻结 contexts 与 checkpoint 是本机恢复状态，不是 Git 发布证据。其路径、摘要和恢复规则已写入版本化 handoff。
- 旧 run `...T110012Z` 与 `...T111022Z` 保留作本机工程诊断；不得复制到权威样本分母。
- 当前提交不推送远端，不创建 PR 或发布标签。

## 验证记录

- 支持运行时：Python 3.12（项目声明 `>=3.11,<3.14`）。
- 完整测试：`python3.12 -m unittest discover -s tests -t . -q`，`1164/1164 OK`。旧测试曾把全部 skill sources 锁死为三个；现已纠正为“三个互斥决策角色 + 一个非角色实验总控”，定向 9 项 skill package 测试通过。
- 结构验证：版本库范围内全部 JSON 均经 `jq` 解析通过；已跟踪修改的 `git diff --check` 通过。全量 staged 检查仅报告历史 Markdown 硬换行、冻结文档和已物化源码中的既存尾随空白/额外 EOF 空行；这些字节可能受摘要或历史证据绑定，因此本次不做破坏性格式化。
- 本地恢复验证：权威 practical run 的 context integrity 与 event chain 均为 `PASS`，manifest digest 与 handoff 一致，checkpoint 仍为 `0/32`、next `96`。
- 敏感信息检查：常见私钥、云访问键、OpenAI/GitHub/Slack token 特征及敏感文件名扫描无命中；`.env*` 继续被忽略。
- 大文件检查：Git 范围内不存在超过 5 MiB 的文件；待提交新文件均为 JSON、Markdown/纯文本、Python 或其他文本源码/证据。
