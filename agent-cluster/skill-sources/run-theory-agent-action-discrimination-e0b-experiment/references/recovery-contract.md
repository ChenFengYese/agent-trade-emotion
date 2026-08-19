# E0B recovery contract

1. Read the authoritative handoff, then run status against its exact run root.
2. Recompute the event chain from sample 160 upward. Immutable events and output envelopes are authority; checkpoint is a recoverable projection.
3. If an event exists, all six bound outputs and receipts must exist and revalidate. Never rerun that sample.
4. If byte-identical write-once outputs exist without an event after a crash, retry `record` only with the same six semantic objects and receipts. Any differing byte is a hard stop; do not delete or overwrite.
5. If no event exists for `next_sample_index`, resume exactly that sample. Do not skip or substitute a sample.
6. If a formal child failed before a valid six-object case was recorded, stop that run according to protocol; do not silently retry the role or classify the transport failure as a market/theory result.
7. Do not read outcome bars or evaluation artifacts until the verified event count is 32 and terminal is true.
8. Do not use old chat, an E0A run, another source, mutable pointers, or a guessed digest to repair state.
9. A clean planned handoff to a new Codex window is allowed only at a verified event boundary. The new controller repeats authority and status checks before spawning a role.

An integrity failure is never permission to regenerate artifacts. Preserve the run and report the exact mismatch.
