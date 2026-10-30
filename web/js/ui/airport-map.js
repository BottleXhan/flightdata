// 데이터 탭 공항 지도 (Canvas, mapdata/land50.json): 휠 확대 · 끌기 · 클릭 선택.
import { loadMapData, MAPDATA } from '../data/airports.js';
import { apCode } from '../data/period.js';
import { $, cssVar } from '../lib/dom.js';
import { esc } from '../lib/fmt.js';

/* ---------- 데이터 탭 공항 지도 (수집기 map_canvas 와 같은 방식, Canvas) ----------
   mapdata/land50.json = Natural Earth 50m 육지 (날짜변경선에서 미리 자름). 휠 확대 · 끌기 · 공항 클릭 → 공항 칸에 넣음 */
export const AMAP = { lon: 127, lat: 37, k: 12, land: null, holes: null, pts: null, marks: [], sel: null, drag: null, hover: null, raf: 0, W: 0, H: 0, fitted: false };
let AMAP_LOADING = null;

function loadAmap() {
  if (AMAP_LOADING) return AMAP_LOADING;
  const bbox = p => { let a = 999, b = 999, c = -999, d = -999; for (const [x, y] of p) { if (x < a) a = x; if (x > c) c = x; if (y < b) b = y; if (y > d) d = y; } return [a, b, c, d]; };
  const lod = p => ({ 1: p, 3: p.length > 30 ? p.filter((_, i) => i % 3 === 0) : p, 8: p.length > 80 ? p.filter((_, i) => i % 8 === 0) : p });
  AMAP_LOADING = Promise.all([fetch('mapdata/land50.json').then(r => { if (!r.ok) throw new Error('land50'); return r.json(); }), loadMapData()])
    .then(([d, ok]) => {
      AMAP.land = d.land.map(p => [lod(p), bbox(p)]);
      AMAP.holes = (d.holes || []).map(p => [lod(p), bbox(p)]);
      // 점은 IATA 있는 공항, 글자 자리는 한글 이름 있는 주요 공항이 먼저
      AMAP.pts = ok ? Object.entries(MAPDATA.airports).filter(([, a]) => a[5]).map(([c, a]) => ({ c, a, lon: a[4], lat: a[3], pri: a[9] ? 0 : 1 })).sort((x, y) => x.pri - y.pri) : [];
      return true;
    })
    .catch(e => { console.warn('지도 자료', e); $('amapNote').textContent = '지도 자료를 불러오지 못했습니다 (mapdata 폴더 확인).'; return false; });
  return AMAP_LOADING;
}

const amapFx = () => AMAP.k * Math.max(0.2, Math.cos(AMAP.lat * Math.PI / 180));

function amapXY(lon, lat) {
  const dlon = ((lon - AMAP.lon + 540) % 360) - 180;
  return [AMAP.W / 2 + dlon * amapFx(), AMAP.H / 2 - (lat - AMAP.lat) * AMAP.k];
}

const amapLL = (x, y) => [AMAP.lon + (x - AMAP.W / 2) / amapFx(), AMAP.lat - (y - AMAP.H / 2) / AMAP.k];

export function amapDraw() {
  if (AMAP.raf) return;
  AMAP.raf = requestAnimationFrame(() => { AMAP.raf = 0; amapRender(); });
}

