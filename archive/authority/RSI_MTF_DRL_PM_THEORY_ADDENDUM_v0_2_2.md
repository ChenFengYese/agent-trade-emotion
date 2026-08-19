# RSI-MTF-DRL-PM Theory Addendum v0.2.2

> 状态：`REVIEW_CANDIDATE / E0 / REJECT_FREEZE`  
> 阶段：`P0-RSI-01C — outcome-free contract serialization repair`  
> 日期：2026-07-23  
> 性质：v0.2.1 的最小语义修订；不授权数据接入、回测、paper、OMS 或交易

---

## 0. 规范地位、版本边界与当前授权

### 0.1 复合理论

本文件不是独立策略，也不复制 v0.2.1 的全部规范。`v0.2.2` 的完整理论是以下四个不可替代、按顺序组合的 artifact：

1. `CORE_TRADING_THEORY.md` v2.0，raw SHA-256  
   `06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d`；
2. `config/rsi_mtf_drl_pm.research_contract.v0_2.json`，full canonical SHA-256  
   `38d572453045016bbdc314d184f9be87a608ec8bc36aabaf92d8c0ce742201e5`；
3. `RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md`，raw SHA-256  
   `021053480fe9a49b3902803e2d363793416a120263551fb741fb3444af6550fd`；
4. 本文件的 raw bytes 与外部计算的 `v0_2_2_delta_raw_sha256`。

本文件不得嵌入自身摘要。P0-RSI-01C builder 必须从冻结后的原始字节计算第四项，再计算：

```text
composite_theory_id =
  ID("rsi-mtf-drl-pm-composite-theory/v0.2.2", {
    core_raw_sha256,
    v0_2_contract_canonical_sha256,
    v0_2_1_addendum_raw_sha256,
    v0_2_2_delta_raw_sha256
  })
```

新 contract 的唯一 ID 为：

```text
rsi-mtf-drl-pm-v0-2-2-outcome-free-contract
```

目标路径为：

```text
config/rsi_mtf_drl_pm.research_contract.v0_2_2.json
```

旧 v0.2.1 文件是已失败但可审计的 immutable input；不得修改、重写或以 erratum 替换。旧 v0.2 contract 也必须保持原样。

### 0.2 覆盖规则

解释顺序固定为 CORE → v0.2 contract → v0.2.1 addendum → 本文件。本文件只覆盖本文件明确列出的 clause、schema、domain、字段或算法；其他 v0.2.1 规范继续有效。

覆盖的规范单位不是自然语言相似句，而是下表的精确路由：

| v0.2.1 规范单位 | v0.2.2 处理 |
|---|---|
| §1.2 composite/candidate identity | 由本文件 §2 完整替换 |
| §1.3 source object 通用排序 | 由本文件 §3.2 完整替换 |
| §2.1–§2.7 source/control schemas | 由本文件 §3–§7 对应 successor schema 完整替换 |
| §2.8–§2.9 synthetic event/bundle | 保留未改语义；版本、artifact union、scope、BARRIER payload 与 identity 由 §9 替换 |
| §4.4 OI completeness | 由 §5.5 完整替换 proof window |
| §5.1 U event/receipt 语义 | 由 §6.1 完整替换 |
| §5.2、§6.1、§7、§10、§12.3 source selection | 由 §5 的统一 selector 约束 |
| §9.1 RULE_CHANGE 映射 | 由 §5.3 与 §10.3 完整替换 |
| §9.1 BARRIER_EVALUATION payload | 由 §9.3 完整替换 |
| §9.2 reducer priority | 由 §10.1 完整替换 |
| §9.2 submission descendant time | 由 §10.2 完整替换 |
| §10.1–§10.2 Pivot/Target source identity | 由 §11 完整替换歧义字段 |
| §11 FrozenLedgerSeed/FrozenActionContext/bindings | 保留未改字段；新增或替换字段由 §8、§12 指定 |
| §12.1 Pi_exit priority object | 由 §10.1 successor object 替换 |
| §12.2 SharedEntryAction authority | 由 §8 完整替换为 sealed proof authority |
| §12.4 dynamic EV bindings | 由 §7.4、§9.3 完整替换 |
| §12.5 label bindings | 由 §12.2 完整替换 |
| §13 baseline/challenger identity | 由 §2.2 完整序列化；数值集合不变 |
| §14 route | 由 §14 完整替换 |

若一个实现需要为未列出的冲突选择解释，必须返回 `SPEC_CONFLICT`。禁止通过默认值、alias、字段猜测、lex winner 或 adapter 补义。

### 0.3 权限交集与停止条件

当前唯一授权工作是：

```text
P0-RSI-01C = serialize v0.2.2 contract + validator schema + negative contract tests
```

仍然禁止：

- source/exchange adapter、reader、数据库、网络、历史数据下载；
- backtest、parameter search、calibration、holdout；
- execution simulator、paper、OMS、exchange connector；
- API key、账户、资金、订单或真实市场操作；
- 将 synthetic PASS 描述为 predictive validity、execution realism 或交易可用性。

授权按所有适用层的交集计算，`ALLOW ∩ DENY = DENY`。本文件冻结前，P0-RSI-01C 也不得启动。冻结条件是独立 reviewer 对 §13 的每一项给出 `PASS` 且原始文件 SHA 在审查前后不变。

---

## 1. 统一原子规则

v0.2.1 §1.1 的 `UtcUs`、`DecimalString`、`QtyBase`、`Price`、`Money`、`Bps`、`Sha256`、`StableId`、decimal128、rounding 与 tick/lot 规则继续逐字有效。

Canonical JSON 与 `ID(d,x)` 也继续逐字有效。所有本文件新增 schema：

- 必须是 exact-key object；
- 所有 key 必须存在；
- 只有明确声明的字段允许 `null`；
- 禁止 float、隐含默认、字段 alias、unknown enum；
- 修改字段集合或含义时必须使用本文件的 v0.2.2 schema literal 与 domain；
- 同一 identity preimage 对应不同 canonical bytes 时必须 `CONFLICT`，不得选一个。

`Scope4` exact object：

```text
{
  venue_id:string,
  instrument_id:string,
  lane_id:string,
  availability_kind:enum{SYNTHETIC,ACTUAL,RECONSTRUCTED}
}
```

当前 P0-RSI-01C/02/03 唯一允许：

```text
lane_id = "E0_SYNTHETIC_CANONICAL_V0_2_2"
availability_kind = "SYNTHETIC"
ledger_identity.role = "SYNTHETIC"
```

任何 `DEVELOPMENT`、`CALIBRATION`、`HOLDOUT`、`ACTUAL` 或 `RECONSTRUCTED` object 进入当前 bundle、evidence、fixture manifest 或 ledger，均必须拒绝。

---

## 2. Candidate、参数与 policy registry

### 2.1 旧 contract slice 的机械绑定

令 `V02` 为第 0.1 节固定 canonical digest 对应的旧 JSON object。以下摘要必须从该 exact artifact 的 JSON Pointer 机械计算，不能复制文字或选择子字段：

```text
v0_2_controls_sha256 =
  SHA256(CanonicalJSON(V02["controls"]))

v0_2_entry_contract_sha256 =
  SHA256(CanonicalJSON(V02["entry_contract"]))

v0_2_risk_execution_contract_sha256 =
  SHA256(CanonicalJSON(V02["risk_execution_contract"]))

v0_2_label_contract_sha256 =
  SHA256(CanonicalJSON(V02["label_contract"]))
```

Expected values：

```text
v0_2_controls_sha256 =
  80f0c203f7ce02ffc5ef65c9a85e541e8bacdcbb44c8e7e34f33fa4e07e7d436
v0_2_entry_contract_sha256 =
  fef9822cc1cc504ac8bc93b8f6f7a9bc951f658549508bba9c215d36e46f47e0
v0_2_risk_execution_contract_sha256 =
  77db59ac12a17ae650457751523f459e3cbe0adad8bed465480d442e79332b36
v0_2_label_contract_sha256 =
  7171baca5be3047494a91c9e2292c786cfe1a28aea9db1b7d1f2b6e3f5c68019
```

字段不存在、JSON 类型不符或旧 full canonical digest 不等于 §0.1 固定值时，builder 必须停止为 `BASE_ARTIFACT_MISMATCH`。

### 2.2 `ParameterSet.v0.2.2`

Top-level exact keys：

```text
schema_version
variant_kind
challenged_key
adverse_pressure_min_consecutive_seconds
k_threshold
abs_d_threshold
r_threshold
l_upper_threshold
responding_bps
u_active_seconds
u_cooldown_seconds
ev_min_n
synthetic_barrier_ack_latency_seconds
parameter_set_sha256
```

类型与固定值：

```text
schema_version =
  "rsi-mtf-drl-pm.parameter-set.v0.2.2"

variant_kind = enum{BASELINE,ONE_LAYER_CHALLENGER}

challenged_key =
  enum{
    ADVERSE_PRESSURE_MIN_CONSECUTIVE_SECONDS,
    K_THRESHOLD,
    ABS_D_THRESHOLD,
    R_THRESHOLD,
    L_UPPER_THRESHOLD,
    RESPONDING_BPS,
    EV_MIN_N
  } | null

adverse_pressure_min_consecutive_seconds:int
k_threshold:DecimalString
abs_d_threshold:DecimalString
r_threshold:DecimalString
l_upper_threshold:DecimalString
responding_bps:Bps
u_active_seconds:int
u_cooldown_seconds:int
ev_min_n:int
synthetic_barrier_ack_latency_seconds:int
parameter_set_sha256:StableId
```

BASELINE exact values：

```text
challenged_key = null
adverse_pressure_min_consecutive_seconds = 5
k_threshold = "1.5"
abs_d_threshold = "0.1"
r_threshold = "0.6"
l_upper_threshold = "-0.0005"
responding_bps = "5"
u_active_seconds = 1800
u_cooldown_seconds = 900
ev_min_n = 30
synthetic_barrier_ack_latency_seconds = 1
```

ONE_LAYER_CHALLENGER 必须有且只有 `challenged_key` 指向的一项偏离 baseline，且该项只能取：

```text
ADVERSE_PRESSURE_MIN_CONSECUTIVE_SECONDS -> {1,10}
K_THRESHOLD                             -> {"1","2"}
ABS_D_THRESHOLD                         -> {"0.05","0.2"}
R_THRESHOLD                             -> {"0.5","0.7"}
L_UPPER_THRESHOLD                       -> {"-0.001","0"}
RESPONDING_BPS                          -> {"3","8"}
EV_MIN_N                                -> {60,100}
```

其余项必须逐字等于 baseline。当前 P0-RSI-01C/02/03 只允许 `BASELINE`；challenger 只是为未来另行授权的 P0-RSI-04 冻结合法空间。

```text
parameter_set_sha256 =
  ID("candidate-parameter-set/v0.2.2",
     entire object excluding parameter_set_sha256)
```

### 2.3 Exact policy objects

所有 policy object 的 `stage_role` 在当前阶段固定 `"SYNTHETIC"`, `composite_theory_id` 等于 §0.1 的计算结果，`parameter_set_sha256` 等于 §2.2 BASELINE。

#### `UPolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
v0_2_controls_sha256,
partition_rule,master_selection_rule,dedup_rule,cooldown_rule,
u_active_seconds,u_cooldown_seconds,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.u-policy.v0.2.2"
partition_rule = "UTC_HALF_OPEN_CYCLES_FROM_UNIX_EPOCH"
master_selection_rule = "FIRST_VALID_GATE_NEUTRAL_U_ON_CLOSED_15M_GRID"
dedup_rule = "ONE_MASTER_OPPORTUNITY_PER_CYCLE"
cooldown_rule = "SUPPRESS_NEW_MASTER_UNTIL_MASTER_PLUS_ACTIVE_PLUS_COOLDOWN"
u_active_seconds = ParameterSet.u_active_seconds
u_cooldown_seconds = ParameterSet.u_cooldown_seconds
```

`policy_sha256=ID("u-policy/v0.2.2", entire object excluding policy_sha256)`。

#### `EntryPolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
v0_2_entry_contract_sha256,
formula_scope,source_selector_policy_sha256,
decision_proof_required,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.entry-policy.v0.2.2"
formula_scope = "V0_2_1_SECTIONS_3_TO_8_AS_OVERRIDDEN_BY_V0_2_2"
decision_proof_required = true
```

`source_selector_policy_sha256` 必须等于 §5.6；  
`policy_sha256=ID("entry-policy/v0.2.2", entire object excluding policy_sha256)`。

#### `ExitPolicyTemplate.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
formula_scope,pi_exit_policy_sha256,reducer_priority_policy_sha256,
source_selector_policy_sha256,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.exit-policy-template.v0.2.2"
formula_scope = "V0_2_1_SECTIONS_9_10_12_AS_OVERRIDDEN_BY_V0_2_2"
```

三个引用摘要按字段顺序分别等于 v0.2.2 `PiExitPolicy`、§10.1 与 §5.6 的重算结果。  
`policy_sha256=ID("exit-policy-template/v0.2.2", entire object excluding policy_sha256)`。

#### `CostPolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
v0_2_risk_execution_contract_sha256,
fee_bps_per_side,worst_slippage_bps_per_side,
funding_buffer_bps,tail_bps,accounting_rule,policy_sha256
```

Exact values为 `"5","10","5","10"`，`accounting_rule` 固定  
`"V0_2_1_SECTION_8_AND_11_CURRENT_INVENTORY_BASIS_NO_DOUBLE_COUNT"`。

`policy_sha256=ID("cost-policy/v0.2.2", entire object excluding policy_sha256)`。

#### `RiskPolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
v0_2_risk_execution_contract_sha256,
risk_formula_scope,pending_deadline_seconds,
rule_snapshot_change_action,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.risk-policy.v0.2.2"
risk_formula_scope = "V0_2_1_SECTIONS_8_9_11_AS_OVERRIDDEN_BY_V0_2_2"
pending_deadline_seconds = 2
rule_snapshot_change_action =
  "PRE_SUBMIT_ABSTAIN_POST_SUBMIT_DATA_HEALTH_INVALID"
```

`policy_sha256=ID("risk-policy/v0.2.2", entire object excluding policy_sha256)`。

#### `LabelPolicyBinding.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
v0_2_label_contract_sha256,first_hit_label_policy_sha256,
label_scope,policy_sha256
```

`schema_version="rsi-mtf-drl-pm.label-policy-binding.v0.2.2"`；  
`label_scope="V0_2_1_SECTION_12_5_AS_OVERRIDDEN_BY_V0_2_2"`；  
`policy_sha256=ID("label-policy-binding/v0.2.2", entire object excluding policy_sha256)`。

#### `DataRolePolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
allowed_ledger_roles,allowed_evidence_roles,allowed_availability_kinds,
required_lane_id,fixture_manifest_required,
real_source_adapter_authorized,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.data-role-policy.v0.2.2"
allowed_ledger_roles = ["SYNTHETIC"]
allowed_evidence_roles = ["SYNTHETIC"]
allowed_availability_kinds = ["SYNTHETIC"]
required_lane_id = "E0_SYNTHETIC_CANONICAL_V0_2_2"
fixture_manifest_required = true
real_source_adapter_authorized = false
```

`policy_sha256=ID("data-role-policy/v0.2.2", entire object excluding policy_sha256)`。

#### `EstimatorPolicy.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,parameter_set_sha256,stage_role,
estimator_kind,lcb_confidence,minimum_n,y_r_lower,y_r_upper,
sample_window_rule,chronology_rule,policy_sha256
```

Exact values：

```text
schema_version = "rsi-mtf-drl-pm.estimator-policy.v0.2.2"
estimator_kind = "HOEFFDING_SUPPORT_WIDTH_4_ONE_SIDED_95_LCB"
lcb_confidence = "0.95"
minimum_n = ParameterSet.ev_min_n
y_r_lower = "-1"
y_r_upper = "3"
sample_window_rule = "EXACT_MATCH_BUCKET_EXPANDING_PAST_ONLY"
chronology_rule = "TERMINAL_PLUS_LABEL_TAIL_NOT_AFTER_SAMPLE_END"
```

`policy_sha256=ID("estimator-policy/v0.2.2", entire object excluding policy_sha256)`。

### 2.4 `PolicyBundle.v0.2.2` 与 candidate

Exact keys：

```text
u_policy_sha256
entry_policy_sha256
exit_policy_template_sha256
cost_policy_sha256
risk_policy_sha256
label_policy_sha256
data_role_sha256
estimator_policy_sha256
policy_bundle_sha256
```

前八项必须各自命中 `PolicyRegistry.v0.2.2` 中恰好一个合法 object。

```text
policy_bundle_sha256 =
  ID("candidate-policy-bundle/v0.2.2",
     entire object excluding policy_bundle_sha256)

candidate_id =
  ID("rsi-mtf-drl-pm-candidate/v0.2.2", {
    composite_theory_id,
    parameter_set_sha256,
    policy_bundle_sha256
  })
```

### 2.5 `PolicyRegistry.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,
v0_2_controls_sha256,v0_2_entry_contract_sha256,
v0_2_risk_execution_contract_sha256,v0_2_label_contract_sha256,
parameter_set,u_policy,entry_policy,exit_policy_template,
cost_policy,risk_policy,label_policy,data_role_policy,
estimator_policy,source_selector_policy,
policy_bundle,candidate_id,registry_sha256
```

每个 nested object 必须满足本节或 §5.6、所有重复摘要逐字相等，且只允许一个 BASELINE candidate。exit、label 的外部引用还必须分别解析到 bundle 中唯一 PI_EXIT_POLICY、REDUCER_PRIORITY_POLICY 与 FIRST_HIT_LABEL_POLICY static artifact，逐字验证其摘要。构造顺序唯一为：ParameterSet → U/Cost/Risk/DataRole/Estimator/SourceSelector → PiExit → Entry/ExitTemplate → FirstHit → LabelPolicyBinding → PolicyBundle → candidate_id → Registry；禁止通过 placeholder hash 形成循环。

```text
schema_version = "rsi-mtf-drl-pm.policy-registry.v0.2.2"
registry_sha256 =
  ID("policy-registry/v0.2.2",
     entire object excluding registry_sha256)
```

---

## 3. Source scope、schema 与同类排序

### 3.1 Canonical source schemas

以下 successor schema 完整替换同名 v0.2.1 schema。各 source 的 `schema_version` 必须取本节 literal；`quality` 只允许本节 enum。

#### `ClosedMarkBar.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_id,stream_generation_id,period_seconds,
bar_open_at_us,bar_close_at_us,closed_at_us,lane_available_at_us,
close_price,source_sequence,quality,payload_sha256,stable_bar_id
```

约束：

```text
schema_version = "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2"
availability_kind enum{SYNTHETIC,ACTUAL,RECONSTRUCTED}
stream_generation_id:StableId
period_seconds enum{900,14400}
source_sequence:int>=0
quality enum{VALID,INVALID,GAP,CONFLICT}
bar_close_at_us - bar_open_at_us = period_seconds * 1_000_000
bar_open_at_us 与 bar_close_at_us 对 Unix epoch period grid 对齐
bar_close_at_us <= closed_at_us <= lane_available_at_us
```

```text
payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and stable_bar_id))
stable_bar_id =
  ID("closed-mark-bar/v0.2.2",
     entire object excluding stable_bar_id)
```

slot identity 是 `(venue_id,instrument_id,lane_id,availability_kind,source_id,stream_generation_id,period_seconds,bar_open_at_us)`。同 slot 相同 bytes 去重；不同 payload、close、close/availability time 或 quality 一律把 slot 判为 `CONFLICT`，不得 tie-break。

#### `BookSnapshot.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_id,book_generation_id,event_time_us,lane_available_at_us,
source_sequence,best_bid,best_ask,bids,asks,
sequence_contiguous,quality,payload_sha256,event_id
```

`Level` exact keys仍为 `price:Price,qty_base:QtyBase`。v0.2.1 的价阶、数量、crossed book 与连续性约束继续有效，并新增：

```text
schema_version = "rsi-mtf-drl-pm.book-snapshot.v0.2.2"
event_time_us <= lane_available_at_us
```

```text
payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and event_id))
event_id =
  ID("book-snapshot/v0.2.2", entire object excluding event_id)
