// 개요: 공항 정보 카드 · 숫자 카드 · 작은 그래프 3개 · Top 5.
import { MAPDATA } from '../data/airports.js';
import { autoTz, isoD } from '../data/period.js';
import { $, cssVar } from '../lib/dom.js';
import { esc, fmtDate, fmtN, fmtPct, fmtTime, HOUR, WD, wdOf } from '../lib/fmt.js';
import { STATE } from '../state.js';
import { charts, mkChart, themeColors } from '../ui/charts.js';
import { setPane } from '../ui/nav.js';
import { airlineRouteSummary, setMixView } from './mix.js';

/* ---------- 운항 통계 (개요 카드 · 항공사 · 노선) ---------- */
export function renderStats(res) {
  const mv = STATE.view.movements, nA = mv.filter(m => m.type === 'A').length;
  const off = STATE.data.offsetH * HOUR;
  $('stTotal').innerHTML = `${mv.length.toLocaleString()} <span class="text-sm font-medium muted">편</span>`;
  $('stTotalSub').textContent = `도착 ${nA.toLocaleString()} · 출발 ${(mv.length - nA).toLocaleString()}`;
  $('stAvg').innerHTML = `${fmtN(res.overallAvgDaily)} <span class="text-sm font-medium muted">편/일</span>`;
  $('stAvgSub').textContent = `${res.days}일 · 시간당 평균 ${fmtN(res.overallAvgDaily / 24)}편`;
  const pd = res.daily.reduce((a, b) => (b.tot > a.tot ? b : a));
  $('stPeakDay').innerHTML = `${pd.tot.toLocaleString()} <span class="text-sm font-medium muted">편</span>`;
  $('stPeakDaySub').textContent = `${fmtDate(pd.ls)} (${WD[wdOf(pd.ls)]}) · 일평균의 ${(pd.tot / res.overallAvgDaily).toFixed(2)}배`;
  let hi = 0; for (let i = 1; i < res.s.tot.length; i++) if (res.s.tot[i] > res.s.tot[hi]) hi = i;
  const hl = res.startLocal + hi * HOUR;
  $('stPeakHour').innerHTML = `${res.s.tot[hi]} <span class="text-sm font-medium muted">편</span>`;
  $('stPeakHourSub').textContent = `${fmtDate(hl)} (${WD[wdOf(hl)]}) ${fmtTime(hl)}–${fmtTime(hl + HOUR)} · 도착 ${res.s.arr[hi]} / 출발 ${res.s.dep[hi]}`;
  const nD = mv.length - nA;
  $('stRatio').innerHTML = mv.length ? `${Math.round(nA / mv.length * 100)} : ${100 - Math.round(nA / mv.length * 100)}` : '–';
  $('stRatioSub').textContent = `도착 ${nA.toLocaleString()} · 출발 ${nD.toLocaleString()} (%)`;
}

