import os
import sys
import io
import json
import time
import queue
import threading
import tempfile
import subprocess
import base64
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple, Union

# --- OCR & PDF ---
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

try:
    import ocrmypdf  # opcional, mas recomendado
    OCRMYPDF_AVAILABLE = True
except Exception:
    OCRMYPDF_AVAILABLE = False

try:
    from pdf2image import convert_from_path  # fallback se precisar rasterizar PDF
    PDF2IMAGE_AVAILABLE = True
except Exception:
    PDF2IMAGE_AVAILABLE = False

try:
    import easyocr  # OCR alternativo mais rápido
    EASYOCR_AVAILABLE = True
    # Inicializa EasyOCR uma vez só (para evitar recarregar modelo a cada uso)
    easyocr_reader = None
except Exception:
    EASYOCR_AVAILABLE = False
    easyocr_reader = None

# --- HTTP & env ---
import requests
from dotenv import load_dotenv

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
class MatriculaInfo:
    numero: str
    proprietarios: List[str]
    descricao: str
    confrontantes: List[str]
    evidence: List[str]
    lote: Optional[str] = None  # número do lote
    quadra: Optional[str] = None  # número da quadra

@dataclass
class LoteConfronta:
    """Informações sobre um lote confrontante"""
    identificador: str  # "lote 10", "matrícula 1234", etc.
    tipo: str  # "lote", "matrícula", "pessoa", "via_publica", "estado", "outros"
    matricula_anexada: Optional[str] = None  # número da matrícula se foi anexada
    direcao: Optional[str] = None  # norte, sul, leste, oeste, etc.
    
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
    confidence: Optional[float]
    reasoning: str
    raw_json: Dict
    
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
    
    @property
    def confrontantes(self) -> List[str]:
        """Compatibilidade: retorna todos confrontantes encontrados"""
        all_confrontantes = []
        for matricula in self.matriculas_encontradas:
            all_confrontantes.extend(matricula.confrontantes)
        return list(set(all_confrontantes))  # remove duplicatas
    
    @property
    def evidence(self) -> List[str]:
        """Compatibilidade: retorna todas evidências"""
        all_evidence = []
        for matricula in self.matriculas_encontradas:
            all_evidence.extend(matricula.evidence)
        return all_evidence

# =========================
# Utilidades de OCR / Texto
# =========================
def run_ocrmypdf(input_pdf: str, output_pdf: str) -> bool:
    """
    Tenta rodar o OCR com o ocrmypdf. Retorna True se conseguiu.
    """
    if not OCRMYPDF_AVAILABLE:
        return False
    try:
        # --force-ocr força OCR mesmo se já tiver texto
        # --skip-text skipa páginas com texto real (deixa mais rápido)
        # Estratégia: primeiro tenta sem --force, se vier vazio no texto, a gente tenta forçar
        # Aqui já vamos direto no --force-ocr para garantir máxima extração.
        cmd = [
            sys.executable, "-m", "ocrmypdf",
            "--force-ocr",
            "--optimize", "0",
            "--quiet",
            input_pdf, output_pdf
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except Exception:
        return False

def pdf_extract_text_with_pymupdf(pdf_path: str) -> str:
    """
    Extrai texto com PyMuPDF. Se o PDF for imagem pura, pode vir vazio.
    """
    text_chunks = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text = page.get_text("text") or ""
            if not text.strip():
                # Tenta usar "blocks" como fallback leve
                text = page.get_text("blocks") or ""
                if isinstance(text, list):
                    text = "\n".join([b[4] for b in text if len(b) > 4 and isinstance(b[4], str)])
            text_chunks.append(text)
    return "\n".join(text_chunks).strip()

def rasterize_pdf_and_ocr(pdf_path: str, dpi: int = 300) -> str:
    """
    Rasteriza cada página do PDF e roda Tesseract com configurações otimizadas.
    """
    if not PDF2IMAGE_AVAILABLE:
        return ""
    
    try:
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=10)  # limita páginas
        
        texts = []
        for i, img in enumerate(images, 1):
            # Configurações otimizadas para documentos de texto
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝàáâãäåçèéêëìíîïñòóôõöùúûüý0123456789.,;:!?()[]{}/""-\'\s'
            
            try:
                # Primeiro tenta com configuração otimizada
                txt = pytesseract.image_to_string(img, lang="por+eng", config=custom_config)
                if not txt.strip():
                    # Se não funcionou, tenta configuração padrão
                    txt = pytesseract.image_to_string(img, lang="por+eng")
                
                if txt.strip():
                    texts.append(txt.strip())
                    
            except Exception:
                continue
        
        full_text = "\n\n".join(texts).strip()
        return full_text
        
    except Exception:
        return ""

