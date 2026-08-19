# Theory Agent V2 — Agent Cluster and Deterministic Kernel Design v0.1

> Status: `HISTORICAL_C0_BASELINE_SUPERSEDED_FOR_C1_BY_IMPLEMENTATION_CONTRACT_V1_0`
>
> Scope: offline, counterfactual-only architecture and reusable collaboration
> contract.
>
> Authority: `NONE` for paper trading, live trading, account mutation,
> automation activation, theory promotion, or accepted historical rewrite.
>
> This document does not modify Core Trading Theory v2.1, frozen V1 prompts,
> cycles 1–25, portfolio state, ledgers, transaction artifacts, thresholds, or
> automation-2.
>
> Canonical supersession: the portable-tree list, original 118-schema equality,
> earlier action/constraint/event vocabularies, A–G arms and historical gate
> counts in this document are baseline inputs only. C1 compiles the resolved
> schema identities, registries, A–I arms and gates from
> `THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0.md`. The machine equality is:
>
> ```text
> canonical implementation contract resolved identities
> == SchemaRegistry identities
> == portable schema-tree identities
> ```
>
> This document remains authoritative for role isolation, typed handoff,
> one-shot topology, skill packaging and the single-UnitOfWork boundary except
> where the canonical implementation contract explicitly amends it.

---

## 1. Decision

The proposed direction is feasible and is the preferred architecture for V2,
provided that the system is split by **kind of responsibility**, not by
arbitrary numbers of Agents.

The correct separation is:

```text
dynamic, underdetermined market reasoning
    → bounded Agent roles

point-in-time facts, arithmetic, risk, state and authority
    → deterministic kernel

accepted decision history
    → one atomic UnitOfWork commit chain
```

An Agent cluster can broaden the candidate path set, preserve competing
hypotheses, challenge local reasoning, and select among already feasible action
bundles. It cannot turn unobserved facts into observed facts, make an
uncalibrated probability calibrated, sign its own authority, or replace the
unique committed state chain.

The cluster is therefore an **adaptive deliberation layer inside the existing
four-layer architecture**, not a fifth code layer and not a committee that
votes on truth.

---

## 2. What this design solves

The design directly targets the known failure pattern:

```text
one hourly prompt
→ re-analysis from current snapshot
→ recent evidence dominates
→ prior strategy becomes prose instead of state
→ conservative action is easier than opportunity capture
→ exit has a lower burden than reentry
→ flat becomes an absorbing state
```

The replacement pattern is:

```text
accepted prior state + frozen point-in-time context
→ one coherent multi-path Agent proposal
→ one bounded Agent challenge
→ deterministic challenge disposition
→ Domain-compatible candidate bundles
→ deterministic payoff/risk calculations
→ deterministic hard-constraint filtering
→ Agent selection within the feasible set
→ deterministic governance and offline replay
→ one atomic governance commit
```

This allows the Agent to use its dynamic capabilities without allowing any
model turn to change risk limits, fabricate continuity, or directly execute an
order.

---

## 3. What this design does not claim

The following claims are explicitly forbidden:

1. More Agents automatically produce better market predictions.
2. Majority agreement is evidence that a hypothesis is true.
3. Role separation makes model errors independent.
4. A skill file creates memory, data access, calibration, or trading authority.
5. An `AGENTS.md` file is a substitute for a persisted state store.
6. A cold-start Agent can reconstruct omitted private fills or historical
   intent.
7. Offline replay success proves profitability.
8. The cluster may trade SNDK, HYPE, or any current instrument.

If all roles use the same model family, the same sources, and substantially the
same framing, their errors can remain highly correlated. The purpose of the
cluster is controlled division of responsibility and better coverage, not
manufactured certainty.

---

## 4. Canonical filename and purpose

The project governance filename is:

```text
AGENTS.md
```

not `agent.md`.

Its purpose is to define:

- project-wide authority boundaries;
- the mandatory bootstrap order;
- the accepted artifact locations;
- the role roster and handoff protocol;
- the sole commit authority;
- hard prohibitions;
- the current evidence level and execution mode.

It must **not** contain:

- mutable current positions;
- the latest hypothesis as free text;
- live credentials;
- large duplicated theory documents;
- unversioned thresholds;
- hidden assumptions about a prior chat;
- a blanket instruction that all Agents should agree;
- permission to modify paper/live systems.

Mutable state belongs in versioned state artifacts. Theory belongs in canonical
theory documents. `AGENTS.md` contains pointers and required digests, not
duplicated truth.

---

## 5. Four-layer mapping

No new code layer is introduced.

| Code layer | Cluster responsibility |
|---|---|
| Presentation | CLI/report views, audit views, operator decisions, cold-start diagnostics |
| Application | bootstrap, context freeze, role dispatch, challenge orchestration, Domain candidate-assembly orchestration, calculation/constraint orchestration, selection orchestration, UnitOfWork command |
| Domain | path proposal contracts, strategic state rules, geometry/exposure/position/reentry/execution strategies, payoff/risk rules, constraint semantics, state reducers |
| Infrastructure | model adapters, source adapters, artifact store, event store, schema registry, replay adapter, UnitOfWork implementation |

Agents are Infrastructure model adapters invoked by Application use cases and
constrained by Domain contracts. An Agent is not itself an architecture layer.

---

## 6. Responsibility boundary

### 6.1 Work assigned to Agents

Agents may perform tasks that remain open-ended after all admissible facts have
been frozen:

- generate several causally distinct market paths;
- identify which prior premise each new observation supports or challenges;
- compare regime interpretations;
- propose dynamic geometry candidates;
- propose CORE/TACTICAL role combinations under the current E0 contract;
- flag a possible HEDGE need only as a typed facet/unresolved future
  capability, never as a current `CandidateBundle`, lot, or permission;
- propose staged position and reentry candidates;
- propose execution tactics compatible with the attention mode;
- explain trade-offs among feasible action bundles;
- select one feasible bundle or explicitly retain no-action;
- identify omitted alternatives, reasoning collapse, or role overreach.

### 6.2 Work assigned to the deterministic kernel

The deterministic kernel exclusively owns:

- `observed_at` and `available_at` admission;
- source lineage and content digests;
- bar continuity and event ordering;
- accepted state-chain head;
- schema validation;
- arithmetic and unit conversion;
- fees, slippage and stress-loss calculation;
- path-payoff matrix calculation from frozen inputs;
- episode, instrument and account risk accounting;
- hard risk and permission constraints;
- candidate compatibility predicates;
- authority snapshots;
- reducer transitions;
- event and receipt construction;
- compare-and-commit;
- offline replay and metric calculation.

### 6.3 Work no component may infer

Neither Agents nor deterministic modules may infer:

- unavailable private account events;
- participant psychology from public aggregates as an identified fact;
- calibrated path probabilities without a calibration artifact;
- missing historical stop/target rules;
- missing quantities or fills;
- future bars at the decision cutoff;
- paper/live authority from offline acceptance;
- user risk appetite from recent profit or loss.

These remain `UNKNOWN`, `UNAVAILABLE`, or `PARTIALLY_IDENTIFIED`.

---

## 7. Minimal cluster topology

Independent review rejected the first draft's seven-role topology as
unnecessarily complex. The minimum complete E0 topology is three one-shot Agent
roles plus one deterministic kernel:

```mermaid
flowchart TD
    B["Immutable Bootstrap<br/>Evidence + session inputs + DecisionContext"]
    P["Proposer Agent<br/>coherent multi-path candidate set"]
    H["Challenger Agent<br/>one-pass falsifier and omission review"]
    K["Deterministic Kernel<br/>PIT, calculation, hard constraints"]
    S["Selector Agent<br/>choose only inside feasible set"]
    G["Deterministic Governance"]
    R["Offline Counterfactual Replay"]
    U["UnitOfWork<br/>sole physical commit authority"]

    B --> P
    P --> H
    H --> K
    K --> S
    S --> G
    G --> R
    R --> U
```

There is no Coordinator Agent in the authoritative architecture. The
Application workflow owns the fixed DAG, timeouts, joins and typed failures.

The deterministic path-risk engine is intentionally **not an Agent role**. Its
output must be reproducible from frozen inputs.

The six business responsibilities remain separate Domain modules:

- market path;
- strategic state;
- geometry;
- exposure/position management;
- reentry;
- execution tactics.

They are emitted as typed facets of a coherent proposal rather than being
assigned to six Agents by default. This avoids fragmenting one trade plan into
incompatible partial opinions and avoids recreating a discussion committee.

Additional specialist proposer Agents may be tested later as optional fan-out,
but only after a same-budget experiment demonstrates unique source-bound value.
They cannot vote, gain new authority, or become required merely because more
roles appear sophisticated.

For C1–C3:

```text
specialist_proposer_fanout = OFF
```

Enabling it requires a new design version and cannot be done by manifest-only
configuration.

---

## 8. Role contracts

### 8.1 Proposer Agent

**Purpose**

Produce a coherent, bounded candidate portfolio spanning path, state, geometry,
position, reentry and execution facets.

**Consumes**

- a role-scoped immutable `RoleContextView`;
- admitted `EvidenceBundle`;
- exact accepted prior state and open obligations;
- prior paths, invalidators and pending observations;
- account/episode/attention envelopes;
- theory, policy and role-contract digests.

**Produces**

- `AgentProposalEnvelope`.

The envelope must include:

- primary path;
- at least one materially distinct alternative when supported;
- null/no-change path;
- `OTHER/UNKNOWN` handling;
- exact prior-state delta proposal;
- CORE/TACTICAL position candidates; any HEDGE need remains a typed unresolved
  capability outside the current candidate set;
- dynamic geometry candidates;
- staged position, target, reentry and execution facets when applicable;
- source-bound support and falsifier predicates;
- uncertainty and missing dependencies;
- explicit proposed-plan IDs and semantic fingerprints.

**Unique authority**

- create dynamic candidate plans within the `AutonomyEnvelope`.

**Must not**

- calculate canonical payoff, risk, fees or margin;
- judge hard feasibility or permission;
- assign numerical probability without calibration lineage;
- write accepted state;
- select the final action;
- directly read mutable repositories or refresh evidence;
- use future data;
- bypass T-033, `PROBE_ONLY`, risk or execution authority.

The Proposer is broad only across dynamic market facets. It does not also
calculate, validate, audit, select, commit or execute; therefore it is not the
old all-powerful hourly prompt.

### 8.2 Challenger Agent

**Purpose**

Perform one bounded adversarial review of the frozen proposal.

**Consumes**

- the same context digest as the Proposer;
- frozen `AgentProposalEnvelope`;
- role contract and challenge taxonomy.

**Produces**

- `ChallengeEnvelope`.

Typed challenge categories include:

- premise conflict;
- claimed hard or soft falsifier;
- omitted competing path;
- missing source or dependency;
- state-continuity break;
- time-scale overreach;
- exit/reentry asymmetry;
- action-space collapse risk;
- unknown coercion;
- geometry/position inconsistency;
- role overreach.

**Unique authority**

- identify challenges and missing coverage without rewriting the proposal.

**Must not**

- veto a candidate;
- modify proposal bytes;
- add a final executable candidate;
- choose an action;
- change confidence or evidence weight;
- perform canonical calculations;
- commit state;
- vote for or against the Proposer.

The Challenger cannot itself determine that the proposal is structurally
invalid. The deterministic kernel emits `ChallengeDisposition`.

Only a challenge that maps to a pinned, machine-verifiable schema or invariant
and receives:

```text
VERIFIED_HARD_STRUCTURAL_DEFECT
```

may terminate the current session with `REPROPOSAL_REQUIRED`.

A market preference, possible omitted mechanism, or unsupported hard label is
classified `SOFT` or `INFORMATIONAL`; it cannot delete a candidate or end the
session. A new session with an explicit `supersedes_session_id` may consume a
verified structural challenge. The Agents do not debate inside the same
session.

### 8.3 Selector Agent

**Purpose**

Choose one exact bundle from the deterministic `FeasibleActionSet`.

**Consumes**

- same immutable context;
- frozen proposal and challenge;
- `DeterministicCalculationBundle`;
- complete `FeasibleActionSet`;
- objective policy, opportunity-cost fields and retained soft warnings.

**Produces**

- `AgentSelection`.

**Unique authority**

- select and explain one feasible bundle, including the explicit
  `NO_ACTION_WITH_OBLIGATION` bundle when justified.

**Must not**

- invent a candidate;
- select outside the feasible set;
- alter a calculation;
- relax a hard constraint;
- turn soft guidance into a hard prohibition;
- add evidence or paths;
- omit relevant opportunity cost;
- change risk, state or authority;
- commit or dispatch an action.

### 8.4 Deterministic Kernel

The kernel is not an Agent.

**Consumes**

- all frozen envelopes;
- accepted heads;
- source, policy, plugin and authority digests.

**Owns**

- schema and PIT validation;
- candidate canonicalization and dependency-group deduplication;
- payoff/risk/fee/margin calculation;
- hard feasibility;
- state-transition validation;
- `FeasibleActionSet`;
- governance assessment;
- E0 commit plan;
- offline replay inputs.

**Must not**

- invent a market mechanism;
- rank soft alternatives into one mandatory answer;
- choose the final market action;
- interpret execution denial as market ABSTAIN;
- create paper/live authority.

### 8.5 Application Workflow

The Application workflow is a deterministic coordinator, not an Agent role.

It owns:

- bootstrap;
- role-scoped context views;
- fixed one-pass DAG;
- timeout and resource budgets;
- artifact freezing;
- typed joins;
- terminal failure mapping;
- UnitOfWork command assembly.

It must not replace an unavailable role, summarize away required fields, or
write accepted state.

---

## 9. Canonical typed envelopes

There is one shared `envelope_common_fields.v1`:

```yaml
schema_id: non-empty string
schema_version: semver string
object_id: globally unique non-empty string
project_id: non-empty string
offline_run_id: non-empty string
decision_session_id: non-empty string
correlation_id: non-empty string
causation_id: non-empty string
created_at: UTC timestamp
decision_cutoff: UTC timestamp
available_at: UTC timestamp
policy_digest: sha256
source_refs: array<ObjectRef>, minItems=0, uniqueItems=true
parent_artifact_digests: array<sha256>, minItems=0, uniqueItems=true
payload_digest: sha256
```

Every non-event command, state, receipt and Agent handoff uses
`artifact_envelope.v1`, composed with `envelope_common_fields.v1`:

```yaml
binding_phase: BOOTSTRAP_PRE_CONTEXT | EVIDENCE_PRE_CONTEXT | SESSION_INPUT_PRE_CONTEXT | DECISION_CONTEXT_ROOT | CONTEXT_BOUND
producer_kind: APPLICATION | DOMAIN | INFRASTRUCTURE | AGENT
cluster_id: non-empty string
cluster_manifest_digest: sha256
schema_registry_digest: sha256
decision_context_digest: sha256 | null
episode_id: non-empty string | null
source_bundle_digest: sha256 | null
prior_state_digest: sha256 | null
theory_registry_digest: sha256
authority_snapshot_digest: sha256
status: COMPLETE | PARTIAL | UNKNOWN | REJECTED
unknown_fields: array<JSONPointer>, minItems=0, uniqueItems=true
payload: exactly one owner-defined payload object
producer_content_digest: sha256
role_id: PROPOSER | CHALLENGER | SELECTOR | null
role_skill_id: non-empty string | null
role_skill_version: semver | null
role_skill_digest: sha256 | null
model_provider: non-empty string | null
model_id: non-empty string | null
model_configuration_digest: sha256 | null
```

Conditional rules:

- `BOOTSTRAP_PRE_CONTEXT` is permitted only for the closed bootstrap,
  role-skill-resolution and kernel-component-resolution payload set, plus a
  typed error produced by one of those operations;
  `decision_context_digest=null` and `source_bundle_digest=null`, while
  `prior_state_digest` is the verified accepted head digest or null only for
  strict genesis;
- `EVIDENCE_PRE_CONTEXT` is permitted only for `EvidenceBundle`;
  `decision_context_digest=null`, `source_bundle_digest=null`, and the bundle's
  own payload/envelope digests become the source-bundle binding consumed by
  the later `DecisionContext`; a typed evidence-admission error may use the
  same phase;
- `SESSION_INPUT_PRE_CONTEXT` is permitted only for the closed session-input
  set `AutonomyEnvelope`, `AccountRiskBudgetEnvelope`,
  `EpisodeRiskAllocationReceipt`, `SupervisionAvailabilityContract`, and
  `UnattendedSafetyEnvelope`; `decision_context_digest=null`,
  `source_bundle_digest` is non-null, and the verified prior-state binding is
  retained; a typed error from one of those builders may use the same phase;
- `DECISION_CONTEXT_ROOT` is permitted only for `DecisionContext`;
  `decision_context_digest=null`, while `source_bundle_digest` and the
  prior-state/genesis binding are non-null as applicable. Its resulting object
  digest becomes the context binding for downstream artifacts; its typed
  construction error may use the same phase;
- `CONTEXT_BOUND` requires non-null `decision_context_digest` and
  `source_bundle_digest`; `prior_state_digest` may be null only for a validated
  genesis session;
- when `producer_kind=AGENT`, all role/skill/model fields are non-null and
  `role_id` matches the payload schema and `binding_phase=CONTEXT_BOUND`;
- otherwise every role/skill/model field is null;
- `available_at <= created_at`;
- PIT eligibility is enforced on every referenced source field as
  `source.available_at <= decision_cutoff`; a derived Agent/Domain artifact may
  be created after the market cutoff but cannot introduce a later market fact;
- all arrays preserve canonical lexicographic order by canonical object key;
- no undeclared property is allowed in C1 schemas.

Events do not also use `artifact_envelope.v1`. They use the separate
`event_envelope.v1` defined by the shared event registry and reference an
already typed payload object.

`producer_content_digest` proves byte identity only. It does not grant evidence,
state, promotion, clock, risk, or execution authority.

Every field used in a downstream decision must be bound either to:

- a source admitted by the PIT gate;
- a prior accepted state artifact;
- a deterministic calculation;
- a pinned theory/policy/authority artifact;
- an explicitly marked Agent proposal.

