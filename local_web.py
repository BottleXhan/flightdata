"""FlightData 프로그램(exe)의 작은 웹 서버 — 분석기 화면을 보여 주고, 그 화면에서 누른 [CSV 받기] 를 대신 수행한다.

- 127.0.0.1 에서만 듣고, Host 머리글이 그 주소가 아니면 거절한다 (다른 사이트가 이 서버를 부르지 못하게).
  POST 는 Origin 도 같은 주소여야 하고 JSON 만 받는다 (웹 페이지가 몰래 수집을 시작하지 못하게)
- 보내는 것: 분석기 페이지(web/analyzer.html), 노선 지도 자료(web/mapdata/*.json),
  받은 CSV 목록(/api/collector)과 그 내용(/csv/<번호>). 경로를 받지 않고 번호로만 열어 다른 파일은 읽을 수 없다
- 수집: POST /api/collect → 작업 스레드에서 fetch_flights.collect_many (연도별로 나눠 받기 가능),
  GET /api/collect/status 로 진행·기록, POST /api/collect/stop, POST /api/open-folder
- 저장 폴더 바꾸기: POST /api/settings {outDir} (쓰기 확인 후 설정에 저장), 회원가입 안내: POST /api/open-url (OpenSky 홈페이지만)
- 보관함: GET /api/files 로 저장 폴더의 CSV 목록, /api/file/<번호> 로 그 내용 (경로는 받지 않음)
- 비밀번호는 화면에서 받아 이 PC 의 Windows 자격 증명 관리자에만 저장(선택)하고, 화면으로 돌려주지 않는다
- 머리의 로그인: POST /api/login 이 OpenSky 인증 서버에서 토큰을 받아 확인하고, 이 실행 동안 메모리에만 들고 있다가 수집에 쓴다
  (POST /api/logout 으로 지움, forget 이면 기억한 비밀번호도 삭제)
- ICAO 원문 페이지(저작권 문서 번역)는 넣지 않으므로 웹 링크로 보낸다
"""
import datetime as dt
import json
import os
import sys
import threading
import time
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
    """기본 저장 폴더 = FlightData.exe 가 있는 폴더 안의 OpenSky_CSV (사용자 요청 2026-10-28, 예전엔 문서 폴더의 OpenSky_CSV)."""
    import fetch_flights as ff
    return os.path.join(ff.APP_DIR, "OpenSky_CSV")


def in_temp_dir():
    """zip 을 풀지 않고 압축 파일 안에서 exe 를 실행하면 Windows 가 임시 폴더에 꺼내 실행한다 → 설정·CSV 가 사라짐."""
    import tempfile
    import fetch_flights as ff
    t = os.path.normcase(os.path.abspath(tempfile.gettempdir()))
    return os.path.normcase(os.path.abspath(ff.APP_DIR)).startswith(t + os.sep)


def app_version():
    """빌드할 때 GitHub Actions 가 만드는 _build.py 의 버전 (예: "1.32"). 개발 실행이면 빈 문자열."""
    try:
        from _build import BUILD
        return BUILD
    except ImportError:
        return ""


OLD_DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "Documents", "OpenSky_CSV")
OLD_DEFAULTS = {os.path.normcase(os.path.abspath(os.path.join(os.path.expanduser("~"), *x, "OpenSky_CSV")))
                for x in (("Documents",), ("OneDrive", "Documents"), ("OneDrive", "문서"), ("문서",))}


def out_dir_setting():
    """설정의 저장 폴더. 예전 기본값(문서 폴더의 OpenSky_CSV)이 자동으로 저장돼 있던 것이면 새 기본값으로."""
    d = load_settings().get("out_dir") or ""
    if not d or os.path.normcase(os.path.abspath(d)) in OLD_DEFAULTS:
        return default_out_dir()
    return d


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
        if self.state == "running" and self.stop:          # 중지 직후: 작업이 끝날 때까지 잠깐 기다림
            for _ in range(40):
                if self.state != "running":
                    break
                time.sleep(0.25)
        if self.state == "running":
            raise RuntimeError("이미 받는 중입니다." + (" 중지하는 중이니 잠시 뒤 다시 누르세요." if self.stop else ""))
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
        if not pw and self.server.session and self.server.session[0] == user:   # 머리에서 로그인한 비밀번호
            pw = self.server.session[1]
        try:
            if pw and remember:
                oa.save_password(user, pw)
            elif not pw and remember:
                pw = oa.load_password(user) or ""
            elif not remember:
                oa.forget_password(user)
        except Exception:  # noqa: BLE001 — 저장 실패해도 이번 수집은 진행
            pass
        out_dir = (p.get("outDir") or "").strip() or out_dir_setting()
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
            import fetch_flights as ff
            with self.lock:
                self.results, self.error = results, str(ex)
                self.state = "stopped" if isinstance(ex, ff.Stopped) or self.stop else "error"
            if results:
                self.server.set_csvs([pth for _, pth, _ in results])


