// Chart.js 공통: 색 · 평균선 플러그인 · y축 확대 · 막대 데이터셋.
import { $, cssVar } from '../lib/dom.js';
import { fmtN, fmtPct } from '../lib/fmt.js';

export const charts = {};

/* ---------- Chart.js 공통 ---------- */
export function themeColors() {
  return {
    arr: cssVar('--series-arr'), dep: cssVar('--series-dep'), avg: cssVar('--series-avg'),
    band: cssVar('--band'), grid: cssVar('--grid'), text: cssVar('--text-secondary'),
    surface: cssVar('--surface'), primary: cssVar('--text-primary'), muted: cssVar('--text-muted')
  };
}

/** 설계 첨두시간 창 음영 + 순위 N 세로선을 그리는 플러그인 */
const overlayPlugin = {
  id: 'overlay',
  beforeDatasetsDraw(chart, _a, o) {
    if (o?.mark) {                       // 강조할 막대 한 개 (예: 첨두일) 뒤 음영
      const { ctx, chartArea: ca, scales: { x } } = chart;
      const w = Math.max(14, x.getPixelForValue(1) - x.getPixelForValue(0)), px = x.getPixelForValue(o.mark.index);
      ctx.save(); ctx.fillStyle = o.mark.band; ctx.fillRect(px - w / 2, ca.top, w, ca.bottom - ca.top); ctx.restore();
    }
    if (!o || o.from == null) return;
    const { ctx, chartArea: ca, scales: { x } } = chart;
    const w = x.getPixelForValue(1) - x.getPixelForValue(0);
    const x0 = Math.max(ca.left, x.getPixelForValue(o.from) - w / 2);
    const x1 = Math.min(ca.right, x.getPixelForValue(o.to) - w / 2);
    ctx.save(); ctx.fillStyle = o.color; ctx.fillRect(x0, ca.top, x1 - x0, ca.bottom - ca.top); ctx.restore();
  },
  afterDatasetsDraw(chart, _a, o) {
    if (o?.mark) {                       // 막대 위 말풍선 라벨
      const { ctx, chartArea: ca, scales: { x, y } } = chart, m = o.mark;
      const px = x.getPixelForValue(m.index), py = y.getPixelForValue(m.value);
      ctx.save(); ctx.font = '700 12px ' + getComputedStyle(document.body).fontFamily;
      const tw = ctx.measureText(m.label).width + 16, th = 22;
      const bx = Math.min(Math.max(px - tw / 2, ca.left), ca.right - tw), by = Math.max(ca.top, py - th - 10);
      ctx.fillStyle = m.bg; ctx.beginPath(); ctx.roundRect(bx, by, tw, th, 6); ctx.fill();
      ctx.beginPath(); ctx.moveTo(px - 5, by + th); ctx.lineTo(px + 5, by + th); ctx.lineTo(px, by + th + 6); ctx.closePath(); ctx.fill();
      ctx.fillStyle = m.ink; ctx.textBaseline = 'middle'; ctx.fillText(m.label, bx + 8, by + th / 2 + 1); ctx.restore();
    }
    if (o?.avg && o.avg.value != null) {   // 평균값: 가로 점선 + 오른쪽 라벨
      const { ctx, chartArea: ca, scales: { y } } = chart, a = o.avg, py = y.getPixelForValue(a.value);
      if (py >= ca.top && py <= ca.bottom) {
        ctx.save();
        if (!a.noLine) { ctx.strokeStyle = a.color; ctx.globalAlpha = .75; ctx.setLineDash([5, 4]); ctx.lineWidth = 1.5;
          ctx.beginPath(); ctx.moveTo(ca.left, py); ctx.lineTo(ca.right, py); ctx.stroke(); ctx.setLineDash([]); ctx.globalAlpha = 1; }
        ctx.font = '700 11.5px ' + getComputedStyle(document.body).fontFamily;
        const tw = ctx.measureText(a.label).width + 12, th = 19, bx = ca.right - tw, by = Math.max(ca.top, py - th - 3);
        ctx.fillStyle = a.bg; ctx.beginPath(); ctx.roundRect(bx, by, tw, th, 5); ctx.fill();
        ctx.strokeStyle = a.color; ctx.lineWidth = 1; ctx.stroke();
        ctx.fillStyle = a.color; ctx.textBaseline = 'middle'; ctx.fillText(a.label, bx + 6, by + th / 2 + 1);
        ctx.restore();
      }
    }
    if (!o || o.vline == null) return;
    const { ctx, chartArea: ca, scales: { x } } = chart;
    const px = x.getPixelForValue(o.vline);
    ctx.save(); ctx.strokeStyle = o.lineColor; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(px, ca.top); ctx.lineTo(px, ca.bottom); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = o.lineColor; ctx.font = '600 11px system-ui';
    ctx.fillText(o.vlabel, Math.min(px + 4, ca.right - 80), ca.top + 12); ctx.restore();
  }
};

/** 차이가 잘 보이도록 y축을 0 대신 최솟값 근처에서 시작 (사용자 요청). 값이 0 가까이까지 내려가면 그대로 0부터 */
function zoomY(o, tots) {
  const v = tots.filter(x => x > 0);
  if (!v.length) return false;
  const lo = Math.min(...v), hi = Math.max(...tots), span = hi - lo;
  let floor = lo - span * 0.35;
  if (floor < hi * 0.15 || span <= 0) return false;
  const step = Math.pow(10, Math.floor(Math.log10(span))) / 2;
  floor = Math.floor(floor / step) * step;
  Object.assign(o.scales.y, { beginAtZero: false, min: floor });
  o.scales.y.title.text = '운항 (편) · 0부터 아님';
  return true;
}

