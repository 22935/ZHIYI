export type MarketplaceResourceKind = 'execution_backend' | 'model_server' | 'tool_service'
export type MarketplaceInstallationStatus =
  | 'queued' | 'installing' | 'registering' | 'running' | 'failed'
  | 'stopped' | 'uninstalling' | 'removed'

export interface MarketplaceCatalogItem {
  catalogId: string
  kind: MarketplaceResourceKind
  version: string
  displayName: string
  description: string
  sizeBytes: number
  requirements: Record<string, unknown>
  capabilities?: string[]
  category: string
}

export interface MarketplaceInstallation {
  jobId: string
  catalogId?: string | null
  ownerScope: string
  status: MarketplaceInstallationStatus
  runtimeId?: string | null
  displayName: string
  createdAt: string
  updatedAt: string
  errorSummary?: string | null
}

export interface CustomLocalResourceRequest {
  displayName: string
  kind: MarketplaceResourceKind
  endpoint: { protocol: 'http' | 'https'; address: string }
  capabilities: string[]
  modelIds?: string[]
  provider?: string
  adapter?: string
}
