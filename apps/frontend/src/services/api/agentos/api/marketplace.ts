import { agentosRequest } from '../client'
import type {
  CustomLocalResourceRequest,
  MarketplaceCatalogItem,
  MarketplaceInstallation
} from '../types/marketplace'

export const createMarketplaceApi = () => ({
  async uploadMarketplaceToolFile(jobId: string, file: File): Promise<{ sourcePath: string; sizeBytes: number }> {
    const data = new FormData()
    data.append('file', file)
    return (await agentosRequest.post<{ sourcePath: string; sizeBytes: number }>(`/marketplace/installations/${encodeURIComponent(jobId)}/files`, data)).data
  },

  async executeMarketplaceTool(jobId: string, input: Record<string, unknown>): Promise<Record<string, unknown>> {
    return (await agentosRequest.post<Record<string, unknown>>(`/marketplace/installations/${encodeURIComponent(jobId)}/execute`, input, { timeout: 45000 })).data
  },

  async downloadMarketplaceToolFile(jobId: string, path: string): Promise<Blob> {
    return (await agentosRequest.get<Blob>(`/marketplace/installations/${encodeURIComponent(jobId)}/files`, { params: { path }, responseType: 'blob' })).data
  },

  async listMarketplaceCatalog(): Promise<{ items: MarketplaceCatalogItem[] }> {
    return (await agentosRequest.get<{ items: MarketplaceCatalogItem[] }>('/marketplace/catalog')).data
  },

  async listMarketplaceInstallations(): Promise<{ items: MarketplaceInstallation[] }> {
    return (await agentosRequest.get<{ items: MarketplaceInstallation[] }>('/marketplace/installations')).data
  },

  async installMarketplaceItem(payload: { catalogId: string }): Promise<MarketplaceInstallation> {
    return (await agentosRequest.post<MarketplaceInstallation>('/marketplace/installations', payload)).data
  },

  async createCustomMarketplaceResource(payload: CustomLocalResourceRequest): Promise<MarketplaceInstallation> {
    return (await agentosRequest.post<MarketplaceInstallation>('/marketplace/custom-resources', payload)).data
  },

  async stopMarketplaceInstallation(jobId: string): Promise<MarketplaceInstallation> {
    return (await agentosRequest.post<MarketplaceInstallation>(
      `/marketplace/installations/${encodeURIComponent(jobId)}/stop`
    )).data
  },

  async uninstallMarketplaceInstallation(jobId: string): Promise<MarketplaceInstallation> {
    return (await agentosRequest.delete<MarketplaceInstallation>(
      `/marketplace/installations/${encodeURIComponent(jobId)}`
    )).data
  }
})
