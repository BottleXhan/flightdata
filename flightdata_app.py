"""FlightData — 수집과 분석을 한 창에서 (Windows exe 의 시작 파일).

이 PC 안에서만 열리는 작은 웹 서버(local_web)를 띄우고, 그 주소의 분석기 화면을 프로그램 창(pywebview → Edge WebView2)으로 연다.
분석기 화면의 "OpenSky에서 받기" 가 이 서버를 통해 fetch_flights 로 수집하고, 받은 CSV 를 같은 창에서 바로 분석한다.
창을 띄우지 못하면(WebView2 없음 등) 브라우저로 열고, 이 창(콘솔 없음)을 닫을 때까지 서버를 유지한다.

    python flightdata_app.py            # 개발용 실행
    FlightData.exe --selftest           # 빌드 확인 (필요한 모듈·데이터가 들어갔는지)
"""
import os
import sys
import time
import webbrowser

import fetch_flights as ff
import local_web


def selftest():
    import trino.auth  # noqa: F401
    import zoneinfo
    import webview  # noqa: F401                             # 프로그램 창
    import opensky_auth as oa
    import updater
    assert updater.parse_ver("FlightData_1.0.46") == (1, 0, 46) and updater.parse_ver("1.0.47") > updater.parse_ver("1.0.46")
    assert os.path.isfile(os.path.join(local_web.web_dir(), "analyzer.html"))
    assert os.path.isfile(os.path.join(local_web.web_dir(), "mapdata", "airports_min.json"))
    assert oa.CAN_REMEMBER                                  # Windows 자격 증명 관리자: 저장 → 읽기 → 삭제
    assert oa.save_password("flightdata-selftest", "pw-테스트")
    assert oa.load_password("flightdata-selftest") == "pw-테스트"
    assert oa.forget_password("flightdata-selftest") and oa.load_password("flightdata-selftest") is None
    zoneinfo.ZoneInfo("Asia/Seoul")
    srv = local_web.AnalyzerServer()
    assert srv.start()
    return 0


class Api:
    """화면(JavaScript)에서 window.pywebview.api.<이름>() 으로 부르는 것 — 프로그램 창에서만 되는 일."""

    window = None

    def choose_folder(self, start=""):
        """저장 폴더 고르기 창. 고른 폴더 경로(취소하면 None)."""
        import webview
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        start = start if start and os.path.isdir(start) else os.path.expanduser("~")
        res = self.window.create_file_dialog(kind, directory=start)
        return (res[0] if isinstance(res, (list, tuple)) else res) if res else None

    # ---------- 제목줄 없는 창(frameless)의 창 버튼·끌기 (사용자 요청: Windows 제목줄 없애고 헤더 오른쪽에 버튼) ----------
    # pywebview 의 maximize/move 는 제목줄 없는 창에서 화면 배율·위치를 잘못 잡아 창이 화면 밖으로 나가는 일이 있어
    # (사용자 보고 1.1.4) Windows API 로 직접: 최대화 = 지금 모니터의 작업 영역(작업 표시줄 제외)에 꽉 맞춤
    _maxed = False
    _normal = None                                           # 이전 크기 (물리 픽셀 left, top, width, height)

    def _hwnd(self):
        import ctypes
        return ctypes.windll.user32.FindWindowW(None, self.window.title)

    def _scale(self, hwnd):
        import ctypes
        try:
            return ctypes.windll.user32.GetDpiForWindow(hwnd) / 96 or 1
        except Exception:  # noqa: BLE001
            return 1

    def _work(self, hwnd):
        """창이 있는 모니터의 작업 영역 (left, top, right, bottom)."""
        import ctypes
        from ctypes import wintypes

        class MI(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        mi = MI(); mi.cbSize = ctypes.sizeof(MI)
        mon = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
        ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi))
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom

    def _rect(self, hwnd):
        import ctypes
        from ctypes import wintypes
        r = wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.left, r.top, r.right - r.left, r.bottom - r.top

    def _place(self, hwnd, x, y, w, h):
        import ctypes
        ctypes.windll.user32.SetWindowPos(hwnd, None, int(x), int(y), int(w), int(h), 0x0004 | 0x0010 | 0x4000)  # NOZORDER·NOACTIVATE·ASYNC

    def _default_rect(self, hwnd):
        """이전 크기: 1480×920(화면 배율 반영)을 작업 영역 가운데, 작업 영역보다 크면 맞춤."""
        l, t, r, b = self._work(hwnd)
        s = self._scale(hwnd)
        w, h = min(int(1480 * s), r - l - 40), min(int(920 * s), b - t - 40)
        return l + (r - l - w) // 2, t + (b - t - h) // 2, w, h

    def maximize_now(self):
        if not sys.platform.startswith("win"):
            return self.window.maximize()
        hwnd = self._hwnd()
        if not hwnd:
            return
        if not self._maxed:
            self._normal = self._rect(hwnd)
        l, t, r, b = self._work(hwnd)
        self._place(hwnd, l, t, r - l, b - t)
        self._maxed = True

    def restore_now(self):
        if not sys.platform.startswith("win"):
            return self.window.restore()
        hwnd = self._hwnd()
        if not hwnd:
            return
        n = self._normal
        l, t, r, b = self._work(hwnd)
        if not n or n[2] >= r - l - 10:                       # 처음부터 최대화였으면 기본 크기로
            n = self._default_rect(hwnd)
        self._place(hwnd, *n)
        self._maxed = False

    def win_min(self):
        self.window.minimize()

    def win_max(self):
        """최대화 ↔ 이전 크기. 바뀐 상태(True = 최대화)를 돌려줌."""
        self.restore_now() if self._maxed else self.maximize_now()
        return self._maxed

    def win_state(self):
        return self._maxed

    def win_close(self):
        self.window.destroy()

    def win_move(self, x, y):
        """헤더를 끌 때: 화면 좌표(CSS 픽셀) → 물리 픽셀로 창 왼쪽 위를 옮김 (최대화였으면 이전 크기로)."""
        if not sys.platform.startswith("win"):
            return self.window.move(int(x), int(y))
        hwnd = self._hwnd()
        if not hwnd:
            return
        s = self._scale(hwnd)
        if self._maxed:
            self.restore_now()
        _, _, w, h = self._rect(hwnd)
        self._place(hwnd, x * s, y * s, w, h)

    def win_rect(self):
        """지금 창 위치·크기 (CSS 픽셀) — 테두리를 끌어 크기 바꿀 때 시작값."""
        hwnd = self._hwnd()
        if not hwnd:
            return None
        s = self._scale(hwnd)
        x, y, w, h = self._rect(hwnd)
        return [x / s, y / s, w / s, h / s]

    def win_set_rect(self, x, y, w, h):
        """테두리 끌기로 크기 바꾸기 (CSS 픽셀, 최소 1100×700)."""
        hwnd = self._hwnd()
        if not hwnd:
            return
        s = self._scale(hwnd)
        w, h = max(1100, w), max(700, h)
        self._maxed = False
        self._place(hwnd, x * s, y * s, w * s, h * s)

    def set_theme(self, dark, caption="", text=""):
        """창 맨 위 제목 표시줄을 화면의 밝게/어둡게에 맞춘다 (Windows 10 1809+ 어두운 제목줄, Windows 11 은 색까지)."""
        if not sys.platform.startswith("win") or self.window is None:
            return False
        try:
            import ctypes
            from ctypes import wintypes
            # 창 찾기: 제목으로 (다른 스레드에서 .NET 창 객체를 건드리지 않게 — 멈춤 방지)
            hwnd = ctypes.windll.user32.FindWindowW(None, self.window.title)
            if not hwnd:
                return False
            dwm = ctypes.windll.dwmapi

            def setattr_(attr, value):
                v = ctypes.c_int(value)
                return dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))
            flag = 1 if dark else 0
            if setattr_(20, flag) != 0:                       # DWMWA_USE_IMMERSIVE_DARK_MODE (옛 빌드는 19)
                setattr_(19, flag)
            for attr, css in ((35, caption), (36, text)):     # DWMWA_CAPTION_COLOR / TEXT_COLOR (Windows 11)
                rgb = _css_rgb(css)
                if rgb:
                    setattr_(attr, rgb[0] | (rgb[1] << 8) | (rgb[2] << 16))
            # 제목줄을 다시 그리게 (Windows 10 은 이게 있어야 바로 바뀜)
            ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0010 | 0x4000)  # +NOACTIVATE·ASYNC (안 기다림)
            return True
        except Exception:  # noqa: BLE001 — 제목줄 색은 꾸밈이라 실패해도 무시
            return False


