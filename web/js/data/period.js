// 공항 코드·UTC 오프셋과 분석 기간(빠른 선택·연도 선택).
import { loadMapData, MAPDATA } from './airports.js';
import { csvSets } from './datasets.js';
import { $ } from '../lib/dom.js';
import { dateToLocalSec, DAY, pad } from '../lib/fmt.js';
import { AMAP, amapSelect } from '../ui/airport-map.js';

/* ---------- 공항 · UTC 기본값 (회색 예시만 보이고, 비워 두면 RKSI · 공항 시간대 자동) ---------- */
export const DEFAULT_AP = 'RKSI';
export const apCode = () => $('icao').value.trim().toUpperCase() || DEFAULT_AP;

/** 공항 시간대(IANA)로 그 날 현지 정오의 UTC 오프셋(시간). 모르면 null */
export function autoTz(ap, day) {
  const tz = MAPDATA?.airports?.[ap]?.[6];
  if (!tz) return null;
  try {
    const d = new Date(`${day || new Date().toISOString().slice(0, 10)}T12:00:00Z`);
    const s = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'shortOffset' }).formatToParts(d).find(x => x.type === 'timeZoneName').value;
    const m = s.match(/GMT([+-])(\d+)(?::(\d+))?/);
    return m ? (m[1] === '-' ? -1 : 1) * (+m[2] + (+m[3] || 0) / 60) : 0;
  } catch (e) { return null; }
}

/** 공항 ap 에 쓸 UTC 오프셋: 직접 넣은 값(지금 공항일 때) → 시간대 자동 → 9 */
export function offsetFor(ap = apCode(), day = $('startDate').value) {
  const v = $('tz').value.trim();
  if (v !== '' && isFinite(+v) && ap === apCode()) return +v;
  return autoTz(ap, day) ?? 9;
}

export function updateApInfo() {
  const ap = apCode(), a = MAPDATA?.airports?.[ap], auto = autoTz(ap, $('startDate').value);
  $('tz').placeholder = auto == null ? '9' : String(auto);
  $('apInfo').textContent = !MAPDATA ? '' : a
    ? `${a[0]}${a[1] ? ' · ' + a[1] : ''}${a[2] ? ', ' + a[2] : ''} · ${Math.abs(a[3]).toFixed(3)}°${a[3] >= 0 ? 'N' : 'S'} ${Math.abs(a[4]).toFixed(3)}°${a[4] >= 0 ? 'E' : 'W'}${a[6] ? ` · ${a[6]} (UTC${auto >= 0 ? '+' : ''}${auto})` : ''}`
    : (/^[A-Z0-9]{4}$/.test(ap) ? '등록되지 않은 공항 코드입니다. UTC 오프셋을 직접 입력하세요.' : 'ICAO 코드는 4자리입니다 (예: RKSI).');
  setTimeout(() => { if (AMAP.sel !== ap) amapSelect(ap); });   // 데이터 탭 지도에도 표시
}

/* ---------- 기간 빠른 선택 (최근 7·30일, 1년 단위) ---------- */
export const MAX_DAYS = 3660;                                // 한 번에 볼 수 있는 최대 기간 (약 10년)
export const isoD = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const yesterday = () => isoD(new Date(Date.now() - DAY * 1000));

/** 불러온 CSV 의 기간 (있으면 연도 선택을 그 안으로 자름) */
export const csvRangeNow = () => $('source').value === 'csv' ? csvSets.get($('csvAirport').value || apCode())?.range : null;

export function setRange(a, b) {
  const r = csvRangeNow();
  if (r) { if (a < r[0]) a = r[0]; if (b > r[1]) b = r[1]; }
  $('startDate').value = a; $('endDate').value = b;
  updateSpan();
}

export function quickDays(n) {
  const e = yesterday(), s = isoD(new Date(Date.now() - n * DAY * 1000));
  const r = csvRangeNow();
  if (r && (e > r[1] || s < r[0])) {            // CSV 를 불러왔으면 그 끝에서 n 일
    const end = r[1], st = isoD(new Date(dateToLocalSec(end) * 1000 - (n - 1) * DAY * 1000));
    return setRange(st, end);
  }
  setRange(s, e);
}

function quickYear(y) {
  const last = yesterday();
  setRange(`${y}-01-01`, `${y}-12-31` < last ? `${y}-12-31` : last);
}

/** CSV 기간 안의 연도 (경계에 며칠만 걸친 해는 뺌: 12/31 밤 출발편이 다음 해 1/1 로 넘어가는 경우 등) */
export function csvYears(r) {
  const out = [];
  for (let y = +r[0].slice(0, 4); y <= +r[1].slice(0, 4); y++) {
    const a = r[0] > `${y}-01-01` ? r[0] : `${y}-01-01`, b = r[1] < `${y}-12-31` ? r[1] : `${y}-12-31`;
    if (Math.round((dateToLocalSec(b) - dateToLocalSec(a)) / DAY) + 1 >= 7) out.push(y);
  }
  return out.length ? out.reverse() : [+r[1].slice(0, 4)];
}

