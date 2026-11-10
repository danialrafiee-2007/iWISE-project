@echo off
rem Truth Guardian: download the whole project and run it, with one double-click (D-213).
rem
rem It asks which drive to use, makes the folder "iWISE_Truth Guardian" there and downloads the latest ready-made package
rem from the project's GitHub Releases: the whole source code with its tests and documents, Python with every package,
rem and every model (the Guardian's, the word detector, HHEM, Qwen3-VL-2B, Whisper Small, Tesseract, E5, mDeBERTa).
rem Each part is checked against its SHA-256 before use; a broken download resumes where it stopped, and running this
rem file again skips what is already done. Then the package unpacks itself and the app opens in the browser, offline.
rem It installs nothing in Windows, needs no administrator, and writes nothing outside that folder.
rem
rem Needs Windows 10 (version 1803) or newer, for its own curl and tar.

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
title Truth Guardian - download and run

set "REPO=danialrafiee-2007/iWISE-project"
set "BASE=https://github.com/%REPO%/releases/latest/download"
set "FOLDER=iWISE_Truth Guardian"
rem For testing only: another place to download from, and another folder name.
if defined TG_RELEASE_BASE set "BASE=%TG_RELEASE_BASE%"
if defined TG_FOLDER set "FOLDER=%TG_FOLDER%"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -Command"

echo.
echo   Truth Guardian: hallucination detection for RAG and agent answers
echo   This downloads the whole project (source code and models) and runs it.
echo   این فایل کل پروژه (سورس کد و مدل‌ها) را دانلود و اجرا می‌کند.
echo.

if not exist "%CURL%" goto old_windows
if not exist "%TAR%" goto old_windows

rem ---- 1. Which drive ----
echo   Drives on this computer and their free space / درایوها و فضای آزاد:
%PS% "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { '      {0}   {1,8:N0} GB free' -f $_.DeviceID, ($_.FreeSpace/1GB) }"
set "DEFAULT="
for /f %%d in ('%PS% "(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Sort-Object FreeSpace -Descending | Select-Object -First 1).DeviceID.Substring(0,1)"') do set "DEFAULT=%%d"
if not defined DEFAULT set "DEFAULT=%SystemDrive:~0,1%"
echo.

:ask_drive
set "DRIVE="
set /p "DRIVE=  Drive letter / حرف درایو [%DEFAULT%]: "
if not defined DRIVE set "DRIVE=%DEFAULT%"
set "DRIVE=%DRIVE:~0,1%"
if not exist "%DRIVE%:\" (
  echo   Drive %DRIVE%: was not found. / درایو %DRIVE%: پیدا نشد.
  goto ask_drive
)
set "ROOT=%DRIVE%:\%FOLDER%"
set "PACKAGES=%ROOT%\packages"
if not exist "%PACKAGES%" mkdir "%PACKAGES%" 2>nul
if not exist "%PACKAGES%" (
  echo   Cannot write to %DRIVE%:. Choose another drive. / روی %DRIVE%: نمی‌توان نوشت؛ درایو دیگری انتخاب کنید.
  goto ask_drive
)
echo.
echo   Folder / پوشه: %ROOT%
echo.

rem ---- 2. What the latest package holds ----
echo   Reading the latest release... / خواندن آخرین نسخه...
call :fetch "package.txt" "%PACKAGES%\package.txt" || goto no_release
call :fetch "SHA256SUMS.txt" "%PACKAGES%\SHA256SUMS.txt" || goto no_release
call :fetch "Start-Truth-Guardian.bat" "%ROOT%\Start-Truth-Guardian.bat" || goto no_release
call :fetch "README-FIRST.txt" "%ROOT%\README-FIRST.txt" || goto no_release
set "BUILD="
set "PARTS="
set "NEED_GB="
for /f "usebackq tokens=1,2 delims==" %%a in ("%PACKAGES%\package.txt") do set "%%a=%%b"
if not defined BUILD goto no_release
if not defined PARTS goto no_release
echo   Version / نسخه: %BUILD%   (%PARTS% parts / بخش)
echo.

rem Already unpacked: start at once.
if exist "%ROOT%\TruthGuardian\runtime\unpacked-%BUILD%.txt" goto start

