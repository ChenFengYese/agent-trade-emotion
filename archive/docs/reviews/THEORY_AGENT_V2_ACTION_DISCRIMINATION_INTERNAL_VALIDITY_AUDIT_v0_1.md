# Theory Agent V2 动作判别实验 E0A 内部效度审计 v0.1

状态：`FROZEN_PREOUTCOME_AUDIT`
审计对象：`128..159` 的 32 个冻结决策 context、E0A 合同与确定性实现
数据边界：本审计没有构造 outcome reader、没有读取任何决策时点后的 bar、没有运行 evaluate
旧运行处置：`native-codex-action-e0a-inline-btcusdt-20260801T070500Z` 保持 `3/32`、不可修改、不可评价

## 一、结论

E0A 已证明“相同冻结 context 下，Single-Strong 与 blind 三角色集群能够产生可审计的动作分歧”，但其金融动作合同和终局评价合同不足以判断哪一臂更忠实、更有经济价值。继续补齐旧 E0A 的 32 个样本会放大调用成本，却不能消除判定对象本身的歧义。

根因不是市场理论已被否证，也不是数据源失败。根因分为：

1. **金融合同失败**：路径终点、逐 lot 止损、追踪保护、部分减仓和重入语义不一致；
2. **实验设计失败**：一次性独立 profile 被用于表达本应跨轮履约的 reentry；
3. **评价函数失败**：1 小时结果拥有终局晋级权，32 小时设计的 4/8/24 小时诊断没有同等决策权；
4. **Agent 评分失败**：cluster 的专职 Challenger 被结构性奖励，而 Single 的 proposal 因没有自我质疑被扣分；
5. **编排失败**：旧正式 run 在 sample 131 创建 Selector 前触发 native thread limit，但这只解释为什么运行停在 3/32，不解释上述内部效度缺陷。

## 二、冻结 context 的量化事实

| 项目 | 冻结事实 |
|---|---:|
| 决策 context | 32 |
| profile | 8 类，每类 4 次 |
| 含既有 lot 的 context | 24 |
| 失败路径统一终点与逐 lot stop 不一致 | 20 |
| `HOLD_CORE_TRAIL` 出现在注册动作中 | 12 |
| `PARTIAL_TAKE_PROFIT` 出现在注册动作中 | 12 |
| `EXIT_WITH_REENTRY` 出现在注册动作中 | 20 |
| `REENTER_CORE` 出现在注册动作中 | 3 |
| `ADD_CONFIRMATION` / `ADD_TREND` | 6 / 3 |
| supervision | attended 16；unattended protected 8；unattended no-new-risk 8 |

20 个不一致 context 为：

`129, 130, 131, 132, 134, 137, 138, 139, 140, 142, 145, 146, 147, 148, 150, 153, 154, 155, 156, 158`。

## 三、五层证据定位

### 1. 原始市场数据层

- 点时可见的 1h/4h/1d bar、mark、ATR、24h/96h 高低点具有冻结谱系；
- 公开数据缺少 funding、OI、order book、liquidation flow、参与者心理和路径概率，context 正确保留为 typed UNKNOWN；
- 本审计未发现 E0A 内部效度失败由市场数据缺失直接造成。

### 2. 理论分析层

- 多时间尺度、竞争路径、风险预算、机会成本和重入对称性已经进入 Agent 选择轴；
- 但“反弹到 T1 后如何迁移为趋势延续”“重入合同如何跨轮履行”只存在概念，没有完整编译为可回放状态转换；
- 因此属于决策政策形式化不完整，不等于反弹/趋势理论本身已经失败。

### 3. 假说状态层

- E0A 的 profile 是相互独立的 counterfactual 快照，不是同一 `StrategicEpisodeState` 的连续事件链；
- `REENTRY_PENDING` 能测试“当前已经有重入义务时选 WAIT 还是 REENTER”，但 `EXIT_WITH_REENTRY` 不能证明下一周期真实生成、继承和履行了同一合同；
- E0A 只能评价单步动作判别，不能评价状态连续性。

### 4. 决策政策层

