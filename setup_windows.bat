@echo off
chcp 65001 > nul
where python >nul 2>nul
if errorlevel 1 (
  echo Pythonが見つかりません。Python 3をインストールしてください。
  pause
  exit /b 1
)
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m pytest
echo.
echo セットアップが完了しました。run_app.bat を実行してください。
pause
