# Generalized Competing-Path v0.5.0 Validation Report

## Scope and authority snapshot

- Validation date: 2026-07-26
- CWD: `/Users/wt/Documents/agent-trade-emotion`
- Branch: `codex/s0-research-foundation`
- HEAD at task start: `7ca3fc4f99a57f98217e703f222b295653ace87e`
- Evidence level: `E0`
- Current milestone result: `NOT_RUN`
- Synthetic execution status: `SYNTHETIC_TESTS_PASS_AWAITING_SOL_REGATE`
- Next state: `AWAITING_SOL_V5_M00_REGATE`

This run used only local theory, exact contracts and hand-written synthetic
fixtures. It did not read new market data or outcomes. The included
`SEEN_NARRATIVE` PatternInstance is an explicitly anecdotal diagnostic case;
its known narrative result did not adjust formal rules or synthetic
assertions.

No active G1 path, B4, download, source adapter, backtest, calibration,
holdout, account, paper, live, deployment or trading action was read or
changed.

`CORE_TRADING_THEORY.md` is the current root mirror. The immutable v2.1
authority is `CORE_TRADING_THEORY_v2_1.md`, pinned by
`config/core_trading_theory.authority.v2_1.json`. Both files are byte-equal at
140126 bytes with SHA-256
`2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d`.
The challenger, method contract and hypothesis registry pin the same authority
identity, path, digest and size.

## P0 semantic closure

The executable contract now enforces:

- data, state, perspective, primitive mechanism, compound path, scenario and
  action are separate objects;
- primitive mechanisms are non-exclusive multi-label hypotheses whose ordinal
  support is never normalized; event repricing, liquidity-vacuum/cascade and
  continuation may coexist without simplex displacement;
- `ARTIFACT` is an epistemic/data-quality alternative and cannot directly or
  indirectly weight market utility: any mixture-eligible market or residual
  path containing it fails closed before competition validation or utility;
- compound PathSpec objects contain nonempty, unique, registered
  `primitive_mechanism_ids`;
- before any PathEvent is accepted, a complete exact PathSpec is canonically
  rehashed and must match its `path_id` in the independently loaded finite
  method-contract allowlist; the digest binds nested fields and every list
  order, so a pending path cannot self-sign a changed horizon, falsifier,
  milestone, edge or capacity guard;
- runtime primitive power sets, Cartesian products, LLM compounds and
  unregistered compound paths fail closed;
- compound path weights exist only for a predeclared competition set that
  references a registered finite `partition_proof_id`; arbitrary
  `exclusivity_basis` text is outside the exact schema;
- each partition proof carries a canonical SHA-256 over the complete exact
  proof object excluding only its own digest field; a finite method authority
  allowlist binds the exact proof ID/digest, path-registry digest, eligible
  path IDs, partition domain ID/values and residual scope;
- residual-only authority is forbidden: an eligible proof scope must include
  at least one market path and the exact residual; residual-only shrink,
  domain/cell rename, market-cell swap, partition-domain ID drift and
  same-identity proof-content drift all fail after attacker-side rehashing;
- each partition proof also binds the exact competition-set ID, ordered path
  IDs, partition/calibration versions and a recomputed canonical
  `path_registry_digest` over ordered
  `path_hypothesis_id + primitive_mechanism_ids + role` definitions;
- the helper executes the finite partition check: every cell is nonempty,
  cells are ordered by path ID and pairwise disjoint, and their union equals
  the frozen universe; exact booleans are required rather than trusted;
- the only residual is `OTHER_PATH` with `role=RESIDUAL_PATH`,
  `primitive_mechanism_ids=["OTHER"]` and
  `residual_domain_values=["OTHER_OR_UNRESOLVED_TERMINAL"]`; `OTHER` is
  forbidden in market paths;
- V5-M00 numeric scenario math accepts only an exact, causally available
  `SYNTHETIC_COUNTERFACTUAL_ONLY` ScenarioDistribution; qualitative E0 uses no
  numbers and calibrated market probability mode remains forbidden;
- a canonical UtilityReceipt binds the complete scenario, utility vector,
  stress cost, tail, uncertainty, `as_of` and authority; exact
  PermissionEnvelope values are `DENY/UNKNOWN`, `ABSTAIN` only and zero risk;
  ActionCandidate validates and binds all three carriers but always abstains;
  research geometry is separate from permission;
