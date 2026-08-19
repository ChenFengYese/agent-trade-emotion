# Frozen E0B experiment protocol

## Paired comparison

Each sample uses identical frozen bytes for both arms: market measurements, counterfactual state, per-lot positions and stops, risk budget, action transition contracts, candidate calculations, path matrix, typed unknowns, supervision and action choice set.

- Single arm: one clean Agent identity produces proposal, self-review and selection.
- Cluster arm: a clean Proposer and blind clean Challenger reason independently; a clean Selector receives both frozen outputs plus the common context.
- Non-selectors set `selected_action=null` and `ranked_action_ids=[]`.
- Selectors rank every hard-feasible action exactly once and select the first ranked action.
- Singleton samples remain policy controls; neither arm may replace the only admissible action.

## Deterministic kernel versus Agent autonomy

The kernel owns PIT boundaries, state, supervision, action permissions, per-lot transitions, transaction costs, stop/gap loss, total and marginal risk, net reward-risk, break-even odds threshold, path arithmetic and outcome accounting. Funding and path probabilities remain typed UNKNOWN.

The Agent owns only competing-path interpretation, ordinal trade-offs and bounded selection among the supplied feasible actions. It must distinguish:

- strategic thesis from tactical risk action;
- CORE from TACTICAL exposure;
- existing-position management from a new trade at the current price;
- actual PnL from diagnostic opportunity loss;
- short execution evidence from strategic evidence;
- attended from unattended supervision;
- current action execution from a future review or reentry obligation.

No role may invent probability, EV, Kelly size, fill, trail order, reentry fill, or missing evidence.

## Financial and outcome contract

- Failure exits each post-action lot at its own registered stop, or a worse bar open on a gap, plus frozen costs.
- A newly armed trail is effective from the next bar; ambiguous same-bar target/return sequences remain UNKNOWN.
- Immediate realized, remaining unrealized, historical entry cost, current transaction cost, net account change, MAE and conservative peak-to-trough drawdown remain separate fields.
- Evaluation horizons are 1/4/8/24 hours. One-hour advantage cannot independently promote an arm.
- `WAIT_WITH_REVIEW` and `EXIT_WITH_REENTRY` are open-loop only after their one-hour deadline. A disagreement involving an overdue review-dependent action forces `INCONCLUSIVE_SEQUENTIAL_CONTRACT_NOT_PROVEN`.
- Opportunity loss is the algebraic mirror of the arm-relative net result and is diagnostic, not actual loss or an independent promotion gate.
- Overlapping windows are not iid samples; any outcome verdict is descriptive for this frozen source only.

## Response transport

Return one JSON object and no markdown. The complete canonical packet must be present in the clean child's initial message. The controller validates exact context/state digests, path slots, action assessments, selection axes, evidence IDs, role boundaries, ranking completeness, packet digest/length, task topology, run-wide task-ID uniqueness and Selector upstream binding.

Explicit role tool use or external-data use invalidates the case. Controller observation is not service-side sandbox attestation, so the practical evidence label remains mandatory.

## Stop conditions

Stop without advancing the checkpoint on context/source/packet mismatch, invalid schema, missing or conflicting output, role overreach, future-data exposure, selection outside the choice set, tool/external-data use, child failure, scheduler limit, event-chain mismatch or checkpoint mismatch. Never replace a frozen response with a better answer.
