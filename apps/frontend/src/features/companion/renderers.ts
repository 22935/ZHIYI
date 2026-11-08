import type { AvatarRenderer, CompanionState, DiyShape, SkinManifest } from './types'

const NS = 'http://www.w3.org/2000/svg'

const EYE_PATHS: Record<CompanionState, { left: string; right: string; mouth: string }> = {
  idle: { left: 'M70 78a4 4 0 1 0 0.1 0', right: 'M130 78a4 4 0 1 0 0.1 0', mouth: 'M88 116q12 8 24 0' },
  listening: { left: 'M64 78a8 8 0 1 0 0.1 0', right: 'M124 78a8 8 0 1 0 0.1 0', mouth: 'M88 118h24' },
  // 思考时挑一边眉、保留另一只圆眼和小弧嘴，比「三个点」更像在琢磨而不是加载中。
  thinking: { left: 'M62 76q8 -9 16 -2', right: 'M126 80a5 5 0 1 0 0.1 0', mouth: 'M94 118q6 -6 12 0' },
  working: { left: 'M64 80h12', right: 'M124 80h12', mouth: 'M88 118h24' },
  happy: { left: 'M64 82q6 -10 12 0', right: 'M124 82q6 -10 12 0', mouth: 'M84 114q16 14 32 0' },
  alert: { left: 'M64 76a8 8 0 1 0 0.1 0', right: 'M124 76a8 8 0 1 0 0.1 0', mouth: 'M100 112v12' },
  sleeping: { left: 'M64 80h12', right: 'M124 80h12', mouth: 'M92 120h16' },
  error: { left: 'M64 74l12 12m0 -12l-12 12', right: 'M124 74l12 12m0 -12l-12 12', mouth: 'M86 122q14 -10 28 0' }
}

/** 朗读时的口型逐帧切换，让角色看起来真的在说话而不是静态贴图。 */
const TALK_FRAMES = [
  'M88 116q12 10 24 0',
  'M85 113q15 17 30 0',
  'M90 118q10 6 20 0',
  'M86 112q14 20 28 0'
]
const BLINK_EYE = 'M64 80h12'
const BLINK_EYE_RIGHT = 'M124 80h12'

const createSvg = (tag: string): SVGElement => document.createElementNS(NS, tag)

