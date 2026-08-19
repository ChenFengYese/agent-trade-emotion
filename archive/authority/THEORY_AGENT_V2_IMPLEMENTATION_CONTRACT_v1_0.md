# Theory Agent V2 Implementation Contract v1.0

Status: `CANONICAL_E0_IMPLEMENTATION_CONTRACT_CLOSED`

Evidence level: `E0`

Runtime authority: `NONE`

Paper authority: `NONE`

Live authority: `NONE`

System mode: `E0_OFFLINE_COUNTERFACTUAL`

External execution authority: `NONE_E0`

Executable: `false`

Applies to: new, independent, offline, counterfactual-only Theory Agent V2
implementation.

Does not modify: `CORE_TRADING_THEORY_v2_1.md`, frozen V1 prompts, cycles
`0001` through `0025`, V1 account/portfolio state, ledgers, transactions,
reports, thresholds, or automation-2.

Legacy access: `READ_ONLY_DIGEST_BOUND`.

---

## 1. Authority and purpose

This contract closes the remaining business-contract boundary between:

1. the reviewed strategic-episode candidate;
2. the path-payoff and staged-position candidate;
3. bounded Agent autonomy;
4. the three-role Agent cluster;
5. the four-layer V2 architecture.

For V2 E0 implementation, conflicts between those candidate documents are
resolved by this contract. This contract does not promote any candidate into
Core Trading Theory. Core v2.1 remains the theory authority. Where Core and this
contract conflict, Core wins and the affected V2 candidate is denied.

The implementation target is:

```text
frozen point-in-time evidence
→ persistent accepted strategic state
→ bounded Agent proposal and challenge
→ deterministic candidate assembly, payoff, risk and constraint evaluation
→ Agent selection inside the exact feasible set
→ deterministic E0 governance
→ offline replay
→ one atomic UnitOfWork commit
```

Every object and transition below is counterfactual-only. No object is
dispatchable to a paper or live venue.

---

## 2. Canonical conventions

### 2.1 Schema and bytes

- JSON Schema dialect: `2020-12`.
- Schema identity: `(unversioned schema_id, full SemVer schema_version)`.
- Initial schema version: `1.0.0`.
- Every object schema uses `additionalProperties: false`.
- Every field is required unless its type explicitly includes `null`.
- Timestamps are UTC RFC 3339 strings with an explicit `Z`.
- Decimal values are canonical base-10 strings plus an explicit unit or
  currency reference. Binary floating-point JSON numbers are forbidden.
- Canonicalization is JCS/RFC 8785.
- Digests are lowercase SHA-256 hex.
- Self-digest calculation omits exactly the schema-declared self-digest field,
  canonicalizes the remaining payload, hashes it, and inserts the digest.
- Arrays are ordered unless explicitly declared as unique sets.
- `ObjectRef` and `CausalRef` retain their exact definitions from the Agent
  cluster contract.

### 2.2 Immutability and ownership

- Every authoritative object has exactly one owner module.
- Every accepted revision references its previous accepted revision.
- A reducer never mutates an object owned by another module.
- Cross-module effects are proposed as typed objects and become visible only in
  one UnitOfWork.
- Narrative text, Agent prose, reports and chat summaries have no state,
  evidence, calculation, permission or commit authority.

### 2.3 Point-in-time rule

A decision-bearing field is admissible only when:

```text
available_at <= decision_cutoff
and ingested_at <= decision_cutoff
and source_committed_at <= decision_cutoff
and source_commit_receipt is valid
and physical_existence_at_source_time = PROVEN
and usage_scope = DECISION_CONTEMPORANEOUS
```

Provider archives with release-time proof may be used only for
`COUNTERFACTUAL_MARKET_REPLAY`. They may not be represented as data consumed by
the historical Agent.

### 2.4 No implicit defaults

An absent profile, threshold, multiplier, cost, calendar, state head, risk
envelope, permission, ACK, or required lineage is `UNKNOWN` or a typed rejection.
Implementation code may not guess a value from the SNDK outcome, a later price,
a common market convention, or model prose.

### 2.5 Orthogonal execution, probability and dataset axes

Every decision-bearing, action-bearing, replay and commit artifact carries the
following exact E0 authority tuple:

```yaml
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
```

These fields are not aliases for probability quality or dataset provenance.
Probability-bearing objects use only:

```text
ProbabilityStatus =
  CALIBRATED_OOS
  | ORDINAL_ONLY
  | UNKNOWN
```

Replay manifests separately declare:

```text
DatasetType =
  LEGACY_ACTUAL_INPUT
  | HISTORICAL_COUNTERFACTUAL_REPLAY
  | SYNTHETIC_CONTRACT_FIXTURE
  | INDEPENDENT_FROZEN_EVALUATION
```

`DatasetType` describes the source/evaluation cohort only. It cannot confer
calibration, execution, paper, live, or theory authority. Conversely, the E0
system mode does not imply that a dataset is synthetic.

---

## 3. Canonical conflict resolutions

The following names and semantics are final for V2 E0:

| Conflicting draft terms | Canonical term | Resolution |
|---|---|---|
| `PositionPathPlan` | `StagedPositionPlan` | one immutable plan with ordered registered stages |
| `TranchePlan` | `StageSpec` | stage is a pre-registered risk/action specification |
| `TrancheTransitionReceipt`, `StageActivationReceipt` | `StageTransitionReceipt` | one receipt covers the complete stage lifecycle |
| `AttentionAvailabilityContract` | `SupervisionAvailabilityContract` | supervision is an execution-permission fact, never a market view |
| implicit episode risk fields only | `EpisodeRiskBudgetEnvelope` | a separate Domain Position aggregate owns episode risk allocation and use |
| `RiskBudgetRevisionReceipt` | `EpisodeRiskBudgetTransitionReceipt` | every episode-risk revision has a typed before/after receipt |
| `CounterfactualTrancheSelectionReceipt` | no separate object | use `AgentSelection` + `StageTransitionReceipt` + `CounterfactualPolicyReceipt` |
| permission-bearing action names | semantic `ActionIntent` plus authority tuple | permission, runtime and executability never appear in the action token |
| mixed strategy/protection/geometry intent | three orthogonal `ProposedActionPlan` facets | each validator evaluates only its owned facet |
| free-form wait/abstain | `NO_ACTION_WITH_OBLIGATION` | must carry a review clock and unmet dependency or explicit no-opportunity reason |

`StageActivationReceipt.v1` is removed from the initial schema set and replaced
by `StageTransitionReceipt.v1`.

`HEDGE` remains a valid value of the closed lot-role taxonomy so an Agent request
can be audited. Under E0 it is rejected during deterministic candidate assembly,
before a `CandidateBundle`, feasible-set member, selection or counterfactual
policy receipt can exist.

---

## 4. Closed enums

### 4.1 Strategic and exposure state

```text
StrategicStatus =
  ACTIVE
  | CHALLENGED
  | INVALIDATED
  | CLOSED

ExposureStatus =
  FLAT
  | EXPOSED
  | RISK_REDUCED
  | EXIT_PENDING
  | RECONCILE_PENDING

WorkflowProjection =
  ACTIVE
  | CHALLENGED
  | RISK_REDUCED
  | REENTRY_PENDING
  | INVALIDATED
  | CLOSED
```

`WorkflowProjection` is a lossy read projection, derived in this precedence
order and never accepted as command input:

```text
CLOSED
  if StrategicStatus=CLOSED
INVALIDATED
  else if StrategicStatus=INVALIDATED
REENTRY_PENDING
  else if ExposureStatus=FLAT and a nonterminal ReentryContract exists
CHALLENGED
  else if StrategicStatus=CHALLENGED
RISK_REDUCED
  else if ExposureStatus=RISK_REDUCED
ACTIVE
  otherwise
```

`StrategicStatus` and `ExposureStatus` remain the two authoritative,
independently owned axes. There is no workflow-state reducer, workflow-state
event or inverse mapping from `WorkflowProjection` to either axis.

### 4.2 Position and stage

```text
LotRole = CORE | TACTICAL | HEDGE

EntryStage = PROBE | CONFIRMED

StageKind = INITIAL | CONFIRMATION | TREND

StageStatus =
  REGISTERED
  | ELIGIBLE
  | ARMED
  | COUNTERFACTUAL_FILLED
  | PROTECTED
  | PARTIALLY_CLOSED
  | CLOSED
  | EXPIRED
  | CANCELLED
  | REJECTED
```

`EntryStage`, `StageKind`, and `LotRole` are orthogonal. There is no default
mapping between them.

### 4.3 Supervision

```text
SupervisionMode =
  SUPERVISED
  | UNATTENDED_PROTECTED
  | NO_NEW_RISK
```

### 4.4 Reentry

```text
ReentryStatus =
  OPEN
  | DUE
  | ELIGIBLE
  | EXECUTED
  | EXPIRED
  | CANCELLED_INVALIDATED
  | CANCELLED_CLOSED
```

### 4.5 Geometry

```text
AnalysisGeometryStatus =
  DRAFT
  | PROPOSED
  | ACTIVE_ANALYSIS
  | STALE_FOR_NEW_DECISIONS
  | SUPERSEDED
  | EXPIRED

ExecutionBarrierStatus =
  NONE
  | PENDING_VENUE_ACK
  | ACTIVE_PROTECTION
  | SUPERSEDED
  | TRIGGERED
  | CANCELLED
  | REJECTED
  | ACK_TIMEOUT
  | HALTED_RECONCILE
```

### 4.6 Closed action and operation registries

```text
ActionIntent =
  KEEP_CORE
  | ACTIVATE_REGISTERED_STAGE
  | REDUCE_TACTICAL
  | PARTIAL_PROFIT
  | EXIT_STRATEGIC
  | EXIT_TO_REENTRY_PENDING
  | REENTER_PARTIAL
  | NO_ACTION_WITH_OBLIGATION

ProtectiveActionType =
  NONE
  | TIGHTEN_STOP
  | TRAIL_CORE
  | STOP
  | KILL
  | PROTECTION_REPAIR
  | REDUCE_ONLY
  | EXIT
  | TIMEOUT
  | RECONCILIATION

GeometryOperation =
  KEEP
  | EXPIRE
  | REBUILD_ANALYTICAL
  | REVISE_PROTECTION

AtomicEffectType =
  CREATE_REENTRY_CONTRACT
  | RESERVE_STAGE_RISK
  | RELEASE_STAGE_RISK
  | REGISTER_PROTECTIVE_BARRIER
  | REQUEST_PORTFOLIO_RECONCILIATION

AggregateType =
  STRATEGIC_EPISODE
  | HYPOTHESIS_SET
  | POSITION_PLAN
  | EPISODE_RISK_BUDGET
  | STAGE
  | SUPERVISION
  | GEOMETRY
  | REENTRY
  | PORTFOLIO
  | SCHEDULER_CURSOR
```

Intent semantics:

| Intent | Required semantic effect |
|---|---|
| `KEEP_CORE` | retain existing reconciled CORE exposure and protection |
| `ACTIVATE_REGISTERED_STAGE` | evaluate one existing `StageSpec`; no ad-hoc stage may be created |
| `REDUCE_TACTICAL` | reduce only TACTICAL quantity; strategic status is unchanged |
| `PARTIAL_PROFIT` | reduce a declared quantity/role under a frozen target or management policy |
| `EXIT_STRATEGIC` | requires independent valid strategic invalidation or accepted terminal close cause |
| `EXIT_TO_REENTRY_PENDING` | request CORE quantity zero while the thesis survives and require the atomic `CREATE_REENTRY_CONTRACT` effect |
| `REENTER_PARTIAL` | evaluate an `ELIGIBLE` reentry contract, new THI, current geometry and current risk |
| `NO_ACTION_WITH_OBLIGATION` | no new risk; must record exact reason, dependency and next review clock |

`ProtectiveActionType` is not a directional view. `TIGHTEN_STOP` and
`TRAIL_CORE` require non-looser protection; `STOP`, `KILL`, `REDUCE_ONLY`,
`EXIT`, `TIMEOUT` and `RECONCILIATION` are protective or operational causes,
not strategic invalidators.

`GeometryOperation` controls analytical/protection geometry lifecycle only.
`REBUILD_ANALYTICAL` cannot cancel active protection.
`REVISE_PROTECTION` requires a paired protective action and ACK-ordering policy.

`CREATE_REENTRY_CONTRACT` is an atomic UnitOfWork effect. It is never an
`ActionIntent`, protective action, geometry operation or independently
selectable candidate.

Every `ProposedActionPlan` carries exactly one `ActionIntent`, exactly one
`ProtectiveActionType` (including `NONE`), exactly one `GeometryOperation`, and
a unique set of atomic effects. One facet cannot hide a separately permissioned
risk increase or strategic mutation.

---

## 5. Canonical object additions and replacements

The Architecture initial schema set is amended before C1.0:

### 5.1 Remove

- `stage_activation_receipt.v1`

### 5.2 Add

- `episode_risk_budget_envelope.v1`
- `episode_risk_budget_transition_receipt.v1`
- `stage_transition_receipt.v1`
- `supervision_transition_receipt.v1`
- `trading_session_calendar_profile.v1`
- `expected_slot_policy.v1`
- `matching_policy_profile.v1`
- `barrier_order_spec.v1`
- `data_dependency_contract.v1`
- `plugin_invocation_receipt.v1`
- `cross_timescale_control_envelope.v1`
- `recursive_feasibility_receipt.v1`
- `receding_horizon_plan.v1`
- `calibration_registry.v1`
- `probability_use_authorization.v1`
- `forecast_coherence_receipt.v1`
- `uncertainty_decomposition_receipt.v1`
- `regime_shift_monitor_receipt.v1`
- `aggregate_head_receipt.v1`
- `event_replay_compatibility_manifest.v1`
- `reasoning_strategy_contract.v1`
- `decision_criterion_policy.v1`
- `forecast_issuance_receipt.v1`
- `outcome_resolution_receipt.v1`
- `calibration_dataset_manifest.v1`

The schema count is not an authority or acceptance target. Registry/tree set
equality is recomputed from the materialized registry and schema tree after
these changes. No prose count, prior inventory count or test fixture count may
be used as authority.

### 5.3 `EpisodeRiskBudgetEnvelope.v1`

Owner: `DOMAIN_POSITION`

