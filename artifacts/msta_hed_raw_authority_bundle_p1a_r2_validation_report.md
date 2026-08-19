# P1A-R2 Static Validation Report

**Status:** `DRAFT_AWAITING_SOL_P1A_R2_GATE`.

This repair preserves v0.1.0 and v0.1.1 as rejected history and adds only the
five v0.1.2 P1A-R2 artifacts. It did not read or modify active G1, and did not
use network, filesystem runtime I/O, an adapter runtime, market/outcome data,
download, backtest, calibration, paper/live execution or trading.

## What R2 closes

- Exact closed object/interface/supporting-schema chain, including a contract
  trust snapshot and explicit v0.5 carrier/result binding object.
- Current P1A contract digest, source/artifact/raw/request/receipt/result/
  cursor/coverage/bundle links, exact child lists and transform binding.
- Schema and full-chain opaque path rejection; synthetic carrier/result digests
  are recomputed from typed payload objects, not accepted as arbitrary hex.
- Point-in-time, expiry, revision/tombstone/generation-boundary, proof-qualified
  coverage, receipt-prefix/idempotency and trusted-seal checks.
- A programmatically mapped fixture: every listed `case_id` has a named
  executed mutator and an asserted exact reason code.

## Executed validation

`tests/test_msta_hed_raw_authority_bundle_p1a_r2_contract.py` ran **5/5**
tests. Its fixture loop executed **26/26** counterexample mutators, including
wrong contract digest, identity drift, seal/tip/key failure, expiry class,
path aliases, reconstructed admission, coverage proof/interval/cause failure,
revision/fork/generation failure, request/receipt/result/cursor drift, missing
payload/prefix field, arbitrary v0.5 digest and active-G1 aliases.

The validator is an executable static reference, not a runtime implementation.
It therefore provides no claim of production cryptography, real source
availability, market validity, hypothesis support, causal efficacy, backtest
performance, calibration, paper readiness or trading authorization.

Raw SHA-256 at report creation: specification
`b56f46b5bb8a4a5d7b8077fa64ee69815620860b5d68bbfd8fd19f81ddaa2f54`,
contract `751580429f7a293c45ed57fbc2c86399e49639c37f575009a892e2d57dfff7bc`,
fixture `341af751fc422c439f8287e222d12edfbc60a0fcd9c1ee31bf50124701947247`,
test `8da7cbff82a32b700a0a4120067cc1c8c3d9a25da4113d41efc13b1f791e38a6`.
