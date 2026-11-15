@echo off
rem Starts the Armory editor on this PC only (127.0.0.1) and opens your browser. Close this window to stop it.
cd /d "%~dp0"
where python >nul 2>nul && (python server.py) || (py -3 server.py)
pause
