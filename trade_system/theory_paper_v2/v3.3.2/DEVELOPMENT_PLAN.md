# V3.3.2 最小系统开发计划

版本：`v3.3.2-system-foundation-review-candidate.3`

更新日期：2026-08-14

状态：`SEMANTIC_SINGLETONS_PASSED / FINAL_IDENTITY_G1_RECOVERY_PREFLIGHT_PENDING / CONTINUITY_24H_NOT_STARTED / NO_TESTNET_LIVE_AUTHORITY`

## 1. 结论

当前只维护 V3.3.2。系统使用现有四层 `market_cycle`、唯一 Repository 和唯一 raw/PIT store；不复制平台、事实 owner、scheduler 或事件总线。

每个已准入资产由一个持续顶层 Codex Goal 负责。Goal 独占市场分析、竞争假说、动作、仓位、检查频率、休息与 Review，并在冻结授权内直接提交本地 paper intent。Codex host 负责保持/恢复 Goal；仓库只保存 Goal 的 next-check 声明，不解释条件、不定时、不唤醒、不审批交易。

用户已授权 HYPE 公开数据和隔离本地 paper；未授权 testnet、live、私有账户、凭据、外部订单或资金。系统只有身份、PIT、时限、风险、账本 CAS、不可变封存和实验终止硬门。

## 2. 当前交付

### 2.1 必须成立

1. HYPE raw 先封存后解析，以 exact instrument、closed bar、PIT、freshness、单位和 claim ceiling 进入同一 `AssetDataSlice/InputSnapshot`。
2. 顶层 Goal 通过 `v332-paper-agent setup|prepare|commit|process` 操作隔离账户；除 setup 内部取得 Goal 身份外，公开调用只接 run/theory/cycle，不接交易字段或批准字段。
3. `prepare/commit` 绑定当前 Goal registry、sealed Decision/Plan、agent request/delivery、paper context、intent request、账本头和可信时间；不依赖 paper-action Worker、wake ACK 或监督 receipt。
4. paper 支持 WAIT/HOLD/WATCH、七类命令、完整保护 bracket、保守 fill、成本/资金费、版本重放和崩溃恢复；无外部交易 transport。
5. Goal checkpoint 只有 register、append/CAS、supersede 与 replay；没有 approve/defer/reject/trigger/dispatch/ACK/recover-wake。
6. Outcome 的 endpoint 与 ordered future path 独立采集；V3.3.2 必须携合法 path schema，即使结果是 `CENSORED`。
7. 下一 Decision 自动内联最新 earlier COMPLETE Review 原文；上一轮没有 intent 也不能断开学习链。
8. 静态对照固定标成 `IDEALIZED_STATIC_REFERENCE`；没有 matched actual fill/cost arm 时是 `NOT_COMPARABLE`。
9. capability assessor 从权威 registry、工件、账本/checkpoint heads 和独立 assessor 输出重建证据，不接受调用方代填结论。
10. 所有 optional 缺失与真实成本/收益未知保持 typed `UNKNOWN/NOT_EVALUATED`。

### 2.2 明确不做

- 不建设仓库内条件监控器、唤醒 runner、定时器、监督交易 API 或第二套 controller。
- 不让系统从 Agent 原文解析并替它选择方向、仓位、价格、注意力或 Review。
- 不用 paper、fixture、本地 PASS、接口可达或一次样本声称真实成交、盈利、生产可用或泛化。
- 不把 SNDK 正股、SNDKx、spot 和 perpetual 当成统一产品；未准入资产不开账户。
- 不接私有 key、账户、testnet/live、外部订单或资金。

## 3. 四层 owner

| 层 | owner | 只负责 | 不负责 |
|---|---|---|---|
| Presentation | `market_cycle.py`、`paper_agent.py`、workbench | 五工件输入输出、Goal paper 工具、只读展示 | 市场判断、监督批准 |
| Application | data profile、Goal registry/checkpoint、paper、Outcome/Review、evaluation | 用例编排与纯派生 | 第二事实 owner、scheduler |
| Domain | identity/data/paper/capability/continuity contracts | 不变量与可重放值 | I/O、市场 selector |
| Infrastructure | source/raw/repository/mailbox/ledger/clock | raw-first、create-once、CAS、可信时间 | Agent 语义、外部订单 |

