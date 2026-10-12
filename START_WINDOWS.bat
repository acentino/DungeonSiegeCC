@echo off
cd /d "%~dp0"
py -3 importer.py
if errorlevel 1 pause
