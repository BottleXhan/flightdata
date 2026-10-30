// web/js 모듈의 import 줄을 실제로 쓰는 이름에 맞춰 다시 만든다 (리팩터링 보조 도구).
//   node tools/fix_imports.mjs            → 고침
//   node tools/fix_imports.mjs --check    → 고칠 것이 있으면 목록을 출력하고 1 로 끝남 (CI 용)
// 필요: npm i -D acorn (package.json devDependencies)
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import * as acorn from 'acorn';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'web', 'js');
const files = [];
(function walk(d) { for (const n of fs.readdirSync(d)) { const p = path.join(d, n); fs.statSync(p).isDirectory() ? walk(p) : n.endsWith('.js') && files.push(p); } })(ROOT);

const patNames = (p, out = []) => {
  if (!p) return out;
  if (p.type === 'Identifier') out.push(p.name);
  else if (p.type === 'ObjectPattern') p.properties.forEach(q => patNames(q.type === 'RestElement' ? q.argument : q.value, out));
  else if (p.type === 'ArrayPattern') p.elements.forEach(e => patNames(e, out));
  else if (p.type === 'RestElement') patNames(p.argument, out);
  else if (p.type === 'AssignmentPattern') patNames(p.left, out);
  return out;
};
const declsOf = body => {
  const out = [];
  for (let s of body) {
    if (s.type === 'ExportNamedDeclaration' && s.declaration) s = s.declaration;
    if ((s.type === 'FunctionDeclaration' || s.type === 'ClassDeclaration') && s.id) out.push(s.id.name);
    if (s.type === 'VariableDeclaration') s.declarations.forEach(d => out.push(...patNames(d.id)));
  }
  return out;
};

// 1) 모듈별 export 이름
const parsed = new Map(), exportOwner = new Map(), eolOf = new Map();
for (const f of files) {
  const raw = fs.readFileSync(f, 'utf8');
  const src = raw.replace(/\r\n/g, '\n');                       // Windows 체크아웃(CRLF)도 같은 결과
  eolOf.set(f, raw.includes('\r\n') ? '\r\n' : '\n');
  const ast = acorn.parse(src, { ecmaVersion: 2023, sourceType: 'module', locations: true });
  parsed.set(f, { src, ast });
  for (const s of ast.body) {
    if (s.type !== 'ExportNamedDeclaration' || !s.declaration) continue;
    for (const n of declsOf([s.declaration])) {
      if (n === 'init') continue;
      if (exportOwner.has(n)) throw new Error(`같은 이름을 두 모듈이 export: ${n} (${exportOwner.get(n)}, ${f})`);
      exportOwner.set(n, f);
    }
  }
}

