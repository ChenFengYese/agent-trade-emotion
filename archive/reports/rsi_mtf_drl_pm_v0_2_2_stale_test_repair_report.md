# RSI-MTF-DRL-PM v0.2.2 stale-test repair report

## Scope and workspace facts

- CWD: `/Users/wt/Documents/agent-trade-emotion`
- Branch: `codex/s0-research-foundation`
- HEAD: `7ca3fc4f99a57f98217e703f222b295653ace87e`
- Permitted change: only the four stale expected literals in
  `tests/test_rsi_mtf_drl_pm_v0_2_2_kernel.py`: the two strategy-contract
  authority values and the two `contract.py` source-authority values.
- No market or historical data was read; no runtime-state directory was read;
  no champion, strategy-contract, or active G1 file was modified.

## Authority check

The read-only authority file was
`config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json`.

| File | Actual bytes | Actual SHA-256 |
|---|---:|---|
| `config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json` | 23,636 | `26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc` |
| `trade_system/rsi_mtf_drl_pm_v0_2_2/contract.py` | 34,460 | `ec301735ed867022f1ac0c92c68caaad8bfc9cf0a939c9063f36acf514a1b554` |

The strategy-contract values match the independently supplied authority value.
The dedicated v0.2.2 contract suite also passed `15/15`, including the frozen
`contract.py` AST allowlist and frozen-input tamper-rejection checks. No source
file was modified by this repair.

## Assertion repair

In `KernelB2Tests.test_frozen_b1_authorities_are_unchanged`, the strategy
contract expected tuple changed only as follows:

| Field | Before | After |
|---|---:|---:|
| byte size | `23_639` | `23_636` |
| SHA-256 | `baf9f21109a3183031eed41c9c81683561045e1c22b4bb8c370c119edc356bb4` | `26ab29e08968518a758a45ce872dd748543e59b93e2909b19e35052d2bdd4cdc` |

The subsequent, separately authorized `contract.py` source-authority tuple
changed only as follows:

| Field | Before | After |
|---|---:|---:|
| byte size | `34_463` | `34_460` |
| SHA-256 | `34edf3aee78dc270239cba9f9a78766f3d6626f7807bf8063f2710461f75efa9` | `ec301735ed867022f1ac0c92c68caaad8bfc9cf0a939c9063f36acf514a1b554` |

## Commands and results

Read-only authority check:

```text
wc -c config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json
shasum -a 256 config/rsi_mtf_drl_pm.strategy_contract.v0_2_2.json
```

Before the repair, the contract/kernel-only command was:

```text
python3.12 -m unittest -v \
  tests/test_rsi_mtf_drl_pm_v0_2_2_contract.py \
  tests/test_rsi_mtf_drl_pm_v0_2_2_kernel.py
```

Result: `30` run, `29` pass, `1` fail. The failure was the stale
strategy-contract size assertion: actual `23636`, expected `23639`.

After the repair, the pre-existing directed authority/contract/kernel command
was:

```text
/opt/homebrew/bin/python3.12 -B -m unittest -v \
  tests.test_rsi_research_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_contract \
  tests.test_rsi_mtf_drl_pm_v0_2_2_kernel
```

Intermediate result after the strategy-contract tuple repair: `48` run,
`47` pass, `1` fail. The sole remaining failure was the stale `contract.py`
source-authority tuple documented above.

After the dedicated contract-suite verification and the two additional
test-literal updates, the same command was rerun.

Final result: `48` run, `48` pass, `0` fail (`OK`).

## Boundary

These checks establish only byte-level test/authority consistency. They do not
establish market validity, backtest performance, paper-trading readiness, or
trading authorization.
