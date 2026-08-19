# MSTA-HED Raw AuthorityBundle P1A Contract Specification v0.1.0

**Status:** `DRAFT_AWAITING_SOL_P1A_GATE`  
**Stage:** `V5-P1A / E0 / pure local no-I/O contract-design freeze`  
**Implementation / I/O:** both `false`  
**Scope:** static schema, synthetic counterexamples, and future-admission boundaries only.

This document does not authorize a source adapter, market or outcome access,
download, backtest, calibration, holdout, paper, account access, deployment, or
trading.  It does not alter any exact v0.5 carrier.  It is a wrapper boundary
that may later bind an already-valid v0.5 result, never a replacement for it.

## 1. Goal and non-goal

The next practical precondition is not another signal feature.  It is an
immutable, point-in-time answer to: *which raw bytes and source contract were
available, in which revision, through which pure transform, under which
coverage qualifications, and under which external seal?*

P1A freezes the answer as nine exact-key objects:

1. `SourceAuthoritySnapshotV1`
2. `RawArtifactDescriptorV1`
3. `RawRecordEnvelopeV1`
4. `CoverageEventV1`
5. `AdapterCursorV1`
6. `AdapterReceiptV1`
7. `RawAuthorityBundleManifestV1`
8. `RawAuthoritySealV1`
9. `EvidenceAdmissionContextV1`

There is intentionally no implementation module, adapter execution, storage
writer, downloader, market row, outcome label, or market-validity claim.

## 2. Fixed identity and canonicalization rules

All objects are closed schemas.  A missing, extra, incorrectly typed, or
unknown-enum field is fail-closed.  Identity is lowercase SHA-256 over UTF-8
canonical JSON with `ensure_ascii=true`, `sort_keys=true`, and separators
`(',', ':')`; every digest is domain-separated as
`SHA256(domain + '\\x00' + canonical_json(payload))`.

Each self digest excludes **only its own digest field**.  A pending object may
not provide the digest of its authority, source, bundle, or seal.  Reference
direction is acyclic:

```text
contract
  -> source snapshot
  -> artifact / raw record / coverage
  -> cursor / adapter receipt
  -> bundle manifest
  -> external seal
  -> evidence admission context
  -> unchanged v0.5 result
```

`contract_sha256` is the hash of this JSON contract excluding only that field.
All timestamps must be UTC `Z` text with an explicit zero offset.  Naive,
offset-bearing noncanonical, malformed, or future-for-decision timestamps are
rejected.  Numeric market values and quantities are decimal strings, never
JSON numbers, exponent notation, IEEE float, `NaN`, or infinity.  Paths are
logical relative identifiers only: absolute paths, `..`, empty segments,
backslashes, and platform-device forms are rejected.

## 3. Point-in-time clocks and revisions

Every record distinguishes:

- `event_at`: source occurrence time when supplied; it is not a publication
  claim.
- `published_at`: source publication time; `null` means unknown, never a
  substituted receive time.
- `received_at`: local observation/capture time.
- `available_at`: earliest local decision visibility time.
- `decision_time`: the future admission cutoff.

For `ACTUAL`, `received_at <= available_at <= decision_time`; source event and
publication times, when known, must not be later than availability.  For
`RECONSTRUCTED`, a nonempty `reconstruction_basis` is required and it may only
serve research replay after a separately authorized lane; it cannot be passed
as actual contemporaneous availability.  Unknown publication remains `null`.
Late facts append a later envelope/receipt and never rewrite an earlier
receipt, bundle, or seal.

Three identities are deliberately separate:

- `raw_record_id`: immutable byte observation identity;
- `logical_record_id`: the source business record being revised;
- `revision_id`: one version of that logical record.

An exact duplicate repeats the same raw and revision content and must be
idempotently classified, never counted twice.  Revision operation is exactly
`CORRECT`, `CANCEL`, `REORG_RETRACT`, or `REINSTATE`.  A non-genesis revision
references a predecessor; ordinal must advance by one within a fork.  A source
generation reset starts a new `source_generation_id`, requires an explicit
coverage boundary, and cannot silently continue an old cursor.

## 4. Coverage is observed absence, not invented facts

`CoverageEventV1` is append-only and records one of nine classes:

`CONNECTIVITY_GAP`, `SOURCE_SEQUENCE_GAP`, `RECEIPT_LATENCY_BREACH`,
`SCHEMA_REJECT`, `SOURCE_OUTAGE`, `RATE_LIMIT`, `CURSOR_RESET`,
`ARTIFACT_INTEGRITY_FAILURE`, `COVERAGE_UNKNOWN`.

It records the known interval, observation basis, affected scope, and whether
the source can prove a sequence gap.  Silence cannot imply `NO_TRADE`,
`ZERO_VOLUME`, no liquidation, no price movement, or a healthy source.  No
interpolation, forward fill, zero fill, fabricated sequence, or inferred row
is permitted.  A bundle carrying a required unresolved gap is inadmissible.

## 5. Pure source-adapter boundary

A future adapter interface is a pure function only:

```text
adapt(request: AdapterRequestV1, source_snapshot: SourceAuthoritySnapshotV1,
      prior_cursor: AdapterCursorV1 | null, supplied_payload: bytes)
  -> AdapterResultV1
```

It receives all inputs explicitly and returns records, coverage facts, next
cursor, and one receipt.  It may not access filesystem, network, environment,
wall clock, random state, globals, retry loops, or mutable caches.  Empty
input is the only case that produces no receipt.  A nonempty input that wholly
rejects must create the first typed rejection receipt; an identical retry only
becomes idempotent after that receipt exists.

The closed result reasons include `SOURCE_SCHEMA_INVALID`, `SOURCE_RATE_LIMIT`,
`SOURCE_OUTAGE`, `CURSOR_INVALID`, `CURSOR_GENERATION_RESET_REQUIRED`,
`IDEMPOTENCY_CONFLICT`, `ARTIFACT_HASH_MISMATCH`, and
`CAPABILITY_NOT_ALLOWLISTED`.  Rate limit/outage are facts about the supplied
input/receipt, not authorization to retry or make network calls.

## 6. Bundle, seal, and v0.5 wrapper admission

`RawAuthorityBundleManifestV1` commits the exact source snapshot, artifacts,
raw-record identities, coverage events, cursor and adapter receipt in the
defined order.  It is not sealed by hashing itself.  `RawAuthoritySealV1` is
an external immutable-tip assertion whose `sealed_bundle_digest` must exactly
equal the bundle digest.  Missing, mismatched, self-issued, expired, or
unverifiable seal is fail-closed.

`EvidenceAdmissionContextV1` binds one unchanged v0.5 exact carrier/receipt
digest to its raw record, revision, transform, coverage disposition, bundle,
seal, expected external tip, expiry and decision cutoff.  It adds no keys to
v0.5 `Evidence`, `UpdateReceipt`, or `EvidenceLedgerReceipt`.  Admission only
states whether provenance is structurally admissible; it does not create a
market fact, score, probability, action, or permission.

## 7. Lane isolation and future source plan

Every source bundle belongs to exactly one named lane:

`SYNTHETIC_CONTRACT`, `METADATA_ONLY`, `DEVELOPMENT`, `CALIBRATION`,
`ONE_SHOT_HOLDOUT`, `PAPER_SHADOW`.

Each lane has distinct plan ID, registry digest, evidence root, bundle digest,
and external seal.  Once a source interval is `SEEN`, it cannot be renamed,
copied, or relabelled into an independent holdout.  `ACTIVE_G1` is not a lane
and is forbidden for all P1A reads/writes and bindings.  P1A contains no real
source rows.

Future source priority is a plan only, not evidence support: P0 source
admission order is official venue depth/trade, mark/funding/OI, venue metadata,
then independently versioned market context.  The theory-test sequence is
`H01 -> H03 -> H05 -> H02 -> H04 -> H06 -> H08 -> H07`; a source’s existence
does not support any hypothesis until separately admitted and tested.

## 8. Acceptance boundary

Passing the accompanying synthetic tests can establish only that the P1A
schema is internally consistent and rejects the named counterexamples.  It
does not establish real data availability, adapter correctness, market
validity, causality, calibration, positive expectancy, paper readiness, or
trading authorization.  A separate Sol P1A gate is required before any pure
runtime implementation, and another explicit authority is required before any
I/O or market/outcome access.
