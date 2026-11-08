/**
 * DIY 形象的纯逻辑层：默认值、净化、持久化、导入导出与 manifest 生成。
 *
 * 边界：所有配置只落在 localStorage，不进任何后端 Store；
 * localStorage 是用户可编辑的，因此读取时一律净化，绝不信任原始字段。
 * 图片只允许四类位图 dataURL，禁用 SVG/HTML，避免注入。
 */
import type { CompanionCustomization, DiyShape, SkinManifest } from './types'

export const CUSTOMIZATION_STORAGE_KEY = 'companion.customization.v1'
export const DIY_SKIN_ID = 'companion-diy'
export const MAX_NAME_LENGTH = 12
export const MAX_LINES = 6
export const MAX_LINE_LENGTH = 60
/** 压缩后的 256px 位图约 100~300KB，留足余量但防止 localStorage 配额被吃光。 */
export const MAX_IMAGE_CHARS = 700_000

const SHAPES: DiyShape[] = ['circle', 'squircle', 'drop', 'star', 'blob']

export const SHAPE_LABEL: Record<DiyShape, string> = {
  circle: '圆滚滚',
  squircle: '方团子',
  drop: '小水滴',
  star: '小星星',
  blob: '软乎乎'
}

export const DEFAULT_CUSTOMIZATION: CompanionCustomization = {
  version: 1,
  name: '知宝',
  shape: 'circle',
  primary: '#4c8dff',
  accent: '#b9d4ff',
  background: '#12233f',
  image: null,
  voice: { rate: 1, pitch: 1.12, volume: 0.9, muted: false },
  lines: [],
  motion: true
}

export interface DiyPreset {
  id: string
  label: string
  value: Pick<CompanionCustomization, 'shape' | 'primary' | 'accent' | 'background'>
}

export const DIY_PRESETS: DiyPreset[] = [
  { id: 'ocean', label: '海盐蓝', value: { shape: 'circle', primary: '#4c8dff', accent: '#b9d4ff', background: '#12233f' } },
  { id: 'peach', label: '蜜桃橘', value: { shape: 'blob', primary: '#ff9b6a', accent: '#ffd4b8', background: '#3d2118' } },
  { id: 'mint', label: '薄荷绿', value: { shape: 'drop', primary: '#4ac9a8', accent: '#baf2e2', background: '#10332c' } },
  { id: 'grape', label: '葡萄紫', value: { shape: 'star', primary: '#a98bff', accent: '#e0d3ff', background: '#271b45' } },
  { id: 'cocoa', label: '可可棕', value: { shape: 'squircle', primary: '#d0a06a', accent: '#f3ddbd', background: '#332619' } }
]

const HEX = /^#[0-9a-fA-F]{6}$/
const IMAGE_DATA_URL = /^data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$/

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value))

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? value as Record<string, unknown> : {}

const finiteOr = (value: unknown, fallback: number): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

/** 名字去掉控制字符与前后空白，最长 12 字；空名字回落默认。 */
export function sanitizeName(raw: unknown): string {
  if (typeof raw !== 'string') return DEFAULT_CUSTOMIZATION.name
  const cleaned = raw.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, MAX_NAME_LENGTH)
  return cleaned || DEFAULT_CUSTOMIZATION.name
}

export function isValidImage(raw: unknown): raw is string {
  return typeof raw === 'string' && raw.length <= MAX_IMAGE_CHARS && IMAGE_DATA_URL.test(raw)
}

export function sanitizeCustomization(raw: unknown): CompanionCustomization {
  const data = asRecord(raw)
  const voice = asRecord(data.voice)
  const color = (value: unknown, fallback: string): string =>
    typeof value === 'string' && HEX.test(value) ? value.toLowerCase() : fallback
  const lines = Array.isArray(data.lines)
    ? data.lines
      .filter((line): line is string => typeof line === 'string')
      .map(line => line.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, MAX_LINE_LENGTH))
      .filter(Boolean)
      .slice(0, MAX_LINES)
    : []
  return {
    version: 1,
    name: sanitizeName(data.name),
    shape: SHAPES.includes(data.shape as DiyShape)
      ? data.shape as DiyShape : DEFAULT_CUSTOMIZATION.shape,
    primary: color(data.primary, DEFAULT_CUSTOMIZATION.primary),
    accent: color(data.accent, DEFAULT_CUSTOMIZATION.accent),
    background: color(data.background, DEFAULT_CUSTOMIZATION.background),
    image: isValidImage(data.image) ? data.image : null,
    voice: {
      rate: clamp(finiteOr(voice.rate, DEFAULT_CUSTOMIZATION.voice.rate), 0.5, 2),
      pitch: clamp(finiteOr(voice.pitch, DEFAULT_CUSTOMIZATION.voice.pitch), 0, 2),
      volume: clamp(finiteOr(voice.volume, DEFAULT_CUSTOMIZATION.voice.volume), 0, 1),
      muted: voice.muted === true
    },
    lines,
    motion: data.motion !== false
  }
}

/** 把一行一条的文本域内容转成台词数组，供编辑器复用。 */
export function parseLines(raw: string): string[] {
  return sanitizeCustomization({ lines: raw.split('\n') }).lines
}

export interface CustomizationStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export function loadCustomization(storage: CustomizationStorage | null): CompanionCustomization {
  if (!storage) return { ...DEFAULT_CUSTOMIZATION }
  try {
    const raw = storage.getItem(CUSTOMIZATION_STORAGE_KEY)
    return raw ? sanitizeCustomization(JSON.parse(raw)) : { ...DEFAULT_CUSTOMIZATION }
  } catch {
    return { ...DEFAULT_CUSTOMIZATION }
  }
}

export function saveCustomization(storage: CustomizationStorage | null, value: CompanionCustomization): void {
  if (!storage) return
  try {
    storage.setItem(CUSTOMIZATION_STORAGE_KEY, JSON.stringify(sanitizeCustomization(value)))
  } catch {
    // 隐私模式或配额耗尽：DIY 退化为内存态，不影响主流程。
  }
}

/** 导出成可分享的 JSON；失败（含图片过大）时返回 null 交由 UI 提示。 */
export function exportCustomization(value: CompanionCustomization): string {
  return JSON.stringify(sanitizeCustomization(value), null, 2)
}

/** 导入只接受净化后的对象，非法内容不会让渲染器拿到脏数据。 */
export function importCustomization(raw: string): CompanionCustomization | null {
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return sanitizeCustomization(parsed)
  } catch {
    return null
  }
}

const IDENTITY_STATE_MAP: SkinManifest['stateMap'] = {
  idle: 'idle',
  listening: 'listening',
  thinking: 'thinking',
  working: 'working',
  happy: 'happy',
  alert: 'alert',
  sleeping: 'sleeping',
  error: 'error'
}

/** 生成 DIY 皮肤 manifest：状态映射恒等，外观全部由 custom 决定。 */
export function buildDiySkin(custom: CompanionCustomization): SkinManifest {
  return {
    id: DIY_SKIN_ID,
    version: '1.0.0',
    label: `我的形象 · ${custom.name}`,
    rendererType: 'diy-svg',
    fallbackSkinId: 'companion-static',
    stateMap: { ...IDENTITY_STATE_MAP },
    custom: sanitizeCustomization(custom)
  }
}
