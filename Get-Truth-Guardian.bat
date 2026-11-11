@echo off
rem Truth Guardian: download the whole project, set it up and run it, with one double-click (D-213, D-217, D-224).
rem
rem It asks which drive to use, makes the folder "iWISE_Truth Guardian" there and downloads the latest ready-made package
rem from the project's GitHub Releases: the whole source code with its tests and documents, Python with every package,
rem and every model (the Guardian's, the word detector, HHEM, Qwen3-VL-2B, Whisper Small, Tesseract, E5, mDeBERTa).
rem All its questions come first (the drive, whether to delete the downloaded parts once they are unpacked, whether to
rem put a shortcut on the desktop), so the rest runs on its own. Each part is checked against its SHA-256 before use, a
rem broken download resumes where it stopped, and the whole download's progress is shown with the time left. Then it
rem unpacks the parts into the folder's TruthGuardian folder and runs the project there with TruthGuardian.bat, which
rem opens the app in the browser, offline. The desktop shortcut runs TruthGuardian.bat too.
rem Run again, it finds its folder, skips what is done and starts the app; without internet it starts the copy already
rem on this computer. It installs nothing in Windows and needs no administrator; outside its folder it writes only the
rem desktop shortcut, and only when asked to.
rem Its messages are in English, since the console of Windows 10 draws Persian letters as empty boxes; the Persian guide
rem is README-FIRST.txt in the folder and the release page.
rem
rem Needs Windows 10 (version 1803) or newer, for its own curl and tar.

setlocal EnableExtensions DisableDelayedExpansion
rem No "chcp 65001": everything here is in English, and that code page stops "set /p" from reading answers given in a file.
title Truth Guardian - download and run

set "REPO=danialrafiee-2007/iWISE-project"
set "BASE=https://github.com/%REPO%/releases/latest/download"
set "FOLDER=iWISE_Truth Guardian"
set "LINK_NAME=Truth Guardian.lnk"
rem For testing only: another place to download from, another folder name, a folder that stands for the desktop, and
rem the drive offered first (so that a test never reaches a real drive).
if defined TG_RELEASE_BASE set "BASE=%TG_RELEASE_BASE%"
if defined TG_FOLDER set "FOLDER=%TG_FOLDER%"
set "LINK_DIR=%TG_DESKTOP%"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"
set "PS=powershell -NoProfile -ExecutionPolicy Bypass -Command"
set "C=$c=[Globalization.CultureInfo]::InvariantCulture"

echo.
echo   Truth Guardian: hallucination detection for RAG and agent answers
echo   This downloads the whole project (source code and models), sets it up and runs it on this computer.
echo.

if not exist "%CURL%" goto old_windows
if not exist "%TAR%" goto old_windows

rem ---- 1. Which drive: the one that already holds the folder, else the one with the most free space ----
echo   Drives on this computer:
%PS% "%C%; $f=$env:FOLDER; Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object { $m=''; if (Test-Path -LiteralPath ($_.DeviceID+'\'+$f+'\packages\package.txt')) { $m='   <- Truth Guardian is already here' }; [string]::Format($c, '      {0}   {1,8:N0} GB free{2}', $_.DeviceID, ($_.FreeSpace/1GB), $m) }" <nul
set "DEFAULT="
for /f %%d in ('%PS% "$f=$env:FOLDER; $all=@(Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'); $d=$all | Where-Object { Test-Path -LiteralPath ($_.DeviceID+'\'+$f+'\packages\package.txt') } | Select-Object -First 1; if (-not $d) { $d=$all | Sort-Object FreeSpace -Descending | Select-Object -First 1 }; $d.DeviceID.Substring(0,1)" ^<nul') do set "DEFAULT=%%d"
if not defined DEFAULT set "DEFAULT=%SystemDrive:~0,1%"
if defined TG_DRIVE set "DEFAULT=%TG_DRIVE%"
echo.
echo   Press Enter for drive %DEFAULT%, or type another drive letter.
set "TRIES=0"

:ask_drive
set /a TRIES+=1
if %TRIES% GTR 5 goto no_drive
set "DRIVE="
set /p "DRIVE=  Drive [%DEFAULT%]: "
if not defined DRIVE set "DRIVE=%DEFAULT%"
set "DRIVE=%DRIVE:~0,1%"
if not exist "%DRIVE%:\" goto drive_missing
set "ROOT=%DRIVE%:\%FOLDER%"
set "PACKAGES=%ROOT%\packages"
rem The project, unpacked: TruthGuardian.bat in it runs it.
set "APP=%ROOT%\TruthGuardian"
if not exist "%PACKAGES%" mkdir "%PACKAGES%" 2>nul
if not exist "%PACKAGES%" goto drive_readonly
echo.
echo   Folder: %ROOT%
rem A copy of this file in the folder, which also gets a newer version later.
if /i not "%~f0"=="%ROOT%\Get-Truth-Guardian.bat" copy /y "%~f0" "%ROOT%\Get-Truth-Guardian.bat" >nul 2>nul
echo.

rem ---- 2. What the latest package holds; without internet, what is already here ----
echo   Reading the latest release...
set "ONLINE=1"
call :fetch "package.txt" || set "ONLINE="
if defined ONLINE call :fetch "SHA256SUMS.txt" || set "ONLINE="
if defined ONLINE call :fetch "README-FIRST.txt" || set "ONLINE="
if not defined ONLINE goto offline
move /y "%PACKAGES%\package.txt.new" "%PACKAGES%\package.txt" >nul
move /y "%PACKAGES%\SHA256SUMS.txt.new" "%PACKAGES%\SHA256SUMS.txt" >nul
move /y "%PACKAGES%\README-FIRST.txt.new" "%ROOT%\README-FIRST.txt" >nul
goto read_package
:offline
del /f /q "%PACKAGES%\*.new" >nul 2>nul
echo   No connection to GitHub: using what is already on this computer.
:read_package
if not exist "%PACKAGES%\package.txt" goto no_release
if not exist "%PACKAGES%\SHA256SUMS.txt" goto no_release
set "BUILD="
set "PARTS="
set "NEED_GB="
set "TOTAL_MB="
for /f "usebackq tokens=1,2 delims==" %%a in ("%PACKAGES%\package.txt") do (
  if /i "%%a"=="BUILD" set "BUILD=%%b"
  if /i "%%a"=="PARTS" set "PARTS=%%b"
  if /i "%%a"=="NEED_GB" set "NEED_GB=%%b"
  if /i "%%a"=="TOTAL_MB" set "TOTAL_MB=%%b"
)
if not defined BUILD goto no_release
if not defined PARTS goto no_release
if not defined NEED_GB set "NEED_GB=0"
if not defined TOTAL_MB set /a TOTAL_MB=PARTS * 2048
rem The size as people read it (rounded), and rounded up for the room it needs.
set /a SIZE_GB=(TOTAL_MB + 512) / 1024
if %SIZE_GB% LSS 1 set "SIZE_GB=1"
set /a SIZE_UP=(TOTAL_MB + 1023) / 1024
echo   Version %BUILD%: %PARTS% parts, about %SIZE_GB% GB.
echo.

rem Already unpacked: start at once.
if not exist "%APP%\runtime\unpacked-%BUILD%.txt" goto room
echo   This version is already set up on this computer.
goto start

:room
rem ---- 3. Room for what is still to download and for unpacking ----
call :measure
set /a NEED_ALL=SIZE_UP - DONE_GB + NEED_GB
set "FREE_GB="
for /f %%g in ('%PS% "[math]::Floor((New-Object IO.DriveInfo('%DRIVE%')).AvailableFreeSpace/1GB)" ^<nul') do set "FREE_GB=%%g"
if not defined FREE_GB goto questions
if %FREE_GB% GEQ %NEED_ALL% goto questions
echo   This needs about %NEED_ALL% GB on %DRIVE%: and only %FREE_GB% GB is free. Choose another drive.
echo.
goto ask_drive

:questions
rem ---- 4. Two questions, so that the rest runs on its own ----
echo   Two questions, then everything runs on its own (keep this window open):
set "CLEAN=Y"
set "ANSWER=y"
set /p "ANSWER=  After unpacking, delete the downloaded parts to free about %SIZE_GB% GB? The app does not need them. [Y/n]: "
if /i "%ANSWER:~0,1%"=="n" set "CLEAN=N"
set "LINK=N"
set "HAS_LINK="
for /f %%x in ('%PS% "$d=$env:LINK_DIR; if (-not $d) { $d=[Environment]::GetFolderPath('Desktop') }; Test-Path -LiteralPath (Join-Path $d $env:LINK_NAME)" ^<nul') do set "HAS_LINK=%%x"
if /i "%HAS_LINK%"=="True" goto asked
set "ANSWER=y"
set /p "ANSWER=  Put a Truth Guardian shortcut on the desktop, to start it later with a double-click? [Y/n]: "
if /i not "%ANSWER:~0,1%"=="n" set "LINK=Y"
:asked
echo.

rem ---- 5. Every part, downloaded (or found here) and checked ----
call :measure
set "T0=%NOW%"
set "DONE0=%DONE_BYTES%"
set "FAILED="
for /f "usebackq tokens=1,2" %%h in ("%PACKAGES%\SHA256SUMS.txt") do call :part %%h %%i
if defined FAILED goto download_failed
call :overall
echo   All %PARTS% parts are here and checked.
echo.

rem ---- 6. Unpack every part into the TruthGuardian folder, once; a part already unpacked is noted and skipped ----
if not exist "%APP%" mkdir "%APP%" 2>nul
if not exist "%APP%" goto cannot_unpack
echo   Unpacking into %APP%
echo   This happens once and needs no internet. Please keep this window open.
rem Windows' tar is given each part by its name alone, from inside the packages folder.
pushd "%PACKAGES%"
set "N=0"
:unpack_next
set /a N+=1
if %N% GTR %PARTS% goto unpacked
set "PART=truth-guardian-%N%-of-%PARTS%.zip"
if exist "%APP%\runtime\unpacked-%BUILD%-%N%.txt" goto unpack_next
echo   Part %N% of %PARTS%
"%TAR%" -xf "%PART%" -C "%APP%"
if errorlevel 1 goto part_damaged
if not exist "%APP%\runtime" mkdir "%APP%\runtime"
>"%APP%\runtime\unpacked-%BUILD%-%N%.txt" echo %PART%
goto unpack_next
:unpacked
popd
>"%APP%\runtime\unpacked-%BUILD%.txt" echo %BUILD%
echo   Unpacked.
echo.
if "%CLEAN%"=="Y" call :clean
if "%LINK%"=="Y" call :shortcut

:start
rem ---- 7. Run: TruthGuardian.bat in the project builds its Python environment the first time and opens the app ----
if not exist "%APP%\TruthGuardian.bat" goto part_damaged
echo.
echo   Next time, double-click the Truth Guardian shortcut on the desktop, if there is one, or TruthGuardian.bat in
echo   %APP%
echo   No internet is needed. This file starts it too, and gets a newer version when there is one.
echo.
call "%APP%\TruthGuardian.bat" %*
if errorlevel 1 goto app_failed
exit /b 0


rem ======== helpers ========

rem :fetch name : a small file of the release, fetched again each time (the release may be newer), as name.new.
:fetch
"%CURL%" -fsL --retry 2 --retry-delay 2 --connect-timeout 10 -o "%PACKAGES%\%~1.new" "%BASE%/%~1" 2>nul
exit /b %errorlevel%

rem :measure : the bytes of this version's parts already here (whole or begun), in GB too, and the time.
:measure
set "DONE_BYTES=0"
set "DONE_GB=0"
set "NOW=0"
for /f "tokens=1-3" %%a in ('%PS% "$s=(Get-ChildItem -LiteralPath $env:PACKAGES -File | Where-Object { $_.Name -like ('truth-guardian-*-of-'+$env:PARTS+'.zip*') } | Measure-Object Length -Sum).Sum; if (-not $s) { $s=0 }; '{0} {1} {2}' -f [long]$s, [math]::Floor($s/1GB), [DateTimeOffset]::Now.ToUnixTimeSeconds()" ^<nul') do set "DONE_BYTES=%%a" & set "DONE_GB=%%b" & set "NOW=%%c"
exit /b 0

rem :overall : how much of the whole download is here, and from the speed so far, how long the rest takes.
:overall
%PS% "%C%; $s=(Get-ChildItem -LiteralPath $env:PACKAGES -File | Where-Object { $_.Name -like ('truth-guardian-*-of-'+$env:PARTS+'.zip*') } | Measure-Object Length -Sum).Sum; if (-not $s) { $s=0 }; $t=[double]$env:TOTAL_MB*1MB; if ($t -le 0) { exit }; $line=[string]::Format($c, '  Overall: {0:N1} of {1:N1} GB ({2:N0}%%)', ($s/1GB), ($t/1GB), [math]::Min(100, 100*$s/$t)); $new=$s-[double]$env:DONE0; $sec=[DateTimeOffset]::Now.ToUnixTimeSeconds()-[long]$env:T0; if ($new -gt 20MB -and $sec -gt 3 -and ($t-$s) -gt 2MB) { $r=$new/$sec; $m=[math]::Max(1, [math]::Ceiling(($t-$s)/$r/60)); if ($m -ge 60) { $left=[string]::Format($c, '{0} h {1} min', [math]::Floor($m/60), $m %% 60) } else { $left=[string]::Format($c, '{0} min', $m) }; $line+=[string]::Format($c, ', {0:N1} MB/s, about {1} left', ($r/1MB), $left) }; $line" <nul
exit /b 0

rem :part hash name : one part, skipped when it is already here and checks; else downloaded (resuming a broken
rem download) and checked; a part that fails its check is downloaded once more from the start. Offline, it only checks.
:part
set "WANT=%~1"
set "NAME=%~2"
set "FILE=%PACKAGES%\%NAME%"
if exist "%FILE%" (
  call :check
  if not errorlevel 1 (
    echo   %NAME%: already here and checked
    exit /b 0
  )
  del /f /q "%FILE%" >nul 2>nul
)
if not defined ONLINE (
  echo   %NAME%: not downloaded yet
  set "FAILED=1"
  exit /b 1
)
for %%t in (1 2) do (
  call :download && (
    call :check && (
      echo   %NAME%: checked
      exit /b 0
    )
    echo   %NAME%: the check failed, downloading it again
    del /f /q "%FILE%" "%FILE%.part" >nul 2>nul
  )
)
echo   %NAME%: could not be downloaded
set "FAILED=1"
exit /b 1

:download
echo.
echo   Downloading %NAME%
call :overall
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
  echo   The connection broke; trying again...
  ping -n 6 127.0.0.1 >nul
  goto download_again
)
exit /b 1
:downloaded
move /y "%FILE%.part" "%FILE%" >nul
exit /b 0

:check
set "GOT="
for /f %%s in ('%PS% "(Get-FileHash -Algorithm SHA256 -LiteralPath $env:FILE).Hash.ToLower()" ^<nul') do set "GOT=%%s"
if /i "%GOT%"=="%WANT%" exit /b 0
exit /b 1

rem :clean : this version's downloaded parts go (the names in SHA256SUMS.txt, nothing else), once every one of them is
rem noted as unpacked.
:clean
if not exist "%APP%\runtime\unpacked-%BUILD%.txt" exit /b 1
for /f "usebackq tokens=2" %%n in ("%PACKAGES%\SHA256SUMS.txt") do del /f /q "%PACKAGES%\%%n" "%PACKAGES%\%%n.part" >nul 2>nul
echo   The downloaded parts are deleted: about %SIZE_GB% GB is free again.
exit /b 0

rem :shortcut : "Truth Guardian" on the desktop, which runs TruthGuardian.bat in the project, with the site's shield.
:shortcut
set "LINK_DONE="
for /f %%x in ('%PS% "$d=$env:LINK_DIR; if (-not $d) { $d=[Environment]::GetFolderPath('Desktop') }; $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d $env:LINK_NAME)); $s.TargetPath=(Join-Path $env:APP 'TruthGuardian.bat'); $s.WorkingDirectory=$env:APP; $s.Description='Truth Guardian: hallucination detection, offline on this computer'; $i=(Join-Path $env:APP 'deploy\portable\truth-guardian.ico'); if (Test-Path -LiteralPath $i) { $s.IconLocation=$i+',0' }; $s.Save(); 'ok'" ^<nul 2^>nul') do set "LINK_DONE=%%x"
if "%LINK_DONE%"=="ok" goto shortcut_made
echo   The desktop shortcut could not be made; TruthGuardian.bat in the TruthGuardian folder starts the app.
exit /b 0
:shortcut_made
echo   On the desktop: a shortcut named Truth Guardian.
exit /b 0


rem ======== messages ========

:drive_missing
echo   Drive %DRIVE%: was not found.
goto ask_drive

:drive_readonly
echo   Cannot write to %DRIVE%:. Choose another drive.
goto ask_drive

:old_windows
echo   This needs Windows 10 version 1803 or newer.
goto failed

:no_drive
echo   No drive was chosen that can hold Truth Guardian.
goto failed

:no_release
echo   The latest release could not be read. Check the internet connection and run this file again.
goto failed

:download_failed
echo.
if not defined ONLINE goto offline_unfinished
echo   Some parts could not be downloaded. Run this file again: what is done is kept and the rest resumes.
goto failed
:offline_unfinished
echo   There is no internet connection and the download is not finished.
echo   Connect to the internet and run this file again: what is done is kept and the rest resumes.
goto failed

:cannot_unpack
echo   The folder %APP% could not be made. Choose another drive and run this file again.
goto failed

:part_damaged
popd 2>nul
echo.
echo   A part could not be unpacked: %PART%
echo   Each part was checked before unpacking, so the drive is most likely full: free some space on drive %DRIVE%: and
echo   run this file again. What is already unpacked is kept.
goto failed

:app_failed
echo.
echo   The app did not start. The messages above say why; TruthGuardian.bat check, in the TruthGuardian folder, lists
echo   what is missing.
goto failed

:failed
echo.
pause
exit /b 1
