@echo off
rem タスクスケジューラから毎日実行されるスクリプト
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python update_data.py >> update_log.txt 2>&1

rem 更新データをGitHubへpush（リポジトリ設定済みの場合のみ・サイトに自動反映）
git rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel%==0 (
  git add data index.html js css robots.txt sitemap.xml README.md >> update_log.txt 2>&1
  git commit -m "daily data update" >> update_log.txt 2>&1
  git push >> update_log.txt 2>&1
)
