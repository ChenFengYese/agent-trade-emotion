# MSTA-HED Raw AuthorityBundle P1A-R2 v0.1.2

**Status:** `DRAFT_AWAITING_SOL_P1A_R2_GATE`. This is a pure-local static
contract and executable synthetic validator. It does not authorize any adapter
runtime, active-G1 access, I/O, source/data download, market/outcome row,
backtest, calibration, holdout, paper/live operation, deployment or trade.

## Exact chain

Nine authority objects remain: source snapshot, artifact, raw revision,
coverage event, cursor, receipt, bundle, seal and admission. Request/result are
two exact interface schemas. `TrustedSealAuthoritySnapshotV1` and
`V05CarrierBindingV1` are explicit supporting schemas. Every object has a
closed ordered field set and domain-separated self digest; validation rejects a
wrong `schema_type`, missing or extra field, malformed digest, invalid opaque
path, or an unbound child.

Logical paths are opaque identifiers, never decoded filesystem paths. `%`, `~`,
absolute/device/backslash forms and empty, dot or parent segments are rejected
both by object validation and by complete-chain validation.

The bundle must carry the **current** P1A canonical contract digest and exact
one-to-one source/artifact/raw/cursor/receipt/coverage/transform membership.
All coverage children are validated as an array, not as a singleton shortcut.
The adapter request, receipt and result bind source, adapter contract, payload
hash and byte length, decision time, prefix, prior/next cursor and a
domain-separated idempotency formula. Accepted results have no reasons;
rejected results have reasons; an `EMPTY` result can only describe zero-byte
input and no receipt.

## Clocks, revisions and coverage

Actual records obey `received <= ingested <= derived <= actual_available <=
decision`. Event/publication may be null. Reconstructed availability carries
counterfactual basis but is never admitted as actual. Artifact/request/coverage
clocks cannot be future relative to the decision. Initial revisions are genesis
only; the three record identities are distinct; fork/generation/tombstone
rules fail closed. A generation boundary is only valid for an explicit
`TRANSPORT_GAP + CURSOR_RESET` transition with matching old/new generation,
scope and clock.

Coverage preserves exactly the nine state classes. Cause codes are independent.
Each proof-required state has a closed proof kind and proof reference/digest;
`CONFIRMED_NO_ACTIVITY`, expected cadence, native sequence gaps and market
halts require their corresponding proof. Coverage disposition is recomputed
from the entire sealed membership. `SCHEMA_REJECT`, rate limit, cursor reset,
integrity and receipt-latency causes can never be caller-cleared.

## Seal and admission

The seal is checked against an exact trusted-authority snapshot: authority,
algorithm, key ID, public-key fingerprint, verification material, external-tip
contract and external-tip digest must all agree. The deterministic E0 verifier
is only a reproducible test aid, not production cryptography. Decision time
must precede both seal/admission expiry and admission expiry cannot exceed seal
expiry.

The v0.5 binding recomputes carrier and result digests from explicit closed
synthetic payload objects; it does not add or change a v0.5 carrier key. An
admission must match raw logical/revision identity, transform, every coverage
member, bundle, seal, tip, lane, binding and have no admitted error reasons.
`ACTIVE_G1`, Application Support and SEEN aliases are forbidden even when a
lane name says `DEVELOPMENT`.

The later market-path order remains `H01,H03,H05,H02,H04,H06,H08,H07` bound to
the v0.5 registry. `V5-H09-LAYERED_ERROR_ATTRIBUTION` is a mandatory quality
guard, not a market-path hypothesis. This static result supports none of them.
