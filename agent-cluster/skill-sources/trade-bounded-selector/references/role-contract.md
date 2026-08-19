# Selector role contract summary

This stable package reference is for bootstrap construction and package audit.
The live role call consumes only the canonical
`resolved_role_input_document.v1` bytes supplied by
`APPLICATION_DECISION_SESSION`.

## Port

`ResolvedRoleInputBundle.v1 -> AgentSelection.v1`

## Unique authority

- Open-ended owner: explanation and choice among existing feasible members.
- Deterministic owners: candidate assembly, payoff/risk/cost calculation,
  constraints, feasible-set membership, criterion validation, state reduction,
  persistence, replay, governance, and commit.
- Runtime authority: `E0_OFFLINE_COUNTERFACTUAL / NONE_E0 / executable=false`.

## Selection invariants

`selected_candidate_ref` is non-null and names an exact member of the complete
`FeasibleActionSet.v1`. No-action is a first-class member with explicit
obligations and opportunity cost. Ranking uses the exact frozen
`DecisionCriterionPolicy.v1`; E0 carries no accepted numeric probability
authorization, and the Selector cannot invent one.
