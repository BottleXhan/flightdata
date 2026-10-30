// 프로그램(exe) 안에서만: 로컬 서버 확인, 'OpenSky에서 받기' 화면 준비와 다운로드 진행.
import { csvFlights, onCsvSelected } from '../data/datasets.js';
import { updateSpan } from '../data/period.js';
import { doLogin, LOGIN_USER, showLogin } from './login.js';
import { syncSettings } from './settings.js';
import { checkUpdate } from './update.js';
import { flightsToMovements } from '../engine/csv.js';
import { $, apiPost, setProgress, setStatus, showMsg } from '../lib/dom.js';
import { esc } from '../lib/fmt.js';
import { run } from '../run.js';

export let COLLECTOR = false;

function setupCollectUI(info) {
  const opt = document.createElement('option');
  opt.value = 'collect'; opt.textContent = 'OpenSky에서 받기';
  $('source').prepend(opt);
  const st = info.settings || {};
  $('hLogin').hidden = false;
  if (info.inTemp) showMsg('<b>압축 파일 내부에서 실행 중입니다.</b> 이 상태에서는 CSV·설정·보관함이 임시 폴더에 저장되어 유실됩니다. 프로그램을 종료하고 zip <b>압축 해제 후</b> 폴더 안의 FlightData exe를 실행하세요.', 'err');
  if (info.version) { $('brandVer').textContent = info.version; $('brandVer').hidden = false; document.title = `FlightData ${info.version}`; }
  document.querySelectorAll('.app-only').forEach(el => { el.hidden = false; });
  $('setVer').textContent = `FlightData_${info.version || '?'}`;
  setTimeout(() => checkUpdate(false), 8000);              // 화면이 다 뜬 뒤 조용히 새 버전 확인 (시작 부담 줄임)
  if (st.user) $('cUser').value = st.user;
  $('cRemember').checked = st.remember === true; $('cRemember').disabled = !info.canRemember;   // 자동 로그인: 처음엔 꺼짐 (사용자 요청)
  $('cSplit').checked = st.split !== false; $('cAircraft').checked = st.aircraft !== false;
  $('cDir').value = st.outDir || '';
  $('hLoginForm').onsubmit = e => { e.preventDefault(); doLogin(); };
  // 로그인한 뒤에도 자동 로그인을 켜고 끔
  $('cAuto2').onchange = async () => {
    const on = $('cAuto2').checked; $('cRemember').checked = on;
    const r = await apiPost('/api/autologin', { on }).catch(() => null), j = r ? await r.json().catch(() => ({})) : {};
    if (!r?.ok) { $('cAuto2').checked = $('cRemember').checked = !on; return showLogin(LOGIN_USER, j.error || '자동 로그인 설정을 변경하지 못했습니다', true); }
    showLogin(LOGIN_USER, on ? '자동 로그인 사용 — 다음 실행 시 자동으로 로그인합니다' : '자동 로그인 해제 (저장된 비밀번호 삭제)');
    setTimeout(() => { if (LOGIN_USER) $('hLoginMsg').hidden = true; }, 3500);
  };
  $('cRemember').addEventListener('change', () => { $('cAuto2').checked = $('cRemember').checked; });
  $('hLogout').onclick = async () => {
    await apiPost('/api/logout', { forget: true }).catch(() => {});
    showLogin(null, '로그아웃 완료 (저장된 비밀번호 삭제)');
  };
  if (info.loggedIn) showLogin(info.loggedIn);
  else if (st.remember === true && info.pwSaved && st.user) doLogin(true);   // 자동 로그인을 켜 둔 경우에만 열 때 로그인
  else showLogin(null);
  $('cOpenDir').onclick = $('cOpenDir2').onclick = () => apiPost('/api/open-folder', { dir: $('cDir').value });
  // 저장 폴더 바꾸기: 프로그램 창의 폴더 고르기 창 (pywebview js_api). 직접 고쳐 넣어도 저장됨
  const setDir = async d => {
    const r = await apiPost('/api/settings', { outDir: d }), j = await r.json().catch(() => ({}));
    $('cDirMsg').hidden = false; $('cDirMsg').classList.toggle('err', !r.ok);
    $('cDirMsg').textContent = r.ok ? `저장 폴더 변경 완료 — 다음 다운로드부터 ${j.outDir} 에 저장됩니다` : (j.error || '이 폴더를 쓸 수 없습니다');
    if (r.ok) { $('cDir').value = $('cDir').dataset.ok = j.outDir; syncSettings(); }
    else if ($('cDir').dataset.ok) $('cDir').value = $('cDir').dataset.ok;   // 못 쓰는 폴더면 원래대로
  };
  $('cDir').dataset.ok = $('cDir').value;
  $('cPickDir').onclick = async () => {
    const api = window.pywebview?.api;
    if (!api?.choose_folder) { $('cDir').focus(); $('cDir').select(); $('cDirMsg').hidden = false; $('cDirMsg').textContent = '폴더 경로 입력 후 Enter'; return; }
    const d = await api.choose_folder($('cDir').value);
    if (d) setDir(d);
  };
  $('cDir').addEventListener('change', () => $('cDir').value.trim() && setDir($('cDir').value.trim()));
  // 회원가입 안내 (OpenSky 계정)
  const signup = open => { $('hSignupPop').hidden = !open; $('hSignup').setAttribute('aria-expanded', String(open)); };
  $('hSignup').onclick = () => signup($('hSignupPop').hidden);
  $('hSignupClose').onclick = () => signup(false);
  $('hSignupGo').onclick = () => apiPost('/api/open-url', { url: 'https://opensky-network.org/' });
  document.addEventListener('click', e => { if (!e.target.closest('#hSignupPop, #hSignup')) signup(false); });
  $('cStop').onclick = () => { apiPost('/api/collect/stop'); $('cStop').disabled = true; dvProg({ state: '중지 처리 중', text: '진행 중인 조회를 취소하는 중…' }); };
  $('cLogCopy').onclick = () => navigator.clipboard?.writeText($('cLog').textContent);
  $('source').value = 'collect'; $('source').onchange();
  $('kitGuide').hidden = true;                          // 이 프로그램 안에서는 "수집기 받기" 안내가 필요 없음
  $('kitBtn2').hidden = true;
  $('welcome').classList.add('in-app');
}

