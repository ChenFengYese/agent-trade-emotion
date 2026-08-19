---
name: run-theory-agent-e0-experiment
description: Resume or run the native Codex Theory Agent V2 E0 cluster experiment from its durable checkpoint. Use when a new Codex project window must create Single-Strong, Proposer, blind Challenger, and Selector subagents over frozen point-in-time contexts, record each completed paired sample, survive context interruption, evaluate 32 pairs, or report experiment status without using a custom model transport.
---

# Run Theory Agent E0 Experiment

## Purpose

Run the practical native-Codex comparison from project artifacts instead of a
custom model-call transport. Treat the checkpoint as memory and the frozen
context files as the only market inputs. Keep all work offline,
counterfactual, and non-executable.

## Start or resume

1. Resolve the project root and read, in order:
   - `requirements/history/2026-07-30-theory-paper-practice.md`, section XIV;
   - `agent-cluster/experiments/native-codex-e0-20260731/HANDOFF.md`;
   - the exact runtime `manifest.json` and `checkpoint.json` named there;
   - the three role skills under `agent-cluster/skill-sources/`;
   - `references/experiment-protocol.md`;
   - `references/recovery-contract.md`.
2. Run the state script with `verify`. Stop on any digest or event-chain
   failure.
3. Read `next_sample_index`. Never choose a sample by its later outcome and
   never skip an incomplete index.
4. Continue until all 32 pairs are recorded, then run `evaluate`.

Do not inspect an old conversation to reconstruct state. Do not use
`current`, `latest`, memory summaries, or model recollection as experiment
authority.

## Native orchestration

For one sample, read the exact canonical context bytes once and inject those
same bytes into both arms. Follow the immutable run manifest's
`native_input_transport.mode`; do not silently substitute another transport.

For `CLEAN_SINGLE_TURN_FORK_V1`, the controller creates a purpose-built current
turn containing the exact context bytes and semantic schema. A fresh worker is
spawned with `fork_turns="1"`, so it inherits that transport turn and no older
controller history. The worker must not read the repository or use tools. This
is a practical native transport boundary, not machine-attested byte transport.

Use native Codex collaboration:

1. Spawn one `SINGLE_STRONG_NATIVE` worker under the frozen transport mode.
   Keep the same worker identity for Proposal, self-review, and bounded
   selection, and return the three schema-valid semantic objects.
2. In parallel, spawn one fresh Proposer and one fresh blind Challenger under
   the same transport mode. Give each the same canonical context. Do not show
   the proposal to the blind Challenger.
3. After both cluster outputs return, spawn one Selector with the same context,
   proposal, and blind challenge. It must choose one exact `action_id` from
   `feasible_actions`.
4. Keep at most three workers active. Workers return JSON only and do not edit
   files, browse, refresh data, call tools, or message each other.
5. Save six semantic JSON objects through `apply_patch`, call the state
   script's `record` command, then verify the checkpoint before starting the
   next index.

Use the frozen reasoning text and output schema in the runtime bundle. Role
skills define separation of duties; the experiment protocol defines the
smaller semantic output used for this comparison.

## Context and budget boundary

- Pass the canonical context as task input; do not let a worker discover
  additional repository or market data. A clean single inherited transport
  turn is task input, not authority to inherit older conversation history.
- Use the same Codex model family and reasoning setting for all workers in one
  window when the product permits it.
- Record observed differences honestly. Native subagent served-model identity
  and exact token equality are not machine-attested, so the evidence class
  remains `PRACTICAL_CODEX_CLUSTER_EXPERIMENT`.
- Do not revive the old `codex exec` preflight or make the optional app-server
  adapter a prerequisite.

## State continuity

The controller is the only writer. After every completed paired sample:

- archive all six outputs;
- append one digest-chained sample event;
- advance the checkpoint by exactly one index;
- keep the accepted event head and next index durable.

If context is compacted or the window closes, stop after the current record.
A new controller resumes from `checkpoint.json`; it does not repeat completed
samples or infer missing outputs.

## Completion

After sample 127 is recorded:

1. Run `native_experiment_state.py evaluate`.
2. Run `verify` again.
3. Report path coverage, challenge coverage, exact-action errors, action
   distribution, one-hour diagnostic replay, selection status, and all
   limitations.
4. State explicitly that this is not strict transport-attested evidence,
   predictive proof, profitability proof, paper authorization, or live
   authorization.

Do not instantiate the 101% second-round account or restore automation.

## Failure behavior

Fail closed when a context digest differs, an output violates schema, a
non-selector selects an action, a Selector chooses outside the feasible set,
an index is skipped, or the event chain breaks. Preserve completed artifacts
and report the exact error. Do not repair a failed output by inventing market
facts or using later prices.
