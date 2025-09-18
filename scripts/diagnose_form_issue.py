#!/usr/bin/env python3
"""
Diagnóstico avançado do Google Forms
Identifica problemas específicos que causam erro 400
"""
import os
import sys
import requests
import re
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Carrega variáveis de ambiente
load_dotenv(project_root / ".env")

class GoogleFormsDiagnostic:
    def __init__(self):
        self.form_url = os.getenv("GOOGLE_FORM_URL", "")
        self.view_url = self.form_url.replace("/formResponse", "/viewform")

        # IDs corretos já confirmados
        self.fields = {
            "TIPO": "entry.579089408",
            "DESCRICAO": "entry.597505189",
            "MODELO": "entry.207190791",
            "TIMESTAMP": "entry.943393649",
            "VERSAO": "entry.1649732056"
        }

    def check_form_status(self):
        """Verifica se o formulário está aceitando respostas"""
        print("🔍 VERIFICANDO STATUS DO FORMULÁRIO...")

        try:
            response = requests.get(self.view_url, timeout=15)
            html = response.text

            # Verifica sinais de que o formulário não aceita respostas
            closed_indicators = [
                "não está aceitando respostas",
                "formulário foi fechado",
                "form is no longer accepting responses",
                "responses are no longer being accepted",
                "Este formulário não aceita mais respostas"
            ]

            for indicator in closed_indicators:
                if indicator.lower() in html.lower():
                    print(f"❌ PROBLEMA ENCONTRADO: {indicator}")
                    return False

            # Verifica se há reCAPTCHA
            if "recaptcha" in html.lower():
                print("⚠️  RECAPTCHA detectado - pode estar bloqueando envios automáticos")

            # Verifica se requer login
            if "accounts.google.com" in html or "sign in" in html.lower():
                print("⚠️  Formulário pode exigir login Google")

            print("✅ Formulário parece estar aceitando respostas")
            return True

        except Exception as e:
            print(f"❌ Erro ao verificar formulário: {e}")
            return False

    def extract_form_metadata(self):
        """Extrai metadados importantes do formulário"""
        print("\n🔍 EXTRAINDO METADADOS DO FORMULÁRIO...")

        try:
            response = requests.get(self.view_url, timeout=15)
            html = response.text

            metadata = {}

            # Busca por FBzx (Facebook token)
            fbzx_match = re.search(r'"fbzx":"([^"]*)"', html)
            if fbzx_match:
                metadata['fbzx'] = fbzx_match.group(1)
                print(f"   FBzx token: {metadata['fbzx']}")

            # Busca por outros tokens importantes
            fvv_match = re.search(r'"fvv":"([^"]*)"', html)
            if fvv_match:
                metadata['fvv'] = fvv_match.group(1)
                print(f"   FVV token: {metadata['fvv']}")

            # Busca por configurações do formulário
            form_config_match = re.search(r'AF_initDataCallback.*?"data":\[(.*?)\]', html, re.DOTALL)
            if form_config_match:
                print("   ✅ Configuração do formulário encontrada")

            return metadata

        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return {}

    def test_with_browser_simulation(self):
        """Testa com simulação completa de navegador"""
        print("\n🔍 TESTANDO COM SIMULAÇÃO COMPLETA DE NAVEGADOR...")

        session = requests.Session()

        # Headers mais completos
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }

        try:
            # 1. Primeiro visita a página para estabelecer sessão
            print("   1. Visitando página do formulário...")
            view_response = session.get(self.view_url, headers=headers)

            # 2. Extrai metadados necessários
            metadata = self.extract_form_metadata_from_response(view_response.text)

            # 3. Prepara headers para POST
            post_headers = headers.copy()
            post_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://docs.google.com',
                'Referer': self.view_url
            })

            # 4. Dados com metadados
            data = {
                self.fields["TIPO"]: "ERRO",
                self.fields["DESCRICAO"]: "Teste diagnóstico avançado",
                self.fields["MODELO"]: "google/gemini-2.5-pro",
                self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.fields["VERSAO"]: "1.0.0"
            }

            # Adiciona metadados se encontrados
            data.update(metadata)

            print("   2. Enviando formulário com metadados...")
            response = session.post(self.form_url, data=data, headers=post_headers, timeout=30)

            print(f"   Status: {response.status_code}")

            if response.status_code == 200:
                print("   ✅ SUCESSO!")
                return True, response
            else:
                print("   ❌ Ainda erro 400")
                return False, response

        except Exception as e:
            print(f"   ❌ Erro: {e}")
            return False, None

    def extract_form_metadata_from_response(self, html):
        """Extrai metadados específicos da resposta"""
        metadata = {}

        # Busca por campos hidden importantes
        hidden_patterns = [
            r'<input[^>]*name="([^"]*)"[^>]*type="hidden"[^>]*value="([^"]*)"',
            r'<input[^>]*type="hidden"[^>]*name="([^"]*)"[^>]*value="([^"]*)"'
        ]

        for pattern in hidden_patterns:
            matches = re.findall(pattern, html)
            for name, value in matches:
                if name not in ['fbzx', 'fvv', 'pageHistory', 'submissionTimestamp']:
                    continue
                metadata[name] = value

        return metadata

    def test_field_types_individually(self):
        """Testa cada tipo de campo individualmente para identificar problema"""
        print("\n🔍 TESTANDO TIPOS DE CAMPO INDIVIDUALMENTE...")

        # Teste 1: Campo de múltipla escolha (TIPO)
        print("   Testando campo TIPO (múltipla escolha)...")
        result1 = self.test_single_value(self.fields["TIPO"], "ERRO")

        # Teste 2: Campo de texto longo (DESCRIÇÃO)
        print("   Testando campo DESCRIÇÃO (texto)...")
        result2 = self.test_single_value(self.fields["DESCRICAO"], "Teste")

        # Teste 3: Campo de texto curto (MODELO)
        print("   Testando campo MODELO (texto curto)...")
        result3 = self.test_single_value(self.fields["MODELO"], "teste")

        # Teste 4: Campo de data/hora
        print("   Testando campo TIMESTAMP (data)...")
        result4 = self.test_single_value(self.fields["TIMESTAMP"], "2025-09-18")

        # Teste 5: Campo de versão
        print("   Testando campo VERSÃO (texto)...")
        result5 = self.test_single_value(self.fields["VERSAO"], "1.0.0")

        return [result1, result2, result3, result4, result5]

    def test_single_value(self, field_id, value):
        """Testa um único campo com um valor"""
        try:
            data = {field_id: value}
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            response = requests.post(self.form_url, data=data, headers=headers, timeout=15)
            success = response.status_code == 200

            print(f"      {field_id}: {response.status_code} ({'✅' if success else '❌'})")
            return {'field': field_id, 'value': value, 'status': response.status_code, 'success': success}

        except Exception as e:
            print(f"      {field_id}: Erro - {e}")
            return {'field': field_id, 'value': value, 'status': 0, 'success': False, 'error': str(e)}

    def check_manual_submission(self):
        """Instrui como fazer um teste manual"""
        print("\n🔍 TESTE MANUAL RECOMENDADO:")
        print("=" * 50)
        print("1. Abra o formulário no navegador:")
        print(f"   {self.view_url}")
        print()
        print("2. Preencha os campos com:")
        print("   - Tipo: ERRO")
        print("   - Descrição: Teste manual")
        print("   - Modelo: google/gemini-2.5-pro")
        print("   - Data: 2025-09-18")
        print("   - Versão: 1.0.0")
        print()
        print("3. Envie o formulário")
        print("4. Se funcionar manualmente, o problema é com headers/cookies")
        print("5. Se não funcionar, o formulário tem restrições")

    def suggest_alternatives(self):
        """Sugere alternativas se o Google Forms não funcionar"""
        print("\n💡 ALTERNATIVAS SE O FORMS NÃO FUNCIONAR:")
        print("=" * 50)
        print("1. Usar Google Sheets API diretamente")
        print("2. Salvar feedback em arquivo local JSON")
        print("3. Enviar por email usando SMTP")
        print("4. Usar webhook para outro serviço")
        print("5. Criar próprio endpoint para receber feedback")

    def run_complete_diagnostic(self):
        """Executa diagnóstico completo"""
        print("=" * 80)
        print("DIAGNÓSTICO AVANÇADO - GOOGLE FORMS ERROR 400")
        print("=" * 80)

        # 1. Verifica status do formulário
        form_active = self.check_form_status()

        # 2. Extrai metadados
        metadata = self.extract_form_metadata()

        # 3. Testa com simulação de navegador
        browser_success, browser_response = self.test_with_browser_simulation()

        # 4. Testa campos individualmente
        field_results = self.test_field_types_individually()

        # 5. Análise final
        print("\n" + "=" * 80)
        print("DIAGNÓSTICO FINAL")
        print("=" * 80)

        if browser_success:
            print("✅ SOLUÇÃO ENCONTRADA: Simulação de navegador funcionou!")
            print("   Use os metadados extraídos na requisição")
        elif not form_active:
            print("❌ PROBLEMA: Formulário não está aceitando respostas")
            print("   Verifique as configurações do Google Forms")
        else:
            print("❌ PROBLEMA PERSISTENTE: Erro 400 em todos os testes")
            print("   Possíveis causas:")
            print("   - reCAPTCHA ativo")
            print("   - Restrições de domínio")
            print("   - Formulário requer autenticação")
            print("   - IDs dos campos mudaram")

        # 6. Instruções para teste manual
        self.check_manual_submission()

        # 7. Alternativas
        self.suggest_alternatives()

        return browser_success

def main():
    """Função principal"""
    try:
        diagnostic = GoogleFormsDiagnostic()
        success = diagnostic.run_complete_diagnostic()

        if success:
            print(f"\n🎉 Problema resolvido! Integre a solução no feedback_system.py")
        else:
            print(f"\n⚠️ Problema persiste. Considere implementar alternativa.")

    except Exception as e:
        print(f"❌ Erro no diagnóstico: {e}")

if __name__ == "__main__":
    main()