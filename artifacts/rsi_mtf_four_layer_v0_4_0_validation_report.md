# RSI-MTF Four-Layer v0.4.0 Validation Report

## Scope and snapshot

- Validation time: 2026-07-26 (local workspace audit)
- CWD: `/Users/wt/Documents/agent-trade-emotion`
- Branch: `codex/s0-research-foundation`
- HEAD: `7ca3fc4f99a57f98217e703f222b295653ace87e`
- Evidence level: `E0`
- Scope: static contracts and hand-written synthetic fixtures only.

No real historical market payload or outcome was read. No source adapter,
backtest, calibration, holdout, paper trading, live trading, deployment, or
activity-G1 mutation was performed.

## Exact commands and results

### v0.4.0 cross-artifact synthetic contract

Command:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_four_layer_v0_4_0_contract
```

Result: `14` run, `13` pass, `1` fail.

Failing test:

```text
test_labels_parent_child_mapping_and_roles_match_method_contract
```

Observed reason: the synthetic contract's `mechanical_label_mapping` lacks the
method contract's newly-added `DOWNTREND_RANGE_NESTED` and
`UPTREND_RANGE_NESTED` entries. The test correctly rejects a partial cross-file
mapping rather than weakening the equality rule.

### v0.3.0 challenger regression

Command:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_drl_pm_theory_challenger_v0_3_0
```

Result: `12/12 PASS`.

### v0.2.2 authority, contract, kernel, and direct-AST regression

Actual modules selected:

```text
tests.test_rsi_research_contract
tests.test_rsi_mtf_drl_pm_v0_2_2_contract
tests.test_rsi_mtf_drl_pm_v0_2_2_kernel
```

The latter two modules include direct AST allowlist checks for the frozen
contract/kernel source. Command:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_research_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_kernel
```

Result: `48` run, `47` pass, `1` fail.

Failing test:

```text
tests.test_rsi_mtf_drl_pm_v0_2_2_kernel.KernelB2Tests.
test_frozen_b1_authorities_are_unchanged
```

Observed reason:

```text
rsi_mtf_drl_pm.strategy_contract.v0_2_2.json size: actual 23636 != expected 23639
```

This report does not modify the frozen authority object or its assertion.

### Parse, syntax, and whitespace checks

Commands:

```text
jq empty \
  config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json \
  config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json

rg -n '[[:blank:]]+$' \
  RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md \
  config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json \
  config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json \
  tests/test_rsi_mtf_four_layer_v0_4_0_contract.py

/opt/homebrew/bin/python3.12 -B -c "import ast, pathlib; ast.parse(pathlib.Path('tests/test_rsi_mtf_four_layer_v0_4_0_contract.py').read_text(encoding='utf-8')); print('PYTHON_AST_PARSE=PASS')"
```

Result: all three v0.4 JSON files parse; no trailing whitespace found across
the five new v0.4 artifacts; Python AST parsing passed.

## New v0.4 artifact hashes

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `64673fae89d90a9e3620f4bacd1597fa8d1f9ea9b975efac9f7986a6a018eb1b` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `6e60790518a35e5224ee33667b9c7989cb02250d64d98ab96c8c5c866129002d` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `cc7067c43e7c1a1ba0694b669f436460a24b652a95a427677fb2bd2b8a3d713e` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `cae86046de335fe9b613dfc6fcdbc35624048d13314babaf2fc688c1b45da937` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `f2fab230f320a5f046d8fe7bfc8d200c8ff92bcf732a2be8b2589f002c78b4d4` |

## Activity G1 read-only snapshot

Read-only paths:

```text
/Users/wt/Library/Application Support/agent-trade-emotion/config/forward_capture_plan.g1.v1.json
/Users/wt/Library/Application Support/agent-trade-emotion/config/source_registry.v3.json
/Users/wt/Library/Application Support/agent-trade-emotion/logs/capture-supervisor.stdout.log
```

Frozen hashes:

| Artifact | SHA-256 |
|---|---|
| `forward_capture_plan.g1.v1.json` | `189317fdff53d9f0ca64747d48690a283a3328b04df539f53307eb1370c3cb6d` |
| `source_registry.v3.json` | `b3848092824dc65e9fea6ac524811453b8abf4783b865d8c057089cb5603453f` |

Latest supervisor decision in the inspected log:

```text
action=WAIT
decided_at=2026-07-26T02:24:18.682376+00:00
reason_codes=[FUTURE_SLOT_PENDING, MISSED_SLOTS_PRESENT]
missed_slots=13
pending_slots=15
resource_guard.passed=true
free_bytes=18921963520
min_free_bytes=16106127360
max_plan_bytes=12884901888
plan_bytes=0
```

The plan reports `FROZEN_FORWARD_CAPTURE_PLAN`; the source registry reports
`FROZEN_SOURCE_REGISTRY`. No active-G1 file was changed or deployed.

## Gate conclusion

`V4-M00` is **not passed**: the cross-artifact synthetic test has one real
failure. The frozen v0.2.2 B1 authority regression also has one real failure.
Neither failure is a market result or a trading result. No B4, historical
outcome, backtest, paper, or live authorization is implied. The only permitted
next decision is a Sol stage-gate review after the recorded contract/authority
failures are resolved and the full synthetic/authority regression batch is
rerun.

## Superseding v0.4 repair run

The preceding first-run failure record is retained as audit evidence. This
repair run synchronized the synthetic contract with the current v0.4 method
contract: the `RANGE_NESTED` label mappings, the mutually-exclusive
`MarketScenario` label definition and its frozen `central_range_band`, the
complete finite candidate tuple, `ActionOutcome` joint/filled-cohort semantics,
the causal measurement contract, and the H10 prefix-only fixtures and tests.
No theory, method contract, registry, active-G1 artifact, or v0.2 authority was
changed by this repair run.

Commands:

```text
jq empty config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json

