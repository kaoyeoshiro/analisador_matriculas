#!/usr/bin/env python3
"""Script de teste para o sistema de atualização"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from updater import create_updater

def test_updater():
    print("=== Teste do Sistema de Atualização ===")

    # Cria o updater
    updater = create_updater()
    updater.silent = False  # Ativa logs detalhados

    print(f"Configurações:")
    print(f"  Repo: {updater.repo_owner}/{updater.repo_name}")
    print(f"  Versão atual: {updater.current_version}")
    print(f"  Executável procurado: {updater.executable_name}")
    print(f"  Diretório da app: {updater.app_dir}")
    print(f"  É executável compilado: {updater.is_executable}")
    print(f"  Caminho do executável: {updater.current_exe_path}")
    print()

    # Testa verificação de atualizações
    print("Verificando atualizações...")
    update_info = updater.check_for_updates()

    if update_info:
        print("SUCESSO: Nova atualizacao encontrada!")
        print(f"  Versao: {update_info['version']}")
        print(f"  Asset: {update_info['asset_name']}")
        print(f"  URL: {update_info['download_url']}")
        print(f"  Data: {update_info['published_at']}")
        print("\nNotas da versao:")
        print(update_info['release_notes'][:200] + "..." if len(update_info['release_notes']) > 200 else update_info['release_notes'])
    else:
        print("ERRO: Nenhuma atualizacao encontrada ou erro na verificacao")

    print("\n=== Teste finalizado ===")

if __name__ == "__main__":
    test_updater()