@echo off
rem One file for a new Windows computer: downloads the project and its models, installs everything and starts the app.
rem   Install-Truth-Guardian.bat              everything goes into a folder named TruthGuardian next to this file
rem   Install-Truth-Guardian.bat --no-setup   only the downloads, for testing this file
rem Stopped or failed? Run it again: what is done is skipped and broken downloads resume.

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title Truth Guardian installer
set "TARGET=%CD%\TruthGuardian"
set "REPO=https://github.com/danialrafiee-2007/iWISE-project"
if not defined TG_SOURCE_ZIP set "TG_SOURCE_ZIP=%REPO%/archive/refs/heads/main.zip"
if not defined TG_RELEASE set "TG_RELEASE=%REPO%/releases/download/word-detector-v1"
if not defined TG_UV_ZIP set "TG_UV_ZIP=https://github.com/astral-sh/uv/releases/download/0.13.5/uv-x86_64-pc-windows-msvc.zip"
set "UV_SHA=a38b8d1902b7cfbc76b423ba1bb456f623f42064cdc72628b6075b89afd1019a"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"
set "NEED_GB=15"

echo.
echo   Truth Guardian installer
echo   Downloads the project and its models, installs them into the folder below and starts the app.
echo   It needs internet and about %NEED_GB% GB of free space, and can take a long time on the first run.
echo   Folder: %TARGET%
echo.

if not exist "%CURL%" goto old_windows
if not exist "%TAR%" goto old_windows
set "NON_LATIN=0"
for /f %%n in ('powershell -NoProfile -Command "[int]($env:TARGET -match '[^\x00-\x7F]')"') do set "NON_LATIN=%%n"
if "%NON_LATIN%"=="1" goto non_latin_path

if exist "%TARGET%\.venv" goto space_ok
set "FREE_GB="
for /f %%g in ('powershell -NoProfile -Command "[math]::Floor((New-Object IO.DriveInfo((Get-Location).Drive.Name)).AvailableFreeSpace/1GB)"') do set "FREE_GB=%%g"
if not defined FREE_GB goto space_ok
if %FREE_GB% GEQ %NEED_GB% goto space_ok
echo   Only %FREE_GB% GB is free on this drive. Move this file to a drive with at least %NEED_GB% GB free and run it again.
goto fail
:space_ok

if not exist "%TARGET%" mkdir "%TARGET%"
if not exist "%TARGET%\runtime\uv" mkdir "%TARGET%\runtime\uv"

echo   [1/5] Project source
if exist "%TARGET%\TruthGuardian.bat" goto source_done
if exist "%TARGET%\code.zip" del "%TARGET%\code.zip"
call :fetch "%TG_SOURCE_ZIP%" "%TARGET%\code.zip" "" || goto fail
"%TAR%" -xf "%TARGET%\code.zip" -C "%TARGET%" --strip-components=1 || goto bad_zip
if not exist "%TARGET%\TruthGuardian.bat" goto bad_zip
del "%TARGET%\code.zip"
:source_done
echo         done

echo   [2/5] uv, which installs Python and the packages
if exist "%TARGET%\runtime\uv\uv.exe" goto uv_done
call :fetch "%TG_UV_ZIP%" "%TARGET%\uv.zip" "%UV_SHA%" || goto fail
"%TAR%" -xf "%TARGET%\uv.zip" -C "%TARGET%\runtime\uv" || goto bad_zip
del "%TARGET%\uv.zip"
:uv_done
echo         done

echo   [3/5] The text section's models
call :model truth-guardian-word-detector.zip 58989703e2480b12fc981687f57b4ec31698df422faff612a11aea8ebf3c5206 || goto fail
call :model truth-guardian-hhem-fast.zip fc632fe4bbbc7bf80970a9969df87bcce31ada52e791141d378c6ffb656e043c || goto fail
call :model truth-guardian-reader-e5.zip 903ac3f0791e8aa4e4627095ecf7bc25b774b4524726230ce9e530ee3dde861f || goto fail
call :model truth-guardian-reader-nli.zip f512ff609ab956e9c66f310ba1b1751f032e810c87d39ff132597287bd1785f7 || goto fail
echo         done

if /i "%~1"=="--no-setup" goto finished_downloads

echo   [4/5] Python, packages, data and the other models
call "%TARGET%\TruthGuardian.bat" setup
set "SETUP_RC=%errorlevel%"
if not "%SETUP_RC%"=="0" if not "%SETUP_RC%"=="2" goto fail

