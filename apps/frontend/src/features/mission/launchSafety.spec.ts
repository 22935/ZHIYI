import { beforeEach, expect, it, vi } from 'vitest'
import { workflowApi } from '@/services/api/workflow'
import { createMissionLaunchAttempt } from './launchAttempt'
import { workbenchLaunchCommand } from './command'
import { createNativeWorkbenchDraft } from '@/features/acg/workbench'

vi.mock('@/services/api/workflow', () => ({ workflowApi: { startWorkflowAsync: vi.fn() } }))
const request = () => workbenchLaunchCommand({ ...createNativeWorkbenchDraft(), taskGoal: 'goal' }, [])
beforeEach(() => { vi.resetAllMocks(); sessionStorage.clear(); localStorage.setItem('userId', 'local-owner') })
it('P0: attachment-not-ready never rotates the operation identity', async () => {
  const failure = { response: { status: 409, data: { detail: { code: 'ATTACHMENT_NOT_READY' } } } }
  vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(failure).mockResolvedValueOnce({ missionId: 'm', runId: 'r' } as any)
  const attempt = createMissionLaunchAttempt()
  await expect(attempt.launch(request())).rejects.toBe(failure)
  const original = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0]
  await attempt.launch(request())
  expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0]).toEqual(original)
})
