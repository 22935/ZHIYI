import { fork } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const projectArgument = process.argv.indexOf('--project');
const project = projectArgument < 0 ? fileURLToPath(new URL('../tsconfig.build.json', import.meta.url))
  : resolve(process.argv[projectArgument + 1] || '');
if (!existsSync(project)) throw new Error('Backend TypeScript project is missing');
const cacheBase = join(dirname(project), '.cache', 'backend-dev');
mkdirSync(cacheBase, { recursive: true });
const cache = realpathSync(mkdtempSync(join(cacheBase, 'session-')));
const generations = new Set();
let watcher, child, childReady = false, reloadRequested = false, pendingReload = false;
let latest, serving, debounce, stopping = false, finished = false;
const log = (event, extra = {}) => {
  const value = { event, ...extra };
  console.log(JSON.stringify(value));
  if (process.connected) process.send?.(value);
};
const removeGeneration = directory => {
  if (!directory || !generations.has(directory)) return;
  const absolute = resolve(directory);
  if (dirname(absolute) !== cache || !absolute.startsWith(cache + sep)
    || realpathSync(absolute) !== absolute) throw new Error('Unsafe development build cleanup');
  rmSync(absolute, { recursive: true });
  generations.delete(directory);
};
const prune = () => {
  for (const directory of generations) if (directory !== latest && directory !== serving) removeGeneration(directory);
};
const finish = () => {
  if (finished || child) return;
  finished = true;
  latest = serving = undefined;
  prune();
  // The empty session directory was created by this process only.
  if (realpathSync(cache) !== cache) throw new Error('Development cache identity changed');
  rmdirSync(cache); // non-recursive: never remove another process's files
  process.off('SIGINT', shutdown);
  process.off('SIGTERM', shutdown);
  process.off('disconnect', shutdown);
  if (process.connected) process.disconnect();
};
function shutdown() {
  if (stopping) return;
  stopping = true;
  clearTimeout(debounce);
  watcher?.close();
  if (child?.connected) child.send('shutdown');
  else if (!child) finish();
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
process.on('disconnect', shutdown);
process.on('message', message => { if (message === 'shutdown') shutdown(); });

const requestReload = () => {
  if (childReady && child?.connected && pendingReload && !reloadRequested) {
    reloadRequested = true;
    child.send('reload');
  }
};
const launch = () => {
  if (stopping || !latest || child) return;
  pendingReload = reloadRequested = childReady = false;
  serving = latest;
  const launched = fork(join(serving, 'main.js'), [], {
    execArgv: [], windowsHide: true, stdio: ['ignore', 'inherit', 'inherit', 'ipc'],
    env: process.env,
  });
  child = launched;
  launched.on('message', message => {
    if (!message || typeof message !== 'object') return;
    if (message.event === 'listening') {
      childReady = true;
      log('backend_ready', { pid: launched.pid, address: message.address });
      requestReload();
    } else if (message.event === 'reload_pending') log('reload_pending', { pid: launched.pid });
  });
  launched.on('error', () => { log('backend_spawn_failed'); process.exitCode = 1; });
  launched.once('exit', code => {
    child = undefined;
    serving = undefined;
    childReady = false;
    prune();
    if (stopping) finish();
    else if (pendingReload) launch();
    else { log('backend_exited', { code }); }
  });
};

const report = diagnostic => {
  console.error(ts.formatDiagnostics([diagnostic], {
    getCanonicalFileName: file => file, getCurrentDirectory: ts.sys.getCurrentDirectory,
    getNewLine: () => ts.sys.newLine,
  }).trimEnd());
};
const host = ts.createWatchCompilerHost(project, { noEmit: false, noEmitOnError: true }, ts.sys,
  ts.createSemanticDiagnosticsBuilderProgram, report, () => {});
host.afterProgramCreate = builder => {
  if (stopping) return;
  clearTimeout(debounce);
  const program = builder.getProgram();
  const diagnostics = ts.getPreEmitDiagnostics(program);
  const errors = diagnostics.filter(item => item.category === ts.DiagnosticCategory.Error);
  if (errors.length) { errors.forEach(report); log('build_failed', { errors: errors.length }); return; }
  const output = program.getCompilerOptions().outDir;
  if (!output) { log('build_failed', { reason: 'OUT_DIR_REQUIRED' }); return; }
  const generation = realpathSync(mkdtempSync(join(cache, 'build-')));
  generations.add(generation);
  try {
    // Emit a complete immutable generation. A running child must never import
    // a mixture of modules from two builds, even while it drains a long SSE.
    const emitted = program.emit(undefined, (file, text) => {
      const location = relative(output, file);
      if (isAbsolute(location) || location === '..' || location.startsWith('..' + sep)) {
        throw new Error('Compiler output escaped the configured directory');
      }
      const target = join(generation, location);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, text);
    });
    if (emitted.emitSkipped || emitted.diagnostics.some(item => item.category === ts.DiagnosticCategory.Error)
      || !existsSync(join(generation, 'main.js'))) {
      emitted.diagnostics.forEach(report);
      removeGeneration(generation);
      log('build_failed', { reason: 'EMIT_FAILED' });
      return;
    }
    latest = generation;
    prune();
    log('build_succeeded');
    debounce = setTimeout(() => {
      if (stopping) return;
      if (!child) launch();
      else { pendingReload = true; requestReload(); }
    }, 200);
  } catch {
    removeGeneration(generation);
    log('build_failed', { reason: 'EMIT_FAILED' });
  }
};
watcher = ts.createWatchProgram(host);