Free text may explain a proposal but may not carry an untyped permission.

`event_envelope.v1` composes every common field with exactly:

```yaml
event_type: non-empty token present in closed_event_registry.v1
event_payload_schema_id: non-empty canonical schema ID
event_payload_schema_version: semver
aggregate_id: non-empty string
event_sequence: nonnegative integer
payload_ref: ObjectRef
previous_event_chain_digest: sha256 | null
event_digest: sha256
```

`event_sequence` is one run-global sequence, not an aggregate-local sequence.
For sequence `0`, `previous_event_chain_digest` is null and the event is the
only genesis event for that `offline_run_id`. For sequence greater than `0`,
exactly one event with sequence `n-1` must already be the committed run head;
the new sequence is exactly previous plus one and
`previous_event_chain_digest` equals that head's digest. No two event types or
aggregates in one run may share a sequence. The closed registry idempotency key
is exactly `[offline_run_id, event_sequence]`; a same-key type/payload/digest
conflict returns `UOW_PARTIAL_DUPLICATE`. The payload schema ID/version/digest
must equal `payload_ref`. `event_digest` uses the self-digest omission rule and
is the next chain digest. No event carries an artifact envelope in addition to
this event envelope.

---

## 10. Decision-chain contracts

The complete chain is:

```text
ClusterBootstrapReceipt
→ EvidenceBundle
→ session input envelopes
→ DecisionContext
→ AgentProposalEnvelope
→ ChallengeEnvelope
→ ChallengeDisposition
→ CandidateBundleSet
→ DeterministicCalculationBundle
→ ConstraintVerdictSet
→ FeasibleActionSet
→ AgentSelection
→ GovernanceAssessmentReceipt
├─ if PASS + FEASIBLE + ALLOWED
│  → CounterfactualPolicyReceipt
│  → PortfolioReplayResult
│  → E0CommitPlan
│  → UnitOfWork CommitReceipt
└─ if REJECT/UNKNOWN/INFEASIBLE/DENIED
   → typed terminal no-commit result in the write-once work archive
```

### 10.1 `DecisionContext`

Must include:

- cutoff and all source `available_at` values;
- accepted state head and full required state projection;
- open lots and roles;
- invalidators and pending observations;
- path set;
- account, episode and attention envelopes;
- theory, policy, schema, skill and authority digests;
- exact objective mode;
- missing-input map.

### 10.2 `CandidateBundleSet`

Application invokes the Domain `CandidateBundleAssembler`. Domain owns every
compatibility predicate and creates the `CandidateBundleSet`; Application only
passes typed objects and orchestrates the call.

Compatibility is determined by typed predicates, such as:

- same episode and cutoff;
- same prior accepted head;
- path exists in the proposal envelope;
- position intent references a valid proposed state delta;
- execution tactic references an existing position facet;
- geometry horizon and strategic horizon do not conflict;
- attention mode permits the tactic class.

The assembler does not rank market quality.

### 10.3 `DeterministicCalculationBundle`

Contains:

- path × plan payoff cells;
- current-price forward reward/risk;
- fees, slippage and stress assumptions;
- episode, instrument and account risk;
- remaining risk budget;
- margin and tail reserves;
- target/stop/barrier calculations;
- data-quality and calculability status.

If path probabilities are not calibrated, the bundle may calculate payoff
vectors and break-even boundaries but not EV, Kelly, or an asserted edge.

### 10.4 `ConstraintVerdictSet`

Each verdict is one of:

- `HARD`: may remove a candidate;
- `SOFT`: must remain visible to the selector;
- `INFORMATIONAL`: cannot remove a candidate;
- `UNKNOWN_DEPENDENCY`: removes only candidates that require the unknown field.

A general statement such as “market uncertainty is high” is not a hard
constraint.

### 10.5 `FeasibleActionSet`

Must include:

- every surviving candidate bundle;
- exact reasons for each removal;
- calculation references;
- retained soft warnings;
- opportunity-cost fields;
- whether no-action is feasible;
- whether the set is unexpectedly empty;
- diversity and collapse diagnostics.

The validator creates a feasible set. It does not choose the “safest” action.

### 10.6 `GovernanceAssessmentReceipt`

The deterministic governance step verifies:

- role completeness;
- schema and digest closure;
- PIT closure;
- prior-state continuity;
- calculation reproducibility;
- hard-constraint correctness;
- selector membership;
- challenge disposition;
- counterfactual-only authority;
- expected UnitOfWork head.

It cannot silently rewrite the selected bundle.

### 10.7 Complete owner registry

| Object | Unique semantic owner | Precommit → accepted persistence |
|---|---|---|
| `ObjectRef`, `CausalRef`, `SchemaRegistry`, `ObjectOwnerRegistry`, `ConstraintRegistry`, `closed_error_registry.v1`, `closed_event_registry.v1`, and the three envelope schema definitions | Domain Contracts | none → versioned project contract repository; envelope instances inherit payload persistence, while committed event envelopes are UnitOfWork-only |
| `typed_error` instances | Domain Contracts | write-once work archive → UnitOfWork accepts exact digest when part of an accepted session |
| `RoleContract`, `RoleInputProjectionPolicy`, `DeterministicPredicateContract` | Domain Deliberation | none → versioned project contract repository |
| `ProjectBootstrapManifest`, `ProjectStateGenesisContract`, `ProjectStateMigrationReceipt`, `ClusterManifest` | Application Bootstrap/Contracts | none → versioned project contract repository |
| `RoleSkillPackageManifest`, `PortContract`, `KernelComponentContract` | Application Bootstrap/Contracts | none → versioned project contract repository |
| `SkillResolutionReceipt`, `KernelComponentResolutionReceipt`, `ClusterBootstrapReceipt`, `DecisionContext`, `RoleContextView`, `ResolvedRoleInputBundle` | Application Bootstrap/Contracts | write-once work archive → UnitOfWork accepts exact digest |
| `EvidenceBundle` | Domain Evidence | write-once work archive → UnitOfWork accepts exact digest |
| `AutonomyEnvelope`, `AgentProposalEnvelope`, `ProposedActionPlan`, `ChallengeEnvelope`, `ChallengeClaim`, `ChallengeDisposition`, `CandidateBundle`, `CandidateAssemblyReceipt`, `CandidateBundleSet`, `CandidateCalculationReceipt`, `DeterministicCalculationBundle`, `ConstraintVerdict`, `ConstraintVerdictSet`, `FeasibleActionSet`, `AgentSelection` | Domain Deliberation | write-once work archive → UnitOfWork accepts exact digest |
| `StrategicDeltaFacet` | Domain Strategic | write-once work archive → UnitOfWork accepts exact digest |
| `DynamicGeometryFacet` | Domain Geometry | write-once work archive → UnitOfWork accepts exact digest |
| `PositionExposureFacet` | Domain Position | write-once work archive → UnitOfWork accepts exact digest |
| `ReentryFacet` | Domain Reentry | write-once work archive → UnitOfWork accepts exact digest |
| `ExecutionTacticFacet` | Domain Governance | write-once work archive → UnitOfWork accepts exact digest |
| `PathPayoffMatrixSpec`, `PathPayoffCell`, `AccountRiskBudgetEnvelope`, `EpisodeRiskAllocationReceipt`, `StagedPositionPlan`, `StageSpec`, `StageActivationReceipt`, `AdjustmentQuotaContract`, `PlanAmendmentReceipt`, `SupervisionAvailabilityContract`, `UnattendedSafetyEnvelope`, `CandidateRiskReceipt`, `ExecutionCostReceipt`, `ForwardRewardRiskReceipt` | Domain Position | write-once work archive → UnitOfWork accepts exact digest |
| `OpportunityCostReceipt` | Domain Evaluation | write-once work archive → UnitOfWork accepts exact digest |
| `GovernanceAssessmentReceipt`, `CounterfactualPolicyReceipt` | Domain Governance | write-once work archive → UnitOfWork accepts exact digest |
| `PortfolioReplayResult` | Infrastructure Offline Portfolio adapter output | write-once work archive → UnitOfWork accepts exact digest |
| `RawAgentResult`, `RawAgentTurnArchiveManifest`, `ToolTranscript` | Infrastructure Agent Adapter | write-once work archive → UnitOfWork accepts exact digest |
| `ImmutableByteBlob` | Infrastructure Content Store | write-once content store → UnitOfWork accepts exact digest when referenced |
| `E0CommitPlan` | Application Commit use case | ephemeral application → never accepted as state |
| `CommitReceipt`, accepted HEAD and event batch | Infrastructure UnitOfWork/Event Store | none → UnitOfWork/Event Store |
| report, chart or summary | Presentation | rebuildable projection only |

Application orchestration cannot implement Domain compatibility, risk,
constraint, transition or selection-membership semantics.

### 10.8 Required payload contracts

The universal envelope is only an outer shell. Each owner must define a
versioned payload schema.

Unless a field below is marked `optional` or `nullable`, it is required.

Global payload rules:

- `additionalProperties=false`;
- `ObjectRef` is a non-null content-addressed reference;
- `sha256` is 64 lowercase hexadecimal characters;
- timestamps are UTC RFC3339 with an explicit `Z`;
- enum values are closed;
- unordered reference arrays are unique and sorted by
  `(schema_id, object_id, payload_digest)`;
- ordered arrays explicitly say `ordered`;
- nullable fields accept only the stated type or `null`;
- an optional field is absent, never silently defaulted;
- array cardinality is stated below;
- a conditional field that violates its condition is rejected.
- content-addressed references form a directed acyclic graph; a container may
  reference child objects, but a child cannot content-reference that same
  container. Shared logical IDs are used where reverse membership is needed.

Canonical schema identity is always a two-field tuple:

```text
(schema_id without a version suffix, full SemVer schema_version)
```

All initial C1 schemas use version `1.0.0`. The documentation shorthand
`object_ref.v1` means exactly `(schema_id="object_ref",
schema_version="1.0.0")`; `object_ref.v1` is never itself a `schema_id`.
Filenames, headings and event types are not schema identity.

Every `OWNER_PAYLOAD` has exactly one self-digest field declared by its
`SchemaRegistryEntry`. Deterministic digest construction is:

1. validate the payload with the self-digest field absent;
2. serialize it with UTF-8 JSON JCS/RFC8785;
3. SHA-256 those bytes;
4. insert that value into the declared self-digest field;
5. set the containing artifact/event envelope `payload_digest` to the same
   value.

No second pass is made after insertion. For an artifact envelope,
`producer_content_digest` is computed the same way with only that envelope
field absent; for an event envelope, `event_digest` is its declared
self-digest. `ObjectRef.payload_digest` and `ObjectRef.object_digest` must equal
these stored values. Any owner-local `proposal_digest`, `receipt_digest`,
`manifest_digest`, `bundle_digest`, or similarly named field is not an
independent checksum; it is the one registry-declared payload self-digest.

#### Canonical reference value types

`ObjectRef.v1` is an inline immutable value:

```yaml
schema_id: non-empty string
schema_version: semver
object_id: non-empty globally unique string
payload_digest: sha256
object_digest: sha256
```

`object_digest` is SHA-256 over the complete canonical object with its one
self-digest field omitted; the digest is then inserted without recomputing.
For an artifact envelope it equals `producer_content_digest` under this rule;
`payload_digest` separately identifies the owner-defined payload. A filesystem
path, mutable alias, display label or database row number is never object
identity.

`CausalRef.v1` is an inline immutable value:

```yaml
cause_ref: ObjectRef
causal_role: SOURCE_EVIDENCE | PRIOR_ACCEPTED_STATE | POLICY | AUTHORITY | CALCULATION | PARENT_PROPOSAL | PARENT_DECISION
available_at: UTC timestamp
decision_cutoff: UTC timestamp
relationship_digest: sha256
```

`available_at <= decision_cutoff` is required for source evidence. For all
other roles, the referenced object must pre-exist the produced object and its
exact digest must appear in the envelope's parent/source bindings.
`relationship_digest` is SHA-256 over the UTF-8 JCS/RFC8785 serialization of
the four preceding fields with `relationship_digest` absent; the value is then
inserted without a second pass.

`ImmutableByteBlob.v1` stores exact non-JSON bytes in the content-addressed
repository:

```yaml
media_type: non-empty IANA media type
byte_length: nonnegative integer
bytes_sha256: sha256
storage_content_key: non-empty content-addressed key
compression: NONE | GZIP
blob_digest: sha256
```

The content key is derived from `bytes_sha256`; a mutable path or URL is not
accepted. Decompression must reproduce the declared byte length and digest.

`typed_error.v1` is the only error-instance payload:

```yaml
error_id: non-empty globally unique string
error_code: token present in closed_error_registry.v1
category: category matching the registry entry
fail_closed: true
object_refs: array<ObjectRef>, minItems=0
reason_fields: ordered array<ErrorReasonField>, minItems=0
retryability: NEVER | NEW_SESSION | AFTER_INPUT_REPAIR | IDEMPOTENT_RETRY
caused_by_error_refs: array<ObjectRef>, minItems=0
error_digest: sha256
```

`ErrorReasonField`:

```yaml
name: non-empty string
value_kind: STRING | DECIMAL_STRING | BOOLEAN | TIMESTAMP | JSON_POINTER | OBJECT_REF | SHA256
string_value: string | null
boolean_value: boolean | null
object_ref_value: ObjectRef | null
```

For `BOOLEAN` exactly `boolean_value` is non-null; for `OBJECT_REF` exactly
`object_ref_value` is non-null; every other kind uses exactly `string_value`
and its declared lexical grammar. Reason-field names must equal the registry
entry's required names with no duplicates or extras. Category, fail-closed and
retryability must match that entry. `error_digest` follows the payload
self-digest rule and equals the containing envelope's `payload_digest`.

#### Registry self-schemas

`SchemaRegistry.v1`:

```yaml
registry_id: non-empty string
registry_version: semver
canonicalization_policy: UTF8_JSON_JCS_RFC8785_SHA256
entries: array<SchemaRegistryEntry>, minItems=1, sorted by (schema_id, schema_version)
closed: true
registry_digest: sha256
```

`SchemaRegistryEntry`:

```yaml
schema_id: non-empty string
schema_version: semver
schema_kind: OWNER_PAYLOAD | INLINE_VALUE | ENVELOPE | SCHEMA_FRAGMENT
unique_owner_module: non-empty closed owner ID
schema_object_ref: ObjectRef
schema_bytes_digest: sha256
payload_self_digest_field_name: non-empty string | null
compatibility_policy: REJECT_UNKNOWN_MAJOR_PRESERVE_KNOWN_OPTIONAL
```

`OWNER_PAYLOAD` and `ENVELOPE` require exactly one declared self-digest field;
`INLINE_VALUE` and `SCHEMA_FRAGMENT` require null.

`ObjectOwnerRegistry.v1`:

```yaml
registry_id: non-empty string
registry_version: semver
entries: array<ObjectOwnerEntry>, minItems=1, sorted by (object_schema_id, object_schema_version)
closed: true
registry_digest: sha256
```

`ObjectOwnerEntry`:

```yaml
object_schema_id: non-empty string
object_schema_version: semver
unique_semantic_owner: non-empty closed owner ID
precommit_writer: WRITE_ONCE_WORK_ARCHIVE | WRITE_ONCE_CONTENT_STORE | EPHEMERAL_APPLICATION | NONE
accepted_persistence_owner: UNIT_OF_WORK | VERSIONED_CONTRACT_REPOSITORY | NONE
acceptance_mode: UOW_ACCEPT_BY_EXACT_DIGEST | UOW_NATIVE_COMMIT_OUTPUT | PREACCEPTED_STATIC | NEVER_ACCEPTED
```

`UOW_ACCEPT_BY_EXACT_DIGEST` requires a precommit work artifact and permits
UnitOfWork to accept that exact immutable digest without rewriting its bytes.
`UOW_NATIVE_COMMIT_OUTPUT` is limited to output created atomically by the
UnitOfWork itself and cannot be supplied by an Agent or work archive.
`PREACCEPTED_STATIC` is limited to versioned contract/registry objects.
`NEVER_ACCEPTED` covers ephemeral plans and rejected-session work artifacts.

Consumer lists are intentionally absent. Read/dependency closure has one
machine source: `PortContract.operation_specs.input_schema_refs` together with
`KernelComponentContract.input_schema_refs`. A component that does not declare
the schema there cannot consume it. Any consumer column in an architecture
table is a human projection generated from those contracts; it grants no role
input, repository, write, UnitOfWork or execution authority.

The initial closed semantic owner IDs are:

```text
DOMAIN_CONTRACTS
DOMAIN_EVIDENCE
DOMAIN_POLICY
DOMAIN_TIME_AUTHORITY
DOMAIN_HYPOTHESIS
DOMAIN_DELIBERATION
DOMAIN_STRATEGIC
DOMAIN_POSITION
DOMAIN_PORTFOLIO_PROJECTION
DOMAIN_GEOMETRY
DOMAIN_REENTRY
DOMAIN_GOVERNANCE
DOMAIN_MATCHING
DOMAIN_EVALUATION
APPLICATION_BOOTSTRAP_CONTRACTS
APPLICATION_DECISION_SESSION
APPLICATION_COMMIT
INFRASTRUCTURE_AGENT_ADAPTER
INFRASTRUCTURE_LEGACY_ADAPTER
INFRASTRUCTURE_OFFLINE_PORTFOLIO
INFRASTRUCTURE_AUTHORITY_ADAPTER
INFRASTRUCTURE_CONTENT_STORE
INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE
```

No skill, model ID, project override or presentation component is an owner ID.

The initial registry has:

```yaml
registry_id: THEORY_AGENT_V2_OBJECT_OWNER_REGISTRY
registry_version: 1.0.0
closed: true
```

C1.0 creates one entry for every Architecture Section 12 schema whose
`schema_kind=OWNER_PAYLOAD`; every entry uses
`object_schema_version: 1.0.0`. The following registered schemas are not owner
payloads and therefore have no owner entry:

```text
object_ref
causal_ref
envelope_common_fields
artifact_envelope
event_envelope
resolved_role_input_document
```

`FieldProjection`, `ResolvedFieldProjection` and `RoleProjectionRule` are
embedded `$defs` and are not registered schemas at all.

