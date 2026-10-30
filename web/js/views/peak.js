// 첨두시간 산정 (선택): 기준 선택 · 비교표 · 순위 곡선 · 첨두 비율 · 처리능력 · UK CAA 대조.
import { ranked } from '../engine/peak.js';
import { caaExpect, capStatus, ratioSummary } from '../engine/stats.js';
import { $ } from '../lib/dom.js';
import { DAY, esc, fmtDate, fmtDT, fmtN, fmtPct } from '../lib/fmt.js';
import { renderAll } from '../run.js';
import { STATE } from '../state.js';
import { baseOptions, mkChart, themeColors } from '../ui/charts.js';
import { PANE, setPane, syncSideNav } from '../ui/nav.js';
import { saveLast } from '../ui/session.js';
import { TARGET } from './profile-target.js';

export function cfgFromUI() {
  const bn = $('busyN').value;
  return {
    method: $('method').value,
    N: bn === 'custom' ? Math.max(1, parseInt($('customN').value, 10) || 1) : +bn,
    window: $('window').value,
    adpmDays: $('adpmDays').value,
    adpmSpan: +$('adpmSpan').value,
    pct: +$('pct').value
  };
}

export function renderSplit(res) {
  const rows = [['arr', '도착 (Arrivals)'], ['dep', '출발 (Departures)'], ['tot', '합계 (Total Movements)']];
  const sw = { arr: 'var(--series-arr)', dep: 'var(--series-dep)', tot: 'var(--text-secondary)' };
  $('splitTable').innerHTML = `<thead><tr><th>구분</th><th class="num">기간 총운항</th><th class="num">일평균</th>
    <th class="num">Peak 수요(2h 평균)</th><th>Peak 시각</th><th class="num">Busy Hour(${res.N}번째)</th>
    <th class="num">최대 단일 시간</th><th class="num">Peak/일평균</th></tr></thead><tbody>` +
    rows.map(([k, name]) => {
      const x = res.split[k];
      return `<tr><td><span class="swatch" style="background:${sw[k]}"></span>${name}</td>
        <td class="num">${fmtN(x.total, 0)}</td><td class="num">${fmtN(x.avgDaily)}</td>
        <td class="num"><b>${fmtN(x.peak?.v)}</b></td><td>${x.peak ? fmtDT(x.peak.start) : '–'}</td>
        <td class="num">${fmtN(x.busy?.v)}</td><td class="num">${fmtN(x.rawPeak?.v, 0)}</td>
        <td class="num">${fmtPct(x.peakHourShare)}</td></tr>`;
    }).join('') + '</tbody>';
}

const METHOD_ORDER = ['icao_peak', 'icao_busy', 'nth_hour', 'adpm', 'iata_sbd', 'pct_day', 'pct5', 'abs_peak'];
const SRC_OF = { icao_peak: 'src-peak', icao_busy: 'src-busy', nth_hour: 'src-343', adpm: 'src-344', iata_sbd: 'src-344', pct_day: 'src-343', pct5: 'src-343', abs_peak: 'src-abs' };

export function renderMethodTable(res, selId) {
  $('methodTable').innerHTML = `<thead><tr><th>산정 기준</th><th>근거</th><th>첨두 시간대</th>
    <th class="num">합계</th><th class="num">도착</th><th class="num">출발</th><th class="num">설계일 총운항</th><th class="num">첨두 집중률</th><th class="num">연간 운항 대비</th></tr></thead><tbody>` +
    [...res.methods].sort((x, y) => METHOD_ORDER.indexOf(x.id) - METHOD_ORDER.indexOf(y.id)).map(m => `<tr class="${m.id === selId ? 'hl' : ''}"${m.id === 'abs_peak' ? ' style="color:var(--text-muted)" title="계획 기준으로 쓰지 않는 참고값 (§3.4.2, Section II §1.2.5)"' : ''}><td>${esc(m.name)}${m.id === selId ? ' <span class="badge">선택</span>' : ''} <a href="icao-source.html#${SRC_OF[m.id]}" class="text-xs" style="color:var(--accent)">원문</a></td>
      <td class="secondary">${esc(m.basis)}</td><td>${esc(m.when)}</td>
      <td class="num"><b>${fmtN(m.v)}</b></td><td class="num">${fmtN(m.arr)}</td><td class="num">${fmtN(m.dep)}</td>
      <td class="num">${fmtN(m.dayTotal, 0)}</td><td class="num">${fmtPct(m.conc)}</td><td class="num">${m.annualRatio == null ? '–' : (m.annualRatio * 100).toFixed(3) + '%'}</td></tr>`).join('') + '</tbody>';
}

