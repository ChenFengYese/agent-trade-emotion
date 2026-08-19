"""January-only development pipeline for the frozen COIN-M v2 contract.

This is deliberately a diagnostic artifact builder, not a backtest-to-trading
bridge.  It reads only the already-seen January archive set and writes new
files once.  February is not an input accepted by this module.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from .binance_cm_historical_diagnostic import BarrierTrade, HistoricalDiagnosticError, HistoricalDiagnosticPlan, canonical_sha256, label_barrier_path, select_positive_ev
from .binance_cm_historical_mechanism import _DayInput, _load_day
from .historical_evidence_ledger import sha256_file, verify_historical_evidence_ledger


OUTCOMES = ("TP", "SL", "TIMEOUT")
UTC = timezone.utc


class HistoricalDevelopmentError(ValueError):
    pass


def _write_once(path: Path, content: str) -> None:
    if path.exists():
        raise HistoricalDevelopmentError("refusing to overwrite immutable development artifact: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _rebind_january_input_audit(plan: HistoricalDiagnosticPlan, workspace_root: Path) -> List[Dict[str, Any]]:
    """Rehash all 84 already-seen inputs recorded by the bounded v1 report."""
    ledger = json.loads((workspace_root / plan.raw["evidence_ledger"]).read_text(encoding="utf-8"))
    report_path = workspace_root / ledger["report"]["path"]
    audit = json.loads(report_path.read_text(encoding="utf-8"))["input_audit"]
    result=[]
    for day in plan.dates:
        day_audit=audit.get(day)
        if not isinstance(day_audit,dict) or set(day_audit) != {"aggTrades","bookDepth","metrics"}:
            raise HistoricalDevelopmentError("v1 report lacks complete input audit for %s" % day)
        bound={}
        for kind,item in day_audit.items():
            archive=workspace_root/item["path"]; checksum=workspace_root/item["checksum_path"]
            if sha256_file(archive)!=item["archive_sha256"] or sha256_file(checksum)!=item["checksum_file_sha256"]:
                raise HistoricalDevelopmentError("input audit digest drifted for %s/%s" % (day,kind))
            bound[kind]=item
        result.append({"date":day,"input_audit":bound})
    return result


def _state(total: float, plan: HistoricalDiagnosticPlan) -> str:
    proxies = plan.raw["feature_proxies"]
    if total <= float(proxies["thin_max_depth"]): return "THIN_BOOK"
    if total >= float(proxies["deep_min_depth"]): return "DEEP_BOOK"
    return "NORMAL_BOOK"


def _latest(items: Sequence[Tuple[datetime, Any]], at: datetime) -> Tuple[datetime, Any] | None:
    index = bisect.bisect_right([item[0] for item in items], at) - 1
    return items[index] if index >= 0 else None


def _range_indices(times: Sequence[datetime], start: datetime, end: datetime, *, end_inclusive: bool = True) -> Tuple[int, int]:
    """Exact window boundaries: pressure is [start,end), response is (start,end]."""
    return bisect.bisect_left(times, start), (bisect.bisect_right(times, end) if end_inclusive else bisect.bisect_left(times, end))


def build_day_rows(item: _DayInput, plan: HistoricalDiagnosticPlan) -> List[Dict[str, Any]]:
    """Generate outcome-labeled diagnostic rows from one checksum-validated day.

    Every feature is observed by `decision_at`; labels are attached only after
    their path ends. Rows with a missing/stale/gapped required path are censored
    rather than filled forward.
    """
    if plan.status not in {"FROZEN_SEEN_DEVELOPMENT", "FROZEN_BEFORE_DOWNLOAD"}:
        raise HistoricalDevelopmentError("rows require a frozen diagnostic contract")
    trades, depths, metrics = item.trades, item.depths, item.metrics
    trade_times = [x.at for x in trades]
    depth_items = [(at, (bid, ask)) for at, bid, ask in depths]
    timing = plan.timing_policy
    start = datetime.combine(item.day, time.min, tzinfo=UTC)
    current = start + timedelta(seconds=timing["pressure_window_seconds"])
    finish = start + timedelta(hours=23, minutes=50)
    rows: List[Dict[str, Any]] = []
    while current <= finish:
        pressure_start, pressure_end = current-timedelta(seconds=300), current
        response_end = pressure_end+timedelta(seconds=60)
        decision_at = response_end+timedelta(seconds=1)
        eligible_at = decision_at+timedelta(milliseconds=250)
        pressure_snapshot = _latest(depth_items, pressure_end)
        prior_oi = _latest(metrics, pressure_start)
        current_oi = _latest(metrics, pressure_end)
        if not pressure_snapshot or not prior_oi or not current_oi:
            current += timedelta(minutes=5); continue
        snap_at, (bid, ask) = pressure_snapshot
        prior_snapshots = [at for at, _ in depth_items if at < snap_at]
        pressure_gap = (snap_at-prior_snapshots[-1]).total_seconds() if prior_snapshots else float("inf")
        pressure_age = (pressure_end-snap_at).total_seconds()
        if pressure_age > 30 or pressure_gap > 60:
            current += timedelta(minutes=5); continue
        li, ri = _range_indices(trade_times, pressure_start, pressure_end, end_inclusive=False)
        old_index = bisect.bisect_left(trade_times, pressure_start)-1
        if ri <= li or old_index < 0:
            current += timedelta(minutes=5); continue
        signed = sum((-x.quantity if x.buyer_maker else x.quantity) for x in trades[li:ri])
        total = bid+ask
        d = 100.0*signed/total
        if abs(d) < plan.pressure_threshold:
            current += timedelta(minutes=5); continue
        pressure_side, pressure_depth = ("BUY", ask) if d > 0 else ("SELL", bid)
        # The mechanism is explicitly contrarian: buy pressure produces a
        # SELL action and sell pressure produces a BUY action.  Never reuse
        # the pressure side for labels or realised-return sign.
        side = "SELL" if pressure_side == "BUY" else "BUY"
        # The response is strictly post-pressure.  Its actual timestamps supply
        # age and gap validation; no assumed 30-second cadence is used.
        response = [(at, values) for at, values in depth_items if pressure_end < at <= response_end]
        if len(response) < 2:
            current += timedelta(minutes=5); continue
        response_times = [x[0] for x in response]
        response_gap = max((b-a).total_seconds() for a, b in zip(response_times, response_times[1:]))
        response_age = (response_end-response_times[-1]).total_seconds()
        if response_gap > 60 or response_age > 30:
            current += timedelta(minutes=5); continue
        directional = [values[1] if pressure_side == "BUY" else values[0] for _, values in response]
        price_end, old_price = trades[ri-1].price, trades[old_index].price
        response_trade_left = bisect.bisect_right(trade_times, pressure_end)
        response_trade_right = bisect.bisect_right(trade_times, response_end)
        if response_trade_right <= response_trade_left:
            current += timedelta(minutes=5); continue
        response_return = math.log(trades[response_trade_right-1].price/price_end)
        r = math.log(directional[-1]/pressure_depth)-abs(response_return)
        current_age = (decision_at-current_oi[0]).total_seconds()
        oi_gap = (current_oi[0]-prior_oi[0]).total_seconds()
        if current_age > 300 or oi_gap <= 0 or oi_gap > 300:
            current += timedelta(minutes=5); continue
        entry_index = bisect.bisect_left(trade_times, eligible_at)
        if entry_index >= len(trades):
            current += timedelta(minutes=5); continue
        entry = trades[entry_index]
        entry_wait = (entry.at-eligible_at).total_seconds()
        if entry_wait > timing["max_entry_wait_seconds"]:
            current += timedelta(minutes=5); continue
        horizon = entry.at+timedelta(seconds=300)
        end_index = bisect.bisect_right(trade_times, horizon)
        path = trades[entry_index:end_index]
        path_head_age=(path[0].at-entry.at).total_seconds() if path else float("inf")
        path_max_gap=max(((b.at-a.at).total_seconds() for a,b in zip(path,path[1:])),default=0.0)
        path_tail_age=(horizon-path[-1].at).total_seconds() if path else float("inf")
        if not path or path_head_age > timing["max_path_trade_age_seconds"] or path_max_gap > timing["max_path_trade_gap_seconds"] or path_tail_age > timing["max_path_trade_age_seconds"]:
            current += timedelta(minutes=5); continue
        label = label_barrier_path(side=side, entry_price=entry.price, tp_bps=20, sl_bps=12, horizon_end=horizon, trades=[BarrierTrade(x.at,x.trade_id,x.price) for x in path])
        if label["outcome"] not in OUTCOMES:
            current += timedelta(minutes=5); continue
        valuation_price = float(label.get("valuation_price", entry.price if label["outcome"] != "TIMEOUT" else path[-1].price))
        gross = 20.0 if label["outcome"] == "TP" else -12.0 if label["outcome"] == "SL" else (valuation_price/entry.price-1.0)*(10000.0 if side=="BUY" else -10000.0)
        row = {
            "record_type":"binance_cm_historical_diagnostic_development_row.v2", "diagnostic_id":plan.diagnostic_id, "plan_canonical_sha256":plan.canonical_digest,
            "date":item.day.isoformat(), "data_role":"DEVELOPMENT" if plan.status=="FROZEN_SEEN_DEVELOPMENT" else "FRESH_SCORE_ONLY", "stage":"WATCH", "cohort":"ALL_EXTREMES_SHARED", "pressure_side":pressure_side, "side":side, "state_id":_state(total,plan),
            "features":{"D":d,"R":r,"L":math.log(float(current_oi[1])/float(prior_oi[1])),"response_persistent":1.0 if all(x>=pressure_depth for x in directional) else 0.0,"price_decelerates":1.0 if (1 if d>0 else -1)*response_return <= 0 else 0.0},
            "response_snapshot_count":len(response), "timing":{"pressure_start":pressure_start.isoformat(),"pressure_end":pressure_end.isoformat(),"response_start":pressure_end.isoformat(),"response_end":response_end.isoformat(),"decision_at":decision_at.isoformat(),"entry_at":entry.at.isoformat(),"path_end_at":label["path_end_at"],"valuation_event_at":label["valuation_event_at"],"label_available_at":label["path_end_at"]},
            "actual_timestamp_quality":{"pressure_book_age_seconds":pressure_age,"pressure_book_gap_seconds":pressure_gap,"response_book_age_seconds":response_age,"response_book_gap_seconds":response_gap,"oi_age_seconds":current_age,"oi_gap_seconds":oi_gap,"path_head_age_seconds":path_head_age,"path_max_gap_seconds":path_max_gap,"path_tail_age_seconds":path_tail_age},
            "label":{"outcome":label["outcome"],"gross_return_bps":gross,"same_timestamp_conservative_sl":bool(label.get("same_timestamp_conservative_sl",False)),"timeout_payoff_kind":"LAST_OBSERVED_AGGTRADE_BEFORE_HORIZON_BPS"},
        }
        row["row_sha256"] = canonical_sha256(row)
        rows.append(row); current += timedelta(minutes=5)
    return rows


@dataclass
class ThreeClassLogistic:
    names: Tuple[str,...]; means: List[float]; scales: List[float]; weights: List[List[float]]
    @classmethod
    def fit(cls, rows: Sequence[Mapping[str,Any]], names: Sequence[str]) -> "ThreeClassLogistic":
        if not rows: raise HistoricalDevelopmentError("cannot fit an empty split")
        names=tuple(names); X=[[float(r["features"][n]) for n in names] for r in rows]
        means=[sum(x[i] for x in X)/len(X) for i in range(len(names))]; scales=[max(math.sqrt(sum((x[i]-means[i])**2 for x in X)/len(X)),1e-9) for i in range(len(names))]
        weights=[[0.0]*(len(names)+1) for _ in OUTCOMES]; outcome={x:i for i,x in enumerate(OUTCOMES)}
        for _ in range(250):
            grad=[[0.0]*(len(names)+1) for _ in OUTCOMES]
            for x,row in zip(X,rows):
                vector=[1.0]+[(v-m)/s for v,m,s in zip(x,means,scales)]; probs=_softmax([sum(w*v for w,v in zip(z,vector)) for z in weights]); target=outcome[row["label"]["outcome"]]
                for ci in range(3):
                    for fi,v in enumerate(vector): grad[ci][fi]+=(probs[ci]-(1.0 if ci==target else 0.0))*v
            for ci in range(3):
                for fi in range(len(weights[ci])): weights[ci][fi]-=.1*(grad[ci][fi]/len(X)+(.01*weights[ci][fi] if fi else 0))
        return cls(names,means,scales,weights)
    def predict(self,row:Mapping[str,Any])->Dict[str,float]:
        vector=[1.0]+[(float(row["features"][n])-m)/s for n,m,s in zip(self.names,self.means,self.scales)]
        return dict(zip(OUTCOMES,_softmax([sum(w*v for w,v in zip(z,vector)) for z in self.weights])))
    def artifact(self)->Dict[str,Any]: return {"feature_names":list(self.names),"scaler":{"means":self.means,"scales":self.scales},"weights":self.weights,"epochs":250,"learning_rate":.1,"l2":.01,"calibration":{"kind":"IDENTITY_TEMPERATURE_1","temperature":1.0,"fit_status":"NOT_FIT_IDENTITY_FROZEN","split":"CALIBRATION_RESERVED_NOT_USED"}}


def _softmax(logits:Sequence[float])->List[float]:
    top=max(logits); e=[math.exp(x-top) for x in logits]; total=sum(e); return [x/total for x in e]


def _split(rows:Sequence[Dict[str,Any]], plan:HistoricalDiagnosticPlan)->Tuple[List[Dict[str,Any]],List[Dict[str,Any]],List[Dict[str,Any]]]:
    fit_end,cal_end,_=(datetime.fromisoformat(plan.raw["split_policy"][x].replace("Z","+00:00")) for x in ("fit_end","calibration_end","development_test_end"))
    def at(r): return datetime.fromisoformat(r["timing"]["decision_at"])
    return [r for r in rows if at(r)<=fit_end],[r for r in rows if fit_end<at(r)<=cal_end],[r for r in rows if cal_end<at(r)]


def _scores(rows:Sequence[Dict[str,Any]], model:ThreeClassLogistic, timeout:float, cost:float, *, candidate: bool)->Dict[str,Any]:
    loss=brier=base=stress=0.; selected=0; eligible=0; gross=0.
    for row in rows:
        p=model.predict(row); actual=row["label"]["outcome"]; loss-=math.log(max(p[actual],1e-15)); brier+=sum((p[o]-(1. if o==actual else 0.))**2 for o in OUTCOMES)
        choice=select_positive_ev(probabilities=p,base_cost_bps=10,tp_bps=20,sl_bps=12,timeout_payoff_bps=timeout)
        feature_eligible = (not candidate) or (row["features"]["response_persistent"] == 1.0 and row["features"]["price_decelerates"] == 1.0)
        if feature_eligible: eligible += 1
        if feature_eligible and choice["selected"]:
            selected+=1; g=float(row["label"]["gross_return_bps"]); gross+=g; base+=g-cost; stress+=g-20
    n=len(rows)
    return {"observations":n,"eligible_count":eligible,"log_loss":loss/n if n else None,"multiclass_brier":brier/n if n else None,"selected_count":selected,"selected_gross_bps":gross,"selected_base_utility_bps":base,"selected_stress_utility_bps":stress,"opportunity_normalized_utility_bps":base/n if n else None,"stress_mean_bps":stress/selected if selected else None}


def _coverage(rows:Sequence[Dict[str,Any]])->Dict[str,Any]:
    def counts(key):
        result:Dict[str,int]={}
        for row in rows: result[str(row[key])]=result.get(str(row[key]),0)+1
        return result
    days=counts("date"); sides=counts("side"); states=counts("state_id")
    return {"effective_episodes":len(rows),"utc_days":len(days),"by_day":days,"by_side":sides,"by_state":states,"max_day_concentration":max(days.values(),default=0)/len(rows) if rows else 1.,"max_state_concentration":max(states.values(),default=0)/len(rows) if rows else 1.,"max_direction_concentration":max(sides.values(),default=0)/len(rows) if rows else 1.}


def _bootstrap(test:Sequence[Dict[str,Any]], cand:ThreeClassLogistic, control:ThreeClassLogistic, timeout_c:float, timeout_k:float, seed:int)->Dict[str,Any]:
    by_day:Dict[str,List[Dict[str,Any]]]={}
    for row in test: by_day.setdefault(row["date"],[]).append(row)
    if not by_day:return {"iterations":400,"candidate_base_lower95":None,"incremental_lower95":None}
    rng=random.Random(seed); days=sorted(by_day); base=[]; inc=[]
    for _ in range(400):
        sample=[row for day in [rng.choice(days) for __ in days] for row in by_day[day]]
        a=_scores(sample,cand,timeout_c,10,candidate=True)["opportunity_normalized_utility_bps"]; b=_scores(sample,control,timeout_k,10,candidate=False)["opportunity_normalized_utility_bps"]
        base.append(a); inc.append(a-b)
    base.sort();inc.sort(); return {"iterations":400,"seed":seed,"candidate_base_lower95":base[9],"incremental_lower95":inc[9]}


def _decision(coverage:Mapping[str,Any], predictive:Mapping[str,Any], bootstrap:Mapping[str,Any], candidate:Mapping[str,Any], plan:HistoricalDiagnosticPlan)->Dict[str,Any]:
    g=plan.gate_policy
    if not coverage["effective_episodes"]: return {"decision":"STOP_DATA_INVALID","reason":"NO_EFFECTIVE_EPISODES"}
    coverage_fail=(coverage["effective_episodes"]<g["min_effective_episodes"] or min(coverage["by_side"].get("BUY",0),coverage["by_side"].get("SELL",0))<g["min_effective_per_side"] or coverage["utc_days"]<g["min_utc_days"] or min(coverage["by_state"].get(s,0) for s in ("THIN_BOOK","NORMAL_BOOK","DEEP_BOOK"))<g["min_effective_per_state"] or coverage["max_day_concentration"]>g["max_utc_day_concentration"] or coverage["max_state_concentration"]>g["max_state_concentration"] or coverage["max_direction_concentration"]>g["max_direction_concentration"])
    if coverage_fail:return {"decision":"WAIT_DATA_COVERAGE","reason":"FROZEN_COVERAGE_GATE_NOT_MET"}
    for side, values in predictive.items():
        candidate_metrics, control_metrics = values["candidate"], values["control"]
        if candidate_metrics["log_loss"] > control_metrics["log_loss"] * (1.0-g["relative_logloss_improvement_min"]) or candidate_metrics["multiclass_brier"] > control_metrics["multiclass_brier"]:
            return {"decision":"STOP_PREDICTIVE","reason":"FROZEN_DIRECTIONAL_LOGLOSS_OR_BRIER_GATE_NOT_MET","side":side}
    if bootstrap["candidate_base_lower95"]<=0 or bootstrap["incremental_lower95"]<=0 or candidate["stress_mean_bps"] is None or candidate["stress_mean_bps"]<0:return {"decision":"STOP_ECONOMIC","reason":"FROZEN_ECONOMIC_GATE_NOT_MET"}
    return {"decision":"NOT_ADJUDICATED_DEVELOPMENT","reason":"JANUARY_IS_SEEN_DEVELOPMENT_ONLY"}


def build_january_development_artifacts(*, plan:HistoricalDiagnosticPlan, input_root:Path, workspace_root:Path, rows_path:Path, manifest_path:Path, model_path:Path)->Dict[str,Any]:
    if plan.status!="FROZEN_SEEN_DEVELOPMENT": raise HistoricalDevelopmentError("only January seen-development plan is accepted")
    ledger_path=workspace_root/plan.raw["evidence_ledger"]; ledger=verify_historical_evidence_ledger(ledger_path,workspace_root=workspace_root)
    all_rows:List[Dict[str,Any]]=[]; audit=[]; shim=SimpleNamespace(instrument=plan.instrument)
    for text in plan.dates:
        day=date.fromisoformat(text); item=_load_day(shim,input_root,day); all_rows.extend(build_day_rows(item,plan)); audit.append({"date":text,"input_audit":item.audit})
    all_rows.sort(key=lambda x:(x["timing"]["decision_at"],x["side"]))
    _write_once(rows_path,"".join(canonical_sha256({})[:0]+json.dumps(r,sort_keys=True,separators=(",",":"))+"\n" for r in all_rows))
    fit,cal,test=_split(all_rows,plan)
    models:Dict[str,Any]={"record_type":"binance_cm_historical_diagnostic_model.v2","diagnostic_id":plan.diagnostic_id,"plan_canonical_sha256":plan.canonical_digest,"status":"DEVELOPMENT_ONLY","outcomes":list(OUTCOMES),"splits":{"fit":len(fit),"calibration":len(cal),"development_test":len(test)},"models":{}}
    results={}
    for side in ("BUY","SELL"):
        f=[r for r in fit if r["side"]==side]; t=[r for r in test if r["side"]==side]
        if not f or not t: continue
        cand=ThreeClassLogistic.fit(f,("D","R","response_persistent","price_decelerates")); control=ThreeClassLogistic.fit(f,("D",))
        timeout_c=sum(r["label"]["gross_return_bps"] for r in f if r["label"]["outcome"]=="TIMEOUT")/max(1,sum(r["label"]["outcome"]=="TIMEOUT" for r in f)); timeout_k=timeout_c
        models["models"][side]={"candidate":cand.artifact(),"control":control.artifact(),"timeout_payoff_bps_fit_only":timeout_c}
        results[side]={"candidate":_scores(t,cand,timeout_c,10,candidate=True),"control":_scores(t,control,timeout_k,10,candidate=False),"bootstrap":_bootstrap(t,cand,control,timeout_c,timeout_k,20260723)}
    models["model_canonical_sha256"]=canonical_sha256(models); _write_once(model_path,json.dumps(models,sort_keys=True,separators=(",",":"))+"\n")
    # Overall evaluation uses models fitted by side; aggregate only factual per-side reports.
    coverage=_coverage(test); first=next(iter(results.values()),None)
    aggregate_candidate={"stress_mean_bps":None} if not first else {"stress_mean_bps":sum(x["candidate"]["selected_stress_utility_bps"] for x in results.values())/max(1,sum(x["candidate"]["selected_count"] for x in results.values()))}
    aggregate_bootstrap={"candidate_base_lower95":min((x["bootstrap"]["candidate_base_lower95"] for x in results.values()),default=None),"incremental_lower95":min((x["bootstrap"]["incremental_lower95"] for x in results.values()),default=None)}
    decision=_decision(coverage,results,aggregate_bootstrap,aggregate_candidate,plan) if aggregate_bootstrap["candidate_base_lower95"] is not None else {"decision":"WAIT_DATA_COVERAGE","reason":"NO_SIDE_MODEL_TEST"}
    rows_binding={"path":str(rows_path),"sha256":sha256_file(rows_path)}
    manifest={"record_type":"binance_cm_historical_diagnostic_development_manifest.v2","manifest_id":"%s-post-pressure-response-v2" % plan.diagnostic_id,"semantic_version":"post_pressure_response_v2","diagnostic_id":plan.diagnostic_id,"status":"DEVELOPMENT_ONLY_NOT_TRADING","plan_canonical_sha256":plan.canonical_digest,"v1_ledger":ledger,"input_audit":audit,"software_bindings":{"development_module":{"path":str(Path(__file__).resolve()),"sha256":sha256_file(Path(__file__).resolve())}},"row_count":len(all_rows),"rows_artifact":rows_binding,"rows":{"path":str(rows_path),"sha256":rows_binding["sha256"],"count":len(all_rows)},"model":{"path":str(model_path),"sha256":sha256_file(model_path)},"split_counts":{"fit":len(fit),"calibration":len(cal),"development_test":len(test)},"coverage":coverage,"evaluation_by_side":results,"gate":decision,"g2_eligibility":False,"trading_authorization":"DENIED"}
    manifest["manifest_canonical_sha256"]=canonical_sha256(manifest); _write_once(manifest_path,json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n")
    return {"rows":len(all_rows),"rows_sha256":sha256_file(rows_path),"model_sha256":sha256_file(model_path),"manifest_sha256":sha256_file(manifest_path),"gate":decision}


def finalize_january_development_artifacts(*, plan: HistoricalDiagnosticPlan, workspace_root: Path, rows_path: Path, manifest_path: Path, model_path: Path) -> Dict[str, Any]:
    """Finalize a previously write-once row artifact without rereading inputs.

    This explicit recovery path is useful if a process boundary occurs after
    immutable rows are safely written. It refuses rows that do not bind the
    exact January plan, so it cannot turn an arbitrary file into evidence.
    """
    if plan.status != "FROZEN_SEEN_DEVELOPMENT" or not rows_path.is_file():
        raise HistoricalDevelopmentError("finalization requires an existing January development row artifact")
    try:
        rows=[json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError,json.JSONDecodeError) as exc:
        raise HistoricalDevelopmentError("development rows cannot be parsed") from exc
    if not rows or any(r.get("record_type")!="binance_cm_historical_diagnostic_development_row.v2" or r.get("plan_canonical_sha256")!=plan.canonical_digest or r.get("data_role")!="DEVELOPMENT" or r.get("date") not in plan.dates or r.get("label",{}).get("outcome") not in OUTCOMES for r in rows):
        raise HistoricalDevelopmentError("development rows do not bind the frozen January contract")
    # Recheck their own row receipts before fitting; no outcome can repair a
    # malformed feature/timestamp row.
    if any(canonical_sha256({k:v for k,v in r.items() if k!="row_sha256"}) != r.get("row_sha256") for r in rows):
        raise HistoricalDevelopmentError("development row digest drifted")
    ledger=verify_historical_evidence_ledger(workspace_root/plan.raw["evidence_ledger"],workspace_root=workspace_root)
    input_audit=_rebind_january_input_audit(plan, workspace_root)
    fit,cal,test=_split(rows,plan)
    models={"record_type":"binance_cm_historical_diagnostic_model.v2","diagnostic_id":plan.diagnostic_id,"plan_canonical_sha256":plan.canonical_digest,"status":"DEVELOPMENT_ONLY","outcomes":list(OUTCOMES),"splits":{"fit":len(fit),"calibration":len(cal),"development_test":len(test)},"models":{}}
    results={}
    for side in ("BUY","SELL"):
        f=[r for r in fit if r["side"]==side]; t=[r for r in test if r["side"]==side]
        if not f or not t: continue
        candidate=ThreeClassLogistic.fit(f,("D","R","response_persistent","price_decelerates")); control=ThreeClassLogistic.fit(f,("D",))
        timeout=sum(r["label"]["gross_return_bps"] for r in f if r["label"]["outcome"]=="TIMEOUT")/max(1,sum(r["label"]["outcome"]=="TIMEOUT" for r in f))
        models["models"][side]={"candidate":candidate.artifact(),"control":control.artifact(),"timeout_payoff_bps_fit_only":timeout}
        results[side]={"candidate":_scores(t,candidate,timeout,10,candidate=True),"control":_scores(t,control,timeout,10,candidate=False),"bootstrap":_bootstrap(t,candidate,control,timeout,timeout,20260723)}
    models["model_canonical_sha256"]=canonical_sha256(models); _write_once(model_path,json.dumps(models,sort_keys=True,separators=(",",":"))+"\n")
    coverage=_coverage(test)
    bootstrap={"candidate_base_lower95":min((x["bootstrap"]["candidate_base_lower95"] for x in results.values()),default=None),"incremental_lower95":min((x["bootstrap"]["incremental_lower95"] for x in results.values()),default=None)}
    candidate={"stress_mean_bps":sum(x["candidate"]["selected_stress_utility_bps"] for x in results.values())/max(1,sum(x["candidate"]["selected_count"] for x in results.values()))} if results else {"stress_mean_bps":None}
    gate=_decision(coverage,results,bootstrap,candidate,plan) if bootstrap["candidate_base_lower95"] is not None else {"decision":"WAIT_DATA_COVERAGE","reason":"NO_SIDE_MODEL_TEST"}
    binding={"path":str(rows_path),"sha256":sha256_file(rows_path)}
    manifest={"record_type":"binance_cm_historical_diagnostic_development_manifest.v2","manifest_id":"%s-post-pressure-response-v2" % plan.diagnostic_id,"semantic_version":"post_pressure_response_v2","diagnostic_id":plan.diagnostic_id,"status":"DEVELOPMENT_ONLY_NOT_TRADING","plan_canonical_sha256":plan.canonical_digest,"v1_ledger":ledger,"input_audit":input_audit,"software_bindings":{"development_module":{"path":str(Path(__file__).resolve()),"sha256":sha256_file(Path(__file__).resolve())}},"row_count":len(rows),"rows_artifact":binding,"rows":{"path":str(rows_path),"sha256":binding["sha256"],"count":len(rows)},"model":{"path":str(model_path),"sha256":sha256_file(model_path)},"split_counts":{"fit":len(fit),"calibration":len(cal),"development_test":len(test)},"coverage":coverage,"evaluation_by_side":results,"gate":gate,"g2_eligibility":False,"trading_authorization":"DENIED"}
    manifest["manifest_canonical_sha256"]=canonical_sha256(manifest); _write_once(manifest_path,json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n")
    return {"rows":len(rows),"rows_sha256":binding["sha256"],"model_sha256":sha256_file(model_path),"manifest_sha256":sha256_file(manifest_path),"gate":gate}
