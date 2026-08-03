type Rgb = { r: number; g: number; b: number }

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const parseColor = (color: string): Rgb | null => {
  const normalized = color.trim()
  const hex = normalized.match(/^#([\da-f]{3}|[\da-f]{6})$/i)?.[1]
  if (hex) {
    const expanded = hex.length === 3 ? hex.split('').map(value => value + value).join('') : hex
    return {
      r: Number.parseInt(expanded.slice(0, 2), 16),
      g: Number.parseInt(expanded.slice(2, 4), 16),
      b: Number.parseInt(expanded.slice(4, 6), 16)
    }
  }

  const rgb = normalized.match(/^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i)
  if (!rgb) return null
  return {
    r: clamp(Math.round(Number(rgb[1])), 0, 255),
    g: clamp(Math.round(Number(rgb[2])), 0, 255),
    b: clamp(Math.round(Number(rgb[3])), 0, 255)
  }
}

/** Blend a semantic graph color into the current theme surface. */
export const mixGraphColor = (foreground: string, background: string, weight: number) => {
  const fg = parseColor(foreground)
  const bg = parseColor(background)
  if (!fg || !bg) return background
  const amount = clamp(weight, 0, 1)
  const channel = (front: number, back: number) => Math.round(back + (front - back) * amount)
  return `rgb(${channel(fg.r, bg.r)}, ${channel(fg.g, bg.g)}, ${channel(fg.b, bg.b)})`
}

export const edgeActivationOpacity = (activation: string) => ({
  active: 0.94,
  inactive: 0.62,
  terminated: 0.42,
  superseded: 0.32
})[activation] ?? 0.94

export const graphEdgeWidth = (edgeType: string) => ({
  dependency: 3,
  execution: 2,
  communication: 1.5,
  control_flow: 1.5,
  write: 1.4,
  read: 1.4,
  support: 1.4
})[edgeType] ?? 1.4
