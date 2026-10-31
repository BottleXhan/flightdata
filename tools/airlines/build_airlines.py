"""항공사 대응표 만들기: 편명 앞 3자리(ICAO 항공사 코드) → [IATA 코드, 이름, 나라(ISO 2자리), 한글 이름].

    py -3.13 tools/airlines/build_airlines.py        # → web/mapdata/airlines.json

자료: OpenFlights airlines.dat · countries.dat (https://openflights.org/data, Open Database License (ODbL) 1.0).
그래서 만든 airlines.json 도 ODbL 을 따른다 (출처 표시: 설정 › 데이터 출처, README).
OpenFlights 자료는 오래된 곳이 있어(운항 중인 화물 항공사가 '중단'으로, 신생 항공사 없음) 아래 OVERRIDE 로 보정한다.
IATA 코드는 로고(pics.avs.io)를 찾는 데 쓰므로, 운항 중이 아닌 항공사에는 넣지 않는다 (같은 코드를 지금 다른 항공사가 씀).
"""
import csv
import io
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "web", "mapdata", "airlines.json")
SRC = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/"

# ICAO: (IATA, 이름, 나라, 한글 이름) — OpenFlights 에 없거나 틀린 곳 (2026-10 기준)
OVERRIDE = {
    "KAL": ("KE", "Korean Air", "KR", "대한항공"),
    "AAR": ("OZ", "Asiana Airlines", "KR", "아시아나항공"),
    "JJA": ("7C", "Jeju Air", "KR", "제주항공"),
    "JNA": ("LJ", "Jin Air", "KR", "진에어"),
    "TWB": ("TW", "T'way Air", "KR", "티웨이항공"),
    "ABL": ("BX", "Air Busan", "KR", "에어부산"),
    "ASV": ("RS", "Air Seoul", "KR", "에어서울"),
    "ESR": ("ZE", "Eastar Jet", "KR", "이스타항공"),
    "APZ": ("YP", "Air Premia", "KR", "에어프레미아"),
    "EOK": ("RF", "Aero K", "KR", "에어로케이"),
    "HGG": ("4H", "Hi Air", "KR", "하이에어"),
    "KJA": ("", "Air Incheon", "KR", "에어인천"),
    "FDX": ("FX", "FedEx Express", "US", ""),
    "UPS": ("5X", "UPS Airlines", "US", ""),
    "CKS": ("K4", "Kalitta Air", "US", ""),
    "GTI": ("5Y", "Atlas Air", "US", ""),
    "PAC": ("PO", "Polar Air Cargo", "US", ""),
    "ABW": ("RU", "AirBridgeCargo", "RU", ""),
    "CAO": ("CA", "Air China Cargo", "CN", ""),
    "CKK": ("CK", "China Cargo Airlines", "CN", ""),
    "VJC": ("VJ", "VietJet Air", "VN", ""),
    "TTW": ("IT", "Tigerair Taiwan", "TW", ""),
    "SJX": ("JX", "Starlux Airlines", "TW", ""),
    "HKE": ("UO", "HK Express", "HK", ""),
    "CRK": ("HX", "Hong Kong Airlines", "HK", ""),
    "APJ": ("MM", "Peach", "JP", ""),
    "JJP": ("GK", "Jetstar Japan", "JP", ""),
    "SJO": ("IJ", "Spring Japan", "JP", ""),
    "ZIP": ("ZG", "ZIPAIR", "JP", ""),
}
# OpenFlights 나라 이름 중 countries.dat 와 다르게 적힌 것
COUNTRY_ALIAS = {
    "South Korea": "KR", "Republic of Korea": "KR", "Hong Kong SAR of China": "HK", "Macao SAR of China": "MO",
    "Taiwan": "TW", "Russia": "RU", "Vietnam": "VN", "Iran": "IR", "Syria": "SY", "Laos": "LA",
    "Ivory Coast": "CI", "Congo (Kinshasa)": "CD", "Congo (Brazzaville)": "CG", "Macedonia": "MK",
    "Moldova": "MD", "Tanzania": "TZ", "Bolivia": "BO", "Venezuela": "VE", "Brunei": "BN", "Burma": "MM",
    "Czech Republic": "CZ", "Cape Verde": "CV", "Swaziland": "SZ", "East Timor": "TL", "Palestine": "PS",
    "Democratic People's Republic of Korea": "KP", "Democratic Republic of Congo": "CD", "Democratic Republic of the Congo": "CD",
    "Republic of the Congo": "CG", "Faroe Islands": "FO", "Kyrgyzstan": "KG", "Lao Peoples Democratic Republic": "LA",
    "Netherland": "NL", "Russian Federation": "RU", "Saint Kitts and Nevis": "KN", "Saint Lucia": "LC",
    "Saint Vincent and the Grenadines": "VC", "Somali Republic": "SO", "Syrian Arab Republic": "SY", "UNited Kingdom": "GB",
}


def fetch(name):
    with urllib.request.urlopen(SRC + name, timeout=60) as r:
        return r.read().decode("utf-8")


def main():
    cc = {row[0]: row[1] for row in csv.reader(io.StringIO(fetch("countries.dat"))) if len(row) >= 2 and row[1]}
    cc.update(COUNTRY_ALIAS)
    rows = [r for r in csv.reader(io.StringIO(fetch("airlines.dat"))) if len(r) >= 8]
    active_iata = {r[3] for r in rows if r[7] == "Y" and len(r[3]) == 2}
    out, unknown = {}, set()
    # 운항 중인 것을 먼저 넣어, 같은 ICAO 의 옛 항공사가 덮어쓰지 않게
    for r in sorted(rows, key=lambda r: r[7] != "Y"):
        _, name, _, iata, icao, _, country, active = r[:8]
        if len(icao) != 3 or not icao.isalpha() or icao in out:
            continue
        c = cc.get(country, "")
        if country and not c:
            unknown.add(country)
        iata = iata if active == "Y" and len(iata) == 2 and iata != "-" else ""
        if not iata and active != "Y" and r[3] in active_iata:
            iata = ""                                    # 옛 항공사 코드를 지금 다른 곳이 씀 → 로고 없음
        out[icao] = [iata, name.strip(), c, ""]
    for icao, v in OVERRIDE.items():
        out[icao] = list(v)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(out.items())), f, ensure_ascii=False, separators=(",", ":"))
    print(f"{OUT}: {len(out)}곳 (IATA 있음 {sum(1 for v in out.values() if v[0])})")
    if unknown:
        print("나라 코드를 모르는 이름:", ", ".join(sorted(unknown)))


if __name__ == "__main__":
    main()
