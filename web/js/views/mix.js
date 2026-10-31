// 운항 구성: 노선(지도) · 항공사 · 기종.
import { loadMapData, MAPDATA, regionName } from '../data/airports.js';
import { $, cssVar } from '../lib/dom.js';
import { esc, fmtPct, HOUR } from '../lib/fmt.js';
import { STATE } from '../state.js';
import { airlineMark, airlineName, airlineOf, apFlag, flag, flagSrc, logoSrc } from '../ui/badges.js';
import { hbarChart } from '../ui/charts.js';
import { PANE, setPane } from '../ui/nav.js';
import { renderAirportCard } from './overview.js';
import { cfgFromUI } from './peak.js';

/* ---------- 기종별 운항 (CSV 에 OpenSky aircraft database 기종 정보가 있을 때) ---------- */
function typeSummary(res, sel) {
  const mv = STATE.view.movements;
  const withType = mv.filter(m => m.typecode);
  const inWin = m => sel.start != null && m.t + STATE.data.offsetH * HOUR >= sel.start && m.t + STATE.data.offsetH * HOUR < sel.start + sel.len;
  const by = new Map();
  for (const m of withType) {
    const e = by.get(m.typecode) || { code: m.typecode, n: 0, inPeak: 0, models: new Map() };
    e.n++; if (inWin(m)) e.inPeak++;
    if (m.model) e.models.set(m.model, (e.models.get(m.model) || 0) + 1);
    by.set(m.typecode, e);
  }
  const rows = [...by.values()].sort((a, b) => b.n - a.n).map(e => ({
    code: e.code, n: e.n, share: e.n / mv.length, inPeak: sel.start != null ? e.inPeak : null,
    model: [...e.models.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || ''
  }));
  return { rows, coverage: mv.length ? withType.length / mv.length : 0, total: mv.length };
}

export function renderTypes(res, sel) {
  const t = typeSummary(res, sel);
  if (!t.rows.length) {
    $('typeNote').innerHTML = '이 데이터에는 기종 정보가 없습니다. 최신 <code>fetch_flights.py</code>로 다시 받으면 OpenSky 항공기 데이터베이스에서 기종·운항사를 붙여 줍니다 (이미 받은 날짜는 다시 조회하지 않음).';
    $('typeTable').innerHTML = '';
    $('typeChartWrap').hidden = true;
    return;
  }
  $('typeChartWrap').hidden = false;
  const tops = t.rows.slice(0, 15);
  $('typeChartTitle').textContent = `운항이 많은 기종 상위 ${tops.length}개 (전체 ${t.rows.length.toLocaleString()}개)`;
  hbarChart('typeChart', tops, { labelOf: r => r.model ? `${r.code} ${r.model.length > 16 ? r.model.slice(0, 15) + '…' : r.model}` : r.code, valOf: r => r.n, total: t.total });
  $('typeNote').textContent = `기종 확인 ${fmtPct(t.coverage)} (${(t.coverage * t.total).toLocaleString()} / ${t.total.toLocaleString()}편) · 출처: OpenSky aircraft database (icao24 기준 연결, 등록 정보라 실제 운항 기종과 다를 수 있음)`;
  const top = t.rows.slice(0, 20);
  $('typeTable').innerHTML = '<thead><tr><th>기종 코드</th><th>모델</th><th class="num">운항</th><th class="num">비율</th><th style="width:30%"></th></tr></thead><tbody>' +
    top.map(r => `<tr><td><b style="font-family:var(--font-data)">${esc(r.code)}</b></td><td class="secondary">${esc(r.model)}</td><td class="num">${r.n.toLocaleString()}</td><td class="num">${fmtPct(r.share)}</td>
      <td><div style="height:8px;border-radius:4px;background:var(--accent);width:${(r.n / t.rows[0].n * 100).toFixed(1)}%"></div></td></tr>`).join('') +
    (t.rows.length > 20 ? `<tr><td colspan="5" class="muted">외 ${t.rows.length - 20}개 기종</td></tr>` : '') + '</tbody>';
}

export function airlineRouteSummary() {
  const mv = STATE.view.movements, al = new Map(), rt = new Map();
  for (const m of mv) {
    const code = /^[A-Z]{3}\d/.test(m.callsign || '') ? m.callsign.slice(0, 3) : '기타';
    const a = al.get(code) || { code, n: 0, arr: 0, dep: 0, names: new Map() };
    a.n++; m.type === 'A' ? a.arr++ : a.dep++;
    if (m.operator) a.names.set(m.operator, (a.names.get(m.operator) || 0) + 1);
    al.set(code, a);
    const ap = m.other || '미상';
    const r = rt.get(ap) || { ap, n: 0, from: 0, to: 0 };
    r.n++; m.type === 'A' ? r.from++ : r.to++;
    rt.set(ap, r);
  }
  const name = a => [...a.names.entries()].sort((x, y) => y[1] - x[1])[0]?.[0] || '';
  return {
    total: mv.length,
    airlines: [...al.values()].sort((a, b) => b.n - a.n).map(a => ({ ...a, name: airlineName(a.code, name(a)), cc: airlineOf(a.code)?.[2] || '' })),
    routes: [...rt.values()].filter(r => r.ap !== '미상').sort((a, b) => b.n - a.n)   // 상대 공항을 모르는 운항(미상)은 노선에서 뺌 (사용자 요청)
  };
}

export function renderAirlinesRoutes() {
  const S = STATE.alrt = airlineRouteSummary(), TOP = 50;
  const bar = (v, max) => `<div style="height:8px;border-radius:4px;background:var(--accent);width:${max ? (v / max * 100).toFixed(1) : 0}%"></div>`;
  const amax = S.airlines[0]?.n, rmax = S.routes[0]?.n;
  $('alNote').textContent = `${S.airlines.length.toLocaleString()}개 항공사 코드 · 항공사 이름·나라: OpenFlights (없으면 항공기 데이터베이스의 운영사) · 로고: pics.avs.io · "기타" = 항공사 형식이 아닌 편명`;
  $('alTable').innerHTML = '<thead><tr><th class="num">순위</th><th></th><th>코드</th><th>항공사</th><th>나라</th><th class="num">운항</th><th style="width:18%"></th><th class="num">비율</th><th class="num">도착</th><th class="num">출발</th></tr></thead><tbody>' +
    S.airlines.slice(0, TOP).map((a, i) => `<tr><td class="num">${i + 1}</td><td class="mark">${airlineMark(a.code)}</td><td><b style="font-family:var(--font-data)">${esc(a.code)}</b></td><td class="secondary">${esc(a.name)}</td>
      <td class="secondary" style="white-space:nowrap">${a.cc ? flag(a.cc) + esc(regionName(a.cc)) : ''}</td>
      <td class="num"><b>${a.n.toLocaleString()}</b></td><td>${bar(a.n, amax)}</td><td class="num">${fmtPct(a.n / S.total)}</td><td class="num">${a.arr.toLocaleString()}</td><td class="num">${a.dep.toLocaleString()}</td></tr>`).join('') +
    (S.airlines.length > TOP ? `<tr><td colspan="10" class="muted">외 ${S.airlines.length - TOP}개</td></tr>` : '') + '</tbody>';
  $('rtNote').textContent = `${S.routes.length.toLocaleString()}개 공항 · 지도의 선 굵기 = 운항 수`;
  const apName = c => { const a = MAPDATA?.airports?.[c]; return a ? `${a[0]}${a[1] ? ' · ' + a[1] : ''}` : ''; };
  $('rtTable').innerHTML = '<thead><tr><th class="num">순위</th><th>공항</th><th class="num">운항</th><th style="width:18%"></th><th class="num">비율</th><th class="num">에서 도착</th><th class="num">으로 출발</th></tr></thead><tbody>' +
    S.routes.slice(0, TOP).map((r, i) => `<tr data-rt="${esc(r.ap)}"><td class="num">${i + 1}</td><td>${apFlag(r.ap)}<b>${esc(r.ap)}</b> <span class="text-xs muted">${esc(apName(r.ap))}</span></td>
      <td class="num"><b>${r.n.toLocaleString()}</b></td><td>${bar(r.n, rmax)}</td><td class="num">${fmtPct(r.n / S.total)}</td><td class="num">${r.from.toLocaleString()}</td><td class="num">${r.to.toLocaleString()}</td></tr>`).join('') +
    (S.routes.length > TOP ? `<tr><td colspan="7" class="muted">외 ${S.routes.length - TOP}개</td></tr>` : '') + '</tbody>';
  // 그래프: 상위 15개 (도착·출발 쌓기)
  const CT = 15, shortAp = c => { const a = MAPDATA?.airports?.[c]; return a ? (a[9] || a[1] || a[0]).split(' ')[0] : ''; };
  const rts = S.routes.filter(r => r.ap !== '미상').slice(0, CT);
  $('rtChartTitle').textContent = `운항이 많은 노선 상위 ${rts.length}곳 (전체 ${S.routes.length.toLocaleString()}곳) · 도착 = 그 공항에서 옴, 출발 = 그 공항으로 감`;
  hbarChart('rtChart', rts, { labelOf: r => `${r.ap} ${shortAp(r.ap)}`.trim(), arrOf: r => r.from, depOf: r => r.to, total: S.total,
    iconOf: r => ({ flag: flagSrc(MAPDATA?.airports?.[r.ap]?.[2]) }) });
  const als = S.airlines.slice(0, CT);
  $('alChartTitle').textContent = `운항이 많은 항공사 상위 ${als.length}곳 (전체 ${S.airlines.length.toLocaleString()}곳)`;
  hbarChart('alChart', als, { labelOf: a => a.name ? `${a.code} ${a.name.length > 14 ? a.name.slice(0, 13) + '…' : a.name}` : a.code, arrOf: a => a.arr, depOf: a => a.dep, total: S.total,
    iconOf: a => ({ logo: logoSrc(a.code), flag: flagSrc(a.cc) }) });
  if (!MAPDATA) loadMapData().then(ok => ok && renderAirlinesRoutes());   // 지도·공항명 자료를 받은 뒤 다시 그림
  else { renderRouteMap(S); renderAirportCard(S); }
}

function renderRouteMap(S) {
  if (!window.d3 || !MAPDATA) return;
  const el = $('rtMap'), W = el.clientWidth || 700, H = el.clientHeight || 500, A = MAPDATA.airports;
  const origin = A[STATE.data.airport];
  $('sumApName').textContent = origin ? `${origin[0]} · ${[origin[1], origin[2]].filter(Boolean).join(', ')}` : '';
  const routes = S.routes.filter(r => A[r.ap]).map(r => ({ ...r, a: A[r.ap] }));
  const missing = S.routes.filter(r => !A[r.ap]).reduce((s, r) => s + r.n, 0);
  $('rtMapNote').textContent = '';
  el.innerHTML = '';
  if (!origin) { $('rtMapNote').textContent = `${STATE.data.airport} 의 위치를 몰라 지도를 그리지 못했습니다.`; return; }
  const O = [origin[4], origin[3]], pts = routes.map(r => [r.a[4], r.a[3]]);
  // 분석 공항의 경도를 가운데로 돌려, 태평양을 건너는 노선도 끊기지 않게
  const proj = d3.geoNaturalEarth1().rotate([-O[0], 0]).fitExtent([[50, 30], [W - 70, H - 30]], { type: 'MultiPoint', coordinates: [O, ...pts] });
  if (proj.scale() > 1600) { proj.scale(1600); const [cx, cy] = proj(O), t = proj.translate(); proj.translate([t[0] + W / 2 - cx, t[1] + H / 2 - cy]); }   // 가까운 노선만 있으면 너무 크게 확대하지 않음
  const path = d3.geoPath(proj), css = cssVar;
  const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`);
  const g = svg.append('g');
  g.append('path').datum(d3.geoGraticule10()).attr('d', path).attr('fill', 'none').attr('stroke', css('--map-grid'));
  g.append('path').datum(MAPDATA.land).attr('d', path).attr('fill', css('--map-land')).attr('stroke', css('--map-grid'));
  const max = d3.max(routes, r => r.n) || 1, wS = d3.scaleSqrt().domain([0, max]).range([0.6, 7]), rS = d3.scaleSqrt().domain([0, max]).range([2, 9]);
  const tip = $('rtTip');
  const show = (ev, r) => {
    const box = el.getBoundingClientRect();
    tip.innerHTML = `${flag(r.a[2])}<b>${esc(r.ap)}</b> ${esc(r.a[0])}<br><span class="muted">${esc([r.a[1], r.a[2]].filter(Boolean).join(', '))}</span><br>` +
      `<b>${r.n.toLocaleString()}편</b> · ${fmtPct(r.n / S.total)}<br>이 공항에서 도착 ${r.from.toLocaleString()} · 이 공항으로 출발 ${r.to.toLocaleString()}`;
    tip.hidden = false;
    tip.style.left = Math.min(ev.clientX - box.left + 12, box.width - 290) + 'px';
    tip.style.top = (ev.clientY - box.top + 12) + 'px';
  };
  const hide = () => { tip.hidden = true; };
  const sorted = [...routes].sort((a, b) => a.n - b.n);                  // 굵은 선이 위로
  g.append('g').selectAll('path').data(sorted).join('path')
    .attr('d', r => path({ type: 'LineString', coordinates: [O, [r.a[4], r.a[3]]] }))
    .attr('fill', 'none').attr('stroke', css('--accent')).attr('stroke-opacity', 0.55).attr('stroke-linecap', 'round')
    .attr('stroke-width', r => wS(r.n)).attr('vector-effect', 'non-scaling-stroke')
    .on('mousemove', show).on('mouseleave', hide);
  const dots = g.append('g').selectAll('circle').data(sorted).join('circle')
    .attr('cx', r => proj([r.a[4], r.a[3]])[0]).attr('cy', r => proj([r.a[4], r.a[3]])[1]).attr('r', r => rS(r.n))
    .attr('fill', css('--accent')).attr('stroke', css('--surface')).attr('stroke-width', 1).attr('vector-effect', 'non-scaling-stroke')
    .on('mousemove', show).on('mouseleave', hide);
  const top = [...routes].sort((a, b) => b.n - a.n).slice(0, 12);
  const labels = g.append('g').selectAll('text').data(top).join('text')
    .attr('x', r => proj([r.a[4], r.a[3]])[0] + rS(r.n) + 3).attr('y', r => proj([r.a[4], r.a[3]])[1] + 4)
    .text(r => r.ap).attr('font-size', 11).attr('font-weight', 600).attr('fill', css('--text-secondary'))
    .attr('paint-order', 'stroke').attr('stroke', css('--map-land')).attr('stroke-width', 3);
  const [ox, oy] = proj(O);
  const og = g.append('g');
  og.append('circle').attr('cx', ox).attr('cy', oy).attr('r', 8).attr('fill', css('--sign')).attr('stroke', css('--sign-ink')).attr('stroke-width', 1.5).attr('vector-effect', 'non-scaling-stroke');
  og.append('text').attr('x', ox + 11).attr('y', oy - 8).text(STATE.data.airport).attr('font-size', 13).attr('font-weight', 800)
    .attr('fill', css('--text-primary')).attr('paint-order', 'stroke').attr('stroke', css('--map-land')).attr('stroke-width', 3);
  svg.call(d3.zoom().scaleExtent([1, 12]).on('zoom', ev => {
    g.attr('transform', ev.transform);
    const k = ev.transform.k;                                             // 확대해도 점·글자 크기 유지
    dots.attr('r', r => rS(r.n) / k);
    labels.attr('font-size', 11 / k).attr('stroke-width', 3 / k).attr('x', r => proj([r.a[4], r.a[3]])[0] + (rS(r.n) + 3) / k).attr('y', r => proj([r.a[4], r.a[3]])[1] + 4 / k);
    og.select('circle').attr('r', 8 / k); og.select('text').attr('font-size', 13 / k).attr('stroke-width', 3 / k).attr('x', ox + 11 / k).attr('y', oy - 8 / k);
  }));
  // 표의 행에 마우스를 올리면 지도에서 그 노선 강조
  $('rtTable').querySelectorAll('[data-rt]').forEach(tr => {
    tr.onmouseenter = () => g.selectAll('path[stroke-width]').attr('stroke-opacity', function (r) { return r && r.ap === tr.dataset.rt ? 1 : 0.15; });
    tr.onmouseleave = () => g.selectAll('path[stroke-width]').attr('stroke-opacity', r => (r ? 0.55 : null));
  });
}

/** 운항 구성 보기 (노선 · 항공사 · 기종) — 고른 것만 보이고, 숨어 있던 그래프는 다시 그림 */
export function setMixView(v) {
  $('ch-mix').dataset.mv = v;
  document.querySelectorAll('[data-mpick]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mpick === v)));
  if (PANE !== 'mix') setPane('mix');
  else if (STATE.res) { renderAirlinesRoutes(); renderTypes(STATE.res, STATE.res.methods.find(m => m.id === cfgFromUI().method) || STATE.res.methods[0]); }
  window.scrollTo({ top: 0 });
}

export function init() {
  $('sMixTabs').onclick = e => { const b = e.target.closest('[data-mpick]'); if (b) setMixView(b.dataset.mpick); };
}