/** 데이터 탭의 큰 진행 막대 · 기록 */
function dvProg({ state, text, p } = {}) {
  $('dvProg').hidden = false;
  if (state) { $('dvpState').textContent = state; $('dvProg').dataset.state = state; }
  if (text != null) $('dvpText').textContent = text;
  if (p != null) { $('dvpBar').style.width = (p * 100).toFixed(1) + '%'; $('dvpPct').textContent = Math.floor(p * 100) + '%'; }
}

export async function collectInApp(airport, beginUtc, endUtc, sd, ed, offsetH) {
  const user = LOGIN_USER || $('cUser').value.trim();
  if (!user) { $('cUser').focus(); throw new Error('우측 상단에서 OpenSky 로그인 후 진행하세요.'); }
  const r = await apiPost('/api/collect', { user, password: '', remember: $('cRemember').checked, airport, start: sd, end: ed, tz: offsetH,
    split: $('cSplit').checked, aircraft: $('cAircraft').checked, outDir: $('cDir').value });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `다운로드를 시작하지 못했습니다 (HTTP ${r.status})`);
  $('cStop').disabled = false; $('cLog').textContent = '';
  dvProg({ state: '다운로드 중', text: `${airport} · ${sd} ~ ${ed} · 준비 중…`, p: 0 });
  $('dvProg').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  let since = 0, st;
  for (;;) {                                              // 진행 지켜보기
    await new Promise(ok => setTimeout(ok, 700));
    st = await (await fetch('/api/collect/status?since=' + since, { cache: 'no-store' })).json();
    if (st.log.length) { $('cLog').textContent += st.log.join('\n') + '\n'; $('cLog').scrollTop = 1e9; since = st.logLen; }
    if (st.n) { setProgress(st.i / st.n); dvProg({ p: st.i / st.n }); }
    const t = st.authUrl ? '브라우저에 OpenSky 로그인 창이 열렸습니다. 로그인하면 이어집니다.' : `${airport} · ${st.text}`;
    setStatus(t); dvProg({ text: t });
    if (st.state !== 'running') break;
  }
  $('cStop').disabled = true;
  const files = st.results.length;
  if (st.state === 'stopped') {
    dvProg({ state: '중지됨', text: '중지됨 — 재실행 시 완료된 날짜는 건너뜁니다' });
    const e = new Error('다운로드를 중지했습니다. [다운로드 시작]으로 재실행하면 완료된 날짜는 건너뛰고 이어서 진행합니다.'); e.stopped = true;
    if (!files) throw e;
  } else dvProg(st.state === 'error' ? { state: files ? '부분 완료' : '오류', text: st.error || '' } : { state: '완료', text: `CSV ${files}개 저장 완료 · 분석 화면으로 이동합니다`, p: 1 });
  if (st.state === 'error' && !files) throw new Error(st.error || '다운로드 오류');
  // 받은 CSV 를 불러와(이 브라우저에도 저장) 분석
  const info = await (await fetch('/api/collector', { cache: 'no-store' })).json();
  const fl = [];
  for (let i = 0; i < info.files.length; i++) fl.push(new File([await (await fetch(`/csv/${i}`, { cache: 'no-store' })).text()], info.files[i], { type: 'text/csv' }));
  await onCsvSelected(fl);
  $('startDate').value = sd; $('endDate').value = ed; updateSpan();
  if (st.state === 'error') showMsg(esc(`일부만 다운로드되었습니다: ${st.error}`), 'err');
  if (!csvFlights) throw new Error('다운로드한 CSV를 읽지 못했습니다.');
  return flightsToMovements(csvFlights, airport, beginUtc, endUtc);
}

export async function detectCollector() {
  if (!['localhost', '127.0.0.1'].includes(location.hostname)) return false;
  try {
    const r = await fetch('/api/collector', { cache: 'no-store' });
    if (!r.ok) return false;
    const info = await r.json();
    COLLECTOR = true;
    if (info.app) { setupCollectUI(info); return true; }   // 프로그램: 처음엔 데이터 탭 + "OpenSky에서 받기" (사용자 요청)
    if (!info.files?.length) return true;
    setStatus('수집기에서 받은 CSV 불러오는 중…');
    const files = [];
    for (let i = 0; i < info.files.length; i++) {
      const t = await (await fetch(`/csv/${i}`, { cache: 'no-store' })).text();
      files.push(new File([t], info.files[i], { type: 'text/csv' }));
    }
    $('source').value = 'csv'; $('source').onchange();
    await onCsvSelected(files);
    $('csvInfo').textContent = '수집기에서 불러옴 · ' + $('csvInfo').textContent;
    if (csvFlights) run();
  } catch (e) { console.warn(e); }
  return true;
}
