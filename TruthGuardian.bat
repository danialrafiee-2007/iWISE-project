@echo off
rem Truth Guardian launcher for Windows.
rem   TruthGuardian.bat         start the web app (offline) and open the browser
rem   TruthGuardian.bat setup   first time on a computer: install and download everything (needs internet once)
rem   TruthGuardian.bat check   show what is present and what is missing
rem   TruthGuardian.bat test    run the test suite
rem   TruthGuardian.bat smoke   end-to-end check of the web app against the real models
rem   TruthGuardian.bat help    this help
rem Options: --port N (default 8765), --no-browser

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Truth Guardian
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "TRANSFORMERS_VERBOSITY=error"
set "HF_HUB_DISABLE_PROGRESS_BARS=1"
set "HF_HUB_VERBOSITY=error"
set "TOKENIZERS_PARALLELISM=false"

for /f %%e in ('echo prompt $E^| cmd') do set "ESC=%%e"
set "B=%ESC%[1m"
set "DIM=%ESC%[90m"
set "OK=%ESC%[92m"
set "WARN=%ESC%[93m"
set "ERR=%ESC%[91m"
set "TEAL=%ESC%[96m"
set "R=%ESC%[0m"

set "MODE=start"
set "PORT=8765"
set "BROWSER="
set "PAUSE_AT_END=0"
echo %cmdcmdline% | find /i "%~nx0" >nul && set "PAUSE_AT_END=1"

:parse
if "%~1"=="" goto parsed
if /i "%~1"=="setup" (set "MODE=setup" & shift & goto parse)
if /i "%~1"=="check" (set "MODE=check" & shift & goto parse)
if /i "%~1"=="test" (set "MODE=test" & shift & goto parse)
if /i "%~1"=="smoke" (set "MODE=smoke" & shift & goto parse)
if /i "%~1"=="help" (set "MODE=help" & shift & goto parse)
if /i "%~1"=="-h" (set "MODE=help" & shift & goto parse)
if /i "%~1"=="/?" (set "MODE=help" & shift & goto parse)
if /i "%~1"=="--no-browser" (set "BROWSER=--no-browser" & shift & goto parse)
if /i "%~1"=="--port" (set "PORT=%~2" & shift & shift & goto parse)
echo %ERR%Unknown option: %~1%R%
set "MODE=help"
shift
goto parse
:parsed

set /a "PORT_NUM=%PORT%" 2>nul
if not "%PORT_NUM%"=="%PORT%" (
  echo %ERR%--port needs a number, got "%PORT%".%R%
  goto fail
)
if %PORT% LSS 1024 (echo %ERR%Choose a port from 1024 to 65535.%R% & goto fail)
if %PORT% GTR 65535 (echo %ERR%Choose a port from 1024 to 65535.%R% & goto fail)

echo.
echo   %TEAL%%B%Truth Guardian%R%  %DIM%hallucination detection for RAG and agent answers . iWISE 2026, AI Challenge 4%R%
echo.

if /i "%MODE%"=="help" goto help
call :find_uv || goto fail
if /i "%MODE%"=="setup" goto setup
if /i "%MODE%"=="check" goto check
if /i "%MODE%"=="test" goto test
if /i "%MODE%"=="smoke" goto smoke
goto start

rem ---------------------------------------------------------------------------------------------------------------
:start
if not exist ".venv\Scripts\python.exe" (
  echo %WARN%This computer is not set up yet.%R% Run %B%TruthGuardian.bat setup%R% once with internet, then TruthGuardian.bat again.
  goto fail
)
set "CODE="
for /f %%c in ('curl.exe -s -m 2 -o nul -w "%%{http_code}" http://127.0.0.1:%PORT%/api/health 2^>nul') do set "CODE=%%c"
if "%CODE%"=="200" (
  echo   %OK%Already running%R% on http://127.0.0.1:%PORT%
  if not defined BROWSER start "" "http://127.0.0.1:%PORT%"
  goto done
)
netstat -ano -p tcp | findstr /r /c:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo %ERR%Port %PORT% is used by another program.%R% Start on another port, for example: %B%TruthGuardian.bat --port 8780%R%
  goto fail
)
echo   %DIM%Checking the models and data...%R%
uv run --offline --quiet python -m truth_guardian.web --check
if errorlevel 1 (
  echo.
  echo %ERR%Something required is missing.%R% Run %B%TruthGuardian.bat setup%R% once with internet.
  goto fail
)
echo.
echo   %OK%Starting%R% on %B%http://127.0.0.1:%PORT%%R%
echo   %DIM%The models warm up in the background, about a minute; the page shows when they are ready.%R%
echo   %DIM%Everything runs on this computer. Keep this window open; press Ctrl+C here to stop.%R%
echo.
uv run --offline --quiet python -m truth_guardian.web --port %PORT% %BROWSER%
set "RC=%errorlevel%"
if "%RC%"=="0" goto done
if "%RC%"=="-1073741510" goto done
echo.
echo %ERR%The app stopped with an error (code %RC%).%R% The messages above say why; %B%TruthGuardian.bat check%R% lists what is missing.
goto fail

