# Theory Agent V2 动作判别实验 E0B v0.2

状态：`PRECALL_FROZEN_CANDIDATE`
模式：`E0_OFFLINE_COUNTERFACTUAL`
外部执行权限：`NONE_E0`
证据标签：`PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`
用途：比较同一冻结决策 context 下 Single-Strong 与 blind Proposer/Challenger/Selector 的有界动作选择；不证明预测、盈利、paper 或 live 能力

## 一、实验问题

在确定性系统已经冻结点时事实、逐 lot 状态、风险上限、动作转换、交易成本和可行集合以后，blind 三角色集群是否相对 Single-Strong 产生：

1. 可审计的动作差异；
2. 更完整但不越权的路径/反证审查；
3. 在 1/4/8/24 小时冻结结果上具有描述性选择优势，且没有扩大最大回撤；
4. 对核心持仓、战术仓、加仓、减仓、退出义务和重入义务更忠实的选择。

实验不估计胜率，不计算伪精确 EV/Kelly，不把一次冻结历史推广为稳定市场规律。

## 二、样本与不可后见边界

- 唯一决策窗口：冻结 BTCUSDT bundle 的连续 index `160..191`，共 32 个；
- profile 与 supervision 仅按 index offset 确定性轮转，每个 profile 4 次；
- 这些决策 context 未用于 E0A 128..131 的正式 Agent 输入；
- context 只能读取 `<= decision_at` 的 96 根 1h、已 available 的 4h/1d 派生 bar；
- outcome reader 只能在 32 个 digest-chained event、192 份 role output 和 terminal checkpoint 全部验证后构造；
- 不因 E0A Agent 的动作或挑战内容修改 E0B 的市场窗口、路径阈值或终局方向；本版本仅修复其在 future outcome 之前已证实的合同错误；
- 160..191 与 E0A 来自同一历史 bundle，结果只作同源扩展诊断，不是独立市场外样本。

## 三、职责分界

确定性内核拥有：PIT、state、逐 lot 数量/成本/止损、动作转换、费用/滑点、总风险、监督权限、可行集合、事件写入和 outcome 隔离。

Agent 拥有：在 typed UNKNOWN 边界内解释多条路径、识别支持/反证、比较机会成本与跨时间尺度一致性，并从冻结 feasible set 中排序选择。

Agent 不得修改事实、数字、硬失效、风险上限、动作合同、state digest 或权限；内核不得因默认安全偏好删除合法 HOLD/ADD/REENTER。

语义层同时冻结三项一致性：`PRIMARY / ALTERNATIVE / NULL` 必须使用三个互异且非 OTHER/UNKNOWN 的 path；`hard_falsifier_refs` 只能引用 `state.hard_invalidator_refs` 的闭集；动作序位固定为 `PREFERRED > VIABLE > UNKNOWN > AVOID`，Selector 的 ranking 必须按该序位非降排列且首项必须是 `PREFERRED`。格式正确但违反任一关系的输出均 fail closed。

## 四、逐 lot 路径合同

`FAILURE_TO_STOP` 不再使用虚假的公共终点：

- `terminal_policy = EACH_POST_ACTION_LOT_AT_REGISTERED_STOP`；
- 每个 post-action lot 显式列出 `lot_id / role / quantity / stop / exit_cost`；
- `terminal_reference = null`；
- `net_account_change` 必须与上述逐 lot 退出完全复算一致。

T1、T2 和 T1 后回到 mark 的路径仍可使用公共价格终点。OTHER/UNKNOWN 无金额、无概率。

例外：`HOLD_CORE_TRAIL + EXHAUSTION_T1_THEN_RETURN` 缺少“T1 与回到 mark 是否发生在同一 bar”的顺序信息，而 trail 只从下一 bar 生效。因此该行固定为 `UNKNOWN_T1_RETURN_SEQUENCE_NEXT_BAR_TRAIL`，金额、终点和收益率均为 `null`；不得把可能的 later-bar trail fill 伪装成确定收益。