唯一主链：

```text
public capture → sealed raw/PIT → InputSnapshot
→ persistent Goal decision → HypothesisRecord + BehaviorPlan
→ Goal prepare/write/commit local-paper intent
→ Goal-chosen future captures + mechanical paper process
→ ordered Outcome → Goal Review
→ next Decision receives latest COMPLETE Review
```

## 4. 当前事实与边界

| 范围 | 当前事实 | 尚不能声明 |
|---|---|---|
| HYPE data | shared raw owner、strong profile、provider-ahead normalization、optional typed UNKNOWN 已实现 | 连续 L2、完整历史、长期稳定性 |
| Goal/paper | direct cycle-only port、isolated account、execution receipt、风险复算、原子 bracket、crash replay 与 G1 同 Goal资格已通过；较长 POSITION 自然受保护样本 5/5 展示 | 长期连续性与收益能力 |
| Goal cadence | registry/checkpoint append/CAS/supersede 已实现；host Goal/计划任务是恢复 owner | 仓库自动唤醒、精确定时、长期无人值守 |
| Outcome | 纯决策后 ordered 15m path、exact grid、endpoint/path 独立、合法 censored 已通过统一代码门 | 分钟内顺序或真实成交路径 |
| Review continuity | latest earlier COMPLETE Review 原文/ref/SHA 自动进入下一 Decision；intent 只是可选交叉绑定 | Review 一定改善后续交易 |
| Static diagnostic | bracket 事前原子登记、歧义 fail closed、episode link 已实现 | actual-vs-static 政策优越性 |
| Funding/cost | 严格 history 边界、逐结算点、当时仓位和 frozen closed-15m proxy | 真实 venue 费用与成本后收益 |
| Evaluation | E0 无评分事实包、独立 assessor transport和五类语义 singleton 前向证据已完成 | 预测、收益、泛化、组织独立性 |
| Continuity | checkpoint/owner heads/recovery probe 与权威 run close 已实现 | 已完成 24 小时 |

## 5. Goal paper 工具合同

公开命令：

```text
v332-paper-agent --runtime-root RUN --theory-package V332 setup
v332-paper-agent --runtime-root RUN --theory-package V332 prepare DECISION_CYCLE
v332-paper-agent --runtime-root RUN --theory-package V332 commit DECISION_CYCLE
v332-paper-agent --runtime-root RUN --theory-package V332 process MARKET_CYCLE
```

- `setup` 从当前 Codex Goal 身份、frozen policy、setup slice 和可信时钟派生 registry/account；不接受 account、balance、leverage、risk、time 或 trade 参数。
- `prepare` 只冻结当前 Goal 可写的 exact intent contract；不选动作。
- `commit` 读取 create-once Agent intent，执行授权/PIT/schema/stale-ledger/risk/terminal 硬门后原子写本地 paper，并封存 execution receipt。
- `process` 只接 admitted cycle；系统机械选择该 slice 最丰富的合法 QUOTE，否则 MARK，调用者不能选 fill 方式。
- checkpoint 写入失败不得变成合法 paper intent 的许可门；paper 硬门失败也不得改写 Agent intent。

## 6. 检查点与恢复

`AttentionRequest` 的冻结字段名 `earliest_wake_at` 只表示 Goal 自述的 next-check time。仓库只保存：identity、mode、窗口、reason/focus、episode/account ref、data cursor 和 supersedes。

Goal 恢复时读取：最新 COMPLETE Review、当前 paper account/open orders、最近 checkpoint、到期 Outcome 和最新 data cursor。若 host 无法恢复同一 Goal，则停止当前前向批次并新建 run/account/identity；不以 generation+1 拼接同一实验样本。

continuity 只比较实际后续 Decision 与自述窗口、owner heads 和重复副作用。错过自述时间是 Agent cadence 证据，不是系统自动 restart 条件。

## 7. 资格与实验顺序

### G0：代码门

