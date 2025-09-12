
import os
import sys
import io
import json
import queue
import threading
import tempfile
import subprocess
import base64
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple, Union

# --- OCR & PDF ---
import fitz  # PyMuPDF
from PIL import Image
try:
    from pdf2image import convert_from_path  # Para conversão de PDF em imagens
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False

# --- HTTP & env ---
import requests
from dotenv import load_dotenv

# --- Plotting & Visualization ---
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import Polygon
import numpy as np

# --- GUI ---
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# =========================u
# Configuração
# =========================
APP_TITLE = "Analisador de Usucapião com IA Visual – Matrículas e Confrontantes (PGE-MS)"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Carrega .env
load_dotenv()
DEFAULT_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# =========================
# Estruturas
# =========================
@dataclass
class TransmissaoInfo:
    """Informações sobre uma transmissão na cadeia dominial"""
    data: Optional[str] = None
    tipo_transmissao: Optional[str] = None
    proprietario_anterior: Optional[str] = None
    novo_proprietario: Optional[str] = None
    percentual: Optional[str] = None
    valor: Optional[str] = None
    registro: Optional[str] = None

@dataclass
class RestricaoInfo:
    """Informações sobre restrições e gravames"""
    tipo: str
    data_registro: Optional[str] = None
    credor: Optional[str] = None
    valor: Optional[str] = None
    situacao: str = "vigente"  # "vigente" ou "baixada"
    data_baixa: Optional[str] = None
    observacoes: Optional[str] = None

@dataclass
class DadosGeometricos:
    """Dados geométricos extraídos para geração de planta"""
    medidas: Dict[str, float] = None  # frente, fundos, lateral_direita, lateral_esquerda
    confrontantes: Dict[str, str] = None  # direção -> nome do confrontante
    area_total: Optional[float] = None
    angulos: Dict[str, float] = None  # direção -> ângulo em graus
    formato: str = "retangular"  # retangular, irregular, triangular, etc.
    observacoes: List[str] = None
    
    def __post_init__(self):
        if self.medidas is None:
            self.medidas = {}
        if self.confrontantes is None:
            self.confrontantes = {}
        if self.angulos is None:
            self.angulos = {}
        if self.observacoes is None:
            self.observacoes = []

@dataclass
class MatriculaInfo:
    numero: str
    proprietarios: List[str]
    descricao: str
    confrontantes: List[str]
    evidence: List[str]
    lote: Optional[str] = None  # número do lote
    quadra: Optional[str] = None  # número da quadra
    cadeia_dominial: List[TransmissaoInfo] = None  # histórico de transmissões
    restricoes: List[RestricaoInfo] = None  # restrições e gravames
    dados_geometricos: Optional[DadosGeometricos] = None  # dados para planta
    
    def __post_init__(self):
        if self.cadeia_dominial is None:
            self.cadeia_dominial = []
        if self.restricoes is None:
            self.restricoes = []
        if self.dados_geometricos is None:
            self.dados_geometricos = None

@dataclass
class LoteConfronta:
    """Informações sobre um lote confrontante"""
    identificador: str  # "lote 10", "matrícula 1234", etc.
    tipo: str  # "lote", "matrícula", "pessoa", "via_publica", "estado", "outros"
    matricula_anexada: Optional[str] = None  # número da matrícula se foi anexada
    direcao: Optional[str] = None  # norte, sul, leste, oeste, etc.
    
@dataclass
class EstadoMSDireitos:
    """Informações sobre direitos do Estado de MS"""
    tem_direitos: bool = False
    detalhes: List[Dict] = None
    criticidade: str = "baixa"  # "alta", "media", "baixa"
    observacao: str = ""
    
    def __post_init__(self):
        if self.detalhes is None:
            self.detalhes = []

@dataclass
class ResumoAnalise:
    """Resumo estruturado da análise para o relatório"""
    cadeia_dominial_completa: Dict[str, List[Dict]] = None  # matrícula -> lista cronológica
    restricoes_vigentes: List[Dict] = None  # restrições ainda em vigor
    restricoes_baixadas: List[Dict] = None  # restrições já canceladas
    estado_ms_direitos: EstadoMSDireitos = None  # direitos do Estado de MS
    
    def __post_init__(self):
        if self.cadeia_dominial_completa is None:
            self.cadeia_dominial_completa = {}
        if self.restricoes_vigentes is None:
            self.restricoes_vigentes = []
        if self.restricoes_baixadas is None:
            self.restricoes_baixadas = []
        if self.estado_ms_direitos is None:
            self.estado_ms_direitos = EstadoMSDireitos()

@dataclass
class AnalysisResult:
    arquivo: str
    matriculas_encontradas: List[MatriculaInfo]
    matricula_principal: Optional[str]  # número da matrícula de usucapião
    matriculas_confrontantes: List[str]  # números das matrículas confrontantes
    # NOVOS CAMPOS PARA MELHOR CONTROLE
    lotes_confrontantes: List[LoteConfronta]  # todos os confrontantes identificados
    matriculas_nao_confrontantes: List[str]  # matrículas anexadas que NÃO são confrontantes
    lotes_sem_matricula: List[str]  # lotes confrontantes sem matrícula anexada
    confrontacao_completa: Optional[bool]  # se todas confrontantes foram apresentadas
    proprietarios_identificados: Dict[str, List[str]]  # número -> lista proprietários
    resumo_analise: Optional[ResumoAnalise] = None  # resumo estruturado da análise
    confidence: Optional[float] = None
    reasoning: str = ""
    raw_json: Dict = None
    
    def __post_init__(self):
        if self.resumo_analise is None:
            self.resumo_analise = ResumoAnalise()
        if self.raw_json is None:
            self.raw_json = {}
    
    # Campos de compatibilidade (para não quebrar código existente)
    @property
    def is_confrontante(self) -> Optional[bool]:
        """Compatibilidade: retorna se encontrou Estado MS como confrontante"""
        estado_patterns = ['estado de mato grosso do sul', 'estado de ms', 'estado do ms', 
                          'fazenda do estado', 'governo do estado', 'fazenda pública estadual']
        for matricula in self.matriculas_encontradas:
            for confrontante in matricula.confrontantes:
                if any(pattern in confrontante.lower() for pattern in estado_patterns):
                    return True
        return False
    


def image_to_base64(image_path_or_pil: Union[str, Image.Image], max_size: int = 1024, jpeg_quality: int = 85) -> str:
    """
    Converte imagem para base64 otimizada para envio à API de visão.
    """
    try:
        if isinstance(image_path_or_pil, str):
            img = Image.open(image_path_or_pil)
        else:
            img = image_path_or_pil
        
        # Converte para RGB se necessário
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Redimensiona se muito grande (mantém proporção)
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        
        # Converte para base64
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=jpeg_quality, optimize=True)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return img_str
    except Exception as e:
        print(f"Erro ao converter imagem para base64: {e}")
        return ""

def get_pdf_page_count(pdf_path: str) -> int:
    """
    Retorna o número total de páginas de um PDF.
    """
    try:
        if PDF2IMAGE_AVAILABLE:
            try:
                from pdf2image.utils import get_page_count  # type: ignore
                return get_page_count(pdf_path)
            except Exception:
                pass
        
        # Fallback com PyMuPDF
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()
        return page_count
        
    except Exception as e:
        print(f"Erro ao contar páginas do PDF: {e}")
        return 0

def pdf_to_images(pdf_path: str, max_pages: Optional[int] = 10) -> List[Image.Image]:
    """
    Converte PDF para lista de imagens PIL para análise visual.
    Se max_pages for None, processa todas as páginas.
    """
    images = []
    try:
        # Primeiro tenta com pdf2image (mais rápido)
        if PDF2IMAGE_AVAILABLE:
            try:
                if max_pages is None:
                    # Sem limite - processa todas as páginas
                    pdf_images = convert_from_path(pdf_path, dpi=200)
                else:
                    pdf_images = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=max_pages)
                return pdf_images
            except Exception:
                pass
        
        # Fallback com PyMuPDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        pages_to_process = total_pages if max_pages is None else min(total_pages, max_pages)
        
        for page_num in range(pages_to_process):
            page = doc[page_num]
            # Converte página para imagem
            mat = fitz.Matrix(2.0, 2.0)  # escala 2x para melhor qualidade
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("ppm")
            img = Image.open(io.BytesIO(img_data))
            images.append(img)
        doc.close()
        
    except Exception as e:
        print(f"Erro ao converter PDF para imagens: {e}")
    
    return images


