// 운항량: 시간대별·일별·요일별·월별·연별 그래프와 세부 정보 표.
import { peakOf, yearGroups } from '../engine/stats.js';
import { $, cssVar } from '../lib/dom.js';
import { esc, fmtDate, fmtN, fmtPct, HOUR, pad, WD, wdOf } from '../lib/fmt.js';
import { STATE } from '../state.js';
import { barDs, baseOptions, mkChart, themeColors, zoomStack } from '../ui/charts.js';
import { cfgFromUI } from './peak.js';
import { fillDetail, setTargetLabel, showDesign, syncTarget, TARGET } from './profile-target.js';

/* ---------- 시간대별 프로파일 ---------- */
export function buildProfileOptions(res, sel) {
  const s = $('profileSel'), prev = s.value;
  const opts = [['avg', '기간 전체 평균일']];
  const busiest = res.daily.reduce((a, b) => (b.tot > a.tot ? b : a));
  opts.push([`day:${busiest.d}`, `PEAK 일 · ${fmtDate(busiest.ls)} (${WD[wdOf(busiest.ls)]}) · ${busiest.tot}편`]);
  if (sel.day != null && showDesign()) opts.push([`day:${sel.day}`, `설계일 · ${fmtDate(res.daily[sel.day].ls)} (${WD[wdOf(res.daily[sel.day].ls)]})`]);
  opts.push(['adpm', `${res.adpm?.label} (§3.4.3 b)`]);
  for (const d of res.daily) opts.push([`day:${d.d}`, `${fmtDate(d.ls)} (${WD[wdOf(d.ls)]}) · ${d.tot}편`]);
  s.innerHTML = opts.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');
  s.value = opts.some(o => o[0] === prev) && STATE.keepProfile ? prev : opts[0][0];
  // 평균 · PEAK 버튼 + 세부 선택(설계일·피크 월 평균일·날짜별)
  TARGET.profile.modes.peak = `day:${busiest.d}`;
  TARGET.profile.modes.design = sel.day != null ? `day:${sel.day}` : null;
  // 버튼에 날짜 표시
  const md = ls => `${fmtDate(ls).slice(5)} (${WD[wdOf(ls)]})`;
  setTargetLabel('profile', 'peak', 'PEAK 일', md(busiest.ls));
  setTargetLabel('profile', 'design', '설계일', sel.day != null ? md(res.daily[sel.day].ls) : '없음');
  syncTarget('profile');
}