```yaml
episode_risk_budget_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
revision: positive integer
account_risk_budget_envelope_ref: ObjectRef
episode_risk_allocation_receipt_ref: ObjectRef
frozen_equity_ref: ObjectRef
episode_risk_cap_ref: ObjectRef
core_risk_cap_ref: ObjectRef
tactical_risk_cap_ref: ObjectRef
hedge_risk_cap_ref: ObjectRef
realized_loss_ref: ObjectRef
realized_cost_ref: ObjectRef
open_risk_ref: ObjectRef
pending_risk_ref: ObjectRef
reserved_untriggered_stage_risk_ref: ObjectRef
tail_reserve_ref: ObjectRef
remaining_episode_capacity_ref: ObjectRef
stage_risk_allocation_refs: ordered array<ObjectRef>, minItems=1
risk_reuse_policy: NO_DISCRETIONARY_RECYCLING_E0
unrealized_profit_credit_ref: null
valid_from: UTC timestamp
valid_until: UTC timestamp
previous_revision_ref: ObjectRef | null
policy_digest: sha256
envelope_digest: sha256
```

Required invariant:

```text
realized_loss
+ realized_cost
+ open_risk
+ pending_risk
+ reserved_untriggered_stage_risk
+ tail_reserve
<= episode_risk_cap
```

All components are nonnegative and share one account-risk unit. Unrealized
profit never reduces the left side and never increases a cap. Components are
mutually exclusive under the frozen accounting policy: a cost embedded in an
open or pending risk value cannot also appear in `realized_cost`. The
CORE/TACTICAL/HEDGE sub-caps are nonnegative, sum to no more than the episode
cap, and `hedge_risk_cap=0` in E0.

### 5.4 `EpisodeRiskBudgetTransitionReceipt.v1`

Owner: `DOMAIN_POSITION`

```yaml
strategic_episode_ref: ObjectRef
prior_budget_ref: ObjectRef | null
next_budget_ref: ObjectRef
cause_event_ref: ObjectRef
transition_kind: ALLOCATE | RESERVE_STAGE | RELEASE_UNUSED_STAGE | OPEN_RISK | PENDING_RISK | REALIZE_LOSS | REALIZE_COST | CLOSE_RISK | RECONCILE
affected_stage_ref: ObjectRef | null
before_component_refs: nonempty ordered array<ObjectRef>
after_component_refs: nonempty ordered array<ObjectRef>
account_cap_verdict: PASS | FAIL | UNKNOWN
episode_cap_verdict: PASS | FAIL | UNKNOWN
profit_non_recycling_verdict: PASS | FAIL
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

### 5.5 `StagedPositionPlan.v1`

Owner: `DOMAIN_POSITION`

```yaml
plan_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
revision: positive integer
side: LONG | SHORT
episode_risk_budget_ref: ObjectRef
path_payoff_matrix_ref: ObjectRef
stage_refs: ordered array<ObjectRef>, minItems=1
stage_count: positive integer
stage_risk_fraction_sum_ref: ObjectRef
stage_execution_policy_ref: ObjectRef
adjustment_quota_ref: ObjectRef
target_policy_ref: ObjectRef
reentry_policy_ref: ObjectRef
supervision_contract_ref: ObjectRef
unregistered_action_policy: REJECT
frozen_before_first_fill: true
valid_from: UTC timestamp
valid_until: UTC timestamp
previous_revision_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
plan_digest: sha256
```

`stage_count == stage_refs.length`; stage risk fractions are nonnegative and sum
to no more than one episode risk unit.

### 5.6 `StageSpec.v1`

Owner: `DOMAIN_POSITION`

```yaml
stage_id: non-empty globally unique string
plan_id: non-empty globally unique string
stage_index: nonnegative integer
stage_kind: INITIAL | CONFIRMATION | TREND
entry_stage: PROBE | CONFIRMED
lot_role: CORE | TACTICAL
predecessor_stage_ref: ObjectRef | null
activation_dependency_refs: ordered array<ObjectRef>, minItems=0
required_evidence_class_refs: ordered array<ObjectRef>, minItems=0
required_time_authority_ref: ObjectRef
risk_fraction_ref: ObjectRef
entry_trigger_ref: ObjectRef
entry_zone_ref: ObjectRef
invalidation_ref: ObjectRef
geometry_ref: ObjectRef
hypothesis_ref: ObjectRef
stop_ref: ObjectRef
target_ref: ObjectRef
horizon_ref: ObjectRef
maximum_quantity_ref: ObjectRef
maximum_slippage_ref: ObjectRef
gap_stress_buffer_ref: ObjectRef
minimum_forward_reward_risk_policy_ref: ObjectRef
pending_risk_ref: ObjectRef
required_permission_ref: ObjectRef
allowed_supervision_modes: nonempty unique array<SUPERVISED | UNATTENDED_PROTECTED>
expiry: UTC timestamp
untriggered_disposition: WAIT | EXPIRE
maximum_retries: nonnegative integer
cancellation_predicate_refs: ordered array<ObjectRef>, minItems=0
stage_digest: sha256
```

The first stage has a null predecessor. Every later stage references the
immediately preceding stage. HEDGE is absent from E0 `StageSpec`.

### 5.7 `StageTransitionReceipt.v1`

Owner: `DOMAIN_POSITION`

```yaml
stage_ref: ObjectRef
plan_ref: ObjectRef
prior_stage_receipt_ref: ObjectRef | null
status_before: null | REGISTERED | ELIGIBLE | ARMED | COUNTERFACTUAL_FILLED | PROTECTED | PARTIALLY_CLOSED | CLOSED | EXPIRED | CANCELLED | REJECTED
status_after: REGISTERED | ELIGIBLE | ARMED | COUNTERFACTUAL_FILLED | PROTECTED | PARTIALLY_CLOSED | CLOSED | EXPIRED | CANCELLED | REJECTED
cause_event_ref: ObjectRef
decision_cutoff: UTC timestamp
trigger_verdict: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
expiry_verdict: ACTIVE | EXPIRED
predecessor_verdict: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
remaining_account_risk_ref: ObjectRef
remaining_episode_risk_ref: ObjectRef
current_forward_reward_risk_ref: ObjectRef
protection_atomicity_verdict: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
counterfactual_disposition: SELECTED | REJECTED | NOT_ELIGIBLE | FILLED | NOT_APPLICABLE
selected_action_plan_ref: ObjectRef | null
matching_result_ref: ObjectRef | null
portfolio_reconciliation_ref: ObjectRef | null
authoritative_position_state_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

No later price may revive an EXPIRED, CANCELLED or REJECTED stage. A new plan
revision creates new stage IDs.

`StageTransitionReceipt` is a lifecycle receipt, not position or fill authority.
Plan acceptance events may register a stage; a selected current action and risk
reservation may arm it; matching events may report a candidate fill; and
portfolio reconciliation events may advance filled/protected/closed status.
Only the portfolio aggregate owns authoritative quantity, lot and fill state.
The matching result is evidence for that reducer and cannot by itself create a
lot. A transition to `COUNTERFACTUAL_FILLED`, `PROTECTED`,
`PARTIALLY_CLOSED` or `CLOSED` requires the exact portfolio reconciliation and
authoritative position-state refs; the stage receipt never duplicates their
fields or ownership.

### 5.8 `SupervisionAvailabilityContract.v1`

Owner: `DOMAIN_POSITION`

```yaml
supervision_contract_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
revision: positive integer
mode_windows: ordered array<TimeWindow>, minItems=1
max_unattended_duration_ref: ObjectRef
allowed_autonomous_action_intents: unique array<ActionIntent>
forbidden_unattended_action_intents: unique array<ActionIntent>
allowed_autonomous_protective_actions: unique array<ProtectiveActionType>
forbidden_unattended_protective_actions: unique array<ProtectiveActionType>
allowed_autonomous_geometry_operations: unique array<GeometryOperation>
forbidden_unattended_geometry_operations: unique array<GeometryOperation>
allowed_preregistered_stage_refs: unique array<ObjectRef>
required_active_protection_refs: unique array<ObjectRef>
required_ack_freshness_ref: ObjectRef
data_freshness_policy_ref: ObjectRef
maximum_unattended_worst_case_loss_ref: ObjectRef
review_deadline_refs: nonempty ordered array<ObjectRef>
alert_policy_ref: ObjectRef
failure_action: NO_NEW_RISK
valid_from: UTC timestamp
valid_until: UTC timestamp
previous_revision_ref: ObjectRef | null
contract_digest: sha256
```

`TimeWindow`:

```yaml
start_at: UTC timestamp
end_at: UTC timestamp
mode: SUPERVISED | UNATTENDED_PROTECTED | NO_NEW_RISK
```

Windows are ordered, non-overlapping and satisfy `start_at < end_at`.

### 5.9 `SupervisionTransitionReceipt.v1`

Owner: `DOMAIN_POSITION`

```yaml
contract_ref: ObjectRef
mode_before: null | SUPERVISED | UNATTENDED_PROTECTED | NO_NEW_RISK
mode_after: SUPERVISED | UNATTENDED_PROTECTED | NO_NEW_RISK
cause_event_ref: ObjectRef
effective_at: UTC timestamp
protection_coverage_verdict: PASS | FAIL | UNKNOWN
ack_freshness_verdict: PASS | FAIL | UNKNOWN
data_freshness_verdict: PASS | FAIL | UNKNOWN
account_consistency_verdict: PASS | FAIL | UNKNOWN
worst_case_loss_verdict: PASS | FAIL | UNKNOWN
resulting_permission: NORMAL_E0 | PREREGISTERED_PROTECTED_ONLY_E0 | NO_NEW_RISK
receipt_digest: sha256
```

### 5.10 `DataDependencyContract.v1`

Owner: `DOMAIN_POLICY`

```yaml
dependency_contract_id: non-empty globally unique string
consumer_kind: REDUCER | CALCULATOR | ACTION_PLAN_FACET | PLUGIN
consumer_id: non-empty closed consumer ID
field_requirements: nonempty ordered array<FieldRequirement>
unknown_propagation_policy: DEPENDENT_CANDIDATE_ONLY
policy_digest: sha256
contract_digest: sha256
```

`FieldRequirement`:

```yaml
field_pointer: JSON Pointer
necessity: REQUIRED_TO_CONSTRUCT | REQUIRED_TO_CALCULATE | OPTIONAL_SUPPORT | EVALUATION_ONLY
accepted_quality_states: nonempty unique array<OBSERVED | DERIVED | PROXY>
on_missing: SESSION_NO_COMMIT | CANDIDATE_UNKNOWN_REMOVE | CALCULATION_PARTIAL_UNKNOWN | RETAIN_WITH_UNKNOWN | IGNORE_FOR_DECISION
applicable_action_intents: unique array<ActionIntent>
applicable_protective_actions: unique array<ProtectiveActionType>
applicable_geometry_operations: unique array<GeometryOperation>
constraint_id: non-empty registered constraint ID
```

### 5.11 `CrossTimescaleControlEnvelope.v1`

Owner: `DOMAIN_STRATEGIC`

```yaml
envelope_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
strategic_state_ref: ObjectRef
strategic_state_revision: positive integer
strategic_timeframe_ref: ObjectRef
available_at_cutoff: UTC timestamp
evidence_refs: ordered array<ObjectRef>, minItems=1
lease: CrossTimescaleLease
promotion_requirement_refs: ordered array<ObjectRef>, minItems=1
terminal_safe_action_plan_ref: ObjectRef
authority_ref: ObjectRef
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
envelope_digest: sha256
```

`CrossTimescaleLease`:

```yaml
valid_from: UTC timestamp
valid_until: UTC timestamp
next_strategic_review_at: UTC timestamp
permitted_fast_action_intents: unique array<ActionIntent>
permitted_protective_actions: unique array<ProtectiveActionType>
permitted_geometry_operations: unique array<GeometryOperation>
max_position_delta_ref: ObjectRef
max_risk_delta_ref: ObjectRef
max_action_rate_ref: ObjectRef
risk_reduction_permissions: unique array<ProtectiveActionType>
forbidden_strategic_mutation_refs: nonempty ordered array<ObjectRef>
emergency_override_policy_ref: ObjectRef
lease_digest: sha256
```

The exact accepted strategic state revision must equal the envelope revision and
the decision cutoff must be inside `[valid_from, valid_until)`. Expiry, revision
mismatch, missing authority or unverifiable state permits only the registered
terminal safe action, whose position and risk deltas are nonpositive. Lower
timeframe evidence can create a typed promotion request or a protective/risk
action inside this envelope; it cannot emit a strategic transition event.

### 5.12 `RecursiveFeasibilityReceipt.v1`

Owner: `DOMAIN_POSITION`

