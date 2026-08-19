from __future__ import annotations

import unittest

from trade_system.theory_paper_v2.infrastructure.authority import (
    AuthorityAdapterError,
    E0ExternalExecutionDenyAdapter,
)


class E0ExternalExecutionDenyTests(unittest.TestCase):
    def test_paper_and_live_objects_are_never_accepted_in_e0(self) -> None:
        adapter = E0ExternalExecutionDenyAdapter()
        for method in (adapter.submit_paper, adapter.submit_live):
            with self.subTest(method=method.__name__):
                with self.assertRaisesRegex(
                    AuthorityAdapterError,
                    "EXTERNAL_EXECUTION_FORBIDDEN_E0",
                ):
                    method(
                        {
                            "system_mode": "E0_OFFLINE_COUNTERFACTUAL",
                            "external_execution_authority": "NONE_E0",
                            "executable": False,
                        }
                    )


if __name__ == "__main__":
    unittest.main()