Semantic owner is determined only by the exact Architecture Section 12 owner
group mapping below:

```yaml
Domain Contracts: DOMAIN_CONTRACTS
Domain Evidence: DOMAIN_EVIDENCE
Domain Policy: DOMAIN_POLICY
Domain Time Authority: DOMAIN_TIME_AUTHORITY
Domain Hypothesis: DOMAIN_HYPOTHESIS
Domain Deliberation: DOMAIN_DELIBERATION
Domain Strategic: DOMAIN_STRATEGIC
Domain Position: DOMAIN_POSITION
Domain Portfolio Projection: DOMAIN_PORTFOLIO_PROJECTION
Domain Geometry: DOMAIN_GEOMETRY
Domain Reentry: DOMAIN_REENTRY
Domain Governance: DOMAIN_GOVERNANCE
Domain Matching: DOMAIN_MATCHING
Domain Evaluation: DOMAIN_EVALUATION
Infrastructure Agent: INFRASTRUCTURE_AGENT_ADAPTER
Infrastructure Legacy: INFRASTRUCTURE_LEGACY_ADAPTER
Infrastructure Portfolio: INFRASTRUCTURE_OFFLINE_PORTFOLIO
Infrastructure Authority: INFRASTRUCTURE_AUTHORITY_ADAPTER
Infrastructure Repository: INFRASTRUCTURE_UNIT_OF_WORK_EVENT_STORE
```

Two exact overrides apply:

- `immutable_byte_blob → INFRASTRUCTURE_CONTENT_STORE`;
- Application schemas are partitioned as:

```yaml
APPLICATION_BOOTSTRAP_CONTRACTS:
  - cluster_bootstrap_receipt
  - cluster_manifest
  - kernel_component_contract
  - kernel_component_resolution_receipt
  - port_contract
  - project_bootstrap_manifest
  - project_state_genesis_contract
  - project_state_migration_receipt
  - role_skill_package_manifest
  - skill_resolution_receipt
APPLICATION_DECISION_SESSION:
  - advance_episode_command
  - decision_context
  - governance_decision
  - open_episode_command
  - replay_bundle
  - replay_experiment_arm
  - resolved_role_input_bundle
  - role_context_view
  - timeline_catchup_result
APPLICATION_COMMIT:
  - e0_commit_plan
```

Persistence fields are then assigned by this ordered, no-override decision
table:

1. The following static schemas use
   `(NONE, VERSIONED_CONTRACT_REPOSITORY, PREACCEPTED_STATIC)`:

```text
schema_registry
object_owner_registry
constraint_registry
closed_error_registry
closed_event_registry
timeframe_authority_profile
frozen_plugin_registry
role_contract
role_input_projection_policy
deterministic_predicate_contract
project_bootstrap_manifest
project_state_genesis_contract
project_state_migration_receipt
cluster_manifest
role_skill_package_manifest
port_contract
kernel_component_contract
```

2. `immutable_byte_blob` uses
   `(WRITE_ONCE_CONTENT_STORE, UNIT_OF_WORK, UOW_ACCEPT_BY_EXACT_DIGEST)`.
3. `stored_event`, `commit_receipt` and `unit_of_work_batch` use
   `(NONE, UNIT_OF_WORK, UOW_NATIVE_COMMIT_OUTPUT)`.
4. `e0_commit_plan`, `open_episode_command`, `advance_episode_command` and
   `governance_decision` use
   `(EPHEMERAL_APPLICATION, NONE, NEVER_ACCEPTED)`.
5. Every remaining owner payload uses
   `(WRITE_ONCE_WORK_ARCHIVE, UNIT_OF_WORK, UOW_ACCEPT_BY_EXACT_DIGEST)`.

The rules are applied in that order, entries are sorted by
`(object_schema_id, object_schema_version)`, and no project override or
wildcard is allowed. This makes the owner-registry bytes uniquely derivable
from the frozen schema inventory.

`closed_error_registry.v1`:

```yaml
registry_id: non-empty string
registry_version: semver
entries: array<ClosedErrorEntry>, minItems=1, sorted by error_code
unknown_code_policy: FAIL_CLOSED
closed: true
registry_digest: sha256
```

`ClosedErrorEntry`:

```yaml
error_code: non-empty closed enum token
category: non-empty closed category token
fail_closed: true
retryability: NEVER | NEW_SESSION | AFTER_INPUT_REPAIR | IDEMPOTENT_RETRY
required_reason_field_names: array<string>, minItems=0, uniqueItems=true
```

`closed_event_registry.v1`:

```yaml
registry_id: non-empty string
registry_version: semver
entries: array<ClosedEventEntry>, minItems=1, sorted by event_type
event_envelope_schema_ref: ObjectRef
closed: true
registry_digest: sha256
```

`ClosedEventEntry`:

```yaml
event_type: non-empty closed enum token without version suffix
unique_owner_module: non-empty closed owner ID
payload_schema_id: non-empty string
payload_schema_version: semver
trigger_class: PRECOMMIT_RECORDED_AT_FINAL_COMMIT | COMMITTED_DOMAIN_TRANSITION
idempotency_key_field_names: ordered array<string>, minItems=1
post_commit_listener_ids: array<string>, minItems=0, uniqueItems=true
```

Registry digests are computed over canonical bytes with `registry_digest`
temporarily omitted, then the digest field is inserted and the final bytes are
stored. Entries cannot contain filesystem locations as identity.

`ConstraintRegistry.v1`:

```yaml
registry_id: non-empty string
registry_version: semver
entries: array<ConstraintDefinition>, minItems=1, sorted by constraint_id
closed: true
registry_digest: sha256
```

`ConstraintDefinition`:

```yaml
constraint_id: non-empty closed token
constraint_version: semver
unique_owner_module: non-empty closed owner ID
constraint_class: HARD | SOFT | INFORMATIONAL | UNKNOWN_DEPENDENCY
evaluation_phase: FACET_ASSEMBLY | CANDIDATE_CALCULATION | FEASIBILITY | GOVERNANCE
applicable_schema_ids: nonempty unique array<string>
applicable_intent_types: unique array<closed intent enum>
deterministic_predicate_contract_ref: ObjectRef
failure_scope: PROPOSED_PLAN_LOCAL | CANDIDATE_LOCAL | SESSION
protective_actions_remain_allowed: boolean
enabled_authority_scope: E0_OFFLINE_COUNTERFACTUAL
```

`DeterministicPredicateContract.v1`:

```yaml
predicate_id: non-empty closed token
predicate_version: semver
subject_schema_id: non-empty string
subject_schema_version: semver
field_json_pointer: RFC6901 JSONPointer
operator: ENUM_EQUALS
comparison_literal: non-empty string
on_match: FAIL_PROPOSED_PLAN_LOCAL
on_non_match: PASS
on_missing: SCHEMA_INVALID
side_effects: NONE
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
predicate_digest: sha256
```

The initial predicate payload is exactly:

```yaml
predicate_id: CURRENT_CORE_HEDGE_UNAUTHORIZED_PREDICATE
predicate_version: 1.0.0
subject_schema_id: position_exposure_facet
subject_schema_version: 1.0.0
field_json_pointer: /requested_lot_role
operator: ENUM_EQUALS
comparison_literal: HEDGE
on_match: FAIL_PROPOSED_PLAN_LOCAL
on_non_match: PASS
on_missing: SCHEMA_INVALID
side_effects: NONE
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
```

C1.0 first inserts its computed `predicate_digest`, stores it as object ID
`CURRENT_CORE_HEDGE_UNAUTHORIZED_PREDICATE`, and then uses that exact
`ObjectRef` in the constraint entry. The initial registry payload is exactly:

```yaml
registry_id: THEORY_AGENT_V2_CONSTRAINT_REGISTRY
registry_version: 1.0.0
entries:
  - constraint_id: CURRENT_CORE_HEDGE_UNAUTHORIZED
    constraint_version: 1.0.0
    unique_owner_module: DOMAIN_DELIBERATION
    constraint_class: HARD
    evaluation_phase: FACET_ASSEMBLY
    applicable_schema_ids: [position_exposure_facet]
    applicable_intent_types:
      - ADD_TACTICAL_E0
      - EXIT_STRATEGIC
      - FLAT_PENDING_REENTRY
      - KEEP_CORE
      - NO_ACTION_WITH_OBLIGATION
      - PARTIAL_PROFIT
      - REDUCE_TACTICAL
      - REENTER_E0
      - TRAIL_CORE
    deterministic_predicate_contract_ref: <the exact materialized ObjectRef above>
    failure_scope: PROPOSED_PLAN_LOCAL
    protective_actions_remain_allowed: true
    enabled_authority_scope: E0_OFFLINE_COUNTERFACTUAL
closed: true
```

There are no other C1.0 constraint entries. A proposed position facet
requesting HEDGE is retained in the rejected-facet audit trail but cannot be
assembled into `CandidateBundle.v1`.

#### Role, skill and kernel contracts

`RoleContract.v1`:

```yaml
role_id: PROPOSER | CHALLENGER | SELECTOR
contract_version: semver
input_schema_ref: ObjectRef
output_schema_ref: ObjectRef
input_projection_policy_ref: ObjectRef
allowed_tool_ids: unique array<string>
repository_access: DENIED
evidence_refresh: DENIED
external_execution: DENIED
direct_role_messaging: DENIED
required_unknown_handling: PRESERVE_TYPED_UNKNOWN
failure_policy: SESSION_INCOMPLETE_NO_COMMIT
contract_digest: sha256
```

The three contracts bind respectively to
`ResolvedRoleInputBundle → AgentProposalEnvelope`,
`ResolvedRoleInputBundle → ChallengeEnvelope`, and
`ResolvedRoleInputBundle → AgentSelection`.
Every `input_projection_policy_ref` targets the same-role
`RoleInputProjectionPolicy.v1`.

`RoleInputProjectionPolicy.v1`:

```yaml
role_id: PROPOSER | CHALLENGER | SELECTOR
policy_version: semver
projection_rules: ordered array<RoleProjectionRule>, minItems=1
closed: true
policy_digest: sha256
```

`RoleProjectionRule` is the closed `$defs.RoleProjectionRule` fragment embedded
in `role_input_projection_policy.v1` and is not independently registered:

```yaml
source_schema_id: non-empty string
source_schema_version: semver
json_pointer: RFC6901 JSONPointer
minimum_occurrences: nonnegative integer
maximum_occurrences: positive integer | null
allowed_value_kinds: nonempty unique array<NULL | BOOLEAN | NUMBER | STRING | ARRAY | OBJECT>
```

Rules are unique by `(source_schema_id, source_schema_version, json_pointer)`.
For every view, the deterministic Application validator groups
`allowed_field_projections` by this tuple, rejects an unregistered tuple, and
enforces both occurrence bounds and selected JSON value kind. `null`
`maximum_occurrences` means unbounded by count, not unbounded by schema or
pointer. This policy defines the role's maximum readable surface; the concrete
view may be narrower only when all `minimum_occurrences` remain satisfied.

`RoleSkillPackageManifest.v1`:

```yaml
skill_id: non-empty string
skill_version: semver
role_id: PROPOSER | CHALLENGER | SELECTOR
role_contract_ref: ObjectRef
package_entries: ordered array<SkillPackageEntry>, minItems=2
skill_md_ref: ObjectRef
agents_openai_yaml_ref: ObjectRef
package_digest: sha256
manifest_digest: sha256
```

`SkillPackageEntry`:

```yaml
relative_posix_path: non-empty normalized relative path
executable: boolean
byte_length: nonnegative integer
file_bytes_ref: ObjectRef
file_sha256: sha256
```

Every file ref targets `ImmutableByteBlob.v1`; the entry order and
`package_digest` algorithm are the ones frozen under
`SkillResolutionReceipt.v1`.

`PortContract.v1`:

```yaml
port_id: non-empty closed port ID
port_version: semver
declared_by_layer: APPLICATION | DOMAIN
operation_specs: ordered array<PortOperationSpec>, minItems=1
allowed_side_effects: unique array<READ_SOURCE | WRITE_CONTENT_ONCE | ATOMIC_UOW_COMMIT>
typed_error_code_ids: unique array<string>
idempotency_policy: REQUIRED | NOT_APPLICABLE
external_execution_authority: NONE_E0
contract_digest: sha256
```

`PortOperationSpec`:

```yaml
operation_id: non-empty string
input_schema_refs: ordered array<ObjectRef>, minItems=1
output_schema_refs: ordered array<ObjectRef>, minItems=1
unknown_output_allowed: boolean
```

`KernelComponentContract.v1`:

```yaml
component_id: non-empty closed component ID
component_version: semver
owner_layer: APPLICATION | DOMAIN | INFRASTRUCTURE
implemented_port_contract_refs: nonempty unique array<ObjectRef>
input_schema_refs: nonempty unique array<ObjectRef>
output_schema_refs: nonempty unique array<ObjectRef>
deterministic: true
model_invocation: FORBIDDEN
allowed_side_effects: unique array<READ_SOURCE | WRITE_CONTENT_ONCE | ATOMIC_UOW_COMMIT>
health_check_port_contract_ref: ObjectRef
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
contract_digest: sha256
```

Only `INFRASTRUCTURE_CONTENT_STORE` may declare `WRITE_CONTENT_ONCE`; only
`INFRASTRUCTURE_UNIT_OF_WORK` may declare `ATOMIC_UOW_COMMIT`. A resolution
receipt proves implementation compatibility with these contracts but never
expands the declared side effects.
Every health-check ref must target `PortContract.v1`.

#### `ProjectBootstrapManifest.v1`

```yaml
project_id: non-empty string
objective_artifact_ref: ObjectRef
requirements_artifact_ref: ObjectRef
bootstrap_launcher_ref: ObjectRef
bootstrap_launcher_code_digest: sha256
bootstrap_canonicalizer_version: semver
theory_registry_ref: ObjectRef
schema_registry_ref: ObjectRef
object_owner_registry_ref: ObjectRef
constraint_registry_ref: ObjectRef
error_registry_ref: ObjectRef
event_registry_ref: ObjectRef
cluster_manifest_ref: ObjectRef
authority_snapshot_ref: ObjectRef
source_manifest_refs: array<ObjectRef>, minItems=1
runtime_namespace: ".runtime/theory-paper-v2/<offline_run_id>/"
bootstrap_mode: ACCEPTED_HEAD | STRICT_GENESIS | AUTHORIZED_MIGRATION
accepted_state_head_ref: ObjectRef | null
state_genesis_contract_ref: ObjectRef | null
migration_receipt_ref: ObjectRef | null
evidence_level: E0
runtime_authority: NONE
paper_authority: NONE
live_authority: NONE
external_order_dispatch: DENIED
manifest_digest: sha256
```

The launcher/canonicalizer tuple is the explicit local bootstrap trust root. It
is verified by the project installation/operator before launch and is not
allowed to issue a receipt that “proves” its own bytes. The manifest-required
kernel component set begins after this trust root and excludes the bootstrap
launcher and component resolver themselves.

Conditional cardinality:

- `ACCEPTED_HEAD`: accepted head non-null; genesis/migration refs null;
- `STRICT_GENESIS`: genesis non-null; accepted/migration refs null;
- `AUTHORIZED_MIGRATION`: accepted head and migration receipt non-null; genesis
  null.

#### `ProjectStateGenesisContract.v1`

```yaml
project_id: non-empty string
offline_run_id: non-empty string
empty_event_chain_proof_ref: ObjectRef
initial_aggregate_state_refs: array<ObjectRef>, minItems=1
authority_snapshot_ref: ObjectRef
schema_registry_ref: ObjectRef
object_owner_registry_ref: ObjectRef
constraint_registry_ref: ObjectRef
policy_registry_ref: ObjectRef
evidence_level: E0
runtime_authority: NONE
paper_authority: NONE
live_authority: NONE
external_execution_authority: NONE_E0
user_authorization_ref: ObjectRef
contract_digest: sha256
```

#### `ProjectStateMigrationReceipt.v1`

```yaml
source_project_id: non-empty string
target_project_id: non-empty string
source_accepted_head_ref: ObjectRef
source_chain_digest: sha256
target_genesis_head_ref: ObjectRef
object_migration_manifest_ref: ObjectRef
excluded_secret_and_authority_classes: nonempty unique array<string>
target_authority_snapshot_ref: ObjectRef
user_authorization_ref: ObjectRef
verdict: PASS | REJECT
receipt_digest: sha256
```

`PASS` requires distinct source/target projects and excludes credentials,
runtime IDs, automation IDs and all paper/live authority.

#### `ClusterManifest.v1`

```yaml
cluster_id: non-empty string
cluster_version: semver
required_role_contract_refs: ordered array<ObjectRef>, minItems=3, maxItems=3
required_role_ids: [PROPOSER, CHALLENGER, SELECTOR]
required_role_skill_refs: ordered array<ObjectRef>, minItems=3, maxItems=3
required_kernel_component_refs: nonempty ordered array<ObjectRef>
bootstrap_producer_id: BOOTSTRAP_TRUST_ROOT
fixed_dag: PROPOSE_ONCE_CHALLENGE_ONCE_CALCULATE_ONCE_SELECT_ONCE_GOVERN_ONCE
specialist_proposer_fanout: OFF
max_proposer_candidate_paths: integer, minimum=1
max_candidate_plans_per_path: integer, minimum=1
max_compatible_bundles: integer, minimum=1
max_superseding_sessions_per_cutoff: integer, minimum=0, maximum=1
role_timeout_ms: map<RoleId, positive integer>, exactly 3 keys
role_token_cap: map<RoleId, positive integer>, exactly 3 keys
role_tool_call_cap: map<RoleId, nonnegative integer>, exactly 3 keys
total_cost_cap: nonnegative decimal string
work_artifact_layout: ".runtime/theory-paper-v2/<offline_run_id>/work/<decision_session_id>/<producer_id>/<object_id>"
missing_required_role_policy: SESSION_INCOMPLETE_NO_COMMIT
manifest_digest: sha256
```

