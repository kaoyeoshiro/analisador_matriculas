#!/usr/bin/env python3
"""
Teste final do sistema de feedback com fallback local
"""
import os
import sys
from pathlib import Path

# Adiciona o diretório src ao path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from feedback_system import FeedbackSystem

def test_feedback_final():
    """Testa o sistema de feedback com fallback local"""
    print("TESTE FINAL DO SISTEMA DE FEEDBACK")
    print("=" * 60)

    # Inicializa o sistema
    feedback_system = FeedbackSystem(
        app_version="1.0.0",
        modelo_llm="google/gemini-2.5-pro"
    )

    print("Sistema de feedback inicializado com sucesso")
    print(f"URL do formulario: {feedback_system.google_form_url}")
    print(f"IDs dos campos: {feedback_system.form_fields}")
    print()

    # Teste 1: Feedback de erro
    print("TESTE 1: Enviando feedback de ERRO...")
    success_erro = feedback_system.enviar_feedback_teste(
        tipo="ERRO",
        descricao="Teste de erro - Analise de matricula falhando - Confrontantes nao identificados corretamente",
        processo="12345.6789.10"
    )

    print(f"Resultado: {'SUCESSO' if success_erro else 'FALHOU'}")
    print()

    # Teste 2: Feedback de sucesso
    print("TESTE 2: Enviando feedback de SUCESSO_AUTO...")
    success_auto = feedback_system.enviar_feedback_teste(
        tipo="SUCESSO_AUTO",
        descricao="Teste de sucesso automatico - Sistema funcionando perfeitamente - Todos os confrontantes identificados",
        processo="98765.4321.00"
    )

    print(f"Resultado: {'SUCESSO' if success_auto else 'FALHOU'}")
    print()

    # Verifica arquivos gerados
    feedback_dir = Path(__file__).parent.parent / "feedback_data"
    print("ARQUIVOS DE FEEDBACK GERADOS:")
    print("-" * 40)

    if feedback_dir.exists():
        for arquivo in feedback_dir.glob("*"):
            tamanho = arquivo.stat().st_size
            print(f"{arquivo.name}: {tamanho} bytes")
    else:
        print("Nenhum arquivo encontrado")

    # Resultado final
    print()
    print("=" * 60)
    print("RESULTADO FINAL")
    print("=" * 60)

    if success_erro and success_auto:
        print("TODOS OS TESTES PASSARAM!")
        print("Sistema de feedback esta funcionando corretamente")
        print("Como o Google Forms falhou, os dados estao sendo salvos localmente")
    elif success_erro or success_auto:
        print("ALGUNS TESTES PASSARAM")
        print("Verifique os logs para mais detalhes")
    else:
        print("TODOS OS TESTES FALHARAM")
        print("Verifique a configuracao do sistema")

    print()
    print("PROXIMOS PASSOS:")
    print("1. Verifique os arquivos em feedback_data/")
    print("2. Abra o CSV no Excel para analise")
    print("3. O sistema continuara funcionando mesmo sem Google Forms")

    return success_erro and success_auto

if __name__ == "__main__":
    test_feedback_final()