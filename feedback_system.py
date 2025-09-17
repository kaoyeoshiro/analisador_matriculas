"""
Sistema de Feedback Inteligente - Controle por Estados

Coleta dados de uso de forma não intrusiva, diferenciando entre:
- Problemas reais (reportados pelo usuário)
- Sucessos implícitos (uso normal sem reclamações)
"""

import os
import json
import time
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

        # Configuração do Google Forms via ambiente
        self.google_form_url = os.getenv('GOOGLE_FORM_URL', '')
        self.form_fields = {
            'tipo': os.getenv('GOOGLE_FORM_FIELD_TIPO', 'entry.1234567890'),
            'descricao': os.getenv('GOOGLE_FORM_FIELD_DESCRICAO', 'entry.0987654321'),
            'modelo': os.getenv('GOOGLE_FORM_FIELD_MODELO', 'entry.5566778899'),
            'timestamp': os.getenv('GOOGLE_FORM_FIELD_TIMESTAMP', 'entry.9988776655'),
            'versao': os.getenv('GOOGLE_FORM_FIELD_VERSAO', 'entry.1357924680'),
        }

        # Arquivo de feedback local (backup/debug)
        self.feedback_file = os.path.join(os.path.dirname(__file__), 'dist', 'feedback_pendente.json')

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
            self._enviar_feedback_automatico(
                "SUCESSO_AUTO",
                f"Relatório do processo {self._processo_atual} gerado sem problemas reportados - sistema fechado"
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

            # Salva localmente primeiro (backup)
            self._salvar_feedback_local(feedback_data)

            # Envia para Google Forms se configurado
            if self.google_form_url and self.google_form_url.strip():
                return self._enviar_para_google_forms(feedback_data)
            else:
                print("[Feedback] Google Forms não configurado, salvando apenas localmente")
                return True

        except Exception as e:
            print(f"[Feedback] Erro ao enviar feedback: {e}")
            return False

    def _salvar_feedback_local(self, feedback_data: Dict[str, Any]):
        """
        Salva feedback localmente como backup

        Args:
            feedback_data: Dados do feedback
        """
        try:
            # Garante que o diretório existe
            os.makedirs(os.path.dirname(self.feedback_file), exist_ok=True)

            # Lê feedbacks existentes
            feedbacks = []
            if os.path.exists(self.feedback_file):
                try:
                    with open(self.feedback_file, 'r', encoding='utf-8') as f:
                        feedbacks = json.load(f)
                except:
                    feedbacks = []

            # Adiciona novo feedback
            feedbacks.append(feedback_data)

            # Mantém apenas os últimos 100 feedbacks
            feedbacks = feedbacks[-100:]

            # Salva de volta
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedbacks, f, indent=2, ensure_ascii=False)

            print(f"[Feedback] Salvo localmente: {self.feedback_file}")

        except Exception as e:
            print(f"[Feedback] Erro ao salvar localmente: {e}")

    def _enviar_para_google_forms(self, feedback_data: Dict[str, Any]) -> bool:
        """
        Envia feedback para Google Forms

        Args:
            feedback_data: Dados do feedback

        Returns:
            True se enviado com sucesso, False caso contrário
        """
        try:
            # Prepara dados para o formulário
            form_data = {
                self.form_fields['tipo']: feedback_data['tipo'],
                self.form_fields['descricao']: feedback_data['descricao'],
                self.form_fields['modelo']: feedback_data['modelo'],
                self.form_fields['timestamp']: feedback_data['timestamp'],
                self.form_fields['versao']: feedback_data['versao']
            }

            # Envia POST para Google Forms
            response = requests.post(
                self.google_form_url,
                data=form_data,
                timeout=10,
                headers={
                    'User-Agent': 'FeedbackSystem/1.0',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }
            )

            # Google Forms retorna 200 mesmo com sucesso (redirect)
            if response.status_code in [200, 302]:
                print(f"[Feedback] Enviado para Google Forms com sucesso")
                return True
            else:
                print(f"[Feedback] Erro no Google Forms: {response.status_code}")
                return False

        except requests.exceptions.Timeout:
            print("[Feedback] Timeout ao enviar para Google Forms")
            return False
        except requests.exceptions.RequestException as e:
            print(f"[Feedback] Erro de rede: {e}")
            return False
        except Exception as e:
            print(f"[Feedback] Erro inesperado: {e}")
            return False

    def get_estatisticas_locais(self) -> Dict[str, Any]:
        """
        Retorna estatísticas dos feedbacks salvos localmente

        Returns:
            Dicionário com estatísticas
        """
        try:
            if not os.path.exists(self.feedback_file):
                return {"total": 0, "erros": 0, "sucessos": 0}

            with open(self.feedback_file, 'r', encoding='utf-8') as f:
                feedbacks = json.load(f)

            total = len(feedbacks)
            erros = sum(1 for f in feedbacks if f.get('tipo') == 'ERRO')
            sucessos = sum(1 for f in feedbacks if f.get('tipo') == 'SUCESSO_AUTO')

            return {
                "total": total,
                "erros": erros,
                "sucessos": sucessos,
                "taxa_sucesso": (sucessos / total * 100) if total > 0 else 0
            }

        except Exception as e:
            print(f"[Feedback] Erro ao calcular estatísticas: {e}")
            return {"total": 0, "erros": 0, "sucessos": 0, "erro": str(e)}


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
