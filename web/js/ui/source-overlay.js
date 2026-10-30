// ICAO 원문 페이지(icao-source.html)를 겹친 창으로 열기 — 프로그램 안에서는 웹 링크로.
import { COLLECTOR } from '../desktop/collect.js';
import { $ } from '../lib/dom.js';

/* ---------- 수집기(exe) 안에서 열린 경우: 방금 받은 CSV 를 자동으로 불러와 분석 ----------
   FlightData 수집기가 127.0.0.1 에서 이 페이지를 제공하고 /api/collector · /csv/<번호> 를 연다. */
const WEB_URL = 'https://claude.ai/artifact/HUBvzfeuXAMq794VBkYPn5';

// ICAO 원문: 페이지를 떠나지 않고 위에 겹쳐 연다 → "돌아가기"는 겹친 창만 닫아 보던 화면·불러온 데이터가 그대로 남음
function syncSourceTheme() {
  try {
    const w = $('srcFrame').contentWindow, r = w.document.documentElement, t = document.documentElement.dataset.theme;
    if (t) r.dataset.theme = t; else delete r.dataset.theme;
    w.syncThemeIcon && w.syncThemeIcon();
  } catch (e) {}
}

function openSource(href) {
  const f = $('srcFrame'), want = new URL(href, location.href).href;
  if (f.src !== want) f.src = want;
  $('srcOverlay').hidden = false;
  document.body.style.overflow = 'hidden';
  syncSourceTheme();
  setTimeout(() => { try { f.contentWindow.focus(); } catch (e) {} }, 50);
}

export function init() {
  window.closeSource = () => {
    $('srcOverlay').hidden = true;
    document.body.style.overflow = '';
  };
  $('srcFrame').addEventListener('load', syncSourceTheme);
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href^="icao-source.html"]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey) return;     // Ctrl+클릭 등은 새 탭으로 그대로
    e.preventDefault();
    if (COLLECTOR) { window.open(WEB_URL, '_blank', 'noopener'); return; }   // 수집기 안에는 원문 페이지가 없음 → 웹 링크에서 보기
    openSource(a.getAttribute('href'));
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('srcOverlay').hidden) closeSource(); });
}