# =========================
# Cliente OpenRouter
# =========================
def call_openrouter_vision(model: str, system_prompt: str, user_prompt: str, images_base64: List[str], temperature: float = 0.0, max_tokens: int = 1500) -> Dict:
    """
    Chama a API OpenRouter com suporte a visão computacional (análise de imagens).
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pge-ms.lab/analise-matriculas",
        "X-Title": "Analise de Matriculas PGE-MS"
    }

    # Constrói mensagem com imagens
    content = [{"type": "text", "text": user_prompt}]
    
    # Adiciona cada imagem
    for i, img_b64 in enumerate(images_base64):
        if img_b64:  # verifica se base64 não está vazio
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{img_b64}",
                    "detail": "high"  # alta qualidade para documentos
                }
            })

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ],
        "temperature": 0.1,  # Reduzido para respostas mais focadas
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}
    }

    try:
        # Debug detalhado do payload
        try:
            message_content = payload['messages'][1]['content']
            image_count = sum(1 for item in message_content if item.get('type') == 'image_url')
            text_count = sum(1 for item in message_content if item.get('type') == 'text')
            
            print(f"🌐 Fazendo requisição para: {OPENROUTER_URL}")
            print(f"📦 Payload contém {len(message_content)} elementos total")
            print(f"🖼️ Imagens no payload: {image_count}")
            print(f"📝 Textos no payload: {text_count}")
            print(f"🔑 Modelo: {payload.get('model', 'N/A')}")
            
            # Calcula tamanho total do payload em MB
            import sys
            payload_size_mb = sys.getsizeof(str(payload)) / (1024 * 1024)
            print(f"📐 Tamanho do payload: {payload_size_mb:.2f}MB")
            
        except Exception as e:
            print(f"⚠️ Erro ao analisar payload: {e}")
            print(f"📊 Estrutura do payload: {list(payload.keys()) if isinstance(payload, dict) else type(payload)}")
        
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        
        print(f"📡 Status da resposta: {resp.status_code}")
        print(f"📊 Headers da resposta: {dict(list(resp.headers.items())[:5])}...")  # primeiros 5 headers
        
        if resp.status_code != 200:
            print(f"❌ Erro HTTP {resp.status_code}: {resp.text[:500]}")
            # Tenta extrair mais detalhes do erro
            try:
                error_data = json.loads(resp.text)
                if "error" in error_data:
                    error_msg = error_data["error"]
                    if isinstance(error_msg, dict):
                        error_details = error_msg.get("message", str(error_msg))
                    else:
                        error_details = str(error_msg)
                    raise RuntimeError(f"API Error ({resp.status_code}): {error_details}")
            except json.JSONDecodeError:
                pass
            raise RuntimeError(f"API retornou status {resp.status_code}: {resp.text[:200]}")
            
        response_text = resp.text.strip()
        print(f"📝 Tamanho da resposta: {len(response_text)} chars")
        
        if not response_text:
            raise RuntimeError("Resposta vazia da API")
        
        # Debug da resposta bruta
        if len(response_text) < 200:
            print(f"📄 Resposta completa: {response_text}")
        else:
            print(f"📄 Início da resposta: {response_text[:300]}...")
            print(f"📄 Final da resposta: ...{response_text[-100:]}")
            
        # Parse mais robusto do JSON
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            print(f"❌ Erro JSON: {e}")
            print(f"📄 Conteúdo problemático: {response_text[:1000]}")
            raise RuntimeError(f"Resposta da API não é JSON válido: {e}")
        
        # Debug da estrutura da resposta
        print(f"🔍 Estrutura da resposta: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        
        if not isinstance(data, dict):
            raise RuntimeError(f"Resposta da API não é um objeto JSON: {type(data)}")
        
        if "choices" not in data:
            print(f"❌ Campo 'choices' não encontrado. Campos disponíveis: {list(data.keys())}")
            # Verifica se há uma mensagem de erro
            if "error" in data:
                error_msg = data["error"]
                raise RuntimeError(f"API retornou erro: {error_msg}")
            raise RuntimeError(f"Campo 'choices' ausente na resposta. Estrutura: {data}")
        
        if not data["choices"]:
            print(f"❌ Lista 'choices' está vazia")
            raise RuntimeError("Lista 'choices' vazia na resposta da API")
        
        if not isinstance(data["choices"], list):
            print(f"❌ 'choices' não é uma lista: {type(data['choices'])}")
            raise RuntimeError(f"Campo 'choices' deve ser uma lista, mas é: {type(data['choices'])}")
        
        print(f"✅ Resposta válida com {len(data['choices'])} choice(s)")
        return data
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro na requisição para OpenRouter: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Erro ao decodificar JSON da resposta: {e}. Resposta: {response_text[:500]}")
    except Exception as e:
        raise RuntimeError(f"Erro inesperado na chamada da API: {e}")


def clean_json_response(content: str) -> str:
    """Extrai JSON de uma resposta que pode conter markdown e texto adicional"""
    content = content.strip()
    
    # Procura por blocos JSON em markdown
    import re
    
    # Padrão 1: ```json ... ```
    json_pattern = r'```json\s*\n(.*?)\n```'
    match = re.search(json_pattern, content, re.DOTALL)
    if match:
        json_content = match.group(1).strip()
        print(f"✅ JSON extraído do markdown (```json): {len(json_content)} chars")
        return json_content
    
    # Padrão 2: ``` ... ``` (sem especificar json)
    json_pattern = r'```\s*\n(.*?)\n```'
    match = re.search(json_pattern, content, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        # Verifica se parece com JSON (começa com { ou [)
        if candidate.startswith('{') or candidate.startswith('['):
            print(f"✅ JSON extraído do markdown (```): {len(candidate)} chars")
            return candidate
    
    # Padrão 3: Procura por { ... } que parece ser JSON
    json_pattern = r'\{.*\}'
    match = re.search(json_pattern, content, re.DOTALL)
    if match:
        candidate = match.group(0).strip()
        print(f"✅ JSON extraído por regex {{...}}: {len(candidate)} chars")
        return candidate
    
    # Se não encontrou nada, retorna o conteúdo original
    print(f"⚠️ Nenhum JSON encontrado, retornando conteúdo original: {len(content)} chars")
    return content

# =========================
# Prompting
# =========================
SYSTEM_PROMPT = (
    "Você é um perito ESPECIALISTA em análise de processos de usucapião e matrículas imobiliárias brasileiras. "
    "Sua responsabilidade é CRÍTICA: a identificação COMPLETA de confrontantes pode determinar o sucesso ou fracasso de um usucapião. "
    "\n\nMISSÃO VITAL:\n"
    "🎯 IDENTIFIQUE TODOS os confrontantes da matrícula principal SEM EXCEÇÃO\n"
    "🎯 TODO LOTE DEVE TER NO MÍNIMO 4 CONFRONTANTES (uma para cada direção)\n"
    "🎯 EXTRAIA LITERALMENTE cada nome, matrícula, rua mencionada como confrontante\n"
    "🎯 ANALISE palavra por palavra a descrição do imóvel principal\n"
    "🎯 PROCURE confrontantes em TODAS as direções (norte, sul, leste, oeste, frente, fundos)\n"
    "🎯 SE MENOS DE 4 CONFRONTANTES: releia o texto procurando informações perdidas\n"
    "\n\nCONSEQUÊNCIAS:\n"
    "❌ UM confrontante perdido = usucapião pode ser NEGADO\n"
    "✅ TODOS confrontantes identificados = processo bem fundamentado\n"
    "\n\nMISSÃO ADICIONAL CRÍTICA - CADEIA DOMINIAL:\n"
    "📋 ANALISE TODA A CADEIA DOMINIAL DO IMÓVEL desde a titulação original até o momento atual\n"
    "📋 IDENTIFIQUE TODOS os proprietários históricos em ordem cronológica\n"
    "📋 CONSIDERE co-propriedade em percentuais como cadeias dominiais autônomas\n"
    "📋 PROCURE por registros de transmissões: compra/venda, doação, herança, adjudicação\n"
    "📋 VERIFIQUE restrições: penhora, indisponibilidade, hipoteca, gravames não baixados\n"
    "\n\nDeterminar qual é a matrícula principal (objeto do usucapião) e extrair proprietários ATUAIS de cada matrícula. "
    "Verificar se o Estado de Mato Grosso do Sul aparece como confrontante. "
    "Considere linguagem arcaica, abreviações, variações tipográficas e OCR imperfeito. "
    "\n\n🔥 ZERO TOLERÂNCIA para confrontantes perdidos. Cada um é VITAL."
)

AGGREGATE_PROMPT = (
    "Você receberá texto extraído de documentos de um processo de usucapião contendo múltiplas matrículas. "
    "TAREFA COMPLETA:\n\n"
    "1) IDENTIFIQUE todas as matrículas presentes no texto (números, mesmo com variações de formatação)\n"
    "2) Para cada matrícula encontrada:\n"
    "   - Extraia o número da matrícula (normalize: remova pontos/espaços)\n"
    "   - IDENTIFIQUE o número do LOTE e da QUADRA (FUNDAMENTAL para confrontações)\n"
    "     * Procure por: 'lote nº', 'lote número', 'lote sob o nº', 'quadra nº', 'quadra número'\n"
    "     * Exemplos: 'lote 10', 'lote sob o nº 15', 'quadra 21', 'quadra número 05'\n"
    "   - Identifique APENAS os proprietários ATUAIS (ignore vendedores/doadores antigos)\n"
    "     * Procure por 'PROPRIETÁRIO(S)', 'ATUAL PROPRIETÁRIO', ou última transação\n"
    "     * Se há vendas/doações, considere apenas o último comprador/donatário\n"
    "     * Ignore nomes precedidos por 'de:', 'vendido por:', 'doado por:', 'assinado por:'\n"
    "   - Extraia a descrição do imóvel\n"
    "   - Liste TODOS os confrontantes mencionados (EXTREMAMENTE IMPORTANTE)\n"
    "   - Colete evidências (trechos literais)\n\n"
    "3) DETERMINE qual é a matrícula principal (objeto do usucapião) - geralmente a primeira ou mais detalhada\n"
    "4) 🚨 ANÁLISE EXTREMAMENTE RIGOROSA DOS CONFRONTANTES (CRÍTICO PARA USUCAPIÃO):\n"
    "   \n"
    "   📍 LOCALIZAÇÃO DE INFORMAÇÕES DE CONFRONTAÇÃO:\n"
    "   - Procure na seção 'DESCRIÇÃO DO IMÓVEL' da matrícula principal\n"
    "   - Procure em seções denominadas 'CONFRONTAÇÕES', 'LIMITES', 'DIVISAS'\n"
    "   - Procure em qualquer texto que descreva o perímetro/limites do imóvel\n"
    "   - Examine tabelas, averbações, registros complementares\n"
    "   \n"
    "   🔍 PALAVRAS-CHAVE OBRIGATÓRIAS A BUSCAR:\n"
    "   - 'confronta', 'confrontante', 'confrontação', 'confrontações'\n"
    "   - 'limita', 'limitado', 'limites', 'limita-se'\n"
    "   - 'divisa', 'faz divisa', 'divisa com'\n"
    "   - 'ao norte', 'ao sul', 'ao leste', 'ao oeste'\n"
    "   - 'pela frente', 'pelos fundos', 'laterais'\n"
    "   - 'adjacente', 'vizinho', 'contíguo'\n"
    "   \n"
    "   📊 TIPOS DE CONFRONTANTES A IDENTIFICAR:\n"
    "   - LOTES: números de lotes confrontantes (ex: 'lote 11', 'lote nº 09', 'lote sob o nº 15')\n"
    "   - MATRÍCULAS: números de outras matrículas (ex: 'matrícula 1.234', 'mat. 5678')\n"
    "   - PESSOAS: nomes completos de proprietários vizinhos\n"
    "   - EMPRESAS: razões sociais, CNPJs\n"
    "   - VIAS PÚBLICAS: ruas, avenidas, praças, rodovias\n"
    "   - ENTES PÚBLICOS: Estado, Município, União, autarquias\n"
    "   - ACIDENTES GEOGRÁFICOS: rios, córregos, morros\n"
    "   - OUTROS IMÓVEIS: glebas, chácaras identificados\n"
    "   \n"
    "   ⚠️ INSTRUÇÕES CRÍTICAS:\n"
    "   - LEIA PALAVRA POR PALAVRA da descrição do imóvel principal\n"
    "   - TODO LOTE DEVE TER NO MÍNIMO 4 CONFRONTANTES (uma para cada direção)\n"
    "   - Para CADA direção (norte, sul, leste, oeste, frente, fundos), identifique O QUE confronta\n"
    "   - Se encontrou menos de 4 confrontantes, RELEIA o texto procurando mais\n"
    "   - Se mencionar 'terreno de João Silva', João Silva é confrontante\n"
    "   - Se mencionar 'matrícula 1.234', a matrícula 1.234 é confrontante\n"
    "   - Se mencionar 'Rua das Flores', a Rua das Flores é confrontante\n"
    "   - Se mencionar 'lote 11', o lote 11 é confrontante\n"
    "   - NÃO suponha, EXTRAIA exatamente como está escrito\n"
    "   - ALERTAR SE MENOS DE 4 CONFRONTANTES: pode estar faltando informação\n"
    "   \n"
    "5) VERIFICAÇÃO DE QUANTIDADE MÍNIMA DE CONFRONTANTES:\n"
    "   - CONTE quantos confrontantes identificou para a matrícula principal\n"
    "   - Se MENOS de 4 confrontantes: RELEIA todo o texto novamente\n"
    "   - Procure por termos como 'limita-se por', 'cerca-se de', 'circundado por'\n"
    "   - Verifique se há descrições em formatos diferentes (tabelas, parágrafos separados)\n"
    "   - UM LOTE SEMPRE TEM PELO MENOS 4 LADOS, portanto 4 CONFRONTANTES\n"
    "   \n"
    "6) VERIFICAÇÃO CRUZADA DE MATRÍCULAS:\n"
    "   - Se identificou que matrícula A confronta com matrícula B, certifique-se que ambas estão no documento\n"
    "   - Liste todas as matrículas mencionadas como confrontantes na seção 'matriculas_confrontantes'\n"
    "   \n"
    "7) VERIFICAÇÃO ESPECÍFICA DO ESTADO DE MS:\n"
    "   - Procure por: 'Estado', 'Estado de Mato Grosso do Sul', 'MS', 'Governo', 'Fazenda Pública'\n"
    "   - Se encontrar qualquer referência ao Estado como confrontante, marque como true\n\n"
    "8) 📋 ANÁLISE COMPLETA DA CADEIA DOMINIAL (CRÍTICO PARA USUCAPIÃO):\n"
    "   Para definir a propriedade do imóvel, analise toda a cadeia dominial, isto é, o histórico completo de proprietários desde a titulação original até o momento atual.\n"
    "   \n"
    "   🔍 PROCURE POR SEÇÕES:\n"
    "   - 'REGISTRO', 'REGISTRO ANTERIOR', 'ORIGEM', 'PROCEDÊNCIA'\n"
    "   - 'TRANSMISSÕES', 'AVERBAÇÕES', 'HISTÓRICO DE PROPRIETÁRIOS'\n"
    "   - Numeração sequencial de registros (R.1, R.2, R.3, etc.)\n"
    "   - Datas de transações e tipos de transmissão\n"
    "   \n"
    "   📊 EXTRAIA PARA CADA TRANSMISSÃO:\n"
    "   - Data da transmissão\n"
    "   - Tipo de transmissão (compra/venda, doação, herança, adjudicação, etc.)\n"
    "   - Proprietário anterior (vendedor/doador)\n"
    "   - Novo proprietário (comprador/donatário)\n"
    "   - Percentual de propriedade (se houver co-propriedade)\n"
    "   - Valor da transação (se informado)\n"
    "   \n"
    "   🎯 CO-PROPRIEDADE:\n"
    "   - Considere co-propriedade em percentuais como cadeias dominiais autônomas\n"
    "   - Se João possui 50% e Maria possui 50%, trate como duas cadeias separadas\n"
    "   - Rastreie cada percentual independentemente\n"
    "   \n"
    "9) 🚨 IDENTIFICAÇÃO DE RESTRIÇÕES E GRAVAMES:\n"
    "   Verificar e indicar restrições sobre o imóvel que não tenham sido baixadas.\n"
    "   \n"
    "   🔍 PROCURE POR:\n"
    "   - 'PENHORA', 'ARRESTO', 'SEQUESTRO'\n"
    "   - 'INDISPONIBILIDADE', 'BLOQUEIO JUDICIAL'\n"
    "   - 'HIPOTECA', 'PENHOR', 'ANTICRESE'\n"
    "   - 'USUFRUTO', 'ENFITEUSE', 'SERVIDÃO'\n"
    "   - 'FIDEICOMISSO', 'ALIENAÇÃO FIDUCIÁRIA'\n"
    "   - 'ÔNUS', 'GRAVAME', 'RESTRIÇÃO'\n"
    "   \n"
    "   ⚖️ VERIFIQUE STATUS:\n"
    "   - Para cada restrição encontrada, verifique se foi BAIXADA ou CANCELADA\n"
    "   - Procure por: 'BAIXA', 'CANCELAMENTO', 'EXTINÇÃO', 'QUITAÇÃO'\n"
    "   - Se não há registro de baixa, considere a restrição como VIGENTE\n"
    "   - Anote datas de registro e eventual baixa\n"
    "   \n"
    "   🚨 ATENÇÃO ESPECIAL - ESTADO DE MATO GROSSO DO SUL:\n"
    "   - IDENTIFIQUE com prioridade máxima se o Estado de MS tem qualquer direito registrado\n"
    "   - Procure por: 'Estado de Mato Grosso do Sul', 'Estado de MS', 'Fazenda Pública', 'Governo do Estado'\n"
    "   - Verifique se aparece como: CREDOR em hipotecas/penhoras, PROPRIETÁRIO, USUFRUTUÁRIO\n"
    "   - Marque como CRÍTICO qualquer direito vigente do Estado de MS\n"
    "   \n"
    "10) 📐 EXTRAÇÃO DE DADOS GEOMÉTRICOS (PARA GERAÇÃO DE PLANTA):\n"
    "   Para possibilitar a geração automática de planta do imóvel, extraia com precisão:\n"
    "   \n"
    "   📏 MEDIDAS LINEARES:\n"
    "   - FRENTE: medida da frente do lote (em metros)\n"
    "   - FUNDOS: medida dos fundos do lote (em metros)\n"
    "   - LATERAL DIREITA: medida do lado direito (em metros)\n"
    "   - LATERAL ESQUERDA: medida do lado esquerdo (em metros)\n"
    "   - Procure por: 'medindo', 'metros', 'm', 'frente', 'fundos', 'lado direito', 'lado esquerdo'\n"
    "   \n"
    "   🧭 ORIENTAÇÃO E CONFRONTAÇÕES:\n"
    "   - Para cada lado: identifique COM O QUE confronta\n"
    "   - Relacione direção com confrontante: 'frente' -> 'Rua X', 'fundos' -> 'lote Y'\n"
    "   - Procure por: 'ao norte com', 'ao sul com', 'frente para', 'fundos com'\n"
    "   \n"
    "   📐 ÂNGULOS E FORMATO:\n"
    "   - Identifique se o terreno é retangular (ângulos de 90°)\n"
    "   - Se irregular: procure por ângulos específicos mencionados\n"
    "   - Formato: 'retangular', 'irregular', 'triangular', 'trapezoidal'\n"
    "   \n"
    "   📊 ÁREA TOTAL:\n"
    "   - Procure por: 'área de', 'com área total de', 'm²', 'metros quadrados'\n"
    "   - Calcule se não informado: frente × lateral (para retângulos)\n"
    "\n🔥 ALERTA MÁXIMO: A omissão de qualquer confrontante pode invalidar o usucapião. Seja METICULOSO.\n\n"
    "💡 EXEMPLO PRÁTICO DE IDENTIFICAÇÃO:\n"
    "Se o texto diz: 'lote nº 10 da quadra 21, confronta ao norte com o lote 11, ao sul com a Rua das Flores, ao leste com terreno de Maria Santos, matrícula 1.234, e ao oeste com o Estado de Mato Grosso do Sul'\n"
    "EXTRAIA LOTE/QUADRA: lote='10', quadra='21'\n"
    "EXTRAIA CONFRONTANTES: ['lote 11', 'Rua das Flores', 'Maria Santos', 'matrícula 1.234', 'Estado de Mato Grosso do Sul']\n"
    "CONTAGEM: 5 confrontantes identificados (✅ mais que o mínimo de 4)\n"
    "NUNCA omita nenhum lote, nome ou referência mencionada.\n\n"
    "⚠️ REGRA FUNDAMENTAL: Se encontrar menos de 4 confrontantes, PROCURE NOVAMENTE no texto!\n\n"
    "🧠 ANÁLISE EFICIENTE EM 3 ETAPAS:\n"
    "\n"
    "ETAPA 1 - MAPEAMENTO RÁPIDO:\n"
    "- Identifique a matrícula PRINCIPAL e suas confrontantes\n"
    "- Conte: tem pelo menos 4 confrontantes? Se não, procure mais\n"
    "\n"
    "ETAPA 2 - VERIFICAÇÃO CRUZADA:\n"
    "- Confirme proprietários ATUAIS (ignore histórico de vendas)\n"
    "- Verifique presença do Estado de MS como confrontante\n"
    "\n"
    "ETAPA 3 - VALIDAÇÃO:\n"
    "- ✅ Todas as matrículas identificadas?\n"
    "- ✅ Mínimo 4 confrontantes da principal?\n"
    "- ✅ Proprietários atuais confirmados?\n"
    "\n"
    "Responda em JSON com este esquema EXPANDIDO:\n"
    "{\n"
    '  "matriculas_encontradas": [\n'
    '    {\n'
    '      "numero": "12345",\n'
    '      "lote": "10",\n'
    '      "quadra": "21",\n'
    '      "proprietarios": ["Nome 1", "Nome 2"],\n'
    '      "descricao": "descrição do imóvel",\n'
    '      "confrontantes": ["lote 11", "confrontante 2"],\n'
    '      "evidence": ["trecho literal 1", "trecho literal 2"],\n'
    '      "cadeia_dominial": [\n'
    '        {\n'
    '          "data": "01/01/2020",\n'
    '          "tipo_transmissao": "compra e venda",\n'
    '          "proprietario_anterior": "João Silva",\n'
    '          "novo_proprietario": "Maria Santos",\n'
    '          "percentual": "100%",\n'
    '          "valor": "R$ 100.000,00",\n'
    '          "registro": "R.1"\n'
    '        }\n'
    '      ],\n'
    '      "restricoes": [\n'
    '        {\n'
    '          "tipo": "hipoteca",\n'
    '          "data_registro": "15/06/2019",\n'
    '          "credor": "Banco XYZ",\n'
    '          "valor": "R$ 80.000,00",\n'
    '          "situacao": "vigente",\n'
    '          "data_baixa": null,\n'
    '          "observacoes": "hipoteca para financiamento imobiliário"\n'
    '        }\n'
    '      ],\n'
    '      "dados_geometricos": {\n'
    '        "medidas": {\n'
    '          "frente": 14.0,\n'
    '          "fundos": 14.0,\n'
    '          "lateral_direita": 30.69,\n'
    '          "lateral_esquerda": 30.69\n'
    '        },\n'
    '        "confrontantes": {\n'
    '          "frente": "Rua Alberto Albertini",\n'
    '          "fundos": "Corredor Público",\n'
    '          "lateral_direita": "lote 05",\n'
    '          "lateral_esquerda": "lote 03"\n'
    '        },\n'
    '        "area_total": 429.66,\n'
    '        "angulos": {\n'
    '          "frente": 90.0,\n'
    '          "lateral_direita": 90.0,\n'
    '          "fundos": 90.0,\n'
    '          "lateral_esquerda": 90.0\n'
    '        },\n'
    '        "formato": "retangular",\n'
    '        "observacoes": ["terreno plano", "esquina"]\n'
    '      }\n'
    '    }\n'
    '  ],\n'
    '  "matricula_principal": "12345",\n'
    '  "matriculas_confrontantes": ["12346", "12347"],\n'
    '  "lotes_confrontantes": [\n'
    '    {\n'
    '      "identificador": "lote 11",\n'
    '      "tipo": "lote",\n'
    '      "matricula_anexada": "12346",\n'
    '      "direcao": "norte"\n'
    '    },\n'
    '    {\n'
    '      "identificador": "Rua das Flores",\n'
    '      "tipo": "via_publica",\n'
    '      "matricula_anexada": null,\n'
    '      "direcao": "sul"\n'
    '    }\n'
    '  ],\n'
    '  "matriculas_nao_confrontantes": ["12348"],\n'
    '  "lotes_sem_matricula": ["lote 12", "lote 15"],\n'
    '  "confrontacao_completa": true|false|null,\n'
    '  "proprietarios_identificados": {"12345": ["Nome"], "12346": ["Nome2"]},\n'
    '  "resumo_analise": {\n'
    '    "cadeia_dominial_completa": {\n'
    '      "12345": [\n'
    '        {"proprietario": "Origem/Titulação", "periodo": "até 2015", "percentual": "100%"},\n'
    '        {"proprietario": "João Silva", "periodo": "2015-2020", "percentual": "100%"},\n'
    '        {"proprietario": "Maria Santos", "periodo": "2020-atual", "percentual": "100%"}\n'
    '      ]\n'
    '    },\n'
    '    "restricoes_vigentes": [\n'
    '      {"tipo": "hipoteca", "credor": "Banco XYZ", "valor": "R$ 80.000,00", "status": "vigente"}\n'
    '    ],\n'
    '    "restricoes_baixadas": [\n'
    '      {"tipo": "penhora", "data_baixa": "10/12/2021", "motivo": "quitação judicial"}\n'
    '    ],\n'
    '    "estado_ms_direitos": {\n'
    '      "tem_direitos": true|false,\n'
    '      "detalhes": [\n'
    '        {"matricula": "12345", "tipo_direito": "credor_hipoteca", "status": "vigente", "valor": "R$ 50.000,00"},\n'
    '        {"matricula": "12346", "tipo_direito": "proprietario", "percentual": "50%", "status": "atual"}\n'
    '      ],\n'
    '      "criticidade": "alta|media|baixa",\n'
    '      "observacao": "Estado de MS possui hipoteca vigente na matrícula principal"\n'
    '    }\n'
    '  },\n'
    '  "confidence": 0.0-1.0,\n'
    '  "reasoning": "explicação detalhada da análise"\n'
    "}\n\n"
    "TIPOS DE CONFRONTANTES:\n"
    "- 'lote': lotes numerados (ex: lote 11, lote 15)\n"
    "- 'matrícula': matrículas identificadas por número\n"
    "- 'pessoa': nomes de pessoas proprietárias\n"
    "- 'via_publica': ruas, avenidas, praças\n"
    "- 'estado': Estado, Município, União\n"
    "- 'outros': córregos, rios, outros elementos\n\n"
    "INSTRUÇÕES ESPECIAIS:\n"
    "- Em 'lotes_confrontantes': liste TODOS os confrontantes com tipo e direção\n"
    "- Em 'matriculas_nao_confrontantes': matrículas anexadas que NÃO são confrontantes da principal\n"
    "- Em 'lotes_sem_matricula': lotes confrontantes mencionados sem matrícula anexada"
)

PARTIAL_PROMPT = (
    "Você receberá UM TRECHO de uma matrícula. Retorne APENAS JSON com:\n"
    '{ "confrontantes": ["..."], "evidence": ["trecho literal..."] }\n'
    "– Liste confrontantes exatamente como aparecerem no trecho (sem normalizar), e evidências curtas."
)


def _safe_get_dict(data, key, default=None):
    """Retorna valor do dicionário garantindo que seja do tipo correto."""
    if default is None:
        default = {}
    
    value = data.get(key, default)
    if not isinstance(value, dict):
        return default
    return value

def _safe_get_list(data, key, default=None):
    """Retorna valor do dicionário garantindo que seja uma lista."""
    if default is None:
        default = []
    
    value = data.get(key, default)
    if not isinstance(value, list):
        return default
    return value

def _safe_process_matricula_data(m_data):
    """Processa dados de matrícula de forma robusta, evitando erros com campos vazios."""
    if not isinstance(m_data, dict):
        return None
    
    try:
        # Processa cadeia dominial
        cadeia_dominial_obj = []
        cadeia_data = _safe_get_list(m_data, "cadeia_dominial")
        for transmissao_data in cadeia_data:
            if isinstance(transmissao_data, dict):
                transmissao = TransmissaoInfo(
                    data=transmissao_data.get("data"),
                    tipo_transmissao=transmissao_data.get("tipo_transmissao"),
                    proprietario_anterior=transmissao_data.get("proprietario_anterior"),
                    novo_proprietario=transmissao_data.get("novo_proprietario"),
                    percentual=transmissao_data.get("percentual"),
                    valor=transmissao_data.get("valor"),
                    registro=transmissao_data.get("registro")
                )
                cadeia_dominial_obj.append(transmissao)
        
        # Processa restrições
        restricoes_obj = []
        restricoes_data = _safe_get_list(m_data, "restricoes")
        for restricao_data in restricoes_data:
            if isinstance(restricao_data, dict):
                restricao = RestricaoInfo(
                    tipo=restricao_data.get("tipo", ""),
                    data_registro=restricao_data.get("data_registro"),
                    credor=restricao_data.get("credor"),
                    valor=restricao_data.get("valor"),
                    situacao=restricao_data.get("situacao", "vigente"),
                    data_baixa=restricao_data.get("data_baixa"),
                    observacoes=restricao_data.get("observacoes")
                )
                restricoes_obj.append(restricao)
        
        # Processa dados geométricos com validação robusta
        dados_geom_data = _safe_get_dict(m_data, "dados_geometricos")
        medidas = _safe_get_dict(dados_geom_data, "medidas")
        confrontantes_geom = _safe_get_dict(dados_geom_data, "confrontantes")
        angulos = _safe_get_dict(dados_geom_data, "angulos")
        observacoes_geom = _safe_get_list(dados_geom_data, "observacoes")
        
        dados_geometricos = DadosGeometricos(
            medidas=medidas,
            confrontantes=confrontantes_geom,
            area_total=dados_geom_data.get("area_total"),
            angulos=angulos,
            formato=dados_geom_data.get("formato", "retangular"),
            observacoes=observacoes_geom
        )
        
        # Processa listas principais com validação
        proprietarios = _safe_get_list(m_data, "proprietarios")
        confrontantes_list = _safe_get_list(m_data, "confrontantes")
        evidence = _safe_get_list(m_data, "evidence")
        
        matricula = MatriculaInfo(
            numero=str(m_data.get("numero", "")),
            proprietarios=proprietarios,
            descricao=str(m_data.get("descricao", "")),
            confrontantes=confrontantes_list,
            evidence=evidence,
            lote=m_data.get("lote"),
            quadra=m_data.get("quadra"),
            cadeia_dominial=cadeia_dominial_obj,
            restricoes=restricoes_obj,
            dados_geometricos=dados_geometricos
        )
        return matricula
        
    except Exception as e:
        print(f"⚠️ Erro ao processar dados da matrícula: {e}")
        return None

def analyze_with_vision_llm(model: str, file_path: str) -> AnalysisResult:
    """
    Analisa documento usando visão computacional da LLM (análise direta de imagens).
    """
    fname_placeholder = os.path.basename(file_path)
    
    try:
        print(f"🔍 Convertendo {fname_placeholder} para análise visual...")
        
        # Converte arquivo para imagens
        ext = os.path.splitext(file_path.lower())[1]
        if ext == ".pdf":
            # Verifica o número de páginas ANTES de processar
            try:
                total_pages = get_pdf_page_count(file_path)
                print(f"📊 PDF contém {total_pages} página(s)")
            except Exception as e:
                print(f"⚠️ Erro ao contar páginas: {e}")
                total_pages = 0
            
            # Removido limite de páginas - processará qualquer quantidade
            if total_pages > 100:
                print(f"⚠️ PDF com {total_pages} páginas - processamento pode demorar")
            
            try:
                images = pdf_to_images(file_path, max_pages=None)  # sem limite de páginas
                print(f"📄 PDF convertido em {len(images) if images else 0} página(s)")
            except Exception as e:
                print(f"❌ Erro ao converter PDF: {e}")
                print(f"🔍 Tipo do erro: {type(e).__name__}")
                raise ValueError(f"Erro ao converter PDF para imagens: {e}")
                
        elif ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]:
            try:
                images = [Image.open(file_path)]
                print(f"🖼️ Imagem carregada para análise")
            except Exception as e:
                print(f"❌ Erro ao abrir imagem: {e}")
                raise ValueError(f"Erro ao abrir imagem: {e}")
        else:
            raise ValueError(f"Formato de arquivo não suportado para análise visual: {ext}")
        
        if not images:
            raise ValueError("Não foi possível extrair imagens do arquivo")
        
        # Validação das imagens
        print(f"🔍 Validando {len(images)} imagem(ns)...")
        images_validas = []
        for i, img in enumerate(images):
            try:
                if img and hasattr(img, 'size') and img.size[0] > 0 and img.size[1] > 0:
                    images_validas.append(img)
                else:
                    print(f"⚠️ Imagem {i+1} inválida ou vazia")
            except Exception as e:
                print(f"⚠️ Erro ao validar imagem {i+1}: {e}")
        
        if not images_validas:
            raise ValueError("Nenhuma imagem válida foi extraída do arquivo")
            
        images = images_validas
        print(f"✅ {len(images)} imagem(ns) válida(s) para processar")
        
        print(f"🔄 Preparando {len(images)} imagem(ns) para envio à IA...")
        
        # Converte imagens para base64
        images_b64 = []
        total_size_kb = 0
        
        for i, img in enumerate(images):
            try:
                if not img or not hasattr(img, 'size'):
                    print(f"⚠️ Imagem {i+1} inválida - pulando")
                    continue
                    
                print(f"📐 Processando imagem {i+1}: {img.size[0]}x{img.size[1]} pixels")
                b64 = image_to_base64(img, max_size=1536)  # tamanho maior para documentos
                if b64:
                    size_kb = len(b64) // 1024
                    total_size_kb += size_kb
                    images_b64.append(b64)
                    print(f"✅ Imagem {i+1} preparada ({size_kb:.1f}KB)")
                    print(f"📊 Total acumulado: {total_size_kb:.1f}KB")
                else:
                    print(f"⚠️ Falha ao processar imagem {i+1}")
            except Exception as e:
                print(f"❌ Erro ao processar imagem {i+1}: {e}")
                print(f"🔍 Tipo do erro: {type(e).__name__}")
                continue
        
        print(f"📈 TOTAL: {len(images_b64)} imagens preparadas, {total_size_kb:.1f}KB")
        
        # Processamento inteligente baseado no tamanho real
        # Ajuste dinâmico da qualidade baseado no número de páginas
        if len(images_b64) > 50:
            print(f"⚠️ Muitas páginas ({len(images_b64)}) - otimizando qualidade automaticamente")
            # Reconverte com qualidade menor para muitas páginas
            print(f"🔍 DEBUG: Tentando otimizar {len(images)} imagens originais...")
            images_b64_temp = []
            try:
                for i, img in enumerate(images):
                    print(f"🔄 Reprocessando imagem {i+1}/{len(images)} com qualidade reduzida...")
                    # Qualidade menor para documentos grandes
                    b64 = image_to_base64(img, max_size=800, jpeg_quality=50)
                    if b64:
                        images_b64_temp.append(b64)
                        print(f"✅ Imagem {i+1} otimizada com sucesso")
                    else:
                        print(f"⚠️ Falha ao otimizar imagem {i+1}")
                images_b64 = images_b64_temp
                total_size_kb = sum(len(img) // 1024 for img in images_b64) if images_b64 else 0
                print(f"📈 APÓS OTIMIZAÇÃO: {len(images_b64)} imagens, {total_size_kb:.1f}KB")
            except Exception as e:
                print(f"❌ ERRO na otimização de muitas páginas: {e}")
                print(f"🔍 Tipo do erro: {type(e).__name__}")
                raise
        elif total_size_kb / 1024 > 20:  # Se maior que 20MB, otimiza
            print(f"⚠️ Payload grande ({total_size_kb/1024:.1f}MB) - otimizando qualidade")
            print(f"🔍 DEBUG: Tentando otimizar {len(images)} imagens originais...")
            images_b64_temp = []
            try:
                for i, img in enumerate(images):
                    print(f"🔄 Reprocessando imagem {i+1}/{len(images)} para reduzir tamanho...")
                    b64 = image_to_base64(img, max_size=1024, jpeg_quality=60)
                    if b64:
                        images_b64_temp.append(b64)
                        print(f"✅ Imagem {i+1} comprimida com sucesso")
                    else:
                        print(f"⚠️ Falha ao comprimir imagem {i+1}")
                images_b64 = images_b64_temp
                total_size_kb = sum(len(img) // 1024 for img in images_b64) if images_b64 else 0
                print(f"📈 APÓS OTIMIZAÇÃO: {len(images_b64)} imagens, {total_size_kb:.1f}KB")
            except Exception as e:
                print(f"❌ ERRO na otimização de payload grande: {e}")
                print(f"🔍 Tipo do erro: {type(e).__name__}")
                raise
        
        if not images_b64:
            raise ValueError("Não foi possível converter nenhuma imagem para envio")
        
        # Prompt específico para análise visual
        vision_prompt = (
            "Analise visualmente estas imagens de documentos de matrícula imobiliária de um processo de usucapião. "
            f"IDENTIFIQUE e EXTRAIA com precisão:\n\n"
            "1) TODOS os números de matrícula visíveis nos documentos\n"
            "2) Para cada matrícula:\n"
            "   - IDENTIFIQUE VISUALMENTE o número do LOTE e QUADRA (CRÍTICO para confrontações)\n"
            "     * Procure texto: 'lote nº', 'lote número', 'lote sob o nº', 'quadra nº'\n"
            "     * Exemplos visuais: 'lote 10', 'quadra 21', 'lote sob o nº 15'\n"
            "   - PROPRIETÁRIOS ATUAIS apenas (ignore vendedores/doadores antigos)\n"
            "     * Procure seções como 'PROPRIETÁRIO(S)' ou última transação registrada\n"
            "     * Se há histórico de vendas/doações, considere apenas o último titular\n"
            "   - Descrição do imóvel (localização, medidas)\n"
            "   - TODOS os confrontantes mencionados (CRÍTICO - NÃO PERCA NENHUM)\n"
            "3) DETERMINE qual matrícula é a principal (objeto do usucapião)\n"
            "4) 🚨 ANÁLISE PIXEL-POR-PIXEL DOS CONFRONTANTES (ULTRA CRÍTICO):\n"
            "   \n"
            "   🔍 ONDE PROCURAR VISUALMENTE:\n"
            "   - Seção 'DESCRIÇÃO DO IMÓVEL' da matrícula principal\n"
            "   - Qualquer parágrafo que descreva limites/perímetro do terreno\n"
            "   - Tabelas com informações de confrontação\n"
            "   - Averbações, registros, anotações manuscritas\n"
            "   - Carimbos com informações complementares\n"
            "   \n"
            "   📝 TEXTO VISUAL A IDENTIFICAR (OBRIGATÓRIO):\n"
            "   - 'confronta com', 'confrontando', 'confrontações'\n"
            "   - 'limita-se', 'limitado por', 'limites'\n"
            "   - 'faz divisa', 'divisa com', 'divisas'\n"
            "   - 'ao norte', 'ao sul', 'leste', 'oeste'\n"
            "   - 'frente', 'fundos', 'lateral'\n"
            "   - 'adjacente', 'vizinho'\n"
            "   \n"
            "   🎯 CONFRONTANTES A CAPTURAR VISUALMENTE:\n"
            "   - LOTES: 'lote 11', 'lote nº 09', 'lote sob o nº 15' (PRIORIDADE MÁXIMA)\n"
            "   - NÚMEROS DE MATRÍCULAS: '1.234', 'mat. 5678', 'matrícula 9999'\n"
            "   - NOMES DE PESSOAS: qualquer nome próprio mencionado como confrontante\n"
            "   - EMPRESAS: razões sociais vizinhas\n"
            "   - RUAS/AVENIDAS: nomes de vias públicas\n"
            "   - ESTADO/GOVERNO: 'Estado', 'MS', 'Fazenda Pública'\n"
            "   - RIOS/CÓRREGOS: acidentes geográficos\n"
            "   \n"
            "   ⚡ MÉTODO DE ANÁLISE VISUAL:\n"
            "   - LEIA palavra por palavra todo texto da descrição do imóvel principal\n"
            "   - TODO LOTE DEVE TER NO MÍNIMO 4 CONFRONTANTES (norte, sul, leste, oeste; ou nascente, poente, etc)\n"
            "   - Para cada direção mencionada, identifique EXATAMENTE o que confronta\n"
            "   - Se encontrou menos de 4 confrontantes, EXAMINE NOVAMENTE as imagens\n"
            "   - Não interprete: extraia o texto literal como confrontante\n"
            "   - Se vê 'confronta ao norte com João Silva', anote 'João Silva'\n"
            "   - Se vê 'limita ao sul com matrícula 1234', anote '1234'\n"
            "   - Se vê 'leste com lote 11', anote 'lote 11'\n"
            "   - Se vê 'frente para Rua X', anote 'Rua X'\n"
            "   - ALERTA: Se menos de 4 confrontantes, pode haver texto não detectado\n"
            "   \n"
            "5) VERIFICAÇÃO CRUZADA VISUAL:\n"
            "   - Se viu matrícula A confrontando com B, certifique-se que ambas estão no documento\n"
            "   - Liste TODAS as matrículas vistas como confrontantes\n"
            "   \n"
            "6) BUSCA ESPECÍFICA POR ESTADO DE MS:\n"
            "   - Escaneie todo documento procurando 'Estado', 'MS', 'Mato Grosso do Sul' como confrontante\n\n"
            "7) 📋 ANÁLISE VISUAL DA CADEIA DOMINIAL:\n"
            "   - Identifique visualmente todas as transmissões de propriedade\n"
            "   - Procure seções 'REGISTRO', 'TRANSMISSÕES', 'AVERBAÇÕES'\n"
            "   - Para cada transmissão: data, tipo, proprietário anterior, novo proprietário, percentual\n"
            "   - Considere co-propriedade como cadeias autônomas\n"
            "\n"
            "8) 🚨 IDENTIFICAÇÃO VISUAL DE RESTRIÇÕES:\n"
            "   - Procure por 'PENHORA', 'HIPOTECA', 'INDISPONIBILIDADE', 'ÔNUS'\n"
            "   - Verifique se há registros de 'BAIXA' ou 'CANCELAMENTO'\n"
            "   - Liste apenas restrições ainda VIGENTES\n"
            "\n🔥 VIDA OU MORTE: Cada confrontante perdido pode invalidar o usucapião. ZERO TOLERÂNCIA para omissões.\n\n"
            "🔄 ANÁLISE EM 2 PASSADAS EFICIENTES:\n"
            "\n"
            "PASSADA 1 - IDENTIFICAÇÃO:\n"
            "- Identifique a matrícula PRINCIPAL e todas as confrontantes\n"
            "- Conte confrontantes: mínimo 4 para cada direção\n"
            "- Se menos de 4: procure em outras seções do documento\n"
            "\n"
            "PASSADA 2 - VALIDAÇÃO:\n"
            "- Confirme proprietários ATUAIS (ignore vendedores antigos)\n"
            "- Verifique presença do Estado de MS como confrontante\n"
            "- Extraia lote/quadra de cada matrícula\n"
            "\n"
            "IMPORTANTE: LEIA com atenção todo o texto visível, incluindo tabelas, carimbos e anotações.\n"
            "Responda em JSON seguindo exatamente este formato:\n\n"
        )
        
        # Extrai o esquema JSON do AGGREGATE_PROMPT de forma segura
        try:
            if "Responda em JSON com este esquema:\n" in AGGREGATE_PROMPT:
                schema_part = AGGREGATE_PROMPT.split("Responda em JSON com este esquema:\n")[1]
            elif "Responda em JSON com este esquema EXPANDIDO:\n" in AGGREGATE_PROMPT:
                schema_part = AGGREGATE_PROMPT.split("Responda em JSON com este esquema EXPANDIDO:\n")[1]
            elif "Responda em JSON" in AGGREGATE_PROMPT:
                schema_part = AGGREGATE_PROMPT.split("Responda em JSON")[1].split(":\n")[1] if ":\n" in AGGREGATE_PROMPT.split("Responda em JSON")[1] else AGGREGATE_PROMPT.split("Responda em JSON")[1]
            else:
                schema_part = "{\n  \"matriculas_encontradas\": [],\n  \"matricula_principal\": null,\n  \"confrontacao_completa\": false\n}"
                
            vision_prompt += schema_part
            print(f"✅ Schema JSON extraído com sucesso ({len(schema_part)} chars)")
            
        except Exception as schema_error:
            print(f"⚠️ Erro ao extrair schema JSON: {schema_error}")
            fallback_schema = "{\n  \"matriculas_encontradas\": [],\n  \"matricula_principal\": null,\n  \"confrontacao_completa\": false\n}"
            vision_prompt += fallback_schema
        
        # Chama API com visão
        print(f"🚀 Enviando {len(images_b64)} imagem(ns) para {model}...")
        print(f"📏 Tamanho do prompt: {len(vision_prompt)} chars")
        
        print(f"🔍 DEBUG: Iniciando chamada da API...")
        data = call_openrouter_vision(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=vision_prompt,
            images_base64=images_b64,
            temperature=0.0,
            max_tokens=80000  # Tokens otimizados para análise eficiente
        )
        
        print(f"✅ Resposta da API recebida com sucesso")
        print(f"🔍 DEBUG: Iniciando processamento da resposta...")
        
        # Debug da estrutura da resposta
        print(f"🔍 Estrutura da resposta:")
        print(f"  - choices: {len(data.get('choices', []))} elementos")
        if data.get('choices'):
            choice = data['choices'][0]
            print(f"  - finish_reason: {choice.get('finish_reason')}")
            print(f"  - message keys: {list(choice.get('message', {}).keys())}")
            content = choice.get('message', {}).get('content', '')
            print(f"  - content length: {len(content) if content else 0}")
            if content:
                print(f"  - content preview: {content[:200]}...")
            else:
                print(f"  - content is: {repr(content)}")
        
        # Acesso seguro ao conteúdo da resposta
        try:
            if not data.get("choices") or len(data["choices"]) == 0:
                raise IndexError("Lista 'choices' vazia na resposta da API")
            
            choice = data["choices"][0]
            if not choice.get("message"):
                raise KeyError("Campo 'message' não encontrado na resposta")
                
            content = choice["message"].get("content", "")
            
            print(f"🔍 Content final: {len(content) if content else 0} chars")
            if content:
                print(f"📝 Primeiros 500 chars: {content[:500]}")
            else:
                print(f"⚠️ Content está vazio ou None!")
                
        except (IndexError, KeyError, TypeError) as e:
            print(f"❌ Erro ao acessar conteúdo da resposta: {e}")
            print(f"📊 Estrutura da resposta: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            raise RuntimeError(f"Estrutura de resposta inválida da API: {e}")
        
        try:
            print(f"🔍 DEBUG: Iniciando limpeza do JSON...")
            # Limpa marcadores de código markdown se presentes
            clean_content = clean_json_response(content)
            print(f"🔧 JSON limpo para parse: {clean_content[:100]}...")
            print(f"🔍 DEBUG: JSON limpo tem {len(clean_content)} caracteres")
            
            print(f"🔍 DEBUG: Tentando fazer json.loads()...")
            parsed = json.loads(clean_content)
            print(f"✅ JSON parsed com sucesso! Tipo: {type(parsed)}")
            print(f"🔍 Keys no parsed: {list(parsed.keys()) if isinstance(parsed, dict) else 'não é dict'}")
        except json.JSONDecodeError as e:
            print(f"❌ Erro ao fazer parse do JSON da visão: {e}")
            print(f"📄 Conteúdo completo da resposta:")
            print(content)
            parsed = {
                "matriculas_encontradas": [],
                "matricula_principal": None,
                "matriculas_confrontantes": [],
                "lotes_confrontantes": [],
                "matriculas_nao_confrontantes": [],
                "lotes_sem_matricula": [],
                "confrontacao_completa": None,
                "proprietarios_identificados": {},
                "confidence": None,
                "reasoning": f"Erro de parsing JSON da análise visual: {content[:500]}..."
            }

        # Converte dados das matrículas para objetos MatriculaInfo usando processamento seguro
        matriculas_obj = []
        for m_data in parsed.get("matriculas_encontradas", []):
            matricula = _safe_process_matricula_data(m_data)
            if matricula is not None:
                matriculas_obj.append(matricula)

        # Processa lotes confrontantes
        print(f"🔍 DEBUG: Processando lotes confrontantes...")
        lotes_confrontantes_obj = []
        lotes_confrontantes_raw = parsed.get("lotes_confrontantes", [])
        print(f"🔍 lotes_confrontantes encontrados: {len(lotes_confrontantes_raw)} itens")
        
        try:
            for i, lote_data in enumerate(lotes_confrontantes_raw):
                print(f"🔍 Processando lote {i+1}: {type(lote_data)}")
                if isinstance(lote_data, dict):
                    lote_confronta = LoteConfronta(
                        identificador=lote_data.get("identificador", ""),
                        tipo=lote_data.get("tipo", "outros"),
                        matricula_anexada=lote_data.get("matricula_anexada"),
                        direcao=lote_data.get("direcao")
                    )
                    lotes_confrontantes_obj.append(lote_confronta)
                    print(f"✅ Lote {i+1} processado com sucesso")
                else:
                    print(f"⚠️ Lote {i+1} não é dict: {lote_data}")
        except Exception as e:
            print(f"❌ ERRO ao processar lotes confrontantes: {e}")
            print(f"🔍 Tipo do erro: {type(e).__name__}")
            raise

        # Processa resumo da análise com tratamento seguro
        resumo_data = _safe_get_dict(parsed, "resumo_analise")
        
        # Processa direitos do Estado de MS
        estado_ms_data = _safe_get_dict(resumo_data, "estado_ms_direitos")
        estado_ms_direitos = EstadoMSDireitos(
            tem_direitos=bool(estado_ms_data.get("tem_direitos", False)),
            detalhes=_safe_get_list(estado_ms_data, "detalhes"),
            criticidade=str(estado_ms_data.get("criticidade", "baixa")),
            observacao=str(estado_ms_data.get("observacao", ""))
        )
        
        resumo_analise = ResumoAnalise(
            cadeia_dominial_completa=_safe_get_list(resumo_data, "cadeia_dominial_completa"),
            restricoes_vigentes=_safe_get_list(resumo_data, "restricoes_vigentes"),
            restricoes_baixadas=_safe_get_list(resumo_data, "restricoes_baixadas"),
            estado_ms_direitos=estado_ms_direitos
        )

        return AnalysisResult(
            arquivo=fname_placeholder,
            matriculas_encontradas=matriculas_obj,
            matricula_principal=parsed.get("matricula_principal"),
            matriculas_confrontantes=parsed.get("matriculas_confrontantes", []),
            lotes_confrontantes=lotes_confrontantes_obj,
            matriculas_nao_confrontantes=parsed.get("matriculas_nao_confrontantes", []),
            lotes_sem_matricula=parsed.get("lotes_sem_matricula", []),
            confrontacao_completa=parsed.get("confrontacao_completa"),
            proprietarios_identificados=parsed.get("proprietarios_identificados", {}),
            resumo_analise=resumo_analise,
            confidence=parsed.get("confidence"),
            reasoning=parsed.get("reasoning", ""),
            raw_json=parsed
        )
        
    except Exception as e:
        # CAPTURE O ERRO E MOSTRE LOGS DETALHADOS ANTES DE RETORNAR
        print(f"🚨 CAPTURADO ERRO GERAL na análise visual!")
        print(f"❌ Tipo do erro: {type(e).__name__}")
        print(f"❌ Mensagem do erro: {str(e)}")
        print(f"❌ Arquivo sendo processado: {fname_placeholder}")
        
        # Traceback detalhado
        import traceback
        print(f"📍 Traceback completo:")
        traceback.print_exc()
        
        # Se análise visual falhar, retorna erro estruturado
        return AnalysisResult(
            arquivo=fname_placeholder,
            matriculas_encontradas=[],
            matricula_principal=None,
            matriculas_confrontantes=[],
            lotes_confrontantes=[],
            matriculas_nao_confrontantes=[],
            lotes_sem_matricula=[],
            confrontacao_completa=None,
            proprietarios_identificados={},
            confidence=None,
            reasoning=f"Erro na análise visual: {str(e)}",
            raw_json={}
        )

# Função analyze_text_with_llm removida - pipeline textual obsoleto
    """
    Estratégia:
    - Se texto for curto: chamada única com prompt agregado.
    - Se texto for longo: faz passadas parciais para extrair confrontantes/evidências, deduplica,
      e faz uma chamada final curta passando o resumo + um trecho representativo do original.
    """
    fname_placeholder = "<arquivo>"
    text = full_text.strip()
    if not text:
        return AnalysisResult(
            arquivo=fname_placeholder,
            matriculas_encontradas=[],
            matricula_principal=None,
            matriculas_confrontantes=[],
            lotes_confrontantes=[],
            matriculas_nao_confrontantes=[],
            lotes_sem_matricula=[],
            confrontacao_completa=None,
            proprietarios_identificados={},
            confidence=None,
            reasoning="Texto vazio após OCR.",
            raw_json={}
        )

    chunks = chunk_text(text, max_chars=18000)

    # Caso simples: uma chamada direta
    if len(chunks) == 1:
        data = call_openrouter(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=AGGREGATE_PROMPT + "\n\nTEXTO:\n" + chunks[0],
            temperature=0.0,
            max_tokens=1500
        )
        # Acesso seguro ao conteúdo
        try:
            if not data.get("choices") or len(data["choices"]) == 0:
                raise IndexError("Lista 'choices' vazia na resposta da API")
            content = data["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as e:
            print(f"Erro ao acessar conteúdo da resposta: {e}")
            parsed = {
                "matriculas_encontradas": [],
                "matricula_principal": None,
                "matriculas_confrontantes": [],
                "lotes_confrontantes": [],
                "matriculas_nao_confrontantes": [],
                "lotes_sem_matricula": [],
                "confrontacao_completa": None,
                "proprietarios_identificados": {},
                "confidence": None,
                "reasoning": f"Erro de estrutura da resposta da API: {e}"
            }
        else:
            try:
                clean_content = clean_json_response(content)
                parsed = json.loads(clean_content)
            except json.JSONDecodeError as e:
                print(f"Erro ao fazer parse do JSON: {e}")
                print(f"Conteúdo da resposta: {content[:500]}")
                parsed = {
                    "matriculas_encontradas": [],
                    "matricula_principal": None,
                    "matriculas_confrontantes": [],
                    "lotes_confrontantes": [],
                    "matriculas_nao_confrontantes": [],
                    "lotes_sem_matricula": [],
                    "confrontacao_completa": None,
                    "proprietarios_identificados": {},
                    "confidence": None,
                    "reasoning": f"Erro de parsing JSON: {content}"
                }

        # Converte dados das matrículas para objetos MatriculaInfo usando processamento seguro
        matriculas_obj = []
        for m_data in parsed.get("matriculas_encontradas", []):
            matricula = _safe_process_matricula_data(m_data)
            if matricula is not None:
                matriculas_obj.append(matricula)

        return AnalysisResult(
            arquivo=fname_placeholder,
            matriculas_encontradas=matriculas_obj,
            matricula_principal=parsed.get("matricula_principal"),
            matriculas_confrontantes=parsed.get("matriculas_confrontantes", []),
            lotes_confrontantes=[],  # TODO: implementar processamento de lotes para texto
            matriculas_nao_confrontantes=parsed.get("matriculas_nao_confrontantes", []),
            lotes_sem_matricula=parsed.get("lotes_sem_matricula", []),
            confrontacao_completa=parsed.get("confrontacao_completa"),
            proprietarios_identificados=parsed.get("proprietarios_identificados", {}),
            confidence=parsed.get("confidence"),
            reasoning=parsed.get("reasoning", ""),
            raw_json=parsed
        )

    # Texto longo: pipeline parcial
    all_confrontantes = []
    all_evidence = []

    for i, ch in enumerate(chunks, 1):
        data = call_openrouter(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=PARTIAL_PROMPT + "\n\nTRECHO:\n" + ch,
            temperature=0.0,
            max_tokens=800
        )
        # Acesso seguro ao conteúdo do chunk
        try:
            if not data.get("choices") or len(data["choices"]) == 0:
                print(f"Chunk {i}: Lista 'choices' vazia")
                continue
            content = data["choices"][0]["message"]["content"]
        except (IndexError, KeyError, TypeError) as e:
            print(f"Erro no chunk {i} ao acessar resposta: {e}")
            continue
            
        try:
            clean_content = clean_json_response(content)
            parsed = json.loads(clean_content)
            if "confrontantes" in parsed and isinstance(parsed["confrontantes"], list):
                all_confrontantes.extend([c for c in parsed["confrontantes"] if isinstance(c, str)])
            if "evidence" in parsed and isinstance(parsed["evidence"], list):
                all_evidence.extend([e for e in parsed["evidence"] if isinstance(e, str)])
        except json.JSONDecodeError as e:
            print(f"Erro JSON no chunk {i}: {e}")
            print(f"Conteúdo: {content[:200] if 'content' in locals() else 'N/A'}")
        except Exception as e:
            print(f"Erro no chunk {i}: {e}")
            # ignora erro parcial

    # Deduplicação leve mantendo ordem
    seen = set()
    dedup_confrontantes = []
    for c in all_confrontantes:
        key = c.strip().lower()
        if key and key not in seen:
            seen.add(key)
            dedup_confrontantes.append(c.strip())

    # Chamada final curta com resumo
    resumo = {
        "confrontantes_coletados": dedup_confrontantes[:200],
        "amostras_evidencia": all_evidence[:20]
    }
    final_user = (
        AGGREGATE_PROMPT
        + "\n\nRESUMO PREPARADO (use para decidir):\n"
        + json.dumps(resumo, ensure_ascii=False, indent=2)
        + "\n\nNota: Decida com base no resumo; se faltar certeza, indique is_confrontante=null com reasoning."
    )

    data = call_openrouter(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=final_user,
        temperature=0.0,
        max_tokens=900
    )
    # Acesso seguro ao conteúdo da chamada final
    try:
        if not data.get("choices") or len(data["choices"]) == 0:
            raise IndexError("Lista 'choices' vazia na resposta final da API")
        content = data["choices"][0]["message"]["content"]
    except (IndexError, KeyError, TypeError) as e:
        print(f"Erro ao acessar resposta final: {e}")
        parsed = {
            "matriculas_encontradas": [],
            "matricula_principal": None,
            "matriculas_confrontantes": [],
            "lotes_confrontantes": [],
            "matriculas_nao_confrontantes": [],
            "lotes_sem_matricula": [],
            "confrontacao_completa": None,
            "proprietarios_identificados": {},
            "confidence": None,
            "reasoning": f"Erro de estrutura na resposta final da API: {e}"
        }
    else:
        try:
            clean_content = clean_json_response(content)
            parsed = json.loads(clean_content)
        except json.JSONDecodeError as e:
            print(f"Erro JSON na chamada final: {e}")
            print(f"Conteúdo: {content[:500]}")
            parsed = {
                "matriculas_encontradas": [],
                "matricula_principal": None,
                "matriculas_confrontantes": [],
                "lotes_confrontantes": [],
                "matriculas_nao_confrontantes": [],
                "lotes_sem_matricula": [],
                "confrontacao_completa": None,
                "proprietarios_identificados": {},
                "confidence": None,
                "reasoning": f"Erro JSON: {content}"
            }

    # Converte dados das matrículas para objetos MatriculaInfo
    matriculas_obj = []
    for m_data in parsed.get("matriculas_encontradas", []):
        if isinstance(m_data, dict):
            matricula = MatriculaInfo(
                numero=m_data.get("numero", ""),
                proprietarios=m_data.get("proprietarios", []),
                descricao=m_data.get("descricao", ""),
                confrontantes=m_data.get("confrontantes", []),
                evidence=m_data.get("evidence", [])
            )
            matriculas_obj.append(matricula)

    # Se não encontrou matrículas estruturadas, cria uma genérica com dados coletados
    if not matriculas_obj and (dedup_confrontantes or all_evidence):
        matricula_generica = MatriculaInfo(
            numero="não identificado",
            proprietarios=[],
            descricao="",
            confrontantes=dedup_confrontantes,
            evidence=all_evidence[:20],
            lote=None,
            quadra=None
        )
        matriculas_obj.append(matricula_generica)

    return AnalysisResult(
        arquivo=fname_placeholder,
        matriculas_encontradas=matriculas_obj,
        matricula_principal=parsed.get("matricula_principal"),
        matriculas_confrontantes=parsed.get("matriculas_confrontantes", []),
        lotes_confrontantes=[],
        matriculas_nao_confrontantes=parsed.get("matriculas_nao_confrontantes", []),
        lotes_sem_matricula=parsed.get("lotes_sem_matricula", []),
        confrontacao_completa=parsed.get("confrontacao_completa"),
        proprietarios_identificados=parsed.get("proprietarios_identificados", {}),
        confidence=parsed.get("confidence"),
        reasoning=parsed.get("reasoning", ""),
        raw_json=parsed
    )

# =========================
# GUI
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x700")
        self.minsize(1000, 650)

        self.files: List[str] = []
        self.results: Dict[str, AnalysisResult] = {}
        self.queue = queue.Queue()

        self.create_widgets()
        self.poll_queue()

    def create_widgets(self):
        # Top frame (controles)
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=8)

        self.btn_add = ttk.Button(top, text="Adicionar PDFs/Imagens", command=self.add_files)
        self.btn_add.pack(side="left")

        self.btn_remove = ttk.Button(top, text="Remover Selecionados", command=self.remove_selected)
        self.btn_remove.pack(side="left", padx=(8,0))

        ttk.Label(top, text="Matrícula Principal (opcional):").pack(side="left", padx=(16,4))
        self.matricula_var = tk.StringVar()
        self.matricula_entry = ttk.Entry(top, textvariable=self.matricula_var, width=15)
        self.matricula_entry.pack(side="left")
        
        # Adiciona placeholder manual
        def add_placeholder():
            if not self.matricula_var.get():
                self.matricula_entry.insert(0, "ex: 12345")
                self.matricula_entry.config(foreground='gray')
        
        def remove_placeholder(event):
            if self.matricula_entry.get() == "ex: 12345":
                self.matricula_entry.delete(0, tk.END)
                self.matricula_entry.config(foreground='black')
        
        def validate_placeholder(event):
            if not self.matricula_entry.get():
                add_placeholder()
        
        self.matricula_entry.bind('<FocusIn>', remove_placeholder)
        self.matricula_entry.bind('<FocusOut>', validate_placeholder)
        add_placeholder()
        
        ttk.Label(top, text="Modelo com Visão:").pack(side="left", padx=(16,4))
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.model_entry = ttk.Entry(top, textvariable=self.model_var, width=25)
        self.model_entry.pack(side="left")
        
        # Dica sobre modelos com visão
        info_btn = ttk.Button(top, text="?", width=3, command=self.show_model_info)
        info_btn.pack(side="left", padx=(2,0))

        self.btn_process = ttk.Button(top, text="Processar", command=self.process_all)
        self.btn_process.pack(side="left", padx=12)

        self.btn_export = ttk.Button(top, text="Exportar CSV", command=self.export_csv)
        self.btn_export.pack(side="left")
        
        self.btn_generate_plant = ttk.Button(top, text="Gerar Planta", command=self.generate_property_plant)
        self.btn_generate_plant.pack(side="left", padx=(8,0))

        # Progress bar
        self.progress = ttk.Progressbar(top, orient="horizontal", mode="determinate", length=220)
        self.progress.pack(side="right")

        # Split: esquerda (lista arquivos) / direita (resultados)
        split = ttk.Panedwindow(self, orient="horizontal")
        split.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Esquerda: arquivos
        left = ttk.Frame(split)
        split.add(left, weight=1)

        ttk.Label(left, text="Arquivos anexados").pack(anchor="w", pady=(0,4))
        self.tree_files = ttk.Treeview(left, columns=("caminho",), show="headings", height=12)
        self.tree_files.heading("caminho", text="Caminho")
        self.tree_files.pack(fill="both", expand=True)
        self.tree_files.bind("<Delete>", lambda e: self.remove_selected())

        # Direita: resultados
        right = ttk.Frame(split)
        split.add(right, weight=2)

        # Área de alerta para direitos do Estado de MS
        alert_frame = ttk.Frame(right)
        alert_frame.pack(fill="x", padx=5, pady=(0,10))
        
        self.estado_alert_var = tk.StringVar()
        self.estado_alert_label = ttk.Label(
            alert_frame, 
            textvariable=self.estado_alert_var,
            font=("Arial", 10, "bold"),
            foreground="red",
            background="yellow",
            relief="solid",
            borderwidth=2,
            padding=5
        )
        # Label inicialmente oculto
        self.estado_alert_label.pack_forget()
        
        ttk.Label(right, text="Imóveis Confrontantes").pack(anchor="w", pady=(0,4))
        cols = ("matricula", "lote_quadra", "tipo", "proprietario", "estado_ms", "confianca")
        self.tree_results = ttk.Treeview(right, columns=cols, show="tree headings", height=12)
        self.tree_results.heading("#0", text="")  # Coluna da árvore
        self.tree_results.heading("matricula", text="Matrícula")
        self.tree_results.heading("lote_quadra", text="Lote/Quadra")
        self.tree_results.heading("tipo", text="Tipo")
        self.tree_results.heading("proprietario", text="Proprietário")
        self.tree_results.heading("estado_ms", text="Estado MS")
        self.tree_results.heading("confianca", text="Confiança")
        
        self.tree_results.column("#0", width=30, minwidth=30)  # Coluna da árvore (ícones)
        self.tree_results.column("matricula", width=100, anchor="center")
        self.tree_results.column("lote_quadra", width=100, anchor="center")
        self.tree_results.column("tipo", width=90, anchor="center")
        self.tree_results.column("proprietario", width=220)  # Ajustada para acomodar nova coluna
        self.tree_results.column("estado_ms", width=80, anchor="center")
        self.tree_results.column("confianca", width=80, anchor="center")
        self.tree_results.pack(fill="both", expand=True)

        # Botões de ação sobre resultado
        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=6)
        self.btn_ver = ttk.Button(btns, text="Ver Detalhes", command=self.show_details)
        self.btn_ver.pack(side="left")
        ttk.Label(btns, text="  ").pack(side="left")  # espaçador
        
        # Campo de resumo (maior para melhor legibilidade)
        ttk.Label(right, text="Resumo da Análise").pack(anchor="w", pady=(10,4))
        self.txt_resumo = tk.Text(right, height=8, wrap=tk.WORD, state=tk.DISABLED, font=("TkDefaultFont", 10))
        self.txt_resumo.pack(fill="both", expand=True, pady=(0,6))

        # Log
        ttk.Label(self, text="Log / Mensagens").pack(anchor="w", padx=10)
        self.txt_log = tk.Text(self, height=8)
        self.txt_log.pack(fill="both", expand=False, padx=10, pady=(0,10))

    # ---------- Ações ----------
    def add_files(self):
        paths = filedialog.askopenfilenames(
            title="Selecione PDFs ou imagens",
            filetypes=[
                ("PDF e Imagem", "*.pdf;*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp"),
                ("PDF", "*.pdf"),
                ("Imagens", "*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.bmp;*.webp"),
                ("Todos", "*.*"),
            ]
        )
        if not paths:
            return
        new = 0
        for p in paths:
            p = os.path.abspath(p)
            if p not in self.files:
                self.files.append(p)
                self.tree_files.insert("", "end", values=(p,))
                new += 1
        if new:
            self.log(f"{new} arquivo(s) adicionado(s).")

    def remove_selected(self):
        sel = self.tree_files.selection()
        removed = 0
        for item in sel:
            path = self.tree_files.item(item, "values")[0]
            if path in self.files:
                self.files.remove(path)
            self.tree_files.delete(item)
            removed += 1
        if removed:
            self.log(f"{removed} arquivo(s) removido(s).")

    def process_all(self):
        if not self.files:
            messagebox.showwarning("Nada a processar", "Adicione pelo menos um arquivo.")
            return
        model = self.model_var.get().strip()
        if not model:
            messagebox.showwarning("Modelo", "Informe um modelo do OpenRouter.")
            return

        self.progress["value"] = 0
        self.progress["maximum"] = len(self.files)
        self.results.clear()
        for i in self.tree_results.get_children():
            self.tree_results.delete(i)

        t = threading.Thread(target=self._worker_process, args=(model,), daemon=True)
        t.start()

    def _worker_process(self, model: str):
        for idx, path in enumerate(self.files, 1):
            filename = os.path.basename(path)
            try:
                self.queue.put(("log", f"📄 Processando {filename} ({idx}/{len(self.files)})"))
                
                # Verifica se o arquivo existe e diagnostica problemas
                if not os.path.exists(path):
                    self.queue.put(("log", f"❌ Arquivo não encontrado: {filename}"))
                    continue
                
                # Diagnóstico do arquivo
                diagnostico = self.diagnose_file_issues(path)
                if "❌" in diagnostico or "⚠️" in diagnostico:
                    self.queue.put(("log", f"🔍 Diagnóstico: {diagnostico}"))
                
                # Análise visual direta com IA
                self.queue.put(("log", f"👁️ Analisando documento visualmente com IA..."))
                
                # Adiciona número da matrícula informado pelo usuário (se houver)
                matricula_informada = self.matricula_var.get().strip()
                if matricula_informada and matricula_informada != "ex: 12345":
                    matricula_normalizada = matricula_informada.replace(".", "").replace(" ", "")
                    self.queue.put(("log", f"📝 Matrícula de referência informada: {matricula_normalizada}"))
                
                res = analyze_with_vision_llm(model, path)
                res.arquivo = filename
                self.results[path] = res

                # Log dos resultados principais
                if res.reasoning and "Erro na análise visual" in res.reasoning:
                    # Extrai mais detalhes do erro com proteção
                    try:
                        partes = res.reasoning.split("Erro na análise visual: ")
                        if len(partes) > 1:
                            erro_detalhes = partes[-1][:100]
                        else:
                            erro_detalhes = res.reasoning[:100]
                    except Exception:
                        erro_detalhes = "Erro desconhecido"
                    
                    self.queue.put(("log", f"⚠️ Problema na análise visual: {erro_detalhes}"))
                    self.queue.put(("log", f"💡 Possíveis causas: arquivo muito grande, ilegível ou formato não suportado"))
                elif res.matriculas_encontradas:
                    self.queue.put(("log", f"📋 {len(res.matriculas_encontradas)} matrícula(s) identificada(s) visualmente"))
                    if res.matricula_principal:
                        self.queue.put(("log", f"🏠 Matrícula principal: {res.matricula_principal}"))
                    if res.matriculas_confrontantes:
                        self.queue.put(("log", f"🔗 {len(res.matriculas_confrontantes)} matrícula(s) confrontante(s)"))
                    if res.is_confrontante:
                        self.queue.put(("log", f"🏛️ Estado de MS identificado como confrontante"))
                else:
                    self.queue.put(("log", f"⚠️ Nenhuma matrícula foi identificada no documento"))
                
                # Prepara dados para exibição na tabela
                mat_principal = res.matricula_principal or "Não identificada"
                mat_confrontantes = ", ".join(res.matriculas_confrontantes[:3]) + ("..." if len(res.matriculas_confrontantes) > 3 else "")
                if not mat_confrontantes:
                    mat_confrontantes = "Nenhuma"
                
                estado_ms = "SIM" if res.is_confrontante else "NÃO"
                
                
                # Formata confiança (já vem como percentual da API)
                if res.confidence is not None:
                    confianca_pct = f"{int(res.confidence)}%"
                else:
                    confianca_pct = "N/A"
                
                # Resumo dos proprietários
                proprietarios_resumo = []
                for numero, props in list(res.proprietarios_identificados.items())[:2]:
                    if props:
                        proprietarios_resumo.append(f"{numero}: {props[0]}" + ("..." if len(props) > 1 else ""))
                proprietarios_texto = " | ".join(proprietarios_resumo)
                if not proprietarios_texto:
                    proprietarios_texto = "Não identificados"

                # Mensagem de conclusão baseada no status
                if res.reasoning and "Erro na análise visual" in res.reasoning:
                    self.queue.put(("log", f"⚠️ Análise de {filename} concluída com problemas (confiança: {confianca_pct})"))
                elif res.matriculas_encontradas:
                    self.queue.put(("log", f"✅ Análise de {filename} concluída com sucesso (confiança: {confianca_pct})"))
                else:
                    self.queue.put(("log", f"ℹ️ Análise de {filename} concluída - nenhuma matrícula identificada (confiança: {confianca_pct})"))
                
                self.queue.put(("result", (path, res)))
                
            except Exception as e:
                error_msg = str(e)
                if "páginas excede o limite máximo" in error_msg:
                    self.queue.put(("log", f"🚫 {filename}: {error_msg}"))
                else:
                    self.queue.put(("log", f"❌ Erro ao processar {filename}: {error_msg}"))
            finally:
                self.queue.put(("progress", 1))

    def export_csv(self):
        if not self.results:
            messagebox.showinfo("Sem resultados", "Nada para exportar ainda.")
            return
        out = filedialog.asksaveasfilename(
            title="Salvar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not out:
            return
        try:
            import csv
            with open(out, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["arquivo", "matricula_principal", "matriculas_confrontantes", "estado_ms_confrontante", 
                           "confianca_percentual", "proprietarios", "reasoning"])
                for path, res in self.results.items():
                    # Formata confiança (já vem como percentual da API)
                    confianca_pct = f"{int(res.confidence)}%" if res.confidence is not None else "N/A"
                    
                    # Prepara proprietários para CSV
                    proprietarios_csv = []
                    for numero, props in res.proprietarios_identificados.items():
                        if props:
                            proprietarios_csv.append(f"{numero}: {'; '.join(props)}")
                    
                    w.writerow([
                        res.arquivo,
                        res.matricula_principal or "Não identificada",
                        " | ".join(res.matriculas_confrontantes),
                        "SIM" if res.is_confrontante else "NÃO",
                        confianca_pct,
                        " | ".join(proprietarios_csv),
                        res.reasoning.replace("\n", " ").strip()
                    ])
            self.log(f"CSV salvo em: {out}")
        except Exception as e:
            messagebox.showerror("Erro ao salvar", str(e))

    def show_details(self):
        sel = self.tree_results.selection()
        if not sel:
            messagebox.showinfo("Detalhes", "Selecione um resultado.")
            return
        
        # Para a nova estrutura hierárquica, usa o primeiro resultado disponível
        # (já que só temos um resultado por análise)
        if not self.results:
            messagebox.showwarning("Ops", "Nenhum resultado disponível.")
            return
        
        # Pega o primeiro resultado
        res = next(iter(self.results.values()))
        self._open_details_window(res)

    def _open_details_window(self, res: AnalysisResult):
        win = tk.Toplevel(self)
        win.title(f"Análise de Usucapião – {res.arquivo}")
        win.geometry("1100x700")

        frm = ttk.Frame(win)
        frm.pack(fill="both", expand=True, padx=10, pady=10)

        # Resumo geral
        estado_ms = "SIM" if res.is_confrontante else "NÃO"
        
        # Converte confiança para percentual
        if res.confidence is not None:
            confianca_display = f"{int(res.confidence)}%"
        else:
            confianca_display = "N/A"
            
        ttk.Label(frm, text=f"Estado MS confrontante: {estado_ms}   |   Confiança: {confianca_display}").pack(anchor="w", pady=(0,6))

        # Matrícula principal
        ttk.Label(frm, text="Matrícula Principal (Usucapião):").pack(anchor="w")
        box_principal = tk.Text(frm, height=3)
        box_principal.pack(fill="x", pady=(0,8))
        mat_principal_text = res.matricula_principal or "Não identificada"
        if res.matricula_principal and res.matricula_principal in res.proprietarios_identificados:
            proprietarios = res.proprietarios_identificados[res.matricula_principal]
            mat_principal_text += f"\nProprietários: {', '.join(proprietarios)}"
        box_principal.insert("1.0", mat_principal_text)
        box_principal.configure(state="disabled")

        # Matrículas encontradas
        ttk.Label(frm, text="Todas as Matrículas Identificadas:").pack(anchor="w")
        box_matriculas = tk.Text(frm, height=8)
        box_matriculas.pack(fill="both", expand=False, pady=(0,8))
        
        matriculas_text = []
        for i, matricula in enumerate(res.matriculas_encontradas, 1):
            matriculas_text.append(f"{i}. Matrícula: {matricula.numero}")
            if matricula.proprietarios:
                matriculas_text.append(f"   Proprietários: {', '.join(matricula.proprietarios)}")
            if matricula.confrontantes:
                matriculas_text.append(f"   Confrontantes: {', '.join(matricula.confrontantes[:5])}" + ("..." if len(matricula.confrontantes) > 5 else ""))
            matriculas_text.append("")
        
        if not matriculas_text:
            matriculas_text = ["Nenhuma matrícula foi identificada estruturadamente"]
            
        box_matriculas.insert("1.0", "\n".join(matriculas_text))
        box_matriculas.configure(state="disabled")

        # Matrículas confrontantes
        ttk.Label(frm, text="Matrículas Confrontantes:").pack(anchor="w")
        box_confrontantes = tk.Text(frm, height=4)
        box_confrontantes.pack(fill="x", pady=(0,8))
        confrontantes_text = ", ".join(res.matriculas_confrontantes) if res.matriculas_confrontantes else "Nenhuma identificada"
        box_confrontantes.insert("1.0", confrontantes_text)
        box_confrontantes.configure(state="disabled")

        # Raciocínio
        ttk.Label(frm, text="🧠 Raciocínio Pericial da IA:").pack(anchor="w")
        box_reasoning = tk.Text(frm, height=8, font=("TkDefaultFont", 10), wrap="word")
        box_reasoning.pack(fill="both", expand=True)
        
        # Formata o reasoning para melhor legibilidade
        reasoning_texto = res.reasoning if res.reasoning else "Raciocínio não disponível."
        if reasoning_texto and not reasoning_texto.startswith(("📋", "🧠", "🎯")):
            reasoning_texto = f"📋 {reasoning_texto}"
        
        box_reasoning.insert("1.0", reasoning_texto)
        box_reasoning.configure(state="disabled")

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "result":
                    # payload agora contém: path, result_object (AnalysisResult)
                    path, result = payload
                    self.populate_results_tree(result)
                    self.update_summary(result)
                    # Atualiza alerta sobre direitos do Estado de MS
                    self.update_estado_alert()
                elif kind == "progress":
                    val = self.progress["value"] + payload
                    self.progress["value"] = val
        except queue.Empty:
            pass
        self.after(100, self.poll_queue)

    def populate_results_tree(self, result):
        """Popula a tabela com estrutura hierárquica: principal + confrontantes + não confrontantes"""
        # Limpa resultados anteriores para este arquivo
        for item in self.tree_results.get_children():
            self.tree_results.delete(item)
        
        if not result:
            return
        
        # Encontra a matrícula principal nos dados
        matricula_principal_obj = None
        if result.matricula_principal:
            for mat in result.matriculas_encontradas:
                if mat.numero == result.matricula_principal:
                    matricula_principal_obj = mat
                    break
        
        estado_ms = "SIM" if result.matriculas_confrontantes and any("Estado" in str(conf) or "MS" in str(conf) for conf in result.matriculas_confrontantes) else "NÃO"
        
        # Debug e formatação da confiança
        if result.confidence is not None:
            print(f"🔍 DEBUG Confiança na tabela: {result.confidence} (tipo: {type(result.confidence)})")
            # Se o valor está entre 0.0 e 1.0, multiplica por 100
            if isinstance(result.confidence, (int, float)) and 0 <= result.confidence <= 1:
                confianca = f"{int(result.confidence * 100)}%"
            else:
                confianca = f"{int(result.confidence)}%"
        else:
            confianca = "N/A"
        
        # Insere matrícula principal - cada proprietário em linha separada
        proprietarios_principal = ["N/A"]  # Valor padrão
        lote_quadra_principal = ""
        
        if matricula_principal_obj:
            proprietarios_principal = matricula_principal_obj.proprietarios
            if not proprietarios_principal:
                proprietarios_principal = ["N/A"]
            
            # Formata informação de lote/quadra da matrícula principal
            if matricula_principal_obj.lote or matricula_principal_obj.quadra:
                lote_parts = []
                if matricula_principal_obj.lote:
                    lote_parts.append(f"Lote {matricula_principal_obj.lote}")
                if matricula_principal_obj.quadra:
                    lote_parts.append(f"Quadra {matricula_principal_obj.quadra}")
                lote_quadra_principal = " / ".join(lote_parts)
        
        if matricula_principal_obj:
            # Primeira linha da matrícula principal (com o primeiro proprietário)
            principal_id = self.tree_results.insert("", "end", text="🏠", values=(
                result.matricula_principal,
                lote_quadra_principal,
                "Principal",
                proprietarios_principal[0],
                estado_ms,
                confianca
            ))
            
            # Linhas adicionais para outros proprietários da matrícula principal
            for i, proprietario in enumerate(proprietarios_principal[1:], 1):
                self.tree_results.insert(principal_id, "end", text="", values=(
                    "",  # Matrícula vazia nas linhas de proprietários adicionais
                    "",  # Lote/Quadra vazio
                    "",  # Tipo vazio
                    proprietario,
                    "",  # Estado MS só na primeira linha
                    ""   # Confiança só na primeira linha
                ))
        else:
            # Se não há matrícula principal identificada, mostra informação geral
            principal_id = self.tree_results.insert("", "end", text="📄", values=(
                result.matricula_principal or "Não identificada",
                "",
                "Documento",
                f"{len(result.matriculas_encontradas)} matrícula(s) encontrada(s)",
                estado_ms,
                confianca
            ))
        
        # Insere matrículas confrontantes como filhas
        for mat_num in result.matriculas_confrontantes:
            # Encontra dados da matrícula confrontante
            confrontante_obj = None
            for mat in result.matriculas_encontradas:
                if mat.numero == mat_num:
                    confrontante_obj = mat
                    break
            
            proprietarios_confrontante = confrontante_obj.proprietarios if confrontante_obj else ["N/A"]
            if not proprietarios_confrontante:
                proprietarios_confrontante = ["N/A"]
            
            # Formata informação de lote/quadra da confrontante
            lote_quadra_confrontante = ""
            if confrontante_obj and (confrontante_obj.lote or confrontante_obj.quadra):
                lote_parts = []
                if confrontante_obj.lote:
                    lote_parts.append(f"Lote {confrontante_obj.lote}")
                if confrontante_obj.quadra:
                    lote_parts.append(f"Quadra {confrontante_obj.quadra}")
                lote_quadra_confrontante = " / ".join(lote_parts)
            
            # Primeira linha da matrícula confrontante
            conf_id = self.tree_results.insert(principal_id, "end", text="  ↳", values=(
                mat_num,
                lote_quadra_confrontante,
                "Confrontante",
                proprietarios_confrontante[0],
                "",  # Estado MS só na principal
                ""   # Confiança só na principal
            ))
            
            # Linhas adicionais para outros proprietários da confrontante
            for proprietario in proprietarios_confrontante[1:]:
                self.tree_results.insert(conf_id, "end", text="", values=(
                    "",  # Matrícula vazia nas linhas de proprietários adicionais
                    "",  # Lote/Quadra vazio
                    "",  # Tipo vazio
                    proprietario,
                    "",  # Estado MS só na principal
                    ""   # Confiança só na principal
                ))

        # Insere matrículas NÃO confrontantes (se houver)
        for mat_num in result.matriculas_nao_confrontantes:
            # Encontra dados da matrícula não confrontante
            nao_confrontante_obj = None
            for mat in result.matriculas_encontradas:
                if mat.numero == mat_num:
                    nao_confrontante_obj = mat
                    break
            
            proprietarios_nao_confrontante = nao_confrontante_obj.proprietarios if nao_confrontante_obj else ["N/A"]
            if not proprietarios_nao_confrontante:
                proprietarios_nao_confrontante = ["N/A"]
            
            # Formata informação de lote/quadra
            lote_quadra_nao_confrontante = ""
            if nao_confrontante_obj and (nao_confrontante_obj.lote or nao_confrontante_obj.quadra):
                lote_parts = []
                if nao_confrontante_obj.lote:
                    lote_parts.append(f"Lote {nao_confrontante_obj.lote}")
                if nao_confrontante_obj.quadra:
                    lote_parts.append(f"Quadra {nao_confrontante_obj.quadra}")
                lote_quadra_nao_confrontante = " / ".join(lote_parts)
            
            # Primeira linha da matrícula não confrontante
            nao_conf_id = self.tree_results.insert(principal_id, "end", text="  ⚬", values=(
                mat_num,
                lote_quadra_nao_confrontante,
                "Não Confrontante",
                proprietarios_nao_confrontante[0],
                "",  # Estado MS só na principal
                ""   # Confiança só na principal
            ))
            
            # Linhas adicionais para outros proprietários
            for proprietario in proprietarios_nao_confrontante[1:]:
                self.tree_results.insert(nao_conf_id, "end", text="", values=(
                    "",  # Matrícula vazia
                    "",  # Lote/Quadra vazio
                    "",  # Tipo vazio
                    proprietario,
                    "",  # Estado MS só na principal
                    ""   # Confiança só na principal
                ))

        # Insere lotes confrontantes sem matrícula anexada
        for lote_sem_mat in result.lotes_sem_matricula:
            self.tree_results.insert(principal_id, "end", text="  ⚠", values=(
                "FALTANTE",
                lote_sem_mat,
                "Falta Matrícula",
                "Matrícula não anexada",
                "",  # Estado MS só na principal
                ""   # Confiança só na principal
            ))
        
        # Expande automaticamente a árvore
        self.tree_results.item(principal_id, open=True)
        for child in self.tree_results.get_children(principal_id):
            self.tree_results.item(child, open=True)
        
        # Aplica estilo à matrícula principal
        self.configure_tree_styles()

    def configure_tree_styles(self):
        """Configura estilos visuais para a tabela hierárquica"""
        # Configura tags para diferentes tipos de linha
        self.tree_results.tag_configure("principal", background="#E8F4FD", font=("TkDefaultFont", 9, "bold"))
        self.tree_results.tag_configure("confrontante", background="#F0F8F0")  # Verde claro
        self.tree_results.tag_configure("nao_confrontante", background="#FFF8F0")  # Laranja claro
        self.tree_results.tag_configure("faltante", background="#FFF0F0")  # Vermelho claro
        
        # Aplica tags aos itens
        for item in self.tree_results.get_children():
            # Item principal
            self.tree_results.item(item, tags=("principal",))
            # Itens filhos (confrontantes, não confrontantes, faltantes)
            for child in self.tree_results.get_children(item):
                child_values = self.tree_results.item(child, "values")
                if len(child_values) > 2:
                    tipo = child_values[2]  # coluna "Tipo"
                    if tipo == "Confrontante":
                        self.tree_results.item(child, tags=("confrontante",))
                    elif tipo == "Não Confrontante":
                        self.tree_results.item(child, tags=("nao_confrontante",))
                    elif tipo == "Falta Matrícula":
                        self.tree_results.item(child, tags=("faltante",))
                    else:
                        self.tree_results.item(child, tags=("confrontante",))  # padrão

    def update_summary(self, result):
        """Atualiza o campo de resumo com o reasoning do modelo"""
        if not result:
            self.set_summary_text("Nenhuma análise disponível.")
            return
        
        # Usa o reasoning do modelo se disponível
        if result.reasoning and result.reasoning.strip():
            # Adiciona informações básicas + reasoning do modelo
            confianca = int(result.confidence * 100) if result.confidence is not None and result.confidence <= 1 else int(result.confidence) if result.confidence is not None else 0
            
            resumo_header = f"ANÁLISE PERICIAL (Confiança: {confianca}%)\n\n"
            reasoning_texto = result.reasoning.strip()
            
            # Formata o reasoning para melhor legibilidade
            if reasoning_texto and not reasoning_texto.startswith("📋"):
                reasoning_texto = f"📋 {reasoning_texto}"
            
            resumo = resumo_header + reasoning_texto
            self.set_summary_text(resumo)
        else:
            # Fallback para resumo automático se não houver reasoning
            self._generate_fallback_summary(result)
    
    def _generate_fallback_summary(self, result):
        """Gera resumo automático caso não haja reasoning do modelo"""
        if not result.matricula_principal:
            self.set_summary_text("Dados insuficientes para análise.")
            return
        
        # Encontra dados da matrícula principal
        matricula_principal_obj = None
        for mat in result.matriculas_encontradas:
            if mat.numero == result.matricula_principal:
                matricula_principal_obj = mat
                break
        
        if not matricula_principal_obj:
            self.set_summary_text("Dados da matrícula principal não encontrados.")
            return
        
        # Monta o resumo automático
        proprietarios = " e ".join(matricula_principal_obj.proprietarios)
        
        confrontantes_str = ""
        if result.matriculas_confrontantes:
            if len(result.matriculas_confrontantes) <= 3:
                confrontantes_str = ", ".join(result.matriculas_confrontantes)
            else:
                confrontantes_str = ", ".join(result.matriculas_confrontantes[:3]) + f" e mais {len(result.matriculas_confrontantes) - 3}"
        else:
            confrontantes_str = "nenhuma matrícula confrontante identificada"
        
        confianca = int(result.confidence * 100) if result.confidence is not None and result.confidence <= 1 else int(result.confidence) if result.confidence is not None else 0
        
        resumo = (
            f"🎯 RESUMO AUTOMÁTICO (Confiança: {confianca}%)\n\n"
            f"A matrícula nº {result.matricula_principal}, registrada em nome de {proprietarios}, "
            f"possui como confrontantes as matrículas {confrontantes_str}. "
            f"O resultado da análise apresentou índice de confiança de {confianca}%."
        )
        
        self.set_summary_text(resumo)

    def set_summary_text(self, text):
        """Atualiza o texto do campo de resumo"""
        self.txt_resumo.config(state=tk.NORMAL)
        self.txt_resumo.delete("1.0", tk.END)
        self.txt_resumo.insert("1.0", text)
        self.txt_resumo.config(state=tk.DISABLED)

    def show_model_info(self):
        """Mostra informações sobre modelos com suporte a visão"""
        info = (
            "MODELOS RECOMENDADOS COM VISÃO:\n\n"
            "• google/gemini-2.5-pro (Recomendado)\n"
            "• anthropic/claude-opus-4\n"
            "• openai/gpt-5\n"
        )
        messagebox.showinfo("Modelos com Suporte a Visão", info)
    
    def diagnose_file_issues(self, file_path: str) -> str:
        """Diagnostica problemas comuns com arquivos"""
        issues = []
        
        try:
            # Verifica se arquivo existe
            if not os.path.exists(file_path):
                issues.append("❌ Arquivo não encontrado")
                return "; ".join(issues)
            
            # Verifica tamanho do arquivo (apenas informativo)
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if file_size_mb > 100:  # Aumentou limite
                issues.append(f"ℹ️ Arquivo grande ({file_size_mb:.1f}MB) - processamento pode demorar")
            
            # Verifica extensão
            ext = os.path.splitext(file_path.lower())[1]
            if ext == ".pdf":
                # Verifica número de páginas
                try:
                    page_count = get_pdf_page_count(file_path)
                    if page_count > 200:  # Limite muito alto, apenas informativo
                        issues.append(f"ℹ️ PDF com {page_count} páginas - processamento pode demorar")
                    elif page_count == 0:
                        issues.append("❌ PDF corrompido ou vazio")
                except:
                    issues.append("❌ Erro ao ler PDF")
            elif ext not in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]:
                issues.append(f"❌ Formato não suportado: {ext}")
            
            if not issues:
                issues.append("✅ Arquivo parece estar OK")
                
        except Exception as e:
            issues.append(f"❌ Erro ao analisar arquivo: {str(e)[:50]}")
        
        return "; ".join(issues)

    def check_estado_ms_rights(self, analysis_result: AnalysisResult) -> Optional[str]:
        """Verifica se o Estado de MS tem direitos registrados nas matrículas"""
        direitos_encontrados = []
        
        # Verifica em todas as matrículas
        for matricula in analysis_result.matriculas_encontradas:
            # Verifica se Estado de MS é proprietário
            for proprietario in matricula.proprietarios:
                if any(palavra in proprietario.lower() for palavra in 
                      ['estado de mato grosso do sul', 'estado de ms', 'estado do ms', 
                       'fazenda pública', 'governo do estado']):
                    direitos_encontrados.append(f"Matrícula {matricula.numero}: Proprietário")
            
            # Verifica restrições onde Estado de MS é credor
            for restricao in matricula.restricoes:
                if restricao.credor and any(palavra in restricao.credor.lower() for palavra in 
                                          ['estado de mato grosso do sul', 'estado de ms', 'estado do ms', 
                                           'fazenda pública', 'governo do estado']):
                    direitos_encontrados.append(
                        f"Matrícula {matricula.numero}: {restricao.tipo.upper()} "
                        f"({restricao.situacao})"
                    )
        
        # Verifica resumo da análise
        if analysis_result.resumo_analise:
            # Verifica estrutura específica de direitos do Estado de MS
            if analysis_result.resumo_analise.estado_ms_direitos.tem_direitos:
                for detalhe in analysis_result.resumo_analise.estado_ms_direitos.detalhes:
                    direitos_encontrados.append(
                        f"⚠️ {detalhe.get('tipo_direito', 'Direito').upper()} "
                        f"(Status: {detalhe.get('status', 'N/A')})"
                    )
            
            # Verifica também nas restrições gerais
            for restricao in analysis_result.resumo_analise.restricoes_vigentes:
                if restricao.get('credor') and any(palavra in restricao['credor'].lower() for palavra in 
                                                 ['estado de mato grosso do sul', 'estado de ms', 'estado do ms', 
                                                  'fazenda pública', 'governo do estado']):
                    direitos_encontrados.append(
                        f"VIGENTE: {restricao.get('tipo', 'Restrição').upper()}"
                    )
        
        if direitos_encontrados:
            return " | ".join(direitos_encontrados)
        return None

    def update_estado_alert(self):
        """Atualiza o alerta sobre direitos do Estado de MS"""
        direitos_estado = []
        
        # Verifica todos os resultados analisados
        for file_path, result in self.results.items():
            direitos = self.check_estado_ms_rights(result)
            if direitos:
                filename = os.path.basename(file_path)
                direitos_estado.append(f"{filename}: {direitos}")
        
        if direitos_estado:
            alert_text = "ATENÇÃO: Estado de MS tem direitos registrados!\n" + "\n".join(direitos_estado)
            self.estado_alert_var.set(alert_text)
            self.estado_alert_label.pack(fill="x", pady=(0,5))
            # Piscar o alerta para chamar atenção
            self.blink_alert()
        else:
            self.estado_alert_label.pack_forget()

    def blink_alert(self):
        """Faz o alerta piscar para chamar atenção"""
        current_bg = self.estado_alert_label.cget("background")
        if current_bg == "yellow":
            self.estado_alert_label.configure(background="red", foreground="white")
            self.after(500, lambda: self.estado_alert_label.configure(background="yellow", foreground="red"))
        
        # Repete o piscar 3 vezes
        self.after(1000, self.blink_alert_cycle)

    def blink_alert_cycle(self):
        """Controla o ciclo de piscar do alerta"""
        if not hasattr(self, '_blink_count'):
            self._blink_count = 0
        
        if self._blink_count < 3:
            self.blink_alert()
            self._blink_count += 1
        else:
            self._blink_count = 0

    def generate_property_plant(self):
        """Gera planta do imóvel com base nos dados geométricos extraídos"""
        if not self.results:
            messagebox.showwarning("Nenhum resultado", "Processe pelo menos um arquivo antes de gerar a planta.")
            return
        
        # Encontra a matrícula principal
        matricula_principal = None
        for file_path, result in self.results.items():
            if result.matricula_principal:
                for matricula in result.matriculas_encontradas:
                    if matricula.numero == result.matricula_principal:
                        matricula_principal = matricula
                        break
                if matricula_principal:
                    break
        
        if not matricula_principal:
            messagebox.showwarning("Matrícula não encontrada", "Não foi possível identificar a matrícula principal.")
            return
        
        # Verifica se há algum dado geométrico, mas prossegue mesmo com dados parciais
        dados_geom = matricula_principal.dados_geometricos
        if not dados_geom:
            print("⚠️ Nenhum dado geométrico encontrado, gerando planta conceitual...")
        elif not dados_geom.medidas:
            print("⚠️ Medidas específicas não encontradas, usando dados disponíveis...")
        
        # Gera a planta
        self._generate_plant_image(matricula_principal)

    def _generate_plant_image(self, matricula: MatriculaInfo):
        """Gera a imagem da planta usando matplotlib"""
        try:
            # Mostra janela de progresso
            progress_window = tk.Toplevel(self)
            progress_window.title("Gerando Planta do Imóvel")
            progress_window.geometry("400x150")
            progress_window.transient(self)
            progress_window.grab_set()
            
            ttk.Label(progress_window, text="🏗️ Gerando planta do imóvel...").pack(pady=20)
            progress_bar = ttk.Progressbar(progress_window, mode="indeterminate")
            progress_bar.pack(pady=10, padx=20, fill="x")
            progress_bar.start()
            
            def generate_in_thread():
                try:
                    # Gera a imagem usando matplotlib
                    image_url = self._generate_plant_with_matplotlib(matricula)
                    
                    if image_url:
                        # Cria prompt informativo para exibir na janela de resultado
                        plant_prompt = self._create_info_text(matricula)
                        progress_window.after(0, lambda: self._show_generated_image(image_url, plant_prompt, progress_window))
                    else:
                        progress_window.after(0, lambda: self._show_plant_error("Não foi possível gerar a planta", progress_window))
                    
                except Exception as e:
                    progress_window.after(0, lambda: self._show_plant_error(str(e), progress_window))
            
            # Executa em thread separada
            thread = threading.Thread(target=generate_in_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao gerar planta: {e}")
    
    def _create_info_text(self, matricula: MatriculaInfo) -> str:
        """Cria texto informativo sobre a planta gerada"""
        info = f"""PLANTA TÉCNICA GERADA COM MATPLOTLIB

