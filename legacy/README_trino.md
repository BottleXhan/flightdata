# OpenSky Trino 운항 수집

OpenSky Trino(과거 데이터베이스)에서 공항의 도착·출발 운항을 받아 CSV로 저장합니다.
REST API의 일일 크레딧 한도 없이 **1년치 데이터**를 받을 수 있어, ICAO Busy hour(연간 30·40번째)를 정의대로 계산할 수 있습니다.

> 사용 전에 OpenSky의 "Trino - Historical Data" 가이드, 특히 **Tools & Performance Considerations**를 꼭 읽으세요.
> 성능 규칙을 반복해서 어기면 계정이 정지됩니다.

## 이 스크립트가 지키는 가이드 규칙

| 가이드 규칙 | 스크립트 동작 |
|---|---|
| 항상 파티션 열로 거르기 (`flights_data4`는 `day`) | 모든 쿼리에 `WHERE day = <UTC 자정 Unix 시각>` |
| 큰 쿼리는 작게 나누기 | 하루(day 파티션 1개)씩 따로 조회 |
| 동시 쿼리 제한 (사용자당 2개) | 한 번에 하나씩 순서대로, 쿼리 사이 1초 대기 |
| 대량 전체 다운로드 금지 | 해당 공항(도착 또는 출발) 운항만, 필요한 6개 열만 (`track` 배열 제외) |
| 알려진 데이터 손실 구간 | 기간이 겹치면 경고 출력 |

이미 받은 날짜는 `trino_cache/` 폴더에 저장해 두고, 다시 실행하면 **조회하지 않고 캐시를 읽습니다**. 중간에 멈춰도 이어서 받을 수 있습니다.

`day` 파티션은 운항이 **끝난** UTC 날짜 기준이라, 출발편이 다음 날 끝나는 경우를 위해 마지막 날 다음 날까지 조회합니다(가이드 Flights 절).

## 방법 A. Google Colab (설치 없음, 권장)

1. https://colab.research.google.com 에 Google 계정으로 들어갑니다.
2. **파일 → 노트북 업로드**에서 `opensky_trino_colab.ipynb`를 올립니다.
3. **1. 설정** 칸에 사용자명, 공항, 기간, UTC 오프셋을 입력합니다.
   1년치처럼 오래 걸릴 때는 **SAVE_TO_DRIVE**에 체크하세요. Google Drive에 진행 상황이 저장되어 연결이 끊겨도 이어받을 수 있습니다.
4. 각 칸 왼쪽의 ▶ 버튼을 **1 → 2 → 3 → 4 → 5** 순서로 누릅니다.
   - 4번에서 OpenSky 로그인 링크가 나오면 눌러서 로그인합니다.
5. 5번 칸이 CSV를 내려받아 줍니다.

> Colab은 Google Cloud 서버에서 실행됩니다. OpenSky API 문서는 *"we may block AWS and other hyperscalers"*라고 밝히고 있어,
> 클라우드 서버에서의 접속이 막힐 수 있습니다. Colab에서 접속 오류가 나면 **방법 B(내 PC)**를 쓰세요.

## 방법 B. 내 PC에서 Python으로 실행

> **Windows에서 가장 쉬운 방법:** `fetch_flights.py`와 `run_fetch.bat`을 같은 폴더에 두고 **`run_fetch.bat`을 더블클릭**하세요.
> 사용자명·공항·기간을 차례로 물어보고, 값은 다음 실행 때 기본값으로 기억합니다(`fetch_settings.json`).
> Python 3.13이 설치되어 있으면 그것을 씁니다. 3.15처럼 너무 최신 버전은 일부 부속 프로그램이 설치되지 않습니다.

### 준비

1. OpenSky Trino 접근 승인 (메일로 안내받은 상태)
2. Python 3.9 이상
3. 라이브러리 설치
   ```bash
   pip install trino
   ```

### 실행

먼저 `--dry-run`으로 어떤 쿼리를 보낼지 확인합니다 (Trino에 접속하지 않음).

```bash
python fetch_flights.py --user 내아이디 --airport RKSI --start 2025-01-01 --end 2025-12-31 --tz 9 --dry-run
```

확인했으면 실제로 받습니다.

