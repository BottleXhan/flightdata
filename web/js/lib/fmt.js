// 숫자·날짜 형식과 시간 상수 (DOM 없음 — node 테스트에서도 씀). 시각은 '현지 시각을 UTC 필드에 담은 epoch 초'.
export const pad = n => String(n).padStart(2, '0');
export const DAY = 86400, HOUR = 3600, Q = 900;          // 초 단위
export const WD = ['일', '월', '화', '수', '목', '금', '토'];

/** "현지 시각 epoch초"(UTC 필드에 현지 시각이 들어있는 값)를 문자열로 */
export const fmtDate = ls => { const d = new Date(ls * 1000); return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`; };
export const fmtTime = ls => { const d = new Date(ls * 1000); return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`; };
export const fmtDT = ls => `${fmtDate(ls)} ${fmtTime(ls)}`;
export const wdOf = ls => new Date(ls * 1000).getUTCDay();
export const fmtN = (v, d = 1) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('ko-KR', { minimumFractionDigits: 0, maximumFractionDigits: d });
export const fmtPct = v => v == null || !isFinite(v) ? '–' : (v * 100).toFixed(1) + '%';
export const dateToLocalSec = s => Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / 1000;
export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
