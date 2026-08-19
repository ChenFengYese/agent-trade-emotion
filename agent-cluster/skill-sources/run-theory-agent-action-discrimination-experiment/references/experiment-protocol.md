# Frozen E0A experiment protocol

## Paired comparison

Each sample uses identical frozen bytes for both arms: market measurements, counterfactual state, risk budget, candidate calculations, path matrix, typed unknowns, supervision and action choice set.

- Single arm: one clean Agent identity produces proposal, self-review and selection.
- Cluster arm: a clean Proposer and blind clean Challenger reason independently; a clean Selector receives both outputs and the common context.
- Non-selectors must set `selected_action` to null and `ranked_action_ids` to an empty list.
- Selectors rank every choice-set action exactly once and select the first ranked action.

Singleton samples remain in the experiment as policy controls. The Agent must still provide path and risk review, but cannot replace the kernel's only admissible action.

## Financial interpretation

The kernel, not an Agent, calculates marked gross, stop risk, transaction cost, marginal net reward-risk, break-even odds threshold, tail-gap loss and multi-path payoff. Break-even probability is an odds threshold, not a forecast. Funding and path probabilities remain UNKNOWN.

The Agent owns only path interpretation, ordinal trade-offs and selection among hard-feasible candidates. It must distinguish:

- thesis state from risk action;
- CORE from TACTICAL exposure;
- existing-position management from a new trade at the current price;
- actual PnL from opportunity loss;
- strategic time scale from tactical evidence;
- attended from unattended supervision.

## Response transport

Return one JSON object and no markdown. The controller validates exact context and state digests, all path slots, all action assessments, all selection axes, closed challenge categories, evidence IDs, role boundaries and ranking completeness.

Explicit role tool use or external-data use invalidates the case. When the collaboration surface cannot machine-attest tool absence, record the limitation and retain the practical evidence label; never promote it to strict transport-attested evidence.

## Stop conditions

Stop without advancing the checkpoint on context mismatch, invalid schema, missing output, role overreach, future-data exposure, selection outside the choice set, output conflict, event-chain mismatch or checkpoint mismatch. Do not replace an already frozen response with a better answer.
