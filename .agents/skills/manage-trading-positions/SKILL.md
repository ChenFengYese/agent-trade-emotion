---
name: manage-trading-positions
description: >-
  Assess and manage single-position or portfolio exposure using explicit user constraints.
  Use for 仓位管理, position sizing, leverage, liquidation buffer, concentration, correlated
  exposure, portfolio heat, drawdown, stress tests, Kelly/volatility sizing, adding,
  trimming, taking profit, holding, exiting, re-entering, or managing an open trade.
---

# Manage trading positions

Turn current account facts and thesis state into transparent exposure choices. Never replace
unknown user risk tolerance with a universal percentage.

## Reconstruct actual state

Obtain or label `UNKNOWN`:

- venue/account mode, instrument, side, quantity, multiplier, entry, mark, and timestamp;
- open and conditional orders, stops, targets, and reduce-only status;
- cash/collateral, equity, margin used, maintenance requirement, and liquidation inputs;
- realized/unrealized PnL, fees, funding, borrow, and conversion effects;
- other positions, sector/factor/currency exposures, and relevant correlations;
- thesis, invalidation, catalyst, horizon, and current review event.

Separate paper facts from live facts and broker estimates from exchange facts. Do not read a
private account without explicit authority.

## Re-evaluate the thesis

Compare current evidence with the original thesis without rewriting the original decision.
Ask whether the mechanism strengthened, weakened, changed horizon, or failed. Distinguish:

- favorable price from correct mechanism;
- adverse price from thesis invalidation;
- execution error from market error;
- a temporary drawdown from an intolerable loss under the user's constraint.

## Calculate exposure and loss paths

Use instrument-aware arithmetic:

```text
notional = abs(quantity * current_price * contract_multiplier)
loss_to_level = abs(quantity * (current_price - adverse_level) * contract_multiplier)
                + estimated_exit_friction
portfolio_heat = sum(loss_to_each_position_invalidation) / current_equity
```

For nonlinear products, use scenario repricing and Greeks rather than linear arithmetic.
For cross margin, compute risk from the full account state. Retrieve liquidation formulas
from the exact venue; never estimate a generic liquidation price as authoritative.

Stress at least the risks that can dominate the stated horizon: gap, volatility expansion,
liquidity loss, correlation convergence, funding/borrow shock, basis/oracle divergence,
assignment, and collateral drawdown.

## Size from explicit constraints

Apply the strictest relevant bound:

- loss budget to a meaningful invalidation or stress level;
- maximum notional/leverage/margin and liquidation buffer;
- single-name, sector, factor, currency, venue, and counterparty concentration;
- liquidity and stressed exit capacity;
- borrow, funding, option assignment, and collateral constraints.

For a linear stop-distance scenario:

```text
maximum_units = floor_to_venue_increment(
  (explicit_loss_budget - estimated_friction) / loss_per_unit_to_invalidation
)
```

Never round up. Do not default to 1%, 2%, 6-8% portfolio heat, fixed ATR multiples, or a
fixed stop. Use those only as user-requested scenarios.

Use Kelly sizing only when win probabilities and payoff distributions are calibrated,
out-of-sample, sufficiently stable, and net of costs. Otherwise mark Kelly sizing
`MEASUREMENT_INSUFFICIENT`; if requested, show a sensitivity range rather than a
prescription.

## Compare legal actions

Compare the actions that fit the current state:

- `HOLD`: what evidence still supports keeping full risk;
- `ADD`: what new evidence justifies more risk and how concentration changes;
- `REDUCE / PARTIAL_TAKE_PROFIT`: how each size changes downside, upside, and reentry;
- `EXIT`: whether the thesis, risk budget, or execution premise failed;
- `REENTER`: what state must recur and what was learned from the prior exit;
- `WAIT`: reason, opportunity cost, and next decision event;
- `OTHER`: hedge, roll, restructure, or unsupported action, when genuinely relevant.

Do not silently delete an action to make a legacy tool fit. State the ideal action first,
then map to current capabilities.

## Report

Show current exposure and evidence timestamp, loss paths, binding constraints, action
comparison, preferred action, strongest alternative, invalidation, and next review event.
Read [references/authoritative-sources.md](references/authoritative-sources.md) when using
diversification, margin, expected shortfall, options, futures, or Kelly concepts.
