"""Fail-closed, receipt-bound fresh-only scorer for the February diagnostic.

It never acquires data, fits models, calibrates, or trades.  It can score one
already-authorized, acquisition-verified input set exactly once.
"""
from __future__ import annotations

from pathlib import Path
from datetime import date
from types import SimpleNamespace
import tempfile
from typing import Any, Dict

from .historical_diagnostic_authorization import (
    HistoricalDiagnosticAuthorizationError,
    consume_fresh_scoring_authorization,
    finalize_consumed_scoring,
    register_ready_to_score,
    register_wait_data_not_scored,
    verify_acquisition_receipt,
    verify_authorized_execution_contract,
    verify_pre_download_authorization_receipt,
)
from .binance_cm_historical_diagnostic import FROZEN_BEFORE_DOWNLOAD, HistoricalDiagnosticPlan
from .historical_diagnostic_authorization import canonical_sha256, sha256_file
from .binance_cm_historical_mechanism import _load_day
from .historical_diagnostic_development import ThreeClassLogistic, _bootstrap, _coverage, _decision, _scores, build_day_rows
import json
import os


class HistoricalDiagnosticApplicationError(ValueError):
    pass


def _write_once_json(path: Path, value: Dict[str, Any]) -> str:
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        handle=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as exc: raise HistoricalDiagnosticApplicationError("application report is write-once") from exc
    with os.fdopen(handle,"w",encoding="utf-8") as stream:
        text=json.dumps(value,sort_keys=True,separators=(",",":"))+"\n"; stream.write(text); stream.flush(); os.fsync(stream.fileno())
    return sha256_file(path)


def _fresh_gate(coverage: Dict[str,Any], predictive: Dict[str,Any], bootstrap: Dict[str,Any], stress: float, plan: HistoricalDiagnosticPlan) -> Dict[str,Any]:
    g=plan.gate_policy
    if not coverage["effective_episodes"]: return {"decision":"STOP_DATA_INVALID","reason":"NO_EFFECTIVE_EPISODES"}
    if min(coverage["by_side"].get("BUY",0),coverage["by_side"].get("SELL",0)) < g["min_effective_per_side"] or coverage["effective_episodes"]<g["min_effective_episodes"] or coverage["utc_days"]<g["min_utc_days"] or min(coverage["by_state"].get(s,0) for s in ("THIN_BOOK","NORMAL_BOOK","DEEP_BOOK"))<g["min_effective_per_state"] or coverage["max_day_concentration"]>g["max_utc_day_concentration"] or coverage["max_state_concentration"]>g["max_state_concentration"] or coverage["max_direction_concentration"]>g["max_direction_concentration"]:
        return {"decision":"WAIT_DATA_COVERAGE","reason":"FRESH_COVERAGE_GATE_NOT_MET"}
    for side in ("BUY","SELL"):
        if side not in predictive: return {"decision":"WAIT_DATA_COVERAGE","reason":"EMPTY_DIRECTION"}
        c,k=predictive[side]["candidate"],predictive[side]["control"]
        if c["log_loss"]>k["log_loss"]*(1-g["relative_logloss_improvement_min"]) or c["multiclass_brier"]>k["multiclass_brier"]: return {"decision":"STOP_PREDICTIVE","side":side}
    if bootstrap.get("candidate_base_lower95") is None or bootstrap["candidate_base_lower95"]<=0 or bootstrap["incremental_lower95"]<=0 or stress<0:return {"decision":"STOP_ECONOMIC"}
    return {"decision":"E0-X_COMPLETE_DESCRIPTIVE","reason":"FRESH_SCORE_COMPLETE_NOT_G2"}


def _model_from_artifact(value: Dict[str, Any]) -> ThreeClassLogistic:
    try:
        scaler=value["scaler"]
        return ThreeClassLogistic(tuple(value["feature_names"]), list(scaler["means"]), list(scaler["scales"]), list(value["weights"]))
    except (KeyError, TypeError) as exc:
        raise HistoricalDiagnosticApplicationError("receipt-bound January model artifact is invalid") from exc


def _fresh_rows(plan: HistoricalDiagnosticPlan, acquisition: Dict[str, Any], workspace_root: Path) -> list[Dict[str, Any]]:
    """Parse only acquisition-bound ZIPs through the frozen row builder."""
    by_day={}
    for item in acquisition["inputs"]:
        by_day.setdefault(item["date"],{})[item["kind"]]=workspace_root/item["archive_path"]
    rows=[]
    with tempfile.TemporaryDirectory(prefix="fresh-score-") as temp:
        root=Path(temp)
        for text in plan.dates:
            files=by_day.get(text,{})
            if set(files)!={"aggTrades","bookDepth","metrics"}: raise HistoricalDiagnosticApplicationError("verified acquisition has incomplete day mapping")
            # Link exact receipt-bound archives/checksums into the parser's
            # flat, filename-bound interface; no download or mutation occurs.
            for kind, src in files.items():
                target=root/src.name; target.symlink_to(src)
                (root/(src.name+".CHECKSUM")).symlink_to(Path(str(src)+".CHECKSUM"))
            item=_load_day(SimpleNamespace(instrument=plan.instrument),root,date.fromisoformat(text))
            rows.extend(build_day_rows(item,plan))
    return sorted(rows,key=lambda r:(r["timing"]["decision_at"],r["side"]))