rem ---- 3. Room for the download and for unpacking ----
if not defined NEED_GB set "NEED_GB=0"
set "FREE_GB="
for /f %%g in ('%PS% "[math]::Floor((New-Object IO.DriveInfo('%DRIVE%')).AvailableFreeSpace/1GB)"') do set "FREE_GB=%%g"
set /a NEED_ALL=%PARTS% * 2 + %NEED_GB%
if defined FREE_GB if %FREE_GB% LSS %NEED_ALL% (
  echo   This needs about %NEED_ALL% GB on %DRIVE%: and only %FREE_GB% GB is free. Choose another drive.
  echo   به حدود %NEED_ALL% گیگابایت فضا روی %DRIVE%: نیاز است و فقط %FREE_GB% گیگابایت آزاد است. درایو دیگری انتخاب کنید.
  echo.
  goto ask_drive
)

rem ---- 4. Every part, downloaded and checked ----
set "FAILED="
for /f "usebackq tokens=1,2" %%h in ("%PACKAGES%\SHA256SUMS.txt") do call :part %%h %%i
if defined FAILED goto download_failed
echo.
echo   Every part is downloaded and checked. / همهٔ بخش‌ها دانلود و بررسی شدند.
echo.

:start
rem ---- 5. Unpack (the first time) and run ----
call "%ROOT%\Start-Truth-Guardian.bat" %*
exit /b %errorlevel%


rem ======== helpers ========

rem :fetch name destination : a small file of the release, fetched again each time (the release may be newer).
:fetch
"%CURL%" -fsSL --retry 5 --retry-delay 3 -o "%~2" "%BASE%/%~1"
exit /b %errorlevel%

rem :part hash name : one part, skipped when it is already here and checks; else downloaded (resuming a broken
rem download) and checked; a part that fails its check is downloaded once more from the start.
:part
set "WANT=%~1"
set "NAME=%~2"
set "FILE=%PACKAGES%\%NAME%"
if exist "%FILE%" (
  call :check
  if not errorlevel 1 (
    echo   %NAME%: already here and checked / از قبل موجود و بررسی‌شده
    exit /b 0
  )
  del /f /q "%FILE%" >nul 2>nul
)
for %%t in (1 2) do (
  call :download && (
    call :check && (
      echo   %NAME%: checked / بررسی شد
      exit /b 0
    )
    echo   %NAME%: the check failed, downloading again / بررسی ناموفق بود؛ دوباره دانلود می‌شود
    del /f /q "%FILE%" "%FILE%.part" >nul 2>nul
  )
)
echo   %NAME%: could not be downloaded / دانلود نشد
set "FAILED=1"
exit /b 1

:download
echo   Downloading / دانلود: %NAME%
set "TRY=0"
:download_again
set /a TRY+=1
"%CURL%" -fL -# -C - --retry 5 --retry-delay 5 --connect-timeout 30 -o "%FILE%.part" "%BASE%/%NAME%"
if not errorlevel 1 goto downloaded
rem A finished file answers a resume with an error; its check decides.
if exist "%FILE%.part" (
  move /y "%FILE%.part" "%FILE%" >nul
  call :check && exit /b 0
  move /y "%FILE%" "%FILE%.part" >nul
)
rem A server that cannot resume (or a part kept from another version) starts again from the beginning.
if %TRY% GEQ 2 del /f /q "%FILE%.part" >nul 2>nul
if %TRY% LSS 5 (
  echo   The connection broke; trying again... / اتصال قطع شد؛ تلاش دوباره...
  ping -n 6 127.0.0.1 >nul
  goto download_again
)
exit /b 1
:downloaded
move /y "%FILE%.part" "%FILE%" >nul
exit /b 0

:check
set "GOT="
for /f %%s in ('%PS% "(Get-FileHash -Algorithm SHA256 -LiteralPath $env:FILE).Hash.ToLower()"') do set "GOT=%%s"
if /i "%GOT%"=="%WANT%" exit /b 0
exit /b 1


rem ======== messages ========

:old_windows
echo   This needs Windows 10 version 1803 or newer. / این فایل به ویندوز ۱۰ نسخهٔ ۱۸۰۳ یا جدیدتر نیاز دارد.
goto failed

:no_release
echo   The latest release could not be read. Check the internet connection and run this file again.
echo   آخرین نسخه خوانده نشد. اتصال اینترنت را بررسی کنید و این فایل را دوباره اجرا کنید.
goto failed

:download_failed
echo.
echo   Some parts could not be downloaded. Run this file again: what is done is kept and the rest resumes.
echo   برخی بخش‌ها دانلود نشدند. این فایل را دوباره اجرا کنید: آنچه انجام شده می‌ماند و بقیه ادامه پیدا می‌کند.
goto failed

:failed
echo.
pause
exit /b 1
