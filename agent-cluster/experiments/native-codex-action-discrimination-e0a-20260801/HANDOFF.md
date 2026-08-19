# Native Codex Action-Discrimination E0A Handoff

## Authority

- cwd: `/Users/wt/Documents/agent-trade-emotion`
- branch at freeze: `codex/s0-research-foundation`
- run ID: `native-codex-action-e0a-btcusdt-20260801T064710Z`
- run root: `/Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0a-btcusdt-20260801T064710Z`
- manifest digest: `3ef7153fe04e0e06ef1584a0e3d5f05fcc6a4b2538af59d2ee9a55ef6ac6780f`
- design physical SHA-256: `4071dbfc04ecf1432f4f27b184b6e8458a75485a2a7e26f6f0e3b1dd6717e498`
- config self digest: `0a362c06abd9aec8f501ddee52bb34540549f31291856c4b3722b88cd2b85a67`
- config physical SHA-256: `c28791bf12385c5b5c5073aa579900b4c03b2230a8240a594242886f452403f3`
- semantic schema digest: `52f2c564da928a3849e51d24a65904b15eebb0308bf15571be0e27486a0080a4`
- source dataset payload digest: `c62f036a5bd5245aa73a01e545d8ebb696aaa03fb9212146e50d93680f71ab05`
- evidence: `PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`
- mode / authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`

Do not use another run, old chat state, `current/latest`, the prior 096..127 outputs, or a newly generated manifest as authority.

## Verified starting checkpoint

At the freeze boundary:

- integrity: `PASS`
- completed count: `0`
- next sample: `128`
- role output count: `0`
- event head: `0000000000000000000000000000000000000000000000000000000000000000`
- terminal: `false`
- frozen contexts: `32`
- formal role outputs: `0`

Before doing anything else, run:

```bash
python3.12 -m trade_system.theory_paper_v2.presentation.action_discrimination_cli status \
  --run-root /Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0a-btcusdt-20260801T064710Z
```

The status output, immutable events and manifest override this initial snapshot after progress begins.

## Required procedure

Use `$run-theory-agent-action-discrimination-experiment`. Process only the exact `next_sample_index`, one case at a time. For each case produce:

1. one clean Single-Strong bundle containing proposal, self-review and selection;
2. one clean cluster Proposer output;
3. one clean blind Challenger output that has not seen the Proposer;
4. one clean Selector output that receives the exact frozen proposal and challenge.

The controller is the only writer. A role returns JSON only and uses no tool, file, network, memory or external data. Do not repair invalid output. Six valid semantic objects are recorded atomically, then status is verified before the next sample.

After `completed=32 / role_output_count=192 / terminal=true`, and only then, run the outcome evaluator. Freeze its result even when the verdict is negative or inconclusive.

## Forbidden

- no modification of theory, design, config, schema, context, risk formula, state profile, scoring or terminal rule;
- no reading future outcome bars before the 32-event terminal chain;
- no automation, paper/live adapter, private account, credential, 101% account, order or real funds;
- no claim of strict same-model/token attestation, prediction validity, profitability or production readiness.

The unrelated untracked file `requirements/2026-08-01-macos-storage-cleanup.md` belongs to another task and must not be staged or modified.