// 2) 모듈별 자유 식별자 (스코프 고려)
function freeNames(ast, top) {
  const refs = new Set(), scopes = [];
  const declared = n => scopes.some(s => s.has(n));
  const hoist = (body, sc) => declsOf(body).forEach(n => sc.add(n));
  const visitPattern = p => {
    if (!p) return;
    if (p.type === 'AssignmentPattern') { visitPattern(p.left); visit(p.right); }
    else if (p.type === 'ObjectPattern') p.properties.forEach(q => { if (q.computed) visit(q.key); visitPattern(q.type === 'RestElement' ? q.argument : q.value); });
    else if (p.type === 'ArrayPattern') p.elements.forEach(visitPattern);
    else if (p.type === 'RestElement') visitPattern(p.argument);
  };
  function visit(n, parent, key) {
    if (!n || typeof n.type !== 'string') return;
    switch (n.type) {
      case 'ImportDeclaration': return;
      case 'Identifier':
        if (parent && ((parent.type === 'MemberExpression' && key === 'property' && !parent.computed) ||
          (parent.type === 'Property' && key === 'key' && !parent.computed && !parent.shorthand) ||
          parent.type === 'LabeledStatement' || parent.type === 'BreakStatement' || parent.type === 'ContinueStatement')) return;
        if (!declared(n.name) && !top.has(n.name)) refs.add(n.name);
        return;
      case 'FunctionDeclaration': case 'FunctionExpression': case 'ArrowFunctionExpression': {
        const sc = new Set(); n.params.forEach(p => patNames(p).forEach(x => sc.add(x)));
        if (n.type === 'FunctionExpression' && n.id) sc.add(n.id.name);
        scopes.push(sc); n.params.forEach(visitPattern);
        if (n.body.type === 'BlockStatement') { hoist(n.body.body, sc); n.body.body.forEach(s => visit(s, n.body, 'body')); } else visit(n.body, n, 'body');
        scopes.pop(); return;
      }
      case 'BlockStatement': case 'StaticBlock': { const sc = new Set(); hoist(n.body, sc); scopes.push(sc); n.body.forEach(s => visit(s, n, 'body')); scopes.pop(); return; }
      case 'ForStatement': case 'ForInStatement': case 'ForOfStatement': {
        const sc = new Set(), init = n.init || n.left;
        if (init && init.type === 'VariableDeclaration') init.declarations.forEach(d => patNames(d.id).forEach(x => sc.add(x)));
        scopes.push(sc); for (const k of Object.keys(n)) if (n[k] && typeof n[k] === 'object' && k !== 'loc') visit(n[k], n, k); scopes.pop(); return;
      }
      case 'CatchClause': { scopes.push(new Set(patNames(n.param))); visit(n.body, n, 'body'); scopes.pop(); return; }
      case 'VariableDeclarator': visitPattern(n.id); visit(n.init, n, 'init'); return;
    }
    for (const k of Object.keys(n)) {
      if (k === 'type' || k === 'loc' || k === 'start' || k === 'end') continue;
      const v = n[k];
      if (Array.isArray(v)) v.forEach(x => visit(x, n, k)); else if (v && typeof v === 'object') visit(v, n, k);
    }
  }
  for (const s of ast.body) visit(s, null, null);
  return refs;
}

let changed = 0;
const check = process.argv.includes('--check');
for (const f of files) {
  const { src, ast } = parsed.get(f);
  const top = new Set(declsOf(ast.body));
  for (const s of ast.body) if (s.type === 'ImportDeclaration' && s.specifiers.some(x => x.type === 'ImportNamespaceSpecifier')) s.specifiers.forEach(x => top.add(x.local.name));
  const want = new Map();
  for (const n of freeNames(ast, top)) {
    const o = exportOwner.get(n);
    if (!o || o === f) continue;
    if (!want.has(o)) want.set(o, []);
    want.get(o).push(n);
  }
  // 손으로 쓴 import 는 그대로: 모듈 전체(import * as m) 또는 init
  const keep = ast.body.filter(s => s.type === 'ImportDeclaration' && s.specifiers.some(x => x.type === 'ImportNamespaceSpecifier' || (x.type === 'ImportSpecifier' && x.imported.name === 'init')));
  const lines = [...keep.map(s => src.slice(s.start, s.end))];
  for (const [o, ns] of [...want].sort((a, b) => (a[0] < b[0] ? -1 : 1))) {
    let rel = path.relative(path.dirname(f), o).split(path.sep).join('/');
    if (!rel.startsWith('.')) rel = './' + rel;
    lines.push(`import { ${ns.sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1)).join(', ')} } from '${rel}';`);
  }
  const imports = ast.body.filter(s => s.type === 'ImportDeclaration');
  const end = imports.length ? imports[imports.length - 1].end : 0;
  const lead = (src.match(/^(?:\/\/.*\n)+/) || [''])[0];          // 파일 머리 설명은 import 위에 그대로
  const rest = src.slice(Math.max(end, lead.length)).replace(/^\n+/, '');
  const next = lead + (lines.length ? lines.join('\n') + '\n\n' : '') + rest;
  if (next !== src) {
    changed++;
    if (check) console.log('import 정리 필요:', path.relative(ROOT, f));
    else fs.writeFileSync(f, next.replace(/\n/g, eolOf.get(f)));
  }
}
console.log(check ? (changed ? `${changed}개 파일` : 'import 정상') : `${changed}개 파일 고침`);
if (check && changed) process.exit(1);
