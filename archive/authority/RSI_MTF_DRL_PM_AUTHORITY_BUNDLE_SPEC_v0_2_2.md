# RSI-MTF-DRL-PM Authority Bundle Specification v0.2.2

> 状态：`ROUTE_B_SPEC / E0 / CONTRACT_DRAFTING_ONLY`
>
> 目的：以最小的 outcome-free JSON contract、纯 Python reference kernel、
> golden synthetic evidence 与外部 review receipt，形成 v0.2.2 的唯一可执行
> authority；本文件不授权数据、回测、paper、OMS 或交易。

## 0. 决定与边界

本规格实施 Route B。以下 frozen inputs 保持只读：

```text
CORE_TRADING_THEORY.md
  raw_sha256 = 06014b2f9e2665abef55e816616661951b35cb766ab9a49aadfad6841d7f822d
  size_bytes = 110738

config/rsi_mtf_drl_pm.research_contract.v0_2.json
  raw_sha256 = 33d84ce8fdfa7766fbce340beac9916344655c002e39ed6c8db29cefaaa6b047
  size_bytes = 23206
  canonical_sha256 =
    38d572453045016bbdc314d184f9be87a608ec8bc36aabaf92d8c0ce742201e5
  canonical_size_bytes = 20204

RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md
  raw_sha256 = 021053480fe9a49b3902803e2d363793416a120263551fb741fb3444af6550fd
  size_bytes = 197800

RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md
  raw_sha256 = 43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6
  size_bytes = 136468

RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md
  raw_sha256 = 4971a337605b7d3bbfdae3657a47498c2cfeb2d055f0e861339c57e02968aa48
  size_bytes = 82244

artifacts/rsi_mtf_drl_pm_direct_ast_v0_2_2/
  slice_a_sources_selectors.report.md
  raw_sha256 = c239afc048dc26a641b150495eba0a57c8e12e4129adbfe045710e5ed61fdfdc
  size_bytes = 19166
```

Terra 的穷举报告证明，Direct AST 在 Slice A 已连续遇到 decimal runtime、
union narrowing、selector status、ConstRef predicate、computed/scalar order、
Sha256 lexical validity 与 algorithm interface authority 缺口。当前不存在完整
Direct AST、global closure 或 DirectASTReviewReceipt。因此 Profile、checker、
tests 与 partial fragments只保留为历史设计证据，不进入新 contract、kernel、
manifest、golden expected value或最终 release authority。

禁止继续增加通用 expression language、opcode、per-node AST、AST interpreter、
JSON Schema interpreter、code generator或 plugin system。finite interface table和
state/event table只是本策略的有限数据，不是新的通用语言。

### 0.1 Semantic preservation and route-only supersession

Route B 不改变交易理论，只替换已被反例证明不可完成的构造与代码身份路线。
除下表明确列出的 route-only 条款外，
`RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md` 继续优先于本规格：

| semantic source范围 | Route B状态 | 唯一解释 |
|---|---|---|
| §0.1 四层 source lineage 与 `composite_theory_id` 构造 | `RETAINED_EXACT` | 四个 frozen digest、domain、preimage field names 与计算结果不得改变 |
| §0.1 contract container ID/path、P0-RSI-01C builder/output shape | `SUPERSEDED_ROUTE_ONLY` | 原 `rsi-mtf-drl-pm-v0-2-2-outcome-free-contract`、`config/rsi_mtf_drl_pm.research_contract.v0_2_2.json` 与 full-schema/AST serialization target，由本规格 §2 的 Strategy Contract container、path 与 B1 output替代；这不改变 composite theory、wire object或策略 identity |
| §0.2 覆盖规则 | `RETAINED_EXACT` | 未被本表逐项列出的 semantic conflict仍须 `SPEC_CONFLICT` |
| §0.3 权限交集、数据/市场/交易禁令 | `RETAINED_EXACT` | `ALLOW ∩ DENY = DENY` 与全部 forbidden capability不变 |
| §0.3 named current step | `STAGE_MAPPED_ROUTE_ONLY` | `P0-RSI-01C` 的名称和旧产物形态映射到 B1；B2/B3仍须分别过新 gate |
| §1–§11.4，除下一行列出的 §8.2 `selector_bindings` proof shape | `RETAINED_EXACT_SEMANTICS` | parameter、policy、wire schema、formula、status、selector economic rule、identity domain、state/event、risk与chronology均不得改变 |
| §8.2 `DecisionInputBinding.selector_bindings` proof shape | `SUPERSEDED_ROUTE_ONLY_C05_PROOF_OBSERVABILITY` | 在既有三个字段后增加本规格 §2.3.1A 的 `g0_selection_binding`；只使 retained S4/G0 候选集可由 public `decision_calculator` 机械观察和反证，不改变 grid、Book selector、price rounding、candidate、rank、winner、entry/abstain或 risk经济语义 |
| §12.1 lines 2498–2534、2547–2563 与 §12.1A–§12.5 | `RETAINED_EXACT_SEMANTICS` | ledger/label field set、binding equality、descriptor、policy与identity semantics不变；`code_sha256` field保留 |
| §12.1 lines 2535–2545 legacy receipt sequence/runtime reads | `SUPERSEDED_ROUTE_ONLY` | 不生成 ContractDigestReceipt、SchemaTransformReceipt或旧 ImplementationManifestReceipt；contract raw/canonical digest由本规格 §2、§6外部重算，pure runtime按 §4.2从 revalidated bundle byte-copy bindings，最终由 Route B external receipt证明，不读取 receipt或 filesystem |
| §12.6 lines 2793–2807 PathInputBundle schema/semantics | `RETAINED_EXACT_SEMANTICS` | exact fields、types、domains与path behavior不变 |
| §12.6 lines 2808–2811 TransformSet/result-AST derivation | `SUPERSEDED_ROUTE_ONLY` | 不生成或消费 TransformSet/result AST；B2直接 hard-code retained source semantics，B3以 exact synthetic positive/negative replay验证 |
| §12.7 与 §12.8 lines 2883–2956 | `RETAINED_EXACT_SEMANTICS` | successor identity preimages及58行 old→new domain mapping不变 |
| §12.8 lines 2957–2963 builder/domain scan obligation | `SUPERSEDED_ROUTE_ONLY` | 不由 contract builder扫描；改由 §6 external authority reviewer执行 exact 58-row immutable-source/code-domain audit并写入 `identity_domain_audit` |
| §13.1 C01–C20 | `RETAINED_CLOSURE` | 本规格 §4只做可执行 trace，不降低任何 positive/negative proof |
| §13.1 C21 | `ROUTE_ADAPTED_CLOSURE` | 保留旧 object/domain拒绝与 exact file-set closure；只把 AST patch proof替换为 source→spec→decision→contract lineage proof，并把 replay内只读 checker的三字段 PASS carrier与两次 replay后的 external receipt generator严格分离 |
| §13.2 items 1–9、11 与 §13.3–§13.6 | `RETAINED_ACCEPTANCE` | schema/digest、selector、coverage、EV、proof、reducer、identity与非市场结论保持 |
| §12.9 | `SUPERSEDED_ROUTE_ONLY` | ContractAST、NodeId、PatchOp、TransformSet、SchemaTransformReceipt与 AST serializer不进入 successor authority |
| §12.10 | `SUPERSEDED_ROUTE_ONLY` | 旧 source roots、file roles、implementation manifest/receipt shape及 `code_sha256=old manifest_sha256` equality由本规格 §3、§4.2、§6的无环 code identity替代；六个 public entrypoint职责和 ledger/label `code_sha256` field保留 |
| §13.2 item 10 | `SUPERSEDED_ROUTE_ONLY` | AST mutation proof由 Route Decision、finite interface registry、lineage、domain与 file-set mutation proof替代 |
| §14.1–§14.3 | `STAGE_MAPPED` | `P0-RSI-01C/02/03` 分别映射为 `B1/B2/B3`；旧 route artifact path和 AST产物不再要求 |
| §14.4–§14.6 | `RETAINED_NOT_AUTHORIZED` | 映射为 B4及其后阶段，但当前权限仍为 forbidden |

Route B中以下旧 artifacts/actions明确不存在，不是待实现 placeholder：

```text
config/rsi_mtf_drl_pm.research_contract.v0_2_2.json
ContractDigestReceipt.v0.2.2
SchemaTransformReceipt.v0.2.2
ImplementationManifestReceipt.v0.2.2
ContractAST.v0.2.2
TransformSet.v0.2.2
result AST
runtime receipt read
contract-builder domain scan
```

其替代关系唯一为：

```text
old contract/digest receipt
  -> Strategy Contract + Route B manifest/external receipt
old schema transform receipt/result AST
  -> pinned source semantics + exact Python bytes + C01-C21 replay
old implementation receipt/code equality
  -> kernel_code_sha256 + Route B external receipt
old runtime receipt read
  -> explicit revalidated contract/bundle binding propagation
old builder domain scan
  -> external receipt.identity_domain_audit
```

因此，只有表中逐项列出的新 path、contract container identity、serialization
shape、manifest/code identity shape或 Python layout属于 route delta；它们不是
strategy semantic delta。任何未列在表中的差异都属于 `SCOPE_BREACH`，必须
停止并交 Sol。

## 1. 唯一 authority graph

authority只能沿以下方向：

Route B Decision的唯一 path：

```text
config/rsi_mtf_drl_pm.route_b_decision.v0_2_2.json
```

```text
immutable v0.2/v0.2.1 source lineage
  -> immutable v0.2.2 semantic source raw SHA
  -> this Authority Bundle Spec raw SHA
  -> Route B Decision raw SHA
  -> immutable outcome-free Strategy Contract raw + canonical SHA
  -> exact Python source/test/golden file set
  -> Authority Bundle Manifest raw + manifest SHA
  -> external Authority Bundle Review Receipt raw + receipt SHA
  -> RSI_MTF_DRL_PM_FINAL_THEORY_v0_2_2.md raw SHA
  -> separately authorized source adapter/data manifest
  -> DEVELOPMENT, CALIBRATION, one-shot HOLDOUT
```

禁止反向绑定和自证：

- semantic source、旧 v0.2 contract、Profile 与本规格不得被回写；
- contract不携带未来 manifest、receipt或 final theory hash；
- manifest不得包含自身 raw SHA；`manifest_sha256` 只对排除该字段的 canonical
  object计算；
- receipt位于 manifest file set之外，并重新读取和哈希全部输入；
- final theory只能 pin已经 PASS 的 exact bundle，不得修改其任何 byte；
- golden expected value不是 contract输入，也不能反向决定 parameter、policy、
  formula、chronology或 risk invariant。

