@echo off
rem Meeting mode: capture system audio and show always-on-top subtitles.
cd /d "%~dp0"
call start.bat --source system --overlay --overlay-font-size 30 %*