/* ---------- 순위 곡선 ---------- */
export function renderRank(res) {
  const tc = themeColors();
  const LIMIT = Math.min(res.rkTot.length, Math.max(200, res.N * 3));
  const twoH = res.rkTot.slice(0, LIMIT).map(e => e.v);
  const raw = Array.from(res.s.tot).sort((a, b) => b - a).slice(0, LIMIT);
  $('rankNote').textContent = `상위 ${LIMIT}개 시간 (전체 ${res.rkTot.length}개). 점선 = Busy Hour 순위 ${res.N}`;
  const o = baseOptions(tc, { plugins: { overlay: { vline: res.N - 1, vlabel: `N=${res.N}: ${fmtN(twoH[res.N - 1])}편`, lineColor: tc.primary } } });
  o.scales.x.title = { display: true, text: '순위', color: tc.text };
  o.plugins.tooltip.callbacks = { title: i => `${i[0].label}위`, label: c => `${c.dataset.label}: ${fmtN(c.parsed.y)}편` };
  mkChart('rankChart', {
    type: 'line',
    data: {
      labels: twoH.map((_, i) => i + 1), datasets: [
        { label: '연속 2시간 평균', data: twoH, borderColor: tc.avg, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, stepped: false },
        { label: '단일 시간', data: raw, borderColor: tc.arr, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5 }
      ]
    }, options: o
  });
}

export function renderRatios(res, sel) {
  const R = STATE.ratios = ratioSummary(res, sel);
  const pct = (v, d = 2) => v == null || !isFinite(v) ? '–' : (v * 100).toFixed(d) + '%';
  const peakHourRatio = R.chain[R.chain.length - 1].annual;
  $('ratioNote').textContent = `peak hour ratio = ${fmtN(sel.v)} ÷ ${fmtN(R.annual, 0)} = ${pct(peakHourRatio, 4)}` +
    (R.pm ? ` · busy month ratio = ${pct(R.pm.est / R.annual)}` : '') +
    (res.days < 360 ? ` · 분석 기간이 ${res.days}일이라 월별 비율은 1년치일 때와 다릅니다 (없는 달은 표에 없음).` : '');
  $('ratioChain').innerHTML = '<thead><tr><th>단계</th><th class="num">운항</th><th class="num">연간 대비</th><th class="num">앞 단계 대비</th><th>설명</th></tr></thead><tbody>' +
    R.chain.map(c => `<tr class="${c.key ? 'hl' : ''}"><td>${c.key ? '<b>' + esc(c.step) + '</b>' : esc(c.step)}</td><td class="num">${fmtN(c.v, c.v >= 1000 ? 0 : 1)}</td>
      <td class="num">${c.key ? '<b>' + pct(c.annual, 4) + '</b>' : pct(c.annual, c.annual < 0.01 ? 4 : 2)}</td>
      <td class="num">${c.prev == null ? '–' : (c.prev < 1 ? pct(c.prev) : '×' + c.prev.toFixed(2))}<div class="text-xs muted">${esc(c.prevLbl)}</div></td>
      <td class="secondary text-xs">${esc(c.note)}</td></tr>`).join('') + '</tbody>';
}

