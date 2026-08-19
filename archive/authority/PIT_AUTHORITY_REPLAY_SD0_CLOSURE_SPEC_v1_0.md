# PITAR1 SD0 计量式来源闭合规范 v1.0

## 地位、身份与不可越界项

本文件落实 `SOL_RESEARCH_SYSTEM_PIT_AUTHORITY_REPLAY_SD0_D0_PHASED_ROUTE.v1` 唯一当前 P0：构建并在所有预检通过后执行一个固定、可计量、失败关闭的官方文档／校验和侧车／ZIP 头元数据闭合包。它不是 D0 授权、不是历史数据准入，且不会读取 ZIP 正文或任何市场行。

- 路线：`RSR-PITAR1-SD0-DUAL-LANE-PHASED-v1`；决策路径：`config/sol_decision.research-system-pit-authority-replay-sd0-d0-phased-route.v1.json`。
- 路线物理 SHA-256：`776a7b69c2655dd76eb84ccab12b3fbac30aef6a81b0f6ebad27ab391b129ec0`；路线 canonical SHA-256：`a777dc9411f638f1d3728f7f98f4ccbb64673f06b8f344dd3489efcdc5b79eeb`。
- 唯一绑定工作区／分支／HEAD：`/Users/wt/Documents/agent-trade-emotion`／`codex/s0-research-foundation`／`7ca3fc4f99a57f98217e703f222b295653ace87e`。
- 精确静态路径：本规范、`config/pit_authority_replay.sd0_measurement_contract.v1.json`、`config/pit_authority_replay.sd0_request_plan.v1.json`、`trade_system/pit_authority_replay_sd0_metered_fetch_v1.py`、`tests/test_pit_authority_replay_sd0_metered_fetch_v1.py`。运行时路径也只能属于合同列出的十四项 allowlist。

计量合同绑定路线的全部权威文件及其物理身份；路线有 canonical 身份的 JSON 绑定也必须同时匹配。路线未声明 Markdown canonical 身份时，合同显式为 `null`，不得自行推断或伪造。当前契约和请求计划 canonical 身份分别为 `4ed9f22451ede5c834c20e4f1786d344847166b646f9a1b17d2948e16c617a5b` 与 `a334816cca1cbdf676e1b935a3404f5803d4ee892c25d2e1d7d34d3a02ea6fe7`。

任何人、客户端或本地测试都不能自我接受 SD0。唯一完成门是新的独立 `GPT-5.6-SOL_ULTRA_SD0_GATE`。当前不授予 D0、D1、D2、D3、E2、paper、testnet、部署、凭据、订单或资金权限；最大资金风险与订单数均为零。活动 G1 既不能读取、复制、修改，也不能成为 SD0 输入或输出。

## 精确请求与资源上限

请求计划是闭合的：只允许七个逻辑请求，按 `SD0-001` 至 `SD0-007` 串行执行，首个失败即停；只允许计划中精确 HTTPS URL 与 `raw.githubusercontent.com`、`data.binance.vision` 两个主机。每一个 GET 必须先有相同对象成功的 HEAD，且 HEAD 必须为零正文、允许的 content type 与可接受的声明长度。

1. `HEAD` README；随后仅允许其配对 `GET`，正文最多 1 MiB。
2. `HEAD` LICENSE；随后仅允许其配对 `GET`，正文最多 1 MiB。
3. `HEAD` 精确的 `BTCUSDT-1m-2024-03.zip.CHECKSUM`；随后仅允许其配对 `GET`，正文最多 64 KiB。
4. 仅 `HEAD` 精确的 `BTCUSDT-1m-2024-03.zip`。

不得有 ZIP `GET`、市场行正文、目录或搜索请求、备用 URL／主机、浏览器或 web 工具、curl／通用下载器、cookie／凭据、直连、环境代理覆盖、重定向或重试。并发为一；单请求超时 15 秒；总墙钟 120 秒；最多七个逻辑请求；总响应正文最多 2,162,688 字节；每个响应头最多 64 KiB；全部本地工件最多 10 MiB；磁盘预检至少 15 GiB；外部成本为零。