- dependency groups contribute once per target; every row is validated for
  exact schema/type/enum/clock/quality and determinable `target_ids` before
  target filtering, so malformed string/tuple/mixed target carriers cannot be
  silently dropped while remaining rows update support;
- the independently reloaded method artifact binds a frozen E0 synthetic
  lineage authority; canonical admitted projections deterministically bind
  `evidence_id`, dependency group and a projected underlying-increment
  identity after canonical UTC rendering; `target_ids` is exact ledger routing
  rather than raw identity, while attacker-supplied identifiers or an
  in-memory replacement authority fail closed;
- a versioned EvidenceLedgerReceipt V2 binds exact
  observation-frame/episode/path/mechanism scope, full method ID/raw SHA,
  decision time, recursively type-tagged canonical input batch, rederived
  effects/effect digest, admitted identities, group and terminal winners,
  unclipped/clipped support, before/after state digests, sequential receipt
  ID, previous hash and complete receipt hash;
- the reducer starts only from strict `ACTIVE/0/empty-chain` genesis, re-decodes
  every stored batch and independently recomputes every effect and state
  declaration; empty-effects 0-to-9 forgery, a foreign effect absent from the
  batch, and whole-chain declaration rewrite plus complete attacker rehash all
  fail as non-derivable rather than being trusted as self-consistent;
- same-ID replay and same-ID semantic drift are rejected. A distinct
  authority-valid candidate with the same underlying increment and same group
  competes for the single full-ledger group winner and is not additive; the
  same underlying increment under a different group fails closed;
- group winners use maximum absolute signed delta and lexical evidence ID;
  one-batch, weak-then-strong and strong-then-weak segmentation produces the
  same final winner, raw support, clipped support, status and state digest.
  Raw support remains available after clipping, and a weaker later candidate
  does not reduce the stored winner;
- the first cross-receipt Evidence replay appends exactly one permanent
  rejection receipt and an identical idempotency context is a byte-identical
  no-op. Idempotency binds scope, transition kind, batch, canonical decision
  time and rejection class rather than batch alone. A causal-future rejection
  is `RETRYABLE_AT_LATER_DECISION_TIME` and rederives at a later decision time,
  while permanent/resource rejection does not;
- exact evidence identity is unique across the full target-scoped batch, so
  same-ID rows in one or different dependency groups, conflicting payloads,
  and SUPPORT plus HARD_FALSIFIER collisions all reject the relevant batch as
  `UNKNOWN` without changing support; typed enums, source version and aware
  `available_at <= decision_time` are required; missing, malformed, naive and
  nonvalid evidence is permanently rejected as `UNKNOWN`, while future
  evidence is retryable without changing support at the early decision;
- hard falsification is irreversible within the current path
  instance/opportunity episode, while a new ObservationFrame may independently
  instantiate the same registered primitive only with distinct nonempty
  frame/episode/path IDs, zero initial support and an empty new receipt chain;
  same-ID or old receipt-prefix reuse fails closed;
- terminal class is monotonic in the same opportunity/path instance. Under
  event-time semantics B, late ordinary Evidence strictly before terminal
  cutoff may correct current derived support without reactivation or action;
  ordinary Evidence equal to or after cutoff is rejected. A complete lifecycle
  carrier must include the exact
  PathSpec, ordered exact PathEvents, path start, requested horizon and
  terminal time and must re-pass the pinned PathSpec allowlist, causal clock,
  earliest stopping, predeclared hard-trigger and exact-expiry checks. The
  episode mechanism must also be present in the PathSpec primitive mechanisms;
  a cross-mechanism lifecycle carrier and the old path-ID/digest-only
  self-signed carrier are rejected;
- terminal reason/status may be corrected by a later-arriving earlier valid
  event while remaining terminal. Lifecycle uses the final validated
  PathEvent `event_at`; exact expiry equals start plus horizon; HARD Evidence
  conservatively uses canonical `available_at`. Equal times use the frozen
  semantic priority `HARD_FALSIFIER < EXPIRY < TERMINAL_MILESTONE`, then stable
  method authority. Current winner uses a semantic identity that excludes
  arbitrary PathEvent IDs and source digests; synonymous provenance can remain
  in receipts without changing current state digest. If a terminal changes the
  cutoff, current state recomputes cutoff-eligible identities, groups, winners
  and raw/clipped support. Historical receipts remain byte-identical
  decision-time views. Mixed SUPPORT/SOFT/HARD in one batch or all receipt
  orders produce the same terminal winner, support and current state digest.
  `EXPIRED_OR_UNKNOWN` remains a terminal schema value but has no V5-M00
  synthetic transition source;
