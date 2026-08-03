import { describe, expect, it } from 'vitest'

import { edgeActivationOpacity, graphEdgeWidth, mixGraphColor } from './acgGraphVisuals'

describe('ACG graph visual helpers', () => {
  it('mixes semantic colors into the active theme surface', () => {
    expect(mixGraphColor('#75C69A', '#343548', 0.24)).toBe('rgb(68, 88, 92)')
    expect(mixGraphColor('#fff', '#000', 0.5)).toBe('rgb(128, 128, 128)')
  })

  it('keeps inactive relationships visible while preserving state hierarchy', () => {
    expect(edgeActivationOpacity('active')).toBe(0.94)
    expect(edgeActivationOpacity('inactive')).toBe(0.62)
    expect(edgeActivationOpacity('terminated')).toBe(0.42)
    expect(edgeActivationOpacity('superseded')).toBe(0.32)
  })

  it('uses a clear width hierarchy for primary and cognitive edges', () => {
    expect(graphEdgeWidth('dependency')).toBe(3)
    expect(graphEdgeWidth('execution')).toBe(2)
    expect(graphEdgeWidth('support')).toBe(1.4)
  })
})
