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


def main():
    srv = local_web.AnalyzerServer()
    url = srv.url()
    try:
        import webview
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True      # 보관함의 CSV 내려받기 (pywebview 5+)
        except Exception:  # noqa: BLE001
            pass
        api = Api()
        api.window = webview.create_window("FlightData", url, width=1480, height=920, min_size=(1100, 700), maximized=True, js_api=api)
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
