# MSTA-HED 研究体系一致性与证据审计 v1.0

状态：`E0_STATIC_AUDIT`

审计快照：

- cwd：`/Users/wt/Documents/agent-trade-emotion`
- branch：`codex/s0-research-foundation`
- HEAD：`7ca3fc4f99a57f98217e703f222b295653ace87e`
- worktree：已有大量历史修改与未跟踪工件；本轮不把 dirty 状态解释为失败，
  但所有结论只绑定实际读取的物理文件。

## 1. 总结

当前理论已经从“指标直接预测涨跌”转向：

```text
多周期状态
→ 结构位置
→ 有限竞争假说
→ 证据更新
→ 情景与交易命题
→ 效用
→ 权限
→ 行动
→ 结果与修订
```

方向符合最初目标，但当前系统仍为多个版本化理论对象、历史合同和终止路线的
叠加，不是可直接回测或自动交易的统一系统。

当前最强证据仍为 E0：

- 合成合同可以验证一部分类型和不变量；
- 文献和官方文档可以支持定义、语义和候选测量；
- 尚无合格证据证明目标市场预测优势、成本后正期望、paper 或实盘可行；
- 原有 raw AuthorityBundle 路线已终止，不能用“等待更多数据”掩盖其结构性
  权威失败。

## 2. 当前路线事实

### 2.1 已确认

1. `CORE_TRADING_THEORY.md` 与 `CORE_TRADING_THEORY_v2_1.md` 字节一致，
   SHA-256 均为
   `2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d`。
2. 当前核心理论 v2.1 仍为只读权威，本轮候选不自动替代它。
3. V5-M00 的 Sol 结论是纯 E0 合成合同 PASS，不是 raw、市场、runtime、
   backtest 或交易 PASS。
4. 其后的 P1A-R3.1 因权威所有权、字段类型、时钟、payload、别名等 11 类
   反例被错误接受，进入 `TERMINAL_P1A_AUTHORITY_CHAIN_BLOCK`。
5. 旧 active-G1 数学上不可达，旧 P1A 路线不修复、不重开。
6. 新 Sol 路线只允许 P0 理论、来源文档、registry、measurement contract、
   pure validator、合成与对抗测试。
7. D0 数据获取至 E3 paper 全部仍关闭。

### 2.2 已看历史实验的正确含义

已有 January 2025 COIN-M 开发期诊断：

- 使用的是 `BTCUSD_PERP` COIN-M，不是当前拟定的 `BTCUSDT` USD-M；
- bookDepth 是约 30 秒的百分比聚合深度，不是真实逐序 L2；
- 候选两侧没有选出交易；
- 候选 log loss/Brier 未优于 D-only control；
- 状态覆盖集中，最终为 `WAIT_DATA_COVERAGE`。

该结果应表述为：

`SEEN_DEVELOPMENT + NEGATIVE_DESCRIPTIVE + INCONCLUSIVE_COVERAGE`

它不能验证严格 \(R\)（订单存活、撤单、补充和冲击后韧性），也不能否定整个
理论。它首先暴露 `MEASUREMENT` 与 `COVERAGE` 问题。

February 片段存在永久 23 分钟 bookDepth 断档，属于
`SEEN + WAIT_DATA_NOT_SCORED`，不能补跑或重新标为未见。

## 3. 最高影响的 22 项问题

