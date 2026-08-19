# Current Theory

## V4.0.0 — Decision & Trading Specification

V4.0.0 is the current methodology baseline for the analysis → non-executable trading-plan transition. It supersedes V3.4 as the decision-architecture specification while preserving V3.4 forecast runtime as historical/forecast-only infrastructure.

### Core chain

`PIT Evidence → State → Hypotheses → Evidence Update → Structure → Risk → Opportunity/Path → Execution → Position → Management → Exit/Re-entry → Audit`

### Current hard requirements

- Risk is defined in account-loss terms; notional and leverage are separate.
- Structural stop precedes sizing; stress and tail loss bound the final notional.
- PR is opportunity geometry/path efficiency, never a standalone signal.
- EV is cost-aware and may use ordinal/banded probabilities until calibration exists.
- Exposure increases require a new evidence event.
- Position quality can decay while thesis remains valid.
- Limit no-fill/partial-fill is an execution outcome, not a market-thesis failure.
- Canonical, adversarial, repeatability/mutation, and OOS evaluation are separate benchmark layers.

### Trading-stage boundary

The project now contains a V4 non-executable decision layer at `trade_system/v4_decision/`. It can calculate risk-based notional, stress loss, scenario net EV, and validate a trade plan. It cannot read private accounts, use credentials, submit orders, or move funds.

The next research stage is analysis → trade-plan evaluation under PIT public data. Paper/testnet/live authority remains a separate explicit authorization boundary.
