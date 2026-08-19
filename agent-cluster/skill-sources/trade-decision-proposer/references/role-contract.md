# Proposer role contract summary

This stable package reference is for bootstrap construction and package audit.
The live role call consumes only the canonical
`resolved_role_input_document.v1` bytes supplied by
`APPLICATION_DECISION_SESSION`.

## Port

`ResolvedRoleInputBundle.v1 -> AgentProposalEnvelope.v1`

## Unique authority

- Open-ended owner: semantic multi-path proposal composition.
- Deterministic owners: point-in-time admission, canonicalization, numeric
  calculation, constraint validation, state reduction, persistence, replay,
  governance, and commit.
- Runtime authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`.

## Required coverage

The result names a primary path, material alternatives, a null/no-action path,
and an other/unknown path. It preserves the prior strategic state, registered
time-scale permissions, falsifiers, review clocks, stage and reentry
contracts. It includes `NO_ACTION_WITH_OBLIGATION` when dependencies permit.

The semantic `ActionIntent` vocabulary is:

`KEEP_CORE`, `ACTIVATE_REGISTERED_STAGE`, `REDUCE_TACTICAL`,
`PARTIAL_PROFIT`, `EXIT_STRATEGIC`, `EXIT_TO_REENTRY_PENDING`,
`REENTER_PARTIAL`, `NO_ACTION_WITH_OBLIGATION`.

These tokens carry no permission. `CREATE_REENTRY_CONTRACT` is an atomic effect,
not an action intent. HEDGE is not an E0 candidate.
