# V3.2.6 版本入口

版本：`V3.2.6-five-trap-hardening-candidate`

状态：`ADVANCED_PENDING_EVALUATION / LEGACY_SINGLE_FILE_RUNTIME_COMPATIBILITY`

市场有效性：`UNKNOWN_NOT_EVALUATED`

## 当前正文

完整原字节正文仍位于：

- [`theory/current/V3_2_DYNAMIC_AGGRESSIVE.md`](../../current/V3_2_DYNAMIC_AGGRESSIVE.md)

固定信息：

```text
size_bytes = 99647
sha256 = eea31863e8e32f0999d91d587113be227be32b705c799455c386660fadb01061
```

本目录是版本化文档入口，不复制第二份正文。现有 V3.2 runtime 把旧路径的单一 Markdown 全文作为 `COMPLETE_V32_THEORY_DIRECT_CURRENT_ROOT_INPUT`，并明确拒绝 symlink；目前有文档、代码和测试消费者继续绑定该路径。直接移动、拆分或用软链接替换会破坏兼容。

## 版本角色

V3.2.6 保留为 V3.3.0 的先进待评价前身，主要贡献包括：

- 公开点时数据、未来隔离和 raw-first；
- lead/runner-up/OTHER 与不可校准序数判断；
- probe、confirm add、runner、reduce 和 reentry；
- 动态区域、路径 modifier、dependency cluster；
- public reference risk 与未来真实执行分开；
- delta 分析、恢复和单尝试故障边界。

其主要不足为：

- 市场、仓位、资格、authority、receipt、恢复与事故混在约 10 万字节单文件；
- 后段治理和 qualification 占据过多篇幅；
- 固定支持档位和部分 reentry 参数仍写入稳定理论；
- Agent packet、runtime closure 和重复验证过重；
- 没有正式 target cycle/outcome，市场价值仍未知。

## 读取规则

- 研究 V3.2.6 历史语义或重放绑定消费者时读取旧单文件；
- 当前理论开发默认读取 [`../v3.3.0/README.md`](../v3.3.0/README.md) 及其按需模块；
- 不把旧 qualification、本地 PASS 或 frozen failure 继承给 V3.3.0；
- 只有新 manifest loader 和消费者迁移完成后，旧快照才可退出。
