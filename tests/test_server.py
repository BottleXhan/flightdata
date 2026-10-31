"""로컬 서버: 정적 파일 · 보안 검사(Host/Origin/JSON) · 번호로만 여는 CSV · 설정 API."""
import http.client
import json
import os

import pytest

from app import server as server_mod
from app.server import AnalyzerServer, static_path


@pytest.fixture
def srv(app_dir, monkeypatch):
    monkeypatch.setattr(server_mod, "PORT", 18790)           # 실제 프로그램(8790)과 겹치지 않게
    s = AnalyzerServer()
    s.start()
    yield s
    s.httpd.shutdown()
    s.httpd.server_close()


def request(s, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", s.port, timeout=10)
    h = {"Host": f"127.0.0.1:{s.port}"}
    if body is not None:
        h.update({"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{s.port}"})
    h.update(headers or {})
    c.request(method, path, body=None if body is None else json.dumps(body), headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, r.getheader("Content-Type"), data


def test_static_files(srv):
    st, ct, body = request(srv, "GET", "/")
    assert st == 200 and ct.startswith("text/html") and b'src="js/main.js"' in body
    st, ct, _ = request(srv, "GET", "/js/main.js")
    assert st == 200 and ct.startswith("text/javascript")    # 모듈 스크립트는 JS 형식이어야 실행됨
    assert request(srv, "GET", "/css/app.css")[0] == 200
    assert request(srv, "GET", "/mapdata/land50.json")[0] == 200
    st, ct, body = request(srv, "GET", "/flags/kr.svg")                # 국기 (flag-icons)
    assert st == 200 and ct == "image/svg+xml" and body.startswith(b"<svg")
    al = json.loads(request(srv, "GET", "/mapdata/airlines.json")[2])  # 항공사 대응표 (OpenFlights + 보정)
    assert al["KAL"] == ["KE", "Korean Air", "KR", "대한항공"] and al["FDX"][0] == "FX"


def test_second_server_does_not_share_port(srv):
    """두 번째 서버는 같은 포트에 붙지 않고 다음 포트로 (예전엔 Windows 에서 둘 다 18790/8790 을 잡았음, 1.3.2)."""
    s2 = AnalyzerServer()
    s2.start()
    try:
        assert s2.port != srv.port
    finally:
        s2.httpd.shutdown()
        s2.httpd.server_close()


def test_static_path_stays_inside_web():
    assert static_path("/../fetch_flights.py") is None
    assert static_path("/..%2f..%2fwindows/win.ini") is None
    assert static_path("/js/../index.html").endswith("index.html")
    assert static_path("/nope.exe") is None


def test_rejects_other_hosts_and_cross_origin(srv):
    assert request(srv, "GET", "/", headers={"Host": "evil.example"})[0] == 403
    assert request(srv, "POST", "/api/logout", {}, headers={"Origin": "https://evil.example"})[0] == 403
    st, _, _ = request(srv, "POST", "/api/logout", None, headers={"Content-Type": "text/plain", "Origin": f"http://127.0.0.1:{srv.port}"})
    assert st == 403


def test_collector_info_and_csv_by_number(srv, tmp_path):
    st, _, body = request(srv, "GET", "/api/collector")
    info = json.loads(body)
    assert st == 200 and info["app"] is True and info["files"] == [] and "settings" in info
    f = tmp_path / "RKSI_2025-01-01_2025-01-02.csv"
    f.write_bytes(b"icao24\n1\n")
    srv.set_csvs([str(f)])
    assert request(srv, "GET", "/csv/0")[2] == b"icao24\n1\n"
    assert request(srv, "GET", "/csv/1")[0] == 404
    assert request(srv, "GET", "/csv/../x")[0] == 404
    assert request(srv, "GET", "/api/nothing")[0] == 404


def test_settings_out_dir_and_files(srv, tmp_path):
    d = tmp_path / "csvs"
    st, _, body = request(srv, "POST", "/api/settings", {"outDir": str(d)})
    assert st == 200 and json.loads(body)["outDir"] == str(d) and os.path.isdir(d)
    (d / "A.csv").write_text("x", encoding="utf-8")
    files = json.loads(request(srv, "GET", "/api/files")[2])
    assert [x["name"] for x in files["files"]] == ["A.csv"]
    assert request(srv, "GET", "/api/file/0")[2] == b"x"
    assert request(srv, "POST", "/api/settings", {"outDir": ""})[0] == 400


def test_collect_validation(srv):
    st, _, body = request(srv, "POST", "/api/collect", {"user": "", "airport": "RKSI", "start": "2025-01-01", "end": "2025-01-02"})
    assert st == 400 and "사용자명" in json.loads(body)["error"]
    st, _, body = request(srv, "POST", "/api/collect", {"user": "me", "airport": "ICN", "start": "2025-01-01", "end": "2025-01-02"})
    assert st == 400 and "4자리" in json.loads(body)["error"]
    st, _, body = request(srv, "GET", "/api/collect/status")
    assert json.loads(body)["state"] == "idle"


def test_errors_are_answered_not_dropped(srv, tmp_path, monkeypatch):
    """처리 중 오류도 JSON 으로 답하고, 폴더 열기는 폴더만 (1.3.2)."""
    st, ct, body = request(srv, "GET", "/api/collect/status?since=abc")
    assert st == 500 and ct.startswith("application/json") and "error" in json.loads(body)
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=10)
    c.request("POST", "/api/logout", body="[1]", headers={"Host": f"127.0.0.1:{srv.port}", "Content-Type": "application/json"})
    assert c.getresponse().status == 400
    c.close()
    opened = []
    monkeypatch.setattr("os.startfile", opened.append, raising=False)
    f = tmp_path / "x.exe"
    f.write_bytes(b"")
    assert request(srv, "POST", "/api/open-folder", {"dir": str(f)})[0] == 400
    assert request(srv, "POST", "/api/open-folder", {"dir": str(tmp_path)})[0] == 200
    assert opened == [str(tmp_path)]


def test_open_url_only_opensky(srv, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert request(srv, "POST", "/api/open-url", {"url": "https://evil.example/"})[0] == 403
    assert request(srv, "POST", "/api/open-url", {"url": "https://opensky-network.org/"})[0] == 200
    assert opened == ["https://opensky-network.org/"]
