# -*- mode: python ; coding: utf-8 -*-
# Configuração PyInstaller para o sistema de auto-atualização

import os

# Constrói lista de datas condicionalmente
datas = [('../VERSION', '.')]  # Arquivo VERSION é obrigatório

# Adiciona .env apenas se existir
if os.path.exists('../.env'):
    datas.append(('../.env', '.'))

# Adiciona arquivos de documentação do feedback
if os.path.exists('../config/.env.example'):
    datas.append(('../config/.env.example', '.'))
if os.path.exists('../docs/FEEDBACK_SETUP.md'):
    datas.append(('../docs/FEEDBACK_SETUP.md', '.'))

# Adiciona módulos do sistema como dados
if os.path.exists('../src/updater.py'):
    datas.append(('../src/updater.py', '.'))
if os.path.exists('../src/feedback_system.py'):
    datas.append(('../src/feedback_system.py', '.'))

a = Analysis(
    ['../src/main.py'],
    pathex=['../src'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'packaging.version',  # Necessário para updater.py
        'requests',
        'urllib.parse',
        'fitz',  # PyMuPDF
        'PIL',
        'PIL.Image',
        'pdf2image',
        'pdf2image.utils',
        'docx',
        'docx.document',
        'docx.shared',
        'docx.oxml.ns',
        'docx.enum.text',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib.pagesizes',
        'reportlab.lib.styles',
        'reportlab.platypus',
        'reportlab.lib.enums',
        'dotenv',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.font',
        'threading',
        'queue',
        'json',
        'base64',
        'tempfile',
        'subprocess',
        'pathlib',
        'dataclasses',
        'datetime',
        'textwrap',
        'csv',
        # Módulos do sistema
        'updater',
        'feedback_system',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RelatorioTJMS',  # Nome padrão para o executável
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Adicione um ícone aqui se desejar: icon='icon.ico'
)
