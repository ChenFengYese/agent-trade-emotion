# Recovery contract

1. Run the status command against the handoff's exact run root.
2. Recompute the event chain from sample 128 upward. Immutable events and output envelopes are authority; the checkpoint is only a recoverable projection.
3. If an event exists, all six bound outputs must exist and revalidate. Never rerun that sample.
4. If output files exist without an event, retry record only with byte-identical outputs. Conflicting bytes are a hard stop.
5. If no event exists for `next_sample_index`, resume that exact sample. Do not skip it.
6. Do not read evaluation artifacts or outcome bars until the verified event count reaches 32.
7. Do not use old chat text, another run, `latest` pointers, or a guessed digest to repair state.

An integrity failure is not permission to delete or regenerate artifacts. Preserve the run and report the exact mismatch.