/** 연도 표: 2017 ~ 올해 (CSV 를 불러왔으면 그 안의 연도만 누를 수 있음).
    한 번 누르면 그 해, 이어서 다른 해를 누르면 두 해 사이 전체를 적용하고 닫는다 (수집기와 같은 방식) */
let yearFirst = null;

function quickYears(y0, y1) {
  const [a, b] = y0 < y1 ? [y0, y1] : [y1, y0], last = yesterday();
  setRange(`${a}-01-01`, `${b}-12-31` < last ? `${b}-12-31` : last);
}

function paintYears(lo, hi) {
  $('yearGrid').querySelectorAll('button').forEach(x => x.classList.toggle('on', lo != null && +x.dataset.y >= lo && +x.dataset.y <= hi));
}

function openYears() {
  const now = new Date().getFullYear(), r = csvRangeNow(), ok = r ? new Set(csvYears(r)) : null;
  $('yearGrid').innerHTML = Array.from({ length: now - 2017 + 1 }, (_, i) => 2017 + i)
    .map(y => `<button type="button" data-y="${y}"${ok && !ok.has(y) ? ' disabled' : ''}>${y}${y === now ? ' ~어제' : ''}</button>`).join('');
  yearFirst = null;
  $('yearMsg').textContent = '연도 1개 선택, 또는 시작·종료 연도를 순서대로 선택';
  const sd = $('startDate').value, ed = $('endDate').value;
  if (/-01-01$/.test(sd)) paintYears(+sd.slice(0, 4), +ed.slice(0, 4));
  $('yearPop').hidden = false; $('yearBtn').setAttribute('aria-expanded', 'true');
}

function closeYears() { $('yearPop').hidden = true; $('yearBtn').setAttribute('aria-expanded', 'false'); }

export function buildYearButtons() { closeYears(); updateSpan(); }

export function updateSpan() {
  const sd = $('startDate').value, ed = $('endDate').value;
  let txt = '';
  if (sd && ed && ed >= sd) {
    const n = Math.round((dateToLocalSec(ed) - dateToLocalSec(sd)) / DAY) + 1;
    txt = `선택 기간 ${n.toLocaleString()}일` + (n > MAX_DAYS ? ` — 한 번에 최대 ${MAX_DAYS.toLocaleString()}일(약 10년)까지 볼 수 있습니다` : '');
  }
  $('spanInfo').textContent = txt;
  $('spanInfo').style.color = /최대/.test(txt) ? 'var(--danger, #d64545)' : '';
  // 연도 단위면 버튼에 고른 연도 표시 (끝이 12/31 이거나 어제·CSV 끝)
  const y0 = sd.slice(0, 4), y1 = ed.slice(0, 4);
  const full = /-01-01$/.test(sd) && (/-12-31$/.test(ed) || ed === yesterday() || ed === csvRangeNow()?.[1]);
  $('yearBtn').textContent = '📅 ' + (full ? (y0 === y1 ? y0 : `${y0} ~ ${y1}`) : '연도 선택');
  $('yearBtn').setAttribute('aria-pressed', String(full));
  document.querySelectorAll('#quickRange [data-q]').forEach(b => b.setAttribute('aria-pressed', 'false'));
  updateApInfo();
}

let lastAp = apCode();
/** 최근 분석을 되살린 뒤: 지금 공항을 '직접 넣은 UTC 를 지울' 기준으로 */
export function syncLastAp() { lastAp = apCode(); }

export function init() {
  // 기본 기간: 최근 완료된 7일(어제까지) + 빠른 선택 버튼
  quickDays(7);
  buildYearButtons();
  loadMapData().then(updateApInfo);
  $('quickRange').addEventListener('click', e => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.q) { quickDays(+b.dataset.q); b.setAttribute('aria-pressed', 'true'); }
    if (b.id === 'yearBtn') { $('yearPop').hidden ? openYears() : closeYears(); }
    if (b.dataset.y) {
      const y = +b.dataset.y;
      if (yearFirst == null) {                       // 첫 번째: 그 해만 적용, 끝 연도를 기다림
        yearFirst = y; quickYear(y); paintYears(y, y);
        $('yearMsg').textContent = `${y}년 선택됨 · 기간 지정 시 종료 연도 선택`;
      } else { quickYears(yearFirst, y); closeYears(); }   // 두 번째: 두 해 사이 전체
    }
  });
  document.addEventListener('click', e => { if (!$('yearPop').hidden && !e.target.closest('.ypick')) closeYears(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('yearPop').hidden) { closeYears(); $('yearBtn').focus(); } });
  ['startDate', 'endDate'].forEach(id => $(id).addEventListener('change', updateSpan));
  $('tz').addEventListener('input', updateApInfo);
  $('icao').addEventListener('input', () => { if (apCode() !== lastAp) { lastAp = apCode(); $('tz').value = ''; } updateApInfo(); });
}