```

#### `AggTrade.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_id,stream_generation_id,event_time_us,lane_available_at_us,
source_sequence,price,qty_base,buyer_is_taker,quality,
payload_sha256,event_id
```

`schema_version="rsi-mtf-drl-pm.agg-trade.v0.2.2"`，`event_time_us<=lane_available_at_us`，price/qty>0。

`stream_generation_id:StableId`，`source_sequence:int>=0`。

```text
payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and event_id))
event_id =
  ID("agg-trade/v0.2.2", entire object excluding event_id)
```

#### `OpenInterest.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_id,stream_generation_id,event_time_us,lane_available_at_us,
source_sequence,oi_base,quality,payload_sha256,event_id
```

`schema_version="rsi-mtf-drl-pm.open-interest.v0.2.2"`，`event_time_us<=lane_available_at_us`，oi_base>0。

`stream_generation_id:StableId`，`source_sequence:int>=0`。

```text
payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and event_id))
event_id =
  ID("open-interest/v0.2.2", entire object excluding event_id)
```

`BookSnapshot.book_generation_id:StableId` 且
`source_sequence:int>=0`。所有 source schema 都要求
`venue_id/instrument_id/lane_id/source_id` 为非空 string。当前阶段 scope 必须满足
§1 的 E0 literal。

### 3.2 `OrderedSourceProjection.v0.2.2`

不存在跨 schema 的 `event_class_rank`，也不存在全体 artifact 通用 source order。

`OrderedMarketSourceKind` 是封闭 enum：

```text
CLOSED_MARK_BAR, BOOK_SNAPSHOT, AGG_TRADE, OPEN_INTEREST
```

仅为比较而临时重算的 projection exact keys：

```text
object_kind,venue_id,instrument_id,lane_id,availability_kind,
economic_time_us,lane_available_at_us,source_sequence,
source_object_id,payload_sha256,generation_id
```

accessor 表：

| kind | economic_time_us | source_object_id | generation_id |
|---|---|---|---|
| CLOSED_MARK_BAR | `bar_close_at_us` | `stable_bar_id` | `stream_generation_id` |
| BOOK_SNAPSHOT | `event_time_us` | `event_id` | `book_generation_id` |
| AGG_TRADE | `event_time_us` | `event_id` | `stream_generation_id` |
| OPEN_INTEREST | `event_time_us` | `event_id` | `stream_generation_id` |

projection 不持久化、不是 artifact、不得改变 payload hash。

排序只允许在同 `object_kind`、同 `Scope4`、同 `source_id`、同 schema version 的 homogeneous collection 内使用：

```text
(economic_time_us, source_sequence, source_object_id) ascending
```

CoverageSeal、VenueInstrumentSnapshot、AccountRiskSnapshot、FrozenEVEvidence、policy、receipt、manifest 与 derived proof 不参加这个顺序。不同 source kind 必须放在不同 typed field；禁止先拼接再排序。§9 reducer priority 也绝不能作为 source-object rank。

### 3.3 Source collision

在相同 `(schema_version,Scope4,source_id,generation_id,source_sequence)` 下：

- canonical bytes 相同：幂等去重；
- source_object_id 相同但 bytes 不同：`CONFLICT`；
- source_object_id 不同：`CONFLICT`；
- generation 或 source 不同：不能靠 lex 选择，必须由 consumer 的 exact selector 与 coverage proof决定是否 admissible。

---

## 4. Exact coverage

### 4.1 `CoverageSeal.v0.2.2`

Coverage 只证明一种 source kind 的一个 `(a,b]` 窗口，不再声称证明 reducer replay。`CanonicalSyntheticEventBundle.coverage` 是 reducer event-array coverage 的唯一 authority。

Top-level exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_id,source_schema_version,covered_object_kind,
window_start_exclusive_us,window_end_inclusive_us,lane_available_at_us,
generation_ranges,covered_event_ids,covered_event_set_sha256,
event_count,observed_gap_intervals,complete,seal_sha256
```

Exact literals/types：

```text
schema_version = "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2"
covered_object_kind =
  enum{CLOSED_MARK_BAR,BOOK_SNAPSHOT,AGG_TRADE,OPEN_INTEREST}
window_start_exclusive_us < window_end_inclusive_us
window_end_inclusive_us <= lane_available_at_us
```

`GenerationRange` exact keys：

```text
generation_id:StableId
first_source_sequence:int>=0
last_source_sequence:int>=0
event_count:int>0
```

`generation_ranges` 按 `generation_id` 小写 hex 严格升序。对每个 range：

```text
first_source_sequence <= last_source_sequence
event_count = last_source_sequence - first_source_sequence + 1
```

并且该 generation 的 `covered_event_ids` 所解析出的 source sequence 必须恰好包含区间内每个整数一次；缺一、重复或越界都使 seal invalid。没有 covered event 时 `generation_ranges=[]`。

`covered_event_ids` 必须：

1. 恰好列出 bundle.artifacts 中同 schema、同 source_id、同 Scope4、经济时间落在 `(window_start_exclusive_us,window_end_inclusive_us]` 的全部 source objects；
2. 每个 ID 唯一命中一个相应 source artifact；
3. 按 §3.2 homogeneous order 严格排序；
4. 无重复、无额外、无遗漏。

上述第 1 项还要求每个 covered object 的 `lane_available_at_us<=seal.lane_available_at_us`。若 bundle 中存在同 scope/source/kind、经济时间在 window 内、但 availability 晚于 seal 的 source object，则该 seal 不得 `complete=true`；late arrival 不能被一个更早的 complete seal静默排除。

```text
covered_event_set_sha256 =
  ID("coverage-covered-event-set/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    source_id,source_schema_version,covered_object_kind,
    window_start_exclusive_us,window_end_inclusive_us,
    covered_event_ids
  })

event_count = len(covered_event_ids)
```

`Gap` exact keys仍为：

```text
start_exclusive_us,end_inclusive_us,
reason enum{SEQUENCE_GAP,CONNECTION_GAP,IMPORT_GAP,CONFLICT}
```

每个 gap 必须在 seal window 内，按 `(start_exclusive_us,end_inclusive_us,reason)` 严格排序且互不重叠。

```text
complete = true
```

当且仅当：

- `observed_gap_intervals=[]`；
- exact covered set check PASS；
- 每个 generation 的连续整数 check PASS；
- 所有 referenced source object 的 `quality=VALID`，且 BOOK_SNAPSHOT 的 `sequence_contiguous=true`；其他三个 kind 没有额外 contiguity field；
- 没有同 identity conflict。

空窗口可 `complete=true`，但只允许 `covered_event_ids=[]`、`generation_ranges=[]`、`event_count=0`、gap=[]；consumer 是否接受空集由其公式决定。

```text
seal_sha256 =
  ID("source-coverage-seal/v0.2.2",
     entire object excluding seal_sha256)
```

### 4.2 唯一 seal binding

任何需要 coverage 的 consumer 必须显式保存一个 `coverage_seal_artifact_id`，并逐字段验证 scope、kind、source schema、window、availability 与 digest。

匹配 seal：

- 0 个：`UNKNOWN`；
- 相同 artifact ID 的完全重复：去重；
- 2 个或更多不同 artifact ID：`COVERAGE_CONFLICT`；
- 禁止取 min/max/lex/latest。

窗口规范统一为 `(a,b]`。若旧公式声明：

```text
[a,b]   -> (a-1,b]
[a,b)   -> (a-1,b-1]
(a,b)   -> (a,b-1]
```

其中 `1` 表示 1 微秒；若减法下溢或转换后空/倒置，输入 invalid。原本就是 `(a,b]` 时不转换。

---

## 5. Snapshot schemas 与统一 selector

### 5.1 `VenueInstrumentSnapshot.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
contract_kind,effective_at_us,lane_available_at_us,
tick_size,lot_step,min_qty,max_qty,min_notional_usdt,max_notional_usdt,
max_leverage,initial_margin_rate,fee_bps_per_side,
rule_fingerprint_sha256,quality,payload_sha256,snapshot_id
```

Exact constraints：

```text
schema_version =
  "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2"
contract_kind = "LINEAR_USDT_PERPETUAL"
quality enum{VALID,INVALID,CONFLICT}
effective_at_us <= lane_available_at_us

当 quality=VALID 时，所有 DecimalString 必须可精确解析，且：
tick_size > 0
lot_step > 0
min_qty > 0
max_qty >= min_qty
min_notional_usdt > 0
max_notional_usdt >= min_notional_usdt
max_leverage > 0
0 < initial_margin_rate <= 1
fee_bps_per_side >= 0
```

anchor 时唯一 admissible baseline snapshot 还必须逐字段等于：

```text
tick_size="0.1"
lot_step="0.001"
min_qty="0.001"
max_qty="10"
min_notional_usdt="5"
max_notional_usdt="20000"
max_leverage="2"
initial_margin_rate="0.5"
fee_bps_per_side="5"
```

且其 exact baseline fingerprint 必须是：

```text
560b1f3623316659f86eb385d7637ff71d8a67cef3499010e3499971e24a1f77
```

```text
rule_fingerprint_sha256 =
  ID("venue-rule-fingerprint/v0.2.2", {
    contract_kind,tick_size,lot_step,min_qty,max_qty,
    min_notional_usdt,max_notional_usdt,max_leverage,
    initial_margin_rate,fee_bps_per_side
  })

payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and snapshot_id))

snapshot_id =
  ID("venue-instrument-snapshot/v0.2.2",
     entire object excluding snapshot_id)
```

baseline literal 只约束 anchor selector 的成功结果，不约束 anchor 后的 snapshot。后续
snapshot 只要满足上述 structural validity，便可保持相同 fingerprint 或产生不同
fingerprint；相同 fingerprint 不是 rule change，不同 fingerprint 必须进入
`RULE_CHANGE` 路径。`quality!=VALID` 或任一 structural range 失败属于 data
health/UNKNOWN，不能伪装成 `RULE_CHANGE`，也不能被 selector 选中。

### 5.2 `AccountRiskSnapshot.v0.2.2`

Exact keys：

```text
schema_version,account_scope_id,venue_id,instrument_id,lane_id,
availability_kind,source_id,effective_at_us,lane_available_at_us,
equity_usdt,available_balance_usdt,existing_initial_margin_usdt,
open_order_reserve_usdt,pending_fee_reserve_usdt,
position_qty_base,position_vwap,open_order_ids,
quality,payload_sha256,snapshot_id
```

Exact constraints：

```text
schema_version =
  "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2"
quality enum{VALID,INVALID,CONFLICT}
effective_at_us <= lane_available_at_us
0 <= available_balance_usdt <= equity_usdt
所有 reserve >= 0
position_qty_base = "0" iff position_vwap = null
```

`account_scope_id/source_id` 非空。`open_order_ids` 去重并按 UTF-8 bytes 严格升序。v0.2.1 的 E0 balance、pre-submit zero position/order、post-submit exact account projection 与 mismatch 规则继续有效。

```text
payload_sha256 =
  SHA256(CanonicalJSON(object excluding payload_sha256 and snapshot_id))

snapshot_id =
  ID("account-risk-snapshot/v0.2.2",
     entire object excluding snapshot_id)
```

### 5.3 Exact selector functions

所有 selector 都是纯函数。输入 collection 是已通过 exact schema、artifact scope 与 collision validation 的集合。任何 `CONFLICT` identity 在 selector 前失败；selector 不用于掩盖 conflict。

定义：

```text
SourceQuery exact keys =
  venue_id,instrument_id,lane_id,availability_kind,
  source_id,source_schema_version
```

#### `SelectBook(query,tau_us,max_age_us)`

eligible 当且仅当：

```text
schema_version = query.source_schema_version
Scope4、source_id 与 query 逐字相等
quality = VALID
sequence_contiguous = true
event_time_us <= tau_us
lane_available_at_us <= tau_us
0 <= tau_us - event_time_us <= max_age_us
```

先取最大 `event_time_us`，再在该集合取最小：

```text
(lane_available_at_us,source_sequence,event_id)
```

0 个返回 `UNKNOWN`。同 identity 不同 bytes、同 `(generation,source_sequence)` 不同 event 或 winner set 中不可消解冲突返回 `CONFLICT`。EntryZone、anchor、I0、G0、Pivot、Target、barrier current price 与 first-hit path 必须调用此函数；不得各自定义 “latest”。

#### `SelectOpenInterest(query,tau_us,max_age_us)`

eligible 与 `SelectBook` 相同，但 schema 为 OpenInterest、无需 `sequence_contiguous` 字段；先最大 `event_time_us`，再最小：

```text
(lane_available_at_us,source_sequence,event_id)
```

0 个 `UNKNOWN`，冲突 `CONFLICT`。

#### `SelectVenueSnapshot(scope,tau_us)`

eligible：

```text
Scope4相等
quality=VALID
effective_at_us<=tau_us
lane_available_at_us<=tau_us
```

取最大 `effective_at_us`。该时刻若存在两个不同 `rule_fingerprint_sha256`，返回 `RULE_SNAPSHOT_CONFLICT`；相同 fingerprint 的重复发布去重后取最小 `snapshot_id`。

anchor 冻结 `rule_fingerprint_sha256`。在 ENTRY_SUBMIT 前，每次 action recomputation 都调用本 selector：

- selected fingerprint 等于 frozen：继续；
- selected fingerprint 不同：唯一生成 `CONTROL_ABSTAIN`，reason=`RULE_CHANGE`；
- UNKNOWN/CONFLICT：按 pre-submit common-quality fail closed。

ENTRY_SUBMIT 已处理，或已经存在 reserve/open order/open position risk 后，selected fingerprint 不同的唯一 synthetic 映射是：

```text
DATA_HEALTH_INVALID
reason_code = "RULE_CHANGE"
```

随后按 v0.2.1 §9 的 HALT/reduce-only/reconcile 路径处理。`EPISODE_TERMINAL` 不是新 event kind，也不得作为 rule-change 替代 event。

#### `SelectAccountSnapshot(account_query,tau_us,max_age_us)`

`account_query` exact keys为 `account_scope_id` 加 §5.3 `SourceQuery` 的全部 keys，且 `source_schema_version="rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2"`。

eligible：

```text
account_scope_id、Scope4、source_id、schema_version逐字等于 account_query
quality=VALID
effective_at_us<=tau_us
lane_available_at_us<=tau_us
0<=tau_us-effective_at_us<=max_age_us
```

取最大 `effective_at_us`。该时刻：

- canonical payload 完全相同的重复去重，取最小 `snapshot_id`；
- 两个不同 `payload_sha256` 返回 `ACCOUNT_SNAPSHOT_CONFLICT`；
- 0 个返回 `UNKNOWN`。

age 唯一按 `effective_at_us` 计算，不按 lane time。两个 pre-submit literal 都固定为：

```text
ANCHOR_ACCOUNT_MAX_AGE_US = 1_000_000
ACTION_ACCOUNT_MAX_AGE_US = 1_000_000
```

U anchor 调用 `SelectAccountSnapshot(account_query,anchor_at_us,ANCHOR_ACCOUNT_MAX_AGE_US)` 并冻结 anchor account artifact ID；entry action 调用 `SelectAccountSnapshot(account_query,action_at_us,ACTION_ACCOUNT_MAX_AGE_US)` 并冻结 action account artifact ID。post-submit POSITION_SNAPSHOT/RECONCILE_OK/ACCOUNT_MISMATCH 不调用“latest”，而必须由 event.input_artifact_ids 明确指定一个 snapshot ID，并继续满足 v0.2.1 `AccountProofTime`。

#### `SelectClosedMarkBarSlot(query,period_seconds,bar_open_at_us,tau_us)`

要求 exact slot、quality=VALID、`closed_at_us<=tau_us`、`lane_available_at_us<=tau_us`。一个合法 object 返回该 bar；0 个 `UNKNOWN`；多种 canonical payload `CONFLICT`。不得按 arrival 或 ID 挑一个。

#### `SelectAggTradeWindow(query,start_exclusive_us,end_inclusive_us,decision_at_us,seal_id)`

先按 §4.2 验证唯一 AGG_TRADE seal；返回 `covered_event_ids` 对应的 exact homogeneous array。每项必须 `lane_available_at_us<=decision_at_us` 且 quality=VALID。D 的 60 秒窗口必须调用本函数。

### 5.4 Pivot 与 path 的 grid selection

对于每个 expected UTC second `g_us`，唯一 grid book 是：

```text
SelectBook(query,g_us,1_000_000)
```

`g_us` 是 evaluation time，不是所选 book 的 event/availability time。完整窗口仍必须绑定 §4 的 BOOK_SNAPSHOT seal。Pivot 的窗口 extreme 在这些已选 grid points 上计算，不直接对 raw books 计算。

同价 extreme tie-break：

```text
(grid_time_us,
 selected_book.lane_available_at_us,
 selected_book.source_sequence,
 selected_book.event_id)
```

均升序。由此“每秒选 book”与“窗口中选 extreme”是两个先后固定的步骤。

### 5.5 OI completeness

v0.2.1 的：

```text
L(t)=ln(OI(t)/OI(t-900s))
```

两个 endpoint 各允许最多 60 秒 age，因此 exact source proof window 是：

```text
(t-960_000_000, t]
```

consumer 必须绑定一个 `covered_object_kind=OPEN_INTEREST`、上述 exact endpoints、`complete=true` 的 CoverageSeal；然后：

```text
oi_now  = SelectOpenInterest(query,t,60_000_000)
oi_prev = SelectOpenInterest(query,t-900_000_000,60_000_000)
```

两个 selected `event_id` 都必须出现在该 seal 的 `covered_event_ids`，且同 query/scope。缺 endpoint、gap、sequence conflict、seal conflict 或跨 scope 均返回 `UNKNOWN`，不得用最近值跨越 gap。

### 5.6 `SourceSelectorPolicy.v0.2.2`

Exact keys：

```text
schema_version,book_selector,open_interest_selector,
venue_selector,account_selector,bar_selector,trade_window_selector,
grid_rule,coverage_rule,policy_sha256
```

Exact values：

```text
schema_version =
  "rsi-mtf-drl-pm.source-selector-policy.v0.2.2"
book_selector =
  "MAX_EVENT_TIME_THEN_MIN_LANE_SEQUENCE_ID"
open_interest_selector =
  "MAX_EVENT_TIME_THEN_MIN_LANE_SEQUENCE_ID"
venue_selector =
  "MAX_EFFECTIVE_THEN_FINGERPRINT_CONFLICT_ELSE_MIN_ID"
account_selector =
  "MAX_EFFECTIVE_THEN_PAYLOAD_CONFLICT_ELSE_MIN_ID"
bar_selector =
  "EXACT_SLOT_SINGLETON"
trade_window_selector =
  "EXACT_COVERED_EVENT_SET"
grid_rule =
  "UTC_ONE_SECOND_SELECT_BOOK_AGE_LE_ONE_SECOND"
coverage_rule =
  "ONE_EXPLICIT_COMPLETE_V0_2_2_SEAL_NO_LEX_FALLBACK"
```

```text
policy_sha256 =
  ID("source-selector-policy/v0.2.2",
     entire object excluding policy_sha256)
```

---

## 6. U receipt 与 synthetic fixture authority

### 6.1 `UObservationReceipt.v0.2.2`

U 的 master/dedup/cooldown 结果不是 management reducer event，也不得加入 `ReducerEventKind`。

Exact keys：

```text
schema_version,event_kind,venue_id,instrument_id,lane_id,role,
cycle_start_us,grid_close_us,evaluation_at_us,
master_opportunity_id,parent_master_receipt_id,
u_policy_sha256,input_bar_id,receipt_sha256
```

Types/literals：

```text
schema_version =
  "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2"
