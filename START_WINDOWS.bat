@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0importer.py" (
  echo ERROR: importer.py is missing from %~dp0
  echo Download the complete DungeonSiegeCC repository instead of individual files.
  pause
  exit /b 1
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0importer.py"
) else (
  python "%~dp0importer.py"
)
if errorlevel 1 pause
