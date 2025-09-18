#!/usr/bin/env python3
"""
Script para construir executável do Sistema de Análise de Matrículas Confrontantes
Usa PyInstaller para criar um arquivo .exe distribuível
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def clean_build_dirs():
    """Remove diretórios de build anteriores"""
    dirs_to_clean = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"✅ Removido diretório: {dir_name}")

def create_exe():
    """Cria o executável usando PyInstaller"""
    
    print("🚀 Iniciando construção do executável...")
    
    # Limpa builds anteriores
    clean_build_dirs()
    
    # Configurações do PyInstaller
    pyinstaller_args = [
        'pyinstaller',
        '--onefile',  # Arquivo único
        '--windowed',  # Interface gráfica (sem console)
        '--name=Matriculas_Confrontantes_PGE_MS',  # Nome do executável
        '--add-data=matrículas;matrículas',  # Inclui pasta de PDFs exemplo
        '--hidden-import=PIL._tkinter_finder',  # Import implícito necessário
        '--hidden-import=requests',
        '--hidden-import=matplotlib',
        '--hidden-import=fitz',  # PyMuPDF
        '--hidden-import=pdf2image',
        '--hidden-import=dotenv',
        '--collect-all=matplotlib',  # Coleta todos os arquivos do matplotlib
        '--collect-all=PIL',  # Coleta todos os arquivos do Pillow
        '--exclude-module=_tkinter',  # Exclui módulo problemático
        '--debug=all',  # Debug para ver problemas
        '../main.py'
    ]
    
    try:
        print("📦 Executando PyInstaller...")
        result = subprocess.run(pyinstaller_args, check=True, capture_output=True, text=True)
        print("✅ PyInstaller executado com sucesso!")
        
        # Verifica se o executável foi criado
        exe_path = Path('dist/Matriculas_Confrontantes_PGE_MS.exe')
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"🎉 Executável criado com sucesso!")
            print(f"📁 Localização: {exe_path.absolute()}")
            print(f"📏 Tamanho: {size_mb:.1f} MB")
            
            # Cria pasta de distribuição
            dist_folder = Path('distribuicao')
            dist_folder.mkdir(exist_ok=True)
            
            # Copia executável para pasta de distribuição
            shutil.copy2(exe_path, dist_folder / 'Matriculas_Confrontantes_PGE_MS.exe')
            
            # Cria arquivo README para distribuição
            readme_content = """# Analisador de Usucapião com IA Visual - Matrículas e Confrontantes (PGE-MS)

## Como usar:

1. Execute o arquivo: Matriculas_Confrontantes_PGE_MS.exe
2. Configure sua API Key do OpenRouter no campo correspondente
3. Adicione arquivos PDF de matrículas usando o botão "Adicionar PDFs/Imagens"
4. Clique em "Processar Todos" para analisar os documentos
5. Após o processamento, forneça feedback sobre a precisão dos resultados

## Requisitos:
- Windows 10/11
- Conexão com internet para API de IA
- API Key válida do OpenRouter

## Configuração inicial:
1. Obtenha uma API Key em: https://openrouter.ai/
2. Coloque a chave no campo "API Key" da interface

## Suporte:
Este sistema foi desenvolvido para a Procuradoria-Geral do Estado de Mato Grosso do Sul (PGE-MS)
para análise automatizada de processos de usucapião.

Versão: 1.0.0
Data: Setembro 2025
"""
            
            with open(dist_folder / 'README.txt', 'w', encoding='utf-8') as f:
                f.write(readme_content)
            
            print(f"📦 Pasta de distribuição criada: {dist_folder.absolute()}")
            print("\n🎯 PRÓXIMOS PASSOS:")
            print("1. Configure o Google Forms seguindo o guia fornecido")
            print("2. Atualize as configurações GOOGLE_FORM_CONFIG no código")
            print("3. Reconstrua o executável após configurar o formulário")
            print("4. Distribua a pasta 'distribuicao' completa")
            
        else:
            print("❌ Executável não foi encontrado!")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro durante execução do PyInstaller:")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        return False
    
    return True

def create_installer_config():
    """Cria configuração para Inno Setup (opcional)"""
    inno_script = """
[Setup]
AppName=Analisador de Usucapião PGE-MS
AppVersion=1.0.0
AppPublisher=Procuradoria-Geral do Estado de MS
DefaultDirName={autopf}\\Matriculas Confrontantes PGE-MS
DefaultGroupName=PGE-MS
OutputDir=instalador
OutputBaseFilename=Setup_Matriculas_Confrontantes_PGE_MS
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\\BrazilianPortuguese.isl"

[Files]
Source: "distribuicao\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\\Analisador de Matrículas"; Filename: "{app}\\Matriculas_Confrontantes_PGE_MS.exe"
Name: "{autodesktop}\\Analisador de Matrículas PGE-MS"; Filename: "{app}\\Matriculas_Confrontantes_PGE_MS.exe"

[Run]
Filename: "{app}\\Matriculas_Confrontantes_PGE_MS.exe"; Description: "{cm:LaunchProgram,Analisador de Matrículas}"; Flags: nowait postinstall skipifsilent
"""
    
    with open('setup_config.iss', 'w', encoding='utf-8') as f:
        f.write(inno_script)
    
    print("📄 Arquivo de configuração do Inno Setup criado: setup_config.iss")

if __name__ == "__main__":
    print("🏗️ Build System - Analisador de Matrículas Confrontantes")
    print("=" * 60)
    
    success = create_exe()
    
    if success:
        create_installer_config()
        print("\n✅ Build concluído com sucesso!")
        print("\nPara criar um instalador profissional:")
        print("1. Instale o Inno Setup: https://jrsoftware.org/isinfo.php")
        print("2. Abra o arquivo: setup_config.iss")
        print("3. Compile para gerar o instalador")
    else:
        print("\n❌ Build falhou!")
        sys.exit(1)
