# V3.1.1 之前与组件理论压缩摘要

状态：`LEGACY_INDEX / NON_AUTHORITY`

目的：把旧理论退出默认阅读路线，同时保留冻结重放和活动消费者所需的原字节。

## 1. 使用结论

当前 Agent 不应默认读取下列原文。只有代码/配置/测试明确引用、冻结工件重放、或当前问题命中其独有机制时，才按链接读取。当前规则见 [`../versions/v3.3.0/README.md`](../versions/v3.3.0/README.md)。

旧文件“保留”表示引用完整性需要，不表示其规则仍为当前 authority。

## 2. 研究版本

| 原文 | 压缩贡献 | 当前处理 |
|---|---|---|
| [`RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md`](../history/RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md) | raw-first、十二轴、关联候选、严格路径、实验冻结 | 有大量配置/测试/冻结引用；保留原字节 |
| [`RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md`](../history/RESEARCH_THEORY_v3_DRAFT_FOR_REVIEW.md) | 开放市场研究、Agent 假说和多层判断草案 | 有配置/测试引用；保留原字节 |
| [`CORE_TRADING_THEORY_v2_1`](../../archive/authority/CORE_TRADING_THEORY_v2_1.md) | Core PIT、事实/因果/概率和工程 authority | 大量活动与冻结绑定；由版本入口导航 |
| [`CORE_TRADING_THEORY_v2_0`](../../archive/authority/CORE_TRADING_THEORY_v2_0.rsi-v0_2_2.md) | V2.0 与 RSI 兼容基线 | 代码、测试和配置绑定；保留 |

## 3. 组件 challenger

| 原文 | 有效内容摘要 | 在 V3.3.0 的去向 | 删除状态 |
|---|---|---|---|
| [`MARKET_SENTIMENT v1.0`](../history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_0.md) | 情绪序数与非概率表达 | 01/03 的 attention、ordinal support | 有引用，保留 |
| [`MARKET_SENTIMENT v1.1`](../history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_1.md) | 情绪标准修订 | 01/03 | 有引用，保留 |
| [`MARKET_SENTIMENT v1.2`](../history/MARKET_SENTIMENT_ORDINAL_STANDARD_v1_2.md) | 当前情绪标准后继 | 01/03 | 有引用，保留 |
| [`GENERALIZED_COMPETING_PATH v0.5`](../history/GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md) | 竞争路径、反证、OTHER | 03 Path Contract | 有引用，保留 |
| [`MSTA-HED guidance v0.6`](../history/MSTA_HED_TECHNICAL_GUIDANCE_v0_6_0.md) | 多尺度技术分析与风险指导 | 01 三 frame、02 仓位 | 有引用，保留 |
| [`MSTA-HED integration v0.6`](../history/MSTA_HED_THEORY_INTEGRATION_CHALLENGER_v0_6_0.md) | 多尺度整合路线 | 01/03 | 有引用，保留 |
| [`RESEARCH_SYSTEM v1.0`](../history/RESEARCH_SYSTEM_THEORY_CHALLENGER_v1_0.md) | 研究系统对象与边界 | 04 五工件/四层 | 有引用，保留 |
| [`DYNAMIC_HYPOTHESIS_GRAPH v1.2`](../history/RESEARCH_SYSTEM_DYNAMIC_HYPOTHESIS_GRAPH_CHALLENGER_v1_2.md) | 动态假说图与谱系 | 03 lifecycle | 有引用，保留 |
| [`RSI MTF DRL PM v0.3`](../history/RSI_MTF_DRL_PM_THEORY_CHALLENGER_v0_3_0.md) | RSI、多周期、动态风险 | 01 method card、02 policy | 有引用，保留 |
| [`RSI MTF FOUR LAYER v0.4`](../history/RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md) | 四层系统结构 | README/04 | 有引用，保留 |

## 4. 已吸收并删除的五份原文

下列原文的有效设计已被 V3.3.0 吸收，没有现行代码、配置或测试消费者；Strategic 文件只有一处冻结历史需求叙述引用。用户于 `2026-08-11` 明确批准删除，五份原文已退出工作树。

| 精确路径 | 字节 | SHA-256 前后缀 | 已吸收内容 |
|---|---:|---|---|
| `theory/history/BOUNDED_AGENT_AUTONOMY_CHALLENGER_v0_1.md` | 15,060 | `0bace37f…66c20c` | 05 的 Agent 自由空间与硬边界 |
| `theory/history/PATH_RISK_AND_STAGED_POSITION_GOVERNANCE_CHALLENGER_v0_1.md` | 25,262 | `3356dad0…17a918` | 02 的 path risk、tranche、阶段管理 |
| `theory/history/STRATEGIC_EPISODE_POSITION_GOVERNANCE_CHALLENGER_v0_1.md` | 56,411 | `9b682f7f…17c0b` | 02 的 episode、harvest、runner、reentry |
| `theory/history/THEORY_AGENT_V2_THEORY_BASIS_v1_0.md` | 22,659 | `9e86f0cf…555dc` | 03/04 的 Agent 与假说分工 |
| `theory/history/THEORY_AGENT_V2_THEORY_TECHNICAL_BRIEF_v0_1.md` | 7,974 | `5b78cd8d…d8a3bd` | 04 的 bounded packet 与落地边界 |

合计：`127,366` 字节。

删除释放工作树正文 `127,366` 字节。历史叙述继续保留原文件名，活动 `archive/legacy-path-map.tsv` 不再把旧根路径映射到不存在文件。若需恢复，必须从基准提交 `0de6bf87ae3d065205d337ad8996881b159f91f6` 的旧根路径按原 SHA-256 恢复；不得把恢复动作解释为重新成为当前理论。

## 5. Authority 与规格类历史

`archive/authority/` 中的数据、PIT、RSI、MSTA、Theory Agent 合同和治理文件不是当前理论正文，但多数被配置、代码、测试或冻结工件绑定。它们继续作为兼容/重放材料；不得因版本较旧批量删除。

[`COLD_STORAGE_LIMITS.md`](../../archive/authority/COLD_STORAGE_LIMITS.md) 即使当前无精确引用，也定义“本地冷副本不是独立灾备、未经授权不得删除”的保护边界，继续保留。

## 6. 压缩后的默认规则

- 默认只读 V3.3.0 当前 owner；
- 需要旧 runtime 时读 V3.2.6 单文件快照；
- 需要前一可靠性语义时读 V3.1.1；
- 需要冻结重放时，保留原文按绑定路径读取；本次已删除五稿只能从上列 Git 恢复点读取；
- 不从 legacy 文件继承 CURRENT、权限、参数或市场结论；
- 新内容不得再追加到 legacy 原文。
