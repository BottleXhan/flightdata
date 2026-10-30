// 진입점: 각 모듈의 화면 연결(init)을 순서대로 실행하고, 프로그램(exe) 확인 → 저장 데이터 복원 순으로 시작한다.
import * as charts from './ui/charts.js';
import * as airports from './data/airports.js';
import * as datasets from './data/datasets.js';
import * as update from './desktop/update.js';
import * as settings from './desktop/settings.js';
import * as airportSearch from './ui/airport-search.js';
import * as overview from './views/overview.js';
import * as period from './data/period.js';
import * as peak from './views/peak.js';
import * as run from './run.js';
import * as filters from './filters.js';
import * as profile from './views/profile.js';
import * as airportMap from './ui/airport-map.js';
import * as library from './views/library.js';
import * as desktopWindow from './desktop/window.js';
import * as home from './views/home.js';
import * as nav from './ui/nav.js';
import * as mix from './views/mix.js';
import * as session from './ui/session.js';
import * as profileTarget from './views/profile-target.js';
import * as calendar from './views/calendar.js';
import * as theme from './ui/theme.js';
import * as sourceOverlay from './ui/source-overlay.js';
import { COLLECTOR, detectCollector } from './desktop/collect.js';
import { $, setStatus } from './lib/dom.js';

// 순서가 의미 있는 곳: period(기본 기간 7일) · filters · peak(기준 옵션) 이 먼저 값을 채우고 session 이 지난번 값으로 덮어씀
for (const m of [charts, airports, datasets, update, settings, airportSearch, overview, period, peak, run, filters, profile,
  airportMap, library, desktopWindow, home, nav, mix, session, profileTarget, calendar, theme, sourceOverlay]) m.init();

const bootDone = () => { $('bootOverlay').hidden = true; };
setTimeout(bootDone, 15000);
const boot = detectCollector();
Promise.all([boot.catch(() => {}), airports.loadMapData().catch(() => {})]).then(() => setTimeout(bootDone, 150));
boot.then(async () => {
  datasets.renderSaved();
  // 첫 화면은 항상 데이터 탭 (사용자 요청). 프로그램은 "OpenSky에서 받기", 웹은 지난번 CSV 를 골라만 두고 분석은 버튼으로
  if (COLLECTOR) return;
  let id = null; try { id = localStorage.getItem(datasets.DS_LAST); } catch (e) {}
  if (id) try { await datasets.openSaved(id, true, false); setStatus('최근 데이터 선택됨 — [분석 시작]으로 분석합니다'); } catch (e) { console.warn(e); }
});
