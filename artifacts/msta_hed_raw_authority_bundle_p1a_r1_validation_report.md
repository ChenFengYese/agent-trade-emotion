# P1A-R1 Raw AuthorityBundle Static Validation Report

**Status:** `DRAFT_AWAITING_SOL_P1A_R1_GATE`  
**Scope:** pure local static contract repair; no active G1 read/write, no I/O,
no adapter runtime, no market/outcome rows, no download, no historical test,
and no trading action.

## Frozen candidate files

| File | SHA-256 |
|---|---|
| `MSTA_HED_RAW_AUTHORITY_BUNDLE_P1A_SPEC_v0_1_1.md` | `0d3baabd7f0e4cc4d607e82a5219a5b376c0e731f7faed7c9c502cb0bfe4a652` |
| `config/msta_hed_raw_authority_bundle.p1a_contract.v0_1_1.json` | `45baae1c3a65429236f65420fc3ce8fcfecf6006af09679f3c42b45519a9bdac` |
| `config/msta_hed_raw_authority_bundle.p1a_synthetic_contract.v0_1_1.json` | `996928b5e81664b81fb1c9b1af6f01e2d3a1a69f3bca6e8daf622de4bf66598f` |
| `tests/test_msta_hed_raw_authority_bundle_p1a_r1_contract.py` | `a76b841136ca09f7b5109b4ebac7ee78b2bdbf0f541a223d7f1c59d6075e5bbc` |

The internal contract canonical digest is
`be01d0c9c5d0aa9b27590643487f0f3e1ece303ffe7567a93f1ed03ec40c9e05`;
the fixture canonical digest is
`3351251a81de708fce015e4eed31de7ccd76acbb36e614d28c7a580f7e6690ef`.

## Executed checks

| Command | Result |
|---|---:|
| `python3 -m unittest tests/test_msta_hed_raw_authority_bundle_p1a_r1_contract.py -v` | 17/17 PASS |
| `python3 -m unittest tests/test_msta_hed_raw_authority_bundle_p1a_contract.py -v` | 14/14 PASS (superseded v0.1.0 historical contract) |
| `python3 -m unittest tests/test_generalized_competing_path_v0_5_0_contract.py -v` | 58/58 PASS |
| `python3 -m unittest tests/test_rsi_mtf_four_layer_v0_4_0_contract.py -v` | 26/26 PASS |
| strict duplicate-key JSON load for the two R1 JSON files | 2/2 PASS |
| `git diff --check` | PASS |

The R1 executable reference actually calls its validator for invalid revision,
reconstructed admission, `SCHEMA_REJECT + CLEAR`, raw-outside-bundle, untrusted
seal, missing adapter-result field, wrong idempotency formula, arbitrary bundle
child, source/artifact mismatch, Active-G1 alias, nonempty admitted errors,
path aliases, and seal/bundle clock inconsistency. It also checks all eleven
closed schemas, the nine exact coverage states, separate cause codes, seal
allowlist material, receipt/result linkage, and contiguous revision/tombstone/
generation-boundary rules.

## Boundary of this evidence

This is static executable reference validation only. It establishes neither a
runtime adapter, cryptographic production seal, source availability, actual
market rows, point-in-time market completeness, hypothesis support, causal
market claim, backtest/calibration result, paper readiness, nor trading
authorization. A Sol gate remains required before any further stage.
