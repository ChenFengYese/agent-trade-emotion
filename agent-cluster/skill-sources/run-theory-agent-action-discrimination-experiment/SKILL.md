---
name: run-theory-agent-action-discrimination-experiment
description: Resume or run the frozen Theory Agent V2 E0A action-discrimination experiment with native Codex subagents. Use when asked to continue, monitor, verify, or complete the paired Single-Strong versus blind Proposer-Challenger-Selector experiment without paper, live, automation, account, or order authority.
---

# Run Theory Agent Action Discrimination Experiment

## Authority

1. Read `agent-cluster/experiments/native-codex-action-discrimination-e0a-inline-20260801/HANDOFF.md`.
2. Treat its exact manifest, checkpoint, event head, config, dataset and design digests as authority. Do not reconstruct state from chat.
3. Read [experiment-protocol.md](references/experiment-protocol.md) before any role call. Read [recovery-contract.md](references/recovery-contract.md) when a run is incomplete, interrupted, or inconsistent.
4. Run `python3.12 -m trade_system.theory_paper_v2.presentation.action_discrimination_cli status --run-root <run-root>` and stop if integrity is not `PASS`.

## Non-negotiable boundary

- Keep `system_mode=E0_OFFLINE_COUNTERFACTUAL`, `external_execution_authority=NONE_E0`, and `executable=false`.
- Do not resume automations, connect paper/live systems, open an account, create a 101% round-two account, send orders, or use real funds.
- Do not change theory, config, profiles, financial formulas, contexts, scoring, manifest, source data, or historical outputs after the manifest is frozen.
- Outcome bars are inaccessible until all 192 role outputs and 32 events are frozen and verified.
- Evidence remains `PRACTICAL_CODEX_ACTION_DISCRIMINATION_EXPERIMENT`; native collaboration does not attest the served model or exact token equality.

## Controller workflow

The root/controller is the only artifact writer. Role agents return JSON only and must not use tools, files, network, memory, or external data.

For the exact `next_sample_index`:

1. Generate the `single-strong-bundle` packet. Spawn one clean native subagent with `fork_turns=none` and put the complete canonical packet directly in its initial message. It returns the three nested outputs in order of reasoning: proposal, self-review, selection.
2. Generate the cluster proposal packet and blind challenge packet from the same frozen context. Spawn clean, independent native subagents using the same direct-inline initial-message protocol. The Challenger must not receive or see the Proposer output.
3. Generate the cluster selector packet only after proposal and blind challenge are returned. Spawn a clean native Selector with the complete selector packet directly inline; it sees the common context plus those two frozen outputs.
4. Do not rewrite invalid JSON, infer missing fields, substitute action synonyms, or repair content. Validation failure leaves the sample incomplete and stops the run.
5. Put the four raw response files and exact `invocation-receipts.json` in a temporary case directory and call `record`. Each receipt binds the role, child task, packet digest and byte length, `fork_turns=none`, context digest, and controller-observed tool/external-data status. The kernel validates six semantic outputs and all receipts before it writes the event or advances the checkpoint.
6. Immediately run `status`; continue only if the completed count, next index, output count, and event head all agree.
7. Process one sample at a time through 159. Do not parallel-write cases.

Use `scripts/native_action_state.py` as the thin CLI entrypoint when convenient.

## Completion

After status reports `completed_count=32`, `role_output_count=192`, and `terminal=true`:

1. Run `evaluate` once. This is the first authorized future-outcome read.
2. Verify the immutable result and per-case diagnostics.
3. Report the exact terminal verdict and KPI values without upgrading them to prediction, profitability, paper readiness, or production evidence.
4. Update the handoff and requirement record; commit only the intended project files and leave unrelated user changes untouched.

If the verdict is `NO_ACTION_DISCRIMINATION` or `INCONCLUSIVE_ACTION_TRADEOFF`, freeze it. Do not tune and rerun the same outcome window.
