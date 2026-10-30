// CSV 가져오기와 이 브라우저(IndexedDB)에 저장한 데이터 목록.
import { loadMapData } from './airports.js';
import { apCode, buildYearButtons, csvRangeNow, csvYears, offsetFor, setRange, updateSpan } from './period.js';
import { csvAirportOf, csvRange, flightsToMovements, readFlightsCSV } from '../engine/csv.js';
import { $, setStatus, showMsg } from '../lib/dom.js';
import { esc, pad } from '../lib/fmt.js';
import { run } from '../run.js';
import { LAST_KEY } from '../ui/session.js';
import { renderHome } from '../views/home.js';
import { renderLib } from '../views/library.js';

/* ---------- CSV 불러오기 (OpenSky 운항 형식: Trino flights_data4 / REST /flights 와 같은 열) ---------- */
export let csvFlights = null;   // 마지막으로 읽은 파일의 운항 목록
export let csvSets = new Map();   // 공항 → { flights, names[], range }

/** 파일을 고르면 모두 읽어 공항별로 묶고, 분석할 공항을 고르게 한다 */
export let CSV_NAMES = [], CSV_FILES = [];
/** 불러온 CSV 를 모두 비움 (홈으로) */
export function clearCsv() { csvFlights = null; csvSets = new Map(); CSV_FILES = []; CSV_NAMES = []; }                   // 불러온 CSV 이름·파일 (최근 분석 기억·저장용)

export async function onCsvSelected(list, opts = {}) {
  const files = Array.isArray(list) ? list : ($('csvFile').files.length ? [...$('csvFile').files] : CSV_FILES);
  CSV_NAMES = files.map(f => f.name); CSV_FILES = files;
  csvFlights = null; csvSets = new Map();
  if (!files.length) return;
  await loadMapData();                               // 공항 시간대 (UTC 자동)
  try {
    for (const file of files) {
      const flights = readFlightsCSV(await file.text());
      const ap = csvAirportOf(flights, file.name);
      const set = csvSets.get(ap) || { flights: [], names: [], range: null };
      set.flights = set.flights.concat(flights); set.names.push(file.name);
      const r = csvRange(flights, ap, file.name, offsetFor(ap));
      if (r) set.range = set.range ? [r[0] < set.range[0] ? r[0] : set.range[0], r[1] > set.range[1] ? r[1] : set.range[1]] : r;
      csvSets.set(ap, set);
    }
    const aps = [...csvSets.keys()];
    $('csvAirport').innerHTML = aps.map(a => `<option value="${esc(a)}">${esc(a)} — ${esc(csvSets.get(a).names.join(', '))}</option>`).join('');
    $('csvAirportWrap').style.display = aps.length > 1 ? '' : 'none';
    const cur = apCode();
    selectCsvAirport(aps.includes(cur) ? cur : aps[0]);
    showMsg(null);
    if (!opts.fromStore) saveDataset(files).catch(e => console.warn('데이터 저장 실패', e));
  } catch (e) {
    showMsg(esc(e.message), 'err');
  }
}

/* ---------- 불러온 CSV 저장 (이 브라우저의 IndexedDB, gzip 압축) ----------
   다음에 페이지를 열면 마지막 데이터를 바로 불러와 분석한다. 서버나 다른 사람에게는 가지 않는다. */
export const DS_LAST = 'flightdata.lastDataset';

function dsDB() {
  return new Promise((ok, no) => {
    const r = indexedDB.open('flightdata', 1);
    r.onupgradeneeded = () => r.result.createObjectStore('datasets', { keyPath: 'id' });
    r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error);
  });
}

export async function dsTx(mode, fn) {
  const db = await dsDB();
  return new Promise((ok, no) => {
    const t = db.transaction('datasets', mode), st = t.objectStore('datasets'); let out;
    Promise.resolve(fn(st)).then(v => { out = v; });
    t.oncomplete = () => ok(out); t.onerror = () => no(t.error);
  });
}

export const req = r => new Promise((ok, no) => { r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error); });

async function gz(text) {
  if (!window.CompressionStream) return { text };
  return { blob: await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).blob() };
}

export async function ungz(f) {
  if (f.text != null) return f.text;
  return new Response(f.blob.stream().pipeThrough(new DecompressionStream('gzip'))).text();
}

async function saveDataset(files) {
  const id = files.map(f => `${f.name}:${f.size}`).sort().join('|');
  const trim = r => { const ys = csvYears(r), a = `${Math.min(...ys)}-01-01`, b = `${Math.max(...ys)}-12-31`; return [r[0] > a ? r[0] : a, r[1] < b ? r[1] : b]; };
  const aps = [...csvSets.keys()], ranges = [...csvSets.values()].map(x => x.range).filter(Boolean).map(trim);
  const lo = ranges.reduce((a, r) => (!a || r[0] < a ? r[0] : a), null), hi = ranges.reduce((a, r) => (!a || r[1] > a ? r[1] : a), null);
  const packed = [];
  for (const f of files) packed.push({ name: f.name, ...(await gz(await f.text())) });
  const old = await dsTx('readonly', st => req(st.get(id))).catch(() => null);
  const rec = { id, label: `${aps.join(', ')} · ${lo || '?'} ~ ${hi || '?'}`, files: packed, n: files.length,
                bytes: files.reduce((t, f) => t + f.size, 0), savedAt: Date.now(),
                aps, lo, hi, flights: [...csvSets.values()].reduce((t, x) => t + x.flights.length, 0),
                name: old?.name || '', note: old?.note || '', createdAt: old?.createdAt || old?.savedAt || Date.now() };
  await dsTx('readwrite', st => st.put(rec));
  try { localStorage.setItem(DS_LAST, id); } catch (e) {}
  renderSaved();
}

