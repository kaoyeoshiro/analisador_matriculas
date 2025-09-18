#!/usr/bin/env python3
"""
Implementa sistema de feedback local como alternativa ao Google Forms
Cria relatórios em formato legível e exportável
"""
import os
import sys
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Adiciona o diretório src ao path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

class LocalFeedbackManager:
    def __init__(self, feedback_dir: Path = None):
        """Inicializa o gerenciador de feedback local"""
        if feedback_dir is None:
            feedback_dir = Path(__file__).parent.parent / "feedback_data"

        self.feedback_dir = feedback_dir
        self.feedback_dir.mkdir(exist_ok=True)

        # Arquivos de dados
        self.json_file = self.feedback_dir / "feedback_completo.json"
        self.csv_file = self.feedback_dir / "feedback_relatorio.csv"
        self.summary_file = self.feedback_dir / "resumo_feedback.txt"

    def salvar_feedback(self, feedback_data: Dict[str, Any]) -> bool:
        """Salva feedback nos formatos JSON, CSV e resumo texto"""
        try:
            # 1. Adiciona ao arquivo JSON
            self._salvar_json(feedback_data)

            # 2. Adiciona ao arquivo CSV
            self._salvar_csv(feedback_data)

            # 3. Atualiza resumo em texto
            self._atualizar_resumo()

            print(f"✅ Feedback salvo localmente em: {self.feedback_dir}")
            return True

        except Exception as e:
            print(f"❌ Erro ao salvar feedback local: {e}")
            return False

    def _salvar_json(self, feedback_data: Dict[str, Any]):
        """Salva no arquivo JSON"""
        try:
            # Carrega dados existentes
            if self.json_file.exists():
                with open(self.json_file, 'r', encoding='utf-8') as f:
                    dados = json.load(f)
            else:
                dados = {"feedbacks": [], "metadados": {"criado_em": datetime.now().isoformat()}}

            # Adiciona novo feedback
            feedback_data["id"] = len(dados["feedbacks"]) + 1
            feedback_data["salvo_em"] = datetime.now().isoformat()
            dados["feedbacks"].append(feedback_data)
            dados["metadados"]["ultimo_update"] = datetime.now().isoformat()
            dados["metadados"]["total"] = len(dados["feedbacks"])

            # Salva
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"Erro ao salvar JSON: {e}")

    def _salvar_csv(self, feedback_data: Dict[str, Any]):
        """Salva no arquivo CSV"""
        try:
            # Campos do CSV
            campos = ['timestamp', 'tipo', 'descricao', 'processo', 'modelo', 'versao']

            # Verifica se arquivo existe
            arquivo_existe = self.csv_file.exists()

            with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=campos)

                # Escreve cabeçalho se arquivo novo
                if not arquivo_existe:
                    writer.writeheader()

                # Escreve dados
                row = {campo: feedback_data.get(campo, '') for campo in campos}
                writer.writerow(row)

        except Exception as e:
            print(f"Erro ao salvar CSV: {e}")

    def _atualizar_resumo(self):
        """Atualiza arquivo de resumo em texto"""
        try:
            if not self.json_file.exists():
                return

            with open(self.json_file, 'r', encoding='utf-8') as f:
                dados = json.load(f)

            feedbacks = dados.get("feedbacks", [])

            # Estatísticas
            total = len(feedbacks)
            erros = len([f for f in feedbacks if f.get("tipo") == "ERRO"])
            sucessos = len([f for f in feedbacks if f.get("tipo") == "SUCESSO_AUTO"])

            # Últimos 5 feedbacks
            ultimos = sorted(feedbacks, key=lambda x: x.get("timestamp", ""), reverse=True)[:5]

            # Gera resumo
            resumo = f"""
RELATÓRIO DE FEEDBACK - SISTEMA DE MATRÍCULAS CONFRONTANTES
============================================================

Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

ESTATÍSTICAS GERAIS:
- Total de feedbacks: {total}
- Erros reportados: {erros}
- Sucessos automáticos: {sucessos}
- Taxa de erro: {(erros/total*100):.1f}% (se > 0)

ÚLTIMOS 5 FEEDBACKS:
{'-' * 50}
"""

            for i, feedback in enumerate(ultimos, 1):
                resumo += f"""
{i}. [{feedback.get('timestamp', 'N/A')}] {feedback.get('tipo', 'N/A')}
   Processo: {feedback.get('processo', 'N/A')}
   Modelo: {feedback.get('modelo', 'N/A')}
   Descrição: {feedback.get('descricao', 'N/A')[:100]}...
"""

            resumo += f"""

ARQUIVOS GERADOS:
- JSON completo: {self.json_file.name}
- Planilha CSV: {self.csv_file.name}
- Este resumo: {self.summary_file.name}

Para análises detalhadas, abra o arquivo CSV no Excel ou Google Sheets.
"""

            with open(self.summary_file, 'w', encoding='utf-8') as f:
                f.write(resumo)

        except Exception as e:
            print(f"Erro ao gerar resumo: {e}")

    def gerar_relatorio_completo(self) -> str:
        """Gera relatório completo para análise"""
        try:
            if not self.json_file.exists():
                return "Nenhum feedback encontrado."

            with open(self.json_file, 'r', encoding='utf-8') as f:
                dados = json.load(f)

            feedbacks = dados.get("feedbacks", [])

            if not feedbacks:
                return "Nenhum feedback encontrado."

            # Análise por modelo
            modelos = {}
            for f in feedbacks:
                modelo = f.get("modelo", "Desconhecido")
                if modelo not in modelos:
                    modelos[modelo] = {"total": 0, "erros": 0}
                modelos[modelo]["total"] += 1
                if f.get("tipo") == "ERRO":
                    modelos[modelo]["erros"] += 1

            # Análise temporal (últimos 7 dias)
            from datetime import datetime, timedelta
            agora = datetime.now()
            uma_semana = agora - timedelta(days=7)

            recentes = [f for f in feedbacks
                       if datetime.fromisoformat(f.get("timestamp", "1970-01-01 00:00:00")) > uma_semana]

            relatorio = f"""
RELATÓRIO DETALHADO DE FEEDBACK
===============================

Total de feedbacks: {len(feedbacks)}
Feedbacks últimos 7 dias: {len(recentes)}

ANÁLISE POR MODELO LLM:
{'-' * 30}
"""

            for modelo, stats in modelos.items():
                taxa_erro = (stats["erros"] / stats["total"] * 100) if stats["total"] > 0 else 0
                relatorio += f"• {modelo}: {stats['total']} usos, {stats['erros']} erros ({taxa_erro:.1f}%)\n"

            relatorio += f"""

FEEDBACK MAIS RECENTE:
{'-' * 30}
{feedbacks[-1] if feedbacks else 'Nenhum'}

ARQUIVOS DISPONÍVEIS:
{'-' * 30}
• JSON: {self.json_file}
• CSV: {self.csv_file}
• Resumo: {self.summary_file}
"""

            return relatorio

        except Exception as e:
            return f"Erro ao gerar relatório: {e}"