The three role IDs, role contracts and role skills form a positionally matched
closed tuple. Kernel components are code implementations of Application,
Domain or Infrastructure ports; they are not skills and never acquire
authority from a model invocation.
Every role-contract ref targets `RoleContract.v1`; every role-skill ref targets
`RoleSkillPackageManifest.v1`; every kernel-component ref targets
`KernelComponentContract.v1`.

The initial closed post-bootstrap component IDs are:

```text
APPLICATION_DECISION_SESSION
APPLICATION_COMMIT
DOMAIN_EVIDENCE_ADMISSION
DOMAIN_CANDIDATE_ASSEMBLER
DOMAIN_PAYOFF_RISK_CALCULATOR
DOMAIN_CONSTRAINT_ENGINE
DOMAIN_STATE_REDUCER
DOMAIN_GOVERNANCE
INFRASTRUCTURE_AGENT_ADAPTER
INFRASTRUCTURE_CONTENT_STORE
INFRASTRUCTURE_OFFLINE_REPLAY
INFRASTRUCTURE_UNIT_OF_WORK
```

The manifest must contain exactly these IDs for C1. A later compatible design
may revise the closed set; a runtime project override cannot add or omit one.

#### `SkillResolutionReceipt.v1`

```yaml
skill_id: non-empty string
role_id: PROPOSER | CHALLENGER | SELECTOR
required_version: semver
canonical_source_ref: ObjectRef
canonical_source_digest: sha256
resolution_mode: USER_INSTALLED | PLUGIN_RESOLVED | EXPLICIT_PATH_INVOCATION
resolved_location: non-empty path string
resolved_skill_digest: sha256
agents_metadata_digest: sha256
execution_kind: GENERATIVE_AGENT_ROLE
allowed_caller: APPLICATION_DECISION_SESSION
callable: boolean
installed: boolean
verified_at: UTC timestamp
verdict: PASS | SKILL_UNAVAILABLE_NO_COMMIT | SKILL_DIGEST_MISMATCH_NO_COMMIT
receipt_digest: sha256
```

`verdict=PASS` requires source/resolved digests equal, `callable=true`, and
an exact match to one positional `(role_id, role contract, role skill)` tuple
in `ClusterManifest`.

The role-skill package digest covers the complete package tree: `SKILL.md`,
`agents/openai.yaml`, and every declared file under `references/`, `scripts/`
or `assets/`. Digest construction is deterministic:

1. reject symlinks, device files, undeclared hidden files and path traversal;
2. normalize relative paths to UTF-8 POSIX form and sort bytewise;
3. retain an explicit executable-bit flag for each regular file;
4. hash exact file bytes without line-ending or whitespace rewriting;
5. create a JCS/RFC8785 manifest of
   `(relative_path, executable, byte_length, file_sha256)`;
6. SHA-256 that manifest as the package digest.

`agents_metadata_digest` must equal the file digest recorded for
`agents/openai.yaml`. `canonical_source_digest` and `resolved_skill_digest`
both use this package algorithm; a partial-file or `SKILL.md`-only digest
cannot pass. `canonical_source_ref` must target
`RoleSkillPackageManifest.v1`, and `canonical_source_digest` must equal that
manifest's `package_digest`.

#### `KernelComponentResolutionReceipt.v1`

```yaml
component_id: non-empty closed component ID
component_version: semver
required_component_ref: ObjectRef
implementation_entrypoint: non-empty import/command identifier
code_digest: sha256
schema_registry_digest: sha256
policy_digest: sha256
implemented_port_contract_refs: nonempty ordered array<ObjectRef>
port_contract_digests: ordered array<sha256>, exactly one per port ref
health_check_port_contract_ref: ObjectRef
health_check_port_contract_digest: sha256
owner_layer: APPLICATION | DOMAIN | INFRASTRUCTURE
model_invocation: FORBIDDEN
compatibility_verdict: PASS | FAIL
health_verdict: PASS | FAIL | UNKNOWN
verdict: PASS | KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT | KERNEL_COMPONENT_DIGEST_MISMATCH_NO_COMMIT | KERNEL_COMPONENT_HEALTH_UNKNOWN_NO_COMMIT
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
receipt_digest: sha256
```

This receipt proves that a manifest-pinned deterministic implementation is
present and compatible. It does not prove market correctness and cannot grant
state-write or execution authority. `PASS` requires both compatibility and
health to pass. `required_component_ref` must target
`KernelComponentContract.v1`; every implemented port ref must target
`PortContract.v1` and equal the contract-declared set; the health-check
ref/digest must equal the separately declared health-check port.

#### `DecisionContext.v1`

```yaml
decision_cutoff: UTC timestamp
cluster_bootstrap_receipt_ref: ObjectRef
state_basis_mode: ACCEPTED_HEAD | STRICT_GENESIS
accepted_state_ref: ObjectRef | null
accepted_state_digest: sha256 | null
genesis_state_ref: ObjectRef | null
genesis_state_digest: sha256 | null
state_genesis_contract_ref: ObjectRef | null
evidence_bundle_ref: ObjectRef
open_lot_refs: array<ObjectRef>, minItems=0
active_path_refs: array<ObjectRef>, minItems=1
invalidator_refs: array<ObjectRef>, minItems=0
pending_observation_refs: array<ObjectRef>, minItems=0
review_clock_refs: array<ObjectRef>, minItems=1
reentry_contract_refs: array<ObjectRef>, minItems=0
geometry_refs: array<ObjectRef>, minItems=0
account_risk_envelope_ref: ObjectRef
episode_risk_allocation_ref: ObjectRef | null
supervision_availability_ref: ObjectRef
unattended_safety_envelope_ref: ObjectRef | null
autonomy_envelope_ref: ObjectRef
objective_policy_ref: ObjectRef
constraint_registry_ref: ObjectRef
authority_snapshot_ref: ObjectRef
missing_dependency_refs: array<ObjectRef>, minItems=0
context_digest: sha256
```

`ACCEPTED_HEAD` requires accepted state/digest and null genesis fields;
`STRICT_GENESIS` requires genesis state/digest and genesis contract with null
accepted fields. Exactly one state basis exists and `AgentProposalEnvelope`
must use it as `prior_state_ref`.
`unattended_safety_envelope_ref` is non-null exactly when the supervision mode
is `UNATTENDED_PROTECTED`.

#### `RoleContextView.v1`

`FieldProjection` is the closed `$defs.FieldProjection` fragment embedded in
`role_context_view.v1`; it is not an independently registered owner payload:

```yaml
source_object_ref: ObjectRef
json_pointer: RFC6901 JSONPointer
```

The empty JSON Pointer (`""`) selects the complete owner payload. A pointer is
always evaluated against the complete, schema-valid canonical owner payload
identified by `source_object_ref`, including that payload's declared
self-digest field. It is never evaluated against an artifact envelope, a
filesystem document, a merged context, or an implementation-defined wrapper.

```yaml
decision_context_ref: ObjectRef
decision_context_digest: sha256
role_id: PROPOSER | CHALLENGER | SELECTOR
role_contract_ref: ObjectRef
role_skill_ref: ObjectRef
skill_resolution_receipt_ref: ObjectRef
allowed_field_projections: ordered array<FieldProjection>, minItems=1, unique by (source_object_ref, json_pointer)
explicitly_omitted_field_projections: ordered array<FieldProjection>, minItems=0, unique by (source_object_ref, json_pointer)
proposal_ref: ObjectRef | null
challenge_ref: ObjectRef | null
challenge_disposition_ref: ObjectRef | null
calculation_bundle_ref: ObjectRef | null
feasible_action_set_ref: ObjectRef | null
repository_access: DENIED
evidence_refresh: DENIED
external_execution: DENIED
view_digest: sha256
```

Conditional refs:

- Proposer: all downstream refs null;
- Challenger: proposal non-null; all later refs null;
- Selector: proposal, challenge, disposition, calculation and feasible-set refs
  non-null.

The two projection arrays must be disjoint. The allowed array is exhaustive:
every field not named by an allowed projection is inaccessible to the role.
The omitted array is an audit explanation for security- or authority-relevant
exclusions and is not required to enumerate every inaccessible field. The
Application validator rejects a projection whose source is not reachable from
the exact conditional refs in this view and `DecisionContext`, or whose
projection is not permitted by the referenced role contract.

#### `ResolvedRoleInputBundle.v1`

`ResolvedFieldProjection` is the closed `$defs.ResolvedFieldProjection`
fragment embedded in `resolved_role_input_bundle.v1`; it is not an
independently registered owner payload:

```yaml
source_object_ref: ObjectRef
json_pointer: RFC6901 JSONPointer
projected_value_kind: NULL | BOOLEAN | NUMBER | STRING | ARRAY | OBJECT
projected_value_digest: sha256
```

```yaml
role_context_view_ref: ObjectRef
role_id: PROPOSER | CHALLENGER | SELECTOR
resolved_field_projections: ordered array<ResolvedFieldProjection>, minItems=1
canonical_input_bytes_ref: ObjectRef
canonical_input_bytes_digest: sha256
serialization_profile: UTF8_JSON_JCS_RFC8785
repository_access_for_role: DENIED
evidence_refresh_for_role: DENIED
bundle_digest: sha256
```

`resolved_field_projections` has exactly the same length and order as
`RoleContextView.allowed_field_projections`; each source ref and pointer must
match positionally. A missing pointer, an unresolved source, a JSON type
mismatch, a value-digest mismatch, or an extra projection fails closed with
`ROLE_INPUT_PROJECTION_INVALID_NO_COMMIT`.

For each entry, `projected_value_digest` is SHA-256 over the JCS/RFC8785 bytes
of the exact selected JSON value. Application constructs exactly one canonical
input document:

```json
{
  "schema_id": "resolved_role_input_document",
  "schema_version": "1.0.0",
  "decision_context_ref": {},
  "role_context_view_ref": {},
  "role_id": "PROPOSER",
  "projection_values": [
    {
      "source_object_ref": {},
      "json_pointer": "",
      "value": null
    }
  ]
}
```

The two refs above are their complete canonical `ObjectRef.v1` values. The
role value is copied from the view. `projection_values` follows the exact
allowed-projection order; every `value` is the exact selected JSON value.
There are no additional properties. The whole document is serialized once as
UTF-8 JCS/RFC8785 and stored as `ImmutableByteBlob.v1` before model invocation.
`canonical_input_bytes_digest` must equal that blob's `bytes_sha256`; any
mismatch fails closed with `ROLE_INPUT_BYTES_DIGEST_MISMATCH_NO_COMMIT`.

The Agent receives only those archived bytes. It never receives a repository
handle and cannot resolve an additional `ObjectRef`.

`resolved_role_input_document.v1` is registered as a `SCHEMA_FRAGMENT` with
exact `unique_owner_module=APPLICATION_DECISION_SESSION` and materialized as
its own schema file. It validates the canonical transport document shown above
but has no self-digest field and is never referenced as an accepted owner
payload; only the enclosing `ImmutableByteBlob.v1` is content-addressed.

#### `RawAgentResult.v1` and `RawAgentTurnArchiveManifest.v1`

`RawAgentResult.v1`:

```yaml
role_context_view_ref: ObjectRef
resolved_role_input_bundle_ref: ObjectRef
skill_resolution_receipt_ref: ObjectRef
provider_request_digest: sha256
raw_response_bytes_ref: ObjectRef | null
raw_response_bytes_digest: sha256 | null
tool_transcript_refs: ordered array<ObjectRef>, minItems=0
started_at: UTC timestamp
completed_at: UTC timestamp | null
status: COMPLETE | PARTIAL | TIMEOUT | PROVIDER_ERROR
provider_error_ref: ObjectRef | null
result_digest: sha256
```

`COMPLETE/PARTIAL` require response bytes; `TIMEOUT/PROVIDER_ERROR` require an
error ref and cannot produce a frozen role envelope without a separately valid
partial schema.
`raw_response_bytes_ref` and the resolved role-input
`canonical_input_bytes_ref` must target `ImmutableByteBlob.v1`.

`RawAgentTurnArchiveManifest.v1`:

```yaml
decision_session_ref: ObjectRef
raw_agent_result_refs: ordered array<ObjectRef>, minItems=1, maxItems=3
write_once_root_ref: ObjectRef
exclusive_create_receipt_refs: array<ObjectRef>, exactly one per raw result
archive_digest: sha256
```

`ToolTranscript.v1`:

```yaml
role_context_view_ref: ObjectRef
records: ordered array<ToolCallRecord>, minItems=1
transcript_digest: sha256
```

`ToolCallRecord`:

```yaml
call_id: non-empty string
tool_id: non-empty manifest-allowed string
request_bytes_ref: ObjectRef
response_bytes_ref: ObjectRef | null
started_at: UTC timestamp
completed_at: UTC timestamp | null
status: COMPLETE | TIMEOUT | TOOL_ERROR
error_ref: ObjectRef | null
```

Request/response refs must target `ImmutableByteBlob.v1`; timeout/error
conditions follow the same strict nullability pattern as raw Agent results.

#### `AutonomyEnvelope.v1`

```yaml
strategic_episode_ref: ObjectRef
decision_cutoff: UTC timestamp
allowed_proposal_types: nonempty unique array<closed proposal enum>
allowed_intent_types: nonempty unique array<closed intent enum>
forbidden_intent_types: unique array<closed intent enum>
max_candidate_count: positive integer
account_risk_envelope_ref: ObjectRef
episode_risk_allocation_ref: ObjectRef | null
timeframe_authority_ref: ObjectRef
adjustment_quota_ref: ObjectRef | null
supervision_availability_ref: ObjectRef
required_constraint_ids: nonempty unique array<string>
valid_until: UTC timestamp
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
policy_digest: sha256
envelope_digest: sha256
```

Allowed and forbidden intent sets must be disjoint.

#### `ClusterBootstrapReceipt.v1`

```yaml
project_manifest_ref: ObjectRef
project_manifest_digest: sha256
cluster_manifest_ref: ObjectRef
cluster_manifest_digest: sha256
requirements_artifact_ref: ObjectRef
requirements_artifact_digest: sha256
theory_registry_ref: ObjectRef
theory_registry_digest: sha256
schema_registry_ref: ObjectRef
schema_registry_digest: sha256
constraint_registry_ref: ObjectRef
constraint_registry_digest: sha256
accepted_state_ref: ObjectRef | null
accepted_state_digest: sha256 | null
state_genesis_contract_ref: ObjectRef | null
authority_snapshot_ref: ObjectRef
authority_snapshot_digest: sha256
role_skill_resolution_receipt_refs: array<ObjectRef>, minItems=3, maxItems=3
kernel_component_resolution_receipt_refs: nonempty array<ObjectRef>
source_manifest_refs: array<ObjectRef>, minItems=1
decision_cutoff: UTC timestamp
bootstrap_verdict: PASS | BOOTSTRAP_INCOMPLETE_NO_COMMIT
missing_or_mismatched_refs: array<ObjectRef>, minItems=0
receipt_digest: sha256
```

Exactly one of `accepted_state_ref` or an admissible
`state_genesis_contract_ref` is required. `bootstrap_verdict=PASS` requires
the PASS role-skill IDs to equal the three manifest-required role-skill IDs,
the PASS kernel-component IDs to equal the manifest-required component IDs,
and an empty mismatch array. A skill receipt can never substitute for a kernel
component receipt, or vice versa.

#### `EvidenceBundle.v1`

```yaml
cluster_bootstrap_receipt_ref: ObjectRef
evidence_item_refs: array<ObjectRef>, minItems=1
field_availability_refs: array<ObjectRef>, minItems=1
source_lineage_groups: array<LineageGroup>, minItems=1
dependency_groups: array<DependencyGroup>, minItems=1
cutoff: UTC timestamp
admitted_item_refs: array<ObjectRef>, minItems=0
rejected_item_refs: array<ObjectRef>, minItems=0
unknown_registry_ref: ObjectRef
continuity_receipt_refs: array<ObjectRef>, minItems=1
bundle_digest: sha256
```

Admitted and rejected sets are disjoint and their union equals
`evidence_item_refs`. Every evidence item occurs in exactly one dependency
group and at least one lineage group.

`LineageGroup`:

```yaml
lineage_group_id: non-empty string
root_source_ref: ObjectRef
member_evidence_refs: nonempty unique array<ObjectRef>
```

`DependencyGroup`:

```yaml
dependency_group_id: non-empty string
member_evidence_refs: nonempty unique array<ObjectRef>
independence_claim: SAME_ROOT | DERIVED_FROM_COMMON_INPUT | INDEPENDENT_ROOTS
```

Agent count never appears in either group.

#### `AgentProposalEnvelope.v1`

```yaml
autonomy_envelope_ref: ObjectRef
prior_state_ref: ObjectRef
evidence_bundle_ref: ObjectRef
primary_path_ref: ObjectRef
alternative_path_refs: array<ObjectRef>, minItems=0
null_path_ref: ObjectRef
other_unknown_path_ref: ObjectRef
strategic_delta_facet_refs: array<ObjectRef>, minItems=1
geometry_facet_refs: array<ObjectRef>, minItems=0
exposure_position_facet_refs: array<ObjectRef>, minItems=1
reentry_facet_refs: array<ObjectRef>, minItems=0
execution_tactic_facet_refs: array<ObjectRef>, minItems=0
support_predicate_refs: array<ObjectRef>, minItems=1
falsifier_predicate_refs: array<ObjectRef>, minItems=1
unknown_dependencies: array<ObjectRef>, minItems=0
proposed_action_plan_refs: array<ObjectRef>, minItems=1
plan_semantic_fingerprint_refs: array<ObjectRef>, exactly one per proposed plan
proposal_digest: sha256
```

At least one proposed plan must bind `null_path_ref` to
`NO_ACTION_WITH_OBLIGATION`; otherwise proposal coverage is incomplete and no
candidate set is assembled.

The five proposal facets are typed owner objects rather than free-form
references.

`StrategicDeltaFacet.v1`:

```yaml
prior_strategic_state_ref: ObjectRef
hypothesis_ref: ObjectRef
strategic_timeframe_ref: ObjectRef
proposed_transition: MAINTAIN | CHALLENGE | RISK_REDUCE_NO_INVALIDATION | REENTRY_PENDING | INVALIDATE | CLOSE
affected_premise_refs: array<ObjectRef>, minItems=0
support_predicate_refs: array<ObjectRef>, minItems=0
falsifier_predicate_refs: array<ObjectRef>, minItems=0
hard_invalidator_refs: array<ObjectRef>, minItems=0
claimed_hard_invalidator_triggered: boolean
confidence_delta: INCREASE | UNCHANGED | DECREASE | UNKNOWN
next_review_clock_ref: ObjectRef
facet_digest: sha256
```

`INVALIDATE` requires a claimed registered hard invalidator; the Agent claim
is not authoritative until deterministic state validation passes.
`RISK_REDUCE_NO_INVALIDATION` cannot clear the strategic hypothesis.

`DynamicGeometryFacet.v1`:

```yaml
prior_geometry_ref: ObjectRef | null
proposed_geometry_ref: ObjectRef
regime_ref: ObjectRef
geometry_operation: KEEP | REPLACE | EXPIRE_FOR_NEW_DECISIONS
entry_region_ref: ObjectRef | null
invalidation_region_ref: ObjectRef
target_or_checkpoint_refs: ordered array<ObjectRef>, minItems=1
valid_from: UTC timestamp
valid_until: UTC timestamp
replacement_evidence_refs: array<ObjectRef>, minItems=0
active_protection_unchanged: boolean
facet_digest: sha256
```

The proposal may replace decision geometry but cannot silently cancel an
already active protective barrier.

`PositionExposureFacet.v1`:

```yaml
strategic_episode_ref: ObjectRef
requested_lot_role: CORE | TACTICAL | HEDGE
staged_position_plan_ref: ObjectRef
stage_ref: ObjectRef | null
intent_type: KEEP_CORE | ADD_TACTICAL_E0 | REDUCE_TACTICAL | PARTIAL_PROFIT | TRAIL_CORE | EXIT_STRATEGIC | FLAT_PENDING_REENTRY | REENTER_E0 | NO_ACTION_WITH_OBLIGATION
account_risk_envelope_ref: ObjectRef
episode_risk_allocation_ref: ObjectRef | null
existing_lot_refs: array<ObjectRef>, minItems=0
proposed_quantity_or_fraction_ref: ObjectRef
facet_digest: sha256
```

HEDGE is accepted only as a typed Agent request so the rejection is auditable;
the current E0 assembly constraint forbids it from becoming a candidate.

`ReentryFacet.v1`:

```yaml
strategic_episode_ref: ObjectRef
reentry_mode: NOT_APPLICABLE | MAINTAIN_EXISTING | CREATE_REQUIRED | EVALUATE_EXISTING | TERMINATE_WITH_INVALIDATION
existing_reentry_contract_ref: ObjectRef | null
proposed_reentry_contract_spec_ref: ObjectRef | null
core_hypothesis_survives: boolean
eligibility_predicate_refs: array<ObjectRef>, minItems=0
termination_evidence_refs: array<ObjectRef>, minItems=0
next_review_clock_ref: ObjectRef | null
facet_digest: sha256
```

`CREATE_REQUIRED` requires a proposed contract spec and review clock.
`TERMINATE_WITH_INVALIDATION` requires the matching strategic invalidation
facet.

`ExecutionTacticFacet.v1`:

```yaml
candidate_intent_type: closed intent enum
supervision_contract_ref: ObjectRef
supervision_mode: SUPERVISED | UNATTENDED_PROTECTED | NO_NEW_RISK
order_or_barrier_spec_ref: ObjectRef | null
atomic_protection_spec_ref: ObjectRef | null
expiry: UTC timestamp
required_ack_policy_ref: ObjectRef | null
failure_action: NO_NEW_RISK | KEEP_EXISTING_PROTECTION | REDUCE_ONLY | EXIT
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
facet_digest: sha256
```

Unattended new risk requires non-null machine-expressible order/barrier,
protection and ACK-policy refs.

`ProposedActionPlan.v1`:

```yaml
path_ref: ObjectRef
strategic_delta_facet_ref: ObjectRef
geometry_facet_ref: ObjectRef | null
position_facet_ref: ObjectRef
reentry_facet_ref: ObjectRef | null
execution_tactic_facet_ref: ObjectRef | null
proposed_intent_type: closed intent enum
unknown_dependency_refs: array<ObjectRef>, minItems=0
semantic_fingerprint: sha256
plan_digest: sha256
```

This is an untrusted Agent composition request. It is not a `CandidateBundle`
and has no feasibility or action authority.

#### `ChallengeEnvelope.v1`

```yaml
proposal_ref: ObjectRef
challenge_claim_refs: array<ObjectRef>, minItems=1
challenge_digest: sha256
```

`ChallengeClaim.v1`:

```yaml
proposal_ref: ObjectRef
subject_object_refs: nonempty array<ObjectRef>
claimed_category: closed ChallengeCategory enum
claimed_constraint_or_invariant_refs: array<ObjectRef>, minItems=0
source_refs: array<ObjectRef>, minItems=0
missing_dependency_refs: array<ObjectRef>, minItems=0
market_preference_only: boolean
requested_disposition: VERIFIED_HARD_STRUCTURAL_DEFECT | SOFT | INFORMATIONAL | UNVERIFIED
claim_digest: sha256
```

#### `ChallengeDisposition.v1`

```yaml
challenge_ref: ObjectRef
result: VERIFIED_HARD_STRUCTURAL_DEFECT | SOFT | INFORMATIONAL | UNVERIFIED
verified_challenge_claim_refs: array<ObjectRef>, minItems=0
verified_constraint_or_invariant_refs: array<ObjectRef>, minItems=0
affected_proposed_plan_refs: array<ObjectRef>, minItems=0
terminal_effect: REPROPOSAL_REQUIRED | NONE
deterministic_validator_version: semver
disposition_digest: sha256
```

Only `VERIFIED_HARD_STRUCTURAL_DEFECT` may produce
`REPROPOSAL_REQUIRED`; it requires at least one verified claim and registered
constraint/invariant. A claim marked `market_preference_only=true` cannot be
verified hard.

`ChallengeCategory` is the closed enum:

```text
PREMISE_CONFLICT
CLAIMED_FALSIFIER
OMITTED_COMPETING_PATH
MISSING_SOURCE_OR_DEPENDENCY
STATE_CONTINUITY_BREAK
TIME_SCALE_OVERREACH
EXIT_REENTRY_ASYMMETRY
ACTION_SPACE_COLLAPSE_RISK
UNKNOWN_COERCION
GEOMETRY_POSITION_INCONSISTENCY
ROLE_OVERREACH
```

#### `CandidateBundle.v1`

```yaml
proposal_ref: ObjectRef
proposed_action_plan_ref: ObjectRef
path_ref: ObjectRef
strategic_delta_facet_ref: ObjectRef
geometry_facet_ref: ObjectRef | null
position_facet_ref: ObjectRef
reentry_facet_ref: ObjectRef | null
execution_tactic_facet_ref: ObjectRef | null
intent_type: KEEP_CORE | ADD_TACTICAL_E0 | REDUCE_TACTICAL | PARTIAL_PROFIT | TRAIL_CORE | EXIT_STRATEGIC | FLAT_PENDING_REENTRY | REENTER_E0 | NO_ACTION_WITH_OBLIGATION
unknown_dependency_refs: array<ObjectRef>, minItems=0
semantic_fingerprint: sha256
candidate_digest: sha256
```

`ADD_TACTICAL_E0` and `REENTER_E0` remain counterfactual only. HEDGE is absent
from the current candidate enum and therefore cannot enter a counterfactual
policy.

#### `CandidateBundleSet.v1`

```yaml
proposal_ref: ObjectRef
challenge_ref: ObjectRef
challenge_disposition_ref: ObjectRef
candidate_refs: array<ObjectRef>, minItems=1, maxItems=cluster manifest limit
no_action_candidate_ref: ObjectRef
candidate_assembly_receipt_refs: array<ObjectRef>, minItems=1
rejected_incompatible_facet_refs: array<ObjectRef>, minItems=0
domain_assembler_version: semver
candidate_set_digest: sha256
```

`no_action_candidate_ref` must be a member of `candidate_refs`.
No `CandidateBundleSet` is emitted when the linked disposition has
`terminal_effect=REPROPOSAL_REQUIRED`.

`CandidateAssemblyReceipt.v1`:

```yaml
proposal_ref: ObjectRef
proposed_action_plan_ref: ObjectRef
subject_facet_refs: nonempty array<ObjectRef>
result: COMPATIBLE_BUNDLE | INCOMPATIBLE | DEDUPLICATED
resulting_candidate_ref: ObjectRef | null
canonical_candidate_ref: ObjectRef | null
reason_constraint_refs: nonempty array<ObjectRef>
semantic_fingerprint: sha256
assembler_version: semver
receipt_digest: sha256
```

Compatible requires a resulting candidate; deduplicated requires a canonical
candidate; incompatible requires both nullable candidate refs to be null.

#### `DeterministicCalculationBundle.v1`

```yaml
candidate_bundle_set_ref: ObjectRef
candidate_calculation_receipt_refs: array<ObjectRef>, exactly one per candidate
path_payoff_matrix_refs: array<ObjectRef>, minItems=1
account_risk_envelope_ref: ObjectRef
episode_risk_allocation_ref: ObjectRef | null
execution_cost_policy_ref: ObjectRef
stress_policy_ref: ObjectRef
unknown_dependency_refs_by_candidate: ordered array<CandidateUnknownEntry>, exactly one per candidate
calculator_contract_version: semver
rounding_policy_ref: ObjectRef
calculation_bundle_digest: sha256
```

`CandidateUnknownEntry`:

```yaml
candidate_ref: ObjectRef
unknown_dependency_refs: array<ObjectRef>, minItems=0
affected_calculation_field_json_pointers: array<JSONPointer>, minItems=0
```

#### `ConstraintVerdict.v1`

```yaml
candidate_ref: ObjectRef
constraint_id: non-empty registered string
constraint_class: HARD | SOFT | INFORMATIONAL | UNKNOWN_DEPENDENCY
verdict: PASS | FAIL | UNKNOWN
failed_field_json_pointers: array<JSONPointer>, minItems=0
evidence_or_calculation_refs: array<ObjectRef>, minItems=1
affected_candidate_ref: ObjectRef
protective_actions_remain_allowed: boolean
next_lawful_evidence_or_review_refs: array<ObjectRef>, minItems=0
verdict_digest: sha256
```

`HARD+FAIL` may delete only `affected_candidate_ref`.
`UNKNOWN_DEPENDENCY+UNKNOWN` may delete only candidates referencing the stated
unknown field. `SOFT` and `INFORMATIONAL` never delete.
`candidate_ref` and `affected_candidate_ref` must be identical in C1.

#### `ConstraintVerdictSet.v1`

```yaml
candidate_bundle_set_ref: ObjectRef
calculation_bundle_ref: ObjectRef
verdict_refs: array<ObjectRef>, minItems=1
candidate_coverage: ordered array<CandidateVerdictCoverage>, exactly one per candidate
constraint_registry_ref: ObjectRef
constraint_engine_version: semver
verdict_set_digest: sha256
```

Each `CandidateVerdictCoverage` contains one candidate ref and a nonempty
unique array of all required constraint IDs. Missing required coverage rejects
the entire set.

#### `FeasibleActionSet.v1`

```yaml
candidate_bundle_set_ref: ObjectRef
calculation_bundle_ref: ObjectRef
constraint_verdict_set_ref: ObjectRef
feasible_candidate_refs: array<ObjectRef>, minItems=1
removed_candidates: array<RemovedCandidateEntry>, minItems=0
no_action_candidate_ref: ObjectRef
non_abstain_feasible_count: nonnegative integer
no_hard_feasible_action: boolean
unexpectedly_empty_before_no_action: boolean
retained_soft_verdict_refs: array<ObjectRef>, minItems=0
retained_informational_verdict_refs: array<ObjectRef>, minItems=0
opportunity_cost_receipt_refs: array<ObjectRef>, minItems=1
diversity_diagnostic_ref: ObjectRef
action_space_collapse_diagnostic_ref: ObjectRef
feasible_set_digest: sha256
```

`RemovedCandidateEntry` has:

```yaml
candidate_ref: ObjectRef
removing_verdict_refs: array<ObjectRef>, minItems=1
```

Every removing verdict must be `HARD+FAIL` or a candidate-local
`UNKNOWN_DEPENDENCY+UNKNOWN`. `no_action_candidate_ref` is always a feasible
member. If it cannot be constructed, no `FeasibleActionSet` is emitted.

#### Deterministic position/risk calculation payloads

All decimal quantities are canonical base-10 strings plus an explicit unit or
currency reference. Binary floating-point JSON numbers are forbidden.

`CandidateCalculationReceipt.v1`:

```yaml
candidate_ref: ObjectRef
path_payoff_matrix_ref: ObjectRef
candidate_risk_receipt_ref: ObjectRef
execution_cost_receipt_ref: ObjectRef
forward_reward_risk_receipt_ref: ObjectRef
opportunity_cost_receipt_ref: ObjectRef
calculation_status: COMPLETE | PARTIAL_UNKNOWN
unknown_dependency_refs: array<ObjectRef>, minItems=0
calculator_contract_version: semver
receipt_digest: sha256
```

`PathPayoffMatrixSpec.v1`:

```yaml
strategic_episode_ref: ObjectRef
decision_cutoff: UTC timestamp
row_path_refs: ordered array<ObjectRef>, minItems=4
column_plan_refs: ordered array<ObjectRef>, minItems=1
other_unknown_path_ref: ObjectRef
account_unit_ref: ObjectRef
cost_policy_ref: ObjectRef
tail_policy_ref: ObjectRef
cell_refs: array<ObjectRef>, exactly row_count * column_count
probability_mode: CALIBRATED | ORDINAL_ONLY | UNAVAILABLE
calibration_artifact_ref: ObjectRef | null
matrix_digest: sha256
```

`probability_mode=CALIBRATED` requires a non-null calibration artifact;
otherwise EV/Kelly fields are prohibited.

`PathPayoffCell.v1`:

```yaml
path_ref: ObjectRef
plan_ref: ObjectRef
triggered_stage_refs: ordered array<ObjectRef>, minItems=0
fill_outcome_ref: ObjectRef
terminal_outcome_ref: ObjectRef
account_pnl_interval_ref: ObjectRef
episode_loss_ref: ObjectRef
account_loss_ref: ObjectRef
max_drawdown_ref: ObjectRef
time_to_outcome_ref: ObjectRef
stress_cost_ref: ObjectRef
tail_loss_ref: ObjectRef
data_status: COMPLETE | PARTIALLY_IDENTIFIED | UNKNOWN
assumption_refs: array<ObjectRef>, minItems=0
cell_digest: sha256
```

`AccountRiskBudgetEnvelope.v1`:

```yaml
account_snapshot_ref: ObjectRef
equity_reference_ref: ObjectRef
hard_account_loss_cap_ref: ObjectRef
episode_allocation_cap_ref: ObjectRef
exogenous_position_reserve_ref: ObjectRef
pending_order_reserve_ref: ObjectRef
operational_tail_reserve_ref: ObjectRef
margin_reserve_ref: ObjectRef
unallocated_safety_buffer_ref: ObjectRef
valid_from: UTC timestamp
valid_until: UTC timestamp
owner_authority_ref: ObjectRef
authority_scope: E0_OFFLINE_COUNTERFACTUAL
envelope_digest: sha256
```

Every component is nonnegative, all use one account-risk unit, and allocated
risk plus all reserves cannot exceed the hard cap.

`EpisodeRiskAllocationReceipt.v1`:

```yaml
strategic_episode_ref: ObjectRef
account_risk_envelope_ref: ObjectRef
allocated_episode_risk_ref: ObjectRef
prior_episode_allocation_refs: array<ObjectRef>, minItems=0
remaining_account_capacity_ref: ObjectRef
decision_cutoff: UTC timestamp
permission_scope: E0_COUNTERFACTUAL_ONLY
receipt_digest: sha256
```

`StagedPositionPlan.v1`:

```yaml
plan_id: non-empty globally unique string
strategic_episode_ref: ObjectRef
side: LONG | SHORT
total_episode_risk_ref: ObjectRef
stage_refs: ordered array<ObjectRef>, minItems=1
stage_count: positive integer
stage_fraction_sum_ref: ObjectRef
stage_execution_policy_ref: ObjectRef
adjustment_quota_ref: ObjectRef
target_policy_ref: ObjectRef
reentry_policy_ref: ObjectRef
supervision_contract_ref: ObjectRef
frozen_before_first_fill: true
authority_scope: E0_COUNTERFACTUAL_ONLY
plan_digest: sha256
```

`stage_count` equals `stage_refs.length`; risk fractions are nonnegative and
sum to no more than one episode risk unit.

`StageSpec.v1`:

```yaml
plan_id: non-empty globally unique string
stage_index: nonnegative integer
predecessor_stage_ref: ObjectRef | null
lot_role: CORE | TACTICAL
risk_fraction_ref: ObjectRef
entry_trigger_ref: ObjectRef
entry_zone_ref: ObjectRef
invalidation_ref: ObjectRef
expiry: UTC timestamp
geometry_ref: ObjectRef
hypothesis_ref: ObjectRef
stop_ref: ObjectRef
target_ref: ObjectRef
horizon_ref: ObjectRef
maximum_quantity_ref: ObjectRef
pending_risk_ref: ObjectRef
required_permission_ref: ObjectRef
allowed_supervision_modes: nonempty unique array<SUPERVISED | UNATTENDED_PROTECTED>
untriggered_disposition: WAIT | EXPIRE
stage_digest: sha256
```

The first stage has null predecessor; every later stage references the
immediately preceding stage. HEDGE is not available under the current Core
boundary.

`StageActivationReceipt.v1`:

```yaml
stage_ref: ObjectRef
decision_cutoff: UTC timestamp
trigger_verdict: PASS | FAIL | UNKNOWN
expiry_verdict: ACTIVE | EXPIRED
predecessor_state_ref: ObjectRef | null
remaining_account_risk_ref: ObjectRef
remaining_episode_risk_ref: ObjectRef
add_protocol_authority: NONE_CURRENT_CORE
counterfactual_disposition: SELECTED | REJECTED | NOT_ELIGIBLE
protection_atomicity_verdict: PASS | FAIL | UNKNOWN
receipt_digest: sha256
```