- observation count is event-time variable; PathSpec and PathEvent are both
  exact-key closed, timestamps obey
  `path_started_at <= event_at <= available_at <= decision_time`, and the last
  and only stop is the earliest registered hard falsifier, terminal milestone
  or exact frozen expiry; `NEVER_STOP`, `FIXED_8_DAY`, horizon extension and
  events after termination/expiry fail closed;
- exact target routing requires the singleton path instance; adding a target
  alias fails closed. Equivalent timezone spellings canonicalize to the same
  evidence/group/underlying/content identity and are replay-rejected rather
  than counted twice;
- receipt decision time is canonical UTC and nondecreasing at append and
  reducer boundaries; increasing and equal instants are valid, equivalent
  timezone text canonicalizes identically, and regression fails closed;
- accepted lifecycle ID/digest enters the internal ledger identity set; exact
  replay in the same decision context is byte-identical, same-ID content drift
  is permanent rejection, and a distinct earlier valid terminal may compete;
- a 257-event lifecycle against capacity 256 produces
  `RESOURCE_CAPACITY_REQUIRED/UNKNOWN_RESOURCE` rejection at ledger admission,
  never `FALSIFIED/EXPIRED/TERMINAL`;
- RSI `None` still runs scheduled, state-change, event-arrival,
  data-quality-change and position-risk evaluation; PatternInstance candidates
  are nonempty, unique and registered;
- risk budget, liquidity/venue/margin caps and final size must be finite,
  non-boolean and strictly positive;
- post-position stop, target, horizon and size are one-way, and a path switch
  cannot auto-reverse.

## Actual commands and results

### Current v0.5 synthetic contract

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_generalized_competing_path_v0_5_0_contract
```

Result: `58/58 PASS`.

The file contains 58 executed test methods and the synthetic contract contains
103 declarative fixture records. Fixture presence is not counted as executable
coverage. Executed fail-closed mutations exercise competition/proof schema
drift, `NOT_A_PROOF`, arbitrary `exclusivity_basis`, exact booleans,
set/path/cell ordering, missing residual, empty/overlapping/gapped cells, exact
residual semantics, partition/calibration drift, canonical path-registry
digest drift, full-proof content/method-authority drift, and market/residual
`ARTIFACT` or misplaced `OTHER`. The full-proof test performs actual canonical
rehashing of residual-only shrink, domain/cell rename, market-cell swap,
partition-domain ID drift and same-identity content drift, then proves the
fixed method authority rejects each result.

The remaining methods execute exact ScenarioDistribution/UtilityReceipt/
PermissionEnvelope/ActionCandidate carriers, all-new-risk `ABSTAIN`, geometry
separation, coexistence/non-simplex primitive support, multi-primitive compound
paths, primitive support used as utility weights, runtime power-set/compound
injection, causal evidence rejection, episode falsification scope, exact
PathSpec/PathEvent lifecycle and expiry, variable 2/8/20/21-event paths,
RSI-absent event arrival, PatternInstance candidate closure and authority
lineage. The identity and ledger attack families additionally prove
validate-before-filter for malformed target scope; exact singleton target
routing and typed list/tuple distinction; equivalent-timezone identity
canonicalization; target-scoped duplicate
`evidence_id` rejection under same-group, cross-group, conflicting-content,
SUPPORT-plus-HARD_FALSIFIER and input-order variants; cross-receipt replay,
semantic drift and same-group underlying replacement without additive double
count; full-ledger segmentation invariance, raw support after saturation,
strict genesis, empty/no-op and rejection-only behavior; lifecycle authority,
earliest-terminal cutoff compensation, cross-mechanism rejection and
semantic-priority tie breaking despite source-digest grinding;
receipt transition rederivation under empty-effect, foreign-effect and
full-chain attacker rehash; caller-supplied expected-tip rollback detection;
receipt scope/order/hash tamper rejection and order-invariant batch identity;
per-call method-authority reload; and preservation of the existing exact
Evidence carrier and existing exact UpdateReceipt schema. Separate PathSpec
tests prove an
attacker-recomputed digest cannot replace the independent method authority
after horizon, hard-falsifier, nested capacity-guard or ordered
milestone/primitive mutations.

The five third-round tests additionally execute canonical/nondecreasing
decision clocks at both boundaries; Evidence and lifecycle
future-to-visible retries; permanent rejection freezing; accepted lifecycle
identity, exact-context no-op and content drift; semantic terminal provenance
merge; event-time-B late ordinary correction; mixed SUPPORT/SOFT/HARD in one
batch and all 120 receipt permutations; and ledger-level capacity overflow
resource routing.

The synthetic lineage authority is intentionally not claimed as raw
provenance: the exact Evidence carrier lacks raw-record and transform
identities and may conservatively merge distinct raw observations with the
same projection; a small `available_at` change can also create a different
projected underlying group for what may be one real source. The complete
PathEvent lifecycle checks are likewise synthetic logical authority, not proof
that a real external event occurred. A separately frozen raw AuthorityBundle
remains mandatory before any runtime admission.

The reducer validates only the canonical prefix supplied to the current pure
call. A caller-provided previously trusted `expected_tip_hash` detects a
truncated prefix or alternative full chain, as the executable tests show.
There is no external immutable tip/seal at V5-M00, so an attacker able to
replace the complete batch, chain and claimed tip can create another internally
valid chain. No cross-process rollback, fork prevention, runtime append-only
storage or raw provenance closure is claimed.

The pairwise new-opportunity validator is exercised when a caller explicitly
provides a terminal predecessor: new frame/episode/path IDs, `ACTIVE/0` genesis
and an empty new chain are required. The pure helper has no global
ObservationFrame/opportunity scope registry and cannot prove uniqueness when
the predecessor is omitted; that remains an external runtime authority
boundary.

### Historical v0.4 regression

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_four_layer_v0_4_0_contract
```

