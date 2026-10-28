OpenSky 운항 CSV 수집 도구
==========================

FlightData 분석기에 넣을 CSV 파일을 OpenSky Network 에서 받는 도구입니다. (Windows)

[처음 한 번만]
1. OpenSky 계정 (https://opensky-network.org) 과 Trino(과거 데이터) 사용 승인이 필요합니다.
2. Python 3.13 을 설치합니다. PowerShell 에서:  py install 3.13
   (또는 https://www.python.org 에서 3.13 설치. 3.15 처럼 너무 최신 버전은 설치 오류가 날 수 있습니다.)

[CSV 받기]
1. 이 폴더의 run_fetch.bat 을 더블클릭합니다.
   - Windows 가 "PC 보호" 경고를 띄우면 [추가 정보] → [실행].
   - 처음 실행할 때 필요한 프로그램(trino)을 자동으로 설치합니다.
2. 검은 창에서 차례로 입력합니다. Enter 만 누르면 [ ] 안의 값을 씁니다.
   - OpenSky 사용자명
   - 공항 ICAO 코드 (예: RKSI, 여러 개는 RKSI,RKSS)
   - 현지 UTC 오프셋 (한국 = 9)
   - 시작일, 종료일 (예: 2025-01-01, 2025-12-31)
3. 브라우저에 OpenSky 로그인 창이 열리면 로그인합니다.
4. 끝나면 이 폴더에 CSV 가 생깁니다 (예: RKSI_2025-01-01_2025-12-31.csv).
5. 분석기 왼쪽 "운항 CSV 파일" 에서 그 CSV 를 고르고 [데이터 보기] 를 누릅니다.

[알아 두기]
- 하루씩 차례로 받습니다. 1년치는 오래 걸리니 처음엔 며칠로 시험해 보세요.
- 받은 날짜는 trino_cache 폴더에 저장되어 다시 받지 않습니다. 중간에 창을 닫아도 이어서 받을 수 있습니다.
- 항공기 정보(기종·운항사)를 붙이기 위해 처음 한 번 aircraftDatabase.csv (수십 MB) 를 내려받습니다.
- OpenSky 조회 규칙(하루 단위, 한 번에 하나씩)을 지키도록 만들어져 있습니다. 코드를 고쳐 쓰지 마세요.
  규칙을 어기거나 계정을 여러 개 만들면 계정이 정지될 수 있습니다.
- OpenSky 데이터는 비상업적 연구용입니다. 발표·논문에 쓰면 원 논문을 인용하세요:
  Schäfer et al., "Bringing Up OpenSky: A Large-scale ADS-B Sensor Network for Research", IPSN 2014.
