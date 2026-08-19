# P0-RSI-01B-AST build report

Status: `BLOCKED_BASE_AST_MATERIALIZATION`.  No candidate is available for
pinning.  A prior pointer-only draft was withdrawn after Sol spot-check showed
that it omitted required v0.2.1 fields and nested constraints.

## Recomputed source evidence

- Source contract ID: `rsi-mtf-drl-pm-v0-2-1-outcome-free-contract`
- Source composite: `1db68758cae0e4b79e3206221498071ced9f7720b8d8e2fa95a1bb53995a45a7`

The source composite was independently recomputed as
`ID("rsi-mtf-drl-pm-composite-theory/v0.2.1", {core_raw_sha256,
v0_2_contract_canonical_sha256,addendum_raw_sha256})`.  Inputs matched the
required raw/canonical digests: CORE `06014b...822d`, legacy raw
`33d84c...047`, legacy canonical `38d572...1e5`, and immutable addendum raw
`021053...0fd`.

## Precise materialization blocker

The current immutable prose names semantic fields and constraints, but an AST
candidate must materialize each complete base node under a selected reviewed
normalization profile.  This milestone cannot honestly claim that condition.
The failed draft demonstrates the exact unresolved work: `EntryExecutionBinding`
must include all 20 specified top-level fields (not merely the two fields that
appear in transform pointers); `SharedEntryAction` must include all 16;
`PathInputBundle` all 26; and the canonical bundle, artifact/event/coverage,
ledger record, label envelope, field sets, and algorithm nodes must include all
unchanged nested fields and constraints.  A pointer's presence cannot prove
that its enclosing frozen node is complete or byte-equal.

No semantic default was selected to fill those missing nodes.  The required
next input is a complete reviewed normalization profile/node inventory (or
enough implementation time to materialize every normative clause and submit it
to a node-by-node Sol audit).  Until then, source identity is resolved but
AST completeness is not.

## Review limits and deferred work

The direct v0.2.2 overlay and collision-checked base+overlay merge are not
included because an incomplete base must not be used as a merge input.

## Verification

Executed successfully before withdrawal:

```text
read-only SHA-256 and composite-ID recomputation
```

No AST validator or test remains, because validating only the withdrawn
pointer skeleton would be misleading.  No broader suite was run; the worktree
contained unrelated in-progress changes.
