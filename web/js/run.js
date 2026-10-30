// 분석 실행 흐름: [분석 시작]/[다운로드 시작] → 운항 불러오기 → 분석 → 모든 화면 다시 그리기(renderAll).
import { loadMapData } from './data/airports.js';
import { CSV_NAMES, csvFlights } from './data/datasets.js';
import { apCode, buildYearButtons, MAX_DAYS, offsetFor, updateSpan } from './data/period.js';
import { collectInApp } from './desktop/collect.js';
import { flightsToMovements } from './engine/csv.js';
import { generateDemo } from './engine/demo.js';
import { analyze } from './engine/peak.js';
import { yearGroups } from './engine/stats.js';
import { applyFilters, buildFilterOptions } from './filters.js';
import { $, setProgress, setStatus, showMsg } from './lib/dom.js';
import { dateToLocalSec, DAY, esc, fmtDate, fmtN, fmtPct, HOUR } from './lib/fmt.js';
import { STATE } from './state.js';
import { PANE, setPane, setSide, syncSideNav } from './ui/nav.js';
import { saveLast } from './ui/session.js';
import { renderAirlinesRoutes, renderTypes } from './views/mix.js';
import { renderOverviewExtras, renderStats } from './views/overview.js';
import { cfgFromUI, renderCAA, renderCapacity, renderMethodTable, renderRank, renderRatios, renderSplit } from './views/peak.js';
import { buildProfileOptions, buildWdOptions, ptab, renderProfileTab, setPtab } from './views/profile.js';

export function renderAll() {
  const movements = applyFilters(STATE.data.movements);
  if (!movements.length) {
    showMsg('현재 필터 조건에 해당하는 운항이 없습니다. 필터 조건을 조정하세요.', 'err');
    return;
  }
  showMsg(null);
  STATE.view = { ...STATE.data, movements };
  const res = STATE.res = analyze(STATE.view, cfgFromUI());
  const cfg = cfgFromUI();
  const sel = res.methods.find(m => m.id === cfg.method) || res.methods[0];
  const peak = res.methods.find(m => m.id === 'icao_peak');
  const busy = res.methods.find(m => m.id === 'icao_busy');

  $('results').classList.remove('hidden');
  $('welcome').hidden = true;
  // 상단 바 목차는 사용자 요청으로 쓰지 않음 (사이드바 목차만) — 그 자리에 공항·기간(#hrun)
  $('hrun').hidden = false;
  $('demoNote').hidden = STATE.data.source !== 'demo';
  $('sumAirport').textContent = STATE.data.airport;
  $('sumPeriod').textContent = `${fmtDate(STATE.data.startLocal)} ~ ${fmtDate(STATE.data.startLocal + (STATE.data.days - 1) * DAY)} · ${STATE.data.days}일`;
  $('sumMeta').textContent = `운항 ${STATE.view.movements.length.toLocaleString()}편` + (movements.length !== STATE.data.movements.length ? ` (전체 ${STATE.data.movements.length.toLocaleString()}편 중 필터)` : '') +
    ` · ${{ demo: '데모 데이터', csv: 'CSV (OpenSky Trino)', collect: 'OpenSky에서 받음' }[STATE.data.source]} · UTC${STATE.data.offsetH >= 0 ? '+' : ''}${STATE.data.offsetH}`;
  $('kMethodBadge').textContent = { icao_peak: 'ICAO Peak', icao_busy: 'ICAO Busy', nth_hour: '§3.4.3 a', adpm: '§3.4.3 b', iata_sbd: '§3.4.3 c', pct_day: '§3.4.3 d', pct5: '§3.4.3 e' }[sel.id];
  $('kDesign').innerHTML = `${fmtN(sel.v)} <span class="text-sm font-medium muted">편/시간</span>`;
  $('kDesignSub').textContent = `${sel.when} · 도착 ${fmtN(sel.arr)} / 출발 ${fmtN(sel.dep)}`;
  $('kPeak').innerHTML = peak ? `${fmtN(peak.v)} <span class="text-sm font-medium muted">편/시간</span>` : '–';
  $('kPeakSub').textContent = peak ? `2시간 평균 최대 · ${peak.when}` : '';
  $('kBusyLbl').textContent = `Busy Hour Demand (${res.N}번째)`;
  $('kBusy').innerHTML = busy ? `${fmtN(busy.v)} <span class="text-sm font-medium muted">편/시간</span>` : '–';
  $('kBusySub').textContent = busy ? `${res.N}개 시간대에서 도달·초과 · Peak 대비 ${fmtPct(busy.v / peak.v)}` : '';
  $('kConc').textContent = fmtPct(sel.conc);
  $('kConcSub').textContent = `설계일 총 ${fmtN(sel.dayTotal, 0)}편 대비 · 기간 일평균(${fmtN(res.overallAvgDaily)}편) 대비 ${fmtPct(sel.concAvg)}`;

  renderSplit(res);
  renderMethodTable(res, sel.id);
  buildProfileOptions(res, sel);
  buildWdOptions(res);
  // 연별 탭: 두 해 이상일 때만 (보고 있었는데 한 해가 되면 시간대별로)
  const multiYear = yearGroups(res).length > 1, yTab = document.querySelector('[data-ptab="year"]');
  yTab.hidden = !multiYear;
  if (!multiYear && ptab === 'year') { setPtab('hour'); document.querySelectorAll('[data-ptab]').forEach(x => x.setAttribute('aria-selected', String(x.dataset.ptab === 'hour'))); }
  renderProfileTab();                 // 운항 프로파일: 보이는 탭만 그림 (숨은 캔버스는 크기가 0)
  syncSideNav();
  renderRank(res);
  renderRatios(res, sel);
  renderCapacity(res, sel);
  renderCAA(res);
  renderTypes(res, sel);
  renderStats(res);
  setTimeout(() => renderOverviewExtras(res));
  renderAirlinesRoutes();
}