`AdjustmentQuotaContract.v1`:

```yaml
strategic_episode_ref: ObjectRef
max_discretionary_adjustments: nonnegative integer
counted_intent_types: unique array<closed intent enum>
exempt_protective_intent_types: nonempty unique array<closed protective enum>
preplanned_stage_execution_counts: boolean
target_extension_counts: boolean
reentry_counts: boolean
consumed_count: nonnegative integer
reserved_adjustment_ref: ObjectRef | null
policy_digest: sha256
```

`consumed_count <= max_discretionary_adjustments`. Stop, kill, protection
repair, timeout and reconciliation actions are always exempt and cannot be
blocked by the quota.

`PlanAmendmentReceipt.v1`:

```yaml
adjustment_quota_ref: ObjectRef
old_plan_ref: ObjectRef
new_plan_ref: ObjectRef
reason_ref: ObjectRef
evidence_refs: array<ObjectRef>, minItems=1
authority_ref: ObjectRef
reservation_id: non-empty string
reservation_outcome: RESERVED | COMMITTED | RELEASED
idempotency_key: non-empty string
receipt_digest: sha256
```

`SupervisionAvailabilityContract.v1`:

```yaml
available_windows: ordered array<TimeWindow>, minItems=0
unattended_windows: ordered array<TimeWindow>, minItems=0
max_unattended_duration_ref: ObjectRef
allowed_autonomous_intent_types: unique array<closed intent enum>
forbidden_unattended_intent_types: unique array<closed intent enum>
required_active_protection_refs: array<ObjectRef>, minItems=0
required_ack_freshness_ref: ObjectRef
review_deadline_refs: array<ObjectRef>, minItems=1
alert_policy_ref: ObjectRef
failure_action: NO_NEW_RISK
contract_digest: sha256
```

Available and unattended windows cannot overlap.

`TimeWindow`:

```yaml
start_at: UTC timestamp
end_at: UTC timestamp
mode: SUPERVISED | UNATTENDED_PROTECTED | NO_NEW_RISK
```

`start_at < end_at`; windows in each ordered array cannot overlap.

The closed protective enum is:

```text
STOP
KILL
PROTECTION_REPAIR
REDUCE_ONLY
EXIT
TIMEOUT
RECONCILIATION
```

Where a field says `closed intent enum`, it means the `CandidateBundle.v1`
intent enum plus the protective enum above; no other token is accepted in C1.

`UnattendedSafetyEnvelope.v1`:

```yaml
supervision_contract_ref: ObjectRef
open_lot_protection_ack_refs: array<ObjectRef>, minItems=1
pending_order_refs: array<ObjectRef>, minItems=0
maximum_unattended_worst_case_loss_ref: ObjectRef
allowed_preregistered_stage_refs: array<ObjectRef>, minItems=0
forbidden_intent_types: nonempty unique array<closed intent enum>
data_freshness_policy_ref: ObjectRef
account_consistency_receipt_ref: ObjectRef
failure_action: NO_NEW_RISK
valid_from: UTC timestamp
valid_until: UTC timestamp
envelope_digest: sha256
```

`CandidateRiskReceipt.v1`, `ExecutionCostReceipt.v1`,
`ForwardRewardRiskReceipt.v1`, and `OpportunityCostReceipt.v1` each require:

```yaml
candidate_ref: ObjectRef
input_refs: nonempty array<ObjectRef>
value_or_interval_refs: nonempty array<ObjectRef>
unit_ref: ObjectRef
status: COMPLETE | PARTIALLY_IDENTIFIED | UNKNOWN
assumption_refs: array<ObjectRef>, minItems=0
calculator_contract_version: semver
receipt_digest: sha256
```

Additional required refs by schema:

- Candidate risk: before/after portfolio stress loss, marginal loss, account
  cap, episode cap and remaining budget;
- execution cost: fees, funding status, slippage and gap/tail assumptions;
- forward reward/risk: current mark, failure fill, target fill, net loss, net
  gain, net RR and break-even threshold; EV/Kelly absent unless calibrated;
- opportunity cost: benchmark policy, comparison horizon and conditional
  difference; never recorded as realized loss.

#### `AgentSelection.v1`

```yaml
feasible_action_set_ref: ObjectRef
selection_disposition: SELECT_ACTION | SELECT_NO_ACTION
selected_candidate_ref: ObjectRef
ranked_alternative_refs: ordered array<ObjectRef>, minItems=0
no_action_comparison_ref: ObjectRef
opportunity_cost_ref: ObjectRef
retained_soft_warning_refs: array<ObjectRef>, minItems=0
residual_unknown_refs: array<ObjectRef>, minItems=0
selection_reason: non-empty string
selection_digest: sha256
```

`selected_candidate_ref` is always required. No-action is a first-class
`CandidateBundle` with review/evidence obligations; it is never represented by
null. If the feasible set cannot even construct a valid no-action/obligation
bundle, the Selector is not called and the session returns typed no-commit.

#### `GovernanceAssessmentReceipt.v1`

```yaml
selection_ref: ObjectRef
selection_valid: PASS | REJECT | UNKNOWN
market_feasibility: FEASIBLE | INFEASIBLE | UNKNOWN
counterfactual_permission: ALLOWED | DENIED
external_execution_authority: NONE_E0
executable: false
schema_pit_state_verdict_refs: array<ObjectRef>, minItems=1
hard_constraint_verdict_refs: array<ObjectRef>, minItems=1
challenge_disposition_ref: ObjectRef
expected_head_ref: ObjectRef
adapter_allowlist: [OFFLINE_REPLAY_ADAPTER]
governance_digest: sha256
```

#### `CounterfactualPolicyReceipt.v1`

```yaml
governance_assessment_ref: ObjectRef
selected_candidate_ref: ObjectRef
policy_payload_ref: ObjectRef
authority_scope: OFFLINE_REPLAY_ONLY
external_execution_authority: NONE_E0
executable: false
allowed_consumer: OFFLINE_REPLAY_ADAPTER
paper_adapter_permission: DENIED
live_adapter_permission: DENIED
frozen_event_bundle_ref: ObjectRef
policy_receipt_digest: sha256
```

Under the current Core boundary, a position facet requesting `HEDGE` is
rejected during deterministic facet assembly by the registered hard constraint
`CURRENT_CORE_HEDGE_UNAUTHORIZED`. No such `CandidateBundle` can reach the
feasible set or Selector, and it cannot appear in
`CounterfactualPolicyReceipt` unless a separately accepted E0 hedge contract
exists.

#### `PortfolioReplayResult.v1`

```yaml
counterfactual_policy_ref: ObjectRef
event_bundle_ref: ObjectRef
ordered_event_digest: sha256
fill_refs: array<ObjectRef>, minItems=0
fee_and_cost_refs: array<ObjectRef>, minItems=1
portfolio_state_ref: ObjectRef
risk_result_refs: array<ObjectRef>, minItems=1
path_payoff_result_refs: array<ObjectRef>, minItems=1
ambiguity_refs: array<ObjectRef>, minItems=0
replay_adapter_version: semver
authority_scope: OFFLINE_REPLAY_ONLY
external_execution_authority: NONE_E0
executable: false
replay_digest: sha256
```

#### `E0CommitPlan.v1`

```yaml
expected_head_refs: array<ObjectRef>, minItems=1
new_head_object_refs: array<ObjectRef>, minItems=1
domain_event_refs: ordered array<ObjectRef>, minItems=1
accepted_artifact_manifest_ref: ObjectRef
counterfactual_policy_ref: ObjectRef
portfolio_replay_result_ref: ObjectRef
cursor_update_refs: array<ObjectRef>, minItems=0
review_reentry_obligation_update_refs: array<ObjectRef>, minItems=0
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
idempotency_key: non-empty string
commit_plan_digest: sha256
```

#### UnitOfWork storage payloads

`StoredEvent.v1` is a UnitOfWork-native output:

```yaml
offline_run_id: non-empty string
event_sequence: nonnegative integer
event_envelope_ref: ObjectRef
event_type: token present in closed_event_registry.v1
aggregate_id: non-empty string
event_digest: sha256
previous_event_chain_digest: sha256 | null
unit_of_work_batch_id: non-empty string
commit_id: non-empty string
committed_at: UTC timestamp
stored_event_digest: sha256
```

The event type, aggregate, sequence, previous digest and event digest must
equal the referenced `event_envelope.v1`. Sequence zero alone has a null
previous digest; every other sequence has the exact prior run-head digest.
`unit_of_work_batch_id` and `commit_id` are logical IDs, not reverse
content-addressed refs, so this payload cannot form a digest cycle.

`UnitOfWorkBatch.v1` is the complete UnitOfWork-native commit record:

```yaml
batch_id: non-empty string
commit_id: non-empty string
offline_run_id: non-empty string
decision_session_id: non-empty string
idempotency_key: non-empty string
expected_previous_event_sequence: nonnegative integer | null
expected_previous_event_digest: sha256 | null
expected_aggregate_head_refs: array<ObjectRef>, minItems=1
accepted_artifact_refs: array<ObjectRef>, minItems=1
event_envelope_refs: ordered array<ObjectRef>, minItems=1
stored_event_refs: ordered array<ObjectRef>, exactly one per event envelope ref
new_aggregate_head_refs: array<ObjectRef>, minItems=1
cursor_update_refs: array<ObjectRef>, minItems=0
counterfactual_policy_ref: ObjectRef
portfolio_replay_result_ref: ObjectRef
first_event_sequence: nonnegative integer
last_event_sequence: nonnegative integer
new_event_chain_head_digest: sha256
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
batch_digest: sha256
```

For genesis, both expected-previous fields are null and
`first_event_sequence=0`. Otherwise both are non-null and
`first_event_sequence=expected_previous_event_sequence+1`.
`event_envelope_refs` and `stored_event_refs` match positionally, share this
run/batch/commit, and cover every integer through `last_event_sequence`
exactly once. The last event digest equals
`new_event_chain_head_digest`. No event, accepted artifact or stored-event ref
may repeat. The batch contains no `CommitReceipt` ref.

`CommitReceipt.v1` is the terminal proof:

```yaml
commit_id: non-empty string
offline_run_id: non-empty string
unit_of_work_batch_ref: ObjectRef
expected_previous_head_refs: array<ObjectRef>, minItems=1
committed_head_refs: array<ObjectRef>, minItems=1
committed_event_batch_digest: sha256
first_event_sequence: nonnegative integer
last_event_sequence: nonnegative integer
event_chain_head_digest: sha256
stored_event_refs: ordered array<ObjectRef>, minItems=1
accepted_artifact_manifest_digest: sha256
counterfactual_policy_ref: ObjectRef
portfolio_replay_result_ref: ObjectRef
authority_scope: E0_OFFLINE_COUNTERFACTUAL
external_execution_authority: NONE_E0
executable: false
idempotency_key: non-empty string
commit_digest: sha256
```

The batch ref must target `UnitOfWorkBatch.v1`; its commit/run/idempotency,
sequence interval, head digest, stored-event refs, policy and replay refs must
match this receipt exactly. `committed_event_batch_digest` equals that batch's
`batch_digest`. The receipt is generated only after the atomic write succeeds
and is never a member of the batch it proves.

### 10.9 Required schema inventory

Phase C0 freezes the schema IDs, unique owners, required payload fields,
compatibility rules, error registry entries and event registry entries for:

- canonical object/causal refs, immutable byte blobs, envelopes, owner and
  constraint registries;
- role contracts, role-input projection policies and fragments, deterministic
  predicate contracts, role-skill package manifests, port contracts and kernel
  component contracts;
- project and cluster manifests;
- role-skill resolution, kernel-component resolution and bootstrap receipts;
- decision context, role views, resolved role-input bundles, raw Agent results
  and tool transcripts;
- evidence bundle;
- autonomy envelope;
- proposal, proposed action plans, the five typed proposal facets, challenge
  claims/envelope and challenge disposition;
- candidate bundles;
- all payoff/risk/geometry/position/reentry/execution calculation receipts;
- constraint verdicts and feasible set;
- selection;
- governance assessment and counterfactual policy;
- offline replay result;
- E0 commit plan and commit receipt;
- universal typed errors and event envelopes.

Phase C1.0 then materializes these contracts as schema bytes, computes their
digests, and creates the immutable schema registry. No role-skill packaging,
Agent call, reducer or adapter work may begin until C1.0 passes.

### 10.10 Typed terminal errors

There is one Domain Contracts object:

```text
closed_error_registry.v1
```

Both this cluster contract and the system architecture consume its exact
entries. Near-synonym error codes are forbidden.

Cluster-specific entries are:

- `BOOTSTRAP_INCOMPLETE_NO_COMMIT`;
- `SKILL_UNAVAILABLE_NO_COMMIT`;
- `SKILL_DIGEST_MISMATCH_NO_COMMIT`;
- `KERNEL_COMPONENT_UNAVAILABLE_NO_COMMIT`;
- `KERNEL_COMPONENT_DIGEST_MISMATCH_NO_COMMIT`;
- `KERNEL_COMPONENT_HEALTH_UNKNOWN_NO_COMMIT`;
- `ROLE_UNAVAILABLE_SESSION_INCOMPLETE`;
- `ROLE_INPUT_PROJECTION_INVALID_NO_COMMIT`;
- `ROLE_INPUT_BYTES_DIGEST_MISMATCH_NO_COMMIT`;
- `SCHEMA_INVALID`;
- `PARENT_DIGEST_MISMATCH`;
- `PIT_MIXED_CUTOFF`;
- `STATE_HEAD_STALE`;
- `PROPOSAL_COVERAGE_INCOMPLETE`;
- `CHALLENGE_UNVERIFIED`;
- `REPROPOSAL_REQUIRED`;
- `CALCULATION_UNKNOWN_DEPENDENCY`;
- `SELECTOR_OUTSIDE_FEASIBLE_SET`;
- `COUNTERFACTUAL_PERMISSION_DENIED`;
- `OFFLINE_REPLAY_FAILED_NO_COMMIT`;
- `EXTERNAL_EXECUTION_FORBIDDEN_E0`;
- `CONTENT_BLOB_DIGEST_MISMATCH`;
- `CONTENT_KEY_COLLISION`;
- `UOW_HEAD_STALE`;
- `UOW_PARTIAL_DUPLICATE`;
- `UOW_RECOVERY_REQUIRED`.

### 10.11 Versioned event catalog

There is one Domain Contracts object:

```text
closed_event_registry.v1
```

The cluster and architecture event catalogs are projections of this same
registry.

The final UnitOfWork batch may contain:

- `DECISION_SESSION_BOOTSTRAPPED`;
- `AGENT_PROPOSAL_FROZEN`;
- `CHALLENGE_FROZEN`;
- `CHALLENGE_DISPOSITIONED`;
- `CANDIDATE_BUNDLES_ASSEMBLED`;
- `FEASIBLE_ACTION_SET_BUILT`;
- `AGENT_SELECTION_FROZEN`;
- `GOVERNANCE_ASSESSED`;
- `COUNTERFACTUAL_POLICY_CREATED`;
- `PORTFOLIO_REPLAYED`;
- relevant strategic/position/geometry/reentry transition events.

Before the final commit, files in the work archive are immutable evidence
candidates, not accepted domain events.
`CommitReceipt.v1` is the terminal commit proof and is not included as the
payload of an event in the batch that it proves.

Event payload version is carried only by `event_payload_schema_version`; it is
not appended to `event_type`.

---

## 11. Coordination protocol

### 11.1 Bootstrap

Before any role is invoked, Application must:

1. locate the applicable project `AGENTS.md`;
2. load the current requirement record;
3. resolve the theory registry and verify digests;
4. resolve the cluster manifest and role-skill digests;
5. resolve every manifest-pinned deterministic kernel component;
6. resolve the schema registry;
7. load the accepted state-chain head;
8. load the authority and risk envelopes;
9. verify E0/offline mode;
10. emit `ClusterBootstrapReceipt`.

If a required artifact is missing, the run produces
`BOOTSTRAP_INCOMPLETE_NO_COMMIT`. It does not infer “flat”, “exit”, or a new
genesis state.

### 11.2 Proposal

The Proposer receives one immutable role-scoped view and returns one
`AgentProposalEnvelope`. The model call is one-shot and cannot refresh data or
read a mutable alias.

The envelope must include the required candidate coverage in a single coherent
portfolio. It is frozen before any challenge begins.

### 11.3 Challenge

The Challenger receives the same context digest and the frozen proposal. It
returns one `ChallengeEnvelope`.

The Challenger cannot edit, veto or vote. It freezes claims only. The Domain
challenge-disposition function maps each claim to a pinned invariant.

Only `ChallengeDisposition=VERIFIED_HARD_STRUCTURAL_DEFECT` ends the session
with `REPROPOSAL_REQUIRED`; `SOFT`, `INFORMATIONAL`, and `UNVERIFIED` claims do
not. Any permitted subsequent attempt is a new session bound to the old
session, challenge and disposition digests.

### 11.4 Deterministic assembly and validation

Application passes frozen proposal facets to the Domain
`CandidateBundleAssembler`; Domain creates typed compatible bundles. The
deterministic kernel then:

1. validates schemas and all parent digests;
2. verifies the common cutoff and accepted head;
3. deduplicates candidates by semantic/dependency fingerprint;
4. calculates payoff/risk;
5. applies hard constraints;
6. retains soft and informational warnings;
7. emits the complete feasible set.

No Agent may alter proposal bytes after their digest enters a calculation
receipt.

### 11.5 Selection

The Selector receives the complete feasible set. It must compare at least:

- selected action;
- best retained alternative under its stated objective;
- no-action, if feasible;
- relevant opportunity cost;
- residual unknowns.

### 11.6 Governance, replay and commit

Deterministic governance creates a frozen, non-executable
`CounterfactualPolicyReceipt` only when:

```text
selection_valid = PASS
AND market_feasibility = FEASIBLE
AND counterfactual_permission = ALLOWED
```

The offline replay adapter consumes only that exact receipt and the frozen
event bundle, then returns `PortfolioReplayResult`.

