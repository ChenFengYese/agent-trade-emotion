# 本机采集运维

当前生产式能力仅是**公开行情证据采集**，不含 API key、账户接口或下单路径。

部署或在代码升级后刷新本机 LaunchAgent：

```bash
./ops/deploy_capture_supervisor.sh
```

运行状态：

```bash
launchctl print gui/$(id -u)/com.agent-trade-emotion.capture-supervisor
tail -n 100 "/Users/wt/Library/Application Support/agent-trade-emotion/logs/capture-supervisor.stdout.log"
python3 -m trade_system capture-plan-status \
  --plan config/forward_capture_plan.g1.v1.json \
  --data-root "/Users/wt/Library/Application Support/agent-trade-emotion/runtime/g1-forward"
```

临时停止调度（不删除 package、配置、日志或 evidence）：

```bash
launchctl bootout gui/$(id -u)/com.agent-trade-emotion.capture-supervisor
```

LaunchAgent 按 28 个冻结 UTC slot 换算后的 `Asia/Shanghai` 本地日历时刻唤醒，并在登录/重载时额外运行一次恢复检查；已启动的 61 分钟采集不会并发重入，slot 目录一旦存在就永不自动复用。系统时区若改变，必须重新生成并核对日历项；即使触发时刻漂移，UTC plan 仍会拒绝迟到或越窗采集。后台运行包与冻结配置部署在 `~/Library/Application Support/agent-trade-emotion`，以避开 macOS 对 `Documents` 后台访问的隐私限制。源码仍以本仓库为权威，变更代码后必须重新部署，不能直接修改 site-packages 或已部署的只读配置。
