---
name: run-theory-agent-action-discrimination-e0b-experiment
description: Resume or run the frozen Theory Agent V2 E0B action-discrimination experiment with native Codex subagents. Use when asked to continue, verify, monitor, or complete the offline paired Single-Strong versus blind Proposer-Challenger-Selector experiment over samples 160..191.
---

# Run Theory Agent Action Discrimination E0B

## Authority

1. Read `agent-cluster/experiments/native-codex-action-discrimination-e0b-20260801/HANDOFF.md` completely.
2. Treat its exact run root, manifest, checkpoint, event head, config, source receipt, dataset and design digests as authority. Never reconstruct state from chat or an older E0A run.
3. Read [experiment-protocol.md](references/experiment-protocol.md) before any role call. Read [recovery-contract.md](references/recovery-contract.md) whenever the run is incomplete, interrupted, or inconsistent.
4. Run `python3.12 -m trade_system.theory_paper_v2.presentation.action_discrimination_cli status --run-root <run-root>` and stop unless integrity is `PASS` and every handoff binding matches.

## Non-negotiable boundary

- Keep `system_mode=E0_OFFLINE_COUNTERFACTUAL`, `external_execution_authority=NONE_E0`, and `executable=false`.
- Do not resume or create automation, connect paper/live systems, open an account, send orders, use credentials, or touch funds.
- Do not change theory, design, config, profiles, financial formulas, context, packet rules, scoring, terminal policy, source data, or historical outputs after freeze.
- Outcome bars are inaccessible until all 192 role outputs and 32 events are frozen and verified.
- Evidence remains `PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`; native collaboration does not attest served-model or exact-token equality.
- E0B is a one-step action-selection experiment. It cannot prove cross-cycle review or reentry fulfilment; review-dependent actions after one hour are terminal-incomparable.

## Controller workflow

The root controller is the only project-artifact writer. Role agents receive a complete canonical packet in their initial message and return JSON only. They must not use tools, files, network, memory, later prices, or outside facts.

For the exact `next_sample_index`:

1. Generate `single-strong-bundle`. Spawn one clean native child with `fork_turns=none` and put the entire canonical packet directly in its initial message. It returns exactly three nested objects: proposal, self-review, selection.
2. Generate `cluster-proposal` and `cluster-challenge` from the same frozen context. Use independent clean children; the blind Challenger must not receive or see the Proposer output.
3. Generate `cluster-selection` only after the exact proposal and blind challenge are frozen into its packet. Use a fourth clean child.
4. Do not repair invalid JSON, infer missing fields, replace evidence IDs, alter action names, or rerun a failed formal role. Any child creation failure, truncation, schema error, tool/external-data use, timeout, or scheduler limit stops the run without advancing.
5. Build exact invocation receipts. Single's three objects bind one task and one packet; Proposer, Challenger, and Selector bind three distinct clean tasks. Every task ID is globally unique for the full run and cannot be reused by a later sample. The kernel independently reconstructs packet digest/length and Selector upstream objects.
6. Call `record` only after all six semantic objects validate. A crash before the event may be resumed only with byte-identical objects; conflicting bytes are a hard stop.
7. Immediately run `status`. Continue only if completed count, next index, output count, event head and manifest binding agree.
8. Process one sample at a time through 191. A planned new-window handoff at a verified checkpoint is allowed; parallel case writes are forbidden.

Use `scripts/native_action_state.py` as the thin CLI entrypoint when convenient.

## Completion

After status reports `completed_count=32`, `role_output_count=192`, and `terminal=true`:

1. Run `evaluate` exactly once. This is the first authorized future-outcome read.
2. Verify the immutable result and every per-case diagnostic.
3. Report the exact terminal verdict, contract-comparability exclusions and KPI values without upgrading them to predictive validity, profitability, paper readiness, or production evidence.
4. Update the handoff and requirement record; commit only intended project files and preserve unrelated user changes.

Freeze negative or inconclusive results. Do not tune and rerun the same outcome window.
