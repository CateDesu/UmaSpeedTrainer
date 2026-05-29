@echo off
rem setspeed.bat
rem Write a new speed value into the control file the DLL polls.
rem Usage:  setspeed 3       (3x)
rem         setspeed 0.5     (slow motion)
rem         setspeed off     (back to 1.0)
rem         setspeed         (show current)

setlocal
set "CTRL=%TEMP%\uma-hook.ctrl"

if "%~1"=="" (
    if exist "%CTRL%" (
        type "%CTRL%"
    ) else (
        echo control file not found at %CTRL%
    )
    goto :eof
)

if /I "%~1"=="off" (
    echo 1.0> "%CTRL%"
    echo speed: OFF
    goto :eof
)

echo %~1> "%CTRL%"
echo speed: %~1x
