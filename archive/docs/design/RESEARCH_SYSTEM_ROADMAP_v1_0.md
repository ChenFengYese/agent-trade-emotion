# MSTA-HED 研究与系统路线图 v1.0

状态：`P0_ROUTE_CANDIDATE`

本路线图是依赖与优先级设计，不是阶段授权。当前只能执行 RSR-P0；D0、D1、
D2、D3、E2、E3 均须新的 Sol 决定。

## 1. 最终目标

最终系统应能够：

1. 从 point-in-time 多源数据识别周线、日线、4H、1H 和 15m 的背景与阶段；
2. 识别结构区间和当前位置，而不是只输出方向；
3. 在 RSI、量价、订单流、杠杆、强平、事件和宏观变化时更新有限竞争路径；
4. 只有在位置、触发、净价值、风险、数据和权限同时满足时形成订单候选；
5. 先以结构失效定义止损，再反推归一化仓位；
6. 持仓后动态更新剩余价值，同时保证最坏风险单调不扩大；
7. 对每次 WAIT、行动、结果和失败原因可复现；
8. 用新证据校准或局部修订理论，而不删除负面结果或反复调整以挽救失败。

## 2. 系统模块

```text
Source Authority
  ↓
Raw Admission
  ↓
PIT Replay ───────────────┐
  ↓                       │
Feature / Clock / Quality │
  ↓                       │
State + Zone              │
  ↓                       │
Hypothesis + Evidence     │
  ↓                       │
Scenario + Trade Thesis   │
  ↓                       │
Utility + Permission      │
  ↓                       │
Action / Risk / Execution │
  ↓                       │
Result + Evaluation ──────┘
```

各模块必须输出 `UNKNOWN/WAIT/SUSPEND`，不能因数据缺失强制给方向。

## 3. 优先级原则

### P0

- 权威、数据完整性、PIT、revision、gap；
- 理论对象链与测量合同；
- 核心假说的低成本区分；
- 权限、风险和非自授权合同；
- 能停止多个下游错误工作的事实。

### P1

- 明显改善常用研究流程或降低高概率错误；
- leverage、event、dependency de-dup 等有增量潜力的模块；
- dynamic management 的同入口比较；
- 跨源验证。

### P2

- historical analog、复杂 regime/changepoint；
- 高成本专业数据；
- 全系统联合优化；
- 任何未证明净收益的通用平台或复杂模型。

## 4. 阶段门

### RSR-P0：研究重构基础

允许：

- 理论与来源审计；
- 权威文档和原始论文发现；
- versioned theory candidate；
- object/source/hypothesis/parameter/dispute registry；
- measurement/stage contract；
- pure total validator；
- synthetic/adversarial tests。

完成条件：

- 当前核心理论、旧 active-G1、旧 P1A 和活动 Application Support 均未修改；
- 每个 testable hypothesis 有 measurement contract；
- 来源记录 grade、license、clock、revision、gap 和 claim mapping；
- validator 检查 exact fields、types、IDs、clock、digest、cross-binding、
  empty semantics、alias 和 fail-closed totality；
- 独立验证者不依赖构建者 helper；
- 完整证据索引与声明边界；
- Sol 明确 PASS。

通过后不会自动授权 D0。

### D0：历史数据获取授权

P0：

- 确定一个主执行研究标的和一个产品身份；
- exact source、URL/object pattern、period、schema、estimated bytes、cost、
  license、storage root、checksum；
- DEVELOPMENT、CALIBRATION、一次性 HOLDOUT 的时间角色；
- partial download、retry、replacement、checksum fail、no-backfill；
- 资源预算和终止条件。

建议主线候选：

1. `BTCUSDT` Binance USD-M perpetual 作为目标研究产品；
2. 官方 exchange metadata、trades/aggTrades、klines、mark/index/funding/OI；
3. strict L2 单独评估，不能用 COIN-M aggregated bookDepth 冒充；
4. 一个独立 venue 或专业数据库只用于 PIT 对齐后的交叉验证。

这只是候选，D0 必须重新核对当前官方可得性和法律/成本。

### D1：原始工件准入

每个 artifact 必须具有：

- raw bytes；
- SHA-256 和 byte length；
- source receipt；
- license/terms status；
- exact instrument/contract；
- coverage window；
- event/published/received/available clocks；
- logical/revision identity；
- gap facts；
- chronology role；
- 外部 pinned authority。

零字节、空结果、静默和部分文件必须有不同状态。候选对象不能提供自己的
trust root 或 acceptance。

### D2：adapter 与 deterministic replay