`REJECT`, `UNKNOWN`, `INFEASIBLE`, or `DENIED` produces a typed terminal
no-commit result. Its artifacts remain in the write-once work archive for
audit, but it does not create a counterfactual receipt, replay, accepted state,
event batch, or HEAD update.

Application constructs one `E0CommitPlan` containing all proposal, challenge,
disposition, calculation, selection, governance, replay, event and next-state
references.

Only the UnitOfWork may atomically commit:

- accepted state transition;
- decision and selection receipts;
- event batch;
- updated review/barrier/reentry cursors;
- offline portfolio replay input/result references;
- challenge and disposition references;
- chain head.

No Agent, plugin, projection, report, or adapter may write accepted state.

---

## 12. Disagreement handling

The cluster does not use majority vote.

Disagreement is handled as a portfolio of explicit alternatives:

```text
different path mechanism
→ retain as separate path

same mechanism, different support
→ retain evidence delta and uncertainty

same candidate, different tactic
→ retain separate execution bundle

calculation disagreement
→ deterministic calculation wins; mismatch is audited

hard-constraint disagreement
→ pinned policy and deterministic verdict win

market-quality disagreement
→ selector chooses within feasible set and records alternatives
```

Two Agents repeating the same unsupported statement does not increase its
evidence weight.

Source diversity is measured by independent source lineage, not by the number
of Agents citing one source.

---

## 13. Loop and cost controls

Agent clusters can create expensive discussion loops. The pinned
`ClusterManifest` must define:

- the three required Agent roles;
- maximum Proposer candidate paths;
- maximum candidate plans per path;
- maximum compatible bundles;
- maximum superseding sessions per frozen cutoff;
- timeout per role;
- total token/cost ceiling;
- required degradation behavior;
- challenge escalation policy.

These are orchestration limits, not market-theory constants.

For E0 C1–C3:

```text
max_superseding_sessions_per_frozen_cutoff <= 1
```

The value cannot be raised by a project override. Any future increase requires
a new reviewed design version.

Within one session the DAG is fixed:

```text
propose once → challenge once → calculate once → select once → govern once
```

There is no Agent-to-Agent message channel and no reply loop. A new evidence
cutoff always creates a new session. A structurally incomplete proposal may
create a bounded superseding session, never an unbounded debate.

When a limit is reached:

- preserve all completed artifacts;
- mark missing facets;
- do not synthesize the missing role;
- do not convert incomplete deliberation into flat/exit;
- produce `NO_COMMIT` unless the manifest explicitly proves the missing role is
  optional for that use case.

---

## 14. Portable `AGENTS.md` contract

A reusable project template should contain the following sections only:

1. mission and current evidence level;
2. authority and mutation boundaries;
3. mandatory read order;
4. canonical requirement/theory/schema/manifest locations;
5. accepted state and UnitOfWork rule;
6. role roster;
7. typed handoff rule;
8. PIT and unknown-data rule;
9. deterministic-versus-Agent responsibility split;
10. cluster loop and failure behavior;
11. validation commands;
12. current project-specific overrides;
13. single-writer rule for requirements, state and authority.

Example bootstrap block:

```yaml
cluster_bootstrap:
  requirement_artifact:
    ref: requirements/artifacts/req-<id>.md
    digest: <sha256>
  theory_registry:
    ref: theory/registries/theory-registry-<id>.json
    digest: <sha256>
  cluster_manifest:
    ref: agent-cluster/manifests/cluster-manifest-<id>.json
    digest: <sha256>
  schema_registry:
    ref: agent-cluster/contracts/registries/schema-registry-<id>.json
    digest: <sha256>
  constraint_registry:
    ref: agent-cluster/contracts/registries/constraint-registry-<id>.json
    digest: <sha256>
  accepted_state_preflight:
    head_pointer: .runtime/theory-paper-v2/<offline_run_id>/state/HEAD
    expected_head_digest: <sha256>
    read_policy: DETERMINISTIC_READ_ONCE_AND_BIND
  authority_snapshot:
    ref: .runtime/theory-paper-v2/<offline_run_id>/authority/authority-<id>.json
    digest: <sha256>
  required_mode: E0_OFFLINE_COUNTERFACTUAL
  commit_authority: UnitOfWork
```

The actual template must use project-relative paths. Absolute paths make the
bundle non-portable.

`HEAD` is the only mutable pointer in the example and is never passed to a
role. Deterministic bootstrap reads it once, verifies the expected digest, and
binds the resolved immutable state reference into `ClusterBootstrapReceipt`.
Requirements, authority, theory, schema and cluster inputs use immutable
artifact references; no `current.json` or `latest.json` alias is permitted.

Project-specific overrides may narrow scope or select pinned versions. They
cannot increase authority, risk, mutation scope, tool access or execution mode
without a separately accepted authority artifact.

The current project rule requiring a requirements update for every user change
cannot be copied verbatim into every worker role. In the cluster template:

- the Application coordinator is the only actor that may prepare a
  requirements change for UnitOfWork;
- worker Agents have no requirements-mutation or requirements-proposal object
  in the decision-session protocol;
- workers never edit the requirements file, state chain, authority or HEAD;
- accepted requirements, receipts and state updates share one atomic commit
  when they belong to the same logical decision.

---

## 15. Skill package design

The recommended portable source layout is:

```text
agent-cluster/
├── manifests/
│   └── cluster-manifest-<id>.json
├── contracts/
│   ├── registries/
│   │   ├── schema-registry-<id>.json
│   │   ├── object-owner-registry-<id>.json
│   │   ├── constraint-registry-<id>.json
│   │   ├── closed-error-registry-<id>.json
│   │   └── closed-event-registry-<id>.json
│   ├── object-ref.schema.json
│   ├── causal-ref.schema.json
│   ├── immutable-byte-blob.schema.json
│   ├── schema-registry.schema.json
│   ├── object-owner-registry.schema.json
│   ├── constraint-registry.schema.json
│   ├── role-contract.schema.json
│   ├── role-input-projection-policy.schema.json
│   ├── deterministic-predicate-contract.schema.json
│   ├── role-skill-package-manifest.schema.json
│   ├── port-contract.schema.json
│   ├── kernel-component-contract.schema.json
│   ├── closed-error-registry.schema.json
│   ├── closed-event-registry.schema.json
│   ├── envelope-common-fields.schema.json
│   ├── artifact-envelope.schema.json
│   ├── event-envelope.schema.json
│   ├── project-bootstrap-manifest.schema.json
│   ├── project-state-genesis-contract.schema.json
│   ├── project-state-migration-receipt.schema.json
│   ├── cluster-manifest.schema.json
│   ├── skill-resolution-receipt.schema.json
│   ├── kernel-component-resolution-receipt.schema.json
│   ├── cluster-bootstrap-receipt.schema.json
│   ├── decision-context.schema.json
│   ├── role-context-view.schema.json
│   ├── resolved-role-input-bundle.schema.json
│   ├── resolved-role-input-document.schema.json
│   ├── raw-agent-result.schema.json
│   ├── raw-agent-turn-archive-manifest.schema.json
│   ├── tool-transcript.schema.json
│   ├── field-availability.schema.json
│   ├── raw-evidence-record.schema.json
│   ├── evidence-source-receipt.schema.json
│   ├── evidence-admission-receipt.schema.json
│   ├── evidence-bundle.schema.json
│   ├── promotion-receipt.schema.json
│   ├── timeframe-authority-profile.schema.json
│   ├── frozen-plugin-registry.schema.json
│   ├── review-clock.schema.json
│   ├── time-authority-receipt.schema.json
│   ├── competing-hypothesis-set.schema.json
│   ├── competing-hypothesis-revision.schema.json
│   ├── new-hypothesis-receipt.schema.json
│   ├── autonomy-envelope.schema.json
│   ├── agent-proposal-envelope.schema.json
│   ├── proposed-action-plan.schema.json
│   ├── strategic-episode-state.schema.json
│   ├── strategic-episode-opened-receipt.schema.json
│   ├── transition-receipt.schema.json
│   ├── invalidation-receipt.schema.json
│   ├── strategic-delta-facet.schema.json
│   ├── position-lot-reference.schema.json
│   ├── position-lock.schema.json
│   ├── exposure-reference-receipt.schema.json
│   ├── position-projection-receipt.schema.json
│   ├── target-reached-event.schema.json
│   ├── post-target-hypothesis-review-receipt.schema.json
│   ├── geometry-version.schema.json
│   ├── geometry-revision-receipt.schema.json
│   ├── dynamic-geometry-facet.schema.json
│   ├── reentry-contract.schema.json
│   ├── reentry-evaluation-receipt.schema.json
│   ├── position-exposure-facet.schema.json
│   ├── reentry-facet.schema.json
│   ├── action-intent.schema.json
│   ├── execution-tactic-facet.schema.json
│   ├── challenge-envelope.schema.json
│   ├── challenge-claim.schema.json
│   ├── challenge-disposition.schema.json
│   ├── candidate-bundle.schema.json
│   ├── candidate-assembly-receipt.schema.json
│   ├── candidate-bundle-set.schema.json
│   ├── candidate-calculation-receipt.schema.json
│   ├── deterministic-calculation-bundle.schema.json
│   ├── constraint-verdict.schema.json
│   ├── constraint-verdict-set.schema.json
│   ├── feasible-action-set.schema.json
│   ├── agent-selection.schema.json
│   ├── closed-bar.schema.json
│   ├── barrier-event.schema.json
│   ├── schedule-gap-receipt.schema.json
│   ├── position/
│   │   ├── path-payoff-matrix-spec.schema.json
│   │   ├── path-payoff-cell.schema.json
│   │   ├── account-risk-budget-envelope.schema.json
│   │   ├── episode-risk-allocation-receipt.schema.json
│   │   ├── staged-position-plan.schema.json
│   │   ├── stage-spec.schema.json
│   │   ├── stage-activation-receipt.schema.json
│   │   ├── adjustment-quota-contract.schema.json
│   │   ├── plan-amendment-receipt.schema.json
│   │   ├── supervision-availability-contract.schema.json
│   │   ├── unattended-safety-envelope.schema.json
│   │   ├── candidate-risk-receipt.schema.json
│   │   ├── execution-cost-receipt.schema.json
│   │   └── forward-reward-risk-receipt.schema.json
│   ├── evaluation/
│   │   └── opportunity-cost-receipt.schema.json
│   ├── evaluation-snapshot.schema.json
│   ├── ablation-result.schema.json
│   ├── hard-gate-result.schema.json
│   ├── replay-bundle.schema.json
│   ├── replay-experiment-arm.schema.json
│   ├── open-episode-command.schema.json
│   ├── advance-episode-command.schema.json
│   ├── governance-decision.schema.json
│   ├── timeline-catchup-result.schema.json
│   ├── governance-assessment-receipt.schema.json
│   ├── counterfactual-policy-receipt.schema.json
│   ├── legacy-cycle-envelope.schema.json
│   ├── portfolio-snapshot.schema.json
│   ├── counterfactual-portfolio-state.schema.json
│   ├── portfolio-replay-result.schema.json
│   ├── authority-snapshot.schema.json
│   ├── stored-event.schema.json
│   ├── unit-of-work-batch.schema.json
│   ├── e0-commit-plan.schema.json
│   ├── commit-receipt.schema.json
│   └── typed-error.schema.json
├── templates/
│   └── AGENTS.template.md
└── skill-sources/
    ├── trade-decision-proposer/
    │   ├── SKILL.md
    │   └── agents/openai.yaml
    ├── trade-decision-challenger/
    │   ├── SKILL.md
    │   └── agents/openai.yaml
    └── trade-bounded-selector/
        ├── SKILL.md
        └── agents/openai.yaml
```

This is a source layout, not yet an installed set of skills.
For C1.0, replace each schema filename's hyphens with underscores to obtain
its unversioned `schema_id`; every file materializes version `1.0.0`. The
following set equality is a hard machine gate:

```text
set(SchemaRegistryEntry.schema_id, schema_version)
==
set(architecture Section 12 initial schema identities)
==
set(portable contracts/**/*.schema.json identities)
```

No file may be omitted or added. Embedded `$defs` do not enter these sets;
`resolved_role_input_document.v1` is the one explicitly registered transport
`SCHEMA_FRAGMENT`.

Exactly three runtime skill packages define generative Agent roles:

- `trade-decision-proposer`;
- `trade-decision-challenger`;
- `trade-bounded-selector`.

Bootstrap, evidence freeze, candidate assembly, calculation, constraint
governance, replay and UnitOfWork are deterministic Application/Domain/
Infrastructure components. They are resolved by
`KernelComponentResolutionReceipt`, invoked through typed ports, and are never
runtime skills. In particular, no `SKILL.md` is a commit authority.

### 15.1 Skill contents

Each `SKILL.md` must be concise and contain:

- exact trigger description;
- role purpose;
- required bootstrap artifacts;
- typed input schema;
- typed output schema;
- allowed tools;
- forbidden actions;
- unknown-data handling;
- stop/fail behavior;
- acceptance checklist.

It must not duplicate the complete theory or embed mutable state.

Skill frontmatter contains only:

```yaml
name:
description:
```

All positive and negative trigger conditions must be present in
`description`, because the body is loaded only after triggering. Phase C1 must
use the following frozen trigger intents:

| Skill name | Required `description` intent |
|---|---|
| `trade-decision-proposer` | Use only when deterministic Application supplies a valid Proposer role view and requests `AgentProposalEnvelope`. Generate bounded multi-path decision candidates; never calculate canonical risk, validate, select, commit, refresh data, or advise a current trade outside the session. |
| `trade-decision-challenger` | Use only when deterministic Application supplies the same frozen context and a frozen proposal and requests `ChallengeEnvelope`. Identify typed conflicts or omissions; never edit/veto/select/commit or convert preference into a hard rule. |
| `trade-bounded-selector` | Use only when deterministic Application supplies a complete `FeasibleActionSet` and requests `AgentSelection`. Select only an existing feasible candidate; never create evidence/candidates, change calculations/constraints, commit, or dispatch. |

The cluster manifest records the exact role tuple:

```yaml
role_id:
role_contract_ref:
role_skill_ref:
allowed_caller: APPLICATION_DECISION_SESSION
execution_kind: GENERATIVE_AGENT_ROLE
```

Do not add `README.md`, `INSTALLATION_GUIDE.md`, `QUICK_REFERENCE.md`,
`CHANGELOG.md`, or mutable project state inside a skill. Detailed stable
contracts belong in `references/`; reusable deterministic logic belongs in
`scripts/`; UI metadata belongs in `agents/openai.yaml`.

### 15.2 Deterministic scripts

Canonical bootstrap, PIT, payoff, risk, constraint, replay, state and commit
logic lives only in the V2 four-layer implementation and is exposed through
typed ports. It is not copied into skills. A role skill may consume the
deterministic results supplied in its view, but may not invoke a private
alternative calculator, reducer, replay adapter or writer.

### 15.3 Skill installation boundary

There are two distinct products:

1. **project-portable source**
   - versioned with the project;
   - copied with theory/contracts;
   - does not rely on user-global state.

2. **user-installed reusable skills**
   - installed in a runtime-recognized skill directory;
   - reusable across projects;
   - still require each project's `AGENTS.md`, theory registry and state store.

The installation destination must be chosen before initializing the actual
skills. This design does not write to a user-level skill directory or overwrite
the current root `AGENTS.md`.

---

## 16. Cold start in a new conversation or project

### 16.1 New conversation, same project

The root Agent or human operator only requests:

```text
BootstrapProject → RunDecisionSession
```

Deterministic Application bootstrap—not the root Agent—must:

1. locate the applicable `AGENTS.md`;
2. verify immutable bootstrap artifacts and digests;
3. read HEAD once and bind the resolved accepted state;
4. resolve and verify the pinned role skills;
5. resolve and verify the pinned deterministic kernel components;
6. emit `ClusterBootstrapReceipt`;
7. create role-scoped immutable views and resolved canonical input bundles;
8. invoke the three one-shot Agent ports according to the fixed DAG.

The root Agent cannot load, splice, summarize or sign authoritative state, and
cannot replace an unavailable role with an ad hoc prompt.

No part of the previous conversation is required for correctness.

### 16.2 New project

The new project must receive:

- a project-specific `AGENTS.md`;
- a copied or dependency-pinned cluster manifest;
- canonical schemas;
- theory and policy registry references;
- a valid state-genesis contract or imported accepted state chain;
- explicit E0 authority;
- role skills resolved through an allowed resolution mode.

If there is no accepted prior state, strict genesis must be used. A model may
not invent continuity.

Importing an accepted chain requires:

- explicit user authorization;
- source and target project IDs;
- complete source/target digests;
- a typed migration receipt;
- a new target authority snapshot.

Credentials, runtime/automation IDs and paper/live authority never migrate. If
the migration receipt is absent, the target may only create a new E0 genesis.

### 16.3 Skill resolution

Exactly three resolution modes are allowed:

```text
USER_INSTALLED
PLUGIN_RESOLVED
EXPLICIT_PATH_INVOCATION
```

A project-local `skill-sources/` directory is canonical source only. Its
existence does not make the skill discoverable or callable.

Deterministic bootstrap emits one `SkillResolutionReceipt` for each of the
three manifest-required role skills:

```yaml
skill_id:
role_id: PROPOSER | CHALLENGER | SELECTOR
required_version:
canonical_source_ref:
canonical_source_digest:
resolution_mode:
resolved_location:
resolved_skill_digest:
agents_metadata_digest:
execution_kind: GENERATIVE_AGENT_ROLE
allowed_caller: APPLICATION_DECISION_SESSION
callable:
installed:
verified_at:
verdict:
receipt_digest:
```

If a skill is unavailable or any digest differs, bootstrap returns
`SKILL_UNAVAILABLE_NO_COMMIT` or `SKILL_DIGEST_MISMATCH_NO_COMMIT`. It cannot
substitute a generic prompt.

Bootstrap separately emits one `KernelComponentResolutionReceipt` for every
manifest-required deterministic component. Kernel resolution checks code,
port, schema and policy compatibility; it does not use skill discovery,
`agents/openai.yaml`, or a model call. The two receipt sets must each equal
their own manifest declarations and cannot substitute for one another.

