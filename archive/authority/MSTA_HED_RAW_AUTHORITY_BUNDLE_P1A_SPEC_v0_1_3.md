# MSTA-HED P1A-R3 E0 Synthetic Genesis Admission Reference

**Status:** `DRAFT_AWAITING_SOL_P1A_R3_GATE`  
**Maximum claim:** `E0_SYNTHETIC_GENESIS_ADMISSION_REFERENCE_CLOSED`.

R3 initial draft did not pass its independent gate. R3.1 is an in-place repair
of this same draft only; it adds no P1B or data authority. The termination
rule is strict: after R3.1 verification this package stops at the stated draft
gate and requires a new Sol decision for any subsequent work.

R3 is deliberately smaller than a data adapter. It only accepts
`SYNTHETIC_CONTRACT`, `SUPPLIED_PAYLOAD_ONLY`, zero or one unique `INITIAL`
genesis record, the exact nine-field v0.5 `Evidence` carrier
(`evidence_id,available_at,perspective_id,dependency_group,target_ids,direction,ordinal_strength,quality,source_version`), closed synthetic
transform/coverage/tip authorities, and a module-pinned synthetic trust root.
It has no network, subprocess, environment, wall-clock, runtime filesystem,
source, market, outcome, download, backtest, calibration, holdout, paper/live
or deployment capability.

Zero-byte input with no records or authority/receipt/admission objects returns
`VALID_EMPTY_NOT_ADMITTED`, with receipt and admission both null. A nonempty
candidate can return `ADMITTED` only with one initial genesis record, nonempty
receipt/admission, `CLEAR` coverage, an authorized transform, authorized proof,
matching external-tip identity and a valid exact v0.5 Evidence binding.

The pinned trust root exists outside the candidate graph and is anchored by the
fixed R3 contract canonical digest in the pure reference module. Candidates
cannot supply or replace it. Decision, tip and record clocks are closed UTC-Z
timestamps; decision time must be within the pinned trust validity window.

R3 explicitly does **not** support multiple revisions, cursor history, receipt
prefix history, `UpdateReceipt`, `EvidenceLedgerReceipt`, production/real
cryptography, dynamic proof discovery, or a runtime adapter. Those are P1B-or-
later questions and are not authorized by this artifact.

The future market-path order remains `H01,H03,H05,H02,H04,H06,H08,H07`;
`V5-H09-LAYERED_ERROR_ATTRIBUTION` remains a quality guard outside that order.
No R3 synthetic result supports a market hypothesis or trading action.
