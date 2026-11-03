@echo off
rem Truth Guardian, the ready-made package: one double-click, no internet, nothing installed in Windows.
rem The first time this unpacks packages\ into one folder; afterwards the app starts at once.

setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
pushd "%~dp0"
title Truth Guardian
set "PACKAGES=%CD%\packages"
set "TAR=%SystemRoot%\System32\tar.exe"
set "BUILD="
set "PARTS="
set "NEED_GB="

echo.
echo   Truth Guardian: hallucination detection for RAG and agent answers
echo.

if not exist "%PACKAGES%\package.txt" goto no_packages
for /f "usebackq tokens=1,2 delims==" %%a in ("%PACKAGES%\package.txt") do set "%%a=%%b"
if not defined BUILD goto no_packages
if not defined PARTS goto no_packages

rem Next to this file on a normal disk. Windows' tar and the models' C++ libraries cannot read a path with non-Latin
rem letters, and a very long path would break the longest file names inside, so those unpack at the top of the same
rem drive. A USB stick or a network folder would be slow, so those unpack on the system drive.
set "HERE=%CD%"
set "KIND="
set "NON_LATIN=0"
for /f "tokens=1,2" %%k in ('powershell -NoProfile -Command "$h=$env:HERE; '{0} {1}' -f (New-Object IO.DriveInfo($h.Substring(0,1))).DriveType, [int]($h -match '[^\x00-\x7F]')"') do set "KIND=%%k" & set "NON_LATIN=%%l"
set "TARGET=%HERE%\TruthGuardian"
if "%NON_LATIN%"=="1" set "TARGET=%HERE:~0,2%\TruthGuardian"
if not "%TARGET:~85%"=="" set "TARGET=%HERE:~0,2%\TruthGuardian"
if defined KIND if /i not "%KIND%"=="Fixed" set "TARGET=%SystemDrive%\TruthGuardian"
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
if exist "%TARGET%" goto target_ready
set "TARGET=%USERPROFILE%\TruthGuardian"
if not exist "%TARGET%" mkdir "%TARGET%" 2>nul
if not exist "%TARGET%" goto cannot_write
:target_ready

if exist "%TARGET%\runtime\unpacked-%BUILD%.txt" goto start
if not exist "%TAR%" goto old_windows
if exist "%TARGET%\runtime\unpacked-%BUILD%-1.txt" goto unpack
set "FREE_GB="
for /f %%g in ('powershell -NoProfile -Command "[math]::Floor((New-Object IO.DriveInfo('%TARGET:~0,1%')).AvailableFreeSpace/1GB)"') do set "FREE_GB=%%g"
if not defined FREE_GB goto unpack
if not defined NEED_GB goto unpack
if %FREE_GB% LSS %NEED_GB% goto no_space

:unpack
echo   First start: unpacking into %TARGET%
echo   This happens once and needs no internet. Please keep this window open.
echo.
cd /d "%PACKAGES%"
set "N=0"
:unpack_next
set /a N+=1
if %N% GTR %PARTS% goto unpacked
set "PART=truth-guardian-%N%-of-%PARTS%.zip"
if exist "%TARGET%\runtime\unpacked-%BUILD%-%N%.txt" goto unpack_next
if not exist "%PACKAGES%\%PART%" goto part_missing
echo   Part %N% of %PARTS%
"%TAR%" -xf "%PART%" -C "%TARGET%"
if errorlevel 1 goto part_damaged
if not exist "%TARGET%\runtime" mkdir "%TARGET%\runtime"
>"%TARGET%\runtime\unpacked-%BUILD%-%N%.txt" echo %PART%
goto unpack_next
:unpacked
>"%TARGET%\runtime\unpacked-%BUILD%.txt" echo %BUILD%
echo   Unpacked.
echo.

:start
if not exist "%TARGET%\TruthGuardian.bat" goto part_damaged
call "%TARGET%\TruthGuardian.bat" %*
if errorlevel 1 goto app_failed
goto finished

:no_packages
echo   The packages folder is missing. Copy the whole Truth Guardian folder, not only this file, and try again.
goto failed

:cannot_write
echo   No folder could be created to unpack into. Copy this folder to a disk you can write to and try again.
goto failed

:old_windows
echo   This needs Windows 10 version 1803 or newer.
goto failed

:no_space
echo   Unpacking needs about %NEED_GB% GB on drive %TARGET:~0,1%: and only %FREE_GB% GB is free.
echo   Free some space, or copy this folder to another disk, and try again.
goto failed

:part_missing
echo   %PART% is missing from the packages folder. Copy the whole Truth Guardian folder again and try again.
goto failed

:part_damaged
echo.
echo   A package part could not be unpacked: %PART%
echo   Check the free space on drive %TARGET:~0,1%:, copy the packages folder again if it still fails, and run this file again.
echo   What is already unpacked is kept.
goto failed

:app_failed
echo.
echo   The app did not start. The messages above say why.

:failed
echo.
pause
popd
endlocal
exit /b 1

:finished
popd
endlocal
exit /b 0