先 supplied fixture，后 offline raw artifact。验证：

- exact schema 与字段类型；
- side、unit、contract multiplier；
- snapshot/delta 与 sequence；
- reconnect、duplicate、out-of-order、gap；
- document/schema version；
- revision；
- `available_at ≤ decision_at`；
- deterministic output digest；
- 不补数据、不把 silent 变零。

### D3：PIT 数据集、特征与 episode

冻结：

- ClockProfile；
- master opportunity universe；
- feature/state/zone 版本；
- shock/response/partial-order episode；
- scenario、first-hit、censoring；
- gap eligibility；
- DEVELOPMENT/CALIBRATION/HOLDOUT；
- purge/embargo；
- coverage and support minimums。

D3 只生成研究数据集，不评分模型。

### E2：回测、校准与一次性 holdout

必须在打开 holdout 前冻结：

- hypothesis versions；
- baseline/comparator；
- labels/horizons；
- costs、funding、slippage assumptions；
- coverage denominator；
- metrics and uncertainty；
- sensitivity grid；
- stop/support/failure conditions；
- trial registry；
- candidate code/config SHA。

只有一个明确 candidate 可以消耗一次性 holdout。打开后不修改参数、假说
文字、cohort、label 或 cost。

### E3：paper/testnet

前置：

- E2 对 exact candidate 的阶段决定；
- independent risk engine；
- OMS idempotency/reconciliation；
- data health、kill switch、protection；
- duplicate、partial fill、reject、timeout、disconnect、unknown order、
  stale data、clock anomaly 等 failure injection；
- account、credential、legal 和 operator 边界。

E3 仍不自动授权资金或实盘。

## 5. 权威数据获取矩阵

| 数据族 | 首选来源 | 主要用途 | 最关键缺陷 | 后备/交叉验证 |
| --- | --- | --- | --- | --- |
| 合约与元数据 | 目标交易所官方 | symbol、tick、multiplier、status | 历史版本变化 | 第二官方 venue / 专业库 |
| OHLCV/trades | 官方 archive/API | baseline、state、zone、RSI | 文件修订、单 venue | OKX/Bybit 或专业库 |
| mark/index/funding/OI | 官方 derivatives source | L/K、成本、拥挤 | OI 意图歧义、时钟 | Coin Metrics/Kaiko |
| liquidation | 官方可证明 source | F axis | silent 不等于 zero | 专业库、只做交叉验证 |
| strict L2 | 官方 sequenced data 优先 | C/R、fill context | 历史覆盖和序列 | Kaiko/CME 类专业产品 |
| COT | CFTC official | 低频传统期货背景 | 周频延迟、映射风险 | CME metadata |
| 宏观 vintage | BLS/BEA + ALFRED/FRED | K/event risk | release time、revision | 原始 release page |
| 执行成本 | exact target venue paper/fills | E3 fill/slippage | 无历史替代 | 保守压力区间 |

原则：

- A 级来源仍需实际 artifact 验证；
- B 级专业库用于弥补/交叉，不覆盖官方冲突；
- C/D 级内容只能生成假说；
- E 级不得进入模型；
- strict R 若长期无合格数据，应简化理论，而不是使用错误代理。

## 6. 历史数据 chronology 设计

### 6.1 角色

- `DEVELOPMENT`：特征、状态、假说和参数开发；
- `CALIBRATION`：ordinal-to-probability、threshold、cost 等映射；
- `HOLDOUT`：一次性最终评价；
- `SEEN_DIAGNOSTIC`：已看历史，仅可诊断，不能升级为 holdout；
- `CENSORED_TERMINAL`：永久断档或权威失败。

### 6.2 划分规则

- 先按时间顺序，不随机打乱；
- split 之前冻结 source coverage；
- purge 至少覆盖标签 horizon；
- embargo 防止相邻泄漏；
- 各角色包含足够的主要 state/side，但不能看到 outcome 后挑区间；
- support 不足就 `WAIT_DATA`，不能降低标准；
- 已见 January/February 永久不是未见数据。

具体日期和比例在 D0/D3 根据可获得的完整连续数据冻结，本 P0 不提前编造。

## 7. E2 最小实验阶梯

### E2-0 数据与标签基线

只验证：

- PIT；
- gap/censoring；
- first-hit；
- no-trade；
- simple direction/range base rate。

若这一步不稳定，停止增加指标。

### E2-1 简单状态与位置

模型：

- 单周期简单结构；
- 两周期结构；
- 当前五周期 profile；
- state+zone；
- random/shifted zone placebo。

