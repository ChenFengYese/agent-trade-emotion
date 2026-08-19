# Authoritative position and portfolio risk sources

Verified on 2026-08-15. Regulatory and institutional frameworks provide concepts, not a
universal personal risk budget.

| Topic | Source | Correct use |
|---|---|---|
| Asset allocation and diversification | [Investor.gov guide](https://www.investor.gov/additional-resources/general-resources/publications-research/info-sheets/beginners-guide-asset) | Check concentration across and within asset categories; diversification does not eliminate loss. |
| Futures sizing and stops | [CME position and risk management](https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/position-and-risk-management) | Size from account profile and loss scenarios, not broker maximum. |
| Margin account risk | [FINRA brokerage accounts](https://www.finra.org/investors/investing/investment-accounts/brokerage-accounts) | Include borrowing cost, margin calls, losses beyond deposit, and forced liquidation. |
| Options leverage and assignment | [FINRA options guide](https://www.finra.org/investors/insights/options-z-basics-greeks) and [OCC disclosure](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document) | Model obligations, nonlinear exposure, assignment, and margin by strategy. |
| Crypto and derivatives leverage | [CFTC virtual-currency risk advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html) | Leverage amplifies moves; platform, cyber, manipulation, and recourse risks remain. |
| Expected shortfall, basis risk, liquidity horizon | [Basel market-risk terminology](https://www.bis.org/basel_framework/chapter/MAR/10.htm?inforce=20230101&published=20200327&tldate=20550106) | Use definitions and stress concepts; do not present bank capital rules as a retail prescription. |
| Kelly growth criterion | [Kelly, 1956](https://onlinelibrary.wiley.com/doi/abs/10.1002/j.1538-7305.1956.tb03809.x) | Requires specified probabilities and payoffs; parameter uncertainty can make the theoretical optimum unsafe. |
| Hyperliquid margin | [Official margining documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining) | Compute cross/isolated and maintenance risk from current venue rules. |
| Hyperliquid liquidation | [Official liquidation documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations) | Liquidation price can change with funding, unrealized PnL, and other cross-margin positions. |

Keep VaR/expected shortfall, volatility, drawdown, scenario loss, and loss-to-invalidation
separate. Each answers a different question and depends on model and horizon assumptions.
