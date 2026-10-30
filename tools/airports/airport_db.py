"""공항 찾기: ICAO 코드를 몰라도 이름·도시·IATA·한글 이름으로 찾고, 위치와 시간대(UTC 오프셋)를 알려 준다.

데이터: airports.json — mwgg/Airports (MIT License, https://github.com/mwgg/Airports) 에서
4자리 ICAO 코드가 있는 공항만 추려 [icao, iata, name, city, country, lat, lon, tz] 로 저장.
"""
import datetime as dt
import json
import math
import os
import sys

# 자주 찾는 공항의 한글 이름 (검색용)
KO_NAMES = {
    "RKSI": "인천", "RKSS": "김포", "RKPC": "제주", "RKPK": "김해 부산", "RKTN": "대구", "RKTU": "청주",
    "RKJB": "무안", "RKNY": "양양", "RKJJ": "광주", "RKJY": "여수", "RKPU": "울산", "RKTH": "포항",
    "RKPS": "사천 진주", "RKNW": "원주", "RKJK": "군산", "RKSM": "서울공항 성남",
    "RJTT": "하네다 도쿄", "RJAA": "나리타 도쿄", "RJBB": "간사이 오사카", "RJOO": "이타미 오사카",
    "RJCC": "신치토세 삿포로", "RJFF": "후쿠오카", "ROAH": "나하 오키나와", "RJGG": "주부 나고야",
    "ZBAA": "서우두 베이징", "ZBAD": "다싱 베이징", "ZSPD": "푸둥 상하이", "ZSSS": "훙차오 상하이",
    "ZGGG": "광저우", "ZGSZ": "선전", "ZYTL": "다롄", "ZSQD": "칭다오", "ZYYJ": "옌지",
    "VHHH": "홍콩", "VMMC": "마카오", "RCTP": "타오위안 타이베이", "RCSS": "쑹산 타이베이",
    "WSSS": "창이 싱가포르", "VTBS": "수완나품 방콕", "VTBD": "돈므앙 방콕", "VVNB": "노이바이 하노이",
    "VVTS": "떤선녓 호찌민", "VVDN": "다낭", "RPLL": "마닐라", "RPVM": "세부 막탄", "WIII": "자카르타",
    "WADD": "발리 덴파사르", "WMKK": "쿠알라룸푸르", "OMDB": "두바이", "OTHH": "도하", "EGLL": "히드로 런던",
    "LFPG": "샤를드골 파리", "EDDF": "프랑크푸르트", "EHAM": "스히폴 암스테르담", "KLAX": "로스앤젤레스",
    "KJFK": "존에프케네디 뉴욕", "KSFO": "샌프란시스코", "KSEA": "시애틀", "PANC": "앵커리지",
    "PHNL": "호놀룰루", "PGUM": "괌", "PGSN": "사이판", "YSSY": "시드니", "CYVR": "밴쿠버",
}


def _data_path():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))   # exe 안에 묶인 경우
    return os.path.join(base, "airports.json")


class Airport:
    __slots__ = ("icao", "iata", "name", "city", "country", "lat", "lon", "tz", "ko")

    def __init__(self, row):
        self.icao, self.iata, self.name, self.city, self.country, self.lat, self.lon, self.tz = row
        self.ko = KO_NAMES.get(self.icao, "")

    def label(self):
        code = self.icao + (f" · {self.iata}" if self.iata else "")
        place = ", ".join(x for x in (self.city, self.country) if x)
        return f"{code}   {self.name}" + (f" — {place}" if place else "") + (f"  ({self.ko})" if self.ko else "")

    def utc_offset(self, day=None):
        """그 날 현지 자정의 UTC 오프셋(시간). 시간대를 모르면 None."""
        if not self.tz:
            return None
        try:
            from zoneinfo import ZoneInfo
            d = day or dt.date.today()
            off = dt.datetime(d.year, d.month, d.day, 12, tzinfo=ZoneInfo(self.tz)).utcoffset()
            return off.total_seconds() / 3600
        except Exception:  # noqa: BLE001 — tzdata 가 없거나 시간대 이름이 낯설면
            return None


class AirportDB:
    def __init__(self):
        with open(_data_path(), encoding="utf-8") as f:
            self.items = [Airport(r) for r in json.load(f)]
        self.by_icao = {a.icao: a for a in self.items}

    def get(self, icao):
        return self.by_icao.get((icao or "").strip().upper())

    def search(self, query, limit=60):
        q = (query or "").strip().lower()
        if not q:
            return []
        scored = []
        for a in self.items:
            if q == a.icao.lower() or (a.iata and q == a.iata.lower()):
                s = 0
            elif a.ko and q in a.ko:
                s = 1
            elif a.name.lower().startswith(q) or a.city.lower().startswith(q):
                s = 2
            elif q in a.name.lower() or q in a.city.lower() or a.icao.lower().startswith(q):
                s = 3
            else:
                continue
            scored.append((s, 0 if a.iata else 1, a.icao, a))      # 같은 점수면 IATA 있는(큰) 공항 먼저
        scored.sort(key=lambda x: x[:3])
        return [x[3] for x in scored[:limit]]

    def nearest(self, lat, lon, max_km=30):
        """지도에서 누른 곳과 가장 가까운 공항 (IATA 있는 큰 공항에 5km 가산점)."""
        best, bd = None, None
        dlat = max_km / 111 + 0.1
        dlon = dlat / max(0.2, math.cos(math.radians(lat)))
        for a in self.items:
            if abs(a.lat - lat) > dlat or abs(a.lon - lon) > dlon:
                continue
            p1, p2 = math.radians(lat), math.radians(a.lat)
            h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(a.lon - lon) / 2) ** 2
            km = 12742 * math.asin(math.sqrt(h))
            score = km - (min(5, max_km * 0.2) if a.iata else 0)
            if km <= max_km and (bd is None or score < bd):
                best, bd = a, score
        return best
