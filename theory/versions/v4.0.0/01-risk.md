# V4.0 Risk Engine

Let `E` be current equity, `R_trade` the explicit maximum structural loss budget, `d_stop` the entry-to-structural-stop percentage, `s_stress` the stress buffer, and `C_exec` deterministic execution cost.

`N_raw = R_trade / d_stop`

`R_struct = N * d_stop`

`R_stress = N * (d_stop + s_stress) + C_exec`

`R_tail` is a separate severe-but-plausible loss scenario and must remain within the approved tail budget.

The chosen notional is the minimum of all applicable bounds: structural risk, stress risk, instrument/venue limits, portfolio concentration, liquidation buffer, and stressed executable liquidity. Leverage changes margin usage and liquidation distance; it does not redefine price-loss risk.

Risk tiers are functional guidance only until calibrated. The protocol does not impose a universal percentage of equity. A valid case must state the authorized budget or mark sizing `UNKNOWN/INSUFFICIENT`.

Structural, tactical, and catastrophic stops are separate concepts. A catastrophic boundary must never be substituted for a normal trade stop merely to manufacture a better reward/risk ratio.
