# MSTA-HED Raw AuthorityBundle P1A-R1 Specification v0.1.1

**Status:** `DRAFT_AWAITING_SOL_P1A_R1_GATE`  
**Authority:** static local contract and synthetic fail-closed validation only.  
**Not authorized:** runtime adapter, filesystem/network I/O, market or outcome rows,
download, historical test, calibration, holdout, paper/live execution, deployment,
account access, or trading.  `ACTIVE_G1` and all Application Support aliases are
forbidden inputs, including in a `DEVELOPMENT` lane.

## 1. Closed boundary

There are nine authority objects, in this acyclic order:

1. `SourceAuthoritySnapshotV1`
2. `RawArtifactDescriptorV1`
3. `RawRecordEnvelopeV1`
4. `CoverageEventV1`
5. `AdapterCursorV1`
6. `AdapterReceiptV1`
7. `RawAuthorityBundleManifestV1`
8. `RawAuthoritySealV1`
9. `EvidenceAdmissionContextV1`

`AdapterRequestV1` and `AdapterResultV1` are additionally frozen **interface
schemas**, not authority objects. Every one of the eleven schemas has exact
fields, exact field types/nullability, closed enums and item schemas in the
companion JSON contract. Unknown, missing, aliased, malformed, or extra keys
are rejected. This includes `schema_type`; a digest never repairs a wrong type.

Canonical identities are lowercase SHA-256 over domain-separated, canonical
UTF-8 JSON, excluding only that object's own digest field. Logical paths are
opaque non-decoded relative identifiers: absolute paths, `..`, empty segments,
backslash/device forms, `%` encodings, and `~` aliases are rejected. No runtime
filesystem claim follows from this logical-identifier rule.

## 2. Clocks, revisions, and coverage

Source `event_at` and `published_at` may be null; unknown time is never
invented. A record must satisfy:

```text
received_at <= ingested_at <= derived_at <= actual_available_at <= decision_time
```

Known event/publication times cannot be after actual availability. `ACTUAL`
has no reconstruction fields. `RECONSTRUCTED` preserves its actual clock plus
counterfactual availability and a basis, but is never `ADMITTED` under actual
admission or outside a separately authorized research lane. Late data append
new receipts/bundles; they do not alter a sealed prefix.

`INITIAL` is ordinal zero with no predecessor. `CORRECT`, `CANCEL`,
`REORG_RETRACT`, and `REINSTATE` must reference the immediately preceding
revision with contiguous ordinal. `raw_record_id`, `logical_record_id`, and
`revision_id` are three distinct identities. Cancel/retract are tombstones;
reinstate is active. A fork or unresolved lineage is `UNKNOWN` and fails closed.
A generation change requires an explicit coverage generation boundary.

Coverage state has exactly nine values:

```text
CONTINUOUS_OBSERVED, CONFIRMED_NO_ACTIVITY, EXPECTED_SNAPSHOT_CADENCE,
NATIVE_SEQUENCE_GAP, TRANSPORT_GAP, SOURCE_OUTAGE, MARKET_HALT,
OBSERVED_UNUSABLE, UNKNOWN_COVERAGE
```

Causes are a separate closed vocabulary, including `RATE_LIMIT`,
`CURSOR_RESET`, `SCHEMA_REJECT`, `ARTIFACT_INTEGRITY_FAILURE`, and
`RECEIPT_LATENCY_BREACH`; they are not states. The coverage disposition is
derived solely from sealed coverage membership. A caller cannot assert `CLEAR`.
`SCHEMA_REJECT` can never produce `CLEAR`. Silence is not no-trade and no
interpolation, zero fill, or invented sequence is allowed.

## 3. Adapter, bundle, seal, and admission

The future adapter is a pure, explicit-input interface only. Its idempotency
key is exactly:

```text
SHA256(adapter_contract_digest | source_snapshot_digest |
       prior_cursor_digest_or_NULL | supplied_payload_sha256 | decision_time)
```

Only `SUPPLIED_PAYLOAD_ONLY` capability is allowed. There is no network,
filesystem, environment, clock, random, retry-loop, global, or mutable-cache
capability. A nonempty all-rejected input still produces its first typed receipt;
an empty result is the only receipt-less result.

A bundle binds P1A contract digest, source snapshot, adapter-contract digest,
transform digest, artifact, raw record, coverage membership, cursor and receipt
as exact sealed sets. Arbitrary/duplicate child digests fail. The external seal
must bind a trusted authority-snapshot allowlist, test algorithm, key identity,
public-key fingerprint/verification material, signed bundle payload and external
tip contract. The deterministic E0 test verifier is solely a synthetic validator,
not production cryptography.

Admission rechecks the unchanged v0.5 carrier/result digest bindings, transform,
receipt, complete coverage membership/disposition, exact bundle, trusted seal,
tip, expiry, lane, and empty admitted error list. It never adds v0.5 keys.

## 4. Theory-routing binding

P1A has no market evidence. When separately authorized data exists, market-path
tests use registry IDs `H01, H03, H05, H02, H04, H06, H08, H07` in that order.
`V5-H09-LAYERED_ERROR_ATTRIBUTION` is not a market-path hypothesis: it remains a
required data-quality guard before any of the eight market-path tests. Passing
this contract does not support any hypothesis, market mechanism, expectancy, or
trading decision.

## 5. Validation boundary

The executable reference test validates only synthetic structural rejection
paths. It intentionally makes no claim about a real source, real availability,
adapter implementation, market validity, causal truth, backtest result,
calibration, paper readiness, or trading authorization.
