"""한국공항공사 항공기 운항정보 (재난안전데이터공유플랫폼 DSSP-IF-00052) — 김포공항 운항 실적.

- 김포(GMP) 한 공항의 실제 도착·출발 기록: 날짜, 항공사(ICAO)·편명, 예정·실제 시각(현지), 기종(ICAO 코드), 상대 공항(IATA),
  도착·출발 구분(I/O), 운행 상태(Nrm 정상 · Dly 지연). 결항은 기록되지 않음. 2024-01-01 부터 (2025-09-26 부터 약 40일 공백)
- 조회 조건(날짜·공항)은 받지 않아 전체를 한 번에 1,000건씩 받는다 (약 375회, 하루 한도 1,000회).
  기록이 날짜순으로 쌓이지 않아 새 기록만 골라 받을 수 없음 → 전체를 받아 MAX_AGE 일 동안 캐시로 씀
- 쓰임: ① 김포 분석은 스케줄(계획) 대신 이 실적 ② 다른 국내 공항 스케줄의 김포 노선 편에 같은 날·같은 편 기종을 붙임

인증키: ⚙ 설정에서 넣으면 Windows 자격 증명 관리자, 없으면 환경 변수 SAFETYDATA_KEY.
"""
import datetime as dt
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00052"
PAGE = 1000                                                  # 이 API 의 한 번 최대
MAX_AGE = 7                                                  # 캐시를 다시 받기 전까지 쓰는 날 수
AIRPORT = "RKSS"
_KEY_USER = "~safetydata.go.kr"


class _Stop(Exception):
    pass


# ---------- 인증키 ----------

def clean_key(k):
    k = (k or "").strip()
    return urllib.parse.unquote(k) if "%" in k else k


def _env_key():
    k = os.environ.get("SAFETYDATA_KEY")
    if not k and sys.platform.startswith("win"):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "SAFETYDATA_KEY")[0]
        except OSError:
            k = None
    return clean_key(k)


def load_key():
    try:
        import opensky_auth as oa
        k = oa.load_password(_KEY_USER)
    except Exception:  # noqa: BLE001
        k = None
    return clean_key(k) or _env_key()


def save_key(k):
    import opensky_auth as oa
    k = clean_key(k)
    return oa.save_password(_KEY_USER, k) if k else oa.forget_password(_KEY_USER)


# ---------- API ----------

def _call(key, page, rows=PAGE):
    q = {"serviceKey": key, "returnType": "json", "pageNo": page, "numOfRows": rows}
    try:
        with urllib.request.urlopen(BASE + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"재난안전데이터공유플랫폼에 접속하지 못했습니다: {e.reason}") from None
    try:
        j = json.loads(raw)
    except ValueError:
        raise RuntimeError("재난안전데이터공유플랫폼 응답을 읽지 못했습니다.") from None
    h = j.get("header") or {}
    if h.get("resultCode") not in ("00", None) or "body" not in j:
        msg = h.get("errorMsg") or h.get("resultMsg") or "알 수 없는 오류"
        raise RuntimeError(f"재난안전데이터공유플랫폼 오류: {msg} — ⚙ 설정의 재난안전데이터 인증키·등록 IP 를 확인하세요")
    body = j.get("body") or []
    return (body if isinstance(body, list) else [body]), int(j.get("totalCount") or 0)


def check_key(key):
    _call(key, 1, 1)


def _compact(r):
    """API 한 행 → [날짜, 콜사인, I/O, 예정 HHMMSS, 실제 HHMMSS, 기종, 상대 공항 IATA, 상태, 생성 일시]"""
    s = lambda k: str(r.get(k) or "").strip()
    return [s("DT")[:10].replace("/", "-"), s("ARMN_CD").upper() + s("FLIGHT_NM").upper(), s("ARVL_DPTRE_SE").upper(),
            s("PRNMNT_TM").zfill(6), s("ARVL_DPTRE_TM").zfill(6), s("KOMA").upper(), s("ARPR_CD_ARVL_DPTRE").upper(),
            s("OPR_STTS"), s("CRT_DT")]


def dedup(rows):
    """같은 날·편·방향·예정 시각·상대 공항이 여러 번 들어 있으면 마지막에 만든 기록 하나만 (실제로 같은 기록이 두 번 든 경우가 많음)."""
    best = {}
    for r in rows:
        k = (r[0], r[1], r[2], r[3], r[6])
        if k not in best or r[8] > best[k][8]:
            best[k] = r
    return sorted(best.values(), key=lambda r: (r[0], r[4]))


