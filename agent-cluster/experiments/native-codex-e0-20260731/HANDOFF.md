# Native Codex Theory Agent V2 E0 handoff

## Current run

- Run ID: `native-codex-e0-btcusdt-20260801T043054Z`
- Exact run root:
  `.runtime/theory-paper-v2/native-codex-cluster/native-codex-e0-btcusdt-20260801T043054Z`
- Manifest digest:
  `d1bb654f4a4dfa4a64eb2aeac2c903d56ca5cbcd0d4cded7a53aa9fdcd0495c2`
- Evidence class: `PRACTICAL_CODEX_CLUSTER_EXPERIMENT`
- Initial status: `READY_FOR_NATIVE_CODEX`
- Initial next sample: `96`
- Sample range: `96..127`, exactly 32 paired contexts
- Configured worker model: `gpt-5.6-sol`
- Configured reasoning effort: `medium`
- Calls per arm: `3`
- Input transport: `CLEAN_SINGLE_TURN_FORK_V1`

The mutable status authority is the digest-verified `checkpoint.json` in the
exact run root. Collection and evaluation are complete:
`completed_count=32`, `next_sample_index=null`,
`status=EXPERIMENT_COMPLETE_PRACTICAL`; context integrity and the event chain
both verify as `PASS`. Do not rerun or replace a recorded sample.

The earlier pre-call run `native-codex-e0-btcusdt-20260731T110012Z` remains
preserved with zero Agent outputs and is superseded because its manifest did
not freeze the native model configuration. Run `...T111022Z` contains two
engineering-diagnostic pairs whose workers opened context files themselves;
that violates the final byte-injection protocol. Run `...T112457Z` is also
preserved at `completed_count=0`: native collaboration could not reliably
place its complete 31KB context in a `fork_turns=none` spawn message, workers
could not stay open for multipart delivery, and direct app input to a
multi-agent v2 child was rejected. None of these older runs may be resumed,
copied into, or counted toward the authoritative 32-pair denominator.

The current authoritative run was created before any formal worker output
after a non-counting transport diagnostic proved that a purpose-built current
turn can carry the complete bytes and a fresh worker can inherit only that
turn. Its manifest freezes this as `CLEAN_SINGLE_TURN_FORK_V1`. It completed
without a partial sample.

## Stored result

- Result digest:
  `b2fa08eb9dac647c6949c8c405a6ecb2eae55a7e654ed286fb8a7239c8b2d28d`
- Selection status: `PRACTICAL_CLUSTER_PREFERRED`
- Outputs/events: `192 / 32`
- Mean composite, cluster/single: `0.9895833 / 0.8706597`
- Mean challenge coverage, cluster/single: `0.984375 / 0.6354167`
- Mean path coverage, cluster/single: `0.984375 / 0.9765625`
- Hard action errors, cluster/single: `0 / 0`
- Action distribution in both arms: `HOLD_STATE=31`, `WAIT_FLAT=1`
- One-hour diagnostic net PnL, cost, and primary-path capture: identical across
  both arms

The frozen preference establishes better structural challenge coverage under
this metric. It does not establish different actions, better dynamic position
management, predictive validity, or economic improvement.

## New-window startup

Use this exact request:

> 使用 $run-theory-agent-e0-experiment，核验唯一权威 run
> native-codex-e0-btcusdt-20260801T043054Z 的已完成 checkpoint 与 stored
> result。若状态为 `EXPERIMENT_COMPLETE_PRACTICAL`，只报告结果，不重跑、
> 不替换样本，不读取或复用 T110012Z/T111022Z/T112457Z 输出。

The controller must first read the root `AGENTS.md`, then the selected skill,
then run the skill's `verify` command. Conversation history is not authority.

## Boundary

This run compares native Single-Strong and blind three-role Codex workflows.
It deliberately does not claim machine-attested served-model equality or exact
token-budget equality. It cannot be relabeled as the abandoned strict
transport-attested run.

No automation, private account, paper order, live order, or real-funds
authority is included.
