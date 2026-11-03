@echo off
rem Truth Guardian launcher for Windows.
rem   TruthGuardian.bat         start the web app (offline) and open the browser
rem   TruthGuardian.bat setup   once, with internet: install and download everything into this folder
rem   TruthGuardian.bat check   show what is present and what is missing
rem   TruthGuardian.bat test    run the test suite
rem   TruthGuardian.bat smoke   end-to-end check of the web app against the real models
rem   TruthGuardian.bat help    this help
rem Options: --port N (default 8765), --no-browser
rem
rem Everything the app needs is kept inside this folder (uv, Python, the package cache and the language models in
rem runtime\), so after one setup the whole folder can be copied to another Windows computer and run offline there.

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Truth Guardian
set "RUNTIME=%CD%\runtime"
set "UV_CACHE_DIR=%RUNTIME%\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%RUNTIME%\python"
set "UV_MANAGED_PYTHON=1"
set "UV_PYTHON_INSTALL_BIN=0"
set "UV_PYTHON_INSTALL_REGISTRY=0"
set "HF_HOME=%RUNTIME%\hf"
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
call :env_check || goto fail
if "%NEED_ENV%"=="1" call :env_build || goto fail
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
call :step 1 "Python and packages, kept in runtime" "call :env_setup" || goto fail
set "HAVE_RAW=0"
if exist "data\raw\nltk_data\corpora\wordnet" if exist "data\raw\ragtruth\response.jsonl" set "HAVE_RAW=1"
if "%HAVE_RAW%"=="1" (call :skip 2 "Datasets and WordNet") else (call :step 2 "Datasets and WordNet (checksums verified)" "uv run --offline python scripts\download_data.py" || goto fail)
if exist "data\processed\ragtruth_dev.jsonl" (call :skip 3 "Processed datasets") else (call :step 3 "Processed datasets" "uv run --offline python scripts\build_data.py" || goto fail)
if exist "data\processed\perturb_dev.jsonl" (call :skip 4 "Fool-the-Guardian suite") else (call :step 4 "Fool-the-Guardian suite" "uv run --offline python scripts\build_perturbations.py" || goto fail)
if exist "data\processed\tg_agent_dev.jsonl" (call :skip 5 "TG-Agent trajectories") else (call :step 5 "TG-Agent trajectories" "uv run --offline python scripts\build_tg_agent.py" || goto fail)
if exist "models\onnx\hhem-de9a5e6b.onnx" (call :skip 6 "Fast HHEM (ONNX export)") else (call :step 6 "Fast HHEM (ONNX export, a few minutes)" "uv run --offline python scripts\export_onnx.py" || echo   %WARN%ONNX export failed; the app still runs, about a third slower.%R%)
set "MODELS_MISSING=0"
call :step 7 "Models for sound, images and languages (4.5 GB, checksums verified)" "uv run --offline python scripts\fetch_media_models.py" || (set "MODELS_MISSING=1" & echo   %WARN%Some of these models could not be downloaded; run setup again to continue.%R%)
call :step 8 "Language models, warm-up and example cache" "uv run --offline python -m truth_guardian.web --prepare" || goto fail
echo.
echo   %B%Final check (offline)%R%
uv run --offline --quiet python -m truth_guardian.web --check || goto fail
echo.
if "%MODELS_MISSING%"=="1" goto setup_partial
echo   %OK%Setup complete.%R% From now on just double-click %B%TruthGuardian.bat%R%; no internet is needed.
echo   %DIM%The whole folder, runtime included, can be copied to another Windows computer and runs there offline.%R%
goto done

:setup_partial
echo   %WARN%Setup is not finished:%R% some models could not be downloaded, so the check above lists what will not work yet.
echo   %DIM%Run setup again with internet; it fetches only what is missing.%R%
if "%PAUSE_AT_END%"=="1" pause
endlocal
exit /b 2

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
echo   %B%TruthGuardian.bat setup%R%   once, with internet: install and download everything into this folder
echo   %B%TruthGuardian.bat check%R%   show what is present and what is missing
echo   %B%TruthGuardian.bat test%R%    run the test suite
echo   %B%TruthGuardian.bat smoke%R%   end-to-end check of the web app against the real models
echo.
echo   Options: %B%--port N%R% (default 8765), %B%--no-browser%R%
echo   Example: TruthGuardian.bat --port 8780 --no-browser
goto done

