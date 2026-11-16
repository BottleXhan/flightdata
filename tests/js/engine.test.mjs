// 분석 엔진(순수 계산) 회귀 테스트: 리팩터링 전 분석기에서 뽑은 결과(golden_engine.json)와 같아야 한다.
// 기준을 바꿔야 할 때(계산 로직을 일부러 고친 경우): py -3.13 tools/golden.py <폴더> --engine 의 engine.json 으로 교체
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { cases } from './golden_cases.mjs';
import { generateDemo } from '../../web/js/engine/demo.js';
import { analyze } from '../../web/js/engine/peak.js';
import { readFlightsCSV, flightsToMovements } from '../../web/js/engine/csv.js';
import { dateToLocalSec } from '../../web/js/lib/fmt.js';
import { codeLetter, sizeOf, typeLabel } from '../../web/js/engine/classify.js';

const golden = JSON.parse(fs.readFileSync(new URL('./golden_engine.json', import.meta.url), 'utf8'));
const got = JSON.parse(JSON.stringify(cases({ generateDemo, analyze, dateToLocalSec, readFlightsCSV, flightsToMovements })));

test('데모 데이터 생성 (고정 시드)', () => assert.deepEqual(got.demo, golden.demo));
for (let i = 0; i < golden.analyze.length; i++) {
  test(`첨두 산정 ${golden.analyze[i].cfg.method}`, () => assert.deepEqual(got.analyze[i], golden.analyze[i]));
}
test('CSV 읽기 · 운항 변환', () => assert.deepEqual(got.csv, golden.csv));

test('기종 라벨: 이름이 코드와 같으면 코드만', () => {
  assert.equal(typeLabel('A320'), 'A320');
  assert.equal(typeLabel('B738'), 'B738 (737-800)');
  assert.equal(typeLabel('b77w'), 'b77w (777-300ER)');
  assert.equal(typeLabel('ZZZZ'), 'ZZZZ');
});

test('ICAO 등급: 날개폭 경계 (Annex 14 Table 1-1)', () => {
  assert.deepEqual([14.9, 15, 23.99, 24, 35.81, 36, 51.9, 52, 64.8, 65, 79.77, 80].map(codeLetter), ['A', 'B', 'B', 'C', 'C', 'D', 'D', 'E', 'E', 'F', 'F', '']);
  const types = JSON.parse(fs.readFileSync(new URL('../../web/mapdata/aircraft_types.json', import.meta.url), 'utf8'));
  assert.equal(sizeOf({ typecode: 'B738' }, types), 'C');
  assert.equal(sizeOf({ typecode: 'b77w' }, types), 'E');
  assert.equal(sizeOf({ typecode: 'A388' }, types), 'F');
  assert.equal(sizeOf({ typecode: 'ZZZZ' }, types), 'U');
  assert.equal(sizeOf({ typecode: '' }, types), 'U');
});