Result: `26/26 PASS`.

Combined current V5 and historical v0.4 result: `84/84 PASS`.

All six historical v0.4 artifacts remained physically unchanged:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `019c117a0bc6ad4b2f19dad5edbbe2d8cfec8a64ca06e432ed9f2a0626feb153` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `3ddbfe7c4ad292af86465a7d29e12eeec84d6a1a0949b06d383ecda1033390e0` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `df049e7f880134f08362ba5df82fc1d94afb31bcf3cb59ce57b30eb4a3acd885` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `3819318ace8e42621a4b18eacab96aab0460c2f54e588bf6d9341d4b6b1e38b2` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `687a03f08f34d1aee77984bffea72a22b22c48af4f0c50fca27259631734fd92` |
| `artifacts/rsi_mtf_four_layer_v0_4_0_validation_report.md` | `4be1ae547a3bd7c8d1f19f551ec5394f162e8f1545eceb4a2afa5227e03c6b86` |

### Legacy v0.2 and direct-AST compatibility batch

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_research_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_kernel \
  tests.test_rsi_mtf_drl_pm_direct_ast
```

Result: `59` run, `56` pass, `3` errors.

Classification: `LEGACY_AUTHORITY_BYTES_UNAVAILABLE`.

Two research-contract tests correctly report
`review tooling SHA-256 drift: CORE_TRADING_THEORY.md`; one strategy-contract
test correctly returns `E_KERNEL_CONTRACT_INVALID` for the same legacy root
authority mismatch. Those historical contracts bind the former CORE bytes at
the mutable root path. Governance requires retaining the current v2.1 root
mirror and not rewriting the old v0.2 contracts, hashes or tests. The new V5
authority uses an immutable versioned snapshot instead. All 11 direct-AST
tests and the remaining 45 legacy tests passed; the seven pinned legacy v0.2
artifacts checked by the V5 suite retained their frozen hashes.

An initial unqualified `python3` invocation resolved to system Python 3.9,
loaded only 31 tests and produced four errors: the same two authority drift
errors plus two `typing.TypeAlias` import errors. It is not the declared
project runtime and is not used for the compatibility result above; rerunning
with `/opt/homebrew/bin/python3.12` loaded all 59 tests and produced the
expected three fail-closed authority errors.

This legacy compatibility result does not make the current V5 synthetic suite
fail, but it remains an explicit fail-closed limitation for callers that still
attempt to validate old v0.2 contracts against the current root mirror.

### JSON, AST, integrity and whitespace

```text
python3.12 -B - <<'PY'
# json.loads plus object_pairs_hook duplicate-key rejection over all four JSON
# artifacts; AST parse/guards; exact test/fixture counts; method raw-SHA
# binding; CORE mirror byte/hash/size verification
PY