```yaml
receipt_id: non-empty globally unique string
candidate_action_ref: ObjectRef
starting_aggregate_head_refs: nonempty ordered array<ObjectRef>
planning_horizon_ref: ObjectRef
next_review_at: UTC timestamp
stress_scenario_set: StressScenarioSet
reachable_state_summary_refs: nonempty ordered array<ObjectRef>
safe_continuation_action_refs: ordered array<ObjectRef>, minItems=0
terminal_safe_action_ref: ObjectRef
hard_constraint_result_refs: nonempty ordered array<ObjectRef>
solver_or_evaluator_version: semver
solver_or_evaluator_digest: sha256
status: PASS | FAIL | UNKNOWN
failure_reason_codes: ordered array<string>
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

`StressScenarioSet` is an embedded `$defs` value in this schema:

```yaml
stress_scenario_set_id: non-empty globally unique string
frozen_at: UTC timestamp, not later than the decision cutoff
scenario_refs: nonempty ordered unique array<ObjectRef>
required_scenario_class_refs: nonempty ordered unique array<ObjectRef>
coverage_verdict: PASS | FAIL | UNKNOWN
set_digest: sha256
```

`PASS` requires at least one registered compliant continuation or terminal safe
action for every registered stress scenario and exact starting head, and
therefore requires `safe_continuation_action_refs` to contain at least one
entry. `FAIL` or `UNKNOWN` may contain an empty continuation array, but the
terminal safe action remains mandatory. `UNKNOWN` is not PASS and cannot
authorize new risk. This receipt proves
contract feasibility only; it is not evidence for a market path, probability,
profit or causal effect.

### 5.13 `RecedingHorizonPlan.v1`

Owner: `DOMAIN_POSITION`

```yaml
receding_horizon_plan_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
revision: positive integer
decision_cutoff: UTC timestamp
planning_context_id: non-empty globally unique string
candidate_action_set_digest: sha256
current_authorized_action_ref: ObjectRef
conditional_continuation_branches: ordered array<ContinuationBranch>, minItems=0
planned_review_points: nonempty ordered array<UTC timestamp>
terminal_fallback_action_ref: ObjectRef
cost_model_ref: ObjectRef
path_payoff_matrix_ref: ObjectRef
recursive_feasibility_receipt_ref: ObjectRef
first_step_only: true
future_branch_authority: REQUIRES_CURRENT_DATA_REAPPROVAL
previous_revision_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
plan_digest: sha256
```

`ContinuationBranch`:

```yaml
branch_id: non-empty string, unique within plan
trigger_predicate_refs: nonempty ordered array<ObjectRef>
planned_action_ref: ObjectRef
remaining_risk_budget_ref: ObjectRef
review_at: UTC timestamp
branch_status: CONDITIONAL_NOT_AUTHORIZED
branch_digest: sha256
```

Only `current_authorized_action_ref` may enter the current `UnitOfWorkBatch`.
A continuation branch is planning evidence, not an order, permission, stage
activation or reserved fill. When its trigger becomes current, the branch must
be rebuilt and approved with then-available data, exact current aggregate
heads, current costs, current supervision and a new feasibility receipt.

### 5.14 `CalibrationRegistry.v1`

Owner: `DOMAIN_POLICY`

```yaml
calibration_registry_id: non-empty globally unique string
registry_version: semver
calibration_record_refs: ordered unique array<ObjectRef>, minItems=0
registry_status: EMPTY_E0
valid_from: UTC timestamp
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
registry_digest: sha256
```

The future-compatible nested `CalibrationRecord` contract is:

```yaml
calibration_record_id: non-empty globally unique string
model_or_forecaster_ref: ObjectRef
calibration_dataset_manifest_ref: ObjectRef
event_definition_ref: ObjectRef
label_resolver_ref: ObjectRef
instrument_or_universe_scope_ref: ObjectRef
forecast_horizon_ref: ObjectRef
regime_or_cohort_ref: ObjectRef
training_cutoff: UTC timestamp
evaluation_cutoff: UTC timestamp
sample_size: nonnegative integer
effective_sample_size_ref: ObjectRef
forecast_issuance_set_digest: sha256
outcome_resolution_set_digest: sha256
brier_score_ref: ObjectRef
log_score_ref: ObjectRef
reliability_diagnostics_ref: ObjectRef
sharpness_diagnostics_ref: ObjectRef
drift_status: NO_SHIFT | SUSPECTED | CONFIRMED | UNKNOWN
valid_from: UTC timestamp
expires_at: UTC timestamp
record_digest: sha256
```

For E0, `calibration_record_refs` is exactly empty and no
`CalibrationRecord` instance is accepted into decision state. The nested
contract exists only to freeze the future interface; it confers no current
calibration authority.

### 5.15 `ProbabilityUseAuthorization.v1`

Owner: `DOMAIN_POLICY`

```yaml
authorization_id: non-empty globally unique string
calibration_record_ref: ObjectRef
coherence_receipt_ref: ObjectRef
authorized_event_scope_ref: ObjectRef
authorized_horizon_ref: ObjectRef
authorized_regime_ref: ObjectRef
allowed_uses: nonempty unique array<DISPLAY_ONLY | PATH_RANKING | EXPECTED_VALUE | POSITION_SIZING>
maximum_risk_authority_ref: ObjectRef
valid_from: UTC timestamp
valid_until: UTC timestamp
revocation_predicate_refs: nonempty ordered array<ObjectRef>
fallback_probability_status: ORDINAL_ONLY | UNKNOWN
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
authorization_digest: sha256
```

The schema is materialized, but the accepted E0 authorization instance count is
exactly zero. Therefore E0 probability status is only `ORDINAL_ONLY` or
`UNKNOWN`; numeric probability may appear only as untrusted research output and
cannot enter expected value, Kelly, risk-cap allocation or position sizing.

### 5.16 `ForecastCoherenceReceipt.v1`

Owner: `DOMAIN_POLICY`

```yaml
receipt_id: non-empty globally unique string
forecast_set_ref: ObjectRef
probability_status: CALIBRATED_OOS | ORDINAL_ONLY | UNKNOWN
mutual_exclusivity_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
exhaustiveness_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
other_path_present: true | false | UNKNOWN
probability_sum_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
nested_event_monotonicity_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
conditional_identity_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
cross_horizon_consistency_check: PASS | FAIL | UNKNOWN | NOT_APPLICABLE
status: PASS | FAIL | UNKNOWN
violation_refs: ordered array<ObjectRef>, minItems=0
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

Coherence PASS does not create calibration. `CALIBRATED_OOS` additionally
requires a current calibration record and probability-use authorization; that
state is unreachable in E0.

### 5.17 `UncertaintyDecompositionReceipt.v1`

Owner: `DOMAIN_EVALUATION`

```yaml
receipt_id: non-empty globally unique string
analysis_ref: ObjectRef
aleatoric_or_path_uncertainty_refs: ordered array<ObjectRef>, minItems=1
epistemic_or_model_uncertainty_refs: ordered array<ObjectRef>, minItems=1
data_missingness_uncertainty_refs: ordered array<ObjectRef>, minItems=0
point_in_time_uncertainty_refs: ordered array<ObjectRef>, minItems=0
regime_shift_uncertainty_refs: ordered array<ObjectRef>, minItems=0
shared_source_correlation_refs: ordered array<ObjectRef>, minItems=0
agent_disagreement_summary_ref: ObjectRef
decision_implication_refs: ordered array<ObjectRef>, minItems=1
non_reducible_unknown_refs: ordered array<ObjectRef>, minItems=0
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

Agent agreement, voting, eloquence or self-reported confidence cannot reduce
data missingness, point-in-time uncertainty, shared-source correlation or
irreducible market-path uncertainty to zero.

### 5.18 `RegimeShiftMonitorReceipt.v1`

Owner: `DOMAIN_EVALUATION`

```yaml
receipt_id: non-empty globally unique string
monitor_id: non-empty registered monitor ID
model_or_metric_ref: ObjectRef
observation_window_ref: ObjectRef
available_at_cutoff: UTC timestamp
change_statistic_refs: ordered array<ObjectRef>, minItems=1
threshold_policy_ref: ObjectRef
detected_status: NO_SHIFT | SUSPECTED | CONFIRMED | UNKNOWN
affected_probability_authorization_refs: ordered array<ObjectRef>, minItems=0
required_review_refs: ordered array<ObjectRef>, minItems=0
revocation_event_refs: ordered array<ObjectRef>, minItems=0
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

A regime signal may revoke a model/probability authorization and emit a bounded
review request. It may not emit an action, invalidate a market hypothesis,
activate a stage, close a lot or mutate strategic status. E0 has no probability
authorization to revoke, but still records the review and UNKNOWN boundary.

### 5.19 `AggregateHeadReceipt.v1`

Owner: `INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE`

```yaml
aggregate_head_receipt_id: non-empty globally unique string
aggregate_id: non-empty string
aggregate_type: AggregateType
aggregate_revision: nonnegative integer
state_ref: ObjectRef
state_digest: sha256
last_event_id: non-empty string
last_event_digest: sha256
previous_aggregate_head_receipt_ref: ObjectRef | null
reducer_version: semver
schema_version: semver
committed_at: UTC timestamp
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

Every aggregate command supplies the exact expected pair
`(aggregate_revision, state_digest)` and the corresponding prior head receipt.
`(aggregate_id, aggregate_revision)` is unique. A projection, snapshot, report
or prose summary is never an aggregate head.

### 5.20 `EventReplayCompatibilityManifest.v1`

Owner: `INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE`

```yaml
manifest_id: non-empty globally unique string
manifest_version: semver
genesis_contract_ref: ObjectRef
genesis_state_digest: sha256
first_event_sequence: nonnegative integer
last_event_sequence: nonnegative integer
expected_event_chain_head_digest: sha256
event_schema_version_refs: nonempty ordered array<ObjectRef>
reducer_version_refs: nonempty ordered array<ObjectRef>
upcaster_chain: ordered array<UpcasterEntry>, minItems=0
snapshot_manifest: ordered array<SnapshotEntry>, minItems=0
projection_cursor_set: ordered array<ProjectionCursorEntry>, minItems=0
full_replay_expected_digest: sha256
compatibility_test_refs: nonempty ordered array<ObjectRef>
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
manifest_digest: sha256
```

```yaml
UpcasterEntry:
  event_schema_id: non-empty registered schema ID
  from_event_schema_version: semver
  to_event_schema_version: semver
  input_event_schema_ref: ObjectRef
  output_event_schema_ref: ObjectRef
  upcaster_code_digest: sha256
  interpretation_only: true
SnapshotEntry:
  aggregate_id: non-empty string
  covered_revision: nonnegative integer
  snapshot_object_ref: ObjectRef
  snapshot_object_digest: sha256
  state_digest: sha256
  snapshot_schema_version: semver
ProjectionCursorEntry:
  consumer_id: non-empty string
  last_processed_event_ref: ObjectRef
  lag_status: CURRENT | LAGGING | UNKNOWN
```

Snapshots are non-authoritative caches. Full replay must equal
`full_replay_expected_digest`; upcasters interpret old immutable events and
never rewrite them. A `LAGGING` or `UNKNOWN` projection cannot supply a command
state head. Replay consumes exactly the declared genesis and inclusive event
sequence range, and must reproduce both the expected event-chain head and final
state digest.

### 5.21 `ReasoningStrategyContract.v1`

Owner: `DOMAIN_POLICY`

```yaml
reasoning_strategy_contract_id: non-empty globally unique string
role_id: token present in closed role registry
reasoning_strategy: non-empty registered strategy token
visible_input_refs: ordered array<ObjectRef>, minItems=1
hidden_or_blinded_input_class_refs: ordered array<ObjectRef>, minItems=0
required_evidence_output_refs: ordered array<ObjectRef>, minItems=1
required_falsifier_refs: ordered array<ObjectRef>, minItems=1
prohibited_claim_refs: ordered array<ObjectRef>, minItems=1
output_schema_ref: ObjectRef
tool_and_source_policy_ref: ObjectRef
token_budget: positive integer
latency_budget_ref: ObjectRef
failure_and_timeout_behavior_ref: ObjectRef
evaluation_rubric_ref: ObjectRef
blinding_proof_ref: ObjectRef | null
contract_version: semver
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
contract_digest: sha256
```

Every Agent output is an untrusted proposal. Schema validity, provenance,
point-in-time admissibility and deterministic constraints are evaluated after
the role returns. Agreement, voting and self-confidence provide no evidence
weight and no action authority.

### 5.22 `DecisionCriterionPolicy.v1`

Owner: `DOMAIN_POLICY`

```yaml
decision_criterion_policy_id: non-empty globally unique string
revision: positive integer
hard_constraints_precedence: true
calibrated_mode_rule: FROZEN_EXPECTED_UTILITY
ordinal_mode_rule: ROBUST_DOMINANCE_THEN_MINIMAX_REGRET
unknown_mode_rule: NO_NEW_RISK_WITH_OBLIGATION
calibrated_mode_authorization_required: true
ordinal_numeric_probability_use: FORBIDDEN
unknown_numeric_probability_use: FORBIDDEN
no_action_comparison_rule: COMPARE_AS_EXPLICIT_FEASIBLE_ACTION
tie_break_order: ordered unique array<LOWER_WORST_CASE_LOSS | LOWER_TAIL_LOSS | LOWER_COST | LOWER_TURNOVER | EARLIER_OBLIGATION_REVIEW | CANONICAL_ACTION_ID>, minItems=1
utility_function_ref: ObjectRef | null
robust_dominance_policy_ref: ObjectRef
regret_policy_ref: ObjectRef
opportunity_comparison_policy_ref: ObjectRef
maximum_supported_uncertainty_ref: ObjectRef
valid_from: UTC timestamp
valid_until: UTC timestamp
previous_revision_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
policy_digest: sha256
```

Every `DecisionContext`, `FeasibleActionSet`, `AgentSelection` and deterministic
selection validation binds the exact policy ref and digest. In E0,
`utility_function_ref=null`; the calibrated branch is unreachable because
there is no accepted probability authorization. The Selector may explain a
choice, but it may not invent a criterion, assign numerical probabilities,
change the tie-break order or choose outside the feasible set.

### 5.23 Calibration lineage interfaces

These three schemas make future calibration replayable but grant no E0
probability authority.

`ForecastIssuanceReceipt.v1` — Owner: `DOMAIN_EVALUATION`

```yaml
forecast_issuance_id: non-empty globally unique string
forecaster_ref: ObjectRef
event_definition_ref: ObjectRef
instrument_or_universe_scope_ref: ObjectRef
forecast_horizon_ref: ObjectRef
issued_at: UTC timestamp
available_at: UTC timestamp
probability_vector_ref: ObjectRef
probability_status_at_issuance: CALIBRATED_OOS | ORDINAL_ONLY | UNKNOWN
calibration_record_ref: ObjectRef | null
source_input_manifest_ref: ObjectRef
source_input_digest: sha256
outcome_due_at: UTC timestamp
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

`OutcomeResolutionReceipt.v1` — Owner: `DOMAIN_EVALUATION`

```yaml
outcome_resolution_id: non-empty globally unique string
forecast_issuance_ref: ObjectRef
event_definition_ref: ObjectRef
label_resolver_ref: ObjectRef
outcome_status: RESOLVED | PENDING | CENSORED | CONFLICTED
resolved_label_ref: ObjectRef | null
observation_window_start: UTC timestamp
observation_window_end: UTC timestamp
label_available_at: UTC timestamp | null
source_receipt_refs: ordered array<ObjectRef>, minItems=0
overlapping_horizon_group_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
receipt_digest: sha256
```

`CalibrationDatasetManifest.v1` — Owner: `DOMAIN_EVALUATION`

```yaml
calibration_dataset_manifest_id: non-empty globally unique string
dataset_version: semver
forecast_issuance_refs: ordered unique array<ObjectRef>, minItems=1
outcome_resolution_refs: ordered unique array<ObjectRef>, minItems=1
training_cutoff: UTC timestamp
evaluation_cutoff: UTC timestamp
pending_count: nonnegative integer
censored_count: nonnegative integer
resolved_count: nonnegative integer
overlap_handling_policy_ref: ObjectRef
cohort_and_regime_policy_ref: ObjectRef
label_leakage_check_ref: ObjectRef
dataset_type: INDEPENDENT_FROZEN_EVALUATION
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
manifest_digest: sha256
```

The manifest requires one-to-one issuance/outcome lineage, preserves pending
and censored forecasts, and forbids labels whose `available_at` exceeds the
evaluation cutoff. E0 materializes these schemas but accepts no instances into
decision state and keeps `CalibrationRegistry.calibration_record_refs=[]`.