🏠 INFORMAÇÕES DO IMÓVEL:
- Matrícula: {matricula.numero or 'N/A'}
- Lote: {matricula.lote or 'N/A'}
- Quadra: {matricula.quadra or 'N/A'}

👥 PROPRIETÁRIO(S):"""
        
        for prop in matricula.proprietarios:
            info += f"\n- {prop}"
            
        if matricula.dados_geometricos:
            dados = matricula.dados_geometricos
            info += f"\n\n📐 DADOS GEOMÉTRICOS:"
            if dados.area_total:
                info += f"\n- Área Total: {dados.area_total}"
            if dados.formato:
                info += f"\n- Formato: {dados.formato}"
            if dados.medidas:
                info += f"\n- Medidas: {dados.medidas}"
                
        info += f"\n\n✅ Planta gerada usando matplotlib - precisão técnica garantida!"
        return info

    def _create_plant_prompt(self, matricula: MatriculaInfo) -> str:
        """Cria prompt estruturado para geração da planta, adaptando-se aos dados disponíveis"""
        dados = matricula.dados_geometricos
        
        prompt = f"""Crie uma planta baixa técnica e profissional do seguinte imóvel:

🏠 INFORMAÇÕES DO IMÓVEL:
- Matrícula: {matricula.numero or 'N/A'}
- Lote: {matricula.lote or 'N/A'}
- Quadra: {matricula.quadra or 'N/A'}"""

        # Adiciona formato se disponível
        if dados and dados.formato:
            prompt += f"\n- Formato: {dados.formato}"
        else:
            prompt += f"\n- Formato: Retangular (padrão)"

        prompt += "\n\n📏 MEDIDAS DISPONÍVEIS (em metros):"
        
        # Adiciona medidas se disponíveis
        medidas_encontradas = False
        if dados and dados.medidas:
            for direcao, medida in dados.medidas.items():
                if medida:  # Só adiciona se a medida não for vazia
                    prompt += f"\n- {direcao.title()}: {medida}m"
                    medidas_encontradas = True
        
        if not medidas_encontradas:
            prompt += "\n- Medidas específicas não informadas"
            # Tenta extrair informações da descrição da matrícula
            if matricula.descricao:
                prompt += f"\n- DESCRIÇÃO DISPONÍVEL: {matricula.descricao[:200]}..."
                prompt += "\n- (Extrair dimensões aproximadas da descrição acima)"
        
        prompt += "\n\n🧭 CONFRONTAÇÕES IDENTIFICADAS:"
        confrontacoes_encontradas = False
        
        # Tenta usar dados geométricos primeiro
        if dados and dados.confrontantes:
            for direcao, confrontante in dados.confrontantes.items():
                if confrontante:
                    prompt += f"\n- {direcao.title()}: {confrontante}"
                    confrontacoes_encontradas = True
        
        # Se não há confrontações nos dados geométricos, usa as confrontações gerais da matrícula
        if not confrontacoes_encontradas and matricula.confrontantes:
            for i, confrontante in enumerate(matricula.confrontantes):
                if confrontante:
                    prompt += f"\n- Lado {i+1}: {confrontante}"
                    confrontacoes_encontradas = True
        
        if not confrontacoes_encontradas:
            prompt += "\n- Confrontações não especificadas (usar confrontantes genéricos)"
        
        # Adiciona área se disponível
        if dados and dados.area_total:
            prompt += f"\n\n📊 ÁREA TOTAL: {dados.area_total} m²"
        else:
            prompt += f"\n\n📊 ÁREA TOTAL: A ser calculada pelas dimensões estimadas"
        
        prompt += "\n\n📐 ÂNGULOS:"
        if dados and dados.angulos:
            for direcao, angulo in dados.angulos.items():
                if angulo:
                    prompt += f"\n- {direcao.title()}: {angulo}°"
        else:
            prompt += "\n- Todos os ângulos: 90° (terreno retangular padrão)"
        
        prompt += f"""

