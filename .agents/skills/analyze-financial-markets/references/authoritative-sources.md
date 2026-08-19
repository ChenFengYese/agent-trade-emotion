# Authoritative market-analysis sources

Verified on 2026-08-15. Recheck live documentation and release schedules when current data
matters.

## Source priority

1. Issuer filings, regulator/government releases, exchange specifications, and official
   market-data documentation.
2. Peer-reviewed or clearly identified working papers with methods and limitations.
3. Reputable data vendors and professional reporting, with primary-source confirmation.
4. Community analysis and social data as discovery or sentiment evidence only.

## Primary routes

| Need | Preferred source | Important limit |
|---|---|---|
| U.S. issuer filings and XBRL facts | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Preserve accession, filing time, amendments, units, periods, and custom-tag context. |
| Historical macro information set | [ALFRED help](https://alfred.stlouisfed.org/help) and [vintage dates API](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html) | Use the vintage available at the decision time; later revisions leak future information. |
| Federal Reserve events and releases | [Federal Reserve statistical release calendar](https://www.federalreserve.gov/data/releaseschedule.htm) | Calendar time is not the same as actual public availability; record retrieval time. |
| Futures positioning | [CFTC Commitments of Traders](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm) and [explanatory notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm) | Weekly, lagged, category-based, partly self-reported; it does not reveal individual reasons. |
| Equity order mechanics | [SEC Trading Basics](https://www.sec.gov/file/trading101basicspdf) | Order behavior and protection differ by venue, broker, session, and volatility. |
| Futures risk and position planning | [CME position and risk management](https://www.cmegroup.com/education/courses/things-to-know-before-trading-cme-futures/position-and-risk-management) | Educational guidance is not a universal risk percentage. |
| Hyperliquid public market schema | [Official info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) | Mids can fall back to last trade when the book is empty; identify remapped assets. |
| Hyperliquid funding | [Official funding documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) | Annualized funding is a rate projection, not guaranteed realized carry. |

## Evidence cautions

- Label delayed, revised, sampled, aggregated, self-reported, and reconstructed data.
- Preserve corporate actions, symbol changes, delistings, contract rolls, funding intervals,
  and quote/collateral differences.
- Treat headlines, analyst consensus, wallet tags, and “smart money” labels as claims whose
  construction and selection process must be checked.
- For order books, distinguish one snapshot from a sequenced book with gap detection and
  post-stress replenishment.
- Preserve raw captures and a hash only when the analysis must later prove what bytes were
  used; do not create hashes for presentation artifacts.