### 5.24 Blind/post-proposal challenge amendments

The following amendments supersede the earlier cluster draft so the blind
experiment is representable without leaking a proposal:

```text
ChallengeMode =
  POST_PROPOSAL
  | BLIND_CONTEXT_ONLY
```

`ChallengeEnvelope.v1`:

```yaml
challenge_mode: ChallengeMode
proposal_ref: ObjectRef | null
reasoning_strategy_contract_ref: ObjectRef
role_context_view_ref: ObjectRef
challenge_claim_refs: nonempty ordered array<ObjectRef>
blinding_proof_ref: ObjectRef | null
challenge_digest: sha256
```

`ChallengeClaim.v1` uses `proposal_ref: ObjectRef | null`. In
`POST_PROPOSAL`, both the envelope and every claim require the exact proposal
ref and `blinding_proof_ref=null`. In `BLIND_CONTEXT_ONLY`, those proposal refs
are null, the immutable role view explicitly omits all proposal projections,
and a valid blinding proof is required. A blind claim can identify missing
paths, evidence conflicts, time-scale risks or required invariants from the
shared frozen context, but cannot claim a defect in proposal bytes it did not
see.

`RoleContextView.v1` keeps its nullable `proposal_ref` and adds:

```yaml
challenge_mode: POST_PROPOSAL | BLIND_CONTEXT_ONLY | NOT_APPLICABLE
reasoning_strategy_contract_ref: ObjectRef
```

For a blind Challenger, `proposal_ref=null`,
`challenge_mode=BLIND_CONTEXT_ONLY`, and the proposal projections are present
in the explicit omission list. For a post-proposal Challenger,
`proposal_ref` is non-null. Proposer and Selector use `NOT_APPLICABLE`.
The resolved role-input bundle and its digest must prove the same projection.

`ChallengeDisposition.v1` adds a non-null `proposal_ref`. The deterministic
disposition stage is where a frozen blind challenge and frozen proposal are
first joined. It may map applicable blind claims to the proposal, but it may
not rewrite either artifact. Candidate assembly consumes the disposition, not
an implied link inside a blind challenge.

### 5.25 `ProposedActionPlan.v1` amendment

Owner: `DOMAIN_DELIBERATION`

```yaml
proposed_action_plan_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
decision_cutoff: UTC timestamp
path_ref: ObjectRef
cross_timescale_control_envelope_ref: ObjectRef
strategic_delta_facet_ref: ObjectRef
position_facet_ref: ObjectRef
reentry_facet_ref: ObjectRef | null
execution_tactic_facet_ref: ObjectRef | null
registered_stage_ref: ObjectRef | null
action_intent: ActionIntent
protective_action_type: ProtectiveActionType
geometry_operation: GeometryOperation
atomic_effect_types: unique array<AtomicEffectType>
unknown_dependency_refs: ordered array<ObjectRef>, minItems=0
semantic_fingerprint: sha256
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
plan_digest: sha256
```

Facet constraints:

1. `EXIT_TO_REENTRY_PENDING` requires exactly one
   `CREATE_REENTRY_CONTRACT` effect in the same UnitOfWork and a surviving
   ACTIVE/CHALLENGED thesis.
2. No other action may carry `CREATE_REENTRY_CONTRACT`.
3. `ACTIVATE_REGISTERED_STAGE` and `REENTER_PARTIAL` require a non-null exact
   registered stage ref; its E0 lot role is CORE or TACTICAL.
4. An Agent HEDGE request remains in the immutable proposal archive, then is
   hard-rejected before candidate-bundle construction.
5. `EXIT_STRATEGIC` requires an independent accepted invalidation or terminal
   close receipt; protective EXIT alone is insufficient.
6. `REVISE_PROTECTION` requires a non-`NONE` protective action, exact barrier
   revision and ACK-ordering policy.
7. `NO_ACTION_WITH_OBLIGATION` requires zero position/risk increase, an exact
   next review clock and an unmet dependency or frozen no-opportunity reason.
8. No action token contains E0, paper, live, permission or executability
   semantics; those live only in the authority tuple and governance receipt.

### 5.26 Extended `PathPayoffMatrixSpec.v1`

Owner: `DOMAIN_POSITION`

```yaml
path_payoff_matrix_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
revision: positive integer
decision_cutoff: UTC timestamp
decision_horizon_ref: ObjectRef
planning_context_id: non-empty globally unique string
candidate_action_set_digest: sha256
row_path_refs: ordered array<ObjectRef>, minItems=5
column_action_plan_refs: ordered array<ObjectRef>, minItems=1
other_path_ref: ObjectRef
unknown_path_ref: ObjectRef
includes_other: true
includes_unknown: true
account_unit_ref: ObjectRef
total_account_risk_ref: ObjectRef
marginal_account_risk_ref: ObjectRef
cost_model_ref: ObjectRef
offline_risk_model_ref: ObjectRef
tail_policy_ref: ObjectRef
cell_refs: ordered array<ObjectRef>, exactly row_count * column_count
probability_status: CALIBRATED_OOS | ORDINAL_ONLY | UNKNOWN
probability_use_authorization_ref: ObjectRef | null
forecast_coherence_receipt_ref: ObjectRef | null
break_even_region_ref: ObjectRef
robust_dominance_receipt_ref: ObjectRef
regret_analysis_ref: ObjectRef
expected_value_ref: ObjectRef | null
kelly_size_ref: ObjectRef | null
previous_revision_ref: ObjectRef | null
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
matrix_digest: sha256
```

Every referenced `PathPayoffCell` additionally carries:

```yaml
path_ref: ObjectRef
action_plan_ref: ObjectRef
intermediate_state_refs: ordered array<ObjectRef>, minItems=1
continuation_action_refs: ordered array<ObjectRef>, minItems=0
triggered_stage_refs: ordered array<ObjectRef>, minItems=0
fill_outcome_ref: ObjectRef
slippage_ref: ObjectRef
fee_ref: ObjectRef
funding_status_ref: ObjectRef
offline_risk_ref: ObjectRef
terminal_outcome_ref: ObjectRef
account_pnl_interval_ref: ObjectRef
total_account_risk_ref: ObjectRef
marginal_account_risk_ref: ObjectRef
max_drawdown_ref: ObjectRef
stress_loss_ref: ObjectRef
tail_loss_ref: ObjectRef
time_to_outcome_ref: ObjectRef
data_status: COMPLETE | PARTIALLY_IDENTIFIED | UNKNOWN
assumption_refs: ordered array<ObjectRef>, minItems=0
cell_digest: sha256
```

`OTHER` is a residual market path; `UNKNOWN` is an epistemic/data state and is
not silently inserted into or removed from a probability simplex. E0 requires
`probability_use_authorization_ref=null`, `expected_value_ref=null` and
`kelly_size_ref=null`. It may compare conditional payoffs, break-even regions,
robust dominance and regret without pretending that ordinal ranks are numeric
probabilities. Every future branch remains conditional and unapproved.

The matrix is calculated before final selection. It binds the frozen
`planning_context_id` and complete `candidate_action_set_digest`, not a future
`RecedingHorizonPlan` identity. After selection, the plan copies both values,
references this matrix and chooses `current_authorized_action_ref` from the
matrix columns. This removes a forward identity cycle while preserving exact
lineage.

### 5.27 Extended `OpportunityCostReceipt.v1`

Owner: `DOMAIN_EVALUATION`

```yaml
receipt_id: non-empty globally unique string
candidate_ref: ObjectRef
evaluated_action_ref: ObjectRef
comparator_action_ref: ObjectRef
comparator_policy_ref: ObjectRef
comparator_policy_digest: sha256
comparator_frozen_at: UTC timestamp
decision_cutoff: UTC timestamp
comparator_recursive_feasibility_receipt_ref: ObjectRef
same_risk_and_authority_constraints: PASS
comparison_horizon_ref: ObjectRef
path_complexity_or_switch_count: nonnegative integer
fill_slippage_and_fee_model_ref: ObjectRef
support_overlap_status: PASS | PARTIAL | UNKNOWN
identification_contract_ref: ObjectRef | null
counterfactual_tier: OBSERVABLE_ACCOUNTING | MODEL_CONDITIONAL | CAUSAL_OPE
selected_value_interval_ref: ObjectRef
comparator_value_interval_ref: ObjectRef
conditional_difference_interval_ref: ObjectRef
uncertainty_interval_ref: ObjectRef
not_realized_loss: true
issued_before_selection: true
formal_metric_eligibility: ELIGIBLE | DIAGNOSTIC_ONLY | UNKNOWN
status: COMPLETE | PARTIALLY_IDENTIFIED | UNKNOWN
assumption_refs: ordered array<ObjectRef>, minItems=0
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
calculator_contract_version: semver
receipt_digest: sha256
```

The only formal comparator is a policy frozen no later than the decision cutoff
that was feasible under the same then-current data, risk, supervision and
authority constraints. A later-price-aware or clairvoyant policy may be
reported separately as a diagnostic upper bound, but cannot populate this
receipt, formal performance, incident fault or realized P&L.

This receipt is an ex-ante comparison calculated for each candidate before
selection; `candidate_ref` and `evaluated_action_ref` must point to that same
candidate/action pair. It contains no selected-action field and cannot be
rewritten after selection. Post-selection and post-outcome comparisons belong
to a later `EvaluationSnapshot` and never feed the original feasible set or
selection. `CAUSAL_OPE` is formally eligible only when
`support_overlap_status=PASS` and `identification_contract_ref` is non-null and
valid. `PARTIAL`, `UNKNOWN`, model-conditional and hindsight-only comparisons
are diagnostic or partially identified, never realized P&L.

### 5.28 Extended `UnitOfWorkBatch.v1`

Owner: `INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE`

```yaml
batch_id: non-empty globally unique string
commit_id: non-empty globally unique string
offline_run_id: non-empty string
decision_session_id: non-empty string
idempotent_command_id: non-empty globally unique string
idempotency_key: non-empty string
expected_previous_event_sequence: nonnegative integer | null
expected_previous_event_digest: sha256 | null
expected_aggregate_preconditions: nonempty ordered array<AggregatePrecondition>
accepted_artifact_refs: nonempty ordered array<ObjectRef>
receding_horizon_plan_ref: ObjectRef
authorized_first_step_action_ref: ObjectRef
atomic_effect_refs: ordered array<ObjectRef>, minItems=0
event_envelope_refs: nonempty ordered array<ObjectRef>
stored_event_refs: ordered array<ObjectRef>, exactly one per event envelope
new_aggregate_head_receipt_refs: nonempty ordered array<ObjectRef>
cursor_update_refs: ordered array<ObjectRef>, minItems=0
counterfactual_policy_ref: ObjectRef
portfolio_replay_result_ref: ObjectRef
first_event_sequence: nonnegative integer
last_event_sequence: nonnegative integer
new_event_chain_head_digest: sha256
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
batch_digest: sha256
```

`AggregatePrecondition`:

```yaml
aggregate_id: non-empty string
aggregate_type: AggregateType
expected_aggregate_revision: nonnegative integer
expected_state_digest: sha256
expected_aggregate_head_receipt_ref: ObjectRef
precondition_digest: sha256
```

The batch is compare-and-swap atomic on both the global event-chain head and
every aggregate precondition. Each modified aggregate produces exactly one new
`AggregateHeadReceipt`; all receipts bind the batch's actual last event for that
aggregate. Any mismatch makes the entire batch no-commit. Reuse of the same
idempotent command ID with the same input digest returns the original receipt;
reuse with different bytes is rejected. Only
`authorized_first_step_action_ref` may create current effects. Conditional
branches in the receding-horizon plan cannot appear in `atomic_effect_refs`.

### 5.29 New constraint and event registry entries

Required hard constraints:

- `CROSS_TIMESCALE_LEASE_CURRENT`
- `LOWER_TIMEFRAME_STRATEGIC_MUTATION_FORBIDDEN`
- `ACTION_FACETS_CLOSED_AND_COMPATIBLE`
- `BLIND_CHALLENGE_PROPOSAL_HIDDEN`
- `REENTRY_CREATION_ATOMIC_EFFECT_REQUIRED`
- `RECURSIVE_FEASIBILITY_PASS_REQUIRED_FOR_NEW_RISK`
- `RECEDING_HORIZON_FIRST_STEP_ONLY`
- `PROBABILITY_USE_AUTHORIZATION_REQUIRED`
- `CALIBRATION_LINEAGE_COMPLETE`
- `REGIME_SIGNAL_NO_TRADE_AUTHORITY`
- `AGGREGATE_EXPECTED_REVISION_AND_DIGEST_MATCH`
- `PROJECTION_NOT_COMMAND_HEAD`
- `OPPORTUNITY_COMPARATOR_FROZEN_AND_FEASIBLE`
- `DECISION_CRITERION_POLICY_BOUND`
- `REASONING_OUTPUT_UNTRUSTED`

Required unique event types:

- `CROSS_TIMESCALE_ENVELOPE_ISSUED`
- `CROSS_TIMESCALE_ENVELOPE_EXPIRED`
- `LOWER_TIMEFRAME_PROMOTION_REQUESTED`
- `RECURSIVE_FEASIBILITY_EVALUATED`
- `RECEDING_HORIZON_PLAN_RECORDED`
- `RECEDING_HORIZON_REVIEW_DUE`
- `CALIBRATION_REGISTRY_MATERIALIZED`
- `PROBABILITY_USE_AUTHORIZATION_REVOKED`
- `FORECAST_COHERENCE_EVALUATED`
- `UNCERTAINTY_DECOMPOSED`
- `REGIME_SHIFT_MONITORED`
- `REGIME_REVIEW_REQUESTED`
- `AGGREGATE_HEAD_COMMITTED`
- `EVENT_REPLAY_COMPATIBILITY_VERIFIED`
- `REASONING_STRATEGY_RESOLVED`
- `DECISION_CRITERION_POLICY_FROZEN`
- `FORECAST_ISSUED`
- `OUTCOME_RESOLUTION_RECORDED`
- `CALIBRATION_DATASET_FROZEN`
- `PROPOSED_ACTION_PLAN_RECORDED`
- `PATH_PAYOFF_MATRIX_CALCULATED`
- `OPPORTUNITY_COMPARATOR_EVALUATED`
- `UNIT_OF_WORK_COMMITTED`

