# 并发工作目录

本目录只解决同一工作区内多个 Agent 的写入冲突，不是新的项目状态中心。长期目标、验收和稳定结论仍由 `requirements/CURRENT.md` 等唯一 owner 保存。

## 规则

1. 每个并发顶层工作 Agent 在修改文件前创建 `<work-id>--<agent-id>.md`，只写自己的文件，不修改他人的工作文件。
2. 顶层任务内部的子 Agent 不单独建文件；父 Agent 在自己的 `owned_paths` 中覆盖子任务路径，验收并整合其结果，避免递归登记。
3. 开工前扫描本目录其他顶层任务的 `ACTIVE` 文件；`owned_paths` 的文件或子树不得重叠。发现重叠时停止写入并通知主 Agent，不抢占文件。
4. 主 Agent/任务发起者默认是 integrator。`AGENTS.md`、`requirements/CURRENT.md`、`WORKSPACE.md`、`README.md`、当前蓝图、理论入口和错误复盘只由 integrator 在同步点合并；其他 Agent 只记录 `proposed_shared_updates`。
5. integrator 合并前重新读取共享文件，确认没有并发变化后只写一次稳定结果。无法确定 integrator 时，共享文件保持只读并交由用户指定。
6. 工作文件只记当前范围、路径所有权、结果和下一动作，不记命令流水或推理长文，不作为研究证据，也不得暂存或提交。
7. 稳定结果合入唯一 owner 后，Agent 删除自己的工作文件；未解决的交接文件只保留到新 owner 接手，不长期归档。
8. `updated_at` 只表示新鲜度，不是自动过期租约。原 owner 已确认停止或不可用时，integrator 才能在自己的新文件中声明接手，并在合并后移除旧文件。

## 每个 Agent 的最小格式

```text
work_id: <stable task id>
owner: <agent id>
integrator: <agent id>
status: ACTIVE | BLOCKED_CONFLICT | READY_TO_MERGE | DONE
scope: <one sentence>
owned_paths: <exclusive paths>
proposed_shared_updates: <shared owner changes or NONE>
latest_result: <current result>
next_action: <one next action>
updated_at: <ISO-8601>
```
