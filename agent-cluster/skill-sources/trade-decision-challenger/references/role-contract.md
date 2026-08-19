# Challenger role contract summary

This stable package reference is for bootstrap construction and package audit.
The live role call consumes only the canonical
`resolved_role_input_document.v1` bytes supplied by
`APPLICATION_DECISION_SESSION`.

## Port

`ResolvedRoleInputBundle.v1 -> ChallengeEnvelope.v1`

## Unique authority

- Open-ended owner: typed conflict and omission claims.
- Deterministic owner: `ChallengeDisposition.v1`, constraint verification,
  candidate removal, persistence, governance, and commit.
- Runtime authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`.

## Challenge modes

- `POST_PROPOSAL`: proposal references are the exact frozen proposal;
  `blinding_proof_ref` is null.
- `BLIND_CONTEXT_ONLY`: proposal references are null, proposal projections are
  explicitly omitted, and `blinding_proof_ref` is valid.

A blind claim may identify context-grounded missing paths or required
invariants, but cannot allege a byte-level defect in a proposal it did not see.
A market preference is never a verified hard structural defect.
