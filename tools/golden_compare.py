"""tools/golden.py 로 남긴 두 기록을 비교한다 (화면 글자·차트 값·엔진 결과).

    py -3.13 tools/golden_compare.py <기준 폴더> <비교 폴더>
"""
import difflib
import json
import os
import sys


def load(d, name):
    p = os.path.join(d, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def main():
    a, b = sys.argv[1:3]
    bad = 0
    ua, ub = load(a, "ui.json"), load(b, "ui.json")
    for k in ua:
        va, vb = ua[k], ub.get(k)
        if va == vb:
            continue
        bad += 1
        print(f"✗ {k}")
        if isinstance(va, dict) and isinstance(vb, dict):
            for f in va:
                if va[f] != vb.get(f):
                    sa = va[f] if isinstance(va[f], str) else json.dumps(va[f], ensure_ascii=False, indent=0)
                    sb = vb.get(f) if isinstance(vb.get(f), str) else json.dumps(vb.get(f), ensure_ascii=False, indent=0)
                    for line in list(difflib.unified_diff(sa.splitlines(), sb.splitlines(), lineterm="", n=0))[2:14]:
                        print("   ", f, line[:160])
        else:
            print("   ", str(va)[:200], "→", str(vb)[:200])
    ea, eb = load(a, "engine.json"), load(b, "engine.json")
    if ea is not None and eb is not None:
        if ea != eb:
            bad += 1
            print("✗ engine.json 다름")
    print("같음" if not bad else f"다른 항목 {bad}개")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
