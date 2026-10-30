// 최근 분석 기억 (localStorage flightdata.last): 공항·기간·필터·기준 옵션.
import { DEFAULT_AP, syncLastAp, updateSpan } from '../data/period.js';
import { syncFilterUI } from '../filters.js';
import { $ } from '../lib/dom.js';
import { setPeak, updateMethodOptions } from '../views/peak.js';

/* 최근 분석 기억 (이 브라우저에만): 공항·UTC·기간·운항 구분·첨두 설정. CSV 파일은 다시 골라야 함 */
export const LAST_KEY = 'flightdata.last';
const LAST_IDS = ['icao', 'tz', 'startDate', 'endDate', 'fDir', 'fSize', 'fH0', 'fH1', 'method', 'busyN', 'customN', 'window', 'adpmDays', 'adpmSpan', 'pct'];

export function saveLast(extra = {}) {
  try {
    const cur = JSON.parse(localStorage.getItem(LAST_KEY) || '{}');
    const v = Object.fromEntries(LAST_IDS.map(id => [id, $(id).value]));
    localStorage.setItem(LAST_KEY, JSON.stringify({ ...cur, ...v, peakOn: $('peakOn').checked, source: $('source').value, ...extra }));
  } catch (e) {}
}

export function init() {
  (function restoreLast() {
    let L = null;
    try { L = JSON.parse(localStorage.getItem(LAST_KEY) || 'null'); } catch (e) {}
    if (!L) return;
    for (const id of LAST_IDS) if (L[id] != null && $(id)) $(id).value = L[id];
    updateMethodOptions();
    setPeak(!!L.peakOn);
    syncLastAp();
    updateSpan();
    if (L.files?.length) {
      $('lastNote').hidden = false;
      $('lastNote').textContent = `최근 분석: ${L.icao || DEFAULT_AP} · ${L.startDate} ~ ${L.endDate} · ${L.files.join(', ')} — 같은 CSV를 선택하면 이어서 분석할 수 있습니다`;
    }
  })();
  LAST_IDS.forEach(id => $(id).addEventListener('change', () => saveLast()));
  syncFilterUI();
}
