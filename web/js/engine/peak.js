// 집계와 ICAO Doc 9184 첨두시간 산정 엔진 (순수 계산).
import { DAY, fmtDate, fmtDT, fmtN, fmtPct, fmtTime, HOUR, pad, Q, WD, wdOf } from '../lib/fmt.js';

/** 운항 목록 → 정시(60분)·15분 빈(bin) 배열 */
export function bin(movements, startLocal, days, offsetH) {
  const nH = days * 24, nQ = days * 96;
  const s = {
    arr: new Float64Array(nH), dep: new Float64Array(nH),
    qArr: new Float64Array(nQ), qDep: new Float64Array(nQ)
  };
  for (const m of movements) {
    const rel = m.t + offsetH * HOUR - startLocal;
    if (rel < 0 || rel >= days * DAY) continue;
    const h = Math.floor(rel / HOUR), q = Math.floor(rel / Q);
    if (m.type === 'A') { s.arr[h]++; s.qArr[q]++; } else { s.dep[h]++; s.qDep[q]++; }
  }
  s.tot = s.arr.map((v, i) => v + s.dep[i]);
  s.qTot = s.qArr.map((v, i) => v + s.qDep[i]);
  return s;
}

/**
 * 연속 2시간 평균 (Averaged over two consecutive hours)
 * @param bins  기본 빈 배열 (정시=1시간 빈, 이동=15분 빈)
 * @param k     1시간에 해당하는 빈 개수 (정시=1, 15분=4)
 * 반환: A[i] = (H[i] + H[i+k]) / 2,  H[i] = bins[i..i+k-1] 합
 */
export function twoHourAvg(bins, k) {
  const n = bins.length, H = new Float64Array(Math.max(0, n - k + 1));
  let run = 0;
  for (let i = 0; i < n; i++) { run += bins[i]; if (i >= k) run -= bins[i - k]; if (i >= k - 1) H[i - k + 1] = run; }
  const A = new Float64Array(Math.max(0, H.length - k));
  for (let i = 0; i < A.length; i++) A[i] = (H[i] + H[i + k]) / 2;
  return { H, A };
}

export const argmax = a => { let b = -1, bi = -1; for (let i = 0; i < a.length; i++) if (a[i] > b) { b = a[i]; bi = i; } return bi; };

/** 값 배열을 내림차순 정렬한 [{i, v}] (동률 시 이른 시간 우선) */
export const ranked = a => Array.from(a, (v, i) => ({ i, v })).sort((x, y) => y.v - x.v || x.i - y.i);