目标：证明复杂状态/位置有增量。

### E2-2 RSI 消融

同一 master universe：

1. structure+position；
2. + fixed RSI 30/70；
3. + conditional RSIpct/slope/divergence；
4. full candidate without RSI。

若 RSI 无增量，移除或降级，而不是调更多 RSI 参数。

### E2-3 用户方法论路径

测试四条竞争路径：

- shock absorption/transition；
- squeeze then failure；
- balance；
- support consumption/tail break；
- OTHER/UNKNOWN。

事件起点和最大长度必须 outcome-free。

### E2-4 leverage/event

分别增加：

- OI/funding/basis/liquidation；
- official PIT event reaction；
- relative strength。

每族单独 ablation，不能联合加入后只报告整体改善。

### E2-5 strict resilience

仅在真实合格序列 L2 后执行：

- pressure only；
- price-volume-wick；
- strict impact+resilience；
- no-R；
- gap/ineligible。

否则保持 `WAIT_DATA` 或简化。

### E2-6 dynamic action geometry

使用相同 entry：

- fixed structural stop/target；
- time stop；
- monotone trailing；
- no target extension；
- profit-locked extension。

比较净结果、MFE、MAE、tail risk、turnover 和 cost。

### E2-7 full integration

最后才比较：

- simple trend；
- simple range；
- structure-only；
- finite-path system；
- full system；
- no-trade。

若 full system 没有稳定增量，优先保留更简单版本。

## 8. 指标

数据：

- qualified coverage；
- gap/censored；
- revision conflicts；
- PIT violations；
- state/side concentration。

状态：

- accuracy 或 proper categorical score；
- transition delay；
- state churn；
- UNKNOWN/ABSTAIN；
- simple baseline comparison。

假说：

- Top-1；
- Top-2 coverage；
- OTHER/UNKNOWN；
- falsifier response；
- expiry；
- elimination latency；
- calibrated Brier/log loss（仅校准后）。

决策：

- common-universe coverage；
- WAIT opportunity cost；
- middle-location error；
- premature entry；
- trigger-to-action latency；
- net EV interval。

交易/执行：

- win/loss distribution；
- MFE/MAE；
- profit capture；
- fill/no-fill；
- fees/funding/slippage；
- tail loss；
- order-state failures。

研究完整性：

- trial count；
- changed parameter count；
- PBO/DSR/Reality Check 等适用诊断；
- sensitivity stability；
- state/side support；
- holdout consumption receipt。

## 9. 假说失败处理

```text
冻结候选与负面结果
→ 检查数据/时钟/coverage
→ 检查 opportunity/label/window
→ 检查 state/zone
→ 检查 mechanism/path
→ 检查 dependence/calibration/selection
→ 检查 entry/stop/target
→ 检查 cost/fill/transport
→ 只改一个主要层
→ 新版本、新 chronology、新测试
```

两轮同根因未关闭，停止 Terra high 重复修补并提交 Sol。证据充分且简单模型
持续更优时，理论负责人应简化或终止具体假说版本。

## 10. 阶段性目标

### M0：P0 完成

- 理论、治理、来源、hypothesis、measurement、parameter、dispute、stage；
- strict validator；
- independent adversarial PASS；
- Sol P0 decision。

### M1：D0–D2 最小数据权威闭合

- 一个 exact product；
- OHLCV/trades/metadata；
- PIT/revision/gap；
- deterministic replay；
- 不包含策略结果。

### M2：D3 最小研究数据集

- baseline/state/zone/RSI；
- master universe；
- scenario/first-hit；
- coverage 合格。

### M3：E2-0 至 E2-3

- 简单基线；
- state/zone；
- RSI 消融；
- 用户方法论四路径。

只有 M3 证明有稳定增量，才投资高级数据。

### M4：E2-4 至 E2-7

- leverage/event；
- strict R；
- dynamic management；
- full integration；
- one-time holdout。

### M5：E3

- paper/testnet 工程和风险；
- 仍无资金和实盘权限。

## 11. 当前下一步

本轮：

1. 关闭 P0 registries 和 validator；
2. 由独立 Terra high 执行对抗复核；
3. 修复 deterministic defects；
4. 形成 artifact inventory、validation report 和 claim boundary；
5. 仅在完整 `REVIEW_READY` 后调用 Sol ultra。

若 Sol P0 PASS：

- 准备 D0 候选，不自动下载数据；
- 优先选择能验证 state/zone/RSI/用户四路径的最小官方数据；
- strict L2 和专业付费数据保持条件性后备，避免在基础理论未证明前投入高成本。
