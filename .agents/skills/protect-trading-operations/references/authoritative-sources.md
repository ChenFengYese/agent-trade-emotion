# Authoritative trading-security sources

Verified on 2026-08-15. Recheck venue documentation before configuring credentials or
transactions.

| Control area | Source | Key use |
|---|---|---|
| Phishing-resistant authentication | [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) | Prefer cryptographic, verifier-bound authentication; manually entered OTP is not phishing-resistant. |
| Secrets lifecycle | [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) | Centralize storage, provisioning, auditing, rotation, and revocation; do not hard-code secrets. |
| API authorization and unsafe consumption | [OWASP API Security Top 10](https://owasp.org/API-Security/) | Check broken authentication/function authorization, rate limits, misconfiguration, inventory, and untrusted upstream APIs. |
| Financial-account hygiene | [FINRA cyber-safe accounts](https://www.finra.org/investors/insights/cyber-safe-financial-accounts) | Use MFA, unique credentials, alerts, trusted devices, verified sites, and activity review. |
| Exchange key scopes | [Binance Spot REST security types](https://developers.binance.com/en/docs/products/spot/rest-api) | Separate public, trade, and user-data permissions; keys are sensitive and trading is not enabled by default. |
| Hyperliquid API wallets and replay | [Official nonces and API wallets](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets) | Use separate API wallets/processes, unique nonces, expiry, and understand replay risk after pruning. |
| Hyperliquid impersonation and wallet safety | [Official support guide](https://hyperliquid.gitbook.io/hyperliquid-docs/support) | Verify official domains, reject DMs, and never share seed phrases or private keys. |
| Crypto platform, leverage, fraud, and cyber risk | [CFTC virtual-currency advisory](https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/understand_risks_of_virtual_currency.html) | Include platform safeguards, recourse, volatility, manipulation, phishing, and leverage. |

## Capability ladder

Treat each as a separate grant:

1. public read-only market data;
2. private read-only account data;
3. deterministic local calculation;
4. isolated local paper;
5. testnet;
6. live order create/cancel;
7. transfer/withdrawal/allowance/contract call;
8. persistent automation.

Grant only the narrowest required level, target, duration, and limits. Never inherit a higher
level from an adjacent capability.
