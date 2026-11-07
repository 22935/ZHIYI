import type { SkinManifest } from './types'

/**
 * 内置皮肤清单。资源与逻辑分离：
 * 业务层只发 8 个语义状态，具体形象状态由 skin.stateMap 声明。
 */
export const BUILTIN_SKINS: SkinManifest[] = [
  {
    id: 'companion-static',
    version: '1.0.0',
    label: '轻量 SVG',
    rendererType: 'inline-svg',
    fallbackSkinId: null,
    stateMap: {
      idle: 'idle',
      listening: 'listening',
      thinking: 'thinking',
      working: 'working',
      happy: 'happy',
      alert: 'alert',
      sleeping: 'sleeping',
      error: 'error'
    }
  },
  {
    id: 'companion-grok',
    version: '1.0.0',
    label: '动效 SVG',
    rendererType: 'grok-svg',
    fallbackSkinId: 'companion-static',
    stateMap: {
      idle: 'idle',
      listening: 'listening',
      thinking: 'thinking',
      working: 'working',
      happy: 'happy',
      alert: 'alerting',
      sleeping: 'sleeping',
      error: 'sad'
    }
  }
]

export class SkinRegistry {
  private readonly skins = new Map<string, SkinManifest>()

  constructor(manifests: SkinManifest[] = BUILTIN_SKINS) {
    manifests.forEach(skin => this.register(skin))
  }

  register(skin: SkinManifest): void {
    if (this.skins.has(skin.id)) throw new Error(`Duplicate companion skin: ${skin.id}`)
    if (!skin.stateMap || Object.keys(skin.stateMap).length !== 8) {
      throw new Error(`Incomplete companion stateMap: ${skin.id}`)
    }
    this.skins.set(skin.id, skin)
  }

  resolve(skinId: string | null): SkinManifest {
    const found = skinId ? this.skins.get(skinId) : undefined
    const fallback = this.skins.get('companion-static')
    if (!fallback) throw new Error('Companion static skin is missing')
    return found ?? fallback
  }

  list(): SkinManifest[] {
    return [...this.skins.values()]
  }
}

export const defaultSkinRegistry = new SkinRegistry()

export const COMPANION_SKIN_STORAGE_KEY = 'companion.skin_id.v1'
