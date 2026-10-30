// 날짜 선택 달력 (일별 운항량 색 농도, PEAK 일 노랑, 설계일 점).
import { $ } from '../lib/dom.js';
import { esc, fmtDate, pad, WD, wdOf } from '../lib/fmt.js';
import { STATE } from '../state.js';
import { cfgFromUI } from './peak.js';
import { setTarget, showDesign } from './profile-target.js';

/* ---------- 날짜 선택 달력 (일별 운항량을 색 농도로, PEAK 일은 노랑, 설계일은 점) ---------- */
const cal = { y: null, m: null };

function calDays() {
  const byDate = new Map();
  for (const d of STATE.res?.daily || []) byDate.set(fmtDate(d.ls), d);
  return byDate;
}

export function syncCalLabel() {
  const v = $('profileSel').value;
  if (v === 'adpm') { $('calBtnLbl').textContent = STATE.res?.adpm?.label || '피크 월 평균일'; return; }
  const d = v.startsWith('day:') ? STATE.res?.daily[+v.slice(4)] : null;
  $('calBtnLbl').textContent = d ? `${fmtDate(d.ls)} (${WD[wdOf(d.ls)]}) · ${d.tot.toLocaleString()}편` : '날짜를 고르세요';
}

export function openCal() {
  if (!STATE.res) return;
  const v = $('profileSel').value, res = STATE.res;
  const d = v.startsWith('day:') ? res.daily[+v.slice(4)] : res.daily.reduce((a, b) => (b.tot > a.tot ? b : a));
  const dt = new Date(d.ls * 1000); cal.y = dt.getUTCFullYear(); cal.m = dt.getUTCMonth();
  renderCal();
  $('calPop').hidden = false; $('calBtn').setAttribute('aria-expanded', 'true');
  $('calPop').querySelector('.is-sel, .cal-day:not(:disabled)')?.focus({ preventScroll: true });
}

function closeCal() { $('calPop').hidden = true; $('calBtn').setAttribute('aria-expanded', 'false'); }

function renderCal() {
  const res = STATE.res, byDate = calDays(), v = $('profileSel').value;
  const sel = res.methods.find(m => m.id === cfgFromUI().method) || res.methods[0];
  const tots = res.daily.map(d => d.tot), lo = Math.min(...tots), hi = Math.max(...tots);
  const peakD = res.daily.reduce((a, b) => (b.tot > a.tot ? b : a)).d;
  const first = res.daily[0].ls, last = res.daily[res.daily.length - 1].ls;
  const ym = (y, m) => y * 12 + m, fy = new Date(first * 1000), ly = new Date(last * 1000);
  const minYM = ym(fy.getUTCFullYear(), fy.getUTCMonth()), maxYM = ym(ly.getUTCFullYear(), ly.getUTCMonth()), cur = ym(cal.y, cal.m);
  const nDays = new Date(Date.UTC(cal.y, cal.m + 1, 0)).getUTCDate(), lead = (new Date(Date.UTC(cal.y, cal.m, 1)).getUTCDay() + 6) % 7;
  let cells = ['월', '화', '수', '목', '금', '토', '일'].map(w => `<div class="cal-wd">${w}</div>`).join('') + '<div></div>'.repeat(lead);
  for (let day = 1; day <= nDays; day++) {
    const key = `${cal.y}-${pad(cal.m + 1)}-${pad(day)}`, d = byDate.get(key);
    if (!d) { cells += `<button class="cal-day" type="button" disabled>${day}<small>&nbsp;</small></button>`; continue; }
    const lvl = hi > lo ? (d.tot - lo) / (hi - lo) : 0.5;
    const cls = ['cal-day', d.d === peakD && 'is-peak', v === `day:${d.d}` && 'is-sel', showDesign() && d.d === sel.day && 'is-design'].filter(Boolean).join(' ');
    cells += `<button class="${cls}" type="button" data-cal="${d.d}" style="background:color-mix(in srgb, var(--accent) ${Math.round(8 + lvl * 52)}%, var(--surface-2))"
      title="${key} (${WD[wdOf(d.ls)]}) · ${d.tot}편${d.d === peakD ? ' · PEAK 일' : ''}${showDesign() && d.d === sel.day ? ' · 설계일' : ''}">${day}<small>${d.tot}</small></button>`;
  }
  $('calPop').innerHTML = `<div class="cal-head">
      <button class="icon-btn" type="button" data-calnav="-1" aria-label="이전 달" ${cur <= minYM ? 'disabled' : ''}>‹</button>
      <b>${cal.y}년 ${cal.m + 1}월</b>
      <button class="icon-btn" type="button" data-calnav="1" aria-label="다음 달" ${cur >= maxYM ? 'disabled' : ''}>›</button></div>
    <div class="cal-grid">${cells}</div>
    <div class="cal-foot"><span>적음<span class="cal-scale"></span>많음 · <b style="color:var(--text-primary)">노랑</b> PEAK 일${showDesign() ? ' · <span style="color:var(--accent)">●</span> 설계일' : ''}</span>
      <button class="btn" type="button" data-caladpm style="padding:.3rem .6rem;font-size:.75rem">${esc(res.adpm?.label || '피크 월 평균일')}</button></div>`;
}

export function init() {
  $('calBtn').onclick = () => ($('calPop').hidden ? openCal() : closeCal());
  $('calPop').onclick = e => {
    const nav = e.target.closest('[data-calnav]');
    if (nav) { const t = cal.y * 12 + cal.m + +nav.dataset.calnav; cal.y = Math.floor(t / 12); cal.m = t % 12; renderCal(); return; }
    const dbtn = e.target.closest('[data-cal]');
    if (dbtn) { setTarget('profile', `day:${dbtn.dataset.cal}`); closeCal(); $('calBtn').focus(); return; }
    if (e.target.closest('[data-caladpm]')) { setTarget('profile', 'adpm'); closeCal(); }
  };
  $('calPop').onkeydown = e => { if (e.key === 'Escape') { closeCal(); $('calBtn').focus(); } };
  document.addEventListener('click', e => { if (e.target.isConnected && !$('calPop').hidden && !e.target.closest('.calwrap') && !e.target.closest('[data-tmode="detail"]')) closeCal(); });
}
