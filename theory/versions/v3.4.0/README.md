# V3.4.0 低频定时战略 Trading Agent 理论增量

版本：`3.4.0-low-frequency-strategic-agent-candidate.2`

状态：`FROZEN_THEORY_REVIEW_CANDIDATE / FORECAST_RUNTIME_IMPLEMENTED / NON_EXECUTABLE / MARKET_NOT_EVALUATED`

V3.4.0 不改写冻结的 V3.3.2 原文，而是在其市场认知、竞争假说、动态仓位、PIT 与安全边界之上增加一个更窄、更强的时间与战略控制层。r3 的核心失败不是“缺少更多技术指标”，而是高周期语言没有转化为真实权限：continuous-goal 使 Agent 长期被短周期波动反复唤醒，局部阈值逐步替代完整因果、人群、事件、未来空间和仓位管理。

## 1. 当前硬边界

```text
4H      = 最低 LLM 市场决策周期
1D+     = regime / higher strategy
1H      = 4H 内部证据，不拥有独立 LLM 交易权
15m/5m  = 内部路径与执行证据，不拥有独立 LLM 交易权
tick/L2 = execution / data / fail-safe evidence
```

当前 LLM 只由外部 UTC scheduler 在 `00/04/08/12/16/20` 六个 slot 唤醒。每次任务有明确终点，完成后停止；Agent 无权把“半小时后再看”转换成下一次 wake。

两次 committee 之间：

- LLM 不能生成新 thesis 或临时改变仓位；
- 本地执行器只能执行上一次 committee 已冻结的 bounded tranche/harvest/exit 条件；
- safety system 只能 `HALT/CANCEL/REDUCE/EXIT`，不得新增 LONG/SHORT exposure。

## 2. 当前必须解决的战略语义

每次有仓位或准备增加 exposure 时必须维护：

1. 15m/1H/4H/1D 四层 zone 与权限；
2. trend phase、因果 thesis、强替代和至少两条 IF→THEN path；
3. participant/positioning、event/news、sentiment、data quality/conflicts；
4. primary target、right-tail、acceleration/cascade 候选区域；
5. realized 与 unrealized PnL；
6. WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT 比较；
7. 冻结到下一 4H committee 的 tranche plan；
8. strategic invalidation、catastrophic protection、等待下一 committee 的最大压力风险、gap/impact stress 和成本后 R:R。

普通 15m/1H break 不能单独 `EXIT_CORE/EXIT_ALL`。如果仓位必须依赖 30 分钟后再次调用 LLM 才安全，说明仓位规模或风险几何不符合 V3.4。

## 3. Durable Strategic State 与低 Token 上下文

长期连续对话退出当前架构。每资产只携带：

```text
latest StrategicState
+ last-4H asset delta
+ shared market summary
+ portfolio/position summary
+ immutable source refs
```

默认 context canonical byte ceiling 为 `64 KiB`；历史 forecast/outcome 仍 write-once 保存，但不重复灌入 prompt。上下文控制用字节预算，实际 token 用 provider usage 另行测量，禁止把某 tokenizer 的估算冒充统一成本。

## 4. 当前实现

当前已实现：

- `strategic_control.py`：V3.4 exposure 语义与 deterministic payoff/risk 复算；
- `scheduled_strategy.py`：固定 4H 时间权限、FORECAST_ONLY semantics、intra-window authority 与低 token context；
- `forecast_qualification.py` + `strategic_state_repository.py`：按资产/4H slot write-once 的 FORECAST_ONLY harness 与 durable StrategicState，context 绑定 theory/asset/reference/slot/digest，Outcome 绑定精确 4H/12H/24H 时点；
- `v34-forecast`：只处理本地、不可执行的 context / forecast / outcome/evaluation，并可记录有 source ref 的 provider 实际 token usage；无法取得时保持 UNKNOWN。

当前没有 V3.4 paper/testnet/live authority。旧 V3.3.2 runtime 不自动获得 V3.4 身份。

## 5. 验证顺序

```text
FORECAST_ONLY
→ FROZEN_PLAN
→ DYNAMIC_MANAGEMENT
```

Stage A 先冻结 4H/12H/24H path，评价方向、target touch、MFE/MAE 和状态转换，不交易。Stage B 才测试一次性冻结仓位计划。Stage C 最后才比较 Agent 动态管理相对 frozen shadow 的增量价值。

## 6. 文档 owner

| 文件 | 责任 |
|---|---|
| `00_REVISION_SCOPE.md` | r3 归因、修订和 cohort 边界 |
| `01_STRATEGIC_MARKET_COGNITION.md` | 四周期证据、趋势、人群/事件/情绪、未来路径 |
| `02_MULTI_TIMEFRAME_POSITION_CONTROL.md` | PnL、WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT 与风险几何 |
| `03_EXPOSURE_ADMISSION_AND_AGENT_CONTROL.md` | exposure admission、4H scheduler、durable state 与 intra-window 权限 |
| `04_VALIDATION_PROGRAM.md` | Forecast → Frozen Plan → Dynamic Management |
| `05_SCHEDULED_COGNITION_AND_TOKEN_EFFICIENCY.md` | 定时认知、低 token context 与当前 forecast harness |

未来多模型管理 Agent 设计不属于本理论版本，单独位于 `design/POST_V34_MULTI_MODEL_AGENT_MANAGEMENT.md`，V3.4 runtime 不得导入。
