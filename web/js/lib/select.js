// <select> 를 같은 모양의 펼침 목록으로 바꿔 주는 위젯.
import { esc } from './fmt.js';

/** 기본 select 는 브라우저가 위로 펼치기도 해서, 항상 아래로 펼쳐지는 목록으로 바꾼다 (값·change 는 원래 select 그대로) */
export function enhanceSelect(sel) {
  const btn = document.createElement('button'), list = document.createElement('div');
  btn.type = 'button'; btn.id = sel.id + 'Btn'; btn.className = 'field dd-btn';
  btn.setAttribute('aria-haspopup', 'listbox'); btn.setAttribute('aria-expanded', 'false');
  btn.innerHTML = '<span></span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  list.className = 'dd-list'; list.setAttribute('role', 'listbox'); list.hidden = true;
  sel.hidden = true; sel.after(btn, list);
  const render = () => { btn.firstChild.textContent = sel.selectedOptions[0]?.text || '–'; };
  const close = () => { list.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
  const open = () => {
    list.innerHTML = [...sel.options].map(o => `<button type="button" role="option" data-v="${esc(o.value)}" aria-selected="${o.selected}">${esc(o.text)}</button>`).join('');
    list.hidden = false; btn.setAttribute('aria-expanded', 'true');
    const cur = list.querySelector('[aria-selected="true"]');
    if (cur) { list.scrollTop = cur.offsetTop - 4; cur.focus({ preventScroll: true }); }
  };
  btn.onclick = () => (list.hidden ? open() : close());
  list.onclick = e => {
    const o = e.target.closest('[data-v]'); if (!o) return;
    sel.value = o.dataset.v; render(); close(); btn.focus();
    sel.dispatchEvent(new Event('change'));
  };
  list.onkeydown = e => {
    const items = [...list.querySelectorAll('[data-v]')], i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); items[Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus(); }
    if (e.key === 'Escape') { close(); btn.focus(); }
  };
  document.addEventListener('click', e => { if (!list.hidden && !btn.contains(e.target) && !list.contains(e.target)) close(); });
  sel._ddRender = render;
  render();
}
