// DOM 도우미와 상태 줄·메시지, 로컬 서버 POST.
export const $ = id => document.getElementById(id);
export const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export function setStatus(t) { $('status').textContent = t; }

export function setProgress(p) {
  $('progressWrap').classList.toggle('hidden', p == null);
  $('progress').style.width = ((p ?? 0) * 100).toFixed(1) + '%';
}

export function showMsg(html, kind = 'warn') {
  const el = $('msg');
  if (!html) { el.classList.add('hidden'); return; }
  el.className = 'text-sm p-3 ' + (kind === 'err' ? 'notice-err' : 'notice-warn');
  el.innerHTML = html;
}

/* ---------- FlightData 프로그램(exe) 안: "OpenSky에서 받기" ----------
   local_web 서버의 /api/collect 로 수집을 시작하고 /api/collect/status 를 지켜본 뒤, 받은 CSV 를 그대로 분석한다 */
export const apiPost = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b || {}) });
