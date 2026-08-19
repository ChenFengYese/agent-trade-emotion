"""Compatibility metadata mirroring the project's supported Python runtime."""

from setuptools import find_packages, setup


setup(
    name="agent-trade-emotion",
    version="0.1.0",
    description="Point-in-time, paper-only research runtime for the BTCUSDT absorption system",
    packages=find_packages(include=("trade_system", "trade_system.*")),
    python_requires=">=3.11,<3.14",
    extras_require={"market": ["websockets>=12,<16"]},
    entry_points={
        "console_scripts": [
            "trade-system=trade_system.cli:main",
            "market-cycle=trade_system.theory_paper_v2.presentation.market_cycle:main",
            "v332-market-workbench=trade_system.theory_paper_v2.presentation.market_workbench:main",
            "v332-paper-agent=trade_system.theory_paper_v2.presentation.paper_agent:main",
        ]
    },
)
