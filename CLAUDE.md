# FlightData

OpenSky Network Trino(과거 데이터)에서 공항 운항 CSV 를 받고, 같은 창에서 바로 통계를 보는 Windows 프로그램 + 같은 분석기의 웹 버전.
ICAO Doc 9184(Airport Planning Manual Part I, 3rd ed. 2023) 기준 첨두시간 산정은 선택 기능으로 들어 있다.

- 저장소: **BottleXhan/flightdata (Public)** — 2026-10-31 예전 비공개 저장소 ICAO(opensky-peak-hour-app 브랜치)를 여기로 합침. ICAO 히스토리는 저작권 PDF 가 들어 있어 가져오지 않았다 (파일만 복사).
- 현재 버전: `VERSION` 파일. 1.4.1 = 국기·항공사 로고·항공사 이름 + (push 안 한 1.3.2 를 합침) 두 번 실행 방지·창 찾기(이 프로세스 창만)·복원 크기·보관함 등록 표시·API 오류 응답. 1.3.1 = 구조 리팩터링(화면·기능 변화 없음, 리팩터링 전후 화면 글자·차트 값·계산 결과가 같음을 golden 비교로 확인)
- 웹 버전(아티팩트): https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5 (링크가 있는 누구나 열람)
- Python 은 **`py -3.13`** (3.15 는 zstandard 빌드 실패). 의존성: `trino tzdata pywebview requests` (+ 빌드 pyinstaller, 시험 pytest, 미리보기 playwright). Node 22 + `npm ci` (acorn: import 정리 도구)

## 저작권 자료 — 저장소에 절대 넣지 않음

