type ViteRuntimeEnv = {
  DEV?: boolean
  MODE?: string
  VITE_API_BASE_URL?: string
}

const env = (import.meta as ImportMeta & { env?: ViteRuntimeEnv }).env || {}
const isDesktopFamilyMode = env.MODE === 'electron'
const defaultDesktopApiOrigin = isDesktopFamilyMode && !env.DEV
  ? 'http://127.0.0.1:18080'
  : ''
// Desktop hot reload always uses its local Vite proxy. In particular, do not
// inherit a shell-level VITE_API_BASE_URL left by another local service.
const configuredApiOrigin = (isDesktopFamilyMode && env.DEV
  ? ''
  : env.VITE_API_BASE_URL || defaultDesktopApiOrigin
).trim().replace(/\/$/, '')

// 内部发行版：启动器可能把 Backend 端口整体偏移（避免与本机其他程序冲突），
// 渲染层以 Main 同步下发的 origin 为准，构建期常量只作兜底。
const bridgeApiOrigin = (() => {
  const value = (globalThis as { kinlinDesktop?: { apiOrigin?: unknown } }).kinlinDesktop?.apiOrigin
  return typeof value === 'string' && /^https?:\/\//i.test(value) ? value.replace(/\/$/, '') : ''
})()

const absoluteApiOrigin = bridgeApiOrigin
  || (/^https?:\/\//i.test(configuredApiOrigin) ? configuredApiOrigin : '')

const normalizePath = (path: string): string => path.startsWith('/') ? path : `/${path}`

/**
 * Resolve an API path against the configured Backend origin.
 *
 * Web builds and the desktop hot-reload build keep relative URLs so they use
 * the active Vite proxy. The packaged Electron build (自定义协议同源规则)
 * falls back to the loopback TypeScript backend because no Vite server is present.
 */
export const apiUrl = (path: string): string => `${absoluteApiOrigin}${normalizePath(path)}`

/** Local writes require an explicit application header; no user credential is sent. */
export const LOCAL_REQUEST_HEADERS = { 'X-Zhiyi-Local-Request': '1' } as const

export const localFetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase()
  if (['GET', 'HEAD', 'OPTIONS'].includes(method)) return fetch(input, init)
  const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined))
  headers.set('X-Zhiyi-Local-Request', '1')
  return fetch(input, { ...init, headers })
}

/** Resolve health/readiness through the TypeScript backend's /api aliases. */
export const backendUrl = (path: string): string => {
  const normalizedPath = normalizePath(path)
  const gatewayPath = normalizedPath === '/api' || normalizedPath.startsWith('/api/')
    ? normalizedPath
    : `/api${normalizedPath}`
  return `${absoluteApiOrigin}${gatewayPath}`
}

export const websocketUrl = (path: string): string => {
  const normalizedPath = normalizePath(path)
  if (absoluteApiOrigin) {
    const parsed = new URL(absoluteApiOrigin)
    const protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${parsed.host}${normalizedPath}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${normalizedPath}`
}
