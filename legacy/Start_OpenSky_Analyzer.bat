@echo off
chcp 65001 >nul
rem OpenSky 첨두시간 분석기 — 더블클릭하면 브라우저에 분석기가 열립니다. 이 창을 닫으면 종료됩니다.
title OpenSky 첨두시간 분석기 - 이 창을 닫으면 종료
cd /d "%~dp0"
py -V:3.13 --version >nul 2>&1
if %errorlevel%==0 (
  py -V:3.13 app.py
) else (
  py app.py
)
echo.
echo 종료되었습니다. 아무 키나 누르면 창이 닫힙니다.
pause >nul