export function renderCapacity(res, sel) {
  const tc = themeColors();
  const cap = parseFloat($('capTotal').value);
  const warn = Math.min(1, Math.max(0.01, (parseFloat($('capWarn').value) || 85) / 100));
  const g = (parseFloat($('fcGrowth').value) || 0) / 100;
  const rc = (parseFloat($('fcRatio').value) || 0) / 100;
  const years = Math.min(40, Math.max(1, parseInt($('fcYears').value, 10) || 20));
  if (!$('fcBase').value) $('fcBase').value = new Date((res.startLocal + (res.days - 1) * DAY) * 1000).getUTCFullYear();
  const y0 = parseInt($('fcBase').value, 10);
  const annual0 = res.overallAvgDaily * 365, ratio0 = sel.v / annual0;

  const rows = [];
  for (let t = 0; t <= years; t++) {
    const annual = annual0 * (1 + g) ** t, ratio = ratio0 * (1 + rc) ** t, peak = annual * ratio;
    rows.push({ year: y0 + t, annual, ratio, peak, util: cap ? peak / cap : null });
  }
  const satRow = cap ? rows.find(r => r.peak >= cap) : null;
  const warnRow = cap ? rows.find(r => r.peak >= cap * warn) : null;

  const card = (title, value, sub) => `<div class="rounded-lg p-3" style="background:var(--surface-2)"><div class="text-xs font-semibold secondary">${title}</div><div class="text-xl font-bold mt-1 tabnum">${value}</div><div class="text-xs muted mt-1">${sub}</div></div>`;
  if (!cap) {
    $('capCards').innerHTML = card('현재 이용률', '–', '시간당 처리능력을 입력하세요') +
      card('기준 첨두 비율', `${(ratio0 * 100).toFixed(3)}%`, `설계 첨두 ${fmtN(sel.v)}편 ÷ 연간 ${fmtN(annual0, 0)}편`) +
      card(`${y0 + years}년 예측 첨두`, `${fmtN(rows[years].peak)} 편/시간`, `성장률 ${(g * 100).toFixed(1)}%/년 가정`) +
      card('포화 예상 연도', '–', '처리능력 입력 필요');
  } else {
    const st = capStatus(sel.v / cap, warn);
    $('capCards').innerHTML =
      card('현재 이용률', `${(sel.v / cap * 100).toFixed(1)}%`, `${st.icon} ${st.label}`) +
      card('여유 편수', `${fmtN(cap - sel.v)} 편/시간`, `처리능력 ${fmtN(cap)} − 설계 첨두 ${fmtN(sel.v)}`) +
      card(`주의 기준 도달`, warnRow ? `${warnRow.year}년` : `${y0 + years}년 이후`, warnRow ? `예측 첨두 ${fmtN(warnRow.peak)}편 (${Math.round(warn * 100)}%)` : '예측 기간 안에는 도달하지 않음') +
      card('포화 예상 연도', satRow ? `${satRow.year}년` : `${y0 + years}년 이후`, satRow ? `예측 첨두 ${fmtN(satRow.peak)}편 ≥ 처리능력` : '예측 기간 안에는 포화되지 않음');
  }
  $('capNote').textContent = `기준: ${sel.name} ${fmtN(sel.v)}편/시간 · 기준 연간 운항 ${fmtN(annual0, 0)}편(분석 기간 ${res.days}일 일평균 × 365)` +
    (res.days < 365 ? ' · 1년 미만 데이터로 환산한 값이라 계절 변동이 반영되지 않을 수 있습니다.' : '') +
    ' · 처리능력은 공항이 공표한 시간당 운항 용량(슬롯 등)을 입력하세요.';

  const ds = [{ label: '예측 첨두시간 수요', data: rows.map(r => r.peak), borderColor: tc.arr, backgroundColor: tc.arr, borderWidth: 2, pointRadius: 3, pointHoverRadius: 6, tension: 0.2 }];
  if (cap) {
    ds.push({ label: '처리능력', data: rows.map(() => cap), borderColor: tc.primary, borderWidth: 2, pointRadius: 0, borderDash: [6, 4] });
    ds.push({ label: '주의 기준', data: rows.map(() => cap * warn), borderColor: tc.dep, borderWidth: 2, pointRadius: 0, borderDash: [2, 4] });
  }
  const o = baseOptions(tc, { yTitle: '운항 (편/시간)' });
  o.scales.y.beginAtZero = false;
  o.plugins.tooltip.callbacks = { label: c => `${c.dataset.label}: ${fmtN(c.parsed.y)}편/시간` };
  mkChart('fcChart', { type: 'line', data: { labels: rows.map(r => r.year), datasets: ds }, options: o });

  $('fcTable').innerHTML = `<thead><tr><th>연도</th><th class="num">연간 운항</th><th class="num">첨두 비율</th><th class="num">예측 첨두 (편/시간)</th><th class="num">이용률</th><th>상태</th></tr></thead><tbody>` +
    rows.map(r => {
      const st = cap ? capStatus(r.util, warn) : null;
      return `<tr class="${r === satRow ? 'hl' : ''}"><td>${r.year}</td><td class="num">${fmtN(r.annual, 0)}</td><td class="num">${(r.ratio * 100).toFixed(3)}%</td><td class="num">${fmtN(r.peak)}</td><td class="num">${cap ? (r.util * 100).toFixed(1) + '%' : '–'}</td><td>${st ? st.icon + ' ' + st.label : '–'}</td></tr>`;
    }).join('') + '</tbody>';
}