def fetch(key, log=print, should_stop=None):
    out, page, total = [], 1, None
    while True:
        if should_stop and should_stop():
            raise _Stop
        for attempt in range(3):
            try:
                items, total = _call(key, page)
                break
            except RuntimeError as e:
                if attempt == 2 or "인증키" in str(e):
                    raise
                log(f"  오류: {e} → 5초 후 재시도")
                time.sleep(5)
        out += [_compact(r) for r in items]
        if page % 50 == 0:
            log(f"  김포 운항 실적 {len(out):,} / {total:,}건")
        if len(items) < PAGE or page * PAGE >= total:
            break
        page += 1
    rows = dedup(out)
    log(f"  김포 운항 실적 {len(out):,}건 받음 (조회 {page}회) → 중복 정리 후 {len(rows):,}건")
    return rows


def _cache_path(cache_root):
    return os.path.join(cache_root, AIRPORT, "kac_actual.json.gz")


def load(cache_root, key=None, log=print, should_stop=None, max_age=MAX_AGE):
    """김포 실적 기록 (캐시가 max_age 일 안이면 그대로). 인증키가 없으면 None. 중지하면 _Stop."""
    path = _cache_path(cache_root)
    old = None
    if os.path.exists(path):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                old = json.load(f)
        except (OSError, ValueError):
            old = None
    if old and (dt.date.today() - dt.date.fromisoformat(old["fetched"])).days < max_age:
        log(f"김포 운항 실적: {old['fetched']} 에 받은 캐시 사용 ({len(old['rows']):,}건)")
        return old["rows"]
    key = key or load_key()
    if not key:
        return old["rows"] if old else None
    log("김포 운항 실적 받는 중 (재난안전데이터공유플랫폼, 약 375회 조회 · 몇 분)")
    try:
        rows = fetch(key, log, should_stop)
    except RuntimeError as e:
        if old:
            log(f"  {e} → {old['fetched']} 에 받은 캐시 사용")
            return old["rows"]
        raise
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"fetched": dt.date.today().isoformat(), "rows": rows}, f, ensure_ascii=False, separators=(",", ":"))
    return rows


# ---------- 쓰기 ----------

def _ts(day, hhmmss, sched, tz):
    """현지 날짜 + 실제 시각 → UTC 초. 예정과 12시간 넘게 차이 나면 자정을 넘긴 것으로 보고 하루 옮김."""
    h, m = int(hhmmss[:2]), int(hhmmss[2:4])
    d = dt.date.fromisoformat(day)
    if sched.isdigit() and len(sched) == 6:
        diff = (h * 60 + m) - (int(sched[:2]) * 60 + int(sched[2:4]))
        d += dt.timedelta(days=1 if diff < -720 else -1 if diff > 720 else 0)
    t = dt.datetime(d.year, d.month, d.day, h, m, tzinfo=dt.timezone.utc)
    return int(t.timestamp() - tz * 3600)


def type_index(rows):
    """{(콜사인, 김포 기준 날짜, 김포 기준 I/O): 기종}"""
    return {(r[1], r[0], r[2]): r[5] for r in rows if r[5]}


def days_covered(rows, min_flights=100):
    """기록이 충분한 날 (공백 기간·기록이 일부만 있는 날은 빼고 스케줄로 채움)."""
    n = {}
    for r in rows:
        n[r[0]] = n.get(r[0], 0) + 1
    return {d for d, c in n.items() if c >= min_flights}


def flights(rows, start, end, tz, ap=None, days=None):
    """기간(현지 start~end, days 가 있으면 그 날만) 김포 운항 → [(icao24, callsign, firstseen, lastseen, dep, arr, typecode), …]"""
    ap = ap or {}
    out = []
    for r in rows:
        day, cs, io, sched, act, typ, other = r[:7]
        if not (start <= day <= end) or (days is not None and day not in days) or io not in ("I", "O"):
            continue
        if not (act.isdigit() or sched.isdigit()):
            continue
        t = _ts(day, act if act.isdigit() else sched, sched, tz)
        o = ap.get(other, other)
        out.append((cs, cs, "", t, o, AIRPORT, typ) if io == "I" else (cs, cs, t, "", AIRPORT, o, typ))
    return out