event_kind enum{MASTER_CREATED,DEDUP_ATTACHED,COOLDOWN_SUPPRESSED}
role = "SYNTHETIC"
cycle_start_us,grid_close_us,evaluation_at_us:UtcUs
master_opportunity_id:StableId|null
parent_master_receipt_id:StableId|null
u_policy_sha256:Sha256
input_bar_id:StableId
```

共同约束：

```text
cycle_start_us <= grid_close_us <= evaluation_at_us
input_bar_id 唯一命中一个 CLOSED_MARK_BAR artifact
该 bar 为 15m、bar_close_at_us=grid_close_us、lane_available_at_us<=evaluation_at_us
u_policy_sha256 = PolicyRegistry.u_policy.policy_sha256
```

nullability：

| event_kind | master_opportunity_id | parent_master_receipt_id |
|---|---|---|
| MASTER_CREATED | non-null | null |
| DEDUP_ATTACHED | 与 parent MASTER 相同 | parent MASTER receipt_sha256 |
| COOLDOWN_SUPPRESSED | null | null |

MASTER_CREATED 与 DEDUP_ATTACHED 的 non-null value 必须等于 §12.7：

```text
ID("master-opportunity/v0.2.2", {
  u_policy_sha256,venue_id,instrument_id,lane_id,
  availability_kind:"SYNTHETIC",role,cycle_start_us
})
```

```text
receipt_sha256 =
  ID("u-observation-receipt/v0.2.2",
     entire object excluding receipt_sha256)
```

每个 control bundle 只允许且必须包含同一个 MASTER_CREATED receipt artifact；DEDUP/COOLDOWN receipt 不进入 management event_array。`FrozenLedgerSeed.master_u_receipt_sha256` 必须等于该 MASTER receipt。v0.2.1 §5.1 中把 DEDUP/COOLDOWN 描述成 event 的文字由本节替换。

### 6.2 `SyntheticFixtureManifest.v0.2.2`

Exact keys：

```text
schema_version,composite_theory_id,role,availability_kind,
venue_id,instrument_id,lane_id,
generator_policy,generator_policy_sha256,
source_queries,
source_artifact_ids,diagnostic_artifact_ids,
source_artifact_set_sha256,manifest_sha256
```

Exact constraints：

```text
schema_version =
  "rsi-mtf-drl-pm.synthetic-fixture-manifest.v0.2.2"
role = "SYNTHETIC"
availability_kind = "SYNTHETIC"
lane_id = "E0_SYNTHETIC_CANONICAL_V0_2_2"
generator_policy_sha256:Sha256
```

`source_queries` exact keys：

```text
closed_mark_bar_15m
closed_mark_bar_4h
book
agg_trade
open_interest
account
```

前五项均为 §5.3 `SourceQuery`。它们的 `source_schema_version` 依次固定为：

```text
rsi-mtf-drl-pm.closed-mark-bar.v0.2.2
rsi-mtf-drl-pm.closed-mark-bar.v0.2.2
rsi-mtf-drl-pm.book-snapshot.v0.2.2
rsi-mtf-drl-pm.agg-trade.v0.2.2
rsi-mtf-drl-pm.open-interest.v0.2.2
```

`account` 是 §5.3 `account_query`。所有 query 的 Scope4 必须逐字等于 manifest；所有 `source_id` 非空。closed_mark_bar_15m/4h 可以使用相同 source_id，但 consumer period分别固定 900/14400。所有 selector 必须从该 manifest 取 query，不得在 artifacts 中择优挑 source。

`generator_policy` 是 inline `SyntheticFixtureGeneratorPolicy.v0.2.2`，exact keys：

```text
schema_version,composite_theory_id,generator_kind,
randomness_rule,wall_clock_rule,outcome_access_rule,
source_schema_versions,policy_sha256
```

Exact values：

```text
schema_version =
  "rsi-mtf-drl-pm.synthetic-fixture-generator-policy.v0.2.2"
generator_kind =
  "DETERMINISTIC_HAND_AUTHORED_E0_FIXTURE"
randomness_rule = "FORBIDDEN"
wall_clock_rule = "FORBIDDEN"
outcome_access_rule =
  "DECISION_INPUTS_CAUSAL_ONLY_FUTURE_EVENTS_PREDECLARED_NOT_READ"
source_schema_versions = [
  "rsi-mtf-drl-pm.closed-mark-bar.v0.2.2",
  "rsi-mtf-drl-pm.book-snapshot.v0.2.2",
  "rsi-mtf-drl-pm.agg-trade.v0.2.2",
  "rsi-mtf-drl-pm.open-interest.v0.2.2",
  "rsi-mtf-drl-pm.source-coverage-seal.v0.2.2",
  "rsi-mtf-drl-pm.venue-instrument-snapshot.v0.2.2",
  "rsi-mtf-drl-pm.account-risk-snapshot.v0.2.2",
  "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2",
  "rsi-mtf-drl-pm.u-observation-receipt.v0.2.2"
]
```

array 顺序逐字固定。`composite_theory_id` 与 manifest 相等。

```text
generator_policy.policy_sha256 =
  ID("synthetic-fixture-generator-policy/v0.2.2",
     generator_policy excluding policy_sha256)

generator_policy_sha256 =
  generator_policy.policy_sha256
```

`source_artifact_ids` 去重、按 StableId 严格升序，并恰好列出本 synthetic fixture set 与 manifest Scope4 相同的 source objects、CoverageSeal、Venue/Account snapshots、FrozenEV evidence 与 U receipts；不含 manifest 自身、derived action/proof、management events、ledger records 或 labels。

`diagnostic_artifact_ids` 也去重、按 StableId 严格升序。它只能列出专门用于 `ACCOUNT_MISMATCH/SNAPSHOT_SCOPE_MISMATCH` negative scenario 的 cross-scope ACCOUNT_RISK_SNAPSHOT；这些 artifact 禁止进入 decision proof、selector、position/reconcile authority。没有该 scenario 时必须为 `[]`。

```text
source_artifact_set_sha256 =
  ID("synthetic-fixture-artifact-set/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    source_queries,source_artifact_ids,diagnostic_artifact_ids
  })

manifest_sha256 =
  ID("synthetic-fixture-manifest/v0.2.2",
     entire object excluding manifest_sha256)
```

当前 ledger/label 的 `data_or_fixture_sha256` 必须等于 `manifest_sha256`。`generator_policy_sha256` 只绑定 fixture 生成规则，不证明市场代表性。任何 DEVELOPMENT evidence 或 source object 进入 manifest 都必须拒绝整个 fixture。

---

## 7. Frozen EV evidence

### 7.1 `EVObservation.v0.2.2`

Exact keys：

```text
observation_id,opportunity_id,terminal_at_us,label_tail_us,
label_record_sha256,y_r,terminal_class,bindings_sha256
```

Types：

```text
observation_id:StableId
opportunity_id:StableId
terminal_at_us:UtcUs
label_tail_us:int>=0
label_record_sha256:Sha256
y_r:DecimalString
terminal_class enum{
  NO_FILL,TP,SL,STRUCTURE_EXIT,TIMEOUT,OPERATIONAL_OVERRIDE
}
bindings_sha256:Sha256
```

`label_tail_us` 是非负微秒 duration。

```text
observation_id =
  ID("ev-observation/v0.2.2", {
    opportunity_id,terminal_at_us,label_tail_us,
    label_record_sha256,y_r,terminal_class,bindings_sha256
  })
```

array 按 `(terminal_at_us,opportunity_id,label_record_sha256)` 严格排序；同 opportunity 在同 bucket 的 canonical tick replay 去重规则继续使用 v0.2.1 §8.3。

### 7.2 `FrozenEVEvidence.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
evidence_kind,candidate_id,control_id,side,management_state,
relative_anchor_bp_bucket,extension_bp_bucket,role,
sample_start_exclusive_us,sample_end_inclusive_us,
issued_at_us,lane_available_at_us,expires_at_us,
observations,n,sum_y_r,min_y_r,max_y_r,class_counts,
observations_sha256,estimator_policy_sha256,cost_policy_sha256,
label_policy_sha256,data_role_sha256,evidence_sha256
```

Exact literals/types：

```text
schema_version =
  "rsi-mtf-drl-pm.frozen-ev-evidence.v0.2.2"
evidence_kind enum{SUBMIT,HOLD,EXIT_NOW}
control_id enum{C1,C2,C3,C4,Cmu,C5}
side enum{LONG,SHORT}
management_state enum{PRE_SUBMIT,PROFIT_LOCKED}
role = "SYNTHETIC"
availability_kind = "SYNTHETIC"
lane_id = "E0_SYNTHETIC_CANONICAL_V0_2_2"
relative_anchor_bp_bucket:int
extension_bp_bucket:int|null
observations:array<EVObservation.v0.2.2>
n:int>=0
class_counts exact keys =
  NO_FILL,TP,SL,STRUCTURE_EXIT,TIMEOUT,OPERATIONAL_OVERRIDE
```

每个 class count 为 JSON integer `>=0`。

kind/state/nullability：

| evidence_kind | management_state | extension_bp_bucket |
|---|---|---|
| SUBMIT | PRE_SUBMIT | null |
| HOLD | PROFIT_LOCKED | non-null, >=0 |
| EXIT_NOW | PROFIT_LOCKED | non-null, >=0 |

bucket 公式：

```text
relative_anchor_bp_bucket =
  floor(10000 * (p_candidate - anchor_price) / anchor_price)

extension_bp_bucket =
  floor(10000 * s * (g - T_ack) / T_ack)
```

LONG `s=+1`，SHORT `s=-1`。HOLD 与用于同一 target comparison 的 EXIT_NOW 必须使用相同 `g`、`T_ack` 和 extension bucket；SUBMIT 不计算 extension bucket。

`p_candidate` 对 SUBMIT 唯一为 proposed `p_limit`；对 HOLD/EXIT_NOW pair 唯一为同一个 proposed `g`。因此同 pair 的 relative-anchor bucket 也必须相等。

chronology：

```text
sample_start_exclusive_us < sample_end_inclusive_us
sample_end_inclusive_us < issued_at_us
issued_at_us <= lane_available_at_us <= expires_at_us
expires_at_us - issued_at_us = 30_000_000
每个 observation:
  sample_start_exclusive_us < terminal_at_us
  terminal_at_us + label_tail_us <= sample_end_inclusive_us
  opportunity_id != 当前 opportunity_id
```

每个 observation 的 `bindings_sha256` 必须逐字等于由同 candidate、control、side、scope、cost、label、data-role 与 estimator policies 构造的 expected binding digest；不同 digest 的 row 使整份 evidence invalid。

该 expected digest 只有一个 preimage：

```text
bindings_sha256 =
  ID("ev-observation-bindings/v0.2.2", {
    composite_theory_id,
    venue_id,instrument_id,lane_id,availability_kind,
    evidence_kind,candidate_id,control_id,side,management_state,
    relative_anchor_bp_bucket,extension_bp_bucket,
    estimator_policy_sha256,cost_policy_sha256,
    label_policy_sha256,data_role_sha256
  })
```

每个 row 的值必须与 evidence object 上述字段的重算值相同。

统计量完全由 observations 重算：

```text
n = len(observations)
sum_y_r = decimal128 exact sum(observations[*].y_r)
class_counts[k] = count(terminal_class=k)
sum(class_counts)=n
```

每个 `y_r` 必须 `-1<=y_r<=3`。`n=0` 时：

```text
sum_y_r="0", min_y_r=null, max_y_r=null
```

`n>0` 时：

```text
min_y_r=min(y_r)
max_y_r=max(y_r)
n*min_y_r <= sum_y_r <= n*max_y_r
```

```text
observations_sha256 =
  ID("ev-observation-set/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    evidence_kind,candidate_id,control_id,side,management_state,
    relative_anchor_bp_bucket,extension_bp_bucket,observations
  })

evidence_sha256 =
  ID("frozen-ev-evidence/v0.2.2",
     entire object excluding evidence_sha256)
```

四个 policy digest 必须分别等于 §2 registry 的 estimator、cost、label、data-role policy；candidate_id 必须由同 registry 重算。当前阶段 `DEVELOPMENT` 不在 enum admissibility 内。

### 7.3 `SelectFrozenEVEvidence`

输入 key exact fields：

```text
Scope4,evidence_kind,candidate_id,control_id,side,management_state,
relative_anchor_bp_bucket,extension_bp_bucket,
estimator_policy_sha256,cost_policy_sha256,
label_policy_sha256,data_role_sha256,
current_opportunity_id,decision_at_us
```

eligible evidence 必须逐字段匹配，且：

```text
sample_end_inclusive_us < decision_at_us
issued_at_us <= decision_at_us
lane_available_at_us <= decision_at_us <= expires_at_us
n >= ParameterSet.ev_min_n
every observations[*].opportunity_id != current_opportunity_id
```

selector preimage：

```text
evidence_selection_key_sha256 =
  ID("frozen-ev-evidence-selection-key/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    evidence_kind,candidate_id,control_id,side,management_state,
    relative_anchor_bp_bucket,extension_bp_bucket,
    estimator_policy_sha256,cost_policy_sha256,
    label_policy_sha256,data_role_sha256,
    current_opportunity_id,decision_at_us
  })
```

取最大 `issued_at_us`。该时刻：

- 完全相同 evidence hash 去重；
- 不同 `evidence_sha256` 返回 `EVIDENCE_CONFLICT`；
- 0 个返回 `UNKNOWN`。

成功结果 exact tuple 是
`(evidence_artifact_id,evidence_sha256,evidence_selection_key_sha256)`。禁止按 artifact ID、sample size 或 EV outcome 选择。LCB、mean、Dirichlet class probability仍按 v0.2.1 §8.3，从本对象的可重算统计量计算。

### 7.4 SUBMIT 与 dynamic target bindings

每个 ENTRY decision proof 必须绑定恰好一个 `evidence_kind=SUBMIT` artifact；其 artifact ID 与 evidence hash 都进入 §8 proof closure。

每个通过 data/geometry/non-crossing 检查并到达 EV stage 的 target candidate，
必须各自绑定一对：

```text
HOLD evidence
EXIT_NOW evidence
```

两者必须同 Scope4、candidate、control=C5、side、relative-anchor bucket、extension bucket、management_state、sample window policies与 decision time selector；kind 必须分别为 HOLD/EXIT_NOW。两者必须同时为 null或同时 non-null；只给一个、互换 hash 或 bucket 不同均拒绝。

非 null pair 还必须有相同 `sample_start_exclusive_us`、`sample_end_inclusive_us`、四个 policy digests 与 `n`。两份 evidence 各自按 §7.3 独立选出；若任一 selector conflict或上述 pair equality失败，target EV 为 UNKNOWN。

每个成功 pair 必须写入 §9.3 的唯一
`CandidateEvidenceBinding.v0.2.2`；禁止只在 event 顶层保存一对可被多个
target candidate 复用的 hash。到达 EV stage 但任一 selector 返回
UNKNOWN/CONFLICT 的 candidate 不得产生半个 binding，也不得成为 winner；其
UNKNOWN/CONFLICT 状态仍由 reducer 的既有 barrier 状态语义处理。

---

## 8. Decision proof 与 sealed entry authority

### 8.1 Authority 选择

v0.2.2 只允许一种解释：

1. bundle validator 从 exact `DecisionInputBinding` 指定的全量 source/policy artifacts 纯重算 entry/abstain decision；
2. 重算结果与 binding、SharedEntryAction、FrozenActionContext 逐 byte 对齐后，sealed action 才获得 authority；
3. management reducer 不读取 bars/books/trades/OI/evidence，也不再次运行 entry calculator；它只消费已通过 bundle validator 的 action/context 与 event_array。

因此既不存在“只信任自洽 SharedEntryAction”，也不存在“reducer 自己隐式寻找 raw inputs”的第二条合法路径。

### 8.2 `DecisionInputBinding.v0.2.2`

Exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
opportunity_id,control_id,side,candidate_id,
decision_kind,decision_at_us,
named_artifact_bindings,
selector_bindings,
source_artifact_ids,source_artifact_set_sha256,
calculator_policy_bundle_sha256,
decision_result_sha256,proof_sha256
```

Exact types：

```text
schema_version =
  "rsi-mtf-drl-pm.decision-input-binding.v0.2.2"
control_id enum{C1,C2,C3,C4,Cmu}
side enum{LONG,SHORT}
decision_kind enum{ENTRY,ABSTAIN}
source_artifact_ids:array<StableId>
```

`named_artifact_bindings` exact keys：

```text
anchor_venue_snapshot_artifact_id
action_venue_snapshot_artifact_id
anchor_account_snapshot_artifact_id
action_account_snapshot_artifact_id
submit_ev_evidence_artifact_id
master_u_receipt_artifact_id
policy_registry_artifact_id
fixture_manifest_artifact_id
```

每项为 `StableId|null`。`master_u_receipt_artifact_id`、`policy_registry_artifact_id` 与 `fixture_manifest_artifact_id` 永远 non-null。ENTRY 时其余五项也全部 non-null。ABSTAIN 时，某项 non-null 当且仅当 calculator 实际读取该 selected object；某项为 null 当且仅当对应 selector无合法 object，且 `reason_code` 正是由该缺失产生的 fail-closed reason。所有 non-null values 必须出现在 `source_artifact_ids`，并分别唯一命中正确 schema；同一个 artifact可合法同时承担 anchor/action，字段仍都必须写出。

`selector_bindings` exact keys：

```text
anchor_account_max_age_us
action_account_max_age_us
submit_ev_selection_key_sha256
```

前两项必须分别为 §5.3 的 `1_000_000`。`submit_ev_selection_key_sha256:Sha256|null`：ENTRY 必须 non-null并等于 §7.3 以 `current_opportunity_id=DecisionInputBinding.opportunity_id` 重算的 selection key；ABSTAIN 在 S5 已读取 EV 时 non-null，否则 null。

`source_artifact_ids` 去重并按 StableId 严格升序，且必须恰好是纯 calculator 实际读取的下列 closure：

- CLOSED_MARK_BAR、BOOK_SNAPSHOT、AGG_TRADE、OPEN_INTEREST source artifacts；
- 上述读取所需的全部且仅有 CoverageSeal；
- frozen anchor/action VenueInstrumentSnapshot；
- frozen anchor/action AccountRiskSnapshot；
- ENTRY 时唯一 SUBMIT FrozenEVEvidence；
- MASTER_CREATED UObservationReceipt；
- PolicyRegistry；
- SyntheticFixtureManifest，作为 source query/closed fixture authority。

不允许遗漏，也不允许加入未被计算读取的 artifact。decision proof 自身、SharedEntryAction、future lifecycle/path artifact、management event/record 与 label 不得进入该数组。所有 artifact 必须 `available_at_us<=decision_at_us`，或是允许 null availability 的 static policy/fixture manifest；任何未来 availability 拒绝。

calculator 的读取顺序固定，因而“实际读取”不是实现自由：

```text
S0 policy registry + fixture manifest/source queries + master U receipt
S1 frozen anchor book + anchor venue/account
S2 control-specific RSI/K/D/R/L/RESPONDING source windows
S3 action-time venue rule + EntryZone/current book
S4 geometry/G0 source windows
S5 SUBMIT EV evidence
S6 action account + quantity/risk/margin
```

每一 stage 必须 eager 读取该 stage 规范要求的全部 source/coverage artifacts；若该 stage 得到 terminal FALSE/UNKNOWN/CONFLICT，后续 stages 禁止读取，proof closure在此停止。ENTRY 必须完成 S0–S6。

pre-deadline 只有 `RULE_CHANGE`、`ANCHOR_UNKNOWN`、`NO_C1_EVENT` 可形成 calculator ABSTAIN；其余未通过状态等待 control deadline。deadline 的 ABSTAIN reason 用以下首个匹配项：

```text
RULE_CHANGE
ANCHOR_UNKNOWN
NO_C1_EVENT
GATE_FALSE
GATE_UNKNOWN_AT_DEADLINE
ENTRY_ZONE_EMPTY
COMMON_CHECK_FAILED
EV_UNKNOWN
RISK_OR_MARGIN_FAIL
TTL_EXPIRED
```

该顺序也决定读取停止点。显式 fatal reducer event不进入这个 list。

```text
source_artifact_set_sha256 =
  ID("decision-source-artifact-set/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    opportunity_id,control_id,side,candidate_id,
    decision_at_us,named_artifact_bindings,selector_bindings,
    source_artifact_ids
  })
```

`calculator_policy_bundle_sha256` 必须等于 §2.4。

重算结果是以下互斥 exact union。

ENTRY result exact keys：

```text
decision_kind,action_at_us,p_limit,submitted_qty,
initial_levels,risk_basis
```

其中 `decision_kind="ENTRY"`；`initial_levels` exact keys：

```text
anchor,p_limit,i0,g0,s0,t0,h0_us,tcap
```