/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_four_layer_v0_4_0_contract

/opt/homebrew/bin/python3.12 -B -c "import ast, pathlib; p=pathlib.Path('tests/test_rsi_mtf_four_layer_v0_4_0_contract.py'); ast.parse(p.read_text()); print('AST_PASS', p)"

rg -n '[[:blank:]]+$' \
  config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json \
  tests/test_rsi_mtf_four_layer_v0_4_0_contract.py \
  artifacts/rsi_mtf_four_layer_v0_4_0_validation_report.md
```

Results:

- JSON parse: `PASS`.
- v0.4 synthetic contract suite: `18/18 PASS`.
- Python AST parse: `PASS`.
- Trailing-whitespace check: `PASS` (no matches).
- The known frozen v0.2.2 stale-B1 regression was intentionally not rerun or
  repaired; it is unrelated to this permitted v0.4 repair scope and remains a
  separately recorded authority issue above.

Superseding artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `cef36610638fc9931ed0ed2051be690aaaba49033494c75271440951dd1a4149` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `07bf201e3e610cfb34e97b9bbc9dcf72be3328d29b5e96323739c943ff85eac0` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `da653c9458bb063ea5f8bea64f6e88b8287f02aecf3157e6f602b6c28382ef18` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `2604b0c5451c5c9838cfdbb7a5a2ff1e26dffc8a5364305bbad011ffe07f2e8d` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `a3a77842f93ed142b93ab08302649a0fa235c4e6093469a89c614b586ba18989` |

## Terminal superseding receipt — sole current terminal state

This EOF receipt is the **only current terminal state** for this append-only
report. It supersedes the old `Final state-change receipt` and every prior
terminal claim, status, test count, and artifact hash above. Earlier entries
remain historical audit evidence only.

Current registry state is `V4-M00.result_status=NOT_RUN` and
`V4-M00.test_execution_status=TESTS_PASS_AWAITING_SOL_STAGE_GATE`; H01 through
H12 are all `WAIT_DATA`.

Current verification results are v0.4 `22/22 PASS`, v0.2 `48/48 PASS`, and
combined `70/70 PASS`. The v0.4 JSON contracts pass `3/3 jq`; Python AST,
trailing-whitespace, and `git diff --check` all pass. This remains E0
outcome-free evidence and grants no B4, data, development, backtest, paper, or
live authorization.

Current non-self-referential artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `b706280a36f74074e81f445afb285c46adbb15896664e837b8ef35a481e051cb` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `0a27aff6b21dd82e58d85432298ce88314af88481ae646215f29a1d3772b77d2` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `ec63fe18781f94901f6751e15559a1a055a0025598dc90cd942ed98cf47d11b7` |

The report's physical SHA-256 is intentionally not embedded in this text:
because it is self-referential, the post-write external stage-gate binding
provides that final physical digest.

## Terminal superseding receipt — causal-clock/type closure

This EOF receipt supersedes every earlier terminal receipt in this append-only
report. Earlier entries remain audit history only.

Scope was limited to the V4-M00 E0 synthetic causal-clock/type defect: a future
`source_timestamp` could pass the former helper, and Python truthiness could
accept pseudo-boolean `is_closed`. No market data, B4 activity, adapter,
backtest, paper/live path, deployment, frozen v0.2 authority object, or active
G1 path was read or changed.

The theory, method contract, hypothesis registry, and synthetic contract now
require the same frozen visibility invariant: a bar is visible only if
`is_closed` is the exact JSON boolean `true`; `source_timestamp`, `close_time`,
`available_at`, and `decision_time` are present, valid, timezone-aware and
comparable; and all three record timestamps are no later than the decision
time. Missing, malformed, incomparable, future-sourced, and pseudo-boolean
inputs fail closed to `DATA_INVALID` and `UNKNOWN_OR_ABSTAIN`.

`_visible` now implements that invariant without implicit local-time handling.
The H10 and H11 prefix helpers delegate to one `_daily_prefix` implementation;
that implementation passes raw values to `_visible` and contains neither
`bool()` nor `str()` coercion. Synthetic fixtures F19–F23 and contract tests
cover a future source timestamp, string and numeric pseudo-booleans, malformed
time, and missing time.

### Actual verification receipt

- v0.4 synthetic contract suite: `25/25 PASS`.
- Frozen v0.2 combined contract/kernel/research suite: `48/48 PASS`.
- Frozen direct-AST conformance suite: `11/11 PASS`.
- Independent adversarial harness: `PASS` for five invalid cases across both
  H10 and H11 prefix helpers.
- v0.4 JSON parsing: `3/3 PASS`; causal visibility AST guard: `PASS`.
- Trailing-whitespace scan: `PASS` (no matches); `git diff --check`: `PASS`.
  The whitespace scan explicitly included the untracked v0.4 artifacts, which
  are not covered by ordinary `git diff --check` until staged.

The actual commands were:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_four_layer_v0_4_0_contract
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_research_contract tests.test_rsi_mtf_drl_pm_v0_2_2_contract tests.test_rsi_mtf_drl_pm_v0_2_2_kernel
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_drl_pm_direct_ast
/opt/homebrew/bin/python3.12 -B - <<'PY'  # independent visibility adversarial harness
jq empty config/rsi_mtf_four_layer.method_contract.v0_4_0.json config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json
/opt/homebrew/bin/python3.12 -B - <<'PY'  # AST causal-visibility guard
rg -n '[[:blank:]]+$' [the six v0.4 artifacts]
git diff --check
```