| ID | 问题 | 证据 | 处置 |
| --- | --- | --- | --- |
| DSP-001 | 合成 PASS 与 raw 权威终止被混为连续成功路线 | `sol_decision.v5-m00...:1-11,104-117`; `sol_decision.p1a...:70-209` | 新路线；旧终局永久保留 |
| DSP-002 | 治理和路线图的“当前阶段”是旧快照 | `PROGRAM_GOVERNANCE.md:3-6,48-60`; `SYSTEM_DESIGN_ROADMAP.md:582-624` | 由新 Sol 决定和 stage contract 覆盖当前状态，不回写历史 |
| DSP-003 | `ENTER_PROBE` 同时表示确认后进入和响应未完成的早期试探 | `CORE...:417-446,503-510`; `ROADMAP:295-310` | 拆成两个 policy namespace |
| DSP-004 | 历史线性链把 Action 放在 Permission 前 | `CORE...:1084-1115`; `MSTA v0.6:38-52` | 冻结依赖 DAG，Permission 必须先于 Action |
| DSP-005 | State/Path 到 Scenario/TradeThesis/Outcome 缺少冻结映射 | `CORE...:1197-1235`; `MSTA v0.6:167-177` | D3/E2 前冻结 opportunity、scenario 和 action outcome |
| DSP-006 | proper score 曾错误瞄准非互斥机制支持 | `CORE...:1150-1160`; `V5 registry:342-378` | 只评价可观测互斥 scenario/action outcome |
| DSP-007 | 机制确认窗口可能包含结果 | `synthetic contract:213-252`; `CORE...:269-286` | 分离 antecedent/cutoff/confirmation/outcome |
| DSP-008 | 数据/时钟无效曾被写成市场机制反证 | `CORE...:1166-1172` | 数据失败为 INCONCLUSIVE，不是市场 falsifier |
| DSP-009 | OTHER、UNKNOWN、ABSTAIN 被混合 | `V5 registry:366-371`; `MSTA v0.6:183-190` | 三个对象、三个 denominator、三组指标 |
| DSP-010 | 周期 profile 同时被写为冻结和通用候选 | `CORE...:1250-1254`; `method:794-822`; `MSTA v0.6:62-72` | 当前 BTC profile 版本化，非通用事实 |
| DSP-011 | 100ms–4H 时钟与 1D/1W context 缺少接口 | `CORE...:345-353,1250-1254` | 新增 ClockProfile |
| DSP-012 | StructuralPosition 的 strength/consumption 可能后验构造 | `MSTA v0.6:74-88`; `TECH:54-64` | position、strength、consumption、uncertainty 分合同 |
| DSP-013 | 持仓后 target 是否可向外延伸存在策略冲突 | `CORE...:1015-1023`; `method:858-879` | NO_EXTENSION 与 PROFIT_LOCKED_EXTENSION 分命名空间 |
| DSP-014 | 旧 `Confirmation.EXECUTION_READY` 混合确认和权限 | `v0.4:103-119,228-263`; `TECH:35-48` | 历史对象只经 versioned adapter，不能直映 Permission |
| DSP-015 | max-abs 去重可能偏爱噪声，目标层又未校准 | `method:520-667` | 延后到 scenario 概率层比较三类聚合 |
| DSP-016 | ABSTAIN 可能通过丢弃困难样本改善分数 | `CORE...:1027-1033`; `V5 registry:342-378` | 冻结 gate-neutral master universe，报告 coverage-risk |
| DSP-017 | 旧权威字节和 prose-only hypothesis 没有完整 crosswalk | `research contract:27-38`; `v0.3:603-639`; `V5 decision:96-102` | 不改历史；新 registry 显式 lineage，旧缺口保留 |
| DSP-018 | registry 摘要声明缺少域前缀与 `0x00` 拼接公式 | 独立数学审查 F-001 | 七份工件显式声明完整公式并重算摘要 |
| DSP-019 | ER/RVOL 缺少零分母与非有限输入边界 | 独立数学审查 F-002 | typed `UNKNOWN`，禁止更新状态、分数或权限 |
| DSP-020 | challenger 仓位公式与核心 v2.1 的成本、尾部和单位约束冲突 | 独立数学审查 F-003 | 以当前核心公式为高权威，P0 保持 `max_risk=0` |
| DSP-021 | ordinal prior/weight 未登记，半衰期公式实际为时间常数 | 独立数学审查 F-004 | 禁止隐藏 prior/weight，冻结聚合器，补组/总 cap 并加入 `ln(2)` |
| DSP-022 | hard falsifier/expiry 仍为自然语言，独立实现可能分歧 | 独立数学审查 F-005 | 明确阻断 D3/E2；后续升级为版本化机器谓词 |

机器可读详情：
`config/research_system.dispute_registry.v1.json`。

## 4. 理论链审查

### 4.1 定义与观测

改进：

- Fact、Measurement、State、Mechanism、Path、TradeThesis、Utility、
  Permission、Action、Result 已分离；
- public aggregate data 的 participant identity 和意图边界明确；
- `UNKNOWN` 不是零。

未闭合：

- ClockProfile 尚未有真实源测试；
- StructuralPosition 的强度/消耗仍待独立测量；
- strict \(R\) 缺少合格序列数据。

### 4.2 数据与特征

改进：

- 采用 `available_at`、revision identity 和 gap/censoring；
- ER、ATRpct、RVOL、CLV、BodyEfficiency、RSIpct 都有公式和 undefined
  语义；
- RSI 不再直接产生订单。

未闭合：

- 所有参数仍是 initial assumption；
- 不同 venue 的量、合约单位和时钟未实际验证；
- source registry 目前只登记文档。

### 4.3 基础假设与机制

改进：

- 机制允许共存；
- 参与者意图被降为低可观测机制线索；
- 压力—冲击—韧性有独立窗口要求。

未闭合：

- 机制到 observable scenario 的映射未经过市场数据；
- L/F/K 数据族的增量价值未知；
- 机制库可能缺失或冗余。

### 4.4 状态、路径与决策

改进：

- 二维状态：方向×阶段；
- 有限路径池强制包含 OTHER/UNKNOWN；
- 用户案例已抽象为可变长度部分顺序，不是八日模板；
- 市场路径与交易位置、成功概率和权限分离。

未闭合：

- 当前周期组合未证明优于更简单 profile；
- scenario label、master opportunity 和 action-specific outcome 要在 D3
  前冻结；
- ordinal ranking 尚不能输出 probability。

### 4.5 风险与执行

改进：

- 止损位于结构失效外，而不是固定百分比；
- 持仓后风险单调不扩大；
- fill/cost/no-fill/market path 分离。

未闭合：

- 无目标 venue 的 fill、滑点、延迟和费用证据；
- target extension policy 仍需作为两个独立 challenger；
- 无 paper 或 OMS 证据。

