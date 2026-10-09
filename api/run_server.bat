@echo off
REM Starts the Smart OMR Evaluator API so phones on the LAN can reach it.
REM
REM Runs via the system Python 3.11 interpreter (not venv\Scripts\python.exe)
REM pointed at the venv's installed packages, because that interpreter
REM already has a Windows Firewall "Allow" rule for the Public network
REM profile. The venv's own python.exe does not, and this machine's WiFi is
REM classified Public -- Windows then drops inbound phone connections to it
REM silently (no error here, the phone just times out). Changing that needs
REM an admin-elevated firewall rule; this sidesteps needing one at all.
set PYTHONPATH=%~dp0venv\Lib\site-packages
"C:\users\henit\appdata\local\programs\python\python311\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
