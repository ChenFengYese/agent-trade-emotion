# V3.3.2 用户指定范围、修订与冻结声明

版本：`3.3.2-complete-market-analysis-candidate.3`

状态：`USER_DIRECTED_SCOPE / FROZEN_THEORY_REVIEW_CANDIDATE / USER_REVIEW_REQUIRED / NON_EXECUTABLE`

## 1. 用户选择

用户于 2026-08-12 先后明确选择：

1. V3.3.1 保持冻结，不扩充、不改写；
2. 在 V3.3.2 建立完整市场分析手册；
3. 数据不足不删除机构、公司、散户、套牢盘、错误叙事等机制，它们可作为未验证但可行动的竞争假说；
4. 闪迪 USDT/SNDKx 历史分析作为用户验证且可扩充的教学案例；
5. V3.3.2 是实验理论版本，可突破旧版对理论范围的既定限制；
6. 市场认知建立后，继续补全动态交易、动态仓位、参考执行、风险预算、跨周期连续性和评价归因；
7. 直接修改当前 V3.3.2 候选，解决已知理论缺口，完成后先交由用户审查，不急于实验。
8. 交易 Agent 自己决定是否继续近端观察或请求稍后恢复；监控 Agent 只处理运行许可、登记和恢复，不判断市场；每个资产由独立交易 Agent 负责。
9. 放弃测试网优先路线，后续改用简化但可审计的纸面交易、账户、仓位和数据工作台；当前只做理论与系统设计，不开发、不运行市场实验。
10. 系统架构、唤醒、账户、订单、日志和 UI 必须归入系统类文档，不与市场知识、动态交易和仓位知识体系混写。
11. 在修改文档前，允许进行一次不接市场、不读写账户的最小 Goal/子 Agent 秒级恢复探针。

因此，candidate.3 是用户对 candidate.2 冻结规则的最新、明确覆盖，不是系统自行扩张。该覆盖仅授权本次理论与系统设计更新及上述最小运行探针；candidate.3 校验完成后重新冻结。后续 Agent 不得以旧边界回退本次内容，也不得以本次授权推导市场实验、纸面交易实现或真实交易权限。

## 2. 本实验版本明确扩充的理论范围

V3.3.2 candidate.3 允许并要求：

- 从 price-only 骨架扩充为价格、成交、微观结构、杠杆、事件、情绪、基本面、跨资产和参与者 proxy 的完整市场认知；
- 在数据缺失时保留会改变路径、动作或仓位的机制假说，并明确观测等级与证伪条件；
- 对机构护盘、吸筹、派发、公司维稳、错误叙事和操纵风险建立条件路径，而不把它们冒充已观测事实；
- 把市场核心形式化为多尺度状态识别、状态转换、行为主体假说和动态证伪；
- 把 calendar clock 与 market-event clock 分离；
- 区分战略 episode、当前参考敞口、目标参考敞口、仓位变化和参考执行意图；
- 定义开仓、试探、持有、加仓、减仓、止盈、平仓、再入场、对冲和反转的状态转换；
- 定义 tranche、CORE、TACTICAL、HEDGE、PROBE、RUNNER 的角色、独立风险和退出义务；
- 定义风险预算层级、无交易区、迟滞规则、冲突优先级、数据降级和产品特有风险；
- 独立评价市场认知、路径、动作、仓位、转换、参考执行、真实执行、风险治理和机会成本；
- 将用户验证经验登记为 `USER_VALIDATED`，进入教学和后续前瞻比较；
- 为未来合格数据定义状态转移与 timing 模型，但不把所有方法压缩成技术指标打分。
- 把“继续观察、何时复核、何时释放注意力”纳入交易 Agent 的动态决策和独立评价；
- 只在理论中定义注意力语义，把 Goal、唤醒账本、Agent 生命周期和纸面交易台实现移交系统蓝图。

## 3. 本选择不取消的上位边界

“实验版本忽略既定边界”只适用于理论范围、分析方法和评价结构，不取消：

- V3.3.1 理论、manifest 与旧 run 的原字节只读；
- 合法数据、raw-first、PIT、`available_at`、未来隔离和不回填；
- 事实、测量、潜在状态、主体假说与主体意图分层；
- 缺少校准时不输出伪精确 probability、sum-to-100、margin、entropy 或 EV；
- 不读取未授权账户、凭据、订单和资金，不启用 paper/testnet/live；
- 不制造或传播虚假信息，不实施市场操纵；
- 文档、案例和本地校验不等于预测有效、仓位有效、成本后盈利或生产可用；
- 系统不得覆盖 Agent 的市场认知、假说、参考动作、参考仓位和复盘语义；
- 当前所有交易、仓位与执行内容均为公开数据下的不可执行参考理论。

## 4. Candidate.1 的保留与本次修订证据

candidate.1 是中间理论候选，不是 Git 已跟踪基线。为使本次用户授权的原地修订可恢复，修改前已保存精确归档：

```text
archive:
/Users/wt/.local/state/agent-trade-emotion/theory-backups/
v3.3.2-complete-market-analysis-candidate.1-20260812T211500+0800.tar.gz

sha256:
ed20745365dbd675fd20f23ecb838b2c7a1821bfd04ddeb566a97f6b614f18ed
```

归档只用于恢复 candidate.1 字节，不是市场证据，也不授权把旧候选重新路由为当前理论。

## 5. Candidate.2 的保留与 Candidate.3 冻结政策

candidate.2 修改前已保存精确归档：

```text
archive:
/Users/wt/.local/state/agent-trade-emotion/theory-backups/
v3.3.2-complete-market-analysis-candidate.2-20260812T231500+0800.tar.gz

sha256:
9b684af8ed6946efb76164ce1256f1afd1f61ff36b8e2527e45fef4a4e0dc78a

candidate.2 manifest sha256:
42112555e7e7c079f4479e23b14054d112ef7d1af3ec68ea4b69ba9c50ce3eed
```

candidate.3 在正文、理论/系统分类、链接、manifest、摘要、编码和 V3.3.1 不变校验完成后冻结为：

`FROZEN_THEORY_REVIEW_CANDIDATE / USER_REVIEW_REQUIRED / NON_EXECUTABLE`

```text
candidate.3 frozen bytes
→ user reviews theory
→ no experiment before a separate user decision
→ no in-place semantic edit after this freeze
→ correction or expansion creates a new revision/version
→ any experiment uses a new theory/run identity
```

manifest 只证明候选字节身份与包内一致性，不证明市场预测、动态仓位、参考执行或盈利能力。

## 6. 当前运行与路由边界

本版本不接管、恢复或修改任何 V3.3.1 实验。完成 integrator 合并后，本目录可成为 `theory/CURRENT.md` 的当前审查路线，但 `CURRENT_REVIEW_ROUTE` 不等于 runtime 路由或实验激活。本次没有启动市场数据采集、回测、paper/testnet/live、账户或订单动作。

已执行的唯一运行探针只验证同一活跃 Goal 任务树内的秒级消息与原子 Agent 恢复；探针没有市场输入、文件副作用或交易能力。证据与边界只记录在系统 owner [`design/CURRENT_BLUEPRINT.md`](../../../design/CURRENT_BLUEPRINT.md)，不作为理论或市场有效性证据。
