@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "%~dp0runtime" mkdir "%~dp0runtime"
set "LAUNCH_LOG=%~dp0runtime\launcher.log"
>"%LAUNCH_LOG%" echo [%date% %time%] Starting Codex Desktop Pet

where python.exe >nul 2>&1
if errorlevel 1 goto :no_python

for %%I in (python.exe) do set "PYTHON_EXE=%%~$PATH:I"
"%PYTHON_EXE%" -c "import PyQt5, win32api" >>"%LAUNCH_LOG%" 2>&1
if errorlevel 1 goto :missing_dependencies

for %%I in ("%PYTHON_EXE%") do set "PYTHONW_EXE=%%~dpIpythonw.exe"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%PYTHON_EXE%"

>>"%LAUNCH_LOG%" echo Python: %PYTHON_EXE%
start "Codex Desktop Pet" /b "%PYTHONW_EXE%" "%~dp0app.py" >>"%LAUNCH_LOG%" 2>&1
if errorlevel 1 goto :launch_failed
exit /b 0

:no_python
>>"%LAUNCH_LOG%" echo ERROR: python.exe was not found in PATH.
goto :show_error

:missing_dependencies
>>"%LAUNCH_LOG%" echo ERROR: PyQt5 or pywin32 is missing from %PYTHON_EXE%.
goto :show_error

:launch_failed
>>"%LAUNCH_LOG%" echo ERROR: Failed to create the desktop pet process.

:show_error
start "Codex Desktop Pet - startup error" cmd.exe /k "echo Codex Desktop Pet could not start. ^& echo. ^& type "%LAUNCH_LOG%" ^& echo. ^& echo Install dependencies with: python -m pip install -r "%~dp0requirements.txt""
exit /b 1