export function renderProfile() {
  const res = STATE.res, tc = themeColors(), v = $('profileSel').value;
  const sel = res.methods.find(m => m.id === cfgFromUI().method) || res.methods[0];
  let arr, dep, avg2, note, band = null;
  const labels = [...Array(24).keys()].map(h => `${pad(h)}시`);
  if (v.startsWith('day:')) {
    const d = +v.slice(4), o = d * 24;
    arr = Array.from(res.s.arr.slice(o, o + 24));
    dep = Array.from(res.s.dep.slice(o, o + 24));
    // 자정 이후 시간까지 이어지는 연속 2시간 평균 (마지막 시간은 다음날 0시와 평균)
    avg2 = labels.map((_, h) => res.c.tot[o + h] ?? null);
    note = `${fmtDate(res.daily[d].ls)} · 총 ${res.daily[d].tot}편 (도착 ${res.daily[d].arr} / 출발 ${res.daily[d].dep}) · 선은 해당 시각부터 2시간 평균`;
    if (sel.start != null && sel.day === d) {
      const h0 = (sel.start - res.daily[d].ls) / HOUR;
      band = { from: h0, to: h0 + sel.len / HOUR };
    }
  } else {
    let src;
    if (v === 'adpm') { src = res.adpm; note = `${res.adpm.label} (${res.adpm.n}일) 시간대별 평균`; }
    else {
      const a = new Array(24).fill(0), dp = new Array(24).fill(0);
      for (let i = 0; i < res.s.arr.length; i++) { a[i % 24] += res.s.arr[i]; dp[i % 24] += res.s.dep[i]; }
      src = { arr: a.map(x => x / res.days), dep: dp.map(x => x / res.days) };
      note = `분석 기간 ${res.days}일 시간대별 평균`;
    }
    arr = src.arr; dep = src.dep;
    const tot = arr.map((x, h) => x + dep[h]);
    avg2 = tot.map((x, h) => (x + tot[(h + 1) % 24]) / 2);
    if (sel.id === 'adpm' && v === 'adpm') band = { from: sel.hourOfDay, to: sel.hourOfDay + 1 };
  }
  const pk = peakOf(Array.from(arr), Array.from(dep)), fmtH = h => `${pad(h)}:00–${pad(h + 1)}:00`;
  const dec = v.startsWith('day:') ? 0 : 1;
  $('profileNote').innerHTML = `<b style="color:var(--text-primary)">PEAK 시간 ${fmtH(pk.i)} · ${fmtN(pk.tot, dec)}편</b> (도착 ${fmtN(arr[pk.i], dec)} / 출발 ${fmtN(dep[pk.i], dec)}) · ${esc(note)}`;
  const datasets = [
    // 선은 별도 stack 그룹 → 막대(도착+출발)와 합산되지 않음 (단일 y축 유지)
    { type: 'line', label: '합계 연속 2시간 평균', data: avg2, stack: 'line', borderColor: tc.avg, backgroundColor: tc.avg, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: 0.25, order: 0 },
    { ...barDs('도착', arr, tc.arr), order: 1 },
    { ...barDs('출발', dep, tc.dep), order: 1 }
  ];
  if (!showDesign()) band = null;
  const o = baseOptions(tc, { stacked: true, plugins: { overlay: band ? { ...band, color: tc.band } : {} } });
  const hMean = arr.reduce((t, v, i) => t + v + dep[i], 0) / arr.length;
  o.plugins.overlay.avg = { value: hMean, label: `평균 ${fmtN(hMean)}편/시간`, color: tc.primary, bg: tc.surface };
  o.plugins.tooltip.callbacks = {
    label: c => `${c.dataset.label}: ${fmtN(c.parsed.y)}편`,
    footer: items => { const a = items.find(i => i.dataset.label === '도착'), d = items.find(i => i.dataset.label === '출발'); return a && d ? `합계: ${fmtN(a.parsed.y + d.parsed.y)}편` : ''; }
  };
  applyPeak(o, datasets, peakMark(pk.i, pk.tot, `PEAK ${pad(pk.i)}시 · ${fmtN(pk.tot, dec)}편`), 'PEAK 시간 (가장 바쁜 시간)');
  zoomStack(o, datasets, arr, dep, 'profileChart');
  mkChart('profileChart', { type: 'bar', data: { labels, datasets }, options: o });
  setProfTable(`시간대별 · ${note}`, labels.map((_, h) => ({ label: fmtH(h), arr: arr[h], dep: dep[h], extra: avg2[h] })),
    { dec, peak: pk.i, extraHead: '연속 2시간 평균', labelHead: '시간',
      summary: { sumLabel: v.startsWith('day:') ? '하루 합계' : '하루 합계 (평균일)', avgLabel: '시간당 평균', avgUnit: '편/시간' } });
}

/* ---------- 요일별 · 월별 프로파일 (시간대별 프로파일과 같은 형식) ---------- */
export function buildWdOptions(res) {
  const s = $('wdSel'), prev = s.value;
  const opts = [['all', `기간 전체 (${res.days}일)`]];
  if (res.peakMonth) opts.push([`m:${res.peakMonth.k}`, `피크 월 · ${res.peakMonth.k}`]);
  for (const m of res.months) if (m !== res.peakMonth) opts.push([`m:${m.k}`, m.k]);
  s.innerHTML = opts.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');
  s.value = opts.some(o => o[0] === prev) ? prev : 'all';
  TARGET.wd.modes.peak = res.peakMonth ? `m:${res.peakMonth.k}` : null;
  setTargetLabel('wd', 'peak', 'PEAK 월', res.peakMonth ? res.peakMonth.k : '없음');
  fillDetail('wd', res.months.map(m => [`m:${m.k}`, m.k + (m === res.peakMonth ? ' (PEAK 월)' : '')]));
  syncTarget('wd');
}

/* 운항 프로파일 "세부 정보" 표: 지금 그린 차트의 값을 그대로 표로 (rows: {label, arr, dep, extra?, tag?}) */
export const profTbl = { sort: 'time', last: null };
const SORT_LABEL = { 시간: '시간순', 일자: '날짜순', 요일: '요일순', 월: '월순', 연: '연도순' };

