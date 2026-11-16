"""FAA Aircraft Characteristics Database → web/mapdata/aircraft_types.json

출처: FAA Office of Airports, Aircraft Characteristics Database (ICAO 기종 코드 기준, 공항 계획·설계용)
      https://www.faa.gov/airports/engineering/aircraft_char_database — 미국 연방정부 저작물(퍼블릭 도메인)
결과: {ICAO 기종 코드: [모델, 제조사, 날개폭 m, 길이 m, 꼬리 높이 m, 최대이륙중량 kg, ICAO 등급(A~F), ICAO WTC, 주 바퀴 바깥 폭 m]}
  - 날개폭은 윙렛·샤크렛 있는 형과 없는 형 중 큰 값 (같은 기종 코드에 둘 다 있으면 보수적으로)
  - ICAO 등급 = 비행장 참조 코드 문자 (Annex 14 Vol I Table 1-1, 날개폭 기준)
    A < 15 m ≤ B < 24 m ≤ C < 36 m ≤ D < 52 m ≤ E < 65 m ≤ F < 80 m

사용: py -3.13 tools/aircraft/build_types.py [받아 둔 xlsx 경로]   (경로가 없으면 FAA 에서 받음, openpyxl 필요)
"""
import json
import os
import sys
import tempfile
import urllib.request

URL = "https://www.faa.gov/airports/engineering/aircraft_char_database/aircraft_data"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "web", "mapdata", "aircraft_types.json")
FT, LB = 0.3048, 0.45359237


def code_letter(span_m):
    for lim, c in ((15, "A"), (24, "B"), (36, "C"), (52, "D"), (65, "E"), (80, "F")):
        if span_m < lim:
            return c
    return ""                                                  # 80 m 이상: Table 1-1 밖


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build(xlsx):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    rows = list(wb["ACD_Data"].iter_rows(values_only=True))
    head = [str(h).strip() if h else "" for h in rows[0]]
    out = {}
    for r in rows[1:]:
        d = dict(zip(head, r))
        code = str(d.get("ICAO_Code") or "").strip().upper()
        spans = [num(d.get("Wingspan_ft_without_winglets_sharklets")), num(d.get("Wingspan_ft_with_winglets_sharklets"))]
        spans = [s for s in spans if s]
        if not code or not spans:
            continue
        span = round(max(spans) * FT, 2)
        m = lambda k, f=FT: round(num(d.get(k)) * f, 2) if num(d.get(k)) else None
        mtow = num(d.get("MTOW_lb"))
        out[code] = [str(d.get("Model_FAA") or "").strip(), str(d.get("Manufacturer") or "").strip().title(), span,
                     m("Length_ft"), m("Tail_Height_at_OEW_ft"), round(mtow * LB) if mtow else None,
                     code_letter(span), str(d.get("ICAO_WTC") or "").strip(), m("Main_Gear_Width_ft")]
    # 계열 이름 (한국공항공사 운항정보 KOMA 에 A330·B787 처럼 세부형 없이 나옴): 계열 안의 ICAO 등급이 모두 같을 때만,
    # 제원은 계열에서 날개폭이 가장 큰 형. 등급이 섞인 계열(예: B747 = E·F)은 넣지 않음
    for fam, pre, name in (("A330", "A33", "Airbus A330 (계열)"), ("A340", "A34", "Airbus A340 (계열)"), ("A350", "A35", "Airbus A350 (계열)"),
                           ("B767", "B76", "Boeing 767 (계열)"), ("B777", "B77", "Boeing 777 (계열)"), ("B787", "B78", "Boeing 787 (계열)"),
                           ("B737", "B73", "Boeing 737 (계열)"), ("A320", "A32", "")):
        mem = [v for c, v in out.items() if c.startswith(pre) and c != fam]
        if fam in out or not mem or len({v[6] for v in mem}) != 1:
            continue
        big = max(mem, key=lambda v: v[2])
        out[fam] = [name, big[1], *big[2:]]
    return dict(sorted(out.items()))


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if not src:
        src = os.path.join(tempfile.mkdtemp(), "faa_acd.xlsx")
        urllib.request.urlretrieve(URL, src)
    types = build(src)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(types, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(types)}개 기종 → {os.path.normpath(OUT)}")


if __name__ == "__main__":
    main()
