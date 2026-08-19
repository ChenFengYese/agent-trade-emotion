"""Presentation adapters for Theory Agent research runtimes.

The package initializer is deliberately side-effect free.  Consumers import
the concrete report, CLI, or V3.2 production composition module they need.
Eagerly importing the legacy E0 report graph here would execute unrelated
modules before a V3.2 entrypoint and would make its frozen local-import closure
depend on the legacy dynamic bootstrap path.
"""

__all__: list[str] = []
