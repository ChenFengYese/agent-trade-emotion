# Local paper execution boundary

Read this only when the Agent chooses an actual local paper action or must manage an admitted order/position.

## Current useful surface

The repository can represent WAIT/WATCH/CONDITIONAL records, standalone MARKET, bilateral LIMIT, bounded marketable LIMIT, protected flat LIMIT entry, HOLD, CANCEL, REDUCE/LIMIT_REDUCE/CLOSE, protective stop, and targets. Confirm current code before relying on a less common action.

Known limits include no native protected STOP_ENTRY, no atomic multi-entry intent, no generic cancel-replace, and incomplete direction-symmetric protected ADD/REENTER. These are limits of the tool, not limits of the Agent's ideal decision.

State the ideal trading action first. Then:

1. map it to an existing tool only if the economics and timing remain faithful;
2. if no faithful mapping exists, record `UNSUPPORTED_ACTION_SPACE` rather than silently converting to WAIT;
3. change code only after a real, current trading decision is repeatedly or materially distorted by the missing capability.

## Observation and fills

Market analysis is state/event-driven. Mechanical execution observation is separate: while an order or position needs evidence, it may collect forward public quotes, visible size, trades, protection, fees and funding without asking the Agent to rethink the market every poll.

Only strictly later executable facts may create a paper fill. A later candle touching a limit does not prove queue order or a fill. If observation coverage is insufficient, use `MEASUREMENT_INSUFFICIENT/EXECUTION_EVIDENCE_GAP`; do not backfill the favorable result and do not claim a definite no-fill beyond the observed facts.

Local paper is not live trading. Never use private credentials, testnet/live endpoints, external orders, or funds without new explicit authorization.
