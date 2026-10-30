"""화면·네트워크 없이 확인할 수 있는 계산: 조회 계획, 연도 나누기, 버전·폴더 이름, 설정."""
import datetime as dt
import os

import fetch_flights as ff
from app import settings, updater
from app.collector import year_segments
from app.window import Api


def test_plan_days_includes_next_day_for_departures():
    begin = ff.local_date_to_utc("2025-03-01", 9)            # 현지 자정 = 전날 15:00 UTC
    end = ff.local_date_to_utc("2025-03-03", 9) + 86400
    days = ff.plan_days(begin, end)
    assert days[0] == ff.utc_ts("2025-02-28 00:00")
    assert days[-1] == ff.utc_ts("2025-03-04 00:00")          # 기간 끝(03-03 15:00 UTC)의 날 + 1 (출발편이 다음 날 끝남)
    assert all(b - a == 86400 for a, b in zip(days, days[1:]))


def test_parse_airports_and_gaps():
    assert ff.parse_airports("rksi, RKSS rksi") == ["RKSI", "RKSS"]
    gaps = ff.overlapping_gaps(ff.utc_ts("2024-05-20 00:00"), ff.utc_ts("2024-05-22 00:00"))
    assert gaps == [("2024-05-20 10:00", "2024-05-21 05:00")]


def test_year_segments():
    segs = year_segments(dt.date(2023, 11, 1), dt.date(2025, 2, 3))
    assert segs == [(dt.date(2023, 11, 1), dt.date(2023, 12, 31)), (dt.date(2024, 1, 1), dt.date(2024, 12, 31)),
                    (dt.date(2025, 1, 1), dt.date(2025, 2, 3))]
    assert year_segments(dt.date(2025, 1, 1), dt.date(2025, 1, 1)) == [(dt.date(2025, 1, 1), dt.date(2025, 1, 1))]


def test_versions_and_folder_names():
    assert updater.parse_ver("FlightData_1.2.4") == (1, 2, 4) and updater.parse_ver("v1.3.1") > updater.parse_ver("1.2.10")
    assert updater.parse_ver("no version") == ()
    assert updater.new_folder_name("FlightData_1.2.4", "1.3.1") == "FlightData_1.3.1"
    assert updater.new_folder_name("FlightData_1.2.4 (2)", "1.3.1") == "FlightData_1.3.1 (2)"
    assert updater.new_folder_name("FlightData", "1.3.1") == ""          # 버전 없는 폴더 이름은 그대로
    assert updater.new_folder_name("FlightData_1.3.1", "1.3.1") == ""


def test_release_notes_changes():
    md = "안내\n\n### 이번 버전에서 바뀐 것\n- **구조** 정리\n- 테스트 추가\n\n### 기타\n- 무시"
    assert updater.notes_text(md) == ["구조 정리", "테스트 추가"]


def test_out_dir_defaults(app_dir):
    assert settings.out_dir() == os.path.join(str(app_dir), "OpenSky_CSV")
    old = os.path.join(os.path.expanduser("~"), "Documents", "OpenSky_CSV")
    settings.save({"out_dir": old})                          # 예전 기본값 → 새 기본값
    assert settings.out_dir() == settings.default_out_dir()
    gone = os.path.join(str(app_dir), "FlightData_1.1.7", "OpenSky_CSV")
    settings.save({"out_dir": gone})                         # 업데이트로 이름이 바뀐 예전 버전 폴더
    assert settings.out_dir() == settings.default_out_dir()
    mine = str(app_dir / "mine")
    settings.save({"out_dir": mine, "user": "x"})
    assert settings.out_dir() == mine and settings.load()["user"] == "x"
    assert settings.out_dir_value(settings.default_out_dir()) == "" and settings.out_dir_value(mine) == mine


def test_js_api_exposes_only_functions():
    # 밑줄 없는 속성이 객체면 pywebview 가 페이지마다 그 안을 뒤져 창이 멈춘다 (1.2.3)
    api = Api()
    assert not [n for n in dir(api) if not n.startswith("_") and not callable(getattr(api, n))]
