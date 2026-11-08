import { describe, expect, it } from 'vitest'
import { capabilityReason, inspectorLabel, inspectorValue } from './inspectorPresentation'

describe('Inspector display labels', () => {
  it('localizes known states and counters while preserving unknown evidence and IDs', () => {
    expect(inspectorValue('COMPLETED')).toBe('已完成')
    expect(inspectorValue('0 records')).toBe('0 条')
    expect(inspectorValue('18 packs')).toBe('18 组')
    expect(inspectorValue(0)).toBe(0)
    expect(inspectorValue(null)).toBe('暂未提供')
    expect(inspectorValue('run_79f5998a0b12')).toBe('run_79f5998a0b12')
    expect(inspectorValue('future-state')).toBe('future-state')
    expect(inspectorLabel('semanticTaskKey')).toBe('任务标识')
  })
  it('explains unavailable actions without claiming missing outputs or inventing authority', () => {
    expect(capabilityReason('RECOVERY_EVIDENCE_UNAVAILABLE')).toBe('当前没有满足恢复条件的失败步骤。')
    expect(capabilityReason('future-code')).toContain('技术详情')
    expect(capabilityReason('future-code')).not.toContain('产物丢失')
  })
})
