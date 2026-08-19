# Authoritative research-validation sources

Verified on 2026-08-15. Link to these works; do not reproduce copyrighted papers.

| Risk | Source | Practical implication |
|---|---|---|
| Backtest selection and overfitting | [Bailey et al., The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253) | Ordinary holdout methods can be unreliable after extensive strategy selection; preserve the candidate set and selection process. |
| Multiple-signal overfitting | [Novy-Marx, NBER Working Paper 21329](https://www.nber.org/papers/w21329) | Combining the best signals from many trials can create severe bias even with apparently strong in-sample statistics. |
| Point-in-time macro data | [ALFRED help](https://alfred.stlouisfed.org/help) and [FRED vintage dates](https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html) | Reconstruct values as they existed on the historical decision date. |
| Filing facts and timing | [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Bind facts to filing/accession/period/unit and public dissemination time; account for amendments. |
| Post-acceptance EDGAR corrections | [SEC Accessing EDGAR Data](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data) | Current indexes can incorporate later corrections or removals; preserve the historical information set. |
| COT history and classifications | [CFTC COT notes](https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm) | Weekly classifications and backcast history have limitations; avoid account-level or causal interpretations. |

## Minimum claim ladder

| Evidence | It may support | It does not by itself support |
|---|---|---|
| Local/synthetic PASS | Code or invariant behavior | Real data validity or returns |
| Historical backtest | Behavior under modeled history | Future edge, capacity, or live readiness |
| Locked out-of-sample | Less-selected historical evidence | Prospective robustness or profitability |
| Paper/shadow | Forward data/execution behavior in the simulator | Real fills, custody, or live permission |
| Prospective sealed study | Actual forward prediction/process evidence | Broad regime generalization |
| Authorized small live sample | Narrow realized operation and cost | Scaled profitability or production readiness |