`PROBABILITY_USE_AUTHORIZATION_REVOKED` is retained for replay compatibility;
in E0 no authorization-creation event exists and this event can only describe a
pre-existing future-compatible input rejected from current authority.

---

## 6. Common reducer protocol

Every Domain reducer implements:

```text
reduce(
  exact prior accepted aggregate head,
  one ordered admitted event,
  frozen policy/profile refs,
  decision cutoff
) -> ReducerResult
```

`ReducerResult` contains:

```yaml
status: APPLIED | NO_CHANGE | REJECTED | UNKNOWN
prior_state_ref: ObjectRef
next_state_candidate_ref: ObjectRef | null
transition_receipt_ref: ObjectRef | null
emitted_event_payload_refs: ordered array<ObjectRef>
typed_error_ref: ObjectRef | null
consumed_policy_refs: ordered array<ObjectRef>
result_digest: sha256
```

Rules:

1. `APPLIED` requires next state and transition receipt.
2. `NO_CHANGE` requires neither and records the evaluated event.
3. `REJECTED` requires a non-retryable typed error.
4. `UNKNOWN` requires a dependency or data error and cannot become ABSTAIN.
5. The prior state ref must equal the accepted chain head.
6. Reducers are pure and cannot write repositories.
7. Multiple aggregate results become visible only through one UnitOfWork.

---

## 7. StrategicEpisodeReducer

Owner: `DOMAIN_STRATEGIC`

### 7.1 Strategic transitions

| From | To | Exact required predicate |
|---|---|---|
| genesis | ACTIVE | strict genesis, accepted timeframe profile, registered hypothesis, premise set, hard invalidators, review clock and episode-risk allocation all valid |
| ACTIVE | ACTIVE | no qualified challenge/invalidation/terminal close; evidence delta may still create a new revision |
| ACTIVE | CHALLENGED | admitted evidence maps to an exact premise, has strategic authority or valid promotion, and creates next review clock |
| CHALLENGED | ACTIVE | the registered challenge is resolved by admitted evidence under the same or higher authority; no hard invalidator is active |
| ACTIVE/CHALLENGED | INVALIDATED | registered hard invalidator or accepted compound rule passes and `InvalidationReceipt` exists |
| ACTIVE/CHALLENGED | CLOSED | accepted horizon/opportunity/administrative close rule passes, exposure is FLAT, orders terminal, reconciliation complete, reentry terminal |
| INVALIDATED | CLOSED | exposure FLAT, orders terminal, reconciliation complete, all reentry contracts terminal |

Forbidden:

- `INVALIDATED → ACTIVE/CHALLENGED`;
- `CLOSED → any`;
- tactical/noise evidence directly changing strategic status;
- target hit, risk reduction, flatness or Agent confidence alone causing
  invalidation.

### 7.2 Exposure derivation

Exposure is derived after portfolio reconciliation:

```text
RECONCILE_PENDING
  if portfolio/order truth is unprovable or risk exceeds reference without authority

EXIT_PENDING
  else if accepted nonterminal exit exists

FLAT
  else if reconciled strategy quantity = 0 and no pending exposure quantity

RISK_REDUCED
  else if current gross frozen-risk exposure < immutable reference exposure

EXPOSED
  otherwise
```

When authoritative CORE quantity changes from positive to zero while strategic
status is ACTIVE or CHALLENGED, the same UnitOfWork must create a nonterminal
`ReentryContract`. Tactical residual exposure does not satisfy this invariant.

### 7.3 Errors and events

Errors:

- `STRATEGIC_PRIOR_HEAD_MISMATCH`
- `STRATEGIC_ILLEGAL_TRANSITION`
- `STRATEGIC_PREMISE_MAPPING_MISSING`
- `STRATEGIC_TIME_AUTHORITY_MISSING`
- `STRATEGIC_INVALIDATOR_UNREGISTERED`
- `STRATEGIC_REENTRY_ATOMICITY_MISSING`
- `STRATEGIC_CLOSE_PRECONDITION_FAILED`

Events:

- `EPISODE_OPENED`
- `STRATEGIC_STATE_ADVANCED`
- `STRATEGIC_CHALLENGED`
- `STRATEGIC_CHALLENGE_RESOLVED`
- `STRATEGIC_INVALIDATED`
- `STRATEGIC_CLOSED`
- `EXPOSURE_STATE_DERIVED`

---

## 8. StageReducer

Owner: `DOMAIN_POSITION`

### 8.1 Closed transition table

| From | To | Exact cause |
|---|---|---|
| none | REGISTERED | accepted frozen plan revision before first trigger/fill |
| REGISTERED | REGISTERED (`NO_CHANGE`) | trigger/dependency UNKNOWN or not yet passed and stage not expired; emit an evaluation artifact, not a transition receipt |
| REGISTERED | ELIGIBLE | trigger, predecessor, evidence, time authority, current forward RR, risk and supervision all PASS |
| REGISTERED | EXPIRED | expiry reached before eligibility |
| REGISTERED | CANCELLED | a pre-registered cancellation predicate passes |
| REGISTERED | REJECTED | invalid schema, unregistered action, HEDGE, risk breach or forbidden permission |
| ELIGIBLE | ARMED | exact stage candidate selected, governance passes E0, pending risk reserved |
| ELIGIBLE | REGISTERED | trigger no longer passes but stage remains valid and policy allows waiting |
| ELIGIBLE | EXPIRED/CANCELLED/REJECTED | corresponding terminal cause |
| ARMED | COUNTERFACTUAL_FILLED | matching reports a counterfactual fill candidate and the portfolio reducer accepts the exact fill/quantity into counterfactual position truth |
| ARMED | ELIGIBLE | no fill and order expires/cancels while stage remains eligible |
| ARMED | EXPIRED/CANCELLED/REJECTED | corresponding terminal cause, including protection atomicity failure before fill |
| COUNTERFACTUAL_FILLED | PROTECTED | complete simulated protection and reconciliation PASS atomically |
| PROTECTED | PARTIALLY_CLOSED | reconciled residual quantity is positive and below filled quantity |
| PROTECTED/PARTIALLY_CLOSED | CLOSED | reconciled residual quantity reaches zero |

Terminal states `CLOSED`, `EXPIRED`, `CANCELLED`, and `REJECTED` have no outgoing
transition.

Stage state advances only from admitted plan, matching and portfolio events.
Agent text, a `StageTransitionReceipt` by itself, or a later projection cannot
advance it. `COUNTERFACTUAL_FILL_RECORDED` remains matching evidence;
`STAGE_COUNTERFACTUAL_FILLED` is emitted only after the portfolio aggregate has
accepted and reconciled that evidence.

### 8.2 Activation gates

`REGISTERED → ELIGIBLE` requires all:

1. strategic status `ACTIVE`;
2. exact stage registered before trigger;
3. trigger current and not expired;
4. predecessor and dependencies pass;
5. PIT and time authority pass;
6. independent stop, target/checkpoint, invalidator and horizon exist;
7. current-price forward payoff/RR satisfies the frozen policy;
8. reserved stage risk is sufficient;
9. account, episode, instrument and portfolio stress gates pass;
10. cost, liquidity, margin and venue-model gates pass;
11. supervision mode permits the stage;
12. atomic simulated entry/protection can be represented;
13. E0 scope is counterfactual and non-dispatchable.

Any real ADD authority check fails in E0.

### 8.3 Errors and events

Errors:

- `STAGE_UNREGISTERED`
- `STAGE_PRIOR_RECEIPT_MISMATCH`
- `STAGE_PREDECESSOR_FAILED`
- `STAGE_TRIGGER_UNKNOWN`
- `STAGE_EXPIRY_REACHED`
- `STAGE_TERMINAL_REUSE`
- `STAGE_FORWARD_RR_INELIGIBLE`
- `STAGE_RISK_CAP_FAILED`
- `STAGE_SUPERVISION_FORBIDDEN`
- `STAGE_PROTECTION_ATOMICITY_UNKNOWN`
- `STAGE_HEDGE_FORBIDDEN_E0`
- `STAGE_REAL_ADD_AUTHORITY_NONE`

Events:

- `STAGE_REGISTERED`
- `STAGE_ELIGIBLE`
- `STAGE_ARMED`
- `STAGE_COUNTERFACTUAL_FILLED`
- `STAGE_PROTECTED`
- `STAGE_PARTIALLY_CLOSED`
- `STAGE_CLOSED`
- `STAGE_EXPIRED`
- `STAGE_CANCELLED`
- `STAGE_REJECTED`

---

## 9. RiskBudgetReducer

Owner: `DOMAIN_POSITION`

### 9.1 Transitions

| Operation | Required result |
|---|---|
| `ALLOCATE` | owner-authorized episode allocation fits account cap and reserves |
| `RESERVE_STAGE` | move available episode capacity to an exact REGISTERED/ELIGIBLE stage reservation |
| `PENDING_RISK` | move stage reservation to pending order risk without increasing total planned risk |
| `OPEN_RISK` | replace pending/reserved risk by reconciled open worst-case risk and costs |
| `REALIZE_LOSS` | add realized loss permanently; it cannot be recycled |
| `REALIZE_COST` | add fee/funding/slippage cost permanently when modeled/observed |
| `CLOSE_RISK` | remove reconciled open risk after close; realized loss/cost remain |
| `RELEASE_UNUSED_STAGE` | release only an untriggered expired/cancelled reservation under frozen policy |
| `RECONCILE` | recompute open/pending risk from authoritative portfolio truth; inconsistencies fail closed |

No operation may:

- raise account or episode caps;
- subtract unrealized profit;
- reset realized loss or cost;
- move risk between episodes without owner authorization;
- hide exogenous or pending exposure through netting;
- recycle a stopped-out tranche allocation under E0.

### 9.2 Errors and events

Errors:

- `RISK_ACCOUNT_ENVELOPE_MISSING`
- `RISK_EPISODE_ALLOCATION_MISSING`
- `RISK_COMPONENT_UNIT_MISMATCH`
- `RISK_ACCOUNT_CAP_BREACH`
- `RISK_EPISODE_CAP_BREACH`
- `RISK_STAGE_RESERVATION_BREACH`
- `RISK_UNREALIZED_PROFIT_RECYCLING`
- `RISK_REALIZED_LOSS_RESET`
- `RISK_CROSS_EPISODE_REALLOCATION_UNAUTHORIZED`
- `RISK_PORTFOLIO_TRUTH_UNKNOWN`

Events:

- `EPISODE_RISK_ALLOCATED`
- `STAGE_RISK_RESERVED`
- `STAGE_RISK_RELEASED_UNUSED`
- `PENDING_RISK_UPDATED`
- `OPEN_RISK_UPDATED`
- `RISK_LOSS_REALIZED`
- `RISK_COST_REALIZED`
- `RISK_RECONCILED`

---

## 10. SupervisionReducer

Owner: `DOMAIN_POSITION`

### 10.1 Transitions

| From | To | Required predicate |
|---|---|---|
| any | SUPERVISED | current time is inside a frozen supervised window |
| SUPERVISED | UNATTENDED_PROTECTED | frozen unattended window begins and protection, ACK freshness, data freshness, account consistency and worst-case loss all PASS |
| SUPERVISED | NO_NEW_RISK | operator becomes unavailable and unattended protection cannot be proven |
| UNATTENDED_PROTECTED | SUPERVISED | next supervised window begins |
| UNATTENDED_PROTECTED | NO_NEW_RISK | any required protection/ACK/data/account/loss predicate becomes FAIL or UNKNOWN |
| NO_NEW_RISK | SUPERVISED | supervised window begins and account/data consistency pass |
| NO_NEW_RISK | UNATTENDED_PROTECTED | a later frozen unattended window begins and every protection predicate passes |

Semantics:

- `SUPERVISED` permits normal E0 proposal evaluation.
- `UNATTENDED_PROTECTED` permits only pre-registered stages with atomically
  modeled protection.
- `NO_NEW_RISK` permits hold, tighten, reduce, exit, reconciliation and kill;
  it forbids stage activation and reentry.
- A supervision transition never changes strategic status.
- Scheduler catch-up cannot retrospectively manufacture supervision.

Errors:

- `SUPERVISION_WINDOW_MISSING`
- `SUPERVISION_WINDOW_OVERLAP`
- `SUPERVISION_PROTECTION_UNKNOWN`
- `SUPERVISION_ACK_STALE`
- `SUPERVISION_DATA_STALE`
- `SUPERVISION_ACCOUNT_UNRECONCILED`
- `SUPERVISION_WORST_CASE_LOSS_UNKNOWN`
- `SUPERVISION_NEW_RISK_FORBIDDEN`

Events:

- `SUPERVISION_MODE_CHANGED`
- `UNATTENDED_PROTECTION_FAILED`
- `NO_NEW_RISK_ENTERED`

---

## 11. GeometryReducer

Owner: `DOMAIN_GEOMETRY`

### 11.1 Analysis geometry

| From | To | Required cause |
|---|---|---|
| none | DRAFT | immutable geometry candidate created |
| DRAFT | PROPOSED | candidate passes schema and PIT checks |
| PROPOSED | ACTIVE_ANALYSIS | deterministic governance activation receipt |
| ACTIVE_ANALYSIS | STALE_FOR_NEW_DECISIONS | regime/anchor/validity policy invalidates use for new decisions |
| ACTIVE_ANALYSIS | SUPERSEDED | a new analytical geometry becomes active |
| ACTIVE_ANALYSIS | EXPIRED | validity clock ends |

### 11.2 Executable barrier

E0 simulates the lifecycle but never creates a venue-dispatchable object:

| From | To | Required cause |
|---|---|---|
| NONE | PENDING_VENUE_ACK | replacement/request represented in replay |
| PENDING_VENUE_ACK | ACTIVE_PROTECTION | simulated ACK ordering proves activation before crossing |
| PENDING_VENUE_ACK | REJECTED/ACK_TIMEOUT/HALTED_RECONCILE | corresponding simulated result |
| ACTIVE_PROTECTION | SUPERSEDED | old/new replacement is atomic and ACK precedes crossing |
| ACTIVE_PROTECTION | TRIGGERED | barrier crossing matched |
| ACTIVE_PROTECTION | CANCELLED | lot closes or accepted cancellation is proven |

Rules:

- analytical staleness never cancels active protection;
- stop may tighten but never loosen after PositionLock;
- horizon may shorten but never lengthen;
- target extension remains denied unless Core T-023 gates and ACK pass; in E0
  uncalibrated value gates deny it;
- if crossing precedes replacement ACK, the old barrier executes.

Errors:

