# V3.1.1 修复、资格与后继实验日志

状态：`V3_1_1_RELIABILITY_FIXES_IN_PROGRESS_TARGET_SUPERSEDED_BY_V3_2_NO_EXPERIMENT_STARTED`

范围：`PUBLIC_NON_ACCOUNT_ONLY / LOCAL / NONE_LOCAL_SIMULATION / NON_EXECUTABLE`

明确排除：paper/live、账户、订单、凭据、资金、组合写回，以及恢复任何旧 s3/E0/E0B 或失败 V3.1 run。

2026-08-07 范围变更：用户要求在实验前把过度保守的行为政策升级为 V3.2 动态进攻体系。V3.1.1 的通用 P0 修复继续收口，但其 authority/qualification/target 全部保持未创建；完成代码不等于允许启动旧设计。

## 1. 不可改写的前身事实

- 旧 run：`v31-prospective-btcusdt-20260806t183742z`
- research：`READY_FOR_CYCLE / completed=1 / next=2`
- research checkpoint：`8ff47b9a81de570dc518b38cb1949119fdcc9d94c90314e7eab1ed58f3fa2c26`
- monitor：`FAILED_CLOSED / attempt=1 / outcome=0 / resume_allowed=false`
- monitor checkpoint：`6745fea805fcabd5a36224792bbb7864e0431ff3dfdfcee51e367255607e8b60`
- failure：`440e5714c2f10e2c8b5ba31582addc86c5c69b523cbf3356568c18b6879a5616`
- raw capture：不存在；精确外部响应与根因保持 `UNKNOWN`

裁决：monitor 永久失败优先于 research READY；旧 run 不重试、不修补、不推进、不计入后继目标。

## 2. 已知问题、根因与修复状态

| 问题 | 根因 | 版本化纠正 | 当前状态 |
|---|---|---|---|
| outcome 解析失败后没有 raw | parser 位于耐久 capture 之前 | capture-only transport、原子 raw+record、读回后纯 parser | 代码与故障注入通过，待正式 monitor 资格 |
| HTTP 4xx/5xx body 丢失 | `HTTPError` 被当作无 response | 保存有界真实 response body 后再解析 | 聚焦测试通过 |
| attempt-only crash 可能重取 | attempt/capture 恢复状态不完整 | attempt-only 永不二次 GET；只有已提交 capture 可本地恢复 | 聚焦测试通过 |
| 并发 wake 误判在途请求 | 无同 cycle resolution guard | 线程锁 + OS file lock 串行化 | 并发测试恰好一次 GET |
| transport failure receipt 孤立 | failure receipt 与 checkpoint 更新非原子 | orphan receipt 本地重绑，0 second GET | 聚焦测试通过 |
| failed 后仍可追加 parse | store transition 约束不足 | failed/terminal checkpoint 不可再追加 capture/parse | 聚焦测试通过 |
| clock 未冻结/可漂移 | provider/local 时间语义混合 | `L=2000ms / A=5000ms` 自摘要政策；变更在 attempt 前拒绝 | 边界测试通过，待 authority 绑定 |
| research READY 覆盖 monitor FAILED | 两 owner 没有总状态 | run-level Supervisor permit | 代码测试通过 |
| accepted 后 schedule crash 不可恢复 | 两 store 无 commit intent/material | 完整 write-once commit material + `COMMIT_RESERVED` + 确定性恢复 | 故障注入通过 |
| Cycle 8 accepted 冒充完成 | 终态只看 research | 双 `8/8 accepted+outcome` 才 `TERMINAL_COMPLETE` | Supervisor 测试通过 |
| Q7 typed AST 同名字段误报 | presentation 对已验证 typed bundle 深扫 | full loader 先验证，再精确投影五语义文档 | 正负测试通过 |
| 74 路径被误称完整闭包 | 显式清单不含递归 import | 静态本地闭包 + fresh-process trace union | 收集/漂移测试通过，待最终冻结 |
| 十二轴来源与投影缺失 | 旧十轴迁移且数据名与轴规则未接线 | 12 轴 direct/proxy/derived/UNKNOWN registry；PIT/admission/raw 图投影 | Domain/Application 测试通过，待 run-local 封存 |
| 单帧盘口/价格越级代理 | 缺少 forbidden proxy 规则 | 单帧 book 只能价格压力代理；清算/韧性/注意力/跨市场无来源即 UNKNOWN | 测试通过 |
| OI change 可跨周期错配 | previous accepted OI 未精确绑定 | 上一 admission+dataset+OI digest 与当前双 input 全匹配 | 测试通过 |
| 关联候选可事后变化 | 未冻结全集、窗口、lag、多重检验 | 96 候选；1H/4H；168/720；BY q=.05 + Holm alpha=.05 | 合同测试通过，结果仍未评价 |
| portfolio/reentry 范围不清 | 理论动作域与当前无账户实验混合 | 当前 run=`EXCLUDED_NO_CLAIM`，仅静态 FLAT shadow | 已冻结 |
| 预测/校准/净收益/regime 易被过度宣称 | 运行测试与市场证据未分层 | 独立评价合同；8 周期不得晋级 | 已冻结为 UNKNOWN/不适用 |
| fresh source/Codex/monitor 资格缺失 | 旧 Q6/Q7/Q8 不覆盖新 runtime | successor 三资格合同与 two-run authority lineage | 合同通过，正式资格未执行 |
| Agent lifecycle 只有 pure builder | 生产 controller 未实际写 context/consumption/commit envelope | controller-owned write-once 接线并由 full loader 深重放 | P0 修复进行中，未运行资格 |
| support role 可被任意 self-digest 冒充 | key 未绑定 exact schema/digest field | qualification/target exact role spec 和逐角色替换回归 | P0 修复进行中 |
| 完整理论只存路径/摘要 | Agent 无法直接读取冻结正文 | 内嵌完整 UTF-8 theory semantic document 并校验物理 SHA | pure contract 已通过，生产接线进行中 |
| permit 与 outcome crash tail 可能死锁 | 只识别理想 checkpoint 邻接状态 | 同 owner/cycle permit replay；已有 raw/accepted 的确定性 tail recovery | P0 修复进行中 |
| V3.1.1 行为仍过度保守 | UNKNOWN 统一压向 WAIT，正式 run 排除 portfolio/reentry | V3.2 typed UNKNOWN、probe、动态计划、双时钟 outcome queue | 已完成设计候选，代码未实现 |

