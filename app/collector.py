"""화면에서 시작한 수집 한 건 (한 번에 하나): 입력 확인 → 작업 스레드에서 fetch_flights.collect_many → 진행·기록을 화면이 가져감."""
import datetime as dt
import os
import threading
import time

import fetch_flights as ff
import opensky_auth as oa

from app import settings


def year_segments(s, e):
    """연도별로 나눈 구간 [(시작, 끝), …] (한 해 안이면 하나)."""
    out, a = [], s
    while a <= e:
        b = min(e, dt.date(a.year, 12, 31))
        out.append((a, b))
        a = b + dt.timedelta(days=1)
    return out


class Collector:
    def __init__(self, server):
        self.server, self.lock = server, threading.Lock()
        self.state, self.log, self.i, self.n, self.text = "idle", [], 0, 0, ""
        self.auth_url = self.error = None
        self.results, self.stop = [], False

    def status(self, since=0):
        with self.lock:
            return {"state": self.state, "i": self.i, "n": self.n, "text": self.text, "authUrl": self.auth_url,
                    "error": self.error, "results": [os.path.basename(p) for _, p, _ in self.results],
                    "log": self.log[since:], "logLen": len(self.log)}

    def _log(self, m):
        with self.lock:
            self.log.append(str(m))

    def request_stop(self):
        """바로 멈춤: 다음 날짜 전에 멈추고, 실행 중인 Trino 쿼리도 취소."""
        self.stop = True
        with self.lock:
            self.text = "중지하는 중…"
        ff.cancel_current()

    def start(self, p):
        if self.state == "running" and self.stop:          # 중지 직후: 작업이 끝날 때까지 잠깐 기다림
            for _ in range(40):
                if self.state != "running":
                    break
                time.sleep(0.25)
        if self.state == "running":
            raise RuntimeError("이미 받는 중입니다." + (" 중지하는 중이니 잠시 뒤 다시 누르세요." if self.stop else ""))
        user = (p.get("user") or "").strip().lower()
        airports = ff.parse_airports(p.get("airport") or "")
        if not user:
            raise ValueError("OpenSky 사용자명을 입력하세요.")
        if not airports or any(len(a) != 4 for a in airports):
            raise ValueError("공항은 4자리 ICAO 코드로 입력하세요.")
        s, e = dt.date.fromisoformat(p["start"]), dt.date.fromisoformat(p["end"])
        if e < s:
            raise ValueError("종료일이 시작일보다 빠릅니다.")
        tz = float(p.get("tz", 9))
        remember, pw = bool(p.get("remember")), p.get("password") or ""
        if not pw and self.server.session and self.server.session[0] == user:   # 머리에서 로그인한 비밀번호
            pw = self.server.session[1]
        try:
            if pw and remember:
                oa.save_password(user, pw)
            elif not pw and remember:
                pw = oa.load_password(user) or ""
            elif not remember:
                oa.forget_password(user)
        except Exception:  # noqa: BLE001 — 저장 실패해도 이번 수집은 진행
            pass
        out_dir = (p.get("outDir") or "").strip() or settings.out_dir()
        os.makedirs(out_dir, exist_ok=True)
        aircraft, split = bool(p.get("aircraft", True)), bool(p.get("split", True))
        settings.save({"user": user, "airport": ",".join(airports), "tz": tz, "out_dir": settings.out_dir_value(out_dir),
                       "aircraft": aircraft, "remember_pw": remember, "split": split})
        segs = year_segments(s, e) if split else [(s, e)]
        with self.lock:
            self.state, self.log, self.i, self.n, self.text = "running", [], 0, 0, "시작하는 중…"
            self.auth_url = self.error = None
            self.results, self.stop = [], False
        threading.Thread(target=self._run, args=(user, airports, segs, tz, out_dir, aircraft, pw or None), daemon=True).start()

    def _run(self, user, airports, segs, tz, out_dir, aircraft, password):
        total = sum((b - a).days + 1 for a, b in segs)
        done, results = 0, []
        try:
            for j, (a, b) in enumerate(segs, 1):
                tag = f"{a.year}년 ({j}/{len(segs)}) · " if len(segs) > 1 else ""
                if len(segs) > 1:
                    self._log(f"── {a.year}년: {a} ~ {b} ──")
                outs = {ap: os.path.join(out_dir, f"{ap}_{a}_{b}.csv") for ap in airports}
                sd = (b - a).days + 1

                def prog(i, n, base=done, sd=sd, tag=tag):
                    with self.lock:
                        self.i, self.n, self.text, self.auth_url = base + i * sd / n, total, f"{tag}{i} / {n}일", None

                def auth(url):
                    with self.lock:
                        self.auth_url, self.text = url, "브라우저에 OpenSky 로그인 창이 열렸습니다. 로그인하면 이어집니다."

                res = ff.collect_many(user, airports, a.isoformat(), b.isoformat(), tz, cache_root=os.path.join(out_dir, "trino_cache"),
                                      outs=outs, log=self._log, on_auth_url=auth, on_progress=prog,
                                      should_stop=lambda: self.stop, aircraft_info=aircraft, password=password)
                done += sd
                results += [(ap, v[0], len(v[1])) for ap, v in res.items()]
            with self.lock:
                self.results, self.state, self.i, self.n = results, "done", total, total
            self.server.set_csvs([pth for _, pth, _ in results])
        except Exception as ex:  # noqa: BLE001 — 화면에 그대로 보여 준다
            with self.lock:
                self.results, self.error = results, str(ex)
                self.state = "stopped" if isinstance(ex, ff.Stopped) or self.stop else "error"
            if results:
                self.server.set_csvs([pth for _, pth, _ in results])