## 五、动作状态转换合同

| 动作 | 冻结转换 | 禁止误读 |
|---|---|---|
| WAIT_WITH_REVIEW | 仓位不变；保留下一根闭合 1h 或更早硬风险事件的复核义务 | 空仓无成本、无限等待 |
| HOLD_CORE | 保留所有当前已准入 CORE/TACTICAL lot 及其逐 lot stop | 重新建仓或放宽 stop |
| HOLD_CORE_TRAIL | 保留 lot；当后续闭合 bar 的 high 首次达到 T1 时，于下一根 bar 起把 stop 棘轮到 `max(old_stop, T1-(mark-stop_new))` | 假设未知的同 K 线 high/low 顺序或立即有利成交 |
| OPEN_CORE / REENTER_CORE | 以 decision mark 新建 6.25% CORE、使用 `stop_new` | 超出剩余风险、把重入当作延续旧成交 |
| ADD_CONFIRMATION / ADD_TREND | 以 decision mark 新建 3.125% TACTICAL、使用 `stop_new` | 无独立边际 RR 或超风险加仓 |
| REDUCE_TACTICAL | 关闭最后一个 TACTICAL lot 的全部剩余数量 | 关闭 CORE |
| PARTIAL_TAKE_PROFIT | 关闭每个现有 lot 剩余数量的 50%，其盈亏按各自 entry 单独报告 | 保证“获利”或只减某一角色 |
| EXIT_WITH_REENTRY | 当前 mark 关闭全部 lot，并创建独立、未来才可履行的 reentry review obligation | 同一步已执行重入、已获得未来 reentry 收益 |
| INVALIDATE_AND_EXIT | 仅在冻结 hard invalidator control 中关闭全部 lot并使 thesis invalidated | 风险减仓自动等同观点失效 |

`EXIT_WITH_REENTRY` 生成的合同至少包含：`status=OPEN`、`created_by_action`、`review_deadline`、`allowed_fulfilment_action=REENTER_CORE`、`maximum_new_stop_risk_fraction=0.0125`、`execution_in_current_action=false`。E0B 是单步实验，只能检查义务是否被正确创建/承认，不能宣称跨轮履约已经证明。

`WAIT_WITH_REVIEW` 与 `EXIT_WITH_REENTRY` 还必须分别生成显式 `review_obligation_after`，包含 `status=OPEN`、目的、下一根闭合 1h 或更早硬风险事件的 deadline，以及 `execution_in_current_action=false`。Evaluator 的一小时边界必须来自该冻结语义，不能只靠隐藏的事后硬编码。

## 六、OHLC 与成交顺序

追踪保护使用 `OHLC_ORDER_UNKNOWN_TRAIL_EFFECTIVE_NEXT_BAR`：

1. 当前 bar 先只用进入该 bar 前已经生效的 stop 判断触发；
2. 若 high 达 T1，trail 在 bar 结束后 armed；
3. 新 stop 从下一根 bar 开始有效；
4. 不用同一根 OHLC 猜测 high/low 的先后；
5. 最大回撤仍使用每根 bar 的 low 计算，不能因 trail 未同 K 生效而隐藏下行路径。

这是一项可复算的保守信息规则，不代表真实撮合引擎的逐笔成交顺序。

stop outcome 另采用 `MIN_REGISTERED_STOP_AND_BAR_OPEN_PLUS_FROZEN_EXIT_COST`：若下一 bar open 已低于生效 stop，以更差的 open 为价格参考并另计冻结费率/滑点；若 open 在 stop 上方但 low 触及 stop，才以 stop 为参考。不得假设 gap 一定按注册 stop 成交。

最大回撤不是“相对决策点最低值”。E0B 同时报告：

- `maximum_adverse_excursion_from_decision`：相对 decision mark 的最大不利变动；
- `maximum_drawdown_from_decision`：从已观察权益峰值到随后谷值的保守 OHLC 上界。

