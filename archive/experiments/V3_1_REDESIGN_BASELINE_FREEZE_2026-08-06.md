# V3.1 重设计前实验基线冻结记录

## 1. 裁决

- 冻结对象：`native-codex-btc-pilot-s3-20260806t0942z`。
- 冻结原因：用户于 2026-08-06 改变工作顺序，要求先完成 V3.1 理论、系统更新和验证，再创建新实验。
- 状态：`PAUSED_BY_REQUIREMENT_CHANGE / BASELINE_ONLY / NOT_A_MARKET_FAILURE / DO_NOT_RESUME`。
- 已完成：Cycle 1/4；未启动：Cycle 2–4。
- 禁止：续跑、回写 accepted 工件、补造 halt/failure receipt、读取未来结果或将本次暂停解释为预测结果。
- 执行边界：`NONE_LOCAL_SIMULATION`，`order_sent=false`，`account_accessed=false`。

## 2. 冻结时实际状态

- 冻结核验时间：`2026-08-06T10:50:50Z`。
- checkpoint：`status=READY_FOR_CYCLE`，`cycle_index=2`，`total_cycles=4`，`revision=4`。
- checkpoint 语义摘要：`fc18847d32db0bd09582c644d3643c4101eb9de675706830a076453dc51f912c`。
- checkpoint 物理 SHA-256：`7b4292149d65ea9bcaeaf69bfe0d56b2f252dbf8989231cb9ee000bc8e40a288`。
- controller：`actual_state=PAUSED`，`desired_state=PAUSED`，`kill_switch_engaged=true`，`run_permission=false`，`next_action=NOOP_STOPPED`。
- controller current 物理 SHA-256：`e272ad0f00c73e5fd5ae94632ad7050134d5b478b31107b5aa01e2c2f0c34992`。
- heartbeat：`btc-agent` 已更新为 `PAUSED`，且明确禁止承担 V3.1 新实验。
- heartbeat 配置物理 SHA-256：`37370785113b960cdba14a78ed65099b0f60d586af6f625779b1b2aa34244021`。

## 3. Manifest、配置与授权绑定

| 对象 | 语义摘要 | 物理 SHA-256 |
|---|---|---|
| run manifest | `53d6a65f1f222416040cb1bbd7fed41e6c1c9bd46c28d9c0866e6b52c346f2f8` | `2009fa9f4e35c2679021406de078ddb44a679344d43ad233f2b4abe8083846cb` |
| config source v4 | `8de86115c2ec6a627409ff52d13676b05ddfa0e1d69010b797f6cd950516383f` | `624e1cfa0c146739366e0d549542b954662ef54225c663d27326c09493c72ef3` |
| authorization receipt v4 | `ff00f872fb3bbf20804fd181c4ef8fcbb4c0b595d1ab0def759c27419c75a2e7` | `d65f0ba076fc69d5bcc1fd1cabcac8046ba10374a1531f53806cd20eb9f01fef` |
| pre-suspension current authority | 不作为继续运行授权 | `433ddd6852762f797513956983e609b4613ba7cd2f8e7eae753c941bf8ea15d2` |

说明：manifest 内部还绑定了复制进 run 的 frozen authority/config/receipt；本记录不修改这些历史副本。项目级 current authority 已另行改为 `SUSPENDED_THEORY_V3_1_REDESIGN`，从而阻止旧入口继续运行。

## 4. Cycle 1 不可改写证据

| 对象 | 语义摘要 | 物理 SHA-256 |
|---|---|---|
| market snapshot | `9edea443b940a1b3353d91ec2c3ab53f778ba9b830f40a5c90348b52573429d6` | 由 accepted state 与原周期收据绑定 |
| sentiment state | `bc777140c6f3ad4b88a81322cd0453ac8db8e0a19b83cbf7834f8ab7af55eae8` | 由 accepted state 与原周期收据绑定 |
| proposal payload | `75ab70ae72049b9c9f6bb0b3e744d8cf4a23ad6c814157fce44e363b1455b0b2` | 由原 transport 收据绑定 |
| deterministic evaluation | `5724576bb5c9d938d9dfd5825c4fc912320c764d56c7555a0138ac4dadf9c6bf` | 由原周期收据绑定 |
| accepted state | `451eae1db96897a7d89e734a4df30a1774ba2414ae389a05283039b13d3d96bc` | `ed84f019fc2a4bb85715dad280e6da461d118acfebb7fa1cc003be7a8f962965` |
| cycle report | `840724992070aed6c1bb97716a356c3c247044acc973f0ff51ef1d9cd9560fd8` | `235350fc10a225ab6f9949f8456aca5c2e90cd94bd955356159d70832214f880` |
| completion receipt | `8c2f457f254e9f4278deccb3d23a07858dc9cd07360e1f9bd5ecd97583762827` | `8c4e5946d0619c739de80d103beb6708e6f22a1e128eab9866c41553e7a03d6d` |

Cycle 1 的原始选择为不可执行 `WAIT`。该事实只证明当轮流程和当时已知语义门通过，不证明方向预测、增量价值、盈利、跨状态泛化或生产就绪。

## 5. V3.1 后续实验边界

V3.1 文档、实现和验证全部完成后，如需进行新周期实验，必须使用：

1. 新理论版本与物理摘要；
2. 新 schema/配置/授权收据；
3. 新 run id、空 checkpoint 与未见 future outcome；
4. 新评价合同，且在观察结果前冻结；
5. 新的 heartbeat 或明确的一次性控制流程，不得复用本 `btc-agent`；
6. 仍保持不可执行、无账户、无订单、无资金权限。