## 2. Strategy Contract

唯一 planned path：

```text
config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json
```

文件必须按 semantic source §1.2 的 UTF-8 CanonicalJSON规则序列化，无 BOM、
无空白、无 trailing newline、无 JSON float。integer限制在 JavaScript
safe-integer范围；所有 decimal使用 semantic source定义的 canonical decimal
STRING。由于本规格冻结的 B1 contract literals、paths与 IDs 全是 ASCII，该
contract 的 actual bytes还必须是 ASCII-only；这是 B1 container的额外物理
不变量，不得限制 kernel、wire object、golden、ledger或label的 retained UTF-8
string domain。

### 2.1 Exact top-level schema

top-level exact keys：

```text
schema_version
contract_id
composite_theory_id
status
evidence_level
source_authority
route_decision_raw_sha256
scope
authorization
runtime
canonicalization
chronology
semantic_commitment
support_type_registry
algorithm_interface_registry
public_entrypoint_registry
closure_case_registry
synthetic_gate
```

Exact literals：

```text
schema_version = "rsi-mtf-drl-pm.strategy-contract.v0.2.2"
contract_id = "RSI_MTF_DRL_PM_STRATEGY_CONTRACT.v0.2.2"
composite_theory_id = "3e7ecf5e257d8a2dbf5cc826c1da1240283a2379de710e4be90f7bcfdb8118ea"
status = "IMMUTABLE_CONTRACT_REVIEW_BYTES"
evidence_level = "E0"
scope = "OUTCOME_FREE_SYNTHETIC_AUTHORITY_ONLY"
```

`source_authority` exact keys：

```text
core_theory_path
core_theory_size_bytes
core_theory_raw_sha256
legacy_v0_2_contract_path
legacy_v0_2_contract_size_bytes
legacy_v0_2_contract_raw_sha256
legacy_v0_2_contract_canonical_size_bytes
legacy_v0_2_contract_canonical_sha256
v0_2_1_addendum_path
v0_2_1_addendum_size_bytes
v0_2_1_addendum_raw_sha256
semantic_source_path
semantic_source_size_bytes
semantic_source_raw_sha256
authority_bundle_spec_path
authority_bundle_spec_size_bytes
authority_bundle_spec_raw_sha256
```

所有值必须逐 byte匹配 Route B Decision。`route_decision_raw_sha256` 必须匹配
decision file exact bytes。`composite_theory_id` 必须按 retained semantic source
§0.1 从四个 frozen digest重算，并逐字等于上述 literal。新 Route B container
使用新 identity；不得覆盖或伪装成旧
`rsi-mtf-drl-pm-v0-2-outcome-free-contract`，也不得继续使用已被本规格
route-only supersede的
`rsi-mtf-drl-pm-v0-2-2-outcome-free-contract`。

`authorization` exact keys及唯一值：

```text
synthetic_reference_kernel = "ALLOWED_AFTER_B1_PASS"
synthetic_golden_tests = "ALLOWED_AFTER_B1_PASS"
market_data = "FORBIDDEN"
historical_data = "FORBIDDEN"
source_adapter = "FORBIDDEN"
backtest = "FORBIDDEN"
calibration = "FORBIDDEN"
holdout = "FORBIDDEN"
paper = "FORBIDDEN"
oms = "FORBIDDEN"
live_trading = "FORBIDDEN"
```

`runtime` exact value：

```text
language = "PYTHON"
requires_python = ">=3.11,<3.14"
dependencies = []
decimal_backend = "DECIMAL_CONTEXT_34_HALF_EVEN"
canonical_json_backend = "PINNED_UTF8_CODEPOINT_CANONICAL_JSON"
```

`canonicalization` 是 exact object，keys 与唯一值为：

```text
json_encoding = "UTF-8"
object_key_order = "UNICODE_CODE_POINT_ASCENDING"
whitespace = "NONE"
trailing_newline = false
string_policy = "UTF8_JSON_STRING_NO_NORMALIZATION"
integer_policy = "SAFE_INTEGER_ONLY"
float_policy = "FORBIDDEN"
decimal_policy = "CANONICAL_DECIMAL_STRING_CONTEXT_34_HALF_EVEN"
digest_algorithm = "SHA-256"
identity_rule = "SHA256_UTF8_DOMAIN_NUL_CANONICAL_JSON"
array_order_policy = "SCHEMA_DECLARED_NO_IMPLICIT_SORT"
```

这些值固定以下行为：

- exact JSON object keys、UTF-8 strings、safe integers、禁止 float；
- decimal precision 34、`ROUND_HALF_EVEN`、禁止 rounded parse；
- `ID(domain,x)=SHA256(UTF8(domain)||0x00||CanonicalJSON(x))`；
- Sha256/StableId恰为 64 lowercase hex；
- arrays保留 contract或 schema规定的顺序，不做隐式 sort；
- fixed string只来自本规格 exact literals或 pinned semantic source；runtime不执行
  prose。

### 2.2 Chronology

当前 contract的 active data role只能是 `SYNTHETIC`。`chronology` 必须显式包含：

```text
active_role
synthetic_availability
development
calibration
holdout
pre_access_seen_registry_policy
same_timestamp_rule
```

其中 `development`、`calibration`、`holdout` 各自只有
`authorization,window` 两个 exact keys；值为：

```text
active_role = "SYNTHETIC"
synthetic_availability = "SYNTHETIC"
development.authorization = "FORBIDDEN_UNTIL_B4"
calibration.authorization = "FORBIDDEN_UNTIL_POST_DEVELOPMENT_GATE"
holdout.authorization = "FORBIDDEN_UNTIL_POST_CALIBRATION_FREEZE"
development.window = null
calibration.window = null
holdout.window = null
pre_access_seen_registry_policy = "REJECT_ANY_SEEN_ROLE_REUSE"
same_timestamp_rule = "STOP_FIRST"
```

null在这里是明确的“未授权、未选择”，不是 placeholder。B1不得读取日期、市场
outcome或 seen registry来填写窗口。B4只能由新的 Sol authorization创建新版本
contract或独立 chronology artifact；不得回写 B1 bytes。

### 2.3 Finite interface authorities

Route B 不再复制 semantic source 的全部 schema、formula、policy、status、
identity、state-machine或 risk objects，也不从 contract解释它们。否则会重新
形成第二套 schema language。`semantic_commitment` 是 exact object：

```text
strategy_semantics = "PINNED_SOURCE_AUTHORITY_ONLY"
parameter_override = "FORBIDDEN"
policy_override = "FORBIDDEN"
schema_override = "FORBIDDEN"
formula_override = "FORBIDDEN"
status_override = "FORBIDDEN"
selector_override = "FORBIDDEN"
identity_override = "FORBIDDEN"
state_machine_override = "FORBIDDEN"
risk_override = "FORBIDDEN"
runtime_text_dispatch = "FORBIDDEN"
```

这些语义由完整 source lineage、§0.1 retention table与最终 exact Python bytes
共同实现；contract若出现任何被禁止的 override、expression、opcode、formula
body、schema language或 executable string，必须拒绝。B2只能 hard-code pinned
semantics；不得遍历 contract来解释行为。

以下三个 interface registry与 §4.1 `closure_case_registry` 都是有限 metadata，
均为 JSON array、member ID唯一、按 ID UTF-8 bytes严格升序，且必须逐字等于
对应表格。runtime不能新增 member。

#### 2.3.1 Route B transient support types

`support_type_registry` member exact keys为
`type_id,ordered_fields,invariants`。`ordered_fields` 是 ordered
`{name,type_id}` array；`invariants` 是 ordered ASCII string array。exact
inventory。表中 `*(empty)*` 必须序列化为 `ordered_fields=[]`：

| type_id | ordered_fields | invariants |
|---|---|---|
| `AggTradeArtifactTupleV0_2_2` | `artifacts:Tuple[AggTradeArtifactV0_2_2]` | `["AGG_TRADE_WRAPPERS_ONLY","PRESERVE_ARTIFACT_ORDER","PRESERVE_ARTIFACT_ID"]` |
| `ArtifactCatalogV0_2_2` | `artifacts:Tuple[ArtifactWrapperV0_2_2]` | `["ARTIFACT_CATALOG_COMPLETE","ARTIFACT_ID_STRICT_ASC","NO_PARALLEL_ID_PAYLOAD"]` |
| `ArtifactWrapperV0_2_2` | `artifact_id:StableId,artifact_scope_id:StableIdOrNull,schema_id:ArtifactSchemaIdV0_2_2,available_at_us:UtcUsOrNull,payload_sha256:Sha256,payload:ExactPayloadBySchemaId` | `["SEMANTIC_ARTIFACT_WRAPPER_9_1_9_2"]` |
| `AuthorityLineageFileSetCheckResultV0_2_2` | `schema_version:LiteralRsiMtfDrlPmAuthorityLineageFileSetCheckV0_2_2,status:LiteralPASS,closure_id:LiteralC21` | `["C21_MINIMAL_ACYCLIC_PASS","NO_MANIFEST_GOLDEN_RECEIPT_DIGEST_OR_PROJECTION","NO_PARTIAL_SUCCESS"]` |
| `BundleValidationFailureV0_2_2` | `status:LiteralINVALID,error_code:KernelErrorCodeV0_2_2` | `["FAIL_CLOSED_TERMINAL","BUNDLE_ERROR_SUBSET_ONLY","NO_DEFAULT_ACTION","NO_PARTIAL_SUCCESS","NO_FREE_MESSAGE"]` |
| `BundleValidationOutcomeV0_2_2` | *(empty)* | `["EXACT_UNION_VALIDATED_BUNDLE_OR_BUNDLE_VALIDATION_FAILURE","NO_OTHER_VARIANT"]` |
| `CoverageSealBindingV0_2_2` | `coverage_seal_artifact_id:StableId,coverage_seal_sha256:Sha256,venue_id:NonEmptyString,instrument_id:NonEmptyString,lane_id:NonEmptyString,availability_kind:AvailabilityKind,source_id:NonEmptyString,source_schema_version:SourceSchemaVersion,covered_object_kind:OrderedMarketSourceKind,window_start_exclusive_us:UtcUs,window_end_inclusive_us:UtcUs,lane_available_at_us:UtcUs` | `["COVERAGE_BINDING_QUERY_THEN_ID_DIGEST"]` |
| `KernelErrorCodeV0_2_2` | *(empty)* | `["E_KERNEL_CONTRACT_INVALID","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID","E_C01_MIXED_SOURCE_KIND","E_C02_SCOPE_MISMATCH","E_C03_COVERAGE_SET_INVALID","E_C04_BAR_CAUSALITY_INVALID","E_C05_BOOK_GRID_DEDUP_INVALID","E_C06_VENUE_RULE_MAPPING_INVALID","E_C07_ACCOUNT_ASOF_CONFLICT","E_C08_EV_STATS_INCONSISTENT","E_C09_TARGET_EVIDENCE_INCOMPLETE","E_C10_TARGET_ARTIFACT_ID_INVALID","E_C11_OI_SEAL_INCOMPLETE","E_C12_DECISION_PROOF_INVALID","E_C13_POLICY_DIGEST_MISMATCH","E_C14_U_RECEIPT_EVENT_FORBIDDEN","E_C15_PRIORITY_TABLE_INVALID","E_C16_DESCENDANT_CAUSALITY_INVALID","E_C17_ARTIFACT_SCOPE_MISMATCH","E_C18_ROLE_NOT_SYNTHETIC","E_C19_GENERATION_CLOSURE_INVALID","E_C20_SELECTOR_BINDING_MISMATCH","E_C21_AUTHORITY_LINEAGE_INVALID"]` |
| `MarketSourceArtifactTupleV0_2_2` | `artifacts:Tuple[ClosedMarkBarArtifactV0_2_2|BookSnapshotArtifactV0_2_2|AggTradeArtifactV0_2_2|OpenInterestArtifactV0_2_2]` | `["SOURCE_WRAPPERS_ONLY","PRESERVE_ARTIFACT_ORDER","PRESERVE_ARTIFACT_ID"]` |
| `OIEndpointSelectionV0_2_2` | `coverage_seal_artifact:CoverageSealArtifactV0_2_2,oi_now_artifact:OpenInterestArtifactV0_2_2,oi_prev_artifact:OpenInterestArtifactV0_2_2` | `["OI_WINDOW_960S_ENDPOINTS_IN_SEAL_SAME_SCOPE"]` |
| `ValidatedBundleV0_2_2` | `status:LiteralVALID,bundle:CanonicalSyntheticEventBundleV0_2_2,bundle_sha256:StableId,validated_as_of_us:UtcUs,role:SyntheticRole` | `["STATUS_EXACT_VALID","BUNDLE_SHA256_EQUALS_BUNDLE_FIELD","ROLE_EXACT_SYNTHETIC","VALIDATED_AS_OF_EQUALS_VALIDATOR_ARGUMENT","REVALIDATE_BEFORE_REDUCER_OR_LABEL"]` |

