import { rm } from 'node:fs/promises'
import { copyFileSync, mkdirSync } from 'node:fs'
import { build } from 'esbuild'

// 主进程与 Preload 统一 esbuild 打包：CJS 产物、external electron、不压缩，
// 保证审计可直接读产物。入口只有这两个，渲染层由 apps/frontend 独立构建。
const entries = [
  { entryPoints: ['src/main.ts'], outfile: 'dist/main.js' },
  { entryPoints: ['src/preload.ts'], outfile: 'dist/preload.js' }
]

await rm('dist', { recursive: true, force: true })

for (const entry of entries) {
  await build({
    ...entry,
    bundle: true,
    format: 'cjs',
    platform: 'node',
    target: 'node20',
    external: ['electron', 'canvas'],
    sourcemap: true,
    minify: false,
    logLevel: 'info'
  })
}

// 窗口/任务栏图标随 dist 一起进 asar：BrowserWindow.icon 按 dist 相对路径解析，
// electron-builder 的 files 白名单已含 dist/**，打包后同样可用。
mkdirSync('dist/icons', { recursive: true })
copyFileSync('icons/icon.ico', 'dist/icons/icon.ico')
