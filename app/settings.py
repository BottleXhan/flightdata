"""경로와 설정: exe 폴더(APP_DIR)의 fetch_settings.json, 저장 폴더(기본 = exe 옆 OpenSky_CSV), web 폴더, 버전."""
import json
import os
import re
import sys
import tempfile

import fetch_flights as ff

# 설정·항공기 DB·app_data 를 두는 폴더 = exe 폴더 (개발 실행이면 저장소 폴더). 미리보기·시험에서는 바꿔 씀
APP_DIR = ff.APP_DIR
SETTINGS_NAME = "fetch_settings.json"                      # 명령창 버전(fetch_flights)과 같은 파일
WEB_URL = "https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5"
# 예전 기본 저장 폴더(문서\OpenSky_CSV) — 설정에 자동으로 저장돼 있던 것이면 새 기본값으로 바꿔 씀
OLD_DEFAULTS = {os.path.normcase(os.path.abspath(os.path.join(os.path.expanduser("~"), *x, "OpenSky_CSV")))
                for x in (("Documents",), ("OneDrive", "Documents"), ("OneDrive", "문서"), ("문서",))}


def web_dir():
    """분석기 화면 폴더: exe 안(PyInstaller 임시 폴더) 또는 저장소의 web/."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "web")


def app_data_dir():
    """창(WebView2)의 저장소 — 보관함 IndexedDB 와 diag.log."""
    return os.path.join(APP_DIR, "app_data")


def app_version():
    """빌드할 때 GitHub Actions 가 만드는 _build.py 의 버전 (예: "1.3.1"). 개발 실행이면 빈 문자열."""
    try:
        from _build import BUILD
        return BUILD
    except ImportError:
        return ""


def in_temp_dir():
    """zip 을 풀지 않고 압축 파일 안에서 exe 를 실행하면 Windows 가 임시 폴더에 꺼내 실행한다 → 설정·CSV 가 사라짐."""
    t = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    return os.path.normcase(os.path.abspath(APP_DIR)).startswith(t + os.sep)


def load():
    try:
        with open(os.path.join(APP_DIR, SETTINGS_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(d):
    """바뀐 값만 넣어 저장 (다른 값은 그대로)."""
    try:
        cur = load()
        cur.update(d)
        with open(os.path.join(APP_DIR, SETTINGS_NAME), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
    except OSError:
        pass


def default_out_dir():
    """기본 저장 폴더 = FlightData.exe 가 있는 폴더 안의 OpenSky_CSV (사용자 요청 2026-10-28, 예전엔 문서 폴더)."""
    return os.path.join(APP_DIR, "OpenSky_CSV")


def out_dir():
    """지금 저장 폴더. 비어 있거나 예전 기본값이면 새 기본값."""
    d = load().get("out_dir") or ""
    if not d or os.path.normcase(os.path.abspath(d)) in OLD_DEFAULTS:
        return default_out_dir()
    # 예전 버전 폴더(FlightData_x.y.z\OpenSky_CSV)를 가리키는데 그 폴더가 없어졌으면(업데이트로 이름이 바뀜) 지금 기본값
    if not os.path.isdir(d) and os.path.basename(d.rstrip("\\/")).lower() == "opensky_csv" \
            and re.fullmatch(r"flightdata_\d+\.\d+\.\d+", os.path.basename(os.path.dirname(d.rstrip("\\/"))).lower()):
        return default_out_dir()
    return d


def out_dir_value(d):
    """설정에 넣을 값: 기본 폴더면 "" (경로를 박아 두지 않아야 폴더째 옮기거나 이름이 바뀌어도 따라감)."""
    return "" if os.path.normcase(os.path.abspath(d)) == os.path.normcase(default_out_dir()) else d
