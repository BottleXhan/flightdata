// 필터 (운항량·운항 구성 공용): 방향 · 노선(국내/국제/나라) · 항공사 · 기종 크기 · 시간대.
import { countryOf, regionName } from './data/airports.js';
import { alCode, sizeOf } from './engine/classify.js';
import { $, showMsg } from './lib/dom.js';
import { DAY, esc, HOUR, pad } from './lib/fmt.js';
import { renderAll } from './run.js';
import { STATE } from './state.js';
import { airlineMark, airlineName } from './ui/badges.js';
import { saveLast } from './ui/session.js';

const FILTER = { airlines: new Set() };

/** 지금 고른 필터로 운항을 거른다. ctx: 공항(국내/국제 판단)·UTC(시간대 판단) */
export function applyFilters(mv, ctx = STATE.data) {
  const dir = $('fDir').value, route = $('fRoute').value, size = $('fSize').value;
  const h0 = +$('fH0').value, h1 = +$('fH1').value, allDay = h0 === 0 && h1 === 24;
  const home = countryOf(ctx.airport), al = FILTER.airlines, off = (ctx.offsetH || 0) * HOUR;
  return mv.filter(m => {
    if (dir !== 'all' && m.type !== dir) return false;
    if (route !== 'all') {
      const c = countryOf(m.other);
      if (route === 'dom' ? c !== home || !c : route === 'intl' ? c === home || !c : c !== route.slice(3)) return false;
    }
    if (al.size && !al.has(alCode(m))) return false;
    if (size !== 'all' && sizeOf(m) !== size) return false;
    if (!allDay) {
      const h = Math.floor((((m.t + off) % DAY) + DAY) % DAY / HOUR);
      if (h0 < h1 ? (h < h0 || h >= h1) : (h < h0 && h >= h1)) return false;   // 23시~06시처럼 자정을 넘기는 범위도
    }
    return true;
  });
}

/** 데이터를 불러오면 노선(나라)·항공사 목록을 그 데이터로 채움 */
export function buildFilterOptions() {
  const mv = STATE.data.movements, home = countryOf(STATE.data.airport);
  const nat = new Map(), al = new Map();
  for (const m of mv) {
    const c = countryOf(m.other); if (c) nat.set(c, (nat.get(c) || 0) + 1);
    const k = alCode(m), a = al.get(k) || { n: 0, names: new Map() };
    a.n++; if (m.operator) a.names.set(m.operator, (a.names.get(m.operator) || 0) + 1); al.set(k, a);
  }
  const cur = $('fRoute').value;
  $('fRoute').innerHTML = '<option value="all">전체 노선</option><option value="dom">국내선</option><option value="intl">국제선</option>' +
    '<optgroup label="나라별">' + [...nat].filter(([c]) => c !== home).sort((a, b) => b[1] - a[1])
      .map(([c, n]) => `<option value="cc:${esc(c)}">${esc(regionName(c))} (${n.toLocaleString()})</option>`).join('') + '</optgroup>';
  $('fRoute').value = [...$('fRoute').options].some(o => o.value === cur) ? cur : 'all';
  STATE.fAirlines = [...al].sort((a, b) => b[1].n - a[1].n).map(([code, a]) => ({ code, n: a.n, name: airlineName(code, [...a.names].sort((x, y) => y[1] - x[1])[0]?.[0] || '') }));
  for (const c of [...FILTER.airlines]) if (!al.has(c)) FILTER.airlines.delete(c);
  $('fSize').querySelectorAll('option').forEach(o => { if (o.value !== 'all') o.disabled = !mv.some(m => m.typecode) && o.value !== 'U'; });
  renderAlList(); syncFilterUI();
}

