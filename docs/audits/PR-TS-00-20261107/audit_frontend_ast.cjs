// Independent syntax traversal using the repository's already-installed TypeScript.
// Reads sources only; writes a new audit JSON with symbols/locations, never payload values.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../..');
const ts = require(path.join(root, 'apps/frontend/node_modules/typescript'));
const relative = p => path.relative(root, p).replaceAll('\\', '/');
function walk(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]); }
const result = [];
for (const file of ['apps/frontend/src', 'apps/desktop/electron/src'].flatMap(d => walk(path.join(root, d)))) {
  if (!/\.(ts|js|vue)$/.test(file) || /\.spec\./.test(file)) continue;
  const raw = fs.readFileSync(file, 'utf8');
  const scripts = file.endsWith('.vue') ? [...raw.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m => ({ text: m[1], offset: raw.slice(0, m.index + m[0].indexOf('>') + 1).split('\n').length - 1 })) : [{ text: raw, offset: 0 }];
  for (const script of scripts) {
    const sf = ts.createSourceFile(file, script.text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
    const imports = [];
    const functions = [];
    const calls = [];
    function visit(node, context) {
      if (ts.isImportDeclaration(node)) imports.push(node.moduleSpecifier.text);
      let here = context;
      if (ts.isFunctionLike(node) && node.body) {
        const name = node.name?.getText(sf) || (ts.isVariableDeclaration(node.parent) ? node.parent.name.getText(sf) : (ts.isPropertyAssignment(node.parent) ? node.parent.name.getText(sf) : context + '/<callback>'));
        const start = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1 + script.offset;
        const end = sf.getLineAndCharacterOfPosition(node.end).line + 1 + script.offset;
        here = name;
        functions.push({ name, start, end });
      }
      if (ts.isCallExpression(node) || ts.isNewExpression(node)) {
        const expr = node.expression.getText(sf);
        const start = sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1 + script.offset;
        const end = sf.getLineAndCharacterOfPosition(node.end).line + 1 + script.offset;
        const httpCandidate = /(?:^|\.)(?:fetch|serverFetch|EventSource|WebSocket)$/.test(expr) || /(?:request|api|axios|client|http).*\.(?:get|post|put|patch|delete|request)$/i.test(expr);
        calls.push({ expression: expr, enclosing: here, start, end, httpCandidate });
      }
      ts.forEachChild(node, child => visit(child, here));
    }
    visit(sf, '<module/setup>');
    result.push({ file: relative(file), imports, functions, calls });
  }
}
fs.writeFileSync(path.join(__dirname, 'frontend-ast-evidence.json'), JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
process.stdout.write(JSON.stringify({ parsedScriptBlocks: result.length, httpCandidateCalls: result.flatMap(x => x.calls).filter(x => x.httpCandidate).length }) + '\n');
