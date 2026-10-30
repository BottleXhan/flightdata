// 공항 찾기 칸 (이름·도시·한글·IATA).
import { loadMapData, searchAirports } from '../data/airports.js';
import { $ } from '../lib/dom.js';
import { esc } from '../lib/fmt.js';
import { AMAP, amapMarks } from './airport-map.js';

let apTimer = null;

export function init() {
  $('apSearch').addEventListener('input', () => {
    clearTimeout(apTimer);
    apTimer = setTimeout(async () => {
      await loadMapData();
      const res = searchAirports($('apSearch').value);
      $('apResults').innerHTML = res.map(([, , code, a]) => `<button type="button" data-ap="${esc(code)}"><b>${esc(code)}</b>${a[5] ? esc(a[5]) + ' · ' : ''}${esc(a[0])}<small> — ${esc([a[1], a[2]].filter(Boolean).join(', '))}${a[9] ? ` (${esc(a[9])})` : ''}</small></button>`).join('') ||
        ($('apSearch').value.trim() ? '<p class="text-xs muted" style="padding:.5rem">맞는 공항이 없습니다</p>' : '');
      $('apResults').hidden = !$('apResults').innerHTML;
      amapMarks(res.map(r => r[2]));
    }, 120);
  });
  $('apResults').onclick = e => {
    const b = e.target.closest('[data-ap]'); if (!b) return;
    $('icao').value = b.dataset.ap; $('apSearch').value = ''; $('apResults').hidden = true; AMAP.marks = [];
    $('icao').dispatchEvent(new Event('input')); $('icao').dispatchEvent(new Event('change'));
  };
  document.addEventListener('click', e => { if (!e.target.closest('.apsearch')) $('apResults').hidden = true; });
}
