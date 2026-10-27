"""인터넷 없이 그리는 공항 지도 (tkinter Canvas).

지도 타일 서버(OpenStreetMap·CARTO 등)는 프로그램 접속을 막거나 API 키를 요구하고, 회사 망에서 막히기도 해서
Natural Earth 1:50m 육지 윤곽(land.json, 공개 데이터)을 직접 그린다.
- 휠: 커서 위치 기준 확대/축소, 끌기: 이동, 누르기: 가장 가까운 공항 선택
- 확대하면 IATA 코드가 있는 공항이 작은 점으로 보인다
"""
import json
import math
import os
import sys
import tkinter as tk


def _data_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


class AirportMap(tk.Canvas):
    def __init__(self, master, db, on_pick, colors, scale=1.0, family="", **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self.db, self.on_pick, self.c = db, on_pick, colors
        self.s, self.family = scale, family                       # 화면 배율 (Windows 125%·150% 등) — 글자·점 크기에 곱함
        with open(_data_path("land.json"), encoding="utf-8") as f:
            d = json.load(f)
        # 넓게 볼 때 쓸 성긴 윤곽을 미리 만들어 둠 (점 간격 1·3·8)
        lod = lambda p: {1: p, 3: p[::3] if len(p) > 30 else p, 8: p[::8] if len(p) > 80 else p}
        self.land = [(lod(p), self._bbox(p)) for p in d["land"]]
        self.holes = [(lod(p), self._bbox(p)) for p in d.get("holes", [])]
        self._redraw_job = None
        self._span = None                                          # 창 크기를 알게 되면 맞출 위도 폭 (처음 배율)
        # 확대했을 때 보일 공항: 주요 공항(한글 이름 사전에 있는 곳)이 글자 자리를 먼저 차지
        self.small = sorted((a for a in db.items if a.iata), key=lambda a: 0 if a.ko else 1)
        self.lon, self.lat, self.k = 127.0, 37.0, 12.0              # 가운데 경도·위도, 1도당 픽셀
        self.selected, self.marks = None, []
        self._drag = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)                     # Windows / macOS
        self.bind("<Button-4>", lambda e: self._zoom(1.25, e.x, e.y, later=True))   # Linux
        self.bind("<Button-5>", lambda e: self._zoom(0.8, e.x, e.y, later=True))

    @staticmethod
    def _bbox(poly):
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        return min(xs), min(ys), max(xs), max(ys)

    # ---------- 좌표 변환 (가운데 위도에서 경도 비율을 맞춘 단순 투영) ----------
    def _fx(self):
        return self.k * max(0.2, math.cos(math.radians(self.lat)))

    def to_xy(self, lon, lat):
        w, h = self.winfo_width(), self.winfo_height()
        dlon = (lon - self.lon + 540) % 360 - 180
        return w / 2 + dlon * self._fx(), h / 2 - (lat - self.lat) * self.k

    def to_lonlat(self, x, y):
        w, h = self.winfo_width(), self.winfo_height()
        return self.lon + (x - w / 2) / self._fx(), self.lat - (y - h / 2) / self.k

    def view_bbox(self):
        w, h = self.winfo_width(), self.winfo_height()
        lon0, lat1 = self.to_lonlat(0, 0)
        lon1, lat0 = self.to_lonlat(w, h)
        return lon0, lat0, lon1, lat1

    # ---------- 그리기 ----------
    def set_colors(self, colors):
        self.c = colors
        self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        self.configure(bg=self.c["water"])
        x0, y0, x1, y1 = self.view_bbox()
        fx, k, cx, cy = self._fx(), self.k, w / 2, h / 2

        step = 1 if k > 12 else 3 if k > 4 else 8                   # 넓게 볼수록 성긴 윤곽
        min_px = 1.2                                                 # 화면에서 1픽셀 남짓 가까운 점은 건너뜀 (그리는 양 줄이기)

        def draw(polys, fill):
            for lods, (a, b, c_, d) in polys:
                if d < y0 - 1 or b > y1 + 1:
                    continue
                for off in (-360, 0, 360):                           # 날짜변경선 너머도 이어서 보이게
                    if c_ + off < x0 - 1 or a + off > x1 + 1:
                        continue
                    pts, lx, ly = [], None, None
                    ox = cx + (off - self.lon) * fx
                    oy = cy + self.lat * k
                    for lon, lat in lods[step]:
                        x, y = ox + lon * fx, oy - lat * k
                        if lx is None or abs(x - lx) + abs(y - ly) >= min_px:
                            pts += (x, y)
                            lx, ly = x, y
                    if len(pts) >= 6:
                        self.create_polygon(pts, fill=fill, outline=self.c["coast"])
        draw(self.land, self.c["land"])
        draw(self.holes, self.c["water"])

        # 위도·경도 눈금
        step = 30 if k < 4 else 10 if k < 15 else 5 if k < 40 else 1
        g = math.floor(x0 / step) * step
        while g <= x1:
            x, _ = self.to_xy(g, 0)
            self.create_line(x, 0, x, h, fill=self.c["grid"])
            g += step
        g = math.floor(y0 / step) * step
        while g <= y1:
            _, y = self.to_xy(0, g)
            self.create_line(0, y, w, y, fill=self.c["grid"])
            g += step

        # 점과 글자: 배율에 맞춘 크기, 글자는 겹치면 생략 (고른 공항 → 검색 결과 → 나머지 순서로 자리 차지)
        S = self.s
        def font(px, bold=False):
            return (self.family, -int(round(px * S)), "bold") if bold else (self.family, -int(round(px * S)))
        placed = []
        def label(x, y, text, f, fill, pad=0, gap=0):
            """점 오른쪽 → 왼쪽 → 위 → 아래 순서로 빈 자리를 찾아 글자를 놓고, 없으면 생략."""
            for ax, px, py in (("w", x + gap, y), ("e", x - gap, y), ("s", x, y - gap), ("n", x, y + gap)):
                tid = self.create_text(px, py, text=text, anchor=ax, fill=fill, font=f, tags="lbl")
                x0_, y0_, x1_, y1_ = self.bbox(tid)
                box = (x0_ - pad, y0_ - pad, x1_ + pad, y1_ + pad)
                if not any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
                    placed.append(box)
                    return
                self.delete(tid)
        shown = {a.icao for a in self.marks} | ({self.selected.icao} if self.selected else set())
        sel = self.selected
        if sel:                                                     # 고른 공항 글자 자리를 먼저 잡아 둠
            x, y = self.to_xy(sel.lon, sel.lat)
            r = 9 * S
            label(x, y, f"{sel.icao}  {sel.name}", font(14, True), self.c["text"], pad=S, gap=r + 5 * S)
            placed.append((x - r, y - r, x + r, y + r))
        mk = []
        for a in self.marks:
            x, y = self.to_xy(a.lon, a.lat)
            if a is not sel:
                label(x, y, a.icao, font(12, True), self.c["text"], pad=S, gap=10 * S)
            mk.append((x, y))
        if k >= 18:                                                 # 확대하면 공항 점 (IATA 있는 공항)
            r = 2.5 * S
            for a in self.small:
                if a.icao in shown or not (x0 <= a.lon <= x1 and y0 <= a.lat <= y1):
                    continue
                x, y = self.to_xy(a.lon, a.lat)
                if any(b[0] - r <= x <= b[2] + r and b[1] - r <= y <= b[3] + r for b in placed):
                    continue                                        # 이미 놓인 글자 위의 점은 생략
                self.create_oval(x - r, y - r, x + r, y + r, fill=self.c["dot"], outline="")
                if k >= 60:
                    label(x, y, a.icao, font(11), self.c["muted"], pad=S, gap=6 * S)
        r = 5.5 * S
        for x, y in mk:                                             # 검색 결과 점
            self.create_oval(x - r, y - r, x + r, y + r, fill=self.c["accent"], outline=self.c["land"], width=max(1, int(2 * S)))
        if sel:                                                     # 고른 공항 (공항 표지 노랑)
            x, y = self.to_xy(sel.lon, sel.lat)
            r = 9 * S
            self.create_oval(x - r, y - r, x + r, y + r, fill="#f2c230", outline="#17130a", width=max(1, int(2 * S)))
        self.tag_raise("lbl")                                       # 글자는 항상 점보다 위
        self.create_text(w - 8 * S, h - 6 * S, text="지도: Natural Earth", anchor="se", fill=self.c["muted"], font=font(11))

    def _on_configure(self, _e):
        if self._span and self.winfo_height() > 10:                # 처음 한 번: 지도 높이에 위도 span 도가 들어가게
            self.k = max(self.k, self.winfo_height() / self._span)
            self._span = None
        self.redraw()

    # ---------- 바깥에서 부르는 것 ----------
    def show(self, airport, zoom=None, span=None):
        """공항을 가운데로. span: 지도 높이에 들어갈 위도 폭(도) — 이보다 넓게 보고 있으면 그만큼 확대."""
        self.selected = airport
        self.lon, self.lat = airport.lon, airport.lat
        if zoom:
            self.k = zoom
        if span:
            if self.winfo_height() > 10:
                self.k = max(self.k, self.winfo_height() / span)
            else:
                self._span = span
        self.redraw()

    def set_marks(self, airports):
        self.marks = list(airports)
        if self.marks:
            lons = [a.lon for a in self.marks]
            lats = [a.lat for a in self.marks]
            self.lon, self.lat = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
            span = max(max(lats) - min(lats), (max(lons) - min(lons)) * 0.6, 4)
            self.k = max(2, min(80, self.winfo_height() / (span * 1.6)))
        self.redraw()

    # ---------- 조작 ----------
    def _zoom(self, f, x, y, later=False):
        lon, lat = self.to_lonlat(x, y)
        k0 = self.k
        self.k = max(1.5, min(400, self.k * f))
        nlon, nlat = self.to_lonlat(x, y)                           # 커서 아래 지점이 그대로 있도록
        self.lon += lon - nlon
        self.lat = max(-80, min(80, self.lat + lat - nlat))
        if not later:
            self.redraw()
            return
        # 휠: 지금 그림을 바로 늘리고(빠름), 휠을 멈추면 한 번만 다시 그림
        g = self.k / k0
        self.scale("all", x, y, g, g)
        if self._redraw_job:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(160, self._redraw_now)

    def _redraw_now(self):
        self._redraw_job = None
        self.redraw()

    def _wheel(self, e):
        self._zoom(1.25 if e.delta > 0 else 0.8, e.x, e.y, later=True)

    def _press(self, e):
        self._drag = (e.x, e.y, e.x, e.y, False)

    def _motion(self, e):
        if not self._drag:
            return
        sx, sy, lx, ly, moved = self._drag
        if abs(e.x - sx) + abs(e.y - sy) > 4:
            moved = True
        self.move("all", e.x - lx, e.y - ly)                       # 끄는 동안은 옮기기만, 놓으면 다시 그림
        self._drag = (sx, sy, e.x, e.y, moved)

    def _release(self, e):
        if not self._drag:
            return
        sx, sy, _, _, moved = self._drag
        self._drag = None
        if moved:
            self.lon -= (e.x - sx) / self._fx()
            self.lat = max(-80, min(80, self.lat + (e.y - sy) / self.k))
            self.redraw()
            return
        lon, lat = self.to_lonlat(e.x, e.y)
        a = self.db.nearest(lat, (lon + 540) % 360 - 180, max_km=max(15, 25 * 111 / self.k))
        if a:
            self.on_pick(a)

    def zoom_in(self):
        self._zoom(1.5, self.winfo_width() / 2, self.winfo_height() / 2)

    def zoom_out(self):
        self._zoom(1 / 1.5, self.winfo_width() / 2, self.winfo_height() / 2)
