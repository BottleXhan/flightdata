"""FlightData 프로그램의 작은 웹 서버 — 분석기 화면(web/)을 보여 주고, 화면이 부르는 /api/* 를 처리한다.

- 127.0.0.1 에서만 듣고, Host 머리글이 그 주소가 아니면 거절한다 (다른 사이트가 이 서버를 부르지 못하게).
  POST 는 Origin 도 같은 주소여야 하고 JSON 만 받는다 (웹 페이지가 몰래 수집을 시작하지 못하게)
- 정적 파일은 web 폴더 안의 알려진 형식만. CSV 는 경로를 받지 않고 번호로만 연다 (api.py)
- 포트는 8790 고정: 분석기 창의 저장 데이터(보관함 IndexedDB)가 주소별로 저장되므로 다음 실행에도 같은 주소여야 함
"""
import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from app import api, settings, updater
from app.collector import Collector

PORT = 8790
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


class _HTTPServer(ThreadingHTTPServer):
    """포트를 혼자만 잡는 서버 (1.3.2). 기본값(SO_REUSEADDR)이면 Windows 에서 이미 듣고 있는 8790 에
    두 번째 프로그램도 붙어 버려, 요청이 아무 쪽으로나 가고 업데이트 직후 포트 기다리기도 무의미했음."""
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):          # Windows: 예전 버전(재사용 옵션)이 위에 덮어 잡는 것도 막음
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def static_path(url_path):
    """URL 경로 → web 폴더 안의 파일 (밖으로 나가는 경로·모르는 형식은 None). "/" 는 index.html"""
    root = os.path.normpath(settings.web_dir())
    full = os.path.normpath(os.path.join(root, url_path.lstrip("/") or "index.html"))
    if not full.startswith(root + os.sep) or os.path.splitext(full)[1].lower() not in MIME or not os.path.isfile(full):
        return None
    return full


class AnalyzerServer:
    def __init__(self):
        self.csvs = []                                       # 분석기에 넘길 CSV 경로 (마지막 수집 결과)
        self.disk = []                                       # 보관함 화면에 보여 준 저장 폴더 CSV 경로 (번호로 연다)
        self.close_window = None                             # 업데이트 뒤 다시 시작할 때 창을 닫는 함수 (main 이 넣음)
        self.port_wait = 0                                   # 업데이트 직후: 예전 창이 포트를 놓을 때까지 기다릴 초
        self.session = None                                  # (사용자명, 비밀번호) — 머리에서 로그인한 동안 메모리에만
        self.httpd = None
        self.collector = Collector(self)
        self._updater = None

    @property
    def port(self):
        return self.httpd.server_address[1] if self.httpd else None

    @property
    def updater(self):
        if self._updater is None:
            self._updater = updater.Updater(settings.app_version())
        return self._updater

    def set_csvs(self, paths):
        self.csvs = [p for p in paths if p and os.path.isfile(p)]

    def url(self):
        return f"http://127.0.0.1:{self.start()}/"

    def start(self):
        if self.httpd:
            return self.port
        handler = type("Handler", (_Handler,), {"srv": self})
        deadline = time.time() + self.port_wait
        while True:                                          # 업데이트 직후엔 8790 이 비기를 잠깐 기다림
            try:
                self.httpd = _HTTPServer(("127.0.0.1", PORT), handler)
                break
            except OSError:
                if time.time() >= deadline:
                    break
                time.sleep(0.3)
        if self.httpd is None:
            for port in (*range(PORT + 1, PORT + 10), 0):
                try:
                    self.httpd = _HTTPServer(("127.0.0.1", port), handler)
                    break
                except OSError:
                    continue
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.port


class _Handler(BaseHTTPRequestHandler):
    srv = None                                               # AnalyzerServer (start 에서 넣음)

    def log_message(self, *a):
        pass

    def _send(self, reply):
        self.send_response(reply.code)
        self.send_header("Content-Type", reply.ctype)
        self.send_header("Content-Length", str(len(reply.body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in reply.headers.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(reply.body)

    def _local(self, value, scheme=""):
        port = self.srv.port
        return (value or "").lower() in (f"{scheme}127.0.0.1:{port}", f"{scheme}localhost:{port}")

    def do_GET(self):
        if not self._local(self.headers.get("Host")):
            return self._send(api.text(403, "forbidden"))
        u = urlparse(self.path)
        full = static_path(u.path)
        if full:
            with open(full, "rb") as f:
                return self._send(api.Reply(200, f.read(), MIME[os.path.splitext(full)[1].lower()]))
        return self._send(self._dispatch(api.GET, u.path, parse_qs(u.query)))

    def _dispatch(self, table, path, arg):
        """처리 함수가 예상 못 한 오류를 내도 응답은 돌려줌 (예전엔 연결만 끊겨 화면에 이유가 안 보였음, 1.3.2)."""
        try:
            return api.dispatch(table, self.srv, path, arg)
        except Exception as e:  # noqa: BLE001
            return api.error(f"처리 중 오류: {e}", 500)

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self._local(self.headers.get("Host")) or (origin and not self._local(origin, "http://")) \
                or not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self._send(api.text(403, "forbidden"))
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self._send(api.error("잘못된 요청", 400))
        if not isinstance(body, dict):
            return self._send(api.error("잘못된 요청", 400))
        return self._send(self._dispatch(api.POST, urlparse(self.path).path, body))
