// 결과 요약 계산: 연별 묶음 · 첨두 비율 체인 · 처리능력 상태 · UK CAA 기준표 (순수 계산).
import { fmtDate, fmtN, WD, wdOf } from '../lib/fmt.js';

/* 첨두(가장 큰 합계) 막대 강조: 표지 노랑 막대 + 세로 띠 + 말풍선 */
export function peakOf(arr, dep) {
  const tot = arr.map((a, i) => a + dep[i]);
  let i = 0; for (let k = 1; k < tot.length; k++) if (tot[k] > tot[i]) i = k;
  return { i, tot: tot[i] };
}

/* ---------- 연별 (분석 기간이 두 해 이상일 때만 탭 표시) ---------- */
export function yearGroups(res) {
  const g = new Map();
  for (const d of res.daily) { const y = fmtDate(d.ls).slice(0, 4); (g.get(y) || g.set(y, []).get(y)).push(d); }
  return [...g].map(([k, ds]) => ({ k, ds }));
}

/* ---------- 상세 테이블 ---------- */

/* ---------- 처리능력 비교 · 미래 첨두 예측 ----------
   · 이용률 = 설계 첨두시간 수요 ÷ 시간당 처리능력. 100% 이상이면 ICAO 정의상 포화(Saturation).
   · 주의 기준(기본 85%)은 ICAO 정의가 아닌 이 도구의 설정값.
   · 미래 첨두(§3.8.4) = 연간 운항(기준 × (1+성장률)^t) × 첨두 비율(기준 × (1+비율 변화)^t)
     기준 연간 운항 = 분석 기간 일평균 × 365, 기준 첨두 비율 = 설계 첨두 ÷ 기준 연간 운항 */
export function capStatus(util, warn) {
  if (util >= 1) return { icon: '✕', label: '포화 (ICAO: 수요 ≥ 처리능력)' };
  if (util >= warn) return { icon: '⚠', label: `주의 (이용률 ${Math.round(warn * 100)}% 이상)` };
  return { icon: '✓', label: '여유' };
}

/* ---------- 첨두 비율 (월·일·시간) — §3.8.4 비율 체인 ---------- */
export function ratioSummary(res, sel) {
  const annual = res.overallAvgDaily * 365, daily = res.daily, nDays = daily.length;
  const monthDays = k => new Date(Date.UTC(+k.slice(0, 4), +k.slice(5, 7), 0)).getUTCDate();
  const months = res.months.map(m => {
    const total = m.ds.reduce((a, b) => a + b.tot, 0), full = monthDays(m.k);
    const est = m.avg * full;                                  // 일부만 있는 달은 일평균 × 달력 일수로 환산
    return { k: m.k, days: m.ds.length, full, total, avg: m.avg, est, partial: m.ds.length < full,
             annualShare: annual ? est / annual : null, index: res.overallAvgDaily ? m.avg / res.overallAvgDaily : null, peak: m === res.peakMonth };
  });
  const pm = months.find(m => m.peak);
  const byDay = [...daily].sort((a, b) => b.tot - a.tot || a.d - b.d);
  const days = byDay.map((d, i) => ({ rank: i + 1, date: fmtDate(d.ls), wd: WD[wdOf(d.ls)], tot: d.tot, d: d.d,
    annualShare: annual ? d.tot / annual : null, avgIndex: res.overallAvgDaily ? d.tot / res.overallAvgDaily : null,
    pmIndex: pm ? d.tot / pm.avg : null }));
  const hours = Array.from({ length: 24 }, (_, h) => {
    let sum = 0, max = 0;
    for (const d of daily) { const v = res.s.tot[d.d * 24 + h]; sum += v; if (v > max) max = v; }
    const dd = sel.day != null ? daily[sel.day] : null;
    const dv = dd ? res.s.tot[dd.d * 24 + h] : null;
    return { h, avg: sum / nDays, share: res.overallAvgDaily ? sum / nDays / res.overallAvgDaily : null, max,
             design: dv, designShare: dd && dd.tot ? dv / dd.tot : null };
  });
  const weekdays = [1, 2, 3, 4, 5, 6, 0].map(w => {         // 월요일부터
    const ds = daily.filter(d => wdOf(d.ls) === w);
    const total = ds.reduce((a, b) => a + b.tot, 0), avg = ds.length ? total / ds.length : null;
    const pmDs = pm ? res.peakMonth.ds.filter(d => wdOf(d.ls) === w) : [];
    return { w, name: WD[w], n: ds.length, total, avg, max: ds.length ? Math.max(...ds.map(d => d.tot)) : null,
             index: avg != null && res.overallAvgDaily ? avg / res.overallAvgDaily : null,
             pmAvg: pmDs.length ? pmDs.reduce((a, b) => a + b.tot, 0) / pmDs.length : null };
  });
  const wSum = weekdays.reduce((a, b) => a + (b.avg || 0), 0);
  for (const x of weekdays) x.weekShare = x.avg != null && wSum ? x.avg / wSum : null;
  const top = byDay[0];
  const chain = [
    { step: '연간 운항 (환산)', v: annual, annual: 1, prev: null, prevLbl: '', note: `기간 일평균 ${fmtN(res.overallAvgDaily)}편 × 365` },
    pm && { step: `피크 월 (${pm.k})`, v: pm.est, annual: pm.est / annual, prev: pm.est / annual, prevLbl: '바쁜 달 비율 (÷ 연간)',
            note: `일평균 최대인 달${pm.partial ? ` · ${pm.days}/${pm.full}일만 있어 일평균 × ${pm.full}일로 환산` : ''}` },
    pm && { step: '피크 월 평균일', v: pm.avg, annual: pm.avg / annual, prev: pm.avg / pm.est, prevLbl: '÷ 피크 월', note: `${pm.days}일 평균` },
    { step: `첨두일 (${fmtDate(top.ls)} ${WD[wdOf(top.ls)]})`, v: top.tot, annual: top.tot / annual, prev: pm ? top.tot / pm.avg : null, prevLbl: '÷ 피크 월 평균일', note: '기간 중 가장 바쁜 날' },
    sel.dayTotal != null && { step: `설계일 (${sel.day != null ? fmtDate(daily[sel.day].ls) : res.adpm?.label || '평균일'})`, v: sel.dayTotal, annual: sel.dayTotal / annual,
            prev: pm ? sel.dayTotal / pm.avg : null, prevLbl: '÷ 피크 월 평균일', note: '선택한 설계 첨두시간이 속한 날' },
    { step: '설계 첨두시간', v: sel.v, annual: sel.v / annual, prev: sel.dayTotal ? sel.v / sel.dayTotal : null, prevLbl: '÷ 설계일 (첨두 집중률)',
      note: `${sel.name} · ${sel.when}`, key: true }
  ].filter(Boolean);
  return { annual, months, days, hours, weekdays, chain, pm };
}