`risk_basis` exact keys：

```text
submitted_qty,r_unit_usdt,r_episode_max_usdt,
pending_existing_at_action_usdt
```

ABSTAIN result exact keys：

```text
decision_kind,action_at_us,reason_code,
initial_levels,risk_basis
```

其中 `decision_kind="ABSTAIN"`；`reason_code` 必须是 v0.2.2 admissible CONTROL_ABSTAIN reason；`initial_levels` 八项全为 null；`risk_basis` 四项全为 `"0"`。

v0.2.2 admissible CONTROL_ABSTAIN reason 的封闭 enum 是：

```text
ANCHOR_UNKNOWN,NO_C1_EVENT,GATE_FALSE,GATE_UNKNOWN_AT_DEADLINE,
ENTRY_ZONE_EMPTY,COMMON_CHECK_FAILED,EV_UNKNOWN,
RISK_OR_MARGIN_FAIL,TTL_EXPIRED,RULE_CHANGE
```

旧 `EPISODE_TERMINAL` 不再是 CONTROL_ABSTAIN reason alias。显式
ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT 仍由自身 reducer event
作为 pre-submit fatal authority，不伪装成 calculator ABSTAIN result。

decision clock equality 没有容差：

```text
ENTRY:
  DecisionInputBinding.decision_at_us
  = ENTRY result.action_at_us
  = SharedEntryAction.action_at_us
  = FrozenActionContext.action_at_us
  = ENTRY_SUBMIT.event_time_us
  = ENTRY_SUBMIT.lane_available_at_us

CONTROL_ABSTAIN:
  DecisionInputBinding.decision_at_us
  = ABSTAIN result.action_at_us
  = FrozenActionContext.action_at_us
  = CONTROL_ABSTAIN.event_time_us
  = CONTROL_ABSTAIN.lane_available_at_us
```

所有 proof source 的 causal availability 必须不晚于同一个 `decision_at_us`。任一侧相差 1 微秒也拒绝；不得以较晚 proof 重写较早 action。

```text
decision_result_sha256 =
  ID("decision-result/v0.2.2", exact union result)

proof_sha256 =
  ID("decision-input-binding/v0.2.2",
     entire binding excluding proof_sha256)
```

### 8.3 `SharedEntryAction.v0.2.2`

Top-level exact keys：

```text
schema_version,venue_id,instrument_id,lane_id,availability_kind,
source_control_id,opportunity_id,candidate_id,side,
anchor_at_us,anchor_price,action_at_us,p_limit,submitted_qty,
expires_at_us,initial_levels,risk_basis,
entry_policy_sha256,
decision_input_binding_artifact_id,
decision_input_binding_sha256,decision_result_sha256,
entry_action_sha256
```

除新增 scope/proof 字段外，v0.2.1 §12.2 的 control-neutral、C5 replay、expires、levels、risk 与 C4/C5 byte equality 规则继续有效。

```text
schema_version =
  "rsi-mtf-drl-pm.shared-entry-action.v0.2.2"
entry_policy_sha256 = PolicyRegistry.entry_policy.policy_sha256
decision_input_binding_artifact_id =
  unique DECISION_INPUT_BINDING wrapper artifact_id
decision_input_binding_sha256 =
  wrapper.payload.proof_sha256
decision_result_sha256 =
  wrapper.payload.decision_result_sha256
entry_action_sha256 =
  ID("shared-entry-action/v0.2.2",
     entire object excluding entry_action_sha256)
```

binding 必须是 ENTRY union，scope/control/action/result 与本 action逐字段相等。
令 `shared_entry_action_artifact_id` 为唯一承载本 action 的
SHARED_ENTRY_ACTION wrapper ID，则：

```text
ENTRY_SUBMIT.input_artifact_ids =
  sort_unique(
    DecisionInputBinding.source_artifact_ids
    union {
      DecisionInputBinding wrapper artifact_id,
      shared_entry_action_artifact_id
    }
  )
```

这是 exact set equality，不是 contains 条件。SUBMIT evidence 与所有直接
source/policy/fixture authority 已包含在 proof 的 source closure 中；任何缺项、
额外 artifact、payload ID、event ID 或 future lifecycle/path artifact 都拒绝。

### 8.4 `FrozenLedgerSeed` 与 `FrozenActionContext` additions

`FrozenLedgerSeed.v0.2.2` top-level exact keys：

```text
schema_version,opportunity_id,control_id,candidate_id,side,
anchor_at_us,anchor_status,anchor_price,cost_basis,policy_bindings,
master_u_receipt_sha256,seed_sha256
```

它使用 v0.2.1 §11.0 对 identity、side、anchor、cost_basis 的 exact type/nullability/constraints，并：

- `schema_version="rsi-mtf-drl-pm.frozen-ledger-seed.v0.2.2"`；
- 在 `policy_bindings` 中使用 §12.1 的完整 successor fields；
- 新增 top-level `master_u_receipt_sha256:Sha256`；
- `seed_sha256=ID("frozen-ledger-seed/v0.2.2", object excluding seed_sha256)`。

`FrozenActionContext.v0.2.2` top-level exact keys：

```text
schema_version,ledger_seed_sha256,decision_kind,action_at_us,entry_mode,
shared_entry_action_sha256,initial_levels,risk_basis,
decision_input_binding_artifact_id,
decision_input_binding_sha256,decision_result_sha256,
action_context_sha256
```

三个 decision-proof 字段类型精确为：

```text
decision_input_binding_artifact_id:StableId|null
decision_input_binding_sha256:Sha256|null
decision_result_sha256:Sha256|null
```

并遵循：

- 由 CONTROL_ABSTAIN 形成的 ABSTAIN 与所有 ENTRY 都必须三项 non-null并绑定一个 DecisionInputBinding；ABSTAIN 的 `shared_entry_action_sha256=null`，proof 是 ABSTAIN union；ENTRY proof 是 ENTRY union并与 SharedEntryAction 相等；
- 由显式 pre-submit ACCOUNT_MISMATCH/KILL/DATA_HEALTH_INVALID/EVENT_CONFLICT 形成的 fatal ABSTAIN，三个 proof 字段必须全 null；其 authority 只来自已验证 CanonicalSyntheticEvent 与 details/input binding，不得另造 calculator result；
- C5 REPLAY_C4 使用 C4 的 SharedEntryAction 与 ENTRY decision proof，不新造 C5 entry decision。

```text
schema_version =
  "rsi-mtf-drl-pm.frozen-action-context.v0.2.2"
action_context_sha256 =
  ID("frozen-action-context/v0.2.2",
     entire object excluding action_context_sha256)
```

---

## 9. Artifact、synthetic event 与 bundle successor

### 9.1 Scoped artifact wrapper

`ArtifactWrapper.v0.2.2` exact keys：

```text
artifact_id,artifact_scope_id,schema_id,
available_at_us,payload_sha256,payload
```

对 scopeful artifact：

```text
artifact_scope_id =
  ID("synthetic-artifact-scope/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind
  })
```

其中四项来自 payload，或来自该 derived object 明确绑定的 Scope4。只有下列 static policy artifact 允许 `artifact_scope_id=null`：

```text
PI_EXIT_POLICY
FIRST_HIT_LABEL_POLICY
REDUCER_PRIORITY_POLICY
POLICY_REGISTRY
```

其他 schema 必须非 null。`available_at_us` 的 exact mapping：

| schema group | available_at_us |
|---|---|
| 上述四个 static policy | `null` |
| SYNTHETIC_FIXTURE_MANIFEST、C4_C5_EXOGENOUS_PATH_MANIFEST | `null`，但 scope non-null |
| CLOSED_MARK_BAR、BOOK_SNAPSHOT、AGG_TRADE、OPEN_INTEREST、SOURCE_COVERAGE_SEAL、VENUE_INSTRUMENT_SNAPSHOT、ACCOUNT_RISK_SNAPSHOT、FROZEN_EV_EVIDENCE | payload 对应 `lane_available_at_us` |
| U_OBSERVATION_RECEIPT | `payload.evaluation_at_us` |
| DECISION_INPUT_BINDING | `payload.decision_at_us` |
| SHARED_ENTRY_ACTION | `payload.action_at_us` |
| EXIT_POLICY_INSTANCE | first nonzero fill causal-effective time |
| SYNTHETIC_FUNDING_OBSERVATION | observation causal availability time |
| SYNTHETIC_CONFLICT_PROOF | matching EVENT_CONFLICT.event_time_us |

```text
payload_sha256 = SHA256(CanonicalJSON(payload))

artifact_id =
  ID("synthetic-artifact/v0.2.2", {
    artifact_scope_id,schema_id,available_at_us,payload_sha256
  })
```

同 payload bytes 在不同 scope 产生不同 artifact ID。除 static policy外，`artifact_scope_id=null` 一律拒绝。除 §9.2 明示 successor 外，旧 v0.2.1 payload/version/domain 不得进入 v0.2.2 bundle。

### 9.2 Artifact schema routing

`ArtifactSchemaId.v0.2.2` 是以下封闭 enum：

```text
CLOSED_MARK_BAR
BOOK_SNAPSHOT
AGG_TRADE
OPEN_INTEREST
SOURCE_COVERAGE_SEAL
VENUE_INSTRUMENT_SNAPSHOT
ACCOUNT_RISK_SNAPSHOT
FROZEN_EV_EVIDENCE
U_OBSERVATION_RECEIPT
SYNTHETIC_FIXTURE_MANIFEST
POLICY_REGISTRY
REDUCER_PRIORITY_POLICY
PI_EXIT_POLICY
FIRST_HIT_LABEL_POLICY
DECISION_INPUT_BINDING
SHARED_ENTRY_ACTION
EXIT_POLICY_INSTANCE
C4_C5_EXOGENOUS_PATH_MANIFEST
SYNTHETIC_FUNDING_OBSERVATION
SYNTHETIC_CONFLICT_PROOF
```

Payload routing：

| schema_id | exact successor |
|---|---|
| CLOSED_MARK_BAR | §3.1 ClosedMarkBar.v0.2.2 |
| BOOK_SNAPSHOT | §3.1 BookSnapshot.v0.2.2 |
| AGG_TRADE | §3.1 AggTrade.v0.2.2 |
| OPEN_INTEREST | §3.1 OpenInterest.v0.2.2 |
| SOURCE_COVERAGE_SEAL | §4 CoverageSeal.v0.2.2 |
| VENUE_INSTRUMENT_SNAPSHOT | §5.1 |
| ACCOUNT_RISK_SNAPSHOT | §5.2 |
| FROZEN_EV_EVIDENCE | §7.2 |
| U_OBSERVATION_RECEIPT | §6.1 |
| SYNTHETIC_FIXTURE_MANIFEST | §6.2 |
| POLICY_REGISTRY | §2.5 |
| REDUCER_PRIORITY_POLICY | §10.1 |
| PI_EXIT_POLICY | §10.1 |
| FIRST_HIT_LABEL_POLICY | §12.3 |
| DECISION_INPUT_BINDING | §8.2 |
| SHARED_ENTRY_ACTION | §8.3 |
| EXIT_POLICY_INSTANCE | §12.4 ExitPolicyInstance.v0.2.2 |
| C4_C5_EXOGENOUS_PATH_MANIFEST | §12.5 C4C5ExogenousPathManifest.v0.2.2 |
| SYNTHETIC_FUNDING_OBSERVATION | 本节下文 |
| SYNTHETIC_CONFLICT_PROOF | 本节下文 |

`SyntheticFundingObservation.v0.2.2` exact keys：

```text
schema_version,funding_event_id,venue_id,instrument_id,lane_id,
availability_kind,economic_event_time_us,interval_start_us,
interval_end_us,funding_rate,price_basis,quality
```

Exact literals：

```text
schema_version =
  "rsi-mtf-drl-pm.synthetic-funding-observation.v0.2.2"
availability_kind = "SYNTHETIC"
quality = "VALID"
interval_start_us < interval_end_us = economic_event_time_us
economic_event_time_us <= wrapper.available_at_us
funding_event_id =
  ID("synthetic-funding/v0.2.2", {
    venue_id,instrument_id,lane_id,
    interval_start_us,interval_end_us
  })
```

`SyntheticConflictProof.v0.2.2` exact keys：

```text
schema_version,claimed_source_identity,claimed_event_kind,
original_payload_sha256,original_payload,
incoming_payload_sha256,incoming_payload,proof_sha256
```

除 `schema_version="rsi-mtf-drl-pm.synthetic-conflict-proof.v0.2.2"` 与
`proof_sha256=ID("synthetic-conflict-proof/v0.2.2", object excluding proof_sha256)` 外，v0.2.1 §2.9 的 event-kind、payload validity 与 mismatch rules逐字有效。

### 9.3 `CanonicalSyntheticEvent.v0.2.2`

Top-level exact keys：

```text
event_kind,venue_id,instrument_id,episode_id,opportunity_id,
control_id,candidate_id,event_time_us,lane_available_at_us,
economic_event_time_us,priority_rank,source_sequence,source_event_id,
predecessor_event_ids,input_artifact_ids,shared_entry_event_id,
request_id,order_id,payload_sha256,payload
```

types、request/order nullability、ready-set allocator 与 economic-time union 使用冻结的 v0.2.1 §2.8 exact definitions；所有 identity domain 改为 v0.2.2：

```text
canonical-synthetic-event-presequence/v0.2.2
canonical-synthetic-event/v0.2.2
```

`ReducerPayloadMap.v0.2.2` 是 v0.2.1 §9.1 的 exact 34-kind payload map执行以下封闭 transform：

```text
REPLACE CONTROL_ABSTAIN payload
REPLACE ENTRY_SUBMIT payload
REPLACE BARRIER_EVALUATION payload
REPLACE FUNDING_DEBIT funding_event_id preimage
其他 30 kinds 的 exact key/type/nullability不变
```

`CONTROL_ABSTAIN` exact payload：

```text
reason_code:enum{
  ANCHOR_UNKNOWN,NO_C1_EVENT,GATE_FALSE,GATE_UNKNOWN_AT_DEADLINE,
  ENTRY_ZONE_EMPTY,COMMON_CHECK_FAILED,EV_UNKNOWN,
  RISK_OR_MARGIN_FAIL,TTL_EXPIRED,RULE_CHANGE
}
```

`ENTRY_SUBMIT` exact payload：

```text
price,qty,order_side,expires_at_us,
entry_policy_sha256,shared_entry_action_sha256,
decision_input_binding_sha256
```

其值必须逐字段等于 §8 SharedEntryAction/DecisionInputBinding；`entry_policy_sha256` 等于 PolicyRegistry；ENTRY_SUBMIT.input_artifact_ids 必须满足 §8.3。

`FUNDING_DEBIT` exact keys/type保持 v0.2.1 §9.1，但其 `funding_event_id` 必须重算为：

```text
ID("synthetic-funding/v0.2.2", {
  venue_id,instrument_id,lane_id,
  interval_start_us,interval_end_us
})
```

且逐字等于唯一 funding observation artifact。旧不含 lane_id 的 preimage拒绝。

`BARRIER_EVALUATION` exact payload：

```text
pivot_input_sha256,target_input_sha256,
candidate_evidence_bindings,target_winner_candidate_id
```

`candidate_evidence_bindings` 的 item schema 为
`CandidateEvidenceBinding.v0.2.2`，exact keys：

```text
target_candidate_id
relative_anchor_bp_bucket
extension_bp_bucket
hold_evidence_artifact_id
hold_evidence_sha256
hold_selection_key_sha256
exit_now_evidence_artifact_id
exit_now_evidence_sha256
exit_now_selection_key_sha256
binding_sha256
```

Exact types/constraints：

```text
target_candidate_id:StableId
relative_anchor_bp_bucket:int
extension_bp_bucket:int>=0
hold_evidence_artifact_id:StableId
hold_evidence_sha256:Sha256
hold_selection_key_sha256:Sha256
exit_now_evidence_artifact_id:StableId
exit_now_evidence_sha256:Sha256
exit_now_selection_key_sha256:Sha256

binding_sha256 =
  ID("target-candidate-evidence-binding/v0.2.2",
     item excluding binding_sha256)
```

数组必须覆盖且只覆盖所有通过 data/geometry/non-crossing 并到达 EV stage、
且 HOLD 与 EXIT_NOW 两个 selector 都成功的 target candidate。每个
`target_candidate_id` 恰好一项，按
`(target_candidate_id,binding_sha256)` UTF-8 bytes 严格升序；重复
target ID、半个 pair 或额外 binding 都拒绝。每项两个 artifact ID 在
`event.input_artifact_ids` 中唯一命中 FROZEN_EV_EVIDENCE，hash 逐字相等。
两个 evidence 的 `candidate_id=event.candidate_id`、`control_id=C5`，并与
event Scope4、side、management state及本 item 两个 bucket逐字段相等；
两个 selection key 分别以 `evidence_kind=HOLD` 和
`evidence_kind=EXIT_NOW`、`current_opportunity_id=event.opportunity_id`、
`decision_at_us=event.event_time_us` 按 §7.3 重算。§7.4 的 pair equality
也必须通过。

`target_winner_candidate_id:StableId|null`。非 null 时必须恰好命中数组中一项，
并等于 §11.3 exact rank 的唯一 winner；没有成功 pair 或没有 candidate
通过全部 EV gate 时必须为 null。`event.input_artifact_ids` 中 schema 为
FROZEN_EV_EVIDENCE 的 ID 集必须恰好等于数组内全部 HOLD/EXIT_NOW artifact
ID 的并集。

令：

```text
market_input_artifact_ids =
  sorted unique event.input_artifact_ids whose schema_id in
  {BOOK_SNAPSHOT,SOURCE_COVERAGE_SEAL}
```

则：

```text
pivot_input_sha256 =
  ID("pivot-evaluation-inputs/v0.2.2", {
    event_time_us,market_input_artifact_ids,
    pivot_policy_id:"pivot-theta.v0.2.2"
  })

target_input_sha256 =
  ID("target-evaluation-inputs/v0.2.2", {
    event_time_us,market_input_artifact_ids,
    target_policy_id:"target-boundary-theta.v0.2.2",
    candidate_evidence_bindings,target_winner_candidate_id
  })
```

`target_input_sha256` 因而承诺完整 per-candidate evidence array 与 winner，不得
只承诺 winner 的 pair。旧
`ev_hold_evidence_sha256`、`ev_exit_now_evidence_sha256` 或单一
`ev_evidence_sha256` 字段全部不存在 alias。

### 9.4 `CanonicalSyntheticEventBundle.v0.2.2`

Top-level exact keys仍为：

```text
schema_version,bundle_scope_id,ledger_bindings,ledger_identity,
ledger_seed,action_context,entry_execution_binding,
artifacts,coverage,event_array,finalized_at_us,
event_set_sha256,bundle_sha256
```

Exact successor literals/domains：

```text
schema_version =
  "rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.2"

bundle_scope_id =
  ID("canonical-synthetic-bundle-scope/v0.2.2", {
    ledger_identity,
    ledger_seed_sha256:ledger_seed.seed_sha256,
    policy_bundle_sha256:ledger_bindings.policy_bundle_sha256
  })

event_set_sha256 =
  ID("canonical-synthetic-event-set/v0.2.2",
     event_array)

bundle_sha256 =
  ID("canonical-synthetic-event-bundle/v0.2.2",
     entire bundle excluding bundle_sha256)
```

`event_set_sha256` 必须逐字等于 `coverage.event_set_sha256`。两者的 preimage 都是完整、已排序、逐 byte相同的 `event_array`；禁止只 hash source_event_ids、payload hashes 或任何 projection。§12.8 对该 domain 的 `DOMAIN_ONLY` 因而与冻结 v0.2.1 preimage一致。

`artifacts` 使用 §9.1 exact wrapper与 §9.2 union。以下 root closure 必须全部满足：

