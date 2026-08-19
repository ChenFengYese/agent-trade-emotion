# V4.0.0 Decision & Trading Specification

V4.0 is the current methodology baseline for the transition from market analysis to non-executable trade planning. It does not grant paper, testnet, live-order, account, credential, or fund authority.

## Core chain

`PIT Evidence → State → Competitive Hypotheses → Evidence Update → Structure → Risk → Opportunity/Path → Execution → Position → Management → Exit/Re-entry → Audit`

## Hard separations

- Risk budget is an account-loss constraint, not a notional or leverage rule.
- Structural invalidation is chosen before sizing; size is derived from risk and stress constraints.
- PR measures opportunity geometry/path efficiency; it is never a standalone entry signal.
- EV compares scenario-weighted net outcomes after execution costs; probability may remain ordinal or banded when calibration is absent.
- Probe/Lead/Main are functional exposure states, not fixed percentages. Any increase in exposure requires new evidence.
- A limit order is not a fill. A target is a management event, not an automatic flatten instruction.
- Thesis validity and position quality are separate variables.
- Exit and re-entry are separate states.
- Canonical examples teach protocol conformance; adversarial cases test capability.

## Stage 4 benchmark architecture

- Stage 4-A Canonical: seven existing path cases, used to verify methodology conformance.
- Stage 4-B Adversarial: contradictory and mutated paths, including persistent breakout, false-break sequences, V-reversals, range persistence, high/low PR traps, missing data, and execution failure.
- Stage 4-C Repeatability/Mutation: same PIT input repeated and one evidence variable changed at a time.
- Stage 4-D OOS Validation: only after protocol validation; evaluates whether the decision architecture produces stable cost-aware outcomes.

## Required per-case record

`PIT Cutoff → FACT → INFERENCE → Market State → Evidence Matrix → H1/H2/H3 → Structure Map → Stop Architecture → Risk Engine → Multi-horizon PR → Scenario EV → Execution → Position Architecture → Management → Exit/Re-entry → Independent Critic → Final Decision`

V4.0 deliberately avoids adding indicators for their own sake. The objective is to make evidence relationships, risk mathematics, event definitions, execution assumptions, and decision changes auditable.
