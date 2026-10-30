"""수집기 화면 미리보기 (exe 를 실행하지 않고 화면만 확인용).

가상 화면(Xvfb)에서 fetch_gui 를 띄워 주요 장면을 PNG 로 저장한다. OpenSky 에는 접속하지 않는다
(수집은 가짜 함수로 바꿔 진행 막대·기록만 흉내 냄).

    xvfb-run -a -s "-screen 0 1280x860x24" python3 trino/preview_gui.py [저장 폴더] [--scale 1.5]

필요: tkinter, customtkinter, tkcalendar, tzdata, ImageMagick(import)
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
OUT = os.path.abspath(args[0] if args else os.path.join(HERE, "..", "preview"))
SCALE = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 1.0
os.makedirs(OUT, exist_ok=True)
sys.argv = [sys.argv[0]]

import fetch_flights as ff  # noqa: E402
ff.APP_DIR = os.path.join(OUT, ".settings")                 # 미리보기 설정은 따로 (진짜 설정을 건드리지 않게)
ff.SETTINGS = os.path.join(ff.APP_DIR, "fetch_settings.json")
os.makedirs(ff.APP_DIR, exist_ok=True)
for f in os.listdir(ff.APP_DIR):
    os.remove(os.path.join(ff.APP_DIR, f))

import fetch_gui as g  # noqa: E402

g.messagebox.askyesno = lambda *a, **k: False              # 완료 창은 띄우지 않음
# Windows 처럼 보이게: 비밀번호 기억 칸을 켜 둔 모습 (실제 저장은 하지 않음)
g.oa.CAN_REMEMBER = True
g.oa.save_password = lambda *a: True
g.oa.load_password = lambda *a: None
g.oa.forget_password = lambda *a: True
gate = threading.Event()


def fake_collect_many(user, airports, start, end, tz, cache_root=None, outs=None, log=print, on_progress=None,
                      should_stop=None, **kw):
    """가짜 수집: 하루씩 받는 것처럼 진행·기록만 내보낸다 (중간에 멈춰 '받는 중' 화면을 찍음)."""
    log(f"{', '.join(airports)}: 현지 {start} ~ {end} (UTC{tz:+g}) → day 파티션 8개를 하루씩 조회")
    log("  OpenSky 로그인 성공 (비밀번호)")
    for i in range(1, 9):
        if i == 5:
            gate.wait(20)
        log(f"  {i}/8  {start}  도착 {150 + i * 3} · 출발 {160 + i * 2}  (0.{i}초)")
        if on_progress:
            on_progress(i, 8)
        time.sleep(0.05)
    os.makedirs(os.path.dirname(list(outs.values())[0]), exist_ok=True)
    res = {}
    for ap in airports:
        p = outs[ap]
        open(p, "w").close()
        res[ap] = (p, [None] * 2457, 1220, 1237)
    return res


g.ff.collect_many = fake_collect_many
if SCALE != 1.0:
    g.ctk.set_widget_scaling(SCALE)

app = g.App()
app.geometry("+0+0")
shots = []


def shot(name):
    app.update()
    path = os.path.join(OUT, f"{len(shots) + 1:02d}_{name}.png")
    subprocess.run(["import", "-window", "root", "-crop", f"{app.winfo_width()}x{app.winfo_height()}+0+0", path], check=False)
    shots.append(path)


def find(widget, cls, text=None):
    out = []
    for c in widget.winfo_children():
        if isinstance(c, cls) and (text is None or c.cget("text") == text):
            out.append(c)
        out += find(c, cls, text)
    return out


def close_popups():
    for w in app.winfo_children():
        if isinstance(w, g.tk.Toplevel):
            w.destroy()


steps = []
step = steps.append


@step
def s_light():
    g.ctk.set_appearance_mode("light")
    app.e_user.insert(0, "myname")
    app.e_pw.insert(0, "password")
    app.after(400, lambda: shot("기본_밝게"))


@step
def s_dark():
    g.ctk.set_appearance_mode("dark")
    app.after(600, lambda: shot("기본_어둡게"))


@step
def s_search():
    app.v_search.set("하네다")
    app._search()
    app.after(500, lambda: shot("공항찾기_하네다"))


@step
def s_years():
    app.v_search.set("")
    app._search()
    app._open_years(app.b_years)
    app.after(500, lambda: shot("연도선택_팝업"))


@step
def s_years_range():
    btns = {b.cget("text"): b for w in app.winfo_children() if isinstance(w, g.tk.Toplevel) for b in find(w, g.ctk.CTkButton)}
    btns.get("2022") and btns["2022"].invoke()
    app.after(200, lambda: btns.get("2024") and btns["2024"].invoke())
    app.after(700, lambda: shot("연도선택_2022-2024_적용"))


@step
def s_calendar():
    close_popups()
    cal = find(app, g.ctk.CTkButton, "📅")
    if cal:
        cal[0].invoke()
    app.after(600, lambda: shot("달력_팝업"))


@step
def s_running():
    close_popups()
    app.v_dir.set(os.path.join(OUT, ".csv"))
    app._last7()
    app._start()
    app.after(1500, lambda: shot("받는중"))


@step
def s_done():
    gate.set()
    app.after(2000, lambda: shot("완료"))


PAGE = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>수집기 미리보기</title><style>
:root{--bg:#eef1f4;--surface:#fff;--text:#0f1720;--muted:#6b7686;--accent:#1f5fbf;--chip:#e3e8ee}
@media (prefers-color-scheme:dark){:root{--bg:#0d1116;--surface:#151a21;--text:#e9eef4;--muted:#8a95a5;--accent:#3d82e0;--chip:#1e252e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,"Malgun Gothic","Noto Sans KR",sans-serif}
header{position:sticky;top:0;background:var(--bg);padding:12px 16px 8px;z-index:2}
h1{font-size:15px;margin:0 0 8px}h1 small{font-weight:400;color:var(--muted);margin-left:6px}
nav{display:flex;flex-wrap:wrap;gap:6px}nav button{border:0;border-radius:999px;padding:5px 11px;background:var(--chip);color:var(--text);font:inherit;font-size:12.5px;cursor:pointer}
nav button[aria-pressed=true]{background:var(--accent);color:#fff}
main{padding:4px 16px 24px}figure{margin:0;background:var(--surface);border-radius:12px;padding:10px}
img{width:100%;height:auto;display:block;border-radius:6px}figcaption{color:var(--muted);font-size:12.5px;margin-top:8px}
</style></head><body><header><h1>FlightData 수집기 미리보기<small>가상 화면에서 촬영 · ← → 키로 넘기기</small></h1><nav id="nav"></nav></header>
<main><figure><img id="img" alt=""><figcaption id="cap"></figcaption></figure></main>
<script>const S=__SCENES__;let i=0;const nav=document.getElementById('nav');
S.forEach((s,k)=>{const b=document.createElement('button');b.textContent=(k+1)+'. '+s.name;b.onclick=()=>show(k);nav.appendChild(b)});
function show(k){i=(k+S.length)%S.length;document.getElementById('img').src=S[i].src;document.getElementById('img').alt=S[i].name;
document.getElementById('cap').textContent=(i+1)+' / '+S.length+' · '+S[i].name+' — 실제 exe 는 맑은 고딕, 📅 는 Windows 에서 정상 표시';
[...nav.children].forEach((b,j)=>b.setAttribute('aria-pressed',j===i))}
addEventListener('keydown',e=>{if(e.key==='ArrowRight')show(i+1);if(e.key==='ArrowLeft')show(i-1)});show(0);</script></body></html>"""


def write_page():
    """장면 이미지를 한 페이지(index.html)에 넣는다 — 이미지를 파일 안에 넣어 그 파일 하나만 열면 됨."""
    import base64
    import json
    scenes = []
    for p in shots:
        with open(p, "rb") as f:
            scenes.append({"name": os.path.basename(p)[3:-4].replace("_", " "), "src": "data:image/png;base64," + base64.b64encode(f.read()).decode()})
    out = os.path.join(OUT, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(PAGE.replace("__SCENES__", json.dumps(scenes, ensure_ascii=False)))
    return out


def run(i=0):
    if i < len(steps):
        steps[i]()
        app.after(2200, lambda: run(i + 1))
    else:
        print("\n".join(shots + [write_page()]))
        app.destroy()


app.after(1500, run)
app.mainloop()
