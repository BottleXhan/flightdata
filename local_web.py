"""FlightData 프로그램(exe)의 작은 웹 서버 — 분석기 화면을 보여 주고, 그 화면에서 누른 [CSV 받기] 를 대신 수행한다.

- 127.0.0.1 에서만 듣고, Host 머리글이 그 주소가 아니면 거절한다 (다른 사이트가 이 서버를 부르지 못하게).
  POST 는 Origin 도 같은 주소여야 하고 JSON 만 받는다 (웹 페이지가 몰래 수집을 시작하지 못하게)
- 보내는 것: 분석기 페이지(web/analyzer.html), 노선 지도 자료(web/mapdata/*.json),
  받은 CSV 목록(/api/collector)과 그 내용(/csv/<번호>). 경로를 받지 않고 번호로만 열어 다른 파일은 읽을 수 없다
- 수집: POST /api/collect → 작업 스레드에서 fetch_flights.collect_many (연도별로 나눠 받기 가능),
  GET /api/collect/status 로 진행·기록, POST /api/collect/stop, POST /api/open-folder
- 비밀번호는 화면에서 받아 이 PC 의 Windows 자격 증명 관리자에만 저장(선택)하고, 화면으로 돌려주지 않는다
- ICAO 원문 페이지(저작권 문서 번역)는 넣지 않으므로 웹 링크로 보낸다
"""
import datetime as dt
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

WEB_URL = "https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5"
STATIC = {"/": ("analyzer.html", "text/html; charset=utf-8"),
          "/index.html": ("analyzer.html", "text/html; charset=utf-8"),
          "/mapdata/land.json": ("mapdata/land.json", "application/json"),
          "/mapdata/airports_min.json": ("mapdata/airports_min.json", "application/json"),
          "/mapdata/land50.json": ("mapdata/land50.json", "application/json")}


def web_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "web")


def default_out_dir():
    return os.path.join(os.path.expanduser("~"), "Documents", "OpenSky_CSV")


