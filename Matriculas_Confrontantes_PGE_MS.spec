# -*- mode: python ; coding: utf-8 -*-
# Configuração PyInstaller para o sistema de auto-atualização

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('VERSION', '.'),  # Inclui arquivo VERSION no executável
        ('.env', '.'),     # Inclui arquivo .env se existir
    ],
    hiddenimports=[
        'packaging.version',  # Necessário para updater.py
        'requests',
        'urllib.parse',
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Adicione um ícone aqui se desejar: icon='icon.ico'
)