- 每个 event/predecessor/input ID 唯一解析；
- every non-C0 bundle 含唯一 POLICY_REGISTRY、SYNTHETIC_FIXTURE_MANIFEST、MASTER U receipt；
- C0 的 `action_context=null`；
- calculator CONTROL_ABSTAIN 或 ENTRY activation 恰好含一个 DECISION_INPUT_BINDING；pre-submit fatal ABSTAIN 恰好含零个；
- ENTRY 另含唯一 SHARED_ENTRY_ACTION 与 SUBMIT evidence；CONTROL_ABSTAIN 与 pre-submit fatal ABSTAIN 都含零个 SHARED_ENTRY_ACTION；
- proof.source_artifact_ids 中每项都在 artifacts 唯一命中；
- manifest.source_artifact_ids 与 diagnostic_artifact_ids 中每项都在 artifacts 唯一命中；
- 除 §5.3 明示 wrong-scope diagnostic AccountRiskSnapshot 外，每个 scopeful artifact 的 scope等于 ledger Scope4；
- wrong-scope diagnostic artifact只能位于 manifest.diagnostic_artifact_ids，并只能被一个 `ACCOUNT_MISMATCH/SNAPSHOT_SCOPE_MISMATCH` 引用；不能进入 manifest.source_artifact_ids、decision proof、selector、reconcile、position或 label source proof；
- static policy artifact虽然 scope/availability为 null，仍必须在 bundle finalized 前已由 digest固定。

`context-activation event` 唯一为 event_array 全序中第一条在 FLAT prefix 激活
action context 的 `CONTROL_ABSTAIN`、`ENTRY_SUBMIT`，或以下允许的 pre-submit
fatal event。闭包分支互斥：

1. `CONTROL_ABSTAIN`：恰好一个 ABSTAIN DecisionInputBinding；context 的三个
   proof 字段全部 non-null并逐字命中该 wrapper/result；零 SharedEntryAction；
   decision/action/event clock满足 §8.2 exact equality。
2. `ENTRY_SUBMIT`：恰好一个 ENTRY DecisionInputBinding 与一个
   SharedEntryAction；context、action、event逐字绑定；input artifact exact set
   满足 §8.3。
3. `ACCOUNT_MISMATCH`、`KILL`、`DATA_HEALTH_INVALID` 或 `EVENT_CONFLICT`：
   仅当它是首个 activation event，且此前 state=FLAT、没有
   ENTRY_SUBMIT、order reserve、positive fill 或 open risk，才可形成 fatal
   ABSTAIN。此分支恰好零 DecisionInputBinding、零 SharedEntryAction；
   context `decision_kind=ABSTAIN`，三个 proof 字段与
   `shared_entry_action_sha256` 全 null，
   `action_at_us=fatal_event.event_time_us`。fatal event 的
   `lane_available_at_us=event_time_us`，且同一或更早时间不得再有
   CONTROL_ABSTAIN/ENTRY_SUBMIT，也不得存在 submission descendant。

fatal 分支的 event proof 不是自由摘要，必须满足以下 exact closure：

```text
EVENT_CONFLICT:
  input_artifact_ids =
    [unique matching SYNTHETIC_CONFLICT_PROOF wrapper artifact_id]
  event.payload.original_event_id =
    proof.claimed_source_identity
  event.payload.original_payload_sha256 =
    proof.original_payload_sha256
  event.payload.incoming_payload_sha256 =
    proof.incoming_payload_sha256

trusted ACCOUNT_MISMATCH:
  input_artifact_ids contains exactly one trusted
    ACCOUNT_RISK_SNAPSHOT for the mismatch observation
  snapshot_id,account_scope_id,observed_position_qty,
    observed_position_vwap byte-equal that snapshot
  details_sha256 =
    ID("account-mismatch-details/v0.2.2", {
      reason_code,account_snapshot_artifact_id,
      observed_position_qty,observed_position_vwap
    })

non-trusting ACCOUNT_MISMATCH:
  snapshot_id,account_scope_id,observed_position_qty,
    observed_position_vwap are all null
  details_sha256 =
    ID("account-mismatch-details/v0.2.2", {
      reason_code,predecessor_event_ids,input_artifact_ids
    })

KILL or DATA_HEALTH_INVALID:
  details_sha256 =
    ID("synthetic-fatal-details/v0.2.2", {
      event_kind,reason_code,predecessor_event_ids,input_artifact_ids
    })
```

trusted/non-trusting 的 snapshot quality、scope、reason priority、
`AccountProofTime` 与 order-set规则保持冻结 v0.2.1 exact constraints。fatal
event 的 predecessor/input arrays 必须先按其 event schema验证，再参与上式；
不得以“等价 details”或额外 artifact替代。除以上三个分支外，任何 non-C0
action context 缺 DecisionInputBinding 都拒绝；submission 后发生 fatal event
只能作用于既有 ENTRY context，不能新建 fatal ABSTAIN context。

`coverage` exact keys：

```text
status,window_start_exclusive_us,window_end_inclusive_us,
expected_grid_times_us,observed_grid_times_us,missing_grid_times_us,
event_count,artifact_count,event_set_sha256,
artifact_set_sha256,coverage_sha256
```

Exact rules：

```text
status enum{COMPLETE,CENSORED}
三个 grid arrays 为 UtcUs，严格升序、无重复
observed ∩ missing = empty
observed ∪ missing = expected
COMPLETE iff missing=[]
event_count=len(event_array)
artifact_count=len(artifacts)
event_set_sha256 =
  ID("canonical-synthetic-event-set/v0.2.2",event_array)
artifact_set_sha256 =
  ID("canonical-synthetic-artifact-set/v0.2.2",artifacts)
coverage_sha256 =
  ID("canonical-synthetic-coverage/v0.2.2",
     coverage excluding coverage_sha256)
```

C0/NO_ACTION/NO_FILL、正常 FILLED、data censor 与 ZERO_GRID 的 endpoint/array规则逐字使用冻结的 v0.2.1 §2.9 coverage branch definitions；只替换本节三个 domain。它不得放入 source CoverageSeal 的 covered set或替代 §4 seal。

`EntryExecutionBinding.v0.2.2` 使用 v0.2.1 §12.2 exact fields/algorithms并作以下机械替换：

```text
schema_version =
  "rsi-mtf-drl-pm.entry-execution-binding.v0.2.2"
shared-synthetic-entry-request/v0.2.2
shared-synthetic-entry-order/v0.2.2
shared-synthetic-entry-event/v0.2.2
entry-execution-binding/v0.2.2
```

它引用 §8.3 的 v0.2.2 SharedEntryAction。C4/C5 byte-exact cohort、trace、terminal proof、cost binding与未来不可读规则保持有效。

---

## 10. Reducer total order、submission causality 与 rule change

### 10.1 `ReducerPriorityPolicy.v0.2.2`

Exact keys：

```text
schema_version,event_rank,stop_ack_rank_predicate,
tie_break,unknown_event_action,policy_sha256
```

`event_rank` 是 exact object，必须恰好包含全部 34 个 `ReducerEventKind` key，不多不少：

```text
{
  ACCOUNT_MISMATCH:1,
  KILL:1,
  DATA_HEALTH_INVALID:1,
  EVENT_CONFLICT:1,

  FILL_CUMULATIVE:2,
  EXIT_FILL_CUMULATIVE:2,
  POSITION_SNAPSHOT:2,

  FUNDING_DEBIT:3,
  STOP_HIT:4,
  STOP_ACK:{MATCHING_SUFFICIENT:5,OTHERWISE:10},

  PENDING_DEADLINE:6,
  STOP_REJECT_OR_UNKNOWN:6,
  PROTECTION_REPAIR:6,

  STRUCTURE_EXIT:7,
  TARGET_HIT:8,
  HORIZON:9,

  STOP_REQUEST:10,
  TARGET_REQUEST:10,
  TARGET_ACK:10,
  TARGET_REJECT_OR_UNKNOWN:10,
  REDUCE_ONLY_EXIT_REQUEST:10,
  EXIT_ACK:10,
  EXIT_REJECT_OR_UNKNOWN:10,
  RECONCILE_OK:10,

  CONTROL_ABSTAIN:11,
  ENTRY_SUBMIT:11,
  ENTRY_ACK:11,
  ENTRY_REJECT:11,
  ENTRY_EXPIRE:11,
  CANCEL_REQUEST:11,
  CANCEL_ACK:11,
  CANCEL_REJECT_OR_UNKNOWN:11,

  BARRIER_EVALUATION:12,
  NO_CHANGE:12
}
```

Exact literals：

```text
schema_version =
  "rsi-mtf-drl-pm.reducer-priority-policy.v0.2.2"

stop_ack_rank_predicate =
  "PREFIX_CURRENT_PROTECTION_REQUEST_EXACT_ID_PRICE_QTY_SIDE_REDUCE_ONLY_ROLE_AND_COVERAGE_SUFFICIENT"

tie_break =
  ["event_time_us","priority_rank","source_sequence","source_event_id"]

unknown_event_action = "REJECT_BUNDLE"
```

STOP_ACK 的两个 predicate 是互斥且穷尽的 complement。rank 必须在已处理 prefix 上重算；fixture 不得自行声明 sufficient。每个 enum 正好命中一个 rank branch。

```text
policy_sha256 =
  ID("reducer-priority-policy/v0.2.2",
     entire object excluding policy_sha256)
```

`PiExitPolicy.v0.2.2` 使用 v0.2.1 §12.1 的全部 exact fields与 nested objects，但：

```text
schema_version = "rsi-mtf-drl-pm.pi-exit.v0.2.2"
policy_id = "pi-exit.v0.2.2"
reducer_policy_id = "fill-protect-reconcile.v0.2.2"
pivot_policy_id = "pivot-theta.v0.2.2"
target_boundary_policy_id = "target-boundary-theta.v0.2.2"
priority = full ReducerPriorityPolicy.v0.2.2 object
policy_sha256 =
  ID("pi-exit-policy/v0.2.2",
     entire object excluding policy_sha256)
```

为消除旧版自由字符串 policy ID，PiExit successor 的字段集合还必须执行一次 exact replacement：

```text
minus {
  ev_evidence_policy_id,
  cost_policy_id,
  risk_policy_id,
  label_policy_id
}

plus {
  estimator_policy_sha256,
  cost_policy_sha256,
  risk_policy_sha256,
  data_role_sha256,
  v0_2_label_contract_sha256
}
```

前四项分别等于 §2 registry 对应 policy；`v0_2_label_contract_sha256` 等于 §2.1。PiExit 不引用最终 FirstHit/LabelPolicy hash，以避免 `PiExit → FirstHit → PiExit` 摘要环；FirstHit 单向绑定 PiExit。

旧八符号 priority array 完全禁止。Pi policy 内嵌 priority object必须与唯一 REDUCER_PRIORITY_POLICY artifact逐 byte相等。

### 10.2 Submission root 与 descendant

对一个 submission control，定义：

```text
submission_descendant(e) =
  ENTRY_SUBMIT.source_event_id
  位于 e.predecessor_event_ids 的传递闭包
```

ENTRY_SUBMIT 本身不是 descendant。它必须：

```text
event_time_us = lane_available_at_us = SharedEntryAction.action_at_us
economic_event_time_us = null
```

并绑定 §8 proof/action。每个 `submission_descendant(e)` 必须：

```text
e.event_time_us > action_at_us
若 e.economic_event_time_us 非 null：
  e.economic_event_time_us > action_at_us
```

相等也拒绝。所有 entry ACK/reject/expire/fill/cancel status 与由 submission/open risk 因果产生的 protection/exit events必须是 descendant；缺 predecessor path 不能仅靠较晚时间补足。pre-submit CONTROL_ABSTAIN、rule change 与 unrelated diagnostic 不得伪造为 descendant。

### 10.3 Rule change event mapping

§5.3 的 mapping 是唯一合法映射：

```text
before ENTRY_SUBMIT:
  CONTROL_ABSTAIN / reason=RULE_CHANGE

after ENTRY_SUBMIT or reserve/open risk:
  DATA_HEALTH_INVALID / reason_code=RULE_CHANGE
```

第二种 event 必须是 submission descendant，按 rank 1 优先并进入既有 HALT/reduce-only/reconcile。不得生成不存在的 `EPISODE_TERMINAL` event kind，也不得仅因 snapshot ID 改变触发 rule change。

---

## 11. Pivot、Target 与 path identity

### 11.1 Pivot

`PivotTheta.v0.2.2` 继承 v0.2.1 §10.1 公式，只能使用 §5.4 生成的 1 秒 grid points，且必须绑定唯一 `(t-300s,t]` BOOK_SNAPSHOT CoverageSeal。

extreme tie-break 已由 §5.4 完整定义。`pivot_input_sha256` 使用 §9.3 domain；任何 raw-book shortcut、缺秒或 seal conflict 返回 UNKNOWN。

### 11.2 `TargetCandidate.v0.2.2`

两类候选公式不变，identity 完整替换。

`ThreePointTargetCandidate` exact keys：

```text
candidate_kind,side,grid_times_us,rounded_price,
input_artifact_ids,coverage_seal_artifact_id,
coverage_seal_sha256,priority_rank,candidate_id
```

Exact constraints：

```text
candidate_kind = "THREE_POINT_FAVORABLE_PIVOT"
grid_times_us = [u-1_000_000,u,u+1_000_000]
input_artifact_ids =
  [book artifact at u-1s, book artifact at u, book artifact at u+1s]
priority_rank = 0
```

两个数组按时间顺序保留，不按 ID 排序。每个 artifact 必须是 §5.4 对该 grid time 的实际 selected BOOK wrapper；`input_artifact_ids` 中禁止放 UtcUs、Book.event_id 或虚构 ID。

```text
candidate_id =
  ID("target-three-point/v0.2.2", {
    side,grid_times_us,rounded_price,input_artifact_ids,
    coverage_seal_artifact_id,coverage_seal_sha256
  })
```

`WindowExtremeTargetCandidate` exact keys：

```text
candidate_kind,side,window_start_exclusive_us,
window_end_inclusive_us,rounded_price,
winner_grid_time_us,winner_book_artifact_id,winner_book_event_id,
coverage_seal_artifact_id,coverage_seal_sha256,
priority_rank,candidate_id
```

Exact constraints：

```text
candidate_kind = "WINDOW_FAVORABLE_EXTREME"
priority_rank = 1
winner 是 §5.4 grid points 中 favorable extreme 与 exact tie-break 的结果
```

```text
candidate_id =
  ID("target-window-extreme/v0.2.2", {
    side,window_start_exclusive_us,window_end_inclusive_us,
    rounded_price,winner_grid_time_us,
    winner_book_artifact_id,winner_book_event_id,
    coverage_seal_artifact_id,coverage_seal_sha256
  })
```

所有时间字段必须使用 exact `*_us` 名；旧 `lane_available_at/window_start_exclusive/window_end_inclusive` 不存在 alias。

### 11.3 Target selection

候选先通过 v0.2.1 §10.2 geometry、Tcap、non-crossing 与 EV rules，再按 exact：

```text
[
  "MAX_LCB_RELATIVE_EV",
  "MIN_EXTENSION",
  "MIN_PRIORITY_RANK",
  "LEX_STABLE_ID"
]
```

其中：

- relative EV = HOLD LCB − EXIT_NOW LCB；
- extension = §7.2 的 nonnegative extension bp bucket；
- priority_rank 是 candidate 的 0/1；
- StableId 是 candidate_id。

HOLD/EXIT_NOW 必须是 §7.4 的同 bucket pair。任一 evidence UNKNOWN、conflict 或单边缺失使该候选 UNKNOWN；不得改用平均值或另一 evidence。

每个可排序 candidate 的 pair 必须在同一 BARRIER_EVALUATION 的
`candidate_evidence_bindings` 中唯一出现。排序结果必须逐字等于 payload 的
`target_winner_candidate_id`；target input digest同时绑定完整排序输入数组与该
winner。禁止只保存 winner evidence、让多个 target 复用同一 pair，或在 digest
外重新选择 candidate。

### 11.4 Path grid

v0.2.1 §12.3 每个 expected path grid 统一调用 §5.4。`BookPoint` 的 `book_artifact_id` 必须是实际 wrapper ID，`book_event_id` 是 payload.event_id；二者不可互换。

source coverage artifact 必须是 §4 的 exact BOOK_SNAPSHOT seal。ZERO_GRID_OPERATIONAL_OVERRIDE 仍允许 source coverage null；除此以外，缺 seal或 seal不完整必须显式 CENSOR，不能把 bundle.coverage 当 source proof。

---

## 12. Ledger、policy bindings 与 label successor

### 12.1 Frozen policy bindings

`FrozenLedgerSeed.policy_bindings.v0.2.2` exact keys：

```text
u_policy_sha256
entry_policy_sha256
exit_policy_template_sha256
cost_policy_sha256
risk_policy_sha256
label_policy_sha256
data_role_sha256
estimator_policy_sha256
source_selector_policy_sha256
reducer_priority_policy_sha256
policy_bundle_sha256
```

前八项与 §2.4 `PolicyBundle` 逐字段相等；`source_selector_policy_sha256` 等于 §5.6；`reducer_priority_policy_sha256` 等于 §10.1；`policy_bundle_sha256` 必须从前八项重算。旧 `entry_contract_sha256` 字段不再是 alias。

`ManagementLedgerBindings.v0.2.2` exact keys：

```text
core_raw_sha256
v0_2_contract_canonical_sha256
v0_2_1_addendum_raw_sha256
v0_2_2_delta_raw_sha256
v0_2_2_contract_sha256
composite_theory_id
policy_bundle_sha256
code_sha256
data_or_fixture_sha256
ledger_seed_sha256
```

前四项逐字绑定 §0.1，contract SHA 是 P0-RSI-01C 产物的 full canonical digest，composite按 §0.1重算，`policy_bundle_sha256=FrozenLedgerSeed.policy_bindings.policy_bundle_sha256`，`data_or_fixture_sha256=SyntheticFixtureManifest.manifest_sha256`。

为避免 self-reference，contract JSON 只定义 `v0_2_2_contract_sha256` 的 type与外部 equality rule，不得在自身 canonical bytes中嵌入一个声称等于自身的 concrete digest。P0-RSI-01C 完成序列唯一为：

```text
1. serialize contract without self-digest value
2. compute full canonical contract digest
3. write immutable ContractDigestReceipt 与 SchemaTransformReceipt
4. P0-RSI-02 生成并验证 ImplementationManifest/Receipt
5. runtime ledger/label binding读取三个 PASS receipts并写入唯一 digest
```

receipt 不回写 contract。validator 必须同时验证 receipt 指向的 contract bytes；自由传入的 64 hex 不构成 authority。

v0.2.1 ledger record top-level/nested schema与 reducer state projection继续有效，机械升版：

```text
schema_version =
  "rsi-mtf-drl-pm.management-ledger.v0.2.2"
operator =
  {kind:"SYSTEM",id:"rsi-mtf-drl-pm-reducer-v0.2.2"}
management-ledger/v0.2.2
management-genesis/v0.2.2
management-genesis-inputs/v0.2.2
management-event/v0.2.2
management-record-inputs/v0.2.2
management-ledger-record/v0.2.2
canonical-synthetic-event-envelope/v0.2.2
```

record.bindings 使用本节 exact object；原来的单一 `policy_sha256` 被 `policy_bundle_sha256` 完整替换。

### 12.1A 全量 ledger artifact descriptor 映射

对 reducer 当前 event 的每个 `input_artifact_id`，descriptor exact keys 为：

```text
input_id,payload_sha256,lane_available_at_us,quality
```

Exact types：

```text
input_id:StableId
payload_sha256:Sha256
lane_available_at_us:UtcUs
quality:enum{VALID,UNKNOWN,INVALID,CONFLICT}
```

`input_id=wrapper.artifact_id`，
`payload_sha256=wrapper.payload_sha256`。descriptor 按 `input_id` 严格升序，
无重复。以下表格是 `ArtifactSchemaId.v0.2.2` 全部 20 个成员的封闭时间与
quality 映射：

