@echo off
rem Gerald bridge daemon for Windows (autostart via Task Scheduler, see README).
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" -m bridge.daemon
