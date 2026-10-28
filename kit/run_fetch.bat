@echo off
chcp 65001 >nul
rem OpenSky 운항 CSV 수집 — 더블클릭으로 실행
cd /d "%~dp0"

rem Python 찾기 (3.13 우선)
set "PY="
py -V:3.13 --version >nul 2>&1 && set "PY=py -V:3.13"
if not defined PY py --version >nul 2>&1 && set "PY=py"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [!] Python 이 설치되어 있지 않습니다.
  echo     PowerShell 에서  py install 3.13  을 실행하거나 python.org 에서 Python 3.13 을 설치한 뒤 다시 실행하세요.
  echo.
  pause
  exit /b 1
)

rem 처음 한 번: trino 라이브러리 설치
%PY% -c "import trino" >nul 2>&1
if errorlevel 1 (
  echo 처음 실행: 필요한 프로그램^(trino^)을 설치합니다. 1분 정도 걸립니다...
  %PY% -m pip install -q trino
)

%PY% fetch_flights.py
echo.
echo 결과 CSV 는 이 폴더에 저장됩니다. 분석기 왼쪽 "운항 CSV 파일" 에서 고르세요.
echo 창을 닫으려면 아무 키나 누르세요.
pause >nul