回撤顺序固定为：gap 在 open 先处理；其余同 bar 对多头采用 high-before-intrabar-low 的保守上界。终局 guardrail 只使用后一项，并明确这仍不是逐笔真实 MDD。

## 七、收益账本

每个动作、每个 horizon 分开报告：

- `predecision_embedded_gross_pnl`：决策前所有既有 lot 按 mark 相对 entry 的共同嵌入盈亏；
- `modeled_historical_entry_cost`：按冻结费率和 adverse slippage 对既有 lot 入场成本作统一模型化，不冒充真实历史成交费用；
- `predecision_embedded_net_pnl_after_modeled_entry_cost`：前两项相减；
- `embedded_pnl_realized_immediately`：动作在 mark 立即关闭数量所对应的历史盈亏；
- `embedded_pnl_remaining_at_decision`：动作后保留数量对应的历史盈亏；
- `decision_incremental_realized_pnl`：只从 decision mark 起算、在 horizon 内止损产生的价格损益；
- `decision_incremental_unrealized_pnl`：开放 lot 从 decision mark 到 horizon close 的变化；
- `transaction_cost`：即时动作与 horizon 内退出的费用和 adverse slippage；
- `net_account_value_change`：决策时点后的增量净变化；
- `full_accounting_net_pnl_from_entry`：共同事前嵌入毛盈亏减模型化历史入场成本，再加决策后增量净变化；
- `opportunity_loss`：相对同一 feasible set 的后见最佳动作，仅作诊断，永不记作实际亏损。

不得用短期已实现收益证明战略退出正确；不得把未实现盈亏、机会损失和实际亏损混为一项。

同一 case/horizon 下，`opportunity_loss = hindsight_best - selected_net`，因此两臂 opportunity-loss 差与净值差是代数镜像，不是第二条独立确认；它只用于解释错失路径，不进入独立晋级门。

## 八、preoutcome 评分对称性

- 每臂均有一个 proposal、一个专职审查角色、一个 selector；
- 只有 `SELF_REVIEW` 与 `CHALLENGE_BLIND` 必须提出至少一个 material challenge；proposal 与 selection 不因没有自我质疑被扣分；
- schema/PIT/证据引用/动作完整性/角色边界是硬有效性；
- challenge category coverage 单独报告为诊断，不能把动作分歧自动定义为 beneficial；
- 不从文字 checklist 分数推导金融动作优劣。

## 九、多 horizon 终局规则

只有通过全部硬安全、PIT、角色、收据与事件链验证的 32/32 event 和 192 份输出才能进入终局函数；任何硬错误都在 event/result 前 fail-stop，不产生可达的“硬错误终局”。输入未完成时为 `INCOMPLETE_NO_DECISION`；完整但没有动作分歧时为 `NO_ACTION_DISCRIMINATION`。

对每个 horizon `1/4/8/24h` 汇总两臂的：净账户变化、机会损失、最大 case 回撤及逐 case win/tie/loss。

E0B 不伪造跨轮 Agent 决策。`WAIT_WITH_REVIEW` 与 `EXIT_WITH_REENTRY` 在 1h review deadline 后标记为 `REVIEW_DEPENDENT_NOT_CONTRACT_COMPARABLE`；4/8/24h 的持续空仓数值只能作为 open-loop 敏感性，不能用于任何一臂晋级。只要真实动作分歧涉及这种超期状态，终局必须为 `INCONCLUSIVE_SEQUENTIAL_CONTRACT_NOT_PROVEN`。这明确区分“一步动作判别”与后续需要另行实验的“跨轮重入履约”。

只有满足全部条件时，才可给出 `DESCRIPTIVE_CLUSTER_SELECTION_ADVANTAGE`：

1. cluster 的 aggregate net 在四个 horizon 均不低于 single，且至少一个严格更高；
2. cluster 的全 horizon 保守 peak-to-trough 最大 case drawdown 不比 single 高超过账户 `0.25%`；
3. 24h 不能劣于 single。

