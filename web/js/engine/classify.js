// 운항 분류: 기종 크기(이 도구의 분류) · 항공사 코드 (순수 계산).
/* ---------- 필터 (사이드바 3): 운항 구분 · 방향 · 노선(국내/국제/나라) · 항공사 · 기종 크기 · 시간대 ---------- */
// 기종 크기: ICAO 기종 코드로 나눔 (이 도구의 분류). 광동체 = 대형, 협동체 제트 = 중형, 리저널 제트·터보프롭·소형기 = 소형
export const SIZE_L = /^(A30|A31[0]|A33|A34|A35|A38|B74|B76|B77|B78|MD11|DC10|IL96|IL86|B52|A124|AN22|A225|C5|C17|K35|KC10)/;
export const SIZE_M = /^(A31[89]|A32|A19N|A20N|A21N|B73|B37M|B38M|B39M|B3XM|B75|B71|B72|MD8|MD9|DC9|BCS|C919|E19|E29|E195|E295|F100|B46|RJ1|T204|T154|SU95)/;

export function sizeOf(m) {
  const t = (m.typecode || '').toUpperCase();
  if (!t) return 'U';
  return SIZE_L.test(t) ? 'L' : SIZE_M.test(t) ? 'M' : 'S';
}

export const alCode = m => /^[A-Z]{3}\d/.test(m.callsign || '') ? m.callsign.slice(0, 3) : '기타';
