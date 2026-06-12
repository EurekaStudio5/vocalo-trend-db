@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ボカロトレンドDB を起動しています...
start "" http://localhost:8765
python -m http.server 8765
