@echo off
rem Spusti grafy v prehliadaci
cd /d %~dp0
call .venv\Scripts\activate
streamlit run app\dashboard.py
pause