const prefersReducedMotion = (): boolean => {
  try {
    return typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

interface Face {
  setState(state: CompanionState): void
  setSpeaking(on: boolean): void
  setListening(on: boolean): void
  destroy(): void
}

/**
 * 表情层：三种皮肤共用的「眨眼 / 说话口型 / 收音光晕」。
 * 所有计时器都由 destroy() 对称清理，组件卸载不会留下跑动的 interval。
 */
function createFace(svg: SVGElement, stroke: string, motion: boolean): Face {
  const ring = createSvg('circle')
  ring.setAttribute('cx', '100')
  ring.setAttribute('cy', '100')
  ring.setAttribute('r', '88')
  ring.setAttribute('fill', 'none')
  ring.setAttribute('stroke', stroke)
  ring.setAttribute('stroke-width', '3')
  ring.setAttribute('class', 'companion-face-ring')
  ring.setAttribute('opacity', '0')
  svg.appendChild(ring)

  const makeStroke = (): SVGElement => {
    const part = createSvg('path')
    part.setAttribute('fill', 'none')
    part.setAttribute('stroke', stroke)
    part.setAttribute('stroke-width', '5')
    part.setAttribute('stroke-linecap', 'round')
    svg.appendChild(part)
    return part
  }
  const leftEye = makeStroke()
  const rightEye = makeStroke()
  const mouth = makeStroke()

  let state: CompanionState = 'idle'
  let speaking = false
  let listening = false
  let blinking = false
  let frame = 0
  let talkTimer: ReturnType<typeof setInterval> | null = null
  let blinkTimer: ReturnType<typeof setInterval> | null = null
  let blinkRestoreTimer: ReturnType<typeof setTimeout> | null = null
  let disposed = false

  const paint = (): void => {
    const paths = EYE_PATHS[state]
    leftEye.setAttribute('d', blinking ? BLINK_EYE : paths.left)
    rightEye.setAttribute('d', blinking ? BLINK_EYE_RIGHT : paths.right)
    mouth.setAttribute('d', speaking ? TALK_FRAMES[frame % TALK_FRAMES.length] : paths.mouth)
    svg.setAttribute('data-companion-speaking', speaking ? '1' : '0')
    svg.setAttribute('data-companion-listening', listening ? '1' : '0')
  }

  if (motion) {
    blinkTimer = setInterval(() => {
      if (disposed || speaking || state === 'sleeping') return
      blinking = true
      paint()
      if (blinkRestoreTimer !== null) clearTimeout(blinkRestoreTimer)
      blinkRestoreTimer = setTimeout(() => { blinking = false; paint() }, 130)
    }, 4200)
  }

  return {
    setState(next) { state = next; paint() },
    setSpeaking(on) {
      if (speaking === on) return
      speaking = on
      if (talkTimer !== null) clearInterval(talkTimer)
      talkTimer = null
      if (on && motion) {
        frame = 0
        talkTimer = setInterval(() => { frame += 1; paint() }, 140)
      }
      paint()
    },
    setListening(on) { listening = on; paint() },
    destroy() {
      disposed = true
      if (talkTimer !== null) clearInterval(talkTimer)
      if (blinkTimer !== null) clearInterval(blinkTimer)
      if (blinkRestoreTimer !== null) clearTimeout(blinkRestoreTimer)
      talkTimer = null
      blinkTimer = null
      blinkRestoreTimer = null
    }
  }
}

function makeSvgRoot(): SVGSVGElement {
  const svg = createSvg('svg') as SVGSVGElement
  svg.setAttribute('viewBox', '0 0 200 200')
  svg.setAttribute('width', '100%')
  svg.setAttribute('height', '100%')
  svg.setAttribute('role', 'img')
  svg.setAttribute('aria-label', '虚拟伙伴形象')
  return svg
}

/**
 * 默认皮肤：纯内联 SVG，零外部资源、零引擎依赖。
 * 只使用既有设计令牌，不引入新配色；状态差异靠形状而非颜色。
 */
export class InlineSvgRenderer implements AvatarRenderer {
  private svg: SVGSVGElement | null = null
  private face: Face | null = null
  private skin: SkinManifest | null = null
  private state: CompanionState = 'idle'

  mount(el: HTMLElement, skin: SkinManifest): void {
    this.skin = skin
    const svg = makeSvgRoot()
    const body = createSvg('circle')
    body.setAttribute('cx', '100')
    body.setAttribute('cy', '100')
    body.setAttribute('r', '68')
    body.setAttribute('fill', 'var(--accent-fade)')
    body.setAttribute('stroke', 'var(--primary-line)')
    body.setAttribute('stroke-width', '2')
    svg.appendChild(body)
    el.appendChild(svg)
    this.svg = svg
    this.face = createFace(svg, 'var(--primary-color)', !prefersReducedMotion())
    this.setState(this.state)
  }

  setState(state: CompanionState): void {
    this.state = state
    this.face?.setState(state)
    this.svg?.setAttribute('data-companion-state', this.skin?.stateMap[state] ?? state)
  }

  setSpeaking(on: boolean): void { this.face?.setSpeaking(on) }
  setListening(on: boolean): void { this.face?.setListening(on) }

  destroy(): void {
    this.face?.destroy()
    this.face = null
    this.svg?.parentNode?.removeChild(this.svg)
    this.svg = null
    this.skin = null
  }
}

const SHAPE_PATHS: Record<DiyShape, string> = {
  circle: 'M100 28a72 72 0 1 0 0.1 0',
  squircle: 'M64 28h72a36 36 0 0 1 36 36v72a36 36 0 0 1 -36 36H64a36 36 0 0 1 -36 -36V64a36 36 0 0 1 36 -36z',
  drop: 'M100 22C120 52 172 84 172 122a72 72 0 0 1 -144 0C28 84 80 52 100 22z',
  star: 'M100 24l19 43 47 5 -35 32 10 47 -41 -25 -41 25 10 -47 -35 -32 47 -5z',
  blob: 'M100 26c34 0 62 20 70 52 8 30 -2 58 -24 76 -20 16 -46 22 -70 18 -28 -4 -52 -20 -58 -48 -6 -26 4 -54 26 -72 16 -14 36 -26 56 -26z'
}

let diySeq = 0

/**
 * DIY 皮肤：形状、配色、上传图片、表情与动效全部由 custom manifest 驱动。
 * 换外观只重建渲染器，业务层仍只发 8 个语义状态。
 */
export class DiySvgRenderer implements AvatarRenderer {
  private svg: SVGSVGElement | null = null
  private face: Face | null = null
  private skin: SkinManifest | null = null
  private state: CompanionState = 'idle'

  mount(el: HTMLElement, skin: SkinManifest): void {
    const custom = skin.custom
    if (!custom) throw new Error('DIY skin is missing customization')
    this.skin = skin
    const svg = makeSvgRoot()
    const shapePath = SHAPE_PATHS[custom.shape] ?? SHAPE_PATHS.circle
    const clipId = `companion-diy-clip-${++diySeq}`

    const defs = createSvg('defs')
    const clip = createSvg('clipPath')
    clip.setAttribute('id', clipId)
    const clipShape = createSvg('path')
    clipShape.setAttribute('d', shapePath)
    clip.appendChild(clipShape)
    defs.appendChild(clip)
    svg.appendChild(defs)

    const body = createSvg('path')
    body.setAttribute('d', shapePath)
    body.setAttribute('fill', custom.background)
    body.setAttribute('stroke', custom.primary)
    body.setAttribute('stroke-width', '5')
    svg.appendChild(body)

    if (custom.image) {
      const image = createSvg('image')
      image.setAttribute('x', '24')
      image.setAttribute('y', '24')
      image.setAttribute('width', '152')
      image.setAttribute('height', '152')
      image.setAttribute('preserveAspectRatio', 'xMidYMid slice')
      image.setAttribute('href', custom.image)
      image.setAttribute('clip-path', `url(#${clipId})`)
      svg.appendChild(image)
      // 图片上盖一层半透明主色，保证表情线条始终看得清。
      const tint = createSvg('path')
      tint.setAttribute('d', shapePath)
      tint.setAttribute('fill', custom.primary)
      tint.setAttribute('opacity', '0.18')
      svg.appendChild(tint)
    } else {
      const highlight = createSvg('ellipse')
      highlight.setAttribute('cx', '76')
      highlight.setAttribute('cy', '62')
      highlight.setAttribute('rx', '24')
      highlight.setAttribute('ry', '12')
      highlight.setAttribute('fill', custom.accent)
      highlight.setAttribute('opacity', '0.55')
      highlight.setAttribute('transform', 'rotate(-24 76 62)')
      svg.appendChild(highlight)
    }

    // 腮红：让自定义形象也有「小脸」的感觉。
    const blush = (cx: string): SVGElement => {
      const dot = createSvg('ellipse')
      dot.setAttribute('cx', cx)
      dot.setAttribute('cy', '104')
      dot.setAttribute('rx', '9')
      dot.setAttribute('ry', '5')
      dot.setAttribute('fill', custom.accent)
      dot.setAttribute('opacity', '0.5')
      return dot
    }
    svg.appendChild(blush('58'))
    svg.appendChild(blush('142'))

    el.appendChild(svg)
    this.svg = svg
    const motion = custom.motion && !prefersReducedMotion()
    this.face = createFace(svg, custom.accent, motion)
    this.setState(this.state)
  }

  setState(state: CompanionState): void {
    this.state = state
    this.face?.setState(state)
    this.svg?.setAttribute('data-companion-state', this.skin?.stateMap[state] ?? state)
  }

  setSpeaking(on: boolean): void { this.face?.setSpeaking(on) }
  setListening(on: boolean): void { this.face?.setListening(on) }

  destroy(): void {
    this.face?.destroy()
    this.face = null
    this.svg?.parentNode?.removeChild(this.svg)
    this.svg = null
    this.skin = null
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
    const svg = makeSvgRoot()
    svg.setAttribute('class', 'companion-grok-svg')
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
    this.svg?.setAttribute('data-companion-state', this.skin?.stateMap[state] ?? state)
    this.svg?.setAttribute('data-companion-speaking', '0')
    this.svg?.setAttribute('data-companion-listening', '0')
  }

  setSpeaking(on: boolean): void { this.svg?.setAttribute('data-companion-speaking', on ? '1' : '0') }
  setListening(on: boolean): void { this.svg?.setAttribute('data-companion-listening', on ? '1' : '0') }

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
  if (skin.rendererType === 'grok-svg') return new GrokRenderer()
  if (skin.rendererType === 'diy-svg') return new DiySvgRenderer()
  return new InlineSvgRenderer()
}