| schema_id | descriptor lane_available_at_us | descriptor quality |
|---|---|---|
| CLOSED_MARK_BAR | wrapper.available_at_us | payload VALID→VALID，GAP→UNKNOWN，INVALID→INVALID，CONFLICT→CONFLICT |
| BOOK_SNAPSHOT | wrapper.available_at_us | payload VALID且 sequence_contiguous=true→VALID；GAP→UNKNOWN；INVALID→INVALID；CONFLICT或 sequence conflict→CONFLICT |
| AGG_TRADE | wrapper.available_at_us | payload VALID→VALID，GAP→UNKNOWN，INVALID→INVALID，CONFLICT→CONFLICT |
| OPEN_INTEREST | wrapper.available_at_us | payload VALID→VALID，GAP→UNKNOWN，INVALID→INVALID，CONFLICT→CONFLICT |
| SOURCE_COVERAGE_SEAL | wrapper.available_at_us | complete=true且 gap=[] 且 exact covered-set/sequence checks通过→VALID；identity conflict或任一 gap.reason=CONFLICT→CONFLICT；其余 incomplete/ordinary gap→UNKNOWN |
| VENUE_INSTRUMENT_SNAPSHOT | wrapper.available_at_us | payload quality 的 VALID/INVALID/CONFLICT 同名映射；VALID还须通过 §5.1 structural checks |
| ACCOUNT_RISK_SNAPSHOT | wrapper.available_at_us | payload quality 的 VALID/INVALID/CONFLICT 同名映射；VALID还须通过 §5.2 exact checks |
| FROZEN_EV_EVIDENCE | wrapper.available_at_us | exact schema/hash/statistics通过→VALID；`n<ev_min_n` 是 calculator UNKNOWN，不改变 descriptor quality |
| U_OBSERVATION_RECEIPT | payload.evaluation_at_us | exact schema/hash/binding通过→VALID |
| SYNTHETIC_FIXTURE_MANIFEST | ledger_seed.anchor_at_us | exact schema/hash/source-query closure通过→VALID |
| POLICY_REGISTRY | ledger_seed.anchor_at_us | exact schema/hash/policy closure通过→VALID |
| REDUCER_PRIORITY_POLICY | ledger_seed.anchor_at_us | exact schema/hash且等于 registry binding→VALID |
| PI_EXIT_POLICY | ledger_seed.anchor_at_us | exact schema/hash且等于 registry binding→VALID |
| FIRST_HIT_LABEL_POLICY | ledger_seed.anchor_at_us | exact schema/hash且等于 registry binding→VALID |
| DECISION_INPUT_BINDING | payload.decision_at_us | exact proof重算与 closure通过→VALID |
| SHARED_ENTRY_ACTION | payload.action_at_us | exact action/proof binding通过→VALID |
| EXIT_POLICY_INSTANCE | first nonzero fill causal-effective time | exact schema/hash且与该 fill后 policy instance逐字相等→VALID |
| C4_C5_EXOGENOUS_PATH_MANIFEST | ledger_seed.anchor_at_us | exact schema/hash与传递 ID closure通过→VALID |
| SYNTHETIC_FUNDING_OBSERVATION | wrapper.available_at_us | exact schema/hash通过→VALID |
| SYNTHETIC_CONFLICT_PROOF | wrapper.available_at_us | CONFLICT |

表中 `wrapper.available_at_us` 必须 non-null并逐字等于 §9.1 的 schema mapping；
static/manifest row 的 wrapper availability 必须 null，descriptor 时间才唯一替换为
`ledger_seed.anchor_at_us`。每个 descriptor time 都必须
`<=event.event_time_us`。enum 外无 fallback；malformed、hash mismatch、
scope mismatch、wrong successor 或表中要求的 exact binding失败都在 bundle
validation 阶段直接拒绝，绝不能降级成 UNKNOWN。

### 12.2 `LabelBindings.v0.2.2`

Exact keys：

```text
core_raw_sha256
v0_2_contract_canonical_sha256
v0_2_1_addendum_raw_sha256
v0_2_2_delta_raw_sha256
v0_2_2_contract_sha256
composite_theory_id
candidate_id
policy_bundle_sha256
code_sha256
data_or_fixture_sha256
synthetic_bundle_sha256
entry_execution_binding_sha256
management_ledger_head_sha256
label_policy_sha256
```

`label_policy_sha256=PolicyRegistry.label_policy.policy_sha256`；该 object 内再唯一绑定 §12.3 FirstHitLabelPolicy。重复字段必须与 ledger/bundle/registry/manifest逐字一致。NO_ACTION 的 no-entry identity domain 改为：

```text
ID("no-entry-execution/v0.2.2", {opportunity_id,control_id})
```

label record domain 改为：

```text
label_record_sha256 =
  ID("label-record/v0.2.2", {
    bindings:LabelBindings.v0.2.2,
    label:label envelope excluding label_record_sha256
  })
```

FirstHit label envelope top-level exact keys：

```text
control_id,side,action_at_us,submission_label,execution_flags,
observation_status,censor_reason,market_path_label,
terminal_event_id,terminal_at_us,fill_sequence_sha256,
path_input_sha256,pi_exit_sha256,label_record_sha256
```

它的 type、nullable combination、winner/censor/fill/path semantics逐字使用冻结的 v0.2.1 §12.5，只把 LabelBindings、PiExit、PathInputBundle、management IDs 与 label domain替换成本文件 successor。无字段新增、删除或重命名。

### 12.3 `FirstHitLabelPolicy.v0.2.2`

Exact keys：

```text
schema_version,control_dispatch,observation_grid_rule,
snapshot_selection_rule,trigger_rule,arbitration_rule,
operational_override_rule,no_fill_rule,partial_fill_rule,
horizon_rule,label_tail_rule,pi_exit_sha256,policy_sha256
```

Exact values：

```text
schema_version =
  "rsi-mtf-drl-pm.first-hit-label-policy.v0.2.2"

control_dispatch = {
  C0:"NO_MARKET_PATH",
  C1:"FIXED_S0_I0_T0_H0",
  C2:"FIXED_S0_I0_T0_H0",
  C3:"FIXED_S0_I0_T0_H0",
  C4:"FIXED_S0_I0_T0_H0",
  Cmu:"FIXED_S0_I0_T0_H0",
  C5:"DYNAMIC_PI_EXIT_EXACT_C4_FILL"
}

observation_grid_rule =
  "SECTION_11_4_EXACT_PREFIX_GRID"
snapshot_selection_rule =
  "SECTION_5_SELECT_BOOK_THEN_GRID_COMMIT_WITH_POST_FILL_PROOF"
trigger_rule =
  "V0_2_1_SECTION_12_4_DIRECT_AND_ACKED_BARRIER_TRIGGERS"
arbitration_rule =
  "SECTION_10_1_FULL_REDUCER_PRIORITY_AND_STOP_FIRST"
operational_override_rule =
  "CAUSE_EVENT_POSITION_NOT_GLOBAL_PREEMPTION"
no_fill_rule =
  "SEPARATE_SUBMISSION_LABEL_NO_MARKET_PATH"
partial_fill_rule =
  "EXECUTION_FLAG_NOT_MARKET_CLASS"
horizon_rule =
  "ABSOLUTE_H0_ENDPOINT_INCLUDED_NO_EXTENSION"
label_tail_rule =
  "ROLE_CHRONOLOGY_LABEL_TAIL_BEFORE_FINALIZE"
pi_exit_sha256 = PiExitPolicy.v0.2.2.policy_sha256
```

```text
policy_sha256 =
  ID("first-hit-label-policy/v0.2.2",
     entire object excluding policy_sha256)
```

### 12.4 `ExitPolicyInstance.v0.2.2`

Exact keys：

```text
schema_version,opportunity_id,control_id,side,template_id,
initial_levels,dynamic_policy_sha256,
reducer_priority_policy_sha256,
same_timestamp_rule,horizon_rule,policy_instance_sha256
```

Exact constraints：

```text
schema_version =
  "rsi-mtf-drl-pm.exit-policy-instance.v0.2.2"
template_id enum{FIXED_S0_I0_T0_H0,DYNAMIC_PI_EXIT}
control_id=C5 iff template_id=DYNAMIC_PI_EXIT
initial_levels exact keys =
  p_limit,pe,i0,g0,s0,t0,tcap,h0_us
dynamic_policy_sha256 =
  PiExitPolicy.policy_sha256 iff C5 else null
reducer_priority_policy_sha256 =
  ReducerPriorityPolicy.policy_sha256
same_timestamp_rule = "STOP_FIRST"
horizon_rule = "ABSOLUTE_H0_NO_EXTENSION"
```

C5/C4 initial_levels byte-identical，其他 v0.2.1 §12.3 geometry binding约束不变。

```text
policy_instance_sha256 =
  ID("exit-policy-instance/v0.2.2",
     entire object excluding policy_instance_sha256)
```

旧 `priority` field完全不存在，也没有内嵌/摘要两种 representation。

### 12.5 `C4C5ExogenousPathManifest.v0.2.2`

Exact keys：

```text
schema_version,opportunity_id,candidate_id,lane_id,
availability_kind,path_start_us,h0_us,
book_artifact_ids,funding_artifact_ids,
source_coverage_artifact_ids,manifest_sha256
```

Exact literals：

```text
schema_version =
  "rsi-mtf-drl-pm.c4-c5-exogenous-path-manifest.v0.2.2"
availability_kind = "SYNTHETIC"
```

三个 ID arrays各自去重、lex排序并唯一命中对应 BOOK、FUNDING、SOURCE_COVERAGE artifacts。正常 path 的 book IDs 必须恰好等于 §11.4 selected grid；funding IDs 必须恰好等于 `[first_fill_causal_time_us,H0]` 内所有 admissible funding observations；coverage IDs必须恰好列出所用 seal。ZERO_GRID_OPERATIONAL_OVERRIDE 时三个 arrays全空。

```text
zero_grid_shared_cause_id =
  ID("zero-grid-shared-cause/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,
    event_kind,event_time_us,economic_event_time_us,
    shared_entry_event_id,input_artifact_ids,payload_sha256
  })

manifest_sha256 =
  ID("c4-c5-exogenous-path-manifest/v0.2.2",
     entire object excluding manifest_sha256)
```

`zero_grid_shared_cause_id` 是 validator transient value，不是 manifest field；C4/C5 必须重算相同值。

### 12.6 `PathInputBundle.v0.2.2`

Base schema唯一为冻结的 v0.2.1 addendum §12.3 `PathInputBundle.v0.2.1`。successor 的 top-level exact keys仍为：

```text
schema_version,opportunity_id,control_id,side,lane_id,
availability_kind,first_fill_shared_event_id,
first_fill_economic_time_us,first_fill_causal_time_us,
path_start_us,h0_us,evaluated_through_us,status,censor_reason,
censor_cause_event_id,synthetic_coverage_sha256,
source_coverage_artifact_id,source_coverage_seal_sha256,
book_points,missing_grid_times_us,reducer_events,funding_events,
funding_events_sha256,exit_policy_sha256,path_input_sha256
```

successor 必须是唯一 ID 为
`PATH_INPUT_BUNDLE_V0_2_1_TO_V0_2_2` 的 TransformSet 对冻结 base AST
逐 operation应用后的唯一 result AST。实现不得从本段自然语言推断 patch，也不得
以 section pointer、diff note 或人工“保持不变”标记替代 result AST digest。

### 12.7 Feature identity successor preimages

以下五个 identity 不采用 domain-only replacement，而使用这里的完整 preimage：

```text
rsi_cross_event_id =
  ID("rsi-cross-event/v0.2.2", {
    candidate_id,venue_id,instrument_id,lane_id,availability_kind,
    control_id,side,grid_close_us,previous_state,current_boolean,
    input_bar_artifact_ids,input_bar_ids
  })
```

两个 bar arrays 都按 `(period_seconds,bar_close_at_us,stable_bar_id)` 的同一 bar顺序；前者写 wrapper artifact IDs，后者写 payload stable_bar_ids。

```text
d_evidence_sha256 =
  ID("d-grid-input/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,source_id,
    window_start_exclusive_us,window_end_inclusive_us,
    coverage_seal_artifact_id,coverage_seal_sha256,
    agg_trade_artifact_ids,agg_trade_event_ids
  })
```

两个 trade arrays 按 §3.2 同一顺序一一对应。

```text
pressure_event_id =
  ID("pressure-run/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,source_id,
    side,t_start_us,t_p_us,pressure_grid_inputs
  })
```

`pressure_grid_inputs` exact fields保持 `grid_time_us,d_value,d_evidence_sha256,state`。

```text
g0_candidate_id =
  ID("g0-executable-touch/v0.2.2", {
    venue_id,instrument_id,lane_id,availability_kind,source_id,
    policy_id:"EXECUTABLE_PRICE_TOUCH_V1",
    side,rounded_price,grid_time_us,source_event_time_us,
    book_artifact_id,book_event_id,
    coverage_seal_artifact_id,coverage_seal_sha256
  })
```

G0 的去重与选择是两个不同阶段。先以 exact key
`(rounded_price,grid_time_us)` 分组；每组只保留按
`(lane_available_at_us,source_sequence,book_event_id)` 升序的首项。相同
`rounded_price` 但不同 `grid_time_us` 的候选必须保留为不同候选，禁止跨 grid
去重。完成组内去重后，才对剩余候选应用冻结的全局 G0 排序
`(favorable_distance,priority_rank,lane_available_at_us,stable_id)` 并取首项。

```text
opportunity_id =
  ID("master-opportunity/v0.2.2", {
    u_policy_sha256,venue_id,instrument_id,lane_id,
    availability_kind,role,cycle_start_us
  })
```

当前两项 literal仍为 SYNTHETIC。RSI event ledger key 同时升级为：

```text
(candidate_id,venue_id,instrument_id,lane_id,availability_kind,
 control_id,side,grid_close_us)
```

### 12.8 Exhaustive old-domain transform registry

对下表每一项，`DOMAIN_ONLY` 的机械含义只有：使用 v0.2.1 已冻结 clause 中完全相同的 exact preimage object，唯一把 ASCII domain literal 从左列替换为右列；不得添加、删除、重命名或重排 preimage fields。`REDEFINED` 表示 preimage 已在指定 section完整给出。

| old domain | v0.2.2 domain | transform |
|---|---|---|
| `account-mismatch-details/v0.2.1` | `account-mismatch-details/v0.2.2` | DOMAIN_ONLY |
| `account-risk-snapshot/v0.2.1` | `account-risk-snapshot/v0.2.2` | REDEFINED §5.2 |
| `agg-trade/v0.2.1` | `agg-trade/v0.2.2` | REDEFINED §3.1 |
| `book-snapshot/v0.2.1` | `book-snapshot/v0.2.2` | REDEFINED §3.1 |
| `c4-c5-exogenous-path-manifest/v0.2.1` | `c4-c5-exogenous-path-manifest/v0.2.2` | REDEFINED §12.5 |
| `candidate-parameter-set/v0.2.1` | `candidate-parameter-set/v0.2.2` | REDEFINED §2.2 |
| `candidate-policy-bundle/v0.2.1` | `candidate-policy-bundle/v0.2.2` | REDEFINED §2.4 |
| `canonical-synthetic-artifact-set/v0.2.1` | `canonical-synthetic-artifact-set/v0.2.2` | DOMAIN_ONLY |
| `canonical-synthetic-bundle-scope/v0.2.1` | `canonical-synthetic-bundle-scope/v0.2.2` | REDEFINED §9.4 |
| `canonical-synthetic-coverage/v0.2.1` | `canonical-synthetic-coverage/v0.2.2` | DOMAIN_ONLY |
| `canonical-synthetic-event-bundle/v0.2.1` | `canonical-synthetic-event-bundle/v0.2.2` | REDEFINED §9.4 |
| `canonical-synthetic-event-envelope/v0.2.1` | `canonical-synthetic-event-envelope/v0.2.2` | DOMAIN_ONLY |
| `canonical-synthetic-event-presequence/v0.2.1` | `canonical-synthetic-event-presequence/v0.2.2` | REDEFINED §9.3 |
| `canonical-synthetic-event-set/v0.2.1` | `canonical-synthetic-event-set/v0.2.2` | DOMAIN_ONLY |
| `canonical-synthetic-event/v0.2.1` | `canonical-synthetic-event/v0.2.2` | REDEFINED §9.3 |
| `closed-mark-bar/v0.2.1` | `closed-mark-bar/v0.2.2` | REDEFINED §3.1 |
| `control-abstain-terminal/v0.2.1` | `control-abstain-terminal/v0.2.2` | DOMAIN_ONLY |
| `d-grid-input/v0.2.1` | `d-grid-input/v0.2.2` | REDEFINED §12.7 |
| `entry-execution-binding/v0.2.1` | `entry-execution-binding/v0.2.2` | REDEFINED §9.4 |
| `exit-policy-instance/v0.2.1` | `exit-policy-instance/v0.2.2` | REDEFINED §12.4 |
| `first-hit-label-policy/v0.2.1` | `first-hit-label-policy/v0.2.2` | REDEFINED §12.3 |
| `frozen-action-context/v0.2.1` | `frozen-action-context/v0.2.2` | REDEFINED §8.4 |
| `frozen-ledger-seed/v0.2.1` | `frozen-ledger-seed/v0.2.2` | REDEFINED §8.4 |
| `g0-executable-touch/v0.2.1` | `g0-executable-touch/v0.2.2` | REDEFINED §12.7 |
| `label-censor-terminal/v0.2.1` | `label-censor-terminal/v0.2.2` | DOMAIN_ONLY |
| `label-record/v0.2.1` | `label-record/v0.2.2` | REDEFINED §12.2 |
| `management-event/v0.2.1` | `management-event/v0.2.2` | DOMAIN_ONLY |
| `management-genesis-inputs/v0.2.1` | `management-genesis-inputs/v0.2.2` | DOMAIN_ONLY |
| `management-genesis/v0.2.1` | `management-genesis/v0.2.2` | DOMAIN_ONLY |
| `management-ledger/v0.2.1` | `management-ledger/v0.2.2` | REDEFINED §12.1 bindings |
| `management-record-inputs/v0.2.1` | `management-record-inputs/v0.2.2` | DOMAIN_ONLY |
| `master-opportunity/v0.2.1` | `master-opportunity/v0.2.2` | REDEFINED §12.7 |
| `no-entry-execution/v0.2.1` | `no-entry-execution/v0.2.2` | REDEFINED §12.2 |
| `open-interest/v0.2.1` | `open-interest/v0.2.2` | REDEFINED §3.1 |
| `path-funding-events/v0.2.1` | `path-funding-events/v0.2.2` | REDEFINED §12.6 |
| `path-input-bundle/v0.2.1` | `path-input-bundle/v0.2.2` | REDEFINED §12.6 |
| `pi-exit-policy/v0.2.1` | `pi-exit-policy/v0.2.2` | REDEFINED §10.1 |
| `pivot-evaluation-inputs/v0.2.1` | `pivot-evaluation-inputs/v0.2.2` | REDEFINED §9.3 |
| `pressure-run/v0.2.1` | `pressure-run/v0.2.2` | REDEFINED §12.7 |
| `rsi-cross-event/v0.2.1` | `rsi-cross-event/v0.2.2` | REDEFINED §12.7 |
| `rsi-mtf-drl-pm-candidate/v0.2.1` | `rsi-mtf-drl-pm-candidate/v0.2.2` | REDEFINED §2.4 |
| `rsi-mtf-drl-pm-composite-theory/v0.2.1` | `rsi-mtf-drl-pm-composite-theory/v0.2.2` | REDEFINED §0.1 |
| `shared-entry-action/v0.2.1` | `shared-entry-action/v0.2.2` | REDEFINED §8.3 |
| `shared-synthetic-entry-event/v0.2.1` | `shared-synthetic-entry-event/v0.2.2` | DOMAIN_ONLY with v0.2.2 entry_action_sha256 |
| `shared-synthetic-entry-order/v0.2.1` | `shared-synthetic-entry-order/v0.2.2` | DOMAIN_ONLY |
| `shared-synthetic-entry-request/v0.2.1` | `shared-synthetic-entry-request/v0.2.2` | DOMAIN_ONLY with v0.2.2 entry_action_sha256 |
| `source-coverage-seal/v0.2.1` | `source-coverage-seal/v0.2.2` | REDEFINED §4 |
| `synthetic-artifact/v0.2.1` | `synthetic-artifact/v0.2.2` | REDEFINED §9.1 |
| `synthetic-conflict-proof/v0.2.1` | `synthetic-conflict-proof/v0.2.2` | REDEFINED §9.2 |
| `synthetic-fatal-details/v0.2.1` | `synthetic-fatal-details/v0.2.2` | DOMAIN_ONLY |
| `synthetic-funding/v0.2.1` | `synthetic-funding/v0.2.2` | REDEFINED §9.2 |
| `synthetic-management-order/v0.2.1` | `synthetic-management-order/v0.2.2` | DOMAIN_ONLY |
| `synthetic-management-request/v0.2.1` | `synthetic-management-request/v0.2.2` | DOMAIN_ONLY |
| `target-evaluation-inputs/v0.2.1` | `target-evaluation-inputs/v0.2.2` | REDEFINED §9.3 |
| `target-three-point/v0.2.1` | `target-three-point/v0.2.2` | REDEFINED §11.2 |
| `target-window-extreme/v0.2.1` | `target-window-extreme/v0.2.2` | REDEFINED §11.2 |
| `venue-instrument-snapshot/v0.2.1` | `venue-instrument-snapshot/v0.2.2` | REDEFINED §5.1 |
| `zero-grid-shared-cause/v0.2.1` | `zero-grid-shared-cause/v0.2.2` | REDEFINED §12.5 |