- `GEOMETRY_PRIOR_VERSION_MISMATCH`
- `GEOMETRY_ANALYSIS_TRANSITION_ILLEGAL`
- `GEOMETRY_PROTECTION_TRANSITION_ILLEGAL`
- `GEOMETRY_STOP_LOOSEN_FORBIDDEN`
- `GEOMETRY_HORIZON_EXTENSION_FORBIDDEN`
- `GEOMETRY_T023_GATE_UNCALIBRATED`
- `GEOMETRY_ACK_MISSING`
- `GEOMETRY_OLD_BARRIER_ALREADY_CROSSED`

Events:

- `ANALYSIS_GEOMETRY_ACTIVATED`
- `ANALYSIS_GEOMETRY_STALED`
- `ANALYSIS_GEOMETRY_SUPERSEDED`
- `ANALYSIS_GEOMETRY_EXPIRED`
- `PROTECTION_REPLACEMENT_REQUESTED`
- `PROTECTION_ACTIVATED`
- `PROTECTION_TRIGGERED`
- `PROTECTION_REPLACEMENT_FAILED`

---

## 12. ReentryReducer

Owner: `DOMAIN_REENTRY`

### 12.1 Closed transition table

| From | To | Required cause |
|---|---|---|
| none | OPEN | authoritative CORE quantity becomes zero while strategy remains ACTIVE/CHALLENGED |
| OPEN | DUE | earliest review or mandatory review clock reached |
| OPEN/DUE/ELIGIBLE | CANCELLED_INVALIDATED | strategic status becomes INVALIDATED |
| OPEN/DUE/ELIGIBLE | CANCELLED_CLOSED | episode closes without invalidation |
| DUE | ELIGIBLE | frozen pullback, continuation or time-review route passes |
| DUE | OPEN | UNKNOWN deferral is frozen and deferral count remains below maximum |
| ELIGIBLE | DUE | current-cutoff predicates no longer pass but contract remains reviewable |
| OPEN/DUE/ELIGIBLE | EXPIRED | expiry or un-deferrable UNKNOWN |
| ELIGIBLE | EXECUTED | new THI, risk, governance and reconciled minimum CORE fill all pass |

Terminal states have no outgoing transitions.

At `latest_review_at`, exactly one evaluation, allowed deferral, or terminal
result is mandatory. Silence and repeated WAIT are illegal.

Errors:

- `REENTRY_ATOMIC_OPEN_MISSING`
- `REENTRY_PRIOR_STATE_MISMATCH`
- `REENTRY_REVIEW_OVERDUE`
- `REENTRY_DEFERRAL_LIMIT_MISSING`
- `REENTRY_DEFERRAL_LIMIT_EXCEEDED`
- `REENTRY_CURRENT_ELIGIBILITY_FAILED`
- `REENTRY_NEW_THI_MISSING`
- `REENTRY_RISK_PERMISSION_MISSING`
- `REENTRY_CORE_FILL_UNRECONCILED`

Events:

- `REENTRY_OPENED`
- `REENTRY_DUE`
- `REENTRY_ELIGIBLE`
- `REENTRY_DEFERRED`
- `REENTRY_EXPIRED`
- `REENTRY_CANCELLED_INVALIDATED`
- `REENTRY_CANCELLED_CLOSED`
- `REENTRY_EXECUTED`

---

## 13. Candidate, constraint and selection reducers

The Agent cluster C0 definitions remain canonical subject to the intent changes
in Section 4.6.

Required deterministic sequence:

```text
exact AggregateHeadReceipt set
+ current CrossTimescaleControlEnvelope
+ current ReasoningStrategyContract set
+ current regime/probability/uncertainty state
→ role-specific AgentProposalEnvelope
→ blind or post-proposal ChallengeEnvelope according to experiment arm
→ ChallengeDisposition
→ ProposedActionPlan facet validation
→ CandidateBundleAssembler
→ PathPayoffMatrixSpec and CandidateCalculationReceipt for every candidate
→ RecursiveFeasibilityReceipt for every candidate
→ ConstraintVerdictSet
→ FeasibleActionSet
→ AgentSelection
→ GovernanceAssessmentReceipt
→ RecedingHorizonPlan for the exact selected candidate
→ UnitOfWorkBatch containing only the selected current action
```

`DecisionContext.v1`, `FeasibleActionSet.v1` and `AgentSelection.v1` each add:

```yaml
decision_criterion_policy_ref: ObjectRef
decision_criterion_policy_digest: sha256
```

The three refs and digests must be byte-identical. The deterministic validator
applies the frozen probability-status branch, hard-constraint precedence and
tie-break order before governance; an Agent explanation cannot replace or
amend that evaluation.

Rules:

- candidate assembly recognizes only the closed `ActionIntent`,
  `ProtectiveActionType`, `GeometryOperation` and `AtomicEffectType` facets;
- every facet must be allowed by the current cross-timescale lease;
- every requested stage activation references one exact `StageSpec`;
- a HEDGE request is retained in the proposal archive and receives a hard
  rejection before `CandidateBundleAssembler` emits any candidate;
- every theory-defined meaningful action is assembled unless a typed hard or
  unknown-dependency constraint applies;
- only `HARD+FAIL` and candidate-local
  `UNKNOWN_DEPENDENCY+UNKNOWN` remove a candidate;
- new-risk candidates require recursive-feasibility PASS; UNKNOWN is removal
  from the current feasible set, not a safe-pass conversion;
- only an exact current ProbabilityUseAuthorization can permit numeric
  probabilities in EV or position sizing; E0 has none;
- soft and informational findings cannot remove a candidate;
- Selector must choose one exact feasible-set member;
- Selector and deterministic validation consume the same frozen
  `DecisionCriterionPolicy`;
- the receding-horizon plan is materialized after selection and authorizes only
  that selected member as its current first step;
- `NO_ACTION_WITH_OBLIGATION` is always constructed when its dependencies are
  available;
- repeated selection of no-action while non-no-action feasible members exist is
  an audit failure predicate, not an automatic safety success;
- no Agent or deterministic component may turn a failed model call into a flat
  or exit decision.

Errors:

- `ACTION_INTENT_UNKNOWN`
- `PROTECTIVE_ACTION_TYPE_UNKNOWN`
- `GEOMETRY_OPERATION_UNKNOWN`
- `ACTION_FACET_INCOMPATIBLE`
- `CANDIDATE_STAGE_REF_MISSING`
- `CANDIDATE_THEORY_ACTION_OMITTED`
- `CANDIDATE_HEDGE_FORBIDDEN_E0`
- `CONSTRAINT_UNREGISTERED`
- `CONSTRAINT_SOFT_REMOVAL_FORBIDDEN`
- `FEASIBLE_SET_INCOMPLETE`
- `FEASIBLE_SET_NO_ACTION_MISSING`
- `SELECTOR_OUTSIDE_FEASIBLE_SET`
- `SELECTION_CRITERION_POLICY_MISMATCH`
- `SELECTION_ABSTAIN_OBLIGATION_MISSING`
- `RECURSIVE_FEASIBILITY_NOT_PASS`
- `RECEDING_HORIZON_FUTURE_BRANCH_UNAUTHORIZED`
- `PROBABILITY_USE_UNAUTHORIZED_E0`

Events remain precommit work artifacts until the final UnitOfWork:

- `PROPOSAL_RECORDED`
- `CHALLENGE_RECORDED`
- `CHALLENGE_DISPOSITION_RECORDED`
- `CANDIDATES_ASSEMBLED`
- `CANDIDATES_CALCULATED`
- `CONSTRAINTS_EVALUATED`
- `FEASIBLE_SET_BUILT`
- `AGENT_SELECTION_RECORDED`
- `GOVERNANCE_ASSESSED`

---

## 14. Trading calendar and scheduler contract

### 14.1 `TradingSessionCalendarProfile.v1`

Owner: `DOMAIN_TIME_AUTHORITY`

```yaml
calendar_profile_id: non-empty globally unique string
instrument_id: non-empty string
venue_id: non-empty string
market_clock_type: CONTINUOUS_24_7 | SESSION_CALENDAR
iana_timezone: non-empty IANA timezone string
weekly_session_specs: ordered array<WeeklySessionSpec>, minItems=0
holiday_closure_refs: ordered array<ObjectRef>, minItems=0
special_session_refs: ordered array<ObjectRef>, minItems=0
halt_event_source_ref: ObjectRef | null
corporate_action_source_ref: ObjectRef | null
bar_alignment_policy: UTC_EPOCH | SESSION_OPEN
calendar_source_ref: ObjectRef
valid_from: UTC timestamp
valid_until: UTC timestamp
profile_digest: sha256
```

`CONTINUOUS_24_7` requires empty weekly/holiday/special arrays and
`UTC_EPOCH` alignment. `SESSION_CALENDAR` requires at least one weekly session
and an authoritative calendar source.

`WeeklySessionSpec`:

```yaml
weekday: MON | TUE | WED | THU | FRI | SAT | SUN
local_open_time: HH:MM:SS
local_close_time: HH:MM:SS
session_label: non-empty string
```

### 14.2 `ExpectedSlotPolicy.v1`

Owner: `DOMAIN_TIME_AUTHORITY`

```yaml
expected_slot_policy_id: non-empty globally unique string
calendar_profile_ref: ObjectRef
wake_interval_ref: ObjectRef
bar_timeframe_refs: nonempty ordered array<ObjectRef>
strategic_review_clock_refs: nonempty ordered array<ObjectRef>
grace_period_ref: ObjectRef
source_lateness_policy_ref: ObjectRef
gap_terminal_policy: STOP_AT_FIRST_UNRECOVERABLE_BAR
policy_digest: sha256
```

Expected wake, bar and strategic-review slots are separate. Closed sessions,
registered holidays and halts are not missing slots.

### 14.3 SchedulerReducer

For each wake:

1. load accepted calendar and expected-slot policy;
2. enumerate expected wake/review/bar slots after committed cursors;
3. compare completed slots;
4. create a `ScheduleGapReceipt` for every actual gap;
5. fetch every closed bar after each barrier cursor;
6. verify continuity and corporate-action normalization;
7. replay every contiguous bar in source order;
8. advance each barrier cursor only through its verified contiguous prefix;
9. advance wake cursor after terminal gap classification;
10. advance strategic-review cursor only for real or fully PIT-recoverable
    reviews;
11. commit cursors, gaps, barrier results and portfolio state atomically.

Gap status:

```text
DETECTED
| BAR_RECOVERED
| RECOVERED_FULL
| PARTIAL_SOURCE_GAP
| UNRECOVERABLE
```

If a closed bar is missing, later bars are not applied for that
instrument/timeframe. Missing non-bar evidence may permit barrier replay but
censors the missed strategic review.

Errors:

- `SCHEDULE_CALENDAR_PROFILE_MISSING`
- `SCHEDULE_EXPECTED_SLOT_POLICY_MISSING`
- `SCHEDULE_SLOT_ENUMERATION_AMBIGUOUS`
- `SCHEDULE_BAR_GAP`
- `SCHEDULE_CURSOR_NONCONTIGUOUS`
- `SCHEDULE_CORPORATE_ACTION_UNKNOWN`
- `SCHEDULE_STRATEGIC_REVIEW_UNRECOVERABLE`

Events:

- `WAKE_ASSESSED`
- `SCHEDULE_GAP_DETECTED`
- `SCHEDULE_GAP_TERMINAL`
- `BAR_CONTINUITY_VERIFIED`
- `BARRIER_CURSOR_ADVANCED`
- `WAKE_CURSOR_ADVANCED`
- `STRATEGIC_REVIEW_CURSOR_ADVANCED`

---

## 15. Event-driven matching contract

### 15.1 `MatchingPolicyProfile.v1`

Owner: `DOMAIN_MATCHING`

```yaml
matching_policy_id: non-empty globally unique string
instrument_id: non-empty string
venue_id: non-empty string
calendar_profile_ref: ObjectRef
price_tick_ref: ObjectRef
quantity_step_ref: ObjectRef
contract_multiplier_ref: ObjectRef
currency_ref: ObjectRef
same_bar_priority: STOP_FIRST
gap_fill_policy: CONSERVATIVE_OPEN_PLUS_SLIPPAGE
limit_touch_policy: REQUIRE_CROSS_BEYOND_ONE_TICK | ACTUAL_FILL_ONLY
partial_fill_policy: ACTUAL_OR_VOLUME_MODEL_ONLY
volume_participation_cap_ref: ObjectRef | null
fee_policy_ref: ObjectRef
slippage_policy_ref: ObjectRef
funding_policy_ref: ObjectRef | null
corporate_action_policy_ref: ObjectRef | null
policy_digest: sha256
```

If a required multiplier, tick, quantity step, cost or slippage policy is
missing, payoff is UNKNOWN and the dependent new-risk candidate is removed.

### 15.2 `BarrierOrderSpec.v1`

Owner: `DOMAIN_MATCHING`

```yaml
barrier_order_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
lot_ref: ObjectRef | null
stage_ref: ObjectRef | null
geometry_ref: ObjectRef | null
barrier_type: KILL | ACCOUNT_MISMATCH | STOP_MARKET | PROTECTION_REPAIR | STRUCTURE_EXIT_MARKET | TARGET_LIMIT | TIMEOUT | ENTRY_STOP_MARKET | ENTRY_LIMIT | BARRIER_UPDATE
side: BUY | SELL
quantity_ref: ObjectRef
remaining_quantity_ref: ObjectRef
trigger_price_ref: ObjectRef | null
limit_price_ref: ObjectRef | null
reduce_only: boolean
active_from: UTC timestamp
active_until: UTC timestamp
time_in_force: GTC | IOC | FOK | UNTIL_TIME
matching_policy_ref: ObjectRef
protection_priority: nonnegative integer
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
spec_digest: sha256
```

At least one of lot or stage ref is non-null except for an account-wide `KILL`
or `ACCOUNT_MISMATCH`. New-risk entry specs require a stage ref and non-null
geometry. Protective/exit specs require
`reduce_only=true` and non-null geometry except `KILL`, `ACCOUNT_MISMATCH`, and
an account-wide reconciliation exit, whose trigger authority is the referenced
risk/account event.

### 15.3 `ClosedBar.v1`

Owner: `DOMAIN_MATCHING`