rem ---------------------------------------------------------------------------------------------------------------
:find_uv
if exist "%RUNTIME%\uv\uv.exe" (set "PATH=%RUNTIME%\uv;%PATH%" & exit /b 0)
where uv >nul 2>&1 && exit /b 0
if exist "%USERPROFILE%\.local\bin\uv.exe" (set "PATH=%USERPROFILE%\.local\bin;%PATH%" & exit /b 0)
if exist "%USERPROFILE%\.cargo\bin\uv.exe" (set "PATH=%USERPROFILE%\.cargo\bin;%PATH%" & exit /b 0)
echo %ERR%uv is not installed.%R% It manages Python and the packages for this project. Install it once, then run TruthGuardian.bat setup:
echo     winget install --id=astral-sh.uv -e
echo   or see https://docs.astral.sh/uv/getting-started/installation/
exit /b 1

:env_check
rem The Python environment (.venv) holds absolute paths. When it was built in another folder (the project was copied
rem or moved) or no longer runs, it is removed and NEED_ENV=1 asks for a rebuild for this folder.
set "NEED_ENV=0"
set "BUILT_IN="
if exist ".venv\built-in.txt" set /p BUILT_IN=<".venv\built-in.txt"
if /i "%BUILT_IN%"=="%CD%" if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "" >nul 2>&1 && exit /b 0
set "NEED_ENV=1"
rem uv links the Python minor version to its install with a junction, an absolute path that points back into the old
rem folder after a copy; without it uv uses the install itself. rmdir removes the link only, never what it points to.
for /f "delims=" %%d in ('dir /a:l /b "%RUNTIME%\python" 2^>nul') do rmdir "%RUNTIME%\python\%%d"
for /d %%d in ("%RUNTIME%\python\cpython-*") do if not exist "%%d\python.exe" rmdir "%%d" 2>nul
if not exist ".venv" exit /b 0
rmdir /s /q ".venv"
if not exist ".venv" exit /b 0
echo %ERR%The old .venv folder could not be removed.%R% Close the programs that use it, then try again.
exit /b 1

:env_build
if not exist "%RUNTIME%\uv-cache" (
  echo %WARN%This computer is not set up yet.%R% Run %B%TruthGuardian.bat setup%R% once with internet, then TruthGuardian.bat again.
  exit /b 1
)
echo   %DIM%First start in this folder: building its Python environment offline from runtime, about a minute...%R%
uv sync --offline --frozen --quiet
if errorlevel 1 (
  echo %ERR%The Python environment could not be built offline.%R% Copy the whole folder including runtime, or run %B%TruthGuardian.bat setup%R% once with internet.
  exit /b 1
)
>".venv\built-in.txt" echo %CD%
exit /b 0

:env_setup
call :env_check || exit /b 1
uv sync --inexact --offline --quiet >nul 2>&1 || uv sync --inexact || exit /b 1
>".venv\built-in.txt" echo %CD%
if exist "%RUNTIME%\uv\uv.exe" exit /b 0
rem keep the uv that built the package cache next to it, so another computer needs no uv of its own
for /f "delims=" %%u in ('where uv 2^>nul') do (
  if not exist "%RUNTIME%\uv" mkdir "%RUNTIME%\uv"
  copy /y "%%u" "%RUNTIME%\uv\uv.exe" >nul || exit /b 1
  exit /b 0
)
exit /b 1

:step
echo   %TEAL%[%~1/8]%R% %~2
%~3
rem No block here: a bracket in a step's name would end it early and every step would look failed.
if not errorlevel 1 goto step_ok
echo   %ERR%Step %~1 failed:%R% %~2
exit /b 1
:step_ok
echo   %OK%done%R%
exit /b 0

:skip
echo   %TEAL%[%~1/8]%R% %~2 %DIM%(already there)%R%
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