class AnalyzerServer:
    def __init__(self):
        self.csvs = []                                       # 분석기에 넘길 CSV 경로 (마지막 수집 결과)
        self.disk = []                                       # 보관함 화면에 보여 준 저장 폴더 CSV 경로 (번호로 연다)
        self.close_window = None                             # 업데이트 뒤 다시 시작할 때 창을 닫는 함수 (flightdata_app 이 넣음)
        self.port_wait = 0                                   # 업데이트 직후: 예전 창이 포트를 놓을 때까지 기다릴 초
        self._updater = None
        self.session = None                                  # (사용자명, 비밀번호) — 머리에서 로그인한 동안 메모리에만
        self.httpd = None
        self.collector = Collector(self)

    @property
    def port(self):
        return self.httpd.server_address[1] if self.httpd else None

    def set_csvs(self, paths):
        self.csvs = [p for p in paths if p and os.path.isfile(p)]

    @property
    def updater(self):
        if self._updater is None:
            import updater
            self._updater = updater.Updater(app_version())
        return self._updater

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
                        saved = bool(user and st.get("remember_pw", False) and oa.load_password(user))
                    except Exception:  # noqa: BLE001
                        pass
                    return self._json({"files": [os.path.basename(p) for p in srv.csvs], "app": True,
                                       "canRemember": oa.CAN_REMEMBER, "pwSaved": saved,
                                       "loggedIn": srv.session[0] if srv.session else None,
                                       "version": app_version(),
                                       "inTemp": in_temp_dir(),
                                       "settings": {"user": user, "remember": st.get("remember_pw", False), "split": st.get("split", True),
                                                    "aircraft": st.get("aircraft", True), "outDir": out_dir_setting()}})
                if path == "/api/pwsaved":
                    import opensky_auth as oa
                    try:
                        return self._json({"saved": bool(oa.load_password((q.get("user") or [""])[0]))})
                    except Exception:  # noqa: BLE001
                        return self._json({"saved": False})
                if path == "/api/files":                     # 보관함: 저장 폴더의 CSV 목록 (번호로만 열 수 있음)
                    d = out_dir_setting()
                    try:
                        names = sorted((n for n in os.listdir(d) if n.lower().endswith(".csv") and os.path.isfile(os.path.join(d, n))),
                                       key=lambda n: -os.path.getmtime(os.path.join(d, n)))
                    except OSError:
                        names = []
                    srv.disk = [os.path.join(d, n) for n in names]
                    return self._json({"dir": d, "files": [{"name": n, "size": os.path.getsize(pth), "mtime": os.path.getmtime(pth)}
                                                           for n, pth in zip(names, srv.disk)]})
                if path.startswith("/api/file/"):
                    try:
                        with open(srv.disk[int(path[10:])], "rb") as f:
                            return self._send(200, f.read(), "text/csv; charset=utf-8")
                    except (ValueError, IndexError, OSError):
                        return self._send(404, b"not found")
                if path == "/api/update/check":              # 새 버전 확인 (GitHub 최신 릴리스)
                    import updater
                    try:
                        info = dict(srv.updater.check(force=bool(q.get("force"))))
                        info["changes"] = updater.notes_text(info.get("notes"))
                        return self._json(info)
                    except Exception as e:  # noqa: BLE001
                        return self._json({"error": f"새 버전을 확인하지 못했습니다: {e}"}, 502)
                if path == "/api/update/status":
                    return self._json(srv.updater.status())
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
                if path == "/api/login":
                    import opensky_auth as oa
                    user = (body.get("user") or "").strip().lower()
                    pw, remember = body.get("password") or "", bool(body.get("remember", False))
                    if not user:
                        return self._json({"error": "OpenSky 사용자명을 넣으세요."}, 400)
                    if not pw:
                        try:
                            pw = oa.load_password(user) or ""
                        except Exception:  # noqa: BLE001
                            pw = ""
                    if not pw:
                        return self._json({"error": "비밀번호를 넣으세요."}, 400)
                    try:
                        oa.PasswordToken(user, pw).token()
                    except oa.LoginError as e:
                        return self._json({"error": str(e)}, 401)
                    except Exception as e:  # noqa: BLE001
                        return self._json({"error": f"로그인을 확인하지 못했습니다: {e}"}, 502)
                    srv.session, saved = (user, pw), False
                    try:
                        if remember:
                            saved = bool(oa.save_password(user, pw))
                        else:
                            oa.forget_password(user)
                    except Exception:  # noqa: BLE001
                        pass
                    save_settings({"user": user, "remember_pw": remember})
                    return self._json({"ok": True, "user": user, "saved": saved})
                if path == "/api/autologin":                 # 로그인한 뒤 자동 로그인 켜기·끄기
                    import opensky_auth as oa
                    on = bool(body.get("on"))
                    user = srv.session[0] if srv.session else load_settings().get("user", "")
                    try:
                        if on:
                            if not srv.session:
                                return self._json({"error": "먼저 로그인하세요."}, 400)
                            if not oa.save_password(srv.session[0], srv.session[1]):
                                return self._json({"error": "이 PC 에 비밀번호를 저장하지 못했습니다."}, 500)
                        elif user:
                            oa.forget_password(user)
                    except Exception as e:  # noqa: BLE001
                        return self._json({"error": f"자동 로그인 설정 실패: {e}"}, 500)
                    save_settings({"remember_pw": on})
                    return self._json({"ok": True, "on": on})
                if path == "/api/logout":
                    import opensky_auth as oa
                    user = srv.session[0] if srv.session else load_settings().get("user", "")
                    srv.session = None
                    if body.get("forget") and user:
                        try:
                            oa.forget_password(user)
                        except Exception:  # noqa: BLE001
                            pass
                    return self._json({"ok": True})
                if path == "/api/settings":                  # 저장 폴더 바꾸기
                    d = os.path.abspath(os.path.expanduser((body.get("outDir") or "").strip()))
                    if not (body.get("outDir") or "").strip():
                        return self._json({"error": "폴더를 고르세요."}, 400)
                    try:
                        os.makedirs(d, exist_ok=True)
                        probe = os.path.join(d, ".flightdata_write_test")
                        with open(probe, "w") as f:
                            f.write("ok")
                        os.remove(probe)
                    except OSError as e:
                        return self._json({"error": f"이 폴더에 저장할 수 없습니다: {e}"}, 400)
                    save_settings({"out_dir": d})
                    return self._json({"ok": True, "outDir": d})
                if path == "/api/open-url":                  # 회원가입 안내: OpenSky 홈페이지만 기본 브라우저로
                    u = (body.get("url") or "").strip()
                    if not (u == "https://opensky-network.org/" or u.startswith("https://opensky-network.org/")):
                        return self._send(403, b"forbidden")
                    import webbrowser
                    webbrowser.open(u)
                    return self._json({"ok": True})
                if path == "/api/update/apply":
                    if srv.collector.state == "running":
                        return self._json({"error": "데이터를 받는 중에는 업데이트할 수 없습니다. 먼저 중지하세요."}, 409)
                    try:
                        srv.updater.apply()
                    except RuntimeError as e:
                        return self._json({"error": str(e)}, 409)
                    return self._json({"ok": True})
                if path == "/api/update/restart":
                    try:
                        srv.updater.restart(srv.close_window or (lambda: os._exit(0)))
                    except RuntimeError as e:
                        return self._json({"error": str(e)}, 409)
                    return self._json({"ok": True})
                if path == "/api/collect/stop":           # 바로 멈춤: 다음 날짜 전에 멈추고, 실행 중인 쿼리도 취소
                    import fetch_flights as ff
                    srv.collector.stop = True
                    with srv.collector.lock:
                        srv.collector.text = "중지하는 중…"
                    ff.cancel_current()
                    return self._json({"ok": True})
                if path == "/api/open-folder":
                    d = (body.get("dir") or "").strip() or out_dir_setting()
                    os.makedirs(d, exist_ok=True)
                    if sys.platform.startswith("win"):
                        os.startfile(d)  # noqa: S606 — 사용자가 고른 저장 폴더를 탐색기로
                    else:
                        import webbrowser
                        webbrowser.open("file://" + d)
                    return self._json({"ok": True})
                return self._send(404, b"not found")

        # 포트를 고정해 두어야 분석기 창의 저장 데이터(IndexedDB, 주소별로 따로 저장됨)가 다음 실행에도 남는다
        deadline = time.time() + self.port_wait
        while True:                                          # 업데이트 직후엔 8790 이 비기를 잠깐 기다림 (보관함이 주소별로 저장되므로)
            try:
                self.httpd = ThreadingHTTPServer(("127.0.0.1", 8790), Handler)
                break
            except OSError:
                if time.time() >= deadline:
                    break
                time.sleep(0.3)
        if self.httpd is None:
            for port in (*range(8791, 8800), 0):
                try:
                    self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
                    break
                except OSError:
                    continue
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.port

    def url(self):
        return f"http://127.0.0.1:{self.start()}/"
