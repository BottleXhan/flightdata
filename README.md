# FlightData 수집기

FlightData 분석기에 넣을 CSV 를 [OpenSky Network](https://opensky-network.org) Trino(과거 데이터)에서 받는 Windows 프로그램입니다.

**받기:** [최신 FlightData_Collector.exe](../../releases/latest/download/FlightData_Collector.exe) — 설치 없이 더블클릭

- OpenSky 계정과 Trino 사용 승인이 필요합니다. 비밀번호는 프로그램에 입력하지 않고 브라우저 로그인 창에서 입력합니다.
- 공항 이름·도시·IATA·한글로 검색하거나 지도에서 고르면 ICAO 코드와 UTC 오프셋이 자동으로 채워집니다.
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
