"""수집기 안에 넣은 분석기를 이 PC 에서만 여는 작은 웹 서버.

- 127.0.0.1 의 빈 포트에서만 듣고, Host 머리글이 그 주소가 아니면 거절한다 (다른 사이트가 이 서버를 부르지 못하게)
- 보내는 것: 분석기 페이지(web/analyzer.html), 노선 지도 자료(web/mapdata/*.json),
  방금 받은 CSV 목록(/api/collector)과 그 내용(/csv/<번호>). 경로를 받지 않고 번호로만 열어 다른 파일은 읽을 수 없다
- ICAO 원문 페이지(저작권 문서 번역)는 수집기에 넣지 않으므로 웹 링크로 보낸다
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WEB_URL = "https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5"
STATIC = {"/": ("analyzer.html", "text/html; charset=utf-8"),
          "/index.html": ("analyzer.html", "text/html; charset=utf-8"),
          "/mapdata/land.json": ("mapdata/land.json", "application/json"),
          "/mapdata/airports_min.json": ("mapdata/airports_min.json", "application/json")}


def web_dir():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "web")


class AnalyzerServer:
    def __init__(self):
        self.csvs = []                                       # 분석기에 넘길 CSV 경로 (마지막 수집 결과)
        self.httpd = None

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

            def do_GET(self):
                host = (self.headers.get("Host") or "").lower()
                if host not in (f"127.0.0.1:{srv.port}", f"localhost:{srv.port}"):
                    return self._send(403, b"forbidden")
                path = self.path.split("?", 1)[0].split("#", 1)[0]
                if path in STATIC:
                    name, ctype = STATIC[path]
                    try:
                        with open(os.path.join(web_dir(), name), "rb") as f:
                            return self._send(200, f.read(), ctype)
                    except OSError:
                        return self._send(404, b"not found")
                if path == "/api/collector":
                    body = json.dumps({"files": [os.path.basename(p) for p in srv.csvs]}, ensure_ascii=False).encode()
                    return self._send(200, body, "application/json; charset=utf-8")
                if path.startswith("/csv/"):
                    try:
                        with open(srv.csvs[int(path[5:])], "rb") as f:
                            return self._send(200, f.read(), "text/csv; charset=utf-8")
                    except (ValueError, IndexError, OSError):
                        return self._send(404, b"not found")
                if path == "/icao-source.html":                 # 원문 페이지는 웹 링크에서
                    return self._send(302, extra={"Location": WEB_URL})
                return self._send(404, b"not found")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.port

    def url(self):
        return f"http://127.0.0.1:{self.start()}/"
