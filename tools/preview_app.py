"""FlightData 프로그램(exe) 화면 미리보기 — exe 를 실행하지 않고 화면을 확인하기 위한 것 (사용자 요청 2026-10-28).

exe 와 같은 local_web 서버를 이 PC 에서 띄우고(수집·로그인은 가짜, OpenSky 에 접속하지 않음),
Playwright(Chromium)로 주요 장면을 찍어 이미지를 넣은 한 장짜리 preview/app/index.html 을 만든다.

    py -3.13 tools/preview_app.py            # → preview/app/01_….png … + index.html

필요: node + playwright(설치돼 있는 것), preview/libs 의 Chart.js·d3·JSZip·tailwind.css (없으면 npm 으로 준비)
"""
import base64
import csv
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "preview", "app")
LIBS = os.path.join(ROOT, "preview", "libs")
ANALYZER = os.path.join(ROOT, "web", "analyzer.html")
sys.path.insert(0, ROOT)

import fetch_flights as ff  # noqa: E402
import local_web  # noqa: E402
import opensky_auth as oa  # noqa: E402


def prepare_libs():
    """화면을 exe 와 같게 찍으려면 CDN 라이브러리를 로컬에서 대신 준다 (이 환경은 CDN 이 막혀 있음)."""
    os.makedirs(LIBS, exist_ok=True)
    need = {"chartjs/package/dist/chart.umd.js": "chart.js@4.4.1", "d3/package/dist/d3.min.js": "d3@7.8.5",
            "jszip/package/dist/jszip.min.js": "jszip@3.10.1"}
    for path, pkg in need.items():
        if os.path.exists(os.path.join(LIBS, path)):
            continue
        d = os.path.join(LIBS, path.split("/")[0])
        os.makedirs(d, exist_ok=True)
        tgz = subprocess.run(["npm", "pack", pkg, "--silent"], cwd=d, capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1]
        subprocess.run(["tar", "xzf", tgz], cwd=d, check=True)
    tw = os.path.join(LIBS, "tw.css")
    if not os.path.exists(tw) or os.path.getmtime(tw) < os.path.getmtime(ANALYZER):
        twd = os.path.join(LIBS, "tw")
        if not os.path.exists(os.path.join(twd, "node_modules", ".bin", "tailwindcss")):
            os.makedirs(twd, exist_ok=True)
            subprocess.run(["npm", "install", "tailwindcss@3.4.16", "--silent", "--no-audit", "--no-fund"], cwd=twd, check=True)
        with open(os.path.join(LIBS, "tw.in.css"), "w") as f:
            f.write("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")
        subprocess.run([os.path.join(twd, "node_modules", ".bin", "tailwindcss"), "-i", os.path.join(LIBS, "tw.in.css"),
                        "--content", ANALYZER, "-o", tw, "--minify"], check=True, capture_output=True)


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
    web = os.path.join(tmp, "web")
    os.makedirs(os.path.join(web, "mapdata"))
    shutil.copy(ANALYZER, os.path.join(web, "analyzer.html"))
    for n in ("land.json", "land50.json", "airports_min.json"):
        shutil.copy(os.path.join(ROOT, "web", "mapdata", n), os.path.join(web, "mapdata", n))
    local_web.web_dir = lambda: web
    ff.APP_DIR = os.path.join(tmp, "app")
    ff.SETTINGS = os.path.join(ff.APP_DIR, "fetch_settings.json")
    os.makedirs(ff.APP_DIR)
    ff.collect_many = fake_collect_many
    oa.PasswordToken = FakeToken
    oa.CAN_REMEMBER = True
    oa.save_password = lambda *a: True
    oa.load_password = lambda *a: None
    oa.forget_password = lambda *a: True
    vf = os.path.join(ROOT, "VERSION")
    local_web.app_version = lambda: open(vf).read().strip()
    local_web.in_temp_dir = lambda: False                  # 미리보기는 임시 폴더에서 도니까 "압축 파일 안" 경고는 끔
    srv = local_web.AnalyzerServer()
    return srv.url()


