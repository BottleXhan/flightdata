"""시작 순서: 무거운 모듈 미리 불러오기 → 서버 → 숨긴 창 만들기 → 화면이 준비되면 최대화해서 보여 주기.
창을 띄우지 못하면(WebView2 없음 등) 브라우저로 열고, 이 프로세스를 끝낼 때까지 서버를 유지한다.
"""
import os
import sys
import threading
import time
import webbrowser

from app import settings, updater
from app.server import AnalyzerServer
from app.window import Api

_T0 = time.time()


def selftest():
    """빌드 확인 (FlightData.exe --selftest): 필요한 모듈·데이터가 들어갔는지."""
    import trino.auth  # noqa: F401
    import zoneinfo
    import webview  # noqa: F401                             # 프로그램 창
    import opensky_auth as oa
    assert updater.parse_ver("FlightData_1.0.46") == (1, 0, 46) and updater.parse_ver("1.0.47") > updater.parse_ver("1.0.46")
    web = settings.web_dir()
    for f in ("index.html", "css/app.css", "js/main.js", "mapdata/airports_min.json", "mapdata/land50.json", "mapdata/airlines.json", "flags/kr.svg"):
        assert os.path.isfile(os.path.join(web, f)), f
    assert oa.CAN_REMEMBER                                  # Windows 자격 증명 관리자: 저장 → 읽기 → 삭제
    assert oa.save_password("flightdata-selftest", "pw-테스트")
    assert oa.load_password("flightdata-selftest") == "pw-테스트"
    assert oa.forget_password("flightdata-selftest") and oa.load_password("flightdata-selftest") is None
    zoneinfo.ZoneInfo("Asia/Seoul")
    api = Api()                                             # js_api 에 함수 말고 객체가 보이면 pywebview 가 그 안을 다 뒤져 창이 멈춤 (1.2.3)
    assert not [n for n in dir(api) if not n.startswith("_") and not callable(getattr(api, n))]
    assert AnalyzerServer().start()
    return 0


def _warmup():
    """무거운 모듈(requests·trino·로그인·업데이트)은 창을 띄우기 **전에** 불러 둔다.
    예전(1.0.46)엔 창과 동시에 뒤에서 불러서, 파이썬 GIL 을 오래 잡는 동안 창(WinForms)이 멈춰 "응답 없음"이 떴음."""
    try:
        import requests  # noqa: F401
        import trino.dbapi  # noqa: F401
        import zoneinfo
        zoneinfo.ZoneInfo("Asia/Seoul")
    except Exception:  # noqa: BLE001
        pass


def _diag(msg):
    """진단 기록: exe 폴더\\app_data\\diag.log (시작 단계 시각·창 멈춤). 실제 Windows 에서 원인을 찾으려고 (1.2.4)."""
    try:
        d = settings.app_data_dir()
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "diag.log")
        if os.path.exists(p) and os.path.getsize(p) > 512 * 1024:
            os.replace(p, p + ".1")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} +{time.time() - _T0:6.2f}s  {msg}\n")
    except OSError:
        pass


def _watchdog(api):
    """창이 2초 넘게 메시지를 처리하지 못하면(= 응답 없음 직전) 그때 모든 스레드가 하던 일을 diag.log 에 남김."""
    if not sys.platform.startswith("win"):
        return
    import ctypes
    import traceback
    from ctypes import wintypes
    send = ctypes.windll.user32.SendMessageTimeoutW
    res = wintypes.DWORD()
    hung_since = None
    while True:
        time.sleep(1)
        try:
            hwnd = api._hwnd() if api._window is not None else 0
        except Exception:  # noqa: BLE001
            hwnd = 0
        if not hwnd:
            continue
        t = time.time()
        ok = send(hwnd, 0, 0, 0, 0x0002, 2000, ctypes.byref(res))   # WM_NULL, SMTO_ABORTIFHUNG, 2초
        if ok:
            if hung_since:
                _diag(f"창 다시 응답 (멈춤 약 {time.time() - hung_since:.1f}초)")
                hung_since = None
            continue
        if hung_since is None:
            hung_since = t
            names = {th.ident: th.name for th in threading.enumerate()}
            stacks = [f"--- {names.get(ident, ident)}\n" + "".join(traceback.format_stack(frame)[-12:])
                      for ident, frame in sys._current_frames().items()]
            _diag("창이 2초 넘게 응답 없음. 스레드 상태:\n" + "\n".join(stacks))


_MUTEX = None                                               # 프로세스가 끝날 때까지 쥐고 있어야 함


