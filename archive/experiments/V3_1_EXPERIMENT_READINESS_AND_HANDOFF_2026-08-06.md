# V3.1 新周期实验资格与运行交接

- 日期：2026-08-06
- 需求记录：`requirements/2026-07-30-theory-paper-practice.md` §三十三
- 冻结理论：`CURRENT_RESEARCH_THEORY_v3_1_DRAFT_FOR_REVIEW.md`
- 理论 SHA-256：`ceee2b5fdb6962e4ae42ba32cdf980e44830b69a2c833289e472593cf3d92553`
- 唯一 run：`v31-prospective-btcusdt-20260806t183742z`
- 当前结论：`CYCLE_1_ACCEPTED / OUTCOME_ATTEMPT_1_FAILED / MONITOR_FAILED_CLOSED / RUN_TERMINAL_NO_RETRY`
- 外部执行权限：`NONE_LOCAL_SIMULATION / NO_PAPER / NO_LIVE / NO_ACCOUNT / NO_ORDER / NO_FUNDS`

## 1. 结论

用户已经批准冻结的 V3.1 理论内容，并授权一个全新的、公开数据、不可执行 `BTC-USDT-SWAP` 前瞻实验。Q0–Q8 已由可重建 typed receipts 和外部耐久证据关闭，active authority、run genesis、正式首周期与独立 outcome monitor 均已建立。旧 `s3/v1.3/v1.4/E0/E0A/E0B` 继续保持原状，不得恢复或复用。

首周期由当前 Codex 任务作为唯一 Strategy Agent 完成开放分析、确定性语义编译、封存后动作选择和六对象接受，选择为 `WAIT`。在合法 1H 结果窗口内，系统先耐久预留唯一 attempt，随后公开 OKX adapter 因 `V31_OUTCOME_PUBLIC_VALUE_INVALID` 失败；monitor 已永久 `FAILED_CLOSED`，没有 outcome receipt，Cycle 2 未启动且不得启动。该结果证明失败关闭生效，也暴露 outcome 原始响应未在解析前耐久化的设计缺陷。

## 2. 已关闭的资格门与冻结权威

| 门 | 当前状态 | 关键边界 |
|---|---|---|
| Q0 理论—实验范围 | `PASS` | 只评价 manifest 纳入能力；连续组合、数值概率、EV 等排除项不得形成结论 |
| Q1 理论权威 | `PASS` | 绑定用户批准的 V3.1 物理文件和 approval receipt |
| Q2 十二轴情绪 | `PASS` | PIT contributor、冲突、覆盖和 UNKNOWN 全链绑定；无总情绪概率 |
| Q3 动作/组合范围 | `PASS` | 仅研究动作；portfolio mutation、paper/live 明确排除 |
| Q4 耐久语义重放 | `PASS` | typed assembly bundle、六事件、checkpoint 和跨进程重放失败关闭 |
| Q5 关联证据 | `PASS` | 只开放冻结的 Pearson/Fisher pair universe；其他统计/因果能力不宣称 |
| Q6 外部来源 | `PASS` | 单次公开 OKX 采集，raw、44 条 PIT datum、5 条 UNKNOWN 均耐久绑定 |
| Q7 当前 Codex Agent | `PASS` | proposal 与 post-seal selection 分阶段、单次交付、编译后才允许选择 |
| Q8 固定评价/监控 | `PASS` | elapsed-1H 绝对 mark 规则、单次 outcome attempt、OTHER/UNKNOWN 与停止门事前冻结 |

资格 receipt digest：

- Q0 `fd1491ca2ce7f75c95d5cf9411b2499fccf527a1492dd6dbcdcc5b7a7fea8473`
- Q1 `e4379a687fa859f8559914c1964a4c5de9de858b4c75dac84ebb04c2aba2ac73`
- Q2 `0d47e2e4ceca997d9f7273e79cba90ca34078dac5808d732e54b221ffe44fd7a`
- Q3 `8c32d39b827f444bad986f682316495d298064d8e3ee7a8868b9a4690c5051b6`
- Q4 `4168d1ed86fcfddf97b0b104026e61bcc2ef14f3f68f1ac32516e5bcd798988a`
- Q5 `61f58a113864c166ca4e25a3a85321b2dc4c39fdd4e16bb2198460dba3eee070`
- Q6 `4316a3f0dd4da99a4e8e7b0f4865ee8a2214bc2a63255001c678dd3dc2009e56`
- Q7 `a27696ea3528d6f84ddff53f8f31b0139ea25aff85815370628dcf94d26df67c`
- Q8 `6a91c6752815346efe859517adf0ec4188a8387fab794500e2f9d97ab31ea752`