Current non-self-referential artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `f98781e8dcfcf6c29de3180f120d889efb16f01e65045dd86e62807e1a24957b` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `5b7314aac628dec0dcd213e04c7f2309c70f0e00a5e31bad1be4335a478271a1` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `c962ebe6fa0b5d58562a781104575d767caa24079ceb01acb2d448b462e5d5c6` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `9694405007ea12465aad1d8f28bbf763d9b925c9cb2964431780f40809f82ce8` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `ee53f97badf99f2ccd6a9fc5e66b86da38e1974324d9730c5daaf9fa7fb1e51d` |

The report's own physical SHA-256 is deliberately external to this
self-referential text and must be bound after this write. Passing these E0
tests repairs only the identified synthetic defect; it does not reverse the
Sol determination `V4-M00 NOT PASS` or `B4 DENY`. A new independent Sol
stage-gate review is required before either status may change.

## P0 semantic-repair rerun receipt

All earlier receipts remain historical records. This superseding receipt covers
the final state-agent v0.4 theory/method/registry baseline and the permitted
synthetic/test-only repair. No real historical payload or outcome was read; no
adapter, backtest, calibration, paper/live action, v0.2 mutation, or active-G1
mutation occurred.

The rerun adds synthetic enforcement for the following P0 semantic boundaries:

- `ActionOutcome` has exactly `NO_FILL`, `TP_FIRST`, `SL_FIRST`,
  `STRUCTURE_EXIT`, and `TIMEOUT`; `DataDisposition` is independently counted.
- The valid `StructuralRegime` cross-grid is exhaustive, and parent-child
  conflict remains a `DecisionState` relation rather than rewriting a TFState.
- `source_sequence` is comparable only within one source and generation/stream;
  equal-time cross-source inputs are an economic batch, with replay tie-breaks
  having no market-time meaning.
- `StatePermissionGate` is boolean-only and cannot move the four-zone price
  intersection; deny/unknown produces an empty zone.
