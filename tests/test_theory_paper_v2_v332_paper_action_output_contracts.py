from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from trade_system.theory_paper_v2.domain.contracts.canonical import (
    canonical_bytes,
    loads_json_strict,
)
from trade_system.theory_paper_v2.domain.market_cycle.paper import (
    BRACKET_ACTIVATION_POLICY,
    BRACKET_EXIT_POLICY,
    PaperExecutionIntentV1,
)
from trade_system.theory_paper_v2.infrastructure.market_cycle.paper_intent_mailbox import (
    LocalPaperExecutionIntentMailbox,
    PaperExecutionIntentMailboxError,
    paper_action_space_contract,
)
from trade_system.theory_paper_v2.v32_durable_json import write_once_json


class V332PaperActionOutputContractTests(unittest.TestCase):
    def _assert_external_wire_order(self, fields: list[str]) -> None:
        document = {field: field for field in fields}
        external_agent_bytes = (
            json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        self.assertEqual(canonical_bytes(document) + b"\n", external_agent_bytes)

    @staticmethod
    def _agent_request(root: Path, cycle_id: str) -> str:
        packet = {
            "cycle_id": cycle_id,
            "paper_context": {
                "paper_context_sha256": "3" * 64,
                "ledger_head": {
                    "revision": 1,
                    "record_sha256": "4" * 64,
                },
                "paper_account_policy": {
                    "max_decision_loss": "50",
                    "max_position_notional": "500",
                    "max_observed_drawdown": "100",
                    "cost_model": {"model_id": "paper-cost-v1"},
                },
                "account": {
                    "account_id": "hype-paper",
                    "owner_logical_agent_id": "HYPE_TRADER",
                    "owner_agent_generation": 1,
                    "permitted_symbol": "HYPE-USDT-SWAP",
                    "positions": [
                        {
                            "symbol": "HYPE-USDT-SWAP",
                            "quantity": "0",
                        }
                    ],
                },
            },
        }
        packet_sha256 = hashlib.sha256(canonical_bytes(packet)).hexdigest()
        write_once_json(
            root / cycle_id / "transport" / "agent-request.json",
            {"packet": packet, "packet_sha256": packet_sha256},
        )
        return packet_sha256

    @staticmethod
    def _issue(
        root: Path, cycle_id: str
    ) -> tuple[LocalPaperExecutionIntentMailbox, object, str]:
        request_sha256 = V332PaperActionOutputContractTests._agent_request(
            root, cycle_id
        )
        mailbox = LocalPaperExecutionIntentMailbox(
            root, clock=lambda: "2026-08-13T08:02:00Z"
        )
        issued = mailbox.issue_request(
            cycle_id,
            logical_agent_id="HYPE_TRADER",
            agent_generation=1,
            physical_task_id="codex:/root/hype-paper-agent",
            decision_sha256="1" * 64,
            issued_at="2026-08-13T08:00:30Z",
            valid_until="2026-08-13T08:06:00Z",
        )
        return mailbox, issued, request_sha256

    def test_fresh_execution_request_publishes_13_command_and_bracket_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cycles"
            cycle_id = "hype-decision-1"
            mailbox, issued, decision_request_sha256 = self._issue(
                root, cycle_id
            )
            contract = issued.document["output_contract"]
            self.assertEqual("1.3.0", issued.document["output_schema_version"])
            self.assertEqual("1.3.0", contract["schema_version"])
            self.assertEqual(
                "1.3.0", contract["fixed_values"]["schema_version"]
            )
            self.assertEqual(
                "CREATE_ONCE_NO_REWRITE",
                contract["write_semantics"]["mode"],
            )
            self.assertEqual(
                sorted(contract["exact_fields"]), contract["exact_fields"]
            )
            self.assertEqual(
                sorted(contract["command_shape"]["exact_fields"]),
                contract["command_shape"]["exact_fields"],
            )
            self.assertEqual(
                sorted(contract["bracket_shape"]["exact_fields"]),
                contract["bracket_shape"]["exact_fields"],
            )
            self._assert_external_wire_order(contract["exact_fields"])
            self._assert_external_wire_order(
                contract["command_shape"]["exact_fields"]
            )
            self._assert_external_wire_order(
                contract["bracket_shape"]["exact_fields"]
            )
            self.assertIn(
                "56.06",
                contract["canonical_decimal_format"]["valid_examples"],
            )
            self.assertIn(
                "56.060",
                contract["canonical_decimal_format"]["invalid_examples"],
            )
            self.assertEqual(
                "paper-cost-v1",
                contract["command_shape"]["fixed_values"]["cost_model_id"],
            )
            self.assertEqual(
                BRACKET_ACTIVATION_POLICY,
                contract["bracket_shape"]["fixed_values"][
                    "activation_policy"
                ],
            )
            self.assertEqual(
                BRACKET_EXIT_POLICY,
                contract["bracket_shape"]["fixed_values"]["exit_policy"],
            )
            self.assertIn(
                "TOP_LEVEL_COMMAND_AND_BRACKET_ENTRY_EQUAL_INTENT_ID",
                contract["command_shape"]["dynamic_bindings"]["command_id"],
            )
            self.assertEqual(
                "UNIQUE_SAFE_IDENTIFIER_NOT_EQUAL_TO_INTENT_ID",
                contract["bracket_shape"]["protective_stop"]["command_id"],
            )
            for field_name in (
                "evidence_delta",
                "activation",
                "hard_invalidation",
            ):
                with self.subTest(field_name=field_name):
                    self.assertEqual(
                        "STRING",
                        contract["field_constraints"][field_name]["json_type"],
                    )
            self.assertEqual(
                ["LIMIT"],
                contract["paper_action_space"]["protected_flat_entry"][
                    "entry_command_types"
                ],
            )
            self.assertIn(
                "MARKET",
                contract["paper_action_space"]["standalone_command_types"],
            )
            self.assertEqual(
                "UNSUPPORTED_USE_BOUNDED_LIMIT_OR_NON_EXECUTABLE_REFERENCE",
                contract["paper_action_space"]["protected_flat_entry"][
                    "market_with_bracket_status"
                ],
            )
            binding_stages = contract["paper_action_space"]["binding_stages"]
            self.assertIn(
                "paper_context_sha256",
                binding_stages["available_in_predecision_context"],
            )
            self.assertIn(
                "request.decision_sha256",
                binding_stages["bound_in_postdecision_request"],
            )
            self.assertEqual(
                ["execution_intent_request_sha256"],
                binding_stages["bound_after_request_is_sealed"],
            )
            self.assertIn(
                "intent.authored_at",
                binding_stages["agent_authored_in_intent"],
            )
            self.assertIn(
                "intent.valid_until",
                binding_stages["agent_authored_in_intent"],
            )
            agent_request = loads_json_strict(
                (
                    root
                    / cycle_id
                    / "transport"
                    / "agent-request.json"
                ).read_bytes()
            )
            paper_context = agent_request["packet"]["paper_context"]
            self.assertEqual(
                paper_action_space_contract(
                    paper_context, symbol="HYPE-USDT-SWAP"
                ),
                contract["paper_action_space"],
            )

            fixed = contract["fixed_values"]
            intent = PaperExecutionIntentV1(
                intent_id="hype-transition-wait-1",
                execution_intent_request_sha256=issued.request_sha256,
                decision_request_sha256=decision_request_sha256,
                paper_context_sha256=fixed["paper_context_sha256"],
                ledger_head_record_sha256=fixed[
                    "ledger_head_record_sha256"
                ],
                decision_cycle_id=fixed["decision_cycle_id"],
                decision_sha256=fixed["decision_sha256"],
                account_id=fixed["account_id"],
                logical_agent_id=fixed["logical_agent_id"],
                agent_generation=fixed["agent_generation"],
                expected_account_version=fixed["expected_account_version"],
                symbol=fixed["symbol"],
                authored_at="2026-08-13T08:01:00Z",
                valid_until="2026-08-13T08:05:00Z",
                action="WAIT",
                episode_id="hype-episode-1",
                transition_id="hype-transition-wait-1",
                tranche_id=None,
                role="CASH_FLAT",
                pre_state={"signed_quantity": "0"},
                target_state={"signed_quantity": "0"},
                position_delta={"signed_quantity_change": "0"},
                evidence_delta="No activation evidence justifies exposure.",
                activation="Remain flat until the stated evidence changes.",
                hard_invalidation="Reassess before this intent expires.",
                risk_budget={
                    "maximum_loss": "50",
                    "notional_cap": "500",
                    "max_observed_drawdown": "100",
                },
                command=None,
                bracket=None,
            )
            self.assertEqual(sorted(intent.to_dict()), contract["exact_fields"])
            ordered_intent = {
                field: intent.to_dict()[field]
                for field in contract["exact_fields"]
            }
            external_agent_bytes = (
                json.dumps(
                    ordered_intent,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            self.assertEqual(
                canonical_bytes(intent.to_dict()) + b"\n",
                external_agent_bytes,
            )
            mailbox.intent_path(cycle_id).write_bytes(external_agent_bytes)
            self.assertEqual(intent, mailbox.receive(cycle_id).intent)

    def test_mailbox_recomputes_and_rejects_a_tampered_output_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cycles"
            cycle_id = "hype-decision-tampered"
            mailbox, _, _ = self._issue(root, cycle_id)
            path = mailbox.intent_request_path(cycle_id)
            document = loads_json_strict(path.read_bytes())
            document["output_contract"]["fixed_values"]["symbol"] = "BTC-USDT-SWAP"
            path.write_bytes(canonical_bytes(document) + b"\n")
            with self.assertRaisesRegex(
                PaperExecutionIntentMailboxError,
                "OUTPUT_CONTRACT_INVALID",
            ):
                mailbox.receive(cycle_id)


if __name__ == "__main__":
    unittest.main()