export async function loadDataset(id) {
  const rec = await dsTx('readonly', st => req(st.get(id)));
  if (!rec) return null;
  const files = [];
  for (const f of rec.files) files.push(new File([await ungz(f)], f.name, { type: 'text/csv' }));
  return files;
}

export async function renderSaved() {
  let list = [];
  try { list = await dsTx('readonly', st => req(st.getAll())); } catch (e) { $('savedWrap').hidden = true; return; }
  list.sort((a, b) => b.savedAt - a.savedAt);
  let cur = null; try { cur = localStorage.getItem(DS_LAST); } catch (e) {}
  const mb = b => b >= 1e6 ? (b / 1e6).toFixed(1) + 'MB' : Math.max(1, Math.round(b / 1e3)) + 'KB';
  const when = t => { const d = new Date(t); return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  $('savedList').innerHTML = list.map(r => `<div class="srow"><button type="button" class="sopen" data-open="${esc(r.id)}" aria-current="${r.id === cur}" title="${esc(r.files.map(f => f.name).join(', '))}">${esc(r.name || r.label)}<small>파일 ${r.n}개 · ${mb(r.bytes)} · ${when(r.savedAt)} 저장</small></button><button type="button" class="sdel" data-del="${esc(r.id)}" title="이 데이터 지우기" aria-label="지우기">✕</button></div>`).join('');
  $('savedWrap').hidden = !list.length;
  renderLib(list);
  renderHome(list);
}

export async function openSaved(id, restoreDates, autoRun = true) {
  const files = await loadDataset(id);
  if (!files) return false;
  setStatus('저장된 데이터 불러오는 중…');
  $('source').value = 'csv'; $('source').onchange();
  await onCsvSelected(files, { fromStore: true });
  try { localStorage.setItem(DS_LAST, id); } catch (e) {}
  if (restoreDates) {                                  // 지난번에 보던 기간 (파일 안에 있으면)
    let L = null; try { L = JSON.parse(localStorage.getItem(LAST_KEY) || 'null'); } catch (e) {}
    const r = csvRangeNow();
    if (L?.startDate && r && L.startDate >= r[0] && L.endDate <= r[1]) { $('startDate').value = L.startDate; $('endDate').value = L.endDate; updateSpan(); }
  }
  $('csvInfo').textContent = '저장된 데이터 · ' + $('csvInfo').textContent;
  renderSaved();
  if (csvFlights && autoRun) run();
  return true;
}

function selectCsvAirport(ap) {
  const set = csvSets.get(ap);
  if (!set) return;
  csvFlights = set.flights;
  $('csvAirport').value = ap;
  if (ap !== apCode()) $('tz').value = '';            // 공항이 바뀌면 직접 넣은 UTC 는 지움
  $('icao').value = ap;
  buildYearButtons();
  if (set.range) {
    // 파일 전체 기간 (여러 해면 연도 선택으로 줄일 수 있음). 경계에 며칠만 걸친 해(12/31 밤 출발편 등)는 뺌
    const ys = csvYears(set.range), lo = `${Math.min(...ys)}-01-01`, hi = `${Math.max(...ys)}-12-31`;
    setRange(set.range[0] > lo ? set.range[0] : lo, set.range[1] < hi ? set.range[1] : hi);
  }
  const n = flightsToMovements(set.flights, ap).length;
  $('csvInfo').textContent = `${set.names.join(', ')}: 운항 ${set.flights.length.toLocaleString()}건 · ${ap} 도착/출발 ${n.toLocaleString()}건` +
    (set.range ? ` (현지 ${set.range[0]} ~ ${set.range[1]})` : ' — 공항 코드를 확인하세요') +
    (set.range && csvYears(set.range).length > 1 ? ` · ${csvYears(set.range).reverse().join('·')}년 · "연도 선택"으로 일부 해만 볼 수 있습니다` : '') +
    (csvSets.size > 1 ? ` · 불러온 공항 ${csvSets.size}곳: ${[...csvSets.keys()].join(', ')}` : '');
}

export function init() {
  $('savedList').onclick = async e => {
    const o = e.target.closest('[data-open]'), d = e.target.closest('[data-del]');
    if (o) openSaved(o.dataset.open, false);
    if (d) {
      await dsTx('readwrite', st => st.delete(d.dataset.del));
      try { if (localStorage.getItem(DS_LAST) === d.dataset.del) localStorage.removeItem(DS_LAST); } catch (e) {}
      renderSaved();
    }
  };
  $('csvFile').onchange = () => onCsvSelected();
  // 공항을 바꾸면: 불러온 CSV 에 그 공항이 있으면 그 데이터로. 없으면 고른 공항을 그대로 두고 알려 줌
  // (예전에는 CSV 를 다시 읽어 CSV 의 공항으로 되돌렸음 — 지도에서 다른 공항을 눌러도 안 바뀌던 원인)
  $('icao').addEventListener('change', () => {
    const ap = apCode();
    if (csvSets.has(ap)) { if ($('source').value === 'csv') selectCsvAirport(ap); return; }
    if (csvSets.size && $('source').value === 'csv')
      $('csvInfo').textContent = `불러온 CSV에 ${ap} 데이터가 없습니다 (포함 공항: ${[...csvSets.keys()].join(', ')}). 다른 CSV를 선택하거나 OpenSky에서 다운로드하세요.`;
  });
  $('csvAirport').onchange = () => selectCsvAirport($('csvAirport').value);
}