function amapRender() {
  const cv = $('amapCv'), box = $('amap');
  if (!AMAP.land || !box.offsetWidth || !box.offsetHeight) return;
  const W = box.clientWidth, H = box.clientHeight, dpr = devicePixelRatio || 1;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  AMAP.W = W; AMAP.H = H;
  if (!AMAP.fitted) { AMAP.fitted = true; AMAP.k = Math.max(AMAP.k, H / 5.2); }   // 처음: 한반도가 지도 높이에 꽉 차는 정도 (수집기와 같게)
  const g = cv.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const C = { water: cssVar('--map-water'), land: cssVar('--map-land'), coast: cssVar('--map-coast'), grid: cssVar('--map-grid'),
              text: cssVar('--text-primary'), muted: cssVar('--text-muted'), accent: cssVar('--accent'), font: getComputedStyle(document.body).fontFamily };
  g.fillStyle = C.water; g.fillRect(0, 0, W, H);
  const fx = amapFx(), k = AMAP.k;
  const [x0, y1] = amapLL(0, 0), [x1, y0] = amapLL(W, H);
  const step = k > 12 ? 1 : k > 4 ? 3 : 8;
  const draw = (polys, fill) => {
    g.fillStyle = fill; g.strokeStyle = C.coast; g.lineWidth = 1;
    for (const [lods, [a, b, c, d]] of polys) {
      if (d < y0 - 1 || b > y1 + 1) continue;
      for (const off of [-360, 0, 360]) {
        // 가운데 경도 근처로 감아 둔 화면 좌표 (날짜변경선 너머도 이어서 보이게)
        const base = Math.round(AMAP.lon / 360) * 360 + off;
        if (c + base < x0 - 1 || a + base > x1 + 1) continue;
        const ox = W / 2 + (base - AMAP.lon) * fx, oy = H / 2 + AMAP.lat * k;
        g.beginPath(); let n = 0, lx = null, ly = null;
        for (const [lon, lat] of lods[step]) {
          const x = ox + lon * fx, y = oy - lat * k;
          if (lx === null || Math.abs(x - lx) + Math.abs(y - ly) >= 1.2) { n ? g.lineTo(x, y) : g.moveTo(x, y); n++; lx = x; ly = y; }
        }
        if (n >= 3) { g.closePath(); g.fill(); g.stroke(); }
      }
    }
  };
  draw(AMAP.land, C.land); draw(AMAP.holes, C.water);
  // 위도·경도 눈금
  const gs = k < 4 ? 30 : k < 15 ? 10 : k < 40 ? 5 : 1;
  g.strokeStyle = C.grid; g.beginPath();
  for (let v = Math.floor(x0 / gs) * gs; v <= x1; v += gs) { const x = W / 2 + (v - AMAP.lon) * fx; g.moveTo(x, 0); g.lineTo(x, H); }
  for (let v = Math.floor(y0 / gs) * gs; v <= y1; v += gs) { const y = H / 2 - (v - AMAP.lat) * k; g.moveTo(0, y); g.lineTo(W, y); }
  g.stroke();
  // 글자: 점 오른쪽 → 왼쪽 → 위 → 아래 빈 자리, 없으면 생략 (고른 공항 → 검색 결과 → 주요 공항 순서로 자리 차지)
  const placed = [];
  const hit = bx => placed.some(p => !(bx[2] < p[0] || bx[0] > p[2] || bx[3] < p[1] || bx[1] > p[3]));
  const label = (x, y, text, font, fill, gap) => {
    g.font = font; const w = g.measureText(text).width, h = parseFloat(font.match(/(\d+(\.\d+)?)px/)[1]);
    for (const [lx, ly] of [[x + gap, y - h / 2], [x - gap - w, y - h / 2], [x - w / 2, y - gap - h], [x - w / 2, y + gap]]) {
      const bx = [lx - 2, ly - 1, lx + w + 2, ly + h + 1];
      if (hit(bx)) continue;
      placed.push(bx);
      g.fillStyle = C.water; g.globalAlpha = .55; g.fillRect(bx[0], bx[1], bx[2] - bx[0], bx[3] - bx[1]); g.globalAlpha = 1;   // 해안선 위에서도 읽히게
      g.fillStyle = fill; g.textBaseline = 'top'; g.fillText(text, lx, ly); return true;
    }
    return false;
  };
  const sel = AMAP.sel && MAPDATA?.airports[AMAP.sel];
  if (sel) {
    const [x, y] = amapXY(sel[4], sel[3]);
    placed.push([x - 9, y - 9, x + 9, y + 9]);
    label(x, y, `${AMAP.sel}  ${sel[9] || sel[0]}`, `700 14px ${C.font}`, C.text, 14);
  }
  const mk = AMAP.marks.filter(c => c !== AMAP.sel && MAPDATA?.airports[c]).map(c => { const a = MAPDATA.airports[c]; const [x, y] = amapXY(a[4], a[3]); return [c, x, y]; });
  for (const [c, x, y] of mk) { placed.push([x - 6, y - 6, x + 6, y + 6]); }
  for (const [c, x, y] of mk) label(x, y, c, `700 12px ${C.font}`, C.text, 9);
  if (k >= 6) {                                          // 확대하면 공항 점
    const r = k >= 40 ? 2.6 : k >= 15 ? 2 : 1.4;
    g.fillStyle = C.muted;
    for (const p of AMAP.pts) {
      if (p.c === AMAP.sel || AMAP.marks.includes(p.c)) continue;
      const [x, y] = amapXY(p.lon, p.lat);
      if (x < -5 || y < -5 || x > W + 5 || y > H + 5) continue;
      g.globalAlpha = k >= 15 ? .9 : .55;
      g.beginPath(); g.arc(x, y, r, 0, 7); g.fill();
      if (k >= 40 && (p.pri === 0 || k >= 80)) { g.globalAlpha = 1; label(x, y, p.c, `500 11px ${C.font}`, C.muted, 6); g.fillStyle = C.muted; }
    }
    g.globalAlpha = 1;
  }
  for (const [, x, y] of mk) { g.beginPath(); g.arc(x, y, 5.5, 0, 7); g.fillStyle = C.accent; g.fill(); g.lineWidth = 2; g.strokeStyle = C.land; g.stroke(); }
  if (sel) {
    const [x, y] = amapXY(sel[4], sel[3]);
    g.beginPath(); g.arc(x, y, 8, 0, 7); g.fillStyle = '#f2c230'; g.fill(); g.lineWidth = 2; g.strokeStyle = '#17130a'; g.stroke();
  }
}