冻结对象：

- experiment contract digest：`a3d66ed528f13089d05b12655de0065c835f23016c6511fee2da38ffdc72ae73`
- manifest digest：`f75a37c7a6a910b30ca452b45b4ef086a17f1251b7affd60e0496109ba9017b8`
- authorization receipt digest：`034fead618a731aa47ba4ca9897a84bd46dc333bc3252672f14455d25b412579`
- active authority digest：`e11ece4ce46aba8902fbe93373ed24941eab659e6177be1f07f53eac1d7a32fc`
- run genesis digest：`766497fe894fa0ee827670eefd98986479f5773a81adea98d37d20db6b265531`

## 3. 资格与启动中遇到的问题

| 问题 | 原始处理 | 当前解决方案与边界 |
|---|---|---|
| Q7 第一次 stdin 在 payload 前收到 EOF | `...183742z-q7` 永久 `FAILED_CLOSED` | 保留原始失败，不修改、不重试同一 root |
| Q7 第二次 canonical PTY 行缓冲无法接收完整 JSON | `...183742z-q7-attempt2` 永久 `FAILED_CLOSED` | 保留失败；第三个独立 root 使用 non-canonical/no-echo byte transport，每阶段新 worker |
| Q7 成功证据 | `...183742z-q7-attempt3` 完整交付 | transport evidence digest=`9248677e17a4450d63537524b2f9281f5fa6551d7dc14a0baf221abf9b9b2181`，选择 `WAIT` |
| 首个正式 source qualification ID 不符合冻结语法 | `...v31-formal-source-cycle1-20260806t185157z` 在 plan/checkpoint/network 前拒绝，仅留锁目录 | 不复用、不删除；使用新合法 ID |
| 冻结 presentation helper 对 Q7 typed AST 中的 `NONE_LOCAL_SIMULATION` 产生深扫描误报 | 首次正式 admission 在写入前只读失败 | 先运行完整 authority loader，验证 Q0–Q8、外部物理证据及 74 个冻结 runtime 文件；应用调用只接收其中五份已验证授权语义文档。未改 frozen runtime、未绕过完整 loader |
| heartbeat 创建参数两次在控制面校验前被拒绝 | 未创建任务、无实验副作用 | 按控制面返回的 schema 修正后仅创建一个任务，并核对旧任务全部仍为 `PAUSED` |
| Cycle 1 outcome 适配器拒绝公开值 | 唯一 attempt 后 `V31_OUTCOME_PUBLIC_VALUE_INVALID`，monitor 永久 `FAILED_CLOSED` | 不重试、不补取、不推进 Cycle 2；保留 attempt/failure/checkpoint。successor 改为 raw-before-parse，并冻结 provider/local clock-skew 合同 |
| outcome 失败响应未耐久保存 | raw 写入发生在 adapter 成功返回之后，语义拒绝时只留下错误码 | 精确根因保持 UNKNOWN；禁止把“交易所时钟领先”写成事实。successor 必须对响应先 write-once，再解析/归一化 |
| research/monitor 双 checkpoint 分裂 | research 仍为 `READY_FOR_CYCLE / next=2`，monitor 已 `FAILED_CLOSED` | 当前以 monitor 终局并暂停唯一入口；successor 必须增加统一 supervisor gate，在 source/prepare/Agent 前拒绝 outcome gap 或 monitor failure |

上述 presentation helper 是当前唯一已知的运行期适配缺陷。因为其文件字节已经被 active authority 冻结，实验进行中不得修改；当前投影方案只缩小下游输入，不改变或跳过上游完整验证。应在本 run 终止后另建新 authority 才能修复代码。

## 4. 正式 Cycle 1

### 4.1 点时市场记录

