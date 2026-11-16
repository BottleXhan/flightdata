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

// ICAO 기종 코드 → 일반 이름 (그래프 라벨용). 이름이 코드와 같거나 표에 없으면 코드만 보임.
// OpenSky 의 model 칸(A320 232SL, 777 2B5ER 등)은 등록 정보의 세부 형식·고객 번호라 라벨에 쓰지 않음.
export const TYPE_NAMES = {
  A306: 'A300-600', A30B: 'A300', A310: 'A310', A318: 'A318', A319: 'A319', A320: 'A320', A321: 'A321',
  A19N: 'A319neo', A20N: 'A320neo', A21N: 'A321neo', A332: 'A330-200', A333: 'A330-300', A337: 'A330 벨루가XL',
  A338: 'A330-800neo', A339: 'A330-900neo', A342: 'A340-200', A343: 'A340-300', A345: 'A340-500', A346: 'A340-600',
  A359: 'A350-900', A35K: 'A350-1000', A388: 'A380', A3ST: 'A300 벨루가', BCS1: 'A220-100', BCS3: 'A220-300',
  B712: '717', B721: '727-100', B722: '727-200', B732: '737-200', B733: '737-300', B734: '737-400', B735: '737-500',
  B736: '737-600', B737: '737-700', B738: '737-800', B739: '737-900', B37M: '737 MAX 7', B38M: '737 MAX 8',
  B39M: '737 MAX 9', B3XM: '737 MAX 10', B742: '747-200', B743: '747-300', B744: '747-400', B748: '747-8',
  B74S: '747SP', B752: '757-200', B753: '757-300', B762: '767-200', B763: '767-300', B764: '767-400',
  B772: '777-200', B77L: '777-200LR·777F', B773: '777-300', B77W: '777-300ER', B778: '777-8', B779: '777-9',
  B788: '787-8', B789: '787-9', B78X: '787-10',
  MD11: 'MD-11', MD82: 'MD-82', MD83: 'MD-83', MD88: 'MD-88', MD90: 'MD-90', DC10: 'DC-10',
  E170: 'E170', E175: 'E175', E190: 'E190', E195: 'E195', E290: 'E190-E2', E295: 'E195-E2', E75L: 'E175', E75S: 'E175',
  E135: 'ERJ-135', E145: 'ERJ-145', CRJ1: 'CRJ100', CRJ2: 'CRJ200', CRJ7: 'CRJ700', CRJ9: 'CRJ900', CRJX: 'CRJ1000',
  AT43: 'ATR 42-300', AT45: 'ATR 42-500', AT46: 'ATR 42-600', AT72: 'ATR 72', AT75: 'ATR 72-500', AT76: 'ATR 72-600',
  DH8A: 'Dash 8-100', DH8B: 'Dash 8-200', DH8C: 'Dash 8-300', DH8D: 'Dash 8-400', SF34: 'Saab 340', SB20: 'Saab 2000',
  F70: 'Fokker 70', F100: 'Fokker 100', B461: 'BAe 146-100', B462: 'BAe 146-200', B463: 'BAe 146-300',
  RJ85: 'Avro RJ85', RJ1H: 'Avro RJ100', SU95: 'Superjet 100', C919: 'C919', AJ27: 'ARJ21', A124: 'An-124',
  IL76: 'Il-76', IL96: 'Il-96', C130: 'C-130', C30J: 'C-130J', C17: 'C-17', K35R: 'KC-135', A400: 'A400M',
  B190: 'Beech 1900', C208: 'Cessna 208', C172: 'Cessna 172', PC12: 'PC-12', DHC6: 'Twin Otter'
};
export const typeName = code => TYPE_NAMES[(code || '').toUpperCase()] || '';
export const typeLabel = code => { const n = typeName(code); return n && n !== code ? `${code} (${n})` : code; };

export const alCode = m => /^[A-Z]{3}\d/.test(m.callsign || '') ? m.callsign.slice(0, 3) : '기타';
