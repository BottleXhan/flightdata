// 라이트/다크 테마와 프로그램 창 제목줄 색.
import { $ } from '../lib/dom.js';
import { renderAll } from '../run.js';
import { STATE } from '../state.js';
import { amapDraw } from './airport-map.js';

// 테마 전환 (차트 색상은 CSS 변수에서 다시 읽어 재렌더)
// 테마 아이콘: 라이트 모드에서는 달(다크로 전환), 다크 모드에서는 해(라이트로 전환)
const ICON_MOON = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
const ICON_SUN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';

export function isDark() {
  const r = document.documentElement;
  return r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
}

/** 프로그램 창(exe)의 맨 위 제목 표시줄도 밝게/어둡게에 맞춤 — Windows DWM (pywebview js_api) */
function syncTitleBar() {
  const api = window.pywebview?.api; if (!api?.set_theme) return;
  const cs = getComputedStyle(document.querySelector('.topbar'));
  api.set_theme(isDark(), cs.backgroundColor, getComputedStyle(document.body).color).catch?.(() => {});
}

function syncThemeIcon() {
  const b = document.getElementById('themeBtn'), dark = isDark();
  b.innerHTML = dark ? ICON_SUN : ICON_MOON;
  b.title = b.ariaLabel = dark ? '라이트 모드로 전환' : '다크 모드로 전환';
  setTimeout(syncTitleBar, 30);
}

export function init() {
  window.addEventListener('pywebviewready', () => setTimeout(syncTitleBar, 50));
  $('themeBtn').onclick = () => {
    document.documentElement.dataset.theme = isDark() ? 'light' : 'dark';
    syncThemeIcon();
    amapDraw();
    if (STATE.data) renderAll();
  };
  syncThemeIcon();
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { syncThemeIcon(); amapDraw(); if (STATE.data) renderAll(); });
}
