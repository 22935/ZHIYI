import type { ResourceUseQuery } from './identity'

export type RuntimeResourceType = 'agent' | 'model' | 'embedding' | 'tool' | 'worker' | 'skill' | 'mcp' | string
export type RuntimeResourceHealth = 'unknown' | 'online' | 'degraded' | 'offline' | string
export type RuntimeDeploymentTier = 'local' | 'terminal' | 'edge' | 'cloud' | string
export interface RuntimeResourceEndpoint {
  protocol: 'local' | 'http' | 'https' | 'grpc' | string
  address: string
}
/** Resource catalog read projection; command contracts are declared separately. */
export interface RuntimeResourceItem {
  profile: RuntimeResourceCatalogProfile
  snapshot: RuntimeResourceCatalogSnapshot
  snapshotVersion: number
}

export interface RuntimeResourceCatalogProfile {
  runtimeKind?: 'execution_backend' | 'model_server' | 'tool_service' | 'model_endpoint' | string | null
  displayName?: string | null
  nodeId?: string | null
  trust?: string | null
  hostRuntimeId?: string | null
  provider?: string | null
  sourceType?: string | null
  adapter?: string | null
  model?: string | null
  contextWindowTokens?: number | null
  maxOutputTokens?: number | null
  resourceId: string
  resourceType: RuntimeResourceType
  deploymentTier?: RuntimeDeploymentTier | null
  capabilities: string[]
  domains: string[]
  version: number
  enabled: boolean
  capacity: number
  privacyLevel?: string | null
  dataZone?: string | null
  location?: string | null
  ownerScope?: string | null
  modelIds?: string[] | null
  labels?: Array<{ key: string; value: string }> | null
  costMetadata?: Array<{ key: string; value: number }> | null
  computeCapacity?: {
    cpuCores?: number | null
    memoryMb?: number | null
    gpuType?: string | null
    gpuMemoryMb?: number | null
    bandwidthMbps?: number | null
  } | null
}

export interface RuntimeResourceCatalogSnapshot {
  healthStatus: RuntimeResourceHealth
  utilization?: number | null
  latencyMs?: number | null
  availableSlots?: number | null
  reliability?: number | null
  observedAt?: string | null
}
export interface ResourceRegistrationRequest {
  profile: {
    runtimeId: string; kind: 'execution_backend' | 'model_server' | 'tool_service'
    nodeId: string; displayName: string; placement: 'device' | 'edge' | 'cloud'; trust: string
    provider?: string; sourceType?: string; adapter?: string; metadata?: Record<string, unknown>
    capabilities: string[]; domains: string[]; capacity: number; ownerScope: string
    endpoint: RuntimeResourceEndpoint; modelIds: string[]; enabled: boolean
  }
  snapshot: { runtimeId: string; availableSlots: number; utilization: number; healthStatus: 'unknown' }
}
export interface ResourceRegistrationResult {
  resourceId?: string; nodeId?: string; credentialId: string; secret: string; ownerScope: string
}
export interface NodeCatalogItem {
  profile: { nodeId: string; displayName: string; placement: string; trust: string;
    ownerScope?: string | null; enabled: boolean; provider?: string | null; sourceType?: string | null; adapter?: string | null;
    computeCapacity?: RuntimeResourceCatalogProfile['computeCapacity'] }
  healthStatus: string; snapshotVersion: number
}
export interface NodeRegistrationRequest {
  profile: { nodeId: string; displayName: string; placement: 'device' | 'edge' | 'cloud'; trust: string; ownerScope: string;
    provider?: string; sourceType?: string; adapter?: string; metadata?: Record<string, unknown>;
    computeCapacity: { cpuCores: number; memoryMb: number; gpuMemoryMb: number; bandwidthMbps: number; gpuType: string | null } }
  snapshot: { nodeId: string; healthStatus: 'offline' }
}
/** 资源最近一次 attempt 绑定投影（execution_bindings JOIN attempts 的只读行）。 */
export interface ResourceUsageRecord {
  bindingId: string
  attemptId: string
  runId: string
  taskId: string
  missionId?: string | null
  taskTitle?: string | null
  semanticTaskKey?: string | null
  acgNodeId?: string | null
  agentId: string
  modelId: string
  attemptNumber: number
  attemptStatus: string
  startedAt?: string | null
  finishedAt?: string | null
  boundAt: string
}
/** 资源健康事件历史行（resource_health_events，倒序）。 */
export interface ResourceHealthEvent {
  observedAt?: string | null
  reliability?: number | null
  latencyMs?: number | null
  lastHeartbeat?: string | null
  version: number
}
/** 资源凭据元数据：仅 id 与年龄，秘密材料只在轮换响应中出现一次。 */
export interface ResourceCredentialMetadata {
  resourceId: string
  credentialId: string
  createdAt: string
}
export interface ResourceBindingObservation extends ResourceUseQuery {
  attemptId: string
  taskId: string
  semanticTaskKey?: string | null
  attemptNumber: number
  attemptStatus: string
  startedAt?: string | null
  finishedAt?: string | null
  deploymentTier: RuntimeDeploymentTier | null
}
export interface ResourceFailoverObservation {
  eventId: string
  stepId: string | null
  timestamp: string | null
  failedResources: Array<{
    stepId?: string
    resourceId: string
    error?: string | null
  }>
  retryStepIds: string[]
}
export interface ResourceObservation {
  runId: string
  items: RuntimeResourceItem[]
  bindings: ResourceBindingObservation[]
  attemptCount: number
  source: string
  failoverEvents: ResourceFailoverObservation[]
}