这些是非 wire、非持久化的 Python boundary types。所有 selector成功 variant必须
返回完整 ArtifactWrapper；failure variant只能是下表的 exact status literal。
不得返回裸 payload、null、exception或 aligned parallel arrays。malformed input
是 deterministic rejection，不得伪装成 selector status。

#### 2.3.1A C05 decision-proof observability overlay

本小节只 route-only supersede semantic source §8.2
`DecisionInputBinding.selector_bindings` 的 proof shape。策略的 grid、Book
selector、rounding、candidate identity、rank、winner、decision result及 risk
语义保持不变，因而这是 `C05_PROOF_OBSERVABILITY_ONLY`，
`STRATEGY_ECONOMIC_SEMANTICS_UNCHANGED`。

`selector_bindings` 的 exact ordered fields由原三项：

```text
anchor_account_max_age_us
action_account_max_age_us
submit_ev_selection_key_sha256
```

扩为：

```text
anchor_account_max_age_us
action_account_max_age_us
submit_ev_selection_key_sha256
g0_selection_binding
```

第四项类型恰为 `G0SelectionBindingV0_2_2|null`。non-null object的 exact
ordered fields为：

| field | type |
|---|---|
| `grid_times_us` | `array<UtcUs>` |
| `selected_book_artifact_ids` | `array<StableId>` |
| `coverage_seal_artifact_id` | `StableId` |
| `coverage_seal_sha256` | `Sha256` |
| `ranked_candidate_ids` | `array<StableId>` |
| `winner_candidate_id` | `StableId|null` |
| `binding_sha256` | `Sha256` |

```text
binding_sha256 =
  ID("g0-selection-binding/v0.2.2",
     entire object excluding binding_sha256)
```

outer `source_artifact_set_sha256` 与 `proof_sha256` 继续因包含完整
`selector_bindings` 而绑定该 object。其余 exact closure规则为：

1. `grid_times_us` 必须逐字等于 retained S4冻结公式的结果，并严格升序、唯一；
2. `selected_book_artifact_ids` 与 `grid_times_us` 等长且按 grid位置逐项对应；
   同一个 Book artifact ID允许在不同 grid重复，每项必须是该 grid调用
   `SelectBook(g,1_000_000)` 的唯一 winner；
3. seal必须是 proof closure内唯一的 exact `complete=true`
   `BOOK_SNAPSHOT` CoverageSeal，且本 object引用的全部 artifact ID都必须进入
   `DecisionInputBinding.source_artifact_ids`；
4. `ranked_candidate_ids` 必须是完整 unique array：先按
   `(rounded_price,grid_time_us)` 分组，组内按 retained
   lane/sequence/event-ID tie-break取 winner，再按 retained global G0 rank排序；
   相同 price但不同 grid必须形成两个不同 candidate ID，不得合并；
5. `winner_candidate_id` 等于 `ranked_candidate_ids` 首项；空数组时必须为
   `null`；
6. ENTRY 时 `g0_selection_binding` 必须 non-null，ranked array非空，
   winner non-null，且 `initial_levels.g0` 逐字等于 winner的 rounded price；
7. ABSTAIN 只有在 S4已完成有限 exact grid selection时才允许 non-null；若该
   complete selection无候选，则 `ranked_candidate_ids=[]` 且
   `winner_candidate_id=null`；S4未完成或在 S4之前停止时必须为 null。

C05 public negative必须使用合法 ENTRY：从两枚 same-price/different-grid
candidate中删除一枚，重算 nested `binding_sha256`、outer proof与全部 wrapper
digest，同时保持 artifacts、`initial_levels.g0` 与 decision result不变。
`decision_calculator` 必须首先抛出
`KernelValidationError("E_C05_BOOK_GRID_DEDUP_INVALID")`。private helper-only
断言不构成 C05 closure evidence。

`G0SelectionBindingV0_2_2` 是 retained wire proof的 route overlay，不是新的
transient Python boundary carrier，因此不得加入
`support_type_registry`；该 registry仍恰为11项。

#### 2.3.2 Exact 13-algorithm interface registry

`algorithm_interface_registry` member exact keys为
`algorithm_id,parameters,returns,status_semantics,owner_entrypoint_id,
authority_ref`。`parameters` 是 ordered array，元素 exact keys为
`name,type_id`；不是 object map。`authority_ref` 是非空 ordered array，
元素为 ASCII `relative_path:Lstart-Lend`。12 个 helper均为 B2 private pure functions；
`ValidateDecimal` 同样不进入 package exports。

| algorithm_id | ordered parameters | returns | status_semantics | owner_entrypoint_id | authority_ref |
|---|---|---|---|---|---|
| `algorithm/OrderedSourceProjection.v0.2.2` | `source_object:MarketSourceObjectV0_2_2` | `OrderedSourceProjectionV0_2_2` | `NO_STATUS` | `bundle_validator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L604-L639"]` |
| `algorithm/SelectAccountSnapshot.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,account_query:AccountQueryV0_2_2,tau_us:UtcUs,max_age_us:NonNegativeUtcDelta` | `AccountRiskSnapshotArtifactV0_2_2|UNKNOWN|ACCOUNT_SNAPSHOT_CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L954-L981"]` |
| `algorithm/SelectAggTradeWindow.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,start_exclusive_us:UtcUs,end_inclusive_us:UtcUs,decision_at_us:UtcUs,seal_binding:CoverageSealBindingV0_2_2` | `AggTradeArtifactTupleV0_2_2|UNKNOWN|COVERAGE_CONFLICT` | `SUCCESS_WRAPPERS_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L987-L989"]` |
| `algorithm/SelectBook.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,tau_us:UtcUs,max_age_us:NonNegativeUtcDelta` | `BookSnapshotArtifactV0_2_2|UNKNOWN|CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L894-L914"]` |
| `algorithm/SelectBookGrid.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,grid_time_us:UtcUs` | `BookSnapshotArtifactV0_2_2|UNKNOWN|CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS_MAX_AGE_US_1000000` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L991-L1010"]` |
| `algorithm/SelectClosedMarkBarSlot.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,period_seconds:PeriodSeconds900Or14400,bar_open_at_us:UtcUs,tau_us:UtcUs` | `ClosedMarkBarArtifactV0_2_2|UNKNOWN|CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L983-L985"]` |
| `algorithm/SelectCoverageSeal.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,binding:CoverageSealBindingV0_2_2` | `CoverageSealArtifactV0_2_2|UNKNOWN|COVERAGE_CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `bundle_validator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L746-L765"]` |
| `algorithm/SelectOpenInterest.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,tau_us:UtcUs,max_age_us:NonNegativeUtcDelta` | `OpenInterestArtifactV0_2_2|UNKNOWN|CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L916-L925"]` |
| `algorithm/SelectVenueSnapshot.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,scope:Scope4V0_2_2,tau_us:UtcUs` | `VenueInstrumentSnapshotArtifactV0_2_2|UNKNOWN|RULE_SNAPSHOT_CONFLICT` | `SUCCESS_WRAPPER_OR_EXACT_STATUS` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L926-L952"]` |
| `algorithm/SourceCollision.v0.2.2` | `source_artifacts:MarketSourceArtifactTupleV0_2_2` | `Boolean` | `TRUE_COLLISION_PRESENT_FALSE_COLLISION_FREE` | `bundle_validator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L641-L648"]` |
| `algorithm/ValidateCoverageSeal.v0.2.2` | `source_artifacts:MarketSourceArtifactTupleV0_2_2,seal_artifact:CoverageSealArtifactV0_2_2,binding:CoverageSealBindingV0_2_2` | `Boolean` | `TRUE_ALL_COVERAGE_RULES_PASS_FALSE_OTHERWISE` | `bundle_validator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L654-L744"]` |
| `algorithm/ValidateDecimal.v0.2.2` | `kind:DecimalKindV0_2_2,value:String` | `Boolean` | `TRUE_EXACT_DECIMAL_KIND_RULES_PASS_FALSE_OTHERWISE` | `bundle_validator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md:L47-L60","RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L102-L102"]` |
| `algorithm/ValidateOICompleteness.v0.2.2` | `artifacts:ArtifactCatalogV0_2_2,query:SourceQueryV0_2_2,t_us:UtcUs,seal_binding:CoverageSealBindingV0_2_2` | `OIEndpointSelectionV0_2_2|UNKNOWN` | `ENDPOINT_GAP_SEQUENCE_SEAL_OR_SCOPE_FAILURE_MAPS_UNKNOWN` | `decision_calculator` | `["RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md:L1012-L1033"]` |