## 5. 数据来源审计

### 5.1 已登记的 A 级候选

- Binance 官方 archive 与 USD-M 技术文档；
- OKX 官方 API/order-book 与历史数据目录；
- Bybit 官方 order-book 文档；
- CFTC COT 官方数据库与方法；
- FRED/ALFRED vintage API；
- BLS 与 BEA 官方统计/日历/修订；
- CME DataMine 官方交易所产品；
- Cont–Kukanov–Stoikov、Gneiting–Raftery、White、Lo–Mamaysky–Wang、
  Hamilton、Almgren–Chriss、PBO、Deflated Sharpe 等原始高质量研究。

### 5.2 已登记的 B 级候选

- Kaiko 专业数据库；
- Coin Metrics 专业数据库；
- Adams–MacKay changepoint 原作者预印本。

### 5.3 关键限制

- 官方不等于完整；
- 公开网页不等于数据文件已取得；
- API 可访问不等于历史 PIT 可用；
- archive checksum 只能验证文件身份，不能证明全市场覆盖；
- 专业付费数据不自动成为 A 级；
- 论文只支持其样本和假设，不能证明目标 crypto/perpetual 策略；
- 宏观 observation date 不能替代 release/available time；
- COT 是延迟聚合背景，不是 15 分钟信号；
- snapshot/aggregated depth 不能替代 strict sequenced L2。

## 6. 当前内容分类

### 6.1 已确认

- 类型必须分离；
- PIT 与 revision 不能穿越；
- ordinal score 不是 probability；
- OI 和聚合量价不能唯一识别参与者意图；
- 旧 active-G1 不可达；
- 旧 P1A 权威路线终止；
- 数据/合同失败不能解释为市场假说失败；
- 构建、独立复核和阶段批准必须分权。

### 6.2 暂时支持

- 文献在其他市场/样本中支持 order-flow imbalance、depth 与短时 impact
  的关系；
- proper score、data-snooping 控制和 execution cost separation 有正式
  方法基础；
- 技术形态可以被客观计算和经验检验。

这些仅为方法/transport 前提，不是目标市场策略证据。

### 6.3 优先待验证

- 多周期状态相对简单 profile 的增量；
- StructuralPosition；
- RSI 条件化及其消融；
- strict pressure–impact–resilience；
- 有限路径与 OTHER/UNKNOWN；
- 用户案例抽象出的四条竞争路径；
- leverage/forced-flow context；
- event reaction 风险门；
- evidence dependency de-dup；
- dynamic risk 与 execution realism；
- full integrated system 最后验证。

### 6.4 已归档或终止

- “固定八日普遍规律”：因用户需求澄清而归档为误读，不是市场 falsification；
- RSI 低于 30 或高于 70 直接下单；
- 从公开聚合数据计算精确参与者人数/机构计划；
- 旧 active-G1 恢复路线；
- 旧 P1A v0.1.3 权威链修补路线。

### 6.5 尚未否定

January 的负面描述没有否定 strict \(R\)、多周期系统或用户方法论；原因是
产品、测量、覆盖和 action selection 均不满足严格理论合同。它必须作为负面
证据保留，但不能被反向包装为支持。

## 7. 不可验证命题清单

下列命题在没有更高等级、合法取得的参与者级数据时，不能进入正式模型：

- “机构正在吸筹”作为事实；
- “大户将发布利好”；
- “多数人已经跑路”；
- “当前成交量代表某类人数”；
- “某一次十字星必然见顶/见底”；
- “某个固定日数后必然上涨或下跌”；
- 未经校准的“当前路径概率 70%”；
- 无执行数据的“订单一定成交”；
- 无成本数据的“策略正期望”。

这些可以被改写为可观测机制假说或风险场景，但不能保持不可证伪主体叙事。

## 8. 当前系统符合最初方向吗

方向上符合：

- 先理论和动态策略；
- 再历史验证；
- 根据结果局部修订；
- 多周期、情绪/压力、历史、宏观四层被纳入；
- RSI 作为触发而非核心预测器；
- 入场、止损、目标和动态管理均有理论位置。

阶段上尚未达到：

- 没有权威 raw 数据准入；
- 没有统一 D3 数据集；
- 没有合格回测/校准/holdout；
- 没有 paper；
- 没有真实执行证据。

因此当前系统是“可进入严格研究准备”的候选，而不是“已经能够参与市场”的
自动交易系统。

## 9. 审计结论

当前最正确的下一步不是继续增加指标，也不是直接回测已有代码，而是：

1. 完成 P0 strict registries、validator 和 independent review；
2. Sol 审核 P0；
3. 单独 D0 选择最小权威数据组合；
4. 按 D1–D3 解决 raw、PIT、revision、gap 和 measurement；
5. 从简单状态/结构基线开始 E2；
6. 对每个失败先做错误归因，再只改一个理论层；
7. full integration 最后测试。

这条路线允许多提假设、优先验证弱假说，同时保留可证伪性与防止事后过拟合。
