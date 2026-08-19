"""Identity-gated dependency composition for the shared market-cycle route."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
from pathlib import PurePosixPath
import stat
import threading
from typing import Any, Iterator, Mapping

from ...application.market_cycle.data_profiles import (
    AssetDataProfileMarketDataAdapter,
)
from ...application.market_cycle.agent_session import AgentSessionService
from ...application.market_cycle.attention import (
    AttentionApplicationError,
    AttentionService,
)
from ...application.market_cycle.paper import replay_paper_account
from ...application.market_cycle.ports import ClockPort, MarketDataPort
from ...application.market_cycle.service import AdvanceResult, CycleService
from ...domain.contracts.canonical import (
    CanonicalContractError,
    canonical_bytes,
    canonical_digest,
    loads_json_strict,
)
from ...domain.market_cycle.attention import (
    AgentRegistry,
    AttentionContractError,
    AttentionRequest,
    GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID,
    GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION,
    GoalAttentionCheckpointV1,
)
from ...domain.market_cycle.contracts import (
    LAWFUL_REFERENCE_ACTIONS,
    MEMORY_ITEM_MAX_UTF8_BYTES,
    ArtifactRef,
    CycleRequest,
    InputSnapshot,
    Review,
    RunState,
    VerifiedMemoryItem,
    normalize_verified_memory_items,
)
from ...domain.market_cycle.experiment import (
    ExperimentPolicyError,
    ExperimentPolicyV1,
)
from ...domain.market_cycle.theory import (
    CURRENT_THEORY_IDENTITY,
    V332_THEORY_IDENTITY,
    TheoryIdentity,
    TheoryIdentityError,
    require_supported_theory_identity,
)
from ...v32_durable_json import (
    atomic_replace_json,
    ensure_directory_tree,
    exclusive_lock_file,
    write_once_json,
)
from ..market_data.optional_context import OkxOptionalContextMarketData
from ..market_data.okx_profiles import (
    HYPE_OKX_CONTRACT_IDENTITY,
    HYPE_OKX_DATA_PROFILE,
    HYPE_OKX_INSTRUMENT_ID,
    HYPE_OKX_PROFILE_ID,
    HypeOkxPublicCollector,
    build_hype_data_profile_service,
)
from ..market_data.okx_snapshot import OkxBaselineMarketData
from ..market_data.okx_transport import OkxPublicTransport
from ..market_data.raw_capture import FileRawCaptureStore
from .clock import SystemUTCMonotonicClock
from .attention_repository import AttentionRepositoryError, FileAttentionRepository
from .codex_mailbox import LocalMarketCycleAgentMailbox
from .controller_state import FileControllerState
from .goal_identity import current_codex_goal_identity
from .okx_outcome import OkxMarkOutcome
from .paper_context import PaperDecisionContextProvider
from .paper_ledger import FilePaperLedger
from .paper_intent_mailbox import (
    _REQUEST_FIELDS_FRESH as _PAPER_INTENT_REQUEST_FIELDS_FRESH,
    _REQUEST_FIELDS_LEGACY as _PAPER_INTENT_REQUEST_FIELDS_LEGACY,
    _REQUEST_SCHEMA_ID as _PAPER_INTENT_REQUEST_SCHEMA_ID,
    _REQUEST_SCHEMA_VERSION as _PAPER_INTENT_REQUEST_SCHEMA_VERSION,
)
from .repository import FileCycleRepository, MarketCycleRepositoryError
from .theory_package import FileTheoryPackageLoader


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_THEORY_PACKAGE = _PROJECT_ROOT / "theory" / "versions" / "v3.3.1"
DEFAULT_RUNTIME_ROOT = (
    Path.home() / ".local" / "state" / "agent-trade-emotion" / "market-cycle"
)

RUN_MANIFEST_RELATIVE_PATH = Path("controller/run.json")
EXPERIMENT_POLICY_RELATIVE_PATH = Path("controller/experiment-policy.json")
_EXPERIMENT_POLICY_MAX_BYTES = 256 * 1024
RUN_MANIFEST_SCHEMA_ID = "agent_trade_emotion_v331_runtime_run"
RUN_MANIFEST_SCHEMA_VERSION = "1.0.0"
RUN_MANIFEST_STATUSES = frozenset({"OPEN", "CLOSED"})
AGENT_FIRST_CONTRACT_IDENTITY = "V331_AGENT_FIRST_VERBATIM_DECISION_REVIEW_V1"
V332_RUNTIME_CONTRACT_IDENTITY = "V332_MULTI_ASSET_AGENT_ATTENTION_PAPER_V1"
_RUN_MANIFEST_MAX_BYTES = 64 * 1024
_RUN_MANIFEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "theory_manifest_sha256",
        "implementation_sha256",
        "contract_identity",
        "market_contract_identity",
        "experiment_identity",
        "status",
    }
)
RUN_IDENTITY_REGISTRY_DIRECTORY = Path(".controller-run-identities")
RUN_IDENTITY_SEAL_SCHEMA_ID = "agent_trade_emotion_v331_runtime_run_identity_seal"
RUN_IDENTITY_SEAL_SCHEMA_VERSION = "1.0.0"
_RUN_IDENTITY_SEAL_MAX_BYTES = 64 * 1024
_RUN_IDENTITY_SEAL_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "run_root_canonical_path",
        "theory_manifest_sha256",
        "implementation_sha256",
        "contract_identity",
        "market_contract_identity",
        "experiment_identity",
        "run_manifest_identity_sha256",
    }
)
RUN_CLOSURE_RELATIVE_PATH = Path("controller/run-closed.json")
RUN_LIFECYCLE_LOCK_RELATIVE_PATH = Path("controller/run-lifecycle.lock")
RUN_CLOSURE_SCHEMA_ID = "agent_trade_emotion_v331_runtime_run_closure"
RUN_CLOSURE_SCHEMA_VERSION = "1.0.0"
_RUN_CLOSURE_MAX_BYTES = 64 * 1024
_RUN_CLOSURE_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "run_id",
        "run_manifest_identity_sha256",
        "status",
    }
)
_RUN_LIFECYCLE_LOCAL = threading.local()
_IMPLEMENTATION_DIRECTORIES = (
    "trade_system/theory_paper_v2/application/market_cycle",
    "trade_system/theory_paper_v2/domain/market_cycle",
    "trade_system/theory_paper_v2/infrastructure/market_cycle",
    "trade_system/theory_paper_v2/infrastructure/market_data",
)
_IMPLEMENTATION_SINGLE_FILES = (
    "trade_system/theory_paper_v2/presentation/market_cycle.py",
    "trade_system/theory_paper_v2/presentation/paper_agent.py",
    "trade_system/theory_paper_v2/domain/contracts/canonical.py",
    "trade_system/theory_paper_v2/v32_durable_json.py",
)
MEMORY_CONTEXT_RELATIVE_PATH = Path("controller/memory-context.json")
MEMORY_CONTEXT_SCHEMA_ID = "agent_trade_emotion_v331_memory_context"
MEMORY_CONTEXT_SCHEMA_VERSION = "2.0.0"
_MEMORY_DESCRIPTOR_MAX_BYTES = 64 * 1024
_MEMORY_DESCRIPTOR_FIELDS = frozenset({"schema_id", "schema_version", "items"})
_MEMORY_ITEM_DESCRIPTOR_FIELDS = frozenset(
    {
        "kind",
        "source_run_id",
        "source_cycle_id",
        "source_ref",
    }
)
_MEMORY_SOURCE_ARTIFACT_TYPES = {
    "RECENT_FULL_DAILY": frozenset({"InputSnapshot"}),
    "RELATED_DECISION_REVIEW": frozenset(
        {"HypothesisRecord", "BehaviorPlan", "Review"}
    ),
    "DERIVED_OLDER_SUMMARY": frozenset({"Review"}),
}
CYCLE_RUN_BINDING_RELATIVE_PATH = Path("transport/run-binding.json")
CYCLE_RUN_BINDING_SCHEMA_ID = "agent_trade_emotion_v331_cycle_run_binding"
CYCLE_RUN_BINDING_SCHEMA_VERSION = "1.0.0"
_CYCLE_RUN_BINDING_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "cycle_id",
        "run_manifest_identity_sha256",
        "run_id",
        "theory_manifest_sha256",
        "implementation_sha256",
        "contract_identity",
        "market_contract_identity",
        "experiment_identity",
    }
)


class MarketCycleRuntimeError(ValueError):
    """The explicit runtime composition or run-identity boundary is invalid."""


def _runtime_contract_identity(identity: TheoryIdentity) -> str:
    """Keep V3.3.1 run bytes distinct from the V3.3.2 system contract."""

    supported = require_supported_theory_identity(identity)
    return (
        AGENT_FIRST_CONTRACT_IDENTITY
        if supported == CURRENT_THEORY_IDENTITY
        else V332_RUNTIME_CONTRACT_IDENTITY
    )


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _implementation_source_paths(project_root: Path = _PROJECT_ROOT) -> tuple[Path, ...]:
    """Return the blueprint source set, sorted by project-relative POSIX path."""

    paths: set[Path] = set()
    for relative_directory in _IMPLEMENTATION_DIRECTORIES:
        directory = project_root / relative_directory
        try:
            directory_metadata = directory.lstat()
        except FileNotFoundError as exc:
            raise MarketCycleRuntimeError(
                f"RUN_IMPLEMENTATION_SCOPE_MISSING:{relative_directory}"
            ) from exc
        if stat.S_ISLNK(directory_metadata.st_mode) or not stat.S_ISDIR(
            directory_metadata.st_mode
        ):
            raise MarketCycleRuntimeError(
                f"RUN_IMPLEMENTATION_SCOPE_UNSAFE:{relative_directory}"
            )
        for root, directory_names, file_names in os.walk(directory, followlinks=False):
            root_path = Path(root)
            for name in tuple(directory_names) + tuple(file_names):
                candidate = root_path / name
                if candidate.is_symlink():
                    relative = candidate.relative_to(project_root).as_posix()
                    raise MarketCycleRuntimeError(
                        f"RUN_IMPLEMENTATION_SOURCE_SYMLINK:{relative}"
                    )
            for name in file_names:
                if name.endswith(".py"):
                    paths.add(root_path / name)
    for relative_file in _IMPLEMENTATION_SINGLE_FILES:
        paths.add(project_root / relative_file)
    return tuple(
        sorted(paths, key=lambda path: path.relative_to(project_root).as_posix())
    )


def current_implementation_identity(project_root: Path = _PROJECT_ROOT) -> str:
    """Hash the live blueprint source set without embedding a self-referential digest."""

    identity = hashlib.sha256()
    for source_path in _implementation_source_paths(project_root):
        relative = source_path.relative_to(project_root).as_posix()
        try:
            metadata = source_path.lstat()
        except FileNotFoundError as exc:
            raise MarketCycleRuntimeError(
                f"RUN_IMPLEMENTATION_SOURCE_MISSING:{relative}"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketCycleRuntimeError(
                f"RUN_IMPLEMENTATION_SOURCE_UNSAFE:{relative}"
            )
        identity.update(f"{_sha256(source_path.read_bytes())}  {relative}\n".encode("utf-8"))
    return identity.hexdigest()


def _bounded_identity(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode("utf-8")) > 512
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise MarketCycleRuntimeError(f"RUN_MANIFEST_{field_name}_INVALID")
    return value


def _digest(value: object, *, field_name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MarketCycleRuntimeError(f"RUN_MANIFEST_{field_name}_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class FrozenRunManifest:
    """Exact controller-owned identity required by every active runtime entry."""

    run_id: str
    theory_manifest_sha256: str
    implementation_sha256: str
    contract_identity: str
    market_contract_identity: str
    experiment_identity: str
    status: str
    raw_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_id": RUN_MANIFEST_SCHEMA_ID,
            "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
            "run_id": self.run_id,
            "theory_manifest_sha256": self.theory_manifest_sha256,
            "implementation_sha256": self.implementation_sha256,
            "contract_identity": self.contract_identity,
            "market_contract_identity": self.market_contract_identity,
            "experiment_identity": self.experiment_identity,
            "status": self.status,
        }

    def identity_dict(self) -> dict[str, str]:
        """Return the immutable identity fields, excluding OPEN/CLOSED state."""

        value = self.to_dict()
        value.pop("status")
        return value

    @property
    def identity_sha256(self) -> str:
        return _sha256(canonical_bytes(self.identity_dict()))

    @property
    def initial_open_raw_sha256(self) -> str:
        """Digest the canonical initial OPEN manifest independent of later closure."""

        value = self.to_dict()
        value["status"] = "OPEN"
        return _sha256(canonical_bytes(value) + b"\n")


def _canonical_run_root(runtime_root: Path | str) -> Path:
    root = Path(runtime_root).absolute()
    try:
        metadata = root.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("RUN_ROOT_MISSING") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MarketCycleRuntimeError("RUN_ROOT_UNSAFE")
    return root.resolve(strict=True)


@contextmanager
def run_lifecycle_lock(runtime_root: Path | str) -> Iterator[None]:
    """Hold the one run-wide mutation/closure lock, reentrantly per thread.

    ``exclusive_lock_file`` deliberately reopens its OS lock on every call and
    therefore is not a nesting primitive.  Store and service entry points do
    nest, so only the outermost frame acquires the OS lock; every inner frame
    remains inside that same critical section.
    """

    root = _canonical_run_root(runtime_root)
    lock_path = root / RUN_LIFECYCLE_LOCK_RELATIVE_PATH
    key = os.fspath(lock_path)
    depths = getattr(_RUN_LIFECYCLE_LOCAL, "depths", None)
    if depths is None:
        depths = {}
        _RUN_LIFECYCLE_LOCAL.depths = depths
    depth = depths.get(key, 0)
    if depth:
        depths[key] = depth + 1
        try:
            yield
        finally:
            remaining = depths[key] - 1
            if remaining:
                depths[key] = remaining
            else:
                depths.pop(key, None)
        return
    with exclusive_lock_file(lock_path):
        depths[key] = 1
        try:
            yield
        finally:
            depths.pop(key, None)


def run_identity_seal_path(runtime_root: Path | str) -> Path:
    """Return the controller registry anchor outside the replaceable run root."""

    root = _canonical_run_root(runtime_root)
    return root.parent / RUN_IDENTITY_REGISTRY_DIRECTORY / f"{root.name}.json"


def run_identity_seal_document(
    runtime_root: Path | str, manifest: FrozenRunManifest
) -> dict[str, str]:
    """Return the exact controller document that must be published create-once."""

    if not isinstance(manifest, FrozenRunManifest):
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_MANIFEST_INVALID")
    root = _canonical_run_root(runtime_root)
    if manifest.run_id != root.name or manifest.status not in RUN_MANIFEST_STATUSES:
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_MANIFEST_INVALID")
    return {
        "schema_id": RUN_IDENTITY_SEAL_SCHEMA_ID,
        "schema_version": RUN_IDENTITY_SEAL_SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "run_root_canonical_path": str(root),
        "theory_manifest_sha256": manifest.theory_manifest_sha256,
        "implementation_sha256": manifest.implementation_sha256,
        "contract_identity": manifest.contract_identity,
        "market_contract_identity": manifest.market_contract_identity,
        "experiment_identity": manifest.experiment_identity,
        "run_manifest_identity_sha256": manifest.identity_sha256,
    }


def initialize_run_identity_seal(
    runtime_root: Path | str, manifest: FrozenRunManifest
) -> str:
    """Controller-only O_EXCL publication; active runtime never calls this."""

    if not isinstance(manifest, FrozenRunManifest) or manifest.status != "OPEN":
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_MANIFEST_INVALID")
    path = run_identity_seal_path(runtime_root)
    return write_once_json(
        path, run_identity_seal_document(runtime_root, manifest)
    )


def initialize_v332_run(
    runtime_root: Path | str,
    *,
    theory_package: Path | str,
    experiment_policy: ExperimentPolicyV1,
) -> FrozenRunManifest:
    """Create one fresh V3.3.2 run bound to a create-once experiment policy.

    The caller chooses the exact run path and policy.  This function creates no
    market request and performs no network, paper, account, or order action.
    A partially initialized root is never reused; callers must choose a new
    run id after any failure.
    """

    if not isinstance(experiment_policy, ExperimentPolicyV1):
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_REQUIRED")
    root = Path(runtime_root).absolute()
    if root.name != experiment_policy.run_id:
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_RUN_ROOT_MISMATCH")
    package_path = Path(theory_package).absolute()
    if not package_path.is_dir():
        raise MarketCycleRuntimeError("THEORY_PACKAGE_REQUIRED")
    package = FileTheoryPackageLoader(package_path).load(V332_THEORY_IDENTITY)
    if (
        experiment_policy.venue_id != "OKX"
        or experiment_policy.instrument_id != HYPE_OKX_INSTRUMENT_ID
        or experiment_policy.market_contract_identity != HYPE_OKX_CONTRACT_IDENTITY
        or experiment_policy.data_profile
        != HYPE_OKX_DATA_PROFILE.market_data_profile
    ):
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_MARKET_NOT_ADMITTED")
    if root.exists() or root.is_symlink():
        raise MarketCycleRuntimeError("RUN_ROOT_ALREADY_EXISTS")
    ensure_directory_tree(root.parent)
    try:
        os.mkdir(root, 0o700)
    except FileExistsError as exc:
        raise MarketCycleRuntimeError("RUN_ROOT_ALREADY_EXISTS") from exc
    ensure_directory_tree(root / RUN_MANIFEST_RELATIVE_PATH.parent)
    write_once_json(
        root / EXPERIMENT_POLICY_RELATIVE_PATH,
        experiment_policy.to_dict(),
    )
    implementation_sha256 = current_implementation_identity()
    manifest_document = {
        "schema_id": RUN_MANIFEST_SCHEMA_ID,
        "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": root.name,
        "theory_manifest_sha256": package.identity.manifest_digest,
        "implementation_sha256": implementation_sha256,
        "contract_identity": V332_RUNTIME_CONTRACT_IDENTITY,
        "market_contract_identity": HYPE_OKX_CONTRACT_IDENTITY,
        "experiment_identity": experiment_policy.policy_sha256,
        "status": "OPEN",
    }
    raw = canonical_bytes(manifest_document) + b"\n"
    write_once_json(root / RUN_MANIFEST_RELATIVE_PATH, manifest_document)
    manifest = FrozenRunManifest(
        run_id=root.name,
        theory_manifest_sha256=package.identity.manifest_digest,
        implementation_sha256=implementation_sha256,
        contract_identity=V332_RUNTIME_CONTRACT_IDENTITY,
        market_contract_identity=HYPE_OKX_CONTRACT_IDENTITY,
        experiment_identity=experiment_policy.policy_sha256,
        status="OPEN",
        raw_sha256=_sha256(raw),
    )
    initialize_run_identity_seal(root, manifest)
    return manifest


def _read_experiment_policy(
    runtime_root: Path, manifest: FrozenRunManifest
) -> ExperimentPolicyV1:
    path = runtime_root / EXPERIMENT_POLICY_RELATIVE_PATH
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_MISSING") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > _EXPERIMENT_POLICY_MAX_BYTES
    ):
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_UNSAFE")
    raw = path.read_bytes()
    try:
        value = loads_json_strict(raw)
        if not isinstance(value, Mapping) or canonical_bytes(value) + b"\n" != raw:
            raise MarketCycleRuntimeError("EXPERIMENT_POLICY_NONCANONICAL")
        policy = ExperimentPolicyV1.from_dict(value)
    except (CanonicalContractError, ExperimentPolicyError) as exc:
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_INVALID") from exc
    if (
        policy.run_id != manifest.run_id
        or policy.market_contract_identity != manifest.market_contract_identity
        or policy.policy_sha256 != manifest.experiment_identity
    ):
        raise MarketCycleRuntimeError("EXPERIMENT_POLICY_IDENTITY_MISMATCH")
    return policy


def _validate_run_identity_seal(
    runtime_root: Path, manifest: FrozenRunManifest
) -> None:
    """Bind one run_id to one immutable identity across fresh processes."""

    path = run_identity_seal_path(runtime_root)
    registry = path.parent
    try:
        registry_metadata = registry.lstat()
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_MISSING") from exc
    if (
        stat.S_ISLNK(registry_metadata.st_mode)
        or not stat.S_ISDIR(registry_metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
    ):
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_UNSAFE")
    raw = path.read_bytes()
    if not raw or len(raw) > _RUN_IDENTITY_SEAL_MAX_BYTES:
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_CAPACITY_INVALID")
    try:
        value = loads_json_strict(raw)
    except CanonicalContractError as exc:
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_JSON_INVALID") from exc
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _RUN_IDENTITY_SEAL_FIELDS
        or canonical_bytes(value) + b"\n" != raw
        or dict(value) != run_identity_seal_document(runtime_root, manifest)
    ):
        raise MarketCycleRuntimeError("RUN_IDENTITY_SEAL_MISMATCH")


def _validate_run_closure(runtime_root: Path, manifest: FrozenRunManifest) -> bool:
    """Validate the controller marker and report whether it is present."""

    path = runtime_root / RUN_CLOSURE_RELATIVE_PATH
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        if manifest.status == "CLOSED":
            raise MarketCycleRuntimeError("RUN_CLOSURE_MARKER_MISSING")
        return False
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketCycleRuntimeError("RUN_CLOSURE_MARKER_UNSAFE")
    raw = path.read_bytes()
    if not raw or len(raw) > _RUN_CLOSURE_MAX_BYTES:
        raise MarketCycleRuntimeError("RUN_CLOSURE_MARKER_CAPACITY_INVALID")
    try:
        value = loads_json_strict(raw)
    except CanonicalContractError as exc:
        raise MarketCycleRuntimeError("RUN_CLOSURE_MARKER_JSON_INVALID") from exc
    expected = {
        "schema_id": RUN_CLOSURE_SCHEMA_ID,
        "schema_version": RUN_CLOSURE_SCHEMA_VERSION,
        "run_id": manifest.run_id,
        "run_manifest_identity_sha256": manifest.identity_sha256,
        "status": "CLOSED",
    }
    if (
        not isinstance(value, Mapping)
        or frozenset(value) != _RUN_CLOSURE_FIELDS
        or canonical_bytes(value) + b"\n" != raw
        or dict(value) != expected
    ):
        raise MarketCycleRuntimeError("RUN_CLOSURE_MARKER_IDENTITY_MISMATCH")
    return True


def _memory_source_run_root(runtime_root: Path, source_run_id: object) -> Path:
    run_id = _bounded_identity(source_run_id, field_name="MEMORY_SOURCE_RUN_ID")
    if (
        run_id in {".", ".."}
        or "/" in run_id
        or "\\" in run_id
        or Path(run_id).name != run_id
    ):
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_RUN_ID_UNSAFE")
    current_root = _canonical_run_root(runtime_root)
    if run_id != current_root.name:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_RUN_MISMATCH")
    runs_parent = current_root.parent.resolve(strict=True)
    source_root = runs_parent / run_id
    try:
        metadata = source_root.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_RUN_MISSING") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_RUN_UNSAFE")
    resolved_source = source_root.resolve(strict=True)
    if resolved_source.parent != runs_parent or resolved_source != current_root:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_RUN_ESCAPE")
    return resolved_source


def _verified_memory_from_descriptor(
    runtime_root: Path,
    descriptor: Mapping[str, Any],
    *,
    expected_theory_identity: TheoryIdentity,
) -> VerifiedMemoryItem:
    """Derive provenance only from one existing, content-addressed source cycle."""

    kind = descriptor.get("kind")
    allowed_artifacts = _MEMORY_SOURCE_ARTIFACT_TYPES.get(kind)
    if allowed_artifacts is None:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_KIND_INVALID")
    source_run_id = _bounded_identity(
        descriptor.get("source_run_id"), field_name="MEMORY_SOURCE_RUN_ID"
    )
    source_cycle_id = _bounded_identity(
        descriptor.get("source_cycle_id"), field_name="MEMORY_SOURCE_CYCLE_ID"
    )
    source_ref_value = descriptor.get("source_ref")
    if not isinstance(source_ref_value, Mapping):
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_REF_INVALID")
    try:
        source_ref = ArtifactRef.from_dict(source_ref_value)
    except (KeyError, TypeError, ValueError) as exc:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_REF_INVALID") from exc
    if source_ref.artifact_type not in allowed_artifacts:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_KIND_REF_MISMATCH")

    source_root = _memory_source_run_root(runtime_root, source_run_id)
    source_raw_store = FileRawCaptureStore(source_root)
    repository = FileCycleRepository(
        source_root / "cycles", raw_capture_verifier=source_raw_store
    )
    try:
        state = repository.load_state(source_cycle_id)
        request = repository.load_request(source_cycle_id)
        snapshot = InputSnapshot.from_dict(
            repository.load_artifact(source_cycle_id, "InputSnapshot")
        )
    except (KeyError, TypeError, ValueError, MarketCycleRepositoryError) as exc:
        raise MarketCycleRuntimeError(
            "MEMORY_CONTEXT_SOURCE_CYCLE_INVALID"
        ) from exc
    if (
        request.cycle_id != source_cycle_id
        or snapshot.cycle_id != source_cycle_id
        or request.request_id != snapshot.request_id
        or request.venue_id != snapshot.venue_id
        or request.instrument_id != snapshot.instrument_id
        or request.contract_identity != snapshot.contract_identity
        or request.theory_identity != snapshot.theory_identity
        or request.theory_identity != expected_theory_identity
        or state.theory_identity != expected_theory_identity
        or source_ref not in state.artifact_refs
    ):
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_IDENTITY_MISMATCH")

    try:
        source_value = repository.load_artifact(
            source_cycle_id, source_ref.artifact_type
        )
        source_payload = canonical_bytes(source_value)
    except (CanonicalContractError, MarketCycleRepositoryError) as exc:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_REF_INVALID") from exc
    if (
        len(source_payload) != source_ref.size_bytes
        or _sha256(source_payload) != source_ref.sha256
        or len(source_payload) > MEMORY_ITEM_MAX_UTF8_BYTES
    ):
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_SOURCE_REF_INVALID")

    if source_ref.artifact_type == "InputSnapshot":
        availability_basis = "SEALED_AT"
        source_available_at = snapshot.sealed_at
    else:
        try:
            review = Review.from_dict(
                repository.load_artifact(source_cycle_id, "Review")
            )
        except (KeyError, TypeError, ValueError, MarketCycleRepositoryError) as exc:
            raise MarketCycleRuntimeError(
                "MEMORY_CONTEXT_SOURCE_REVIEW_UNAVAILABLE"
            ) from exc
        if (
            review.cycle_id != source_cycle_id
            or review.theory_identity != expected_theory_identity
        ):
            raise MarketCycleRuntimeError(
                "MEMORY_CONTEXT_SOURCE_IDENTITY_MISMATCH"
            )
        availability_basis = "REVIEWED_AT"
        source_available_at = review.reviewed_at

    source_path = (
        PurePosixPath(source_run_id)
        / "cycles"
        / source_cycle_id
        / source_ref.path
    ).as_posix()
    return VerifiedMemoryItem(
        kind=str(kind),
        status="AVAILABLE",
        source_path=source_path,
        source_sha256=source_ref.sha256,
        source_cycle_id=source_cycle_id,
        venue_id=snapshot.venue_id,
        instrument_id=snapshot.instrument_id,
        contract_identity=snapshot.contract_identity,
        availability_basis=availability_basis,
        source_available_at=source_available_at,
        verbatim_text=source_payload.decode("utf-8", errors="strict"),
    )


def load_verified_memory_context(
    runtime_root: Path | str,
    *,
    expected_theory_identity: TheoryIdentity = CURRENT_THEORY_IDENTITY,
) -> tuple[VerifiedMemoryItem, ...]:
    """Load an optional all-or-nothing controller descriptor; invalid means UNKNOWN."""

    try:
        identity = require_supported_theory_identity(expected_theory_identity)
    except TheoryIdentityError as exc:
        raise MarketCycleRuntimeError("MEMORY_CONTEXT_THEORY_IDENTITY_INVALID") from exc
    root = Path(runtime_root).absolute()
    descriptor_path = root / MEMORY_CONTEXT_RELATIVE_PATH
    try:
        controller_metadata = descriptor_path.parent.lstat()
        if stat.S_ISLNK(controller_metadata.st_mode) or not stat.S_ISDIR(
            controller_metadata.st_mode
        ):
            return ()
        metadata = descriptor_path.lstat()
    except FileNotFoundError:
        return ()
    except OSError:
        return ()
    try:
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketCycleRuntimeError("MEMORY_CONTEXT_DESCRIPTOR_UNSAFE")
        raw = descriptor_path.read_bytes()
        if not raw or len(raw) > _MEMORY_DESCRIPTOR_MAX_BYTES:
            raise MarketCycleRuntimeError("MEMORY_CONTEXT_DESCRIPTOR_CAPACITY_INVALID")
        value = loads_json_strict(raw)
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _MEMORY_DESCRIPTOR_FIELDS
            or value.get("schema_id") != MEMORY_CONTEXT_SCHEMA_ID
            or value.get("schema_version") != MEMORY_CONTEXT_SCHEMA_VERSION
            or canonical_bytes(value) + b"\n" != raw
        ):
            raise MarketCycleRuntimeError("MEMORY_CONTEXT_DESCRIPTOR_INVALID")
        descriptors = value.get("items")
        if not isinstance(descriptors, list):
            raise MarketCycleRuntimeError("MEMORY_CONTEXT_ITEMS_INVALID")
        items: list[VerifiedMemoryItem] = []
        for descriptor in descriptors:
            if (
                not isinstance(descriptor, Mapping)
                or frozenset(descriptor) != _MEMORY_ITEM_DESCRIPTOR_FIELDS
            ):
                raise MarketCycleRuntimeError("MEMORY_CONTEXT_ITEM_INVALID")
            items.append(
                _verified_memory_from_descriptor(
                    root,
                    descriptor,
                    expected_theory_identity=identity,
                )
            )
        return normalize_verified_memory_items(items)
    except (CanonicalContractError, OSError, TypeError, UnicodeError, ValueError):
        return ()


def _cycle_run_binding_document(
    manifest: FrozenRunManifest, *, cycle_id: str
) -> dict[str, str]:
    return {
        "schema_id": CYCLE_RUN_BINDING_SCHEMA_ID,
        "schema_version": CYCLE_RUN_BINDING_SCHEMA_VERSION,
        "cycle_id": cycle_id,
        "run_manifest_identity_sha256": manifest.identity_sha256,
        "run_id": manifest.run_id,
        "theory_manifest_sha256": manifest.theory_manifest_sha256,
        "implementation_sha256": manifest.implementation_sha256,
        "contract_identity": manifest.contract_identity,
        "market_contract_identity": manifest.market_contract_identity,
        "experiment_identity": manifest.experiment_identity,
    }


def _read_run_manifest(
    runtime_root: Path,
    *,
    theory_manifest_sha256: str,
    implementation_sha256: str,
    expected_contract_identity: str = AGENT_FIRST_CONTRACT_IDENTITY,
    recover_interrupted_closure: bool = False,
) -> FrozenRunManifest:
    try:
        root_metadata = runtime_root.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("RUN_ROOT_MISSING") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise MarketCycleRuntimeError("RUN_ROOT_UNSAFE")

    controller_directory = runtime_root / RUN_MANIFEST_RELATIVE_PATH.parent
    try:
        controller_metadata = controller_directory.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("RUN_MANIFEST_DIRECTORY_MISSING") from exc
    if stat.S_ISLNK(controller_metadata.st_mode) or not stat.S_ISDIR(
        controller_metadata.st_mode
    ):
        raise MarketCycleRuntimeError("RUN_MANIFEST_DIRECTORY_UNSAFE")
    path = runtime_root / RUN_MANIFEST_RELATIVE_PATH
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise MarketCycleRuntimeError("RUN_MANIFEST_MISSING") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketCycleRuntimeError("RUN_MANIFEST_UNSAFE")
    raw = path.read_bytes()
    if not raw or len(raw) > _RUN_MANIFEST_MAX_BYTES:
        raise MarketCycleRuntimeError("RUN_MANIFEST_TRANSPORT_CAPACITY_INVALID")
    try:
        value = loads_json_strict(raw)
    except CanonicalContractError as exc:
        raise MarketCycleRuntimeError("RUN_MANIFEST_JSON_INVALID") from exc
    if (
        not isinstance(value, Mapping)
        or canonical_bytes(value) + b"\n" != raw
        or frozenset(value) != _RUN_MANIFEST_FIELDS
    ):
        raise MarketCycleRuntimeError("RUN_MANIFEST_FIELDS_INVALID")
    if value.get("schema_id") != RUN_MANIFEST_SCHEMA_ID:
        raise MarketCycleRuntimeError("RUN_MANIFEST_SCHEMA_ID_INVALID")
    if value.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
        raise MarketCycleRuntimeError("RUN_MANIFEST_SCHEMA_VERSION_INVALID")

    run_id = _bounded_identity(value.get("run_id"), field_name="RUN_ID")
    if runtime_root.name != run_id:
        raise MarketCycleRuntimeError("RUN_MANIFEST_RUN_ROOT_MISMATCH")
    observed_theory = _digest(
        value.get("theory_manifest_sha256"), field_name="THEORY_SHA256"
    )
    if observed_theory != theory_manifest_sha256:
        raise MarketCycleRuntimeError("RUN_MANIFEST_THEORY_IDENTITY_MISMATCH")
    observed_implementation = _digest(
        value.get("implementation_sha256"), field_name="IMPLEMENTATION_SHA256"
    )
    if observed_implementation != implementation_sha256:
        raise MarketCycleRuntimeError("RUN_MANIFEST_IMPLEMENTATION_IDENTITY_MISMATCH")
    status = value.get("status")
    if status not in RUN_MANIFEST_STATUSES:
        raise MarketCycleRuntimeError("RUN_MANIFEST_STATUS_INVALID")
    contract_identity = _bounded_identity(
        value.get("contract_identity"), field_name="CONTRACT_IDENTITY"
    )
    if contract_identity != _bounded_identity(
        expected_contract_identity, field_name="EXPECTED_CONTRACT_IDENTITY"
    ):
        raise MarketCycleRuntimeError("RUN_MANIFEST_CONTRACT_IDENTITY_MISMATCH")
    manifest = FrozenRunManifest(
        run_id=run_id,
        theory_manifest_sha256=observed_theory,
        implementation_sha256=observed_implementation,
        contract_identity=contract_identity,
        market_contract_identity=_bounded_identity(
            value.get("market_contract_identity"),
            field_name="MARKET_CONTRACT_IDENTITY",
        ),
        experiment_identity=_bounded_identity(
            value.get("experiment_identity"), field_name="EXPERIMENT_IDENTITY"
        ),
        status=str(status),
        raw_sha256=_sha256(raw),
    )
    _validate_run_identity_seal(runtime_root, manifest)
    closure_present = _validate_run_closure(runtime_root, manifest)
    if closure_present and manifest.status == "OPEN":
        if not recover_interrupted_closure:
            raise MarketCycleRuntimeError("RUN_CLOSURE_RECOVERY_REQUIRED")
        # Closure publishes the marker first.  A crash between the marker and
        # manifest replacement is completed only by an explicit close entry;
        # ordinary reads never mutate lifecycle state.
        with run_lifecycle_lock(runtime_root):
            locked_raw = path.read_bytes()
            if locked_raw == raw:
                closed_document = manifest.to_dict()
                closed_document["status"] = "CLOSED"
                try:
                    atomic_replace_json(path, closed_document)
                except (CanonicalContractError, OSError) as exc:
                    raise MarketCycleRuntimeError(
                        "RUN_CLOSURE_MANIFEST_REPLACE_FAILED"
                    ) from exc
            return _read_run_manifest(
                runtime_root,
                theory_manifest_sha256=theory_manifest_sha256,
                implementation_sha256=implementation_sha256,
                expected_contract_identity=expected_contract_identity,
                recover_interrupted_closure=False,
            )
    return manifest


@dataclass(frozen=True, slots=True)
class RunManifestGate:
    """Recheck immutable identity, one-way closure and live code before each entry."""

    runtime_root: Path
    manifest: FrozenRunManifest
    expected_theory_identity: TheoryIdentity = CURRENT_THEORY_IDENTITY

    @contextmanager
    def mutation_guard(self) -> Iterator[FrozenRunManifest]:
        """Serialize one complete mutation and prove the run is still OPEN."""

        with run_lifecycle_lock(self.runtime_root):
            yield self.verify(require_open=True)

    def verify(self, *, require_open: bool) -> FrozenRunManifest:
        try:
            identity = require_supported_theory_identity(
                self.expected_theory_identity
            )
        except TheoryIdentityError as exc:
            raise MarketCycleRuntimeError("RUN_THEORY_IDENTITY_INVALID") from exc
        current_implementation = current_implementation_identity()
        observed = _read_run_manifest(
            self.runtime_root,
            theory_manifest_sha256=identity.manifest_digest,
            implementation_sha256=current_implementation,
            expected_contract_identity=_runtime_contract_identity(identity),
        )
        if observed.identity_dict() != self.manifest.identity_dict():
            raise MarketCycleRuntimeError("RUN_MANIFEST_IMMUTABLE_IDENTITY_CHANGED")
        if require_open and observed.status != "OPEN":
            raise MarketCycleRuntimeError("RUN_MANIFEST_NOT_OPEN")
        return observed


class V332GoalRegistryGate:
    """Verify that this process is the exact policy-bound persistent Goal."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        paper_account_policy: Mapping[str, Any],
    ) -> None:
        logical_agent_id = paper_account_policy.get("logical_agent_id")
        agent_generation = paper_account_policy.get("agent_generation")
        if (
            not isinstance(logical_agent_id, str)
            or not logical_agent_id
            or type(agent_generation) is not int
            or agent_generation < 1
        ):
            raise MarketCycleRuntimeError("V332_GOAL_POLICY_BINDING_INVALID")
        self._logical_agent_id = logical_agent_id
        self._agent_generation = agent_generation
        self._repository = FileAttentionRepository(runtime_root / "attention")
        self._sessions = AgentSessionService(self._repository)

    def verify(
        self, *, physical_goal_id: str | None = None
    ):  # noqa: ANN201 - domain value is intentionally returned
        """Replay the registry and match it to the host-only current identity."""

        try:
            observed_goal_id = (
                current_codex_goal_identity()
                if physical_goal_id is None
                else physical_goal_id
            )
            registry = self._sessions.current(self._logical_agent_id)
            head = self._repository.load(self._logical_agent_id)
        except (OSError, ValueError) as exc:
            raise MarketCycleRuntimeError("V332_GOAL_REGISTRY_INVALID") from exc
        if (
            head.revision < 1
            or registry.logical_agent_id != self._logical_agent_id
            or registry.generation != self._agent_generation
            or registry.symbol != HYPE_OKX_INSTRUMENT_ID
            or registry.status not in {"ACTIVE", "IDLE"}
            or registry.physical_task_id != observed_goal_id
        ):
            raise MarketCycleRuntimeError("V332_GOAL_REGISTRY_MISMATCH")
        return registry