`authority_ref` 是审查定位，不是 executable text。`status_semantics` 必须逐字
保存 table内容；尤其 `SourceCollision=true` 表示 collision-present，
`ValidateCoverageSeal=true` 表示 valid。不得增加 selector return variant。

#### 2.3.3 Exact six public entrypoints

`public_entrypoint_registry` member exact keys为
`entrypoint_id,python_symbol,parameters,returns,failure_mode,failure_code_order,
purity`。`parameters` 与 algorithm registry使用相同 ordered `{name,type_id}`
items；`failure_code_order` 是 exact ordered enum array；`purity` 全部为
`PURE_STDLIB_NO_IO`。

| entrypoint_id | python_symbol | ordered parameters | returns | failure_mode | failure_code_order |
|---|---|---|---|---|---|
| `bundle_validator` | `trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:validate_bundle` | `contract:StrategyContractV0_2_2,bundle:CanonicalSyntheticEventBundleV0_2_2,as_of_us:UtcUs,role:SyntheticRole` | `BundleValidationOutcomeV0_2_2` | `RETURN_BUNDLE_VALIDATION_FAILURE` | `["E_KERNEL_CONTRACT_INVALID","E_C01_MIXED_SOURCE_KIND","E_C02_SCOPE_MISMATCH","E_C03_COVERAGE_SET_INVALID","E_C04_BAR_CAUSALITY_INVALID","E_C08_EV_STATS_INCONSISTENT","E_C09_TARGET_EVIDENCE_INCOMPLETE","E_C10_TARGET_ARTIFACT_ID_INVALID","E_C13_POLICY_DIGEST_MISMATCH","E_C14_U_RECEIPT_EVENT_FORBIDDEN","E_C17_ARTIFACT_SCOPE_MISMATCH","E_C18_ROLE_NOT_SYNTHETIC","E_C19_GENERATION_CLOSURE_INVALID","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID"]` |
| `contract_serializer` | `trade_system.rsi_mtf_drl_pm_v0_2_2.contract:serialize_contract` | `contract:StrategyContractV0_2_2` | `CanonicalContractBytesV0_2_2` | `RAISE_CONTRACT_VALIDATION_ERROR` | `["E_KERNEL_CONTRACT_INVALID"]` |
| `decision_calculator` | `trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:calculate_decision` | `contract:StrategyContractV0_2_2,binding:DecisionInputBindingV0_2_2,artifacts:ArtifactCatalogV0_2_2,as_of_us:UtcUs,role:SyntheticRole` | `DecisionResultV0_2_2` | `RAISE_KERNEL_VALIDATION_ERROR` | `["E_KERNEL_CONTRACT_INVALID","E_C05_BOOK_GRID_DEDUP_INVALID","E_C06_VENUE_RULE_MAPPING_INVALID","E_C07_ACCOUNT_ASOF_CONFLICT","E_C11_OI_SEAL_INCOMPLETE","E_C12_DECISION_PROOF_INVALID","E_C20_SELECTOR_BINDING_MISMATCH","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID"]` |
| `labeler` | `trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:first_hit_label` | `contract:StrategyContractV0_2_2,validated_bundle:ValidatedBundleV0_2_2,reducer_trace:ManagementLedgerRecordTupleV0_2_2,as_of_us:UtcUs,role:SyntheticRole` | `FirstHitLabelEnvelopeV0_2_2` | `RAISE_KERNEL_VALIDATION_ERROR` | `["E_KERNEL_CONTRACT_INVALID","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID"]` |
| `ledger_encoder` | `trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:encode_ledger` | `contract:StrategyContractV0_2_2,ledger_record:ManagementLedgerRecordV0_2_2,as_of_us:UtcUs,role:SyntheticRole` | `CanonicalManagementLedgerRecordBytesV0_2_2` | `RAISE_KERNEL_VALIDATION_ERROR` | `["E_KERNEL_CONTRACT_INVALID","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID"]` |
| `reducer` | `trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:reduce_event_array` | `contract:StrategyContractV0_2_2,validated_bundle:ValidatedBundleV0_2_2,as_of_us:UtcUs,role:SyntheticRole` | `ManagementLedgerRecordTupleV0_2_2` | `RAISE_KERNEL_VALIDATION_ERROR` | `["E_KERNEL_CONTRACT_INVALID","E_C15_PRIORITY_TABLE_INVALID","E_C16_DESCENDANT_CAUSALITY_INVALID","E_KERNEL_ARGUMENT_INVALID","E_KERNEL_SCHEMA_INVALID","E_KERNEL_DIGEST_INVALID","E_KERNEL_BINDING_INVALID"]` |

`validate_bundle` 的 success variant必须是完整
`ValidatedBundleV0_2_2`，且它是该 type的唯一 producer；failure variant必须是
`BundleValidationFailureV0_2_2`。`BundleValidationOutcomeV0_2_2` 恰为这两个
variant的 closed union。reducer与labeler收到 success carrier后，必须用相同
`contract`、`validated_as_of_us` 与 `role` 对 embedded bundle重新执行同一纯
validation并逐字段比较 carrier；不得信任调用方自行构造的 nominal object。

failure code只能来自 `KernelErrorCodeV0_2_2`。bundle validator只允许五个
`E_KERNEL_*` generic codes及 C01、C02、C03、C04、C08、C09、C10、C13、C14、
C17、C18、C19 exact closure codes。contract bytes/object不匹配先返回
`E_KERNEL_CONTRACT_INVALID`。其余输入先做足以安全识别 violation
predicate的 structural parse；若 violation命中 §4.1 的 bundle-validator
closure，必须返回其 exact `E_Cxx_*`，多项同时命中时按 C01、C02、C03、C04、
C08、C09、C10、C13、C14、C17、C18、C19 顺序 fail first。只有无法归入这些
closure的 residual failure，才按 argument、exact-schema、digest、binding顺序
返回 `E_KERNEL_ARGUMENT_INVALID`、`E_KERNEL_SCHEMA_INVALID`、
`E_KERNEL_DIGEST_INVALID`、`E_KERNEL_BINDING_INVALID`。因而例如 valid
DEVELOPMENT role固定返回 C18，nested
policy byte mutation但保留旧 digest固定返回 C13，不得先降级成 generic code。
failure不得携带 default action、partial success、自由 message、stack或环境
信息。

其余 failure-capable entrypoint不得返回自由 error object或让 harness补码：

- `decision_calculator` 命中 closure时按
  C05→C06→C07→C11→C12→C20 fail first；
- `reducer` 按 C15→C16 fail first；
- `authority_lineage_checker` 唯一 closure failure为 C21；
- `labeler`、`ledger_encoder` 及上述 entrypoint的 residual validation failure
  按 contract→argument→schema→digest→binding顺序使用五个 `E_KERNEL_*`；
- `contract_serializer` 与 `validate_contract_bytes` 的任何 failure均使用
  `ContractValidationError("E_KERNEL_CONTRACT_INVALID")`。

`decision_calculator`、`reducer`、`labeler`、`ledger_encoder` 与
`authority_lineage_checker` 必须实际抛出 §3 的
`KernelValidationError`；B3 replay
harness只能从 caught exception的 `.error_code`生成 canonical actual error
object。semantic `UNKNOWN/ABSTAIN/CENSORED/HALT` 是正常 success return，绝不
转换为 exception。

B1 validator必须证明每个 `failure_code_order` member都属于
`KernelErrorCodeV0_2_2`，每个 C01–C20 code恰好出现在其 §4.1 executor对应的
array且不出现在其他 public executor，C21只属于
`authority_lineage_checker`。漏码、跨 executor重复、数组 reorder或 generic
priority漂移都拒绝。

`synthetic_gate` exact keys：

```text
required_closure_ids
required_positive_case_ids
required_negative_case_ids
repeat_process_runs
required_result
maximum_claim
```

其中 `required_closure_ids=["C01",...,"C21"]`；`repeat_process_runs=2`；
`required_result="E0_SYNTHETIC_VALIDATED"`；
`maximum_claim="MECHANICALLY_SINGLE_VALUED_AT_E0"`。

## 3. Reference Python package

planned source root：

```text
trade_system/rsi_mtf_drl_pm_v0_2_2/
```

职责边界：

| file | phase | sole responsibility |
|---|---|---|
| `__init__.py` | B1 | 只导出已冻结 public symbols；无 import side effect |
| `contract.py` | B1 | canonical bytes、exact contract validator、finite interface registries与source-authority检查 |
| `model.py` | B2 | frozen value objects、decimal、Sha256/StableId、canonical schema与identity validation |
| `kernel.py` | B2 | source/coverage/selectors、U/EV/decision、canonical bundle、reducer、ledger与label纯函数 |
| `authority.py` | B3 | 只读 C21 lineage/file-set checker与单进程 golden replay driver；不生成 external receipt、不启动子进程、不属于 strategy kernel |

不按 307 个旧 NodeId创建文件，不拆分成 plugin、provider、visitor、compiler或
generated code。只有当 `kernel.py` 已产生真实独立高风险边界时，才允许 Sol
批准一次面向 reducer/ledger 的局部拆分。

kernel public functions只接受 immutable typed values和显式 `as_of_us/role`；
不得读取 filesystem、network、database、environment、wall clock、random、
global mutable state或活动 G1。不得捕获 validation error后返回默认交易动作。

`authority.py` 可以只读 contract、manifest、golden、exact file set及 decision
中列明的 CORE/v0.2/v0.2.1/v0.2.2 frozen source paths；它不得读取其他
project data，也不得成为 decision、reducer或label调用依赖。它不得构造完整
receipt、不得调用自身 replay driver、不得导入或调用 subprocess/process
creation。两次 fresh-process启动与最终 audits/receipt construction只属于
bundle外的 independent external verifier。所有 kernel source只使用 Python
standard library。

B1 `__init__.py` 的 exact source为：

```python
from .contract import serialize_contract

__all__ = ("serialize_contract",)
```

