"""FlightData 프로그램(exe) 화면 미리보기 — exe 를 실행하지 않고 화면을 확인하기 위한 것 (사용자 요청 2026-10-28).

exe 와 같은 서버(app.server)를 이 PC 에서 띄우고(수집·로그인은 가짜, OpenSky 에 접속하지 않음),
Playwright 로 설치된 Microsoft Edge 를 움직여 주요 장면을 찍고, 이미지를 넣은 한 장짜리 preview/app/index.html 을 만든다.

    py -3.13 tools/preview_app.py            # → preview/app/01_….png … + index.html

필요: pip install playwright (브라우저는 설치된 Edge 사용, CDN 은 인터넷에서)
"""
import base64
import csv
import json
import os
import random
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "preview", "app")
sys.path.insert(0, ROOT)

import fetch_flights as ff  # noqa: E402
import opensky_auth as oa  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app import settings  # noqa: E402
from app.server import AnalyzerServer  # noqa: E402


# ---------- 가짜 수집 · 로그인 (OpenSky 에 접속하지 않음) ----------
AIRLINES = ["KAL", "AAR", "JJA", "TWB", "JNA", "ABL", "ASV", "CPA", "JAL", "ANA", "CES", "CSN", "UAL", "DAL", "SIA", "THA", "EVA", "VJC", "QTR", "UAE"]
DESTS = ["RJTT", "RJAA", "RJBB", "RJFF", "ZSPD", "ZBAA", "VHHH", "RCTP", "WSSS", "VTBS", "RPLL", "VVTS", "KLAX", "KJFK", "EGLL", "LFPG",
         "OMDB", "OTHH", "RKPC", "RKPK", "RKTU", "WADD", "YSSY", "PANC"]
TYPES = [("B77W", "777-300ER"), ("A333", "A330-300"), ("B738", "737-800"), ("A321", "A321neo"), ("B789", "787-9"), ("A359", "A350-900"),
         ("B744", "747-400F"), ("A388", "A380-800"), ("B39M", "737 MAX 8"), ("A320", "A320-200")]
HOUR_W = [3, 2, 1, 1, 1, 2, 5, 8, 9, 9, 8, 7, 7, 7, 7, 8, 8, 9, 10, 10, 9, 8, 6, 4]


def fake_csv(path, ap, start, end, tz):
    import datetime as dt
    rnd = random.Random(f"{ap}{start}")
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["icao24", "callsign", "firstseen", "lastseen", "estdepartureairport", "estarrivalairport", "typecode", "model"])
        d = s
        while d <= e:
            base = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) - int(tz * 3600)
            n = int(300 * (1.12 if d.weekday() in (4, 6) else 1.0) * rnd.uniform(0.9, 1.1))
            for _ in range(n):
                h = rnd.choices(range(24), HOUR_W)[0]
                t = base + h * 3600 + rnd.randrange(3600)
                al, ds, (tc, md) = rnd.choice(AIRLINES), rnd.choice(DESTS), rnd.choice(TYPES)
                cs = f"{al}{rnd.randrange(10, 999)}"
                if rnd.random() < .5:
                    w.writerow([f"{rnd.randrange(16**6):06x}", cs, t - 7200, t, ds, ap, tc, md])
                else:
                    w.writerow([f"{rnd.randrange(16**6):06x}", cs, t, t + 7200, ap, ds, tc, md])
            d += dt.timedelta(days=1)


def fake_collect_many(user, airports, start, end, tz, cache_root=None, outs=None, log=print, on_progress=None, should_stop=None,
                      password=None, **kw):
    import datetime as dt
    days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 2
    log(f"{', '.join(airports)}: 현지 {start} ~ {end} (UTC{tz:+g}) → day 파티션 {days}개를 하루씩 조회")
    log("  OpenSky 로그인 성공 (비밀번호)")
    for i in range(1, days + 1):
        time.sleep(0.5)
        d = dt.date.fromisoformat(start) + dt.timedelta(days=i - 1)
        log(f"  {i}/{days}  {d}  도착 {140 + i * 3} · 출발 {150 + i * 2}  (0.{i % 10}초)")
        on_progress and on_progress(i, days)
    res = {}
    for ap in airports:
        os.makedirs(os.path.dirname(outs[ap]), exist_ok=True)
        fake_csv(outs[ap], ap, start, end, tz)
        res[ap] = (outs[ap], [None] * 2100, 1050, 1050)
    return res


class FakeToken:
    def __init__(self, user, pw):
        self.pw = pw

    def token(self):
        if self.pw != "password":
            raise oa.LoginError("OpenSky 로그인 실패 (invalid_grant). 사용자명·비밀번호를 확인하세요.")
        return "x"


def start_server(tmp):
    settings.APP_DIR = os.path.join(tmp, "app")
    os.makedirs(settings.APP_DIR)
    ff.collect_many = fake_collect_many
    oa.PasswordToken = FakeToken
    oa.CAN_REMEMBER = True
    oa.save_password = lambda *a: True
    oa.load_password = lambda *a: None
    oa.forget_password = lambda *a: True
    settings.app_version = lambda: open(os.path.join(ROOT, "VERSION")).read().strip()
    settings.in_temp_dir = lambda: False                   # 미리보기는 임시 폴더에서 도니까 "압축 파일 안" 경고는 끔
    return AnalyzerServer().url()


# 프로그램 창(제목줄 없음) 흉내: pywebview js_api 대신
FAKE_PYWEBVIEW = """window.pywebview = { api: { win_close: async () => {}, win_min: async () => {}, win_max: async () => true, win_state: async () => true,
  win_move: async () => {}, set_theme: async () => {} } };
window.addEventListener('DOMContentLoaded', () => setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 300));"""


