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

const golden = JSON.parse(fs.readFileSync(new URL('./golden_engine.json', import.meta.url), 'utf8'));
const got = JSON.parse(JSON.stringify(cases({ generateDemo, analyze, dateToLocalSec, readFlightsCSV, flightsToMovements })));

test('데모 데이터 생성 (고정 시드)', () => assert.deepEqual(got.demo, golden.demo));
for (let i = 0; i < golden.analyze.length; i++) {
  test(`첨두 산정 ${golden.analyze[i].cfg.method}`, () => assert.deepEqual(got.analyze[i], golden.analyze[i]));
}
test('CSV 읽기 · 운항 변환', () => assert.deepEqual(got.csv, golden.csv));
