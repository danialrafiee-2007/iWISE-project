@echo off
rem Truth Guardian with the plain HTML front end (src\truth_guardian\web\static_html), next to the React one.
rem Same models, same API, same options as TruthGuardian.bat; only the pages differ.
rem   TruthGuardian-HTML.bat           start it on http://127.0.0.1:8766 and open the browser
rem   TruthGuardian-HTML.bat --port N  another port
rem It uses port 8766, not 8765, so it never opens the React app by mistake and both can run at once.

setlocal EnableExtensions DisableDelayedExpansion
set "TG_UI=html"
echo.
echo   HTML front end
call "%~dp0TruthGuardian.bat" --port 8766 %*
set "RC=%errorlevel%"
if "%RC%"=="0" goto end
echo %cmdcmdline% | find /i "%~nx0" >nul && pause
:end
endlocal & exit /b %RC%
