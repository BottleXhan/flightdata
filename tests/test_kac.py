"""한국공항공사 스케줄 → 운항 행 펼치기 (네트워크 없이)."""
import collections as C
import datetime as dt

import kac_schedule as kac


def dom(num, dep, arr, t_dep, t_arr, st, ed, days, **kw):
    r = {"domesticNum": num, "startcityCode": dep, "arrivalcityCode": arr, "domesticStartTime": t_dep,
         "domesticArrivalTime": t_arr, "domesticStdate": st + "T00:00:00", "domesticEddate": ed + "T00:00:00"}
    for i, k in enumerate(kac._DOM_DAYS):
        r[k] = "Y" if i in days else "N"
    r.update(kw)
    return r


def kst(s):
    return int(dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone(dt.timedelta(hours=9))).timestamp())


AP = {"GMP": "RKSS", "USN": "RKPU", "CJU": "RKPC", "FUK": "RJFF"}
AL = {"KE": "KAL", "7C": "JJA"}


def test_expand_weekdays_times_and_codes():
    recs = {"dom": [dom("KE1843", "GMP", "USN", "0800", "0900", "2026-11-01", "2026-11-30", {0, 2}),   # 월·수
                    dom("KE1844", "USN", "GMP", "0930", "1030", "2026-11-01", "2026-11-30", {0})]}
    rows = kac.expand(recs, "RKPU", "2026-11-09", "2026-11-11", 9, AP, AL)   # 11-09 월, 11-11 수
    arr = [r for r in rows if r[5] == "RKPU"]
    dep = [r for r in rows if r[4] == "RKPU"]
    assert [r[3] for r in arr] == [kst("2026-11-09 09:00"), kst("2026-11-11 09:00")]
    assert dep == [("KE1844", "KAL1844", kst("2026-11-09 09:30"), kst("2026-11-09 10:30"), "RKPU", "RKSS")]
    assert arr[0][1] == "KAL1843" and arr[0][4] == "RKSS" and arr[0][2] == kst("2026-11-09 08:00")


def test_expand_period_bounds_and_latest_revision_wins():
    recs = {"dom": [dom("7C171", "GMP", "USN", "0600", "0700", "2026-01-01", "2026-12-31", set(range(7))),
                    dom("7C171", "GMP", "USN", "0610", "0715", "2026-03-01", "2026-12-31", set(range(7)))]}
    rows = kac.expand(recs, "RKPU", "2026-03-01", "2026-03-01", 9, AP, AL)
    assert len(rows) == 1 and rows[0][3] == kst("2026-03-01 07:15")     # 같은 날 같은 편: 운항 시작일이 늦은 기록
    assert kac.expand(recs, "RKPU", "2026-02-28", "2026-02-28", 9, AP, AL)[0][3] == kst("2026-02-28 07:00")
    assert kac.expand(recs, "RKPU", "2027-01-01", "2027-01-31", 9, AP, AL) == []


def test_expand_overnight_arrival_counts_on_arrival_day():
    recs = {"dom": [dom("KE9", "CJU", "USN", "2330", "0030", "2026-05-01", "2026-05-31", set(range(7)))]}
    rows = kac.expand(recs, "RKPU", "2026-05-10", "2026-05-10", 9, AP, AL)
    assert [r[3] for r in rows] == [kst("2026-05-10 00:30")]          # 05-09 출발편이 05-10 도착


def test_expand_international_in_out():
    days = {k.replace("domestic", "international"): "Y" for k in kac._DOM_DAYS}
    recs = {"int": [{"airportCode": "USN", "cityCode": "FUK", "internationalIoType": "IN", "internationalNum": "TW216",
                     "internationalTime": "1500", "internationalStdate": "2026-11-01T00:00:00",
                     "internationalEddate": "2026-11-30T00:00:00", **days},
                    {"airportCode": "PUS", "cityCode": "USN", "internationalIoType": "OUT", "internationalNum": "X1",
                     "internationalTime": "1000", "internationalStdate": "2026-11-01T00:00:00",
                     "internationalEddate": "2026-11-30T00:00:00", **days}]}
    rows = kac.expand(recs, "RKPU", "2026-11-10", "2026-11-10", 9, AP, AL)
    assert rows == [("TW216", "TW216", "", kst("2026-11-10 15:00"), "RJFF", "RKPU")]   # 다른 공항 기록은 무시


def test_kac_airports_and_key_cleaning():
    assert kac.is_kac("rkpu") and kac.is_kac("RKSS") and not kac.is_kac("RKSI") and not kac.is_kac("RJAA")
    assert len(kac.KAC_AIRPORTS) == 14
    assert kac.clean_key("ab%2Bc%3D%3D") == "ab+c==" and kac.clean_key(" ab+c== ") == "ab+c=="
    assert kac.callsign_of("KE1595", AL) == "KAL1595" and kac.callsign_of("ZZ1", AL) == "ZZ1"


def _fake_api(records):
    """실제 API 처럼: 편명은 포함 검색, 한 페이지 100건까지, 페이지 크기에 따라 순서가 달라 페이지끼리 겹침."""
    def call(key, op, pageNo=1, numOfRows=100, **flt):
        assert numOfRows <= 100
        L = [r for r in records[op]
             if all(r.get(k) == v for k, v in flt.items() if k in ("schDeptCityCode", "schArrvCityCode"))
             and flt.get("schFlightNum", "") in r["num"]]
        rot = (numOfRows * 7) % max(len(L), 1)               # 순서가 고정되지 않음
        order = L[rot:] + L[:rot]
        lo = (pageNo - 1) * numOfRows
        lo = max(0, lo - 13 * (pageNo - 1))                  # 페이지마다 앞 페이지와 13건 겹침 → 그만큼 빠짐
        return [dict(r) for r in order[lo:lo + numOfRows]], len(L)
    return call


