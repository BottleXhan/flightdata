"""FlightData 업데이트 — GitHub 최신 릴리스를 확인하고, 새 exe 로 바꾼 뒤 다시 시작한다 (사용자 요청 2026-10-28).

실행 중인 exe 는 덮어쓸 수 없지만 이름은 바꿀 수 있다(Windows). 그래서
  1) 최신 릴리스의 FlightData_<버전>.zip 을 받아 (GitHub 가 알려 주는 sha256 이 있으면 대조)
  2) 그 안의 FlightData.exe 를 지금 exe 옆에 FlightData.new.exe 로 풀고
  3) 지금 exe → FlightData.old.exe, 새 exe → 원래 이름으로 바꾼 뒤
  4) 새 exe 를 --after-update 로 띄우고 지금 창을 닫는다 (새 exe 는 시작할 때 .old 를 지움).
설정·항공기 DB·보관함(app_data)·OpenSky_CSV 는 exe 옆에 그대로 남는다.
"""
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import zipfile

REPO = "BottleXhan/flightdata"
API = f"https://api.github.com/repos/{REPO}/releases/latest"


def parse_ver(v):
    """'FlightData_1.0.46' / 'v1.0.46' / '1.0.46' → (1, 0, 46). 모르면 ()."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def exe_path():
    return sys.executable if getattr(sys, "frozen", False) else ""


def cleanup_old():
    """지난 업데이트에서 남은 FlightData.old.exe 를 지운다 (시작할 때)."""
    p = exe_path()
    if not p:
        return
    old = os.path.join(os.path.dirname(p), "FlightData.old.exe")
    for _ in range(20):                                       # 예전 프로세스가 끝날 때까지 잠깐 기다림
        if not os.path.exists(old):
            return
        try:
            os.remove(old)
            return
        except OSError:
            time.sleep(0.5)


class Updater:
    def __init__(self, current):
        self.current = current or ""
        self.lock = threading.Lock()
        self.cache = (0, None)
        self.state, self.text, self.done_bytes, self.total_bytes, self.error = "idle", "", 0, 0, None

    # ---------- 확인 ----------
    def check(self, force=False):
        t, info = self.cache
        if info and not force and time.time() - t < 600:
            return info
        import requests
        r = requests.get(API, timeout=15, headers={"Accept": "application/vnd.github+json"})
        r.raise_for_status()
        j = r.json()
        latest = (j.get("name") or j.get("tag_name") or "").replace("FlightData_", "")
        asset = next((a for a in j.get("assets", []) if a.get("name", "").lower().endswith(".zip")), None)
        info = {"current": self.current, "latest": latest, "newer": bool(parse_ver(latest) > parse_ver(self.current) and parse_ver(self.current)),
                "notes": j.get("body") or "", "page": j.get("html_url") or f"https://github.com/{REPO}/releases/latest",
                "asset": asset and asset.get("browser_download_url"), "size": asset and asset.get("size"),
                "digest": (asset or {}).get("digest") or "", "canApply": bool(exe_path() and asset)}
        self.cache = (time.time(), info)
        return info

    def status(self):
        with self.lock:
            return {"state": self.state, "text": self.text, "done": self.done_bytes, "total": self.total_bytes, "error": self.error}

    # ---------- 적용 ----------
    def apply(self):
        if not exe_path():
            raise RuntimeError("개발 실행(파이썬)에서는 업데이트할 수 없습니다. exe 에서 하세요.")
        with self.lock:
            if self.state == "running":
                raise RuntimeError("이미 업데이트하는 중입니다.")
            self.state, self.text, self.done_bytes, self.total_bytes, self.error = "running", "최신 버전 확인 중…", 0, 0, None
        threading.Thread(target=self._run, daemon=True).start()

    def _set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def _run(self):
        try:
            import requests
            info = self.check(force=True)
            if not info["asset"]:
                raise RuntimeError("최신 릴리스에 zip 파일이 없습니다.")
            self._set(text=f"FlightData_{info['latest']} 받는 중…", total_bytes=info.get("size") or 0)
            buf = io.BytesIO()
            with requests.get(info["asset"], stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1 << 16):
                    buf.write(chunk)
                    self._set(done_bytes=buf.tell())
            data = buf.getvalue()
            dg = info.get("digest") or ""
            if dg.startswith("sha256:") and hashlib.sha256(data).hexdigest() != dg.split(":", 1)[1]:
                raise RuntimeError("받은 파일이 손상되었습니다 (sha256 불일치). 다시 시도하세요.")
            self._set(text="새 버전으로 바꾸는 중…")
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                name = next((n for n in z.namelist() if n.lower().endswith("/flightdata.exe") or n.lower() == "flightdata.exe"), None)
                if not name:
                    raise RuntimeError("zip 안에 FlightData.exe 가 없습니다.")
                exe_bytes = z.read(name)
            cur = exe_path()
            d = os.path.dirname(cur)
            new, old = os.path.join(d, "FlightData.new.exe"), os.path.join(d, "FlightData.old.exe")
            with open(new, "wb") as f:
                f.write(exe_bytes)
            if os.path.exists(old):
                try:
                    os.remove(old)
                except OSError:
                    pass
            os.replace(cur, old)                              # 실행 중인 exe 는 이름만 바꿀 수 있음
            try:
                os.replace(new, cur)
            except OSError:
                os.replace(old, cur)                          # 실패하면 원래대로
                raise
            self._set(state="ready", text=f"FlightData_{info['latest']} 로 바꿨습니다. 다시 시작합니다…")
        except Exception as e:  # noqa: BLE001
            self._set(state="error", error=str(e), text="")

    def restart(self, close_window):
        """새 exe 를 띄우고 지금 창을 닫는다."""
        cur = exe_path()
        if self.state != "ready" or not cur:
            raise RuntimeError("업데이트가 아직 끝나지 않았습니다.")
        flags = 0x00000008 | 0x00000200 if sys.platform.startswith("win") else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen([cur, "--after-update"], cwd=os.path.dirname(cur), creationflags=flags, close_fds=True)
        threading.Timer(0.3, close_window).start()


def notes_text(md):
    """릴리스 설명에서 '이번 버전에서 바뀐 것' 목록만 (화면용)."""
    lines = (md or "").splitlines()
    out, on = [], False
    for ln in lines:
        if ln.startswith("### "):
            on = "바뀐" in ln
            continue
        if on and ln.startswith("- "):
            out.append(ln[2:].replace("**", ""))
    return out


if __name__ == "__main__":
    print(json.dumps(Updater("1.0.0").check(), ensure_ascii=False, indent=1))