- 决策时刻：`2026-08-06T18:52:52.950875Z`
- mark：`64366.1 USDT/BTC`
- 15m：收益 `-0.16560065%`，成交量/中位数 `0.7611`
- 1h：收益 `-0.21412879%`，成交量/中位数 `0.6448`，区间 `0.4517811%`
- 4h：收益 `+0.01517%`，成交量/中位数 `1.9965`
- 1d：收益 `+0.856456%`，成交量/中位数 `1.0073`
- 订单簿 top-5 imbalance：`+0.51295`
- recent trades imbalance：`-0.188395`
- funding：`+0.00003545`
- OI：`31719.0771 BTC`；跨周期 OI change=`UNKNOWN`
- liquidation、新闻/叙事、跨市场、拥挤变化、流动性韧性和尾部压力中无合格数据的部分均保持 `UNKNOWN`，未填零。

### 4.2 Agent 公开分析与选择

- 机制竞争：短周期回撤/主动卖压与盘口买方吸收并存；长周期并未给出同向确认。
- lead：短周期下行延续，方向 `SHORT`。
- runner-up：bid absorption 后反弹，方向 `LONG`。
- `OTHER/UNKNOWN` 保持开放。
- 十二轴中有三项 `NEGATIVE`、一项 `NEUTRAL`、一项 `MIXED`、七项 `UNKNOWN`；没有生成总情绪分或未校准数值概率。
- 完整合法动作经过编译后均可选择；最终动作=`WAIT`，selected_at=`2026-08-06T19:08:52.844349Z`。
- WAIT 原因：短周期方向压力与盘口吸收冲突，关键杠杆/清算/尾部/事件/跨市场信息缺失；机会成本是可能错过任一方向的首段突破，下一复核由冻结监控阈值触发。

正式工件：proposal envelope digest=`0753cb9d4dde73e41cec22d9925b2883a62787bbb06913be279d98b6a9ed9aa2`；semantic compilation digest=`80173786c42d6d1a7cc1ca6d269bf5cfc0c1f9ebdccd24abfda1452f53465605`；formal transport evidence digest=`2b465f292e1328800126dcde47c50296edaf38b92c3b7b2524d0c0f009b94c35`；accepted state digest=`118d5acceb71d8daf5759c4076fd668e190a931a60c9a9743d575fe9d7101ad7`；completion digest=`c6bc98cb296825a54471d86268e5f7f507651d7ebe09159f02aef56e5afb11b1`；research checkpoint digest=`8ff47b9a81de570dc518b38cb1949119fdcc9d94c90314e7eab1ed58f3fa2c26`。

## 5. Outcome monitor 与下一边界

- monitor plan digest：`23a691161b439e6dd224fca1a30e2b2890730fe162b49a4223f019406d3e2303`
- 当前 monitor checkpoint：`FAILED_CLOSED / resume_allowed=false`，digest=`6745fea805fcabd5a36224792bbb7864e0431ff3dfdfcee51e367255607e8b60`
- outcome window：`2026-08-06T19:52:52.950875Z` 至 `2026-08-06T20:07:52.950875Z`
- confirmation：mark `<= 64075.3`
- contradiction：mark `>= 64656.9`
- hard falsifier：mark `>= 64947.7`
- 语义：决策后 elapsed-1H 的首个公开 PIT mark，不是把任意秒决策伪装成整点 closed candle。

唯一 attempt digest=`64ce943d9840ba564ef7e178c56cb0e81ff84f10a6a7e28b9bfd157b8aba0132`；failure digest=`440e5714c2f10e2c8b5ba31582addc86c5c69b523cbf3356568c18b6879a5616`；outcome count=`0`。heartbeat `v3-1-btc` 在记录终局后暂停；旧任务继续 `PAUSED`。

当前 run 已无合法下一状态：不得重试 outcome、不得把失败改成 UNKNOWN outcome、不得推进 Cycle 2。后续只能离线修正 successor 设计、重新测试和冻结新 authority；创建新 run 需要用户另行授权。

## 6. 当前可确认与不可确认

可以确认：V3.1 已完成一次正式 accepted cycle，真实公开 source、当前 Codex 两阶段交付、确定性编译、六对象接受和失败关闭均在同一条不可执行主链发生；outcome raw-before-parse 缺口也由真实运行暴露，而非由测试推测。

仍不能确认：Cycle 1 没有合法 outcome，不能评价 lead/runner、路径或动作表现；更不能证明市场预测增量、校准、盈利、跨 regime 泛化或生产就绪。冻结合同没有启用合格 calibrated forecast，因此本 run 不计算或宣称 Brier、log score、ECE、EV、margin 或 entropy。