rem ---------------------------------------------------------------------------------------------------------------
:setup
echo   %B%Setting up this computer%R% %DIM%(needs internet once; safe to run again, finished steps are skipped)%R%
echo.
set "HF_HUB_OFFLINE="
call :step 1 "Python and packages" "uv sync --inexact" || goto fail
set "HAVE_RAW=0"
if exist "data\raw\nltk_data\corpora\wordnet" if exist "data\raw\ragtruth\response.jsonl" set "HAVE_RAW=1"
if "%HAVE_RAW%"=="1" (call :skip 2 "Datasets and WordNet") else (call :step 2 "Datasets and WordNet (checksums verified)" "uv run python scripts\download_data.py" || goto fail)
if exist "data\processed\ragtruth_dev.jsonl" (call :skip 3 "Processed datasets") else (call :step 3 "Processed datasets" "uv run python scripts\build_data.py" || goto fail)
if exist "data\processed\perturb_dev.jsonl" (call :skip 4 "Fool-the-Guardian suite") else (call :step 4 "Fool-the-Guardian suite" "uv run python scripts\build_perturbations.py" || goto fail)
if exist "data\processed\tg_agent_dev.jsonl" (call :skip 5 "TG-Agent trajectories") else (call :step 5 "TG-Agent trajectories" "uv run python scripts\build_tg_agent.py" || goto fail)
if exist "models\onnx\hhem-de9a5e6b.onnx" (call :skip 6 "Fast HHEM (ONNX export)") else (call :step 6 "Fast HHEM (ONNX export, a few minutes)" "uv run python scripts\export_onnx.py" || echo   %WARN%ONNX export failed; the app still runs, about a third slower.%R%)
call :step 7 "Language models, warm-up and example cache" "uv run python -m truth_guardian.web --prepare" || goto fail
echo.
echo   %B%Final check (offline)%R%
uv run --offline --quiet python -m truth_guardian.web --check || goto fail
echo.
echo   %OK%Setup complete.%R% From now on just double-click %B%TruthGuardian.bat%R%; no internet is needed.
goto done

rem ---------------------------------------------------------------------------------------------------------------
:check
uv run --offline --quiet python -m truth_guardian.web --check
if errorlevel 1 goto fail
goto done

:test
uv run --offline pytest -q
if errorlevel 1 goto fail
goto done

:smoke
uv run --offline python scripts\smoke_web.py
if errorlevel 1 goto fail
goto done

:help
echo   %B%TruthGuardian.bat%R%         start the web app offline and open the browser
echo   %B%TruthGuardian.bat setup%R%   first time on a computer: install and download everything (needs internet once)
echo   %B%TruthGuardian.bat check%R%   show what is present and what is missing
echo   %B%TruthGuardian.bat test%R%    run the test suite
echo   %B%TruthGuardian.bat smoke%R%   end-to-end check of the web app against the real models
echo.
echo   Options: %B%--port N%R% (default 8765), %B%--no-browser%R%
echo   Example: TruthGuardian.bat --port 8780 --no-browser
goto done

rem ---------------------------------------------------------------------------------------------------------------
:find_uv
where uv >nul 2>&1 && exit /b 0
if exist "%USERPROFILE%\.local\bin\uv.exe" (set "PATH=%USERPROFILE%\.local\bin;%PATH%" & exit /b 0)
if exist "%USERPROFILE%\.cargo\bin\uv.exe" (set "PATH=%USERPROFILE%\.cargo\bin;%PATH%" & exit /b 0)
echo %ERR%uv is not installed.%R% It manages Python and the packages for this project. Install it once, then run TruthGuardian.bat setup:
echo     winget install --id=astral-sh.uv -e
echo   or see https://docs.astral.sh/uv/getting-started/installation/
exit /b 1

:step
echo   %TEAL%[%~1/7]%R% %~2
%~3
if errorlevel 1 (
  echo   %ERR%Step %~1 failed:%R% %~2
  exit /b 1
)
echo   %OK%done%R%
exit /b 0

:skip
echo   %TEAL%[%~1/7]%R% %~2 %DIM%(already there)%R%
exit /b 0

:fail
echo.
if "%PAUSE_AT_END%"=="1" pause
endlocal
exit /b 1

:done
if "%PAUSE_AT_END%"=="1" if /i not "%MODE%"=="start" pause
endlocal
exit /b 0
