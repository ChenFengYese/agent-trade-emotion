---
name: v340-strategic-trader
description: Use the V3.4.0 scheduled low-frequency strategic Trading Agent workflow for public PIT market research. The LLM receives new market-decision authority only at fixed 4H UTC committee slots; FORECAST_ONLY is currently implemented and non-executable.
---

# V3.4.0 Scheduled Strategic Trader

Act as a fixed-schedule strategic market decision owner, not a continuous market poller. Read `requirements/CURRENT.md` and `theory/CURRENT.md`; use the V3.4 overlay plus only the relevant frozen V3.3.2 base owner when needed.

## Time authority

- External scheduler is authoritative: UTC `00:00 / 04:00 / 08:00 / 12:00 / 16:00 / 20:00`.
- 4H is the minimum LLM market-decision horizon; 1D+ defines regime/higher strategy.
- 1H/15m/5m/tick are evidence resolution inside the current 4H window, not independent decision horizons.
- A 1H/15m break cannot itself wake the LLM, create a new thesis, reverse a position or perform an ordinary full CORE exit.
- Do not propose an earlier wake. “Check again in 30 minutes” has no scheduling authority.

At a committee, read the internal lower-timeframe path to explain what happened inside the 4H state. After sealing the committee result, stop market reasoning until the next fixed slot.

## Current Stage A: FORECAST_ONLY

Current V3.4 has no paper authority. At each committee, use the bounded context to maintain one durable strategic state and freeze 4H/12H/24H paths. Resolve:

1. 4H+ horizon, regime and trend phase;
2. 15m/1H/4H/1D zones and the evidential meaning of each break;
3. causal thesis, strong alternative and at least two IF→THEN paths;
4. participant/cost/constraint hypotheses, catalyst/news, sentiment/positioning, data quality and conflicts;
5. future-space, right-tail/left-tail and acceleration/cascade candidates;
6. next discriminating observation at the next legitimate decision horizon;
7. state change: `INITIALIZE/KEEP/STRENGTHEN/WEAKEN/INVALIDATE/REPLACE`.

Do not trade in FORECAST_ONLY. Do not infer missing participant identity or hidden intent as fact; preserve `UNKNOWN` and competing mechanisms.

## Future position stages

Only after Stage A qualifies may a fresh version/cohort implement `FROZEN_PLAN`, and only after that qualifies may it implement `DYNAMIC_MANAGEMENT`.

Before future new/increased exposure, strategic semantics must additionally cover realized/unrealized PnL, WAIT/HOLD/ADD/REDUCE/HARVEST/EXIT comparison, strategic invalidation, catastrophic protection, quantity, primary/right-tail targets, conditional tranche/runner plan, cost/gap/impact stress, maximum-loss budget and risk of waiting to the next 4H committee.

Between committees, the LLM has no position-change authority. A future local executor may mechanically execute only conditions explicitly frozen by the last committee; a safety system may only emergency `HALT/CANCEL/REDUCE/EXIT`. Dynamic management therefore means pre-authorized staircase execution, not repeated lower-timeframe LLM re-analysis.

If a future position cannot safely wait until the next 4H committee, the position geometry/size is invalid for V3.4; do not solve that by shortening the LLM horizon.

## Context and token discipline

Use only `latest StrategicState + current 4H asset delta + shared market summary + portfolio summary + immutable refs`. Do not paste full history, full theory or prior Agent conversations into every committee. The current deterministic context ceiling is 64 KiB; actual token usage must later be measured from provider usage rather than guessed from bytes.

Post-V3.4 multi-model routing/Manager Agent design is explicitly inactive in this version. Do not spawn Agent-to-Agent dialogue or model hierarchies while producing V3.4 evidence.

## Evidence boundary

Keep V3.3.2 r3/E-025 immutable and separate. Engineering PASS proves only contracts. Market skill, edge and profitability remain `UNKNOWN` until new strict PIT Stage-A evidence exists.
