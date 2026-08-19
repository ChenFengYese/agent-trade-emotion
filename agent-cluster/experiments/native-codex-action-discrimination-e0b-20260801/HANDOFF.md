# Native Codex Action-Discrimination E0B Handoff

## Sole formal authority

- cwd: `/Users/wt/Documents/agent-trade-emotion`
- branch: `codex/s0-research-foundation`
- implementation freeze commit: `b141750e5830238101c4cdf39a94010043e014dc`
- run ID: `native-codex-action-e0b-btcusdt-20260801T102202Z`
- exact run root: `/Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0b-btcusdt-20260801T102202Z`
- frozen sample range: `160..191`, exactly 32 ordered contexts
- evidence class: `PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`
- mode / authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`
- financial contract: `ACTION_E0B_FINANCIAL_CONTRACT_V2`
- outcome reader: `EVALUATE_AFTER_ALL_ROLE_OUTPUTS_FROZEN`

This run is the sole formal E0B authority. The E0A failure and partial runs,
all transport diagnostics, and the E0B transport preflight remain immutable
engineering evidence. They must not be resumed, copied into this run, or
counted toward its 32-sample denominator.

## Frozen bindings

- manifest self digest: `68edb61182fc1a5763b04c9856553b194a366ead4ebca585e40298c988d273f4`
- manifest physical SHA-256: `ae0e218d5f36b358dd4419d2cbdd317a602850a8a2dfe5fa6b9ca28d84276569`
- config self digest: `6729f1c3626fe9a155625f3a5ad11e428815274128bbc92588428122f05c7425`
- frozen config physical SHA-256: `13a41eb2b7b107cff518b5c40518dffca70a8aae1c976e1c6f550c9d8cda24bf`
- source config physical SHA-256: `86a9a96fae3bdd750edb9fbeee32082ac0494eb99ee8e713da25b000565f80de`
- semantic schema self digest: `52f2c564da928a3849e51d24a65904b15eebb0308bf15571be0e27486a0080a4`
- semantic schema physical SHA-256: `34d6a78dc2599a23dc7f84725259022b54c1fe79d21e3174720dc87171031398`
- source receipt self digest: `cdd4cba984d86f2a0e70bac560c5bcfa41c71df06d8290900cbe6b5a78223423`
- source receipt physical SHA-256: `02f8e9ac97295ea27bcfc9db73a72daf7d1ab98320e88a9728f972a134122a40`
- starting checkpoint self digest: `a382aafbcd3e663939437a3fa5d4e6bf5de83ae9b07ca1e5da58f32f8a15cd62`
- starting checkpoint physical SHA-256: `2da980cb705e9759c5d1133f450cb05b67441b28381b12c79622deb92c10c75c`
- design physical SHA-256: `a7637061538b44ec819e468118f9b254babcdf9fc58d4b99d0b4a6cf0a874df0`
- source run ID: `formal-e0-btcusdt-20260731T103131Z`
- source run bindings digest: `811d911890b115e6f9b426a83b29b9ffb125dea564a37bf67a52036c3d35d4aa`
- source dataset manifest digest: `2a3ea95ef9f9cf4fc4c85f684cca05f5be74cbced84deeae75534150fed439b1`
- source dataset payload digest: `c62f036a5bd5245aa73a01e545d8ebb696aaa03fb9212146e50d93680f71ab05`

Self digests are canonical-object bindings stored inside the corresponding
JSON objects. Physical SHA-256 values bind the exact bytes on disk. Neither
kind may be substituted for the other during recovery.

## Transport preflight binding

- child task: `/root/e0b_transport_preflight_v2`
- sample / context: `160 / 336a1c627d15b5f5fa49b8a43740e12d87d113a2e96b5851c532747446ca638d`
- packet digest: `7636f323a7fea9f57b7418228b4dfd72b85c8fae22bdd4a8113f145f4239dd74`
- packet byte length: `20698`
- packet physical SHA-256: `1e3c796d5e3f0e6868d60c2bdbb48c81fc28963efcc72f28abc15e68dbe3f245`
- Selector choice count: `2`
- result: `PASS_DIRECT_INLINE_NO_TRUNCATION`
- formal role output: `false`

The preflight task ID is permanently reserved and cannot be reused. Formal
packets must be regenerated from this run and must match all preflight fields
frozen in the manifest. The preflight answer is never a formal role output.

## Starting checkpoint

- integrity: `PASS`
- completed count: `0`
- next sample: `160`
- role output count: `0`
- event head: `0000000000000000000000000000000000000000000000000000000000000000`
- terminal: `false`
- frozen contexts: `32`
- stored role outputs / events / evaluation results: `0 / 0 / 0`
- outcome access during prepare: `false`

Before the first role call and after every recorded sample, run:

```bash
/opt/homebrew/bin/python3.12 -m trade_system.theory_paper_v2.presentation.action_discrimination_cli status \
  --run-root /Users/wt/Documents/agent-trade-emotion/.runtime/theory-paper-v2/action-discrimination/native-codex-action-e0b-btcusdt-20260801T102202Z
