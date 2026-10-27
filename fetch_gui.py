#!/usr/bin/env python3
"""
FlightData 수집기 — 창으로 쓰는 버전 (Windows .exe 로 묶어 배포)

왼쪽 카드: 1 계정 · 2 공항 · 3 기간(달력) · 4 저장 → [CSV 받기]
오른쪽 카드: 공항 찾기(이름·도시·IATA·한글) + 지도. 공항을 고르면 ICAO 코드·위치·공항명이 채워지고
            공항 시간대에 맞춰 UTC 오프셋이 자동으로 바뀐다.
아래 카드: 진행 막대 · 상태 · 기록
수집 규칙은 fetch_flights.py 와 같다 (하루씩, day 파티션 필터, 순차 조회, 캐시).
화면은 customtkinter (분석기와 같은 색: 파랑 강조, 공항 표지 노랑은 공항 코드에만), Windows 밝게/어둡게 설정을 따른다.
"""
import datetime as dt
import json
import os
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import customtkinter as ctk

import fetch_flights as ff
from airport_db import AirportDB

try:                                    # 달력 (없으면 날짜를 직접 입력)
    from tkcalendar import Calendar
except Exception:  # noqa: BLE001
    Calendar = None
from map_canvas import AirportMap       # 인터넷 없이 그리는 지도 (Natural Earth 육지 윤곽)

ANALYZER_URL = "https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5"
DEFAULT_AIRPORT = "RKSI"                # 공항 칸을 비워 두면 쓰는 값 (칸에는 회색 예시로만 보임)
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "OpenSky_CSV")
# 분석기와 같은 색 (밝게, 어둡게)
BG = ("#eef1f4", "#0d1116")
CARD = ("#ffffff", "#151a21")
FIELD = ("#e6eaef", "#1e252e")
TEXT = ("#0f1720", "#e9eef4")
TEXT2 = ("#485463", "#b3becb")
MUTED = ("#788496", "#828fa0")
ACCENT = ("#1f5fbf", "#3d82e0")
ACCENT_HOVER = ("#1a4f9e", "#5d9cf0")
SIGN, SIGN_INK = "#f2c230", "#17130a"


