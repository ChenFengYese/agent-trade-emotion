"""Production composition for the V3.1.1 successor qualification run.

This module is deliberately a thin, controller-owned layer over the existing
source, probe, monitor, and current-Codex durable replay workflows.  It has no
Agent callable, automation interface, account interface, order interface, or
paper/live execution path.

The four public actions are intentionally separate:

* acquire and seal one fresh official-public source qualification;
* execute and seal the ten local monitor/supervisor probes;
* seal an already-completed current-Codex cycle-one delivery;
* aggregate and replay the three receipts plus the official-schema replay.

The official-schema replay reads the already write-once OKX mark-price bytes
from the source qualification.  It never performs a second GET and never
claims to be an experiment outcome or monitor resolution.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

from ..application.v31_successor_qualification_v2 import (
    compose_fresh_public_source_qualification_v2,
    compose_monitor_runtime_qualification_v2,
    verify_fresh_public_source_qualification_durable_v2,
    verify_monitor_qualification_durable_v2,
)
from ..application.v311_codex_durable_qualification_v3 import (
    compose_current_codex_durable_qualification_v3,
    verify_current_codex_qualification_durable_v3,
)
from ..domain.contracts.canonical import (
    canonical_digest,
    load_json_strict,
    self_digest,
    verify_self_digest,
)
from ..domain.governance.v31_application_authority_projection_v2 import (
    project_v31_application_authority_chain_v2,
)
from ..domain.governance.v31_successor_qualification_v2 import (
    MONITOR_QUALIFICATION_DIGEST_FIELD,
    SOURCE_QUALIFICATION_DIGEST_FIELD,
)
from ..domain.governance.v311_codex_durable_qualification_v3 import (
    CODEX_QUALIFICATION_V3_DIGEST_FIELD,
)
from ..domain.governance.v311_successor_authority_envelope_v2 import (
    V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH,
)
from ..domain.v31_outcome_capture_v2 import (
    OKX_MARK_PRICE_URL,
    build_outcome_clock_policy,
    build_public_outcome_capture,
    parse_public_outcome_capture,
    verify_outcome_clock_policy,
    verify_public_outcome_parse_receipt,
)
from ..domain.v31_run_genesis import (
    RUN_GENESIS_DIGEST_FIELD,
    RUN_GENESIS_REF,
    verify_v31_run_genesis_receipt,
)
from ..infrastructure.v31_research_store import LocalV31ResearchStore
from ..infrastructure.v31_source_qualification_store import (
    LocalV31SourceQualificationStore,
)
from ..infrastructure.v31_successor_probe_store_v2 import (
    PERSISTED_RECEIPT_REF,
    execute_and_persist_successor_qualification_probes_v2,
    load_persisted_successor_qualification_probes_v2,
)
from ..application.v31_source_qualification import (
    verify_durable_v31_source_qualification_completion,
)
from .v31_source_qualification_composition import (
    execute_local_v31_source_qualification,
    initialize_local_v31_source_qualification,
)


class V311SuccessorQualificationCompositionV3Error(ValueError):
    """The production qualification composition failed closed."""


RECEIPT_ROOT = "qualification-receipts-v3"
PUBLIC_SOURCE_RECEIPT_REF = f"{RECEIPT_ROOT}/public-source-v2.json"
MONITOR_RECEIPT_REF = f"{RECEIPT_ROOT}/outcome-monitor-v2.json"
CODEX_RECEIPT_REF = f"{RECEIPT_ROOT}/codex-durable-delivery-v3.json"
SCHEMA_COMPATIBILITY_RECEIPT_REF = (
    f"{RECEIPT_ROOT}/outcome-schema-compatibility-v3.json"
)
QUALIFICATION_SET_RECEIPT_REF = f"{RECEIPT_ROOT}/qualification-set-v3.json"
SOURCE_QUALIFICATION_ROOT_NAME = "fresh-public-source-v2"

SCHEMA_COMPATIBILITY_SCHEMA_ID = (
    "theory_paper_v311_official_outcome_schema_compatibility_v3"
)
SCHEMA_COMPATIBILITY_DIGEST_FIELD = "schema_compatibility_receipt_digest"
QUALIFICATION_SET_SCHEMA_ID = "theory_paper_v311_successor_qualification_set_v3"
QUALIFICATION_SET_DIGEST_FIELD = "qualification_set_receipt_digest"
SCHEMA_VERSION = "3.0.0"

_MARK_REQUEST_ID = "okx-native-mark-price"
_OBSERVABLE_REF = "metric:mark-price-usdt"
_DOCUMENT_BINDING_FIELDS = frozenset(
    {
        "relative_ref",
        "schema_id",
        "digest_field",
        "semantic_digest",
        "physical_sha256",
    }
)
_STANDARD_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_BOUNDARY = {
    "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
    "external_execution_authority": "NONE_LOCAL_SIMULATION",
    "executable": False,
    "account_access": False,
    "paper_trading": False,
    "live_trading": False,
    "order_submission": False,
    "credential_use": False,
    "funds_access": False,
    "portfolio_mutation": False,
    "automation_created": False,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _time(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V311SuccessorQualificationCompositionV3Error(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V311SuccessorQualificationCompositionV3Error(code) from exc
    if parsed.tzinfo is None:
        raise V311SuccessorQualificationCompositionV3Error(code)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _relative_ref(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise V311SuccessorQualificationCompositionV3Error(code)
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise V311SuccessorQualificationCompositionV3Error(code)
    return value


def _contained_root(
    project_root: Path, relative_ref: str, *, allow_create: bool
) -> Path:
    try:
        project = Path(project_root).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_PROJECT_ROOT_INVALID"
        ) from exc
    if not project.is_dir():
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_PROJECT_ROOT_INVALID"
        )
    ref = _relative_ref(relative_ref, "V311_QUALIFICATION_PATH_INVALID")
    cursor = project
    for part in PurePosixPath(ref).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise V311SuccessorQualificationCompositionV3Error(
                "V311_QUALIFICATION_SYMLINK_FORBIDDEN"
            )
    if allow_create:
        cursor.mkdir(parents=True, exist_ok=True)
    try:
        root = cursor.resolve(strict=True)
        root.relative_to(project)
    except (OSError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_PATH_INVALID"
        ) from exc
    return root


def _full_binding(
    *, store: LocalV31ResearchStore, relative_ref: str, digest_field: str
) -> dict[str, str]:
    document = store.read_document(
        relative_ref=relative_ref, digest_field=digest_field
    )
    partial = store.artifact_binding(
        relative_ref=relative_ref,
        digest_field=digest_field,
        expected_semantic_digest=str(document[digest_field]),
    )
    return {
        "relative_ref": relative_ref,
        "schema_id": str(document["schema_id"]),
        "digest_field": digest_field,
        "semantic_digest": str(partial["semantic_digest"]),
        "physical_sha256": str(partial["physical_sha256"]),
    }


def _write_receipt(
    *,
    store: LocalV31ResearchStore,
    relative_ref: str,
    document: Mapping[str, Any],
    digest_field: str,
) -> dict[str, str]:
    store.write_document(
        relative_ref=relative_ref,
        document=document,
        digest_field=digest_field,
    )
    return _full_binding(
        store=store, relative_ref=relative_ref, digest_field=digest_field
    )


def _read_receipt(
    *, store: LocalV31ResearchStore, relative_ref: str, digest_field: str
) -> tuple[dict[str, Any], dict[str, str]]:
    try:
        document = dict(
            store.read_document(
                relative_ref=relative_ref, digest_field=digest_field
            )
        )
        binding = _full_binding(
            store=store, relative_ref=relative_ref, digest_field=digest_field
        )
    except (OSError, TypeError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_RECEIPT_REPLAY_INVALID"
        ) from exc
    return document, binding


def _document_exists(root: Path, relative_ref: str) -> bool:
    ref = _relative_ref(relative_ref, "V311_QUALIFICATION_PATH_INVALID")
    target = root.joinpath(*PurePosixPath(ref).parts)
    if target.is_symlink():
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SYMLINK_FORBIDDEN"
        )
    return target.is_file()


def _validated_context(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
) -> dict[str, Any]:
    """Revalidate standard V3 and its already-initialized run genesis."""

    try:
        projection = project_v31_application_authority_chain_v2(
            qualification_v3_chain
        )
        authority = dict(projection["authority"])
        authority_digest = verify_self_digest(authority, "authority_digest")
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_V3_CHAIN_INVALID"
        ) from exc
    binding = qualification_authority_binding
    if (
        not isinstance(binding, Mapping)
        or set(binding) != _STANDARD_BINDING_FIELDS
        or binding.get("path") != V311_QUALIFICATION_ACTIVE_AUTHORITY_PATH
        or binding.get("schema_id") != authority.get("schema_id")
        or binding.get("digest_field") != "authority_digest"
        or binding.get("semantic_digest") != authority_digest
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_AUTHORITY_BINDING_INVALID"
        )
    project = Path(project_root).resolve(strict=True)
    authority_path = project.joinpath(
        *PurePosixPath(str(binding["path"])).parts
    )
    try:
        authority_path.resolve(strict=True).relative_to(project)
        authority_payload = authority_path.read_bytes()
        loaded_authority = load_json_strict(authority_path)
    except (OSError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_AUTHORITY_PHYSICAL_INVALID"
        ) from exc
    if (
        authority_path.is_symlink()
        or loaded_authority != authority
        or hashlib.sha256(authority_payload).hexdigest()
        != binding.get("physical_sha256")
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_AUTHORITY_PHYSICAL_INVALID"
        )
    run_id = authority.get("authorized_run_id")
    expected_root_ref = f"agent-cluster/experiments/{run_id}"
    if (
        qualification_run_root_ref != expected_root_ref
        or authority.get("experiment_start_authorized") is not True
        or not str(authority.get("status") or "").startswith("ACTIVE_")
        or authority.get("external_execution_authority")
        != "NONE_LOCAL_SIMULATION"
        or authority.get("executable") is not False
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_RUN_AUTHORITY_INVALID"
        )
    run_root = _contained_root(
        project, qualification_run_root_ref, allow_create=False
    )
    run_store = LocalV31ResearchStore(run_root)
    try:
        genesis = dict(
            run_store.read_document(
                relative_ref=RUN_GENESIS_REF,
                digest_field=RUN_GENESIS_DIGEST_FIELD,
            )
        )
        documents = {
            "theory_approval": projection["theory_approval"],
            "experiment_contract": projection["experiment_contract"],
            "experiment_manifest": projection["manifest"],
            "experiment_authorization": projection["authorization_receipt"],
            "current_authority": authority,
        }
        global_bindings = {
            "theory_approval": authority["theory_approval_binding"],
            "experiment_contract": authority["experiment_contract_binding"],
            "experiment_manifest": authority["manifest_binding"],
            "experiment_authorization": authority[
                "authorization_receipt_binding"
            ],
            "current_authority": dict(binding),
        }
        verify_v31_run_genesis_receipt(
            genesis, documents=documents, global_bindings=global_bindings
        )
        rows = [
            row
            for row in genesis["genesis_artifacts"]
            if row.get("source_role") == "current_authority"
        ]
        if len(rows) != 1:
            raise ValueError("current authority copy missing")
        row = rows[0]
        local_binding = {
            "relative_ref": str(row["local_ref"]),
            "schema_id": str(row["schema_id"]),
            "digest_field": str(row["digest_field"]),
            "semantic_digest": str(row["semantic_digest"]),
            "physical_sha256": str(row["local_physical_sha256"]),
        }
        local_authority = dict(
            run_store.read_document(
                relative_ref=local_binding["relative_ref"],
                digest_field="authority_digest",
                expected_semantic_digest=authority_digest,
            )
        )
        actual_local = _full_binding(
            store=run_store,
            relative_ref=local_binding["relative_ref"],
            digest_field="authority_digest",
        )
        genesis_binding = _full_binding(
            store=run_store,
            relative_ref=RUN_GENESIS_REF,
            digest_field=RUN_GENESIS_DIGEST_FIELD,
        )
        local_payload = run_root.joinpath(
            *PurePosixPath(local_binding["relative_ref"]).parts
        ).read_bytes()
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_RUN_GENESIS_INVALID"
        ) from exc
    if (
        local_authority != authority
        or actual_local != local_binding
        or local_payload != authority_payload
        or row.get("global_ref") != binding["path"]
        or row.get("global_physical_sha256") != binding["physical_sha256"]
        or row.get("exact_bytes_copied") is not True
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_RUN_GENESIS_AUTHORITY_DRIFT"
        )
    return {
        "project": project,
        "run_root": run_root,
        "run_root_ref": qualification_run_root_ref,
        "run_id": str(run_id),
        "authority": authority,
        "authority_digest": authority_digest,
        "authority_binding": local_binding,
        "standard_authority_binding": dict(binding),
        "run_genesis_binding": genesis_binding,
    }


def _project_binding(
    binding: Mapping[str, Any], *, run_root_ref: str
) -> dict[str, str]:
    if not isinstance(binding, Mapping) or set(binding) != _DOCUMENT_BINDING_FIELDS:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_BINDING_INVALID"
        )
    return {
        "path": PurePosixPath(run_root_ref, str(binding["relative_ref"])).as_posix(),
        "schema_id": str(binding["schema_id"]),
        "digest_field": str(binding["digest_field"]),
        "semantic_digest": str(binding["semantic_digest"]),
        "physical_sha256": str(binding["physical_sha256"]),
    }


def initialize_execute_and_seal_public_source_qualification_v3(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
    predecessor_run_id: str,
    qualification_id: str,
) -> dict[str, Any]:
    """Perform at most one fixed public collection and seal source-v2 evidence."""

    context = _validated_context(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
    )
    store = LocalV31ResearchStore(context["run_root"])
    if _document_exists(context["run_root"], PUBLIC_SOURCE_RECEIPT_REF):
        receipt, binding = _read_receipt(
            store=store,
            relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
            digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
        )
        verify_fresh_public_source_qualification_durable_v2(
            project_root=context["project"],
            authority=context["authority"],
            validated_authority_digest=context["authority_digest"],
            document=receipt,
        )
        return {
            "qualification": receipt,
            "binding": binding,
            "source_execution": "SEALED_REPLAY_NO_GET",
            "collector_called_this_invocation": False,
            "authority_copy_binding": context["authority_binding"],
            "standard_authority_binding": context[
                "standard_authority_binding"
            ],
            "run_genesis_binding": context["run_genesis_binding"],
        }

    source_root_ref = PurePosixPath(
        context["run_root_ref"], SOURCE_QUALIFICATION_ROOT_NAME
    ).as_posix()
    source_root = _contained_root(
        context["project"], source_root_ref, allow_create=True
    )
    checkpoint = source_root / "qualification-checkpoint.json"
    if not checkpoint.exists():
        initialize_local_v31_source_qualification(
            qualification_root=source_root, qualification_id=qualification_id
        )
    execution = execute_local_v31_source_qualification(
        qualification_root=source_root, qualification_id=qualification_id
    )
    if execution.get("status") != "SEALED":
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_PUBLIC_SOURCE_NOT_SEALED"
        )
    source_store = LocalV31SourceQualificationStore(source_root)
    replay = verify_durable_v31_source_qualification_completion(
        store=source_store,
        qualification_id=qualification_id,
    )
    snapshot_binding = replay["completion"]["snapshot_binding"]
    snapshot = source_store.read_document(
        relative_ref=str(snapshot_binding["relative_ref"]),
        digest_field="native_market_snapshot_digest",
        expected_semantic_digest=str(snapshot_binding["semantic_digest"]),
    )
    fresh = max(
        _time(row["response_received_at"], "V311_PUBLIC_SOURCE_TIME_INVALID")
        for row in snapshot["source_captures"]
    )
    qualified_at = _utc_now()
    qualified = _time(qualified_at, "V311_PUBLIC_SOURCE_TIME_INVALID")
    expires = fresh + timedelta(hours=1)
    if qualified >= expires:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_PUBLIC_SOURCE_EXPIRED_BEFORE_SEAL"
        )
    receipt = compose_fresh_public_source_qualification_v2(
        project_root=context["project"],
        qualification_root_ref=source_root_ref,
        qualification_id=qualification_id,
        run_id=context["run_id"],
        predecessor_run_id=predecessor_run_id,
        authority=context["authority"],
        authority_binding=context["authority_binding"],
        validated_authority_digest=context["authority_digest"],
        qualified_at=qualified_at,
        expires_at=_iso(expires),
    )
    binding = _write_receipt(
        store=store,
        relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
        document=receipt,
        digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
    )
    verify_fresh_public_source_qualification_durable_v2(
        project_root=context["project"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=receipt,
    )
    return {
        "qualification": receipt,
        "binding": binding,
        "source_execution": dict(execution),
        "collector_called_this_invocation": execution.get(
            "collector_called_this_invocation"
        ),
        "authority_copy_binding": context["authority_binding"],
        "standard_authority_binding": context["standard_authority_binding"],
        "run_genesis_binding": context["run_genesis_binding"],
    }


def _content_type(capture: Mapping[str, Any]) -> str:
    headers = capture.get("selected_response_headers")
    if not isinstance(headers, list):
        return ""
    for row in headers:
        if (
            isinstance(row, Mapping)
            and str(row.get("name", "")).casefold() == "content-type"
            and isinstance(row.get("value"), str)
        ):
            return str(row["value"])
    return ""


def _equivalent_mark_locator(actual_url: str) -> bool:
    actual = urlsplit(actual_url)
    expected = urlsplit(OKX_MARK_PRICE_URL)
    try:
        actual_query = parse_qsl(
            actual.query, keep_blank_values=True, strict_parsing=True
        )
        expected_query = parse_qsl(
            expected.query, keep_blank_values=True, strict_parsing=True
        )
    except ValueError:
        return False
    return (
        actual.scheme == expected.scheme == "https"
        and actual.netloc == expected.netloc
        and actual.path == expected.path
        and not actual.fragment
        and sorted(actual_query) == sorted(expected_query)
        and len(actual_query) == len({name for name, _value in actual_query})
    )


def _build_schema_compatibility_receipt(
    *,
    project_root: Path,
    source_qualification: Mapping[str, Any],
    clock_policy: Mapping[str, Any],
    sealed_at: str,
) -> dict[str, Any]:
    source_digest = verify_self_digest(
        source_qualification, SOURCE_QUALIFICATION_DIGEST_FIELD
    )
    clock_digest = verify_outcome_clock_policy(clock_policy)
    source_root_ref = _relative_ref(
        source_qualification.get("qualification_root_ref"),
        "V311_SCHEMA_SOURCE_ROOT_INVALID",
    )
    project = Path(project_root).resolve(strict=True)
    try:
        source_root = project.joinpath(
            *PurePosixPath(source_root_ref).parts
        ).resolve(strict=True)
        source_root.relative_to(project)
    except (OSError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_ROOT_INVALID"
        ) from exc
    if not source_root.is_dir() or source_root.is_symlink():
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_ROOT_INVALID"
        )
    store = LocalV31SourceQualificationStore(source_root)
    completion = source_qualification.get("completion")
    snapshot = source_qualification.get("snapshot")
    if not isinstance(completion, Mapping) or not isinstance(snapshot, Mapping):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_DOCUMENT_INVALID"
        )
    raw_binding = completion.get("raw_bindings", {}).get(_MARK_REQUEST_ID)
    captures = snapshot.get("source_captures")
    if not isinstance(raw_binding, Mapping) or not isinstance(captures, list):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_MARK_BINDING_INVALID"
        )
    matches = [row for row in captures if row.get("request_id") == _MARK_REQUEST_ID]
    if len(matches) != 1 or not isinstance(matches[0], Mapping):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_MARK_CAPTURE_INVALID"
        )
    source_capture = dict(matches[0])
    try:
        raw = store.read_raw(
            relative_ref=str(raw_binding["relative_ref"]),
            expected_sha256=str(raw_binding["semantic_digest"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_MARK_RAW_INVALID"
        ) from exc
    raw_digest = hashlib.sha256(raw).hexdigest()
    if (
        raw_digest != raw_binding.get("physical_sha256")
        or raw_digest != source_capture.get("raw_body_sha256")
        or raw_digest != raw_binding.get("semantic_digest")
        or source_capture.get("http_status") != 200
        or not _equivalent_mark_locator(str(source_capture.get("final_url") or ""))
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_MARK_LINEAGE_INVALID"
        )
    started = _time(
        source_capture.get("request_started_at"),
        "V311_SCHEMA_SOURCE_CAPTURE_TIME_INVALID",
    )
    received = _time(
        source_capture.get("response_received_at"),
        "V311_SCHEMA_SOURCE_CAPTURE_TIME_INVALID",
    )
    elapsed = int((received - started).total_seconds() * 1_000)
    if elapsed < 0 or elapsed > 60_000:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_SOURCE_CAPTURE_TIME_INVALID"
        )
    capture = build_public_outcome_capture(
        run_id=str(source_qualification["run_id"]),
        cycle_index=1,
        monitor_plan_digest=source_digest,
        monitor_attempt_digest=canonical_digest(
            {
                "purpose": "SOURCE_SCHEMA_COMPATIBILITY_ONLY",
                "source_capture_record_digest": source_capture["record_digest"],
                "raw_sha256": raw_digest,
            }
        ),
        source_request_id=str(source_capture["request_id"]),
        requested_at=str(source_capture["request_started_at"]),
        request_started_at=str(source_capture["request_started_at"]),
        response_received_at=str(source_capture["response_received_at"]),
        monotonic_elapsed_ms=elapsed,
        status_code=int(source_capture["http_status"]),
        content_type=_content_type(source_capture),
        # The source collector canonicalizes query pairs lexicographically,
        # while the frozen outcome adapter freezes the same pairs in another
        # order.  Exact source URL is retained below and equivalence is proved.
        final_url=OKX_MARK_PRICE_URL,
        raw_payload=raw,
    )
    parsed = parse_public_outcome_capture(
        capture=capture,
        raw_payload=raw,
        clock_policy=clock_policy,
        observable_ref=_OBSERVABLE_REF,
    )
    if parsed["parse_status"] == "ADMITTED_OBSERVED":
        verdict = "SCHEMA_COMPATIBLE_NOT_OUTCOME"
    elif (
        parsed["parse_status"] == "ADMITTED_UNKNOWN"
        and parsed["error_code"] == "CLOCK_BOUND_EXCEEDED"
    ):
        verdict = "SCHEMA_COMPATIBLE_CLOCK_NOT_OUTCOME"
    else:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_OFFICIAL_SCHEMA_INCOMPATIBLE_WITH_FROZEN_OUTCOME_ADAPTER"
        )
    sealed = _time(sealed_at, "V311_SCHEMA_COMPATIBILITY_SEALED_AT_INVALID")
    if sealed < received:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_COMPATIBILITY_SEALED_AT_INVALID"
        )
    document = {
        "schema_id": SCHEMA_COMPATIBILITY_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": source_qualification["run_id"],
        "qualification_id": source_qualification["qualification_id"],
        "sealed_at": sealed_at,
        "source_qualification_v2_digest": source_digest,
        "source_qualification_root_ref": source_root_ref,
        "clock_policy_digest": clock_digest,
        "source_raw_binding": dict(raw_binding),
        "source_capture_record_digest": source_capture["record_digest"],
        "source_transport": {
            "request_id": source_capture["request_id"],
            "method": source_capture["method"],
            "final_url": source_capture["final_url"],
            "http_status": source_capture["http_status"],
            "content_type": _content_type(source_capture),
            "request_started_at": source_capture["request_started_at"],
            "response_received_at": source_capture["response_received_at"],
            "raw_body_sha256": raw_digest,
            "raw_body_byte_length": len(raw),
        },
        "frozen_parser_projection": {
            "request_url": OKX_MARK_PRICE_URL,
            "final_url": OKX_MARK_PRICE_URL,
            "locator_relation": "EXACT_ENDPOINT_AND_QUERY_SET_ORDER_NORMALIZED",
            "source_url_preserved_separately": True,
            "transport_claim": "SCHEMA_REPLAY_ONLY_NOT_A_SECOND_REQUEST",
        },
        "capture": capture,
        "parse_receipt": parsed,
        "verdict": verdict,
        "schema_compatible": True,
        "outcome_admitted": False,
        "monitor_resolution_created": False,
        "historical_source_replay": True,
        "additional_network_get_count": 0,
        "limitations": [
            "OFFICIAL_RESPONSE_SCHEMA_COMPATIBILITY_ONLY",
            "NOT_AN_EXPERIMENT_OUTCOME",
            "NOT_A_PROVIDER_AVAILABILITY_GUARANTEE",
            "QUERY_ORDER_NORMALIZED_WITH_EXACT_SOURCE_URL_RETAINED",
        ],
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, SCHEMA_COMPATIBILITY_DIGEST_FIELD)


def verify_official_outcome_schema_compatibility_v3(
    *,
    project_root: Path,
    source_qualification: Mapping[str, Any],
    clock_policy: Mapping[str, Any],
    document: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(document, SCHEMA_COMPATIBILITY_DIGEST_FIELD)
        rebuilt = _build_schema_compatibility_receipt(
            project_root=project_root,
            source_qualification=source_qualification,
            clock_policy=clock_policy,
            sealed_at=str(document["sealed_at"]),
        )
        verify_public_outcome_parse_receipt(
            document["parse_receipt"],
            capture=document["capture"],
            raw_payload=LocalV31SourceQualificationStore(
                Path(project_root)
                / str(source_qualification["qualification_root_ref"])
            ).read_raw(
                relative_ref=str(document["source_raw_binding"]["relative_ref"]),
                expected_sha256=str(
                    document["source_raw_binding"]["semantic_digest"]
                ),
            ),
            clock_policy=clock_policy,
            observable_ref=_OBSERVABLE_REF,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        if isinstance(exc, V311SuccessorQualificationCompositionV3Error):
            raise
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_COMPATIBILITY_REPLAY_INVALID"
        ) from exc
    if rebuilt != dict(document) or supplied != rebuilt[SCHEMA_COMPATIBILITY_DIGEST_FIELD]:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_SCHEMA_COMPATIBILITY_REPLAY_MISMATCH"
        )
    return supplied


def execute_and_seal_monitor_qualification_v3(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
    predecessor_run_id: str,
    production_root_paths: Sequence[str],
    trace_paths: Sequence[str],
    runtime_closure_bindings: Mapping[str, str],
    clock_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the ten local probes and seal monitor-v2 plus schema replay."""

    context = _validated_context(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
    )
    store = LocalV31ResearchStore(context["run_root"])
    source, _source_binding = _read_receipt(
        store=store,
        relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
        digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
    )
    verify_fresh_public_source_qualification_durable_v2(
        project_root=context["project"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=source,
    )
    if (
        _document_exists(context["run_root"], MONITOR_RECEIPT_REF)
        and _document_exists(context["run_root"], SCHEMA_COMPATIBILITY_RECEIPT_REF)
    ):
        monitor, monitor_binding = _read_receipt(
            store=store,
            relative_ref=MONITOR_RECEIPT_REF,
            digest_field=MONITOR_QUALIFICATION_DIGEST_FIELD,
        )
        compatibility, compatibility_binding = _read_receipt(
            store=store,
            relative_ref=SCHEMA_COMPATIBILITY_RECEIPT_REF,
            digest_field=SCHEMA_COMPATIBILITY_DIGEST_FIELD,
        )
        verify_monitor_qualification_durable_v2(
            run_root=context["run_root"], document=monitor
        )
        verify_official_outcome_schema_compatibility_v3(
            project_root=context["project"],
            source_qualification=source,
            clock_policy=monitor["clock_policy"],
            document=compatibility,
        )
        return {
            "qualification": monitor,
            "binding": monitor_binding,
            "schema_compatibility": compatibility,
            "schema_compatibility_binding": compatibility_binding,
            "probe_execution": "SEALED_REPLAY_NO_PROBE_RERUN",
            "network_get_count": 0,
        }

    policy = dict(clock_policy or build_outcome_clock_policy())
    verify_outcome_clock_policy(policy)
    if _document_exists(context["run_root"], PERSISTED_RECEIPT_REF):
        probes = load_persisted_successor_qualification_probes_v2(
            output_root=context["run_root"]
        )
        probe_execution = "PERSISTED_REPLAY_NO_PROBE_RERUN"
    else:
        probes = execute_and_persist_successor_qualification_probes_v2(
            project_root=context["project"],
            output_root=context["run_root"],
            executed_at=_utc_now(),
            production_root_paths=production_root_paths,
            trace_paths=trace_paths,
            runtime_closure_bindings=runtime_closure_bindings,
            clock_policy=policy,
        )
        probe_execution = "TEN_EXECUTED_LOCAL_FAILURE_INJECTION_CASES"
    if probes["clock_policy"] != policy:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_MONITOR_CLOCK_POLICY_MISMATCH"
        )
    compatibility = _build_schema_compatibility_receipt(
        project_root=context["project"],
        source_qualification=source,
        clock_policy=policy,
        sealed_at=_utc_now(),
    )
    compatibility_binding = _write_receipt(
        store=store,
        relative_ref=SCHEMA_COMPATIBILITY_RECEIPT_REF,
        document=compatibility,
        digest_field=SCHEMA_COMPATIBILITY_DIGEST_FIELD,
    )
    bindings = probes["receipt"]["artifact_bindings"]
    monitor = compose_monitor_runtime_qualification_v2(
        run_id=context["run_id"],
        predecessor_run_id=predecessor_run_id,
        authority=context["authority"],
        authority_binding=context["authority_binding"],
        validated_authority_digest=context["authority_digest"],
        qualified_at=_utc_now(),
        clock_policy=policy,
        clock_policy_binding=bindings["clock_policy"],
        raw_first_probe=probes["raw_first_probe"],
        raw_first_probe_binding=bindings["raw_first_probe"],
        supervisor_probe=probes["supervisor_probe"],
        supervisor_probe_binding=bindings["supervisor_probe"],
    )
    monitor_binding = _write_receipt(
        store=store,
        relative_ref=MONITOR_RECEIPT_REF,
        document=monitor,
        digest_field=MONITOR_QUALIFICATION_DIGEST_FIELD,
    )
    verify_monitor_qualification_durable_v2(
        run_root=context["run_root"], document=monitor
    )
    verify_official_outcome_schema_compatibility_v3(
        project_root=context["project"],
        source_qualification=source,
        clock_policy=policy,
        document=compatibility,
    )
    return {
        "qualification": monitor,
        "binding": monitor_binding,
        "schema_compatibility": compatibility,
        "schema_compatibility_binding": compatibility_binding,
        "probe_execution": probe_execution,
        "network_get_count": 0,
    }


