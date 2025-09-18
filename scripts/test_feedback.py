#!/usr/bin/env python3
"""
Script completo para testar e corrigir envio ao Google Forms - Matrículas Confrontantes
Identifica causas do erro 400 e fornece solução funcional
VERSÃO PARA SISTEMA DE MATRÍCULAS CONFRONTANTES
"""
import os
import sys
import requests
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv

# Adiciona o diretório raiz ao path para acessar .env
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Carrega variáveis de ambiente
load_dotenv(project_root / ".env")

class MatriculasFeedbackDebugger:
    def __init__(self):
        # Configurações do formulário do .env
        self.form_url = os.getenv("GOOGLE_FORM_URL", "")
        self.view_url = self.form_url.replace("/formResponse", "/viewform")

        # IDs dos campos do .env
        self.fields = {
            "TIPO": os.getenv("GOOGLE_FORM_FIELD_TIPO", ""),
            "DESCRICAO": os.getenv("GOOGLE_FORM_FIELD_DESCRICAO", ""),
            "MODELO": os.getenv("GOOGLE_FORM_FIELD_MODELO", ""),
            "TIMESTAMP": os.getenv("GOOGLE_FORM_FIELD_TIMESTAMP", ""),
            "VERSAO": os.getenv("GOOGLE_FORM_FIELD_VERSAO", "")
        }

        # Headers apropriados para Google Forms
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': 'https://docs.google.com',
            'Referer': self.view_url,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }

        # Verifica se as configurações foram carregadas
        if not self.form_url:
            raise ValueError("GOOGLE_FORM_URL não encontrada no .env")

        for field_name, field_value in self.fields.items():
            if not field_value:
                print(f"⚠️  AVISO: {field_name} não encontrado no .env")

    def debug_response(self, response: requests.Response) -> Dict:
        """Captura informações detalhadas da resposta"""
        debug_info = {
            'status_code': response.status_code,
            'headers': dict(response.headers),
            'url': response.url,
            'content_length': len(response.content),
            'content_preview': response.text[:500],
            'redirects': len(response.history),
            'final_url': response.url
        }

        # Detecta redirecionamentos
        if response.history:
            debug_info['redirect_chain'] = [r.url for r in response.history]

        # Verifica se foi para página de confirmação (sucesso é 200 + redirect)
        if response.status_code == 200:
            debug_info['success'] = True
        else:
            debug_info['success'] = False

        return debug_info

    def test_method_1_with_sentinel(self) -> Tuple[bool, Dict]:
        """Teste 1: POST com campo sentinel para múltipla escolha"""
        print("TESTE 1: POST com campo sentinel...")

        data = {
            f"{self.fields['TIPO']}_sentinel": "",  # Campo sentinel vazio
            self.fields["TIPO"]: "ERRO",             # Valor da múltipla escolha
            self.fields["DESCRICAO"]: "Teste com campo sentinel - Sistema Matrículas",
            self.fields["MODELO"]: "google/gemini-2.5-pro",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_2_without_tipo(self) -> Tuple[bool, Dict]:
        """Teste 2: POST sem o campo problemático de múltipla escolha"""
        print("TESTE 2: POST sem campo TIPO...")

        data = {
            self.fields["DESCRICAO"]: "Teste sem campo tipo - Sistema Matrículas",
            self.fields["MODELO"]: "google/gemini-2.5-flash",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_3_simple_tipo(self) -> Tuple[bool, Dict]:
        """Teste 3: POST apenas com campo TIPO simples"""
        print("TESTE 3: POST só com campo TIPO...")

        data = {
            self.fields["TIPO"]: "SUCESSO_AUTO"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_4_basic_values(self) -> Tuple[bool, Dict]:
        """Teste 4: POST com valores básicos e corretos"""
        print("TESTE 4: POST com valores básicos...")

        data = {
            self.fields["TIPO"]: "ERRO",
            self.fields["DESCRICAO"]: "Teste básico do sistema de matrículas confrontantes",
            self.fields["MODELO"]: "google/gemini-2.5-pro",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_5_minimal_headers(self) -> Tuple[bool, Dict]:
        """Teste 5: Headers mínimos"""
        print("TESTE 5: Headers mínimos...")

        minimal_headers = {
            'User-Agent': 'Mozilla/5.0',
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        data = {
            self.fields["TIPO"]: "ERRO",
            self.fields["DESCRICAO"]: "Teste com headers mínimos"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=minimal_headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_6_session_cookies(self) -> Tuple[bool, Dict]:
        """Teste 6: Com sessão e cookies do Google"""
        print("TESTE 6: Com sessão e cookies...")

        session = requests.Session()

        try:
            # Primeiro visita a página do formulário para obter cookies
            session.get(self.view_url, headers=self.headers, timeout=15)

            data = {
                self.fields["TIPO"]: "ERRO",
                self.fields["DESCRICAO"]: "Teste com sessão - Sistema de análise de usucapião",
                self.fields["MODELO"]: "google/gemini-2.5-flash",
                self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.fields["VERSAO"]: "1.0.0"
            }

            response = session.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_7_url_encoded_values(self) -> Tuple[bool, Dict]:
        """Teste 7: Com valores URL encoded"""
        print("TESTE 7: Com valores URL encoded...")

        data = {
            self.fields["TIPO"]: "SUCESSO_AUTO",
            self.fields["DESCRICAO"]: urllib.parse.quote("Teste com caracteres especiais: análise, usucapião, confrontação"),
            self.fields["MODELO"]: urllib.parse.quote("google/gemini-2.5-pro"),
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_8_different_user_agents(self) -> Tuple[bool, Dict]:
        """Teste 8: Com diferentes User-Agents"""
        print("TESTE 8: Com User-Agent diferente...")

        headers_alt = self.headers.copy()
        headers_alt['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

        data = {
            self.fields["TIPO"]: "ERRO",
            self.fields["DESCRICAO"]: "Teste User-Agent Linux - Sistema PGE-MS",
            self.fields["MODELO"]: "openai/gpt-4o-mini",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=headers_alt,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_9_with_additional_headers(self) -> Tuple[bool, Dict]:
        """Teste 9: Com headers adicionais"""
        print("TESTE 9: Com headers adicionais...")

        headers_extra = self.headers.copy()
        headers_extra.update({
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin'
        })

        data = {
            self.fields["TIPO"]: "SUCESSO_AUTO",
            self.fields["DESCRICAO"]: "Teste headers extras - Análise jurídica automática",
            self.fields["MODELO"]: "anthropic/claude-3-sonnet",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=headers_extra,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_10_with_form_tokens(self) -> Tuple[bool, Dict]:
        """Teste 10: Tentando capturar e usar tokens do formulário"""
        print("TESTE 10: Com tokens do formulário...")

        session = requests.Session()

        try:
            # Obtém a página do formulário
            form_response = session.get(self.view_url, headers=self.headers, timeout=15)

            # Tenta extrair tokens/campos hidden da página
            import re

            # Procura por campos hidden que podem ser necessários
            hidden_fields = {}
            for match in re.finditer(r'<input[^>]*type=["\']hidden["\'][^>]*name=["\']([^"\']+)["\'][^>]*value=["\']([^"\']*)["\'][^>]*>', form_response.text):
                field_name = match.group(1)
                field_value = match.group(2)
                if field_name not in ['fbzx', 'fvv', 'partialResponse', 'pageHistory', 'submissionTimestamp']:
                    hidden_fields[field_name] = field_value

            print(f"   Campos hidden encontrados: {list(hidden_fields.keys())}")

            data = {
                self.fields["TIPO"]: "ERRO",
                self.fields["DESCRICAO"]: "Teste com tokens do formulário - Sistema completo",
                self.fields["MODELO"]: "google/gemini-2.5-pro",
                self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                self.fields["VERSAO"]: "1.0.0"
            }

            # Adiciona campos hidden encontrados
            data.update(hidden_fields)

            response = session.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_11_real_scenario(self) -> Tuple[bool, Dict]:
        """Teste 11: Cenário real do sistema de matrículas"""
        print("TESTE 11: Cenário real do sistema...")

        data = {
            self.fields["TIPO"]: "ERRO",
            self.fields["DESCRICAO"]: "Erro na análise de matrícula 12345.6789.10 - Confrontantes não identificados corretamente. Sistema encontrou apenas 2 de 4 confrontantes esperados na análise do documento PDF.",
            self.fields["MODELO"]: "google/gemini-2.5-pro",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def test_method_12_success_scenario(self) -> Tuple[bool, Dict]:
        """Teste 12: Cenário de sucesso do sistema"""
        print("TESTE 12: Cenário de sucesso...")

        data = {
            self.fields["TIPO"]: "SUCESSO_AUTO",
            self.fields["DESCRICAO"]: "Análise bem-sucedida da matrícula 98765.4321.00 - Todos os 6 confrontantes identificados corretamente. Relatório gerado com análise jurídica completa para processo de usucapião.",
            self.fields["MODELO"]: "google/gemini-2.5-pro",
            self.fields["TIMESTAMP"]: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.fields["VERSAO"]: "1.0.0"
        }

        try:
            response = requests.post(
                self.form_url,
                data=data,
                headers=self.headers,
                timeout=30,
                allow_redirects=True
            )

            debug_info = self.debug_response(response)
            print(f"   Status: {response.status_code}")
            print(f"   Success: {debug_info['success']}")

            return debug_info['success'], debug_info

        except Exception as e:
            return False, {'error': str(e)}

    def run_progressive_tests(self) -> Dict:
        """Executa testes progressivos até encontrar 100% de sucesso"""
        print("=" * 80)
        print("TESTE COMPLETO - SISTEMA DE MATRÍCULAS CONFRONTANTES (PGE-MS)")
        print("=" * 80)
        print(f"URL do formulário: {self.form_url}")
        print(f"URL de visualização: {self.view_url}")
        print()
        print("IDs dos campos do .env:")
        for name, entry_id in self.fields.items():
            print(f"  {name}: {entry_id}")
        print()

        results = {}
        all_tests = [
            ('with_sentinel', self.test_method_1_with_sentinel),
            ('without_tipo', self.test_method_2_without_tipo),
            ('only_tipo', self.test_method_3_simple_tipo),
            ('basic_values', self.test_method_4_basic_values),
            ('minimal_headers', self.test_method_5_minimal_headers),
            ('session_cookies', self.test_method_6_session_cookies),
            ('url_encoded', self.test_method_7_url_encoded_values),
            ('different_ua', self.test_method_8_different_user_agents),
            ('extra_headers', self.test_method_9_with_additional_headers),
            ('form_tokens', self.test_method_10_with_form_tokens),
            ('real_scenario', self.test_method_11_real_scenario),
            ('success_scenario', self.test_method_12_success_scenario)
        ]

        # Executa todos os testes
        for test_name, test_method in all_tests:
            success, info = test_method()
            results[test_name] = {'success': success, 'info': info}
            print()

        # Análise dos resultados
        self.analyze_results(results)

        return results

    def analyze_results(self, results: Dict):
        """Analisa resultados e fornece recomendações"""
        print("=" * 80)
        print("ANÁLISE DOS RESULTADOS")
        print("=" * 80)

        successful_methods = []

        for method_name, result in results.items():
            if result['success']:
                successful_methods.append(method_name)
                print(f"✅ SUCCESS {method_name.upper()}: FUNCIONOU")
            else:
                print(f"❌ FAIL {method_name.upper()}: FALHOU")
                if 'error' in result['info']:
                    print(f"   Erro: {result['info']['error']}")
                else:
                    status = result['info'].get('status_code', 'N/A')
                    print(f"   Status: {status}")
                    if status == 400:
                        print(f"   Preview: {result['info'].get('content_preview', '')[:100]}")

        print()
        print("RECOMENDAÇÕES:")

        if successful_methods:
            print(f"✅ Método funcional encontrado: {successful_methods[0].upper()}")
            self.generate_working_code(successful_methods[0])
        else:
            print("❌ Nenhum método funcionou. Investigações adicionais:")
            print("   1. Verifique se o formulário aceita respostas")
            print("   2. Teste preenchimento manual no navegador")
            print("   3. Confirme IDs dos campos com JavaScript no console")
            print("   4. Verifique se há restrições de CORS ou reCAPTCHA")
            print("   5. Atualize os IDs no arquivo .env se necessário")

    def generate_working_code(self, method: str):
        """Gera código Python funcional baseado no método que funcionou"""
        print()
        print("=" * 80)
        print("CÓDIGO PYTHON FUNCIONAL PARA O SISTEMA DE MATRÍCULAS")
        print("=" * 80)

        if method == 'with_sentinel':
            code = f'''
def send_feedback_to_google_forms(tipo: str, descricao: str, modelo: str, versao: str = "1.0.0") -> bool:
    """
    Envia feedback para Google Forms - MÉTODO COM SENTINEL (FUNCIONAL)

    Args:
        tipo: "ERRO" ou "SUCESSO_AUTO"
        descricao: Descrição detalhada do problema/sucesso
        modelo: Modelo LLM utilizado (ex: google/gemini-2.5-pro)
        versao: Versão da aplicação

    Returns:
        bool: True se enviado com sucesso
    """
    import requests
    from datetime import datetime

    url = "{self.form_url}"

    headers = {{
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Origin': 'https://docs.google.com',
        'Referer': '{self.view_url}'
    }}

    data = {{
        "{self.fields['TIPO']}_sentinel": "",     # Campo sentinel obrigatório
        "{self.fields['TIPO']}": tipo,            # TIPO: ERRO ou SUCESSO_AUTO
        "{self.fields['DESCRICAO']}": descricao,  # DESCRIÇÃO
        "{self.fields['MODELO']}": modelo,        # MODELO LLM
        "{self.fields['TIMESTAMP']}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # TIMESTAMP
        "{self.fields['VERSAO']}": versao         # VERSÃO
    }}

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro ao enviar feedback: {{e}}")
        return False

# EXEMPLO DE USO NO SEU SISTEMA:
success = send_feedback_to_google_forms(
    tipo="ERRO",
    descricao="Erro na análise de matrícula 12345.6789.10 - Confrontantes não identificados",
    modelo="google/gemini-2.5-pro",
    versao="1.0.0"
)
'''

        elif method == 'basic_values':
            code = f'''
def send_feedback_to_google_forms(tipo: str, descricao: str, modelo: str, versao: str = "1.0.0") -> bool:
    """
    Envia feedback para Google Forms - MÉTODO BÁSICO (FUNCIONAL)
    """
    import requests
    from datetime import datetime

    url = "{self.form_url}"

    headers = {{
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }}

    data = {{
        "{self.fields['TIPO']}": tipo,
        "{self.fields['DESCRICAO']}": descricao,
        "{self.fields['MODELO']}": modelo,
        "{self.fields['TIMESTAMP']}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{self.fields['VERSAO']}": versao
    }}

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro: {{e}}")
        return False
'''

        elif method == 'without_tipo':
            code = f'''
def send_feedback_to_google_forms(descricao: str, modelo: str, versao: str = "1.0.0") -> bool:
    """
    Envia feedback SEM o campo TIPO (que estava causando problema)
    """
    import requests
    from datetime import datetime

    url = "{self.form_url}"

    headers = {{
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }}

    data = {{
        "{self.fields['DESCRICAO']}": descricao,
        "{self.fields['MODELO']}": modelo,
        "{self.fields['TIMESTAMP']}": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "{self.fields['VERSAO']}": versao
    }}

    try:
        response = requests.post(url, data=data, headers=headers, timeout=30)
        return response.status_code == 200
    except Exception as e:
        print(f"Erro: {{e}}")
        return False
'''

        print(code)
        print()
        print("COMO INTEGRAR NO SEU CÓDIGO:")
        print("1. Substitua a função send_feedback atual em src/feedback_system.py")
        print("2. Mantenha as configurações do .env inalteradas")
        print("3. Use a função acima nos pontos onde há envio de feedback")
        print("4. Teste com dados reais do sistema de matrículas")
        print()
        print("EXEMPLO DE INTEGRAÇÃO:")
        print("# Substitua em feedback_system.py:")
        print("# success = send_feedback_to_google_forms(...)")

def main():
    """Função principal para executar os testes"""
    try:
        debugger = MatriculasFeedbackDebugger()
        results = debugger.run_progressive_tests()
        return results
    except Exception as e:
        print(f"❌ Erro na inicialização: {e}")
        print("Verifique se o arquivo .env está configurado corretamente.")
        return None

if __name__ == "__main__":
    main()