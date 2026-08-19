---
name: validate-trading-research
description: >-
  Determine whether a trading backtest, factor, signal, model, paper result, or performance
  claim is trustworthy enough for its stated decision. Use for 回测, walk-forward,
  out-of-sample, overfitting, data leakage, survivorship bias, revised data, execution
  assumptions, transaction costs, multiple testing, Sharpe/drawdown metrics, or comparing
  historical, paper, prospective, and live evidence.
---

# Validate trading research

Audit the claim actually made. Do not turn a historical simulation into predictive,
profitability, production, or trading-permission evidence.

## Classify the evidence stage

Label the strongest demonstrated stage:

1. theory or calculation;
2. synthetic/local test;
3. in-sample historical description;
4. historical backtest;
5. locked out-of-sample or walk-forward;
6. paper/shadow with forward-only observations;
7. prospective real-time evidence;
8. authorized live evidence.

Do not skip stages in the report. A later stage can still be invalid if identity, chronology,
cost, or account facts are wrong.

## Freeze before evaluation

Record the candidate's data universe, rules, features, parameters, decision times, action
mapping, costs, benchmark, metrics, and stopping rule before inspecting the holdout or future
outcome. Produce the baseline result before modifying the theory or scoring rule.

If the user asks for document-only review, do not run experiments or tests.

## Audit data chronology

Verify:

- exact instrument/venue identity, symbol history, delistings, and universe membership;
- raw source, license, retrieval time, checksum where needed, and transformation lineage;
- event time versus conservative `available_at`;
- macro vintages, filing publication/amendment times, corporate actions, and restatements;
- bar closure, timezone, session, contract rolls, quote currency, and missing intervals;
- label horizons and feature windows that do not cross the decision boundary.

Treat an unprovable PIT boundary, wrong identity, or future leakage as invalidating, not as a
small caveat. Read
[references/authoritative-sources.md](references/authoritative-sources.md) for primary
vintage and overfitting references.

## Audit execution realism

Reconstruct when an order could first exist and fill. Include instrument-relevant:

- next-tradable price, spread, slippage, market impact, partial fill, queue, and volume;
- maker/taker, broker, clearing, exchange, network, and tax assumptions;
- borrow availability/rate, funding, roll, dividends, splits, assignment, and collateral;
- latency, session, trigger, gap, liquidation, and stale-order behavior.

Do not fill from the same price observation that generated the decision unless the market
mechanism proves that sequence.

## Audit model selection

- Split chronologically; keep the final holdout untouched until the rule is frozen.
- Fit scalers, features, thresholds, and hyperparameters inside each training window.
- Purge or embargo overlapping labels when information spans split boundaries.
- Track every tried feature, rule, universe, parameter, metric, and stopping decision.
- Correct interpretation for multiple testing and selection. Treat best-of-grid output as
  selected performance, not an unbiased estimate.
- Require enough independent events and regimes for the stated horizon.

Use the probability of backtest overfitting or related methods only when their assumptions
fit; do not use one statistic as a universal pass/fail gate.

## Challenge with controls

Compare against the smallest meaningful set:

- cash/no-trade and buy-and-hold or a relevant passive benchmark;
- a simple strategy using the same data and execution engine;
- identical splits, costs, universe, and capital constraints;
- parameter, start-date, cost, liquidity, and regime sensitivity;
- placebo or randomized controls matched on turnover/exposure when useful.

Inspect return concentration, drawdown path, tail loss, turnover, capacity, and dependency
on a few assets or events. Do not optimize the benchmark after seeing results.

## Issue the verdict

Use one of:

- `VALID_FOR_STATED_CLAIM`;
- `PARTIAL / MEASUREMENT_INSUFFICIENT`;
- `INVALID`;
- `UNKNOWN_NOT_EVALUATED`.

State the claim allowed, the strongest evidence, invalidating failures, material limitations,
and exactly one next evidence step. Report net-of-cost results alongside gross, sample and
regime coverage, all tried variants, and untouched-holdout status.
