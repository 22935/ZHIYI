import { agentosRequest } from '../client'
import type {
  CustomLocalResourceRequest,
  MarketplaceCatalogItem,
  MarketplaceInstallation
} from '../types/marketplace'

export const createMarketplaceApi = () => ({
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