echo   [5/5] Starting the app
start "Truth Guardian" "%TARGET%\TruthGuardian.bat"
echo.
if "%SETUP_RC%"=="2" goto partly_done
echo   Done. The app opens in its own window and in your browser, about a minute from now.
echo   Next time just double-click TruthGuardian.bat in the folder above; it needs no internet.
timeout /t 15 >nul 2>&1
endlocal
exit /b 0

:partly_done
echo   The app opens in its own window, but some models for sound, images or other languages are still missing.
echo   Run this file again with a steady connection: only what is missing is downloaded.
echo.
pause
endlocal
exit /b 0

:finished_downloads
echo   Downloads finished; setup skipped.
endlocal
exit /b 0

rem ---------------------------------------------------------------------------------------------------------------
:model
rem %~1 zip in the release, %~2 its SHA-256. A mark in runtime says it was opened to the end.
if exist "%TARGET%\runtime\opened-%~1.txt" exit /b 0
echo         %~1
call :fetch "%TG_RELEASE%/%~1" "%TARGET%\%~1" "%~2" || exit /b 1
"%TAR%" -xf "%TARGET%\%~1" -C "%TARGET%" || goto bad_zip_sub
>"%TARGET%\runtime\opened-%~1.txt" echo %~2
del "%TARGET%\%~1"
exit /b 0

:bad_zip_sub
echo   %~1 could not be opened. Check the free space and run this file again.
del "%TARGET%\%~1"
exit /b 1

:fetch
rem %~1 address, %~2 file, %~3 its SHA-256, or empty when it has none. Resumes a part already there. A try that brought
rem more bytes does not count, and a stalled connection is dropped after a minute, so a shaky link still finishes.
set "TRIES=0"
if "%~3"=="" goto fetch_try
call :hash_ok "%~2" "%~3" && exit /b 0
:fetch_try
set /a TRIES+=1
set "HAD="
if exist "%~2" for %%f in ("%~2") do set "HAD=%%~zf"
"%CURL%" -L --fail --progress-bar --connect-timeout 30 --speed-limit 1024 --speed-time 60 -C - -o "%~2" "%~1"
set "RC=%errorlevel%"
if "%RC%"=="22" goto fetch_refused
if "%RC%"=="33" goto fetch_refused
if not "%RC%"=="0" goto fetch_retry
if "%~3"=="" exit /b 0
call :hash_ok "%~2" "%~3" && exit /b 0
echo         The download did not match its checksum; fetching it again.
del "%~2"
goto fetch_retry
:fetch_refused
rem A part that cannot be resumed is refused too, so one clean try before giving up.
if not exist "%~2" goto fetch_not_found
del "%~2"
:fetch_retry
set "HAS="
if exist "%~2" for %%f in ("%~2") do set "HAS=%%~zf"
if defined HAS if not "%HAS%"=="%HAD%" set "TRIES=0"
if %TRIES% GEQ 10 goto fetch_gave_up
timeout /t 30 >nul 2>&1
goto fetch_try
:fetch_not_found
echo.
echo   The server refused this address: %~1
echo   If the repository is private, you need access to it. Ask the team for the public link.
exit /b 1
:fetch_gave_up
echo.
echo   Could not download: %~1
echo   Check the internet connection, or try a VPN.
exit /b 1

:hash_ok
if not exist "%~1" exit /b 1
set "TG_FILE=%~1"
set "GOT="
for /f %%h in ('powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:TG_FILE -Algorithm SHA256).Hash"') do set "GOT=%%h"
if /i "%GOT%"=="%~2" exit /b 0
exit /b 1

:bad_zip
echo   A downloaded file could not be opened. Check the free space and run this file again.
if exist "%TARGET%\code.zip" del "%TARGET%\code.zip"
if exist "%TARGET%\uv.zip" del "%TARGET%\uv.zip"
goto fail

:old_windows
echo   This needs Windows 10 version 1803 or newer, which include curl and tar.
goto fail

:non_latin_path
echo   This folder's path has non-Latin letters, which tar and the models' libraries cannot read.
echo   Move this file to a folder such as D:\TG and run it again.
goto fail

:fail
echo.
echo   Not finished. Run this file again: what is done is skipped and broken downloads resume.
echo.
pause
endlocal
exit /b 1
