// 사이드바 목차와 장 전환(setPane), 사이드바 열기/닫기.
import { $ } from '../lib/dom.js';
import { STATE } from '../state.js';
import { amapDraw } from './airport-map.js';
import { renderHome } from '../views/home.js';
import { renderDisk, renderLib } from '../views/library.js';
import { renderAirlinesRoutes, renderTypes } from '../views/mix.js';
import { renderOverviewExtras } from '../views/overview.js';
import { cfgFromUI } from '../views/peak.js';
import { ptab, PVIEW_NAME, renderProfileTab } from '../views/profile.js';

/* ---------- 사이드바 목차: 누르면 그 장으로 이동하고, 사이드바 내용도 그 장에 맞게 바꿈 ----------
   공항 개요 = 데이터·공항·기간·첨두 스위치 / 운항 프로파일 = 보기 탭 + 필터 / 운항 구성 = 바로 가기 + 필터 / 첨두시간 산정 = 기준 */
const PANE_TARGET = { home: 'homeView', data: 'dataView', lib: 'libView', overview: 'ch-overview', profile: 'sec-profile', mix: 'ch-mix', peak: 'ch-peak' };
export let PANE = 'home';

export function setPane(name, scroll = true) {
  const btn = document.querySelector(`#sideNav [data-pane="${name}"]`);
  if (!btn || btn.disabled || btn.hidden) name = 'home';
  PANE = name;
  document.querySelectorAll('#sideNav [data-pane]').forEach(b => b.setAttribute('aria-current', String(b.dataset.pane === name)));
  document.querySelectorAll('[data-spane]').forEach(el => { el.hidden = el.dataset.spane !== name; });
  const host = document.querySelector(`[data-filterhost="${name}"]`);   // 필터는 프로파일·구성에서 함께 씀
  if (host) { host.appendChild($('filterStep')); $('filterStep').hidden = false; } else $('filterStep').hidden = true;
  $('sidePanel').scrollTop = 0;
  // 오른쪽 본문도 그 장만 보이게 + 상단 바 표시
  $('results').dataset.view = name;
  $('mainView').dataset.pane = name;
  if (name === 'data') amapDraw();
  if (name === 'lib') { renderLib(); renderDisk(); }
  if (name === 'home') renderHome();
  if (name === 'overview' && STATE.res) renderOverviewExtras(STATE.res);
  if (STATE.res) {                       // 숨어 있던 동안 크기 0 으로 그려진 그림을 다시 그림
    if (name === 'profile') renderProfileTab();
    if (name === 'mix') { renderAirlinesRoutes(); renderTypes(STATE.res, STATE.res.methods.find(m => m.id === cfgFromUI().method) || STATE.res.methods[0]); }
  }
  if (scroll) window.scrollTo({ top: 0, behavior: 'auto' });
}

/** 결과가 생기면 목차를 켜고, 연별 탭·첨두 항목·현재 보기 탭을 맞춤 */
export function syncSideNav() {
  const has = !!STATE.data;
  document.querySelector('#sideNav [data-pane="overview"]').disabled = !has;
  document.querySelector('#sideNav [data-pane="profile"]').disabled = !has;
  document.querySelector('#sideNav [data-pane="mix"]').disabled = !has;
  document.querySelector('#sideNav [data-pane="peak"]').hidden = !$('peakOn').checked;
  document.querySelector('[data-ppick="year"]').hidden = document.querySelector('[data-ptab="year"]').hidden;
  document.querySelectorAll('[data-ppick]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.ppick === ptab)));
  $('pViewName').textContent = '· ' + (PVIEW_NAME[ptab] || '');
}

// 왼쪽 분석 설정 열기/닫기 (PC 에서는 선택을 기억, 휴대폰에서는 분석 후 자동으로 닫힘)
export function setSide(open, remember = true) {
  document.body.classList.toggle('side-closed', !open);
  $('sideBtn').setAttribute('aria-expanded', String(open));
  $('sideBtn').title = open ? '분석 설정 닫기' : '분석 설정 열기';
  $('sideBtnArrow').setAttribute('d', open ? 'M15 10l-2 2 2 2' : 'M13 10l2 2-2 2');
  if (remember && innerWidth >= 1024) try { localStorage.setItem('sideOpen', open ? '1' : '0'); } catch (e) {}
}

export function init() {
  $('sideNav').onclick = e => { const b = e.target.closest('[data-pane]'); if (b && !b.disabled) setPane(b.dataset.pane); };
  $('sProfTabs').onclick = e => {
    const b = e.target.closest('[data-ppick]'); if (!b) return;
    if (PANE !== 'profile') setPane('profile');
    document.querySelector(`[data-ptab="${b.dataset.ppick}"]`).click();
    syncSideNav();
  };
  document.querySelectorAll('[data-ptab]').forEach(b => b.addEventListener('click', () => setTimeout(syncSideNav)));
  document.querySelectorAll('[data-goto-pane]').forEach(b => { b.onclick = () => setPane(b.dataset.gotoPane); });
  $('sideBtn').onclick = () => {
    const open = document.body.classList.contains('side-closed');
    setSide(open);
    if (open && innerWidth < 1024) $('sidePanel').scrollIntoView({ block: 'start' });
  };
  try { if (innerWidth >= 1024 && localStorage.getItem('sideOpen') === '0') setSide(false, false); } catch (e) {}
}