- H10/H11 have price-only primary endpoints; H12 is the independent event
  arrival diagnostic and cannot make either price hypothesis pass.
- The exact nine-field cohort key prohibits pooling under any one-field
  difference.
- An RSI episode emits `OBSERVE` once at creation, deduplicates persistent
  extremes, and may evaluate only at a later eligible closed decision time.

Commands:

```text
jq empty config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json

/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_four_layer_v0_4_0_contract

/opt/homebrew/bin/python3.12 -B -c "import ast, pathlib; p=pathlib.Path('tests/test_rsi_mtf_four_layer_v0_4_0_contract.py'); ast.parse(p.read_text(encoding='utf-8')); print('PYTHON_AST_PARSE=PASS')"
```

Results:

- JSON parse: `3/3 PASS`.
- Targeted v0.4 synthetic contract suite: `22/22 PASS`.
- Python AST parse: `PASS`.
- No trailing whitespace in the three permitted repair artifacts/report:
  `PASS`.

Observed state-agent registry values at this rerun:

- `V4-M00.result_status`: `NOT_RUN`.
- `V4-M00.test_execution_status`: `P0_REPAIR_IN_PROGRESS_AWAITING_RERUN`.
- H01 through H12: `WAIT_DATA`.

The test evidence is therefore awaiting a Sol stage-gate decision; no B4,
development, historical-outcome, backtest, calibration, paper, or live
authorization follows from this receipt. The registry state above is reported
as read and was not changed by this test-execution role.

Superseding rerun hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `ef2f820957010bb44d4729e21a3c2482b00eb59789aa8d9a110b49f344ba73d6` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `ebbebebb6668da2d7ba96a1b57ae3046298111c49ba8964286b6645c499ad12a` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `c83de51b4aedb2d743b704ef3c1e9a8d43e0ba0ed001e68c98e9b463fb2cf0d2` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `30e435269e370636c57de70fd0da25da656ae5a0f6a782c29451a1d28af2f6a8` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `ae3107393a02eb07c19a09d24e16f0df57e73d92729b6f7502cded8e98e185e3` |

## Final P0 semantic-repair correction receipt

The preceding P0 rerun receipt is retained. Before finalizing it, two test
semantics were corrected without changing theory, method, registry, v0.2, or
active G1:

- Parent-child conflict is represented by legal
  `parent_child_relation=UNKNOWN` plus `data_quality_rollup_reason=CONFLICT`;
  it no longer uses a nonexistent parent-child enum value. The cross-grid now
  includes `-theta_v`, `0`, `+theta_v`, and `theta_de` boundaries.
- A persistent RSI extreme suppresses only a duplicate `OBSERVE`. It no longer
  prevents an existing episode from reaching `EVALUATE_REVERSAL` at a later
  eligible closed decision time. Same-bar upgrade remains forbidden.

The machine-readable fixture set additionally records the eight required P0
counterexamples: valid cross-region transition, non-rewriting parent conflict,
post-fill operational override outside the joint vector, equal-time
cross-source non-exchangeable handling, denied permission gate, one-field
cohort mismatch, persistent RSI lifecycle, and H12's inability to satisfy an
H10 price endpoint.

Final rerun commands and results:

```text
jq empty config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json

/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_four_layer_v0_4_0_contract

/opt/homebrew/bin/python3.12 -B -c "import ast, pathlib; p=pathlib.Path('tests/test_rsi_mtf_four_layer_v0_4_0_contract.py'); ast.parse(p.read_text(encoding='utf-8')); print('PYTHON_AST_PARSE=PASS')"
```

- JSON parse: `3/3 PASS`.
- Targeted v0.4 synthetic contract suite: `22/22 PASS`.
- Python AST parse and permitted-artifact trailing-whitespace check: `PASS`.
- Registry readback remains `V4-M00.result_status=NOT_RUN`,
  `test_execution_status=P0_REPAIR_IN_PROGRESS_AWAITING_RERUN`, and H01–H12
  are all `WAIT_DATA`.

This evidence awaits a Sol stage-gate decision. It remains E0 outcome-free:
no historical payload/outcome, backtest, calibration, paper, live, or B4
authorization is implied.

Final corrected hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `ef2f820957010bb44d4729e21a3c2482b00eb59789aa8d9a110b49f344ba73d6` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `ebbebebb6668da2d7ba96a1b57ae3046298111c49ba8964286b6645c499ad12a` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `c83de51b4aedb2d743b704ef3c1e9a8d43e0ba0ed001e68c98e9b463fb2cf0d2` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `ba2702d895cd3b3c71103903222e36f34ac29ebbf610a087ad8793048046561f` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `b53ccc52fe1d8e2d0b83396b4ce17f38a41b3f4d24ed32803a64262da7a53edb` |

