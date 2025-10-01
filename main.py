#!/usr/bin/env python3
"""Ponto de entrada principal do Sistema de Análise de Matrículas Confrontantes."""

import importlib
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def run():
    module = importlib.import_module("src.main")
    if hasattr(module, "main"):
        module.main()
    else:
        raise AttributeError("O módulo src.main não define a função main().")


if __name__ == "__main__":
    run()
