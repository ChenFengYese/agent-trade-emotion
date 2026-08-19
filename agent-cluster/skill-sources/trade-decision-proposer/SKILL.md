---
name: trade-decision-proposer
description: Use only when deterministic Application supplies a valid Proposer role view and requests AgentProposalEnvelope. Generate bounded multi-path decision candidates; never calculate canonical risk, validate, select, commit, refresh data, advise a current trade outside the session, or place orders.
---

# Trade Decision Proposer

## Purpose

Produce one untrusted, bounded `AgentProposalEnvelope.v1` from the exact
immutable Proposer input supplied by `APPLICATION_DECISION_SESSION`. Preserve
the strategic state across time while expressing competing market paths and
their lawful semantic actions. Do not turn the proposal into permission.

## Required bootstrap artifacts

Proceed only when the supplied canonical role-input document proves all of the
following through its projected values:

- a successful `ClusterBootstrapReceipt.v1`;
- a verified `SkillResolutionReceipt.v1` for role `PROPOSER`;
- a `RoleContextView.v1` with `repository_access`, `evidence_refresh`, and
  `external_execution` all `DENIED`;
- a matching `ResolvedRoleInputBundle.v1`, `RoleContract.v1`, output schema,
  cutoff, accepted state or strict genesis basis, and context digest;
- `system_mode=E0_OFFLINE_COUNTERFACTUAL`,
  `external_execution_authority=NONE_E0`, and `executable=false`.

Treat every projected value as frozen. Never resolve an `ObjectRef`, mutable
alias, repository path, conversation memory, account, or market source.

## Typed interface

Input: one canonical `resolved_role_input_document.v1` whose role is
`PROPOSER`, produced from a validated `ResolvedRoleInputBundle.v1`.

Output: exactly one JSON result conforming to the caller-supplied
`AgentProposalEnvelope.v1` output contract. Populate only semantic fields and
references permitted by that contract. Treat identifiers, canonicalization,
self-digests, numeric calculations, validation, and persistence as
deterministic-adapter responsibilities. Add no prose outside the result.

The proposal must cover:

- one primary path;
- every material supported alternative path within the bounded input;
- the explicit null/no-action path;
- the explicit other/unknown path;
- at least one `NO_ACTION_WITH_OBLIGATION` plan when its registered
  dependencies are present;
- typed strategic, geometry, position, reentry, and execution facets only when
  the supplied output contract permits them.

Use only the current closed vocabularies in the supplied contract. Reference
only registered hypotheses, premises, falsifiers, stages, geometry,
protection, review clocks, evidence, and risk envelopes already present in the
role view. A proposed invalidation is a non-authoritative claim and requires a
registered hard invalidator. A risk reduction must not silently invalidate a
surviving thesis.

## Workflow

1. Confirm the role, bootstrap, cutoff, state basis, authority tuple, and output
   contract are present and mutually consistent as supplied.
2. Separate admitted observations from typed unknowns. Do not count repeated or
   commonly derived evidence as independent confirmation.
3. Explicitly update the prior strategic hypothesis by evidence delta; do not restart the
   analysis from the latest snapshot.
4. Keep time-scale authority intact. Lower-timeframe evidence may alter
   execution or risk facets but may not erase a higher-timeframe thesis unless
   it maps to a registered promotion rule or hard invalidator.
5. Build bounded primary, alternative, null, and other/unknown paths. For each
   path, cite supplied support, falsifier, affected premise, next review
   obligation, and a lawful semantic action.
6. Preserve exit/reentry symmetry. If the thesis survives while exposure goes
   to zero, propose `EXIT_TO_REENTRY_PENDING` with the required reentry-contract
   effect `CREATE_REENTRY_CONTRACT`; never create an absorbing flat state.
7. Return one complete proposal. Do not call another role or request a second
   turn.

## Allowed tools

Use no tools. Reason only over the canonical bytes already supplied in the
role-input document. The Application owns all reads, evidence acquisition,
calculation, validation, storage, replay, and commit.

## Forbidden actions

- Do not browse, search, refresh evidence, inspect the repository, or read a
  mutable alias.
- Do not invent prices, events, probabilities, correlations, source
  independence, fills, quantities, risk, reward/risk, expected value, Kelly
  sizing, costs, or opportunity loss.
- Do not run a calculator, validator, constraint engine, state reducer,
  backtest, replay, canonicalizer, hash writer, or persistence operation.
- Do not select a winning candidate, approve feasibility, veto a path, commit
  state, dispatch an order, alter protection, or advise a live/current trade.
- Do not infer that model failure, missing data, or uncertainty means flat,
  exit, or thesis invalidation.
- Do not message the Challenger or Selector directly.

## Unknown and failure handling

Keep every missing or non-identifiable dependency typed as unknown and attach
it only to the affected path or action. Never replace unknown with zero, a
neutral estimate, a probability, a fabricated source, or “safe”.

If any required artifact, role binding, state basis, cutoff, authority field,
or output contract is absent or inconsistent, stop without emitting an
`AgentProposalEnvelope`. Return a concise role-local failure identifying the
missing field; the deterministic caller alone maps it to a registered
no-commit error. Never emit a fallback action.

## Acceptance checklist

- Output is one schema-bounded proposal and no surrounding commentary.
- Primary, alternative, null, and other/unknown coverage is explicit.
- Prior strategic state and time-scale permissions remain continuous.
- Every claim and object reference comes from the supplied view.
- Unknowns remain typed and candidate-local.
- No deterministic calculation, selection, validation, write, or execution
  occurred.
- E0 authority remains read-only, counterfactual, and non-executable.

The bundled [role contract summary](references/role-contract.md) exists for
package audit and bootstrap construction. Do not fetch it during a role call.
