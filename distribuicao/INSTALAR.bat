@echo off
echo =============================================================================
echo     INSTALADOR - Analisador de Matriculas Confrontantes PGE-MS
echo =============================================================================
echo.
echo Este script instalara o sistema no seu computador.
echo.
pause

:: Criar pasta no Arquivos de Programas
set "INSTALL_DIR=%ProgramFiles%\PGE-MS\Analisador Matriculas"
echo Criando pasta de instalacao: %INSTALL_DIR%
mkdir "%INSTALL_DIR%" 2>nul

:: Copiar arquivos
echo Copiando arquivos...
copy "Matriculas_Confrontantes_PGE_MS.exe" "%INSTALL_DIR%\" >nul
copy "README.txt" "%INSTALL_DIR%\" >nul
copy "exemplo.env" "%INSTALL_DIR%\" >nul
copy "GUIA_GOOGLE_FORMS_FEEDBACK.md" "%INSTALL_DIR%\" >nul

:: Criar atalho na area de trabalho
echo Criando atalho na area de trabalho...
set "SHORTCUT=%USERPROFILE%\Desktop\Analisador Matriculas PGE-MS.lnk"
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%INSTALL_DIR%\Matriculas_Confrontantes_PGE_MS.exe'; $Shortcut.Save()"

:: Criar atalho no menu iniciar
echo Criando atalho no menu iniciar...
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"
set "SHORTCUT_START=%START_MENU%\Analisador Matriculas PGE-MS.lnk"
powershell "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT_START%'); $Shortcut.TargetPath = '%INSTALL_DIR%\Matriculas_Confrontantes_PGE_MS.exe'; $Shortcut.Save()"

echo.
echo =============================================================================
echo                               INSTALACAO CONCLUIDA!
echo =============================================================================
echo.
echo O sistema foi instalado em: %INSTALL_DIR%
echo.
echo Atalhos criados:
echo - Area de trabalho: Analisador Matriculas PGE-MS
echo - Menu iniciar: Analisador Matriculas PGE-MS
echo.
echo PROXIMOS PASSOS:
echo 1. Obtenha uma API Key em: https://openrouter.ai/
echo 2. Execute o programa e configure a API Key
echo 3. Consulte o README.txt para instrucoes completas
echo.
echo Pressione qualquer tecla para executar o programa...
pause >nul

:: Executar o programa
"%INSTALL_DIR%\Matriculas_Confrontantes_PGE_MS.exe"
