@echo off
cd /d %~dp0
call venv\Scripts\activate
python assistant.py
echo.
echo Script finished. Press any key to exit.
pause
