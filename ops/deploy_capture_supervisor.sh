#!/bin/sh
set -eu

project_root="/Users/wt/Documents/agent-trade-emotion"
runtime_root="/Users/wt/Library/Application Support/agent-trade-emotion"
agent_path="/Users/wt/Library/LaunchAgents/com.agent-trade-emotion.capture-supervisor.plist"
agent_label="com.agent-trade-emotion.capture-supervisor"
user_domain="gui/$(id -u)"

cd "$project_root"
/usr/bin/python3 -m compileall -q trade_system
/usr/bin/python3 -m trade_system validate-capture-plan --plan config/forward_capture_plan.g1.v1.json >/dev/null
/usr/bin/python3 -m pip install --user --no-deps --no-build-isolation .

mkdir -p "$runtime_root/config" "$runtime_root/logs" "$runtime_root/runtime"
install -m 444 config/forward_capture_plan.g1.v1.json "$runtime_root/config/forward_capture_plan.g1.v1.json"
install -m 444 config/source_registry.v3.json "$runtime_root/config/source_registry.v3.json"
plutil -lint ops/launchd/com.agent-trade-emotion.capture-supervisor.plist
install -m 644 ops/launchd/com.agent-trade-emotion.capture-supervisor.plist "$agent_path"

launchctl bootout "$user_domain/$agent_label" >/dev/null 2>&1 || true
launchctl bootstrap "$user_domain" "$agent_path"
launchctl print "$user_domain/$agent_label"
