@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" main.py >> bot_stdout.log 2>&1
