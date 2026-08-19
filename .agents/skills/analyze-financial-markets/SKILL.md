---
name: analyze-financial-markets
description: >-
  Build source-grounded, point-in-time analysis of equities, rates, FX, commodities,
  futures, options, crypto, or cross-asset markets. Use for 市场分析, regime, catalysts,
  fundamentals, macro, technical structure, order flow, derivatives, sentiment, on-chain
  evidence, competitive hypotheses, forecasts, or a research-only LONG/SHORT/WAIT view.
---

# Analyze financial markets

Build a falsifiable market view from information actually available at the stated
decision time. Use analysis dimensions selectively; do not force a universal checklist.

## Establish the decision context

Resolve or explicitly assume:

- instrument identity, venue, contract type, quote/collateral currency, and session;
- as-of time, decision horizon, and the action or question the analysis must inform;
- current exposure and relevant legal actions, if supplied;
- data permissions and whether the task is descriptive, historical, paper, or prospective.

Fail closed on ambiguous instrument identity. Keep non-critical missing information
`UNKNOWN` and continue with the evidence that is valid.

## Choose discriminating evidence

Select only dimensions likely to separate the live hypotheses:

- price structure, returns, volatility, volume, and liquidity;
- order book or trade flow when a real sequence exists;
- futures curve, basis, funding, open interest, options surface, and positioning;
- issuer filings, earnings, balance sheet, valuation, and corporate actions;
- macro releases, rates, FX, cross-asset transmission, and event calendar;
- verified news, policy, on-chain state, or sentiment.

Read [references/authoritative-sources.md](references/authoritative-sources.md) when
choosing or interpreting a source. Prefer issuer, regulator, government, exchange, or
peer-reviewed material. Use community attention as a lead to verify, not as truth.

## Maintain an evidence ledger

For every decision-relevant statement, retain:

- `class`: `FACT / MEASURE / INFERENCE / HYPOTHESIS / FORECAST / POLICY / RISK`;
- source and instrument identity;
- `event_time`, `published_at`, `retrieved_at`, and conservative `available_at`;
- `ACTUAL / RECONSTRUCTED`, transformation, assumptions, and known gaps.

Require `available_at <= decision_at` for a prospective claim. Use data vintages for
revised macro series. Never substitute the latest corrected value for what was known then.

## Compete explanations

Create:

1. a leading mechanism/path;
2. the strongest plausible alternative;
3. an `OTHER` bucket for unresolved mechanisms.

For each, state supporting evidence, contradicting evidence, what would falsify it, and the
next observation that would change the ranking. If calibration is absent, use ordinal
ranking rather than probability percentages.

## Connect view to action

When the user requests a trading view, compare the legal actions rather than emitting a
signal from one indicator. Include `WAIT` only with its reason, opportunity cost, and next
review event. Distinguish:

- market direction from trade quality;
- thesis validity from entry quality;
- prediction from execution and position risk;
- an analytical target from an automatic exit.

Use `$plan-trade-execution` for order mechanics and
`$manage-trading-positions` for actual exposure.

## Report

Lead with:

1. as-of market state and evidence coverage;
2. leading hypothesis, runner-up, and material `UNKNOWN`;
3. path scenarios, catalysts, and invalidation;
4. the preferred research action plus the best alternative;
5. what evidence to obtain or review next.

Do not claim causality from correlation, completeness from coverage, or predictive edge
from a coherent narrative. A snapshot cannot prove resilience, open interest has no
directional identity by itself, missing liquidation data is not zero, and aggregated
position ratios do not reveal individual intent.
