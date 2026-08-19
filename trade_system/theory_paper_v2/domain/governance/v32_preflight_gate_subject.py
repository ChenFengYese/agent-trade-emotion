"""Typed, capability-limited subjects for V3.2 Q0-Q8 preflight gates.

These subjects do not claim that a public source, Codex delivery, or outcome
monitor was exercised.  They bind a fixed set of production implementation
files and already typed authority/support documents so Infrastructure can
replay readiness without accepting a free-form ``PASS`` document.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
import re
from typing import Any, Mapping

from ..contracts.canonical import self_digest, verify_self_digest
from .v32_qualification_identity import (
    EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID,
    EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID,
    FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID,
    FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID,
    FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID,
    FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID,
    FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID,
    TOMBSTONED_V32_RUN_IDS,
    V32QualificationIdentityError,
    is_exact_historical_v32_qualification_preflight_identity_v1,
    validate_v32_active_qualification_identity_v1,
    validate_v32_run_id_syntax_v1,
)


class V32PreflightGateSubjectError(ValueError):
    """A typed V3.2 preflight subject failed an exact invariant."""


SCHEMA_ID = "theory_paper_v32_typed_preflight_gate_subject_v1"
DIGEST_FIELD = "typed_preflight_gate_subject_digest"
SCHEMA_VERSION = "1.0.0"
QUALIFICATION_PROFILE = "QUALIFICATION_PHASE_A"
TARGET_PROFILE = "TARGET_PHASE_A"
GATE_IDS = tuple(f"Q{index}" for index in range(9))
ACTUAL_CAPABILITY_GATE_IDS = frozenset({"Q2", "Q3", "Q6"})

# These are explicit production roots, not test evidence.  A path change is an
# authority change and therefore requires a newly committed workspace freeze.
GATE_IMPLEMENTATION_PATHS = {
    "Q0": (
        "trade_system/theory_paper_v2/infrastructure/authority/v311_successor_current_research_v2.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v31_current_research.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_current_research.py",
    ),
    "Q1": (
        "trade_system/theory_paper_v2/infrastructure/authority/v31_runtime_closure_v2.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_workspace_freeze.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q2": (
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification_controller.py",
        "trade_system/theory_paper_v2/application/v32_durable_source_replay.py",
        "trade_system/theory_paper_v2/application/v32_public_evidence_port.py",
        "trade_system/theory_paper_v2/domain/governance/v32_qualification_identity.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_actual_capability_attempt_ports.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_runtime_namespace.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_secure_write_once_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_okx_public_bundle_transport.py",
        "trade_system/theory_paper_v2/infrastructure/v32_public_https_route.py",
        "trade_system/theory_paper_v2/infrastructure/v32_public_source_collector.py",
        "trade_system/theory_paper_v2/presentation/v32_qualification_composition.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q3": (
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification_controller.py",
        "trade_system/theory_paper_v2/domain/governance/v32_qualification_identity.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_actual_capability_attempt_ports.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_runtime_namespace.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_secure_write_once_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_current_root_agent_mailbox.py",
        "trade_system/theory_paper_v2/presentation/v32_qualification_composition.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q4": (
        "trade_system/theory_paper_v2/application/v32_agent_semantic_compiler.py",
        "trade_system/theory_paper_v2/domain/v32_dynamic_action_plan.py",
    ),
    "Q5": (
        "trade_system/theory_paper_v2/application/v32_cycle_acceptance.py",
        "trade_system/theory_paper_v2/application/v32_prospective_runtime.py",
        "trade_system/theory_paper_v2/domain/v32_run_genesis.py",
        "trade_system/theory_paper_v2/infrastructure/v32_analysis_material_adapter.py",
        "trade_system/theory_paper_v2/infrastructure/v32_authorized_revision_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_cycle_audit_completion_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_dynamic_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_analysis_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_audit_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_run_control_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_runtime_clock.py",
        "trade_system/theory_paper_v2/presentation/v32_target_run_composition.py",
        "trade_system/theory_paper_v2/presentation/v32_target_wake_composition.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q6": (
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification_controller.py",
        "trade_system/theory_paper_v2/application/v32_outcome_tick_composition.py",
        "trade_system/theory_paper_v2/application/v32_public_evidence_port.py",
        "trade_system/theory_paper_v2/domain/governance/v32_qualification_identity.py",
        "trade_system/theory_paper_v2/domain/v32_qualification_monitor_probe.py",
        "trade_system/theory_paper_v2/domain/v32_runtime_support_contracts.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_actual_capability_attempt_ports.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_monitor_probe_store.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_qualification_runtime_namespace.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_secure_write_once_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_outcome_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_okx_public_outcome_adapter.py",
        "trade_system/theory_paper_v2/infrastructure/v32_outcome_tick_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_public_https_route.py",
        "trade_system/theory_paper_v2/presentation/v32_qualification_composition.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q7": (
        "trade_system/theory_paper_v2/application/v32_actual_capability_qualification_controller.py",
        "trade_system/theory_paper_v2/application/v32_prospective_runtime.py",
        "trade_system/theory_paper_v2/domain/v32_agent_lifecycle.py",
        "trade_system/theory_paper_v2/domain/v32_run_genesis.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_current_research.py",
        "trade_system/theory_paper_v2/infrastructure/v32_analysis_material_adapter.py",
        "trade_system/theory_paper_v2/infrastructure/v32_authorized_revision_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_cycle_audit_completion_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_analysis_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_local_audit_lane.py",
        "trade_system/theory_paper_v2/infrastructure/v32_run_control_store.py",
        "trade_system/theory_paper_v2/infrastructure/v32_runtime_clock.py",
        "trade_system/theory_paper_v2/presentation/v32_target_run_composition.py",
        "trade_system/theory_paper_v2/presentation/v32_target_wake_composition.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
    "Q8": (
        "trade_system/theory_paper_v2/domain/governance/v32_authorization.py",
        "trade_system/theory_paper_v2/infrastructure/authority/v32_current_research.py",
        "trade_system/theory_paper_v2/v32_durable_json.py",
    ),
}
# Exact semantic identities of permanently tombstoned historical
# qualifications.  Most are durable FAILED_CLOSED; the Agent-window case is
# EXPIRED_TERMINAL with its original RUNNING/REQUESTED bytes preserved.
# Historical replay is digest-bound below; these values are never an alternate
# path policy for a new run.
FAILED_PRE_NETWORK_SUBJECT_DIGESTS = {
    "Q0": "e8332544d0e879dedd910c415ddacf86769b401c5d8fb5772e90fe72d3555b61",
    "Q1": "05f5540d7fffd5d8b56329cab06e2fb34a2529db6554843f368d6823b78dba1e",
    "Q2": "3f20103635a037b1c8bae2346d48dc8c3663650371d0bb4f4893d5c37ff105e1",
    "Q3": "5edac6bcbf6b76768694b1c85a5547f4fd475f577bf342eb2535bb09cd69092a",
    "Q4": "1eb1ba35d19b508e1f90c91a38f1a0c44394dbf7eab7e5586cf3c52d513685b8",
    "Q5": "74f8531c9cedd6e5a366bbdc0102df5575fce2e2722e0e541466a777976aaf9d",
    "Q6": "41db47cf86587d8842801ba63c4afac2eb29abfe48dea691982b41f5c974865a",
    "Q7": "da3e942e706c7498c475deac62f07f282251d1083cceb0edb27bb2b6aafdee09",
    "Q8": "24a76ac376d0ec46fae1afb7c312fbf474784305449e519dacc8bf9fb1d7ae58",
}
FAILED_PUBLIC_SOURCE_SUBJECT_DIGESTS = {
    "Q0": "d91ddeadb763248901c7bc869d2fbac5cd10e87dc40e6de2a51ef4ad429ebd80",
    "Q1": "20e529f00c3b874871f63e25a4490dbc88587254d108fdf51d15860a1cb92f25",
    "Q2": "ea16fe30277c3f85d76cb8b6972003b1c3eebbbb55fdc91b86e7f27a65d4a9aa",
    "Q3": "e811495e58696b3255bd9b37c1ab9e78d835f3d401a9b32131b559a86dc854a1",
    "Q4": "f7d838088355972a1d78eb78ad54c41e8d53ed5aed6e21e4feed42ce2365b73a",
    "Q5": "88482c4948543d78049456a16a85ae70c766efbea287aa883b18175e56c69541",
    "Q6": "595b4f8105cd6968aa052a3296bea9da30ce4a4e77ef6a97139ce2d09aa897b9",
    "Q7": "0c83a7d87074b98a84c8d35c21f08be92a7f236960987dce145ec8c743f205ff",
    "Q8": "b20ee91ccedef5ec4261f7ccbe84eeaccbd2ab37cca816fcd23b830648c92ea6",
}
FAILED_OPENAPI_ROUTE_SUBJECT_DIGESTS = {
    "Q0": "08260604940763f0fd48e5166dee11681eebc3d94f338982d4b0ac2cf98395a9",
    "Q1": "777c2578dde311752bc71eff9104fd07e1369a976b5d5c60cd682b1e2d22ceab",
    "Q2": "8efbf49206c22d091e5797eddc0d00b3c7c5c79b3dcde83d04a370b1133f9134",
    "Q3": "a1a9416a44af9f9c064476aa8bed5506f2d9341beea21cfee028e5c3dfe6e661",
    "Q4": "717851d39f8f1d81858676fb0a58cd6c3615506a736e8c563f4db47870a4c66e",
    "Q5": "e6bc642a0fbaadaf923dacdaf851aa164a9bdf07763359dadd609ed75bfdda27",
    "Q6": "cf871f85837cb5ff7f9ade030511327df1038c65401804c97fc671347e87e50a",
    "Q7": "6b48c69a27934500132b60d46cdcc703ccbdba81c52f0442d61025aee87f6531",
    "Q8": "d28b834294ec10bf9d459904e56840f8e1b7b4980e3f48fe29a2b334252f5eda",
}
FAILED_FUNDING_TIME_SUBJECT_DIGESTS = {
    "Q0": "be0a88f38fc351b6c15c43ebab91e4af666bbaef804d49d043d337d72ae0c359",
    "Q1": "befff6eb68b1ed28af66d249f57465f1d63d18574230802444aa7a209deae00d",
    "Q2": "e94702b1722b5c7650b51543c4eb357c4cc9c41c7552ef54b4a7049daa236370",
    "Q3": "da4d933fca02055d3fa5628be65884e08b05b5bca2eeb02f9423d145a8070eb3",
    "Q4": "58a486b69d48fb409001853b73dfcf2393c3d03ec87e18f59500271f2f698cda",
    "Q5": "0c4ab60a056ee9a07b0a7625315a8600302f8529c0f1633d5a9d2ec3c86dd82a",
    "Q6": "f5c1dff05fc10a207e478c6b7b9d58b82f2e5ddf127e4cf26638f5020109208f",
    "Q7": "bf16a6185ed81e4622ccae3b047fc6e3c66d974b77ab79dc8fe72f88191f1087",
    "Q8": "2bdf85b371c30c3f50e4265463d9f7ecda61f29edbf2a37cb25e424ca021ee30",
}
FAILED_MATERIALIZATION_SUBJECT_DIGESTS = {
    "Q0": "7a1593bdd53ecab39ed84627fc85aba8ffdf63fcb1754907b1bb5345381ec6d8",
    "Q1": "0f0a30b6ea23d9e4de5ea250985035f203820153aba4dbb54d91a467768ef288",
    "Q2": "11c694b27898f2e45e2de2513fd69f6c5c00b73389afe0d13139188c8e798aca",
    "Q3": "8c50fcecfb4835792601464d2a0cb1d728fef333773546fcb6e9acb1a3d74c7e",
    "Q4": "33a7570009cb47447b901476f4ec21a57d7392d6cb377fe307533cbcb3016594",
    "Q5": "e219d840628cf913b7cfbfe6523bcae493c4def8d1fa4e96f47ecd857d0c5a0e",
    "Q6": "8ca529bb3c41eccb8816c99728327c33a2a4f1b791c95697a7a4e2151fffb78c",
    "Q7": "07ddfad46b397e0c44c31df4056b0af32f15dbaf83c34f251ba02f7b14ecae83",
    "Q8": "9d309eeec9553cc5d0bb8f095cf8cb3e10a12d38372e0b40189e07265ffec10b",
}
FAILED_CONTEXT_CAPACITY_SUBJECT_DIGESTS = {
    "Q0": "bcc926e9b407a1cf7cbf95c27b5778c0d9288936478a2c1bca8a9dd4ecd0f533",
    "Q1": "e1e5a480d3139fa2b840c8bd51cb5fa9b10e84f035792585bc7e5951c7665433",
    "Q2": "c0b7c1a36428657921035440c62932d61a30ea76163f794d40c706d5521ebc91",
    "Q3": "e2708e5b2e4501f1fcf6a4759ee97094cb763660b3bf7068c0a3a49e33e81848",
    "Q4": "c762f7db204cb9b709f9308b59c143ee74a164457d91964f9089f51e8816ab8a",
    "Q5": "6a48a2bb9e60eb7095cc3928e9a41cb80f0ce7693e3ec59dea89998886b1d6fc",
    "Q6": "f310225ee53426cce64922ab4016bc0c505520bc6ea856e6f1f9980e9788cb05",
    "Q7": "927b56b68c8ebdd302b19fd45b94e0acb82d82a3e05fd4a489f97435e895eae0",
    "Q8": "61742f50e6a0a1a6d07ed15be67068de057bd61bf75ae5ec54bba690c68990dd",
}
EXPIRED_AGENT_WINDOW_SUBJECT_DIGESTS = {
    "Q0": "9d5b0063574c37242eaa975811a06b6118f1610e8531b3abc45a64f94699b787",
    "Q1": "9a8f1e7cb52cb7d7e9f32ff0d34d00d41920c989392ecb177ec782f58007ca58",
    "Q2": "0136f3c8dbd845b7b9f874601c03fc4be3c1e764bd27d467144e643179455bf9",
    "Q3": "49e7a4887d073e9826614b239a0bf703b422f04bb5c255cb492a7eb3d062c01a",
    "Q4": "b3a5a0251bf6fa0a48e2d290a56b1bfc930f6f6b94b6a63b33096a67339afba5",
    "Q5": "102c7e4fb18c59691f8bb386416b2727ebe128f10f2aecfabeede46ae331518e",
    "Q6": "620b2374ee303bb26dee58e1e50e4f5e8d0d68f60f60ad4a166f77f4a3bfbc10",
    "Q7": "83d3b69d1dcd59a3601748ccea9d1aeae2013d6f4c02737634db0ef6bcf6a626",
    "Q8": "7a8ba30b8ad5abbe6269c303faa8d5b3d26f0d945a7637be3d040bf0039873c8",
}
EXPIRED_CURRENT_CODEX_SUBJECT_DIGESTS = {
    "Q0": "dd07c9f043f3bf88efd2f5d28437e029b394d5086bebb22ea538d9436d55581b",
    "Q1": "5a4d2ae5c081d841d9a61d62c7f4ef000547b88e716aa6f27adfc57e34b74e47",
    "Q2": "850920f1d1d1b19f66fb1eac0eccbb0d4378b533a65349601f04f2db199b6337",
    "Q3": "3acf59e372e089b88f79950b3ad0b5faaa0b25da0f7e815ff269857106a0f0a7",
    "Q4": "4448a50796948ce0a21d7e38d8c023fc76b79760300dbc7bee8ab2cdf6b86f15",
    "Q5": "69eb0de71b9f16a4b6de2e61559896d5346eb4ad23f784e30ab3247c844eccd5",
    "Q6": "2647d06eba335d53cdd1027e4fdfd8fc1c61db9478d42937dbced074e9975cb1",
    "Q7": "9cd9f09388987e634e1fd07bcf0ea9719767759dc67867054f7ffb14410fdec4",
    "Q8": "eb0d8be47a7e3a1a1fe228e97d68aba9d04bd09216dec325483c036b411f7053",
}
FAILED_CONCURRENT_MATERIALIZATION_SUBJECT_DIGESTS = {
    "Q0": "609bdea681f6f397314a09b7e1f53eb15890432b6e8729054e8690f6fcefce8b",
    "Q1": "edbe75521ece128514b2cb8ecb989575d2e45169ad16b8b2a687b1ac848bf6ae",
    "Q2": "57246acf0cb29ac9b40871b511788cfaf32fcea6aa760bc37b6e67b45a013a77",
    "Q3": "6ee7a2bb1ae4c23c4108b2549f18c1f7fd5aa7b54e2b3ac70efa90556d1e56a6",
    "Q4": "aefe096de9363642f31346bcaba8764386cc05ae6949feea8c45c0d79e373eb0",
    "Q5": "e2b4b1950f833cd36f623f3d048758b15086b6eecfe3775bd47fe0f20fe0ede4",
    "Q6": "b6e437fadd49308f922d0d76e5a2ef076d8fa5c999d49d3f4c243ff5527533a1",
    "Q7": "fb1b3a4ddf4ba34ddbd1433de82a45240c27240e0a7de283b24f5b0e055e208b",
    "Q8": "260ff3d6f6a51babe97ddb1762034815345b37cb334953e4385f08bfaafc41d8",
}
_HISTORICAL_SUBJECT_DIGESTS_BY_QUALIFICATION_RUN_ID = {
    # The first failed qualification used the earlier pre-network closure.
    # The second reached its sole public request and is frozen separately.
    "v32-qualification-btcusdt-20260808t150343z": (
        FAILED_PRE_NETWORK_SUBJECT_DIGESTS
    ),
    FAILED_V32_PUBLIC_SOURCE_QUALIFICATION_RUN_ID: (
        FAILED_PUBLIC_SOURCE_SUBJECT_DIGESTS
    ),
    FAILED_V32_OPENAPI_ROUTE_QUALIFICATION_RUN_ID: (
        FAILED_OPENAPI_ROUTE_SUBJECT_DIGESTS
    ),
    FAILED_V32_FUNDING_TIME_QUALIFICATION_RUN_ID: (
        FAILED_FUNDING_TIME_SUBJECT_DIGESTS
    ),
    FAILED_V32_MATERIALIZATION_QUALIFICATION_RUN_ID: (
        FAILED_MATERIALIZATION_SUBJECT_DIGESTS
    ),
    FAILED_V32_CONTEXT_CAPACITY_QUALIFICATION_RUN_ID: (
        FAILED_CONTEXT_CAPACITY_SUBJECT_DIGESTS
    ),
    EXPIRED_V32_AGENT_WINDOW_QUALIFICATION_RUN_ID: (
        EXPIRED_AGENT_WINDOW_SUBJECT_DIGESTS
    ),
    EXPIRED_V32_CURRENT_CODEX_QUALIFICATION_RUN_ID: (
        EXPIRED_CURRENT_CODEX_SUBJECT_DIGESTS
    ),
    FAILED_V32_CONCURRENT_MATERIALIZATION_QUALIFICATION_RUN_ID: (
        FAILED_CONCURRENT_MATERIALIZATION_SUBJECT_DIGESTS
    ),
}

GATE_ANCHOR_ROLES = {
    "Q0": ("predecessor_authority",),
    "Q1": ("runtime_manifest",),
    "Q2": ("experiment_contract", "runtime_manifest"),
    "Q3": ("experiment_contract", "runtime_manifest"),
    "Q4": ("experiment_contract", "runtime_manifest"),
    "Q5": ("experiment_contract", "runtime_manifest"),
    "Q6": ("clock_policy", "outcome_adapter_contract", "runtime_manifest"),
    "Q7": ("experiment_contract", "runtime_manifest"),
    "Q8": ("experiment_contract", "runtime_manifest", "theory_approval"),
}

GATE_VERIFICATION_KINDS = {
    "Q0": "LEGACY_OR_PREDECESSOR_AUTHORITY_FULL_REPLAY_ANCHOR",
    "Q1": "RUNTIME_CLOSURE_AND_WORKSPACE_PHYSICAL_REPLAY_ANCHOR",
    "Q2": "PUBLIC_SOURCE_RAW_FIRST_PATH_PREFLIGHT_ONLY",
    "Q3": "CURRENT_CODEX_DURABLE_MAILBOX_PATH_PREFLIGHT_ONLY",
    "Q4": "SEMANTIC_COMPILER_AND_ACTION_PATH_REPLAY_ANCHOR",
    "Q5": "ACCEPTANCE_STORE_AND_RECOVERY_PATH_REPLAY_ANCHOR",
    "Q6": "FIXED_OUTCOME_MONITOR_PATH_PREFLIGHT_ONLY",
    "Q7": "APPLICATION_PROJECTION_AND_TYPED_BUNDLE_PATH_REPLAY_ANCHOR",
    "Q8": "PUBLIC_ONLY_NON_EXECUTION_BOUNDARY_REPLAY_ANCHOR",
}

PRODUCTION_ROOT_PATHS = tuple(
    sorted(
        {
            "trade_system/theory_paper_v2/infrastructure/authority/v32_authority_lifecycle.py",
            *(
                path
                for paths in GATE_IMPLEMENTATION_PATHS.values()
                for path in paths
            ),
        }
    )
)

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_BINDING_FIELDS = frozenset(
    {"path", "schema_id", "digest_field", "semantic_digest", "physical_sha256"}
)
_BOUNDARY_FIELDS = frozenset(
    {
        "source_scope",
        "external_execution_authority",
        "executable",
        "account_access",
        "account_data_accessed",
        "paper_trading",
        "live_trading",
        "order_submission",
        "order_data_accessed",
        "credential_access",
        "funds_access",
        "portfolio_mutation",
    }
)
_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "subject_id",
        "gate_id",
        "profile",
        "run_id",
        "target_run_id",
        "evaluated_at",
        "verification_kind",
        "implementation_bindings",
        "implementation_path_count",
        "anchor_bindings",
        "anchor_count",
        "fresh_process_required",
        "network_probe_performed",
        "actual_capability_claimed",
        "subject_status",
        "claim_ceiling",
        *_BOUNDARY_FIELDS,
        DIGEST_FIELD,
    }
)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise V32PreflightGateSubjectError(code)
    return value


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX_64.fullmatch(value) is None:
        raise V32PreflightGateSubjectError(code)
    return value


def _time(value: Any, code: str) -> str:
    text = _text(value, code)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V32PreflightGateSubjectError(code) from exc
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).isoformat().replace("+00:00", "Z") != text
    ):
        raise V32PreflightGateSubjectError(code)
    return text


def _relative(value: Any, code: str, *, python_only: bool = False) -> str:
    text = _text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or any(part in {"", ".", ".."} for part in path.parts)
        or (python_only and path.suffix != ".py")
    ):
        raise V32PreflightGateSubjectError(code)
    return text


def _binding(value: Any, code: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_FIELDS:
        raise V32PreflightGateSubjectError(code)
    return {
        "path": _relative(value.get("path"), code),
        "schema_id": _text(value.get("schema_id"), code),
        "digest_field": _text(value.get("digest_field"), code),
        "semantic_digest": _digest(value.get("semantic_digest"), code),
        "physical_sha256": _digest(value.get("physical_sha256"), code),
    }


def _boundary() -> dict[str, Any]:
    return {
        "source_scope": "PUBLIC_NON_ACCOUNT_ONLY",
        "external_execution_authority": "NONE_LOCAL_SIMULATION",
        "executable": False,
        "account_access": False,
        "account_data_accessed": False,
        "paper_trading": False,
        "live_trading": False,
        "order_submission": False,
        "order_data_accessed": False,
        "credential_access": False,
        "funds_access": False,
        "portfolio_mutation": False,
    }


def build_v32_typed_preflight_gate_subject_v1(
    *,
    subject_id: str,
    gate_id: str,
    profile: str,
    run_id: str,
    target_run_id: str,
    evaluated_at: str,
    implementation_bindings: Mapping[str, str],
    anchor_bindings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if gate_id not in GATE_IDS or profile not in {
        QUALIFICATION_PROFILE,
        TARGET_PROFILE,
    }:
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_IDENTITY_INVALID")
    run = _text(run_id, "V32_PREFLIGHT_SUBJECT_RUN_INVALID")
    target = _text(target_run_id, "V32_PREFLIGHT_SUBJECT_RUN_INVALID")
    try:
        if profile == QUALIFICATION_PROFILE:
            target, run = validate_v32_active_qualification_identity_v1(
                target_run_id=target,
                qualification_run_id=run,
            )
        else:
            target = validate_v32_run_id_syntax_v1(target)
            run = validate_v32_run_id_syntax_v1(run)
            if target in TOMBSTONED_V32_RUN_IDS:
                raise V32QualificationIdentityError(
                    "V32_QUALIFICATION_RUN_ID_TOMBSTONED"
                )
    except V32QualificationIdentityError as exc:
        raise V32PreflightGateSubjectError(
            "V32_PREFLIGHT_SUBJECT_RUN_INVALID"
        ) from exc
    if (
        (profile == QUALIFICATION_PROFILE and run == target)
        or (profile == TARGET_PROFILE and run != target)
        or (profile == TARGET_PROFILE and gate_id in ACTUAL_CAPABILITY_GATE_IDS)
    ):
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_RUN_INVALID")
    supplied_paths = (
        tuple(implementation_bindings)
        if isinstance(implementation_bindings, Mapping)
        else ()
    )
    required_paths = GATE_IMPLEMENTATION_PATHS[gate_id]
    if (
        not isinstance(implementation_bindings, Mapping)
        or tuple(implementation_bindings) != required_paths
    ):
        raise V32PreflightGateSubjectError(
            "V32_PREFLIGHT_SUBJECT_IMPLEMENTATION_INVALID"
        )
    implementations = {
        _relative(path, "V32_PREFLIGHT_SUBJECT_IMPLEMENTATION_INVALID", python_only=True): _digest(
            implementation_bindings[path],
            "V32_PREFLIGHT_SUBJECT_IMPLEMENTATION_INVALID",
        )
        for path in required_paths
    }
    roles = GATE_ANCHOR_ROLES[gate_id]
    if not isinstance(anchor_bindings, Mapping) or tuple(anchor_bindings) != roles:
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_ANCHOR_INVALID")
    anchors = {
        role: _binding(
            anchor_bindings[role], "V32_PREFLIGHT_SUBJECT_ANCHOR_INVALID"
        )
        for role in roles
    }
    return self_digest(
        {
            "schema_id": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "subject_id": _text(subject_id, "V32_PREFLIGHT_SUBJECT_ID_INVALID"),
            "gate_id": gate_id,
            "profile": profile,
            "run_id": run,
            "target_run_id": target,
            "evaluated_at": _time(
                evaluated_at, "V32_PREFLIGHT_SUBJECT_TIME_INVALID"
            ),
            "verification_kind": GATE_VERIFICATION_KINDS[gate_id],
            "implementation_bindings": implementations,
            "implementation_path_count": len(implementations),
            "anchor_bindings": anchors,
            "anchor_count": len(anchors),
            "fresh_process_required": True,
            "network_probe_performed": False,
            "actual_capability_claimed": False,
            "subject_status": "TYPED_PREFLIGHT_READY",
            "claim_ceiling": "PREFLIGHT_ONLY_NOT_ACTUAL_CAPABILITY_OR_RUN_RESULT",
            **_boundary(),
        },
        DIGEST_FIELD,
    )


def verify_v32_typed_preflight_gate_subject_v1(
    document: Mapping[str, Any],
) -> str:
    if not isinstance(document, Mapping) or set(document) != _FIELDS:
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_INVALID")
    try:
        supplied = verify_self_digest(document, DIGEST_FIELD)
        if is_exact_historical_v32_qualification_preflight_identity_v1(
            profile=document.get("profile"),
            run_id=document.get("run_id"),
            target_run_id=document.get("target_run_id"),
        ):
            gate_id = document.get("gate_id")
            historical_digests = _HISTORICAL_SUBJECT_DIGESTS_BY_QUALIFICATION_RUN_ID.get(
                document.get("run_id")
            )
            if (
                gate_id not in GATE_IDS
                or historical_digests is None
                or supplied != historical_digests[gate_id]
            ):
                raise V32PreflightGateSubjectError(
                    "V32_PREFLIGHT_HISTORICAL_SUBJECT_INVALID"
                )
            return supplied
        rebuilt = build_v32_typed_preflight_gate_subject_v1(
            subject_id=document["subject_id"],
            gate_id=document["gate_id"],
            profile=document["profile"],
            run_id=document["run_id"],
            target_run_id=document["target_run_id"],
            evaluated_at=document["evaluated_at"],
            implementation_bindings=document["implementation_bindings"],
            anchor_bindings=document["anchor_bindings"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, V32PreflightGateSubjectError):
            raise
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_INVALID") from exc
    if dict(document) != rebuilt or supplied != rebuilt[DIGEST_FIELD]:
        raise V32PreflightGateSubjectError("V32_PREFLIGHT_SUBJECT_INVALID")
    return supplied


__all__ = [
    "ACTUAL_CAPABILITY_GATE_IDS",
    "DIGEST_FIELD",
    "GATE_ANCHOR_ROLES",
    "GATE_IDS",
    "GATE_IMPLEMENTATION_PATHS",
    "EXPIRED_AGENT_WINDOW_SUBJECT_DIGESTS",
    "EXPIRED_CURRENT_CODEX_SUBJECT_DIGESTS",
    "FAILED_CONCURRENT_MATERIALIZATION_SUBJECT_DIGESTS",
    "FAILED_CONTEXT_CAPACITY_SUBJECT_DIGESTS",
    "FAILED_FUNDING_TIME_SUBJECT_DIGESTS",
    "FAILED_MATERIALIZATION_SUBJECT_DIGESTS",
    "FAILED_OPENAPI_ROUTE_SUBJECT_DIGESTS",
    "FAILED_PUBLIC_SOURCE_SUBJECT_DIGESTS",
    "FAILED_PRE_NETWORK_SUBJECT_DIGESTS",
    "PRODUCTION_ROOT_PATHS",
    "SCHEMA_ID",
    "V32PreflightGateSubjectError",
    "build_v32_typed_preflight_gate_subject_v1",
    "verify_v32_typed_preflight_gate_subject_v1",
]
