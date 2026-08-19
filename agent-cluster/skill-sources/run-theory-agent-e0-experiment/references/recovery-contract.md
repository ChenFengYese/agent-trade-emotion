# Cross-window recovery contract

## Authority order

1. immutable `manifest.json`
2. digest-verified `checkpoint.json`
3. ordered `events/096.json` through the last completed sample
4. write-once context and output artifacts referenced by those events
5. conversation memory only as non-authoritative convenience

## Resume rule

Run:

```bash
python3.12 agent-cluster/skill-sources/run-theory-agent-e0-experiment/scripts/native_experiment_state.py verify \
  --run-root <exact-run-root>
```

Continue only the exact `next_sample_index`. If it is null and status is
`COLLECTION_COMPLETE_PENDING_EVALUATION`, run `evaluate`. If status is
`EXPERIMENT_COMPLETE_PRACTICAL`, report the stored result and do not rerun.
Use only the `native_input_transport.mode` frozen in that run's manifest.

## Interruption rule

Do not mark a sample complete until all six outputs validate and its event is
written. An interrupted, unrecorded sample may be rerun. A recorded sample is
immutable and must not be repeated or replaced.

## Memory rule

The checkpoint carries the accepted event head, completed indices, next index,
and current status. No narrative summary can replace or override those fields.
