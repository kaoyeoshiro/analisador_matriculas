import os
import sys
import json
import time
import threading
import tempfile
import subprocess
import requests
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Callable

# Import seguro para packaging.version
try:
    from packaging import version
    HAS_PACKAGING = True
except ImportError:
    HAS_PACKAGING = False
    # Implementação simples para comparação de versões
    class SimpleVersion:
        def __init__(self, version_string):
            self.version_string = version_string
            # Remove 'v' prefix se existir
            if version_string.startswith('v'):
                version_string = version_string[1:]
            # Split em números
            self.parts = []
            for part in version_string.split('.'):
                try:
                    self.parts.append(int(part))
                except ValueError:
                    self.parts.append(0)

        def __gt__(self, other):
            if isinstance(other, str):
                other = SimpleVersion(other)
            # Compara parte por parte
            max_len = max(len(self.parts), len(other.parts))
            self_parts = self.parts + [0] * (max_len - len(self.parts))
            other_parts = other.parts + [0] * (max_len - len(other.parts))

            for i in range(max_len):
                if self_parts[i] > other_parts[i]:
                    return True
                elif self_parts[i] < other_parts[i]:
                    return False
            return False

    # Cria alias para manter compatibilidade
    version = type('', (), {'parse': SimpleVersion})()

class AutoUpdater:
    def __init__(self,
                 repo_owner: str,
                 repo_name: str,
                 current_version: str = None,
                 executable_name: str = None,
                 silent: bool = True,
                 auto_update: bool = True,
                 parent_window = None):
        """
        Sistema de auto-atualização automática

        Args:
            repo_owner: Proprietário do repositório GitHub
            repo_name: Nome do repositório
            current_version: Versão atual (se None, lê do arquivo VERSION)
            executable_name: Nome do executável (se None, usa o nome atual)
            silent: Se True, não exibe logs detalhados
            auto_update: Se True, aplica atualizações automaticamente
            parent_window: Janela pai para diálogos (opcional)
        """
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.silent = silent
        self.auto_update = auto_update
        self.parent_window = parent_window

        # Detecta se está rodando como executável
        self.is_executable = getattr(sys, 'frozen', False)

        # Determina o executável atual
        if executable_name:
            self.executable_name = executable_name
        elif self.is_executable:
            self.executable_name = os.path.basename(sys.executable)
        else:
            self.executable_name = "RelatorioTJMS.exe"  # Nome padrão

        # Detecta o caminho real do executável atual
        if self.is_executable:
            # Se está rodando como executável, usa o caminho real
            self.current_exe_path = sys.executable
            self.app_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # Se não é executável, procura pelo executável no diretório
            self.app_dir = os.path.dirname(os.path.abspath(__file__))

            # Procura o executável em vários locais possíveis
            possible_paths = [
                os.path.join(self.app_dir, self.executable_name),
                os.path.join(self.app_dir, "dist", self.executable_name),
                os.path.join(os.getcwd(), self.executable_name),
                os.path.join(os.getcwd(), "dist", self.executable_name),
            ]

            self.current_exe_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    self.current_exe_path = path
                    break

            # Se não encontrou, usa o caminho padrão (será verificado depois)
            if not self.current_exe_path:
                self.current_exe_path = os.path.join(self.app_dir, self.executable_name)

        # Garante que o diretório existe
        if not os.path.exists(self.app_dir):
            self.app_dir = os.getcwd()

        # Versão atual
        self.current_version = current_version or self._read_version_file()

        # URLs da API do GitHub
        self.api_base = f"https://api.github.com/repos/{repo_owner}/{repo_name}"

        if not self.silent:
            print(f"[AutoUpdater] Inicializado para {repo_owner}/{repo_name}")
            print(f"[AutoUpdater] Versão atual: {self.current_version}")
            print(f"[AutoUpdater] Executável: {self.executable_name}")
            print(f"[AutoUpdater] Diretório: {self.app_dir}")
            print(f"[AutoUpdater] Caminho do executável: {self.current_exe_path}")
            print(f"[AutoUpdater] É executável: {self.is_executable}")

    def _read_version_file(self) -> str:
        """Lê a versão do arquivo VERSION"""
        # Tenta encontrar o arquivo VERSION em vários locais
        possible_locations = [
            os.path.join(self.app_dir, "VERSION"),
            os.path.join(self.app_dir, "version"),
            os.path.join(os.getcwd(), "VERSION"),
            os.path.join(os.getcwd(), "version"),
            os.path.join(os.path.dirname(__file__), "VERSION"),
            os.path.join(os.path.dirname(__file__), "version")
        ]

        for version_file in possible_locations:
            try:
                if os.path.exists(version_file):
                    with open(version_file, 'r', encoding='utf-8') as f:
                        version_content = f.read().strip()
                        if version_content:
                            if not self.silent:
                                print(f"[AutoUpdater] Versão lida de: {version_file}")
                            return version_content
            except Exception as e:
                if not self.silent:
                    print(f"[AutoUpdater] Erro ao ler {version_file}: {e}")
                continue

        if not self.silent:
            print(f"[AutoUpdater] Arquivo VERSION não encontrado, usando versão padrão")
        return "1.0.0"

    def _update_version_files(self, new_version: str):
        """Atualiza todos os arquivos de versão encontrados"""
        # Locais onde atualizar o arquivo VERSION
        version_locations = [
            os.path.join(self.app_dir, "VERSION"),
            os.path.join(self.app_dir, "version"),
            os.path.join(os.getcwd(), "VERSION"),
            os.path.join(os.getcwd(), "version"),
            os.path.join(os.path.dirname(__file__), "VERSION"),
            os.path.join(os.path.dirname(__file__), "version")
        ]

        updated_files = []
        for version_file in version_locations:
            try:
                # Se o arquivo já existe ou está no diretório do app, atualiza
                if os.path.exists(version_file) or os.path.dirname(version_file) == self.app_dir:
                    with open(version_file, 'w', encoding='utf-8') as f:
                        f.write(new_version)
                    updated_files.append(version_file)
                    if not self.silent:
                        print(f"[AutoUpdater] Arquivo VERSION atualizado: {version_file}")
            except Exception as e:
                if not self.silent:
                    print(f"[AutoUpdater] Erro ao atualizar {version_file}: {e}")

        return updated_files

    def sync_version_with_github(self) -> bool:
        """Sincroniza a versão local com a versão do GitHub (sem baixar executável)"""
        try:
            # Verifica a versão mais recente no GitHub
            url = f"{self.api_base}/releases/latest"
            headers = {'Accept': 'application/vnd.github.v3+json'}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            release_data = response.json()
            latest_version = release_data['tag_name'].lstrip('v')

            self._log(f"Versão no GitHub: {latest_version}")
            self._log(f"Versão local: {self.current_version}")

            # Se a versão local está desatualizada, atualiza os arquivos VERSION
            if version.parse(latest_version) > version.parse(self.current_version):
                self._log("Versão local desatualizada. Atualizando arquivos VERSION...")
                updated_files = self._update_version_files(latest_version)

                if updated_files:
                    self._log(f"Arquivos VERSION atualizados: {updated_files}")
                    # Atualiza a versão atual em memória
                    self.current_version = latest_version
                    return True
                else:
                    self._log("Nenhum arquivo VERSION foi atualizado")
                    return False
            else:
                self._log("Versão local já está atualizada")
                return False

        except Exception as e:
            self._log(f"Erro ao sincronizar versão: {e}")
            return False

    def _log(self, message: str):
        """Log interno respeitando o modo silent"""
        if not self.silent:
            print(f"[AutoUpdater] {message}")

    def check_for_updates(self) -> Optional[dict]:
        """
        Verifica se há atualizações disponíveis

        Returns:
            dict com informações da release ou None se não há updates
        """
        try:
            self._log("Verificando atualizações...")

            # Busca a latest release
            url = f"{self.api_base}/releases/latest"
            headers = {'Accept': 'application/vnd.github.v3+json'}

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            release_data = response.json()
            latest_version = release_data['tag_name'].lstrip('v')

            self._log(f"Versão disponível: {latest_version}")
            self._log(f"Versão atual: {self.current_version}")

            # Compara versões
            if version.parse(latest_version) > version.parse(self.current_version):
                self._log("Nova versão encontrada!")

                # Procura o asset do executável
                executable_asset = None
                for asset in release_data.get('assets', []):
                    if asset['name'].endswith('.exe') or asset['name'] == self.executable_name:
                        executable_asset = asset
                        break

                if executable_asset:
                    return {
                        'version': latest_version,
                        'download_url': executable_asset['browser_download_url'],
                        'asset_name': executable_asset['name'],
                        'release_notes': release_data.get('body', ''),
                        'published_at': release_data.get('published_at', '')
                    }
                else:
                    self._log("Executável não encontrado nos assets da release")
            else:
                self._log("Já está na versão mais recente")

        except requests.exceptions.RequestException as e:
            self._log(f"Erro de rede ao verificar atualizações: {e}")
        except Exception as e:
            self._log(f"Erro ao verificar atualizações: {e}")

        return None

    def download_update(self, update_info: dict, progress_callback: Callable[[int], None] = None) -> Optional[str]:
        """
        Faz download da nova versão

        Args:
            update_info: Informações da atualização do check_for_updates
            progress_callback: Função para callback de progresso (0-100)

        Returns:
            Caminho do arquivo baixado ou None em caso de erro
        """
        try:
            download_url = update_info['download_url']
            asset_name = update_info['asset_name']

            self._log(f"Baixando atualização: {asset_name}")

            # Cria arquivo temporário
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"update_{asset_name}")

            # Download com progress
            response = requests.get(download_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        if progress_callback and total_size > 0:
                            progress = int((downloaded / total_size) * 100)
                            progress_callback(progress)

            self._log(f"Download concluído: {temp_file}")
            return temp_file

        except Exception as e:
            self._log(f"Erro no download: {e}")
            return None

    def apply_update(self, downloaded_file: str, update_info: dict) -> bool:
        """
        Aplica a atualização substituindo o executável atual

        Args:
            downloaded_file: Caminho do arquivo baixado
            update_info: Informações da atualização

        Returns:
            True se sucesso, False caso contrário
        """
        try:
            # Usa o caminho pré-detectado no __init__
            current_exe = self.current_exe_path

            # Log detalhado para debug
            self._log(f"Aplicando atualização...")
            self._log(f"is_executable: {self.is_executable}")
            self._log(f"app_dir: {self.app_dir}")
            self._log(f"executable_name: {self.executable_name}")
            self._log(f"current_exe_path: {current_exe}")

            # Verifica se os arquivos existem
            if not os.path.exists(downloaded_file):
                self._log(f"Arquivo baixado não encontrado: {downloaded_file}")
                return False

            if not os.path.exists(current_exe):
                self._log(f"Executável atual não encontrado: {current_exe}")
                self._log("Falha na detecção do executável - cancelando atualização")
                return False

            self._log(f"Aplicando atualização de: {current_exe}")

            # Usa caminhos curtos para evitar problemas com espaços
            import subprocess
            try:
                # Converte para caminho curto no Windows
                def get_short_path(path):
                    try:
                        import ctypes
                        from ctypes import wintypes
                        _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
                        _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
                        _GetShortPathNameW.restype = wintypes.DWORD

                        output_buf = ctypes.create_unicode_buffer(260)
                        result = _GetShortPathNameW(path, output_buf, 260)
                        if result:
                            return output_buf.value
                    except:
                        pass
                    return path

                current_exe_short = get_short_path(current_exe)
                downloaded_file_short = get_short_path(downloaded_file)
                version_file_short = get_short_path(os.path.join(self.app_dir, 'VERSION'))

            except:
                # Fallback para caminhos normais com aspas duplas
                current_exe_short = f'"{current_exe}"'
                downloaded_file_short = f'"{downloaded_file}"'
                version_file_short = f'"{os.path.join(self.app_dir, "VERSION")}"'

            # Usa caminhos curtos também no PowerShell
            try:
                import ctypes
                from ctypes import wintypes
                def get_short_path_ps(path):
                    try:
                        _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
                        _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
                        _GetShortPathNameW.restype = wintypes.DWORD
                        output_buf = ctypes.create_unicode_buffer(260)
                        result = _GetShortPathNameW(path, output_buf, 260)
                        if result:
                            return output_buf.value
                    except:
                        pass
                    return path

                current_exe_ps = get_short_path_ps(current_exe)
                downloaded_file_ps = get_short_path_ps(downloaded_file)
                version_file_ps = get_short_path_ps(os.path.join(self.app_dir, 'VERSION'))
            except:
                current_exe_ps = current_exe
                downloaded_file_ps = downloaded_file
                version_file_ps = os.path.join(self.app_dir, 'VERSION')

            self._log(f"PowerShell - Original: {current_exe}")
            self._log(f"PowerShell - Curto: {current_exe_ps}")

            # Escapa aspas duplas e usa caminhos literais
            def escape_path_for_powershell(path):
                # Escapa aspas duplas e usa aspas simples para envolver
                return f"'{path}'"

            downloaded_safe = escape_path_for_powershell(downloaded_file)
            current_safe = escape_path_for_powershell(current_exe)
            version_safe = escape_path_for_powershell(os.path.join(self.app_dir, 'VERSION'))

            self._log(f"PowerShell paths:")
            self._log(f"  Downloaded: {downloaded_safe}")
            self._log(f"  Current: {current_safe}")

            # Cria script PowerShell mais robusto (funciona melhor com caminhos)
            powershell_content = f"""
# Auto-update script
$ErrorActionPreference = "Stop"

Write-Host "Aplicando atualizacao..."
Start-Sleep -Seconds 2

$downloadedFile = {downloaded_safe}
$currentExe = {current_safe}
$appDir = '{self.app_dir}'
$newVersion = "{update_info['version']}"

# Lista de arquivos VERSION para atualizar
$versionFiles = @(
    (Join-Path $appDir "VERSION"),
    (Join-Path $appDir "version"),
    (Join-Path (Get-Location) "VERSION"),
    (Join-Path (Get-Location) "version")
)

Write-Host "Verificando arquivos..."
Write-Host "Arquivo baixado: $downloadedFile"
Write-Host "Executavel atual: $currentExe"

# Verifica se os arquivos existem
$downloadExists = Test-Path -LiteralPath $downloadedFile
$currentExists = Test-Path -LiteralPath $currentExe

Write-Host "Download existe: $downloadExists"
Write-Host "Current existe: $currentExists"

if (-not $downloadExists) {{
    Write-Host "ERRO: Arquivo de atualizacao nao encontrado"
    Write-Host "Caminho testado: $downloadedFile"
    Read-Host "Pressione Enter para continuar"
    exit 1
}}

if (-not $currentExists) {{
    Write-Host "ERRO: Executavel atual nao encontrado"
    Write-Host "Caminho testado: $currentExe"
    Write-Host "Listando arquivos no diretorio:"
    Get-ChildItem (Split-Path $currentExe -Parent) | ForEach-Object {{ Write-Host "  $($_.Name)" }}
    Read-Host "Pressione Enter para continuar"
    exit 1
}}

try {{
    Write-Host "Criando backup..."
    $backupPath = "$currentExe.backup"
    Copy-Item -LiteralPath $currentExe -Destination $backupPath -Force

    Write-Host "Aplicando nova versao..."
    Copy-Item -LiteralPath $downloadedFile -Destination $currentExe -Force

    Write-Host "Atualizando arquivos de versao..."
    foreach ($versionFile in $versionFiles) {{
        try {{
            if ((Test-Path -LiteralPath $versionFile) -or ($versionFile -like "*$appDir*")) {{
                $newVersion | Out-File -LiteralPath $versionFile -Encoding UTF8 -NoNewline
                Write-Host "  ✓ Atualizado: $versionFile"
            }}
        }} catch {{
            Write-Host "  ❌ Erro ao atualizar: $versionFile - $($_.Exception.Message)"
        }}
    }}

    Write-Host "Limpando arquivos temporarios..."
    Remove-Item -LiteralPath $downloadedFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue

    Write-Host "Atualizacao aplicada com sucesso!"
    Write-Host "Reiniciando aplicacao em 3 segundos..."
    Start-Sleep -Seconds 3

    Start-Process -LiteralPath $currentExe

}} catch {{
    Write-Host "ERRO: $($_.Exception.Message)"
    Write-Host "Restaurando backup..."
    $backupPath = "$currentExe.backup"
    if (Test-Path -LiteralPath $backupPath) {{
        Copy-Item -LiteralPath $backupPath -Destination $currentExe -Force
        Remove-Item -LiteralPath $backupPath -Force -ErrorAction SilentlyContinue
    }}
    Read-Host "Pressione Enter para continuar"
    exit 1
}}

Start-Sleep -Seconds 1
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""

            # Salva e executa o script PowerShell
            ps_file = os.path.join(tempfile.gettempdir(), "update_aplicar.ps1")
            with open(ps_file, 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(powershell_content)

            self._log("Executando script de atualização...")

            # PowerShell geralmente tem problemas, vai direto para batch que é mais confiável
            self._log("🔄 Usando método batch direto (mais confiável que PowerShell)...")
            self._apply_update_batch(downloaded_file, current_exe, update_info)
            return True

            # Sai do aplicativo atual para permitir substituição
            time.sleep(1)
            sys.exit(0)

        except Exception as e:
            self._log(f"Erro ao aplicar atualização: {e}")
            return False

    def _apply_update_batch(self, downloaded_file: str, current_exe: str, update_info: dict):
        """Método fallback usando batch script"""
        try:
            self._log("🔄 Usando método batch para atualização...")

            # Converte caminhos para formato curto (evita problemas com acentos)
            def get_short_path_name(long_path):
                try:
                    import ctypes
                    from ctypes import wintypes
                    _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
                    _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
                    _GetShortPathNameW.restype = wintypes.DWORD

                    output_buf = ctypes.create_unicode_buffer(260)
                    result = _GetShortPathNameW(long_path, output_buf, 260)
                    if result:
                        return output_buf.value
                except:
                    pass
                return long_path

            # Usa caminhos curtos para evitar problemas com acentos
            current_exe_short = get_short_path_name(current_exe)
            downloaded_file_short = get_short_path_name(downloaded_file)
            version_file_short = get_short_path_name(os.path.join(self.app_dir, 'VERSION'))

            self._log(f"Caminho original: {current_exe}")
            self._log(f"Caminho curto: {current_exe_short}")

            # Usa subst para criar drive temporário se necessário
            # Isso evita problemas com acentos completamente
            batch_content = f"""@echo off
setlocal enabledelayedexpansion
chcp 65001 > nul
echo Aplicando atualizacao (metodo batch)...
timeout /t 2 /nobreak > nul

echo Debug: Verificando caminhos originais...
echo Downloaded original: {downloaded_file}
echo Current original: {current_exe}
echo Downloaded short: {downloaded_file_short}
echo Current short: {current_exe_short}

echo Verificando se arquivos existem...
if exist "{downloaded_file}" (
    echo ✓ Arquivo de download encontrado: {downloaded_file}
) else (
    echo ❌ Arquivo de download NAO encontrado: {downloaded_file}
    if exist "{downloaded_file_short}" (
        echo ✓ Mas versao curta encontrada: {downloaded_file_short}
        set "DOWNLOAD_FILE={downloaded_file_short}"
    ) else (
        echo ❌ Versao curta tambem nao encontrada: {downloaded_file_short}
        pause
        exit /b 1
    )
)

if exist "{current_exe}" (
    echo ✓ Executavel atual encontrado: {current_exe}
    set "CURRENT_EXE={current_exe}"
) else (
    echo ❌ Executavel atual NAO encontrado: {current_exe}
    if exist "{current_exe_short}" (
        echo ✓ Mas versao curta encontrada: {current_exe_short}
        set "CURRENT_EXE={current_exe_short}"
    ) else (
        echo ❌ Versao curta tambem nao encontrada: {current_exe_short}
        echo Listando arquivos no diretorio:
        dir "{os.path.dirname(current_exe)}" /b
        pause
        exit /b 1
    )
)

echo Aguardando aplicacao fechar...
timeout /t 3 /nobreak

echo Verificando se processo ainda esta rodando...
tasklist /FI "IMAGENAME eq RelatorioTJMS.exe" 2>NUL | find /I /N "RelatorioTJMS.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo Tentando fechar processo RelatorioTJMS.exe...
    taskkill /F /IM RelatorioTJMS.exe >nul 2>&1
    timeout /t 2 /nobreak
)

