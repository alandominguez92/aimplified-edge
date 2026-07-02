@echo off
REM One-click save: stage everything, commit, and push to GitHub.
REM   Double-click it, or run:  save.cmd "your message"
cd /d "%~dp0"

git add -A
if "%~1"=="" (
  git commit -m "update %date% %time%"
) else (
  git commit -m "%~1"
)
git push

echo.
echo Done. Press any key to close.
pause >nul