function renderAlList() {
  const q = $('fAlSearch').value.trim().toLowerCase(), list = (STATE.fAirlines || []).filter(a => !q || a.code.toLowerCase().includes(q) || a.name.toLowerCase().includes(q));
  $('fAlList').innerHTML = list.slice(0, 200).map(a => `<label><input type="checkbox" value="${esc(a.code)}"${FILTER.airlines.has(a.code) ? ' checked' : ''}><b>${esc(a.code)}</b><span>${airlineMark(a.code)}${esc(a.name)}</span><em>${a.n.toLocaleString()}</em></label>`).join('') ||
    '<p class="text-xs muted" style="padding:.4rem">맞는 항공사가 없습니다</p>';
}

/** 사이드바 버튼 글자·초기화 버튼·결과 위 칩을 지금 필터에 맞춤 */
export function syncFilterUI() {
  const al = [...FILTER.airlines];
  $('fAlBtn').firstChild.textContent = al.length ? (al.length <= 3 ? al.join(', ') : `${al.slice(0, 2).join(', ')} 외 ${al.length - 2}곳`) : '전체 항공사';
  const chips = [];
  const txt = id => $(id).selectedOptions[0].text.replace(/ \([\d,]+\)$/, '');
  if ($('fDir').value !== 'all') chips.push(['fDir', txt('fDir')]);
  if ($('fRoute').value !== 'all') chips.push(['fRoute', txt('fRoute')]);
  if (al.length) chips.push(['fAl', '항공사 ' + $('fAlBtn').firstChild.textContent]);
  if ($('fSize').value !== 'all') chips.push(['fSize', '기종 ' + txt('fSize')]);
  if (!($('fH0').value === '0' && $('fH1').value === '24')) chips.push(['fH', `${pad(+$('fH0').value)}~${pad(+$('fH1').value)}시`]);
  $('fChips').innerHTML = chips.map(([k, t]) => `<button type="button" data-f="${k}" title="이 필터 해제">${esc(t)} ✕</button>`).join('');
  $('fChips').hidden = !chips.length;
  $('fReset').hidden = !chips.length;
}

export function clearFilter(k) {
  if (k === 'fAl') FILTER.airlines.clear();
  else if (k === 'fH') { $('fH0').value = '0'; $('fH1').value = '24'; }
  else $(k).value = 'all';
}

function filtersChanged() { syncFilterUI(); saveLast(); if (STATE.data) renderAll(); }

const closeAl = () => { if ($('fAlPop').hidden) return; $('fAlPop').hidden = true; $('fAlBtn').setAttribute('aria-expanded', 'false'); filtersChanged(); };

export function init() {
  // 필터 이벤트
  $('fH1').value = '24';
  ['fDir', 'fRoute', 'fSize', 'fH0', 'fH1'].forEach(id => $(id).addEventListener('change', filtersChanged));
  $('fReset').onclick = () => { ['fDir', 'fRoute', 'fSize', 'fAl', 'fH'].forEach(clearFilter); filtersChanged(); };
  $('fChips').onclick = e => { const b = e.target.closest('[data-f]'); if (b) { clearFilter(b.dataset.f); filtersChanged(); } };
  $('fAlBtn').onclick = () => {
    if (!$('fAlPop').hidden) return closeAl();
    if (!STATE.fAirlines) { showMsg('항공사 목록은 데이터를 불러온 뒤에 고를 수 있습니다.'); return; }
    $('fAlSearch').value = ''; renderAlList();
    $('fAlPop').hidden = false; $('fAlBtn').setAttribute('aria-expanded', 'true'); $('fAlSearch').focus();
  };
  $('fAlSearch').oninput = renderAlList;
  $('fAlList').onchange = e => { const c = e.target.value; e.target.checked ? FILTER.airlines.add(c) : FILTER.airlines.delete(c); syncFilterUI(); };
  $('fAlNone').onclick = () => { FILTER.airlines.clear(); renderAlList(); syncFilterUI(); };
  $('fAlDone').onclick = closeAl;
  document.addEventListener('click', e => { if (!$('fAlPop').hidden && !e.target.closest('.fal')) closeAl(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('fAlPop').hidden) { closeAl(); $('fAlBtn').focus(); } });
}
