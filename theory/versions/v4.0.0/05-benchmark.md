# V4.0 Benchmark and Scoring

Stage 4 is a decision-architecture benchmark, not a strategy backtest.

Hard failures include: PIT leakage; risk-budget violation; moving a structural stop to manufacture RR; averaging down because of loss; using positioning/crowding as a standalone reversal signal; using PR as a standalone signal; treating no-fill as a fill; ignoring known execution failure; or continuing a position solely because the old thesis has not fully failed.

Recommended score dimensions: PIT/information integrity 10%; market state 10%; hypothesis update 10%; structural reasoning 10%; risk engine 15%; PR/path 10%; EV/scenario logic 10%; position architecture 10%; management 7.5%; execution 5%; attribution/audit 2.5%.

The score never overrides hard failures. Evaluate by regime and by adversarial mutation. Repeatability should require stable core risk boundaries under identical evidence. Mutation tests should produce directionally sensible decision changes when one discriminating variable changes.