## Terminal superseding receipt — second Sol P0 repair

This is the latest status in this report. All earlier `18/18`, `22/22`, and
their associated hashes are preserved as historical receipts and are superseded
by the artifact hashes and results below.

This repair remains entirely synthetic and outcome-free. No historical market
payload/outcome, data adapter, backtest, calibration, paper/live action, or
active-G1 mutation occurred. The only registry mutation was the explicitly
authorized post-pass change of `V4-M00.test_execution_status`; its
`result_status` and all hypothesis results were not changed.

Executed commands:

```text
jq empty config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json

/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_mtf_four_layer_v0_4_0_contract

/opt/homebrew/bin/python3.12 -B -c "import ast,pathlib; ast.parse(pathlib.Path('tests/test_rsi_mtf_four_layer_v0_4_0_contract.py').read_text()); print('AST_PASS')"

/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_research_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_kernel
```

Actual results:

- v0.4 synthetic contract suite: `22/22 PASS`.
- Three v0.4 JSON files: `3/3 jq PASS`.
- Python AST and permitted-artifact whitespace checks: `PASS`.
- Frozen v0.2 authority/contract/kernel batch: `48/48 PASS`.

The v0.4 suite now executes synthetic counterexamples for finite positive
parameter domains and boundary partitioning; identity/replay closure;
ALLOW/DENY-only permission gating; legal RSI episode lifecycle; immutable
post-fill scoring denominators; H10/H11 price-only versus H12 diagnostic
separation; exact nine-key cohort pooling; and preservation of HALT/EXIT/MANAGE
priority under parent conflict.

Current registry readback:

- `V4-M00.result_status`: `NOT_RUN`.
- `V4-M00.test_execution_status`: `TESTS_PASS_AWAITING_SOL_STAGE_GATE`.
- H01 through H12: `WAIT_DATA`.

The current evidence is awaiting Sol stage-gate review. It is still E0
outcome-free and grants no B4, development, historical-outcome, backtest,
calibration, paper, or live authorization.

Terminal hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `f3303f23d01820cbc1fcb0feca9f6811476ac531b32b2a7fa6ca830b50aca211` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `0a27aff6b21dd82e58d85432298ce88314af88481ae646215f29a1d3772b77d2` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `de18038876d399b23ed50166a29f8f8170dce021a75f4eb50736dfc543c32875` |

## Terminal superseding receipt — executable semantic-counterexample closure

This final receipt supersedes the immediately preceding terminal hash for the
synthetic contract test file. Prior receipts remain historical evidence.

- v0.4 targeted suite: `22/22 PASS`.
- v0.2 authority/contract/kernel suite: `48/48 PASS`.
- Combined executed batch: `70/70 PASS`.
- Three JSON files parsed with `jq`; AST and trailing-whitespace checks passed.

The final synthetic execution covers strict parameter-domain rejection,
identity/replay failure cases, ALLOW/DENY gate rejection, legal RSI action plus
separate emission flag and all upgrade vetoes, immutable score denominators,
four-zone schema closure, priority preservation under parent conflict, and the
executable H12 event-versus-price negative case. Registry state is unchanged:
`NOT_RUN`, `TESTS_PASS_AWAITING_SOL_STAGE_GATE`, H01–H12 `WAIT_DATA`.

Final revised test hash:

| Artifact | SHA-256 |
|---|---|
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `b78453c9928467a8fe5bcbcdb9e4e7763c9af65acbffccd66dcd0d5bce117555` |

## Terminal superseding receipt — identity and denominator closure

This is the current terminal receipt; prior test hashes are historical. The
synthetic replay contract now rejects missing/empty identity fields, invalid
sequence values, duplicate sequence and duplicate stable IDs, while retaining
different-generation sequence incomparability. Synthetic scoring now reports
the three score denominators separately from exact disposition counts and
pre-/post-fill nonvalid counts; predictions are checked immutable before and
after scoring.

Executed results: v0.4 `22/22 PASS`; v0.2 `48/48 PASS`; combined `70/70 PASS`;
three JSON `jq`, AST and whitespace checks `PASS`. Registry remains
`NOT_RUN` / `TESTS_PASS_AWAITING_SOL_STAGE_GATE` / H01–H12 `WAIT_DATA`.
No historical payload, outcome, backtest, adapter, paper/live action, or G1
mutation occurred.