另有非 `ID(...)` 的 record hash ASCII domain：

```text
management-ledger-record/v0.2.1
  -> management-ledger-record/v0.2.2
```

preimage仍是 `CanonicalJSON(record excluding record_hash)`。

本表是 v0.2.1 文档中所有规范 identity domain 的封闭输入集合。builder 必须静态扫描冻结 v0.2.1 raw bytes：

```text
set(found_old_domains) = set(left_column_domains)
```

少一个、多一个、重复映射或发现未映射 old domain，都停止为 `UNMAPPED_IDENTITY_DOMAIN`。本文件新增 domain 由其定义 section直接注册，不参与左列 equality check。

### 12.9 Mechanical AST transform registry

继承不是自然语言规则。P0-RSI-01C 必须先把冻结 v0.2.1 canonical contract解析为
`ContractAST.v0.2.2`，再按本节有限 operations 产生 successor。

`ContractAST.v0.2.2` exact keys：

```text
ast_schema_version
source_contract_id
source_contract_sha256
types
field_sets
schemas
objects
algorithms
domains
exports
ast_sha256
```

所有 map key 为 ASCII string并按 UTF-8 bytes排序。schema/object/algorithm/domain
node 都是 canonical JSON value；禁止只保存 source section、行号或自由文本摘要。

```text
ast_schema_version = "rsi-mtf-drl-pm.contract-ast.v0.2.2"
ast_sha256 =
  ID("contract-ast/v0.2.2",
     entire object excluding ast_sha256)
```

`TransformOp.v0.2.2` exact keys：

```text
sequence,op,json_pointer,
old_node,old_node_sha256,
new_node,new_node_sha256,
operation_sha256
```

规则：

```text
sequence:int>=0
op enum{ADD,REMOVE,REPLACE}
json_pointer = RFC6901 absolute pointer

ADD:
  target does not exist
  old_node=null
  old_node_sha256=null
  new_node!=null
  new_node_sha256=SHA256(CanonicalJSON(new_node))

REMOVE:
  target exists and byte-equals old_node
  old_node!=null
  old_node_sha256=SHA256(CanonicalJSON(old_node))
  new_node=null
  new_node_sha256=null

REPLACE:
  target exists and byte-equals old_node
  old_node!=null
  new_node!=null
  old_node_sha256=SHA256(CanonicalJSON(old_node))
  new_node_sha256=SHA256(CanonicalJSON(new_node))

operation_sha256 =
  ID("schema-transform-operation/v0.2.2",
     entire operation excluding operation_sha256)
```

operations 的 sequence 必须从 0 连续，按 sequence应用。任一 target
existence、old-node bytes或 digest mismatch 立即停止；RFC6901 application
自然保留未被 operation触及的 AST nodes。

以下记法只用于紧凑列出 exact operation array，serializer 必须展开为上述 exact
object：

```text
R(pointer,old,new) = REPLACE
A(pointer,new)     = ADD
D(pointer,old)     = REMOVE
```

每个 JSON string/object/array 都是 operation 内的完整 `old_node/new_node`，
不是注释或 pointer。

#### TransformSet `ENTRY_EXECUTION_BINDING_V0_2_1_TO_V0_2_2`

```text
[
R("/schemas/EntryExecutionBinding/properties/schema_version/const",
  "rsi-mtf-drl-pm.entry-execution-binding.v0.2.1",
  "rsi-mtf-drl-pm.entry-execution-binding.v0.2.2"),
R("/schemas/EntryExecutionBinding/properties/shared_entry_action/$ref",
  "#/schemas/SharedEntryAction.v0.2.1",
  "#/schemas/SharedEntryAction.v0.2.2"),
R("/domains/shared_entry_request",
  "shared-synthetic-entry-request/v0.2.1",
  "shared-synthetic-entry-request/v0.2.2"),
R("/domains/shared_entry_order",
  "shared-synthetic-entry-order/v0.2.1",
  "shared-synthetic-entry-order/v0.2.2"),
R("/domains/shared_entry_event",
  "shared-synthetic-entry-event/v0.2.1",
  "shared-synthetic-entry-event/v0.2.2"),
R("/domains/entry_execution_binding",
  "entry-execution-binding/v0.2.1",
  "entry-execution-binding/v0.2.2")
]
```

#### TransformSet `PATH_INPUT_BUNDLE_V0_2_1_TO_V0_2_2`

```text
[
R("/schemas/PathInputBundle/properties/schema_version/const",
  "rsi-mtf-drl-pm.path-input-bundle.v0.2.1",
  "rsi-mtf-drl-pm.path-input-bundle.v0.2.2"),
R("/schemas/PathInputBundle/properties/reducer_events/items/properties/event_kind/$ref",
  "#/types/ReducerEventKind.v0.2.1",
  "#/types/ReducerEventKind.v0.2.2"),
R("/schemas/PathInputBundle/properties/source_coverage/$ref",
  "#/schemas/CoverageSeal.v0.2.1",
  "#/schemas/CoverageSeal.v0.2.2"),
R("/algorithms/PathInputBundle.book_selector/$ref",
  "#/algorithms/LocalLatestBook.v0.2.1",
  "#/algorithms/SelectBookThenGridCommit.v0.2.2"),
R("/domains/path_funding_events",
  "path-funding-events/v0.2.1",
  "path-funding-events/v0.2.2"),
R("/domains/path_input_bundle",
  "path-input-bundle/v0.2.1",
  "path-input-bundle/v0.2.2")
]
```

#### TransformSet `MANAGEMENT_LEDGER_V0_2_1_TO_V0_2_2`

```text
[
R("/schemas/ManagementLedger/properties/schema_version/const",
  "rsi-mtf-drl-pm.management-ledger.v0.2.1",
  "rsi-mtf-drl-pm.management-ledger.v0.2.2"),
R("/schemas/ManagementLedger/properties/bindings/$ref",
  "#/schemas/ManagementLedgerBindings.v0.2.1",
  "#/schemas/ManagementLedgerBindings.v0.2.2"),
R("/schemas/ManagementLedger/properties/operator/const",
  {"kind":"SYSTEM","id":"rsi-mtf-drl-pm-reducer-v0.2.1"},
  {"kind":"SYSTEM","id":"rsi-mtf-drl-pm-reducer-v0.2.2"}),
R("/domains/management_ledger",
  "management-ledger/v0.2.1","management-ledger/v0.2.2"),
R("/domains/management_genesis",
  "management-genesis/v0.2.1","management-genesis/v0.2.2"),
R("/domains/management_genesis_inputs",
  "management-genesis-inputs/v0.2.1","management-genesis-inputs/v0.2.2"),
R("/domains/management_event",
  "management-event/v0.2.1","management-event/v0.2.2"),
R("/domains/management_record_inputs",
  "management-record-inputs/v0.2.1","management-record-inputs/v0.2.2"),
R("/domains/management_ledger_record",
  "management-ledger-record/v0.2.1","management-ledger-record/v0.2.2"),
R("/domains/canonical_event_envelope",
  "canonical-synthetic-event-envelope/v0.2.1",
  "canonical-synthetic-event-envelope/v0.2.2")
]
```

#### TransformSet `PI_EXIT_POLICY_V0_2_1_TO_V0_2_2`

```text
[
R("/schemas/PiExitPolicy/properties/schema_version/const",
  "rsi-mtf-drl-pm.pi-exit.v0.2.1",
  "rsi-mtf-drl-pm.pi-exit.v0.2.2"),
R("/schemas/PiExitPolicy/properties/policy_id/const",
  "pi-exit.v0.2.1","pi-exit.v0.2.2"),
R("/schemas/PiExitPolicy/properties/reducer_policy_id/const",
  "fill-protect-reconcile.v0.2.1",
  "fill-protect-reconcile.v0.2.2"),
R("/schemas/PiExitPolicy/properties/pivot_policy_id/const",
  "pivot-theta.v0.2.1","pivot-theta.v0.2.2"),
R("/schemas/PiExitPolicy/properties/target_boundary_policy_id/const",
  "target-boundary-theta.v0.2.1",
  "target-boundary-theta.v0.2.2"),
R("/schemas/PiExitPolicy/properties/priority",
  {"type":"array","const":["KILL_ACCOUNT_MISMATCH","STOP_HIT","PROTECTION_REPAIR","STRUCTURE_EXIT","TARGET_HIT","TIMEOUT","BARRIER_UPDATE","NO_CHANGE"]},
  {"$ref":"#/schemas/ReducerPriorityPolicy.v0.2.2"}),
D("/schemas/PiExitPolicy/properties/ev_evidence_policy_id",
  {"type":"string","minLength":1}),
D("/schemas/PiExitPolicy/properties/cost_policy_id",
  {"type":"string","minLength":1}),
D("/schemas/PiExitPolicy/properties/risk_policy_id",
  {"type":"string","minLength":1}),
D("/schemas/PiExitPolicy/properties/label_policy_id",
  {"type":"string","minLength":1}),
A("/schemas/PiExitPolicy/properties/estimator_policy_sha256",
  {"$ref":"#/types/Sha256"}),
A("/schemas/PiExitPolicy/properties/cost_policy_sha256",
  {"$ref":"#/types/Sha256"}),
A("/schemas/PiExitPolicy/properties/risk_policy_sha256",
  {"$ref":"#/types/Sha256"}),
A("/schemas/PiExitPolicy/properties/data_role_sha256",
  {"$ref":"#/types/Sha256"}),
A("/schemas/PiExitPolicy/properties/v0_2_label_contract_sha256",
  {"$ref":"#/types/Sha256"}),
R("/schemas/PiExitPolicy/field_set/$ref",
  "#/field_sets/PiExitPolicy.v0.2.1",
  "#/field_sets/PiExitPolicy.v0.2.2"),
R("/domains/pi_exit_policy",
  "pi-exit-policy/v0.2.1","pi-exit-policy/v0.2.2")
]
```

#### TransformSet `CANONICAL_BUNDLE_V0_2_1_TO_V0_2_2`

```text
[
R("/schemas/CanonicalSyntheticEventBundle/properties/schema_version/const",
  "rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.1",
  "rsi-mtf-drl-pm.canonical-synthetic-event-bundle.v0.2.2"),
R("/schemas/CanonicalSyntheticEventBundle/properties/ledger_bindings/$ref",
  "#/schemas/ManagementLedgerBindings.v0.2.1",
  "#/schemas/ManagementLedgerBindings.v0.2.2"),
R("/schemas/CanonicalSyntheticEventBundle/properties/artifacts/items/$ref",
  "#/schemas/ArtifactWrapper.v0.2.1",
  "#/schemas/ArtifactWrapper.v0.2.2"),
R("/schemas/CanonicalSyntheticEventBundle/properties/event_array/items/$ref",
  "#/schemas/CanonicalSyntheticEvent.v0.2.1",
  "#/schemas/CanonicalSyntheticEvent.v0.2.2"),
R("/schemas/CanonicalSyntheticEventBundle/properties/coverage/$ref",
  "#/objects/CanonicalSyntheticCoverage.v0.2.1",
  "#/objects/CanonicalSyntheticCoverage.v0.2.2"),
R("/algorithms/CanonicalSyntheticEventBundle.root_closure/$ref",
  "#/algorithms/BundleRootClosure.v0.2.1",
  "#/algorithms/BundleRootClosure.v0.2.2"),
R("/domains/canonical_bundle_scope",
  "canonical-synthetic-bundle-scope/v0.2.1",
  "canonical-synthetic-bundle-scope/v0.2.2"),
R("/domains/canonical_event_set",
  "canonical-synthetic-event-set/v0.2.1",
  "canonical-synthetic-event-set/v0.2.2"),
R("/domains/canonical_event_bundle",
  "canonical-synthetic-event-bundle/v0.2.1",
  "canonical-synthetic-event-bundle/v0.2.2")
]
```

#### TransformSet `REDUCER_PAYLOAD_MAP_V0_2_1_TO_V0_2_2`

```text
[
R("/objects/ReducerPayloadMap/CONTROL_ABSTAIN/$ref",
  "#/schemas/ControlAbstainPayload.v0.2.1",
  "#/schemas/ControlAbstainPayload.v0.2.2"),
R("/objects/ReducerPayloadMap/ENTRY_SUBMIT/$ref",
  "#/schemas/EntrySubmitPayload.v0.2.1",
  "#/schemas/EntrySubmitPayload.v0.2.2"),
R("/objects/ReducerPayloadMap/BARRIER_EVALUATION/$ref",
  "#/schemas/BarrierEvaluationPayload.v0.2.1",
  "#/schemas/BarrierEvaluationPayload.v0.2.2"),
R("/algorithms/ReducerPayloadMap.FUNDING_DEBIT.funding_identity/$ref",
  "#/algorithms/FundingIdentity.v0.2.1",
  "#/algorithms/FundingIdentity.v0.2.2")
]
```

#### TransformSet `CANONICAL_COVERAGE_V0_2_1_TO_V0_2_2`

```text
[
R("/objects/CanonicalSyntheticCoverage/field_set/$ref",
  "#/field_sets/CanonicalSyntheticCoverage.v0.2.1",
  "#/field_sets/CanonicalSyntheticCoverage.v0.2.2"),
R("/algorithms/CanonicalSyntheticCoverage.branch/$ref",
  "#/algorithms/CanonicalCoverageBranch.v0.2.1",
  "#/algorithms/CanonicalCoverageBranch.v0.2.2"),
R("/domains/canonical_event_set",
  "canonical-synthetic-event-set/v0.2.1",
  "canonical-synthetic-event-set/v0.2.2"),
R("/domains/canonical_artifact_set",
  "canonical-synthetic-artifact-set/v0.2.1",
  "canonical-synthetic-artifact-set/v0.2.2"),
R("/domains/canonical_coverage",
  "canonical-synthetic-coverage/v0.2.1",
  "canonical-synthetic-coverage/v0.2.2")
]
```

#### TransformSet `MANAGEMENT_LEDGER_RECORD_V0_2_1_TO_V0_2_2`

```text
[
R("/objects/ManagementLedgerRecord/properties/bindings/$ref",
  "#/schemas/ManagementLedgerBindings.v0.2.1",
  "#/schemas/ManagementLedgerBindings.v0.2.2"),
R("/objects/ManagementLedgerRecord/properties/operator/const",
  {"kind":"SYSTEM","id":"rsi-mtf-drl-pm-reducer-v0.2.1"},
  {"kind":"SYSTEM","id":"rsi-mtf-drl-pm-reducer-v0.2.2"}),
R("/algorithms/ManagementLedgerRecord.input_descriptor/$ref",
  "#/algorithms/LedgerInputDescriptorMap.v0.2.1",
  "#/algorithms/LedgerInputDescriptorMap.v0.2.2"),
R("/domains/management_record_inputs",
  "management-record-inputs/v0.2.1",
  "management-record-inputs/v0.2.2"),
R("/domains/management_ledger_record",
  "management-ledger-record/v0.2.1",
  "management-ledger-record/v0.2.2")
]
```

#### TransformSet `FIRST_HIT_LABEL_ENVELOPE_V0_2_1_TO_V0_2_2`

```text
[
R("/objects/FirstHitLabelEnvelope/field_set/$ref",
  "#/field_sets/FirstHitLabelEnvelope.v0.2.1",
  "#/field_sets/FirstHitLabelEnvelope.v0.2.2"),
R("/objects/FirstHitLabelEnvelope/properties/bindings/$ref",
  "#/schemas/LabelBindings.v0.2.1",
  "#/schemas/LabelBindings.v0.2.2"),
R("/objects/FirstHitLabelEnvelope/properties/pi_exit/$ref",
  "#/schemas/PiExitPolicy.v0.2.1",
  "#/schemas/PiExitPolicy.v0.2.2"),
R("/objects/FirstHitLabelEnvelope/properties/path_input/$ref",
  "#/schemas/PathInputBundle.v0.2.1",
  "#/schemas/PathInputBundle.v0.2.2"),
R("/algorithms/FirstHitLabelEnvelope.management_identity/$ref",
  "#/algorithms/ManagementIdentity.v0.2.1",
  "#/algorithms/ManagementIdentity.v0.2.2"),
R("/domains/label_record",
  "label-record/v0.2.1","label-record/v0.2.2")
]
```

这九个 TransformSet 是封闭集合。`C4C5ExogenousPathManifest.v0.2.2` 与本文件
其余 successor 使用直接 exact schema，不在 transform registry 中。不得使用
wildcard path、glob、regex、RENAME、MOVE、COPY，或新增未列出的 transform。

`TransformSet.v0.2.2` exact keys：

```text
schema_version,transform_set_id,
base_contract_sha256,base_ast_sha256,
operations,operations_sha256,
result_ast_sha256,transform_set_sha256
```

```text
schema_version =
  "rsi-mtf-drl-pm.schema-transform-set.v0.2.2"
operations_sha256 =
  ID("schema-transform-operation-set/v0.2.2",
     operations)
transform_set_sha256 =
  ID("schema-transform-set/v0.2.2",
     entire object excluding transform_set_sha256)
```

`SchemaTransformReceipt.v0.2.2` exact keys：

```text
schema_version,contract_id,
base_raw_sha256,base_canonical_sha256,delta_raw_sha256,
base_ast_sha256,
transform_set_sha256s,
applied_operation_sha256s,
result_ast_sha256,result_contract_sha256,
serializer_id,status,receipt_sha256
```

Exact rules：

```text
schema_version =
  "rsi-mtf-drl-pm.schema-transform-receipt.v0.2.2"
contract_id = "RSI_MTF_DRL_PM_CONTRACT.v0.2.2"
serializer_id =
  "RFC8785_CANONICAL_JSON_UTF8_SHA256_AST_PATCH_V1"
status = "PASS"
transform_set_sha256s =
  nine registry sets in the order printed above
applied_operation_sha256s =
  concatenation of each set.operations[*].operation_sha256
  in transform-set order and sequence order
result_contract_sha256 =
  SHA256(serialized immutable v0.2.2 contract bytes)
receipt_sha256 =
  ID("schema-transform-receipt/v0.2.2",
     entire object excluding receipt_sha256)
```

receipt 只有在每个 operation成功、九个 result AST 合并时没有 pointer collision、
result AST exact-schema validation通过、domain registry 58/58通过且最终 serializer
bytes复算一致时才可写 `PASS`。receipt 不回写被 hash 的 contract bytes。

### 12.10 `ImplementationManifest.v0.2.2` 与唯一 code identity

ledger/label 的 `code_sha256` 不接受任意 git SHA、目录 hash、wheel hash或调用方
传值。唯一 authority 是通过本节 receipt验证的 implementation manifest digest。

`ContractDigestReceipt.v0.2.2` exact keys：

```text
schema_version,contract_id,contract_relative_path,
contract_size_bytes,contract_sha256,serializer_id,
schema_transform_receipt_sha256,status,receipt_sha256
```

```text
schema_version =
  "rsi-mtf-drl-pm.contract-digest-receipt.v0.2.2"
contract_id = "RSI_MTF_DRL_PM_CONTRACT.v0.2.2"
serializer_id = "RFC8785_CANONICAL_JSON_UTF8_SHA256_AST_PATCH_V1"
status = "PASS"
receipt_sha256 =
  ID("contract-digest-receipt/v0.2.2",
     entire receipt excluding receipt_sha256)
```