B1不得导入尚不存在的 `kernel.py`，也不得 export validator、helper、exception、
version、dynamic proxy或其他 symbol。`contract.py` 必须定义以下 exact B1
review surface：

```text
ContractValidationError(ValueError)
serialize_contract(contract:Mapping[str,JSONValue]) -> bytes
validate_contract_bytes(contract_bytes:bytes,workspace_root:pathlib.Path) -> None
```

`serialize_contract` 是 no-IO exact-schema validator加 canonical serializer；
`validate_contract_bytes` 另做 physical byte、actual source hash/size与 decision
binding检查，只允许 filesystem read，失败统一抛
`ContractValidationError`，且 exact
`error_code="E_KERNEL_CONTRACT_INVALID"`、`args=("E_KERNEL_CONTRACT_INVALID",)`；
禁止附加自由 message、path或环境内容。contract tests从 module直接导入这三个
symbol。
B2完成时才可按新的阶段调度加入其余五个 package public symbols。

B2 `model.py` 必须定义且不得 package-export：

```text
KernelValidationError(ValueError)
```

其 constructor只接受 `KernelErrorCodeV0_2_2` member，exact
`.error_code=member`、`.args=(member,)`，无其他 instance field、自由 message、
stack payload或 fallback code。`kernel.py` 与 `authority.py` 必须导入并复用
同一个 class；禁止各自定义不同 exception或让 test harness按 exception text
猜测 error code。

## 4. C01–C21 closure trace

每一行都必须在 contract `closure_case_registry` 中存在，并在 golden suite有
至少一个 positive与一个 mutation/negative case。PASS只表示机械单值。

| ID | contract freeze | kernel proof | required negative |
|---|---|---|---|
| C01 | homogeneous source kinds与order keys | kind-specific projection/order | 不同 source kind concat/sort拒绝 |
| C02 | Scope4、source、venue、lane fields | exact scope equality | venue-A object进入 venue-B proof拒绝 |
| C03 | coverage IDs、generation ranges、set digest | exact set与整数连续性 | hole、duplicate、extra、missing ID拒绝 |
| C04 | bar time fields | `bar_close<=closed<=available` | closed晚于available拒绝 |
| C05 | single Book selector、grid/extreme tie与§2.3.1A public proof binding | two-stage grid selection及完整 ranked candidate重算 | 同价不同grid误去重或 proof删一枚拒绝 |
| C06 | venue rule fields/fingerprint/status | structural validity与rule-change mapping | invalid range伪装RULE_CHANGE拒绝 |
| C07 | account scope/age/conflict | exact as-of selector | age +1us、同effective异payload拒绝 |
| C08 | EV rows/stats/bindings | recompute n/sum/min/max/classes | self-inconsistent stats拒绝 |
| C09 | per-target HOLD/EXIT evidence bindings | full candidate set与winner | 漏项、互换kind、只hash winner拒绝 |
| C10 | target artifact-ID fields | actual wrapper IDs与grid times分离 | UtcUs写入artifact ID拒绝 |
| C11 | OI endpoints与exact seal window | two endpoints plus coverage | endpoint存在但seal gap仍UNKNOWN |
| C12 | decision input/action exact fields | full recomputation与fatal union | source漏项、clock +1us、fatal带proof拒绝 |
| C13 | parameter/policy registry与domains | full digest chain | nested mutation保留旧hash拒绝 |
| C14 | U receipt独立schema | reducer event enum exclusion | U receipt进入event array拒绝 |
| C15 | 34-kind priority table | exhaustive rank与STOP_ACK complement | kind缺失、重复、predicate重叠拒绝 |
| C16 | submission root/descendant clocks | strict causal descendant | ACK/fill time等于action拒绝 |
| C17 | artifact scope identity | scope included in ID | same payload跨lane同ID拒绝 |
| C18 | active role SYNTHETIC only | role admission before calculation | DEVELOPMENT evidence在B1–B3拒绝 |
| C19 | generation StableId/ranges | exact generation closure | bad StableId或sequence gap拒绝 |
| C20 | frozen selector artifact IDs | recompute anchor/action bindings | 替换venue/account artifact保留result拒绝 |
| C21 | lineage、domain、exact file set | read-only lineage/file-set check plus external receipt recomputation | 旧object冒充v0.2.2、file漏/多拒绝 |

### 4.1 Exact closure case authority

每个 closure 的 mandatory anchor case与错误码由下表冻结。contract
`closure_case_registry` 必须逐行保存
`closure_id,case_executor_id,positive_case_id,negative_case_id,
negative_error_code`，不得增删、改名或换码：

| closure_id | case_executor_id | positive_case_id | negative_case_id | negative_error_code |
|---|---|---|---|---|
| C01 | `bundle_validator` | `C01-P-HOMOGENEOUS-ORDER` | `C01-N-MIXED-KIND-ORDER` | `E_C01_MIXED_SOURCE_KIND` |
| C02 | `bundle_validator` | `C02-P-SCOPE-ISOLATED` | `C02-N-CROSS-SCOPE` | `E_C02_SCOPE_MISMATCH` |
| C03 | `bundle_validator` | `C03-P-COVERAGE-CONTIGUOUS` | `C03-N-COVERAGE-SET` | `E_C03_COVERAGE_SET_INVALID` |
| C04 | `bundle_validator` | `C04-P-BAR-CAUSAL` | `C04-N-BAR-LATE-CLOSE` | `E_C04_BAR_CAUSALITY_INVALID` |
| C05 | `decision_calculator` | `C05-P-BOOK-TWO-STAGE` | `C05-N-BOOK-GRID-DEDUP` | `E_C05_BOOK_GRID_DEDUP_INVALID` |
| C06 | `decision_calculator` | `C06-P-VENUE-RULE-MAPPING` | `C06-N-VENUE-RULE-MAPPING` | `E_C06_VENUE_RULE_MAPPING_INVALID` |
| C07 | `decision_calculator` | `C07-P-ACCOUNT-ASOF` | `C07-N-ACCOUNT-CONFLICT` | `E_C07_ACCOUNT_ASOF_CONFLICT` |
| C08 | `bundle_validator` | `C08-P-EV-RECOMPUTED` | `C08-N-EV-STATS` | `E_C08_EV_STATS_INCONSISTENT` |
| C09 | `bundle_validator` | `C09-P-TARGET-EVIDENCE-FULL` | `C09-N-TARGET-EVIDENCE-MISSING` | `E_C09_TARGET_EVIDENCE_INCOMPLETE` |
| C10 | `bundle_validator` | `C10-P-TARGET-ARTIFACT-BOUND` | `C10-N-TIME-AS-ARTIFACT-ID` | `E_C10_TARGET_ARTIFACT_ID_INVALID` |
| C11 | `decision_calculator` | `C11-P-OI-SEAL-ENDPOINTS` | `C11-N-OI-SEAL-GAP` | `E_C11_OI_SEAL_INCOMPLETE` |
| C12 | `decision_calculator` | `C12-P-DECISION-PROOF-TOTAL` | `C12-N-DECISION-PROOF` | `E_C12_DECISION_PROOF_INVALID` |
| C13 | `bundle_validator` | `C13-P-POLICY-DIGEST-CHAIN` | `C13-N-POLICY-DIGEST` | `E_C13_POLICY_DIGEST_MISMATCH` |
| C14 | `bundle_validator` | `C14-P-U-RECEIPT-SEPARATE` | `C14-N-U-AS-REDUCER-EVENT` | `E_C14_U_RECEIPT_EVENT_FORBIDDEN` |
| C15 | `reducer` | `C15-P-PRIORITY-34-TOTAL` | `C15-N-PRIORITY-TABLE` | `E_C15_PRIORITY_TABLE_INVALID` |
| C16 | `reducer` | `C16-P-DESCENDANT-CAUSAL` | `C16-N-DESCENDANT-EQUAL-TIME` | `E_C16_DESCENDANT_CAUSALITY_INVALID` |
| C17 | `bundle_validator` | `C17-P-ARTIFACT-SCOPE-ID` | `C17-N-ARTIFACT-CROSS-SCOPE` | `E_C17_ARTIFACT_SCOPE_MISMATCH` |
| C18 | `bundle_validator` | `C18-P-SYNTHETIC-ROLE` | `C18-N-DEVELOPMENT-ROLE` | `E_C18_ROLE_NOT_SYNTHETIC` |
| C19 | `bundle_validator` | `C19-P-GENERATION-CLOSED` | `C19-N-GENERATION-GAP` | `E_C19_GENERATION_CLOSURE_INVALID` |
| C20 | `decision_calculator` | `C20-P-SELECTOR-BINDING` | `C20-N-SELECTOR-SUBSTITUTION` | `E_C20_SELECTOR_BINDING_MISMATCH` |
| C21 | `authority_lineage_checker` | `C21-P-AUTHORITY-FILE-SET` | `C21-N-AUTHORITY-LINEAGE` | `E_C21_AUTHORITY_LINEAGE_INVALID` |

`case_executor_id` 必须引用 §2.3.3 public entrypoint；唯一例外
`authority_lineage_checker` 固定解析到
`trade_system.rsi_mtf_drl_pm_v0_2_2.authority:check_authority_lineage_and_file_set`，
只负责 C21 的 read-only lineage/domain/exact-file-set validation，不得被
kernel调用。

C09 的 retained proof object位于 canonical bundle的
`BARRIER_EVALUATION` event context，必须同时读取 event identity、time、
`input_artifact_ids`、ledger state/side与 per-target evidence binding；这些
字段不属于 `decision_calculator` 的 public input。故本 route refreeze只把
C09 closure owner从 `decision_calculator` 移至 `bundle_validator`，不改变
任何 C09 predicate。C09 negative的唯一 public carrier因此是
`BundleValidationFailureV0_2_2{status:"INVALID",
error_code:"E_C09_TARGET_EVIDENCE_INCOMPLETE"}`，不得由 private helper断言、
`KernelValidationError` 或非法 artifact payload代替。

该 review-only symbol的 exact signature/failure surface为：

```text
check_authority_lineage_and_file_set(
  workspace_root:pathlib.Path,
  manifest_relative_path:RelativePath
) -> AuthorityLineageFileSetCheckResultV0_2_2

failure = KernelValidationError("E_C21_AUTHORITY_LINEAGE_INVALID")
```

success必须逐字段恰为以下最小 value：

```text
{
  "schema_version":
    "rsi-mtf-drl-pm.authority-lineage-file-set-check.v0.2.2",
  "status":"PASS",
  "closure_id":"C21"
}
```

