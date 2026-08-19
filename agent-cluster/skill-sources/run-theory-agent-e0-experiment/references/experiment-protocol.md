# Native Codex E0 experiment protocol

## Scope

- Evidence: `PRACTICAL_CODEX_CLUSTER_EXPERIMENT`
- Data: frozen BTCUSDT historical counterfactual contexts, indices 96–127
- Arms: `SINGLE_STRONG_NATIVE` and `CLUSTER_BLIND_NATIVE`
- Authority: `E0_OFFLINE_COUNTERFACTUAL`, `NONE_E0`, `executable=false`
- No custom model transport, automation, paper order, live order, or account
  connection

## Paired sample

Both arms receive the exact bytes from `contexts/NNN.json`.

The run manifest freezes the input transport. Under
`CLEAN_SINGLE_TURN_FORK_V1`, a controller turn contains the exact context bytes
and output schema; a fresh worker uses `fork_turns=1` and therefore receives
only that purpose-built transport turn, not earlier controller history. Worker
repository reads, tools, browsing, and evidence refresh remain forbidden.
Because the native fork is not byte-attested by the product, this transport is
valid only for `PRACTICAL_CODEX_CLUSTER_EXPERIMENT` evidence.

Single-Strong returns:

1. `PROPOSAL`
2. `SELF_REVIEW`
3. `SELECTION`

Cluster returns:

1. Proposer `PROPOSAL`
2. independent `CHALLENGE_BLIND`
3. Selector `SELECTION`

The blind Challenger must not see proposal bytes. Only the Selector sees both
cluster artifacts. Every non-selector must return `selected_action=null`.
Every Selector must return an exact ID from `feasible_actions`.

## Semantic object

Return only JSON matching `semantic-output.schema.json`. In particular:

- `schema_id`: `topology_semantic_payload`
- `schema_version`: `1.0.0`
- `output_kind`: the phase named above
- path fields: primary, alternatives, null, other/unknown
- `challenge_claims`: only evidence-grounded claims
- `selected_action`: null except in Selection
- `unknowns`: preserve missing or unidentified inputs

Do not add probabilities, prices, quantities, risk calculations, or evidence
that is absent from the context.

## Frozen evaluation

The state utility computes:

- four-slot path coverage;
- registered challenge-category coverage;
- exact feasible-action validity;
- their unweighted mean composite;
- one-hour post-decision counterfactual net PnL, transaction cost, and primary
  path capture.

Next-bar outcomes are unavailable to workers and enter only evaluation.
Cluster preference requires a higher mean composite and no more hard action
errors. A tie or unproven improvement resolves to
`INCONCLUSIVE_USE_SINGLE_AGENT`.

Economic replay is diagnostic. It is not predictive, causal, profitable, or
tradable evidence.
