// 프로그램(exe) 안에서만: 새 버전 확인 · 오른쪽 아래 알림 · 업데이트 적용.
import { $, apiPost, showMsg } from '../lib/dom.js';
import { esc } from '../lib/fmt.js';

/* ---------- 업데이트 (GitHub 최신 릴리스) — 프로그램 안에서만 ---------- */
let UPD = null;

export async function checkUpdate(manual = false) {
  try {
    const r = await fetch('/api/update/check' + (manual ? '?force=1' : ''), { cache: 'no-store' }), j = await r.json();
    if (!r.ok) throw new Error(j.error || r.status);
    UPD = j;
    $('setVer').textContent = `FlightData_${j.current || '?'}`;
    $('setVerNote').textContent = j.newer ? `새 버전 ${j.latest} 사용 가능` : '최신 버전입니다';
    $('setUpdGo').hidden = !j.newer;
    if (j.newer) openUpd();                              // 새 버전이 있으면 오른쪽 아래 알림
    else if (manual) showMsg(`최신 버전(FlightData_${j.current})을 사용 중입니다.`);
  } catch (e) { if (manual) showMsg('새 버전을 확인하지 못했습니다: ' + esc(e.message), 'warn'); }
}

export function openUpd() {
  if (!UPD) return;
  $('updTitle').textContent = `업데이트 가능 — FlightData_${UPD.latest}`;
  $('updSub').textContent = `현재 ${UPD.current} · 설정·보관함·CSV 데이터는 유지됩니다`;
  $('updList').innerHTML = (UPD.changes || []).map(c => `<li>${esc(c)}</li>`).join('') || '<li>변경 사항은 릴리스 페이지를 참고하세요</li>';
  $('updMsg').textContent = UPD.canApply ? '' : '이 환경에서는 자동 업데이트를 지원하지 않습니다 — 릴리스 페이지의 zip으로 새 버전을 받으세요.';
  $('updGo').disabled = !UPD.canApply; $('updGo').textContent = '업데이트'; $('updLater').disabled = false;
  $('updBarWrap').hidden = true; $('updModal').hidden = false;
}

export async function applyUpd() {
  $('updGo').disabled = $('updLater').disabled = true; $('updBarWrap').hidden = false; $('updMsg').textContent = '다운로드 중…';
  try {
    const r = await apiPost('/api/update/apply'); const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || r.status);
    for (;;) {
      await new Promise(ok => setTimeout(ok, 400));
      const st = await (await fetch('/api/update/status', { cache: 'no-store' })).json();
      if (st.total) $('updBar').style.width = Math.min(100, st.done / st.total * 100).toFixed(1) + '%';
      $('updMsg').textContent = st.text + (st.total ? ` (${(st.done / 1e6).toFixed(1)} / ${(st.total / 1e6).toFixed(1)}MB)` : '');
      if (st.state === 'error') throw new Error(st.error);
      if (st.state === 'ready') break;
    }
    $('updBar').style.width = '100%'; $('updMsg').textContent = '새 버전으로 재시작합니다…';
    await apiPost('/api/update/restart');
  } catch (e) {
    $('updMsg').textContent = '업데이트 실패: ' + e.message; $('updGo').disabled = $('updLater').disabled = false; $('updGo').textContent = '다시 시도';
  }
}

export function init() {
  $('updLater').onclick = () => { $('updModal').hidden = true; };
  $('updGo').onclick = applyUpd;
}
