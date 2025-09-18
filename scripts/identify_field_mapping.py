#!/usr/bin/env python3
"""
Script para identificar o mapeamento correto dos campos do Google Forms
Usa os IDs encontrados no console e testa cada um individualmente
"""
import os
import sys
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Carrega variáveis de ambiente
load_dotenv(project_root / ".env")

class FieldMappingIdentifier:
    def __init__(self):
        # URL do formulário
        self.form_url = os.getenv("GOOGLE_FORM_URL", "")
        self.view_url = self.form_url.replace("/formResponse", "/viewform")

        # IDs encontrados no console (em ordem de aparição)
        self.discovered_ids = [
            "entry.579089408",
            "entry.597505189",
            "entry.207190791",
            "entry.943393649",
            "entry.1649732056"
        ]

        # Headers básicos
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Origin': 'https://docs.google.com',
            'Referer': self.view_url
        }

    def test_single_field(self, entry_id: str, test_value: str = "teste") -> dict:
        """Testa um único campo para ver se aceita valores"""
        print(f"🧪 Testando {entry_id} com valor '{test_value}'...")

        # Testa apenas com esse campo
        data = {entry_id: test_value}

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=15,
                allow_redirects=True
            )

            result = {
                'entry_id': entry_id,
                'status_code': response.status_code,
                'success': response.status_code == 200,
                'content_preview': response.text[:200],
                'redirected': len(response.history) > 0,
                'final_url': response.url
            }

            print(f"   Status: {response.status_code} | Success: {result['success']}")
            return result

        except Exception as e:
            print(f"   Erro: {e}")
            return {
                'entry_id': entry_id,
                'status_code': 0,
                'success': False,
                'error': str(e)
            }

    def test_field_combinations(self):
        """Testa diferentes combinações de campos"""
        print("\n🔍 TESTANDO CAMPOS INDIVIDUAIS")
        print("=" * 50)

        # Testa cada campo individualmente
        individual_results = []
        for entry_id in self.discovered_ids:
            result = self.test_single_field(entry_id, "teste_individual")
            individual_results.append(result)
            print()

        # Testa combinações que fazem sentido
        print("\n🔍 TESTANDO COMBINAÇÕES DE CAMPOS")
        print("=" * 50)

        combination_tests = [
            # Teste 1: Primeiro campo como TIPO
            {
                'name': 'TIPO_primeiro',
                'data': {self.discovered_ids[0]: "ERRO"}
            },
            # Teste 2: Último campo como TIPO
            {
                'name': 'TIPO_ultimo',
                'data': {self.discovered_ids[4]: "ERRO"}
            },
            # Teste 3: Combinação básica (assumindo ordem lógica)
            {
                'name': 'combinacao_basica',
                'data': {
                    self.discovered_ids[0]: "ERRO",
                    self.discovered_ids[1]: "Teste de descrição",
                    self.discovered_ids[2]: "google/gemini-2.5-pro"
                }
            },
            # Teste 4: Com campo sentinel
            {
                'name': 'com_sentinel',
                'data': {
                    f"{self.discovered_ids[0]}_sentinel": "",
                    self.discovered_ids[0]: "ERRO",
                    self.discovered_ids[1]: "Teste com sentinel"
                }
            },
            # Teste 5: Todos os campos
            {
                'name': 'todos_campos',
                'data': {
                    self.discovered_ids[0]: "ERRO",
                    self.discovered_ids[1]: "Descrição do problema",
                    self.discovered_ids[2]: "google/gemini-2.5-pro",
                    self.discovered_ids[3]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    self.discovered_ids[4]: "1.0.0"
                }
            }
        ]

        combination_results = []
        for test in combination_tests:
            print(f"🧪 Testando {test['name']}...")

            try:
                response = requests.post(
                    self.form_url,
                    data=test['data'],
                    headers=self.headers,
                    timeout=15,
                    allow_redirects=True
                )

                result = {
                    'name': test['name'],
                    'data': test['data'],
                    'status_code': response.status_code,
                    'success': response.status_code == 200,
                    'content_preview': response.text[:200]
                }

                print(f"   Status: {response.status_code} | Success: {result['success']}")
                combination_results.append(result)

            except Exception as e:
                print(f"   Erro: {e}")
                combination_results.append({
                    'name': test['name'],
                    'success': False,
                    'error': str(e)
                })

            print()

        return individual_results, combination_results

    def analyze_form_page(self):
        """Analisa a página do formulário para tentar identificar a ordem dos campos"""
        print("🔍 ANALISANDO PÁGINA DO FORMULÁRIO...")

        try:
            response = requests.get(self.view_url, headers=self.headers, timeout=15)
            html = response.text

            # Busca por textos que podem indicar os campos
            field_indicators = {
                'tipo': ['tipo', 'category', 'categoria', 'classificação'],
                'descricao': ['descrição', 'description', 'problema', 'detalhe', 'comentário'],
                'modelo': ['modelo', 'model', 'llm', 'engine'],
                'timestamp': ['data', 'timestamp', 'hora'],
                'versao': ['versão', 'version']
            }

            print("   Buscando indicadores na página...")

            # Procura pelos IDs na ordem que aparecem no HTML
            ids_in_order = []
            for entry_id in self.discovered_ids:
                if entry_id in html:
                    position = html.find(entry_id)
                    ids_in_order.append((position, entry_id))

            # Ordena pela posição no HTML
            ids_in_order.sort()

            print("   IDs na ordem que aparecem no HTML:")
            for position, entry_id in ids_in_order:
                print(f"      {entry_id} (posição {position})")

            return [entry_id for _, entry_id in ids_in_order]

        except Exception as e:
            print(f"   Erro ao analisar página: {e}")
            return self.discovered_ids

    def suggest_mapping_from_results(self, individual_results, combination_results):
        """Sugere mapeamento baseado nos resultados dos testes"""
        print("\n🎯 ANÁLISE DOS RESULTADOS E SUGESTÃO DE MAPEAMENTO")
        print("=" * 60)

        # Analisa resultados individuais
        working_fields = [r for r in individual_results if r.get('success', False)]
        failing_fields = [r for r in individual_results if not r.get('success', False)]

        print("CAMPOS QUE FUNCIONAM INDIVIDUALMENTE:")
        for field in working_fields:
            print(f"   ✅ {field['entry_id']}")

        print(f"\nCAMPOS QUE FALHAM INDIVIDUALMENTE:")
        for field in failing_fields:
            print(f"   ❌ {field['entry_id']}")

        # Analisa combinações
        working_combinations = [r for r in combination_results if r.get('success', False)]

        print(f"\nCOMBINAÇÕES QUE FUNCIONAM:")
        for combo in working_combinations:
            print(f"   ✅ {combo['name']}")
            for key, value in combo['data'].items():
                print(f"      {key}: {value}")

        # Sugere mapeamento baseado na análise
        suggested_mapping = self.generate_mapping_suggestion(individual_results, combination_results)

        return suggested_mapping

    def generate_mapping_suggestion(self, individual_results, combination_results):
        """Gera sugestão de mapeamento baseada nos resultados"""

        # Se alguma combinação funcionou, use ela como base
        working_combinations = [r for r in combination_results if r.get('success', False)]

        if working_combinations:
            best_combo = working_combinations[0]

            if best_combo['name'] == 'todos_campos':
                return {
                    'TIPO': self.discovered_ids[0],
                    'DESCRICAO': self.discovered_ids[1],
                    'MODELO': self.discovered_ids[2],
                    'TIMESTAMP': self.discovered_ids[3],
                    'VERSAO': self.discovered_ids[4]
                }

        # Fallback: mapear baseado na ordem mais comum
        return {
            'TIPO': self.discovered_ids[0],       # Primeiro campo geralmente é classificação
            'DESCRICAO': self.discovered_ids[1],  # Segundo campo geralmente é texto longo
            'MODELO': self.discovered_ids[2],     # Terceiro campo
            'TIMESTAMP': self.discovered_ids[3],  # Quarto campo
            'VERSAO': self.discovered_ids[4]      # Quinto campo
        }

    def generate_new_env_config(self, mapping):
        """Gera nova configuração para o .env"""
        config_lines = [
            "# Configurações Google Forms - IDs CORRIGIDOS VIA CONSOLE",
            f"GOOGLE_FORM_URL={self.form_url}"
        ]

        for field_name, entry_id in mapping.items():
            config_lines.append(f"GOOGLE_FORM_FIELD_{field_name}={entry_id}")

        return "\n".join(config_lines)

    def run_complete_analysis(self):
        """Executa análise completa"""
        print("=" * 80)
        print("IDENTIFICADOR DE MAPEAMENTO DE CAMPOS - GOOGLE FORMS")
        print("=" * 80)
        print(f"Formulário: {self.view_url}")
        print(f"IDs encontrados no console: {len(self.discovered_ids)}")
        print()

        for i, entry_id in enumerate(self.discovered_ids, 1):
            print(f"{i}. {entry_id}")
        print()

        # 1. Analisa ordem na página
        ordered_ids = self.analyze_form_page()

        # 2. Testa campos individuais e combinações
        individual_results, combination_results = self.test_field_combinations()

        # 3. Sugere mapeamento
        mapping = self.suggest_mapping_from_results(individual_results, combination_results)

        # 4. Gera config
        new_config = self.generate_new_env_config(mapping)

        print("\n📝 MAPEAMENTO SUGERIDO:")
        print("-" * 40)
        for field_name, entry_id in mapping.items():
            print(f"{field_name:12} -> {entry_id}")

        print(f"\n📝 NOVA CONFIGURAÇÃO .env:")
        print("-" * 40)
        print(new_config)

        # 5. Salva relatório
        self.save_detailed_report(individual_results, combination_results, mapping, new_config)

        return mapping

    def save_detailed_report(self, individual_results, combination_results, mapping, new_config):
        """Salva relatório detalhado"""
        report_path = project_root / "scripts" / "field_mapping_report.txt"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("RELATÓRIO DETALHADO - MAPEAMENTO DE CAMPOS\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"Data: {datetime.now()}\n")
            f.write(f"URL: {self.view_url}\n\n")

            f.write("IDs ENCONTRADOS NO CONSOLE:\n")
            for i, entry_id in enumerate(self.discovered_ids, 1):
                f.write(f"{i}. {entry_id}\n")
            f.write("\n")

            f.write("RESULTADOS DOS TESTES INDIVIDUAIS:\n")
            f.write("-" * 40 + "\n")
            for result in individual_results:
                f.write(f"ID: {result['entry_id']}\n")
                f.write(f"Status: {result['status_code']}\n")
                f.write(f"Sucesso: {result.get('success', False)}\n")
                f.write("-" * 20 + "\n")

            f.write("\nRESULTADOS DOS TESTES DE COMBINAÇÃO:\n")
            f.write("-" * 40 + "\n")
            for result in combination_results:
                f.write(f"Teste: {result['name']}\n")
                f.write(f"Sucesso: {result.get('success', False)}\n")
                if 'data' in result:
                    f.write("Dados enviados:\n")
                    for key, value in result['data'].items():
                        f.write(f"  {key}: {value}\n")
                f.write("-" * 20 + "\n")

            f.write(f"\nMAPEAMENTO FINAL:\n")
            f.write("-" * 40 + "\n")
            for field_name, entry_id in mapping.items():
                f.write(f"{field_name} -> {entry_id}\n")

            f.write(f"\nCONFIGURAÇÃO .env:\n")
            f.write("-" * 40 + "\n")
            f.write(new_config)

        print(f"\n💾 Relatório detalhado salvo em: {report_path}")

def main():
    """Função principal"""
    try:
        identifier = FieldMappingIdentifier()
        mapping = identifier.run_complete_analysis()

        print("\n" + "=" * 80)
        print("✅ ANÁLISE CONCLUÍDA!")
        print("=" * 80)
        print("PRÓXIMOS PASSOS:")
        print("1. Atualize o .env com a configuração sugerida")
        print("2. Execute test_feedback.py novamente")
        print("3. Se ainda houver erro 400, ajuste manualmente o mapeamento")

    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    main()