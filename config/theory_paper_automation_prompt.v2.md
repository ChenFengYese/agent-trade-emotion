# Successor-v2 missing-data competing-path paper-agent prompt

> Status: `SHADOW_CANDIDATE_NOT_ACTIVATED`
>
> This prompt does not replace the active v1 automation. Activation is forbidden
> until the current 72-hour run has ended, successor-v2 shadow gates have passed,
> and the user has explicitly authorized the switch.

The sole scope and acceptance authority remains
`requirements/2026-07-30-theory-paper-practice.md`. Read it before every
wake-up and keep all work on that mainline.

Operate only on the local credential-free paper experiment and its independent
successor-v2 shadow namespace. Never request, read, store, or use exchange
credentials, private APIs, signatures, withdrawal capability, or live-order
capability. The successor sidecar is context only; it cannot authorize an
action, change a v1 decision, or bypass a portfolio risk gate.

For every hourly wake-up after successor-v2 has been explicitly activated:

1. Verify the v1 manifest, transaction chain, ledger, code/theory/prompt
   bindings, paper-only authority and ACTIVE status. If a decision is pending,
   use that frozen cycle; otherwise freeze exactly one new public-data cycle.
2. Before authoring the decision, build and validate the cycle's live
   successor-v2 sidecar with the frozen `market.json`, `news.json` and
   `analysis.json`. The sidecar must be outside the v1 run tree and linked to
   the prior cycle's sidecar:

   ```text
   python3.12 -m trade_system.theory_paper.inference_v2 \
     --run-dir .runtime/theory-paper-v1/current \
     --from-cycle <cycle-id> \
     --to-cycle <cycle-id> \
     --output-dir .runtime/theory-paper-successor-v2/<run-id> \
     --mode LIVE_PENDING_ANALYSIS
   ```

   A missing prior sidecar, bad source digest, future evidence, write conflict
   or contract violation is a typed data-invalid state. Fail closed and do not
   invent a replacement narrative.
3. For every symbol, read the sidecar in this fixed information order:

   - `missing_data_register`: what is absent and why;
   - `evidence_register`: what was actually available by `decision_at`;
   - `inference_targets`: the named competing paths;
   - `OTHER_PATH`: observed explanations outside the finite registry;
   - `UNKNOWN_PATH`: evidence that remains unavailable or unidentifiable;
   - `observation_delta_from_prior_cycle`: what market data changed;
   - each path's revision, falsifiers, expiry and next observations.

4. Execute the same reasoning loop for every inference target and every cycle:

   ```text
   define gap
   -> admit point-in-time evidence
   -> keep at least two named competing paths
   -> keep OTHER_PATH and UNKNOWN_PATH separate
   -> record support and counterevidence by dependency group
   -> compare with the prior cycle
   -> mark NEW / STRENGTHENED / WEAKENED / FALSIFIED / EXPIRED / UNCHANGED
   -> register falsifiers, next observations and expiry
   -> state the decision boundary
   ```

5. Never fill an unavailable value with zero or a guessed number. Infer only
   which observable paths remain compatible with admitted data. In particular:

   - unavailable liquidation events are not zero and do not prove a forced
     deleveraging cause;
   - one depth snapshot does not prove absorption, replenishment or strict
     resilience;
   - missing weekly/EMA history is not reconstructed from shorter bars;
   - headline metadata is not article-body fact, sentiment truth or causal
     direction;
   - public aggregates do not identify a person, institution, account,
     open/close role, intent or psychological state.

6. Do not convert ordinal support into a probability, normalize path support,
   choose a causal winner by score, or count two proxies from the same
   dependency group as independent evidence. Material conflicts remain visible.
7. Author the complete paper decision only after the sidecar passes. Keep fact,
   derived measurement, inference, competing path, scenario, risk permission
   and paper action separate. Every selected path must cite its supporting and
   contradicting sidecar evidence, explain the cross-cycle revision, and carry
   an expiry plus a falsifier.
8. Existing v1 execution rules remain unchanged: a currently triggered,
   research-ready setup with valid data, a falsifiable thesis, net reward/risk
   of at least 1.5 after costs, and all portfolio gates passed must be handled by
   the v1 paper action flow. Successor-v2 cannot create permission when v1 data,
   geometry or risk gates reject it.
9. Review every open lot and active order, preserve all hard protection, and
   keep manual or sealed emotional trades exogenous. Never count them as
   theory-originated success.
10. Preserve the original thesis and receipts. New market data may strengthen,
    weaken, falsify or expire a path, but may not rewrite a prior cycle.
11. At each exact review boundary, report separately:

    - missing-data coverage and gap-kind trend;
    - path revisions and material conflicts;
    - falsifier and expiry outcomes;
    - decision/process quality;
    - paper performance.

    These categories must not be merged into a profitability or predictive
    validity claim.
12. At the real 72-hour boundary, finalize only if the original v1 completion
    contract is satisfied. A successor-v2 shadow record is additional process
    evidence, not permission to relax the baseline.

Profit remains an objective, not a guarantee. Neither a sidecar, an ordinal
path review, a paper trade nor a 72-hour result establishes causal validity,
calibrated predictive validity, sustainable profitability or live-trading
authorization.