echo Criando backup...
copy "%CURRENT_EXE%" "%CURRENT_EXE%.backup" > nul 2>&1

echo Aplicando nova versao...
if not defined DOWNLOAD_FILE set "DOWNLOAD_FILE={downloaded_file}"

REM Tenta copiar 3 vezes com intervalo
set COPY_SUCCESS=0
for /L %%i in (1,1,3) do (
    if !COPY_SUCCESS! equ 0 (
        echo Tentativa %%i de copia...
        copy "%DOWNLOAD_FILE%" "%CURRENT_EXE%" /Y >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            set COPY_SUCCESS=1
            echo ✓ Copia bem-sucedida na tentativa %%i
        ) else (
            echo ❌ Tentativa %%i falhou, aguardando...
            timeout /t 2 /nobreak
        )
    )
)

if !COPY_SUCCESS! equ 0 (
    echo ERRO: Falha ao copiar nova versao apos 3 tentativas
    echo Restaurando backup...
    copy "%CURRENT_EXE%.backup" "%CURRENT_EXE%" /Y > nul 2>&1
    pause
    exit /b 1
)

echo Atualizando arquivos de versao...
REM Atualiza VERSION no diretorio do app
if exist "{os.path.join(self.app_dir, 'VERSION')}" (
    echo {update_info['version']} > "{os.path.join(self.app_dir, 'VERSION')}"
    echo   ✓ Atualizado: {os.path.join(self.app_dir, 'VERSION')}
) else (
    echo {update_info['version']} > "{os.path.join(self.app_dir, 'VERSION')}"
    echo   ✓ Criado: {os.path.join(self.app_dir, 'VERSION')}
)

