#!/usr/bin/env python3
"""Ponto de entrada principal do Sistema de Análise de Matrículas Confrontantes."""

import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    base_dir = Path(__file__).resolve().parent
    src_dir = base_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

from src.main import main as run_app


def run() -> None:
    run_app()


if __name__ == "__main__":
    run()
