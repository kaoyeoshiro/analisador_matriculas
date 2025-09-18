#!/usr/bin/env python3
"""
Teste simplificado do sistema de feedback local
"""
import json
import csv
from pathlib import Path
from datetime import datetime

def criar_sistema_feedback_local():
    """Cria sistema de feedback local funcional"""

    # Diretório de feedback
    feedback_dir = Path(__file__).parent.parent / "feedback_data"
    feedback_dir.mkdir(exist_ok=True)

    print("SISTEMA DE FEEDBACK LOCAL")
    print("=" * 50)
    print(f"Diretorio: {feedback_dir}")

    # Arquivos
    json_file = feedback_dir / "feedback_completo.json"
    csv_file = feedback_dir / "feedback_relatorio.csv"
    summary_file = feedback_dir / "resumo.txt"

    # Teste 1: Salvar feedback de erro
    feedback_erro = {
        "id": 1,
        "tipo": "ERRO",
        "descricao": "Erro na analise de matricula 12345.6789.10 - Confrontantes nao identificados",
        "processo": "12345.6789.10",
        "modelo": "google/gemini-2.5-pro",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "versao": "1.0.0"
    }

    # Teste 2: Salvar feedback de sucesso
    feedback_sucesso = {
        "id": 2,
        "tipo": "SUCESSO_AUTO",
        "descricao": "Analise bem-sucedida - Todos os confrontantes identificados",
        "processo": "98765.4321.00",
        "modelo": "google/gemini-2.5-pro",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "versao": "1.0.0"
    }

    feedbacks = [feedback_erro, feedback_sucesso]

    # Salva JSON
    dados_json = {
        "feedbacks": feedbacks,
        "metadados": {
            "criado_em": datetime.now().isoformat(),
            "total": len(feedbacks)
        }
    }

    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(dados_json, f, indent=2, ensure_ascii=False)

    print(f"JSON salvo: {json_file}")

    # Salva CSV
    campos = ['id', 'timestamp', 'tipo', 'descricao', 'processo', 'modelo', 'versao']

    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        for feedback in feedbacks:
            writer.writerow(feedback)

    print(f"CSV salvo: {csv_file}")

    # Gera resumo
    total = len(feedbacks)
    erros = len([f for f in feedbacks if f["tipo"] == "ERRO"])
    sucessos = len([f for f in feedbacks if f["tipo"] == "SUCESSO_AUTO"])

    resumo = f"""RELATORIO DE FEEDBACK - SISTEMA DE MATRICULAS CONFRONTANTES
=========================================================

Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

ESTATISTICAS:
- Total de feedbacks: {total}
- Erros reportados: {erros}
- Sucessos automaticos: {sucessos}
- Taxa de erro: {(erros/total*100):.1f}%

ULTIMOS FEEDBACKS:
"""

    for feedback in feedbacks:
        resumo += f"""
[{feedback['timestamp']}] {feedback['tipo']}
Processo: {feedback['processo']}
Modelo: {feedback['modelo']}
Descricao: {feedback['descricao'][:80]}...
"""

    resumo += f"""

ARQUIVOS GERADOS:
- Dados completos: {json_file.name}
- Planilha para analise: {csv_file.name}
- Este resumo: {summary_file.name}

COMO USAR:
1. Abra o arquivo CSV no Excel para analise detalhada
2. O arquivo JSON contem todos os dados estruturados
3. Este resumo fornece uma visao geral rapida

NOTA: O Google Forms apresentou erro 400, por isso todos
os feedbacks estao sendo salvos localmente.
"""

    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(resumo)

    print(f"Resumo salvo: {summary_file}")

    print("\nARQUIVOS CRIADOS:")
    for arquivo in feedback_dir.glob("*"):
        tamanho = arquivo.stat().st_size
        print(f"  {arquivo.name}: {tamanho} bytes")

    print(f"\nSUCESSO! Sistema de feedback local implementado.")
    print(f"Verifique os arquivos em: {feedback_dir}")

    return feedback_dir

if __name__ == "__main__":
    criar_sistema_feedback_local()