export function renderCAA(res) {
  const typed = parseFloat($('caaAnnual').value);
  const est = res.overallAvgDaily * 365;
  const annual = typed > 0 ? typed : est;
  const { row, out } = caaExpect(annual);
  const rawRank = ranked(res.s.tot);
  const peakDay = res.daily.reduce((a, b) => (b.tot > a.tot ? b : a));
  const peakHour = rawRank[0];
  const sbr = rawRank.length >= 30 ? rawRank[29] : null;
  const avgDay = res.overallAvgDaily;
  const ratio = (act, exp) => (act != null && exp ? `${(act / exp * 100).toFixed(0)}%` : '–');
  const lines = [
    ['평균일 운항', annual / 365, avgDay, '연간 ÷ 365'],
    ['첨두일 운항', row[2], peakDay.tot, `가장 바쁜 날 (${fmtDate(peakDay.ls)})`],
    ['첨두시간 운항', row[4], peakHour?.v, '가장 바쁜 정시 1시간'],
    ['SBR (30번째 바쁜 시간)', row[6], sbr?.v, '단일 정시 운항 30번째']
  ];
  $('caaTable').innerHTML = '<thead><tr><th>항목</th><th class="num">CAA 표 기대값</th><th class="num">이 데이터</th><th class="num">데이터 ÷ 기대값</th><th>데이터 산정 방법</th></tr></thead><tbody>' +
    lines.map(([n, e, a, how]) => `<tr><td>${n}</td><td class="num">${fmtN(e, 0)}</td><td class="num">${fmtN(a, 0)}</td><td class="num"><b>${ratio(a, e)}</b></td><td class="secondary">${how}</td></tr>`).join('') +
    `<tr><td>첨두시간 ÷ SBR</td><td class="num">${(1 / row[5]).toFixed(2)}</td><td class="num">${sbr ? (peakHour.v / sbr.v).toFixed(2) : '–'}</td><td class="num">–</td><td class="secondary">교재 식 (2.1): 절대 첨두 ≈ 1.2 × SBR</td></tr></tbody>`;
  $('caaNote').textContent = `기준 연간 운항 ${fmtN(annual, 0)}편 (${typed > 0 ? '입력값' : `데이터 추정: 일평균 ${fmtN(avgDay)}편 × 365`})` +
    (out === 'low' ? ' · 표의 최소(10,000편)보다 작아 최소 행으로 비교' : out === 'high' ? ' · 표의 최대(500,000편)보다 커서 최대 행으로 비교' : '') +
    (res.days < 360 ? ` · 분석 기간이 ${res.days}일이라 첨두일·SBR은 1년 기준보다 낮게 나올 수 있습니다.` : '') +
    (typed > 0 ? ' · 공식 연간 운항을 넣으면 "데이터 ÷ 기대값"이 OpenSky 수집 누락 정도를 가늠하는 데 도움이 됩니다.' : '');
}

