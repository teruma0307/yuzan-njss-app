@echo off
chcp 65001 > nul
if not exist .venv\Scripts\activate (
  echo 先に setup_windows.bat を実行してください。
  pause
  exit /b 1
)
call .venv\Scripts\activate
streamlit run app.py
pause