| Artifact | SHA-256 |
|---|---|
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `7745758eb8e793c4de07aa3fdb0bc8fb82469103f5f33a4c977c7fba3509dc96` |

## Terminal superseding receipt — current stage-state evidence

This is the sole current terminal receipt. It supersedes the old **Final
state-change receipt** and every prior terminal status/hash claim in this
append-only report. Historical receipts remain retained for audit only.

The theory §8 V4-M00 row now exactly matches the registry: result status is
`NOT_RUN` and human-readable test state is
`TESTS_PASS_AWAITING_SOL_STAGE_GATE`. H01–H12 remain `WAIT_DATA`. This remains
E0 outcome-free evidence and implies no market claim, B4, development,
historical outcome access, backtest, paper, or live authorization.

Actual verification:

- v0.4 targeted synthetic suite: `22/22 PASS`.
- v0.2 authority/contract/kernel suite: `48/48 PASS`.
- Combined execution: `70/70 PASS`.
- v0.4 JSON: `3/3 jq PASS`; Python AST, whitespace, and `git diff --check`:
  `PASS`.

Current artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `b706280a36f74074e81f445afb285c46adbb15896664e837b8ef35a481e051cb` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `0a27aff6b21dd82e58d85432298ce88314af88481ae646215f29a1d3772b77d2` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `ec63fe18781f94901f6751e15559a1a055a0025598dc90cd942ed98cf47d11b7` |
| `artifacts/rsi_mtf_four_layer_v0_4_0_validation_report.md` | Self-referential final artifact; final SHA-256 is computed and reported by the post-write verification immediately following this append. |

Gate status: `V4_M00_TESTS_PASS_AWAITING_SOL_GATE`.

This is still E0 outcome-free contract evidence only. It provides no real
historical outcome, market-validity, calibration, backtest, paper-trading, or
live-trading conclusion, and does not authorize a B4 or development transition.

## Final state-change receipt

This receipt records the state-agent update after the superseding v0.4 repair
run. It does not replace or erase any prior run record in this report and does
not modify theory, configuration, tests, or active G1.

Current state observed from the v0.4 registry:

- Milestone `result_status`: `NOT_RUN`.
- Milestone `test_execution_status`: `TESTS_PASS_AWAITING_SOL_STAGE_GATE`
  (the requested `PASS_AWAITING_SOL` state in its exact registry spelling).
- H01 through H10 `result_status`: `WAIT_DATA`.

Evidence carried forward from the superseding repair run: v0.4 synthetic
contract suite `18/18 PASS`; no market outcome, historical payload, backtest,
calibration, paper, or live conclusion is implied.

Current JSON parse receipt:

```text
jq empty config/rsi_mtf_four_layer.method_contract.v0_4_0.json \
  config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json
```

Result: `2/2 JSON jq PASS`.

State-change artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `3ba6704b957d23999fce969e4b1bf15e739cc58b42b3a6f370786d9dc7ebcab6` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `07bf201e3e610cfb34e97b9bbc9dcf72be3328d29b5e96323739c943ff85eac0` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `a4c93acd43c78b0bf28b7456030769d06b665cb58778fa5385a21dfa08f486f0` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `2604b0c5451c5c9838cfdbb7a5a2ff1e26dffc8a5364305bbad011ffe07f2e8d` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `a3a77842f93ed142b93ab08302649a0fa235c4e6093469a89c614b586ba18989` |

## Terminal superseding receipt — sole current terminal state at EOF

This EOF block is the only current terminal state. It supersedes the old
`Final state-change receipt` and all prior terminal claims; older entries are
historical audit evidence only.

