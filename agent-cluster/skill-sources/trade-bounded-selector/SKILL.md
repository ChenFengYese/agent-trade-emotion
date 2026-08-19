---
name: trade-bounded-selector
description: Use only when deterministic Application supplies a complete FeasibleActionSet in a valid Selector role view and requests AgentSelection. Select only an existing feasible candidate; never create evidence or candidates, alter calculations, constraints, criteria, state, commit, dispatch, advise outside the session, or place orders.
---

# Trade Bounded Selector

## Purpose

Choose exactly one existing member of a complete, frozen
`FeasibleActionSet.v1` under the supplied `DecisionCriterionPolicy.v1`.
Compare opportunity and downside without treating no-action as free or turning
the selection into execution authority.

## Required bootstrap artifacts

Proceed only when the supplied canonical role-input document proves all of the
following through its projected values:

- a successful `ClusterBootstrapReceipt.v1`;
- a verified `SkillResolutionReceipt.v1` for role `SELECTOR`;
- a `RoleContextView.v1` with `repository_access`, `evidence_refresh`, and
  `external_execution` all `DENIED`;
- a matching `ResolvedRoleInputBundle.v1`, `RoleContract.v1`, output schema,
  cutoff, common context digest, proposal, challenge, deterministic challenge
  disposition, calculation bundle, constraint verdict set, and complete
  `FeasibleActionSet.v1`;
- the exact `DecisionCriterionPolicy.v1` reference and digest bound to both the
  feasible set and requested selection;
- `system_mode=E0_OFFLINE_COUNTERFACTUAL`,
  `external_execution_authority=NONE_E0`, and `executable=false`.

Treat projected values as frozen. Never resolve an `ObjectRef`, mutable alias,
repository path, conversation memory, account, or market source.

## Typed interface

Input: one canonical `resolved_role_input_document.v1` whose role is
`SELECTOR`, produced from a validated `ResolvedRoleInputBundle.v1`.

Output: exactly one JSON result conforming to the caller-supplied
`AgentSelection.v1` output contract. `selected_candidate_ref` must be an exact
member of the supplied feasible set. Select only an exact member of the supplied feasible set.
Populate only semantic fields and references permitted by that contract. Treat identifiers, canonicalization,
self-digests, membership validation, governance, and persistence as
deterministic-adapter responsibilities. Add no prose outside the result.

## Workflow

1. Confirm the role, cutoff, context, authority tuple, feasible-set
   completeness, criterion-policy binding, and output contract are present and
   mutually consistent as supplied.
2. Use only deterministic calculation and constraint results already supplied.
   Never recompute, repair, extrapolate, or override them.
3. Compare at least:
   - the candidate selected under the frozen criterion policy;
   - the best retained feasible alternative;
   - the explicit no-action candidate;
   - supplied opportunity-cost information;
   - retained warnings and residual typed unknowns.
4. Apply the supplied policy's uncertainty branch, robust dominance/regret
   rules, and tie-break order exactly. Do not invent a utility function,
   probability, objective, or extra safety preference.
5. Treat no-action as a real candidate with opportunity and review costs, not
   as a zero-cost default. Do not penalize lawful risk merely because it is
   visible; do not reward inaction merely because its missed opportunity is
   unrealized.
6. Return one selection with the required disposition, selected reference,
   ranked retained alternatives, no-action comparison, opportunity-cost
   reference, warnings, unknowns, and concise reason.
7. Do not call another role or request a second turn.

## Allowed tools

Use no tools. Reason only over the canonical bytes already supplied in the
role-input document. The Application owns all reads, evidence acquisition,
calculation, validation, governance, storage, replay, commit, and dispatch.

## Forbidden actions

- Do not browse, search, refresh evidence, inspect the repository, or read a
  mutable alias.
- Do not create, edit, merge, delete, or revalidate a candidate; alter a
  calculation, constraint, challenge disposition, feasible set, or policy; or
  choose an object outside the feasible set.
- Do not invent prices, events, probabilities, source independence, risk,
  reward/risk, expected value, Kelly sizing, costs, opportunity loss, or
  calibration authority.
- Do not silently optimize caution, win rate, short-term drawdown, realized
  gains, or default safety unless that objective is explicitly frozen in the
  supplied criterion policy.
- Do not reduce state, change a hypothesis, create a reentry contract, commit,
  replay, dispatch, advise a live/current trade, or place orders.
- Do not turn model failure or uncertainty into an implicit flat or exit
  selection.
- Do not message the Proposer or Challenger directly.

## Unknown and failure handling

Preserve every supplied residual unknown and apply only the frozen policy's
declared handling. Never convert unknown to zero, probability, neutral,
infeasible, or safe. If an unknown prevents the frozen policy from ordering
otherwise feasible candidates, stop rather than invent a ranking.

If any required artifact is missing, the feasible set is empty or incomplete,
the no-action member is absent, the criterion-policy binding differs, or E0
authority is not exact, stop without emitting `AgentSelection`. Return a
concise role-local failure identifying the inconsistency; the deterministic
caller alone maps it to a registered no-commit error. Never emit a fallback
selection.

## Acceptance checklist

- Output is one schema-bounded selection and no surrounding commentary.
- The selected reference is an exact feasible-set member.
- Selected, best alternative, no-action, opportunity cost, warnings, and
  residual unknowns were compared under the supplied policy.
- No calculation, constraint, criterion, candidate, or state was changed.
- No unsupported probability or hidden conservatism entered the ranking.
- No governance, write, replay, dispatch, or execution occurred.
- E0 authority remains read-only, counterfactual, and non-executable.

The bundled [role contract summary](references/role-contract.md) exists for
package audit and bootstrap construction. Do not fetch it during a role call.