```

Stop unless every binding above matches and status reports `integrity=PASS`.
Conversation history, mutable summaries and older handoffs are not authority.

## New-window startup

Use this exact request in a fresh Codex project window:

> 使用 `$run-theory-agent-action-discrimination-e0b-experiment`，严格读取
> E0B handoff 并核验唯一权威 run
> `native-codex-action-e0b-btcusdt-20260801T102202Z`。从 checkpoint 的
> `next_sample_index` 开始，每次只完成、记录并验证一个 paired sample；任何
> packet、schema、工具使用、调度或状态异常立即停止。32/32 终态前禁止读取
> outcome，禁止 automation、paper/live、账户、订单和资金动作。

The controller must read the root `AGENTS.md`, then the installed
`run-theory-agent-action-discrimination-e0b-experiment` skill, then both
protocol references named by that skill. The controller is the sole writer.

## Formal role workflow

For each exact checkpoint sample:

1. Create one clean Single-Strong child with `fork_turns=none`; put its full
   canonical packet in the initial message and collect its three nested
   semantic objects.
2. Create independent clean Proposer and blind Challenger children from their
   complete initial packets. The Challenger must not see the proposal.
3. Freeze the validated proposal and challenge into a Selector packet, then
   create a fourth clean child with a new run-wide-unique task ID.
4. Reject rather than repair malformed, incomplete, tool-using, externally
   informed, overreaching or mismatched output. A formal role call is never
   retried or semantically replaced in the same run.
5. Record only after all six semantic objects and all six invocation receipts
   validate. Immediately run status before advancing.

The run is serial and write-once. Parallel sample writes are forbidden. A
clean planned handoff at a verified checkpoint is allowed. Recovery from a
partial write is allowed only with byte-identical artifacts under the frozen
recovery contract; conflicting bytes fail closed.

Outcome access and deterministic evaluation remain forbidden until status
proves `completed_count=32`, `role_output_count=192`, and `terminal=true`.

## Interpretation boundary

E0B tests one-step bounded action selection over one frozen, overlapping
BTCUSDT historical window. It can diagnose state/action discrimination,
theory fidelity, financial-contract compliance and topology differences. It
cannot by itself prove sequential review or reentry fulfilment, independent
market generalization, prediction, cost-stable profitability, paper readiness,
production readiness or live-trading safety.

Native collaboration does not machine-attest served-model equality, exact
token-budget equality or service-side tool isolation. Keep the practical
evidence label even if the run completes successfully.

## Forbidden

- no theory, design, config, schema, context, financial formula, scoring,
  policy, historical artifact or frozen output modification;
- no future/outcome read before the verified 32/32 terminal checkpoint;
- no E0A resume, preflight reuse, old-chat reconstruction, output repair,
  sample replacement, tuning on this outcome window or same-window rerun;
- no automation, paper/live system, account, credential, order, external
  execution authority, 101% account or real funds;
- no predictive-validity, profitability, production or strict-transport claim.

The unrelated untracked
`requirements/2026-08-01-macos-storage-cleanup.md` belongs to the user and must
remain untouched and unstaged.
