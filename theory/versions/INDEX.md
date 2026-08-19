# 理论版本索引

当前审查入口：[`v3.4.0/README.md`](./v3.4.0/README.md)

## 默认可导航版本

| 版本 | 状态 | 正文位置 | 用途 |
|---|---|---|---|
| [`v3.4.0`](./v3.4.0/README.md) | 冻结定时战略增量；固定 4H、Durable State、低 token context、exposure admission 与分阶段验证；FORECAST_ONLY runtime 已实现但不可执行 | [`MANIFEST.json`](./v3.4.0/MANIFEST.json) + 七个绑定文档；继承冻结 V3.3.2 | 当前理论审查路线 |
| [`v3.3.2`](./v3.3.2/README.md) | 冻结前身；完整市场/动态仓位/注意力理论；r3 已关闭、E-025 3/12 | [`MANIFEST.json`](./v3.3.2/MANIFEST.json) + 九个绑定文档 | V3.4 基础与历史 cohort |
| [`v3.3.1`](./v3.3.1/README.md) | 冻结前身；Agent-first runtime 与第一批公共数据接入曾通过离线最小验收；旧 run 不恢复 | [`MANIFEST.json`](./v3.3.1/MANIFEST.json) + 八个绑定文档 | 只读实现与理论谱系 |
| [`v3.3.0`](./v3.3.0/README.md) | 被替代的冻结前身；旧 run 只读 | [`MANIFEST.json`](./v3.3.0/MANIFEST.json) + 八个绑定文档 | 历史 hypothesis-only/确定性 planner 语义 |
| [`v3.2.6`](./v3.2.6/README.md) | 先进待评价；旧单文件 runtime snapshot | 兼容正文在 `theory/current` | 历史语义和旧消费者 |
| [`v3.1.1`](./v3.1.1/README.md) | 被替代；前一 reliability base | 原字节在 `theory/history` | 可靠性谱系和旧消费者 |
| [`v2.1`](./v2.1/README.md) | legacy engineering authority | 原字节在 `archive/authority` | 大量绑定消费者与冻结重放 |

没有任何版本当前被证明为市场成熟、盈利、可执行或生产可用。

## 路由规则

1. 当前理论审查先从 `v3.4.0/README.md` 读取本次增量；未修改的基础问题继续路由到冻结 `v3.3.2` owner。V3.4 manifest digest 为 `1e7c3512c0cbd7de07d0b4c648bb65a9e668c27917297ee2ddc1c6b62a7bfe56`。
2. 旧版本目录提供版本身份、状态、摘要和原字节位置；不复制第二份正文。
3. `theory/current/V3_2_DYNAMIC_AGGRESSIVE.md` 暂时是旧 runtime compatibility snapshot，不是新的当前阅读入口。
4. V3.1/V3.0、Core V2.x 与组件 challenger 只从 [`../legacy/SUMMARY_BEFORE_V3_1_1.md`](../legacy/SUMMARY_BEFORE_V3_1_1.md) 导航。
5. 有冻结摘要或活动消费者的旧文件保持原字节；先迁移消费者，再决定删除。
6. 工件必须绑定 `theory_version + theory_revision + theory_manifest_digest`，不能只靠文件名判断当前性；当前审查路由不等于 runtime/实验激活。

## 版本晋级

```text
DRAFT
→ FROZEN_DOCUMENT_CANDIDATE
→ RUNTIME_IMPLEMENTED
→ FORWARD_CANDIDATE_ACTIVATED
→ FORWARD_EVIDENCE_OBSERVED
→ RETAIN / REVISE / REJECT
```

本地 PASS、文档完整、API 可达或 qualification accepted 不会自动跨越 `FORWARD_EVIDENCE_OBSERVED`。
