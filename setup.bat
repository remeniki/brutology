@echo off
rem Vytvori prostredie a nainstaluje kniznice. Vystup sa ulozi do data\logs\last_output.txt
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath 'data\logs\last_output.txt'"
pause