def shoot(url, out):
    n = [0]
    errs = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        p = b.new_page(viewport={"width": 1600, "height": 900}, locale="ko-KR", timezone_id="Asia/Seoul")
        p.on("pageerror", lambda e: errs.append(str(e)))
        p.add_init_script(FAKE_PYWEBVIEW)

        def shot(name, wait=500):
            p.wait_for_timeout(wait)
            n[0] += 1
            p.screenshot(path=os.path.join(out, f"{n[0]:02d}_{name}.png"))

        def pane(v):
            p.click(f'#sideNav [data-pane="{v}"]')
            p.wait_for_timeout(600)

        p.goto(url)
        p.wait_for_function("document.getElementById('bootOverlay')?.hidden === true", timeout=30000)
        shot("홈", 600)
        pane("data")
        p.fill("#cUser", "myname")
        shot("데이터_첫화면")
        p.click("#hSignup"); shot("회원가입_안내", 300); p.click("#hSignupClose")
        p.click("#setBtn"); p.click(".set-src summary"); shot("설정", 300); p.click("#setBtn")
        p.fill("#cPw", "password"); p.click("#hLoginBtn"); p.wait_for_timeout(800)
        p.click('[data-dvmode="map"]'); p.fill("#apSearch", "도쿄"); shot("지도에서_공항찾기", 900)
        try:
            p.click("#apResults [data-ap]", timeout=2000)
        except Exception:  # noqa: BLE001
            pass
        p.click("#amapClose")
        p.fill("#icao", "RKSI"); p.dispatch_event("#icao", "input"); p.dispatch_event("#icao", "change")
        p.click('[data-q="7"]'); p.wait_for_timeout(300)
        p.click("#runBtn"); shot("받는중", 2200)
        p.wait_for_function("document.querySelector('#mainView').dataset.pane === 'overview'", timeout=60000)
        shot("개요", 1500)
        pane("profile")
        for v, name in (("hour", "시간대별"), ("day", "일별"), ("wd", "요일별")):
            p.click(f'[data-ppick="{v}"]'); shot("운항량_" + name, 800)
        pane("mix")
        for v, name in (("route", "노선"), ("airline", "항공사"), ("type", "기종")):
            p.click(f'[data-mpick="{v}"]'); shot("운항구성_" + name, 1200)
        pane("lib"); shot("보관함", 1000)
        p.evaluate("() => document.getElementById('themeBtn').click()")
        pane("profile"); p.click('[data-ppick="hour"]'); shot("어둡게_운항량", 900)
        pane("home"); shot("어둡게_홈", 600)
        b.close()
    return errs


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FlightData 미리보기</title><style>
:root{--bg:#eef1f4;--surface:#fff;--text:#0f1720;--muted:#6b7686;--accent:#1f5fbf;--chip:#e3e8ee}
@media (prefers-color-scheme:dark){:root{--bg:#0d1116;--surface:#151a21;--text:#e9eef4;--muted:#8a95a5;--accent:#3d82e0;--chip:#1e252e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,"Malgun Gothic","Noto Sans KR",sans-serif}
header{position:sticky;top:0;background:var(--bg);padding:12px 16px 8px;z-index:2}
h1{font-size:15px;margin:0 0 8px}h1 small{font-weight:400;color:var(--muted);margin-left:6px}
nav{display:flex;flex-wrap:wrap;gap:6px}nav button{border:0;border-radius:999px;padding:5px 11px;background:var(--chip);color:var(--text);font:inherit;font-size:12.5px;cursor:pointer}
nav button[aria-pressed=true]{background:var(--accent);color:#fff}
main{padding:4px 16px 24px}figure{margin:0;background:var(--surface);border-radius:12px;padding:10px}
img{width:100%;height:auto;display:block;border-radius:6px}figcaption{color:var(--muted);font-size:12.5px;margin-top:8px}
</style></head><body><header><h1>__TITLE__<small>가짜 데이터로 촬영 · ← → 키로 넘기기</small></h1><nav id="nav"></nav></header>
<main><figure><img id="img" alt=""><figcaption id="cap"></figcaption></figure></main>
<script>const S=__SCENES__;let i=0;const nav=document.getElementById('nav');
S.forEach((s,k)=>{const b=document.createElement('button');b.textContent=(k+1)+'. '+s.name;b.onclick=()=>show(k);nav.appendChild(b)});
function show(k){i=(k+S.length)%S.length;document.getElementById('img').src=S[i].src;document.getElementById('img').alt=S[i].name;
document.getElementById('cap').textContent=(i+1)+' / '+S.length+' · '+S[i].name+' — OpenSky 에 접속하지 않은 가짜 수집·가짜 운항 데이터, 실제 exe 는 맑은 고딕';
[...nav.children].forEach((b,j)=>b.setAttribute('aria-pressed',j===i))}
addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(i+1);if(e.key==='ArrowLeft')show(i-1)});show(0);</script></body></html>"""


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix="fd_preview_")
    errs = shoot(start_server(tmp), OUT)
    pngs = sorted(n for n in os.listdir(OUT) if n.endswith(".png"))
    scenes = [{"name": n[3:-4].replace("_", " "), "src": "data:image/png;base64," + base64.b64encode(open(os.path.join(OUT, n), "rb").read()).decode()}
              for n in pngs]
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__TITLE__", f"FlightData_{settings.app_version()} 화면 미리보기").replace("__SCENES__", json.dumps(scenes, ensure_ascii=False)))
    print("\n".join([os.path.join(OUT, n) for n in pngs] + [os.path.join(OUT, "index.html")]))
    if errs:
        print("페이지 오류:", " | ".join(errs))
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