/** 지도 열기·닫기 (auto = 검색 때문에 저절로 열림) */
export function amapOpen(open, auto = false) {
  // 지도는 데이터 카드 안의 "지도에서 공항 찾기" 화면으로 — 공항·기간 칸 대신 지도가 카드 전체를 채움 (사용자 요청: 한 화면에)
  $('dvCard').dataset.mode = open ? 'map' : 'form';
  document.querySelectorAll('[data-dvmode]').forEach(b => b.setAttribute('aria-selected', String((b.dataset.dvmode === 'map') === open)));
  $('amapBox').hidden = !open; AMAP.auto = open && auto;
  $('amapToggle').setAttribute('aria-expanded', String(open));
  const srch = document.querySelector('.apsearch');            // 공항 찾기 칸을 지도 위로 옮겨 씀
  if (open) $('amapSearchSlot').appendChild(srch); else $('apSlotHome').after(srch);
  if (open) { window.scrollTo({ top: 0 }); $('apSearch').focus(); }
  if (open) { AMAP.W = $('amap').clientWidth; AMAP.H = $('amap').clientHeight; AMAP.fitted = false; amapSelect(apCode(), !auto); }
}

/** 화면 좌표에서 가장 가까운 공항 (r 픽셀 안) */
function amapNearest(x, y, r = 14) {
  let best = null, bd = r * r;
  const cand = [...AMAP.marks, AMAP.sel].filter(Boolean).map(c => ({ c, a: MAPDATA.airports[c] })).filter(p => p.a).map(p => ({ ...p, lon: p.a[4], lat: p.a[3] }));
  for (const p of cand.concat(AMAP.k >= 6 ? AMAP.pts : [])) {
    const [px, py] = amapXY(p.lon, p.lat), d = (px - x) ** 2 + (py - y) ** 2;
    if (d < bd) { bd = d; best = p.c; }
  }
  return best;
}

function amapZoom(f, x = AMAP.W / 2, y = AMAP.H / 2) {
  const [lo, la] = amapLL(x, y);
  AMAP.k = Math.min(600, Math.max(1.2, AMAP.k * f));
  AMAP.lat = Math.max(-75, Math.min(80, la + (y - AMAP.H / 2) / AMAP.k));
  AMAP.lon = lo - (x - AMAP.W / 2) / amapFx();
  amapDraw();
}

/** 공항을 고름 (공항 칸 · CSV 에서 바뀐 경우) — 지도 밖이면 가운데로 */
export async function amapSelect(code, center = false) {
  if (!(await loadAmap())) return;
  const a = MAPDATA.airports[code];
  AMAP.sel = a ? code : null;
  $('amapSel').textContent = a ? `${code}${a[5] ? ' / ' + a[5] : ''} · ${a[9] || a[0]}${a[1] ? ' · ' + a[1] : ''}` : '–';
  if (a) {
    const [x, y] = amapXY(a[4], a[3]);
    if (center || !AMAP.W || x < 40 || y < 40 || x > AMAP.W - 40 || y > AMAP.H - 40) { AMAP.lon = a[4]; AMAP.lat = a[3]; if (AMAP.H) AMAP.k = Math.max(AMAP.k, AMAP.H / 5.2); }
  }
  amapDraw();
}