这三个 fields都是固定 literal，不携带 manifest SHA、golden SHA、file-set
SHA、replay digest、receipt field或 receipt status的任何值或 projection；
因此 C21 positive golden
`expected_output` 是上述固定 value，而不是 future receipt。checker在返回它
之前必须只读重算 frozen source→spec→decision→contract lineage、manifest
digest、§6 exact 12-file set及 hashes、parent/import closure、58-row
identity-domain closure和 C21 capability exclusions。任何失败均抛出 exact
`KernelValidationError("E_C21_AUTHORITY_LINEAGE_INVALID")`；不得返回 partial
receipt、自由 error或其他 exception carrier。C21 negative case的 actual code
必须来自该 exact caught exception。

该 checker不得构造 `AuthorityBundleReviewReceipt`，不得调用 golden replay
driver，不得启动或等待任何进程，也不得读取 receipt。它与同文件的 replay
CLI只能共享无副作用的 canonical/hash/read-only validation helpers，调用边
固定为 `replay driver -> checker`，反向调用为 forbidden。完整 receipt只能由
bundle外的 independent external verifier在 checker所属 replay已由两个 fresh
process各执行一次并产生 byte-identical PASS stdout之后构造。

`required_positive_case_ids` 与 `required_negative_case_ids` 分别是上表对应列按
`closure_id` 顺序形成的 exact 21-item arrays。golden authority必须恰好包含
这 42 个 case，不得由实现新增或删减 authority case；额外 exploratory unit
test可以存在，但不进入 closure digest或 PASS计数。每个 positive/negative
case必须覆盖 §4 同行的完整 proof/counterexample；例如 C15 positive input必须
一次携带全部 34 kind rank与全部 reachable transition，而非任选一个样例。

### 4.2 Acyclic kernel code identity

semantic source 的 `ManagementLedgerBindings.code_sha256` 与
`LabelBindings.code_sha256` field set保持不变；只把 §12.10 旧的
`code_sha256=ImplementationManifest.manifest_sha256` equality route-only
替换为：

```text
kernel_files = exact sorted file descriptors independently computed for:
  trade_system/__init__.py                                  KERNEL_SOURCE
  trade_system/rsi_mtf_drl_pm_v0_2_2/__init__.py            KERNEL_SOURCE
  trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py            CONTRACT_VALIDATOR
  trade_system/rsi_mtf_drl_pm_v0_2_2/kernel.py              KERNEL_SOURCE
  trade_system/rsi_mtf_drl_pm_v0_2_2/model.py               KERNEL_SOURCE

kernel_file_set_sha256 =
  ID("rsi-mtf-drl-pm-kernel-file-set/v0.2.2", kernel_files)

kernel_runtime = contract.runtime

kernel_entrypoints = {
  bundle_validator:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:validate_bundle",
  contract_serializer:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.contract:serialize_contract",
  decision_calculator:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:calculate_decision",
  labeler:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:first_hit_label",
  ledger_encoder:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:encode_ledger",
  reducer:
    "trade_system.rsi_mtf_drl_pm_v0_2_2.kernel:reduce_event_array"
}

kernel_code_sha256 =
  ID("rsi-mtf-drl-pm-kernel-code/v0.2.2", {
    contract_canonical_sha256,
    runtime:kernel_runtime,
    entrypoints:kernel_entrypoints,
    kernel_file_set_sha256
  })

ManagementLedgerBindings.code_sha256
  = LabelBindings.code_sha256
  = kernel_code_sha256
```

`kernel_files` member是从上述 exact paths的当前 bytes独立构造的
`relative_path,role,size_bytes,sha256` exact object，按 §6 相同规则排序；此时
manifest尚不存在。B3创建 manifest后，其 `files` 对上述五条 path的 exact
projection必须逐字等于这个既有 `kernel_files` array。
`kernel_runtime` 必须逐字等于已验证 contract的 exact `runtime` object。
`kernel_entrypoints` 是从已验证 `contract.public_entrypoint_registry` 按
`entrypoint_id -> python_symbol` 作出的唯一 projection，keys与values必须逐字
等于上述 object；不得使用完整 registry array、未来 manifest object、import后
function repr或 caller提供 map。B3 manifest的 `runtime` 与 `entrypoints` 必须
分别逐字等于这两个既有值。

`authority.py`、tests、golden、manifest与receipt不进入 kernel code preimage。
B2 kernel bytes冻结后，B3 external fixture builder先计算
`kernel_code_sha256`，再把该值写入每个 code-bearing synthetic input bundle的
`ledger_bindings.code_sha256`，并生成 golden expected values。pure runtime的
唯一传播规则是：

1. `validate_bundle` 重算 contract digest与 bundle内全部 binding equality；
   对 `code_sha256` 只验证 Sha256 lexical validity和 bundle内部一致性，不得
   声称它已经等于 actual code；
2. success carrier保留 byte-identical embedded bundle，不得新增或覆盖 code；
3. reducer把
   `validated_bundle.bundle.ledger_bindings.code_sha256` byte-copy到每个
   `ManagementLedgerBindings.code_sha256`；
4. labeler要求 reducer trace所有 code值与 validated bundle相等，再将同一 bytes
   copy到 `LabelBindings.code_sha256`；
5. ledger encoder只验证并序列化 record，不得替换 code binding；
6. external reviewer最后从 exact kernel files重算 actual digest，并同时核验
   golden input bundles、actual ledger records与actual labels。

kernel不得读取自身文件、manifest或receipt，不得硬编码自身摘要，不得增加
`code_sha256` caller参数或接受下游 override。没有 external PASS receipt时，
一个内部一致但任意的 64-hex binding只能产生 non-authoritative synthetic
output，不能自称 code authority。

B3 golden的 C21 expected value只能是 §4.1 三字段 constant PASS carrier；B3
manifest随后绑定 golden与完整 file set。C21 checker可以在 replay中读取并
验证这个已构造 manifest，但不得把 manifest/golden-derived value写回 golden，
也不得生成 receipt。external verifier最后启动两次 fresh replay、复算两层
digest并构造 receipt。因此依赖方向唯一为：

```text
contract -> kernel files -> kernel_code_sha256
         -> golden input bundle + constant C21 expected PASS
         -> actual ledger/label
         -> full file_set + manifest
         -> replay -> C21 read-only checker -> minimal C21 actual PASS
         -> two external fresh-process observations
         -> external receipt
```

禁止把 `manifest_sha256`、`implementation_id`、golden digest、receipt digest
或未来 final theory digest写入 ledger/label `code_sha256`。runtime
ledger/label不嵌 receipt；external PASS receipt通过
`observed_kernel_code_sha256` 对同一 code authority作外部证明。
尤其禁止出现
`golden[C21 expected receipt] -> manifest -> receipt -> replay[C21]` 的环。

## 5. Golden synthetic evidence

planned path：

```text
tests/fixtures/rsi_mtf_drl_pm_v0_2_2.golden.json
```

文件必须是 synthetic-only canonical JSON；禁止复制市场、历史、G1、January、
February、March、账户或 outcome-derived parameter。top-level exact keys：

```text
schema_version
suite_id
contract_canonical_sha256
kernel_code_sha256
positive_cases
negative_cases
```

每个 positive case exact keys：

```text
case_id
closure_id
case_executor_id
input
expected_output
```

每个 negative case exact keys：

```text
case_id
closure_id
case_executor_id
base_case_id
mutation
expected_error_code
```

`kernel_code_sha256` 必须按 §4.2 从已冻结 B2 kernel bytes重算；所有
expected ledger/label的 `code_sha256` 必须逐字等于该值。case arrays按
`case_id`严格升序，ID唯一。`mutation` exact keys为
`operation,path,value`；operation只允许 `ADD/REMOVE/REPLACE/REORDER`，仅由
test harness应用，绝不进入 runtime kernel。

唯一 C21 positive case
`C21-P-AUTHORITY-FILE-SET.expected_output` 必须逐字等于 §4.1 的三字段
`AuthorityLineageFileSetCheckResultV0_2_2` constant；不得保存
`AuthorityBundleReviewReceiptV0_2_2`、manifest/file/golden digest、replay
result或其 projection。`C21-N-AUTHORITY-LINEAGE` 必须让同一个 checker实际
读取 mutation后指向的非 v0.2.2/不合法 manifest observation并抛出 C21 exact
exception；harness不得伪造 error code。file missing/extra/symlink与
identity-domain/capability counterexamples由 authority tests作 in-memory
manifest/file-catalog mutation并调用同一 checker的纯 comparison helpers；
最终 external verifier还必须对 actual workspace重新执行真实 exact-set
检查。

minimum families：

- exact keys、enum、null、decimal、Sha256、StableId；
- scalar与computed numeric strict order；
- duplicate/collision/coverage/generation；
- selector 0/1/2、tie与专属 status；
- policy/identity/binding digest mutation；
- 34 event priorities与每个 reachable state transition；
- submit/ACK/fill/protection/reconcile/rule-change；
- target/pivot/path/funding、same-timestamp STOP_FIRST；
- byte-identical bundle replay、ledger head与label；
- role/availability/future clock、scope与artifact substitution。
- bundle-return与non-bundle exception actual error carrier，以及每个 executor
  multi-violation fail-first；
- code-bearing base input→actual ledger→actual label byte-copy与 external
  kernel digest equality；
- 58-row old/new identity-domain audit、record hash domain与 dynamic-domain
  construction rejection。

golden expected mismatch不得由 Terra单独修改 expected来“修复”；若 semantic
source与 contract允许两种解释，停止并回 Sol。

## 6. Authority Bundle Manifest and Review Receipt

planned manifest：

```text
artifacts/rsi_mtf_drl_pm_authority_bundle_v0_2_2.json
```

exact keys：

```text
schema_version
manifest_kind
contract_id
core_theory_raw_sha256
legacy_v0_2_contract_raw_sha256
legacy_v0_2_contract_canonical_sha256
v0_2_1_addendum_raw_sha256
semantic_source_raw_sha256
authority_bundle_spec_raw_sha256
route_decision_raw_sha256
contract_raw_sha256
contract_canonical_sha256
runtime
entrypoints
c21_check_entrypoint
files
file_set_sha256
kernel_file_set_sha256
kernel_code_sha256
golden_suite_sha256
closure_trace_sha256
kernel_capabilities
implementation_id
manifest_sha256
```

`files`逐项 exact keys为 `relative_path,role,size_bytes,sha256`，按
`(relative_path,role,sha256)` UTF-8 bytes严格升序，path唯一、relative、
无 symlink。role只允许：

```text
CONTRACT
CONTRACT_VALIDATOR
KERNEL_SOURCE
TEST
GOLDEN_SYNTHETIC
REVIEW_TOOL
```