Current state: `V4-M00.result_status=NOT_RUN`,
`V4-M00.test_execution_status=TESTS_PASS_AWAITING_SOL_STAGE_GATE`, and
H01–H12 are `WAIT_DATA`. Verification: v0.4 `22/22 PASS`, v0.2 `48/48 PASS`,
combined `70/70 PASS`, v0.4 JSON `3/3 jq PASS`, plus AST, whitespace and
`git diff --check` `PASS`. This remains E0 outcome-free; no B4, data,
development, backtest, paper, or live authorization follows.

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `b706280a36f74074e81f445afb285c46adbb15896664e837b8ef35a481e051cb` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `0a27aff6b21dd82e58d85432298ce88314af88481ae646215f29a1d3772b77d2` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `72485660feb7e53c7ca53c0d6474e7d35ca6ea95c1aa3ca0cfb348655f9e875a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `ec63fe18781f94901f6751e15559a1a055a0025598dc90cd942ed98cf47d11b7` |

The validation report physical SHA-256 is intentionally external: self-hashing
within this report is impossible. Post-write stage-gate binding provides its
final digest.

## Terminal superseding receipt — post-Sol-NOT-PASS P0 closure at EOF

This EOF receipt is the only current terminal state. It supersedes every prior
terminal claim and receipt above, which remain historical evidence only. It
records the minimum E0 repair after the Sol decision `V4-M00 NOT PASS`; it does
not claim that Sol has subsequently passed the gate.

The repaired synthetic contracts now execute: gated RSI episode creation and
irreversible termination state while retaining identity; one strict shared
post-fill record validator before all denominators; complete exact-key finite
candidate-family validation for all eleven frozen fields and at most eight
unique tuples; and exact cross-artifact H10/H11 Action set equality.

Actual verification results:

- v0.4 targeted suite: `23/23 PASS`.
- v0.2 authority/contract/kernel suite: `48/48 PASS`.
- Combined execution: `71/71 PASS`.
- Three v0.4 JSON documents: `3/3 jq PASS`.
- Python AST, trailing-whitespace and `git diff --check`: `PASS`.

Registry state remains `V4-M00.result_status=NOT_RUN`,
`V4-M00.test_execution_status=TESTS_PASS_AWAITING_SOL_STAGE_GATE`, with H01–H12
all `WAIT_DATA`. Evidence remains E0 outcome-free. B4, real historical outcome
access, source probing/download, adapter work, backtest, paper and live remain
unauthorized.

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `543ccc9e8e3c0045e848a3de5f43929814956c2339536c9d85c9db68b6019a61` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `4096aed75e9ea47fc76f8761f7148a52051d576f508db94e7fb16f7a6dcd3b3d` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `cdab704ef7514a5b71967ac5149e2ed4054fc5792bd9665656a90414f8ef0cb4` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `30f062cfebf2ff227d2d4618d625830a16098d5a26f298052cac3fa723c467ae` |

The report physical SHA-256 remains an external post-write stage-gate binding;
embedding its own final digest would be self-referential.

## Terminal superseding receipt — Terra adversarial-edge closure at EOF

This is the sole current terminal receipt. It supersedes every prior terminal
claim and receipt above, which remain append-only historical evidence. It
records the minimum E0 repair after the independent Terra adversarial audit and
does not claim that Sol has subsequently passed the V4-M00 stage gate.

The repaired executable semantics now reject JSON/Python numeric
pseudo-booleans `1/0/1.0/0.0` for `observed_fill`, reject JSON booleans as
probability values, and route both individual scoring and all denominators
through the same strict record validator. Candidate-family uniqueness is
semantic after numeric normalization, so `1/1.0` and `-0.0/0.0` cannot bypass
duplicate rejection. RSI creation and same-bar state retain
`eligible_for_upgrade=false`; only the strictly later, fully gated path sets it
true, while an inactive retained record without termination proof returns
`UNKNOWN/LIFECYCLE_PROOF_MISSING`. The old constant-true ABSTAIN assertion was
removed. The method and synthetic H10/H11 Action sets remain exactly
`UNKNOWN/OBSERVE/ABSTAIN/EVALUATE_REVERSAL`.

Actual verification:

- v0.4 targeted suite: `23/23 PASS`.
- v0.2 authority/contract/kernel suite: `48/48 PASS`.
- Combined execution: `71/71 PASS`.
- Three v0.4 JSON documents: `3/3 jq PASS`.
- Independent adversarial reproduction, Python AST, trailing-whitespace, and
  `git diff --check`: `PASS`.

Registry state is unchanged:
`V4-M00.result_status=NOT_RUN`,
`V4-M00.test_execution_status=TESTS_PASS_AWAITING_SOL_STAGE_GATE`, and H01–H12
remain `WAIT_DATA`. This is E0 outcome-free contract evidence only. It grants no
B4, real-data access, source probing/download, adapter work, backtest, paper,
live, market-validity, or profitability conclusion.

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `68d3f5576cea3083b458f9ef3801f8f4387d24b9d768d3473fe281fb314e437b` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `c37446d2bed4389fc8e8e370621af2b7dfaed3e2ed6b8b7f7929720f4b8dce7a` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `bc37a4070a8e3d0edb7daaa557ae3b9b8b45145f36cb0d2e29f3eea2c81ba63a` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `f663b0e8ce4a2aefb23520208db71a95042aee932375d04afc43685839196b2a` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `66491f36a5675476959ecd16c813b1f99872df0151439573afe83e25d7f62f22` |

The report physical SHA-256 is intentionally external and is computed only
after this final write; embedding it here would be self-referential.

## Terminal superseding receipt — event-clock closure

This EOF receipt supersedes every earlier terminal receipt in this append-only
report. Earlier receipt counts and hashes remain audit history only.

The same V4-M00 causal-clock P0 closure was extended to H12 without changing
stage authority: events require `source_timestamp`, `published_at`,
`available_at`, and `decision_time` to be present, valid, timezone-aware,
comparable, and each no later than the decision time. `source_timestamp` is
source provenance and is explicitly distinct from `published_at`, the public
event publication time. Missing, malformed, incomparable, future-source,
future-publication, or future-revision availability fails closed to
`DATA_INVALID` and `UNKNOWN_OR_ABSTAIN`; revisions remain append-only.

The method, registry, and synthetic contracts carry one identical frozen
`event_visibility_invariant`; H12 now requires `source_timestamp`; and the
test helper validates all four timestamps without coercion or local-time
fallback. New F24–F27 fixtures cover future source time, future revision
availability, malformed publication time, and missing source time.

### Actual verification receipt

- v0.4 synthetic contract suite: `26/26 PASS`.
- Frozen v0.2 combined research/contract/kernel/direct-AST suite: `59/59 PASS`
  (`48` combined research/contract/kernel plus `11` direct-AST).
- Independent adversarial causal-clock harness: `PASS` for five bar cases
  across H10/H11 and five event cases across H12.
- `jq empty` on the three v0.4 JSON contracts: `3/3 PASS`.
- AST causal-clock guard, trailing-whitespace scan, and `git diff --check`:
  `PASS`. The whitespace scan explicitly included all six untracked v0.4
  artifacts; ordinary `git diff --check` does not inspect untracked files.

Commands actually run:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_mtf_four_layer_v0_4_0_contract
/opt/homebrew/bin/python3.12 -B -m unittest -v tests.test_rsi_research_contract tests.test_rsi_mtf_drl_pm_v0_2_2_contract tests.test_rsi_mtf_drl_pm_v0_2_2_kernel tests.test_rsi_mtf_drl_pm_direct_ast
/opt/homebrew/bin/python3.12 -B - <<'PY'  # independent bar/H10/H11/H12 adversarial harness
jq empty config/rsi_mtf_four_layer.method_contract.v0_4_0.json config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json
/opt/homebrew/bin/python3.12 -B - <<'PY'  # AST causal-clock guard
rg -n '[[:blank:]]+$' RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md config/rsi_mtf_four_layer.method_contract.v0_4_0.json config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json tests/test_rsi_mtf_four_layer_v0_4_0_contract.py artifacts/rsi_mtf_four_layer_v0_4_0_validation_report.md
git diff --check
```

