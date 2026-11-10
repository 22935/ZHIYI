import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, agentosRequest } from '@/services/api/agentos'

describe('resource marketplace API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('sends an installation request to the backend instead of registering in the browser', async () => {
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({
      data: { jobId: 'job-1', status: 'queued' }
    } as never)

    await agentosApi.installMarketplaceItem({ catalogId: 'model.demo' })

    expect(post).toHaveBeenCalledWith('/marketplace/installations', { catalogId: 'model.demo' })
  })

  it('encodes installation IDs before stop and uninstall commands', async () => {
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: {} } as never)
    const remove = vi.spyOn(agentosRequest, 'delete').mockResolvedValue({ data: {} } as never)

    await agentosApi.stopMarketplaceInstallation('job/with space')
    await agentosApi.uninstallMarketplaceInstallation('job/with space')

    expect(post).toHaveBeenCalledWith('/marketplace/installations/job%2Fwith%20space/stop')
    expect(remove).toHaveBeenCalledWith('/marketplace/installations/job%2Fwith%20space')
  })
})