class ManifestBoundCycleService:
    """Guard every mutating/recovery use case before delegating to Application."""

    def __init__(
        self,
        *,
        service: CycleService,
        repository: FileCycleRepository,
        gate: RunManifestGate,
        goal_registry_gate: V332GoalRegistryGate | None = None,
        goal_window_create_required: bool = False,
    ) -> None:
        self._service = service
        self._repository = repository
        self._gate = gate
        self._goal_registry_gate = goal_registry_gate
        self._goal_window_create_required = goal_window_create_required

    def mutation_guard(self):  # noqa: ANN201 - context manager proxy
        return self._gate.mutation_guard()

    def _require_current_v332_goal(self) -> None:
        if self._gate.expected_theory_identity != V332_THEORY_IDENTITY:
            raise MarketCycleRuntimeError("RUN_V332_GOAL_ROUTE_NOT_APPLICABLE")
        try:
            physical_goal_id = current_codex_goal_identity()
        except ValueError as exc:
            raise MarketCycleRuntimeError(
                "RUN_V332_GOAL_IDENTITY_REQUIRED"
            ) from exc
        if self._goal_registry_gate is not None:
            self._goal_registry_gate.verify(physical_goal_id=physical_goal_id)

    def current_v332_goal_registry(self):  # noqa: ANN201 - domain value returned
        """Return the exact host-derived Goal registry for formal Goal entries."""

        if self._gate.expected_theory_identity != V332_THEORY_IDENTITY:
            raise MarketCycleRuntimeError("RUN_V332_GOAL_ROUTE_NOT_APPLICABLE")
        if self._goal_registry_gate is None:
            raise MarketCycleRuntimeError("RUN_V332_GOAL_REGISTRY_REQUIRED")
        try:
            physical_goal_id = current_codex_goal_identity()
        except ValueError as exc:
            raise MarketCycleRuntimeError(
                "RUN_V332_GOAL_IDENTITY_REQUIRED"
            ) from exc
        return self._goal_registry_gate.verify(physical_goal_id=physical_goal_id)

    def _forbid_v332_goal_worker_control(self, worker_id: str) -> None:
        if (
            self._gate.expected_theory_identity == V332_THEORY_IDENTITY
            and worker_id in {"decision-v1", "review-v1"}
        ):
            raise MarketCycleRuntimeError(
                "RUN_V332_GOAL_WORKER_CONTROL_FORBIDDEN"
            )

    def _binding_path(self, cycle_id: str) -> Path:
        return self._repository.root / cycle_id / CYCLE_RUN_BINDING_RELATIVE_PATH

    def _cycle_present(self, cycle_id: str) -> bool:
        path = self._repository.root / cycle_id
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise MarketCycleRuntimeError("RUN_CYCLE_PRESENCE_UNAVAILABLE") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise MarketCycleRuntimeError("RUN_CYCLE_DIRECTORY_UNSAFE")
        return True

    def _write_cycle_binding(
        self, manifest: FrozenRunManifest, *, cycle_id: str
    ) -> None:
        expected = _cycle_run_binding_document(manifest, cycle_id=cycle_id)
        try:
            write_once_json(self._binding_path(cycle_id), expected)
        except (CanonicalContractError, OSError) as exc:
            raise MarketCycleRuntimeError("RUN_BINDING_WRITE_ONCE_FAILED") from exc

    def _verify_cycle_binding(
        self, manifest: FrozenRunManifest, *, cycle_id: str
    ) -> None:
        path = self._binding_path(cycle_id)
        try:
            parent_metadata = path.parent.lstat()
            if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
                parent_metadata.st_mode
            ):
                raise MarketCycleRuntimeError("RUN_BINDING_DIRECTORY_UNSAFE")
            metadata = path.lstat()
        except FileNotFoundError as exc:
            raise MarketCycleRuntimeError("RUN_BINDING_MISSING") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise MarketCycleRuntimeError("RUN_BINDING_UNSAFE")
        raw = path.read_bytes()
        try:
            value = loads_json_strict(raw)
        except CanonicalContractError as exc:
            raise MarketCycleRuntimeError("RUN_BINDING_JSON_INVALID") from exc
        if (
            not isinstance(value, Mapping)
            or frozenset(value) != _CYCLE_RUN_BINDING_FIELDS
            or canonical_bytes(value) + b"\n" != raw
            or dict(value)
            != _cycle_run_binding_document(manifest, cycle_id=cycle_id)
        ):
            raise MarketCycleRuntimeError("RUN_BINDING_IDENTITY_MISMATCH")

    def _require_cycle_binding(
        self, cycle_id: str, *, require_open: bool
    ) -> FrozenRunManifest:
        manifest = self._gate.verify(require_open=require_open)
        request = self._repository.load_request(cycle_id)
        if request.contract_identity != manifest.market_contract_identity:
            raise MarketCycleRuntimeError("RUN_MANIFEST_CYCLE_CONTRACT_MISMATCH")
        if (
            request.theory_identity != self._gate.expected_theory_identity
            or request.theory_identity.manifest_digest
            != manifest.theory_manifest_sha256
        ):
            raise MarketCycleRuntimeError("RUN_MANIFEST_CYCLE_THEORY_MISMATCH")
        self._verify_cycle_binding(manifest, cycle_id=request.cycle_id)
        return manifest

    def create(self, request: CycleRequest) -> RunState:
        return self._create(request, goal_window_verified=False)

    def _create_goal_cycle(self, request: CycleRequest) -> RunState:
        """Runtime-only continuation after current Goal/window verification."""

        return self._create(request, goal_window_verified=True)

    def _create(
        self, request: CycleRequest, *, goal_window_verified: bool
    ) -> RunState:
        with self.mutation_guard() as manifest:
            if self._goal_window_create_required and not goal_window_verified:
                raise MarketCycleRuntimeError(
                    "RUN_V332_GOAL_WINDOW_CREATE_REQUIRED"
                )
            if request.contract_identity != manifest.market_contract_identity:
                raise MarketCycleRuntimeError("RUN_MANIFEST_CREATE_CONTRACT_MISMATCH")
            if (
                request.theory_identity != self._gate.expected_theory_identity
                or request.theory_identity.manifest_digest
                != manifest.theory_manifest_sha256
            ):
                raise MarketCycleRuntimeError("RUN_MANIFEST_CREATE_THEORY_MISMATCH")
            with self._repository.locked(request.cycle_id):
                existing = self._cycle_present(request.cycle_id)
                if existing:
                    self._verify_cycle_binding(manifest, cycle_id=request.cycle_id)
                state = self._service.create(request)
                if not existing:
                    self._write_cycle_binding(manifest, cycle_id=state.cycle_id)
                return state

    def status(self, cycle_id: str) -> RunState:
        self._require_cycle_binding(cycle_id, require_open=False)
        return self._service.status(cycle_id)

    def verify_cycle_read(self, cycle_id: str) -> FrozenRunManifest:
        """Validate identity for read-only sidecar inspection, including CLOSED runs."""

        return self._require_cycle_binding(cycle_id, require_open=False)

    def deliver_agent_decision(
        self,
        cycle_id: str,
        decision_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                if self._gate.expected_theory_identity == V332_THEORY_IDENTITY:
                    self._require_current_v332_goal()
                    return self._service.deliver_goal_decision(
                        cycle_id, decision_bytes, media_type=media_type
                    )
                return self._service.deliver_agent_decision(
                    cycle_id, decision_bytes, media_type=media_type
                )

    def deliver_agent_review(
        self,
        cycle_id: str,
        review_bytes: bytes,
        *,
        media_type: str = "text/markdown",
    ) -> str:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                if self._gate.expected_theory_identity == V332_THEORY_IDENTITY:
                    self._require_current_v332_goal()
                    return self._service.deliver_goal_review(
                        cycle_id, review_bytes, media_type=media_type
                    )
                return self._service.deliver_agent_review(
                    cycle_id, review_bytes, media_type=media_type
                )

    def deliver_worker_result(
        self,
        cycle_id: str,
        worker_id: str,
        *,
        media_type: str = "text/markdown",
    ) -> Mapping[str, Any]:
        """Reject the retired V3.3.2 Worker-result delivery route."""

        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                raise MarketCycleRuntimeError(
                    "RUN_WORKER_RESULT_DELIVERY_NOT_SUPPORTED"
                )

    def run_next(self, cycle_id: str) -> AdvanceResult:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                return self._service.run_next(cycle_id)

    def controller_status(self) -> Mapping[str, Any]:
        """Read internal Worker deadline/dispatch state without mutating it."""

        observed = self._gate.verify(require_open=False)
        value = dict(self._service.controller_status())
        value["run_status"] = observed.status
        value["controller_mode"] = (
            "ACTIVE_OPEN" if observed.status == "OPEN" else "READ_ONLY_CLOSED"
        )
        value["mutations_allowed"] = observed.status == "OPEN"
        return value

    def controller_prepare_worker(
        self,
        cycle_id: str,
        worker_id: str,
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                task_path = self._service.controller_materialize_worker_task(
                    cycle_id, worker_id
                )
                return self._service.controller_prepare_worker(
                    cycle_id, worker_id, task_path
                )

    def controller_mark_worker_spawn_requested(
        self, cycle_id: str, worker_id: str, dispatch_id: str
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                return self._service.controller_mark_worker_spawn_requested(
                    cycle_id, worker_id, dispatch_id
                )

    def controller_acknowledge_worker_spawn(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        execution_ref: str,
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                return self._service.controller_acknowledge_worker_spawn(
                    cycle_id, worker_id, dispatch_id, execution_ref
                )

    def controller_admit_worker_result_for_delivery(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        """Read-only V3.3.2 result admission; creates no delivery."""

        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                if self._gate.expected_theory_identity != V332_THEORY_IDENTITY:
                    raise MarketCycleRuntimeError(
                        "RUN_WORKER_RESULT_ADMISSION_NOT_SUPPORTED"
                    )
                return self._service.controller_admit_worker_result_for_delivery(
                    cycle_id, worker_id
                )

    def controller_complete_worker(
        self,
        cycle_id: str,
        worker_id: str,
        dispatch_id: str,
        output_sha256: str,
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                return self._service.controller_complete_worker(
                    cycle_id, worker_id, dispatch_id, output_sha256
                )

    def controller_recover_worker(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                return self._service.controller_recover_worker(cycle_id, worker_id)

    def controller_expire_worker(
        self, cycle_id: str, worker_id: str
    ) -> Mapping[str, Any]:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                self._forbid_v332_goal_worker_control(worker_id)
                return self._service.controller_expire_worker(cycle_id, worker_id)

    def controller_prepare_agent_decision(
        self,
        cycle_id: str,
    ) -> Mapping[str, Any]:
        return self.controller_prepare_worker(cycle_id, "decision-v1")

    def controller_mark_spawn_requested(
        self, cycle_id: str, dispatch_id: str
    ) -> Mapping[str, Any]:
        return self.controller_mark_worker_spawn_requested(
            cycle_id, "decision-v1", dispatch_id
        )

    def controller_acknowledge_spawn(
        self, cycle_id: str, dispatch_id: str, execution_ref: str
    ) -> Mapping[str, Any]:
        return self.controller_acknowledge_worker_spawn(
            cycle_id, "decision-v1", dispatch_id, execution_ref
        )

    def controller_complete_agent_decision(
        self, cycle_id: str, dispatch_id: str, delivery_sha256: str
    ) -> Mapping[str, Any]:
        return self.controller_complete_worker(
            cycle_id, "decision-v1", dispatch_id, delivery_sha256
        )

    def controller_recover_agent_decision(
        self, cycle_id: str
    ) -> Mapping[str, Any]:
        return self.controller_recover_worker(cycle_id, "decision-v1")

    def controller_expire_agent_decision(
        self, cycle_id: str, reason_code: str
    ) -> AdvanceResult:
        with self.mutation_guard():
            with self._repository.locked(cycle_id):
                self._require_cycle_binding(cycle_id, require_open=True)
                if self._gate.expected_theory_identity == V332_THEORY_IDENTITY:
                    raise MarketCycleRuntimeError(
                        "RUN_V332_GOAL_WORKER_CONTROL_FORBIDDEN"
                    )
                return self._service.controller_expire_agent_decision(
                    cycle_id, reason_code
                )


def _runtime_moment(value: object, *, code: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise MarketCycleRuntimeError(code)
    try:
        observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketCycleRuntimeError(code) from exc
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise MarketCycleRuntimeError(code)
    return observed


def _require_controller_quiet(runtime: "MarketCycleRuntime") -> None:
    try:
        controller = runtime.controller_state.status()
        events = controller.get("events")
        workers = controller.get("worker_dispatches")
        if not isinstance(events, Mapping) or not isinstance(workers, Mapping):
            raise ValueError("controller state mappings are missing")
        if any(not isinstance(event, Mapping) for event in events.values()) or any(
            not isinstance(worker, Mapping) for worker in workers.values()
        ):
            raise ValueError("controller state entry is malformed")
        if any(event.get("status") == "PENDING" for event in events.values()):
            raise MarketCycleRuntimeError("RUN_CLOSE_PENDING_CONTROLLER_EVENT")
        if any(
            worker.get("status") in {"PREPARED", "SPAWN_REQUESTED", "DISPATCHED"}
            for worker in workers.values()
        ):
            raise MarketCycleRuntimeError("RUN_CLOSE_ACTIVE_WORKER")
    except MarketCycleRuntimeError:
        raise
    except Exception as exc:
        raise MarketCycleRuntimeError("RUN_CLOSE_CONTROLLER_REPLAY_INVALID") from exc


def _close_read_canonical(path: Path, *, code: str) -> tuple[Mapping[str, Any], bytes]:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > 8 * 1024 * 1024
        ):
            raise OSError("unsafe close fact")
        raw = path.read_bytes()
        value = loads_json_strict(raw)
        if (
            not isinstance(value, Mapping)
            or canonical_bytes(value) + b"\n" != raw
        ):
            raise ValueError("noncanonical close fact")
        return value, raw
    except (CanonicalContractError, OSError, ValueError) as exc:
        raise MarketCycleRuntimeError(code) from exc


def _require_completed_paper_intent(
    runtime: "MarketCycleRuntime",
    *,
    cycle_id: str,
    transport: Path,
    request: Mapping[str, Any],
    request_raw: bytes,
) -> None:
    """Trust the paper owner's immutable completion fact, then replay its ledger."""

    receipt, _ = _close_read_canonical(
        transport / "paper-action-execution-receipt.json",
        code="RUN_CLOSE_PAPER_ACTION_RECEIPT_INVALID",
    )
    if (
        receipt.get("schema_id")
        != "agent-trade-emotion.paper-action-execution-receipt"
        or receipt.get("schema_version") != "2.1.0"
        or receipt.get("status") != "COMMITTED"
        or receipt.get("run_id") != runtime.run_manifest.run_id
        or receipt.get("cycle_id") != cycle_id
        or receipt.get("account_id") != request.get("account_id")
        or receipt.get("intent_request_sha256") != _sha256(request_raw)
    ):
        raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_ACTION_RECEIPT_INVALID")
    try:
        account_id = str(request["account_id"])
        policy = runtime.experiment_policy
        if (
            policy is None
            or not isinstance(policy.paper_account, Mapping)
            or policy.paper_account.get("account_id") != account_id
        ):
            raise ValueError("request account is not policy-bound")
        records = FilePaperLedger(runtime.runtime_root / "paper").load_records(account_id)
        replay_paper_account(records)
    except Exception as exc:
        raise MarketCycleRuntimeError(
            "RUN_CLOSE_PAPER_ACTION_RECEIPT_INVALID"
        ) from exc


def _require_no_live_paper_intent(
    runtime: "MarketCycleRuntime", *, close_now: datetime
) -> None:
    cycles_root = runtime.repository.root
    try:
        metadata = cycles_root.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE")
    try:
        candidates = tuple(cycles_root.iterdir())
    except OSError as exc:
        raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE") from exc
    for cycle_root in candidates:
        try:
            cycle_metadata = cycle_root.lstat()
        except OSError as exc:
            raise MarketCycleRuntimeError(
                "RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE"
            ) from exc
        if stat.S_ISLNK(cycle_metadata.st_mode) or not stat.S_ISDIR(
            cycle_metadata.st_mode
        ):
            raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE")
        if cycle_root.name == ".locks":
            continue
        transport = cycle_root / "transport"
        try:
            transport_metadata = transport.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise MarketCycleRuntimeError(
                "RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE"
            ) from exc
        if stat.S_ISLNK(transport_metadata.st_mode) or not stat.S_ISDIR(
            transport_metadata.st_mode
        ):
            raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_SCAN_UNSAFE")
        request_path = transport / "paper-execution-intent-request.json"
        try:
            request_path.lstat()
        except FileNotFoundError:
            continue
        request, request_raw = _close_read_canonical(
            request_path, code="RUN_CLOSE_PAPER_INTENT_REQUEST_INVALID"
        )
        if (
            frozenset(request)
            not in {
                _PAPER_INTENT_REQUEST_FIELDS_FRESH,
                _PAPER_INTENT_REQUEST_FIELDS_LEGACY,
            }
            or request.get("schema_id") != _PAPER_INTENT_REQUEST_SCHEMA_ID
            or request.get("schema_version") != _PAPER_INTENT_REQUEST_SCHEMA_VERSION
            or request.get("cycle_id") != cycle_root.name
        ):
            raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_REQUEST_INVALID")
        valid_until = _runtime_moment(
            request.get("valid_until"), code="RUN_CLOSE_PAPER_INTENT_REQUEST_INVALID"
        )
        issued_at = _runtime_moment(
            request.get("issued_at"), code="RUN_CLOSE_PAPER_INTENT_REQUEST_INVALID"
        )
        if issued_at >= valid_until:
            raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_INTENT_REQUEST_INVALID")
        receipt_path = transport / "paper-action-execution-receipt.json"
        try:
            receipt_path.lstat()
        except FileNotFoundError:
            if not valid_until < close_now:
                raise MarketCycleRuntimeError("RUN_CLOSE_LIVE_PAPER_INTENT")
            continue
        _require_completed_paper_intent(
            runtime,
            cycle_id=cycle_root.name,
            transport=transport,
            request=request,
            request_raw=request_raw,
        )


def _require_continuity_close_ready(
    runtime: "MarketCycleRuntime", *, close_now: datetime
) -> None:
    policy = runtime.experiment_policy
    if policy is None or policy.phase != "CONTINUITY_24H":
        raise MarketCycleRuntimeError("RUN_CLOSE_CONTINUITY_POLICY_REQUIRED")
    start = _runtime_moment(policy.starts_at, code="RUN_CLOSE_POLICY_START_INVALID")
    if close_now < start + timedelta(seconds=86_400):
        raise MarketCycleRuntimeError("RUN_CLOSE_CONTINUITY_ELAPSED_REQUIRED")

    try:
        from .continuity_checkpoint import FileContinuityCheckpointStore

        final = FileContinuityCheckpointStore(
            runtime, clock=runtime.controller_state.trusted_now
        ).load_final()
    except Exception as exc:
        raise MarketCycleRuntimeError("RUN_CLOSE_FINAL_CONTINUITY_REQUIRED") from exc
    if final.record_kind != "FINAL" or final.disposition != "FINALIZED":
        raise MarketCycleRuntimeError("RUN_CLOSE_FINAL_CONTINUITY_REQUIRED")

    try:
        for cycle_id in runtime.repository.list_cycle_ids():
            if runtime.repository.load_state(cycle_id).terminal is not True:
                raise MarketCycleRuntimeError("RUN_CLOSE_TERMINAL_CYCLES_REQUIRED")
    except MarketCycleRuntimeError:
        raise
    except Exception as exc:
        raise MarketCycleRuntimeError("RUN_CLOSE_CYCLE_REPLAY_INVALID") from exc

    paper_policy = policy.paper_account
    if not isinstance(paper_policy, Mapping):
        raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_POLICY_REQUIRED")
    try:
        records = FilePaperLedger(runtime.runtime_root / "paper").load_records(
            str(paper_policy["account_id"])
        )
        replay_paper_account(records)
    except Exception as exc:
        raise MarketCycleRuntimeError("RUN_CLOSE_PAPER_LEDGER_NOT_REPLAYABLE") from exc


def _close_market_cycle_runtime(runtime: "MarketCycleRuntime") -> FrozenRunManifest:
    if runtime.identity != V332_THEORY_IDENTITY:
        raise MarketCycleRuntimeError("RUN_CLOSE_V332_ONLY")
    gate = runtime.service._gate
    with run_lifecycle_lock(runtime.runtime_root):
        observed = _read_run_manifest(
            runtime.runtime_root,
            theory_manifest_sha256=runtime.identity.manifest_digest,
            implementation_sha256=current_implementation_identity(),
            expected_contract_identity=V332_RUNTIME_CONTRACT_IDENTITY,
            recover_interrupted_closure=True,
        )
        if observed.identity_dict() != gate.manifest.identity_dict():
            raise MarketCycleRuntimeError("RUN_MANIFEST_IMMUTABLE_IDENTITY_CHANGED")
        if observed.status == "CLOSED":
            return observed
        policy = runtime.experiment_policy
        if policy is None:
            raise MarketCycleRuntimeError("RUN_CLOSE_EXPERIMENT_POLICY_REQUIRED")
        close_now = _runtime_moment(
            runtime.controller_state.trusted_now(), code="RUN_CLOSE_CLOCK_INVALID"
        )
        _require_controller_quiet(runtime)
        _require_no_live_paper_intent(runtime, close_now=close_now)
        if policy.phase == "CONTINUITY_24H":
            _require_continuity_close_ready(runtime, close_now=close_now)
        elif policy.phase != "CAPABILITY_PILOT":
            raise MarketCycleRuntimeError("RUN_CLOSE_PHASE_UNSUPPORTED")

        marker = {
            "schema_id": RUN_CLOSURE_SCHEMA_ID,
            "schema_version": RUN_CLOSURE_SCHEMA_VERSION,
            "run_id": observed.run_id,
            "run_manifest_identity_sha256": observed.identity_sha256,
            "status": "CLOSED",
        }
        try:
            write_once_json(
                runtime.runtime_root / RUN_CLOSURE_RELATIVE_PATH, marker
            )
            closed_document = observed.to_dict()
            closed_document["status"] = "CLOSED"
            atomic_replace_json(
                runtime.runtime_root / RUN_MANIFEST_RELATIVE_PATH,
                closed_document,
            )
        except (CanonicalContractError, OSError) as exc:
            raise MarketCycleRuntimeError("RUN_CLOSE_PUBLICATION_FAILED") from exc
        return _read_run_manifest(
            runtime.runtime_root,
            theory_manifest_sha256=runtime.identity.manifest_digest,
            implementation_sha256=current_implementation_identity(),
            expected_contract_identity=V332_RUNTIME_CONTRACT_IDENTITY,
        )


def _append_v332_goal_attention_checkpoint(
    *,
    repository: FileAttentionRepository,
    service: AttentionService,
    request: AttentionRequest,
    checkpoint: GoalAttentionCheckpointV1,
    registry: AgentRegistry,
) -> None:
    """Private runtime writer for one already host-verified Goal fact."""

    state = service.status(request.logical_agent_id)
    accepted = _runtime_moment(
        checkpoint.accepted_at,
        code="ATTENTION_REQUEST_ACCEPTED_AT_INVALID",
    )
    issued = _runtime_moment(
        request.issued_at,
        code="ATTENTION_ISSUED_AT_INVALID",
    )
    latest = _runtime_moment(
        request.latest,
        code="ATTENTION_LATEST_TIME_INVALID",
    )
    if accepted < issued:
        raise AttentionApplicationError("ATTENTION_REQUEST_RECEIPT_BEFORE_ISSUED")
    if accepted > latest:
        raise AttentionApplicationError("ATTENTION_REQUEST_EXPIRED")
    if (
        state.registry != registry
        or request.logical_agent_id != registry.logical_agent_id
        or request.symbol != registry.symbol
        or request.agent_generation != registry.generation
        or request.continuity_nonce != registry.continuity_nonce
        or checkpoint.physical_goal_id != registry.physical_task_id
        or checkpoint.request_sha256 != request.agent_owned_sha256
    ):
        raise AttentionApplicationError(
            "ATTENTION_GOAL_CHECKPOINT_BINDING_INVALID"
        )
    if request.request_id in state.requests:
        raise AttentionApplicationError("ATTENTION_REQUEST_ID_CONFLICT")
    if state.active_request_id is None:
        if request.supersedes is not None:
            raise AttentionApplicationError("ATTENTION_SUPERSEDES_NO_ACTIVE_REQUEST")
    elif request.supersedes != state.active_request_id:
        raise AttentionApplicationError(
            "ATTENTION_ACTIVE_REQUEST_REQUIRES_SUPERSEDES"
        )
    repository.compare_and_swap(
        request.logical_agent_id,
        expected_revision=state.revision,
        event_id=f"request:{request.request_id}",
        event_type="ATTENTION_REQUEST_SUBMITTED",
        occurred_at=checkpoint.accepted_at,
        payload={
            "request": request.to_dict(),
            "accepted_at": checkpoint.accepted_at,
            "goal_checkpoint": checkpoint.to_dict(),
        },
    )


@dataclass(frozen=True, slots=True)
class MarketCycleRuntime:
    service: ManifestBoundCycleService
    repository: FileCycleRepository
    mailbox: LocalMarketCycleAgentMailbox
    controller_state: FileControllerState
    identity: TheoryIdentity
    run_manifest: FrozenRunManifest
    experiment_policy: ExperimentPolicyV1 | None
    verified_memory: tuple[VerifiedMemoryItem, ...]
    runtime_root: Path

    def mutation_guard(self):  # noqa: ANN201 - context manager proxy
        """Return the authoritative run-wide OPEN mutation context."""

        guard = getattr(self.service, "mutation_guard", None)
        if callable(guard):
            return guard()
        return run_lifecycle_lock(self.runtime_root)

    def create_goal_cycle(self, cycle_id: str) -> RunState:
        """Create one continuity cycle before the Goal's own window expires."""

        policy = self.experiment_policy
        if (
            self.identity != V332_THEORY_IDENTITY
            or policy is None
            or policy.phase != "CONTINUITY_24H"
            or not policy.local_paper_authorized
            or not isinstance(policy.paper_account, Mapping)
        ):
            raise MarketCycleRuntimeError(
                "V332_GOAL_CYCLE_CREATE_NOT_AUTHORIZED"
            )
        setup_cycle_id = str(policy.paper_account["setup_cycle_id"])
        with self.mutation_guard():
            try:
                persisted = self.repository.load_request(cycle_id)
            except MarketCycleRepositoryError as exc:
                if str(exc) != "MARKET_CYCLE_REQUEST_MISSING":
                    raise
                persisted = None
            if persisted is not None:
                if cycle_id == setup_cycle_id:
                    try:
                        current_codex_goal_identity()
                    except ValueError as exc:
                        raise MarketCycleRuntimeError(
                            "RUN_V332_GOAL_IDENTITY_REQUIRED"
                        ) from exc
                else:
                    self.service.current_v332_goal_registry()
                return self.service.status(cycle_id)

            require_registered_goal = cycle_id != setup_cycle_id
            if require_registered_goal:
                registry = self.service.current_v332_goal_registry()
                try:
                    attention_repository = FileAttentionRepository(
                        self.runtime_root / "attention"
                    )
                    attention = AttentionService(attention_repository).status(
                        registry.logical_agent_id
                    )
                except (
                    AttentionApplicationError,
                    AttentionContractError,
                    AttentionRepositoryError,
                ) as exc:
                    raise MarketCycleRuntimeError(
                        "V332_GOAL_CYCLE_ATTENTION_INVALID"
                    ) from exc
                active_request_id = attention.active_request_id
                if active_request_id is None:
                    # The Goal's first market decision has no prior decision from
                    # which to author a durable next-check checkpoint.
                    prior_non_setup = tuple(
                        item
                        for item in self.repository.list_cycle_ids()
                        if item != setup_cycle_id
                    )
                    if prior_non_setup:
                        raise MarketCycleRuntimeError(
                            "V332_GOAL_CYCLE_ATTENTION_REQUIRED"
                        )
                    active_request = None
                    checkpoint = None
                else:
                    active_request = attention.requests.get(active_request_id)
                    checkpoint = attention.request_goal_checkpoints.get(
                        active_request_id
                    )
                    if (
                        attention.registry != registry
                        or attention.request_statuses.get(active_request_id)
                        != "PENDING"
                        or active_request is None
                        or checkpoint is None
                    ):
                        raise MarketCycleRuntimeError(
                            "V332_GOAL_CYCLE_ATTENTION_INVALID"
                        )
            else:
                try:
                    current_codex_goal_identity()
                except ValueError as exc:
                    raise MarketCycleRuntimeError(
                        "RUN_V332_GOAL_IDENTITY_REQUIRED"
                    ) from exc
                if self.repository.list_cycle_ids():
                    raise MarketCycleRuntimeError(
                        "V332_GOAL_CYCLE_SETUP_CONFLICT"
                    )
                active_request = None
                checkpoint = None

            trusted_now = self.controller_state.trusted_now()
            if active_request is not None and checkpoint is not None:
                observed = _runtime_moment(
                    trusted_now, code="V332_GOAL_CYCLE_TRUSTED_TIME_INVALID"
                )
                accepted = _runtime_moment(
                    checkpoint.accepted_at,
                    code="V332_GOAL_CYCLE_ATTENTION_INVALID",
                )
                latest = _runtime_moment(
                    active_request.latest_useful_at,
                    code="V332_GOAL_CYCLE_ATTENTION_INVALID",
                )
                if observed < accepted:
                    raise MarketCycleRuntimeError(
                        "V332_GOAL_CYCLE_TRUSTED_TIME_REGRESSION"
                    )
                if observed > latest:
                    raise MarketCycleRuntimeError(
                        "V332_GOAL_CYCLE_ATTENTION_WINDOW_EXPIRED"
                    )

            request = CycleRequest(
                request_id=f"{cycle_id}.request",
                cycle_id=cycle_id,
                requested_at=trusted_now,
                venue_id=policy.venue_id,
                instrument_id=policy.instrument_id,
                contract_identity=policy.market_contract_identity,
                analysis_profile="COLD",
                data_profile=policy.data_profile,
                outcome_horizon_seconds=policy.decision_horizon_seconds,
                outcome_tolerance_seconds=policy.outcome_tolerance_seconds,
                lawful_actions=LAWFUL_REFERENCE_ACTIONS,
                theory_identity=self.identity,
            )
            return self.service._create_goal_cycle(request)

    def close_run(self) -> FrozenRunManifest:
        """Freeze this run without flattening paper positions or orders."""

        return _close_market_cycle_runtime(self)

    def submit_goal_attention_checkpoint(
        self, request: AttentionRequest
    ) -> Mapping[str, Any]:
        """Seal one exact Agent request with trusted Goal and clock provenance."""

        with self.mutation_guard():
            policy = self.experiment_policy
            if (
                self.identity != V332_THEORY_IDENTITY
                or policy is None
                or not policy.local_paper_authorized
                or not isinstance(policy.paper_account, Mapping)
            ):
                raise MarketCycleRuntimeError(
                    "V332_GOAL_ATTENTION_CHECKPOINT_NOT_AUTHORIZED"
                )
            if not isinstance(request, AttentionRequest):
                raise MarketCycleRuntimeError(
                    "V332_GOAL_ATTENTION_REQUEST_INVALID"
                )
            registry = self.service.current_v332_goal_registry()
            try:
                repository = FileAttentionRepository(self.runtime_root / "attention")
                service = AttentionService(repository)
                state = service.status(request.logical_agent_id)
                persisted = state.request_goal_checkpoints.get(request.request_id)
                existing = state.requests.get(request.request_id)
                if existing is not None:
                    if (
                        existing != request
                        or persisted is None
                        or persisted.run_id != self.run_manifest.run_id
                        or persisted.run_manifest_identity_sha256
                        != self.run_manifest.identity_sha256
                        or persisted.experiment_policy_sha256 != policy.policy_sha256
                        or persisted.physical_goal_id != registry.physical_task_id
                        or persisted.request_sha256 != request.agent_owned_sha256
                    ):
                        raise AttentionApplicationError(
                            "ATTENTION_FORMAL_CHECKPOINT_CONFLICT"
                        )
                else:
                    accepted_at = self.controller_state.trusted_now()
                    checkpoint = GoalAttentionCheckpointV1(
                        schema_id=GOAL_ATTENTION_CHECKPOINT_SCHEMA_ID,
                        schema_version=GOAL_ATTENTION_CHECKPOINT_SCHEMA_VERSION,
                        run_id=self.run_manifest.run_id,
                        run_manifest_identity_sha256=(
                            self.run_manifest.identity_sha256
                        ),
                        experiment_policy_sha256=policy.policy_sha256,
                        physical_goal_id=str(registry.physical_task_id),
                        physical_goal_source="CODEX_THREAD_ID",
                        request_sha256=request.agent_owned_sha256,
                        accepted_at=accepted_at,
                        accepted_clock_source="CONTROLLER_TRUSTED_CLOCK",
                    )
                    _append_v332_goal_attention_checkpoint(
                        repository=repository,
                        service=service,
                        request=request,
                        checkpoint=checkpoint,
                        registry=registry,
                    )
                    state = service.status(request.logical_agent_id)
                    persisted = state.request_goal_checkpoints.get(
                        request.request_id
                    )
                event = next(
                    (
                        item
                        for item in repository.replay(request.logical_agent_id)
                        if item.event_id == f"request:{request.request_id}"
                    ),
                    None,
                )
            except (
                AttentionApplicationError,
                AttentionContractError,
                AttentionRepositoryError,
            ) as exc:
                raise MarketCycleRuntimeError(
                    f"V332_GOAL_ATTENTION_CHECKPOINT_INVALID:{exc}"
                ) from exc
            if persisted is None or event is None:
                raise MarketCycleRuntimeError(
                    "V332_GOAL_ATTENTION_CHECKPOINT_NOT_DURABLE"
                )
            event_document = event.to_dict()
            return {
                "schema_id": (
                    "agent-trade-emotion.v332-goal-attention-checkpoint-receipt"
                ),
                "schema_version": "1.0.0",
                "status": "CHECKPOINTED",
                "run_id": self.run_manifest.run_id,
                "logical_agent_id": request.logical_agent_id,
                "physical_goal_id": persisted.physical_goal_id,
                "request_id": request.request_id,
                "request_sha256": request.agent_owned_sha256,
                "accepted_at": persisted.accepted_at,
                "stream_revision": event.revision,
                "checkpoint_event_sha256": event.event_sha256,
                "checkpoint_document_sha256": canonical_digest(event_document),
            }


def _build_market_cycle_runtime_locked(
    *,
    runtime_root: Path | str = DEFAULT_RUNTIME_ROOT,
    theory_package: Path | str | None = None,
    expected_theory_identity: TheoryIdentity = CURRENT_THEORY_IDENTITY,
    clock: ClockPort | None = None,
    allow_public_collection: bool = False,
    recover_interrupted_closure: bool = False,
) -> MarketCycleRuntime:
    """Verify identities and wire adapters; public acquisition is explicit opt-in."""

    if type(allow_public_collection) is not bool:
        raise MarketCycleRuntimeError("PUBLIC_COLLECTION_MODE_INVALID")
    if type(recover_interrupted_closure) is not bool:
        raise MarketCycleRuntimeError("RUN_CLOSURE_RECOVERY_MODE_INVALID")

    try:
        identity = require_supported_theory_identity(expected_theory_identity)
    except TheoryIdentityError as exc:
        raise MarketCycleRuntimeError("THEORY_IDENTITY_UNSUPPORTED") from exc
    root = Path(runtime_root).absolute()
    if theory_package is None and identity != CURRENT_THEORY_IDENTITY:
        raise MarketCycleRuntimeError(
            "THEORY_PACKAGE_REQUIRED: non-default identity requires an explicit package"
        )
    package_path = (
        DEFAULT_THEORY_PACKAGE if theory_package is None else Path(theory_package)
    )
    if not package_path.is_dir():
        raise MarketCycleRuntimeError(
            "THEORY_PACKAGE_REQUIRED: pass the expected frozen theory directory"
        )
    package = FileTheoryPackageLoader(package_path).load(identity)
    implementation_identity = current_implementation_identity()
    manifest = _read_run_manifest(
        root,
        theory_manifest_sha256=package.identity.manifest_digest,
        implementation_sha256=implementation_identity,
        expected_contract_identity=_runtime_contract_identity(identity),
        recover_interrupted_closure=recover_interrupted_closure,
    )
    experiment_policy: ExperimentPolicyV1 | None = None
    if identity == V332_THEORY_IDENTITY:
        policy_path = root / EXPERIMENT_POLICY_RELATIVE_PATH
        try:
            policy_path.lstat()
        except FileNotFoundError:
            if (
                len(manifest.experiment_identity) == 64
                and all(
                    character in "0123456789abcdef"
                    for character in manifest.experiment_identity
                )
            ):
                raise MarketCycleRuntimeError("EXPERIMENT_POLICY_MISSING")
        else:
            experiment_policy = _read_experiment_policy(root, manifest)
        if allow_public_collection and (
            experiment_policy is None
            or not experiment_policy.public_data_authorized
        ):
            raise MarketCycleRuntimeError("PUBLIC_COLLECTION_NOT_AUTHORIZED_BY_POLICY")
    gate = RunManifestGate(root, manifest, expected_theory_identity=identity)
    verified_memory = load_verified_memory_context(
        root, expected_theory_identity=identity
    )
    runtime_clock = SystemUTCMonotonicClock() if clock is None else clock
    if not callable(runtime_clock) or not callable(
        getattr(runtime_clock, "monotonic_ns", None)
    ):
        raise MarketCycleRuntimeError("RUNTIME_CLOCK_PORT_INVALID")
    cycles_root = root / "cycles"
    raw_store = FileRawCaptureStore(root)
    repository = FileCycleRepository(
        cycles_root,
        raw_capture_verifier=raw_store,
    )
    transport = OkxPublicTransport(raw_sink=raw_store, clock=runtime_clock)
    profile_service = None
    if identity == CURRENT_THEORY_IDENTITY:
        market_data: MarketDataPort = OkxOptionalContextMarketData(
            core=OkxBaselineMarketData(transport=transport),
            transport=transport,
        )
    else:
        if manifest.market_contract_identity != HYPE_OKX_CONTRACT_IDENTITY:
            raise MarketCycleRuntimeError(
                "V332_MARKET_DATA_PROFILE_NOT_ADMITTED:"
                f"{manifest.market_contract_identity}"
            )
        profile_service = build_hype_data_profile_service(raw_store=raw_store)
        market_data = AssetDataProfileMarketDataAdapter(
            service=profile_service,
            profile_id=HYPE_OKX_PROFILE_ID,
            collector=(
                HypeOkxPublicCollector(transport=transport)
                if allow_public_collection
                else None
            ),
        )
    outcome = OkxMarkOutcome(
        transport=transport,
        clock=runtime_clock,
        allow_public_collection=(
            True if identity == CURRENT_THEORY_IDENTITY else allow_public_collection
        ),
    )
    decision_context = None
    if experiment_policy is not None and experiment_policy.local_paper_authorized:
        if profile_service is None or experiment_policy.paper_account is None:
            raise MarketCycleRuntimeError("V332_PAPER_CONTEXT_CONFIGURATION_INVALID")
        attention_repository = FileAttentionRepository(root / "attention")
        decision_context = PaperDecisionContextProvider(
            ledger=FilePaperLedger(root / "paper"),
            profiles=profile_service,
            profile_id=HYPE_OKX_PROFILE_ID,
            account_id=str(experiment_policy.paper_account["account_id"]),
            paper_account_policy=experiment_policy.paper_account,
            experiment_policy_sha256=experiment_policy.policy_sha256,
            attention_repository=attention_repository,
            attention_service=AttentionService(attention_repository),
            cycle_repository=repository,
        )
    mailbox = LocalMarketCycleAgentMailbox(
        cycles_root,
        clock=runtime_clock,
        local_paper_authorized=bool(
            experiment_policy is not None
            and experiment_policy.local_paper_authorized
        ),
        decision_context=decision_context,
    )
    controller_state = FileControllerState(
        root,
        run_id=manifest.run_id,
        run_manifest_identity_sha256=manifest.identity_sha256,
        run_manifest_raw_sha256=manifest.initial_open_raw_sha256,
        theory_manifest_sha256=manifest.theory_manifest_sha256,
        implementation_sha256=manifest.implementation_sha256,
        contract_identity=manifest.contract_identity,
        market_contract_identity=manifest.market_contract_identity,
        experiment_identity=manifest.experiment_identity,
        clock=runtime_clock,
        allow_initialize=manifest.status == "OPEN",
    )
    application_service = CycleService(
        market_data=market_data,
        agent=mailbox,
        clock=runtime_clock,
        repository=repository,
        outcome=outcome,
        theory_fragments=package.hot_path_fragments,
        verified_memory=verified_memory,
        controller_dispatch=controller_state,
        decision_context=decision_context,
    )
    goal_registry_gate = None
    if (
        identity == V332_THEORY_IDENTITY
        and experiment_policy is not None
        and isinstance(experiment_policy.paper_account, Mapping)
    ):
        goal_registry_gate = V332GoalRegistryGate(
            root,
            paper_account_policy=experiment_policy.paper_account,
        )
    service = ManifestBoundCycleService(
        service=application_service,
        repository=repository,
        gate=gate,
        goal_registry_gate=goal_registry_gate,
        goal_window_create_required=bool(
            identity == V332_THEORY_IDENTITY
            and experiment_policy is not None
            and experiment_policy.phase == "CONTINUITY_24H"
        ),
    )
    return MarketCycleRuntime(
        service=service,
        repository=repository,
        mailbox=mailbox,
        controller_state=controller_state,
        identity=package.identity,
        run_manifest=manifest,
        experiment_policy=experiment_policy,
        verified_memory=verified_memory,
        runtime_root=root,
    )


def build_market_cycle_runtime(
    *,
    runtime_root: Path | str = DEFAULT_RUNTIME_ROOT,
    theory_package: Path | str | None = None,
    expected_theory_identity: TheoryIdentity = CURRENT_THEORY_IDENTITY,
    clock: ClockPort | None = None,
    allow_public_collection: bool = False,
    recover_interrupted_closure: bool = False,
) -> MarketCycleRuntime:
    """Compose one runtime while closure excludes constructor-side writes."""

    with run_lifecycle_lock(runtime_root):
        return _build_market_cycle_runtime_locked(
            runtime_root=runtime_root,
            theory_package=theory_package,
            expected_theory_identity=expected_theory_identity,
            clock=clock,
            allow_public_collection=allow_public_collection,
            recover_interrupted_closure=recover_interrupted_closure,
        )


__all__ = [
    "AGENT_FIRST_CONTRACT_IDENTITY",
    "V332_RUNTIME_CONTRACT_IDENTITY",
    "DEFAULT_RUNTIME_ROOT",
    "DEFAULT_THEORY_PACKAGE",
    "EXPERIMENT_POLICY_RELATIVE_PATH",
    "CYCLE_RUN_BINDING_RELATIVE_PATH",
    "CYCLE_RUN_BINDING_SCHEMA_ID",
    "CYCLE_RUN_BINDING_SCHEMA_VERSION",
    "FileControllerState",
    "FrozenRunManifest",
    "ManifestBoundCycleService",
    "MEMORY_CONTEXT_RELATIVE_PATH",
    "MEMORY_CONTEXT_SCHEMA_ID",
    "MEMORY_CONTEXT_SCHEMA_VERSION",
    "MarketCycleRuntime",
    "MarketCycleRuntimeError",
    "RUN_MANIFEST_RELATIVE_PATH",
    "RUN_MANIFEST_SCHEMA_ID",
    "RUN_MANIFEST_SCHEMA_VERSION",
    "RUN_IDENTITY_REGISTRY_DIRECTORY",
    "RUN_IDENTITY_SEAL_SCHEMA_ID",
    "RUN_IDENTITY_SEAL_SCHEMA_VERSION",
    "RUN_CLOSURE_RELATIVE_PATH",
    "RUN_CLOSURE_SCHEMA_ID",
    "RUN_CLOSURE_SCHEMA_VERSION",
    "RUN_LIFECYCLE_LOCK_RELATIVE_PATH",
    "RunManifestGate",
    "build_market_cycle_runtime",
    "current_implementation_identity",
    "initialize_v332_run",
    "initialize_run_identity_seal",
    "load_verified_memory_context",
    "run_identity_seal_document",
    "run_identity_seal_path",
    "run_lifecycle_lock",
]
