/**
 * 桌面宿主的权限白名单决策（纯函数，供 main.ts 的会话加固接线、node --test 直测）。
 *
 * 设计边界：
 * - 唯一放行项：**应用自有页面来源**发起的 `media` 权限中的**纯音频（麦克风）**请求——
 *   Companion 的语音输入 / 语音唤醒（Web Speech API 在 Electron 里以 `media` 权限请求麦克风）。
 * - 摄像头（`video`）、屏幕捕获（`display-capture`）、定位、通知等其余权限一律拒绝，
 *   与既有 `hardenSession()` 的全拒策略保持同一收紧方向。
 * - 来源校验是第二道锁：即使渲染层被注入了远程内容（导航守卫之外的场景），
 *   非自有 Origin 的麦克风请求也不会被放行。
 */

/**
 * `new URL(url).origin` 的安全包装；解析失败返回 null（按未知来源处理 = 拒绝）。
 *
 * 注意：自定义应用协议（kinlin-app）属于 WHATWG「非特殊 scheme」，Node 侧 URL
 * 即使在 Electron 里注册为 standard 也可能返回字符串 'null'（origin 不透明）。
 * 此时手动拼 `scheme://host`——拼出的结果仍必须与白名单**精确匹配**，
 * 所以这个兜底不会放大授权面（kinlin-app://attacker 照样过不了白名单）。
 */
export function normalizeOrigin(url: string | undefined | null): string | null {
  if (typeof url !== 'string' || url.length === 0) return null
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch {
    return null
  }
  if (parsed.origin.length > 0 && parsed.origin !== 'null') return parsed.origin
  if (parsed.host.length === 0) return null
  return `${parsed.protocol}//${parsed.host}`
}

/**
 * 判断 mediaTypes 是否只涉及音频。
 * - `['audio']` → 放行（麦克风 / 语音识别）。
 * - 含 `'video'` → 拒绝（摄像头绝不放行）。
 * - 含 `'unknown'` → 拒绝（Electron 对无法归类的媒体请求，宁可错杀）。
 * - `undefined` / 空数组 → 放行：老版本 Electron 的 Web Speech 识别请求可能不带 mediaTypes，
 *   而 getUserMedia({ video }) 一定会带 `'video'`，故此分支不会打开摄像头。
 */
export function isAudioOnlyMediaRequest(mediaTypes: readonly string[] | undefined | null): boolean {
  if (mediaTypes == null || mediaTypes.length === 0) return true
  if (!mediaTypes.includes('audio')) return false
  return mediaTypes.every((type) => type === 'audio')
}

export interface PermissionRequestInput {
  permission: string
  /** setPermissionRequestHandler details.mediaTypes，仅 `media` 权限有意义。 */
  mediaTypes?: readonly string[] | undefined
  /** details.requestingUrl；用于来源校验。 */
  requestingUrl?: string | undefined
  /** 允许发起麦克风请求的 Origin 集合（应用协议 Origin + 开发服务器 Origin）。 */
  allowedOrigins: ReadonlySet<string>
}

/**
 * setPermissionRequestHandler 的同步决策：仅自有来源的纯音频 `media` 请求放行。
 */
export function shouldGrantPermissionRequest(input: PermissionRequestInput): boolean {
  if (input.permission !== 'media') return false
  if (!isAudioOnlyMediaRequest(input.mediaTypes)) return false
  const origin = normalizeOrigin(input.requestingUrl)
  return origin !== null && input.allowedOrigins.has(origin)
}

export interface PermissionCheckInput {
  permission: string
  /** setPermissionCheckHandler details.mediaType（单数：'audio' | 'video'）。 */
  mediaType?: string | undefined
  /** 发起检查的 Origin。 */
  requestingOrigin?: string | undefined
  allowedOrigins: ReadonlySet<string>
}

/**
 * setPermissionCheckHandler 的同步决策：与请求侧同一口径，
 * 仅自有来源的音频 `media` 检查返回 true（`navigator.permissions.query` / 能力探测走这里）。
 */
export function shouldGrantPermissionCheck(input: PermissionCheckInput): boolean {
  if (input.permission !== 'media') return false
  if (input.mediaType === 'video') return false
  const origin = normalizeOrigin(input.requestingOrigin)
  return origin !== null && input.allowedOrigins.has(origin)
}

/**
 * 汇总应用允许的 Origin 集合：自定义应用协议（打包形态）+ Vite dev server（开发形态）。
 * devServerUrl 为空（打包形态）时只含应用协议 Origin。
 */
export function buildAllowedOrigins(devServerUrl: string | undefined, parseHttp: (raw: string | undefined) => URL | null): Set<string> {
  const origins = new Set<string>()
  // kinlin-app 是 standard scheme，Origin 形如 kinlin-app://shell。
  origins.add('kinlin-app://shell')
  if (devServerUrl) {
    const parsed = parseHttp(devServerUrl)
    if (parsed) origins.add(parsed.origin)
  }
  return origins
}