Current non-self-referential artifact hashes:

| Artifact | SHA-256 |
|---|---|
| `RSI_MTF_FOUR_LAYER_THEORY_CHALLENGER_v0_4_0.md` | `019c117a0bc6ad4b2f19dad5edbbe2d8cfec8a64ca06e432ed9f2a0626feb153` |
| `config/rsi_mtf_four_layer.method_contract.v0_4_0.json` | `3ddbfe7c4ad292af86465a7d29e12eeec84d6a1a0949b06d383ecda1033390e0` |
| `config/rsi_mtf_four_layer.hypothesis_registry.v0_4_0.json` | `df049e7f880134f08362ba5df82fc1d94afb31bcf3cb59ce57b30eb4a3acd885` |
| `config/rsi_mtf_four_layer.synthetic_measurement_contract.v0_4_0.json` | `3819318ace8e42621a4b18eacab96aab0460c2f54e588bf6d9341d4b6b1e38b2` |
| `tests/test_rsi_mtf_four_layer_v0_4_0_contract.py` | `687a03f08f34d1aee77984bffea72a22b22c48af4f0c50fca27259631734fd92` |

The validation report's physical SHA-256 remains external to this
self-referential text and must be bound after this write. These E0 contract
tests repair specified synthetic defects only. They do not reverse the current
Sol determination `V4-M00 NOT PASS` or `B4 DENY`; a new independent Sol review
is required before any gate state may change.