def image_ocr(image_path: str) -> str:
    """
    OCR direto em imagem (jpg/png/tiff) - versão padrão.
    """
    try:
        img = Image.open(image_path)
        txt = pytesseract.image_to_string(img, lang="por+eng")
        return txt.strip()
    except Exception:
        return ""

def image_ocr_fast(image_path: str) -> str:
    """
    OCR otimizado para velocidade em imagem. Tenta EasyOCR primeiro, depois Tesseract.
    """
    # Tenta EasyOCR se disponível (geralmente mais rápido)
    if EASYOCR_AVAILABLE:
        try:
            global easyocr_reader
            if easyocr_reader is None:
                easyocr_reader = easyocr.Reader(['pt', 'en'], gpu=False)  # CPU mode para compatibilidade
            
            results = easyocr_reader.readtext(image_path, paragraph=True)
            if results:
                text = ' '.join([result[1] for result in results])
                return text.strip()
        except Exception:
            pass
    
    # Fallback para Tesseract rápido
    try:
        img = Image.open(image_path)
        
        # Configuração rápida do Tesseract
        fast_config = r'--oem 3 --psm 6 -c tessedit_pageseg_mode=6'
        txt = pytesseract.image_to_string(img, lang="por+eng", config=fast_config)
        return txt.strip()
    except Exception:
        return ""

def rasterize_pdf_and_ocr_fast(pdf_path: str, dpi: int = 200) -> str:
    """
    Versão RÁPIDA: rasteriza PDF e roda OCR com configurações otimizadas para velocidade.
    """
    if not PDF2IMAGE_AVAILABLE:
        return ""
    
    try:
        # Limita a 5 páginas e usa DPI menor para velocidade
        images = convert_from_path(pdf_path, dpi=dpi, first_page=1, last_page=5, thread_count=2)
        
        texts = []
        for i, img in enumerate(images, 1):
            try:
                # Configuração ultra-rápida - menos precisa mas muito mais rápida
                speed_config = r'--oem 3 --psm 6 -c tessedit_pageseg_mode=6 tessedit_ocr_engine_mode=3'
                
                txt = pytesseract.image_to_string(img, lang="por+eng", config=speed_config)
                
                if txt.strip():
                    texts.append(txt.strip())
                    
                    # Para acelerar ainda mais, para se já temos texto suficiente
                    if len('\n\n'.join(texts)) > 1000:
                        break
                        
            except Exception:
                continue
        
        full_text = "\n\n".join(texts).strip()
        return full_text
        
    except Exception:
        return ""

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

def pdf_to_images(pdf_path: str, max_pages: int = 10) -> List[Image.Image]:
    """
    Converte PDF para lista de imagens PIL para análise visual.
    """
    images = []
    try:
        # Primeiro tenta com pdf2image (mais rápido)
        if PDF2IMAGE_AVAILABLE:
            try:
                pdf_images = convert_from_path(pdf_path, dpi=200, first_page=1, last_page=max_pages)
                return pdf_images[:max_pages]
            except Exception:
                pass
        
        # Fallback com PyMuPDF
        doc = fitz.open(pdf_path)
        for page_num in range(min(len(doc), max_pages)):
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

