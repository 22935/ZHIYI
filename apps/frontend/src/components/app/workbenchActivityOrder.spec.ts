import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { WorkbenchSidebar } from '@/features/workspace/shell'
import {
  applyWorkbenchActivityOrder,
  readWorkbenchActivityOrder,
  writeWorkbenchActivityOrder
} from './workbenchActivityOrder'

const KEY = 'zhiyi.workbench.activity.order.v1'

describe('workbenchActivityOrder', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('falls back to the canonical order without persisted data', () => {
    expect(readWorkbenchActivityOrder()).toBeUndefined()
    expect(applyWorkbenchActivityOrder(undefined)).toEqual(['files', 'search', 'git', 'thought'])
  })

  it('round-trips a reordered list', () => {
    writeWorkbenchActivityOrder(['git', 'thought', 'files', 'search'])
    expect(readWorkbenchActivityOrder()).toEqual(['git', 'thought', 'files', 'search'])
    expect(applyWorkbenchActivityOrder(readWorkbenchActivityOrder())).toEqual(['git', 'thought', 'files', 'search'])
  })

  it('appends missing ids and drops unknown ones', () => {
    expect(applyWorkbenchActivityOrder(['thought', 'bogus' as WorkbenchSidebar])).toEqual(['thought', 'files', 'search', 'git'])
    expect(applyWorkbenchActivityOrder([])).toEqual(['files', 'search', 'git', 'thought'])
  })

  it('rejects malformed, incomplete or duplicated payloads', () => {
    localStorage.setItem(KEY, 'not-json')
    expect(readWorkbenchActivityOrder()).toBeUndefined()
    localStorage.setItem(KEY, JSON.stringify({ activityOrder: 'x' }))
    expect(readWorkbenchActivityOrder()).toBeUndefined()
    localStorage.setItem(KEY, JSON.stringify({ activityOrder: ['git'] }))
    expect(readWorkbenchActivityOrder()).toBeUndefined()
    localStorage.setItem(KEY, JSON.stringify({ activityOrder: ['git', 'git', 'files', 'search'] }))
    expect(readWorkbenchActivityOrder()).toBeUndefined()
  })
})