def test_fetch_gets_every_record_despite_overlapping_pages(monkeypatch):
    recs = [{"num": f"{al}{n}", "schDeptCityCode": "PUS", "seq": i}
            for al, nums in (("BX", range(8100, 8130)), ("KE", range(1, 60)), ("C7", range(700, 703)))
            for n in nums for i in range(7)]
    recs += [{"num": "7C7351", "schDeptCityCode": "PUS", "seq": i} for i in range(130)]   # 100건 넘는 편명, "C7" 포함
    for r in recs:
        r["domesticNum"] = r["num"]
    monkeypatch.setattr(kac, "_call", _fake_api({"dom": recs}))
    f = kac._Fetcher("k", log=lambda *a: None)
    got = f.fetch("dom", "PUS")
    key = lambda r: (r["num"], r["seq"])
    assert sorted(map(key, got)) == sorted(map(key, recs))
    naive, _ = f.pages("dom", schDeptCityCode="PUS")
    assert len({key(r) for r in naive}) < len(recs)          # 그냥 페이지를 넘기면 빠짐 (이 시험의 전제)


def test_fetch_airport_stops(monkeypatch):
    monkeypatch.setattr(kac, "_call", _fake_api({"dom": [], "int": []}))
    assert kac.fetch_airport("k", "PUS", log=lambda *a: None, should_stop=lambda: True) is None


def test_load_maps_prefers_korean_airline():
    ap, al = kac.load_maps()
    assert ap["USN"] == "RKPU" and ap["GMP"] == "RKSS"
    assert al["RS"] == "ASV" and al["KE"] == "KAL"


# ---------- 김포 운항 실적 (kac_actual) ----------
import kac_actual as ka


def act(day, cs, io, sched, actual, typ, other, crt="2025-01-01 00:00:00"):
    return [day, cs, io, sched, actual, typ, other, "Nrm", crt]


def test_actual_dedup_keeps_latest_and_distinct_legs():
    rows = [act("2026-11-09", "KAL1601", "O", "080000", "081000", "BCS3", "USN", "a"),
            act("2026-11-09", "KAL1601", "O", "080000", "081500", "BCS3", "USN", "b"),   # 같은 기록 두 번 → 나중 것
            act("2026-11-09", "ESR261", "O", "065000", "070900", "B38M", "ICN"),
            act("2026-11-09", "ESR261", "O", "124000", "125400", "B38M", "CJU")]        # 같은 편명 다른 구간 → 둘 다
    d = ka.dedup(rows)
    assert len(d) == 3 and [r[4] for r in d if r[1] == "KAL1601"] == ["081500"]


def test_actual_flights_times_and_overnight():
    rows = [act("2026-11-09", "KAL1601", "O", "080000", "081000", "BCS3", "USN"),
            act("2026-11-09", "JJA140", "I", "235000", "001500", "B738", "CJU")]            # 예정 23:50 → 실제 다음날 00:15
    f = ka.flights(rows, "2026-11-09", "2026-11-09", 9, {"USN": "RKPU", "CJU": "RKPC"})
    assert f[0] == ("KAL1601", "KAL1601", kst("2026-11-09 08:10"), "", "RKSS", "RKPU", "BCS3")
    assert f[1] == ("JJA140", "JJA140", "", kst("2026-11-10 00:15"), "RKPC", "RKSS", "B738")


def test_merge_actual_types_for_gimpo_route_and_gimpo_uses_actual():
    sched = {"dom": [dom("KE1601", "GMP", "USN", "0800", "0900", "2026-11-01", "2026-11-30", set(range(7))),
                     dom("KE1801", "CJU", "USN", "1000", "1100", "2026-11-01", "2026-11-30", set(range(7)))]}
    actual = [act("2026-11-09", "KAL1601", "O", "080000", "081000", "BCS3", "USN")] * 1
    rows = kac.merge_actual(kac.expand(sched, "RKPU", "2026-11-09", "2026-11-10", 9, AP, AL), actual, "RKPU", "2026-11-09", "2026-11-10", 9, AP)
    typ = {(r[1], r[3]): r[6] for r, _ in rows}
    assert typ[("KAL1601", kst("2026-11-09 09:00"))] == "BCS3"           # 김포 기록에 같은 날·같은 편
    assert typ[("KAL1601", kst("2026-11-10 09:00"))] == ""               # 그날 김포 기록 없음
    assert typ[("KAL1801", kst("2026-11-09 11:00"))] == ""               # 김포를 오가지 않는 편
    assert {s for _, s in rows} == {"KAC"}
    many = [act("2026-11-09", f"KAL{i}", "O", "090000", "090500", "A321", "CJU") for i in range(120)]   # 기록이 충분한 날만 실적으로
    g = kac.merge_actual(kac.expand(sched, "RKSS", "2026-11-09", "2026-11-10", 9, AP, AL), many, "RKSS", "2026-11-09", "2026-11-10", 9, AP)
    src = C.Counter(s for _, s in g)
    assert src["KAC_ACT"] == 120 and src["KAC"] == 1                     # 11-10 은 스케줄(KE1601 출발)
    assert kac.merge_actual([("X", "X", 1, 2, "RKPU", "RKSS")], None, "RKPU", "a", "b", 9) == [(("X", "X", 1, 2, "RKPU", "RKSS", ""), "KAC")]