def seal_completed_codex_cycle1_qualification_v3(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
    predecessor_run_id: str,
) -> dict[str, Any]:
    """Seal an already-completed current-Codex cycle one; never invoke an Agent."""

    context = _validated_context(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
    )
    store = LocalV31ResearchStore(context["run_root"])
    if _document_exists(context["run_root"], CODEX_RECEIPT_REF):
        receipt, binding = _read_receipt(
            store=store,
            relative_ref=CODEX_RECEIPT_REF,
            digest_field=CODEX_QUALIFICATION_V3_DIGEST_FIELD,
        )
        verify_current_codex_qualification_durable_v3(
            project_root=context["project"],
            run_root_ref=context["run_root_ref"],
            authority=context["authority"],
            validated_authority_digest=context["authority_digest"],
            document=receipt,
        )
        return {
            "qualification": receipt,
            "binding": binding,
            "agent_invoked": False,
            "status": "SEALED_REPLAY_NO_AGENT_CALL",
        }
    source, _source_binding = _read_receipt(
        store=store,
        relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
        digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
    )
    verify_fresh_public_source_qualification_durable_v2(
        project_root=context["project"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=source,
    )
    receipt = compose_current_codex_durable_qualification_v3(
        project_root=context["project"],
        run_root_ref=context["run_root_ref"],
        run_id=context["run_id"],
        predecessor_run_id=predecessor_run_id,
        cycle_index=1,
        authority=context["authority"],
        authority_binding=context["authority_binding"],
        validated_authority_digest=context["authority_digest"],
        source_qualification_v2_digest=source[SOURCE_QUALIFICATION_DIGEST_FIELD],
        qualified_at=_utc_now(),
    )
    binding = _write_receipt(
        store=store,
        relative_ref=CODEX_RECEIPT_REF,
        document=receipt,
        digest_field=CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    )
    verify_current_codex_qualification_durable_v3(
        project_root=context["project"],
        run_root_ref=context["run_root_ref"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=receipt,
    )
    return {
        "qualification": receipt,
        "binding": binding,
        "agent_invoked": False,
        "status": "SEALED_FROM_COMPLETED_CYCLE1",
    }


def _build_qualification_set_receipt(
    *,
    context: Mapping[str, Any],
    predecessor_run_id: str,
    sealed_at: str,
    receipt_bindings: Mapping[str, Mapping[str, Any]],
    receipt_digests: Mapping[str, str],
    schema_compatibility_binding: Mapping[str, Any],
    schema_compatibility_digest: str,
) -> dict[str, Any]:
    expected_names = ("public_source", "codex_durable_delivery", "outcome_monitor")
    if tuple(receipt_bindings) != expected_names or tuple(receipt_digests) != expected_names:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_RECEIPTS_INVALID"
        )
    for binding in (*receipt_bindings.values(), schema_compatibility_binding):
        if not isinstance(binding, Mapping) or set(binding) != _DOCUMENT_BINDING_FIELDS:
            raise V311SuccessorQualificationCompositionV3Error(
                "V311_QUALIFICATION_SET_BINDING_INVALID"
            )
    _time(sealed_at, "V311_QUALIFICATION_SET_TIME_INVALID")
    document = {
        "schema_id": QUALIFICATION_SET_SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "run_id": context["run_id"],
        "predecessor_run_id": predecessor_run_id,
        "qualification_run_root_ref": context["run_root_ref"],
        "authority_digest": context["authority_digest"],
        "authority_binding": dict(context["authority_binding"]),
        "standard_authority_binding": dict(
            context["standard_authority_binding"]
        ),
        "run_genesis_binding": dict(context["run_genesis_binding"]),
        "sealed_at": sealed_at,
        "receipt_bindings": {name: dict(receipt_bindings[name]) for name in expected_names},
        "receipt_digests": {name: receipt_digests[name] for name in expected_names},
        "schema_compatibility_binding": dict(schema_compatibility_binding),
        "schema_compatibility_digest": schema_compatibility_digest,
        "qualification_cardinality": {
            "public_source": 1,
            "codex_cycle": 1,
            "raw_first_probe_cases": 6,
            "supervisor_probe_cases": 4,
            "official_schema_raw_replays": 1,
            "additional_schema_network_gets": 0,
        },
        "agent_callable_accepted": False,
        "outcome_read": False,
        "accepted_cycle_monitor_scheduled": True,
        "monitor_supersession_required_before_target_authority": True,
        "authority_boundary": dict(_BOUNDARY),
    }
    return self_digest(document, QUALIFICATION_SET_DIGEST_FIELD)


def verify_successor_qualification_set_receipt_v3(
    document: Mapping[str, Any],
) -> str:
    try:
        supplied = verify_self_digest(document, QUALIFICATION_SET_DIGEST_FIELD)
    except (TypeError, ValueError) as exc:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_RECEIPT_INVALID"
        ) from exc
    expected = {
        "schema_id",
        "schema_version",
        "run_id",
        "predecessor_run_id",
        "qualification_run_root_ref",
        "authority_digest",
        "authority_binding",
        "standard_authority_binding",
        "run_genesis_binding",
        "sealed_at",
        "receipt_bindings",
        "receipt_digests",
        "schema_compatibility_binding",
        "schema_compatibility_digest",
        "qualification_cardinality",
        "agent_callable_accepted",
        "outcome_read",
        "accepted_cycle_monitor_scheduled",
        "monitor_supersession_required_before_target_authority",
        "authority_boundary",
        QUALIFICATION_SET_DIGEST_FIELD,
    }
    if (
        set(document) != expected
        or document.get("schema_id") != QUALIFICATION_SET_SCHEMA_ID
        or document.get("schema_version") != SCHEMA_VERSION
        or document.get("agent_callable_accepted") is not False
        or document.get("outcome_read") is not False
        or document.get("accepted_cycle_monitor_scheduled") is not True
        or document.get("monitor_supersession_required_before_target_authority")
        is not True
        or document.get("authority_boundary") != _BOUNDARY
        or document.get("qualification_cardinality")
        != {
            "public_source": 1,
            "codex_cycle": 1,
            "raw_first_probe_cases": 6,
            "supervisor_probe_cases": 4,
            "official_schema_raw_replays": 1,
            "additional_schema_network_gets": 0,
        }
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_RECEIPT_INVALID"
        )
    _time(document.get("sealed_at"), "V311_QUALIFICATION_SET_TIME_INVALID")
    return supplied


