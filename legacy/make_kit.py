#!/usr/bin/env python3
"""분석기 페이지의 "수집 도구 받기" 버튼용 파일을 만든다.

    python trino/make_kit.py
      → dist/kit/*.txt            (아티팩트에 files 로 올림 — 페이지가 브라우저에서 zip 으로 묶음)
      → dist/opensky_fetch_kit.zip (같은 내용의 zip, 직접 전달용)
"""
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "dist")
FILES = {"run_fetch.bat": "run_fetch.bat.txt", "fetch_flights.py": "fetch_flights.py.txt", "README_KR.txt": "README_KR.txt"}

os.makedirs(os.path.join(DIST, "kit"), exist_ok=True)
with zipfile.ZipFile(os.path.join(DIST, "opensky_fetch_kit.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for name, served in FILES.items():
        src = os.path.join(HERE, name)
        shutil.copyfile(src, os.path.join(DIST, "kit", served))
        z.write(src, f"OpenSky_CSV_Kit/{name}")
print(os.path.abspath(DIST))
