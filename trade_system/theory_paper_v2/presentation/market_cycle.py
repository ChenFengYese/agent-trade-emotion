"""Thin local CLI for identity-bound, public, non-executable research cycles."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

from ..domain.contracts.canonical import canonical_bytes, loads_json_strict
from ..domain.market_cycle.contracts import (
    LAWFUL_REFERENCE_ACTIONS,
    MARKET_DATA_PROFILES,
    CycleRequest,
)
from ..domain.market_cycle.capability_evaluation import CAPABILITY_IDS
from ..domain.market_cycle.paper_capability_evaluation import PAPER_CAPABILITY_IDS
from ..domain.market_cycle.evidence import (
    EvidencePolicy,
    V332_EVIDENCE_POLICY_ID,
)
from ..domain.market_cycle.experiment import ExperimentPolicyV1
from ..domain.market_cycle.theory import (
    V332_THEORY_IDENTITY,
    V332_THEORY_REVISION,
)
from ..infrastructure.market_data.okx_profiles import (
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
)
from ..application.market_cycle.service import (
    CONTROLLER_CYCLE_WORKER_IDS,
)
from ..infrastructure.market_cycle.clock import SystemUTCMonotonicClock
from ..infrastructure.market_cycle.runtime import (
    DEFAULT_RUNTIME_ROOT,
    build_market_cycle_runtime,
    initialize_v332_run,
)
from ..infrastructure.market_cycle.operational_evaluation_store import (
    FileOperationalEvaluationStore,
)
from ..infrastructure.market_cycle.capability_evaluation_store import (
    FileCapabilityEvaluationStore,
)
from ..infrastructure.market_cycle.paper_capability_evaluation_store import (
    FilePaperCapabilityEvaluationStore,
)

_DEFAULT_V332_THEORY_PACKAGE = (
    Path(__file__).resolve().parents[3] / "theory" / "versions" / "v3.3.2"
)
_V332_CONTROLLER_WORKER_IDS = tuple(
    worker_id
    for worker_id in CONTROLLER_CYCLE_WORKER_IDS
    if worker_id not in {"decision-v1", "review-v1"}
)
_V332_COMPLETABLE_WORKER_IDS = (
    *_V332_CONTROLLER_WORKER_IDS,
    "capability-assessor-v1",
)


def _write(value: Mapping[str, Any]) -> None:
    sys.stdout.buffer.write(canonical_bytes(value) + b"\n")


def _paper_cycle_id(value: str) -> str:
    if not value or "," in value:
        raise argparse.ArgumentTypeError(
            "pass each exact paper cycle with a separate --cycle-id; "
            "comma-separated lists are not accepted"
        )
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="market-cycle",
        description=(
            "Identity-bound public-data, Agent-first research cycle. V3.3.2 public collection "
            "requires a frozen experiment policy; this CLI never grants external account, order, "
            "credential, testnet, live or funds authority."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=DEFAULT_RUNTIME_ROOT,
        help="exact run root containing the controller-owned controller/run.json",
    )
    parser.add_argument(
        "--theory-version",
        choices=("3.3.2",),
        default="3.3.2",
        help="the current command surface is bound to frozen V3.3.2",
    )
    parser.add_argument(
        "--allow-public-collection",
        action="store_true",
        help=(
            "explicitly allow V3.3.2 HYPE input collection into the primary raw store; "
            "without this flag V3.3.2 is replay-only"
        ),
    )
    parser.add_argument(
        "--theory-package",
        type=Path,
        default=None,
        help=(
            "frozen V3.3.2 package directory; optional when running from a "
            "checkout containing the bundled V3.3.2 package"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "initialize-run",
        help=(
            "create one fresh V3.3.2 run and bind its canonical experiment policy; "
            "performs no network, paper, account or order action"
        ),
    )
    initialize.add_argument("policy_file", type=Path)

    commands.add_parser(
        "close-run",
        help=(
            "atomically freeze the V3.3.2 run; preserves paper positions and "
            "orders and performs no market collection or trading action"
        ),
    )

    create = commands.add_parser("create", help="create a request; performs no network I/O")
    create.add_argument("cycle_id")
    create.add_argument("--instrument")
    create.add_argument("--contract-identity")
    create.add_argument(
        "--analysis-profile",
        choices=("COLD",),
        default="COLD",
    )
    create.add_argument(
        "--data-profile",
        choices=tuple(sorted(MARKET_DATA_PROFILES)),
        default=None,
        help="frozen public-data profile for this cycle; performs no account access",
    )
    create.add_argument("--horizon-seconds", type=int, default=None)
    create.add_argument("--tolerance-seconds", type=int, default=None)

    next_step = commands.add_parser(
        "next",
        help="perform one durable transition; CAPTURE_INPUT/CAPTURE_OUTCOME may use public OKX HTTPS",
    )
    next_step.add_argument("cycle_id")

    status = commands.add_parser("status", help="read one RunState without advancing")
    status.add_argument("cycle_id")

    evaluate = commands.add_parser(
        "evaluate-operational",
        help=(
            "replay one COMPLETE V3.3.2 cycle, seal its create-once no-score E0 "
            "package, and emit the saved package; performs no network I/O"
        ),
    )
    evaluate.add_argument("cycle_id")
    evaluate.add_argument("--evaluation-id")

    capability_prepare = commands.add_parser(
        "capability-prepare-assessor",
        help=(
            "freeze one general singleton capability basis and prepare its "
            "independent assessor; performs no network or trading action"
        ),
    )
    capability_prepare.add_argument("cycle_id")
    capability_prepare.add_argument(
        "capability_id", choices=tuple(sorted(CAPABILITY_IDS))
    )
    capability_prepare.add_argument("task_id")
    capability_prepare.add_argument("assessment_due_at")

    capability_preregister = commands.add_parser(
        "capability-preregister",
        help="seal the prepared task after an independent assessor ACK",
    )
    capability_preregister.add_argument("cycle_id")
    capability_preregister.add_argument(
        "capability_id", choices=tuple(sorted(CAPABILITY_IDS))
    )

    capability_seal = commands.add_parser(
        "capability-seal-assessment",
        help="seal receipt-bound pre-outcome assessor findings",
    )
    capability_seal.add_argument("cycle_id")
    capability_seal.add_argument(
        "capability_id", choices=tuple(sorted(CAPABILITY_IDS))
    )
    capability_seal.add_argument("assessment_id")

    paper_capability_prepare = commands.add_parser(
        "paper-capability-prepare-assessor",
        help=(
            "freeze one paper singleton capability basis and prepare its "
            "independent assessor; performs no market, account or trading action"
        ),
    )
    paper_capability_prepare.add_argument(
        "capability_id", choices=tuple(sorted(PAPER_CAPABILITY_IDS))
    )
    paper_capability_prepare.add_argument("task_id")
    paper_capability_prepare.add_argument("assessment_due_at")
    paper_capability_prepare.add_argument(
        "--cycle-id",
        dest="cycle_ids",
        action="append",
        required=True,
        type=_paper_cycle_id,
        help=(
            "exact evidence cycle; repeat --cycle-id in chronological order "
            "for multi-cycle evidence (values are never comma-split)"
        ),
    )

    paper_capability_preregister = commands.add_parser(
        "paper-capability-preregister",
        help="seal a paper capability task after its independent assessor ACK",
    )
    paper_capability_preregister.add_argument(
        "capability_id", choices=tuple(sorted(PAPER_CAPABILITY_IDS))
    )
    paper_capability_preregister.add_argument(
        "--cycle-id",
        dest="cycle_ids",
        action="append",
        required=True,
        type=_paper_cycle_id,
        help="repeat once per exact evidence cycle in chronological order",
    )

    paper_capability_seal = commands.add_parser(
        "paper-capability-seal-assessment",
        help="seal receipt-bound pre-outcome paper assessor findings",
    )
    paper_capability_seal.add_argument(
        "capability_id", choices=tuple(sorted(PAPER_CAPABILITY_IDS))
    )
    paper_capability_seal.add_argument("assessment_id")
    paper_capability_seal.add_argument(
        "--cycle-id",
        dest="cycle_ids",
        action="append",
        required=True,
        type=_paper_cycle_id,
        help="repeat once per exact evidence cycle in chronological order",
    )

    request = commands.add_parser("agent-request", help="read the pending Agent sidecar")
    request.add_argument("cycle_id")

    review_request = commands.add_parser(
        "agent-review-request", help="read the pending Agent review sidecar"
    )
    review_request.add_argument("cycle_id")

    deliver = commands.add_parser(
        "deliver", help="write one verbatim UTF-8 Agent decision bound to a request"
    )
    deliver.add_argument("cycle_id")
    deliver.add_argument("decision_file", type=Path)
    deliver.add_argument(
        "--media-type",
        default="text/markdown",
        help="non-authoritative format hint; readable UTF-8 body admission is content-based",
    )

    deliver_review = commands.add_parser(
        "deliver-review",
        help="write one verbatim UTF-8 Agent review bound to sealed Outcome",
    )
    deliver_review.add_argument("cycle_id")
    deliver_review.add_argument("review_file", type=Path)
    deliver_review.add_argument(
        "--media-type",
        default="text/markdown",
        help="non-authoritative format hint; readable UTF-8 body admission is content-based",
    )

    commands.add_parser(
        "controller-status",
        help="read internal Worker deadline and dispatch state without advancing",
    )

    prepare = commands.add_parser(
        "controller-prepare-worker",
        help="materialize and bind one supported cycle Worker task before spawn",
    )
    prepare.add_argument("cycle_id")
    prepare.add_argument(
        "worker_id", choices=_V332_CONTROLLER_WORKER_IDS
    )

    spawn = commands.add_parser(
        "controller-mark-worker-spawn-requested",
        help="persist spawn intent before asking an external Worker scheduler",
    )
    spawn.add_argument("cycle_id")
    spawn.add_argument(
        "worker_id", choices=_V332_CONTROLLER_WORKER_IDS
    )
    spawn.add_argument("dispatch_id")

    spawn_ack = commands.add_parser(
        "controller-ack-worker-spawn",
        help="mark DISPATCHED only after the external scheduler returns an acknowledgement",
    )
    spawn_ack.add_argument("cycle_id")
    spawn_ack.add_argument(
        "worker_id", choices=_V332_COMPLETABLE_WORKER_IDS
    )
    spawn_ack.add_argument("dispatch_id")
    spawn_ack.add_argument("execution_ref")

    complete = commands.add_parser(
        "controller-complete-worker",
        help="bind one timely Worker output and release the active dispatch lane",
    )
    complete.add_argument("cycle_id")
    complete.add_argument(
        "worker_id", choices=_V332_COMPLETABLE_WORKER_IDS
    )
    complete.add_argument("dispatch_id")
    complete.add_argument("output_sha256")

    recover = commands.add_parser(
        "controller-recover-worker",
        help="inspect the durable recovery action for one interrupted Worker dispatch",
    )
    recover.add_argument("cycle_id")
    recover.add_argument(
        "worker_id", choices=_V332_CONTROLLER_WORKER_IDS
    )

    expire_worker = commands.add_parser(
        "controller-expire-worker",
        help="expire an overdue Worker with its fixed kind-owned reason",
    )
    expire_worker.add_argument("cycle_id")
    expire_worker.add_argument(
        "worker_id", choices=_V332_CONTROLLER_WORKER_IDS
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    expected_identity = V332_THEORY_IDENTITY
    theory_package = args.theory_package
    if theory_package is None:
        theory_package = _DEFAULT_V332_THEORY_PACKAGE
    if args.command == "initialize-run":
        if args.allow_public_collection:
            raise ValueError("initialize-run does not collect public data")
        policy_path = args.policy_file
        if policy_path.is_symlink() or not policy_path.is_file():
            raise ValueError("experiment policy file is not a safe regular file")
        raw = policy_path.read_bytes()
        value = loads_json_strict(raw)
        if canonical_bytes(value) + b"\n" != raw:
            raise ValueError("experiment policy file must be canonical JSON with newline")
        policy = ExperimentPolicyV1.from_dict(value)
        manifest = initialize_v332_run(
            args.runtime_root,
            theory_package=theory_package,
            experiment_policy=policy,
        )
        _write(
            {
                "run_manifest": manifest.to_dict(),
                "run_manifest_identity_sha256": manifest.identity_sha256,
                "experiment_policy_sha256": policy.policy_sha256,
            }
        )
        return 0
    if args.command == "close-run" and args.allow_public_collection:
        raise ValueError("close-run does not collect public data")
    runtime = build_market_cycle_runtime(
        runtime_root=args.runtime_root,
        theory_package=theory_package,
        expected_theory_identity=expected_identity,
        allow_public_collection=args.allow_public_collection,
        recover_interrupted_closure=args.command == "close-run",
    )
    if args.command == "close-run":
        manifest = runtime.close_run()
        _write(
            {
                "run_manifest": manifest.to_dict(),
                "run_manifest_identity_sha256": manifest.identity_sha256,
                "closure_status": "CLOSED",
            }
        )
        return 0
    if args.command == "create":
        policy = runtime.experiment_policy
        if policy.phase == "CONTINUITY_24H":
            if any(
                value is not None
                for value in (
                    args.instrument,
                    args.contract_identity,
                    args.data_profile,
                    args.horizon_seconds,
                    args.tolerance_seconds,
                )
            ) or args.analysis_profile != "COLD":
                raise ValueError(
                    "CONTINUITY_CREATE_USES_FROZEN_POLICY_WITHOUT_OVERRIDES"
                )
            state = runtime.create_goal_cycle(args.cycle_id)
        else:
            instrument = args.instrument or HYPE_OKX_INSTRUMENT_ID
            data_profile = (
                args.data_profile or HYPE_OKX_DATA_PROFILE.market_data_profile
            )
            contract_identity = (
                args.contract_identity
                or runtime.run_manifest.market_contract_identity
            )
            horizon_seconds = (
                args.horizon_seconds
                if args.horizon_seconds is not None
                else 3600
            )
            tolerance_seconds = (
                args.tolerance_seconds
                if args.tolerance_seconds is not None
                else 60
            )
            state = runtime.service.create(
                CycleRequest(
                    request_id=f"{args.cycle_id}.request",
                    cycle_id=args.cycle_id,
                    requested_at=SystemUTCMonotonicClock()(),
                    venue_id="OKX",
                    instrument_id=instrument,
                    contract_identity=contract_identity,
                    analysis_profile=args.analysis_profile,
                    data_profile=data_profile,
                    outcome_horizon_seconds=horizon_seconds,
                    outcome_tolerance_seconds=tolerance_seconds,
                    lawful_actions=LAWFUL_REFERENCE_ACTIONS,
                    theory_identity=runtime.identity,
                )
            )
        _write(state.to_dict())
        return 0
    if args.command == "next":
        result = runtime.service.run_next(args.cycle_id)
        _write(
            {
                "changed": result.changed,
                "pending_reason": result.pending_reason,
                "pending_ref": result.pending_ref,
                "state": result.state.to_dict(),
            }
        )
        return 0
    if args.command == "status":
        _write(runtime.service.status(args.cycle_id).to_dict())
        return 0
    if args.command == "evaluate-operational":
        package = FileOperationalEvaluationStore(runtime).evaluate_and_seal(
            cycle_id=args.cycle_id,
            evaluation_id=(
                args.evaluation_id or f"{args.cycle_id}.e0-operational-evaluation"
            ),
            evidence_policy=EvidencePolicy(
                policy_id=V332_EVIDENCE_POLICY_ID,
                theory_revision=V332_THEORY_REVISION,
            ),
        )
        _write(package)
        return 0
    if args.command == "capability-prepare-assessor":
        record = FileCapabilityEvaluationStore(runtime).prepare_assessor(
            cycle_id=args.cycle_id,
            task_id=args.task_id,
            capability_id=args.capability_id,
            assessment_due_at=args.assessment_due_at,
        )
        _write(record)
        return 0
    if args.command == "capability-preregister":
        task = FileCapabilityEvaluationStore(runtime).preregister(
            cycle_id=args.cycle_id,
            capability_id=args.capability_id,
        )
        _write(task.to_dict())
        return 0
    if args.command == "capability-seal-assessment":
        assessment = FileCapabilityEvaluationStore(runtime).seal_assessment(
            cycle_id=args.cycle_id,
            capability_id=args.capability_id,
            assessment_id=args.assessment_id,
        )
        _write(assessment.to_dict())
        return 0
    if args.command == "paper-capability-prepare-assessor":
        record = FilePaperCapabilityEvaluationStore(runtime).prepare_assessor(
            cycle_ids=tuple(args.cycle_ids),
            task_id=args.task_id,
            capability_id=args.capability_id,
            assessment_due_at=args.assessment_due_at,
        )
        _write(record)
        return 0
    if args.command == "paper-capability-preregister":
        task = FilePaperCapabilityEvaluationStore(runtime).preregister(
            cycle_ids=tuple(args.cycle_ids),
            capability_id=args.capability_id,
        )
        _write(task.to_dict())
        return 0
    if args.command == "paper-capability-seal-assessment":
        assessment = FilePaperCapabilityEvaluationStore(runtime).seal_assessment(
            cycle_ids=tuple(args.cycle_ids),
            capability_id=args.capability_id,
            assessment_id=args.assessment_id,
        )
        _write(assessment.to_dict())
        return 0
    if args.command == "agent-request":
        runtime.service.verify_cycle_read(args.cycle_id)
        request = runtime.mailbox.request(args.cycle_id)
        if request is None:
            raise ValueError("agent request does not exist")
        _write(request)
        return 0
    if args.command == "agent-review-request":
        runtime.service.verify_cycle_read(args.cycle_id)
        request = runtime.mailbox.review_request(args.cycle_id)
        if request is None:
            raise ValueError("agent review request does not exist")
        _write(request)
        return 0
    if args.command == "deliver":
        status = runtime.service.deliver_agent_decision(
            args.cycle_id,
            args.decision_file.read_bytes(),
            media_type=args.media_type,
        )
        _write({"cycle_id": args.cycle_id, "delivery_status": status})
        return 0
    if args.command == "deliver-review":
        status = runtime.service.deliver_agent_review(
            args.cycle_id,
            args.review_file.read_bytes(),
            media_type=args.media_type,
        )
        _write({"cycle_id": args.cycle_id, "delivery_status": status})
        return 0
    if args.command == "controller-status":
        _write(runtime.service.controller_status())
        return 0
    if args.command == "controller-prepare-worker":
        _write(
            runtime.service.controller_prepare_worker(
                args.cycle_id,
                args.worker_id,
            )
        )
        return 0
    if args.command == "controller-mark-worker-spawn-requested":
        _write(
            runtime.service.controller_mark_worker_spawn_requested(
                args.cycle_id, args.worker_id, args.dispatch_id
            )
        )
        return 0
    if args.command == "controller-ack-worker-spawn":
        if args.worker_id == "capability-assessor-v1":
            capabilities = runtime.experiment_policy.capability_ids
            if len(capabilities) != 1:
                raise ValueError(
                    "capability assessor ACK requires one singleton capability policy"
                )
            capability_id = capabilities[0]
            if capability_id in CAPABILITY_IDS:
                record = FileCapabilityEvaluationStore(
                    runtime
                ).acknowledge_assessor_spawn(
                    cycle_id=args.cycle_id,
                    dispatch_id=args.dispatch_id,
                    execution_ref=args.execution_ref,
                )
            elif capability_id in PAPER_CAPABILITY_IDS:
                record = FilePaperCapabilityEvaluationStore(
                    runtime
                ).acknowledge_assessor_spawn(
                    cycle_id=args.cycle_id,
                    dispatch_id=args.dispatch_id,
                    execution_ref=args.execution_ref,
                )
            else:
                raise ValueError(
                    "capability assessor ACK is unsupported for this policy"
                )
            _write(record)
        else:
            _write(
                runtime.service.controller_acknowledge_worker_spawn(
                    args.cycle_id,
                    args.worker_id,
                    args.dispatch_id,
                    args.execution_ref,
                )
            )
        return 0
    if args.command == "controller-complete-worker":
        if args.worker_id == "capability-assessor-v1":
            with runtime.mutation_guard():
                runtime.service.verify_cycle_read(args.cycle_id)
                _write(
                    runtime.controller_state.complete_worker(
                        args.cycle_id,
                        args.worker_id,
                        args.dispatch_id,
                        args.output_sha256,
                    )
                )
        else:
            _write(
                runtime.service.controller_complete_worker(
                    args.cycle_id,
                    args.worker_id,
                    args.dispatch_id,
                    args.output_sha256,
                )
            )
        return 0
    if args.command == "controller-recover-worker":
        _write(
            runtime.service.controller_recover_worker(
                args.cycle_id, args.worker_id
            )
        )
        return 0
    if args.command == "controller-expire-worker":
        _write(
            runtime.service.controller_expire_worker(
                args.cycle_id, args.worker_id
            )
        )
        return 0
    raise AssertionError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