def verify_receipt_bound_application(*, plan_path: Path, contract_path: Path | None, receipt_path: Path | None, workspace_root: Path) -> Dict[str, Any]:
    """Return a non-executing readiness proof or reject missing authority.

    The caller has to provide both files explicitly; absence is a hard refusal,
    preventing a default path from being mistaken for approval.
    """
    if contract_path is None or receipt_path is None or not contract_path.is_file() or not receipt_path.is_file():
        raise HistoricalDiagnosticApplicationError("application refused: an explicit authorized contract and authorization receipt are both required")
    try:
        receipt = verify_pre_download_authorization_receipt(receipt_path, plan_path=plan_path, workspace_root=workspace_root)
        contract = verify_authorized_execution_contract(contract_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root)
    except HistoricalDiagnosticAuthorizationError as exc:
        raise HistoricalDiagnosticApplicationError("application refused: receipt-bound authority verification failed: %s" % exc) from exc
    return {"record_type":"historical_diagnostic_application_readiness.v1","status":"AUTHORIZED_NOT_EXECUTED","contract_id":contract["contract_id"],"receipt_id":receipt["receipt_id"],"fresh_inputs_read":False,"fresh_scoring_run":False,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}


def execute_authorized_fresh_diagnostic(*, plan_path: Path, contract_path: Path, receipt_path: Path, acquisition_path: Path, registry_path: Path, workspace_root: Path, report_path: Path, scoring_attempt_id: str) -> Dict[str, Any]:
    """Receipt-bound fresh-score handoff; it never fits a February model.

    Acquisition integrity is checked before model loading.  A complete input
    transitions atomically READY_TO_SCORE -> CONSUMED_SCORING_STARTED.  This
    intentionally stops at a write-once *scoring handoff* until the receipt's
    exact scorer package is supplied; no market order capability exists here.
    """
    if report_path.exists(): raise HistoricalDiagnosticApplicationError("application report is write-once")
    try:
        plan = HistoricalDiagnosticPlan.load(plan_path)
        if plan.status != FROZEN_BEFORE_DOWNLOAD:
            raise HistoricalDiagnosticApplicationError("authorized fresh application requires the February score-only plan")
        receipt = verify_pre_download_authorization_receipt(receipt_path, plan_path=plan_path, workspace_root=workspace_root)
        verify_authorized_execution_contract(contract_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root)
        # Cache the receipt identity, scope, and model binding before consuming
        # the one-shot authorization.  The post-consume failure path must be
        # able to seal the consumed registry state even if later file reads
        # fail (including an artifact being removed between consume and load).
        receipt_doc = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_id = receipt["receipt_id"]
        receipt_scope_sha256 = receipt_doc["receipt_scope_sha256"]
        january = receipt_doc.get("january_v2_development_evidence", {})
        model_binding = january.get("model")
        # This validates all 84 archives/checksums/coverage/gaps before any
        # policy/model receipt is opened.
        try:
            acquisition = verify_acquisition_receipt(acquisition_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root)
            acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
        except HistoricalDiagnosticAuthorizationError as quality_error:
            summary = canonical_sha256({"plan":sha256_file(plan_path),"acquisition_path":str(acquisition_path),"receipt":receipt_id,"mode":"FRESH_SCORE_ONLY","quality":"INCOMPLETE_OR_INVALID"})
            wait = register_wait_data_not_scored(registry_path, receipt_id=receipt_id, receipt_scope_sha256=receipt_scope_sha256, summary_sha256=summary)
            report={"record_type":"authorized_fresh_diagnostic_handoff.v1","status":"WAIT_DATA_NOT_SCORED","reason":"INPUT_QUALITY_FAILED_BEFORE_MODEL_LOAD","authorization":wait,"fresh_inputs_scored":False,"model_loaded":False,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
            report["report_canonical_sha256"]=canonical_sha256(report); _write_once_json(report_path,report)
            return report
        summary = canonical_sha256({"plan":sha256_file(plan_path),"acquisition":sha256_file(acquisition_path),"receipt":receipt_id,"mode":"FRESH_SCORE_ONLY"})
        register_ready_to_score(registry_path, acquisition_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root, summary_sha256=summary)
        consumed = consume_fresh_scoring_authorization(registry_path, acquisition_path, receipt_path, plan_path=plan_path, workspace_root=workspace_root, summary_sha256=summary, scoring_attempt_id=scoring_attempt_id)
    except HistoricalDiagnosticAuthorizationError as exc:
        raise HistoricalDiagnosticApplicationError("fresh application refused before model load: %s" % exc) from exc
    try:
      if not isinstance(model_binding, dict): raise HistoricalDiagnosticApplicationError("consumed authorization lacks receipt-bound January model binding")
      model_path=workspace_root / model_binding.get("path", "")
      if not model_path.is_file() or model_binding.get("sha256") != sha256_file(model_path): raise HistoricalDiagnosticApplicationError("receipt-bound January model digest drifted")
      model_doc=json.loads(model_path.read_text(encoding="utf-8")); models=model_doc.get("models",{})
      if set(models) != {"BUY","SELL"}: raise HistoricalDiagnosticApplicationError("January model must contain fixed BUY and SELL models")
    # Consumption is intentionally adjacent to first model load. From this
    # point no retry can occur, even if parsing/scoring raises an error.
      rows=_fresh_rows(plan, acquisition, workspace_root); by_side={}; all_candidate=[]; all_control=[]
      for side in ("BUY","SELL"):
        candidate=_model_from_artifact(models[side]["candidate"]); control=_model_from_artifact(models[side]["control"])
        timeout=float(models[side]["timeout_payoff_bps_fit_only"])
        subset=[r for r in rows if r["side"]==side]
        candidate_score=_scores(subset,candidate,timeout,10,candidate=True); control_score=_scores(subset,control,timeout,10,candidate=False)
        by_side[side]={"candidate":candidate_score,"control":control_score,"bootstrap":_bootstrap(subset,candidate,control,timeout,timeout,20260723)}
        all_candidate.append(candidate_score); all_control.append(control_score)
      coverage=_coverage(rows)
      bases=[x["bootstrap"]["candidate_base_lower95"] for x in by_side.values() if x["bootstrap"]["candidate_base_lower95"] is not None]; increments=[x["bootstrap"]["incremental_lower95"] for x in by_side.values() if x["bootstrap"]["incremental_lower95"] is not None]
      bootstrap={"candidate_base_lower95":min(bases) if bases else None,"incremental_lower95":min(increments) if increments else None}
      stress=sum(x["selected_stress_utility_bps"] for x in all_candidate)/max(1,sum(x["selected_count"] for x in all_candidate))
      gate=_fresh_gate(coverage,by_side,bootstrap,stress,plan)
      status="INCONCLUSIVE_CONSUMED" if gate["decision"]=="WAIT_DATA_COVERAGE" else "STOP_CURRENT_V2_PROXY" if gate["decision"].startswith("STOP_") else "E0-X_COMPLETE_DESCRIPTIVE"
      tab={}
      for r in rows:
        tab.setdefault(r["side"],{}).setdefault(r["state_id"],{}).setdefault(r["label"]["outcome"],0)
        tab[r["side"]][r["state_id"]][r["label"]["outcome"]] += 1
      report={"record_type":"authorized_fresh_diagnostic_report.v1","status":status,"plan_canonical_sha256":plan.canonical_digest,"receipt_id":receipt_id,"acquisition":acquisition,"authorization":consumed,"january_model":model_binding,"fresh_mode":"FRESH_SCORE_ONLY","model_fit_performed":False,"calibration_fit_performed":False,"fresh_inputs_scored":True,"rows":len(rows),"coverage":coverage,"side_state_outcome":tab,"cohort":"ALL_EXTREMES_SHARED","evaluation_by_side":by_side,"gate":gate,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}
      report["report_canonical_sha256"]=canonical_sha256(report); digest=_write_once_json(report_path,report); finalize_consumed_scoring(registry_path,receipt_id=receipt_id,receipt_scope_sha256=receipt_scope_sha256,status="SCORING_COMPLETE",report_sha256=digest); return report
    except Exception as exc:
      failure={"record_type":"authorized_fresh_diagnostic_report.v1","status":"SCORING_FAILED_CONSUMED","reason_code":"POST_CONSUME_%s" % type(exc).__name__.upper(),"receipt_id":receipt_id,"fresh_inputs_scored":False,"model_fit_performed":False,"eligible_for_binance_g2":False,"trading_authorization":"DENIED"}; failure["report_canonical_sha256"]=canonical_sha256(failure); digest=_write_once_json(report_path,failure); finalize_consumed_scoring(registry_path,receipt_id=receipt_id,receipt_scope_sha256=receipt_scope_sha256,status="SCORING_FAILED_CONSUMED",report_sha256=digest); raise HistoricalDiagnosticApplicationError("consumed scoring failed; immutable failure report written") from exc
