// 제목줄 없는 프로그램 창: 창 버튼 · 헤더 끌어 옮기기 · 가장자리 크기 조절 (pywebview js_api).
import { $ } from '../lib/dom.js';

// 데이터 출처는 ⚙ 설정 안 (사용자 요청)

/* ---------- 제목줄 없는 프로그램 창: 헤더 오른쪽 창 버튼 + 헤더 끌어서 옮기기 ---------- */
const MAX_ICO = '<path d="M3 1.5h7.5V9M1.5 3h7.5v7.5H1.5z" fill="none" stroke="currentColor" stroke-width="1.1"/>';
const RES_ICO = '<rect x="1.5" y="1.5" width="9" height="9" fill="none" stroke="currentColor" stroke-width="1.1"/>';

function setMaxIco(maxed) {
  $('winMaxIco').innerHTML = maxed ? MAX_ICO : RES_ICO; document.querySelector('[data-win="max"]').title = maxed ? '이전 크기로' : '최대화';
  $('rsz').hidden = !document.body.classList.contains('frameless') || maxed;   // 최대화일 땐 테두리 크기 조절 없음
}

export function init() {
  window.addEventListener('pywebviewready', async () => {
    const api = window.pywebview?.api; if (!api?.win_close) return;
    document.body.classList.add('frameless'); $('winCtl').hidden = false;
    const syncMax = async () => { try { setMaxIco(await api.win_state()); } catch (e) {} };
    syncMax(); setTimeout(syncMax, 800); setTimeout(syncMax, 2000);   // 처음 최대화가 끝난 뒤 아이콘 맞춤
    $('winCtl').onclick = async e => {
      const b = e.target.closest('[data-win]'); if (!b) return; b.blur();
      if (b.dataset.win === 'min') api.win_min();
      if (b.dataset.win === 'max') setMaxIco(await api.win_max());
      if (b.dataset.win === 'close') api.win_close();
    };
    // 테두리 끌어 크기 바꾸기
    $('rsz').addEventListener('mousedown', async e => {
      const ed = e.target.dataset.e; if (!ed || e.button !== 0) return;
      e.preventDefault();
      const r0 = await api.win_rect(); if (!r0) return;
      const sx = e.screenX, sy = e.screenY; let raf = 0, last = null;
      const mv = ev => {
        const dx = ev.screenX - sx, dy = ev.screenY - sy; let [x, y, w, h] = r0;
        if (ed.includes('e')) w = r0[2] + dx;
        if (ed.includes('s')) h = r0[3] + dy;
        if (ed.includes('w')) { w = Math.max(1100, r0[2] - dx); x = r0[0] + r0[2] - w; }
        if (ed.includes('n')) { h = Math.max(700, r0[3] - dy); y = r0[1] + r0[3] - h; }
        last = [x, y, w, h];
        if (!raf) raf = requestAnimationFrame(() => { raf = 0; api.win_set_rect(...last); });
      };
      const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
    const bar = document.querySelector('.topbar');
    const free = t => !t.closest('button, a, input, select, label, textarea, .hl-pop, .brand, .winctl');
    bar.addEventListener('dblclick', async e => { if (free(e.target)) setMaxIco(await api.win_max()); });
    bar.addEventListener('mousedown', e => {
      if (e.button !== 0 || !free(e.target)) return;
      const dpr = devicePixelRatio || 1;
      let ox = e.clientX, oy = e.clientY, moved = false, raf = 0, last = null;
      const mv = ev => {
        if (!moved && Math.abs(ev.screenX - e.screenX) + Math.abs(ev.screenY - e.screenY) < 4) return;
        if (!moved) { moved = true; if (innerWidth > screen.availWidth - 20) { ox = Math.min(ox, 700); setMaxIco(false); } }   // 최대화 상태에서 끌면 원래 크기로
        last = [ev.screenX - ox, ev.screenY - oy];
        if (!raf) raf = requestAnimationFrame(() => { raf = 0; api.win_move(last[0], last[1]); });
      };
      const up = () => { removeEventListener('mousemove', mv); removeEventListener('mouseup', up); };
      addEventListener('mousemove', mv); addEventListener('mouseup', up);
    });
  });
}