def implementar_sistema_local():
    """Implementa sistema de feedback local"""
    print("=" * 80)
    print("IMPLEMENTANDO SISTEMA DE FEEDBACK LOCAL")
    print("=" * 80)

    # Cria gerenciador
    feedback_manager = LocalFeedbackManager()

    print(f"📁 Diretório de feedback: {feedback_manager.feedback_dir}")
    print()

    # Testa o sistema
    print("🧪 TESTANDO SISTEMA LOCAL...")

    # Teste 1: Feedback de erro
    feedback_erro = {
        "tipo": "ERRO",
        "descricao": "Erro na análise de matrícula 12345.6789.10 - Confrontantes não identificados",
        "processo": "12345.6789.10",
        "modelo": "google/gemini-2.5-pro",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "versao": "1.0.0"
    }

    success1 = feedback_manager.salvar_feedback(feedback_erro)
    print(f"   Erro salvo: {'✅' if success1 else '❌'}")

    # Teste 2: Feedback de sucesso
    feedback_sucesso = {
        "tipo": "SUCESSO_AUTO",
        "descricao": "Análise bem-sucedida - Todos os confrontantes identificados",
        "processo": "98765.4321.00",
        "modelo": "google/gemini-2.5-pro",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "versao": "1.0.0"
    }

    success2 = feedback_manager.salvar_feedback(feedback_sucesso)
    print(f"   Sucesso salvo: {'✅' if success2 else '❌'}")

    # Gera relatório
    print("\n📊 RELATÓRIO GERADO:")
    print(feedback_manager.gerar_relatorio_completo())

    # Instruções para integração
    print("\n" + "=" * 80)
    print("COMO INTEGRAR NO SISTEMA PRINCIPAL:")
    print("=" * 80)
    print("1. Substitua a chamada para Google Forms por feedback local")
    print("2. Use LocalFeedbackManager no lugar do Google Forms")
    print("3. Monitore os arquivos gerados para análise")
    print("4. Implemente envio manual dos dados para Google Sheets (opcional)")

    return feedback_manager

def main():
    """Função principal"""
    manager = implementar_sistema_local()

    # Mostra arquivos gerados
    print(f"\n📁 ARQUIVOS GERADOS:")
    for arquivo in manager.feedback_dir.glob("*"):
        tamanho = arquivo.stat().st_size
        print(f"   {arquivo.name}: {tamanho} bytes")

if __name__ == "__main__":
    main()