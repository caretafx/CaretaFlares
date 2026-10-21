@echo off
rem Roda tools\build.bat em prioridade baixa (a maquina trava facil).
if not exist "%~dp0..\build" mkdir "%~dp0..\build"
start "" /low /b /wait cmd /c ""%~dp0build.bat" > "%~dp0..\build\build.log" 2>&1"
type "%~dp0..\build\build.log"
findstr /c:"BUILD OK" "%~dp0..\build\build.log" >nul
