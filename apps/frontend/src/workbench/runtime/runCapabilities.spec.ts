import { expect, it } from 'vitest'
import { readRunCapabilities } from './runCapabilities'
import { projectLifecycle } from './lifecycleProjection'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'
import type { MissionWorkspaceProjection, WorkflowRun } from '@/services/api/agentos'

it('fails closed for absent, foreign, stale, malformed and unknown offers', () => {
  const cap = capabilitiesFixture('a', 'm')
  expect(readRunCapabilities(cap, 'm', 'a', 1)).toBe(cap)
  for (const value of [null, { ...cap, runId: 'b' }, { ...cap, missionId: 'foreign' },
    { ...cap, schemaVersion: 2 }, { ...cap, status: 'alien' }, { ...cap, canReview: undefined },
    { ...cap, runtimeRevision: -1 }, { ...cap, formalActions: ['invented'] }]) {
    expect(readRunCapabilities(value as any, 'm', 'a', 1)).toBeNull()
  }
  expect(readRunCapabilities(cap, 'm', 'a', 2)).toBeNull()
})
it('does not let selection, latest or a source edge authorize another Run', () => {
  const a = capabilitiesFixture('a', 'm', 'running', 3)
  const b = capabilitiesFixture('b', 'm', 'failed', 4)
  const workspace = { mission: { missionId: 'm' }, entries: [], graphNodes: [],
    activeRun: { runId: 'a', status: 'running', isActive: true, createdAt: '2026-01-01', actionCapabilities: a },
    runs: [{ runId: 'b', status: 'failed', isActive: false, createdAt: '2026-02-01', actionCapabilities: b }] } as MissionWorkspaceProjection
  const selected = projectLifecycle({ workspace, selectedRunId: 'a' })
  expect(selected).toMatchObject({ latestRunId: 'b', isReadOnly: false })
  expect(selected).not.toHaveProperty('currentRunId')
  expect(selected.capabilities?.canCancel).toBe(true)
  expect(projectLifecycle({ workspace, selectedRunId: 'b' }).capabilities?.canCancel).toBe(false)
  expect(projectLifecycle({ workspace, selectedRunId: 'unknown' }).isReadOnly).toBe(true)
})
it('uses the newer authoritative revision and ignores an old detailed Run', () => {
  const cap = capabilitiesFixture('a', 'm', 'cancelled', 5)
  const workspace = { mission: { missionId: 'm' }, entries: [], graphNodes: [], runs: [],
    activeRun: { runId: 'a', status: 'cancelled', actionCapabilities: cap } } as unknown as MissionWorkspaceProjection
  const old = { runId: 'a', missionId: 'm', runtimeRevision: 4, status: 'running',
    actionCapabilities: capabilitiesFixture('a', 'm', 'running', 4) } as WorkflowRun
  expect(projectLifecycle({ workspace, selectedRunId: 'a', run: old })).toMatchObject({ phase: 'CANCELLED',
    capabilities: { runtimeRevision: 5, canCancel: false }, isReadOnly: true })
})
it('does not resolve same-revision contradictory permissions with array order or timestamps', () => {
  const cap = capabilitiesFixture('a', 'm', 'running', 5)
  const workspace = { mission: { missionId: 'm' }, entries: [], graphNodes: [], runs: [],
    activeRun: { runId: 'a', status: 'running', actionCapabilities: cap } } as unknown as MissionWorkspaceProjection
  const run = { runId: 'a', missionId: 'm', runtimeRevision: 5, status: 'cancelled',
    actionCapabilities: capabilitiesFixture('a', 'm', 'cancelled', 5) } as WorkflowRun
  expect(projectLifecycle({ workspace, selectedRunId: 'a', run })).toMatchObject({
    phase: 'UNKNOWN', capabilities: null, isReadOnly: true })
})

it('allows only the offered terminal soft delete on a superseded Run', () => {
  const cap = capabilitiesFixture('a', 'm', 'superseded', 5, { lineage: { supersededByRunId: 'b' } })
  expect(readRunCapabilities(cap, 'm', 'a', 5)?.canDelete).toBe(true)
  expect(readRunCapabilities({ ...cap, canCancel: true }, 'm', 'a', 5)).toBeNull()
  expect(readRunCapabilities({ ...cap, canRerunSuccessor: true }, 'm', 'a', 5)).toBeNull()
  expect(readRunCapabilities(capabilitiesFixture('a', 'm', 'running', 5, { canDelete: true }), 'm', 'a', 5)).toBeNull()
})