/** y축을 확대하면 쌓은 막대의 아래쪽(도착)이 잘려 색 구분이 안 되므로, 보이는 부분(축 바닥 ~ 합계)을
    도착·출발 비율대로 나눈 떠 있는 막대로 그림 (사용자 요청: 확대해도 도착·출발 색 구분). 툴팁은 실제 값 */
export function zoomStack(o, datasets, arr, dep, canvasId) {
  const tots = arr.map((v, i) => v + dep[i]);
  const legend = $(canvasId)?.closest('[data-ppane]')?.querySelector('.legend');
  if (legend) delete legend.dataset.zoom;
  if (!zoomY(o, tots)) return;
  const fl = o.scales.y.min;
  const cut = i => { const t = tots[i]; return t > fl ? fl + (t - fl) * (t ? arr[i] / t : 0) : fl; };
  for (const d of datasets) {
    if (d.label === '도착') { d.data = tots.map((t, i) => [fl, cut(i)]); d.grouped = false; }
    if (d.label === '출발') { d.data = tots.map((t, i) => [cut(i), Math.max(fl, t)]); d.grouped = false; }
  }
  o.scales.y.stacked = false;
  const real = c => c.dataset.label === '도착' ? arr[c.dataIndex] : c.dataset.label === '출발' ? dep[c.dataIndex] : null;
  const lab = o.plugins.tooltip.callbacks.label;
  o.plugins.tooltip.callbacks.label = c => real(c) != null ? `${c.dataset.label}: ${fmtN(real(c))}편` : lab(c);
  o.plugins.tooltip.callbacks.footer = items => { const it = items.find(x => real(x) != null); return it ? `합계: ${fmtN(tots[it.dataIndex])}편` : ''; };
}

export function baseOptions(tc, extra = {}) {
  return {
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: tc.surface, titleColor: tc.primary, bodyColor: tc.primary, borderColor: tc.grid, borderWidth: 1, padding: 10 },
      ...extra.plugins
    },
    scales: {
      x: { stacked: extra.stacked, grid: { display: false }, ticks: { color: tc.text, maxRotation: 0, autoSkipPadding: 10 } },
      y: { stacked: extra.stacked, beginAtZero: true, grid: { color: tc.grid }, border: { display: false }, ticks: { color: tc.text },
           title: { display: true, text: extra.yTitle || '운항 (편)', color: tc.text } }
    }
  };
}

/** 운항 구성용 가로 막대 (상위 N개, 도착·출발 쌓기 또는 한 값) */
export function hbarChart(id, rows, { labelOf, arrOf, depOf, valOf, total, unitNote = '' }) {
  const tc = themeColors(), box = $(id).parentElement;
  box.style.height = Math.max(160, rows.length * 26 + 50) + 'px';
  const labels = rows.map(labelOf), split = !!arrOf;
  const o = baseOptions(tc, { stacked: true });
  o.indexAxis = 'y';
  Object.assign(o.scales.x, { grid: { color: tc.grid }, ticks: { color: tc.text } });
  Object.assign(o.scales.y, { grid: { display: false }, ticks: { color: tc.primary, autoSkip: false, font: { size: 11.5 } }, title: { display: false } });
  o.scales.x.title = { display: true, text: '운항 (편)', color: tc.text };
  o.plugins.tooltip.callbacks = {
    label: c => `${c.dataset.label}: ${fmtN(c.parsed.x, 0)}편`,
    footer: it => { const i = it[0].dataIndex, v = split ? arrOf(rows[i]) + depOf(rows[i]) : valOf(rows[i]); return `합계: ${v.toLocaleString()}편 · ${fmtPct(v / total)}`; }
  };
  if (split) o.plugins.legend = { display: true, position: 'top', align: 'start', labels: { boxWidth: 10, boxHeight: 10, color: tc.text } };
  const hb = (label, data, color) => ({ type: 'bar', label, data, backgroundColor: color, stack: 's', borderRadius: 3, barPercentage: 0.8, categoryPercentage: 0.9 });
  const datasets = split ? [hb('도착', rows.map(arrOf), tc.arr), hb('출발', rows.map(depOf), tc.dep)] : [hb('운항', rows.map(valOf), tc.arr)];
  mkChart(id, { type: 'bar', data: { labels, datasets }, options: o });
}

export function mkChart(id, config) { charts[id]?.destroy(); charts[id] = new Chart($(id), config); }

export const barDs = (label, data, color, stack = 's') => ({ type: 'bar', label, data, backgroundColor: color, stack, borderRadius: 4, borderSkipped: 'start', borderColor: cssVar('--surface'), borderWidth: { top: 2 }, barPercentage: 0.9, categoryPercentage: 0.9 });

export function init() {
  Chart.register(overlayPlugin);
  Chart.defaults.font.family = '"Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif';   // 차트 글자도 본문 글꼴
  document.addEventListener('click', e => {                // 세부 정보 열기·닫기 (운항 구성 표)
    const b = e.target.closest('.dtoggle'); if (!b) return;
    const d = $(b.getAttribute('aria-controls')), open = d.hidden;
    d.hidden = !open; b.setAttribute('aria-expanded', String(open));
    b.firstElementChild.textContent = open ? '세부 정보 닫기' : '세부 정보';
  });
}