## 3. 新理论与运行设计

- 理论增补：`CURRENT_RESEARCH_THEORY_v3_1_1_SUCCESSOR.md`
- 运行设计：`V3_1_SUCCESSOR_RUNTIME_DESIGN_2026-08-07.md`
- 需求权威：`requirements/2026-07-30-theory-paper-practice.md`
- V3.2 最新理论：`CURRENT_RESEARCH_THEORY_v3_2_DYNAMIC_AGGRESSIVE.md`
- V3.2 建议裁决：`V3_2_USER_RECOMMENDATION_ADJUDICATION_2026-08-07.md`
- V3.2 系统与实验设计：`V3_2_SYSTEM_AND_EXPERIMENT_DESIGN_2026-08-07.md`

核心决定：动态性与开放性保留在信息发现、假说新增和竞争路径；权限、时点、候选关联全集、单次网络尝试、提交顺序和实验分母必须有限冻结。

## 4. 当前验证记录

截至本日志创建时已实际完成：

- old active v2 full loader：Q0–Q8、物理证据、74 implementation bindings 通过；
- outcome capture/resolution、Supervisor、authority projection、runtime closure、关联/评价、十二轴 Domain/Application 的聚焦与交叉测试通过；
- accept→monitor 跨 store 崩溃边界：模拟 research CAS 后进程死亡，第二次只从同一 commit material 恢复，Agent 调用=0、outcome 读取=0；
- 旧 Cycle 1 source artifact 只读十二轴回放：22 个 source observation；没有把清算、韧性、事件、注意力或跨市场缺口补零。
- 全部 `test_theory_paper_v2_v31*.py`：332 项、160.106 秒、全部通过；这是本地 V3.1/V3.1.1 合同与回归证据，不是市场有效性证据。

本节只记录已运行的检查。最终完整测试计数、资格摘要、target run_id、各周期和终态将在后续追加。

## 5. 资格与实验状态

| 阶段 | 状态 | 说明 |
|---|---|---|
| qualification authority/run | `NOT_YET_FROZEN` | 必须与旧 run、target run 不同 |
| fresh public source | `NOT_YET_EXECUTED` | 必须 authority-postdating，12 个公开 GET raw 重放 |
| current root Codex durable delivery | `NOT_YET_EXECUTED` | qualification run 仅 1 个资格 cycle，不计 target |
| fixed monitor probes | `IN_IMPLEMENTATION` | 由真实故障注入 receipt 组成，不接受 caller 自报 PASS |
| qualification retirement | `NOT_YET_EXECUTED` | 不接 automation，不可计入 8/8 |
| final target authority/genesis | `NOT_YET_FROZEN` | 绑定三资格、闭包、V3.1.1 与旧失败 lineage |
| target accepted/outcomes | `0/8 + 0/8` | 尚未创建唯一 target run |

## 6. 评价证据状态

- 市场预测增量：`UNKNOWN_NOT_EVALUATED`
- 概率校准：`NOT_APPLICABLE_ORDINAL_ONLY`
- 成本后收益：`UNKNOWN_NOT_EVALUATED / EXCLUDED_NO_CLAIM`
- 跨 regime 泛化：`UNKNOWN_NOT_EVALUATED`
- 96 候选关联发现：`UNKNOWN_NOT_EVALUATED`

这些状态不会因本地测试、API 可达、accepted state 或最终 `8/8` 自动改变。

## 7. 工作区与清理边界

必须保留：

- 旧失败 run、qualification/target 的全部原始证据；
- 冻结理论、authority、manifest、receipt 和 runtime 字节；
- 用户既有未提交修改与 `THEORY_AND_EXPERIMENT_EVOLUTION_AUDIT_2026-08-05_副本.md`；
- 当前及归档 Codex 会话。

只允许清理本任务生成且可重建的 cache、临时目录和测试残留；不使用广域递归删除，不清理失败证据，不用 `git add .`，不把脏工作区误报为干净。
