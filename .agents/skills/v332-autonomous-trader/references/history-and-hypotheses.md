# History and hypotheses

## Hypothesis ownership

A market hypothesis persists until the Trading Agent decides otherwise. Separate it from time-bounded objects:

- forecast path or expected sequence;
- observation/sample horizon;
- order validity and expiry;
- position episode and its risk boundary.

When a path fails to appear by its horizon, record that fact. The Agent may keep the mechanism with a different path, weaken it, suspend it, merge it with another hypothesis, replace it, retire it, or later revive it. No runtime state or clock performs this decision.

Original hypotheses are never rewritten. New judgments append or reference the earlier source so the evolution remains understandable.

## Complete history, optional retrieval

Preserve the complete original Agent analysis, Decision, Hypothesis, Outcome, Review, and paper facts in their existing source:

- a formal run: its cycle artifacts and ledger;
- a no-run analysis: the Codex task/report that produced it;
- a user-supplied report: the original attachment or file.

Do not replace originals with summaries. A compact index or artifact reference may help discovery, but it is non-authoritative and may be rebuilt.

Do not inject all prior text into each decision. Start with the current market, current order/position obligations, and explicit user context. Retrieve a prior source only when the Agent judges it relevant—for example to test recurrence, inspect a contradiction, manage an active episode, or review a candidate lesson.

For a local run, locate sources without creating a new memory service:

```sh
rg --files <run-root>/cycles | rg '/artifacts/(HypothesisRecord|BehaviorPlan|Outcome|Review)\.json$'
rg -n '<hypothesis-id|cycle-id|topic>' <run-root>/cycles
```

Read the exact source artifact after selecting it. Do not bulk-load every prior Decision/Review merely because it exists.

## Learning

A Review may propose a learning candidate, not a permanent policy. Record its evidence, likely scope, plausible counterexample, and what future observation could strengthen or reject it. Later Agent decisions may adopt, modify, ignore, or contradict it.

Never promote one sample into a default such as “do not chase”, “always wait for pullback”, fixed `PROBE`, fixed size, or fixed risk. Reuse is legitimate only after a fresh current-state judgment.
