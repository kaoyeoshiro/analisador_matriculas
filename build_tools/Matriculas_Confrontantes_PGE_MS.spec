# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

# Tenta incluir pasta de matrículas se existir (opcional para desenvolvimento)
datas = []
matriculas_path = os.path.join('..', 'matrículas')
if os.path.exists(matriculas_path):
    datas.append((matriculas_path, 'matrículas'))

binaries = []
hiddenimports = ['PIL._tkinter_finder', 'requests', 'fitz', 'pdf2image', 'dotenv']

# Coleta dependências do PIL (essencial)
try:
    tmp_ret = collect_all('PIL')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except:
    pass

# Matplotlib e EasyOCR são opcionais - não falhar se não encontrados
try:
    tmp_ret = collect_all('matplotlib')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except:
    pass

try:
    tmp_ret = collect_all('easyocr')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except:
    pass


a = Analysis(
    ['..\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['_tkinter'],
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
    name='Matriculas_Confrontantes_PGE_MS',
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
    version='version_info.txt',
    icon=None,
    uac_admin=False,
    uac_uiaccess=False,
)