export function analyze(data, cfg) {
  const { movements, startLocal, days, offsetH } = data;
  const s = bin(movements, startLocal, days, offsetH);
  const nH = days * 24;

  // ── 정시 기준 연속 2시간 평균 (순위 산정의 기준 시계열)
  const c = { arr: twoHourAvg(s.arr, 1).A, dep: twoHourAvg(s.dep, 1).A, tot: twoHourAvg(s.tot, 1).A };
  // ── 이동 60분(15분 간격) 연속 2시간 평균
  const r = { arr: twoHourAvg(s.qArr, 4).A, dep: twoHourAvg(s.qDep, 4).A, tot: twoHourAvg(s.qTot, 4).A };

  const rolling = cfg.window === 'rolling';
  const win = (metricSeries, i, stepSec, srcAll) => ({
    start: startLocal + i * stepSec, len: 2 * HOUR,
    v: metricSeries[i], arr: srcAll.arr[i], dep: srcAll.dep[i], tot: srcAll.tot[i]
  });

  // ── Busy hour 순위 N (ICAO 정의: 연간 40·30번째 — 분석 기간 안의 N번째를 그대로 씀)
  const N = cfg.N;

  // ── 구분별(도착/출발/합계) 독립 산정
  const split = {};
  for (const m of ['arr', 'dep', 'tot']) {
    const ser = rolling ? r[m] : c[m], step = rolling ? Q : HOUR;
    const pi = argmax(ser);
    const rk = ranked(c[m]);
    const bi = rk[Math.min(N, rk.length) - 1];
    const rawRk = ranked(s[m]);
    split[m] = {
      peak: pi >= 0 ? { v: ser[pi], start: startLocal + pi * step } : null,
      busy: bi ? { v: bi.v, start: startLocal + bi.i * HOUR } : null,
      rawPeak: rawRk[0] ? { v: rawRk[0].v, start: startLocal + rawRk[0].i * HOUR } : null,
      total: s[m].reduce((a, b) => a + b, 0)
    };
    split[m].avgDaily = split[m].total / days;
    split[m].peakHourShare = split[m].peak ? split[m].peak.v / Math.max(1, split[m].avgDaily) : null;
  }

  // ── 일별 합계
  const daily = [];
  for (let d = 0; d < days; d++) {
    let a = 0, dp = 0; for (let h = 0; h < 24; h++) { a += s.arr[d * 24 + h]; dp += s.dep[d * 24 + h]; }
    daily.push({ d, ls: startLocal + d * DAY, arr: a, dep: dp, tot: a + dp });
  }
  const overallAvgDaily = daily.reduce((x, y) => x + y.tot, 0) / days;

  // ── 피크 월 (일평균 운항 최대인 달 → 부분 월 편향 방지)
  const months = {};
  for (const dd of daily) { const k = fmtDate(dd.ls).slice(0, 7); (months[k] ||= []).push(dd); }
  const monthStats = Object.entries(months).map(([k, ds]) => ({ k, ds, avg: ds.reduce((a, b) => a + b.tot, 0) / ds.length }));
  const peakMonth = monthStats.reduce((a, b) => (b.avg > a.avg ? b : a), monthStats[0]);

  const methods = [];

  // (1) ICAO Peak Aircraft Traffic Demand
  {
    const ser = rolling ? r.tot : c.tot, step = rolling ? Q : HOUR, src = rolling ? r : c;
    const i = argmax(ser);
    if (i >= 0) {
      const w = win(ser, i, step, src);
      methods.push({ id: 'icao_peak', name: 'Peak aircraft traffic demand', basis: `연속 2시간 평균 최대 (${rolling ? '이동 60분' : '정시'})`, ...w, day: Math.floor((w.start - startLocal) / DAY) });
    }
  }
  // (2) ICAO Busy Hour Aircraft Traffic Demand
  const rkTot = ranked(c.tot);
  {
    const e = rkTot[Math.min(N, rkTot.length) - 1];
    if (e) {
      const w = win(c.tot, e.i, HOUR, c);
      methods.push({ id: 'icao_busy', name: `Busy hour aircraft traffic demand (${N}번째)`, basis: `연속 2시간 평균 ${N}번째`, ...w, day: Math.floor((w.start - startLocal) / DAY) });
    }
  }
  // (3) IATA: 피크 월 평균 주의 두 번째로 바쁜 날의 피크 시간
  let iataInfo = null;
  if (peakMonth) {
    const byWd = {};
    for (const dd of peakMonth.ds) (byWd[wdOf(dd.ls)] ||= []).push(dd);
    const wdAvg = Object.entries(byWd).map(([w, ds]) => ({ w: +w, ds, avg: ds.reduce((a, b) => a + b.tot, 0) / ds.length })).sort((a, b) => b.avg - a.avg);
    const second = wdAvg[1] || wdAvg[0];
    const rep = second.ds.reduce((a, b) => (Math.abs(b.tot - second.avg) < Math.abs(a.tot - second.avg) ? b : a));
    let bh = 0; for (let h = 1; h < 24; h++) if (s.tot[rep.d * 24 + h] > s.tot[rep.d * 24 + bh]) bh = h;
    const hi = rep.d * 24 + bh;
    iataInfo = { month: peakMonth.k, wd: second.w, wdAvg: second.avg, fallback: !wdAvg[1], weekdaysCovered: wdAvg.length };
    methods.push({
      id: 'iata_sbd', name: 'c) Second busiest day 피크 시간 (IATA)',
      basis: `피크 월 ${peakMonth.k} · 평균 주 2위 요일 ${WD[second.w]}요일(평균 ${fmtN(second.avg)}편)${wdAvg[1] ? '' : ' ※요일 데이터 부족'}`,
      start: startLocal + hi * HOUR, len: HOUR, v: s.tot[hi], arr: s.arr[hi], dep: s.dep[hi], tot: s.tot[hi], day: rep.d
    });
  }
  // (4) N번째 바쁜 단일 시간 (SBR)
  {
    const rk = ranked(s.tot), e = rk[Math.min(N, rk.length) - 1];
    if (e) methods.push({ id: 'nth_hour', name: `a) ${N}번째 바쁜 시간`, basis: `단일 정시 운항 ${N}번째`, start: startLocal + e.i * HOUR, len: HOUR, v: e.v, arr: s.arr[e.i], dep: s.dep[e.i], tot: e.v, day: Math.floor(e.i / 24) });
  }
  // (5) §3.4.3 b) 피크 월(또는 피크 2개월)의 평균일(또는 평균 평일) 피크 시간 — FAA 방식(§3.4.4)
  let adpm = null;
  if (peakMonth) {
    let span = [peakMonth], spanKey = peakMonth.k;
    if (cfg.adpmSpan === 2 && monthStats.length > 1) {
      // 연속된 두 달 중 일평균이 가장 높은 조합
      let best = null;
      for (let k = 0; k < monthStats.length - 1; k++) {
        const ds = monthStats[k].ds.concat(monthStats[k + 1].ds), avg = ds.reduce((a, b) => a + b.tot, 0) / ds.length;
        if (!best || avg > best.avg) best = { ds, avg, ms: [monthStats[k], monthStats[k + 1]] };
      }
      span = best.ms; spanKey = `${best.ms[0].k}~${best.ms[1].k}`;
    }
    let ds = span.flatMap(m => m.ds);
    if (cfg.adpmDays === 'weekday') { const wk = ds.filter(dd => wdOf(dd.ls) >= 1 && wdOf(dd.ls) <= 5); if (wk.length) ds = wk; }
    const pa = new Array(24).fill(0), pd = new Array(24).fill(0);
    for (const dd of ds) for (let h = 0; h < 24; h++) { pa[h] += s.arr[dd.d * 24 + h]; pd[h] += s.dep[dd.d * 24 + h]; }
    const n = ds.length;
    adpm = { arr: pa.map(v => v / n), dep: pd.map(v => v / n), label: `${spanKey} ${cfg.adpmDays === 'weekday' ? '평균 평일' : '평균일'}`, n };
    adpm.tot = adpm.arr.map((v, h) => v + adpm.dep[h]);
    const h = argmax(adpm.tot), dayAvg = adpm.tot.reduce((a, b) => a + b, 0);
    methods.push({ id: 'adpm', name: 'b) 피크 월 평균일 피크 시간 (FAA)', basis: `${adpm.label} (${n}일 평균, 일 ${fmtN(dayAvg)}편)`, start: null, hourOfDay: h, len: HOUR, v: adpm.tot[h], arr: adpm.arr[h], dep: adpm.dep[h], tot: adpm.tot[h], day: null, dayTotal: dayAvg });
  }
  // (6) §3.4.3 d) 90/95 백분위 바쁜 기간(일)의 피크 시간
  {
    const sorted = [...daily].sort((a, b) => a.tot - b.tot || a.d - b.d);
    const dd = sorted[Math.max(0, Math.ceil(cfg.pct * sorted.length) - 1)];
    let bh = 0; for (let h = 1; h < 24; h++) if (s.tot[dd.d * 24 + h] > s.tot[dd.d * 24 + bh]) bh = h;
    const hi = dd.d * 24 + bh;
    methods.push({ id: 'pct_day', name: `d) ${Math.round(cfg.pct * 100)} 백분위 바쁜 날 피크 시간`, basis: `일 운항 ${Math.round(cfg.pct * 100)} 백분위 날 (${fmtDate(dd.ls)}, ${dd.tot}편)`, start: startLocal + hi * HOUR, len: HOUR, v: s.tot[hi], arr: s.arr[hi], dep: s.dep[hi], tot: s.tot[hi], day: dd.d });
  }
  // (7) §3.4.3 e) 5% busy hour: 이보다 바쁜 모든 시간의 누적 운항이 총운항의 5%가 되는 시간
  {
    const rk = ranked(s.tot), total = split.tot.total;
    let cum = 0, e = rk[rk.length - 1];
    for (const x of rk) { if (cum >= 0.05 * total) { e = x; break; } cum += x.v; }
    methods.push({ id: 'pct5', name: 'e) 5% busy hour', basis: `상위 ${rk.indexOf(e)}개 시간 누적 ${fmtN(cum, 0)}편 = 총운항의 ${fmtPct(cum / total)}`, start: startLocal + e.i * HOUR, len: HOUR, v: e.v, arr: s.arr[e.i], dep: s.dep[e.i], tot: e.v, day: Math.floor(e.i / 24) });
  }
  // (8) 참고: Absolute peak — 가장 바쁜 달의 가장 바쁜 날 최대 60분 수요 (Section II §1.2.5, 계획 기준으로 쓰지 않음)
  if (peakMonth) {
    const bd = peakMonth.ds.reduce((a, b) => (b.tot > a.tot ? b : a));
    let bj = bd.d * 96, bv = -1;
    for (let j = bd.d * 96; j < bd.d * 96 + 96 && j + 4 <= s.qTot.length; j++) {
      let v = 0; for (let q = 0; q < 4; q++) v += s.qTot[j + q];
      if (v > bv) { bv = v; bj = j; }
    }
    const sum = a => a.slice(bj, bj + 4).reduce((x, y) => x + y, 0);
    methods.push({ id: 'abs_peak', name: '참고: Absolute peak (계획 기준 아님)', basis: `가장 바쁜 달(${peakMonth.k})의 가장 바쁜 날 최대 60분 (15분 간격 이동)`, start: startLocal + bj * Q, len: HOUR, v: bv, arr: sum(s.qArr), dep: sum(s.qDep), tot: bv, day: bd.d });
  }

  // 각 방법의 설계일 총운항 & 첨두 집중률
  for (const m of methods) {
    if (m.dayTotal == null) m.dayTotal = m.day != null ? daily[m.day].tot : null;
    m.conc = m.dayTotal ? m.v / m.dayTotal : null;
    m.concAvg = overallAvgDaily ? m.v / overallAvgDaily : null;
    m.annualRatio = overallAvgDaily ? m.v / (overallAvgDaily * 365) : null;   // §3.8.4 peak hour ratio (연간 환산 운항 대비)
    m.when = m.start != null ? `${fmtDT(m.start)}–${fmtTime(m.start + m.len)} (${WD[wdOf(m.start)]})` : `매일 ${pad(m.hourOfDay)}:00–${pad(m.hourOfDay + 1)}:00`;
  }

  // 시간대별 상세용 순위 맵
  const rankOf = new Int32Array(nH).fill(0);
  rkTot.forEach((e, k) => { rankOf[e.i] = k + 1; });

  return { s, c, r, split, daily, months: monthStats, peakMonth, methods, N, rkTot, rankOf, adpm, iataInfo, overallAvgDaily, days, startLocal };
}
