# Authoritative execution sources

Verified on 2026-08-15. Consult the exact current venue/broker specification before relying
on an order type or fee.

| Topic | Primary source | Use |
|---|---|---|
| Equity market, limit, stop, and stop-limit basics | [SEC Trading Basics](https://www.sec.gov/file/trading101basicspdf) | Distinguish price control, immediacy, triggers, and non-execution. |
| Volatile-market stop risks | [FINRA stop-order guidance](https://www.finra.org/investors/insights/stop-orders-factors-consider-during-volatile-markets) | A stop price is not a guaranteed execution price. |
| Futures position and exchange risk | [CME position and risk management](https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/position-and-risk-management) | Size from risk scenarios, not maximum broker margin. |
| Cash versus margin accounts | [FINRA brokerage accounts](https://www.finra.org/investors/investing/investment-accounts/brokerage-accounts) | Margin can create losses beyond deposited cash and forced liquidation. |
| Options contract and assignment risk | [OCC Characteristics and Risks of Standardized Options](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document) | Read the current disclosure before options planning. |
| Hyperliquid contract identity | [Official contract specifications](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications) | Confirm linear/quanto details, collateral, multiplier, leverage, and limits. |
| Hyperliquid funding | [Official funding documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) | Funding is hourly and path-dependent; annualized screens are not guaranteed carry. |
| Hyperliquid liquidation | [Official liquidation documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations) | Cross-margin equity, funding, and other positions can change effective liquidation risk. |
| Hyperliquid fees | [Official fee documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees) | Retrieve the applicable current tier; do not hard-code a stale fee. |

For every venue, distinguish documented semantics from observed behavior. Broker-side
triggers, session rules, queue priority, maintenance, circuit breakers, and outages can
change the realized outcome.