// 산정 기준에 따라 관련 옵션만 표시
const METHOD_HINT = {
  icao_peak: '분석 기간 전체에서 연속 2시간 평균이 가장 큰 값입니다. 시간 창은 정시 기준 또는 15분 간격 이동 60분을 고를 수 있습니다.',
  icao_busy: '연속 2시간 평균을 큰 순서로 세운 N번째 값입니다. ICAO 정의는 연간 40번째(또는 30번째)입니다.',
  nth_hour: '단일 정시 운항을 큰 순서로 세운 N번째 값입니다. §3.4.3 a)는 20·30·40번째를 예로 듭니다. 30번째는 영국·유럽에서 쓰는 SBR(Standard Busy Rate)입니다 (Ashford et al. 2013).',
  adpm: '일평균 운항이 가장 많은 달(또는 연속 2개월)의 평균일(또는 평균 평일) 시간대별 프로파일에서 가장 바쁜 시간입니다. FAA 방식이며, 교재에서는 TPHP(Typical Peak Hour Passengers) 또는 PPH(Peak Profile Hour)라고 부릅니다 (Ashford et al. 2013).',
  iata_sbd: '피크 월의 요일별 평균으로 평균 주를 만들고, 두 번째로 바쁜 요일의 대표일에서 가장 바쁜 시간을 씁니다. IATA 권장 방식입니다. 추가 옵션이 없습니다.',
  pct_day: '일 운항을 기준으로 90 또는 95 백분위에 해당하는 날의 가장 바쁜 시간입니다.',
  pct5: '이보다 바쁜 모든 시간의 누적 운항이 총운항의 5%가 되는 시간입니다. 교재에서는 BHR(Busy-Hour Rate)이라 부르며, SBR의 공항 간 혼잡 수준 차이를 보완하려고 도입되었습니다 (Ashford et al. 2013). 추가 옵션이 없습니다.'
};

export function updateMethodOptions() {
  const m = $('method').value;
  // 순위 N 선택지: ICAO Busy hour 는 정의상 30/40번째, §3.4.3 a) 는 20/30/40번째
  const bn = $('busyN'), cur = bn.value;
  const ns = m === 'icao_busy' ? ['30', '40'] : ['20', '30', '40'];
  bn.innerHTML = ns.map(n => `<option value="${n}">${n}번째</option>`).join('') + '<option value="custom">사용자 지정</option>';
  bn.value = ns.includes(cur) || cur === 'custom' ? cur : '30';
  $('busyNLbl').textContent = m === 'icao_busy' ? 'Busy hour 순위 (연간)' : '바쁜 시간 순위 (연간)';
  $('customN').disabled = bn.value !== 'custom';
  document.querySelectorAll('[data-opt]').forEach(el => {
    const keys = el.dataset.opt.split(' ');
    const show = keys.includes('custom') ? ['icao_busy', 'nth_hour'].includes(m) && bn.value === 'custom' : keys.includes(m);
    el.style.display = show ? '' : 'none';
  });
  $('methodHint').textContent = METHOD_HINT[m] || '';
}

export function setPeak(on) {
  $('peakOn').checked = on;
  document.querySelector('#sideNav [data-pane="peak"]').hidden = !on;
  document.body.classList.toggle('peak-on', on);
  // 설계일을 보고 있다가 끄면 평균으로 (PEAK 일과 같은 날이면 그대로)
  if (!on && STATE.res && TARGET.profile.modes.design && $('profileSel').value === TARGET.profile.modes.design &&
      TARGET.profile.modes.design !== TARGET.profile.modes.peak) $('profileSel').value = 'avg';
  $('peakOpts').hidden = !on;
  $('ch-peak').hidden = !on;
}

export function init() {
  $('method').addEventListener('change', updateMethodOptions);
  updateMethodOptions();
  $('busyN').onchange = () => { updateMethodOptions(); STATE.data && renderAll(); };
  // 첨두시간 산정 스위치: 기준 선택 칸을 사이드바로 옮겨 두고, 켜면 "첨두시간 산정" 장과 목차 항목을 보임
  $('peakOpts').appendChild(document.querySelector('.peak-ctl'));
  $('peakOn').onchange = () => {
    setPeak($('peakOn').checked);
    saveLast();
    syncSideNav();
    if (STATE.data) renderAll();
    if ($('peakOn').checked) setPane('peak', !!STATE.data); else if (PANE === 'peak') setPane(STATE.data ? 'overview' : 'data', false);
  };
  $('caaAnnual').addEventListener('input', () => STATE.res && renderCAA(STATE.res));
  ['capTotal', 'capWarn', 'fcGrowth', 'fcRatio', 'fcYears', 'fcBase'].forEach(id => $(id).addEventListener('input', () => {
    if (!STATE.res) return;
    renderCapacity(STATE.res, STATE.res.methods.find(m => m.id === cfgFromUI().method) || STATE.res.methods[0]);
  }));
}