def ensure_ocr_and_text(file_path: str) -> Tuple[str, str]:
    """
    Garante que teremos texto da matrícula usando APENAS OCR:
    - Se for imagem: OCR direto 
    - Se for PDF: SEMPRE usa OCR (nunca extração direta que só pega cabeçalhos)
    Retorna (texto, caminho_pdf_pesquisavel_ou_original).
    """
    ext = os.path.splitext(file_path.lower())[1]
    if ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]:
        text = image_ocr_fast(file_path)
        return text, file_path

    if ext == ".pdf":
        # ESTRATÉGIA: APENAS OCR (nunca extração direta de PDF)
        # 1) Primeiro tenta rasterizar + OCR otimizado
        text_fast = rasterize_pdf_and_ocr_fast(file_path, dpi=200)  # DPI menor para velocidade
        if len(text_fast) > 100:
            return text_fast, file_path

        # 2) Se OCR rápido falhar, tenta qualidade alta
        text_quality = rasterize_pdf_and_ocr(file_path, dpi=300)
        if len(text_quality) > 50:
            return text_quality, file_path

        # 3) Se tudo falhar, tenta ocrmypdf como último recurso
        with tempfile.TemporaryDirectory() as tmpd:
            out_pdf = os.path.join(tmpd, "ocr.pdf")
            if run_ocrmypdf(file_path, out_pdf):
                # NUNCA usa extração direta, sempre re-processa com OCR
                text_ocr = rasterize_pdf_and_ocr_fast(out_pdf, dpi=150)
                if len(text_ocr) > 50:
                    return text_ocr, out_pdf

        return "", file_path

    # Outros formatos não suportados
    return "", file_path

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
        message_content = payload['messages'][1]['content']
        image_count = sum(1 for item in message_content if item.get('type') == 'image_url')
        text_count = sum(1 for item in message_content if item.get('type') == 'text')
        
        print(f"🌐 Fazendo requisição para: {OPENROUTER_URL}")
        print(f"📦 Payload contém {len(message_content)} elementos total")
        print(f"🖼️ Imagens no payload: {image_count}")
        print(f"📝 Textos no payload: {text_count}")
        
        # Calcula tamanho total do payload em MB
        import sys
        payload_size_mb = sys.getsizeof(str(payload)) / (1024 * 1024)
        print(f"📐 Tamanho do payload: {payload_size_mb:.2f}MB")
        
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        
        print(f"📡 Status da resposta: {resp.status_code}")
        print(f"📊 Headers da resposta: {dict(list(resp.headers.items())[:5])}...")  # primeiros 5 headers
        
        if resp.status_code != 200:
            print(f"❌ Erro HTTP: {resp.text}")
            raise RuntimeError(f"API retornou status {resp.status_code}: {resp.text}")
            
        response_text = resp.text.strip()
        print(f"📝 Tamanho da resposta: {len(response_text)} chars")
        
        if not response_text:
            raise RuntimeError("Resposta vazia da API")
        
        # Debug da resposta bruta
        if len(response_text) < 100:
            print(f"📄 Resposta completa (pequena): {response_text}")
        else:
            print(f"📄 Início da resposta: {response_text[:200]}...")
            
        data = json.loads(response_text)
        
        if "choices" not in data or not data["choices"]:
            print(f"❌ Estrutura da resposta: {list(data.keys())}")
            raise RuntimeError(f"Formato de resposta inesperado: {data}")
            
        return data
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro na requisição para OpenRouter: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Erro ao decodificar JSON da resposta: {e}. Resposta: {response_text[:500]}")
    except Exception as e:
        raise RuntimeError(f"Erro inesperado na chamada da API: {e}")

