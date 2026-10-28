#!/usr/bin/env python3
"""
OpenSky Trino 에서 특정 공항의 도착·출발 운항을 받아 CSV 로 저장한다.
결과 CSV 는 분석기(icao-peak-hour.html)의 "CSV 파일 불러오기"로 읽는다.

OpenSky "Trino - Historical Data" 가이드의 성능 규칙을 지킨다.
  1. 모든 쿼리에 파티션 열 조건을 건다: flights_data4 는 WHERE day = <UTC 자정 Unix 시각>
  2. 큰 쿼리는 쪼갠다: 하루(day 파티션 1개)씩 따로 조회
  3. 동시 쿼리를 제한한다: 한 번에 하나씩 순서대로 실행
  4. 필요한 열만 고른다: track 같은 큰 배열 열은 읽지 않음
  5. 이미 받은 날은 캐시에서 읽어 다시 조회하지 않는다 (중단 후 이어받기)

day 파티션은 운항이 끝난(lastseen) UTC 날짜 기준이다.
  - 도착: lastseen 이 기간 안 → 기간에 걸친 UTC 날짜들
  - 출발: firstseen 이 기간 안이지만 다음 날 끝날 수 있음 → 마지막 날 + 1일까지 조회

설치:  pip install trino
실행:  python fetch_flights.py --user 내아이디 --airport RKSI --start 2025-01-01 --end 2025-12-31 --tz 9
       (처음 실행하면 브라우저가 열려 OpenSky 로그인을 요청한다)
       인수 없이 실행하면(또는 Windows 에서 run_fetch.bat 더블클릭) 값을 하나씩 물어본다.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

DAY = 86400
TABLE = "flights_data4"
# 설정·항공기 DB 를 둘 폴더: 스크립트 폴더, exe(PyInstaller)로 실행하면 exe 가 있는 폴더
APP_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
COLUMNS = ["icao24", "callsign", "firstseen", "lastseen", "estdepartureairport", "estarrivalairport"]

# 가이드의 "Known Data Gaps" (UTC). 이 구간은 데이터가 영구 손실되어 결과가 과소 집계된다.
KNOWN_GAPS = [
    ("2023-01-02 23:00", "2023-01-03 10:00"),
    ("2023-01-18 11:00", "2023-01-23 07:00"),
    ("2023-06-21 13:00", "2023-06-21 22:00"),
    ("2023-11-15 06:00", "2023-11-16 08:00"),
    ("2023-11-20 01:00", "2023-11-20 03:00"),
    ("2023-12-02 08:00", "2023-12-05 03:00"),
    ("2024-05-20 10:00", "2024-05-21 05:00"),
    ("2026-01-02 19:00", "2026-01-03 18:00"),
    ("2026-01-24 08:00", "2026-01-24 17:00"),
]


def utc_ts(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).timestamp())


def local_date_to_utc(date_str, tz_hours):
    d = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
    return int(d.timestamp() - tz_hours * 3600)


def plan_days(begin_utc, end_utc):
    """조회할 day 파티션 값 목록 (UTC 자정 Unix 시각)."""
    first = begin_utc // DAY * DAY
    last = (end_utc - 1) // DAY * DAY + DAY      # 출발편이 다음 날 끝나는 경우
    return list(range(first, last + 1, DAY))


def overlapping_gaps(begin_utc, end_utc):
    return [(a, b) for a, b in KNOWN_GAPS if utc_ts(a) < end_utc and utc_ts(b) > begin_utc]


def connect(user, on_auth_url=None, password=None, log=print):
    import trino
    from trino.auth import (OAuth2Authentication, CompositeRedirectHandler,
                            ConsoleRedirectHandler, WebBrowserRedirectHandler)
    auth = None
    if password:                                            # 비밀번호 로그인 (브라우저 없이, pyopensky 와 같은 방식)
        from opensky_auth import PasswordToken, LoginError, trino_auth
        tok = PasswordToken(user, password)
        try:
            tok.token()
            auth = trino_auth(tok)
            log("  OpenSky 로그인 성공 (비밀번호)")
        except LoginError as e:
            log(f"  {e} → 브라우저 로그인으로 진행합니다")
    if auth is None:
        # 로그인 주소는 브라우저로 열고 콘솔에도 출력, 필요하면 화면(app.py)에도 전달
        handlers = [WebBrowserRedirectHandler(), ConsoleRedirectHandler()]
        if on_auth_url:
            handlers.append(on_auth_url)
        auth = OAuth2Authentication(redirect_auth_url_handler=CompositeRedirectHandler(handlers))
    # 가이드의 CLI 와 같은 설정: catalog=minio, schema=osky. 사용자명은 소문자.
    return trino.dbapi.connect(
        host="trino.opensky-network.org",
        port=443,
        http_scheme="https",
        user=user.lower(),
        auth=auth,
        catalog="minio",
        schema="osky",
    )


def query_day(conn, day, airports):
    """day 파티션 하나에서 여러 공항(도착 또는 출발)의 운항을 한 번에 조회."""
    if isinstance(airports, str):
        airports = [airports]
    marks = ", ".join("?" for _ in airports)
    sql = (
        f"SELECT {', '.join(COLUMNS)} FROM {TABLE} "
        f"WHERE day = {int(day)} "
        f"AND (estarrivalairport IN ({marks}) OR estdepartureairport IN ({marks}))"
    )
    cur = conn.cursor()
    cur.execute(sql, tuple(airports) * 2)
    rows = cur.fetchall()
    cur.close()
    return rows


def read_cache(path):
    with open(path, newline="", encoding="utf-8-sig") as f:   # BOM 있어도 읽힘
        return [tuple(r[c] for c in COLUMNS) for r in csv.DictReader(f)]


# ── 항공기 정보 (OpenSky aircraft database, https://opensky-network.org/aircraft-database)
# traffic 라이브러리(aircraft.download_opensky)와 같은 주소에서 한 번 내려받아 스크립트 폴더에 둔다.
AIRCRAFT_DB_URL = "https://s3.opensky-network.org/data-samples/metadata/aircraftDatabase.csv"
AIRCRAFT_DB = os.path.join(APP_DIR, "aircraftDatabase.csv")
AIRCRAFT_COLUMNS = ["registration", "typecode", "model", "manufacturer", "operator", "icaoaircrafttype"]
# DB 의 열 이름 후보 (버전에 따라 다를 수 있어 여러 이름을 허용)
_DB_ALIASES = {
    "registration": ["registration"],
    "typecode": ["typecode"],
    "model": ["model"],
    "manufacturer": ["manufacturername", "manufacturer"],
    "operator": ["operator", "owner"],
    "icaoaircrafttype": ["icaoaircrafttype"],
}


def ensure_aircraft_db(log=print):
    """항공기 DB 가 없으면 내려받는다. 실패해도 수집은 계속(기종 열만 비움)."""
    if os.path.exists(AIRCRAFT_DB) and os.path.getsize(AIRCRAFT_DB) > 0:
        return True
    log("항공기 정보 데이터베이스를 처음 한 번 내려받습니다 (수십 MB, 몇 분 걸릴 수 있음)…")
    try:
        import urllib.request
        tmp = AIRCRAFT_DB + ".tmp"
        with urllib.request.urlopen(AIRCRAFT_DB_URL, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, AIRCRAFT_DB)
        return True
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ 항공기 정보 DB 를 받지 못했습니다 ({e}). 기종 열은 비워 둡니다.")
        log(f"    직접 받아 이 폴더에 aircraftDatabase.csv 로 저장해도 됩니다: {AIRCRAFT_DB_URL}")
        return False


def load_aircraft_info(icao24s, log=print):
    """필요한 icao24 만 골라 {icao24: {registration, typecode, ...}} 로 읽는다."""
    if not ensure_aircraft_db(log):
        return {}
    want, info = set(i.lower() for i in icao24s if i), {}
    with open(AIRCRAFT_DB, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        head = [h.strip().strip("'").lower() for h in next(reader)]
        col = {k: [head.index(a) for a in al if a in head] for k, al in _DB_ALIASES.items()}   # 앞에서부터 비어 있지 않은 값 사용
        i_icao = head.index("icao24") if "icao24" in head else None
        if i_icao is None:
            log("  ⚠ 항공기 정보 DB 형식을 알 수 없습니다 (icao24 열 없음).")
            return {}
        for row in reader:
            if len(row) <= i_icao:
                continue
            k = row[i_icao].strip().strip("'").lower()
            if k in want and k not in info:
                info[k] = {c: next((row[j].strip().strip("'") for j in js if j < len(row) and row[j].strip().strip("'")), "")
                           for c, js in col.items()}
    log(f"  항공기 정보: {len(want)}대 중 {len(info)}대 확인 ({len(info) / max(1, len(want)) * 100:.0f}%)")
    return info


def write_rows(path, rows, columns=COLUMNS):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:   # BOM: 엑셀에서 한글·특수문자가 깨지지 않게
        w = csv.writer(f)
        w.writerow(columns)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
    os.replace(tmp, path)


SETTINGS = os.path.join(APP_DIR, "fetch_settings.json")


def ask_args():
    """인수 없이 실행했을 때: 값을 물어보고, 사용자명·공항·오프셋은 다음 실행을 위해 기억한다."""
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}

    def ask(label, default="", check=None):
        while True:
            v = input(f"{label}" + (f" [{default}]" if default else "") + ": ").strip() or default
            if v and (check is None or check(v)):
                return v
            print("  다시 입력하세요.")

    def is_date(v):
        try:
            dt.datetime.strptime(v, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def is_num(v):
        try:
            float(v)
            return True
        except ValueError:
            return False

    print("OpenSky Trino 운항 수집 — Enter 를 누르면 [ ] 안의 값을 사용합니다.\n")
    user = ask("OpenSky 사용자명", saved.get("user", ""))
    airport = ",".join(parse_airports(ask("공항 ICAO 코드 (여러 개는 쉼표로, 예: RKSI,RKSS)", saved.get("airport", "RKSI"),
                                          lambda v: bool(parse_airports(v)) and all(len(x) == 4 for x in parse_airports(v)))))
    tz = ask("현지 UTC 오프셋 (시간)", f"{float(saved.get('tz', 9)):g}", is_num)
    start = ask("시작일 (YYYY-MM-DD)", saved.get("start", ""), is_date)
    end = ask("종료일 (YYYY-MM-DD, 포함)", saved.get("end", ""), is_date)
    try:
        with open(SETTINGS, "w", encoding="utf-8") as f:
            json.dump({"user": user, "airport": airport, "tz": float(tz), "start": start, "end": end}, f, ensure_ascii=False)
    except OSError:
        pass
    print()
    return ["--user", user, "--airport", airport, "--tz", tz, "--start", start, "--end", end]


def main():
    ap = argparse.ArgumentParser(description="OpenSky Trino 공항 운항 수집 (분석기용 CSV)")
    ap.add_argument("--user", required=True, help="OpenSky 사용자명")
    ap.add_argument("--airport", required=True, help="ICAO 공항 코드. 여러 개는 쉼표로 (예: RKSI,RKSS,RKPC)")
    ap.add_argument("--start", required=True, help="시작일 (현지, YYYY-MM-DD)")
    ap.add_argument("--end", required=True, help="종료일 (현지, YYYY-MM-DD, 포함)")
    ap.add_argument("--tz", type=float, default=0, help="현지 UTC 오프셋 시간 (예: 9)")
    ap.add_argument("--out", help="결과 CSV 경로 (기본: <공항>_<시작>_<종료>.csv)")
    ap.add_argument("--cache", default="trino_cache", help="일별 캐시 폴더")
    ap.add_argument("--pause", type=float, default=1.0, help="쿼리 사이 대기 초")
    ap.add_argument("--dry-run", action="store_true", help="쿼리 계획만 출력")
    ap.add_argument("--no-aircraft", action="store_true", help="항공기 정보(기종 등) 열을 붙이지 않음")
    a = ap.parse_args(None if len(sys.argv) > 1 else ask_args())

    try:
        airports = parse_airports(a.airport)
        if not airports or any(len(x) != 4 for x in airports):
            raise ValueError("공항 코드는 4자리 ICAO 코드입니다 (여러 개는 쉼표로 구분).")
        if a.out and len(airports) > 1:
            raise ValueError("--out 은 공항이 하나일 때만 쓸 수 있습니다.")
        collect_many(a.user, airports, a.start, a.end, a.tz, cache_root=a.cache,
                     outs={airports[0]: a.out} if a.out else None,
                     pause=a.pause, dry_run=a.dry_run, aircraft_info=not a.no_aircraft)
    except ValueError as e:
        sys.exit(str(e))


def parse_airports(text):
    """'RKSI, RKSS rkpc' → ['RKSI', 'RKSS', 'RKPC'] (쉼표·공백 구분, 중복 제거)"""
    out = []
    for a in text.replace(",", " ").split():
        a = a.strip().upper()
        if a and a not in out:
            out.append(a)
    return out


def collect(user, airport, start, end_date, tz, cache_root="trino_cache", out=None, pause=1.0,
            dry_run=False, log=print, on_auth_url=None, on_progress=None, should_stop=None,
            aircraft_info=True, password=None):
    """공항 하나 수집 (app.py 호환). 반환: (CSV 경로, 운항 행 목록, 도착 수, 출발 수)."""
    airport = airport.strip().upper()
    res = collect_many(user, [airport], start, end_date, tz, cache_root=cache_root, outs={airport: out} if out else None,
                       pause=pause, dry_run=dry_run, log=log, on_auth_url=on_auth_url, on_progress=on_progress,
                       should_stop=should_stop, aircraft_info=aircraft_info, password=password)
    return res[airport]


def collect_many(user, airports, start, end_date, tz, cache_root="trino_cache", outs=None, pause=1.0,
                 dry_run=False, log=print, on_auth_url=None, on_progress=None, should_stop=None,
                 aircraft_info=True, password=None):
    """여러 공항을 하루씩 함께 조회해 공항별 CSV 를 만든다.
    날짜마다 쿼리는 한 번(아직 캐시 없는 공항만 IN 조건으로), 결과는 공항별 캐시·CSV 로 나눈다.
    반환: {공항: (CSV 경로, 운항 행 목록, 도착 수, 출발 수)}"""
    airports = [a.strip().upper() for a in airports]
    begin = local_date_to_utc(start, tz)
    end = local_date_to_utc(end_date, tz) + DAY
    if end <= begin:
        raise ValueError("종료일이 시작일보다 빠릅니다.")
    days = plan_days(begin, end)
    outs = outs or {}
    for ap in airports:
        outs.setdefault(ap, f"{ap}_{start}_{end_date}.csv")
        os.makedirs(os.path.join(cache_root, ap), exist_ok=True)

    log(f"{', '.join(airports)}: 현지 {start} ~ {end_date} (UTC{tz:+g}) → day 파티션 {len(days)}개를 하루씩 조회"
        + (f" (공항 {len(airports)}곳을 한 쿼리로)" if len(airports) > 1 else ""))
    today_utc = int(time.time()) // DAY * DAY
    if end > today_utc - DAY:
        log("  ⚠ OpenSky 운항 자료는 매일 밤 일괄 갱신됩니다. 최근 1~2일은 자료가 없거나 일부만 있을 수 있으니,"
            " 종료일은 이틀 전 이전으로 하는 것을 권장합니다. (해당 날짜는 캐시하지 않고 다음 실행 때 다시 조회)")
    for g in overlapping_gaps(begin, end):
        log(f"  ⚠ 알려진 데이터 손실 구간과 겹침 (UTC {g[0]} ~ {g[1]}): 이 시간대는 과소 집계됩니다.")
    if dry_run:
        for d in days:
            log(f"  WHERE day = {d}  ({dt.datetime.fromtimestamp(d, dt.timezone.utc):%Y-%m-%d})")
        return {ap: (outs[ap], [], 0, 0) for ap in airports}

    conn = None
    all_rows = {ap: [] for ap in airports}
    for i, d in enumerate(days, 1):
        if should_stop and should_stop():
            raise RuntimeError("사용자가 중지했습니다. 다시 시작하면 받은 날은 건너뜁니다.")
        label = f"{dt.datetime.fromtimestamp(d, dt.timezone.utc):%Y-%m-%d}"
        caches = {ap: os.path.join(cache_root, ap, f"{label}.csv") for ap in airports}
        got = {}
        for ap in airports:
            cached = read_cache(caches[ap]) if os.path.exists(caches[ap]) else None
            if cached:                                      # 0건 캐시는 믿지 않고 다시 조회 (예전에 너무 일찍 조회한 날)
                got[ap] = cached
        need = [ap for ap in airports if ap not in got]
        if need:
            if conn is None:
                conn = connect(user, on_auth_url, password=password, log=log)
            t0 = time.time()
            for attempt in range(3):
                try:
                    rows = query_day(conn, d, need)
                    break
                except Exception as e:                      # 대기열 초과 등: 기다렸다 재시도
                    if attempt == 2:
                        raise
                    wait = 30 * (attempt + 1)
                    log(f"  오류: {e} → {wait}초 후 재시도")
                    time.sleep(wait)
            # 아직 야간 일괄 처리가 끝나지 않았을 수 있는 최근 날짜와 0건은 캐시하지 않음 → 다음 실행 때 다시 조회
            fresh = d >= today_utc - DAY
            for ap in need:
                mine = [r for r in rows if r[4] == ap or r[5] == ap]
                got[ap] = mine
                if mine and not fresh:
                    write_rows(caches[ap], mine)
            counts = " · ".join(f"{ap} {len(got[ap])}" for ap in need)
            log(f"[{i}/{len(days)}] {label} 조회 {counts}건 ({time.time() - t0:.1f}초)"
                + (" — 최근 날짜라 아직 자료가 없거나 일부일 수 있어 저장하지 않음" if fresh else ""))
            time.sleep(pause)
        cached_aps = [ap for ap in airports if ap not in need]
        if cached_aps:
            log(f"[{i}/{len(days)}] {label} 캐시 " + " · ".join(f"{ap} {len(got[ap])}" for ap in cached_aps) + "건")
        for ap in airports:
            all_rows[ap].extend(got[ap])
        if on_progress:
            on_progress(i, len(days))

    # 기간 안의 도착(lastseen)·출발(firstseen)만 남기고 중복 제거
    def local(ts):
        return dt.datetime.fromtimestamp(int(ts) + tz * 3600, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ts != "" else ""
    kept = {}
    for ap in airports:
        seen, keep = set(), []
        for r in all_rows[ap]:
            icao24, callsign, fs, ls, dep, arr = r
            fs = int(fs) if fs not in (None, "") else None
            ls = int(ls) if ls not in (None, "") else None
            is_arr = arr == ap and ls is not None and begin <= ls < end
            is_dep = dep == ap and fs is not None and begin <= fs < end
            key = (icao24, fs, ls)
            if (is_arr or is_dep) and key not in seen:
                seen.add(key)
                keep.append((icao24, (callsign or "").strip(), fs or "", ls or "", dep or "", arr or ""))
        keep.sort(key=lambda r: (r[2] or r[3]))
        kept[ap] = keep
    info = load_aircraft_info({r[0] for k in kept.values() for r in k}, log) if aircraft_info else None

    result = {}
    for ap, keep in kept.items():
        # 엑셀에서 읽기 쉽도록 현지 시각 열 추가 (분석기는 Unix 초 열을 사용)
        out_rows = [r + (local(r[2]), local(r[3])) for r in keep]
        out_cols = COLUMNS + ["firstseen_local", "lastseen_local"]
        if info is not None:
            out_rows = [r + tuple(info.get((r[0] or "").lower(), {}).get(c, "") for c in AIRCRAFT_COLUMNS) for r in out_rows]
            out_cols += AIRCRAFT_COLUMNS
        write_rows(outs[ap], out_rows, out_cols)
        n_arr = sum(1 for r in keep if r[5] == ap and r[3] != "" and begin <= int(r[3]) < end)
        n_dep = sum(1 for r in keep if r[4] == ap and r[2] != "" and begin <= int(r[2]) < end)
        log(f"완료: {outs[ap]} (운항 {len(keep)}건 · 도착 {n_arr} · 출발 {n_dep})")
        result[ap] = (outs[ap], keep, n_arr, n_dep)
    return result

if __name__ == "__main__":
    main()