/** 검색 결과를 지도에 표시하고 한눈에 들어오게 맞춤 */
export async function amapMarks(codes) {
  if (!(await loadAmap())) return;
  AMAP.marks = codes.filter(c => MAPDATA.airports[c]);
  if (AMAP.marks.length && AMAP.H) {
    const ll = AMAP.marks.map(c => MAPDATA.airports[c]), lons = ll.map(a => a[4]), lats = ll.map(a => a[3]);
    AMAP.lon = (Math.min(...lons) + Math.max(...lons)) / 2; AMAP.lat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const span = Math.max(Math.max(...lats) - Math.min(...lats), (Math.max(...lons) - Math.min(...lons)) * 0.6, 4);
    AMAP.k = Math.max(2, Math.min(80, AMAP.H / (span * 1.6)));
    AMAP.fitted = true;
  }
  amapDraw();
}

export function init() {
  (() => {
    const cv = $('amapCv'), tip = $('amapTip');
    const pos = e => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    cv.addEventListener('wheel', e => { e.preventDefault(); const [x, y] = pos(e); amapZoom(e.deltaY < 0 ? 1.25 : 0.8, x, y); }, { passive: false });
    cv.addEventListener('pointerdown', e => { const [x, y] = pos(e); AMAP.drag = { x, y, x0: x, y0: y, moved: false }; cv.setPointerCapture(e.pointerId); });
    cv.addEventListener('pointermove', e => {
      const [x, y] = pos(e), d = AMAP.drag;
      if (d) {
        if (Math.abs(x - d.x0) + Math.abs(y - d.y0) > 4) { d.moved = true; cv.classList.add('drag'); }
        if (d.moved) {
          AMAP.lon -= (x - d.x) / amapFx(); AMAP.lat = Math.max(-75, Math.min(80, AMAP.lat + (y - d.y) / AMAP.k));
          AMAP.lon = ((AMAP.lon + 540) % 360) - 180;
          d.x = x; d.y = y; tip.hidden = true; amapDraw(); return;
        }
      }
      if (!AMAP.pts) return;
      const c = amapNearest(x, y, 10), a = c && MAPDATA.airports[c];
      cv.style.cursor = c ? 'pointer' : '';
      if (!a) { tip.hidden = true; return; }
      tip.innerHTML = `<b>${esc(c)}</b>${a[5] ? esc(a[5]) + ' · ' : ''}${esc(a[9] || a[0])} <span class="muted">${esc([a[1], a[2]].filter(Boolean).join(', '))}</span>`;
      tip.hidden = false;
      tip.style.left = Math.min(x + 14, AMAP.W - tip.offsetWidth - 6) + 'px'; tip.style.top = Math.max(6, y - 34) + 'px';
    });
    cv.addEventListener('pointerleave', () => { tip.hidden = true; });
    cv.addEventListener('pointerup', e => {
      const d = AMAP.drag; AMAP.drag = null; cv.classList.remove('drag');
      if (!d || d.moved || !AMAP.pts) return;
      const [x, y] = pos(e), c = amapNearest(x, y);
      if (!c) return;
      $('icao').value = c; AMAP.marks = [];
      $('icao').dispatchEvent(new Event('input')); $('icao').dispatchEvent(new Event('change'));
    });
    $('amapIn').onclick = () => amapZoom(1.6);
    $('amapOut').onclick = () => amapZoom(1 / 1.6);
    $('amapHome').onclick = () => amapSelect(apCode() || AMAP.sel, true);
    $('amapToggle').onclick = () => amapOpen(true);
    document.querySelectorAll('[data-dvmode]').forEach(b => { b.onclick = () => amapOpen(b.dataset.dvmode === 'map'); });
    $('amapClose').onclick = () => amapOpen(false);
    new ResizeObserver(amapDraw).observe($('amap'));
    loadAmap().then(ok => ok && amapSelect(apCode(), true));
  })();
}
