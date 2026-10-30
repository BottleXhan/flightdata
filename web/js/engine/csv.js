// OpenSky 운항 CSV 읽기 → 공항 도착·출발 운항(movement) 변환 (순수 계산).
import { fmtDate, HOUR } from '../lib/fmt.js';

export function parseCSV(text) {
  const rows = [];
  let row = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = ''; if (row.some(c => c !== '')) rows.push(row); row = [];
    } else cell += ch;
  }
  row.push(cell); if (row.some(c => c !== '')) rows.push(row);
  return rows;
}

export const AIRCRAFT_FIELDS = ['registration', 'typecode', 'model', 'manufacturer', 'operator', 'icaoaircrafttype'];

export function readFlightsCSV(text) {
  const rows = parseCSV(text.replace(/^\ufeff/, ''));
  if (rows.length < 2) throw new Error('CSV에 데이터가 없습니다.');
  const head = rows[0].map(h => h.trim().toLowerCase());
  const need = ['icao24', 'callsign', 'firstseen', 'lastseen', 'estdepartureairport', 'estarrivalairport'];
  const miss = need.filter(c => !head.includes(c));
  if (miss.length) throw new Error(`CSV에 필요한 열이 없습니다: ${miss.join(', ')}`);
  const ix = Object.fromEntries(need.map(c => [c, head.indexOf(c)]));
  // 선택 열: fetch_flights.py 가 OpenSky aircraft database 로 붙인 항공기 정보
  const opt = Object.fromEntries(AIRCRAFT_FIELDS.map(c => [c, head.indexOf(c)]).filter(([, i]) => i >= 0));
  return rows.slice(1).map(r => {
    const f = {
      icao24: r[ix.icao24], callsign: r[ix.callsign],
      firstSeen: +r[ix.firstseen] || null, lastSeen: +r[ix.lastseen] || null,
      estDepartureAirport: (r[ix.estdepartureairport] || '').trim().toUpperCase(),
      estArrivalAirport: (r[ix.estarrivalairport] || '').trim().toUpperCase()
    };
    for (const [c, i] of Object.entries(opt)) f[c] = (r[i] || '').trim();
    return f;
  });
}

/** 운항 목록 → 해당 공항의 도착(lastSeen)·출발(firstSeen) 운항, 기간 [beginUtc, endUtc) */
export function flightsToMovements(flights, airport, beginUtc, endUtc) {
  const out = [], seen = new Set();
  for (const f of flights) {
    for (const [isArr, t] of [[true, f.lastSeen], [false, f.firstSeen]]) {
      if ((isArr ? f.estArrivalAirport : f.estDepartureAirport) !== airport) continue;
      if (!t || (beginUtc != null && (t < beginUtc || t >= endUtc))) continue;
      const key = `${isArr ? 'A' : 'D'}|${f.icao24}|${t}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const mv = { t, type: isArr ? 'A' : 'D', callsign: (f.callsign || '').trim(), icao24: f.icao24, other: isArr ? f.estDepartureAirport : f.estArrivalAirport };
      for (const c of AIRCRAFT_FIELDS) if (f[c]) mv[c] = f[c];
      out.push(mv);
    }
  }
  return out;
}

/** 파일을 고르면 읽어 두고, 공항 기준 운항 범위로 분석 기간을 채움 */
/** 파일 이름 "<공항>_<시작>_<종료>.csv" 또는 운항 날짜 범위로 기간을 정한다.
 *  출발·도착이 모두 이 공항인 운항(회항 등)은 한쪽 시각이 기간 밖(전날·다음날)일 수 있어,
 *  하루 운항이 중앙값의 5% 미만인 가장자리 날짜는 뺀다. */
export function csvRange(flights, airport, fileName, offsetH) {
  const fromName = fileName.match(/([A-Z0-9]{4})_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})/i);
  if (fromName && fromName[1].toUpperCase() === airport) return [fromName[2], fromName[3]];
  const mv = flightsToMovements(flights, airport);
  if (!mv.length) return null;
  const perDay = new Map();
  for (const m of mv) { const d = fmtDate(m.t + offsetH * HOUR); perDay.set(d, (perDay.get(d) || 0) + 1); }
  const daysSorted = [...perDay.keys()].sort();
  const counts = [...perDay.values()].sort((x, y) => x - y), median = counts[Math.floor(counts.length / 2)];
  let i0 = 0, i1 = daysSorted.length - 1;
  while (i0 < i1 && perDay.get(daysSorted[i0]) < median * 0.05) i0++;
  while (i1 > i0 && perDay.get(daysSorted[i1]) < median * 0.05) i1--;
  return [daysSorted[i0], daysSorted[i1]];
}

/** 파일의 공항: 이름 앞 4자리, 아니면 출발·도착 공항 중 가장 많이 나온 코드 */
export function csvAirportOf(flights, fileName) {
  const m = fileName.match(/^([A-Z0-9]{4})_/i);
  if (m) return m[1].toUpperCase();
  const cnt = new Map();
  for (const f of flights) for (const a of [f.estDepartureAirport, f.estArrivalAirport]) if (a) cnt.set(a, (cnt.get(a) || 0) + 1);
  return [...cnt.entries()].sort((x, y) => y[1] - x[1])[0]?.[0] || '';
}