At B3，`files` 必须恰好是以下 12 个 path/role，不多不少：

| relative_path | role |
|---|---|
| `config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json` | `CONTRACT` |
| `tests/__init__.py` | `TEST` |
| `tests/fixtures/rsi_mtf_drl_pm_v0_2_2.golden.json` | `GOLDEN_SYNTHETIC` |
| `tests/test_rsi_mtf_drl_pm_v0_2_2_authority.py` | `TEST` |
| `tests/test_rsi_mtf_drl_pm_v0_2_2_contract.py` | `TEST` |
| `tests/test_rsi_mtf_drl_pm_v0_2_2_kernel.py` | `TEST` |
| `trade_system/__init__.py` | `KERNEL_SOURCE` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/__init__.py` | `KERNEL_SOURCE` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/authority.py` | `REVIEW_TOOL` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py` | `CONTRACT_VALIDATOR` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/kernel.py` | `KERNEL_SOURCE` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/model.py` | `KERNEL_SOURCE` |

new package root `trade_system/rsi_mtf_drl_pm_v0_2_2/` 递归不得出现其他
regular file或 symlink；review与test process必须以
`-B` 禁止产生 bytecode。命名的 test/fixture/contract paths不得通过 helper
path扩展 authority。对以上全部 Python source做 AST import closure：

- relative import必须解析到上述五个 package files之一；
- `trade_system.*` absolute import只允许该 exact package；
- test只可导入 Python standard library与该 exact package；
- dynamic import、path injection、namespace extension与 native module拒绝；
- 任一 transitive local import未列入 `files` 即 C21 FAIL。

Python import machinery在加载 exact package/test modules前必然执行现存
`trade_system/__init__.py` 与 `tests/__init__.py`；两者因此是 mandatory
parent-package closure，必须逐 byte进入 `files`。它们不得再导入任何 local
module。禁止通过把 tests改成非 package、修改 `sys.path`、自定义 loader或
直接文件加载来绕过该 closure。

这是一组固定 path，不是可配置 root或 plugin discovery。

manifest与external receipt自身位于 `files` 之外，避免 self-reference；
semantic source、Authority Bundle Spec与Route B Decision由顶层 hash字段
直接绑定，也不伪装成 kernel implementation file。

manifest `runtime` 必须逐字等于 contract `runtime`；`entrypoints` exact keys为：

```text
bundle_validator
contract_serializer
decision_calculator
labeler
ledger_encoder
reducer
```

各值逐字等于 §2.3 表中的 `python_symbol`。
`c21_check_entrypoint` 唯一为
`trade_system.rsi_mtf_drl_pm_v0_2_2.authority:check_authority_lineage_and_file_set`。
manifest不得保存 external receipt generator entrypoint；该 generator位于
authority bundle与 `files` 之外。

`kernel_capabilities` exact keys全部为 false：

```text
filesystem_read,filesystem_write,network_io,database_io,
environment_read,wall_clock,nondeterministic_randomness,
dynamic_import,native_extension,source_adapter,event_generator,
backtest,oms,live_trading
```

`authority.py` 的有限 filesystem read只在 single-process replay/C21 review
process发生，不得通过 kernel entrypoint可达；它提供的 audit observations
不能代替 external verifier在两次 replay完成后的独立复算。

`kernel_capabilities` 与 `observed_kernel_capabilities` 的扫描边界是从六个
public entrypoint symbol开始的 transitive symbol/import reachability，不是对
同文件中不可达 review symbol的误报。`contract.py:validate_contract_bytes`
可对本规格列明的 frozen paths作只读验证，
`authority.py:check_authority_lineage_and_file_set` 可执行 C21 review reads；
二者都不得从六个 public symbols可达，且不得执行 write、network、database、
environment、clock、random、subprocess或 dynamic import。scanner必须另外
确认这两个 review-only reachability exclusions及 checker→replay/process
exclusion，不能因同模块共存而把 public runtime的
`filesystem_read=false` 改成 true。

```text
file_set_sha256 =
  ID("rsi-mtf-drl-pm-file-set/v0.2.2", files)

implementation_id =
  ID("rsi-mtf-drl-pm-implementation/v0.2.2", {
    contract_canonical_sha256,runtime,entrypoints,c21_check_entrypoint,
    file_set_sha256,kernel_file_set_sha256,kernel_code_sha256,
    golden_suite_sha256,closure_trace_sha256
  })

manifest_sha256 =
  ID("rsi-mtf-drl-pm-authority-manifest/v0.2.2",
     entire manifest excluding manifest_sha256)
```

`golden_suite_sha256` 是 exact canonical golden file bytes的 SHA-256；
`closure_trace_sha256 =
ID("rsi-mtf-drl-pm-closure-trace/v0.2.2",
contract.closure_case_registry)`。`kernel_file_set_sha256` 与
`kernel_code_sha256` 必须严格按 §4.2 重算；manifest中没有可自由填写的
code identity。

planned external receipt：

```text
artifacts/rsi_mtf_drl_pm_authority_bundle_review_v0_2_2.json
```

该文件只能由 manifest `files`之外的 independent external verifier构造。构造
顺序固定为：先读取并验证 manifest与 actual workspace；再用 §6 exact argv
启动两个 fresh processes并等待两者退出；只有两次 stdout byte-identical、
所有 cases PASS且 external audits全部 PASS后，才组装 receipt并计算
`receipt_sha256`。`authority.py`、C21 checker、golden replay或任何 kernel
symbol均不得构造、返回或写入该 receipt；external verifier也不得被写入
manifest `files`或由 replay/C21 call graph调用。

exact keys：

```text
schema_version
manifest_relative_path
manifest_size_bytes
manifest_raw_sha256
manifest_sha256
core_theory_raw_sha256
legacy_v0_2_contract_raw_sha256
legacy_v0_2_contract_canonical_sha256
v0_2_1_addendum_raw_sha256
semantic_source_raw_sha256
authority_bundle_spec_raw_sha256
route_decision_raw_sha256
contract_raw_sha256
contract_canonical_sha256
observed_file_set_sha256
observed_kernel_file_set_sha256
observed_kernel_code_sha256
code_binding_audit
identity_domain_audit
observed_runtime
test_commands
test_count
test_failures
repeat_run_digests
capability_scan
closure_results
review_status
reviewer_role
receipt_sha256
```

`observed_runtime` exact keys为
`implementation,name,version,executable_path,executable_sha256`；
`test_commands` 每项 exact keys为
`argv,cwd,environment,exit_code,stdout_sha256,stderr_sha256`，禁止 shell
string；`cwd="."`，`environment` exact object为：

```text
LC_ALL = "C"
PYTHONHASHSEED = "0"
PYTHONDONTWRITEBYTECODE = "1"
TZ = "UTC"
```

该 object替换 child environment，不与调用方 environment merge；executable使用
absolute path，因此不依赖 `PATH`。

`code_binding_audit` exact keys为：

```text
expected_kernel_code_sha256
golden_input_bundle_count
golden_input_distinct_code_sha256s
actual_ledger_record_count
actual_ledger_distinct_code_sha256s
actual_label_count
actual_label_distinct_code_sha256s
hardcoded_kernel_digest_literals
status
```

三个 counts都必须是 positive integer。reviewer必须执行全部42 cases；input
audit只统计 golden中完整保存的 positive/base CanonicalSyntheticEventBundle，
以及被 negative case通过 `base_case_id`引用的 mutation前 base；若 negative
mutation故意改 code binding，它必须实际失败且不得产生 ledger/label，不把该
counterexample伪装成 authoritative input。对所有 audited base inputs、实际成功
输出 ledger record与label读取 exact binding。三个 distinct arrays都必须恰为
`[observed_kernel_code_sha256]`；
`expected_kernel_code_sha256=observed_kernel_code_sha256`；
`hardcoded_kernel_digest_literals=[]`；`status="PASS"`。只检查 expected output
或只检查 output hash不算通过。

`identity_domain_audit` exact keys为：

```text
source_old_domain_count
mapping_pair_count
source_old_domain_set_sha256
mapping_old_domain_set_sha256
mapping_new_domain_set_sha256
mapping_pairs_sha256
kernel_mapped_new_domain_set_sha256
record_hash_domain
record_hash_domain_present
dynamic_domain_construction_found
status
```

authority reviewer沿用 semantic source §12.8 lines 2957–2963 的 normative
`found_old_domains` scan，但它是 review-time immutable-source audit，不是
contract builder或 runtime parser。它从 semantic source §12.8 table读取 exact
`{old_domain,new_domain,transform}` 58-row array；所有 set先去重、按 UTF-8 bytes
严格升序，再计算：

```text
source_old_domain_set_sha256 =
  ID("rsi-mtf-drl-pm-old-domain-set/v0.2.2",
     sorted found_old_domains)

mapping_old_domain_set_sha256 =
  ID("rsi-mtf-drl-pm-old-domain-set/v0.2.2",
     sorted table.old_domain)

mapping_new_domain_set_sha256 =
  ID("rsi-mtf-drl-pm-new-domain-set/v0.2.2",
     sorted table.new_domain)

mapping_pairs_sha256 =
  ID("rsi-mtf-drl-pm-domain-mapping/v0.2.2",
     table rows in source order)
