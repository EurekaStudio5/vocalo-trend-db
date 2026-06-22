@echo off
rem Daily auto-update for Vocalo Trend DB (run by Task Scheduler)
rem Uses absolute paths so it works even when PATH is minimal under the scheduler.
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set "PY=C:\Users\USER\AppData\Local\Programs\Python\Python312\python.exe"
set "GIT=C:\Users\chela\Git\cmd\git.exe"

echo ==== START %DATE% %TIME% ==== >> update_log.txt

rem 1) collect fresh data
"%PY%" update_data.py >> update_log.txt 2>&1

rem 2) publish to GitHub Pages (commit + push the deploy files)
"%GIT%" rev-parse --is-inside-work-tree >nul 2>&1
if %errorlevel%==0 (
  "%GIT%" add data index.html js css robots.txt sitemap.xml README.md >> update_log.txt 2>&1
  "%GIT%" commit -m "daily data update" >> update_log.txt 2>&1
  "%GIT%" push >> update_log.txt 2>&1
)

echo ==== DONE  %DATE% %TIME% ==== >> update_log.txt
