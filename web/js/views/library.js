// 보관함: 저장한 데이터 목록 · 찾기 · 정렬 · 이름/메모 · 병합 · 내려받기 · 삭제, exe 저장 폴더 CSV.
import { loadMapData, MAPDATA, regionName } from '../data/airports.js';
import { csvFlights, DS_LAST, dsTx, loadDataset, onCsvSelected, openSaved, renderSaved, req, ungz } from '../data/datasets.js';
import { COLLECTOR } from '../desktop/collect.js';
import { $, apiPost, setStatus } from '../lib/dom.js';
import { esc, pad } from '../lib/fmt.js';
import { run } from '../run.js';
import { setPane } from '../ui/nav.js';

/* ---------- 보관함: 저장한 데이터 보관 · 관리 (이 브라우저/프로그램의 IndexedDB) ----------
   목록 · 찾기 · 정렬 · 이름/메모 · 열기 · 내려받기 · 지우기 · 여러 개 함께 열기. exe 면 저장 폴더의 CSV 도 보여 줌 */
const LIB = { list: [], sel: new Set(), edit: null };
const libMB = b => b >= 1e9 ? (b / 1e9).toFixed(2) + 'GB' : b >= 1e6 ? (b / 1e6).toFixed(1) + 'MB' : Math.max(1, Math.round(b / 1e3)) + 'KB';
export const libWhen = t => { const d = new Date(t); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`; };
export const libAps = r => r.aps || [(r.label || '').split(' · ')[0]];
const libApName = c => { const a = MAPDATA?.airports?.[c]; return a ? (a[9] || a[0]) : ''; };
const libApCc = c => MAPDATA?.airports?.[c]?.[2] || '';

export const libPeriod = r => {
  if (r.lo || r.hi) return [r.lo, r.hi];
  const m = (r.label || '').match(/(\d{4}-\d\d-\d\d) ~ (\d{4}-\d\d-\d\d)/); return m ? [m[1], m[2]] : [null, null];
};

export async function renderLib(list) {
  if (!list) { try { list = await dsTx('readonly', st => req(st.getAll())); } catch (e) { list = []; } }
  const changed = list !== LIB.list; LIB.list = list;
  if (changed && !$('libDisk').hidden) renderDisk();          // 저장 폴더 CSV 의 등록됨/미등록 표시도 새 목록으로 (저장은 비동기라 추가 직후엔 옛 목록이었음)
  for (const id of [...LIB.sel]) if (!list.some(r => r.id === id)) LIB.sel.delete(id);
  let cur = null; try { cur = localStorage.getItem(DS_LAST); } catch (e) {}
  if (!MAPDATA) { await loadMapData(); }
  // 공항·나라 필터 목록 (보관한 데이터에 있는 것만)
  const allAps = [...new Set(list.flatMap(libAps))].sort(), allCc = [...new Set(allAps.map(libApCc).filter(Boolean))];
  const fill = (id, items, label) => { const cur = $(id).value;
    $(id).innerHTML = `<option value="">${label}</option>` + items.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
    if (items.some(([v]) => v === cur)) $(id).value = cur; };
  fill('libAp', allAps.map(c => [c, `${c} ${libApName(c)}`.trim()]), '모든 공항');
  fill('libCc', allCc.map(c => [c, regionName(c)]).sort((a, b) => a[1].localeCompare(b[1], 'ko')), '모든 나라');
  const q = $('libQ').value.trim().toLowerCase(), sort = $('libSort').value, fAp = $('libAp').value, fCc = $('libCc').value;
  const rows = list.filter(r => (!q || [r.name, r.label, r.note, ...libAps(r), ...libAps(r).map(libApName), ...libAps(r).map(c => regionName(libApCc(c))), ...r.files.map(f => f.name)].join(' ').toLowerCase().includes(q))
    && (!fAp || libAps(r).includes(fAp)) && (!fCc || libAps(r).some(c => libApCc(c) === fCc)));
  const key = { saved: r => -r.savedAt, ap: r => libAps(r).join(','), period: r => libPeriod(r)[0] || '', size: r => -r.bytes }[sort];
  rows.sort((a, b) => { const x = key(a), y = key(b); return x < y ? -1 : x > y ? 1 : 0; });
  const apset = new Set(list.flatMap(libAps)), fl = list.reduce((t, r) => t + (r.flights || 0), 0), by = list.reduce((t, r) => t + r.bytes, 0);
  $('lsN').textContent = list.length; $('lsAp').textContent = apset.size;
  $('lsFl').textContent = list.some(r => r.flights) ? fl.toLocaleString() : '–';
  $('lsMb').textContent = list.length ? libMB(by) : '–';
  $('lsMbSub').textContent = 'CSV 원본 크기 (압축 저장)';
  $('libSub').textContent = list.length ? `${list.length}개 · 마지막 저장 ${libWhen(Math.max(...list.map(r => r.savedAt)))}` : '';
  const days = r => { const [a, b] = libPeriod(r); return a && b ? Math.round((Date.parse(b) - Date.parse(a)) / 864e5) + 1 : null; };
  $('libTbl').innerHTML = !list.length
    ? '<tr><td class="lib-empty">저장된 데이터가 없습니다. 데이터 다운로드 또는 CSV 가져오기 시 자동 저장됩니다.</td></tr>'
    : !rows.length ? '<tr><td class="lib-empty">검색 결과가 없습니다</td></tr>'
    : `<thead><tr><th style="width:28px"><input type="checkbox" id="libAll" aria-label="모두 선택"></th><th>이름</th><th>공항</th><th>공항 이름</th><th>나라</th><th>기간</th><th class="num">일수</th><th class="num">운항</th><th class="num">파일</th><th class="num">크기</th><th>저장</th><th>메모</th><th></th></tr></thead><tbody>` +
      rows.map(r => {
        const [a, b] = libPeriod(r), ed = LIB.edit === r.id;
        return `<tr class="${r.id === cur ? 'cur' : ''}" data-id="${esc(r.id)}">
          <td><input type="checkbox" data-sel aria-label="선택" ${LIB.sel.has(r.id) ? 'checked' : ''}></td>
          <td class="lname">${ed ? `<input class="field" data-ename value="${esc(r.name || r.label)}" aria-label="이름">` : esc(r.name || r.label)}<small title="${esc(r.files.map(f => f.name).join(', '))}">${esc(r.files.map(f => f.name).join(', '))}</small></td>
          <td class="aps">${esc(libAps(r).join(', '))}</td>
          <td class="secondary">${libAps(r).map(c => { const a = MAPDATA?.airports?.[c]; return a ? (a[9] ? `${esc(a[9])} <small class="muted">${esc(a[0])}</small>` : esc(a[0])) : ''; }).filter(Boolean).join('<br>') || '–'}</td>
          <td class="secondary" style="white-space:nowrap">${esc([...new Set(libAps(r).map(c => regionName(libApCc(c))).filter(Boolean))].join(', ') || '–')}</td>
          <td style="white-space:nowrap">${a ? `${esc(a)} ~ ${esc(b)}` : '–'}</td>
          <td class="num">${days(r) ?? '–'}</td>
          <td class="num">${r.flights ? r.flights.toLocaleString() : '–'}</td>
          <td class="num">${r.n}</td>
          <td class="num">${libMB(r.bytes)}</td>
          <td style="white-space:nowrap" class="secondary">${libWhen(r.savedAt)}</td>
          <td class="lnote">${ed ? `<input class="field" data-enote value="${esc(r.note || '')}" placeholder="메모" aria-label="메모">` : esc(r.note || '')}</td>
          <td><div class="lact">${ed ? '<button class="btn btn-primary" data-act="save">저장</button><button class="btn" data-act="cancel">취소</button>'
            : `<button class="btn btn-primary" data-act="open">분석</button><button class="btn" data-act="edit" title="이름·메모 편집">✎</button><button class="btn" data-act="dl" title="CSV 다운로드">⤓</button><button class="btn" data-act="del" title="삭제">✕</button>`}</div></td></tr>`;
      }).join('') + '</tbody>';
  const all = $('libAll'); if (all) all.checked = rows.length > 0 && rows.every(r => LIB.sel.has(r.id));
  $('libSel').hidden = !LIB.sel.size; $('libSelN').textContent = `${LIB.sel.size}개 선택`;
  libWhere();
}

async function libWhere() {
  let t = COLLECTOR ? '저장 위치: exe 폴더의 app_data (PC 간 공유되지 않음).' : '저장 위치: 이 브라우저 (다른 브라우저·PC와 공유되지 않으며, 브라우저 데이터 삭제 시 함께 삭제됨).';
  try { const e = await navigator.storage?.estimate?.(); if (e?.quota) t += ` 사용 ${libMB(e.usage || 0)} / 여유 ${libMB(e.quota)}`; } catch (e) {}
  $('libWhere').textContent = t;
}

async function libPatch(id, patch) {
  await dsTx('readwrite', async st => { const r = await req(st.get(id)); if (r) st.put({ ...r, ...patch }); });
  await renderSaved();
}

async function libDownload(ids) {
  const recs = LIB.list.filter(r => ids.includes(r.id));
  const files = recs.flatMap(r => r.files);
  const save = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 5000); };
  if (files.length === 1) return save(new Blob([await ungz(files[0])], { type: 'text/csv' }), files[0].name);
  if (!window.JSZip) { for (const f of files) save(new Blob([await ungz(f)], { type: 'text/csv' }), f.name); return; }
  const z = new JSZip(); for (const f of files) z.file(f.name, await ungz(f));
  save(await z.generateAsync({ type: 'blob' }), recs.length === 1 ? `${(recs[0].name || recs[0].label).replace(/[\\/:*?"<>|~]+/g, '_').replace(/\s+/g, '')}.zip` : 'FlightData_보관함.zip');
}

async function libDelete(ids) {
  const names = LIB.list.filter(r => ids.includes(r.id)).map(r => r.name || r.label);
  if (!confirm(`보관함에서 삭제하시겠습니까?\n\n${names.join('\n')}\n\n(저장 폴더의 CSV 파일은 삭제되지 않습니다)`)) return;
  await dsTx('readwrite', st => { ids.forEach(id => st.delete(id)); });
  try { if (ids.includes(localStorage.getItem(DS_LAST))) localStorage.removeItem(DS_LAST); } catch (e) {}
  ids.forEach(id => LIB.sel.delete(id));
  renderSaved();
}

export async function libOpen(ids) {
  if (ids.length === 1) { setPane('data'); return openSaved(ids[0], false); }
  const files = [];
  for (const id of ids) files.push(...(await loadDataset(id)) || []);
  const seen = new Set(), uniq = files.filter(f => !seen.has(f.name + f.size) && seen.add(f.name + f.size));
  setPane('data');
  $('source').value = 'csv'; $('source').onchange();
  await onCsvSelected(uniq);                              // 합친 묶음도 보관함에 하나로 저장됨
  LIB.sel.clear();
  if (csvFlights) run();
}

/* exe: 저장 폴더의 CSV 파일 목록 (/api/files) — 보관함에 넣기 · 바로 분석 */
export async function renderDisk() {
  if (!COLLECTOR) return;
  try {
    const j = await (await fetch('/api/files', { cache: 'no-store' })).json();
    $('libDisk').hidden = false; $('libDiskDir').textContent = '· ' + j.dir;
    const inLib = new Set(LIB.list.flatMap(r => r.files.map(f => f.name)));
    $('libDiskTbl').innerHTML = !j.files.length ? '<tr><td class="lib-empty">이 폴더에 CSV 파일이 없습니다</td></tr>' :
      `<thead><tr><th>파일</th><th class="num">크기</th><th>수정</th><th>보관함</th><th></th></tr></thead><tbody>` +
      j.files.map((f, i) => `<tr data-i="${i}" data-name="${esc(f.name)}"><td class="lname">${esc(f.name)}</td><td class="num">${libMB(f.size)}</td><td class="secondary">${libWhen(f.mtime * 1000)}</td>
        <td>${inLib.has(f.name) ? '<span class="badge">등록됨</span>' : '<span class="muted text-xs">미등록</span>'}</td>
        <td><div class="lact"><button class="btn btn-primary" data-dact="open">분석</button>${inLib.has(f.name) ? '' : '<button class="btn" data-dact="add">보관함에 추가</button>'}</div></td></tr>`).join('') + '</tbody>';
  } catch (e) { console.warn(e); }
}

export function init() {
  $('libTbl').addEventListener('click', e => {
    const tr = e.target.closest('tr[data-id]'); if (!tr) return;
    const id = tr.dataset.id, b = e.target.closest('[data-act]');
    if (e.target.matches('[data-sel]')) { e.target.checked ? LIB.sel.add(id) : LIB.sel.delete(id); return renderLib(LIB.list); }
    if (!b) return;
    const act = b.dataset.act;
    if (act === 'open') libOpen([id]);
    if (act === 'dl') libDownload([id]);
    if (act === 'del') libDelete([id]);
    if (act === 'edit') { LIB.edit = id; renderLib(LIB.list); tr.ownerDocument.querySelector('[data-ename]')?.focus(); }
    if (act === 'cancel') { LIB.edit = null; renderLib(LIB.list); }
    if (act === 'save') { const r = LIB.list.find(x => x.id === id); LIB.edit = null;
      const nm = tr.querySelector('[data-ename]').value.trim();
      libPatch(id, { name: nm && nm !== r.label ? nm : '', note: tr.querySelector('[data-enote]').value.trim() }); }
  });
  $('libTbl').addEventListener('keydown', e => {
    if (!e.target.matches('[data-ename],[data-enote]')) return;
    if (e.key === 'Enter') e.target.closest('tr').querySelector('[data-act="save"]').click();
    if (e.key === 'Escape') { LIB.edit = null; renderLib(LIB.list); }
  });
  $('libTbl').addEventListener('change', e => {
    if (e.target.id !== 'libAll') return;
    const vis = [...$('libTbl').querySelectorAll('tr[data-id]')].map(t => t.dataset.id);
    vis.forEach(id => e.target.checked ? LIB.sel.add(id) : LIB.sel.delete(id)); renderLib(LIB.list);
  });
  $('libQ').addEventListener('input', () => renderLib(LIB.list));
  $('libSort').onchange = () => renderLib(LIB.list);
  $('libAp').onchange = $('libCc').onchange = () => renderLib(LIB.list);
  $('libSelNone').onclick = () => { LIB.sel.clear(); renderLib(LIB.list); };
  $('libOpenSel').onclick = () => libOpen([...LIB.sel]);
  $('libDlSel').onclick = () => libDownload([...LIB.sel]);
  $('libDelSel').onclick = () => libDelete([...LIB.sel]);
  ['libAdd', 'libAdd2'].forEach(id => $(id).addEventListener('change', async e => {
    const files = [...e.target.files]; e.target.value = '';
    if (!files.length) return;
    $('source').value = 'csv'; $('source').onchange();
    await onCsvSelected(files);                             // 읽어서 보관함에 저장 (데이터 탭에도 선택됨)
    setStatus(`보관함에 추가했습니다: ${files.map(f => f.name).join(', ')}`);
  }));
  $('libDiskTbl').addEventListener('click', async e => {
    const b = e.target.closest('[data-dact]'); if (!b) return;
    const tr = b.closest('tr'), txt = await (await fetch('/api/file/' + tr.dataset.i, { cache: 'no-store' })).text();
    const file = new File([txt], tr.dataset.name, { type: 'text/csv' });
    if (b.dataset.dact === 'open') setPane('data');
    $('source').value = 'csv'; $('source').onchange();
    await onCsvSelected([file]);                            // 저장이 끝나면 renderLib → renderDisk 로 "등록됨" 표시
    if (b.dataset.dact === 'open' && csvFlights) run();
  });
  $('libDiskRefresh').onclick = renderDisk;
  $('libDiskOpen').onclick = () => apiPost('/api/open-folder', { dir: $('cDir').value });
}
