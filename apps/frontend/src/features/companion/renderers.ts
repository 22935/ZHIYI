import type { AvatarRenderer, CompanionState, SkinManifest } from './types'

const NS = 'http://www.w3.org/2000/svg'

const EYE_PATHS: Record<CompanionState, { left: string; right: string; mouth: string }> = {
  idle: { left: 'M70 78a4 4 0 1 0 0.1 0', right: 'M130 78a4 4 0 1 0 0.1 0', mouth: 'M84 118h32' },
  listening: { left: 'M64 78a8 8 0 1 0 0.1 0', right: 'M124 78a8 8 0 1 0 0.1 0', mouth: 'M88 118h24' },
  thinking: { left: 'M64 72a5 5 0 1 0 0.1 0', right: 'M126 82a5 5 0 1 0 0.1 0', mouth: 'M96 118a5 5 0 1 0 0.1 0' },
  working: { left: 'M64 80h12', right: 'M124 80h12', mouth: 'M88 118h24' },
  happy: { left: 'M64 82q6 -10 12 0', right: 'M124 82q6 -10 12 0', mouth: 'M84 114q16 14 32 0' },
  alert: { left: 'M64 76a8 8 0 1 0 0.1 0', right: 'M124 76a8 8 0 1 0 0.1 0', mouth: 'M100 112v12' },
  sleeping: { left: 'M64 80h12', right: 'M124 80h12', mouth: 'M92 120h16' },
  error: { left: 'M64 74l12 12m0 -12l-12 12', right: 'M124 74l12 12m0 -12l-12 12', mouth: 'M86 122q14 -10 28 0' }
}

const createSvg = (tag: string): SVGElement => document.createElementNS(NS, tag)

/**
 * 默认皮肤：纯内联 SVG，零外部资源、零引擎依赖。
 * 只使用既有设计令牌，不引入新配色；状态差异靠形状而非颜色。
 */
export class InlineSvgRenderer implements AvatarRenderer {
  private svg: SVGElement | null = null
  private leftEye: SVGElement | null = null
  private rightEye: SVGElement | null = null
  private mouth: SVGElement | null = null
  private skin: SkinManifest | null = null

  mount(el: HTMLElement, skin: SkinManifest): void {
    this.skin = skin
    const svg = createSvg('svg')
    svg.setAttribute('viewBox', '0 0 200 200')
    svg.setAttribute('width', '100%')
    svg.setAttribute('height', '100%')
    svg.setAttribute('role', 'img')
    svg.setAttribute('aria-label', '虚拟伙伴形象')

    const body = createSvg('circle')
    body.setAttribute('cx', '100')
    body.setAttribute('cy', '100')
    body.setAttribute('r', '68')
    body.setAttribute('fill', 'var(--accent-fade)')
    body.setAttribute('stroke', 'var(--primary-line)')
    body.setAttribute('stroke-width', '2')
    svg.appendChild(body)

    const makeStroke = () => {
      const part = createSvg('path')
      part.setAttribute('fill', 'none')
      part.setAttribute('stroke', 'var(--primary-color)')
      part.setAttribute('stroke-width', '4')
      part.setAttribute('stroke-linecap', 'round')
      svg.appendChild(part)
      return part
    }
    this.leftEye = makeStroke()
    this.rightEye = makeStroke()
    this.mouth = makeStroke()
    el.appendChild(svg)
    this.svg = svg
    this.setState('idle')
  }

  setState(state: CompanionState): void {
    const paths = EYE_PATHS[state]
    this.leftEye?.setAttribute('d', paths.left)
    this.rightEye?.setAttribute('d', paths.right)
    this.mouth?.setAttribute('d', paths.mouth)
    this.svg?.setAttribute('data-companion-state', this.skin?.stateMap[state] ?? state)
  }

  destroy(): void {
    this.svg?.parentNode?.removeChild(this.svg)
    this.svg = null
    this.leftEye = null
    this.rightEye = null
    this.mouth = null
    this.skin = null
  }
}

const prefersReducedMotion = (): boolean => {
  try {
    return typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * 动效皮肤：按需动态加载既有 grok-character 引擎。
 * 引擎顶层会访问 window 并依赖 SVG 运行时，因此绝不静态导入；
 * 加载或构造失败时由上层 SkinRegistry 的 fallbackSkinId 降级。
 */
export class GrokRenderer implements AvatarRenderer {
  private bot: { setState(name: string): void; destroy(): void } | null = null
  private svg: SVGSVGElement | null = null
  private skin: SkinManifest | null = null
  private state: CompanionState = 'idle'
  private disposed = false

  async mount(el: HTMLElement, skin: SkinManifest): Promise<void> {
    this.skin = skin
    const module = await import('@/lib/grok-character')
    if (this.disposed) return
    const svg = createSvg('svg') as SVGSVGElement
    svg.setAttribute('viewBox', '0 0 200 200')
    svg.setAttribute('width', '100%')
    svg.setAttribute('height', '100%')
    el.appendChild(svg)
    this.svg = svg
    this.bot = new module.GrokCharacter(svg, {
      shape: 'blob',
      color: 'blue',
      scheme: 'light',
      mode: 'hold',
      state: skin.stateMap[this.state],
      followPointer: true,
      reduceMotion: prefersReducedMotion()
    })
  }

  setState(state: CompanionState): void {
    this.state = state
    this.bot?.setState(this.skin?.stateMap[state] ?? state)
  }

  destroy(): void {
    this.disposed = true
    this.bot?.destroy()
    this.bot = null
    this.svg?.parentNode?.removeChild(this.svg)
    this.svg = null
    this.skin = null
  }
}

export function createRenderer(skin: SkinManifest): AvatarRenderer {
  return skin.rendererType === 'grok-svg' ? new GrokRenderer() : new InlineSvgRenderer()
}
