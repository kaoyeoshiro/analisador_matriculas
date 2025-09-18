#!/usr/bin/env python3
"""
Ponto de entrada principal do Sistema de Análise de Matrículas Confrontantes
"""

import sys
import os
from pathlib import Path

# Adiciona o diretório src ao path para imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Importa e executa o main real
from main import main

if __name__ == "__main__":
    main()