def call_openrouter(model: str, system_prompt: str, user_prompt: str, temperature: float = 0.0, max_tokens: int = 1200) -> Dict:
    """
    Chama o endpoint /chat/completions do OpenRouter.
    Retorna o dicionário do JSON da resposta.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", OPENROUTER_API_KEY)
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY não configurada. Defina no .env ou variável de ambiente.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        # Campos opcionais, mas úteis para boas práticas:
        "HTTP-Referer": "https://pge-ms.lab/analise-matriculas",  # ajuste se quiser
        "X-Title": "Analise de Matriculas PGE-MS"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,  # Otimizado para velocidade
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"}  # força JSON se o modelo suportar
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120)
        
        # Debug: imprime resposta bruta se houver problema
        if resp.status_code != 200:
            print(f"Erro HTTP {resp.status_code}: {resp.text}")
            raise RuntimeError(f"API retornou status {resp.status_code}")
            
        response_text = resp.text.strip()
        if not response_text:
            raise RuntimeError("Resposta vazia da API")
            
        data = json.loads(response_text)
        
        # Verifica se a resposta tem o formato esperado
        if "choices" not in data or not data["choices"]:
            raise RuntimeError(f"Formato de resposta inesperado: {data}")
            
        return data
        
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erro na requisição para OpenRouter: {e}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Erro ao decodificar JSON da resposta: {e}. Resposta: {response_text[:500]}")
    except Exception as e:
        raise RuntimeError(f"Erro inesperado na chamada da API: {e}")

def clean_json_response(content: str) -> str:
    """Remove marcadores de código markdown do JSON"""
    clean_content = content.strip()
    if clean_content.startswith("```json"):
        clean_content = clean_content[7:]
    if clean_content.startswith("```"):
        clean_content = clean_content[3:]
    if clean_content.endswith("```"):
        clean_content = clean_content[:-3]
    return clean_content.strip()

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
    "🔥 ALERTA MÁXIMO: A omissão de qualquer confrontante pode invalidar o usucapião. Seja METICULOSO.\n\n"
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
    '      "evidence": ["trecho literal 1", "trecho literal 2"]\n'
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

def chunk_text(txt: str, max_chars: int = 18000) -> List[str]:
    """
    Divide texto em pedaços seguros para contexto.
    """
    txt = txt or ""
    if len(txt) <= max_chars:
        return [txt]
    chunks = []
    start = 0
    while start < len(txt):
        end = min(start + max_chars, len(txt))
        # tenta quebrar em limite de parágrafo
        if end < len(txt):
            nl = txt.rfind("\n\n", start, end)
            if nl != -1 and (end - nl) < 1500:
                end = nl
        chunks.append(txt[start:end])
        start = end
    return chunks

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
            total_pages = get_pdf_page_count(file_path)
            print(f"📊 PDF contém {total_pages} página(s)")
            
            if total_pages > 30:
                raise ValueError(
                    f"PDF com {total_pages} páginas excede o limite máximo de 30 páginas. "
                    f"Por favor, divida o documento em arquivos menores ou processe apenas as páginas relevantes."
                )
            
            images = pdf_to_images(file_path, max_pages=30)  # máximo de 30 páginas
            print(f"📄 PDF convertido em {len(images)} página(s)")
        elif ext in [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"]:
            images = [Image.open(file_path)]
            print(f"🖼️ Imagem carregada para análise")
        else:
            raise ValueError(f"Formato de arquivo não suportado para análise visual: {ext}")
        
        if not images:
            raise ValueError("Não foi possível extrair imagens do arquivo")
        
        print(f"🔄 Preparando {len(images)} imagem(ns) para envio à IA...")
        
        # Converte imagens para base64
        images_b64 = []
        total_size_kb = 0
        
        for i, img in enumerate(images):
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
        
        print(f"📈 TOTAL: {len(images_b64)} imagens preparadas, {total_size_kb:.1f}KB")
        
        # Verificação de limitações da API
        MAX_IMAGES = 30  # Limitação máxima permitida
        MAX_SIZE_MB = 50  # Limitação conservadora de payload
        
        # Verificação já foi feita no início - não deve exceder 30 páginas
        if len(images_b64) > MAX_IMAGES:
            print(f"⚠️ ERRO INTERNO: {len(images_b64)} imagens excede limite de {MAX_IMAGES}")
            raise ValueError(f"Erro interno: Número de imagens ({len(images_b64)}) excede limite máximo")
        
        if total_size_kb / 1024 > MAX_SIZE_MB:
            print(f"⚠️ Payload muito grande ({total_size_kb/1024:.1f}MB) - reduzindo qualidade das imagens")
            # Reconverte com qualidade menor
            images_b64 = []
            for i, img in enumerate(images[:MAX_IMAGES]):
                b64 = image_to_base64(img, max_size=1024, jpeg_quality=60)  # Qualidade reduzida
                if b64:
                    images_b64.append(b64)
            total_size_kb = sum(len(img) // 1024 for img in images_b64)
            print(f"📈 APÓS REDUÇÃO: {len(images_b64)} imagens, {total_size_kb:.1f}KB")
        
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
            "🔥 VIDA OU MORTE: Cada confrontante perdido pode invalidar o usucapião. ZERO TOLERÂNCIA para omissões.\n\n"
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
            "Responda em JSON seguindo exatamente este formato:\n\n" +
            AGGREGATE_PROMPT.split("Responda em JSON com este esquema:\n")[1]
        )
        
        # Chama API com visão
        print(f"🚀 Enviando {len(images_b64)} imagem(ns) para {model}...")
        print(f"📏 Tamanho do prompt: {len(vision_prompt)} chars")
        
        data = call_openrouter_vision(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=vision_prompt,
            images_base64=images_b64,
            temperature=0.0,
            max_tokens=80000  # Tokens otimizados para análise eficiente
        )
        
        print(f"✅ Resposta da API recebida com sucesso")
        
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
        
        content = data["choices"][0]["message"]["content"]
        print(f"🔍 Content final: {len(content) if content else 0} chars")
        if content:
            print(f"📝 Primeiros 500 chars: {content[:500]}")
        else:
            print(f"⚠️ Content está vazio ou None!")
        
        try:
            # Limpa marcadores de código markdown se presentes
            clean_content = clean_json_response(content)
            print(f"🔧 JSON limpo para parse: {clean_content[:100]}...")
            parsed = json.loads(clean_content)
            print(f"✅ JSON parsed com sucesso")
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

        # Converte dados das matrículas para objetos MatriculaInfo
        matriculas_obj = []
        for m_data in parsed.get("matriculas_encontradas", []):
            if isinstance(m_data, dict):
                matricula = MatriculaInfo(
                    numero=m_data.get("numero", ""),
                    proprietarios=m_data.get("proprietarios", []),
                    descricao=m_data.get("descricao", ""),
                    confrontantes=m_data.get("confrontantes", []),
                    evidence=m_data.get("evidence", []),
                    lote=m_data.get("lote"),
                    quadra=m_data.get("quadra")
                )
                matriculas_obj.append(matricula)

        # Processa lotes confrontantes
        lotes_confrontantes_obj = []
        for lote_data in parsed.get("lotes_confrontantes", []):
            if isinstance(lote_data, dict):
                lote_confronta = LoteConfronta(
                    identificador=lote_data.get("identificador", ""),
                    tipo=lote_data.get("tipo", "outros"),
                    matricula_anexada=lote_data.get("matricula_anexada"),
                    direcao=lote_data.get("direcao")
                )
                lotes_confrontantes_obj.append(lote_confronta)

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
            confidence=parsed.get("confidence"),
            reasoning=parsed.get("reasoning", ""),
            raw_json=parsed
        )
        
    except Exception as e:
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

def analyze_text_with_llm(model: str, full_text: str) -> AnalysisResult:
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
        content = data["choices"][0]["message"]["content"]
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
        except Exception as e:
            print(f"Erro inesperado no parsing: {e}")
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
                "reasoning": f"Erro: {e}"
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
                    evidence=m_data.get("evidence", []),
                    lote=m_data.get("lote"),
                    quadra=m_data.get("quadra")
                )
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
        content = data["choices"][0]["message"]["content"]
        try:
            clean_content = clean_json_response(content)
            parsed = json.loads(clean_content)
            if "confrontantes" in parsed and isinstance(parsed["confrontantes"], list):
                all_confrontantes.extend([c for c in parsed["confrontantes"] if isinstance(c, str)])
            if "evidence" in parsed and isinstance(parsed["evidence"], list):
                all_evidence.extend([e for e in parsed["evidence"] if isinstance(e, str)])
        except json.JSONDecodeError as e:
            print(f"Erro JSON no chunk {i}: {e}")
            print(f"Conteúdo: {content[:200]}")
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
    content = data["choices"][0]["message"]["content"]
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
            "confrontacao_completa": None,
            "proprietarios_identificados": {},
            "confidence": None,
            "reasoning": f"Erro JSON: {content}"
        }
    except Exception as e:
        print(f"Erro na chamada final: {e}")
        parsed = {
            "matriculas_encontradas": [],
            "matricula_principal": None,
            "matriculas_confrontantes": [],
            "confrontacao_completa": None,
            "proprietarios_identificados": {},
            "confidence": None,
            "reasoning": f"Erro: {e}"
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

        ttk.Label(right, text="Resultados da Análise de Usucapião").pack(anchor="w", pady=(0,4))
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
                
                # Verifica se o arquivo existe
                if not os.path.exists(path):
                    self.queue.put(("log", f"❌ Arquivo não encontrado: {filename}"))
                    continue
                
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
                    self.queue.put(("log", f"⚠️ Problema na análise visual - verifique se o arquivo é legível"))
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

                self.queue.put(("log", f"✅ Análise de {filename} concluída com sucesso (confiança: {confianca_pct})"))
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
        proprietarios_principal = matricula_principal_obj.proprietarios
        if not proprietarios_principal:
            proprietarios_principal = ["N/A"]
        
        # Formata informação de lote/quadra da matrícula principal
        lote_quadra_principal = ""
        if matricula_principal_obj.lote or matricula_principal_obj.quadra:
            lote_parts = []
            if matricula_principal_obj.lote:
                lote_parts.append(f"Lote {matricula_principal_obj.lote}")
            if matricula_principal_obj.quadra:
                lote_parts.append(f"Quadra {matricula_principal_obj.quadra}")
            lote_quadra_principal = " / ".join(lote_parts)
        
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
            
            resumo_header = f"🎯 ANÁLISE PERICIAL (Confiança: {confianca}%)\n\n"
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
            "• anthropic/claude-3.5-sonnet (Recomendado)\n"
            "• anthropic/claude-3-opus\n"
            "• anthropic/claude-3-sonnet\n"
            "• anthropic/claude-3-haiku\n"
            "• openai/gpt-4o\n"
            "• openai/gpt-4o-mini\n"
            "• openai/gpt-4-turbo\n\n"
            "IMPORTANTE:\n"
            "Este sistema usa análise visual direta dos documentos.\n"
            "Certifique-se de usar um modelo que suporte imagens.\n\n"
            "Claude 3.5 Sonnet é altamente recomendado para\n"
            "análise precisa de documentos jurídicos."
        )
        messagebox.showinfo("Modelos com Suporte a Visão", info)

    def log(self, msg: str):
        self.txt_log.insert("end", msg + "\n")
        self.txt_log.see("end")

# =========================
# Main
# =========================
if __name__ == "__main__":
    app = App()
    app.mainloop()