export async function run() {
  showMsg(null);
  await loadMapData();
  const airport = apCode();
  const sd = $('startDate').value, ed = $('endDate').value;
  const offsetH = offsetFor(airport, sd);
  if (!/^[A-Z0-9]{4}$/.test(airport)) return showMsg('ICAO 공항 코드는 4자리 영문/숫자입니다 (예: RKSI).', 'err');
  if (!sd || !ed || ed < sd) return showMsg('분석 기간을 올바르게 입력하세요.', 'err');
  const startLocal = dateToLocalSec(sd);
  const days = Math.round((dateToLocalSec(ed) - startLocal) / DAY) + 1;
  if (days > MAX_DAYS) return showMsg(`분석 기간은 최대 ${MAX_DAYS.toLocaleString()}일(약 10년)입니다. "연도 선택"으로 기간을 줄이세요.`, 'err');
  const beginUtc = startLocal - offsetH * HOUR, endUtc = startLocal + days * DAY - offsetH * HOUR;
  const source = $('source').value;

  const warnings = [];
  if (days < 7) warnings.push('분석 기간이 7일 미만이면 IATA 평균 주(week) 구성이 불완전합니다.');
  if (days > 366 && $('peakOn').checked) warnings.push('여러 해 기간입니다. 첨두시간 순위(30번째 등)는 기간 전체에서 센 값이라 연간 기준과 다릅니다. 연도별 값은 "연도 선택"으로 한 해씩 보세요.');
  if (days < 360 && $('peakOn').checked) warnings.push(`ICAO Busy hour·N번째 바쁜 시간은 연간(1년) 기준입니다. 지금은 ${days}일 안에서의 순위라 1년치로 분석할 때보다 값이 낮게 나올 수 있습니다.`);

  $('runBtn').disabled = true; setProgress(0);
  try {
    let movements;
    if (source === 'demo') { setStatus('데모 데이터 생성 중…'); movements = generateDemo(airport, startLocal, days, offsetH); setProgress(1); }
    else if (source === 'collect') movements = await collectInApp(airport, beginUtc, endUtc, sd, ed, offsetH);
    else if (source === 'csv') {
      if (!csvFlights) throw new Error('CSV 파일을 먼저 선택하세요.');
      movements = flightsToMovements(csvFlights, airport, beginUtc, endUtc); setProgress(1);
    }
    if (!movements.length) throw new Error('해당 기간에 운항이 없습니다. 공항 코드·기간·CSV 파일을 확인하세요.');
    STATE.data = { airport, offsetH, startLocal, days, movements, source };
    buildFilterOptions();
    STATE.keepProfile = false;
    renderAll();
    STATE.keepProfile = true;
    $('recalcBtn').disabled = false;
    setStatus(`${airport} · ${days}일 · 운항 ${movements.length.toLocaleString()}편 분석 완료${source === 'demo' ? ' (데모)' : ''}`);
    saveLast({ files: source === 'csv' ? CSV_NAMES : [] });
    $('lastNote').hidden = true;
    document.body.classList.add('has-data');
    if (PANE === 'data' || PANE === 'home') setPane('overview');
    if (warnings.length) showMsg(warnings.map(esc).join('<br>'));
    if (innerWidth < 1024) { setSide(false, false); $('ch-overview').scrollIntoView({ block: 'start' }); }   // 좁은 화면: 설정 아래 결과로 이동
  } catch (e) {
    console.error(e);
    setStatus('');
    showMsg(esc(e.message), e.stopped ? 'warn' : 'err');
  } finally {
    $('runBtn').disabled = false; setTimeout(() => setProgress(null), 600);
  }
}

export function init() {
  $('runBtn').onclick = run;
  $('recalcBtn').onclick = () => STATE.data && renderAll();
  ['method', 'window', 'customN', 'adpmDays', 'adpmSpan', 'pct'].forEach(id => $(id).addEventListener('change', () => STATE.data && renderAll()));
  $('source').onchange = () => {
    $('csvOpts').style.display = $('source').value === 'csv' ? '' : 'none';
    $('collectOpts').style.display = $('source').value === 'collect' ? '' : 'none';
    const src = $('source').value;
    $('runBtn').textContent = src === 'collect' ? '다운로드 시작' : '분석 시작';
    $('dvTitle').textContent = { collect: 'OpenSky 데이터 다운로드', csv: 'CSV 데이터 분석', demo: '데모 데이터' }[src] || '데이터 보기';
    $('dvGoName').textContent = src === 'collect' ? '다운로드' : '분석';
    $('dvSub').textContent = { collect: '공항·기간 선택 후 다운로드 — CSV 저장 및 자동 분석', csv: '왼쪽에서 CSV 선택 시 공항·기간 자동 입력', demo: '합성 운항 스케줄 · 공항·기간 제한 없음' }[src] || '';
    $('dvOpts').hidden = src !== 'collect';
    buildYearButtons();
  };
  // 데모로 둘러보기: 지난해 1년치 합성 데이터
  $('demoBtn').onclick = () => {
    const y = new Date().getFullYear() - 1;
    $('source').value = 'demo'; $('source').onchange();
    $('startDate').value = `${y}-01-01`; $('endDate').value = `${y}-12-31`;
    updateSpan();
    run();
  };
}