```yaml
instrument_id: non-empty string
venue_id: non-empty string
timeframe_ref: ObjectRef
session_id: non-empty string
open_time: UTC timestamp
close_time: UTC timestamp
open_ref: ObjectRef
high_ref: ObjectRef
low_ref: ObjectRef
close_ref: ObjectRef
volume_ref: ObjectRef | null
trade_count_ref: ObjectRef | null
corporate_action_adjustment_ref: ObjectRef | null
observed_at: UTC timestamp
available_at: UTC timestamp
ingested_at: UTC timestamp
source_committed_at: UTC timestamp
source_commit_receipt_ref: ObjectRef
source_revision: non-empty string
lineage_digest: sha256
bar_digest: sha256
```

### 15.4 Barrier ordering

Proven same-source causal order is preserved. For simultaneous or unorderable
events:

```text
KILL/ACCOUNT_MISMATCH
→ STOP_MARKET
→ PROTECTION_REPAIR
→ STRUCTURE_EXIT_MARKET
→ TARGET_LIMIT
→ TIMEOUT
→ ENTRY_STOP_MARKET
→ ENTRY_LIMIT
→ BARRIER_UPDATE
→ NO_CHANGE
```

When OHLC proves both stop and target were touched but not their order:

- mark `AMBIGUOUS_BARRIER_ORDER`;
- authoritative replay applies `STOP_FIRST`;
- also compute favorable and adverse diagnostic bounds;
- never substitute the favorable bound for authoritative accounting.

### 15.5 Fill rules

1. Actual V1 fill records, when lineage-valid, are authoritative for observed
   V1 accounting only.
2. For a long-position stop sell:
   - if `bar.open <= stop`, base fill is `bar.open`;
   - otherwise a stop touch uses the stop price;
   - adverse slippage is then applied.
3. For a short-position stop buy:
   - if `bar.open >= stop`, base fill is `bar.open`;
   - otherwise a stop touch uses the stop price;
   - adverse slippage is then applied.
4. A limit target with no actual fill requires price to cross beyond the limit
   by at least one registered tick. Mere touch is no fill under the default E0
   policy.
5. New-risk limit entry follows the same cross-beyond-one-tick rule.
6. A long entry stop fills from `bar.open` plus adverse slippage when the bar
   gaps above the stop, otherwise from the stop plus adverse slippage when
   crossed. A short entry stop applies the symmetric rule.
7. Partial fill is admitted only from an actual fill or a frozen volume model
   with a participation cap. Otherwise fill quantity is UNKNOWN; new risk is not
   opened.
8. Fee, slippage and modeled funding are applied once. Missing funding remains
   UNKNOWN and is not silently zero.
9. Gap, queue and intrabar uncertainty is retained in diagnostic intervals.
10. A cancel/replace becomes effective only after its ACK event. If an old
   barrier crosses first, the old barrier executes.
11. Matching never reads future bars or a later Agent decision.

Errors:

- `MATCHING_POLICY_MISSING`
- `MATCHING_MULTIPLIER_UNKNOWN`
- `MATCHING_TICK_OR_STEP_UNKNOWN`
- `MATCHING_COST_POLICY_UNKNOWN`
- `MATCHING_BAR_LINEAGE_INVALID`
- `MATCHING_BARRIER_INACTIVE`
- `MATCHING_LIMIT_TOUCH_INSUFFICIENT`
- `MATCHING_PARTIAL_FILL_UNIDENTIFIED`
- `MATCHING_AMBIGUOUS_BARRIER_ORDER`
- `MATCHING_CANCEL_REPLACE_ACK_UNKNOWN`
- `MATCHING_FUTURE_BAR_FORBIDDEN`

Events:

- `BARRIER_EVALUATED`
- `STOP_HIT`
- `TARGET_HIT`
- `TIMEOUT_HIT`
- `ENTRY_TRIGGERED`
- `AMBIGUOUS_BARRIER_ORDER_RECORDED`
- `COUNTERFACTUAL_FILL_RECORDED`
- `PARTIAL_FILL_RECORDED`
- `ORDER_NO_FILL_RECORDED`
- `CANCEL_REPLACE_ACK_RECORDED`
- `PORTFOLIO_RECONCILIATION_REQUIRED`

---

## 16. Legacy V1 mapping contract

### 16.1 Boundary

V1 is a read-only evidence and characterization source. V1 cycles never become
an accepted V2 state chain. V2 historical replay begins from an explicit E0
strict-genesis contract or, for a different project with an accepted V2 chain,
an authorized migration receipt. Missing V2 fields are never synthesized from
later outcomes.

Cycle `0025` is excluded from decision replay because it has frozen input but no
submitted Agent decision.

### 16.2 `LegacyCycleEnvelope.v1`

Owner: `INFRASTRUCTURE_LEGACY_ADAPTER`

```yaml
legacy_cycle_envelope_id: non-empty globally unique string
legacy_run_id: non-empty string
cycle_id: integer, minimum=1, maximum=24
freeze_cutoff: UTC timestamp
decision_submitted_at: UTC timestamp
source_manifest_ref: ObjectRef
source_manifest_digest: sha256
ledger_head_ref: ObjectRef
transaction_head_ref: ObjectRef
analysis_artifact_refs: ordered array<ObjectRef>, minItems=1
decision_artifact_refs: ordered array<ObjectRef>, minItems=1
market_snapshot_refs: ordered array<ObjectRef>, minItems=1
agent_actual_input_refs: ordered array<ObjectRef>, minItems=0
portfolio_before_ref: ObjectRef
portfolio_after_ref: ObjectRef
lot_refs: ordered array<ObjectRef>, minItems=0
order_refs: ordered array<ObjectRef>, minItems=0
fill_refs: ordered array<ObjectRef>, minItems=0
report_refs: ordered array<ObjectRef>, minItems=0
field_mapping_entries: ordered array<LegacyFieldMappingEntry>, minItems=1
gap_entries: ordered array<LegacyGapEntry>, minItems=0
integrity_verdict: PASS | FAIL
physical_existence_claim: SOURCE_ARTIFACTS_ONLY
usage_scope: FORENSIC_REPLAY
envelope_digest: sha256
```

`LegacyFieldMappingEntry`:

```yaml
source_artifact_ref: ObjectRef
source_json_pointer: JSON Pointer
target_schema_id: non-empty string
target_json_pointer: JSON Pointer
usage_class: ACTUAL_AGENT_INPUT | COUNTERFACTUAL_MARKET_REPLAY | EVALUATION_ONLY
quality_state: OBSERVED | DERIVED | PROXY | MISSING | CONFLICTED | STALE | NOT_APPLICABLE
observed_at: UTC timestamp | null
available_at: UTC timestamp | null
ingested_at: UTC timestamp | null
source_committed_at: UTC timestamp | null
physical_existence_at_source_time: PROVEN | NOT_CLAIMED | DISPROVEN
lineage_digest: sha256
```

`LegacyGapEntry`:

```yaml
gap_id: non-empty globally unique string
cycle_id: integer, minimum=1, maximum=24
object_class: MARKET_BAR | NON_BAR_EVIDENCE | STRATEGIC_STATE | INTENT | GEOMETRY | REENTRY | ORDER_ACK | FILL | COST | FUNDING | ACCOUNT
source_pointer: JSON Pointer | null
required_by_refs: ordered array<ObjectRef>, minItems=0
gap_status: UNKNOWN_LEGACY_UNDECLARED | MISSING_SOURCE_ARTIFACT | RECONSTRUCTED_UNVERIFIED | CONFLICTED | NOT_APPLICABLE
permitted_use: NONE | EVALUATION_ONLY | COUNTERFACTUAL_BOUND_ONLY
reason_codes: nonempty ordered array<string>
gap_digest: sha256
```

### 16.3 Mapping rules

- Historical Agent analysis and action attribution uses only
  `ACTUAL_AGENT_INPUT`.
- Later provider archives may enter only `COUNTERFACTUAL_MARKET_REPLAY`.
- Reconstructed state, geometry, intent or reentry objects are
  `EVALUATION_ONLY` and cannot alter the V1 arm.
- V1 lot/order/fill/account objects retain their original identifiers and
  exogenous-versus-strategy attribution.
- Missing quantities, private orders, ACKs, queue position, funding and
  intrabar order remain gaps.
- Legacy adapter verifies manifests, ledger, transactions, reports and object
  digests and performs zero writes under the V1 root.
- A failed integrity verdict prevents all replay consumption.

Errors:

- `LEGACY_CYCLE_OUT_OF_SCOPE`
- `LEGACY_CYCLE_0025_DECISION_ABSENT`
- `LEGACY_MANIFEST_DIGEST_MISMATCH`
- `LEGACY_LEDGER_OR_TRANSACTION_INVALID`
- `LEGACY_FIELD_MAPPING_AMBIGUOUS`
- `LEGACY_PHYSICAL_EXISTENCE_UNPROVEN`
- `LEGACY_WRITE_ATTEMPT_FORBIDDEN`

---

## 17. Plugin registry contract

### 17.1 E0 lifecycle

```text
STATIC_BUILTIN_PLUGINS_ONLY
NO_DYNAMIC_INSTALL
NO_DYNAMIC_UPDATE
NO_NETWORK
NO_FILESYSTEM
NO_PROCESS
NO_ENVIRONMENT
NO_AMBIENT_CLOCK
NO_RANDOMNESS
```

Lifecycle:

```text
DEFINED_IN_CODE
→ REGISTERED_IN_FROZEN_REGISTRY
→ ACTIVATED_FOR_EXACT_REPLAY_BUNDLE
→ INVOKED_WITHIN_BUDGET
→ DEACTIVATED_AT_RUN_END
```

### 17.2 `FrozenPluginRegistry.v1`

Owner: `DOMAIN_POLICY`

```yaml
plugin_registry_id: non-empty globally unique string
registry_version: semver
entries: ordered unique array<PluginRegistryEntry>, minItems=0
required_plugin_ids: unique array<string>
optional_plugin_ids: unique array<string>
feature_flag_refs: ordered array<ObjectRef>, minItems=0
default_failure_policy: RETURN_UNKNOWN
dynamic_operations: FORBIDDEN
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
registry_digest: sha256
```

An empty registry is legal only when every required policy is implemented as a
resolved deterministic kernel component and the manifest declares no required
plugin. `required_plugin_ids` and `optional_plugin_ids` are disjoint and their
union equals the plugin IDs in `entries`.

### 17.3 `PluginRegistryEntry`

The entry is materialized as `$defs/PluginRegistryEntry` inside
`frozen_plugin_registry.v1`:

```yaml
plugin_id: non-empty string
plugin_type: EVIDENCE_SOURCE | NORMAL_RANGE_POLICY | EVENT_QUALIFICATION_POLICY | RISK_POLICY | HORIZON_POLICY | CALIBRATION_METHOD | ROBUST_OPTIMIZATION | ENSEMBLE_FORECAST | CHANGE_POINT_MONITOR
plugin_version: semver
code_digest: sha256
input_schema_refs: nonempty unique array<ObjectRef>
output_schema_refs: nonempty unique array<ObjectRef>
permission_scope: READ_FROZEN_INPUT_ONLY
required: boolean
instrument_profile_refs: unique array<ObjectRef>
maximum_calls: nonnegative integer
maximum_input_bytes: nonnegative integer
deterministic_timeout_result: UNKNOWN
failure_result: UNKNOWN
mock_fixture_ref: ObjectRef
independent_test_id: non-empty string
feature_flag_ref: ObjectRef
entry_digest: sha256
```

### 17.4 `PluginInvocationReceipt.v1`

Owner: `DOMAIN_POLICY`

```yaml
plugin_entry_ref: ObjectRef
replay_bundle_ref: ObjectRef
input_refs: nonempty ordered array<ObjectRef>
input_digest: sha256
verdict: PASS | REJECT | UNKNOWN
reason_codes: ordered array<string>
evidence_refs: ordered array<ObjectRef>
available_at: UTC timestamp
call_index: nonnegative integer
budget_verdict: PASS | FAIL
output_ref: ObjectRef | null
output_digest: sha256 | null
receipt_digest: sha256
```

Plugin rules:

- plugin cannot write Domain state, access repositories, dispatch action,
  self-promote evidence or add mechanism IDs;
- required plugin failure makes only its declared dependent candidates UNKNOWN
  unless the dependency contract declares `SESSION_NO_COMMIT`;
- optional plugin failure cannot remove unrelated candidates;
- role skills are not plugins and plugin receipts cannot substitute for
  `SkillResolutionReceipt`;
- deterministic kernel components are not plugins and use
  `KernelComponentResolutionReceipt`.
- E0 keeps the plugin registry empty. The four future method classes
  (`CALIBRATION_METHOD`, `ROBUST_OPTIMIZATION`, `ENSEMBLE_FORECAST`,
  `CHANGE_POINT_MONITOR`) are interface reservations only; activating any of
  them requires a new contract/policy digest and cannot be disguised as a
  generic risk policy.

---

## 18. Data requirements and UNKNOWN propagation

### 18.1 Required E0 data classes

| Data class | Minimum source | Missing result |
|---|---|---|
| prior accepted V2 heads | exact `AggregateHeadReceipt` revision/digest pairs plus global UnitOfWork event-chain head, or strict genesis | session no-commit |
| decision cutoff and clock | trusted time authority | session no-commit |
| dataset type and source cohort | frozen dataset/replay manifest, independent of authority tuple | dataset consumption denied |
| cross-timescale authority | current strategic state and unexpired `CrossTimescaleControlEnvelope` | safe degradation only; no new risk or strategic mutation |
| ordered closed bars | frozen archive with lineage | cursor stops at first missing bar |
| instrument calendar/profile | frozen policy registry | scheduler unknown/no strategic advance |
| account equity/risk envelope | frozen E0 fixture or lineage-valid legacy account snapshot | new-risk candidates removed |
| lot/order/fill state | lineage-valid legacy artifacts or E0 replay state | reconcile pending |
| quantity/multiplier/tick/step | instrument profile | payoff/risk unknown; new risk removed |
| stop/target/horizon geometry | registered stage/lot geometry | dependent candidate removed |
| fee/slippage/gap policy | matching/cost profile | payoff/risk unknown; new risk removed |
| funding | observed/model policy | UNKNOWN, never silently zero |
| protection/ACK state | actual legacy record or E0 simulated ordering | unattended new risk denied |
| numeric path probabilities | current calibration record + coherence PASS + `ProbabilityUseAuthorization` | `ORDINAL_ONLY` or `UNKNOWN`; no EV/Kelly/sizing; E0 always follows this path |
| opportunity comparator | policy frozen by decision cutoff and recursive-feasibility PASS under identical constraints | no formal opportunity-cost receipt; diagnostic upper bound only |
| participant psychology | not identifiable from public aggregates | explicit unavailable construct with competing proxy hypotheses |