공개 저장소이므로 아래는 `C:\dev\reference\` (저장소 밖)에만 둔다. `.gitignore` 에 `*.pdf`·`icao-source.html` 도 걸어 둠.

| 파일 | 내용 |
|---|---|
| `ICAO, Doc 9184, … (Third Edition, 2023).pdf` | ICAO 원문 |
| `Airport Operations Third Edition_CAA사항 포함.pdf` | Ashford et al. 교재 3판 (McGraw-Hill 2013). Ch.2 첨두 정의(SBR·BHR·TPHP)·UK CAA Table 2.1 에 사용. 공개 페이지에는 요약·인용·수치만 |
| `icao-source.html` | ICAO 원문 페이지(영문/국문/좌우 비교). 아티팩트에만 올림, exe 에는 넣지 않음 (`app/api.py` 가 `/icao-source.html` 을 웹 링크로 돌림) |

## 파일 구성

| 경로 | 내용 |
|---|---|
| `flightdata_app.py` | exe 시작 파일 (PyInstaller 대상) → `app.main.run`. `--selftest`, `--after-update`, `--finish-update` |
| `app/main.py` | 시작 순서(무거운 import 먼저 → 서버 → 숨긴 창 → loaded 때 최대화·표시), `_diag`(`app_data\diag.log`), `_watchdog`, `selftest` |
| `app/window.py` | pywebview js_api `Api`: 제목줄 없는 창 조작(Win32 직접)·폴더 고르기·제목줄 색. **밑줄 없는 속성은 함수만** |
| `app/server.py` | 127.0.0.1:8790 서버: Host/Origin/JSON 검사, `web/` 정적 파일(알려진 확장자만, 폴더 밖 차단), 나머지는 `api.dispatch` |
| `app/api.py` | `/api/*` 처리 함수 — `@get("/경로")`·`@post(...)` 로 등록, 끝이 `/` 인 경로는 접두사(`/csv/<n>`, `/api/file/<n>`). 새 API 는 여기에 함수 하나 추가 |
| `app/collector.py` | 화면에서 시작한 수집 작업(스레드, 연도별 나누기, 중지) |
| `app/settings.py` | `APP_DIR`(exe 폴더) · `fetch_settings.json` 읽기/쓰기 · 저장 폴더 규칙 · `web_dir()` · 버전(`_build.py`) |
| `app/updater.py` | GitHub releases/latest 확인·zip 받기·sha256 대조·창 없는 도우미 exe 로 교체·폴더 이름 변경 |
| `fetch_flights.py` | Trino 수집 본체 (CLI·대화형 겸용 — `kit/run_fetch.bat` 이 같은 폴더의 이 파일을 실행하므로 **루트 단독 파일 유지**). `collect_many`, 캐시, 항공기 DB, `Stopped`/`cancel_current()` |
| `opensky_auth.py` | Keycloak password grant(client_id=trino-client) → JWT, refresh, 실패 시 브라우저 OAuth2. 비밀번호는 Windows 자격 증명 관리자("FlightData/OpenSky:<사용자>") |
| `web/index.html` · `web/css/app.css` | 분석기 화면 구조 · 스타일 (exe·아티팩트 공통). CDN: Tailwind Play · Chart.js 4.4.1 · JSZip 3.10.1 · d3 7.8.5 |
| `web/js/` | ES 모듈 36개 (빌드 도구 없음). `main.js` 가 각 모듈의 `init()`(이벤트 연결)을 순서대로 부름 — 순서 의미: period·filters·peak 가 기본값을 채운 뒤 session 이 지난번 값으로 덮어씀 |
| `web/js/engine/` | **순수 계산** (DOM 없음, node 시험): `csv`(CSV→운항) · `demo`(고정 시드) · `peak`(analyze, ICAO 기준) · `stats`(비율 체인·처리능력·CAA·연별) · `classify`(기종 크기·항공사) |
| `web/js/lib/` | `fmt`(형식·시간 상수, 순수) · `dom`($·상태 줄·메시지·apiPost) · `select`(펼침 목록 위젯) |
| `web/js/data/` | `airports`(MAPDATA·공항 찾기) · `period`(공항 코드·UTC·기간) · `datasets`(CSV 가져오기·IndexedDB 저장) |
| `web/js/views/` | 장: `home` · `library`(보관함) · `overview` · `profile`(운항량) · `profile-target`(표시 대상) · `calendar` · `mix`(운항 구성) · `peak`(첨두시간) |
| `web/js/ui/` | `nav`(setPane·사이드바) · `charts`(Chart.js 공통) · `session`(최근 분석 기억) · `theme` · `airport-map`(데이터 탭 지도) · `airport-search` · `source-overlay`(ICAO 원문 창) · `badges`(국기 `flag(cc)`·`apFlag(공항)`, 항공사 `airlineMark`·`airlineName`) |
| `web/flags/` | 국기 SVG 270개(flag-icons 7.2.3, MIT, `LICENSE.txt`) — `tools/flags/get_flags.py` 로 받음. 화면은 `<img src="flags/kr.svg">` 로 필요한 것만 읽음 (Windows 는 국기 이모지를 못 그림) |
| `web/js/desktop/` | exe 안에서만: `collect`(서버 확인·다운로드 진행) · `login` · `update` · `settings`(⚙) · `window`(창 버튼·끌기) |
| `web/js/run.js` · `filters.js` · `state.js` | 분석 실행(run·renderAll) · 필터 · 공유 상태 `STATE {data, res}` |
| `web/mapdata/` | `land.json`(110m), `land50.json`(50m, 데이터 탭 지도), `airports_min.json` = {ICAO: [이름, 도시, 국가, lat, lon, IATA, tz, 표고ft, 주, 한글이름]}, `airlines.json` = {편명 앞 3자리: [IATA, 이름, 나라, 한글이름]} (OpenFlights ODbL + 한국·화물 항공사 보정, `tools/airlines/build_airlines.py`, IATA 는 운항 중인 곳만 = 로고용). 셋 다 `loadMapData()` 가 `MAPDATA.{land, airports, airlines}` 로 |
| `tests/` | pytest(`test_core` 계산·설정·js_api 규칙, `test_server` 정적 파일·보안·API) · `tests/js/engine.test.mjs`(분석 엔진 = `golden_engine.json`) |
| `tools/golden.py` · `golden_compare.py` | 리팩터링 전후 비교: 실제 서버 + Edge(Playwright)로 데모 12장면의 화면 글자·차트 값·스크린샷 기록 → 비교 |
| `tools/preview_app.py` | 화면 미리보기: 가짜 수집·로그인(비밀번호 "password")·가짜 CSV 로 서버를 띄우고 Edge 로 16장면 → `preview/app/index.html` (preview/ 는 git 제외) |
| `tools/fix_imports.mjs` | `web/js` import 줄을 실제 쓰는 이름에 맞춰 다시 만듦 (`npm run imports`, CI 는 `--check`) |
| `tools/airports/` | `airport_db.py` · `airports.json`(mwgg/Airports MIT 17,067곳 + 한글 이름) — `airports_min.json` 의 원본 자료, 실행에는 안 씀 |
| `tools/airlines/` · `tools/flags/` | `build_airlines.py`(OpenFlights 받아 `airlines.json`, 보정표 OVERRIDE) · `get_flags.py`(flag-icons 받아 `web/flags/`) — 자료를 새로 만들 때만 |
| `icon.svg` · `icon.ico` | 노랑 둥근 사각형 + 45° 남색 비행기. 분석기 favicon·머리 로고도 같은 path |
| `CHANGELOG.md` · `VERSION` | 패치 노트 · 버전 |
| `README.md` · `README_KR.txt` | 저장소 안내 · zip 에 들어가는 사용법 |
| `kit/` | 명령창 버전 (`run_fetch.bat` CRLF 유지 + `README_KR.txt`, `fetch_flights.py` 와 함께 씀) |
| `.github/workflows/release.yml` | main push → 시험(pytest · `npm run check`) → exe 빌드 → selftest → `FlightData_<VER>.zip` 릴리스 |

## 빌드 · 배포

- main 에 push → `release.yml`: Python 3.13, 시험이 실패하면 빌드하지 않음, `pyinstaller --onefile --windowed --name FlightData --icon icon.ico --add-data "web;web" … flightdata_app.py`, `--selftest`, zip = 폴더 `FlightData_<VER>\`(FlightData_<VER>.exe · README_KR.txt · 빈 OpenSky_CSV\), 태그 `v<VER>`, 릴리스 이름 `FlightData_<VER>`, 설명 = CHANGELOG.md 의 그 버전 부분.
- **패치를 push 할 때마다 `VERSION` 을 올리고 `CHANGELOG.md` 맨 위에 `## x.y.z` 항목을 쓴다.** 작은 패치 = 마지막 숫자 +1, 조금 큰 업데이트 = 가운데 숫자 +1 하고 마지막은 .1 부터. 사용자에게는 `FlightData_x.y.z` 이름으로 알림.
- 릴리스 자산은 zip 하나. 항공기 DB(OpenSky 자료)는 넣지 않음 — 첫 다운로드 때 받음. 서명 안 됨 → SmartScreen [추가 정보]→[실행].
- 이 세션은 GitHub 릴리스를 직접 고치지 않는다 — 워크플로로만.
- 로컬 확인: `py -3.13 -m pytest -q tests` · `npm run check` · `py -3.13 flightdata_app.py --selftest` (exit 0), 창 실행은 `py -3.13 flightdata_app.py` (업데이트 적용은 exe 에서만).
- 화면을 건드리는 큰 변경 전후: `py -3.13 tools/golden.py preview/golden_a` → 변경 → `… preview/golden_b` → `py -3.13 tools/golden_compare.py preview/golden_a preview/golden_b`. 계산을 일부러 바꿨으면 `--engine` 으로 뽑은 engine.json 으로 `tests/js/golden_engine.json` 교체.

## 웹 버전(아티팩트) 올리기

`web/index.html` 을 페이지로, files 에 `css/app.css` · `js/**/*.js`(36개, 경로 그대로) · `mapdata/land.json`·`mapdata/land50.json`·`mapdata/airports_min.json`·`mapdata/airlines.json` · `flags/*.svg`(270개 — 한 번에 255개까지라 두 번에 나눠 올림), `icao-source.html`, 그리고 원문 페이지의 "돌아가기" 용으로 `web/index.html` 사본을 `icao-peak-hour.html` 로. 모듈 스크립트라 js 파일이 하나라도 빠지면 화면 전체가 안 뜸. 지금 올라가 있는 아티팩트는 1.2.4 때의 한 파일 버전(동작은 같음) — 다음에 화면을 바꿀 때 이 구조로 다시 올릴 것. icao-source.html 은 저장소 밖이라 **scratchpad 에 복사한 뒤** 그 경로를 files 로 넘긴다. 변경할 때마다 위 공유 링크를 사용자에게 준다.

## exe 동작 (현재)

- **시작**: 창을 띄우기 전에 requests·trino·opensky_auth·updater·zoneinfo 를 동기로 import (뒤 스레드 import 가 GIL 을 잡아 창이 멈추던 문제). `create_window(hidden=True)` → `events.loaded`(첫 번만, 20초 지나면 강제) 때 Win32 최대화 후 show. `app_data\diag.log` 에 단계 시각, watchdog 이 1초마다 `SendMessageTimeoutW(WM_NULL, 2초)` 실패 시 모든 스레드 스택 기록. 업데이트 확인은 8초 뒤.
- **한 번만 실행**: 이름 있는 뮤텍스 `Local\FlightData.single` — 이미 떠 있으면 제목이 "FlightData …"인 창을 앞으로 가져오고 끝남(`--after-update` 는 예외). 서버는 `SO_EXCLUSIVEADDRUSE`(`allow_reuse_address=False`) — 파이썬 기본값이면 Windows 에서 두 프로세스가 8790 을 함께 잡았음(1.3.1 이하).
- **js_api(Api) 규칙**: 밑줄 없는 속성은 함수만 (공개 속성 `window` 가 있으면 pywebview 가 페이지 로드마다 .NET 폼 전체를 재귀 getattr → "응답 없음", 1.2.3). selftest 가 확인.
- **창**: frameless. 헤더 오른쪽 최소화·최대화·닫기(#winCtl), 빈 곳 끌기 = 이동, 더블클릭 = 최대화 전환, 가장자리 8곳(#rsz) 크기 조절(최소 1100×700). 복원 크기 = 보이는 상태에서 최대화하기 전 크기(작업 영역 안으로 맞춤), 없으면 가운데 1480×920. 최대화·이동은 Win32 직접(창 = EnumWindows 로 이 프로세스의 같은 제목 창 — FindWindowW 는 같은 제목의 탐색기 탭 대리 창을 잡았음 · GetDpiForWindow·MonitorFromWindow 작업 영역·SetWindowPos ASYNC). 제목줄 색은 DwmSetWindowAttribute 20/35/36, 최대화 중 34=COLOR_NONE·33 둥근 모서리 끔.
- **저장 위치**: 설정 `fetch_settings.json`·항공기 DB·`app_data`(WebView2 저장소 → IndexedDB 보관함 유지) 는 exe 폴더(`fetch_flights.APP_DIR`). CSV·`trino_cache` 기본 = exe 옆 `OpenSky_CSV` (설정 out_dir 은 "" 로 두고, 예전 기본값(문서·OneDrive 문서)이면 새 기본값으로). zip 안에서 바로 실행하면 inTemp 경고.
- **로그인**: 머리 오른쪽(exe 만). POST /api/login 이 실제 토큰으로 확인 → 서버 메모리 세션에 보관, 화면에는 비밀번호를 돌려주지 않음. "자동 로그인"(기본 꺼짐) 켜고 로그인하면 자격 증명 관리자 저장 + remember_pw=true. 로그인 중 잠금·45초 제한. 로그인 안 하면 브라우저 OAuth. [회원가입] 팝업 = OpenSky 가입·Trino 신청 안내 + 홈페이지 열기(/api/open-url, opensky-network.org 만).
- **중지**: /api/collect/stop 이 실행 중 Trino 쿼리를 cursor.cancel(), 재시도 대기도 0.5초마다 확인. 상태 "stopped", 직후 start 는 최대 10초 대기.
- **업데이트**: /api/update/check(10분 캐시) → 오른쪽 아래 알림(#updModal.upd-toast) 과 ⚙ 설정 둘 다에서 [업데이트]. 새 exe 를 지금 exe 옆에 `FlightData_<새 버전>.exe` 로 쓰고, `%TEMP%\FlightData_update_<pid>.exe --finish-update` 도우미가 이전 프로세스 종료를 기다려 옛 exe 삭제 + 폴더 이름의 x.y.z 를 새 버전으로 바꾼 뒤 새 exe 실행. 1.2.1 이하는 1.2.2+ 로 자동 업데이트 불가(한 번 새로 받기).
- **API (`app/api.py`)**: /api/collector(app=true, version, 방금 받은 CSV), /csv/<n>, /api/collect·/status·/stop, /api/open-folder, /api/pwsaved, /api/login·/logout·/autologin, /api/settings{outDir}, /api/files·/api/file/<n>, /api/open-url, /api/update/check·apply·status·restart.

## 분석기 화면 (현재)

- 이름 "FlightData", 부제 "OpenSky 데이터". 글꼴 Noto Sans KR(숫자 tabular-nums). 공항 표지 노랑(--sign)은 PEAK·공항 코드에만. 다크 모드. 폭 제한 없음(창 너비 꽉).
- **머리**: 로고(누르면 홈) + 버전 · 가운데 #hrun(공항·기간·운항 수) · 오른쪽 로그인(초록 점+사용자명) · ⚙ 설정(#setPop: 버전·업데이트 / 저장 폴더 바꾸기·열기 / 자동 로그인 / 테마 라이트·다크 / 접는 "데이터 출처" + ICAO 원문 링크) · 창 버튼. #themeBtn·#homeBtn 은 hidden 으로 남아 코드에서 씀.
- **사이드바 목차(#sideNav 가로 탭)**: 홈 | 데이터 | 보관함 | 개요 | 운항량 | 운항 구성 | (첨두시간: 스위치 켰을 때). 누르면 사이드바 내용과 본문(#results[data-view])이 함께 바뀜(setPane). 첫 화면은 항상 홈 탭, 시작 시 자동 분석하지 않음. 준비 중 덮개(#bootOverlay, 최대 15초).
- **홈**: 바로가기 4개(데이터 다운로드·보관함·CSV 가져오기·데모), 최근 데이터 6개, 지금 보는 데이터. 로고 → resetHome()(받는 중이면 막음).
- **데이터**: 카드 탭 [데이터 다운로드 | 지도에서 공항 찾기]. 1 공항(공항 검색 "예: 인천, 인천국제공항, Incheon, ICN, RKSI", 비우면 RKSI·공항 시간대 자동) 2 기간(최근 7·30일, 📅 연도 선택 팝업 2017~올해, 범위 선택) 3 [다운로드 시작]/[분석 시작] + exe 옵션(연도별 CSV 나누기·기종 정보·저장 폴더). 받는 중 패널 #dvProg(%·막대·중지·폴더 열기·기록). 지도는 Canvas(land50, 휠 확대·끌기·클릭 선택, 처음 위도 5.2°).
- **보관함**: IndexedDB "flightdata"/datasets(gzip), 이름·메모·공항 이름·나라 열, 공항·나라 필터, 분석·이름 편집·CSV 내려받기(여러 파일 JSZip)·삭제, 여러 개 병합 후 분석, exe 면 저장 폴더 CSV 목록. CSV 내용은 서버로 보내지 않음. localStorage "flightdata.last"(설정)·"flightdata.lastDataset".
- **개요**: 공항 정보 카드(작은 지구본·이름·도시·코드·표고·시간대·항공사/연결 공항/나라 수·국제선 비율·최다 노선) + 숫자 카드 5개(총 운항·하루 평균·가장 바쁜 날·가장 바쁜 1시간·도착:출발) + 작은 그래프 3개(누르면 운항량) + Top 5 노선·항공사·기종(누르면 운항 구성).
- **운항량**: 사이드바 "보기" 시간대별·일별·요일별·월별·(두 해 이상이면) 연별 + 첨두시간 스위치(#peakOn) + 필터. 도착·출발 막대, 모든 그래프 평균 점선+라벨, y축 확대(zoomY, "0부터 아님") 때도 도착:출발 비율로 나눈 떠 있는 막대. 표시 대상(평균/PEAK 일/설계일/날짜 달력 등), "세부 정보" 표.
- **운항 구성**: 보기 [노선 | 항공사 | 기종], 상위 15 가로 막대, 표는 "세부 정보"로. 노선은 지도(분석 공항 경도 중심 NaturalEarth, 대권 선 굵기=운항 수)와 그래프 좌우 배치, "미상" 노선 제외.
- **필터**(운항량·구성 공용 #filterStep): 방향 · 노선(국내/국제/나라별) · 항공사(편명 앞 3자리) · 기종 크기(typecode → 대형/중형/소형, 이 도구의 분류) · 현지 시간대. 칩으로 해제.
- **첨두시간 산정(선택)**: 스위치를 켜야 탭·설계일 표시(.design-only)가 보임. 아래 "산정 기준".
- 1.2.1 에서 **코드째 삭제**: 순위·운항 목록·방법론 장, 공항별 비교, 여객·화물 구분, 엑셀/시간대별 CSV 내보내기(SheetJS), 상단 바 목차, 수집 도구 zip. 되살릴 때는 ICAO 저장소 히스토리(1.2.0 이전)에서.

## 데이터 규칙 (OpenSky)

- Trino `flights_data4`, **항상 `WHERE day = <UTC 자정>` 파티션 필터**, 하루씩 순차, 필요한 6개 열만, 캐시로 재조회 방지. 여러 공항은 날짜당 쿼리 1번(IN). `day` 는 lastseen 기준이라 마지막 날 +1일까지 조회. 위반 반복 시 계정 정지, 다중 계정 영구 차단, 화이트리스트 요청 금지.
- 클라우드 IP(Colab 등)는 차단됨 → 사용자 PC 에서만 수집.
- 항공기 DB: `https://s3.opensky-network.org/data-samples/metadata/aircraftDatabase.csv` 를 한 번 받아 icao24 로 registration·typecode·model·manufacturer·operator 붙임 (실데이터 미검증).
- 인용: Schäfer et al., "Bringing Up OpenSky", IPSN 2014 — 설정 › 데이터 출처에 표시.
- 항공사 로고: `https://pics.avs.io/120/40/<IATA>@2x.png` 를 화면에서 바로 읽음 (사용자 선택 2026-10-31: 외부 로고 서비스). 저장소에 로고 파일을 넣지 않음. 못 받으면 `ui/badges.js` 의 문서 error 처리기가 항공사 나라 국기로 바꿈. 로고는 어두운 글자라 흰 바탕 칩(`img.al-logo`). 아티팩트(웹 버전)에서는 외부 이미지가 막히면 국기만 보임.
- firstSeen/lastSeen·est*Airport 는 추정값. 2026-10-26 RKSI 3일 953건(하루 약 320편)으로 실제보다 크게 적음 → 커버리지 한계, 공식 통계 대조 필요.

## 산정 기준 (첨두시간 스위치)

- 기본: §3.4.3 a) 30번째 바쁜 시간 = SBR. 그 밖에 Glossary(Peak / Busy hour 연속 2시간 평균 30·40번째), §3.4.3 b)~e)(피크 월 평균일(FAA)·Second busiest day(IATA)·90/95 백분위·5% busy hour). Absolute peak 은 참고값만.
- N번째는 분석 기간 안의 N번째 그대로(1년 미만이면 경고만, 기간 비례 환산 없음). 분석 기간 최대 3,660일.
- 처리능력 비교(이용률·포화), 미래 첨두(§3.8.4 peak hour ratio × 성장률), 첨두 비율 체인(연간→피크 월→평균일→첨두일→설계일→설계 첨두시간; 단계 구성은 이 도구의 해석), UK CAA Table 2.1 대조(선형 보간).
- 원문에 절차가 없어 이 도구가 정한 해석: IATA 평균 주 구성, 백분위 busy period = 일, 피크 2개월 = 일평균 최대 연속 두 달. 화면에 해석임을 표시.

## 작업 규칙 (사용자 선호)

- 사용자에게는 한국어로 답한다.
- 코드 구조 규칙: 계산은 `web/js/engine/`(DOM 금지, node 시험), 화면 연결(addEventListener 등)은 각 모듈의 `init()` 안, 다른 모듈의 `let` 은 직접 대입하지 말고 그 모듈에 설정 함수를 둠(ES 모듈 import 는 읽기 전용). JS 모듈을 추가·이동하면 `npm run imports` → `npm run check`. 서버 API 는 `app/api.py` 에 함수 추가.
- 화면을 바꾸면 `tools/preview_app.py` 로 미리보기를 만들어 `preview/app/index.html` 을 SendUserFile(display=render)로 보낸다 (회사 PC 는 exe 실행마다 보안 검사).
- UI 문구는 업무용 용어·짧은 명사형: 다운로드, 선택, 입력, 가져오기, 삭제, 추가, 병합 후 분석, 데이터 초기화, 데모 실행, 우측 상단, "~하세요/~됩니다". 화면에 "비상업적·상업" 같은 말 쓰지 않음(발표용).
- PC 화면만 고려(휴대폰 X). 사용자 화면은 32인치 UHD·배율 150% 안팎 — 물리 픽셀×배율, 흐림·1px 틈 주의.
- 디자인: 테두리 장식 없이, 가독성 우선. Tailwind 유틸리티와 겹치는 클래스 이름(예: `outline`) 금지.
- ICAO 원문 페이지: 조항은 전문, 문장 단위로 영문·국문 행 맞춤(`.seg-row`), 번역은 원문 구조를 따름, 원문에 없는 내용은 그렇다고 표시.
- 자격증명(client_secret·비밀번호 등)은 코드·저장소·채팅에 넣지 않는다. 공개 저장소임을 잊지 말 것.

## 미해결 · 다음 후보

- "응답 없음"이 1.2.4 이후에도 재발하면 사용자에게 `app_data\diag.log` 를 받아 원인 확인. 다음 후보는 onefile → onedir 빌드(단 updater 가 `_internal` 까지 교체해야 하고 1.2.3 이하와 호환 안 됨).
- 실제 Windows 확인됨(2026-10-31, 1.3.1 exe·1.3.2 로컬 빌드): 시작 최대화·창 버튼·끌기·더블클릭·테마·보관함·두 번 실행. 미검증: 비밀번호 로그인 실서버, 업데이트 전체 흐름.
- **서머타임(DST) 미반영**: UTC 오프셋을 기간 시작일 기준 하나로 고정(`offsetFor`, 수집 `tz`도 숫자 하나). 한국(RKSI 등)은 문제없지만 미국·유럽 공항은 서머타임 기간의 시간대별 그래프·날짜 경계가 1시간 밀림. 고치려면 운항마다 현지 오프셋을 계산해야 해서 engine 전반(`peak`·`stats`)과 golden 이 바뀜.
- 최소화된 창을 ShowWindow(SW_RESTORE) 로 되살리면 WebView2 화면이 흰색으로 남음 → 다른 프로세스에서 복원할 땐 WM_SYSCOMMAND SC_RESTORE 를 쓸 것.
- 목표 연도(5·10·20년, Section I §2.4.9)별 요약표, 주기장 소요 추정(Section II §2.2.8).