function setProfTable(title, rows, opts = {}) {
  profTbl.last = { title, rows: rows.map((r, i) => ({ ...r, isPeak: i === opts.peak })), opts };
  renderProfTable();
}

export function renderProfTable() {
  if (!profTbl.last) return;
  const { title, opts } = profTbl.last, { dec = 1, extraHead = null, labelHead = '구분', extraDec = 1 } = opts;
  let rows = profTbl.last.rows;
  if (profTbl.sort === 'desc') rows = [...rows].sort((a, b) => (b.arr + b.dep) - (a.arr + a.dep));
  const peak = rows.findIndex(r => r.isPeak);
  document.querySelector('[data-psort="time"]').textContent = SORT_LABEL[labelHead] || '시간순';
  document.querySelectorAll('[data-psort]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.psort === profTbl.sort)));
  const sum = rows.reduce((a, r) => a + r.arr + r.dep, 0);
  // 합계 · 평균 카드 (차트 위)
  const sm = opts.summary || {}, n = rows.length || 1;
  const sA = sm.sumArr ?? rows.reduce((a, r) => a + r.arr, 0), sD = sm.sumDep ?? rows.reduce((a, r) => a + r.dep, 0);
  const aA = sm.avgArr ?? rows.reduce((a, r) => a + r.arr, 0) / n, aD = sm.avgDep ?? rows.reduce((a, r) => a + r.dep, 0) / n, sdec = sm.sumDec ?? dec, adec = sm.avgDec ?? 1;
  $('profStats').innerHTML = `<div class="pstat"><div class="pstat-label">${esc(sm.sumLabel || '합계')}</div>
      <div class="pstat-value">${fmtN(sA + sD, sdec)}<small>편</small></div><div class="pstat-sub">도착 ${fmtN(sA, sdec)} · 출발 ${fmtN(sD, sdec)}</div></div>
    <div class="pstat"><div class="pstat-label">${esc(sm.avgLabel || '평균')}</div>
      <div class="pstat-value">${fmtN(aA + aD, adec)}<small>${esc(sm.avgUnit || '편')}</small></div><div class="pstat-sub">도착 ${fmtN(aA, adec)} · 출발 ${fmtN(aD, adec)}</div></div>` +
    (() => { const pk = profTbl.last.rows.find(r => r.isPeak); if (!pk) return '';
      return `<div class="pstat"><div class="pstat-label"><span class="badge" style="margin:0 4px 0 0">PEAK</span>${esc(pk.label)}</div>
      <div class="pstat-value">${fmtN(pk.arr + pk.dep, dec)}<small>${esc(sm.avgUnit || '편')}</small></div><div class="pstat-sub">도착 ${fmtN(pk.arr, dec)} · 출발 ${fmtN(pk.dep, dec)} · 평균의 ${((pk.arr + pk.dep) / ((aA + aD) || 1)).toFixed(2)}배</div></div>`; })();
  $('profDetailNote').textContent = title;
  $('profDetailTable').innerHTML = `<thead><tr><th>${labelHead}</th><th class="num">도착</th><th class="num">출발</th><th class="num">합계</th><th class="num">비율</th>${extraHead ? `<th class="num">${extraHead}</th>` : ''}</tr></thead><tbody>` +
    rows.map((r, i) => { const tot = r.arr + r.dep;
      return `<tr class="${i === peak ? 'hl' : ''}"><td>${esc(r.label)}${i === peak ? ' <span class="badge">PEAK</span>' : ''}${r.tag ? ` <span class="chip">${esc(r.tag)}</span>` : ''}</td>
        <td class="num">${fmtN(r.arr, dec)}</td><td class="num">${fmtN(r.dep, dec)}</td><td class="num"><b>${fmtN(tot, dec)}</b></td>
        <td class="num">${sum ? fmtPct(tot / sum) : '–'}</td>${extraHead ? `<td class="num">${r.extra == null ? '–' : extraDec === 2 ? r.extra.toFixed(2) : fmtN(r.extra, extraDec)}</td>` : ''}</tr>`; }).join('') +
    `</tbody><tfoot><tr><td><b>합계</b></td><td class="num">${fmtN(rows.reduce((a, r) => a + r.arr, 0), dec)}</td><td class="num">${fmtN(rows.reduce((a, r) => a + r.dep, 0), dec)}</td><td class="num"><b>${fmtN(sum, dec)}</b></td><td class="num">100%</td>${extraHead ? '<td></td>' : ''}</tr>
      <tr><td><b>평균</b></td><td class="num">${fmtN(rows.reduce((a, r) => a + r.arr, 0) / (rows.length || 1), 1)}</td><td class="num">${fmtN(rows.reduce((a, r) => a + r.dep, 0) / (rows.length || 1), 1)}</td><td class="num"><b>${fmtN(sum / (rows.length || 1), 1)}</b></td><td class="num">${rows.length ? fmtPct(1 / rows.length) : '–'}</td>${extraHead ? '<td></td>' : ''}</tr></tfoot>`;
}

function peakMark(i, value, label) {
  return { index: i, value, label, bg: cssVar('--sign'), ink: cssVar('--sign-ink'), band: cssVar('--sign-soft') };
}

const peakFill = (base, color, i) => ({ backgroundColor: c => (c.dataIndex === i ? color : base) });

function applyPeak(o, datasets, mark, tip) {
  o.plugins.overlay = { ...(o.plugins.overlay || {}), mark };
  o.scales.y.suggestedMax = mark.value * 1.15;          // 말풍선 자리
  o.plugins.tooltip.callbacks.afterTitle = it => (it[0].dataIndex === mark.index ? '★ ' + tip : '');
  const arr = datasets.find(d => d.label === '도착'), dep = datasets.find(d => d.label === '출발');
  Object.assign(arr, peakFill(arr.backgroundColor, cssVar('--sign-deep'), mark.index));
  Object.assign(dep, peakFill(dep.backgroundColor, cssVar('--sign'), mark.index));
}

function profileChart(id, labels, arr, dep, line, lineLabel, band, titles, peak) {
  const tc = themeColors();
  const o = baseOptions(tc, { stacked: true, plugins: { overlay: band ? { ...band, color: tc.band } : {} } });
  if (line?.length && line.every(v => v === line[0]))   // 평균 점선에 값 라벨
    o.plugins.overlay.avg = { value: line[0], label: `평균 ${fmtN(line[0], line[0] >= 1000 ? 0 : 1)}편`, color: tc.avg, bg: tc.surface, noLine: true };
  o.plugins.tooltip.callbacks = {
    title: i => titles ? titles[i[0].dataIndex] : i[0].label,
    label: c => `${c.dataset.label}: ${fmtN(c.parsed.y)}편`,
    footer: items => { const a = items.find(i => i.dataset.label === '도착'), d = items.find(i => i.dataset.label === '출발'); return a && d ? `합계: ${fmtN(a.parsed.y + d.parsed.y)}편` : ''; }
  };
  const datasets = [
    { type: 'line', label: lineLabel, data: line, stack: 'line', borderColor: tc.avg, backgroundColor: tc.avg, borderWidth: 2, borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 0, order: 0 },
    { ...barDs('도착', arr, tc.arr), order: 1 }, { ...barDs('출발', dep, tc.dep), order: 1 }
  ];
  if (peak) applyPeak(o, datasets, peak.mark, peak.tip);
  zoomStack(o, datasets, arr, dep, id);
  mkChart(id, { type: 'bar', data: { labels, datasets }, options: o });
}

export function renderWeekdayProfile() {
  const res = STATE.res, v = $('wdSel').value;
  const sel = res.methods.find(m => m.id === cfgFromUI().method) || res.methods[0];
  const ds = v === 'all' ? res.daily : (res.months.find(m => 'm:' + m.k === v)?.ds || res.daily);
  const order = [1, 2, 3, 4, 5, 6, 0];
  const g = order.map(w => { const x = ds.filter(d => wdOf(d.ls) === w); const n = x.length || 1;
    return { n: x.length, arr: x.reduce((a, d) => a + d.arr, 0) / n, dep: x.reduce((a, d) => a + d.dep, 0) / n }; });
  const avg = ds.reduce((a, d) => a + d.tot, 0) / ds.length;
  const selWd = sel.day != null ? wdOf(res.daily[sel.day].ls) : null;
  const k = showDesign() ? order.indexOf(selWd) : -1;
  const pk = peakOf(g.map(x => x.arr), g.map(x => x.dep)), top = [pk.i, pk.tot];
  $('wdNote').innerHTML = `<b style="color:var(--text-primary)">PEAK 요일 ${WD[order[top[0]]]}요일 · 하루 평균 ${fmtN(top[1])}편</b> (도착 ${fmtN(g[pk.i].arr)} / 출발 ${fmtN(g[pk.i].dep)}, 평균의 ${(top[1] / avg).toFixed(2)}배)` +
    ` · ${v === 'all' ? '분석 기간' : esc(v.slice(2))} 요일별 하루 평균`;
  profileChart('wdChart', order.map(w => WD[w]), g.map(x => x.arr), g.map(x => x.dep), g.map(() => avg), v === 'all' ? '기간 일평균 (합계)' : '해당 월 일평균 (합계)',
    k >= 0 && k !== pk.i ? { from: k, to: k + 1 } : null, order.map((w, i) => `${WD[w]}요일 (${g[i].n}일 평균)`),
    { mark: peakMark(pk.i, pk.tot, `PEAK ${WD[order[pk.i]]}요일 · ${fmtN(pk.tot)}편`), tip: 'PEAK 요일 (가장 바쁜 요일)' });
  setProfTable(`요일별 하루 평균 · ${v === 'all' ? '분석 기간 전체' : v.slice(2)}`, order.map((w, i) => ({ label: `${WD[w]}요일`, arr: g[i].arr, dep: g[i].dep, extra: g[i].n })),
    { dec: 1, peak: pk.i, extraHead: '일수', labelHead: '요일', extraDec: 0,
      summary: { sumLabel: `${v === 'all' ? '기간' : v.slice(2)} 합계 (${ds.length}일)`, sumArr: ds.reduce((a, d) => a + d.arr, 0), sumDep: ds.reduce((a, d) => a + d.dep, 0), sumDec: 0,
        avgLabel: '요일 평균 (하루)', avgUnit: '편/일' } });
}

function renderMonthProfile() {
  const res = STATE.res, total = $('monSel').value === 'total';
  const ms = res.months.map(m => { const a = m.ds.reduce((x, d) => x + d.arr, 0), d = m.ds.reduce((x, y) => x + y.dep, 0), n = m.ds.length;
    return { k: m.k, n, arr: total ? a : a / n, dep: total ? d : d / n, peak: m === res.peakMonth }; });
  const line = total ? ms.reduce((x, m) => x + m.arr + m.dep, 0) / ms.length : res.overallAvgDaily;
  const pk = ms.findIndex(m => m.peak), top = peakOf(ms.map(m => m.arr), ms.map(m => m.dep));
  const partial = res.months.filter(m => m.ds.length < new Date(Date.UTC(+m.k.slice(0, 4), +m.k.slice(5, 7), 0)).getUTCDate()).length;
  // PEAK 값은 위 카드에 있으므로 여기에는 참고 사항만 (없으면 숨김)
  const monRemarks = [pk >= 0 && pk !== top.i ? `일평균 기준 피크 월은 ${ms[pk].k} (일평균 ${fmtN(res.peakMonth.avg)}편, 파란 음영)` : '',
    total && partial ? `날짜가 일부만 있는 달 ${partial}개는 합계가 작게 나옵니다` : ''].filter(Boolean);
  $('monNote').textContent = monRemarks.join(' · ');
  $('monNote').hidden = !monRemarks.length;
  profileChart('monChart', ms.map(m => m.k), ms.map(m => m.arr), ms.map(m => m.dep), ms.map(() => line), total ? '월 평균 (합계)' : '기간 일평균 (합계)',
    pk >= 0 && pk !== top.i ? { from: pk, to: pk + 1 } : null, ms.map(m => `${m.k} (${m.n}일${total ? '' : ' 평균'})`),
    { mark: peakMark(top.i, top.tot, `PEAK ${ms[top.i].k} · ${fmtN(top.tot, total ? 0 : 1)}편`), tip: total ? 'PEAK 월 (월 합계가 가장 많은 달)' : 'PEAK 월 (하루 평균이 가장 많은 달)' });
  setProfTable(`월별 ${total ? '합계' : '하루 평균'}`, ms.map(m => ({ label: m.k, arr: m.arr, dep: m.dep, extra: m.n })),
    { dec: total ? 0 : 1, peak: top.i, extraHead: '데이터 일수', labelHead: '월', extraDec: 0,
      summary: { sumLabel: `기간 합계 (${res.months.length}개월)`, sumArr: res.daily.reduce((a, d) => a + d.arr, 0), sumDep: res.daily.reduce((a, d) => a + d.dep, 0), sumDec: 0,
        avgLabel: total ? '월 평균' : `하루 평균 (${res.months.length}개월 평균)`, avgUnit: total ? '편/월' : '편/일' } });
}

function renderYearProfile() {
  const res = STATE.res, total = $('yearSel').value === 'total';
  const ys = yearGroups(res).map(y => { const a = y.ds.reduce((x, d) => x + d.arr, 0), d = y.ds.reduce((x, z) => x + z.dep, 0), n = y.ds.length;
    return { k: y.k, n, arr: total ? a : a / n, dep: total ? d : d / n }; });
  const line = total ? ys.reduce((x, y) => x + y.arr + y.dep, 0) / ys.length : res.overallAvgDaily;
  const top = peakOf(ys.map(y => y.arr), ys.map(y => y.dep));
  const fullDays = y => (+y % 4 === 0 && (+y % 100 !== 0 || +y % 400 === 0)) ? 366 : 365;
  const partial = ys.filter(y => y.n < fullDays(y.k));
  const note = total && partial.length ? `날짜가 일부만 있는 해(${partial.map(y => `${y.k}년 ${y.n}일`).join(', ')})는 합계가 작게 나옵니다. 해끼리 비교는 "하루 평균"이 정확합니다` : '';
  $('yearNote').textContent = note; $('yearNote').hidden = !note;
  profileChart('yearChart', ys.map(y => y.k), ys.map(y => y.arr), ys.map(y => y.dep), ys.map(() => line), total ? '연평균 (합계)' : '기간 일평균 (합계)',
    null, ys.map(y => `${y.k}년 (${y.n}일${total ? '' : ' 평균'})`),
    { mark: peakMark(top.i, top.tot, `PEAK ${ys[top.i].k} · ${fmtN(top.tot, total ? 0 : 1)}편`), tip: total ? 'PEAK 연도 (연 합계가 가장 많은 해)' : 'PEAK 연도 (하루 평균이 가장 많은 해)' });
  setProfTable(`연별 ${total ? '합계' : '하루 평균'}`, ys.map(y => ({ label: y.k, arr: y.arr, dep: y.dep, extra: y.n })),
    { dec: total ? 0 : 1, peak: top.i, extraHead: '데이터 일수', labelHead: '연', extraDec: 0,
      summary: { sumLabel: `기간 합계 (${ys.length}개 연도)`, sumArr: res.daily.reduce((a, d) => a + d.arr, 0), sumDep: res.daily.reduce((a, d) => a + d.dep, 0), sumDec: 0,
        avgLabel: total ? '연 평균' : `하루 평균 (${ys.length}개 연도 평균)`, avgUnit: total ? '편/년' : '편/일' } });
}

/* ---------- 일별 ---------- */
function renderDaily(res, sel) {
  const tc = themeColors();
  const labels = res.daily.map(d => fmtDate(d.ls).slice(5));
  const pk = res.daily.reduce((a, b) => (b.tot > a.tot ? b : a));
  const pkI = res.daily.indexOf(pk), pkLbl = `${fmtDate(pk.ls)} (${WD[wdOf(pk.ls)]})`;
  $('dailyNote').innerHTML = `<b style="color:var(--text-primary)">PEAK 일 ${pkLbl} · ${pk.tot.toLocaleString()}편</b> (도착 ${pk.arr} / 출발 ${pk.dep}, 일평균의 ${(pk.tot / res.overallAvgDaily).toFixed(2)}배)` +
    ` · 기간 일평균 ${fmtN(res.overallAvgDaily)}편 · 피크 월 ${esc(res.peakMonth?.k)} 일평균 ${fmtN(res.peakMonth?.avg)}편`;
  const band = showDesign() && sel.day != null && sel.day !== pkI ? { from: sel.day, to: sel.day + 1, color: tc.band } : {};
  const mark = { index: pkI, value: pk.tot, label: `PEAK ${fmtDate(pk.ls).slice(5)} · ${pk.tot.toLocaleString()}편`, bg: cssVar('--sign'), ink: cssVar('--sign-ink'), band: cssVar('--sign-soft') };
  const o = baseOptions(tc, { stacked: true, plugins: { overlay: { ...band, mark } } });
  const dMean = res.daily.reduce((t, d) => t + d.tot, 0) / res.daily.length;
  o.plugins.overlay.avg = { value: dMean, label: `평균 ${fmtN(dMean)}편/일`, color: tc.primary, bg: tc.surface };
  o.scales.y.suggestedMax = pk.tot * 1.15;           // 말풍선 자리
  o.plugins.tooltip.callbacks = {
    title: i => { const d = res.daily[i[0].dataIndex]; return `${fmtDate(d.ls)} (${WD[wdOf(d.ls)]})`; },
    label: c => `${c.dataset.label}: ${fmtN(c.parsed.y, 0)}편`,
    footer: i => `합계: ${res.daily[i[0].dataIndex].tot}편`
  };
  o.plugins.tooltip.callbacks.afterTitle = i => (i[0].dataIndex === pkI ? '★ PEAK 일 (기간 중 가장 바쁜 날)' : '');
  // 첨두일 막대는 표지 노랑으로 칠해 365개 막대 사이에서도 바로 보이게
  const hi = (base, peakColor) => ({ backgroundColor: c => (c.dataIndex === pkI ? peakColor : base) });
  const dArr = res.daily.map(d => d.arr), dDep = res.daily.map(d => d.dep);
  const datasets = [
    { ...barDs('도착', dArr, tc.arr), ...hi(tc.arr, cssVar('--sign-deep')) },
    { ...barDs('출발', dDep, tc.dep), ...hi(tc.dep, cssVar('--sign')) }
  ];
  zoomStack(o, datasets, dArr, dDep, 'dailyChart');
  mkChart('dailyChart', { type: 'bar', data: { labels, datasets }, options: o });
  setProfTable(`일별 · ${res.daily.length}일`, res.daily.map(d => ({ label: `${fmtDate(d.ls)} (${WD[wdOf(d.ls)]})`, arr: d.arr, dep: d.dep,
    extra: d.tot / res.overallAvgDaily, tag: showDesign() && d.d === sel.day ? '설계일' : '' })), { dec: 0, peak: pkI, extraHead: '÷ 일평균', labelHead: '일자', extraDec: 2,
      summary: { sumLabel: `기간 합계 (${res.daily.length}일)`, avgLabel: '하루 평균', avgUnit: '편/일' } });
}

export const PVIEW_NAME = { hour: '시간대별', day: '일별', wd: '요일별', month: '월별', year: '연별' };
export let ptab = 'hour';
export function setPtab(v) { ptab = v; }

export function renderProfileTab() {
  document.querySelectorAll('[data-ppane]').forEach(el => { el.style.display = el.dataset.ppane === ptab ? '' : 'none'; });
  document.querySelectorAll('[data-pctl]').forEach(el => { el.hidden = el.dataset.pctl !== ptab; });   // 표시 대상은 카드와 같은 줄
  if (!STATE.res) return;
  const sel = STATE.res.methods.find(m => m.id === cfgFromUI().method) || STATE.res.methods[0];
  ({ hour: renderProfile, day: () => renderDaily(STATE.res, sel), wd: renderWeekdayProfile, month: renderMonthProfile, year: renderYearProfile })[ptab]();
}

export function init() {
  // 운항 패턴: 표시 대상 줄을 본문 머리(예전 보기 탭 자리)로
  document.querySelector('#sec-profile .panel-head').appendChild(document.querySelector('#sec-profile .pctl'));
  $('profileSel').onchange = renderProfile;
  document.querySelectorAll('[data-ptab]').forEach(b => b.onclick = () => {
    ptab = b.dataset.ptab;
    document.querySelectorAll('[data-ptab]').forEach(x => x.setAttribute('aria-selected', String(x === b)));
    renderProfileTab();
  });
  $('wdSel').onchange = () => STATE.res && renderWeekdayProfile();
  $('monSel').onchange = () => STATE.res && renderMonthProfile();
  $('yearSel').onchange = () => STATE.res && renderYearProfile();
}
