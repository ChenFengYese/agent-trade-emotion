"""Real typed support builders shared by V3.1.1 lifecycle tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from tests import (
    test_theory_paper_v2_v31_sentiment_native_projection_adapter_v2
    as sentiment_fixture,
)
from trade_system.theory_paper_v2.application.v31_sentiment_native_projection_adapter_v2 import (
    build_v31_sentiment_native_projection_receipt_v2,
)
from trade_system.theory_paper_v2.domain.contracts.canonical import canonical_bytes
from trade_system.theory_paper_v2.domain.governance.v311_fresh_process_trace_v2 import (
    build_v311_fresh_process_trace_receipt_v2,
)
from trade_system.theory_paper_v2.domain.governance.v311_successor_authority_envelope_v2 import (
    build_v311_runtime_closure_receipt_v2,
    build_v311_supervisor_policy_v2,
)
from trade_system.theory_paper_v2.domain.v31_association_preregistration_v2 import (
    build_v31_association_preregistration_v2,
)
from trade_system.theory_paper_v2.domain.v31_evaluation_contract_v2 import (
    build_v31_evaluation_contract_v2,
)


_RUNTIME_PATH = (
    "trade_system/theory_paper_v2/infrastructure/"
    "v31_successor_probe_store_v2.py"
)


def _document_binding(
    path: str, document: dict, digest_field: str
) -> dict[str, str]:
    return {
        "path": path,
        "schema_id": document["schema_id"],
        "digest_field": digest_field,
        "semantic_digest": document[digest_field],
        "physical_sha256": hashlib.sha256(
            canonical_bytes(document) + b"\n"
        ).hexdigest(),
    }

def build_real_typed_qualification_supports(
    *,
    project_root: Path,
    run_id: str,
    public_source_qualification: dict,
    outcome_monitor_qualification: dict,
    schema_compatibility: dict,
    frozen_at: str = "2026-08-07T09:00:00Z",
) -> dict[str, dict]:
    """Return every non-addendum qualification support via its real builder."""

    runtime_target = project_root / _RUNTIME_PATH
    runtime_sha = hashlib.sha256(runtime_target.read_bytes()).hexdigest()
    trace = build_v311_fresh_process_trace_receipt_v2(
        trace_id="v311-typed-support-trace-20260807t085959z",
        started_at="2026-08-07T08:59:58Z",
        completed_at="2026-08-07T08:59:59Z",
        parent_pid=100,
        worker_pid=101,
        invocation_nonce="typed-support-nonce",
        echoed_nonce="typed-support-nonce",
        python_executable="/opt/homebrew/bin/python3.12",
        python_version="3.12-test",
        production_root_paths=(_RUNTIME_PATH,),
        imported_root_modules=(
            "trade_system.theory_paper_v2.infrastructure."
            "v31_successor_probe_store_v2",
        ),
        observed_project_python_paths=(_RUNTIME_PATH,),
        stderr_sha256=hashlib.sha256(b"").hexdigest(),
        stderr_empty=True,
    )
    trace_binding = _document_binding(
        "typed-support/fresh-process-trace.json",
        trace,
        "fresh_process_trace_digest",
    )
    runtime = build_v311_runtime_closure_receipt_v2(
        run_scope_id=run_id,
        frozen_at=frozen_at,
        production_root_paths=(_RUNTIME_PATH,),
        fresh_process_trace=trace,
        fresh_process_trace_binding=trace_binding,
        frozen_bindings={_RUNTIME_PATH: runtime_sha},
    )
    association = build_v31_association_preregistration_v2(
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    evaluation = build_v31_evaluation_contract_v2(
        association_preregistration=association,
        run_scope_id=run_id,
        frozen_at=frozen_at,
    )
    with patch.object(sentiment_fixture, "RUN_ID", run_id):
        dataset, registry, admission = sentiment_fixture._bundle(cycle=1)
    projection = build_v31_sentiment_native_projection_receipt_v2(
        projection_id=f"projection:{run_id}:1",
        pit_dataset=dataset,
        information_revision_registry=registry,
        cycle_source_admission=admission,
    )
    return {
        "clock_policy": dict(outcome_monitor_qualification["clock_policy"]),
        "supervisor_policy": build_v311_supervisor_policy_v2(),
        "runtime_closure": runtime,
        "sentiment_source_registry": dict(
            projection["native_source_registry"]
        ),
        "sentiment_projection": projection,
        "association_preregistration": association,
        "evaluation_contract": evaluation,
        "public_source_qualification": public_source_qualification,
        "outcome_monitor_qualification": outcome_monitor_qualification,
        "schema_compatibility": schema_compatibility,
    }