- `FAILURE_TO_STOP` 行显示单一 `geometry.stop_new`，金额却按各 lot 自有 stop 计算，终点和金额不属于同一反事实路径；
- `HOLD_CORE_TRAIL` 的 T1 触发、trail 距离、棘轮和 OHLC 同 K 线顺序没有进入 Agent 可见合同；
- `PARTIAL_TAKE_PROFIT` 实际关闭每个 CORE/TACTICAL lot 的 50%，且在部分 lot 浮亏时不一定是“take profit”；
- `EXIT_WITH_REENTRY` 只在当前时点平掉所有 exposure 并把状态文字改为 OPEN，没有重入触发、价格、数量、止损、成本或后续收益；
- 因此 Agent 比较的是标签，不是完整且同构的动作转换。

### 5. 仓位执行与收益层

- 即时交易费用、决策后已实现/未实现盈亏和机会损失已分离；机会损失也正确标为非实际亏损；
- 但事前嵌入盈亏被设置为 `None / EXCLUDED_COMMON_STATE`，无法核对“部分止盈”是否真实盈利、全平实际兑现多少历史盈亏；
- trail 同 K 线内先后顺序未冻结；
- 终局晋级仅比较 1h 聚合净值与全 horizon 最大回撤，4/8/24h 净值和机会损失不参与晋级。

## 四、评分偏置

每个 arm 有三个输出、每个输出 14 个二元项。`MATERIAL_SELF_CHALLENGE` 被要求于所有输出：实际已记录的 128..130 中 Single 每次为 41，Cluster 每次为 42；Single 固定缺失项是 `PROPOSAL:MATERIAL_SELF_CHALLENGE`。Cluster 具有专职 Challenger，且 proposer 也可附带 challenge，因此这一分差不能解释为更好的动作选择。

旧 `beneficial_intervention_count` 又把“动作不同且 cluster checklist 更高”直接定义为有益。该指标把角色拓扑差异循环证明为动作价值，不能进入终局因果裁决。

## 五、根因裁决

| 类别 | 裁决 | 证据含义 |
|---|---|---|
| 市场理论失败 | 未证明 | 尚未读取 outcome；动作合同缺陷不能否证市场假说 |
| 理论工程化失败 | 是 | 动态迁移、重入和逐仓路径没有完整编译 |
| 数据失败 | 否（就本事故） | PIT 数据和 typed UNKNOWN 边界可用；缺陷来自解释/状态合同 |
| 状态管理失败 | 是 | 独立 profile 不能证明跨轮状态连续性 |
| 决策政策失败 | 是 | 标签、实际 lot 转换和收益矩阵不一致 |
| 评价函数失败 | 是 | 1h 越权、quality topology bias |
| Agent 编排失败 | 是但独立 | thread limit 导致旧 run 停止，不是金融缺陷根因 |

## 六、最小可行处置

1. 冻结旧 E0A，不补写、不重试、不 evaluate；
2. 新建 E0B，仅用旧 Agent 未读取过的 `160..191` 连续决策窗口；
3. 逐 lot 表达失败端点，显式冻结全部动作转换；
4. 一步实验把 `EXIT_WITH_REENTRY` 定义为“退出并创建义务”，不得冒充已执行重入；
5. 收益账本同时报告事前嵌入盈亏与决策期增量，机会损失继续不记作实际亏损；
6. trail 采用无前视、无乐观同 K 线假设的固定顺序；
7. 终局只有在 1/4/8/24 全 horizon 描述性支配且回撤 guardrail 合格时才能给出一臂优势，否则 `INCONCLUSIVE`；
8. 自审与 blind challenge 对称计分，挑战覆盖只作诊断；
9. 在 32-context 静态合同测试、未来隔离和新 handoff 冻结通过前，不启动任何 E0B 正式角色。

## 七、证据索引

- profile、动作与样本分配：`trade_system/theory_paper_v2/domain/action_discrimination/model.py`
- lot、动作转换、路径矩阵：`trade_system/theory_paper_v2/domain/action_discrimination/engine.py`
- 多 horizon 模拟与终局：`trade_system/theory_paper_v2/domain/action_discrimination/evaluation.py`
- 语义质量评分：`trade_system/theory_paper_v2/domain/action_discrimination/validation.py`
- PIT/outcome 权限与事件链：`trade_system/theory_paper_v2/infrastructure/action_discrimination_store.py`
- 旧冻结合同：`THEORY_AGENT_V2_ACTION_DISCRIMINATION_EXPERIMENT_v0_1.md`
- 旧运行恢复证据：`agent-cluster/experiments/native-codex-action-discrimination-e0a-inline-20260801/HANDOFF.md`
