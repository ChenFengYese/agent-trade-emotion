# 历史库索引

`archive/` 只保存不应进入默认上下文、但仍有复盘或重放价值的材料。文件名和正文保留原日期或版本；不在历史正文上继续追加现行结论。首批从根目录迁入的正文没有批量改写，因此其中旧相对路径应按仓库根目录解释。

| 路径 | 类别 | 读取规则 |
|---|---|---|
| `authority/` | 冻结权威、边界和冷存储限制 | 只读；禁止把当前字节冒充旧摘要对应版本 |
| `config-history/` | 已退出活动引用的配置说明 | 只在追溯旧配置时读取 |
| `docs/design/` | 被替代的系统、V3、Theory Agent 和 paper 设计 | 当前实现以 `design/CURRENT_BLUEPRINT.md` 为准 |
| `docs/reviews/` | 旧审计、裁决和可靠性复盘 | 当前问题以 `reviews/ERRORS.md` 为准 |
| `docs/logs/` | 旧实现日志和 checkpoint | 不是当前状态，不继续追加 |
| `docs/status/` | 被替代的根 README/状态快照 | 仅用于恢复当时叙述 |
| `experiments/` | 旧实验设计、handoff 和冻结说明 | 真实机器工件仍在原 `agent-cluster/experiments/` 路径 |
| `reports/` | 已退出活动引用的生成或验证报告 | 不作为当前通过或有效性结论 |
| `user-preserved/` | 用户原始副本 | 只移动和校验，不删除或改写 |

旧根路径到当前分类位置的精确映射见 `legacy-path-map.tsv`。冻结 config、artifact、handoff、receipt 和 HAR 原始证据保持原字节；严格重放使用清理前提交 `0de6bf87ae3d065205d337ad8996881b159f91f6`，不得用当前文件替代摘要不匹配的历史 blob。