/* ---------- 개요: 작은 그래프 3개 + Top 5 (사용자 요청) ---------- */
export function renderOverviewExtras(res) {
  if (!res || !STATE.view || !$('ovHour').offsetWidth) return;      // 개요가 안 보이면 나중에 (setPane 이 다시 부름)
  const tc = themeColors(), sign = cssVar('--sign');
  const mini = (id, labels, datasets, extra = {}) => mkChart(id, { type: extra.type || 'bar', data: { labels, datasets },
    options: { responsive: true, maintainAspectRatio: false, animation: false, events: [],
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: { x: { stacked: true, grid: { display: false }, ticks: { color: tc.muted, font: { size: 10 }, maxRotation: 0, autoSkip: true, maxTicksLimit: extra.xt || 8 } },
                y: { stacked: true, beginAtZero: true, grid: { color: tc.grid }, border: { display: false }, ticks: { color: tc.muted, font: { size: 10 }, maxTicksLimit: 4 } } } } });
  const pkColor = (arr, base) => { const mx = Math.max(...arr); return arr.map(v => v === mx ? sign : base); };
  // 하루 24시간 (기간 평균)
  const ha = new Array(24).fill(0), hd = new Array(24).fill(0);
  for (let i = 0; i < res.s.arr.length; i++) { ha[i % 24] += res.s.arr[i]; hd[i % 24] += res.s.dep[i]; }
  const hA = ha.map(v => v / res.days), hD = hd.map(v => v / res.days), hT = hA.map((v, i) => v + hD[i]);
  const hMax = Math.max(...hT);
  mini('ovHour', hA.map((_, h) => String(h)), [
    { data: hA, backgroundColor: hT.map(v => v === hMax ? sign : tc.arr), borderRadius: 2 },
    { data: hD, backgroundColor: hT.map(v => v === hMax ? sign : tc.dep), borderRadius: 2 }], { xt: 7 });
  // 요일별 하루 평균 (월~일)
  const order = [1, 2, 3, 4, 5, 6, 0], wa = {}, wd = {}, wn = {};
  for (const d of res.daily) { const w = wdOf(d.ls); wa[w] = (wa[w] || 0) + d.arr; wd[w] = (wd[w] || 0) + d.dep; wn[w] = (wn[w] || 0) + 1; }
  const WA = order.map(w => wn[w] ? wa[w] / wn[w] : 0), WDp = order.map(w => wn[w] ? wd[w] / wn[w] : 0), WT = WA.map((v, i) => v + WDp[i]);
  const wMax = Math.max(...WT);
  mini('ovWd', order.map(w => WD[w]), [
    { data: WA, backgroundColor: WT.map(v => v === wMax ? sign : tc.arr), borderRadius: 3 },
    { data: WDp, backgroundColor: WT.map(v => v === wMax ? sign : tc.dep), borderRadius: 3 }]);
  // 일별 추이 (선)
  const dl = res.daily.map(d => fmtDate(d.ls).slice(5)), dt = res.daily.map(d => d.tot), dMax = Math.max(...dt);
  mini('ovDay', dl, [{ data: dt, borderColor: tc.arr, backgroundColor: 'transparent', borderWidth: 2, tension: .25, fill: false,
    pointRadius: dt.map(v => v === dMax ? 4 : (dt.length <= 31 ? 2 : 0)), pointBackgroundColor: dt.map(v => v === dMax ? sign : tc.arr), pointBorderWidth: 0 }],
    { type: 'line', xt: 6 });
  charts.ovDay.options.scales.y.beginAtZero = false; charts.ovDay.update();
  // Top 5
  const S = STATE.alrt || airlineRouteSummary(), tot = STATE.view.movements.length;
  const list = (id, rows) => {
    const mx = rows[0]?.n || 1;
    $(id).innerHTML = rows.length ? rows.map((r, i) => `<li><span class="rk">${i + 1}</span><span class="nm"><b>${esc(r.code)}</b>${esc(r.name || '')}</span>
      <span class="br"><span style="width:${(r.n / mx * 100).toFixed(1)}%"></span></span><span class="vl">${r.n.toLocaleString()}<small>${fmtPct(r.n / tot)}</small></span></li>`).join('')
      : '<li class="empty">정보 없음</li>';
  };
  const apNm = c => { const a = MAPDATA?.airports?.[c]; return a ? (a[9] || a[1] || a[0]) : ''; };
  list('ovTopRoute', S.routes.filter(r => r.ap !== '미상').slice(0, 5).map(r => ({ code: r.ap, name: apNm(r.ap), n: r.n })));
  list('ovTopAirline', S.airlines.filter(a => a.code !== '기타').slice(0, 5).map(a => ({ code: a.code, name: a.name, n: a.n })));
  const ty = new Map(); for (const m of STATE.view.movements) if (m.typecode) ty.set(m.typecode, (ty.get(m.typecode) || 0) + 1);
  list('ovTopType', [...ty.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([code, n]) => ({ code, name: '', n })));
}

