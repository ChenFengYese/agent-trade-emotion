# Theory Agent V2 E0A 传输修订 v0.1

状态：`FROZEN_BEFORE_SUCCESSOR_ROLE_CALL`

修订类型：`TRANSPORT_ONLY_SUCCESSOR`

证据等级：`PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`

## 1. 失败证据

首个正式 run `native-codex-action-e0a-btcusdt-20260801T064710Z` 的 manifest
digest 为 `3ef7153fe04e0e06ef1584a0e3d5f05fcc6a4b2538af59d2ee9a55ef6ac6780f`。
sample 128 的 Single、Proposer 和 blind Challenger 均被明确声明为正式调用，但
clean worker 没有获得位于总控上一工具输出中的 packet，分别返回缺包错误。

总控依冻结协议停止：没有合法 semantic output、没有 event、没有 checkpoint 推进、
没有 outcome read。该 run 永久保留为失败证据，不得重试或改称 diagnostic。

## 2. 独立传输诊断

在不写正式 run 的 diagnostic 中，总控生成 sample-128 `cluster-proposal` packet：

- canonical packet byte length：`15402`；
- packet digest：`90887ee568a5ba535ec0c8091f4f3c3a54cf643f02008572b6630c7eef873f21`；
- context digest：`b749e2a9cb0688ace6cacafe404e147705840bcce2346bbd38a48827b4193d9b`；
- selector choice count：`2`。

一个 `fork_turns=none` clean diagnostic child 在 spawn 的 initial message 本身收到完整
packet，并原样回传上述四个锚点；没有使用路径、文件、前文继承或分段续送，未观察到
截断。该结果只证明 direct-inline 可用，不计入正式样本。

## 3. Successor 冻结协议

`INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1` 是 successor 的唯一角色输入
传输：

1. 总控生成完整 canonical role packet；
2. `spawn_agent` 必须使用 `fork_turns=none`；
3. initial message 必须直接包含完整 packet 字节对应的 UTF-8 JSON，不得仅包含路径、
   digest、前文引用或“读取上一工具输出”的指令；
4. role 不得调用文件、工具、网络、memory 或外部数据；
5. role 输出必须绑定 exact context/state digest；
6. 每个 output envelope 保存 packet digest、byte length、child task ID、fork mode、
   controller-observed tool/external-data 状态，以及模型/token 不可证明状态；
7. Proposal 与 blind Challenger 分别由 clean child 接收共同 context packet；blind
   Challenger packet 不含 proposal；Selector packet 才能包含已冻结的 proposal 与
   challenge；
8. 任何 packet 缺失、截断、schema 错误或角色越权均停止 successor，不得再次更换
   transport 后隐藏失败。

## 4. 保持不变的实验身份

Successor 必须与冻结设计 v0.1 保持：

- source dataset、indices `128..159` 和 32 context 内容；
- 8 profile、supervision 分配、11 动作和 selector choice sets；
- 金融公式、风险上限、成本、path matrix、评分和 terminal verdict order；
- Single-Strong 与 blind 三角色拓扑；
- `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`；
- outcome terminal gate、无概率/EV、无 automation/paper/live/account/order。

Successor manifest 必须证明其 32 个 context digest 与失败 run 逐 index 完全相等。只有
transport config、run ID、manifest 和 handoff 可以不同。