### 18.2 Unknown propagation

1. Missing prior state, cutoff, authority or schema: session no-commit.
2. Missing data required only by one candidate: remove that candidate with
   `UNKNOWN_DEPENDENCY`; retain unrelated candidates.
3. Missing probability calibration: retain path payoff and break-even
   boundaries; prohibit EV, Kelly and edge claims.
4. Missing execution detail: return an identified interval or UNKNOWN; never
   insert zero cost or favorable fill.
5. Missing strategic evidence does not invalidate a thesis.
6. Missing Agent role does not become NO_ACTION; session is incomplete.
7. Missing optional support evidence preserves the candidate with an UNKNOWN
   support field.
8. Conflicted or stale data is not silently downgraded to MISSING; its quality
   state remains explicit.
9. Later outcomes may enter evaluation only after their own availability time.
10. An UNKNOWN field can be narrowed only by a newly admitted lawful source and
    creates a new revision; history is unchanged.
11. Agent agreement, optimizer convergence and coherence PASS cannot promote
    `ORDINAL_ONLY` or `UNKNOWN` to `CALIBRATED_OOS`.
12. A suspected/confirmed regime shift can request review and revoke probability
    use; it cannot produce an action or strategic invalidation.

### 18.3 Lawful acquisition routes

- public market data: official venue/provider API or immutable official archive;
- private orders, fills, ACKs and account state: official read-only account API
  or official export, explicit user authorization and immutable local capture;
- corporate-action/session calendars: official venue or recognized calendar
  source with version and availability time;
- unavailable psychology: remain an inference target, never a fact.

---

## 19. A–I ablation and acceptance contract

### 19.1 Frozen arms

All arms receive the same:

- point-in-time replay bundle;
- policy/profile versions;
- model proposal stream where the arm uses Agent proposals;
- matching and cost policy;
- account and exogenous-position baseline;
- event chronology.

Arms:

| Arm | Cumulative enabled delta |
|---|---|
| A | frozen V1 behavior characterization |
| B | A + persistent `StrategicEpisodeState` |
| C | B + CORE/TACTICAL lot-role separation |
| D | C + four-path post-target review |
| E | D + mandatory `ReentryContract` |
| F | E + expiring/rebuildable dynamic geometry |
| G | F + scheduler continuity and event-driven matching |
| H | G + PathPayoffMatrix, account/episode risk envelopes and staged positions |
| I | H + SupervisionAvailabilityContract and unattended safety |

Arm A has two required outputs:

1. `A_OBSERVED_V1`, the immutable historical behavior;
2. `A_REPLAYED_V1`, the characterization implementation.

The replayed result must match every identifiable V1 state/action/fill. A
non-identifiable field remains UNKNOWN and is not optimized to match the
outcome.

The three-Agent cluster versus one strong Agent is a separate equal-budget
experiment. It is not arm J and does not change A–I mechanics.

The eleven theory-basis contracts are governance contracts, not an additional
ablation arm. Their first applicable arm is frozen as follows:

| Contract | Applicable arms |
|---|---|
| `AggregateHeadReceipt`, `EventReplayCompatibilityManifest`, extended `UnitOfWorkBatch` | B–I |
| `CrossTimescaleControlEnvelope` | B–I |
| `ReasoningStrategyContract` | every arm/experiment that invokes an Agent |
| `UncertaintyDecompositionReceipt`, `RegimeShiftMonitorReceipt` | B–I |
| empty `CalibrationRegistry`, probability authorization prohibition, `ForecastCoherenceReceipt` | D–I |
| extended `OpportunityCostReceipt` | D–I |
| `RecursiveFeasibilityReceipt`, `RecedingHorizonPlan`, extended `PathPayoffMatrixSpec` | H–I |

An arm may omit a not-yet-applicable feature, but it may not weaken the
point-in-time, UNKNOWN, authority-tuple, aggregate-concurrency or no-forward-
branch-authorization rules needed by the feature it does include.

### 19.2 Required scenarios

At minimum:

1. trend continuation after rebound;
2. rebound failure;
3. false breakout;
4. range;
5. deep pullback and recovery;
6. no-pullback acceleration;
7. event gap through stop;
8. initial stage fails immediately;
9. confirmation stage triggers and reverses;
10. trend stage becomes forward-RR ineligible after appreciation;
11. target and stop touched in one bar;
12. missed wake with an intermediate trigger and reversal;
13. geometry replacement ACK race;
14. CORE exit with surviving thesis and reentry obligation;
15. continuation reentry without preferred pullback;
16. supervised to unattended transition;
17. unattended stale data or lost protection;
18. tactical signal attempting strategic invalidation;
19. feasible non-no-action candidates with repeated Agent no-action selection;
20. missing required Agent role or bootstrap state;
21. expired cross-timescale lease with a fast-layer strategic mutation attempt;
22. recursive feasibility FAIL and UNKNOWN after an otherwise attractive add;
23. conditional future branch submitted without current-data reapproval;
24. coherent forecasts without calibration or probability-use authorization;
25. suspected/confirmed regime shift attempting to invalidate or trade;
26. aggregate revision match with state-digest mismatch, and the converse;
27. lagging projection or snapshot used as a command head;
28. frozen feasible opportunity comparator versus a hindsight-only comparator;
29. forged stage receipt attempting to create a fill or quantity;
30. nonempty E0 calibration registry or probability-authorization instance;
31. unanimous Agent output attempting to erase PIT/data/path uncertainty;
32. atomic strategic exit-to-reentry commit with one deliberately failed effect.

SNDK is a seen functional fixture only. At least one independently frozen,
non-SNDK scenario suite is mandatory. Synthetic scenarios establish contract
behavior, not market prediction.

### 19.3 Hard functional gates

All must pass:

- prior-head/stateless recomputation violations: `0`;
- future-data acceptance: `0`;
- unauthorized HEDGE/ADD/paper/live dispatch: `0`;
- mixed action/protection/geometry token or permission-suffixed action: `0`;
- unregistered stage activation: `0`;
- StageTransitionReceipt-created fill/lot/quantity: `0`;
- account/episode/stage risk-cap breach acceptance: `0`;
- unrealized-profit risk subsidy: `0`;
- supervision change altering strategic status: `0`;
- unattended unprotected new risk: `0`;
- lower-timeframe direct invalidation: `0`;
- expired/mismatched control envelope authorizing new risk or strategic
  mutation: `0`;
- surviving-thesis CORE-zero without reentry contract: `0`;
- overdue nonterminal reentry without receipt: `0`;
- missing intermediate barrier: `0` when the source data are complete;
- cursor jump across a missing bar: `0`;
- soft constraint deleting a candidate: `0`;
- Selector outside feasible set: `0`;
- selector/feasible-set/decision-context criterion-policy mismatch: `0`;
- blind-Challenger proposal leakage: `0`;
- omitted theory-defined meaningful action: `0`;
- missing role substituted by another role/prompt: `0`;
- partial UnitOfWork visibility: `0`;
- aggregate revision-only or digest-only compare-and-swap acceptance: `0`;
- lagging projection/snapshot accepted as command head: `0`;
- receding-horizon future branch committed without current reapproval: `0`;
- recursive-feasibility FAIL/UNKNOWN authorizing new risk: `0`;
- regime monitor directly emitting action/invalidation: `0`;
- E0 calibration record or probability-use authorization accepted: `0`;
- incomplete forecast/outcome/calibration lineage accepted: `0`;
- ordinal/UNKNOWN probability used in EV, Kelly or position sizing: `0`;
- opportunity-cost receipt using a non-frozen or infeasible comparator: `0`;
- opportunity cost booked as realized loss: `0`;
- Agent agreement reducing non-reducible uncertainty: `0`;
- identical deterministic inputs producing different kernel/replay digests: `0`;
- deterministic compiler/replay equality: `100%`;
- mandatory path/payoff cell coverage including OTHER/UNKNOWN: `100%`;
- E0 object accepted by paper/live adapter: `0`.

### 19.4 Separate metric groups

Functional:

- transition and constraint correctness;
- state/digest continuity;
- scheduler/matching fidelity;
- candidate-set completeness.

Behavioral:

- dynamic-analysis-to-action conversion;
- feasible-set diversity;
- feasible no-action rate;
- eligible-flat duration;
- registered/eligible/selected/filled stage counts;
- qualified reentry/stage omission;
- under-participation duration;
- late-chase rejection.

Economic:

- realized and unrealized P&L separated;
- fees, modeled funding and slippage separated;
- account/episode/stage risk utilization;
- maximum drawdown, stress loss and tail loss;
- turnover and cost;
- opportunity capture against a pre-registered benchmark.

Only extended `OpportunityCostReceipt` instances whose comparator was frozen and
feasible at the decision cutoff enter formal opportunity-capture metrics.
Hindsight and clairvoyant comparators are separately labelled diagnostic bounds.

Agent-cluster:

- dynamic path coverage;
- material challenge coverage;
- same-input proposal and selection variance;
- role failure correlation;
- model calls, tokens, latency and cost;
- equal-budget quality delta versus one strong Agent;
- blind-Challenger versus post-proposal-Challenger delta;
- correct proposal degraded by consensus;
- shared-source correlated hallucination;
- persuasive weak-agent contamination;
- role-overreach, timeout and partial-completion localization by typed receipt.

The Agent experiment is a separate factorial comparison, never arm J:

1. one strong Agent;
2. current three-role cluster with the Challenger seeing the proposal;
3. the same cluster with a blind Challenger that receives no Proposer output
   until its independent critique is frozen.

All three receive equal decision data, tools, source policy, total token budget,
wall-clock budget and model class. Blinding is proven by
`ReasoningStrategyContract` input projections and byte digests. Outputs from one
experiment cannot enter another experiment's proposal, challenge or selection.

The original 12-checkpoint cluster exercise is an engineering smoke test only
and cannot choose the second-round topology. Topology selection uses a
separately frozen paired holdout policy:

- at least 32 paired decision sessions spanning every canonical scenario class
  and at least one independently frozen non-SNDK cohort;
- identical inputs, model class, total token/call budget, tools, latency budget
  and deterministic post-processing;
- zero additional safety, state, PIT, authority or role-overreach failures;
- at least five percentage points improvement in dynamic candidate coverage or
  at least ten percentage points improvement in material challenge coverage,
  without reducing the other measure;
- a paired uncertainty interval for the frozen action-quality rubric whose
  lower bound is nonnegative;
- complete cost, timeout and missing-role accounting.

When these conditions select a cluster, that exact topology and reasoning
strategy digests are used. If the strong single Agent is better, it is used. If
the evidence is insufficient or the paired interval is unresolved, topology
selection is `INCONCLUSIVE_USE_SINGLE_AGENT`; this does not claim the cluster
inferior and does not by itself fail an otherwise valid E0-to-paper gate. No
topology is chosen by a favorable sample mean alone.

No behavioral or economic metric may compensate for a failed hard functional
gate. Opportunity cost is never booked as realized cash loss. Without calibrated
probabilities, no EV, Kelly, predictive superiority or profitability claim is
allowed.

---

## 20. Implementation dependency order

Implementation must proceed in this order:

1. materialize the amended schema identity set, including all eleven theory-basis
   objects and the three action facets;
2. materialize schema, owner, error, event, constraint and plugin/policy
   registries twice independently; compute the set from artifacts and require
   byte equality rather than asserting a schema count;
3. implement event compatibility/upcasters, `AggregateHeadReceipt`, per-
   aggregate revision+digest compare-and-swap and the sole UnitOfWork;
4. implement pure Strategic, Exposure, Stage, Risk, Supervision, Geometry and
   Reentry reducers plus `CrossTimescaleControlEnvelope`;
5. implement the empty E0 calibration registry, probability-authorization
   prohibition, forecast coherence, uncertainty decomposition and regime-review
   path without any trade transition;
6. implement `ProposedActionPlan` facet validation, candidate assembly,
   calculators, constraints and fixed proposal fixtures;
7. implement extended path-payoff/opportunity-cost calculation, recursive
   feasibility and receding-horizon first-step compilation;
8. implement calendar, expected-slot, scheduler and event-driven matching;
9. implement offline portfolio replay as sole counterfactual lot/fill/quantity
   authority and bind stage lifecycle receipts to its reconciliations;
10. implement the read-only V1 adapter and cycles 1–24 replay bundles;
11. execute deterministic A–I synthetic and historical replay without Agent
    calls;
12. create the project-local AGENTS template and role skill sources, each bound
    to a `ReasoningStrategyContract`;
13. connect one-shot Agent adapters after `SkillResolutionReceipt` validation;
14. execute isolated cold-start, equal-budget single/cluster and blind/post-
    proposal Challenger experiments;
15. publish hard-gate, gap, compatibility and residual-risk reports.

No role skill is a prerequisite for testing deterministic mechanics. Fixed
typed proposal fixtures are used first.

---

## 21. E0 completion boundary

V2 E0 is functionally complete only when:

- every schema and registry in the amended set is materialized and digest-bound;
- the independently calculated registry/tree schema-ID sets are equal;
- every reducer transition and error above has positive and negative tests;
- every authoritative object has one owner, mock and independent test surface;
- legacy reads perform zero V1 writes;
- A–I use point-in-time inputs and preserve UNKNOWN fields;
- E0 accepts an empty calibration registry and zero probability-use
  authorizations;
- rolling plans commit only the current first step;
- formal opportunity-cost records use only frozen feasible comparators;
- every changed aggregate is protected by revision+state-digest compare-and-
  swap and produces a new aggregate-head receipt;
- every hard functional gate passes;
- the same frozen deterministic input replays to the same digests;
- all governance, replay and commit outputs bind:

```yaml
system_mode: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
```

Gate passage establishes engineering and functional closure only. It does not
establish calibration, prediction, causal validity, profitability, paper
readiness, live readiness or automation authority.

The following remain explicitly outside E0 and require separate accepted
contracts and authorization:

- real ADD;
- HEDGE accounting and action;
- instrument-specific empirical calibration;
- dynamic plugin installation;
- paper/live adapters and orders;
- automation creation or activation;
- promotion into Core theory.

---

## 22. Freeze statement

This file is the canonical implementation contract for the new V2 E0 namespace.
It resolves candidate-document naming and interface conflicts without rewriting
those source documents.

Any change to an enum, transition, object owner, matching rule, unknown policy,
legacy mapping, plugin permission or A–I arm creates a new version of this file,
new schema/registry digests and a new replay lineage. It cannot edit historical
V1 or previously committed V2 objects.
