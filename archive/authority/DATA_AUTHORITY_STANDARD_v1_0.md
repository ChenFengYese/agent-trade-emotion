# 数据来源权威标准 v1.0

## 1. 目的与边界

本标准为研究系统登记**来源能力**，而不是证明某个数据集已经取得、完整、可回放或可用于交易。来源被登记后仍必须逐批通过原始工件、校验和、覆盖证明、修订链和 point-in-time（PIT）验证。文档发现、API 可访问、网页可见、供应商声称覆盖，均不构成研究证据准入。

本标准不授权下载行情、抓取网页、接入 API、回测、纸面交易或实盘交易。`config/research_system.source_authority_registry.v1.json` 在本版本仅为文档发现清单。

## 2. 来源等级（authority grade）

| 等级 | 含义 | 可支持的最强主张 | 不能自动推出的主张 |
| --- | --- | --- | --- |
| A | 官方原始数据、监管/法律原文、正式技术标准、公开官方数据库、原始实验数据或高质量同行评议研究 | 在其明确口径和样本内的事实、正式语义或研究结论 | 文件完整、目标市场可迁移性、PIT 合格、预测优势或可执行成交 |
| B | 权威机构报告、专业数据库、行业核心机构数据或方法和结果可复现的研究报告 | 在其许可证、版本、方法和覆盖内的候选事实或参数 | 原始交易场所真值、完整覆盖或目标策略有效；付费不等于 A 级 |
| C | 有明确方法、样本和上游来源的二手研究或专业分析 | 研究线索、交叉核对或候选假说 | 单独支撑高置信度核心结论 |
| D | 新闻转述、平台文章、个人经验、论坛内容或未公开完整方法的结论 | 案例、异常线索和假说生成 | 直接进入正式理论结论、参数或交易规则 |
| E | 无法追踪来源、无法复现或明显依赖主观断言的内容 | 只能进入待澄清线索池 | 任何正式事实、参数、机制或行动 |

等级衡量来源对具体命题的权威与可审计程度，不衡量策略收益或单个数据文件的实际质量。同一机构可因不同产品和命题具有不同等级；同一 A 级来源的实际工件仍可能在完整性、覆盖、修订或 PIT 轴上为 `UNKNOWN`。

## 3. 四个独立状态轴

每个来源必须分别声明以下状态；禁止用一个“可信”标签替代四项验证。

| 轴 | 可用状态 | 需要的最小证据 |
| --- | --- | --- |
| `integrity_status` | `VERIFIED` / `FAILED` / `UNKNOWN_NOT_VERIFIED` | 原始工件、固定内容标识或校验和、解析记录与保管链 |
| `coverage_status` | `VERIFIED_COMPLETE` / `VERIFIED_PARTIAL` / `GAP_CONFIRMED` / `UNKNOWN_NOT_ACQUIRED` | 合约化观察窗口、期望频率或原生序列、缺口证明 |
| `revision_status` | `VERIFIED_VERSIONED` / `VERIFIED_NON_REVISING` / `REVISION_CONFLICT` / `UNKNOWN_NOT_VERIFIED` | logical ID、revision ID、操作、发布时间与可重放的版本选择规则 |
| `pit_status` | `VERIFIED_AVAILABLE_AT` / `FAILED_LOOKAHEAD` / `UNKNOWN_NOT_VERIFIED` | `event_time`、`published_at`（适用时）、`received_at`、`available_at` 与 lane 可用性记录 |

`UNKNOWN` 不是零、无事件、无修订或无影响；它要求下游 `ABSTAIN`、剔除或按协议降级。官方来源也可以是 `coverage_status=UNKNOWN_NOT_ACQUIRED`。

## 4. PIT、修订与断档规则

每个准入记录至少应具有：

```text
source_id, instrument_id, source_event_id, logical_id, revision_id,
revision_operation, event_time, published_at, received_at, available_at,
artifact_id, artifact_sha256, coverage_seal_id, parser_version
```

在决策时刻 `t`，仅可使用 `available_at <= t` 的同一 lane 已准入版本。对于宏观或监管数据，`event_time`/参考周/观测期绝不能替代 `published_at`；对原始市场消息，交易所时间不能替代本系统的 `received_at` 与准入 `available_at`。修订必须新建版本，不能静默覆盖旧回放。

若连续性无法由原生序列、快照契约或权威无活动证明闭合，覆盖状态为 `UNKNOWN`。网络静默、接口空结果、供应商页面缺少文件均不可解释为“市场无活动”。

## 5. Source adapter 边界

adapter 只负责：获取获授权的原始工件、保存原字节与哈希、解析为规范字段、记录时钟、映射合约、生成 coverage/revision 事实。adapter 不得：

1. 补齐缺失数据或把沉默转为零；
2. 推断机构、做市商或交易者意图；
3. 将供应商字段重命名后伪装为原始事件；
4. 用当前修订值替代历史可得 vintage；
5. 把数据可访问性升级为策略或执行授权。

不同来源必须保留独立 `source_id`、工件与 revision 链；cross-validation 只能发现冲突、时钟错配或映射问题，不能把两个未知来源合成为已验证真值。

## 6. 准入与使用门

文档发现属于当前 `RSR-P0`，不是 D0 数据准入。后续门与程序统一为：

| 门 | 必须满足 | 允许用途 |
| --- | --- | --- |
| RSR-P0 文档发现 | 来源记录完整；四轴可为 `UNKNOWN` | 理论的数据可得性讨论、未来 adapter 设计；不得取得数据、测量或回测 |
| D0 获取授权 | exact source、许可、instrument、schema、期间、成本、资源、chronology 和失败规则 | 仅获取决定中列明的原始工件 |
| D1 原始准入 | 原始字节、哈希、来源 receipt、完整性、coverage、revision、PIT 与外部权威已验证 | 仅准入 exact raw artifact |
| D2 adapter/replay | 字段、单位、sequence、gap、clock、revision、确定性与 malformed input 已复核 | 仅离线解析和 point-in-time replay |
| D3 数据集 | feature、state、zone、episode、label、censoring、chronology 和 coverage 已冻结 | 仅生成预注册研究数据集，不评分 |
| E2 回测/校准 | candidate、baseline、cost、split、metric、trial 和一次性 holdout 已冻结 | 仅执行决定中列明的历史评价 |
| E3 paper/testnet | E2 结论、独立风险/OMS、故障注入和账户边界已满足 | 仅决定中列明的 paper/testnet；无资金或实盘 |

不得跳门。来源的 `next_gate` 只描述下一项需要验证的事实，不构成行动授权。

## 7. 可支持命题的约束

来源记录中的 `supported_propositions` 是**上限**。例如：CFTC COT 可用于低频拥挤背景，不能做 15 分钟入场；ALFRED 可用于 vintage-aware 宏观发布日期研究，不能以当前修订值回填历史；论文可支持变量定义，不能证明策略收益。任何策略结论还需独立满足理论测量合同、样本外协议、成本模型和风险门。

## 8. 版本、替换与审计

Registry 的条目在 `DOCUMENT_DISCOVERY_ONLY` 状态下不替代既有冻结 authority package，也不改写已有研究结论。替换来源时，必须并存旧条目、声明替换理由、映射影响、PIT 可比性与回放版本；不得静默改写。每次由 D0 升级时，必须新建版本和审计报告。