```bash
python fetch_flights.py --user 내아이디 --airport RKSI --start 2025-01-01 --end 2025-12-31 --tz 9
```

- `--user`: OpenSky 사용자명 (자동으로 소문자 처리)
- `--tz`: 공항 현지 UTC 오프셋 (인천 = 9)
- 처음 실행하면 **브라우저가 열려 OpenSky 로그인**을 요청합니다 (가이드의 external authentication).
  브라우저가 열리지 않으면 터미널에 나온 주소를 직접 여세요.
- 1년치는 쿼리 367번(하루 1번)이며, 시간은 서버 상태에 따라 다릅니다.

완료되면 `RKSI_2025-01-01_2025-12-31.csv`가 생깁니다.

**여러 공항 한 번에:** `--airport RKSI,RKSS,RKPC` (대화형에서는 `RKSI,RKSS`처럼 입력).
날짜마다 쿼리는 **한 번**(공항들을 `IN` 조건으로 함께)이라 가이드 규칙(파티션 필터·순차 실행)을 그대로 지키며,
결과는 공항별 CSV(`RKSI_….csv`, `RKSS_….csv`)와 공항별 캐시로 나뉩니다. 이미 받은 공항은 다시 조회하지 않습니다.
UTC 오프셋은 모든 공항에 같은 값이 적용되므로, 시간대가 다른 공항은 따로 받으세요.
분석기에서 CSV 여러 개를 한꺼번에 고르면 공항을 골라 분석하고 **공항별 비교표**를 볼 수 있습니다.

## 항공기 정보 (기종·운항사)

수집이 끝나면 OpenSky 항공기 데이터베이스(https://opensky-network.org/aircraft-database)에서 `icao24`로
등록번호·기종 코드·모델·제조사·운항사·ICAO 항공기 유형을 찾아 CSV 열로 붙입니다.

- 처음 한 번 `aircraftDatabase.csv`(수십 MB)를 스크립트 폴더에 내려받습니다. 주소는 traffic 라이브러리와 같습니다:
  `https://s3.opensky-network.org/data-samples/metadata/aircraftDatabase.csv`
- 받지 못하면 기종 열만 비우고 수집은 계속합니다. 직접 받아 같은 이름으로 두어도 됩니다.
- 붙이지 않으려면 `--no-aircraft`.
- 등록 정보 기준이라 모든 기체가 확인되지는 않으며, 실제 운항 기종과 다를 수 있습니다.
- 분석기는 이 모델 이름(예: `747 406ERF`, `777F`, `A330-243F`, 개조 화물기 `P2F`·`BCF`)과 화물 항공사 편명으로 **여객·화물을 추정**해 따로 첨두시간을 산정할 수 있습니다.

## 분석기에서 사용

1. `icao-peak-hour.html`을 엽니다.
2. 데이터 소스 → **CSV 파일 불러오기 (Trino 수집 결과)**
3. 공항 코드와 UTC 오프셋을 확인하고 CSV 파일을 고르면 분석 기간이 자동으로 채워집니다.
4. "데이터 수집 및 ICAO 기준 피크 산정"을 누릅니다.

## 주의

- 비상업적 연구 목적으로만 사용합니다. 논문·웹페이지·발표에 쓰면 OpenSky가 요청하는 원 논문을 인용하세요:
  > Matthias Schäfer, Martin Strohmeier, Vincent Lenders, Ivan Martinovic and Matthias Wilhelm. "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research". In Proceedings of the 13th IEEE/ACM International Symposium on Information Processing in Sensor Networks (IPSN), pages 83-94, April 2014.
- 계정을 여러 개 만들면 모든 계정이 영구 차단됩니다 (OpenSky API 문서).
- OpenSky는 계속 이용하는 조건으로 ADS-B 수신 데이터 제공(feeding)을 요청합니다: https://opensky-network.org/feed
- `estdepartureairport` / `estarrivalairport`는 수신 위치로 **추정한** 공항이라 실제 운항 실적과 차이가 날 수 있습니다. 공항 공식 통계와 대조하세요.
- 쿼리가 멈췄으면 Trino UI에서 사용자명으로 찾아 KILL 하세요 (가이드 Killing Queries).
