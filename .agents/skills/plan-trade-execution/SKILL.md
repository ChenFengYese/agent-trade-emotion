---
name: plan-trade-execution
description: >-
  Turn a market thesis into a non-executable, venue-aware trade plan. Use for 市场交易,
  entries, exits, limit/market/stop orders, time-in-force, liquidity, spread, slippage,
  impact, fees, funding, borrow, protection, staged execution, cancel/replace, or checking
  whether an intended trade is operationally expressible.
---

# Plan trade execution

Translate the Agent's market decision into explicit mechanics without changing the thesis
or placing an order.

## Start from an owned decision

Require or state assumptions for:

- exact instrument, venue, side, desired exposure, and decision horizon;
- thesis, invalidation, entry logic, and why action is preferred now;
- current position and open orders;
- user-defined risk constraints and current authority level.

If no thesis exists, use `$analyze-financial-markets` first. If size is unresolved, use
`$manage-trading-positions`. Do not invent account values, broker support, leverage, or
permission.

## Verify the instrument contract

Check official venue or broker material for tick/lot size, multiplier, quote and collateral,
trading hours, settlement, expiry or funding interval, margin mode, liquidation mechanics,
fees, borrow, and supported order semantics. Read
[references/authoritative-sources.md](references/authoritative-sources.md) for primary
routes and known order risks.

Treat every unsupported field as `UNKNOWN`. A similarly named ticker on another venue is
not the same instrument.

## Compare execution routes

Compare only routes relevant to the intended action:

| Route | Main benefit | Main risk |
|---|---|---|
| No trade / watch | Avoids poor price or unsupported mechanics | Opportunity cost and stale thesis |
| Passive limit | Price control and possible maker economics | No fill, partial fill, queue uncertainty, adverse selection |
| Marketable limit | Bounded price with higher immediacy | Still can partially fill or expire |
| Market | Highest immediacy in ordinary conditions | Unbounded realized price within available liquidity |
| Stop | Conditional activation | Trigger is not guaranteed execution price; gaps can be large |
| Stop-limit | Trigger plus price bound | Can trigger and remain unfilled |
| Staged execution | Reduces timing and impact concentration | More decisions, fees, path risk, and incomplete exposure |
| Reduce-only exit | Limits accidental exposure growth | Venue semantics and race conditions still require verification |

Do not use one order type as a permanent policy. Choose from current liquidity, urgency,
adverse-selection risk, gap risk, and the cost of no fill.

## Price the friction

Estimate separately when observable:

- half/full spread and likely crossing;
- explicit maker/taker, clearing, exchange, broker, and network fees;
- slippage and market impact under normal and stressed depth;
- funding, borrow, roll, conversion, and collateral basis;
- partial-fill, cancel latency, and opportunity cost.

Label modeled values as estimates with assumptions. Do not treat recent average volume or
one order-book snapshot as guaranteed capacity.

## Build the plan

Specify:

1. action, side, target exposure, and current state;
2. entry condition or zone, order type, price bound, quantity, and time-in-force;
3. maximum tolerable spread/slippage and conditions that cancel the attempt;
4. protection logic, acknowledging gap and trigger risk;
5. management events for hold/add/reduce/partial-exit/full-exit/reentry;
6. order expiry, stale-thesis rule, and next review event;
7. expected and stressed all-in cost;
8. ideal action versus the closest currently supported tool mapping.

A target is a management event, not an automatic instruction to flatten. A zero fill is an
execution outcome, not proof the market view was wrong.

## Enforce the execution boundary

This skill produces a draft only. Before any external order, account read, credential use,
or fund effect:

- confirm current explicit authority for the exact mode and venue;
- invoke `$protect-trading-operations`;
- bind the final venue, instrument, side, size, prices, protection, time-in-force, account,
  and request expiry;
- stop if any material field or authorization is missing.

Never infer live authority from a public API, funded wallet, paper run, prior approval, or
value-zero canary.
