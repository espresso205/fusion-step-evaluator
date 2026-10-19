@echo off
setlocal
set "EVALUATOR_PYTHON=%FUSION_STEP_PYTHON%"
if defined EVALUATOR_PYTHON goto configured
if exist "%~dp0runtime\python\python.exe" set "EVALUATOR_PYTHON=%~dp0runtime\python\python.exe"
if not defined EVALUATOR_PYTHON set "EVALUATOR_PYTHON=python"
:configured
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
"%EVALUATOR_PYTHON%" -B "%~dp0mcp_server.py" %*
exit /b %ERRORLEVEL%