🎯 REQUISITOS TÉCNICOS:
✅ Vista superior (planta baixa)
✅ Escala gráfica visível (mesmo que aproximada)
✅ Cotas com medidas disponíveis ou estimadas
✅ Rosa dos ventos indicando orientação
✅ Legenda identificando confrontantes conhecidos
✅ Área total (exata ou estimada)
✅ Estilo técnico profissional
✅ Linhas precisas e limpas
✅ Texto legível em fonte técnica

📝 ADAPTAÇÕES QUANDO DADOS INCOMPLETOS:
✅ Use dimensões proporcionais razoáveis
✅ Indique medidas como "aprox." quando estimadas
✅ Crie confrontações genéricas se necessário
✅ Mantenha aparência profissional mesmo com dados parciais

🚫 NÃO INCLUIR:
❌ Construções internas
❌ Móveis ou decoração
❌ Vegetação detalhada
❌ Cores excessivas

RESULTADO: Planta baixa técnica do terreno usando todos os dados disponíveis, complementando informações em falta com estimativas razoáveis e profissionais."""
        
        return prompt

    def _generate_plant_with_matplotlib(self, matricula: MatriculaInfo) -> Optional[str]:
        """Gera planta técnica usando matplotlib baseada nos dados geométricos"""
        try:
            print(f"🎨 Gerando planta técnica com matplotlib...")
            
            # Configura matplotlib para não mostrar em GUI separada
            plt.switch_backend('Agg')
            
            # Cria figura com tamanho A4 landscape
            fig, ax = plt.subplots(figsize=(11.7, 8.3), dpi=150)
            ax.set_aspect('equal')
            
            # Extrai dados geométricos
            dados_geom = matricula.dados_geometricos
            medidas = dados_geom.medidas if dados_geom.medidas else {}
            confrontantes = dados_geom.confrontantes if dados_geom.confrontantes else {}
            
            # Define coordenadas do terreno baseado nas medidas
            coords = self._calculate_plot_coordinates(medidas, dados_geom.formato)
            
            if coords:
                # Desenha o terreno
                terreno = Polygon(coords, fill=False, edgecolor='black', linewidth=2)
                ax.add_patch(terreno)
                
                # Adiciona medidas e confrontantes
                self._add_measurements_and_labels(ax, coords, medidas, confrontantes)
                
                # Calcula limites e adiciona margem
                x_coords = [p[0] for p in coords]
                y_coords = [p[1] for p in coords]
                margin = max(max(x_coords) - min(x_coords), max(y_coords) - min(y_coords)) * 0.2
                
                ax.set_xlim(min(x_coords) - margin, max(x_coords) + margin)
                ax.set_ylim(min(y_coords) - margin, max(y_coords) + margin)
            else:
                # Fallback: desenha terreno genérico baseado na descrição
                self._draw_generic_plot(ax, matricula)
            
            # Configura estilo técnico
            ax.grid(True, alpha=0.3, linestyle='-', linewidth=0.5)
            ax.set_title(f'PLANTA DO IMÓVEL - LOTE {matricula.lote}, QUADRA {matricula.quadra}\n'
                        f'MATRÍCULA Nº {matricula.numero}', 
                        fontsize=14, fontweight='bold', pad=20)
            
            # Remove ticks mas mantém grid
            ax.set_xticks([])
            ax.set_yticks([])
            
            # Adiciona legenda e informações
            self._add_plant_legend(ax, matricula)
            
            # Salva em buffer de memória
            img_buffer = io.BytesIO()
            plt.savefig(img_buffer, format='png', bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            img_buffer.seek(0)
            
            # Converte para base64
            import base64
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            data_url = f"data:image/png;base64,{img_base64}"
            
            plt.close(fig)  # Limpa a figura da memória
            print(f"✅ Planta gerada com sucesso usando matplotlib")
            
            return data_url
            
        except Exception as e:
            print(f"❌ Erro ao gerar planta com matplotlib: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_plot_coordinates(self, medidas: Dict, formato: str) -> List[Tuple[float, float]]:
        """Calcula coordenadas do terreno baseado nas medidas"""
        try:
            if not medidas:
                return None
                
            # Extrai medidas principais
            frente = self._extract_number(medidas.get('frente', ''))
            fundos = self._extract_number(medidas.get('fundos', ''))
            lado_direito = self._extract_number(medidas.get('lado_direito', ''))
            lado_esquerdo = self._extract_number(medidas.get('lado_esquerdo', ''))
            
            if not any([frente, fundos, lado_direito, lado_esquerdo]):
                return None
            
            # Define valores padrão baseados nos dados disponíveis
            if formato.lower() == 'retangular' or not formato:
                # Terreno retangular
                width = frente or fundos or 20  # Usa frente, fundos ou valor padrão
                height = lado_direito or lado_esquerdo or 30  # Usa um dos lados ou valor padrão
                
                return [
                    (0, 0),           # Canto inferior esquerdo
                    (width, 0),       # Canto inferior direito
                    (width, height),  # Canto superior direito
                    (0, height)       # Canto superior esquerdo
                ]
            else:
                # Para formatos não retangulares, tenta usar todas as medidas
                coords = []
                if frente:
                    coords.extend([(0, 0), (frente, 0)])
                if lado_direito and frente:
                    coords.append((frente, lado_direito))
                if fundos and lado_direito:
                    coords.append((frente - fundos if fundos <= frente else 0, lado_direito))
                if lado_esquerdo:
                    coords.append((0, lado_direito - lado_esquerdo if lado_esquerdo <= lado_direito else 0))
                    
                return coords if len(coords) >= 3 else self._calculate_plot_coordinates(medidas, 'retangular')
                
        except Exception as e:
            print(f"❌ Erro ao calcular coordenadas: {e}")
            return None

    def _extract_number(self, text: str) -> Optional[float]:
        """Extrai número de uma string (ex: '20,00 metros' -> 20.0)"""
        if not text:
            return None
        
        import re
        # Procura por padrões numéricos
        matches = re.findall(r'(\d+(?:[,\.]\d+)?)', str(text))
        if matches:
            # Converte vírgula para ponto
            number_str = matches[0].replace(',', '.')
            try:
                return float(number_str)
            except ValueError:
                return None
        return None

    def _add_measurements_and_labels(self, ax, coords: List[Tuple[float, float]], 
                                   medidas: Dict, confrontantes: Dict):
        """Adiciona medidas e rótulos de confrontantes na planta"""
        try:
            n_coords = len(coords)
            if n_coords < 3:
                return
                
            sides = ['frente', 'lado_direito', 'fundos', 'lado_esquerdo']
            confronts = ['frente', 'direita', 'fundos', 'esquerda']
            
            for i in range(n_coords):
                p1 = coords[i]
                p2 = coords[(i + 1) % n_coords]
                
                # Calcula ponto médio da linha
                mid_x = (p1[0] + p2[0]) / 2
                mid_y = (p1[1] + p2[1]) / 2
                
                # Determina o lado baseado na posição
                side_idx = i % len(sides)
                side_name = sides[side_idx]
                confront_name = confronts[side_idx]
                
                # Adiciona medida
                if side_name in medidas and medidas[side_name]:
                    measure_text = str(medidas[side_name])
                    # Ajusta posição do texto baseado na orientação da linha
                    if abs(p2[0] - p1[0]) > abs(p2[1] - p1[1]):  # Linha horizontal
                        ax.text(mid_x, mid_y - 2, measure_text, ha='center', va='top', 
                               fontsize=10, fontweight='bold', color='blue')
                    else:  # Linha vertical
                        ax.text(mid_x - 2, mid_y, measure_text, ha='right', va='center',
                               fontsize=10, fontweight='bold', color='blue', rotation=90)
                
                # Adiciona confrontante
                confront_text = confrontantes.get(confront_name, '')
                if confront_text:
                    # Posiciona o texto de confrontante um pouco mais afastado
                    offset = 5
                    if abs(p2[0] - p1[0]) > abs(p2[1] - p1[1]):  # Linha horizontal
                        ax.text(mid_x, mid_y + offset, confront_text, ha='center', va='bottom',
                               fontsize=8, style='italic', color='green')
                    else:  # Linha vertical
                        ax.text(mid_x + offset, mid_y, confront_text, ha='left', va='center',
                               fontsize=8, style='italic', color='green', rotation=90)
                        
        except Exception as e:
            print(f"❌ Erro ao adicionar medidas: {e}")

    def _draw_generic_plot(self, ax, matricula: MatriculaInfo):
        """Desenha terreno genérico quando não há dados geométricos suficientes"""
        try:
            # Desenha retângulo padrão 20x30
            coords = [(0, 0), (20, 0), (20, 30), (0, 30)]
            terreno = Polygon(coords, fill=False, edgecolor='black', linewidth=2)
            ax.add_patch(terreno)
            
            # Adiciona texto indicativo
            ax.text(10, 15, 'TERRENO\n(Medidas aproximadas)', ha='center', va='center',
                   fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.7))
            
            # Define limites
            ax.set_xlim(-5, 25)
            ax.set_ylim(-5, 35)
            
            print("🏗️ Planta genérica gerada (dados geométricos insuficientes)")
            
        except Exception as e:
            print(f"❌ Erro ao desenhar planta genérica: {e}")

    def _add_plant_legend(self, ax, matricula: MatriculaInfo):
        """Adiciona legenda e informações na planta"""
        try:
            # Adiciona caixa de informações no canto
            info_text = f"PROPRIETÁRIO(S):\n"
            for prop in matricula.proprietarios[:3]:  # Máximo 3 para não poluir
                info_text += f"• {prop}\n"
            if len(matricula.proprietarios) > 3:
                info_text += f"• ... e mais {len(matricula.proprietarios) - 3}\n"
                
            if matricula.dados_geometricos and matricula.dados_geometricos.area_total:
                info_text += f"\nÁREA TOTAL: {matricula.dados_geometricos.area_total}"
            
            # Posiciona a legenda no canto superior direito
            ax.text(0.98, 0.98, info_text, transform=ax.transAxes, fontsize=9,
                   verticalalignment='top', horizontalalignment='right',
                   bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.8))
            
            # Adiciona rosa dos ventos simples
            self._add_compass_rose(ax)
            
        except Exception as e:
            print(f"❌ Erro ao adicionar legenda: {e}")

    def _add_compass_rose(self, ax):
        """Adiciona rosa dos ventos simples"""
        try:
            # Posiciona no canto inferior direito
            compass_x = 0.9
            compass_y = 0.1
            
            # Desenha setas dos pontos cardeais
            arrow_props = dict(arrowstyle='->', lw=1.5, color='red')
            
            # Norte (para cima)
            ax.annotate('N', xy=(compass_x, compass_y + 0.05), xytext=(compass_x, compass_y),
                       transform=ax.transAxes, ha='center', va='bottom',
                       arrowprops=arrow_props, fontweight='bold', color='red')
            
            # Leste (para direita)  
            ax.annotate('L', xy=(compass_x + 0.03, compass_y), xytext=(compass_x, compass_y),
                       transform=ax.transAxes, ha='left', va='center',
                       arrowprops=arrow_props, fontweight='bold', color='red')
            
        except Exception as e:
            print(f"❌ Erro ao adicionar rosa dos ventos: {e}")

    def _show_generated_image(self, image_url: str, prompt: str, progress_window: tk.Toplevel):
        """Mostra a imagem gerada"""
        progress_window.destroy()
        
        # Cria janela para mostrar a imagem
        result_window = tk.Toplevel(self)
        result_window.title("🏗️ Planta Gerada")
        result_window.geometry("900x700")
        result_window.transient(self)
        
        # Frame principal
        main_frame = ttk.Frame(result_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Título
        ttk.Label(main_frame, text="🏗️ Planta do Imóvel Gerada", 
                 font=("Arial", 14, "bold")).pack(pady=(0,10))
        
        # Área da imagem
        image_frame = ttk.Frame(main_frame, relief="solid", borderwidth=1)
        image_frame.pack(fill="both", expand=True, pady=(0,10))
        
        try:
            print(f"🖼️ Tentando exibir imagem...")
            # Carrega e exibe a imagem real
            image_data = self._download_image(image_url)
            if image_data:
                print(f"✅ Dados da imagem carregados: {len(image_data)} bytes")
                from PIL import Image as PILImage
                import io
                
                # Abre a imagem com PIL
                pil_image = PILImage.open(io.BytesIO(image_data))
                print(f"✅ Imagem aberta com PIL: {pil_image.size}")
                
                # Redimensiona para caber na janela (mantém proporção)
                max_size = (800, 500)
                pil_image.thumbnail(max_size, PILImage.Resampling.LANCZOS)
                print(f"✅ Imagem redimensionada para: {pil_image.size}")
                
                # Converte para formato Tkinter PhotoImage
                from PIL import ImageTk
                photo = ImageTk.PhotoImage(pil_image)
                
                # Exibe a imagem
                image_label = ttk.Label(image_frame, image=photo)
                image_label.image = photo  # Mantém referência
                image_label.pack(expand=True, padx=10, pady=10)
                
                # Armazena dados da imagem para salvar
                self._current_image_data = image_data
                self._current_image_url = image_url
                print(f"✅ Imagem exibida com sucesso na interface")
            else:
                print(f"❌ Falha ao carregar dados da imagem")
                error_text = f"""❌ Não foi possível carregar a imagem