/* ---------- 공항 정보 카드: 기본 정보(mwgg/Airports) + 이 데이터에서 센 값 ---------- */
export function renderAirportCard(S) {
  const A = MAPDATA.airports, code = STATE.data.airport, a = A[code];
  $('apCard').hidden = !a;
  $('sumApName').hidden = !!a;                          // 카드에 이름이 있으니 머리 줄에서는 뺌
  if (!a) return;
  const [name, city, cc, lat, lon, iata, tz, elev, state, ko] = a;
  let country = cc;
  try { country = new Intl.DisplayNames(['ko'], { type: 'region' }).of(cc) || cc; } catch (e) {}
  const off = autoTz(code, isoD(new Date((STATE.data.startLocal) * 1000)));
  $('apcName').textContent = name;
  $('apcKo').textContent = ko ? ko : '';
  $('apcPlace').textContent = [city, state && state !== city ? state : '', country].filter(Boolean).join(', ');
  // 이 데이터에서: 연결 공항·나라, 국제선 비율, 가장 많은 노선
  const known = S.routes.filter(r => A[r.ap]), knownN = known.reduce((t, r) => t + r.n, 0);
  const intlN = known.filter(r => A[r.ap][2] !== cc).reduce((t, r) => t + r.n, 0);
  const nations = new Set(known.map(r => A[r.ap][2]));
  const top = known[0], tA = top && A[top.ap];
  const airlines = S.airlines.filter(x => x.code !== '기타').length;
  const f = (t, v) => `<div><dt>${t}</dt><dd>${v}</dd></div>`;
  $('apcGrid').innerHTML =
    f('코드', `${code}${iata ? ' <small>· IATA</small> ' + esc(iata) : ''}`) +
    f('위치', `${Math.abs(lat).toFixed(3)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(3)}°${lon >= 0 ? 'E' : 'W'}`) +
    f('표고', elev == null ? '–' : `${elev.toLocaleString()} ft <small>(${Math.round(elev * 0.3048).toLocaleString()} m)</small>`) +
    f('시간대', `${off == null ? '–' : 'UTC' + (off >= 0 ? '+' : '') + off} <small>${esc(tz || '')}</small>`) +
    f('항공사', `${airlines.toLocaleString()}곳 <small>(편명 기준)</small>`) +
    f('연결 공항', `${known.length.toLocaleString()}곳 <small>· ${nations.size}개 나라</small>`) +
    f('국제선 비율', knownN ? `${fmtPct(intlN / knownN)}` : '–') +
    f('가장 많은 노선', tA ? `${esc(top.ap)} <small>${esc(tA[9] || tA[1] || tA[0])} · ${top.n.toLocaleString()}편</small>` : '–');
  // 작은 지구본 (공항 위치에 노란 점)
  const el = $('apGlobe'); el.innerHTML = '';
  if (!window.d3) return;
  const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const W = 132, proj = d3.geoOrthographic().rotate([-lon, -lat * 0.7]).fitExtent([[3, 3], [W - 3, W - 3]], { type: 'Sphere' });
  const path = d3.geoPath(proj), svg = d3.select(el).append('svg').attr('width', W).attr('height', W);
  svg.append('path').datum({ type: 'Sphere' }).attr('d', path).attr('fill', css('--map-water'));
  svg.append('path').datum(d3.geoGraticule10()).attr('d', path).attr('fill', 'none').attr('stroke', css('--map-grid')).attr('stroke-width', .5);
  svg.append('path').datum(MAPDATA.land).attr('d', path).attr('fill', css('--map-land'));
  const [x, y] = proj([lon, lat]);
  svg.append('circle').attr('cx', x).attr('cy', y).attr('r', 5).attr('fill', css('--sign')).attr('stroke', '#17130a').attr('stroke-width', 1.5);
}

export function init() {
  document.querySelector('.ovmini').addEventListener('click', e => {
    const b = e.target.closest('[data-ovp]'); if (!b) return;
    setPane('profile'); document.querySelector(`[data-ppick="${b.dataset.ovp}"]`)?.click();
  });
  document.querySelector('.ovtop').addEventListener('click', e => {
    const b = e.target.closest('[data-ovm]'); if (b) setMixView(b.dataset.ovm);
  });
}
