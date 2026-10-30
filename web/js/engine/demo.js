// 데모 데이터 생성기: 요일·계절 변동, 도착/출발 이봉형 시간 분포, 포아송 잡음 (고정 시드, 순수 계산).
import { DAY, HOUR, wdOf } from '../lib/fmt.js';

export function mulberry32(a) { return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

export function poisson(l, rnd) {
  if (l > 40) { const u = 1 - rnd(), v = rnd(); return Math.max(0, Math.round(l + Math.sqrt(l) * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v))); }
  let L = Math.exp(-l), k = 0, p = 1; do { k++; p *= rnd(); } while (p > L); return k - 1;
}

export function generateDemo(airport, startLocal, days, offsetH) {
  const seed = [...airport].reduce((s, c) => s * 31 + c.charCodeAt(0), 7);
  const rnd = mulberry32(seed);
  const g = (h, mu, s) => Math.exp(-0.5 * ((h - mu) / s) ** 2);
  const arrShape = h => 0.15 + g(h, 7.5, 1.6) * 1.0 + g(h, 13, 2.2) * 0.7 + g(h, 18.5, 1.8) * 1.1 + g(h, 22.5, 1.2) * 0.5;
  const depShape = h => 0.12 + g(h, 9, 1.5) * 1.2 + g(h, 14.5, 2.0) * 0.8 + g(h, 20, 1.7) * 0.9 + g(h, 1, 1.0) * 0.4;
  const sumA = [...Array(24).keys()].reduce((s, h) => s + arrShape(h + .5), 0);
  const sumD = [...Array(24).keys()].reduce((s, h) => s + depShape(h + .5), 0);
  const wdF = [1.06, 0.95, 0.92, 0.96, 1.0, 1.08, 1.03];
  const out = [];
  for (let d = 0; d < days; d++) {
    const dayLs = startLocal + d * DAY;
    const m = new Date(dayLs * 1000).getUTCMonth();
    const season = 1 + 0.12 * Math.cos((m - 7) / 12 * 2 * Math.PI);  // 8월 피크
    const daily = 340 * wdF[wdOf(dayLs)] * season * (0.95 + rnd() * 0.1);
    for (let h = 0; h < 24; h++) {
      for (const [type, shape, sum] of [['A', arrShape, sumA], ['D', depShape, sumD]]) {
        const n = poisson(daily * shape(h + .5) / sum, rnd);
        for (let k = 0; k < n; k++) {
          const ls = dayLs + h * HOUR + Math.floor(rnd() * HOUR);
          out.push({
            t: ls - offsetH * HOUR, type,
            callsign: ['KAL', 'AAR', 'JNA', 'TWB', 'ANA', 'CPA', 'UAE', 'DAL', 'FDX', 'GTI'][Math.floor(rnd() * 10)] + (100 + Math.floor(rnd() * 900)),
            icao24: Math.floor(rnd() * 0xffffff).toString(16).padStart(6, '0'),
            other: ['RJTT', 'VHHH', 'ZSPD', 'WSSS', 'KLAX', 'RKPC', 'OMDB', 'EDDF'][Math.floor(rnd() * 8)]
          });
        }
      }
    }
  }
  return out;
}
