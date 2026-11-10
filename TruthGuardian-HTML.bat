@echo off
rem Truth Guardian full screen on its own port: the same site TruthGuardian.bat serves (src\truth_guardian\web\static_html).
rem Same models, same API, same options as TruthGuardian.bat.
rem   TruthGuardian-HTML.bat           start it on http://127.0.0.1:8766 and open it full screen
rem   TruthGuardian-HTML.bat --port N  another port
rem It uses port 8766, so it can run beside TruthGuardian.bat (port 8765), which serves the same site (D-214).
rem The site opens full screen, like a film, as soon as the server answers (scripts\open_fullscreen.ps1): Chrome or
rem Edge as an app window with no address bar or tabs. F11 leaves full screen, Alt+F4 closes it. --no-browser opens
rem nothing; setup, check, test and smoke open nothing either.

setlocal EnableExtensions DisableDelayedExpansion
set "TG_UI=html"
rem The folder of this file, kept before the options are read: shift moves %0 too, so %~dp0 would change.
set "HERE=%~dp0"
set "PORT=8766"
set "OPEN=1"
set "PASS="
:args
if "%~1"=="" goto args_done
if /i "%~1"=="--no-browser" set "OPEN=0"
if /i "%~1"=="setup" set "OPEN=0"
if /i "%~1"=="check" set "OPEN=0"
if /i "%~1"=="test" set "OPEN=0"
if /i "%~1"=="smoke" set "OPEN=0"
if /i "%~1"=="help" set "OPEN=0"
if /i "%~1"=="--port" set "PORT=%~2"
set PASS=%PASS% %1
shift
goto args
:args_done

echo.
echo   HTML front end, full screen
if "%OPEN%"=="1" start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%HERE%scripts\open_fullscreen.ps1" -Port %PORT%
call "%HERE%TruthGuardian.bat" --port 8766 --no-browser%PASS%
set "RC=%errorlevel%"
if "%RC%"=="0" goto end
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
:end
endlocal & exit /b %RC%
