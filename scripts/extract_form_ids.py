#!/usr/bin/env python3
"""
Script para extrair IDs corretos do Google Forms
Analisa o HTML do formulário para encontrar os entry IDs reais
"""
import os
import sys
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Carrega variáveis de ambiente
load_dotenv(project_root / ".env")

class GoogleFormsIDExtractor:
    def __init__(self):
        # URL base do formulário
        form_url = os.getenv("GOOGLE_FORM_URL", "")
        if not form_url:
            raise ValueError("GOOGLE_FORM_URL não encontrada no .env")

        # Converte para URL de visualização
        self.view_url = form_url.replace("/formResponse", "/viewform")
        self.form_url = form_url

        # Headers para simular navegador
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

    def fetch_form_html(self) -> str:
        """Busca o HTML do formulário"""
        print(f"🔍 Buscando HTML do formulário: {self.view_url}")

        try:
            response = requests.get(self.view_url, headers=self.headers, timeout=30)
            response.raise_for_status()

            print(f"✅ HTML obtido com sucesso ({len(response.text)} caracteres)")
            return response.text

        except Exception as e:
            print(f"❌ Erro ao buscar HTML: {e}")
            return ""

    def extract_entry_ids(self, html: str) -> dict:
        """Extrai todos os entry IDs do HTML"""
        print("\n🔍 Extraindo entry IDs do HTML...")

        entry_ids = {}

        # Padrões para encontrar entry IDs
        patterns = [
            # Padrão 1: name="entry.123456789"
            r'name=["\']?(entry\.\d+)["\']?',
            # Padrão 2: data-name="entry.123456789"
            r'data-name=["\']?(entry\.\d+)["\']?',
            # Padrão 3: "entry.123456789" em qualquer lugar
            r'"(entry\.\d+)"',
            # Padrão 4: 'entry.123456789' em qualquer lugar
            r"'(entry\.\d+)'",
        ]

        all_entries = set()

        for pattern in patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            all_entries.update(matches)

        print(f"📋 Encontrados {len(all_entries)} entry IDs únicos:")
        for entry in sorted(all_entries):
            print(f"   - {entry}")

        return list(sorted(all_entries))

    def analyze_form_structure(self, html: str) -> dict:
        """Analisa a estrutura do formulário para identificar tipos de campo"""
        print("\n🔍 Analisando estrutura do formulário...")

        # Busca por diferentes tipos de input
        field_analysis = {}

        # Padrão para encontrar inputs com context
        input_pattern = r'<[^>]*(?:input|select|textarea)[^>]*name=["\']?(entry\.\d+)["\']?[^>]*>'

        inputs = re.findall(input_pattern, html, re.IGNORECASE | re.DOTALL)

        for entry_id in inputs:
            # Busca o contexto ao redor do entry ID
            context_pattern = rf'.{{0,500}}{re.escape(entry_id)}.{{0,500}}'
            context_match = re.search(context_pattern, html, re.IGNORECASE | re.DOTALL)

            if context_match:
                context = context_match.group(0)

                # Identifica tipo do campo
                field_type = "text"
                if "radio" in context.lower():
                    field_type = "radio"
                elif "checkbox" in context.lower():
                    field_type = "checkbox"
                elif "select" in context.lower():
                    field_type = "select"
                elif "textarea" in context.lower():
                    field_type = "textarea"

                # Tenta extrair label/pergunta
                label_patterns = [
                    r'aria-label=["\']([^"\']+)["\']',
                    r'<label[^>]*>([^<]+)</label>',
                    r'data-value=["\']([^"\']+)["\']',
                ]

                label = "Sem label"
                for label_pattern in label_patterns:
                    label_match = re.search(label_pattern, context, re.IGNORECASE)
                    if label_match and label_match.group(1).strip():
                        label = label_match.group(1).strip()
                        break

                field_analysis[entry_id] = {
                    'type': field_type,
                    'label': label,
                    'context_preview': context[:200] + "..." if len(context) > 200 else context
                }

        return field_analysis

    def suggest_field_mapping(self, field_analysis: dict) -> dict:
        """Sugere mapeamento dos campos baseado na análise"""
        print("\n🎯 Sugerindo mapeamento de campos...")

        mapping_suggestions = {}

        # Palavras-chave para identificar campos
        keywords = {
            'TIPO': ['tipo', 'category', 'categoria', 'status', 'classificação'],
            'DESCRICAO': ['descrição', 'description', 'problema', 'detalhe', 'texto', 'comentário'],
            'MODELO': ['modelo', 'model', 'llm', 'engine', 'ai'],
            'TIMESTAMP': ['timestamp', 'data', 'date', 'tempo', 'hora'],
            'VERSAO': ['versão', 'version', 'ver', 'release']
        }

        for entry_id, analysis in field_analysis.items():
            label_lower = analysis['label'].lower()
            context_lower = analysis['context_preview'].lower()

            # Verifica correspondências
            for field_name, field_keywords in keywords.items():
                for keyword in field_keywords:
                    if keyword in label_lower or keyword in context_lower:
                        if field_name not in mapping_suggestions:
                            mapping_suggestions[field_name] = entry_id
                        break

        return mapping_suggestions

    def generate_new_env_config(self, mapping: dict) -> str:
        """Gera nova configuração para o .env"""
        print("\n📝 Gerando nova configuração...")

        config_lines = [
            "# Configurações Google Forms - IDs CORRIGIDOS",
            f"GOOGLE_FORM_URL={self.form_url}"
        ]

        for field_name, entry_id in mapping.items():
            config_lines.append(f"GOOGLE_FORM_FIELD_{field_name}={entry_id}")

        return "\n".join(config_lines)

    def run_analysis(self):
        """Executa análise completa"""
        print("=" * 80)
        print("EXTRATOR DE IDs DO GOOGLE FORMS - SISTEMA MATRÍCULAS CONFRONTANTES")
        print("=" * 80)
        print(f"Formulário: {self.view_url}")
        print()

        # 1. Busca HTML
        html = self.fetch_form_html()
        if not html:
            print("❌ Não foi possível obter o HTML do formulário")
            return

        # 2. Extrai entry IDs
        entry_ids = self.extract_entry_ids(html)
        if not entry_ids:
            print("❌ Nenhum entry ID encontrado")
            return

        # 3. Analisa estrutura
        field_analysis = self.analyze_form_structure(html)

        print("\n📊 ANÁLISE DETALHADA DOS CAMPOS:")
        print("-" * 60)
        for entry_id, analysis in field_analysis.items():
            print(f"🔹 {entry_id}")
            print(f"   Tipo: {analysis['type']}")
            print(f"   Label: {analysis['label']}")
            print(f"   Context: {analysis['context_preview'][:100]}...")
            print()

        # 4. Sugere mapeamento
        mapping = self.suggest_field_mapping(field_analysis)

        print("🎯 MAPEAMENTO SUGERIDO:")
        print("-" * 40)
        for field_name, entry_id in mapping.items():
            print(f"{field_name:12} -> {entry_id}")

        # 5. Gera nova config
        new_config = self.generate_new_env_config(mapping)

        print("\n📝 NOVA CONFIGURAÇÃO PARA .env:")
        print("-" * 50)
        print(new_config)

        # 6. Salva análise completa
        self.save_analysis_report(entry_ids, field_analysis, mapping, new_config)

        return mapping

    def save_analysis_report(self, entry_ids: list, field_analysis: dict, mapping: dict, new_config: str):
        """Salva relatório completo da análise"""
        report_path = project_root / "scripts" / "form_analysis_report.txt"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write("RELATÓRIO DE ANÁLISE DO GOOGLE FORMS\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"URL do Formulário: {self.view_url}\n")
            f.write(f"Data da Análise: {__import__('datetime').datetime.now()}\n\n")

            f.write("TODOS OS ENTRY IDs ENCONTRADOS:\n")
            f.write("-" * 40 + "\n")
            for entry_id in entry_ids:
                f.write(f"- {entry_id}\n")
            f.write("\n")

            f.write("ANÁLISE DETALHADA DOS CAMPOS:\n")
            f.write("-" * 40 + "\n")
            for entry_id, analysis in field_analysis.items():
                f.write(f"Entry ID: {entry_id}\n")
                f.write(f"Tipo: {analysis['type']}\n")
                f.write(f"Label: {analysis['label']}\n")
                f.write(f"Context: {analysis['context_preview']}\n")
                f.write("-" * 20 + "\n")

            f.write("\nMAPEAMENTO SUGERIDO:\n")
            f.write("-" * 40 + "\n")
            for field_name, entry_id in mapping.items():
                f.write(f"{field_name} -> {entry_id}\n")

            f.write(f"\nNOVA CONFIGURAÇÃO .env:\n")
            f.write("-" * 40 + "\n")
            f.write(new_config)

        print(f"\n💾 Relatório salvo em: {report_path}")

def main():
    """Função principal"""
    try:
        extractor = GoogleFormsIDExtractor()
        mapping = extractor.run_analysis()

        if mapping:
            print("\n" + "=" * 80)
            print("✅ ANÁLISE CONCLUÍDA COM SUCESSO!")
            print("=" * 80)
            print("PRÓXIMOS PASSOS:")
            print("1. Atualize o arquivo .env com os novos IDs")
            print("2. Execute novamente o test_feedback.py")
            print("3. Verifique o relatório detalhado em scripts/form_analysis_report.txt")

    except Exception as e:
        print(f"❌ Erro na análise: {e}")

if __name__ == "__main__":
    main()