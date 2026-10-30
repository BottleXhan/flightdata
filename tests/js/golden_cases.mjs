// 분석 엔진 기준 결과 (리팩터링 전후 비교용). 브라우저(tools/golden.py)와 node(engine.test.mjs) 양쪽에서 같은 함수로 돌린다.
export function cases(api) {
  const { generateDemo, analyze, dateToLocalSec, readFlightsCSV, flightsToMovements } = api;
  const round = v => (typeof v === 'number' ? Math.round(v * 1e6) / 1e6 : v);
  const pick = (o, keys) => Object.fromEntries(keys.map(k => [k, round(o?.[k] ?? null)]));
  const out = {};
  const startLocal = dateToLocalSec('2025-01-01'), days = 365, offsetH = 9;
  const movements = generateDemo('RKSI', startLocal, days, offsetH);
  out.demo = { n: movements.length, first: movements.slice(0, 3), last: movements.slice(-2) };
  const data = { movements, startLocal, days, offsetH };
  const cfgs = [
    { method: 'nth_hour', N: 30, window: 'clock', adpmDays: 'all', adpmSpan: 1, pct: 0.9 },
    { method: 'icao_busy', N: 40, window: 'rolling', adpmDays: 'weekday', adpmSpan: 2, pct: 0.95 },
    { method: 'icao_peak', N: 20, window: 'rolling', adpmDays: 'all', adpmSpan: 2, pct: 0.9 },
  ];
  out.analyze = cfgs.map(cfg => {
    const r = analyze(data, cfg);
    return {
      cfg,
      methods: r.methods.map(m => pick(m, ['id', 'name', 'basis', 'start', 'hourOfDay', 'len', 'v', 'arr', 'dep', 'tot', 'day', 'dayTotal', 'conc', 'concAvg', 'annualRatio', 'when'])),
      split: Object.fromEntries(Object.entries(r.split).map(([k, s]) => [k, { peak: s.peak, busy: s.busy, rawPeak: s.rawPeak, total: s.total, avgDaily: round(s.avgDaily), peakHourShare: round(s.peakHourShare) }])),
      daily: r.daily.map(d => d.tot),
      months: r.months.map(m => [m.k, round(m.avg)]),
      peakMonth: r.peakMonth?.k,
      top: r.rkTot.slice(0, 50),
      iataInfo: r.iataInfo,
      adpm: r.adpm && { label: r.adpm.label, n: r.adpm.n, tot: r.adpm.tot.map(round) },
      overallAvgDaily: round(r.overallAvgDaily),
    };
  });
  const csv = '﻿icao24,callsign,firstseen,lastseen,estdepartureairport,estarrivalairport,typecode,model\n' +
    '71c001,KAL123 ,1735689600,1735700000,RKSI,RJTT,B77W,777-3B5ER\n' +
    '71c002,"AAR,9",1735690000,1735699000,rjtt,RKSI,,\n' +
    '71c001,KAL123 ,1735689600,1735700000,RKSI,RJTT,B77W,777-3B5ER\n';
  const fl = readFlightsCSV(csv);
  out.csv = { flights: fl, movements: flightsToMovements(fl, 'RKSI', 1735600000, 1735800000) };
  return out;
}
