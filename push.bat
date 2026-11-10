@echo off
rem Posle commity na GitHub. Vystup sa ulozi do data\logs\last_output.txt
cd /d %~dp0
git push 2>&1 | powershell -NoProfile -Command "$input | Tee-Object -FilePath 'data\logs\last_output.txt'"
pause