REM Atualiza version no diretorio do app (minuscula)
if exist "{os.path.join(self.app_dir, 'version')}" (
    echo {update_info['version']} > "{os.path.join(self.app_dir, 'version')}"
    echo   ✓ Atualizado: {os.path.join(self.app_dir, 'version')}
)

REM Atualiza VERSION no diretorio atual
if exist "{os.path.join(os.getcwd(), 'VERSION')}" (
    echo {update_info['version']} > "{os.path.join(os.getcwd(), 'VERSION')}"
    echo   ✓ Atualizado: {os.path.join(os.getcwd(), 'VERSION')}
)

REM Atualiza version no diretorio atual (minuscula)
if exist "{os.path.join(os.getcwd(), 'version')}" (
    echo {update_info['version']} > "{os.path.join(os.getcwd(), 'version')}"
    echo   ✓ Atualizado: {os.path.join(os.getcwd(), 'version')}
)

echo Limpando arquivos temporarios...
del "%DOWNLOAD_FILE%" > nul 2>&1
del "%CURRENT_EXE%.backup" > nul 2>&1

echo Atualizacao aplicada com sucesso!
echo Reiniciando aplicacao em 3 segundos...
timeout /t 3 /nobreak

start "" "%CURRENT_EXE%"

timeout /t 1 /nobreak > nul
del "%~f0"
"""

            # Salva e executa o script batch
            batch_file = os.path.join(tempfile.gettempdir(), "update_aplicar.bat")
            with open(batch_file, 'w', encoding='utf-8', newline='\r\n') as f:
                f.write(batch_content)

            self._log(f"Executando script batch: {batch_file}")

            # Executa o batch
            subprocess.Popen([batch_file], creationflags=subprocess.CREATE_NEW_CONSOLE)

            # Aguarda um pouco e depois sai para permitir substituição
            self._log("Saindo da aplicação para permitir atualização...")
            time.sleep(2)
            sys.exit(0)

        except Exception as e:
            self._log(f"Erro no método batch: {e}")
            return False

    def update_if_available(self, progress_callback: Callable[[str, int], None] = None) -> bool:
        """
        Verifica e aplica atualização automaticamente se disponível

        Args:
            progress_callback: Função para callback de progresso (status, percentage)

        Returns:
            True se houve atualização, False caso contrário
        """
        try:
            if progress_callback:
                progress_callback("Verificando atualizações...", 0)

            # Verifica por atualizações
            update_info = self.check_for_updates()

            if not update_info:
                if progress_callback:
                    progress_callback("Já está atualizado", 100)
                return False

            if not self.auto_update:
                self._log(f"Nova versão disponível: {update_info['version']} (auto_update=False)")
                return False

            if progress_callback:
                progress_callback("Baixando atualização...", 20)

            # Download da atualização
            def download_progress(percent):
                if progress_callback:
                    progress_callback("Baixando atualização...", 20 + int(percent * 0.7))

            downloaded_file = self.download_update(update_info, download_progress)

            if not downloaded_file:
                if progress_callback:
                    progress_callback("Erro no download", 100)
                return False

            if progress_callback:
                progress_callback("Aplicando atualização...", 95)

            # Aplica a atualização (vai sair do app)
            self.apply_update(downloaded_file, update_info)

            return True

        except Exception as e:
            self._log(f"Erro na atualização automática: {e}")
            if progress_callback:
                progress_callback("Erro na atualização", 100)
            return False

    def check_and_update_async(self, callback: Callable[[bool, str], None] = None):
        """
        Executa verificação e atualização em thread separada

        Args:
            callback: Função chamada ao final (success, message)
        """
        def update_thread():
            try:
                success = self.update_if_available()
                message = "Atualização aplicada" if success else "Já está atualizado"
                if callback:
                    callback(success, message)
            except Exception as e:
                if callback:
                    callback(False, f"Erro: {e}")

        thread = threading.Thread(target=update_thread, daemon=True)
        thread.start()
        return thread


def create_updater(repo_owner: str = "kaoyeoshiro", repo_name: str = "analisador_matriculas") -> AutoUpdater:
    """
    Cria uma instância do AutoUpdater com configurações padrão

    Args:
        repo_owner: Proprietário do repositório (padrão: kaoyeoshiro)
        repo_name: Nome do repositório (padrão: analisador_matriculas)

    Returns:
        Instância configurada do AutoUpdater
    """
    return AutoUpdater(
        repo_owner=repo_owner,
        repo_name=repo_name,
        executable_name="RelatorioTJMS.exe",
        silent=True,
        auto_update=True
    )


if __name__ == "__main__":
    # Teste do sistema de atualização
    print("=== Teste do Sistema de Auto-Atualização ===")

    updater = create_updater()
    print(f"Versão atual: {updater.current_version}")

    # Verifica por atualizações
    update_info = updater.check_for_updates()

    if update_info:
        print(f"Nova versão disponível: {update_info['version']}")
        print(f"URL de download: {update_info['download_url']}")

        # Pergunta se deve aplicar
        choice = input("\nAplicar atualização? (s/N): ").lower().strip()
        if choice == 's':
            print("\nIniciando atualização...")
            updater.update_if_available()
    else:
        print("Já está na versão mais recente!")