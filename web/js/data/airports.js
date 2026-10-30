// 공항 자료(mapdata/airports_min.json)·노선 지도 윤곽 불러오기, 나라 이름, 공항 찾기.
import { $ } from '../lib/dom.js';

/* ---------- 공항 찾기 (이름·도시·한글·IATA) — airports_min.json ---------- */
export function searchAirports(q) {
  q = q.trim().toLowerCase();
  if (!q || !MAPDATA) return [];
  const out = [];
  for (const [code, a] of Object.entries(MAPDATA.airports)) {
    const [name, city, , , , iata, , , , ko] = a;
    let sc = null;
    if (code.toLowerCase() === q || (iata && iata.toLowerCase() === q)) sc = 0;
    else if (ko && ko.includes(q)) sc = 1;
    else if (name.toLowerCase().startsWith(q) || (city || '').toLowerCase().startsWith(q)) sc = 2;
    else if (name.toLowerCase().includes(q) || (city || '').toLowerCase().includes(q) || code.toLowerCase().startsWith(q)) sc = 3;
    if (sc != null) out.push([sc, iata ? 0 : 1, code, a]);
  }
  return out.sort((x, y) => x[0] - y[0] || x[1] - y[1] || (x[2] < y[2] ? -1 : 1)).slice(0, 8);
}

export const countryOf = ap => MAPDATA?.airports?.[ap]?.[2] || '';
export let regionName = cc => cc;

/* ---------- 노선 지도 (d3, 페이지와 함께 올린 mapdata/*.json) ---------- */
export let MAPDATA = null, MAPLOADING = null;

export function loadMapData() {
  if (MAPLOADING) return MAPLOADING;
  MAPLOADING = Promise.all(['mapdata/land.json', 'mapdata/airports_min.json'].map(u => fetch(u).then(r => { if (!r.ok) throw new Error(u); return r.json(); })))
    .then(([land, airports]) => { MAPDATA = { land, airports }; return true; })
    .catch(e => { console.warn('지도 자료를 불러오지 못함', e); $('rtMapNote').textContent = '지도 자료를 불러오지 못했습니다 (내 PC에서 HTML만 열면 mapdata 폴더가 같은 곳에 있어야 합니다).'; return false; });
  return MAPLOADING;
}

export function init() {
  try { const dn = new Intl.DisplayNames(['ko'], { type: 'region' }); regionName = cc => { try { return dn.of(cc) || cc; } catch (e) { return cc; } }; } catch (e) {}
}
