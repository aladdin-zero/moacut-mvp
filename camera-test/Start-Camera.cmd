@echo off
cd /d "%~dp0.."
"%~dp0..\.venv-ai\Scripts\python.exe" "%~dp0server.py" --open
pause