def load_settings():
    import fetch_flights as ff
    try:
        with open(ff.SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(d):
    import fetch_flights as ff
    try:
        cur = load_settings()
        cur.update(d)
        with open(ff.SETTINGS, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
    except OSError:
        pass


def year_segments(s, e):
    """연도별로 나눈 구간 [(시작, 끝), …] (한 해 안이면 하나)."""
    out, a = [], s
    while a <= e:
        b = min(e, dt.date(a.year, 12, 31))
        out.append((a, b))
        a = b + dt.timedelta(days=1)
    return out


class Collector:
    """화면에서 시작한 수집 한 건의 상태 (한 번에 하나)."""

    def __init__(self, server):
        self.server, self.lock = server, threading.Lock()
        self.state, self.log, self.i, self.n, self.text = "idle", [], 0, 0, ""
        self.auth_url = self.error = None
        self.results, self.stop = [], False

    def status(self, since=0):
        with self.lock:
            return {"state": self.state, "i": self.i, "n": self.n, "text": self.text, "authUrl": self.auth_url,
                    "error": self.error, "results": [os.path.basename(p) for _, p, _ in self.results],
                    "log": self.log[since:], "logLen": len(self.log)}

    def _log(self, m):
        with self.lock:
            self.log.append(str(m))

    def start(self, p):
        import fetch_flights as ff
        import opensky_auth as oa
        if self.state == "running":
            raise RuntimeError("이미 받는 중입니다.")
        user = (p.get("user") or "").strip().lower()
        airports = ff.parse_airports(p.get("airport") or "")
        if not user:
            raise ValueError("OpenSky 사용자명을 입력하세요.")
        if not airports or any(len(a) != 4 for a in airports):
            raise ValueError("공항은 4자리 ICAO 코드로 입력하세요.")
        s, e = dt.date.fromisoformat(p["start"]), dt.date.fromisoformat(p["end"])
        if e < s:
            raise ValueError("종료일이 시작일보다 빠릅니다.")
        tz = float(p.get("tz", 9))
        remember, pw = bool(p.get("remember")), p.get("password") or ""
        try:
            if pw and remember:
                oa.save_password(user, pw)
            elif not pw and remember:
                pw = oa.load_password(user) or ""
            elif not remember:
                oa.forget_password(user)
        except Exception:  # noqa: BLE001 — 저장 실패해도 이번 수집은 진행
            pass
        out_dir = (p.get("outDir") or "").strip() or default_out_dir()
        os.makedirs(out_dir, exist_ok=True)
        save_settings({"user": user, "airport": ",".join(airports), "tz": tz, "out_dir": out_dir,
                       "aircraft": bool(p.get("aircraft", True)), "remember_pw": remember, "split": bool(p.get("split", True))})
        segs = year_segments(s, e) if p.get("split", True) else [(s, e)]
        with self.lock:
            self.state, self.log, self.i, self.n, self.text = "running", [], 0, 0, "시작하는 중…"
            self.auth_url = self.error = None
            self.results, self.stop = [], False
        threading.Thread(target=self._run, args=(user, airports, segs, tz, out_dir, bool(p.get("aircraft", True)), pw or None),
                         daemon=True).start()

    def _run(self, user, airports, segs, tz, out_dir, aircraft, password):
        import fetch_flights as ff
        total = sum((b - a).days + 1 for a, b in segs)
        done, results = 0, []
        try:
            for j, (a, b) in enumerate(segs, 1):
                tag = f"{a.year}년 ({j}/{len(segs)}) · " if len(segs) > 1 else ""
                if len(segs) > 1:
                    self._log(f"── {a.year}년: {a} ~ {b} ──")
                outs = {ap: os.path.join(out_dir, f"{ap}_{a}_{b}.csv") for ap in airports}
                sd = (b - a).days + 1

                def prog(i, n, base=done, sd=sd, tag=tag):
                    with self.lock:
                        self.i, self.n, self.text, self.auth_url = base + i * sd / n, total, f"{tag}{i} / {n}일", None

                def auth(url):
                    with self.lock:
                        self.auth_url, self.text = url, "브라우저에 OpenSky 로그인 창이 열렸습니다. 로그인하면 이어집니다."

                res = ff.collect_many(user, airports, a.isoformat(), b.isoformat(), tz, cache_root=os.path.join(out_dir, "trino_cache"),
                                      outs=outs, log=self._log, on_auth_url=auth, on_progress=prog,
                                      should_stop=lambda: self.stop, aircraft_info=aircraft, password=password)
                done += sd
                results += [(ap, v[0], len(v[1])) for ap, v in res.items()]
            with self.lock:
                self.results, self.state, self.i, self.n = results, "done", total, total
            self.server.set_csvs([pth for _, pth, _ in results])
        except Exception as ex:  # noqa: BLE001 — 화면에 그대로 보여 준다
            with self.lock:
                self.results, self.state, self.error = results, "error", str(ex)
            if results:
                self.server.set_csvs([pth for _, pth, _ in results])


class AnalyzerServer:
    def __init__(self):
        self.csvs = []                                       # 분석기에 넘길 CSV 경로 (마지막 수집 결과)
        self.httpd = None
        self.collector = Collector(self)

    @property
    def port(self):
        return self.httpd.server_address[1] if self.httpd else None

    def set_csvs(self, paths):
        self.csvs = [p for p in paths if p and os.path.isfile(p)]

    def start(self):
        if self.httpd:
            return self.port
        srv = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", extra=None):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, obj, code=200):
                return self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

            def _host_ok(self):
                return (self.headers.get("Host") or "").lower() in (f"127.0.0.1:{srv.port}", f"localhost:{srv.port}")

            def do_GET(self):
                if not self._host_ok():
                    return self._send(403, b"forbidden")
                u = urlparse(self.path)
                path, q = u.path, parse_qs(u.query)
                if path in STATIC:
                    name, ctype = STATIC[path]
                    try:
                        with open(os.path.join(web_dir(), name), "rb") as f:
                            return self._send(200, f.read(), ctype)
                    except OSError:
                        return self._send(404, b"not found")
                if path == "/api/collector":
                    import opensky_auth as oa
                    st = load_settings()
                    user = st.get("user", "")
                    saved = False
                    try:
                        saved = bool(user and st.get("remember_pw", True) and oa.load_password(user))
                    except Exception:  # noqa: BLE001
                        pass
                    return self._json({"files": [os.path.basename(p) for p in srv.csvs], "app": True,
                                       "canRemember": oa.CAN_REMEMBER, "pwSaved": saved,
                                       "settings": {"user": user, "remember": st.get("remember_pw", True), "split": st.get("split", True),
                                                    "aircraft": st.get("aircraft", True), "outDir": st.get("out_dir") or default_out_dir()}})
                if path == "/api/pwsaved":
                    import opensky_auth as oa
                    try:
                        return self._json({"saved": bool(oa.load_password((q.get("user") or [""])[0]))})
                    except Exception:  # noqa: BLE001
                        return self._json({"saved": False})
                if path == "/api/collect/status":
                    return self._json(srv.collector.status(int((q.get("since") or ["0"])[0] or 0)))
                if path.startswith("/csv/"):
                    try:
                        with open(srv.csvs[int(path[5:])], "rb") as f:
                            return self._send(200, f.read(), "text/csv; charset=utf-8")
                    except (ValueError, IndexError, OSError):
                        return self._send(404, b"not found")
                if path == "/icao-source.html":                 # 원문 페이지는 웹 링크에서
                    return self._send(302, extra={"Location": WEB_URL})
                return self._send(404, b"not found")

            def do_POST(self):
                origin = self.headers.get("Origin")
                if not self._host_ok() or (origin and origin.lower() not in (f"http://127.0.0.1:{srv.port}", f"http://localhost:{srv.port}")) \
                        or not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    return self._send(403, b"forbidden")
                try:
                    body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                except ValueError:
                    return self._json({"error": "잘못된 요청"}, 400)
                path = urlparse(self.path).path
                if path == "/api/collect":
                    try:
                        srv.collector.start(body)
                    except (ValueError, RuntimeError, KeyError) as e:
                        return self._json({"error": str(e)}, 409 if isinstance(e, RuntimeError) else 400)
                    return self._json({"ok": True})
                if path == "/api/collect/stop":
                    srv.collector.stop = True
                    return self._json({"ok": True})
                if path == "/api/open-folder":
                    d = (body.get("dir") or "").strip() or load_settings().get("out_dir") or default_out_dir()
                    os.makedirs(d, exist_ok=True)
                    if sys.platform.startswith("win"):
                        os.startfile(d)  # noqa: S606 — 사용자가 고른 저장 폴더를 탐색기로
                    else:
                        import webbrowser
                        webbrowser.open("file://" + d)
                    return self._json({"ok": True})
                return self._send(404, b"not found")

        # 포트를 고정해 두어야 분석기 창의 저장 데이터(IndexedDB, 주소별로 따로 저장됨)가 다음 실행에도 남는다
        for port in (*range(8790, 8800), 0):
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                break
            except OSError:
                continue
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.port

    def url(self):
        return f"http://127.0.0.1:{self.start()}/"
