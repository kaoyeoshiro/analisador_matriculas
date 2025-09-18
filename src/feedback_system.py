"""
Sistema de Feedback Inteligente - Controle por Estados

Coleta dados de uso de forma não intrusiva, diferenciando entre:
- Problemas reais (reportados pelo usuário)
- Sucessos implícitos (uso normal sem reclamações)
"""

import threading
import requests
from datetime import datetime
from typing import Optional, Dict, Any
import tkinter as tk
from tkinter import messagebox, simpledialog

class FeedbackSystem:
    def __init__(self, app_version: str = "1.0.0", modelo_llm: str = "google/gemini-2.5-pro"):
        """
        Inicializa o sistema de feedback

        Args:
            app_version: Versão da aplicação
            modelo_llm: Modelo LLM utilizado
        """
        self.app_version = app_version
        self.modelo_llm = modelo_llm

        # Estados de controle
        self._feedback_enviado = False
        self._processo_atual: Optional[str] = None
        self._relatorio_gerado_com_sucesso = False

        # Configuração do Google Forms - IDs CORRETOS HARDCODED
        self.google_form_url = "https://docs.google.com/forms/d/e/1FAIpQLSdxpVRV22Adm2bXkoH3jyjyuN32GQVKxX9ebpzkRHV9vN3J4g/formResponse"
        self.view_form_url = "https://docs.google.com/forms/d/e/1FAIpQLSdxpVRV22Adm2bXkoH3jyjyuN32GQVKxX9ebpzkRHV9vN3J4g/viewform"
        # IDs reais obtidos a partir do bloco FB_PUBLIC_LOAD_DATA_ do formulário
        self.form_fields = {
            'tipo': 'entry.1649732056',
            'descricao': 'entry.579089408',
            'modelo': 'entry.597505189',
            'timestamp': 'entry.207190791',
            'versao': 'entry.943393649',
        }

        # Referência para o botão de feedback (será definida externamente)
        self.btn_feedback: Optional[tk.Button] = None

        print(f"[Feedback] Sistema inicializado - Versão: {app_version}, Modelo: {modelo_llm}")

    def set_feedback_button(self, btn_feedback: tk.Button):
        """Define a referência do botão de feedback para controle de estado"""
        self.btn_feedback = btn_feedback
        # Inicialmente desabilitado
        self._disable_feedback_button()

    def _enable_feedback_button(self):
        """Habilita o botão de feedback"""
        if self.btn_feedback:
            self.btn_feedback.configure(state="normal")
            print("[Feedback] Botão habilitado")

    def _disable_feedback_button(self):
        """Desabilita o botão de feedback"""
        if self.btn_feedback:
            self.btn_feedback.configure(state="disabled")
            print("[Feedback] Botão desabilitado")

    def _reset_feedback_state(self):
        """Reset do estado de feedback para novo processo"""
        self._feedback_enviado = False
        self._relatorio_gerado_com_sucesso = False
        self._processo_atual = None
        self._disable_feedback_button()
        print("[Feedback] Estado resetado")

    def on_relatorio_sucesso(self, numero_processo: str):
        """
        Chamado quando um relatório é gerado com sucesso

        Args:
            numero_processo: Número/ID do processo trabalhado
        """
        print(f"[Feedback] Relatório gerado com sucesso - Processo: {numero_processo}")

        # Se havia processo anterior sem feedback negativo, envia feedback positivo
        if (self._processo_atual and
            self._processo_atual != numero_processo and
            self._relatorio_gerado_com_sucesso and
            not self._feedback_enviado):

            print("[Feedback] Enviando feedback positivo automático (novo processo)")
            self._enviar_feedback_automatico(
                "SUCESSO_AUTO",
                f"Relatório do processo {self._processo_atual} gerado sem problemas reportados - novo relatório iniciado"
            )

        # Atualiza estado para o novo processo
        self._processo_atual = numero_processo
        self._relatorio_gerado_com_sucesso = True
        self._feedback_enviado = False

        # Habilita botão de feedback negativo
        self._enable_feedback_button()

        print(f"[Feedback] Estado atualizado - Processo atual: {numero_processo}")

    def on_reportar_erro_manual(self, parent_window=None) -> bool:
        """
        Abre diálogo para o usuário reportar erro manualmente

        Args:
            parent_window: Janela pai para o diálogo

        Returns:
            True se feedback foi enviado, False caso contrário
        """
        if not self._relatorio_gerado_com_sucesso:
            messagebox.showwarning(
                "Aviso",
                "Gere um relatório primeiro antes de reportar problemas.",
                parent=parent_window
            )
            return False

        if self._feedback_enviado:
            messagebox.showinfo(
                "Informação",
                "Feedback já foi enviado para este processo.",
                parent=parent_window
            )
            return False

        # Diálogo para descrição do problema
        descricao = simpledialog.askstring(
            "Reportar Erro no Conteúdo",
            f"Descreva o problema encontrado no processo {self._processo_atual}:\n\n"
            "Seja específico para nos ajudar a melhorar o sistema.",
            parent=parent_window
        )

        if not descricao or not descricao.strip():
            return False

        # Envia feedback negativo
        sucesso = self._enviar_feedback(
            tipo="ERRO",
            descricao=descricao.strip(),
            processo=self._processo_atual
        )

        if sucesso:
            self._feedback_enviado = True
            self._disable_feedback_button()

            messagebox.showinfo(
                "Feedback Enviado",
                "Obrigado pelo feedback! Sua contribuição nos ajuda a melhorar o sistema.",
                parent=parent_window
            )
            print(f"[Feedback] Erro reportado manualmente - Processo: {self._processo_atual}")
            return True
        else:
            messagebox.showerror(
                "Erro no Envio",
                "Não foi possível enviar o feedback. Tente novamente mais tarde.",
                parent=parent_window
            )
            return False

    def on_fechamento_aplicacao(self):
        """
        Chamado quando a aplicação está sendo fechada
        Envia feedback positivo automático se aplicável
        """
        if (self._processo_atual and
            self._relatorio_gerado_com_sucesso and
            not self._feedback_enviado):

            print("[Feedback] Enviando feedback positivo automático (fechamento)")
            self._enviar_feedback(
                tipo="SUCESSO_AUTO",
                descricao=(
                    f"Relatório do processo {self._processo_atual} "
                    "gerado sem problemas reportados - sistema fechado"
                ),
                processo=self._processo_atual
            )

    def _enviar_feedback_automatico(self, tipo: str, descricao: str):
        """
        Envia feedback automático em thread separada

        Args:
            tipo: Tipo do feedback (SUCESSO_AUTO)
            descricao: Descrição automática do evento
        """
        def enviar_async():
            self._enviar_feedback(
                tipo=tipo,
                descricao=descricao,
                processo=self._processo_atual
            )

        # Executa em thread separada para não bloquear interface
        thread = threading.Thread(target=enviar_async, daemon=True)
        thread.start()

    def _enviar_feedback(self, tipo: str, descricao: str, processo: Optional[str]) -> bool:
        """
        Envia feedback para Google Forms

        Args:
            tipo: ERRO ou SUCESSO_AUTO
            descricao: Descrição do feedback
            processo: Número do processo (pode ser None)

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Dados do feedback
            feedback_data = {
                'tipo': tipo,
                'descricao': descricao,
                'processo': processo or "N/A",
                'modelo': self.modelo_llm,
                'timestamp': timestamp,
                'versao': self.app_version
            }

            print(f"[Feedback] Enviando: {feedback_data}")

            return self._enviar_para_google_forms(feedback_data)

        except Exception as e:
            print(f"[Feedback] Erro ao enviar feedback: {e}")
            return False

    def _enviar_para_google_forms(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Envia feedback para Google Forms - VERSÃO FUNCIONAL COM SENTINEL

        Args:
            feedback_data: Dados do feedback

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Headers completos como navegador real
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://docs.google.com',
                'Referer': self.view_form_url,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
                'Connection': 'keep-alive'
            }

            # Prepara dados com campo sentinel (método que funciona)
            form_data = {
                f"{self.form_fields['tipo']}_sentinel": "",  # Campo sentinel obrigatório
                self.form_fields['tipo']: feedback_data['tipo'],
                self.form_fields['descricao']: feedback_data['descricao'],
                self.form_fields['modelo']: feedback_data['modelo'],
                self.form_fields['timestamp']: feedback_data['timestamp'],
                self.form_fields['versao']: feedback_data['versao']
            }

            print(f"[Feedback] Enviando para Google Forms...")
            print(f"[Feedback] Dados: {form_data}")

            # Envia POST para Google Forms
            response = requests.post(
                self.google_form_url,
                data=form_data,
                headers=headers,
                timeout=30,
                allow_redirects=True
            )

            print(f"[Feedback] Status: {response.status_code}")
            print(f"[Feedback] URL final: {response.url}")

            # Google Forms retorna 200 com sucesso
            if response.status_code == 200:
                print(f"[Feedback] SUCESSO: Enviado para Google Forms!")
                return True
            else:
                print(f"[Feedback] ERRO: Google Forms retornou {response.status_code}")
                print(f"[Feedback] Preview: {response.text[:200]}")
                return False

        except requests.exceptions.Timeout:
            print("[Feedback] TIMEOUT: Google Forms nao respondeu")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[Feedback] ERRO DE REDE: {e}")
            return False
        except Exception as e:
            print(f"[Feedback] Erro inesperado: {e}")
            return False

    def enviar_feedback_teste(self, tipo: str, descricao: str, processo: str = "TESTE") -> bool:
        """
        Método público para testar envio de feedback

        Args:
            tipo: "ERRO" ou "SUCESSO_AUTO"
            descricao: Descrição do feedback
            processo: Número do processo (padrão: "TESTE")

        Returns:
            True se enviado com sucesso
        """
        return self._enviar_feedback(tipo, descricao, processo)


# Função de conveniência para criar instância global
_feedback_instance: Optional[FeedbackSystem] = None

def get_feedback_system() -> FeedbackSystem:
    """Retorna a instância global do sistema de feedback"""
    global _feedback_instance
    if _feedback_instance is None:
        _feedback_instance = FeedbackSystem()
    return _feedback_instance

def initialize_feedback_system(app_version: str, modelo_llm: str) -> FeedbackSystem:
    """
    Inicializa o sistema de feedback global

    Args:
        app_version: Versão da aplicação
        modelo_llm: Modelo LLM utilizado

    Returns:
        Instância do sistema de feedback
    """
    global _feedback_instance
    _feedback_instance = FeedbackSystem(app_version, modelo_llm)
    return _feedback_instance