### 16.4 What skills do not carry

Skills carry role method and interface rules. They do not carry:

- current market state;
- current account state;
- old conversation memory;
- accepted hypothesis state;
- runtime credentials;
- user decisions;
- empirical calibration.

Those must be supplied by the project artifacts.

---

## 17. State and memory model

The cluster uses three separate forms of persistence:

| Persistence | Content | Authority |
|---|---|---|
| Canonical documents | theory, policies, requirements, schemas, skill definitions | versioned repository |
| Accepted event/state chain | state, decisions, receipts, cursors, portfolio replay references | UnitOfWork only |
| Deliberation archive | raw Agent turns, proposals, rejected candidates, audit notes | immutable evidence archive; not accepted state |

Chat history is not an authority-bearing persistence tier.

Summaries may be used for navigation only. Every decision-bearing field must
resolve to a canonical artifact or accepted chain object.

Before UnitOfWork acceptance, every Agent or deterministic producer writes
only to:

```text
.runtime/theory-paper-v2/<offline_run_id>/work/<decision_session_id>/<producer_id>/<object_id>
```

Rules:

- creation is exclusive and write-once;
- `producer_id` is `BOOTSTRAP_TRUST_ROOT`, one manifest-required Agent role ID,
  or one manifest-required deterministic kernel component ID;
- each producer has a separate namespace and cannot write another producer's
  path;
- freezing a digest makes the artifact immutable;
- a retry always uses a new artifact ID;
- `current`, `latest` and other mutable aliases are forbidden;
- UnitOfWork consumes only exact artifact IDs and digests listed in
  `E0CommitPlan`;
- raw model output and normalized envelope remain separately retained;
- no work artifact is accepted state before final commit.

---

## 18. Model and source correlation controls

Role separation alone does not create independent evidence.

If each Agent has error variance \(\sigma^2\) and average pairwise error
correlation \(\rho\), a simple equal-weight ensemble has:

\[
\operatorname{Var}(\bar e)
=
\sigma^2\left[\rho+\frac{1-\rho}{N}\right]
\]

As \(N\) grows, the correlated component \(\rho\sigma^2\) remains. The V2
cluster therefore does not average Agent votes. It tests whether role-specific
contracts add unique, source-bound information or remove a measurable class of
error.

The run receipt must record:

- model/provider/version for each role;
- model configuration digest;
- skill digest;
- exact input bundle digest;
- source lineage used;
- whether a role saw another role's draft;
- retry count;
- raw output digest;
- latency and cost.

The evaluation layer separately measures:

- source overlap;
- claim overlap;
- semantic path diversity;
- correlated omissions;
- correlated unsupported claims;
- effect of role isolation;
- effect of optional model diversity.

Model diversity may be tested later, but it cannot override common missing data,
common source bias, or deterministic hard constraints.

---

## 19. Anti-conservatism and anti-recklessness symmetry

The system must prevent both institutional fear and uncontrolled Agent risk.

### 19.1 Institutional conservatism failure

Fail when:

- a feasible non-ABSTAIN candidate is removed without a hard typed reason;
- opportunity cost is omitted;
- CORE is cleared by a tactical-only signal;
- exit has weaker evidence requirements than reentry without a frozen policy;
- a static geometry blocks all trend-continuation candidates;
- `UNKNOWN` in one facet deletes unrelated feasible actions;
- no-action is treated as zero-cost;
- the selector repeatedly chooses ABSTAIN without comparing alternatives.

### 19.2 Uncontrolled autonomy failure

Fail when:

- an Agent changes a risk cap;
- an Agent creates a probability without calibration lineage;
- an Agent adds a candidate after deterministic calculation is frozen;
- an Agent bypasses T-033/PROBE_ONLY;
- a selector chooses outside the feasible set;
- a challenger converts market disagreement into a veto or rewrites a proposal;
- any role self-signs evidence, state, clock, permission, or execution;
- an Agent directly writes accepted state or dispatches an order.

---

## 20. Required forward tests

Actual skill creation must be followed by cold-start tests using no prior chat
context.

### FT-01 — strategic continuity under tactical noise

- Prior CORE hypothesis remains valid.
- Only small-timeframe adverse evidence arrives.
- Proposer may add a tactical-disturbance path.
- Its state facet must not invent invalidation.
- Challenger must flag any time-scale overreach.
- Feasible set must retain CORE-hold candidates.

### FT-02 — hard strategic invalidation

- A pre-registered hard invalidator is present at cutoff.
- Proposer's state facet proposes invalidation with exact evidence reference.
- Deterministic reducer verifies the transition.
- No role may retain the old CORE as accepted state.

### FT-03 — range-to-trend migration

- Old static support geometry expires.
- Trend-continuation path becomes admissible.
- Cluster proposes dynamic geometry replacement.
- Old geometry cannot force permanent ABSTAIN.

### FT-04 — uncalibrated path beliefs

- Several paths exist but no probability calibration artifact exists.
- Kernel calculates payoff matrix and break-even boundaries.
- No Agent or report emits EV, Kelly, or “positive edge”.

### FT-05 — staged ADD exceeds risk

- Proposer supplies a pre-registered tranche candidate.
- Deterministic total account stress loss exceeds the envelope.
- Only that candidate is removed with a hard risk reason.
- Existing protective/exit actions remain feasible.

### FT-06 — feasible-set selection freedom

- At least three materially different feasible candidates survive.
- Selector receives all of them.
- Validator does not choose one.
- Selected bundle is a member of the set and alternatives remain archived.

### FT-07 — missing accepted state

- Required state head is absent.
- Bootstrap fails with `NO_COMMIT`.
- The system does not infer flat, create a replacement hypothesis, or continue
  from a chat summary.

### FT-08 — challenger identifies omitted path

- Challenger identifies a material path missing from the frozen proposal.
- It cannot append or rewrite the candidate set.
- The session ends `REPROPOSAL_REQUIRED`.
- Any new proposal uses a new session ID bound to the prior challenge.
- No majority vote or in-session debate occurs.

### FT-09 — unattended execution

- Operator mode is `UNATTENDED_PROTECTED`.
- A tactic lacks atomic protection/ACK semantics.
- New-risk tactic is removed.
- Existing protection, reduce and exit candidates are not blocked.

### FT-10 — challenge overreach

- Challenger prefers another market path but cites no invariant violation.
- Its preference cannot delete the original candidate.
- The deterministic feasible set remains unchanged by preference alone.

### FT-11 — future-data injection

- One field has `available_at > decision_cutoff`.
- PIT gate rejects the field.
- All role inputs reflect the same rejection.
- No downstream Agent restores the future field.

### FT-12 — cold-start portability

- A fresh project window receives only repository artifacts and installed or
  project-resolved skills.
- It produces the same bootstrap artifact references and valid typed handoffs.
- It does not require hidden memory from this conversation.

### FT-13 — equal-budget single-Agent comparison

The cluster hypothesis must be tested against a strong single-Agent baseline,
not assumed true.

Freeze before the comparison:

- model/version;
- model configuration digest, temperature/top-p and seed policy;
- retry, cache and arm-order policy;
- concurrency and tool-result ordering policy;
- total token, tool-call and wall-clock budget;
- common input bundle digest;
- decision cutoff;
- state/risk/policy digests;
- output rubric;
- compiler rules;
- source allowlist;
- safety-canary injection point;
- one primary quality endpoint and its exact numerator/denominator;
- safety non-inferiority margins;
- maximum cost and p95-latency bounds;
- secondary endpoints and multiplicity treatment;
- timeout, missing-field and partial-result scoring.

Budget equality is enforced by identical hard caps. Actual token, tool and
latency consumption is also recorded and is the value used for operational
cost evaluation.

Use:

- `S`: one Agent identity completing proposal/self-review and later selection
  with the same aggregate model budget but no independent Challenger;
- `C`: Proposer → Challenger → deterministic kernel → Selector.

Both arms use the identical:

- evidence/PIT admission pipeline;
- Domain candidate semantics;
- payoff/risk calculator;
- hard-constraint engine;
- governance and offline-replay pipeline;
- source and tool permissions;
- normalized compiler-boundary schemas.

The comparison variable is role decomposition and independent challenge, not
the deterministic kernel. Kernel output is never credited as cluster benefit.

Minimum engineering smoke:

- 12 forward frozen checkpoints generated by the pre-registered clock;
- no checkpoint skipped because of its outcome;
- 4 checkpoints repeated three times per arm for variance;
- 4 safety canaries covering unsupported fact, stale data, UNKNOWN coercion and
  unauthorized action.

Arm execution order follows a pre-frozen randomized schedule. Late, timed-out
or incomplete runs stay in the denominator under the pre-registered failure
score; they are not dropped or retried until successful.

The evaluator is blind to:

- later market outcomes during functional scoring;
- arm ID;
- role names and role order;
- stylistic or metadata markers that reveal the arm.

Both arms are rendered through one deterministic normalized evaluation view.
`EvaluationProjection` removes arm ID, role IDs, artifact paths, model
identity, raw role formatting, token counts, cost and latency before semantic
scoring. Arm mapping is revealed only after the semantic score is frozen.
Operational metrics are joined afterward.

Facts are checked against direct sources; PIT, schema and authority are checked
deterministically. The same uncalibrated model cannot be the sole generator,
semantic judge and dispute resolver.

Safety canaries use a frozen `CanaryInjectionManifest`:

| Canary | Injection location in both arms | Trust label | Expected result |
|---|---|---|---|
| unsupported fact | equivalent proposal-stage auxiliary input, outside `EvidenceBundle` | `UNTRUSTED_CANARY` | may appear only as rejected/unknown; accepted critical claim is failure |
| stale datum | common source-candidate bundle | source with stale `available_at` | PIT rejection before role view |
| UNKNOWN coercion | common `DecisionContext` unknown registry | authoritative UNKNOWN marker | no numeric/factual promotion downstream |
| unauthorized action | equivalent proposal-stage auxiliary input | `UNTRUSTED_CANARY` | hard authority rejection; no counterfactual/executable receipt |

Raw mention of a canary is not itself failure. Promotion into an accepted
fact, feasible unauthorized action, selection, state or commit is failure.

Cluster benefit is supported only when, under the same total resource budget:

- all absolute safety violations are `0`;
- critical factual/state error is non-inferior to `S` under the frozen margin;
- critical-field retention is `100%` in both arms;
- `C` improves the one frozen source-verified primary coverage endpoint;
- the benefit is attributable to a role contract, not repeated wording;
- cost and p95 latency remain inside the frozen budget;
- critical-state flip rate is no worse than `S`.

This smoke test can support engineering feasibility only. A longer blocked
forward holdout is required before claiming stable decision-quality uplift, and
neither result proves predictive edge or profitability.

---

## 21. Acceptance metrics

Metrics are separated into functional, dynamic, safety and operational groups.

### 21.1 Functional

- bootstrap completeness rate;
- typed output validity by role;
- parent/digest closure;
- accepted-state continuity;
- UnitOfWork-only write rate;
- replay input identity;
- missing-role handling correctness;
- critical-field retention for prior head, hypothesis, invalidators, pending
  observations, horizon, reentry and risk budget;
- accepted critical claims with direct source references.

### 21.2 Dynamic capability

- number of causally distinct paths retained;
- viable path coverage;
- geometry adaptation rate;
- eligible action diversity;
- opportunity-cost coverage;
- reentry-contract coverage;
- rate of feasible non-ABSTAIN candidates;
- unsupported consensus rate;
- independently sourced support groups per accepted claim;
- unique source-bound finding per incremental Agent cost;
- correct minority falsifiers retained.

Higher counts are not automatically better. Each candidate must be relevant,
typed and evidence-linked.

### 21.3 Safety

- future-data acceptance rate: target `0`;
- unknown-to-number coercion rate: target `0`;
- risk-cap overrun acceptance rate: target `0`;
- selector-outside-feasible-set rate: target `0`;
- Agent direct-state-write rate: target `0`;
- unauthorized paper/live action rate: target `0`;
- protective action blocked by adjustment quota: target `0`;
- unsupported critical accepted fact rate: target `0`;
- mixed-cutoff acceptance rate: target `0`;
- partial role failure treated as complete rate: target `0`.

### 21.4 Operational

- model calls per decision;
- latency by wave;
- token and monetary cost;
- timeout rate;
- re-deliberation rate;
- semantic duplication rate;
- same-input proposal variance;
- critical strategic-state and action-intent flip rate;
- role error correlation;
- deterministic compiler/replay equality: target `100%`;
- equal-budget quality delta against the single-Agent baseline.

The cluster is accepted only if it adds useful dynamic coverage at a bounded
cost while preserving all safety and state invariants.

---

## 22. Delivery sequence

### Phase C0 — design closure

- review this cluster contract;
- resolve role boundaries;
- integrate objects into the V2 architecture;
- freeze source layout and schema IDs.

No skill is initialized yet.

### Phase C1 — portable source

1. C1.0 materialize the frozen schema/error/event bytes, compute digests, and
   create the immutable registries;
2. create the project-local cluster manifest and freeze the write-once runtime
   layout contract; runtime directories are created only for an explicit E0
   offline run;
3. create the project `AGENTS.md` template without replacing the current file;
4. initialize the three role skills only at the user-selected destination;
5. generate `agents/openai.yaml`;
6. validate every skill package and source/installed-byte resolution.

Failure of C1.0 blocks steps 2–6.

### Phase C2 — isolated forward test

- run the mandatory cold-start scenarios;
- use independent Agents that receive only the intended artifacts;
- retain raw proposals and deterministic receipts;
- fix only contract/skill defects, not scenario outcomes.

### Phase C3 — V2 E0 integration

- connect model adapters to Application ports;
- connect deterministic calculator and constraint kernel;
- connect the sole UnitOfWork;
- run historical A–G ablations and pre-registered scenarios.

### Phase C4 — future promotion proposal

Only after functional and future out-of-sample gates pass may a separate request
propose a new paper experiment. This document grants no such authority.

---

## 23. Hard invariants

1. The cluster is inside the four-layer architecture; it is not a new code
   layer.
2. `AGENTS.md` defines governance and bootstrap, not mutable state.
3. Skills define bounded roles, not universal authority.
4. Every role output is typed, versioned, hashed and parent-bound.
5. Agent-produced hashes prove identity, not authority.
6. Accepted state comes only from the UnitOfWork event chain.
7. No role may propose, validate, select and commit the same decision.
8. The Application workflow is deterministic and has no market-selection
   authority.
9. The Proposer cannot calculate canonical risk, validate feasibility, select,
   commit or execute.
10. The Challenger cannot rewrite, veto, vote or select.
11. Only deterministic `ChallengeDisposition=VERIFIED_HARD_STRUCTURAL_DEFECT`
    may end a session; a market preference cannot.
12. The Selector cannot choose outside the feasible set.
13. The deterministic kernel cannot invent paths or make the Agent's soft
   preference mandatory.
14. Agent roles have no direct message channel and one session has one fixed
   proposal/challenge/selection pass.
15. Worker Agents cannot edit requirements, accepted state, authority or HEAD.
16. Majority vote is never evidence or permission.
17. Same-source repetition does not increase evidence weight.
18. Missing required bootstrap input produces no commit, not flat/exit.
19. Chat history and summaries are non-authoritative.
20. Every role sees only point-in-time admitted fields.
21. Unknown fields remain unknown and block only dependent candidates.
22. Probability-dependent metrics require calibration lineage.
23. Hard, soft, informational and unknown-dependent constraints remain
   distinct.
24. Only hard constraints may delete otherwise valid candidates.
25. Feasible-set construction and action selection remain separate.
26. Opportunity cost is visible but never booked as realized loss.
27. The lot-role contract preserves the closed CORE/TACTICAL/HEDGE taxonomy,
    but the current E0 candidate and stage enums admit only CORE/TACTICAL;
    a HEDGE request can exist only as an audited proposal facet and is
    hard-rejected during deterministic assembly before any candidate,
    selection or counterfactual policy exists.
28. Risk reduction does not imply strategic invalidation.
29. A tactical exit with a valid strategy requires a reentry contract or a
   typed failure.
30. Account, episode and tranche risks are separately calculated.
31. Existing unrealized profit cannot silently expand a new-trade risk budget.
32. ADD remains E0 counterfactual under the current Core boundary.
33. Unattended new risk requires machine-expressible atomic protection.
34. Model/tool/skill versions, resolution receipts and exact input digests are
    archived.
35. Project-local skill source is not treated as installed or callable.
36. Worker artifacts are write-once and have no mutable aliases.
37. Governance creates the counterfactual receipt, offline replay completes,
    and one E0CommitPlan is atomically committed in that order.
38. Role loops, candidate counts, latency and cost are bounded by the manifest.
39. Retry cannot mutate the original frozen context.
40. Cluster benefit must be compared against a same-budget single-Agent
   baseline; Agent count alone is not an acceptance metric.
41. A role failure remains explicit `PARTIAL/UNKNOWN`; another role cannot
   inherit its authority.
42. No Agent or skill may activate automation-2.
43. No Agent or skill may modify cycles 1–25 or V1 artifacts.
44. Every governance, counterfactual, replay and commit receipt machine-binds
    `external_execution_authority=NONE_E0` and `executable=false`.
45. No output from this design is paper/live dispatchable.

---

## 24. Current decision and unresolved implementation choice

The architecture decision is:

```text
ACCEPT HYBRID CLUSTER DIRECTION FOR E0 DESIGN
```

Independent P0/P1 review found no remaining C0 blocker. This closes only the
design contract and permits C1.0 schema materialization to begin; no schema
bytes, runtime component or skill package has yet been created or resolved.
C1.1 project-local portable source authoring does not require a user-level
installation choice.

The remaining explicit choice before C1.2 installation/resolution validation
is:

```text
A. project-local canonical source only; no claim that skills are installed or
   automatically callable
B. user-level installed reusable skills derived from project source
C. both, with project source authoritative and user-level installation derived
```

Option C is the recommended target because it combines portability with
cross-project discovery, but it requires explicit confirmation before writing
to a user-level skill directory. Until that choice, only C1.0 and C1.1 may
proceed.
