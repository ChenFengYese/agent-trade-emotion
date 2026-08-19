# V4.0 Opportunity, Path and EV

PR is geometry. For each target:

`RawPR = reward_distance / risk_distance`

Path-adjusted opportunity discounts obstacles between entry and target. If barrier-clearance probabilities are available, a path factor may be modeled as a product of conditional probabilities; otherwise use an ordinal path-quality label and retain the uncertainty.

Scenario value is:

`EV_net = Σ P(path_i) × NetPnL(path_i)`

`NetPnL = GrossPnL - fees - funding/borrow - slippage - impact - delay/execution penalties`

Compare `TRADE`, `CONDITIONAL`, and `WAIT` when the future setup has meaningful option value. A Probe is justified only when the information value of limited exposure can be plausibly greater than its bounded loss; it is not a disguised low-confidence Main.

Position quality decays when remaining opportunity, path accessibility, or execution quality deteriorates even if the original thesis remains valid.
