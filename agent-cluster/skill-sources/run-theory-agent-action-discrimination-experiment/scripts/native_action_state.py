#!/usr/bin/env python3
"""Thin stable entrypoint for the project-owned action E0A CLI."""

from __future__ import annotations

from trade_system.theory_paper_v2.presentation.action_discrimination_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