def seal_successor_qualification_set_v3(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
    predecessor_run_id: str,
) -> dict[str, Any]:
    """Bind the three envelope receipts and the schema replay write-once."""

    context = _validated_context(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
    )
    if _document_exists(context["run_root"], QUALIFICATION_SET_RECEIPT_REF):
        return load_successor_qualification_set_v3(
            project_root=project_root,
            qualification_v3_chain=qualification_v3_chain,
            qualification_authority_binding=qualification_authority_binding,
            qualification_run_root_ref=qualification_run_root_ref,
            predecessor_run_id=predecessor_run_id,
        )
    store = LocalV31ResearchStore(context["run_root"])
    source, source_binding = _read_receipt(
        store=store,
        relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
        digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
    )
    codex, codex_binding = _read_receipt(
        store=store,
        relative_ref=CODEX_RECEIPT_REF,
        digest_field=CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    )
    monitor, monitor_binding = _read_receipt(
        store=store,
        relative_ref=MONITOR_RECEIPT_REF,
        digest_field=MONITOR_QUALIFICATION_DIGEST_FIELD,
    )
    compatibility, compatibility_binding = _read_receipt(
        store=store,
        relative_ref=SCHEMA_COMPATIBILITY_RECEIPT_REF,
        digest_field=SCHEMA_COMPATIBILITY_DIGEST_FIELD,
    )
    bindings = {
        "public_source": source_binding,
        "codex_durable_delivery": codex_binding,
        "outcome_monitor": monitor_binding,
    }
    digests = {
        "public_source": source[SOURCE_QUALIFICATION_DIGEST_FIELD],
        "codex_durable_delivery": codex[CODEX_QUALIFICATION_V3_DIGEST_FIELD],
        "outcome_monitor": monitor[MONITOR_QUALIFICATION_DIGEST_FIELD],
    }
    receipt = _build_qualification_set_receipt(
        context=context,
        predecessor_run_id=predecessor_run_id,
        sealed_at=_utc_now(),
        receipt_bindings=bindings,
        receipt_digests=digests,
        schema_compatibility_binding=compatibility_binding,
        schema_compatibility_digest=compatibility[
            SCHEMA_COMPATIBILITY_DIGEST_FIELD
        ],
    )
    _write_receipt(
        store=store,
        relative_ref=QUALIFICATION_SET_RECEIPT_REF,
        document=receipt,
        digest_field=QUALIFICATION_SET_DIGEST_FIELD,
    )
    return load_successor_qualification_set_v3(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
        predecessor_run_id=predecessor_run_id,
    )