传输只能使用 `http://127.0.0.1:7897` 代理上的 TLS，且必须验证证书。代理 TCP 监听器预检成功只是发送请求的必要条件，并不代表来源可用、许可已闭合，或自动赋予网络执行资格；预检失败时不能切换代理或直连。只允许 create-once 写入预检工件，状态为 `WAIT_DATA_NETWORK_TRANSPORT_NO_REQUESTS`，外部请求数为零，然后停止。

## 预检、写入与失败关闭

在任何外部请求前，客户端必须确认：cwd／分支／HEAD 和所有权威哈希匹配；十四项 allowlist 输出中待新建路径不存在；路径及父路径均无符号链接；可用磁盘达标；精确代理 TCP 预检成功；本地客户端与合成风险测试证据存在；并记录请求计划 canonical 摘要。输出根为 `.runtime/pitar1-sd0-v1`；所有输出 create-once，已存在、重写、符号链接或 allowlist 之外的路径一律拒绝。部分运行保留已写回执，报告失败关闭，绝不以同一 run ID 重试。

计量合同为十四个角色定义了闭合 schema：预检、请求 NDJSON、响应头 NDJSON、README、LICENSE、checksum 侧车、ZIP HEAD 回执、闭合报告、内容身份清单及五项静态构建工件。JSON 采用拒绝未知键、重复键和非有限数；哈希为小写 64 位十六进制；时间为 RFC3339 UTC `Z`；NDJSON 每行一个对象且无空行。

失败状态仅能是合同枚举中的：`WAIT_DATA_NETWORK_TRANSPORT_NO_REQUESTS`、`FAIL_CLOSED_NO_OVERWRITE`、`HALT_ROUTE_DRIFT_NEW_SOL_REVIEW`、`HALT_PROTOCOL_VIOLATION`、`HALT_RESOURCE_CAP`、`HALT_NO_ROW_LEAK_VIOLATION`、`WAIT_DATA_TERMS_D0_DENIED`、`WAIT_DATA_SOURCE_CONTRACT_MISMATCH`、`WAIT_DATA_NO_FALLBACK` 或 `STOP_AND_ESCALATE_TO_SOL_WITH_PROBLEM_BUNDLE`。状态不允许隐式升级为通过。

## 证据、条款与两证据车道

成功的最高正面主张仅为：精确的来源文档、校验和侧车与归档头元数据，在指定代理、请求顺序和资源上限下被获取，且未访问市场行或 ZIP 正文。这不证明数据行有效性、可用时点、回测、预测、期望收益、盈利、paper 或交易许可。

README 必须识别候选仓库和布局；CHECKSUM 必须恰有一个语法有效并绑定精确 ZIP 基名的 SHA-256；ZIP HEAD 必须具有非零且位于未来 D0 压缩上限内的声明长度。软件仓库 LICENSE 不等于市场数据复用条款。若未明确允许目标下载、当地保留、衍生研究工件及预定辖区，结果必须是 `WAIT_DATA_TERMS_D0_DENIED`，D0 仍被拒绝。

`HAR1` 是历史归档工程重放车道：只可作为重建工程证据／假设延迟敏感性；`event_time` 绝不得复制、别名化或作为 `received_at`／`available_at` 证据，不能推进真实 PIT 门。`FCR1` 是实际前向可用性车道：必须有实际 `received_at_utc`、单调时钟、ingested、admission、available 与 decision 时钟，并需要新的不可变计划、注册表、采集器摘要、证据根、cohort map 及未来 Sol 门。HAR1 不得填补 FCR1 时钟；FCR1 也不能回溯赋予 HAR1 点时性；只有预先分配、互不重叠的 FCR1 cohort 才可能支撑校准、锁定 holdout、shadow 或 paper 主张。

## 可复核性

两个 JSON 自摘要均以 UTF-8、`ensure_ascii=true`、递归排序键、分隔符 `,`／`:` 的 canonical JSON 计算，排除自身摘要字段，并使用 domain separator `0x00`：

`sha256(domain_prefix_utf8 || 0x00 || canonical_json(document_without_own_digest))`。

合同域为 `pitar1/sd0-measurement-contract/v1`，字段为 `contract_sha256`；计划域为 `pitar1/sd0-request-plan/v1`，字段为 `plan_sha256`。物理 SHA-256 始终仅针对文件最终原始字节；不得以 canonical 摘要替代物理身份。
