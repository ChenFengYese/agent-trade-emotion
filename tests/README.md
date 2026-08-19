# 单点测试使用规范

默认入口是 `tools/run_focused_tests.py`。它只运行 `targets.json` 中列出的精确 unittest 方法；没有 discovery、通配符、资格收据或失败后全量回退。

## 日常命令

```bash
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py list
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py show v32-lifecycle-core
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py plan v32-lifecycle-core
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py run v32-lifecycle-core
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py plan --changed path/to/changed.py
/opt/homebrew/bin/python3.12 tools/run_focused_tests.py run --changed path/to/changed.py
```

多个改动路径要重复写 `--changed`。多个 target 可在一次 `plan`/`run` 后依次列出；重复方法只运行一次，同一测试类只支付一次 `setUpClass`。

## 强制规则

- 先 `plan`，确认精确方法、预算和人工建议，再 `run`。
- 未映射源码或测试文件返回退出码 2；先补一个最小 owner target，不得改跑全集。
- `manual_only=true` 只出现在 `manual_recommendations`，不会由 `--changed` 自动执行。
- `manual_only` 只约束日常单点入口；隔离的 `legacy-wide` 仍是历史全发现诊断，包含这些慢项，因此只能由人工明确启动一次，不能跟随普通修改。
- 超预算记为 `OVER_BUDGET`；先拆 fixture 或缩小 owner，不能单纯抬高预算。
- 文档零测试只适用于 `no_business_tests` 明确列出的路径。
- `tools/run_theory_tests.py legacy-wide` 是隔离的历史诊断入口，本工具永不调用它。

## 当前目标类别

- 默认单点：runner、V3.3 market-cycle 合同/证据/repository/公开数据/离线 E2E、fixture 隔离、current/生命周期 authority、V3.11 envelope、Agent lifecycle、semantic compiler、target wake、qualification materializer、analysis material、增量 market graph、历史 postcommit reader。
- 人工升级：lifecycle memo、selection/WAIT 边界、target-wake permit/ownership 边界、完整 materializer 双 Agent E2E、完整 Cycle acceptance、完整 market graph replay、真实子进程边界。

单个慢 E2E 只允许在它列出的跨层合同共同变化时运行一次。若定位表明耗时来自真实全链重放而非重复 fixture，就保留其覆盖并停止继续“优化数字”，不得用跨 wake 缓存、skip 或减少首次真实验证换速度。

每个目标的 owner、触发路径、方法 ID、预算、适用场景、禁止用途和升级条件均以 [`targets.json`](./targets.json) 为唯一机器记录。新增目标只加入真实 owner 的最小代表方法；不为理论完整性或尚未暴露的边界扩写测试。
