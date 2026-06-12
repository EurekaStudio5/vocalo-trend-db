@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo データを更新しています（数分かかります）...
python update_data.py
echo.
echo 更新完了！
pause