cmp -s CORE_TRADING_THEORY.md CORE_TRADING_THEORY_v2_1.md
rg -n '[[:blank:]]+$' [the ten scoped authority/theory/contract/test/report files]
git diff --check
```

Results:

- JSON parse: `4/4 PASS`.
- Duplicate-key rejection: `4/4 PASS`.
- V5 AST guard and exact discovery counts: `PASS` (`58` methods, `103`
  unique fixtures).
- Root/versioned authority byte equality, SHA-256 and size: `PASS`.
- Trailing-whitespace scan: `PASS` (no matches).
- `git diff --check`: `PASS`.

## Current non-self-referential hashes

| Artifact | SHA-256 |
|---|---|
| `CORE_TRADING_THEORY.md` | `2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d` |
| `CORE_TRADING_THEORY_v2_1.md` | `2c9673127f85f587651130997d1454d7d0862bdc8677f5132e322d7da5ae0d3d` |
| `config/core_trading_theory.authority.v2_1.json` | `a3e174c616b176253f4aef2ce267a932d43f7e64db3490db815a27f007df12d4` |
| `GENERALIZED_COMPETING_PATH_THEORY_CHALLENGER_v0_5_0.md` | `3d3d62e6d2a55e25acee6552930b464410af8806a408cdfc0dafd96427526853` |
| `config/generalized_competing_path.method_contract.v0_5_0.json` | `18ef5234cb018d1a89252733a6d66903a145864031a2c8d663f021abe79740b0` |
| `config/generalized_competing_path.hypothesis_registry.v0_5_0.json` | `fed1bcceac87582f811f57f420b83481e1621dbd8eb6627ab2fc5ee2357a33b3` |
| `config/generalized_competing_path.synthetic_measurement_contract.v0_5_0.json` | `4159cb6bfb82022db15a95951dcc9e60e53779c900892c48196139f07140d628` |
| `tests/test_generalized_competing_path_v0_5_0_contract.py` | `5e81ca8264d4844c5a230e609f6b881c92118cd05e17596a81c763cbec687412` |

The report's own physical SHA-256 is deliberately external to this file to
avoid a self-referential digest. It must be computed after the final write.

## Tests not executed

No real-market, outcome, adapter, download, backtest, calibration, holdout,
paper, live, account, deployment or active-G1 test was executed because each
is explicitly outside V5-M00 authority. No low-risk visual or performance test
was added; this milestone has no runtime UI or production service.

## Deferred items

Actual primitive labels, compound-path calibration, proper-score comparison,
walk-forward validation and cost-adjusted trading value remain future
DEVELOPMENT/CALIBRATION work requiring separate authorization and unseen data.
The current exact Evidence carrier cannot establish raw-record or transform
lineage; a separately governed raw AuthorityBundle and runtime admission
contract remain deferred rather than being inferred from synthetic hashes.
An external immutable tip/seal and a global ObservationFrame/opportunity scope
registry are also deferred; the current expected-tip parameter is only as
trustworthy as its caller. HARD Evidence uses `available_at` because the
existing exact carrier lacks event time, so a future runtime authority must
unify HARD and PathEvent clock semantics rather than treating this E0
conservative ordering as production design. Capacity overflow currently
proves only fail-closed resource routing; runtime compaction, durable receipt
continuation and resource recovery remain unimplemented.
Legacy v0.2 root-path compatibility requires a separately governed historical
authority-routing decision; old contracts were intentionally not rewritten.

## Known risks and terminal receipt

The current evidence proves only that the E0 contracts are internally
executable and that the registered finite synthetic domain is partitioned
without overlap or omission under the frozen definitions. This is
pre-registered synthetic partition evidence, not a real-market mathematical
proof. It does not prove causal truth, predictive validity, profitability,
production readiness or trading safety.

Terminal state:

```text
V5-M00.result_status = NOT_RUN
V5-M00.test_execution_status = SYNTHETIC_TESTS_PASS_AWAITING_SOL_REGATE
next_state = AWAITING_SOL_V5_M00_REGATE
B4/DATA/BACKTEST/CALIBRATION/HOLDOUT/PAPER/LIVE = FORBIDDEN
```

An independent Sol re-gate is required before any milestone result may change.
