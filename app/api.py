"""/api/* 처리 함수. 함수마다 @get / @post 로 경로를 붙이고, server.py 가 경로로 찾아 부른다.
GET 은 쿼리(dict of list), POST 는 JSON 본문(dict)을 받아 Reply 를 돌려준다.

- 비밀번호는 화면에서 받아 이 PC 의 Windows 자격 증명 관리자에만 저장(선택)하고, 화면으로 돌려주지 않는다
- 머리의 로그인: /api/login 이 OpenSky 인증 서버에서 토큰을 받아 확인하고, 이 실행 동안 메모리(srv.session)에만 둔다
- CSV 는 경로를 받지 않고 번호로만 연다 (/csv/<n> = 방금 받은 것, /api/file/<n> = 보관함에 보여 준 저장 폴더 목록)
"""
import json
import os
import sys
import webbrowser
from collections import namedtuple

import opensky_auth as oa

from app import settings, updater

Reply = namedtuple("Reply", "code body ctype headers", defaults=("text/plain; charset=utf-8", {}))
GET, POST = {}, {}


def ok(obj=None, code=200):
    return Reply(code, json.dumps({"ok": True} if obj is None else obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")


def error(msg, code):
    return ok({"error": msg}, code)


def text(code, msg):
    return Reply(code, msg.encode())


def csv_file(path):
    try:
        with open(path, "rb") as f:
            return Reply(200, f.read(), "text/csv; charset=utf-8")
    except OSError:
        return text(404, "not found")


def route(table, path):
    """경로가 '/' 로 끝나면 앞부분이 같은 모든 경로 (나머지를 rest 로 넘김)."""
    def deco(fn):
        table[path] = fn
        return fn
    return deco


def get(path):
    return route(GET, path)


def post(path):
    return route(POST, path)


def dispatch(table, srv, path, arg):
    if path in table:
        return table[path](srv, arg)
    for p, fn in table.items():
        if p.endswith("/") and path.startswith(p):
            return fn(srv, arg, path[len(p):])
    return text(404, "not found")


def _q(q, name, default=""):
    return (q.get(name) or [default])[0]


# ---------- 화면 시작 ----------

@get("/api/collector")
def collector_info(srv, q):
    """화면이 처음 묻는 것: 프로그램 안인지, 로그인·설정 상태, 버전, 방금 받은 CSV 이름."""
    st = settings.load()
    user = st.get("user", "")
    saved = False
    try:
        saved = bool(user and st.get("remember_pw", False) and oa.load_password(user))
    except Exception:  # noqa: BLE001
        pass
    return ok({"files": [os.path.basename(p) for p in srv.csvs], "app": True,
               "canRemember": oa.CAN_REMEMBER, "pwSaved": saved,
               "loggedIn": srv.session[0] if srv.session else None,
               "version": settings.app_version(), "inTemp": settings.in_temp_dir(),
               "settings": {"user": user, "remember": st.get("remember_pw", False), "split": st.get("split", True),
                            "aircraft": st.get("aircraft", True), "outDir": settings.out_dir()}})


@get("/csv/")
def collected_csv(srv, q, rest):
    try:
        return csv_file(srv.csvs[int(rest)])
    except (ValueError, IndexError):
        return text(404, "not found")


@get("/icao-source.html")
def icao_source(srv, q):
    """ICAO 원문 페이지(저작권 문서 번역)는 exe 에 넣지 않으므로 웹 링크로."""
    return Reply(302, b"", headers={"Location": settings.WEB_URL})


# ---------- 로그인 ----------

@get("/api/pwsaved")
def pw_saved(srv, q):
    try:
        return ok({"saved": bool(oa.load_password(_q(q, "user")))})
    except Exception:  # noqa: BLE001
        return ok({"saved": False})


@post("/api/login")
def login(srv, body):
    user = (body.get("user") or "").strip().lower()
    pw, remember = body.get("password") or "", bool(body.get("remember", False))
    if not user:
        return error("OpenSky 사용자명을 넣으세요.", 400)
    if not pw:
        try:
            pw = oa.load_password(user) or ""
        except Exception:  # noqa: BLE001
            pw = ""
    if not pw:
        return error("비밀번호를 넣으세요.", 400)
    try:
        oa.PasswordToken(user, pw).token()
    except oa.LoginError as e:
        return error(str(e), 401)
    except Exception as e:  # noqa: BLE001
        return error(f"로그인을 확인하지 못했습니다: {e}", 502)
    srv.session, saved = (user, pw), False
    try:
        if remember:
            saved = bool(oa.save_password(user, pw))
        else:
            oa.forget_password(user)
    except Exception:  # noqa: BLE001
        pass
    settings.save({"user": user, "remember_pw": remember})
    return ok({"ok": True, "user": user, "saved": saved})


@post("/api/autologin")
def autologin(srv, body):
    """로그인한 뒤 자동 로그인 켜기·끄기."""
    on = bool(body.get("on"))
    user = srv.session[0] if srv.session else settings.load().get("user", "")
    try:
        if on:
            if not srv.session:
                return error("먼저 로그인하세요.", 400)
            if not oa.save_password(srv.session[0], srv.session[1]):
                return error("이 PC 에 비밀번호를 저장하지 못했습니다.", 500)
        elif user:
            oa.forget_password(user)
    except Exception as e:  # noqa: BLE001
        return error(f"자동 로그인 설정 실패: {e}", 500)
    settings.save({"remember_pw": on})
    return ok({"ok": True, "on": on})


@post("/api/logout")
def logout(srv, body):
    user = srv.session[0] if srv.session else settings.load().get("user", "")
    srv.session = None
    if body.get("forget") and user:
        try:
            oa.forget_password(user)
        except Exception:  # noqa: BLE001
            pass
    return ok()


@post("/api/open-url")
def open_url(srv, body):
    """회원가입 안내: OpenSky 홈페이지만 기본 브라우저로."""
    u = (body.get("url") or "").strip()
    if not (u == "https://opensky-network.org/" or u.startswith("https://opensky-network.org/")):
        return text(403, "forbidden")
    webbrowser.open(u)
    return ok()


# ---------- 수집 ----------

@post("/api/collect")
def collect(srv, body):
    try:
        srv.collector.start(body)
    except (ValueError, RuntimeError, KeyError) as e:
        return error(str(e), 409 if isinstance(e, RuntimeError) else 400)
    return ok()


@get("/api/collect/status")
def collect_status(srv, q):
    return ok(srv.collector.status(int(_q(q, "since", "0") or 0)))


@post("/api/collect/stop")
def collect_stop(srv, body):
    srv.collector.request_stop()
    return ok()


# ---------- 저장 폴더 · 보관함 ----------

@post("/api/settings")
def change_out_dir(srv, body):
    """저장 폴더 바꾸기: 만들고 쓰기 확인 후 설정에 저장."""
    raw = (body.get("outDir") or "").strip()
    if not raw:
        return error("폴더를 고르세요.", 400)
    d = os.path.abspath(os.path.expanduser(raw))
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".flightdata_write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return error(f"이 폴더에 저장할 수 없습니다: {e}", 400)
    settings.save({"out_dir": settings.out_dir_value(d)})
    return ok({"ok": True, "outDir": d})


@post("/api/open-folder")
def open_folder(srv, body):
    d = (body.get("dir") or "").strip() or settings.out_dir()
    os.makedirs(d, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(d)  # noqa: S606 — 사용자가 고른 저장 폴더를 탐색기로
    else:
        webbrowser.open("file://" + d)
    return ok()


@get("/api/files")
def disk_files(srv, q):
    """보관함: 저장 폴더의 CSV 목록 (새것부터). 내용은 번호로만 열 수 있음."""
    d = settings.out_dir()
    try:
        names = sorted((n for n in os.listdir(d) if n.lower().endswith(".csv") and os.path.isfile(os.path.join(d, n))),
                       key=lambda n: -os.path.getmtime(os.path.join(d, n)))
    except OSError:
        names = []
    srv.disk = [os.path.join(d, n) for n in names]
    return ok({"dir": d, "files": [{"name": n, "size": os.path.getsize(p), "mtime": os.path.getmtime(p)} for n, p in zip(names, srv.disk)]})


@get("/api/file/")
def disk_file(srv, q, rest):
    try:
        return csv_file(srv.disk[int(rest)])
    except (ValueError, IndexError):
        return text(404, "not found")


# ---------- 업데이트 ----------

@get("/api/update/check")
def update_check(srv, q):
    """새 버전 확인 (GitHub 최신 릴리스)."""
    try:
        info = dict(srv.updater.check(force=bool(q.get("force"))))
        info["changes"] = updater.notes_text(info.get("notes"))
        return ok(info)
    except Exception as e:  # noqa: BLE001
        return error(f"새 버전을 확인하지 못했습니다: {e}", 502)


@get("/api/update/status")
def update_status(srv, q):
    return ok(srv.updater.status())


@post("/api/update/apply")
def update_apply(srv, body):
    if srv.collector.state == "running":
        return error("데이터를 받는 중에는 업데이트할 수 없습니다. 먼저 중지하세요.", 409)
    try:
        srv.updater.apply()
    except RuntimeError as e:
        return error(str(e), 409)
    return ok()


@post("/api/update/restart")
def update_restart(srv, body):
    try:
        srv.updater.restart(srv.close_window or (lambda: os._exit(0)))
    except RuntimeError as e:
        return error(str(e), 409)
    return ok()