Possíveis causas:
• URL da imagem inválida ou expirada
• Problema de conexão com o servidor
• Formato de imagem não suportado

URL recebida: {image_url[:100]}..."""
                ttk.Label(image_frame, text=error_text, justify="center").pack(expand=True)
            
        except Exception as e:
            print(f"❌ Erro ao exibir imagem: {e}")
            import traceback
            traceback.print_exc()
            error_text = f"""❌ Erro ao carregar imagem

Detalhes do erro: {str(e)}

URL: {image_url if isinstance(image_url, str) else 'N/A'}"""
            ttk.Label(image_frame, text=error_text, justify="center").pack(expand=True)
        
        # Botões
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        ttk.Button(button_frame, text="💾 Salvar Imagem", 
                  command=lambda: self._save_image(image_url)).pack(side="left")
        
        ttk.Button(button_frame, text="📋 Ver Prompt", 
                  command=lambda: self._show_prompt_window(prompt)).pack(side="left", padx=(10,0))
        
        ttk.Button(button_frame, text="Fechar", 
                  command=result_window.destroy).pack(side="right")

    def _download_image(self, image_content: str) -> Optional[bytes]:
        """Baixa ou converte a imagem dependendo do formato"""
        try:
            print(f"🔍 Processando conteúdo da imagem: {image_content[:100]}...")
            
            if image_content.startswith("data:image"):
                # Imagem em base64
                print("📎 Decodificando imagem base64...")
                import base64
                header, data = image_content.split(",", 1)
                return base64.b64decode(data)
            elif image_content.startswith("http"):
                # Imagem via URL
                print(f"🌐 Baixando imagem da URL: {image_content}")
                response = requests.get(image_content, timeout=30)
                print(f"📡 Status do download: {response.status_code}")
                if response.status_code == 200:
                    print(f"✅ Imagem baixada: {len(response.content)} bytes")
                    return response.content
                else:
                    print(f"❌ Erro no download: {response.text}")
            else:
                # Verifica se é base64 puro (sem header data:image)
                import base64
                import re
                
                # Remove quebras de linha e espaços
                clean_content = re.sub(r'\s+', '', image_content)
                
                # Verifica se parece ser base64
                if re.match(r'^[A-Za-z0-9+/]*={0,2}$', clean_content) and len(clean_content) > 100:
                    print("📎 Tentando decodificar como base64 puro...")
                    try:
                        decoded = base64.b64decode(clean_content)
                        # Verifica se os primeiros bytes parecem ser de imagem
                        if decoded.startswith(b'\x89PNG') or decoded.startswith(b'\xff\xd8\xff') or decoded.startswith(b'GIF'):
                            print("✅ Base64 puro decodificado com sucesso")
                            return decoded
                    except Exception as decode_error:
                        print(f"❌ Erro ao decodificar base64: {decode_error}")
                
                print(f"❌ Formato de conteúdo não reconhecido: {type(image_content)}")
                print(f"📝 Primeiros 200 chars: {image_content[:200]}")
            return None
        except Exception as e:
            print(f"❌ Erro ao baixar imagem: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _save_image(self, image_url: str):
        """Salva a imagem gerada"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg"), ("All files", "*.*")],
                title="Salvar Planta Gerada"
            )
            if filename:
                if hasattr(self, '_current_image_data') and self._current_image_data:
                    with open(filename, 'wb') as f:
                        f.write(self._current_image_data)
                    messagebox.showinfo("Sucesso", f"Imagem salva em: {filename}")
                else:
                    # Tenta baixar novamente
                    image_data = self._download_image(image_url)
                    if image_data:
                        with open(filename, 'wb') as f:
                            f.write(image_data)
                        messagebox.showinfo("Sucesso", f"Imagem salva em: {filename}")
                    else:
                        messagebox.showerror("Erro", "Não foi possível baixar a imagem")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar imagem: {e}")

    def _show_prompt_window(self, prompt: str):
        """Mostra o prompt usado para gerar a imagem"""
        prompt_window = tk.Toplevel(self)
        prompt_window.title("📋 Prompt Utilizado")
        prompt_window.geometry("600x400")
        prompt_window.transient(self)
        
        text_widget = tk.Text(prompt_window, wrap="word", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(prompt_window, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)
        
        text_widget.insert("1.0", prompt)
        text_widget.configure(state="disabled")

    def _show_plant_result(self, prompt: str, progress_window: tk.Toplevel):
        """Mostra o resultado da geração da planta"""
        progress_window.destroy()
        
        # Cria janela para mostrar o prompt gerado (por enquanto)
        result_window = tk.Toplevel(self)
        result_window.title("Prompt para Geração de Planta")
        result_window.geometry("800x600")
        result_window.transient(self)
        
        # Frame principal
        main_frame = ttk.Frame(result_window)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Título
        ttk.Label(main_frame, text="📐 Prompt para Geração de Planta do Imóvel", 
                 font=("Arial", 14, "bold")).pack(pady=(0,10))
        
        # Texto do prompt
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill="both", expand=True)
        
        text_widget = tk.Text(text_frame, wrap="word", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        text_widget.insert("1.0", prompt)
        text_widget.configure(state="disabled")
        
        # Botões
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(10,0))
        
        ttk.Button(button_frame, text="📋 Copiar Prompt", 
                  command=lambda: self._copy_to_clipboard(prompt)).pack(side="left")
        
        ttk.Button(button_frame, text="💾 Salvar como TXT", 
                  command=lambda: self._save_prompt_to_file(prompt)).pack(side="left", padx=(10,0))
        
        ttk.Button(button_frame, text="Fechar", 
                  command=result_window.destroy).pack(side="right")
        
        # Instruções
        instructions = """
💡 INSTRUÇÕES:
1. Copie este prompt e use em APIs de geração de imagem como:
   • DALL-E 3 (OpenAI)
   • Midjourney
   • Stable Diffusion
   • Leonardo AI

2. Para melhores resultados, adicione:
   • "architectural drawing"
   • "technical blueprint"
   • "professional land survey"
"""
        
        ttk.Label(main_frame, text=instructions, justify="left", 
                 font=("Arial", 9), foreground="gray").pack(pady=(10,0))

    def _show_plant_error(self, error: str, progress_window: tk.Toplevel):
        """Mostra erro na geração da planta"""
        progress_window.destroy()
        messagebox.showerror("Erro na Geração", f"Erro ao gerar planta: {error}")

    def _copy_to_clipboard(self, text: str):
        """Copia texto para a área de transferência"""
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        messagebox.showinfo("Copiado", "Prompt copiado para a área de transferência!")

    def _save_prompt_to_file(self, prompt: str):
        """Salva o prompt em arquivo de texto"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Salvar Prompt da Planta"
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(prompt)
                messagebox.showinfo("Salvo", f"Prompt salvo em: {filename}")
            except Exception as e:
                messagebox.showerror("Erro", f"Erro ao salvar arquivo: {e}")

    def log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

# =========================
# Main
# =========================
if __name__ == "__main__":
    app = App()
    app.mainloop()