SHOTS = r"""
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [url, out, libs] = process.argv.slice(2);
const lib = p => fs.readFileSync(path.join(libs, p));
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
  const tw = fs.readFileSync(path.join(libs, 'tw.css'), 'utf8');
  await p.route('**/cdn.tailwindcss.com/**', r => r.fulfill({ contentType: 'text/javascript', body: `document.head.insertAdjacentHTML('beforeend', ${JSON.stringify('<style>' + tw + '</style>')});` }));
  await p.route('**/Chart.js/**', r => r.fulfill({ contentType: 'text/javascript', body: lib('chartjs/package/dist/chart.umd.js') }));
  await p.route('**/d3/**', r => r.fulfill({ contentType: 'text/javascript', body: lib('d3/package/dist/d3.min.js') }));
  await p.route('**/jszip/**', r => r.fulfill({ contentType: 'text/javascript', body: lib('jszip/package/dist/jszip.min.js') }));
  await p.route('**/xlsx/**', r => r.fulfill({ contentType: 'text/javascript', body: '' }));
  await p.route('**/fonts.googleapis.com/**', r => r.fulfill({ contentType: 'text/css', body: '' }));
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  let n = 0; const shot = async (name, wait = 500) => { await p.waitForTimeout(wait); await p.screenshot({ path: path.join(out, `${String(++n).padStart(2, '0')}_${name}.png`) }); };
  const pane = async v => { await p.click(`#sideNav [data-pane="${v}"]`); await p.waitForTimeout(600); };
  await p.addInitScript(() => { window.pywebview = { api: { win_close: async () => {}, win_min: async () => {}, win_max: async () => true, win_state: async () => true, win_move: async () => {}, set_theme: async () => {} } };
    window.addEventListener('DOMContentLoaded', () => setTimeout(() => window.dispatchEvent(new Event('pywebviewready')), 300)); });   // 프로그램 창(제목줄 없음) 흉내
  await p.goto(url); await p.waitForTimeout(2500);
  await shot('홈', 600);
  await pane('data');
  await p.fill('#cUser', 'myname');
  await shot('데이터_첫화면');
  await p.click('#hSignup'); await shot('회원가입_안내', 300); await p.click('#hSignupClose');
  await p.click('#setBtn'); await p.click('.set-src summary'); await shot('설정', 300); await p.click('#setBtn');
  await p.fill('#cPw', 'password'); await p.click('#hLoginBtn'); await p.waitForTimeout(800);
  await p.click('[data-dvmode="map"]'); await p.fill('#apSearch', '도쿄'); await shot('지도에서_공항찾기', 900);
  await p.click('#apResults [data-ap]').catch(() => {}); await p.click('#amapClose');
  await p.fill('#icao', 'RKSI'); await p.dispatchEvent('#icao', 'input'); await p.dispatchEvent('#icao', 'change');
  await p.click('[data-q="7"]'); await p.waitForTimeout(300);
  await p.click('#runBtn'); await shot('받는중', 2200);
  await p.waitForFunction(() => document.querySelector('#mainView').dataset.pane === 'overview', null, { timeout: 60000 });
  await shot('개요', 1500);
  await pane('profile');
  for (const [v, name] of [['hour', '시간대별'], ['day', '일별'], ['wd', '요일별']]) { await p.click(`[data-ppick="${v}"]`); await shot('운항량_' + name, 800); }
  await pane('mix');
  for (const [v, name] of [['route', '노선'], ['airline', '항공사'], ['type', '기종']]) { await p.click(`[data-mpick="${v}"]`); await shot('운항구성_' + name, 1200); }
  await pane('lib'); await shot('보관함', 1000);
  await p.evaluate(() => document.getElementById('themeBtn').click()); await pane('profile'); await p.click('[data-ppick="hour"]'); await shot('어둡게_운항량', 900);
  await pane('home'); await shot('어둡게_홈', 600);
  if (errs.length) console.error('page errors:', errs.join(' | '));
  await b.close();
})();
"""

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
    prepare_libs()
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    tmp = tempfile.mkdtemp(prefix="fd_preview_")
    url = start_server(tmp)
    js = os.path.join(tmp, "shots.js")
    with open(js, "w", encoding="utf-8") as f:
        f.write(SHOTS)
    env = dict(os.environ, NODE_PATH=subprocess.run(["npm", "root", "-g"], capture_output=True, text=True).stdout.strip())
    subprocess.run(["node", js, url, OUT, LIBS], check=True, env=env)
    pngs = sorted(n for n in os.listdir(OUT) if n.endswith(".png"))
    scenes = [{"name": n[3:-4].replace("_", " "), "src": "data:image/png;base64," + base64.b64encode(open(os.path.join(OUT, n), "rb").read()).decode()}
              for n in pngs]
    ver = local_web.app_version()
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__TITLE__", f"FlightData_{ver} 화면 미리보기").replace("__SCENES__", json.dumps(scenes, ensure_ascii=False)))
    print("\n".join([os.path.join(OUT, n) for n in pngs] + [os.path.join(OUT, "index.html")]))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