Single 的优势使用完全镜像规则。其余均为 `INCONCLUSIVE_ACTION_TRADEOFF`。1h 结果不能单独晋级任何一臂。

该规则是冻结历史上的描述性向量支配，不提供 iid、显著性、预测有效性或稳定盈利声明。

## 十、原生角色与编排

- Single-Strong：同一 clean identity 内依次输出 proposal、自审、selection；
- Cluster：clean Proposer 与 blind Challenger 不互见，Selector 只接收两者冻结输出；
- 六个 semantic output 对同一 context digest，模型/精确 token 无机器证明时保持 practical 标签；
- canonical packet 必须在 child 的 initial message 一次性直接内联，并保存 packet digest、byte length、task id 与无工具/无外部数据收据；controller 必须从冻结 context 和最终 proposal/challenge 独立重算每个 packet 的 digest/长度，Single 三对象绑定同一 task，Proposer/Challenger/Selector 绑定三个互异 clean task，Selector packet 必须绑定最终入库的两份 upstream；
- 总控为唯一 writer；每个 sample 必须先完成六对象全验，再以 write-once 输出、单一 event 和原子 checkpoint 投影记录。多文件落盘不是文件系统事务；中途崩溃只能用字节完全相同的对象恢复，任何冲突均停止；
- 每完成一组立即 verify；任一 child 创建失败、缺包、schema 错误、超时或 thread limit 均停止，不重试、不补齐、不读 outcome；
- 为避免旧事故，新窗口只保留一个 sample worker；该 worker 顺序创建并等待四个 clean role child，自然完成后返回；不得 interrupt 已完成 worker 制造残留线程。

## 十一、正式调用前验收

必须全部通过：

1. 160..191 与旧 128..159 无重叠，32 个 context、8 profile 各 4 次、11 动作均有注册与可行覆盖；
2. 每个 failure row 的逐 lot stop、数量、费用与金额完全复算一致；
3. action transition document 与 simulator 对 partial/reduce/exit/add/trail 完全一致；
4. reentry obligation 不包含当前动作内的虚构成交或收益；
5. 所有 context 明示 trail 同 K 线政策；
6. 收益账本四类盈亏和成本恒等式通过；
7. topology-symmetric quality fixture 得分相同；
8. 构造“cluster 只在 1h 更好、24h 更差”的诊断时不得晋级 cluster；
9. outcome adapter 在 terminal chain 前构造失败；
10. outcome adapter 的 source run ID、run-binding、dataset manifest/payload digest 必须与 source receipt 精确一致；
11. 每次 load/role/record/verify 都把实际 context 的 context/state/calculation/matrix/physical digest 与 manifest 唯一行重新核对；
12. E0B config 的账户、几何、动作转换、outcome、quality 与终局字段必须逐项绑定实现常量，任一漂移 fail closed；
13. validator 必须拒绝编造 hard-falsifier ref、前三路径重复、Selector ranking 与自身 ordinal 冲突；WAIT/EXIT 必须显式携带下一小时 review obligation；
14. 同一样本内 Single 三对象绑定同一 task，Proposer/Challenger/Selector 绑定三个互异 task；四个 task 在完整 run 内不得被任何后续样本复用，且 transport preflight child task 永远不得作为正式角色复用；
15. 新 manifest、config、design、schema、source receipt 与 handoff digest 全部冻结，且 outputs/events/evaluation 为空。

## 十二、停止和结论边界

本实验不恢复 automation，不连接公开接口以外的新数据，不连接私有账户，不创建 paper/live 订单，不操作资金。硬安全错误会在 event/terminal result 之前停止，因此不存在可达的“带硬错误 terminal verdict”；只有零硬错误链能进入结果函数。任何工程 PASS 只证明合同与运行可复算；任何描述性动作优势只说明这 32 个同源冻结时点，不证明市场预测或生产就绪。