/* ---------- UK CAA 기준표 (Ashford et al. 2013, Table 2.1, Source: UK CAA) ----------
   [연간 운항, 첨두일/평균일 비, 첨두일 운항, 첨두시간/첨두일 비, 첨두시간 운항, SBR/첨두시간 비, SBR 운항] */
export const CAA_TABLE = [[10000,2.666,73,0.1125,8,0.688,6],[20000,2.255,124,0.1051,13,0.732,10],[30000,2.045,168,0.1011,17,0.759,13],[40000,1.907,209,0.0983,21,0.779,16],[50000,1.807,248,0.0961,24,0.794,19],[60000,1.729,284,0.0944,27,0.807,22],[70000,1.666,320,0.093,30,0.819,24],[80000,1.613,354,0.0918,32,0.828,27],[90000,1.568,387,0.0908,35,0.837,29],[100000,1.529,419,0.0898,38,0.845,32],[110000,1.494,450,0.089,40,0.852,34],[120000,1.463,481,0.0883,42,0.859,36],[130000,1.435,511,0.0876,45,0.865,39],[140000,1.409,541,0.0869,47,0.871,41],[150000,1.386,570,0.0863,49,0.876,43],[160000,1.365,598,0.0858,51,0.881,45],[170000,1.345,626,0.0853,53,0.886,47],[180000,1.326,654,0.0848,55,0.891,49],[190000,1.309,681,0.0844,57,0.895,51],[200000,1.293,708,0.084,59,0.899,53],[210000,1.278,735,0.0836,61,0.903,55],[220000,1.264,762,0.0832,63,0.907,57],[230000,1.25,788,0.0828,65,0.91,59],[240000,1.237,814,0.0825,67,0.914,61],[250000,1.225,839,0.0821,69,0.917,63],[260000,1.214,864,0.0818,71,0.92,65],[270000,1.203,890,0.0815,73,0.924,67],[280000,1.192,914,0.0812,74,0.927,69],[290000,1.182,939,0.081,76,0.929,71],[300000,1.172,964,0.0807,78,0.932,72],[310000,1.163,988,0.0804,79,0.935,74],[320000,1.154,1012,0.0802,81,0.938,76],[330000,1.146,1036,0.0799,83,0.94,78],[340000,1.137,1060,0.0797,84,0.943,80],[350000,1.13,1083,0.0795,86,0.945,81],[360000,1.122,1106,0.0793,88,0.948,83],[370000,1.114,1130,0.0791,89,0.95,85],[380000,1.107,1153,0.0788,91,0.952,87],[390000,1.1,1176,0.0786,92,0.954,88],[400000,1.094,1199,0.0785,94,0.957,90],[410000,1.087,1221,0.0783,96,0.959,92],[420000,1.081,1244,0.0781,97,0.961,93],[430000,1.075,1266,0.0779,99,0.963,95],[440000,1.069,1288,0.0777,100,0.965,97],[450000,1.063,1311,0.0776,102,0.967,98],[460000,1.057,1333,0.0774,103,0.969,100],[470000,1.052,1354,0.0772,105,0.971,102],[480000,1.047,1376,0.0771,106,0.972,103],[490000,1.041,1398,0.0769,108,0.974,105],[500000,1.036,1420,0.0768,109,0.976,106]];

export function caaExpect(annual) {
  const T = CAA_TABLE, lo = T[0], hi = T[T.length - 1];
  if (annual <= lo[0]) return { row: lo, out: 'low' };
  if (annual >= hi[0]) return { row: hi, out: 'high' };
  const k = T.findIndex(r => r[0] >= annual), a = T[k - 1], b = T[k], f = (annual - a[0]) / (b[0] - a[0]);
  return { row: a.map((v, i) => v + (b[i] - v) * f), out: null };
}