def _already_running(focus=True):
    """이미 FlightData 가 떠 있으면 그 창을 앞으로 가져오고 True (1.3.2).
    두 번째로 켜면 8790 을 못 잡아 다른 주소(빈 보관함)로 뜨므로, 새로 띄우지 않고 있던 창을 보여 준다.
    focus=False(업데이트 직후): 예전 창이 닫히는 중이라 표시만 쥐고 False."""
    global _MUTEX
    if not sys.platform.startswith("win"):
        return False
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.CreateMutexW.restype = wintypes.HANDLE
    _MUTEX = k32.CreateMutexW(None, False, "Local\\FlightData.single")
    if k32.GetLastError() != 183 or not focus:              # ERROR_ALREADY_EXISTS 가 아니면 처음 켠 것
        return False
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        buf, cls = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(64)
        u32.GetWindowTextW(hwnd, buf, 64)
        u32.GetClassNameW(hwnd, cls, 64)
        if cls.value.startswith("WindowsForms") and (buf.value == "FlightData" or buf.value.startswith("FlightData ")):   # pywebview 창 "FlightData 1.3.2" (탐색기 창·탭 아님)
            found.append(hwnd)
            return False
        return True
    u32.EnumWindows(each, 0)
    for hwnd in found:
        if u32.IsIconic(hwnd):                              # 작업 표시줄처럼 SC_RESTORE 로 (ShowWindow 로 되살리면 화면(WebView2)이 흰색으로 남음)
            u32.PostMessageW(hwnd, 0x0112, 0xF120, 0)       # WM_SYSCOMMAND, SC_RESTORE
        u32.SetForegroundWindow(hwnd)
    return True


def main():
    _diag(f"시작 {settings.app_version()} {' '.join(sys.argv[1:])}")
    if _already_running(focus="--after-update" not in sys.argv):  # 업데이트 직후엔 예전 창이 아직 닫히는 중일 수 있음
        _diag("이미 실행 중 → 그 창을 앞으로")
        return 0
    _warmup()
    _diag("구성 요소 불러옴")
    srv = AnalyzerServer()
    if "--after-update" in sys.argv:                      # 업데이트로 다시 켜짐: 예전 창이 닫힐 때까지 포트를 기다리고 .old 를 지움
        srv.port_wait = 15
    url = srv.url()
    threading.Thread(target=updater.cleanup_old, daemon=True).start()
    try:
        import webview
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True      # 보관함의 CSV 내려받기 (pywebview 5+)
        except Exception:  # noqa: BLE001
            pass
        api = Api()
        api._window = webview.create_window(f"FlightData {settings.app_version()}".strip(), url, width=1480, height=920, min_size=(1100, 700), js_api=api,
                                           frameless=True, easy_drag=False, hidden=True)   # Windows 제목줄 없이 — 창 버튼·끌기는 화면 헤더에서
        srv.close_window = lambda: api._window.destroy()
        # 창은 숨긴 채 만들고 화면(내부 브라우저 WebView2)이 다 준비되면 보여 줌 (1.2.4, 사용자 보고 "가끔 응답 없음, 기다리면 풀림"):
        # 처음 켤 때 WebView2·.NET 구성 요소를 읽는 몇 초 동안 창이 멈춰 Windows 가 "응답 없음"을 띄웠음 — 안 보이는 창에는 안 뜸
        shown = threading.Event()

        def reveal():
            if shown.is_set():
                return
            shown.set()
            _diag("화면 준비됨 → 창 표시")
            try:
                api.maximize_now()                          # 숨긴 채로 작업 영역에 꽉 (제목줄 없는 창이라 직접)
            except Exception:  # noqa: BLE001
                pass
            api._window.show()
        api._window.events.loaded += reveal
        threading.Timer(20, reveal).start()                 # 화면이 끝내 안 오면 그래도 보여 줌
        api._window.events.shown += lambda: (time.sleep(0.15), api.maximize_now())
        threading.Thread(target=_watchdog, args=(api,), daemon=True).start()
        # private_mode 를 끄고 exe 폴더에 보관 → 분석기의 "저장된 데이터"(IndexedDB)가 다음 실행에도 남음
        _diag("창 만들기")
        webview.start(private_mode=False, storage_path=settings.app_data_dir())
        return 0
    except Exception:  # noqa: BLE001 — 창을 못 띄우면 브라우저로
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0


def run(argv):
    if "--finish-update" in argv:                         # 업데이트 마무리 도우미 (창 없이)
        return updater.finish_update(argv)
    return selftest() if "--selftest" in argv else main()