def load_settings():
    try:
        with open(ff.SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(d):
    """기존 설정에 d 를 덮어 저장 (테마처럼 따로 저장하는 값을 지우지 않게)."""
    try:
        cur = load_settings()
        cur.update(d)
        with open(ff.SETTINGS, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
    except OSError:
        pass


def open_folder(path):
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606 — 사용자가 고른 폴더를 탐색기로 연다
    else:
        webbrowser.open("file://" + os.path.abspath(path))


def fmt_tz(h):
    if h is None:
        return "?"
    sign = "+" if h >= 0 else "-"
    hh, mm = int(abs(h)), int(round(abs(h) % 1 * 60))
    return f"UTC{sign}{hh}" + (f":{mm:02d}" if mm else "")


class App(ctk.CTk):
    def __init__(self):
        theme = load_settings().get("theme", "system")       # 처음엔 Windows 밝게/어둡게를 따르고, 버튼으로 바꾸면 기억
        ctk.set_appearance_mode(theme if theme in ("light", "dark") else "system")
        super().__init__(fg_color=BG)
        self.title("FlightData 수집기")
        self.geometry("1240x820")
        self.minsize(1060, 700)
        fam = "Malgun Gothic" if sys.platform.startswith("win") else "Noto Sans CJK KR"
        self.f = {k: ctk.CTkFont(family=fam, size=s, weight=w) for k, (s, w) in {
            "title": (20, "bold"), "h": (14, "bold"), "step": (12, "bold"), "body": (13, "normal"),
            "small": (12, "normal"), "code": (15, "bold"), "btn": (13, "bold"), "big": (15, "bold")}.items()}

        self.q = queue.Queue()
        self.worker = None
        self.stop_flag = False
        self.auth_url = None
        self.db = AirportDB()
        self.results = []
        self.hints = []

        s = load_settings()
        today = dt.date.today()
        self.saved = s
        self.tz_auto = None                 # 공항 시간대로 계산한 UTC 오프셋 (회색 예시로 표시, 비워 두면 이 값 사용)
        self._last_ap = None
        self.v_dir = tk.StringVar(value=s.get("out_dir", DEFAULT_DIR))
        self.v_aircraft = tk.BooleanVar(value=s.get("aircraft", True))
        self.v_status = tk.StringVar(value="입력 칸을 채우고 [CSV 받기] 를 누르세요.")
        self.v_apname = tk.StringVar(value="")
        self.v_apinfo = tk.StringVar(value="")
        self.v_tzinfo = tk.StringVar(value="")
        self.v_search = tk.StringVar(value="")
        self.start_default, self.end_default = today - dt.timedelta(days=6), today   # 오늘이 마지막 날, 최근 7일

        self._build()
        self._lookup_airport(move_map=True)
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- 화면 조각 ----------
    def _card(self, parent):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16)

    def _step(self, parent, num, text):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(f, text=str(num), width=22, height=22, corner_radius=11, fg_color=FIELD, text_color=TEXT2,
                     font=self.f["step"]).pack(side="left")
        ctk.CTkLabel(f, text=text, text_color=TEXT2, font=self.f["step"]).pack(side="left", padx=(8, 0))
        return f

    def _hint(self, parent, **kw):
        lb = ctk.CTkLabel(parent, text_color=MUTED, font=self.f["small"], justify="left", anchor="w", **kw)
        self.hints.append(lb)
        return lb

    def _entry(self, parent, var, **kw):
        if var is not None:
            kw["textvariable"] = var
        return ctk.CTkEntry(parent, fg_color=FIELD, border_width=0, corner_radius=10, height=36,
                            text_color=TEXT, font=self.f["body"], **kw)

    def _btn(self, parent, text, cmd, primary=False, **kw):
        if primary:
            kw.setdefault("height", 44)
            return ctk.CTkButton(parent, text=text, command=cmd, fg_color=ACCENT, hover_color=ACCENT_HOVER, corner_radius=10,
                                 font=self.f["big"], **kw)
        kw.setdefault("height", 34)
        kw.setdefault("font", self.f["btn"])
        return ctk.CTkButton(parent, text=text, command=cmd, fg_color=FIELD, hover_color=("#d8dee6", "#283039"),
                             text_color=TEXT, corner_radius=10, **kw)

    # ---------- 밝게 / 어둡게 ----------
    def _sync_theme_btn(self):
        dark = ctk.get_appearance_mode() == "Dark"          # 분석기와 같게: 어두우면 해(밝게로), 밝으면 달(어둡게로)
        self.b_theme.configure(text="☀" if dark else "☾")

    def _toggle_theme(self):
        mode = "light" if ctk.get_appearance_mode() == "Dark" else "dark"
        ctk.set_appearance_mode(mode)
        save_settings({"theme": mode})
        self._sync_theme_btn()

    # ---------- 화면 ----------
    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 10))
        mark = ctk.CTkLabel(head, text="✈", width=36, height=36, corner_radius=10, fg_color=SIGN, text_color=SIGN_INK,
                            font=ctk.CTkFont(size=18, weight="bold"))
        mark.pack(side="left")
        tbox = ctk.CTkFrame(head, fg_color="transparent")
        tbox.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(tbox, text="FlightData 수집기", font=self.f["title"], text_color=TEXT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(tbox, text="받은 CSV 는 FlightData 분석기의 \"운항 CSV 파일\" 에서 고릅니다", font=self.f["small"],
                     text_color=MUTED, anchor="w").pack(anchor="w")
        self._btn(head, "분석기 열기 ↗", lambda: webbrowser.open(ANALYZER_URL), width=130).pack(side="right")
        self.b_theme = self._btn(head, "", self._toggle_theme, width=44, font=ctk.CTkFont(size=18))
        self.b_theme.pack(side="right", padx=(0, 8))
        self._sync_theme_btn()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20)
        body.grid_columnconfigure(0, weight=5, uniform="c")
        body.grid_columnconfigure(1, weight=6, uniform="c")
        body.grid_rowconfigure(0, weight=1)

        # ── 왼쪽 카드: 입력 ──
        left = ctk.CTkScrollableFrame(body, fg_color=CARD, corner_radius=16)     # 화면이 작으면 스크롤
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_columnconfigure(0, weight=1)
        L = {"padx": 20, "sticky": "ew"}
        r = 0

        def add(w, pady=(0, 0), **kw):
            nonlocal r
            w.grid(row=r, column=0, pady=pady, **{**L, **kw})
            r += 1
            return w

        add(self._step(left, 1, "OpenSky 계정"), pady=(18, 6), sticky="w")
        self.e_user = add(self._entry(left, None, placeholder_text="OpenSky 사용자명"))
        if self.saved.get("user"):
            self.e_user.insert(0, self.saved["user"])
        add(self._hint(left, text="비밀번호는 [CSV 받기] 후 열리는 로그인 창에서 입력합니다"), pady=(4, 0))

        add(self._step(left, 2, "공항"), pady=(16, 6), sticky="w")
        aprow = ctk.CTkFrame(left, fg_color="transparent")
        aprow.grid_columnconfigure(1, weight=1)
        # 기본값은 회색 예시(RKSI)로만 보이고, 누르면 사라져 새로 입력. 비워 두면 RKSI 로 받음
        ap = self.e_ap = ctk.CTkEntry(aprow, width=110, height=36, fg_color=SIGN, text_color=SIGN_INK, placeholder_text="RKSI",
                                      placeholder_text_color="#8c7a3c", border_width=0, corner_radius=10, font=self.f["code"], justify="center")
        if self.saved.get("airport") and self.saved["airport"] != DEFAULT_AIRPORT:
            ap.insert(0, self.saved["airport"])
        ap.grid(row=0, column=0, rowspan=2, sticky="w")
        ap.bind("<Return>", lambda e: self._lookup_airport(move_map=True))
        ap.bind("<FocusOut>", lambda e: self._lookup_airport(move_map=True))
        ctk.CTkLabel(aprow, textvariable=self.v_apname, font=self.f["h"], text_color=TEXT, anchor="w", justify="left") \
            .grid(row=0, column=1, sticky="ew", padx=(12, 0))
        self._hint(aprow, textvariable=self.v_apinfo).grid(row=1, column=1, sticky="ew", padx=(12, 0))
        add(aprow)
        tzrow = ctk.CTkFrame(left, fg_color="transparent")
        ctk.CTkLabel(tzrow, text="UTC 오프셋", font=self.f["small"], text_color=TEXT2).pack(side="left")
        self.e_tz = ctk.CTkEntry(tzrow, width=64, height=30, fg_color=FIELD, border_width=0, corner_radius=8, placeholder_text="9",
                                 placeholder_text_color=MUTED, font=self.f["body"], justify="center")      # 비워 두면 자동 값
        self.e_tz.pack(side="left", padx=(8, 8))
        self._hint(tzrow, textvariable=self.v_tzinfo).pack(side="left", fill="x", expand=True)
        add(tzrow, pady=(8, 0))
        add(self._hint(left, text="ICAO 코드를 모르면 오른쪽 '공항 찾기' 에서 이름으로 찾거나 지도를 누르세요"), pady=(4, 0))

        add(self._step(left, 3, "기간 (현지)"), pady=(16, 6), sticky="w")
        prow = ctk.CTkFrame(left, fg_color="transparent")
        self.v_start = tk.StringVar(value=self.start_default.isoformat())
        self.v_end = tk.StringVar(value=self.end_default.isoformat())
        for i, var in enumerate((self.v_start, self.v_end)):
            box = ctk.CTkFrame(prow, fg_color=FIELD, corner_radius=10)
            e = ctk.CTkEntry(box, textvariable=var, width=110, height=36, fg_color="transparent", border_width=0,
                             font=self.f["body"], text_color=TEXT)
            e.pack(side="left", padx=(6, 0))
            e.bind("<FocusOut>", lambda ev: self._update_tz_for_period())
            b_ = ctk.CTkButton(box, text="📅", width=34, height=30, fg_color="transparent", hover_color=CARD, text_color=TEXT2,
                               corner_radius=8, command=lambda v=var: None)
            b_.configure(command=lambda v=var, w=box: self._open_calendar(v, w))
            b_.pack(side="left", padx=(0, 4))
            box.pack(side="left")
            if i == 0:
                ctk.CTkLabel(prow, text="~", text_color=MUTED).pack(side="left", padx=8)
        add(prow, sticky="w")
        qrow = ctk.CTkFrame(left, fg_color="transparent")
        for txt, fn in (("최근 7일", self._last7), ("최근 30일", self._last30)):
            self._btn(qrow, txt, fn, width=86, height=30).pack(side="left", padx=(0, 6))
        add(qrow, pady=(8, 0), sticky="w")
        # 1년 단위: 최근 3개 연도 버튼 + 그 전 연도는 목록 (올해는 1월 1일 ~ 오늘)
        yrow = ctk.CTkFrame(left, fg_color="transparent")
        ctk.CTkLabel(yrow, text="1년 단위", font=self.f["small"], text_color=TEXT2).pack(side="left", padx=(0, 8))
        this = dt.date.today().year
        for y in range(this - 2, this + 1):
            self._btn(yrow, f"{y}" + (" (오늘까지)" if y == this else ""), lambda y=y: self._year(y),
                      width=120 if y == this else 64, height=30).pack(side="left", padx=(0, 6))
        older = [str(y) for y in range(this - 3, 2016, -1)]          # OpenSky 과거 운항 자료는 2017년 무렵부터
        self.v_year = tk.StringVar(value="이전 연도")
        ctk.CTkOptionMenu(yrow, values=older, variable=self.v_year, width=104, height=30, corner_radius=10,
                          fg_color=FIELD, button_color=FIELD, button_hover_color=("#d8dee6", "#283039"), text_color=TEXT,
                          dropdown_fg_color=CARD, dropdown_text_color=TEXT, font=self.f["btn"], dropdown_font=self.f["small"],
                          command=lambda v: self._year(int(v))).pack(side="left")
        add(yrow, pady=(6, 0), sticky="w")
        # 여러 해 (N년): 시작 연도 ~ 끝 연도
        mrow = ctk.CTkFrame(left, fg_color="transparent")
        ctk.CTkLabel(mrow, text="여러 해", font=self.f["small"], text_color=TEXT2).pack(side="left", padx=(0, 8))
        years = [str(y) for y in range(this, 2016, -1)]
        self.v_y0, self.v_y1 = tk.StringVar(value=str(this - 2)), tk.StringVar(value=str(this - 1))
        om = dict(values=years, width=84, height=30, corner_radius=10, fg_color=FIELD, button_color=FIELD,
                  button_hover_color=("#d8dee6", "#283039"), text_color=TEXT, dropdown_fg_color=CARD, dropdown_text_color=TEXT,
                  font=self.f["btn"], dropdown_font=self.f["small"])
        ctk.CTkOptionMenu(mrow, variable=self.v_y0, **om).pack(side="left")
        ctk.CTkLabel(mrow, text="~", text_color=MUTED).pack(side="left", padx=6)
        ctk.CTkOptionMenu(mrow, variable=self.v_y1, **om).pack(side="left")
        self._btn(mrow, "적용", self._years, width=56, height=30).pack(side="left", padx=(6, 0))
        add(mrow, pady=(6, 0), sticky="w")
        self.v_split = tk.BooleanVar(value=True)
        add(ctk.CTkCheckBox(left, text="연도별로 CSV 나누기", variable=self.v_split, command=self._update_span,
                            font=self.f["small"], text_color=TEXT2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            checkbox_width=18, checkbox_height=18, corner_radius=5), pady=(8, 0), sticky="w")
        add(self._hint(left, text="분석기에서 1년씩 보기 좋습니다"), pady=(2, 0))
        self.v_span = tk.StringVar(value="")
        add(ctk.CTkLabel(left, textvariable=self.v_span, font=self.f["small"], text_color=TEXT, anchor="w", justify="left"), pady=(4, 0))
        add(self._hint(left, text="오늘·어제 자료는 OpenSky 가 밤에 갱신해 일부만 있을 수 있습니다 (다음에 받을 때 다시 조회)"), pady=(4, 0))

        add(self._step(left, 4, "저장"), pady=(16, 6), sticky="w")
        frow = ctk.CTkFrame(left, fg_color="transparent")
        frow.grid_columnconfigure(0, weight=1)
        self._entry(frow, self.v_dir).grid(row=0, column=0, sticky="ew")
        self._btn(frow, "바꾸기…", self._pick_dir, width=80, height=36).grid(row=0, column=1, padx=(8, 0))
        add(frow)
        add(ctk.CTkCheckBox(left, text="기종·운항사 정보 붙이기", variable=self.v_aircraft,
                            font=self.f["small"], text_color=TEXT2, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                            checkbox_width=18, checkbox_height=18, corner_radius=5), pady=(10, 0), sticky="w")
        add(self._hint(left, text="처음 한 번 OpenSky 항공기 DB 를 내려받습니다"), pady=(2, 0))

        add(ctk.CTkFrame(left, fg_color="transparent", height=12))
        def rewrap(e):                              # 도움말은 카드 너비에 맞춰 줄바꿈 (화면 배율과 상관없이)
            k = ctk.ScalingTracker.get_widget_scaling(left)
            for lb in self.hints:
                lb.configure(wraplength=max(160, (e.width / k) - 60))
        left.bind("<Configure>", rewrap, add="+")         # add: 스크롤 범위를 고치는 customtkinter 기본 처리를 지우지 않게

        # ── 오른쪽 카드: 공항 찾기 · 지도 ──
        right = self._card(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(right, text="공항 찾기", font=self.f["h"], text_color=TEXT, anchor="w").grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))
        se = self._entry(right, self.v_search, placeholder_text="이름 · 도시 · IATA · 한글  (예: 인천, Tokyo, ICN)")
        se.grid(row=1, column=0, sticky="ew", padx=20)
        se.bind("<KeyRelease>", lambda e: self._search())
        se.bind("<Return>", lambda e: self._pick_result(0))
        # 검색 결과는 검색할 때만 작게(최대 5줄) 보이고, 나머지 공간은 지도
        self.res_box = ctk.CTkFrame(right, fg_color=FIELD, corner_radius=10)
        self.res_box.grid_columnconfigure(0, weight=1)

        mapf = ctk.CTkFrame(right, fg_color=FIELD, corner_radius=12)
        mapf.grid(row=3, column=0, sticky="nsew", padx=20, pady=(10, 4))
        self.map = AirportMap(mapf, self.db, lambda a: self._choose(a, move_map=False), self._map_colors(),
                              scale=ctk.ScalingTracker.get_widget_scaling(self), family=self.f["body"].cget("family"))
        self.map.pack(fill="both", expand=True, padx=6, pady=6)
        zf = ctk.CTkFrame(mapf, fg_color="transparent")
        zf.place(x=14, y=14)
        for t, fn in (("+", self.map.zoom_in), ("−", self.map.zoom_out)):
            ctk.CTkButton(zf, text=t, width=30, height=30, corner_radius=8, fg_color=CARD, hover_color=FIELD, text_color=TEXT,
                          font=self.f["h"], command=fn).pack(pady=(0, 4))
        ctk.CTkLabel(right, text="휠로 확대 · 끌어서 이동 · 누르면 가장 가까운 공항을 고릅니다 (인터넷 없이 동작)",
                     font=self.f["small"], text_color=MUTED, anchor="w").grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 12))

        # ── 아래 카드: 진행 · 기록 ──
        # ── 아래 카드: 실행 버튼 · 진행 · 기록 (항상 보임) ──
        bottom = self._card(self)
        bottom.grid(row=2, column=0, sticky="ew", padx=20, pady=(12, 16))
        bottom.grid_columnconfigure(1, weight=1)
        acts = ctk.CTkFrame(bottom, fg_color="transparent")
        acts.grid(row=0, column=0, rowspan=2, sticky="w", padx=(20, 16), pady=(14, 6))
        self.b_start = self._btn(acts, "CSV 받기", self._start, primary=True, width=150)
        self.b_start.pack(side="left")
        self.b_stop = self._btn(acts, "중지", self._stop, state="disabled", width=70, height=44)
        self.b_stop.pack(side="left", padx=(8, 0))
        self._btn(acts, "저장 폴더 열기", self._open_dir, width=120, height=44).pack(side="left", padx=(8, 0))
        self.b_login = self._btn(acts, "로그인 창 다시 열기", lambda: self.auth_url and webbrowser.open(self.auth_url), height=44)
        self.pb = ctk.CTkProgressBar(bottom, height=8, corner_radius=4, progress_color=ACCENT, fg_color=FIELD)
        self.pb.set(0)
        self.pb.grid(row=0, column=1, sticky="sew", padx=(0, 20), pady=(18, 4))
        ctk.CTkLabel(bottom, textvariable=self.v_status, font=self.f["body"], text_color=TEXT, anchor="w") \
            .grid(row=1, column=1, sticky="new", padx=(0, 20))
        self.log = ctk.CTkTextbox(bottom, height=90, fg_color=FIELD, corner_radius=10, text_color=TEXT2,
                                  font=self.f["small"], wrap="word", state="disabled")
        self.log.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(6, 14))

    # ---------- 공항 ----------
    def _map_colors(self):
        d = 1 if ctk.get_appearance_mode() == "Dark" else 0
        return {"water": ("#dfe7ef", "#0f1620")[d], "land": ("#f7f9fb", "#252e3a")[d], "coast": ("#c9d3de", "#36414f")[d],
                "grid": ("#d3dce6", "#1a2230")[d], "dot": ("#8a97a8", "#6b7888")[d], "accent": ACCENT[d],
                "text": TEXT[d], "muted": MUTED[d]}

    def _show_results(self):
        for w in self.res_box.winfo_children():
            w.destroy()
        if not self.v_search.get().strip():
            self.res_box.grid_forget()
            return
        self.res_box.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 0))
        if not self.results:
            ctk.CTkLabel(self.res_box, text="검색 결과가 없습니다.", text_color=MUTED, font=self.f["small"]).grid(row=0, column=0, sticky="w", padx=8, pady=4)
            return
        TOP = 5
        if len(self.results) > TOP:
            ctk.CTkLabel(self.res_box, text=f"외 {len(self.results) - TOP}곳 — 더 자세히 입력하거나 지도에서 고르세요", text_color=MUTED,
                         font=self.f["small"], anchor="w").grid(row=TOP, column=0, sticky="ew", padx=10, pady=(0, 4))
        for i, a in enumerate(self.results[:TOP]):
            place = ", ".join(x for x in (a.city, a.country) if x)
            text = f"{a.icao}{'  ' + a.iata if a.iata else ''}   {a.name}" + (f"  —  {place}" if place else "") + (f"   ({a.ko})" if a.ko else "")
            ctk.CTkButton(self.res_box, text=text, anchor="w", fg_color="transparent", hover_color=CARD, text_color=TEXT,
                          font=self.f["small"], height=26, corner_radius=8, command=lambda a=a: self._choose(a)) \
                .grid(row=i, column=0, sticky="ew", padx=4, pady=(4 if i == 0 else 0, 0))

    def _search(self):
        self.results = self.db.search(self.v_search.get())
        self._show_results()
        self.map.set_marks(self.results[:20])

    def _pick_result(self, i):
        if 0 <= i < len(self.results):
            self._choose(self.results[i])

    @staticmethod
    def _show_placeholder(entry):
        """프로그램이 칸을 비웠을 때도 회색 예시가 다시 보이게 (customtkinter 는 포커스가 빠질 때만 다시 그림)."""
        if not entry.get() and entry.focus_get() is not entry._entry and hasattr(entry, "_activate_placeholder"):
            entry._activate_placeholder()

    def _airport_text(self):
        return self.e_ap.get().strip() or DEFAULT_AIRPORT

    def _choose(self, a, move_map=True):
        self.e_ap.delete(0, "end")
        self.e_ap.insert(0, a.icao)
        self._lookup_airport(move_map=move_map)

    def _lookup_airport(self, move_map=False):
        codes = ff.parse_airports(self._airport_text())
        a = self.db.get(codes[0]) if codes else None
        if not a:
            self.v_apname.set("모르는 코드" if codes else "")
            self.v_apinfo.set("오른쪽 '공항 찾기' 에서 이름으로 찾아보세요." if codes else "")
            self.v_tzinfo.set("")
            return
        if a.icao != self._last_ap:                         # 공항이 바뀌면 직접 넣은 오프셋을 지우고 자동 값으로
            if self._last_ap is not None:
                self.e_tz.delete(0, "end")
                self._show_placeholder(self.e_tz)
            self._last_ap = a.icao
        extra = f"  외 {len(codes) - 1}곳" if len(codes) > 1 else ""
        self.v_apname.set(a.name + extra)
        self.v_apinfo.set(f"{', '.join(x for x in (a.city, a.country) if x)}  ·  {a.lat:.3f}, {a.lon:.3f}" + (f"  ·  {a.ko}" if a.ko else ""))
        self._update_tz_for_period(a)
        if move_map:
            self.map.show(a, zoom=max(self.map.k, 25))
        else:
            self.map.selected = a
            self.map.redraw()

    def _update_tz_for_period(self, a=None):
        """공항 시간대로 UTC 오프셋 자동 설정 (기간 시작일 기준; 서머타임이 바뀌면 알림)."""
        if hasattr(self, "v_span"):
            self._update_span()
        codes = ff.parse_airports(self._airport_text())
        a = a or (self.db.get(codes[0]) if codes else None)
        if not a:
            return
        try:
            s, e = self._dates()
        except ValueError:
            s = e = dt.date.today()
        h0, h1 = a.utc_offset(s), a.utc_offset(e)
        if h0 is None:
            self.tz_auto = None
            self.v_tzinfo.set("시간대를 몰라 직접 입력하세요")
            return
        self.tz_auto = h0
        self.e_tz.configure(placeholder_text=f"{h0:g}")
        self._show_placeholder(self.e_tz)
        note = f"{a.tz} 기준 자동 ({fmt_tz(h0)}) · 비워 두면 이 값"
        if h1 is not None and h1 != h0:
            note += f" · 기간 중 서머타임 변경({fmt_tz(h1)}), 시작일 기준"
        self.v_tzinfo.set(note)

    # ---------- 기간 ----------
    def _dates(self):
        return dt.date.fromisoformat(self.v_start.get().strip()), dt.date.fromisoformat(self.v_end.get().strip())

    def _set_period(self, a, b):
        self.v_start.set(a.isoformat())
        self.v_end.set(b.isoformat())
        self._update_tz_for_period()

    def _years(self):
        """여러 해: 시작 연도 1월 1일 ~ 끝 연도 12월 31일 (올해면 오늘까지)."""
        y0, y1 = sorted((int(self.v_y0.get()), int(self.v_y1.get())))
        self._set_period(dt.date(y0, 1, 1), min(dt.date(y1, 12, 31), dt.date.today()))

    def _segments(self, s, e):
        """연도별로 나누기를 켜고 기간이 해를 넘으면 [(시작, 끝), …] 연도별 구간, 아니면 한 구간."""
        if not self.v_split.get() or s.year == e.year:
            return [(s, e)]
        return [(max(s, dt.date(y, 1, 1)), min(e, dt.date(y, 12, 31))) for y in range(s.year, e.year + 1)]

    def _update_span(self):
        try:
            s, e = self._dates()
        except ValueError:
            self.v_span.set("날짜를 YYYY-MM-DD 로 입력하세요")
            return
        if e < s:
            self.v_span.set("종료일이 시작일보다 빠릅니다")
            return
        n = (e - s).days + 1
        seg = self._segments(s, e)
        txt = f"선택한 기간: {n:,}일 (하루씩 조회)"
        if len(seg) > 1:
            txt += f" · 연도별 CSV {len(seg)}개 ({seg[0][0].year}~{seg[-1][0].year})"
        if n > 366:
            txt += " · 오래 걸리니 중간에 멈춰도 받은 날은 저장되어 이어받습니다"
        self.v_span.set(txt)

    def _open_calendar(self, var, anchor):
        """날짜 칸 아래에 달력 창을 띄운다 (오늘 이후는 고를 수 없음)."""
        if not Calendar:
            return
        try:
            cur = dt.date.fromisoformat(var.get().strip())
        except ValueError:
            cur = dt.date.today()
        dark = ctk.get_appearance_mode() == "Dark"
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.configure(bg=CARD[1] if dark else "#ffffff")
        x, y = anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height() + 4
        top.geometry(f"+{x}+{y}")
        c = {"bg": CARD[1] if dark else "#ffffff", "fg": TEXT[1] if dark else TEXT[0], "f2": FIELD[1] if dark else FIELD[0],
             "m": MUTED[1] if dark else MUTED[0], "a": ACCENT[1] if dark else ACCENT[0]}
        cal = Calendar(top, selectmode="day", year=cur.year, month=cur.month, day=cur.day, maxdate=dt.date.today(),
                       date_pattern="yyyy-mm-dd", locale="ko_KR", firstweekday="sunday", showweeknumbers=False, borderwidth=0,
                       font=(self.f["body"].cget("family"), 11), background=c["f2"], foreground=c["fg"],
                       headersbackground=c["bg"], headersforeground=c["m"], normalbackground=c["bg"], normalforeground=c["fg"],
                       weekendbackground=c["bg"], weekendforeground=c["fg"], othermonthbackground=c["bg"], othermonthwebackground=c["bg"],
                       othermonthforeground=c["m"], othermonthweforeground=c["m"], selectbackground=c["a"], selectforeground="#ffffff",
                       disabledbackground=c["bg"], disabledforeground=c["m"], disableddaybackground=c["bg"], disableddayforeground=c["m"], bordercolor=c["bg"])
        cal.pack(padx=8, pady=8)

        def pick(_e=None):
            var.set(cal.get_date())
            top.destroy()
            self._update_tz_for_period()
        cal.bind("<<CalendarSelected>>", pick)
        top.bind("<Escape>", lambda e: top.destroy())
        top.bind("<FocusOut>", lambda e: top.after(150, lambda: top.winfo_exists() and top.focus_get() is None and top.destroy()))
        top.focus_force()

    def _last7(self):
        t = dt.date.today()
        self._set_period(t - dt.timedelta(days=6), t)

    def _last30(self):
        t = dt.date.today()
        self._set_period(t - dt.timedelta(days=29), t)

    def _year(self, y):
        """한 해 전체 (올해는 1월 1일부터 오늘까지)."""
        today = dt.date.today()
        self._set_period(dt.date(y, 1, 1), min(dt.date(y, 12, 31), today))

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.v_dir.get() or DEFAULT_DIR)
        if d:
            self.v_dir.set(d)

    def _open_dir(self):
        d = self.v_dir.get() or DEFAULT_DIR
        os.makedirs(d, exist_ok=True)
        open_folder(d)

    # ---------- 수집 ----------
    def _validate(self):
        user = self.e_user.get().strip().lower()
        airports = ff.parse_airports(self._airport_text())
        if not user:
            raise ValueError("OpenSky 사용자명을 입력하세요.")
        if not airports or any(len(a) != 4 for a in airports):
            raise ValueError("공항은 4자리 ICAO 코드로 입력하세요. 모르면 오른쪽 '공항 찾기' 를 쓰세요.")
        txt = self.e_tz.get().strip()
        try:
            tz = float(txt) if txt else (self.tz_auto if self.tz_auto is not None else 9.0)
        except ValueError:
            raise ValueError("UTC 오프셋은 숫자로 입력하세요 (예: 9, -5, 5.5). 비워 두면 공항에 맞춰 자동으로 정합니다.")
        s, e = self._dates()
        if e < s:
            raise ValueError("종료일이 시작일보다 빠릅니다.")
        return user, airports, tz, s.isoformat(), e.isoformat()

    def _start(self):
        try:
            user, airports, tz, start, end = self._validate()
        except ValueError as e:
            messagebox.showwarning("입력 확인", str(e) if str(e) else "날짜·UTC 오프셋을 확인하세요.")
            return
        out_dir = self.v_dir.get().strip() or DEFAULT_DIR
        os.makedirs(out_dir, exist_ok=True)
        save_settings({"user": user, "airport": ",".join(airports), "tz": tz, "out_dir": out_dir, "aircraft": self.v_aircraft.get()})
        self.stop_flag = False
        self.pb.set(0)
        self._clear_log()
        self._busy(True)
        self.v_status.set("수집을 시작합니다…")
        segs = self._segments(dt.date.fromisoformat(start), dt.date.fromisoformat(end))
        self.worker = threading.Thread(target=self._run, args=(user, airports, segs, tz, out_dir, self.v_aircraft.get()), daemon=True)
        self.worker.start()

    def _run(self, user, airports, segs, tz, out_dir, aircraft):
        """구간(연도)마다 차례로 받는다. 캐시를 같이 쓰므로 겹치는 날은 다시 조회하지 않는다."""
        put = self.q.put
        total = sum((e - s).days + 1 for s, e in segs)
        done_days, results = 0, []
        try:
            for j, (s, e) in enumerate(segs, 1):
                tag = f"{s.year}년 ({j}/{len(segs)}) · " if len(segs) > 1 else ""
                if len(segs) > 1:
                    put(("log", f"\n── {s.year}년: {s} ~ {e} ──"))
                outs = {a: os.path.join(out_dir, f"{a}_{s}_{e}.csv") for a in airports}
                seg_days = (e - s).days + 1
                res = ff.collect_many(
                    user, airports, s.isoformat(), e.isoformat(), tz, cache_root=os.path.join(out_dir, "trino_cache"), outs=outs,
                    log=lambda m: put(("log", m)),
                    on_auth_url=lambda url: put(("auth", url)),
                    on_progress=lambda i, n, base=done_days, sd=seg_days, tag=tag:
                        put(("progress", (base + i * sd / n, total, f"{tag}{i} / {n}일"))),
                    should_stop=lambda: self.stop_flag,
                    aircraft_info=aircraft)
                done_days += seg_days
                results += [(ap, v[0], len(v[1])) for ap, v in res.items()]
            put(("done", results))
        except Exception as e:  # noqa: BLE001 — 화면에 그대로 보여 준다
            if results:
                put(("log", "이미 완성된 CSV: " + ", ".join(os.path.basename(p) for _, p, _ in results)))
            put(("error", str(e)))

    def _stop(self):
        self.stop_flag = True
        self.v_status.set("중지 요청 — 지금 받는 날짜가 끝나면 멈춥니다.")

    def _busy(self, on):
        self.b_start.configure(state="disabled" if on else "normal", text="받는 중…" if on else "CSV 받기")
        self.b_stop.configure(state="normal" if on else "disabled")
        if not on:
            self.b_login.pack_forget()

    # ---------- 화면 갱신 (작업 스레드 → 큐 → 여기) ----------
    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._append(val)
                elif kind == "auth":
                    self.auth_url = val
                    self.v_status.set("브라우저에 OpenSky 로그인 창이 열렸습니다. 로그인하면 자동으로 이어집니다.")
                    self.b_login.pack(side="left", padx=(8, 0))
                elif kind == "progress":
                    i, n, txt = val
                    self.pb.set(i / n if n else 0)
                    self.v_status.set(f"{txt} 받음  ·  전체 {i / n:.0%}" if n else txt)
                    self.b_login.pack_forget()
                elif kind == "done":
                    self._busy(False)
                    self.pb.set(1)
                    lines = [f"{ap}: {os.path.basename(p)} ({n:,}건)" for ap, p, n in val]
                    self.v_status.set("완료 — " + " · ".join(lines))
                    self._append("\n완료. 저장 폴더의 CSV 를 분석기 \"운항 CSV 파일\" 에서 고르세요.")
                    if messagebox.askyesno("완료", "CSV 를 저장했습니다.\n\n" + "\n".join(lines) + "\n\n저장 폴더를 열까요?"):
                        self._open_dir()
                elif kind == "error":
                    self._busy(False)
                    self.v_status.set("오류로 멈췄습니다. 아래 기록을 확인하세요.")
                    self._append(f"\n[오류] {val}")
        except queue.Empty:
            pass
        mode = ctk.get_appearance_mode()                    # Windows 밝게/어둡게가 바뀌면 지도 색도 맞춤
        if mode != getattr(self, "_mode", None):
            self._mode = mode
            self.map.set_colors(self._map_colors())
            self._sync_theme_btn()
        self.after(150, self._poll)

    def _append(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("닫기", "수집 중입니다. 닫을까요? (받은 날짜는 저장되어 다음에 이어받습니다)"):
                return
            self.stop_flag = True
        self.destroy()


if __name__ == "__main__":
    if "--selftest" in sys.argv:                            # 빌드 확인용: 필요한 모듈·데이터가 exe 에 들어갔는지
        import trino.auth  # noqa: F401
        import zoneinfo
        assert AirportDB().get("RKSI").utc_offset() == 9
        assert Calendar is not None
        import map_canvas
        assert os.path.exists(map_canvas._data_path("land.json"))
        zoneinfo.ZoneInfo("America/New_York")
        sys.exit(0)
    App().mainloop()
