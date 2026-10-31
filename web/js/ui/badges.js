// 국기·항공사 로고 그림 (HTML 조각). 국기 = web/flags/<코드>.svg (flag-icons, MIT),
// 로고 = pics.avs.io (IATA 코드로, 화면을 열 때 인터넷에서 — 저장소에는 넣지 않음, 사용자 선택 2026-10-31).
import { MAPDATA, regionName } from '../data/airports.js';
import { esc } from '../lib/fmt.js';

/** 편명 앞 3자리 → [IATA, 이름, 나라, 한글 이름] (모르면 null) */
export const airlineOf = code => MAPDATA?.airlines?.[code] || null;

/** 화면에 쓸 항공사 이름: 한글 이름 → 대응표 이름 → fallback(항공기 DB 운영사) */
export const airlineName = (code, fallback = '') => { const a = airlineOf(code); return a ? (a[3] || a[1]) : fallback; };

/** 그림 주소 (차트 캔버스용 — ui/charts.js 의 라벨 그림) */
export const flagSrc = cc => (/^[A-Z]{2}$/.test(cc || '') ? `flags/${cc.toLowerCase()}.svg` : '');
export const logoSrc = code => { const a = airlineOf(code); return a?.[0] ? `https://pics.avs.io/120/40/${a[0]}@2x.png` : ''; };

export function flag(cc) {
  if (!/^[A-Z]{2}$/.test(cc || '')) return '';
  return `<img class="flag" src="flags/${cc.toLowerCase()}.svg" alt="" title="${esc(regionName(cc))}" loading="lazy">`;
}

/** 공항 코드 → 그 나라 국기 */
export const apFlag = ap => flag(MAPDATA?.airports?.[ap]?.[2]);

/** 항공사 표시: 로고(IATA 를 알면) — 로고를 못 받으면 항공사 나라 국기로 바뀜. 둘 다 모르면 '' */
export function airlineMark(code) {
  const a = airlineOf(code);
  if (!a) return '';
  if (!a[0]) return flag(a[2]);
  return `<img class="al-logo" src="${esc(logoSrc(code))}" alt="${esc(a[1])}" title="${esc(a[1])}" loading="lazy" referrerpolicy="no-referrer" data-cc="${esc(a[2])}">`;
}

export function init() {
  // 그림을 못 받으면: 로고 → 나라 국기, 국기 → 없앰 (인라인 onerror 를 쓰지 않으려고 문서 전체에서 받음)
  document.addEventListener('error', e => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    if (img.classList.contains('al-logo')) img.outerHTML = flag(img.dataset.cc);
    else if (img.classList.contains('flag')) img.remove();
  }, true);
}
