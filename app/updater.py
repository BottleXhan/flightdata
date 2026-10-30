"""FlightData 업데이트 — GitHub 최신 릴리스를 확인하고, 새 exe 로 바꾼 뒤 다시 시작한다 (사용자 요청 2026-10-28).

exe 이름에 버전이 붙는다 (FlightData_1.2.2.exe, 사용자 요청 2026-10-28). 그래서
  1) 최신 릴리스의 FlightData_<버전>.zip 을 받아 (GitHub 가 알려 주는 sha256 이 있으면 대조)
  2) 그 안의 exe 를 지금 exe 옆에 FlightData_<새 버전>.exe 로 풀고 (이름이 같으면 예전 방식: 지금 exe → FlightData.old.exe)
  4) 새 exe 를 임시 폴더에 복사해 --finish-update 도우미로 띄우고 창을 닫으면, 도우미가 끝나기를 기다렸다가
     FlightData.old.exe 를 지우고, 폴더 이름이 FlightData_<버전> 이면 새 버전 이름으로 바꾼 뒤 새 exe 를 --after-update 로 띄운다.
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


def _old_exes(d, keep):
    """폴더 안의 이전 버전 exe: FlightData.old.exe · FlightData.new.exe · (버전 이름 exe 를 쓰면) 예전 이름 FlightData.exe · 지금보다 낮은 FlightData_x.y.z.exe."""
    keep_v = parse_ver(os.path.basename(keep))
    out = []
    for f in os.listdir(d):
        lf = f.lower()
        if not (lf.startswith("flightdata") and lf.endswith(".exe")) or os.path.normcase(os.path.join(d, f)) == os.path.normcase(keep):
            continue
        v = parse_ver(f)
        if lf in ("flightdata.old.exe", "flightdata.new.exe") or (lf == "flightdata.exe" and keep_v) or (v and keep_v and v < keep_v):
            out.append(os.path.join(d, f))
    return out


def cleanup_old():
    """지난 업데이트에서 남은 이전 버전 exe·도우미를 지운다 (시작할 때)."""
    try:
        cleanup_helpers()
    except Exception:  # noqa: BLE001
        pass
    p = exe_path()
    if not p:
        return
    for _ in range(20):                                       # 예전 프로세스가 끝날 때까지 잠깐 기다림
        left = []
        for f in _old_exes(os.path.dirname(p), p):
            try:
                os.remove(f)
            except OSError:
                left.append(f)
        if not left:
            return
        time.sleep(0.5)


class Updater:
    def __init__(self, current):
        self.current = current or ""
        self.lock = threading.Lock()
        self.cache = (0, None)
        self.state, self.text, self.done_bytes, self.total_bytes, self.error = "idle", "", 0, 0, None
        self.new_exe = ""

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
                name = next((n for n in z.namelist() if re.search(r"(^|/)flightdata[^/]*\.exe$", n.lower())), None)
                if not name:
                    raise RuntimeError("zip 안에 FlightData exe 가 없습니다.")
                exe_bytes = z.read(name)
            cur = exe_path()
            d = os.path.dirname(cur)
            target = os.path.join(d, f"FlightData_{info['latest']}.exe")
            if os.path.normcase(target) != os.path.normcase(cur):
                tmp = target + ".part"
                with open(tmp, "wb") as f:
                    f.write(exe_bytes)
                os.replace(tmp, target)                       # 지금 exe 는 그대로 두고 옆에 새 이름으로 (끝난 뒤 도우미가 지움)
                self.new_exe = target
            else:                                             # 이름이 같으면 (예전 방식) 실행 중인 exe 는 이름만 바꿀 수 있음
                new, old = os.path.join(d, "FlightData.new.exe"), os.path.join(d, "FlightData.old.exe")
                with open(new, "wb") as f:
                    f.write(exe_bytes)
                if os.path.exists(old):
                    try:
                        os.remove(old)
                    except OSError:
                        pass
                os.replace(cur, old)
                try:
                    os.replace(new, cur)
                except OSError:
                    os.replace(old, cur)                      # 실패하면 원래대로
                    raise
                self.new_exe = cur
            self._set(state="ready", text=f"FlightData_{info['latest']} 로 바꿨습니다. 다시 시작합니다…")
        except Exception as e:  # noqa: BLE001
            self._set(state="error", error=str(e), text="")

    def restart(self, close_window):
        """새 exe 로 다시 시작. 새 exe 를 임시 폴더에 복사해 '마무리 도우미'(--finish-update)로 띄움 — 창 없는 exe 라 검은 명령창이 안 뜸.
        도우미가 지금 프로세스가 끝나길 기다렸다가 (1) 이전 exe(FlightData.old.exe) 삭제, (2) 폴더 이름이 FlightData_<버전> 이면
        새 버전 이름으로 바꾸고 (사용자 요청), (3) 새 exe 를 --after-update 로 실행.
        (1.1.5·1.1.6 은 cmd 스크립트를 썼는데 Windows Terminal 창이 뜨고 find 에서 멈춤 — 사용자 보고)"""
        cur = exe_path()
        if self.state != "ready" or not cur:
            raise RuntimeError("업데이트가 아직 끝나지 않았습니다.")
        d = os.path.dirname(cur)
        parent, base = os.path.dirname(d), os.path.basename(d)
        latest = (self.cache[1] or {}).get("latest", "")
        to = new_folder_name(base, latest)
        if to and os.path.exists(os.path.join(parent, to)):
            to = ""
        import shutil
        import tempfile
        tmp = tempfile.gettempdir()
        helper = os.path.join(tmp, f"FlightData_update_{os.getpid()}.exe")
        shutil.copy2(cur, helper)                         # 폴더 밖에서 돌아야 폴더 이름을 바꿀 수 있음
        pids = [os.getpid()] + ([os.getppid()] if getattr(sys, "frozen", False) else [])   # onefile 은 부모(부트로더)가 exe 를 잡고 있음
        args = [helper, "--finish-update", "--pids", ",".join(map(str, pids)), "--dir", d, "--to", to,
                "--exe", os.path.basename(self.new_exe or cur)]
        flags = 0x08000000 if sys.platform.startswith("win") else 0   # CREATE_NO_WINDOW
        subprocess.Popen(args, cwd=tmp, creationflags=flags, close_fds=True)
        threading.Timer(0.3, close_window).start()
        threading.Timer(4.0, lambda: os._exit(0)).start()   # 창을 닫아도 프로세스가 남으면 강제로 끝냄 (도우미가 기다리지 않게)


def new_folder_name(base, latest):
    """폴더 이름 안의 버전을 새 버전으로: 'FlightData_1.1.7' → 'FlightData_1.2.2', 'FlightData_1.1.7 (2)' 도. 버전이 없으면 '' (그대로 둠)."""
    if not latest or not parse_ver(latest) or not base.lower().startswith("flightdata"):
        return ""
    m = re.search(r"\d+\.\d+\.\d+", base)
    if not m or m.group(0) == latest:
        return ""
    return base[:m.start()] + latest + base[m.end():]


def _arg(argv, name, default=""):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def finish_update(argv):
    """--finish-update 로 실행된 도우미 (임시 폴더의 새 exe 복사본). 창·서버 없이 일만 하고 끝남."""
    pids = [int(x) for x in _arg(argv, "--pids").split(",") if x.strip().isdigit()]
    d, to, exe_name = _arg(argv, "--dir"), _arg(argv, "--to"), _arg(argv, "--exe", "FlightData.exe")
    if sys.platform.startswith("win"):
        import ctypes
        k = ctypes.windll.kernel32
        for pid in pids:                                  # 예전 프로세스가 끝날 때까지 (최대 30초씩)
            h = k.OpenProcess(0x00100000, False, pid)     # SYNCHRONIZE
            if h:
                k.WaitForSingleObject(h, 30000)
                k.CloseHandle(h)
    time.sleep(0.5)
    keep = os.path.join(d, exe_name)
    for _ in range(20):                                   # 이전 버전 exe 삭제 (사용자 요청)
        left = []
        for f in _old_exes(d, keep):
            try:
                os.remove(f)
            except OSError:
                left.append(f)
        if not left:
            break
        time.sleep(0.5)
    target = d
    if to and not os.path.exists(os.path.join(os.path.dirname(d), to)):
        for _ in range(10):                               # 백신 검사 등으로 잠깐 잠겨 있을 수 있음
            try:
                os.rename(d, os.path.join(os.path.dirname(d), to))
                target = os.path.join(os.path.dirname(d), to)
                break
            except OSError:
                time.sleep(1)
    exe = os.path.join(target, exe_name)
    subprocess.Popen([exe, "--after-update"], cwd=target, close_fds=True)
    return 0


def cleanup_helpers():
    """지난 업데이트 도우미(임시 폴더의 FlightData_update_*.exe)와 1.1.5·1.1.6 의 cmd 스크립트를 지움."""
    import glob
    import tempfile
    for _ in range(10):
        left = glob.glob(os.path.join(tempfile.gettempdir(), "FlightData_update_*.exe")) + \
            glob.glob(os.path.join(tempfile.gettempdir(), "flightdata_update_*.cmd"))
        for f in list(left):
            try:
                os.remove(f)
                left.remove(f)
            except OSError:
                pass
        if not left:
            return
        time.sleep(2)


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
