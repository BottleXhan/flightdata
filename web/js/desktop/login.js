// 프로그램(exe) 안에서만: 머리 오른쪽 OpenSky 로그인 (비밀번호는 서버에만, 화면엔 없음).
import { $ } from '../lib/dom.js';
import { PANE } from '../ui/nav.js';
import { renderHome } from '../views/home.js';

export let LOGIN_USER = null, LOGIN_BUSY = false;                                   // 머리의 OpenSky 로그인 (비밀번호는 프로그램 쪽에만, 화면에는 없음)

export function showLogin(user, msg = '', err = false) {
  LOGIN_USER = user || null;
  $('hLoginForm').hidden = !!user; $('hLoginOn').hidden = !user;
  $('hLoginUser').textContent = user || '';
  $('cAuto2').checked = $('cRemember').checked;
  $('hLoginMsg').textContent = msg; $('hLoginMsg').hidden = !msg; $('hLoginMsg').classList.toggle('err', err);
  if (PANE === 'home') renderHome();
}

export async function doLogin(auto = false) {
  const user = $('cUser').value.trim();
  if (!user) { $('cUser').focus(); return showLogin(null, 'OpenSky 사용자명을 입력하세요.', true); }
  if (LOGIN_BUSY) return;                                  // 로그인 중에 다시 누르지 않게
  LOGIN_BUSY = true;
  $('hLoginBtn').disabled = true; $('hLoginForm').classList.add('busy'); $('hLoginBtn').textContent = '로그인 중…';
  showLogin(null, (auto ? '자동 로그인 중' : 'OpenSky 인증 중') + ' — 잠시 기다려 주십시오');
  $('hLoginMsg').insertAdjacentHTML('afterbegin', '<span class="hl-spin" aria-hidden="true"></span>');
  const ac = new AbortController(), to = setTimeout(() => ac.abort(), 45000);
  try {
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: ac.signal,
      body: JSON.stringify({ user, password: $('cPw').value, remember: $('cRemember').checked }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    $('cPw').value = '';
    showLogin(j.user, j.saved ? '자동 로그인 사용 — 다음 실행 시 자동으로 로그인합니다' : '');
    setTimeout(() => { if (LOGIN_USER) $('hLoginMsg').hidden = true; }, 3500);
  } catch (e) {
    const m = e.name === 'AbortError' ? 'OpenSky 응답 없음 — 네트워크 연결을 확인한 뒤 다시 시도하세요.' : e.message;
    showLogin(null, auto ? `자동 로그인 실패: ${m}` : m + ' — 비밀번호 로그인을 지원하지 않는 계정은 비밀번호 없이 다운로드하면 브라우저 로그인 창이 열립니다.', true);
  } finally {
    clearTimeout(to); LOGIN_BUSY = false;
    $('hLoginBtn').disabled = false; $('hLoginForm').classList.remove('busy'); $('hLoginBtn').textContent = '로그인';
  }
}
