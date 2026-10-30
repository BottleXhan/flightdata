// ⚙ 설정 팝업: 버전·업데이트 · 저장 폴더 · 자동 로그인 · 화면 테마.
import { LOGIN_USER } from './login.js';
import { applyUpd, checkUpdate, openUpd } from './update.js';
import { $, showMsg } from '../lib/dom.js';
import { isDark } from '../ui/theme.js';

// ⚙ 설정 (머리 오른쪽): 버전·업데이트 · 저장 폴더 · 자동 로그인 · 화면
const setPop = open => { $('setPop').hidden = !open; $('setBtn').setAttribute('aria-expanded', String(open)); if (open) syncSettings(); };

export function syncSettings() {
  const d = $('cDir').value || '–'; $('setDir').textContent = d.length > 38 ? '…' + d.slice(-37) : d; $('setDir').title = d;
  $('setAuto').checked = $('cRemember').checked; $('setAuto').disabled = $('cRemember').disabled;
  document.querySelectorAll('#setTheme [data-th]').forEach(b => b.setAttribute('aria-pressed', String((b.dataset.th === 'dark') === isDark())));
}

export function init() {
  $('setBtn').onclick = e => { e.stopPropagation(); setPop($('setPop').hidden); };
  document.addEventListener('click', e => { if (!e.target.closest('#setWrap')) setPop(false); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') setPop(false); });
  $('setUpdCheck').onclick = async () => { $('setVerNote').textContent = '확인하는 중…'; await checkUpdate(true); };
  $('setUpdGo').onclick = () => { setPop(false); openUpd(); applyUpd(); };
  $('setDirPick').onclick = () => $('cPickDir').click();
  $('setDirOpen').onclick = () => $('cOpenDir').click();
  $('setAuto').onchange = () => {
    if (LOGIN_USER) { $('cAuto2').checked = $('setAuto').checked; $('cAuto2').dispatchEvent(new Event('change')); }
    else { $('cRemember').checked = $('setAuto').checked; $('cRemember').dispatchEvent(new Event('change')); showMsg($('setAuto').checked ? '자동 로그인: 다음 로그인부터 적용됩니다.' : '자동 로그인을 해제했습니다.'); }
  };
  $('setTheme').onclick = e => {
    const b = e.target.closest('[data-th]'); if (!b) return;
    if ((b.dataset.th === 'dark') !== isDark()) $('themeBtn').click();
    syncSettings();
  };
}
