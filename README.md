# FlightData

[OpenSky Network](https://opensky-network.org) Trino(과거 데이터)에서 공항 운항 CSV 를 받고, **같은 창에서 바로 분석**하는 Windows 프로그램입니다.

**받기:** [최신 릴리스](../../releases/latest)에서 `FlightData_1.xx.exe` (이름의 숫자가 버전) — 설치 없이 더블클릭
· 명령창 버전(Python 필요): [FlightData_CLI.zip](../../releases/latest/download/FlightData_CLI.zip)

- exe 를 켜면 FlightData 분석기(`web/analyzer.html`)가 프로그램 창(Edge WebView2, [pywebview](https://pywebview.flowrl.com))으로 열립니다. 화면은 이 PC 안에서만 열리는 작은 서버(127.0.0.1, `local_web.py`)가 보내고, "OpenSky에서 받기" 도 그 서버가 `fetch_flights.py` 로 수행합니다. 웹 버전: https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5
- OpenSky 계정과 Trino 사용 승인이 필요합니다. 비밀번호를 넣으면 브라우저 없이 바로 로그인합니다(pyopensky 와 같은 방식). "이 PC에 비밀번호 기억" 은 Windows 자격 증명 관리자에 저장하며, 파일이나 저장소에는 남기지 않고 화면으로 돌려주지도 않습니다. 비밀번호를 비우면 브라우저 로그인 창이 열립니다.
- OpenSky 조회 규칙(하루 단위 day 파티션 필터, 한 번에 하나씩, 받은 날은 캐시)을 지킵니다.
- 서명되지 않은 프로그램이라 처음 실행할 때 SmartScreen 경고가 뜹니다: [추가 정보] → [실행].

자세한 사용법: [README_KR.txt](README_KR.txt)

## 데이터 출처 · 인용

- 운항 데이터: The OpenSky Network (비상업적 연구용). 발표·논문에 쓰면 인용: Matthias Schäfer et al., "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research", IPSN 2014.
- 공항 목록 `airports.json`: [mwgg/Airports](https://github.com/mwgg/Airports) (MIT License)
- 지도 윤곽 `land.json`: Natural Earth (public domain)

## 직접 실행 (Python 3.13)

```
pip install trino customtkinter tkcalendar tzdata
python fetch_gui.py
```
