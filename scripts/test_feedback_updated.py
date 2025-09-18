#!/usr/bin/env python3
"""
Teste do sistema de feedback atualizado
Testa se o envio para Google Forms está funcionando
"""
import os
import sys
from pathlib import Path

# Adiciona o diretório src ao path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from feedback_system import FeedbackSystem

def test_feedback_system():
    """Testa o sistema de feedback atualizado"""
    print("=" * 80)
    print("TESTE DO SISTEMA DE FEEDBACK ATUALIZADO")
    print("=" * 80)

    # Inicializa o sistema
    feedback_system = FeedbackSystem(
        app_version="1.0.0",
        modelo_llm="google/gemini-2.5-pro"
    )

    print("✅ Sistema de feedback inicializado")
    print(f"📋 URL do formulário: {feedback_system.google_form_url}")
    print(f"📋 IDs dos campos: {feedback_system.form_fields}")
    print()

    # Teste 1: Feedback de erro
    print("🧪 TESTE 1: Enviando feedback de ERRO...")
    success_erro = feedback_system.enviar_feedback_teste(
        tipo="ERRO",
        descricao="Teste de erro do sistema atualizado - Análise de matrícula falhando",
        processo="12345.6789.10"
    )

    print(f"   Resultado: {'✅ SUCESSO' if success_erro else '❌ FALHOU'}")
    print()

    # Teste 2: Feedback de sucesso
    print("🧪 TESTE 2: Enviando feedback de SUCESSO_AUTO...")
    success_auto = feedback_system.enviar_feedback_teste(
        tipo="SUCESSO_AUTO",
        descricao="Teste de sucesso automático - Sistema funcionando corretamente",
        processo="98765.4321.00"
    )

    print(f"   Resultado: {'✅ SUCESSO' if success_auto else '❌ FALHOU'}")
    print()

    # Resultado final
    print("=" * 80)
    print("RESULTADO FINAL")
    print("=" * 80)

    if success_erro and success_auto:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("✅ Sistema de feedback está funcionando corretamente")
    elif success_erro or success_auto:
        print("⚠️  ALGUNS TESTES PASSARAM")
        print("⚠️  Verifique os logs para mais detalhes")
    else:
        print("❌ TODOS OS TESTES FALHARAM")
        print("❌ Verifique a configuração do Google Forms")

    return success_erro and success_auto

if __name__ == "__main__":
    test_feedback_system()