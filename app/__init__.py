"""FlightData 프로그램(Windows exe). 시작 파일은 저장소 루트의 flightdata_app.py.

  main.py       시작 순서 · 진단 기록 · 창 멈춤 감시 · selftest
  window.py     pywebview 창의 js_api (제목줄 없는 창 조작 · 폴더 고르기 · 제목줄 색)
  server.py     127.0.0.1 웹 서버 (보안 검사 · 정적 파일 · 경로 → 처리 함수)
  api.py        /api/* 처리 함수
  collector.py  화면에서 시작한 수집 작업 (작업 스레드)
  settings.py   경로(exe 폴더 · web 폴더 · 저장 폴더)와 설정 파일 · 버전
  updater.py    GitHub 릴리스 확인 · 새 exe 로 교체 · 마무리 도우미

OpenSky 접근(fetch_flights.py · opensky_auth.py)은 명령창 키트도 쓰므로 저장소 루트에 단독 파일로 둔다.
"""