`contract_relative_path` 必须唯一定位 P0-RSI-01C immutable JSON；receipt
verifier 逐 byte重算 size/hash，并要求
`contract_sha256=SchemaTransformReceipt.result_contract_sha256` 且 transform
receipt status=PASS。

`ImplementationFile.v0.2.2` exact keys：

```text
relative_path,role,size_bytes,sha256
```

Exact types：

```text
relative_path:string
role enum{SOURCE,TEST,SCHEMA,GENERATED_GOLDEN}
size_bytes:int>=0
sha256:Sha256
```

path 必须是 UTF-8 NFC、POSIX relative path；非空，不得以 `/` 开头，不得含
空 segment、`.`、`..`、反斜线、NUL 或 symlink。`sha256` 对该 path 的 exact
file bytes计算。

`ImplementationManifest.v0.2.2` exact keys：

```text
schema_version,manifest_kind,
contract_id,contract_sha256,composite_theory_id,
contract_digest_receipt_sha256,schema_transform_receipt_sha256,
runtime,source_roots,test_roots,entrypoints,
files,file_set_sha256,capabilities,
implementation_id,manifest_sha256
```

Exact literals与 nested keys：

```text
schema_version =
  "rsi-mtf-drl-pm.implementation-manifest.v0.2.2"
manifest_kind = "PURE_CONTRACT_IMPLEMENTATION"
contract_id = "RSI_MTF_DRL_PM_CONTRACT.v0.2.2"

runtime exact keys =
  language,requires_python,decimal_backend,canonical_json_backend
runtime = {
  language:"PYTHON",
  requires_python:">=3.11,<3.14",
  decimal_backend:"DECIMAL_CONTEXT_34_HALF_EVEN",
  canonical_json_backend:"RFC8785_UTF8"
}

source_roots =
  ["src/rsi_mtf_drl_pm_v0_2_2"]
test_roots =
  ["tests/rsi_mtf_drl_pm_v0_2_2"]

entrypoints exact keys =
  contract_serializer,bundle_validator,decision_calculator,
  reducer,ledger_encoder,labeler
entrypoints = {
  contract_serializer:
    "rsi_mtf_drl_pm_v0_2_2.contract:serialize_contract",
  bundle_validator:
    "rsi_mtf_drl_pm_v0_2_2.bundle:validate_bundle",
  decision_calculator:
    "rsi_mtf_drl_pm_v0_2_2.decision:calculate_decision",
  reducer:
    "rsi_mtf_drl_pm_v0_2_2.reducer:reduce_event_array",
  ledger_encoder:
    "rsi_mtf_drl_pm_v0_2_2.ledger:encode_ledger",
  labeler:
    "rsi_mtf_drl_pm_v0_2_2.label:first_hit_label"
}

capabilities exact keys =
  filesystem_write,network_io,database_io,wall_clock,
  nondeterministic_randomness,source_adapter,event_generator,
  timer_service,exchange_simulator,backtest,oms,live_trading
每个 capability = false
```

`files` 是 exact repository file set：必须列出两个 fixed roots 下每个 regular
file且只列这些文件；SOURCE/TEST 只允许 `.py`，SCHEMA只允许 `.json`，
GENERATED_GOLDEN只允许 `.json` 或 `.sha256`。manifest file与 receipt file位于
roots外，不进入自身 file set。array按
`(relative_path,role,sha256)` UTF-8 bytes严格升序且 path唯一。root缺失、
root内额外 regular file、root外 entrypoint、symlink或 role/suffix不匹配都拒绝。

```text
file_set_sha256 =
  ID("implementation-file-set/v0.2.2",
     files)

implementation_id =
  ID("implementation-identity/v0.2.2", {
    contract_sha256,composite_theory_id,
    runtime,entrypoints,file_set_sha256
  })

manifest_sha256 =
  ID("implementation-manifest/v0.2.2",
     entire manifest excluding manifest_sha256)
```

`contract_sha256` 必须等于 immutable contract-digest receipt 与
SchemaTransformReceipt 的 `result_contract_sha256`；
`composite_theory_id` 必须按 §0.1重算。两个 receipt SHA 必须唯一命中同一次
P0-RSI-01C 构建且 status=PASS。

`ImplementationManifestReceipt.v0.2.2` exact keys：

```text
schema_version,manifest_sha256,
observed_file_set_sha256,contract_sha256,
contract_digest_receipt_sha256,schema_transform_receipt_sha256,
entrypoint_resolution_sha256,capability_scan_sha256,
status,receipt_sha256
```

```text
schema_version =
  "rsi-mtf-drl-pm.implementation-manifest-receipt.v0.2.2"
status = "PASS"

entrypoint_resolution_sha256 =
  ID("implementation-entrypoint-resolution/v0.2.2", {
    runtime,entrypoints,
    resolved_relative_paths,
    resolved_symbol_ast_sha256s
  })

capability_scan_sha256 =
  ID("implementation-capability-scan/v0.2.2", {
    files,
    forbidden_imports,
    forbidden_calls,
    forbidden_native_extensions,
    observed_capabilities
  })

receipt_sha256 =
  ID("implementation-manifest-receipt/v0.2.2",
     entire receipt excluding receipt_sha256)
```

receipt verifier 必须重新枚举 fixed roots、逐 byte重算每个 file hash/size与
`observed_file_set_sha256`，在隔离 import中解析六个 exact entrypoints，并证明：

```text
observed_file_set_sha256 = manifest.file_set_sha256
forbidden_imports=[]
forbidden_calls=[]
forbidden_native_extensions=[]
observed_capabilities = manifest.capabilities
```

只有全部通过才可写 PASS。由此 ledger 与 label 的 equality 唯一为：

```text
ManagementLedgerBindings.code_sha256
  = LabelBindings.code_sha256
  = ImplementationManifest.manifest_sha256
```

且两处必须引用同一份 PASS ImplementationManifestReceipt。仅拥有相同 file hash
但 manifest/runtime/entrypoints/capabilities不同，或仅拥有相同 manifest payload
但实际文件集合不同，都不能成为 code authority。

---

## 13. Contract serialization acceptance

P0-RSI-01C 必须把本节作为 machine-checkable acceptance matrix。仅“字段存在”“hash 非空”或 positive fixture PASS 不足以冻结。

### 13.1 联合 P0 closure matrix

| ID | 原阻塞 | 本文件唯一 closure | 必须存在的 negative proof |
|---|---|---|---|
| C01 | undefined `event_class_rank` | §3.2 删除跨类全序，逐 schema accessor + homogeneous order | CoverageSeal/Account/Book 拼接排序必须拒绝 |
| C02 | source venue/lane/provenance 不闭合 | §1、§3.1、§9.1 scope 与 scoped artifact ID | venue-A book 放入 venue-B proof 必须拒绝 |
| C03 | CoverageSeal 仅 count/first/last | §4 exact covered IDs、set digest、generation integer closure | `{1,2,4}` 与 `{1,3,4}` 不得同为 complete |
| C04 | ClosedMarkBar 因果窗口错误 | §3.1 `bar_close<=closed<=available` | `closed_at_us>lane_available_at_us` 拒绝 |
| C05 | 多套 Book “latest”与 G0 跨 grid误去重 | §5.3 单一 SelectBook；§5.4 两阶段 grid/extreme；§12.7 `(rounded_price,grid_time_us)` dedup | 同价不同 grid必须保留；同 key才按 lane/sequence/event ID取首项 |
| C06 | venue rule ID/值语义与 event mapping歧义 | §5.1 structural range、baseline fingerprint、§5.3 selector、§10.3 mapping | later VALID不同 fingerprint必须可达；相同 rule新 ID不触发 change |
| C07 | account scope/latest/age 不闭合 | §5.2/§5.3 exact scope、两个 max-age literal、conflict | age 多 1us、同 effective不同 payload均不得成为 winner |
| C08 | EV observations与统计不可重算 | §7 inline rows、chronology、bindings、stats/hash | `n=30,min=max=0,sum=100` 必须拒绝 |
| C09 | HOLD/EXIT_NOW 只绑定一个证据 | §7.4、§9.3 sorted per-candidate binding array与 winner | 漏一个 candidate、单证据、互换 kind、不同 bucket或只 hash winner均拒绝 |
| C10 | target 把 UtcUs 当 StableId | §11.2 三个实际 BOOK wrapper IDs + grid times | time integer 写入 artifact ID array拒绝 |
| C11 | OI endpoint gap不可证 | §5.5 exact `(t-960s,t]` OI seal | 两 endpoint存在但 seal gap仍 UNKNOWN |
| C12 | SharedEntryAction authority 双重规范 | §8 validator全量重算、exact ENTRY input set、same-microsecond clock、fatal no-proof union | source漏/多一项、clock差1us、fatal带 proof或 calculator无 proof均拒绝 |
| C13 | candidate/policy hash 仅占位 | §2 exact objects、old pointer slices、domains、registry | 改任一 nested值但保留 hash拒绝 |
| C14 | U 结果不在 reducer enum | §6.1 独立 receipt，不扩 ReducerEventKind | U receipt 放 event_array拒绝 |
| C15 | Pi priority 与 §9.2不一致 | §10.1 full 34-kind mapping | 任一 enum缺失/重复或 STOP_ACK branch重叠拒绝 |
| C16 | submit root 与 descendant等时矛盾 | §10.2 root例外 + strict descendant | ACK/fill causal time等于 action拒绝 |
| C17 | generic artifact ID 不绑定 scope | §9.1 artifact_scope_id in identity | 同 payload跨 lane必须有不同 ID且不可消费 |
| C18 | DEVELOPMENT evidence 可泄漏 E0 | §1、§6.2、§7 role/availability literal | DEVELOPMENT role 即使 hash合法也拒绝 |
| C19 | source generation不可核对 | §3.1 generation fields均为 StableId、§4 ranges | 非 StableId generation或 range缺序号拒绝 |
| C20 | selector proof 没有 frozen IDs | §8 closure、§5 anchor/action selection | action account/venue artifact替换但保留result拒绝 |
| C21 | v0.2.1 domain 下改变字段 | §9.2/§12.8 domain closure、§12.9 finite AST ops、§12.10 manifest authority | old-node mismatch、未列 patch、文件漏/多、任一旧 schema/domain进入 bundle均拒绝 |

独立 reviewer 必须逐行给出：

```text
closure_status: PASS|REWORK
normative_evidence: section/paragraph
counterexample_checked: exact case
residual_ambiguity: NONE or precise blocker
```

任一 `REWORK` 或非 `NONE` residual ambiguity 都使本文件保持 `REJECT_FREEZE`。

### 13.2 Required schema/digest tests

contract validator 至少必须证明：

1. exact keys：每个 successor schema分别对 missing、extra、wrong-null、unknown enum 拒绝；
2. canonical JSON：object key insertion order不改变 digest，array order按 schema语义保留；
3. decimal：float、指数、`-0`、尾随零与越界拒绝；
4. domain separation：同 preimage 在两个 domain 得到不同 digest，旧 domain digest不得冒充；
5. binding chain：base hashes → composite → policy objects → bundle → candidate → seed/ledger/label 全链任一 byte mutation fail closed；
6. no self-reference：delta raw SHA 与 contract canonical SHA 只由外层 artifact 绑定，不写回被 hash 的自身对象；
7. duplicate semantics：exact duplicate幂等；same identity/different bytes conflict；
8. stage role：当前只接受 E0 synthetic literal；
9. old artifact reproducibility：旧 v0.2 与 v0.2.1 文件 byte/hash仍可原样验证，但不可作为 v0.2.2 object；
10. AST patch：每个 ADD/REMOVE/REPLACE 的 old/new node、pointer、sequence 与 digest 任一 mutation拒绝，九个 TransformSet operation数逐项固定；
11. implementation identity：fixed roots 漏/多文件、symlink、entrypoint漂移、capability=true/实测不符、receipt或 manifest byte mutation全部拒绝。

### 13.3 Required selector/coverage tests

至少覆盖：

- Book winner 的 max event time 与 min lane/sequence/ID 三层 tie；
- Pivot 先每秒 SelectBook，再 window extreme；
- Venue baseline exact fingerprint、later structurally VALID same/different fingerprint、range-invalid非 RULE_CHANGE；
- Account same effective/different payload；
- source scope、source_id、generation、availability_kind 的单字段 mutation；
- exact seal 0/1/2 matching artifacts；
- complete empty window、nonempty continuous range、hole、duplicate sequence、extra ID、missing ID；
- OI 两端各 60 秒 age 边界与 `(t-960s,t]` proof；
- `[a,b]` 到 `(a-1us,b]` 的端点转换与下溢拒绝。

### 13.4 Required EV/proof tests

至少覆盖：

- observation sort、duplicate identity、tail超界、current opportunity leakage；
- n/sum/min/max/class counts 任一 mutation；
- evidence policy digest、scope、role、bucket、issue/lane/expiry 任一 mutation；
- selector current_opportunity_id mutation、observation current-opportunity leakage与 selection-key重算；
- same issued time distinct evidence conflict；
- SUBMIT extension non-null、HOLD/EXIT extension null；
- 两个以上 target candidate 的 sorted binding array、winner、HOLD/EXIT artifact ID/hash/selection-key；漏一 candidate、pair缺一、kind互换、不同 policy/extension；
- DecisionInputBinding missing/extra/future/cross-scope artifact；
- anchor/action account max-age不是 `1_000_000`、ENTRY_SUBMIT exact set漏/多 artifact；
- ENTRY result与 SharedEntryAction price/qty/levels/risk 任一 byte差异；
- ENTRY/CONTROL clock任一处相差 1us；CONTROL_ABSTAIN proof与四类 fatal-event no-proof 两条互斥路径；
- C5 自造 decision proof而非复用 C4 必须拒绝。

### 13.5 Required reducer/identity tests

至少覆盖：

- 34 event kinds各命中一个 rank；STOP_ACK rank 5/10 predicate互补；
- event-array tie `(time,rank,sequence,id)` 与 predecessor-ready 重算一致；
- ENTRY_SUBMIT 是 root且 time=action；
- direct/transitive descendant严格 `>action`，economic non-null也严格大于；
- rule fingerprint same/new ID no change；
- pre-submit rule change ABSTAIN、post-submit rank-1 DATA_HEALTH_INVALID；
- G0 同 rounded price不同 grid保留、同 `(price,grid)` exact dedup；
- BARRIER 多 candidate evidence array、winner与 full target input hash；
- target candidate three book artifact IDs、window winner ID 与 `_us` keys；
- artifact scope identity、bundle root closure、wrong-scope diagnostic唯一例外；
- 全部 20 个 ArtifactSchemaId descriptor time/quality mapping逐项 positive/negative；
- full sealed bundle replay产生 byte-identical ledger head/label。

### 13.6 非市场结论

通过本节只证明：

```text
theory is mechanically single-valued at E0
```

不证明：

```text
data exists
data is fit
signal predicts returns
cost assumptions are realistic
execution is feasible
strategy can trade
```

这些结论必须由后续相互独立的阶段证据获得，不能写入 P0-RSI-01C PASS。

---

## 14. 动态研究与开发路线

### 14.1 当前阶段：P0-RSI-01C

产物：

- `config/rsi_mtf_drl_pm.research_contract.v0_2_2.json`；
- contract schema validator；
- §13 的最小 negative contract tests；
- implementation manifest schema，但不写策略实现。

PASS：

- 本文件独立审查 PASS；
- 四层理论 hash 与 composite binding 可重算；
- 所有 exact schema/domain/selector/coverage/policy 机械序列化；
- contract canonical digest稳定；
- 无 data、backtest、execution 权限扩张。

REJECT：

- 任一默认值、自由 policy string、未定义 selector、digest cycle；
- 修改 v0.2.1；
- 为了让 fixture通过而放宽 exact rule；
- 把 schema test描述成市场验证。

### 14.2 P0-RSI-02：pure implementation

只有新的阶段决定才能启动。允许的完整模块：

- pure source/schema validators；
- pure feature、U、entry/risk/EV calculators；
- exact selector/coverage validators；
- CanonicalSyntheticEventBundle validator；
- 只消费 sealed event_array 的 management reducer；
- ledger encoder与 labeler。

禁止 IO/network/reader/adapter/timer service/exchange simulator/backtest。Terra 实现必须绑定 v0.2.2 full contract digest；同 bundle 得到 byte-identical output。

问题路由：

- code 不符合 contract：Terra 只修实现；
- contract 出现两种合法解释：立即停止，交 Sol 发布新 semantic delta；
- 测试 expected 与 contract冲突：不得只改 expected。

### 14.3 P0-RSI-03：synthetic system gate

完整 synthetic fixtures 必须覆盖 §13、v0.2.1 原有 reducer/state×event/ledger/label acceptance，并增加：

- scope isolation；
- exact coverage/collision；
- venue/account selector conflict；
- U receipt；
- EV observation recomputation与 dual evidence；
- decision proof closure；
- priority 34-kind exhaustiveness；
- submission descendant；
- target/OI identity。

阶段完成时由 Sol 审查事实结果。PASS 只升级为 `E0_SYNTHETIC_VALIDATED`，不升级市场证据。

### 14.4 P0-RSI-04：data feasibility 与 DEVELOPMENT

该阶段不会自动开放。先决产物必须是新的 Sol authorization artifact 与独立 source→canonical adapter contract，至少冻结：

- source vendor/exchange、symbol、venue、clock与许可；
- bar/book/trade/OI/account/venue rule schema mapping；
- raw immutable manifest、checksum、timezone、sequence/generation；
- actual/reconstructed availability；
- gap、late、conflict、maintenance 与 delisting policy；
- DEVELOPMENT chronology、pre-access seen registry 与 label tail；
- adapter code digest、canonical bundle digest与可重复 environment；
- 成本/成交模拟 assumptions 与证据等级。

第一项市场问题不是“收益多少”，而是：

```text
这些字段、频率、sequence、as-of 与 completeness proof 是否真实可获得？
```

只有数据可用性/完整性 PASS，才可在未见 DEVELOPMENT 上运行 frozen baseline。任何缺 1 秒 book、OI endpoint、source sequence 或 as-of clock 的事实失败，只能走 data-layer delta、censor或停止；不得通过 forward-fill、删窗口或改 selector救策略。

### 14.5 Predictive validity 路线

在另行授权后，顺序固定：

1. DEVELOPMENT：frozen baseline + 一次一层 challenger；只产生候选假设；
2. CALIBRATION：只验证预先声明的候选，不回选新参数；
3. one-shot HOLDOUT：一次性、不可重用；
4. execution-realism contract：只有预测与成本后结果通过才设计；
5. paper safety gate；
6. 只有 paper 风险、运行、回滚、监控与资金上限全部通过，才可能申请有限 live 阶段。

每一步都必须独立保存：

```text
theory_digest,contract_digest,code_digest,adapter_digest,
data_manifest_digest,candidate_id,seen_roles,
test_or_evaluation_result,next_authorized_stage
```

失败后的唯一路由：

| 事实失败层 | 返回层 | 禁止动作 |
|---|---|---|
| theory/contract ambiguity | Sol theory delta | implementation 默认 |
| implementation mismatch | Terra implementation | 修改理论救代码 |
| synthetic test暴露规范矛盾 | Sol theory delta | 只改 expected |
| source availability/gap fail | data contract或 STOP | 改信号/forward-fill |
| DEVELOPMENT predictive fail | 预注册的一层 challenger或 STOP | 多参数搜索 |
| CALIBRATION/HOLDOUT fail | candidate STOP | 重用或回选 holdout |
| execution realism fail | execution model/risk delta | 用理想 fill 替代 |
| paper safety fail | safety/operations delta | 直接 live |

### 14.6 可持续优化的含义

本系统允许持续改善的是“经过版本化证据推动的离线研究路线”，不是运行时策略自改：

- policy、parameter、data adapter、execution model 每次变化都产生新 digest；
- active contract 下禁止在线学习、热更新阈值或 outcome-driven action；
- 新版本必须与旧版本并存可复验；
- stage failure 只回到归因层，不跨层调参；
- 市场 evidence 与 engineering evidence 分账；
- 所有资金或不可逆权限始终需要新的显式阶段授权。

这就是 v0.2.2 的理论完成边界：先把 E0 变成单值、可证伪、可重放的研究系统，再询问市场事实；绝不把“能运行”提前等同于“能交易”。
