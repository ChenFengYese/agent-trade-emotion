from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from typing import Any, Mapping

from tests.test_theory_paper_v2_v31_authorization import _make_chain
from trade_system.theory_paper_v2.domain.contracts.canonical import self_digest
from trade_system.theory_paper_v2.domain.governance import (
    v31_application_authority_projection_v2 as projection_v2,
)
from trade_system.theory_paper_v2.infrastructure.authority.v31_current_research import (
    load_v31_active_authorization_chain,
)


def _typed_authority_node_paths(value: Any, path: tuple[str, ...] = ()) -> list[str]:
    matches: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            current = (*path, str(key))
            if key == "external_execution_authority" and isinstance(nested, Mapping):
                if nested == {"kind": "STRING", "value": "NONE_LOCAL_SIMULATION"}:
                    matches.append(".".join(current))
            matches.extend(_typed_authority_node_paths(nested, current))
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            matches.extend(_typed_authority_node_paths(nested, (*path, str(index))))
    return matches


class V31ApplicationAuthorityProjectionV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls.project = Path(cls._temporary_directory.name)
        _make_chain(cls.project)
        cls.loaded_chain = load_v31_active_authorization_chain(cls.project)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def test_full_loader_chain_projects_deep_copied_exact_five(self) -> None:
        self.assertEqual(
            projection_v2.V31_FULL_LOADER_CHAIN_KEYS,
            set(self.loaded_chain),
        )

        projected = projection_v2.project_v31_application_authority_chain_v2(
            self.loaded_chain
        )

        self.assertEqual(
            projection_v2.V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS,
            tuple(projected),
        )
        self.assertNotIn("qualification_receipts", projected)
        self.assertNotIn("predecessor_authority", projected)
        for key in projection_v2.V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS:
            self.assertEqual(self.loaded_chain[key], projected[key])
            self.assertIsNot(self.loaded_chain[key], projected[key])

    def test_q7_typed_authority_nodes_are_data_not_business_permissions(self) -> None:
        q7 = self.loaded_chain["qualification_receipts"]["Q7"]
        collision_paths = _typed_authority_node_paths(q7)
        self.assertGreater(len(collision_paths), 0)

        projected = projection_v2.project_v31_application_authority_chain_v2(
            self.loaded_chain
        )

        self.assertEqual(
            "NONE_LOCAL_SIMULATION",
            projected["authority"]["external_execution_authority"],
        )
        self.assertFalse(projected["authority"]["paper_trading"])

    def test_direct_business_authority_expansion_is_rejected(self) -> None:
        for field, value in (
            ("paper_trading", True),
            ("external_execution_authority", "NONE_E0"),
            ("executable", True),
        ):
            with self.subTest(field=field):
                forged = copy.deepcopy(self.loaded_chain)
                authority = {
                    key: nested
                    for key, nested in forged["authority"].items()
                    if key != "authority_digest"
                }
                authority[field] = value
                forged["authority"] = self_digest(authority, "authority_digest")

                with self.assertRaisesRegex(
                    projection_v2.V31ApplicationAuthorityProjectionError,
                    "V31_APPLICATION_AUTHORITY_RELATION_OR_PERMISSION_INVALID",
                ):
                    projection_v2.project_v31_application_authority_chain_v2(
                        forged
                    )

    def test_five_document_mapping_cannot_masquerade_as_full_loader_output(
        self,
    ) -> None:
        projected_only = {
            key: copy.deepcopy(self.loaded_chain[key])
            for key in projection_v2.V31_APPLICATION_AUTHORITY_DOCUMENT_KEYS
        }

        with self.assertRaisesRegex(
            projection_v2.V31ApplicationAuthorityProjectionError,
            "V31_APPLICATION_AUTHORITY_FULL_CHAIN_INVALID",
        ):
            projection_v2.project_v31_application_authority_chain_v2(
                projected_only
            )


if __name__ == "__main__":
    unittest.main()
