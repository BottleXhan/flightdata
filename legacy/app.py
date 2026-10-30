#!/usr/bin/env python3
"""
OpenSky 첨두시간 분석기 — 내 PC 실행기

더블클릭(Start_OpenSky_Analyzer.bat) 하면:
  1. 이 PC 에서만 접속되는 작은 웹 서버를 띄우고 (http://localhost:8788)
  2. 브라우저에 분석기를 연다.
  3. 분석기에서 데이터 소스 "OpenSky Trino (내 PC)" 로 수집 → 바로 분석.

Trino 는 브라우저가 직접 접속할 수 없고 클라우드 서버에서는 막히므로, 이 PC 의 Python 이 대신 접속한다.
조회 규칙(하루씩, day 파티션 필터, 순차 실행, 캐시)은 fetch_flights.py 와 같다.
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def ensure_trino():
    """처음 실행할 때 trino 라이브러리가 없으면 설치한다."""
    try:
        import trino  # noqa: F401
    except ImportError:
        print("처음 실행: trino 라이브러리를 설치합니다 (1분 정도)…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "trino"])


import fetch_flights as ff  # noqa: E402


def disable_quick_edit():
    """Windows 콘솔을 마우스로 클릭하면 '선택 모드'로 프로그램이 멈추는 것을 막는다."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(-10)                  # STD_INPUT_HANDLE
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(handle, ctypes.byref(mode)):
            k32.SetConsoleMode(handle, (mode.value & ~0x0040) | 0x0080)   # QUICK_EDIT 끔, EXTENDED_FLAGS 켬
    except Exception:  # noqa: BLE001
        pass


def keep_awake(on):
    """수집하는 동안 Windows 가 절전 모드로 들어가지 않게 한다."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))
    except Exception:  # noqa: BLE001
        pass

PAGES = {"/": "icao-peak-hour.html", "/icao-peak-hour.html": "icao-peak-hour.html", "/icao-source.html": "icao-source.html"}
CACHE_ROOT = os.path.join(HERE, "trino_cache")

job_lock = threading.Lock()
job = {"state": "idle"}          # idle | running | done | error


def find_page(name):
    for d in (HERE, os.path.dirname(HERE)):     # 같은 폴더, 없으면 상위 폴더(저장소 구조)
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def load_settings():
    try:
        with open(ff.SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def run_job(params):
    def log(msg):
        with job_lock:
            job["log"].append(msg)
            job["log"] = job["log"][-200:]

    def on_auth_url(url):
        with job_lock:
            job["auth_url"] = url

    def on_progress(done, total):
        with job_lock:
            job["done"], job["total"] = done, total

    keep_awake(True)
    try:
        out_name = f"{params['airport']}_{params['start']}_{params['end']}.csv"
        out, rows, n_arr, n_dep = ff.collect(
            params["user"], params["airport"], params["start"], params["end"], params["tz"],
            cache_root=CACHE_ROOT, out=os.path.join(HERE, out_name), log=log,
            on_auth_url=on_auth_url, on_progress=on_progress, should_stop=lambda: job.get("stop"))
        with job_lock:
            job.update(state="done", out=out, rows=len(rows), arrivals=n_arr, departures=n_dep)
    except Exception as e:  # noqa: BLE001 — 화면에 그대로 보여 준다
        with job_lock:
            job.update(state="error", error=str(e))
    finally:
        keep_awake(False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _local_only(self):
        # 다른 웹사이트가 이 PC 의 서버를 조종하지 못하도록 Host/Origin 을 확인
        host = (self.headers.get("Host") or "").split(":")[0]
        origin = self.headers.get("Origin")
        ok_origin = origin is None or origin in (f"http://localhost:{self.server.server_port}", f"http://127.0.0.1:{self.server.server_port}")
        if host not in ("localhost", "127.0.0.1") or not ok_origin:
            self._send(403, {"error": "forbidden"})
            return False
        return True

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._local_only():
            return
        path = self.path.split("?")[0]
        if path in PAGES:
            p = find_page(PAGES[path])
            if not p:
                return self._send(404, f"{PAGES[path]} 파일을 app.py 와 같은 폴더에 두세요.".encode("utf-8"), "text/plain; charset=utf-8")
            with open(p, "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self._send(200, {"ok": True, "settings": load_settings()})
        if path == "/api/status":
            with job_lock:
                s = {k: v for k, v in job.items() if k != "stop"}
            return self._send(200, s)
        if path == "/api/result":
            with job_lock:
                out = job.get("out") if job.get("state") == "done" else None
            if not out:
                return self._send(404, {"error": "결과가 없습니다."})
            with open(out, "rb") as f:
                return self._send(200, f.read(), "text/csv; charset=utf-8")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._local_only():
            return
        if self.path == "/api/stop":
            with job_lock:
                job["stop"] = True
            return self._send(200, {"ok": True})
        if self.path != "/api/fetch":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            params = {
                "user": str(body["user"]).strip(), "airport": str(body["airport"]).strip().upper(),
                "start": str(body["start"]), "end": str(body["end"]), "tz": float(body["tz"]),
            }
            if not params["user"] or len(params["airport"]) != 4:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"error": "사용자명, 공항 코드(4자리), 기간을 확인하세요."})
        with job_lock:
            if job.get("state") == "running":
                return self._send(409, {"error": "이미 수집 중입니다."})
            job.clear()
            job.update(state="running", log=[], done=0, total=0, params=params)
        try:
            with open(ff.SETTINGS, "w", encoding="utf-8") as f:
                json.dump(params, f, ensure_ascii=False)
        except OSError:
            pass
        threading.Thread(target=run_job, args=(params,), daemon=True).start()
        self._send(202, {"ok": True})


def main():
    disable_quick_edit()
    ensure_trino()
    server = None
    for port in range(8788, 8798):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("사용할 수 있는 포트가 없습니다 (8788-8797).")
    url = f"http://localhost:{server.server_port}/"
    print(f"OpenSky 첨두시간 분석기: {url}")
    print("브라우저가 열리지 않으면 위 주소를 직접 여세요. 이 창을 닫으면 종료됩니다.")
    print("분석기 페이지를 닫아도 수집은 계속됩니다. 페이지를 다시 열면 이어서 보여 줍니다.")
    if not find_page("icao-peak-hour.html"):
        print("⚠ icao-peak-hour.html 을 찾지 못했습니다. app.py 와 같은 폴더에 두세요.")
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
