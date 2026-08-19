# Native Codex Action-Discrimination E0A Inline Successor Handoff

## Sole active authority

- cwd: `/Users/wt/Documents/agent-trade-emotion`
- run ID: `native-codex-action-e0a-inline-btcusdt-20260801T070500Z`
- run root: `/Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0a-inline-btcusdt-20260801T070500Z`
- manifest digest: `71cf6cf58e4f57cb916ec7ca8bcbeac4e2e15ddc46162becce59de3ad69da27c`
- transport: `INITIAL_MESSAGE_DIRECT_INLINE_CANONICAL_PACKET_V1`
- clean fork: `none`
- invocation receipts: required
- transport addendum physical SHA-256: `f7c4a781b9efefc9aa60af1a4127ae83d8c51373e62173450e55821331eafbfe`
- config self digest: `44008474739e7d8329324efeb6cc16162e4cbee93dcb5639829ee580da97950a`
- config physical SHA-256: `7ac9b14bc6624874133a95b17206e85a7192380119cd3df2a89098092cbc2c72`
- source dataset payload digest: `c62f036a5bd5245aa73a01e545d8ebb696aaa03fb9212146e50d93680f71ab05`
- evidence: `PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`
- mode / authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`

The predecessor run `native-codex-action-e0a-btcusdt-20260801T064710Z` is a preserved transport failure and must not be resumed. It remains `completed=0 / outputs=0`; its three formal sample-128 calls lacked packets. Do not copy or reinterpret those errors as semantic outputs.

## Frozen equivalence proof

The successor's 32 ordered rows exactly equal the predecessor by:

- context digest;
- state digest;
- candidate calculation digest;
- path matrix digest;
- sample index.

Only run identity, manifest, transport config and handoff differ. Dataset, context, financial policy, profiles, actions, scoring and terminal rules are unchanged.

## Starting checkpoint

- integrity: `PASS`
- completed count: `0`
- next sample: `128`
- role output count: `0`
- event head: `0000000000000000000000000000000000000000000000000000000000000000`
- terminal: `false`
- outcome reads: `0`

Verify before each action:

```bash
python3.12 -m trade_system.theory_paper_v2.presentation.action_discrimination_cli status \
  --run-root /Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0a-inline-btcusdt-20260801T070500Z
```

## Exact role transport

For every role call:

1. generate the exact packet from this run;
2. create a clean child with `fork_turns=none`;
3. put the entire canonical packet JSON in the spawn initial message itself;
4. never tell the child to read a path, tool output, parent context or later message;
5. observe that the child used no tool or external data;
6. preserve raw JSON unchanged;
7. create an invocation receipt with exact role key, child task ID, packet digest, packet byte length, context digest and practical attestation fields.

Single-Strong uses one child/packet for its three nested outputs; copy the same task and packet identity into the three role-key receipts. Proposal and blind Challenger use independent children and packets. Selector is spawned only after the exact proposal and challenge are frozen into its packet.

Record one case only when all six semantic objects and six receipts are valid. Immediately verify before moving to the next index. No semantic repair or same-run transport fallback is permitted.

Outcome evaluation is forbidden until `completed=32 / role_output_count=192 / terminal=true` is verified.

## Forbidden

- no modification of source, theory, addendum, config, schema, context, formulas, scoring or historical artifacts;
- no predecessor-run retry, no old chat reconstruction, no mutable `latest/current`;
- no automation, paper/live, account, credential, order, 101% account or real funds;
- no strict same-model/token claim, predictive-validity claim, profitability claim or production promotion.

The unrelated untracked `requirements/2026-08-01-macos-storage-cleanup.md` must remain untouched.