```

reviewer再以 Python stdlib `ast`枚举 §4.2 五个 kernel files中的完整 string
constants；取与58个 `new_domain`相交的 set，按同一 new-domain-set rule计算
`kernel_mapped_new_domain_set_sha256`。动态拼接/格式化 identity domain一律
记为 found。这个 scan只读取最终 Python string constants，是 review-time
capability/identity audit；它不是 ContractAST、schema transform、runtime
interpreter、code generator或 source-generation input。PASS exact conditions：

```text
source_old_domain_count = 58
mapping_pair_count = 58
source_old_domain_set_sha256 = mapping_old_domain_set_sha256
kernel_mapped_new_domain_set_sha256 = mapping_new_domain_set_sha256
record_hash_domain = "management-ledger-record/v0.2.2"
record_hash_domain_present = true
dynamic_domain_construction_found = false
status = "PASS"
```

多、少、重复 mapping、缺任一 new-domain literal或动态构造均为
`E_C21_AUTHORITY_LINEAGE_INVALID`。该 audit不执行 semantic prose，也不允许
kernel读取 source文件。

`capability_scan` exact keys为
`forbidden_imports,forbidden_calls,forbidden_native_extensions,
observed_kernel_capabilities,resolved_entrypoints,public_reachability_roots,
review_only_symbols,review_only_reachable_from_public,
c21_check_reachable_replay_or_process_symbols`；
`resolved_entrypoints` 必须逐字等于 manifest六个 `entrypoints`加
`c21_check_entrypoint`。`public_reachability_roots` 必须恰为六个 public symbol
按 entrypoint ID顺序的 array；`review_only_symbols` 必须恰为
`["trade_system.rsi_mtf_drl_pm_v0_2_2.authority:check_authority_lineage_and_file_set",
"trade_system.rsi_mtf_drl_pm_v0_2_2.contract:validate_contract_bytes"]`；
`review_only_reachable_from_public=[]`。
`c21_check_reachable_replay_or_process_symbols` 是从
`c21_check_entrypoint` 开始的 transitive AST call/import reachability中命中的
local replay/CLI driver、`subprocess`、`multiprocessing`、`os.system/popen/
spawn*/exec*`、`asyncio.create_subprocess_*` 或其他 process-creation symbol；
它必须恰为 `[]`。`authority.py` 整个 module也不得 import `subprocess`或
`multiprocessing`。external verifier启动进程的代码不在 manifest `files`
内，不能借此绕过 checker的 call-graph isolation。
`reviewer_role` 唯一为
`INDEPENDENT_SOL_ULTRA`。

两次 fresh-process replay的 argv必须恰为：

```text
[
  observed_runtime.executable_path,
  "-B","-X","utf8",
  "-m","trade_system.rsi_mtf_drl_pm_v0_2_2.authority",
  "replay",
  "--contract","config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json",
  "--golden","tests/fixtures/rsi_mtf_drl_pm_v0_2_2.golden.json"
]
```

`executable_path` 必须是 `pathlib.Path(sys.executable).resolve()` 得到的
absolute regular file，其 bytes匹配
`executable_sha256`，版本满足 contract runtime。不得通过 shell、wrapper或
不同 argv运行。

replay stdout必须是无 trailing newline的 ASCII canonical JSON，exact keys：

```text
schema_version
contract_canonical_sha256
kernel_code_sha256
golden_suite_sha256
case_results
closure_results
replay_digest
```

`case_results` 必须恰好覆盖 §4.1 的 42 个 case，按 `case_id` UTF-8 bytes严格
升序；每项 exact keys为
`case_id,closure_id,kind,result_sha256,status,error_code`。`kind` 为
`POSITIVE|NEGATIVE`，`status="PASS"`；positive 的 `error_code=null`，
negative 必须逐字等于 §4.1 的 code。`result_sha256` 对该 case的 canonical
actual result或 canonical error object计算，不得是常量、expected-only hash
或 test stdout hash。negative canonical error object exact keys/value为
`{case_id,closure_id,error_code}`，三项逐字来自 §4.1；不得包含自由 message、
stack、clock或 environment。

negative actual code的唯一来源按 executor固定：

- `bundle_validator`：实际 returned
  `BundleValidationFailureV0_2_2.error_code`；
- `decision_calculator`、`reducer`、`authority_lineage_checker`：实际 caught
  `KernelValidationError.error_code`。

若返回 success、抛出其他 exception、error code不在 exact enum、或 harness
读取 `expected_error_code` 来补 actual code，该 case立即 FAIL。多 violation
必须先由 §2.3.3 的 executor-specific fail-first规则解析，再生成 error object。

stdout `kernel_code_sha256` 必须从当前五个 kernel files重算，并同时逐字等于
golden与manifest的同名值。replay只输出上述 ASCII IDs、digests、status、
booleans与 null，不输出 semantic payload；因此这里的 ASCII-only是该固定
review envelope的物理子集，不限制 retained UTF-8 CanonicalJSON。

```text
replay_digest =
  ID("rsi-mtf-drl-pm-replay-result/v0.2.2",
     entire replay result excluding replay_digest)
```

`closure_results`必须 exact C01–C21且每项为
`{closure_id,positive_pass,negative_pass,residual_ambiguity}`；
`residual_ambiguity="NONE"` 才可 PASS。`repeat_run_digests`必须恰好两个相同
`replay_digest`，且两个 stdout bytes及 stdout SHA也必须相同。
`review_status="PASS"` 需要：

```text
test_failures = 0
observed_file_set_sha256 = manifest.file_set_sha256
observed_kernel_file_set_sha256 = manifest.kernel_file_set_sha256
observed_kernel_code_sha256 = manifest.kernel_code_sha256
code_binding_audit.status = "PASS"
identity_domain_audit.status = "PASS"
capability_scan.review_only_reachable_from_public = []
capability_scan.c21_check_reachable_replay_or_process_symbols = []
all kernel capabilities = false
all C01-C21 positive_pass = true
all C01-C21 negative_pass = true
all residual_ambiguity = "NONE"
```

```text
receipt_sha256 =
  ID("rsi-mtf-drl-pm-authority-review-receipt/v0.2.2",
     entire receipt excluding receipt_sha256)
```

receipt由 manifest外部 verifier与独立 Sol reviewer在两次 replay完成后生成；
kernel、manifest、fixture、C21 checker或 replay不得自称 PASS。

## 7. Stage gates

### B1 — contract candidate

允许：

- 新 v0.2.2 outcome-free contract；
- 只读 exact contract validator；
- contract-only synthetic mutation tests。

PASS：

- source/decision/spec hashes匹配；
- physical JSON canonical且 digest稳定；
- top schema与每个 registry exact/closed；
- semantic commitment、11 个 support types、13 个 algorithm interfaces与
  6 个 public entrypoint signatures逐字匹配；
- 26 个 error codes、六个 failure modes与 executor-specific fail-first arrays
  闭合；
- C01–C21 trace无缺失；
- active role只有 SYNTHETIC；
- no outcome/data/adapter/backtest/paper/trading capability；
- independent Sol review为 PASS。

达到 B1 PASS前禁止创建 `model.py`、`kernel.py` 或 golden expected outputs。

### B2 — pure reference kernel

只有 B1 PASS 后由新的阶段调度启动。Terra实现 `model.py` 与 `kernel.py`，
逐 registry完成完整模块，包括 single `KernelValidationError`、executor-specific
fail-first、ValidatedBundle revalidation及 §4.2 code-binding byte-copy；每遇
contract双解立即停止交 Sol，不自行默认。B2结束不产生市场结论。

### B3 — synthetic authority gate

完成 golden suite、tests、`authority.py`、manifest、两次独立进程重放、
code-binding/identity-domain/capability audits与 external receipt。独立 Sol审核
同一 exact hashes。
唯一升级是 `E0_SYNTHETIC_VALIDATED`。

### B4 — data feasibility

必须另有 Sol authorization与独立 source-adapter contract。先验证字段、频率、
sequence、generation、as-of、coverage与成本证据能否获得；任何 gap只能
censor、data delta或停止。B4不得修改 B1–B3 authority bytes。

DEVELOPMENT、CALIBRATION、one-shot HOLDOUT、paper与live继续按 semantic source
§14.4–§14.6，各自需要新的显式 gate。

## 8. Terra B1 exact delivery

Terra B1只可创建：

```text
config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json
trade_system/rsi_mtf_drl_pm_v0_2_2/__init__.py
trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py
tests/test_rsi_mtf_drl_pm_v0_2_2_contract.py
artifacts/rsi_mtf_drl_pm_v0_2_2_b1_contract_report.md
```

不得修改：

```text
CORE_TRADING_THEORY.md
RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_1.md
RSI_MTF_DRL_PM_THEORY_ADDENDUM_v0_2_2.md
RSI_MTF_DRL_PM_DIRECT_AST_PROFILE_v0_2_2.md
config/rsi_mtf_drl_pm.research_contract.v0_2.json
trade_system/rsi_research_contract.py
tests/test_rsi_research_contract.py
active G1 package, plan, registry, logs or evidence
January, February, March or any seen-role artifact
```

B1 minimum tests：

1. exact authority hashes、四层 `composite_theory_id`重算与新/旧 container
   identity隔离；
2. semantic UTF-8 CanonicalJSON行为，以及仅 B1 contract actual bytes的
   ASCII、safe integer、no float、no trailing LF附加约束；
3. semantic commitment 与四个 finite registries的 missing/extra/duplicate/
   reordered member拒绝；
4. 11 个 support type的 field order、closed union、success carrier、C21
   三字段 constant PASS carrier且无 derived field、26-member
   `KernelErrorCode` order、bundle subset与 invariant mutation拒绝；
5. 13 个 algorithm的 parameter order、return、status polarity、owner与
   authority-ref mutation拒绝；
6. 6 个 public entrypoint的 parameter/return/symbol/failure-mode/
   failure-code-order/purity，`ContractValidationError` exact carrier，以及 B1
   `__init__.__all__` exact；
7. C01–C21 closure、42 个 case ID、21 个 error code与 gate arrays的
   missing/extra/mismatch拒绝；
8. semantic commitment、chronology、authorization任一 mutation拒绝；
9. parameter/policy/schema/formula/status/selector/identity/state/risk override，
   outcome、market/historical data、adapter、backtest、paper、OMS、live字段或
    capability注入拒绝；
10. authority-ref path/range必须命中 frozen source且 owner reference全量闭合；
11. validator source无 filesystem write、network、database、subprocess、
    environment、clock、random或 dynamic import；
12. 旧 v0.2 contract validator既有 18 tests继续通过，且 CORE、v0.2 raw/
    canonical、v0.2.1、v0.2.2、Profile与 Terra report hashes未变。

B1 report必须列出 exact file hashes/sizes、实际命令/test count、失败数、
未运行项与最大允许声明。不得生成 manifest或 PASS receipt；它们属于 B3。

## 9. Failure routing and release

```text
contract ambiguity -> Sol semantic/contract delta
implementation mismatch -> Terra implementation fix
golden expected conflicts with contract -> Sol, never expected-only edit
source availability/gap failure -> B4 data delta or STOP
DEVELOPMENT failure -> one preregistered challenger or STOP
CALIBRATION/HOLDOUT failure -> candidate STOP
```

最终用户可读理论的唯一 planned path：

```text
RSI_MTF_DRL_PM_FINAL_THEORY_v0_2_2.md
```

该文件只能在 B3 PASS 后创建，并逐项 pin semantic source、Authority Bundle
Spec、Route B Decision、contract、manifest与external receipt的 raw/canonical
hash。它必须明确区分：

```text
mechanical E0 validity
synthetic validation
data feasibility
predictive validity
execution realism
paper safety
live authorization
```

任何前一层 PASS都不得被写成后一层结论。
