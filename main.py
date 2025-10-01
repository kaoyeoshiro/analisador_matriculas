#!/usr/bin/env python3
"""Ponto de entrada principal do Sistema de Análise de Matrículas Confrontantes."""

import importlib
import importlib.util
import sys
from pathlib import Path

_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_SRC_DIR = _BASE_DIR / "src"

for candidate in (_BASE_DIR, _SRC_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path and candidate.exists():
        sys.path.insert(0, candidate_str)


def run():
    try:
        module = importlib.import_module("src.main")
    except ModuleNotFoundError:
        fallback_path = _SRC_DIR / "main.py"
        if not fallback_path.exists():
            raise
        spec = importlib.util.spec_from_file_location("src.main", fallback_path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

    if hasattr(module, "main"):
        module.main()
    else:
        raise AttributeError("O módulo src.main não define a função main().")


if __name__ == "__main__":
    run()
