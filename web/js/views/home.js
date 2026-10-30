// 홈: 바로가기 · 최근 데이터 · 지금 데이터, 처음으로(resetHome).
import { clearCsv, dsTx, req } from '../data/datasets.js';
import { buildYearButtons, quickDays, updateApInfo } from '../data/period.js';
import { COLLECTOR } from '../desktop/collect.js';
import { LOGIN_USER } from '../desktop/login.js';
import { clearFilter, syncFilterUI } from '../filters.js';
import { $, setProgress, setStatus, showMsg } from '../lib/dom.js';
import { DAY, esc, fmtDate } from '../lib/fmt.js';
import { STATE } from '../state.js';
import { amapOpen } from '../ui/airport-map.js';
import { PANE, setPane, syncSideNav } from '../ui/nav.js';
import { libAps, libOpen, libPeriod, libWhen } from './library.js';

/* ---------- ⟲ 처음으로: 불러온 데이터·결과·필터를 비우고 첫 화면(데이터 탭)으로 (사용자 요청) ---------- */
function resetHome() {
  if ($('runBtn').disabled) { showMsg('다운로드 중에는 초기화할 수 없습니다. 먼저 [중지]하세요.', 'warn'); return; }
  STATE.data = STATE.res = STATE.view = null;
  clearCsv();
  $('csvFile').value = ''; $('csvAirportWrap').style.display = 'none';
  $('csvInfo').textContent = 'CSV 선택 시 공항·기간이 자동 입력됩니다.';
  ['fDir', 'fRoute', 'fSize', 'fAl', 'fH'].forEach(id => { try { clearFilter(id); } catch (e) {} });
  syncFilterUI();
  $('results').classList.add('hidden'); $('hrun').hidden = true; $('fChips').hidden = true;
  document.body.classList.remove('has-data');
  $('welcome').hidden = false; $('dvProg').hidden = true; $('cLog').textContent = ''; $('lastNote').hidden = true;
  $('icao').value = ''; $('tz').value = ''; $('apSearch').value = ''; $('apResults').hidden = true;
  quickDays(7); buildYearButtons(); updateApInfo();
  if (COLLECTOR && document.querySelector('#source option[value="collect"]')) $('source').value = 'collect';
  else $('source').value = 'csv';
  $('source').onchange();
  amapOpen(false);
  showMsg(null); setStatus(''); setProgress(null);
  syncSideNav(); setPane('home');
}

// 로고: 홈 화면으로 (보던 데이터는 그대로 — 비우기는 홈의 [데이터 초기화])
const goHome = () => setPane('home');

/* ---------- 홈: 큰 바로가기 + 최근 데이터 + 지금 데이터 ---------- */
export async function renderHome(list) {
  if (!list) { try { list = await dsTx('readonly', st => req(st.getAll())); } catch (e) { list = []; } }
  list = [...list].sort((a, b) => b.savedAt - a.savedAt);
  $('haLibD').textContent = list.length ? `저장된 데이터 ${list.length}건 · 관리 및 재분석` : '다운로드·가져온 데이터가 자동 저장됩니다';
  $('homeRecent').innerHTML = list.length ? list.slice(0, 6).map(r => {
    const [a, b] = libPeriod(r);
    return `<button type="button" data-hopen="${esc(r.id)}"><span class="aps">${esc(libAps(r).join(', '))}</span><span>${esc(r.name || (a ? `${a} ~ ${b}` : r.label))}<small>${r.flights ? r.flights.toLocaleString() + '편 · ' : ''}${esc(r.note || r.files.map(f => f.name).join(', '))}</small></span><em>${libWhen(r.savedAt)}</em></button>`;
  }).join('') : '<p class="home-empty">저장된 데이터가 없습니다. [데이터 다운로드] 또는 [CSV 가져오기]로 시작하세요.</p>';
  const D = STATE.data;
  $('homeNowBody').innerHTML = D
    ? `<p style="margin:0 0 16px"><span class="apcode" style="font-size:1rem;padding:.05rem .45rem;border-radius:6px">${esc(D.airport)}</span>
        <b style="margin-left:8px">${fmtDate(D.startLocal)} ~ ${fmtDate(D.startLocal + (D.days - 1) * DAY)}</b> · ${D.days}일 · 운항 ${D.movements.length.toLocaleString()}편</p>
       <div class="flex flex-wrap gap-2"><button class="btn btn-primary" type="button" data-hgo="overview">개요</button><button class="btn" type="button" data-hgo="profile">운항량</button><button class="btn" type="button" data-hgo="mix">운항 구성</button><button class="btn" type="button" data-hreset title="불러온 데이터·결과·필터 초기화">데이터 초기화</button></div>`
    : '<p class="home-empty">분석 중인 데이터가 없습니다.</p>';
  const v = $('brandVer').textContent; $('homeVer').textContent = v || '';
  $('homeStatus').innerHTML = COLLECTOR
    ? (LOGIN_USER ? `<span style="color:#2fa66a">●</span> <b>${esc(LOGIN_USER)}</b>` : '로그아웃 상태<br><span class="text-xs muted">우측 상단에서 로그인</span>')
    : '웹 버전 · CSV 분석<br><span class="text-xs muted">다운로드는 FlightData 프로그램에서 지원</span>';
  if (!COLLECTOR) { $('haCollectT').textContent = 'CSV 데이터 분석'; $('haCollectD').textContent = '공항·기간 선택 후 CSV 분석'; }
}

export function init() {
  $('homeView').addEventListener('click', e => {
    const b = e.target.closest('[data-home],[data-hopen],[data-hgo],[data-hreset]'); if (!b) return;
    if (b.dataset.hopen) return libOpen([b.dataset.hopen]);
    if (b.dataset.hgo) return setPane(b.dataset.hgo);
    if ('hreset' in b.dataset) return resetHome();
    const a = b.dataset.home;
    if (a === 'collect') { if (COLLECTOR && document.querySelector('#source option[value="collect"]')) { $('source').value = 'collect'; $('source').onchange(); } setPane('data'); }
    if (a === 'lib') setPane('lib');
    if (a === 'csv') { $('source').value = 'csv'; $('source').onchange(); $('csvFile').click(); }
    if (a === 'demo') $('demoBtn').click();
  });
  $('csvFile').addEventListener('change', () => { if (PANE === 'home' && $('csvFile').files.length) setPane('data'); });
  document.querySelector('.brand').style.cursor = 'pointer';
  document.querySelector('.brand').title = '홈으로';
  document.querySelector('.brand').onclick = goHome;
}
