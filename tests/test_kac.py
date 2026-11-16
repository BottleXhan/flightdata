"""한국공항공사 스케줄 → 운항 행 펼치기 (네트워크 없이)."""
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


def test_load_maps_prefers_korean_airline():
    ap, al = kac.load_maps()
    assert ap["USN"] == "RKPU" and ap["GMP"] == "RKSS"
    assert al["RS"] == "ASV" and al["KE"] == "KAL"
