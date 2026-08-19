# Community skill screening

Verified on 2026-08-15. Install and star counts are popularity signals that drift; they
are not accuracy, safety, or profitability evidence. No third-party executable code or
instructions were vendored into this suite.

## Screened candidates

| Candidate | Observed support | Useful contribution | Import decision |
|---|---:|---|---|
| [Binance trading-signal](https://skills.sh/binance/binance-skills-hub/trading-signal) | 8.1K installs; [repository](https://github.com/binance/binance-skills-hub) 942 stars | Official venue example of discrete on-chain signal fields | Do not import. It treats address count as increased reliability without validation and is adjacent to credentialed execution skills. |
| [ECC llm-trading-agent-security](https://skills.sh/affaan-m/ecc/llm-trading-agent-security) | 5.9K installs; MIT | Prompt injection, simulation, independent limits, wallet isolation | Paraphrase only. Its examples sign/send transactions and hard-code universal spend/loss thresholds. |
| [Backtesting Trading Strategies](https://skills.sh/jeremylongshore/claude-code-plugins-plus-skills/backtesting-trading-strategies) | 4.1K installs; repository reported about 2.5K stars; MIT | Costs, walk-forward, metrics, and trade logs | Do not import. Default yfinance/grid-search flow lacks strict PIT, survivorship, revision, and multiple-testing controls and uses an arbitrary Sharpe target. |
| [TraderMonty position-sizer](https://skills.sh/tradermonty/claude-trading-skills/position-sizer) | 1.3K installs; MIT | Stop-distance arithmetic, floor-to-increment, concentration constraints | Do not import. It defaults to fixed 1%/2% rules, long stocks, and prescriptive portfolio heat. |
| [himself65 finance-skills](https://github.com/himself65/finance-skills) | 3.2K stars, 366 forks; MIT | Broad source routing, liquidity, valuation, read-only Hyperliquid adapter | Do not import wholesale. Several skills install dependencies, rely on yfinance or third-party APIs, or mix paid/provider-specific routes. |
| [OpenAI portfolio-risk-management registry snapshot](https://www.skills.sh/openai/role-specific-plugins/portfolio-risk-management) | 7 installs; parent repository 470 stars; MIT | Official source-resolution and exposure-review workflow | Do not import. The registry page existed, but the skill was absent from the audited current `main`; the snapshot also depended on parent-plugin context and connectors. |

Other high-install results included finance-news, stock-checker, margin/futures execution,
and Polymarket packages. They were not selected because this project needs source-grounded
cross-market reasoning without silently adding provider dependencies or execution authority.

Audited repository heads: Binance `2863a186d2bbd8987fa4790d7b81a299a58364ce`,
ECC `c9de8f5b2b3a225bca9befa2b7700aa5e3a4d1b8`, TraderMonty
`769a6c88b16ccdc3239a14fcbaf9ef2c44d183a8`, backtesting
`478aaf17731714fed9b1779284de6a5b3729ef6e`, himself65
`fe5608d2512a7d6a7b9821ce8a88c48464ecd6e4`, and OpenAI
`5bddb251b7dcd1507f96191a58b8fd4409086f00`.

## Reuse rule

Before adding any future community skill:

1. verify the exact repository, commit, license, maintainer, and current install count;
2. read every `SKILL.md`, executable script, dependency, dynamic prompt, and network endpoint;
3. reject default credentials, order placement, wallet signing, package installation, hidden
   prompts, fixed strategy answers, or unsupported performance claims;
4. pin the accepted bytes and preserve attribution if any substantial content is copied;
5. revalidate against current project authorization and trading-theory boundaries.
