# FlightData

[OpenSky Network](https://opensky-network.org) Trino(과거 데이터)에서 공항 운항 CSV 를 받고, **같은 창에서 바로 분석**하는 Windows 프로그램입니다.

**받기:** [최신 릴리스](../../releases/latest)에서 `FlightData_1.0.xx.zip` (숫자가 버전) → 압축을 풀고 폴더 안의 `FlightData_<버전>.exe` 더블클릭 (설치 필요 없음)
· [패치 노트](CHANGELOG.md)
· 명령창 버전(Python 필요): 이 저장소의 `kit/run_fetch.bat` + `fetch_flights.py` (Code → Download ZIP)

- exe 를 켜면 FlightData 분석기(`web/analyzer.html`)가 프로그램 창(Edge WebView2, [pywebview](https://pywebview.flowrl.com))으로 열립니다. 화면은 이 PC 안에서만 열리는 작은 서버(127.0.0.1, `local_web.py`)가 보내고, "OpenSky에서 받기" 도 그 서버가 `fetch_flights.py` 로 수행합니다. 웹 버전: https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5
- OpenSky 계정과 Trino 사용 승인이 필요합니다. 비밀번호를 넣으면 브라우저 없이 바로 로그인합니다(pyopensky 와 같은 방식). "이 PC에 비밀번호 기억" 은 Windows 자격 증명 관리자에 저장하며, 파일이나 저장소에는 남기지 않고 화면으로 돌려주지도 않습니다. 비밀번호를 비우면 브라우저 로그인 창이 열립니다.
- OpenSky 조회 규칙(하루 단위 day 파티션 필터, 한 번에 하나씩, 받은 날은 캐시)을 지킵니다.
- 서명되지 않은 프로그램이라 처음 실행할 때 SmartScreen 경고가 뜹니다: [추가 정보] → [실행].

자세한 사용법: [README_KR.txt](README_KR.txt)

## 데이터 출처 · 인용

- 운항 데이터: The OpenSky Network. 발표·논문에 쓰면 인용: Matthias Schäfer et al., "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research", IPSN 2014.
- 공항 목록 `web/mapdata/airports_min.json`: [mwgg/Airports](https://github.com/mwgg/Airports) (MIT License, 원본 `tools/airports/airports.json`)
- 지도 윤곽 `web/mapdata/land*.json`: Natural Earth (public domain)
- 항공사 이름·나라 `web/mapdata/airlines.json`: [OpenFlights](https://openflights.org/data) airlines·countries, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (이 파일도 ODbL, 만드는 도구 `tools/airlines/build_airlines.py` — 한국·화물 항공사 보정 포함)
- 국기 `web/flags/*.svg`: [flag-icons](https://github.com/lipis/flag-icons) (MIT License, `web/flags/LICENSE.txt`)
- 항공사 로고: 화면에 표시할 때 [pics.avs.io](https://pics.avs.io) 에서 받음 (저장소에 넣지 않음). 로고는 각 항공사의 상표

## 구조

| 경로 | 내용 |
|---|---|
| `web/` | 분석기 화면 (exe·웹 공통): `index.html` · `css/app.css` · `js/` (ES 모듈, 빌드 도구 없음) · `mapdata/` |
| `web/js/engine/` | 순수 계산 — CSV 읽기 · 데모 데이터 · ICAO 첨두시간 산정 · 요약 통계 (DOM 없음, node 로 시험) |
| `web/js/views/` · `ui/` · `data/` · `desktop/` | 화면 장 · 공용 화면 요소 · 공항/기간/불러온 데이터 · 프로그램(exe) 전용 기능 |
| `app/` | exe: 시작(`main`) · 창(`window`) · 로컬 서버(`server`) · API(`api`) · 수집 작업(`collector`) · 설정(`settings`) · 업데이트(`updater`) |
| `fetch_flights.py` · `opensky_auth.py` | OpenSky Trino 수집 · 로그인 (명령창 버전도 이 파일을 그대로 씀) |
| `flightdata_app.py` | exe 시작 파일 |
| `tests/` | 파이썬 시험(pytest) · 분석 엔진 시험(`tests/js`, node) |
| `tools/` | 화면 미리보기 · 리팩터링 비교(golden) · import 정리 도구 |

## 직접 실행 · 시험 (Python 3.13, Node 22)

```
py -3.13 -m pip install trino tzdata pywebview requests pytest
py -3.13 flightdata_app.py            # 프로그램 창으로 실행
py -3.13 -m pytest -q tests           # 파이썬 시험
npm ci && npm run check               # import 정리 상태 + 분석 엔진 시험
```
