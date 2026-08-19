# Route B B1 contract evidence report

Status: `B1_CANDIDATE / E0 / NOT_MARKET_VALIDATED`

This is a contract-only evidence report. It is neither a B1 PASS receipt nor an
authorization for B2, data, backtests, paper, OMS, or live trading.

## Frozen authorities actually verified

- Authority Bundle Spec: `a99300b39966898f608927e0cf05d45c30481b8f0d5d7eae266ed1cdd1d54728`, 70,723 bytes.
- Route B Decision: `09942d7a2e06554ae00b6bb95153648436b459a7a0cd107cf630a34a3c8a7f57`, 8,668 bytes, ASCII, no trailing LF; internal canonical decision digest `e66be1025b2fcf616d91f446029f5326f23421ca5ddf38b697288482c2b8c4c4` was recomputed.
- Semantic source: `43eedbee0a10cf0254721052c1aca23baf027a90f879739ec33b48180cfd87a6`, 136,468 bytes.
- Legacy v0.2 raw/canonical digest: `33d84ce8fdfa7766fbce340beac9916344655c002e39ed6c8db29cefaaa6b047` / `38d572453045016bbdc314d184f9be87a608ec8bc36aabaf92d8c0ce742201e5`; canonical size 20,204 bytes.
- Four-layer `composite_theory_id` was recomputed with `UTF8(domain) || NUL || CanonicalJSON(preimage)` as `3e7ecf5e257d8a2dbf5cc826c1da1240283a2379de710e4be90f7bcfdb8118ea`.
- All 14 Route B Decision frozen inputs were read, size-checked, and SHA-256 checked.

## Exact B1 delivery hashes

| Path | Bytes | SHA-256 |
|---|---:|---|
| `config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json` | 23,639 | `baf9f21109a3183031eed41c9c81683561045e1c22b4bb8c370c119edc356bb4` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/__init__.py` | 76 | `9276a94019698e2fe53b8a230a2faeaa0c824495ad8c9fdfcc0443b3dd86194d` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py` | 34,463 | `34edf3aee78dc270239cba9f9a78766f3d6626f7807bf8063f2710461f75efa9` |
| `tests/test_rsi_mtf_drl_pm_v0_2_2_contract.py` | 27,113 | `3edc128336c98d6de795c8c83566851335723b8e362de755bd68e89a43b40923` |

The report's own hash/size is deliberately not self-asserted. It must be
observed by an external command after this file is closed; it is not an
authority input, manifest, or receipt.

## Checks run

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_research_contract
```

Result: `33 tests, 0 failures` (15 B1 tests; 18 immutable legacy v0.2 tests).

The B1 tests exercise all twelve §8 minimum families: closed top/nested object
keys; physical/canonical JSON; all four finite registries; 11 support types,
C21 carrier, union and 26 codes; 13 algorithm interfaces and real source
ranges; six public entrypoints/failure arrays/`__all__`; C01--C21 and 42 case
IDs; all 32 semantic/chronology/authorization leaves; both superseded container
IDs; forbidden capability injection; frozen-source exact import/call-form AST
allowlists with write and indirect-call counterexamples; Mapping subclass
recursive materialization; all ordinary public-boundary exceptions mapped to
the exact carrier while process-exit exceptions propagate; and
temporary-workspace decision, all-14
frozen-input, legacy canonical and composite lineage tampering.

## Not run / maximum permitted statement

- No B2 model/kernel, B3 golden fixture, manifest, replay, external receipt,
  data adapter, market/historical data, backtest, calibration, holdout, paper,
  OMS, active G1, or live capability was created, read, or run by this B1 work.
- The largest justified statement is: the B1 Route-B contract candidate is
  mechanically closed and source-bound at E0, pending independent Sol review.
  This is not synthetic validation, market validity, predictive validity,
  execution realism, profitability, or trading authorization.
