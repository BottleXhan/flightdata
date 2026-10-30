"""FlightData — 수집과 분석을 한 창에서 (Windows exe 의 시작 파일, 코드는 app/).

    py -3.13 flightdata_app.py              # 개발용 실행
    FlightData.exe --selftest               # 빌드 확인 (필요한 모듈·데이터가 들어갔는지)
"""
import sys

from app.main import run

if __name__ == "__main__":
    sys.exit(run(sys.argv))