def _css_rgb(css):
    """'rgb(21, 26, 33)' / '#151a21' → (r, g, b)."""
    import re
    css = (css or "").strip()
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", css)
    if m:
        return tuple(int(x) for x in m.groups())
    m = re.match(r"#([0-9a-fA-F]{6})$", css)
    if m:
        h = m.group(1)
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return None


def _warmup():
    try:
        import requests  # noqa: F401
        import trino.dbapi  # noqa: F401
        import opensky_auth  # noqa: F401
        import updater  # noqa: F401
        import fetch_flights  # noqa: F401
        import zoneinfo
        zoneinfo.ZoneInfo("Asia/Seoul")
    except Exception:  # noqa: BLE001
        pass


def main():
    # 무거운 모듈(requests·trino·로그인·업데이트)은 창을 띄우기 **전에** 불러 둔다.
    # 예전(1.0.46)엔 창과 동시에 뒤에서 불러서, 파이썬 GIL 을 오래 잡는 동안 창(WinForms)이 멈춰 "응답 없음"이 떴음
    _warmup()
    import updater
    srv = local_web.AnalyzerServer()
    if "--after-update" in sys.argv:                      # 업데이트로 다시 켜짐: 예전 창이 닫힐 때까지 포트를 기다리고 .old 를 지움
        srv.port_wait = 15
    url = srv.url()
    threading_cleanup = __import__("threading").Thread(target=updater.cleanup_old, daemon=True)
    threading_cleanup.start()
    try:
        import webview
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True      # 보관함의 CSV 내려받기 (pywebview 5+)
        except Exception:  # noqa: BLE001
            pass
        api = Api()
        api.window = webview.create_window(f"FlightData {local_web.app_version()}".strip(), url, width=1480, height=920, min_size=(1100, 700), js_api=api,
                                           frameless=True, easy_drag=False)   # Windows 제목줄 없이 — 창 버튼·끌기는 화면 헤더에서
        srv.close_window = lambda: api.window.destroy()
        # 처음엔 작업 영역에 꽉 차게 (제목줄 없는 창이라 pywebview maximized 대신 직접)
        api.window.events.shown += lambda: (time.sleep(0.15), api.maximize_now())
        # private_mode 를 끄고 exe 폴더에 보관 → 분석기의 "저장된 데이터"(IndexedDB)가 다음 실행에도 남음
        webview.start(private_mode=False, storage_path=os.path.join(ff.APP_DIR, "app_data"))
        return 0
    except Exception:  # noqa: BLE001 — 창을 못 띄우면 브라우저로
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else main())
