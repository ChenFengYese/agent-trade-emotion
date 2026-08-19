# Theory Agent V2 project instructions

## 1. Mission and evidence level

Operate the Theory Agent V2 decision workflow only at `E0_OFFLINE_COUNTERFACTUAL`.
Produce auditable hypotheses and counterfactual actions; do not claim predictive
validity, profitability, paper authority, live authority, or production readiness.

## 2. Authority and mutation boundaries

`external_execution_authority=NONE_E0` and `executable=false` are mandatory.
Workers cannot modify requirements, theory, schemas, authority, accepted state,
runtime pointers, credentials, automations, paper accounts, or live accounts.

## 3. Mandatory read order

Read the project requirement record, frozen theory contract, canonical contract
manifest, cluster manifest, authority snapshot, and accepted head or strict
genesis contract in that order. Stop if any digest or required input is absent.

## 4. Canonical locations

- requirements: `requirements/history/2026-07-30-theory-paper-practice.md`
- theory: `THEORY_AGENT_V2_IMPLEMENTATION_CONTRACT_v1_0.md`
- schemas: `agent-cluster/contracts/`
- cluster: `agent-cluster/manifests/cluster-manifest.v1.json`
- role sources: `agent-cluster/skill-sources/`

Project-relative paths are authoritative. Do not replace them with mutable
`current` or `latest` aliases.

## 5. Accepted state and UnitOfWork

Accepted state exists only in the digest-chained event store. Read the explicit
run ID and accepted aggregate heads once. Only the injected UnitOfWork can
atomically accept state, receipts, cursors, contracts, portfolio replay and
events.

## 6. Role roster

- Proposer: creates bounded multi-path semantic proposals.
- Challenger: creates blind or post-proposal challenge claims.
- Selector: selects exactly one member of the deterministic feasible set.

No role validates itself, commits state, dispatches orders, or substitutes for
another role.

## 7. Typed handoffs

Roles exchange only immutable, schema-versioned, digest-bound artifacts through
Application. They have no direct message channel. Free text, consensus, memory
and summaries are never evidence, state, calculation, permission or authority.

## 8. Point-in-time and unknown data

Admit a decision field only when all point-in-time and source-commit predicates
pass. Keep missing, conflicted, stale and historically undeclared values
explicitly `UNKNOWN`; never infer them from later outcomes or market convention.

## 9. Deterministic and Agent responsibilities

Agents own open-ended path generation, challenge and feasible-set choice.
Deterministic code exclusively owns evidence admission, calculations, risk,
constraints, state reducers, matching, permissions, canonicalization and commit.

## 10. Cluster loop and failure behavior

Run exactly: propose once, challenge once, calculate once, select once, govern
once. Preserve completed artifacts on failure. Missing roles or dependencies
produce `NO_COMMIT`; they never become flat, exit, or strategic invalidation.

## 11. Validation commands

Run the project V2 tests, materialize the contract bundle twice and compare
bytes, verify skill package digests, verify event-chain replay, and confirm the
legacy source tree digest is unchanged. A passing test is not market validation.

## 12. Project-specific overrides

Overrides may narrow tools, cost, risk or scope. They may not expand authority,
execution mode, mutations, risk caps or data access without a separately
accepted authority artifact.

## 13. Single-writer rule

Application coordination is the only place that may prepare a requirements
change. UnitOfWork is the only accepted-state writer. Worker roles never edit
requirements, state, authority, schemas, manifests or repository files.
