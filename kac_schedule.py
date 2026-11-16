"""한국공항공사 항공기 운항 스케줄(공공데이터포털 15158949)로 공항 운항 CSV 를 만든다.

인천을 뺀 한국공항공사 관할 14개 공항은 OpenSky 대신 이 스케줄만 쓴다 (OpenSky 서버에 접속하지 않음, 로그인 불필요).
- 국내선 /dom: 운항 시작·종료일 + 요일별 운항 여부 + 출발·도착 시각(현지, HHMM) — 2008년 기록부터 있음
- 국제선 /int: 이 공항(airportCode) 기준 IN/OUT 과 시각 하나
- 계획 운항이다: 결항·지연·부정기편·훈련 비행은 들어 있지 않다

결과 CSV 는 fetch_flights.py 와 같은 열(icao24·callsign·firstseen·lastseen·estdepartureairport·estarrivalairport…)이라
분석기가 그대로 읽는다. icao24 자리에는 편명(같은 분에 도착하는 두 편이 하나로 합쳐지지 않게), source 열 = "KAC".

인증키: ⚙ 설정에서 넣으면 Windows 자격 증명 관리자에 저장. 없으면 환경 변수 DATA_GO_KR_KEY.
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://apis.data.go.kr/B551178/flight-schedule"
PAGE = 100                                                   # 이 API 는 한 번에 100건까지 (1000 이면 HTTP 오류)
KAC_AIRPORTS = {                                             # 한국공항공사 관할 (인천 RKSI 는 인천국제공항공사)
    "RKSS": "GMP", "RKPK": "PUS", "RKPC": "CJU", "RKTN": "TAE", "RKJJ": "KWJ", "RKTU": "CJJ", "RKJB": "MWX",
    "RKPU": "USN", "RKJY": "RSU", "RKTH": "KPO", "RKPS": "HIN", "RKNW": "WJU", "RKJK": "KUV", "RKNY": "YNY",
}
SOURCE = "KAC"
_DOM_DAYS = ["domesticMon", "domesticTue", "domesticWed", "domesticThu", "domesticFri", "domesticSat", "domesticSun"]
_INT_DAYS = [d.replace("domestic", "international") for d in _DOM_DAYS]
_KEY_USER = "~data.go.kr"                                    # 자격 증명 관리자 항목 이름 (OpenSky 사용자명과 겹치지 않게)
_HERE = os.path.dirname(os.path.abspath(__file__))


class KeyMissing(RuntimeError):
    pass


def is_kac(icao):
    return (icao or "").strip().upper() in KAC_AIRPORTS


# ---------- 인증키 ----------

def clean_key(k):
    k = (k or "").strip()
    return urllib.parse.unquote(k) if "%" in k else k      # 포털의 Encoding 키를 넣어도 됨


def _env_key():
    k = os.environ.get("DATA_GO_KR_KEY")
    if not k and sys.platform.startswith("win"):           # setx 로 저장한 값은 이미 떠 있는 프로세스에 안 보임
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
                k = winreg.QueryValueEx(h, "DATA_GO_KR_KEY")[0]
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

def _call(key, op, **params):
    q = {"serviceKey": key, "type": "json", **params}
    url = f"{BASE}/{op}?" + urllib.parse.urlencode(q)
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
    except urllib.error.URLError as e:
        raise RuntimeError(f"공공데이터포털에 접속하지 못했습니다: {e.reason}") from None
    try:
        j = json.loads(raw)
    except ValueError:
        raise RuntimeError("공공데이터포털 응답을 읽지 못했습니다.") from None
    if "response" not in j:                                  # 게이트웨이 오류: 키 미등록·호출 한도 등
        h = j.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader", {})
        msg = h.get("returnAuthMsg") or h.get("errMsg") or "알 수 없는 오류"
        if "SERVICE_KEY" in (h.get("errMsg") or ""):
            msg += " — ⚙ 설정의 공공데이터포털 인증키를 확인하세요 (활용 신청 직후에는 1시간쯤 걸릴 수 있음)"
        raise RuntimeError(f"공공데이터포털 오류: {msg}")
    head = j["response"].get("header", {})
    if head.get("resultCode") not in ("00", None):
        raise RuntimeError(f"공공데이터포털 오류: {head.get('resultMsg')}")
    body = j["response"].get("body") or {}
    items = (body.get("items") or {}).get("item") or []
    return (items if isinstance(items, list) else [items]), int(body.get("totalCount") or 0)


def check_key(key):
    """키로 1건 조회해 본다 (틀리면 RuntimeError)."""
    _call(key, "dom", pageNo=1, numOfRows=1)


class _Stop(Exception):
    pass


class _Fetcher:
    """페이지를 넘기면 순서가 고정되지 않아 페이지끼리 기록이 겹치고 그만큼 다른 기록이 빠진다
    (2026-11-16 김해 국제선: 7,748건 중 1,936건이 겹침, 결과적으로 2025 운항의 약 40% 누락).
    그래서 편명 앞부분(schFlightNum, 포함 검색)을 항공사 코드 → 숫자 한 자리씩 늘려 100건 이하로 나눠
    한 페이지 조회만 쓴다. 한 편명이 100건을 넘을 때만 페이지 크기를 바꿔 가며 받은 것을 합친다."""

    SIZES = (100, 60, 51, 34, 27)                            # 크기마다 겹치는 위치가 달라 합치면 채워짐

    def __init__(self, key, log=print, should_stop=None):
        self.key, self.log, self.should_stop, self.calls = key, log, should_stop, 0

    def get(self, op, page=1, rows=PAGE, **flt):
        if self.should_stop and self.should_stop():
            raise _Stop
        for attempt in range(3):
            try:
                self.calls += 1
                return _call(self.key, op, pageNo=page, numOfRows=rows, **flt)
            except RuntimeError as e:
                if attempt == 2 or "인증키" in str(e):
                    raise
                self.log(f"  오류: {e} → 5초 후 재시도")
                time.sleep(5)

    def pages(self, op, rows=PAGE, **flt):
        out, page = [], 1
        while True:
            items, total = self.get(op, page, rows, **flt)
            out += items
            if not items or page * rows >= total:
                return out, total
            page += 1

    def pages_union(self, op, **flt):
        """페이지를 넘겨야 하는 조회: 페이지 크기를 바꿔 가며 받아 합친다 (진짜 중복 기록은 하나로)."""
        got, total = {}, None
        for size in self.SIZES:
            items, total = self.pages(op, size, **flt)
            for x in items:
                got.setdefault(json.dumps(x, sort_keys=True, ensure_ascii=False), x)
            if len(got) >= total:
                break
        return list(got.values())

    def walk(self, op, numf, base, prefix, total, out):
        """편명이 prefix 로 시작하는 기록 → out."""
        if total <= PAGE:
            items, _ = self.get(op, **base, schFlightNum=prefix)
            out += [x for x in items if (x.get(numf) or "").strip().upper().startswith(prefix)]
            return
        rest = total
        if len(prefix) < 6:                                  # 편명은 항공사 2자 + 숫자 4자리까지
            for ch in "0123456789":
                items, t = self.get(op, **base, schFlightNum=prefix + ch)
                if t:
                    rest -= t
                    if t <= PAGE:
                        out += [x for x in items if (x.get(numf) or "").strip().upper().startswith(prefix + ch)]
                    else:
                        self.walk(op, numf, base, prefix + ch, t, out)
        if rest > 0:                                         # 편명이 정확히 prefix 인 기록이 100건 넘음
            out += [x for x in self.pages_union(op, **base, schFlightNum=prefix)
                    if (x.get(numf) or "").strip().upper() == prefix]

    def fetch(self, op, iata):
        numf = "domesticNum" if op == "dom" else "internationalNum"
        bases = [{"schDeptCityCode": iata}, {"schArrvCityCode": iata}]  # 가이드 설명과 달리 Dept = 출발 공항
        first = [self.pages(op, **b) for b in bases]         # 항공사 목록만 얻는 용도 (빠진 기록이 있음)
        airlines = sorted({(x.get(numf) or "").strip().upper()[:2] for items, _ in first for x in items} - {""})
        self.log(f"  {'국내선' if op == 'dom' else '국제선'}: 항공사 {len(airlines)}곳 편명별로 나눠 받는 중")
        out, short = [], 0
        for b, (_, total) in zip(bases, first):
            s = 0
            for al in airlines:
                _, t = self.get(op, **b, schFlightNum=al)    # walk 와 같은 포함 검색 건수
                if t:
                    s += t
                    self.walk(op, numf, b, al, t, out)
            short += max(0, total - s)
        if short:
            self.log(f"  (항공사 목록에 안 잡힌 기록 {short}건 제외)")
        return out


def fetch_airport(key, iata, log=print, should_stop=None):
    """공항 하나의 스케줄 기록 전부 {'dom': [...], 'int': [...]} (출발·도착 둘 다). 중지하면 None."""
    f, res = _Fetcher(key, log, should_stop), {}
    try:
        for op in ("dom", "int"):
            res[op] = f.fetch(op, iata)
            log(f"  {'국내선' if op == 'dom' else '국제선'} 스케줄 {len(res[op]):,}건")
    except _Stop:
        return None
    log(f"  (공공데이터포털 조회 {f.calls:,}회)")
    return res


# ---------- 코드 변환 ----------

def load_maps(mapdata_dir=None):
    """IATA → ICAO: 공항(airports_min.json), 항공사(airlines.json, 같은 IATA 면 한국 항공사 우선)."""
    d = mapdata_dir or os.path.join(_HERE, "web", "mapdata")
    ap, al = {}, {}
    try:
        with open(os.path.join(d, "airports_min.json"), encoding="utf-8") as f:
            for icao, v in json.load(f).items():
                if len(v) > 5 and v[5]:
                    ap.setdefault(v[5].upper(), icao)
        for k, v in KAC_AIRPORTS.items():
            ap[v] = k
        with open(os.path.join(d, "airlines.json"), encoding="utf-8") as f:
            for icao, v in json.load(f).items():
                if v and v[0] and (v[0] not in al or (len(v) > 2 and v[2] == "KR")):
                    al[v[0].upper()] = icao
    except OSError:
        pass
    return ap, al


def callsign_of(num, al):
    """편명(IATA, 예: KE1595) → 콜사인 모양(KAL1595). 분석기는 앞 3자리를 항공사로 쓴다."""
    num = (num or "").strip().upper()
    icao = al.get(num[:2])
    return icao + num[2:] if icao and len(num) > 2 else num


# ---------- 날짜별로 펼치기 ----------

def _d(s):
    return dt.date.fromisoformat((s or "")[:10])


def _ts(day, hhmm, tz):
    hhmm = (hhmm or "").strip().zfill(4)
    h, m = int(hhmm[:2]), int(hhmm[2:4])
    t = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc) + dt.timedelta(hours=h, minutes=m)
    return int(t.timestamp() - tz * 3600)


def expand(records, airport, start, end, tz, ap=None, al=None):
    """스케줄 기록 → 기간(현지 start~end) 안의 운항 행 [(icao24, callsign, firstseen, lastseen, dep, arr), …].
    운항 요일은 출발일 기준. 같은 편·같은 날·같은 방향이 여러 기록에 있으면 운항 시작일이 가장 늦은 것(최신 개정)만."""
    airport = airport.upper()
    iata = KAC_AIRPORTS[airport]
    ap, al = ap or {}, al or {}
    icao_of = lambda c: ap.get((c or "").upper(), (c or "").upper())
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    begin, finish = _ts(s, "0000", tz), _ts(e + dt.timedelta(days=1), "0000", tz)
    best = {}

    def put(key, stdate, row, t):
        if begin <= t < finish and (key not in best or stdate > best[key][0]):
            best[key] = (stdate, row)

    for r in records.get("dom", []):
        dep, arr = (r.get("startcityCode") or "").upper(), (r.get("arrivalcityCode") or "").upper()
        if iata not in (dep, arr) or dep == arr:
            continue
        a, b = max(_d(r["domesticStdate"]), s - dt.timedelta(days=1)), min(_d(r["domesticEddate"]), e)
        num = (r.get("domesticNum") or "").strip().upper()
        d = a
        while d <= b:
            if r.get(_DOM_DAYS[d.weekday()]) == "Y":
                fs = _ts(d, r.get("domesticStartTime"), tz)
                ls = _ts(d, r.get("domesticArrivalTime"), tz)
                if ls < fs:                                  # 자정을 넘겨 도착
                    ls += 86400
                row = (num, callsign_of(num, al), fs, ls, icao_of(dep), icao_of(arr))
                if dep == iata:
                    put((num, "D", d), r["domesticStdate"], row, fs)
                else:
                    put((num, "A", d), r["domesticStdate"], row, ls)
            d += dt.timedelta(days=1)

    for r in records.get("int", []):
        if (r.get("airportCode") or "").upper() != iata:
            continue
        io, other = (r.get("internationalIoType") or "").upper(), icao_of(r.get("cityCode"))
        a, b = max(_d(r["internationalStdate"]), s), min(_d(r["internationalEddate"]), e)
        num = (r.get("internationalNum") or "").strip().upper()
        d = a
        while d <= b:
            if r.get(_INT_DAYS[d.weekday()]) == "Y":
                t = _ts(d, r.get("internationalTime"), tz)
                if io == "IN":
                    put((num, "A", d), r["internationalStdate"], (num, callsign_of(num, al), "", t, other, airport), t)
                elif io == "OUT":
                    put((num, "D", d), r["internationalStdate"], (num, callsign_of(num, al), t, "", airport, other), t)
            d += dt.timedelta(days=1)

    rows = [v[1] for v in best.values()]
    rows.sort(key=lambda r: (r[3] if r[5] == airport else r[2]))
    return rows


# ---------- 수집 (fetch_flights.collect_many 와 같은 모양의 결과) ----------

def _cache_path(cache_root, airport):
    return os.path.join(cache_root, airport, f"kac_schedule_v2_{dt.date.today():%Y-%m-%d}.json")   # v2: 1.5.1 의 누락 캐시를 쓰지 않음


def load_records(airport, cache_root, key=None, log=print, should_stop=None):
    """오늘 받은 기록이 캐시에 있으면 그것을, 없으면 API 에서 받아 캐시에 둔다 (같은 날 다시 받지 않음)."""
    path = _cache_path(cache_root, airport)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            log(f"{airport}: 오늘 받은 한국공항공사 스케줄 캐시 사용")
            return json.load(f)
    key = key or load_key()
    if not key:
        raise KeyMissing("공공데이터포털 인증키가 없습니다. 우측 상단 ⚙ 설정에서 인증키를 등록하세요.")
    log(f"{airport}: 한국공항공사 운항 스케줄 받는 중 (공공데이터포털)")
    recs = fetch_airport(key, KAC_AIRPORTS[airport], log=log, should_stop=should_stop)
    if recs is None:
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for old in os.listdir(os.path.dirname(path)):            # 예전 날짜 캐시는 지움
        if old.startswith("kac_schedule_") and old != os.path.basename(path):
            try:
                os.remove(os.path.join(os.path.dirname(path), old))
            except OSError:
                pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(recs, f, ensure_ascii=False)
    return recs


GMP = "RKSS"
SOURCE_ACTUAL = "KAC_ACT"                                    # 김포 운항 실적 (kac_actual.py)


def _gmp_side(row):
    """스케줄 행의 김포 쪽 (I/O, 시각) — 김포를 오가지 않으면 None."""
    if row[4] == GMP:
        return "O", row[2]
    if row[5] == GMP:
        return "I", row[3]
    return None


def _kst_day(ts):
    return dt.datetime.fromtimestamp(int(ts) + 9 * 3600, dt.timezone.utc).date().isoformat()


def merge_actual(rows, actual, airport, start, end, tz, ap=None):
    """스케줄 행(6칸) + 김포 실적 → [(행 7칸 = …+기종, source), …]
    - 김포를 오가는 편: 김포 기록에 같은 날·같은 편·같은 방향이 있으면 그 기종
    - 김포 자체: 실적 기록이 충분한 날은 스케줄 대신 실적(실제 시각·기종, 결항 제외·부정기편 포함), 나머지 날은 스케줄"""
    import kac_actual
    if not actual:
        return [(r + ("",), SOURCE) for r in rows]
    idx = kac_actual.type_index(actual)
    out = []
    days = None
    if airport == GMP:
        days = {d for d in kac_actual.days_covered(actual) if start <= d <= end}
        rows = [r for r in rows if _kst_day(r[2] if r[4] == GMP else r[3]) not in days]
        out += [(r, SOURCE_ACTUAL) for r in kac_actual.flights(actual, start, end, tz, ap, days)]
    for r in rows:
        g = _gmp_side(r)
        typ = idx.get((r[1], _kst_day(g[1]), g[0]), "") if g and g[1] != "" else ""
        out.append((r + (typ,), SOURCE))
    out.sort(key=lambda x: x[0][3] if (x[0][5] == airport and x[0][3] != "") or x[0][2] == "" else x[0][2])   # 이 공항 쪽 시각
    return out


def collect(airport, start, end, tz, out, cache_root="trino_cache", log=print, should_stop=None, mapdata_dir=None, actual=None):
    """반환: (CSV 경로, 운항 행 목록, 도착 수, 출발 수) — fetch_flights.collect 와 같은 모양. 중지하면 None.
    actual: kac_actual.load() 의 김포 운항 실적 (있으면 김포 노선 편에 기종, 김포는 실적으로)."""
    airport = airport.upper()
    recs = load_records(airport, cache_root, log=log, should_stop=should_stop)
    if recs is None:
        return None
    ap, al = load_maps(mapdata_dir)
    rows = merge_actual(expand(recs, airport, start, end, tz, ap, al), actual, airport, start, end, tz, ap)

    def local(ts):
        return dt.datetime.fromtimestamp(int(ts) + tz * 3600, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if ts != "" else ""
    cols = ["icao24", "callsign", "firstseen", "lastseen", "estdepartureairport", "estarrivalairport", "typecode",
            "firstseen_local", "lastseen_local", "source"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(r + (local(r[2]), local(r[3]), src) for r, src in rows)
    n_arr = sum(1 for r, _ in rows if r[5] == airport)
    n_dep = len(rows) - n_arr
    n_act = sum(1 for _, src in rows if src == SOURCE_ACTUAL)
    n_typ = sum(1 for r, _ in rows if r[6])
    msg = f"완료: {out} (운항 {len(rows):,}건 · 도착 {n_arr:,} · 출발 {n_dep:,}"
    if n_act:
        msg += f" · 김포 운항 실적 {n_act:,}건"
    if actual:
        msg += f" · 기종 확인 {n_typ:,}건 ({n_typ / max(len(rows), 1):.0%})"
    log(msg + ") — 스케줄은 계획 운항, 결항·부정기편 미반영")
    return out, [r for r, _ in rows], n_arr, n_dep