def load_successor_qualification_set_v3(
    *,
    project_root: Path,
    qualification_v3_chain: Mapping[str, Any],
    qualification_authority_binding: Mapping[str, Any],
    qualification_run_root_ref: str,
    predecessor_run_id: str,
) -> dict[str, Any]:
    """Physically replay the authority copy, all receipts, probes, and raw bytes."""

    context = _validated_context(
        project_root=project_root,
        qualification_v3_chain=qualification_v3_chain,
        qualification_authority_binding=qualification_authority_binding,
        qualification_run_root_ref=qualification_run_root_ref,
    )
    store = LocalV31ResearchStore(context["run_root"])
    manifest, manifest_binding = _read_receipt(
        store=store,
        relative_ref=QUALIFICATION_SET_RECEIPT_REF,
        digest_field=QUALIFICATION_SET_DIGEST_FIELD,
    )
    verify_successor_qualification_set_receipt_v3(manifest)
    if (
        manifest.get("run_id") != context["run_id"]
        or manifest.get("predecessor_run_id") != predecessor_run_id
        or manifest.get("qualification_run_root_ref") != context["run_root_ref"]
        or manifest.get("authority_digest") != context["authority_digest"]
        or manifest.get("authority_binding") != context["authority_binding"]
        or manifest.get("standard_authority_binding")
        != context["standard_authority_binding"]
        or manifest.get("run_genesis_binding")
        != context["run_genesis_binding"]
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_CONTEXT_MISMATCH"
        )
    source, source_binding = _read_receipt(
        store=store,
        relative_ref=PUBLIC_SOURCE_RECEIPT_REF,
        digest_field=SOURCE_QUALIFICATION_DIGEST_FIELD,
    )
    codex, codex_binding = _read_receipt(
        store=store,
        relative_ref=CODEX_RECEIPT_REF,
        digest_field=CODEX_QUALIFICATION_V3_DIGEST_FIELD,
    )
    monitor, monitor_binding = _read_receipt(
        store=store,
        relative_ref=MONITOR_RECEIPT_REF,
        digest_field=MONITOR_QUALIFICATION_DIGEST_FIELD,
    )
    compatibility, compatibility_binding = _read_receipt(
        store=store,
        relative_ref=SCHEMA_COMPATIBILITY_RECEIPT_REF,
        digest_field=SCHEMA_COMPATIBILITY_DIGEST_FIELD,
    )
    verify_fresh_public_source_qualification_durable_v2(
        project_root=context["project"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=source,
    )
    verify_current_codex_qualification_durable_v3(
        project_root=context["project"],
        run_root_ref=context["run_root_ref"],
        authority=context["authority"],
        validated_authority_digest=context["authority_digest"],
        document=codex,
    )
    verify_monitor_qualification_durable_v2(
        run_root=context["run_root"], document=monitor
    )
    verify_official_outcome_schema_compatibility_v3(
        project_root=context["project"],
        source_qualification=source,
        clock_policy=monitor["clock_policy"],
        document=compatibility,
    )
    bindings = {
        "public_source": source_binding,
        "codex_durable_delivery": codex_binding,
        "outcome_monitor": monitor_binding,
    }
    digests = {
        "public_source": source[SOURCE_QUALIFICATION_DIGEST_FIELD],
        "codex_durable_delivery": codex[CODEX_QUALIFICATION_V3_DIGEST_FIELD],
        "outcome_monitor": monitor[MONITOR_QUALIFICATION_DIGEST_FIELD],
    }
    if (
        codex.get("source_qualification_v2_digest") != digests["public_source"]
        or compatibility.get("source_qualification_v2_digest")
        != digests["public_source"]
        or manifest.get("receipt_bindings") != bindings
        or manifest.get("receipt_digests") != digests
        or manifest.get("schema_compatibility_binding") != compatibility_binding
        or manifest.get("schema_compatibility_digest")
        != compatibility[SCHEMA_COMPATIBILITY_DIGEST_FIELD]
    ):
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_CROSS_BINDING_INVALID"
        )
    rebuilt = _build_qualification_set_receipt(
        context=context,
        predecessor_run_id=predecessor_run_id,
        sealed_at=str(manifest["sealed_at"]),
        receipt_bindings=bindings,
        receipt_digests=digests,
        schema_compatibility_binding=compatibility_binding,
        schema_compatibility_digest=compatibility[
            SCHEMA_COMPATIBILITY_DIGEST_FIELD
        ],
    )
    if rebuilt != manifest:
        raise V311SuccessorQualificationCompositionV3Error(
            "V311_QUALIFICATION_SET_REPLAY_MISMATCH"
        )
    return {
        "manifest": manifest,
        "manifest_binding": manifest_binding,
        "qualifications": {
            "public_source": source,
            "codex_durable_delivery": codex,
            "outcome_monitor": monitor,
        },
        "qualification_bindings": {
            name: _project_binding(binding, run_root_ref=context["run_root_ref"])
            for name, binding in bindings.items()
        },
        "schema_compatibility": compatibility,
        "schema_compatibility_binding": _project_binding(
            compatibility_binding, run_root_ref=context["run_root_ref"]
        ),
        "authority_copy_binding": context["authority_binding"],
        "standard_authority_binding": context["standard_authority_binding"],
        "run_genesis_binding": context["run_genesis_binding"],
        "network_get_count_during_replay": 0,
        "agent_invoked_during_replay": False,
        "outcome_read": False,
    }


__all__ = [
    "CODEX_RECEIPT_REF",
    "MONITOR_RECEIPT_REF",
    "PUBLIC_SOURCE_RECEIPT_REF",
    "QUALIFICATION_SET_DIGEST_FIELD",
    "QUALIFICATION_SET_RECEIPT_REF",
    "SCHEMA_COMPATIBILITY_DIGEST_FIELD",
    "SCHEMA_COMPATIBILITY_RECEIPT_REF",
    "V311SuccessorQualificationCompositionV3Error",
    "execute_and_seal_monitor_qualification_v3",
    "initialize_execute_and_seal_public_source_qualification_v3",
    "load_successor_qualification_set_v3",
    "seal_completed_codex_cycle1_qualification_v3",
    "seal_successor_qualification_set_v3",
    "verify_official_outcome_schema_compatibility_v3",
    "verify_successor_qualification_set_receipt_v3",
]