- changed-path owning tests + direct consumers 通过；
- implementation identity 覆盖所有安全依赖；
- 无 active paper-action Worker、wake/trigger runner、supervisor trade API；
- public CLI 无 caller-supplied trade/approve/override 字段；
- docs/targets 与源码一致。

### G1：persistent-Goal 短资格

用一个独立顶层 Goal 和 fresh run：

1. setup 隔离账户；
2. Goal 自主选择两次不同检查间隔并记录 checkpoint；
3. host 恢复同一 Goal；
4. Goal 完成一轮 Decision/Plan，prepare 后自主写 WAIT 或可执行 intent；
5. commit 成功或仅因公开硬门诚实拒绝；
6. 对 fresh admitted cycle process；
7. 重启后重复调用无双写；
8. 全程无仓库 wake/dispatch/approval、无外部订单。

若 host 不能保持/恢复同一 Goal，标记外部能力阻塞；不得在仓库补 scheduler。

### G2：fresh POSITION

G1 通过后新开 singleton `POSITION_MANAGEMENT` run。两个短样本均已完成 D0→Outcome→Review→D1 和独立 pre-Outcome 评价：首个样本的 D0 入场 `UNRESOLVED`、D1 合法 WAIT；G2b 的 D0/D1 均自主 WAIT。两者终局都无持仓，均为 4/5 criteria demonstrated，`NO_LOSS_AVERAGING` 因无真实亏损持仓场景而未证明，保持 `NOT_DEMONSTRATED_ON_THIS_SAMPLE`。G2b 的 prepare/commit/status 重放无双写；较新 market event 已入账后重放旧 cycle `process`，由市场时间单调性硬门零写拒绝。不得强迫入场、回填或把该拒绝误报为幂等缺陷。

随后一个较长、有界 fresh run 自然形成 bracket 入场成交、非零亏损仓位、足额 active reduce-only stop、完成的 D0 Outcome/Review 与同 episode D1。Goal 自主选择零增量 `HOLD`，没有亏损加仓或弱化保护；独立 assessor 5/5 `DEMONSTRATED_ON_THIS_SAMPLE`。止损随后自然平仓，已知费用后结果为亏损，funding/carry 仍为 `UNKNOWN`；这只证明单样本仓位管理能力，不证明收益或泛化。

### G3：24 小时综合批次

真实受保护持仓 G2 与权威收尾门现已成立。最终 funding/process 与 continuity FINAL 语义提交后，只需在该最终 implementation identity 上完成受影响的 G1/SYSTEM_EXECUTION+RECOVERY 短资格（含 funding typed 状态、异常恢复、FINAL→close 交接），即可创建新 86,400 秒 policy/run/account；无需重复依赖合同未改变的五个语义 singleton。Goal 自主 cadence；运行中身份/PIT/hash/ledger/未授权副作用污染则保留旧批次并重开，不拼接。optional UNKNOWN、合法 WAIT 或可重放同 transition 可继续。

## 8. 测试门

- 日常只跑改动模块 owning tests 与直接消费者，默认 `<2 min`；跨模块合同 `<5 min`；唯一 E2E `<10 min`。
- 同一 test ID 同一门只跑一次；代码和输入不变不碰运气重跑。
- HTTP 真实 capture 与离线回归分开；正式前向实验不得当调试器。
- 资金、身份、PIT、未来泄漏与外部副作用属于发布高风险门；其他 optional 缺失不扩大测试。

## 9. 停止线

立即停止并保留原事实：

- instrument/PIT/raw SHA/五工件/registry/ledger head 不一致；
- Goal 身份改变、intent 过期、账本 stale 或风险超 policy；
- create-once 冲突、重复 command、不可恢复 partial write；
- 出现 testnet/live/private/external order/funds 副作用；
- 为继续需要第二 core、绕过许可或修改冻结理论/评价标准。

optional 数据失败、合法 WAIT、无 fill、path censored 或真实成本未知只记录 typed 状态，不伪造成零或成功。

## 10. 唯一下一步

提交最终 funding/process 与 continuity FINAL 修复，完成一次 final-identity 的 G1/SYSTEM_EXECUTION+RECOVERY 短资格和 FINAL→close 交接；通过后立即启动唯一 fresh 24 小时批次，不重复已完成的语义 singleton。
