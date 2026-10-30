"""리팩터링 전후 비교용 기준 기록 — 분석기를 실제 서버(local_web)로 띄우고 Edge(Playwright)로 데모를 돌려
장면별 화면 글자·차트 값·스크린샷을 남긴다. OpenSky 에는 접속하지 않는다.

    py -3.13 tools/golden.py <출력 폴더> [--engine]

  --engine : 분석 엔진 결과(tests/js/golden_cases.mjs)도 페이지 안에서 계산해 engine.json 으로 저장
             (분석기가 전역 함수로 노출하던 리팩터링 전 코드에서만 가능)
필요: pip install playwright (브라우저는 설치된 Microsoft Edge 사용)
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402


def start_server(tmp):
    try:
        from app import settings as st                     # 리팩터링 뒤 구조
        st.APP_DIR = tmp
        from app.server import AnalyzerServer
    except ImportError:
        import fetch_flights as ff                         # 리팩터링 전 구조
        ff.APP_DIR = tmp
        ff.SETTINGS = os.path.join(tmp, "fetch_settings.json")
        from local_web import AnalyzerServer
    return AnalyzerServer().url()


CHARTS = """() => Object.values(Chart.instances).filter(c => c.canvas.offsetParent).map(c => ({
  id: c.canvas.id, labels: c.data.labels, data: c.data.datasets.map(d => [d.label, d.data])
})).sort((a, b) => (a.id > b.id ? 1 : -1))"""


def scenes(page):
    """(이름, 실행할 JS) — 데모 실행 후 각 장·보기를 차례로 연다"""
    yield "overview", "document.querySelector('#sideNav [data-pane=overview]').click()"
    for v in ("hour", "day", "wd", "month"):
        yield f"profile_{v}", f"document.querySelector('#sideNav [data-pane=profile]').click(); document.querySelector('[data-ppick={v}]').click()"
    for v in ("route", "airline", "type"):
        yield f"mix_{v}", f"document.querySelector('#sideNav [data-pane=mix]').click(); document.querySelector('[data-mpick={v}]').click()"
    yield "peak", "document.querySelector('#sideNav [data-pane=profile]').click(); const p = document.getElementById('peakOn'); if (!p.checked) p.click(); document.querySelector('#sideNav [data-pane=peak]').click()"
    yield "profile_hour_peak", "document.querySelector('#sideNav [data-pane=profile]').click(); document.querySelector('[data-ppick=hour]').click()"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = os.path.abspath(args[0] if args else os.path.join(ROOT, "preview", "golden"))
    os.makedirs(out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="fd_golden_")
    url = start_server(tmp)
    rec = {}
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        page = b.new_page(viewport={"width": 1600, "height": 1000}, locale="ko-KR", timezone_id="Asia/Seoul")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.wait_for_function("document.getElementById('bootOverlay')?.hidden === true", timeout=30000)
        if "--engine" in sys.argv:
            src = open(os.path.join(ROOT, "tests", "js", "golden_cases.mjs"), encoding="utf-8").read().replace("export function", "function")
            eng = page.evaluate(f"() => {{ {src}; return cases({{ generateDemo, analyze, dateToLocalSec, readFlightsCSV, flightsToMovements }}); }}")
            with open(os.path.join(out, "engine.json"), "w", encoding="utf-8") as f:
                json.dump(eng, f, ensure_ascii=False, indent=1)
        page.screenshot(path=os.path.join(out, "00_home.png"))
        rec["home"] = page.inner_text("#mainView")
        page.evaluate("() => document.getElementById('demoBtn').click()")
        page.wait_for_function("!document.querySelector('#sideNav [data-pane=overview]').disabled", timeout=60000)
        page.wait_for_timeout(800)
        for i, (name, js) in enumerate(scenes(page), 1):
            page.evaluate(f"() => {{ {js} }}")
            page.wait_for_timeout(700)
            page.screenshot(path=os.path.join(out, f"{i:02d}_{name}.png"))
            rec[name] = {"text": page.inner_text("#results"), "side": page.inner_text("#sidePanel"), "charts": page.evaluate(CHARTS)}
        # 여러 해 (연별 탭)
        page.evaluate("() => { document.querySelector('#sideNav [data-pane=data]').click(); }")
        page.fill("#startDate", "2023-01-01")
        page.fill("#endDate", "2025-12-31")
        page.evaluate("() => { document.getElementById('runBtn').click(); }")
        page.wait_for_timeout(4000)
        page.evaluate("() => { document.querySelector('#sideNav [data-pane=profile]').click(); document.querySelector('[data-ppick=year]').click(); }")
        page.wait_for_timeout(700)
        page.screenshot(path=os.path.join(out, "99_profile_year.png"))
        rec["profile_year"] = {"text": page.inner_text("#results"), "charts": page.evaluate(CHARTS)}
        rec["errors"] = errors
        b.close()
    with open(os.path.join(out, "ui.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print(f"{out}: 장면 {len(rec) - 1}개, 페이지 오류 {len(errors)}개")
    for e in errors:
        print("  !", e)


if __name__ == "__main__":
    main()
