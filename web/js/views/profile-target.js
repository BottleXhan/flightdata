// 운항량 '표시 대상' (평균 · PEAK 일 · 설계일 · 날짜 선택).
import { $ } from '../lib/dom.js';
import { esc } from '../lib/fmt.js';
import { enhanceSelect } from '../lib/select.js';
import { STATE } from '../state.js';
import { openCal, syncCalLabel } from './calendar.js';
import { profTbl, renderProfile, renderProfTable, renderWeekdayProfile } from './profile.js';

/* 표시 대상: 평균 / PEAK / 세부 선택 (값은 숨은 select 에 두고, 버튼·세부 목록이 그 값을 바꿈) */
/** 설계일·설계 첨두시간 창은 "ICAO 첨두시간 보기"를 켰을 때만 프로파일에 표시 */
export const showDesign = () => $('peakOn').checked;

export const TARGET = {
  profile: { store: 'profileSel', modes: { avg: 'avg', peak: null, design: null }, detail: 'cal', render: () => renderProfile() },
  wd: { store: 'wdSel', modes: { avg: 'all', peak: null }, detail: 'select', render: () => renderWeekdayProfile() }
};

export function setTargetLabel(key, mode, name, date) {
  const b = document.querySelector(`[data-tkey="${key}"][data-tmode="${mode}"]`);
  b.innerHTML = `<span>${esc(name)}</span><span class="tgt-date">${esc(date)}</span>`;
}

export function fillDetail(key, opts) {
  const d = $(key + 'Detail'), prev = d.value;
  d.innerHTML = opts.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('');
  if (opts.some(o => o[0] === prev)) d.value = prev;
  d._ddRender?.();
}

function targetMode(key) {
  const t = TARGET[key], v = $(t.store).value;
  for (const [m, mv] of Object.entries(t.modes)) if (mv != null && v === mv) return m;
  return 'detail';
}

export function syncTarget(key) {
  const t = TARGET[key], mode = targetMode(key);
  document.querySelectorAll(`[data-tkey="${key}"]`).forEach(b => {
    b.setAttribute('aria-pressed', String(b.dataset.tmode === mode));
    if (b.dataset.tmode in t.modes) b.disabled = t.modes[b.dataset.tmode] == null;
  });
  document.querySelector(`[data-tdetail="${key}"]`).hidden = mode !== 'detail';
  if (t.detail === 'select') {
    const d = $(key + 'Detail');
    if (mode === 'detail' && [...d.options].some(o => o.value === $(t.store).value)) d.value = $(t.store).value;
    d._ddRender?.();
  } else syncCalLabel();
}

export function setTarget(key, v) {
  $(TARGET[key].store).value = v;
  syncTarget(key);
  if (STATE.res) TARGET[key].render();
}

export function init() {
  document.querySelectorAll('[data-tmode]').forEach(b => b.onclick = () => {
    const key = b.dataset.tkey, t = TARGET[key], mode = b.dataset.tmode;
    if (mode !== 'detail') return setTarget(key, t.modes[mode]);
    if (t.detail === 'select') { const d = $(key + 'Detail'); return setTarget(key, d.value || d.options[0]?.value); }
    // 날짜 선택: 달력을 연다 (지금 보고 있는 날 또는 PEAK 일에서 시작)
    document.querySelector(`[data-tdetail="${key}"]`).hidden = false;
    openCal();
  });
  enhanceSelect($('wdDetail'));
  document.querySelectorAll('[data-psort]').forEach(b => b.onclick = () => { profTbl.sort = b.dataset.psort; renderProfTable(); $('profDetail').querySelector('.overflow-auto').scrollTop = 0; });
  $('profDetailBtn').onclick = () => {
    const open = $('profDetail').hidden;
    $('profDetail').hidden = !open;
    $('profDetailBtn').setAttribute('aria-expanded', String(open));
    $('profDetailIcon').style.transform = open ? 'rotate(180deg)' : '';
    $('profDetailBtn').firstElementChild.textContent = open ? '세부 정보 닫기' : '세부 정보';
  };
  $('wdDetail').onchange = () => setTarget('wd', $('wdDetail').value);
}
